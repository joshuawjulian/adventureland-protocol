// travel.js: walk around walls, go through doors, use the transporter, and
// get out of jail. Node.js 22.18+. No packages.
//
// It uses the grid of pathfind.js for the walls, and Actions.moveTo for each
// straight part of the walk.
import { Grid } from "./pathfind.js";

const sleep = (/** @type {number} */ ms) => new Promise((resolve) => setTimeout(resolve, ms));

// The distances of the server (node/server.js:221-223): a door works within
// 112 px of its box, the transporter NPC within 160 px of the NPC.
const DOOR_DIST = 112;
const TRANSPORTER_DIST = 160;
// How long to wait for `new_map` after a transport. Live sends it at once for
// a door; for the bank it comes after the account loads (in_progress).
const NEW_MAP_MS = 5000;

/** @typedef {{map: string, x: number, y: number, to: string, spawn: number, by: "door" | "transporter"}} Hop */

export class Travel {
  /**
   * @param {import("./world.js").World} world
   * @param {import("./actions.js").Actions} act
   */
  constructor(world, act) {
    this.world = world;
    this.act = act;
    this.G = world.G;
  }

  // region walk-to
  // Walks to (x, y) on this map, around the walls. If (x, y) is not walkable,
  // it walks to the nearest walkable point (at most 320 px away). Returns true
  // when we arrived; false when there is no path, or when something stopped
  // the walk: a `correction`, a death, a door, or jail. The caller decides
  // again on its next tick.
  /** @param {number} x @param {number} y @returns {Promise<boolean>} */
  async walkTo(x, y) {
    this.world.advance();
    const me = this.world.me;
    const map = me.map;
    const m = me.m; // the map counter: it changes on each map change
    const grid = Grid.forMap(this.G, map);
    if (!grid.safe(x, y)) {
      const k = grid.nearestFree(x, y);
      if (k < 0) return false;
      [x, y] = grid.point(k);
    }
    const path = grid.findPath(me.x, me.y, x, y);
    if (!path) return false;
    for (const [px, py] of path) {
      const arrived = await this.act.moveTo(px, py);
      if (me.map !== map || me.m !== m || me.rip) return false; // we left this map, or died
      if (!arrived) return false; // a correction: our position was wrong
    }
    return true;
  }
  // endregion walk-to

  // region transport
  // Sends `transport` {to, s}: through a door near us, or with the transporter
  // NPC near us. Then waits until `new_map` puts us on `map`. The server
  // answers a door with success and sends `new_map` first; the bank answers
  // {in_progress: true}, and `new_map` comes later (node/server.js:5887-6056).
  /** @param {string} map @param {number} spawn @returns {Promise<boolean>} */
  async transport(map, spawn) {
    const me = this.world.me;
    const m = me.m;
    const r = await this.act.request("transport", { to: map, s: spawn });
    if (!r || r.failed) return false; // for example transport_cant_reach: too far from the door
    return this.#waitUntil(() => me.m !== m && me.map === map, NEW_MAP_MS);
  }
  // endregion transport

  // region leave-jail
  // A line violation (a `move` from or to a point that is not walkable) sends
  // the character to the map `jail`. `leave` takes it to `main` spawn 0, the
  // town (node/server.js:5864-5885). It fails while the character is dead,
  // or with more than 5 monsters on it.
  /** @returns {Promise<boolean>} */
  async leaveJail() {
    const me = this.world.me;
    const r = await this.act.request("leave", {});
    if (!r || r.failed) return false;
    return this.#waitUntil(() => me.map !== "jail", NEW_MAP_MS);
  }
  // endregion leave-jail

  // region route
  // The ways out of `map`: each door that needs no key, and each place of the
  // transporter if the map has one. A door [x, y, w, h, to, to_spawn,
  // own_spawn, lock] works from its own spawn point (door[6]); the server
  // measures from the box of the door at that spawn (node/server.js:5899-5910).
  /** @param {string} map @returns {Hop[]} */
  exits(map) {
    const def = this.G.maps[map];
    if (!def) return [];
    /** @type {Hop[]} */
    const out = [];
    for (const door of def.doors ?? []) {
      if (door[7]) continue; // a locked door ("ulocked", ...): it needs a key first
      const spawn = def.spawns[door[6]];
      if (spawn) out.push({ map, x: spawn[0], y: spawn[1], to: door[4], spawn: door[5] ?? 0, by: "door" });
    }
    const npc = (def.npcs ?? []).find((/** @type {any} */ n) => n.id === "transporter");
    const pos = npc?.position ?? npc?.positions?.[0];
    if (pos) {
      // G.npcs.transporter.places: map -> the spawn where she sends you.
      for (const [to, spawn] of Object.entries(this.G.npcs.transporter?.places ?? {})) {
        if (to !== map) out.push({ map, x: pos[0], y: pos[1], to, spawn: Number(spawn), by: "transporter" });
      }
    }
    return out;
  }

  // The fewest hops from `from` to `to`: a breadth-first search on the graph
  // of maps. Returns [] when we are there, or null when no route exists.
  /** @param {string} from @param {string} to @returns {Hop[] | null} */
  route(from, to) {
    if (from === to) return [];
    /** @type {Map<string, Hop | null>} map -> the hop that reached it */
    const came = new Map([[from, null]]);
    const queue = [from];
    while (queue.length) {
      const map = /** @type {string} */ (queue.shift());
      for (const hop of this.exits(map)) {
        if (came.has(hop.to) || !this.G.maps[hop.to]) continue;
        came.set(hop.to, hop);
        if (hop.to === to) {
          /** @type {Hop[]} */
          const hops = [];
          for (let h = hop; h; h = came.get(h.map) ?? null) hops.unshift(h);
          return hops;
        }
        queue.push(hop.to);
      }
    }
    return null;
  }

  // Goes to `map` along route(): for each hop, walk to the door (or to the
  // transporter), then transport. Returns true when we are on `map`.
  /** @param {string} map @returns {Promise<boolean>} */
  async goToMap(map) {
    const hops = this.route(this.world.me.map, map);
    if (!hops) return false;
    for (const hop of hops) {
      if (!(await this.walkTo(hop.x, hop.y))) return false;
      // walkTo can stop short of the point (at the nearest walkable cell).
      // The server then says "transport_cant_reach"; do not even ask.
      const me = this.world.me;
      const reach = hop.by === "door" ? DOOR_DIST : TRANSPORTER_DIST;
      if (Math.hypot(me.x - hop.x, me.y - hop.y) > reach) return false;
      if (!(await this.transport(hop.to, hop.spawn))) return false;
    }
    return this.world.me.map === map;
  }
  // endregion route

  // Polls `test` every 50 ms until it is true, or until `ms` have passed.
  /** @param {() => boolean} test @param {number} ms */
  async #waitUntil(test, ms) {
    for (const end = performance.now() + ms; performance.now() < end; await sleep(50)) if (test()) return true;
    return test();
  }
}
