// items.ts: the inventory and the NPC services: buy, sell, equip, give items
// and gold to another character, upgrade and compound. Node.js 22.18+.
//
// `me.items` is the inventory: an array of 42 slots (G: isize), each an item
// {name, q?, level?, ...} or null. `me.slots` is the equipment: slot name ->
// item. `me.esize` is the number of empty inventory slots. All three come in
// `start` and `player` (node/server.js:855-1001).
import { normalize } from "./actions.ts";
import type { Actions, GameResponse } from "./actions.ts";
import type { Budget } from "./budget.ts";
import type { GData } from "./gdata.ts";
import type { InventoryItem, Me, World } from "./world.ts";

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** An inventory item with the fields that this module reads. */
export interface Item extends InventoryItem {
  l?: string; // a lock: "l" locked, "s" sealed, "u" unsealing
}

/** `me` with the inventory fields that World.Me does not name. */
export interface Gear {
  slots: Record<string, Item | null | undefined>; // the equipment
  esize?: number; // empty inventory slots
  isize?: number; // inventory size (42)
}
export type MeWithGear = Me & Gear;

/** An NPC on our map. */
export interface Npc {
  id: string;
  x: number;
  y: number;
}

/** G.npcs[id]: the fields that this module reads. */
interface NpcDef {
  role?: string; // "merchant", "newupgrade", "transport", ...
  items?: (string | null)[]; // a shop: the items that it sells
}

// region rules
// An NPC sells, buys, upgrades and compounds within 400 px (B.sell_dist,
// node/server.js:220). Stand a little nearer: our position is an estimate.
export const NPC_DIST = 350;

// The equipment slots for each item type (G.items[name].type). Rings and
// earrings have two slots.
export const SLOTS_FOR_TYPE: Readonly<Record<string, string[]>> = {
  weapon: ["mainhand"], shield: ["offhand"], source: ["offhand"], quiver: ["offhand"],
  misc_offhand: ["offhand"], helmet: ["helmet"], chest: ["chest"], pants: ["pants"],
  shoes: ["shoes"], gloves: ["gloves"], belt: ["belt"], amulet: ["amulet"], orb: ["orb"],
  cape: ["cape"], ring: ["ring1", "ring2"], earring: ["earring1", "earring2"],
};

// The item types that a bot keeps and never sells (the loot rules of the
// game guide, "A merchant in practice"): potions, scrolls and offerings, and
// jewelry, which you compound in groups of three.
export const KEEP_TYPES: readonly string[] = ["pot", "uscroll", "cscroll", "pscroll", "offering", "ring", "earring", "amulet", "belt", "orb"];

// Is this inventory item loot to sell? Not a kept type, not locked (`l`), not
// an upgrade in progress ("placeholder").
export function isLoot(G: GData, item: Item | null | undefined): item is Item {
  if (!item || item.name === "placeholder" || item.l) return false;
  const def = G.items[item.name];
  return !!def && !KEEP_TYPES.includes(def.type);
}
// endregion rules

export class Items {
  readonly world: World;
  readonly act: Actions;
  readonly budget: Budget;
  readonly G: GData;
  #log: { seq: number; r: GameResponse }[] = []; // the last game_response events
  #seq = 0;

