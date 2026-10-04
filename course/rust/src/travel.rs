// travel.rs: walk around walls, go through doors, use the transporter, and
// get out of jail.
//
// It uses the grid of pathfind.rs for the walls, and Actions::move_to for
// each straight part of the walk.
//
// Concurrency: Travel is a Clone handle. The grids are behind one lock, and
// the code never holds a lock across an `.await`.

use std::collections::{HashMap, VecDeque};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::json;

use crate::actions::Actions;
use crate::alsocket::Result;
use crate::pathfind::Grid;
use crate::world::{num, text, Entity, World};

/// The distances of the server (node/server.js:221-223): a door works within
/// 112 px of its box, the transporter NPC within 160 px of the NPC.
const DOOR_DIST: f64 = 112.0;
const TRANSPORTER_DIST: f64 = 160.0;
/// How long to wait for `new_map` after a transport. Live sends it at once for
/// a door; for the bank it comes after the account loads (in_progress).
const NEW_MAP_MS: u64 = 5000;

/// True for a dead character: `rip` is true (or a gravestone name).
pub fn is_dead(me: &Entity) -> bool {
    me.get("rip").is_some_and(|r| r.as_bool() != Some(false) && !r.is_null())
}

/// One step of a route: stand at (x, y) on `map`, then transport to `to`.
#[derive(Debug, Clone)]
pub struct Hop {
    pub map: String,
    pub x: f64,
    pub y: f64,
    pub to: String,
    pub spawn: u64,
    pub by: &'static str, // "door" or "transporter"
}

/// Walks and map changes of one character. Clones share the grids.
#[derive(Clone)]
pub struct Travel {
    world: World,
    act: Actions,
    grids: Arc<Mutex<HashMap<String, Arc<Grid>>>>, // map -> grid, built once
}

impl Travel {
    pub fn new(world: &World, act: &Actions) -> Travel {
        Travel { world: world.clone(), act: act.clone(), grids: Arc::default() }
    }

    /// The grid of `map`. It is built once for each map and kept.
    pub fn grid(&self, map: &str) -> Result<Arc<Grid>> {
        let mut grids = self.grids.lock().unwrap_or_else(|p| p.into_inner());
        if let Some(grid) = grids.get(map) {
            return Ok(grid.clone());
        }
        let grid = Arc::new(Grid::for_map(&self.world.g, map)?);
        grids.insert(map.to_string(), grid.clone());
        Ok(grid)
    }

    // region walk-to
    /// Walk to (x, y) on this map, around the walls. If (x, y) is not walkable,
    /// walk to the nearest walkable point (at most 320 px away). True when we
    /// arrived; false when there is no path, or when something stopped the
    /// walk: a `correction`, a death, a door, or jail. The caller decides
    /// again on its next tick.
    pub async fn walk_to(&self, x: f64, y: f64) -> Result<bool> {
        self.world.advance();
        let me = self.world.me();
        let map = text(&me, "map").to_string();
        let m = me.get("m").cloned(); // the map counter: it changes on each map change
        let grid = self.grid(&map)?;
        let (mut x, mut y) = (x, y);
        if !grid.safe(x, y) {
            let Some(k) = grid.nearest_free(x, y) else { return Ok(false) };
            (x, y) = grid.point(k);
        }
        let Some(path) = grid.find_path(num(&me, "x"), num(&me, "y"), x, y) else { return Ok(false) };
        for (px, py) in path {
            let arrived = self.act.move_to(px, py).await?;
            let me = self.world.me();
            if text(&me, "map") != map || me.get("m").cloned() != m || is_dead(&me) {
                return Ok(false); // we left this map, or died
            }
            if !arrived {
                return Ok(false); // a correction: our position was wrong
            }
        }
        Ok(true)
    }
    // endregion walk-to

    // region transport
    /// Send `transport` {to, s}: through a door near us, or with the transporter
    /// NPC near us. Then wait until `new_map` puts us on `map`. The server
    /// answers a door with success and sends `new_map` first; the bank answers
    /// {in_progress: true}, and `new_map` comes later (node/server.js:5887-6056).
    pub async fn transport(&self, map: &str, spawn: u64) -> Result<bool> {
        let m = self.world.me().get("m").cloned();
        let r = self.act.request("transport", json!({"to": map, "s": spawn}), None, None).await?;
        if !r.is_some_and(|r| !r.failed) {
            return Ok(false); // for example transport_cant_reach: too far from the door
        }
        Ok(self.wait_until(|me| me.get("m").cloned() != m && text(me, "map") == map, NEW_MAP_MS).await)
    }
    // endregion transport

