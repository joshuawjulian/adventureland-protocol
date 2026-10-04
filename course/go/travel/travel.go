// Package travel walks around walls, goes through doors, uses the
// transporter, and gets out of jail. It uses the grid of the pathfind
// package for the walls, and Actions.MoveTo for each straight part of the
// walk.
//
// Concurrency: the methods block the goroutine that calls them (a walk can
// take many seconds). Call them from your program's goroutine, never from a
// socket handler. They read our character with World.CopyMe, so they never
// hold the world lock while they send.
package travel

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"sort"
	"time"

	"albot/actions"
	"albot/gdata"
	"albot/pathfind"
	"albot/world"
)

// The distances of the server (node/server.js:221-223): a door works within
// 112 px of its box, the transporter NPC within 160 px of the NPC.
const (
	doorDist        = 112.0
	transporterDist = 160.0
)

// newMapWait: how long to wait for `new_map` after a transport. Live sends it
// at once for a door; for the bank it comes after the account loads
// (in_progress).
const newMapWait = 5 * time.Second

// Hop is one step on a route between maps: stand at (X, Y) on Map, then
// transport to spawn Spawn of To. By is "door" or "transporter".
type Hop struct {
	Map   string
	X, Y  float64
	To    string
	Spawn int
	By    string
}

// MapDef is the part of G.maps[name] that the course reads.
type MapDef struct {
	Doors  [][]any     `json:"doors"`  // [x, y, w, h, to map, to spawn, own spawn, lock?]
	Spawns [][]float64 `json:"spawns"` // [x, y, direction?, scatter?]
	NPCs   []struct {
		ID        string      `json:"id"`
		Position  []float64   `json:"position"`
		Positions [][]float64 `json:"positions"`
	} `json:"npcs"`
	Monsters []struct {
		Type     string    `json:"type"`
		Boundary []float64 `json:"boundary"` // [x1, y1, x2, y2]; missing for a few
	} `json:"monsters"`
}

// Maps decodes G.maps (map name -> MapDef). It decodes on each call: keep
// the result.
func Maps(G *gdata.GData) (map[string]MapDef, error) {
	var m map[string]MapDef
	if err := json.Unmarshal(G.Tables["maps"], &m); err != nil {
		return nil, fmt.Errorf("G.maps: %w", err)
	}
	return m, nil
}

// Travel moves one character.
type Travel struct {
	world  *world.World
	act    *actions.Actions
	G      *gdata.GData
	maps   map[string]MapDef // G.maps, decoded once
	places map[string]int    // G.npcs.transporter.places: map -> spawn
}

// New makes the travel of one character.
func New(w *world.World, act *actions.Actions) *Travel {
	t := &Travel{world: w, act: act, G: w.G}
	t.maps, _ = Maps(w.G) // an empty table if G has none: no routes
	var npcs map[string]struct {
		Places map[string]int `json:"places"`
	}
	_ = json.Unmarshal(w.G.Tables["npcs"], &npcs)
	t.places = npcs["transporter"].Places
	return t
}

// region walk-to

// WalkTo walks to (x, y) on this map, around the walls. If (x, y) is not
// walkable, it walks to the nearest walkable point (at most 320 px away). It
// returns true when we arrived; false when there is no path, or when
// something stopped the walk: a `correction`, a death, a door, or jail. The
// caller decides again on its next tick.
func (t *Travel) WalkTo(x, y float64) (bool, error) {
	t.world.Advance()
	me := t.world.CopyMe()
	mapName, m := me.Str("map"), me.Num("m") // m: the map counter; it changes on each map change
	grid, err := pathfind.ForMap(t.G, mapName)
	if err != nil {
		return false, err
	}
	if !grid.Safe(x, y) {
		k := grid.NearestFree(x, y)
		if k < 0 {
			return false, nil
		}
		p := grid.Point(k)
		x, y = p.X, p.Y
	}
	path := grid.FindPath(me.Num("x"), me.Num("y"), x, y)
	if path == nil {
		return false, nil
	}
	for _, p := range path {
		arrived, err := t.act.MoveTo(p.X, p.Y)
		if err != nil {
			return false, err // the socket closed
		}
		now := t.world.CopyMe()
		if now.Str("map") != mapName || now.Num("m") != m || now.Bool("rip") {
			return false, nil // we left this map, or died
		}
		if !arrived {
			return false, nil // a correction: our position was wrong
		}
	}
	return true, nil
}

// endregion walk-to

// region transport

// Transport sends `transport` {to, s}: through a door near us, or with the
// transporter NPC near us. Then it waits until `new_map` puts us on mapName.
// The server answers a door with success and sends `new_map` first; the bank
// answers {in_progress: true}, and `new_map` comes later
// (node/server.js:5887-6056).
func (t *Travel) Transport(mapName string, spawn int) (bool, error) {
	m := t.world.CopyMe().Num("m")
	r, err := t.act.Request("transport", map[string]any{"to": mapName, "s": spawn}, "transport", 2*time.Second)
	if errors.Is(err, actions.ErrNoReply) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if r.Failed { // for example transport_cant_reach: too far from the door
		return false, nil
	}
	return t.waitUntil(func(me world.Entity) bool { return me.Num("m") != m && me.Str("map") == mapName }), nil
}

