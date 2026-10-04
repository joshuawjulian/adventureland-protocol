// PartyMerchant.java: three fighters and one merchant in one program. The fighters farm in a
// party. The merchant walks to them, takes their loot and gold, sells the loot in the town and
// puts the gold in the bank.
// Uses albot. Java 21; Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyWarrior mvn -q compile exec:java -Dexec.mainClass=PartyMerchant -Dexec.args="1"
//      AL_CHARACTER is the leader. The program adds the next two fighters of your character
//      list, and your first merchant.
//      the argument: stop after this many merchant trips (the tests use 1). Without it: until Ctrl-C.
// Make a merchant first, if you have none: -Dexec.args="--create-merchant MyMerchant"
//
// Threads: each fighter runs its loop on its own virtual thread; the merchant runs on the main
// thread. Each character has its own World, so each loop takes only its own World lock, except
// hasLoot(), which reads the World of a fighter under that fighter's lock.
import albot.Actions;
import albot.Api;
import albot.Farmer;
import albot.GData;
import albot.Items;
import albot.Party;
import albot.Travel;
import albot.World;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.List;

public class PartyMerchant {
    static final long TICK_MS = 100;

    // region rules
    static final int FIGHTERS = 3; // the live limit: 3 characters that fight, plus merchants (game guide, "Many characters and bots")
    static final double GIVE_DIST = 300; // `send` works within 400 px on the same map (node/server.js:8463-8560)
    static final long FIGHTER_GOLD = 20000; // a fighter keeps this much gold for potions, and gives the rest
    static final long MERCHANT_GOLD = 50000; // the merchant keeps this much, and banks the rest

    /**
     * A fighter keeps only its potions. Everything else goes to the merchant: loot to sell, and
     * jewelry that the merchant compounds later.
     */
    static boolean give(GData G, JsonNode it) {
        if (it == null || !it.isObject() || it.path("name").asText().equals("placeholder") || it.hasNonNull("l")) return false;
        GData.ItemDef def = G.items().get(it.path("name").asText());
        return def != null && !"pot".equals(def.type());
    }
    // endregion rules

    /** One character and its tools. farmer is null for the merchant: only fighters farm. */
    record Crew(Party.Member m, Travel travel, Items items, Party party, Farmer farmer) {}

    static volatile boolean stop = false;
    static GData G;
    static List<Crew> crew = new ArrayList<>();
    static Crew merchant;

    public static void main(String[] args) throws Exception {
        Runtime.getRuntime().addShutdownHook(new Thread(() -> stop = true));

        // region choose
        Api.Auth auth = Api.login();
        var lists = Api.serversAndCharacters(auth);
        if (args.length > 0 && args[0].equals("--create-merchant")) {
            String name = args.length > 1 ? args[1] : "";
            Party.createCharacter(auth, name, "merchant");
            System.out.println("created the merchant " + name + ". Run the program again without --create-merchant.");
            System.exit(0);
        }
        int trips = args.length > 0 ? Integer.parseInt(args[0]) : 0;
        Api.Server server = Api.findServer(lists.servers()); // AL_SERVER
        Api.Character leader = Api.findCharacter(lists.characters()); // AL_CHARACTER
        if (leader.type().equals("merchant")) throw new IllegalStateException("AL_CHARACTER must be a fighter: it leads the party");
        List<Api.Character> fighters = new ArrayList<>(List.of(leader));
        for (Api.Character c : lists.characters()) {
            if (fighters.size() < FIGHTERS && !c.type().equals("merchant") && !c.name().equals(leader.name())) fighters.add(c);
        }
        Api.Character merchantCharacter = lists.characters().stream()
                .filter(c -> c.type().equals("merchant")).findFirst()
                .orElseThrow(() -> new IllegalStateException("no merchant on this account: run with --create-merchant <Name> first"));
        System.out.println("team: " + String.join(", ", fighters.stream().map(Api.Character::name).toList())
                + "; merchant: " + merchantCharacter.name());
        // endregion choose

        // region connect
        G = GData.loadG(); // one G for all four
        List<Api.Character> all = new ArrayList<>(fighters);
        all.add(merchantCharacter);
        for (Api.Character c : all) {
            boolean fights = !c.type().equals("merchant");
            Party.Member m = Party.connectMember(auth, server, c, G);
            World w = m.world();
            synchronized (w) {
                System.out.printf("in game as %s (%s, level %d) on %s at %s%n", w.me.path("id").asText(),
                        w.me.path("ctype").asText(), w.me.path("level").asInt(), w.me.path("map").asText(), xy(w.me));
            }
            Travel travel = new Travel(w, m.act());
            crew.add(new Crew(m, travel, new Items(w, m.act(), m.budget()), new Party(w, m.act()),
                    // Only fighters farm. (A Farmer also prints each chest that opens for us.)
                    fights ? new Farmer(w, m.act(), m.cooldowns(), travel, m.name() + ": ") : null));
        }
        Crew lead = crew.get(0);
        merchant = crew.get(crew.size() - 1);
        // endregion connect

        // region party
        // The leader invites each one; each waits for its `invite`, then accepts.
        for (Crew c : crew.subList(1, crew.size())) {
            lead.party().invite(c.m().name());
            if (!c.party().waitInvite(lead.m().name())) throw new IllegalStateException(c.m().name() + " got no invitation");
            Actions.GameResponse r = c.party().accept(lead.m().name());
            if (r == null || r.failed()) throw new IllegalStateException(c.m().name() + " could not join: " + (r != null ? r.response() : "no answer"));
        }
        for (int waited = 0; lead.party().list().size() < crew.size() && waited < 5000; waited += 100) Thread.sleep(100);
        System.out.println("party: " + String.join(", ", lead.party().list()));
        // endregion party

        // region run
        List<Thread> fighting = new ArrayList<>();
        for (Crew f : crew.subList(0, crew.size() - 1)) {
            fighting.add(Thread.ofVirtual().start(() -> {
                try {
                    fighterLoop(f);
                } catch (InterruptedException e) {
                    // the program ends
                }
            }));
        }
        int done = 0;
        while (!stop && (trips == 0 || done < trips)) {
            if (merchantTrip()) done++;
        }
        stop = true; // the fighters end their loops
        for (Thread t : fighting) t.join();
        for (Crew c : crew) c.m().close();
        System.out.println("OK");
        System.exit(0);
        // endregion run
    }

