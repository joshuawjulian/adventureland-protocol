// World.java: our copy of the world: our character (me), the monsters, the other players
// and the chests, kept up to date from the server's events.
// Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
//
// Threads: AlSocket calls the handlers on its dispatcher thread, and the program's own loop
// runs on another thread. So all state of a World is behind one lock: the World object itself.
// The handlers run inside it, and the public methods are synchronized. When your code reads
// `me`, `monsters`, `players` or `chests`, hold the lock too:
//     synchronized (world) { double x = world.me.path("x").asDouble(); ... }
package albot;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

public final class World {
    static final ObjectMapper JSON = new ObjectMapper();

    private final AlSocket sock;
    /** The game data. */
    public final GData G;
    private final Map<String, List<Consumer<JsonNode>>> handlers = new HashMap<>();
    private long lastAdvance = System.currentTimeMillis(); // when advance() last moved the entities

    /** Our character: the `start` payload (without `entities`), with each `player` merged in. Empty until `start`. */
    public ObjectNode me = JSON.createObjectNode();
    /** Monster id -> monster. */
    public final Map<String, ObjectNode> monsters = new LinkedHashMap<>();
    /** Id -> other player or NPC (never us). The id of a player is its name. */
    public final Map<String, ObjectNode> players = new LinkedHashMap<>();
    /** Chest id -> the `drop` payload. Removed on `chest_opened`. */
    public final Map<String, JsonNode> chests = new LinkedHashMap<>();

    // region constructor
    /** Registers the handlers. Make the World BEFORE you send `loaded` and `auth`, so that `start` reaches it. */
    public World(AlSocket sock, GData G) {
        this.sock = sock;
        this.G = G;
        listen("start", this::onStart);
        listen("player", this::onPlayer);
        listen("entities", this::applyEntities);
        listen("death", d -> monsters.remove(d.path("id").asText()));
        listen("disappear", d -> {
            monsters.remove(d.path("id").asText());
            players.remove(d.path("id").asText());
        });
        listen("new_map", this::onNewMap);
        listen("drop", d -> chests.put(d.path("id").asText(), d));
        listen("chest_opened", d -> chests.remove(d.path("id").asText()));
        // The server disagreed with our position (more than 132 px off, node/server.js:11248-11256).
        listen("correction", d -> me.put("x", d.path("x").asDouble()).put("y", d.path("y").asDouble()));
    }
    // endregion constructor

    // region listen
    /**
     * Adds a handler for an event. One table from event name to handlers, so that hitchhikers
     * (events that ride inside `player`) reach the same handlers as events that arrive alone.
     * The first listen for a name also subscribes to it on the socket.
     */
    public synchronized void listen(String name, Consumer<JsonNode> handler) {
        if (!handlers.containsKey(name)) {
            handlers.put(name, new ArrayList<>());
            sock.on(name, data -> dispatch(name, data));
        }
        handlers.get(name).add(handler);
    }

    /** Calls the handlers of `name`, inside the lock. A handler that throws does not stop the others. */
    public synchronized void dispatch(String name, JsonNode data) {
        for (var handler : List.copyOf(handlers.getOrDefault(name, List.of()))) {
            try {
                handler.accept(data);
            } catch (RuntimeException e) {
                System.err.println("world: handler for \"" + name + "\" threw: " + e);
            }
        }
    }
    // endregion listen

    // region on-start
    /** `start`: our full character, plus the first full view in `entities`. */
    public synchronized void onStart(JsonNode data) {
        me = data.deepCopy();
        me.remove("entities");
        lastAdvance = System.currentTimeMillis();
        applyEntities(data.path("entities"));
    }
    // endregion on-start

    // region on-player
    /** `player`: the fields of our character that changed. Merge them into `me`. */
    public synchronized void onPlayer(JsonNode data) {
        ObjectNode fields = data.deepCopy();
        fields.remove("hitchhikers");
        me.setAll(fields); // merge: `start` had fields that `player` does not repeat
        // Hitchhikers: [event, payload] pairs that rode along. Handle them as if they arrived alone.
        for (JsonNode pair : data.path("hitchhikers")) dispatch(pair.path(0).asText(), pair.path(1));
    }
    // endregion on-player

    // region apply-entities
    /**
     * Monsters send only the fields that differ from G.monsters[type]. Start from the G entry,
     * set max_hp to G's hp, then put the monster's own fields over them.
     */
    public ObjectNode withDefaults(JsonNode monster) {
        ObjectNode out = JSON.createObjectNode();
        JsonNode def = G.raw().path("monsters").path(monster.path("type").asText());
        if (def.isObject()) {
            out.setAll((ObjectNode) def.deepCopy());
            out.set("max_hp", def.path("hp"));
        }
        out.setAll((ObjectNode) monster.deepCopy()); // the monster's own fields win
        return out;
    }

