// connect.ts: enter the game with one character, print where it is, and leave.
// Node.js 22.18+, no packages.
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=<name> node connect.ts
//      (AL_SERVER is optional: without it, the first server of the list)
import { Bot } from "./albot/bot.ts";

// Log in, choose the server and the character, load G, do the handshake.
const bot = await Bot.connect();
const { welcome } = bot;
console.log(`welcome: ${welcome.region} ${welcome.name}, version ${welcome.version}`);

const me = bot.world.me; // `start` has no `name`: `id` is the name of a character
console.log(`in game as ${me.id} (${me.ctype}, level ${me.level}) on ${me.map} at ${Math.round(me.x)},${Math.round(me.y)}`);

bot.close(); // the server then saves the character and shows it offline
console.log("OK");
