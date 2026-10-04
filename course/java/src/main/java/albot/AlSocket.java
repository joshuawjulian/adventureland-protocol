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

    private WebSocket ws;
    private final StringBuilder partial = new StringBuilder(); // a large message comes in parts
    private final CompletableFuture<Void> handshake = new CompletableFuture<>();

    private final Object lock = new Object(); // guards the five fields below
    private final Map<String, List<Consumer<JsonNode>>> handlers = new HashMap<>();
    private final List<Waiter> waiters = new ArrayList<>();
    private final Map<String, List<JsonNode>> early = new HashMap<>(); // events from before the first on/waitFor
    private boolean listening; // true after the first on/waitFor
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

    // This runs when the connection ends, for any cause.
    private void end(String reason) {
        handshake.completeExceptionally(new IOException(reason)); // no effect if already complete
        // socket.io-client reports the end as a local "disconnect" event, and so
        // does AlSocket. The server never sends an event with this name.
        events.add(new Event("disconnect", new TextNode(reason)));
        events.add(END); // the dispatcher stops after the last event
    }

    // ---- the dispatcher thread ----

    // Gives events to handlers and waiters, in arrival order.
    private void dispatch() {
        try {
            for (Event ev = events.take(); ev != END; ev = events.take()) {
                deliver(ev);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        synchronized (lock) {
            closed = true;
            for (Waiter w : waiters) w.result().completeExceptionally(new IOException("socket closed"));
            waiters.clear();
        }
        done.complete(null);
    }

    // Gives one event to the handlers and waiters for its name.
    private void deliver(Event ev) {
        List<Consumer<JsonNode>> toCall;
        synchronized (lock) {
            toCall = new ArrayList<>(handlers.getOrDefault(ev.name(), List.of()));
            var it = waiters.iterator();
            while (it.hasNext()) {
                Waiter w = it.next();
                if (w.name().equals(ev.name()) && safeTest(w, ev.data())) {
                    it.remove();
                    w.result().complete(ev.data());
                }
            }
        }
        for (var handler : toCall) {
            try {
                handler.accept(ev.data());
            } catch (RuntimeException e) { // one bad handler must not stop the socket
                System.err.println("alsocket: handler for \"" + ev.name() + "\" threw: " + e);
            }
        }
    }

    // Each on/waitFor calls this. The server sends "welcome" immediately after
    // the handshake, before your code can call waitFor("welcome"). AlSocket
    // keeps all events from before the first on/waitFor. The first subscriber
    // for an event name gets the kept events for that name. They run on the
    // thread that called on/waitFor, one time.
    private void subscribed(String name) {
        List<JsonNode> kept;
        synchronized (lock) {
            listening = true;
            kept = early.remove(name);
        }
        if (kept != null) {
            for (JsonNode data : kept) deliver(new Event(name, data));
        }
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
        // On timeout, remove the waiter. thenApplyAsync: your code after
        // join() must not run inside the lock of the dispatcher.
        var future = result.orTimeout(timeout.toMillis(), TimeUnit.MILLISECONDS)
                .whenComplete((d, e) -> { synchronized (lock) { waiters.remove(waiter); } })
                .thenApplyAsync(d -> d);
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

    /** Disconnect correctly: Socket.IO disconnect, then a normal WebSocket close. Waits for the end. */
    public void close() {
        if (done.isDone()) return;
        send("41");
        sendClose();
        done.join();
    }
}
