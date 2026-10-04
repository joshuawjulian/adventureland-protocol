// World.cs: our copy of the game world. Our character (Me), the monsters and
// other players in view, and the chests. The server sends changes; the
// handlers below apply them.
//
// Threads: AlSocket calls the handlers on its dispatcher thread, and your
// program reads the world on another thread. So one lock, Gate, guards all of
// the state. Each handler runs with Gate locked. Lock Gate when you read Me,
// Monsters, Players or Chests:  lock (world.Gate) { var hp = world.Me.Num("hp"); }
// The methods of World lock it for you. (A C# lock can be taken again by the
// thread that has it, so a handler can call these methods.)
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Albot;

/// <summary>
/// An entity (Me, a monster, a player) is the JSON object of the server, kept
/// as it is, so that `player` can merge into it field by field. These helpers
/// read one field. A missing number is 0.
/// </summary>
public static class Entity
{
    public static double Num(this JsonNode? e, string key)
    {
        if (e?[key] is JsonValue v)
        {
            if (v.TryGetValue<double>(out var d)) return d;
            // A value that C# code stored as int or long: read its JSON text.
            if (v.GetValueKind() == JsonValueKind.Number) return double.Parse(v.ToJsonString(), System.Globalization.CultureInfo.InvariantCulture);
        }
        return 0;
    }

    public static string? Str(this JsonNode? e, string key) =>
        e?[key] is JsonValue v && v.GetValueKind() == JsonValueKind.String ? v.GetValue<string>() : null;

    /// <summary>True for true, and for a value that JavaScript counts as true (rip can be a name).</summary>
    public static bool Bool(this JsonNode? e, string key) => e?[key] switch
    {
        null => false,
        JsonValue v => v.GetValueKind() switch
        {
            JsonValueKind.True => true,
            JsonValueKind.String => v.GetValue<string>() != "",
            JsonValueKind.Number => e.Num(key) != 0,
            _ => false,
        },
        _ => true, // an object or array
    };
}

public sealed class World
{
    /// <summary>Lock this before you read or change the state below.</summary>
    public readonly object Gate = new();

    public readonly AlSocket Sock;
    public readonly GData G;

    /// <summary>Our character: the `start` data (without entities), with each `player` merged in.
    /// Empty until `start`. Always the same object, so a reference to it stays good.</summary>
    public readonly JsonObject Me = [];
    /// <summary>id -> monster.</summary>
    public readonly Dictionary<string, JsonObject> Monsters = [];
    /// <summary>id -> other player or NPC. Never us.</summary>
    public readonly Dictionary<string, JsonObject> Players = [];
    /// <summary>chest id -> the `drop` data.</summary>
    public readonly Dictionary<string, JsonObject> Chests = [];

    private readonly Dictionary<string, List<Action<JsonNode?>>> _handlers = [];
    private long _last = Environment.TickCount64; // ms; the time of the last Advance or update

    // region constructor
    /// <summary>Create it BEFORE you send `loaded` and `auth`, so that no update passes before the handlers exist.</summary>
    public World(AlSocket sock, GData g)
    {
        Sock = sock;
        G = g;
        Listen("start", OnStart);
        Listen("player", OnPlayer);
        Listen("entities", ApplyEntities);
        Listen("death", d => Monsters.Remove(d.Str("id") ?? "")); // a monster died
        Listen("disappear", d =>
        {
            // A monster or player left the view, left the map, or disconnected.
            var id = d.Str("id") ?? "";
            Monsters.Remove(id);
            Players.Remove(id);
        });
        Listen("new_map", OnNewMap);
        Listen("drop", d => { if (d.Str("id") is string id) Chests[id] = d!.AsObject(); });
        Listen("chest_opened", d => Chests.Remove(d.Str("id") ?? ""));
        Listen("correction", d =>
        {
            // The server did not agree with the position of our `move`: use its x and y.
            Advance();
            Me["x"] = d.Num("x");
            Me["y"] = d.Num("y");
        });
    }
    // endregion constructor

