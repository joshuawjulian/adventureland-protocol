// Actions.cs: the things that our character does: move, attack, heal, open
// chests, respawn. Every emit goes through the Budget. A method that waits for
// a reply registers the wait BEFORE the emit, so that a fast reply cannot
// arrive before the wait exists.
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Albot;

/// <summary>
/// game_response in one shape. The server sends an object {response, place,
/// failed, ...} or a bare string. Data has the whole object, for the fields of
/// one code (ms, id, ...).
/// </summary>
public sealed record GameResponse(string Response, string? Place, bool Failed, bool Success, JsonObject Data)
{
    /// <summary>The `ms` field (cooldown, not_ready, cant_respawn), or 0.</summary>
    public double Ms => Data.Num("ms");
}

public sealed class Actions
{
    private readonly AlSocket _sock;
    private readonly World _world;
    private readonly Cooldowns _cooldowns;
    private readonly Budget _budget;
    private long? _diedAt; // ms (Environment.TickCount64); guarded by world.Gate

    // B.rip_time: the wait between death and respawn (node/server.js:224).
    private const int RipTimeMs = 12000;

    public Actions(AlSocket sock, World world, Cooldowns cooldowns, Budget budget)
    {
        _sock = sock;
        _world = world;
        _cooldowns = cooldowns;
        _budget = budget;
        // Remember when we died: `rip` becomes true in `start` or `player`.
        world.Listen("start", NoteDeath);
        world.Listen("player", NoteDeath);
    }

    private void NoteDeath(JsonNode? data)
    {
        if (data is not JsonObject || data["rip"] is null) return; // no news about rip
        if (!data.Bool("rip")) _diedAt = null;
        else _diedAt ??= Environment.TickCount64;
    }

    // region normalize
    /// <summary>game_response as one shape: a string gets failed = success = false;
    /// an object gets false for a missing failed or success.</summary>
    public static GameResponse Normalize(JsonElement data)
    {
        if (data.ValueKind == JsonValueKind.String)
            return new GameResponse(data.GetString()!, null, false, false, new JsonObject { ["response"] = data.GetString() });
        var obj = data.ValueKind == JsonValueKind.Object ? JsonNode.Parse(data.GetRawText())!.AsObject() : [];
        return new GameResponse(obj.Str("response") ?? "", obj.Str("place"), obj.Bool("failed"), obj.Bool("success"), obj);
    }

    /// <summary>A WaitForAsync predicate: an object game_response with this place.</summary>
    public static Func<JsonElement, bool> ResponseFor(string place) => d =>
        d.ValueKind == JsonValueKind.Object && d.TryGetProperty("place", out var p)
        && p.ValueKind == JsonValueKind.String && p.GetString() == place;
    // endregion normalize

    // region request

    /// <summary>
    /// Sends evt and waits for the game_response with place (default: evt).
    /// null when no reply comes in timeoutMs. 2 s: a reply takes one round trip;
    /// some failures send no game_response at all.
    /// </summary>
    public async Task<GameResponse?> RequestAsync(string evt, object? payload, string? place = null, int timeoutMs = 2000)
    {
        var reply = _sock.WaitForAsync("game_response", ResponseFor(place ?? evt), TimeSpan.FromMilliseconds(timeoutMs));
        // If the emit throws (the socket closed), we never await `reply`. That is
        // safe: AlSocket marks the failure of each wait as observed.
        await _budget.EmitAsync(evt, payload);
        try { return Normalize(await reply); }
        catch (TimeoutException) { return null; }
    }
    // endregion request

    // region move-to
    /// <summary>
    /// Starts a straight walk to (x, y). The payload has our position now, the target,
    /// and `m`, the map counter: with a wrong m, the server ignores the move without a
    /// reply (node/server.js:11183-11271). No wait for the walk.
    /// </summary>
    public Task MoveAsync(double x, double y)
    {
        object payload;
        lock (_world.Gate)
        {
            _world.Advance();
            var me = _world.Me;
            payload = new { x = me.Num("x"), y = me.Num("y"), going_x = x, going_y = y, m = me.Num("m") };
            // The server does the same: we walk from now on.
            me["going_x"] = x;
            me["going_y"] = y;
            me["moving"] = true;
        }
        return _budget.EmitAsync("move", payload);
    }

