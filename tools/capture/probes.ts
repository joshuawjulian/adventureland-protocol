// probes.ts: the probe plan, as stages that run.ts runs one at a time.
//
//   python3 tools/capture/run.py <stage>
//
// Each stage connects the characters it needs (the four authorized characters on US V; see
// session.ts), sends its probes with probe() (which writes a `probe` record naming the shape
// ids it means to hit), and leaves the characters in a sane place. PROBES.md is the same plan
// as a table: which request exercises which documented response or failure row, the setup it
// needs, what it costs, and the events that are not live-testable.
//
// "Least detrimental" (the owner's rule): every costly path uses the cheapest thing that works:
//   - upgrade: a +0 `helmet` (3,200 gold) with a `scroll0` the merchant already has;
//   - compound: three `test_orb` (1 gold each, standmerchant) with one `cscroll0` (6,400 gold);
//   - destroy / send / trade / giveaway: a `test_orb` (1 gold) or one potion;
//   - donate: 1 gold; sell: one potion; gold moves between our own characters (no tax);
//   - exchange: one `anniversarygift` that the merchant had;
//   - shells (bless_server, buy_with_cash): the account has 600 shells, so each paid request
//     is sent with a price above that (1,200 and `cosmo5` at 1,299): the server starts the
//     payment and it fails later, which exercises both replies and spends nothing;
//   - harakiri: once, on the level-7 merchant (the cheapest death), then respawn;
//   - duel: between our own warrior and mage; the mage walks out at once (a duel restores the
//     state it saved, node/server.js:1108-1136);
//   - jail: one deliberate move into a wall by the warrior, then `leave` (no cost).
// Things that cost more than the account can pay (mail: 48,000 gold; a wheel spin: 10,000;
// slots: 1,000,000; lock/seal: 250,000) are probed only on their failure paths.
import { AlSocket } from "../../course/ts/albot/alsocket.ts";
import { socketUrl } from "../../course/ts/albot/api.ts";
import { EXTRA_COST } from "../../course/ts/albot/budget.ts";
import { Grid } from "../../course/ts/albot/pathfind.ts";
import { setLabel } from "./record.ts";
import type { Frame } from "./record.ts";
import { codeOf, first, got, probe, responsesIn } from "./probe.ts";
import type { ProbeOptions, ProbeResult } from "./probe.ts";
import type { Char, Session } from "./session.ts";
import { sleep } from "./session.ts";

export interface Stage {
  what: string;
  chars?: string[]; // default: all four
  connect?: boolean; // false: HTTP only (or the stage connects by itself)
  run: (s: Session) => Promise<void>;
}

const W = "SETYWarrior";
const P = "SETYPriest";
const M = "SETYMage";
const MER = "SETYMerchant";

// ---- Shape refs ----------------------------------------------------------------------------
// A short way to name shape ids in the probes: "F5" -> send/<ev>/failure/5, "R:Success" ->
// send/<ev>/response/Success, "A2" -> send/<ev>/also/2, "req" -> send/<ev>/request, and the same
// under a variant with "v:<variant id>:" in front ("v:withdraw:R:Withdraw").
export function sid(ev: string, ref: string): string {
  let base = `send/${ev}`;
  let r = ref;
  const m = /^v:([^:]+):(.*)$/.exec(ref);
  if (m) {
    base += `/variant/${m[1]}`;
    r = m[2];
  }
  if (r === "req") return `${base}/request`;
  if (r.startsWith("R:")) return `${base}/response/${r.slice(2)}`;
  if (/^F\d+$/.test(r)) return `${base}/failure/${r.slice(1)}`;
  if (/^A\d+$/.test(r)) return `${base}/also/${r.slice(1)}`;
  throw new Error(`bad shape ref ${ref}`);
}

// Stop waiting at the first frame of one of these events.
const on = (...events: string[]) => (f: Frame) => events.includes(f.event);
// No reply expected: wait a short fixed time.
const NONE: ProbeOptions = { until: () => false, timeoutMs: 900, tailMs: 100 };

/** One probe: `refs` are the shapes it means to exercise (see sid). */
function pr(s: Session, c: Char, ev: string, payload: unknown, refs: string[] = [], opts: ProbeOptions = {}): Promise<ProbeResult> {
  return probe(s, c, `${ev}${refs.length ? ":" + refs.join(",") : ""}`, ev, payload, {
    ...opts,
    expect: [...(opts.expect ?? []), ...refs.map((r) => sid(ev, r))],
  });
}

// ---- Helpers -----------------------------------------------------------------------------------

function ch(s: Session, name: string): Char {
  const c = s.chars.get(name);
  if (!c) throw new Error(`${name} is not connected in this stage`);
  return c;
}

/** The first inventory slot with this item (and level), or -1. */
function slot(c: Char, name: string, level: number | null = null): number {
  return c.items.find(name, level);
}

/** The first empty inventory slot, or -1. */
function empty(c: Char): number {
  const items = c.me.items ?? [];
  const i = items.findIndex((x) => !x);
  if (i >= 0) return i;
  return items.length < 42 ? items.length : -1;
}

/** Walks to (x, y) on this map; true when we got within `near` px. Tries again once. */
async function walk(s: Session, c: Char, x: number, y: number, near = 60): Promise<boolean> {
  for (let i = 0; i < 3; i++) {
    s.check();
    await c.travel.walkTo(x, y);
    c.m.world.advance();
    if (Math.hypot(c.me.x - x, c.me.y - y) <= near) return true;
  }
  console.log(`  ${c.name}: could not walk to ${x},${y} (at ${Math.round(c.me.x)},${Math.round(c.me.y)})`);
  return false;
}

async function goMap(s: Session, c: Char, map: string): Promise<boolean> {
  for (let i = 0; i < 3 && c.me.map !== map; i++) {
    s.check();
    await c.travel.goToMap(map);
  }
  if (c.me.map !== map) console.log(`  ${c.name}: could not reach ${map} (on ${c.me.map})`);
  return c.me.map === map;
}

/** The position of an NPC on a map from G (the first position). */
function npcAt(s: Session, map: string, id: string): [number, number] {
  const maps = s.G.maps as Record<string, { npcs?: { id: string; position?: number[]; positions?: number[][] }[] }>;
  const n = maps[map]?.npcs?.find((x) => x.id === id);
  const p = n?.position ?? n?.positions?.[0];
  if (!p) throw new Error(`no NPC ${id} on ${map}`);
  return [p[0], p[1]];
}

/** Walks to a point next to an NPC (the NPC's own cell is not walkable). */
async function toNpc(s: Session, c: Char, map: string, id: string, dy = 40): Promise<boolean> {
  const [x, y] = npcAt(s, map, id);
  return walk(s, c, x, y + dy, 120);
}

async function until(test: () => boolean, ms: number): Promise<boolean> {
  for (const end = Date.now() + ms; Date.now() < end; await sleep(100)) if (test()) return true;
  return test();
}

/** Keeps hp/mp up with the free regeneration or a potion (the course's heal). */
async function topUp(c: Char): Promise<void> {
  const me = c.me;
  if (me.rip) return;
  if (me.hp < me.max_hp * 0.6) await c.m.act.heal("hp");
  else if (me.mp < me.max_mp * 0.5) await c.m.act.heal("mp");
}

function gold(c: Char): number {
  return Number(c.me.gold ?? 0);
}

function report(s: Session): void {
  for (const c of s.chars.values()) {
    const me = c.me;
    console.log(`  ${c.name}: ${me.map} ${Math.round(me.x)},${Math.round(me.y)} hp ${me.hp}/${me.max_hp} mp ${me.mp}/${me.max_mp} gold ${me.gold}${me.rip ? " DEAD" : ""}`);
  }
}

// ---- The bare observer socket ----------------------------------------------------------------
// A socket that sent `loaded` but no `auth`: an observer without a character. It exercises the
// "No character" rows of every handler that answers them, and the observer events.
async function observer(s: Session): Promise<Char> {
  setLabel("observer");
  const sock = await AlSocket.connect(socketUrl(s.server));
  await sock.waitFor("welcome", () => true, 10_000);
  // Before `auth` the server allows only 50 call-cost per 4 s (node/server.js:4891, `climit`),
  // and some events cost a lot (`tracker` 51, `players` 13: course/ts/albot/budget.ts). So the
  // observer has its own small budget: 40 per 4 s, with the same extra costs as the course.
  const calls: [number, number][] = [];
  const emit = async (e: string, p: unknown) => {
    const cost = 1 + (EXTRA_COST[e] ?? 0);
    for (;;) {
      while (calls.length && Date.now() - calls[0][0] >= 4000) calls.shift();
      if (calls.reduce((a, [, c]) => a + c, 0) + cost <= 40) break;
      await sleep(calls[0][0] + 4010 - Date.now());
    }
    calls.push([Date.now(), cost]);
    sock.emit(e, p);
  };
  const pseudo = {
    name: "observer",
    closedReason: null as string | null,
    m: { sock, budget: { emit } },
  };
  sock.on<string>("disconnect", (r) => (pseudo.closedReason = String(r)));
  const c = pseudo as unknown as Char;
  await probe(s, c, "loaded", "loaded", { success: 1, width: 1920, height: 1080, scale: 2 }, {
    until: on("entities"), expect: [sid("loaded", "R:Snapshot")],
  });
  return c;
}

// ---- Stages ----------------------------------------------------------------------------------

