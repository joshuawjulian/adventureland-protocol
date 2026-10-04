# Adventure Land API: project context

An interactive, searchable reference for the [Adventure Land](https://adventure.land) MMO
protocol, meant to be published on GitHub for anyone writing their own client or bot. It
documents every socket event both ways, every `game_response` code, the game data (G) and the
server's event state (S). The owner (Julian) intends to someday write his own AL client from
scratch, by hand, for the fun of it; this reference is the groundwork for that, and for others
doing the same. When they start that client, act as a guide and reviewer, not the builder,
unless asked.

## Where this came from

It was split out of the owner's bot project, `/home/julian/dev/al/claude-bot-old` (a Bun +
TypeScript party bot built on ALClient, with a Svelte dashboard; see that repo's
`docs/guide.qmd`). That project also has `docs/api.qmd`, an earlier single-file Quarto version
of this same content; **this repo is now the source of truth** for the reference.

The first draft was produced on 2026-10-04 by reading the game's old open-source server, slice
by slice (one pass per area, see `docs/WRITING.md`), then assembled and spot-checked:

- `attack` and `buy` entries were checked line by line against the source: exact.
- Every response code string in `node/server.js` + `node/server_functions.js` (165 distinct
  `fail_response("x")` / `response: "x"` literals) appears in the content.
- Not every cited line number was re-checked; a few were found off by a handful of lines and
  fixed. Treat citations as "within a few lines".

## Source of truth: the live game's open-source code

The owner's rule (2026-10-04): **everything is driven from the open-source code; no reverse
engineering.** Read the code; don't infer behavior from ALClient, captured traffic or guesses.

