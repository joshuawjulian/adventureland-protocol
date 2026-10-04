// Actions.java: the things that a character does: move, attack, heal, loot, respawn.
// Each action sends its event through the Budget and, if the server answers, waits for the answer.
// Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
//
// Threads: the methods block the thread that calls them (Thread.sleep and future.get), so call
// them from your loop, never from a handler: a handler that waits blocks the dispatcher, and
// then the answer that it waits for never arrives.
package albot;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.function.Predicate;

public final class Actions {
    private final AlSocket sock;
    private final World world;
    private final Cooldowns cooldowns;
    private final Budget budget;
    private long diedAt = 0; // System.currentTimeMillis() of our last death; guarded by `this`

    public Actions(AlSocket sock, World world, Cooldowns cooldowns, Budget budget) {
        this.sock = sock;
        this.world = world;
        this.cooldowns = cooldowns;
        this.budget = budget;
        // The death of our character: game_response "defeated_by_a_monster" {monster, xp}.
        world.listen("game_response", d -> {
            if (d.path("response").asText().equals("defeated_by_a_monster")) {
                synchronized (this) { diedAt = System.currentTimeMillis(); }
            }
        });
    }

    // region normalize
    /**
     * game_response in one shape. response: the code ("data", "cooldown", "too_far", ...).
     * place: the event that it answers (null if the server did not say). raw: the whole payload,
     * for the fields of each code (for example `ms` of "cooldown").
     */
    public record GameResponse(String response, String place, boolean failed, boolean success, JsonNode raw) {}

    /** game_response arrives as an object or as a bare string. Make it one shape. */
    public static GameResponse normalize(JsonNode data) {
        if (data.isTextual()) return new GameResponse(data.asText(), null, false, false, data);
        return new GameResponse(data.path("response").asText(), data.path("place").asText(null),
                data.path("failed").asBoolean(false), data.path("success").asBoolean(false), data);
    }

    /** A waitFor predicate: a game_response object about this `place`. */
    public static Predicate<JsonNode> responseFor(String place) {
        return d -> d.isObject() && place.equals(d.path("place").asText());
    }
    // endregion normalize

    // region request
    /**
     * Sends `event` and waits for the game_response whose place matches. The wait starts BEFORE
     * the emit, so that a fast answer cannot pass first. null if no answer came in time (some
     * failures answer with another event, for example `disappear`).
     */
    public GameResponse request(String event, Object payload, String place, long timeoutMs) throws InterruptedException {
        var reply = sock.waitFor("game_response", responseFor(place), Duration.ofMillis(timeoutMs));
        budget.emit(event, payload);
        try {
            return normalize(reply.get());
        } catch (ExecutionException timeoutOrClosed) {
            return null;
        }
    }

    /** request with place = event and a 2 s timeout (a normal answer takes well under 1 s). */
    public GameResponse request(String event, Object payload) throws InterruptedException {
        return request(event, payload, event, 2000);
    }
    // endregion request

    // region move-to
    /**
     * Starts a straight walk to (x, y) on this map. No wait: the server does not answer `move`.
     * It ignores a move whose `m` is not its map counter (node/server.js:11203).
     */
    public void move(double x, double y) throws InterruptedException {
        Map<String, Object> payload;
        synchronized (world) {
            world.advance(); // our position now
            ObjectNode me = world.me;
            payload = Map.of("x", me.path("x").asDouble(), "y", me.path("y").asDouble(),
                    "going_x", x, "going_y", y, "m", me.path("m").asInt());
            me.put("going_x", x).put("going_y", y).put("moving", true); // the server does the same
        }
        budget.emit("move", payload); // outside the world lock: emit can wait for room
    }

