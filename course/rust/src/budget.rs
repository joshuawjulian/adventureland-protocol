// budget.rs: stay under the server's call-cost limit, so that it never kicks us.
//
// The server counts a "call-cost" per socket: each event costs 1, some cost
// more (EXTRA_COST). Over 200 in the last 4 s, it disconnects the socket
// (`limitdc`, node/server.js:4892-4962). Budget sends every event of the bot
// and waits when the last 4 s have no room.
//
// Concurrency: emit() runs on the program's tasks, and the `new_map` handler
// on the socket's dispatcher task. So the list of calls sits behind one lock,
// Arc<Mutex<...>>. No method holds it across an `.await`.

use std::collections::VecDeque;
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::{Duration, Instant};

use serde_json::Value;

use crate::alsocket::{AlSocket, Result};
use crate::world::World;

// region budget
/// The extra call-cost of some events (`CC`, node/server.js:242-258). All
/// other events have no extra cost.
pub const EXTRA_COST: &[(&str, f64)] = &[
    ("auth", 2.0),
    ("move", 1.5),
    ("players", 12.0),
    ("secondhands", 16.0),
    ("friend", 24.0),
    ("send_updates", 12.0),
    ("cruise", 10.0),
    ("random_look", 10.0),
    ("equip", 3.0),
    ("unequip", 6.0),
    ("tracker", 50.0),
    ("ccreport", 3.0),
];

/// 150 of the server's 200: the server also adds cost that we cannot see
/// (each `player` update that it sends back can add 1, node/server.js:4550-4592).
pub const LIMIT: f64 = 150.0;
/// The window of the server's count: 4 s (limits.calls, node/server.js:256-257).
pub const WINDOW_MS: u64 = 4000;

#[derive(Clone)]
pub struct Budget {
    sock: Arc<AlSocket>,
    calls: Arc<Mutex<VecDeque<(Instant, f64)>>>, // (when, cost), oldest first
}

impl Budget {
    pub fn new(sock: Arc<AlSocket>, world: &World) -> Budget {
        let budget = Budget { sock, calls: Arc::default() };
        // A map change costs 8 (add_call_cost(player, 8, "transport"), node/server.js:4726).
        let b = budget.clone();
        world.listen("new_map", move |_, _| b.lock().push_back((Instant::now(), 8.0)));
        budget
    }

    fn lock(&self) -> MutexGuard<'_, VecDeque<(Instant, f64)>> {
        let mut calls = self.calls.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        let window = Duration::from_millis(WINDOW_MS);
        while calls.front().is_some_and(|(at, _)| at.elapsed() >= window) {
            calls.pop_front(); // older than 4 s: the server forgot it too
        }
        calls
    }

    /// The call-cost of one event: 1, plus its extra cost.
    pub fn cost(&self, event: &str) -> f64 {
        1.0 + EXTRA_COST.iter().find(|(name, _)| *name == event).map_or(0.0, |(_, c)| *c)
    }

    /// The total call-cost of the last 4 s.
    pub fn spent(&self) -> f64 {
        self.lock().iter().map(|(_, c)| c).sum()
    }

    /// Wait until the last 4 s have room for `event`, record its cost, then send it.
    pub async fn emit(&self, event: &str, payload: Value) -> Result<()> {
        let cost = self.cost(event);
        loop {
            let wait = {
                let mut calls = self.lock();
                let spent: f64 = calls.iter().map(|(_, c)| c).sum();
                if spent + cost <= LIMIT || calls.is_empty() {
                    calls.push_back((Instant::now(), cost));
                    None
                } else {
                    // Wait until the oldest call leaves the window (+10 ms for the clock).
                    let oldest = calls.front().map(|(at, _)| *at).unwrap_or_else(Instant::now);
                    Some(oldest + Duration::from_millis(WINDOW_MS + 10))
                }
            }; // the lock ends here, before the .await
            match wait {
                None => return self.sock.emit(event, payload).await,
                Some(until) => tokio::time::sleep_until(until.into()).await,
            }
        }
    }
}
// endregion budget
