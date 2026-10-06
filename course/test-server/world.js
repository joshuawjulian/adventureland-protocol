// world.js: one game server (for example "EU I" at /ws1/). Each World has its
// own maps, monsters, characters, chests and parties, like one live server
// process (vendor/adventureland_mongodb/node/server.js).
//
// It is NOT the game. It copies the live payload shapes and rules for what the
// course uses, and each handler cites the live code that it copies, as
// node/server.js:LINE (treat line numbers as "within a few lines").
// Where it is simpler than live, a comment says so.

import crypto from "node:crypto";
import { message, itemMessage, killMessage } from "./messages.js";
import {
  boxDistance,
  simpleDistance,
  withinVision,
  crossesWall,
  damageMultiplier,
  itemProperties,
  itemValue,
  itemGrade,
  newItem,
  cacheItem,
  canStack,
  canEquipItem,
  CHARACTER_SLOTS,
} from "./g.js";
import { ACCOUNT } from "./accounts.js";

// Every time and duration here uses clock(), not clock(). clock() is the wall clock, and
// it can jump: in Docker on WSL2 it jumped by seconds during the course checks. A jump moved
// characters too far or too little and broke walks in the programs. clock() is milliseconds
// since the epoch, like clock(), but it is monotonic: performance.now() counts from the
// start of the process (performance.timeOrigin) and never goes back.
const clock = () => performance.timeOrigin + performance.now();

// The maps that exist on the test server. A door or `transport` to another map
// gets "cant_enter", as live does for a map without an instance
// (node/server.js:5912-5918). trim-g.js keeps the geometry of these maps.
export const MAPS = ["main", "bank", "jail", "woffice"];

// region constants
// node/server.js:200-240 (B): the distances and times that the rules below use.
const B = {
  vision: [700, 500], // the view box: +-700 px in x, +-500 px in y
  u_vision: 65, // move this far, and the server sends the new view (node/server.js:216)
  max_vision: 1000, // farther targets "disappear" for attack (node/server.js:218)
  dist: 400, // `send` range (node/server.js:219)
  sell_dist: 400, // NPC range for buy, sell, upgrade, compound (node/server.js:220)
  door_dist: 112, // door range (node/server.js:221)
  transporter_dist: 160, // transporter NPC range (node/server.js:223)
  start_map: "main",
  m_outgoing_gmult: 0.12, // chest gold from the damage the monster did (node/server.js:234)
};

