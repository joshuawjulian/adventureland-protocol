// actions.ts: the things that our character does: move, attack, heal, loot,
// respawn. Each one sends its event through the Budget, and the ones that wait
// for a reply register the wait BEFORE they send (a fast reply must not come
// first). Part 3 puts the other actions in travel, items and party.
import type { AlSocket } from "./alsocket.ts";
import type { Budget } from "./budget.ts";
import type { Cooldowns } from "./cooldowns.ts";
import type { World } from "./world.ts";

/**
 * `game_response`, in one shape. The server sends it as an object
 * {response, place, failed: true, ...} or {response, place, success: true, ...}
 * (node/server_functions.js:3393-3446), or as a bare string ("upgrade_no_item").
 */
export interface GameResponse {
  response: string; // the code: "data", "cooldown", "too_far", ...
  place?: string; // the event (or skill) that it answers
  failed: boolean;
  success: boolean; // a successful attack has no `success` key: so read `failed`
  ms?: number; // cooldown, not_ready, cant_respawn: the ms left
  [field: string]: unknown; // the fields of each code
}

/** `chest_opened`: the reply to open_chest. */
export interface ChestOpened {
  id: string;
  gone?: boolean; // the chest was not there (opened already, or never ours)
  gold?: number; // after the 10 % tax
  items?: { name: string; q?: number; looter: string | null }[];
}

interface MovePayload {
  x: number; // where we are now (the server checks it)
  y: number;
  going_x: number; // where we go
  going_y: number;
  m: number; // the map counter of `me`
}

type Stat = "hp" | "mp";

// 12 s: B.rip_time, the wait after a death before `respawn` works (node/server.js:224).
const RIP_TIME_MS = 12_000;
// 250 ms more than the walk time of moveTo: room for the network delay.
const MOVE_SLACK_MS = 250;

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

// region normalize
/** A string becomes {response, failed: false, success: false}; an object gets those two defaults. */
export function normalize(data: unknown): GameResponse {
  if (typeof data === "string") return { response: data, failed: false, success: false };
  return { failed: false, success: false, ...(data as Partial<GameResponse>) } as GameResponse;
}

/** A waitFor predicate: an object game_response for this `place`. */
export function responseFor(place: string): (data: unknown) => boolean {
  return (data) => typeof data === "object" && data !== null && (data as GameResponse).place === place;
}
// endregion normalize

export class Actions {
  readonly sock: AlSocket;
  readonly world: World;
  readonly cooldowns: Cooldowns;
  readonly budget: Budget;
  #diedAt = 0; // Date.now() of our last death, 0 if not known

  constructor(sock: AlSocket, world: World, cooldowns: Cooldowns, budget: Budget) {
    this.sock = sock;
    this.world = world;
    this.cooldowns = cooldowns;
    this.budget = budget;
    // The server says "defeated_by_a_monster" when we die (node/server.js:13884-13940).
    world.listen<GameResponse | string>("game_response", (d) => {
      if (typeof d === "object" && d.response === "defeated_by_a_monster") this.#diedAt = Date.now();
    });
  }

  // region request
  // Send `event` and wait for the game_response whose `place` matches.
  // null when no reply comes in time: some failures have no game_response
  // (an attack on a monster that is gone gets `disappear` with reason "not_there").
  async request(event: string, payload: object = {}, place = event, timeoutMs = 2000): Promise<GameResponse | null> {
    // The wait starts here, before the emit. `.then` turns a timeout (or a
    // closed socket) into null, so the promise never rejects unhandled.
    const reply = this.sock.waitFor("game_response", responseFor(place), timeoutMs).then(normalize, () => null);
    await this.budget.emit(event, payload);
    return reply;
  }
  // endregion request

  // region move-to
  /** Starts a straight walk to (x, y) on this map. It does not wait. */
  async move(x: number, y: number): Promise<void> {
    this.world.advance(); // `me` must be where we are now, both for the payload and for later steps
    const me = this.world.me;
    // `m` must equal the server's map counter, or the server ignores the move with no reply.
    const payload: MovePayload = { x: me.x, y: me.y, going_x: x, going_y: y, m: me.m };
    // The server does the same with its copy (node/server.js:11183-11271).
    me.going_x = x;
    me.going_y = y;
    me.moving = true;
    await this.budget.emit("move", payload);
  }

