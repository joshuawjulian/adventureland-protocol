// FirstKill.java: the checkpoint of Part 2. Enter the game, heal, walk to the nearest goo,
// kill it, open its chest, print the xp.
// Uses albot.Bot. Java 21; Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=<name> mvn -q compile exec:java -Dexec.mainClass=FirstKill
import albot.Bot;
import albot.World;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public class FirstKill {
    static final long LIMIT_MS = 90_000; // 90 s: a level 1 warrior kills a goo in well under that
    static final long TICK_MS = 100;     // one turn of the loop: often enough, cheap on the call-cost
    static final long RIP_MS = 12_000;   // 12 s: B.rip_time, the wait before `respawn` (node/server.js:224)

    public static void main(String[] args) throws Exception {
        Bot bot = Bot.connect(); // HTTP login, G, socket, handshake
        try {
            run(bot);
        } finally {
            bot.close(); // the server then saves the character and marks it offline
        }
    }

    static void run(Bot bot) throws Exception {
        World world = bot.world;
        synchronized (world) { // the dispatcher thread changes `me`: hold the lock to read it
            System.out.printf("in game as %s (%s, level %d) on %s at %s%n", world.me.path("id").asText(),
                    world.me.path("ctype").asText(), world.me.path("level").asInt(), world.me.path("map").asText(),
                    xy(world.me));
        }

        // The goo is dead on its `death`, or on a `hit` with kill: true. Our own handlers, so that
        // we see it also when the goo leaves `monsters` for another reason.
        var target = new String[1]; // the id of our goo; set once, below
        var killed = new AtomicBoolean();
        world.listen("death", d -> { if (d.path("id").asText().equals(target[0])) killed.set(true); });
        world.listen("hit", d -> {
            if (d.path("kill").asBoolean() && d.path("id").asText().equals(target[0])) killed.set(true);
        });
        var diedAt = new AtomicLong(); // for the "respawn in <s> s" line only; Actions keeps its own
        world.listen("game_response", d -> {
            if (d.path("response").asText().equals("defeated_by_a_monster")) diedAt.set(World.nowMs());
        });

        long deadline = World.nowMs() + LIMIT_MS;
        while (!killed.get()) {
            if (World.nowMs() > deadline) throw new IllegalStateException("no kill in 90 s");
            world.advance(); // positions are now, not at the last update
            double hp, maxHp, range;
            boolean dead;
            synchronized (world) {
                hp = world.me.path("hp").asDouble();
                maxHp = world.me.path("max_hp").asDouble();
                range = world.me.path("range").asDouble();
                JsonNode rip = world.me.path("rip"); // false, true, or the name of a gravestone
                dead = rip.isTextual() || rip.asBoolean();
            }

            if (dead) {
                long left = diedAt.get() == 0 ? RIP_MS : Math.max(0, diedAt.get() + RIP_MS - World.nowMs());
                System.out.println("died; respawn in " + Math.round(left / 1000.0) + " s");
                if (!bot.act.respawn()) throw new IllegalStateException("respawn failed");
                synchronized (world) { System.out.println("respawned at " + xy(world.me)); }
                continue;
            }

            // Heal first: under 70 % hp, when the potion timer is ready.
            if (hp < 0.7 * maxHp && bot.cooldowns.ready("potion")) {
                if (bot.act.heal("hp")) { // the `player` update came before the reply
                    synchronized (world) {
                        System.out.printf("heal hp: %d/%d%n", Math.round(world.me.path("hp").asDouble()),
                                Math.round(world.me.path("max_hp").asDouble()));
                    }
                }
                Thread.sleep(TICK_MS);
                continue;
            }

            // Choose the target once: the nearest goo.
            if (target[0] == null) {
                ObjectNode goo = world.nearestMonster("goo");
                if (goo == null) { // none in view now; a new one spawns soon
                    Thread.sleep(TICK_MS);
                    continue;
                }
                synchronized (world) {
                    target[0] = goo.path("id").asText();
                    System.out.println("target: goo " + target[0] + " at " + xy(goo));
                }
            }

            double gap = -1, gx = 0, gy = 0, mx = 0, my = 0;
            synchronized (world) {
                ObjectNode goo = world.monsters.get(target[0]);
                if (goo != null) { // null: out of view for a moment; wait for the next update
                    gap = world.distance(world.me, goo);
                    gx = goo.path("x").asDouble();
                    gy = goo.path("y").asDouble();
                    mx = world.me.path("x").asDouble();
                    my = world.me.path("y").asDouble();
                }
            }
            if (gap > range) {
                // Walk to the point on the line goo -> us that is range - 10 px from the goo.
                // 10 px: a margin, because the goo walks too. The centres are farther apart than
                // the boxes, so the gap there is less than our range.
                double d = Math.hypot(mx - gx, my - gy);
                double r = Math.max(range - 10, 0);
                if (d > 0) bot.act.moveTo(gx + (mx - gx) / d * r, gy + (my - gy) / d * r);
            } else if (gap >= 0 && bot.cooldowns.ready("attack")) {
                bot.act.attack(target[0]);
            }
            Thread.sleep(TICK_MS);
        }
        System.out.println("killed goo " + target[0]);

        // The chest (`drop`) comes just after the kill. Wait up to 3 s for it.
        long until = World.nowMs() + 3000;
        while (World.nowMs() < until) {
            synchronized (world) { if (!world.chests.isEmpty()) break; }
            Thread.sleep(TICK_MS);
        }
        List<String> ids;
        synchronized (world) { ids = List.copyOf(world.chests.keySet()); }
        for (String id : ids) {
            JsonNode r = bot.act.openChest(id);
            if (r == null || r.path("gone").asBoolean()) continue;
            // The gold is after the 10 % tax of the server.
            System.out.println("chest " + id + ": +" + r.path("gold").asLong() + " gold, "
                    + r.path("items").size() + " item(s)");
        }

        synchronized (world) {
            System.out.printf("xp: %d/%d, level %d%n", world.me.path("xp").asLong(),
                    world.me.path("max_xp").asLong(), world.me.path("level").asInt());
        }
        System.out.println("OK");
    }

    /** "x,y" with the position rounded to integers. */
    static String xy(JsonNode e) {
        return Math.round(e.path("x").asDouble()) + "," + Math.round(e.path("y").asDouble());
    }
}
