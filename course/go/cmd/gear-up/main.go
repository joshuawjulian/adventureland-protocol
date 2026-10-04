// cmd/gear-up/main.go: upgrades a coat to +3 and compounds rings in groups
// of three, with the stop rule of the game guide. It farms first until it
// has a chest (gold and rings).
//
//	Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger go run ./cmd/gear-up
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"sort"
	"sync/atomic"
	"time"

	"albot/actions"
	"albot/bot"
	"albot/farmer"
	"albot/items"
	"albot/travel"
)

const tick = 100 * time.Millisecond

// region rules
// The stop rule (the game guide, "A progression plan"): take a piece to +3
// with no spare copy. Above +3 the chance falls (70 % for +4), so stop and
// use spares ("Step 2"). Also stop when the server's chance, with grace, is
// below 90 %: then a failure is too likely for an item that we wear.
const (
	item        = "coat" // 6,000 gold at Gabriel (`basics`)
	targetLevel = 3
	minChance   = 0.9
)

// Jewelry: compound groups of three while the chance is at least 90 %. For
// most jewelry that is +0 -> +1 only (99 %); +2 is 75 %.
// endregion rules

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

// result is "success", "fail" or the response code of a roll.
func result(r actions.GameResponse, err error, event string) string {
	switch {
	case errors.Is(err, actions.ErrNoReply):
		return "no answer"
	case r.Response == event+"_success":
		return "success"
	case r.Response == event+"_fail":
		return "fail"
	}
	return r.Response
}

