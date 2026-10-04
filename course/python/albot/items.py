# items.py: the inventory and the NPC services: buy, sell, equip, give items
# and gold to another character, upgrade and compound.
#
# me["items"] is the inventory: a list of 42 slots (G: isize), each an item
# {name, q?, level?, ...} or None. me["slots"] is the equipment: slot name ->
# item. me["esize"] is the number of empty inventory slots. All three come in
# `start` and `player` (node/server.js:855-1001).
import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable

from .actions import Actions, GameResponse, normalize
from .budget import Budget
from .gdata import GData
from .world import World

# region rules
# An NPC sells, buys, upgrades and compounds within 400 px (B.sell_dist,
# node/server.js:220). Stand a little nearer: our position is an estimate.
NPC_DIST = 350

# The equipment slots for each item type (G.items[name].type). Rings and
# earrings have two slots.
SLOTS_FOR_TYPE: dict[str, list[str]] = {
    "weapon": ["mainhand"], "shield": ["offhand"], "source": ["offhand"], "quiver": ["offhand"],
    "misc_offhand": ["offhand"], "helmet": ["helmet"], "chest": ["chest"], "pants": ["pants"],
    "shoes": ["shoes"], "gloves": ["gloves"], "belt": ["belt"], "amulet": ["amulet"], "orb": ["orb"],
    "cape": ["cape"], "ring": ["ring1", "ring2"], "earring": ["earring1", "earring2"],
}

# The item types that a bot keeps and never sells (the loot rules of the
# game guide, "A merchant in practice"): potions, scrolls and offerings, and
# jewelry, which you compound in groups of three.
KEEP_TYPES = ["pot", "uscroll", "cscroll", "pscroll", "offering", "ring", "earring", "amulet", "belt", "orb"]


def is_loot(G: GData, item: Any) -> bool:
    """Is this inventory item loot to sell? Not a kept type, not locked (`l`),
    not an upgrade in progress ("placeholder")."""
    if not item or item.get("name") == "placeholder" or item.get("l"):
        return False
    d = G["items"].get(item["name"])
    return d is not None and d["type"] not in KEEP_TYPES
# endregion rules


@dataclass(frozen=True)
class Npc:
    """An NPC on our map: its id in G.npcs and its position."""

    id: str
    x: float
    y: float


