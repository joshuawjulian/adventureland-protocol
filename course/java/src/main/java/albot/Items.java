// Items.java: the inventory and the NPC services: buy, sell, equip, give items and gold to
// another character, the bank, upgrade and compound. Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
//
// `me.items` is the inventory: an array of 42 slots (G: isize), each an item {name, q?, level?,
// ...} or null. `me.slots` is the equipment: slot name -> item. `me.esize` is the number of empty
// inventory slots. All three come in `start` and `player` (node/server.js:855-1001).
//
// Threads: the log of answers is behind the lock of this object (the dispatcher writes it, our
// loop reads it). Reads of `me` hold the World lock. No send happens inside a lock.
package albot;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Predicate;

public final class Items {
    // region rules
    /** An NPC sells, buys, upgrades and compounds within 400 px (B.sell_dist, node/server.js:220). Stand a little nearer: our position is an estimate. */
    public static final double NPC_DIST = 350;

    /** The equipment slots for each item type (G.items[name].type). Rings and earrings have two slots. */
    public static final Map<String, List<String>> SLOTS_FOR_TYPE = Map.ofEntries(
            Map.entry("weapon", List.of("mainhand")), Map.entry("shield", List.of("offhand")),
            Map.entry("source", List.of("offhand")), Map.entry("quiver", List.of("offhand")),
            Map.entry("misc_offhand", List.of("offhand")), Map.entry("helmet", List.of("helmet")),
            Map.entry("chest", List.of("chest")), Map.entry("pants", List.of("pants")),
            Map.entry("shoes", List.of("shoes")), Map.entry("gloves", List.of("gloves")),
            Map.entry("belt", List.of("belt")), Map.entry("amulet", List.of("amulet")),
            Map.entry("orb", List.of("orb")), Map.entry("cape", List.of("cape")),
            Map.entry("ring", List.of("ring1", "ring2")), Map.entry("earring", List.of("earring1", "earring2")));

    /**
     * The item types that a bot keeps and never sells (the loot rules of the game guide, "A
     * merchant in practice"): potions, scrolls and offerings, and jewelry, which you compound in
     * groups of three.
     */
    public static final Set<String> KEEP_TYPES = Set.of("pot", "uscroll", "cscroll", "pscroll", "offering",
            "ring", "earring", "amulet", "belt", "orb");

    /** Is this inventory item loot to sell? Not a kept type, not locked (`l`), not an upgrade in progress ("placeholder"). */
    public static boolean isLoot(GData G, JsonNode item) {
        if (item == null || !item.isObject() || item.path("name").asText().equals("placeholder") || item.hasNonNull("l")) return false;
        GData.ItemDef def = G.items().get(item.path("name").asText());
        return def != null && !KEEP_TYPES.contains(def.type());
    }
    // endregion rules

    /** An NPC of the map: its id and position. */
    public record Npc(String id, double x, double y) {}

    private record Logged(long seq, Actions.GameResponse r) {}

    private final World world;
    private final Actions act;
    private final Budget budget;
    private final GData G;
    private final ArrayDeque<Logged> log = new ArrayDeque<>(); // the last 50 game_response events; guarded by `this`
    private long seq = 0; // guarded by `this`

    public Items(World world, Actions act, Budget budget) {
        this.world = world;
        this.act = act;
        this.budget = budget;
        this.G = world.G;
        // The results of upgrade and compound come later, as hitchhikers inside a `player` update.
        // world.listen gets them too (World.onPlayer dispatches them), so keep the last 50
        // game_response events and search them.
        world.listen("game_response", d -> {
            synchronized (this) {
                log.add(new Logged(++seq, Actions.normalize(d)));
                if (log.size() > 50) log.poll();
            }
        });
    }

    // region find
    /** The slot number of the first item called `name` (and of `level`, if not null), or -1. */
    public int find(String name, Integer level) {
        synchronized (world) {
            JsonNode items = world.me.path("items");
            for (int num = 0; num < items.size(); num++) {
                JsonNode it = items.path(num);
                if (it.isObject() && it.path("name").asText().equals(name)
                        && (level == null || it.path("level").asInt(0) == level)) return num;
            }
            return -1;
        }
    }

    /** find with any level. */
    public int find(String name) {
        return find(name, null);
    }

    /** How many of `name` we carry (stacks count their `q`). */
    public int count(String name) {
        synchronized (world) {
            int n = 0;
            for (JsonNode it : world.me.path("items")) {
                if (it.isObject() && it.path("name").asText().equals(name)) n += it.path("q").asInt(1);
            }
            return n;
        }
    }

