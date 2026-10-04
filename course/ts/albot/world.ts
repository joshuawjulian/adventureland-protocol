// world.ts: our copy of the game world: our character (`me`), the monsters,
// the other players and the chests. It is the only place that reads the
// world events, so every other module asks the World.
// Everything runs on the one event loop of Node.js: no locks are necessary.
import type { AlSocket } from "./alsocket.ts";
import type { GData } from "./gdata.ts";

// ---- The shapes of the entities ----
// An entity is the server's JSON object, kept as a plain object: `player`
// merges into it and `entities` replaces it, field by field. The interfaces
// name the fields that the course reads; the index signature keeps the rest.

/** The fields of every thing that moves: monsters, players, NPCs and us. */
export interface Entity {
  id: string; // a number as a string for monsters ("12345"); the name for characters
  x: number; // the feet of the entity, in px
  y: number;
  moving?: boolean;
  going_x?: number; // the end of the current walk
  going_y?: number;
  speed?: number; // px per second
  hp?: number;
  max_hp?: number;
  in?: string; // the instance; same as `map`, except in dungeons
  map?: string;
  type?: string; // monsters only: the key into G.monsters
  [field: string]: unknown;
}

/** One monster from `entities`, after withDefaults() adds the fields of G. */
export interface Monster extends Entity {
  type: string;
  hp: number;
  max_hp: number;
  speed: number;
  range: number;
  target?: string | null; // the name of the character that it attacks
}

/** Another player, or an NPC. Other players get the "stranger" view: no items, no gold. */
export interface Player extends Entity {
  ctype: string; // the class
  level: number;
  rip?: boolean | string;
}

/** One inventory slot of `me.items` (null for an empty slot). */
export interface InventoryItem {
  name: string; // the key into G.items
  q?: number; // the quantity, for items that stack
  level?: number; // the upgrade level
}

/** Our character: the `start` payload, with each `player` merged in. Only `id`, no `name`. */
export interface Me extends Entity {
  ctype: string;
  level: number;
  xp: number;
  max_xp: number;
  hp: number;
  max_hp: number;
  mp: number;
  max_mp: number;
  speed: number;
  range: number; // the attack range, px
  gold: number;
  map: string;
  in: string;
  m: number; // the map counter: `move` must send it, or the server ignores the move
  cc?: number; // our call-cost now (node/server.js:996-998)
  rip?: boolean | string; // true (or a gravestone name) while dead
  items: (InventoryItem | null)[];
  s: Record<string, { ms: number }>; // conditions
}

/** `entities`: the full view (type "all") or the changes (type "xy"). */
export interface EntitiesData {
  type: "all" | "xy";
  in: string;
  map: string;
  monsters: Entity[]; // only the fields that differ from G.monsters[type]
  players: Player[];
}

export type StartData = Me & { entities: EntitiesData };
export type Hitchhiker = [event: string, payload: unknown];
export type PlayerData = Partial<Me> & { hitchhikers?: Hitchhiker[] };

export interface NewMapData {
  name: string; // the map
  in: string;
  x: number;
  y: number;
  m: number;
  entities: EntitiesData; // always type "all"
}

/** `drop`: a chest for us (or our party). */
export interface ChestDrop {
  id: string;
  x: number;
  y: number;
  map: string;
  chest: string; // the look: "chest3", ...
  items: number; // how many items are in it
}

// The hit box of a character: 26 x 36 px (node/server.js:11782-11783).
const PLAYER_WIDTH = 26;
const PLAYER_HEIGHT = 36;
// get_monster_dimensions (js/old_common_functions.js:692-700): 24 x 24 when
// G.dimensions has no entry for the monster type.
const DEFAULT_MONSTER_SIZE = [24, 24];
// distance() returns this for two entities on different maps (old_common_functions.js:711-713).
const FAR = 99999999;

