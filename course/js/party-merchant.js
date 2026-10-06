// party-merchant.js: three fighters and one merchant in one program. The
// fighters farm in a party. The merchant walks to them, takes their loot and
// gold, sells the loot in the town and puts the gold in the bank.
// Node.js 22.18+, no packages.
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyWarrior node party-merchant.js [trips]
//      AL_CHARACTER is the leader. The program adds the next two fighters of
//      your character list, and your first merchant.
//      trips: stop after this many merchant trips (the tests use 1). Without it: until Ctrl-C.
// Make a merchant first, if you have none:
//      node party-merchant.js --create-merchant MyMerchant
import { login, serversAndCharacters, findServer, findCharacter } from "./albot/api.js";
import { loadG } from "./albot/gdata.js";
import { Travel } from "./albot/travel.js";
import { Farmer } from "./albot/farmer.js";
import { Items, isLoot, NPC_DIST } from "./albot/items.js";
import { Party, connectMember, createCharacter } from "./albot/party.js";

const sleep = (/** @type {number} */ ms) => new Promise((resolve) => setTimeout(resolve, ms));
const TICK_MS = 100;

// region rules
const FIGHTERS = 3; // the live limit: 3 characters that fight, plus merchants (game guide, "Many characters and bots")
const GIVE_DIST = 300; // `send` works within 400 px on the same map (node/server.js:8463-8560)
const FIGHTER_GOLD = 20000; // a fighter keeps this much gold for potions, and gives the rest
const MERCHANT_GOLD = 50000; // the merchant keeps this much, and banks the rest
// A fighter keeps only its potions. Everything else goes to the merchant:
// loot to sell, and jewelry that the merchant compounds later.
/** @param {Record<string, any>} G @param {any} it */
const give = (G, it) => !!it && it.name !== "placeholder" && !it.l && G.items[it.name]?.type !== "pot";
// endregion rules

let stop = false;
process.on("SIGINT", () => (stop = true));

// region choose
const auth = await login();
const { servers, characters } = await serversAndCharacters(auth);
if (process.argv[2] === "--create-merchant") {
  const name = process.argv[3] ?? "";
  await createCharacter(auth, name, "merchant");
  console.log(`created the merchant ${name}. Run the program again without --create-merchant.`);
  process.exit(0);
}
const trips = Number(process.argv[2] ?? 0);
const server = findServer(servers); // AL_SERVER
const leader = findCharacter(characters); // AL_CHARACTER
if (leader.type === "merchant") throw new Error("AL_CHARACTER must be a fighter: it leads the party");
const fighters = [leader, ...characters.filter((c) => c.type !== "merchant" && c.name !== leader.name)].slice(0, FIGHTERS);
const merchantCharacter = characters.find((c) => c.type === "merchant");
if (!merchantCharacter) throw new Error("no merchant on this account: run with --create-merchant <Name> first");
console.log(`team: ${fighters.map((c) => c.name).join(", ")}; merchant: ${merchantCharacter.name}`);
// endregion choose

// region connect
const G = await loadG(); // one G for all four
const crew = [];
for (const c of [...fighters, merchantCharacter]) {
  const fights = c.type !== "merchant";
  const m = await connectMember(auth, server, c, G);
  const me = m.world.me;
  console.log(`in game as ${me.id} (${me.ctype}, level ${me.level}) on ${me.map} at ${Math.round(me.x)},${Math.round(me.y)}`);
  const travel = new Travel(m.world, m.act);
  crew.push({
    m,
    travel,
    items: new Items(m.world, m.act, m.budget),
    party: new Party(m.world, m.act),
    // Only fighters farm. (A Farmer also prints each chest that opens for us.)
    farmer: fights ? new Farmer(m.world, m.act, m.cooldowns, travel, `${m.name}: `) : null,
  });
}
const [lead, ...others] = crew;
const merchant = crew[crew.length - 1];
// endregion connect

// region party
// The leader invites each one; each waits for its `invite`, then accepts.
for (const c of others) {
  await lead.party.invite(c.m.name);
  if (!(await c.party.waitInvite(lead.m.name))) throw new Error(`${c.m.name} got no invitation`);
  const r = await c.party.accept(lead.m.name);
  if (!r || r.failed) throw new Error(`${c.m.name} could not join: ${r ? r.response : "no answer"}`);
}
for (let waited = 0; lead.party.list.length < crew.length && waited < 5000; waited += 100) await sleep(100);
console.log(`party: ${lead.party.list.join(", ")}`);
// endregion party

