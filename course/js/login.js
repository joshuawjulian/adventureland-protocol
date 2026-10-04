// login.js: log in over HTTP, then list the game servers and your characters.
// Node.js 22.18+, no packages.
// First run:  AL_EMAIL=you@example.com AL_PASSWORD=... node login.js
// Later runs: AL_AUTH=<user>-<auth> node login.js   (the first run prints this value)
import { login, serversAndCharacters } from "./albot/api.js";

const auth = await login();
console.log(`user id: ${auth.user}`);
const { servers, characters } = await serversAndCharacters(auth);

// The first column is the value for AL_SERVER: region + name, for example "EUI".
console.log("servers (AL_SERVER, players, address, path):");
for (const s of servers) {
  console.log(`  ${(s.region + s.name).padEnd(8)} ${String(s.players).padStart(3)}  ${s.address}  ${s.path}`);
}

// The first column is the value for AL_CHARACTER: the name, not the id.
console.log("characters (AL_CHARACTER, class, level, id, status):");
for (const c of characters) {
  // `server` is there only while the character is online.
  const status = c.server ? `online on ${c.server}` : "offline";
  console.log(`  ${c.name.padEnd(8)} ${c.type.padEnd(9)} ${String(c.level).padStart(3)}  ${c.id}  ${status}`);
}