export const STAGES: Record<string, Stage> = {
  status: {
    what: "HTTP only: list the four characters (online? where?).",
    connect: false,
    run: async (s) => {
      for (const c of s.characters) {
        console.log(`${c.name.padEnd(13)} ${c.type.padEnd(9)} lvl ${c.level} ${c.server ? "ONLINE " + c.server : "offline"} ${c.map} ${Math.round(c.x)},${Math.round(c.y)}${c.rip ? " DEAD" : ""}`);
      }
      console.log(`server ${s.server.region}${s.server.name}: ${s.server.players} players`);
    },
  },

  look: {
    what: "Connect, print each character's state, idle 10 s.",
    run: async (s) => {
      for (const c of s.chars.values()) {
        const me = c.me as unknown as Record<string, unknown>;
        const items = (c.me.items ?? []).map((it, i) => (it ? `${i}:${it.name}${it.level ? "+" + it.level : ""}${it.q ? "x" + it.q : ""}` : null)).filter(Boolean);
        console.log(`${c.name}: ${me.ctype} lvl ${me.level} hp ${me.hp}/${me.max_hp} mp ${me.mp}/${me.max_mp} gold ${me.gold} map ${me.map} ${Math.round(c.me.x)},${Math.round(c.me.y)} esize ${me.esize}`);
        console.log(`  items: ${items.join(" ")}`);
        console.log(`  slots: ${Object.entries((me.slots ?? {}) as Record<string, { name: string; level?: number } | null>).filter(([, v]) => v).map(([k, v]) => `${k}=${v!.name}+${v!.level ?? 0}`).join(" ")}`);
        console.log(`  monsters near: ${[...c.m.world.monsters.values()].slice(0, 8).map((m) => `${m.type}@${Math.round(c.m.world.distance(c.me, m))}`).join(" ")}`);
      }
      await sleep(10_000);
    },
  },

  // 1. A socket with no character. Costs nothing.
  observer: {
    what: "A bare observer socket (loaded, no auth): the observer events and the 'No character' rows.",
    connect: false,
    run: async (s) => {
      const o = await observer(s);
      const q = (ev: string, payload: unknown, refs: string[] = [], opts: ProbeOptions = {}) => pr(s, o, ev, payload, refs, opts);
      // Events that answer without a character.
      await q("ping_trig", { id: 7 }, ["R:Echo"], { until: on("ping_ack") });
      await q("ccreport", undefined, ["R:Report"], { until: on("ccreport") });
      await q("random_look", undefined, ["R:Hint"], { until: on("game_log") });
      await q("buy_shells", undefined, ["R:Refusal"], { until: on("game_log") });
      await q("click", undefined, ["R:Deprecated"], { until: on("game_log") });
      await q("blocker", { type: "pvp" }, ["R:State"], { until: on("blocker", "game_error") });
      await q("blocker", { type: "nope" }, ["F1"], NONE);
      await q("list_pvp", {}, ["R:Success"], { until: on("pvp_list") });
      await q("test", { test: "hello" }, ["R:Time"], { until: on("test") });
      await q("o:home", undefined, ["F2"], NONE);
      await q("o:command", { command: "1+1" }, ["F2"], NONE);
      // "No character" rows that send a reply.
      await q("compound", { items: [0, 1, 2], scroll_num: 3, clevel: 0 }, ["F3"]);
      await q("upgrade", { item_num: 0, scroll_num: 1, clevel: 0 }, ["F1"]);
      await q("buy", { name: "hpot0", quantity: 1 }, ["F1"]);
      await q("buy_with_cash", { name: "cosmo5", quantity: 1 }, ["F1"]);
      await q("bless_server", {}, ["F1"]);
      await q("craft", { items: [[0, 0]] }, ["F1"]);
      await q("destat", { num: 0 }, ["F1"]);
      await q("dismantle", { num: 0 }, ["F1"]);
      await q("donate", { gold: 1 }, ["F1"]);
      await q("exchange", { item_num: 0 }, ["F1"]);
      await q("eval", { command: "hello" }, ["F1"]);
      await q("join_giveaway", { id: MER, slot: "trade1", rid: "abcd" }, ["F1"]);
      await q("sbuy", { rid: "abcd" }, ["F1"]);
      await q("secondhands", {}, ["F1"]);
      await q("send", { name: MER, num: 0 }, ["F1"]);
      await q("trade_buy", { id: MER, slot: "trade1", rid: "abcd", q: 1 }, ["F1"]);
      await q("trade_sell", { id: MER, slot: "trade1", rid: "abcd", q: 1 }, ["F1"]);
      await q("trade_swap", { id: MER, slot: "trade1", rid: "abcd", num: 0, item: { name: "hpot0" } }, ["F1"]);
      await q("unequip", { slot: "mainhand" }, ["F1"]);
      await q("lostandfound", { request_id: "lf0" }, ["F1"]);
      await q("respawn", {}, ["F1"]);
      await q("interaction", { type: "merrit_info" }, ["F1"]);
      // "No character": the handler throws (game_error) or sends nothing.
      await q("destroy", { num: 0, q: 1 }, ["F1"], { until: on("game_error") });
      await q("split", { num: 0, quantity: 1 }, ["F1"], { until: on("game_error") });
      await q("sell", { num: 0, quantity: 1 }, ["F1"], { until: on("game_error") });
      await q("locksmith", { num: 0, operation: "lock" }, ["F1"], { until: on("game_error") });
      await q("exchange_buy", { num: 0, name: "x", q: 1 }, ["F1"], { until: on("game_error") });
      await q("convert", { num: 0 }, ["F1"], { until: on("game_error") });
      await q("skin", { name: "goo" }, ["F1"], { until: on("game_error") });
      await q("whistle", undefined, ["F1"], { until: on("game_error") });
      await q("creward", { name: "x" }, ["F1"], NONE);
      await q("cm", { to: [MER] }, ["F1"], { until: on("game_error") });
      await q("attack", { id: "1" }, ["F1"], NONE);
      await q("players", undefined, ["F1"], NONE);
      await q("pets", undefined, ["F1"], NONE);
      await q("trade_history", undefined, ["F1"], NONE);
      await q("set_home", undefined, ["F1"], NONE);
      await q("signup", undefined, ["F1"], NONE);
      await q("monsterhunt", undefined, ["F1"], NONE);
      await q("harakiri", undefined, ["F1"], NONE);
      await q("legacify", undefined, ["F1"], NONE);
      await q("tarot", undefined, ["F1"], NONE);
      await q("town", undefined, ["F1"], NONE);
      await q("code", { run: true }, ["F1"], NONE);
      await q("use", { item: "hp" }, ["F1"], NONE);
      await q("stop", { action: "town" }, ["F1"], NONE);
      await q("target", { id: null }, ["F1"], NONE);
      await q("say", { message: "x" }, ["F1"]);
      await q("tavern", { event: "info", game: "dice" }, [], { timeoutMs: 1500 });
      await q("poker", { event: "info", request_id: "p0" }, [], { timeoutMs: 1500 });
      await q("mreport", { x: 0, y: 0 }, ["F1"], NONE);
      await q("cruise", 50, ["F1"], NONE);
      await q("party", { event: "leave" }, ["F1"], NONE);
      // The login refusals that cost nothing: a payload that is not an object, and a
      // character id that is not on the account (`no_character`).
      await q("auth", "nope", ["F1"], NONE);
      await q("auth", { user: s.auth.user, auth: s.auth.auth, character: "CH_doesnotexist0000000000", no_html: "1", passphrase: "" }, ["F7"], { until: on("game_error"), timeoutMs: 6000 });
      // `loaded` again on an observer: nothing.
      await q("loaded", { success: 1, width: 1920, height: 1080, scale: 2 }, ["F1"], NONE);
      // Dead handlers: nothing comes back.
      for (const ev of ["requested_ack", "play", "blend", "deepsea", "unlock"]) await q(ev, {}, ["R:Nothing"], NONE);
      await sleep(1000);
      o.m.sock.close();
    },
  },

  // 2. The passive and safe run: the four characters where they stand (the fighters among the
  //    gscorpions of desertland), idle, small requests, a short fight, chests, potions, a party.
  safe: {
    what: "Passive + safe: idle, ping, players, send_updates, property, fight weak monsters, potions, chests, party.",
    run: async (s) => {
      const [w, p, m, mer] = [ch(s, W), ch(s, P), ch(s, M), ch(s, MER)];
      const all = [w, p, m, mer];
      report(s);
      await sleep(5000); // idle: entities, server_info, player
      for (const c of all) {
        await pr(s, c, "ping_trig", { id: 1 }, ["R:Echo"], { until: on("ping_ack") });
        await pr(s, c, "property", { typing: true }, ["v:true:R:Typing"], { until: on("player"), timeoutMs: 1200 });
      }
      await pr(s, mer, "players", undefined, ["R:Success"], { until: on("players") });
      await pr(s, mer, "pets", undefined, ["R:Success"], { until: on("players") });
      await pr(s, mer, "send_updates", undefined, ["R:Gone", "R:Snapshot"], { until: on("entities") });
      await pr(s, mer, "trade_history", undefined, ["R:History"], { until: on("trade_history") });
      await pr(s, mer, "tracker", undefined, ["F2"], NONE);
      await pr(s, mer, "code", { run: true }, ["R:Update"], { until: on("player"), timeoutMs: 1200 });
      await pr(s, mer, "legacify", undefined, ["R:Success"], { until: on("player"), timeoutMs: 1200 });
      await pr(s, mer, "mreport", { x: 0, y: 0 }, ["R:Distance"], { until: on("game_log") });
      await pr(s, mer, "ccreport", undefined, ["R:Report"], { until: on("ccreport") });
      await pr(s, mer, "stop", { action: "town" }, ["R:Success"]);
      await pr(s, mer, "cruise", 50, ["R:Update", "R:Success"]);
      await pr(s, mer, "cruise", 0, ["R:Update", "R:Success"]); // 0 = no cap again (node/server.js:1761)
      await pr(s, mer, "use", { item: "nothing" }, ["v:Other:req", "R:Success"]);
      await pr(s, mer, "respawn", {}, ["F1"]); // alive: `invalid`
      await pr(s, mer, "open_chest", { id: "nosuchchest000" }, ["F9"], { until: on("chest_opened", "game_response") });
      await pr(s, mer, "target", { id: w.name }, ["R:Update", "R:Success"]);
      await pr(s, mer, "target", { id: null }, ["R:Update", "R:Success"]);
      await pr(s, mer, "property", { typing: false, afk: true }, ["v:AFK:R:AFK change"], { until: on("player"), timeoutMs: 1200 });
      await pr(s, mer, "property", { typing: false, afk: true }, ["v:AFK:F2"], NONE);
      await pr(s, mer, "property", { typing: false, afk: false }, ["v:AFK:R:AFK change"], { until: on("player"), timeoutMs: 1200 });
      await pr(s, mer, "o:home", undefined, ["F1"], NONE); // a character socket is no observer
      await pr(s, mer, "loaded", { success: 1, width: 1920, height: 1080, scale: 2 }, ["F1"], NONE);

      // Party: the warrior invites the other three; accept; the failures that cost nothing.
      await pr(s, w, "party", { event: "invite", name: "NoSuchCharacter9" }, ["v:invite:F2"]);
      await pr(s, w, "party", { event: "invite", name: w.name }, ["v:invite:F2"]);
      await pr(s, p, "party", { event: "accept", name: w.name }, ["v:accept:F3"]); // no invite yet
      await pr(s, p, "party", { event: "accept", name: "NoSuchCharacter9" }, ["v:accept:F1"]);
      for (const c of [p, m, mer]) {
        await pr(s, w, "party", { event: "invite", name: c.name }, ["R:Success", "v:invite:A1", "v:invite:A2"], { until: on("game_response") });
        await c.party.waitInvite(w.name, 3000);
        await pr(s, c, "party", { event: "accept", name: w.name }, ["R:Success", "v:accept:A3", "v:accept:A4"]);
      }
      await pr(s, w, "party", { event: "invite", name: p.name }, ["v:invite:F3", "R:Already in party"]);
      await pr(s, p, "party", { event: "accept", name: w.name }, ["v:accept:F4", "R:Already in party"]);
      // request / raccept: the mage leaves, asks to join, the warrior accepts.
      await pr(s, m, "party", { event: "leave" }, ["R:Success", "v:leave:A1", "v:leave:A2", "v:leave:A3"]);
      await pr(s, m, "party", { event: "request", name: "NoSuchCharacter9" }, ["v:request:F1"]);
      await pr(s, m, "party", { event: "request", name: w.name }, ["R:Success", "v:request:A1", "v:request:A2"]);
      await pr(s, w, "party", { event: "raccept", name: m.name }, ["R:Success", "v:raccept:A3", "v:raccept:A4"]);
      await pr(s, w, "party", { event: "raccept", name: m.name }, ["v:raccept:F4", "R:Already in party"]);
      await pr(s, w, "party", { event: "raccept", name: p.name }, ["v:raccept:F4", "R:Already in party"]);
      await pr(s, w, "party", { event: "raccept", name: "NoSuchCharacter9" }, ["v:raccept:F1"]);
      await pr(s, p, "party", { event: "request", name: w.name }, ["v:request:F2", "R:Already in party"]);
      // kick: the priest (2nd) cannot kick the warrior (1st); the warrior kicks the merchant.
      await pr(s, p, "party", { event: "kick", name: w.name }, ["v:kick:F3"]);
      await pr(s, w, "party", { event: "kick", name: "NoSuchCharacter9" }, ["v:kick:F2"]);
      await pr(s, w, "party", { event: "kick", name: mer.name }, ["R:Success", "v:kick:A1", "v:kick:A2", "v:kick:A3", "v:kick:A4"]);
      await pr(s, mer, "party", { event: "kick", name: w.name }, ["v:kick:F1"]);
      await pr(s, mer, "party", { event: "raccept", name: w.name }, ["v:raccept:F3"]);
      await pr(s, mer, "party", { event: "dance" }, ["R:Success"]);
      await pr(s, w, "party", { event: "invite", name: mer.name }, ["R:Success"]);
      await mer.party.waitInvite(w.name, 3000);
      await pr(s, mer, "party", { event: "accept", name: w.name }, ["R:Success"]);

      // A short fight: the warrior and the mage attack gscorpions, the priest heals. ~45 s.
      await fight(s, [w, p, m], 45_000);
      // Attack failures that cost nothing.
      const far = [...w.m.world.monsters.values()].sort((a, b) => w.m.world.distance(w.me, b) - w.m.world.distance(w.me, a))[0];
      if (far) await pr(s, w, "attack", { id: far.id }, ["F8"]);
      await pr(s, w, "attack", { id: w.name }, ["F6"]);
      await pr(s, w, "attack", {}, ["F5"]);
      await pr(s, w, "attack", { id: "999999999" }, ["F7"], { until: on("disappear", "game_response") });
      await pr(s, w, "attack", { id: p.name }, ["F13"]); // a character outside PvP
      const near = w.m.world.nearestMonster();
      if (near) {
        await pr(s, w, "attack", { id: near.id }, ["R:Success", "A1", "A2", "A3", "A4"]);
        await pr(s, w, "attack", { id: near.id }, ["F3"]); // at once again: cooldown
      }
      await pr(s, p, "heal", { id: w.name }, ["R:Success", "A1", "A2", "A3", "A4"]);
      await pr(s, p, "heal", { id: w.name }, ["F4"]);
      await pr(s, w, "heal", { id: p.name }, ["F5"]); // not a priest
      await pr(s, p, "heal", {}, ["F6"]);
      await pr(s, p, "heal", { id: "999999999" }, ["F7"], { until: on("disappear", "game_response") });
      // The merchant (no dartgun) attacks a monster of main: attack_failed.
      const hen = mer.m.world.nearestMonster();
      if (hen) await pr(s, mer, "attack", { id: hen.id }, ["F11"]);
      await pr(s, mer, "heal", { id: w.name }, ["F5"]);
      // Potions and the free regeneration.
      await pr(s, w, "use", { item: "hp" }, ["v:hp:req", "R:Success", "v:hp:A1", "v:hp:A2", "v:hp:A3"]);
      await pr(s, w, "use", { item: "hp" }, ["v:hp:F1"]);
      await sleep(4200);
      const pot = slot(w, "hpot0");
      if (pot >= 0) {
        await pr(s, w, "equip", { num: pot, consume: true }, ["v:Use or equip:R:Potion", "A1", "v:Use or equip:A2", "v:Use or equip:A3"]);
        await pr(s, w, "equip", { num: pot, consume: true }, ["v:Use or equip:F4"]);
      }
      // Chests from the fight.
      for (const c of [w, p, m]) {
        for (const id of [...c.m.world.chests.keys()]) {
          await pr(s, c, "open_chest", { id }, ["R:Opened", "A1", "A2", "A3"], { until: on("chest_opened") });
          c.m.world.chests.delete(id);
        }
      }
      report(s);
    },
  },

  // 3. Desertland: the locksmith, the scrollsmith and Rook are here. The fighters have no
  //    gold, so the paid paths fail with gold_not_enough (free).
  desert: {
    what: "Desertland NPCs: locksmith, scrollsmith (destat), Rook (citizen_route), distance failures of main-only NPCs.",
    chars: [W, P, M],
    run: async (s) => {
      const [w, p, m] = [ch(s, W), ch(s, P), ch(s, M)];
      if (w.me.map !== "desertland") { console.log("warrior is not on desertland; skipping"); return; }
      // Far from main's NPCs: the distance failures.
      const h = slot(w, "hpot0") >= 0 ? slot(w, "hpot0") : 0;
      await pr(s, w, "upgrade", { item_num: h, scroll_num: h, clevel: 0 }, ["F4"]);
      await pr(s, w, "compound", { items: [0, 1, 2], scroll_num: 3, clevel: 0 }, ["F9"]);
      await pr(s, w, "buy", { name: "staff", quantity: 1 }, ["F4"]);
      await pr(s, w, "sell", { num: h, quantity: 1 }, ["F7"]);
      await pr(s, w, "exchange", { item_num: h }, ["F7"]);
      await pr(s, w, "dismantle", { num: h }, ["F2"]);
      await pr(s, w, "craft", { items: [[0, h]] }, ["F6"]);
      await pr(s, w, "monsterhunt", undefined, ["F2"]);
      await pr(s, w, "secondhands", {}, ["F2"]);
      await pr(s, w, "secondhands", { request_id: "sh1" }, ["F2"]);
      await pr(s, w, "tarot", undefined, ["F2"]);
      await pr(s, w, "lostandfound", { request_id: "lf1" }, ["F2"]);
      await pr(s, w, "lostandfound", "info", ["R:Info"]);
      await pr(s, w, "donate", { gold: 1, request_id: "d1" }, ["F2"]);
      await pr(s, w, "eval", { command: "hello" }, ["F2"]);
      await pr(s, w, "bet", { type: "wheel", side: "sun", gold: 10000 }, ["F2"]);
      await pr(s, w, "send", { name: "SETYMerchant", gold: 1 }, ["F3"]); // another map
      await pr(s, w, "bank", { operation: "deposit", amount: 1 }, ["F2"]);
      // Locksmith (316, -270): the paid operations fail on gold (we have 0).
      if (await toNpc(s, w, "desertland", "locksmith")) {
        const it = slot(w, "hpot1") >= 0 ? slot(w, "hpot1") : h;
        await pr(s, w, "locksmith", { num: it, operation: "lock" }, ["F5"]); // a potion: locksmith_cant? (pots are not scrolls)
        await pr(s, w, "locksmith", { num: empty(w), operation: "lock" }, ["F4"]);
        await pr(s, w, "locksmith", { num: it, operation: "unlock" }, ["v:unlock:F1"]);
        await pr(s, w, "locksmith", { num: it, operation: "seal" }, ["v:seal:F1"]);
        await pr(s, w, "locksmith", { num: it, operation: "dance" }, ["v:Other:req", "R:Success"]);
        await pr(s, w, "interaction", { type: "citizen_route", destination: "scrollsmith" }, ["v:citizen_route:F1"]);
      }
      // Rook (citizen17) walks around; try near his spawn.
      const rook = [...w.m.world.players.values()].find((x) => x.id === "citizen17" || (x as Record<string, unknown>).npc === "citizen17");
      if (rook && await walk(s, w, rook.x, rook.y + 30, 100)) {
        await pr(s, w, "interaction", { type: "citizen_route", destination: "scrollsmith", request_id: "cr1" }, ["v:citizen_route:R:Route", "v:citizen_route:R:Route done", "v:citizen_route:A1"], { until: on("game_response", "citizen"), timeoutMs: 2500 });
        await pr(s, w, "interaction", { type: "citizen_route", destination: "scrollsmith" }, ["v:citizen_route:F2"], { until: on("game_log", "game_response") });
      }
      // Scrollsmith (606, -1590): destat.
      if (await toNpc(s, m, "desertland", "scrollsmith")) {
        await pr(s, m, "destat", { num: empty(m) }, ["F3"]);
        await pr(s, m, "destat", { num: slot(m, "hpot0") }, ["F4"]);
        await pr(s, m, "destat", { num: slot(m, "hpot0"), request_id: "ds1" }, ["F4"]);
      }
      await pr(s, p, "destat", { num: 0 }, ["F2"]); // the priest stayed far
      report(s);
    },
  },

  // 4. The fighters go to main; everyone gathers near the shops.
  gather: {
    what: "Bring the three fighters to main (transporter) and next to the merchant.",
    run: async (s) => {
      const [w, p, m, mer] = [ch(s, W), ch(s, P), ch(s, M), ch(s, MER)];
      // The town teleport of desertland first (exercises `town`), then the transporter.
      await pr(s, w, "town", undefined, ["R:Channel", "R:Started"], { until: on("game_response") });
      await pr(s, w, "stop", { action: "town" }, ["R:Success", "A3"]);
      await pr(s, p, "town", undefined, ["R:Channel", "R:Started", "R:Arrived", "A1"], { until: on("new_map"), timeoutMs: 6000 });
      for (const c of [w, p, m]) {
        await goMap(s, c, "main");
      }
      for (const c of [w, p, m, mer]) await walk(s, c, -120 + Math.random() * 40, -120, 80);
      report(s);
    },
  },

  // 5. Shops, inventory, upgrade, compound, exchange. Everyone on main.
  shop: {
    what: "Main shops: buy/sell/split/imove/send/destroy/equip/unequip/upgrade/compound/exchange and their cheap failures.",
    run: async (s) => {
      const [w, p, m, mer] = [ch(s, W), ch(s, P), ch(s, M), ch(s, MER)];
      if (mer.me.map !== "main" || w.me.map !== "main") { console.log("run `gather` first"); return; }
      // Gold: the merchant sends some to the warrior (own account: no tax).
      if (gold(w) === 0) await pr(s, w, "send", { name: mer.name, gold: 1 }, ["v:Gold:F1"]);
      await walk(s, w, mer.me.x + 30, mer.me.y, 60);
      await pr(s, mer, "send", { name: w.name, gold: 300 }, ["v:Gold:R:Gold sent", "v:Gold:A1", "v:Gold:A2", "v:Gold:A3"]);
      await pr(s, mer, "send", { name: "NoSuchCharacter9", gold: 1 }, ["F2"]);
      await pr(s, mer, "send", { name: w.name }, ["v:None:R:Nothing"], NONE);
      await pr(s, mer, "send", { name: w.name, num: empty(mer) }, ["v:Item:F1"]);
      await pr(s, mer, "send", { name: w.name, cx: "nosuchcx" }, ["v:Cosmetic:F1"]);
      const hp1 = slot(mer, "hpot1");
      if (hp1 >= 0) await pr(s, mer, "send", { name: w.name, num: hp1, q: 1 }, ["v:Item:R:Item sent", "v:Item:A1", "v:Item:A2", "v:Item:A3"]);

      // Buy at fancypots (-35,-162) and basics (-89,-165), near where we stand.
      await toNpc(s, w, "main", "fancypots");
      await pr(s, w, "buy", { name: "hpot0", quantity: 1 }, ["R:Success", "A1", "A2"]);
      await pr(s, w, "buy", { name: "ringsj", quantity: 1 }, ["F2"]);
      await pr(s, p, "buy", { name: "hpot0", quantity: 1 }, ["F5"]); // the priest has 0 gold
      await toNpc(s, mer, "main", "basics");
      if (slot(mer, "helmet", 0) < 0) await pr(s, mer, "buy", { name: "helmet", quantity: 1 }, ["R:Success"]);
      // Sell one potion (to any shop NPC within 400 px).
      const wp = slot(w, "hpot0");
      if (wp >= 0) await pr(s, w, "sell", { num: wp, quantity: 1 }, ["R:Success", "A1", "A2"]);
      await pr(s, w, "sell", { num: empty(w), quantity: 1 }, ["F3"]);
      // Split, imove, destroy on the warrior's potion stacks.
      const st = slot(w, "hpot1");
      if (st >= 0) {
        await pr(s, w, "split", { num: st, quantity: 1 }, ["R:Success", "A1"]);
        await pr(s, w, "split", { num: st, quantity: 999999 }, ["R:Whole stack"]);
      }
      await pr(s, w, "split", { num: empty(w), quantity: 1 }, ["F2"]);
      const hel = slot(mer, "helmet", 0);
      if (hel >= 0) await pr(s, mer, "split", { num: hel, quantity: 1 }, ["F3"]);
      await pr(s, w, "imove", { a: 0, b: 1 }, ["R:Success", "A1"]);
      await pr(s, w, "imove", { a: 1, b: 0 }, ["R:Success"]);
      await pr(s, w, "imove", { a: 2, b: 2 }, ["F2"]);
      await pr(s, w, "imove", { a: 2, b: 99 }, ["F3"]);
      const one = slot(w, "hpot1");
      if (one >= 0) await pr(s, w, "destroy", { num: one, q: 1 }, ["R:Success", "A3"]);
      await pr(s, w, "destroy", { num: empty(w), q: 1 }, ["F2"]);
      await pr(s, w, "throw", { num: empty(w) }, ["F7"]);
      if (slot(w, "hpot0") >= 0) await pr(s, w, "throw", { num: slot(w, "hpot0"), x: w.me.x, y: w.me.y }, ["F5"]);

      // Equip / unequip on the merchant (helmet off and on), and the failures.
      await pr(s, mer, "unequip", { slot: "helmet" }, ["R:Success", "A1"]);
      const h0 = slot(mer, "helmet", 0);
      if (h0 >= 0) await pr(s, mer, "equip", { num: h0, slot: "helmet" }, ["v:Use or equip:R:Equipped", "A1"]);
      await pr(s, mer, "unequip", { slot: "elixir" }, ["F2"]);
      await pr(s, mer, "unequip", { slot: "earring1" }, ["F1"]);
      await pr(s, mer, "equip", { num: empty(mer) }, ["F3"]);
      await pr(s, mer, "equip", { num: 99 }, ["F2"]);
      const pots = slot(mer, "hpot1");
      if (pots >= 0) await pr(s, mer, "equip", { num: pots, slot: "helmet" }, ["v:Use or equip:F6"]);
      const shell = slot(mer, "seashell");
      if (shell >= 0) await pr(s, mer, "equip", { num: shell, consume: true }, ["v:Use or equip:F7"]);
      await pr(s, mer, "equip_batch", [{ num: slot(mer, "helmet", 0) >= 0 ? slot(mer, "helmet", 0) : 0, slot: "helmet" }], ["R:Success", "A2"]);
      await pr(s, mer, "equip_batch", { num: 0 }, ["F2"]);
      await pr(s, mer, "equip_batch", [null], ["F3"], { until: on("game_error", "game_response") });
      await pr(s, mer, "activate", { slot: "amulet" }, ["v:Equipment:F4"], NONE);
      await pr(s, mer, "activate", { num: empty(mer) }, ["v:Inventory:R:Inventory updated"], { until: on("player"), timeoutMs: 1200 });
      await pr(s, mer, "booster", { num: 0 }, ["F3"]);
      await pr(s, mer, "booster", null, ["F2"]);
      await pr(s, mer, "convert", { num: empty(mer) }, ["F2"], NONE);
      await pr(s, mer, "merge", { container: "mainhand", pet: "offhand" }, ["F2"]);
      await pr(s, mer, "exchange_buy", { num: 0, name: "x", q: 1 }, ["F3"]);

      // Upgrade at Cue (-207,-220): a +0 helmet with a scroll0 (about 100%: +0 to +1).
      await toNpc(s, mer, "main", "newupgrade");
      const helmet = slot(mer, "helmet", 0);
      const sc = slot(mer, "scroll0");
      const csc0 = slot(mer, "cscroll0");
      if (helmet >= 0 && sc >= 0) {
        await pr(s, mer, "upgrade", { item_num: helmet, scroll_num: sc, clevel: 0, calculate: true }, ["v:true:req", "v:true:R:Chance"]);
        await pr(s, mer, "upgrade", { item_num: helmet, scroll_num: sc, clevel: 3 }, ["F8"]);
        await pr(s, mer, "upgrade", { item_num: empty(mer), scroll_num: sc, clevel: 0 }, ["F5"]);
        await pr(s, mer, "upgrade", { item_num: helmet, scroll_num: empty(mer), clevel: 0 }, ["F7"]);
        const pot = slot(mer, "mpot1");
        if (pot >= 0) await pr(s, mer, "upgrade", { item_num: pot, scroll_num: sc, clevel: 0 }, ["F9"]);
        if (pot >= 0) await pr(s, mer, "upgrade", { item_num: helmet, scroll_num: pot, offering_num: pot, clevel: 0 }, ["F6"]);
        if (csc0 >= 0) await pr(s, mer, "upgrade", { item_num: helmet, scroll_num: csc0, clevel: 0 }, ["F11"]);
        // The real upgrade, then a second request while it runs.
        const r = pr(s, mer, "upgrade", { item_num: helmet, scroll_num: sc, clevel: 0 }, ["v:Upgrade:req", "v:Upgrade:R:Started", "v:Upgrade:R:Progress", "v:Upgrade:R:Success", "v:Upgrade:R:Fail", "v:Upgrade:A1", "v:Upgrade:A3"], { until: (f) => responsesIn(f).some((x) => /^upgrade_(success|fail)/.test(codeOf(x))), timeoutMs: 15000 });
        await sleep(400);
        await pr(s, mer, "upgrade", { item_num: helmet, scroll_num: sc, clevel: 0 }, ["F3"], { timeoutMs: 1200 });
        await r;
      }
      // Compound: three test_orb (1 gold each at the standmerchant) and a cscroll0.
      await toNpc(s, mer, "main", "scrolls");
      if (slot(mer, "cscroll0") < 0) await pr(s, mer, "buy", { name: "cscroll0", quantity: 1 }, ["R:Success"]);
      await toNpc(s, mer, "main", "standmerchant");
      while (mer.items.count("test_orb") < 5) {
        const r = await pr(s, mer, "buy", { name: "test_orb", quantity: 1 }, ["R:Success"]);
        if (!got(r, "buy_success")) break;
      }
      await toNpc(s, mer, "main", "newupgrade");
      const orbs = (mer.me.items ?? []).map((it, i) => (it && it.name === "test_orb" && !it.level ? i : -1)).filter((i) => i >= 0);
      const cs = slot(mer, "cscroll0");
      if (orbs.length >= 3 && cs >= 0) {
        const three = orbs.slice(0, 3);
        await pr(s, mer, "compound", { items: three, scroll_num: cs, clevel: 0, calculate: true }, ["v:true:req", "v:true:R:Chance"]);
        await pr(s, mer, "compound", { items: three.slice(0, 2), scroll_num: cs, clevel: 0 }, ["F1"]);
        await pr(s, mer, "compound", { items: ["a", 1, 2], scroll_num: cs, clevel: 0 }, ["F2"]);
        await pr(s, mer, "compound", { items: three, scroll_num: empty(mer), clevel: 0 }, ["F7"]);
        await pr(s, mer, "compound", { items: [three[0], three[1], empty(mer)], scroll_num: cs, clevel: 0 }, ["F8"]);
        await pr(s, mer, "compound", { items: [three[0], three[0], three[1]], scroll_num: cs, clevel: 0 }, ["F15"]);
        await pr(s, mer, "compound", { items: three, scroll_num: cs, clevel: 2 }, ["F12"]);
        const ring = slot(mer, "ringsj");
        if (ring >= 0) await pr(s, mer, "compound", { items: [three[0], three[1], ring], scroll_num: cs, clevel: 0 }, ["F11"]);
        const sc2 = slot(mer, "scroll0");
        if (sc2 >= 0) await pr(s, mer, "compound", { items: three, scroll_num: sc2, clevel: 0 }, ["F14"]);
        await pr(s, mer, "compound", { items: three, scroll_num: cs, offering_num: slot(mer, "mpot1"), clevel: 0 }, ["F6"]);
        const r = pr(s, mer, "compound", { items: three, scroll_num: cs, clevel: 0 }, ["v:Compound:req", "v:Compound:R:Started", "v:Compound:R:Progress", "v:Compound:R:Success", "v:Compound:R:Fail", "v:Compound:A1", "v:Compound:A3"], { until: (f) => responsesIn(f).some((x) => /^compound_(success|fail)/.test(codeOf(x))), timeoutMs: 16000 });
        await sleep(400);
        await pr(s, mer, "compound", { items: three, scroll_num: cs, clevel: 0 }, ["F5"], { timeoutMs: 1200 });
        await r;
      }
      // Exchange (Xyn, -25,-478): one anniversarygift. Then the failures.
      await toNpc(s, mer, "main", "exchange");
      const gift = slot(mer, "anniversarygift");
      if (gift >= 0) {
        const r = pr(s, mer, "exchange", { item_num: gift }, ["R:Started", "R:Log", "A1", "A5", "A6"], { until: on("game_log"), timeoutMs: 12000, tailMs: 1500 });
        await sleep(500);
        await pr(s, mer, "exchange", { item_num: gift }, ["F2"], { timeoutMs: 1200 });
        await r;
      }
      await pr(s, mer, "exchange", { item_num: empty(mer) }, ["F4"]);
      const shells = slot(mer, "seashell");
      if (shells >= 0) await pr(s, mer, "exchange", { item_num: shells }, ["F8", "F9"]);
      const hpm = slot(mer, "hpot1");
      if (hpm >= 0) await pr(s, mer, "exchange", { item_num: hpm }, ["F7"]);
      // Monster Hunter (126,-413): the warrior starts a hunt; the merchant may not.
      await toNpc(s, w, "main", "monsterhunter");
      await pr(s, w, "monsterhunt", undefined, ["R:Started notice", "R:Started", "A1"], { until: (f) => responsesIn(f).some((x) => codeOf(x) === "data"), timeoutMs: 3000 });
      await pr(s, w, "monsterhunt", undefined, ["F3"]);
      await toNpc(s, mer, "main", "monsterhunter");
      await pr(s, mer, "monsterhunt", undefined, ["F4"]);
      // Craftsman (92,670): dismantle and craft failures that need the NPC.
      await toNpc(s, mer, "main", "craftsman");
      const pot2 = slot(mer, "mpot1");
      if (pot2 >= 0) await pr(s, mer, "dismantle", { num: pot2 }, ["F6"]);
      await pr(s, mer, "craft", { items: [] }, ["F3"]);
      await pr(s, mer, "craft", { items: [[0, empty(mer)]] }, ["F5"]);
      if (pot2 >= 0) await pr(s, mer, "craft", { items: [[0, pot2]] }, ["F6"]);
      report(s);
    },
  },

  // 6. The merchant's stand: listings, wishlist, trades with our own warrior, giveaway.
  stand: {
    what: "Merchant stand and trades between own characters: merchant, equip trade listing, trade_buy/sell/swap, wishlist, giveaway.",
    chars: [W, MER],
    run: async (s) => {
      const [w, mer] = [ch(s, W), ch(s, MER)];
      if (mer.me.map !== "main") { console.log("merchant is not on main"); return; }
      // A quiet spot near the fancypots NPC, both next to each other.
      await walk(s, mer, 20, -100, 60);
      await walk(s, w, 50, -100, 60);
      const stand = slot(mer, "stand0");
      await pr(s, mer, "merchant", { num: empty(mer) }, ["F2"]);
      if (stand >= 0) await pr(s, mer, "merchant", { num: stand }, ["R:Success", "A1", "A2"]);
      await pr(s, w, "trade", { event: "show" }, ["v:show:R:Shown"], { until: on("player"), timeoutMs: 1200 });
      await pr(s, w, "trade", { event: "show" }, ["v:show:F1"], NONE);
      await pr(s, w, "trade", { event: "hide" }, ["v:hide:R:Hidden"], { until: on("player"), timeoutMs: 1200 });
      await pr(s, w, "trade", { event: "hide" }, ["v:hide:F1"], NONE);
      // A listing: one test_orb at 1 gold, in trade1.
      let orb = slot(mer, "test_orb");
      if (orb >= 0) await pr(s, mer, "equip", { num: orb, slot: "trade1", price: 1 }, ["v:Trade listing:req", "v:Trade listing:R:Listed", "v:Trade listing:A1", "A1"]);
      const t1 = () => ((mer.me as unknown as { slots: Record<string, { rid?: string } | null> }).slots?.trade1 ?? null);
      orb = slot(mer, "test_orb");
      if (orb >= 0) await pr(s, mer, "equip", { num: orb, slot: "trade1", price: 1 }, ["v:Trade listing:F4"]);
      await pr(s, w, "trade_buy", { id: mer.name, slot: "nope", q: 1 }, ["F2"]);
      await pr(s, w, "trade_buy", { id: "NoSuchCharacter9", slot: "trade1", q: 1 }, ["F3"]);
      await pr(s, mer, "trade_buy", { id: mer.name, slot: "trade1", q: 1 }, ["F6"]);
      await pr(s, w, "trade_buy", { id: mer.name, slot: "trade1", rid: "zzzz", q: 1 }, ["F7"]);
      await pr(s, w, "trade_buy", { id: mer.name, slot: "trade1", rid: t1()?.rid, q: 5 }, ["F11"]);
      if (t1()) await pr(s, w, "trade_buy", { id: mer.name, slot: "trade1", rid: t1()!.rid, q: 1 }, ["R:Success", "A1", "A2", "A3", "A4", "A5"]);
      // A wishlist entry: the merchant buys one hpot0 for 1 gold; the warrior sells it.
      await pr(s, mer, "trade_wishlist", { slot: "trade2", name: "hpot0", q: 1, price: 1 }, ["R:Success", "A1"]);
      await pr(s, mer, "trade_wishlist", { slot: "trade99", name: "hpot0", q: 1, price: 1 }, ["F2"]);
      const t2 = () => ((mer.me as unknown as { slots: Record<string, { rid?: string } | null> }).slots?.trade2 ?? null);
      await pr(s, w, "trade_buy", { id: mer.name, slot: "trade2", rid: t2()?.rid, q: 1 }, ["F9"]);
      await pr(s, w, "trade_sell", { id: mer.name, slot: "nope", q: 1 }, ["F2"]);
      await pr(s, w, "trade_sell", { id: "NoSuchCharacter9", slot: "trade2", q: 1 }, ["F3"]);
      await pr(s, mer, "trade_sell", { id: mer.name, slot: "trade2", q: 1 }, ["F5"]);
      await pr(s, w, "trade_sell", { id: mer.name, slot: "trade2", rid: "zzzz", q: 1 }, ["F6"]);
      await pr(s, w, "trade_sell", { id: mer.name, slot: "trade1", q: 1 }, ["F6", "F8"]);
      await pr(s, w, "trade_sell", { id: mer.name, slot: "trade2", rid: t2()?.rid, q: 5 }, ["F9"]);
      if (slot(w, "hpot0") < 0) await pr(s, w, "buy", { name: "hpot0", quantity: 1 }, ["R:Success"]);
      if (t2()) await pr(s, w, "trade_sell", { id: mer.name, slot: "trade2", rid: t2()!.rid, q: 1 }, ["R:Success", "A1", "A2", "A3", "A4", "A5"]);
      // A swap offer: one test_orb for one hpot0, in trade3.
      orb = slot(mer, "test_orb");
      if (orb >= 0) await pr(s, mer, "equip", { num: orb, slot: "trade3", want: { name: "mpot0", q: 1 } }, ["v:Trade listing:R:Listed"]);
      const t3 = () => ((mer.me as unknown as { slots: Record<string, { rid?: string } | null> }).slots?.trade3 ?? null);
      await pr(s, w, "trade_swap", { id: mer.name, slot: "trade3", rid: t3()?.rid, num: slot(w, "hpot1"), item: { name: "hpot1" } }, ["F14"]);
      await pr(s, w, "trade_swap", { id: mer.name, slot: "trade3", rid: "zzzz", num: 0, item: { name: "x" } }, ["F7"]);
      await pr(s, w, "trade_swap", { id: mer.name, slot: "trade2", rid: t2()?.rid ?? "zzzz", num: 0, item: { name: "x" } }, ["F7", "F9"]);
      await pr(s, w, "trade_swap", { id: mer.name, slot: "trade3", rid: t3()?.rid, num: empty(w), item: { name: "x" } }, ["F10"]);
      await pr(s, w, "trade_swap", { id: mer.name, slot: "nope", rid: "zzzz", num: 0, item: { name: "x" } }, ["F2"]);
      await pr(s, w, "trade_swap", { id: "NoSuchCharacter9", slot: "trade3", rid: "zzzz", num: 0, item: { name: "x" } }, ["F3"]);
      await pr(s, mer, "trade_swap", { id: mer.name, slot: "trade3", rid: "zzzz", num: 0, item: { name: "x" } }, ["F6"]);
      if (slot(w, "mpot0") < 0) await pr(s, w, "buy", { name: "mpot0", quantity: 1 }, ["R:Success"]);
      const mp0 = slot(w, "mpot0");
      if (t3() && mp0 >= 0) {
        const it = w.me.items[mp0]!;
        await pr(s, w, "trade_swap", { id: mer.name, slot: "trade3", rid: t3()!.rid, num: mp0, item: { name: it.name, q: it.q } }, ["R:Success", "A1", "A2", "A3", "A4", "A5"]);
      }
      // A giveaway of one test_orb in trade4. The warrior has no auth_id: need_auth.
      orb = slot(mer, "test_orb");
      if (orb >= 0) await pr(s, mer, "equip", { num: orb, slot: "trade4", giveaway: true, minutes: 1 }, ["v:Trade listing:R:Listed"]);
      const t4 = () => ((mer.me as unknown as { slots: Record<string, { rid?: string } | null> }).slots?.trade4 ?? null);
      await pr(s, w, "join_giveaway", { id: mer.name, slot: "trade4", rid: t4()?.rid }, ["F9", "R:Success"]);
      await pr(s, w, "join_giveaway", { id: mer.name, slot: "nope", rid: "x" }, ["F2"]);
      await pr(s, w, "join_giveaway", { id: "NoSuchCharacter9", slot: "trade4", rid: "x" }, ["F3"]);
      await pr(s, mer, "join_giveaway", { id: mer.name, slot: "trade4", rid: t4()?.rid }, ["F6"]);
      await pr(s, w, "join_giveaway", { id: mer.name, slot: "trade4", rid: "zzzz" }, ["F7"]);
      await pr(s, w, "join_giveaway", { id: mer.name, slot: "trade2", rid: t2()?.rid ?? "zzzz" }, ["F7", "F8"]);
      await pr(s, mer, "unequip", { slot: "trade4" }, ["F3"]);
      // Clean up: take back the listings, close the stand.
      for (const sl of ["trade1", "trade2", "trade3"]) {
        const v = (mer.me as unknown as { slots: Record<string, unknown> }).slots?.[sl];
        if (v) await pr(s, mer, "unequip", { slot: sl }, ["R:Success"]);
      }
      await pr(s, mer, "merchant", { close: 1 }, ["R:Success"]);
      report(s);
    },
  },

  // 7. The bank: walk in, deposit/withdraw 1 gold, store/retrieve one potion, move, unlock.
  bank: {
    what: "Bank: transport in/out, deposit/withdraw, swap store/retrieve, move, unlock failures; bank_unavailable outside.",
    chars: [MER],
    run: async (s) => {
      const mer = ch(s, MER);
      await pr(s, mer, "bank", { operation: "withdraw", amount: 1 }, ["F2"]);
      await pr(s, mer, "transport", { to: "nowhere_map" }, ["F4"]);
      await pr(s, mer, "transport", { to: "winterland", s: 0 }, ["F7"]);
      if (!(await goMap(s, mer, "bank"))) return;
      await pr(s, mer, "bank", { operation: "deposit", amount: 1 }, ["v:deposit:req", "v:deposit:R:Deposit data", "v:deposit:R:Deposit", "A1"], { tailMs: 600 });
      await pr(s, mer, "bank", { operation: "withdraw", amount: 1 }, ["v:withdraw:req", "v:withdraw:R:Withdraw data", "v:withdraw:R:Withdraw", "A1"], { tailMs: 600 });
      const pot = slot(mer, "mpot1");
      if (pot >= 0) {
        await pr(s, mer, "bank", { operation: "swap", pack: "items0", inv: pot, str: -1 }, ["v:swap:R:Stored"]);
        // Retrieve: find where it went in items0.
        const pack = ((mer.me as unknown as { user?: Record<string, ({ name: string } | null)[]> }).user?.items0) ?? [];
        const at = pack.findIndex((x) => x?.name === "mpot1");
        await pr(s, mer, "bank", { operation: "move", pack: "items0", a: at >= 0 ? at : 0, b: 40 }, ["R:Success", "v:move:req"]);
        await pr(s, mer, "bank", { operation: "move", pack: "items0", a: 40, b: 40 }, ["v:move:F2"]);
        await pr(s, mer, "bank", { operation: "swap", pack: "items0", str: 40, inv: -1 }, ["v:swap:R:Retrieved"]);
      }
      await pr(s, mer, "bank", { operation: "swap", pack: "items0", str: -1, inv: -1 }, ["v:swap:F2"]);
      await pr(s, mer, "bank", { operation: "swap", pack: "items47", str: 0, inv: 0 }, ["v:swap:F1"]);
      await pr(s, mer, "bank", { operation: "move", pack: "items47", a: 0, b: 1 }, ["v:move:F1"]);
      await pr(s, mer, "bank", { operation: "unlock", pack: "nosuchpack", gold: true }, ["v:unlock:F1"]);
      await pr(s, mer, "bank", { operation: "unlock", pack: "items0", gold: true }, ["v:unlock:F2"]);
      await pr(s, mer, "bank", { operation: "unlock", pack: "items40", gold: true }, ["v:unlock:F3"]);
      await pr(s, mer, "bank", { operation: "dance" }, ["R:Success"]);
      await pr(s, mer, "bless_server", {}, ["F1"]); // in the bank: cant_in_bank
      // Out again.
      await goMap(s, mer, "main");
      report(s);
    },
  },

  // 8. Social: chat, cm, friends, magiport, duel, tavern, poker, donate, lost and found, ...
  social: {
    what: "Chat, cm, friend, magiport, duel (own warrior vs own mage), tavern/poker info, donate 1, lostandfound, secondhands, misc.",
    run: async (s) => {
      const [w, p, m, mer] = [ch(s, W), ch(s, P), ch(s, M), ch(s, MER)];
      // Chat.
      await pr(s, w, "say", { message: "x", party: true }, ["v:true:req", "R:Success", "v:true:A1"]);
      await sleep(500);
      await pr(s, w, "say", { message: "x", name: p.name }, ["v:Private:req", "R:Success", "v:Private:R:Private copy", "v:Private:A1"]);
      await sleep(500);
      await pr(s, w, "say", { message: "x", name: w.name }, ["v:Private:F1"]);
      await sleep(500);
      await pr(s, w, "say", { message: "x", name: "NoSuchCharacter9" }, ["R:Success", "v:Private:R:Private failed"], { until: on("pm"), timeoutMs: 4000 });
      await pr(s, w, "say", { message: "x", party: true }, ["F4"]);
      await sleep(500);
      await pr(s, w, "say", { message: 5 }, ["F2"]);
      await sleep(500);
      await pr(s, w, "say", { message: "   " }, ["F5"]);
      await sleep(500);
      await pr(s, mer, "party", { event: "leave" }, ["R:Success"]);
      await pr(s, mer, "say", { message: "x", party: true }, ["v:true:F1"]);
      await sleep(500);
      await pr(s, mer, "say", { message: "hi" }, ["v:Public:req", "R:Success", "v:Public:A1"]);
      // cm between own characters.
      await pr(s, w, "cm", { to: [p.name, m.name], message: "probe" }, ["R:Success", "A1"]);
      await pr(s, w, "cm", { to: p.name, message: { a: 1 } }, ["R:Success"]);
      // Friends: own account.
      await pr(s, w, "friend", { event: "request", name: p.name }, ["v:request:F2", "v:request:R:Already friends"]);
      await pr(s, w, "friend", { event: "request", name: "NoSuchCharacter9" }, ["v:request:F1"]);
      await pr(s, w, "friend", { event: "accept", name: p.name }, ["v:accept:F1"]);
      await pr(s, w, "friend", { event: "unfriend", name: p.name, request_id: "uf1" }, ["R:In progress", "v:unfriend:R:Unfriend complete"], { until: (f) => responsesIn(f).some((x) => /unfriend_/.test(codeOf(x))), timeoutMs: 6000 });
      await pr(s, w, "friend", { event: "dance" }, ["R:In progress"]);
      // Magiport: the mage offers, the priest accepts.
      await pr(s, p, "magiport", { name: m.name }, ["F2"]);
      await pr(s, m, "skill", { name: "magiport", id: p.name }, ["v:magiport:R:Magiport sent", "R:Success", "v:magiport:A1", "v:magiport:A2"], { until: (f) => responsesIn(f).some((x) => codeOf(x) === "data"), timeoutMs: 2500 });
      await pr(s, p, "magiport", { name: m.name }, ["R:Success", "A1", "A2"], { until: on("new_map"), timeoutMs: 3000 });
      // Skills: a few of each class, and the checks that fail.
      await pr(s, w, "skill", { name: "charge" }, ["v:charge:req", "R:Success", "A3", "A4"]);
      await pr(s, w, "skill", { name: "charge" }, ["F12"]);
      await pr(s, w, "skill", { name: "hardshell" }, ["F11"]);
      await pr(s, w, "skill", { name: "nosuchskill" }, ["F4"]);
      await pr(s, w, "skill", { name: "curse", id: "1" }, ["F13"]);
      await pr(s, w, "skill", { name: "rimeshell" }, ["F5"]);
      await pr(s, w, "skill", { name: "boop", id: p.name }, ["F9"]);
      await pr(s, w, "skill", { name: "taunt" }, ["F16", "F17"]);
      await pr(s, w, "skill", { name: "dash", x: w.me.x + 30, y: w.me.y }, ["v:dash:req", "v:dash:R:Dash move"], { until: on("eval", "game_response") });
      await pr(s, w, "skill", { name: "dash", x: w.me.x + 300, y: w.me.y }, ["v:dash:F1"]);
      await pr(s, m, "skill", { name: "light" }, ["F10"]);
      await pr(s, m, "skill", { name: "energize", id: p.name, mp: 1 }, ["v:energize:req", "R:Success", "v:energize:A1", "v:energize:A2"]);
      await pr(s, m, "skill", { name: "blink", x: m.me.x + 40, y: m.me.y }, ["v:blink:req", "R:Success"], { tailMs: 800 });
      await pr(s, m, "skill", { name: "blink", x: 99999, y: 99999 }, ["v:blink:F1"]);
      await pr(s, m, "skill", { name: "warp", x: 0, y: 0, in: "nosuchinstance" }, ["v:blink:F1", "v:warp:F1"]);
      await pr(s, p, "skill", { name: "partyheal" }, ["v:partyheal:req", "R:Success"]);
      await pr(s, p, "skill", { name: "absorb", id: w.name }, ["F11"]);
      await pr(s, p, "skill", { name: "curse" }, ["F17"]);
      await pr(s, p, "skill", { name: "curse", id: p.name }, ["F19"]);
      await pr(s, p, "skill", { name: "curse", id: "999999999" }, ["F20"], { until: on("disappear", "game_response") });
      await pr(s, mer, "skill", { name: "mluck", id: w.name }, ["F11"]);
      await pr(s, mer, "skill", { name: "invis" }, ["F13"]);
      await pr(s, mer, "skill", { name: "3shot", ids: "x" }, ["F6"]);
      await pr(s, mer, "skill", { name: "cburst", targets: "x" }, ["F7"]);
      // Tavern and poker info, and their failures from main.
      await pr(s, w, "tavern", { event: "info", game: "dice" }, ["R:Info"]);
      await pr(s, w, "tavern", { event: "nope" }, ["F1"], NONE);
      await pr(s, w, "poker", { event: "info", request_id: "pk1" }, ["v:info:req", "v:info:R:Info", "v:info:A1"]);
      await pr(s, w, "poker", { event: "join", gold: 1 }, ["F6"]);
      await pr(s, w, "poker", { event: "nope" }, ["F6", "F8"]);
      await pr(s, w, "bet", { type: "wheel", side: "sun" }, ["F2"]);
      // Donate the minimum, lost and found, secondhands near Ponty (106,-47).
      await toNpc(s, mer, "main", "secondhands");
      await pr(s, mer, "donate", { gold: 1 }, ["R:Success", "A1"]);
      await pr(s, mer, "donate", { gold: 1, request_id: "dn1" }, ["F2"]);
      await pr(s, mer, "donate", { gold: 999999999 }, ["F3"]);
      await pr(s, mer, "lostandfound", { request_id: "lf2" }, ["F2"]);
      await pr(s, mer, "secondhands", {}, ["R:List"]);
      await pr(s, mer, "secondhands", { request_id: "sh2" }, ["R:List"]);
      await pr(s, mer, "sbuy", { rid: "zzzz" }, ["F7"], { until: on("game_response", "game_log") });
      await pr(s, mer, "sbuy", { rid: "zzzz", request_id: "sb1" }, ["F7"]);
      await pr(s, mer, "sbuy", { rid: "zzzz", f: true, request_id: "sb2" }, ["F2"]);
      // Misc: signup, mail, cx, interaction, join, enter, transport, leave, tarot, ...
      await pr(s, mer, "signup", undefined, ["R:Success"], { until: (f) => responsesIn(f).some((x) => codeOf(x) === "signed_up") });
      await pr(s, mer, "mail", { to: w.name, subject: "x", message: "x" }, ["F3"]);
      await pr(s, mer, "mail_take_item", { id: "ML_nosuchmail", request_id: 1 }, ["F3"], { timeoutMs: 4000 });
      await pr(s, mer, "cx", { name: "nosuchcosmetic" }, ["v:Put on:F1"]);
      await pr(s, mer, "cx", { slot: "hat" }, ["v:Clear:req", "R:Update", "R:Success"]);
      await pr(s, mer, "cx", { name: "hat404" }, ["v:Put on:req", "R:Update", "R:Success"]);
      await pr(s, mer, "skin", { name: "goo" }, ["F2"], NONE);
      await pr(s, mer, "poke", { name: w.name }, ["F1"], NONE);
      await pr(s, mer, "misc_npc", { npc: "x" }, ["F2"], NONE);
      await pr(s, mer, "pet", undefined, ["F3"], { until: on("game_error") });
      await pr(s, mer, "whistle", undefined, ["F2"], NONE);
      await pr(s, mer, "creward", { name: "x" }, ["F2"], { until: on("game_error") });
      await pr(s, mer, "ureward", { name: "c0" }, ["F2"]);
      await pr(s, mer, "ureward", { name: "nope" }, ["F1"], NONE);
      await pr(s, mer, "interaction", { type: "merrit_info" }, ["v:merrit_info:req", "v:merrit_info:R:Market patron"], { until: on("merrit_status"), timeoutMs: 3000 });
      await pr(s, mer, "interaction", { type: "merrit_info" }, ["v:merrit_info:F1"], NONE);
      await pr(s, w, "interaction", { type: "cavalry", request_id: "cv1" }, ["v:cavalry:F1"], { timeoutMs: 3000 });
      await pr(s, w, "interaction", { type: "newyear_tree", request_id: "ny1" }, ["v:newyear_tree:F1"]);
      await pr(s, w, "interaction", { type: "redorb" }, ["v:redorb:F1"]);
      await pr(s, w, "interaction", { type: "the_lever" }, ["v:the_lever:F1"]);
      await pr(s, w, "interaction", "the_lever", ["v:Lever (bare):req", "v:the_lever:F1"]);
      await pr(s, w, "interaction", { type: "dailytask" }, ["v:dailytask:F1"]);
      await pr(s, w, "interaction", { type: "cave", action: "info", request_id: "cave1" }, ["v:cave:R:Cave visit"], { timeoutMs: 3000 });
      await pr(s, w, "interaction", { type: "cave", action: "state" }, ["v:cave:F2"], { timeoutMs: 3000 });
      await pr(s, w, "interaction", { key: "A" }, ["v:Konami:F2"], NONE);
      await pr(s, w, "eval", { command: "hello" }, ["F2"]);
      await pr(s, w, "join", { name: "goobrawl" }, ["F6"]);
      await pr(s, mer, "join", { name: "goobrawl" }, ["F2"]);
      await pr(s, w, "enter", { place: "crypt" }, ["v:crypt:F1"]);
      await pr(s, w, "enter", { place: "duelland", name: "nosuchinstance" }, ["v:duelland:F1"]);
      await pr(s, w, "enter", { place: "dungeon0" }, ["v:dungeon0:F1"]);
      await pr(s, w, "enter", { place: "resort" }, ["v:Other:F1"]);
      await pr(s, w, "enter", { place: "dreams", name: "x" }, ["v:dreams:F1"], { timeoutMs: 3000 });
      await pr(s, w, "leave", undefined, ["F3"]);
      await pr(s, w, "tarot", undefined, ["F2"]);
      await pr(s, mer, "set_home", undefined, ["R:Success", "F2"]);
      // Paid with shells: the account has 600, so both fail later (no shells spent).
      await pr(s, mer, "bless_server", { request_id: "bl1" }, ["R:Started", "F3", "F4"], { until: (f) => responsesIn(f).some((x) => /bless/.test(codeOf(x))), timeoutMs: 8000 });
      await pr(s, mer, "bless_server", {}, ["R:Started", "F2", "F3"], { timeoutMs: 3000 });
      await pr(s, mer, "buy_with_cash", { name: "cosmo5", quantity: 1 }, ["R:Started", "F5"], { until: (f) => responsesIn(f).some((x) => /shell_purchase/.test(codeOf(x))), timeoutMs: 8000 });
      await pr(s, mer, "buy_with_cash", { name: "hpot0", quantity: 1 }, ["F2"]);
      await pr(s, mer, "buy_with_cash", { name: "nosuchitem", quantity: 1 }, ["F2"]);
      report(s);
    },
  },

  // 9. Duel between our warrior and our mage; the mage walks out to end it.
  duel: {
    what: "Duel: challenge, accept (both into duelland), enter failure, then the mage leaves with town.",
    chars: [W, P, M],
    run: async (s) => {
      const [w, p, m] = [ch(s, W), ch(s, P), ch(s, M)];
      await walk(s, m, w.me.x + 40, w.me.y, 80);
      await pr(s, w, "duel", { event: "challenge", name: "NoSuchCharacter9" }, ["v:challenge:F1"], { until: on("game_response", "game_log") });
      await pr(s, w, "duel", { event: "challenge", name: w.name, request_id: "dc0" }, ["v:challenge:F1"]);
      await pr(s, m, "duel", { event: "accept", name: w.name }, ["v:accept:F1"], { until: on("game_response", "game_log") });
      await pr(s, w, "duel", { event: "challenge", name: m.name, request_id: "dc1" }, ["v:challenge:R:Challenge sent", "v:challenge:A1", "v:challenge:A2"]);
      await pr(s, m, "duel", { event: "accept", name: w.name, request_id: "da1" }, ["v:accept:R:Accepted", "v:accept:R:Moved", "v:accept:A1", "v:accept:A2", "v:accept:A3", "v:accept:A4", "v:accept:A5"], { until: on("new_map"), timeoutMs: 4000, tailMs: 1500 });
      await pr(s, p, "duel", { event: "enter", id: "nosuchduel", request_id: "de1" }, ["v:enter:F3"]);
      await pr(s, w, "duel", { event: "challenge", name: p.name }, ["v:challenge:F2"], { until: on("game_response", "game_log") });
      // Wait for the start (60 s), then the mage teleports out: the duel ends.
      console.log("  waiting for the duel to start (60 s)...");
      await until(() => !(m.me.s as Record<string, unknown>)?.stunned, 70_000);
      await sleep(2000);
      await pr(s, m, "town", undefined, ["R:Channel", "R:Started", "R:Arrived"], { until: on("new_map"), timeoutMs: 8000, tailMs: 3000 });
      await until(() => w.me.map !== "duelland", 15_000);
      report(s);
    },
  },

  // 10. Jail: one move into a wall (a line violation), then `leave` (the only way out of jail).
  jail: {
    what: "Move into a wall (jail), leave jail; move with a wrong `m` (ignored).",
    chars: [W],
    run: async (s) => {
      const w = ch(s, W);
      await pr(s, w, "move", { x: w.me.x, y: w.me.y, going_x: w.me.x + 5, going_y: w.me.y, m: (w.me.m ?? 0) + 7 }, ["F3"], NONE);
      // A point that is not walkable, near us.
      const grid = Grid.forMap(s.G, w.me.map);
      let bad: [number, number] | null = null;
      for (let r = 40; r < 600 && !bad; r += 8) {
        for (let a = 0; a < 16 && !bad; a++) {
          const x = w.me.x + r * Math.cos((a * Math.PI) / 8);
          const y = w.me.y + r * Math.sin((a * Math.PI) / 8);
          if (!grid.safe(x, y)) bad = [Math.round(x), Math.round(y)];
        }
      }
      if (!bad) { console.log("no wall found"); return; }
      await pr(s, w, "move", { x: w.me.x, y: w.me.y, going_x: bad[0], going_y: bad[1], m: w.me.m }, ["F4"], { until: on("new_map"), timeoutMs: 3000, tailMs: 800 });
      if (w.me.map === "jail") {
        await pr(s, w, "leave", undefined, ["R:Moved", "R:Success", "A1", "A2"], { until: (f) => responsesIn(f).some((x) => (x as { place?: string })?.place === "leave"), timeoutMs: 4000 });
      }
      report(s);
    },
  },

  // 11. Harakiri once, on the level-7 merchant; respawn too early, then respawn.
  death: {
    what: "Harakiri on the merchant (once), respawn before 12 s (cant_respawn), then respawn.",
    chars: [MER],
    run: async (s) => {
      const mer = ch(s, MER);
      if (mer.me.rip) console.log("  merchant is dead already");
      else await pr(s, mer, "harakiri", undefined, ["R:Success", "A3"], { until: on("player"), timeoutMs: 2000, tailMs: 800 });
      await pr(s, mer, "harakiri", undefined, ["F1"], NONE);
      await pr(s, mer, "attack", { id: "1" }, ["F2"]);
      await pr(s, mer, "skill", { name: "charge" }, ["F2"]);
      await pr(s, mer, "town", undefined, ["F3"]);
      await pr(s, mer, "respawn", {}, ["F3"]);
      await sleep(12_500);
      await pr(s, mer, "respawn", {}, ["R:Moved", "R:Success", "A2", "A3"], { until: (f) => responsesIn(f).some((x) => (x as { place?: string })?.place === "respawn"), timeoutMs: 4000 });
      report(s);
    },
  },

  // 12. TARGETED (the owner's scope change, 2026-10-04: "You don't need to live confirm if the
  //     code is good enough"). Only the shapes whose `confirm` says `live_needed` and that a
  //     normal account can reach cheaply (python3 scripts/confirm-report.py lists them).
  targeted: {
    what: "Only live_needed shapes: ui/UiNpcSell (sell 1 potion), UiResale (Ponty, only if cheap), pets, merrit_info, cavalry, cave info/state, bless_server Result (fails later: 600 < 1,200 shells), open_chest Opened (short fight).",
    run: async (s) => {
      const [w, p, m, mer] = [ch(s, W), ch(s, P), ch(s, M), ch(s, MER)];
      report(s);
      // pets: `players` event with player.p.pets.
      await pr(s, mer, "pets", undefined, ["R:Success"], { until: on("players") });
      // Market patron, cavalry, cave visit/state.
      await pr(s, mer, "interaction", { type: "merrit_info" }, ["v:merrit_info:req", "v:merrit_info:R:Market patron"], { until: on("merrit_status"), timeoutMs: 4000 });
      await pr(s, w, "interaction", { type: "cavalry", request_id: "cv1" }, ["v:cavalry:R:Cavalry", "v:cavalry:F1"], { timeoutMs: 4000 });
      await pr(s, w, "interaction", { type: "cavalry" }, ["v:cavalry:R:Cavalry", "v:cavalry:F1"], { timeoutMs: 4000 });
      await pr(s, mer, "interaction", { type: "cave", action: "info", request_id: "cave1" }, ["v:cave:R:Cave visit"], { timeoutMs: 4000 });
      await pr(s, mer, "interaction", { type: "cave", action: "state", request_id: "cave2" }, ["v:cave:R:Cave state", "v:cave:F2"], { timeoutMs: 4000 });
      // bless_server: the account has 600 shells, the blessing costs 1,200: the payment fails
      // later (blessed_fail, then bless_result with request_id). Nothing is spent.
      if (Number((mer.me as unknown as { cash?: number }).cash ?? 0) < 1200) {
        await pr(s, mer, "bless_server", { request_id: "bl1" }, ["R:Started", "R:Result", "F3"], { until: (f) => responsesIn(f).some((x) => codeOf(x) === "bless_result"), timeoutMs: 10000, tailMs: 1000 });
        await pr(s, mer, "bless_server", {}, ["R:Started", "R:Result", "F3"], { until: (f) => responsesIn(f).some((x) => /blessed_fail|bless_result/.test(codeOf(x))), timeoutMs: 10000, tailMs: 1500 });
      } else console.log("  merchant has >= 1,200 shells: bless_server skipped (it would spend them)");
      // Sell one potion to the shop NPC (ui "Sale to an NPC", type UiNpcSell).
      if (mer.me.map === "main") {
        await toNpc(s, mer, "main", "basics");
        const pot = slot(mer, "hpot1") >= 0 ? slot(mer, "hpot1") : slot(mer, "mpot1");
        if (pot >= 0) await pr(s, mer, "sell", { num: pot, quantity: 1 }, ["R:Success", "A1", "A2"], { until: on("game_response"), tailMs: 800 });
        // Ponty: buy the cheapest listing only if it is cheap (ui "Secondhands", UiResale).
        await toNpc(s, mer, "main", "secondhands");
        const r = await pr(s, mer, "secondhands", {}, ["R:List"], { until: on("secondhands", "game_response") });
        const lists = r.frames.map((f) => f.data).filter(Array.isArray) as Record<string, unknown>[][];
        const items = lists.flat().filter((x) => x && typeof x === "object" && x.rid);
        const priced = items.map((x) => ({ rid: String(x.rid), name: String(x.name), price: Number(x.price ?? (s.G.items[String(x.name)]?.g ?? 0) * 2) }))
          .filter((x) => x.price > 0).sort((a, b) => a.price - b.price);
        console.log(`  Ponty has ${items.length} listings; cheapest: ${priced.slice(0, 3).map((x) => `${x.name} ~${x.price}`).join(", ")}`);
        // HARD-CODED cap: 3,000 gold, about a tenth of the merchant's gold.
        if (priced[0] && priced[0].price <= 3000 && gold(mer) > priced[0].price + 1000) {
          await pr(s, mer, "sbuy", { rid: priced[0].rid }, ["R:Success", "R:New list", "A1", "A2", "A3"], { until: on("game_response"), tailMs: 800 });
        } else console.log("  no Ponty listing under the cap: sbuy skipped");
      }
      // A short fight for real chests (open_chest Opened: `items` from a real drop).
      if (w.me.map === "desertland") await fight(s, [w, p, m], 50_000);
      for (const c of [w, p, m]) {
        for (const id of [...c.m.world.chests.keys()]) {
          await pr(s, c, "open_chest", { id }, ["R:Opened", "A1", "A2", "A3", "A5"], { until: on("chest_opened") });
          c.m.world.chests.delete(id);
        }
      }
      report(s);
    },
  },

  // Fight only (for reruns): the fighters fight for 60 s where they stand.
  fight: {
    what: "The three fighters fight where they stand for 150 s (FIGHT_MS), open chests.",
    chars: [W, P, M],
    run: async (s) => {
      await fight(s, [ch(s, W), ch(s, P), ch(s, M)], Number(process.env.FIGHT_MS) || 150_000);
      for (const c of s.chars.values()) {
        for (const id of [...c.m.world.chests.keys()]) {
          await pr(s, c, "open_chest", { id }, ["R:Opened", "A1", "A2", "A3"], { until: on("chest_opened") });
          c.m.world.chests.delete(id);
        }
      }
      report(s);
    },
  },
};

