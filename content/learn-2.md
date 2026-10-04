# Part 2 · Talking to Adventure Land

## Logging in and choosing a server

Part 1 gave you `AlSocket` and a local test server. Part 2 uses them to put a character into
the game world. Your character then reads the world, acts in it, and reads the replies. At the
end of the part, a program kills a monster and loots it: [Checkpoint: your first kill](#learn-hearing-back).

Part 2 adds seven modules to the library `albot`. Each chapter explains one or two of them:

| Module | What it does | Chapter |
|---|---|---|
| `api` | The HTTP API: login, the lists of servers and characters, the socket URL. | this chapter |
| `gdata` | The game data G: download it one time for each version, and keep it on disk. | [Getting the game data](#learn-getting-the-game-data) |
| `bot` | The handshake, and `Bot.connect()`, which does all the steps from login to `start`. | [Connecting and the handshake](#learn-connecting-and-the-handshake) |
| `world` | Your copy of the world: your character, the monsters, the players, the chests. | [Reading the world](#learn-reading-the-world) |
| `actions` | Move, attack, heal, loot and respawn. | [Acting in the world](#learn-acting-in-the-world) |
| `cooldowns`, `budget` | When each skill is ready again, and the limit on the events that you send. | [Hearing back](#learn-hearing-back) |

### Before you start this part

You need these items from Part 1:

- The tools of your language and the project folder (steps 3 and 4 of
  [Before you start](#learn-before-you-start)).
- The `alsocket` file of your language in the library folder ([AlSocket](#learn-alsocket)).
- The test server, which runs in its own terminal (step 6 of [Before you start](#learn-before-you-start)).

Then copy the complete library of your language into your project. The `bot` module imports
all the other modules. Thus, the program of
[Connecting and the handshake](#learn-connecting-and-the-handshake) compiles only when all the
files are there. The chapters show the important parts of each file, and each part is the real code
of the file.

1. Open the folder `course/<language>` of this site's repository.
2. Copy the library files of the table below into the same places in your project.
3. Keep your own `alsocket` file if it works. Else, copy that file too.
4. Compile the project one time, with the command of step 4 of
   [Before you start](#learn-before-you-start), or with the first program of this chapter.

| Language | Copy these files |
|---|---|
| JavaScript | `albot/*.js` |
| TypeScript | `albot/*.ts` |
| Python | `albot/*.py` (`__init__.py` too) |
| Go | each module folder: `api/`, `gdata/`, `world/`, `cooldowns/`, `budget/`, `actions/`, `bot/`, `pathfind/` |
| C# | `Albot/*.cs` |
| Rust | `src/lib.rs` and `src/*.rs` |
| Java | `src/main/java/albot/*.java` |

The library also has files for Part 3. Some of their functions throw "not implemented yet:
Part 3" until Part 3 explains them. Part 2 does not call them.

> **Warning:** Never write your password or your auth token in source code. The programs read
> them from the environment variables `AL_EMAIL`, `AL_PASSWORD` and `AL_AUTH` (step 5 of
> [Before you start](#learn-before-you-start)). A person with your auth token can play your
> characters and give away your items.

### The session

Your bot uses the website first, over HTTP. The website gives you a **session** and the
address of each game server. [The AL HTTP API](#learn-the-al-http-api) lists the quirks of
this API. The [HTTP API](#guide-http-api) reference lists each method.

The session is the proof that you logged in. It has two parts:

| Part | Example | Where it comes from |
|---|---|---|
| `user` | `US_tester` | The id of your account. |
| `auth` | 64 hex characters | An auth token. Each password login makes a new one. |

On the wire, the session is one cookie: `auth=<user>-<auth>`. The server splits the cookie at
the `-` (`adventure_functions.js:371-389`). The variable `AL_AUTH` holds the same text,
`<user>-<auth>`. The game socket needs the same two values again, in the `auth` event.

### The steps

1. Send `POST /api/signup_or_login` with `{"email": ..., "password": ..., "only_login": true}`.
2. If the reply does not have `success: true`, stop. Show the `reason`.
3. Keep `user` and `auth` from the reply.
4. Send `POST /api/servers_and_characters` with the body `{}` and the cookie `auth=<user>-<auth>`.
5. In the reply, find the item of `infs` with `type: "servers_and_characters"`.
6. Read the servers from its `servers` field, and your characters from its `characters` field.

Do steps 1 to 3 one time only. After that, `AL_AUTH` holds the session, and the programs start
at step 4.

### The code: one API call

`apiCall` sends one call. It sends a JSON body, and it adds the cookie when it has a session.
It fails only on an HTTP status other than 200. A game failure comes back with status 200 and
`failed: true`, so the caller reads the body.

<!-- include course/js/albot/api.js region=api-call -->

<!-- include course/ts/albot/api.ts region=api-call -->

<!-- include course/python/albot/api.py region=api-call -->

<!-- include course/go/api/api.go region=api-call -->

<!-- include course/csharp/Albot/Api.cs region=api-call -->

<!-- include course/rust/src/api.rs region=api-call -->

<!-- include course/java/src/main/java/albot/Api.java region=api-call -->

`baseUrl()` gives `AL_BASE_URL`, or `https://adventure.land` when the variable is empty. On the
test server, set `AL_BASE_URL` to `http://localhost:8022`.

### The code: log in

`login` reads `AL_AUTH` first. It uses the password only when `AL_AUTH` is empty. After a
password login, it prints the value to save, for bash and for PowerShell.

> **Caution:** Each password login adds a new auth token to your account. The account keeps
> at most 200 tokens. The next login after that deletes all of them, and each bot that uses an
> old token stops (`adventure_functions.js:331-341`). Log in with the password one time. Then
> use `AL_AUTH`.

<!-- include course/js/albot/api.js region=login -->

<!-- include course/ts/albot/api.ts region=login -->

<!-- include course/python/albot/api.py region=login -->

<!-- include course/go/api/api.go region=login -->

<!-- include course/csharp/Albot/Api.cs region=login -->

<!-- include course/rust/src/api.rs region=login -->

<!-- include course/java/src/main/java/albot/Api.java region=login -->

The value `only_login: true` tells the server to never make a new account. Without it, the
website refuses with `cant_signup_on_web` (`api.js:93`). A failed login gives one of these
reasons: `wrong_password`, `email_not_found`, `no_email`, `cant_login_inside_bank` or
`login_failed` (`api.js:84-127`). `cant_login_inside_bank` means that the account was in the
bank in the last 15 minutes.

The token does not expire with time. It stays valid until you call `logout_everywhere`, or
until the account reaches 200 tokens. If a call fails with `not_logged_in`, the token is not
valid. Then unset `AL_AUTH` and log in with the password again.

### The server list

`servers_and_characters` puts both lists in one item of `infs` (`api.js:451-470`). The code
finds the item by its `type`, not by its position:

<!-- include course/js/albot/api.js region=servers-and-characters -->

<!-- include course/ts/albot/api.ts region=servers-and-characters -->

<!-- include course/python/albot/api.py region=servers-and-characters -->

<!-- include course/go/api/api.go region=servers-and-characters -->

<!-- include course/csharp/Albot/Api.cs region=servers-and-characters -->

<!-- include course/rust/src/api.rs region=servers-and-characters -->

<!-- include course/java/src/main/java/albot/Api.java region=servers-and-characters -->

Each entry of `servers` describes one game server (`adventure_functions.js:761-776`):

| Field | Example | Meaning |
|---|---|---|
| `key` | `"SR_EUI"` | The database id of the server: `SR_`, then the region and the name. |
| `region` | `"EU"` | `EU`, `US` or `ASIA`. |
| `name` | `"I"` | `I`, `II`, `III`, `PVP`, ... |
| `players` | `42` | The number of characters online on it. |
| `address` | a host name | The host of the WebSocket. |
| `path` | `"/ws1/"` | The Socket.IO path on that host. [Connecting and the handshake](#learn-connecting-and-the-handshake) makes the URL from it. |
| `msgpack_path` | a URL path | An endpoint that uses MessagePack instead of JSON. The course does not use it. |

The list has only the servers that are online. The order is EU, US, ASIA, then by name
(`adventure_functions.js:673-690`).

`AL_SERVER` holds the region and the name together, without `SR_`: for example `EUI` or
`USII`. `findServer` compares `region + name` with it. If `AL_SERVER` is empty, it takes the
first server of the list.

<!-- include course/js/albot/api.js region=find-server -->

<!-- include course/ts/albot/api.ts region=find-server -->

<!-- include course/python/albot/api.py region=find-server -->

<!-- include course/go/api/api.go region=find-server -->

<!-- include course/csharp/Albot/Api.cs region=find-server -->

<!-- include course/rust/src/api.rs region=find-server -->

<!-- include course/java/src/main/java/albot/Api.java region=find-server -->

### The character list

Each entry of `characters` describes one of your characters (`adventure_functions.js:821-842`):

| Field | Meaning |
|---|---|
| `id` | The character id, for example `CH_tester`. The socket `auth` event needs this value, not the name. |
| `name` | The character name. In the game, the name is also the entity id of the character. `AL_CHARACTER` holds it. |
| `type` | The class: `warrior`, `paladin`, `rogue`, `ranger`, `mage`, `priest` or `merchant`. |
| `level` | The character level. |
| `online` | `0` when the character is offline. Else, the milliseconds since it was last online. |
| `server` | Only when the character is online: the key of its game server, for example `SR_EUI`. |
| `secret` | Only when the character is online: a value to watch it ([observing](#guide-observing-without-a-character)). |
| `rip` | Only when the character is dead. |
| `map`, `in`, `x`, `y` | Where the character was last. |

The characters that are online come first (`adventure_functions.js:850-852`). `findCharacter`
finds the character with the name in `AL_CHARACTER`. The names must be equal, with the same
case.

### Before you use your own client

> **Caution:** A custom client can get a penalty. An account from after 2019-02-01 needs a
> linked platform id. Without it, each character gets the `authfail` condition: luck −85,
> gold −85 and xp −20 (`node/server.js:11856-11870`). Step 2 of
> [Before you start](#learn-before-you-start) links the id. The
> [connecting guide](#guide-connecting-to-a-game-server) has the details.

> **Caution:** Confirm the email of your account. Until you do, each character gets the
> condition `notverified` when it starts: 25% less luck and 25% less gold from kills
> (`node/server.js:11814-11818`).

### The program: login

The program `login` logs in, then prints the servers and your characters. It does not open a
socket. It uses only the module `api`. The first column of each list gives the value for
`AL_SERVER` and for `AL_CHARACTER`.

<!-- include course/js/login.js -->

<!-- include course/ts/login.ts -->

<!-- include course/python/login.py -->

<!-- include course/go/cmd/login/main.go -->

<!-- include course/csharp/Login/Program.cs -->

<!-- include course/rust/src/bin/login.rs -->

<!-- include course/java/src/main/java/Login.java -->

Run it on the test server first:

1. Start the test server, if it does not run.
2. Set `AL_BASE_URL` to `http://localhost:8022`.
3. Set `AL_EMAIL` to `tester@example.com` and `AL_PASSWORD` to `test-password`. Unset `AL_AUTH`.
4. In your project folder, run the command of your language from the table below.
5. Copy the `export AL_AUTH=...` line (or the PowerShell line) from the output, and run it.
6. Run the program again. Now it uses `AL_AUTH`, and it does not print the three lines.
7. Set `AL_SERVER` to `EUI` and `AL_CHARACTER` to `Tester`.

| Language | Command |
|---|---|
| JavaScript | `node login.js` |
| TypeScript | `node login.ts` |
| Python | `python login.py` |
| Go | `go run ./cmd/login` |
| C# | `dotnet run --project Login` (make the project first, as for `AlTest` in step 4 of [Before you start](#learn-before-you-start)) |
| Rust | `cargo run --bin login` |
| Java | `mvn -q compile exec:java -Dexec.mainClass=Login` |

The first run prints this. The output is the same in all seven languages:

```
Logged in with the password. Save this value, and use it from now on:
  export AL_AUTH='US_tester-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'
  PowerShell: $env:AL_AUTH = 'US_tester-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'
user id: US_tester
servers (AL_SERVER, players, address, path):
  EUI        0  localhost:8022  /ws1/
  USI        0  localhost:8022  /ws2/
characters (AL_CHARACTER, class, level, id, status):
  Tester   warrior     1  CH_tester  offline
  Healer   priest      1  CH_healer  offline
  Archer   ranger      1  CH_archer  offline
  Merchy   merchant    1  CH_merchy  offline
```

Then run it one time on the real game: unset `AL_BASE_URL`, and set `AL_EMAIL` and
`AL_PASSWORD` of your account. Save the new `AL_AUTH`. Choose `AL_SERVER` and
`AL_CHARACTER` from the lists.

> **Warning:** The `AL_AUTH` line in the output is your login. Do not paste it into a chat, an
> issue or a screenshot.

If it fails:

| What you see | Cause | What to do |
|---|---|---|
| `set AL_AUTH, or AL_EMAIL and AL_PASSWORD` | No login in the environment. | Set the variables in this terminal. |
| A connection error (`fetch failed`, `ConnectError`, `connection refused`) | The test server does not run, or `AL_BASE_URL` is wrong. | Start the test server. Check `AL_BASE_URL`. |
| `login failed: wrong_password` or `email_not_found` | The email or the password is wrong. | Check `AL_EMAIL` and `AL_PASSWORD`. Do not try again in a loop. |
| `login failed: cant_login_inside_bank` | The account was in the bank in the last 15 minutes. | Wait, then try again. |
| An error that says that the token in `AL_AUTH` is not valid | `servers_and_characters` replied `not_logged_in`. | Unset `AL_AUTH`. Log in with the password again, and save the new value. |
| `<method>: HTTP <status>` | A proxy or the web server in front of the game replied. | Wait, then try again. |
| `no server <key>; the list has: ...` (later programs) | `AL_SERVER` is not in the list. | Use a value from the first column. |

## Getting the game data

**G** is one large JSON object with the static rules of the game: each item, monster, map,
skill and class. Your bot needs it for almost each decision. For example, a monster in the
world sends only the fields that are different from its entry in G. G for version 17478 is
about 2.8 MB. The reference entry [Getting G](#g-getting-g) has the details.

### The steps

1. Send `GET /hub`.
2. Find the text `var VERSION='<number>'` in the page. The number is the version of G.
3. If the file of that version is in the cache, read G from it and stop.
4. Send `GET /data.js`.
5. Cut the text from the first `{` to the last `}`. The body is `var G={...};`, so this part is JSON.
6. Parse the JSON. Save it in the cache for the next run.

None of these requests needs the session. The server writes `VERSION` into `/hub` from the
same value as `G.version` (`main.js:451`, `htmls/base_script.html:32`). Ask for `/hub`
directly. The old page `/comm` sends a 301 redirect to it (`main.js:167`), and some HTTP
clients do not follow redirects. If `VERSION` is not in the page, `loadG` downloads G each
time. That is slow, but correct.

### What is in G

G has more than 30 tables. The [table of all keys](#g-the-top-level-tables) lists each one.
These tables are the most important for a bot:

| Table | Key | What one entry tells you |
|---|---|---|
| [items](#g-items) | item name, for example `hpot0` | Type, price `g`, stack size `s`, what a potion `gives`. |
| [monsters](#g-monsters) | monster type, for example `goo` | Base `hp`, `attack`, `speed`, `range`, `frequency`, `xp`, `respawn`. |
| [maps](#g-maps) | map name, for example `main` | NPCs, monster spawns, doors, spawn points. |
| [geometry](#g-geometry) | map name | The walls. Part 3 uses them to find a path. |
| [npcs](#g-npcs) | NPC id | What a shop sells. |
| [skills](#g-skills) | skill name, for example `attack` | `cooldown`, `mp` cost, `range`, and `share` (the skill uses the cooldown of another skill). |
| [classes](#g-classes) | class name | Base stats and the stat gain for each level. |
| [dimensions](#g-dimensions) | monster or sprite type | The size of the hit box. |
| [levels](#g-levels) | level as a string | The xp for the next level. |

Note the units. Most durations in the game are **milliseconds**, but
`G.monsters[type].respawn` is in **seconds**. `speed` is in pixels per second. `frequency`
is in attacks per second.

### Typed structures

A typed language needs a type for each table that it reads. The library types only the fields
that the course uses, in four types: `ItemDef`, `MonsterDef`, `SkillDef` and `GData`. All other
tables stay raw JSON (Go `json.RawMessage`, C# `JsonObject`, Rust `Value`, Java `JsonNode`).
The JSON parsers ignore the fields that a type does not name. JavaScript and Python read G as
it is.

| Type | Fields |
|---|---|
| `ItemDef` | `name`, `type`, `g`, `s`, `gives`, `cooldown`; in TypeScript, Python and Rust also `compound` and `upgrade` (Part 3) |
| `MonsterDef` | `name`, `hp`, `attack`, `speed`, `range`, `frequency`, `xp`, `respawn`, `size`, `damage_type` |
| `SkillDef` | `name`, `type`, `cooldown`, `mp`, `range`, `share`, `class`, `level` |
| `GData` | `version`, `items`, `monsters`, `skills`, `dimensions`, and the raw tables |

Some fields need care:

- Some numbers are integers in one entry and decimals in another (`frequency`, `respawn`). Use a floating-point type.
- `gives` is a list of pairs, for example `[["hp", 200]]`. Each pair has a string and a number.
- `skills[...].target` is a boolean in some entries and a string in others. The library does not type it.
- Many fields are optional. Use an optional type, or a zero default.

<!-- include course/js/albot/gdata.js region=types -->

<!-- include course/ts/albot/gdata.ts region=types -->

<!-- include course/python/albot/gdata.py region=types -->

<!-- include course/go/gdata/gdata.go region=types -->

<!-- include course/csharp/Albot/GData.cs region=types -->

<!-- include course/rust/src/gdata.rs region=types -->

<!-- include course/java/src/main/java/albot/GData.java region=types -->

### The code: get G

`fetchVersion` reads the version from `/hub`. `downloadG` gets and parses `/data.js`:

<!-- include course/js/albot/gdata.js region=fetch-version -->

<!-- include course/ts/albot/gdata.ts region=fetch-version -->

<!-- include course/python/albot/gdata.py region=fetch-version -->

<!-- include course/go/gdata/gdata.go region=fetch-version -->

<!-- include course/csharp/Albot/GData.cs region=fetch-version -->

<!-- include course/rust/src/gdata.rs region=fetch-version -->

<!-- include course/java/src/main/java/albot/GData.java region=fetch-version -->

<!-- include course/js/albot/gdata.js region=download-g -->

<!-- include course/ts/albot/gdata.ts region=download-g -->

<!-- include course/python/albot/gdata.py region=download-g -->

<!-- include course/go/gdata/gdata.go region=download-g -->

<!-- include course/csharp/Albot/GData.cs region=download-g -->

<!-- include course/rust/src/gdata.rs region=download-g -->

<!-- include course/java/src/main/java/albot/GData.java region=download-g -->

`loadG` asks for the version first, because `/hub` is small. It downloads G only if the cache
does not have that version. The cache file is `.al-cache/<host>/G_<version>.json`, in the
folder where you run the program. `<host>` is the host and the port of `AL_BASE_URL`, with
`_` instead of `:`. Thus, the small G of the test server (`.al-cache/localhost_8022/`) never
mixes with the real G (`.al-cache/adventure.land/`).

<!-- include course/js/albot/gdata.js region=load-g -->

<!-- include course/ts/albot/gdata.ts region=load-g -->

<!-- include course/python/albot/gdata.py region=load-g -->

<!-- include course/go/gdata/gdata.go region=load-g -->

<!-- include course/csharp/Albot/GData.cs region=load-g -->

<!-- include course/rust/src/gdata.rs region=load-g -->

<!-- include course/java/src/main/java/albot/GData.java region=load-g -->

G can change while a server runs. The game server sends `version` in [`welcome`](#recv-welcome),
so you can compare it with your G. The event [`reloaded`](#recv-reloaded) tells you that the
server loaded new game data. If you get it, load G again.

### Where you see it run

This chapter has no program of its own. `Bot.connect()` calls `loadG` before it opens the
socket, so the program `connect` of
[Connecting and the handshake](#learn-connecting-and-the-handshake) uses it. On the first run, `connect`
prints this line before its other lines:

```
downloaded G version 17478
```

The next runs read the cache file and print nothing for G. Delete the folder `.al-cache` to
download G again.

If it fails:

| What you see | Cause | What to do |
|---|---|---|
| `data.js: HTTP <status>` | The website did not give G. | Check `AL_BASE_URL`. Wait, then try again. |
| A JSON parse error | The body of `/data.js` is not `var G={...};`, or the download stopped. | Open `<AL_BASE_URL>/data.js` in a browser and look at the start of the text. |
| `downloaded G version ...` on each run | The program cannot write the cache, or `/hub` has no `VERSION`. | Run the program in a folder where it can write. |

## Connecting and the handshake

A **handshake** is the fixed sequence of events at the start of a connection. Here it has four
events: `welcome`, `loaded`, `auth` and `start`. The module `bot` does it. The reference entry
[Connecting to a game server](#guide-connecting-to-a-game-server) has each detail.

This chapter needs `AL_AUTH`, `AL_CHARACTER` and `AL_SERVER` from
[Logging in and choosing a server](#learn-logging-in-and-choosing-a-server).

### The URL

The URL of the WebSocket is
`wss://<address><path>?EIO=4&transport=websocket&map_protocol=1&no_graphics=1`. The `address`
and the `path` come from the server list. The path must end with exactly one `/`: the server
does not know `/ws1` without the `/`. The scheme follows `AL_BASE_URL`: `ws` for `http`, and
`wss` for `https`.

The first two query parameters are the Engine.IO ones from [Socket.IO by hand](#learn-socket-io-by-hand).
The browser client also sends the last two (`js/game.js:1525`):

| Parameter | Why |
|---|---|
| `map_protocol=1` | You accept generated maps. Without it, the server throws the error `client_update_required` when it sends you one (`node/logic/generated_maps.js:186`). |
| `no_graphics=1` | The server sends generated maps without tile data. A bot does not draw tiles. |

<!-- include course/js/albot/api.js region=socket-url -->

<!-- include course/ts/albot/api.ts region=socket-url -->

<!-- include course/python/albot/api.py region=socket-url -->

<!-- include course/go/api/api.go region=socket-url -->

<!-- include course/csharp/Albot/Api.cs region=socket-url -->

<!-- include course/rust/src/api.rs region=socket-url -->

<!-- include course/java/src/main/java/albot/Api.java region=socket-url -->

Do not add a `secret` to the URL when you play a character. The `secret` is only for
[observing](#guide-observing-without-a-character) a character that is already online.

### The sequence

> **Caution:** Start to listen for `start` and for the failure events before you send `auth`.
> The server can send `start` very quickly. A handler that you add after the event arrives does
> not see it.

1. Open the socket with `AlSocket.connect(url)`.
2. Wait for [`welcome`](#recv-welcome). The server sends it at once, with `region`, `name`, `version`, `S` and a start position for the camera (`node/server.js:4977-5019`).
3. Listen for `start`, `game_error`, `game_log`, `disconnect_reason` and `disconnect`.
4. Send [`loaded`](#send-loaded) with `{"success": 1, "width": 1920, "height": 1080, "scale": 2}`.
5. Send [`auth`](#send-auth) with the fields in the table below.
6. Wait for [`start`](#recv-start). If a failure event arrives first, the login failed.

The server reads none of the fields of `loaded`. The browser sends the same fields
(`js/game.js:7452`). On `loaded`, the server makes an **observer** for your socket: a camera
that receives the events near it. Then it sends one [`entities`](#recv-entities) snapshot
(`node/server.js:5028-5054`). The server ignores `auth` with no reply until the observer
exists (`node/server.js:11583`).

| `auth` field | Value |
|---|---|
| `user` | The part of `AL_AUTH` before the first `-`. |
| `auth` | The part of `AL_AUTH` after the first `-`. |
| `character` | The `id` from the character list (`CH_...`), not the name. |
| `no_html` | `"1"`: a program controls this character. The server sets `afk` to `"code"`. |
| `passphrase` | `""`. Only `test` servers check it. |

The server also ignores `auth` with no reply if `user`, `character` or `auth` is not a string
(`node/server.js:11564-11571`). It adds the prefix `CH_` to the character id when the prefix
is not there (`node/server.js:11573`).

On success, `start` holds the complete state of your character. Its `id` is the character
**name**, not the `CH_` id. `start` has no `name` field. [Reading the world](#learn-reading-the-world)
reads it.

`enterGame` does steps 2 to 6. It returns the `welcome` payload. It does not return `start`:
the `World` of [Reading the world](#learn-reading-the-world) gets `start` through its own
handler.

<!-- include course/js/albot/bot.js region=enter-game -->

<!-- include course/ts/albot/bot.ts region=enter-game -->

<!-- include course/python/albot/bot.py region=enter-game -->

<!-- include course/go/bot/bot.go region=enter-game -->

<!-- include course/csharp/Albot/Bot.cs region=enter-game -->

<!-- include course/rust/src/bot.rs region=enter-game -->

<!-- include course/java/src/main/java/albot/Bot.java region=enter-game -->

### What can fail

`enterGame` fails with a `LoginError`. Its `reason` tells you what happened. The program stops
with an error that has the text `login failed: <reason>`.

| `reason` | What the server sent | Cause | What to do |
|---|---|---|---|
| `no_character` | `game_error` "Failed: no_character" | The character is not on this account. | Check `AL_CHARACTER`. |
| `password_issue` | `game_error` "Failed: password_issue" | The auth token is not valid. | Log in with the password again. |
| `ingame` | `game_error` "Failed: ingame" | The character record still names a game server: it is online, or its last save is not complete. | Follow [the reconnect rule](#learn-alsocket). |
| `mainframe_issue` | `game_error` "Failed: mainframe_issue" | Only when the `auth` has a `mainframe_session`. The course never sends one. | Remove `mainframe_session`. |
| `poker_hand_active` | `game_error` with its own message | A poker hand of this character still runs on another server. | Wait for the hand to end. |
| `cancelled` | `game_error` "Failed: cancelled" | The login took more than 60 s (`node/logic/character_sessions.js:3`). | Connect again. |
| `characters_unconfirmed` | `game_error` "Could not confirm your other characters" | The server could not read the other characters of your account (`node/server.js:11873-11876`). | Wait, then connect again. |
| `server_full` | `game_error` "Can't accept more than 200 players at this time" | The server is full (`node/server.js:11587`, `:11879`). | Use a different server. |
| `authorization_in_progress` | `game_log` "Authorization in progress." | A login for this character runs now, or the server still saves the character after a disconnect, or it is online on this server (`node/server.js:11577-11582`). No `start` comes on this socket. | Close the socket. Follow [the reconnect rule](#learn-alsocket). |
| `limits` | `disconnect_reason` `"limits"` | You have too many characters online. See [rate limits](#guide-rate-limits-and-anti-abuse). | Stop one of your other characters. |
| `timeout` | nothing in 30 s | You sent `auth` before `loaded`, or a field of `auth` is not a string. On a test server: a wrong `passphrase` (a `game_log` "Wrong passphrase!"). | Check the order and the fields. |
| other text | `disconnect` | The socket closed during the handshake. | Read the reason. Follow [the reconnect rule](#learn-alsocket). |

The `game_error` and `game_log` payloads are objects with a `message` text and a `phrase` key
(`languages/index.js:256-258`). The `auth` failures also have `reason`
(`node/server.js:11639-11652`). `errorReason` reads `reason` first, then the `phrase`. It does
not read the English text, because the text can change.

<!-- include course/js/albot/bot.js region=error-reason -->

<!-- include course/ts/albot/bot.ts region=error-reason -->

<!-- include course/python/albot/bot.py region=error-reason -->

<!-- include course/go/bot/bot.go region=error-reason -->

<!-- include course/csharp/Albot/Bot.cs region=error-reason -->

<!-- include course/rust/src/bot.rs region=error-reason -->

<!-- include course/java/src/main/java/albot/Bot.java region=error-reason -->

> **Caution:** Do not try again at once after a failure or a disconnect. The server keeps a
> character in its list of disconnected players until it saves it. Until then, each new `auth`
> gets "Authorization in progress". Use [the reconnect rule](#learn-alsocket) of Part 1: wait
> 30 s, then double the wait after each failed try, to a maximum of 300 s.

The `bot` module has the rule as a function. `attempt` counts the tries from 0. Part 3 uses
it in the bots that run for a long time:

<!-- include course/js/albot/bot.js region=reconnect-delay -->

<!-- include course/ts/albot/bot.ts region=reconnect-delay -->

<!-- include course/python/albot/bot.py region=reconnect-delay -->

<!-- include course/go/bot/bot.go region=reconnect-delay -->

<!-- include course/csharp/Albot/Bot.cs region=reconnect-delay -->

<!-- include course/rust/src/bot.rs region=reconnect-delay -->

<!-- include course/java/src/main/java/albot/Bot.java region=reconnect-delay -->

### Bot.connect: all the steps in one call

`Bot.connect()` reads the environment variables and does each step of Part 2 in order:

1. `login`, then `serversAndCharacters`.
2. `findServer` (`AL_SERVER`) and `findCharacter` (`AL_CHARACTER`).
3. `loadG`.
4. `AlSocket.connect(socketUrl(server))`.
5. Make the `World`, before the handshake, so that its handlers see `start`.
6. `enterGame`.
7. Make `Cooldowns`, `Budget` and `Actions`.

Steps 4 to 7 are a function of their own, `Bot.connectWith(auth, server, character, G)`.
Part 3 uses it to connect several characters after one login.

The result is a `Bot` with the fields `sock`, `G`, `world`, `cooldowns`, `budget`, `act`,
`auth`, `server`, `character` and `welcome`. `close()` closes the socket.

<!-- include course/js/albot/bot.js region=connect -->

<!-- include course/ts/albot/bot.ts region=connect -->

<!-- include course/python/albot/bot.py region=connect -->

<!-- include course/go/bot/bot.go region=connect -->

<!-- include course/csharp/Albot/Bot.cs region=connect -->

<!-- include course/rust/src/bot.rs region=connect -->

<!-- include course/java/src/main/java/albot/Bot.java region=connect -->

**The welcome race.** `AlSocket` keeps early events only until the first `on` or `waitFor`
of any name ([The design of AlSocket](#learn-alsocket)). In Go, C#, Rust and Java, the reader
of the socket runs on its own thread. There, `welcome` can arrive after `World` listens to its
events, and before the handshake waits for `welcome`. Then the socket discards `welcome`.

Thus, in these four languages, `connectWith` starts the wait for `welcome` before it makes the
`World`. JavaScript, TypeScript and Python run on one event loop, so the race cannot occur
there.

### The program: connect

The program `connect` calls `Bot.connect()`, prints a summary, and closes the socket.

<!-- include course/js/connect.js -->

<!-- include course/ts/connect.ts -->

<!-- include course/python/connect.py -->

<!-- include course/go/cmd/connect/main.go -->

<!-- include course/csharp/Connect/Program.cs -->

<!-- include course/rust/src/bin/connect.rs -->

<!-- include course/java/src/main/java/Connect.java -->

1. Start the test server, if it does not run.
2. Set `AL_BASE_URL` to `http://localhost:8022`, `AL_SERVER` to `EUI` and `AL_CHARACTER` to `Tester`.
3. Set `AL_AUTH` to the value that `login` printed.
4. Run the command of your language.

| Language | Command |
|---|---|
| JavaScript | `node connect.js` |
| TypeScript | `node connect.ts` |
| Python | `python connect.py` |
| Go | `go run ./cmd/connect` |
| C# | `dotnet run --project Connect` (make the project as for `Login`) |
| Rust | `cargo run --bin connect` |
| Java | `mvn -q compile exec:java -Dexec.mainClass=Connect` |

The first run prints this. The next runs do not print the first line:

```
downloaded G version 17478
welcome: EU I, version 17478
in game as Tester (warrior, level 1) on main at -87,673
OK
```

When the program closes the socket, the server saves the character and marks it offline. On
the real game, the save can take some seconds. If you run the program again at once, you can
get `authorization_in_progress` or `ingame`. That is the reason for the reconnect rule.

To check the penalties of [Before you use your own client](#learn-logging-in-and-choosing-a-server),
look at the `s` object of `world.me`. It must not have the key `authfail` or `notverified`.

If it fails:

| What you see | Cause | What to do |
|---|---|---|
| `login failed: <reason>` | The handshake failed. | Find the reason in [What can fail](#learn-connecting-and-the-handshake). |
| `no character named "<name>"; the list has: ...` | `AL_CHARACTER` is empty, or it is not the name of one of your characters. | Use a name from the output of `login`. The case must be the same. |
| `no server <key>; the list has: ...` | `AL_SERVER` is not in the server list. | Use a value from the output of `login`, or leave it empty. |
| A compiler error about a missing module | A library file is missing. | Copy all the files of [Before you start this part](#learn-logging-in-and-choosing-a-server). |
| `login failed: timeout` on the test server | The program waited for `welcome` after it listened to other events (the welcome race). | Compare `bot` with the file in `course/<language>`. |

## Reading the world

After `start`, the server sends a stream of events about the world near you. The module
`world` keeps a local copy of that world: your character (`me`), the monsters, the other
players and the chests. This chapter shows how the copy stays correct.

You do not add code to a program in this chapter. `Bot.connect()` makes the `World` for you.
Each program reads `bot.world`. If you write your own connect code, make the `World` after
`AlSocket.connect` and before you send `loaded`.

An **entity** is anything with a position: a monster, a player or an NPC. An **instance** is
one copy of a map. On normal maps, the instance id (`in`) is equal to the map name (`map`).
Dungeons get a random instance id, so two parties can be in two copies of the same map.

Each entity is the JSON object of the server, as it arrived. A `player` update merges into it
field by field, and an `entities` update replaces it. Each language keeps it in its own type
for a JSON object that you can change:

| Language | Entity type |
|---|---|
| JavaScript, TypeScript | a plain object (TypeScript adds interfaces for the fields that the course reads) |
| Python | `dict` |
| Go | `world.Entity`, a `map[string]any` with the helpers `Num`, `Str` and `Bool` |
| C# | `JsonObject` |
| Rust | `Entity`, a `serde_json::Map<String, Value>` |
| Java | Jackson `ObjectNode` |

A helper that reads a number gives 0 for a missing field.

> **Caution:** In Go, C#, Rust and Java, the handlers of `World` run on the thread of the
> socket, and your program runs on another thread. Read the world under its lock: Go
> `w.Lock()` (or `CopyMe`), C# `lock (world.Gate)`, Rust `world.lock()` (or `world.me()`), Java
> `synchronized (world)`.

### The handlers

The constructor listens to nine events. Each handler changes one part of the world:

<!-- include course/js/albot/world.js region=constructor -->

<!-- include course/ts/albot/world.ts region=constructor -->

<!-- include course/python/albot/world.py region=constructor -->

<!-- include course/go/world/world.go region=constructor -->

<!-- include course/csharp/Albot/World.cs region=constructor -->

<!-- include course/rust/src/world.rs region=constructor -->

<!-- include course/java/src/main/java/albot/World.java region=constructor -->

### One table of handlers: listen and dispatch

A **hitchhiker** is an event that the server does not send alone. It puts the event in the
`hitchhikers` array of the next `player` event, as an `[event, payload]` pair. Upgrade results,
new conditions and some cooldowns arrive this way (see [delivery helpers](#guide-delivery-helpers)).
Handle each pair as if it arrived as its own event.

Thus, the `World` keeps one table from an event name to its handlers. `listen` adds a handler
to the table. `dispatch` calls the handlers of a name. An event from the socket and a
hitchhiker go through the same `dispatch`, so a handler does not need to know how its event
arrived. Use `world.listen`, not `sock.on`, for each event that can be a hitchhiker.

<!-- include course/js/albot/world.js region=listen -->

<!-- include course/ts/albot/world.ts region=listen -->

<!-- include course/python/albot/world.py region=listen -->

<!-- include course/go/world/world.go region=listen -->

<!-- include course/csharp/Albot/World.cs region=listen -->

<!-- include course/rust/src/world.rs region=listen -->

<!-- include course/java/src/main/java/albot/World.java region=listen -->

### Your character: start and player

[`start`](#recv-start) holds the complete private state of your character. "Private" means
that it includes the fields that other players never see: `items`, `gold`, `xp` and more.
These fields are the most useful for a bot:

| Field | Meaning |
|---|---|
| `id` | Your character name. Your entity id is your name. |
| `x`, `y`, `map`, `in` | Where you are. |
| `m` | The map counter. It changes on each map change. [`move`](#send-move) needs it. |
| `hp`, `max_hp`, `mp`, `max_mp` | Health and mana. |
| `level`, `xp`, `max_xp`, `gold` | Progress. |
| `ctype` | The class, for example `warrior`. |
| `items` | The inventory: an array with `null` for an empty slot. |
| `slots` | The equipped items, by slot name (`mainhand`, `helmet`, ...). |
| `s` | The conditions on you: `{name: {ms, ...}}`, with the milliseconds left. |
| `speed`, `range`, `frequency`, `attack` | Combat and movement stats. |
| `moving`, `going_x`, `going_y` | Where you walk to. |
| `rip` | `true`, or the name of a gravestone cosmetic, while you are dead. |
| `cc` | Your call-cost now ([Hearing back](#learn-hearing-back)). |
| `entities` | A first snapshot of the world around you. |

`onStart` keeps the payload as `me`, without `entities`. Then it reads `entities` as a normal
update:

<!-- include course/js/albot/world.js region=on-start -->

<!-- include course/ts/albot/world.ts region=on-start -->

<!-- include course/python/albot/world.py region=on-start -->

<!-- include course/go/world/world.go region=on-start -->

<!-- include course/csharp/Albot/World.cs region=on-start -->

<!-- include course/rust/src/world.rs region=on-start -->

<!-- include course/java/src/main/java/albot/World.java region=on-start -->

[`player`](#recv-player) arrives after almost each change to your character. It is again the
complete private state, never a partial update. The server builds it with
`player_to_client(player)` (`node/server.js:855-1003`, `:4578`). A few fields of `start`
(`home`, `friends`, `s_info`, ...) are not in `player`. Thus `onPlayer` **merges** each
`player` into `me`: it copies each field over the field in `me`, and keeps the other fields.

JSON has no `undefined`, so a field with that value is absent. An example is `target` when you
have no target.

<!-- include course/js/albot/world.js region=on-player -->

<!-- include course/ts/albot/world.ts region=on-player -->

<!-- include course/python/albot/world.py region=on-player -->

<!-- include course/go/world/world.go region=on-player -->

<!-- include course/csharp/Albot/World.cs region=on-player -->

<!-- include course/rust/src/world.rs region=on-player -->

<!-- include course/java/src/main/java/albot/World.java region=on-player -->

### Other entities: entities

[`entities`](#recv-entities) has a `type`:

- `"all"`: a **snapshot**, the complete list of each entity that you can see. Delete your old lists, then keep this one.
- `"xy"`: only the entities that changed since the last update.

In both types, each entity object is the complete current state of that entity. Replace your
copy, and do not merge. The live code says it plainly: "complete payloads only"
(`node/server.js:13705`). Each `entities` event also has `in`. If it is not your instance,
ignore the event: it is about a map that you left.

Monsters are a special case. A monster sends `hp`, `max_hp`, `speed` and some other stats
**only when they are different** from `G.monsters[type]` (`node/server.js:1003-1028`). A
monster with full health has no `hp` field. `withDefaults` fills the missing fields from G.
G has no `max_hp`: the `hp` of G is the full health.

A `type: "all"` snapshot can include your own character (`node/server_functions.js:3681-3687`).
`applyEntities` skips the entity whose `id` is your name. Your own state comes from `player`.

<!-- include course/js/albot/world.js region=apply-entities -->

<!-- include course/ts/albot/world.ts region=apply-entities -->

<!-- include course/python/albot/world.py region=apply-entities -->

<!-- include course/go/world/world.go region=apply-entities -->

<!-- include course/csharp/Albot/World.cs region=apply-entities -->

<!-- include course/rust/src/world.rs region=apply-entities -->

<!-- include course/java/src/main/java/albot/World.java region=apply-entities -->

### Removing entities

| Event | When | What the handler does |
|---|---|---|
| [`death`](#recv-death) `{id}` | A monster died. | Deletes the monster. |
| [`disappear`](#recv-disappear) `{id, reason?, outside?}` | An entity left: a door, a teleport, a disconnect, invisibility, or it left your view. | Deletes the monster or the player. |
| [`chest_opened`](#recv-chest_opened) `{id, ...}` | A chest was opened, by you or by another character. | Deletes the chest. |

The server records what it sent to each client. When an entity leaves your view, the server
sends `disappear` with `outside: true` (`node/server.js:13697-13702`). Before each
`type: "all"` snapshot, it also sends `disappear` for each entity that is not in the new
snapshot (`node/server_functions.js:3697-3701`). Thus, if you delete on `disappear`, your lists
stay correct.

If you think that your lists are wrong, send [`send_updates`](#send-send_updates) `{}`. The
server replies with a new `type: "all"` snapshot. It costs 13 call-cost
([Hearing back](#learn-hearing-back)). Do not send it often.

### A new map: new_map

[`new_map`](#recv-new_map) arrives when you go to another map or instance: a door, a teleport,
a respawn, the jail. It has `name` (the map), `in`, `x`, `y`, `m` and an `entities` snapshot.
`onNewMap` copies these into `me`. `m` is the **map counter**: the server adds 1 to it on each
map change. The new `m` is important, because the server ignores a `move` with an old `m`.

<!-- include course/js/albot/world.js region=on-new-map -->

<!-- include course/ts/albot/world.ts region=on-new-map -->

<!-- include course/python/albot/world.py region=on-new-map -->

<!-- include course/go/world/world.go region=on-new-map -->

<!-- include course/csharp/Albot/World.cs region=on-new-map -->

<!-- include course/rust/src/world.rs region=on-new-map -->

<!-- include course/java/src/main/java/albot/World.java region=on-new-map -->

### Units

| Quantity | Unit | Example |
|---|---|---|
| Position (`x`, `y`) | map pixels, decimals allowed. `y` grows down. | `{"x": -12.5, "y": 340}` |
| `speed` | pixels per second | a `speed` of 55 walks 110 px in 2 s |
| `frequency` | attacks per second | the attack cooldown is `round(1000 / frequency)` ms (`node/server.js:1627`) |
| Durations: `ms`, cooldowns, `eta` | milliseconds | `s.poisoned.ms = 3000` |
| `G.monsters[type].respawn` | **seconds** | `goo` respawns after 1 s |
| `online` in the character list | milliseconds | |

More conventions are in [units and conventions](#guide-units-and-conventions).

The field `in` is a keyword in Python and in Rust. Use the key as a string: `me["in"]` in
Python, `me["in"]` or `e.get("in")` in Rust. A struct field in Rust needs
`#[serde(rename = "in")]`. The library keeps entities as JSON objects, so it has no struct
field with that name.

### Moving entities between updates

The server sends a position only when something changes, for example when a monster starts to
walk. Between updates, the entity walks in a straight line at its `speed`. The server moves an
entity by `speed * ms / 1000` pixels for each step, in the direction of `going_x`, `going_y`
(`node/server.js:15129-15131`). `step` does the same for one entity:

<!-- include course/js/albot/world.js region=step -->

<!-- include course/ts/albot/world.ts region=step -->

<!-- include course/python/albot/world.py region=step -->

<!-- include course/go/world/world.go region=step -->

<!-- include course/csharp/Albot/World.cs region=step -->

<!-- include course/rust/src/world.rs region=step -->

<!-- include course/java/src/main/java/albot/World.java region=step -->

`advance` steps `me`, the monsters and the players by the time since the last `advance`, or
since the update that brought them. There is no timer in the background. Call `advance` before
you read a position. The programs call it once in each loop.

<!-- include course/js/albot/world.js region=advance -->

<!-- include course/ts/albot/world.ts region=advance -->

<!-- include course/python/albot/world.py region=advance -->

<!-- include course/go/world/world.go region=advance -->

<!-- include course/csharp/Albot/World.cs region=advance -->

<!-- include course/rust/src/world.rs region=advance -->

<!-- include course/java/src/main/java/albot/World.java region=advance -->

### Distance and range

The server does not measure range from the center of one entity to the center of the other. It
measures the gap between two **hit boxes** (`js/old_common_functions.js:707-740`). A box has
its center at `x`, and its bottom edge at `y` (the feet). A monster has the box of
`G.dimensions[type]`, times `G.monsters[type].size`. A monster type with no entry in
`G.dimensions` has a box of 24 × 24 px. A character has a box of 26 × 36 px
(`node/server.js:11782-11783`).

Two boxes that touch have a distance of 0.

Use `distance` for each range check. An attack with a distance more than your `range` fails
with `too_far`.

<!-- include course/js/albot/world.js region=distance -->

<!-- include course/ts/albot/world.ts region=distance -->

<!-- include course/python/albot/world.py region=distance -->

<!-- include course/go/world/world.go region=distance -->

<!-- include course/csharp/Albot/World.cs region=distance -->

<!-- include course/rust/src/world.rs region=distance -->

<!-- include course/java/src/main/java/albot/World.java region=distance -->

`nearestMonster(type)` uses `distance` to find the closest monster of a type, or of any type.
The checkpoint program of [Hearing back](#learn-hearing-back) uses it to find a goo.

## Acting in the world

To act, you send an event. Then you watch for the result. The module `actions` has one method
for each action. This chapter shows five of them: move, attack, heal, loot and respawn. Each
section gives the payload, the replies and the failures.

Two rules apply to each method:

1. Each event goes through `budget.emit`, so that the bot stays under the call-cost limit.
2. A method that waits for a reply starts the wait before it sends the event.

Most methods use `request`: it sends an event and waits for the `game_response` about it.
[Hearing back](#learn-hearing-back) explains `request`, the call-cost and the cooldowns.

### Moving

Game guide: [Maps and the world](#game-maps-and-the-world).

Send [`move`](#send-move) with your current position, the destination and the map counter:

```json
{"x": -87, "y": 673, "going_x": -20, "going_y": 720, "m": 0}
```

The server does not reply. It starts to move you in a straight line at your `speed`. It does
not find a path around walls for you. If your `x`, `y` is more than 132 px from the position on
the server, the server sends [`correction`](#recv-correction) `{x, y}`
(`node/server.js:11248-11256`). The `World` then uses that position.

> **Caution:** Do not walk through walls. A `move` that starts or ends on a blocked cell sends
> your character to the map `jail` (`node/server.js:11211-11240`). Send [`leave`](#send-leave)
> to come out of it. The server walks the straight line also through a wall. Time on blocked
> cells adds to a "red zone" counter. When the counter is too high, the server takes half of
> your HP plus 1,000 and moves you (`node/server.js:15134-15156`).

Part 3 finds a path around the walls of `G.geometry`.

The server ignores a `move` with no reply in these cases (`node/server.js:11203`):

- `m` is not equal to the map counter of the server.
- You cannot walk, for example when you have the `stunned` condition.
- The destination is your current position.

No event tells you that you arrived. `moveTo` calculates the time: the distance divided by
`speed`, plus 250 ms for the network. It waits that long. Then it calls `advance`, and compares
your position with the destination. `move` alone starts the walk and does not wait.

<!-- include course/js/albot/actions.js region=move-to -->

<!-- include course/ts/albot/actions.ts region=move-to -->

<!-- include course/python/albot/actions.py region=move-to -->

<!-- include course/go/actions/actions.go region=move-to -->

<!-- include course/csharp/Albot/Actions.cs region=move-to -->

<!-- include course/rust/src/actions.rs region=move-to -->

<!-- include course/java/src/main/java/albot/Actions.java region=move-to -->

### Attacking

Game guide: [Stats and combat](#game-stats-and-combat) (how the server calculates a hit, and
the attack speed).

Send [`attack`](#send-attack) `{"id": "<target id>"}`. A monster id is a string, for example
`"12"` on the test server. A player id is the name of the player. The server handles `attack`
as the skill `attack` (`node/server.js:11003-11005`), so all the checks of [`skill`](#send-skill)
apply.

On success, you get these events:

1. [`game_response`](#recv-game_response) with `response: "data"`, `place: "attack"` and the
   fields of the attack: `attacker`, `target`, `pid` (the projectile id), `eta` (the
   milliseconds until the hit) and `damage`. It has no `success` key.
2. [`skill_timeout`](#recv-skill_timeout) `{name: "attack", ms}`: the cooldown starts.
3. [`action`](#recv-action): the same attack, for each client near you.
4. [`hit`](#recv-hit) when the projectile arrives: `id` (the target), `hid` (the attacker),
   `damage`, and `kill: true` if the target died.
5. [`death`](#recv-death) for a dead monster, and maybe [`drop`](#recv-drop) for a chest.

On failure, `game_response` has `failed: true` and a code. These codes are the most frequent:

| Code | Meaning |
|---|---|
| [`cooldown`](#code-cooldown) | Too early. `ms` tells how long to wait. |
| [`too_far`](#code-too_far) | The target is out of range. `dist` is your distance to it (`node/server.js:10030`). |
| [`no_mp`](#code-no_mp) | Not enough MP. |
| [`attack_failed`](#code-attack_failed) | The attack could not start, for example because of the level gap. |
| [`friendly`](#code-friendly) | The target is friendly, or you are in a safe zone. |
| [`disabled`](#code-disabled) | You are stunned or disabled. |

If the target does not exist, you do not get a `game_response`. You get
[`disappear`](#recv-disappear) `{id, reason: "not_there", place: "attack"}`. Then `attack`
gives "no reply" after 2 s (null in JavaScript).

The attack cooldown is `round(1000 / frequency)` milliseconds. The server writes it into
`G.skills.attack.cooldown` before each check (`node/server.js:1627`, `:9778`).

<!-- include course/js/albot/actions.js region=attack -->

<!-- include course/ts/albot/actions.ts region=attack -->

<!-- include course/python/albot/actions.py region=attack -->

<!-- include course/go/actions/actions.go region=attack -->

<!-- include course/csharp/Albot/Actions.cs region=attack -->

<!-- include course/rust/src/actions.rs region=attack -->

<!-- include course/java/src/main/java/albot/Actions.java region=attack -->

### Healing with potions

Game guide: [Stats and combat](#game-stats-and-combat) (cooldowns and mana) and
[Items and equipment](#game-items-and-equipment) (what a new character has).

There are two ways to heal:

| Event | Payload | Effect | Cooldown |
|---|---|---|---|
| [`equip`](#send-equip) | `{"num": <slot>, "consume": true}` | Drinks the potion in inventory slot `num`. It adds what `G.items[name].gives` lists, for example 200 HP for `hpot0`. | `G.items[name].cooldown`, else 2,000 ms (`node/server.js:7826-7878`) |
| [`use`](#send-use) | `{"item": "hp"}` or `{"item": "mp"}` | Free regeneration: `G.skills.regen_hp.output` or `G.skills.regen_mp.output` (50 HP or 100 MP in G 17478). | 4,000 ms (`node/server.js:11988-12024`) |

All potions and the free regeneration use one shared timer. The library calls it `"potion"`.
On success, you get an [`eval`](#recv-eval) `{code: "pot_timeout(<ms>)"}`, a `player` update
with the new HP or MP, then `game_response` `{response: "data", place: "equip"}` (or
`place: "use"`). If the timer still runs, you get [`not_ready`](#code-not_ready) with `ms`.

`heal(stat)` looks for a potion that gives `stat` in the inventory. If it finds one, it drinks
it with `equip`. Else, it sends `use`. It does nothing, and gives false, while the `"potion"`
timer runs.

<!-- include course/js/albot/actions.js region=heal -->

<!-- include course/ts/albot/actions.ts region=heal -->

<!-- include course/python/albot/actions.py region=heal -->

<!-- include course/go/actions/actions.go region=heal -->

<!-- include course/csharp/Albot/Actions.cs region=heal -->

<!-- include course/rust/src/actions.rs region=heal -->

<!-- include course/java/src/main/java/albot/Actions.java region=heal -->

### Looting chests

Game guide: [Drops and loot](#game-drops-and-loot) (who gets the loot, and the chest rules).

When you kill a monster, the server can send [`drop`](#recv-drop) with a chest:
`{id, x, y, map, chest, items}`. The `World` keeps it in `chests`. Send
[`open_chest`](#send-open_chest) `{"id": ...}` to take it. The result is
[`chest_opened`](#recv-chest_opened) with `gold` and `items`, or `{id, gone: true}` if the chest
does not exist now.

- If you are more than 400 px from the chest, you get only the base gold (`goldm: 1, dry: true`).
- A chest that is older than 8 minutes also gives only the base gold (`stale: true`).
- [`loot_no_space`](#code-loot_no_space): your inventory is full. No `chest_opened` comes.
- [`loot_failed`](#code-loot_failed): you are on the map `woffice`, on a map with `mount` (the
  bank maps), or invisible. A chest that belongs to another character also gives it.

The server checks these in `node/server.js:11273-11320`. `openChest` waits 2 s for
`chest_opened`. `openChests` opens each chest that the `World` knows. It deletes the chest from
the list also when no reply came, so that it does not try one chest again and again.

<!-- include course/js/albot/actions.js region=open-chests -->

<!-- include course/ts/albot/actions.ts region=open-chests -->

<!-- include course/python/albot/actions.py region=open-chests -->

<!-- include course/go/actions/actions.go region=open-chests -->

<!-- include course/csharp/Albot/Actions.cs region=open-chests -->

<!-- include course/rust/src/actions.rs region=open-chests -->

<!-- include course/java/src/main/java/albot/Actions.java region=open-chests -->

### Dying and respawning

Game guide: [Stats and combat](#game-stats-and-combat) (death and respawn) and
[Leveling and progression](#game-leveling-and-progression) (the xp that a death costs).

When a monster kills you, you get [`game_response`](#recv-game_response)
[`defeated_by_a_monster`](#code-defeated_by_a_monster) `{monster, xp}`, where `xp` is the xp
that you lost. Your `rip` field becomes `true`, or the name of a gravestone. You cannot act
while you are dead.

1. Wait 12 s after the death. This is `B.rip_time` (`node/server.js:224`, `:6282-6286`).
2. Send [`respawn`](#send-respawn) `{}`. Send `{"safe": true}` to go to the map `woffice` instead.
3. Wait for `game_response` `{response: "data", place: "respawn", success: true}`.

Before that reply, you get [`new_map`](#recv-new_map) (with `effect: 1`) and a `player` with
`rip: false`. HP is full and MP is half. If you are too early, you get
[`cant_respawn`](#code-cant_respawn) with the `ms` left. If you are not dead, you get
[`invalid`](#code-invalid) (`node/server.js:6271-6286`).

`respawn` waits for the rest of the 12 s from the time of death. If the server still says
`cant_respawn`, it waits the `ms` of the reply and tries one more time.

<!-- include course/js/albot/actions.js region=respawn -->

<!-- include course/ts/albot/actions.ts region=respawn -->

<!-- include course/python/albot/actions.py region=respawn -->

<!-- include course/go/actions/actions.go region=respawn -->

<!-- include course/csharp/Albot/Actions.cs region=respawn -->

<!-- include course/rust/src/actions.rs region=respawn -->

<!-- include course/java/src/main/java/albot/Actions.java region=respawn -->

### Buying from an NPC

A bot also buys potions and sells loot. These actions need more than one event: the bot walks
to an NPC, and the NPC must be within 400 px. Part 3 teaches them in its chapter on supplies,
with the code to walk around walls ([Supplies, loot and gear](#learn-supplies-loot-and-gear)). Until then, the
potions of the start are enough. A new character on the test server has 10 `hpot0` and 10 `mpot0`.

## Hearing back

Most events that you send get an answer in [`game_response`](#recv-game_response). This
chapter shows how to read that answer, how to wait for it, how to stay under the rate limit,
and how to track cooldowns. It ends with the checkpoint program of Part 2.

### The shapes of game_response

Usually, `game_response` is an object:

| Field | Meaning |
|---|---|
| `response` | The code, for example `"data"`, `"cooldown"`, `"too_far"`. |
| `place` | The event that it answers. For a skill, it is the skill name, not `"skill"`. |
| `failed` | `true` for a failure. |
| `success` | `true` for some successes. A successful attack has no `success` key. |
| other fields | They depend on the code, for example `ms` for `cooldown`. |

Some handlers send a bare string instead, for example `"distance"` (see the known quirks in
[`game_response`](#recv-game_response)). The code [`data`](#code-data) means "the generic
answer": read `failed`. Other codes name the result, for example
[`buy_success`](#code-buy_success) or [`buy_cant_space`](#code-buy_cant_space). The table in
`game_response` lists all 225 codes. Each code has its own entry, for example
[`too_far`](#code-too_far).

Some answers do not come as `game_response`. `open_chest` answers with `chest_opened`. A
missing target gives `disappear`. Upgrade results arrive later as hitchhikers. Read the
**Server replies** part of the entry of each event.

`normalize` gives each `game_response` one shape. `responseFor(place)` is the predicate that
finds the answer to one event:

<!-- include course/js/albot/actions.js region=normalize -->

<!-- include course/ts/albot/actions.ts region=normalize -->

<!-- include course/python/albot/actions.py region=normalize -->

<!-- include course/go/actions/actions.go region=normalize -->

<!-- include course/csharp/Albot/Actions.cs region=normalize -->

<!-- include course/rust/src/actions.rs region=normalize -->

<!-- include course/java/src/main/java/albot/Actions.java region=normalize -->

### Waiting for a reply

`waitFor` waits for one event that matches a **predicate**: a function that returns true for
the event that you want. It also takes a timeout. To wait for the answer to a request:

> **Caution:** Do step 1 before step 2. If you send first, a fast reply can arrive before
> `waitFor` listens, and you wait until the timeout.

1. Start `waitFor("game_response", responseFor(place))`.
2. Send the event.
3. Wait for the result of step 1.
4. If the timeout ends first, treat the request as "no reply".

In Go, `WaitFor` blocks, so `request` uses `Expect`: it registers the wait and returns a
function. In all other languages, `waitFor` registers the wait when you call it. `request`
keeps the promise, coroutine, task or future, then emits, then waits.

<!-- include course/js/albot/actions.js region=request -->

<!-- include course/ts/albot/actions.ts region=request -->

<!-- include course/python/albot/actions.py region=request -->

<!-- include course/go/actions/actions.go region=request -->

<!-- include course/csharp/Albot/Actions.cs region=request -->

<!-- include course/rust/src/actions.rs region=request -->

<!-- include course/java/src/main/java/albot/Actions.java region=request -->

`game_response` has no request id. If you send two `buy` events at the same time, you cannot
know which answer belongs to which. Send one request for each `place` at a time. A hitchhiker
`game_response` arrives inside `player`, so `waitFor("game_response")` does not see it. Use
`world.listen` for those.

### Call-cost and kicks

Game guide: [rate limits](#guide-rate-limits-and-anti-abuse) has the full rules.

The server counts a **call-cost** for each socket. If the total for the last 4 s is more than
the limit, the server disconnects you. The rules are in `node/server.js:242-258` and
`:4892-4943`:

- Each event costs 1, plus the extra cost in the table below.
- The limit is 200 for a socket with a character, and 50 (200 / 4) for a socket without one.
- Each map change adds 8: a door, `town`, a respawn, a `join` (`add_call_cost(player, 8, "transport")`, `node/server.js:4726`).
- An event that makes the server send `player` again adds up to 2 more (`resend`, `node/server.js:4555-4576`).
- An event whose handler throws an exception adds 16, and you get `game_error` `"ERROR!"` (`node/server.js:4944-4966`).

| Event | Extra cost | Event | Extra cost |
|---|---|---|---|
| `auth` | 2 | `equip` | 3 |
| `move` | 1.5 | `unequip` | 6 |
| `send_updates` | 12 | `players` | 12 |
| `cruise` | 10 | `random_look` | 10 |
| `secondhands` | 16 | `friend` | 24 |
| `ccreport` | 3 | `tracker` | 50 |

> **Caution:** Over the limit, the server sends [`limitdcreport`](#recv-limitdcreport), then
> `disconnect_reason` `"limitdc"`, then it closes the socket. You must do the full handshake
> again on a new socket. Follow [the reconnect rule](#learn-alsocket).

Your current cost is the `cc` field of `start` and `player`. `Budget` keeps a second count on
your side. Its limit is 150, not 200, because the extra cost of `resend` is not visible before
you send. A `move` costs 2.5, so 150 allows 60 moves in 4 s. That is much more than a bot
needs.

`Budget` adds 8 on each `new_map`. `budget.emit` waits until the last 4 s have room for the
event, then sends it.

<!-- include course/js/albot/budget.js region=budget -->

<!-- include course/ts/albot/budget.ts region=budget -->

<!-- include course/python/albot/budget.py region=budget -->

<!-- include course/go/budget/budget.go region=budget -->

<!-- include course/csharp/Albot/Budget.cs region=budget -->

<!-- include course/rust/src/budget.rs region=budget -->

<!-- include course/java/src/main/java/albot/Budget.java region=budget -->

> **Caution:** Send each event through `budget.emit`, also the events that the library does not
> send. A `sock.emit` that bypasses the budget is not in the count.

### Cooldowns

Game guide: [Stats and combat](#game-stats-and-combat) (cooldowns, attack speed and mana).

A **cooldown** is the time that you must wait before you use a skill or a potion again. The
server keeps the true timer. `Cooldowns` keeps a copy, so that the bot does not send requests
that fail. These events tell you about cooldowns:

| Event | Payload | Meaning |
|---|---|---|
| [`skill_timeout`](#recv-skill_timeout) | `{name, ms, penalty?, reason?}` | A cooldown started. The server sends it after each skill and attack. |
| [`game_response`](#recv-game_response) [`cooldown`](#code-cooldown) | `{skill, id, ms, place}` | You were too early. `ms` is the time left. |
| [`game_response`](#recv-game_response) [`not_ready`](#code-not_ready) | `{ms, place}` | The potion timer still runs. |
| [`eval`](#recv-eval) | `{code: "pot_timeout(2000)"}` | The potion timer started (`node/server.js:7878`, `:12023`). |
| [`eval`](#recv-eval) | `{code: "skill_timeout('ethereal',120)"}` | A cooldown started. A few skills use this form (`node/server.js:9608`). |

`eval` carries JavaScript for the browser client, in the field `code`. `Cooldowns` reads only
the two calls above, with a regular expression. It never runs the code. It also accepts a bare
string, in case a server sends one.

Some skills use the cooldown of another skill: `G.skills[name].share`. For example, `3shot`
and `5shot` share the cooldown of `attack`. When one starts, `Cooldowns` starts both.

A map change adds a penalty to your next cooldown. With a transport effect, the server adds
812 ms to the condition `penalty_cd`. Without one, it adds 3,200 ms. The maximum is 120,000 ms
(`node/server.js:4740-4742`). The next skill adds up to 10,000 ms of it to its cooldown
(`node/server_functions.js:3449-3467`). The `ms` in `skill_timeout` already includes it.

`Cooldowns` listens through `world.listen`, so a cooldown that arrives as a hitchhiker also
counts:

<!-- include course/js/albot/cooldowns.js region=cooldowns -->

<!-- include course/ts/albot/cooldowns.ts region=cooldowns -->

<!-- include course/python/albot/cooldowns.py region=cooldowns -->

<!-- include course/go/cooldowns/cooldowns.go region=cooldowns -->

<!-- include course/csharp/Albot/Cooldowns.cs region=cooldowns -->

<!-- include course/rust/src/cooldowns.rs region=cooldowns -->

<!-- include course/java/src/main/java/albot/Cooldowns.java region=cooldowns -->

### Checkpoint: your first kill

Game guide: [Leveling and progression](#game-leveling-and-progression) (xp from a kill).

The program `first-kill` uses all of Part 2. It connects, heals, walks to the nearest goo,
kills it, opens its chest, and closes. A **goo** is the weakest monster of the game: 100 HP,
5 attack, and it does not attack first. Goos live on `main`, near the place where a new
character starts.

Its loop runs every 100 ms:

1. Call `advance`.
2. If the character is dead, respawn.
3. If HP is less than 70% of `max_hp` and the potion timer is ready, heal.
4. If there is no target, take the nearest goo.
5. If the goo is out of range, `moveTo` a point at `range - 10` px from the goo. The 10 px is a
   margin, because the goo moves while you walk.
6. Else, attack when `attack` is ready.

The program stops when the goo dies: a `death` event, or a `hit` with `kill`. Then it waits up
to 3 s for the chest, opens it, prints the xp, and closes. If there is no kill in 90 s, it
fails.

<!-- include course/js/first-kill.js -->

<!-- include course/ts/first-kill.ts -->

<!-- include course/python/first_kill.py -->

<!-- include course/go/cmd/first-kill/main.go -->

<!-- include course/csharp/FirstKill/Program.cs -->

<!-- include course/rust/src/bin/first-kill.rs -->

<!-- include course/java/src/main/java/FirstKill.java -->

Run it on the test server. The test server keeps its world between runs. Reset it first, so
that `Tester` starts again with 40% HP and level 1:

1. Start the test server, if it does not run.
2. Reset it. On Linux and macOS: `curl -X POST http://localhost:8022/test/reset`. On Windows
   PowerShell: `Invoke-RestMethod -Method Post http://localhost:8022/test/reset`.
3. Keep the variables of `connect`: `AL_BASE_URL`, `AL_AUTH`, `AL_SERVER=EUI` and `AL_CHARACTER=Tester`.
4. Run the command of your language.

| Language | Command |
|---|---|
| JavaScript | `node first-kill.js` |
| TypeScript | `node first-kill.ts` |
| Python | `python first_kill.py` |
| Go | `go run ./cmd/first-kill` |
| C# | `dotnet run --project FirstKill` (make the project as for `Login`) |
| Rust | `cargo run --bin first-kill` |
| Java | `mvn -q compile exec:java -Dexec.mainClass=FirstKill` |

The output is the same in all seven languages. The id of the chest is random:

```
in game as Tester (warrior, level 1) on main at -87,673
heal hp: 450/624
target: goo 12 at -4,727
killed goo 12
chest DwhxL3ariE6ZMU04AZs7PhImYnUAsP: +90016 gold, 5 item(s)
xp: 100/200, level 1
OK
```

The first chest of each character carries the first-drop bonus of the live game, so the gold
is large. A `heal hp` line comes each time that the program heals. If the character dies, two
more lines come: `died; respawn in <s> s` and `respawned at <x>,<y>`. Start the test server
with `-e TEST_DAMAGE=20` to see them.

If you run it again without a reset, the output is different, and that is correct. `Tester`
has more than 70% HP, so no `heal hp` line comes. The goo gives no first-drop bonus, and the
xp brings `Tester` to level 2:

```
in game as Tester (warrior, level 1) on main at -33,721
target: goo 14 at -11,731
killed goo 14
chest zE1618zptSKoiuslK0Sa2mUtWa0DI3: +21 gold, 0 item(s)
xp: 0/250, level 2
OK
```

On the real game, the character must be on `main`, near the goos. A new character starts
there. Unset `AL_BASE_URL`, and set `AL_SERVER` and `AL_CHARACTER` to your values.

> **Caution:** `first-kill` walks in straight lines. On the real game, a wall between your
> character and the goo can send the character to `jail`, or cost HP. Start from the spawn
> point of `main`, where the line to the goos is clear.

If it fails:

| What you see | Cause | What to do |
|---|---|---|
| `no kill in 90 s` | No goo is in view: the character is not on `main` near the goos. | On the test server, reset it. On the real game, walk the character to the goos in the game client, then run the program. |
| No `heal hp` line | The character has 70% HP or more. | Reset the test server. On the real game, this is normal. |
| `login failed: authorization_in_progress` or `ingame` | The last run is still saving the character. | Wait 30 s ([the reconnect rule](#learn-alsocket)), then run it again. |
| `died; respawn in 12 s` again and again | The monsters do more damage than the potions heal. | On the test server, start it without `TEST_DAMAGE`. On the real game, attack a goo, not a stronger monster. |
| `respawn failed` | No `respawn` reply came. | Look at the output of the test server. The character must be dead (`rip`) when it sends `respawn`. |
| A disconnect with `limitdc` | The program sent too many events. | Send each event through `budget.emit`. |
| The character is on `jail` | A `move` started or ended on a blocked cell. | Send [`leave`](#send-leave), or use the game client. Part 3 walks around walls. |

You can now log in, connect, read the world, act and read the results. Part 3 puts these parts
together into bots that farm, buy supplies, run a party and upgrade gear:
[Designing a bot](#learn-designing-a-bot).
