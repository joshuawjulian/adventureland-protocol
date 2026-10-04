// cooldowns.ts: when each skill (and the potion timer) is ready again.
// The server tells us in three ways; this class listens to all three, through
// world.listen, so that the events also count when they come as hitchhikers.
import type { GData } from "./gdata.ts";
import type { World } from "./world.ts";

/** `skill_timeout`: a skill was used; it is ready again after `ms` (node/server_functions.js:3448-3468). */
interface SkillTimeout {
  name: string;
  ms: number; // the cooldown plus the penalty
  penalty?: number;
}

/** The fields of a `game_response` object that this class reads. */
interface CooldownResponse {
  response: string; // "cooldown" or "not_ready"
  place?: string; // the event that failed
  skill?: string; // with "cooldown": the skill whose timer runs
  ms?: number; // the ms left
}

// region cooldowns
// Names: the skill names of G.skills ("attack", "3shot", ...), and "potion"
// for the one timer that all potions and the free regeneration share.
export class Cooldowns {
  readonly #G: GData;
  #readyAt = new Map<string, number>(); // name -> the time (Date.now() ms) when it is ready

  constructor(world: World) {
    this.#G = world.G;
    // 1. Each use of a skill.
    world.listen<SkillTimeout>("skill_timeout", (d) => this.start(d.name, d.ms));
    // 2. A refused use: the reply says how long is left.
    world.listen<CooldownResponse | string>("game_response", (d) => {
      if (typeof d !== "object" || d === null) return; // a bare code has no ms
      if (d.response === "cooldown") this.start(d.skill ?? d.place ?? "", d.ms ?? 0);
      if (d.response === "not_ready") this.start("potion", d.ms ?? 0); // potions and `use`
    });
    // 3. Code for the browser client: pot_timeout(ms) after a potion, and
    //    skill_timeout('name',ms) for some skills. It can come as a string or as {code}.
    world.listen<string | { code: string }>("eval", (d) => {
      const code = typeof d === "string" ? d : d.code;
      const pot = /pot_timeout\((\d+)/.exec(code); // "pot_timeout(2000)"
      if (pot) this.start("potion", Number(pot[1]));
      const skill = /skill_timeout\('([^']+)',\s*(\d+)/.exec(code); // "skill_timeout('ethereal',120)"
      if (skill) this.start(skill[1], Number(skill[2]));
    });
  }

  /** The skill `name` is ready again in `ms`. A skill with `share` also starts that skill's timer. */
  start(name: string, ms: number): void {
    const at = Date.now() + ms;
    this.#readyAt.set(name, at);
    const share = this.#G.skills[name]?.share; // for example 3shot shares the cooldown of attack
    if (share) this.#readyAt.set(share, at);
  }

  ready(name: string): boolean {
    return this.msLeft(name) === 0;
  }

  /** The ms until `name` is ready; 0 when it is ready now. */
  msLeft(name: string): number {
    return Math.max(0, (this.#readyAt.get(name) ?? 0) - Date.now());
  }
}
// endregion cooldowns
