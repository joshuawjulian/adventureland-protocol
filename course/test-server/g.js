// g.js: load the game data G, and the game math that the live server takes
// from it (distance, damage, item stats, item value, slots).
//
// Citations: node/... is vendor/adventureland_mongodb/node, js/... is
// vendor/adventureland_mongodb/js. Treat line numbers as "within a few lines".

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { trimG, parseGText, downloadG } from "./trim-g.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));

// region load-g
// Load G in this order: TEST_G_FILE, else G.json next to this file, else
// download https://adventure.land/data.js, trim it and save it as G.json.
// The result is always trimmed (trim-g.js), so /data.js is the same for a full
// and a trimmed input file.
export async function loadG(file) {
  if (file) {
    const G = trimG(parseGText(fs.readFileSync(file, "utf8")));
    console.log(`G version ${G.version} from ${file}`);
    return G;
  }
  const local = path.join(HERE, "G.json");
  if (fs.existsSync(local)) {
    const G = trimG(parseGText(fs.readFileSync(local, "utf8")));
    console.log(`G version ${G.version} from ${local}`);
    return G;
  }
  console.log("no G.json: downloading https://adventure.land/data.js");
  const G = trimG(await downloadG());
  fs.writeFileSync(local, JSON.stringify(G));
  console.log(`G version ${G.version} saved as ${local}`);
  return G;
}
// endregion load-g

// region derived
// Tables that the live server computes from G at startup. We keep them apart
// from G so that /data.js serves G exactly as loaded.
//
// js/old_common_functions.js:157-258 (process_game_data):
// - merchants[map]: every NPC with an `items` list. `sell` works within 400 px
//   of any of them (node/server.js:8067-8071).
// - sellers[map][item]: the NPCs that sell `item` on that map. `buy` needs one
//   within 400 px (node/server.js:8426-8430). Items with `cash` are skipped
//   unless they are also `p2w` (js/old_common_functions.js:239-243).
// - canBuy: an item that any NPC sells (node/server.js:8420, "buy_cant_npc").
// - ref[map][npc id]: NPC positions; ref.upgrade/ref.compound is the
//   "newupgrade" NPC (js/old_common_functions.js:250-251).
// - charge: the chase speed of a monster (js/old_common_functions.js:160-167).
// node/server_functions.js:42-55 (sprocess_game_data): igrade and igrace of an item.
export function deriveTables(G) {
  const D = { merchants: {}, sellers: {}, ref: {}, canBuy: new Set(), charge: {}, igrade: {}, igrace: {} };
  for (const name in G.maps) {
    const map = G.maps[name];
    D.merchants[name] = [];
    D.sellers[name] = {};
    D.ref[name] = {};
    for (const npc of map.npcs || []) {
      if (!npc.position) continue; // NPCs with `positions` (walking ones) are not shops
      const coords = { map: name, in: name, x: npc.position[0], y: npc.position[1], id: npc.id };
      const data = G.npcs[npc.id];
      if (!data) continue;
      if (data.items) {
        D.merchants[name].push(coords);
        for (const item of data.items) {
          if (!item || !G.items[item]) continue;
          if (G.items[item].cash && !G.items[item].p2w) continue;
          (D.sellers[name][item] = D.sellers[name][item] || []).push(coords);
          D.canBuy.add(item);
        }
      }
      D.ref[name][npc.id] = coords;
      if (data.role === "newupgrade") D.ref[name].upgrade = D.ref[name].compound = coords;
      if (data.role === "exchange") D.ref[name].exchange = coords;
    }
  }
  for (const name in G.monsters) {
    const m = G.monsters[name];
    if (m.charge) D.charge[name] = m.charge;
    else if (m.speed >= 60) D.charge[name] = Math.round(m.speed * 1.2);
    else if (m.speed >= 50) D.charge[name] = Math.round(m.speed * 1.3);
    else if (m.speed >= 32) D.charge[name] = Math.round(m.speed * 1.4);
    else if (m.speed >= 20) D.charge[name] = Math.round(m.speed * 1.6);
    else if (m.speed >= 10) D.charge[name] = Math.round(m.speed * 1.7);
    else D.charge[name] = Math.round(m.speed * 2);
  }
  for (const name in G.items) {
    const def = G.items[name];
    const grade = itemGrade(def);
    D.igrade[name] = grade;
    D.igrace[name] = grade === 0 ? 1 : grade === 1 ? -1 : grade === 2 ? -2 : 0;
  }
  return D;
}
// endregion derived