  constructor(world: World, act: Actions, budget: Budget) {
    this.world = world;
    this.act = act;
    this.budget = budget;
    this.G = world.G;
    // The results of upgrade and compound come later, as hitchhikers inside a
    // `player` update. world.listen gets them too (World.onPlayer dispatches
    // them), so keep the last 50 game_response events and search them.
    world.listen<unknown>("game_response", (d) => {
      this.#log.push({ seq: ++this.#seq, r: normalize(d) });
      if (this.#log.length > 50) this.#log.shift();
    });
  }

  /** `me`, with its equipment fields. */
  get me(): MeWithGear {
    return this.world.me as MeWithGear;
  }

  // region find
  // The slot number of the first item called `name` (and of `level`, if
  // given), or -1.
  find(name: string, level: number | null = null): number {
    const items: (Item | null)[] = this.me.items ?? [];
    return items.findIndex((it) => it !== null && it.name === name && (level === null || (it.level ?? 0) === level));
  }

  // How many of `name` we carry (stacks count their `q`).
  count(name: string): number {
    let n = 0;
    for (const it of this.me.items ?? []) if (it && it.name === name) n += it.q ?? 1;
    return n;
  }

  // The number of empty inventory slots.
  freeSlots(): number {
    const me = this.me;
    if (typeof me.esize === "number") return me.esize;
    return (me.isize ?? 42) - (me.items ?? []).filter(Boolean).length;
  }

  // The NPC on our map that sells `item`, or null. NPCs with an `items` list
  // are shops (G.npcs[id].items).
  npcSelling(item: string): Npc | null {
    return this.#npc((npc) => (npc.items ?? []).includes(item));
  }

  // The NPC on our map with this role, for example "newupgrade" (Cue: upgrade
  // and compound) or "merchant" (a shop: it buys any item).
  npcWithRole(role: string): Npc | null {
    return this.#npc((npc) => npc.role === role);
  }

  #npc(test: (npc: NpcDef) => boolean): Npc | null {
    const maps = this.G.maps as Record<string, { npcs?: { id: string; position?: number[]; positions?: number[][] }[] }>;
    const npcs = this.G.npcs as Record<string, NpcDef>;
    for (const n of maps[this.me.map]?.npcs ?? []) {
      const pos = n.position ?? n.positions?.[0];
      if (pos && npcs[n.id] && test(npcs[n.id])) return { id: n.id, x: pos[0], y: pos[1] };
    }
    return null;
  }
  // endregion find

  // region shop
  // Buys from an NPC within 400 px that sells the item. The answer:
  // `buy_success` {cost, num, name, q}, or a failure: "distance" (too far),
  // "buy_cost" (not enough gold), "buy_cant_space" (node/server.js:8409-8461).
  async buy(name: string, quantity: number): Promise<GameResponse | null> {
    return this.act.request("buy", { name, quantity });
  }

  // Sells to any shop NPC within 400 px for 60 % of G.items[name].g (1 gold for
  // a gift item). The answer: `gold_received` {gold} (node/server.js:8046-8096).
  async sell(num: number, quantity: number): Promise<GameResponse | null> {
    return this.act.request("sell", { num, quantity });
  }
  // endregion shop

  // region equip
  // Puts the item of slot `num` on. Without `slot`, the server chooses one
  // from the item type. The old item goes back to the inventory. The answer
  // is {response: "data", slot} on success (node/server.js:7643-7915).
  async equip(num: number, slot: string | null = null): Promise<GameResponse | null> {
    return this.act.request("equip", slot ? { num, slot } : { num });
  }

  async unequip(slot: string): Promise<GameResponse | null> {
    return this.act.request("unequip", { slot });
  }

  // Equips each inventory item that is better than what we wear: the slot is
  // empty, or it holds the same item at a lower level. A simple rule; the game
  // guide ("Gear is more important than level") compares stats. Returns
  // "<name>: <slot>" for each item that went on.
  async equipBetter(): Promise<string[]> {
    const done: string[] = [];
    const me = this.me;
    for (let num = 0; num < (me.items ?? []).length; num++) {
      const it = me.items[num];
      const def = it && this.G.items[it.name];
      const slots = def && SLOTS_FOR_TYPE[def.type];
      if (!it || !slots || it.name === "placeholder") continue;
      const worn = (s: string) => me.slots?.[s];
      const slot =
        slots.find((s) => !worn(s)) ??
        slots.find((s) => worn(s)!.name === it.name && (worn(s)!.level ?? 0) < (it.level ?? 0));
      if (!slot) continue;
      const r = await this.equip(num, slot);
      if (r && !r.failed) done.push(`${it.name}: ${slot}`); // "cant_equip": not for our class
    }
    return done;
  }
  // endregion equip

