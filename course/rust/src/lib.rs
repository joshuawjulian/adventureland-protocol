//! albot: the library of the course. Each module is one file in src/.
//!
//! The order is the order of the chapters: the socket (Part 1), the HTTP API,
//! the game data, the world, cooldowns and the call-cost budget, the actions,
//! and `bot`, which connects all of them (Part 2). Part 3 adds `pathfind`,
//! `travel`, `items`, `party` and `farmer`.

pub mod actions;
pub mod alsocket;
pub mod api;
pub mod bot;
pub mod budget;
pub mod cooldowns;
pub mod farmer;
pub mod gdata;
pub mod items;
pub mod party;
pub mod pathfind;
pub mod travel;
pub mod world;

// The error and result types of the whole library. alsocket.rs defines them,
// because that file must also compile alone (scripts/check-examples.py).
pub use alsocket::{AlSocket, Error, Result};
