// cmd/echo/main.go: open a WebSocket, send one text message, read the reply.
// It needs only github.com/coder/websocket (no albot package).
//
//	Run: go run ./cmd/echo    (AL_ECHO_URL: the echo server; default ws://localhost:8022/echo)
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/coder/websocket"
)

func main() {
	url := os.Getenv("AL_ECHO_URL")
	if url == "" {
		url = "ws://localhost:8022/echo" // the echo endpoint of the course test server
	}
	// Each network call takes a context. This context stops the calls after 10 s.
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	conn, _, err := websocket.Dial(ctx, url, nil)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("connected")
	if err := conn.Write(ctx, websocket.MessageText, []byte("hello")); err != nil { // one text frame
		log.Fatal(err)
	}
	_, reply, err := conn.Read(ctx) // blocks this goroutine until a message arrives
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("received:", string(reply))
	conn.Close(websocket.StatusNormalClosure, "") // 1000 = normal closure
	fmt.Println("closed")
}