    // region listen
    /// <summary>
    /// One table from event name to handlers. Hitchhikers (events that ride inside
    /// `player`) go through Dispatch too, so a handler sees them as if they came alone.
    /// The first Listen for a name also subscribes to the socket.
    /// </summary>
    public void Listen(string name, Action<JsonNode?> handler)
    {
        lock (Gate)
        {
            if (!_handlers.TryGetValue(name, out var list))
            {
                _handlers[name] = list = [];
                Sock.On(name, data => Dispatch(name, ToNode(data)));
            }
            list.Add(handler);
        }
    }

    /// <summary>Calls the handlers of name, with Gate locked.</summary>
    public void Dispatch(string name, JsonNode? data)
    {
        lock (Gate)
        {
            if (!_handlers.TryGetValue(name, out var list)) return;
            foreach (var handler in list.ToList())
            {
                // One bad handler must not stop the others.
                try { handler(data); }
                catch (Exception e) { Console.Error.WriteLine($"handler for \"{name}\" threw: {e.Message}"); }
            }
        }
    }

    // AlSocket gives a JsonElement (read-only). Entities must change, so make a JsonNode.
    // An event with no payload gives null.
    private static JsonNode? ToNode(JsonElement data) =>
        data.ValueKind == JsonValueKind.Undefined ? null : JsonNode.Parse(data.GetRawText());
    // endregion listen

    // region on-start
    // `start`: the full private data of our character, plus the first view in `entities`.
    private void OnStart(JsonNode? data)
    {
        if (data is not JsonObject start) return;
        Me.Clear();
        foreach (var (key, value) in start)
            if (key != "entities") Me[key] = value?.DeepClone(); // a copy: a node has only one parent
        _last = Environment.TickCount64;
        ApplyEntities(start["entities"]);
    }
    // endregion on-start

    // region on-player
    // `player`: changes to our character. Merge them field by field. Note: live sends
    // no `name` for a character, only `id`, and the id is the name.
    private void OnPlayer(JsonNode? data)
    {
        if (data is not JsonObject player) return;
        Advance(); // bring the others to now: the time base changes below
        foreach (var (key, value) in player)
            if (key != "hitchhikers") Me[key] = value?.DeepClone();
        // Hitchhikers: [event, payload] pairs that rode along. Handle each as if it came alone.
        foreach (var pair in player["hitchhikers"]?.AsArray() ?? [])
            if (pair?[0] is JsonValue v && v.TryGetValue<string>(out var name)) Dispatch(name, pair[1]?.DeepClone());
    }
    // endregion on-player

    // region apply-entities
    // `entities`: monsters and players in view. Each object is the full state of
    // that entity now: replace it, do not merge.
    private void ApplyEntities(JsonNode? data)
    {
        if (data is null || data.Str("in") != Me.Str("in")) return; // an instance that we left
        Advance();
        if (data.Str("type") == "all") { Monsters.Clear(); Players.Clear(); } // a full view
        foreach (var node in data["monsters"]?.AsArray() ?? [])
        {
            if (node?.DeepClone() is not JsonObject monster || monster.Str("id") is not string id) continue;
            Monsters[id] = WithDefaults(monster);
        }
        foreach (var node in data["players"]?.AsArray() ?? [])
        {
            if (node?.DeepClone() is not JsonObject player || player.Str("id") is not string id) continue;
            if (id != Me.Str("id")) Players[id] = player; // a full view can include us
        }
    }

    /// <summary>
    /// A monster has only the fields that differ from G.monsters[type]
    /// (node/server.js:1003-1071, monster_to_client). Fill the others from G.
    /// max_hp is G's hp: the server sends max_hp only when it differs.
    /// </summary>
    public JsonObject WithDefaults(JsonObject monster)
    {
        if (monster.Str("type") is string type && G.Monsters.TryGetValue(type, out var def))
        {
            monster["hp"] ??= def.Hp;
            monster["max_hp"] ??= def.Hp;
            monster["speed"] ??= def.Speed;
            monster["attack"] ??= def.Attack;
            monster["range"] ??= def.Range;
            monster["frequency"] ??= def.Frequency;
            monster["xp"] ??= def.Xp;
        }
        return monster;
    }
    // endregion apply-entities

