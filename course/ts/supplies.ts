// supplies.ts: a farming bot that looks after itself. After each chest it
// wears better gear; when potions or bag space run low, it walks to the town,
// sells the loot, buys potions and the basic armor, and goes back to farm.
// Node.js 22.18+, no packages.
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger node supplies.ts [trips]
//      trips: stop after this many town trips (the tests use 1). Without it: until Ctrl-C.
import { Bot } from "./albot/bot.ts";
import { Travel } from "./albot/travel.ts";
import { Farmer } from "./albot/farmer.ts";
import { Items, isLoot, NPC_DIST } from "./albot/items.ts";
import type { MeWithGear, Npc } from "./albot/items.ts";
import type { ChestOpened } from "./albot/actions.ts";

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const TICK_MS = 100;

// region rules
// The restock rule (the game guide, "Your first hour" and "Inventory"):
const MIN_POTIONS = 20; // go to town below 20 hpot0 or 20 mpot0 ...
const MIN_FREE = 5; // ... or below 5 free inventory slots
const POTIONS = 50; // buy up to 50 of each (20 gold each: 2,000 gold for both)
const KEEP_GOLD = 2000; // never spend the potion money on armor ("Your first day", step 1)
// The basic armor that a new character does not wear, from Gabriel (`basics`).
const ARMOR = ["gloves", "coat", "pants"];
// endregion rules

let stop = false;
process.on("SIGINT", () => (stop = true));

const trips = Number(process.argv[2] ?? 0);
const bot = await Bot.connect();
const { world, act, cooldowns, budget, G } = bot;
const me = world.me as MeWithGear; // with the equipment fields
console.log(`in game as ${me.id} (${me.ctype}, level ${me.level}) on ${me.map} at ${Math.round(me.x)},${Math.round(me.y)}`);
const travel = new Travel(world, act);
const items = new Items(world, act, budget);
const farmer = new Farmer(world, act, cooldowns, travel);

// region town
// Walks to within NPC_DIST of an NPC. Says so only when it must walk.
async function goNear(npc: Npc | null): Promise<boolean> {
  if (!npc) throw new Error("no such NPC on this map");
  world.advance();
  if (Math.hypot(me.x - npc.x, me.y - npc.y) <= NPC_DIST) return true;
  console.log(`walk to ${npc.id} at ${npc.x},${npc.y}`);
  return travel.walkTo(npc.x, npc.y);
}

// Buys `quantity` of `name` from the NPC that sells it.
async function shop(name: string, quantity: number): Promise<boolean> {
  if (!(await goNear(items.npcSelling(name)))) return false;
  const r = await items.buy(name, quantity);
  console.log(r && !r.failed ? `buy ${name} x${r.q}: ${r.cost} gold` : `buy ${name}: ${r ? r.response : "no answer"}`);
  return r !== null && !r.failed;
}

async function townTrip(): Promise<boolean> {
  // 1. Sell the loot to the potion shop (any shop buys any item).
  const shopNpc = items.npcSelling("hpot0");
  if (!(await goNear(shopNpc))) return false;
  for (let num = 0; num < me.items.length; num++) {
    const it = me.items[num];
    if (!isLoot(G, it)) continue;
    const r = await items.sell(num, it.q ?? 1);
    if (r && !r.failed) console.log(`sell ${it.name}: +${r.gold} gold`);
  }
  // 2. Potions, up to POTIONS of each.
  for (const name of ["hpot0", "mpot0"]) {
    const need = POTIONS - items.count(name);
    if (need > 0) await shop(name, need);
  }
  // 3. The basic armor that we do not wear, while the gold lasts.
  for (const name of ARMOR) {
    const slot = G.items[name].type; // "gloves", "chest", "pants": the slot has the type's name
    if (me.slots[slot] || me.gold - G.items[name].g < KEEP_GOLD) continue;
    await shop(name, 1);
  }
  for (const line of await items.equipBetter()) console.log(`equip ${line}`);
  console.log(`bag: ${items.count("hpot0")} hpot0, ${items.count("mpot0")} mpot0, ${items.freeSlots()} free slot(s), ${me.gold} gold`);
  return true;
}
// endregion town

// region loop
let chests = 0; // chests opened so far
let seen = 0; // chests that we checked after
world.listen<ChestOpened>("chest_opened", (r) => {
  if (!r.gone) chests++;
});
let done = 0;
while (!stop && (trips === 0 || done < trips)) {
  await sleep(TICK_MS);
  await farmer.tick();
  if (chests === seen) continue;
  // After each chest: wear what is better, then check the supplies.
  seen = chests;
  for (const line of await items.equipBetter()) console.log(`equip ${line}`);
  const hp = items.count("hpot0");
  const mp = items.count("mpot0");
  const free = items.freeSlots();
  if (hp >= MIN_POTIONS && mp >= MIN_POTIONS && free >= MIN_FREE) continue;
  console.log(`supplies low: ${hp} hpot0, ${mp} mpot0, ${free} free slot(s)`);
  if (await townTrip()) done++;
  farmer.target = null; // choose again: the old target is far away now
}
// endregion loop

bot.close();
console.log("OK");
process.exit(0);
