// Package items handles the inventory and the NPC services: buy, sell,
// equip, give items and gold to another character, the bank, upgrade and
// compound.
//
// `items` in our character is the inventory: a list of 42 slots (G: isize),
// each an item {name, q?, level?, ...} or null. `slots` is the equipment:
// slot name -> item. `esize` is the number of empty inventory slots. All
// three come in `start` and `player` (node/server.js:855-1001).
//
// Concurrency: the log of game_response events is behind the Items lock. The
// handler that fills it runs on the dispatch goroutine (with the world lock
// held); the methods run on your goroutine and never hold a lock while they
// send.
package items

import (
	"context"
	"encoding/json"
	"errors"
	"slices"
	"strings"
	"sync"
	"time"

	"albot/actions"
	"albot/budget"
	"albot/gdata"
	"albot/travel"
	"albot/world"
)

// region rules

// NPCDist: an NPC sells, buys, upgrades and compounds within 400 px
// (B.sell_dist, node/server.js:220). Stand a little nearer: our position is
// an estimate.
const NPCDist = 350.0

// SlotsForType are the equipment slots for each item type
// (G.items[name].type). Rings and earrings have two slots.
var SlotsForType = map[string][]string{
	"weapon": {"mainhand"}, "shield": {"offhand"}, "source": {"offhand"}, "quiver": {"offhand"},
	"misc_offhand": {"offhand"}, "helmet": {"helmet"}, "chest": {"chest"}, "pants": {"pants"},
	"shoes": {"shoes"}, "gloves": {"gloves"}, "belt": {"belt"}, "amulet": {"amulet"}, "orb": {"orb"},
	"cape": {"cape"}, "ring": {"ring1", "ring2"}, "earring": {"earring1", "earring2"},
}

// KeepTypes are the item types that a bot keeps and never sells (the loot
// rules of the game guide, "A merchant in practice"): potions, scrolls and
// offerings, and jewelry, which you compound in groups of three.
var KeepTypes = []string{"pot", "uscroll", "cscroll", "pscroll", "offering", "ring", "earring", "amulet", "belt", "orb"}

// IsLoot reports whether an inventory item is loot to sell: not a kept
// type, not locked (`l`), not an upgrade in progress ("placeholder").
func IsLoot(G *gdata.GData, item world.Entity) bool {
	if item == nil || item.Str("name") == "placeholder" || item["l"] != nil {
		return false
	}
	def, ok := G.Items[item.Str("name")]
	return ok && !slices.Contains(KeepTypes, def.Type)
}

// endregion rules

// ItemAt returns inventory slot num of a character (a copy from
// World.CopyMe), or nil for an empty slot.
func ItemAt(me world.Entity, num int) world.Entity {
	list, _ := me["items"].([]any)
	if num < 0 || num >= len(list) {
		return nil
	}
	if it, ok := list[num].(map[string]any); ok {
		return world.Entity(it)
	}
	return nil
}

// Count is the number of inventory slots of a character.
func Count(me world.Entity) int {
	list, _ := me["items"].([]any)
	return len(list)
}

// Slot returns equipment slot `slot` of a character, or nil.
func Slot(me world.Entity, slot string) world.Entity {
	slots, _ := me["slots"].(map[string]any)
	if it, ok := slots[slot].(map[string]any); ok {
		return world.Entity(it)
	}
	return nil
}

// NPC is an NPC on a map.
type NPC struct {
	ID   string
	X, Y float64
}

type logEntry struct {
	seq int
	r   actions.GameResponse
}

// Items acts on the inventory of one character.
type Items struct {
	world  *world.World
	act    *actions.Actions
	budget *budget.Budget
	G      *gdata.GData

	maps     map[string]travel.MapDef // G.maps
	npcs     map[string]npcDef        // G.npcs
	compound map[string]bool          // the items that compound (G.items[name].compound)

	mu  sync.Mutex // guards log and seq
	log []logEntry // the last game_response events
	seq int
}

type npcDef struct {
	Items []any  `json:"items"` // item names, with null for an empty shop slot
	Role  string `json:"role"`
}

// New makes the items of one character.
func New(w *world.World, act *actions.Actions, b *budget.Budget) *Items {
	it := &Items{world: w, act: act, budget: b, G: w.G, compound: map[string]bool{}}
	it.maps, _ = travel.Maps(w.G)
	_ = json.Unmarshal(w.G.Tables["npcs"], &it.npcs)
	var raw map[string]map[string]json.RawMessage
	_ = json.Unmarshal(w.G.Tables["items"], &raw)
	for name, def := range raw {
		if _, ok := def["compound"]; ok {
			it.compound[name] = true
		}
	}
	// The results of upgrade and compound come later, as hitchhikers inside a
	// `player` update. World.Listen gets them too (World dispatches them), so
	// keep the last 50 game_response events and search them.
	w.Listen("game_response", func(d json.RawMessage) {
		r := actions.Normalize(d)
		it.mu.Lock()
		it.seq++
		it.log = append(it.log, logEntry{it.seq, r})
		if len(it.log) > 50 {
			it.log = it.log[1:]
		}
		it.mu.Unlock()
	})
	return it
}

