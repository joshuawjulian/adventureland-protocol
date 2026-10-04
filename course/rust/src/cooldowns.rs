// cooldowns.rs: when each skill (and the shared potion timer) is ready again.
//
// Concurrency: the handlers below run on the socket's dispatcher task, and the
// program asks `ready` from its own task. So the times sit behind one lock,
// Arc<Mutex<...>>, and each method takes it for a short time. The handlers run
// while the world is locked too; this file never locks the world, so the two
// locks cannot wait for each other.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::{Duration, Instant};

use crate::gdata::GData;
use crate::world::World;

// region cooldowns
/// The ready times. Names are skill names ("attack", "supershot", ...) and
/// "potion" for the potion timer that all potions and `use` share.
#[derive(Clone)]
pub struct Cooldowns {
    ready_at: Arc<Mutex<HashMap<String, Instant>>>,
    g: Arc<GData>,
}

impl Cooldowns {
    /// Listen through `world.listen`, so that hitchhikers count too.
    pub fn new(world: &World) -> Cooldowns {
        let cd = Cooldowns { ready_at: Arc::default(), g: world.g.clone() };
        // After each skill and attack: {name, ms} (node/server_functions.js:3448-3468).
        let c = cd.clone();
        world.listen("skill_timeout", move |_, d| {
            c.start(d["name"].as_str().unwrap_or_default(), d["ms"].as_f64().unwrap_or(0.0));
        });
        // We were too early. "cooldown" names the skill; "not_ready" is the potion timer.
        let c = cd.clone();
        world.listen("game_response", move |_, d| {
            let ms = d["ms"].as_f64().unwrap_or(0.0);
            if d["response"] == "cooldown" {
                c.start(d["skill"].as_str().or(d["place"].as_str()).unwrap_or_default(), ms);
            } else if d["response"] == "not_ready" {
                c.start("potion", ms);
            }
        });
        // The server sets some timers with a line of client code to run:
        // "pot_timeout(2000)" or "skill_timeout('name',ms)". It is a string or {code}.
        let c = cd.clone();
        world.listen("eval", move |_, d| {
            let code = d.as_str().or(d["code"].as_str()).unwrap_or_default();
            if let Some((name, ms)) = parse_timeout(code) {
                c.start(&name, ms);
            }
        });
        cd
    }

    fn lock(&self) -> MutexGuard<'_, HashMap<String, Instant>> {
        self.ready_at.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    /// `name` is ready again in `ms` milliseconds. A skill with `share` in
    /// G.skills uses the timer of that other skill too (3shot shares attack).
    pub fn start(&self, name: &str, ms: f64) {
        let at = Instant::now() + Duration::from_millis(ms.max(0.0) as u64);
        let share = self.g.skills.get(name).and_then(|s| s.share.clone());
        let mut ready_at = self.lock();
        ready_at.insert(name.to_string(), at);
        if let Some(other) = share {
            ready_at.insert(other, at);
        }
    }

    /// True when `name` can be used now. A name we never saw is ready.
    pub fn ready(&self, name: &str) -> bool {
        self.ms_left(name) == 0.0
    }

    /// The milliseconds until `name` is ready; 0 when it is ready.
    pub fn ms_left(&self, name: &str) -> f64 {
        let at = self.lock().get(name).copied();
        at.map_or(0.0, |at| at.saturating_duration_since(Instant::now()).as_secs_f64() * 1000.0)
    }
}

/// "pot_timeout(2000)" -> ("potion", 2000); "skill_timeout('ethereal',120)" -> ("ethereal", 120).
fn parse_timeout(code: &str) -> Option<(String, f64)> {
    if let Some(rest) = code.strip_prefix("pot_timeout(") {
        return Some(("potion".into(), rest.split(')').next()?.trim().parse().ok()?));
    }
    let rest = code.strip_prefix("skill_timeout(")?.trim_start_matches(['\'', '"']);
    let (name, rest) = rest.split_once(['\'', '"'])?;
    let ms = rest.trim_start_matches(',').split(')').next()?.trim().parse().ok()?;
    Some((name.to_string(), ms))
}
// endregion cooldowns
