# farm.py: a farming bot. It kills monsters of the Mainland ladder, loots,
# heals, respawns, leaves jail, and reconnects with the course's reconnect
# rule.
# Needs: pip install -r requirements.txt
# Run:   AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger python farm.py [seconds]
#        seconds: stop after this time (the tests use 25). Without it: until Ctrl-C.
import asyncio
import signal
import sys
import time
from typing import Any

from albot.bot import Bot, reconnect_delay_ms
from albot.farmer import Farmer, where
from albot.travel import Travel

TICK = 0.1  # s: one decision every 100 ms: fast enough, and cheap in call-cost
STABLE_S = 5 * 60  # after a session of 5 min, the reconnect wait starts again at the first value

# region stop
# Ctrl-C (SIGINT) or `docker stop` (SIGTERM): finish this tick, close the
# socket, print the summary. A second Ctrl-C stops at once.
stopping = asyncio.Event()


def on_signal() -> None:
    if stopping.is_set():
        sys.exit(1)
    stopping.set()
    print("stopping (press Ctrl-C again to stop at once)", flush=True)


async def wait(seconds: float) -> None:
    """A sleep that ends early when we stop."""
    try:
        await asyncio.wait_for(stopping.wait(), seconds)
    except TimeoutError:
        pass
# endregion stop


async def main() -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, on_signal)
        except NotImplementedError:
            pass  # Windows: Ctrl-C raises KeyboardInterrupt instead
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 0
    started = time.monotonic()
    end_at = started + seconds if seconds > 0 else float("inf")
    kills = 0
    attempt = 0  # failed tries in a row, for reconnect_delay_ms
    last: dict[str, Any] = {}  # our character in the last session

    # region session
    while not stopping.is_set() and time.monotonic() < end_at:
        # 1. Connect. A failure (the server is full, the save of the last
        #    session still runs, ...) waits as the reconnect rule says, then tries again.
        try:
            bot = await Bot.connect()
        except Exception as err:
            ms = reconnect_delay_ms(attempt)
            attempt += 1
            print(f"connect failed: {err}; try again in {ms / 1000:g} s", flush=True)
            await wait(ms / 1000)
            continue
        session = time.monotonic()
        me = bot.world.me
        last = me
        print(f"in game as {me['id']} ({me['ctype']}, level {me['level']}) on {me['map']} at {where(me)}", flush=True)

        # 2. Play until we stop, the time is over, or the socket closes.
        #    AlSocket's local `disconnect` event has the reason; a send on a
        #    closed socket raises, so the except below is the same case.
        lost: list[str] = []  # the reason, when the socket closed
        bot.world.listen("disconnect", lambda reason: lost.append(str(reason)))
        bot.world.listen("disconnect_reason", lambda reason: print(f"the server says: {reason}", flush=True))
        farmer = Farmer(bot.world, bot.act, bot.cooldowns, Travel(bot.world, bot.act))
        try:
            while not stopping.is_set() and not lost and time.monotonic() < end_at:
                await asyncio.sleep(TICK)
                await farmer.tick()
                farmer.next_type()  # a stronger monster when this one is too easy
        except Exception as err:
            if not lost:
                lost.append(str(err))
        kills += farmer.kills
        reason = lost[0] if lost else None  # read it first: close() fires our own `disconnect` too
        await bot.close()
        if reason is None:
            break  # we stopped, or the time is over

        # 3. The reconnect rule: wait, then make a new socket and a full handshake.
        if time.monotonic() - session >= STABLE_S:
            attempt = 0
        ms = reconnect_delay_ms(attempt)
        attempt += 1
        print(f"disconnected: {reason}; reconnect in {ms / 1000:g} s", flush=True)
        await wait(ms / 1000)
    # endregion session

    secs = round(time.monotonic() - started)
    print(f"farmed {secs} s: {kills} kill(s), level {last.get('level')}, {last.get('gold')} gold", flush=True)
    print("OK", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("stopped", flush=True)  # Windows: no signal handler, so Ctrl-C ends here
    except Exception as err:
        print(f"{type(err).__name__}: {err}", file=sys.stderr)
        sys.exit(1)
