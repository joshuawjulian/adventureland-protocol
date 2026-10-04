// servers.js: get the list of game servers and make a socket URL for each.
// Standalone: it uses no file of the library. Node.js 22.18+, no packages.
// Run: node servers.js   (AL_BASE_URL=http://localhost:8022 for the test server)
const base = (process.env.AL_BASE_URL || "https://adventure.land").replace(/\/+$/, "");

// get_servers is public: no login (api.js:884-900).
const res = await fetch(`${base}/api/get_servers`);
console.log("status:", res.status, res.headers.get("content-type")); // 200 = OK
if (!res.ok) throw new Error(`HTTP ${res.status}`);

/** @type {any} */
const body = await res.json(); // read the body and parse it as JSON
// The socket scheme follows the website: http -> ws, https -> wss.
const scheme = base.startsWith("https:") ? "wss" : "ws";
for (const s of body.servers) {
  // The path must end with exactly one "/" (the server matches "/ws1/").
  const path = s.path.replace(/\/*$/, "/");
  const url = `${scheme}://${s.address}${path}?EIO=4&transport=websocket&map_protocol=1&no_graphics=1`;
  console.log(`${s.region} ${s.name}: ${url}`);
}
