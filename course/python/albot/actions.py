# actions.py: what our character does: move, attack, heal, loot, respawn.
#
# Two rules for every action here:
#   1. Every event goes through budget.emit, so that we stay under the
#      call-cost limit.
#   2. An action that waits for a reply registers the wait BEFORE it sends the
#      event. A fast reply can otherwise arrive before the wait exists, and
#      then the wait never ends.
import asyncio
import math
import time
from typing import Any, Callable

from .alsocket import AlSocket
from .budget import Budget
from .cooldowns import Cooldowns
from .world import Entity, World

# game_response after normalize(): always has `response`, `failed` and `success`;
# often `place` (the event it answers) and more fields (ms, id, ...).
GameResponse = dict[str, Any]


# region normalize
def normalize(data: Any) -> GameResponse:
    """game_response arrives as a dict or as a bare string. Make it one shape.
    Note: a successful attack has no `success` key, so success defaults to False;
    check `failed`, not `success`."""
    if isinstance(data, str):
        return {"response": data, "failed": False, "success": False}
    return {"failed": False, "success": False, **data}


def response_for(place: str) -> Callable[[Any], bool]:
    """A predicate for wait_for: a game_response object about `place`."""
    return lambda d: isinstance(d, dict) and d.get("place") == place
# endregion normalize


class Actions:
    def __init__(self, sock: AlSocket, world: World, cooldowns: Cooldowns, budget: Budget) -> None:
        self.sock = sock
        self.world = world
        self.cooldowns = cooldowns
        self.budget = budget
        # When we last died (time.monotonic()), from game_response
        # "defeated_by_a_monster"; None while we live. respawn() reads it.
        self.died_at: float | None = None
        world.listen("game_response", self._on_defeat)

    @property
    def me(self) -> Entity:
        return self.world.me

    # region request
    async def request(self, event: str, payload: Any, place: str | None = None,
                      timeout_ms: float = 2000) -> GameResponse | None:
        """Send `event` and wait for the game_response whose `place` is `place`
        (the event name by default). None if no reply comes in time: some
        failures send another event instead (attack: `disappear`)."""
        await self.budget.wait_for_room(event)  # first, so that it does not use the timeout
        reply = self.sock.wait_for("game_response", response_for(place or event), timeout=timeout_ms / 1000)
        await self.budget.emit(event, payload)
        try:
            return normalize(await reply)
        except TimeoutError:
            return None
    # endregion request

    def _on_defeat(self, d: Any) -> None:
        if isinstance(d, dict) and d.get("response") == "defeated_by_a_monster":
            self.died_at = time.monotonic()

    # region move-to
    async def move(self, x: float, y: float) -> None:
        """Start a straight walk to (x, y). No reply comes: the server takes the
        move, or ignores it without a word (for example a wrong `m`)."""
        me = self.me
        # `m` must equal the server's map counter (it changes on each map change).
        await self.budget.emit("move", {"x": me["x"], "y": me["y"], "going_x": x, "going_y": y, "m": me["m"]})
        me.update(going_x=x, going_y=y, moving=True)  # the server does the same

    async def move_to(self, x: float, y: float) -> bool:
        """Walk in a straight line to (x, y) and wait until we should be there.
        True if we arrived. A straight line only: a wall on the way sends the
        character to jail (Part 3 walks around walls)."""
        self.world.advance()  # our position now
        await self.move(x, y)
        seconds = math.hypot(x - self.me["x"], y - self.me["y"]) / self.me["speed"]
        await asyncio.sleep(seconds + 0.25)  # 0.25 s: room for the network delay
        self.world.advance()
        # Arrived: within 1 px, and still on the way to (x, y). A `correction`
        # or a jail sends us somewhere else: then the walk failed.
        me = self.me
        return (math.hypot(me["x"] - x, me["y"] - y) < 1
                and me.get("going_x") == x and me.get("going_y") == y)
    # endregion move-to

    # region attack
    async def attack(self, target_id: str) -> GameResponse | None:
        """Attack a monster by id. Success: response "data" with the projectile
        (`pid`, `eta`); the damage comes later as a `hit` event. Failure:
        `failed` with a response such as "cooldown" or "too_far". None if no
        game_response came (a target that is gone gets `disappear` instead)."""
        return await self.request("attack", {"id": target_id})
    # endregion attack

    # region heal
    def _find_potion(self, stat: str) -> int:
        """The first inventory slot with a potion that gives `stat`, or -1."""
        for num, item in enumerate(self.me.get("items") or []):
            if not item:
                continue  # an empty slot is null
            item_def = self.world.G["items"].get(item["name"])
            gives = item_def.get("gives", []) if item_def else []
            if any(g[0] == stat for g in gives):
                return num
        return -1

    async def heal(self, stat: str) -> bool:
        """`stat` is "hp" or "mp". Drink a potion that gives it, if we have one;
        else use the free regeneration (`use`). Potions and the regeneration
        share one timer ("potion"): skip (False) when it is not ready."""
        if not self.cooldowns.ready("potion"):
            return False
        num = self._find_potion(stat)
        if num >= 0:
            # A potion is "equipped" with consume: true (node/server.js:7798-7855).
            r = await self.request("equip", {"num": num, "consume": True})
        else:
            r = await self.request("use", {"item": stat})
        return r is not None and not r["failed"]
    # endregion heal

    async def open_chest(self, chest_id: str) -> dict[str, Any] | None:
        """Open one chest. Returns the `chest_opened` payload ({id, gold, items,
        ...}, or {id, gone: true}), or None if no reply came (for example no
        space in the inventory: game_response "loot_no_space")."""
        await self.budget.wait_for_room("open_chest")
        opened = self.sock.wait_for(
            "chest_opened", lambda d: isinstance(d, dict) and d.get("id") == chest_id, timeout=2)
        await self.budget.emit("open_chest", {"id": chest_id})
        try:
            result: dict[str, Any] = await opened
            return result
        except TimeoutError:
            return None

    # region open-chests
    async def open_chests(self) -> int:
        """Open every chest that we know of. Returns how many opened."""
        count = 0
        for chest_id in list(self.world.chests):
            r = await self.open_chest(chest_id)
            if r is not None and not r.get("gone"):
                count += 1
            self.world.chests.pop(chest_id, None)  # opened, gone or failed: do not try again
        return count
    # endregion open-chests

    # region respawn
    async def respawn(self) -> bool:
        """Come back to life. The server refuses `respawn` for 12 s after the death
        (B.rip_time, node/server.js:224) with "cant_respawn" and the ms left.
        We wait out the rest, send it, and try one more time if it was early."""
        if self.died_at is not None:
            wait = self.died_at + 12 - time.monotonic()  # 12 s: rip_time
            if wait > 0:
                await asyncio.sleep(wait)
        r = await self.request("respawn", {}, timeout_ms=3000)
        if r is not None and r["response"] == "cant_respawn":
            await asyncio.sleep(r.get("ms", 0) / 1000 + 0.1)  # +0.1 s: a margin
            r = await self.request("respawn", {}, timeout_ms=3000)
        if r is None or r["failed"]:
            return False
        self.died_at = None
        return True
    # endregion respawn
