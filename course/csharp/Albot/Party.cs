// Party.cs: several characters in one program, a party, and a new character.
//
// The program logs in once, reads the server and character lists once and
// loads G once. Then ConnectMemberAsync opens one socket for each character.
// Each character has its own World, Cooldowns, Budget and Actions: the server
// counts the call-cost for each socket.
//
// Threads: the handlers of Party run on the dispatcher thread; its state is
// behind its own lock (_lock). No lock is held while we send.
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Albot;

// region member
/// <summary>One character in the game: the same parts as a Bot. (Bot has no
/// public constructor for parts, so a team uses this class.)</summary>
public sealed class Member
{
    public required string Name { get; init; }
    public required AlSocket Sock { get; init; }
    public required GData G { get; init; }
    public required World World { get; init; }
    public required Cooldowns Cooldowns { get; init; }
    public required Budget Budget { get; init; }
    public required Actions Act { get; init; }
    public required Character Character { get; init; }

    public Task CloseAsync() => Sock.CloseAsync();
}

public static class Team
{
    /// <summary>
    /// Connects one character with a login, a server and a G that we already have:
    /// Bot.ConnectWithAsync (Bot.ConnectAsync without the HTTP calls).
    /// </summary>
    public static async Task<Member> ConnectMemberAsync(Auth auth, Server server, Character character, GData g)
    {
        var bot = await Bot.ConnectWithAsync(auth, server, character, g);
        return new Member
        {
            Name = character.Name, Sock = bot.Sock, G = g, World = bot.World, Cooldowns = bot.Cooldowns,
            Budget = bot.Budget, Act = bot.Act, Character = character,
        };
    }

    // endregion member

    // region create-character
    /// <summary>
    /// Makes a new character on the account: HTTP `create_character` {name, char}
    /// (api.js:474-588). The name: 4 to 12 letters, digits or "_", not used by
    /// anyone (api.js:24-31). The answer is {success: true}; a failure throws with
    /// its reason: "name_used", "invalid_name", "reached_character_limit", ...
    /// </summary>
    public static async Task<JsonObject> CreateCharacterAsync(Auth auth, string name, string ctype)
    {
        var r = await Api.ApiCallAsync("create_character", new { name, @char = ctype }, auth);
        if (r.Bool("failed")) throw new InvalidOperationException($"create_character failed: {r.Str("reason")}");
        return r;
    }
    // endregion create-character
}

// region party
/// <summary>
/// The party of one character. The server sends `invite` {name} to the character
/// that gets an invitation, and `party_update` {list, party} to each member when
/// the party changes (node/server.js:12357-12546).
/// </summary>
public sealed class Party
{
    private readonly Actions _act;
    private readonly object _lock = new();
    private List<string> _list = [];
    private readonly HashSet<string> _invites = []; // who invited us

    public Party(World world, Actions act)
    {
        _act = act;
        world.Listen("invite", d => { if (d.Str("name") is string n) lock (_lock) _invites.Add(n); });
        // {} (no list) when we left or the party ended.
        world.Listen("party_update", d =>
        {
            var list = (d?["list"] as JsonArray ?? []).Select(x => x?.GetValue<string>() ?? "").ToList();
            lock (_lock) _list = list;
        });
    }

    /// <summary>The names in our party, the leader first.</summary>
    public List<string> List { get { lock (_lock) return [.. _list]; } }

    /// <summary>Invites name (a character on this server). The answer is a success
    /// with place "party", or "invalid" (no such character), "party_full".</summary>
    public Task<GameResponse?> InviteAsync(string name) => _act.RequestAsync("party", new { @event = "invite", name });

    /// <summary>Accepts the invitation of name. It fails with "invitation_expired"
    /// when there was no invitation.</summary>
    public Task<GameResponse?> AcceptAsync(string name) => _act.RequestAsync("party", new { @event = "accept", name });

    public Task<GameResponse?> LeaveAsync() => _act.RequestAsync("party", new { @event = "leave" });

    /// <summary>Waits until name invited us (true), or ms passed (false).</summary>
    public async Task<bool> WaitInviteAsync(string name, int ms = 5000)
    {
        var end = Environment.TickCount64 + ms;
        while (true)
        {
            lock (_lock) if (_invites.Contains(name)) return true;
            if (Environment.TickCount64 >= end) return false;
            await Task.Delay(50);
        }
    }
}
// endregion party
