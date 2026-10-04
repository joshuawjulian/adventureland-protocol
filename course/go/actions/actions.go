// Package actions sends the events that act in the world (move, attack,
// heal, open chests, respawn) and reads the replies. Every event goes
// through the call-cost budget. A method that waits for a reply registers
// the wait before it sends the event, so that a fast reply cannot pass first.
//
// Concurrency: the methods block the goroutine that calls them (a wait for
// a reply, a walk). Call them from your program's goroutine, never from a
// socket handler: the handlers run on the dispatch goroutine, and the reply
// that you wait for comes through that same goroutine.
package actions

import (
	"context"
	"encoding/json"
	"errors"
	"math"
	"sync"
	"time"

	"albot/alsocket"
	"albot/budget"
	"albot/cooldowns"
	"albot/world"
)

// ErrNoReply means that no reply came in time (JS: null).
var ErrNoReply = errors.New("no reply in time")

// region normalize

// GameResponse is a game_response in one shape. The server sends either a
// bare string (the code) or an object {response, place, failed, ...}.
type GameResponse struct {
	Response string       // the code: "data", "cooldown", "too_far", ...
	Place    string       // the event (or skill) that it answers; "" for a bare string
	Failed   bool         // true for a failure
	Success  bool         // true for some successes (a successful attack has no success key)
	MS       float64      // "cooldown", "not_ready", "cant_respawn": the ms that are left
	Data     world.Entity // the whole object; nil for a bare string
}

// Normalize turns either shape of game_response into a GameResponse.
// A bare string is the code alone, with failed and success false.
func Normalize(data json.RawMessage) GameResponse {
	var code string
	if json.Unmarshal(data, &code) == nil {
		return GameResponse{Response: code}
	}
	var e world.Entity
	_ = json.Unmarshal(data, &e)
	return GameResponse{
		Response: e.Str("response"),
		Place:    e.Str("place"),
		Failed:   e.Bool("failed"),
		Success:  e.Bool("success"),
		MS:       e.Num("ms"),
		Data:     e,
	}
}

// ResponseFor is a predicate for Expect: a game_response object with this
// place. A bare string has no place, so it never matches.
func ResponseFor(place string) func(json.RawMessage) bool {
	return func(data json.RawMessage) bool {
		var r struct {
			Place string `json:"place"`
		}
		return json.Unmarshal(data, &r) == nil && r.Place == place
	}
}

// endregion normalize

// region request

