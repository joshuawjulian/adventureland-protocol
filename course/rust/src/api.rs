// api.rs: the HTTP API of the website: log in, list the game servers and your
// characters, and make the WebSocket URL of a game server.
//
// Every call is POST {base}/api/{method} with a JSON body (common_engine
// handlers.js:1). The reply is HTTP 200 with a JSON object, also when the call
// fails: then it has {failed: true, reason}. Extra parts of the reply come in
// the list `infs`.

use std::sync::OnceLock;
use std::time::Duration;

use serde::Deserialize;
use serde_json::{json, Value};

use crate::alsocket::Result;

/// The session: `user` is the account id ("US_..."), `auth` the token.
/// On the wire it is the cookie auth=<user>-<auth>.
#[derive(Debug, Clone)]
pub struct Auth {
    pub user: String,
    pub auth: String,
}

/// One game server (adventure_functions.js:761-776, servers_to_client).
#[derive(Debug, Clone, Deserialize)]
pub struct Server {
    pub region: String, // "EU", "US", "ASIA"
    pub name: String,   // "I", "II", "PVP", ...
    #[serde(default)]
    pub players: u32,
    #[serde(default)]
    pub key: String, // the database id, "SR_EUI" (not the AL_SERVER value)
    pub address: String, // the host (and port) of the WebSocket
    pub path: String,    // the Socket.IO path on that host, "/ws1/"
}

/// One of your characters (adventure_functions.js:821-843, character_to_dict).
#[derive(Debug, Clone, Deserialize)]
pub struct Character {
    pub id: String, // "CH_...": the socket `auth` event needs this, not the name
    pub name: String,
    #[serde(rename = "type")]
    pub ctype: String, // the class. "type" is a Rust keyword, so the field has another name.
    pub level: u32,
    #[serde(default)]
    pub server: Option<String>, // "SR_EUI", only while the character is online
}

/// The two lists of the `servers_and_characters` reply.
#[derive(Debug, Clone, Deserialize)]
pub struct ServersAndCharacters {
    pub servers: Vec<Server>,
    pub characters: Vec<Character>,
}

/// An environment variable, or "" when it is not set.
fn env(name: &str) -> String {
    std::env::var(name).unwrap_or_default()
}

/// AL_BASE_URL or https://adventure.land, without a final "/".
pub fn base_url() -> String {
    let base = env("AL_BASE_URL");
    let base = if base.is_empty() { "https://adventure.land".to_string() } else { base };
    base.trim_end_matches('/').to_string()
}

/// One HTTP client for the whole program: it keeps connections open between calls.
pub(crate) fn http() -> &'static reqwest::Client {
    static CLIENT: OnceLock<reqwest::Client> = OnceLock::new();
    CLIENT.get_or_init(|| {
        reqwest::Client::builder()
            .timeout(Duration::from_secs(60)) // 60 s: G (from gdata) is a few MB on a slow link
            .build()
            .expect("the HTTP client must build")
    })
}

// region api-call
/// POST {base}/api/{method} with a JSON body. With `auth`, the request has the
/// session cookie. An HTTP status other than 200 is an error. The parsed JSON
/// comes back also when it has `failed`: the caller decides what to do.
pub async fn api_call(method: &str, body: Value, auth: Option<&Auth>) -> Result<Value> {
    let mut req = http().post(format!("{}/api/{method}", base_url())).json(&body);
    if let Some(a) = auth {
        req = req.header("Cookie", format!("auth={}-{}", a.user, a.auth));
    }
    let res = req.send().await?;
    if res.status().as_u16() != 200 {
        return Err(format!("{method}: HTTP status {}", res.status()).into());
    }
    Ok(res.json::<Value>().await?)
}
// endregion api-call

/// Splits "<user>-<auth>" at the first "-". The user id has no "-", the token can.
pub fn parse_auth(text: &str) -> Result<Auth> {
    let (user, auth) = text
        .trim()
        .split_once('-')
        .ok_or("the session must look like <user>-<auth>")?;
    Ok(Auth { user: user.to_string(), auth: auth.to_string() })
}

