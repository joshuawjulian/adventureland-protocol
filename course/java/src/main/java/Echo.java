// Echo.java: open a WebSocket, send one text message, read the reply, close.
// Standalone: Java 21, standard library only.
// Run: mvn -q compile exec:java -Dexec.mainClass=Echo
//      (AL_ECHO_URL: a plain WebSocket echo server, default ws://localhost:8022/echo)
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public class Echo {
    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault("AL_ECHO_URL", "ws://localhost:8022/echo");
        var reply = new CompletableFuture<String>();
        var closed = new CompletableFuture<Void>();

        // A Listener: the HTTP client calls these methods when something happens.
        // (A long message can come in parts; AlSocket shows how to join them.)
        WebSocket.Listener listener = new WebSocket.Listener() {
            @Override
            public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
                reply.complete(data.toString());
                ws.request(1); // ask for the next message
                return null;
            }

            @Override
            public CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason) {
                closed.complete(null); // the server answered our close
                return null;
            }
        };
        WebSocket ws = HttpClient.newHttpClient().newWebSocketBuilder()
                .buildAsync(URI.create(url), listener)
                .join(); // join() blocks until the future is complete
        System.out.println("connected");

        ws.sendText("hello", true).join(); // one text frame; true = the last part
        System.out.println("received: " + reply.join());

        ws.sendClose(WebSocket.NORMAL_CLOSURE, "").join(); // 1000: a normal close
        // Wait for the close of the server, but at most 5 s: a lost close must not stop us.
        closed.completeOnTimeout(null, 5, TimeUnit.SECONDS).join();
        System.out.println("closed");
    }
}
