## Before you start

This course is for a programmer who wants to write an Adventure Land bot in their own language.
It goes from zero to a party that levels, loots and gears up. You know how to code, and you know HTTP,
JSON and async I/O. You know the idea of a WebSocket. You do not need to know the game or its
protocol. The course teaches the parts that are specific to Adventure Land (AL), and the
practical side of WebSockets.

![The Mainland town in the official client, with characters, NPCs and the CODE panel](img/learn/town.png "The official client in the Mainland town. Your program replaces this client: it sends the same events to the same servers.")

The course builds one small library, **albot**, chapter by chapter, and a set of programs that
use it. Each part adds modules to the same project. At the end of each part, you run a program
against a local test server, and later against the real game.

### What Adventure Land uses for each part

| Task | Protocol | Where |
|---|---|---|
| Log in, get the list of your characters | HTTP `POST`, JSON | `https://adventure.land/api/<method>` |
| Get the list of game servers | HTTP, JSON | `https://adventure.land/api/get_servers` |
| Get the game data **G** (items, monsters, maps) | HTTP `GET` | `https://adventure.land/data.js` |
| Play: move, attack, see the world | Socket.IO v4 over a WebSocket | `wss://<address><path>`, from the server list |

**Socket.IO** is a small protocol on top of a WebSocket. It gives each message an event name,
such as `move` or `attack`, and it keeps the connection alive with its own pings. Each game
server runs Socket.IO (`node/server.js:81-87`). The website and the game servers are different
hosts. Your bot talks to the website first, then to one game server.

![A bot sends HTTP requests to adventure.land and Socket.IO events to a game server](img/learn/client-server.png "Your bot talks to two hosts: the website over HTTP, then one game server over Socket.IO.")

### The map of this course

