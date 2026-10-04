// Bot.java: everything that a program needs to play, in one object. Bot.connect() logs in,
// chooses the server and the character, loads G, opens the socket and does the handshake.
// Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
package albot;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class Bot {
    /**
     * The server did not let the character in. reason says why: "password_issue", "no_character",
     * "ingame", "server_full", "authorization_in_progress", "limitdc", "timeout", ...
     */
    public static final class LoginError extends Exception {
        public final String reason;

        public LoginError(String reason) {
            super("login failed: " + reason);
            this.reason = reason;
        }
    }

    // region error-reason
    /**
     * The reason of a `game_error` during the handshake. The payload is an object
     * {message, phrase, phrase_args, reason?} (languages/index.js:256-258):
     * a refused `auth` has `reason`: "no_character", "password_issue", "mainframe_issue",
     * "ingame", "poker_hand_active", "cancelled" (node/server.js:11610-11652);
     * a full server has the phrase "server.game_error.capacity" (node/server.js:11587, 11879):
     * we call it "server_full"; "server.game_error.characters_unconfirmed": the server could
     * not read your other characters (node/server.js:11873-11876). Try again later.
     * A bare string (for example "ERROR!") is its own reason.
     */
    public static String errorReason(JsonNode e) {
        if (e.isTextual()) return e.asText();
        if (e.hasNonNull("reason")) return e.path("reason").asText();
        String phrase = e.path("phrase").asText(null);
        if ("server.game_error.capacity".equals(phrase)) return "server_full";
        if (phrase != null) return phrase.substring(phrase.lastIndexOf('.') + 1); // "characters_unconfirmed"
        return e.path("message").asText("unknown");
    }
    // endregion error-reason

    // region enter-game
    /**
     * Step 1 of the handshake: wait for `welcome`. The server sends it at once; AlSocket keeps it
     * until we ask (Part 1).
     */
    public static JsonNode waitWelcome(AlSocket sock, long timeoutMs) throws LoginError, InterruptedException {
        try {
            return sock.waitFor("welcome", null, Duration.ofMillis(timeoutMs)).get();
        } catch (ExecutionException e) {
            throw new LoginError(e.getCause() instanceof TimeoutException ? "timeout" : String.valueOf(e.getCause().getMessage()));
        }
    }

    /**
     * Steps 2 to 4: send `loaded` and `auth`, then wait for `start` or for one of the failures.
     * The server ignores `auth` until `loaded` made an observer for this socket
     * (node/server.js:5028-5054, 11583). `character` is the id ("CH_..."), not the name.
     */
    public static JsonNode sendAuth(AlSocket sock, Api.Auth auth, String characterId, long timeoutMs)
            throws LoginError, InterruptedException {
        // Listen for each possible result BEFORE we send `auth`. The handlers run on the
        // dispatcher thread; they only complete this future. Only the first result counts
        // (complete does nothing after that), so the handlers can stay: AlSocket cannot remove them.
        var started = new CompletableFuture<JsonNode>();
        sock.on("start", started::complete);
        sock.on("game_error", e -> started.completeExceptionally(new LoginError(errorReason(e))));
        // The character is still online, or its save after a disconnect still runs
        // (node/server.js:11577-11582). No `start` comes on this socket.
        sock.on("game_log", m -> {
            if (m.path("phrase").asText().equals("server.game_log.authorization_in_progress")
                    || m.asText().equals("Authorization in progress.")) {
                started.completeExceptionally(new LoginError("authorization_in_progress"));
            }
        });
        sock.on("disconnect_reason", r -> started.completeExceptionally(new LoginError(r.asText())));
        sock.on("disconnect", r -> started.completeExceptionally(new LoginError(r.asText()))); // the socket closed

        // The server reads none of these fields; the browser sends them.
        sock.emit("loaded", Map.of("success", 1, "width", 1920, "height", 1080, "scale", 2));
        sock.emit("auth", Map.of(
                "user", auth.user(),
                "auth", auth.auth(),
                "character", characterId,
                "no_html", "1", // "a program controls this character": the server sets afk to "code"
                "passphrase", "")); // only test servers check it
        try {
            return started.get(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            throw new LoginError("timeout");
        } catch (ExecutionException e) {
            throw (LoginError) e.getCause(); // the handlers above only fail it with a LoginError
        }
    }

    /**
     * The whole handshake on a connected socket: waitWelcome, then sendAuth. Returns `welcome`
     * (Bot keeps it as bot.welcome). `start` reaches the World through its handler.
     */
    public static JsonNode enterGame(AlSocket sock, Api.Auth auth, String characterId, long timeoutMs)
            throws LoginError, InterruptedException {
        JsonNode welcome = waitWelcome(sock, timeoutMs);
        sendAuth(sock, auth, characterId, timeoutMs);
        return welcome;
    }

    /** enterGame with a 30 s timeout (a normal login takes less than 1 s). */
    public static JsonNode enterGame(AlSocket sock, Api.Auth auth, String characterId)
            throws LoginError, InterruptedException {
        return enterGame(sock, auth, characterId, 30000);
    }
    // endregion enter-game

    public final AlSocket sock;
    public final GData G;
    public final World world;
    public final Cooldowns cooldowns;
    public final Budget budget;
    public final Actions act;
    public final Api.Auth auth;
    public final Api.Server server;
    public final Api.Character character;
    public final JsonNode welcome;

    private Bot(AlSocket sock, GData G, World world, Cooldowns cooldowns, Budget budget, Actions act,
                Api.Auth auth, Api.Server server, Api.Character character, JsonNode welcome) {
        this.sock = sock;
        this.G = G;
        this.world = world;
        this.cooldowns = cooldowns;
        this.budget = budget;
        this.act = act;
        this.auth = auth;
        this.server = server;
        this.character = character;
        this.welcome = welcome;
    }

    // region connect
    /** From the environment variables to a character in the game. */
    public static Bot connect() throws IOException, InterruptedException, LoginError {
        Api.Auth auth = Api.login(); // AL_AUTH, or AL_EMAIL + AL_PASSWORD
        var lists = Api.serversAndCharacters(auth);
        Api.Server server = Api.findServer(lists.servers()); // AL_SERVER
        Api.Character character = Api.findCharacter(lists.characters()); // AL_CHARACTER
        GData G = GData.loadG(); // from the cache when we have this version
        return connectWith(auth, server, character, G);
    }

    /**
     * The steps after the HTTP calls: the socket, the World, the handshake and the other parts.
     * Part 3 calls it for each character of a party, with one login, one server list and one G
     * for all of them.
     */
    public static Bot connectWith(Api.Auth auth, Api.Server server, Api.Character character, GData G)
            throws IOException, InterruptedException, LoginError {
        AlSocket sock = AlSocket.connect(Api.socketUrl(server));
        try {
            // The World must exist before `loaded`, so that its handlers get `start`. We make it
            // after `welcome`: on our threads, the first `on` of the World would otherwise let
            // AlSocket drop a `welcome` that arrives a moment later (AlSocket keeps events only
            // until the first subscriber of any name).
            JsonNode welcome = waitWelcome(sock, 30000);
            World world = new World(sock, G);
            sendAuth(sock, auth, character.id(), 30000);
            // These listen to events that come after `start` only.
            Cooldowns cooldowns = new Cooldowns(world);
            Budget budget = new Budget(sock, world);
            Actions act = new Actions(sock, world, cooldowns, budget);
            return new Bot(sock, G, world, cooldowns, budget, act, auth, server, character, welcome);
        } catch (LoginError | InterruptedException | RuntimeException e) {
            sock.close(); // never leave a half-open socket
            throw e;
        }
    }
    // endregion connect

    /** Closes the socket. The server then saves the character and marks it offline. */
    public void close() {
        sock.close();
    }

    // region reconnect-delay
    /**
     * The one reconnect rule. After a disconnect, the server keeps the character until its save
     * ends, and a new `auth` gets "Authorization in progress" (node/server.js:11577-11582, 13055,
     * 16812). So wait AL_RECONNECT_MS (30 s) before the first try (attempt 0), double the wait
     * after each failed try, and wait at most 300 s. After a session that lasted 5 minutes, start
     * again from attempt 0. Close the old socket first, and always make a new AlSocket and do
     * the full handshake again.
     */
    public static long reconnectDelayMs(int attempt) {
        long first = 30000; // 30 s: longer than a normal save
        String env = System.getenv("AL_RECONNECT_MS");
        if (env != null && !env.isEmpty()) first = Long.parseLong(env);
        long max = 300000; // 300 s: the longest wait
        return Math.min(first << Math.min(attempt, 20), max); // 20: no overflow of the shift
    }
    // endregion reconnect-delay
}
