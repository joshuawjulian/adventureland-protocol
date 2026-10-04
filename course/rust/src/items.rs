// items.rs: the inventory and the NPC services: buy, sell, equip, give items
// and gold to another character, the bank, upgrade and compound.
//
// `me.items` is the inventory: an array of 42 slots (G: isize), each an item
// {name, q?, level?, ...} or null. `me.slots` is the equipment: slot name ->
// item. `me.esize` is the number of empty inventory slots. All three come in
// `start` and `player` (node/server.js:855-1001).
//
// Concurrency: Items is a Clone handle. Its log of game_response events is
// behind one lock, which a handler fills on the dispatcher task.

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use crate::actions::{normalize, Actions, GameResponse};
use crate::alsocket::Result;
use crate::budget::Budget;
use crate::gdata::GData;
use crate::world::{num, text, World};

// region rules
/// An NPC sells, buys, upgrades and compounds within 400 px (B.sell_dist,
/// node/server.js:220). Stand a little nearer: our position is an estimate.
pub const NPC_DIST: f64 = 350.0;

/// The equipment slots for each item type (G.items[name].type). Rings and
/// earrings have two slots.
pub const SLOTS_FOR_TYPE: &[(&str, &[&str])] = &[
    ("weapon", &["mainhand"]), ("shield", &["offhand"]), ("source", &["offhand"]),
    ("quiver", &["offhand"]), ("misc_offhand", &["offhand"]), ("helmet", &["helmet"]),
    ("chest", &["chest"]), ("pants", &["pants"]), ("shoes", &["shoes"]), ("gloves", &["gloves"]),
    ("belt", &["belt"]), ("amulet", &["amulet"]), ("orb", &["orb"]), ("cape", &["cape"]),
    ("ring", &["ring1", "ring2"]), ("earring", &["earring1", "earring2"]),
];

/// The item types that a bot keeps and never sells (the loot rules of the
/// game guide, "A merchant in practice"): potions, scrolls and offerings, and
/// jewelry, which you compound in groups of three.
pub const KEEP_TYPES: &[&str] = &["pot", "uscroll", "cscroll", "pscroll", "offering", "ring", "earring", "amulet", "belt", "orb"];

/// The slots for an item type, or None for an item that you cannot wear.
pub fn slots_for(kind: &str) -> Option<&'static [&'static str]> {
    SLOTS_FOR_TYPE.iter().find(|(t, _)| *t == kind).map(|(_, s)| *s)
}

/// Is this inventory item loot to sell? Not a kept type, not locked (`l`),
/// not an upgrade in progress ("placeholder").
pub fn is_loot(g: &GData, item: &Value) -> bool {
    let name = item["name"].as_str().unwrap_or_default();
    if name.is_empty() || name == "placeholder" || !item["l"].is_null() {
        return false;
    }
    g.items.get(name).is_some_and(|def| !KEEP_TYPES.contains(&def.kind.as_str()))
}
// endregion rules

/// An NPC on our map: its id in G.npcs and its position.
#[derive(Debug, Clone)]
pub struct Npc {
    pub id: String,
    pub x: f64,
    pub y: f64,
}

/// The last game_response events, with a sequence number each.
#[derive(Default)]
struct Log {
    seq: u64,
    list: VecDeque<(u64, GameResponse)>,
}

/// The inventory of one character. Clones share the same log.
#[derive(Clone)]
pub struct Items {
    world: World,
    act: Actions,
    budget: Budget,
    log: Arc<Mutex<Log>>,
}

impl Items {
    pub fn new(world: &World, act: &Actions, budget: &Budget) -> Items {
        let items = Items { world: world.clone(), act: act.clone(), budget: budget.clone(), log: Arc::default() };
        // The results of upgrade and compound come later, as hitchhikers inside
        // a `player` update. world.listen gets them too (on_player dispatches
        // them), so keep the last 50 game_response events and search them.
        let log = items.log.clone();
        world.listen("game_response", move |_, d| {
            let mut log = log.lock().unwrap_or_else(|p| p.into_inner());
            log.seq += 1;
            let seq = log.seq;
            log.list.push_back((seq, normalize(d)));
            if log.list.len() > 50 {
                log.list.pop_front();
            }
        });
        items
    }

    /// A copy of the inventory (null for an empty slot).
    pub fn list(&self) -> Vec<Value> {
        self.world.lock().me.get("items").and_then(Value::as_array).cloned().unwrap_or_default()
    }

    // region find
    /// The slot number of the first item called `name` (and of `level`, if
    /// given), or None.
    pub fn find(&self, name: &str, level: Option<u64>) -> Option<usize> {
        self.list().iter().position(|it| {
            it["name"] == name && level.map_or(true, |l| it["level"].as_u64().unwrap_or(0) == l)
        })
    }

    /// How many of `name` we carry (stacks count their `q`).
    pub fn count(&self, name: &str) -> u64 {
        self.list().iter().filter(|it| it["name"] == name).map(|it| it["q"].as_u64().unwrap_or(1)).sum()
    }

