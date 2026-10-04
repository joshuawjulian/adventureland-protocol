// Farmer.java: the decisions of a fighting character, one tick at a time: stay alive, loot,
// choose a target, walk, attack. Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
//
// tick() does the first thing on this list that applies, and returns. It remembers nothing
// between ticks except the target and the counters, so a monster that attacks during a walk
// changes the next tick at once.
//   1. dead: respawn          2. in jail: leave          3. on another map: go home
//   4. low hp or mp: heal     5. a chest: open it        6. no target: choose one
//   7. too far: walk          8. in range: attack
//
// Threads: the handlers (dispatcher thread) and tick (your loop) share the target and the
// counters: they are behind the lock of this object. Reads of `me` hold the World lock.
package albot;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.ArrayList;
import java.util.List;

public final class Farmer {
    // region ladder
    /** The Mainland ladder of the game guide ("Your first day"): the next monster when the current one is too easy. All live on `main`. */
    public static final List<String> LADDER = List.of("goo", "bee", "crab", "snake", "squig", "armadillo", "croc", "tortoise");
    // "Too easy": the last 3 kills took 2 attacks or fewer each (the guide's rule: "go to the next
    // monster when you kill the current one in one or two hits").
    static final int EASY_HITS = 2, EASY_KILLS = 3;
    // endregion ladder

    // Heal below 70 % hp: a potion (or the free regeneration) brings us back up before a weak
    // monster can take the other 30 %. Mana below 30 %: a class that uses mana for attacks
    // (priest, mage) needs it.
    static final double HEAL_HP = 0.7, HEAL_MP = 0.3;
    // Stop 10 px inside our range: the monster moves while we walk.
    static final double RANGE_MARGIN = 10;
    static final long RIP_MS = 12000; // B.rip_time (node/server.js:224)

    private final World world;
    private final Actions act;
    private final Cooldowns cooldowns;
    private final Travel travel;
    private final String prefix; // put before each line that it prints ("Tester: ")

    // Guarded by `this`:
    private String type = "goo"; // the monster type that we hunt now
    private String home = "main"; // the map of our monsters
    private String target = null; // the id of the monster that we attack
    private int kills = 0;
    private int hits = 0; // our hits on the target
    private List<Integer> recent = new ArrayList<>(); // hits for each of the last kills
    private long diedAt = 0; // for the "respawn in <s> s" line

    public Farmer(World world, Actions act, Cooldowns cooldowns, Travel travel, String prefix) {
        this.world = world;
        this.act = act;
        this.cooldowns = cooldowns;
        this.travel = travel;
        this.prefix = prefix;
        // The target is dead when we get `death` with its id, or a `hit` with `kill`.
        world.listen("death", d -> dead(d.path("id").asText()));
        world.listen("hit", d -> {
            String id = d.path("id").asText();
            synchronized (this) {
                if (!id.equals(target)) return;
                if (d.path("hid").asText().equals(world.me.path("id").asText())) hits++; // the handler runs in the World lock
            }
            if (d.path("kill").asBoolean()) dead(id);
        });
        world.listen("game_response", d -> {
            if (d.path("response").asText().equals("defeated_by_a_monster")) {
                synchronized (this) { diedAt = System.currentTimeMillis(); }
            }
        });
        // Each chest that opens for us.
        world.listen("chest_opened", r -> {
            if (!r.path("gone").asBoolean()) {
                log("chest " + r.path("id").asText() + ": +" + r.path("gold").asLong() + " gold, "
                        + r.path("items").size() + " item(s)");
            }
        });
    }

    public Farmer(World world, Actions act, Cooldowns cooldowns, Travel travel) {
        this(world, act, cooldowns, travel, "");
    }

    public void log(String line) {
        System.out.println(prefix + line);
    }

    public synchronized int kills() { return kills; }
    public synchronized String type() { return type; }
    public synchronized void setType(String type) { this.type = type; }
    public synchronized String home() { return home; }
    public synchronized void setHome(String home) { this.home = home; }
    public synchronized String target() { return target; }
    /** Forget the target: tick chooses again (for example after a walk to the town). */
    public synchronized void clearTarget() { target = null; }

    private synchronized void dead(String id) {
        if (!id.equals(target)) return;
        log("killed " + type + " " + id);
        kills++;
        recent.add(hits);
        if (recent.size() > EASY_KILLS) recent.remove(0);
        target = null;
        hits = 0;
    }

    // region next-type
    /**
     * Moves up the ladder when the last kills were easy. Returns true when the type changed.
     * Check the next monster in the game guide first: its damage per second must be less than
     * your healing (game guide, "Your first day").
     */
    public synchronized boolean nextType() {
        int i = LADDER.indexOf(type);
        boolean easy = recent.size() == EASY_KILLS && recent.stream().allMatch(h -> h <= EASY_HITS);
        if (!easy || i < 0 || i + 1 >= LADDER.size()) return false;
        type = LADDER.get(i + 1);
        recent = new ArrayList<>();
        target = null;
        log("next monster: " + type);
        return true;
    }
    // endregion next-type

