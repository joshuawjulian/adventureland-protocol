// FirstKill/Program.cs: the checkpoint of Part 2. Enter the game, kill one goo,
// open its chest, print the xp. It heals when hp is low and respawns if it dies.
// Run (in course/csharp): AL_AUTH=<user>-<auth> AL_CHARACTER=MyWarrior dotnet run --project FirstKill
// The goo must be on a straight line from you, with no wall between (Part 3 walks around walls).
using System.Text.Json.Nodes;
using Albot;

var bot = await Bot.ConnectAsync();
var (world, act, cooldowns) = (bot.World, bot.Act, bot.Cooldowns);
try
{
    Console.WriteLine($"in game as {Me("id")} ({Me("ctype")}, level {MeNum("level")}) on {Me("map")} at {Pos(world.Me)}");

    string? targetId = null;
    var killed = false;
    // Dead: a `death` for the goo, or our `hit` with kill: true. Handlers run with world.Gate locked.
    world.Listen("death", d => killed |= d.Str("id") == targetId);
    world.Listen("hit", d => killed |= d.Str("id") == targetId && d.Bool("kill"));

    // 90 s: a goo dies in about 20 s. Environment.TickCount64 is monotonic; the wall clock
    // (DateTime.UtcNow) can jump, for example in Docker on WSL2.
    var deadline = Environment.TickCount64 + 90_000;
    while (true)
    {
        if (Environment.TickCount64 > deadline) throw new TimeoutException("no kill in 90 s");
        world.Advance(); // positions are as of now
        if (Locked(() => killed)) break;

        if (Locked(() => world.Me.Bool("rip")))
        {
            Console.WriteLine($"died; respawn in {Math.Ceiling(act.RespawnMsLeft() / 1000)} s");
            if (!await act.RespawnAsync()) throw new Exception("respawn failed");
            Console.WriteLine($"respawned at {Locked(() => Pos(world.Me))}");
            continue;
        }

        // Heal first: below 70 % hp, when the potion timer is ready.
        if (MeNum("hp") < 0.7 * MeNum("max_hp") && cooldowns.Ready("potion"))
        {
            if (await act.HealAsync("hp")) Console.WriteLine($"heal hp: {Math.Round(MeNum("hp"))}/{Math.Round(MeNum("max_hp"))}");
        }

        // The target: the nearest goo, once (again only if it went out of view).
        JsonObject? goo;
        lock (world.Gate)
        {
            goo = targetId is null ? world.NearestMonster("goo") : world.Monsters.GetValueOrDefault(targetId);
            if (goo is not null && targetId is null)
            {
                targetId = goo.Str("id");
                Console.WriteLine($"target: goo {targetId} at {Pos(goo)}");
            }
        }
        if (goo is null)
        {
            lock (world.Gate) targetId = null; // gone from view: choose again
            await Task.Delay(100);
            continue;
        }

        double dist, range, gx, gy;
        lock (world.Gate)
        {
            dist = world.Distance(world.Me, goo);
            range = world.Me.Num("range");
            // A point at range - 10 px from the goo, on the line from the goo to us.
            // 10 px: room for the goo to move a little while we walk.
            double mx = world.Me.Num("x"), my = world.Me.Num("y"), ox = goo.Num("x"), oy = goo.Num("y");
            var len = Math.Max(Math.Sqrt((mx - ox) * (mx - ox) + (my - oy) * (my - oy)), 1);
            gx = ox + (mx - ox) / len * (range - 10);
            gy = oy + (my - oy) / len * (range - 10);
        }
        if (dist > range) await act.MoveToAsync(gx, gy);
        else if (cooldowns.Ready("attack")) await act.AttackAsync(targetId!);
        await Task.Delay(100); // 100 ms: the loop rate; the server needs no more
    }
    Console.WriteLine($"killed goo {targetId}");

    // The chest: `drop` comes with the kill, but wait up to 3 s for it.
    for (var i = 0; i < 30 && Locked(() => world.Chests.Count) == 0; i++) await Task.Delay(100);
    List<string> chests = Locked(() => world.Chests.Keys.ToList());
    foreach (var id in chests)
    {
        var r = await act.OpenChestAsync(id);
        if (r is null) continue; // no reply (no space?)
        var items = r["items"] as JsonArray;
        Console.WriteLine($"chest {id}: +{r.Num("gold")} gold, {items?.Count ?? 0} item(s)");
    }

    Console.WriteLine($"xp: {Math.Round(MeNum("xp"))}/{Math.Round(MeNum("max_xp"))}, level {MeNum("level")}");
    Console.WriteLine("OK");
}
finally
{
    await bot.CloseAsync();
}

// Small helpers: read the world with world.Gate locked.
T Locked<T>(Func<T> read) { lock (world.Gate) return read(); }
string? Me(string key) => Locked(() => world.Me.Str(key));
double MeNum(string key) => Locked(() => world.Me.Num(key));
static string Pos(JsonObject e) => $"{Math.Round(e.Num("x"))},{Math.Round(e.Num("y"))}";
