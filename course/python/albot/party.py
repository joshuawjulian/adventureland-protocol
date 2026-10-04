# party.py: several characters in one program, a party, and a new character.
#
# The program logs in once, reads the server and character lists once and
# loads G once. Then connect_member() opens one socket for each character.
# Each character has its own World, Cooldowns, Budget and Actions: the server
# counts the call-cost for each socket.
import asyncio
import time
from typing import Any

from .actions import Actions, GameResponse
from .alsocket import AlSocket
from .api import Auth, Character, Server, api_call
from .bot import Bot
from .budget import Budget
from .cooldowns import Cooldowns
from .gdata import GData
from .world import World


# region member
class Member:
    """One character in the game: the same parts as a Bot."""

    def __init__(self, name: str, sock: AlSocket, G: GData, world: World, cooldowns: Cooldowns,
                 budget: Budget, act: Actions, character: Character) -> None:
        self.name = name
        self.sock = sock
        self.G = G
        self.world = world
        self.cooldowns = cooldowns
        self.budget = budget
        self.act = act
        self.character = character

    async def close(self) -> None:
        await self.sock.close()


async def connect_member(auth: Auth, server: Server, character: Character, G: GData) -> Member:
    """Connect one character with a login, a server and a G that we already
    have: Bot.connect_with (Bot.connect without the HTTP calls)."""
    bot = await Bot.connect_with(auth, server, character, G)
    return Member(character["name"], bot.sock, G, bot.world, bot.cooldowns, bot.budget, bot.act, character)
# endregion member


# region create-character
async def create_character(auth: Auth, name: str, ctype: str) -> dict[str, Any]:
    """Make a new character on the account: HTTP `create_character` {name, char}
    (api.js:474-588). The name: 4 to 12 letters, digits or "_", not used by
    anyone (api.js:24-31). The answer is {success: true}, or {failed: true,
    reason}: "name_used", "invalid_name", "reached_character_limit", ...
    (Not api.create_character: that one is a Part 2 stub.)"""
    r = await api_call("create_character", {"name": name, "char": ctype}, auth)
    if r.get("failed"):
        raise RuntimeError(f"create_character failed: {r.get('reason')}")
    return r
# endregion create-character


# region party
class Party:
    """The party of one character. The server sends `invite` {name} to the
    character that gets an invitation, and `party_update` {list, party} to each
    member when the party changes (node/server.js:12357-12546)."""

    def __init__(self, world: World, act: Actions) -> None:
        self.act = act
        self.list: list[str] = []  # the names in our party, the leader first
        self._invites: set[str] = set()  # who invited us
        world.listen("invite", lambda d: self._invites.add(d["name"]))
        world.listen("party_update", self._on_update)

    def _on_update(self, d: Any) -> None:
        # {} (no list) when we left or the party ended.
        self.list = list(d.get("list") or []) if isinstance(d, dict) else []

    async def invite(self, name: str) -> GameResponse | None:
        """Invite `name` (a character on this server). The answer is a success
        with place "party", or "invalid" (no such character), "party_full"."""
        return await self.act.request("party", {"event": "invite", "name": name})

    async def accept(self, name: str) -> GameResponse | None:
        """Accept the invitation of `name`. It fails with "invitation_expired"
        when there was no invitation."""
        return await self.act.request("party", {"event": "accept", "name": name})

    async def leave(self) -> GameResponse | None:
        return await self.act.request("party", {"event": "leave"})

    async def wait_invite(self, name: str, seconds: float = 5) -> bool:
        """Wait until `name` invited us (True), or `seconds` passed (False)."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if name in self._invites:
                return True
            await asyncio.sleep(0.05)
        return name in self._invites
# endregion party
