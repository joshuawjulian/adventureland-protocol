# al_test.py: take AlSocket through the Adventure Land handshake on the local
# test server: welcome, loaded, auth, start, then 3 s of idle time and a ping.
# Needs: pip install websockets==13.1   (it imports only albot/alsocket.py)
# Run:   python al_test.py      (AL_WS_URL: the game server URL; default: the test server's)
import asyncio
import os

from albot.alsocket import AlSocket

# The fixed account of the test server (course/test-server/accounts.js).
# HARD-CODED on purpose: Part 1 has no login code yet, and this token works
# only on the test server. Never put a real token in code; use AL_AUTH.
TEST_USER = "US_tester"
TEST_AUTH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
TEST_CHARACTER = "CH_tester"  # the id of the character "Tester"


async def main() -> None:
    url = os.environ.get("AL_WS_URL") or "ws://localhost:8022/ws1/?EIO=4&transport=websocket"

    sock = await AlSocket.connect(url)
    print("connected to", url)
    sock.on("game_error", lambda msg: print("game_error:", msg))
    sock.on("disconnect", lambda reason: print("disconnect:", reason))

    # 1. The server sends "welcome" to each new socket.
    welcome = await sock.wait_for("welcome")
    print(f"welcome: {welcome['region']} {welcome['name']}, version {welcome['version']}")

    # 2. Send "loaded". The reply is one full "entities" view (type "all").
    #    Register the wait BEFORE the emit, so that a fast reply can't pass first.
    snapshot = sock.wait_for("entities", lambda d: d["type"] == "all")
    await sock.emit("loaded", {"success": 1, "width": 1920, "height": 1080, "scale": 2})
    print(f"entities: {len((await snapshot)['monsters'])} monster(s)")

    # 3. Log in the character. `start` is the whole character; it has no
    #    `name` field: `id` is the name.
    started = sock.wait_for("start")
    await sock.emit("auth", {
        "user": TEST_USER,
        "auth": TEST_AUTH,
        "character": TEST_CHARACTER,
        "no_html": "1",  # "a program controls this character"
        "passphrase": "",  # only test servers check it
    })
    me = await started
    print(f"start: {me['id']} on {me['map']} at {round(me['x'])},{round(me['y'])}")

    # 4. Do nothing for 3 s. The server pings during this time (every 4 s on
    #    the live servers, node/server.js:83). If our pong does not work, the
    #    server drops us and the next step fails.
    await asyncio.sleep(3)
    ack = sock.wait_for("ping_ack", lambda d: d["id"] == "42")
    await sock.emit("ping_trig", {"id": "42"})
    print("ping_ack after 3 s idle:", (await ack)["id"])

    print("OK")
    await sock.close()  # our "disconnect" handler prints the reason


asyncio.run(main())
