// Farmer.cs: the decisions of a fighting character, one tick at a time: stay
// alive, loot, choose a target, walk, attack.
//
// TickAsync() does the first thing on this list that applies, and returns. It
// remembers nothing between ticks except the target and the counters, so a
// monster that attacks during a walk changes the next tick at once.
//   1. dead: respawn          2. in jail: leave          3. on another map: go home
//   4. low hp or mp: heal     5. a chest: open it        6. no target: choose one
//   7. too far: walk          8. in range: attack
//
// Threads: the handlers run on the dispatcher thread with world.Gate locked.
// The state of the Farmer (target, counters) is guarded by world.Gate too.
using System.Text.Json.Nodes;

namespace Albot;

public sealed class Farmer
{
    // region ladder
    /// <summary>The Mainland ladder of the game guide ("Your first day"): the next
    /// monster when the current one is too easy. All live on `main`.</summary>
    public static readonly string[] Ladder = ["goo", "bee", "crab", "snake", "squig", "armadillo", "croc", "tortoise"];
    // "Too easy": the last 3 kills took 2 attacks or fewer each (the guide's rule:
    // "go to the next monster when you kill the current one in one or two hits").
    private const int EasyHits = 2;
    private const int EasyKills = 3;
    // endregion ladder

    // Heal below 70 % hp: a potion (or the free regeneration) brings us back up
    // before a weak monster can take the other 30 %. Mana below 30 %: a class
    // that uses mana for attacks (priest, mage) needs it.
    private const double HealHp = 0.7;
    private const double HealMp = 0.3;
    // Stop 10 px inside our range: the monster moves while we walk.
    private const double RangeMargin = 10;

    private readonly World _world;
    private readonly Actions _act;
    private readonly Cooldowns _cooldowns;
    private readonly Travel _travel;
    private readonly string _prefix;
    private string _type = "goo";
    private string? _target;
    private int _kills;
    private int _hits; // our hits on the target
    private readonly List<int> _recent = []; // hits for each of the last kills

    /// <summary>prefix: put before each line that it prints ("Tester: ").</summary>
    public Farmer(World world, Actions act, Cooldowns cooldowns, Travel travel, string prefix = "")
    {
        _world = world;
        _act = act;
        _cooldowns = cooldowns;
        _travel = travel;
        _prefix = prefix;
        // The target is dead when we get `death` with its id, or a `hit` with `kill`.
        world.Listen("death", d => Dead(d.Str("id")));
        world.Listen("hit", d =>
        {
            if (d.Str("id") != _target) return;
            if (d.Str("hid") == world.Me.Str("id")) _hits++;
            if (d.Bool("kill")) Dead(d.Str("id"));
        });
        // Each chest that opens for us.
        world.Listen("chest_opened", r =>
        {
            if (!r.Bool("gone"))
                Log($"chest {r.Str("id")}: +{r.Num("gold")} gold, {(r?["items"] as JsonArray)?.Count ?? 0} item(s)");
        });
    }

    /// <summary>The monster type that we hunt now.</summary>
    public string Type { get { lock (_world.Gate) return _type; } set { lock (_world.Gate) _type = value; } }
    /// <summary>The map of our monsters.</summary>
    public string Home { get; set; } = "main";
    /// <summary>The id of the monster that we attack, or null.</summary>
    public string? Target { get { lock (_world.Gate) return _target; } set { lock (_world.Gate) _target = value; } }
    public int Kills { get { lock (_world.Gate) return _kills; } }

    public void Log(string line) => Console.WriteLine(_prefix + line);

    // Called with world.Gate locked (from a handler).
    private void Dead(string? id)
    {
        if (id is null || id != _target) return;
        Log($"killed {_type} {id}");
        _kills++;
        _recent.Add(_hits);
        if (_recent.Count > EasyKills) _recent.RemoveAt(0);
        _target = null;
        _hits = 0;
    }

    // region next-type
    /// <summary>
    /// Moves up the ladder when the last kills were easy. True when the type changed.
    /// Check the next monster in the game guide first: its damage per second must be
    /// less than your healing (game guide, "Your first day").
    /// </summary>
    public bool NextType()
    {
        lock (_world.Gate)
        {
            var i = Array.IndexOf(Ladder, _type);
            var easy = _recent.Count == EasyKills && _recent.All(h => h <= EasyHits);
            if (!easy || i < 0 || i + 1 >= Ladder.Length) return false;
            _type = Ladder[i + 1];
            _recent.Clear();
            _target = null;
            Log($"next monster: {_type}");
            return true;
        }
    }
    // endregion next-type

