// Servers/Program.cs: get the list of game servers over HTTP and print the
// WebSocket URL of each. Standalone: it does not use the albot library.
// .NET 8, no packages.   Run (in course/csharp): dotnet run --project Servers
// AL_BASE_URL: the website (default https://adventure.land; the test server is http://localhost:8022).
using System.Net.Http.Json;
using System.Text.Json.Serialization;

var baseUrl = (Environment.GetEnvironmentVariable("AL_BASE_URL") is { Length: > 0 } b ? b : "https://adventure.land").TrimEnd('/');

using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(15) }; // 15 s: generous for a slow link
var res = await http.GetAsync($"{baseUrl}/api/get_servers");
Console.WriteLine($"status: {(int)res.StatusCode} {res.Content.Headers.ContentType}"); // 200 = OK
res.EnsureSuccessStatusCode(); // an exception for a 4xx or 5xx status

var body = await res.Content.ReadFromJsonAsync<ServerList>()
    ?? throw new Exception("the reply is empty");
// The game socket follows the scheme of the website: http -> ws, https -> wss.
var scheme = baseUrl.StartsWith("https:") ? "wss" : "ws";
foreach (var s in body.Servers)
{
    // The path must end with exactly one "/" (the server matches "/ws1/").
    var url = $"{scheme}://{s.Address}{s.Path.TrimEnd('/')}/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1";
    Console.WriteLine($"{s.Region} {s.Name}: {url}");
}

// The shape of the reply (api.js:884-900). Only the fields that we use.
record Server(
    [property: JsonPropertyName("region")] string Region,   // "EU", "US", "ASIA"
    [property: JsonPropertyName("name")] string Name,       // "I", "II", "PVP", ...
    [property: JsonPropertyName("address")] string Address, // the host, for example "eu1.adventure.land"
    [property: JsonPropertyName("path")] string Path);      // the Socket.IO path, for example "/ws1/"
record ServerList([property: JsonPropertyName("servers")] Server[] Servers);