    /// <summary>
    /// Walks in a straight line to (x, y) and waits for the walk to end. True if we
    /// arrived. A wall on the line sends us to jail: use Travel.WalkToAsync (Part 3) then.
    /// </summary>
    public async Task<bool> MoveToAsync(double x, double y)
    {
        double seconds;
        lock (_world.Gate)
        {
            _world.Advance();
            var me = _world.Me;
            double dx = x - me.Num("x"), dy = y - me.Num("y");
            seconds = Math.Sqrt(dx * dx + dy * dy) / Math.Max(me.Num("speed"), 1); // speed: px per second
        }
        await MoveAsync(x, y);
        // + 250 ms: room for the network delay.
        await Task.Delay(TimeSpan.FromSeconds(seconds) + TimeSpan.FromMilliseconds(250));
        lock (_world.Gate)
        {
            _world.Advance();
            var me = _world.Me;
            // Arrived: within 1 px, and still on the way to (x, y). A `correction`
            // or a jail sends us somewhere else: then the walk failed.
            double ex = me.Num("x") - x, ey = me.Num("y") - y;
            return Math.Sqrt(ex * ex + ey * ey) < 1 && me.Num("going_x") == x && me.Num("going_y") == y;
        }
    }
    // endregion move-to

    // region attack
    /// <summary>
    /// Attacks a monster (or player) by id. The reply: success is response "data" with
    /// the projectile (pid, eta) and NO success key; a failure has failed: true
    /// (too_far, cooldown, ...). null if no reply came: a target that is gone gets
    /// `disappear` with reason "not_there" instead.
    /// </summary>
    public Task<GameResponse?> AttackAsync(string id) => RequestAsync("attack", new { id });
    // endregion attack

    // region heal
    /// <summary>
    /// Restores stat ("hp" or "mp"). With a potion that gives stat in the inventory,
    /// drink it (`equip` with consume: true). Else use the free regeneration
    /// (`use` with item "hp" or "mp"). Both share the potion timer: false when it is not ready.
    /// </summary>
    public async Task<bool> HealAsync(string stat)
    {
        if (!_cooldowns.Ready("potion")) return false;
        var num = FindPotion(stat);
        var r = num >= 0
            ? await RequestAsync("equip", new { num, consume = true })
            : await RequestAsync("use", new { item = stat });
        return r is { Failed: false };
    }

    // The first inventory slot with a potion that gives stat, or -1.
    private int FindPotion(string stat)
    {
        lock (_world.Gate)
        {
            var items = _world.Me["items"] as JsonArray ?? [];
            for (var num = 0; num < items.Count; num++)
            {
                if (items[num].Str("name") is string name && _world.G.Items.TryGetValue(name, out var def)
                    && (def.Gives ?? []).Any(g => g[0].GetString() == stat)) // [stat, amount]
                    return num;
            }
            return -1;
        }
    }
    // endregion heal

    // region open-chests
    /// <summary>
    /// Opens one chest. The reply is `chest_opened` {id, gold, items} or {id, gone: true}.
    /// null if no reply: for example, no space for the items (game_response loot_no_space).
    /// </summary>
    public async Task<JsonObject?> OpenChestAsync(string id)
    {
        var opened = _sock.WaitForAsync("chest_opened",
            d => d.ValueKind == JsonValueKind.Object && d.TryGetProperty("id", out var c) && c.GetString() == id,
            TimeSpan.FromSeconds(2));
        await _budget.EmitAsync("open_chest", new { id });
        try { return JsonNode.Parse((await opened).GetRawText())!.AsObject(); }
        catch (TimeoutException) { return null; }
    }

    /// <summary>Opens each chest that we know of. Returns how many opened.</summary>
    public async Task<int> OpenChestsAsync()
    {
        List<string> ids;
        lock (_world.Gate) ids = [.. _world.Chests.Keys];
        var count = 0;
        foreach (var id in ids)
        {
            var r = await OpenChestAsync(id);
            if (r is not null && !r.Bool("gone")) count++;
            // Also with no reply (a full bag: "loot_no_space"; the chest stays on the
            // server, node/server.js:11315): forget it, so that we do not try it forever.
            lock (_world.Gate) _world.Chests.Remove(id);
        }
        return count;
    }
    // endregion open-chests

    // region respawn
    /// <summary>The ms until the server accepts `respawn`: rip_time after the death. 0 when alive.</summary>
    public double RespawnMsLeft()
    {
        lock (_world.Gate)
            return _diedAt is long at ? Math.Max(0, at + RipTimeMs - Environment.TickCount64) : 0;
    }

    /// <summary>
    /// Waits the rest of the 12 s rip_time, then sends `respawn`. If the server says
    /// cant_respawn (our clock is early), wait its ms and try once more
    /// (node/server.js:6271-6309). True when we are alive again.
    /// </summary>
    public async Task<bool> RespawnAsync()
    {
        await Task.Delay(TimeSpan.FromMilliseconds(RespawnMsLeft()));
        // 3 s: the reply comes after the map change.
        var r = await RequestAsync("respawn", new { }, "respawn", 3000);
        if (r is { Response: "cant_respawn" })
        {
            await Task.Delay(TimeSpan.FromMilliseconds(r.Ms));
            r = await RequestAsync("respawn", new { }, "respawn", 3000);
        }
        return r is { Failed: false };
    }
    // endregion respawn
}
