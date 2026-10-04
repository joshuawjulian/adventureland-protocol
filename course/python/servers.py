# servers.py: get the list of game servers over HTTP, and print the WebSocket
# URL of each one. Standalone: it uses no albot module.
# Needs: pip install httpx==0.27.2
# Run:   python servers.py      (AL_BASE_URL=http://localhost:8022 for the test server)
import asyncio
import os
from dataclasses import dataclass

import httpx


@dataclass
class Server:
    region: str  # "EU", "US", "ASIA"
    name: str  # "I", "II", "PVP", ...
    address: str  # the host (and port), for example "eu1.adventure.land"
    path: str  # the Socket.IO path, for example "/ws1/"


async def main() -> None:
    # The website and its HTTP API. Not a game server.
    base = (os.environ.get("AL_BASE_URL") or "https://adventure.land").rstrip("/")
    async with httpx.AsyncClient(timeout=15) as http:  # 15 s: generous for one request
        res = await http.get(f"{base}/api/get_servers")
    print("status:", res.status_code, res.headers["content-type"])  # 200 = OK
    res.raise_for_status()  # an exception for a 4xx or 5xx status

    body = res.json()  # a dict made from the JSON text
    servers = [
        Server(s["region"], s["name"], s["address"], s["path"])
        for s in body["servers"]  # a missing key raises KeyError here
    ]
    # The game socket follows the scheme of the website: http -> ws, https -> wss.
    scheme = "wss" if base.startswith("https:") else "ws"
    for s in servers:
        # The path must end with exactly one "/" (the server matches "/ws1/").
        url = (f"{scheme}://{s.address}{s.path.rstrip('/')}/"
               "?EIO=4&transport=websocket&map_protocol=1&no_graphics=1")
        print(f"{s.region} {s.name}: {url}")


asyncio.run(main())