// region login
/// The session. AL_AUTH when it is set: then no password goes over the network.
/// Else one password login with AL_EMAIL and AL_PASSWORD, which prints the
/// value to save as AL_AUTH. Each password login adds a token to the account
/// (the live server keeps at most 200), so do it once.
pub async fn login() -> Result<Auth> {
    let saved = env("AL_AUTH");
    if !saved.is_empty() {
        return parse_auth(&saved);
    }
    let (email, password) = (env("AL_EMAIL"), env("AL_PASSWORD"));
    if email.is_empty() || password.is_empty() {
        return Err("set AL_AUTH, or AL_EMAIL and AL_PASSWORD".into());
    }
    // only_login: true: never make a new account by accident (api.js:84-133).
    let body = json!({"email": email, "password": password, "only_login": true});
    let reply = api_call("signup_or_login", body, None).await?;
    // Success: {success: true, user, auth, ...}. Failure: {failed: true, reason}.
    if reply["success"] != true {
        let reason = reply["reason"].as_str().unwrap_or("no reason in the reply");
        return Err(format!("login failed: {reason}").into());
    }
    let (Some(user), Some(auth)) = (reply["user"].as_str(), reply["auth"].as_str()) else {
        return Err("login failed: the reply has no user or auth".into());
    };
    let value = format!("{user}-{auth}");
    println!("Logged in with the password. Save this value, and use it from now on:");
    println!("  export AL_AUTH='{value}'");
    println!("  PowerShell: $env:AL_AUTH = '{value}'");
    Ok(Auth { user: user.to_string(), auth: auth.to_string() })
}
// endregion login

// region servers-and-characters
/// The game servers and your characters: the `infs` item of type
/// "servers_and_characters" (api.js:451-472).
pub async fn servers_and_characters(auth: &Auth) -> Result<ServersAndCharacters> {
    let reply = api_call("servers_and_characters", json!({}), Some(auth)).await?;
    if reply["reason"] == "not_logged_in" {
        return Err("not_logged_in: the session in AL_AUTH is not valid any more. \
                    Unset AL_AUTH and log in with the password again."
            .into());
    }
    if reply["failed"] == true {
        return Err(format!("servers_and_characters failed: {}", reply["reason"]).into());
    }
    let inf = reply["infs"]
        .as_array()
        .and_then(|infs| infs.iter().find(|i| i["type"] == "servers_and_characters"))
        .ok_or("servers_and_characters: the reply has no servers_and_characters item")?;
    Ok(serde_json::from_value(inf.clone())?) // the two lists into our structs
}
// endregion servers-and-characters

// region find-server
/// The server whose region + name is `key` (for example "EUI"). `None` reads
/// AL_SERVER. An empty key means the first server of the list (EU, US, ASIA).
pub fn find_server(servers: &[Server], key: Option<&str>) -> Result<Server> {
    let key = key.map(String::from).unwrap_or_else(|| env("AL_SERVER"));
    let found = if key.is_empty() {
        servers.first()
    } else {
        servers.iter().find(|s| format!("{}{}", s.region, s.name) == key)
    };
    found.cloned().ok_or_else(|| {
        let names: Vec<String> = servers.iter().map(|s| format!("{}{}", s.region, s.name)).collect();
        format!("no server {key}; the list has: {}", names.join(", ")).into()
    })
}
// endregion find-server

/// The character with exactly this `name` (not the "CH_" id). `None` reads AL_CHARACTER.
pub fn find_character(characters: &[Character], name: Option<&str>) -> Result<Character> {
    let name = name.map(String::from).unwrap_or_else(|| env("AL_CHARACTER"));
    if name.is_empty() {
        return Err("set AL_CHARACTER to the name of your character (the login program lists them)".into());
    }
    characters.iter().find(|c| c.name == name).cloned().ok_or_else(|| {
        let names: Vec<&str> = characters.iter().map(|c| c.name.as_str()).collect();
        format!("no character {name}; the list has: {}", names.join(", ")).into()
    })
}

// region socket-url
/// The full WebSocket URL of a game server. The scheme follows `base`
/// (http -> ws, https -> wss); `None` uses base_url(). The path must end with
/// exactly one "/": the server matches "/ws1/", not "/ws1" or "/ws1//".
/// map_protocol=1 and no_graphics=1 are the options of the browser client
/// (js/game.js:1525): without map_protocol=1 the server refuses the generated
/// maps ("client_update_required").
pub fn socket_url(server: &Server, base: Option<&str>) -> String {
    let base = base.map(String::from).unwrap_or_else(base_url);
    let scheme = if base.starts_with("https") { "wss" } else { "ws" };
    let path = server.path.trim_end_matches('/');
    format!(
        "{scheme}://{}{path}/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1",
        server.address
    )
}
// endregion socket-url