// node/server.js:241-254 (CC): the extra call-cost of some events. Each event
// costs 1 more (node/server.js:4897).
const CC = {
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
// node/server.js:255-259: 200 call-cost in 4 s with a character; a socket
// without a character gets a quarter (node/server.js:4903-4905).
const CALL_LIMIT = 200;
const CALL_WINDOW_MS = 4000;
// node/server.js:4899: the cost multiplier of resend() for a few events.
const CALL_MODIFIER = { open_chest: 0.1, skill: 0.05, target: 0.5 };

// node/server.js:171-176 and 15993-15996: with no fighting character to
// watch, the observer view (and `welcome`) is main (0, -50); welcome adds 120
// to y (node/server.js:4987).
const OBSERVER = { map: "main", x: 0, y: -50 };

// The monster packs of main that this server spawns (G.maps.main.monsters).
// Live spawns every pack; four are enough for the course. The goos are the
// first target of every program.
const MONSTER_TYPES = ["goo", "bee", "crab", "snake"];
// The goo pack box of G is [-282, 702, 218, 872], but a straight line from
// (0, 0) reaches only the part with x from about -54 to 54: walls at x -128
// and x 80 (y 240-552) block the rest. The goos here spawn and wander only in
// that part of their G box, so that a program at (0, 0) can walk straight to
// any goo. (Live goos use the whole box.)
const SPAWN_BOX = { goo: [-50, 702, 50, 872] };

// How often the world moves entities and sends updates. Live runs its loops at
// about this rate; the exact value does not matter to the course.
const TICK_MS = 50;

// The delay of the bank "mount" (entering or leaving the bank). Live waits for a
// database transaction in sync_loop (node/server.js:16560-16640); unclear from
// the source how long. 300 ms shows the `in_progress` reply first.
const BANK_MOUNT_MS = 300;
// endregion constants

// A small seeded random generator (mulberry32), so that damage, drops and
// upgrade rolls are the same in each run after a reset.
function makeRng(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// randomStr (live ids of chests, projectiles): letters and digits.
function randomStr(n) {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  const bytes = crypto.randomBytes(n);
  let s = "";
  for (let i = 0; i < n; i++) s += chars[bytes[i] % chars.length];
  return s;
}

// node/server.js:1242-1287 (stat_to_attr): an item stat -> the character field.
const STAT_TO_ATTR = {
  str: "str", int: "int", dex: "dex", vit: "vit", for: "for", armor: "armor", resistance: "resistance",
  pnresistance: "pnresistance", firesistance: "firesistance", fzresistance: "fzresistance",
  phresistance: "phresistance", stresistance: "stresistance", incdmgamp: "incdmgamp", stun: "stun",
  blast: "blast", explosion: "explosion", evasion: "evasion", cuteness: "cuteness", bling: "bling",
  dreturn: "dreturn", reflection: "reflection", crit: "crit", critdamage: "critdamage", miss: "miss",
  avoidance: "avoidance", hp: "max_hp", mp: "max_mp", speed: "speed", lifesteal: "lifesteal",
  manasteal: "manasteal", apiercing: "apiercing", rpiercing: "rpiercing", output: "output",
  attack: "a_attack", mp_cost: "a_mp_cost", mp_reduction: "mp_reduction", xp: "xxp", luck: "xluck",
  gold: "xgold", range: "range", courage: "courage", mcourage: "mcourage", pcourage: "pcourage",
};

export class World {
  // ctx: { G, D, accounts, settings, stats, dropped, log }
  constructor(def, ctx) {
    this.key = def.key; // "EUI"
    this.region = def.region; // "EU"
    this.name = def.name; // "I"
    this.path = def.path; // "/ws1/"
    this.msgpackPath = def.msgpackPath; // listed as live does; not served here
    this.timeOffset = def.timeOffset; // S.schedule.time_offset of the region
    this.ctx = ctx;
    this.G = ctx.G;
    this.D = ctx.D;
    this.cur = null; // the socket and event that the server handles now (live: current_socket, ls_method)
    this.sockets = new Map();
    this.reset();
    this.timer = setInterval(() => this.tick(), TICK_MS);
  }

  get serverId() {
    return "SR_" + this.region + this.name; // node/server.js:462
  }

  // region world-state
  // Make the world new: maps, NPCs, monsters. POST /test/reset calls it after
  // it closes all sockets.
  reset() {
    this.rng = makeRng(0x5eed + this.key.length); // fixed seed per server
    this.instances = {};
    this.players = {}; // socket.id -> character
    this.observers = {}; // socket.id -> observer
    this.byName = {}; // name -> character (live: name_to_id)
    this.chests = {};
    this.parties = {}; // leader name -> [names]
    this.invitations = {}; // inviter name -> {invited id: 1}
    this.requests = {}; // requester name -> {asked id: 1}
    this.dcPlayers = new Set(); // real ids whose save still runs (live: dc_players)
    this.pending = []; // [time, fn]: timers that reset() clears
    this.totalMonsters = 0;
    this.totalMoves = 1;
    for (const map of MAPS) {
      this.instances[map] = { name: map, map, players: {}, monsters: {}, observers: {} };
      this.createNpcs(map);
    }
    for (const pack of this.G.maps.main.monsters || []) {
      if (!MONSTER_TYPES.includes(pack.type) || !pack.boundary) continue;
      for (let i = 0; i < (pack.count || 0); i++) this.newMonster("main", pack);
    }
  }

  // Run fn after ms (in the world tick). reset() drops what is pending.
  later(ms, fn) {
    this.pending.push([clock() + ms, fn]);
  }

  // node/server_functions.js:1784-1855 (create_npc) and 1942-1951: every NPC of
  // the map is an entity in instance.players, id "$" + its name. They stand
  // still here (live citizens walk around).
  createNpcs(map) {
    for (const def of this.G.maps[map].npcs || []) {
      const npc = this.G.npcs[def.id];
      if (!npc) continue;
      const pos = def.position || (def.positions && def.positions[0]);
      if (!pos) continue;
      const entity = {
        speed: npc.speed || 20,
        attack: npc.attack || 100,
        range: npc.range || 40,
        level: npc.level || 100,
        hp: npc.hp || 1200,
        max_hp: npc.hp || 1200,
        armor: 500,
        mp: 2000,
        xp: 0,
        pdps: 0,
        skin: npc.skin,
        name: npc.name,
        in: map,
        map,
        npc: def.id,
        is_player: true,
        is_npc: true,
        type: npc.class || "merchant",
        id: "$" + npc.name,
        cid: 0,
        s: {},
        c: {},
        q: {},
        m: 0,
        slots: {},
        cx: npc.cx || {},
        x: pos[0],
        y: pos[1],
        width: 26,
        height: 36,
      };
      if (npc.type === "fullstatic" && pos.length === 3) entity.direction = pos[2];
      this.instances[map].players[entity.id] = entity;
    }
  }

  // node/server.js:13410-13640 (new_monster), the fields the course reads.
  newMonster(map, pack) {
    const def = this.G.monsters[pack.type];
    const [x1, y1, x2, y2] = (map === "main" && SPAWN_BOX[pack.type]) || pack.boundary;
    const m = {
      id: String(++this.totalMonsters), // live ids are numbers as strings (node/server.js:13417)
      type: pack.type,
      is_monster: true,
      map,
      in: map,
      cid: 1,
      mult: 1,
      m: 0,
      level: 1,
      luckx: 1,
      outgoing: 0,
      s: {},
      last: { attacked: clock(), attack: 0 },
      pack,
      box: (map === "main" && SPAWN_BOX[pack.type]) || pack.boundary, // where it spawns and wanders
      points: {},
      x: x1 + this.rng() * (x2 - x1),
      y: y1 + this.rng() * (y2 - y1),
      moving: false,
      u: true,
      next_wander: clock() + 1000 + this.rng() * 4000,
    };
    for (const p of ["speed", "xp", "hp", "attack", "range", "frequency", "damage_type", "aggro", "evasion", "armor", "resistance", "apiercing", "rpiercing", "1hp", "projectile"]) {
      if (p in def) m[p] = def[p];
    }
    m.max_hp = m.hp;
    m.mp = Math.ceil((m.hp * 2) / 100); // node/server.js:13539
    m.gold = pack.gold; // usually undefined: then D.monster_gold is used
    m.going_x = m.x;
    m.going_y = m.y;
    this.instances[map].monsters[m.id] = m;
    return m;
  }
  // endregion world-state

  // region call-cost
  // node/server_functions.js:5336-5362 (add_call_cost). Each socket keeps
  // [time, method, cost] entries of the last 4 s. A new cost for the same method
  // as the last entry adds to that entry. num -1 is the base cost 1 of an event,
  // always as a new entry.
  addCallCost(socket, num, method) {
    if (!socket || !socket.calls) return;
    if (!num) num = 1;
    if (!method) method = (this.cur && this.cur.method) || "?";
    this.pruneCalls(socket);
    const last = socket.calls[socket.calls.length - 1];
    if (last && last[1] === method && num !== -1) last[2] += num;
    else {
      // [date, method, cost] is the live shape (limitdcreport sends it). The window uses
      // entry.t, a monotonic time, which JSON does not send (it is not an array index).
      const entry = [new Date(), method, num === -1 ? 1 : num];
      entry.t = clock();
      socket.calls.push(entry);
    }
  }

  // add_call_cost(num) with a number only charges current_socket: the socket
  // whose event runs now. Outside an event handler (timers) nothing is charged.
  chargeCurrent(num) {
    if (this.cur) this.addCallCost(this.cur.socket, num);
  }

  pruneCalls(socket) {
    const now = clock();
    while (socket.calls.length && now - socket.calls[0].t > CALL_WINDOW_MS) socket.calls.shift();
  }

  // node/server_functions.js:5388-5405 (get_call_cost)
  getCallCost(socket) {
    if (!socket || !socket.calls) return 0;
    this.pruneCalls(socket);
    let cost = 0;
    for (const c of socket.calls) cost += c[2];
    return cost;
  }

  // node/server.js:4882-4970: the live wrapper around each socket.on handler.
  // It charges the call-cost, kicks with "limitdc" over the limit, and turns an
  // exception into game_error "ERROR!".
  on(socket, method, handler) {
    const stats = this.ctx.stats;
    socket.on(method, (data) => {
      if (data === undefined) data = {}; // node/server.js:4893-4895
      socket.total_calls++;
      this.cur = { socket, method, modifier: CALL_MODIFIER[method] || 1 };
      let climit = CALL_LIMIT;
      try {
        this.addCallCost(socket, -1, method);
        if (!this.players[socket.id]) climit = Math.round(climit / 4);
        if (CC[method]) this.addCallCost(socket, CC[method], method);
        const cost = this.getCallCost(socket);
        stats.maxcc = Math.max(stats.maxcc, cost);
        if (cost > climit) {
          this.limitdc(socket, climit);
        } else {
          handler(data);
        }
      } catch (e) {
        // node/server.js:4943-4970
        console.log(`[${socket.id}] error in "${method}": ${e && e.stack ? e.stack.split("\n").slice(0, 3).join(" | ") : e}`);
        stats.errors++;
        this.addCallCost(socket, 16, method);
        if (this.getCallCost(socket) > climit) this.limitdc(socket, climit);
        else socket.emit("game_error", "ERROR!");
      } finally {
        this.cur = null;
      }
    });
  }

  // node/server.js:4935-4940: the call-cost kick.
  limitdc(socket, climit) {
    this.ctx.stats.limitdc++;
    console.log(`[${socket.id}] LIMITDC: call-cost ${this.getCallCost(socket)} > ${climit}`);
    socket.emit("limitdcreport", { calls: socket.calls, climit, total: socket.total_calls });
    socket.emit("disconnect_reason", "limitdc");
    socket.disconnect();
  }
  // endregion call-cost

  // region responses
  // node/server_functions.js:3393-3419 (fail_response): game_response with
  // {response, place, failed: true, ...data}. place defaults to the event name.
  fail(socket, response, place, data) {
    if (typeof data === "string") data = { reason: data };
    if (place && typeof place === "object") (data = place), (place = null);
    data = Object.assign({}, data || {});
    data.response = response || "data";
    data.place = place || (this.cur && this.cur.method);
    data.failed = true;
    socket.emit("game_response", data);
  }

  // node/server_functions.js:3421-3446 (success_response): {response, place,
  // success: true, ...data}; success stays false if data says false.
  success(socket, response, place, data) {
    if (response && typeof response === "object") (data = response), (response = "data"), (place = null);
    if (place && typeof place === "object") (data = place), (place = null);
    data = Object.assign({}, data || {});
    if (data.success !== false) data.success = true;
    data.response = response || "data";
    data.place = place || (this.cur && this.cur.method);
    socket.emit("game_response", data);
  }
  // endregion responses

  // region entities
  // node/server.js:855-1001 (player_to_client). `stranger` is the copy that
  // other players see (in `entities`); without it, the private copy for the
  // character itself (`start`, `player`).
  playerToClient(p, stranger) {
    const data = {};
    for (const k of [
      "hp", "max_hp", "mp", "max_mp", "xp", "attack", "heal", "frequency", "speed", "range", "armor",
      "resistance", "level", "party", "rip", "npc", "allow", "code", "afk", "target", "focus", "role", "s",
      "c", "q", "b", "age", "pdps", "id", "x", "y", "moving", "going_x", "going_y", "abs", "move_num",
      "position_id", "angle", "cid", "guild", "team",
    ]) {
      if (p[k] !== undefined) data[k] = p[k];
    }
    if (p.afk === "code") data.controller = p.controller;
    data.skin = p.skin;
    data.cx = p.cx;
    data.slots = p.is_npc ? undefined : this.cacheSlots(p);
    data.ctype = p.type;
    data.owner = p.owner || "";
    if (p.is_npc) {
      data.name = p.name;
      if (p.direction !== undefined) data.direction = p.direction;
    }
    // Note: live player_to_client has no `name` for characters, only `id`
    // (= the name). The browser copies id to name (js/game.js:6486).
    if (!stranger) {
      for (const k of [
        "int", "str", "dex", "vit", "for", "mp_cost", "mp_reduction", "max_xp", "goldm", "xpm", "luckm",
        "encouragement", "anniversary", "map", "in", "isize", "esize", "gold", "cash", "targets", "m",
        "evasion", "miss", "reflection", "lifesteal", "manasteal", "rpiercing", "apiercing", "crit",
        "critdamage", "dreturn", "tax", "xrange", "pnresistance", "firesistance", "fzresistance",
        "phresistance", "stresistance", "incdmgamp", "stun", "blast", "explosion", "courage", "mcourage",
        "pcourage", "fear",
      ]) {
        data[k] = p[k];
      }
      data.items = p.items.map(cacheItem); // null for an empty slot
      if (p.user) {
        data.user = JSON.parse(JSON.stringify(p.user)); // the bank, only while in the bank
      }
      if (p.socket) data.cc = this.getCallCost(p.socket); // node/server.js:996-998
    }
    return data;
  }

  cacheSlots(p) {
    const out = {};
    for (const k in p.slots) out[k] = cacheItem(p.slots[k]);
    return out;
  }

  // node/server.js:1003-1071 (monster_to_client): only the fields that differ
  // from G.monsters[type], plus position, movement and target.
  monsterToClient(m) {
    const def = this.G.monsters[m.type];
    const data = {};
    for (const p of ["speed", "hp", "mp", "max_mp", "attack", "xp", "frequency", "armor", "resistance", "1hp", "skin", "cooperative", "drops"]) {
      if (p in m && m[p] !== def[p]) data[p] = m[p];
    }
    if (m.max_hp !== def.hp) data.max_hp = m.max_hp;
    for (const p of ["id", "x", "y", "moving", "going_x", "going_y", "abs", "move_num", "angle", "type", "cid", "target", "focus", "s"]) {
      if (m[p] !== undefined && m[p] !== null) data[p] = m[p];
    }
    if (m.level > 1) data.level = m.level;
    return data;
  }

  entityToClient(e) {
    return e.is_monster ? this.monsterToClient(e) : this.playerToClient(e, true);
  }

  // node/server_functions.js:3675-3711 (send_all_xy): the full view, type "all".
  // Live includes the character itself in `players`. Ids that the client had
  // and that are not in the new view get `disappear` {id, outside: true} first.
  sendAllXy(o, raw) {
    const data = { players: [], monsters: [], type: "all", in: o.in, map: o.map };
    const inst = this.instances[o.in];
    const previous = o.seen || {};
    const seen = (o.seen = {});
    if (inst) {
      for (const id in inst.players) {
        const p = inst.players[id];
        if (!p.dead && withinVision(o, p)) {
          data.players.push(this.playerToClient(p, true));
          seen[p.id] = 1;
        }
      }
      for (const id in inst.monsters) {
        const m = inst.monsters[id];
        if (!m.dead && withinVision(o, m)) {
          data.monsters.push(this.monsterToClient(m));
          seen[m.id] = 1;
        }
      }
    }
    for (const id in previous) if (!seen[id] && id !== o.id) o.socket.emit("disappear", { id, outside: true });
    o.last_upush = [o.x, o.y];
    o.push = false;
    if (raw) return data;
    if (inst) o.socket.emit("entities", data);
    return data;
  }

  // The view of every character and observer of each instance, once a tick
  // (node/server.js:13671-13753, send_xy_updates): entities that changed (`u`),
  // and, after the viewer moved 65 px or arrived (`push`), the whole view
  // again. Entities that left the view get `disappear` {id, outside: true}.
  sendXyUpdates() {
    for (const map in this.instances) {
      const inst = this.instances[map];
      const changed = [];
      for (const id in inst.players) if (inst.players[id].u) changed.push(inst.players[id]);
      for (const id in inst.monsters) if (inst.monsters[id].u) changed.push(inst.monsters[id]);
      const viewers = [...Object.values(inst.players).filter((p) => !p.is_npc && p.socket), ...Object.values(inst.observers)];
      const json = new Map();
      for (const v of viewers) {
        const seen = v.seen || (v.seen = {});
        const players = [];
        const monsters = [];
        const marked = {};
        for (const e of changed) {
          if (e.id === v.id) continue;
          marked[e.id] = true;
          if (e.dead || !withinVision(v, e)) {
            if (seen[e.id]) {
              v.socket.emit("disappear", { id: e.id, outside: true });
              delete seen[e.id];
            }
            continue;
          }
          if (!json.has(e)) json.set(e, this.entityToClient(e));
          seen[e.id] = 1;
          (e.is_monster ? monsters : players).push(json.get(e));
        }
        if (v.push) {
          for (const e of [...Object.values(inst.monsters), ...Object.values(inst.players)]) {
            if (e.id === v.id || marked[e.id]) continue;
            if (e.dead || !withinVision(v, e)) {
              if (seen[e.id]) {
                v.socket.emit("disappear", { id: e.id, outside: true });
                delete seen[e.id];
              }
              continue;
            }
            seen[e.id] = 1;
            (e.is_monster ? monsters : players).push(this.entityToClient(e));
          }
          v.push = false;
          v.last_upush = [v.x, v.y];
        }
        if (players.length || monsters.length) {
          v.socket.emit("entities", { players, monsters, type: "xy", in: v.in, map: v.map });
        }
      }
      for (const e of changed) e.u = false;
    }
  }

  // node/server_functions.js:3744-3790 (xy_emit): send an event to every
  // character and observer that sees `entity`, and always to the id `must`.
  xyEmit(entity, event, data, must) {
    const inst = this.instances[entity.in];
    if (!inst) return;
    for (const id in inst.players) {
      const p = inst.players[id];
      if (p.is_npc || !p.socket) continue;
      if (withinVision(p, entity) || p.id === must) p.socket.emit(event, data);
    }
    for (const id in inst.observers) {
      const o = inst.observers[id];
      if (withinVision(o, entity)) o.socket.emit(event, data);
    }
  }

  // node/server_functions.js:3834-3868 (remove_entity_emit): tell every client
  // that had the entity (or sees it now) that it is gone.
  removeEntityEmit(entity, event, data) {
    for (const table of [this.players, this.observers]) {
      for (const key in table) {
        const o = table[key];
        if (!o || !o.socket) continue;
        const knew = o.seen && o.seen[entity.id];
        if (knew) delete o.seen[entity.id];
        if (!knew && (o.in !== entity.in || !withinVision(o, entity))) continue;
        o.socket.emit(event, data);
      }
    }
  }
  // endregion entities

  // region stats
  // node/server.js:1301-1769 (calculate_player_stats), the parts that change
  // the course's numbers: class and level stats, item stats (with upgrade
  // levels), sets, then the formulas for hp, mp, armor, speed, attack and
  // frequency. Simpler than live: no conditions, titles, monster-hunt or party
  // bonuses, no fear.
  calcStats(p) {
    const G = this.G;
    p.max_xp = G.levels[String(p.level)];
    let levelUp = false;
    while (p.max_xp && p.xp >= p.max_xp) {
      levelUp = true;
      p.xp -= p.max_xp;
      p.level++;
      p.max_xp = G.levels[String(p.level)];
      p.hp = 0; // a level up refills hp and mp below (node/server.js:1314, 1649-1652)
    }
    if (levelUp) {
      this.ctx.stats.levelups++;
      this.xyEmit(p, "ui", { type: "level_up", name: p.name }); // node/server.js:1343
    }
    const cls = G.classes[p.type] || G.classes.merchant;
    p.range = cls.range;
    p.max_hp = cls.hp;
    p.max_mp = cls.mp;
    for (const k of ["a_mp_cost", "a_attack", "lifesteal", "manasteal", "incdmgamp", "mp_reduction", "stun", "blast", "explosion", "cuteness", "bling"]) p[k] = 0;
    for (const k of ["speed", "attack", "frequency", "mp_cost", "armor", "resistance", "apiercing", "rpiercing", "evasion", "miss", "reflection", "crit", "critdamage", "dreturn", "xxp", "xluck", "xgold", "output", "courage", "mcourage", "pcourage", "pnresistance", "firesistance", "fzresistance", "phresistance", "stresistance"]) {
      p[k] = cls[k] || 0;
    }
    for (const stat in cls.stats) {
      let v = cls.stats[stat] + p.level * cls.lstats[stat];
      if (p.level > 40) v += (p.level - 40) * cls.lstats[stat];
      if (p.level > 55) v += (p.level - 55) * cls.lstats[stat];
      if (p.level > 65) v += (p.level - 65) * cls.lstats[stat];
      if (p.level > 80) v -= (p.level - 80) * cls.lstats[stat];
      p[stat] = Math.floor(v);
    }
    p.isize = 42; // node/server.js:1456
    p.esize = p.isize - p.items.length;
    for (const it of p.items) if (!it) p.esize++;
    p.xpm = p.goldm = p.luckm = 1;
    let itemAttack = 0;
    const sets = {};
    for (const slot of CHARACTER_SLOTS) {
      const it = p.slots[slot];
      if (!it || !G.items[it.name]) continue;
      const def = G.items[it.name];
      const prop = itemProperties(it, G);
      if (def.class && !def.class.includes(p.type)) continue;
      this.applyStats(p, prop, { no_range: slot === "offhand" && def.type === "weapon" });
      if (prop.attack) itemAttack += slot === "offhand" ? prop.attack * 0.7 : prop.attack;
      if (slot === "mainhand") this.applyStats(p, cls.doublehand[def.wtype] || cls.mainhand[def.wtype] || {});
      if (slot === "offhand") this.applyStats(p, cls.offhand[def.wtype] || cls.offhand[def.type] || {});
      if (def.set) sets[def.set] = (sets[def.set] || 0) + 1;
    }
    for (const set in sets) {
      const prop = G.sets[set] && G.sets[set][sets[set]];
      if (prop) this.applyStats(p, prop);
    }
    itemAttack = Math.max(itemAttack, 5);
    // node/server_functions.js:1745-1752 (weapon_stat_attack)
    const mainStat = p.type === "paladin" ? p.str / 20 + p.int / 40 : p[cls.main_stat] / 20;
    p.attack += itemAttack * mainStat;
    p.attack += p.a_attack;
    if (p.type === "priest") p.attack *= 1.6;
    if (p.type === "warrior") p.courage += Math.round(p.str / 30);
    if (p.type === "priest") p.mcourage += Math.round(p.int / 30);
    p.speed +=
      Math.min(p.dex, 256) / 32 +
      Math.min(p.str, 256) / 64 +
      Math.min(p.level, 40) / 10 +
      Math.max(0, Math.min(p.level - 40, 20)) / 15 +
      Math.max(0, Math.min(86, p.level) - 60) / 16;
    p.max_hp += p.str * 21 + p.vit * (48 + p.level / 3);
    p.max_hp = Math.max(1, p.max_hp);
    p.max_mp = Math.max(1, p.max_mp);
    p.max_mp += p.int * 15 + p.level * 5;
    p.armor += Math.min(p.str, 160) + Math.max(0, p.str - 160) * 0.25;
    p.resistance += Math.min(p.int, 180) + Math.max(0, p.int - 180) * 0.25;
    p.frequency += Math.min(p.level, 80) / 164 + Math.min(160, p.dex) / 640 + Math.max(p.dex - 160, 0) / 925 + p.int / 1575;
    p.attack_ms = Math.round(1000 / p.frequency);
    p.mp_cost += Math.min(p.level, 80) * (p.mp_cost / 10) + p.a_mp_cost + p.crit * 1.25 + p.lifesteal * 1.5 + p.manasteal / 5;
    p.mp_cost = Math.max(1, p.mp_cost);
    if (!p.hp && !p.rip) {
      p.hp = p.max_hp;
      p.mp = p.max_mp;
    }
    if ((p.gold || 0) <= 0) p.gold = 0;
    p.heal = p.type === "priest" ? p.attack : 0;
    p.output = Math.max(5, p.output);
    p.attack = (p.attack * p.output) / 100;
    for (const k of ["attack", "heal", "hp", "mp", "max_hp", "max_mp", "range", "mp_cost", "resistance", "armor"]) p[k] = Math.round(p[k]);
    p.hp = Math.max(0, Math.min(p.hp, p.max_hp));
    p.mp = Math.max(0, Math.min(p.mp, p.max_mp));
    if (p.party && this.parties[p.party]) p.xxp += p.party_xp || 0;
    p.luckm = Math.max(0.01, 1 + p.xluck / 100);
    p.xpm = Math.max(0.01, 1 + p.xxp / 100);
    p.goldm = Math.max(0.01, 1 + p.xgold / 100);
    p.tax = p.level > 80 ? 0.01 : p.level > 70 ? 0.02 : p.level > 60 ? 0.025 : p.level > 50 ? 0.03 : p.level > 20 ? 0.04 : 0.05;
    p.fear = 0;
    p.speed = Math.max(1, p.speed);
  }

  // node/server.js:1288-1299 (apply_stats)
  applyStats(p, prop, args) {
    for (const stat in prop) {
      if (args && args.no_range && stat === "range") continue;
      if (typeof prop[stat] !== "number") continue;
      if (STAT_TO_ATTR[stat]) p[STAT_TO_ATTR[stat]] = (p[STAT_TO_ATTR[stat]] || 0) + prop[stat];
      else if (stat === "frequency") p.frequency += prop[stat] / 100;
    }
  }

  // node/server.js:4550-4592 (resend): send the private `player` update.
  // "u" and a missing "nc" each add a call-cost to the socket whose event runs
  // now (not always this character's socket). "nc" skips the stats.
  // "reopen" asks the client to redraw the inventory.
  resend(p, events) {
    if (!p || p.is_npc || !p.socket) return;
    const list = (events || "").split("+");
    const mod = (this.cur && this.cur.modifier) || 1;
    if (list.includes("u")) {
      this.chargeCurrent(mod);
      p.u = true;
    }
    if (list.includes("cid")) p.cid++;
    if (!list.includes("nc")) {
      this.chargeCurrent(mod);
      this.calcStats(p);
    }
    const data = this.playerToClient(p);
    if (p.hitchhikers.length) {
      data.hitchhikers = p.hitchhikers; // [event, payload] pairs that ride on this update
      p.hitchhikers = [];
    }
    if (list.includes("reopen")) {
      if (this.cur && this.cur.socket !== p.socket) this.chargeCurrent(mod * 4);
      data.reopen = true;
    }
    p.socket.emit("player", data);
  }
  // endregion stats

  // region inventory
  // node/server.js:2015-2087 (add_item): stack, else the first empty slot, else
  // a new slot at the end. Returns the slot number.
  addItem(p, item) {
    if (!item.name) item = newItem(item, 1, this.G);
    if (!item.oo) item.oo = p.name;
    if (this.G.items[item.name].s) {
      for (let i = 0; i < p.items.length; i++) {
        if (canStack(p.items[i], item, this.G)) {
          p.items[i].q = (item.q || 1) + (p.items[i].q || 1);
          return i;
        }
      }
    }
    for (let i = 0; i < p.items.length; i++) {
      if (!p.items[i]) {
        p.items[i] = item;
        p.esize--;
        return i;
      }
    }
    p.items.push(item);
    p.esize--;
    return p.items.length - 1;
  }

  // js/old_common_functions.js:422-444 (can_add_item)
  canAddItem(p, item) {
    if (p.esize > 0) return true;
    if (this.G.items[item.name].s) return p.items.some((it) => canStack(it, item, this.G));
    return false;
  }

  // js/old_common_functions.js:446-467 (can_add_items)
  canAddItems(p, items) {
    let needed = items.length;
    if (p.esize >= needed || !needed) return true;
    const overhead = [];
    for (const it of items) {
      if (!this.G.items[it.name].s) continue;
      for (let i = 0; i < p.items.length; i++) {
        if (canStack(p.items[i], it, this.G, overhead[i] || 0)) {
          overhead[i] = (overhead[i] || 0) + (it.q || 1);
          needed--;
        }
      }
    }
    return p.esize >= needed;
  }

  // node/server.js:1953-1969 (consume, consume_one)
  consume(p, num, quantity = 1) {
    const available = p.items[num].q || 1;
    if (available === quantity) {
      p.items[num] = null;
      p.esize++;
    } else {
      p.items[num].q -= quantity;
    }
  }
  // endregion inventory

  // region connection
  // node/server.js:4860-5054: a new socket. `welcome` at once; `loaded` makes
  // it an observer; `auth` makes it a character.
  connect(socket) {
    const ctx = this.ctx;
    ctx.stats.connections++;
    this.sockets.set(socket.id, socket);
    socket.total_calls = 0;
    socket.calls = [];
    if (!ctx.settings.quiet) {
      socket.onAny((event, ...args) => {
        const payload = typeof args[0] === "function" ? undefined : args[0];
        console.log(`[${socket.id}] <- ${event} ${payload === undefined ? "" : JSON.stringify(payload)}`);
      });
    }
    // The browser adds map_protocol=1 (js/game.js:1525); live uses it for the
    // generated (cave) maps only. We only warn.
    if (socket.handshake.query.map_protocol !== "1") console.log(`[${socket.id}] note: the URL has no map_protocol=1`);

    socket.first = { map: OBSERVER.map, in: OBSERVER.map, x: OBSERVER.x, y: OBSERVER.y + 120 };
    // node/server.js:4972-5015: welcome. S is the server event state (E);
    // on a normal server it has `schedule` (node/server.js:203-210).
    socket.emit("welcome", {
      region: this.region,
      name: this.name,
      pvp: false,
      gameplay: "normal",
      info: {},
      version: this.G.version,
      x: socket.first.x,
      y: socket.first.y,
      map: socket.first.map,
      in: socket.first.in,
      S: { schedule: { time_offset: this.timeOffset, dailies: [13, 20], nightlies: [23], night: false } },
    });

    const on = (name, f) => this.on(socket, name, f);

    // node/server.js:5020-5027 (CC 12)
    on("send_updates", () => {
      ctx.stats.updates++;
      if (this.observers[socket.id]) this.sendAllXy(this.observers[socket.id]);
      if (this.players[socket.id]) this.sendAllXy(this.players[socket.id]);
    });

    // node/server.js:5028-5054: the client is ready; it becomes an observer of
    // the welcome position and gets the full view.
    on("loaded", () => {
      if (!socket.connected || this.players[socket.id] || this.observers[socket.id]) return;
      const o = {
        socket,
        x: socket.first.x,
        y: socket.first.y,
        map: socket.first.map,
        in: socket.first.in,
        observer: 1,
        id: "o" + socket.id,
        s: {},
        vision: B.vision,
      };
      this.observers[socket.id] = o;
      this.instances[o.in].observers[o.id] = o;
      this.sendAllXy(o);
    });

    // node/server.js:5126-5128
    on("ping_trig", (data) => socket.emit("ping_ack", data));

    on("auth", (data) => this.onAuth(socket, data));
    on("move", (data) => this.onMove(socket, data));
    // node/server.js:11003-11005: attack is the "attack" skill.
    on("attack", (data) => this.onAttack(socket, data));
    on("use", (data) => this.onUse(socket, data));
    on("equip", (data) => this.onEquip(socket, data));
    on("unequip", (data) => this.onUnequip(socket, data));
    on("open_chest", (data) => this.onOpenChest(socket, data));
    on("respawn", (data) => this.onRespawn(socket, data));
    on("buy", (data) => this.onBuy(socket, data));
    on("sell", (data) => this.onSell(socket, data));
    on("transport", (data) => this.onTransport(socket, data));
    on("leave", (data) => this.onLeave(socket, data));
    on("party", (data) => this.onParty(socket, data));
    on("send", (data) => this.onSend(socket, data));
    on("upgrade", (data) => this.onUpgrade(socket, data));
    on("compound", (data) => this.onCompound(socket, data));
    on("bank", (data) => this.onBank(socket, data));

    socket.on("disconnect", (reason) => this.onDisconnect(socket, reason));
  }

  // node/server.js:11563-11986 (auth). The live checks run in this order.
  onAuth(socket, data) {
    const ctx = this.ctx;
    // Non-string fields: the event is ignored, with no reply (node/server.js:11564-11571).
    if (!data || typeof data !== "object" || typeof data.user !== "string" || typeof data.character !== "string" || typeof data.auth !== "string") return;
    ctx.stats.auths++;
    // node/server.js:11572-11573 (normalize_user_id, adventure_functions.js:366-369):
    // "tester" -> "US_tester"; "tester" -> "CH_tester".
    if (data.user && !data.user.startsWith("US_")) data.user = "US_" + data.user;
    if (data.character && !data.character.startsWith("CH_")) data.character = "CH_" + data.character;
    // node/server.js:11577-11582: the character is still saving after a
    // disconnect (dc_players), or it is online on this server.
    if (this.dcPlayers.has(data.character) || Object.values(this.players).some((p) => p.real_id === data.character)) {
      ctx.stats.auth_in_progress++;
      return socket.emit("game_log", message("server.game_log.authorization_in_progress"));
    }
    // node/server.js:11583-11585: auth before `loaded` (no observer yet) is ignored.
    if (!this.observers[socket.id] || this.players[socket.id]) return;
    // node/server.js:11608-11619 (the database transaction):
    const record = ctx.accounts.get(data.character);
    let reason = null;
    if (!record) reason = "no_character";
    else if (data.user !== ctx.accounts.user.id || !ctx.accounts.user.auths.includes(data.auth)) reason = "password_issue";
    else if (record.server) reason = "ingame"; // online (or saving) on the other server
    if (reason) {
      ctx.stats.auth_failed++;
      // node/server.js:11639-11651
      socket.emit("game_error", message("server.game_error.authentication_failed", { reason }, { reason }));
      return;
    }
    record.server = this.serverId;
    record.online = true;
    record.last_online = new Date();

    const p = this.makePlayer(socket, record, data);
    // node/server.js:11884-11892: the observer goes, the character comes.
    this.deleteObserver(socket);
    this.players[socket.id] = p;
    this.byName[p.name] = p;
    this.instances[p.in].players[p.id] = p;
    this.calcStats(p);
    if (record.hp === null) {
      p.hp = Math.round(p.max_hp * record.hpRatio);
      p.mp = p.max_mp;
    }
    // node/server.js:11919-11944: the private character, plus a few login
    // fields, plus the full view as `entities`.
    const cdata = this.playerToClient(p);
    cdata.ipass = randomStr(12);
    cdata.home = undefined;
    cdata.friends = [];
    cdata.acx = {};
    cdata.xcx = [];
    cdata.info = {};
    cdata.base_gold = {};
    cdata.s_info = { schedule: { time_offset: this.timeOffset, dailies: [13, 20], nightlies: [23], night: false } };
    cdata.entities = this.sendAllXy(p, true);
    ctx.stats.starts++;
    socket.emit("start", cdata);
    console.log(`[${socket.id}] ${p.name} entered ${this.region} ${this.name} on ${p.map} at ${Math.round(p.x)},${Math.round(p.y)}`);

    // POST /test/drop and /test/jail with after_start_ms: armed for this name.
    this.runArmed(p.name);

    // TEST_DROP_AFTER_MS: drop each character once, to test the reconnect rule.
    if (ctx.settings.dropAfterMs && !ctx.dropped.has(p.name)) {
      ctx.dropped.add(p.name);
      this.later(ctx.settings.dropAfterMs, () => {
        if (socket.connected) {
          console.log(`[${socket.id}] TEST_DROP_AFTER_MS: dropping ${p.name}`);
          ctx.stats.drops++;
          socket.disconnect(true);
        }
      });
    }
  }

  // Build the live player object from the database record
  // (node/server.js:11697-11815, init_player).
  makePlayer(socket, record, data) {
    const now = clock();
    const p = {
      socket,
      is_player: true,
      id: record.name, // live: the id of a character is its name (node/server.js:11720)
      name: record.name,
      real_id: record.id,
      owner: data.user,
      type: record.type,
      level: record.level,
      xp: record.xp,
      gold: record.gold,
      items: JSON.parse(JSON.stringify(record.items)),
      slots: JSON.parse(JSON.stringify(record.slots)),
      skin: record.skin,
      cx: record.cx,
      map: record.map,
      in: record.map,
      x: record.x,
      y: record.y,
      hp: record.hp,
      mp: record.mp,
      rip: record.rip || false,
      rip_time: record.rip_time,
      p: JSON.parse(JSON.stringify(record.p)),
      s: {},
      c: {},
      q: {},
      m: 0, // the map number: +1 on each map change (node/server.js:11791)
      cid: 1,
      moving: false,
      going_x: record.x,
      going_y: record.y,
      width: 26, // node/server.js:11782-11783
      height: 36,
      xrange: 25, // extra range (node/server.js:11785)
      vision: B.vision,
      targets: 0,
      pdps: 0,
      share: 0.1,
      party: undefined,
      hitchhikers: [],
      last: { attack: now - 10000, transport: now - 10000 }, // node/server.js:11922-11923
      afk: data.no_html ? "code" : true, // node/server.js:11760-11771
      controller: "",
      age: Math.max(1, Math.ceil((now - record.created.getTime()) / 86400000)),
      seen: {},
      last_upush: [record.x, record.y],
      u: true,
    };
    // node/server.js:11738-11750: a character saved on a map without an
    // instance, or in the bank (a "mount" map), comes back at on_exit.
    if (!this.instances[p.map] || this.G.maps[p.map].mount) {
      const place = (this.G.maps[p.map] && this.G.maps[p.map].on_exit) || this.G.maps.main.on_exit || ["main", 0];
      p.map = p.in = place[0];
      p.x = this.G.maps[p.map].spawns[place[1]][0];
      p.y = this.G.maps[p.map].spawns[place[1]][1];
      p.going_x = p.x;
      p.going_y = p.y;
    }
    p.p.ugrace = p.p.ugrace || {};
    p.p.ograce = p.p.ograce || 0;
    return p;
  }

  deleteObserver(socket) {
    const o = this.observers[socket.id];
    delete this.observers[socket.id];
    if (o && this.instances[o.in]) delete this.instances[o.in].observers[o.id];
  }

  // node/server.js:13044-13149 (disconnect)
  onDisconnect(socket, reason) {
    this.sockets.delete(socket.id);
    const p = this.players[socket.id];
    if (p && !p.dc) {
      p.dc = true;
      console.log(`[${socket.id}] ${p.name} disconnected: ${reason}`);
      // A move in progress ends at its target (node/server.js:13069-13074).
      if (p.moving && simpleDistance(p, { x: p.going_x, y: p.going_y }) < 800) {
        p.x = p.going_x;
        p.y = p.going_y;
      }
      if (p.party) this.leaveParty(p.party, p);
      this.removeEntityEmit(p, "disappear", { id: p.id, reason: "disconnect" });
      for (const m of Object.values(this.instances[p.in].monsters)) if (m.target === p.name) this.stopPursuit(m);
      delete this.players[socket.id];
      delete this.byName[p.name];
      delete this.instances[p.in].players[p.id];
      // node/server.js:13128-13134: the character waits in dc_players until its
      // save ends. TEST_SAVE_MS is that time.
      const save = () => {
        this.saveRecord(p);
        this.dcPlayers.delete(p.real_id);
      };
      const ms = this.ctx.settings.saveMs;
      if (ms > 0) {
        this.dcPlayers.add(p.real_id);
        this.later(ms, save);
      } else {
        save();
      }
    } else if (!this.ctx.settings.quiet) {
      console.log(`[${socket.id}] disconnected: ${reason}`);
    }
    this.deleteObserver(socket);
  }

  // Write the character back to the account and mark it offline.
  saveRecord(p) {
    const r = this.ctx.accounts.get(p.real_id);
    if (!r || r.server !== this.serverId) return; // a /test/reset happened meanwhile
    // An upgrade or compound in progress: the item comes back (live keeps the
    // placeholder and finishes later; simpler here).
    for (let i = 0; i < p.items.length; i++) {
      if (p.items[i] && p.items[i].name === "placeholder") p.items[i] = null;
    }
    Object.assign(r, {
      level: p.level,
      xp: p.xp,
      gold: p.gold,
      items: JSON.parse(JSON.stringify(p.items)),
      slots: JSON.parse(JSON.stringify(p.slots)),
      map: p.map,
      in: p.in,
      x: p.x,
      y: p.y,
      hp: p.hp,
      mp: p.mp,
      rip: p.rip,
      rip_time: p.rip_time,
      p: JSON.parse(JSON.stringify(p.p)),
      server: "",
      online: false,
    });
    if (p.user) Object.assign(this.ctx.accounts.user.bank, JSON.parse(JSON.stringify(p.user)));
  }
  // endregion connection

  // region movement
  // node/server.js:11183-11271 (move). The move is accepted if `m` is the
  // current map number, the character can walk (not dead), and the target is
  // not the current position. The server keeps its own x/y; when the client's
  // x/y is more than 132 px off, it sends `correction` with the server's.
  onMove(socket, data) {
    const p = this.players[socket.id];
    const x = parseFloat(data.going_x) || 0;
    const y = parseFloat(data.going_y) || 0;
    // `==`, as live: "0" and 0 are the same map number.
    if (!(p && p.m == data.m && !p.rip && (x !== p.x || y !== p.y))) return;
    this.ctx.stats.moves++;
    const cx = parseFloat(data.x) || 0;
    const cy = parseFloat(data.y) || 0;
    // The wall rule of the test server: the straight segment from the
    // client's position (or the server's, if the client is more than 132 px
    // off) to the target must not cross a line of G.geometry. If it does, the
    // character goes to jail, with the live messages of a line violation
    // (node/server.js:11215-11245). Live checks the start and target cells of
    // a precomputed walk map (smap_data) instead; see the report.
    const off = simpleDistance(p, { x: cx, y: cy }) > 132;
    const from = off ? { x: p.x, y: p.y } : { x: cx, y: cy };
    if (crossesWall(this.G.geometry[p.map], from.x, from.y, x, y)) {
      this.ctx.stats.violations++;
      console.log(`[${socket.id}] VIOLATION: ${p.name} moves through a wall on ${p.map}: ${Math.round(from.x)},${Math.round(from.y)} -> ${Math.round(x)},${Math.round(y)}`);
      this.lineViolation(p);
      return;
    }
    p.going_x = x;
    p.going_y = y;
    this.startMoving(p);
    if (off) socket.emit("correction", { x: p.x, y: p.y }); // node/server.js:11249-11257
  }

  // node/server.js:11234-11245: the messages of a line violation, then
  // defeat_player (node/server.js:4499-4531: a violation counter; a kill only
  // with a PvP `block` condition, which the test server never sets) and jail.
  lineViolation(p) {
    p.socket.emit("game_log", message("server.game_log.line_violation_detected"));
    p.socket.emit("game_log", message("server.game_log.make_sure_you_only_move_with_the_built_in_move_function"));
    p.violations = (p.violations || 0) + 1;
    this.ctx.stats.jails++;
    this.transportPlayerTo(p, "jail");
  }

  // node/server.js:13659-13669 (start_moving_element)
  startMoving(e) {
    e.moving = true;
    e.abs = false;
    e.u = true;
    e.from_x = e.x;
    e.from_y = e.y;
    e.move_num = this.totalMoves++;
  }

  // Move an entity toward going_x/going_y at its speed for dt seconds.
  // Returns true when it arrives.
  step(e, dt) {
    if (!e.moving) return false;
    const dx = e.going_x - e.x;
    const dy = e.going_y - e.y;
    const d = Math.hypot(dx, dy);
    const s = e.speed * dt;
    if (s >= d || d === 0) {
      e.x = e.going_x;
      e.y = e.going_y;
      e.moving = false;
      return true;
    }
    e.x += (dx / d) * s;
    e.y += (dy / d) * s;
    return false;
  }

  // node/server.js:4640-4757 (transport_player_to): to another map (or another
  // spawn of the same map). Sends `disappear` to the others, `new_map` with
  // the new full view to the character, then a `player` update.
  transportPlayerTo(p, name, point, effect) {
    if (!this.instances[name]) name = "main";
    const inst = this.instances[name];
    const newMap = this.G.maps[inst.map];
    const data = { id: p.id, reason: "transport", to: name, s: point };
    if (effect) data.effect = effect;
    this.removeEntityEmit(p, "disappear", data);
    for (const m of Object.values(this.instances[p.in].monsters)) if (m.target === p.name) this.stopPursuit(m);
    delete this.instances[p.in].players[p.id];
    p.map = inst.map;
    p.in = name;
    inst.players[p.id] = p;
    p.m++;
    let direction = 0;
    let scatter = 0;
    if (Array.isArray(point)) {
      [p.x, p.y] = point;
      direction = point[2] || 0;
      scatter = point[3] || 0;
    } else {
      if (!newMap.spawns[point || 0]) point = 0;
      const sp = newMap.spawns[point || 0];
      p.x = sp[0];
      p.y = sp[1];
      direction = sp[2] || 0;
      scatter = sp[3] || 0;
    }
    if (scatter) {
      p.x += this.rng() * scatter - scatter / 2;
      p.y += this.rng() * scatter - scatter / 2;
    }
    p.moving = false;
    p.going_x = p.x;
    p.going_y = p.y;
    p.u = true;
    p.cid++;
    this.calcStats(p);
    this.addCallCost(p.socket, 8, "transport"); // node/server.js:4726
    // node/server.js:4738-4743: a map change adds to the skill penalty
    // (penalty_cd): 812 ms with an effect (respawn, magiport), else 3200 ms.
    const pen = (p.s.penalty_cd && p.s.penalty_cd.ms) || 0;
    p.s.penalty_cd = { ms: Math.min(pen + (effect ? 812 : 3200), 120000) };
    this.ctx.stats.transports++;
    p.socket.emit("new_map", {
      name: inst.map,
      in: name,
      x: p.x,
      y: p.y,
      direction,
      effect: effect || 0,
      info: {},
      m: p.m,
      entities: this.sendAllXy(p, true),
      // Live also sends `eval: EV`, but EV is always undefined there
      // (node/server.js:4727-4737 is switched off), so the key is not in the JSON.
    });
    p.last.transport = clock();
    this.resend(p, "u+cid");
  }
  // endregion movement

  // region combat
  // node/server.js:9764-10996 (skill), the "attack" part, in the live order of
  // checks: dead, cooldown, safe map, target, range; then commence_attack
  // (node/server.js:3159-3612) sends `action`, skill_timeout, `player`, and the
  // game_response with the projectile data. The `hit` follows after `eta` ms.
  onAttack(socket, data) {
    const p = this.players[socket.id];
    if (!p) return;
    const G = this.G;
    const stats = this.ctx.stats;
    stats.attacks++;
    const place = "attack";
    if (p.rip) return this.fail(socket, "disabled", place);
    const now = clock();
    const cooldown = p.attack_ms; // G.skills.attack.cooldown = player.attack_ms (node/server.js:9778)
    if (cooldown && p.last.attack && now - p.last.attack < cooldown) {
      stats.cooldown++;
      return this.fail(socket, "cooldown", place, { skill: "attack", id: data.id, ms: cooldown - (now - p.last.attack) });
    }
    if (G.maps[p.map].safe) return this.fail(socket, "skill_cant_safe", place);
    if (data.id === undefined || data.id === null) return this.fail(socket, "no_target", place);
    const isMonster = String(parseInt(data.id)) === String(data.id);
    let target;
    if (!isMonster && this.byName[data.id] && this.byName[data.id].in === p.in) {
      target = this.byName[data.id];
      if (target.name === p.name) return this.fail(socket, "no_target", place);
    } else if (isMonster && this.instances[p.in].monsters[data.id]) {
      target = this.instances[p.in].monsters[data.id];
    } else {
      stats.not_there++;
      return socket.emit("disappear", { id: data.id, place, reason: "not_there" });
    }
    if (boxDistance(target, p, G) > B.max_vision) {
      stats.not_there++;
      return socket.emit("disappear", { id: data.id, place, reason: "not_there" });
    }
    // Range (node/server.js:9999-10031): range + xrange (25). Using a part of
    // xrange uses it up.
    const dist = boxDistance(p, target, G);
    if (dist > p.range + p.xrange) {
      stats.too_far++;
      return this.fail(socket, "too_far", place, { dist, id: target.id });
    }
    if (dist > p.range) p.xrange -= dist - p.range;

    let resolve;
    let reject = null;
    let cool = true;
    // commence_attack (node/server.js:3159-3612)
    const mainDef = p.slots.mainhand && G.items[p.slots.mainhand.name];
    if (p.type === "merchant" && !(mainDef && mainDef.wtype === "dartgun")) {
      socket.emit("game_response", { response: "attack_failed", id: target.id });
      reject = { failed: true, reason: "merchant", place, id: target.id };
      cool = false;
    } else if (target.is_player) {
      // Simpler than live: no PvP on the test server (a normal server is not PvP).
      socket.emit("game_response", { response: "friendly", id: target.id });
      reject = { failed: true, reason: "friendly", place, id: target.id };
      cool = false;
    } else {
      p.target = target.id;
      p.c = {};
      resolve = this.commenceAttack(p, target, "attack");
    }
    if (cool) this.consumeSkill(p, "attack", cooldown);
    this.resend(p, "u+cid");
    if (reject) {
      reject.response = reject.response || "data";
      socket.emit("game_response", reject);
    } else {
      socket.emit("game_response", resolve);
    }
  }

  // node/server_functions.js:3448-3468 (consume_skill): the next use waits the
  // cooldown plus the penalty (penalty_cd, at most 10 s).
  consumeSkill(p, name, cooldown) {
    const penalty = Math.min((p.s.penalty_cd && p.s.penalty_cd.ms) || 0, 10000);
    p.last[name] = clock() + penalty;
    p.socket.emit("skill_timeout", { name, ms: penalty + cooldown, penalty });
  }

  // node/server.js:3159-3612 (commence_attack), the attack part: the
  // projectile `action` goes to all who see it; `hit` comes at `eta`.
  commenceAttack(attacker, target, atype) {
    const G = this.G;
    let projectile;
    if (attacker.is_monster) projectile = G.monsters[attacker.type].projectile || "stone";
    if (attacker.is_player && G.classes[attacker.type].projectile) projectile = G.classes[attacker.type].projectile;
    const mainDef = attacker.slots && attacker.slots.mainhand && G.items[attacker.slots.mainhand.name];
    if (mainDef && mainDef.projectile) projectile = mainDef.projectile;
    if (!projectile && G.skills[atype].projectile) projectile = G.skills[atype].projectile;
    let damageType = attacker.damage_type || (attacker.is_player ? G.classes[attacker.type].damage_type : "physical");
    if (attacker.is_player && mainDef && mainDef.damage_type) damageType = mainDef.damage_type;
    const dist = boxDistance(attacker, target, G);
    const pid = randomStr(6);
    const action = {
      attacker: attacker.id,
      target: target.id,
      type: atype,
      source: atype,
      x: target.x,
      y: target.y,
      eta: 0,
      m: target.m,
      pid,
    };
    action.projectile = projectile;
    const proj = G.projectiles[projectile];
    if (proj && !proj.instant) action.eta = Math.floor((1000 * dist) / proj.speed);
    else action.instant = true;
    action.damage = attacker.attack;
    this.xyEmit(attacker, "action", action, target.id);
    const info = { pid, projectile, damageType, attack: attacker.attack, atype };
    this.later(action.eta, () => this.completeAttack(attacker, target, info));
    return Object.assign({}, action, { response: "data", place: atype });
  }

  // node/server.js:3707-4468 (complete_attack): the damage, the `hit` event,
  // then the kill or the death.
  completeAttack(attacker, target, info) {
    const G = this.G;
    if (target.dead || target.dc || attacker.dc || target.in !== attacker.in) return;
    if (target.is_player && (target.rip || !this.players[target.socket.id])) return;
    const defense = info.damageType === "magical" ? "resistance" : "armor";
    const pierce = info.damageType === "magical" ? "rpiercing" : "apiercing";
    let attack = Math.ceil(info.attack * (0.9 + this.rng() * 0.2));
    attack = Math.ceil(attack * damageMultiplier((target[defense] || 0) - (attacker[pierce] || 0))) || 0;
    if (target["1hp"]) attack = 1;
    // TEST_DAMAGE: a multiplier for monster damage only (COURSE.md).
    if (attacker.is_monster) attack = Math.round(attack * this.ctx.settings.damage);
    const before = target.hp;
    target.hp -= attack;
    const def = { hid: attacker.id, source: info.atype, projectile: info.projectile, damage_type: info.damageType, pid: info.pid, id: target.id, damage: attack };
    if (target.hp <= 0) def.kill = true;
    if (attacker.is_monster) attacker.outgoing += Math.min(Math.max(before, 0), attack);
    this.ctx.stats.hits++;
    this.xyEmit(target, "hit", def, attacker.id); // node/server.js:4343
    if (attacker.is_monster && target.is_player) {
      if (target.hp <= 0 && !target.rip) this.defeatedByMonster(attacker, target);
      target.c = {};
      this.resend(target, "u+cid"); // node/server.js:4440-4443
    } else if (target.is_monster) {
      target.u = true;
      target.cid++;
      target.points[attacker.name] = (target.points[attacker.name] || 0) + attack;
      if (target.hp <= 0) {
        this.killMonster(attacker, target);
      } else if (!target.target && !G.monsters[target.type].passive) {
        this.targetPlayer(target, attacker); // node/server.js:4387-4396
      }
    }
  }

  // node/server.js:4470-4497 (target_player): the monster chases the character.
  targetPlayer(m, p, noIncrease) {
    if (m.dead) return;
    m.target = p.name;
    if (!noIncrease) p.targets = (p.targets || 0) + 1;
    m.last.attacked = clock();
    m.moving = false;
    m.abs = true;
    m.u = true;
    m.cid++;
    m.speed = this.D.charge[m.type]; // calculate_monster_stats (node/server.js:1792-1794)
  }

  // node/server.js:13839-13882 (stop_pursuit), simpler.
  stopPursuit(m) {
    const p = this.byName[m.target];
    if (p && p.targets) p.targets--;
    m.target = undefined;
    m.speed = this.G.monsters[m.type].speed;
    m.moving = false;
    m.u = true;
    m.cid++;
  }

  // node/server.js:13884-13940 (defeated_by_a_monster)
  defeatedByMonster(m, p) {
    const lost = Math.floor(Math.min(Math.max(p.max_xp * 0.01, p.xp * 0.02), p.xp));
    p.xp -= lost;
    p.socket.emit("game_response", { response: "defeated_by_a_monster", xp: lost, monster: m.type });
    if (m.target) this.stopPursuit(m);
    this.rip(p);
  }

  // node/server_functions.js:439-449 (rip)
  rip(p) {
    p.hp = 0;
    p.rip = true;
    p.rip_time = clock();
    p.moving = false;
    p.abs = true;
    this.ctx.stats.deaths++;
    console.log(`[${p.socket.id}] ${p.name} died`);
    for (const m of Object.values(this.instances[p.in].monsters)) if (m.target === p.name) this.stopPursuit(m);
    if (p.party) this.sendPartyUpdate(p.party);
  }

  // node/server.js:2869-2893 (kill_monster)
  killMonster(attacker, m) {
    if (m.dead) return;
    if (!attacker.party) attacker.socket.emit("game_log", killMessage(attacker.name, m.type, true, this.G));
    else this.partyEmit(attacker.party, "game_log", killMessage(attacker.name, m.type, false, this.G));
    let noDecrease = false;
    if (!m.target) {
      this.targetPlayer(m, attacker, true);
      noDecrease = true;
    }
    this.ctx.stats.kills++;
    this.issueMonsterAward(m);
    this.removeMonster(m, noDecrease);
  }

  // node/server.js:2778-2867 (issue_monster_award): the chest and the xp go to
  // the character that the monster targets (or its party).
  issueMonsterAward(m) {
    const p = this.byName[m.target];
    if (!p) return;
    this.dropSomething(p, m);
    if (!p.party) {
      p.socket.emit("kill_credit", { mtype: m.type });
      if (p.type !== "merchant") p.xp += m.xp * p.xpm * m.mult;
      p.cid++;
      p.u = true;
      // Live sends the new xp with the next `player` update; we send it now.
      this.resend(p, "u+cid");
    } else {
      for (const name of this.parties[p.party]) {
        const c = this.byName[name];
        if (!c) continue;
        c.socket.emit("kill_credit", { mtype: m.type });
        if (c.type === "merchant") continue;
        c.xp += Math.round(m.xp * c.xpm * (c.share || 0) * m.mult);
        c.cid++;
        c.u = true;
        this.resend(c, "u+cid");
      }
    }
  }

  // node/server.js:13350-13406 (remove_monster): `death` to all who had it,
  // and a new monster of the pack later.
  removeMonster(m, noDecrease) {
    m.dead = true;
    const def = this.G.monsters[m.type];
    const ms = def.respawn > 200 ? Math.round(def.respawn * (720 + this.rng() * 480)) : Math.round(def.respawn * 1000 + this.rng() * 900);
    if (def.respawn !== -1) this.later(ms, () => this.newMonster(m.map, m.pack));
    let luckm;
    const p = this.byName[m.target];
    if (p) {
      luckm = p.luckm;
      if (!noDecrease && p.targets) p.targets--;
    }
    this.removeEntityEmit(m, "death", { id: m.id, luckm: luckm || 1 });
    delete this.instances[m.in].monsters[m.id];
  }

  // node/server.js:2381-2486 (drop_something): the chest. Gold from
  // D.monster_gold (or the pack), items from the drop tables (rare), and the
  // first-drop bonus. `drop` goes to the character, or to the party.
  dropSomething(p, m, share = 1) {
    const G = this.G;
    const id = randomStr(30);
    const GOLD = m.gold || G.monster_gold[m.type] || 0;
    const gd = G.drops.gold; // {base, random, x10, x50}
    const drop = { items: [], cash: 0 };
    drop.gold = Math.round(1 + GOLD * gd.base * share + this.rng() * GOLD * gd.random * share) * m.level * m.mult || 0;
    if (m.outgoing) drop.egold = Math.min(m.outgoing * B.m_outgoing_gmult, G.monsters[m.type].hp * 0.048) * share;
    drop.x = m.x;
    drop.y = m.y;
    drop.map = m.map;
    drop.in = m.in;
    this.rollDrops(p, m, drop, share);
    if (p.p.first && !p.p.first_drop) {
      // node/server.js:2428-2435
      p.p.first_drop = true;
      drop.gold += 100000;
      for (const name of ["ringsj", "ringsj", "ringsj", "hpbelt", "gem0"]) if (G.items[name]) drop.items.push(newItem(name, 1, G));
    }
    let chest = "chest3";
    if (this.rng() < gd.x10) (drop.gold *= 10), (chest = "chest4");
    if (this.rng() < gd.x50) (drop.gold *= 50), (chest = "chest5");
    if (drop.items.length || drop.cash) chest = "chest6";
    drop.chest = chest;
    drop.date = clock();
    this.chests[id] = drop;
    this.ctx.stats.chests_dropped++;
    if (p.party) {
      const owners = [];
      for (const name of this.parties[p.party]) {
        const c = this.byName[name];
        if (c && !owners.includes(c.owner)) owners.push(c.owner);
      }
      drop.party = p.party;
      this.partyEmit(p.party, "drop", { x: drop.x, y: drop.y, items: drop.items.length, chest, id, party: p.party, map: drop.map, owners }, p.in);
    } else {
      drop.owners = [p.owner];
      p.socket.emit("drop", { x: drop.x, y: drop.y, items: drop.items.length, chest, id, map: drop.map, owners: [p.owner] });
    }
  }

  // node/server.js:2273-2380 (roll_monster_drops): the monster and map
  // tables. Live also rolls the global tables; their chances are tiny.
  rollDrops(p, m, drop, share) {
    const G = this.G;
    const hpMult = m.max_hp / 1000;
    const add = (entry) => {
      // An entry is [chance, item] or [chance, "open", table] or [chance, "shells", n].
      if (entry[1] === "shells" || entry[1] === "open" || entry[1] === "cx" || !G.items[entry[1]]) return;
      drop.items.push(newItem(entry[1], entry[2] || 1, G));
    };
    for (const e of (G.drops.maps && G.drops.maps[m.map]) || []) {
      if (this.rng() / share / p.luckm / hpMult / m.luckx < e[0]) add(e);
    }
    for (const e of (G.drops.monsters && G.drops.monsters[m.type]) || []) {
      if (this.rng() / (share * p.luckm * m.level * m.mult) < e[0]) add(e);
    }
  }
  // endregion combat

  // region death
  // node/server.js:6271-6309 (respawn): after rip_time (TEST_RIP_MS), back to
  // the map's on_death spawn (main spawn 5), full hp, half mp.
  onRespawn(socket, data) {
    const p = this.players[socket.id];
    if (!p || !p.rip) return this.fail(socket, "invalid");
    if (p.rip_time) {
      const left = this.ctx.settings.ripMs - (clock() - p.rip_time);
      if (left > 0) return this.fail(socket, "cant_respawn", { ms: left });
    }
    this.ctx.stats.respawns++;
    p.hp = p.max_hp;
    p.mp = Math.round(p.max_mp / 2);
    p.rip = false;
    if (data && data.safe) {
      this.transportPlayerTo(p, "woffice", 0, 1);
    } else {
      const place = this.G.maps[p.map].on_death || this.G.maps[B.start_map].on_death || ["main", 0];
      this.transportPlayerTo(p, place[0], place[1], 1);
    }
    if (p.party) this.sendPartyUpdate(p.party);
    this.resend(p, "u+cid");
    this.success(socket, "data", { place: "respawn", cevent: "respawn" });
  }

  // node/server.js:5864-5885 (leave): out of jail, to main spawn 0.
  onLeave(socket) {
    const p = this.players[socket.id];
    if (!p) return;
    if (p.rip) return this.fail(socket, "transport_failed");
    if (p.targets > 5 || p.map !== "jail") return this.fail(socket, "cant_escape");
    this.transportPlayerTo(p, B.start_map);
    this.success(socket);
  }
  // endregion death

  // region potions
  // node/server.js:11988-12025 (use): regen without a potion: +50 hp or +100 mp
  // (G.skills.regen_hp/regen_mp.output), and the shared potion timer 4 s.
  onUse(socket, data) {
    const p = this.players[socket.id];
    if (!p) return;
    if (data.item === "hp" || data.item === "mp") {
      const now = clock();
      if (p.last.potion && p.last.potion > now) return this.fail(socket, "not_ready", { ms: p.last.potion - now });
      p.last.potion = now + 4000;
      if (data.item === "hp") p.hp = Math.min(p.hp + this.G.skills.regen_hp.output, p.max_hp);
      if (data.item === "mp") p.mp = Math.min(p.mp + this.G.skills.regen_mp.output, p.max_mp);
      this.ctx.stats.regens++;
      p.cid++;
      p.u = true;
      socket.emit("player", this.playerToClient(p));
      socket.emit("eval", { code: "pot_timeout(4000)" });
    }
    this.success(socket, { used: data.item });
  }

  // node/server.js:7643-7915 (equip): a potion (an item with `gives`) is drunk;
  // gear goes into its slot. Both use the same handler.
  onEquip(socket, data) {
    const p = this.players[socket.id];
    if (!p) return;
    const G = this.G;
    p.c = {};
    const num = Number(data.num);
    if (num >= p.items.length) return this.fail(socket, "invalid");
    const item = p.items[num];
    if (!item) return this.fail(socket, "no_item");
    if (item.b) return this.fail(socket, "item_blocked");
    if (item.name === "placeholder") return this.fail(socket, "item_placeholder");
    const def = G.items[item.name];
    if (!def) return this.fail(socket, "no_item");
    // Simpler than live: no merchant trade slots (data.slot "trade1".."trade48").
    if (data.slot && String(data.slot).startsWith("trade")) return this.fail(socket, "invalid");
    let toUpdate = "reopen+u+cid";
    const resolve = { num };
    if (def.gives) {
      // node/server.js:7798-7855: the shared potion timer.
      resolve.used = item.name;
      const now = clock();
      if (p.last.potion && p.last.potion > now) return this.fail(socket, "not_ready", { ms: p.last.potion - now });
      if (item.l) return this.fail(socket, "item_locked");
      this.consume(p, num);
      for (const [stat, amount] of def.gives) p[stat] = Math.max(1, (p[stat] || 0) + amount);
      p.hp = Math.min(p.hp, p.max_hp);
      p.mp = Math.min(p.mp, p.max_mp);
      const timeout = def.cooldown || 2000; // hpot0/mpot0: 2000
      p.last.potion = now + timeout;
      toUpdate = "u+cid+reopen+nc";
      this.ctx.stats.potions++;
      socket.emit("eval", { code: "pot_timeout(" + timeout + ")" });
    } else if (!data.consume) {
      // node/server.js:7856-7891
      const comp = canEquipItem(p, def, data.slot || def.type, G);
      if (comp === "no") {
        if (["weapon", "mainhand", "tool"].includes(data.slot || def.type) && p.slots.offhand && G.classes[p.type].doublehand[def.wtype]) {
          socket.emit("game_log", message("server.game_log.unequip_your_offhand_item_to_use_this_two_handed_weapon"));
        }
        this.resend(p, "u+cid+reopen");
        return this.fail(socket, "cant_equip");
      }
      let existing = p.slots[comp];
      p.slots[comp] = item;
      if (existing && existing.b) existing = null;
      p.items[num] = existing || null;
      const pen = (p.s.penalty_cd && p.s.penalty_cd.ms) || 0;
      p.s.penalty_cd = { ms: Math.min(pen + 120, 120000) }; // node/server.js:7906
      resolve.slot = comp;
      this.ctx.stats.equips++;
    } else {
      return this.fail(socket, "cant_consume");
    }
    this.resend(p, toUpdate);
    this.success(socket, "data", resolve);
  }

  // node/server.js:7933-7958 (unequip)
  onUnequip(socket, data) {
    const p = this.players[socket.id];
    if (!p || !data.slot || !p.slots[data.slot]) return this.fail(socket, "invalid");
    if (data.slot === "elixir") return this.fail(socket, "cant");
    const item = p.slots[data.slot];
    if (p.esize <= 0 && !item.b) return this.fail(socket, "no_space");
    delete p.slots[data.slot]; // live sets null; the client sees no item either way
    p.c = {};
    if (!item.b) this.addItem(p, item);
    this.ctx.stats.unequips++;
    this.resend(p, "reopen+u+cid");
    this.success(socket, "data");
  }
  // endregion potions

  // region chests
  // node/server.js:11273-11561 (open_chest). Farther than 400 px: it still
  // opens, with `dry: true` and goldm 1. Gold gets the 10 % server tax
  // (node/server_functions.js:715-728). A party chest shares the gold.
  onOpenChest(socket, data) {
    const p = this.players[socket.id];
    if (!p) return;
    const G = this.G;
    const chest = this.chests[data.id];
    const r = { id: data.id, goldm: p.goldm, opener: p.name, items: [] };
    if (chest && simpleDistance(chest, p) > 400) {
      r.goldm = 1;
      r.dry = true;
    }
    if (chest && clock() - chest.date > 8 * 60000) {
      r.goldm = 1;
      r.stale = true;
    }
    if (p.map === "woffice" || G.maps[p.map].mount) return this.fail(socket, "loot_failed");
    if (!chest) return socket.emit("chest_opened", { id: data.id, gone: true });
    this.ctx.stats.chests++;
    const tax = (gold) => gold - Math.floor(gold * 0.1);
    if (!p.party) {
      if (!this.canAddItems(p, chest.items)) return this.fail(socket, "loot_no_space");
      delete this.chests[data.id];
      let reopen = false;
      for (const item of chest.items) {
        this.addItem(p, item);
        reopen = true;
        const ritem = cacheItem(item);
        ritem.looter = p.name;
        r.items.push(ritem);
        socket.emit("game_log", itemMessage("server.item.found", item, G, {}, { color: "#4BAEAA" }));
      }
      r.gold = tax(Math.round(chest.gold * r.goldm) + Math.round(chest.egold || 0));
      p.gold += r.gold;
      if (r.gold) socket.emit("game_log", message("server.game_log.gold", { amount: String(r.gold) }, { color: "gold" }));
      if (!r.items.length) delete r.items;
      this.resend(p, reopen ? "reopen+nc+inv" : "");
      socket.emit("chest_opened", r);
    } else {
      // node/server.js:11387-11553, simpler: each item goes to the first member
      // with space (live draws a member by share).
      r.party = true;
      delete this.chests[data.id];
      const members = this.parties[p.party].map((n) => this.byName[n]).filter(Boolean);
      const reopen = {};
      for (const item of chest.items) {
        const winner = members.find((c) => this.canAddItem(c, item));
        const ritem = cacheItem(item);
        if (winner) {
          this.addItem(winner, item);
          reopen[winner.id] = true;
          ritem.looter = winner.name;
          this.partyEmit(p.party, "game_log", itemMessage("server.item.named_found", item, G, { player: winner.name }, { color: "#4BAEAA" }));
        } else {
          ritem.looter = null;
          ritem.lostandfound = true;
        }
        r.items.push(ritem);
      }
      if (!r.items.length) delete r.items;
      for (const c of members) {
        const cgold = tax(Math.round(chest.gold * (c.share || 0) * r.goldm) + Math.round((chest.egold || 0) * (c.share || 0)));
        c.gold += cgold;
        if (cgold) c.socket.emit("game_log", message("server.game_log.gold", { amount: String(cgold) }, { color: "gold" }));
        this.resend(c, reopen[c.id] ? "reopen+nc+inv" : "");
        c.socket.emit("chest_opened", Object.assign({}, r, { gold: cgold }));
      }
    }
  }
  // endregion chests

  // region npcs
  // node/server.js:8409-8461 (buy): an NPC on this map that sells the item
  // must be within 400 px.
  onBuy(socket, data) {
    const p = this.players[socket.id];
    if (!p || p.user) return this.fail(socket, "cant_in_bank");
    const G = this.G;
    const name = data.name;
    if (!this.D.canBuy.has(name)) return this.fail(socket, "buy_cant_npc");
    let quantity = Math.min(Math.max(parseInt(data.quantity) || 0, 1), G.items[name].s || 9999);
    if (!this.canAddItem(p, newItem(name, quantity, G))) return this.fail(socket, "buy_cant_space");
    let reach = null;
    for (const l of this.D.sellers[p.map][name] || []) if (simpleDistance(p, l) < B.sell_dist) reach = l;
    if (!reach) return this.fail(socket, "distance");
    if (!G.items[name].s) quantity = 1;
    const cost = quantity * G.items[name].g;
    if (p.gold < cost) return this.fail(socket, "buy_cost");
    const item = newItem(name, quantity, G);
    p.gold -= cost;
    const num = this.addItem(p, item);
    this.ctx.stats.buys++;
    this.xyEmit(reach, "ui", { type: "+$", id: reach.id, name: p.name, item: cacheItem(item), event: "buy" });
    this.resend(p, "reopen+nc+inv");
    this.success(socket, "buy_success", { cost, num, name, q: quantity, cevent: "buy" });
  }

  // node/server.js:8046-8096 (sell): any NPC with a shop on this map within
  // 400 px buys it, for 60 % of G.items[x].g (1 gold for a gift item).
  onSell(socket, data) {
    const p = this.players[socket.id];
    const num = data.num;
    const item = p.items[num]; // live reads this before the player check: no character -> "ERROR!"
    const quantity = Math.min(Math.max(parseInt(data.quantity) || 0, 1), (item && item.q) || 1);
    if (!p || p.user) return this.fail(socket, "cant_in_bank");
    if (!item) return this.fail(socket, "no_item");
    if (item.name === "placeholder") return this.fail(socket, "item_placeholder");
    if (item.l) return this.fail(socket, "item_locked");
    if (item.b) return this.fail(socket, "item_blocked");
    let reach = null;
    for (const m of this.D.merchants[p.map] || []) if (simpleDistance(p, m) < B.sell_dist) reach = m;
    if (!reach) return this.fail(socket, "distance");
    const value = itemValue(item, this.G);
    this.consume(p, num, quantity);
    p.gold += value * quantity;
    const sold = cacheItem(item);
    if (item.q) sold.q = quantity;
    this.ctx.stats.sells++;
    this.xyEmit(reach, "ui", { type: "-$", id: reach.id, name: p.name, item: sold, num, event: "sell" });
    this.resend(p, "reopen+nc+inv");
    this.success(socket, "gold_received", { gold: value * quantity, item: sold, cevent: "sell" });
  }

  // node/server.js:5887-6056 (transport): a door of this map within 112 px of
  // the door box, or the transporter NPC within 160 px. The bank is a "mount"
  // map: the reply is `in_progress`, and new_map comes after the account loads.
  onTransport(socket, data) {
    const p = this.players[socket.id];
    if (!p) return;
    const G = this.G;
    if (p.rip || p.map === "jail") return this.fail(socket, "transport_failed");
    const to = data.to;
    const s = data.s || 0;
    if (!G.maps[to] || !this.instances[to]) return this.fail(socket, "cant_enter");
    if (p.targets > 5) return this.fail(socket, "cant_escape");
    let reach = false;
    for (const door of G.maps[p.map].doors || []) {
      // door: [x, y, width, height, to map, to spawn, own spawn, lock]. The
      // distance is from the box of the door's own spawn (door[6]).
      if (reach || door[4] !== to || s !== (door[5] || 0)) continue;
      const sp = G.maps[p.map].spawns[door[6]];
      const box = { map: p.map, x: sp[0], y: sp[1], width: door[2], height: door[3] };
      if (boxDistance(box, p, G) < B.door_dist) reach = "door";
    }
    const t = this.D.ref[p.map].transporter;
    if (!reach && t && simpleDistance(t, p) < B.transporter_dist && G.npcs.transporter.places[to] === s) reach = "transport";
    if (!reach) return this.fail(socket, "transport_cant_reach");
    const toMount = !!G.maps[to].mount;
    if (toMount && !p.user) {
      // node/server.js:6029-6036: enter the bank.
      if (p.mounting || p.unmounting) return this.fail(socket, "bank_opi");
      this.addCallCost(socket, 32, "bank");
      p.mounting = true;
      this.later(BANK_MOUNT_MS, () => {
        p.mounting = false;
        if (!this.players[socket.id]) return;
        p.user = JSON.parse(JSON.stringify(this.ctx.accounts.user.bank)); // R.user (node/server.js:16610-16611)
        this.transportPlayerTo(p, to, s);
        this.resend(p);
      });
      return this.success(socket, { success: false, in_progress: true });
    } else if (!toMount && p.user) {
      // node/server.js:6037-6048: leave the bank.
      if (p.mounting || p.unmounting) return this.fail(socket, "bank_opi");
      this.addCallCost(socket, 16, "bank");
      p.unmounting = true;
      this.later(BANK_MOUNT_MS, () => {
        p.unmounting = false;
        if (!this.players[socket.id]) return;
        Object.assign(this.ctx.accounts.user.bank, p.user);
        p.user = null;
        this.transportPlayerTo(p, to, s);
        this.resend(p);
      });
      return this.success(socket, { success: false, in_progress: true });
    }
    this.transportPlayerTo(p, to, s);
    this.success(socket);
  }

  // node/server.js:9257-9282, 9475-9482 (bank): gold in and out of the bank,
  // only while the account is "mounted" (inside the bank). Live answers twice:
  // success_response(success), which becomes {response: "data", place: "bank",
  // gold, cevent, success: true}, then the real code {response: "bank_store"
  // or "bank_withdraw", gold, cevent} without a place. Simpler than live: only
  // the gold operations; items and packs answer "invalid".
  onBank(socket, data) {
    const p = this.players[socket.id];
    if (!p) return;
    if (!p.user || p.mounting || p.unmounting) return this.fail(socket, "bank_unavailable");
    let success;
    if (data.operation === "withdraw") {
      const amount = Math.max(0, Math.min(parseInt(data.amount) || 0, p.user.gold));
      p.user.gold -= amount;
      p.gold += amount;
      success = { response: "bank_withdraw", gold: amount, cevent: true };
    } else if (data.operation === "deposit") {
      const amount = Math.max(0, Math.min(parseInt(data.amount) || 0, p.gold));
      p.user.gold += amount;
      p.gold -= amount;
      success = { response: "bank_store", gold: amount, cevent: true };
    } else {
      return this.fail(socket, "invalid");
    }
    this.resend(p, "reopen");
    this.success(socket, Object.assign({}, success)); // an object: response becomes "data"
    socket.emit("game_response", success);
  }
  // endregion npcs

  // region party
  // node/server.js:12357-12546 (party): invite, request, accept, raccept,
  // leave, kick. Every branch ends with success_response({}) unless it
  // returned early.
  onParty(socket, data) {
    const p = this.players[socket.id];
    if (!p) return;
    const limits = { party: 9, party_max: 10 }; // node/server.js:255-259
    const full = (leader) => this.parties[leader] && this.parties[leader].length >= limits.party_max;
    if (data.event === "invite") {
      if (p.party && full(p.party)) return this.fail(socket, "party_full");
      const invited = this.byName[data.id || data.name];
      if (!invited || invited.id === p.id) return this.fail(socket, "invalid");
      if (p.party && p.party === invited.party) return this.success(socket, "already_in_party");
      invited.socket.emit("invite", { name: p.name });
      socket.emit("game_log", message("server.game_log.invited_to_party", { invited: String(invited.name) }));
      (this.invitations[p.name] = this.invitations[p.name] || {})[invited.id] = 1;
      this.ctx.stats.invites++;
    }
    if (data.event === "request") {
      const invited = this.byName[data.id || data.name];
      if (!invited || invited.id === p.id) return this.fail(socket, "invalid");
      if (p.party && p.party === invited.party) return this.success(socket, "already_in_party");
      invited.socket.emit("request", { name: p.name });
      (this.requests[p.name] = this.requests[p.name] || {})[invited.id] = 1;
    }
    if (data.event === "accept" || data.event === "raccept") {
      // accept: p accepts an invite of data.name. raccept: p accepts a request
      // of data.name (the requester joins p's party).
      const other = this.byName[data.name];
      if (!other) return this.fail(socket, "player_gone", { name: data.name });
      const inviter = data.event === "accept" ? other : p;
      const joiner = data.event === "accept" ? p : other;
      if (inviter.party && full(inviter.party)) return this.fail(socket, "party_full");
      // The invite (or request) came from `other` to `p`.
      const table = data.event === "accept" ? this.invitations : this.requests;
      const from = other.name;
      const to = p.id;
      if (!table[from] || !table[from][to]) return this.fail(socket, data.event === "accept" ? "invitation_expired" : "request_expired");
      if (joiner.party && joiner.party === inviter.party) return this.success(socket, "already_in_party");
      if (joiner.party) {
        this.leaveParty(joiner.party, joiner);
        joiner.socket.emit("party_update", {});
        joiner.socket.emit("game_log", message("server.game_log.left_your_current_party"));
      }
      table[from][to] = 0;
      if (!inviter.party) {
        inviter.party = inviter.name;
        this.parties[inviter.name] = [inviter.name];
        this.resend(inviter, "nc+u+cid");
      }
      joiner.party = inviter.party;
      this.parties[inviter.party].push(joiner.name);
      const withInvite = data.event === "accept" && inviter.party !== inviter.name;
      this.partyEmit(
        joiner.party,
        "party_update",
        message(withInvite ? "server.party.joined_with_invite" : "server.party.joined", { player: joiner.name, inviter: inviter.name }, { list: this.parties[inviter.party], party: this.partyToClient(inviter.party) }),
      );
      this.resend(joiner, "nc+u+cid");
      this.ctx.stats.party_joins++;
    }
    if (data.event === "leave") {
      if (!p.party) {
        socket.emit("party_update", {});
        return this.success(socket, {});
      }
      this.leaveParty(p.party, p);
      socket.emit("party_update", {});
      socket.emit("game_log", message("server.game_log.left_the_party"));
      this.resend(p, "nc+u+cid");
    }
    if (data.event === "kick") {
      if (!p.party) return this.success(socket, {});
      const list = this.parties[p.party];
      if (!list.includes(data.name)) {
        socket.emit("party_update", { list, party: this.partyToClient(p.party) });
        return this.success(socket, {});
      }
      if (list.indexOf(p.name) > list.indexOf(data.name)) return this.fail(socket, "cant_kick");
      const kicked = this.byName[data.name];
      if (!kicked) return this.fail(socket, "player_gone");
      this.leaveParty(p.party, kicked);
      kicked.socket.emit("party_update", {});
      this.resend(kicked, "nc+u+cid");
    }
    this.success(socket, {});
  }

  // node/server.js:1138-1213 (party_to_client): each member's share of the
  // gold and xp. With no damage history (pdps 0) the share is even among the
  // members that are not merchants; merchants get 0.
  partyToClient(leader) {
    const list = this.parties[leader] || [];
    const members = list.map((n) => this.byName[n]).filter(Boolean);
    const fighters = members.filter((c) => c.type !== "merchant");
    const party = {};
    for (const c of members) {
      if (!fighters.length) c.share = 1 / Math.max(1, list.length);
      else c.share = c.type === "merchant" ? 0 : 1 / fighters.length;
      c.party_length = fighters.length;
      c.party_xp = [0, 0, 10, 16, 20, 24, 25, 30, 36, 40, 40, 40, 40][fighters.length] || 0;
      party[c.name] = {
        skin: c.skin,
        level: c.level,
        type: c.type,
        x: c.x,
        y: c.y,
        in: c.in,
        map: c.map,
        share: c.share,
        pdps: c.pdps,
        l: fighters.length,
        xp: c.party_xp,
        luck: 0,
        gold: 5,
      };
      if (c.rip) party[c.name].rip = true;
      if (Object.keys(c.cx || {}).length) party[c.name].cx = c.cx;
    }
    return party;
  }

  // node/server.js:1215-1226 (send_party_update)
  sendPartyUpdate(leader) {
    if (!this.parties[leader]) return;
    const party = this.partyToClient(leader);
    for (const name of this.parties[leader]) {
      const c = this.byName[name];
      if (c) c.socket.emit("party_update", { list: this.parties[leader], party });
    }
  }

  // node/server_functions.js:3553-3601 (party_emit)
  partyEmit(leader, event, data, onlyIn) {
    for (const name of this.parties[leader] || []) {
      const c = this.byName[name];
      if (!c || (onlyIn && c.in !== onlyIn)) continue;
      c.socket.emit(event, data);
    }
  }

  // node/server_functions.js:3603-3666 (leave_party): the others get
  // party_update with `leave: 1`; a party of one ends.
  leaveParty(leader, leaver) {
    const old = this.parties[leader];
    if (!old) {
      leaver.party = undefined;
      return;
    }
    const rest = [];
    for (const name of old) {
      const c = this.byName[name];
      if (c) c.party = null;
      if (name !== leaver.name && c) rest.push(name);
    }
    leaver.party = null;
    delete this.parties[leader];
    if (rest.length >= 2) {
      this.parties[rest[0]] = rest;
      for (const name of rest) this.byName[name].party = rest[0];
    }
    for (const name of old) {
      const c = this.byName[name];
      if (!c || name === leaver.name) continue;
      const list = rest.length >= 2 ? this.parties[rest[0]] : false;
      c.socket.emit(
        "party_update",
        message("server.party.left", { player: leaver.name }, { leave: 1, list, party: list ? this.partyToClient(rest[0]) : {} }),
      );
      this.resend(c, "nc+u+cid");
    }
  }
  // endregion party

  // region send
  // node/server.js:8463-8627 (send): items or gold to another character on
  // this server, on the same map, within 400 px. Gold to a character of
  // another account loses 2.5 % (all test characters are one account: no loss).
  onSend(socket, data) {
    const p = this.players[socket.id];
    const receiver = this.byName[data.name || ""];
    if (!p || p.user) return this.fail(socket, "cant_in_bank");
    if (!receiver || receiver.user) return this.fail(socket, "receiver_unavailable");
    if (boxDistance(receiver, p, this.G) > B.dist || receiver.map !== p.map) return this.fail(socket, "distance");
    if (data.num !== undefined) {
      const num = Math.max(0, parseInt(data.num) || 0);
      const item = p.items[num];
      if (!item) return this.fail(socket, "send_no_item");
      if (item.name === "placeholder") return this.fail(socket, "item_placeholder");
      if (item.l) return this.fail(socket, "item_locked");
      if (item.b) return this.fail(socket, "item_blocked");
      const q = Math.min(item.q || 1, Math.max(1, parseInt(data.q || 1) || 1));
      if (!this.canAddItem(receiver, newItem(item.name, q, this.G))) return this.fail(socket, "send_no_space");
      let sent;
      if ((item.q || 1) === q) {
        p.items[num] = null;
        p.esize++;
      } else {
        p.items[num].q -= q;
      }
      if (item.q) {
        sent = newItem(item.name, q, this.G); // create_new_sitem
        if (item.p) sent.p = item.p;
      } else {
        sent = item;
      }
      const rnum = this.addItem(receiver, sent);
      this.ctx.stats.sends++;
      this.xyEmit(p, "ui", { type: "item_sent", receiver: receiver.name, sender: p.name, item: Object.assign(cacheItem(sent), { q }), num: rnum, fnum: num, event: true });
      this.resend(p, "reopen+nc+inv");
      this.resend(receiver, "reopen+nc+inv");
      receiver.socket.emit("game_response", { response: "item_received", name: p.name, item: item.name, q, num: rnum, cevent: true });
      socket.emit("game_response", { response: "item_sent", name: receiver.name, item: item.name, q, num, cevent: true, place: "send" });
    } else if (data.gold !== undefined) {
      let gold = Math.min(p.gold, Math.max(1, parseInt(data.gold || 1) || 1)) || p.gold;
      if (!gold) return this.fail(socket, "invalid");
      p.gold -= gold;
      if (receiver.owner !== p.owner && gold !== 1) gold = parseInt(gold * 0.975);
      receiver.gold += gold;
      this.ctx.stats.sends++;
      this.xyEmit(p, "ui", { type: "gold_sent", receiver: receiver.name, sender: p.name, gold, event: true });
      this.resend(p, "reopen+nc+inv");
      this.resend(receiver, "reopen+nc+inv");
      receiver.socket.emit("game_response", { response: "gold_received", name: p.name, gold, cevent: true });
      socket.emit("game_response", { response: "gold_sent", name: receiver.name, gold, cevent: true, place: "send" });
    }
  }
  // endregion send

  // region upgrade
  // node/server.js:7134-7567 (upgrade), the upgrade-scroll path (uscroll),
  // without offerings and stat scrolls. The upgrade NPC must be within 400 px.
  // `calculate: true` only returns the chance. Else the item becomes a
  // "placeholder" while q.upgrade runs; `q_data` shows the progress, and the
  // result comes as a hitchhiker of a `player` update.
  onUpgrade(socket, data) {
    const p = this.players[socket.id];
    const G = this.G;
    const item = p && p.items[data.item_num];
    const scroll = p && p.items[data.scroll_num];
    if (!p || p.user) return this.fail(socket, "cant_in_bank");
    if (p.q.upgrade) return socket.emit("game_response", "upgrade_in_progress");
    const npc = this.D.ref.main.upgrade;
    if (simpleDistance(npc, p) > B.sell_dist) return socket.emit("game_response", { response: "distance", place: "upgrade", failed: true });
    if (!item) return socket.emit("game_response", "upgrade_no_item");
    if (data.offering_num !== undefined && data.offering_num !== null) {
      // Simpler than live: no offerings.
      return socket.emit("game_response", "upgrade_invalid_offering");
    }
    if (!scroll) return socket.emit("game_response", "upgrade_no_scroll");
    // node/server.js:7166-7168: the client must send the item's level as
    // `clevel`; a missing clevel never matches.
    if ((item.level || 0) != data.clevel) return socket.emit("game_response", "upgrade_mismatch");
    const idef = G.items[item.name];
    const sdef = G.items[scroll.name];
    const grade = itemGrade(idef, item);
    if (!idef.upgrade) return socket.emit("game_response", "upgrade_cant");
    if (sdef.type !== "uscroll" || grade > sdef.grade) {
      if (grade === 4 && sdef.type === "uscroll") return socket.emit("game_response", { response: "max_level", level: item.level, place: "upgrade", failed: true });
      return socket.emit("game_response", "upgrade_incompatible_scroll");
    }
    if (item.l) return socket.emit("game_response", { response: "item_locked", place: "upgrade", failed: true });
    if (grade === 4) return socket.emit("game_response", { response: "max_level", level: item.level, place: "upgrade", failed: true });
    if (!data.calculate) this.consume(p, data.scroll_num);
    const newLevel = (item.level || 0) + 1;
    const ograde = itemGrade(idef, { level: 0 });
    const tmult = ograde === 1 ? 1.5 : ograde === 2 ? 2 : 1;
    // The chance (node/server.js:7313-7406): G.upgrades[igrade][level], plus
    // "grace" from earlier failures, at most +0.24 (or +0.36 with a higher scroll).
    let probability = G.upgrades[this.D.igrade[item.name]][String(newLevel)];
    const oprobability = probability;
    const ug = (lvl) => p.p.ugrace[lvl] || 0;
    let grace = Math.max(0, Math.min(newLevel + 1, (item.grace || 0) + Math.min(3, ug(newLevel) / 4.5) + this.D.igrace[item.name]) + p.p.ograce / 3.2);
    grace = (probability * grace) / newLevel + grace / 1000;
    let high = false;
    if (sdef.grade > grade && newLevel <= 10) {
      probability = probability * 1.2 + 0.01;
      high = true;
      if (!data.calculate) item.grace = (item.grace || 0) + 0.4;
    }
    grace = Math.max(0, grace / 4.8 - 0.4 / ((newLevel - 0.999) * (newLevel - 0.999)));
    probability += grace;
    if (!data.calculate && this.rng() < 0.025) item.grace = (item.grace || 0) + 1;
    probability = high ? Math.min(probability, Math.min(oprobability + 0.36, oprobability * 3)) : Math.min(probability, Math.min(oprobability + 0.24, oprobability * 2));
    if (data.calculate) {
      return this.success(socket, "upgrade_chance", { calculate: true, chance: probability, item: cacheItem(item), grace: item.grace || 0, scroll: scroll.name });
    }
    const result = this.rng();
    const ms = 500 * newLevel * Math.sqrt(newLevel) * tmult; // node/server.js:7427
    p.q.upgrade = { ms, len: ms, num: data.item_num };
    p.items[data.item_num] = { name: "placeholder", p: { chance: probability, name: item.name, level: item.level, scroll: scroll.name, offering: undefined, nums: [] } };
    p.p.u_level = item.level || 0;
    p.p.u_roll = result;
    if (result <= probability) {
      p.p.ugrace[newLevel] = 0;
      p.p.ograce *= 1 - newLevel * 0.005;
      item.level = newLevel;
      if (item.oo !== p.name) item.o = p.name;
      p.p.u_item = item;
    } else {
      p.p.ugrace[newLevel - 1] = ug(newLevel - 1) + 1;
      p.p.ugrace[newLevel] = ug(newLevel) + 1;
      p.p.u_itemx = item;
    }
    this.ctx.stats.upgrades++;
    this.resend(p, "reopen+nc+inv");
  }

  // node/server.js:6862-7132 (compound): three items of the same name and
  // level, a compound scroll, the NPC within 400 px. q.compound runs 10 s.
  onCompound(socket, data) {
    const p = this.players[socket.id];
    const G = this.G;
    if (!Array.isArray(data.items) || data.items.length !== 3) return this.fail(socket, "no_item");
    if (!data.items.every((n) => Number.isInteger(n))) return this.fail(socket, "no_item");
    const [i0, i1, i2] = data.items.map((n) => p.items[n]); // live: no character -> "ERROR!"
    const scroll = p.items[data.scroll_num];
    if (!p || p.user) return this.fail(socket, "cant_in_bank");
    if (p.q.compound) return this.fail(socket, "compound_in_progress", "compound", "in_progress");
    if (data.offering_num !== undefined && data.offering_num !== null) return socket.emit("game_response", "compound_invalid_offering");
    if (!scroll) return socket.emit("game_response", "compound_no_scroll");
    if (!i0 || !i1 || !i2) return this.fail(socket, "no_item");
    if (simpleDistance(this.D.ref.main.compound, p) > B.sell_dist) return socket.emit("game_response", { response: "distance", place: "compound", failed: true });
    const def = G.items[i0.name];
    const sdef = G.items[scroll.name];
    const grade = itemGrade(def, i0);
    if (grade === 4) return socket.emit("game_response", { response: "max_level", level: i0.level || 0, place: "compound", failed: true });
    if (!(i0.name === i1.name && i1.name === i2.name && (i0.level || 0) === (i1.level || 0) && (i1.level || 0) === (i2.level || 0))) {
      return socket.emit("game_response", "compound_mismatch");
    }
    if ((i0.level || 0) != data.clevel) return this.fail(socket, "no_item"); // clevel is required, as for upgrade
    if (!def.compound) return socket.emit("game_response", "compound_cant");
    if (sdef.type !== "cscroll" || grade > sdef.grade) return socket.emit("game_response", "compound_incompatible_scroll");
    if (i0 === i1 || i1 === i2 || i0 === i2) return socket.emit("game_response", { response: "misc_fail", place: "compound", failed: true });
    if (i0.l || i1.l || i2.l) return socket.emit("game_response", { response: "item_locked", place: "compound", failed: true });
    if (!data.calculate) this.consume(p, data.scroll_num);
    const newLevel = (i0.level || 0) + 1;
    let igrade = this.D.igrade[i0.name];
    if ((i0.level || 0) >= 3) igrade = itemGrade(def, { level: (i0.level || 0) - 2 });
    let probability = G.compounds[igrade][String(newLevel)];
    const oprobability = probability;
    let high = 0;
    let graceBonus = 0;
    if (sdef.grade > grade) {
      probability = probability * 1.1 + 0.001;
      if (!data.calculate) graceBonus += 0.4;
      high = sdef.grade - grade;
    }
    const grace = 0.007 * ((i0.grace || 0) + (i1.grace || 0) + (i2.grace || 0) + p.p.ograce);
    probability += Math.min(25 * 0.007, grace) / Math.max((i0.level || 0) - 1, 1);
    if (!data.calculate) i0.grace = Math.max(i0.grace || 0, i1.grace || 0, i2.grace || 0) / 6.4 + graceBonus;
    probability = Math.min(probability, Math.min(oprobability * (3 + (high ? high * 0.6 : 0)), oprobability + 0.2 + (high ? high * 0.05 : 0)));
    const result = this.rng();
    if (data.calculate) {
      return this.success(socket, "compound_chance", { calculate: true, chance: probability, item: cacheItem(i0), scroll: scroll.name, grace: (i0.grace || 0) + (i1.grace || 0) + (i2.grace || 0) });
    }
    const len = 10000; // node/server.js:7037
    p.p.c_roll = result;
    p.q.compound = { ms: len, len, num: data.items[0], nums: [] };
    p.items[data.items[0]] = { name: "placeholder", p: { chance: probability, name: i0.name, level: i0.level || 0, scroll: scroll.name, offering: undefined, nums: [] } };
    p.items[data.items[1]] = null;
    p.items[data.items[2]] = null;
    p.esize += 2;
    if (result <= probability) {
      p.p.ograce *= 1 - newLevel * 0.02;
      i0.level = newLevel;
      if (i0.oo !== p.name) i0.o = p.name;
      p.p.c_item = i0;
      p.p.c_itemx = null;
    } else {
      p.p.c_item = null;
      p.p.c_itemx = i0;
    }
    this.ctx.stats.compounds++;
    this.resend(p, "reopen+nc+inv");
  }

  // node/server.js:14736-14960: run the upgrade and compound timers. While
  // they run, `q_data` shows the digits of the roll; at the end the item
  // comes back (or is gone) and the result rides as a hitchhiker.
  runQueues(p, ms) {
    for (const name of Object.keys(p.q)) {
      const ref = p.q[name];
      const value = ref.ms;
      ref.ms -= ms;
      const slot = p.items[ref.num];
      if (slot && slot.name === "placeholder") {
        const def = slot.p;
        const roll = name === "upgrade" ? p.p.u_roll : p.p.c_roll;
        const lim = name === "upgrade"
          ? [ref.len * 0.8, ref.len * 0.64, ref.len * 0.4, Math.min(3000, ref.len * 0.3), Math.min(2200, ref.len * 0.22)]
          : [8000, 6400, 5000, 3000, 2200];
        let change = false;
        const digits = [parseInt(roll * 10000) % 10, parseInt(roll * 1000) % 10, parseInt(roll * 100) % 10, parseInt(roll * 10)];
        for (let i = 0; i < 4; i++) {
          if (value < lim[i] && def.nums[i] === undefined) {
            def.nums[i] = digits[i];
            change = true;
          }
        }
        const won = name === "upgrade" ? p.p.u_item : p.p.c_item;
        if (value < lim[4] && won && !def.success) (def.success = true), (change = true);
        if (value < lim[4] && !won && !def.failure) (def.failure = true), (change = true);
        if (change) p.socket.emit("q_data", { q: p.q, num: ref.num, p: def });
      }
      if (ref.ms > 0) continue;
      delete p.q[name];
      if (name === "upgrade") {
        const newLevel = p.p.u_level + 1;
        if (p.p.u_item && slot && slot.name === "placeholder") {
          p.items[ref.num] = p.p.u_item;
          p.hitchhikers.push(["game_response", { response: "upgrade_success", level: newLevel, num: ref.num, stale: ref.stale }]);
          this.xyEmit(this.D.ref.main.upgrade, "upgrade", { type: "upgrade", success: 1 });
        } else {
          if (slot && slot.name === "placeholder") {
            p.items[ref.num] = null;
            p.esize++;
          }
          p.hitchhikers.push(["game_response", { response: "upgrade_fail", level: newLevel, num: ref.num, stale: ref.stale }]);
          this.xyEmit(this.D.ref.main.upgrade, "upgrade", { type: "upgrade", success: 0 });
        }
        for (const k of ["u_item", "u_itemx", "u_roll", "u_level"]) delete p.p[k];
      } else if (name === "compound") {
        if (p.p.c_item) {
          const item = p.p.c_item;
          p.hitchhikers.push(["game_response", { response: "compound_success", stale: ref.stale, level: item.level, num: ref.num, up: item.extra || undefined }]);
          this.xyEmit(this.D.ref.main.compound, "upgrade", { type: "compound", success: 1 });
          if (slot && slot.name === "placeholder") p.items[ref.num] = item;
        } else {
          const item = p.p.c_itemx;
          p.hitchhikers.push(["game_response", { response: "compound_fail", level: item.level, num: ref.num, stale: ref.stale }]);
          this.xyEmit(this.D.ref.main.compound, "upgrade", { type: "compound", success: 0 });
          if (slot && slot.name === "placeholder") {
            p.items[ref.num] = null;
            p.esize++;
          }
        }
        for (const k of ["c_item", "c_itemx", "c_roll"]) delete p.p[k];
      }
      this.resend(p, "reopen+u+cid+nc+inv");
    }
  }
  // endregion upgrade

  // region tick
  // One step of the world: timers, movement, monsters, queues, updates.
  tick() {
    const now = clock();
    const dt = this.lastTick ? (now - this.lastTick) / 1000 : TICK_MS / 1000;
    this.lastTick = now;
    try {
      // Timers (projectiles, respawns, saves, the bank).
      if (this.pending.length) {
        const due = this.pending.filter((t) => t[0] <= now);
        this.pending = this.pending.filter((t) => t[0] > now);
        due.sort((a, b) => a[0] - b[0]);
        for (const [, fn] of due) fn();
      }
      for (const p of Object.values(this.players)) {
        if (this.step(p, dt)) p.push = true; // arrived: send the full view
        if (Math.abs(p.x - p.last_upush[0]) > B.u_vision || Math.abs(p.y - p.last_upush[1]) > B.u_vision) p.push = true;
        p.xrange = Math.min(25, p.xrange + 5 * dt); // +5 each second (node/server.js:16236-16245)
        if (p.s.penalty_cd) {
          p.s.penalty_cd.ms -= dt * 1000;
          if (p.s.penalty_cd.ms <= 0) delete p.s.penalty_cd;
        }
        if (Object.keys(p.q).length) this.runQueues(p, dt * 1000);
      }
      for (const map in this.instances) {
        for (const m of Object.values(this.instances[map].monsters)) this.monsterAi(m, now, dt);
      }
      this.sendXyUpdates();
    } catch (e) {
      console.log(`[${this.key}] tick error: ${e && e.stack}`);
      this.ctx.stats.errors++;
    }
  }

  // The monsters, much simpler than live (node/server.js:14280-14700):
  // - With a target: chase it at the `charge` speed; in range, attack at the
  //   monster's frequency with G attack x TEST_DAMAGE.
  // - Without: wander to a random point of the pack's box every 2-6 s. So
  //   idle goos stay in their G box.
  // Monsters attack only a character that attacked them (no aggro here).
  monsterAi(m, now, dt) {
    if (m.dead) return;
    const G = this.G;
    if (m.target) {
      const p = this.byName[m.target];
      if (!p || p.rip || p.in !== m.in || p.dc) return this.stopPursuit(m);
      const d = boxDistance(m, p, G);
      if (d > m.range) {
        if (!m.moving || Math.hypot(m.going_x - p.x, m.going_y - p.y) > 10) {
          m.going_x = p.x;
          m.going_y = p.y;
          this.startMoving(m);
        }
        this.step(m, dt);
      } else {
        if (m.moving) {
          m.moving = false;
          m.u = true;
        }
        if (now >= (m.last.attack || 0) + 1000 / m.frequency) {
          // node/server.js:3427-3432: monsters attack with a random -50..50 ms.
          m.last.attack = now + Math.round(this.rng() * 100 - 50);
          this.commenceAttack(m, p, "attack");
        }
      }
      return;
    }
    if (m.moving) {
      this.step(m, dt);
      return;
    }
    if (now >= m.next_wander) {
      const [x1, y1, x2, y2] = m.box;
      m.going_x = x1 + this.rng() * (x2 - x1);
      m.going_y = y1 + this.rng() * (y2 - y1);
      if (!crossesWall(G.geometry[m.map], m.x, m.y, m.going_x, m.going_y)) this.startMoving(m);
      else (m.going_x = m.x), (m.going_y = m.y);
      m.next_wander = now + 2000 + this.rng() * 4000;
    }
  }
  // endregion tick

  // region test-control
  // POST /test/drop: close the socket of one character (by name), or of all.
  dropCharacter(name) {
    let n = 0;
    for (const p of Object.values(this.players)) {
      if (!name || p.name === name) {
        p.socket.disconnect(true);
        n++;
      }
    }
    return n;
  }

  // POST /test/jail: a line violation for one character now, as if it sent a
  // `move` through a wall (lineViolation). Tests the `leave` code of a bot.
  jailCharacter(name) {
    let n = 0;
    for (const p of Object.values(this.players)) {
      if (p.name === name && !p.rip && p.map !== "jail") {
        console.log(`[${p.socket.id}] TEST: jail for ${p.name}`);
        this.lineViolation(p);
        n++;
      }
    }
    return n;
  }

  // The armed controls (ctx.armed, from POST /test/drop or /test/jail with
  // after_start_ms): when `name` gets `start`, run each control for it that
  // many ms later, once. They find the character by name when they run, so a
  // reconnect in between does not matter.
  runArmed(name) {
    const mine = this.ctx.armed.filter((a) => a.name === name);
    this.ctx.armed = this.ctx.armed.filter((a) => a.name !== name);
    for (const a of mine) {
      this.later(a.ms, () => {
        if (a.action === "drop") this.ctx.stats.drops += this.dropCharacter(name);
        if (a.action === "jail") this.jailCharacter(name);
      });
    }
  }

  // POST /test/reset: close all sockets and make the world new.
  resetAll() {
    for (const s of this.sockets.values()) s.disconnect(true);
    this.sockets.clear();
    this.reset();
  }

  // GET /test/stats: the state of this server.
  summary() {
    const inst = this.instances.main;
    return {
      key: this.key,
      path: this.path,
      players: Object.values(this.players).map((p) => ({ name: p.name, map: p.map, x: Math.round(p.x), y: Math.round(p.y), hp: p.hp, rip: p.rip, cc: this.getCallCost(p.socket) })),
      observers: Object.keys(this.observers).length,
      monsters: Object.keys(inst.monsters).length,
      chests: Object.keys(this.chests).length,
      parties: this.parties,
    };
  }
  // endregion test-control
}

export { ACCOUNT };
