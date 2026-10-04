// actions.js: the things our character does: move, attack, heal, loot,
// respawn. Each method sends one event (through the Budget) and, where the
// server answers, waits for the answer. Node.js 22.18+. No packages.
//
// The rule for every wait: register it BEFORE you send. A fast answer can
// arrive before the next line of code runs.

/** @typedef {{response: string, failed: boolean, success: boolean, place?: string, [key: string]: any}} GameResponse */

const sleep = (/** @type {number} */ ms) => new Promise((resolve) => setTimeout(resolve, ms));

// The wait before a dead character can respawn: B.rip_time (node/server.js:224).
const RIP_MS = 12000;

// region normalize
// `game_response` arrives as an object ({response, place, failed, ...}) or as
// a bare string ("upgrade_no_item"). Make it one shape. A success often has
// no `success` key (a successful attack has none), so only `failed` is sure.
/** @param {any} data @returns {GameResponse} */
export function normalize(data) {
  if (typeof data === "string") return { response: data, failed: false, success: false };
  return { failed: false, success: false, ...data };
}

// A waitFor predicate: an object game_response about this `place` (the
// server sets `place` to the event name that the answer is for).
/** @param {string} place */
export function responseFor(place) {
  return (/** @type {any} */ d) => typeof d === "object" && d !== null && d.place === place;
}
// endregion normalize

export class Actions {
  /**
   * @param {import("./alsocket.js").AlSocket} sock
   * @param {import("./world.js").World} world
   * @param {import("./cooldowns.js").Cooldowns} cooldowns
   * @param {import("./budget.js").Budget} budget
   */
  constructor(sock, world, cooldowns, budget) {
    this.sock = sock;
    this.world = world;
    this.cooldowns = cooldowns;
    this.budget = budget;
    // When we died (Date.now() ms), for respawn(). 0: we did not see it.
    this.diedAt = 0;
    world.listen("game_response", (d) => {
      if (d?.response === "defeated_by_a_monster") this.diedAt = Date.now();
    });
  }

  // region request
  // Sends `event` and waits for the game_response whose `place` matches.
  // Returns the normalized answer (check `.failed`), or null if no answer
  // came in `timeoutMs` (2 s: a normal answer takes one round trip).
  /**
   * @param {string} event
   * @param {any} payload
   * @param {string} [place]
   * @param {number} [timeoutMs]
   * @returns {Promise<GameResponse | null>}
   */
  async request(event, payload, place = event, timeoutMs = 2000) {
    const reply = this.sock.waitFor("game_response", responseFor(place), timeoutMs);
    await this.budget.emit(event, payload);
    try {
      return normalize(await reply);
    } catch (err) {
      if (String(err?.message).startsWith("timed out")) return null;
      throw err; // the socket closed: the caller must know
    }
  }
  // endregion request

  // region move-to
  // Starts a straight walk to (x, y) on this map. No answer comes: the server
  // accepts the move without a reply, or sends `correction`.
  /** @param {number} x @param {number} y */
  async move(x, y) {
    const me = this.world.me;
    // `m` must equal the server's map counter, or the server ignores the move.
    await this.budget.emit("move", { x: me.x, y: me.y, going_x: x, going_y: y, m: me.m });
    Object.assign(me, { going_x: x, going_y: y, moving: true }); // the server does the same
  }

  // Walks in a straight line to (x, y) and waits until we should be there.
  // Returns true if we arrived. It does not go around walls: a move through a
  // wall sends the character to jail (Part 3 adds walkTo for that).
  /** @param {number} x @param {number} y */
  async moveTo(x, y) {
    this.world.advance(); // our position now, for the `move` payload
    const me = this.world.me;
    const eta = (Math.hypot(x - me.x, y - me.y) / me.speed) * 1000; // ms
    await this.move(x, y);
    await sleep(eta + 250); // 250 ms: room for the network delay
    this.world.advance();
    return Math.hypot(me.x - x, me.y - y) < 1 && me.going_x === x && me.going_y === y;
  }
  // endregion move-to

  // region attack
  // Attacks a monster or a player by id. The answer: a game_response with
  // place "attack" (no `success` key on success; `failed` with a reason such
  // as "cooldown" or "too_far"), or null. A target that is not there gets
  // `disappear` with reason "not_there" instead, so then we see null.
  /** @param {string} id */
  async attack(id) {
    return this.request("attack", { id });
  }
  // endregion attack

  // region heal
  // `stat` is "hp" or "mp". Drinks a potion that gives `stat` if one is in the
  // inventory (`equip` with consume: true), else uses the free regeneration
  // (`use`). All of them share the "potion" timer: skip (false) if it is not ready.
  /** @param {"hp" | "mp"} stat */
  async heal(stat) {
    if (!this.cooldowns.ready("potion")) return false;
    const G = this.world.G;
    const items = this.world.me.items ?? [];
    // G.items[name].gives is a list of [stat, amount] pairs.
    const num = items.findIndex(
      (/** @type {any} */ item) => item && G.items[item.name]?.gives?.some((/** @type {any[]} */ [s]) => s === stat),
    );
    const r = num >= 0
      ? await this.request("equip", { num, consume: true })
      : await this.request("use", { item: stat });
    // On success the server sent `eval` "pot_timeout(ms)" first; Cooldowns read it.
    return r !== null && !r.failed;
  }
  // endregion heal

  // region open-chests
  // Opens one chest and waits for `chest_opened` with its id: {id, gold,
  // items, ...}, or {id, gone: true}. null if no answer came (for example
  // the game_response "loot_no_space": the bag is full).
  /** @param {string} id @returns {Promise<any>} */
  async openChest(id) {
    const opened = this.sock.waitFor("chest_opened", (d) => d?.id === id, 2000);
    await this.budget.emit("open_chest", { id });
    try {
      return await opened;
    } catch {
      return null;
    }
  }

  // Opens each chest that we know (from `drop`). Returns how many opened.
  async openChests() {
    let count = 0;
    for (const id of [...this.world.chests.keys()]) {
      const r = await this.openChest(id);
      if (r && !r.gone) count++;
      this.world.chests.delete(id); // also when there was no answer: do not try forever
    }
    return count;
  }
  // endregion open-chests

  // region respawn
  // After death (`me.rip` is set), the server accepts `respawn` only after
  // 12 s. Wait the rest of that time, then send it. If the server still says
  // "cant_respawn" (we did not see the death, so diedAt was 0), it gives the
  // `ms` left: wait that, and try one more time.
  async respawn() {
    const wait = this.diedAt + RIP_MS - Date.now();
    if (wait > 0) await sleep(wait);
    for (let attempt = 0; attempt < 2; attempt++) {
      // 3 s: the answer comes after `new_map` and `player`.
      const r = await this.request("respawn", {}, "respawn", 3000);
      if (!r) return false;
      if (r.response !== "cant_respawn") return !r.failed;
      await sleep(r.ms + 100); // +100 ms: our clock and the server's are not the same
    }
    return false;
  }
  // endregion respawn
}
