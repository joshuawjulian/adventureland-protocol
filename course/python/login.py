# login.py: log in over HTTP, then list the game servers and your characters.
# Needs: pip install -r requirements.txt
# First run:  AL_EMAIL=you@example.com AL_PASSWORD=... python login.py
# Later runs: AL_AUTH=<user>-<auth> python login.py   (the first run prints this value)
import asyncio
import sys

from albot import api


async def main() -> None:
    auth = await api.login()  # AL_AUTH, or one password login
    print(f"user id: {auth.user}")
    lists = await api.servers_and_characters(auth)

    # The AL_SERVER value is region + name, for example "EUI".
    print("servers (AL_SERVER, players, address, path):")
    for s in lists["servers"]:
        print(f"  {s['region'] + s['name']:<8} {s['players']:>3}  {s['address']}  {s['path']}")

    print("characters (AL_CHARACTER, class, level, id, status):")
    for c in lists["characters"]:
        # `server` is there only while the character is online.
        status = f"online on {c['server']}" if c.get("server") else "offline"
        print(f"  {c['name']:<8} {c['type']:<9} {c['level']:>3}  {c['id']}  {status}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as err:  # a short message instead of a traceback
        print(err, file=sys.stderr)
        sys.exit(1)
