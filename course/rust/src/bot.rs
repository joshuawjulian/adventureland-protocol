// bot.rs: connect everything: log in, choose the server and the character,
// load G, open the socket, do the handshake, and make the world, cooldowns,
// budget and actions. A program calls Bot::connect() and then plays.

use std::sync::Arc;
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use crate::actions::Actions;
use crate::alsocket::{AlSocket, Result};
use crate::api::{self, Auth, Character, Server};
use crate::budget::Budget;
use crate::cooldowns::Cooldowns;
use crate::gdata::{self, GData};
use crate::world::World;

/// The game did not let the character in. `reason` is the server's reason
/// ("password_issue", "ingame", ...), "server_full", "characters_unconfirmed",
/// "authorization_in_progress", the text of `disconnect_reason` or
/// `disconnect`, or "timeout".
#[derive(Debug, Clone)]
pub struct LoginError {
    pub reason: String,
}

impl std::fmt::Display for LoginError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "login failed: {}", self.reason)
    }
}

impl std::error::Error for LoginError {}

fn login_error(reason: impl Into<String>) -> LoginError {
    LoginError { reason: reason.into() }
}

// region error-reason
/// The reason of a `game_error` during the handshake. The payload is an object
/// {message, phrase, phrase_args, reason?} (languages/index.js:256-258):
/// - a refused `auth` has `reason`: "no_character", "password_issue",
///   "mainframe_issue", "ingame", "poker_hand_active", "cancelled"
///   (node/server.js:11610-11652);
/// - a full server has the phrase "server.game_error.capacity"
///   (node/server.js:11587, 11879): we call it "server_full";
/// - "server.game_error.characters_unconfirmed": the server could not read
///   your other characters (node/server.js:11873-11876). Try again later.
///
/// A bare string (for example "ERROR!") is its own reason.
pub fn error_reason(e: &Value) -> String {
    if let Some(text) = e.as_str() {
        return text.to_string();
    }
    if let Some(reason) = e["reason"].as_str() {
        return reason.to_string();
    }
    match e["phrase"].as_str() {
        Some("server.game_error.capacity") => "server_full".to_string(),
        // "server.game_error.characters_unconfirmed" -> "characters_unconfirmed"
        Some(phrase) => phrase.rsplit('.').next().unwrap_or(phrase).to_string(),
        None => e["message"].as_str().unwrap_or("unknown").to_string(),
    }
}
// endregion error-reason

// region enter-game
/// The handshake on a connected socket. Returns the `welcome` payload.
///
/// 1. Wait for `welcome`: the server sends it at once.
/// 2. Send `loaded`. The server ignores `auth` until `loaded` made an
///    observer for this socket (node/server.js:5028-5054, 11583-11585).
/// 3. Send `auth`. `character` is the id ("CH_..."), not the name.
/// 4. Wait for `start`, or one of the failures.
///
/// Create the World before you call this: its handlers must see `start`.
/// `timeout_ms`: None is 30 s.
///
/// `welcome`: the payload, if you already waited for it (Bot::connect does).
/// AlSocket keeps early events only until the first on/wait_for of ANY name.
/// World subscribes to its events, so a `welcome` that arrives after that is
/// lost. Wait for `welcome` before you create World, and give it here.
pub async fn enter_game(
    sock: &AlSocket,
    auth: &Auth,
    character_id: &str,
    timeout_ms: Option<u64>,
    welcome: Option<Value>,
) -> std::result::Result<Value, LoginError> {
    let deadline = Instant::now() + Duration::from_millis(timeout_ms.unwrap_or(30_000));
    let left = || deadline.saturating_duration_since(Instant::now());
    let welcome = match welcome {
        Some(welcome) => welcome,
        None => sock
            .wait_for_timeout("welcome", |_| true, left())
            .await
            .map_err(|_| login_error("timeout"))?,
    };

    // Register every wait before the first send (the reply can be fast).
    let start = sock.wait_for_timeout("start", |_| true, left());
    let error = sock.wait_for_timeout("game_error", |_| true, left());
    // "Authorization in progress": the character is still online, or its save
    // after a disconnect still runs (node/server.js:11577-11582). No `start` comes.
    let busy = sock.wait_for_timeout(
        "game_log",
        |d| d["phrase"] == "server.game_log.authorization_in_progress"
            || d.as_str().or(d["message"].as_str()).is_some_and(|m| m.starts_with("Authorization in progress")),
        left(),
    );
    let reason = sock.wait_for_timeout("disconnect_reason", |_| true, left());
    let gone = sock.wait_for_timeout("disconnect", |_| true, left()); // AlSocket's local event

    let sent = async {
        // The server reads none of these fields (node/server.js:5028-5054); the browser sends them.
        sock.emit("loaded", json!({"success": 1, "width": 1920, "height": 1080, "scale": 2})).await?;
        sock.emit("auth", json!({
            "user": auth.user,
            "auth": auth.auth,
            "character": character_id,
            "no_html": "1",   // "a program plays this character": the server sets afk to "code"
            "passphrase": "", // only test servers check it
        }))
        .await
    };
    sent.await.map_err(|e| login_error(format!("disconnect: {e}")))?;

    // The first result wins. A wait that fails (timeout, or the socket closed)
    // turns its branch off; when all are off, it was the timeout.
    // `biased`: check in this order, so that disconnect_reason ("limitdc")
    // wins over the plain disconnect that follows it.
    tokio::select! {
        biased;
        Ok(_) = start => Ok(welcome),
        Ok(e) = error => Err(login_error(error_reason(&e))),
        Ok(_) = busy => Err(login_error("authorization_in_progress")),
        Ok(r) = reason => Err(login_error(r.as_str().unwrap_or("disconnect_reason"))),
        Ok(r) = gone => Err(login_error(r.as_str().unwrap_or("disconnect"))),
        else => Err(login_error("timeout")),
    }
}
// endregion enter-game

