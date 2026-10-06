// gear-up.rs: upgrades a coat to +3 and compounds rings in groups of three,
// with the stop rule of the game guide. It farms first until it has a chest
// (gold and rings).
//   Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger cargo run --bin gear-up
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use serde_json::Value;

use albot::bot::Bot;
use albot::farmer::Farmer;
use albot::gdata::GData;
use albot::items::{field, Items, Npc, NPC_DIST};
use albot::travel::Travel;
use albot::world::{num, text};
use albot::Result;

const TICK: Duration = Duration::from_millis(100);

// region rules
// The stop rule (the game guide, "A progression plan"): take a piece to +3
// with no spare copy. Above +3 the chance falls (70 % for +4), so stop and
// use spares ("Step 2"). Also stop when the server's chance, with grace, is
// below 90 %: then a failure is too likely for an item that we wear.
const ITEM: &str = "coat"; // 6,000 gold at Gabriel (`basics`)
const TARGET_LEVEL: u64 = 3;
const MIN_CHANCE: f64 = 0.9;
// Jewelry: compound groups of three while the chance is at least 90 %. For
// most jewelry that is +0 -> +1 only (99 %); +2 is 75 %.
// endregion rules

/// The parts that the steps below use.
struct Kit {
    bot: Bot,
    travel: Travel,
    items: Items,
}

/// Walk to within `within` px of an NPC (or of a point). Say so only when we must walk.
async fn go_near(k: &Kit, npc: Option<Npc>, within: f64) -> Result<()> {
    let npc = npc.ok_or("no such NPC on this map")?;
    k.bot.world.advance();
    let me = k.bot.world.me();
    if (num(&me, "x") - npc.x).hypot(num(&me, "y") - npc.y) <= within {
        return Ok(());
    }
    println!("walk to {} at {:.0},{:.0}", npc.id, npc.x, npc.y);
    if !k.travel.walk_to(npc.x, npc.y).await? {
        return Err(format!("could not walk to {}", npc.id).into());
    }
    Ok(())
}

/// Buy one `name` and return its slot number.
async fn buy_one(k: &Kit, name: &str) -> Result<usize> {
    go_near(k, k.items.npc_selling(name), NPC_DIST).await?;
    match k.items.buy(name, 1).await? {
        Some(r) if !r.failed => {
            println!("buy {name} x1: {} gold", field(&r, "cost"));
            Ok(field(&r, "num") as usize)
        }
        r => Err(format!("buy {name}: {}", r.map_or("no answer".into(), |r| r.response)).into()),
    }
}

/// The level of an inventory item (0 when it has none).
fn level(items: &[Value], n: usize) -> u64 {
    items.get(n).map_or(0, |it| it["level"].as_u64().unwrap_or(0))
}

// region compound-loop
/// The first group of three: same name, same level, an item that compounds
/// (G `compound`).
fn find_group(g: &GData, items: &[Value]) -> Option<[usize; 3]> {
    let mut groups: HashMap<(String, u64), Vec<usize>> = HashMap::new();
    let mut order = Vec::new(); // in inventory order, so the result does not depend on hashing
    for (n, it) in items.iter().enumerate() {
        let name = it["name"].as_str().unwrap_or_default();
        let Some(def) = g.items.get(name) else { continue };
        if !it["l"].is_null() || def.compound.is_none() {
            continue;
        }
        let key = (name.to_string(), level(items, n));
        if !groups.contains_key(&key) {
            order.push(key.clone());
        }
        groups.entry(key).or_default().push(n);
    }
    order.iter().map(|key| &groups[key]).find(|v| v.len() >= 3).map(|v| [v[0], v[1], v[2]])
}