// region distance
// The live hit box distance (js/old_common_functions.js:707-740): the gap between
// two boxes. A box is `width` wide, centered on x, and `height` tall above y.
// Monsters use G.dimensions[type] (default 24x24, js/old_common_functions.js:692);
// characters on the server are 26x36 (node/server.js:11782-11783).
export function boxDistance(a, b, G) {
  if (!a || !b) return 99999999;
  if ("in" in a && "in" in b && a.in !== b.in) return 99999999;
  if ("map" in a && "map" in b && a.map !== b.map) return 99999999;
  const [aw, ah] = dims(a, G);
  const [bw, bh] = dims(b, G);
  const dx = Math.max(b.x - bw / 2 - (a.x + aw / 2), a.x - aw / 2 - (b.x + bw / 2), 0);
  const dy = Math.max(b.y - bh - a.y, a.y - ah - b.y, 0);
  return Math.sqrt(dx * dx + dy * dy);
}

function dims(e, G) {
  if (e.is_monster) return monsterDims(e.type, G);
  return [e.width || 0, e.height || 0];
}

export function monsterDims(type, G) {
  const d = G.dimensions[type] || [24, 24];
  let [w, h] = d;
  if (G.monsters[type] && G.monsters[type].size) {
    w = Math.round(w * G.monsters[type].size);
    h = Math.round(h * G.monsters[type].size);
  }
  return [w, h];
}

// The point distance (js/old_common_functions.js:1197-1202). Used for NPCs,
// chests, the move correction and the transporter.
export function simpleDistance(a, b) {
  if (a.map && b.map && a.map !== b.map) return 9999999;
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
}

// The vision box (js/old_common_functions.js:682-689): an entity is in view if it
// is in the same instance and within vision[0] px in x and vision[1] px in y.
export function withinVision(observer, e) {
  if (observer.in !== e.in) return false;
  const [vx, vy] = observer.vision;
  return observer.x - vx < e.x && e.x < observer.x + vx && observer.y - vy < e.y && e.y < observer.y + vy;
}
// endregion distance

// region walls
// Does the straight segment a->b cross a wall line of G.geometry[map]?
// x_lines are [x, y1, y2] (a vertical wall at x), y_lines are [y, x1, x2].
// This is a point check. The live client checks the moving base box
// (can_move, js/old_common_functions.js:1499), so it stays a few px further from walls;
// a path that the live client accepts never fails here.
export function crossesWall(geometry, ax, ay, bx, by) {
  if (!geometry) return false;
  for (const [x, y1, y2] of geometry.x_lines || []) {
    if ((ax - x) * (bx - x) > 0 || ax === bx) continue;
    const t = (x - ax) / (bx - ax);
    const y = ay + (by - ay) * t;
    if (y >= y1 && y <= y2) return true;
  }
  for (const [y, x1, x2] of geometry.y_lines || []) {
    if ((ay - y) * (by - y) > 0 || ay === by) continue;
    const t = (y - ay) / (by - ay);
    const x = ax + (bx - ax) * t;
    if (x >= x1 && x <= x2) return true;
  }
  return false;
}
// endregion walls

// region damage
// js/old_common_functions.js:826-842: the share of damage that passes a defense
// (armor or resistance). 1 at 0 defense, lower with more, at least 0.05.
export function damageMultiplier(defense) {
  const { min, max } = Math;
  return min(
    1.32,
    max(
      0.05,
      1 -
        (max(0, min(100, defense)) * 0.001 +
          max(0, min(100, defense - 100)) * 0.001 +
          max(0, min(100, defense - 200)) * 0.00095 +
          max(0, min(100, defense - 300)) * 0.0009 +
          max(0, min(100, defense - 400)) * 0.00082 +
          max(0, min(100, defense - 500)) * 0.0007 +
          max(0, min(100, defense - 600)) * 0.0006 +
          max(0, min(100, defense - 700)) * 0.0005 +
          max(0, defense - 800) * 0.0004) +
        max(0, min(50, 0 - defense)) * 0.001 +
        max(0, min(50, -50 - defense)) * 0.00075 +
        max(0, min(50, -100 - defense)) * 0.0005 +
        max(0, -150 - defense) * 0.00025,
    ),
  );
}
// endregion damage

