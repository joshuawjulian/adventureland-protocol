// cmd/party-merchant/main.go: three fighters and one merchant in one
// program. The fighters farm in a party. The merchant walks to them, takes
// their loot and gold, sells the loot in the town and puts the gold in the
// bank.
//
//	Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyWarrior go run ./cmd/party-merchant [trips]
//	AL_CHARACTER is the leader. The program adds the next two fighters of
//	your character list, and your first merchant.
//	trips: stop after this many merchant trips (the tests use 1). Without it: until Ctrl-C.
//	Make a merchant first, if you have none:
//	go run ./cmd/party-merchant --create-merchant MyMerchant
//
// Each character runs on its own goroutine. A goroutine acts only for its
// own character; it reads the others through copies (World.CopyMe).
package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"sync"
	"time"

	"albot/actions"
	"albot/api"
	"albot/farmer"
	"albot/gdata"
	"albot/items"
	"albot/party"
	"albot/travel"
	"albot/world"
)

const tick = 100 * time.Millisecond

// region rules
const (
	fighters     = 3     // the live limit: 3 characters that fight, plus merchants (game guide, "Many characters and bots")
	giveDist     = 300.0 // `send` works within 400 px on the same map (node/server.js:8463-8560)
	fighterGold  = 20000 // a fighter keeps this much gold for potions, and gives the rest
	merchantGold = 50000 // the merchant keeps this much, and banks the rest
)

// give: a fighter keeps only its potions. Everything else goes to the
// merchant: loot to sell, and jewelry that the merchant compounds later.
func give(G *gdata.GData, it world.Entity) bool {
	return it != nil && it.Str("name") != "placeholder" && it["l"] == nil && G.Items[it.Str("name")].Type != "pot"
}

// endregion rules