// Compounds reports whether the item `name` can be compounded.
func (it *Items) Compounds(name string) bool { return it.compound[name] }

// region find

// Find returns the slot number of the first item called name (and of
// level, if level >= 0), or -1.
func (it *Items) Find(name string, level int) int {
	me := it.world.CopyMe()
	for n := 0; n < Count(me); n++ {
		if i := ItemAt(me, n); i != nil && i.Str("name") == name && (level < 0 || int(i.Num("level")) == level) {
			return n
		}
	}
	return -1
}

// Count is how many of name we carry (stacks count their `q`).
func (it *Items) Count(name string) int {
	me := it.world.CopyMe()
	total := 0
	for n := 0; n < Count(me); n++ {
		if i := ItemAt(me, n); i != nil && i.Str("name") == name {
			total += max(1, int(i.Num("q")))
		}
	}
	return total
}

// FreeSlots is the number of empty inventory slots.
func (it *Items) FreeSlots() int {
	me := it.world.CopyMe()
	if _, ok := me["esize"]; ok {
		return int(me.Num("esize"))
	}
	used := 0
	for n := 0; n < Count(me); n++ {
		if ItemAt(me, n) != nil {
			used++
		}
	}
	return 42 - used
}

// NPCSelling returns the NPC on our map that sells item, or false. NPCs
// with an `items` list are shops (G.npcs[id].items).
func (it *Items) NPCSelling(item string) (NPC, bool) {
	return it.npc(func(d npcDef) bool { return slices.Contains(d.Items, any(item)) })
}

// NPCWithRole returns the NPC on our map with this role, for example
// "newupgrade" (Cue: upgrade and compound) or "merchant" (a shop: it buys any
// item).
func (it *Items) NPCWithRole(role string) (NPC, bool) {
	return it.npc(func(d npcDef) bool { return d.Role == role })
}

func (it *Items) npc(test func(npcDef) bool) (NPC, bool) {
	for _, n := range it.maps[it.world.CopyMe().Str("map")].NPCs {
		pos := n.Position
		if pos == nil && len(n.Positions) > 0 {
			pos = n.Positions[0]
		}
		def, ok := it.npcs[n.ID]
		if len(pos) >= 2 && ok && test(def) {
			return NPC{n.ID, pos[0], pos[1]}, true
		}
	}
	return NPC{}, false
}

// endregion find

// request sends one event and waits 2 s for the game_response with place
// `event`. ErrNoReply means no answer came.
func (it *Items) request(event string, payload any) (actions.GameResponse, error) {
	return it.act.Request(event, payload, event, 2*time.Second)
}

// region shop

// Buy buys from an NPC within 400 px that sells the item. The answer:
// `buy_success` {cost, num, name, q}, or a failure: "distance" (too far),
// "buy_cost" (not enough gold), "buy_cant_space" (node/server.js:8409-8461).
func (it *Items) Buy(name string, quantity int) (actions.GameResponse, error) {
	return it.request("buy", map[string]any{"name": name, "quantity": quantity})
}

// Sell sells to any shop NPC within 400 px for 60 % of G.items[name].g (1
// gold for a gift item). The answer: `gold_received` {gold}
// (node/server.js:8046-8096).
func (it *Items) Sell(num, quantity int) (actions.GameResponse, error) {
	return it.request("sell", map[string]any{"num": num, "quantity": quantity})
}

// endregion shop

// region equip

// Equip puts the item of slot num on. With slot "", the server chooses one
// from the item type. The old item goes back to the inventory. The answer is
// {response: "data", slot} on success (node/server.js:7643-7915).
func (it *Items) Equip(num int, slot string) (actions.GameResponse, error) {
	payload := map[string]any{"num": num}
	if slot != "" {
		payload["slot"] = slot
	}
	return it.request("equip", payload)
}

// Unequip takes the item in slot off.
func (it *Items) Unequip(slot string) (actions.GameResponse, error) {
	return it.request("unequip", map[string]any{"slot": slot})
}

// EquipBetter equips each inventory item that is better than what we wear:
// the slot is empty, or it holds the same item at a lower level. A simple
// rule; the game guide ("Gear is more important than level") compares stats.
// It returns "name: slot" for each item that went on.
func (it *Items) EquipBetter() ([]string, error) {
	var done []string
	for num := 0; num < Count(it.world.CopyMe()); num++ {
		me := it.world.CopyMe() // again for each item: an equip changes the slots
		item := ItemAt(me, num)
		if item == nil || item.Str("name") == "placeholder" {
			continue
		}
		slots := SlotsForType[it.G.Items[item.Str("name")].Type]
		slot := ""
		for _, s := range slots {
			if Slot(me, s) == nil {
				slot = s
				break
			}
		}
		if slot == "" {
			for _, s := range slots {
				if old := Slot(me, s); old.Str("name") == item.Str("name") && old.Num("level") < item.Num("level") {
					slot = s
					break
				}
			}
		}
		if slot == "" {
			continue
		}
		r, err := it.Equip(num, slot)
		if errors.Is(err, actions.ErrNoReply) {
			continue
		}
		if err != nil {
			return done, err
		}
		if !r.Failed { // "cant_equip": not for our class
			done = append(done, item.Str("name")+": "+slot)
		}
	}
	return done, nil
}

