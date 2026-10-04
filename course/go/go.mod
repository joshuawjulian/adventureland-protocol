// The Go project of the course: the albot library (one package per module)
// and the programs in cmd/<name>. Build and run from this folder:
//   go run ./cmd/al-test
module albot

// Go 1.22: coder/websocket v1.8.14 and later need Go 1.23.
go 1.22

// The only package outside the standard library: a plain WebSocket client.
require github.com/coder/websocket v1.8.13
