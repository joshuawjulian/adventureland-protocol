// AlSocket.java: a minimal Socket.IO v4 client, written by hand on top of a
// plain WebSocket. It does enough to play Adventure Land, and no more.
// Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
package albot;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.NullNode;
import com.fasterxml.jackson.databind.node.TextNode;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Consumer;
import java.util.function.Predicate;

public final class AlSocket implements WebSocket.Listener {
    private static final ObjectMapper JSON = new ObjectMapper();

    private record Event(String name, JsonNode data) {}
    private record Waiter(String name, Predicate<JsonNode> pred, CompletableFuture<JsonNode> result) {}
    private static final Event END = new Event("", NullNode.instance); // the last item in the queue
    private static final Event WAKE = new Event("", NullNode.instance); // "look at `replay`": no event

    private WebSocket ws;
    private final StringBuilder partial = new StringBuilder(); // a large message comes in parts
    private final CompletableFuture<Void> handshake = new CompletableFuture<>();

    private final Object lock = new Object(); // guards the seven fields below
    private final Map<String, List<Consumer<JsonNode>>> handlers = new HashMap<>();
    private final List<Waiter> waiters = new ArrayList<>();
    private final Map<String, List<JsonNode>> early = new HashMap<>(); // events from before the first on/waitFor
    private final ArrayDeque<Event> replay = new ArrayDeque<>(); // kept events that the dispatcher must deliver next
    private boolean listening; // true after the first on/waitFor
    private boolean ended; // true after end(): the queue has its last items
    private boolean closed;

    // The listener thread puts events here. The dispatcher thread runs your
    // handlers. Because they are separate, a slow handler can't make us miss a ping.
    private final LinkedBlockingQueue<Event> events = new LinkedBlockingQueue<>();
    private final CompletableFuture<Void> done = new CompletableFuture<>();

    // java.net.http.WebSocket allows one send at a time. Each send starts
    // when the send before it is complete.
    private final Object sendLock = new Object();
    private CompletableFuture<?> lastSend = CompletableFuture.completedFuture(null);

    private AlSocket() {}