    /** The number of empty inventory slots. */
    public int freeSlots() {
        synchronized (world) {
            JsonNode me = world.me;
            if (me.path("esize").isNumber()) return me.path("esize").asInt();
            int used = 0;
            for (JsonNode it : me.path("items")) if (it.isObject()) used++;
            return me.path("isize").asInt(42) - used;
        }
    }

    /** The NPC on our map that sells `item`, or null. NPCs with an `items` list are shops (G.npcs[id].items). */
    public Npc npcSelling(String item) {
        return npc(def -> {
            for (JsonNode i : def.path("items")) if (i.asText().equals(item)) return true;
            return false;
        });
    }

    /**
     * The NPC on our map with this role, for example "newupgrade" (Cue: upgrade and compound) or
     * "merchant" (a shop: it buys any item).
     */
    public Npc npcWithRole(String role) {
        return npc(def -> def.path("role").asText().equals(role));
    }

    private Npc npc(Predicate<JsonNode> test) {
        String map;
        synchronized (world) { map = world.me.path("map").asText(); }
        for (JsonNode n : G.raw().path("maps").path(map).path("npcs")) {
            JsonNode pos = n.has("position") ? n.path("position") : n.path("positions").path(0);
            JsonNode def = G.raw().path("npcs").path(n.path("id").asText());
            if (pos.isArray() && def.isObject() && test.test(def)) {
                return new Npc(n.path("id").asText(), pos.path(0).asDouble(), pos.path(1).asDouble());
            }
        }
        return null;
    }
    // endregion find

    // region shop
    /**
     * Buys from an NPC within 400 px that sells the item. The answer: `buy_success` {cost, num,
     * name, q}, or a failure: "distance" (too far), "buy_cost" (not enough gold), "buy_cant_space"
     * (node/server.js:8409-8461).
     */
    public Actions.GameResponse buy(String name, int quantity) throws InterruptedException {
        return act.request("buy", Map.of("name", name, "quantity", quantity));
    }

    /**
     * Sells to any shop NPC within 400 px for 60 % of G.items[name].g (1 gold for a gift item).
     * The answer: `gold_received` {gold} (node/server.js:8046-8096).
     */
    public Actions.GameResponse sell(int num, int quantity) throws InterruptedException {
        return act.request("sell", Map.of("num", num, "quantity", quantity));
    }
    // endregion shop

    // region equip
    /**
     * Puts the item of slot `num` on. Without `slot` (null), the server chooses one from the item
     * type. The old item goes back to the inventory. The answer is {response: "data", slot} on
     * success (node/server.js:7643-7915).
     */
    public Actions.GameResponse equip(int num, String slot) throws InterruptedException {
        return act.request("equip", slot != null ? Map.of("num", num, "slot", slot) : Map.of("num", num));
    }

    /** equip into the slot that the server chooses. */
    public Actions.GameResponse equip(int num) throws InterruptedException {
        return equip(num, null);
    }

    public Actions.GameResponse unequip(String slot) throws InterruptedException {
        return act.request("unequip", Map.of("slot", slot));
    }

    /**
     * Equips each inventory item that is better than what we wear: the slot is empty, or it holds
     * the same item at a lower level. A simple rule; the game guide ("Gear is more important than
     * level") compares stats. Returns "name: slot" for each item that went on.
     */
    public List<String> equipBetter() throws InterruptedException {
        List<String> done = new ArrayList<>();
        int size;
        synchronized (world) { size = world.me.path("items").size(); }
        for (int num = 0; num < size; num++) {
            String name = null, slot = null;
            synchronized (world) { // choose inside the lock, send outside it
                JsonNode it = world.me.path("items").path(num);
                GData.ItemDef def = it.isObject() ? G.items().get(it.path("name").asText()) : null;
                List<String> slots = def == null ? null : SLOTS_FOR_TYPE.get(def.type());
                if (slots == null || it.path("name").asText().equals("placeholder")) continue;
                JsonNode worn = world.me.path("slots");
                for (String s : slots) if (!worn.path(s).isObject()) { slot = s; break; }
                if (slot == null) {
                    for (String s : slots) {
                        if (worn.path(s).path("name").asText().equals(it.path("name").asText())
                                && worn.path(s).path("level").asInt(0) < it.path("level").asInt(0)) { slot = s; break; }
                    }
                }
                name = it.path("name").asText();
            }
            if (slot == null) continue;
            Actions.GameResponse r = equip(num, slot);
            if (r != null && !r.failed()) done.add(name + ": " + slot); // "cant_equip": not for our class
        }
        return done;
    }
    // endregion equip