// region step
// Move one entity forward in time, the way the server does: speed is in px per
// second, so `ms` milliseconds cover speed * ms / 1000 px of the straight line
// to (going_x, going_y). The server sends no position while an entity walks,
// so this is the only way to know where it is now.
export function step(e: Entity, ms: number): void {
  if (!e.moving || e.going_x === undefined || e.going_y === undefined) return;
  const dx = e.going_x - e.x;
  const dy = e.going_y - e.y;
  const left = Math.hypot(dx, dy); // the distance still to go
  const travel = ((e.speed ?? 0) * ms) / 1000;
  if (travel >= left) {
    // Arrived. The server also stops the entity at the exact end point.
    e.x = e.going_x;
    e.y = e.going_y;
    e.moving = false;
  } else {
    e.x += (dx / left) * travel;
    e.y += (dy / left) * travel;
  }
}
// endregion step

export class World {
  readonly sock: AlSocket;
  readonly G: GData;
  me = {} as Me; // empty until `start`
  readonly monsters = new Map<string, Monster>(); // id -> monster
  readonly players = new Map<string, Player>(); // id -> other player or NPC (never us)
  readonly chests = new Map<string, ChestDrop>(); // chest id -> the `drop` payload

  #handlers = new Map<string, ((data: unknown) => void)[]>(); // event name -> handlers
  // The time (ms) at which each entity's x/y was last correct: the last update
  // from the server, or the last advance(). A WeakMap, so that an entity that
  // leaves the maps leaves this table too.
  #stamps = new WeakMap<Entity, number>();

  // region constructor
  // Create the World BEFORE you send `loaded` and `auth`: the handlers must be
  // there when `start` comes.
  constructor(sock: AlSocket, G: GData) {
    this.sock = sock;
    this.G = G;
    this.listen<StartData>("start", (d) => this.onStart(d));
    this.listen<PlayerData>("player", (d) => this.onPlayer(d));
    this.listen<EntitiesData>("entities", (d) => this.applyEntities(d));
    this.listen<{ id: string }>("death", (d) => this.monsters.delete(d.id));
    this.listen<{ id: string }>("disappear", (d) => {
      this.monsters.delete(d.id);
      this.players.delete(d.id);
    });
    this.listen<NewMapData>("new_map", (d) => this.onNewMap(d));
    this.listen<ChestDrop>("drop", (d) => this.chests.set(d.id, d));
    this.listen<{ id: string }>("chest_opened", (d) => this.chests.delete(d.id));
    // The server's x/y when ours was more than 132 px off (node/server.js:11249-11257).
    this.listen<{ x: number; y: number }>("correction", (d) => {
      this.me.x = d.x;
      this.me.y = d.y;
      this.#stamp(this.me);
    });
  }
  // endregion constructor

  // region listen
  // One table from event name to handlers. Events can come alone, or as
  // "hitchhikers" inside a `player` update. Both reach the handlers through
  // dispatch(), so a handler never has to know how its event came.
  listen<T>(name: string, handler: (data: T) => void): void {
    let list = this.#handlers.get(name);
    if (!list) {
      list = [];
      this.#handlers.set(name, list);
      // The first listen for a name subscribes on the socket, one time.
      this.sock.on(name, (data) => this.dispatch(name, data));
    }
    // The cast: the caller says what the payload is. Nothing checks it at run time.
    list.push(handler as (data: unknown) => void);
  }

  dispatch(name: string, data: unknown): void {
    for (const handler of this.#handlers.get(name) ?? []) {
      try {
        handler(data);
      } catch (err) {
        // One bad handler must not stop the others (or the other hitchhikers).
        console.error(`handler for "${name}" threw:`, err);
      }
    }
  }
  // endregion listen

  // region on-start
  // `start` is our full character plus the full view (`entities`, type "all").
  onStart(data: StartData): void {
    const { entities, ...me } = data;
    this.me = me as Me;
    this.#stamp(this.me);
    this.applyEntities(entities);
  }
  // endregion on-start

  // region on-player
  // `player` is our character again, after a change. Merge it: `start` had
  // fields that `player` does not repeat. Then hand each hitchhiker
  // ([event, payload]) to its handlers, as if it came alone.
  onPlayer(data: PlayerData): void {
    const { hitchhikers, ...changes } = data;
    Object.assign(this.me, changes);
    this.#stamp(this.me);
    for (const [event, payload] of hitchhikers ?? []) this.dispatch(event, payload);
  }
  // endregion on-player

