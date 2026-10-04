# world.py: our copy of the game world. The server sends changes; this module
# keeps the result: our character (`me`), the monsters, the other players,
# and the chests on the ground.
#
# Create the World BEFORE you send `loaded` and `auth`: its handlers must be
# in place when `start` and the first `entities` arrive.
#
# An entity (me, a monster, a player) is the server's JSON object as a plain
# dict. `player` merges into `me` field by field; `entities` replaces each
# entity that it lists. Positions are in px; x is the center, y is the feet.
import math
import time
from typing import Any, Callable, cast

from .alsocket import AlSocket
from .gdata import GData

Entity = dict[str, Any]
Handler = Callable[[Any], object]  # object: return values are ignored


def _num(e: Entity, key: str) -> float:
    """A number field of an entity; a missing (or null) field counts as 0."""
    value = e.get(key)
    return float(value) if isinstance(value, (int, float)) else 0.0


# region step
def step(e: Entity, ms: float) -> None:
    """Move one entity forward in time, the way the server does: in a straight
    line toward going_x/going_y at `speed` px per second."""
    if not e.get("moving"):
        return
    dx, dy = _num(e, "going_x") - _num(e, "x"), _num(e, "going_y") - _num(e, "y")
    left = math.hypot(dx, dy)  # the distance still to go
    travel = _num(e, "speed") * ms / 1000
    if travel >= left:  # it arrives in this step
        e.update(x=e["going_x"], y=e["going_y"], moving=False)
    else:
        e["x"] = _num(e, "x") + dx / left * travel
        e["y"] = _num(e, "y") + dy / left * travel
# endregion step


