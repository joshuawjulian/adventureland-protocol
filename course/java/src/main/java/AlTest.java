// AlTest.java: take AlSocket through the handshake of the local test server, then idle
// 3 s to prove that the pings work. It uses only albot.AlSocket (Part 1 has no other code).
// Run: mvn -q compile exec:java -Dexec.mainClass=AlTest
//      (AL_WS_URL: the full WebSocket URL of a game server;
//       default ws://localhost:8022/ws1/?EIO=4&transport=websocket)
import albot.AlSocket;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import java.util.Map;

public class AlTest {
    // HARD-CODED: the fixed account of the test server (course/test-server/accounts.js).
    // It is not a secret: it works only on the test server. Part 1 has no login code
    // yet; Part 2 gets the real values over HTTP and from AL_AUTH.
    static final String TEST_USER = "US_tester";
    static final String TEST_AUTH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    static final String TEST_CHARACTER = "CH_tester"; // the id, not the name "Tester"

    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault("AL_WS_URL", "ws://localhost:8022/ws1/?EIO=4&transport=websocket");
        Duration tenSeconds = Duration.ofSeconds(10); // a working server answers in much less time

        AlSocket sock = AlSocket.connect(url);
        System.out.println("connected to " + url);
        sock.on("game_error", msg -> System.out.println("game_error: " + msg));
        sock.on("disconnect", reason -> System.out.println("disconnect: " + reason.asText()));

        // 1. The server sends "welcome" to each new socket.
        JsonNode welcome = sock.waitFor("welcome").join();
        System.out.printf("welcome: %s %s, version %d%n",
                welcome.path("region").asText(), welcome.path("name").asText(), welcome.path("version").asInt());

        // 2. Send "loaded". The reply is one full "entities" snapshot (type "all").
        //    Register the wait BEFORE the emit, so that a fast reply cannot pass first.
        var snapshot = sock.waitFor("entities", d -> d.path("type").asText().equals("all"), tenSeconds);
        sock.emit("loaded", Map.of("success", 1, "width", 1920, "height", 1080, "scale", 2));
        System.out.println("entities: " + snapshot.join().path("monsters").size() + " monster(s)");

        // 3. Log in the test character. no_html "1": a program controls this character.
        var started = sock.waitFor("start", null, tenSeconds);
        sock.emit("auth", Map.of("user", TEST_USER, "auth", TEST_AUTH, "character", TEST_CHARACTER,
                "no_html", "1", "passphrase", ""));
        JsonNode me = started.join();
        // `start` has no `name`: the id of a character is its name.
        System.out.printf("start: %s on %s at %d,%d%n", me.path("id").asText(), me.path("map").asText(),
                Math.round(me.path("x").asDouble()), Math.round(me.path("y").asDouble()));

        // 4. Do nothing for 3 s. The server sends pings during this time. If our
        //    pong does not work, the server drops us and the next step fails.
        Thread.sleep(3000);
        var ack = sock.waitFor("ping_ack", d -> d.path("id").asText().equals("42"), tenSeconds);
        sock.emit("ping_trig", Map.of("id", "42"));
        System.out.println("ping_ack after 3 s idle: " + ack.join().path("id").asText());

        System.out.println("OK");
        sock.close(); // the "disconnect" handler prints the reason
    }
}
