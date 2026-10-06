// Package world keeps our copy of the game world: our character (Me), the
// monsters and players that we can see, and the chests that we can open.
// It updates the copy from the events of the server.
//
// Concurrency: AlSocket calls the handlers on its dispatch goroutine, and
// your program reads the world on its own goroutine. One lock (the embedded
// sync.Mutex) guards all fields. The handlers run with the lock held. The
// methods of World take the lock themselves. If you read the fields
// directly, lock first:
//
//	w.Lock()
//	hp := w.Me.Num("hp")
//	w.Unlock()
package world

import (
	"encoding/json"
	"maps"
	"math"
	"strconv"
	"sync"
	"time"

	"albot/alsocket"
	"albot/gdata"
)

// Entity is one object of the server (our character, a monster, a player or
// an NPC) as the server sends it: a JSON object. We keep it as a map, so
// that a `player` update can merge field by field. json.Unmarshal gives
// numbers as float64, strings as string, true/false as bool.
type Entity map[string]any

// Num reads a number. A missing field (or one that is not a number) is 0.
func (e Entity) Num(key string) float64 {
	if v, ok := e[key].(float64); ok {
		return v
	}
	return 0
}

// Str reads a string. A number becomes its text (some ids are numbers).
// A missing field is "".
func (e Entity) Str(key string) string {
	switch v := e[key].(type) {
	case string:
		return v
	case float64:
		return strconv.FormatFloat(v, 'f', -1, 64)
	}
	return ""
}

// Bool reads a field the way JavaScript tests it: false, 0, "" and a missing
// field are false. Thus `rip` (true, or the name of a gravestone) works.
func (e Entity) Bool(key string) bool {
	switch v := e[key].(type) {
	case nil:
		return false
	case bool:
		return v
	case float64:
		return v != 0
	case string:
		return v != ""
	}
	return true // an object or a list
}

// Clone returns a copy that you can keep after you unlock. The handlers
// never change a nested value in place (they replace the field), so a copy
// of the top level is enough.
func (e Entity) Clone() Entity { return maps.Clone(e) }

// decode turns a payload into an Entity. It returns nil if the payload is
// not a JSON object.
func decode(data json.RawMessage) Entity {
	var e Entity
	if json.Unmarshal(data, &e) != nil {
		return nil
	}
	return e
}

// list reads a field that holds a list of objects, such as "monsters".
func list(e Entity, key string) []Entity {
	raw, _ := e[key].([]any)
	out := make([]Entity, 0, len(raw))
	for _, v := range raw {
		if m, ok := v.(map[string]any); ok {
			out = append(out, Entity(m))
		}
	}
	return out
}

// World is our copy of the world. Create it with New, before you send
// `loaded` and `auth`, so that it sees the `start` event.
type World struct {
	sync.Mutex // guards all the fields below

	G        *gdata.GData
	Me       Entity            // the `start` payload (without entities) + each `player`
	Monsters map[string]Entity // id -> monster
	Players  map[string]Entity // id -> other player or NPC (never us)
	Chests   map[string]Entity // chest id -> the `drop` payload

	sock     *alsocket.Socket
	handlers map[string][]func(json.RawMessage)
	stamp    map[string]time.Time // entity id -> when its position was last correct
}

// region constructor

// New makes the world and registers its handlers on sock.
func New(sock *alsocket.Socket, G *gdata.GData) *World {
	w := &World{
		G:        G,
		Me:       Entity{},
		Monsters: map[string]Entity{},
		Players:  map[string]Entity{},
		Chests:   map[string]Entity{},
		sock:     sock,
		handlers: map[string][]func(json.RawMessage){},
		stamp:    map[string]time.Time{},
	}
	w.Listen("start", w.onStart)
	w.Listen("player", w.onPlayer)
	w.Listen("entities", func(d json.RawMessage) {
		if e := decode(d); e != nil {
			w.applyEntities(e)
		}
	})
	// A monster died, or an entity left our view: forget it.
	gone := func(d json.RawMessage) {
		if e := decode(d); e != nil {
			w.forget(e.Str("id"))
		}
	}
	w.Listen("death", gone)
	w.Listen("disappear", gone)
	w.Listen("new_map", w.onNewMap)
	w.Listen("drop", func(d json.RawMessage) { // a chest for us
		if e := decode(d); e != nil {
			w.Chests[e.Str("id")] = e
		}
	})
	w.Listen("chest_opened", func(d json.RawMessage) {
		if e := decode(d); e != nil {
			delete(w.Chests, e.Str("id"))
		}
	})
	// The server disagrees with our position and sends its own x, y.
	w.Listen("correction", func(d json.RawMessage) {
		maps.Copy(w.Me, decode(d))
		w.stamp[w.Me.Str("id")] = time.Now()
	})
	return w
}

// endregion constructor

// region listen

