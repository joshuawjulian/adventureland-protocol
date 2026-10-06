// first-kill.rs: the checkpoint of Part 2. Enter the game, heal when hp is
// low, walk into range of the nearest goo, attack it until it dies, open its
// chest, and print the xp.
//   Run: AL_AUTH=<user>-<auth> AL_CHARACTER=<name> cargo run --bin first-kill
//   AL_SERVER (for example EUI) is optional: empty means the first server.
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use albot::bot::Bot;
use albot::world::{num, text, Entity};
use albot::Result;

// HARD-CODED: the limits of this program.
const TICK: Duration = Duration::from_millis(100); // one loop step: 10 decisions per second
const GIVE_UP: Duration = Duration::from_secs(90); // a goo dies in much less time
const HEAL_BELOW: f64 = 0.7; // heal under 70 % of max_hp
const CHEST_WAIT: Duration = Duration::from_secs(3); // `drop` comes with the kill; 3 s is plenty

/// "<x>,<y>", rounded.
fn at(e: &Entity) -> String {
    format!("{:.0},{:.0}", num(e, "x"), num(e, "y"))
}

/// True for a dead character: `rip` is true, or the name of a gravestone skin.
fn is_dead(me: &Entity) -> bool {
    me.get("rip").is_some_and(|r| r.as_bool() != Some(false) && !r.is_null())
}

#[tokio::main]
async fn main() -> Result<()> {
    let bot = Bot::connect().await?;
    let (world, act) = (&bot.world, &bot.act);
    let me = world.me();
    println!(
        "in game as {} ({}, level {}) on {} at {}",
        text(&me, "id"), text(&me, "ctype"), num(&me, "level"), text(&me, "map"), at(&me)
    );

    let result = hunt(&bot).await;
    if result.is_ok() {
        // The chest: `drop` comes with the kill. Wait for it a short time.
        let since = Instant::now();
        while world.lock().chests.is_empty() && since.elapsed() < CHEST_WAIT {
            tokio::time::sleep(TICK).await;
        }
        let ids: Vec<String> = world.lock().chests.keys().cloned().collect();
        for id in ids {
            if let Some(r) = act.open_chest(&id).await? {
                let items = r["items"].as_array().map_or(0, |a| a.len()); // no `items`: none
                println!("chest {id}: +{} gold, {items} item(s)", r["gold"].as_f64().unwrap_or(0.0));
            }
        }
        let me = world.me();
        println!("xp: {}/{}, level {}", num(&me, "xp"), num(&me, "max_xp"), num(&me, "level"));
        println!("OK");
    }
    bot.close().await?;
    result
}

/// Heal, find a goo, walk into range, attack, until the goo is dead.
async fn hunt(bot: &Bot) -> Result<()> {
    let (world, act, cooldowns) = (&bot.world, &bot.act, &bot.cooldowns);
    let mut target: Option<String> = None; // the goo's id, once we chose one
    // Set by a handler on the dispatcher task, read by this loop.
    let killed = Arc::new(AtomicBool::new(false));
    let target_id = Arc::new(std::sync::Mutex::new(String::new()));
    for event in ["death", "hit"] {
        let (killed, target_id) = (killed.clone(), target_id.clone());
        // `death` {id}, or a `hit` with `kill: true` (node/server.js:4343).
        world.listen(event, move |_, d| {
            let ours = d["id"].as_str() == Some(target_id.lock().unwrap().as_str());
            if ours && (event == "death" || d["kill"] == true) {
                killed.store(true, Ordering::SeqCst);
            }
        });
    }

    let deadline = Instant::now() + GIVE_UP;
    while !killed.load(Ordering::SeqCst) {
        if Instant::now() > deadline {
            return Err("no kill in 90 s".into());
        }
        tokio::time::sleep(TICK).await;
        world.advance(); // positions now, not at the last update
        let me = world.me();

        if is_dead(&me) {
            println!("died; respawn in {} s", act.respawn_ms_left().div_ceil(1000));
            if act.respawn().await? {
                println!("respawned at {}", at(&world.me()));
            }
            continue;
        }

        // 1. Heal first: the test character starts with 40 % hp.
        if num(&me, "hp") < HEAL_BELOW * num(&me, "max_hp") && cooldowns.ready("potion") {
            if act.heal("hp").await? {
                let me = world.me(); // the `player` update came before the reply
                println!("heal hp: {:.0}/{:.0}", num(&me, "hp"), num(&me, "max_hp"));
            }
            continue;
        }

        // 2. Choose the nearest goo, one time.
        let id = match &target {
            Some(id) => id.clone(),
            None => {
                let Some(goo) = world.nearest_monster(Some("goo")) else { continue };
                let id = text(&goo, "id").to_string();
                println!("target: goo {id} at {}", at(&goo));
                *target_id.lock().unwrap() = id.clone();
                target = Some(id.clone());
                id
            }
        };
        let Some(goo) = world.lock().monsters.get(&id).cloned() else {
            continue; // out of sight for now (the kill check above ends the loop when it died)
        };

        // 3. Out of range: walk to a point `range - 10` px from the goo, on the
        //    line from us to it. 10 px: room for the goo's own steps.
        let range = num(&me, "range");
        if world.distance(&me, &goo) > range {
            let (mx, my, gx, gy) = (num(&me, "x"), num(&me, "y"), num(&goo, "x"), num(&goo, "y"));
            let far = (gx - mx).hypot(gy - my).max(1.0);
            let keep = (range - 10.0).max(0.0);
            act.move_to(gx + (mx - gx) / far * keep, gy + (my - gy) / far * keep).await?;
            continue;
        }

        // 4. In range: attack when the attack cooldown is over.
        if cooldowns.ready("attack") {
            act.attack(&id).await?;
        }
    }
    println!("killed goo {}", target.unwrap_or_default());
    Ok(())
}
