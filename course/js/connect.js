// connect.js: log in, connect to a game server, do the handshake and start a
// character. Then close. Node.js 22.18+, no packages.
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyMage node connect.js
//      (AL_SERVER is optional: without it, the program uses the first server of the list.)
import { Bot } from "./albot/bot.js";

const bot = await Bot.connect(); // login, server list, G, socket, handshake
const { welcome } = bot;
console.log(`welcome: ${welcome.region} ${welcome.name}, version ${welcome.version}`);

// `start` has no `name`: `id` is the name. `ctype` is the class.
const me = bot.world.me;
console.log(`in game as ${me.id} (${me.ctype}, level ${me.level}) on ${me.map} at ${Math.round(me.x)},${Math.round(me.y)}`);

bot.close(); // the server then saves the character and marks it offline
console.log("OK");
