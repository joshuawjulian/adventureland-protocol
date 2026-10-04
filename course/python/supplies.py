# supplies.py: a farming bot that looks after itself. After each chest it
# wears better gear; when potions or bag space run low, it walks to the town,
# sells the loot, buys potions and the basic armor, and goes back to farm.
# Needs: pip install -r requirements.txt
# Run:   AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger python supplies.py [trips]
#        trips: stop after this many town trips (the tests use 1). Without it: until Ctrl-C.
import asyncio
import math
import sys
from typing import Any

from albot.bot import Bot
from albot.farmer import Farmer, where
from albot.items import NPC_DIST, Items, Npc, is_loot
from albot.travel import Travel

TICK = 0.1  # s

# region rules
# The restock rule (the game guide, "Your first hour" and "Inventory"):
MIN_POTIONS = 20  # go to town below 20 hpot0 or 20 mpot0 ...
MIN_FREE = 5  # ... or below 5 free inventory slots
POTIONS = 50  # buy up to 50 of each (20 gold each: 2,000 gold for both)
KEEP_GOLD = 2000  # never spend the potion money on armor ("Your first day", step 1)
# The basic armor that a new character does not wear, from Gabriel (`basics`).
ARMOR = ["gloves", "coat", "pants"]
# endregion rules


async def main() -> None:
    trips = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    bot = await Bot.connect()
    world, act, G = bot.world, bot.act, bot.G
    me = world.me
    print(f"in game as {me['id']} ({me['ctype']}, level {me['level']}) on {me['map']} at {where(me)}", flush=True)
    travel = Travel(world, act)
    items = Items(world, act, bot.budget)
    farmer = Farmer(world, act, bot.cooldowns, travel)

    # region town
    async def go_near(npc: Npc | None) -> bool:
        """Walk to within NPC_DIST of an NPC. Say so only when we must walk."""
        if npc is None:
            raise RuntimeError("no such NPC on this map")
        world.advance()
        if math.hypot(me["x"] - npc.x, me["y"] - npc.y) <= NPC_DIST:
            return True
        print(f"walk to {npc.id} at {round(npc.x)},{round(npc.y)}", flush=True)
        return await travel.walk_to(npc.x, npc.y)

    async def shop(name: str, quantity: int) -> bool:
        """Buy `quantity` of `name` from the NPC that sells it."""
        if not await go_near(items.npc_selling(name)):
            return False
        r = await items.buy(name, quantity)
        ok = r is not None and not r["failed"]
        print(f"buy {name} x{r['q']}: {r['cost']} gold" if r is not None and ok
              else f"buy {name}: {r['response'] if r else 'no answer'}", flush=True)
        return ok

    async def town_trip() -> bool:
        # 1. Sell the loot to the potion shop (any shop buys any item).
        if not await go_near(items.npc_selling("hpot0")):
            return False
        for num in range(len(me["items"])):
            it: Any = me["items"][num]
            if not is_loot(G, it):
                continue
            r = await items.sell(num, it.get("q", 1))
            if r is not None and not r["failed"]:
                print(f"sell {it['name']}: +{r['gold']} gold", flush=True)
        # 2. Potions, up to POTIONS of each.
        for name in ("hpot0", "mpot0"):
            need = POTIONS - items.count(name)
            if need > 0:
                await shop(name, need)
        # 3. The basic armor that we do not wear, while the gold lasts.
        for name in ARMOR:
            slot = G["items"][name]["type"]  # "gloves", "chest", "pants": the slot has the type's name
            if (me.get("slots") or {}).get(slot) or me["gold"] - G["items"][name]["g"] < KEEP_GOLD:
                continue
            await shop(name, 1)
        for line in await items.equip_better():
            print(f"equip {line}", flush=True)
        print(f"bag: {items.count('hpot0')} hpot0, {items.count('mpot0')} mpot0, "
              f"{items.free_slots()} free slot(s), {me['gold']} gold", flush=True)
        return True
    # endregion town

    # region loop
    chests = [0]  # chests opened so far (a list: the handler changes it)
    seen = 0  # chests that we checked after
    world.listen("chest_opened", lambda r: None if r.get("gone") else chests.__setitem__(0, chests[0] + 1))
    done = 0
    try:
        while trips == 0 or done < trips:
            await asyncio.sleep(TICK)
            await farmer.tick()
            if chests[0] == seen:
                continue
            # After each chest: wear what is better, then check the supplies.
            seen = chests[0]
            for line in await items.equip_better():
                print(f"equip {line}", flush=True)
            hp, mp, free = items.count("hpot0"), items.count("mpot0"), items.free_slots()
            if hp >= MIN_POTIONS and mp >= MIN_POTIONS and free >= MIN_FREE:
                continue
            print(f"supplies low: {hp} hpot0, {mp} mpot0, {free} free slot(s)", flush=True)
            if await town_trip():
                done += 1
            farmer.target = None  # choose again: the old target is far away now
    # endregion loop
    finally:
        await bot.close()
    print("OK", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("stopped", flush=True)  # Ctrl-C: asyncio.run cancels main, and `finally` closes the socket
    except Exception as err:
        print(f"{type(err).__name__}: {err}", file=sys.stderr)
        sys.exit(1)
