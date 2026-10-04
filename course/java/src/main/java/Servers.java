// Servers.java: get the list of game servers over HTTP and make a socket URL for each.
// Standalone: it uses no albot code. Java 21; Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
// Run: mvn -q compile exec:java -Dexec.mainClass=Servers
//      (AL_BASE_URL: the website, default https://adventure.land)
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;

public class Servers {
    // The shape of the reply, with only the fields that we use. By default, Jackson
    // fails on keys that the record does not have, so tell it to ignore them.
    @JsonIgnoreProperties(ignoreUnknown = true)
    record Server(String region, String name, String address, String path) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    record ServerList(boolean success, List<Server> servers) {}

    public static void main(String[] args) throws Exception {
        String base = System.getenv().getOrDefault("AL_BASE_URL", "https://adventure.land").replaceAll("/+$", "");
        // The game socket uses the scheme of the website: http -> ws, https -> wss.
        String ws = base.startsWith("https:") ? "wss" : "ws";

        // NORMAL: follow redirects (the Java HttpClient does not do it by default).
        // HTTP_1_1: by default the client asks a plain http:// server for an upgrade to HTTP/2
        // (h2c); the local test server drops such a request.
        HttpClient http = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NORMAL)
                .version(HttpClient.Version.HTTP_1_1)
                .build();
        HttpRequest req = HttpRequest.newBuilder(URI.create(base + "/api/get_servers")).build();
        HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString());
        System.out.println("status: " + res.statusCode() + " "
                + res.headers().firstValue("content-type").orElse("?")); // 200 = OK
        if (res.statusCode() != 200) throw new RuntimeException("HTTP " + res.statusCode());

        ServerList body = new ObjectMapper().readValue(res.body(), ServerList.class);
        for (Server s : body.servers()) {
            // The path must end with exactly one "/" (the server matches "/ws1/").
            String url = ws + "://" + s.address() + s.path().replaceAll("/+$", "")
                    + "/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1";
            System.out.println(s.region() + " " + s.name() + ": " + url);
        }
    }
}
