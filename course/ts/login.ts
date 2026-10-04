// login.ts: log in over HTTP, then list the game servers and your characters.
// The values in the first column are the ones for AL_SERVER and AL_CHARACTER.
// Node.js 22.18+, no packages.
// First run:  AL_EMAIL=you@example.com AL_PASSWORD=... node login.ts
// Later runs: AL_AUTH=<user>-<auth> node login.ts   (the first run prints this value)
import { login, serversAndCharacters } from "./albot/api.ts";

const auth = await login(); // AL_AUTH, or a password login that prints the AL_AUTH value
console.log(`user id: ${auth.user}`);
const { servers, characters } = await serversAndCharacters(auth);

console.log("servers (AL_SERVER, players, address, path):");
for (const s of servers) {
  console.log(`  ${(s.region + s.name).padEnd(8)} ${String(s.players).padStart(3)}  ${s.address}  ${s.path}`);
}

console.log("characters (AL_CHARACTER, class, level, id, status):");
for (const c of characters) {
  const status = c.server ? `online on ${c.server}` : "offline"; // `server` only while online
  console.log(`  ${c.name.padEnd(8)} ${c.type.padEnd(9)}${String(c.level).padStart(3)}  ${c.id}  ${status}`);
}