// region fighter
// A fighter farms. When the merchant is near, it gives its loot and gold.
/** @param {typeof crew[number]} f */
async function fighterLoop(f) {
  const { world } = f.m;
  const me = world.me;
  while (!stop) {
    await sleep(TICK_MS);
    await f.farmer?.tick();
    world.advance();
    const near = world.players.get(merchant.m.name); // the merchant, if it is in our view
    if (!near || world.distance(me, near) > GIVE_DIST) continue;
    let n = 0;
    for (let num = 0; num < me.items.length; num++) {
      const it = me.items[num];
      if (!give(G, it)) continue;
      const r = await f.items.sendItem(merchant.m.name, num, it.q ?? 1);
      if (r && !r.failed) n++;
    }
    // Gold only above twice the reserve: not a `send` for each small chest.
    const gold = me.gold > 2 * FIGHTER_GOLD ? me.gold - FIGHTER_GOLD : 0;
    if (gold > 0) await f.items.sendGold(merchant.m.name, gold);
    if (n || gold) console.log(`${f.m.name}: gave ${n} item(s) and ${gold} gold to ${merchant.m.name}`);
  }
}
// endregion fighter

// region merchant
// The merchant: wait for loot, collect it, sell it, bank the gold.
/** @param {typeof crew[number]} f */
const hasLoot = (f) => f.m.world.me.items.some((/** @type {any} */ it) => give(G, it));

async function merchantTrip() {
  const { world } = merchant.m;
  const me = world.me;
  // 1. Wait until a fighter has something to give, or until the merchant holds loot.
  // The merchant holds loot when a walk of the last trip failed after it collected: then go
  // on and sell it. Without this, the wait never ends: the fighters gave all already.
  const holdsLoot = () => me.items.some((/** @type {any} */ it) => isLoot(G, it));
  while (!stop && !holdsLoot() && !crew.slice(0, -1).some(hasLoot)) await sleep(500);
  // 2. Go to each fighter with loot, and wait (10 s at most) until it gave all.
  for (const f of crew.slice(0, -1)) {
    if (stop || !hasLoot(f)) continue;
    const fm = f.m.world.me;
    console.log(`${merchant.m.name}: walk to ${f.m.name} at ${Math.round(fm.x)},${Math.round(fm.y)}`);
    await merchant.travel.walkTo(fm.x, fm.y);
    for (let waited = 0; hasLoot(f) && waited < 10000; waited += 200) await sleep(200);
  }
  // Stop between the steps when we must stop (Ctrl-C, or a fighter failed).
  if (stop) return false;
  // 3. Sell the loot in the town. Keep the jewelry: three of a kind compound.
  const shop = merchant.items.npcSelling("hpot0");
  if (!shop) throw new Error("no shop on this map");
  console.log(`${merchant.m.name}: walk to ${shop.id} at ${shop.x},${shop.y}`);
  if (!(await merchant.travel.walkTo(shop.x, shop.y))) return false;
  let sold = 0;
  let gold = 0;
  for (let num = 0; num < me.items.length; num++) {
    const it = me.items[num];
    if (!isLoot(G, it)) continue;
    const r = await merchant.items.sell(num, it.q ?? 1);
    if (r && !r.failed) (sold++, (gold += r.gold));
  }
  console.log(`${merchant.m.name}: sold ${sold} item(s): +${gold} gold`);
  if (stop) return false;
  // 4. The bank: the door is north of the town. Deposit, then go back out.
  if (!(await merchant.travel.goToMap("bank"))) return false;
  const amount = Math.max(0, me.gold - MERCHANT_GOLD);
  const r = await merchant.items.deposit(amount);
  console.log(`${merchant.m.name}: in the bank: deposited ${r && !r.failed ? r.gold : 0} gold`);
  if (!(await merchant.travel.goToMap("main"))) return false;
  console.log(`${merchant.m.name}: back on main at ${Math.round(me.x)},${Math.round(me.y)}`);
  return true;
}
// endregion merchant

// region run
// The fighters run at the same time as the merchant. Each fighter gets its
// catch NOW, not at the end: a promise that rejects with no handler stops
// Node.js at once (since Node.js 15). When one fighter fails (for example its
// socket closed), say so at once and stop the others: each loop checks `stop`.
/** @type {unknown} */
let failure = null; // the first error of a fighter (null: none)
const fighting = crew.slice(0, -1).map((f) =>
  fighterLoop(f).catch((err) => {
    console.log(`${f.m.name}: stopped: ${/** @type {Error} */ (err).message}`);
    failure ??= err;
    stop = true;
  }),
);
let done = 0;
try {
  while (!stop && (trips === 0 || done < trips)) {
    if (await merchantTrip()) done++;
  }
} finally {
  // Also when the merchant failed: end the fighters' loops, wait for them
  // (this never rejects: each one has its catch), and close every socket.
  stop = true;
  await Promise.all(fighting);
  for (const c of crew) c.m.close();
}
if (failure) {
  // The fighter printed its error above. Exit code 1: the run did not end well.
  console.log("stopped: a fighter failed");
  process.exit(1);
}
console.log("OK");
process.exit(0);
// endregion run
