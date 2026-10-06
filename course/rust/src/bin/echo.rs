// echo.rs: open a plain WebSocket, send one text message, read the reply.
// It does not use the albot library: it tests the WebSocket package alone.
//   Run: cargo run --bin echo
//   Needs tokio, tokio-tungstenite and futures-util (see Cargo.toml).
//   AL_ECHO_URL: the echo server (default: the one of the local test server).
use futures_util::{SinkExt, StreamExt};
use tokio_tungstenite::{connect_async, tungstenite::Message};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let url = std::env::var("AL_ECHO_URL").unwrap_or_default();
    let url = if url.is_empty() { "ws://localhost:8022/echo".to_string() } else { url };

    let (mut ws, _response) = connect_async(url.as_str()).await?;
    println!("connected");

    // One text frame.
    ws.send(Message::Text("hello".into())).await?;

    // .await gives the thread back to tokio until a message arrives.
    match ws.next().await {
        Some(msg) => println!("received: {}", msg?.to_text()?),
        None => return Err("the server closed the connection without a reply".into()),
    }

    // A normal close: we send a close frame, the server answers with one.
    ws.close(None).await?;
    println!("closed");
    Ok(())
}
