// Package api is the HTTP side of Adventure Land: log in, read the list of
// game servers and characters, and make the WebSocket URL of a game server.
//
// The live HTTP API takes a POST with a JSON body at /api/<method>. The reply
// is always HTTP 200 with a JSON object, also when the call fails: then the
// object has failed: true and a reason (common_engine handlers.js:28-32).
// Standard library only.
package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

// Auth is a session: the cookie auth=<User>-<Auth> on the wire.
type Auth struct {
	User string // the user id, "US_..."
	Auth string // the token
}

// Server is one game server of the list (adventure_functions.js:761-776).
type Server struct {
	Key     string `json:"key"`     // the database id, for example "SR_EUI"
	Region  string `json:"region"`  // "EU", "US", "ASIA"
	Name    string `json:"name"`    // "I", "II", "PVP", ...
	Players int    `json:"players"` // characters online on it now
	Address string `json:"address"` // the host (and port) of the WebSocket
	Path    string `json:"path"`    // the Socket.IO path on that host, "/ws1/"
}

// Character is one character of the account (adventure_functions.js:821-843).
type Character struct {
	ID     string `json:"id"`   // "CH_...": send this (not the name) in the socket "auth" event
	Name   string `json:"name"` // the name, the value of AL_CHARACTER
	Type   string `json:"type"` // the class: "warrior", "priest", ...
	Level  int    `json:"level"`
	Server string `json:"server,omitempty"` // "SR_EUI", only while it is online
}

// The HTTP client of the course. 60 s: G (from gdata) is a few MB, and a slow
// link needs time for it. The other calls are small.
var client = &http.Client{Timeout: 60 * time.Second}

// BaseURL is the website and its HTTP API: AL_BASE_URL, or the live site.
// It has no "/" at the end, so that BaseURL() + "/api/..." is correct.
func BaseURL() string {
	base := os.Getenv("AL_BASE_URL")
	if base == "" {
		base = "https://adventure.land"
	}
	return strings.TrimRight(base, "/")
}

// region api-call

// APICall sends POST {base}/api/{method} with body as JSON. With auth, it
// also sends the session cookie. It returns the reply as raw JSON: decode it
// into the struct that you expect. The reply can have failed: true; APICall
// does not check that, because each method has its own failures.
func APICall(ctx context.Context, method string, body any, auth *Auth) (json.RawMessage, error) {
	if body == nil {
		body = map[string]any{} // the server expects an object, also an empty one
	}
	buf, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, "POST", BaseURL()+"/api/"+method, bytes.NewReader(buf))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if auth != nil {
		req.Header.Set("Cookie", "auth="+auth.User+"-"+auth.Auth) // the session cookie
	}
	res, err := client.Do(req)
	if err != nil {
		return nil, err // no connection, DNS failure, timeout, ...
	}
	defer res.Body.Close() // always close the body, or the connection leaks
	if res.StatusCode != http.StatusOK {
		// The API itself always answers 200. Another status is a proxy or a server problem.
		return nil, fmt.Errorf("%s: HTTP %d", method, res.StatusCode)
	}
	return io.ReadAll(res.Body)
}

// endregion api-call

// ParseAuth splits "<user>-<auth>" at the first "-". The user id has no "-".
func ParseAuth(text string) (Auth, error) {
	user, auth, ok := strings.Cut(text, "-")
	if !ok {
		return Auth{}, errors.New("AL_AUTH must look like <user>-<auth>")
	}
	return Auth{user, auth}, nil
}

// region login

