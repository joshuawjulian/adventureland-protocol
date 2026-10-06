// login.rs: log in over HTTP, then list the game servers and your characters,
// with the values to use for AL_SERVER and AL_CHARACTER.
//   First run:  AL_EMAIL=you@example.com AL_PASSWORD=... cargo run --bin login
//   Later runs: AL_AUTH=<user>-<auth> cargo run --bin login   (the first run prints this value)
//   AL_BASE_URL: the website (default https://adventure.land).
use albot::api;
use albot::Result;

#[tokio::main]
async fn main() -> Result<()> {
    let auth = api::login().await?; // AL_AUTH, or one password login
    println!("user id: {}", auth.user);
    let lists = api::servers_and_characters(&auth).await?;

    // AL_SERVER is region + name, for example "EUI". (`key`, "SR_EUI", is the database id.)
    println!("servers (AL_SERVER, players, address, path):");
    for s in &lists.servers {
        let key = format!("{}{}", s.region, s.name);
        println!("  {key:<8} {:>3}  {}  {}", s.players, s.address, s.path);
    }

    // AL_CHARACTER is the name. The socket `auth` event needs the id (CH_...).
    println!("characters (AL_CHARACTER, class, level, id, status):");
    for c in &lists.characters {
        let status = match &c.server {
            Some(server) => format!("online on {server}"), // `server` is there only while online
            None => "offline".to_string(),
        };
        println!("  {:<8} {:<9} {:>3}  {}  {status}", c.name, c.ctype, c.level, c.id);
    }
    Ok(())
}
