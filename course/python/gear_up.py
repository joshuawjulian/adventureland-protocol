# gear_up.py: upgrade a coat to +3 and compound rings in groups of three,
# with the stop rule of the game guide. It farms first until it has a chest
# (gold and rings).
# Needs: pip install -r requirements.txt
# Run:   AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger python gear_up.py
import asyncio
import math
import sys
from typing import Any

from albot.bot import Bot
from albot.farmer import Farmer, where
from albot.items import NPC_DIST, Items, Npc
from albot.travel import Travel

TICK = 0.1  # s

# region rules
# The stop rule (the game guide, "A progression plan"): take a piece to +3
# with no spare copy. Above +3 the chance falls (70 % for +4), so stop and
# use spares ("Step 2"). Also stop when the server's chance, with grace, is
# below 90 %: then a failure is too likely for an item that we wear.
ITEM = "coat"  # 6,000 gold at Gabriel (`basics`)
TARGET_LEVEL = 3
MIN_CHANCE = 0.9
# Jewelry: compound groups of three while the chance is at least 90 %. For
# most jewelry that is +0 -> +1 only (99 %); +2 is 75 %.
# endregion rules


def outcome(r: Any, event: str) -> str:
    """ "success", "fail", or the response of a failure before the roll."""
    if r is None:
        return "no answer"
    if r["response"] == f"{event}_success":
        return "success"
    if r["response"] == f"{event}_fail":
        return "fail"
    return str(r["response"])


async def main() -> None:
    bot = await Bot.connect()
    world, act, G = bot.world, bot.act, bot.G
    me = world.me
    print(f"in game as {me['id']} ({me['ctype']}, level {me['level']}) on {me['map']} at {where(me)}", flush=True)
    travel = Travel(world, act)
    items = Items(world, act, bot.budget)
    farmer = Farmer(world, act, bot.cooldowns, travel)
    try:
        # 1. Farm until one chest opened: the first chest brings gold and rings.
        chests = [0]
        world.listen("chest_opened", lambda r: None if r.get("gone") else chests.__setitem__(0, chests[0] + 1))
        while chests[0] == 0:
            await asyncio.sleep(TICK)
            await farmer.tick()

        async def go_near(npc: Npc | None, within: float = NPC_DIST) -> None:
            """Walk to within `within` px of an NPC (or of a point). Say so only when we must walk."""
            if npc is None:
                raise RuntimeError("no such NPC on this map")
            world.advance()
            if math.hypot(me["x"] - npc.x, me["y"] - npc.y) <= within:
                return
            print(f"walk to {npc.id} at {round(npc.x)},{round(npc.y)}", flush=True)
            if not await travel.walk_to(npc.x, npc.y):
                raise RuntimeError(f"could not walk to {npc.id}")

        async def buy_one(name: str) -> int:
            """Buy one `name` and return its slot number."""
            await go_near(items.npc_selling(name))
            r = await items.buy(name, 1)
            if r is None or r["failed"]:
                raise RuntimeError(f"buy {name}: {r['response'] if r else 'no answer'}")
            print(f"buy {name} x1: {r['cost']} gold", flush=True)
            return int(r["num"])

        # 2. The item to upgrade.
        num = items.find(ITEM)
        if num < 0:
            num = await buy_one(ITEM)

        # 3. Stand where both Lucas (scrolls) and Cue (upgrade, compound) are
        #    within 400 px: the middle of the two (about 140 px from each).
        lucas, cue = items.npc_selling("scroll0"), items.npc_with_role("newupgrade")
        if lucas is None or cue is None:
            raise RuntimeError("no scroll shop or upgrade NPC on this map")
        spot = Npc("scrolls and newupgrade", round((lucas.x + cue.x) / 2), round((lucas.y + cue.y) / 2))
        await go_near(spot, 20)  # 20 px: near the middle, so that both stay within 400 px

        # region upgrade-loop
        while num >= 0 and me["items"][num].get("level", 0) < TARGET_LEVEL:
            level = me["items"][num].get("level", 0)
            scroll = items.find("scroll0")
            if scroll < 0:
                scroll = await buy_one("scroll0")
            # Ask first: the chance includes grace, which only the server knows.
            calc = await items.upgrade(num, scroll, True)
            if calc is None or calc["failed"] or calc["response"] != "upgrade_chance":
                print(f"upgrade {ITEM}: {calc['response'] if calc else 'no answer'}", flush=True)
                break
            if calc["chance"] < MIN_CHANCE:
                print(f"stop: the chance for +{level + 1} is {calc['chance']:.2f}", flush=True)
                break
            r = await items.upgrade(num, scroll)
            result = outcome(r, "upgrade")
            print(f"upgrade {ITEM} +{level} -> +{level + 1}: {result} (chance {calc['chance']:.2f})", flush=True)
            if result != "success" or r is None:
                break  # a fail destroys the item
            num = int(r.get("num", num))
        # endregion upgrade-loop

        # region compound-loop
        def find_group() -> list[int] | None:
            """Three slots with the same name and level, of an item that compounds (G `compound`)."""
            groups: dict[tuple[str, int], list[int]] = {}
            for n, it in enumerate(me["items"]):
                if not it or it.get("l"):
                    continue
                item_def = G["items"].get(it["name"])
                if not item_def or "compound" not in item_def:
                    continue
                groups.setdefault((it["name"], it.get("level", 0)), []).append(n)
            for nums in groups.values():
                if len(nums) >= 3:
                    return nums[:3]
            return None

        group = find_group()
        while group:
            it = me["items"][group[0]]
            level = it.get("level", 0)
            scroll = items.find("cscroll0")
            if scroll < 0:
                scroll = await buy_one("cscroll0")
            calc = await items.compound(group, scroll, True)
            if calc is None or calc["failed"] or calc["response"] != "compound_chance" or calc["chance"] < MIN_CHANCE:
                why = f"{calc['chance']:.2f}" if calc and "chance" in calc else (calc["response"] if calc else "no answer")
                print(f"stop: compound {it['name']} +{level}: {why}", flush=True)
                break
            r = await items.compound(group, scroll)
            result = outcome(r, "compound")
            print(f"compound {it['name']} +{level} x3 -> +{level + 1}: {result} (chance {calc['chance']:.2f})",
                  flush=True)
            if result not in ("success", "fail"):
                break
            group = find_group()
        # endregion compound-loop

        # 4. Wear the results.
        for line in await items.equip_better():
            print(f"equip {line}", flush=True)
        slots = me.get("slots") or {}

        def show(s: str) -> str:
            return f"{slots[s]['name']} +{slots[s].get('level', 0)}" if slots.get(s) else "-"
        print(f"gear: chest {show('chest')}, ring1 {show('ring1')}, ring2 {show('ring2')}, belt {show('belt')}",
              flush=True)
    finally:
        await bot.close()
    print("OK", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as err:
        print(f"{type(err).__name__}: {err}", file=sys.stderr)
        sys.exit(1)
