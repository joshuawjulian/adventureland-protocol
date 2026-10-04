// budget.ts: keep our call-cost under the server's limit, so that the server
// never kicks us with "limitdc".
// Everything runs on the one event loop of Node.js: no locks are necessary.
import type { AlSocket } from "./alsocket.ts";
import type { World } from "./world.ts";

// region budget
// The server allows 200 call-cost per 4 s on each socket (node/server.js:257,
// `limits.calls`; 50 before `auth`). Each event costs 1, plus the extra cost
// below (node/server.js:242-258, CC; added at :4936). Over the limit, the
// server sends disconnect_reason "limitdc" and closes the socket (:4939-4944).
export const EXTRA_COST: Readonly<Record<string, number>> = {
  auth: 2,
  move: 1.5,
  players: 12,
  secondhands: 16,
  friend: 24,
  send_updates: 12,
  cruise: 10,
  random_look: 10,
  equip: 3,
  unequip: 6,
  tracker: 50,
  ccreport: 3,
};
// 150, not 200: some replies add cost that we do not see. Each `player`
// update that the server sends because of our event (resend, node/server.js:4550-4592)
// adds 1 or 2 to our cost.
export const LIMIT = 150;
export const WINDOW_MS = 4000; // the server counts the calls of the last 4 s

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export class Budget {
  readonly #sock: AlSocket;
  #calls: [time: number, cost: number][] = []; // the calls of the last WINDOW_MS, oldest first

  constructor(sock: AlSocket, world: World) {
    this.#sock = sock;
    // The server charges 8 for each map change (add_call_cost(player, 8,
    // "transport"), node/server.js:4726). We see the change as `new_map`.
    world.listen("new_map", () => this.#calls.push([Date.now(), 8]));
  }

  cost(event: string): number {
    return 1 + (EXTRA_COST[event] ?? 0);
  }

  /** The total cost of the last 4 s. */
  spent(): number {
    const now = Date.now();
    while (this.#calls.length > 0 && now - this.#calls[0][0] >= WINDOW_MS) this.#calls.shift();
    return this.#calls.reduce((sum, [, cost]) => sum + cost, 0);
  }

  /** Waits until the last 4 s have room for `event`, then sends it. */
  async emit(event: string, payload?: unknown): Promise<void> {
    const cost = this.cost(event);
    while (this.spent() + cost > LIMIT) {
      // Wait until the oldest call leaves the window (+10 ms, so that it is out).
      await sleep(this.#calls[0][0] + WINDOW_MS - Date.now() + 10);
    }
    // No `await` between the check and the push: no other emit can come between.
    this.#calls.push([Date.now(), cost]);
    this.#sock.emit(event, payload);
  }
}
// endregion budget
