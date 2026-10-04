// Bot.cs: from nothing to a character in the game. Log in, choose the server
// and the character, load G, open the socket, do the handshake, and make the
// World, Cooldowns, Budget and Actions.
using System.Text.Json;

namespace Albot;

/// <summary>The handshake failed. Reason: the reason of game_error (see ErrorReason),
/// "authorization_in_progress", the text of disconnect_reason, "disconnect" or "timeout".</summary>
public sealed class LoginError(string reason) : Exception($"login failed: {reason}")
{
    public string Reason { get; } = reason;
}

public sealed class Bot
{
    public required AlSocket Sock { get; init; }
    public required GData G { get; init; }
    public required World World { get; init; }
    public required Cooldowns Cooldowns { get; init; }
    public required Budget Budget { get; init; }
    public required Actions Act { get; init; }
    public required Auth Auth { get; init; }
    public required Server Server { get; init; }
    public required Character Character { get; init; }
    /// <summary>The `welcome` payload: region, name, version, ...</summary>
    public required JsonElement Welcome { get; init; }

    // region error-reason
    /// <summary>
    /// The reason of a `game_error` during the handshake. The payload is an object
    /// {message, phrase, phrase_args, reason?} (languages/index.js:256-258):
    /// a refused `auth` has `reason`: "no_character", "password_issue", "mainframe_issue",
    /// "ingame", "poker_hand_active", "cancelled" (node/server.js:11610-11652);
    /// a full server has the phrase "server.game_error.capacity" (node/server.js:11587,
    /// 11879): we call it "server_full"; "server.game_error.characters_unconfirmed": the
    /// server could not read your other characters (node/server.js:11873-11876).
    /// A bare string (for example "ERROR!") is its own reason.
    /// </summary>
    public static string ErrorReason(JsonElement e)
    {
        if (e.ValueKind == JsonValueKind.String) return e.GetString()!;
        if (e.ValueKind != JsonValueKind.Object) return "unknown";
        if (e.TryGetProperty("reason", out var r) && r.ValueKind == JsonValueKind.String) return r.GetString()!;
        var phrase = e.TryGetProperty("phrase", out var p) && p.ValueKind == JsonValueKind.String ? p.GetString()! : null;
        if (phrase == "server.game_error.capacity") return "server_full";
        if (phrase != null) return phrase[(phrase.LastIndexOf('.') + 1)..]; // "characters_unconfirmed"
        return e.TryGetProperty("message", out var m) ? m.ToString() : "unknown";
    }
    // endregion error-reason

    // region enter-game
    /// <summary>
    /// The handshake on a connected socket: wait for `welcome`, send `loaded`, send
    /// `auth`, wait for `start`. Returns the welcome payload. `start` reaches the
    /// World through its handler, so create the World before you call this.
    /// welcomeWait: a WaitForAsync("welcome") that you registered before anything
    /// else (see ConnectAsync). Without it, this method registers its own.
    /// </summary>
    public static async Task<JsonElement> EnterGameAsync(AlSocket sock, Auth auth, string characterId,
        int timeoutMs = 30000, Task<JsonElement>? welcomeWait = null)
    {
        var timeout = TimeSpan.FromMilliseconds(timeoutMs);
        // 1. `welcome`: the server sends it at once after the connect.
        var welcome = await (welcomeWait ?? sock.WaitForAsync("welcome", null, timeout));

        // 2. Listen for each result of `auth` BEFORE we send it. The handlers run on
        //    the dispatcher thread; they only complete this task. TrySet: the first result counts.
        var result = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        void Fail(string reason) => result.TrySetException(new LoginError(reason));
        // The World handler for `start` was registered first, so it runs first:
        // when this task completes, World.Me is ready.
        sock.On("start", _ => result.TrySetResult());
        sock.On("game_error", e => Fail(ErrorReason(e)));
        // The character is still online, or still saving after a disconnect: no
        // `start` will come on this socket (node/server.js:11577-11582).
        sock.On("game_log", m =>
        {
            var text = m.ValueKind == JsonValueKind.Object && m.TryGetProperty("message", out var t) ? t.ToString() : m.ToString();
            if (text.StartsWith("Authorization in progress")) Fail("authorization_in_progress");
        });
        sock.On("disconnect_reason", r => Fail(r.ToString()));
        sock.On("disconnect", _ => Fail("disconnect")); // the local event of AlSocket

        // 3. `loaded`. The server reads none of these fields, but it ignores `auth`
        //    until `loaded` made an observer for this socket (node/server.js:5028-5054, 11583).
        await sock.EmitAsync("loaded", new { success = 1, width = 1920, height = 1080, scale = 2 });
        // 4. `auth`. character is the id (CH_...), not the name.
        await sock.EmitAsync("auth", new
        {
            user = auth.User,
            auth = auth.Token,
            character = characterId,
            no_html = "1",   // "a program controls this character": the server sets afk to "code"
            passphrase = "", // only test servers check it
        });

        // 5. `start`, a failure, or the timeout.
        if (await Task.WhenAny(result.Task, Task.Delay(timeout)) != result.Task) throw new LoginError("timeout");
        await result.Task; // throws the LoginError of a failure
        return welcome;
    }
    // endregion enter-game

