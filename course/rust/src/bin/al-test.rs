// al-test.rs: take AlSocket through the game handshake on the local test
// server: welcome, loaded, auth, start. Then idle 3 s (pings must get pongs)
// and check that the socket still works.
//   Run: cargo run --bin al-test
//   Uses only albot::alsocket (Part 1 has no HTTP code yet).
//   AL_WS_URL: the full WebSocket URL of a game server (default: the test server's EU I).
use std::time::Duration;

use albot::alsocket::{AlSocket, Result};
use serde::Deserialize;
use serde_json::json;

// HARD-CODED: the fixed account of the local test server (course/test-server/accounts.js).
// Part 1 has no login code yet, so the test uses these values. They are not
// secret: they exist only on the test server. Never put a real login in code.
const TEST_USER: &str = "US_tester";
const TEST_AUTH: &str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
const TEST_CHARACTER: &str = "CH_tester"; // the id, not the name

// Only the fields that this test reads. The real payloads have many more.
#[derive(Deserialize)]
struct Welcome {
    region: String,
    name: String,
    version: u64,
}
#[derive(Deserialize)]
struct Entities {
    monsters: Vec<serde_json::Value>,
}
#[derive(Deserialize)]
struct Start {
    id: String, // the character name: `start` has no `name` field
    map: String,
    x: f64,
    y: f64,
}

#[tokio::main]
async fn main() -> Result<()> {
    let url = std::env::var("AL_WS_URL").unwrap_or_default();
    let url = if url.is_empty() {
        "ws://localhost:8022/ws1/?EIO=4&transport=websocket".to_string()
    } else {
        url
    };

    let sock = AlSocket::connect(&url).await?;
    println!("connected to {url}");

    // 1. The server sends "welcome" to each new socket. AlSocket keeps it for
    //    us, but only until the first on/wait_for of any name: so wait for it
    //    before the on() calls below.
    let welcome: Welcome = serde_json::from_value(sock.wait_for("welcome", |_| true).await?)?;
    println!("welcome: {} {}, version {}", welcome.region, welcome.name, welcome.version);
    sock.on("game_error", |msg| println!("game_error: {msg}"));
    sock.on("disconnect", |reason| println!("disconnect: {}", reason.as_str().unwrap_or("?")));

    // 2. Send "loaded". The reply is one full "entities" view (type "all").
    //    Register the wait BEFORE the emit, so that a fast reply cannot pass first.
    let view = sock.wait_for("entities", |d| d["type"] == "all");
    sock.emit("loaded", json!({"success": 1, "width": 1920, "height": 1080, "scale": 2}))
        .await?;
    let view: Entities = serde_json::from_value(view.await?)?;
    println!("entities: {} monster(s)", view.monsters.len());

    // 3. Log in the test character.
    let started = sock.wait_for("start", |_| true);
    sock.emit(
        "auth",
        json!({
            "user": TEST_USER,
            "auth": TEST_AUTH,
            "character": TEST_CHARACTER,
            "no_html": "1",   // "a program plays this character"
            "passphrase": "", // only test servers check it
        }),
    )
    .await?;
    let me: Start = serde_json::from_value(started.await?)?;
    println!("start: {} on {} at {:.0},{:.0}", me.id, me.map, me.x, me.y);

    // 4. Do nothing for 3 s. The server pings during this time. If our pong
    //    does not work, the server drops us and the next step fails.
    tokio::time::sleep(Duration::from_secs(3)).await;
    let ack = sock.wait_for("ping_ack", |d| d["id"] == "42");
    sock.emit("ping_trig", json!({"id": "42"})).await?;
    println!("ping_ack after 3 s idle: {}", ack.await?["id"].as_str().unwrap_or("?"));

    println!("OK");
    // close() returns after the "disconnect" handler above printed its line.
    sock.close().await?;
    Ok(())
}
