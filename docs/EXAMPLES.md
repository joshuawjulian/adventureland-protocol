# Code examples: the shared contract

Every code example on the site follows this file, so that seven languages and several writers
produce one consistent course. Read it before writing any example.

## The seven languages

Each example is a **group of consecutive fenced code blocks**, one per language, in this order,
with exactly these fence tags (the page turns a run of them into tabs and shows the reader's
chosen language; the choice is remembered):

| Tab | Fence tag | Runtime | HTTP | WebSocket | JSON | Socket.IO library (for comparison only) |
|---|---|---|---|---|---|---|
| JavaScript | `js` | Node.js 22+ (ES modules) | global `fetch` | global `WebSocket` (built in since Node 22) | `JSON` | `socket.io-client` 4.x |
| TypeScript | `ts` | Node.js 22+ or Bun | global `fetch` | global `WebSocket` | `JSON` + interfaces | `socket.io-client` 4.x |
| Python | `python` | Python 3.11+, `asyncio` | `httpx` (async) | `websockets` 13+ | `json` | `python-socketio[asyncio_client]` 5.x |
| Go | `go` | Go 1.22+ | `net/http` | `github.com/coder/websocket` | `encoding/json` | none worth using (do it by hand) |
| C# | `csharp` | .NET 8, top-level statements | `HttpClient` | `System.Net.WebSockets.ClientWebSocket` | `System.Text.Json` | `SocketIOClient` (NuGet) |
| Rust | `rust` | Rust 2021, `tokio` | `reqwest` (json feature) | `tokio-tungstenite` (rustls) | `serde_json` | `rust_socketio` (async) |
| Java | `java` | Java 21 | `java.net.http.HttpClient` | `java.net.http.WebSocket` | Jackson (`ObjectMapper`) | `io.socket:socket.io-client` 2.x |

Rules:

- **All seven, every time**, in that order. If something truly can't be shown in a language,
  still include the block with a comment saying why.
- **TypeScript is not JavaScript with `: any`.** Give real interfaces for payloads
  (`interface AttackPayload { id: string }`) so the TS tab doubles as type documentation.
- **Snippets compile in context.** A snippet may assume the tutorial's `AlSocket` (below) and a
  connected `sock` variable already exist; say so in a comment the first time on a page. Full
  programs (tutorial "complete program" blocks) must compile/run on their own, with the
  dependency line (`npm i ...`, `pip install ...`, `go get ...`, `dotnet add package ...`,
  `cargo add ...`, Maven coordinates) in a comment at the top.
- **Idiomatic per language**: camelCase in JS/TS/Java, snake_case in Python/Rust, PascalCase
  exported names in Go and C#. Use each language's normal async model: async/await (JS, TS,
  Python, C#, Rust/tokio), goroutines + channels (Go), and `CompletableFuture` or virtual
  threads (Java).
- **Heavy, useful comments.** The reader is an undergrad CS student. Comment *why*, and call out
  anything hard-coded with the reason (e.g. `// 1 s: the server's attack cooldown is in ms`).
- **No secrets in examples.** Read email/password/auth from environment variables
  `AL_EMAIL`, `AL_PASSWORD` (or `AL_AUTH` = `<userID>-<authToken>`).
- Keep per-event snippets short (5–25 lines per language). Tutorial programs can be longer.
- **Course code lives in `course/`, not in the Markdown.** The Learn chapters show the library
  and the programs of `course/<lang>` with includes (below). The contract for its modules,
  names, programs and environment variables is docs/COURSE.md.
- Prose stays **language-agnostic**: explain the idea in words first, then the tab group.

## The `AlSocket` mini client (built in the tutorial, used everywhere after)

Its code is `course/<lang>`'s `alsocket` file (docs/COURSE.md); Learn shows it in the chapter
"AlSocket" (`#learn-alsocket`), after the wire format in "Socket.IO by hand".

**Sources.** Everything is written from the live game's open-source code,
`kaansoral/adventureland_mongodb` (pinned in `versions.json`; `vendor/adventureland_mongodb`).
Read the code; don't infer behavior from other clients. Cite it as `node/server.js:123`,
`api.js:88`, `js/old_common_functions.js:826` (the page links these to the pinned commit).

The tutorial builds a minimal Socket.IO v4 client **by hand on top of a plain WebSocket**, in
every language, because the owner wants to understand everything and because several languages
lack a good Socket.IO v4 library. Every later example uses this same surface:

