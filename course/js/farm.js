// farm.js: a farming bot. It kills monsters of the Mainland ladder, loots,
// heals, respawns, leaves jail, and reconnects with the course's reconnect
// rule. Node.js 22.18+, no packages.
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger node farm.js [seconds]
//      seconds: stop after this time (the tests use 25). Without it: until Ctrl-C.
import { Bot, reconnectDelayMs } from "./albot/bot.js";
import { Travel } from "./albot/travel.js";
import { Farmer } from "./albot/farmer.js";

const sleep = (/** @type {number} */ ms) => new Promise((resolve) => setTimeout(resolve, ms));
const TICK_MS = 100; // one decision every 100 ms: fast enough, and cheap in call-cost
const STABLE_MS = 5 * 60000; // after a session of 5 min, the reconnect wait starts again at the first value

// region stop
// Ctrl-C (SIGINT) or `docker stop` (SIGTERM): finish this tick, close the
// socket, print the summary. A second Ctrl-C stops at once.
let stop = false;
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => {
    if (stop) process.exit(1);
    stop = true;
    console.log("stopping (press Ctrl-C again to stop at once)");
  });
}
// A sleep that ends early when we stop.
/** @param {number} ms */
async function wait(ms) {
  for (const end = Date.now() + ms; !stop && Date.now() < end; ) await sleep(Math.min(200, end - Date.now()));
}
// endregion stop

const seconds = Number(process.argv[2] ?? 0);
const started = Date.now();
const endAt = seconds > 0 ? started + seconds * 1000 : Infinity;
let kills = 0;
let attempt = 0; // failed tries in a row, for reconnectDelayMs
/** @type {Record<string, any>} */
let last = {}; // our character in the last session

// region session
while (!stop && Date.now() < endAt) {
  // 1. Connect. A failure (the server is full, the save of the last session
  //    still runs, ...) waits as the reconnect rule says, then tries again.
  /** @type {Bot} */
  let bot;
  try {
    bot = await Bot.connect();
  } catch (err) {
    const ms = reconnectDelayMs(attempt++);
    console.log(`connect failed: ${/** @type {Error} */ (err).message}; try again in ${ms / 1000} s`);
    await wait(ms);
    continue;
  }
  const session = Date.now();
  const me = bot.world.me;
  last = me;
  console.log(`in game as ${me.id} (${me.ctype}, level ${me.level}) on ${me.map} at ${Math.round(me.x)},${Math.round(me.y)}`);

  // 2. Play until we stop, the time is over, or the socket closes. AlSocket's
  //    local `disconnect` event has the reason; a send on a closed socket
  //    throws, so the catch below is the same case.
  /** @type {string | null} */
  let lost = null;
  bot.world.listen("disconnect", (reason) => (lost = String(reason)));
  bot.world.listen("disconnect_reason", (reason) => console.log(`the server says: ${reason}`)); // "limitdc", "limits", ...
  const farmer = new Farmer(bot.world, bot.act, bot.cooldowns, new Travel(bot.world, bot.act));
  try {
    while (!stop && lost === null && Date.now() < endAt) {
      await sleep(TICK_MS);
      await farmer.tick();
      farmer.nextType(); // a stronger monster when this one is too easy
    }
  } catch (err) {
    lost ??= /** @type {Error} */ (err).message;
  }
  kills += farmer.kills;
  const reason = lost; // read it first: close() fires our own `disconnect` event too
  bot.close();
  if (reason === null) break; // we stopped, or the time is over

  // 3. The reconnect rule: wait, then make a new socket and a full handshake.
  if (Date.now() - session >= STABLE_MS) attempt = 0;
  const ms = reconnectDelayMs(attempt++);
  console.log(`disconnected: ${reason}; reconnect in ${ms / 1000} s`);
  await wait(ms);
}
// endregion session

const secs = Math.round((Date.now() - started) / 1000);
console.log(`farmed ${secs} s: ${kills} kill(s), level ${last.level}, ${last.gold} gold`);
console.log("OK");
process.exit(0); // the SIGINT handlers keep Node alive otherwise
