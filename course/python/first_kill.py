# first_kill.py: the checkpoint of Part 2. Enter the game, heal, walk to the
# nearest goo, kill it, open its chest, and leave.
# Needs: pip install -r requirements.txt
# Run:   AL_AUTH=<user>-<auth> AL_CHARACTER=MyWarrior python first_kill.py
#        (a goo must be in view: on the live game, start near the goos of main)
import asyncio
import math
import sys
import time
from typing import Any

from albot.bot import Bot

TICK = 0.1  # s: one decision each 100 ms is quick enough, and cheap in call-cost
HEAL_BELOW = 0.7  # drink a potion under 70 % hp
TIME_LIMIT = 90  # s: fail when there is no kill by then


def where(e: dict[str, Any]) -> str:
    return f"{round(e['x'])},{round(e['y'])}"


async def revive(bot: Bot) -> None:
    """Dead: wait the rest of the 12 s, respawn, and say where we are."""
    died_at = bot.act.died_at or time.monotonic()
    print(f"died; respawn in {max(0, round(died_at + 12 - time.monotonic()))} s")
    if not await bot.act.respawn():
        raise RuntimeError("respawn failed")
    print(f"respawned at {where(bot.world.me)}")


async def hunt(bot: Bot) -> None:
    world, act, cooldowns = bot.world, bot.act, bot.cooldowns
    me = world.me  # the same dict for the whole session; updates go into it

    # Ids of monsters that died: a `death` event, or a `hit` with `kill`.
    killed: set[str] = set()
    world.listen("death", lambda d: killed.add(d["id"]))
    world.listen("hit", lambda d: killed.add(d["id"]) if d.get("kill") else None)
    world.listen("chest_opened", lambda d: None if d.get("gone") else print(
        f"chest {d['id']}: +{d.get('gold', 0)} gold, {len(d.get('items', []))} item(s)"))

    if me.get("rip"):
        await revive(bot)
    target_id: str | None = None
    while True:
        world.advance()  # positions now, before we decide anything
        if me.get("rip"):
            await revive(bot)
            target_id = None  # the respawn changed the map view
            continue
        if me["hp"] < HEAL_BELOW * me["max_hp"] and cooldowns.ready("potion"):
            if await act.heal("hp"):  # the `player` update came before the reply
                print(f"heal hp: {round(me['hp'])}/{round(me['max_hp'])}")

        if target_id is not None and target_id in killed:
            break
        # Look the goo up again each time: `entities` replaces its dict.
        goo = world.monsters.get(target_id or "")
        if goo is None:  # no target yet, or it left our view
            goo = world.nearest_monster("goo")  # None: no goo in view; wait for one
            if goo is not None:
                target_id = goo["id"]
                print(f"target: goo {target_id} at {where(goo)}")
        elif world.distance(me, goo) > me["range"]:
            # Walk to a point at range - 10 px from the goo, on our side of it.
            # 10 px: a margin, because the goo moves while we walk.
            dx, dy = me["x"] - goo["x"], me["y"] - goo["y"]
            gap = math.hypot(dx, dy) or 1
            stand = max(me["range"] - 10, 0)
            await act.move_to(goo["x"] + dx / gap * stand, goo["y"] + dy / gap * stand)
        elif cooldowns.ready("attack"):
            await act.attack(goo["id"])  # skill_timeout then sets the cooldown
        await asyncio.sleep(TICK)

    print(f"killed goo {target_id}")
    # The chest (`drop`) comes just before `death`. Wait up to 3 s for it.
    for _ in range(30):
        if world.chests:
            break
        await asyncio.sleep(0.1)
    await act.open_chests()  # the chest_opened handler above prints each one
    print(f"xp: {round(me['xp'])}/{round(me['max_xp'])}, level {me['level']}")


async def main() -> None:
    bot = await Bot.connect()
    try:
        me = bot.world.me
        print(f"in game as {me['id']} ({me['ctype']}, level {me['level']}) on {me['map']} at {where(me)}")
        try:
            async with asyncio.timeout(TIME_LIMIT):
                await hunt(bot)
        except TimeoutError:
            raise RuntimeError(f"no kill in {TIME_LIMIT} s") from None
        print("OK")
    finally:
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as err:
        print(f"{type(err).__name__}: {err}", file=sys.stderr)
        sys.exit(1)
