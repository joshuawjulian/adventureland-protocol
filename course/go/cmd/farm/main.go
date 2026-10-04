// cmd/farm/main.go: a farming bot. It kills monsters of the Mainland ladder,
// loots, heals, respawns, leaves jail, and reconnects with the course's
// reconnect rule.
//
//	Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger go run ./cmd/farm [seconds]
//	seconds: stop after this time (the tests use 25). Without it: until Ctrl-C.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"strconv"
	"sync"
	"syscall"
	"time"

	"albot/bot"
	"albot/farmer"
	"albot/travel"
	"albot/world"
)

// tick: one decision every 100 ms: fast enough, and cheap in call-cost.
const tick = 100 * time.Millisecond

// stable: after a session of 5 min, the reconnect wait starts again at the
// first value.
const stable = 5 * time.Minute

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	// region stop
	// Ctrl-C (SIGINT) or `docker stop` (SIGTERM) cancels ctx: the loop ends
	// after this tick, closes the socket and prints the summary. A second
	// Ctrl-C stops at once (NotifyContext gives the signal back to Go).
	// (No defer cancel: that would look like a Ctrl-C at the normal end.)
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	go func() {
		<-ctx.Done()
		fmt.Println("stopping (press Ctrl-C again to stop at once)")
		cancel() // also restores the default: the next Ctrl-C ends the program
	}()
	// wait sleeps d, or less when we stop.
	wait := func(d time.Duration) {
		select {
		case <-ctx.Done():
		case <-time.After(d):
		}
	}
	// endregion stop

	seconds, _ := strconv.Atoi(firstArg())
	started := time.Now()
	endAt := time.Now().Add(100 * 365 * 24 * time.Hour) // "forever"
	if seconds > 0 {
		endAt = started.Add(time.Duration(seconds) * time.Second)
	}
	running := func() bool { return ctx.Err() == nil && time.Now().Before(endAt) }
	kills := 0
	attempt := 0 // failed tries in a row, for ReconnectDelayMs
	var last world.Entity

	// region session
	for running() {
		// 1. Connect. A failure (the server is full, the save of the last
		//    session still runs, ...) waits as the reconnect rule says, then
		//    tries again. The connect itself does not use ctx: Ctrl-C during
		//    the 30 s handshake waits for it.
		b, err := bot.Connect(context.Background())
		if err != nil {
			ms := bot.ReconnectDelayMs(attempt)
			attempt++
			fmt.Printf("connect failed: %v; try again in %d s\n", err, ms/1000)
			wait(time.Duration(ms) * time.Millisecond)
			continue
		}
		session := time.Now()
		me := b.World.CopyMe()
		last = me
		fmt.Printf("in game as %s (%s, level %.0f) on %s at %.0f,%.0f\n",
			me.Str("id"), me.Str("ctype"), me.Num("level"), me.Str("map"), me.Num("x"), me.Num("y"))

		// 2. Play until we stop, the time is over, or the socket closes.
		//    AlSocket's local `disconnect` event has the reason; a send on a
		//    closed socket returns an error, which is the same case.
		var mu sync.Mutex
		lost := ""
		setLost := func(why string) {
			mu.Lock()
			if lost == "" {
				lost = why
			}
			mu.Unlock()
		}
		isLost := func() string { mu.Lock(); defer mu.Unlock(); return lost }
		b.World.Listen("disconnect", func(d json.RawMessage) {
			var why string
			if json.Unmarshal(d, &why) != nil {
				why = string(d)
			}
			setLost(why)
		})
		b.World.Listen("disconnect_reason", func(d json.RawMessage) { // "limitdc", "limits", ...
			fmt.Printf("the server says: %s\n", string(d))
		})
		f := farmer.New(b.World, b.Act, b.Cooldowns, travel.New(b.World, b.Act), "")
		for running() && isLost() == "" {
			time.Sleep(tick)
			if err := f.Tick(); err != nil {
				setLost(err.Error())
				break
			}
			f.NextType() // a stronger monster when this one is too easy
		}
		kills += f.Kills()
		last = b.World.CopyMe()
		why := isLost() // before Close: Close sends our own `disconnect`
		b.Close()
		if why == "" {
			break // we stopped, or the time is over
		}

		// 3. The reconnect rule: wait, then make a new socket and a full handshake.
		if time.Since(session) >= stable {
			attempt = 0
		}
		ms := bot.ReconnectDelayMs(attempt)
		attempt++
		fmt.Printf("disconnected: %s; reconnect in %d s\n", why, ms/1000)
		wait(time.Duration(ms) * time.Millisecond)
	}
	// endregion session

	fmt.Printf("farmed %.0f s: %d kill(s), level %.0f, %.0f gold\n",
		time.Since(started).Seconds(), kills, last.Num("level"), last.Num("gold"))
	fmt.Println("OK")
	return nil
}

// firstArg is the first command-line argument, or "".
func firstArg() string {
	if len(os.Args) > 1 {
		return os.Args[1]
	}
	return ""
}