/// A character in the game, with everything that it needs.
pub struct Bot {
    pub sock: Arc<AlSocket>,
    pub g: Arc<GData>, // G (Rust field names are lower case)
    pub world: World,
    pub cooldowns: Cooldowns,
    pub budget: Budget,
    pub act: Actions,
    pub auth: Auth,
    pub server: Server,
    pub character: Character,
    pub welcome: Value,
}

impl Bot {
    // region connect
    /// Log in, choose the server (AL_SERVER) and the character (AL_CHARACTER),
    /// load G, connect, and enter the game.
    pub async fn connect() -> Result<Bot> {
        let auth = api::login().await?;
        let lists = api::servers_and_characters(&auth).await?;
        let server = api::find_server(&lists.servers, None)?;
        let character = api::find_character(&lists.characters, None)?;
        let g = Arc::new(gdata::load_g(None).await?);
        Bot::connect_with(auth, server, character, g).await
    }

    /// The steps after the HTTP calls: the socket, the World, the handshake and
    /// the other parts. Part 3 calls it for each character of a party, with one
    /// login, one server list and one G for all of them.
    pub async fn connect_with(auth: Auth, server: Server, character: Character, g: Arc<GData>) -> Result<Bot> {
        let sock = Arc::new(AlSocket::connect(&api::socket_url(&server, None)).await?);
        // `welcome` first, before World subscribes to anything: AlSocket keeps
        // early events only until the first on/wait_for (the welcome race).
        let welcome = match sock.wait_for("welcome", |_| true).await {
            Ok(welcome) => welcome,
            Err(e) => {
                let _ = sock.close().await;
                return Err(e);
            }
        };
        // Then the world: its handlers must be in place before `loaded`.
        let world = World::new(sock.clone(), g.clone());
        let welcome = match enter_game(&sock, &auth, &character.id, None, Some(welcome)).await {
            Ok(welcome) => welcome,
            Err(e) => {
                let _ = sock.close().await; // do not leave the socket open
                return Err(e.into());
            }
        };
        let cooldowns = Cooldowns::new(&world);
        let budget = Budget::new(sock.clone(), &world);
        let act = Actions::new(sock.clone(), world.clone(), cooldowns.clone(), budget.clone());
        Ok(Bot { sock, g, world, cooldowns, budget, act, auth, server, character, welcome })
    }
    // endregion connect

    /// Close the socket. The server then saves the character.
    pub async fn close(&self) -> Result<()> {
        self.sock.close().await
    }
}

// region reconnect-delay
/// The wait before reconnect try number `attempt` (0 = the first try), in ms.
///
/// Do not reconnect at once: after a disconnect, the server keeps the character
/// until its save ends, and a new `auth` gets "Authorization in progress"
/// (node/server.js:11577-11582, :13055, :16812). So wait AL_RECONNECT_MS
/// (default 30 s), double the wait after each failed try, at most 300 s.
/// After a session that lasted 5 minutes, start again from attempt 0.
/// Always close the old socket, make a new AlSocket, and do the full handshake.
pub fn reconnect_delay_ms(attempt: u32) -> u64 {
    let first: u64 = std::env::var("AL_RECONNECT_MS")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(30_000);
    let doubled = first.saturating_mul(1u64 << attempt.min(20)); // min: no overflow of the shift
    doubled.min(300_000) // 300 s: the longest wait
}
// endregion reconnect-delay