    /**
     * Walks in a straight line to (x, y) and waits until we should be there: the distance
     * divided by our speed, plus 250 ms for the network. True if we arrived. It does not go
     * around walls (Part 3 adds walkTo for that).
     */
    public boolean moveTo(double x, double y) throws InterruptedException {
        double seconds;
        synchronized (world) {
            world.advance();
            double dist = Math.hypot(x - world.me.path("x").asDouble(), y - world.me.path("y").asDouble());
            seconds = dist / Math.max(world.me.path("speed").asDouble(), 1); // speed is px/s; 1: never divide by 0
        }
        move(x, y);
        Thread.sleep((long) (seconds * 1000) + 250); // 250 ms: room for the network delay
        synchronized (world) {
            world.advance();
            ObjectNode me = world.me;
            return Math.hypot(me.path("x").asDouble() - x, me.path("y").asDouble() - y) < 1
                    && me.path("going_x").asDouble() == x && me.path("going_y").asDouble() == y;
        }
    }
    // endregion move-to

    // region attack
    /**
     * Attacks a monster or a player by id. Success: response "data" with pid and eta (a
     * successful attack has no `success` key); failure: failed with a code such as "cooldown"
     * or "too_far". null: no answer (a target that is gone gets `disappear` "not_there").
     */
    public GameResponse attack(String id) throws InterruptedException {
        return request("attack", Map.of("id", id));
    }
    // endregion attack

    // region heal
    /** The first inventory slot with a potion that gives `stat` ("hp" or "mp"), or -1. */
    int findPotion(String stat) {
        synchronized (world) {
            JsonNode items = world.me.path("items");
            for (int num = 0; num < items.size(); num++) {
                GData.ItemDef def = world.G.items().get(items.path(num).path("name").asText()); // empty slot: null
                if (def != null && def.gives() != null
                        && def.gives().stream().anyMatch(give -> stat.equals(give.get(0)))) return num;
            }
            return -1;
        }
    }

    /**
     * Drinks a potion that gives `stat` if we have one (equip with consume), else uses the free
     * regeneration (use). Both share one timer, "potion". False, without a request, when that
     * timer runs; false when the server says no.
     */
    public boolean heal(String stat) throws InterruptedException {
        if (!cooldowns.ready("potion")) return false;
        int num = findPotion(stat);
        GameResponse r = num >= 0
                ? request("equip", Map.of("num", num, "consume", true))
                : request("use", Map.of("item", stat));
        return r != null && !r.failed();
    }
    // endregion heal

    // region open-chests
    /** Opens one chest. Its answer is `chest_opened` (with gold and items, or gone: true), or null. */
    public JsonNode openChest(String id) throws InterruptedException {
        var opened = sock.waitFor("chest_opened", d -> id.equals(d.path("id").asText()), Duration.ofSeconds(2));
        budget.emit("open_chest", Map.of("id", id));
        try {
            return opened.get();
        } catch (ExecutionException timeout) {
            return null; // no answer: for example game_response "loot_no_space"
        }
    }

    /** Opens each chest that we know of. Returns how many opened (gone chests do not count). */
    public int openChests() throws InterruptedException {
        List<String> ids;
        synchronized (world) { ids = List.copyOf(world.chests.keySet()); }
        int count = 0;
        for (String id : ids) {
            JsonNode r = openChest(id);
            if (r != null && !r.path("gone").asBoolean()) count++;
            synchronized (world) { world.chests.remove(id); } // also when it failed: do not try forever
        }
        return count;
    }
    // endregion open-chests

    // region respawn
    /**
     * Call it when me.rip is set (true, or the name of a gravestone). Waits the rest of the 12 s
     * after the death (B.rip_time, node/server.js:224, 6282-6286), sends `respawn`, and tries one
     * more time if the server says "cant_respawn" (with the `ms` that are left).
     */
    public boolean respawn() throws InterruptedException {
        long wait;
        synchronized (this) { wait = diedAt + 12000 - System.currentTimeMillis(); } // 12 s: rip_time
        if (wait > 0) Thread.sleep(wait);
        // 3 s: the answer comes after `new_map` and `player`.
        GameResponse r = request("respawn", Map.of(), "respawn", 3000); // {safe: true} goes to "woffice"
        if (r != null && r.response().equals("cant_respawn")) { // too early: wait the rest, then once more
            Thread.sleep(r.raw().path("ms").asLong(1000));
            r = request("respawn", Map.of(), "respawn", 3000);
        }
        return r != null && !r.failed();
    }
    // endregion respawn
}
