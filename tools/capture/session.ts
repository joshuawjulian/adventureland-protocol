// session.ts: log in with the saved token, connect the chosen characters to one
// server through the course library, watch for trouble, and stop cleanly.
//
// The login: the owner's bot repo keeps {userID, userAuth} in credentials.json.
// The launcher (run.py) mounts that one file read-only at /creds.json; this
// module reads it into this process's memory only. The token is never printed,
// never written (record.ts redacts it), never put on a command line.
import { readFileSync } from "node:fs";
import { serversAndCharacters, findServer } from "../../course/ts/albot/api.ts";
import type { Auth, Character, Server } from "../../course/ts/albot/api.ts";
import { reconnectDelayMs, LoginError } from "../../course/ts/albot/bot.ts";
import { loadG } from "../../course/ts/albot/gdata.ts";
import type { GData } from "../../course/ts/albot/gdata.ts";
import { connectMember, Party } from "../../course/ts/albot/party.ts";
import type { Member } from "../../course/ts/albot/party.ts";
import { Items } from "../../course/ts/albot/items.ts";
import { Travel } from "../../course/ts/albot/travel.ts";
import { Recorder, setLabel } from "./record.ts";
import type { Frame } from "./record.ts";

export const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** HARD-CODED: the owner authorized these four characters, on US V only. */
export const ALLOWED = ["SETYWarrior", "SETYPriest", "SETYMage", "SETYMerchant"];
export const SERVER_KEY = "USV";

// Events that mean "stop and look": the server kicked us, a GM or the server talks to us,
// or the login failed. The runner aborts the stage on the ones in ABORT_ON.
export const ALERT_EVENTS = new Set(["disconnect_reason", "game_error", "gm", "notice", "server_message"]);
export const ABORT_ON = new Set(["disconnect_reason", "gm"]);

export function readCredentials(path = process.env.AL_CREDS || "/creds.json"): Auth {
  const raw = JSON.parse(readFileSync(path, "utf8")) as { userID?: string; userAuth?: string };
  if (!raw.userID || !raw.userAuth) throw new Error(`${path}: no userID/userAuth`);
  return { user: raw.userID, auth: raw.userAuth };
}

/** One connected character, with the course modules that the probes use. */
export class Char {
  readonly name: string;
  readonly m: Member;
  readonly items: Items;
  readonly travel: Travel;
  readonly party: Party;
  closedReason: string | null = null; // set when the socket closed

  constructor(m: Member) {
    this.name = m.name;
    this.m = m;
    this.items = new Items(m.world, m.act, m.budget);
    this.travel = new Travel(m.world, m.act);
    this.party = new Party(m.world, m.act);
  }

  get me() {
    return this.m.world.me;
  }
}

export class Session {
  readonly rec: Recorder;
  readonly auth: Auth;
  server!: Server;
  characters: Character[] = [];
  G!: GData;
  readonly chars = new Map<string, Char>();
  abortReason: string | null = null; // set by an alert in ABORT_ON, or an unexpected close
  #stopping = false;

  constructor(rec: Recorder, auth: Auth) {
    this.rec = rec;
    this.auth = auth;
    // Watch every incoming frame for trouble.
    rec.listen((f: Frame) => {
      if (f.dir !== "in" || !ALERT_EVENTS.has(f.event)) return;
      const text = `ALERT ${f.char}: ${f.event} ${JSON.stringify(f.data)?.slice(0, 300)}`;
      console.log(text);
      rec.note(text, { alert: f.event, char: f.char });
      if (ABORT_ON.has(f.event) && !this.#stopping) this.abort(`${f.event} on ${f.char}`);
    });
  }

  abort(reason: string): void {
    if (this.abortReason) return;
    this.abortReason = reason;
    console.log(`ABORT: ${reason}`);
    this.rec.note(`abort: ${reason}`);
  }

  /** Throws when the run must stop. Probes call it between steps. */
  check(): void {
    if (this.abortReason) throw new Error(`aborted: ${this.abortReason}`);
  }

  async init(): Promise<void> {
    // The course's apiCall reads only the auth object; nothing here touches AL_AUTH.
    const { servers, characters } = await serversAndCharacters(this.auth);
    this.server = findServer(servers, SERVER_KEY);
    this.characters = characters;
    this.G = await loadG();
    this.rec.note("init", {
      server: `${this.server.region} ${this.server.name}`,
      g_version: this.G.version,
      characters: characters
        .filter((c) => ALLOWED.includes(c.name))
        .map((c) => ({ name: c.name, type: c.type, level: c.level, online: c.online, server: c.server ?? null, map: c.map })),
    });
  }

  // Connects one character. "Authorization in progress" (still online or still saving from
  // a previous run) waits by the course's reconnect rule and tries again, up to 5 times.
  async connect(name: string): Promise<Char> {
    if (!ALLOWED.includes(name)) throw new Error(`${name} is not one of the authorized characters`);
    const character = this.characters.find((c) => c.name === name);
    if (!character) throw new Error(`no character ${name} on the account`);
    for (let attempt = 0; ; attempt++) {
      setLabel(name);
      try {
        const m = await connectMember(this.auth, this.server, character, this.G);
        const c = new Char(m);
        m.sock.on<string>("disconnect", (reason) => {
          c.closedReason = String(reason);
          this.rec.note(`closed ${name}: ${reason}`, { char: name });
          if (!this.#stopping) this.abort(`${name} disconnected: ${reason}`);
        });
        this.chars.set(name, c);
        console.log(`${name}: in game on ${c.me.map} at ${Math.round(c.me.x)},${Math.round(c.me.y)}, level ${c.me.level}, gold ${c.me.gold}${c.me.rip ? " (DEAD)" : ""}`);
        return c;
      } catch (err) {
        const reason = err instanceof LoginError ? err.reason : String(err);
        this.rec.note(`connect ${name} failed: ${reason}`, { char: name });
        if (attempt >= 4 || !(err instanceof LoginError) || !["authorization_in_progress", "ingame", "timeout"].includes(reason)) {
          throw err;
        }
        const wait = reconnectDelayMs(attempt);
        console.log(`${name}: ${reason}; trying again in ${wait / 1000} s`);
        await sleep(wait);
      }
    }
  }

  async connectAll(names: string[]): Promise<Char[]> {
    const out: Char[] = [];
    for (const n of names) {
      out.push(await this.connect(n));
      await sleep(1500); // space the logins: each costs call-cost and server work
    }
    return out;
  }

  /** Closes every socket, waits for the closes to be written, and notes the end. */
  async stop(): Promise<void> {
    if (this.#stopping) return;
    this.#stopping = true;
    for (const c of this.chars.values()) c.m.close();
    await sleep(1000);
    this.rec.note("stop", { pings: this.rec.pings });
  }
}
