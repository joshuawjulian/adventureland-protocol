// world.rs: our copy of the world: our character (`me`), the monsters, the
// other players and the chests, kept up to date from the server's events.
//
// Concurrency: AlSocket calls the handlers on its dispatcher task, and the
// program reads the world from its own task. So the state (WorldState) sits
// behind one lock, Arc<Mutex<...>>. Handlers get `&mut WorldState` while the
// dispatcher holds the lock. Your code takes it with `world.lock()` (or a
// method that takes it), and must not hold it across an `.await`.
//
// Entities are the server's JSON objects (serde_json::Map), not structs: a
// `player` update merges into `me` field by field, and an `entities` update
// replaces a monster. Read a number with `num(&entity, "hp")` (0 when missing).

use std::collections::HashMap;
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::Instant;

use serde_json::{json, Map, Value};

use crate::alsocket::AlSocket;
use crate::gdata::GData;

/// One entity: the server's JSON object of a character, monster or NPC.
pub type Entity = Map<String, Value>;

/// A handler of `listen`. It runs with the world locked.
type Handler = Arc<dyn Fn(&mut WorldState, &Value) + Send + Sync>;

/// A number field of an entity, or 0 when it is missing (or not a number).
pub fn num(e: &Entity, key: &str) -> f64 {
    e.get(key).and_then(Value::as_f64).unwrap_or(0.0)
}

/// A text field of an entity, or "" when it is missing.
pub fn text<'a>(e: &'a Entity, key: &str) -> &'a str {
    e.get(key).and_then(Value::as_str).unwrap_or("")
}

/// The state behind the lock.
pub struct WorldState {
    /// Our character: the `start` payload (without `entities`), with each
    /// `player` update merged in. Empty until `start`. It has no `name`
    /// field: the server sends the name as `id`.
    pub me: Entity,
    pub monsters: HashMap<String, Entity>, // id -> monster
    pub players: HashMap<String, Entity>,  // id -> other player or NPC (never us)
    pub chests: HashMap<String, Value>,    // chest id -> the `drop` payload
    pub g: Arc<GData>,
    last: Instant, // the time of the last advance() or full update
    handlers: HashMap<String, Vec<Handler>>,
}

/// A handle to the world. Clones share the same state.
#[derive(Clone)]
pub struct World {
    state: Arc<Mutex<WorldState>>,
    sock: Arc<AlSocket>,
    pub g: Arc<GData>,
}

impl World {
    // region constructor
    /// Create the world and register its handlers. Do this BEFORE you send
    /// `loaded` and `auth`, so that the world sees `start`.
    pub fn new(sock: Arc<AlSocket>, g: Arc<GData>) -> World {
        let state = WorldState {
            me: Entity::new(),
            monsters: HashMap::new(),
            players: HashMap::new(),
            chests: HashMap::new(),
            g: g.clone(),
            last: Instant::now(),
            handlers: HashMap::new(),
        };
        let world = World { state: Arc::new(Mutex::new(state)), sock, g };
        world.listen("start", WorldState::on_start);
        world.listen("player", WorldState::on_player);
        world.listen("entities", WorldState::apply_entities);
        world.listen("death", |w, d| {
            w.monsters.remove(d["id"].as_str().unwrap_or_default());
        });
        world.listen("disappear", |w, d| {
            let id = d["id"].as_str().unwrap_or_default();
            w.monsters.remove(id);
            w.players.remove(id);
        });
        world.listen("new_map", WorldState::on_new_map);
        world.listen("drop", |w, d| {
            w.chests.insert(d["id"].as_str().unwrap_or_default().to_string(), d.clone());
        });
        world.listen("chest_opened", |w, d| {
            w.chests.remove(d["id"].as_str().unwrap_or_default());
        });
        world.listen("correction", |w, d| {
            // The server disagrees with our position (more than 132 px off): use its position.
            w.me.insert("x".into(), d["x"].clone());
            w.me.insert("y".into(), d["y"].clone());
        });
        world
    }
    // endregion constructor