  // A straight line only (Part 3 adds walkTo with a path around the walls).
  // The server sends no "arrived" event, so wait for the walk time, then look.
  async moveTo(x: number, y: number): Promise<boolean> {
    await this.move(x, y);
    const me = this.world.me;
    const walkMs = (Math.hypot(x - me.x, y - me.y) / me.speed) * 1000; // speed is px per second
    await sleep(walkMs + MOVE_SLACK_MS);
    this.world.advance();
    // A `correction` or a jail moves us somewhere else: then the walk failed.
    return me.going_x === x && me.going_y === y && Math.hypot(me.x - x, me.y - y) < 1;
  }
  // endregion move-to

  // region attack
  // A success is the projectile data {response: "data", place: "attack", pid,
  // eta, ...} with no `success` key. A failure has `failed: true` (cooldown,
  // too_far, ...). The damage comes later, as a `hit` event.
  attack(id: string): Promise<GameResponse | null> {
    return this.request("attack", { id });
  }
  // endregion attack

  // region heal
  // `stat` is "hp" or "mp". Drink a potion that gives `stat` (on the server,
  // a potion is "equipped" with consume: true, node/server.js:7798-7855). With
  // no potion, use the free regeneration (`use`, node/server.js:11988-12025).
  // All of them share the one potion timer: skip (false) while it runs.
  async heal(stat: Stat): Promise<boolean> {
    if (!this.cooldowns.ready("potion")) return false;
    const num = this.#findPotion(stat);
    const r =
      num >= 0
        ? await this.request("equip", { num, consume: true })
        : await this.request("use", { item: stat });
    return r !== null && !r.failed;
  }

  /** The first inventory slot with a potion that gives `stat`, or -1. */
  #findPotion(stat: Stat): number {
    const G = this.world.G;
    return this.world.me.items.findIndex(
      (item) => item !== null && (G.items[item.name]?.gives ?? []).some(([s]) => s === stat),
    );
  }
  // endregion heal

  // region open-chests
  /** Opens one chest. Its reply is `chest_opened` with the same id; null if none comes. */
  async openChest(id: string): Promise<ChestOpened | null> {
    const opened = this.sock.waitFor<ChestOpened>("chest_opened", (d) => d.id === id, 2000).catch(() => null);
    await this.budget.emit("open_chest", { id });
    return opened;
  }

  /** Opens each chest that we know of. Returns how many opened. */
  async openChests(): Promise<number> {
    let count = 0;
    for (const id of [...this.world.chests.keys()]) { // a copy: chest_opened removes the chest
      const r = await this.openChest(id);
      if (r && !r.gone) count++;
      // Also with no reply (a full bag: "loot_no_space"; the chest stays on the
      // server, node/server.js:11315): forget it, so that we do not try it forever.
      this.world.chests.delete(id);
    }
    return count;
  }
  // endregion open-chests

  // region respawn
  /** The ms until `respawn` can work (0 when we do not know the time of the death). */
  msUntilRespawn(): number {
    return this.#diedAt ? Math.max(0, this.#diedAt + RIP_TIME_MS - Date.now()) : 0;
  }

  // Call this while me.rip is set. Wait the rest of the 12 s, then send `respawn`.
  // If we died before this program started, we do not know when: then the server
  // replies "cant_respawn" with the ms left, and we try one more time after them.
  async respawn(): Promise<boolean> {
    const wait = this.msUntilRespawn();
    if (wait > 0) await sleep(wait);
    let r = await this.request("respawn", {}, "respawn", 3000);
    if (r?.response === "cant_respawn") {
      await sleep((r.ms ?? 1000) + 100); // +100 ms: our clock and the server's are not the same
      r = await this.request("respawn", {}, "respawn", 3000);
    }
    return r !== null && !r.failed;
  }
  // endregion respawn
}
