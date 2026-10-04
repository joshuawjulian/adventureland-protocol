// Api.cs: the HTTP API of the website. Log in, get the server list and the
// character list, and make the WebSocket URL of a game server.
// The live API is in api.js (vendor/adventureland_mongodb); the dispatcher that
// reads the request is common_engine/handlers.js.
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Albot;

/// <summary>A session: the user id and the auth token. AL_AUTH is "&lt;User&gt;-&lt;Token&gt;".</summary>
/// <remarks>The server calls the token "auth". C# does not allow a member with the
/// name of its type, so the record calls it Token.</remarks>
public sealed record Auth(string User, string Token);

/// <summary>One game server of the list (adventure_functions.js:761-776, servers_to_client).</summary>
public sealed record Server(
    [property: JsonPropertyName("region")] string Region,   // "EU", "US", "ASIA"
    [property: JsonPropertyName("name")] string Name,       // "I", "II", "PVP", ...
    [property: JsonPropertyName("players")] int Players,
    [property: JsonPropertyName("key")] string Key,         // the database id, "SR_EUI"
    [property: JsonPropertyName("address")] string Address, // the host (and port) of the WebSocket
    [property: JsonPropertyName("path")] string Path)       // the Socket.IO path on that host, "/ws1/"
{
    /// <summary>The AL_SERVER value: region + name, for example "EUI".</summary>
    public string Id => Region + Name;
}

/// <summary>One character of the account (adventure_functions.js:821-843, character_to_dict).</summary>
public sealed record Character(
    [property: JsonPropertyName("id")] string Id,     // "CH_...": the socket `auth` needs this, not the name
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("type")] string Type, // the class: "warrior", "priest", ...
    [property: JsonPropertyName("level")] int Level,
    [property: JsonPropertyName("online")] double Online,   // ms since the login; 0 when offline
    [property: JsonPropertyName("server")] string? Server); // "SR_EUI", only while online

public static class Api
{
    // One HttpClient for the whole program: it keeps connections open between calls.
    // UseCookies = false: we set the Cookie header ourselves. With the default
    // (true), the handler uses its own cookie store and ignores our header.
    // 60 s: G (data.js) is a few MB, and a slow link needs time.
    public static readonly HttpClient Http = new(new SocketsHttpHandler { UseCookies = false })
    {
        Timeout = TimeSpan.FromSeconds(60),
    };

    /// <summary>The website and its HTTP API: AL_BASE_URL, or the live site. No final "/".</summary>
    public static string BaseUrl()
    {
        var url = Environment.GetEnvironmentVariable("AL_BASE_URL");
        return (string.IsNullOrEmpty(url) ? "https://adventure.land" : url).TrimEnd('/');
    }

    // region api-call
    /// <summary>
    /// POST {base}/api/{method} with a JSON body. With an auth, the session goes in the
    /// cookie "auth=&lt;user&gt;-&lt;auth&gt;" (adventure_functions.js:371-385). The server
    /// answers HTTP 200 also when the call fails: then the JSON has failed and reason.
    /// So this throws only on another HTTP status, and returns the JSON as it is.
    /// </summary>
    public static async Task<JsonObject> ApiCallAsync(string method, object? body = null, Auth? auth = null)
    {
        using var req = new HttpRequestMessage(HttpMethod.Post, $"{BaseUrl()}/api/{method}")
        {
            Content = JsonContent.Create(body ?? new { }), // an empty object, not "null"
        };
        if (auth is not null) req.Headers.Add("Cookie", $"auth={auth.User}-{auth.Token}");
        using var res = await Http.SendAsync(req);
        if (res.StatusCode != HttpStatusCode.OK)
            throw new HttpRequestException($"{method}: HTTP {(int)res.StatusCode} {res.ReasonPhrase}");
        var text = await res.Content.ReadAsStringAsync();
        return JsonNode.Parse(text) as JsonObject
            ?? throw new HttpRequestException($"{method}: the reply is not a JSON object");
    }
    // endregion api-call

    /// <summary>Splits "&lt;user&gt;-&lt;auth&gt;" at the first "-". The user id has no "-".</summary>
    public static Auth ParseAuth(string text)
    {
        var dash = text.IndexOf('-');
        if (dash < 0) throw new ArgumentException("AL_AUTH must look like <user>-<auth>");
        return new Auth(text[..dash], text[(dash + 1)..]);
    }

