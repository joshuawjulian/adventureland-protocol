// Package bot puts the library together: log in, choose the server and the
// character, load G, connect, do the handshake, and make the World,
// Cooldowns, Budget and Actions of one character.
package bot

import (
	"context"
	"encoding/json"
	"os"
	"strconv"
	"strings"
	"time"

	"albot/actions"
	"albot/alsocket"
	"albot/api"
	"albot/budget"
	"albot/cooldowns"
	"albot/gdata"
	"albot/world"
)

// Welcome is the part of `welcome` that we read (node/server.js:4977-5019).
type Welcome struct {
	Region  string `json:"region"`  // "EU"
	Name    string `json:"name"`    // "I"
	Version int    `json:"version"` // the version of G on this server
}

// LoginError is a refused handshake. Reason is the reason of game_error,
// "server_full", "authorization_in_progress", the text of
// disconnect_reason, "disconnect: <why>", or "timeout".
type LoginError struct{ Reason string }

func (e *LoginError) Error() string { return "login failed: " + e.Reason }

// region error-reason

// ErrorReason is the reason of a `game_error` during the handshake. The
// payload is an object {message, phrase, phrase_args, reason?}
// (languages/index.js:256-258):
//   - a refused `auth` has `reason`: "no_character", "password_issue",
//     "mainframe_issue", "ingame", "poker_hand_active", "cancelled"
//     (node/server.js:11610-11652);
//   - a full server has the phrase "server.game_error.capacity"
//     (node/server.js:11587, 11879): we call it "server_full";
//   - "server.game_error.characters_unconfirmed": the server could not read
//     your other characters (node/server.js:11873-11876). Try again later.
//
// A bare string (for example "ERROR!") is its own reason.
func ErrorReason(d json.RawMessage) string {
	var e struct{ Message, Phrase, Reason string }
	if json.Unmarshal(d, &e) != nil {
		var text string
		_ = json.Unmarshal(d, &text) // a bare string
		return text
	}
	switch {
	case e.Reason != "":
		return e.Reason
	case e.Phrase == "server.game_error.capacity":
		return "server_full"
	case e.Phrase != "":
		return e.Phrase[strings.LastIndex(e.Phrase, ".")+1:] // "characters_unconfirmed"
	default:
		return e.Message
	}
}

// endregion error-reason

// region enter-game

// EnterGame does the handshake on a new socket and returns the `welcome`
// payload:
//
//  1. wait for `welcome` (the server sends it at once);
//  2. send `loaded`: the server ignores `auth` until `loaded` made an
//     observer for this socket (node/server.js:5028-5054, 11583);
//  3. send `auth`;
//  4. wait for `start`, or one of the failures below.
//
// Go only: the reader of AlSocket runs on its own goroutine, so `welcome`
// can arrive before or after World subscribes to its events. AlSocket keeps
// events only until the first subscription. Thus Connect starts the wait for
// `welcome` (sock.Expect) before it makes the World, and gives that wait to
// EnterGame as waitWelcome. With nil, EnterGame starts the wait itself.
func EnterGame(ctx context.Context, sock *alsocket.Socket, auth api.Auth, characterID string,
	timeout time.Duration, waitWelcome func(context.Context) (json.RawMessage, error)) (Welcome, error) {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	// Step 1: welcome.
	if waitWelcome == nil {
		waitWelcome = sock.Expect("welcome", nil)
	}
	var welcome Welcome
	raw, err := waitWelcome(ctx)
	if err != nil {
		return welcome, &LoginError{"no welcome: " + err.Error()}
	}
	if err := json.Unmarshal(raw, &welcome); err != nil {
		return welcome, err
	}

	// Listen for each result of `auth` BEFORE we send it. The handlers only
	// put the first result on the channel; the send never blocks.
	result := make(chan error, 1)
	report := func(err error) {
		select {
		case result <- err:
		default: // a result is already there: only the first one counts
		}
	}
	sock.On("start", func(json.RawMessage) { report(nil) }) // World keeps the payload
	sock.On("game_error", func(d json.RawMessage) { report(&LoginError{ErrorReason(d)}) })
	sock.On("game_log", func(d json.RawMessage) {
		var m struct{ Phrase string }
		// The character is still online, or the server still saves it after
		// a disconnect: no `start` comes on this socket (node/server.js:11577-11582).
		if json.Unmarshal(d, &m) == nil && m.Phrase == "server.game_log.authorization_in_progress" {
			report(&LoginError{"authorization_in_progress"})
		}
	})
	sock.On("disconnect_reason", func(d json.RawMessage) {
		var why string
		_ = json.Unmarshal(d, &why)
		report(&LoginError{why})
	})
	sock.On("disconnect", func(d json.RawMessage) { report(&LoginError{"disconnect: " + string(d)}) })

	// Step 2: loaded. The server reads none of these fields.
	if err := sock.Emit("loaded", map[string]any{"success": 1, "width": 1920, "height": 1080, "scale": 2}); err != nil {
		return welcome, err
	}
	// Step 3: auth. `character` is the id (CH_...), not the name.
	if err := sock.Emit("auth", map[string]any{
		"user":       auth.User,
		"auth":       auth.Auth,
		"character":  characterID,
		"no_html":    "1", // "a program controls this character": the server sets afk to "code"
		"passphrase": "",  // only test-mode servers check it
	}); err != nil {
		return welcome, err
	}

	// Step 4: start, a failure, or the timeout.
	select {
	case err := <-result:
		return welcome, err
	case <-ctx.Done():
		return welcome, &LoginError{"timeout"}
	}
}

