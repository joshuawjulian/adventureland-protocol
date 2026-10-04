// Cooldowns.cs: when each skill (and the shared potion timer) is ready again.
// The server tells us in three ways; this class listens to all of them.
//
// Threads: the handlers run on the dispatcher thread of AlSocket, and your
// program asks Ready() on another thread. So one lock guards the table.
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Albot;

// region cooldowns
public sealed class Cooldowns
{
    private readonly object _lock = new();
    private readonly Dictionary<string, long> _readyAt = []; // name -> ms (Environment.TickCount64)
    private readonly GData _g;

    /// <summary>
    /// Names are skill names ("attack", "supershot", ...) and "potion" for the
    /// potion timer, which all potions and the free regeneration share.
    /// It listens through world.Listen, so hitchhikers count too.
    /// </summary>
    public Cooldowns(World world)
    {
        _g = world.G;
        // After each skill and attack: {name, ms} (node/server_functions.js:3448-3468, consume_skill).
        world.Listen("skill_timeout", d => Start(d.Str("name") ?? "", d.Num("ms")));
        world.Listen("game_response", d =>
        {
            if (d is not JsonObject) return; // a bare string has no ms
            var code = d.Str("response");
            // Too early: {response: "cooldown", skill, ms}. Some places send no skill.
            if (code == "cooldown") Start(d.Str("skill") ?? d.Str("place") ?? "", d.Num("ms"));
            if (code == "not_ready") Start("potion", d.Num("ms")); // a potion or `use` too early
        });
        world.Listen("eval", d =>
        {
            // eval is code for the browser, as a string or {code}. Two forms set a timer:
            // "pot_timeout(2000)" and "skill_timeout('ethereal',120)".
            var code = d is JsonObject ? d.Str("code") ?? "" : (d as JsonValue)?.ToString() ?? "";
            var pot = Regex.Match(code, @"pot_timeout\((\d+)");
            if (pot.Success) Start("potion", double.Parse(pot.Groups[1].Value));
            var skill = Regex.Match(code, @"skill_timeout\('([^']+)',\s*(\d+)");
            if (skill.Success) Start(skill.Groups[1].Value, double.Parse(skill.Groups[2].Value));
        });
    }

    /// <summary>Not ready for ms from now. A skill with `share` also sets the skill it shares
    /// (G.skills[name].share: for example, the cooldown of 3shot is the attack cooldown).</summary>
    public void Start(string name, double ms)
    {
        var at = Environment.TickCount64 + (long)ms;
        lock (_lock)
        {
            _readyAt[name] = at;
            if (_g.Skills.TryGetValue(name, out var skill) && skill.Share is string share) _readyAt[share] = at;
        }
    }

    public bool Ready(string name) => MsLeft(name) == 0;

    /// <summary>The time until name is ready, in ms. 0 when it is ready.</summary>
    public double MsLeft(string name)
    {
        lock (_lock)
            return _readyAt.TryGetValue(name, out var at) ? Math.Max(0, at - Environment.TickCount64) : 0;
    }
}
// endregion cooldowns
