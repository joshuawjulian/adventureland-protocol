// GearUp.java: upgrades a coat to +3 and compounds rings in groups of three, with the stop rule
// of the game guide. It farms first until it has a chest (gold and rings).
// Uses albot. Java 21; Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger mvn -q compile exec:java -Dexec.mainClass=GearUp
import albot.Actions;
import albot.Bot;
import albot.Farmer;
import albot.GData;
import albot.Items;
import albot.Travel;
import albot.World;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public class GearUp {
    static final long TICK_MS = 100;

    // region rules
    // The stop rule (the game guide, "A progression plan"): take a piece to +3 with no spare copy.
    // Above +3 the chance falls (70 % for +4), so stop and use spares ("Step 2"). Also stop when
    // the server's chance, with grace, is below 90 %: then a failure is too likely for an item
    // that we wear.
    static final String ITEM = "coat"; // 6,000 gold at Gabriel (`basics`)
    static final int TARGET_LEVEL = 3;
    static final double MIN_CHANCE = 0.9;
    // Jewelry: compound groups of three while the chance is at least 90 %. For most jewelry that
    // is +0 -> +1 only (99 %); +2 is 75 %.
    // endregion rules

    static World world;
    static GData G;
    static Travel travel;
    static Items items;

    public static void main(String[] args) throws Exception {
        java.util.Locale.setDefault(java.util.Locale.ROOT); // "0.99", never "0,99"
        Bot bot = Bot.connect();
        world = bot.world;
        G = bot.G;
        synchronized (world) {
            System.out.printf("in game as %s (%s, level %d) on %s at %s%n", world.me.path("id").asText(),
                    world.me.path("ctype").asText(), world.me.path("level").asInt(), world.me.path("map").asText(), xy(world.me));
        }
        travel = new Travel(world, bot.act);
        items = new Items(world, bot.act, bot.budget);
        Farmer farmer = new Farmer(world, bot.act, bot.cooldowns, travel);

        // 1. Farm until one chest opened: the first chest brings gold and rings.
        var chests = new AtomicInteger();
        world.listen("chest_opened", r -> { if (!r.path("gone").asBoolean()) chests.incrementAndGet(); });
        while (chests.get() == 0) {
            Thread.sleep(TICK_MS);
            farmer.tick();
        }

        // 2. The item to upgrade.
        int num = items.find(ITEM);
        if (num < 0) num = buyOne(ITEM);

        // 3. Stand where both Lucas (scrolls) and Cue (upgrade, compound) are within 400 px: the
        //    middle of the two (about 140 px from each).
        Items.Npc lucas = items.npcSelling("scroll0");
        Items.Npc cue = items.npcWithRole("newupgrade");
        if (lucas == null || cue == null) throw new IllegalStateException("no scroll shop or upgrade NPC on this map");
        var spot = new Items.Npc("scrolls and newupgrade", Math.round((lucas.x() + cue.x()) / 2), Math.round((lucas.y() + cue.y()) / 2));
        goNear(spot, 20); // 20 px: near the middle, so that both stay within 400 px

        // region upgrade-loop
        while (num >= 0 && level(num) < TARGET_LEVEL) {
            int level = level(num);
            int scroll = items.find("scroll0");
            if (scroll < 0) scroll = buyOne("scroll0");
            // Ask first: the chance includes grace, which only the server knows.
            Actions.GameResponse calc = items.upgrade(num, scroll, true);
            if (calc == null || calc.failed() || !calc.response().equals("upgrade_chance")) {
                System.out.println("upgrade " + ITEM + ": " + (calc != null ? calc.response() : "no answer"));
                break;
            }
            double chance = calc.raw().path("chance").asDouble();
            if (chance < MIN_CHANCE) {
                System.out.printf("stop: the chance for +%d is %.2f%n", level + 1, chance);
                break;
            }
            Actions.GameResponse r = items.upgrade(num, scroll);
            String result = r == null ? "no answer" : r.response().equals("upgrade_success") ? "success"
                    : r.response().equals("upgrade_fail") ? "fail" : r.response();
            System.out.printf("upgrade %s +%d -> +%d: %s (chance %.2f)%n", ITEM, level, level + 1, result, chance);
            if (!result.equals("success")) break; // a fail destroys the item
            num = r.raw().path("num").asInt(num);
        }
        // endregion upgrade-loop

        // region compound-loop
        for (int[] group = findGroup(); group != null; group = findGroup()) {
            String name;
            int level;
            synchronized (world) {
                JsonNode it = world.me.path("items").path(group[0]);
                name = it.path("name").asText();
                level = it.path("level").asInt(0);
            }
            int scroll = items.find("cscroll0");
            if (scroll < 0) scroll = buyOne("cscroll0");
            Actions.GameResponse calc = items.compound(group, scroll, true);
            if (calc == null || calc.failed() || !calc.response().equals("compound_chance")
                    || calc.raw().path("chance").asDouble() < MIN_CHANCE) {
                String why = calc == null ? "no answer" : calc.raw().has("chance")
                        ? String.format("%.2f", calc.raw().path("chance").asDouble()) : calc.response();
                System.out.printf("stop: compound %s +%d: %s%n", name, level, why);
                break;
            }
            double chance = calc.raw().path("chance").asDouble();
            Actions.GameResponse r = items.compound(group, scroll);
            String result = r == null ? "no answer" : r.response().equals("compound_success") ? "success"
                    : r.response().equals("compound_fail") ? "fail" : r.response();
            System.out.printf("compound %s +%d x3 -> +%d: %s (chance %.2f)%n", name, level, level + 1, result, chance);
            if (!result.equals("success") && !result.equals("fail")) break;
        }
        // endregion compound-loop

        // 4. Wear the results.
        for (String line : items.equipBetter()) System.out.println("equip " + line);
        synchronized (world) {
            System.out.printf("gear: chest %s, ring1 %s, ring2 %s, belt %s%n", show("chest"), show("ring1"), show("ring2"), show("belt"));
        }
        bot.close();
        System.out.println("OK");
        System.exit(0);
    }

    static int level(int num) {
        synchronized (world) { return world.me.path("items").path(num).path("level").asInt(0); }
    }

    /** "coat +3", or "-" for an empty slot. Call it inside the World lock. */
    static String show(String slot) {
        JsonNode s = world.me.path("slots").path(slot);
        return s.isObject() ? s.path("name").asText() + " +" + s.path("level").asInt(0) : "-";
    }

    /** Groups of three: same name, same level, an item that compounds (G `compound`). */
    static int[] findGroup() {
        Map<String, List<Integer>> groups = new LinkedHashMap<>();
        synchronized (world) {
            JsonNode inv = world.me.path("items");
            for (int n = 0; n < inv.size(); n++) {
                JsonNode it = inv.path(n);
                if (!it.isObject() || it.hasNonNull("l")) continue;
                if (!G.raw().path("items").path(it.path("name").asText()).has("compound")) continue;
                groups.computeIfAbsent(it.path("name").asText() + " " + it.path("level").asInt(0), k -> new ArrayList<>()).add(n);
            }
        }
        for (List<Integer> nums : groups.values()) {
            if (nums.size() >= 3) return new int[] {nums.get(0), nums.get(1), nums.get(2)};
        }
        return null;
    }

    /** Walks to within `within` px of an NPC (or of a point). Says so only when it must walk. */
    static void goNear(Items.Npc npc, double within) throws InterruptedException {
        if (npc == null) throw new IllegalStateException("no such NPC on this map");
        synchronized (world) {
            world.advance();
            if (Math.hypot(world.me.path("x").asDouble() - npc.x(), world.me.path("y").asDouble() - npc.y()) <= within) return;
        }
        System.out.printf("walk to %s at %d,%d%n", npc.id(), Math.round(npc.x()), Math.round(npc.y()));
        if (!travel.walkTo(npc.x(), npc.y())) throw new IllegalStateException("could not walk to " + npc.id());
    }

    /** Buys one `name` and returns its slot number. */
    static int buyOne(String name) throws InterruptedException {
        goNear(items.npcSelling(name), Items.NPC_DIST);
        Actions.GameResponse r = items.buy(name, 1);
        if (r == null || r.failed()) throw new IllegalStateException("buy " + name + ": " + (r != null ? r.response() : "no answer"));
        System.out.printf("buy %s x1: %d gold%n", name, r.raw().path("cost").asLong());
        return r.raw().path("num").asInt();
    }

    static String xy(JsonNode e) {
        return Math.round(e.path("x").asDouble()) + "," + Math.round(e.path("y").asDouble());
    }
}