| Part | Chapters | What you get |
|---|---|---|
| Part 1 · The wire | Before you start, [The AL HTTP API](#learn-the-al-http-api), [WebSockets in practice](#learn-websockets-in-practice), [Socket.IO by hand](#learn-socket-io-by-hand), [AlSocket](#learn-alsocket), [A local game server](#learn-a-local-game-server) | `alsocket`: a Socket.IO client that you write yourself, and a fake game server to test it on. |
| Part 2 · Talking to Adventure Land | [Logging in](#learn-logging-in-and-choosing-a-server), [the game data](#learn-getting-the-game-data), [the handshake](#learn-connecting-and-the-handshake), [reading the world](#learn-reading-the-world), [acting](#learn-acting-in-the-world), [hearing back](#learn-hearing-back) | `api`, `gdata`, `bot`, `world`, `actions`, `cooldowns` and `budget`, and the program `first-kill`: a character that kills a monster and loots it. |
| Part 3 · Building a bot | [Designing a bot](#learn-designing-a-bot) and the next chapters | `pathfind`, `travel`, `items`, `party` and `farmer`, and the programs `farm`, `supplies`, `party-merchant` and `gear-up`: bots that farm, buy supplies, run a party with a merchant, and upgrade gear. |

Two other pages help you on the way:

- The **game guide** ([start here](#game-what-adventure-land-is)) tells how the game works:
  classes, combat, items, the economy.
- The **API reference** documents each event, each response code, the game data and the server
  events. A link such as [`attack`](#send-attack) opens its entry.

### What you need

- A computer with Linux, macOS or Windows, and a terminal. On Windows, use PowerShell.
- One of these languages: JavaScript, TypeScript, Python, Go, C#, Rust or Java.
- Docker, for the local test server (step 6). It can also run your language (step 3).
- A copy of Adventure Land on Steam or on the Mac App Store, for the account (step 1). Part 1
  does not need the account. Part 2 needs it.

### Step 1: Make an account and play a little

The website does not let you make an account with an email and a password. It refuses with
the reason `cant_signup_on_web` ("Create your account in your purchased copy of Adventure
Land", `api.js:93`). There are two correct ways:

| Way | What you do |
|---|---|
| The game client | Get the game on [Steam](https://store.steampowered.com/app/777150/) or the [Mac App Store](https://itunes.apple.com/app/adventure-land-code-mmorpg/id1442098247?mt=12). Start it, and sign up there with an email and a password. |
| Sign Up with Steam | If you own the game on Steam, open [adventure.land/steam-signup](https://adventure.land/steam-signup) in a browser. Steam confirms that you own the game. Then you choose an email and a password (`steam_signup.js:51-62`). |

Then do these steps:

1. Write down the email and the password. Your program uses them one time, in Part 2.
2. Open the email from Adventure Land and confirm your address.
3. Make your first character. Choose a class and a name of 4 to 12 letters and digits
   (`api.js:24-31`).
4. Play for 15 minutes. Walk on the map, attack a small monster, and drink a potion.
5. Look at the server list in the game. Each server has a region and a name, for example
   EU I.

For step 2: until you confirm your email, each character gets the condition `notverified`.
It removes 25% of your luck and 25% of your gold from kills (`node/server.js:11814-11818`).

For step 3: make a class that fights. The game guide recommends a ranger or a mage for a first
bot ([Classes](#game-classes)). The bots of Part 3 do not fight with a merchant.

![The seven classes: warrior, paladin, rogue, ranger, mage, priest and merchant](img/learn/classes.png "The seven classes, drawn with sprites from the game. You select the class when you make the character, and you cannot change it.")

For step 4: your bot does the same things that you do with the mouse. If you know how the game
looks, the messages of the server are easier to understand. The game guide starts at
[What Adventure Land is](#game-what-adventure-land-is).

### Step 2: Log in one time through the Steam or Mac App Store client

> **Caution:** A custom client can get a penalty. Link a Steam or Mac App Store id to your
> account first. Without it, each character that logs in from your program can get the
> condition `authfail`: luck −85%, gold −85%, xp −20% (`node/server.js:11856-11870`).

The server sets `authfail` when two things are true:

- You made the account after 2019-02-01. The server then marks the character with `drm`
  (`adventure_functions.js:856-859`).
- The account has no platform id (`pid`). The server saves the Steam id or the Mac App Store
  id as `pid` when you play through that client (`adventure_functions.js:933-968`).

Do these steps one time:

1. Start the game through Steam or through the Mac App Store app.
2. Log in with your email and your password.
3. Enter the game with one character.
4. Close the game.

An account from "Sign Up with Steam" already has its Steam id (`api.js:160`). Do the steps
anyway. They take one minute.

To check the result, log in on [adventure.land](https://adventure.land) in a browser and enter
the game. Look at the condition icons of your character. If you see "Authorization Failure",
the link did not work. Do the steps again. Later, your program can check it too: the `s`
object of the [`start`](#recv-start) event must not have the key `authfail`.

The update notes of 2026-03-22 say "no more 'authfail' condition" for new users of the web
version (`update_notes.js:552-556`). The check is still in the code. It is unclear from the
source which accounts it still reaches, so do the steps.

### Step 3: Install the tools of your language

Install the runtime of your language, at the version in this table or later. The course pins
each package to one version, so that the code in the course compiles the same way on your
computer.

| Language | Runtime | Packages (exact versions) | Docker image |
|---|---|---|---|
| JavaScript | Node.js 22.18 | none to run; `typescript@5.6.3` and `@types/node@22.10.0` to check the JSDoc types | `node:22` |
| TypeScript | Node.js 22.18 (it runs `.ts` files directly) | `typescript@5.6.3`, `@types/node@22.10.0` | `node:22` |
| Python | Python 3.11 | `httpx==0.27.2`, `websockets==13.1` | `python:3.12-slim` |
| Go | Go 1.22 | `github.com/coder/websocket v1.8.13` (v1.8.14 and later need Go 1.23) | `golang:1.22` |
| C# | .NET 8 SDK | none | `mcr.microsoft.com/dotnet/sdk:8.0` |
| Rust | Rust 1.80 | `tokio 1.40`, `tokio-tungstenite 0.24`, `futures-util 0.3`, `serde 1`, `serde_json 1`, `reqwest 0.12` | `rust:1` |
| Java | Java 21 and Maven 3 | `com.fasterxml.jackson.core:jackson-databind:2.18.2` | `maven:3-eclipse-temurin-21` |

The block for your language has the install commands and a version check:

```js
// JavaScript: Node.js 22.18 or later.
// Linux:   install nvm (https://github.com/nvm-sh/nvm), then:  nvm install 22
// macOS:   brew install node
// Windows: winget install OpenJS.NodeJS.LTS
// Check (expect v22.18.0 or later):
node --version
```

```ts
// TypeScript: Node.js 22.18 or later. From 22.18, node runs .ts files directly.
// Linux:   install nvm (https://github.com/nvm-sh/nvm), then:  nvm install 22
// macOS:   brew install node
// Windows: winget install OpenJS.NodeJS.LTS
// Check (expect v22.18.0 or later):
node --version
```

```python
# Python 3.11 or later.
# Linux:   sudo apt install python3 python3-venv     (Ubuntu 24.04 has 3.12)
# macOS:   brew install python
# Windows: winget install Python.Python.3.12
# Check (expect 3.11 or later; on Windows, the command is python, not python3):
python3 --version
```

```go
// Go 1.22 or later.
// Linux and macOS: download it from https://go.dev/dl/, or: brew install go
// Windows: winget install GoLang.Go
// Check (expect go1.22 or later):
go version
```

```csharp
// .NET 8 SDK.
// Linux:   sudo apt install dotnet-sdk-8.0
// macOS:   download the .NET 8 SDK installer from https://dotnet.microsoft.com/download/dotnet/8.0
// Windows: winget install Microsoft.DotNet.SDK.8
// Check (expect 8.0.x in the list):
dotnet --list-sdks
```

```rust
// Rust (stable), with cargo.
// Linux and macOS: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
// Windows: winget install Rustlang.Rustup   (it asks you to install the C++ build tools)
// Check (expect 1.80 or later):
cargo --version
```

```java
// Java 21 (JDK) and Maven.
// Linux:   sudo apt install openjdk-21-jdk maven
// macOS:   brew install --cask temurin@21, then: brew install maven
// Windows: winget install EclipseAdoptium.Temurin.21.JDK, then get Maven from
//          https://maven.apache.org/download.cgi and add its bin folder to PATH.
// Check (expect version "21" and Apache Maven 3.x):
java -version
mvn -v
```

#### Or use Docker for your language

If you do not want to install the tools, run them in the Docker image of the table. Start a
shell in the image, in your project folder (step 4). Put the image name at the end:

```sh
docker run --rm -it -v "$PWD":/w -w /w --add-host=host.docker.internal:host-gateway \
  -e AL_BASE_URL -e AL_EMAIL -e AL_PASSWORD -e AL_AUTH -e AL_SERVER -e AL_CHARACTER \
  -e AL_WS_URL -e AL_ECHO_URL -e AL_RECONNECT_MS node:22 bash
```

In PowerShell, write `${PWD}` instead of `"$PWD"`, and write the command on one line. In the
container, `localhost` is the container itself. To reach the test server on your computer, use
the host name `host.docker.internal` instead of `localhost` in each URL of step 5.

### Step 4: Make the project folder

Make one project folder for the course, for example `al-course`. The library goes in a folder
or package named `albot` inside it. The programs go next to it. Each part adds files to the
same project. The finished project of each language is in the folder `course/<language>` of
this site's repository. Use it to compare when your code does not work.

| Language | The library | A program | Run a program |
|---|---|---|---|
| JavaScript | `albot/alsocket.js`, ... | `al-test.js` | `node al-test.js` |
| TypeScript | `albot/alsocket.ts`, ... | `al-test.ts` | `node al-test.ts` |
| Python | `albot/__init__.py` (empty), `albot/alsocket.py`, ... | `al_test.py` | `python al_test.py` |
| Go | one package for each module: `alsocket/alsocket.go`, ... | `cmd/al-test/main.go` | `go run ./cmd/al-test` |
| C# | the class library `Albot/` (`Albot.csproj`, `AlSocket.cs`, ...) | one console project for each program: `AlTest/` | `dotnet run --project AlTest` |
| Rust | the library crate: `src/lib.rs`, `src/alsocket.rs`, ... | `src/bin/al-test.rs` | `cargo run --bin al-test` |
| Java | `src/main/java/albot/AlSocket.java`, ... (package `albot`) | `src/main/java/AlTest.java` | `mvn -q compile exec:java -Dexec.mainClass=AlTest` |

These commands make the folder and the project file. Run them one time:

```js
// JavaScript: package.json with "type": "module" (the course uses import/export).
mkdir al-course
cd al-course
mkdir albot
npm init -y
npm pkg set type=module
// Optional: check the JSDoc types of the course code with the TypeScript compiler.
npm i -D typescript@5.6.3 @types/node@22.10.0
```

```ts
// TypeScript: node runs the .ts files; tsc only checks the types.
mkdir al-course
cd al-course
mkdir albot
npm init -y
npm pkg set type=module
npm i -D typescript@5.6.3 @types/node@22.10.0
// Then make tsconfig.json with the text in the next tab group. Check the types with: npx tsc
```

```python
# Python: one virtual environment (.venv) for the packages.
mkdir al-course
cd al-course
mkdir albot
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
# Make requirements.txt with the text in the next tab group, then:
pip install -r requirements.txt
# In each new terminal, activate .venv again before you run a program.
```

```go
// Go: one module, named albot. Each module of the course is a package in it.
mkdir al-course
cd al-course
go mod init albot
go get github.com/coder/websocket@v1.8.13
```

```csharp
// C#: a class library for albot, and one console project for each program.
mkdir al-course
cd al-course
dotnet new sln -n Course
dotnet new classlib -n Albot --framework net8.0
rm Albot/Class1.cs            // Windows PowerShell: Remove-Item Albot/Class1.cs
dotnet sln add Albot
// For each program (here AlTest): a console project that uses the library.
dotnet new console -n AlTest --framework net8.0
dotnet add AlTest reference Albot
dotnet sln add AlTest
```

```rust
// Rust: one package with a library crate (src/lib.rs) and one binary per program (src/bin/).
cargo new --lib al-course --name albot
cd al-course
// Then replace Cargo.toml with the text in the next tab group.
```

```java
// Java: one Maven project. The pom.xml is in the next tab group.
// On Windows PowerShell, leave out -p.
mkdir -p al-course/src/main/java/albot
cd al-course
```

The project file of your language, with the pinned versions:

<!-- include course/js/package.json lang=js -->

<!-- include course/ts/tsconfig.json lang=ts -->

<!-- include course/python/requirements.txt lang=python -->

<!-- include course/go/go.mod lang=go -->

<!-- include course/csharp/Albot/Albot.csproj lang=csharp -->

<!-- include course/rust/Cargo.toml lang=rust -->

<!-- include course/java/pom.xml lang=java -->

The first program, [the list of game servers](#learn-the-al-http-api), checks that the folder
is correct.

### Step 5: Set the environment variables

> **Warning:** Do not write your email, your password or your auth token in a program. Code
> goes to Git repositories, screenshots and chat messages. A person with your auth token can
> play your characters and give away your items.

The programs of the whole course read these variables. The last column gives the value for
the local test server of step 6.

| Variable | Used by | What it holds | Default | Test server |
|---|---|---|---|---|
| `AL_BASE_URL` | each program that uses HTTP | The website and its HTTP API. The game socket uses `ws` for `http` and `wss` for `https`. | `https://adventure.land` | `http://localhost:8022` |
| `AL_EMAIL` | `login` (Part 2), one time | The email of your account. | none | `tester@example.com` |
| `AL_PASSWORD` | `login` (Part 2), one time | The password of your account. | none | `test-password` |
| `AL_AUTH` | each program that logs in | Your session: `<userID>-<authToken>`. When it is set, no program sends the password. | none | printed by `login` |
| `AL_SERVER` | each program that enters the game | The game server: region and name together, for example `EUI`. Empty means the first server of the list. | the first server | `EUI` |
| `AL_CHARACTER` | each program that enters the game | The name of the character that the program plays. | none (required) | `Tester` |
| `AL_WS_URL` | `al-test` (Part 1) | The full WebSocket URL of a game server. | `ws://localhost:8022/ws1/?EIO=4&transport=websocket` | the default |
| `AL_ECHO_URL` | `echo` (Part 1) | The URL of a WebSocket echo server. | `ws://localhost:8022/echo` | the default |
| `AL_RECONNECT_MS` | the long-running bots (Part 3) | The first wait of [the reconnect rule](#learn-alsocket), in ms. | `30000` | `2000` |

You need the email and the password for one login only. That login gives you a token, and the
program prints it in a form that you can paste. After that, you set `AL_AUTH`, and the programs
stop using the password. [Logging in and choosing a server](#learn-logging-in-and-choosing-a-server)
explains why this is important.

Set a variable before you start the program. The value stays until you close that terminal.
On Linux and macOS (bash or zsh):

```sh
export AL_BASE_URL='http://localhost:8022'
export AL_CHARACTER='Tester'
export AL_SERVER='EUI'
echo "$AL_CHARACTER"        # check: prints Tester
unset AL_BASE_URL           # back to the real game
```

On Windows PowerShell:

```powershell
$env:AL_BASE_URL = 'http://localhost:8022'
$env:AL_CHARACTER = 'Tester'
$env:AL_SERVER = 'EUI'
echo $env:AL_CHARACTER      # check: prints Tester
Remove-Item Env:AL_BASE_URL # back to the real game
```

Use single quotes around a value. Then the shell does not change characters such as `$` or
`!` in a password.

### Step 6: Start the local test server

> **Warning:** The real game servers are not for tests. A bug can disconnect you many times,
> use your login limits, or send events that your character does not want to send. Test each
> program on the local test server first.

The course has one fake Adventure Land for all its programs. It is a Node.js program in the
folder `course/test-server` of the repository. It answers the HTTP API, serves a copy of G, runs
two small game servers, and has a WebSocket echo endpoint. [A local game server](#learn-a-local-game-server)
explains what it does. Start it now, and keep it running in its own terminal:

1. Copy the folder `course/test-server` from the repository.
2. Open a new terminal in that folder.
3. Run the command below. The first start downloads the packages and a copy of G.

```sh
docker run --rm -it -p 8022:8022 -v "$PWD":/w -w /w node:22 sh -c "npm ci && node server.js"
```

With Node.js 22 on your computer, `npm ci`, then `node server.js`, does the same. The server
listens on port 8022. It prints each event that it receives, so you can see what your program
really sent.

### How to read this course

- **Read the chapters in order.** Each chapter adds to the code of the chapters before it.
- **Choose your language one time.** Use the menu "Code" at the top of the page, or click a
  tab. The page then shows that language on all examples, on all three pages.
- **Run each program against the test server first.** Compare the output with the output in
  the text.

When you are stuck:

1. Read the error message from the start. The first line is usually the cause.
2. Compare your file with the same file in `course/<language>`.
3. Read what the test server printed. It shows each event that your program sent.
4. Search the API reference for the event name or the `reason` text.
5. Ask in the [Adventure Land Discord](https://discord.gg/44yUVeU)
   (`adventure_functions.js:543`). Its coding channels answer bot questions.

## The AL HTTP API

Your bot uses HTTP before it opens a socket: to log in, to get the list of game servers and to
get the game data. The HTTP itself is ordinary. These are the parts that are specific to
Adventure Land:

| Quirk | What to do |
|---|---|
| An API call is a `POST` to `/api/<method>` with a JSON body (`common:handlers.js:34-150`). A few methods, such as `get_servers`, also accept `GET` (`api.js:2260`, `common:handlers.js:54-60`). | Send JSON. Do not use form fields. |
| A failure comes back with **HTTP status 200**, and `"failed": true` with a `"reason"` in the body, for example `{"failed":true,"reason":"invalid_call"}` (`send_json` in `common_engine`). | Always read the body. A status other than 200 comes from the web server in front of the game. |
| Some methods put their data only in an `infs` array of "info objects", each with a `type` (`common:handlers.js:28-32`). | Find the item of the type that you want. |
| The session is the cookie `auth=<userID>-<authToken>` (`api.js:113`, `adventure_functions.js:371-389`). The login reply also has `user` and `auth` in its body (`api.js:116`). | Make the cookie yourself. You do not need a cookie jar. |
| The `pvp` field of a server is `""` for a normal server and `true` for a PvP server. | Do not decode it as a boolean. The examples do not read it. |
| `/comm` sends you to `/hub` with a 301 redirect (`main.js:167`). Python `httpx` and Java `HttpClient` do not follow redirects by default. | Ask for the final URL. |

[Logging in and choosing a server](#learn-logging-in-and-choosing-a-server) shows the login. The
[HTTP API](#guide-http-api) reference lists every method.

### Example: the list of game servers

This program gets the list of game servers and prints a socket URL for each. The list is
public, so the program needs no login (`get_servers` in `api.js:884-900`). It reads
`AL_BASE_URL`, so it works on the test server and on the real game. It is standalone: it uses
no file of the library.

1. Start the test server (step 6 of [Before you start](#learn-before-you-start)).
2. Put the program of your language in your project folder, with the file name in its first
   comment.
3. Set `AL_BASE_URL` to `http://localhost:8022`.
4. Run it with the command in its first comment.

<!-- include course/js/servers.js -->

<!-- include course/ts/servers.ts -->

<!-- include course/python/servers.py -->

<!-- include course/go/cmd/servers/main.go -->

<!-- include course/csharp/Servers/Program.cs -->

<!-- include course/rust/src/bin/servers.rs -->

<!-- include course/java/src/main/java/Servers.java -->

On the test server, the output is:

```
status: 200 application/json; charset=utf-8
EU I: ws://localhost:8022/ws1/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1
US I: ws://localhost:8022/ws2/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1
```

Run it again without `AL_BASE_URL`. Then it asks the real game, and the URLs start with
`wss://`. The list changes over time.

If it fails:

- A connection error on `localhost`: the test server does not run. Start it.
- A connection error on `adventure.land`: open `https://adventure.land/api/get_servers` in a
  browser to check your network.
- A status other than 200: a proxy or the web server in front of the game answered. Wait,
  then try again.
- A compiler error: compare your project file with step 4 of
  [Before you start](#learn-before-you-start).

## WebSockets in practice

A WebSocket library hides the protocol well, until something goes wrong. This chapter shows
what is on the wire, and what your library does by default that matters for Adventure Land.

### The upgrade request

A WebSocket starts as an HTTP request on a normal connection. The client asks the server to
"upgrade" the connection. This is a real exchange with the test server:

```
GET /ws1/?EIO=4&transport=websocket HTTP/1.1
Host: localhost:8022
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13

HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

- Status `101 Switching Protocols` means "yes". After the empty line, the bytes on the
  connection are WebSocket **frames**, not HTTP.
- `Sec-WebSocket-Accept` is a hash of the key. It proves that the server understood the
  request. Your library checks it.
- The **path** must be exact. The live servers listen at the `path` of the server list, for
  example `/ws1/`, with its final `/`. A wrong path gives a 404 or a 400, not a 101.
- The query `?EIO=4&transport=websocket` is for Socket.IO. [Socket.IO by hand](#learn-socket-io-by-hand)
  explains it.

### Frames: text, binary, close, ping

After the upgrade, each message travels in one or more frames. The first byte of a frame holds
a FIN bit ("the last frame of this message") and an **opcode**:

| Opcode | Frame | Use in Adventure Land |
|---|---|---|
| 1 | text | Each Socket.IO packet: UTF-8 JSON text. |
| 2 | binary | Not used on the JSON endpoint. |
| 0 | continuation | The next part of a long message. Your library joins the parts. |
| 8 | close | "I close the connection." It holds a close code. |
| 9, 10 | ping, pong | Protocol keep-alive. The game does not depend on them. |

> **Caution:** The WebSocket ping (opcode 9) and the Socket.IO ping (the text `2`) are
> different things. The game server sends the text `2` every 4 s. Your code must answer each
> one with the text `3`. Your library does not do it for you.

The client masks each frame that it sends: it XORs the data with 4 random bytes. Your library
does this. The close codes that you will see:

| Code | Name | When you see it |
|---|---|---|
| 1000 | normal closure | One side closed on purpose, for example your `close()`. |
| 1001 | going away | The server stops or restarts. |
| 1005 | no status | A close frame without a code. |
| 1006 | abnormal closure | The connection broke with no close frame: a network drop, a killed process, a ping timeout. No one sends 1006. Your library reports it. |
| 1009 | message too big | A message was larger than the limit of the receiver. |
| 1011 | internal error | The server had an error. |

### Your library in practice

Each language's WebSocket library has defaults that matter for Adventure Land. `AlSocket`
([AlSocket](#learn-alsocket)) sets the ones that need a change:

| Language | Library | Read and write | Text frames arrive as | Its own pings | Largest message | A broken connection |
|---|---|---|---|---|---|---|
| JavaScript, TypeScript | the global `WebSocket` of Node.js 22 | a `message` callback; `send(text)` returns at once | `string` (binary: `Blob`) | none; it answers the pings of the server | no limit to set | a `close` event with code 1006 |
| Python | `websockets` 13 (`websockets.asyncio.client`) | `await ws.recv()` or `async for`; `await ws.send(text)` | `str` (binary: `bytes`) | a ping every 20 s, and it closes if no pong comes in 20 s. `AlSocket` stops them (`ping_interval=None`): Socket.IO has its own. | **1 MiB** by default (`max_size`). `AlSocket` sets 16 MiB. | `ConnectionClosedError` with code 1006 |
| Go | `github.com/coder/websocket` | `conn.Read(ctx)` blocks; `conn.Write(ctx, ...)` | `[]byte` with `MessageText` | none. It answers pings **only while a `Read` call runs**, so keep one reader goroutine. | **32 KiB** by default. A larger `entities` frame closes the connection with 1009. `AlSocket` calls `SetReadLimit(16 << 20)`. | an error from `Read`; `websocket.CloseStatus(err)` is -1 when no close frame came |
| C# | `System.Net.WebSockets.ClientWebSocket` | `ReceiveAsync` into a buffer, part by part (`EndOfMessage`); one `SendAsync` at a time | bytes with `MessageType.Text`; decode UTF-8 | a keep-alive frame every 30 s (`KeepAliveInterval`) | no limit; you join the parts | a `WebSocketException`; `CloseStatus` is null |
| Rust | `tokio-tungstenite` 0.24 | `ws.next().await` on the stream; `ws.send(Message::Text(..)).await` | `Message::Text(String)` | none. It queues the pong for a server ping and sends it on the next read or write. | 64 MiB per message | an `Err`, or the stream ends with `None` |
| Java | `java.net.http.WebSocket` | a `Listener`: `onText(ws, data, last)` can give a message in parts; call `ws.request(1)` for the next one; `sendText(text, true)` | `CharSequence` parts | none; it answers the pings of the server | no limit; you join the parts | `onError` with an `IOException`; `onClose` comes only with a close frame |

Two rules come from this table:

- **One reader, always running.** Read in one loop or callback, and never block it. The Go
  library answers pings only inside `Read`. The Socket.IO ping has a 12 s deadline.
- **Handle text as UTF-8 strings.** Names of items and players can contain any character.

### Example: send and receive one message

This program opens a WebSocket to the echo endpoint of the test server, sends `hello`, prints
the reply and closes the connection. It uses only the WebSocket library. Start the test server
first. If your program runs in Docker, set `AL_ECHO_URL` to `ws://host.docker.internal:8022/echo`.

<!-- include course/js/echo.js -->

<!-- include course/ts/echo.ts -->

<!-- include course/python/echo.py -->

<!-- include course/go/cmd/echo/main.go -->

<!-- include course/csharp/Echo/Program.cs -->

<!-- include course/rust/src/bin/echo.rs -->

<!-- include course/java/src/main/java/Echo.java -->

The output is:

```
connected
received: hello
closed
```

## Socket.IO by hand

The game servers speak **Socket.IO v4**. This chapter shows the format on the wire. The next
chapter, [AlSocket](#learn-alsocket), turns it into a client of about 200 to 300 lines.

There are two routes:

- **Write the client yourself** (recommended). You understand each byte that your bot sends,
  and Go has no good Socket.IO v4 client library. The rest of the course uses `AlSocket`.
- **Use a library.** Read this chapter anyway, then go to
  [If you prefer a library](#learn-alsocket). The examples on the other pages use the
  `AlSocket` names, so you must translate them.

### Two layers: Engine.IO and Socket.IO

Socket.IO has two layers. **Engine.IO** is the lower layer: it opens the transport and checks
with pings that the connection is alive. **Socket.IO** is the upper layer: it adds
**namespaces** (channels on one connection) and **events** (a name and a payload).

Each WebSocket text frame holds one **packet**. A packet starts with one digit: the Engine.IO
packet type. If that digit is `4` (message), a second digit follows: the Socket.IO packet type.

| Engine.IO type | Name | Direction | Meaning |
|---|---|---|---|
| `0` | open | server to client | The first packet. It holds the session settings as JSON. |
| `1` | close | both | Close the session. |
| `2` | ping | server to client | "Are you there?" |
| `3` | pong | client to server | "Yes." Send it at once for each ping. |
| `4` | message | both | A Socket.IO packet follows. |

| Socket.IO type | Full packet | Meaning |
|---|---|---|
| `0` CONNECT | `40` | Client: "connect me to the namespace `/`". Server: `40{"sid":"..."}` means "connected". |
| `1` DISCONNECT | `41` | Leave the namespace. |
| `2` EVENT | `42["name",payload]` | An event. This is almost all the traffic. |
| `4` CONNECT_ERROR | `44{"message":"..."}` | The server refused the namespace connect. |

The other types do not occur on a WebSocket-only connection to Adventure Land. These are
Engine.IO `5` (upgrade) and `6` (noop), and Socket.IO `3` (ack), `5` and `6` (binary).

### Events

An event packet is `42` followed by a JSON array. The first item is the event name. The second
item is the payload:

```
42["move",{"x":0,"y":0,"going_x":100,"going_y":200,"m":0}]
42["game_error","Failed: no_character"]
42["send_updates"]
```

The payload can be an object, a string, a number or an array. It can also be absent, as in
the last line. Adventure Land uses at most one payload item. The live server does not use
acknowledgements ("acks"): its wrapper of each handler takes only the payload
(`node/server.js:4883-4885`). If a packet has digits between `42` and `[` (an ack id), skip
them.

### The URL

The URL of a game server has three parts:

- The **host** and the **path** come from the server list, for example `/ws1/`. This is not
  the Socket.IO default `/socket.io/`. Keep the final `/`.
- `?EIO=4&transport=websocket` asks for Engine.IO version 4 directly over a WebSocket. Without
  `transport=websocket`, the server expects HTTP long-polling first.
- `&map_protocol=1&no_graphics=1` are what the game's own client adds (`js/game.js:1525`).
  `map_protocol=1` says that your client understands generated maps. Without it, the server
  throws `client_update_required` when your character enters one
  (`node/logic/generated_maps.js:186`). `no_graphics=1` asks for a navigation grid instead of
  tiles (`node/logic/generated_maps.js:192-205`).

So the full URL for a live server is
`wss://<address><path>?EIO=4&transport=websocket&map_protocol=1&no_graphics=1`. The program
[`servers`](#learn-the-al-http-api) makes these URLs. The test server ignores the last two
values.

### A session, step by step

This is a complete session of the program `al-test` with the test server, which uses the ping
settings of the live servers. `<<` is a frame from the server, `>>` is a frame from the client,
and the number is the time in seconds. Long payloads are cut.

```
  0.00 << 0{"sid":"Yq1V3dPAkB7DGwsfAAAB","upgrades":[],"pingInterval":4000,"pingTimeout":12000,"maxPayload":1000000}
  0.00 >> 40
  0.00 << 40{"sid":"vjv7bCHrNbSoP2lOAAAC"}
  0.00 << 42["welcome",{"region":"EU","name":"I","pvp":false,"gameplay":"normal","info":{},"version":17478,"x":0,"y":70,"map":"main","in":"main","S":{...}}]
  0.01 >> 42["loaded",{"success":1,"width":1920,"height":1080,"scale":2}]
  0.01 << 42["entities",{"type":"all","in":"main","map":"main","players":[],"monsters":[{"id":"1","type":"goo",...},...]}]
  0.01 >> 42["auth",{"user":"US_tester","auth":"0123...","character":"CH_tester","no_html":"1","passphrase":""}]
  0.02 << 42["start",{"id":"Tester","name":"Tester","ctype":"warrior","level":1,"hp":...,"entities":{...}}]
  3.02 >> 42["ping_trig",{"id":"42"}]
  3.02 << 42["ping_ack",{"id":"42"}]
  4.00 << 2
  4.00 >> 3
  4.01 >> 41
  4.01 -- closed code=1000
```

Line by line:

1. `0{...}` is the Engine.IO open packet. `pingInterval` and `pingTimeout` are in
   milliseconds. `maxPayload` is the largest packet, in bytes, that the server accepts from
   you. You do not need either `sid`.
2. The client sends `40` to connect to the default namespace `/`. The server answers
   `40{"sid":...}`. The connection is ready.
3. The server sends [`welcome`](#recv-welcome) at once, without a request
   (`node/server.js:5019`). Your client must not lose it, even before your code asks for it.
4. The client sends [`loaded`](#send-loaded). The server makes an **observer** for the socket:
   a viewer with no character, which sees the map but cannot act
   ([Observing without a character](#guide-observing-without-a-character)). Then it sends one
   full [`entities`](#recv-entities) snapshot (`node/server.js:5028-5051`).
5. The client sends [`auth`](#send-auth) to log in a character. The server answers with
   [`start`](#recv-start). Part 2 explains the fields.
6. [`ping_trig`](#send-ping_trig) is an application-level ping. The server sends back the same
   payload as [`ping_ack`](#recv-ping_ack) (`node/server.js:5126-5128`).
7. After 4 s (`pingInterval`), the server sends the Engine.IO ping `2`. The client answers `3`
   at once.
8. The client sends `41` (leave the namespace) and closes the WebSocket with code 1000.

### The ping rule

> **Caution:** Answer each `2` with a `3` at once. If the server gets no pong within
> `pingTimeout` (12 s on the live servers) after a ping, it closes your connection.

The live game servers use `pingInterval: 4000` and `pingTimeout: 12000`
(`node/server.js:83-84`), not the defaults of the Socket.IO library (25,000 ms and 20,000 ms).
If your program stops for 12 s (a long calculation, a breakpoint, a full queue of messages),
the server drops it. Thus, the pong must come from the reader, not from your event handlers.

The live servers send standard JSON text frames. A special encoder makes some frames faster,
but the bytes are the same as from the normal encoder (`node/json_parser.js:1-12`). They do not
use per-message compression (`permessage-deflate`) (`node/server.js:56-59`).

### The MessagePack endpoint (optional)

Each live game server also has a second Socket.IO endpoint at `msgpack_path` in the server list,
for example `/ws1-msgpack/` (`node/server.js:88-98`). It carries the same events, encoded in
**MessagePack** (a binary format) in binary frames (`docs/articles/X.sub-msgpack.html`). Its
packets are smaller, and a packet from the client can be at most 64 KiB. This course uses the
JSON endpoint, because you can read its frames and compare them with the reference.

## AlSocket

`AlSocket` is the first module of `albot`: a Socket.IO v4 client, written by hand on top of the
WebSocket library of your language. All later chapters and all examples on the other pages use
it, with the same five operations in all seven languages.

### The design of AlSocket

| Operation | What it does |
|---|---|
| `connect(url)` | Opens the WebSocket to the full URL, reads the open packet, sends `40` and waits for `40`. |
| `emit(name, payload)` | Sends `42["name",payload]`. With no payload, it sends `42["name"]`. |
| `on(name, handler)` | Calls `handler(payload)` for each event with this name, from now on. |
| `waitFor(name, pred, timeout)` | Waits for the next event with this name for which `pred(payload)` is true. Fails after the timeout (10 s by default) or when the connection closes. |
| `close()` | Sends `41`, then closes the WebSocket with code 1000. If the server does not answer the close in 5 s, it ends the connection itself. |

The names follow each language: `wait_for` in Python and Rust, `WaitFor` in Go and
`WaitForAsync` in C#. In C#, each method that returns a task has `Async` at the end of its
name. For how these parts use the async model of your language, see
[Async in your language](#guide-the-async-model-of-your-language) in the API reference.
Inside, `AlSocket` has four parts:

1. **A reader.** One loop reads each frame. If the frame is `2`, the reader sends `3` at once.
   If the frame is an event, the reader decodes the JSON and gives the event to the
   dispatcher. Nothing else runs in the reader, so a slow handler cannot delay a pong.
2. **A dispatcher.** It calls your handlers and completes your waiters, in the order in which
   the events arrived. In Go, C#, Rust and Java, the dispatcher runs in its own thread or task.
   Thus, your handlers run one at a time, but on a thread that is not your main thread.
3. **The kept events.** The server sends `welcome` immediately after the handshake. That can
   occur before your code calls `waitFor("welcome")`. `AlSocket` keeps each event that arrives
   before your first `on` or `waitFor`. The first subscriber for an event name gets the kept
   events of that name. After the first subscription, `AlSocket` keeps nothing more. It
   discards an event that has no handler and no waiter, as all Socket.IO clients do.

   Make the wait for `welcome` your first subscription. In Go, C#, Rust and Java, the reader
   runs on its own thread. A `welcome` that arrives after another `on` does not reach you.
4. **A local `disconnect` event.** When the connection ends, `AlSocket` delivers an event with
   the name `disconnect` and a reason string. The server never sends this name. After
   `disconnect`, each waiter fails.

> **Caution:** Start a wait before you send the event that causes the reply. If you send first,
> a fast reply can arrive before your wait starts, and the wait then misses it.

In all languages except Go, `waitFor` registers the waiter when you call it, not when you
await it. Thus this order is correct: call `waitFor`, then `emit`, then await the result. In
Go, `WaitFor` blocks, so `alsocket` also has `Expect`. `Expect` registers the waiter and
returns a function that waits. Python's `wait_for` returns a coroutine that is already
registered.

The payload type is different in each language, because each language has a different
"any JSON value" type:

| Language | Payload type in handlers | No payload |
|---|---|---|
| JavaScript, TypeScript | the decoded value. In TS, give the type as a parameter: `waitFor<Welcome>("welcome")`. | `undefined` |
| Python | `dict`, `list`, `str`, `int`, `float`, `bool` | `None` |
| Go | `json.RawMessage` (decode it with `json.Unmarshal`) | `nil` |
| C# | `JsonElement` | `default` (`ValueKind` is `Undefined`) |
| Rust | `serde_json::Value` | `Value::Null` |
| Java | Jackson `JsonNode` | `NullNode` |

### AlSocket: the complete code

Each tab is one complete file. It uses only the WebSocket and JSON packages of step 3 of
[Before you start](#learn-before-you-start), and no other file of the library. Put it in the
library folder of your project (step 4):

| Language | File | Use it as |
|---|---|---|
| JavaScript, TypeScript | `albot/alsocket.js`, `albot/alsocket.ts` | `import { AlSocket } from "./albot/alsocket.js"` (`.ts`) |
| Python | `albot/alsocket.py` | `from albot.alsocket import AlSocket` |
| Go | `alsocket/alsocket.go` | `import "albot/alsocket"`; the type is `*alsocket.Socket` |
| C# | `Albot/AlSocket.cs` | `using Albot;` |
| Rust | `src/alsocket.rs`, with `pub mod alsocket;` in `src/lib.rs` | `use albot::alsocket::AlSocket;` |
| Java | `src/main/java/albot/AlSocket.java` | `import albot.AlSocket;` |

<!-- include course/js/albot/alsocket.js -->

<!-- include course/ts/albot/alsocket.ts -->

<!-- include course/python/albot/alsocket.py -->

<!-- include course/go/alsocket/alsocket.go -->

<!-- include course/csharp/Albot/AlSocket.cs -->

<!-- include course/rust/src/alsocket.rs -->

<!-- include course/java/src/main/java/albot/AlSocket.java -->

### When the connection breaks

`AlSocket` does not reconnect by itself. This is deliberate. A reconnect to Adventure Land is
not only a new socket. It is the complete handshake again: `welcome`, `loaded`, `auth`, and a
wait for `start`. Your bot must also build its view of the world again.

The whole course uses one reconnect rule. The `bot` module of Part 2 has it as
`reconnectDelayMs` (`reconnect_delay_ms` in Python and Rust):

1. Listen for `disconnect`. Its reason tells you what happened. If the server sent
   [`disconnect_reason`](#recv-disconnect_reason) first, read it too. For example, `"limitdc"`
   means that you sent too many events.
2. Close the old socket, if it is not closed.
3. Wait 30 s (`AL_RECONNECT_MS`) before the first try.
4. Make a new `AlSocket`, and do the complete handshake again. Do not use the old one.
5. If the try fails, double the wait, to a maximum of 300 s, and try again.
6. After a session that lasted 5 minutes or more, start again from 30 s.

The first wait is long for a reason. After a disconnect, the server keeps your character in its
list of disconnected players until it saves the character. Until then, a new `auth` gets
"Authorization in progress" instead of `start` (`node/server.js:11577-11582`, `:13055`,
`:16812`). [Connecting and the handshake](#learn-connecting-and-the-handshake) lists the
other login failures.

> **Caution:** Do not reconnect in a tight loop. If more than 5 sockets without a character
> come from your IP address, the server disconnects all the others (`node/server.js:4830-4852`).

### If you prefer a library

You can also use a Socket.IO library. The programs below use the library of each language for
the first steps of a session. They wait for `welcome`, send `loaded`, and print the size of the
`entities` snapshot. Each library takes the host and the path separately, so the programs split
`AL_WS_URL`.

```js
// lib.js: the first steps again, with the socket.io-client library.
//   npm i socket.io-client@4
import { io } from "socket.io-client";

// The library takes the host and the path separately: split the URL.
const url = new URL(process.env.AL_WS_URL ?? "ws://localhost:8022/ws1/?EIO=4&transport=websocket");
// transports: ["websocket"]: do not start with HTTP long-polling.
const sock = io(url.origin, { path: url.pathname, transports: ["websocket"], reconnection: false });

sock.on("welcome", (data) => {
  console.log(`welcome: ${data.region} ${data.name}`);
  sock.emit("loaded", { success: 1, width: 1920, height: 1080, scale: 2 });
});
sock.on("entities", (data) => {
  console.log(`entities: ${data.monsters.length} monster(s)`);
  sock.disconnect();
});
```

```ts
// lib.ts: the first steps again, with the socket.io-client library.
//   npm i socket.io-client@4
import { io, Socket } from "socket.io-client";

interface Welcome { region: string; name: string }
interface Entities { type: string; monsters: { id: string }[] }

// The library takes the host and the path separately: split the URL.
const url = new URL(process.env.AL_WS_URL ?? "ws://localhost:8022/ws1/?EIO=4&transport=websocket");
// transports: ["websocket"]: do not start with HTTP long-polling.
const sock: Socket = io(url.origin, { path: url.pathname, transports: ["websocket"], reconnection: false });

sock.on("welcome", (data: Welcome) => {
  console.log(`welcome: ${data.region} ${data.name}`);
  sock.emit("loaded", { success: 1, width: 1920, height: 1080, scale: 2 });
});
sock.on("entities", (data: Entities) => {
  console.log(`entities: ${data.monsters.length} monster(s)`);
  sock.disconnect();
});
```

```python
# lib.py: the first steps again, with the python-socketio library.
# pip install "python-socketio[asyncio_client]"
import asyncio
import os
from urllib.parse import urlsplit

import socketio


async def main() -> None:
    # The library takes the host and the path separately: split the URL.
    url = urlsplit(os.environ.get("AL_WS_URL", "ws://localhost:8022/ws1/?EIO=4&transport=websocket"))
    origin, path = f"{url.scheme}://{url.netloc}", url.path
    sio = socketio.AsyncClient(reconnection=False)

    @sio.on("welcome")
    async def on_welcome(data):
        print(f"welcome: {data['region']} {data['name']}")
        await sio.emit("loaded", {"success": 1, "width": 1920, "height": 1080, "scale": 2})

    @sio.on("entities")
    async def on_entities(data):
        print(f"entities: {len(data['monsters'])} monster(s)")
        await sio.disconnect()

    # transports=["websocket"]: do not start with HTTP long-polling.
    await sio.connect(origin, socketio_path=path, transports=["websocket"])
    await sio.wait()  # returns after the disconnect


asyncio.run(main())
```

```go
// Go: this course shows no Socket.IO library for Go.
// Some Go Socket.IO libraries support only old protocol versions, or only
// the server side. If you try one, make sure that it is a client for
// Socket.IO v4 (Engine.IO v4).
// The alsocket package of this chapter is about 300 lines, and you know
// what each line does.
```

```csharp
// Program.cs: the first steps again, with the SocketIOClient library (4.x).
//   dotnet add package SocketIOClient
using System.Text.Json;
using SocketIOClient;
using SocketIOClient.Common;

// The library takes the host and the path separately: split the URL.
var url = new Uri(Environment.GetEnvironmentVariable("AL_WS_URL") ?? "ws://localhost:8022/ws1/?EIO=4&transport=websocket");
var done = new TaskCompletionSource();

using var client = new SocketIO(new Uri(url.GetLeftPart(UriPartial.Authority)), new SocketIOOptions
{
    Path = url.AbsolutePath,
    Transport = TransportProtocol.WebSocket, // do not start with HTTP long-polling
    Reconnection = false,
});
client.On("welcome", async ctx =>
{
    var data = ctx.GetValue<JsonElement>(0); // the first payload
    Console.WriteLine($"welcome: {data.GetProperty("region")} {data.GetProperty("name")}");
    // 4.x takes the payloads as a list.
    await client.EmitAsync("loaded", [new { success = 1, width = 1920, height = 1080, scale = 2 }]);
});
client.On("entities", ctx =>
{
    var data = ctx.GetValue<JsonElement>(0);
    Console.WriteLine($"entities: {data.GetProperty("monsters").GetArrayLength()} monster(s)");
    done.TrySetResult();
    return Task.CompletedTask;
});
await client.ConnectAsync();
await done.Task;
await client.DisconnectAsync();
```

```rust
// main.rs: the first steps again, with the rust_socketio library (async).
//   cargo add rust_socketio --features async
//   cargo add tokio --features full
//   cargo add futures-util serde_json
use futures_util::FutureExt;
use rust_socketio::asynchronous::{Client, ClientBuilder};
use rust_socketio::{Payload, TransportType};
use serde_json::json;
use std::time::Duration;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // This library takes the URL with the path but without the query.
    // (With no path, the library uses "/socket.io/".)
    let url = std::env::var("AL_WS_URL")
        .unwrap_or_else(|_| "ws://localhost:8022/ws1/?EIO=4&transport=websocket".to_string());
    let url = url.split('?').next().unwrap_or_default().to_string();

    let client = ClientBuilder::new(url)
        .transport_type(TransportType::Websocket) // do not start with HTTP long-polling
        .on("welcome", |payload: Payload, client: Client| {
            async move {
                // Payload::Text holds the event's arguments as JSON values.
                if let Payload::Text(args) = payload {
                    println!("welcome: {} {}", args[0]["region"], args[0]["name"]);
                }
                let loaded = json!({"success": 1, "width": 1920, "height": 1080, "scale": 2});
                client.emit("loaded", loaded).await.expect("emit failed");
            }
            .boxed()
        })
        .on("entities", |payload: Payload, _client: Client| {
            async move {
                if let Payload::Text(args) = payload {
                    let count = args[0]["monsters"].as_array().map_or(0, |m| m.len());
                    println!("entities: {count} monster(s)");
                }
            }
            .boxed()
        })
        .connect()
        .await?;

    // The handlers run in the background. Wait 2 s for them, then disconnect.
    tokio::time::sleep(Duration::from_secs(2)).await;
    client.disconnect().await?;
    Ok(())
}
```

```java
// Lib.java: the first steps again, with the socket.io-client library.
// Maven: io.socket:socket.io-client:2.1.1
import io.socket.client.IO;
import io.socket.client.Socket;
import java.net.URI;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import org.json.JSONObject;

public class Lib {
    public static void main(String[] args) throws Exception {
        // The library takes the host and the path separately, and it wants
        // http(s):// in place of ws(s)://.
        URI url = URI.create(System.getenv().getOrDefault("AL_WS_URL", "ws://localhost:8022/ws1/?EIO=4&transport=websocket"));
        String origin = (url.getScheme().equals("wss") ? "https://" : "http://") + url.getAuthority();
        var done = new CountDownLatch(1);

        IO.Options options = IO.Options.builder()
                .setPath(url.getPath())
                .setTransports(new String[] {"websocket"}) // do not start with HTTP long-polling
                .setReconnection(false)
                .build();
        Socket socket = IO.socket(origin, options);

        // Payloads arrive as org.json objects, not as Jackson nodes.
        socket.on("welcome", a -> {
            JSONObject data = (JSONObject) a[0];
            System.out.println("welcome: " + data.optString("region") + " " + data.optString("name"));
            socket.emit("loaded", new JSONObject(Map.of("success", 1, "width", 1920, "height", 1080, "scale", 2)));
        });
        socket.on("entities", a -> {
            JSONObject data = (JSONObject) a[0];
            System.out.println("entities: " + data.optJSONArray("monsters").length() + " monster(s)");
            done.countDown();
        });
        socket.connect();
        done.await();
        socket.disconnect();
        System.exit(0); // the OkHttp threads of the library keep the JVM alive for a minute
    }
}
```

A library does more than `AlSocket`: it can reconnect, buffer events while it reconnects, and
use HTTP long-polling. But it hides the wire format, and its automatic reconnect does not do
the Adventure Land handshake again. If you use one, turn its reconnect off and use the
reconnect rule above.

## A local game server

The test server of step 6 of [Before you start](#learn-before-you-start) is one fake Adventure
Land for the whole course. It is a real Socket.IO v4 server, and it copies the payloads of the
live game for each thing that the course uses. It is not the game: its world is small, and its
rules are simpler. Each of its handlers names the line of the live code that it copies.

| Part | What the test server does |
|---|---|
| HTTP | `signup_or_login`, `servers_and_characters`, `get_servers`, `create_character`, `/hub` and `/data.js` (a smaller copy of the real G). |
| Echo | A plain WebSocket echo at `/echo`, for [WebSockets in practice](#learn-websockets-in-practice). |
| Game servers | `EU I` at the path `/ws1/` and `US I` at `/ws2/`, each with its own world. The live ping settings. |
| The handshake | `welcome`, `loaded`, `auth` (with the live failures), `start`. |
| The world | `player` and `entities` updates, monsters from `G.maps.main` that move and fight back, walls from `G.geometry`. |
| Actions | `move`, `attack`, potions and `use`, chests, death and `respawn`, NPC `buy` and `sell`, `equip`, doors and `transport`, `jail` and `leave`, parties, `send`, `upgrade` and `compound`, and the call-cost limit. |

It has one test account and four characters. Your programs use these values when they run on
it:

| Item | Value |
|---|---|
| Email and password | `tester@example.com`, `test-password` |
| `AL_AUTH` | `US_tester-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef` |
| Characters | `Tester` (warrior), `Healer` (priest), `Archer` (ranger), `Merchy` (merchant), all at level 1 on `main` |
| Start | Spawn 5 of `main`, at -87,673, near the goos, with 10 `hpot0`, 10 `mpot0` and 10,000 gold. `Tester` starts with 40% of its HP, so that your first bot must heal. |

These settings change its behavior. Set them in the terminal of the server, before you start
it (with Docker: `-e NAME=value` before the image name):

| Variable | Default | What it does |
|---|---|---|
| `TEST_PORT` | `8022` | The port for HTTP, the game servers and the echo endpoint. |
| `TEST_PING_INTERVAL`, `TEST_PING_TIMEOUT` | `4000`, `12000` | The Engine.IO ping settings. Set both to `1000` to see a missing pong fast. |
| `TEST_DROP_AFTER_MS` | off | Close each character's socket one time, this long after `start`. It tests your reconnect. |
| `TEST_SAVE_MS` | `0` | After a disconnect, `auth` for that character gets "Authorization in progress" for this long, as on the live server. |
| `TEST_RIP_MS` | `12000` | The wait before a dead character can respawn. |
| `TEST_DAMAGE` | `1` | Multiplies the damage of the monsters. A high value tests potions and death. |
| `TEST_QUIET` | off | Do not print each event. |
| `TEST_G_FILE` | `G.json` | The file with the game data. Without it, the server downloads G from the real game one time. |

It also has three URLs that control a test:

- `POST /test/reset` puts all worlds and characters back to the start.
- `POST /test/drop?character=Tester` closes the socket of that character now.
- `GET /test/stats` shows counters, for example the number of line violations.

### The test program

The program `al-test` sends `AlSocket` through all the steps of the session in
[Socket.IO by hand](#learn-socket-io-by-hand). It connects, waits for `welcome`, and sends
`loaded` and `auth`. Then it does nothing for 3 s, and it ends with a `ping_trig` round trip. It uses only `AlSocket`. It sends the fixed
values of the test account, because Part 1 has no login code yet.

1. Stop the test server with Ctrl-C.
2. Start it again with short ping times, so that a client with no pong fails during the 3 s
   with no activity. With Docker, add `-e TEST_PING_INTERVAL=1000 -e TEST_PING_TIMEOUT=1000`
   before the image name. Without Docker, set the two variables, then run `node server.js`.
3. Put the program of your language in your project folder.
4. In a second terminal, run it with the command in its first comment.
5. Compare the output with the next section.

<!-- include course/js/al-test.js -->

<!-- include course/ts/al-test.ts -->

<!-- include course/python/al_test.py -->

<!-- include course/go/cmd/al-test/main.go -->

<!-- include course/csharp/AlTest/Program.cs -->

<!-- include course/rust/src/bin/al-test.rs -->

<!-- include course/java/src/main/java/AlTest.java -->

### What you see

The program prints this. The text of the `disconnect` reason is different in each language.
The snapshot has 0 monsters. The observer looks at the point of `welcome` (0, 70). The goos
are more than 500 px away from it.

```
connected to ws://localhost:8022/ws1/?EIO=4&transport=websocket
welcome: EU I, version 17478
entities: 0 monster(s)
start: Tester on main at -87,673
ping_ack after 3 s idle: 42
OK
disconnect: transport closed (code 1000)
```

The test server prints each event that it received. The note is correct: `al-test` uses the
short URL of Part 1, and the live server needs `map_protocol=1` only for generated maps.

```
[T_LGTtmVZJw0UvQuAAAA] note: the URL has no map_protocol=1
[T_LGTtmVZJw0UvQuAAAA] <- loaded {"success":1,"width":1920,"height":1080,"scale":2}
[T_LGTtmVZJw0UvQuAAAA] <- auth {"user":"US_tester","auth":"0123...","character":"CH_tester","no_html":"1","passphrase":""}
[T_LGTtmVZJw0UvQuAAAA] Tester entered EU I on main at -87,673
[T_LGTtmVZJw0UvQuAAAA] <- ping_trig {"id":"42"}
[T_LGTtmVZJw0UvQuAAAA] Tester disconnected: client namespace disconnect
```

If the server prints `disconnected: ping timeout`, your client did not answer a ping in time.

### Exercises

1. Remove the line that sends `3` in your `AlSocket`. Run the test again with the short ping
   times. The server prints `ping timeout`, and the client fails at the `ping_trig` step.
2. Stop the test server while the client waits during the 3 s. Read the reason in the
   `disconnect` event. Compare it with the close codes in
   [WebSockets in practice](#learn-websockets-in-practice).
3. Add a `move` step: send [`move`](#send-move) with your position, `going_x`, `going_y` and
   the `m` of `start`. Read the `move` line that the test server prints. Then send an `m` that
   is wrong, and see that the server ignores the move.

You now have a working Socket.IO client and a safe place to test it. Part 2 connects it to the
real game: [Logging in and choosing a server](#learn-logging-in-and-choosing-a-server).
