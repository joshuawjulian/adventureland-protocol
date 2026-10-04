// Package farmer has the decisions of a fighting character, one tick at a
// time: stay alive, loot, choose a target, walk, attack.
//
// Tick does the first thing on this list that applies, and returns. It
// remembers nothing between ticks except the target and the counters, so a
// monster that attacks during a walk changes the next tick at once.
//  1. dead: respawn          2. in jail: leave          3. on another map: go home
//  4. low hp or mp: heal     5. a chest: open it        6. no target: choose one
//  7. too far: walk          8. in range: attack
//
// Concurrency: the target and the counters are behind the Farmer lock. The
// handlers (death, hit, chest_opened) run on the dispatch goroutine with the
// world lock held, so they read World.Me directly; Tick runs on your
// goroutine and reads copies.
package farmer

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"slices"
	"sync"

	"albot/actions"
	"albot/cooldowns"
	"albot/travel"
	"albot/world"
)

// region ladder

// Ladder is the Mainland ladder of the game guide ("Your first day"): the
// next monster when the current one is too easy. All live on `main`.
var Ladder = []string{"goo", "bee", "crab", "snake", "squig", "armadillo", "croc", "tortoise"}

// "Too easy": the last 3 kills took 2 attacks or fewer each (the guide's
// rule: "go to the next monster when you kill the current one in one or two
// hits").
const (
	easyHits  = 2
	easyKills = 3
)

// endregion ladder

// Heal below 70 % hp: a potion (or the free regeneration) brings us back up
// before a weak monster can take the other 30 %. Mana below 30 %: a class
// that uses mana for attacks (priest, mage) needs it.
const (
	healHP = 0.7
	healMP = 0.3
)

// rangeMargin: stop 10 px inside our range: the monster moves while we walk.
const rangeMargin = 10.0

// Farmer fights for one character.
type Farmer struct {
	Home   string // the map of our monsters: "main"
	Prefix string // put before each line that it prints ("Tester: ")

	world     *world.World
	act       *actions.Actions
	cooldowns *cooldowns.Cooldowns
	travel    *travel.Travel
	monsters  map[string][]float64 // G.maps[Home].monsters: type -> its spawn box

	mu     sync.Mutex // guards the fields below
	mtype  string     // the monster type that we hunt now
	target string     // the id of the monster that we attack; "" for none
	kills  int
	hits   int   // our hits on the target
	recent []int // hits for each of the last kills
}

// New makes the farmer of one character. It hunts goos on main first.
func New(w *world.World, act *actions.Actions, cd *cooldowns.Cooldowns, t *travel.Travel, prefix string) *Farmer {
	f := &Farmer{Home: "main", Prefix: prefix, world: w, act: act, cooldowns: cd, travel: t, mtype: "goo",
		monsters: map[string][]float64{}}
	if maps, err := travel.Maps(w.G); err == nil {
		for _, m := range maps[f.Home].Monsters {
			if _, ok := f.monsters[m.Type]; !ok && len(m.Boundary) == 4 {
				f.monsters[m.Type] = m.Boundary
			}
		}
	}
	// The target is dead when we get `death` with its id, or a `hit` with kill.
	w.Listen("death", func(d json.RawMessage) {
		var e struct{ ID string }
		if json.Unmarshal(d, &e) == nil {
			f.dead(e.ID)
		}
	})
	w.Listen("hit", func(d json.RawMessage) {
		var e struct {
			ID   string `json:"id"`
			HID  string `json:"hid"`
			Kill bool   `json:"kill"`
		}
		if json.Unmarshal(d, &e) != nil {
			return
		}
		f.mu.Lock()
		if e.ID == f.target && e.HID == w.Me.Str("id") { // the world lock is held here
			f.hits++
		}
		f.mu.Unlock()
		if e.Kill {
			f.dead(e.ID)
		}
	})
	// Each chest that opens for us.
	w.Listen("chest_opened", func(d json.RawMessage) {
		var r struct {
			ID    string  `json:"id"`
			Gone  bool    `json:"gone"`
			Gold  float64 `json:"gold"`
			Items []any   `json:"items"`
		}
		if json.Unmarshal(d, &r) == nil && !r.Gone {
			f.Log(fmt.Sprintf("chest %s: +%.0f gold, %d item(s)", r.ID, r.Gold, len(r.Items)))
		}
	})
	return f
}

// Log prints one line with the prefix.
func (f *Farmer) Log(line string) { fmt.Println(f.Prefix + line) }

// Kills is the number of kills so far.
func (f *Farmer) Kills() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.kills
}

// Type is the monster type that we hunt now.
func (f *Farmer) Type() string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.mtype
}

// ClearTarget forgets the target: the next tick chooses again.
func (f *Farmer) ClearTarget() {
	f.mu.Lock()
	f.target = ""
	f.mu.Unlock()
}

