# bot.py: from nothing to a character in the game. Bot.connect() logs in,
# chooses the server and the character, loads G, opens the socket, does the
# handshake, and makes the world, cooldowns, budget and actions objects.
import asyncio
import os
from typing import Any

from .actions import Actions
from .alsocket import AlSocket
from .api import Auth, Character, Server, find_character, find_server, login, servers_and_characters, socket_url
from .budget import Budget
from .cooldowns import Cooldowns
from .gdata import GData, load_g
from .world import World


class LoginError(Exception):
    """The handshake failed. `reason` says why: the reason of a game_error
    ("password_issue", "ingame", ...), "server_full", "characters_unconfirmed",
    "authorization_in_progress",
    the text of disconnect_reason, the reason of the disconnect, or "timeout"."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"login failed: {reason}")
        self.reason = reason


# region error-reason
def error_reason(e: Any) -> str:
    """The reason of a `game_error` during the handshake. The payload is a dict
    {message, phrase, phrase_args, reason?} (languages/index.js:256-258):
      - a refused `auth` has `reason`: "no_character", "password_issue",
        "mainframe_issue", "ingame", "poker_hand_active", "cancelled"
        (node/server.js:11610-11652);
      - a full server has the phrase "server.game_error.capacity"
        (node/server.js:11587, 11879): we call it "server_full";
      - "server.game_error.characters_unconfirmed": the server could not read
        your other characters (node/server.js:11873-11876). Try again later.
    A bare string (for example "ERROR!") is its own reason."""
    if isinstance(e, str):
        return e
    if not isinstance(e, dict):
        return "unknown"
    if e.get("reason"):
        return str(e["reason"])
    phrase = e.get("phrase")
    if phrase == "server.game_error.capacity":
        return "server_full"
    if isinstance(phrase, str):
        return phrase.split(".")[-1]  # "characters_unconfirmed"
    return str(e.get("message", "unknown"))
# endregion error-reason


# region enter-game
async def enter_game(sock: AlSocket, auth: Auth, character_id: str, timeout_ms: float = 30000) -> Any:
    """The handshake on a connected socket. Returns the `welcome` payload.
    `start` goes to the handlers (create the World first). Raises LoginError."""
    outcome: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def fail(reason: str) -> None:
        if not outcome.done():  # only the first result counts
            outcome.set_exception(LoginError(reason))

    def on_game_error(e: Any) -> None:
        fail(error_reason(e))

    def on_game_log(m: Any) -> None:
        # The character is online, or still saving after a disconnect: no `start`
        # will come on this socket (node/server.js:11577-11582). See the
        # reconnect rule (reconnect_delay_ms).
        text = m.get("message", "") if isinstance(m, dict) else str(m)
        if text.startswith("Authorization in progress"):
            fail("authorization_in_progress")

    def on_start(_: Any) -> None:
        if not outcome.done():
            outcome.set_result(None)

    # Listen for each result BEFORE we send anything.
    sock.on("start", on_start)
    sock.on("game_error", on_game_error)
    sock.on("game_log", on_game_log)
    sock.on("disconnect_reason", lambda r: fail(str(r)))
    sock.on("disconnect", lambda r: fail(str(r)))  # AlSocket's local event

    try:
        async with asyncio.timeout(timeout_ms / 1000):
            # 1. `welcome`: the server sends it at once. AlSocket keeps it for us.
            welcome = await sock.wait_for("welcome", timeout=timeout_ms / 1000)
            # 2. `loaded`: the server reads none of these fields, but it ignores
            #    `auth` until `loaded` made us an observer (node/server.js:5028-5054).
            await sock.emit("loaded", {"success": 1, "width": 1920, "height": 1080, "scale": 2})
            # 3. `auth`: `character` is the id (CH_...), not the name.
            await sock.emit("auth", {
                "user": auth.user,
                "auth": auth.auth,
                "character": character_id,
                "no_html": "1",  # "a program controls this character"
                "passphrase": "",  # only test servers check it
            })
            # 4. `start`, or one of the failures above.
            await outcome
    except TimeoutError:
        raise LoginError("timeout") from None
    except ConnectionError as err:  # the socket closed while we waited
        raise LoginError(str(err)) from None
    return welcome
# endregion enter-game


class Bot:
    """One character in the game, with everything that it needs."""

    def __init__(self, sock: AlSocket, G: GData, world: World, auth: Auth, server: Server,
                 character: Character, welcome: Any) -> None:
        self.sock = sock
        self.G = G
        self.world = world
        self.auth = auth
        self.server = server
        self.character = character
        self.welcome = welcome
        self.cooldowns = Cooldowns(world)
        self.budget = Budget(sock, world)
        self.act = Actions(sock, world, self.cooldowns, self.budget)

    # region connect
    @classmethod
    async def connect(cls) -> "Bot":
        """Log in and enter the game with AL_CHARACTER on AL_SERVER."""
        auth = await login()  # AL_AUTH, or the password one time
        lists = await servers_and_characters(auth)
        server = find_server(lists["servers"])  # AL_SERVER; empty: the first one
        character = find_character(lists["characters"])  # AL_CHARACTER
        G = await load_g()
        return await cls.connect_with(auth, server, character, G)

    @classmethod
    async def connect_with(cls, auth: Auth, server: Server, character: Character, G: GData) -> "Bot":
        """The steps after the HTTP calls: the socket, the World, the handshake
        and the other parts. Part 3 calls it for each character of a party, with
        one login, one server list and one G for all of them."""
        sock = await AlSocket.connect(socket_url(server))
        try:
            # The World before `loaded`: its handlers must see `start`.
            world = World(sock, G)
            welcome = await enter_game(sock, auth, character["id"])
        except BaseException:
            await sock.close()
            raise
        return cls(sock, G, world, auth, server, character, welcome)
    # endregion connect

    async def close(self) -> None:
        """Close the socket. The server then saves the character."""
        await self.sock.close()


# region reconnect-delay
def reconnect_delay_ms(attempt: int) -> float:
    """How long to wait before reconnect try number `attempt` (0, 1, 2, ...).

    Do not reconnect at once. After a disconnect, the server keeps the character
    in dc_players until its save ends, and a new `auth` gets "Authorization in
    progress" (node/server.js:11577-11582, :13055, :16812). So wait
    AL_RECONNECT_MS (30 s) before the first try, double the wait after each
    failed try, and wait 300 s at most. After a session that lasted 5 minutes,
    start again from attempt 0. Always close the old socket, make a new
    AlSocket, and do the full handshake again."""
    first = float(os.environ.get("AL_RECONNECT_MS") or 30000)
    return min(first * 2 ** attempt, 300000.0)  # 300 s: the cap
# endregion reconnect-delay
