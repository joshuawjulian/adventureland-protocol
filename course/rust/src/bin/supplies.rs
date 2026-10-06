// supplies.rs: a farming bot that looks after itself. After each chest it
// wears better gear; when potions or bag space run low, it walks to the town,
// sells the loot, buys potions and the basic armor, and goes back to farm.
//   Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger cargo run --bin supplies -- [trips]
//   trips: stop after this many town trips (the tests use 1). Without it: until Ctrl-C.
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use albot::bot::Bot;
use albot::farmer::Farmer;
use albot::items::{field, is_loot, Items, Npc, NPC_DIST};
use albot::travel::Travel;
use albot::world::{num, text};
use albot::Result;

const TICK: Duration = Duration::from_millis(100);

// region rules
// The restock rule (the game guide, "Your first hour" and "Inventory"):
const MIN_POTIONS: u64 = 20; // go to town below 20 hpot0 or 20 mpot0 ...
const MIN_FREE: i64 = 5; // ... or below 5 free inventory slots
const POTIONS: u64 = 50; // buy up to 50 of each (20 gold each: 2,000 gold for both)
const KEEP_GOLD: f64 = 2000.0; // never spend the potion money on armor ("Your first day", step 1)
/// The basic armor that a new character does not wear, from Gabriel (`basics`).
const ARMOR: &[&str] = &["gloves", "coat", "pants"];
// endregion rules

static STOP: AtomicBool = AtomicBool::new(false);

/// The parts that the town trip uses.
struct Kit {
    bot: Bot,
    travel: Travel,
    items: Items,
}

// region town
/// Walk to within NPC_DIST of an NPC. Say so only when we must walk.
async fn go_near(k: &Kit, npc: Option<Npc>) -> Result<bool> {
    let npc = npc.ok_or("no such NPC on this map")?;
    k.bot.world.advance();
    let me = k.bot.world.me();
    if (num(&me, "x") - npc.x).hypot(num(&me, "y") - npc.y) <= NPC_DIST {
        return Ok(true);
    }
    println!("walk to {} at {:.0},{:.0}", npc.id, npc.x, npc.y);
    k.travel.walk_to(npc.x, npc.y).await
}

/// Buy `quantity` of `name` from the NPC that sells it.
async fn shop(k: &Kit, name: &str, quantity: u64) -> Result<bool> {
    if !go_near(k, k.items.npc_selling(name)).await? {
        return Ok(false);
    }
    let r = k.items.buy(name, quantity).await?;
    match &r {
        Some(r) if !r.failed => println!("buy {name} x{}: {} gold", field(r, "q"), field(r, "cost")),
        Some(r) => println!("buy {name}: {}", r.response),
        None => println!("buy {name}: no answer"),
    }
    Ok(r.is_some_and(|r| !r.failed))
}

async fn town_trip(k: &Kit) -> Result<bool> {
    let g = &k.bot.g;
    // 1. Sell the loot to the potion shop (any shop buys any item).
    if !go_near(k, k.items.npc_selling("hpot0")).await? {
        return Ok(false);
    }
    for (n, it) in k.items.list().iter().enumerate() {
        if !is_loot(g, it) {
            continue;
        }
        if let Some(r) = k.items.sell(n, it["q"].as_u64().unwrap_or(1)).await? {
            if !r.failed {
                println!("sell {}: +{} gold", text(it.as_object().unwrap(), "name"), field(&r, "gold"));
            }
        }
    }
    // 2. Potions, up to POTIONS of each.
    for name in ["hpot0", "mpot0"] {
        let have = k.items.count(name);
        if have < POTIONS {
            shop(k, name, POTIONS - have).await?;
        }
    }
    // 3. The basic armor that we do not wear, while the gold lasts.
    for name in ARMOR {
        let def = &g.items[*name];
        let me = k.bot.world.me();
        // "gloves", "chest", "pants": the slot has the type's name.
        if !me["slots"][&def.kind].is_null() || num(&me, "gold") - def.g < KEEP_GOLD {
            continue;
        }
        shop(k, name, 1).await?;
    }
    for line in k.items.equip_better().await? {
        println!("equip {line}");
    }
    println!(
        "bag: {} hpot0, {} mpot0, {} free slot(s), {:.0} gold",
        k.items.count("hpot0"), k.items.count("mpot0"), k.items.free_slots(), num(&k.bot.world.me(), "gold")
    );
    Ok(true)
}
// endregion town

#[tokio::main]
async fn main() -> Result<()> {
    tokio::spawn(async {
        if tokio::signal::ctrl_c().await.is_ok() {
            STOP.store(true, Ordering::SeqCst);
        }
    });
    let trips: u64 = std::env::args().nth(1).and_then(|a| a.parse().ok()).unwrap_or(0);
    let bot = Bot::connect().await?;
    let me = bot.world.me();
    println!(
        "in game as {} ({}, level {}) on {} at {:.0},{:.0}",
        text(&me, "id"), text(&me, "ctype"), num(&me, "level"), text(&me, "map"), num(&me, "x"), num(&me, "y")
    );
    let travel = Travel::new(&bot.world, &bot.act);
    let items = Items::new(&bot.world, &bot.act, &bot.budget);
    let farmer = Farmer::new(&bot.world, &bot.act, &bot.cooldowns, &travel, "");
    let k = Kit { bot, travel, items };

    // region loop
    let chests = Arc::new(AtomicU64::new(0)); // chests opened so far
    let c = chests.clone();
    k.bot.world.listen("chest_opened", move |_, r| {
        if r["gone"] != true {
            c.fetch_add(1, Ordering::SeqCst);
        }
    });
    let mut seen = 0; // chests that we checked after
    let mut done = 0;
    while !STOP.load(Ordering::SeqCst) && (trips == 0 || done < trips) {
        tokio::time::sleep(TICK).await;
        farmer.tick().await?;
        if chests.load(Ordering::SeqCst) == seen {
            continue;
        }
        // After each chest: wear what is better, then check the supplies.
        seen = chests.load(Ordering::SeqCst);
        for line in k.items.equip_better().await? {
            println!("equip {line}");
        }
        let (hp, mp, free) = (k.items.count("hpot0"), k.items.count("mpot0"), k.items.free_slots());
        if hp >= MIN_POTIONS && mp >= MIN_POTIONS && free >= MIN_FREE {
            continue;
        }
        println!("supplies low: {hp} hpot0, {mp} mpot0, {free} free slot(s)");
        if town_trip(&k).await? {
            done += 1;
        }
        farmer.state().target = None; // choose again: the old target is far away now
    }
    // endregion loop

    k.bot.close().await?;
    println!("OK");
    Ok(())
}
