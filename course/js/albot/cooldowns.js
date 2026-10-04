// cooldowns.js: when each skill (and the potion timer) is ready again.
// The server tells us in three ways; this class listens to all three.
// Node.js 22.18+. No packages.
//
// Names: a skill name ("attack", "3shot", ...), and "potion" for the one
// timer that all potions and the free regeneration (`use`) share.

// region cooldowns
export class Cooldowns {
  /** @type {Map<string, number>} name -> the time (Date.now() ms) it is ready again */
  #readyAt = new Map();

  /** @param {import("./world.js").World} world */
  constructor(world) {
    this.G = world.G;
    // Through world.listen, so that the same events count when they arrive
    // as hitchhikers inside a `player` update.

    // 1. After each skill (an attack, too): {name, ms}.
    world.listen("skill_timeout", (d) => this.start(d.name, d.ms));

    // 2. We were too early. `cooldown` names the skill; `not_ready` is the potion timer.
    world.listen("game_response", (d) => {
      if (typeof d !== "object" || d === null) return; // a bare string: not about time
      if (d.response === "cooldown") this.start(d.skill ?? d.place, d.ms);
      if (d.response === "not_ready") this.start("potion", d.ms);
    });

    // 3. JavaScript for the browser client, as a string or as {code}:
    //    "pot_timeout(2000)" after a potion, "skill_timeout('ethereal',120)".
    world.listen("eval", (d) => {
      const code = typeof d === "string" ? d : (d?.code ?? "");
      const pot = /^pot_timeout\((\d+)/.exec(code);
      if (pot) this.start("potion", Number(pot[1]));
      const skill = /^skill_timeout\('([^']+)',\s*(\d+)/.exec(code);
      if (skill) this.start(skill[1], Number(skill[2]));
    });
  }

  // `name` is ready again in `ms` milliseconds. A skill can share its timer
  // with another (G.skills[name].share, for example 3shot shares "attack").
  /** @param {string} name @param {number} ms */
  start(name, ms) {
    const at = Date.now() + ms;
    this.#readyAt.set(name, at);
    const share = this.G.skills[name]?.share;
    if (share) this.#readyAt.set(share, at);
  }

  /** @param {string} name */
  ready(name) {
    return this.msLeft(name) === 0;
  }

  // Milliseconds until `name` is ready; 0 when it is ready now.
  /** @param {string} name */
  msLeft(name) {
    return Math.max(0, (this.#readyAt.get(name) ?? 0) - Date.now());
  }
}
// endregion cooldowns