// region items
// js/old_common_functions.js:773-781: the grade (0-4) of an item at its level.
export function itemGrade(def, item) {
  if (!(def.upgrade || def.compound)) return 0;
  const level = (item && item.level) || 0;
  const g = def.grades || [9, 10, 11, 12];
  if (level >= g[3]) return 4;
  if (level >= g[2]) return 3;
  if (level >= g[1]) return 2;
  if (level >= g[0]) return 1;
  return 0;
}

// js/old_common_functions.js:877-1060 (calculate_item_properties), without
// titles (item.p) and class/map extras: the stats of an item at its level.
const PROP_KEYS = [
  "gold", "luck", "xp", "int", "str", "dex", "vit", "for", "charisma", "cuteness", "awesomeness", "bling",
  "hp", "mp", "attack", "range", "armor", "incdmgamp", "resistance", "pnresistance", "firesistance",
  "fzresistance", "phresistance", "stresistance", "stun", "blast", "explosion", "breaks", "stat", "speed",
  "level", "evasion", "miss", "reflection", "lifesteal", "manasteal", "attr0", "attr1", "rpiercing",
  "apiercing", "crit", "critdamage", "dreturn", "frequency", "mp_cost", "mp_reduction", "output",
  "courage", "mcourage", "pcourage",
];
const NO_ROUND = ["evasion", "miss", "reflection", "dreturn", "lifesteal", "manasteal", "attr0", "attr1", "crit", "critdamage", "set", "class", "breaks"];

export function itemProperties(item, G) {
  const def = G.items[item.name];
  const prop = {};
  for (const k of PROP_KEYS) prop[k] = 0;
  prop.set = null;
  prop.class = null;
  if (def.upgrade || def.compound) {
    const u = def.upgrade || def.compound;
    const level = item.level || 0;
    prop.level = level;
    for (let i = 1; i <= level; i++) {
      let m = 1;
      if (def.upgrade) m = { 7: 1.25, 8: 1.5, 9: 2, 10: 3, 11: 1.25, 12: 1.25 }[i] || 1;
      else m = i === 5 ? 1.25 : i === 6 ? 1.5 : i === 7 ? 2 : i >= 8 ? 3 : 1;
      for (const p in u) {
        if (p === "stat") prop[p] += Math.round(u[p] * m);
        else prop[p] = (prop[p] || 0) + u[p] * m;
        if (p === "stat" && i >= 7) prop.stat++;
      }
    }
  }
  for (const p in def) {
    if (prop[p] === null) prop[p] = def[p];
    else if (prop[p] !== undefined && typeof def[p] === "number") prop[p] += def[p];
  }
  for (const p in prop) if (!NO_ROUND.includes(p) && typeof prop[p] === "number") prop[p] = Math.round(prop[p]);
  return prop;
}

// js/old_common_functions.js:783-822 (calculate_item_value): the gold value.
// NPCs pay 60 % of G.items[x].g (`m` 0.6). A `gift` item is worth 1 gold.
export function itemValue(item, G, m) {
  if (!item) return 0;
  if (item.gift) return 1;
  const def = G.items[item.name] || G.items.placeholder_m;
  let value = (def.cash && def.g) || def.g * (m || 0.6);
  let divide = 1;
  if (def.markup) value /= def.markup;
  if (def.compound && item.level) {
    let grade = 0;
    const grades = def.grades || [11, 12];
    for (let i = 1; i <= item.level; i++) {
      if (i > grades[1]) grade = 2;
      else if (i > grades[0]) grade = 1;
      if (def.cash) value *= 1.5;
      else value *= 3.2;
      if (def.type !== "booster") value += G.items["cscroll" + grade].g / 2.4;
      else value *= 0.75;
    }
  }
  if (def.upgrade && item.level) {
    let grade = 0;
    let sValue = 0;
    const grades = def.grades || [11, 12];
    for (let i = 1; i <= item.level; i++) {
      if (i > grades[1]) grade = 2;
      else if (i > grades[0]) grade = 1;
      sValue += G.items["scroll" + grade].g / 2;
      if (i >= 7) (value *= 3), (sValue *= 1.32);
      else if (i === 6) value *= 2.4;
      else if (i >= 4) value *= 2;
      if (i === 9) (value *= 2.64), (value += 400000);
      if (i === 10) value *= 5;
      if (i === 12) value *= 0.8;
    }
    value += sValue;
  }
  if (item.expires) divide = 8;
  return Math.round(value / divide) || 0;
}