    /** `entities`: a full view (type "all") or the entities that changed (type "xy"). */
    public synchronized void applyEntities(JsonNode data) {
        if (!data.path("in").asText().equals(me.path("in").asText())) return; // an instance we left (or before `start`)
        if (data.path("type").asText().equals("all")) { // a full view: forget everything first
            monsters.clear();
            players.clear();
        }
        // Each object is the complete current state of that entity: replace it, do not merge.
        for (JsonNode m : data.path("monsters")) monsters.put(m.path("id").asText(), withDefaults(m));
        String myId = me.path("id").asText();
        for (JsonNode p : data.path("players")) {
            String id = p.path("id").asText();
            if (!id.equals(myId)) players.put(id, p.deepCopy()); // the full view can include us
        }
    }
    // endregion apply-entities

    // region on-new-map
    /** `new_map`: we went through a door, were moved, or respawned. Its `entities` are a full view. */
    public synchronized void onNewMap(JsonNode data) {
        me.set("map", data.path("name"));
        me.set("in", data.path("in"));
        me.set("x", data.path("x"));
        me.set("y", data.path("y"));
        me.set("m", data.path("m")); // the map counter that `move` must send
        me.put("moving", false);
        applyEntities(data.path("entities"));
    }
    // endregion on-new-map

    // region step
    /**
     * Moves one moving entity toward going_x, going_y for `ms` milliseconds, the way the server
     * does (node/server.js:15129-15131). speed is in px per second: one step covers speed * ms / 1000 px.
     */
    public static void step(ObjectNode e, double ms) {
        if (!e.path("moving").asBoolean()) return;
        double x = e.path("x").asDouble(), y = e.path("y").asDouble();
        double gx = e.path("going_x").asDouble(), gy = e.path("going_y").asDouble();
        double left = Math.hypot(gx - x, gy - y); // the distance still to go
        double travel = e.path("speed").asDouble() * ms / 1000;
        if (travel >= left) { // arrived
            e.put("x", gx).put("y", gy).put("moving", false);
        } else {
            e.put("x", x + (gx - x) / left * travel).put("y", y + (gy - y) / left * travel);
        }
    }
    // endregion step

    // region advance
    /** Moves `me`, the monsters and the players forward to now. Call it before you read positions. */
    public synchronized void advance() {
        long now = System.currentTimeMillis();
        double ms = now - lastAdvance;
        lastAdvance = now;
        step(me, ms);
        for (ObjectNode e : monsters.values()) step(e, ms);
        for (ObjectNode e : players.values()) step(e, ms);
    }
    // endregion advance

    // region distance
    /**
     * The hit box {width, height} of an entity. A monster: G.dimensions[type], times
     * G.monsters[type].size (get_monster_dimensions, js/old_common_functions.js:692); a type
     * without an entry in G.dimensions is 24 x 24. A character: 26 x 36 (node/server.js:11782-11783).
     */
    public double[] box(JsonNode e) {
        String type = e.path("type").asText();
        GData.MonsterDef def = G.monsters().get(type);
        if (def == null) return new double[] {e.path("width").asDouble(26), e.path("height").asDouble(36)};
        JsonNode d = G.raw().path("dimensions").path(type);
        double w = d.path(0).asDouble(24), h = d.path(1).asDouble(24);
        if (def.size() != null) return new double[] {Math.round(w * def.size()), Math.round(h * def.size())};
        return new double[] {w, h};
    }

    /**
     * The distance that the server checks for range: the gap between two hit boxes, 0 when they
     * touch (distance(), js/old_common_functions.js:707-740). x is the centre, y is the feet.
     */
    public synchronized double distance(JsonNode a, JsonNode b) {
        if (a.has("map") && b.has("map") && !a.path("map").asText().equals(b.path("map").asText())) {
            return 99999999; // not on the same map: the value that the source uses
        }
        double[] ab = box(a), bb = box(b);
        double ax = a.path("x").asDouble(), ay = a.path("y").asDouble();
        double bx = b.path("x").asDouble(), by = b.path("y").asDouble();
        double dx = Math.max(Math.max(bx - bb[0] / 2 - (ax + ab[0] / 2), ax - ab[0] / 2 - (bx + bb[0] / 2)), 0);
        double dy = Math.max(Math.max(by - bb[1] - ay, ay - ab[1] - by), 0);
        return Math.hypot(dx, dy);
    }
    // endregion distance

    /** The monster closest to `me` (of this type; null type: any), or null if we see none. */
    public synchronized ObjectNode nearestMonster(String type) {
        ObjectNode best = null;
        double bestDist = Double.POSITIVE_INFINITY;
        for (ObjectNode m : monsters.values()) {
            if (type != null && !type.equals(m.path("type").asText())) continue;
            double d = distance(me, m);
            if (d < bestDist) {
                best = m;
                bestDist = d;
            }
        }
        return best;
    }

    /** nearestMonster of any type. */
    public ObjectNode nearestMonster() {
        return nearestMonster(null);
    }
}
