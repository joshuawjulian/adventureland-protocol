# farmer.py: the decisions of a fighting character, one tick at a time:
# stay alive, loot, choose a target, walk, attack.
#
# tick() does the first thing on this list that applies, and returns. It
# remembers nothing between ticks except the target and the counters, so a
# monster that attacks during a walk changes the next tick at once.
#   1. dead: respawn          2. in jail: leave          3. on another map: go home
#   4. low hp or mp: heal     5. a chest: open it        6. no target: choose one
#   7. too far: walk          8. in range: attack
import math
import time
from typing import Any

from .actions import Actions
from .cooldowns import Cooldowns
from .travel import Travel
from .world import World

# region ladder
# The Mainland ladder of the game guide ("Your first day"): the next monster
# when the current one is too easy. All live on `main`.
LADDER = ["goo", "bee", "crab", "snake", "squig", "armadillo", "croc", "tortoise"]
# "Too easy": the last 3 kills took 2 attacks or fewer each (the guide's rule:
# "go to the next monster when you kill the current one in one or two hits").
EASY_HITS = 2
EASY_KILLS = 3
# endregion ladder

# Heal below 70 % hp: a potion (or the free regeneration) brings us back up
# before a weak monster can take the other 30 %. Mana below 30 %: a class
# that uses mana for attacks (priest, mage) needs it.
HEAL_HP = 0.7
HEAL_MP = 0.3
# Stop 10 px inside our range: the monster moves while we walk.
RANGE_MARGIN = 10


def where(e: dict[str, Any]) -> str:
    return f"{round(e['x'])},{round(e['y'])}"


class Farmer:
    def __init__(self, world: World, act: Actions, cooldowns: Cooldowns, travel: Travel,
                 prefix: str = "") -> None:
        """`prefix` goes before each line that it prints ("Tester: ")."""
        self.world = world
        self.act = act
        self.cooldowns = cooldowns
        self.travel = travel
        self.prefix = prefix
        self.type = "goo"  # the monster type that we hunt now
        self.home = "main"  # the map of our monsters
        self.target: str | None = None  # the id of the monster that we attack
        self.kills = 0
        self._hits = 0  # our hits on the target
        self._recent: list[int] = []  # hits for each of the last kills
        # The target is dead when we get `death` with its id, or a `hit` with `kill`.
        world.listen("death", lambda d: self._dead(d["id"]))
        world.listen("hit", self._on_hit)
        world.listen("chest_opened", self._on_chest)

    def log(self, line: str) -> None:
        print(self.prefix + line, flush=True)

    def _on_hit(self, d: Any) -> None:
        if d.get("id") != self.target:
            return
        if d.get("hid") == self.world.me.get("id"):
            self._hits += 1
        if d.get("kill"):
            self._dead(d["id"])

    def _on_chest(self, r: Any) -> None:
        """Each chest that opens for us."""
        if not r.get("gone"):
            self.log(f"chest {r['id']}: +{r.get('gold', 0)} gold, {len(r.get('items') or [])} item(s)")

    def _dead(self, mid: str) -> None:
        if mid != self.target:
            return
        self.log(f"killed {self.type} {mid}")
        self.kills += 1
        self._recent = (self._recent + [self._hits])[-EASY_KILLS:]
        self.target = None
        self._hits = 0

    # region next-type
    def next_type(self) -> bool:
        """Move up the ladder when the last kills were easy. True when the type
        changed. Check the next monster in the game guide first: its damage per
        second must be less than your healing (game guide, "Your first day")."""
        i = LADDER.index(self.type) if self.type in LADDER else -1
        easy = len(self._recent) == EASY_KILLS and all(h <= EASY_HITS for h in self._recent)
        if not easy or i < 0 or i + 1 >= len(LADDER):
            return False
        self.type = LADDER[i + 1]
        self._recent = []
        self.target = None
        self.log(f"next monster: {self.type}")
        return True
    # endregion next-type

    # region tick
    async def tick(self) -> None:
        world, act, cooldowns, travel = self.world, self.act, self.cooldowns, self.travel
        world.advance()  # positions at this moment
        me = world.me

        # 1. Dead: wait for the 12 s, then respawn (at main spawn 5 on `main`).
        if me.get("rip"):
            died = act.died_at if act.died_at is not None else time.monotonic()
            self.log(f"died; respawn in {math.ceil(max(0.0, died + 12 - time.monotonic()))} s")
            if await act.respawn():
                self.log(f"respawned at {where(me)}")
            return
        # 2. Jail: a line violation put us there. `leave` goes to the town.
        if me["map"] == "jail":
            self.log("in jail: leave")
            if await travel.leave_jail():
                self.log(f"left jail: on {me['map']} at {where(me)}")
            return
        # 3. Another map (a door, the bank, a respawn somewhere else): go home.
        if me["map"] != self.home:
            self.log(f"on {me['map']}: go to {self.home}")
            await travel.go_to_map(self.home)
            return
        # 4. Health first, then mana. heal() drinks a potion if we have one.
        if cooldowns.ready("potion"):
            if me["hp"] < HEAL_HP * me["max_hp"]:
                await act.heal("hp")
            elif me["mp"] < HEAL_MP * me["max_mp"]:
                await act.heal("mp")
        # 5. Chests: open them all. Gold and items wait in a chest for 8 min only.
        if world.chests:
            await act.open_chests()
            return
        # 6. The target. Choose the nearest of our type if we have none.
        target = world.monsters.get(self.target) if self.target is not None else None
        if target is None:
            target = world.nearest_monster(self.type)
            if target is None:
                # None in view: walk to the middle of its spawn box (G.maps[map].monsters).
                for pack in world.G["maps"][me["map"]].get("monsters") or []:
                    if pack.get("type") == self.type and pack.get("boundary"):
                        x1, y1, x2, y2 = pack["boundary"]
                        await travel.walk_to((x1 + x2) / 2, (y1 + y2) / 2)
                        break
                return
            self.target = target["id"]
            self._hits = 0
            self.log(f"target: {self.type} {target['id']} at {where(target)}")
        # 7. Too far: walk to a point `range - 10` px from it, on the line to us.
        if world.distance(me, target) > me["range"]:
            dx, dy = me["x"] - target["x"], me["y"] - target["y"]
            d = math.hypot(dx, dy) or 1
            stop = max(0, me["range"] - RANGE_MARGIN)
            await travel.walk_to(target["x"] + dx / d * stop, target["y"] + dy / d * stop)
            return
        # 8. In range: attack when the cooldown allows.
        if cooldowns.ready("attack"):
            await act.attack(target["id"])
    # endregion tick
