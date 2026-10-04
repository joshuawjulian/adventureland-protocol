// Travel.java: walk around walls, go through doors, use the transporter, and get out of jail.
// Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
//
// It uses the Grid for the walls, and Actions.moveTo for each straight part of the walk.
// Threads: the methods block the calling thread (moveTo sleeps), so call them from your loop,
// never from a handler. Reads of `me` hold the World lock; no send happens inside it.
package albot;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BooleanSupplier;

public final class Travel {
    // The distances of the server (node/server.js:221-223): a door works within 112 px of its
    // box, the transporter NPC within 160 px of the NPC.
    static final double DOOR_DIST = 112, TRANSPORTER_DIST = 160;
    // How long to wait for `new_map` after a transport. Live sends it at once for a door; for the
    // bank it comes after the account loads (in_progress).
    static final long NEW_MAP_MS = 5000;

    /** One step between maps: stand at (x, y) on `map`, then transport to `to`, spawn `spawn`. */
    public record Hop(String map, double x, double y, String to, int spawn, String by) {}

    private final World world;
    private final Actions act;
    private final GData G;

    public Travel(World world, Actions act) {
        this.world = world;
        this.act = act;
        this.G = world.G;
    }

    // region walk-to
    /**
     * Walks to (x, y) on this map, around the walls. If (x, y) is not walkable, it walks to the
     * nearest walkable point (at most 320 px away). Returns true when we arrived; false when there
     * is no path, or when something stopped the walk: a `correction`, a death, a door, or jail.
     * The caller decides again on its next tick.
     */
    public boolean walkTo(double x, double y) throws InterruptedException {
        String map;
        int m;
        double sx, sy;
        synchronized (world) {
            world.advance();
            map = world.me.path("map").asText();
            m = world.me.path("m").asInt(); // the map counter: it changes on each map change
            sx = world.me.path("x").asDouble();
            sy = world.me.path("y").asDouble();
        }
        Grid grid = Grid.forMap(G, map);
        if (!grid.safe(x, y)) {
            int k = grid.nearestFree(x, y);
            if (k < 0) return false;
            double[] p = grid.point(k);
            x = p[0];
            y = p[1];
        }
        List<double[]> path = grid.findPath(sx, sy, x, y);
        if (path == null) return false;
        for (double[] p : path) {
            boolean arrived = act.moveTo(p[0], p[1]);
            synchronized (world) {
                JsonNode me = world.me;
                // We left this map, or died.
                if (!me.path("map").asText().equals(map) || me.path("m").asInt() != m || isDead(me)) return false;
            }
            if (!arrived) return false; // a correction: our position was wrong
        }
        return true;
    }

    /** `rip` is false, true, or the name of a gravestone. */
    static boolean isDead(JsonNode me) {
        JsonNode rip = me.path("rip");
        return rip.isTextual() || rip.asBoolean();
    }
    // endregion walk-to

    // region transport
    /**
     * Sends `transport` {to, s}: through a door near us, or with the transporter NPC near us.
     * Then waits until `new_map` puts us on `map`. The server answers a door with success and
     * sends `new_map` first; the bank answers {in_progress: true}, and `new_map` comes later
     * (node/server.js:5887-6056).
     */
    public boolean transport(String map, int spawn) throws InterruptedException {
        int m;
        synchronized (world) { m = world.me.path("m").asInt(); }
        Actions.GameResponse r = act.request("transport", Map.of("to", map, "s", spawn));
        if (r == null || r.failed()) return false; // for example transport_cant_reach: too far from the door
        return waitUntil(() -> {
            synchronized (world) {
                return world.me.path("m").asInt() != m && world.me.path("map").asText().equals(map);
            }
        }, NEW_MAP_MS);
    }
    // endregion transport

    // region leave-jail
    /**
     * A line violation (a `move` from or to a point that is not walkable) sends the character to
     * the map `jail`. `leave` takes it to `main` spawn 0, the town (node/server.js:5864-5885). It
     * fails while the character is dead, or with more than 5 monsters on it.
     */
    public boolean leaveJail() throws InterruptedException {
        Actions.GameResponse r = act.request("leave", Map.of());
        if (r == null || r.failed()) return false;
        return waitUntil(() -> {
            synchronized (world) { return !world.me.path("map").asText().equals("jail"); }
        }, NEW_MAP_MS);
    }
    // endregion leave-jail

