// cmd/first-kill/main.go: the checkpoint of Part 2. Enter the game, heal,
// walk to the nearest goo, attack it until it dies, open its chest, and
// print the xp. It fails after 90 s.
//
//	Run: AL_AUTH=<user>-<auth> AL_CHARACTER=<name> go run ./cmd/first-kill
//	(AL_SERVER is optional, for example EUI.)
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"time"

	"albot/actions"
	"albot/bot"
	"albot/world"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	// 90 s for the whole program: a goo dies in a few hits.
	deadline := time.Now().Add(90 * time.Second)
	ctx, cancel := context.WithDeadline(context.Background(), deadline)
	defer cancel()

	b, err := bot.Connect(ctx)
	if err != nil {
		return err
	}
	defer b.Close()
	w, act, cd := b.World, b.Act, b.Cooldowns

	me := w.CopyMe()
	fmt.Printf("in game as %s (%s, level %.0f) on %s at %.0f,%.0f\n",
		me.Str("id"), me.Str("ctype"), me.Num("level"), me.Str("map"), me.Num("x"), me.Num("y"))

	// The ids of the monsters that died: a `death` event, or a `hit` with
	// kill: true. The handlers run on the dispatch goroutine, so they only
	// put the id on a channel (64: room for many; a full channel drops ids).
	killed := make(chan string, 64)
	onKill := func(d json.RawMessage) {
		var e struct {
			ID   string `json:"id"`
			Kill bool   `json:"kill"`
		}
		if json.Unmarshal(d, &e) == nil {
			select {
			case killed <- e.ID:
			default:
			}
		}
	}
	w.Listen("death", onKill)
	w.Listen("hit", func(d json.RawMessage) {
		var e struct{ Kill bool }
		if json.Unmarshal(d, &e) == nil && e.Kill {
			onKill(d)
		}
	})

	target := "" // the id of our goo; "" until we choose one
	for {
		if time.Now().After(deadline) {
			return errors.New("no kill in 90 s")
		}
		time.Sleep(100 * time.Millisecond) // HARD-CODED: 10 checks per second are enough
		w.Advance()                        // positions now, not at the last update
		me = w.CopyMe()

		if me.Bool("rip") { // dead: wait the rip time, then respawn
			fmt.Printf("died; respawn in %.0f s\n", act.RespawnWait().Seconds())
			if _, err := act.Respawn(); err != nil {
				return err
			}
			me = w.CopyMe()
			fmt.Printf("respawned at %.0f,%.0f\n", me.Num("x"), me.Num("y"))
			continue
		}

		// Heal first, below 70 % hp (HARD-CODED: a goo hits for little).
		if me.Num("hp") < 0.7*me.Num("max_hp") && cd.Ready("potion") {
			healed, err := act.Heal("hp")
			if err != nil && !errors.Is(err, actions.ErrNoReply) {
				return err
			}
			if healed {
				me = w.CopyMe() // the `player` update came before the reply
				fmt.Printf("heal hp: %.0f/%.0f\n", me.Num("hp"), me.Num("max_hp"))
			}
		}

		if target == "" {
			goo := w.NearestMonster("goo")
			if goo == nil {
				continue // none in view yet
			}
			target = goo.Str("id")
			fmt.Printf("target: goo %s at %.0f,%.0f\n", target, goo.Num("x"), goo.Num("y"))
		}

		if isDead(killed, target) {
			break
		}
		goo, ok := w.CopyMonster(target)
		if !ok {
			target = "" // it left our view: choose again
			continue
		}
		if w.Distance(me, goo) > me.Num("range") {
			// Out of range: walk to a point range - 10 px from the goo, on
			// the line from the goo to us (10 px of margin, as it moves).
			x, y := toward(goo, me, me.Num("range")-10)
			if _, err := act.MoveTo(x, y); err != nil {
				return err
			}
		} else if cd.Ready("attack") {
			if _, err := act.Attack(target); err != nil && !errors.Is(err, actions.ErrNoReply) {
				return err
			}
		}
	}
	fmt.Println("killed goo", target)

	// The `drop` (the chest) comes with the kill. Wait up to 3 s for it.
	for i := 0; i < 30 && len(w.ChestIDs()) == 0; i++ {
		time.Sleep(100 * time.Millisecond)
	}
	for _, id := range w.ChestIDs() {
		c, err := act.OpenChest(id)
		if err != nil {
			return fmt.Errorf("chest %s: %w", id, err)
		}
		items, _ := c["items"].([]any) // no `items` key when the chest has none
		fmt.Printf("chest %s: +%.0f gold, %d item(s)\n", id, c.Num("gold"), len(items))
	}

	me = w.CopyMe()
	fmt.Printf("xp: %.0f/%.0f, level %.0f\n", me.Num("xp"), me.Num("max_xp"), me.Num("level"))
	fmt.Println("OK")
	return nil
}

// isDead reads all the ids on the channel, and reports whether target is one.
func isDead(killed chan string, target string) bool {
	dead := false
	for {
		select {
		case id := <-killed:
			dead = dead || id == target
		default:
			return dead
		}
	}
}

// toward returns the point at dist px from `from`, on the line to `to`.
func toward(from, to world.Entity, dist float64) (float64, float64) {
	dx, dy := to.Num("x")-from.Num("x"), to.Num("y")-from.Num("y")
	length := math.Hypot(dx, dy)
	if length == 0 {
		return from.Num("x"), from.Num("y")
	}
	return from.Num("x") + dx/length*dist, from.Num("y") + dy/length*dist
}
