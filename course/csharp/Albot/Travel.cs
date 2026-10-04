// Travel.cs: walk around walls, go through doors, use the transporter, and
// get out of jail.
//
// It uses the Grid of Pathfind.cs for the walls, and Actions.MoveToAsync for
// each straight part of the walk. Threads: it reads the World with world.Gate
// locked, and never holds the lock while it sends.
using System.Text.Json.Nodes;

namespace Albot;

/// <summary>One step between two maps: stand at (X, Y) on Map, then `transport` to To, Spawn.
/// By is "door" or "transporter".</summary>
public sealed record Hop(string Map, double X, double Y, string To, int Spawn, string By);

public sealed class Travel
{
    // The distances of the server (node/server.js:221-223): a door works within
    // 112 px of its box, the transporter NPC within 160 px of the NPC.
    private const double DoorDist = 112;
    private const double TransporterDist = 160;
    // How long to wait for `new_map` after a transport. Live sends it at once for
    // a door; for the bank it comes after the account loads (in_progress).
    private const int NewMapMs = 5000;

    private readonly World _world;
    private readonly Actions _act;
    private readonly GData _g;

    public Travel(World world, Actions act)
    {
        _world = world;
        _act = act;
        _g = world.G;
    }

    // region walk-to
    /// <summary>
    /// Walks to (x, y) on this map, around the walls. If (x, y) is not walkable,
    /// it walks to the nearest walkable point (at most 320 px away). True when we
    /// arrived; false when there is no path, or when something stopped the walk:
    /// a `correction`, a death, a door, or jail. The caller decides again on its next tick.
    /// </summary>
    public async Task<bool> WalkToAsync(double x, double y)
    {
        string? map;
        double m, sx, sy;
        lock (_world.Gate)
        {
            _world.Advance();
            map = _world.Me.Str("map");
            m = _world.Me.Num("m"); // the map counter: it changes on each map change
            sx = _world.Me.Num("x");
            sy = _world.Me.Num("y");
        }
        if (map is null) return false;
        var grid = Grid.ForMap(_g, map);
        if (!grid.Safe(x, y))
        {
            var k = grid.NearestFree(x, y);
            if (k < 0) return false;
            (x, y) = grid.Point(k);
        }
        var path = grid.FindPath(sx, sy, x, y);
        if (path is null) return false;
        foreach (var (px, py) in path)
        {
            var arrived = await _act.MoveToAsync(px, py);
            lock (_world.Gate)
            {
                var me = _world.Me;
                if (me.Str("map") != map || me.Num("m") != m || me.Bool("rip")) return false; // we left this map, or died
            }
            if (!arrived) return false; // a correction: our position was wrong
        }
        return true;
    }
    // endregion walk-to

    // region transport
    /// <summary>
    /// Sends `transport` {to, s}: through a door near us, or with the transporter
    /// NPC near us. Then waits until `new_map` puts us on map. The server answers a
    /// door with success and sends `new_map` first; the bank answers
    /// {in_progress: true}, and `new_map` comes later (node/server.js:5887-6056).
    /// </summary>
    public async Task<bool> TransportAsync(string map, int spawn)
    {
        double m;
        lock (_world.Gate) m = _world.Me.Num("m");
        var r = await _act.RequestAsync("transport", new { to = map, s = spawn });
        if (r is null || r.Failed) return false; // for example transport_cant_reach: too far from the door
        return await WaitUntilAsync(() => _world.Me.Num("m") != m && _world.Me.Str("map") == map, NewMapMs);
    }
    // endregion transport

    // region leave-jail
    /// <summary>
    /// A line violation (a `move` from or to a point that is not walkable) sends
    /// the character to the map `jail`. `leave` takes it to `main` spawn 0, the
    /// town (node/server.js:5864-5885). It fails while the character is dead, or
    /// with more than 5 monsters on it.
    /// </summary>
    public async Task<bool> LeaveJailAsync()
    {
        var r = await _act.RequestAsync("leave", new { });
        if (r is null || r.Failed) return false;
        return await WaitUntilAsync(() => _world.Me.Str("map") != "jail", NewMapMs);
    }
    // endregion leave-jail

