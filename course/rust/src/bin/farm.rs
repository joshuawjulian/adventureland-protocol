// farm.rs: a farming bot. It kills monsters of the Mainland ladder, loots,
// heals, respawns, leaves jail, and reconnects with the course's reconnect
// rule.
//   Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger cargo run --bin farm -- [seconds]
//   seconds: stop after this time (the tests use 25). Without it: until Ctrl-C.
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use albot::bot::{reconnect_delay_ms, Bot};
use albot::farmer::Farmer;
use albot::travel::Travel;
use albot::world::{num, text, Entity};
use albot::Result;

const TICK: Duration = Duration::from_millis(100); // one decision every 100 ms: fast enough, and cheap in call-cost
const STABLE: Duration = Duration::from_secs(5 * 60); // after a session of 5 min, the reconnect wait starts again at the first value

// region stop
/// Set by Ctrl-C: finish this tick, close the socket, print the summary. A
/// second Ctrl-C stops at once.
static STOP: AtomicBool = AtomicBool::new(false);

fn stopping() -> bool {
    STOP.load(Ordering::SeqCst)
}

/// Listen for Ctrl-C on its own task (tokio::signal::ctrl_c works on Linux,
/// macOS and Windows).
fn watch_ctrl_c() {
    tokio::spawn(async {
        loop {
            if tokio::signal::ctrl_c().await.is_err() {
                return;
            }
            if stopping() {
                std::process::exit(1);
            }
            STOP.store(true, Ordering::SeqCst);
            println!("stopping (press Ctrl-C again to stop at once)");
        }
    });
}

/// A sleep that ends early when we stop.
async fn wait(ms: u64) {
    let end = Instant::now() + Duration::from_millis(ms);
    while !stopping() && Instant::now() < end {
        tokio::time::sleep(end.saturating_duration_since(Instant::now()).min(Duration::from_millis(200))).await;
    }
}
// endregion stop

#[tokio::main]
async fn main() -> Result<()> {
    watch_ctrl_c();
    let seconds: u64 = std::env::args().nth(1).and_then(|a| a.parse().ok()).unwrap_or(0);
    let started = Instant::now();
    let end_at = (seconds > 0).then(|| started + Duration::from_secs(seconds));
    let over = || end_at.is_some_and(|end| Instant::now() >= end);
    let mut kills = 0;
    let mut attempt = 0; // failed tries in a row, for reconnect_delay_ms
    let mut last = Entity::new(); // our character in the last session

    // region session
    while !stopping() && !over() {
        // 1. Connect. A failure (the server is full, the save of the last
        //    session still runs, ...) waits as the reconnect rule says, then tries again.
        let bot = match Bot::connect().await {
            Ok(bot) => bot,
            Err(e) => {
                let ms = reconnect_delay_ms(attempt);
                attempt += 1;
                println!("connect failed: {e}; try again in {} s", ms / 1000);
                wait(ms).await;
                continue;
            }
        };
        let session = Instant::now();
        let me = bot.world.me();
        println!(
            "in game as {} ({}, level {}) on {} at {:.0},{:.0}",
            text(&me, "id"), text(&me, "ctype"), num(&me, "level"), text(&me, "map"), num(&me, "x"), num(&me, "y")
        );

        // 2. Play until we stop, the time is over, or the socket closes.
        //    AlSocket's local `disconnect` event has the reason; a send on a
        //    closed socket is an error, so the Err below is the same case.
        let lost: Arc<Mutex<Option<String>>> = Arc::default();
        let l = lost.clone();
        bot.world.listen("disconnect", move |_, reason| {
            *l.lock().unwrap() = Some(reason.as_str().unwrap_or("disconnect").to_string());
        });
        bot.world.listen("disconnect_reason", |_, reason| println!("the server says: {reason}")); // "limitdc", "limits", ...
        let travel = Travel::new(&bot.world, &bot.act);
        let farmer = Farmer::new(&bot.world, &bot.act, &bot.cooldowns, &travel, "");
        let is_lost = || lost.lock().unwrap().is_some();
        while !stopping() && !is_lost() && !over() {
            tokio::time::sleep(TICK).await;
            if let Err(e) = farmer.tick().await {
                lost.lock().unwrap().get_or_insert(e.to_string());
                break;
            }
            farmer.next_type(); // a stronger monster when this one is too easy
        }
        kills += farmer.kills();
        last = bot.world.me();
        // Read the reason BEFORE close(): our own close also sends the local
        // `disconnect` event, and that is not a lost connection.
        let reason = lost.lock().unwrap().clone();
        let _ = bot.close().await;
        let Some(reason) = reason else { break }; // we stopped, or the time is over

        // 3. The reconnect rule: wait, then make a new socket and a full handshake.
        if session.elapsed() >= STABLE {
            attempt = 0;
        }
        let ms = reconnect_delay_ms(attempt);
        attempt += 1;
        println!("disconnected: {reason}; reconnect in {} s", ms / 1000);
        wait(ms).await;
    }
    // endregion session

    println!(
        "farmed {} s: {kills} kill(s), level {}, {:.0} gold",
        started.elapsed().as_secs_f64().round(), num(&last, "level"), num(&last, "gold")
    );
    println!("OK");
    Ok(())
}