    /// Lock the state. A handler that panicked does not make the lock unusable.
    pub fn lock(&self) -> MutexGuard<'_, WorldState> {
        self.state.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    // region listen
    /// Add a handler for an event. One table of handlers for all events, so
    /// that the hitchhikers of a `player` update reach the same handlers
    /// (dispatch). The first handler for a name also subscribes to the socket.
    pub fn listen(&self, name: &str, handler: impl Fn(&mut WorldState, &Value) + Send + Sync + 'static) {
        let first = {
            let mut w = self.lock();
            let list = w.handlers.entry(name.to_string()).or_default();
            list.push(Arc::new(handler));
            list.len() == 1
        }; // the lock ends here: sock.on can give kept events at once, and they lock it
        if first {
            let (state, event) = (self.state.clone(), name.to_string());
            self.sock.on(name, move |data| {
                let mut w = state.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
                w.dispatch(&event, data);
            });
        }
    }

    /// Call the handlers of `name` with `data`, as if the event came from the socket.
    pub fn dispatch(&self, name: &str, data: &Value) {
        self.lock().dispatch(name, data);
    }
    // endregion listen

    /// A copy of `me`.
    pub fn me(&self) -> Entity {
        self.lock().me.clone()
    }

    // region advance
    /// Move `me`, the monsters and the players forward to now. Call it before
    /// you read positions. There is no background timer.
    pub fn advance(&self) {
        let mut w = self.lock();
        let ms = w.last.elapsed().as_secs_f64() * 1000.0;
        w.last = Instant::now();
        let w = &mut *w; // one &mut WorldState, so that we can borrow its fields one by one
        step(&mut w.me, ms);
        w.monsters.values_mut().chain(w.players.values_mut()).for_each(|e| step(e, ms));
    }
    // endregion advance

    /// The gap between the hit boxes of `a` and `b` (see `distance`).
    pub fn distance(&self, a: &Entity, b: &Entity) -> f64 {
        distance(&self.g, a, b)
    }

    /// The monster (of type `kind`, if given) closest to `me`, or None.
    pub fn nearest_monster(&self, kind: Option<&str>) -> Option<Entity> {
        let w = self.lock();
        w.monsters
            .values()
            .filter(|m| kind.map_or(true, |k| text(m, "type") == k))
            .map(|m| (distance(&self.g, &w.me, m), m))
            .min_by(|a, b| a.0.total_cmp(&b.0))
            .map(|(_, m)| m.clone())
    }
}

impl WorldState {
    /// Call each handler of `name`. Handlers get `&mut self`, so they can change the world.
    pub fn dispatch(&mut self, name: &str, data: &Value) {
        let list = self.handlers.get(name).cloned().unwrap_or_default(); // a copy: handlers change self
        for handler in list {
            handler(self, data);
        }
    }

    // region on-start
    /// `start`: our character, and in `entities` the first full view.
    pub fn on_start(&mut self, data: &Value) {
        self.me = data.as_object().cloned().unwrap_or_default();
        self.me.remove("entities"); // the view goes to monsters and players, not into me
        self.last = Instant::now();
        self.apply_entities(&data["entities"]);
    }
    // endregion on-start

    // region on-player
    /// `player`: the new state of our character. Merge it into `me`: the
    /// fields that are in the update replace ours, the others stay.
    pub fn on_player(&mut self, data: &Value) {
        for (key, value) in data.as_object().into_iter().flatten() {
            if key != "hitchhikers" {
                self.me.insert(key.clone(), value.clone());
            }
        }
        // Hitchhikers: [event, payload] pairs that came with this update.
        // Handle each one as if it came alone.
        for pair in data["hitchhikers"].as_array().into_iter().flatten() {
            if let Some(name) = pair[0].as_str() {
                self.dispatch(name, &pair[1]);
            }
        }
    }
    // endregion on-player

    // region apply-entities
    /// `entities`: other characters and monsters. Each object is the full
    /// state of that entity, so it replaces our copy (no merge).
    pub fn apply_entities(&mut self, data: &Value) {
        if data.get("in") != self.me.get("in") {
            return; // an update for an instance (map copy) that we already left
        }
        if data["type"] == "all" {
            // A full view: everything that is not in it is out of sight.
            self.monsters.clear();
            self.players.clear();
        }
        for m in data["monsters"].as_array().into_iter().flatten() {
            let mut monster = m.as_object().cloned().unwrap_or_default();
            self.with_defaults(&mut monster);
            self.monsters.insert(text(&monster, "id").to_string(), monster);
        }
        for p in data["players"].as_array().into_iter().flatten() {
            let player = p.as_object().cloned().unwrap_or_default();
            if player.get("id") != self.me.get("id") {
                // A full view also has us in it. We are `me`, never in `players`.
                self.players.insert(text(&player, "id").to_string(), player);
            }
        }
    }

