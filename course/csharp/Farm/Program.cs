// Farm/Program.cs: a farming bot. It kills monsters of the Mainland ladder,
// loots, heals, respawns, leaves jail, and reconnects with the course's
// reconnect rule.
// Run (in course/csharp): AL_AUTH=<user>-<auth> AL_CHARACTER=MyRanger dotnet run --project Farm [seconds]
//      seconds: stop after this time (the tests use 25). Without it: until Ctrl-C.
using System.Runtime.InteropServices;
using Albot;

const int TickMs = 100; // one decision every 100 ms: fast enough, and cheap in call-cost
const long StableMs = 5 * 60000; // after a session of 5 min, the reconnect wait starts again at the first value

// region stop
// Ctrl-C (SIGINT) or `docker stop` (SIGTERM): finish this tick, close the
// socket, print the summary. A second Ctrl-C stops at once.
// The signal handlers run on another thread than the loop. A plain bool is
// not safe between threads: the JIT can read it once and keep the old value.
// A CancellationTokenSource is safe, and Task.Delay can wait for it too.
using var stopping = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) =>
{
    if (stopping.IsCancellationRequested) Environment.Exit(1);
    e.Cancel = true; // do not end the process now: the loop ends cleanly
    stopping.Cancel();
    Console.WriteLine("stopping (press Ctrl-C again to stop at once)");
};
using var term = PosixSignalRegistration.Create(PosixSignal.SIGTERM, ctx => { ctx.Cancel = true; stopping.Cancel(); });
bool Stop() => stopping.IsCancellationRequested;

// A sleep that ends early when we stop.
async Task Wait(int ms)
{
    try { await Task.Delay(ms, stopping.Token); }
    catch (OperationCanceledException) { } // we stop: the wait is over
}
// endregion stop

var seconds = args.Length > 0 ? double.Parse(args[0]) : 0;
var started = Environment.TickCount64;
var endAt = seconds > 0 ? started + (long)(seconds * 1000) : long.MaxValue;
var kills = 0;
var attempt = 0; // failed tries in a row, for ReconnectDelayMs
double level = 0, gold = 0; // our character in the last session

// region session
while (!Stop() && Environment.TickCount64 < endAt)
{
    // 1. Connect. A failure (the server is full, the save of the last session
    //    still runs, ...) waits as the reconnect rule says, then tries again.
    Bot bot;
    try { bot = await Bot.ConnectAsync(); }
    catch (Exception e)
    {
        var wait = Bot.ReconnectDelayMs(attempt++);
        Console.WriteLine($"connect failed: {e.Message}; try again in {wait / 1000} s");
        await Wait(wait);
        continue;
    }
    var session = Environment.TickCount64;
    var world = bot.World;
    lock (world.Gate)
    {
        var me = world.Me;
        Console.WriteLine($"in game as {me.Str("id")} ({me.Str("ctype")}, level {me.Num("level")}) on {me.Str("map")} at {Math.Round(me.Num("x"))},{Math.Round(me.Num("y"))}");
    }

    // 2. Play until we stop, the time is over, or the socket closes. AlSocket's
    //    local `disconnect` event has the reason; a send on a closed socket
    //    throws, so the catch below is the same case.
    // A handler (on the dispatcher thread) writes `lost`, and this loop reads it.
    // CompareExchange: the first reason counts, and the write is visible at
    // once; Volatile.Read always reads the value in memory, not an old copy.
    string? lost = null;
    world.Listen("disconnect", r => Interlocked.CompareExchange(ref lost, r?.ToString() ?? "disconnect", null));
    world.Listen("disconnect_reason", r => Console.WriteLine($"the server says: {r}")); // "limitdc", "limits", ...
    var farmer = new Farmer(world, bot.Act, bot.Cooldowns, new Travel(world, bot.Act));
    try
    {
        while (!Stop() && Volatile.Read(ref lost) is null && Environment.TickCount64 < endAt)
        {
            await Task.Delay(TickMs);
            await farmer.TickAsync();
            farmer.NextType(); // a stronger monster when this one is too easy
        }
    }
    catch (Exception e)
    {
        Interlocked.CompareExchange(ref lost, e.Message, null);
    }
    kills += farmer.Kills;
    lock (world.Gate) (level, gold) = (world.Me.Num("level"), world.Me.Num("gold"));
    // Read the reason BEFORE the close: our own close also fires `disconnect`.
    var reason = Volatile.Read(ref lost);
    try { await bot.CloseAsync(); } catch { } // the socket can be gone already
    if (reason is null) break; // we stopped, or the time is over

    // 3. The reconnect rule: wait, then make a new socket and a full handshake.
    if (Environment.TickCount64 - session >= StableMs) attempt = 0;
    var ms = Bot.ReconnectDelayMs(attempt++);
    Console.WriteLine($"disconnected: {reason}; reconnect in {ms / 1000} s");
    await Wait(ms);
}
// endregion session

var secs = Math.Round((Environment.TickCount64 - started) / 1000.0);
Console.WriteLine($"farmed {secs} s: {kills} kill(s), level {level}, {gold} gold");
Console.WriteLine("OK");
