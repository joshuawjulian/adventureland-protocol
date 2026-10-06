// Farm.java: a farming bot. It kills monsters of the Mainland ladder, loots, heals, respawns,
// leaves jail, and reconnects with the course's reconnect rule.
// Uses albot. Java 21; Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger mvn -q compile exec:java -Dexec.mainClass=Farm -Dexec.args="25"
//      the argument: stop after this many seconds (the tests use 25). Without it: until Ctrl-C.
import albot.Bot;
import albot.Farmer;
import albot.Travel;
import albot.World;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class Farm {
    static final long TICK_MS = 100; // one decision every 100 ms: fast enough, and cheap in call-cost
    static final long STABLE_MS = 5 * 60_000; // after a session of 5 min, the reconnect wait starts again at the first value

    // region stop
    // Ctrl-C (SIGINT) or `docker stop` (SIGTERM): Java runs the shutdown hook. It asks the loop to
    // stop, then waits until the loop closed the socket and printed the summary (at most 10 s:
    // the JVM does not wait for ever).
    static volatile boolean stop = false;
    static final CountDownLatch finished = new CountDownLatch(1);

    /** A sleep that ends early when we stop. */
    static void pause(long ms) throws InterruptedException {
        for (long end = World.nowMs() + ms; !stop && World.nowMs() < end; ) {
            Thread.sleep(Math.max(1, Math.min(200, end - World.nowMs())));
        }
    }
    // endregion stop

    public static void main(String[] args) throws Exception {
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            if (finished.getCount() == 0) return; // a normal end
            stop = true;
            System.out.println("stopping");
            try { finished.await(10, java.util.concurrent.TimeUnit.SECONDS); } catch (InterruptedException e) { /* exit now */ }
        }));

        long seconds = args.length > 0 ? Long.parseLong(args[0]) : 0;
        long started = World.nowMs();
        long endAt = seconds > 0 ? started + seconds * 1000 : Long.MAX_VALUE;
        int kills = 0;
        int attempt = 0; // failed tries in a row, for reconnectDelayMs
        JsonNode last = null; // our character in the last session

        // region session
        while (!stop && World.nowMs() < endAt) {
            // 1. Connect. A failure (the server is full, the save of the last session still
            //    runs, ...) waits as the reconnect rule says, then tries again.
            Bot bot;
            try {
                bot = Bot.connect();
            } catch (Bot.LoginError | java.io.IOException e) {
                long ms = Bot.reconnectDelayMs(attempt++);
                System.out.println("connect failed: " + e.getMessage() + "; try again in " + ms / 1000 + " s");
                pause(ms);
                continue;
            }
            long session = World.nowMs();
            World world = bot.world;
            synchronized (world) {
                last = world.me;
                System.out.printf("in game as %s (%s, level %d) on %s at %d,%d%n", world.me.path("id").asText(),
                        world.me.path("ctype").asText(), world.me.path("level").asInt(), world.me.path("map").asText(),
                        Math.round(world.me.path("x").asDouble()), Math.round(world.me.path("y").asDouble()));
            }

            // 2. Play until we stop, the time is over, or the socket closes. AlSocket's local
            //    `disconnect` event has the reason.
            var lost = new AtomicReference<String>();
            world.listen("disconnect", r -> lost.compareAndSet(null, r.asText()));
            world.listen("disconnect_reason", r -> System.out.println("the server says: " + r.asText())); // "limitdc", "limits", ...
            Farmer farmer = new Farmer(world, bot.act, bot.cooldowns, new Travel(world, bot.act));
            try {
                while (!stop && lost.get() == null && World.nowMs() < endAt) {
                    Thread.sleep(TICK_MS);
                    farmer.tick();
                    farmer.nextType(); // a stronger monster when this one is too easy
                }
            } catch (RuntimeException e) {
                lost.compareAndSet(null, String.valueOf(e.getMessage()));
            }
            kills += farmer.kills();
            synchronized (world) { last = world.me.deepCopy(); }
            String reason = lost.get(); // read it first: close() fires our own `disconnect` event too
            bot.close();
            if (reason == null) break; // we stopped, or the time is over

            // 3. The reconnect rule: wait, then make a new socket and a full handshake.
            if (World.nowMs() - session >= STABLE_MS) attempt = 0;
            long ms = Bot.reconnectDelayMs(attempt++);
            System.out.println("disconnected: " + reason + "; reconnect in " + ms / 1000 + " s");
            pause(ms);
        }
        // endregion session

        long secs = Math.round((World.nowMs() - started) / 1000.0);
        System.out.printf("farmed %d s: %d kill(s), level %d, %d gold%n", secs, kills,
                last == null ? 0 : last.path("level").asInt(), last == null ? 0 : last.path("gold").asLong());
        System.out.println("OK");
        finished.countDown();
        System.exit(0);
    }
}
