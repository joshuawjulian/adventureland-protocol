// party-merchant.rs: three fighters and one merchant in one program. The
// fighters farm in a party. The merchant walks to them, takes their loot and
// gold, sells the loot in the town and puts the gold in the bank.
//   Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyWarrior cargo run --bin party-merchant -- [trips]
//   AL_CHARACTER is the leader. The program adds the next two fighters of
//   your character list, and your first merchant.
//   trips: stop after this many merchant trips (the tests use 1). Without it: until Ctrl-C.
// Make a merchant first, if you have none:
//   cargo run --bin party-merchant -- --create-merchant MyMerchant
use std::panic::AssertUnwindSafe;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use futures_util::FutureExt; // catch_unwind() on a future
use serde_json::Value;
use tokio::task::{JoinError, JoinSet};

use albot::api::{find_character, find_server, login, servers_and_characters};
use albot::farmer::Farmer;
use albot::gdata::{load_g, GData};
use albot::items::{field, is_loot, Items};
use albot::party::{connect_member, create_character, Member, Party};
use albot::travel::Travel;
use albot::world::{num, text};
use albot::Result;

const TICK: Duration = Duration::from_millis(100);

// region rules
const FIGHTERS: usize = 3; // the live limit: 3 characters that fight, plus merchants (game guide, "Many characters and bots")
const GIVE_DIST: f64 = 300.0; // `send` works within 400 px on the same map (node/server.js:8463-8560)
const FIGHTER_GOLD: f64 = 20000.0; // a fighter keeps this much gold for potions, and gives the rest
const MERCHANT_GOLD: f64 = 50000.0; // the merchant keeps this much, and banks the rest

/// A fighter keeps only its potions. Everything else goes to the merchant:
/// loot to sell, and jewelry that the merchant compounds later.
fn give(g: &GData, it: &Value) -> bool {
    let name = it["name"].as_str().unwrap_or_default();
    !name.is_empty() && name != "placeholder" && it["l"].is_null() && g.items.get(name).is_some_and(|d| d.kind != "pot")
}
// endregion rules

/// Set by Ctrl-C, and by the end of the last trip: the loops end.
static STOP: AtomicBool = AtomicBool::new(false);

fn stopping() -> bool {
    STOP.load(Ordering::SeqCst)
}

/// One character and its tools.
struct Crew {
    m: Member,
    travel: Travel,
    items: Items,
    party: Party,
    farmer: Option<Farmer>, // only fighters farm
}

/// "<x>,<y>", rounded.
fn at(world: &albot::world::World) -> String {
    let me = world.me();
    format!("{:.0},{:.0}", num(&me, "x"), num(&me, "y"))
}

/// What a fighter task gives back: its name, and its result or its panic.
type Ended = std::result::Result<(String, std::thread::Result<Result<()>>), JoinError>;

/// Why a fighter ended, or None when it ended because we stop (Ok).
fn why_ended(ended: Ended) -> Option<String> {
    match ended {
        Ok((_, Ok(Ok(())))) => None,
        Ok((name, Ok(Err(e)))) => Some(format!("{name} stopped: {e}")),
        Ok((name, Err(panic))) => {
            // A panic payload is a &str or a String in practice.
            let text = panic.downcast_ref::<&str>().map(|s| s.to_string()).or_else(|| panic.downcast_ref::<String>().cloned());
            Some(format!("{name} panicked: {}", text.unwrap_or_else(|| "?".into())))
        }
        Err(e) => Some(format!("a fighter task failed: {e}")), // aborted: not in this program
    }
}

// region fighter
/// A fighter farms. When the merchant is near, it gives its loot and gold.
async fn fighter_loop(f: Arc<Crew>, merchant: String) -> Result<()> {
    let world = &f.m.world;
    let g = &f.m.g;
    while !stopping() {
        tokio::time::sleep(TICK).await;
        if let Some(farmer) = &f.farmer {
            farmer.tick().await?;
        }
        world.advance();
        let me = world.me();
        let near = world.lock().players.get(&merchant).cloned(); // the merchant, if it is in our view
        if !near.is_some_and(|m| world.distance(&me, &m) <= GIVE_DIST) {
            continue;
        }
        let mut n = 0;
        for (slot, it) in f.items.list().iter().enumerate() {
            if !give(g, it) {
                continue;
            }
            if f.items.send_item(&merchant, slot, it["q"].as_u64().unwrap_or(1)).await?.is_some_and(|r| !r.failed) {
                n += 1;
            }
        }
        // Gold only above twice the reserve: not a `send` for each small chest.
        let gold = num(&world.me(), "gold");
        let gold = if gold > 2.0 * FIGHTER_GOLD { gold - FIGHTER_GOLD } else { 0.0 };
        if gold > 0.0 {
            f.items.send_gold(&merchant, gold as u64).await?;
        }
        if n > 0 || gold > 0.0 {
            println!("{}: gave {n} item(s) and {gold:.0} gold to {merchant}", f.m.name);
        }
    }
    Ok(())
}
// endregion fighter

