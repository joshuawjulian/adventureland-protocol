// farmer.ts: the decisions of a fighting character, one tick at a time:
// stay alive, loot, choose a target, walk, attack. Node.js 22.18+.
//
// tick() does the first thing on this list that applies, and returns. It
// remembers nothing between ticks except the target and the counters, so a
// monster that attacks during a walk changes the next tick at once.
//   1. dead: respawn          2. in jail: leave          3. on another map: go home
//   4. low hp or mp: heal     5. a chest: open it        6. no target: choose one
//   7. too far: walk          8. in range: attack
import type { Actions, ChestOpened } from "./actions.ts";
import type { Cooldowns } from "./cooldowns.ts";
import type { Travel } from "./travel.ts";
import type { Monster, World } from "./world.ts";

// region ladder
// The Mainland ladder of the game guide ("Your first day"): the next monster
// when the current one is too easy. All live on `main`.
export const LADDER: readonly string[] = ["goo", "bee", "crab", "snake", "squig", "armadillo", "croc", "tortoise"];
// "Too easy": the last 3 kills took 2 attacks or fewer each (the guide's rule:
// "go to the next monster when you kill the current one in one or two hits").
const EASY_HITS = 2;
const EASY_KILLS = 3;
// endregion ladder

// Heal below 70 % hp: a potion (or the free regeneration) brings us back up
// before a weak monster can take the other 30 %. Mana below 30 %: a class
// that uses mana for attacks (priest, mage) needs it.
const HEAL_HP = 0.7;
const HEAL_MP = 0.3;
// Stop 10 px inside our range: the monster moves while we walk.
const RANGE_MARGIN = 10;

/** `hit`: the fields that the Farmer reads. */
interface HitData {
  id: string; // the target
  hid?: string; // the attacker
  kill?: boolean; // this hit killed the target
}

/** G.maps[map].monsters: one pack of monsters and its spawn box. */
interface Pack {
  type: string;
  boundary?: [x1: number, y1: number, x2: number, y2: number];
}

export class Farmer {
  type = "goo"; // the monster type that we hunt now
  home = "main"; // the map of our monsters
  target: string | null = null; // the id of the monster that we attack
  kills = 0;
  readonly world: World;
  readonly act: Actions;
  readonly cooldowns: Cooldowns;
  readonly travel: Travel;
  readonly prefix: string; // put before each line that it prints ("Tester: ")
  #hits = 0; // our hits on the target
  #recent: number[] = []; // hits for each of the last kills

  constructor(world: World, act: Actions, cooldowns: Cooldowns, travel: Travel, prefix = "") {
    this.world = world;
    this.act = act;
    this.cooldowns = cooldowns;
    this.travel = travel;
    this.prefix = prefix;
    // The target is dead when we get `death` with its id, or a `hit` with `kill`.
    world.listen<{ id: string }>("death", (d) => this.#dead(d.id));
    world.listen<HitData>("hit", (d) => {
      if (d.id !== this.target) return;
      if (d.hid === world.me.id) this.#hits++;
      if (d.kill) this.#dead(d.id);
    });
    // Each chest that opens for us.
    world.listen<ChestOpened>("chest_opened", (r) => {
      if (!r.gone) this.log(`chest ${r.id}: +${r.gold ?? 0} gold, ${r.items?.length ?? 0} item(s)`);
    });
  }

  log(line: string): void {
    console.log(this.prefix + line);
  }

  #dead(id: string): void {
    if (id !== this.target) return;
    this.log(`killed ${this.type} ${id}`);
    this.kills++;
    this.#recent = [...this.#recent, this.#hits].slice(-EASY_KILLS);
    this.target = null;
    this.#hits = 0;
  }

  // region next-type
  // Moves up the ladder when the last kills were easy. Returns true when the
  // type changed. Check the next monster in the game guide first: its damage
  // per second must be less than your healing (game guide, "Your first day").
  nextType(): boolean {
    const i = LADDER.indexOf(this.type);
    const easy = this.#recent.length === EASY_KILLS && this.#recent.every((h) => h <= EASY_HITS);
    if (!easy || i < 0 || i + 1 >= LADDER.length) return false;
    this.type = LADDER[i + 1];
    this.#recent = [];
    this.target = null;
    this.log(`next monster: ${this.type}`);
    return true;
  }
  // endregion next-type

  // region tick
  async tick(): Promise<void> {
    const { world, act, cooldowns, travel } = this;
    world.advance(); // positions at this moment
    const me = world.me;

    // 1. Dead: wait for the 12 s, then respawn (at main spawn 5 on `main`).
    if (me.rip) {
      this.log(`died; respawn in ${Math.ceil(act.msUntilRespawn() / 1000)} s`);
      if (await act.respawn()) this.log(`respawned at ${Math.round(me.x)},${Math.round(me.y)}`);
      return;
    }
    // 2. Jail: a line violation put us there. `leave` goes to the town.
    if (me.map === "jail") {
      this.log("in jail: leave");
      if (await travel.leaveJail()) this.log(`left jail: on ${me.map} at ${Math.round(me.x)},${Math.round(me.y)}`);
      return;
    }
    // 3. Another map (a door, the bank, a respawn somewhere else): go home.
    if (me.map !== this.home) {
      this.log(`on ${me.map}: go to ${this.home}`);
      await travel.goToMap(this.home);
      return;
    }
    // 4. Health first, then mana. heal() drinks a potion if we have one.
    if (cooldowns.ready("potion")) {
      if (me.hp < HEAL_HP * me.max_hp) await act.heal("hp");
      else if (me.mp < HEAL_MP * me.max_mp) await act.heal("mp");
    }
    // 5. Chests: open them all. Gold and items wait in a chest for 8 min only.
    if (world.chests.size) {
      await act.openChests();
      return;
    }
    // 6. The target. Choose the nearest of our type if we have none.
    let target: Monster | null = this.target === null ? null : (world.monsters.get(this.target) ?? null);
    if (!target) {
      target = world.nearestMonster(this.type);
      if (!target) {
        // None in view: walk to the middle of its spawn box (G.maps[map].monsters).
        const maps = world.G.maps as Record<string, { monsters?: Pack[] }>;
        const pack = (maps[me.map]?.monsters ?? []).find((p) => p.type === this.type && p.boundary);
        if (pack?.boundary) {
          const [x1, y1, x2, y2] = pack.boundary;
          await travel.walkTo((x1 + x2) / 2, (y1 + y2) / 2);
        }
        return;
      }
      this.target = target.id;
      this.#hits = 0;
      this.log(`target: ${this.type} ${target.id} at ${Math.round(target.x)},${Math.round(target.y)}`);
    }
    // 7. Too far: walk to a point `range - 10` px from it, on the line to us.
    if (world.distance(me, target) > me.range) {
      const dx = me.x - target.x;
      const dy = me.y - target.y;
      const d = Math.hypot(dx, dy) || 1;
      const stop = Math.max(0, me.range - RANGE_MARGIN);
      await travel.walkTo(target.x + (dx / d) * stop, target.y + (dy / d) * stop);
      return;
    }
    // 8. In range: attack when the cooldown allows.
    if (cooldowns.ready("attack")) await act.attack(target.id);
  }
  // endregion tick
}
