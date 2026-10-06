// connect.rs: log in, connect to a game server, do the handshake, and enter
// the game with one character. Then close.
//   Run: AL_AUTH=<user>-<auth> AL_CHARACTER=<name> cargo run --bin connect
//   AL_SERVER (for example EUI) is optional: empty means the first server.
use albot::bot::Bot;
use albot::world::{num, text};
use albot::Result;

#[tokio::main]
async fn main() -> Result<()> {
    let bot = Bot::connect().await?;
    let w = &bot.welcome;
    println!(
        "welcome: {} {}, version {}",
        w["region"].as_str().unwrap_or("?"),
        w["name"].as_str().unwrap_or("?"),
        w["version"]
    );

    let me = bot.world.me(); // `start` has no `name`: the name is `id`
    println!(
        "in game as {} ({}, level {}) on {} at {:.0},{:.0}",
        text(&me, "id"),
        text(&me, "ctype"),
        num(&me, "level"),
        text(&me, "map"),
        num(&me, "x"),
        num(&me, "y")
    );
    println!("OK");
    bot.close().await // the server then saves the character and marks it offline
}
