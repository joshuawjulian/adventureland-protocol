#!/usr/bin/env python3
"""
Builds the site: site/index.html (the start page), game.html, learn.html, reference.html (the
interactive Adventure Land API reference) and deck.html (the game guide as slides).

    python3 build.py

Reads the Markdown in content/, splits it into entries (one per event, response code, game-data
table, server-event key, guide section), and embeds them as JSON in template.html. The result is
one self-contained page: open it locally, or serve the site/ folder with GitHub Pages.

No dependencies beyond Python 3. Markdown is rendered in the browser (marked, from cdnjs).
"""

import json
import os
import re
import sys
from pathlib import Path

import apischema
import includes

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
# Which code the citations point into lives in versions.json, so the build, scripts/fetch-source.sh
# and scripts/check-updates.py agree on one pin. The page links `node/server.js:N` to `live`,
# `common:...` to `common` and `legacy:...` to `legacy` (see srcHref in template.html).
VERSIONS = json.loads((ROOT / "versions.json").read_text())
SOURCES = {name: {"repo": VERSIONS[f"{key}_repo"], "commit": VERSIONS[f"{key}_commit"]}
           for name, key in (("live", "source"), ("common", "common"), ("legacy", "legacy"))}

# Groups for the events a client sends. Every event must appear in exactly one; the build fails
# loudly otherwise, so a newly documented event can't silently go missing from the index.
SEND_GROUPS = [
    # In the order a client meets them: connect, walk, fight, loot and use items, buy potions,
    # upgrade, talk, trade, then the extras. Within a group, the most-used event comes first.
    ("Session and connection", "Logging in, staying connected, asking the server for data.",
     "loaded auth ping_trig send_updates property requested_ack players code ccreport mreport "
     "blocker error disconnect o:home o:command"),
    ("Movement and maps", "Walking, doors, teleports, towns and dying.",
     "move stop town transport enter leave respawn set_home magiport join cruise"),
    ("Combat and skills", "Targeting, attacking, healing and class skills.",
     "target attack heal skill monsterhunt tracker duel harakiri"),
    ("Items and equipment", "Your inventory: looting, equipping, using and moving things.",
     "open_chest equip use unequip imove split merge equip_batch destroy throw activate booster "
     "convert destat locksmith unlock dismantle"),
    ("NPC shops and the bank", "Buying and selling with NPCs, and storage.",
     "buy sell bank secondhands lostandfound sbuy buy_with_cash buy_shells misc_npc donate "
     "bless_server"),
    ("Upgrading, crafting and exchanges", "Turning items into better items.",
     "upgrade compound exchange exchange_buy craft"),
    ("Social", "Chat, parties, friends.", "say party friend cm poke"),
    ("Trading with players", "Gifts, merchant stands, trades and mail.",
     "send merchant trade_sell trade_buy trade_swap trade_wishlist trade_history trade mail "
     "mail_take_item"),
    ("Games, events and rewards", "Event sign-ups, monster hunts' rewards, tavern games, pets.",
     "join_giveaway signup interaction ureward creward tavern poker bet play tarot whistle pet "
     "pets list_pvp deepsea legacify"),
    ("Cosmetics", "How your character looks.", "cx random_look skin blend"),
    ("Admin and development",
     "Game-master, test and debugging handlers. A normal client never sends these.",
     "gm test eval shutdown notice render click"),
]

