// Package cooldowns knows when each skill (and the shared potion timer) is
// ready again. The server tells us in three ways: a `skill_timeout` event, a
// `game_response` "cooldown" or "not_ready" when we were too early, and an
// `eval` with code such as "pot_timeout(2000)".
//
// Concurrency: the handlers run on the dispatch goroutine of AlSocket, and
// your program asks Ready on its own goroutine. One sync.Mutex guards the
// table of ready times; each method takes it.
package cooldowns

import (
	"encoding/json"
	"regexp"
	"strconv"
	"sync"
	"time"

	"albot/world"
)

// Cooldowns maps a skill name (or "potion") to the time when it is ready.
type Cooldowns struct {
	mu      sync.Mutex
	readyAt map[string]time.Time
	w       *world.World
}

// region cooldowns

// The two `eval` codes that start a timer. The server sends JavaScript for
// the browser to run; we read the numbers out of it.
var (
	potRe   = regexp.MustCompile(`pot_timeout\((\d+)`)                // "pot_timeout(2000)"
	skillRe = regexp.MustCompile(`skill_timeout\('([^']+)',\s*(\d+)`) // "skill_timeout('ethereal',120)"
)

// New listens through w.Listen, so that hitchhikers in `player` count too.
func New(w *world.World) *Cooldowns {
	c := &Cooldowns{readyAt: map[string]time.Time{}, w: w}
	// After each skill and attack: {name, ms}.
	w.Listen("skill_timeout", func(d json.RawMessage) {
		var t struct {
			Name string  `json:"name"`
			MS   float64 `json:"ms"`
		}
		if json.Unmarshal(d, &t) == nil {
			c.Start(t.Name, t.MS)
		}
	})
	// We were too early: the reply says how many ms are left.
	w.Listen("game_response", func(d json.RawMessage) {
		var r struct {
			Response string  `json:"response"`
			Place    string  `json:"place"`
			Skill    string  `json:"skill"`
			MS       float64 `json:"ms"`
		}
		if json.Unmarshal(d, &r) != nil {
			return // a bare string: no ms in it
		}
		switch r.Response {
		case "cooldown":
			name := r.Skill
			if name == "" {
				name = r.Place
			}
			c.Start(name, r.MS)
		case "not_ready": // the potion timer
			c.Start("potion", r.MS)
		}
	})
	// eval is a string, or an object {code}.
	w.Listen("eval", func(d json.RawMessage) {
		var code string
		if json.Unmarshal(d, &code) != nil {
			var e struct {
				Code string `json:"code"`
			}
			_ = json.Unmarshal(d, &e)
			code = e.Code
		}
		if m := potRe.FindStringSubmatch(code); m != nil {
			ms, _ := strconv.ParseFloat(m[1], 64)
			c.Start("potion", ms)
		}
		if m := skillRe.FindStringSubmatch(code); m != nil {
			ms, _ := strconv.ParseFloat(m[2], 64)
			c.Start(m[1], ms)
		}
	})
	return c
}

// Start sets name as not ready for ms milliseconds. A skill with
// G.skills[name].share (for example, a skill that shares the attack
// cooldown) also starts the skill that it shares.
func (c *Cooldowns) Start(name string, ms float64) {
	at := time.Now().Add(time.Duration(ms * float64(time.Millisecond)))
	c.mu.Lock()
	defer c.mu.Unlock()
	c.readyAt[name] = at
	if share := c.w.G.Skills[name].Share; share != "" {
		c.readyAt[share] = at
	}
}

// Ready reports whether name is ready now. A name that never started is ready.
func (c *Cooldowns) Ready(name string) bool {
	return c.MsLeft(name) == 0
}

// MsLeft is the time until name is ready, in ms; 0 when it is ready.
func (c *Cooldowns) MsLeft(name string) float64 {
	c.mu.Lock()
	defer c.mu.Unlock()
	left := time.Until(c.readyAt[name]) // the zero time is long ago: negative
	if left <= 0 {
		return 0
	}
	return float64(left.Milliseconds())
}

// endregion cooldowns