class World:
    # region constructor
    def __init__(self, sock: AlSocket, G: GData) -> None:
        self.sock = sock
        self.G = G
        self.me: Entity = {}  # our character; empty until `start`
        self.monsters: dict[str, Entity] = {}  # id -> monster
        self.players: dict[str, Entity] = {}  # id -> other player or NPC (never us)
        self.chests: dict[str, Entity] = {}  # chest id -> the `drop` payload
        self._handlers: dict[str, list[Handler]] = {}
        # When advance() last moved each entity (time.monotonic() seconds).
        # An update from the server resets the time of the entities it lists.
        self._moved_at: dict[str, float] = {}
        self._me_moved_at = time.monotonic()

        self.listen("start", self.on_start)
        self.listen("player", self.on_player)
        self.listen("entities", self.apply_entities)
        self.listen("new_map", self.on_new_map)
        # death: a monster died. disappear: an entity left our view, or the game.
        self.listen("death", lambda d: self.monsters.pop(d["id"], None))
        self.listen("disappear", self._on_disappear)
        # drop: a chest for us (or our party). chest_opened: someone opened it.
        self.listen("drop", lambda d: self.chests.__setitem__(d["id"], d))
        self.listen("chest_opened", lambda d: self.chests.pop(d.get("id"), None))
        # correction: the server disagreed with the position of our last `move`.
        self.listen("correction", self._on_correction)
    # endregion constructor

    def _on_correction(self, data: Entity) -> None:
        self.me.update(x=data["x"], y=data["y"])
        self._me_moved_at = time.monotonic()  # this x, y is true now

    # region listen
    def listen(self, name: str, handler: Handler) -> None:
        """Call handler(data) for each `name` event. One table from event name to
        handlers, so that hitchhikers (events inside `player`) reach the same
        handlers as events that arrive alone."""
        if name not in self._handlers:
            self._handlers[name] = []
            # Only the first listen() of a name subscribes to the socket.
            self.sock.on(name, lambda data: self.dispatch(name, data))
        self._handlers[name].append(handler)

    def dispatch(self, name: str, data: Any) -> None:
        """Give `data` to every handler of `name`, in the order of listen()."""
        for handler in self._handlers.get(name, []):
            handler(data)
    # endregion listen

    # region on-start
    def on_start(self, data: Entity) -> None:
        """`start`: our full character, plus the first view as `entities`.
        Note: `start` has no `name`; `id` is the name of the character."""
        self.me.clear()
        self.me.update({k: v for k, v in data.items() if k != "entities"})
        self._me_moved_at = time.monotonic()
        self.apply_entities(data["entities"])
    # endregion on-start

    # region on-player
    def on_player(self, data: Entity) -> None:
        """`player`: changed fields of our character. Merge them into `me`."""
        self.me.update({k: v for k, v in data.items() if k != "hitchhikers"})
        if "x" in data:
            self._me_moved_at = time.monotonic()  # a fresh position from the server
        # Hitchhikers: [event, payload] pairs that rode along with this update.
        # Handle each one as if it arrived alone.
        for event, payload in data.get("hitchhikers") or []:
            self.dispatch(event, payload)
    # endregion on-player

    # region apply-entities
    def with_defaults(self, monster: Entity) -> Entity:
        """A monster has only the fields that differ from G.monsters[type]
        (node/server.js:1003-1071). Fill the others from G. max_hp is G's `hp`."""
        default = cast(dict[str, Any], self.G["monsters"].get(monster.get("type", ""), {}))
        return {**default, "max_hp": default.get("hp"), **monster}  # the monster's own fields win

    def apply_entities(self, data: Entity) -> None:
        if data.get("in") != self.me.get("in"):
            return  # an update for an instance that we left (or before `start`)
        if data.get("type") == "all":  # a full view: forget everything first
            self.monsters.clear()
            self.players.clear()
        now = time.monotonic()
        # Each object is the complete state of that entity: replace, do not merge.
        for m in data.get("monsters", []):
            self.monsters[m["id"]] = self.with_defaults(m)
            self._moved_at[m["id"]] = now
        for p in data.get("players", []):
            if p["id"] != self.me.get("id"):  # a full view can include us
                self.players[p["id"]] = p
                self._moved_at[p["id"]] = now
    # endregion apply-entities

    def _on_disappear(self, data: Entity) -> None:
        self.monsters.pop(data["id"], None)
        self.players.pop(data["id"], None)

    # region on-new-map
    def on_new_map(self, data: Entity) -> None:
        """`new_map`: we are on another map (a door, a respawn, jail). `m` is the
        map counter that each `move` must repeat."""
        self.me.update(map=data["name"], x=data["x"], y=data["y"], m=data["m"], moving=False)
        self.me["in"] = data["in"]  # `in` is a Python keyword: no keyword argument
        self._me_moved_at = time.monotonic()
        self.apply_entities(data["entities"])  # always type "all"
    # endregion on-new-map

    # region advance
    def advance(self) -> None:
        """Move me, the monsters and the players forward to now. Each entity moves
        by the time since the last advance(), or since the server last told us
        its position. Call this before you read positions; no timer calls it."""
        now = time.monotonic()
        if self.me:
            step(self.me, (now - self._me_moved_at) * 1000)
        self._me_moved_at = now
        for table in (self.monsters, self.players):
            for eid, e in table.items():
                step(e, (now - self._moved_at.get(eid, now)) * 1000)
                self._moved_at[eid] = now
    # endregion advance

    # region distance
    def _box(self, e: Entity) -> tuple[float, float]:
        """The hit box (width, height) of an entity, as the server sees it.
        A monster: G.dimensions[type] (24 x 24 when G has no entry), times
        G.monsters[type].size (get_monster_dimensions, js/old_common_functions.js:692).
        A character: its width and height; the server gives every character
        26 x 36 (node/server.js:11782-11783), and the client copy has no such
        fields, so 26 x 36 is the default."""
        mtype = e.get("type")
        if isinstance(mtype, str) and mtype in self.G["monsters"]:
            w, h = self.G["dimensions"].get(mtype, [24, 24])[:2]
            size = self.G["monsters"][mtype].get("size")
            return (round(w * size), round(h * size)) if size else (w, h)
        return (_num(e, "width") or 26, _num(e, "height") or 36)

    def distance(self, a: Entity, b: Entity) -> float:
        """The gap between two hit boxes: the distance that the server compares
        with `range` (distance(), js/old_common_functions.js:707-740). A box is
        `width` wide, centered on x, and `height` tall above y (y is the feet).
        Boxes that touch or overlap are at 0."""
        if "map" in a and "map" in b and a["map"] != b["map"]:
            return 99999999  # the source's value for "not on the same map"
        aw, ah = self._box(a)
        bw, bh = self._box(b)
        ax, ay, bx, by = _num(a, "x"), _num(a, "y"), _num(b, "x"), _num(b, "y")
        dx = max(bx - bw / 2 - (ax + aw / 2), ax - aw / 2 - (bx + bw / 2), 0)
        dy = max(by - bh - ay, ay - ah - by, 0)
        return math.hypot(dx, dy)
    # endregion distance

    def nearest_monster(self, mtype: str | None = None) -> Entity | None:
        """The monster (of type `mtype`, if given) closest to `me`, or None."""
        best: Entity | None = None
        best_d = math.inf
        for m in self.monsters.values():
            if mtype is not None and m.get("type") != mtype:
                continue
            d = self.distance(self.me, m)
            if d < best_d:
                best, best_d = m, d
        return best
