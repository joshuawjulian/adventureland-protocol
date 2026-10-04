// bot.js: everything that a program needs to play, in one object.
// Bot.connect() logs in, chooses the server and the character, loads G,
// opens the socket and does the handshake. Node.js 22.18+. No packages.
import { AlSocket } from "./alsocket.js";
import { login, serversAndCharacters, findServer, findCharacter, socketUrl } from "./api.js";
import { loadG } from "./gdata.js";
import { World } from "./world.js";
import { Cooldowns } from "./cooldowns.js";
import { Budget } from "./budget.js";
import { Actions } from "./actions.js";

// The server did not let the character in. `reason` says why:
// "password_issue", "no_character", "ingame", "server_full",
// "characters_unconfirmed", "authorization_in_progress", "limits",
// "timeout", ... (see errorReason and enterGame)
export class LoginError extends Error {
  /** @param {string} reason */
  constructor(reason) {
    super(`login failed: ${reason}`);
    this.name = "LoginError";
    this.reason = reason;
  }
}

// region error-reason
// The reason of a `game_error` during the handshake. The payload is an object
// {message, phrase, phrase_args, reason?} (languages/index.js:256-258):
//   - a refused `auth` has `reason`: "no_character", "password_issue",
//     "mainframe_issue", "ingame", "poker_hand_active", "cancelled"
//     (node/server.js:11610-11652);
//   - a full server has the phrase "server.game_error.capacity"
//     (node/server.js:11587, 11879): we call it "server_full";
//   - "server.game_error.characters_unconfirmed": the server could not read
//     your other characters (node/server.js:11873-11876). Try again later.
// A bare string (for example "ERROR!") is its own reason.
/** @param {any} e @returns {string} */
export function errorReason(e) {
  if (typeof e === "string") return e;
  if (e?.reason) return String(e.reason);
  if (e?.phrase === "server.game_error.capacity") return "server_full";
  if (typeof e?.phrase === "string") return e.phrase.split(".").pop(); // "characters_unconfirmed"
  return String(e?.message ?? "unknown");
}
// endregion error-reason

// region enter-game
// The handshake on a connected socket. Returns the `welcome` payload.
// `start` reaches the World through its own handler: create the World first.
//   1. Wait for `welcome` (the server sends it at once; AlSocket keeps it).
//   2. Send `loaded`. The server ignores `auth` until `loaded` made an
//      observer for this socket (node/server.js:5028-5054, 11583).
//   3. Send `auth`. `character` is the id ("CH_..."), not the name.
//   4. Wait for `start`, or for one of the failures.
/**
 * @param {AlSocket} sock
 * @param {import("./api.js").Auth} auth
 * @param {string} characterId
 * @param {number} [timeoutMs]  30 s: a normal login takes less than 1 s
 * @returns {Promise<any>}  the `welcome` payload: {region, name, version, ...}
 */
export async function enterGame(sock, auth, characterId, timeoutMs = 30000) {
  let welcome;
  try {
    welcome = await sock.waitFor("welcome", () => true, timeoutMs);
  } catch (err) {
    const text = String(err?.message);
    throw new LoginError(text.startsWith("timed out") ? "timeout" : text); // else: the socket closed
  }

  // Listen for each possible result BEFORE we send `auth`. AlSocket has no
  // way to remove a handler, so `done` makes the handlers do nothing later.
  const result = new Promise((resolve, reject) => {
    let done = false;
    /** @param {string} reason */
    const fail = (reason) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      reject(new LoginError(reason));
    };
    const timer = setTimeout(() => fail("timeout"), timeoutMs);
    sock.on("start", (data) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve(data);
    });
    sock.on("game_error", (e) => fail(errorReason(e)));
    // The character is still online, or its save after a disconnect still
    // runs (node/server.js:11577-11582). No `start` comes on this socket.
    sock.on("game_log", (m) => {
      const text = typeof m === "string" ? m : m?.message;
      if (m?.phrase === "server.game_log.authorization_in_progress" || text === "Authorization in progress.") {
        fail("authorization_in_progress");
      }
    });
    sock.on("disconnect_reason", (r) => fail(String(r)));
    sock.on("disconnect", (r) => fail(String(r))); // AlSocket's local event: the socket closed
  });

  // The server reads none of these fields; the browser sends them.
  sock.emit("loaded", { success: 1, width: 1920, height: 1080, scale: 2 });
  sock.emit("auth", {
    user: auth.user,
    auth: auth.auth,
    character: characterId,
    no_html: "1", // "a program controls this character": the server sets afk to "code"
    passphrase: "", // only test servers check it
  });
  await result; // `start`: the World has it already
  return welcome;
}
// endregion enter-game

