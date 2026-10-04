// Items.cs: the inventory and the NPC services: buy, sell, equip, give items
// and gold to another character, the bank, upgrade and compound.
//
// Me["items"] is the inventory: an array of 42 slots (G: isize), each an item
// {name, q?, level?, ...} or null. Me["slots"] is the equipment: slot name ->
// item. Me["esize"] is the number of empty inventory slots. All three come in
// `start` and `player` (node/server.js:855-1001).
//
// Threads: the handler below runs on the dispatcher thread. The log of
// game_response events is behind its own lock (_logLock). World state is read
// with world.Gate locked. No lock is held while we send.
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Albot;

/// <summary>An NPC on our map: its G id and its position.</summary>
public sealed record Npc(string Id, double X, double Y);

public sealed class Items
{
    // region rules
    /// <summary>An NPC sells, buys, upgrades and compounds within 400 px (B.sell_dist,
    /// node/server.js:220). Stand a little nearer: our position is an estimate.</summary>
    public const double NpcDist = 350;

    /// <summary>The equipment slots for each item type (G.items[name].type). Rings and
    /// earrings have two slots.</summary>
    public static readonly IReadOnlyDictionary<string, string[]> SlotsForType = new Dictionary<string, string[]>
    {
        ["weapon"] = ["mainhand"], ["shield"] = ["offhand"], ["source"] = ["offhand"], ["quiver"] = ["offhand"],
        ["misc_offhand"] = ["offhand"], ["helmet"] = ["helmet"], ["chest"] = ["chest"], ["pants"] = ["pants"],
        ["shoes"] = ["shoes"], ["gloves"] = ["gloves"], ["belt"] = ["belt"], ["amulet"] = ["amulet"], ["orb"] = ["orb"],
        ["cape"] = ["cape"], ["ring"] = ["ring1", "ring2"], ["earring"] = ["earring1", "earring2"],
    };

    /// <summary>The item types that a bot keeps and never sells (the loot rules of the
    /// game guide, "A merchant in practice"): potions, scrolls and offerings, and
    /// jewelry, which you compound in groups of three.</summary>
    public static readonly string[] KeepTypes = ["pot", "uscroll", "cscroll", "pscroll", "offering", "ring", "earring", "amulet", "belt", "orb"];

    /// <summary>Is this inventory item loot to sell? Not a kept type, not locked (`l`),
    /// not an upgrade in progress ("placeholder").</summary>
    public static bool IsLoot(GData G, JsonNode? item)
    {
        if (item is null || item.Str("name") is not string name || name == "placeholder" || item["l"] is not null) return false;
        return G.Items.TryGetValue(name, out var def) && !KeepTypes.Contains(def.Type);
    }
    // endregion rules

    private readonly World _world;
    private readonly Actions _act;
    private readonly Budget _budget;
    private readonly GData _g;
    // The last game_response events, each with a number that grows by one.
    private readonly List<(long Seq, GameResponse R)> _log = [];
    private readonly object _logLock = new();
    private long _seq;

    public Items(World world, Actions act, Budget budget)
    {
        _world = world;
        _act = act;
        _budget = budget;
        _g = world.G;
        // The results of upgrade and compound come later, as hitchhikers inside a
        // `player` update. world.Listen gets them too (World.OnPlayer dispatches
        // them), so keep the last 50 game_response events and search them.
        world.Listen("game_response", d =>
        {
            // Actions.Normalize reads a JsonElement: make one from the node.
            var r = Actions.Normalize(JsonSerializer.SerializeToElement(d));
            lock (_logLock)
            {
                _log.Add((++_seq, r));
                if (_log.Count > 50) _log.RemoveAt(0);
            }
        });
    }

    // region find
    /// <summary>The slot number of the first item called name (and of level, if
    /// given), or -1.</summary>
    public int Find(string name, int? level = null)
    {
        lock (_world.Gate)
        {
            var items = _world.Me["items"] as JsonArray ?? [];
            for (var n = 0; n < items.Count; n++)
                if (items[n].Str("name") == name && (level is null || items[n].Num("level") == level)) return n;
            return -1;
        }
    }

    /// <summary>How many of name we carry (stacks count their q).</summary>
    public int Count(string name)
    {
        lock (_world.Gate)
        {
            var n = 0;
            foreach (var it in _world.Me["items"] as JsonArray ?? [])
                if (it.Str("name") == name) n += it!["q"] is null ? 1 : (int)it.Num("q");
            return n;
        }
    }

