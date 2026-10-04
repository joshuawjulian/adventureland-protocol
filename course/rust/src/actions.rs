// actions.rs: what the bot does in the world: move, attack, heal, loot,
// respawn. Each event goes out through the call-cost budget. A method that
// waits for a reply registers the wait BEFORE it sends, so that a fast reply
// cannot arrive before the wait exists.

use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use crate::alsocket::{AlSocket, Result};
use crate::budget::Budget;
use crate::cooldowns::Cooldowns;
use crate::world::{num, World};

/// The respawn wait after a death: 12 s (B.rip_time, node/server.js:224).
const RIP_MS: u64 = 12_000;

/// `game_response` in one shape. It arrives as an object or as a bare string.
#[derive(Debug, Clone)]
pub struct GameResponse {
    pub response: String,      // the code: "cooldown", "too_far", "data", ...
    pub place: Option<String>, // the event that it answers (when the server says)
    pub failed: bool,
    pub success: bool, // note: a successful attack has no `success` key: false here
    pub raw: Value,    // the whole payload, for the fields of each code (ms, id, ...)
}

// region normalize
/// A string "x" becomes {response: "x"}; `failed` and `success` default to false.
pub fn normalize(data: &Value) -> GameResponse {
    let response = data.as_str().or(data["response"].as_str()).unwrap_or_default();
    GameResponse {
        response: response.to_string(),
        place: data["place"].as_str().map(String::from),
        failed: data["failed"] == true,
        success: data["success"] == true,
        raw: data.clone(),
    }
}

/// A wait_for predicate: a `game_response` object whose `place` is `place`.
/// A bare string has no place, so it never matches.
pub fn response_for(place: &str) -> impl Fn(&Value) -> bool + Send + Sync + 'static {
    let place = place.to_string();
    move |d: &Value| d["place"] == place.as_str()
}
// endregion normalize

/// The actions of one character. Clones share the same state.
#[derive(Clone)]
pub struct Actions {
    sock: Arc<AlSocket>,
    world: World,
    cooldowns: Cooldowns,
    budget: Budget,
    died_at: Arc<Mutex<Option<Instant>>>, // when we died last (for respawn)
}

impl Actions {
    pub fn new(sock: Arc<AlSocket>, world: World, cooldowns: Cooldowns, budget: Budget) -> Actions {
        let act = Actions { sock, world, cooldowns, budget, died_at: Arc::default() };
        // The server tells us of a death with this response (node/server.js:13884-13940).
        let died_at = act.died_at.clone();
        act.world.listen("game_response", move |_, d| {
            if d["response"] == "defeated_by_a_monster" {
                *died_at.lock().unwrap_or_else(|p| p.into_inner()) = Some(Instant::now());
            }
        });
        act
    }

    // region request
    /// Send `event` and wait for the `game_response` whose place is `place`
    /// (`None`: the event name). `None` as the result: no reply in time
    /// (`timeout_ms`, default 2000). An error: the socket closed.
    pub async fn request(
        &self,
        event: &str,
        payload: Value,
        place: Option<&str>,
        timeout_ms: Option<u64>,
    ) -> Result<Option<GameResponse>> {
        let place = place.unwrap_or(event);
        // 1 day: in effect no timeout of its own. The timeout below decides,
        // so that "no reply" (None) and "socket closed" (Err) stay different.
        let day = Duration::from_secs(86_400);
        let reply = self.sock.wait_for_timeout("game_response", response_for(place), day);
        self.budget.emit(event, payload).await?;
        let ms = Duration::from_millis(timeout_ms.unwrap_or(2000)); // 2 s: replies take < 0.5 s
        match tokio::time::timeout(ms, reply).await {
            Ok(data) => Ok(Some(normalize(&data?))),
            Err(_) => Ok(None), // dropping `reply` also removes the waiter
        }
    }
    // endregion request

