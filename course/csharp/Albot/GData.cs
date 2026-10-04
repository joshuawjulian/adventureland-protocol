// GData.cs: the game data G. Download it once per game version, keep it in a
// cache file, and read it as typed data.
// G is about 3 MB of JSON. The website serves it as /data.js: "var G={...};".
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace Albot;

// region types
// Typed views of the parts of G that the course reads. Only these fields: the
// serializer skips the others. All of G stays in GData.Raw as JSON.

/// <summary>G.items[name].</summary>
public sealed record ItemDef(
    [property: JsonPropertyName("name")] string Name, // the display name, "HP Potion"
    [property: JsonPropertyName("type")] string Type, // "weapon", "pot", "material", ...
    [property: JsonPropertyName("g")] double G,       // the value in gold (also the NPC price)
    [property: JsonPropertyName("gives")] JsonElement[][]? Gives, // potions: [stat, amount] pairs
    [property: JsonPropertyName("cooldown")] double? Cooldown);   // potions: the potion timer, ms

/// <summary>G.monsters[type].</summary>
public sealed record MonsterDef(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("hp")] double Hp,
    [property: JsonPropertyName("attack")] double Attack,
    [property: JsonPropertyName("speed")] double Speed,         // px per second
    [property: JsonPropertyName("range")] double Range,         // px
    [property: JsonPropertyName("frequency")] double Frequency, // attacks per second
    [property: JsonPropertyName("xp")] double Xp,
    [property: JsonPropertyName("respawn")] double Respawn,     // SECONDS; -1 = never by itself
    [property: JsonPropertyName("damage_type")] string? DamageType,
    [property: JsonPropertyName("size")] double? Size);         // scales the hitbox, if set

/// <summary>G.skills[name].</summary>
public sealed record SkillDef(
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("cooldown")] double? Cooldown, // ms
    [property: JsonPropertyName("mp")] double? Mp,
    [property: JsonPropertyName("range")] double? Range,
    [property: JsonPropertyName("share")] string? Share);      // uses the cooldown of this other skill

/// <summary>
/// The game data: the typed tables. The static methods below load it. (C# cannot
/// have a static class GData and a type GData at the same time, so this one class
/// is both, written in two parts.)
/// </summary>
public sealed partial class GData
{
    [JsonPropertyName("version")] public int Version { get; init; }
    [JsonPropertyName("items")] public Dictionary<string, ItemDef> Items { get; init; } = [];
    [JsonPropertyName("monsters")] public Dictionary<string, MonsterDef> Monsters { get; init; } = [];
    [JsonPropertyName("skills")] public Dictionary<string, SkillDef> Skills { get; init; } = [];
    // type -> [width, height, ...]: the hitbox of a monster (js/old_common_functions.js:692).
    [JsonPropertyName("dimensions")] public Dictionary<string, double[]> Dimensions { get; init; } = [];

    /// <summary>All of G as JSON: maps, geometry, npcs, classes, ...</summary>
    [JsonIgnore] public JsonObject Raw { get; private set; } = [];

    /// <summary>Reads G from its JSON text.</summary>
    public static GData Parse(string json)
    {
        var g = JsonSerializer.Deserialize<GData>(json) ?? throw new InvalidDataException("G is null");
        g.Raw = JsonNode.Parse(json)!.AsObject();
        return g;
    }
}
// endregion types

// The static part: load G.
public sealed partial class GData
{
    // region fetch-version
    /// <summary>
    /// The version of the game now: the hub page has var VERSION='17478'
    /// (htmls/base_script.html:32). null if the page does not have it.
    /// </summary>
    public static async Task<int?> FetchVersionAsync(string baseUrl)
    {
        var html = await Api.Http.GetStringAsync($"{baseUrl}/hub");
        var m = Regex.Match(html, @"var\s+VERSION\s*=\s*'(\d+)'");
        return m.Success ? int.Parse(m.Groups[1].Value) : null;
    }
    // endregion fetch-version

    // region download-g
    /// <summary>Downloads G. /data.js is "var G={...};": the JSON is from the first { to the last }.</summary>
    public static async Task<GData> DownloadGAsync(string baseUrl) => Parse(await DownloadTextAsync(baseUrl));

    private static async Task<string> DownloadTextAsync(string baseUrl)
    {
        var js = await Api.Http.GetStringAsync($"{baseUrl}/data.js");
        int first = js.IndexOf('{'), last = js.LastIndexOf('}');
        if (first < 0 || last < first) throw new InvalidDataException("data.js has no JSON object");
        return js[first..(last + 1)];
    }
    // endregion download-g

    /// <summary>
    /// The cache file: .al-cache/&lt;host&gt;/G_&lt;version&gt;.json. host is the host and
    /// port of the website with ":" as "_", so that the G of the test server never
    /// mixes with the live G.
    /// </summary>
    public static string CachePath(string baseUrl, int version)
    {
        var uri = new Uri(baseUrl);
        var host = uri.IsDefaultPort ? uri.Host : $"{uri.Host}_{uri.Port}";
        return Path.Combine(".al-cache", host, $"G_{version}.json");
    }

    // region load-g
    /// <summary>
    /// G from the cache when the cache has this version. Else download it, save it
    /// and say so. The download is about 3 MB; the version check is a small page.
    /// </summary>
    public static async Task<GData> LoadGAsync(string? baseUrl = null)
    {
        baseUrl ??= Api.BaseUrl();
        var version = await FetchVersionAsync(baseUrl);
        if (version is int v && File.Exists(CachePath(baseUrl, v)))
            return Parse(await File.ReadAllTextAsync(CachePath(baseUrl, v)));

        var json = await DownloadTextAsync(baseUrl);
        var g = Parse(json);
        var path = CachePath(baseUrl, g.Version); // the version in G itself
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        await File.WriteAllTextAsync(path, json);
        Console.WriteLine($"downloaded G version {g.Version}");
        return g;
    }
    // endregion load-g
}
