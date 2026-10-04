# alsocket.py: a minimal Socket.IO v4 client, written by hand on top of a
# plain WebSocket. It does enough to play Adventure Land, and no more.
# Python 3.11+.   pip install "websockets>=13"
import asyncio
import inspect
import json
import traceback
from typing import Any, Callable, Coroutine

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed


class AlSocket:
    def __init__(self, ws: ClientConnection):
        self._ws = ws
        self._handlers: dict[str, list[Callable[[Any], Any]]] = {}  # from on()
        self._waiters: list[tuple[str, Callable[[Any], bool], asyncio.Future[Any]]] = []
        # event name -> payloads from before the first on()/wait_for()
        self._early: dict[str, list[Any]] = {}
        self._listening = False  # True after the first on()/wait_for()
        self._closed = False
        self._reader: asyncio.Task[None] | None = None

    @classmethod
    async def connect(cls, url: str, timeout: float = 10.0) -> "AlSocket":
        """Open the WebSocket and do the Socket.IO handshake. `url` is the
        full URL, for example
        "wss://de.adventure.land/ws1/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1"."""
        # 10 s by default: a working server answers in much less time.
        async with asyncio.timeout(timeout):
            # ping_interval=None: stop the WebSocket pings of the library.
            # Socket.IO has its own ping and pong (below). One is enough.
            # max_size: accept messages up to 16 MiB (the default is 1 MiB).
            ws = await connect(url, ping_interval=None, max_size=16 * 2**20)
            # Engine.IO "open": 0{"sid", "pingInterval", "pingTimeout", ...}
            packet = await ws.recv()
            # recv() returns str for a text frame, bytes for a binary frame.
            # Socket.IO v4 on this endpoint uses text frames only.
            if not isinstance(packet, str) or not packet.startswith("0"):
                raise ConnectionError(f"expected Engine.IO open, got {packet!r}")
            # Send Socket.IO "connect" for the default namespace "/".
            await ws.send("40")
            packet = await ws.recv()
            if not isinstance(packet, str):
                raise ConnectionError(f"expected text, got {packet!r}")
            if packet.startswith("44"):  # CONNECT_ERROR: the server refused us
                raise ConnectionError(f"server refused connect: {packet[2:]}")
            if not packet.startswith("40"):
                raise ConnectionError(f"expected 40, got {packet!r}")
        sock = cls(ws)
        # From now on, one background task reads all packets.
        sock._reader = asyncio.create_task(sock._read_loop())
        return sock

    async def _read_loop(self) -> None:
        reason = "transport closed"
        try:
            async for packet in self._ws:
                if not isinstance(packet, str):
                    continue  # a binary frame: AL does not send them on this endpoint
                if packet == "2":
                    # Engine.IO ping. Send a pong at once. If you don't, the
                    # server drops you after pingInterval + pingTimeout.
                    await self._ws.send("3")
                elif packet.startswith("42"):
                    # Socket.IO EVENT: 42["name", payload]. An ack id (digits)
                    # can come between "42" and "[", so parse from the "[".
                    # With no payload, data is None.
                    args = json.loads(packet[packet.index("[") :])
                    self._deliver(args[0], args[1] if len(args) > 1 else None)
                elif packet.startswith("41") or packet == "1":
                    # 41: the server closed our namespace. 1: Engine.IO close.
                    await self._ws.close()
                # AL does not use the other packets ("6" noop, binary packets, acks).
        except ConnectionClosed:
            pass  # a normal end; the reason below has the close code
        except Exception as err:  # network error, bad JSON, ...
            reason = f"transport error: {err!r}"
        self._shutdown(f"{reason} (code {self._ws.protocol.close_code})")

    def _deliver(self, event: str, data: Any) -> None:
        """Give one event to the handlers and waiters for its name."""
        if not self._listening:
            # Nobody listens yet: keep the event (see _subscribed).
            self._early.setdefault(event, []).append(data)
            return
        for handler in self._handlers.get(event, []):
            try:
                result = handler(data)
                if inspect.isawaitable(result):  # an async handler runs as a task
                    asyncio.ensure_future(result)
            except Exception:
                traceback.print_exc()  # one bad handler must not stop the socket
        for name, pred, fut in self._waiters:
            if name != event or fut.done():
                continue
            try:
                match = pred(data)
            except Exception:
                traceback.print_exc()  # an error counts as "no match"
                match = False
            if match:
                fut.set_result(data)

    def _subscribed(self, event: str) -> None:
        """Each on()/wait_for() calls this. The server sends "welcome"
        immediately after the handshake, before your code can call
        wait_for("welcome"). AlSocket keeps all events from before the first
        on()/wait_for(). The first subscriber for an event name gets the kept
        events for that name."""
        self._listening = True
        kept = self._early.pop(event, None)
        if not kept:
            return

        def replay() -> None:
            for data in kept:
                self._deliver(event, data)

        # Soon, not now, so that wait_for() registers its waiter first.
        asyncio.get_running_loop().call_soon(replay)

    async def emit(self, event: str, data: Any = None) -> None:
        """Send an event: 42["name", data]. With data=None, send no payload."""
        if self._closed:
            raise ConnectionError("socket is closed")
        args = [event] if data is None else [event, data]
        await self._ws.send("42" + json.dumps(args, separators=(",", ":")))

    def on(self, event: str, handler: Callable[[Any], Any]) -> None:
        """Call handler(data) for each `event` from now on (sync or async)."""
        self._handlers.setdefault(event, []).append(handler)
        self._subscribed(event)

    def wait_for(
        self,
        event: str,
        pred: Callable[[Any], bool] | None = None,
        timeout: float = 10.0,
    ) -> Coroutine[Any, Any, Any]:
        """Wait for the payload of the next `event` for which pred(data) is
        True. Raises TimeoutError after `timeout` seconds, or ConnectionError
        if the socket closes first.

        This is not `async def` on purpose: the call registers the waiter
        immediately, and the timeout starts. The result is a coroutine. Await
        it, or give it to asyncio.create_task(). Thus you can call wait_for,
        then emit, then await."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        if self._closed:
            fut.set_exception(ConnectionError("socket is closed"))
        else:
            waiter = (event, pred or (lambda _: True), fut)
            self._waiters.append(waiter)
            def expire() -> None:
                if not fut.done():
                    fut.set_exception(TimeoutError(f"timed out waiting for {event!r}"))

            timer = loop.call_later(timeout, expire)

            def cleanup(_: asyncio.Future[Any]) -> None:
                timer.cancel()
                self._waiters.remove(waiter)

            fut.add_done_callback(cleanup)
            self._subscribed(event)

        async def result() -> Any:
            return await fut

        return result()

    async def close(self) -> None:
        """Disconnect correctly: Socket.IO disconnect, then a normal WebSocket close."""
        if self._closed:
            return
        try:
            await self._ws.send("41")
        except Exception:
            pass  # the connection is already gone
        await self._ws.close()
        if self._reader:
            await self._reader  # the reader ends and reports "disconnect"

    def _shutdown(self, reason: str) -> None:
        """This runs one time, when the connection ends for any cause."""
        if self._closed:
            return
        self._closed = True
        # socket.io-client reports the end as a local "disconnect" event, and
        # so does AlSocket. The server never sends an event with this name.
        self._listening = True
        self._deliver("disconnect", reason)
        for _, _, fut in self._waiters:
            if not fut.done():
                fut.set_exception(ConnectionError(f"socket closed: {reason}"))