    /// The server sends only the monster fields that differ from
    /// G.monsters[type] (node/server.js:1003-1071). Fill in the others.
    pub fn with_defaults(&self, monster: &mut Entity) {
        let Some(def) = self.g.monsters.get(text(monster, "type")) else { return };
        let defaults = [
            ("hp", def.hp),
            ("max_hp", def.hp), // G has one `hp`: the full hp
            ("attack", def.attack),
            ("speed", def.speed),
            ("range", def.range),
            ("frequency", def.frequency),
            ("xp", def.xp),
        ];
        for (key, value) in defaults {
            monster.entry(key).or_insert(json!(value));
        }
    }
    // endregion apply-entities

    // region on-new-map
    /// `new_map`: we went through a door, were transported, or respawned.
    /// The payload has the new place and a full view (type "all").
    pub fn on_new_map(&mut self, data: &Value) {
        for (key, from) in [("map", "name"), ("in", "in"), ("x", "x"), ("y", "y"), ("m", "m")] {
            self.me.insert(key.into(), data[from].clone()); // `m`: the map counter that `move` sends
        }
        self.me.insert("moving".into(), json!(false));
        self.last = Instant::now();
        self.apply_entities(&data["entities"]);
    }
    // endregion on-new-map
}

// region step
/// Move one entity toward going_x/going_y for `ms` milliseconds. `speed` is
/// in px per second, so one step is speed * ms / 1000 px.
pub fn step(e: &mut Entity, ms: f64) {
    if e.get("moving") != Some(&Value::Bool(true)) {
        return;
    }
    let (x, y) = (num(e, "x"), num(e, "y"));
    let (gx, gy) = (num(e, "going_x"), num(e, "going_y"));
    let left = (gx - x).hypot(gy - y); // the distance still to go
    let travel = num(e, "speed") * ms / 1000.0;
    if travel >= left {
        // Arrived: stop at the target, not past it.
        e.insert("x".into(), json!(gx));
        e.insert("y".into(), json!(gy));
        e.insert("moving".into(), json!(false));
    } else {
        e.insert("x".into(), json!(x + (gx - x) / left * travel));
        e.insert("y".into(), json!(y + (gy - y) / left * travel));
    }
}
// endregion step

// region distance
/// The hit box of an entity: (width, height). x is the centre of the box and
/// y is its bottom (the feet).
/// - A character is 26 x 36 (node/server.js:11782-11783).
/// - A monster is G.dimensions[type], times G.monsters[type].size, rounded.
///   A type with no entry is 24 x 24 (get_monster_dimensions,
///   js/old_common_functions.js:692).
fn hitbox(g: &GData, e: &Entity) -> (f64, f64) {
    let kind = text(e, "type");
    if e.contains_key("ctype") || !g.monsters.contains_key(kind) {
        return (26.0, 36.0); // characters (and NPCs) have `ctype`; monsters have a G.monsters `type`
    }
    let d = g.dimensions.get(kind);
    let (w, h) = match d {
        Some(d) if d.len() >= 2 => (d[0], d[1]),
        _ => (24.0, 24.0),
    };
    match g.monsters[kind].size {
        Some(size) => ((w * size).round(), (h * size).round()),
        None => (w, h),
    }
}

/// The distance that the server checks for range: the gap between the two
/// hit boxes, 0 when they touch (distance(), js/old_common_functions.js:707-740).
/// Not on the same map or instance: a very large number, as in the source.
pub fn distance(g: &GData, a: &Entity, b: &Entity) -> f64 {
    for key in ["in", "map"] {
        if let (Some(va), Some(vb)) = (a.get(key), b.get(key)) {
            if va != vb {
                return 99_999_999.0;
            }
        }
    }
    let ((aw, ah), (bw, bh)) = (hitbox(g, a), hitbox(g, b));
    let (ax, ay, bx, by) = (num(a, "x"), num(a, "y"), num(b, "x"), num(b, "y"));
    // The gap on each axis. Negative means the boxes overlap on that axis: 0.
    let dx = (bx - bw / 2.0 - (ax + aw / 2.0)).max(ax - aw / 2.0 - (bx + bw / 2.0)).max(0.0);
    let dy = (by - bh - ay).max(ay - ah - by).max(0.0);
    dx.hypot(dy)
}
// endregion distance