    // region on-new-map
    // `new_map`: we went to another map (a door, `transport`, respawn, jail).
    // It has the new position and a full view of the new map.
    private void OnNewMap(JsonNode? data)
    {
        if (data is null) return;
        Me["map"] = data.Str("name");
        Me["in"] = data.Str("in");
        Me["x"] = data.Num("x");
        Me["y"] = data.Num("y");
        Me["m"] = data.Num("m"); // the map counter: `move` must send this value
        Me["moving"] = false;
        Me["going_x"] = data.Num("x");
        Me["going_y"] = data.Num("y");
        ApplyEntities(data["entities"]); // always type "all"
    }
    // endregion on-new-map

    // region step
    /// <summary>
    /// Moves one moving entity toward going_x, going_y. speed is in px per
    /// second, so a step is speed * ms / 1000 px. The server moves it the same way,
    /// so our copy stays close to the server between updates.
    /// </summary>
    public static void Step(JsonObject e, double ms)
    {
        if (!e.Bool("moving")) return;
        double x = e.Num("x"), y = e.Num("y"), gx = e.Num("going_x"), gy = e.Num("going_y");
        double dx = gx - x, dy = gy - y;
        double left = Math.Sqrt(dx * dx + dy * dy); // the distance still to go
        double travel = e.Num("speed") * ms / 1000;
        if (travel >= left) { e["x"] = gx; e["y"] = gy; e["moving"] = false; } // arrived
        else { e["x"] = x + dx / left * travel; e["y"] = y + dy / left * travel; }
    }
    // endregion step

    // region advance
    /// <summary>
    /// Steps Me, the monsters and the players by the time since the last Advance
    /// (or the last update). Call it before you read positions. There is no timer:
    /// the world moves only when somebody asks.
    /// </summary>
    public void Advance()
    {
        lock (Gate)
        {
            var now = Environment.TickCount64;
            double ms = now - _last;
            _last = now;
            if (ms <= 0) return;
            Step(Me, ms);
            foreach (var e in Monsters.Values) Step(e, ms);
            foreach (var e in Players.Values) Step(e, ms);
        }
    }
    // endregion advance

    // region distance
    /// <summary>
    /// The distance that the server checks for range: the gap between two hitboxes,
    /// not between the centres (distance(), js/old_common_functions.js:707-740).
    /// 0 when the boxes touch. A box is centred on x, with y at the feet.
    /// </summary>
    public double Distance(JsonObject a, JsonObject b)
    {
        // Two maps or two instances: the server returns this "far" value.
        if (a.Str("in") is string ain && b.Str("in") is string bin && ain != bin) return 99999999;
        if (a.Str("map") is string amap && b.Str("map") is string bmap && amap != bmap) return 99999999;
        var (aw, ah) = Size(a);
        var (bw, bh) = Size(b);
        double ax = a.Num("x"), ay = a.Num("y"), bx = b.Num("x"), by = b.Num("y");
        double dx = Math.Max(Math.Max(bx - bw / 2 - (ax + aw / 2), ax - aw / 2 - (bx + bw / 2)), 0);
        double dy = Math.Max(Math.Max(by - bh - ay, ay - ah - by), 0);
        return Math.Sqrt(dx * dx + dy * dy);
    }

    // The hitbox (width, height) of an entity.
    private (double W, double H) Size(JsonObject e)
    {
        // A character has `ctype` (its class). The server makes each character
        // 26 x 36 px (node/server.js:11782-11783).
        if (e["ctype"] is not null || e.Str("type") is not string type || !G.Monsters.TryGetValue(type, out var def))
            return (26, 36);
        // A monster: G.dimensions[type], times G.monsters[type].size. 24 x 24 when
        // G has no entry (get_monster_dimensions, js/old_common_functions.js:692).
        double w = 24, h = 24;
        if (G.Dimensions.TryGetValue(type, out var d) && d.Length >= 2) (w, h) = (d[0], d[1]);
        if (def.Size is double size && size != 0) (w, h) = (Math.Round(w * size), Math.Round(h * size));
        return (w, h);
    }
    // endregion distance

    /// <summary>The monster nearest to Me (of this type, if given), or null. Call Advance first.</summary>
    public JsonObject? NearestMonster(string? type = null)
    {
        lock (Gate)
        {
            return Monsters.Values
                .Where(m => type is null || m.Str("type") == type)
                .OrderBy(m => Distance(Me, m))
                .FirstOrDefault();
        }
    }
}
