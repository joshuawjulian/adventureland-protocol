# The course library: the contract

The Learn page builds one small library, **albot**, in seven languages, plus a set of programs
that use it. The code lives in `course/`, one project per language, and the chapters show it
with includes (docs/EXAMPLES.md, "Including code from course/"). This file is the contract
that every chapter and every language follows: the modules, the public names, the programs,
what they print, the environment variables, and the local test server. Parts 1 to 3 are
written; a later change must not rename what is already here.

If you change a name in this file, change it in all seven projects, in the chapters that show
it, and in `scripts/check-course.py`, in one pass.

## Rules for all seven projects

- **Source of truth for behavior is the live game's code** (`vendor/adventureland_mongodb`).
  Cite it in comments as `node/server.js:LINE` where a value or rule comes from it.
- **Heavy, useful comments.** Comment why. Call out each hard-coded value with its reason.
  Comments use the STE word choices of docs/STYLE.md.
- **Region markers** (for includes) are plain comment lines: `// region NAME` and
  `// endregion NAME` (`# region NAME` / `# endregion NAME` in Python). The include drops the
  marker lines. Region names are lowercase with dashes. The regions that chapters use are
  listed under each module below; a project may add more, never rename one that a chapter uses.
- **`alsocket` is standalone.** It imports only its language's standard library and the
  WebSocket and JSON packages below, never another albot module. `scripts/check-examples.py`
  copies this one file to compile the reference examples against it.
- **No secrets in code.** Logins come from the environment variables below.
- **Idiomatic names**: camelCase in JS, TS and Java; snake_case in Python and Rust; PascalCase
  for exported names in Go and C# (C# methods that return a `Task` end in `Async`). The tables
  below give the JS name; the other languages apply their rule mechanically
  (`moveTo` → `move_to` → `MoveTo` / `MoveToAsync`). Exceptions are listed where they occur.
- **Concurrency.** JS, TS and Python run everything on one event loop. In Go, C#, Rust and
  Java, AlSocket calls handlers on its dispatcher thread while the program's own loop runs on
  another thread: `World`, `Cooldowns` and `Budget` keep their state behind one lock each and
  expose methods that take it (Go `sync.Mutex`; C# `lock`; Rust `Arc<Mutex<...>>`; Java
  `synchronized`). Each of these files says so in a comment at the top.
- **Dynamic entities.** An entity (`me`, a monster, a player) is the server's JSON object,
  kept as the language's mutable JSON object, so that `player` merges and `entities` replaces
  work field by field: JS/TS plain objects (TS adds interfaces for the fields the course
  reads); Python `dict`; Go `type Entity map[string]any` with helpers `Num(key) float64`,
  `Str(key) string`, `Bool(key) bool`; C# `System.Text.Json.Nodes.JsonObject`; Rust
  `serde_json::Map<String, Value>` (type alias `Entity`); Java Jackson `ObjectNode`.
  Helpers that read a number treat a missing field as 0.

### Pinned versions

The same pins as learn-1 "Before you start" and `scripts/check-course.py`:

| Language | Runtime | Packages (exact versions) | Docker image |
|---|---|---|---|
| JavaScript | Node.js 22.18+ | none (dev: `typescript@5.6.3`, `@types/node@22.10.0` to check JSDoc types) | `node:22` |
| TypeScript | Node.js 22.18+ (runs `.ts` directly) | dev: `typescript@5.6.3`, `@types/node@22.10.0` | `node:22` |
| Python | 3.11+ | `httpx==0.27.2`, `websockets==13.1` (dev: `mypy==1.13.0`) | `python:3.12-slim` |
| Go | 1.22 | `github.com/coder/websocket v1.8.13` | `golang:1.22` |
| C# | .NET 8 | none | `mcr.microsoft.com/dotnet/sdk:8.0` |
| Rust | 1.80+ (edition 2021) | `tokio 1.40` (full), `tokio-tungstenite 0.24` (`rustls-tls-webpki-roots`), `futures-util 0.3`, `serde 1` (derive), `serde_json 1`, `reqwest 0.12` (`default-features = false`, features `json`, `rustls-tls`) | `rust:1` |
| Java | 21 | `com.fasterxml.jackson.core:jackson-databind:2.18.2`; plugin `exec-maven-plugin 3.5.0` | `maven:3-eclipse-temurin-21` |
| Test server | Node.js 22 | `socket.io@4.8.1`, `ws@8.18.0` | `node:22` |

## Project layout

Each language is one project. The library is a folder (or package, or crate) named `albot`
inside it; the programs sit next to it.

| Language | Project | Library files | Program files | Run a program |
|---|---|---|---|---|
| js | `course/js` (`package.json`, `"type": "module"`) | `albot/<module>.js` | `<program>.js` | `node al-test.js` |
| ts | `course/ts` (`package.json`, `tsconfig.json`) | `albot/<module>.ts` | `<program>.ts` | `node al-test.ts` |
| python | `course/python` (`requirements.txt`) | `albot/<module>.py` (+ `__init__.py`) | `<program>.py` (snake_case: `al_test.py`) | `python al_test.py` |
| go | `course/go` (`go.mod`: `module albot`) | `<module>/<module>.go` (package per module) | `cmd/<program>/main.go` | `go run ./cmd/al-test` |
| csharp | `course/csharp` (`Course.sln`) | `Albot/<Module>.cs` (class library `Albot.csproj`, namespace `Albot`) | `<Program>/Program.cs` + `<Program>.csproj` (top-level statements, references `../Albot`) | `dotnet run --project AlTest` |
| rust | `course/rust` (`Cargo.toml`, crate `albot`) | `src/<module>.rs` (declared in `src/lib.rs`) | `src/bin/<program>.rs` | `cargo run --bin al-test` |
| java | `course/java` (`pom.xml`, artifact `albot`) | `src/main/java/albot/<Module>.java` (package `albot`) | `src/main/java/<Program>.java` (default package) | `mvn -q compile exec:java -Dexec.mainClass=AlTest` |

Module file names per language:

| Module | js / ts / python | go (package) | csharp | rust | java |
|---|---|---|---|---|---|
| alsocket | `alsocket` | `alsocket` (type `Socket`) | `AlSocket.cs` | `alsocket.rs` | `AlSocket.java` |
| api | `api` | `api` | `Api.cs` (static class `Api`) | `api.rs` | `Api.java` (final class, static methods) |
| gdata | `gdata` | `gdata` | `GData.cs` (static class `GData`) | `gdata.rs` | `GData.java` |
| world | `world` | `world` (type `World`) | `World.cs` | `world.rs` | `World.java` |
| cooldowns | `cooldowns` | `cooldowns` (type `Cooldowns`) | `Cooldowns.cs` | `cooldowns.rs` | `Cooldowns.java` |
| budget | `budget` | `budget` (type `Budget`) | `Budget.cs` | `budget.rs` | `Budget.java` |
| actions | `actions` | `actions` (type `Actions`) | `Actions.cs` | `actions.rs` | `Actions.java` |
| pathfind | `pathfind` | `pathfind` (type `Grid`) | `Pathfind.cs` (class `Grid`) | `pathfind.rs` | `Grid.java` |
| travel | `travel` | `travel` (type `Travel`) | `Travel.cs` | `travel.rs` | `Travel.java` |
| items | `items` | `items` (type `Items`) | `Items.cs` | `items.rs` | `Items.java` |
| party | `party` | `party` (types `Member`, `Party`) | `Party.cs` | `party.rs` | `Party.java` (nested `Member`) |
| farmer | `farmer` | `farmer` (type `Farmer`) | `Farmer.cs` | `farmer.rs` | `Farmer.java` |
| bot | `bot` | `bot` (type `Bot`) | `Bot.cs` | `bot.rs` | `Bot.java` |

Program names (the file or folder name in each language):

| Program | js / ts | python | go | csharp | rust | java | Status |
|---|---|---|---|---|---|---|---|
| servers | `servers` | `servers` | `cmd/servers` | `Servers` | `servers` | `Servers` | now |
| echo | `echo` | `echo` | `cmd/echo` | `Echo` | `echo` | `Echo` | now |
| al-test | `al-test` | `al_test` | `cmd/al-test` | `AlTest` | `al-test` | `AlTest` | now |
| login | `login` | `login` | `cmd/login` | `Login` | `login` | `Login` | now |
| connect | `connect` | `connect` | `cmd/connect` | `Connect` | `connect` | `Connect` | now |
| first-kill | `first-kill` | `first_kill` | `cmd/first-kill` | `FirstKill` | `first-kill` | `FirstKill` | now |
| farm | `farm` | `farm` | `cmd/farm` | `Farm` | `farm` | `Farm` | now (Part 3) |
| supplies | `supplies` | `supplies` | `cmd/supplies` | `Supplies` | `supplies` | `Supplies` | now (Part 3) |
| party-merchant | `party-merchant` | `party_merchant` | `cmd/party-merchant` | `PartyMerchant` | `party-merchant` | `PartyMerchant` | now (Part 3) |
| gear-up | `gear-up` | `gear_up` | `cmd/gear-up` | `GearUp` | `gear-up` | `GearUp` | now (Part 3) |

`servers` and `echo` are standalone (no albot import): they are the first smoke tests of a new
project. `al-test` imports only `alsocket`. All other programs use `bot`.

Project files (learn-1 "Before you start" includes them, so keep them short and commented
where the format allows): js `package.json` (`"type": "module"`, devDependencies `typescript`,
`@types/node` pinned) and `tsconfig.json` (`allowJs`, `checkJs`, `noEmit`); ts `package.json`
and `tsconfig.json` (`strict`, `noEmit`, `allowImportingTsExtensions`, `module` `nodenext`);
python `requirements.txt` (exact pins); go `go.mod`; csharp `Course.sln`, `Albot/Albot.csproj`
and one `.csproj` per program; rust `Cargo.toml` (lib + bins, exact feature lists); java
`pom.xml` (Jackson, exec plugin). `scripts/check-course.py` builds with exactly these.

Ignored build output (`course/.gitignore`): `node_modules/`, `.venv/`, `__pycache__/`,
`.mypy_cache/`, `bin/`, `obj/`, `target/`, `cp.txt`, `.al-cache/`, `course/test-server/G.json`.

## Environment variables (one table for the whole course)

| Variable | Used by | Meaning | Default | Test server value |
|---|---|---|---|---|
| `AL_BASE_URL` | every program that uses HTTP | The website and its HTTP API. `ws`/`wss` for the game socket follows its scheme (`http` → `ws`, `https` → `wss`). | `https://adventure.land` | `http://localhost:8022` |
| `AL_EMAIL` | `login` (and any program, when `AL_AUTH` is empty) | The account email. Needed for one password login only. | none | `tester@example.com` |
| `AL_PASSWORD` | as `AL_EMAIL` | The account password. | none | `test-password` |
| `AL_AUTH` | every program that logs in | The session: `<user>-<auth>`, split at the first `-`. When set, no program sends the password. | none | `US_tester-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef` |
| `AL_SERVER` | programs that enter the game | The game server: `region` + `name`, for example `EUI`. **Empty means the first server of the list** (the list is in the order EU, US, ASIA). | first server | `EUI` |
| `AL_CHARACTER` | programs that enter the game | The character name (not the `CH_` id). Required. | none | `Tester` |
| `AL_WS_URL` | `al-test` only (Part 1, before HTTP) | The full WebSocket URL of a game server. | `ws://localhost:8022/ws1/?EIO=4&transport=websocket` | (the default) |
| `AL_ECHO_URL` | `echo` only | The URL of a plain WebSocket echo server. | `ws://localhost:8022/echo` | (the default) |
| `AL_RECONNECT_MS` | long-running programs (Part 3) | The first wait of the reconnect rule, in ms. Tests set it low. | `30000` | `2000` |

There is no `AL_URL`, `AL_ORIGIN` or `AL_PATH` any more.

When a password login succeeds, `api.login` prints exactly these three lines (the value is the
same in both), so the reader can paste the line for their shell:

```
Logged in with the password. Save this value, and use it from now on:
  export AL_AUTH='US_tester-0123...'
  PowerShell: $env:AL_AUTH = 'US_tester-0123...'
```

## Modules and public names

`G` is the game data, `sock` a connected AlSocket, `me` our character. Types in the typed
languages: `Auth {user, auth}`, `Server`, `Character` (records or structs with the fields the
course reads), `GameResponse` (normalized `game_response`), the G defs below.

### alsocket (Part 1, done)

The surface of docs/EXAMPLES.md, unchanged: `connect(url)`, `emit(name, payload?)`,
`on(name, handler)`, `waitFor(name, pred?, timeoutMs?)`, `close()`; Go adds `Expect` and
`Done`; Rust adds `wait_for_timeout`; Java adds `waitFor(name)` and `done()`. Behavior: answers
each `2` with `3` in the reader; one dispatcher in arrival order; keeps events that arrive
before the first `on`/`waitFor` and gives them to the first subscriber of that name; a local
`disconnect` event with a reason, after which waiters fail; no reconnect.

Regions: none required (chapters include the whole file).

### api (Part 2, "Logging in and choosing a server") — now

