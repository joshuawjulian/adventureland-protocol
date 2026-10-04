// PartyMerchant/Program.cs: three fighters and one merchant in one program.
// The fighters farm in a party. The merchant walks to them, takes their loot
// and gold, sells the loot in the town and puts the gold in the bank.
// Run (in course/csharp): AL_AUTH=<user>-<auth> AL_CHARACTER=MyWarrior dotnet run --project PartyMerchant [trips]
//      AL_CHARACTER is the leader. The program adds the next two fighters of
//      your character list, and your first merchant.
//      trips: stop after this many merchant trips (the tests use 1). Without it: until Ctrl-C.
// Make a merchant first, if you have none:
//      dotnet run --project PartyMerchant -- --create-merchant MyMerchant
using System.Text.Json.Nodes;
using Albot;

const int TickMs = 100;

// region rules
const int Fighters = 3;          // the live limit: 3 characters that fight, plus merchants (game guide, "Many characters and bots")
const double GiveDist = 300;     // `send` works within 400 px on the same map (node/server.js:8463-8560)
const double FighterGold = 20000; // a fighter keeps this much gold for potions, and gives the rest
const double MerchantGold = 50000; // the merchant keeps this much, and banks the rest
// endregion rules

// The fighters and the merchant run at the same time, on several threads. One
// token tells all of them to stop: Ctrl-C, or the end of the last trip.
var stop = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; stop.Cancel(); };

// region choose
var auth = await Api.LoginAsync();
var (servers, characters) = await Api.ServersAndCharactersAsync(auth);
if (args.Length > 0 && args[0] == "--create-merchant")
{
    var name = args.Length > 1 ? args[1] : "";
    await Team.CreateCharacterAsync(auth, name, "merchant");
    Console.WriteLine($"created the merchant {name}. Run the program again without --create-merchant.");
    return;
}
var trips = args.Length > 0 ? int.Parse(args[0]) : 0;
var server = Api.FindServer(servers); // AL_SERVER
var leader = Api.FindCharacter(characters); // AL_CHARACTER
if (leader.Type == "merchant") throw new InvalidOperationException("AL_CHARACTER must be a fighter: it leads the party");
var fighters = new[] { leader }.Concat(characters.Where(c => c.Type != "merchant" && c.Name != leader.Name)).Take(Fighters).ToList();
var merchantCharacter = characters.FirstOrDefault(c => c.Type == "merchant")
    ?? throw new InvalidOperationException("no merchant on this account: run with --create-merchant <Name> first");
Console.WriteLine($"team: {string.Join(", ", fighters.Select(c => c.Name))}; merchant: {merchantCharacter.Name}");
// endregion choose

// region connect
var G = await GData.LoadGAsync(); // one G for all four
var crew = new List<Crew>();
foreach (var c in fighters.Append(merchantCharacter))
{
    var m = await Team.ConnectMemberAsync(auth, server, c, G);
    lock (m.World.Gate)
    {
        var me = m.World.Me;
        Console.WriteLine($"in game as {me.Str("id")} ({me.Str("ctype")}, level {me.Num("level")}) on {me.Str("map")} at {Math.Round(me.Num("x"))},{Math.Round(me.Num("y"))}");
    }
    var travel = new Travel(m.World, m.Act);
    // Only fighters farm. (A Farmer also prints each chest that opens for us.)
    var farmer = c.Type != "merchant" ? new Farmer(m.World, m.Act, m.Cooldowns, travel, $"{m.Name}: ") : null;
    crew.Add(new Crew(m, travel, new Items(m.World, m.Act, m.Budget), new Party(m.World, m.Act), farmer));
}
var lead = crew[0];
var merchant = crew[^1];
var team = crew.Take(crew.Count - 1).ToList(); // the fighters
// endregion connect

// region party
// The leader invites each one; each waits for its `invite`, then accepts.
foreach (var c in crew.Skip(1))
{
    await lead.Party.InviteAsync(c.M.Name);
    if (!await c.Party.WaitInviteAsync(lead.M.Name)) throw new InvalidOperationException($"{c.M.Name} got no invitation");
    var r = await c.Party.AcceptAsync(lead.M.Name);
    if (r is null || r.Failed) throw new InvalidOperationException($"{c.M.Name} could not join: {r?.Response ?? "no answer"}");
}
for (var waited = 0; lead.Party.List.Count < crew.Count && waited < 5000; waited += 100) await Task.Delay(100);
Console.WriteLine($"party: {string.Join(", ", lead.Party.List)}");
// endregion party

// region fighter
// A fighter keeps only its potions. Everything else goes to the merchant:
// loot to sell, and jewelry that the merchant compounds later.
bool Give(JsonNode? it) => it is not null && it.Str("name") is string n && n != "placeholder" && it["l"] is null
    && G.Items.TryGetValue(n, out var def) && def.Type != "pot";

