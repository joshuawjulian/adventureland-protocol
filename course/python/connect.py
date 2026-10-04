# connect.py: log in, open a socket to a game server, do the handshake, and
# enter the game with one character. Then leave again.
# Needs: pip install -r requirements.txt
# Run:   AL_AUTH=<user>-<auth> AL_CHARACTER=MyMage AL_SERVER=EUI python connect.py
#        (AL_SERVER is optional: without it, the first server of the list.)
import asyncio
import sys

from albot.bot import Bot


async def main() -> None:
    bot = await Bot.connect()  # login, lists, G, socket, handshake
    try:
        w = bot.welcome
        print(f"welcome: {w['region']} {w['name']}, version {w['version']}")
        me = bot.world.me  # `start` has no `name`: `id` is the name
        print(f"in game as {me['id']} ({me['ctype']}, level {me['level']}) "
              f"on {me['map']} at {round(me['x'])},{round(me['y'])}")
        print("OK")
    finally:
        await bot.close()  # the server then saves the character


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as err:
        print(f"{type(err).__name__}: {err}", file=sys.stderr)
        sys.exit(1)