func (f *Farmer) dead(id string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if id == "" || id != f.target {
		return
	}
	f.Log(fmt.Sprintf("killed %s %s", f.mtype, id))
	f.kills++
	f.recent = append(f.recent, f.hits)
	if len(f.recent) > easyKills {
		f.recent = f.recent[len(f.recent)-easyKills:]
	}
	f.target = ""
	f.hits = 0
}

// region next-type

// NextType moves up the ladder when the last kills were easy. It returns
// true when the type changed. Check the next monster in the game guide
// first: its damage per second must be less than your healing (game guide,
// "Your first day").
func (f *Farmer) NextType() bool {
	f.mu.Lock()
	defer f.mu.Unlock()
	i := slices.Index(Ladder, f.mtype)
	easy := len(f.recent) == easyKills
	for _, h := range f.recent {
		easy = easy && h <= easyHits
	}
	if !easy || i < 0 || i+1 >= len(Ladder) {
		return false
	}
	f.mtype = Ladder[i+1]
	f.recent = nil
	f.target = ""
	f.Log("next monster: " + f.mtype)
	return true
}

// endregion next-type

// region tick

// Tick makes one decision. An error means that the socket closed.
func (f *Farmer) Tick() error {
	w, act, t := f.world, f.act, f.travel
	w.Advance() // positions at this moment
	me := w.CopyMe()
	at := func(e world.Entity) string { return fmt.Sprintf("%.0f,%.0f", e.Num("x"), e.Num("y")) }

	// 1. Dead: wait for the 12 s, then respawn (at main spawn 5 on `main`).
	if me.Bool("rip") {
		f.Log(fmt.Sprintf("died; respawn in %.0f s", math.Ceil(act.RespawnWait().Seconds())))
		ok, err := act.Respawn()
		if ok {
			f.Log("respawned at " + at(w.CopyMe()))
		}
		return fatal(err)
	}
	// 2. Jail: a line violation put us there. `leave` goes to the town.
	if me.Str("map") == "jail" {
		f.Log("in jail: leave")
		ok, err := t.LeaveJail()
		if ok {
			me = w.CopyMe()
			f.Log(fmt.Sprintf("left jail: on %s at %s", me.Str("map"), at(me)))
		}
		return err
	}
	// 3. Another map (a door, the bank, a respawn somewhere else): go home.
	if me.Str("map") != f.Home {
		f.Log(fmt.Sprintf("on %s: go to %s", me.Str("map"), f.Home))
		_, err := t.GoToMap(f.Home)
		return err
	}
	// 4. Health first, then mana. Heal drinks a potion if we have one.
	if f.cooldowns.Ready("potion") {
		var err error
		if me.Num("hp") < healHP*me.Num("max_hp") {
			_, err = act.Heal("hp")
		} else if me.Num("mp") < healMP*me.Num("max_mp") {
			_, err = act.Heal("mp")
		}
		if err = fatal(err); err != nil {
			return err
		}
	}
	// 5. Chests: open them all. Gold and items wait in a chest for 8 min only.
	if len(w.ChestIDs()) > 0 {
		_, err := act.OpenChests()
		return fatal(err)
	}
	// 6. The target. Choose the nearest of our type if we have none.
	f.mu.Lock()
	id, mtype := f.target, f.mtype
	f.mu.Unlock()
	target, ok := w.CopyMonster(id)
	if id == "" || !ok {
		target = w.NearestMonster(mtype)
		if target == nil {
			// None in view: walk to the middle of its spawn box (G.maps[map].monsters).
			if b, ok := f.monsters[mtype]; ok {
				_, err := t.WalkTo((b[0]+b[2])/2, (b[1]+b[3])/2)
				return err
			}
			return nil
		}
		f.mu.Lock()
		f.target, f.hits = target.Str("id"), 0
		f.mu.Unlock()
		f.Log(fmt.Sprintf("target: %s %s at %s", mtype, target.Str("id"), at(target)))
	}
	// 7. Too far: walk to a point `range - 10` px from it, on the line to us.
	if w.Distance(me, target) > me.Num("range") {
		dx, dy := me.Num("x")-target.Num("x"), me.Num("y")-target.Num("y")
		d := math.Hypot(dx, dy)
		if d == 0 {
			d = 1
		}
		stop := math.Max(0, me.Num("range")-rangeMargin)
		_, err := t.WalkTo(target.Num("x")+dx/d*stop, target.Num("y")+dy/d*stop)
		return err
	}
	// 8. In range: attack when the cooldown allows.
	if f.cooldowns.Ready("attack") {
		if _, err := act.Attack(target.Str("id")); fatal(err) != nil {
			return err
		}
	}
	return nil
}

// endregion tick

// fatal keeps only the errors that end a session: "no reply in time" is a
// normal answer here (the next tick tries again).
func fatal(err error) error {
	if errors.Is(err, actions.ErrNoReply) {
		return nil
	}
	return err
}
