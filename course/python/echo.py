# echo.py: open a WebSocket, send one text message, and read the reply.
# Standalone: it uses no albot module.
# Needs: pip install websockets==13.1
# Run:   python echo.py      (AL_ECHO_URL: an echo server; default: the test server's)
import asyncio
import os

from websockets.asyncio.client import connect


async def main() -> None:
    url = os.environ.get("AL_ECHO_URL") or "ws://localhost:8022/echo"
    async with connect(url) as ws:  # the end of the block closes with code 1000
        print("connected")
        await ws.send("hello")  # one text frame
        reply = await ws.recv()  # waits here; other tasks can run meanwhile
        print("received:", reply)
    print("closed")


asyncio.run(main())
