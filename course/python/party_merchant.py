# party_merchant.py: three fighters and one merchant in one program. The
# fighters farm in a party. The merchant walks to them, takes their loot and
# gold, sells the loot in the town and puts the gold in the bank.
# Needs: pip install -r requirements.txt
# Run:   AL_AUTH=<user>-<auth> AL_CHARACTER=MyWarrior python party_merchant.py [trips]
#        AL_CHARACTER is the leader. The program adds the next two fighters of
#        your character list, and your first merchant.
#        trips: stop after this many merchant trips (the tests use 1). Without it: until Ctrl-C.
# Make a merchant first, if you have none:
#        python party_merchant.py --create-merchant MyMerchant
import asyncio
import sys
from dataclasses import dataclass
from typing import Any

from albot.api import find_character, find_server, login, servers_and_characters
from albot.farmer import Farmer, where
from albot.gdata import GData, load_g
from albot.items import Items, is_loot
from albot.party import Member, Party, connect_member, create_character
from albot.travel import Travel

TICK = 0.1  # s

# region rules
FIGHTERS = 3  # the live limit: 3 characters that fight, plus merchants (game guide, "Many characters and bots")
GIVE_DIST = 300  # `send` works within 400 px on the same map (node/server.js:8463-8560)
FIGHTER_GOLD = 20000  # a fighter keeps this much gold for potions, and gives the rest
MERCHANT_GOLD = 50000  # the merchant keeps this much, and banks the rest


def give(G: GData, it: Any) -> bool:
    """A fighter keeps only its potions. Everything else goes to the merchant:
    loot to sell, and jewelry that the merchant compounds later."""
    if not it or it["name"] == "placeholder" or it.get("l"):
        return False
    d = G["items"].get(it["name"])
    return d is None or d["type"] != "pot"
# endregion rules


@dataclass
class Crew:
    """One character and its tools. Only fighters have a Farmer."""

    m: Member
    travel: Travel
    items: Items
    party: Party
    farmer: Farmer | None


async def main() -> None:
    # region choose
    auth = await login()
    lists = await servers_and_characters(auth)
    characters = lists["characters"]
    if len(sys.argv) > 1 and sys.argv[1] == "--create-merchant":
        name = sys.argv[2] if len(sys.argv) > 2 else ""
        await create_character(auth, name, "merchant")
        print(f"created the merchant {name}. Run the program again without --create-merchant.", flush=True)
        return
    trips = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    server = find_server(lists["servers"])  # AL_SERVER
    leader = find_character(characters)  # AL_CHARACTER
    if leader["type"] == "merchant":
        raise RuntimeError("AL_CHARACTER must be a fighter: it leads the party")
    fighters = ([leader] + [c for c in characters
                            if c["type"] != "merchant" and c["name"] != leader["name"]])[:FIGHTERS]
    merchant_character = next((c for c in characters if c["type"] == "merchant"), None)
    if merchant_character is None:
        raise RuntimeError("no merchant on this account: run with --create-merchant <Name> first")
    print(f"team: {', '.join(c['name'] for c in fighters)}; merchant: {merchant_character['name']}", flush=True)
    # endregion choose

    # region connect
    G = await load_g()  # one G for all four
    crew: list[Crew] = []
    try:
        for c in fighters + [merchant_character]:
            m = await connect_member(auth, server, c, G)
            me = m.world.me
            print(f"in game as {me['id']} ({me['ctype']}, level {me['level']}) on {me['map']} at {where(me)}",
                  flush=True)
            travel = Travel(m.world, m.act)
            # Only fighters farm. (A Farmer also prints each chest that opens for us.)
            farmer = Farmer(m.world, m.act, m.cooldowns, travel, f"{m.name}: ") if c["type"] != "merchant" else None
            crew.append(Crew(m, travel, Items(m.world, m.act, m.budget), Party(m.world, m.act), farmer))
        await run(crew, G, trips)
    finally:
        for c2 in crew:
            await c2.m.close()
    print("OK", flush=True)
    # endregion connect