| Repo | Role | Local copy | Cited as |
|---|---|---|---|
| [kaansoral/adventureland_mongodb](https://github.com/kaansoral/adventureland_mongodb) | **The live game** (Express API + Node game server + client), deploys every few days | `vendor/adventureland_mongodb` | `node/server.js:123`, `api.js:88`, `js/old_common_functions.js:826` |
| [kaansoral/common_engine](https://github.com/kaansoral/common_engine) | Its shared engine (request handling, Mongo helpers) | `vendor/common_engine` | `common:js/file.js:12` |
| [kaansoral/adventureland](https://github.com/kaansoral/adventureland) | The old App Engine version, frozen 2026-03-02 | `vendor/adventureland` | `legacy:node/server.js:123` (historical notes only) |

`bash scripts/fetch-source.sh` fetches all three at the commits pinned in `versions.json`.

Useful in the live repo: `docs/articles/*.html` (official guides; text is phrase keys resolved
from `languages/en/*.js`), `docs/articles/adventure-api.html` (the official token JSON API at
`/mcp_api/<method>`), `docs/articles/X.sub-msgpack.html` (the optional MessagePack socket),
`update_notes.js` (the release list), `node/test/` (101 tests that show intended behavior).
Socket facts: the default endpoint at the server list's `path` speaks standard JSON Socket.IO v4
frames (`node/json_parser.js` only speeds up encoding); pingInterval 4000, pingTimeout 12000;
an optional MessagePack endpoint at `msgpack_path`.

**Status of the content (2026-10-04):** the API reference (`connect.md`, `send-*.md`,
`receive.md`, `game-data.md`, `server-events.md`) was first written from the legacy repo and is
being re-verified against the live code. Until that pass lands, its bare citations still point
at legacy line numbers.

## Layout

| Path | What |
|---|---|
| `content/*.md` | All content, in Markdown. Edit these. |
| `course/` | The course library **albot** and its programs, one project per language (`course/js` ... `course/java`), plus `course/test-server` (one fake Adventure Land for all programs). Contract: `docs/COURSE.md`. |
| `docs/COURSE.md` | **The contract for course code**: modules, public names per language, programs and their output, the environment variables, the test server. |
| `includes.py` | The `<!-- include path region=name -->` mechanism build.py uses for Learn chapters. |
| `docs/EXAMPLES.md` | **The contract for code examples**: seven languages, fence tags, libraries, the `AlSocket` mini client every example uses, how to compile-check in docker. |
| `template.html` | The page: CSS, layout, search, rendering. `__DATA__` is replaced by the build. |
| `build.py` | Python 3, no deps. Splits `content/` into entries, embeds them, writes the three `site/*.html` pages. |
| `site/*.html` | The built pages: `learn.html` (course), `game.html` (game guide), `index.html` (API reference). Complete HTML documents; GitHub Pages serves this folder. |
| `vendor/adventureland/` | The game's source at the pinned commit (git-ignored; `bash scripts/fetch-source.sh` recreates it). |
| `docs/WRITING.md` | The entry formats and the prompts used to write each content file. |
| `docs/STYLE.md` | Simplified Technical English (ASD-STE100) rules for all prose. |
| `docs/UPDATING.md` | The update pass after a game update. |
| `versions.json`, `data/g-fingerprint.json` | The pins (G version, live and common repo commits, legacy commit) and a per-key hash of the pinned G. |
| `scripts/check-updates.py` | Compares the pins with the live game; lists entries to re-check; `--fix-lines`, `--pin`. |

**Three pages, kept separate on purpose** (the owner wants the reference apart from the teaching
material): Learn = `learn-1..3.md`, a course from zero (HTTP, WebSockets, Socket.IO by hand,
login, handshake, world state, acting, bot architecture, a complete bot); Game guide =
`game-1..2.md` (what the MMO is, classes, combat, progression, items, upgrading, economy, events
and seasons); API reference = everything else. Every code example comes in seven languages (JS,
TS, Python, Go, C#, Rust, Java) as tabs; the reader's pick is remembered (`alapi.lang`).

Reference content files: `connect.md` (login, HTTP, handshake, observers, rate limits, conventions),
`send-1..4.md` (client→server events in server-code order), `send-observer.md` (`o:home`,
`o:command`), `receive.md` (server→client events grouped by `##` section, including the
225-row `game_response` code table), `game-data.md` (G), `server-events.md` (S).

## Building

```sh
python3 build.py                      # writes site/learn.html, game.html, index.html
python3 build.py --fragment OUT.html  # also writes the reference page without the <html>/<head> shell
python3 scripts/check-examples.py     # compile every reference example against course/<lang>'s AlSocket
python3 scripts/check-course.py       # build course/<lang> x7, run its programs against course/test-server
python3 scripts/gen-types.py --lang ts    # typed definitions from schema/ (ts python go csharp rust java)
python3 scripts/check-types.py        # strict schema check + compile the types in all seven languages
python3 scripts/gen-asyncapi.py       # the socket API as an AsyncAPI 3.0 document: site/asyncapi.json (-o PATH)
python3 scripts/check-asyncapi.py     # validate it with @asyncapi/parser + ajv in Docker (FILE.json, -v)
python3 scripts/confirm-report.py     # how many payload shapes are confirmed (code / live), and which are not
ALAPI_STRICT_CONFIRM=1 python3 build.py   # fails on a shape without `confirm`, or a live mismatch
```

**Confirmation** (docs/WRITING.md, "Confirmation"): every documented payload (a "shape", with a
stable id from `apischema.shape_id`) carries a hand-written `confirm` with the exact live-code
lines (`code`), or `live_needed` when only a capture can settle it. `schema/live.json` is
generated by `scripts/check-captures.py` (never edit it); the build merges it by shape id, and
each shape on the page shows a one-line status. `ALAPI_STRICT_CONFIRM=1` is separate from
`ALAPI_STRICT_TYPES` while the keys are being filled in (a missing `confirm` is only a warning
under `ALAPI_STRICT_TYPES`); fold it in once every shape has one. The models are `buy`, `attack`,
`upgrade`, `player` and `game_response`.

`scripts/gen-asyncapi.py` (stdlib only) writes the AsyncAPI export from `apischema.Schema()`:
one channel `socket`, a `send.<event>` operation per client event with `reply` messages
(`reply.<event>...` and `fail.<event>`), a `receive.<event>` operation per server event, every
type and payload in `components.schemas`, and `x-al-*` extensions for what AsyncAPI has no slot
for (docs/WRITING.md, "AsyncAPI export"). `scripts/check-asyncapi.py` needs Docker (node:22,
`@asyncapi/parser` pinned in the script, npm cache in `alapi-examples-npm`): it fails on any
parser error, checks each schema against the draft-07 meta-schema and each message example
against its payload (a mismatch is a warning; on a trimmed example, info). Run both after
touching `schema/`, `apischema.py` or the generator.

`scripts/check-types.py` needs Docker. It runs the schema check with `ALAPI_STRICT_TYPES=1` (no
duplicate or unknown types, no unknown schema keys, every example valid against its type), then
writes every language into `.examples/types/<lang>/` and compiles it (tsc --strict, mypy
--strict, go vet/build, dotnet build, cargo build, mvn compile; `--lang`, `-v`, `--no-strict`).
Run it after touching anything in `schema/`, `apischema.py` or `scripts/gen-types.py`. The
schema format and the type mapping are in docs/WRITING.md, "The schema".

`scripts/check-course.py` needs Docker. It copies each `course/<lang>` to `.course-build/`
(git-ignored), starts `course/test-server` (the fake game) on a Docker network with the pinned
G (`vendor/G/G_17478.json`), builds all seven projects at once (caches in `alapi-course-*`
volumes), then runs each program and matches its output with docs/COURSE.md "The programs"
(`--lang`, `--program`, `--build-only`, `-v`). Run it after touching anything in `course/`.
Learn chapters show course code with includes (`<!-- include course/go/world/world.go
region=step -->`, `includes.py`, docs/EXAMPLES.md "Including code from course/"); the build
fails on a missing file or region, so fix code in `course/`, never on the page.

`scripts/check-examples.py` needs Docker (it compiles in the images of docs/EXAMPLES.md; `--lang`,
`--entry`, `--file` narrow it). Run it after touching any `**Example:**` section or the AlSocket
code in learn-1.md; the rules a snippet must follow are in docs/EXAMPLES.md, "Reference examples".

Everything runs on the host: it's plain Python 3 and static HTML (the owner's global setup keeps
toolchains in dev containers, but this project needs none). Don't use `jq` (not installed).

How `build.py` turns content into entries (ids are the page's `#links`, so keep them stable):

| Kind | From | Id |
|---|---|---|
| learn / game | each `##` of learn-*.md / game-*.md, numbered in file order (`PARTS` names the groups) | `learn-<slug>`, `game-<slug>` |
| guide | `START_HERE` in build.py; each `##` of connect.md; `##` sections of receive.md with no `###` | `start`, `guide-<slug>` |
| send | each `### \`name\`` in send-*.md, grouped by `SEND_GROUPS` in build.py | `send-<name>` |
| recv | each `### \`name\`` in receive.md, grouped by its `##` section | `recv-<name>` |
| code | each row of the table in codes.md | `code-<code>` |
| g | each `###` in game-data.md (`items (638)` → name `items`, badge 638); `##` sections without `###` | `g-<slug>` |
| s | each `##` of server-events.md; each row of its `## Every key` table | `s-<slug>`, `s-key-<key>` |

**The reference is in order of use** (owner, 2026-10-04): connect.md's sections, the
`SEND_GROUPS` groups and the names inside each group, and the entries inside each receive.md
section all run in the order a client meets them (most-used first within a group). The send-*.md
files themselves stay in server-code order; `SEND_GROUPS` decides the page order. Keep new
entries in that order.

The build **fails** if an event in `content/` isn't in exactly one `SEND_GROUPS` group, or if two
entries share an id. A new client→server event means: document it in a `send-*.md` file, then
add its name to a group.

The pages (`template.html`, one template for all three): `[x](#id)` links and code-span
cross-links resolve across pages (the build embeds `links`: id -> other page's file); a run of
adjacent fenced blocks tagged `js ts python go csharp rust java` becomes one tabbed example,
highlighted with highlight.js 11.9.0 from cdnjs; teaching pages get chapter numbers and
previous/next links. Search ranks name match > summary > body, every word must match;
`code` spans whose text is an entry name become cross-links (same kind preferred, then
send > recv > code > g > s); `file.js:123` references become GitHub links pinned to the
commit (`SRC_RE` / `FILES` in the script); markdown renders with marked 12.0.2 from cdnjs.

## Game updates

`versions.json` pins the G version and the live repo commits the content matches.
`python3 scripts/check-updates.py` compares them with the live game (including the game's own
release list, `update_notes.js`) and lists the entries to re-check; `--fix-lines` rewrites
citations whose lines only shifted. `.github/workflows/game-update.yml` runs it daily and opens a
`game-update` issue. The update pass is in `docs/UPDATING.md`.

## Published copies

- Private preview on claude.ai: https://claude.ai/artifact/H7X5sk1iA6rdJVEvE1G1PU. The page
  is the reference's `--fragment` output (that host adds its own `<html>` shell); `learn.html`
  and `game.html` go up as companion files (`files` in the Artifact tool), so the page switcher's
  relative links work. To update from a new session: `python3 build.py --fragment <tmp>`, read
  the artifact (the tool requires it), then publish `<tmp>` with this `url` and
  `files: {"learn.html": "site/learn.html", "game.html": "site/game.html", "types/<f>": {from:
  "site/types/<f>", contentType: "text/plain"}, "asyncapi.json": "site/asyncapi.json"}` for each
  of the six generated type files plus the AsyncAPI document.
- **GitHub: the owner is setting it up** (2026-10-04). Don't run `git init`, `gh repo
  create` or push unless asked. When it exists: serve `site/` with Pages, and
  `.github/workflows/game-update.yml` starts its daily check.
## License and attribution

The game's code is under "AdventureLandOnlyUse" (in `vendor/adventureland/LICENSE`): use is
fine; **attribution is required, and a website needs a crawlable link back to
https://adventure.land**. The page footer and README carry both, plus the pinned commit.
Don't put the game's source files in this repo (that's why `vendor/` is ignored); short quotes
of identifiers and response codes in the reference are the point of it.

## Writing style

All prose follows **Simplified Technical English (ASD-STE100)**: see `docs/STYLE.md`, and apply
it to every page and every new or edited entry. The owner wants plain, direct prose; heavy, useful comments in code; and anything hard-coded
called out with the reason. Entries say "unclear from the source" rather than guess, and flag
server bugs plainly (see `docs/WRITING.md` for the known quirks list).

## Next steps (owner's direction, in rough order)

1. Re-verify the whole API reference against the live code, rewrite it in STE, and move its
   citations to live line numbers (in progress, 2026-10-04).
2. Per-event examples in all seven languages (stage 2, docs/EXAMPLES.md).
3. Re-check the game guide and the Learn chapters against the live code.
4. GitHub: the owner is setting up the repository.
5. Typed payload definitions: done (`scripts/gen-types.py`, seven languages, from `schema/`).
