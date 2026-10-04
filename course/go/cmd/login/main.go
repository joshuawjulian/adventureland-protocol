// cmd/login/main.go: log in over HTTP, then list the game servers and the
// characters of the account, with the values for AL_SERVER and AL_CHARACTER.
//
//	First run:  AL_EMAIL=you@example.com AL_PASSWORD=... go run ./cmd/login
//	Later runs: AL_AUTH=<user>-<auth> go run ./cmd/login   (the first run prints this value)
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"albot/api"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	// 30 s for both HTTP calls: much more than a working server needs.
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	auth, err := api.Login(ctx)
	if err != nil {
		return err
	}
	fmt.Println("user id:", auth.User)
	servers, characters, err := api.ServersAndCharacters(ctx, auth)
	if err != nil {
		return err
	}

	// The AL_SERVER value is region + name, for example "EUI".
	fmt.Println("servers (AL_SERVER, players, address, path):")
	for _, s := range servers {
		fmt.Printf("  %-8s %3d  %s  %s\n", s.Region+s.Name, s.Players, s.Address, s.Path)
	}
	fmt.Println("characters (AL_CHARACTER, class, level, id, status):")
	for _, c := range characters {
		status := "offline"
		if c.Server != "" { // the list has `server` only while the character is online
			status = "online on " + c.Server
		}
		fmt.Printf("  %-8s %-9s %3d  %s  %s\n", c.Name, c.Type, c.Level, c.ID, status)
	}
	return nil
}
