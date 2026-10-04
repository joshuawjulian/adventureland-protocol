// world.js: our copy of the game world: our character (`me`), the monsters,
// the other players and the chests. The server sends changes as events; the
// handlers here apply them. Node.js 22.18+. No packages.
//
// Create the World BEFORE you send `loaded` and `auth`: the constructor
// registers the handlers, and `start` comes as the reply to `auth`.

// An entity (me, a monster, a player) is the server's JSON object, as it is.
// A `player` update merges into it field by field; an `entities` update
// replaces it. A field that is missing reads as undefined.
/** @typedef {Record<string, any>} Entity */
/** @typedef {(data: any) => void} Handler */

// The size of a character's hit box on the server: 26 x 36 px
// (node/server.js:11782-11783).
const CHARACTER_BOX = [26, 36];
// The hit box of a monster type with no entry in G.dimensions
// (get_monster_dimensions, js/old_common_functions.js:692-700).
const DEFAULT_MONSTER_BOX = [24, 24];

export class World {
  /** @type {Entity} our character: the `start` data with each `player` merged in */
  me = {};
  /** @type {Map<string, Entity>} monster id -> monster */
  monsters = new Map();
  /** @type {Map<string, Entity>} id -> other player or NPC (never us) */
  players = new Map();
  /** @type {Map<string, Entity>} chest id -> the `drop` data */
  chests = new Map();

  /** @type {Map<string, Handler[]>} event name -> handlers */
  #handlers = new Map();
  // When each entity was last moved forward in time (see advance()). A
  // WeakMap, so that the server's objects get no extra field, and a replaced
  // entity is forgotten with its object.
  /** @type {WeakMap<Entity, number>} */
  #steppedAt = new WeakMap();

  /**
   * @param {import("./alsocket.js").AlSocket} sock
   * @param {Record<string, any>} G  the game data (gdata.js)
   */
  // region constructor
  constructor(sock, G) {
    this.sock = sock;
    this.G = G;
    this.listen("start", (data) => this.onStart(data));
    this.listen("player", (data) => this.onPlayer(data));
    this.listen("entities", (data) => this.applyEntities(data));
    this.listen("new_map", (data) => this.onNewMap(data));
    // `death`: a monster died. `disappear`: an entity left our view (or
    // a player logged off, or the target of our attack is not there).
    this.listen("death", (data) => this.monsters.delete(data.id));
    this.listen("disappear", (data) => {
      this.monsters.delete(data.id);
      this.players.delete(data.id);
    });
    this.listen("drop", (data) => this.chests.set(data.id, data));
    this.listen("chest_opened", (data) => this.chests.delete(data.id));
    // The server did not accept our position: it sends its own.
    this.listen("correction", (data) => {
      this.me.x = data.x;
      this.me.y = data.y;
      this.#steppedAt.set(this.me, Date.now());
    });
  }
  // endregion constructor

  // region listen
  // One table from event name to our handlers. Hitchhikers (events that ride
  // inside a `player` update) reach the same handlers through dispatch(), so
  // a handler never needs to know how its event arrived.
  /** @param {string} name @param {Handler} handler */
  listen(name, handler) {
    let list = this.#handlers.get(name);
    if (!list) {
      list = [];
      this.#handlers.set(name, list);
      this.sock.on(name, (data) => this.dispatch(name, data)); // one socket handler per name
    }
    list.push(handler);
  }

