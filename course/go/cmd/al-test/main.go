// cmd/al-test/main.go: send AlSocket through the login handshake of the
// local test server. It uses only the alsocket package of the library.
//
//	Run: go run ./cmd/al-test
//	(AL_WS_URL: the game server; default ws://localhost:8022/ws1/?EIO=4&transport=websocket)
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"

	"albot/alsocket"
)

// Only the fields that this test reads. The real payloads have many more.
type Welcome struct {
	Region  string `json:"region"`
	Name    string `json:"name"`
	Version int    `json:"version"`
}
type Entities struct {
	Type     string            `json:"type"` // "all" for a full view
	Monsters []json.RawMessage `json:"monsters"`
}
type Start struct {
	ID  string  `json:"id"` // the character name (start has no `name`)
	Map string  `json:"map"`
	X   float64 `json:"x"`
	Y   float64 `json:"y"`
}
type PingAck struct {
	ID string `json:"id"`
}

// decode changes a raw payload into a T, or stops the program.
func decode[T any](raw json.RawMessage, err error) T {
	if err != nil {
		log.Fatal(err)
	}
	var v T
	if err := json.Unmarshal(raw, &v); err != nil {
		log.Fatal(err)
	}
	return v
}

func main() {
	url := os.Getenv("AL_WS_URL")
	if url == "" {
		url = "ws://localhost:8022/ws1/?EIO=4&transport=websocket" // EU I of the test server
	}
	// 30 s for the full test: enough for a local server. Each wait below
	// stops when this time ends.
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	sock, err := alsocket.Connect(ctx, url)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("connected to", url)

	// 1. The server sends "welcome" to each new socket. This is our first
	//    subscription, so AlSocket gives us the kept "welcome".
	welcome := decode[Welcome](sock.WaitFor(ctx, "welcome", nil))
	fmt.Printf("welcome: %s %s, version %d\n", welcome.Region, welcome.Name, welcome.Version)
	sock.On("game_error", func(data json.RawMessage) { fmt.Println("game_error:", string(data)) })
	sock.On("disconnect", func(data json.RawMessage) {
		var reason string // AlSocket's local event: the payload is a JSON string
		_ = json.Unmarshal(data, &reason)
		fmt.Println("disconnect:", reason)
	})

	// 2. Send "loaded". The reply is one full "entities" view (type "all").
	//    Expect registers the wait BEFORE the emit, so a fast reply can't pass first.
	waitView := sock.Expect("entities", func(raw json.RawMessage) bool {
		var e Entities
		return json.Unmarshal(raw, &e) == nil && e.Type == "all"
	})
	sock.Emit("loaded", map[string]any{"success": 1, "width": 1920, "height": 1080, "scale": 2})
	view := decode[Entities](waitView(ctx))
	fmt.Printf("entities: %d monster(s)\n", len(view.Monsters))

	// 3. Log in the test character. HARD-CODED: the fixed account of the
	//    test server (course/test-server/accounts.js). Part 1 has no login
	//    code yet; Part 2 reads these values from AL_AUTH and the HTTP API.
	waitStart := sock.Expect("start", nil)
	sock.Emit("auth", map[string]any{
		"user":       "US_tester",
		"auth":       "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
		"character":  "CH_tester", // the id, not the name
		"no_html":    "1",
		"passphrase": "",
	})
	me := decode[Start](waitStart(ctx))
	fmt.Printf("start: %s on %s at %.0f,%.0f\n", me.ID, me.Map, me.X, me.Y)

	// 4. Do nothing for 3 s. The server sends pings in this time. If our
	//    pong does not work, the server drops us and the next step fails.
	time.Sleep(3 * time.Second)
	waitAck := sock.Expect("ping_ack", func(raw json.RawMessage) bool {
		var a PingAck
		return json.Unmarshal(raw, &a) == nil && a.ID == "42"
	})
	sock.Emit("ping_trig", map[string]any{"id": "42"})
	ack := decode[PingAck](waitAck(ctx))
	fmt.Println("ping_ack after 3 s idle:", ack.ID)
	fmt.Println("OK")

	sock.Close()
	<-sock.Done() // wait until the "disconnect" handler has printed its line
}
