// api.ts: the HTTP API of Adventure Land: log in, list the servers and the
// characters, and make the WebSocket URL of a game server.
// Uses only the global `fetch` of Node.js 22. No packages.

/** Your session. On the wire, it is the cookie auth=<user>-<auth>. */
export interface Auth {
  user: string; // the user id, "US_..."
  auth: string; // the auth token, 64 hex characters
}

/** One game server, from servers_and_characters (adventure_functions.js:761-776). */
export interface Server {
  key: string; // the database id, "SR_EUI"
  region: string; // "EU", "US", "ASIA"
  name: string; // "I", "II", "PVP", ...
  players: number;
  address: string; // the host (and port) of the WebSocket
  path: string; // the Socket.IO path on that host, for example "/ws1/"
  msgpack_path?: string; // the MessagePack endpoint (not used in this course)
}

/** One of your characters (adventure_functions.js:821-843, character_to_dict). */
export interface Character {
  id: string; // "CH_...": the socket `auth` event needs this, not the name
  name: string;
  type: string; // the class: "warrior", "merchant", ...
  level: number;
  online: number; // 0 when offline, else ms since the login
  server?: string; // "SR_EUI", only while online
  rip?: boolean | string; // only while dead
  map: string;
  in: string;
  x: number;
  y: number;
}

/** One item of `infs`, the list of extra replies of an API call. */
export interface Inf {
  type: string; // "servers_and_characters", "message", "eval", ...
  servers?: Server[];
  characters?: Character[];
  [field: string]: unknown;
}

/** Every API reply. A failed call has `failed: true` and a `reason`, also with HTTP 200. */
export interface ApiReply {
  success?: boolean;
  failed?: boolean;
  reason?: string;
  infs?: Inf[];
  [field: string]: unknown;
}

/** The reply to signup_or_login (api.js:84-133). */
interface LoginReply extends ApiReply {
  user?: string; // "US_...", only on success
  auth?: string; // the new token, only on success
}

/** AL_BASE_URL, or the real game. Without a final "/", so that `${base}/api/...` is correct. */
export function baseUrl(): string {
  return (process.env.AL_BASE_URL || "https://adventure.land").replace(/\/+$/, "");
}

// region api-call
// Each API call is a POST of a JSON object to /api/<method>, the way ALClient
// does it on the live game. The reply is HTTP 200 with a JSON object, also when
// the call fails (then it has `failed: true` and a `reason`). So an HTTP status
// other than 200 means a problem of the network or of the server, not of the call.
export async function apiCall<T extends object = ApiReply>(
  method: string,
  body: object = {},
  auth: Auth | null = null,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  // The session is a cookie. A program has no cookie jar, so it sends the header itself.
  if (auth) headers.Cookie = `auth=${auth.user}-${auth.auth}`;
  const res = await fetch(`${baseUrl()}/api/${method}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (res.status !== 200) throw new Error(`${method}: HTTP ${res.status}`);
  // `as T` is a promise to the compiler, not a check: the caller reads `failed` first.
  return (await res.json()) as T;
}
// endregion api-call

/** Splits "<user>-<auth>" at the first "-". The user id has no "-"; the token has none either. */
export function parseAuth(text: string): Auth {
  const dash = text.indexOf("-");
  if (dash < 0) throw new Error("AL_AUTH must look like <user>-<auth>");
  return { user: text.slice(0, dash), auth: text.slice(dash + 1) };
}

// region login
// Uses AL_AUTH when it is set, and then sends no password. Only when AL_AUTH is
// empty does it log in with AL_EMAIL and AL_PASSWORD, and then it prints the
// AL_AUTH value to save. Each password login adds a token to the account, and
// the account keeps 200 at most, so do not log in with the password each time.
export async function login(): Promise<Auth> {
  const saved = process.env.AL_AUTH;
  if (saved) return parseAuth(saved);

  const email = process.env.AL_EMAIL;
  const password = process.env.AL_PASSWORD;
  if (!email || !password) throw new Error("set AL_AUTH, or AL_EMAIL and AL_PASSWORD");

  // only_login: true: never make a new account by accident (api.js:93).
  const r = await apiCall<LoginReply>("signup_or_login", { email, password, only_login: true });
  if (r.success !== true || !r.user || !r.auth) {
    throw new Error(`login failed: ${r.reason ?? "no user or auth in the reply"}`);
  }
  const value = `${r.user}-${r.auth}`;
  console.log("Logged in with the password. Save this value, and use it from now on:");
  console.log(`  export AL_AUTH='${value}'`); // bash, zsh
  console.log(`  PowerShell: $env:AL_AUTH = '${value}'`);
  return { user: r.user, auth: r.auth };
}
// endregion login

// region servers-and-characters
// The lists come in `infs`, as the item with type "servers_and_characters"
// (api.js:451-472). The call needs the session cookie.
export async function serversAndCharacters(auth: Auth): Promise<{ servers: Server[]; characters: Character[] }> {
  const r = await apiCall("servers_and_characters", {}, auth);
  if (r.failed && r.reason === "not_logged_in") {
    throw new Error("the token in AL_AUTH is not valid any more. Unset AL_AUTH and log in with the password again.");
  }
  if (r.failed) throw new Error(`servers_and_characters failed: ${r.reason}`);
  const info = r.infs?.find((inf) => inf.type === "servers_and_characters");
  if (!info?.servers || !info.characters) {
    throw new Error("unexpected reply: " + JSON.stringify(r).slice(0, 200));
  }
  return { servers: info.servers, characters: info.characters };
}
// endregion servers-and-characters

// region find-server
// AL_SERVER is region + name, for example "EUI" (`key` is the database id, "SR_EUI").
// Empty means the first server of the list; the list is in the order EU, US, ASIA.
export function findServer(servers: Server[], key: string = process.env.AL_SERVER ?? ""): Server {
  const all = servers.map((s) => s.region + s.name);
  const found = key ? servers.find((s) => s.region + s.name === key) : servers[0];
  if (!found) throw new Error(`no server ${key}; the list has: ${all.join(", ")}`);
  return found;
}
// endregion find-server

/** AL_CHARACTER is the name (not the "CH_" id). It must match exactly. */
export function findCharacter(characters: Character[], name: string = process.env.AL_CHARACTER ?? ""): Character {
  if (!name) throw new Error("set AL_CHARACTER to the name of one of your characters (run login.ts for the list)");
  const found = characters.find((c) => c.name === name);
  if (!found) {
    throw new Error(`no character ${name}; the list has: ${characters.map((c) => c.name).join(", ")}`);
  }
  return found;
}

// region socket-url
// ws(s)://<address><path>?EIO=4&transport=websocket, plus the two options that
// the browser client also sends (js/game.js:1525):
//   map_protocol=1: we accept generated maps (without it, the live server
//     throws "client_update_required", node/logic/generated_maps.js:186).
//   no_graphics=1: send generated maps without tile data.
// The scheme follows AL_BASE_URL: http -> ws (test server), https -> wss (live).
export function socketUrl(server: Server, base: string = baseUrl()): string {
  const scheme = base.startsWith("https:") ? "wss" : "ws";
  // The server matches the path with exactly one final "/" ("/ws1/").
  const path = server.path.replace(/\/*$/, "/");
  return `${scheme}://${server.address}${path}?EIO=4&transport=websocket&map_protocol=1&no_graphics=1`;
}
// endregion socket-url
