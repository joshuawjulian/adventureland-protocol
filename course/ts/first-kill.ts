// first-kill.ts: enter the game, kill the nearest goo, open its chest, leave.
// The checkpoint of Part 2: it uses every module of the library.
// Node.js 22.18+, no packages.
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=<name> node first-kill.ts
import { Bot } from "./albot/bot.ts";
import type { Monster } from "./albot/world.ts";

// HARD-CODED values of this program, with the reasons:
const TICK_MS = 100; // one loop each 100 ms: fast enough to follow a fight, a small call-cost
const HEAL_BELOW = 0.7; // drink at 70 % hp: a goo cannot take the other 70 % before the next potion
const GIVE_UP_MS = 90_000; // a level 1 warrior kills a goo in a few seconds; 90 s means a problem
const CHEST_WAIT_MS = 3000; // `drop` comes just before `death`; 3 s is a lot of room
const GAP_PX = 10; // stop 10 px inside our range, so that a small step of the goo keeps it in range

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const xy = (e: { x: number; y: number }) => `${Math.round(e.x)},${Math.round(e.y)}`;

const bot = await Bot.connect();
const { world, act, cooldowns } = bot;
const me = world.me; // the same object for the whole session: updates merge into it
console.log(`in game as ${me.id} (${me.ctype}, level ${me.level}) on ${me.map} at ${xy(me)}`);

// Dead (from an earlier session)? Respawn first.
async function revive(): Promise<void> {
  console.log(`died; respawn in ${Math.ceil(act.msUntilRespawn() / 1000)} s`);
  if (!(await act.respawn())) throw new Error("respawn failed");
  console.log(`respawned at ${xy(me)}`);
}
if (me.rip) await revive();

function pickGoo(): Monster | null {
  const goo = world.nearestMonster("goo");
  if (!goo) return null; // none in view now; a new one spawns soon
  console.log(`target: goo ${goo.id} at ${xy(goo)}`);
  return goo;
}
let target: Monster | null = null; // picked in the loop, after the first heal

// The goo is dead when its `death` comes, or a `hit` that killed it.
let killed = false;
world.listen<{ id: string }>("death", (d) => { if (d.id === target?.id) killed = true; });
world.listen<{ id: string; kill?: boolean }>("hit", (d) => { if (d.id === target?.id && d.kill) killed = true; });

const deadline = performance.now() + GIVE_UP_MS;
while (!killed) {
  if (performance.now() > deadline) throw new Error("no kill in 90 s");
  world.advance(); // positions are now, not the last update

  if (me.rip) {
    await revive();
    continue;
  }
  if (me.hp < HEAL_BELOW * me.max_hp && cooldowns.ready("potion")) {
    if (await act.heal("hp")) console.log(`heal hp: ${me.hp}/${me.max_hp}`);
  }

  // Pick the nearest goo once. Pick again only if it left our view.
  if (!target || !world.monsters.has(target.id)) target = pickGoo();
  if (!target) {
    await sleep(TICK_MS);
    continue;
  }
  const goo = world.monsters.get(target.id)!; // our copy, updated by `entities`

  if (world.distance(me, goo) > me.range) {
    // Walk to the point on the line goo -> us at (range - 10) px from the goo.
    // The box gap is smaller than the distance of the centers, so there we are in range.
    const dx = me.x - goo.x;
    const dy = me.y - goo.y;
    const d = Math.hypot(dx, dy) || 1; // || 1: no division by 0 if we stand on it
    const r = Math.max(me.range - GAP_PX, 0);
    await act.moveTo(goo.x + (dx / d) * r, goo.y + (dy / d) * r);
  } else if (cooldowns.ready("attack")) {
    await act.attack(goo.id); // the damage comes later as `hit`; the listener sees the kill
  }
  await sleep(TICK_MS);
}
console.log(`killed goo ${target?.id}`);

// The chest: wait for its `drop`, then open each chest that we know of.
const chestDeadline = performance.now() + CHEST_WAIT_MS;
while (world.chests.size === 0 && performance.now() < chestDeadline) await sleep(TICK_MS);
for (const id of [...world.chests.keys()]) {
  const r = await act.openChest(id);
  if (r && !r.gone) console.log(`chest ${id}: +${r.gold ?? 0} gold, ${r.items?.length ?? 0} item(s)`);
}

// The xp comes with the `player` update after the kill.
console.log(`xp: ${Math.floor(me.xp)}/${me.max_xp}, level ${me.level}`);
bot.close();
console.log("OK");
