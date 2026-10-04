// GData.java: the game data G. Download it once per game version, keep it in a cache file,
// and read the parts that the course uses as typed records.
// Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
package albot;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * G, with typed views of three tables. `raw` is the whole G as JSON, for the tables that have
 * no record here (dimensions, geometry, maps, npcs, ...) and for the fields that the records
 * leave out.
 */
public record GData(int version, Map<String, ItemDef> items, Map<String, MonsterDef> monsters,
                    Map<String, SkillDef> skills, JsonNode raw) {

    // FAIL_ON_UNKNOWN_PROPERTIES off: the records model a few fields; G has many more.
    static final ObjectMapper JSON = new ObjectMapper()
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    // NORMAL: follow redirects. The Java HttpClient does not follow them by default.
    static final HttpClient HTTP = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NORMAL)
            .version(HttpClient.Version.HTTP_1_1) // no HTTP/2 upgrade request: see Api.HTTP
            .build();

    // region types
    // Boxed types (Integer, Double) are null when G has no such field.

    /** G.items[name]. gives: [stat, amount] pairs (potions). cooldown in ms. s: the stack size, null = no stack. */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record ItemDef(String name, String type, long g, Integer s, List<List<Object>> gives, Double cooldown) {}

    /** G.monsters[type]. speed in px/s, frequency in attacks/s, respawn in s (-1 = never by itself). */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record MonsterDef(String name, double hp, double attack, double speed, double range,
                             double frequency, double xp, double respawn, Double size) {}

    /** G.skills[name]. cooldown in ms; share: the skill whose cooldown this skill uses. */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record SkillDef(String name, Double cooldown, Double mp, Double range, String share, Integer level) {}
    // endregion types

    /** Makes the typed records from the JSON text of G. */
    public static GData parse(String json) throws IOException {
        JsonNode raw = JSON.readTree(json);
        return new GData(raw.path("version").asInt(),
                JSON.convertValue(raw.path("items"), new TypeReference<Map<String, ItemDef>>() {}),
                JSON.convertValue(raw.path("monsters"), new TypeReference<Map<String, MonsterDef>>() {}),
                JSON.convertValue(raw.path("skills"), new TypeReference<Map<String, SkillDef>>() {}),
                raw);
    }

    static String get(String url) throws IOException, InterruptedException {
        var req = HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(60)).build(); // 60 s: G is a few MB
        var res = HTTP.send(req, HttpResponse.BodyHandlers.ofString());
        if (res.statusCode() != 200) throw new IOException(url + ": HTTP " + res.statusCode());
        return res.body();
    }

    // region fetch-version
    /** The game page has var VERSION='<n>' (htmls/base_script.html:32). null if it is not found. */
    public static Integer fetchVersion(String base) throws IOException, InterruptedException {
        var m = Pattern.compile("var\\s+VERSION\\s*=\\s*'(\\d+)'").matcher(get(base + "/hub"));
        return m.find() ? Integer.valueOf(m.group(1)) : null;
    }
    // endregion fetch-version

    // region download-g
    /** /data.js is the script `var G={...};`. The JSON is the text from the first { to the last }. */
    static String downloadText(String base) throws IOException, InterruptedException {
        String js = get(base + "/data.js");
        int first = js.indexOf('{'), last = js.lastIndexOf('}');
        if (first < 0 || last < first) throw new IOException(base + "/data.js: no JSON object in it");
        return js.substring(first, last + 1);
    }

    /** Downloads G and parses it. */
    public static GData downloadG(String base) throws IOException, InterruptedException {
        return parse(downloadText(base));
    }
    // endregion download-g

    /**
     * .al-cache/<host>/G_<version>.json. <host> is the host and port of `base`, with ":" made "_"
     * (a file name cannot have ":" on Windows), so that the G of the test server and the live G
     * never mix.
     */
    public static Path cachePath(String base, int version) {
        String host = URI.create(base).getAuthority().replace(':', '_');
        return Path.of(".al-cache", host, "G_" + version + ".json");
    }

    // region load-g
    /** G from the cache when the cache has this version; else download it and save it. */
    public static GData loadG(String base) throws IOException, InterruptedException {
        Integer version = fetchVersion(base);
        if (version != null && Files.exists(cachePath(base, version))) {
            return parse(Files.readString(cachePath(base, version)));
        }
        String json = downloadText(base);
        GData G = parse(json);
        Path file = cachePath(base, G.version()); // the version in G itself is the true one
        Files.createDirectories(file.getParent());
        Files.writeString(file, json);
        System.out.println("downloaded G version " + G.version());
        return G;
    }

    /** loadG with Api.baseUrl(). */
    public static GData loadG() throws IOException, InterruptedException {
        return loadG(Api.baseUrl());
    }
    // endregion load-g
}