    // region move-to
    /// Start a straight walk to (x, y) on this map. No reply comes; the server
    /// ignores a move with the wrong map counter `m` (node/server.js:11183-11271).
    /// `move` is a Rust keyword, so the name is written r#move.
    pub async fn r#move(&self, x: f64, y: f64) -> Result<()> {
        self.world.advance(); // our position now, not at the last update
        let payload = {
            let mut w = self.world.lock(); // ends before the .await below
            let payload = json!({
                "x": num(&w.me, "x"), "y": num(&w.me, "y"),
                "going_x": x, "going_y": y,
                "m": w.me.get("m").cloned().unwrap_or(json!(0)),
            });
            // The server does the same with its copy, so step() moves ours.
            w.me.insert("going_x".into(), json!(x));
            w.me.insert("going_y".into(), json!(y));
            w.me.insert("moving".into(), json!(true));
            payload
        };
        self.budget.emit("move", payload).await
    }

    /// Walk to (x, y) in a straight line, and wait the time that it takes
    /// (distance / speed, + 250 ms for the network). True if `me` is there.
    /// It does not go around walls: that is Travel::walk_to (Part 3).
    pub async fn move_to(&self, x: f64, y: f64) -> Result<bool> {
        self.world.advance();
        let me = self.world.me();
        let far = (x - num(&me, "x")).hypot(y - num(&me, "y"));
        let seconds = far / num(&me, "speed").max(1.0); // max: never divide by 0
        self.r#move(x, y).await?;
        tokio::time::sleep(Duration::from_secs_f64(seconds) + Duration::from_millis(250)).await;
        self.world.advance();
        let me = self.world.me();
        // Arrived: within 1 px, and still on the way to (x, y). A `correction`
        // or a jail sends us somewhere else: then the walk failed.
        let near = (num(&me, "x") - x).hypot(num(&me, "y") - y) < 1.0;
        Ok(near && num(&me, "going_x") == x && num(&me, "going_y") == y)
    }
    // endregion move-to

    // region attack
    /// Attack a monster (or player) by id. The reply is a game_response with
    /// place "attack": success has the projectile data (no `success` key),
    /// failure has `failed: true` (cooldown, too_far, ...). None: no reply;
    /// a target that is gone gets `disappear` with reason "not_there" instead.
    pub async fn attack(&self, id: &str) -> Result<Option<GameResponse>> {
        self.request("attack", json!({"id": id}), None, None).await
    }
    // endregion attack

    // region heal
    /// Restore `stat` ("hp" or "mp"). A potion that gives `stat`, if one is in
    /// the inventory (`equip` with consume: true drinks it), else the free
    /// regeneration (`use`). False, without a send, when the shared potion
    /// timer is not ready; false also when the server refuses.
    pub async fn heal(&self, stat: &str) -> Result<bool> {
        if !self.cooldowns.ready("potion") {
            return Ok(false);
        }
        let slot = {
            let w = self.world.lock();
            let items = w.me.get("items").and_then(Value::as_array).cloned().unwrap_or_default();
            items.iter().position(|item| {
                // An empty slot is null: no name, no def, no match.
                let def = self.world.g.items.get(item["name"].as_str().unwrap_or_default());
                def.is_some_and(|d| d.gives.iter().any(|(s, _)| s == stat))
            })
        };
        let (event, payload) = match slot {
            Some(num) => ("equip", json!({"num": num, "consume": true})),
            None => ("use", json!({"item": stat})),
        };
        let reply = self.request(event, payload, None, None).await?;
        Ok(reply.is_some_and(|r| !r.failed))
    }
    // endregion heal

    // region open-chests
    /// Open one chest. The reply is `chest_opened` with this id: {gold, items}
    /// or {gone: true}. None: no reply (for example, `loot_no_space`).
    pub async fn open_chest(&self, id: &str) -> Result<Option<Value>> {
        let wanted = id.to_string();
        let day = Duration::from_secs(86_400); // the timeout below decides (see request)
        let reply = self.sock.wait_for_timeout("chest_opened", move |d| d["id"] == wanted.as_str(), day);
        self.budget.emit("open_chest", json!({"id": id})).await?;
        match tokio::time::timeout(Duration::from_millis(2000), reply).await {
            Ok(data) => Ok(Some(data?)),
            Err(_) => Ok(None),
        }
    }

    /// Open each chest that the world knows. Returns how many opened.
    pub async fn open_chests(&self) -> Result<usize> {
        let ids: Vec<String> = self.world.lock().chests.keys().cloned().collect();
        let mut opened = 0;
        for id in ids {
            let reply = self.open_chest(&id).await?;
            if reply.is_some_and(|r| r["gone"] != true) {
                opened += 1;
            }
            // Also with no reply (a full bag: "loot_no_space"; the chest stays on the
            // server, node/server.js:11315): forget it, so that we do not try it forever.
            self.world.lock().chests.remove(&id);
        }
        Ok(opened)
    }
    // endregion open-chests

    // region respawn
    /// The milliseconds until a respawn is allowed (0 when we do not know of a death).
    pub fn respawn_ms_left(&self) -> u64 {
        let died_at = *self.died_at.lock().unwrap_or_else(|p| p.into_inner());
        died_at.map_or(0, |at| RIP_MS.saturating_sub(at.elapsed().as_millis() as u64))
    }

    /// Wait the rest of the 12 s after the death, then send `respawn`. If the
    /// server says `cant_respawn` (too early), wait its `ms` and try once more.
    /// True when the server accepts it (after `new_map` and `player`).
    pub async fn respawn(&self) -> Result<bool> {
        tokio::time::sleep(Duration::from_millis(self.respawn_ms_left())).await;
        for _try in 0..2 {
            // {} respawns at the map's spawn; {safe: true} would go to "woffice".
            let Some(r) = self.request("respawn", json!({}), None, Some(3000)).await? else {
                return Ok(false);
            };
            if r.response == "cant_respawn" {
                let ms = r.raw["ms"].as_f64().unwrap_or(1000.0);
                tokio::time::sleep(Duration::from_millis(ms as u64 + 50)).await; // +50: clock margin
                continue;
            }
            return Ok(!r.failed);
        }
        Ok(false)
    }
    // endregion respawn
}
