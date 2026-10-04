// cmd/supplies/main.go: a farming bot that looks after itself. After each
// chest it wears better gear; when potions or bag space run low, it walks to
// the town, sells the loot, buys potions and the basic armor, and goes back
// to farm.
//
//	Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger go run ./cmd/supplies [trips]
//	trips: stop after this many town trips (the tests use 1). Without it: until Ctrl-C.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"os/signal"
	"strconv"
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
// The restock rule (the game guide, "Your first hour" and "Inventory"):
const (
	minPotions = 20   // go to town below 20 hpot0 or 20 mpot0 ...
	minFree    = 5    // ... or below 5 free inventory slots
	potions    = 50   // buy up to 50 of each (20 gold each: 2,000 gold for both)
	keepGold   = 2000 // never spend the potion money on armor ("Your first day", step 1)
)

// armor: the basic armor that a new character does not wear, from Gabriel (`basics`).
var armor = []string{"gloves", "coat", "pants"}

// endregion rules

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	trips := 0
	if len(os.Args) > 1 {
		trips, _ = strconv.Atoi(os.Args[1])
	}
	b, err := bot.Connect(ctx)
	if err != nil {
		return err
	}
	defer b.Close()
	w, G := b.World, b.G
	me := w.CopyMe()
	fmt.Printf("in game as %s (%s, level %.0f) on %s at %.0f,%.0f\n",
		me.Str("id"), me.Str("ctype"), me.Num("level"), me.Str("map"), me.Num("x"), me.Num("y"))
	tr := travel.New(w, b.Act)
	inv := items.New(w, b.Act, b.Budget)
	f := farmer.New(w, b.Act, b.Cooldowns, tr, "")

	// region town
	// goNear walks to within NPCDist of an NPC. It says so only when it must walk.
	goNear := func(npc items.NPC, ok bool) (bool, error) {
		if !ok {
			return false, errors.New("no such NPC on this map")
		}
		w.Advance()
		me := w.CopyMe()
		if math.Hypot(me.Num("x")-npc.X, me.Num("y")-npc.Y) <= items.NPCDist {
			return true, nil
		}
		fmt.Printf("walk to %s at %.0f,%.0f\n", npc.ID, npc.X, npc.Y)
		return tr.WalkTo(npc.X, npc.Y)
	}
	// shop buys quantity of name from the NPC that sells it.
	shop := func(name string, quantity int) error {
		npc, ok := inv.NPCSelling(name)
		if near, err := goNear(npc, ok); !near || err != nil {
			return err
		}
		r, err := inv.Buy(name, quantity)
		switch {
		case errors.Is(err, actions.ErrNoReply):
			fmt.Printf("buy %s: no answer\n", name)
		case err != nil:
			return err
		case r.Failed:
			fmt.Printf("buy %s: %s\n", name, r.Response)
		default:
			fmt.Printf("buy %s x%.0f: %.0f gold\n", name, r.Data.Num("q"), r.Data.Num("cost"))
		}
		return nil
	}
	equipBetter := func() error {
		lines, err := inv.EquipBetter()
		for _, l := range lines {
			fmt.Println("equip " + l)
		}
		return err
	}
	townTrip := func() (bool, error) {
		// 1. Sell the loot to the potion shop (any shop buys any item).
		npc, ok := inv.NPCSelling("hpot0")
		if near, err := goNear(npc, ok); !near || err != nil {
			return false, err
		}
		me := w.CopyMe()
		for num := 0; num < items.Count(me); num++ {
			it := items.ItemAt(me, num)
			if !items.IsLoot(G, it) {
				continue
			}
			r, err := inv.Sell(num, max(1, int(it.Num("q"))))
			if err != nil && !errors.Is(err, actions.ErrNoReply) {
				return false, err
			}
			if err == nil && !r.Failed {
				fmt.Printf("sell %s: +%.0f gold\n", it.Str("name"), r.Data.Num("gold"))
			}
		}
		// 2. Potions, up to `potions` of each.
		for _, name := range []string{"hpot0", "mpot0"} {
			if need := potions - inv.Count(name); need > 0 {
				if err := shop(name, need); err != nil {
					return false, err
				}
			}
		}
		// 3. The basic armor that we do not wear, while the gold lasts.
		for _, name := range armor {
			slot := G.Items[name].Type // "gloves", "chest", "pants": the slot has the type's name
			me := w.CopyMe()
			if items.Slot(me, slot) != nil || int(me.Num("gold"))-G.Items[name].G < keepGold {
				continue
			}
			if err := shop(name, 1); err != nil {
				return false, err
			}
		}
		if err := equipBetter(); err != nil {
			return false, err
		}
		fmt.Printf("bag: %d hpot0, %d mpot0, %d free slot(s), %.0f gold\n",
			inv.Count("hpot0"), inv.Count("mpot0"), inv.FreeSlots(), w.CopyMe().Num("gold"))
		return true, nil
	}
	// endregion town

	// region loop
	var chests atomic.Int32 // chests opened so far (the handler runs on the dispatch goroutine)
	w.Listen("chest_opened", func(d json.RawMessage) {
		var r struct{ Gone bool }
		if json.Unmarshal(d, &r) == nil && !r.Gone {
			chests.Add(1)
		}
	})
	seen := int32(0) // chests that we checked after
	done := 0
	for ctx.Err() == nil && (trips == 0 || done < trips) {
		time.Sleep(tick)
		if err := f.Tick(); err != nil {
			return err
		}
		if chests.Load() == seen {
			continue
		}
		// After each chest: wear what is better, then check the supplies.
		seen = chests.Load()
		if err := equipBetter(); err != nil {
			return err
		}
		hp, mp, free := inv.Count("hpot0"), inv.Count("mpot0"), inv.FreeSlots()
		if hp >= minPotions && mp >= minPotions && free >= minFree {
			continue
		}
		fmt.Printf("supplies low: %d hpot0, %d mpot0, %d free slot(s)\n", hp, mp, free)
		ok, err := townTrip()
		if err != nil {
			return err
		}
		if ok {
			done++
		}
		f.ClearTarget() // choose again: the old target is far away now
	}
	// endregion loop

	fmt.Println("OK")
	return nil
}