func run() error {
	b, err := bot.Connect(context.Background())
	if err != nil {
		return err
	}
	defer b.Close()
	w := b.World
	me := w.CopyMe()
	fmt.Printf("in game as %s (%s, level %.0f) on %s at %.0f,%.0f\n",
		me.Str("id"), me.Str("ctype"), me.Num("level"), me.Str("map"), me.Num("x"), me.Num("y"))
	tr := travel.New(w, b.Act)
	inv := items.New(w, b.Act, b.Budget)
	f := farmer.New(w, b.Act, b.Cooldowns, tr, "")

	// 1. Farm until one chest opened: the first chest brings gold and rings.
	var chests atomic.Int32
	w.Listen("chest_opened", func(d json.RawMessage) {
		var r struct{ Gone bool }
		if json.Unmarshal(d, &r) == nil && !r.Gone {
			chests.Add(1)
		}
	})
	for chests.Load() == 0 {
		time.Sleep(tick)
		if err := f.Tick(); err != nil {
			return err
		}
	}

	// goNear walks to within `within` px of an NPC (or of a point). It says
	// so only when it must walk.
	goNear := func(npc items.NPC, within float64) error {
		w.Advance()
		me := w.CopyMe()
		if math.Hypot(me.Num("x")-npc.X, me.Num("y")-npc.Y) <= within {
			return nil
		}
		fmt.Printf("walk to %s at %.0f,%.0f\n", npc.ID, npc.X, npc.Y)
		if ok, err := tr.WalkTo(npc.X, npc.Y); !ok || err != nil {
			return fmt.Errorf("could not walk to %s (%v)", npc.ID, err)
		}
		return nil
	}
	// buyOne buys one `name` and returns its slot number.
	buyOne := func(name string) (int, error) {
		npc, ok := inv.NPCSelling(name)
		if !ok {
			return -1, errors.New("no NPC sells " + name)
		}
		if err := goNear(npc, items.NPCDist); err != nil {
			return -1, err
		}
		r, err := inv.Buy(name, 1)
		if err != nil || r.Failed {
			return -1, fmt.Errorf("buy %s: %s (%v)", name, r.Response, err)
		}
		fmt.Printf("buy %s x1: %.0f gold\n", name, r.Data.Num("cost"))
		return int(r.Data.Num("num")), nil
	}

	// 2. The item to upgrade.
	num := inv.Find(item, -1)
	if num < 0 {
		if num, err = buyOne(item); err != nil {
			return err
		}
	}

	// 3. Stand where both Lucas (scrolls) and Cue (upgrade, compound) are
	//    within 400 px: the middle of the two (about 140 px from each).
	lucas, ok1 := inv.NPCSelling("scroll0")
	cue, ok2 := inv.NPCWithRole("newupgrade")
	if !ok1 || !ok2 {
		return errors.New("no scroll shop or upgrade NPC on this map")
	}
	spot := items.NPC{ID: "scrolls and newupgrade", X: math.Round((lucas.X + cue.X) / 2), Y: math.Round((lucas.Y + cue.Y) / 2)}
	if err := goNear(spot, 20); err != nil { // 20 px: near the middle, so that both stay within 400 px
		return err
	}

	// region upgrade-loop
	for num >= 0 {
		it := items.ItemAt(w.CopyMe(), num)
		level := int(it.Num("level"))
		if it == nil || level >= targetLevel {
			break
		}
		scroll := inv.Find("scroll0", -1)
		if scroll < 0 {
			if scroll, err = buyOne("scroll0"); err != nil {
				return err
			}
		}
		// Ask first: the chance includes grace, which only the server knows.
		calc, err := inv.Upgrade(num, scroll, true)
		if err != nil || calc.Failed || calc.Response != "upgrade_chance" {
			fmt.Printf("upgrade %s: %s\n", item, result(calc, err, "upgrade"))
			break
		}
		chance := calc.Data.Num("chance")
		if chance < minChance {
			fmt.Printf("stop: the chance for +%d is %.2f\n", level+1, chance)
			break
		}
		r, err := inv.Upgrade(num, scroll, false)
		res := result(r, err, "upgrade")
		fmt.Printf("upgrade %s +%d -> +%d: %s (chance %.2f)\n", item, level, level+1, res, chance)
		if res != "success" {
			break // a fail destroys the item
		}
		if r.Data != nil {
			num = int(r.Data.Num("num"))
		}
	}
	// endregion upgrade-loop

	// region compound-loop
	// findGroup: three slots with the same name and level, of an item that
	// compounds (G `compound`).
	findGroup := func() ([3]int, bool) {
		me := w.CopyMe()
		groups := map[string][]int{}
		var keys []string
		for n := 0; n < items.Count(me); n++ {
			it := items.ItemAt(me, n)
			if it == nil || it["l"] != nil || !inv.Compounds(it.Str("name")) {
				continue
			}
			key := fmt.Sprintf("%s %.0f", it.Str("name"), it.Num("level"))
			if groups[key] == nil {
				keys = append(keys, key)
			}
			groups[key] = append(groups[key], n)
		}
		sort.Strings(keys)
		for _, k := range keys {
			if g := groups[k]; len(g) >= 3 {
				return [3]int{g[0], g[1], g[2]}, true
			}
		}
		return [3]int{}, false
	}
	for group, ok := findGroup(); ok; group, ok = findGroup() {
		it := items.ItemAt(w.CopyMe(), group[0])
		name, level := it.Str("name"), int(it.Num("level"))
		scroll := inv.Find("cscroll0", -1)
		if scroll < 0 {
			if scroll, err = buyOne("cscroll0"); err != nil {
				return err
			}
		}
		calc, err := inv.Compound(group, scroll, true)
		chance := calc.Data.Num("chance")
		if err != nil || calc.Failed || calc.Response != "compound_chance" || chance < minChance {
			fmt.Printf("stop: compound %s +%d: %s %.2f\n", name, level, result(calc, err, "compound"), chance)
			break
		}
		r, err := inv.Compound(group, scroll, false)
		res := result(r, err, "compound")
		fmt.Printf("compound %s +%d x3 -> +%d: %s (chance %.2f)\n", name, level, level+1, res, chance)
		if res != "success" && res != "fail" {
			break
		}
	}
	// endregion compound-loop

	// 4. Wear the results.
	lines, err := inv.EquipBetter()
	for _, l := range lines {
		fmt.Println("equip " + l)
	}
	if err != nil {
		return err
	}
	me = w.CopyMe()
	show := func(s string) string {
		if it := items.Slot(me, s); it != nil {
			return fmt.Sprintf("%s +%.0f", it.Str("name"), it.Num("level"))
		}
		return "-"
	}
	fmt.Printf("gear: chest %s, ring1 %s, ring2 %s, belt %s\n", show("chest"), show("ring1"), show("ring2"), show("belt"))
	fmt.Println("OK")
	return nil
}