    /// The number of empty inventory slots.
    pub fn free_slots(&self) -> i64 {
        let w = self.world.lock();
        if let Some(e) = w.me.get("esize").and_then(Value::as_i64) {
            return e;
        }
        let used = w.me.get("items").and_then(Value::as_array).map_or(0, |a| a.iter().filter(|i| !i.is_null()).count());
        w.me.get("isize").and_then(Value::as_i64).unwrap_or(42) - used as i64
    }

    /// The NPC on our map that sells `item`, or None. NPCs with an `items`
    /// list are shops (G.npcs[id].items).
    pub fn npc_selling(&self, item: &str) -> Option<Npc> {
        self.npc(|npc| npc["items"].as_array().is_some_and(|l| l.iter().any(|i| i == item)))
    }

    /// The NPC on our map with this role, for example "newupgrade" (Cue:
    /// upgrade and compound) or "merchant" (a shop: it buys any item).
    pub fn npc_with_role(&self, role: &str) -> Option<Npc> {
        self.npc(|npc| npc["role"] == role)
    }

    fn npc(&self, test: impl Fn(&Value) -> bool) -> Option<Npc> {
        let g = &self.world.g;
        let map = text(&self.world.me(), "map").to_string();
        for n in g.other["maps"][&map]["npcs"].as_array().into_iter().flatten() {
            let pos = if n["position"].is_array() { &n["position"] } else { &n["positions"][0] };
            let id = n["id"].as_str().unwrap_or_default();
            let def = &g.other["npcs"][id];
            if let (Some(x), Some(y)) = (pos[0].as_f64(), pos[1].as_f64()) {
                if def.is_object() && test(def) {
                    return Some(Npc { id: id.to_string(), x, y });
                }
            }
        }
        None
    }
    // endregion find

    // region shop
    /// Buy from an NPC within 400 px that sells the item. The answer:
    /// `buy_success` {cost, num, name, q}, or a failure: "distance" (too far),
    /// "buy_cost" (not enough gold), "buy_cant_space" (node/server.js:8409-8461).
    pub async fn buy(&self, name: &str, quantity: u64) -> Result<Option<GameResponse>> {
        self.act.request("buy", json!({"name": name, "quantity": quantity}), None, None).await
    }

    /// Sell to any shop NPC within 400 px for 60 % of G.items[name].g (1 gold
    /// for a gift item). The answer: `gold_received` {gold} (node/server.js:8046-8096).
    pub async fn sell(&self, num: usize, quantity: u64) -> Result<Option<GameResponse>> {
        self.act.request("sell", json!({"num": num, "quantity": quantity}), None, None).await
    }
    // endregion shop

    // region equip
    /// Put the item of slot `num` on. Without `slot`, the server chooses one
    /// from the item type. The old item goes back to the inventory. The
    /// answer is {response: "data", slot} on success (node/server.js:7643-7915).
    pub async fn equip(&self, num: usize, slot: Option<&str>) -> Result<Option<GameResponse>> {
        let payload = match slot {
            Some(s) => json!({"num": num, "slot": s}),
            None => json!({"num": num}),
        };
        self.act.request("equip", payload, None, None).await
    }

    pub async fn unequip(&self, slot: &str) -> Result<Option<GameResponse>> {
        self.act.request("unequip", json!({"slot": slot}), None, None).await
    }

    /// Equip each inventory item that is better than what we wear: the slot
    /// is empty, or it holds the same item at a lower level. A simple rule;
    /// the game guide ("Gear is more important than level") compares stats.
    /// Returns "<item>: <slot>" for each item that went on.
    pub async fn equip_better(&self) -> Result<Vec<String>> {
        let mut done = Vec::new();
        let count = self.list().len();
        for n in 0..count {
            // Read again each time: each equip changes the inventory and slots.
            let (it, slots) = {
                let w = self.world.lock();
                let it = w.me.get("items").and_then(|i| i.get(n)).cloned().unwrap_or(Value::Null);
                (it, w.me.get("slots").cloned().unwrap_or(Value::Null))
            };
            let name = it["name"].as_str().unwrap_or_default();
            let Some(def) = self.world.g.items.get(name) else { continue };
            let Some(names) = slots_for(&def.kind) else { continue };
            let level = it["level"].as_u64().unwrap_or(0);
            let slot = names.iter().find(|s| slots[**s].is_null()).or_else(|| {
                names.iter().find(|s| slots[**s]["name"] == name && slots[**s]["level"].as_u64().unwrap_or(0) < level)
            });
            let Some(slot) = slot else { continue };
            if let Some(r) = self.equip(n, Some(slot)).await? {
                if !r.failed {
                    done.push(format!("{name}: {slot}")); // "cant_equip": not for our class
                }
            }
        }
        Ok(done)
    }
    // endregion equip