| Name | Signature (JS) | Does |
|---|---|---|
| `baseUrl` | `baseUrl(): string` | `AL_BASE_URL` or `https://adventure.land`, without a final `/`. |
| `apiCall` | `apiCall(method, body = {}, auth = null): Promise<object>` | `POST {base}/api/{method}` with a JSON body; with `auth`, header `Cookie: auth=<user>-<auth>`. Throws on an HTTP status other than 200. Returns the parsed JSON (also when it has `failed`). |
| `parseAuth` | `parseAuth(text): Auth` | Splits `<user>-<auth>` at the first `-`. Throws if there is no `-`. |
| `login` | `login(): Promise<Auth>` | `AL_AUTH` if set (no password). Else `signup_or_login` with `{email, password, only_login: true}`; throws `login failed: <reason>`; prints the three save lines above. |
| `serversAndCharacters` | `serversAndCharacters(auth): Promise<{servers, characters}>` | Finds the `infs` item with `type: "servers_and_characters"`. Throws a clear message on `not_logged_in`. |
| `findServer` | `findServer(servers, key = env AL_SERVER): Server` | Matches `region + name` (e.g. `EUI`); empty key → the first server. Throws `no server <key>; the list has: EUI, USI` when none matches. |
| `findCharacter` | `findCharacter(characters, name = env AL_CHARACTER): Character` | Matches `name` exactly. Throws if `name` is empty or not in the list. |
| `socketUrl` | `socketUrl(server, base = baseUrl()): string` | `ws(s)://<address><path with exactly one final />?EIO=4&transport=websocket&map_protocol=1&no_graphics=1`. |

Regions: `api-call`, `login`, `servers-and-characters`, `find-server`, `socket-url`.

### gdata (Part 2, "Getting the game data") — now

| Name | Signature (JS) | Does |
|---|---|---|
| `fetchVersion` | `fetchVersion(base): Promise<number \| null>` | `GET {base}/hub`, finds `var VERSION='<n>'`. |
| `downloadG` | `downloadG(base): Promise<G>` | `GET {base}/data.js`, parses the text from the first `{` to the last `}`. |
| `cachePath` | `cachePath(base, version): string` | `.al-cache/<host>/G_<version>.json`, `<host>` = host and port of `base` with `:` → `_` (so the trimmed test G never mixes with the live G). |
| `loadG` | `loadG(base = baseUrl()): Promise<G>` | Cache hit → read it. Else download, save, and print `downloaded G version <n>`. |

