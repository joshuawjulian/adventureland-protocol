// Supplies/Program.cs: a farming bot that looks after itself. After each chest
// it wears better gear; when potions or bag space run low, it walks to the
// town, sells the loot, buys potions and the basic armor, and goes back to farm.
// Run (in course/csharp): AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger dotnet run --project Supplies [trips]
//      trips: stop after this many town trips (the tests use 1). Without it: until Ctrl-C.
using System.Text.Json.Nodes;
using Albot;

const int TickMs = 100;

// region rules
// The restock rule (the game guide, "Your first hour" and "Inventory"):
const int MinPotions = 20; // go to town below 20 hpot0 or 20 mpot0 ...
const int MinFree = 5;     // ... or below 5 free inventory slots
const int Potions = 50;    // buy up to 50 of each (20 gold each: 2,000 gold for both)
const double KeepGold = 2000; // never spend the potion money on armor ("Your first day", step 1)
// The basic armor that a new character does not wear, from Gabriel (`basics`).
string[] armor = ["gloves", "coat", "pants"];
// endregion rules

var stop = false;
Console.CancelKeyPress += (_, e) => { e.Cancel = true; stop = true; };

var trips = args.Length > 0 ? int.Parse(args[0]) : 0;
var bot = await Bot.ConnectAsync();
var (world, act, G) = (bot.World, bot.Act, bot.G);
var me = world.Me; // always the same object; read it with world.Gate locked
lock (world.Gate)
    Console.WriteLine($"in game as {me.Str("id")} ({me.Str("ctype")}, level {me.Num("level")}) on {me.Str("map")} at {Math.Round(me.Num("x"))},{Math.Round(me.Num("y"))}");
var travel = new Travel(world, act);
var items = new Items(world, act, bot.Budget);
var farmer = new Farmer(world, act, bot.Cooldowns, travel);

// region town
// Walks to within NpcDist of an NPC. Says so only when it must walk.
async Task<bool> GoNear(Npc? npc)
{
    if (npc is null) throw new InvalidOperationException("no such NPC on this map");
    double gap;
    lock (world.Gate)
    {
        world.Advance();
        gap = Math.Sqrt(Math.Pow(me.Num("x") - npc.X, 2) + Math.Pow(me.Num("y") - npc.Y, 2));
    }
    if (gap <= Items.NpcDist) return true;
    Console.WriteLine($"walk to {npc.Id} at {npc.X},{npc.Y}");
    return await travel.WalkToAsync(npc.X, npc.Y);
}

// Buys quantity of name from the NPC that sells it.
async Task<bool> Shop(string name, int quantity)
{
    if (!await GoNear(items.NpcSelling(name))) return false;
    var r = await items.BuyAsync(name, quantity);
    Console.WriteLine(r is { Failed: false } ? $"buy {name} x{r.Data.Num("q")}: {r.Data.Num("cost")} gold" : $"buy {name}: {r?.Response ?? "no answer"}");
    return r is { Failed: false };
}

async Task<bool> TownTrip()
{
    // 1. Sell the loot to the potion shop (any shop buys any item).
    if (!await GoNear(items.NpcSelling("hpot0"))) return false;
    for (var num = 0; ; num++)
    {
        JsonNode? it;
        lock (world.Gate)
        {
            var bag = me["items"] as JsonArray ?? [];
            if (num >= bag.Count) break;
            it = bag[num]?.DeepClone();
        }
        if (!Items.IsLoot(G, it)) continue;
        var r = await items.SellAsync(num, it!["q"] is null ? 1 : (int)it.Num("q"));
        if (r is { Failed: false }) Console.WriteLine($"sell {it.Str("name")}: +{r.Data.Num("gold")} gold");
    }
    // 2. Potions, up to Potions of each.
    foreach (var name in new[] { "hpot0", "mpot0" })
    {
        var need = Potions - items.Count(name);
        if (need > 0) await Shop(name, need);
    }
    // 3. The basic armor that we do not wear, while the gold lasts.
    foreach (var name in armor)
    {
        var slot = G.Items[name].Type; // "gloves", "chest", "pants": the slot has the type's name
        bool skip;
        lock (world.Gate) skip = me["slots"]?[slot] is not null || me.Num("gold") - G.Items[name].G < KeepGold;
        if (!skip) await Shop(name, 1);
    }
    foreach (var line in await items.EquipBetterAsync()) Console.WriteLine($"equip {line}");
    double gold;
    lock (world.Gate) gold = me.Num("gold");
    Console.WriteLine($"bag: {items.Count("hpot0")} hpot0, {items.Count("mpot0")} mpot0, {items.FreeSlots()} free slot(s), {gold} gold");
    return true;
}
// endregion town

// region loop
var chests = 0; // chests opened so far (the handler runs with world.Gate locked)
var seen = 0;   // chests that we checked after
world.Listen("chest_opened", r => { if (!r.Bool("gone")) chests++; });
var done = 0;
while (!stop && (trips == 0 || done < trips))
{
    await Task.Delay(TickMs);
    await farmer.TickAsync();
    int opened;
    lock (world.Gate) opened = chests;
    if (opened == seen) continue;
    // After each chest: wear what is better, then check the supplies.
    seen = opened;
    foreach (var line in await items.EquipBetterAsync()) Console.WriteLine($"equip {line}");
    int hp = items.Count("hpot0"), mp = items.Count("mpot0"), free = items.FreeSlots();
    if (hp >= MinPotions && mp >= MinPotions && free >= MinFree) continue;
    Console.WriteLine($"supplies low: {hp} hpot0, {mp} mpot0, {free} free slot(s)");
    if (await TownTrip()) done++;
    farmer.Target = null; // choose again: the old target is far away now
}
// endregion loop

await bot.CloseAsync();
Console.WriteLine("OK");