    // region route
    /// <summary>
    /// The ways out of map: each door that needs no key, and each place of the
    /// transporter if the map has one. A door [x, y, w, h, to, to_spawn,
    /// own_spawn, lock] works from its own spawn point (door[6]); the server
    /// measures from the box of the door at that spawn (node/server.js:5899-5910).
    /// </summary>
    public List<Hop> Exits(string map)
    {
        var output = new List<Hop>();
        if (_g.Raw["maps"]?[map] is not JsonObject def) return output;
        var spawns = def["spawns"] as JsonArray ?? [];
        foreach (var door in def["doors"] as JsonArray ?? [])
        {
            if (door is not JsonArray d || d.Count < 7) continue;
            if (d.Count > 7 && d[7] is not null) continue; // a locked door ("ulocked", ...): it needs a key first
            var own = (int)d[6]!.GetValue<double>();
            if (own < 0 || own >= spawns.Count || spawns[own] is not JsonArray s) continue;
            output.Add(new Hop(map, s[0]!.GetValue<double>(), s[1]!.GetValue<double>(),
                d[4]!.GetValue<string>(), (int)(d[5]?.GetValue<double>() ?? 0), "door"));
        }
        var npc = (def["npcs"] as JsonArray ?? []).FirstOrDefault(n => n.Str("id") == "transporter");
        var pos = npc?["position"] as JsonArray ?? npc?["positions"]?[0] as JsonArray;
        if (pos is not null)
        {
            // G.npcs.transporter.places: map -> the spawn where she sends you.
            foreach (var (to, spawn) in _g.Raw["npcs"]?["transporter"]?["places"] as JsonObject ?? [])
                if (to != map)
                    output.Add(new Hop(map, pos[0]!.GetValue<double>(), pos[1]!.GetValue<double>(),
                        to, (int)(spawn?.GetValue<double>() ?? 0), "transporter"));
        }
        return output;
    }

    /// <summary>The fewest hops from one map to another: a breadth-first search on
    /// the graph of maps. An empty list when we are there, null when no route exists.</summary>
    public List<Hop>? Route(string from, string to)
    {
        if (from == to) return [];
        var came = new Dictionary<string, Hop?> { [from] = null }; // map -> the hop that reached it
        var queue = new Queue<string>([from]);
        while (queue.Count > 0)
        {
            var map = queue.Dequeue();
            foreach (var hop in Exits(map))
            {
                if (came.ContainsKey(hop.To) || _g.Raw["maps"]?[hop.To] is null) continue;
                came[hop.To] = hop;
                if (hop.To == to)
                {
                    var hops = new List<Hop>();
                    for (Hop? h = hop; h is not null; h = came.GetValueOrDefault(h.Map)) hops.Insert(0, h);
                    return hops;
                }
                queue.Enqueue(hop.To);
            }
        }
        return null;
    }

    /// <summary>Goes to map along Route(): for each hop, walk to the door (or to the
    /// transporter), then transport. True when we are on map.</summary>
    public async Task<bool> GoToMapAsync(string map)
    {
        string from;
        lock (_world.Gate) from = _world.Me.Str("map") ?? "";
        var hops = Route(from, map);
        if (hops is null) return false;
        foreach (var hop in hops)
        {
            if (!await WalkToAsync(hop.X, hop.Y)) return false;
            // WalkToAsync can stop short of the point (at the nearest walkable cell).
            // The server then says "transport_cant_reach"; do not even ask.
            double gap;
            lock (_world.Gate)
            {
                double dx = _world.Me.Num("x") - hop.X, dy = _world.Me.Num("y") - hop.Y;
                gap = Math.Sqrt(dx * dx + dy * dy);
            }
            if (gap > (hop.By == "door" ? DoorDist : TransporterDist)) return false;
            if (!await TransportAsync(hop.To, hop.Spawn)) return false;
        }
        lock (_world.Gate) return _world.Me.Str("map") == map;
    }
    // endregion route

    // Tests the condition (with world.Gate locked) every 50 ms, until it is true
    // or until ms have passed.
    private async Task<bool> WaitUntilAsync(Func<bool> test, int ms)
    {
        var end = Environment.TickCount64 + ms;
        while (true)
        {
            lock (_world.Gate) if (test()) return true;
            if (Environment.TickCount64 >= end) return false;
            await Task.Delay(50);
        }
    }
}
