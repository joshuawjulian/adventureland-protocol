// Package budget keeps our call-cost under the limit of the server. The
// server adds up a cost for each event that a socket sends in the last 4 s.
// Over 200, it sends disconnect_reason "limitdc" and drops the socket
// (node/server.js:242-258, 4892-4943).
//
// Concurrency: Emit runs on your goroutines, and the new_map handler runs on
// the dispatch goroutine of AlSocket. One sync.Mutex guards the list of
// costs; each method takes it. Emit never sleeps while it holds the lock.
package budget

import (
	"context"
	"encoding/json"
	"sync"
	"time"

	"albot/alsocket"
	"albot/world"
)

// region budget

// ExtraCost: each event costs 1, plus this extra (the CC table,
// node/server.js:242-255).
var ExtraCost = map[string]float64{
	"auth": 2, "move": 1.5, "players": 12, "secondhands": 16, "friend": 24, "send_updates": 12,
	"cruise": 10, "random_look": 10, "equip": 3, "unequip": 6, "tracker": 50, "ccreport": 3,
}

const (
	// Limit is 150 of the server's 200: some replies (a `player` resend)
	// add cost to our socket, and we cannot see that cost.
	Limit = 150
	// WindowMs is the window of the server: it counts the last 4 s.
	WindowMs = 4000
)

type spend struct {
	at   time.Time
	cost float64
}

// Budget is the record of what we spent in the last WindowMs.
type Budget struct {
	mu    sync.Mutex
	spent []spend         // oldest first
	ctx   context.Context // the session context (SetContext); nil = context.Background()
	sock  *alsocket.Socket
}

// SetContext sets the context of the session: when it ends, a wait in Emit
// for room in the budget ends at once with its error. Actions.SetContext
// calls it for you.
func (b *Budget) SetContext(ctx context.Context) {
	b.mu.Lock()
	b.ctx = ctx
	b.mu.Unlock()
}

// New makes the budget. A map change costs 8 more on the server
// (add_call_cost(player, 8, "transport")), so we count 8 on each new_map.
func New(sock *alsocket.Socket, w *world.World) *Budget {
	b := &Budget{sock: sock}
	w.Listen("new_map", func(json.RawMessage) { b.record(8) })
	return b
}

// Cost is the call-cost of one event.
func (b *Budget) Cost(event string) float64 { return 1 + ExtraCost[event] }

// record adds a cost now.
func (b *Budget) record(cost float64) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.spent = append(b.spent, spend{time.Now(), cost})
}

// spentLocked forgets the costs older than the window and adds up the rest.
// Call it with the lock held.
func (b *Budget) spentLocked() float64 {
	for len(b.spent) > 0 && time.Since(b.spent[0].at) > WindowMs*time.Millisecond {
		b.spent = b.spent[1:]
	}
	total := 0.0
	for _, s := range b.spent {
		total += s.cost
	}
	return total
}

// Spent is the total cost of the last 4 s.
func (b *Budget) Spent() float64 {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.spentLocked()
}

// Emit waits until the last 4 s have room for this event, records its
// cost, then sends it. If the session context ends during the wait, it
// returns that error and sends nothing.
func (b *Budget) Emit(event string, payload any) error {
	cost := b.Cost(event)
	for {
		b.mu.Lock()
		if b.spentLocked()+cost <= Limit || len(b.spent) == 0 {
			b.spent = append(b.spent, spend{time.Now(), cost})
			b.mu.Unlock()
			return b.sock.Emit(event, payload)
		}
		// Wait until the oldest cost leaves the window (+10 ms of margin).
		wait := WindowMs*time.Millisecond - time.Since(b.spent[0].at) + 10*time.Millisecond
		ctx := b.ctx
		b.mu.Unlock() // never wait with the lock: the new_map handler needs it
		if ctx == nil {
			ctx = context.Background()
		}
		timer := time.NewTimer(wait)
		select {
		case <-timer.C:
		case <-ctx.Done(): // Ctrl-C or the end of the group: do not wait up to 4 s
			timer.Stop()
			return ctx.Err()
		}
	}
}

// endregion budget