    // region connect
    /// <summary>Everything from the environment variables to a character in the game.</summary>
    public static async Task<Bot> ConnectAsync()
    {
        var auth = await Api.LoginAsync();
        var (servers, characters) = await Api.ServersAndCharactersAsync(auth);
        var server = Api.FindServer(servers);
        var character = Api.FindCharacter(characters);
        var g = await GData.LoadGAsync();
        return await ConnectWithAsync(auth, server, character, g);
    }

    /// <summary>
    /// The steps after the HTTP calls: the socket, the World, the handshake and the
    /// other parts. Part 3 calls it for each character of a party, with one login,
    /// one server list and one G for all of them.
    /// </summary>
    public static async Task<Bot> ConnectWithAsync(Auth auth, Server server, Character character, GData g)
    {
        var sock = await AlSocket.ConnectAsync(Api.SocketUrl(server));
        // Wait for `welcome` first. AlSocket keeps the events that come before the
        // FIRST subscription of any name. The reader runs on its own thread, so
        // `welcome` can arrive after the World subscribes below: then no one would keep it.
        var welcomeWait = sock.WaitForAsync("welcome", null, TimeSpan.FromSeconds(30));
        // The World before `loaded` and `auth`, so that it sees `start` and every update.
        var world = new World(sock, g);
        JsonElement welcome;
        try { welcome = await EnterGameAsync(sock, auth, character.Id, 30000, welcomeWait); }
        catch
        {
            await sock.CloseAsync();
            throw;
        }
        var cooldowns = new Cooldowns(world);
        var budget = new Budget(sock, world);
        return new Bot
        {
            Sock = sock, G = g, World = world, Cooldowns = cooldowns, Budget = budget,
            Act = new Actions(sock, world, cooldowns, budget),
            Auth = auth, Server = server, Character = character, Welcome = welcome,
        };
    }
    // endregion connect

    /// <summary>Closes the socket. The server then saves the character.</summary>
    public Task CloseAsync() => Sock.CloseAsync();

    // region reconnect-delay
    /// <summary>
    /// The one reconnect rule. After a disconnect, the server keeps the character
    /// until its save ends, and a new `auth` gets "Authorization in progress"
    /// (node/server.js:11577-11582, :13055, :16812). So wait AL_RECONNECT_MS (30 s)
    /// before the first try (attempt 0), double the wait after each failed try, at
    /// most 300 s. Start again from attempt 0 after a session of 5 minutes.
    /// </summary>
    public static int ReconnectDelayMs(int attempt)
    {
        var text = Environment.GetEnvironmentVariable("AL_RECONNECT_MS");
        var first = int.TryParse(text, out var ms) && ms > 0 ? ms : 30000;
        const int Max = 300000; // 5 minutes
        return (int)Math.Min(first * Math.Pow(2, Math.Max(attempt, 0)), Max);
    }
    // endregion reconnect-delay
}