  // region apply-entities
  applyEntities(data: EntitiesData): void {
    if (data.in !== this.me.in) return; // an update for an instance that we left
    if (data.type === "all") {
      // A full view: what is not in it is not near us any more.
      this.monsters.clear();
      this.players.clear();
    }
    // Each object is the complete state of that entity now: replace, do not merge.
    for (const m of data.monsters) {
      const monster = this.withDefaults(m);
      this.monsters.set(monster.id, monster);
      this.#stamp(monster);
    }
    for (const p of data.players) {
      if (p.id === this.me.id) continue; // "all" includes us; `me` comes from `player`
      this.players.set(p.id, p);
      this.#stamp(p);
    }
  }

  // A monster sends only the fields that differ from G.monsters[type]
  // (node/server.js:1003-1071). Fill the rest from G. Its own fields win.
  withDefaults(m: Entity): Monster {
    const def = this.G.monsters[m.type ?? ""];
    // max_hp is not a field of G: it is G's `hp`, the hp at full health.
    return { ...def, max_hp: def?.hp, ...m } as Monster;
  }
  // endregion apply-entities

  // region on-new-map
  // A door, a transport or a respawn: a new map, a new position, a new map
  // counter `m`, and a new full view.
  onNewMap(data: NewMapData): void {
    Object.assign(this.me, {
      map: data.name,
      in: data.in,
      x: data.x,
      y: data.y,
      m: data.m,
      moving: false,
      going_x: data.x,
      going_y: data.y,
    });
    this.#stamp(this.me);
    this.applyEntities(data.entities);
  }
  // endregion on-new-map

  // region advance
  // Move every entity forward to now. There is no timer in the background:
  // call advance() before you read positions.
  advance(): void {
    const now = Date.now();
    const move = (e: Entity) => {
      step(e, now - (this.#stamps.get(e) ?? now));
      this.#stamps.set(e, now);
    };
    if (this.me.id) move(this.me);
    for (const m of this.monsters.values()) move(m);
    for (const p of this.players.values()) move(p);
  }
  // endregion advance

  #stamp(e: Entity): void {
    this.#stamps.set(e, Date.now());
  }

  // region distance
  // The distance that the server uses for range: the gap between two hit boxes
  // (distance, js/old_common_functions.js:707-740). x is the center of a box,
  // y is its bottom (the feet). 0 when the boxes touch.
  distance(a: Entity, b: Entity): number {
    if (a.in !== undefined && b.in !== undefined && a.in !== b.in) return FAR;
    if (a.map !== undefined && b.map !== undefined && a.map !== b.map) return FAR;
    const [aw, ah] = this.#size(a);
    const [bw, bh] = this.#size(b);
    const dx = Math.max(b.x - bw / 2 - (a.x + aw / 2), a.x - aw / 2 - (b.x + bw / 2), 0);
    const dy = Math.max(b.y - bh - a.y, a.y - ah - b.y, 0);
    return Math.hypot(dx, dy);
  }

  // A monster's box comes from its type: G.dimensions[type], times
  // G.monsters[type].size (get_monster_dimensions, old_common_functions.js:692-700).
  // Every character has the same box.
  #size(e: Entity): number[] {
    const def = e.type !== undefined ? this.G.monsters[e.type] : undefined;
    if (!def || e.type === undefined) return [PLAYER_WIDTH, PLAYER_HEIGHT];
    const [w, h] = this.G.dimensions[e.type] ?? DEFAULT_MONSTER_SIZE;
    return def.size ? [Math.round(w * def.size), Math.round(h * def.size)] : [w, h];
  }
  // endregion distance

  /** The closest monster to `me` (of `type`, if given), or null. */
  nearestMonster(type: string | null = null): Monster | null {
    let best: Monster | null = null;
    let bestDistance = Infinity;
    for (const m of this.monsters.values()) {
      if (type !== null && m.type !== type) continue;
      const d = this.distance(this.me, m);
      if (d < bestDistance) {
        best = m;
        bestDistance = d;
      }
    }
    return best;
  }
}