class Items:
    def __init__(self, world: World, act: Actions, budget: Budget) -> None:
        self.world = world
        self.act = act
        self.budget = budget
        self.G = world.G
        # The results of upgrade and compound come later, as hitchhikers inside
        # a `player` update. world.listen gets them too (World.on_player
        # dispatches them), so keep the last 50 game_response events and
        # search them. Each one has a sequence number.
        self._log: list[tuple[int, GameResponse]] = []
        self._seq = 0
        world.listen("game_response", self._on_response)

    def _on_response(self, d: Any) -> None:
        self._seq += 1
        self._log.append((self._seq, normalize(d)))
        del self._log[:-50]

    # region find
    def find(self, name: str, level: int | None = None) -> int:
        """The slot number of the first item called `name` (and of `level`, if
        given), or -1."""
        for num, it in enumerate(self.world.me.get("items") or []):
            if it and it["name"] == name and (level is None or it.get("level", 0) == level):
                return num
        return -1

    def count(self, name: str) -> int:
        """How many of `name` we carry (stacks count their `q`)."""
        return sum(it.get("q", 1) for it in self.world.me.get("items") or [] if it and it["name"] == name)

    def free_slots(self) -> int:
        """The number of empty inventory slots."""
        me = self.world.me
        if isinstance(me.get("esize"), int):
            return int(me["esize"])
        return int(me.get("isize", 42)) - sum(1 for it in me.get("items") or [] if it)

    def npc_selling(self, item: str) -> Npc | None:
        """The NPC on our map that sells `item`, or None. NPCs with an `items`
        list are shops (G.npcs[id].items)."""
        return self._npc(lambda npc: item in (npc.get("items") or []))

    def npc_with_role(self, role: str) -> Npc | None:
        """The NPC on our map with this role, for example "newupgrade" (Cue:
        upgrade and compound) or "merchant" (a shop: it buys any item)."""
        return self._npc(lambda npc: npc.get("role") == role)

    def _npc(self, test: Callable[[dict[str, Any]], bool]) -> Npc | None:
        for n in self.G["maps"].get(self.world.me["map"], {}).get("npcs") or []:
            pos = n.get("position") or (n.get("positions") or [None])[0]
            npc = self.G["npcs"].get(n["id"])
            if pos and npc and test(npc):
                return Npc(n["id"], pos[0], pos[1])
        return None
    # endregion find

    # region shop
    async def buy(self, name: str, quantity: int) -> GameResponse | None:
        """Buy from an NPC within 400 px that sells the item. The answer:
        `buy_success` {cost, num, name, q}, or a failure: "distance" (too far),
        "buy_cost" (not enough gold), "buy_cant_space" (node/server.js:8409-8461)."""
        return await self.act.request("buy", {"name": name, "quantity": quantity})

    async def sell(self, num: int, quantity: int) -> GameResponse | None:
        """Sell to any shop NPC within 400 px for 60 % of G.items[name].g (1 gold
        for a gift item). The answer: `gold_received` {gold} (node/server.js:8046-8096)."""
        return await self.act.request("sell", {"num": num, "quantity": quantity})
    # endregion shop

    # region equip
    async def equip(self, num: int, slot: str | None = None) -> GameResponse | None:
        """Put the item of slot `num` on. Without `slot`, the server chooses one
        from the item type. The old item goes back to the inventory. The answer
        is {response: "data", slot} on success (node/server.js:7643-7915)."""
        return await self.act.request("equip", {"num": num, "slot": slot} if slot else {"num": num})

    async def unequip(self, slot: str) -> GameResponse | None:
        return await self.act.request("unequip", {"slot": slot})

    async def equip_better(self) -> list[str]:
        """Equip each inventory item that is better than what we wear: the slot
        is empty, or it holds the same item at a lower level. A simple rule; the
        game guide ("Gear is more important than level") compares stats.
        Returns "name: slot" for each item that went on."""
        done: list[str] = []
        me = self.world.me
        for num in range(len(me.get("items") or [])):
            it = me["items"][num]
            d = self.G["items"].get(it["name"]) if it else None
            slots = SLOTS_FOR_TYPE.get(d["type"]) if d else None
            if not it or not slots or it["name"] == "placeholder":
                continue
            worn = me.get("slots") or {}
            slot = next((s for s in slots if not worn.get(s)), None) or next(
                (s for s in slots if worn[s]["name"] == it["name"] and worn[s].get("level", 0) < it.get("level", 0)),
                None)
            if not slot:
                continue
            r = await self.equip(num, slot)
            if r is not None and not r["failed"]:  # "cant_equip": not for our class
                done.append(f"{it['name']}: {slot}")
        return done
    # endregion equip

    # region send
    async def send_item(self, name: str, num: int, quantity: int) -> GameResponse | None:
        """Give items to another character on our map within 400 px. The answer:
        `item_sent`, or "distance", "send_no_space" (node/server.js:8463-8560)."""
        return await self.act.request("send", {"name": name, "num": num, "q": quantity})

    async def send_gold(self, name: str, gold: int) -> GameResponse | None:
        """Give gold. Between characters of one account the receiver gets all of
        it; to another account, 2.5 % less (node/server.js:8590-8600)."""
        return await self.act.request("send", {"name": name, "gold": gold})
    # endregion send

    # region bank
    async def deposit(self, gold: int) -> GameResponse | None:
        """Gold into the bank. Only inside the bank (a map with `mount`, which
        Travel.go_to_map("bank") reaches); elsewhere: "bank_unavailable". The
        first answer has place "bank" and the `gold` moved (node/server.js:9257-9282)."""
        return await self.act.request("bank", {"operation": "deposit", "amount": gold})

    async def withdraw(self, gold: int) -> GameResponse | None:
        return await self.act.request("bank", {"operation": "withdraw", "amount": gold})
    # endregion bank

    # region upgrade
    async def upgrade(self, item_num: int, scroll_num: int, calculate: bool = False) -> GameResponse | None:
        """Upgrade the item in slot `item_num` with the scroll in `scroll_num`, at
        the upgrade NPC (within 400 px). `clevel` must be the item's level now,
        or the server says "upgrade_mismatch" (node/server.js:7166-7168).
          calculate=True: the answer is `upgrade_chance` {chance}; nothing is used.
          calculate=False: the scroll is used, the slot holds a "placeholder",
            and the result comes later as a hitchhiker: `upgrade_success` or
            `upgrade_fail` {level, num} (node/server.js:14920-14945). On a fail
            the item is gone.
        A failure before the roll is a bare string ("upgrade_no_scroll") or an
        object with place "upgrade" ("distance"). None: no answer in time."""
        item = self.world.me["items"][item_num]
        payload: dict[str, Any] = {"item_num": item_num, "scroll_num": scroll_num,
                                   "clevel": (item or {}).get("level", 0)}
        if calculate:
            payload["calculate"] = True
        # 30 s: the roll of +N takes 0.5 x N x sqrt(N) s, about 9 s at +7.
        return await self._roll("upgrade", payload, 2 if calculate else 30)

    async def compound(self, nums: list[int], scroll_num: int, calculate: bool = False) -> GameResponse | None:
        """Combine three identical items (same name and level) with a compound
        scroll. The same answers as upgrade, with "compound" in place of
        "upgrade". The roll takes 10 s (node/server.js:7037). On a success the
        item is in nums[0], one level higher; the other two slots are empty."""
        item = self.world.me["items"][nums[0]]
        payload: dict[str, Any] = {"items": nums, "scroll_num": scroll_num,
                                   "clevel": (item or {}).get("level", 0)}
        if calculate:
            payload["calculate"] = True
        return await self._roll("compound", payload, 2 if calculate else 30)

    async def _roll(self, event: str, payload: dict[str, Any], seconds: float) -> GameResponse | None:
        """Send the event, then wait for the first game_response about it: an
        object with this `place`, or a response that starts with "<event>_"
        (the bare-string failures and the late hitchhiker results)."""
        since = self._seq  # only answers that come after the emit
        await self.budget.emit(event, payload)
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for seq, r in self._log:
                if seq > since and (r.get("place") == event or str(r["response"]).startswith(event + "_")):
                    return r
            await asyncio.sleep(0.05)
        return None
    # endregion upgrade