  /** @param {string} name @param {any} data */
  dispatch(name, data) {
    for (const handler of this.#handlers.get(name) ?? []) handler(data);
  }
  // endregion listen

  // region on-start
  // `start` is the reply to `auth`: our full character, plus the first view
  // of the map in `entities`. It has no `name`: `id` is the name.
  /** @param {Entity} data */
  onStart(data) {
    const { entities, ...rest } = data;
    this.me = rest;
    this.#steppedAt.set(this.me, Date.now());
    this.applyEntities(entities);
  }
  // endregion on-start

  // region on-player
  // `player`: our character again, with the fields that changed and more.
  // Merge it: `start` had a few fields that `player` does not repeat.
  /** @param {Entity} data */
  onPlayer(data) {
    const { hitchhikers, ...rest } = data;
    Object.assign(this.me, rest);
    this.#steppedAt.set(this.me, Date.now()); // x and y are new now
    // Hitchhikers: [event, payload] pairs that rode along. Handle them as if
    // they arrived alone.
    for (const [event, payload] of hitchhikers ?? []) this.dispatch(event, payload);
  }
  // endregion on-player

  // region apply-entities
  // `entities`: monsters and players in our view. Each object is the complete
  // state of that entity now, so replace it; never merge.
  /** @param {Entity} data */
  applyEntities(data) {
    if (data.in !== this.me.in) return; // an update for a map instance we already left
    if (data.type === "all") {
      // A full snapshot: forget everything first.
      this.monsters.clear();
      this.players.clear();
    }
    const now = Date.now();
    for (const m of data.monsters) {
      const monster = this.withDefaults(m);
      this.monsters.set(m.id, monster);
      this.#steppedAt.set(monster, now);
    }
    for (const p of data.players) {
      if (p.id === this.me.id) continue; // a "type: all" snapshot can include us
      this.players.set(p.id, p);
      this.#steppedAt.set(p, now);
    }
  }

  // Monsters send only the fields that differ from G.monsters[type]. Add the
  // missing fields from G. `max_hp` is `hp` in G.
  /** @param {Entity} monster @returns {Entity} */
  withDefaults(monster) {
    const def = this.G.monsters[monster.type] ?? {};
    return { ...def, max_hp: def.hp, ...monster }; // the monster's own fields win
  }
  // endregion apply-entities

  // region on-new-map
  // `new_map`: we went through a door, a transporter, or we respawned. The
  // payload has a full snapshot of the new view (always type "all").
  /** @param {Entity} data */
  onNewMap(data) {
    Object.assign(this.me, { map: data.name, in: data.in, x: data.x, y: data.y, m: data.m, moving: false });
    this.#steppedAt.set(this.me, Date.now());
    this.applyEntities(data.entities);
  }
  // endregion on-new-map

  // region advance
  // Moves every entity forward to now: the time since its last advance(), or
  // since the update that brought it. Call it before you read positions. There
  // is no background timer, so nothing moves while you do not look.
  advance() {
    const now = Date.now();
    for (const e of [this.me, ...this.monsters.values(), ...this.players.values()]) {
      step(e, now - (this.#steppedAt.get(e) ?? now));
      this.#steppedAt.set(e, now);
    }
  }
  // endregion advance

  // region distance
  // The distance that the server uses for range checks: the gap between two
  // hit boxes, 0 if they touch (distance(), js/old_common_functions.js:707-740).
  // A box is centred on x, and its bottom edge is y (the feet).
  /** @param {Entity} a @param {Entity} b */
  distance(a, b) {
    // Different maps or instances: "very far", as the server says.
    if ("in" in a && "in" in b && a.in !== b.in) return 99999999;
    if ("map" in a && "map" in b && a.map !== b.map) return 99999999;
    const [aw, ah] = this.#box(a);
    const [bw, bh] = this.#box(b);
    const dx = Math.max(b.x - bw / 2 - (a.x + aw / 2), a.x - aw / 2 - (b.x + bw / 2), 0);
    const dy = Math.max(b.y - bh - a.y, a.y - ah - b.y, 0);
    return Math.hypot(dx, dy);
  }

  // The hit box [width, height]. A monster (it has a `type` that is in
  // G.monsters): G.dimensions[type], times G.monsters[type].size, rounded
  // (get_monster_dimensions, js/old_common_functions.js:692-700). Characters
  // have no `type` field: 26 x 36.
  /** @param {Entity} e @returns {number[]} */
  #box(e) {
    const def = typeof e.type === "string" ? this.G.monsters[e.type] : undefined;
    if (!def) return CHARACTER_BOX;
    const [w, h] = this.G.dimensions[e.type] ?? DEFAULT_MONSTER_BOX;
    return def.size ? [Math.round(w * def.size), Math.round(h * def.size)] : [w, h];
  }
  // endregion distance

  // The closest monster to us (of `type`, if given), or null.
  /** @param {string | null} [type] @returns {Entity | null} */
  nearestMonster(type = null) {
    let best = null;
    let bestDistance = Infinity;
    for (const m of this.monsters.values()) {
      if (type && m.type !== type) continue;
      const d = this.distance(this.me, m);
      if (d < bestDistance) {
        best = m;
        bestDistance = d;
      }
    }
    return best;
  }
}

// region step
// Moves one moving entity toward (going_x, going_y), the way the server does:
// `speed` is in pixels per second, so `ms` milliseconds cover speed * ms / 1000
// pixels. It stops at the target.
/** @param {Entity} e @param {number} ms */
export function step(e, ms) {
  if (!e.moving || ms <= 0) return;
  const dx = e.going_x - e.x;
  const dy = e.going_y - e.y;
  const left = Math.hypot(dx, dy); // the distance still to go
  const travel = (e.speed * ms) / 1000;
  if (travel >= left) {
    // Arrived.
    e.x = e.going_x;
    e.y = e.going_y;
    e.moving = false;
  } else {
    e.x += (dx / left) * travel;
    e.y += (dy / left) * travel;
  }
}
// endregion step
