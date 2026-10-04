// trim-g.js: make the game data G smaller for the test server.
//
// The live /data.js is about 3.5 MB. Most of it is art (sprites, tilesets,
// images, animations) and map geometry for maps that the test server does not
// have. The course programs and this server read only the tables in KEEP_TABLES,
// and the geometry of the maps in GEOMETRY_MAPS. Everything else goes.
//
//   node trim-g.js <in> <out>     in: a G.json or a data.js ("var G={...};")
//   node trim-g.js                downloads https://adventure.land/data.js and writes G.json
//
// server.js uses the same trimG() when it loads G, so a full G (for example
// vendor/G/G_17478.json) and a trimmed G.json give the same /data.js.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// The tables that stay. Each one is used by a course program or by this server:
// - items, monsters, npcs, skills, classes, conditions, levels, dimensions,
//   projectiles: entity defaults, ranges, cooldowns, stats, hit boxes.
// - maps (all of them; small) and geometry (below): doors, spawns, walls.
// - upgrades, compounds: the chance tables of upgrade and compound.
// - sets, titles: item stats and stacking rules (titles: can_stack).
// - drops, monster_gold: chest gold and loot.
// - craft, dismantle, tokens, achievements, multipliers: small; kept so that
//   code that looks them up finds an object.
// `version` always stays: /hub and `welcome` send it, and clients cache G by it.
export const KEEP_TABLES = [
  "version",
  "achievements",
  "monsters",
  "maps",
  "geometry",
  "npcs",
  "items",
  "sets",
  "craft",
  "titles",
  "tokens",
  "dismantle",
  "conditions",
  "projectiles",
  "classes",
  "dimensions",
  "levels",
  "upgrades",
  "compounds",
  "monster_gold",
  "skills",
  "multipliers",
  "drops",
];
// Dropped on purpose (big, and nothing in the course reads them): sprites,
// animations, tilesets, imagesets, images, positions, cosmetics, docs, events,
// games. A key that is not in KEEP_TABLES is dropped too, so a newer G with new
// tables still trims.

// The maps that the test server simulates (one instance each, see world.js).
// main: the world of the course. bank: the door test. jail: the wall test.
// woffice: a main door leads there, and respawn with `safe` goes there live.
// Geometry for other maps is dropped (main geometry alone is about 300 KB).
export const GEOMETRY_MAPS = ["main", "bank", "jail", "woffice"];

// Parse G from the text of a G.json or of a data.js. data.js is "var G={...};"
// so the JSON is the text from the first "{" to the last "}".
export function parseGText(text) {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end < start) throw new Error("no JSON object in the G text");
  return JSON.parse(text.slice(start, end + 1));
}

// Return a new, trimmed G. It does not change the input.
export function trimG(G) {
  const out = {};
  for (const key of KEEP_TABLES) {
    if (key === "geometry") continue; // below
    if (G[key] !== undefined) out[key] = G[key];
  }
  out.geometry = {};
  for (const map of GEOMETRY_MAPS) {
    if (G.geometry && G.geometry[map]) out.geometry[map] = G.geometry[map];
  }
  return out;
}

// The live game data. Public, no login needed.
export const DATA_URL = "https://adventure.land/data.js";

export async function downloadG() {
  const res = await fetch(DATA_URL);
  if (res.status !== 200) throw new Error(`GET ${DATA_URL}: status ${res.status}`);
  return parseGText(await res.text());
}

// Command line use.
const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const [input, output] = process.argv.slice(2);
  const here = path.dirname(fileURLToPath(import.meta.url));
  const G = input ? parseGText(fs.readFileSync(input, "utf8")) : await downloadG();
  const trimmed = trimG(G);
  const target = output || path.join(here, "G.json");
  fs.writeFileSync(target, JSON.stringify(trimmed));
  console.log(`wrote ${target}: G version ${trimmed.version}, ${JSON.stringify(trimmed).length} bytes`);
}