  // region send
  // Gives items to another character on our map within 400 px. The answer:
  // `item_sent`, or "distance", "send_no_space" (node/server.js:8463-8560).
  async sendItem(name: string, num: number, quantity: number): Promise<GameResponse | null> {
    return this.act.request("send", { name, num, q: quantity });
  }

  // Gives gold. Between characters of one account the receiver gets all of
  // it; to another account, 2.5 % less (node/server.js:8590-8600).
  async sendGold(name: string, gold: number): Promise<GameResponse | null> {
    return this.act.request("send", { name, gold });
  }
  // endregion send

  // region bank
  // Gold into and out of the bank. Only inside the bank (a map with `mount`,
  // which Travel.goToMap("bank") reaches); elsewhere: "bank_unavailable". The
  // first answer has place "bank" and the `gold` moved (node/server.js:9257-9282).
  async deposit(gold: number): Promise<GameResponse | null> {
    return this.act.request("bank", { operation: "deposit", amount: gold });
  }

  async withdraw(gold: number): Promise<GameResponse | null> {
    return this.act.request("bank", { operation: "withdraw", amount: gold });
  }
  // endregion bank

  // region upgrade
  // Upgrades the item in slot `itemNum` with the scroll in `scrollNum`, at
  // the upgrade NPC (within 400 px). `clevel` must be the item's level now,
  // or the server says "upgrade_mismatch" (node/server.js:7166-7168).
  //   calculate: true -> the answer is `upgrade_chance` {chance}; nothing is used.
  //   calculate: false -> the scroll is used, the slot holds a "placeholder",
  //     and the result comes later as a hitchhiker: `upgrade_success` or
  //     `upgrade_fail` {level, num} (node/server.js:14920-14945). On a fail the
  //     item is gone.
  // A failure before the roll is a bare string ("upgrade_no_scroll") or an
  // object with place "upgrade" ("distance"). null: no answer in time.
  async upgrade(itemNum: number, scrollNum: number, calculate = false): Promise<GameResponse | null> {
    const item = this.me.items[itemNum];
    const payload: Record<string, unknown> = { item_num: itemNum, scroll_num: scrollNum, clevel: item?.level ?? 0 };
    if (calculate) payload.calculate = true;
    // 30 s: the roll of +N takes 0.5 x N x sqrt(N) s, about 9 s at +7.
    return this.#roll("upgrade", payload, calculate ? 2000 : 30000);
  }

  // Combines three identical items (same name and level) with a compound
  // scroll. The same answers as upgrade, with "compound" in place of
  // "upgrade". The roll takes 10 s (node/server.js:7037). On a success the
  // item is in nums[0], one level higher; the other two slots are empty.
  async compound(nums: number[], scrollNum: number, calculate = false): Promise<GameResponse | null> {
    const item = this.me.items[nums[0]];
    const payload: Record<string, unknown> = { items: nums, scroll_num: scrollNum, clevel: item?.level ?? 0 };
    if (calculate) payload.calculate = true;
    return this.#roll("compound", payload, calculate ? 2000 : 30000);
  }

  // Sends the event, then waits for the first game_response about it: an
  // object with this `place`, or a response that starts with "<event>_"
  // (the bare-string failures and the late hitchhiker results).
  async #roll(event: string, payload: object, timeoutMs: number): Promise<GameResponse | null> {
    const since = this.#seq; // only answers that come after the emit
    await this.budget.emit(event, payload);
    for (const end = performance.now() + timeoutMs; performance.now() < end; await sleep(50)) {
      for (const { seq, r } of this.#log) {
        if (seq > since && (r.place === event || String(r.response).startsWith(event + "_"))) return r;
      }
    }
    return null;
  }
  // endregion upgrade
}
