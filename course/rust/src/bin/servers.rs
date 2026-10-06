// servers.rs: get the list of game servers over HTTP and print the WebSocket
// URL of each one. It does not use the albot library: it is the first test of
// a new project (do HTTP and JSON work?).
//   Run: cargo run --bin servers
//   Needs reqwest (json), serde (derive) and tokio (see Cargo.toml).
//   AL_BASE_URL: the website (default https://adventure.land).
use serde::Deserialize;

// The shape of the reply (api.js:884-900). Only the fields that we use;
// serde ignores the others.
#[derive(Deserialize)]
struct Server {
    region: String,  // "EU", "US", "ASIA"
    name: String,    // "I", "II", "PVP", ...
    address: String, // the host (and port) of the game server
    path: String,    // the Socket.IO path on that host, "/ws1/"
}

#[derive(Deserialize)]
struct ServerList {
    servers: Vec<Server>,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let base = std::env::var("AL_BASE_URL").unwrap_or_default();
    let base = if base.is_empty() { "https://adventure.land" } else { base.trim_end_matches('/') };

    let res = reqwest::get(format!("{base}/api/get_servers")).await?;
    let content_type = res.headers().get("content-type").and_then(|v| v.to_str().ok()).unwrap_or("");
    println!("status: {} {content_type}", res.status().as_u16());
    let res = res.error_for_status()?; // an error for a 4xx or 5xx status

    let list: ServerList = res.json().await?; // parse the body into the structs
    // The socket scheme follows the website: http -> ws, https -> wss.
    let scheme = if base.starts_with("https") { "wss" } else { "ws" };
    for s in list.servers {
        // The path must end with exactly one "/" (the server matches "/ws1/").
        let path = s.path.trim_end_matches('/');
        // map_protocol=1 and no_graphics=1: the options of the browser client (js/game.js:1525).
        let url = format!(
            "{scheme}://{}{path}/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1",
            s.address
        );
        println!("{} {}: {url}", s.region, s.name);
    }
    Ok(())
}