async fn compound_loop(k: &Kit) -> Result<()> {
    while let Some(group) = find_group(&k.bot.g, &k.items.list()) {
        let list = k.items.list();
        let name = list[group[0]]["name"].as_str().unwrap_or_default().to_string();
        let lvl = level(&list, group[0]);
        let scroll = match k.items.find("cscroll0", None) {
            Some(s) => s,
            None => buy_one(k, "cscroll0").await?,
        };
        let calc = k.items.compound(group, scroll, true).await?;
        let chance = calc.as_ref().filter(|c| !c.failed && c.response == "compound_chance").map(|c| field(c, "chance"));
        let Some(chance) = chance.filter(|c| *c >= MIN_CHANCE) else {
            let why = chance.map_or(calc.map_or("no answer".into(), |c| c.response), |c| format!("{c:.2}"));
            println!("stop: compound {name} +{lvl}: {why}");
            break;
        };
        let r = k.items.compound(group, scroll, false).await?;
        let result = match r.as_ref().map(|r| r.response.as_str()) {
            Some("compound_success") => "success".to_string(),
            Some("compound_fail") => "fail".to_string(),
            Some(other) => other.to_string(),
            None => "no answer".to_string(),
        };
        println!("compound {name} +{lvl} x3 -> +{}: {result} (chance {chance:.2})", lvl + 1);
        if result != "success" && result != "fail" {
            break;
        }
    }
    Ok(())
}
// endregion compound-loop

#[tokio::main]
async fn main() -> Result<()> {
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

    // 1. Farm until one chest opened: the first chest brings gold and rings.
    let chests = Arc::new(AtomicU64::new(0));
    let c = chests.clone();
    k.bot.world.listen("chest_opened", move |_, r| {
        if r["gone"] != true {
            c.fetch_add(1, Ordering::SeqCst);
        }
    });
    while chests.load(Ordering::SeqCst) == 0 {
        tokio::time::sleep(TICK).await;
        farmer.tick().await?;
    }

    // 2. The item to upgrade.
    let mut num_ = match k.items.find(ITEM, None) {
        Some(n) => Some(n),
        None => Some(buy_one(&k, ITEM).await?),
    };

    // 3. Stand where both Lucas (scrolls) and Cue (upgrade, compound) are
    //    within 400 px: the middle of the two (about 140 px from each).
    let (Some(lucas), Some(cue)) = (k.items.npc_selling("scroll0"), k.items.npc_with_role("newupgrade")) else {
        return Err("no scroll shop or upgrade NPC on this map".into());
    };
    let spot = Npc { id: "scrolls and newupgrade".into(), x: ((lucas.x + cue.x) / 2.0).round(), y: ((lucas.y + cue.y) / 2.0).round() };
    go_near(&k, Some(spot), 20.0).await?; // 20 px: near the middle, so that both stay within 400 px

    // region upgrade-loop
    while let Some(n) = num_.filter(|n| level(&k.items.list(), *n) < TARGET_LEVEL) {
        let lvl = level(&k.items.list(), n);
        let scroll = match k.items.find("scroll0", None) {
            Some(s) => s,
            None => buy_one(&k, "scroll0").await?,
        };
        // Ask first: the chance includes grace, which only the server knows.
        let calc = k.items.upgrade(n, scroll, true).await?;
        let Some(calc) = calc.filter(|c| !c.failed && c.response == "upgrade_chance") else {
            println!("upgrade {ITEM}: no chance in the answer");
            break;
        };
        let chance = field(&calc, "chance");
        if chance < MIN_CHANCE {
            println!("stop: the chance for +{} is {chance:.2}", lvl + 1);
            break;
        }
        let r = k.items.upgrade(n, scroll, false).await?;
        let result = match r.as_ref().map(|r| r.response.as_str()) {
            Some("upgrade_success") => "success".to_string(),
            Some("upgrade_fail") => "fail".to_string(),
            Some(other) => other.to_string(),
            None => "no answer".to_string(),
        };
        println!("upgrade {ITEM} +{lvl} -> +{}: {result} (chance {chance:.2})", lvl + 1);
        if result != "success" {
            break; // a fail destroys the item
        }
        num_ = r.map(|r| r.raw["num"].as_u64().map_or(n, |v| v as usize));
    }
    // endregion upgrade-loop

    compound_loop(&k).await?;

    // 4. Wear the results.
    for line in k.items.equip_better().await? {
        println!("equip {line}");
    }
    let me = k.bot.world.me();
    let show = |s: &str| {
        let it = &me["slots"][s];
        if it.is_null() { "-".to_string() } else { format!("{} +{}", it["name"].as_str().unwrap_or_default(), it["level"].as_u64().unwrap_or(0)) }
    };
    println!("gear: chest {}, ring1 {}, ring2 {}, belt {}", show("chest"), show("ring1"), show("ring2"), show("belt"));
    k.bot.close().await?;
    println!("OK");
    Ok(())
}