// endregion enter-game

// Bot is one character in the game, with all parts of the library.
type Bot struct {
	Sock      *alsocket.Socket
	G         *gdata.GData
	World     *world.World
	Cooldowns *cooldowns.Cooldowns
	Budget    *budget.Budget
	Act       *actions.Actions
	Auth      api.Auth
	Server    api.Server
	Character api.Character
	Welcome   Welcome
}

// region connect

// Connect logs in and enters the game with AL_SERVER and AL_CHARACTER.
func Connect(ctx context.Context) (*Bot, error) {
	auth, err := api.Login(ctx)
	if err != nil {
		return nil, err
	}
	servers, characters, err := api.ServersAndCharacters(ctx, auth)
	if err != nil {
		return nil, err
	}
	server, err := api.FindServer(servers, os.Getenv("AL_SERVER"))
	if err != nil {
		return nil, err
	}
	character, err := api.FindCharacter(characters, os.Getenv("AL_CHARACTER"))
	if err != nil {
		return nil, err
	}
	G, err := gdata.LoadG(ctx, api.BaseURL())
	if err != nil {
		return nil, err
	}
	return ConnectWith(ctx, auth, server, character, G)
}

// ConnectWith does the steps after the HTTP calls: the socket, the World, the
// handshake and the other parts. Part 3 calls it for each character of a
// party, with one login, one server list and one G for all of them.
func ConnectWith(ctx context.Context, auth api.Auth, server api.Server, character api.Character, G *gdata.GData) (*Bot, error) {
	b := &Bot{Auth: auth, Server: server, Character: character, G: G}
	var err error
	if b.Sock, err = alsocket.Connect(ctx, api.SocketURL(b.Server, api.BaseURL())); err != nil {
		return nil, err
	}
	waitWelcome := b.Sock.Expect("welcome", nil) // first: see EnterGame
	b.World = world.New(b.Sock, b.G)             // before `loaded`, so it sees `start`
	// 30 s: the handshake takes much less on a working server.
	b.Welcome, err = EnterGame(ctx, b.Sock, b.Auth, b.Character.ID, 30*time.Second, waitWelcome)
	if err != nil {
		b.Sock.Close()
		return nil, err
	}
	b.Cooldowns = cooldowns.New(b.World)
	b.Budget = budget.New(b.Sock, b.World)
	b.Act = actions.New(b.Sock, b.World, b.Cooldowns, b.Budget)
	return b, nil
}

// endregion connect

// Close closes the socket. The server then saves the character.
func (b *Bot) Close() error { return b.Sock.Close() }

// region reconnect-delay

// ReconnectDelayMs is the one reconnect rule of the course. After a
// disconnect, the server keeps the character in dc_players until its save
// ends, and a new `auth` gets "Authorization in progress"
// (node/server.js:11577-11582). So do not reconnect at once:
//   - attempt 0 (the first try) waits AL_RECONNECT_MS (30 s by default);
//   - each failed try doubles the wait, up to 300 s;
//   - after a session that lasted 5 minutes, start again from attempt 0.
//
// Close the old socket first, and always do the full handshake on a new one.
func ReconnectDelayMs(attempt int) int {
	first := 30000 // ms
	if v, err := strconv.Atoi(os.Getenv("AL_RECONNECT_MS")); err == nil && v > 0 {
		first = v
	}
	const most = 300000 // 300 s
	delay := first
	for i := 0; i < attempt && delay < most; i++ {
		delay *= 2
	}
	return min(delay, most)
}

// endregion reconnect-delay