async def run(crew: list[Crew], G: GData, trips: int) -> None:
    lead, others, merchant = crew[0], crew[1:], crew[-1]
    fighters = crew[:-1]
    stop = asyncio.Event()

    # region party
    # The leader invites each one; each waits for its `invite`, then accepts.
    for c in others:
        await lead.party.invite(c.m.name)
        if not await c.party.wait_invite(lead.m.name):
            raise RuntimeError(f"{c.m.name} got no invitation")
        r = await c.party.accept(lead.m.name)
        if r is None or r["failed"]:
            raise RuntimeError(f"{c.m.name} could not join: {r['response'] if r else 'no answer'}")
    for _ in range(50):
        if len(lead.party.list) >= len(crew):
            break
        await asyncio.sleep(0.1)
    print(f"party: {', '.join(lead.party.list)}", flush=True)
    # endregion party

    # region fighter
    async def fighter_loop(f: Crew) -> None:
        """A fighter farms. When the merchant is near, it gives its loot and gold."""
        world = f.m.world
        me = world.me
        while not stop.is_set():
            await asyncio.sleep(TICK)
            if f.farmer:
                await f.farmer.tick()
            world.advance()
            near = world.players.get(merchant.m.name)  # the merchant, if it is in our view
            if near is None or world.distance(me, near) > GIVE_DIST:
                continue
            n = 0
            for num in range(len(me["items"])):
                it = me["items"][num]
                if not give(G, it):
                    continue
                r = await f.items.send_item(merchant.m.name, num, it.get("q", 1))
                if r is not None and not r["failed"]:
                    n += 1
            # Gold only above twice the reserve: not a `send` for each small chest.
            gold = me["gold"] - FIGHTER_GOLD if me["gold"] > 2 * FIGHTER_GOLD else 0
            if gold > 0:
                await f.items.send_gold(merchant.m.name, gold)
            if n or gold:
                print(f"{f.m.name}: gave {n} item(s) and {gold} gold to {merchant.m.name}", flush=True)
    # endregion fighter

    # region merchant
    def has_loot(f: Crew) -> bool:
        return any(give(G, it) for it in f.m.world.me["items"])

    async def merchant_trip() -> bool:
        """The merchant: wait for loot, collect it, sell it, bank the gold."""
        me = merchant.m.world.me
        name = merchant.m.name
        # 1. Wait until a fighter has something to give.
        while not any(has_loot(f) for f in fighters):
            await asyncio.sleep(0.5)
        # 2. Go to each fighter with loot, and wait (10 s at most) until it gave all.
        for f in fighters:
            if not has_loot(f):
                continue
            fm = f.m.world.me
            print(f"{name}: walk to {f.m.name} at {where(fm)}", flush=True)
            await merchant.travel.walk_to(fm["x"], fm["y"])
            for _ in range(50):
                if not has_loot(f):
                    break
                await asyncio.sleep(0.2)
        # 3. Sell the loot in the town. Keep the jewelry: three of a kind compound.
        shop = merchant.items.npc_selling("hpot0")
        if shop is None:
            raise RuntimeError("no shop on this map")
        print(f"{name}: walk to {shop.id} at {round(shop.x)},{round(shop.y)}", flush=True)
        if not await merchant.travel.walk_to(shop.x, shop.y):
            return False
        sold, gold = 0, 0
        for num in range(len(me["items"])):
            it = me["items"][num]
            if not is_loot(G, it):
                continue
            r = await merchant.items.sell(num, it.get("q", 1))
            if r is not None and not r["failed"]:
                sold += 1
                gold += r["gold"]
        print(f"{name}: sold {sold} item(s): +{gold} gold", flush=True)
        # 4. The bank: the door is north of the town. Deposit, then go back out.
        if not await merchant.travel.go_to_map("bank"):
            return False
        r = await merchant.items.deposit(max(0, me["gold"] - MERCHANT_GOLD))
        print(f"{name}: in the bank: deposited {r['gold'] if r and not r['failed'] else 0} gold", flush=True)
        if not await merchant.travel.go_to_map("main"):
            return False
        print(f"{name}: back on main at {where(me)}", flush=True)
        return True
    # endregion merchant

    # region run
    fighting = asyncio.gather(*(fighter_loop(f) for f in fighters))
    try:
        done = 0
        while trips == 0 or done < trips:
            if await merchant_trip():
                done += 1
    finally:
        stop.set()  # the fighters end their loops
        await fighting
    # endregion run


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("stopped", flush=True)  # Ctrl-C: asyncio.run cancels main; `finally` closes the sockets
    except Exception as err:
        print(f"{type(err).__name__}: {err}", file=sys.stderr)
        sys.exit(1)
