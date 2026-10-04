// AlTest/Program.cs: send AlSocket through the login handshake of the game, on
// the local test server. It uses only AlSocket (Part 1 has no HTTP code yet).
// Run (in course/csharp): dotnet run --project AlTest
// AL_WS_URL: the WebSocket URL of a game server (default: EU I of the test server).
using System.Text.Json;
using Albot;

var url = Environment.GetEnvironmentVariable("AL_WS_URL") is { Length: > 0 } u
    ? u : "ws://localhost:8022/ws1/?EIO=4&transport=websocket";

var sock = await AlSocket.ConnectAsync(url);
Console.WriteLine($"connected to {url}");
// Register the wait for `welcome` FIRST. The server sends it at once, and AlSocket
// keeps events only until the first subscription of any name.
var welcomeWait = sock.WaitForAsync("welcome");
sock.On("game_error", e => Console.WriteLine($"game_error: {e}"));
sock.On("disconnect", reason => Console.WriteLine($"disconnect: {reason}"));

// 1. The server sends `welcome` to each new socket.
var welcome = await welcomeWait;
Console.WriteLine($"welcome: {welcome.GetProperty("region")} {welcome.GetProperty("name")}, version {welcome.GetProperty("version")}");

// 2. Send `loaded`. The reply is one full `entities` view (type "all").
//    Register the wait BEFORE the emit, so that a fast reply cannot pass first.
var viewWait = sock.WaitForAsync("entities", d => d.GetProperty("type").GetString() == "all");
await sock.EmitAsync("loaded", new { success = 1, width = 1920, height = 1080, scale = 2 });
var view = await viewWait;
Console.WriteLine($"entities: {view.GetProperty("monsters").GetArrayLength()} monster(s)");

// 3. Log in the character. Hard-coded: the fixed account of the test server.
//    Part 1 has no login code yet; Part 2 reads AL_AUTH instead. This auth works
//    only on the test server, so it is not a secret.
var startWait = sock.WaitForAsync("start");
await sock.EmitAsync("auth", new
{
    user = "US_tester",
    auth = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    character = "CH_tester",
    no_html = "1",
    passphrase = "",
});
var me = await startWait;
// `start` has no `name`: the id of a character is its name.
Console.WriteLine($"start: {me.GetProperty("id")} on {me.GetProperty("map")} at " +
    $"{Math.Round(me.GetProperty("x").GetDouble())},{Math.Round(me.GetProperty("y").GetDouble())}");

// 4. Do nothing for 3 s. The server sends pings in this time. If our pong
//    does not work, the server drops us and the next step fails.
await Task.Delay(TimeSpan.FromSeconds(3));
var ackWait = sock.WaitForAsync("ping_ack", d => d.GetProperty("id").GetString() == "42");
await sock.EmitAsync("ping_trig", new { id = "42" });
Console.WriteLine($"ping_ack after 3 s idle: {(await ackWait).GetProperty("id")}");

Console.WriteLine("OK");
await sock.CloseAsync(); // the `disconnect` handler prints the last line
