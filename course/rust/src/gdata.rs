// gdata.rs: the game data G: download it once per version, keep it on disk,
// and read it as typed structs.
//
// G is one large JSON object (about 2.8 MB) with the static rules of the game.
// The structs below type only the fields that the course reads. All other
// tables stay in `GData::other` as raw JSON.

use std::collections::HashMap;
use std::path::PathBuf;

use serde::Deserialize;
use serde_json::{Map, Value};

use crate::alsocket::Result;
use crate::api::{base_url, http};

// region types
/// G.items[name]. Every field has a default, so one odd entry cannot stop the parse.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct ItemDef {
    pub name: String, // the display name, "HP Potion"
    #[serde(rename = "type")]
    pub kind: String, // "weapon", "pot", ... ("type" is a Rust keyword)
    pub g: f64,         // the base value in gold (also the NPC price)
    pub s: Option<f64>, // the stack size; None: the item does not stack
    pub gives: Vec<(String, f64)>, // potions: [stat, amount] pairs, [["hp", 200]]
    pub cooldown: Option<f64>,     // ms (potions)
    /// The stats that each compound level adds. Some: the item compounds (jewelry).
    pub compound: Option<HashMap<String, f64>>,
    /// The stats that each upgrade level adds. Some: the item upgrades.
    pub upgrade: Option<HashMap<String, f64>>,
}

/// G.monsters[type]. Use f64 for all numbers: some are integers in one entry
/// and decimals in another (frequency, respawn).
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct MonsterDef {
    pub name: String,
    pub hp: f64,
    pub attack: f64,
    pub speed: f64,     // px per second
    pub range: f64,     // px
    pub frequency: f64, // attacks per second
    pub xp: f64,
    pub respawn: f64, // SECONDS (most durations are ms); -1: never by itself
    pub size: Option<f64>, // a multiplier of the hit box (G.dimensions)
}

/// G.skills[name]. Every field is optional. `target` is not typed: it is a
/// boolean in some entries and a string in others.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct SkillDef {
    pub name: Option<String>,
    pub cooldown: Option<f64>, // ms
    pub mp: Option<f64>,
    pub range: Option<f64>,
    pub share: Option<String>, // this skill uses the cooldown of that skill
    pub level: Option<f64>,
}

/// G: the typed tables, plus all other tables as raw JSON.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct GData {
    pub version: u64,
    pub items: HashMap<String, ItemDef>,
    pub monsters: HashMap<String, MonsterDef>,
    pub skills: HashMap<String, SkillDef>,
    /// Hit boxes: type -> [width, height, ...] (js/old_common_functions.js:692).
    #[serde(default)]
    pub dimensions: HashMap<String, Vec<f64>>,
    /// Every other table (maps, geometry, npcs, classes, levels, ...).
    #[serde(flatten)]
    pub other: Map<String, Value>,
}
// endregion types

// region fetch-version
/// The version of G on the server: the page /hub has var VERSION='<n>'
/// (htmls/base_script.html:32). None when the page or the line is missing.
/// Ask for /hub directly: the old /comm is a redirect (main.js:167).
pub async fn fetch_version(base: &str) -> Option<u64> {
    let res = http().get(format!("{base}/hub")).send().await.ok()?;
    let html = res.text().await.ok()?;
    // A plain string search (no regex crate): find the marker, take the digits after it.
    let rest = &html[html.find("var VERSION")?..];
    let digits: String = rest
        .chars()
        .skip_while(|c| !c.is_ascii_digit())
        .take_while(|c| c.is_ascii_digit())
        .collect();
    digits.parse().ok()
}
// endregion fetch-version

// region download-g
/// Download G as raw JSON. /data.js is "var G={...};" (web_assets.js:52), so the
/// JSON is the text from the first "{" to the last "}".
pub async fn download_g(base: &str) -> Result<Value> {
    let res = http().get(format!("{base}/data.js")).send().await?.error_for_status()?;
    let js = res.text().await?;
    let start = js.find('{').ok_or("data.js has no {")?;
    let end = js.rfind('}').ok_or("data.js has no }")?;
    Ok(serde_json::from_str(&js[start..=end])?)
}
// endregion download-g

/// The cache file: .al-cache/<host>/G_<version>.json. <host> is the host and
/// port of `base` with ":" changed to "_", so that the G of the test server
/// never mixes with the live G.
pub fn cache_path(base: &str, version: u64) -> PathBuf {
    let host = base.split("://").last().unwrap_or(base); // without "https://"
    let host = host.split('/').next().unwrap_or(host).replace(':', "_");
    PathBuf::from(".al-cache").join(host).join(format!("G_{version}.json"))
}

// region load-g
/// G from the cache when the file of this version exists. Else download it,
/// save it, and print "downloaded G version <n>". `None` uses base_url().
/// When /hub has no version, G downloads each time: slow, but correct.
pub async fn load_g(base: Option<&str>) -> Result<GData> {
    let base = base.map(String::from).unwrap_or_else(base_url);
    if let Some(version) = fetch_version(&base).await {
        if let Ok(text) = std::fs::read_to_string(cache_path(&base, version)) {
            return Ok(serde_json::from_str(&text)?);
        }
    }
    let raw = download_g(&base).await?;
    let version = raw["version"].as_u64().ok_or("G has no version")?;
    let path = cache_path(&base, version);
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    std::fs::write(&path, serde_json::to_string(&raw)?)?;
    println!("downloaded G version {version}");
    Ok(serde_json::from_value(raw)?)
}
// endregion load-g
