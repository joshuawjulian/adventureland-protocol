// Supplies.java: a farming bot that looks after itself. After each chest it wears better gear;
// when potions or bag space run low, it walks to the town, sells the loot, buys potions and the
// basic armor, and goes back to farm.
// Uses albot. Java 21; Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger mvn -q compile exec:java -Dexec.mainClass=Supplies -Dexec.args="1"
//      the argument: stop after this many town trips (the tests use 1). Without it: until Ctrl-C.
import albot.Actions;
import albot.Bot;
import albot.Farmer;
import albot.GData;
import albot.Items;
import albot.Travel;
import albot.World;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class Supplies {
    static final long TICK_MS = 100;

    // region rules
    // The restock rule (the game guide, "Your first hour" and "Inventory"):
    static final int MIN_POTIONS = 20; // go to town below 20 hpot0 or 20 mpot0 ...
    static final int MIN_FREE = 5;     // ... or below 5 free inventory slots
    static final int POTIONS = 50;     // buy up to 50 of each (20 gold each: 2,000 gold for both)
    static final long KEEP_GOLD = 2000; // never spend the potion money on armor ("Your first day", step 1)
    // The basic armor that a new character does not wear, from Gabriel (`basics`).
    static final List<String> ARMOR = List.of("gloves", "coat", "pants");
    // endregion rules

    static volatile boolean stop = false;
    static Bot bot;
    static World world;
    static GData G;
    static Travel travel;
    static Items items;

    public static void main(String[] args) throws Exception {
        Runtime.getRuntime().addShutdownHook(new Thread(() -> stop = true));
        int trips = args.length > 0 ? Integer.parseInt(args[0]) : 0;
        bot = Bot.connect();
        world = bot.world;
        G = bot.G;
        synchronized (world) {
            System.out.printf("in game as %s (%s, level %d) on %s at %s%n", world.me.path("id").asText(),
                    world.me.path("ctype").asText(), world.me.path("level").asInt(), world.me.path("map").asText(), xy(world.me));
        }
        travel = new Travel(world, bot.act);
        items = new Items(world, bot.act, bot.budget);
        Farmer farmer = new Farmer(world, bot.act, bot.cooldowns, travel);

        // region loop
        var chests = new AtomicInteger(); // chests opened so far (the dispatcher counts them)
        world.listen("chest_opened", r -> { if (!r.path("gone").asBoolean()) chests.incrementAndGet(); });
        int seen = 0; // chests that we checked after
        int done = 0;
        while (!stop && (trips == 0 || done < trips)) {
            Thread.sleep(TICK_MS);
            farmer.tick();
            if (chests.get() == seen) continue;
            // After each chest: wear what is better, then check the supplies.
            seen = chests.get();
            for (String line : items.equipBetter()) System.out.println("equip " + line);
            int hp = items.count("hpot0"), mp = items.count("mpot0"), free = items.freeSlots();
            if (hp >= MIN_POTIONS && mp >= MIN_POTIONS && free >= MIN_FREE) continue;
            System.out.printf("supplies low: %d hpot0, %d mpot0, %d free slot(s)%n", hp, mp, free);
            if (townTrip()) done++;
            farmer.clearTarget(); // choose again: the old target is far away now
        }
        // endregion loop

        bot.close();
        System.out.println("OK");
        System.exit(0);
    }

    // region town
    /** Walks to within NPC_DIST of an NPC. Says so only when it must walk. */
    static boolean goNear(Items.Npc npc) throws InterruptedException {
        if (npc == null) throw new IllegalStateException("no such NPC on this map");
        synchronized (world) {
            world.advance();
            if (Math.hypot(world.me.path("x").asDouble() - npc.x(), world.me.path("y").asDouble() - npc.y()) <= Items.NPC_DIST) return true;
        }
        System.out.printf("walk to %s at %d,%d%n", npc.id(), Math.round(npc.x()), Math.round(npc.y()));
        return travel.walkTo(npc.x(), npc.y());
    }

    /** Buys `quantity` of `name` from the NPC that sells it. */
    static boolean shop(String name, int quantity) throws InterruptedException {
        if (!goNear(items.npcSelling(name))) return false;
        Actions.GameResponse r = items.buy(name, quantity);
        if (r != null && !r.failed()) {
            System.out.printf("buy %s x%d: %d gold%n", name, r.raw().path("q").asInt(), r.raw().path("cost").asLong());
        } else {
            System.out.printf("buy %s: %s%n", name, r != null ? r.response() : "no answer");
        }
        return r != null && !r.failed();
    }

    static boolean townTrip() throws InterruptedException {
        // 1. Sell the loot to the potion shop (any shop buys any item).
        if (!goNear(items.npcSelling("hpot0"))) return false;
        int size;
        synchronized (world) { size = world.me.path("items").size(); }
        for (int num = 0; num < size; num++) {
            JsonNode it;
            synchronized (world) { it = world.me.path("items").path(num).deepCopy(); }
            if (!Items.isLoot(G, it)) continue;
            Actions.GameResponse r = items.sell(num, it.path("q").asInt(1));
            if (r != null && !r.failed()) System.out.printf("sell %s: +%d gold%n", it.path("name").asText(), r.raw().path("gold").asLong());
        }
        // 2. Potions, up to POTIONS of each.
        for (String name : List.of("hpot0", "mpot0")) {
            int need = POTIONS - items.count(name);
            if (need > 0) shop(name, need);
        }
        // 3. The basic armor that we do not wear, while the gold lasts.
        for (String name : ARMOR) {
            GData.ItemDef def = G.items().get(name);
            String slot = def.type(); // "gloves", "chest", "pants": the slot has the type's name
            boolean skip;
            synchronized (world) {
                skip = world.me.path("slots").path(slot).isObject() || world.me.path("gold").asLong() - def.g() < KEEP_GOLD;
            }
            if (!skip) shop(name, 1);
        }
        for (String line : items.equipBetter()) System.out.println("equip " + line);
        long gold;
        synchronized (world) { gold = world.me.path("gold").asLong(); }
        System.out.printf("bag: %d hpot0, %d mpot0, %d free slot(s), %d gold%n",
                items.count("hpot0"), items.count("mpot0"), items.freeSlots(), gold);
        return true;
    }
    // endregion town

    static String xy(JsonNode e) {
        return Math.round(e.path("x").asDouble()) + "," + Math.round(e.path("y").asDouble());
    }
}