// A simple party fight: the warrior and the mage attack the monster nearest the warrior (only
// monsters that target nobody else or target us), the priest heals whoever is lowest. Potions
// keep everyone up. It stops after `ms`, or when a character dies (then respawn).
async function fight(s: Session, [w, p, m]: Char[], ms: number): Promise<void> {
  const end = Date.now() + ms;
  let target: string | null = null;
  while (Date.now() < end) {
    s.check();
    for (const c of [w, p, m]) {
      c.m.world.advance();
      if (c.me.rip) {
        console.log(`  ${c.name} died; respawning`);
        await c.m.act.respawn();
      }
      await topUp(c);
    }
    const mons = w.m.world.monsters;
    if (!target || !mons.has(target)) {
      const ours = new Set([w.name, p.name, m.name]);
      const free = [...mons.values()].filter((x) => !x.target || ours.has(String(x.target)));
      free.sort((a, b) => w.m.world.distance(w.me, a) - w.m.world.distance(w.me, b));
      target = free[0]?.id ?? null;
    }
    if (target) {
      const mon = mons.get(target)!;
      for (const c of [w, m]) {
        const d = c.m.world.distance(c.me, mon);
        if (d > c.me.range * 0.9) {
          void c.m.act.move(mon.x + (c === w ? 0 : 60), mon.y + (c === w ? 0 : 60));
        } else if (c.m.cooldowns.ready("attack")) {
          await c.m.act.attack(target);
        }
      }
    }
    // The priest heals the lowest of the party within range.
    const low = [w, p, m].sort((a, b) => a.me.hp / a.me.max_hp - b.me.hp / b.me.max_hp)[0];
    if (low.me.hp < low.me.max_hp * 0.8 && p.m.cooldowns.ready("attack")) {
      const d = p.m.world.distance(p.me, low.me);
      if (d > p.me.range * 0.9) void p.m.act.move(low.me.x, low.me.y + 20);
      else await p.m.act.request("heal", { id: low.name });
    }
    await sleep(250);
  }
}