    // region route
    /**
     * The ways out of `map`: each door that needs no key, and each place of the transporter if
     * the map has one. A door [x, y, w, h, to, to_spawn, own_spawn, lock] works from its own
     * spawn point (door[6]); the server measures from the box of the door at that spawn
     * (node/server.js:5899-5910).
     */
    public List<Hop> exits(String map) {
        JsonNode def = G.raw().path("maps").path(map);
        List<Hop> out = new ArrayList<>();
        if (!def.isObject()) return out;
        for (JsonNode door : def.path("doors")) {
            if (door.hasNonNull(7) && !door.path(7).asText().isEmpty()) continue; // a locked door ("ulocked"): it needs a key first
            JsonNode spawn = def.path("spawns").path(door.path(6).asInt());
            if (spawn.isArray()) {
                out.add(new Hop(map, spawn.path(0).asDouble(), spawn.path(1).asDouble(),
                        door.path(4).asText(), door.path(5).asInt(0), "door"));
            }
        }
        for (JsonNode npc : def.path("npcs")) {
            if (!npc.path("id").asText().equals("transporter")) continue;
            JsonNode pos = npc.has("position") ? npc.path("position") : npc.path("positions").path(0);
            if (!pos.isArray()) continue;
            // G.npcs.transporter.places: map -> the spawn where she sends you.
            var places = G.raw().path("npcs").path("transporter").path("places").fields();
            while (places.hasNext()) {
                var place = places.next();
                if (!place.getKey().equals(map)) {
                    out.add(new Hop(map, pos.path(0).asDouble(), pos.path(1).asDouble(),
                            place.getKey(), place.getValue().asInt(), "transporter"));
                }
            }
        }
        return out;
    }

    /**
     * The fewest hops from `from` to `to`: a breadth-first search on the graph of maps. Returns
     * an empty list when we are there, or null when no route exists.
     */
    public List<Hop> route(String from, String to) {
        if (from.equals(to)) return List.of();
        Map<String, Hop> came = new HashMap<>(); // map -> the hop that reached it (null for `from`)
        came.put(from, null);
        var queue = new ArrayDeque<String>();
        queue.add(from);
        while (!queue.isEmpty()) {
            String map = queue.poll();
            for (Hop hop : exits(map)) {
                if (came.containsKey(hop.to()) || !G.raw().path("maps").has(hop.to())) continue;
                came.put(hop.to(), hop);
                if (hop.to().equals(to)) {
                    List<Hop> hops = new ArrayList<>();
                    for (Hop h = hop; h != null; h = came.get(h.map())) hops.add(0, h);
                    return hops;
                }
                queue.add(hop.to());
            }
        }
        return null;
    }

    /**
     * Goes to `map` along route(): for each hop, walk to the door (or to the transporter), then
     * transport. Returns true when we are on `map`.
     */
    public boolean goToMap(String map) throws InterruptedException {
        String here;
        synchronized (world) { here = world.me.path("map").asText(); }
        List<Hop> hops = route(here, map);
        if (hops == null) return false;
        for (Hop hop : hops) {
            if (!walkTo(hop.x(), hop.y())) return false;
            // walkTo can stop short of the point (at the nearest walkable cell). The server then
            // says "transport_cant_reach"; do not even ask.
            double reach = hop.by().equals("door") ? DOOR_DIST : TRANSPORTER_DIST;
            synchronized (world) {
                if (Math.hypot(world.me.path("x").asDouble() - hop.x(), world.me.path("y").asDouble() - hop.y()) > reach) return false;
            }
            if (!transport(hop.to(), hop.spawn())) return false;
        }
        synchronized (world) { return world.me.path("map").asText().equals(map); }
    }
    // endregion route

    /** Polls `test` every 50 ms until it is true, or until `ms` have passed. */
    static boolean waitUntil(BooleanSupplier test, long ms) throws InterruptedException {
        for (long end = System.currentTimeMillis() + ms; System.currentTimeMillis() < end; Thread.sleep(50)) {
            if (test.getAsBoolean()) return true;
        }
        return test.getAsBoolean();
    }
}