| Operation | JS / TS | Python | Go | C# | Rust | Java |
|---|---|---|---|---|---|---|
| connect | `await AlSocket.connect(url)` | `await AlSocket.connect(url)` | `alsocket.Connect(ctx, url)` | `await AlSocket.ConnectAsync(url)` | `AlSocket::connect(url).await?` | `AlSocket.connect(url)` |
| send an event | `sock.emit("move", {x, y})` | `await sock.emit("move", {...})` | `sock.Emit("move", map[string]any{...})` | `await sock.EmitAsync("move", new {...})` | `sock.emit("move", json!({...})).await?` | `sock.emit("move", Map.of(...))` |
| listen | `sock.on("player", (data) => ...)` | `sock.on("player", handler)` | `sock.On("player", func(data json.RawMessage){...})` | `sock.On("player", data => ...)` (data is `JsonElement`) | `sock.on("player", \|data\| ...)` (data is `serde_json::Value`) | `sock.on("player", data -> ...)` (data is `JsonNode`) |
| wait for one | `await sock.waitFor("start", pred?, ms?)` | `await sock.wait_for("start", pred=None, timeout=10)` | `sock.WaitFor(ctx, "start", pred)` | `await sock.WaitForAsync("start", pred?, timeout?)` | `sock.wait_for("start", pred).await?` | `sock.waitFor("start", pred, Duration)` returns `CompletableFuture<JsonNode>` |
| close | `sock.close()` | `await sock.close()` | `sock.Close()` | `await sock.CloseAsync()` | `sock.close().await?` | `sock.close()` |

What it does on the wire (Engine.IO v4 + Socket.IO v4, text frames only):

1. `connect(url)` takes the **full** URL: `wss://<address><path>/?EIO=4&transport=websocket`,
   where `address` and `path` come from the live server list (`adventure_functions.js:751-766`
   in the live repo; fields `name, region, players, key, address, path, msgpack_path`; there is
   no `secure` field). The default Socket.IO path `/socket.io/` is **not** what the live servers
   use. The live server pings every 4,000 ms and drops a client after 12,000 ms without a pong
   (`node/server.js:81-82`).
2. Receive `0{"sid":...,"pingInterval":...,"pingTimeout":...}` (Engine.IO open).
3. Send `40` (Socket.IO connect to the default namespace); receive `40{"sid":...}`.
4. Server sends `2` (ping) every `pingInterval` ms; reply `3` (pong) or you get dropped.
5. Events are `42["name",payload]` both ways. Payload may be an object, a string, a number, or
   absent.
6. `41` = namespace disconnect; `1` = Engine.IO close.

## Reference examples (the `**Example:**` section of reference entries)

Short and neutral: show how to send the event and how to read the result, nothing else.

- Assume a connected `sock` (the `AlSocket` from Learn, "AlSocket"). Don't repeat setup;
  one comment line at the top of the JS tab may say `// sock: a connected AlSocket`.
- **Send entries:** register the wait for the result first, then emit, then read the result.
  Failures arrive as `game_response` with `place` = the event name (check the entry's Fails
  table); success arrives as the event(s) in its Success section. Use real field values.
- **Register before you send.** JS/TS/C#/Java/Rust `waitFor` and Python `wait_for` register at
  the call, so call them before `emit`, then await. In Go, use `wait := sock.Expect(name, pred)`
  before `sock.Emit(...)`, then `wait(ctx)`; never start `WaitFor` in a goroutine and then emit
  (a fast reply can arrive before the waiter exists).
