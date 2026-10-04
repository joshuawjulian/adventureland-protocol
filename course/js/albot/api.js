// api.js: the HTTP side of Adventure Land: log in, read the lists of game
// servers and characters, and make the WebSocket URL of a game server.
// Node.js 22.18+ (fetch is built in). No packages.

/** @typedef {{user: string, auth: string}} Auth  the session: "<user>-<auth>" in two parts */
/** @typedef {{name: string, region: string, players: number, key: string, address: string, path: string}} Server */
/** @typedef {{id: string, name: string, type: string, level: number, online: number, server?: string}} Character */

// The website and its HTTP API (not a game server). AL_BASE_URL changes it,
// for example to the local test server, http://localhost:8022.
export function baseUrl() {
  return (process.env.AL_BASE_URL || "https://adventure.land").replace(/\/+$/, "");
}

// region api-call
// Each API call is a POST of a JSON object to /api/<method>
// (common_engine/handlers.js). The reply is HTTP 200 with a JSON object, also
// when the call fails: then it has `failed: true` and a `reason`. Extra replies
// come in the list `infs`.
/**
 * @param {string} method
 * @param {object} [body]
 * @param {Auth | null} [auth]  after the login: the session cookie
 * @returns {Promise<any>}
 */
export async function apiCall(method, body = {}, auth = null) {
  /** @type {Record<string, string>} */
  const headers = { "Content-Type": "application/json" };
  // The server reads the session from the cookie "auth=<user>-<auth>".
  if (auth) headers.Cookie = `auth=${auth.user}-${auth.auth}`;
  const res = await fetch(`${baseUrl()}/api/${method}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  // Not 200: a network or server problem, not a game answer.
  if (res.status !== 200) throw new Error(`${method}: HTTP ${res.status}`);
  return res.json();
}
// endregion api-call

// "<user>-<auth>" -> {user, auth}. Split at the FIRST dash: the user id
// ("US_...") has no dash, the token may get one in the future.
/** @param {string} text @returns {Auth} */
export function parseAuth(text) {
  const dash = text.indexOf("-");
  if (dash < 0) throw new Error("AL_AUTH must look like <user>-<auth>");
  return { user: text.slice(0, dash), auth: text.slice(dash + 1) };
}

// region login
// Returns the session. If AL_AUTH is set, it uses AL_AUTH and sends no
// password. Only if AL_AUTH is empty does it log in with AL_EMAIL and
// AL_PASSWORD, and then it prints the AL_AUTH value to save. Each password
// login adds a token to the account (200 at most; the next login after that
// deletes all of them), so log in with the password one time only.
/** @returns {Promise<Auth>} */
export async function login() {
  const saved = process.env.AL_AUTH;
  if (saved) return parseAuth(saved);

  const email = process.env.AL_EMAIL;
  const password = process.env.AL_PASSWORD;
  if (!email || !password) throw new Error("set AL_AUTH, or AL_EMAIL and AL_PASSWORD");
  // only_login: true: never make a new account by mistake.
  const data = await apiCall("signup_or_login", { email, password, only_login: true });
  // Success: {success: true, user, auth, ...}. Failure: {failed: true, reason}.
  if (data.success !== true) throw new Error(`login failed: ${data.reason ?? "unknown reason"}`);

  const value = `${data.user}-${data.auth}`;
  console.log("Logged in with the password. Save this value, and use it from now on:");
  console.log(`  export AL_AUTH='${value}'`); // bash, zsh
  console.log(`  PowerShell: $env:AL_AUTH = '${value}'`); // Windows
  return { user: data.user, auth: data.auth };
}
// endregion login

// region servers-and-characters
// The two lists come in the `infs` item of type "servers_and_characters".
/**
 * @param {Auth} auth
 * @returns {Promise<{servers: Server[], characters: Character[]}>}
 */
export async function serversAndCharacters(auth) {
  const data = await apiCall("servers_and_characters", {}, auth);
  if (data.failed && data.reason === "not_logged_in") {
    throw new Error("the token in AL_AUTH is not valid any more. Unset AL_AUTH and log in with the password again.");
  }
  if (data.failed) throw new Error(`servers_and_characters failed: ${data.reason}`);
  const info = data.infs?.find((/** @type {any} */ inf) => inf.type === "servers_and_characters");
  if (!info) throw new Error("unexpected reply: " + JSON.stringify(data).slice(0, 200));
  return { servers: info.servers, characters: info.characters };
}
// endregion servers-and-characters

// region find-server
// `key` is region + name, for example "EUI" (the list's own `key` field is the
// database id, "SR_EUI"). Empty: the first server of the list (EU, US, ASIA).
/**
 * @param {Server[]} servers
 * @param {string} [key]
 * @returns {Server}
 */
export function findServer(servers, key = process.env.AL_SERVER ?? "") {
  if (!key) {
    if (!servers.length) throw new Error("the server list is empty");
    return servers[0];
  }
  const server = servers.find((s) => s.region + s.name === key);
  if (!server) throw new Error(`no server ${key}; the list has: ${servers.map((s) => s.region + s.name).join(", ")}`);
  return server;
}
// endregion find-server

// The character with this name (not the "CH_" id). Names are exact.
/**
 * @param {Character[]} characters
 * @param {string} [name]
 * @returns {Character}
 */
export function findCharacter(characters, name = process.env.AL_CHARACTER ?? "") {
  if (!name) throw new Error("set AL_CHARACTER to the name of a character (run login.js to see them)");
  const character = characters.find((c) => c.name === name);
  if (!character) throw new Error(`no character named "${name}"; the list has: ${characters.map((c) => c.name).join(", ")}`);
  return character;
}

// region socket-url
// The WebSocket URL of a game server. The scheme follows the website:
// http -> ws (the test server), https -> wss (the live game). The path must
// end with exactly one "/" (the server matches "/ws1/"). The two options are
// the ones that the browser also sends (js/game.js:1525):
//   map_protocol=1: we accept generated maps. Without it, the server throws
//                   "client_update_required" when it sends us one.
//   no_graphics=1:  send generated maps without tile data. A bot needs no tiles.
/**
 * @param {Server} server
 * @param {string} [base]
 */
export function socketUrl(server, base = baseUrl()) {
  const scheme = base.startsWith("https:") ? "wss" : "ws";
  const path = server.path.replace(/\/*$/, "/");
  return `${scheme}://${server.address}${path}?EIO=4&transport=websocket&map_protocol=1&no_graphics=1`;
}
// endregion socket-url
