// party.js: several characters in one program, a party, and a new character.
// Node.js 22.18+. No packages.
//
// The program logs in once, reads the server and character lists once and
// loads G once. Then connectMember() opens one socket for each character. Each character has its own World, Cooldowns, Budget and
// Actions: the server counts the call-cost for each socket.
import { apiCall } from "./api.js";
import { Bot } from "./bot.js";
/** @typedef {import("./alsocket.js").AlSocket} AlSocket */
/** @typedef {import("./world.js").World} World */
/** @typedef {import("./cooldowns.js").Cooldowns} Cooldowns */
/** @typedef {import("./budget.js").Budget} Budget */
/** @typedef {import("./actions.js").Actions} Actions */

const sleep = (/** @type {number} */ ms) => new Promise((resolve) => setTimeout(resolve, ms));

// region member
// One character in the game: the same parts as a Bot.
export class Member {
  /**
   * @param {{name: string, sock: AlSocket, G: Record<string, any>, world: World, cooldowns: Cooldowns,
   *   budget: Budget, act: Actions, character: import("./api.js").Character}} parts
   */
  constructor(parts) {
    this.name = parts.name;
    this.sock = parts.sock;
    this.G = parts.G;
    this.world = parts.world;
    this.cooldowns = parts.cooldowns;
    this.budget = parts.budget;
    this.act = parts.act;
    this.character = parts.character;
  }

  close() {
    this.sock.close();
  }
}

// Connects one character with a login, a server and a G that we already
// have: Bot.connectWith (Bot.connect without the HTTP calls).
/**
 * @param {import("./api.js").Auth} auth
 * @param {import("./api.js").Server} server
 * @param {import("./api.js").Character} character
 * @param {Record<string, any>} G
 */
export async function connectMember(auth, server, character, G) {
  const bot = await Bot.connectWith(auth, server, character, G);
  return new Member({ name: character.name, ...bot });
}

// endregion member

// region create-character
// Makes a new character on the account: HTTP `create_character` {name, char}
// (api.js:474-588). The name: 4 to 12 letters, digits or "_", not used by
// anyone (api.js:24-31). The answer is {success: true}, or {failed: true,
// reason}: "name_used", "invalid_name", "reached_character_limit", ...
/**
 * @param {import("./api.js").Auth} auth
 * @param {string} name
 * @param {string} ctype  the class: "merchant", "warrior", ...
 */
export async function createCharacter(auth, name, ctype) {
  const r = await apiCall("create_character", { name, char: ctype }, auth);
  if (r.failed) throw new Error(`create_character failed: ${r.reason}`);
  return r;
}
// endregion create-character

// region party
// The party of one character. The server sends `invite` {name} to the
// character that gets an invitation, and `party_update` {list, party} to each
// member when the party changes (node/server.js:12357-12546).
export class Party {
  /** @type {string[]} the names in our party, the leader first */
  list = [];
  /** @type {Set<string>} who invited us */
  #invites = new Set();

  /**
   * @param {World} world
   * @param {Actions} act
   */
  constructor(world, act) {
    this.act = act;
    world.listen("invite", (d) => this.#invites.add(d.name));
    // {} (no list) when we left or the party ended.
    world.listen("party_update", (d) => (this.list = d?.list ?? []));
  }

  // Invites `name` (a character on this server). The answer is a success
  // with place "party", or "invalid" (no such character), "party_full".
  /** @param {string} name */
  async invite(name) {
    return this.act.request("party", { event: "invite", name });
  }

  // Accepts the invitation of `name`. It fails with "invitation_expired"
  // when there was no invitation.
  /** @param {string} name */
  async accept(name) {
    return this.act.request("party", { event: "accept", name });
  }

  async leave() {
    return this.act.request("party", { event: "leave" });
  }

  // Waits until `name` invited us (true), or `ms` passed (false).
  /** @param {string} name @param {number} [ms] */
  async waitInvite(name, ms = 5000) {
    for (const end = Date.now() + ms; Date.now() < end; await sleep(50)) if (this.#invites.has(name)) return true;
    return this.#invites.has(name);
  }
}
// endregion party
