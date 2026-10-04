// Api.java: the HTTP API of the website: log in, list the servers and the characters,
// and make the WebSocket URL of a game server.
// Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
package albot;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class Api {
    // FAIL_ON_UNKNOWN_PROPERTIES off: the records below model a few fields; the site sends more.
    static final ObjectMapper JSON = new ObjectMapper()
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    // NORMAL: follow redirects. The Java HttpClient does not follow them by default.
    static final HttpClient HTTP = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NORMAL)
            // HTTP/1.1: by default the client asks a plain http:// server for an upgrade to HTTP/2
            // (h2c). Node treats that request as an upgrade, and the local test server drops it.
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(15)) // 15 s: generous for a slow link
            .build();

    private Api() {} // static methods only

    /** The session. On the wire, it is the cookie auth=<user>-<auth>. */
    public record Auth(String user, String auth) {}

    /**
     * One game server (adventure_functions.js:751-766). region is "EU", "US" or "ASIA"; name
     * is "I", "II", "PVP", ...; key is the database id ("SR_EUI"); address is the host (and
     * port) of the WebSocket; path is the Socket.IO path on that host.
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Server(String key, String region, String name, int players, String address, String path) {}

    /**
     * One of your characters (adventure_functions.js:821-843). id ("CH_...") goes in the socket
     * `auth`, not the name. type is the class. server ("SR_EUI") is null while it is offline.
     * (In this file, Character means this record, not java.lang.Character.)
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Character(String id, String name, String type, int level, String server) {}

    /** The two lists of servers_and_characters. */
    public record ServersAndCharacters(List<Server> servers, List<Character> characters) {}

    /** AL_BASE_URL, or the live website, without a final "/". */
    public static String baseUrl() {
        String base = System.getenv("AL_BASE_URL");
        if (base == null || base.isEmpty()) base = "https://adventure.land";
        return base.replaceAll("/+$", "");
    }

    // region api-call
    /**
     * POST a JSON body to {base}/api/{method}. With auth, the session goes in the cookie
     * auth=<user>-<auth>. The live API answers HTTP 200 with a JSON object, also when the call
     * fails ({failed: true, reason}). So any other status is a network or server problem.
     * Returns the parsed JSON; the caller checks `failed`.
     */
    public static JsonNode apiCall(String method, Object body, Auth auth) throws IOException, InterruptedException {
        var req = HttpRequest.newBuilder(URI.create(baseUrl() + "/api/" + method))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(15))
                .POST(HttpRequest.BodyPublishers.ofString(JSON.writeValueAsString(body == null ? Map.of() : body)));
        if (auth != null) req.header("Cookie", "auth=" + auth.user() + "-" + auth.auth());
        HttpResponse<String> res = HTTP.send(req.build(), HttpResponse.BodyHandlers.ofString());
        if (res.statusCode() != 200) throw new IOException(method + ": HTTP " + res.statusCode());
        return JSON.readTree(res.body());
    }
    // endregion api-call

    /** "<user>-<auth>", split at the first "-" (the auth part can have no "-", the user id can). */
    public static Auth parseAuth(String text) {
        int dash = text.indexOf('-');
        if (dash < 0) throw new IllegalArgumentException("AL_AUTH must look like <user>-<auth>");
        return new Auth(text.substring(0, dash), text.substring(dash + 1));
    }

    // region login
    /**
     * Uses AL_AUTH when it is set, and sends no password. Only when AL_AUTH is empty does it
     * log in with AL_EMAIL and AL_PASSWORD; then it prints the AL_AUTH value to save. Each
     * password login adds a token to the account (live: at most 200), so do it once.
     */
    public static Auth login() throws IOException, InterruptedException {
        String saved = System.getenv("AL_AUTH");
        if (saved != null && !saved.isEmpty()) return parseAuth(saved);

        String email = System.getenv("AL_EMAIL"), password = System.getenv("AL_PASSWORD");
        if (email == null || password == null) throw new IOException("set AL_AUTH, or AL_EMAIL and AL_PASSWORD");
        // only_login: never make a new account by accident (api.js:84-133).
        JsonNode reply = apiCall("signup_or_login",
                Map.of("email", email, "password", password, "only_login", true), null);
        // Success: {success: true, user, auth, ...}. Failure: {failed: true, reason}.
        if (!reply.path("success").asBoolean(false)) {
            throw new IOException("login failed: " + reply.path("reason").asText("unknown reason"));
        }
        Auth auth = new Auth(reply.path("user").asText(), reply.path("auth").asText());
        String value = auth.user() + "-" + auth.auth();
        System.out.println("Logged in with the password. Save this value, and use it from now on:");
        System.out.println("  export AL_AUTH='" + value + "'");
        System.out.println("  PowerShell: $env:AL_AUTH = '" + value + "'");
        return auth;
    }
    // endregion login

    // region servers-and-characters
    /** The server list and the character list, from the `infs` item of type "servers_and_characters". */
    public static ServersAndCharacters serversAndCharacters(Auth auth) throws IOException, InterruptedException {
        JsonNode reply = apiCall("servers_and_characters", Map.of(), auth);
        if (reply.path("reason").asText().equals("not_logged_in")) {
            throw new IOException("not_logged_in: the token in AL_AUTH is not valid any more. "
                    + "Unset AL_AUTH and log in with the password again.");
        }
        if (reply.path("failed").asBoolean(false)) {
            throw new IOException("servers_and_characters failed: " + reply.path("reason").asText());
        }
        for (JsonNode inf : reply.path("infs")) {
            if (!inf.path("type").asText().equals("servers_and_characters")) continue;
            var servers = new ArrayList<Server>();
            for (JsonNode s : inf.path("servers")) servers.add(JSON.treeToValue(s, Server.class));
            var characters = new ArrayList<Character>();
            for (JsonNode c : inf.path("characters")) characters.add(JSON.treeToValue(c, Character.class));
            return new ServersAndCharacters(servers, characters);
        }
        throw new IOException("unexpected reply from servers_and_characters: " + reply);
    }
    // endregion servers-and-characters

    // region find-server
    /** The server whose region + name is `key` (for example "EUI"). An empty key: the first server. */
    public static Server findServer(List<Server> servers, String key) {
        if (servers.isEmpty()) throw new IllegalStateException("the server list is empty");
        if (key == null || key.isEmpty()) return servers.get(0); // the list is in the order EU, US, ASIA
        for (Server s : servers) {
            if ((s.region() + s.name()).equals(key)) return s;
        }
        List<String> keys = servers.stream().map(s -> s.region() + s.name()).toList();
        throw new IllegalArgumentException("no server " + key + "; the list has: " + String.join(", ", keys));
    }

    /** findServer with the key in AL_SERVER. */
    public static Server findServer(List<Server> servers) {
        return findServer(servers, System.getenv("AL_SERVER"));
    }

    /** The character with exactly this name (not the CH_ id). */
    public static Character findCharacter(List<Character> characters, String name) {
        if (name == null || name.isEmpty()) throw new IllegalArgumentException("set AL_CHARACTER to the name of a character");
        for (Character c : characters) {
            if (c.name().equals(name)) return c;
        }
        List<String> names = characters.stream().map(Character::name).toList();
        throw new IllegalArgumentException("no character " + name + "; the list has: " + String.join(", ", names));
    }

    /** findCharacter with the name in AL_CHARACTER. */
    public static Character findCharacter(List<Character> characters) {
        return findCharacter(characters, System.getenv("AL_CHARACTER"));
    }
    // endregion find-server

    // region socket-url
    /**
     * ws(s)://<address><path>/?EIO=4&transport=websocket, plus the two options that the browser
     * client also sends (js/game.js:1525). map_protocol=1: we accept generated maps (without it,
     * the server throws "client_update_required", node/logic/generated_maps.js:186).
     * no_graphics=1: send generated maps without tile data. The scheme follows the website:
     * http -> ws, https -> wss.
     */
    public static String socketUrl(Server server, String base) {
        String scheme = base.startsWith("https:") ? "wss" : "ws";
        String path = server.path().replaceAll("/+$", ""); // then add exactly one "/"
        return scheme + "://" + server.address() + path + "/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1";
    }

    /** socketUrl with baseUrl(). */
    public static String socketUrl(Server server) {
        return socketUrl(server, baseUrl());
    }
    // endregion socket-url
}