    /// <summary>The number of empty inventory slots.</summary>
    public int FreeSlots()
    {
        lock (_world.Gate)
        {
            var me = _world.Me;
            if (me["esize"] is not null) return (int)me.Num("esize");
            var items = me["items"] as JsonArray ?? [];
            return (me["isize"] is null ? 42 : (int)me.Num("isize")) - items.Count(i => i is not null);
        }
    }

    /// <summary>The NPC on our map that sells item, or null. NPCs with an `items`
    /// list are shops (G.npcs[id].items).</summary>
    public Npc? NpcSelling(string item) =>
        FindNpc(npc => (npc["items"] as JsonArray ?? []).Any(i => i is JsonValue v && v.GetValueKind() == JsonValueKind.String && v.GetValue<string>() == item));

    /// <summary>The NPC on our map with this role, for example "newupgrade" (Cue:
    /// upgrade and compound) or "merchant" (a shop: it buys any item).</summary>
    public Npc? NpcWithRole(string role) => FindNpc(npc => npc.Str("role") == role);

    private Npc? FindNpc(Func<JsonNode, bool> test)
    {
        string? map;
        lock (_world.Gate) map = _world.Me.Str("map");
        foreach (var n in _g.Raw["maps"]?[map ?? ""]?["npcs"] as JsonArray ?? [])
        {
            var pos = n?["position"] as JsonArray ?? n?["positions"]?[0] as JsonArray;
            if (pos is null || n.Str("id") is not string id || _g.Raw["npcs"]?[id] is not JsonNode npc) continue;
            if (test(npc)) return new Npc(id, pos[0]!.GetValue<double>(), pos[1]!.GetValue<double>());
        }
        return null;
    }
    // endregion find

    // region shop
    /// <summary>Buys from an NPC within 400 px that sells the item. The answer:
    /// `buy_success` {cost, num, name, q}, or a failure: "distance" (too far),
    /// "buy_cost" (not enough gold), "buy_cant_space" (node/server.js:8409-8461).</summary>
    public Task<GameResponse?> BuyAsync(string name, int quantity) =>
        _act.RequestAsync("buy", new { name, quantity });

    /// <summary>Sells to any shop NPC within 400 px for 60 % of G.items[name].g (1 gold
    /// for a gift item). The answer: `gold_received` {gold} (node/server.js:8046-8096).</summary>
    public Task<GameResponse?> SellAsync(int num, int quantity) =>
        _act.RequestAsync("sell", new { num, quantity });
    // endregion shop

    // region equip
    /// <summary>Puts the item of slot num on. Without slot, the server chooses one from
    /// the item type. The old item goes back to the inventory. The answer is
    /// {response: "data", slot} on success (node/server.js:7643-7915).</summary>
    public Task<GameResponse?> EquipAsync(int num, string? slot = null) =>
        slot is null ? _act.RequestAsync("equip", new { num }) : _act.RequestAsync("equip", new { num, slot });

    public Task<GameResponse?> UnequipAsync(string slot) => _act.RequestAsync("unequip", new { slot });

    /// <summary>
    /// Equips each inventory item that is better than what we wear: the slot is
    /// empty, or it holds the same item at a lower level. A simple rule; the game
    /// guide ("Gear is more important than level") compares stats. Returns
    /// "name: slot" for each item that went on.
    /// </summary>
    public async Task<List<string>> EquipBetterAsync()
    {
        var done = new List<string>();
        for (var num = 0; ; num++)
        {
            string? slot = null, name = null;
            lock (_world.Gate)
            {
                var items = _world.Me["items"] as JsonArray ?? [];
                if (num >= items.Count) break;
                var it = items[num];
                name = it.Str("name");
                if (name is null || name == "placeholder" || !_g.Items.TryGetValue(name, out var def)
                    || !SlotsForType.TryGetValue(def.Type, out var slots)) continue;
                var worn = _world.Me["slots"] as JsonObject ?? [];
                slot = slots.FirstOrDefault(s => worn[s] is null)
                    ?? slots.FirstOrDefault(s => worn[s].Str("name") == name && worn[s].Num("level") < it.Num("level"));
            }
            if (slot is null) continue;
            var r = await EquipAsync(num, slot);
            if (r is { Failed: false }) done.Add($"{name}: {slot}"); // "cant_equip": not for our class
        }
        return done;
    }
    // endregion equip

