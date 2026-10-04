// server.js: one fake Adventure Land for the whole course. It is NOT the game.
//
// On one port (TEST_PORT, default 8022):
//   - the HTTP API: /api/signup_or_login, /api/servers_and_characters,
//     /api/get_servers, /api/create_character; /data.js (G); /hub (VERSION)
//   - two game servers, Socket.IO v4: "EU I" at /ws1/ and "US I" at /ws2/.
//     Each one has its own world (world.js).
//   - a plain WebSocket echo at /echo (text and binary)
//   - test control: POST /test/reset, POST /test/drop?character=Name,
//     GET /test/stats
//
// It copies the payload shapes of the live game for what the course uses.
// The live code is vendor/adventureland_mongodb (node/server.js and others);
// each handler cites the lines it copies. docs/COURSE.md, "The local test
// server", is the contract.
//
//   npm install                  (once; socket.io 4.8.1 and ws 8.18.0)
//   node server.js
//
// Settings: environment variables, all optional, prefixed TEST_ so that they
// never clash with the AL_ variables of the programs.

import http from "node:http";
import { Server } from "socket.io";
import { WebSocketServer } from "ws";
import { loadG, deriveTables } from "./g.js";
import { Accounts } from "./accounts.js";
import { World } from "./world.js";
import { makeHttpHandler } from "./http.js";

const env = process.env;
const flag = (v) => !!v && v !== "0" && v.toLowerCase() !== "false";

// region settings
const settings = {
  port: Number(env.TEST_PORT || 8022),
  // The live values (node/server.js:83-84). Lower values show a missing pong sooner.
  pingInterval: Number(env.TEST_PING_INTERVAL || 4000),
  pingTimeout: Number(env.TEST_PING_TIMEOUT || 12000),
  gFile: env.TEST_G_FILE || "",
  // Drop each character's socket once, this long after `start` (0: off).
  dropAfterMs: Number(env.TEST_DROP_AFTER_MS || 0),
  // After a character's socket closes, `auth` for it gets "Authorization in
  // progress" for this long (the live save delay, dc_players).
  saveMs: Number(env.TEST_SAVE_MS || 0),
  // The respawn wait (B.rip_time, node/server.js:224).
  ripMs: Number(env.TEST_RIP_MS || 12000),
  // A multiplier for monster damage, to test potions and death.
  damage: Number(env.TEST_DAMAGE || 1),
  quiet: flag(env.TEST_QUIET),
};
// endregion settings

// The two game servers. Live lists servers in the order EU, US, ASIA
// (adventure_functions.js:679-684). time_offset: hours from UTC of the region
// (node/server.js:339-343). msgpack_path: the live list has it
// ("/ws<n>-msgpack/", node/test/cloudflare_servers.test.js:51-52); the test
// server lists it but does not serve it.
const SERVERS = [
  { key: "EUI", region: "EU", name: "I", path: "/ws1/", msgpackPath: "/ws1-msgpack/", timeOffset: 1 },
  { key: "USI", region: "US", name: "I", path: "/ws2/", msgpackPath: "/ws2-msgpack/", timeOffset: -5 },
];

function newStats() {
  return {
    started: new Date().toISOString(),
    http: 0, api: 0, data_js: 0, logins: 0, created: 0,
    connections: 0, auths: 0, auth_failed: 0, auth_in_progress: 0, starts: 0,
    moves: 0, violations: 0, jails: 0, transports: 0,
    attacks: 0, too_far: 0, cooldown: 0, not_there: 0, hits: 0, kills: 0, levelups: 0,
    chests_dropped: 0, chests: 0, deaths: 0, respawns: 0,
    potions: 0, regens: 0, equips: 0, unequips: 0, buys: 0, sells: 0, sends: 0,
    invites: 0, party_joins: 0, upgrades: 0, compounds: 0,
    updates: 0, maxcc: 0, limitdc: 0, drops: 0, errors: 0,
  };
}

const G = await loadG(settings.gFile);
const ctx = {
  G,
  D: deriveTables(G),
  accounts: new Accounts(G),
  settings,
  stats: newStats(),
  dropped: new Set(), // the characters that TEST_DROP_AFTER_MS already dropped
  armed: [], // [{name, action: "drop" | "jail", ms}]: test controls that wait for `start`
  worlds: [],
};
ctx.worlds = SERVERS.map((def) => new World(def, ctx));
// POST /test/reset: all worlds and the account back to the start, and new counters.
ctx.resetAll = () => {
  for (const w of ctx.worlds) w.resetAll();
  ctx.accounts.reset();
  ctx.dropped.clear();
  ctx.armed = [];
  Object.assign(ctx.stats, newStats());
  console.log("TEST RESET: worlds, account and counters are back to the start");
};

const httpServer = http.createServer(makeHttpHandler(ctx));

// region socket-io
// One Socket.IO server per game server, on the same HTTP server, as live has
// two (JSON and MessagePack) per process (node/server.js:80-98).
// destroyUpgrade: false. By default engine.io closes every WebSocket upgrade
// that is not for its own path after 1 s. With two servers and /echo on one
// HTTP server, that would kill the other upgrades. The "upgrade" handler below
// closes the upgrades that nobody takes.
for (const world of ctx.worlds) {
  const io = new Server(httpServer, {
    path: world.path,
    pingInterval: settings.pingInterval,
    pingTimeout: settings.pingTimeout,
    serveClient: false,
    destroyUpgrade: false,
    cors: { origin: true, credentials: true },
  });
  io.on("connection", (socket) => world.connect(socket));
  world.io = io;
}
// endregion socket-io

// region echo
// A plain WebSocket echo at /echo: each text or binary message comes back as
// the same type. The course uses it before it talks to a game server.
const echo = new WebSocketServer({ noServer: true });
echo.on("connection", (ws) => {
  ws.on("message", (data, isBinary) => ws.send(data, { binary: isBinary }));
});
httpServer.on("upgrade", (req, socket, head) => {
  const path = new URL(req.url, "http://localhost").pathname;
  if (path === "/echo") {
    echo.handleUpgrade(req, socket, head, (ws) => echo.emit("connection", ws, req));
    return;
  }
  // engine.io takes the upgrades of its own path (the same "upgrade" event).
  if (ctx.worlds.some((w) => req.url.startsWith(w.path))) return;
  socket.destroy();
});
// endregion echo

httpServer.listen(settings.port, () => {
  console.log(`test server on http://localhost:${settings.port} (G version ${G.version})`);
  for (const w of ctx.worlds) console.log(`  ${w.region} ${w.name}: ws://localhost:${settings.port}${w.path}?EIO=4&transport=websocket`);
  console.log(`  echo: ws://localhost:${settings.port}/echo`);
  console.log(`  settings: ${JSON.stringify(settings)}`);
});

// Stop at once on Ctrl-C and `docker stop`.
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => process.exit(0));