// endregion equip

// region send

// SendItem gives items to another character on our map within 400 px. The
// answer: `item_sent`, or "distance", "send_no_space"
// (node/server.js:8463-8560).
func (it *Items) SendItem(name string, num, quantity int) (actions.GameResponse, error) {
	return it.request("send", map[string]any{"name": name, "num": num, "q": quantity})
}

// SendGold gives gold. Between characters of one account the receiver gets
// all of it; to another account, 2.5 % less (node/server.js:8590-8600).
func (it *Items) SendGold(name string, gold int) (actions.GameResponse, error) {
	return it.request("send", map[string]any{"name": name, "gold": gold})
}

// endregion send

// region bank

// Deposit puts gold into the bank. Only inside the bank (a map with
// `mount`, which Travel.GoToMap("bank") reaches); elsewhere:
// "bank_unavailable". The first answer has place "bank" and the `gold` moved
// (node/server.js:9257-9282).
func (it *Items) Deposit(gold int) (actions.GameResponse, error) {
	return it.request("bank", map[string]any{"operation": "deposit", "amount": gold})
}

// Withdraw takes gold out of the bank.
func (it *Items) Withdraw(gold int) (actions.GameResponse, error) {
	return it.request("bank", map[string]any{"operation": "withdraw", "amount": gold})
}

// endregion bank

// region upgrade

// Upgrade upgrades the item in slot itemNum with the scroll in scrollNum, at
// the upgrade NPC (within 400 px). `clevel` must be the item's level now, or
// the server says "upgrade_mismatch" (node/server.js:7166-7168).
//   - calculate: true -> the answer is `upgrade_chance` {chance}; nothing is used.
//   - calculate: false -> the scroll is used, the slot holds a "placeholder",
//     and the result comes later as a hitchhiker: `upgrade_success` or
//     `upgrade_fail` {level, num} (node/server.js:14920-14945). On a fail the
//     item is gone.
//
// A failure before the roll is a bare string ("upgrade_no_scroll") or an
// object with place "upgrade" ("distance"). ErrNoReply: no answer in time.
func (it *Items) Upgrade(itemNum, scrollNum int, calculate bool) (actions.GameResponse, error) {
	item := ItemAt(it.world.CopyMe(), itemNum)
	payload := map[string]any{"item_num": itemNum, "scroll_num": scrollNum, "clevel": int(item.Num("level"))}
	if calculate {
		payload["calculate"] = true
		return it.roll("upgrade", payload, 2*time.Second)
	}
	// 30 s: the roll of +N takes 0.5 x N x sqrt(N) s, about 9 s at +7.
	return it.roll("upgrade", payload, 30*time.Second)
}

// Compound combines three identical items (same name and level) with a
// compound scroll. The same answers as Upgrade, with "compound" in place of
// "upgrade". The roll takes 10 s (node/server.js:7037). On a success the item
// is in nums[0], one level higher; the other two slots are empty.
func (it *Items) Compound(nums [3]int, scrollNum int, calculate bool) (actions.GameResponse, error) {
	item := ItemAt(it.world.CopyMe(), nums[0])
	payload := map[string]any{"items": nums[:], "scroll_num": scrollNum, "clevel": int(item.Num("level"))}
	if calculate {
		payload["calculate"] = true
		return it.roll("compound", payload, 2*time.Second)
	}
	return it.roll("compound", payload, 30*time.Second)
}

// roll sends the event, then waits for the first game_response about it: an
// object with this place, or a response that starts with "<event>_" (the
// bare-string failures and the late hitchhiker results).
func (it *Items) roll(event string, payload any, timeout time.Duration) (actions.GameResponse, error) {
	it.mu.Lock()
	since := it.seq // only answers that come after the emit
	it.mu.Unlock()
	if err := it.budget.Emit(event, payload); err != nil {
		return actions.GameResponse{}, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	for {
		it.mu.Lock()
		for _, e := range it.log {
			if e.seq > since && (e.r.Place == event || strings.HasPrefix(e.r.Response, event+"_")) {
				it.mu.Unlock()
				return e.r, nil
			}
		}
		it.mu.Unlock()
		select {
		case <-ctx.Done():
			return actions.GameResponse{}, actions.ErrNoReply
		case <-time.After(50 * time.Millisecond):
		}
	}
}

// endregion upgrade