    // region tick
    public void tick() throws InterruptedException {
        // A copy of what we need from `me`, inside the World lock; the actions run outside it.
        boolean dead;
        String map;
        double hp, maxHp, mp, maxMp, range;
        synchronized (world) {
            world.advance(); // positions at this moment
            ObjectNode me = world.me;
            dead = Travel.isDead(me);
            map = me.path("map").asText();
            hp = me.path("hp").asDouble();
            maxHp = me.path("max_hp").asDouble();
            mp = me.path("mp").asDouble();
            maxMp = me.path("max_mp").asDouble();
            range = me.path("range").asDouble();
        }
        String myType, myHome;
        synchronized (this) {
            myType = type;
            myHome = home;
        }

        // 1. Dead: wait for the 12 s, then respawn (at main spawn 5 on `main`).
        if (dead) {
            long died;
            synchronized (this) { died = diedAt; }
            long left = died == 0 ? RIP_MS : Math.max(0, died + RIP_MS - System.currentTimeMillis());
            log("died; respawn in " + (long) Math.ceil(left / 1000.0) + " s");
            if (act.respawn()) synchronized (world) { log("respawned at " + xy(world.me)); }
            return;
        }
        // 2. Jail: a line violation put us there. `leave` goes to the town.
        if (map.equals("jail")) {
            log("in jail: leave");
            if (travel.leaveJail()) {
                synchronized (world) { log("left jail: on " + world.me.path("map").asText() + " at " + xy(world.me)); }
            }
            return;
        }
        // 3. Another map (a door, the bank, a respawn somewhere else): go home.
        if (!map.equals(myHome)) {
            log("on " + map + ": go to " + myHome);
            travel.goToMap(myHome);
            return;
        }
        // 4. Health first, then mana. heal() drinks a potion if we have one.
        if (cooldowns.ready("potion")) {
            if (hp < HEAL_HP * maxHp) act.heal("hp");
            else if (mp < HEAL_MP * maxMp) act.heal("mp");
        }
        // 5. Chests: open them all. Gold and items wait in a chest for 8 min only.
        boolean chests;
        synchronized (world) { chests = !world.chests.isEmpty(); }
        if (chests) {
            act.openChests();
            return;
        }
        // 6. The target. Choose the nearest of our type if we have none.
        String id;
        double tx, ty, gap, mx, my;
        synchronized (world) {
            String current;
            synchronized (this) { current = target; } // World lock, then ours: the order of the handlers too
            ObjectNode t = current == null ? null : world.monsters.get(current);
            if (t == null) {
                t = world.nearestMonster(myType);
                if (t != null) {
                    synchronized (this) {
                        target = t.path("id").asText();
                        hits = 0;
                    }
                    log("target: " + myType + " " + t.path("id").asText() + " at " + xy(t));
                }
            }
            if (t == null) {
                id = null;
                tx = ty = gap = mx = my = 0;
            } else {
                id = t.path("id").asText();
                tx = t.path("x").asDouble();
                ty = t.path("y").asDouble();
                gap = world.distance(world.me, t);
                mx = world.me.path("x").asDouble();
                my = world.me.path("y").asDouble();
            }
        }
        if (id == null) {
            // None in view: walk to the middle of its spawn box (G.maps[map].monsters).
            for (JsonNode pack : world.G.raw().path("maps").path(map).path("monsters")) {
                if (!pack.path("type").asText().equals(myType) || !pack.path("boundary").isArray()) continue;
                JsonNode b = pack.path("boundary");
                travel.walkTo((b.path(0).asDouble() + b.path(2).asDouble()) / 2, (b.path(1).asDouble() + b.path(3).asDouble()) / 2);
                break;
            }
            return;
        }
        // 7. Too far: walk to a point `range - 10` px from it, on the line to us.
        if (gap > range) {
            double dx = mx - tx, dy = my - ty;
            double d = Math.hypot(dx, dy);
            if (d == 0) d = 1;
            double stop = Math.max(0, range - RANGE_MARGIN);
            travel.walkTo(tx + dx / d * stop, ty + dy / d * stop);
            return;
        }
        // 8. In range: attack when the cooldown allows.
        if (cooldowns.ready("attack")) act.attack(id);
    }
    // endregion tick

    /** "x,y" with the position rounded to integers. */
    static String xy(JsonNode e) {
        return Math.round(e.path("x").asDouble()) + "," + Math.round(e.path("y").asDouble());
    }
}
