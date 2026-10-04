// gear-up.ts: upgrades a coat to +3 and compounds rings in groups of three,
// with the stop rule of the game guide. It farms first until it has a chest
// (gold and rings). Node.js 22.18+, no packages.
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger node gear-up.ts
import { Bot } from "./albot/bot.ts";
import { Travel } from "./albot/travel.ts";
import { Farmer } from "./albot/farmer.ts";
import { Items, NPC_DIST } from "./albot/items.ts";
import type { MeWithGear, Npc } from "./albot/items.ts";
import type { ChestOpened } from "./albot/actions.ts";

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const TICK_MS = 100;

// region rules
// The stop rule (the game guide, "A progression plan"): take a piece to +3
// with no spare copy. Above +3 the chance falls (70 % for +4), so stop and
// use spares ("Step 2"). Also stop when the server's chance, with grace, is
// below 90 %: then a failure is too likely for an item that we wear.
const ITEM = "coat"; // 6,000 gold at Gabriel (`basics`)
const TARGET_LEVEL = 3;
const MIN_CHANCE = 0.9;
// Jewelry: compound groups of three while the chance is at least 90 %. For
// most jewelry that is +0 -> +1 only (99 %); +2 is 75 %.
// endregion rules

const bot = await Bot.connect();
const { world, act, cooldowns, budget, G } = bot;
const me = world.me as MeWithGear; // with the equipment fields
console.log(`in game as ${me.id} (${me.ctype}, level ${me.level}) on ${me.map} at ${Math.round(me.x)},${Math.round(me.y)}`);
const travel = new Travel(world, act);
const items = new Items(world, act, budget);
const farmer = new Farmer(world, act, cooldowns, travel);

// 1. Farm until one chest opened: the first chest brings gold and rings.
let chests = 0;
world.listen<ChestOpened>("chest_opened", (r) => {
  if (!r.gone) chests++;
});
while (chests === 0) {
  await sleep(TICK_MS);
  await farmer.tick();
}

// Walks to within `within` px of an NPC (or of a point). Says so only when it must walk.
async function goNear(npc: Npc | null, within = NPC_DIST): Promise<void> {
  if (!npc) throw new Error("no such NPC on this map");
  world.advance();
  if (Math.hypot(me.x - npc.x, me.y - npc.y) <= within) return;
  console.log(`walk to ${npc.id} at ${npc.x},${npc.y}`);
  if (!(await travel.walkTo(npc.x, npc.y))) throw new Error(`could not walk to ${npc.id}`);
}

// Buys one `name` and returns its slot number.
async function buyOne(name: string): Promise<number> {
  await goNear(items.npcSelling(name));
  const r = await items.buy(name, 1);
  if (!r || r.failed) throw new Error(`buy ${name}: ${r ? r.response : "no answer"}`);
  console.log(`buy ${name} x1: ${r.cost} gold`);
  return Number(r.num);
}

// 2. The item to upgrade.
let num = items.find(ITEM);
if (num < 0) num = await buyOne(ITEM);

// 3. Stand where both Lucas (scrolls) and Cue (upgrade, compound) are within
//    400 px: the middle of the two (about 140 px from each).
const lucas = items.npcSelling("scroll0");
const cue = items.npcWithRole("newupgrade");
if (!lucas || !cue) throw new Error("no scroll shop or upgrade NPC on this map");
const spot = { id: "scrolls and newupgrade", x: Math.round((lucas.x + cue.x) / 2), y: Math.round((lucas.y + cue.y) / 2) };
await goNear(spot, 20); // 20 px: near the middle, so that both stay within 400 px

// region upgrade-loop
while (num >= 0 && (me.items[num]?.level ?? 0) < TARGET_LEVEL) {
  const level = me.items[num]?.level ?? 0;
  let scroll = items.find("scroll0");
  if (scroll < 0) scroll = await buyOne("scroll0");
  // Ask first: the chance includes grace, which only the server knows.
  const calc = await items.upgrade(num, scroll, true);
  if (!calc || calc.failed || calc.response !== "upgrade_chance") {
    console.log(`upgrade ${ITEM}: ${calc ? calc.response : "no answer"}`);
    break;
  }
  const chance = Number(calc.chance);
  if (chance < MIN_CHANCE) {
    console.log(`stop: the chance for +${level + 1} is ${chance.toFixed(2)}`);
    break;
  }
  const r = await items.upgrade(num, scroll);
  const result = r?.response === "upgrade_success" ? "success" : r?.response === "upgrade_fail" ? "fail" : (r?.response ?? "no answer");
  console.log(`upgrade ${ITEM} +${level} -> +${level + 1}: ${result} (chance ${chance.toFixed(2)})`);
  if (result !== "success") break; // a fail destroys the item
  num = typeof r?.num === "number" ? r.num : num;
}
// endregion upgrade-loop

// region compound-loop
// Groups of three: same name, same level, an item that compounds (G `compound`).
function findGroup(): number[] | null {
  const groups = new Map<string, number[]>();
  me.items.forEach((it, n) => {
    if (!it || (it as { l?: string }).l || !G.items[it.name]?.compound) return;
    const key = `${it.name} ${it.level ?? 0}`;
    groups.set(key, [...(groups.get(key) ?? []), n]);
  });
  for (const nums of groups.values()) if (nums.length >= 3) return nums.slice(0, 3);
  return null;
}

for (let group = findGroup(); group; group = findGroup()) {
  const it = me.items[group[0]]!;
  const level = it.level ?? 0;
  let scroll = items.find("cscroll0");
  if (scroll < 0) scroll = await buyOne("cscroll0");
  const calc = await items.compound(group, scroll, true);
  const chance = Number(calc?.chance ?? 0);
  if (!calc || calc.failed || calc.response !== "compound_chance" || chance < MIN_CHANCE) {
    console.log(`stop: compound ${it.name} +${level}: ${calc?.response === "compound_chance" ? chance.toFixed(2) : (calc?.response ?? "no answer")}`);
    break;
  }
  const r = await items.compound(group, scroll);
  const result = r?.response === "compound_success" ? "success" : r?.response === "compound_fail" ? "fail" : (r?.response ?? "no answer");
  console.log(`compound ${it.name} +${level} x3 -> +${level + 1}: ${result} (chance ${chance.toFixed(2)})`);
  if (result !== "success" && result !== "fail") break;
}
// endregion compound-loop

// 4. Wear the results.
for (const line of await items.equipBetter()) console.log(`equip ${line}`);
const show = (s: string) => (me.slots[s] ? `${me.slots[s].name} +${me.slots[s].level ?? 0}` : "-");
console.log(`gear: chest ${show("chest")}, ring1 ${show("ring1")}, ring2 ${show("ring2")}, belt ${show("belt")}`);
bot.close();
console.log("OK");
