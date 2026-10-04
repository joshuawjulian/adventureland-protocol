// GearUp/Program.cs: upgrades a coat to +3 and compounds rings in groups of
// three, with the stop rule of the game guide. It farms first until it has a
// chest (gold and rings).
// Run (in course/csharp): AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger dotnet run --project GearUp
using System.Text.Json.Nodes;
using Albot;

const int TickMs = 100;

// region rules
// The stop rule (the game guide, "A progression plan"): take a piece to +3
// with no spare copy. Above +3 the chance falls (70 % for +4), so stop and
// use spares ("Step 2"). Also stop when the server's chance, with grace, is
// below 90 %: then a failure is too likely for an item that we wear.
const string Item = "coat"; // 6,000 gold at Gabriel (`basics`)
const int TargetLevel = 3;
const double MinChance = 0.9;
// Jewelry: compound groups of three while the chance is at least 90 %. For
// most jewelry that is +0 -> +1 only (99 %); +2 is 75 %.
// endregion rules

var bot = await Bot.ConnectAsync();
var (world, act, G) = (bot.World, bot.Act, bot.G);
var me = world.Me; // always the same object; read it with world.Gate locked
lock (world.Gate)
    Console.WriteLine($"in game as {me.Str("id")} ({me.Str("ctype")}, level {me.Num("level")}) on {me.Str("map")} at {Math.Round(me.Num("x"))},{Math.Round(me.Num("y"))}");
var travel = new Travel(world, act);
var items = new Items(world, act, bot.Budget);
var farmer = new Farmer(world, act, bot.Cooldowns, travel);

// 1. Farm until one chest opened: the first chest brings gold and rings.
var chests = 0;
world.Listen("chest_opened", r => { if (!r.Bool("gone")) chests++; });
while (Locked(() => chests) == 0)
{
    await Task.Delay(TickMs);
    await farmer.TickAsync();
}

// Walks to within `within` px of an NPC (or of a point). Says so only when it must walk.
async Task GoNear(Npc? npc, double within = Items.NpcDist)
{
    if (npc is null) throw new InvalidOperationException("no such NPC on this map");
    var gap = Locked(() =>
    {
        world.Advance();
        return Math.Sqrt(Math.Pow(me.Num("x") - npc.X, 2) + Math.Pow(me.Num("y") - npc.Y, 2));
    });
    if (gap <= within) return;
    Console.WriteLine($"walk to {npc.Id} at {npc.X},{npc.Y}");
    if (!await travel.WalkToAsync(npc.X, npc.Y)) throw new InvalidOperationException($"could not walk to {npc.Id}");
}

// Buys one name and returns its slot number.
async Task<int> BuyOne(string name)
{
    await GoNear(items.NpcSelling(name));
    var r = await items.BuyAsync(name, 1);
    if (r is null || r.Failed) throw new InvalidOperationException($"buy {name}: {r?.Response ?? "no answer"}");
    Console.WriteLine($"buy {name} x1: {r.Data.Num("cost")} gold");
    return (int)r.Data.Num("num");
}

// 2. The item to upgrade.
var num = items.Find(Item);
if (num < 0) num = await BuyOne(Item);

// 3. Stand where both Lucas (scrolls) and Cue (upgrade, compound) are within
//    400 px: the middle of the two (about 140 px from each).
var lucas = items.NpcSelling("scroll0");
var cue = items.NpcWithRole("newupgrade");
if (lucas is null || cue is null) throw new InvalidOperationException("no scroll shop or upgrade NPC on this map");
var spot = new Npc("scrolls and newupgrade", Math.Round((lucas.X + cue.X) / 2, MidpointRounding.AwayFromZero), Math.Round((lucas.Y + cue.Y) / 2, MidpointRounding.AwayFromZero));
await GoNear(spot, 20); // 20 px: near the middle, so that both stay within 400 px

