# budget.py: the call-cost budget.
#
# The server adds up a "call-cost" for each socket over the last 4 s. Over 200,
# it sends disconnect_reason "limitdc" and closes the socket
# (node/server.js:4935-4940). Each event costs 1, and some events cost more
# (EXTRA_COST). Budget.emit waits until the last 4 s have room, so that a bug
# in a loop slows the bot down instead of getting it kicked.
import asyncio
import time
from typing import Any

from .alsocket import AlSocket
from .world import World

# region budget
# The extra call-cost of some events, on top of the 1 that every event costs
# (node/server.js:242-258, charged at node/server.js:4892-4943).
EXTRA_COST: dict[str, float] = {
    "auth": 2, "move": 1.5, "players": 12, "secondhands": 16, "friend": 24, "send_updates": 12,
    "cruise": 10, "random_look": 10, "equip": 3, "unequip": 6, "tracker": 50, "ccreport": 3,
}
# 150, not the server's 200: the server also charges for some of its own
# replies (each resend of `player`), and we cannot see those costs.
LIMIT = 150
WINDOW_MS = 4000  # the server counts the last 4 s


class Budget:
    def __init__(self, sock: AlSocket, world: World) -> None:
        self.sock = sock
        self._spent: list[tuple[float, float]] = []  # (time.monotonic(), cost), oldest first
        # A map change costs 8 (add_call_cost(player, 8, "transport"),
        # node/server.js:4726). We do not send it, but it counts against us.
        world.listen("new_map", lambda _: self._spent.append((time.monotonic(), 8)))

    def cost(self, event: str) -> float:
        return 1 + EXTRA_COST.get(event, 0)

    def spent(self) -> float:
        """The total call-cost of the last 4 s."""
        now = time.monotonic()
        while self._spent and now - self._spent[0][0] > WINDOW_MS / 1000:
            self._spent.pop(0)  # forget calls older than the window
        return sum(c for _, c in self._spent)

    async def wait_for_room(self, event: str) -> None:
        """Wait until `event` fits in the budget. emit() calls it; call it
        yourself before you register a reply wait, so that the wait for room
        does not use up the timeout of the reply."""
        while self.spent() + self.cost(event) > LIMIT:
            # Sleep until the oldest call leaves the window (+10 ms of margin).
            oldest = self._spent[0][0]
            await asyncio.sleep(max(0.01, oldest + WINDOW_MS / 1000 - time.monotonic() + 0.01))

    async def emit(self, event: str, payload: Any = None) -> None:
        """Send `event` when the budget has room. Use this for every event."""
        await self.wait_for_room(event)
        self._spent.append((time.monotonic(), self.cost(event)))
        await self.sock.emit(event, payload)
# endregion budget