// endregion transport

// region leave-jail

// LeaveJail: a line violation (a `move` from or to a point that is not
// walkable) sends the character to the map `jail`. `leave` takes it to
// `main` spawn 0, the town (node/server.js:5864-5885). It fails while the
// character is dead, or with more than 5 monsters on it.
func (t *Travel) LeaveJail() (bool, error) {
	r, err := t.act.Request("leave", map[string]any{}, "leave", 2*time.Second)
	if errors.Is(err, actions.ErrNoReply) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if r.Failed {
		return false, nil
	}
	return t.waitUntil(func(me world.Entity) bool { return me.Str("map") != "jail" }), nil
}

// endregion leave-jail

// region route

// Exits are the ways out of mapName: each door that needs no key, and each
// place of the transporter if the map has one. A door [x, y, w, h, to,
// to_spawn, own_spawn, lock] works from its own spawn point (door[6]); the
// server measures from the box of the door at that spawn
// (node/server.js:5899-5910).
func (t *Travel) Exits(mapName string) []Hop {
	def, ok := t.maps[mapName]
	if !ok {
		return nil
	}
	var out []Hop
	for _, door := range def.Doors {
		if len(door) < 7 {
			continue
		}
		if len(door) > 7 && door[7] != nil && door[7] != false && door[7] != "" {
			continue // a locked door ("ulocked", ...): it needs a key first
		}
		to, _ := door[4].(string)
		toSpawn, _ := door[5].(float64)
		own, _ := door[6].(float64)
		if int(own) < len(def.Spawns) && len(def.Spawns[int(own)]) >= 2 {
			s := def.Spawns[int(own)]
			out = append(out, Hop{mapName, s[0], s[1], to, int(toSpawn), "door"})
		}
	}
	for _, n := range def.NPCs {
		if n.ID != "transporter" {
			continue
		}
		pos := n.Position
		if pos == nil && len(n.Positions) > 0 {
			pos = n.Positions[0]
		}
		if len(pos) < 2 {
			continue
		}
		// G.npcs.transporter.places: map -> the spawn where she sends you.
		// Sorted, so that the route is the same on each run.
		names := make([]string, 0, len(t.places))
		for to := range t.places {
			names = append(names, to)
		}
		sort.Strings(names)
		for _, to := range names {
			if to != mapName {
				out = append(out, Hop{mapName, pos[0], pos[1], to, t.places[to], "transporter"})
			}
		}
	}
	return out
}

// Route is the fewest hops from one map to another: a breadth-first search
// on the graph of maps. It returns an empty route when we are there, and
// false when no route exists.
func (t *Travel) Route(from, to string) ([]Hop, bool) {
	if from == to {
		return []Hop{}, true
	}
	came := map[string]*Hop{from: nil} // map -> the hop that reached it
	queue := []string{from}
	for len(queue) > 0 {
		m := queue[0]
		queue = queue[1:]
		for _, hop := range t.Exits(m) {
			if _, seen := came[hop.To]; seen {
				continue
			}
			if _, known := t.maps[hop.To]; !known {
				continue
			}
			h := hop
			came[hop.To] = &h
			if hop.To == to {
				var hops []Hop
				for p := &h; p != nil; p = came[p.Map] {
					hops = append([]Hop{*p}, hops...)
				}
				return hops, true
			}
			queue = append(queue, hop.To)
		}
	}
	return nil, false
}

// GoToMap goes to mapName along Route: for each hop, walk to the door (or to
// the transporter), then transport. It returns true when we are on mapName.
func (t *Travel) GoToMap(mapName string) (bool, error) {
	hops, ok := t.Route(t.world.CopyMe().Str("map"), mapName)
	if !ok {
		return false, nil
	}
	for _, hop := range hops {
		if ok, err := t.WalkTo(hop.X, hop.Y); !ok || err != nil {
			return false, err
		}
		// WalkTo can stop short of the point (at the nearest walkable cell).
		// The server then says "transport_cant_reach"; do not even ask.
		me := t.world.CopyMe()
		reach := doorDist
		if hop.By == "transporter" {
			reach = transporterDist
		}
		if math.Hypot(me.Num("x")-hop.X, me.Num("y")-hop.Y) > reach {
			return false, nil
		}
		if ok, err := t.Transport(hop.To, hop.Spawn); !ok || err != nil {
			return false, err
		}
	}
	return t.world.CopyMe().Str("map") == mapName, nil
}

// endregion route

// waitUntil polls test (with a copy of our character) every 50 ms, until
// it is true or newMapWait has passed.
func (t *Travel) waitUntil(test func(world.Entity) bool) bool {
	for end := time.Now().Add(newMapWait); time.Now().Before(end); time.Sleep(50 * time.Millisecond) {
		if test(t.world.CopyMe()) {
			return true
		}
	}
	return test(t.world.CopyMe())
}
