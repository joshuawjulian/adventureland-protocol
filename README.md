# Adventure Land from scratch

Everything you need to write your own [Adventure Land](https://adventure.land) client or bot
from scratch, in the language of your choice. No wrapper library: you learn the protocol and
speak it yourself.

It is three pages:

| Page | What it is |
|---|---|
| **Learn** (`site/learn.html`) | A course from zero for a CS student: HTTP and JSON, WebSockets, Socket.IO built by hand, logging in, the handshake, reading the world, acting, bot design, pathfinding, and a complete farming bot. |
| **Game guide** (`site/game.html`) | How the MMO works: classes, stats and combat, leveling, maps, items, upgrading, the economy, drops, events, seasons and social play. |
| **API reference** (`site/index.html`) | Every client → server event (109), every server → client event (74), every `game_response` code (258), the game data **G** and the server's event state **S**: payload fields, every check and its exact reply, and the line of server code behind each one. |

Every code example comes in **JavaScript, TypeScript, Python, Go, C#, Rust and Java**. Pick a
language in the top bar; the pages remember it. The course's programs were compiled and run in
all seven languages against a local test server.

## Source of truth

Everything is written from the live game's open-source code,
[kaansoral/adventureland_mongodb](https://github.com/kaansoral/adventureland_mongodb) (and its
engine, [kaansoral/common_engine](https://github.com/kaansoral/common_engine)). Each source
reference links to the exact line at the commit pinned in [`versions.json`](versions.json).
Where the code is unclear, entries say "unclear from the source" instead of guessing. Server bugs
are flagged where they matter. All prose follows Simplified Technical English (ASD-STE100).

The game updates often. [`scripts/check-updates.py`](scripts/check-updates.py) compares the pins
with the live game (G version, live code commits, the game's own release list) and lists the
entries to re-check; a daily GitHub Action opens an issue when something changed. See
[`docs/UPDATING.md`](docs/UPDATING.md).

## Using it

Open the files in `site/` in a browser, or serve the folder with GitHub Pages. Each page is
self-contained.

- **Search** matches names, fields, codes and descriptions. Press <kbd>/</kbd> to search, the
  arrow keys to move through results, and <kbd>Enter</kbd> to open one.
- **Every entry has a link** (`#send-buy`, `#code-too_far`, `#learn-alsocket`). Names
  inside entries link to their own entries, across pages.
- **Theme**: auto, light or dark.

## Building

```sh
python3 build.py                     # writes site/learn.html, game.html, index.html
bash scripts/fetch-source.sh         # the game's code at the pinned commits, into vendor/
python3 scripts/check-updates.py     # is the reference still current?
python3 scripts/ste-check.py content/*.md --summary   # style check
```

Python 3 only, no dependencies. The build fails if an event is in no group, if two entries share
a link, or if a link points at an entry that doesn't exist.

| File | What |
|---|---|
| `content/learn-1..3.md` | The course |
| `content/game-1..2.md` | The game guide |
| `content/connect.md` | Login, HTTP API, token API, handshake, observers, rate limits, conventions |
| `content/send-1.md` … `send-4.md`, `send-observer.md` | Events you send, in server-code order |
| `content/receive.md`, `content/codes.md` | Events you receive; the `game_response` codes |
| `content/game-data.md`, `content/server-events.md` | G and S |
| `docs/EXAMPLES.md`, `docs/STYLE.md`, `docs/WRITING.md`, `docs/UPDATING.md` | How examples, prose and entries are written, and how to update after a game update |

## Credits

Adventure Land and its code are by [Kaan Soral](https://github.com/kaansoral); this is an
unofficial reference. The game's code is used under its license, which asks for attribution and
a link back to [adventure.land](https://adventure.land). The game's code is not copied into this
repository; `scripts/fetch-source.sh` fetches it.
