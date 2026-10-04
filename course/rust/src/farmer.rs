// farmer.rs: the decisions of a fighting character, one tick at a time:
// stay alive, loot, choose a target, walk, attack.
//
// tick() does the first thing on this list that applies, and returns. It
// remembers nothing between ticks except the target and the counters, so a
// monster that attacks during a walk changes the next tick at once.
//   1. dead: respawn          2. in jail: leave          3. on another map: go home
//   4. low hp or mp: heal     5. a chest: open it        6. no target: choose one
//   7. too far: walk          8. in range: attack
//
// Concurrency: the handlers (on the dispatcher task) and tick() (on the
// program's task) share FarmerState behind one lock. No lock is held across
// an `.await`.

use std::sync::{Arc, Mutex, MutexGuard};

use crate::actions::Actions;
use crate::alsocket::Result;
use crate::cooldowns::Cooldowns;
use crate::travel::{is_dead, Travel};
use crate::world::{num, text, Entity, World};

// region ladder
/// The Mainland ladder of the game guide ("Your first day"): the next monster
/// when the current one is too easy. All live on `main`.
pub const LADDER: &[&str] = &["goo", "bee", "crab", "snake", "squig", "armadillo", "croc", "tortoise"];
/// "Too easy": the last 3 kills took 2 attacks or fewer each (the guide's rule:
/// "go to the next monster when you kill the current one in one or two hits").
const EASY_HITS: u32 = 2;
const EASY_KILLS: usize = 3;
// endregion ladder

/// Heal below 70 % hp: a potion (or the free regeneration) brings us back up
/// before a weak monster can take the other 30 %. Mana below 30 %: a class
/// that uses mana for attacks (priest, mage) needs it.
const HEAL_HP: f64 = 0.7;
const HEAL_MP: f64 = 0.3;
/// Stop 10 px inside our range: the monster moves while we walk.
const RANGE_MARGIN: f64 = 10.0;

/// The state that the handlers and tick() share.
pub struct FarmerState {
    pub kind: String,           // the monster type that we hunt now ("type" is a keyword)
    pub home: String,           // the map of our monsters
    pub target: Option<String>, // the id of the monster that we attack
    pub kills: u64,
    hits: u32,        // our hits on the target
    recent: Vec<u32>, // hits for each of the last kills
}

/// One fighting character's decisions. Clones share the same state.
#[derive(Clone)]
pub struct Farmer {
    world: World,
    act: Actions,
    cooldowns: Cooldowns,
    travel: Travel,
    prefix: String, // put before each line that it prints ("Tester: ")
    state: Arc<Mutex<FarmerState>>,
}

/// "<x>,<y>", rounded.
fn at(e: &Entity) -> String {
    format!("{:.0},{:.0}", num(e, "x"), num(e, "y"))
}

impl Farmer {
    pub fn new(world: &World, act: &Actions, cooldowns: &Cooldowns, travel: &Travel, prefix: &str) -> Farmer {
        let state = FarmerState {
            kind: "goo".into(),
            home: "main".into(),
            target: None,
            kills: 0,
            hits: 0,
            recent: Vec::new(),
        };
        let farmer = Farmer {
            world: world.clone(),
            act: act.clone(),
            cooldowns: cooldowns.clone(),
            travel: travel.clone(),
            prefix: prefix.to_string(),
            state: Arc::new(Mutex::new(state)),
        };
        // The target is dead when we get `death` with its id, or a `hit` with `kill`.
        let (s, p) = (farmer.state.clone(), farmer.prefix.clone());
        world.listen("death", move |_, d| dead(&s, &p, d["id"].as_str().unwrap_or_default()));
        let (s, p) = (farmer.state.clone(), farmer.prefix.clone());
        world.listen("hit", move |w, d| {
            let id = d["id"].as_str().unwrap_or_default();
            {
                let mut st = s.lock().unwrap_or_else(|e| e.into_inner());
                if st.target.as_deref() != Some(id) {
                    return;
                }
                if d["hid"].as_str() == w.me.get("id").and_then(|v| v.as_str()) {
                    st.hits += 1;
                }
            }
            if d["kill"] == true {
                dead(&s, &p, id);
            }
        });
        // Each chest that opens for us.
        let p = farmer.prefix.clone();
        world.listen("chest_opened", move |_, r| {
            if r["gone"] != true {
                let items = r["items"].as_array().map_or(0, |a| a.len());
                println!("{p}chest {}: +{} gold, {items} item(s)", r["id"].as_str().unwrap_or_default(), r["gold"].as_f64().unwrap_or(0.0));
            }
        });
        farmer
    }