    // region send
    /**
     * Gives items to another character on our map within 400 px. The answer: `item_sent`, or
     * "distance", "send_no_space" (node/server.js:8463-8560).
     */
    public Actions.GameResponse sendItem(String name, int num, int quantity) throws InterruptedException {
        return act.request("send", Map.of("name", name, "num", num, "q", quantity));
    }

    /**
     * Gives gold. Between characters of one account the receiver gets all of it; to another
     * account, 2.5 % less (node/server.js:8590-8600).
     */
    public Actions.GameResponse sendGold(String name, long gold) throws InterruptedException {
        return act.request("send", Map.of("name", name, "gold", gold));
    }
    // endregion send

    // region bank
    /**
     * Gold into and out of the bank. Only inside the bank (a map with `mount`, which
     * Travel.goToMap("bank") reaches); elsewhere: "bank_unavailable". The first answer has place
     * "bank" and the `gold` moved (node/server.js:9257-9282).
     */
    public Actions.GameResponse deposit(long gold) throws InterruptedException {
        return act.request("bank", Map.of("operation", "deposit", "amount", gold));
    }

    public Actions.GameResponse withdraw(long gold) throws InterruptedException {
        return act.request("bank", Map.of("operation", "withdraw", "amount", gold));
    }
    // endregion bank

    // region upgrade
    /**
     * Upgrades the item in slot `itemNum` with the scroll in `scrollNum`, at the upgrade NPC
     * (within 400 px). `clevel` must be the item's level now, or the server says
     * "upgrade_mismatch" (node/server.js:7166-7168).
     *   calculate true: the answer is `upgrade_chance` {chance}; nothing is used.
     *   calculate false: the scroll is used, the slot holds a "placeholder", and the result comes
     *   later as a hitchhiker: `upgrade_success` or `upgrade_fail` {level, num}
     *   (node/server.js:14920-14945). On a fail the item is gone.
     * A failure before the roll is a bare string ("upgrade_no_scroll") or an object with place
     * "upgrade" ("distance"). null: no answer in time.
     */
    public Actions.GameResponse upgrade(int itemNum, int scrollNum, boolean calculate) throws InterruptedException {
        int level;
        synchronized (world) { level = world.me.path("items").path(itemNum).path("level").asInt(0); }
        Map<String, Object> payload = new HashMap<>(Map.of("item_num", itemNum, "scroll_num", scrollNum, "clevel", level));
        if (calculate) payload.put("calculate", true);
        // 30 s: the roll of +N takes 0.5 x N x sqrt(N) s, about 9 s at +7.
        return roll("upgrade", payload, calculate ? 2000 : 30000);
    }

    /** upgrade with calculate = false. */
    public Actions.GameResponse upgrade(int itemNum, int scrollNum) throws InterruptedException {
        return upgrade(itemNum, scrollNum, false);
    }

    /**
     * Combines three identical items (same name and level) with a compound scroll. The same
     * answers as upgrade, with "compound" in place of "upgrade". The roll takes 10 s
     * (node/server.js:7037). On a success the item is in nums[0], one level higher; the other two
     * slots are empty.
     */
    public Actions.GameResponse compound(int[] nums, int scrollNum, boolean calculate) throws InterruptedException {
        int level;
        synchronized (world) { level = world.me.path("items").path(nums[0]).path("level").asInt(0); }
        Map<String, Object> payload = new HashMap<>(Map.of("items", nums, "scroll_num", scrollNum, "clevel", level));
        if (calculate) payload.put("calculate", true);
        return roll("compound", payload, calculate ? 2000 : 30000);
    }

    /** compound with calculate = false. */
    public Actions.GameResponse compound(int[] nums, int scrollNum) throws InterruptedException {
        return compound(nums, scrollNum, false);
    }

    /**
     * Sends the event, then waits for the first game_response about it: an object with this
     * `place`, or a response that starts with "<event>_" (the bare-string failures and the late
     * hitchhiker results).
     */
    private Actions.GameResponse roll(String event, Object payload, long timeoutMs) throws InterruptedException {
        long since;
        synchronized (this) { since = seq; } // only answers that come after the emit
        budget.emit(event, payload);
        for (long end = World.nowMs() + timeoutMs; World.nowMs() < end; Thread.sleep(50)) {
            synchronized (this) {
                for (Logged l : log) {
                    if (l.seq() > since && (event.equals(l.r().place()) || l.r().response().startsWith(event + "_"))) return l.r();
                }
            }
        }
        return null;
    }
    // endregion upgrade
}
