// gdata.ts: the game data G. Download it once per game version, keep it in a
// cache file, and read it as typed data.
// Uses the global `fetch` and node:fs of Node.js 22. No packages.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { baseUrl } from "./api.ts";

// region types
// Typed views of the G tables that the course reads. Only the fields that we
// use; G has many more (see the G reference). The other tables stay `unknown`.

/** G.items[name]: one item definition. */
export interface ItemDef {
  name: string; // the display name
  type: string; // "weapon", "pot", "material", ...
  g: number; // the base value in gold (also the NPC price)
  s?: number; // the largest stack; absent = the item does not stack
  gives?: [stat: string, amount: number][]; // potions: what one potion adds
  cooldown?: number; // ms
  compound?: Record<string, number>; // the stats that each compound level adds; present: the item compounds (jewelry)
  upgrade?: Record<string, number>; // the stats that each upgrade level adds; present: the item upgrades
}

/** G.monsters[type]: the base stats of a monster type. */
export interface MonsterDef {
  name: string;
  hp: number;
  mp?: number;
  attack: number;
  speed: number; // px per second
  range: number; // px
  frequency: number; // attacks per second
  xp: number;
  respawn: number; // SECONDS (most other durations are ms); -1 = never by itself
  damage_type: "physical" | "magical" | "pure";
  size?: number; // multiplies the hit box of G.dimensions[type]
}

/** G.skills[name]: a skill or ability. */
export interface SkillDef {
  name: string;
  type?: string;
  cooldown?: number; // ms
  mp?: number;
  range?: number;
  share?: string; // this skill uses the cooldown of that other skill
  class?: string[];
  level?: number;
}

/** The whole object. */
export interface GData {
  version: number;
  items: Record<string, ItemDef>;
  monsters: Record<string, MonsterDef>;
  skills: Record<string, SkillDef>;
  dimensions: Record<string, number[]>; // [width, height, ...] of a sprite or monster type
  [table: string]: unknown; // maps, geometry, npcs, ...: read them as unknown and check
}
// endregion types

// region fetch-version
// The version is in the game page /hub as `var VERSION='17478'`
// (htmls/base_script.html:32). null when the page has no version.
export async function fetchVersion(base: string): Promise<number | null> {
  const res = await fetch(`${base}/hub`);
  if (!res.ok) return null;
  const m = /var\s+VERSION\s*=\s*'(\d+)'/.exec(await res.text());
  return m ? Number(m[1]) : null;
}
// endregion fetch-version

// region download-g
// /data.js is JavaScript, `var G={...};`, not JSON. The JSON is the text from
// the first "{" to the last "}".
export async function downloadG(base: string): Promise<GData> {
  const res = await fetch(`${base}/data.js`);
  if (!res.ok) throw new Error(`data.js: HTTP ${res.status}`);
  const js = await res.text();
  return JSON.parse(js.slice(js.indexOf("{"), js.lastIndexOf("}") + 1)) as GData;
}
// endregion download-g

/**
 * .al-cache/<host>/G_<version>.json. <host> is the host and port of `base`, with
 * ":" changed to "_" (a ":" is not allowed in a Windows file name). One folder per
 * host, so that the small G of the test server never mixes with the live G.
 */
export function cachePath(base: string, version: number): string {
  const host = new URL(base).host.replaceAll(":", "_");
  return join(".al-cache", host, `G_${version}.json`);
}

// region load-g
// G is about 2.8 MB and changes only with the game version. So ask for the
// version (a small page) first, and download G only when the cache has no
// file for that version. The cache folder is relative to the folder where you
// run the program.
export async function loadG(base: string = baseUrl()): Promise<GData> {
  const version = await fetchVersion(base);
  if (version !== null) {
    const file = cachePath(base, version);
    if (existsSync(file)) return JSON.parse(readFileSync(file, "utf8")) as GData;
  }
  const G = await downloadG(base);
  const file = cachePath(base, G.version); // G knows its own version
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, JSON.stringify(G));
  console.log(`downloaded G version ${G.version}`);
  return G;
}
// endregion load-g
