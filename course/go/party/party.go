// Package party runs several characters in one program, makes a party, and
// makes a new character.
//
// The program logs in once, reads the server and character lists once and
// loads G once. Then ConnectMember opens one socket for each character. Each
// character has its own World, Cooldowns, Budget and Actions: the server
// counts the call-cost for each socket.
//
// Concurrency: Party keeps its state behind its own lock. Its handlers run on
// the dispatch goroutine; its methods run on your goroutine.
package party

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"albot/actions"
	"albot/alsocket"
	"albot/api"
	"albot/bot"
	"albot/budget"
	"albot/cooldowns"
	"albot/gdata"
	"albot/world"
)

// region member

// Member is one character in the game: the same parts as a bot.Bot.
type Member struct {
	Name      string
	Sock      *alsocket.Socket
	G         *gdata.GData
	World     *world.World
	Cooldowns *cooldowns.Cooldowns
	Budget    *budget.Budget
	Act       *actions.Actions
	Character api.Character
}

// Close closes the socket of the member.
func (m *Member) Close() error { return m.Sock.Close() }

// ConnectMember connects one character with a login, a server and a G that
// we already have: bot.ConnectWith (bot.Connect without the HTTP calls).
func ConnectMember(ctx context.Context, auth api.Auth, server api.Server, character api.Character, G *gdata.GData) (*Member, error) {
	b, err := bot.ConnectWith(ctx, auth, server, character, G)
	if err != nil {
		return nil, err
	}
	return &Member{
		Name: character.Name, Sock: b.Sock, G: G, World: b.World, Cooldowns: b.Cooldowns,
		Budget: b.Budget, Act: b.Act, Character: character,
	}, nil
}

// endregion member

// region create-character

// CreateCharacter makes a new character on the account: HTTP
// `create_character` {name, char} (api.js:474-588). The name: 4 to 12
// letters, digits or "_", not used by anyone (api.js:24-31). The answer is
// {success: true}, or {failed: true, reason}: "name_used", "invalid_name",
// "reached_character_limit", ...
func CreateCharacter(ctx context.Context, auth api.Auth, name, ctype string) (json.RawMessage, error) {
	raw, err := api.APICall(ctx, "create_character", map[string]any{"name": name, "char": ctype}, &auth)
	if err != nil {
		return nil, err
	}
	var r struct {
		Failed bool   `json:"failed"`
		Reason string `json:"reason"`
	}
	if json.Unmarshal(raw, &r) == nil && r.Failed {
		return raw, fmt.Errorf("create_character failed: %s", r.Reason)
	}
	return raw, nil
}

// endregion create-character

// region party

// Party is the party of one character. The server sends `invite` {name} to
// the character that gets an invitation, and `party_update` {list, party}
// to each member when the party changes (node/server.js:12357-12546).
type Party struct {
	act *actions.Actions

	mu      sync.Mutex // guards list and invites
	list    []string   // the names in our party, the leader first
	invites map[string]bool
}

// New makes the party state of one character.
func New(w *world.World, act *actions.Actions) *Party {
	p := &Party{act: act, invites: map[string]bool{}}
	w.Listen("invite", func(d json.RawMessage) {
		var e struct{ Name string }
		if json.Unmarshal(d, &e) == nil {
			p.mu.Lock()
			p.invites[e.Name] = true
			p.mu.Unlock()
		}
	})
	w.Listen("party_update", func(d json.RawMessage) {
		var e struct{ List []string } // no list (or false) when we left or the party ended
		_ = json.Unmarshal(d, &e)
		p.mu.Lock()
		p.list = e.List
		p.mu.Unlock()
	})
	return p
}

// List returns the names in our party, the leader first.
func (p *Party) List() []string {
	p.mu.Lock()
	defer p.mu.Unlock()
	return append([]string(nil), p.list...)
}

// Invite invites name (a character on this server). The answer is a success
// with place "party", or "invalid" (no such character), "party_full".
func (p *Party) Invite(name string) (actions.GameResponse, error) {
	return p.act.Request("party", map[string]any{"event": "invite", "name": name}, "party", 2*time.Second)
}

// Accept accepts the invitation of name. It fails with "invitation_expired"
// when there was no invitation.
func (p *Party) Accept(name string) (actions.GameResponse, error) {
	return p.act.Request("party", map[string]any{"event": "accept", "name": name}, "party", 2*time.Second)
}

// Leave leaves the party.
func (p *Party) Leave() (actions.GameResponse, error) {
	return p.act.Request("party", map[string]any{"event": "leave"}, "party", 2*time.Second)
}

// WaitInvite waits until name invited us (true), or timeout passed (false).
func (p *Party) WaitInvite(name string, timeout time.Duration) bool {
	has := func() bool {
		p.mu.Lock()
		defer p.mu.Unlock()
		return p.invites[name]
	}
	for end := time.Now().Add(timeout); time.Now().Before(end); time.Sleep(50 * time.Millisecond) {
		if has() {
			return true
		}
	}
	return has()
}

// endregion party