// A fighter farms. When the merchant is near, it gives its loot and gold.
async Task FighterLoop(Crew f)
{
    var world = f.M.World;
    while (!stop.IsCancellationRequested)
    {
        await Task.Delay(TickMs);
        await f.Farmer!.TickAsync();
        bool near;
        List<(int Num, int Q)> gifts = [];
        double gold;
        lock (world.Gate)
        {
            world.Advance();
            var me = world.Me;
            // The merchant, if it is in our view.
            near = world.Players.TryGetValue(merchant.M.Name, out var other) && world.Distance(me, other) <= GiveDist;
            var bag = me["items"] as JsonArray ?? [];
            for (var num = 0; num < bag.Count; num++)
                if (Give(bag[num])) gifts.Add((num, bag[num]!["q"] is null ? 1 : (int)bag[num].Num("q")));
            // Gold only above twice the reserve: not a `send` for each small chest.
            gold = me.Num("gold") > 2 * FighterGold ? me.Num("gold") - FighterGold : 0;
        }
        if (!near) continue;
        var n = 0;
        foreach (var (num, q) in gifts)
        {
            var r = await f.Items.SendItemAsync(merchant.M.Name, num, q);
            if (r is { Failed: false }) n++;
        }
        if (gold > 0) await f.Items.SendGoldAsync(merchant.M.Name, gold);
        if (n > 0 || gold > 0) Console.WriteLine($"{f.M.Name}: gave {n} item(s) and {gold} gold to {merchant.M.Name}");
    }
}
// endregion fighter

// region merchant
// The merchant: wait for loot, collect it, sell it, bank the gold.
bool HasLoot(Crew f)
{
    lock (f.M.World.Gate) return (f.M.World.Me["items"] as JsonArray ?? []).Any(Give);
}

async Task<bool> MerchantTrip()
{
    var world = merchant.M.World;
    var me = world.Me;
    // 1. Wait until a fighter has something to give.
    while (!stop.IsCancellationRequested && !team.Any(HasLoot)) await Task.Delay(500);
    // 2. Go to each fighter with loot, and wait (10 s at most) until it gave all.
    foreach (var f in team)
    {
        if (stop.IsCancellationRequested || !HasLoot(f)) continue;
        double fx, fy;
        lock (f.M.World.Gate) (fx, fy) = (f.M.World.Me.Num("x"), f.M.World.Me.Num("y"));
        Console.WriteLine($"{merchant.M.Name}: walk to {f.M.Name} at {Math.Round(fx)},{Math.Round(fy)}");
        await merchant.Travel.WalkToAsync(fx, fy);
        for (var waited = 0; HasLoot(f) && waited < 10000; waited += 200) await Task.Delay(200);
    }
    // 3. Sell the loot in the town. Keep the jewelry: three of a kind compound.
    var shop = merchant.Items.NpcSelling("hpot0") ?? throw new InvalidOperationException("no shop on this map");
    Console.WriteLine($"{merchant.M.Name}: walk to {shop.Id} at {shop.X},{shop.Y}");
    if (!await merchant.Travel.WalkToAsync(shop.X, shop.Y)) return false;
    int sold = 0;
    double gold = 0;
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
        var r = await merchant.Items.SellAsync(num, it!["q"] is null ? 1 : (int)it.Num("q"));
        if (r is { Failed: false }) { sold++; gold += r.Data.Num("gold"); }
    }
    Console.WriteLine($"{merchant.M.Name}: sold {sold} item(s): +{gold} gold");
    // 4. The bank: the door is north of the town. Deposit, then go back out.
    if (!await merchant.Travel.GoToMapAsync("bank")) return false;
    double amount;
    lock (world.Gate) amount = Math.Max(0, me.Num("gold") - MerchantGold);
    var d = await merchant.Items.DepositAsync(amount);
    Console.WriteLine($"{merchant.M.Name}: in the bank: deposited {(d is { Failed: false } ? d.Data.Num("gold") : 0)} gold");
    if (!await merchant.Travel.GoToMapAsync("main")) return false;
    lock (world.Gate) Console.WriteLine($"{merchant.M.Name}: back on main at {Math.Round(me.Num("x"))},{Math.Round(me.Num("y"))}");
    return true;
}
// endregion merchant

// region run
var fighting = team.Select(f => Task.Run(() => FighterLoop(f))).ToList();
var done = 0;
while (!stop.IsCancellationRequested && (trips == 0 || done < trips))
{
    if (await MerchantTrip()) done++;
}
stop.Cancel(); // the fighters end their loops
await Task.WhenAll(fighting);
foreach (var c in crew) await c.M.CloseAsync();
Console.WriteLine("OK");
// endregion run

/// <summary>One character of the team, with its tools. Farmer is null for the merchant.</summary>
sealed record Crew(Member M, Travel Travel, Items Items, Party Party, Farmer? Farmer);