    // region leave-jail
    /// A line violation (a `move` from or to a point that is not walkable)
    /// sends the character to the map `jail`. `leave` takes it to `main` spawn
    /// 0, the town (node/server.js:5864-5885). It fails while the character is
    /// dead, or with more than 5 monsters on it.
    pub async fn leave_jail(&self) -> Result<bool> {
        let r = self.act.request("leave", json!({}), None, None).await?;
        if !r.is_some_and(|r| !r.failed) {
            return Ok(false);
        }
        Ok(self.wait_until(|me| text(me, "map") != "jail", NEW_MAP_MS).await)
    }
    // endregion leave-jail

    // region route
    /// The ways out of `map`: each door that needs no key, and each place of
    /// the transporter if the map has one. A door [x, y, w, h, to, to_spawn,
    /// own_spawn, lock] works from its own spawn point (door[6]); the server
    /// measures from the box of the door at that spawn (node/server.js:5899-5910).
    pub fn exits(&self, map: &str) -> Vec<Hop> {
        let g = &self.world.g;
        let def = &g.other["maps"][map];
        let mut out = Vec::new();
        for door in def["doors"].as_array().into_iter().flatten() {
            if door.get(7).is_some_and(|l| !l.is_null() && l != false) {
                continue; // a locked door ("ulocked", ...): it needs a key first
            }
            let spawn = &def["spawns"][door[6].as_u64().unwrap_or(0) as usize];
            if let (Some(x), Some(y), Some(to)) = (spawn[0].as_f64(), spawn[1].as_f64(), door[4].as_str()) {
                out.push(Hop { map: map.into(), x, y, to: to.into(), spawn: door[5].as_u64().unwrap_or(0), by: "door" });
            }
        }
        let npc = def["npcs"].as_array().into_iter().flatten().find(|n| n["id"] == "transporter");
        if let Some(npc) = npc {
            let pos = if npc["position"].is_array() { &npc["position"] } else { &npc["positions"][0] };
            if let (Some(x), Some(y)) = (pos[0].as_f64(), pos[1].as_f64()) {
                // G.npcs.transporter.places: map -> the spawn where she sends you.
                for (to, spawn) in g.other["npcs"]["transporter"]["places"].as_object().into_iter().flatten() {
                    if to != map {
                        out.push(Hop { map: map.into(), x, y, to: to.clone(), spawn: spawn.as_u64().unwrap_or(0), by: "transporter" });
                    }
                }
            }
        }
        out
    }

    /// The fewest hops from `from` to `to`: a breadth-first search on the graph
    /// of maps. Some(empty) when we are there, None when no route exists.
    pub fn route(&self, from: &str, to: &str) -> Option<Vec<Hop>> {
        if from == to {
            return Some(Vec::new());
        }
        let maps = &self.world.g.other["maps"];
        let mut came: HashMap<String, Option<Hop>> = HashMap::from([(from.to_string(), None)]); // map -> the hop that reached it
        let mut queue = VecDeque::from([from.to_string()]);
        while let Some(map) = queue.pop_front() {
            for hop in self.exits(&map) {
                if came.contains_key(&hop.to) || !maps[&hop.to].is_object() {
                    continue;
                }
                came.insert(hop.to.clone(), Some(hop.clone()));
                if hop.to == to {
                    let mut hops = vec![hop.clone()];
                    while let Some(Some(h)) = came.get(&hops[0].map) {
                        hops.insert(0, h.clone());
                    }
                    return Some(hops);
                }
                queue.push_back(hop.to);
            }
        }
        None
    }

    /// Go to `map` along route(): for each hop, walk to the door (or to the
    /// transporter), then transport. True when we are on `map`.
    pub async fn go_to_map(&self, map: &str) -> Result<bool> {
        let here = text(&self.world.me(), "map").to_string();
        let Some(hops) = self.route(&here, map) else { return Ok(false) };
        for hop in hops {
            if !self.walk_to(hop.x, hop.y).await? {
                return Ok(false);
            }
            // walk_to can stop short of the point (at the nearest walkable
            // cell). The server then says "transport_cant_reach"; do not even ask.
            let me = self.world.me();
            let reach = if hop.by == "door" { DOOR_DIST } else { TRANSPORTER_DIST };
            if (num(&me, "x") - hop.x).hypot(num(&me, "y") - hop.y) > reach {
                return Ok(false);
            }
            if !self.transport(&hop.to, hop.spawn).await? {
                return Ok(false);
            }
        }
        Ok(text(&self.world.me(), "map") == map)
    }
    // endregion route

    /// Poll `test` on `me` every 50 ms until it is true, or `ms` have passed.
    async fn wait_until(&self, test: impl Fn(&Entity) -> bool, ms: u64) -> bool {
        let end = Instant::now() + Duration::from_millis(ms);
        while Instant::now() < end {
            if test(&self.world.me()) {
                return true;
            }
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
        test(&self.world.me())
    }
}

