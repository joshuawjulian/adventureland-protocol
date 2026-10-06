// first-kill.js: the checkpoint of Part 2. Connect, heal, walk to the nearest
// goo, kill it, open its chest, then close. Node.js 22.18+, no packages.
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyWarrior node first-kill.js
//      (goos live on "main", near the place where a new character starts)
import { Bot } from "./albot/bot.js";

const sleep = (/** @type {number} */ ms) => new Promise((resolve) => setTimeout(resolve, ms));
const TICK_MS = 100; // one decision every 100 ms: often enough, and cheap in call-cost
const LIMIT_MS = 90000; // give up after 90 s: a goo dies in much less time
const HEAL_BELOW = 0.7; // drink at 70 % hp: a goo cannot take the other 30 % in one potion cooldown

const bot = await Bot.connect();
const { world, act, cooldowns } = bot;
const me = world.me; // one object: each `player` update merges into it
console.log(`in game as ${me.id} (${me.ctype}, level ${me.level}) on ${me.map} at ${Math.round(me.x)},${Math.round(me.y)}`);

// The goo is dead when we get `death` with its id, or a `hit` with `kill`.
// It can arrive during any `await` below, so each step checks `killed` first.
/** @type {string | null} */
let targetId = null;
let killed = false;
world.listen("death", (d) => { if (d.id === targetId) killed = true; });
world.listen("hit", (d) => { if (d.id === targetId && d.kill) killed = true; });
// Print each chest as it opens (openChests() only counts them).
world.listen("chest_opened", (r) => {
  if (!r.gone) console.log(`chest ${r.id}: +${r.gold ?? 0} gold, ${r.items?.length ?? 0} item(s)`);
});

// Waits the 12 s, respawns, and says so.
async function respawn() {
  const left = act.msUntilRespawn(); // the rest of the 12 s (B.rip_time)
  console.log(`died; respawn in ${Math.ceil(left / 1000)} s`);
  if (!(await act.respawn())) throw new Error("respawn failed");
  console.log(`respawned at ${Math.round(me.x)},${Math.round(me.y)}`);
}

const deadline = performance.now() + LIMIT_MS;
while (!killed) {
  if (performance.now() > deadline) throw new Error("no kill in 90 s");
  await sleep(TICK_MS);
  world.advance(); // positions at this moment

  if (me.rip) {
    await respawn();
    continue;
  }

  // 1. Health first. heal() skips when the potion timer is not ready.
  if (me.hp < HEAL_BELOW * me.max_hp && cooldowns.ready("potion")) {
    if (await act.heal("hp")) console.log(`heal hp: ${me.hp}/${me.max_hp}`);
  }

  if (killed) break; // it died while we healed

  // 2. The target: the nearest goo. Choose again if it left our view.
  let goo = targetId === null ? null : world.monsters.get(targetId);
  if (!goo) {
    goo = world.nearestMonster("goo");
    if (!goo) continue; // none in view now; a new one spawns soon
    targetId = goo.id;
    console.log(`target: goo ${goo.id} at ${Math.round(goo.x)},${Math.round(goo.y)}`);
  }

  // 3. Out of range: walk to a point `range - 10` px from the goo, on the line
  //    from the goo to us. 10 px of margin: the goo moves while we walk.
  if (world.distance(me, goo) > me.range) {
    const dx = me.x - goo.x;
    const dy = me.y - goo.y;
    const d = Math.hypot(dx, dy) || 1;
    const stop = Math.max(0, me.range - 10);
    await act.moveTo(goo.x + (dx / d) * stop, goo.y + (dy / d) * stop);
    continue;
  }

  // 4. In range: attack when the attack cooldown is over.
  if (cooldowns.ready("attack")) await act.attack(goo.id);
}
console.log(`killed goo ${targetId}`);

// The chest (`drop`) comes with the kill. Wait up to 3 s for it, then open all chests.
for (let waited = 0; world.chests.size === 0 && waited < 3000; waited += TICK_MS) await sleep(TICK_MS);
await act.openChests();

console.log(`xp: ${me.xp}/${me.max_xp}, level ${me.level}`);
bot.close();
console.log("OK");