Typed languages define `ItemDef`, `MonsterDef`, `SkillDef`, `GData` with only the fields the
course reads (Part 2 text lists them; TS, Python and Rust also type `ItemDef.compound` and
`ItemDef.upgrade`, the stats per level, which Part 3 reads to find items that compound); the rest stays reachable as raw JSON (Go
`map[string]json.RawMessage` or similar, C# `JsonObject`, Rust `Value`, Java `JsonNode`).

Regions: `fetch-version`, `download-g`, `load-g`, `types` (in JS: the `G` typedef).

### world (Part 2, "Reading the world") — now

`World` keeps our copy of the world. The constructor registers its handlers, so create it
**before** sending `loaded`/`auth`.

| Name | Signature (JS) | Does |
|---|---|---|
| constructor | `new World(sock, G)` | Registers through `listen`: `start`, `player`, `entities`, `death`, `disappear`, `new_map`, `drop`, `chest_opened`, `correction`. |
| `listen` | `listen(name, handler)` | One table from event name to handlers. The first `listen` for a name also does `sock.on(name, data => dispatch(name, data))`. |
| `dispatch` | `dispatch(name, data)` | Calls the handlers of `name`. Hitchhikers reach handlers through it. |
| `me` | field | Our character: the `start` payload (without `entities`), with each `player` merged in. Empty until `start`. |
| `monsters`, `players` | fields | id → entity. `players` holds other players and NPCs (never us). |
| `chests` | field | chest id → the `drop` payload. Removed on `chest_opened`. |
| `onStart`, `onPlayer`, `applyEntities`, `onNewMap`, `withDefaults` | handlers | As in Part 2. `onPlayer` dispatches `hitchhikers` (`[event, payload]` pairs). `applyEntities` ignores another `in`, clears on `type: "all"`, replaces each entity, skips our own id, and fills monster fields from `G.monsters[type]` (`max_hp` = G `hp`). |
| `step` | `step(e, ms)` (module function) | Moves one moving entity toward `going_x/going_y` by `speed * ms / 1000` px. |
| `advance` | `advance()` | Steps `me`, monsters and players by the time since the last `advance` (or the last update). Call it before you read positions. No background timer. |
| `distance` | `distance(a, b)` | The gap between two hit boxes, the way the server measures range (`js/old_common_functions.js:707-740`); sizes from `G.dimensions` (an entity type with no entry uses the default that the source uses). |
| `nearestMonster` | `nearestMonster(type = null)` | The closest monster (of `type`, if given) to `me`, or null. |

Regions: `constructor` (the handlers it registers), `listen` (with `dispatch`), `on-start`, `on-player`,
`apply-entities`, `on-new-map`, `step`, `advance`, `distance`.

### cooldowns (Part 2, "Hearing back") — now

| Name | Signature (JS) | Does |
|---|---|---|
| constructor | `new Cooldowns(world)` | Listens (through `world.listen`, so hitchhikers count) to `skill_timeout`, `game_response` (`cooldown` → the skill; `not_ready` → `"potion"`), `eval` (`pot_timeout(ms)` → `"potion"`; `skill_timeout('name',ms)`). `eval` can be a string or `{code}`. |
| `start` | `start(name, ms)` | Sets the ready time; also the skill in `G.skills[name].share`. |
| `ready` | `ready(name): boolean` | |
| `msLeft` | `msLeft(name): number` | 0 when ready. |

Names used: skill names, and `"potion"` for the shared potion timer.

Regions: `cooldowns`.

### budget (Part 2, "Hearing back") — now

| Name | Signature (JS) | Does |
|---|---|---|
| `EXTRA_COST` | constant | The per-event extra call-cost (`node/server.js:242-258`). |
| `LIMIT`, `WINDOW_MS` | constants | 150 (of the server's 200; the `resend` cost is not visible), 4000. |
| constructor | `new Budget(sock, world)` | Adds 8 on each `new_map` (the server charges a map change, `add_call_cost(player, 8, "transport")`). |
| `cost` | `cost(event): number` | `1 + EXTRA_COST[event]`. |
| `emit` | `emit(event, payload?): Promise<void>` | Waits until the last 4 s have room, records the cost, then `sock.emit`. |
| `spent` | `spent(): number` | The total of the last 4 s. |

Regions: `budget`.

### actions (Part 2, "Acting in the world") — now

`new Actions(sock, world, cooldowns, budget)`. Every emit goes through `budget.emit`. Methods
that wait for a reply register the wait before the emit. Part 3 puts its actions in new modules,
not here: walking and doors in `travel`, the shop, gear, gifts and upgrades in `items`, the party
in `party`.

| Name | Signature (JS) | Does |
|---|---|---|
| `normalize` | `normalize(data): GameResponse` (module function) | A string → `{response, failed: false, success: false}`; an object gets `failed`/`success` defaults. |
| `responseFor` | `responseFor(place)` (module function) | Predicate: an object `game_response` with this `place`. |
| `request` | `request(event, payload, place = event, timeoutMs = 2000): Promise<GameResponse \| null>` | Wait, emit, normalize. null on timeout. |
| `move` | `move(x, y)` | Emits `move` with `me.x, me.y, going_x, going_y, m`; sets `me.going_x/going_y/moving`. No wait. |
| `moveTo` | `moveTo(x, y): Promise<boolean>` | `move`, then waits distance / speed + 250 ms, then `advance`. True when `me` is less than 1 px from (x, y) and `me.going_x/going_y` are still (x, y) (a `correction` or a jail changed nothing). Straight line only. |
| `attack` | `attack(id): Promise<GameResponse \| null>` | `request("attack", {id})`. |
| `heal` | `heal(stat): Promise<boolean>` | `stat` is `"hp"` or `"mp"`. A potion that gives `stat` (`equip {num, consume: true}`) if one is in the inventory, else the free regeneration (`use {item: stat}`). Skips (false) when `"potion"` is not ready. |
| `openChest` | `openChest(id): Promise<object \| null>` | Waits for `chest_opened` with this id. |
| `openChests` | `openChests(): Promise<number>` | Opens each chest of `world.chests`; returns how many opened (not `gone`). Removes each chest from `world.chests` also when no reply came (`loot_no_space`, `loot_failed`: the live server keeps the chest, `node/server.js:11315`), so that it never tries one chest forever. |
| `respawn` | `respawn(): Promise<boolean>` | Waits the rest of the 12 s `rip_time`, sends `respawn`, retries once on `cant_respawn` with its `ms`. |

Regions: `normalize` (with `responseFor`, and the `GameResponse` type where a language has one),
`request`, `move-to` (`move` and `moveTo`), `attack`, `heal`, `open-chests`, `respawn`.

### pathfind (Part 3, "Distance, range and movement") — now

`Grid.forMap(G, map)` (constructor in Go: `pathfind.ForMap`): the grid of a map from
`G.geometry[map]`, built once per map and cached; throws `no geometry for the map <map> in G`.
8 px cells; a cell is blocked when the player base box (8 px left/right, 7 up, 2 down,
`node/server.js:185`) plus 4 px touches a wall; walkable = flood fill from `G.maps[map].spawns`.

| Name | Signature (JS) | Does |
|---|---|---|
| `safe` | `safe(x, y): boolean` | The nearest cell is walkable. |
| `lineClear` | `lineClear(ax, ay, bx, by): boolean` | Each point every 4 px is safe. |
| `nearestFree` | `nearestFree(x, y): number` | The nearest walkable cell index (rings, at most 40 cells), or -1. |
| `cell`, `point` | `cell(x, y)`, `point(k)` | Position → cell index (-1 outside); cell index → its centre `[x, y]`. |
| `findPath` | `findPath(sx, sy, gx, gy): Point[] \| null` | A* (8 directions, octile estimate, no corner cutting) from the nearest free cell of the start to the goal cell; null if the goal is not walkable or not reachable. Smoothed: each point is the farthest that a clear line reaches. Excludes the start; the last point is the exact goal. |

Regions: `grid`, `find-path`.

### travel (Part 3, "Distance, range and movement") — now

`new Travel(world, act)`.

| Name | Signature (JS) | Does |
|---|---|---|
| `walkTo` | `walkTo(x, y): Promise<boolean>` | A goal that is not walkable becomes the nearest walkable point. `findPath`, then `act.moveTo` for each point. false: no path, or a `moveTo` that did not arrive, or the map changed (`me.map`/`me.m`), or death. |
| `transport` | `transport(map, spawn): Promise<boolean>` | `request("transport", {to, s})`, then polls until `me.map === map` and `me.m` changed (5 s). Works for the bank's `in_progress`. |
| `leaveJail` | `leaveJail(): Promise<boolean>` | `request("leave", {})`, then polls until `me.map !== "jail"`. |
| `exits` | `exits(map): Hop[]` | Doors without a lock (stand at `spawns[door[6]]`, `transport(door[4], door[5])`) and the transporter places (`G.npcs.transporter.places`) if the map has her. `Hop {map, x, y, to, spawn, by: "door" \| "transporter"}`. |
| `route` | `route(from, to): Hop[] \| null` | Breadth-first search on the map graph; `[]` when `from === to`. |
| `goToMap` | `goToMap(map): Promise<boolean>` | For each hop: `walkTo`, check 112 px (door) / 160 px (transporter), `transport`. |

Regions: `walk-to`, `transport`, `leave-jail`, `route`.

### farmer (Part 3, "A complete farming bot") — now

`new Farmer(world, act, cooldowns, travel, prefix = "")`. Fields `type` (`"goo"`), `home`
(`"main"`), `target` (id or null), `kills`. Listens to `death`/`hit` (kill of the target; our
hits by `hid`) and `chest_opened` (prints `chest <id>: +<gold> gold, <n> item(s)`). Prints with
`prefix` before each line.

| Name | Signature (JS) | Does |
|---|---|---|
| `LADDER` | constant | `goo, bee, crab, snake, squig, armadillo, croc, tortoise` (game-1 "Your first day"). |
| `tick` | `tick(): Promise<void>` | `advance`, then the first that applies: rip → print `died; respawn in <s> s`, `respawn`, `respawned at <x>,<y>`; jail → `in jail: leave`, `leaveJail`, `left jail: on <map> at <x>,<y>`; not `home` → `on <map>: go to main`, `goToMap`; potion ready and hp < 70% → `heal("hp")`, else mp < 30% → `heal("mp")`; chests → `openChests`; no target → nearest of `type` (print `target: <type> <id> at <x>,<y>`) or `walkTo` the middle of its pack boundary; out of range → `walkTo` a point `range - 10` px from it; else attack when ready. On a kill: `killed <type> <id>`. |
| `nextType` | `nextType(): boolean` | When each of the last 3 kills took ≤ 2 of our hits: next on `LADDER`, prints `next monster: <type>`. |

Regions: `ladder`, `next-type`, `tick`.

### items (Part 3, "Supplies, loot and gear"; "A party and a merchant"; "Gearing up") — now

`new Items(world, act, budget)`. Keeps the last 50 `game_response` events that reach
`world.listen` (hitchhikers too), normalized, with a sequence number.

| Name | Signature (JS) | Does |
|---|---|---|
| `NPC_DIST`, `SLOTS_FOR_TYPE`, `KEEP_TYPES` | constants | 350; item type → equipment slots; `pot, uscroll, cscroll, pscroll, offering, ring, earring, amulet, belt, orb`. |
| `isLoot` | `isLoot(G, item): boolean` (module function) | Not null, not `placeholder`, not locked (`l`), type not in `KEEP_TYPES`. |
| `find`, `count`, `freeSlots` | `find(name, level = null)`, `count(name)`, `freeSlots()` | Slot number or -1; total `q`; `me.esize`. |
| `npcSelling`, `npcWithRole` | `(item)`, `(role)` → `{id, x, y} \| null` | From `G.maps[me.map].npcs` and `G.npcs[id]`. |
| `buy`, `sell` | `buy(name, quantity)`, `sell(num, quantity)` | `request("buy", {name, quantity})`, `request("sell", {num, quantity})`. |
| `equip`, `unequip` | `equip(num, slot = null)`, `unequip(slot)` | `request("equip", {num, slot?})`, `request("unequip", {slot})`. |
| `equipBetter` | `equipBetter(): Promise<string[]>` | Equips each bag item whose slot is empty or holds the same item at a lower level; returns `"<name>: <slot>"` for each success. |
| `sendItem`, `sendGold` | `(name, num, quantity)`, `(name, gold)` | `request("send", {name, num, q})`, `request("send", {name, gold})`. |
| `deposit`, `withdraw` | `(gold)` | `request("bank", {operation, amount})`. |
| `upgrade` | `upgrade(itemNum, scrollNum, calculate = false): Promise<GameResponse \| null>` | Emits `{item_num, scroll_num, clevel, calculate?}`; returns the first later answer with `place` `"upgrade"` or a response starting with `upgrade_` (2 s with calculate, else 30 s). |
| `compound` | `compound(nums, scrollNum, calculate = false)` | The same with `{items, scroll_num, clevel, calculate?}` and `compound`. |

Regions: `rules`, `find`, `shop`, `equip`, `send`, `bank`, `upgrade`.

### party (Part 3, "A party and a merchant") — now

| Name | Signature (JS) | Does |
|---|---|---|
| `Member` | class | `name, sock, G, world, cooldowns, budget, act, character`; `close()`. The parts of a `Bot` (whose constructor is not public in every language). |
| `connectMember` | `connectMember(auth, server, character, G): Promise<Member>` | `Bot.connectWith`, then a `Member` from the parts of that `Bot`. |
| `createCharacter` | `createCharacter(auth, name, ctype): Promise<object>` | HTTP `create_character` `{name, char}`; throws `create_character failed: <reason>`. |
| `Party` | `new Party(world, act)` | Field `list` (from `party_update`); `invite(name)`, `accept(name)`, `leave()` (`request("party", {event, name})`); `waitInvite(name, ms = 5000): Promise<boolean>` (an `invite` from `name` arrived). |

Regions: `member`, `create-character`, `party`.

### bot (Part 2, "Connecting and the handshake") — now

| Name | Signature (JS) | Does |
|---|---|---|
| `enterGame` | `enterGame(sock, auth, characterId, timeoutMs = 30000): Promise<object>` | Returns the `welcome` payload (`bot.welcome`); `start` reaches `World` through its handler, so create `World` first. The handshake: wait `welcome`, send `loaded`, send `auth` `{user, auth, character, no_html: "1", passphrase: ""}`, wait `start`. Fails with `LoginError(reason)` on `game_error` (`errorReason`), `game_log` "Authorization in progress" (`authorization_in_progress`), `disconnect_reason` (its text), `disconnect`, or the timeout. |
| `errorReason` | `errorReason(payload): string` (module function) | The reason of a `game_error`: its `reason` (`no_character`, `password_issue`, `mainframe_issue`, `ingame`, `poker_hand_active`, `cancelled`); else `server_full` for the phrase `server.game_error.capacity`; else the last part of the phrase (`characters_unconfirmed`); a bare string is itself. |
| `LoginError` | error type | `.reason` as above. Its message is `login failed: <reason>` in all languages. |
| `Bot.connect` | `Bot.connect(): Promise<Bot>` | `login` → `serversAndCharacters` → `findServer` → `findCharacter` → `loadG` → `Bot.connectWith`. |
| `Bot.connectWith` | `Bot.connectWith(auth, server, character, G): Promise<Bot>` | The steps after the HTTP calls: `AlSocket.connect(socketUrl(...))` → `new World` (before `loaded`) → `enterGame` (with the welcome-race handling) → `Cooldowns`, `Budget`, `Actions`. Closes the socket on a failure. Part 3 (`connectMember`) uses it. |
| fields | | `sock`, `G`, `world`, `cooldowns`, `budget`, `act`, `auth`, `server`, `character`, `welcome`. |
| `close` | `close()` | Closes the socket. |
| `reconnectDelayMs` | `reconnectDelayMs(attempt): number` (module function) | **The one reconnect rule** (below). `attempt` counts from 0 (the first try): `AL_RECONNECT_MS × 2^attempt`, at most 300,000. |

**The welcome race.** AlSocket keeps early events only until the first `on`/`waitFor` of *any*
name. With threads (Go, C#, Rust, Java), `welcome` can arrive after `World` subscribes and before
the handshake waits for it, and it is then lost. So `Bot.connectWith` registers the `welcome` wait
(or waits for `welcome`) **before** it creates `World`; each language does this its own way
(C#: an optional `welcomeWait` argument; Java: `waitWelcome` + `sendAuth`). The `start` wait
uses `sock.on`, after `World`'s handler, so `world.me` is filled when `connectWith` returns.

Regions: `error-reason`, `enter-game`, `connect`, `reconnect-delay`.

**The reconnect rule** (Part 1 "AlSocket" states it; every chapter links there): do not
reconnect at once. After a disconnect the server keeps the character in `dc_players` until its
save ends, and a new `auth` then gets "Authorization in progress" (`node/server.js:11577-11582`,
`:13055`, `:16812`). Wait `AL_RECONNECT_MS` (30 s) before the first try, double the wait after
each failed try, at most 300 s. Start again from 30 s after a session that lasted 5 minutes.
Close the old socket first; always make a new AlSocket and do the full handshake again.

## The programs

Every program exits with status 0 on success and non-zero on failure, and prints exactly the
lines below (values in `<>` vary; positions are rounded to integers). `scripts/check-course.py`
matches these lines.

**servers** (Part 1, "The AL HTTP API"; standalone). `GET {AL_BASE_URL}/api/get_servers`.

```
status: 200 application/json; charset=utf-8
EU I: ws://localhost:8022/ws1/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1
US I: ws://localhost:8022/ws2/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1
```

**echo** (Part 1, "WebSockets in practice"; standalone). Sends `hello` to `AL_ECHO_URL`.

```
connected
received: hello
closed
```

**al-test** (Part 1, "A local game server"; imports alsocket only). Connects to `AL_WS_URL`,
waits `welcome`, sends `loaded`, waits the `type: "all"` `entities`, sends `auth` with the test
server's fixed account (`{user: "US_tester", auth: <the test auth>, character: "CH_tester",
no_html: "1", passphrase: ""}`: hard-coded, with a comment that says why: Part 1 has no login
code yet), waits `start`, idles 3 s, `ping_trig` `{id: "42"}` →
`ping_ack`, closes.

```
connected to ws://localhost:8022/ws1/?EIO=4&transport=websocket
welcome: EU I, version <n>
entities: <n> monster(s)
start: Tester on main at <x>,<y>
ping_ack after 3 s idle: 42
OK
disconnect: <reason; different in each language>
```

**login** (Part 2). `login`, `serversAndCharacters`, then prints:

```
user id: US_tester
servers (AL_SERVER, players, address, path):
  EUI      <n>  localhost:8022  /ws1/
  USI      <n>  localhost:8022  /ws2/
characters (AL_CHARACTER, class, level, id, status):
  Tester   warrior    1  CH_tester  offline
  ...
```

(With a password login, the three save lines come first.)

**connect** (Part 2). `Bot.connect()`, prints, closes:

```
welcome: EU I, version <n>
in game as Tester (warrior, level <n>) on main at <x>,<y>
OK
```

**first-kill** (Part 2 checkpoint, end of "Hearing back"). `Bot.connect()`, then: respawn if
dead; loop every 100 ms (heal check first, then pick the nearest goo once, so the first
`heal hp` line comes before `target`) (`advance` first): if hp < 70% of `max_hp` and
the potion timer is ready, `heal("hp")`; if out of range, `moveTo` a point at `range - 10` px
from the goo; else attack when `attack` is ready; on death, respawn. Stop when the goo is dead
(a `death` event, or a `hit` with `kill`), wait up to 3 s for its chest, open the chests,
print, close. Fail after 90 s. No goo in view: wait for the next tick (no error). The
`heal hp` line prints the hp after a successful `heal` (the `player` update comes before the
reply), so it shows the new value.

```
in game as Tester (warrior, level <n>) on main at <x>,<y>
heal hp: <hp>/<max_hp>
target: goo <id> at <x>,<y>
killed goo <id>
chest <id>: +<gold> gold, <n> item(s)
xp: <xp>/<max_xp>, level <n>
OK
```

(The first chest of each fixed character carries the live first-drop bonus, so expect a large
gold number and several items. `heal hp` lines appear each time the program heals; the test character starts with 40% hp, so
there is at least one. If it dies: `died; respawn in <s> s` and `respawned at <x>,<y>`.)

The Part 3 programs are long-running bots. Each one prints the lines below; the farmer's lines
(`target: ...`, `killed ...`, `chest ...`) may come between them. `scripts/check-course.py`
passes the argument in brackets and runs the setup posts.

**farm** (Part 3, "A complete farming bot"). `farm [seconds]` (0 or none: until Ctrl-C).
Loop: `Bot.connect` (on failure: `connect failed: <msg>; try again in <s> s`, the reconnect
rule), then `Farmer.tick` + `nextType` every 100 ms; on `disconnect` (or a throw):
`disconnected: <reason>; reconnect in <s> s`, wait `reconnectDelayMs(attempt)` (attempt back to
0 after a 5-min session), connect again. `disconnect_reason` prints `the server says: <r>`.
Ctrl-C: stop after the tick (a second one exits). Check: `farm 25`, after `POST
/test/drop?character=Tester&after_start_ms=5000` and `POST
/test/jail?character=Tester&after_start_ms=10000`.

```
in game as Tester (warrior, level 1) on main at -87,673
...
disconnected: <reason>; reconnect in 2 s
in game as Tester (warrior, level <n>) on main at <x>,<y>
...
in jail: leave
left jail: on main at <x>,<y>
farmed <s> s: <kills ≥ 1> kill(s), level <n>, <gold> gold
OK
```

**supplies** (Part 3, "Supplies, loot and gear"). `supplies [trips]`. Farms; after each chest
that opens (`chest_opened` without `gone`): `equipBetter` (prints `equip <name>: <slot>`), then
if `hpot0` < 20 or `mpot0` < 20 or free slots < 5: `supplies low: ...` and a town trip: walk to
`fancypots` (prints `walk to <npc> at <x>,<y>` when farther than 350 px), sell each `isLoot`
item (`sell <name>: +<gold> gold`), buy `hpot0`/`mpot0` up to 50 (`buy <name> x<q>: <cost>
gold`), buy `gloves`, `coat`, `pants` for empty slots while 2,000 gold stays, `equipBetter`,
print the bag line. Check: `supplies 1`.

```
in game as Tester (warrior, level 1) on main at -87,673
killed goo <id>
chest <id>: +<gold> gold, 5 item(s)
equip ringsj: ring1
equip ringsj: ring2
equip hpbelt: belt
supplies low: <n> hpot0, <n> mpot0, <n> free slot(s)
walk to fancypots at -35,-162
sell gem0: +<gold> gold
buy hpot0 x<n>: <gold> gold
buy mpot0 x40: 800 gold
buy gloves x1: 3400 gold
buy coat x1: 6000 gold
buy pants x1: 7800 gold
equip gloves: gloves
equip coat: chest
equip pants: pants
bag: 50 hpot0, 50 mpot0, <n> free slot(s), <gold> gold
OK
```

**gear-up** (Part 3, "Gearing up: upgrades and compounds"). Farms until one chest opened; buys
a `coat` if it has none; walks to the middle of `scrolls` and `newupgrade` (within 20 px);
upgrade loop while the coat is below +3: buy `scroll0` if none, `calculate`, stop if the chance
< 0.9 (`stop: the chance for +<n> is <c>`), upgrade, print, stop on a fail; compound loop over
groups of three (same name and level, G `compound`): buy `cscroll0` if none, `calculate`, stop
under 0.9, compound, print; `equipBetter`; the gear line. Results vary with the seeded rolls.

```
in game as Tester (warrior, level 1) on main at -87,673
killed goo <id>
walk to basics at -89,-165
buy coat x1: 6000 gold
walk to scrolls and newupgrade at -335,-158
buy scroll0 x1: 1000 gold
upgrade coat +0 -> +1: success|fail (chance 1.00)
... (+1 -> +2, +2 -> +3 while they succeed)
buy cscroll0 x1: 6400 gold
compound ringsj +0 x3 -> +1: success|fail (chance 0.99)
equip ...
gear: chest <item or ->, ring1 <...>, ring2 <...>, belt <...>
OK
```

**party-merchant** (Part 3, "A party and a merchant"). `party-merchant [trips]` or
`party-merchant --create-merchant <Name>` (prints `created the merchant <Name>. ...` and exits).
Team: `AL_CHARACTER` (must not be a merchant) + the next 2 non-merchants of the character
list + the first merchant. One `login`, one `serversAndCharacters`, one `loadG`, then
`connectMember` for each in turn. Party: the leader invites each, each `waitInvite` + `accept`;
wait up to 5 s for the full list. Fighters (concurrently): `Farmer` with prefix `<name>: `;
after each tick, if the merchant is in view within 300 px: `sendItem` each item that is not a
potion, and `sendGold` of gold above 20,000 when gold is above 40,000; print the gave line if
anything moved. Merchant trip: wait for a fighter with items to give; walk to each such fighter
and wait (10 s at most) until it gave all; walk to `fancypots`; sell `isLoot` items; `goToMap("bank")`;
deposit gold above 50,000; `goToMap("main")`. Check: `party-merchant 1`.

```
team: Tester, Healer, Archer; merchant: Merchy
in game as Tester (warrior, level 1) on main at -87,673
in game as Healer (priest, level 1) on main at -87,673
in game as Archer (ranger, level 1) on main at -87,673
in game as Merchy (merchant, level 1) on main at -87,673
party: Tester, Healer, Archer, Merchy
Merchy: walk to <fighter> at <x>,<y>
<fighter>: gave <n ≥ 1> item(s) and <gold> gold to Merchy
Merchy: walk to fancypots at -35,-162
Merchy: sold <n> item(s): +<gold> gold
Merchy: in the bank: deposited <gold> gold
Merchy: back on main at <x>,<y>
OK
```

## The local test server: `course/test-server`

One fake Adventure Land for the whole course: `node server.js` (Node 22, `socket.io@4.8.1`,
`ws@8.18.0`). It is not the game. It mirrors the live payload shapes for what the course uses
and cites the live code in comments. Settings (all optional; prefixed `TEST_` so they never
clash with the client variables):

| Variable | Default | Meaning |
|---|---|---|
| `TEST_PORT` | `8022` | HTTP, Socket.IO and the echo endpoint, all on one port. |
| `TEST_PING_INTERVAL`, `TEST_PING_TIMEOUT` | `4000`, `12000` | The live values (`node/server.js:83-84`). |
| `TEST_G_FILE` | `G.json` next to `server.js` | The game data. If the file is missing, the server downloads `https://adventure.land/data.js`, trims it and saves `G.json`. `scripts/check-course.py` passes `vendor/G/G_17478.json`. |
| `TEST_DROP_AFTER_MS` | off | Drop each character's socket once, this long after `start` (tests the reconnect rule). |
| `TEST_SAVE_MS` | `0` | After a character's socket closes, `auth` for it gets "Authorization in progress" for this long (the live save delay). |
| `TEST_RIP_MS` | `12000` | The respawn wait (`rip_time`, `node/server.js:224`). |
| `TEST_DAMAGE` | `1` | A multiplier for monster damage, to test potions and death. |
| `TEST_QUIET` | off | Do not print each event. |

Fixed test data (programs and `scripts/check-course.py` rely on these values):

- Account: email `tester@example.com`, password `test-password`; user `US_tester`; auth
  `0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef`.
- Characters: `Tester` (`CH_tester`, warrior), `Healer` (`CH_healer`, priest), `Archer`
  (`CH_archer`, ranger), `Merchy` (`CH_merchy`, merchant). All level 1. They start on `main`
  at spawn 5 (-87, 673), as a new live character does (`api.js:497`), with the starter gear of
  their class (weapon, helmet, shoes), `hpot0` × 10 and `mpot0` × 10 (gift items), and 10,000
  gold (live: 0; so that supplies and gear-up can buy before a kill). `Tester` starts at 40% hp
  so that a first program must heal. The goos are in view from there (live vision is ±700 px in
  x, ±500 px in y) and a straight line to them is clear of walls. Goos wander in
  `[-50, 702, 50, 872]` inside their G box. Respawn is at spawn 5 too; jail `leave` goes to
  spawn 0.
- Java's `HttpClient` asks for `Upgrade: h2c` on plain `http://`; the test server's `upgrade`
  handler closes such a request. Java code sets `HttpClient.Version.HTTP_1_1` (harmless on the
  live `https` site).
- Live facts the programs must follow: `start` and `player` have **no `name`**, only `id` (the
  name); `upgrade`/`compound` need `clevel` (the item's current level; `items` reads it from
  `me.items`); a successful attack `game_response` has no `success` key; the bank door replies
  `in_progress` and `new_map` comes later; chest gold is taxed 10%; a merchant gets no party
  share. NPCs used by Part 3: `fancypots` (-35, -162) potions, `basics` (-89, -165) gear,
  `scrolls` (-464, -96), `newupgrade` (-207, -220) upgrade/compound, `transporter` (-83, -441);
  the bank door at spawn 3 (168, -134).
- Servers: `EU I` at `/ws1/` and `US I` at `/ws2/`, same host and port; each has its own world.
  `address` in the server list is the `Host` header of the request, so the URLs work from
  `localhost` and from another Docker container.

HTTP: `POST /api/signup_or_login`, `POST /api/servers_and_characters`, `GET|POST
/api/get_servers`, `POST /api/create_character`, `GET /hub` (has `var VERSION='<n>'`),
`GET /data.js` (`var G={...};`). Test control: `POST /test/reset` (all worlds and accounts back
to the start), `POST /test/drop?character=Name` (close that socket now; no name: all),
`POST /test/jail?character=Name` (a line violation now: the live messages, then `jail`). Both
take `&after_start_ms=N`: armed, they run N ms after the next `start` of that character, once
(the character is found by name when they run, so a reconnect between does not matter);
`/test/reset` clears them.
`GET /test/stats` (counters as JSON, including `violations` and `maxcc`). A plain WebSocket
echo at `/echo`.

Socket (Socket.IO v4 at the server's `path`): `welcome` at connect; `loaded` → `entities`
(`type: "all"`); `auth` → `start` or the live failures; `ping_trig` → `ping_ack`;
`send_updates`; `player` and `entities` updates; `move` (walls from `G.geometry`: a move that
crosses a wall sends the character to `jail`, as a line violation does live); `attack`
(range, cooldown, damage, `hit`, `death`, `drop`, xp and level up); monsters that fight back;
death, `rip`, `respawn`; `use` (regen) and potions (`equip` with `consume`) with the potion
timer and `eval` `pot_timeout`; `open_chest` → `chest_opened`; `buy`/`sell` within 400 px of
the NPC that sells it; `equip`/`unequip`; doors and `transport` (`new_map`); `jail` and
`leave`; `party` invite/accept and `party_update`; `send` items and gold (400 px, same map);
`bank` `deposit`/`withdraw` of gold inside the bank (two answers, as live: `data` with place
`bank`, then `bank_store`/`bank_withdraw`; items and packs answer `invalid`);
`upgrade` and `compound` with `q` progress data and the result as hitchhikers; the call-cost
(`cc` in `player`, the `limitdc` kick). Each handler cites the live code it copies.

### Part 3 modules, per language

| Language | Notes |
|---|---|
| all | `Member` exists because `Bot` has no public constructor from parts in TS and Java; `connectMember` calls `Bot.connectWith` (`connect_with`, `ConnectWith`, `ConnectWithAsync`), which has each language's welcome-race handling. The farm program reads the lost reason **before** `close()`: our own close fires the local `disconnect` event. |
| ts | `Items.me` is `world.me` cast to `MeWithGear` (`World.Me` has no `slots`/`esize`). `Farmer` uses `act.msUntilRespawn()`. |
| python | `Grid.for_map(G, map_name)`, `Travel.go_to_map(map_name)`, `Travel.route(start, goal)`; `Hop` and `Npc` are frozen dataclasses (`Hop.map_name`); `Party.wait_invite(name, seconds=5)`; `farmer.where(e)` formats `x,y`. Prints use `flush=True`. |
| go | `travel.New`, `items.New`, `party.New`, `farmer.New`; `(value, error)` returns, `actions.ErrNoReply` for no answer; `Route` → `([]Hop, bool)`, `NPCSelling`/`NPCWithRole` → `(NPC, bool)`; `Find(name, level)` with `-1` = any level; `Compound(ctx, [3]int, ...)`; `WaitInvite(name, time.Duration)`; `Farmer` and `Party` state through methods (`Kills()`, `Type()`, `ClearTarget()`, `List()`). |
| csharp | `Team.ConnectMemberAsync`, `Team.CreateCharacterAsync` (no free functions); `record Npc(Id, X, Y)`, `record Hop(Map, X, Y, To, Spawn, By)`; `Grid.CellOf`; grid rounding `Math.Floor(v + 0.5)` (= JS `Math.round`). Chances print with `InvariantCulture`. |
| rust | `find`, `cell`, `nearest_free` return `Option`; `upgrade`/`compound` return `Option<GameResponse>`, fields through `items::field(&r, "chance")`; `FarmerState.kind` for `type`; `Grid::for_map` builds a new grid (`Travel` caches one per map). Ctrl-C only (no SIGTERM). |
| java | Nested records `Party.Member`, `Items.Npc`, `Travel.Hop`; `Farmer` and `Party` state through synchronized accessors (`kills()`, `type()`, `clearTarget()`, `list()`); overloads for defaults; `Grid.forMap` caches in an `IdentityHashMap`; `Locale.ROOT` for the chance. |

## Per-language notes (as built, 2026-10-04)

Where a language could not follow the JS names mechanically, or needed more. Parts 2 and 3
show these names; do not "fix" them back.

| Language | Notes |
|---|---|
| all | `request`/`openChest` give "no reply" on a timeout (null, `None`, `ErrNoReply`, `Ok(None)`); a closed socket is an error. Extra helpers: `Actions.openChest(id)` (first-kill prints each chest), a "time of death" / respawn-wait accessor (`diedAt`, `died_at`, `RespawnWait`, `respawn_ms_left`, `RespawnMsLeft`, `msUntilRespawn`). `distance`: an entity whose `type` is a key of `G.monsters` uses `G.dimensions` (24×24 if missing) × `size`; anything else is 26×36 (`node/server.js:11782-11783`). |
| js | `world.monsters`, `players`, `chests` are `Map`s, as in TS. The `types` region of gdata holds only the JSDoc typedef of `G`. |
| ts | `world.monsters`, `players`, `chests` are `Map`s. `move`/`moveTo` are async (they go through `budget.emit`). `tsconfig` sets `verbatimModuleSyntax` (Node's type stripping needs `import type`). |
| python | `request(..., timeout_ms=2000)`, `enter_game(..., timeout_ms=30000)`; `transport(map_name, spawn)`, `Grid.for_map(G, map_name)`, `nearest_monster(mtype=None)` (no shadowed builtins). Extra `Budget.wait_for_room(event)`. alsocket fix: websockets 13.1 has `ws.protocol.close_code`, not `ws.close_code`. |
| go | Go initialisms: `BaseURL`, `APICall`, `SocketURL`, `ID`. `ctx` is the first parameter of every network call; defaults are explicit arguments (`FindServer(servers, os.Getenv("AL_SERVER"))`). `ServersAndCharacters` returns `([]Server, []Character, error)`. `EnterGame(ctx, sock, auth, characterID, timeout, waitWelcome)`. `World` embeds `sync.Mutex`; `CopyMe`, `CopyMonster`, `ChestIDs` read under the lock. alsocket's `deliver` runs handlers before it wakes waiters. |
| csharp | `Auth(string User, string Token)` (a member cannot have its type's name). `GData` is one partial class (typed tables + `Raw`, and the static loaders). `EnterGameAsync(..., Task<JsonElement>? welcomeWait = null)`. All `World` state behind `world.Gate` (`lock (world.Gate) { ... }`). `Servers` and `Echo` do not reference `Albot`. |
| rust | `Actions::r#move` (`move` is a keyword). Field `g` for G. Defaults are `Option` parameters (`None` = the JS default). `download_g` returns `Value`. `World` is a Clone handle on `Arc<Mutex<WorldState>>`; the handlers are `WorldState` methods. `enter_game(sock, auth, id, timeout_ms, welcome: Option<Value>)`. alsocket's `deliver` runs handlers before it wakes waiters. |
| java | Records nested in their module: `Api.Auth`, `Api.Server`, `Api.Character`, `Actions.GameResponse`, `Bot.LoginError`, `GData.ItemDef`... Overloads stand in for default arguments. `enterGame` also exists as two halves, `waitWelcome` and `sendAuth`. `World` is `synchronized`; programs read inside `synchronized (world) { ... }`. All `HttpClient`s use HTTP/1.1. |