- **Receive entries:** a handler `sock.on("name", ...)` that reads the payload's main fields.
- 3–15 lines per language (Go up to about 30: `gofmt` and `if err` blocks add lines). No prose inside code beyond short comments. Types in the TS tab.
- Every example must pass `python3 scripts/check-examples.py` (see "Checking examples"). It
  compiles each snippet against the real `AlSocket` of `course/<lang>`, so a snippet must follow
  these rules:
  - It is the body of a function that gets `sock`: JS/TS `async function (sock)`; Python
    `async def (sock: AlSocket) -> None`; Go `func(ctx context.Context, sock *alsocket.Socket)
    (err error)` (so `ctx` exists, and `return` and `return err` both work); C#
    `static async Task (AlSocket sock)`; Rust `async fn (sock: &AlSocket) -> Result<()>`
    (AlSocket's `Result`, so `?` works); Java `static void (AlSocket sock) throws Exception`.
  - Imports are given: Python `asyncio json os time` and `typing`'s `Any Literal NotRequired
    TypedDict`; Go `context encoding/json errors fmt log os strings time strconv sync math sort
    slices`; C# the implicit usings plus `System.Text.Json(.Nodes, .Serialization)` and
    `System.Net.WebSockets`; Rust `json! Value Deserialize Serialize Duration Arc Mutex`;
    Java `java.util.*`, `java.util.concurrent.*`, `java.util.function.*`, `Duration`,
    Jackson's `databind.*` and `databind.node.*`.
  - Declarations: TS interfaces, Python classes, Rust structs and fns and Java records can sit
    anywhere. Go `type`/`func`, C# `record`/`class`/`struct`/`enum` and Java methods
    (`static ...`) must start at column 0; the checker moves them out of the function.
  - Every name is defined in the snippet. Inputs get example values
    (`const x = 0, y = 0; // your position now`); secrets come from `AL_AUTH`.
  - It also fails on known misuses that compile: Python `create_task(sock.wait_for(...))`
    plus `sleep(0)` (unless racing tasks with `asyncio.wait`), Rust `join!`/`yield_now`/
    `timeout(...)` around `wait_for` (use `wait_for_timeout`), Go `WaitFor` with `Emit`
    (use `Expect`), and an emit before the first wait.

## Naming used across the course

- The connected socket is `sock`. The character's latest full state is `me`. Game data is `G`.
- Environment: one table for the whole course, in docs/COURSE.md ("Environment variables"):
  `AL_BASE_URL`, `AL_EMAIL`, `AL_PASSWORD`, `AL_AUTH`, `AL_SERVER` (e.g. `EUI`; empty = the
  first server), `AL_CHARACTER` (character name), `AL_WS_URL`, `AL_ECHO_URL`,
  `AL_RECONNECT_MS`. Don't invent others.

## Where examples live

The site is **three separate pages**, so the API reference stays a reference and the teaching
material doesn't clutter it:

| Page | File | Content |
|---|---|---|
| Learn | `site/learn.html` | the tutorial, `content/learn-*.md` (kind `learn`, one entry per `##` chapter, id `learn-<slug>`) |
| Game guide | `site/game.html` | how the MMO works, `content/game-*.md` (kind `game`, one entry per `##`, id `game-<slug>`) |
| API reference | `site/index.html` | everything that was already there: connect, send, receive, codes, G, S |

- Link to any entry with `[text](#id)`, e.g. `[move](#send-move)` or `[AlSocket](#learn-alsocket)`;
  the build rewrites the link to the right page. Ids are slugs: `o:home` is `#send-o-home`.
- Per-event examples go in `content/send-*.md` / `receive.md`, in each entry's `**Example:**`
  section, just before `**Source:**` (layout in docs/WRITING.md). HTTP examples per endpoint go
  in `content/connect.md`.

## Checking examples

**Reference examples:** `python3 scripts/check-examples.py` (options `--lang go`,
`--entry send-buy`, `--file content/send-2.md`, `-v` for raw compiler output). It takes the
`AlSocket` file of each `course/<lang>` and every `**Example:**` (or `#### Example`) group out of
send-*.md and receive.md, writes one project per language under `.examples/` (git-ignored),
compiles them in the images below (caches in `alapi-examples-*` Docker volumes; well under a
minute after the first run), and prints each error as `content/<file>:<line> <entry> [<lang>]`. Exit
status 1 on any error. Fix the Markdown, never the generated files.

**Tutorial programs (the course library):** `python3 scripts/check-course.py` (options
`--lang go`, `--program first-kill`, `--build-only`, `-v`). It copies each `course/<lang>` to
`.course-build/` (git-ignored), starts `course/test-server` in Docker with the pinned G, builds
all seven projects in the images above (caches in `alapi-course-*` volumes), runs each program
against the test server and matches its output with the lines in docs/COURSE.md ("The
programs"). Exit status 1 on any failure. The real game servers need an account and are not
for testing.

## Including code from course/

A chapter never pastes course code. It includes it, so the page and the compiled code are the
same text. The include is an HTML comment alone on its line (`includes.py`, used by build.py):

```markdown
<!-- include course/python/albot/alsocket.py -->
<!-- include course/go/world/world.go region=apply-entities -->
<!-- include course/test-server/server.js region=auth lang=js -->
<!-- include course/rust/Cargo.toml lang=rust -->
```

- The path is relative to the repository root. The build replaces the line with one fenced
  block. The fence tag is `lang=`, else the language of `course/<lang>/`, else the file
  extension.
- `region=NAME` takes only the lines between `// region NAME` and `// endregion NAME`
  (`# region` in Python and shell; `<!-- region -->` in XML). The common indent is removed.
  Region marker lines never show on the page, also in a whole-file include.
- Seven includes in a row, one per language in the order of the table above, separated by
  blank lines, become one tab group, the same as seven hand-written blocks.
- The build fails on a missing file, a missing or empty region, or an unknown option, with the
  line of the include. Rename a region only together with the chapters that use it
  (docs/COURSE.md lists the regions chapters rely on).
