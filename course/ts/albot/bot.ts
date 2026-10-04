// bot.ts: from nothing to a character in the game, in one call: Bot.connect().
// It logs in, finds the server and the character, loads G, opens the socket,
// does the handshake, and makes the World, Cooldowns, Budget and Actions.
import { Actions } from "./actions.ts";
import { AlSocket } from "./alsocket.ts";
import { findCharacter, findServer, login, serversAndCharacters, socketUrl } from "./api.ts";
import type { Auth, Character, Server } from "./api.ts";
import { Budget } from "./budget.ts";
import { Cooldowns } from "./cooldowns.ts";
import { loadG } from "./gdata.ts";
import type { GData } from "./gdata.ts";
import { World } from "./world.ts";

/** `welcome`: the first event on a new socket (node/server.js:4972-5015). */
export interface Welcome {
  region: string; // "EU"
  name: string; // "I"
  version: number; // the version of G on this server
  pvp: boolean;
  gameplay: string; // "normal", "hardcore", ...
  map: string; // where the socket watches from before `auth`
  x: number;
  y: number;
}

/** `auth`: the fields that the server reads (node/server.js:11563-11861). */
interface AuthPayload {
  user: string; // "US_..."
  auth: string; // the token, without the "<user>-" part
  character: string; // "CH_...", the id from the character list
  no_html: string; // "1": a program (not the browser) controls this character
  passphrase: string; // only test servers check it
}

/** game_error and game_log come as {message, phrase, reason?, ...} (or as a bare string). */
interface ServerMessage {
  message: string;
  phrase?: string;
  reason?: string;
}

/** The login of a character failed. `reason` says why. */
export class LoginError extends Error {
  readonly reason: string;
  constructor(reason: string) {
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
export function errorReason(e: ServerMessage | string): string {
  if (typeof e === "string") return e;
  if (e.reason) return String(e.reason);
  if (e.phrase === "server.game_error.capacity") return "server_full";
  if (e.phrase) return e.phrase.split(".").pop() ?? e.phrase; // "characters_unconfirmed"
  return String(e.message ?? "unknown");
}
// endregion error-reason

// region enter-game
// The handshake: wait for `welcome`, send `loaded`, send `auth`, wait for
// `start`. Resolves with the `welcome` payload. Rejects with a LoginError on
// each of the ways that the server says no.
export async function enterGame(
  sock: AlSocket,
  auth: Auth,
  characterId: string,
  timeoutMs = 30_000, // a normal login takes well under 1 s
): Promise<Welcome> {
  // Listen for every result BEFORE the first `await`: `welcome` can be here
  // already (AlSocket keeps it for the first listener of that name).
  const welcome = new Promise<Welcome>((resolve) => sock.on<Welcome>("welcome", resolve));
  const started = new Promise<unknown>((resolve) => sock.on("start", resolve));
  let timer: ReturnType<typeof setTimeout> | undefined;
  const failed = new Promise<never>((_, reject) => {
    const fail = (reason: string) => reject(new LoginError(reason));
    timer = setTimeout(() => fail("timeout"), timeoutMs);
    sock.on<ServerMessage | string>("game_error", (e) => fail(errorReason(e)));
    // "Authorization in progress": the character is still online, or the
    // server still saves it after a disconnect. No `start` comes on this
    // socket (node/server.js:11577-11582). See the reconnect rule.
    sock.on<ServerMessage | string>("game_log", (m) => {
      const text = typeof m === "string" ? m : String(m.message ?? "");
      if (text.startsWith("Authorization in progress")) fail("authorization_in_progress");
    });
    sock.on<string>("disconnect_reason", (r) => fail(String(r))); // the server's reason, then it closes
    sock.on<string>("disconnect", (r) => fail(String(r))); // AlSocket's local event
  });

  try {
    const w = await Promise.race([welcome, failed]);
    // The server reads none of the fields of `loaded`, but it ignores `auth`
    // until `loaded` made this socket an observer (node/server.js:5028-5054, 11583).
    sock.emit("loaded", { success: 1, width: 1920, height: 1080, scale: 2 });
    const payload: AuthPayload = {
      user: auth.user,
      auth: auth.auth,
      character: characterId,
      no_html: "1",
      passphrase: "",
    };
    sock.emit("auth", payload);
    await Promise.race([started, failed]); // the World's handler has read `start` already
    return w;
  } finally {
    clearTimeout(timer);
  }
}
// endregion enter-game

export class Bot {
  readonly sock: AlSocket;
  readonly G: GData;
  readonly world: World;
  readonly cooldowns: Cooldowns;
  readonly budget: Budget;
  readonly act: Actions;
  readonly auth: Auth;
  readonly server: Server;
  readonly character: Character;
  readonly welcome: Welcome;

  // Use Bot.connect() or Bot.connectWith(). (The constructor only stores the parts.)
  private constructor(parts: {
    sock: AlSocket; G: GData; world: World; cooldowns: Cooldowns; budget: Budget; act: Actions;
    auth: Auth; server: Server; character: Character; welcome: Welcome;
  }) {
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
  // Each step uses the environment variables: AL_AUTH (or AL_EMAIL and
  // AL_PASSWORD), AL_SERVER, AL_CHARACTER, AL_BASE_URL.
  static async connect(): Promise<Bot> {
    const auth = await login();
    const { servers, characters } = await serversAndCharacters(auth);
    const server = findServer(servers);
    const character = findCharacter(characters);
    const G = await loadG();
    return Bot.connectWith(auth, server, character, G);
  }

  // The steps after the HTTP calls: the socket, the World, the handshake and
  // the other parts. Part 3 calls it for each character of a party, with one
  // login, one server list and one G for all of them.
  static async connectWith(auth: Auth, server: Server, character: Character, G: GData): Promise<Bot> {
    const sock = await AlSocket.connect(socketUrl(server));
    // No `await` from here to the first line of enterGame: the World and
    // enterGame must listen before the next event can come.
    const world = new World(sock, G); // before `loaded`: it must see `start`
    let welcome: Welcome;
    try {
      welcome = await enterGame(sock, auth, character.id);
    } catch (err) {
      sock.close();
      throw err;
    }
    const cooldowns = new Cooldowns(world);
    const budget = new Budget(sock, world);
    const act = new Actions(sock, world, cooldowns, budget);
    return new Bot({ sock, G, world, cooldowns, budget, act, auth, server, character, welcome });
  }
  // endregion connect

  /** Closes the socket. The server then saves the character and shows it offline. */
  close(): void {
    this.sock.close();
  }
}

// region reconnect-delay
// The one reconnect rule. Do not reconnect at once: after a disconnect, the
// server keeps the character in dc_players until its save ends, and a new
// `auth` gets "Authorization in progress" (node/server.js:11577-11582, :13055,
// :16812). So wait AL_RECONNECT_MS (30 s) before the first try, double the
// wait after each failed try, and wait 300 s at most.
// `attempt` is 0 for the first try. Start again from 0 after a session that
// lasted 5 minutes. Close the old socket first, and always make a new
// AlSocket and a new Bot (the full handshake).
export function reconnectDelayMs(attempt: number): number {
  const first = Number(process.env.AL_RECONNECT_MS) || 30_000;
  return Math.min(first * 2 ** attempt, 300_000);
}
// endregion reconnect-delay