START_HERE = """
The API reference for [Adventure Land](https://adventure.land): every event a client sends,
every event the server sends, every `game_response` code, the game data (**G**) and the
server's event state (**S**). It is written from the live game's open-source code,
[kaansoral/adventureland_mongodb](https://github.com/kaansoral/adventureland_mongodb). Each
source reference links to the exact line at the pinned commit.

For a course from zero, see [Build a bot](learn.html). For how the game works, see the
[Game guide](game.html).

## Entry layout

| Kind | Sections, in order |
|---|---|
| Event you send | summary, **Send**, **Request** (fields, JSON), **Responses** (order, each reply with fields and JSON, then the **Failure** table in check order), **Also sent**, **Limits**, **Notes**, **Example**, **Source** |
| Event you receive | summary, **Payload** (fields, JSON), **Sent to**, **Sent by**, **Notes**, **Example**, **Source** |
| Response code | meaning, how it arrives, **Exact replies** (each request that sends it, with the JSON) |
| Type | the named types of the Type column: see [Types](#guide-types) |
| G table / S key | fields, how the server uses them, source |

Examples come in JavaScript, TypeScript, Python, Go, C#, Rust and Java (top bar). They use
`sock`, a connected [`AlSocket`](learn.html#learn-alsocket).

The group **Async in your language** explains how your language runs a client that reads,
waits and acts at the same time. Start with
[The async model of your language](#guide-the-async-model-of-your-language).

## Typed definitions

The [schema](#guide-types) also generates typed definitions of every request and reply, for
use in your client: [TypeScript](types/al-api.ts), [Python](types/al_api.py),
[Go](types/alapi.go), [C#](types/AlApi.cs), [Rust](types/al_api.rs),
[Java](types/AlApi.java). Each one compiles in strict mode (`scripts/check-types.py`).
The same API is also an [AsyncAPI 3.0 document](asyncapi.json), for code generators and
documentation tools.

## Conventions

- A failure arrives as `game_response` `{response: "<code>", place: "<event>", failed: true}`.
  Each code has its own entry.
- Some results arrive later, inside a `player` event ("hitchhikers"): see
  [`player`](#recv-player).
- Many handlers reply with objects when the request has a `request_id`, and with bare strings
  or nothing when it does not. Each entry states both.
- Units, ids and formats: [Units and conventions](#guide-units-and-conventions).
"""


def slug(text):
    return re.sub(r"[^a-z0-9_]+", "-", text.lower()).strip("-")


def read(name):
    """A content file, with its `<!-- include ... -->` lines expanded into fenced blocks of
    code from course/ (includes.py; docs/EXAMPLES.md, "Including code from course/"). A missing
    file or region stops the build."""
    try:
        # A missing file or region is fatal under ALAPI_STRICT_TYPES=1 (the convention of the
        # schema work); otherwise a warning, so the build passes while course/ is written.
        return includes.expand((CONTENT / name).read_text(), f"content/{name}",
                               strict=bool(os.environ.get("ALAPI_STRICT_TYPES")),
                               warn=lambda m: print(f"warning: include: {m}", file=sys.stderr))
    except includes.IncludeError as e:
        raise SystemExit(f"include: {e}")


def split(text, level):
    """Splits Markdown at headings of `level` (2 or 3). Returns (heading, body) pairs, with the
    text before the first heading as heading None."""
    marker = "#" * level + " "
    parts = re.split(rf"(?m)^(?={re.escape(marker)})", text)
    out = []
    for part in parts:
        if part.startswith(marker):
            heading, _, body = part.partition("\n")
            out.append((heading[len(marker):].strip(), body.strip()))
        elif part.strip():
            out.append((None, part.strip()))
    return out