// region upgrade-loop
while (num >= 0 && LevelAt(num) < TargetLevel)
{
    var level = LevelAt(num);
    var scroll = items.Find("scroll0");
    if (scroll < 0) scroll = await BuyOne("scroll0");
    // Ask first: the chance includes grace, which only the server knows.
    var calc = await items.UpgradeAsync(num, scroll, true);
    if (calc is null || calc.Failed || calc.Response != "upgrade_chance")
    {
        Console.WriteLine($"upgrade {Item}: {calc?.Response ?? "no answer"}");
        break;
    }
    var chance = calc.Data.Num("chance");
    if (chance < MinChance)
    {
        Console.WriteLine($"stop: the chance for +{level + 1} is {F2(chance)}");
        break;
    }
    var r = await items.UpgradeAsync(num, scroll);
    var result = r?.Response switch { "upgrade_success" => "success", "upgrade_fail" => "fail", null => "no answer", var x => x };
    Console.WriteLine($"upgrade {Item} +{level} -> +{level + 1}: {result} (chance {F2(chance)})");
    if (result != "success") break; // a fail destroys the item
    if (r!.Data["num"] is not null) num = (int)r.Data.Num("num");
}
// endregion upgrade-loop

// region compound-loop
// Groups of three: same name, same level, an item that compounds (G `compound`).
int[]? FindGroup() => Locked(() =>
{
    var groups = new Dictionary<string, List<int>>();
    var bag = me["items"] as JsonArray ?? [];
    for (var n = 0; n < bag.Count; n++)
    {
        var it = bag[n];
        if (it is null || it["l"] is not null || it.Str("name") is not string name) continue;
        if (G.Raw["items"]?[name]?["compound"] is null) continue;
        var key = $"{name} {it.Num("level")}";
        if (!groups.TryGetValue(key, out var list)) groups[key] = list = [];
        list.Add(n);
    }
    return groups.Values.FirstOrDefault(l => l.Count >= 3)?.Take(3).ToArray();
});

for (var group = FindGroup(); group is not null; group = FindGroup())
{
    var (name, level) = Locked(() => ((me["items"] as JsonArray)![group[0]].Str("name")!, (int)(me["items"] as JsonArray)![group[0]].Num("level")));
    var scroll = items.Find("cscroll0");
    if (scroll < 0) scroll = await BuyOne("cscroll0");
    var calc = await items.CompoundAsync(group, scroll, true);
    if (calc is null || calc.Failed || calc.Response != "compound_chance" || calc.Data.Num("chance") < MinChance)
    {
        var why = calc is { Response: "compound_chance" } ? F2(calc.Data.Num("chance")) : calc?.Response ?? "no answer";
        Console.WriteLine($"stop: compound {name} +{level}: {why}");
        break;
    }
    var chance = calc.Data.Num("chance");
    var r = await items.CompoundAsync(group, scroll);
    var result = r?.Response switch { "compound_success" => "success", "compound_fail" => "fail", null => "no answer", var x => x };
    Console.WriteLine($"compound {name} +{level} x3 -> +{level + 1}: {result} (chance {F2(chance)})");
    if (result != "success" && result != "fail") break;
}
// endregion compound-loop

// 4. Wear the results.
foreach (var line in await items.EquipBetterAsync()) Console.WriteLine($"equip {line}");
string Show(string s) => Locked(() => me["slots"]?[s] is JsonNode it ? $"{it.Str("name")} +{it.Num("level")}" : "-");
Console.WriteLine($"gear: chest {Show("chest")}, ring1 {Show("ring1")}, ring2 {Show("ring2")}, belt {Show("belt")}");
await bot.CloseAsync();
Console.WriteLine("OK");

// Small helpers: read the world with world.Gate locked.
T Locked<T>(Func<T> read) { lock (world.Gate) return read(); }
// Two decimals with a "." on every computer (the culture of the computer can use ",").
static string F2(double v) => v.ToString("0.00", System.Globalization.CultureInfo.InvariantCulture);
int LevelAt(int n) => Locked(() => (int)(me["items"] as JsonArray)![n].Num("level"));