    // region fighter
    /** A fighter farms. When the merchant is near, it gives its loot and gold. */
    static void fighterLoop(Crew f) throws InterruptedException {
        World world = f.m().world();
        String merchantName = merchant.m().name();
        while (!stop) {
            Thread.sleep(TICK_MS);
            f.farmer().tick();
            List<int[]> gifts = new ArrayList<>(); // {slot, quantity}
            long gold;
            synchronized (world) {
                world.advance();
                JsonNode near = world.players.get(merchantName); // the merchant, if it is in our view
                if (near == null || world.distance(world.me, near) > GIVE_DIST) continue;
                JsonNode inv = world.me.path("items");
                for (int num = 0; num < inv.size(); num++) {
                    if (give(G, inv.path(num))) gifts.add(new int[] {num, inv.path(num).path("q").asInt(1)});
                }
                long have = world.me.path("gold").asLong();
                // Gold only above twice the reserve: not a `send` for each small chest.
                gold = have > 2 * FIGHTER_GOLD ? have - FIGHTER_GOLD : 0;
            }
            int n = 0;
            for (int[] g : gifts) { // the sends happen outside the World lock
                Actions.GameResponse r = f.items().sendItem(merchantName, g[0], g[1]);
                if (r != null && !r.failed()) n++;
            }
            if (gold > 0) f.items().sendGold(merchantName, gold);
            if (n > 0 || gold > 0) System.out.printf("%s: gave %d item(s) and %d gold to %s%n", f.m().name(), n, gold, merchantName);
        }
    }
    // endregion fighter

    // region merchant
    /** Does this fighter have something to give? */
    static boolean hasLoot(Crew f) {
        World w = f.m().world();
        synchronized (w) {
            for (JsonNode it : w.me.path("items")) if (give(G, it)) return true;
            return false;
        }
    }

    /** The merchant: wait for loot, collect it, sell it, bank the gold. */
    static boolean merchantTrip() throws InterruptedException {
        World world = merchant.m().world();
        String name = merchant.m().name();
        List<Crew> fighters = crew.subList(0, crew.size() - 1);
        // 1. Wait until a fighter has something to give.
        while (!stop && fighters.stream().noneMatch(PartyMerchant::hasLoot)) Thread.sleep(500);
        // 2. Go to each fighter with loot, and wait (10 s at most) until it gave all.
        for (Crew f : fighters) {
            if (stop || !hasLoot(f)) continue;
            double fx, fy;
            World fw = f.m().world();
            synchronized (fw) {
                fx = fw.me.path("x").asDouble();
                fy = fw.me.path("y").asDouble();
            }
            System.out.printf("%s: walk to %s at %d,%d%n", name, f.m().name(), Math.round(fx), Math.round(fy));
            merchant.travel().walkTo(fx, fy);
            for (int waited = 0; hasLoot(f) && waited < 10000; waited += 200) Thread.sleep(200);
        }
        // 3. Sell the loot in the town. Keep the jewelry: three of a kind compound.
        Items.Npc shop = merchant.items().npcSelling("hpot0");
        if (shop == null) throw new IllegalStateException("no shop on this map");
        System.out.printf("%s: walk to %s at %d,%d%n", name, shop.id(), Math.round(shop.x()), Math.round(shop.y()));
        if (!merchant.travel().walkTo(shop.x(), shop.y())) return false;
        int sold = 0;
        long gold = 0;
        int size;
        synchronized (world) { size = world.me.path("items").size(); }
        for (int num = 0; num < size; num++) {
            JsonNode it;
            synchronized (world) { it = world.me.path("items").path(num).deepCopy(); }
            if (!Items.isLoot(G, it)) continue;
            Actions.GameResponse r = merchant.items().sell(num, it.path("q").asInt(1));
            if (r != null && !r.failed()) {
                sold++;
                gold += r.raw().path("gold").asLong();
            }
        }
        System.out.printf("%s: sold %d item(s): +%d gold%n", name, sold, gold);
        // 4. The bank: the door is north of the town. Deposit, then go back out.
        if (!merchant.travel().goToMap("bank")) return false;
        long amount;
        synchronized (world) { amount = Math.max(0, world.me.path("gold").asLong() - MERCHANT_GOLD); }
        Actions.GameResponse r = merchant.items().deposit(amount);
        System.out.printf("%s: in the bank: deposited %d gold%n", name, r != null && !r.failed() ? r.raw().path("gold").asLong() : 0);
        if (!merchant.travel().goToMap("main")) return false;
        synchronized (world) { System.out.printf("%s: back on main at %s%n", name, xy(world.me)); }
        return true;
    }
    // endregion merchant

    static String xy(JsonNode e) {
        return Math.round(e.path("x").asDouble()) + "," + Math.round(e.path("y").asDouble());
    }
}
