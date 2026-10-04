// Connect/Program.cs: log in, open a socket to a game server, do the handshake,
// print where the character is, and close.
// Run (in course/csharp): AL_AUTH=<user>-<auth> AL_CHARACTER=MyMage dotnet run --project Connect
//   AL_SERVER (for example EUI) is optional: without it, the first server of the list.
using Albot;

try
{
    var bot = await Bot.ConnectAsync();
    var w = bot.Welcome;
    Console.WriteLine($"welcome: {w.GetProperty("region")} {w.GetProperty("name")}, version {w.GetProperty("version")}");
    lock (bot.World.Gate) // the dispatcher thread can change Me at the same time
    {
        var me = bot.World.Me;
        Console.WriteLine($"in game as {me.Str("id")} ({me.Str("ctype")}, level {me.Num("level")}) " +
            $"on {me.Str("map")} at {Math.Round(me.Num("x"))},{Math.Round(me.Num("y"))}");
    }
    Console.WriteLine("OK");
    await bot.CloseAsync(); // the server then saves the character and marks it offline
}
catch (Exception e)
{
    Console.Error.WriteLine(e.Message);
    return 1;
}
return 0;