    /**
     * Open the WebSocket and do the Socket.IO handshake. url is the full URL,
     * for example "wss://de.adventure.land/ws1/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1".
     */
    public static AlSocket connect(String url) throws IOException, InterruptedException {
        AlSocket sock = new AlSocket();
        try {
            // 10 s: a working server answers in much less time.
            sock.ws = HttpClient.newHttpClient().newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(10))
                    .buildAsync(URI.create(url), sock)
                    .get(10, TimeUnit.SECONDS);
            sock.handshake.get(10, TimeUnit.SECONDS); // onPacket completes it
        } catch (ExecutionException | TimeoutException e) {
            throw new IOException("connect failed: " + e, e);
        }
        Thread.ofVirtual().name("alsocket-dispatch").start(sock::dispatch);
        return sock;
    }

    // ---- WebSocket.Listener: the HTTP client calls these methods ----

    @Override
    public void onOpen(WebSocket ws) {
        this.ws = ws;
        ws.request(1); // ask for the first message
    }

    @Override
    public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
        partial.append(data);
        if (last) {
            String packet = partial.toString();
            partial.setLength(0);
            try {
                onPacket(packet);
            } catch (Exception e) {
                System.err.println("alsocket: bad packet " + packet + ": " + e);
            }
        }
        ws.request(1); // ask for the next message
        return null;
    }

    private void onPacket(String packet) throws IOException {
        if (!handshake.isDone()) {
            if (packet.startsWith("0")) {
                // Engine.IO "open": 0{"sid", "pingInterval", "pingTimeout", ...}
                // Send Socket.IO "connect" for the default namespace "/".
                send("40");
            } else if (packet.startsWith("40")) {
                handshake.complete(null); // the server accepted us
            } else if (packet.startsWith("44")) {
                // CONNECT_ERROR: the server refused us.
                handshake.completeExceptionally(new IOException("server refused connect: " + packet.substring(2)));
            }
            return;
        }
        if (packet.equals("2")) {
            // Engine.IO ping. Send a pong at once. If you don't, the server
            // drops you after pingInterval + pingTimeout.
            send("3");
        } else if (packet.startsWith("42")) {
            // Socket.IO EVENT: 42["name", payload]. An ack id (digits) can
            // come between "42" and "[", so parse from the "[".
            JsonNode args = JSON.readTree(packet.substring(packet.indexOf('[')));
            String name = args.get(0).asText();
            JsonNode data = args.size() > 1 ? args.get(1) : NullNode.instance; // no payload: null
            synchronized (lock) {
                if (!listening) {
                    // Nobody listens yet: keep the event (see subscribed).
                    early.computeIfAbsent(name, k -> new ArrayList<>()).add(data);
                    return;
                }
            }
            events.add(new Event(name, data));
        } else if (packet.startsWith("41") || packet.equals("1")) {
            // 41: the server closed our namespace. 1: Engine.IO close.
            sendClose();
        }
        // AL does not use the other packets ("6" noop, binary packets, acks).
    }

    @Override
    public CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason) {
        sendClose(); // complete the closing handshake
        end("transport closed (code " + statusCode + ")");
        return null;
    }

    @Override
    public void onError(WebSocket ws, Throwable error) {
        end("transport error: " + error);
    }

    // This runs when the connection ends, for any cause. Only the first call counts:
    // onClose, onError and close() can all call it.
    private void end(String reason) {
        handshake.completeExceptionally(new IOException(reason)); // no effect if already complete
        synchronized (lock) {
            if (ended) return;
            ended = true;
        }
        // socket.io-client reports the end as a local "disconnect" event, and so
        // does AlSocket. The server never sends an event with this name.
        events.add(new Event("disconnect", new TextNode(reason)));
        events.add(END); // the dispatcher stops after the last event
    }

    // ---- the dispatcher thread ----

    // Gives events to handlers and waiters, in arrival order. Before each event
    // from the queue, it delivers the kept events that a new subscriber asked for
    // (see subscribed): they arrived before every event in the queue.
    private void dispatch() {
        try {
            while (true) {
                Event ev = events.take(); // blocks; the virtual thread unmounts here
                deliverReplay();
                if (ev == END) break;
                if (ev != WAKE) deliver(ev);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        // Fail each waiter that is left, one time. Copy the list, clear it, and fail
        // the copies outside the lock: each failure runs the whenComplete of waitFor
        // on this thread, and that code removes the waiter from `waiters`. A loop
        // over `waiters` itself would see it change under it.
        List<Waiter> left;
        synchronized (lock) {
            closed = true;
            left = new ArrayList<>(waiters);
            waiters.clear();
            replay.clear();
        }
        for (Waiter w : left) w.result().completeExceptionally(new IOException("socket closed"));
        done.complete(null);
    }

    // Delivers the kept events in `replay`, oldest first.
    private void deliverReplay() {
        while (true) {
            Event ev;
            synchronized (lock) { ev = replay.poll(); }
            if (ev == null) return;
            deliver(ev);
        }
    }

    // Gives one event to the handlers and waiters for its name: first each
    // handler, then each waiter. Thus when a wait returns, the handlers of the
    // same event (for example the ones of World) already ran.
    private void deliver(Event ev) {
        List<Consumer<JsonNode>> toCall;
        List<Waiter> candidates; // the waiters from before this event: a handler that adds one does not give it this event
        synchronized (lock) {
            toCall = new ArrayList<>(handlers.getOrDefault(ev.name(), List.of()));
            candidates = new ArrayList<>();
            for (Waiter w : waiters) if (w.name().equals(ev.name())) candidates.add(w);
        }
        for (var handler : toCall) {
            try {
                handler.accept(ev.data());
            } catch (RuntimeException e) { // one bad handler must not stop the socket
                System.err.println("alsocket: handler for \"" + ev.name() + "\" threw: " + e);
            }
        }
        if (candidates.isEmpty()) return;
        List<Waiter> matched = new ArrayList<>();
        synchronized (lock) {
            for (Waiter w : candidates) {
                // waiters.remove is false if the waiter already ended (timeout, cancel).
                if (safeTest(w, ev.data()) && waiters.remove(w)) matched.add(w);
            }
        }
        // Complete them outside the lock. Each one's code after get()/join() runs on
        // its own thread, and its next stages on the common pool (see waitFor).
        for (Waiter w : matched) w.result().complete(ev.data());
    }

    // Each on/waitFor calls this. The server sends "welcome" immediately after
    // the handshake, before your code can call waitFor("welcome"). AlSocket
    // keeps all events from before the first on/waitFor. The first subscriber
    // for an event name gets the kept events for that name, one time. The
    // dispatcher delivers them, in arrival order, before any later event: so
    // handlers always run on the dispatcher thread, one at a time.
    private void subscribed(String name) {
        synchronized (lock) {
            listening = true;
            List<JsonNode> kept = early.remove(name);
            if (kept == null) return;
            for (JsonNode data : kept) replay.add(new Event(name, data));
        }
        // The dispatcher can be blocked in take() on an empty queue: wake it.
        events.add(WAKE);
    }

    // A predicate that throws counts as "no match".
    private static boolean safeTest(Waiter w, JsonNode data) {
        try {
            return w.pred().test(data);
        } catch (RuntimeException e) {
            System.err.println("alsocket: predicate for \"" + w.name() + "\" threw: " + e);
            return false;
        }
    }

    // ---- sending ----

    private CompletableFuture<?> send(String packet) {
        synchronized (sendLock) {
            // Start after the previous send, also if that send failed.
            lastSend = lastSend.handle((r, e) -> null).thenCompose(x -> ws.sendText(packet, true));
            return lastSend;
        }
    }

    private void sendClose() {
        synchronized (sendLock) {
            lastSend = lastSend.handle((r, e) -> null).thenCompose(x ->
                    ws.isOutputClosed() ? CompletableFuture.completedFuture(null)
                            : ws.sendClose(WebSocket.NORMAL_CLOSURE, ""));
        }
    }

    // ---- the public methods ----

    /** Send an event: 42["name", data]. With null data, send no payload. */
    public CompletableFuture<?> emit(String event, Object data) {
        try {
            List<Object> args = data == null ? List.of(event) : List.of(event, data);
            return send("42" + JSON.writeValueAsString(args));
        } catch (IOException e) {
            return CompletableFuture.failedFuture(e);
        }
    }

    /** Call handler with the payload of each `event` from now on. */
    public void on(String event, Consumer<JsonNode> handler) {
        synchronized (lock) {
            handlers.computeIfAbsent(event, k -> new ArrayList<>()).add(handler);
        }
        subscribed(event);
    }

    /**
     * A future for the payload of the next `event` for which pred is true
     * (null pred: any event). It fails with a TimeoutException after timeout,
     * or with an IOException if the socket closes first. The call registers
     * the waiter immediately: call it, then emit, then join the future.
     */
    public CompletableFuture<JsonNode> waitFor(String event, Predicate<JsonNode> pred, Duration timeout) {
        var result = new CompletableFuture<JsonNode>();
        var waiter = new Waiter(event, pred == null ? d -> true : pred, result);
        synchronized (lock) {
            if (closed) return CompletableFuture.failedFuture(new IOException("socket closed"));
            waiters.add(waiter);
        }
        // On timeout, remove the waiter. thenApplyAsync: the stages that you add
        // to the future run on the common pool, never on the dispatcher thread.
        var future = result.orTimeout(timeout.toMillis(), TimeUnit.MILLISECONDS)
                .whenComplete((d, e) -> { synchronized (lock) { waiters.remove(waiter); } })
                .thenApplyAsync(d -> d);
        // `future` is a new stage, not `result`. If you cancel it (or complete it
        // yourself), cancel `result` too: the whenComplete above then removes the
        // waiter at once, not at its timeout.
        future.whenComplete((d, e) -> result.cancel(false)); // no effect if result is complete
        subscribed(event);
        return future;
    }

    /** The same as waitFor(event, null, 10 s). */
    public CompletableFuture<JsonNode> waitFor(String event) {
        return waitFor(event, null, Duration.ofSeconds(10));
    }

    /** Completes when the connection has ended and the dispatcher has given out each event. */
    public CompletableFuture<Void> done() {
        return done;
    }

    /**
     * Disconnect correctly: Socket.IO disconnect, then a normal WebSocket close. Waits for the
     * end, at most 5 s. Then it closes the transport at once (abort) and returns.
     */
    public void close() {
        if (done.isDone()) return;
        send("41");
        sendClose();
        try {
            // 5 s: the server answers a close in much less. More time means a dead
            // network, or a handler that does not return; do not wait for ever.
            done.get(5, TimeUnit.SECONDS);
        } catch (TimeoutException | ExecutionException e) {
            ws.abort(); // no more frames in or out
            end("closed by the client (no answer in 5 s)"); // waiters fail when the dispatcher is free
        } catch (InterruptedException e) {
            ws.abort();
            end("closed by the client (interrupted)");
            Thread.currentThread().interrupt(); // keep the request to stop for our caller
        }
    }
}
