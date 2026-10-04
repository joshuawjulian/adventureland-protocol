// gdata.js: the game data G (items, monsters, maps, skills, ...). Download it
// once per game version and keep it in a cache file on disk.
// Node.js 22.18+. No packages.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { baseUrl } from "./api.js";

// region types
// G is a large JSON object. JavaScript reads it as it is: G.items.hpot0,
// G.monsters.goo, G.skills.attack. The course reads only a few fields of it.
/** @typedef {Record<string, any>} G */
// endregion types

// region fetch-version
// The version is in the page /hub as `var VERSION='17478'`
// (htmls/base_script.html:32). Returns null if the page changed its shape;
// then the caller downloads G.
/** @param {string} base @returns {Promise<number | null>} */
export async function fetchVersion(base) {
  const res = await fetch(`${base}/hub`);
  if (!res.ok) return null;
  const m = /var\s+VERSION\s*=\s*'(\d+)/.exec(await res.text());
  return m ? Number(m[1]) : null;
}
// endregion fetch-version

// region download-g
// /data.js is JavaScript, not JSON: `var G={...};`. The JSON is the text from
// the first "{" to the last "}" (web_assets.js:52 writes "var G=" + JSON + ";").
/** @param {string} base @returns {Promise<G>} */
export async function downloadG(base) {
  const res = await fetch(`${base}/data.js`);
  if (!res.ok) throw new Error(`data.js: HTTP ${res.status}`);
  const js = await res.text();
  return JSON.parse(js.slice(js.indexOf("{"), js.lastIndexOf("}") + 1));
}
// endregion download-g

// One folder per website, so that the small G of the test server never mixes
// with the live G: .al-cache/<host>/G_<version>.json. A ":" (before a port) is
// not allowed in a Windows file name, so it becomes "_".
/** @param {string} base @param {number | null} version */
export function cachePath(base, version) {
  const host = new URL(base).host.replaceAll(":", "_");
  return join(".al-cache", host, `G_${version}.json`);
}

// region load-g
// G is about 2.8 MB and changes only with the game version. Ask for the
// version first (a small page); download G only if the cache does not have it.
/** @param {string} [base] @returns {Promise<G>} */
export async function loadG(base = baseUrl()) {
  const version = await fetchVersion(base);
  if (version !== null) {
    const file = cachePath(base, version);
    if (existsSync(file)) return JSON.parse(readFileSync(file, "utf8"));
  }
  const G = await downloadG(base);
  const file = cachePath(base, G.version);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, JSON.stringify(G));
  console.log(`downloaded G version ${G.version}`);
  return G;
}
// endregion load-g