    // region send
    /// Give items to another character on our map within 400 px. The answer:
    /// `item_sent`, or "distance", "send_no_space" (node/server.js:8463-8560).
    pub async fn send_item(&self, name: &str, num: usize, quantity: u64) -> Result<Option<GameResponse>> {
        self.act.request("send", json!({"name": name, "num": num, "q": quantity}), None, None).await
    }

    /// Give gold. Between characters of one account the receiver gets all of
    /// it; to another account, 2.5 % less (node/server.js:8590-8600).
    pub async fn send_gold(&self, name: &str, gold: u64) -> Result<Option<GameResponse>> {
        self.act.request("send", json!({"name": name, "gold": gold}), None, None).await
    }
    // endregion send

    // region bank
    /// Gold into the bank. Only inside the bank (a map with `mount`, which
    /// Travel::go_to_map("bank") reaches); elsewhere: "bank_unavailable". The
    /// first answer has place "bank" and the `gold` moved (node/server.js:9257-9282).
    pub async fn deposit(&self, gold: u64) -> Result<Option<GameResponse>> {
        self.act.request("bank", json!({"operation": "deposit", "amount": gold}), None, None).await
    }

    pub async fn withdraw(&self, gold: u64) -> Result<Option<GameResponse>> {
        self.act.request("bank", json!({"operation": "withdraw", "amount": gold}), None, None).await
    }
    // endregion bank

    // region upgrade
    /// Upgrade the item in slot `item_num` with the scroll in `scroll_num`, at
    /// the upgrade NPC (within 400 px). `clevel` must be the item's level now,
    /// or the server says "upgrade_mismatch" (node/server.js:7166-7168).
    /// - calculate: true -> the answer is `upgrade_chance` {chance}; nothing is used.
    /// - calculate: false -> the scroll is used, the slot holds a "placeholder",
    ///   and the result comes later as a hitchhiker: `upgrade_success` or
    ///   `upgrade_fail` {level, num} (node/server.js:14920-14945). On a fail
    ///   the item is gone.
    ///
    /// A failure before the roll is a bare string ("upgrade_no_scroll") or an
    /// object with place "upgrade" ("distance"). None: no answer in time.
    pub async fn upgrade(&self, item_num: usize, scroll_num: usize, calculate: bool) -> Result<Option<GameResponse>> {
        let clevel = self.list().get(item_num).map_or(0, |it| it["level"].as_u64().unwrap_or(0));
        let mut payload = json!({"item_num": item_num, "scroll_num": scroll_num, "clevel": clevel});
        if calculate {
            payload["calculate"] = json!(true);
        }
        // 30 s: the roll of +N takes 0.5 x N x sqrt(N) s, about 9 s at +7.
        self.roll("upgrade", payload, if calculate { 2000 } else { 30_000 }).await
    }

    /// Combine three identical items (same name and level) with a compound
    /// scroll. The same answers as upgrade, with "compound" in place of
    /// "upgrade". The roll takes 10 s (node/server.js:7037). On a success the
    /// item is in nums[0], one level higher; the other two slots are empty.
    pub async fn compound(&self, nums: [usize; 3], scroll_num: usize, calculate: bool) -> Result<Option<GameResponse>> {
        let clevel = self.list().get(nums[0]).map_or(0, |it| it["level"].as_u64().unwrap_or(0));
        let mut payload = json!({"items": nums, "scroll_num": scroll_num, "clevel": clevel});
        if calculate {
            payload["calculate"] = json!(true);
        }
        self.roll("compound", payload, if calculate { 2000 } else { 30_000 }).await
    }

    /// Send the event, then wait for the first game_response about it: an
    /// object with this `place`, or a response that starts with "<event>_"
    /// (the bare-string failures and the late hitchhiker results).
    async fn roll(&self, event: &str, payload: Value, timeout_ms: u64) -> Result<Option<GameResponse>> {
        let since = self.log.lock().unwrap_or_else(|p| p.into_inner()).seq; // only answers after the emit
        self.budget.emit(event, payload).await?;
        let prefix = format!("{event}_");
        let end = Instant::now() + Duration::from_millis(timeout_ms);
        while Instant::now() < end {
            {
                let log = self.log.lock().unwrap_or_else(|p| p.into_inner());
                let hit = log.list.iter().find(|(seq, r)| {
                    *seq > since && (r.place.as_deref() == Some(event) || r.response.starts_with(&prefix))
                });
                if let Some((_, r)) = hit {
                    return Ok(Some(r.clone()));
                }
            } // the lock ends before the sleep
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
        Ok(None)
    }
    // endregion upgrade
}

/// A number field of a response (chance, cost, gold, num, q), 0 when missing.
pub fn field(r: &GameResponse, key: &str) -> f64 {
    r.raw[key].as_f64().unwrap_or(0.0)
}

/// Our gold now.
pub fn gold(world: &World) -> f64 {
    num(&world.me(), "gold")
}
