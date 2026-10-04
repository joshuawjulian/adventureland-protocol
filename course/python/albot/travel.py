# travel.py: walk around walls, go through doors, use the transporter, and
# get out of jail.
#
# It uses the grid of pathfind.py for the walls, and Actions.move_to for each
# straight part of the walk.
import asyncio
import math
import time
from dataclasses import dataclass
from typing import Callable

from .actions import Actions
from .pathfind import Grid
from .world import World

# The distances of the server (node/server.js:221-223): a door works within
# 112 px of its box, the transporter NPC within 160 px of the NPC.
DOOR_DIST = 112
TRANSPORTER_DIST = 160
# How long to wait for `new_map` after a transport, in s. Live sends it at
# once for a door; for the bank it comes after the account loads (in_progress).
NEW_MAP_S = 5.0


@dataclass(frozen=True)
class Hop:
    """One step between two maps: stand at (x, y) on `map_name`, then
    transport to `to` (spawn `spawn`). `by` is "door" or "transporter"."""

    map_name: str
    x: float
    y: float
    to: str
    spawn: int
    by: str


class Travel:
    def __init__(self, world: World, act: Actions) -> None:
        self.world = world
        self.act = act
        self.G = world.G

    # region walk-to
    async def walk_to(self, x: float, y: float) -> bool:
        """Walk to (x, y) on this map, around the walls. If (x, y) is not
        walkable, walk to the nearest walkable point (at most 320 px away).
        True when we arrived; False when there is no path, or when something
        stopped the walk: a `correction`, a death, a door, or jail. The caller
        decides again on its next tick."""
        self.world.advance()
        me = self.world.me
        map_name, m = me["map"], me["m"]  # `m`: the map counter; it changes on each map change
        grid = Grid.for_map(self.G, map_name)
        if not grid.safe(x, y):
            k = grid.nearest_free(x, y)
            if k < 0:
                return False
            x, y = grid.point(k)
        path = grid.find_path(me["x"], me["y"], x, y)
        if path is None:
            return False
        for px, py in path:
            arrived = await self.act.move_to(px, py)
            if me["map"] != map_name or me["m"] != m or me.get("rip"):
                return False  # we left this map, or died
            if not arrived:
                return False  # a correction: our position was wrong
        return True
    # endregion walk-to

    # region transport
    async def transport(self, map_name: str, spawn: int) -> bool:
        """Send `transport` {to, s}: through a door near us, or with the
        transporter NPC near us. Then wait until `new_map` puts us on
        `map_name`. The server answers a door with success and sends `new_map`
        first; the bank answers {in_progress: true}, and `new_map` comes later
        (node/server.js:5887-6056)."""
        me = self.world.me
        m = me["m"]
        r = await self.act.request("transport", {"to": map_name, "s": spawn})
        if r is None or r["failed"]:
            return False  # for example transport_cant_reach: too far from the door
        return await self._wait_until(lambda: me["m"] != m and me["map"] == map_name, NEW_MAP_S)
    # endregion transport

    # region leave-jail
    async def leave_jail(self) -> bool:
        """A line violation (a `move` from or to a point that is not walkable)
        sends the character to the map `jail`. `leave` takes it to `main` spawn
        0, the town (node/server.js:5864-5885). It fails while the character is
        dead, or with more than 5 monsters on it."""
        me = self.world.me
        r = await self.act.request("leave", {})
        if r is None or r["failed"]:
            return False
        return await self._wait_until(lambda: me["map"] != "jail", NEW_MAP_S)
    # endregion leave-jail

    # region route
    def exits(self, map_name: str) -> list[Hop]:
        """The ways out of `map_name`: each door that needs no key, and each
        place of the transporter if the map has one. A door [x, y, w, h, to,
        to_spawn, own_spawn, lock] works from its own spawn point (door[6]);
        the server measures from the box of the door at that spawn
        (node/server.js:5899-5910)."""
        d = self.G["maps"].get(map_name)
        if not d:
            return []
        out: list[Hop] = []
        for door in d.get("doors") or []:
            if len(door) > 7 and door[7]:
                continue  # a locked door ("ulocked", ...): it needs a key first
            spawns = d.get("spawns") or []
            if door[6] < len(spawns):
                sp = spawns[door[6]]
                out.append(Hop(map_name, sp[0], sp[1], door[4], door[5] or 0, "door"))
        for npc in d.get("npcs") or []:
            if npc.get("id") != "transporter":
                continue
            pos = npc.get("position") or (npc.get("positions") or [None])[0]
            if not pos:
                continue
            # G.npcs.transporter.places: map -> the spawn where she sends you.
            places = self.G["npcs"].get("transporter", {}).get("places", {})
            for to, spawn in places.items():
                if to != map_name:
                    out.append(Hop(map_name, pos[0], pos[1], to, int(spawn), "transporter"))
        return out

    def route(self, start: str, goal: str) -> list[Hop] | None:
        """The fewest hops from map `start` to map `goal`: a breadth-first
        search on the graph of maps. [] when we are there, None when no route exists."""
        if start == goal:
            return []
        came: dict[str, Hop | None] = {start: None}  # map -> the hop that reached it
        queue = [start]
        while queue:
            here = queue.pop(0)
            for hop in self.exits(here):
                if hop.to in came or hop.to not in self.G["maps"]:
                    continue
                came[hop.to] = hop
                if hop.to == goal:
                    hops: list[Hop] = []
                    h: Hop | None = hop
                    while h is not None:
                        hops.insert(0, h)
                        h = came.get(h.map_name)
                    return hops
                queue.append(hop.to)
        return None

    async def go_to_map(self, map_name: str) -> bool:
        """Go to `map_name` along route(): for each hop, walk to the door (or
        to the transporter), then transport. True when we are on `map_name`."""
        me = self.world.me
        hops = self.route(me["map"], map_name)
        if hops is None:
            return False
        for hop in hops:
            if not await self.walk_to(hop.x, hop.y):
                return False
            # walk_to can stop short of the point (at the nearest walkable
            # cell). The server then says "transport_cant_reach"; do not even ask.
            reach = DOOR_DIST if hop.by == "door" else TRANSPORTER_DIST
            if math.hypot(me["x"] - hop.x, me["y"] - hop.y) > reach:
                return False
            if not await self.transport(hop.to, hop.spawn):
                return False
        return bool(me["map"] == map_name)
    # endregion route

    async def _wait_until(self, test: Callable[[], bool], seconds: float) -> bool:
        """Poll `test` every 50 ms until it is true, or until `seconds` passed."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if test():
                return True
            await asyncio.sleep(0.05)
        return test()
