// budget.js: stay under the server's call-cost limit. Node.js 22.18+.
//
// The server adds up a "call-cost" for each socket over the last 4 s. Over
// 200 (50 before `auth`), it sends `disconnect_reason` "limitdc" and closes
// the socket (node/server.js:4892-4943). Every event costs 1, plus the extra
// below. Budget.emit() waits until the last 4 s have room, then sends.

// region budget
// The extra call-cost per event (node/server.js:242-258, the table CC).
/** @type {Record<string, number>} */
export const EXTRA_COST = {
  auth: 2, move: 1.5, players: 12, secondhands: 16, friend: 24, send_updates: 12,
  cruise: 10, random_look: 10, equip: 3, unequip: 6, tracker: 50, ccreport: 3,
};
// 150, not 200: the server also charges for some `player` updates that it
// sends back to us (resend), and we cannot see those costs.
export const LIMIT = 150;
export const WINDOW_MS = 4000; // the server's window: 4 s

const sleep = (/** @type {number} */ ms) => new Promise((resolve) => setTimeout(resolve, ms));

export class Budget {
  /** @type {[number, number][]} [time, cost] of each call in the window, oldest first */
  #calls = [];

  /**
   * @param {import("./alsocket.js").AlSocket} sock
   * @param {import("./world.js").World} world
   */
  constructor(sock, world) {
    this.sock = sock;
    // A map change costs 8 more (add_call_cost(player, 8, "transport"),
    // node/server.js:4726). It comes from the server, so count it on `new_map`.
    world.listen("new_map", () => this.#calls.push([Date.now(), 8]));
  }

  /** @param {string} event */
  cost(event) {
    return 1 + (EXTRA_COST[event] ?? 0);
  }

  // The total call-cost of the last 4 s.
  spent() {
    const now = Date.now();
    while (this.#calls.length && now - this.#calls[0][0] >= WINDOW_MS) this.#calls.shift(); // forget old calls
    return this.#calls.reduce((sum, [, c]) => sum + c, 0);
  }

  // Waits until the event fits under LIMIT, records its cost, then sends it.
  /** @param {string} event @param {any} [payload] */
  async emit(event, payload) {
    const cost = this.cost(event);
    while (this.spent() + cost > LIMIT) {
      // Sleep until the oldest call leaves the window (+10 ms of margin).
      await sleep(WINDOW_MS - (Date.now() - this.#calls[0][0]) + 10);
    }
    this.#calls.push([Date.now(), cost]);
    this.sock.emit(event, payload);
  }
}
// endregion budget