// Listen adds a handler for an event. One table maps each event name to our
// handlers, so that Dispatch can also give them the events that ride along
// in a `player` update (hitchhikers). The first Listen for a name also
// subscribes to that name on the socket.
//
// Handlers run with the world lock held: they can read and change the
// fields, but they must not call a World method that locks (or Listen).
func (w *World) Listen(name string, handler func(json.RawMessage)) {
	w.Lock()
	first := len(w.handlers[name]) == 0
	w.handlers[name] = append(w.handlers[name], handler)
	w.Unlock()
	if first {
		// After the unlock: sock.On takes the lock of the socket, and the
		// dispatch goroutine can call Dispatch (which takes our lock) at any
		// time from now on, also for a kept event.
		w.sock.On(name, func(d json.RawMessage) { w.Dispatch(name, d) })
	}
}

// Dispatch calls the handlers of name with data.
func (w *World) Dispatch(name string, data json.RawMessage) {
	w.Lock()
	defer w.Unlock()
	w.dispatchLocked(name, data)
}

func (w *World) dispatchLocked(name string, data json.RawMessage) {
	for _, h := range w.handlers[name] {
		h(data)
	}
}

// endregion listen

// region on-start

// onStart: `start` is our full character, plus the first view of the world
// in `entities`. Note: `start` has no `name`; `id` is the name.
func (w *World) onStart(d json.RawMessage) {
	start := decode(d)
	if start == nil {
		return
	}
	entities, _ := start["entities"].(map[string]any)
	delete(start, "entities") // the entities go to Monsters and Players
	w.Me = start
	w.stamp[w.Me.Str("id")] = time.Now()
	if entities != nil {
		w.applyEntities(Entity(entities))
	}
}

// endregion on-start

// region on-player

// onPlayer: a `player` update has the fields of our character that the
// server sends again. Merge them field by field. Then give each hitchhiker
// (an [event, payload] pair that rides along) to its handlers, as if it
// arrived alone.
func (w *World) onPlayer(d json.RawMessage) {
	var update map[string]json.RawMessage
	if json.Unmarshal(d, &update) != nil {
		return
	}
	hitchhikers := update["hitchhikers"]
	delete(update, "hitchhikers")
	for k, v := range update {
		var value any
		if json.Unmarshal(v, &value) == nil {
			w.Me[k] = value
		}
	}
	w.stamp[w.Me.Str("id")] = time.Now()

	var pairs [][]json.RawMessage
	if json.Unmarshal(hitchhikers, &pairs) == nil {
		for _, pair := range pairs {
			var event string
			if len(pair) == 2 && json.Unmarshal(pair[0], &event) == nil {
				w.dispatchLocked(event, pair[1]) // the lock is already held
			}
		}
	}
}

// endregion on-player

// region apply-entities

// applyEntities puts the monsters and players of an `entities` payload into
// the world. Each object is the complete state of that entity: replace it,
// do not merge.
func (w *World) applyEntities(data Entity) {
	if data.Str("in") != w.Me.Str("in") {
		return // an old update for an instance (or map) that we left
	}
	if data.Str("type") == "all" { // a full view: forget everything first
		for id := range w.Monsters {
			w.forget(id)
		}
		for id := range w.Players {
			w.forget(id)
		}
	}
	now := time.Now()
	for _, m := range list(data, "monsters") {
		w.withDefaults(m)
		w.Monsters[m.Str("id")] = m
		w.stamp[m.Str("id")] = now
	}
	for _, p := range list(data, "players") {
		if p.Str("id") == w.Me.Str("id") {
			continue // a full view also has our own character
		}
		w.Players[p.Str("id")] = p
		w.stamp[p.Str("id")] = now
	}
}

// withDefaults: the server sends only the fields of a monster that are
// different from G.monsters[type] (node/server.js:1003-1071). Fill in the
// others from G. max_hp is G's hp.
func (w *World) withDefaults(m Entity) {
	def, ok := w.G.Monsters[m.Str("type")]
	if !ok {
		return
	}
	for key, value := range map[string]float64{
		"hp": def.HP, "max_hp": def.HP, "speed": def.Speed, "attack": def.Attack,
		"range": def.Range, "frequency": def.Frequency, "xp": def.XP,
	} {
		if _, has := m[key]; !has {
			m[key] = value
		}
	}
}

// forget removes an entity from the world.
func (w *World) forget(id string) {
	delete(w.Monsters, id)
	delete(w.Players, id)
	delete(w.stamp, id)
}

// endregion apply-entities

// region on-new-map