// node/server.js:1981-1991 (create_new_item)
export function newItem(name, quantity, G) {
  const item = { name };
  if (G.items[name].s) item.q = quantity || 1;
  if (G.items[name].upgrade || G.items[name].compound) item.level = 0;
  return item;
}

// node/server_functions.js:4190-4258 (cache_item): the copy of an item that a
// client sees. These fields stay on the server.
const ITEM_HIDDEN = { grace: 1, giveaway: 1, gf: 1, price: 1, want: 1, b: 1, rid: 1, list: 1, o: 1, oo: 1, src: 1 };
export function cacheItem(item) {
  if (!item) return null;
  const out = {};
  for (const p in item) if (!ITEM_HIDDEN[p]) out[p] = item[p];
  return out;
}

// js/old_common_functions.js:407-420 (can_stack)
export function canStack(a, b, G, extra = 0) {
  if (!(a && b && a.name && G.items[a.name].s && a.name === b.name)) return false;
  const max = G.items[a.name].s === true ? 9999 : G.items[a.name].s;
  if ((a.q || 1) + (b.q || 1) + extra > max) return false;
  if ((a.p || b.p) && a.p !== b.p) return false;
  if (a.l || b.l || a.b || b.b) return false;
  return true;
}
// endregion items

// region equip
// node/server.js:1841-1949 (can_equip_item): the slot an item goes to, or "no".
export function canEquipItem(player, def, slot, G) {
  const cls = G.classes[player.type];
  if (!slot) slot = def.type;
  if (slot === "offhand" && def.type !== "weapon") slot = def.type;
  if (def.type === "tool") slot = "mainhand";
  const allowed = ["helmet", "pants", "chest", "weapon", "amulet", "earring", "shoes", "gloves", "ring", "shield", "belt", "source", "orb", "quiver", "cape", "misc_offhand", "tool"];
  if (!allowed.includes(def.type)) return "no";
  if (slot !== def.type && ["shield", "source", "quiver", "misc_offhand"].includes(def.type) && slot !== "offhand") return "no";
  const mainDef = player.slots.mainhand && G.items[player.slots.mainhand.name];
  const twoHanded = mainDef && cls.doublehand[mainDef.wtype];
  if (["weapon", "mainhand", "offhand", "tool"].includes(slot)) {
    if (slot === "weapon" && mainDef && cls.mainhand[mainDef.wtype] && !player.slots.offhand && cls.offhand[def.wtype]) {
      slot = "offhand";
    } else if (slot === "offhand" && (!mainDef || cls.mainhand[mainDef.wtype]) && cls.offhand[def.wtype]) {
      slot = "offhand";
    } else if (slot === "weapon" || slot === "mainhand") {
      if (cls.doublehand[def.wtype] && !player.slots.offhand) {
        // a two-handed weapon with a free offhand: fine
      } else if (!cls.mainhand[def.wtype]) {
        return "no";
      }
      slot = "mainhand";
    } else {
      return "no";
    }
  } else if (def.type === "shield" || def.type === "misc_offhand") {
    if (cls.offhand[def.type] && !twoHanded) slot = "offhand";
    else return "no";
  } else if (def.type === "quiver") {
    if (cls.offhand.quiver && !twoHanded) slot = "offhand";
    else return "no";
  } else if (def.type === "source") {
    if (cls.offhand.source && !twoHanded) slot = "offhand";
    else return "no";
  } else if (def.type === "ring") {
    if (slot !== "ring1" && slot !== "ring2") slot = player.slots.ring1 ? "ring2" : "ring1";
  } else if (def.type === "earring") {
    if (slot !== "earring1" && slot !== "earring2") slot = player.slots.earring1 ? "earring2" : "earring1";
  } else if (slot !== def.type) {
    return "no";
  }
  return slot;
}

// js/old_common_functions.js:104: the slots that give stats.
export const CHARACTER_SLOTS = ["ring1", "ring2", "earring1", "earring2", "belt", "mainhand", "offhand", "helmet", "chest", "pants", "shoes", "gloves", "amulet", "orb", "elixir", "cape"];
// endregion equip
