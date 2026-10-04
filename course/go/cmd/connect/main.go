// cmd/connect/main.go: log in, connect to a game server, do the handshake,
// and print where our character is. Then close.
//
//	Run: AL_AUTH=<user>-<auth> AL_CHARACTER=<name> go run ./cmd/connect
//	(AL_SERVER is optional, for example EUI; empty = the first server of the list.)
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"albot/bot"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	// 60 s: the HTTP calls, a download of G (the first time) and the handshake.
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	b, err := bot.Connect(ctx)
	if err != nil {
		return err
	}
	defer b.Close() // the server then saves the character and marks it offline

	fmt.Printf("welcome: %s %s, version %d\n", b.Welcome.Region, b.Welcome.Name, b.Welcome.Version)
	me := b.World.CopyMe()
	// `start` has no `name`: `id` is the name. `ctype` is the class.
	fmt.Printf("in game as %s (%s, level %.0f) on %s at %.0f,%.0f\n",
		me.Str("id"), me.Str("ctype"), me.Num("level"), me.Str("map"), me.Num("x"), me.Num("y"))
	fmt.Println("OK")
	return nil
}