export class Bot {
  /**
   * Use Bot.connect(). The fields are the parts of the bot.
   * @param {{sock: AlSocket, G: Record<string, any>, world: World, cooldowns: Cooldowns,
   *   budget: Budget, act: Actions, auth: import("./api.js").Auth,
   *   server: import("./api.js").Server, character: import("./api.js").Character, welcome: any}} parts
   */
  constructor(parts) {
    this.sock = parts.sock;
    this.G = parts.G;
    this.world = parts.world;
    this.cooldowns = parts.cooldowns;
    this.budget = parts.budget;
    this.act = parts.act;
    this.auth = parts.auth;
    this.server = parts.server;
    this.character = parts.character;
    this.welcome = parts.welcome;
  }

  // region connect
  // From the environment variables to a character in the game.
  static async connect() {
    const auth = await login(); // AL_AUTH, or AL_EMAIL + AL_PASSWORD
    const { servers, characters } = await serversAndCharacters(auth);
    const server = findServer(servers); // AL_SERVER
    const character = findCharacter(characters); // AL_CHARACTER
    const G = await loadG(); // from the cache when we have this version
    return Bot.connectWith(auth, server, character, G);
  }

  // The steps after the HTTP calls: the socket, the World, the handshake and
  // the other parts. Part 3 calls it for each character of a party, with one
  // login, one server list and one G for all of them.
  /**
   * @param {import("./api.js").Auth} auth
   * @param {import("./api.js").Server} server
   * @param {import("./api.js").Character} character
   * @param {Record<string, any>} G
   */
  static async connectWith(auth, server, character, G) {
    const sock = await AlSocket.connect(socketUrl(server));
    try {
      // The World first: its handlers must be there when `start` arrives.
      const world = new World(sock, G);
      const welcome = await enterGame(sock, auth, character.id);
      // These listen to events that come after `start` only.
      const cooldowns = new Cooldowns(world);
      const budget = new Budget(sock, world);
      const act = new Actions(sock, world, cooldowns, budget);
      return new Bot({ sock, G, world, cooldowns, budget, act, auth, server, character, welcome });
    } catch (err) {
      sock.close(); // never leave a half-open socket
      throw err;
    }
  }
  // endregion connect

  // Closes the socket. The server then saves the character and marks it offline.
  close() {
    this.sock.close();
  }
}

// region reconnect-delay
// The one reconnect rule of the course. Do not reconnect at once: after a
// disconnect the server keeps the character in `dc_players` until its save
// ends, and a new `auth` gets "Authorization in progress" (node/server.js:
// 11577-11582, 13055, 16812). Wait AL_RECONNECT_MS (30 s) before the first
// try, double the wait after each failed try, at most 300 s.
// `attempt` counts the failed tries: 0 before the first try. Set it back to 0
// after a session that lasted 5 minutes. Close the old socket first, and
// always make a new AlSocket and do the full handshake again.
/** @param {number} attempt @returns {number} ms */
export function reconnectDelayMs(attempt) {
  const first = Number(process.env.AL_RECONNECT_MS) || 30000;
  const MAX_MS = 300000; // 5 minutes: longer than any save
  return Math.min(first * 2 ** attempt, MAX_MS);
}
// endregion reconnect-delay