    // region tick
    public async Task TickAsync()
    {
        // A copy of what we need, read with the lock. The awaits below run without it.
        bool rip, hurt, low, chests;
        string? map;
        double x, y;
        lock (_world.Gate)
        {
            _world.Advance(); // positions at this moment
            var me = _world.Me;
            rip = me.Bool("rip");
            map = me.Str("map");
            x = me.Num("x");
            y = me.Num("y");
            hurt = me.Num("hp") < HealHp * me.Num("max_hp");
            low = me.Num("mp") < HealMp * me.Num("max_mp");
            chests = _world.Chests.Count > 0;
        }

        // 1. Dead: wait for the 12 s, then respawn (at main spawn 5 on `main`).
        if (rip)
        {
            Log($"died; respawn in {Math.Ceiling(_act.RespawnMsLeft() / 1000)} s");
            if (await _act.RespawnAsync()) Log($"respawned at {Pos(_world.Me)}");
            return;
        }
        // 2. Jail: a line violation put us there. `leave` goes to the town.
        if (map == "jail")
        {
            Log("in jail: leave");
            if (await _travel.LeaveJailAsync()) Log($"left jail: on {Locked(() => _world.Me.Str("map"))} at {Pos(_world.Me)}");
            return;
        }
        // 3. Another map (a door, the bank, a respawn somewhere else): go home.
        if (map != Home)
        {
            Log($"on {map}: go to {Home}");
            await _travel.GoToMapAsync(Home);
            return;
        }
        // 4. Health first, then mana. HealAsync drinks a potion if we have one.
        if (_cooldowns.Ready("potion"))
        {
            if (hurt) await _act.HealAsync("hp");
            else if (low) await _act.HealAsync("mp");
        }
        // 5. Chests: open them all. Gold and items wait in a chest for 8 min only.
        if (chests)
        {
            await _act.OpenChestsAsync();
            return;
        }
        // 6. The target. Choose the nearest of our type if we have none.
        JsonObject? target;
        double dist, range, tx, ty;
        lock (_world.Gate)
        {
            target = _target is null ? null : _world.Monsters.GetValueOrDefault(_target);
            if (target is null)
            {
                target = _world.NearestMonster(_type);
                if (target is not null)
                {
                    _target = target.Str("id");
                    _hits = 0;
                    Log($"target: {_type} {_target} at {Pos(target)}");
                }
            }
            dist = target is null ? 0 : _world.Distance(_world.Me, target);
            range = _world.Me.Num("range");
            tx = target.Num("x");
            ty = target.Num("y");
        }
        if (target is null)
        {
            // None in view: walk to the middle of its spawn box (G.maps[map].monsters).
            var pack = (_world.G.Raw["maps"]?[map ?? ""]?["monsters"] as JsonArray ?? [])
                .FirstOrDefault(p => p.Str("type") == Type && p?["boundary"] is JsonArray);
            if (pack?["boundary"] is JsonArray b)
                await _travel.WalkToAsync((b[0]!.GetValue<double>() + b[2]!.GetValue<double>()) / 2,
                    (b[1]!.GetValue<double>() + b[3]!.GetValue<double>()) / 2);
            return;
        }
        // 7. Too far: walk to a point `range - 10` px from it, on the line to us.
        if (dist > range)
        {
            double dx = x - tx, dy = y - ty;
            var d = Math.Sqrt(dx * dx + dy * dy);
            if (d == 0) d = 1;
            var stop = Math.Max(0, range - RangeMargin);
            await _travel.WalkToAsync(tx + dx / d * stop, ty + dy / d * stop);
            return;
        }
        // 8. In range: attack when the cooldown allows.
        if (_cooldowns.Ready("attack")) await _act.AttackAsync(target.Str("id")!);
    }
    // endregion tick

    private T Locked<T>(Func<T> read) { lock (_world.Gate) return read(); }
    private string Pos(JsonObject e) => Locked(() => $"{Math.Round(e.Num("x"), MidpointRounding.AwayFromZero)},{Math.Round(e.Num("y"), MidpointRounding.AwayFromZero)}");
}
