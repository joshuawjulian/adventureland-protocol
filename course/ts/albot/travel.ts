// travel.ts: walk around walls, go through doors, use the transporter, and
// get out of jail. Node.js 22.18+. No packages.
//
// It uses the grid of pathfind.ts for the walls, and Actions.moveTo for each
// straight part of the walk.
import { Grid } from "./pathfind.ts";
import type { Actions } from "./actions.ts";
import type { GData } from "./gdata.ts";
import type { World } from "./world.ts";

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

// The distances of the server (node/server.js:221-223): a door works within
// 112 px of its box, the transporter NPC within 160 px of the NPC.
const DOOR_DIST = 112;
const TRANSPORTER_DIST = 160;
// How long to wait for `new_map` after a transport. Live sends it at once for
// a door; for the bank it comes after the account loads (in_progress).
const NEW_MAP_MS = 5000;

/** One step of a route: stand at (x, y) on `map`, then transport to `to`, spawn `spawn`. */
export interface Hop {
  map: string;
  x: number;
  y: number;
  to: string;
  spawn: number;
  by: "door" | "transporter";
}

/** The parts of G.maps[map] that travel reads. */
interface MapDef {
  // [x, y, width, height, to map, to spawn, own spawn, lock?]
  doors?: [number, number, number, number, string, number?, number?, string?][];
  spawns: number[][];
  npcs?: { id: string; position?: number[]; positions?: number[][] }[];
}

export class Travel {
  readonly world: World;
  readonly act: Actions;
  readonly G: GData;

  constructor(world: World, act: Actions) {
    this.world = world;
    this.act = act;
    this.G = world.G;
  }

  #maps(): Record<string, MapDef> {
    return this.G.maps as Record<string, MapDef>;
  }

  // region walk-to
  // Walks to (x, y) on this map, around the walls. If (x, y) is not walkable,
  // it walks to the nearest walkable point (at most 320 px away). Returns true
  // when we arrived; false when there is no path, or when something stopped
  // the walk: a `correction`, a death, a door, or jail. The caller decides
  // again on its next tick.
  async walkTo(x: number, y: number): Promise<boolean> {
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
  async transport(map: string, spawn: number): Promise<boolean> {
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
  async leaveJail(): Promise<boolean> {
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
  exits(map: string): Hop[] {
    const def = this.#maps()[map];
    if (!def) return [];
    const out: Hop[] = [];
    for (const door of def.doors ?? []) {
      if (door[7]) continue; // a locked door ("ulocked", ...): it needs a key first
      const spawn = def.spawns[door[6] ?? 0];
      if (spawn) out.push({ map, x: spawn[0], y: spawn[1], to: door[4], spawn: door[5] ?? 0, by: "door" });
    }
    const npc = (def.npcs ?? []).find((n) => n.id === "transporter");
    const pos = npc?.position ?? npc?.positions?.[0];
    if (pos) {
      // G.npcs.transporter.places: map -> the spawn where she sends you.
      const npcs = this.G.npcs as Record<string, { places?: Record<string, number> }>;
      for (const [to, spawn] of Object.entries(npcs.transporter?.places ?? {})) {
        if (to !== map) out.push({ map, x: pos[0], y: pos[1], to, spawn: Number(spawn), by: "transporter" });
      }
    }
    return out;
  }

  // The fewest hops from `from` to `to`: a breadth-first search on the graph
  // of maps. Returns [] when we are there, or null when no route exists.
  route(from: string, to: string): Hop[] | null {
    if (from === to) return [];
    const came = new Map<string, Hop | null>([[from, null]]); // map -> the hop that reached it
    const queue = [from];
    while (queue.length) {
      const map = queue.shift()!;
      for (const hop of this.exits(map)) {
        if (came.has(hop.to) || !this.#maps()[hop.to]) continue;
        came.set(hop.to, hop);
        if (hop.to === to) {
          const hops: Hop[] = [];
          for (let h: Hop | null = hop; h; h = came.get(h.map) ?? null) hops.unshift(h);
          return hops;
        }
        queue.push(hop.to);
      }
    }
    return null;
  }

  // Goes to `map` along route(): for each hop, walk to the door (or to the
  // transporter), then transport. Returns true when we are on `map`.
  async goToMap(map: string): Promise<boolean> {
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
  async #waitUntil(test: () => boolean, ms: number): Promise<boolean> {
    for (const end = performance.now() + ms; performance.now() < end; await sleep(50)) if (test()) return true;
    return test();
  }
}
