// servers.ts: get the list of game servers and print a socket URL for each.
// Standalone: it uses no file of the albot library. Node.js 22.18+, no packages.
// Run: node servers.ts   (test server: AL_BASE_URL=http://localhost:8022 node servers.ts)

// The shape of one server in the reply of get_servers (api.js:884-900).
// Only the fields that we use; the reply has more.
interface Server {
  region: string; // "EU", "US", "ASIA"
  name: string; // "I", "II", "PVP", ...
  address: string; // the host (and port) of the WebSocket, e.g. "eu1.adventure.land"
  path: string; // the Socket.IO path on that host, e.g. "/ws1/"
}
interface ServerList {
  success?: boolean;
  servers: Server[];
}

// The website and its HTTP API, without a final "/". The real game by default.
const base = (process.env.AL_BASE_URL || "https://adventure.land").replace(/\/+$/, "");

// get_servers is public: no login, so a plain GET works.
const res = await fetch(`${base}/api/get_servers`);
console.log(`status: ${res.status} ${res.headers.get("content-type")}`); // 200 = OK
if (!res.ok) throw new Error(`HTTP ${res.status}`);

const body = (await res.json()) as ServerList; // a promise to the compiler, not a check
// The socket uses the scheme of the website: http -> ws, https -> wss.
const scheme = base.startsWith("https:") ? "wss" : "ws";
for (const s of body.servers) {
  // The path must end with exactly one "/" (the server matches "/ws1/").
  const path = s.path.replace(/\/*$/, "/");
  // map_protocol=1 and no_graphics=1: the options that the browser client also sends (js/game.js:1525).
  console.log(`${s.region} ${s.name}: ${scheme}://${s.address}${path}?EIO=4&transport=websocket&map_protocol=1&no_graphics=1`);
}
