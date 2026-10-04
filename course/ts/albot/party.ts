// party.ts: several characters in one program, a party, and a new character.
// Node.js 22.18+. No packages.
//
// The program logs in once, reads the server and character lists once and
// loads G once. Then connectMember() opens one socket for each character.
// Each character has its own World, Cooldowns, Budget and Actions: the
// server counts the call-cost for each socket.
import type { AlSocket } from "./alsocket.ts";
import { apiCall } from "./api.ts";
import type { ApiReply, Auth, Character, Server } from "./api.ts";
import type { World } from "./world.ts";
import type { Cooldowns } from "./cooldowns.ts";
import type { Budget } from "./budget.ts";
import type { Actions, GameResponse } from "./actions.ts";
import { Bot } from "./bot.ts";
import type { GData } from "./gdata.ts";

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

// region member
/** The parts of one character in the game: the same parts as a Bot. */
export interface MemberParts {
  name: string;
  sock: AlSocket;
  G: GData;
  world: World;
  cooldowns: Cooldowns;
  budget: Budget;
  act: Actions;
  character: Character;
}

// One character in the game. (Bot's constructor is private, so a party
// member is its own class, made from the parts of a Bot.)
export class Member {
  readonly name: string;
  readonly sock: AlSocket;
  readonly G: GData;
  readonly world: World;
  readonly cooldowns: Cooldowns;
  readonly budget: Budget;
  readonly act: Actions;
  readonly character: Character;

  constructor(parts: MemberParts) {
    this.name = parts.name;
    this.sock = parts.sock;
    this.G = parts.G;
    this.world = parts.world;
    this.cooldowns = parts.cooldowns;
    this.budget = parts.budget;
    this.act = parts.act;
    this.character = parts.character;
  }

  close(): void {
    this.sock.close();
  }
}

// Connects one character with a login, a server and a G that we already
// have: Bot.connectWith (Bot.connect without the HTTP calls).
export async function connectMember(auth: Auth, server: Server, character: Character, G: GData): Promise<Member> {
  const bot = await Bot.connectWith(auth, server, character, G);
  return new Member({ name: character.name, ...bot });
}
// endregion member

// region create-character
// Makes a new character on the account: HTTP `create_character` {name, char}
// (api.js:474-588). The name: 4 to 12 letters, digits or "_", not used by
// anyone (api.js:24-31). The answer is {success: true}, or {failed: true,
// reason}: "name_used", "invalid_name", "reached_character_limit", ...
// ctype is the class: "merchant", "warrior", ...
export async function createCharacter(auth: Auth, name: string, ctype: string): Promise<ApiReply> {
  const r = await apiCall("create_character", { name, char: ctype }, auth);
  if (r.failed) throw new Error(`create_character failed: ${r.reason}`);
  return r;
}
// endregion create-character

// region party
/** `party_update`: {list, party}, or {} when we left or the party ended. */
interface PartyUpdate {
  list?: string[];
}

// The party of one character. The server sends `invite` {name} to the
// character that gets an invitation, and `party_update` {list, party} to each
// member when the party changes (node/server.js:12357-12546).
export class Party {
  list: string[] = []; // the names in our party, the leader first
  readonly act: Actions;
  #invites = new Set<string>(); // who invited us

  constructor(world: World, act: Actions) {
    this.act = act;
    world.listen<{ name: string }>("invite", (d) => this.#invites.add(d.name));
    world.listen<PartyUpdate | null>("party_update", (d) => (this.list = d?.list ?? []));
  }

  // Invites `name` (a character on this server). The answer is a success
  // with place "party", or "invalid" (no such character), "party_full".
  async invite(name: string): Promise<GameResponse | null> {
    return this.act.request("party", { event: "invite", name });
  }

  // Accepts the invitation of `name`. It fails with "invitation_expired"
  // when there was no invitation.
  async accept(name: string): Promise<GameResponse | null> {
    return this.act.request("party", { event: "accept", name });
  }

  async leave(): Promise<GameResponse | null> {
    return this.act.request("party", { event: "leave" });
  }

  // Waits until `name` invited us (true), or `ms` passed (false).
  async waitInvite(name: string, ms = 5000): Promise<boolean> {
    for (const end = Date.now() + ms; Date.now() < end; await sleep(50)) if (this.#invites.has(name)) return true;
    return this.#invites.has(name);
  }
}
// endregion party