// crewMember is one character with its tools.
type crewMember struct {
	m      *party.Member
	travel *travel.Travel
	items  *items.Items
	party  *party.Party
	farmer *farmer.Farmer // nil for the merchant
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	// region choose
	auth, err := api.Login(ctx)
	if err != nil {
		return err
	}
	servers, characters, err := api.ServersAndCharacters(ctx, auth)
	if err != nil {
		return err
	}
	if len(os.Args) > 1 && os.Args[1] == "--create-merchant" {
		name := ""
		if len(os.Args) > 2 {
			name = os.Args[2]
		}
		if _, err := party.CreateCharacter(ctx, auth, name, "merchant"); err != nil {
			return err
		}
		fmt.Printf("created the merchant %s. Run the program again without --create-merchant.\n", name)
		return nil
	}
	trips := 0
	if len(os.Args) > 1 {
		trips, _ = strconv.Atoi(os.Args[1])
	}
	server, err := api.FindServer(servers, os.Getenv("AL_SERVER"))
	if err != nil {
		return err
	}
	leader, err := api.FindCharacter(characters, os.Getenv("AL_CHARACTER"))
	if err != nil {
		return err
	}
	if leader.Type == "merchant" {
		return errors.New("AL_CHARACTER must be a fighter: it leads the party")
	}
	team := []api.Character{leader}
	var merchantCharacter *api.Character
	for i, c := range characters {
		if c.Type == "merchant" && merchantCharacter == nil {
			merchantCharacter = &characters[i]
		}
		if c.Type != "merchant" && c.Name != leader.Name && len(team) < fighters {
			team = append(team, c)
		}
	}
	if merchantCharacter == nil {
		return errors.New("no merchant on this account: run with --create-merchant <Name> first")
	}
	names := make([]string, len(team))
	for i, c := range team {
		names[i] = c.Name
	}
	fmt.Printf("team: %s; merchant: %s\n", strings.Join(names, ", "), merchantCharacter.Name)
	// endregion choose

	// region connect
	G, err := gdata.LoadG(ctx, api.BaseURL()) // one G for all four
	if err != nil {
		return err
	}
	var crew []*crewMember
	defer func() {
		for _, c := range crew {
			c.m.Close()
		}
	}()
	for _, c := range append(team, *merchantCharacter) {
		m, err := party.ConnectMember(ctx, auth, server, c, G)
		if err != nil {
			return err
		}
		me := m.World.CopyMe()
		fmt.Printf("in game as %s (%s, level %.0f) on %s at %.0f,%.0f\n",
			me.Str("id"), me.Str("ctype"), me.Num("level"), me.Str("map"), me.Num("x"), me.Num("y"))
		cm := &crewMember{m: m, travel: travel.New(m.World, m.Act), items: items.New(m.World, m.Act, m.Budget),
			party: party.New(m.World, m.Act)}
		if c.Type != "merchant" { // only fighters farm (a Farmer also prints each chest that opens for us)
			cm.farmer = farmer.New(m.World, m.Act, m.Cooldowns, cm.travel, m.Name+": ")
		}
		crew = append(crew, cm)
	}
	lead, merchant := crew[0], crew[len(crew)-1]
	fighting := crew[:len(crew)-1]
	// endregion connect

	// region party
	// The leader invites each one; each waits for its `invite`, then accepts.
	for _, c := range crew[1:] {
		if _, err := lead.party.Invite(c.m.Name); err != nil && !errors.Is(err, actions.ErrNoReply) {
			return err
		}
		if !c.party.WaitInvite(lead.m.Name, 5*time.Second) {
			return fmt.Errorf("%s got no invitation", c.m.Name)
		}
		r, err := c.party.Accept(lead.m.Name)
		if err != nil || r.Failed {
			return fmt.Errorf("%s could not join: %s (%v)", c.m.Name, r.Response, err)
		}
	}
	for waited := 0; len(lead.party.List()) < len(crew) && waited < 5000; waited += 100 {
		time.Sleep(100 * time.Millisecond)
	}
	fmt.Printf("party: %s\n", strings.Join(lead.party.List(), ", "))
	// endregion party

	// play ends when we stop: Ctrl-C (ctx), the last trip, or the first error
	// of a character. Each character's actions use it (SetContext), so a wait
	// in progress (a reply, a walk) ends at once too, not at its timeout.
	play, stopPlay := context.WithCancel(ctx)
	defer stopPlay()
	for _, c := range crew {
		c.m.Act.SetContext(play)
	}
	isStopped := func() bool { return play.Err() != nil }
	// fail keeps the first error of any character and stops all the others
	// at once. Without it, a fighter's error waits until the merchant's
	// trips end, and the other characters play on without that fighter.
	var errMu sync.Mutex
	var firstErr error
	fail := func(err error) {
		errMu.Lock()
		if firstErr == nil {
			firstErr = err
		}
		errMu.Unlock()
		stopPlay()
	}

	// region fighter
	// A fighter farms. When the merchant is near, it gives its loot and gold.
	fighterLoop := func(f *crewMember) error {
		w := f.m.World
		for !isStopped() {
			time.Sleep(tick)
			if err := f.farmer.Tick(); err != nil {
				return err
			}
			w.Advance()
			w.Lock()
			near, ok := w.Players[merchant.m.Name] // the merchant, if it is in our view
			near = near.Clone()
			w.Unlock()
			me := w.CopyMe()
			if !ok || w.Distance(me, near) > giveDist {
				continue
			}
			n := 0
			for num := 0; num < items.Count(me); num++ {
				it := items.ItemAt(me, num)
				if !give(G, it) {
					continue
				}
				r, err := f.items.SendItem(merchant.m.Name, num, max(1, int(it.Num("q"))))
				if err != nil && !errors.Is(err, actions.ErrNoReply) {
					return err
				}
				if err == nil && !r.Failed {
					n++
				}
			}
			// Gold only above twice the reserve: not a `send` for each small chest.
			gold := 0
			if g := int(w.CopyMe().Num("gold")); g > 2*fighterGold {
				gold = g - fighterGold
			}
			if gold > 0 {
				if _, err := f.items.SendGold(merchant.m.Name, gold); err != nil && !errors.Is(err, actions.ErrNoReply) {
					return err
				}
			}
			if n > 0 || gold > 0 {
				fmt.Printf("%s: gave %d item(s) and %d gold to %s\n", f.m.Name, n, gold, merchant.m.Name)
			}
		}
		return nil
	}
	// endregion fighter

	// region merchant
	// The merchant: wait for loot, collect it, sell it, bank the gold.
	hasLoot := func(f *crewMember) bool {
		me := f.m.World.CopyMe()
		for num := 0; num < items.Count(me); num++ {
			if give(G, items.ItemAt(me, num)) {
				return true
			}
		}
		return false
	}
	anyLoot := func() bool {
		for _, f := range fighting {
			if hasLoot(f) {
				return true
			}
		}
		return false
	}
	name := merchant.m.Name
	merchantTrip := func() (bool, error) {
		w := merchant.m.World
		// 1. Wait until a fighter has something to give, or until the merchant holds loot.
		// The merchant holds loot when a walk of the last trip failed after it collected: then go
		// on and sell it. Without this, the wait never ends: the fighters gave all already.
		holdsLoot := func() bool {
			me := w.CopyMe()
			for num := 0; num < items.Count(me); num++ {
				if items.IsLoot(G, items.ItemAt(me, num)) {
					return true
				}
			}
			return false
		}
		for !isStopped() && !holdsLoot() && !anyLoot() {
			time.Sleep(500 * time.Millisecond)
		}
		// 2. Go to each fighter with loot, and wait (10 s at most) until it gave all.
		for _, f := range fighting {
			if isStopped() || !hasLoot(f) {
				continue
			}
			fm := f.m.World.CopyMe()
			fmt.Printf("%s: walk to %s at %.0f,%.0f\n", name, f.m.Name, fm.Num("x"), fm.Num("y"))
			if _, err := merchant.travel.WalkTo(fm.Num("x"), fm.Num("y")); err != nil {
				return false, err
			}
			for waited := 0; !isStopped() && hasLoot(f) && waited < 10000; waited += 200 {
				time.Sleep(200 * time.Millisecond)
			}
		}
		// 3. Sell the loot in the town. Keep the jewelry: three of a kind compound.
		shop, ok := merchant.items.NPCSelling("hpot0")
		if !ok {
			return false, errors.New("no shop on this map")
		}
		fmt.Printf("%s: walk to %s at %.0f,%.0f\n", name, shop.ID, shop.X, shop.Y)
		if ok, err := merchant.travel.WalkTo(shop.X, shop.Y); !ok || err != nil {
			return false, err
		}
		sold, gold := 0, 0.0
		me := w.CopyMe()
		for num := 0; num < items.Count(me); num++ {
			it := items.ItemAt(me, num)
			if !items.IsLoot(G, it) {
				continue
			}
			r, err := merchant.items.Sell(num, max(1, int(it.Num("q"))))
			if err != nil && !errors.Is(err, actions.ErrNoReply) {
				return false, err
			}
			if err == nil && !r.Failed {
				sold++
				gold += r.Data.Num("gold")
			}
		}
		fmt.Printf("%s: sold %d item(s): +%.0f gold\n", name, sold, gold)
		// 4. The bank: the door is north of the town. Deposit, then go back out.
		if ok, err := merchant.travel.GoToMap("bank"); !ok || err != nil {
			return false, err
		}
		amount := max(0, int(w.CopyMe().Num("gold"))-merchantGold)
		r, err := merchant.items.Deposit(amount)
		if err != nil && !errors.Is(err, actions.ErrNoReply) {
			return false, err
		}
		deposited := 0.0
		if err == nil && !r.Failed {
			deposited = r.Data.Num("gold")
		}
		fmt.Printf("%s: in the bank: deposited %.0f gold\n", name, deposited)
		if ok, err := merchant.travel.GoToMap("main"); !ok || err != nil {
			return false, err
		}
		me = w.CopyMe()
		fmt.Printf("%s: back on main at %.0f,%.0f\n", name, me.Num("x"), me.Num("y"))
		return true, nil
	}
	// endregion merchant

	// region run
	var wg sync.WaitGroup
	for _, f := range fighting {
		wg.Add(1)
		go func(f *crewMember) {
			defer wg.Done()
			// An error after the stop is only the stop itself (context.Canceled).
			if err := fighterLoop(f); err != nil && !isStopped() {
				fail(fmt.Errorf("%s: %w", f.m.Name, err)) // the others stop at once
			}
		}(f)
	}
	for done := 0; !isStopped() && (trips == 0 || done < trips); {
		ok, err := merchantTrip()
		if err != nil {
			if !isStopped() {
				fail(fmt.Errorf("%s: %w", name, err))
			}
			break
		}
		if ok {
			done++
		}
	}
	stopPlay() // the fighters end their loops (and their waits)
	wg.Wait()
	errMu.Lock()
	defer errMu.Unlock()
	if firstErr != nil {
		return firstErr
	}
	fmt.Println("OK")
	return nil
	// endregion run
}