    /// The shared state: kind, home, target, kills.
    pub fn state(&self) -> MutexGuard<'_, FarmerState> {
        self.state.lock().unwrap_or_else(|e| e.into_inner())
    }

    pub fn kills(&self) -> u64 {
        self.state().kills
    }

    fn log(&self, line: &str) {
        println!("{}{line}", self.prefix);
    }

    // region next-type
    /// Move up the ladder when the last kills were easy. True when the type
    /// changed. Check the next monster in the game guide first: its damage
    /// per second must be less than your healing (game guide, "Your first day").
    pub fn next_type(&self) -> bool {
        let next = {
            let mut st = self.state();
            let i = LADDER.iter().position(|t| *t == st.kind);
            let easy = st.recent.len() == EASY_KILLS && st.recent.iter().all(|h| *h <= EASY_HITS);
            match i {
                Some(i) if easy && i + 1 < LADDER.len() => {
                    st.kind = LADDER[i + 1].to_string();
                    st.recent.clear();
                    st.target = None;
                    st.kind.clone()
                }
                _ => return false,
            }
        };
        self.log(&format!("next monster: {next}"));
        true
    }
    // endregion next-type

    // region tick
    pub async fn tick(&self) -> Result<()> {
        let (world, act, travel) = (&self.world, &self.act, &self.travel);
        world.advance(); // positions at this moment
        let me = world.me();
        let (kind, home, target_id) = {
            let st = self.state();
            (st.kind.clone(), st.home.clone(), st.target.clone())
        };

        // 1. Dead: wait for the 12 s, then respawn (at main spawn 5 on `main`).
        if is_dead(&me) {
            self.log(&format!("died; respawn in {} s", act.respawn_ms_left().div_ceil(1000)));
            if act.respawn().await? {
                self.log(&format!("respawned at {}", at(&world.me())));
            }
            return Ok(());
        }
        // 2. Jail: a line violation put us there. `leave` goes to the town.
        if text(&me, "map") == "jail" {
            self.log("in jail: leave");
            if travel.leave_jail().await? {
                let me = world.me();
                self.log(&format!("left jail: on {} at {}", text(&me, "map"), at(&me)));
            }
            return Ok(());
        }
        // 3. Another map (a door, the bank, a respawn somewhere else): go home.
        if text(&me, "map") != home {
            self.log(&format!("on {}: go to {home}", text(&me, "map")));
            travel.go_to_map(&home).await?;
            return Ok(());
        }
        // 4. Health first, then mana. heal() drinks a potion if we have one.
        if self.cooldowns.ready("potion") {
            if num(&me, "hp") < HEAL_HP * num(&me, "max_hp") {
                act.heal("hp").await?;
            } else if num(&me, "mp") < HEAL_MP * num(&me, "max_mp") {
                act.heal("mp").await?;
            }
        }
        // 5. Chests: open them all. Gold and items wait in a chest for 8 min only.
        if !world.lock().chests.is_empty() {
            act.open_chests().await?;
            return Ok(());
        }
        // 6. The target. Choose the nearest of our type if we have none.
        let known = target_id.and_then(|id| world.lock().monsters.get(&id).cloned());
        let target = match known {
            Some(t) => t,
            None => {
                let Some(t) = world.nearest_monster(Some(&kind)) else {
                    // None in view: walk to the middle of its spawn box (G.maps[map].monsters).
                    let packs = &world.g.other["maps"][text(&me, "map")]["monsters"];
                    let pack = packs.as_array().into_iter().flatten().find(|p| p["type"] == kind.as_str() && p["boundary"].is_array());
                    if let Some(pack) = pack {
                        let b: Vec<f64> = pack["boundary"].as_array().unwrap().iter().map(|v| v.as_f64().unwrap_or(0.0)).collect();
                        travel.walk_to((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0).await?;
                    }
                    return Ok(());
                };
                {
                    let mut st = self.state();
                    st.target = Some(text(&t, "id").to_string());
                    st.hits = 0;
                }
                self.log(&format!("target: {kind} {} at {}", text(&t, "id"), at(&t)));
                t
            }
        };
        // 7. Too far: walk to a point `range - 10` px from it, on the line to us.
        let range = num(&me, "range");
        if world.distance(&me, &target) > range {
            let (dx, dy) = (num(&me, "x") - num(&target, "x"), num(&me, "y") - num(&target, "y"));
            let d = dx.hypot(dy).max(1.0);
            let stop = (range - RANGE_MARGIN).max(0.0);
            travel.walk_to(num(&target, "x") + dx / d * stop, num(&target, "y") + dy / d * stop).await?;
            return Ok(());
        }
        // 8. In range: attack when the cooldown allows.
        if self.cooldowns.ready("attack") {
            act.attack(text(&target, "id")).await?;
        }
        Ok(())
    }
    // endregion tick
}

/// The target `id` died: count it, and choose a new one on the next tick.
fn dead(state: &Mutex<FarmerState>, prefix: &str, id: &str) {
    let mut st = state.lock().unwrap_or_else(|e| e.into_inner());
    if st.target.as_deref() != Some(id) {
        return;
    }
    println!("{prefix}killed {} {id}", st.kind);
    st.kills += 1;
    let hits = st.hits;
    st.recent.push(hits);
    if st.recent.len() > EASY_KILLS {
        st.recent.remove(0);
    }
    st.target = None;
    st.hits = 0;
}