    // region login
    /// <summary>
    /// The session. AL_AUTH when it is set: then no password goes over the network.
    /// Else one password login with AL_EMAIL and AL_PASSWORD, which prints the value
    /// to save. Each password login adds a token to the account (live keeps 200 at most).
    /// </summary>
    public static async Task<Auth> LoginAsync()
    {
        var saved = Environment.GetEnvironmentVariable("AL_AUTH");
        if (!string.IsNullOrEmpty(saved)) return ParseAuth(saved);

        var email = Environment.GetEnvironmentVariable("AL_EMAIL");
        var password = Environment.GetEnvironmentVariable("AL_PASSWORD");
        if (string.IsNullOrEmpty(email) || string.IsNullOrEmpty(password))
            throw new InvalidOperationException("set AL_AUTH, or AL_EMAIL and AL_PASSWORD");

        // only_login: true. Without it, the web API answers "cant_signup_on_web" (api.js:93).
        var reply = await ApiCallAsync("signup_or_login", new { email, password, only_login = true });
        // Success: {success: true, user, auth}. Failure: {failed: true, reason} (api.js:84-133).
        var user = (string?)reply["user"];
        var token = (string?)reply["auth"];
        if (reply["success"]?.GetValueKind() != JsonValueKind.True || user is null || token is null)
            throw new InvalidOperationException($"login failed: {(string?)reply["reason"] ?? "unknown reason"}");

        var value = $"{user}-{token}";
        Console.WriteLine("Logged in with the password. Save this value, and use it from now on:");
        Console.WriteLine($"  export AL_AUTH='{value}'");
        Console.WriteLine($"  PowerShell: $env:AL_AUTH = '{value}'");
        return new Auth(user, token);
    }
    // endregion login

    // region servers-and-characters
    /// <summary>
    /// The game servers and the characters of the account. They come in the item of
    /// `infs` with type "servers_and_characters" (api.js:451-472).
    /// </summary>
    public static async Task<(List<Server> Servers, List<Character> Characters)> ServersAndCharactersAsync(Auth auth)
    {
        var reply = await ApiCallAsync("servers_and_characters", null, auth);
        if ((string?)reply["reason"] == "not_logged_in")
            throw new InvalidOperationException(
                "not_logged_in: the token in AL_AUTH is not valid. Unset AL_AUTH and log in with the password again.");
        if (reply["failed"] is not null)
            throw new InvalidOperationException($"servers_and_characters failed: {(string?)reply["reason"]}");

        var inf = reply["infs"]?.AsArray()
            .FirstOrDefault(i => (string?)i?["type"] == "servers_and_characters")
            ?? throw new InvalidOperationException("servers_and_characters: no such item in infs");
        var servers = inf["servers"].Deserialize<List<Server>>() ?? [];
        var characters = inf["characters"].Deserialize<List<Character>>() ?? [];
        return (servers, characters);
    }
    // endregion servers-and-characters

    // region find-server
    /// <summary>
    /// The server with region + name equal to key (AL_SERVER, for example "EUI").
    /// An empty key gives the first server: the list is in the order EU, US, ASIA.
    /// </summary>
    public static Server FindServer(List<Server> servers, string? key = null)
    {
        key ??= Environment.GetEnvironmentVariable("AL_SERVER") ?? "";
        if (key == "")
            return servers.FirstOrDefault() ?? throw new InvalidOperationException("the server list is empty");
        return servers.FirstOrDefault(s => s.Id == key)
            ?? throw new InvalidOperationException(
                $"no server {key}; the list has: {string.Join(", ", servers.Select(s => s.Id))}");
    }
    // endregion find-server

    /// <summary>The character with this name (AL_CHARACTER). The name, not the CH_ id.</summary>
    public static Character FindCharacter(List<Character> characters, string? name = null)
    {
        name ??= Environment.GetEnvironmentVariable("AL_CHARACTER") ?? "";
        if (name == "") throw new InvalidOperationException("set AL_CHARACTER to the name of a character");
        return characters.FirstOrDefault(c => c.Name == name)
            ?? throw new InvalidOperationException(
                $"no character {name}; the account has: {string.Join(", ", characters.Select(c => c.Name))}");
    }

    // region socket-url
    /// <summary>
    /// The WebSocket URL of a game server. The scheme follows the website:
    /// http gives ws, https gives wss. The path must end with exactly one "/"
    /// (the server matches "/ws1/"). map_protocol=1 and no_graphics=1 are what the
    /// browser client sends too (js/game.js:1525). Without map_protocol=1, the server
    /// refuses generated maps with "client_update_required".
    /// </summary>
    public static string SocketUrl(Server server, string? baseUrl = null)
    {
        var scheme = (baseUrl ?? BaseUrl()).StartsWith("https:") ? "wss" : "ws";
        var path = server.Path.TrimEnd('/') + "/";
        return $"{scheme}://{server.Address}{path}?EIO=4&transport=websocket&map_protocol=1&no_graphics=1";
    }
    // endregion socket-url
}