// onNewMap: we changed map (a door, the transporter, a respawn, the jail).
// The payload has the new place and a full view of it.
func (w *World) onNewMap(d json.RawMessage) {
	nm := decode(d)
	if nm == nil {
		return
	}
	for _, key := range []string{"in", "x", "y", "m"} {
		w.Me[key] = nm[key]
	}
	w.Me["map"] = nm["name"] // the map is `name` here
	w.Me["moving"] = false
	w.Me["going_x"], w.Me["going_y"] = nm["x"], nm["y"]
	w.stamp[w.Me.Str("id")] = time.Now()
	if entities, ok := nm["entities"].(map[string]any); ok {
		w.applyEntities(Entity(entities)) // always type "all"
	}
}

// endregion on-new-map

// region step

// Step moves one entity that is moving toward going_x, going_y. speed is in
// px per second, so in ms milliseconds it moves speed * ms / 1000 px. The
// server moves entities in a straight line the same way.
func Step(e Entity, ms float64) {
	if !e.Bool("moving") {
		return
	}
	x, y := e.Num("x"), e.Num("y")
	dx, dy := e.Num("going_x")-x, e.Num("going_y")-y
	left := math.Hypot(dx, dy) // the distance that is still to go
	travel := e.Num("speed") * ms / 1000
	if travel >= left { // it arrived
		e["x"], e["y"], e["moving"] = e["going_x"], e["going_y"], false
		return
	}
	e["x"], e["y"] = x+dx/left*travel, y+dy/left*travel
}

// endregion step

// region advance

// Advance moves Me, the monsters and the players forward to now. Each one
// moves for the time since its last update (or the last Advance). There is
// no timer in the background: call Advance before you read positions.
func (w *World) Advance() {
	w.Lock()
	defer w.Unlock()
	now := time.Now()
	move := func(e Entity) {
		id := e.Str("id")
		if last, ok := w.stamp[id]; ok {
			Step(e, float64(now.Sub(last).Milliseconds()))
		}
		w.stamp[id] = now
	}
	move(w.Me)
	for _, m := range w.Monsters {
		move(m)
	}
	for _, p := range w.Players {
		move(p)
	}
}

// endregion advance

// region distance

// size is the hit box (width, height) of an entity, as the server measures
// range. A monster: G.dimensions[type] (24 x 24 if G has no entry), times
// G.monsters[type].size (get_monster_dimensions, js/old_common_functions.js:692-700).
// A character or an NPC: 26 x 36 (node/server.js:11782-11783).
func (w *World) size(e Entity) (float64, float64) {
	def, ok := w.G.Monsters[e.Str("type")]
	if !ok {
		return 26, 36
	}
	width, height := 24.0, 24.0
	if d := w.G.Dimensions[e.Str("type")]; len(d) >= 2 {
		width, height = d[0], d[1]
	}
	if def.Size != 0 {
		width, height = math.Round(width*def.Size), math.Round(height*def.Size)
	}
	return width, height
}

// Distance is the gap between the hit boxes of a and b, the way the server
// measures range (distance, js/old_common_functions.js:707-740). x is the
// center of the box and y its bottom (the feet). 0 means that the boxes touch.
func (w *World) Distance(a, b Entity) float64 {
	for _, key := range []string{"in", "map"} {
		_, inA := a[key]
		_, inB := b[key]
		if inA && inB && a.Str(key) != b.Str(key) {
			return 99999999 // the source's value for "not in the same place"
		}
	}
	aw, ah := w.size(a)
	bw, bh := w.size(b)
	ax, ay, bx, by := a.Num("x"), a.Num("y"), b.Num("x"), b.Num("y")
	dx := math.Max(math.Max(bx-bw/2-(ax+aw/2), ax-aw/2-(bx+bw/2)), 0)
	dy := math.Max(math.Max(by-bh-ay, ay-ah-by), 0)
	return math.Hypot(dx, dy)
}

// endregion distance

// NearestMonster returns a copy of the monster closest to Me (of type mtype,
// if it is not ""), or nil if there is none.
func (w *World) NearestMonster(mtype string) Entity {
	w.Lock()
	defer w.Unlock()
	var best Entity
	bestDist := math.Inf(1)
	for _, m := range w.Monsters {
		if mtype != "" && m.Str("type") != mtype {
			continue
		}
		if d := w.Distance(w.Me, m); d < bestDist {
			best, bestDist = m, d
		}
	}
	return best.Clone()
}

// CopyMe returns a copy of Me that you can read without the lock.
func (w *World) CopyMe() Entity {
	w.Lock()
	defer w.Unlock()
	return w.Me.Clone()
}

// CopyMonster returns a copy of one monster, or false if it is not (or no
// longer) in view.
func (w *World) CopyMonster(id string) (Entity, bool) {
	w.Lock()
	defer w.Unlock()
	m, ok := w.Monsters[id]
	return m.Clone(), ok
}

// ChestIDs returns the ids of the chests that we know now.
func (w *World) ChestIDs() []string {
	w.Lock()
	defer w.Unlock()
	ids := make([]string, 0, len(w.Chests))
	for id := range w.Chests {
		ids = append(ids, id)
	}
	return ids
}