// Request sends event and waits for the game_response whose place is place.
// It returns ErrNoReply after timeout.
func (a *Actions) Request(event string, payload any, place string, timeout time.Duration) (GameResponse, error) {
	wait := a.sock.Expect("game_response", ResponseFor(place)) // 1. register the wait
	if err := a.budget.Emit(event, payload); err != nil {      // 2. send
		return GameResponse{}, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	data, err := wait(ctx) // 3. block until the reply, the timeout or the end of the socket
	if errors.Is(err, context.DeadlineExceeded) {
		return GameResponse{}, ErrNoReply
	}
	if err != nil {
		return GameResponse{}, err
	}
	return Normalize(data), nil
}

// endregion request

// Actions acts for one character.
type Actions struct {
	sock      *alsocket.Socket
	world     *world.World
	cooldowns *cooldowns.Cooldowns
	budget    *budget.Budget

	mu     sync.Mutex // guards diedAt
	diedAt time.Time  // when we last died; zero if not known
}

// New makes the actions of one character.
func New(sock *alsocket.Socket, w *world.World, cd *cooldowns.Cooldowns, b *budget.Budget) *Actions {
	a := &Actions{sock: sock, world: w, cooldowns: cd, budget: b}
	// Note the time of death: respawn must wait 12 s after it.
	w.Listen("game_response", func(d json.RawMessage) {
		if Normalize(d).Response == "defeated_by_a_monster" {
			a.mu.Lock()
			a.diedAt = time.Now()
			a.mu.Unlock()
		}
	})
	return a
}

// region move-to

// Move starts a straight walk to (x, y) and does not wait. The server walks
// us in the same straight line; a line through a wall sends us to jail.
func (a *Actions) Move(x, y float64) error {
	a.world.Advance() // our position now, not at the last update
	a.world.Lock()
	me := a.world.Me
	payload := map[string]any{
		"x": me.Num("x"), "y": me.Num("y"), // where we think we are
		"going_x": x, "going_y": y,
		// m must equal the map counter of the server, or the server ignores
		// the move with no reply.
		"m": me.Num("m"),
	}
	me["going_x"], me["going_y"], me["moving"] = x, y, true // the server does the same
	a.world.Unlock()
	return a.budget.Emit("move", payload)
}

// MoveTo walks in a straight line to (x, y) and waits until we should be
// there: the distance / our speed, plus 250 ms for the network. It reports
// whether we arrived. Use it only when the line is clear of walls.
func (a *Actions) MoveTo(x, y float64) (bool, error) {
	if err := a.Move(x, y); err != nil {
		return false, err
	}
	me := a.world.CopyMe()
	speed := math.Max(me.Num("speed"), 1) // px per second; 1 if not known
	seconds := math.Hypot(x-me.Num("x"), y-me.Num("y")) / speed
	time.Sleep(time.Duration(seconds*float64(time.Second)) + 250*time.Millisecond)
	a.world.Advance()
	me = a.world.CopyMe()
	// Arrived: within 1 px, and still on the way to (x, y). A `correction`
	// or a jail sends us somewhere else: then the walk failed.
	arrived := math.Hypot(me.Num("x")-x, me.Num("y")-y) < 1 &&
		me.Num("going_x") == x && me.Num("going_y") == y
	return arrived, nil
}

// endregion move-to

// region attack

// Attack attacks a monster or a player by id. A success is response "data"
// with place "attack" and the projectile data (pid, eta). A target that is
// gone gets a `disappear` event instead of a game_response: then Attack
// returns ErrNoReply.
func (a *Actions) Attack(id string) (GameResponse, error) {
	// 2 s: a reply takes one round trip; more means it does not come.
	return a.Request("attack", map[string]any{"id": id}, "attack", 2*time.Second)
}

// endregion attack

// region heal

// Heal adds hp or mp (stat is "hp" or "mp"). It drinks a potion that gives
// stat if the inventory has one (`equip` with consume: true). Else it uses
// the free regeneration (`use`). All potions and the regeneration share one
// timer, "potion": when it is not ready, Heal does nothing and returns false.
func (a *Actions) Heal(stat string) (bool, error) {
	if !a.cooldowns.Ready("potion") {
		return false, nil
	}
	num := a.findPotion(stat)
	event, payload := "use", map[string]any{"item": stat}
	if num >= 0 {
		event, payload = "equip", map[string]any{"num": num, "consume": true}
	}
	r, err := a.Request(event, payload, event, 2*time.Second)
	if err != nil {
		return false, err
	}
	return !r.Failed, nil
}

// findPotion returns the inventory slot of a potion that gives stat, or -1.
// G.items[name].gives is a list of [stat, amount] pairs.
func (a *Actions) findPotion(stat string) int {
	a.world.Lock()
	defer a.world.Unlock()
	items, _ := a.world.Me["items"].([]any) // nil is an empty slot
	for num, v := range items {
		item, ok := v.(map[string]any)
		if !ok {
			continue
		}
		name, _ := item["name"].(string)
		for _, give := range a.world.G.Items[name].Gives {
			if give[0] == stat {
				return num
			}
		}
	}
	return -1
}

// endregion heal

// region open-chests

// OpenChest opens one chest and returns the `chest_opened` payload: {id,
// gold, items, ...}, or {id, gone: true} if the chest is not there any more.
// It returns ErrNoReply if no reply comes (for example, loot_no_space comes
// as a game_response instead).
func (a *Actions) OpenChest(id string) (world.Entity, error) {
	wait := a.sock.Expect("chest_opened", func(d json.RawMessage) bool {
		var c struct {
			ID string `json:"id"`
		}
		return json.Unmarshal(d, &c) == nil && c.ID == id
	})
	if err := a.budget.Emit("open_chest", map[string]any{"id": id}); err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	data, err := wait(ctx)
	if errors.Is(err, context.DeadlineExceeded) {
		return nil, ErrNoReply
	}
	if err != nil {
		return nil, err
	}
	var opened world.Entity
	err = json.Unmarshal(data, &opened)
	return opened, err
}

// OpenChests opens each chest that we know, and returns how many opened.
func (a *Actions) OpenChests() (int, error) {
	opened := 0
	for _, id := range a.world.ChestIDs() {
		c, err := a.OpenChest(id)
		// Forget the chest also when no reply came (a full bag:
		// "loot_no_space"; the chest stays on the server,
		// node/server.js:11315), so that we do not try it forever.
		a.world.Lock()
		delete(a.world.Chests, id)
		a.world.Unlock()
		if errors.Is(err, ErrNoReply) {
			continue
		}
		if err != nil {
			return opened, err
		}
		if !c.Bool("gone") {
			opened++
		}
	}
	return opened, nil
}

// endregion open-chests

// region respawn

// RipTime is the wait between death and respawn (B.rip_time,
// node/server.js:224).
const RipTime = 12 * time.Second

// RespawnWait is the rest of RipTime since our death (0 if not known).
func (a *Actions) RespawnWait() time.Duration {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.diedAt.IsZero() {
		return 0
	}
	return max(0, RipTime-time.Since(a.diedAt))
}

// Respawn waits the rest of RipTime, then sends `respawn`. If the server
// replies cant_respawn (too early), it waits the ms of the reply and tries
// one more time. Success: a `new_map` and a `player` with rip: false come
// first, then the game_response.
func (a *Actions) Respawn() (bool, error) {
	time.Sleep(a.RespawnWait())
	for try := 0; try < 2; try++ {
		r, err := a.Request("respawn", map[string]any{}, "respawn", 3*time.Second)
		if err != nil {
			return false, err
		}
		if r.Response != "cant_respawn" {
			return !r.Failed, nil
		}
		time.Sleep(time.Duration(r.MS * float64(time.Millisecond)))
	}
	return false, nil
}

// endregion respawn
