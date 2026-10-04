// party.rs: several characters in one program, a party, and a new character.
//
// The program logs in once, reads the server and character lists once and
// loads G once. Then connect_member() opens one socket for each character.
// Each character has its own World, Cooldowns, Budget and Actions: the
// server counts the call-cost for each socket.
//
// Concurrency: Party is a Clone handle; its state is behind one lock, which
// the handlers fill on the dispatcher task.

use std::collections::HashSet;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use crate::actions::{Actions, GameResponse};
use crate::alsocket::{AlSocket, Result};
use crate::api::{self, Auth, Character, Server};
use crate::bot::Bot;
use crate::budget::Budget;
use crate::cooldowns::Cooldowns;
use crate::gdata::GData;
use crate::world::World;

// region member
/// One character in the game: the same parts as a Bot.
pub struct Member {
    pub name: String,
    pub sock: Arc<AlSocket>,
    pub g: Arc<GData>,
    pub world: World,
    pub cooldowns: Cooldowns,
    pub budget: Budget,
    pub act: Actions,
    pub character: Character,
}

impl Member {
    pub async fn close(&self) -> Result<()> {
        self.sock.close().await
    }
}

/// Connect one character with a login, a server and a G that we already
/// have: Bot::connect_with (Bot::connect without the HTTP calls).
pub async fn connect_member(auth: &Auth, server: &Server, character: &Character, g: Arc<GData>) -> Result<Member> {
    let bot = Bot::connect_with(auth.clone(), server.clone(), character.clone(), g).await?;
    let Bot { sock, g, world, cooldowns, budget, act, character, .. } = bot;
    Ok(Member { name: character.name.clone(), sock, g, world, cooldowns, budget, act, character })
}
// endregion member

// region create-character
/// Make a new character on the account: HTTP `create_character` {name, char}
/// (api.js:474-588). The name: 4 to 12 letters, digits or "_", not used by
/// anyone (api.js:24-31). The answer is {success: true}, or {failed: true,
/// reason}: "name_used", "invalid_name", "reached_character_limit", ...
pub async fn create_character(auth: &Auth, name: &str, ctype: &str) -> Result<Value> {
    let r = api::api_call("create_character", json!({"name": name, "char": ctype}), Some(auth)).await?;
    if r["failed"] == true {
        return Err(format!("create_character failed: {}", r["reason"].as_str().unwrap_or("unknown")).into());
    }
    Ok(r)
}
// endregion create-character

// region party
#[derive(Default)]
struct PartyState {
    list: Vec<String>,        // the names in our party, the leader first
    invites: HashSet<String>, // who invited us
}

/// The party of one character. The server sends `invite` {name} to the
/// character that gets an invitation, and `party_update` {list, party} to
/// each member when the party changes (node/server.js:12357-12546).
#[derive(Clone)]
pub struct Party {
    act: Actions,
    state: Arc<Mutex<PartyState>>,
}

impl Party {
    pub fn new(world: &World, act: &Actions) -> Party {
        let party = Party { act: act.clone(), state: Arc::default() };
        let s = party.state.clone();
        world.listen("invite", move |_, d| {
            let name = d["name"].as_str().unwrap_or_default().to_string();
            s.lock().unwrap_or_else(|p| p.into_inner()).invites.insert(name);
        });
        let s = party.state.clone();
        world.listen("party_update", move |_, d| {
            // {} (no list) when we left or the party ended.
            let list = d["list"].as_array().into_iter().flatten().filter_map(|n| n.as_str().map(String::from)).collect();
            s.lock().unwrap_or_else(|p| p.into_inner()).list = list;
        });
        party
    }

    /// A copy of the names in our party, the leader first.
    pub fn list(&self) -> Vec<String> {
        self.state.lock().unwrap_or_else(|p| p.into_inner()).list.clone()
    }

    /// Invite `name` (a character on this server). The answer is a success
    /// with place "party", or "invalid" (no such character), "party_full".
    pub async fn invite(&self, name: &str) -> Result<Option<GameResponse>> {
        self.act.request("party", json!({"event": "invite", "name": name}), None, None).await
    }

    /// Accept the invitation of `name`. It fails with "invitation_expired"
    /// when there was no invitation.
    pub async fn accept(&self, name: &str) -> Result<Option<GameResponse>> {
        self.act.request("party", json!({"event": "accept", "name": name}), None, None).await
    }

    pub async fn leave(&self) -> Result<Option<GameResponse>> {
        self.act.request("party", json!({"event": "leave"}), None, None).await
    }

    /// Wait until `name` invited us (true), or `ms` passed (false).
    pub async fn wait_invite(&self, name: &str, ms: u64) -> bool {
        let end = Instant::now() + Duration::from_millis(ms);
        loop {
            if self.state.lock().unwrap_or_else(|p| p.into_inner()).invites.contains(name) {
                return true;
            }
            if Instant::now() >= end {
                return false;
            }
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
    }
}
// endregion party