// region merchant
/// Has this fighter something to give?
fn has_loot(f: &Crew) -> bool {
    let me = f.m.world.me();
    me["items"].as_array().is_some_and(|items| items.iter().any(|it| give(&f.m.g, it)))
}

/// The merchant: wait for loot, collect it, sell it, bank the gold.
async fn merchant_trip(crew: &[Arc<Crew>]) -> Result<bool> {
    let (fighters, merchant) = crew.split_at(crew.len() - 1);
    let merchant = &merchant[0];
    let name = &merchant.m.name;
    // 1. Wait until a fighter has something to give, or until the merchant holds loot.
    // The merchant holds loot when a walk of the last trip failed after it collected: then go
    // on and sell it. Without this, the wait never ends: the fighters gave all already.
    let holds_loot = || merchant.items.list().iter().any(|it| is_loot(&merchant.m.g, it));
    while !stopping() && !holds_loot() && !fighters.iter().any(|f| has_loot(f)) {
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
    // 2. Go to each fighter with loot, and wait (10 s at most) until it gave all.
    for f in fighters {
        if stopping() || !has_loot(f) {
            continue;
        }
        let fm = f.m.world.me();
        println!("{name}: walk to {} at {}", f.m.name, at(&f.m.world));
        merchant.travel.walk_to(num(&fm, "x"), num(&fm, "y")).await?;
        for _ in 0..50 {
            if !has_loot(f) {
                break;
            }
            tokio::time::sleep(Duration::from_millis(200)).await;
        }
    }
    // 3. Sell the loot in the town. Keep the jewelry: three of a kind compound.
    let shop = merchant.items.npc_selling("hpot0").ok_or("no shop on this map")?;
    println!("{name}: walk to {} at {:.0},{:.0}", shop.id, shop.x, shop.y);
    if !merchant.travel.walk_to(shop.x, shop.y).await? {
        return Ok(false);
    }
    let (mut sold, mut gold) = (0, 0.0);
    for (slot, it) in merchant.items.list().iter().enumerate() {
        if !is_loot(&merchant.m.g, it) {
            continue;
        }
        if let Some(r) = merchant.items.sell(slot, it["q"].as_u64().unwrap_or(1)).await? {
            if !r.failed {
                sold += 1;
                gold += field(&r, "gold");
            }
        }
    }
    println!("{name}: sold {sold} item(s): +{gold:.0} gold");
    // 4. The bank: the door is north of the town. Deposit, then go back out.
    if !merchant.travel.go_to_map("bank").await? {
        return Ok(false);
    }
    let amount = (num(&merchant.m.world.me(), "gold") - MERCHANT_GOLD).max(0.0);
    let r = merchant.items.deposit(amount as u64).await?;
    println!("{name}: in the bank: deposited {:.0} gold", r.filter(|r| !r.failed).map_or(0.0, |r| field(&r, "gold")));
    if !merchant.travel.go_to_map("main").await? {
        return Ok(false);
    }
    println!("{name}: back on main at {}", at(&merchant.m.world));
    Ok(true)
}
// endregion merchant

#[tokio::main]
async fn main() -> Result<()> {
    tokio::spawn(async {
        if tokio::signal::ctrl_c().await.is_ok() {
            STOP.store(true, Ordering::SeqCst);
        }
    });

    // region choose
    let auth = login().await?;
    let lists = servers_and_characters(&auth).await?;
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).map(String::as_str) == Some("--create-merchant") {
        let name = args.get(2).cloned().unwrap_or_default();
        create_character(&auth, &name, "merchant").await?;
        println!("created the merchant {name}. Run the program again without --create-merchant.");
        return Ok(());
    }
    let trips: u64 = args.get(1).and_then(|a| a.parse().ok()).unwrap_or(0);
    let server = find_server(&lists.servers, None)?; // AL_SERVER
    let leader = find_character(&lists.characters, None)?; // AL_CHARACTER
    if leader.ctype == "merchant" {
        return Err("AL_CHARACTER must be a fighter: it leads the party".into());
    }
    let mut fighters = vec![leader.clone()];
    fighters.extend(lists.characters.iter().filter(|c| c.ctype != "merchant" && c.name != leader.name).cloned());
    fighters.truncate(FIGHTERS);
    let merchant_character = lists
        .characters
        .iter()
        .find(|c| c.ctype == "merchant")
        .cloned()
        .ok_or("no merchant on this account: run with --create-merchant <Name> first")?;
    let names: Vec<&str> = fighters.iter().map(|c| c.name.as_str()).collect();
    println!("team: {}; merchant: {}", names.join(", "), merchant_character.name);
    // endregion choose

    // region connect
    let g = Arc::new(load_g(None).await?); // one G for all four
    let mut crew: Vec<Arc<Crew>> = Vec::new();
    for c in fighters.iter().chain([&merchant_character]) {
        let m = connect_member(&auth, &server, c, g.clone()).await?;
        let me = m.world.me();
        println!(
            "in game as {} ({}, level {}) on {} at {}",
            text(&me, "id"), text(&me, "ctype"), num(&me, "level"), text(&me, "map"), at(&m.world)
        );
        let travel = Travel::new(&m.world, &m.act);
        // Only fighters farm. (A Farmer also prints each chest that opens for us.)
        let farmer = (c.ctype != "merchant").then(|| Farmer::new(&m.world, &m.act, &m.cooldowns, &travel, &format!("{}: ", m.name)));
        let items = Items::new(&m.world, &m.act, &m.budget);
        let party = Party::new(&m.world, &m.act);
        crew.push(Arc::new(Crew { m, travel, items, party, farmer }));
    }
    let lead = crew[0].clone();
    let merchant_name = crew[crew.len() - 1].m.name.clone();
    // endregion connect

    // region party
    // The leader invites each one; each waits for its `invite`, then accepts.
    for c in &crew[1..] {
        lead.party.invite(&c.m.name).await?;
        if !c.party.wait_invite(&lead.m.name, 5000).await {
            return Err(format!("{} got no invitation", c.m.name).into());
        }
        match c.party.accept(&lead.m.name).await? {
            Some(r) if !r.failed => {}
            r => return Err(format!("{} could not join: {}", c.m.name, r.map_or("no answer".into(), |r| r.response)).into()),
        }
    }
    for _ in 0..50 {
        if lead.party.list().len() >= crew.len() {
            break;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    println!("party: {}", lead.party.list().join(", "));
    // endregion party

    // region run
    // Each fighter on its own task, in a JoinSet; the merchant on this one.
    // The loop also watches the fighters: if one ends while we play (an error,
    // a lost connection, a panic), it prints why at once and stops all.
    let mut fighting = JoinSet::new();
    for f in &crew[..crew.len() - 1] {
        let (f, merchant) = (f.clone(), merchant_name.clone());
        let name = f.m.name.clone();
        // catch_unwind: a panic becomes a value with the fighter's name, not
        // only a line on stderr and a JoinError without a name.
        fighting.spawn(async move { (name, AssertUnwindSafe(fighter_loop(f, merchant)).catch_unwind().await) });
    }
    let mut done = 0;
    let mut result = Ok(());
    while !stopping() && (trips == 0 || done < trips) {
        tokio::select! {
            trip = merchant_trip(&crew) => match trip {
                Ok(true) => done += 1,
                Ok(false) => {}
                Err(e) => {
                    result = Err(e);
                    break;
                }
            },
            // A fighter ended. Before the stop, that is a failure: report it
            // now and stop. (select! drops the merchant's trip at its .await.)
            Some(ended) = fighting.join_next() => {
                if let Some(why) = why_ended(ended) {
                    eprintln!("{why}; stopping the others");
                    result = Err(why.into());
                    break;
                }
            }
        }
    }
    STOP.store(true, Ordering::SeqCst); // the other fighters end their loops
    while let Some(ended) = fighting.join_next().await {
        if let Some(why) = why_ended(ended) {
            eprintln!("{why}");
        }
    }
    for c in &crew {
        let _ = c.m.close().await;
    }
    result?;
    println!("OK");
    Ok(())
    // endregion run
}