def first_sentence(md):
    for line in md.splitlines():
        line = line.strip()
        if not line or line.startswith(("|", "#", "```", "**Send", "**Payload", "![")):
            continue
        line = re.sub(r"[*_`]", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        return re.split(r"(?<=[.!?])\s", line)[0][:220]
    return ""


def code_name(heading):
    m = re.match(r"`([^`]+)`", heading)
    return m.group(1) if m else heading


def demote(md, by=1):
    """Pushes headings down so an entry's own sub-headings sit under its title."""
    return re.sub(r"(?m)^(#{2,5}) ", lambda m: "#" * min(6, len(m.group(1)) + by) + " ", md)


items = []

# The machine-readable schema (schema/*.json, read by apischema.py). An entry whose Markdown has
# the line `<!-- schema -->` gets its Request / Responses / Also sent (send) or Payload / Sent to
# / Sent by (receive) sections from the schema at that spot. The schema is checked on load.
SCHEMA = apischema.Schema()
RENDER = apischema.Renderer(SCHEMA)
MARKER = "<!-- schema -->"
# On a schema entry, the hand-written labels become headings, so that all sections of the entry
# look the same. The content files keep the bold labels: scripts/check-examples.py finds
# `**Example:**`.
LABELS = re.compile(r"(?m)^\*\*(Limits|Notes|Example|Source):\*\*[ \t]*\n*")


def expand(kind, name, md):
    specs = SCHEMA.send if kind == "send" else SCHEMA.recv
    if MARKER not in md:
        if name in specs:
            # Mid-conversion (schema written, entry not yet switched) this is normal; it only
            # fails the build in strict mode (ALAPI_STRICT_TYPES=1, the final check).
            msg = f"{specs[name]['_file']} exists, but the {kind} entry `{name}` has no {MARKER} line"
            if os.environ.get("ALAPI_STRICT_TYPES"):
                raise SystemExit(msg)
            print(f"warning: {msg}", file=sys.stderr)
        return md
    if name not in specs:
        raise SystemExit(f"the {kind} entry `{name}` has {MARKER}, but schema/{kind}/{name}.json "
                         f"does not exist")
    body = RENDER.send_md(name) if kind == "send" else RENDER.recv_md(name)
    md = md.replace(MARKER, body)
    md = LABELS.sub(lambda m: f"#### {m.group(1)}\n\n", md)
    # Every entry of a kind has the same sections in the same order, empty ones as "None."
    # (apischema.finish_entry; fatal under ALAPI_STRICT_TYPES=1 when the order is wrong).
    return apischema.finish_entry(kind, name, md)



def add(kind, group, name, md, id_=None, summary=None, extra=None):
    item = {
        "id": id_ or f"{kind}-{slug(name)}",
        "kind": kind,
        "group": group,
        "name": name,
        "summary": summary if summary is not None else first_sentence(md),
        "md": md,
    }
    if extra:
        item.update(extra)
    items.append(item)


# Guide: start here, then the connection sections.
add("guide", "Start here", "Start here", START_HERE.strip(), id_="start",
    summary="What this reference is, how to read it, and where to begin.")
for heading, body in split(read("connect.md"), 2):
    if heading is None:
        continue
    add("guide", "Connecting", heading, demote(body), id_=f"guide-{slug(heading)}")

# Async in your language: an overview, then a lecture in chapters. Most of each chapter is
# prose per language (<div data-lang> blocks, langTabs in template.html).
for heading, body in split(read("async.md"), 2):
    if heading is None:
        continue
    add("guide", "Async in your language", heading, demote(body), id_=f"guide-{slug(heading)}")

# Types: an overview, then one entry per named type of the schema (id type-<name>), so field
# tables can link each type.
add("guide", "Types", "Types", RENDER.types_overview_md(), id_="guide-types",
    summary="How to read the Type column, and every named type.")
for tname in sorted(SCHEMA.types):
    add("guide", "Types", tname, RENDER.type_md(tname), id_=apischema.type_anchor(tname),
        summary=re.sub(r"[`*]", "", SCHEMA.types[tname]["summary"]))

# Events you send.
send = {}
for f in sorted(CONTENT.glob("send-*.md")):
    for heading, body in split(read(f.name), 3):
        if heading:
            send[code_name(heading)] = expand("send", code_name(heading), body)
missing_md = sorted(set(SCHEMA.send) - set(send))
if missing_md:
    raise SystemExit(f"schema/send has events that content/ doesn't document: {missing_md}")
placed = set()
for group, blurb, names in SEND_GROUPS:
    for name in names.split():
        if name not in send:
            raise SystemExit(f"send group lists '{name}', but content/ doesn't document it")
        if name in placed:
            raise SystemExit(f"'{name}' is in two send groups")
        placed.add(name)
        emit = re.search(r"\*\*Send:\*\*[^`]*`([^`]+)`", send[name])
        add("send", group, name, send[name],
            extra={"emit": emit.group(1) if emit else None, "groupBlurb": blurb})
missing = sorted(set(send) - placed)
if missing:
    raise SystemExit(f"documented but in no send group: {', '.join(missing)}")

# Events the server sends: grouped by the receive file's own sections.
for section, body in split(read("receive.md"), 2):
    if section is None:
        continue
    events = split(body, 3)
    if not any(h for h, _ in events):
        add("guide", "Events the server sends", section, demote(body, 1),
            id_=f"guide-{slug(section)}")
        continue
    for heading, md in events:
        if heading:
            add("recv", section, code_name(heading), expand("recv", code_name(heading), md))
missing_md = sorted(set(SCHEMA.recv) - {i["name"] for i in items if i["kind"] == "recv"})
if missing_md:
    raise SystemExit(f"schema/recv has events that content/ doesn't document: {missing_md}")

# Response codes: one entry per row of game_response's table.
# The table lives in its own file, content/codes.md, so the codes and the receive events can be
# edited separately.
table = read("codes.md")
for row in re.findall(r"(?m)^\|\s*`([^`]+)`\s*\|(.+?)\|(.+?)\|\s*$", table):
    code, meaning, where = (c.strip() for c in row)
    letter = code[0].upper() if code[0].isalpha() else "#"
    md = (f"{meaning}\n\n**Arrives as:** `game_response` with `response: \"{code}\"`. See "
          f"[`game_response`](#recv-game_response) for the shared fields "
          f"(`place`, `failed`, `success`...).\n\n**Sent from:** {where}")
    exact = RENDER.code_md(code)  # every reply with this code, from the schema ("None" row if none)
    md = apischema.finish_entry("code", code, md + "\n\n" + exact)
    add("code", letter, code, md, id_=f"code-{slug(code)}", summary=re.sub(r"[`*]", "", meaning))

# Game data (G).
for section, body in split(read("game-data.md"), 2):
    if section is None:
        continue
    tables = split(body, 3)
    if any(h for h, _ in tables):
        intro = next((md for h, md in tables if h is None), "")
        if intro:
            add("g", "Overview", section, intro, id_=f"g-{slug(section)}")
        for heading, md in tables:
            if heading:
                name = re.sub(r"\s*\(\d[^)]*\)\s*$", "", heading)  # "items (638)" -> "items"
                count = re.search(r"\((\d+)", heading)
                add("g", "Tables", name, md, id_=f"g-{slug(name)}",
                    extra={"badge": count.group(1) if count else None})
    else:
        add("g", "Overview", section, body, id_=f"g-{slug(section)}")

# Server events (S): its sections, plus one entry per key from the "Every key" table.
for section, body in split(read("server-events.md"), 2):
    if section is None:
        continue
    add("s", "Overview", section, demote(body), id_=f"s-{slug(section)}")
    if section == "Every key":
        lines = [l for l in body.splitlines() if l.startswith("|")]
        header = [h.strip() for h in lines[0].strip("|").split("|")]
        for line in lines[2:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            key = cells[0].strip("` ")
            details = "\n".join(f"- **{h}:** {c}" for h, c in zip(header[1:], cells[1:]) if c)
            md = (f"{details}\n\nPart of **S**, the server's event state. See "
                  f"[What S is](#s-what-s-is) and [Shape](#s-shape).")
            add("s", "Keys", key, md, id_=f"s-key-{slug(key)}", summary=" · ".join(cells[1:3]))

# The two teaching pages. Each `##` of learn-*.md / game-*.md is one chapter, numbered in file
# order so the index reads like a table of contents. The part name comes from the file's title
# line (`# Part 1: ...`) when there is one, else from PARTS below.
PARTS = {
    "learn-1.md": "Part 1 · The wire",
    "learn-2.md": "Part 2 · Talking to Adventure Land",
    "learn-3.md": "Part 3 · Building a bot",
    "game-1.md": "The world and your character",
    "game-2.md": "Items, economy and events",
}
for kind in ("learn", "game"):
    num = 0
    # Numbered files only: game-data.md is the G reference, not a guide chapter.
    for f in sorted(CONTENT.glob(f"{kind}-[0-9]*.md")):
        group = PARTS.get(f.name, f.stem)
        for heading, body in split(read(f.name), 2):
            if heading is None:
                title = re.match(r"#\s+(.+)", body)
                if title and f.name not in PARTS:  # PARTS wins, so the labels stay uniform
                    group = title.group(1).strip()
                continue
            num += 1
            add(kind, group, heading, demote(body), id_=f"{kind}-{slug(heading)}",
                extra={"num": num})

ids = [i["id"] for i in items]

# Every [text](#id) link must point at an entry, on any page. Entries get removed when the live
# server drops an event, so this catches the links left behind.
known = set(ids)
broken = sorted({(i["id"], m) for i in items for m in re.findall(r"\]\(#([^)\s]+)\)", i["md"])
                 if m not in known})
if broken:
    raise SystemExit("broken links:\n" + "\n".join(f"  in {a}: #{b}" for a, b in broken))
dupes = {i for i in ids if ids.count(i) > 1}
if dupes:
    raise SystemExit(f"duplicate ids: {', '.join(sorted(dupes))}")

# Three pages from one template, so the reference stays a reference and the teaching material
# has room to breathe. Every page also gets `links`: id -> [file, kind, name] for the entries
# that live on the *other* pages, so `#send-move` in the tutorial (or a `move` code span)
# still finds its way to the reference.
# In reading order (owner, 2026-10-04): how the game works, then build a bot, then the reference.
# The site root (index.html) is the start page, home.html; it forwards an old `index.html#id` link
# to reference.html, where the reference lived before.
PAGES = [
    {"id": "game", "file": "game.html", "title": "Game guide", "kinds": ["game"],
     "doc_title": "Adventure Land: Game Guide"},
    {"id": "learn", "file": "learn.html", "title": "Build a bot", "kinds": ["learn"],
     "doc_title": "Adventure Land: Build a Bot"},
    {"id": "ref", "file": "reference.html", "title": "API reference",
     "kinds": ["guide", "send", "recv", "code", "g", "s"], "doc_title": "Adventure Land API"},
]
# A page with nothing in it yet (its content files not written) is left out, nav included.
PAGES = [p for p in PAGES if any(i["kind"] in p["kinds"] for i in items)]
page_of = {i["id"]: p for p in PAGES for i in items if i["kind"] in p["kinds"]}
template = (ROOT / "template.html").read_text()
(ROOT / "site").mkdir(exist_ok=True)


def render(page):
    mine = [i for i in items if i["kind"] in page["kinds"]]
    links = {i["id"]: [page_of[i["id"]]["file"], i["kind"], i["name"]]
             for i in items if page_of[i["id"]] is not page}
    data = {
        "page": {k: page[k] for k in ("id", "title", "doc_title")},
        "pages": [{"id": "home", "file": "index.html", "title": "Start"}]
                 + [{k: p[k] for k in ("id", "file", "title")} for p in PAGES],
        "items": mine,
        "links": links,
        "source": SOURCES,
    }
    body = template.replace("__TITLE__", page["doc_title"]).replace(
        "__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    # The template is the page's content without the document shell. GitHub Pages (and a
    # browser opening the file) needs the full document; `--fragment PATH` also writes the
    # reference page's bare content, for hosts that add their own shell.
    head, _, rest = body.partition("</style>")
    full = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        + head + "</style>\n</head>\n<body>\n" + rest + "\n</body>\n</html>\n"
    )
    (ROOT / "site" / page["file"]).write_text(full)
    print(f"site/{page['file']}: {len(mine)} entries, {len(full) // 1024} KB")
    return body


# Imported (scripts/check-updates.py does, for `items`), the module only collects entries.
# Typed definitions of the whole socket API, generated from schema/ by scripts/gen-types.py,
# published next to the pages so a reader can download them for their language. File name per
# language, as the reference start page links them.
TYPE_FILES = {"ts": "al-api.ts", "python": "al_api.py", "go": "alapi.go",
              "csharp": "AlApi.cs", "rust": "al_api.rs", "java": "AlApi.java"}


def write_types():
    import subprocess
    out = ROOT / "site" / "types"
    out.mkdir(parents=True, exist_ok=True)
    for lang, name in TYPE_FILES.items():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "gen-types.py"), "--lang", lang,
                        "-o", str(out / name)], check=True)
    print(f"site/types/: {len(TYPE_FILES)} typed-definition files")
    # The same API as a standard AsyncAPI 3.0 document (scripts/gen-asyncapi.py; validated by
    # scripts/check-asyncapi.py), for code generators and doc tools.
    subprocess.run([sys.executable, str(ROOT / "scripts" / "gen-asyncapi.py"), "-o",
                    str(ROOT / "site" / "asyncapi.json")], check=True)
    print("site/asyncapi.json: AsyncAPI 3.0")


def write_home():
    """The start page: home.html as it is, plus the pinned commit for its footer."""
    live = SOURCES["live"]
    html = (ROOT / "home.html").read_text().replace("__REPO__", live["repo"]).replace(
        "__COMMIT__", live["commit"]).replace("__SHORT__", live["commit"][:7])
    (ROOT / "site" / "index.html").write_text(html)
    print("site/index.html: start page")


if __name__ == "__main__":
    for page in PAGES:
        body = render(page)
        if page["id"] == "ref" and "--fragment" in sys.argv:
            Path(sys.argv[sys.argv.index("--fragment") + 1]).write_text(body)

    counts = {}
    for i in items:
        counts[i["kind"]] = counts.get(i["kind"], 0) + 1
    print(f"total: {len(items)} entries {counts}")
    write_types()
    write_home()
    # The game guide as slides: deck/ holds the slides, scripts/build-deck.py makes the page.
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build-deck.py")], check=True)