    // region send
    /// <summary>Gives items to another character on our map within 400 px. The answer:
    /// `item_sent`, or "distance", "send_no_space" (node/server.js:8463-8560).</summary>
    public Task<GameResponse?> SendItemAsync(string name, int num, int quantity) =>
        _act.RequestAsync("send", new { name, num, q = quantity });

    /// <summary>Gives gold. Between characters of one account the receiver gets all of
    /// it; to another account, 2.5 % less (node/server.js:8590-8600).</summary>
    public Task<GameResponse?> SendGoldAsync(string name, double gold) =>
        _act.RequestAsync("send", new { name, gold });
    // endregion send

    // region bank
    /// <summary>Gold into the bank. Only inside the bank (a map with `mount`, which
    /// Travel.GoToMapAsync("bank") reaches); elsewhere: "bank_unavailable". The first
    /// answer has place "bank" and the gold moved (node/server.js:9257-9282).</summary>
    public Task<GameResponse?> DepositAsync(double gold) =>
        _act.RequestAsync("bank", new { operation = "deposit", amount = gold });

    public Task<GameResponse?> WithdrawAsync(double gold) =>
        _act.RequestAsync("bank", new { operation = "withdraw", amount = gold });
    // endregion bank

    // region upgrade
    /// <summary>
    /// Upgrades the item in slot itemNum with the scroll in scrollNum, at the upgrade
    /// NPC (within 400 px). clevel must be the item's level now, or the server says
    /// "upgrade_mismatch" (node/server.js:7166-7168).
    ///   calculate: true -> the answer is `upgrade_chance` {chance}; nothing is used.
    ///   calculate: false -> the scroll is used, the slot holds a "placeholder", and
    ///     the result comes later as a hitchhiker: `upgrade_success` or `upgrade_fail`
    ///     {level, num} (node/server.js:14920-14945). On a fail the item is gone.
    /// A failure before the roll is a bare string ("upgrade_no_scroll") or an object
    /// with place "upgrade" ("distance"). null: no answer in time.
    /// </summary>
    public Task<GameResponse?> UpgradeAsync(int itemNum, int scrollNum, bool calculate = false)
    {
        double clevel;
        lock (_world.Gate) clevel = (_world.Me["items"] as JsonArray)?.ElementAtOrDefault(itemNum).Num("level") ?? 0;
        object payload = calculate
            ? new { item_num = itemNum, scroll_num = scrollNum, clevel, calculate = true }
            : new { item_num = itemNum, scroll_num = scrollNum, clevel };
        // 30 s: the roll of +N takes 0.5 x N x sqrt(N) s, about 9 s at +7.
        return RollAsync("upgrade", payload, calculate ? 2000 : 30000);
    }

    /// <summary>
    /// Combines three identical items (same name and level) with a compound scroll.
    /// The same answers as UpgradeAsync, with "compound" in place of "upgrade". The
    /// roll takes 10 s (node/server.js:7037). On a success the item is in nums[0],
    /// one level higher; the other two slots are empty.
    /// </summary>
    public Task<GameResponse?> CompoundAsync(int[] nums, int scrollNum, bool calculate = false)
    {
        double clevel;
        lock (_world.Gate) clevel = (_world.Me["items"] as JsonArray)?.ElementAtOrDefault(nums[0]).Num("level") ?? 0;
        object payload = calculate
            ? new { items = nums, scroll_num = scrollNum, clevel, calculate = true }
            : new { items = nums, scroll_num = scrollNum, clevel };
        return RollAsync("compound", payload, calculate ? 2000 : 30000);
    }

    // Sends the event, then waits for the first game_response about it: an object
    // with this place, or a response that starts with "<event>_" (the bare-string
    // failures and the late hitchhiker results).
    private async Task<GameResponse?> RollAsync(string evt, object payload, int timeoutMs)
    {
        long since;
        lock (_logLock) since = _seq; // only answers that come after the emit
        await _budget.EmitAsync(evt, payload);
        var end = Environment.TickCount64 + timeoutMs;
        while (Environment.TickCount64 < end)
        {
            lock (_logLock)
            {
                foreach (var (seq, r) in _log)
                    if (seq > since && (r.Place == evt || r.Response.StartsWith(evt + "_"))) return r;
            }
            await Task.Delay(50);
        }
        return null;
    }
    // endregion upgrade
}