// Login returns the session. If AL_AUTH is set, it uses that value and sends
// no password. Else it logs in with AL_EMAIL and AL_PASSWORD, and prints the
// AL_AUTH value to save. Each password login adds a token to the account
// (200 at most), so log in with the password one time only.
func Login(ctx context.Context) (Auth, error) {
	if saved := os.Getenv("AL_AUTH"); saved != "" {
		return ParseAuth(saved)
	}
	email, password := os.Getenv("AL_EMAIL"), os.Getenv("AL_PASSWORD")
	if email == "" || password == "" {
		return Auth{}, errors.New("set AL_AUTH, or AL_EMAIL and AL_PASSWORD")
	}
	// only_login: true, so that a wrong email never makes a new account.
	body := map[string]any{"email": email, "password": password, "only_login": true}
	raw, err := APICall(ctx, "signup_or_login", body, nil)
	if err != nil {
		return Auth{}, err
	}
	// Success: {success: true, user, auth, ...}. Failure: {failed: true, reason}.
	var reply struct {
		Success bool   `json:"success"`
		User    string `json:"user"`
		Auth    string `json:"auth"`
		Reason  string `json:"reason"`
	}
	if err := json.Unmarshal(raw, &reply); err != nil {
		return Auth{}, err
	}
	if !reply.Success {
		return Auth{}, fmt.Errorf("login failed: %s", reply.Reason)
	}
	value := reply.User + "-" + reply.Auth
	fmt.Println("Logged in with the password. Save this value, and use it from now on:")
	fmt.Printf("  export AL_AUTH='%s'\n", value)
	fmt.Printf("  PowerShell: $env:AL_AUTH = '%s'\n", value)
	return Auth{reply.User, reply.Auth}, nil
}

// endregion login

// region servers-and-characters

// ServersAndCharacters returns the game servers and the characters of the
// account. The server puts them in the `infs` list of the reply, in the item
// with type "servers_and_characters" (api.js:451-472).
func ServersAndCharacters(ctx context.Context, auth Auth) ([]Server, []Character, error) {
	raw, err := APICall(ctx, "servers_and_characters", nil, &auth)
	if err != nil {
		return nil, nil, err
	}
	var reply struct {
		Failed bool   `json:"failed"`
		Reason string `json:"reason"`
		Infs   []struct {
			Type       string      `json:"type"`
			Servers    []Server    `json:"servers"`
			Characters []Character `json:"characters"`
		} `json:"infs"`
	}
	if err := json.Unmarshal(raw, &reply); err != nil {
		return nil, nil, err
	}
	if reply.Reason == "not_logged_in" {
		return nil, nil, errors.New("the session in AL_AUTH is not valid any more: unset AL_AUTH and log in with the password again")
	}
	if reply.Failed {
		return nil, nil, fmt.Errorf("servers_and_characters failed: %s", reply.Reason)
	}
	for _, inf := range reply.Infs {
		if inf.Type == "servers_and_characters" {
			return inf.Servers, inf.Characters, nil
		}
	}
	return nil, nil, errors.New("servers_and_characters: the reply has no servers_and_characters item")
}

// endregion servers-and-characters

// region find-server

// FindServer returns the server whose region + name is key, for example
// "EUI". An empty key gives the first server of the list (the list is in
// the order EU, US, ASIA). Programs pass os.Getenv("AL_SERVER").
func FindServer(servers []Server, key string) (Server, error) {
	if len(servers) == 0 {
		return Server{}, errors.New("the server list is empty")
	}
	if key == "" {
		return servers[0], nil
	}
	var keys []string
	for _, s := range servers {
		if s.Region+s.Name == key {
			return s, nil
		}
		keys = append(keys, s.Region+s.Name)
	}
	return Server{}, fmt.Errorf("no server %s; the list has: %s", key, strings.Join(keys, ", "))
}

// endregion find-server

// FindCharacter returns the character with this exact name. Programs pass
// os.Getenv("AL_CHARACTER").
func FindCharacter(characters []Character, name string) (Character, error) {
	if name == "" {
		return Character{}, errors.New("set AL_CHARACTER to the name of a character (run the login program to see them)")
	}
	for _, c := range characters {
		if c.Name == name {
			return c, nil
		}
	}
	return Character{}, fmt.Errorf("no character named %q on this account", name)
}

// region socket-url

// SocketURL is the WebSocket URL of a game server. The scheme follows base:
// http gives ws, https gives wss. The two options at the end are the ones
// that the browser client sends (js/game.js:1525):
//   - map_protocol=1: we accept generated maps (without it, the server throws
//     "client_update_required", node/logic/generated_maps.js:186).
//   - no_graphics=1: send generated maps without tile data.
func SocketURL(server Server, base string) string {
	scheme := "wss"
	if u, err := url.Parse(base); err == nil && u.Scheme == "http" {
		scheme = "ws"
	}
	// The path must end with exactly one "/": the server matches "/ws1/".
	path := strings.TrimRight(server.Path, "/") + "/"
	return scheme + "://" + server.Address + path + "?EIO=4&transport=websocket&map_protocol=1&no_graphics=1"
}

// endregion socket-url
