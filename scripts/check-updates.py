#!/usr/bin/env python3
"""Detects game updates that make this reference stale, and says which entries to re-check.

The reference is written from the live game's open-source code. versions.json pins what it
was written against:

  g_version       the game data G. The live version comes from the front page, which loads
                  `data.js?v=<version>`; the data itself from /data.js.
  source_commit   kaansoral/adventureland_mongodb, the live game's code. It deploys every few
  source_version  days; version.js `Version` moves with each deploy, and update_notes.js is
                  the game's own release list. Every bare `node/server.js:123` citation points
                  into this commit.
  common_commit   kaansoral/common_engine, its shared engine (`common:...` citations).

(legacy_* is the old App Engine repo: frozen, never checked.)

Usage (python3 and git only; run from anywhere):

  python3 scripts/check-updates.py                  # check, print a Markdown report
  python3 scripts/check-updates.py --report r.md    # also write the report to a file
  python3 scripts/check-updates.py --fix-lines      # rewrite citations that only shifted
  python3 scripts/check-updates.py --pin            # after an update pass: move the pins
  python3 scripts/check-updates.py --fingerprint    # rebuild data/g-fingerprint.json from
                                                    # vendor/G/G_<g_version>.json

Exit status: 0 nothing changed, 10 something changed (the report says what), 1 error. CI uses
the 10 to open an issue (.github/workflows/game-update.yml). The update procedure is in
docs/UPDATING.md.

How G is compared. The full G of the pinned version isn't in the repo (it's the game's data,
and the live server only serves the current version). So the repo keeps a fingerprint: one
short hash per key of every table (data/g-fingerprint.json, ~100 KB). That's enough to say
"items.hpot1 changed". If vendor/G/G_<pinned>.json also exists locally, the report adds which
fields changed and how.
"""

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSIONS_FILE = ROOT / "versions.json"
FINGERPRINT_FILE = ROOT / "data" / "g-fingerprint.json"
G_CACHE = ROOT / "vendor" / "G"  # git-ignored with the rest of vendor/
CONTENT = ROOT / "content"
GAME_URL = "https://adventure.land"
UA = {"User-Agent": "adventureland-api-update-check (+https://adventure.land)"}

# The two repos that move. `dir` is where scripts/fetch-source.sh puts each.
REPOS = {
    "source": {"dir": ROOT / "vendor" / "adventureland_mongodb", "pin": "source"},
    "common": {"dir": ROOT / "vendor" / "common_engine", "pin": "common"},
}

# Tables that are art and layout, not rules. Their changes are counted, not listed key by key,
# because a new sprite sheet says nothing about the protocol. Hard-coded from G's top-level keys
# at version 17397; a new table not listed here is treated as a rules table, so it shows up.
ART_TABLES = {"animations", "sprites", "tilesets", "imagesets", "images", "positions",
              "dimensions", "cosmetics"}

# Files in the live repo whose changes can change the protocol a client speaks. Hard-coded from
# the repo's layout on 2026-10-04; the rest (art, admin, Steam, translations) is only counted.
PROTOCOL_FILES = ("node/server.js", "node/server_functions.js", "node/json_parser.js",
                  "node/msgpack_parser.js", "api.js", "main.js", "adventure_functions.js",
                  "mcp_api.js", "js/old_common_functions.js")

# Citation parsing: the same rules as srcHref in template.html. Keep the two in step.
ALIAS = {
    "source": {"server.js": "node/server.js", "server_functions.js": "node/server_functions.js",
               "sf": "node/server_functions.js", "common_functions.js": "js/old_common_functions.js",
               "game.js": "js/game.js"},
    "common": {},
}
ROOT_FILES = {"admin_bots.js", "admin_dashboard.js", "adventure_functions.js", "api.js", "crons.js", "filters.js", "main.js", "mainframe.js", "mcp_api.js", "models.js", "seo_paths.js", "steam_news.js", "steam_signin.js", "steam_signup.js", "update_notes.js", "version.js", "web_assets.js"}
SRC_RE = re.compile(r"\b(?:(common|legacy):)?((?:[\w.-]+/)*[\w.-]+\.(?:js|py|html)|sf):(\d+)"
                    r"(?:(\s*[-–]\s*)(\d+))?")


# --- small helpers ------------------------------------------------------------------------

def http_text(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def key_hash(value):
    # sort_keys so the hash depends on content, not on the order the server wrote keys in.
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha1(raw.encode()).hexdigest()[:10]


def fingerprint(G):
    out = {"version": G.get("version"), "tables": {}}
    for table, value in G.items():
        if table == "version":
            continue
        if isinstance(value, dict):
            out["tables"][table] = {k: key_hash(v) for k, v in value.items()}
        else:  # a few top-level values aren't tables; hash them whole
            out["tables"][table] = {"": key_hash(value)}
    return out


def load_entries():
    """The site's entries (id, kind, name, md), straight from build.py so ids always match."""
    # build.py imports apischema.py and includes.py from the repo root; make them importable
    # when this script runs from anywhere (CI runs it as scripts/check-updates.py).
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("build", ROOT / "build.py")
    mod = importlib.util.module_from_spec(spec)
    saved = sys.argv
    sys.argv = ["build.py"]  # build.py reads sys.argv for --fragment
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = saved
    return mod.items


# --- live state ---------------------------------------------------------------------------

def live_g_version():
    # The front page loads G as `data.js?v=<version>`; that number is G's `version`.
    m = re.search(r"data\.js\?v=(\d+)", http_text(GAME_URL))
    if not m:
        raise RuntimeError("couldn't find data.js?v=<version> on the front page")
    return int(m.group(1))


def fetch_g(version):
    """Live G as a dict, cached at vendor/G/G_<version>.json. /data.js is `var G={...};`."""
    path = G_CACHE / f"G_{version}.json"
    if path.exists():
        return json.loads(path.read_text())
    text = http_text(f"{GAME_URL}/data.js", timeout=180)
    body = text[text.index("{"): text.rindex("}") + 1]
    G = json.loads(body)
    if G.get("version") != version:
        # The game updated between our two requests; trust the data we actually hold.
        version = G.get("version")
        path = G_CACHE / f"G_{version}.json"
    G_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(G))
    return G


def live_source_commit(repo):
    out = git("ls-remote", repo, "HEAD")
    return out.split()[0]


# --- G comparison -------------------------------------------------------------------------

def diff_g(old_fp, new_G, old_G=None):
    """Returns {table: {"added": [...], "removed": [...], "changed": [...]}} plus field-level
    detail for changed keys when the old G is available."""
    new_fp = fingerprint(new_G)
    changes = {}
    tables = set(old_fp["tables"]) | set(new_fp["tables"])
    for t in sorted(tables):
        a, b = old_fp["tables"].get(t, {}), new_fp["tables"].get(t, {})
        c = {
            "added": sorted(set(b) - set(a)),
            "removed": sorted(set(a) - set(b)),
            "changed": sorted(k for k in set(a) & set(b) if a[k] != b[k]),
            "count": (len(a), len(b)),
            "new_table": t not in old_fp["tables"],
            "gone_table": t not in new_fp["tables"],
        }
        if c["added"] or c["removed"] or c["changed"] or c["new_table"] or c["gone_table"]:
            if old_G is not None and t not in ART_TABLES:
                c["fields"] = {k: field_diff(old_G[t][k], new_G[t][k])
                               for k in c["changed"] if isinstance(old_G.get(t), dict)}
            changes[t] = c
    return changes


def field_diff(old, new):
    """`hp: 100 -> 120`-style lines for the top-level fields of one G entry."""
    if not (isinstance(old, dict) and isinstance(new, dict)):
        return [f"{short(old)} -> {short(new)}"]
    lines = []
    for f in sorted(set(old) | set(new)):
        if old.get(f) != new.get(f):
            if f not in old:
                lines.append(f"+ {f}: {short(new[f])}")
            elif f not in new:
                lines.append(f"- {f} (was {short(old[f])})")
            else:
                lines.append(f"{f}: {short(old[f])} -> {short(new[f])}")
    return lines


def short(v, n=70):
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[: n - 1] + "…"


def entries_mentioning(entries, names, table=None):
    """Entry ids whose text names any of `names`. Names that can't be English words (they have
    a digit or underscore: `hpot1`, `level2w`) match as whole words; plain-word names (`cave`,
    `cursed`) only inside backticks, so "monsters" in a sentence doesn't count."""
    hits = {}
    for name in names:
        if len(name) >= 4 and re.search(r"[_0-9]", name):
            pat = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
        else:
            pat = re.compile(rf"`{re.escape(name)}`")
        for e in entries:
            if pat.search(e["md"]):
                hits.setdefault(e["id"], set()).add(name)
    if table:
        gid = f"g-{table}"
        if any(e["id"] == gid for e in entries):
            hits.setdefault(gid, set()).add(f"(the {table} table)")
    return hits


# --- source comparison --------------------------------------------------------------------

def ensure_source(commit_new, cwd):
    """Makes sure `commit_new` is in the local clone, with enough history to log back to the
    pin. fetch-source.sh clones shallow, so this deepens as needed."""
    if not (cwd / ".git").exists():
        subprocess.run(["bash", str(ROOT / "scripts" / "fetch-source.sh")], check=True)
    try:
        git("cat-file", "-e", f"{commit_new}^{{commit}}", cwd=cwd)
    except subprocess.CalledProcessError:
        # 300 commits back covers months of the live repo's pace (~1-5 commits a day).
        git("fetch", "--quiet", "--depth", "300", "origin", commit_new, cwd=cwd)


def hunks(old, new, path, cwd):
    """[(old_start, old_len, new_start, new_len)] from `git diff -U0`."""
    out = git("diff", "-U0", old, new, "--", path, cwd=cwd)
    res = []
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", out, re.M):
        a, b, c, d = m.groups()
        res.append((int(a), int(b or 1), int(c), int(d or 1)))
    return res


def map_line(line, file_hunks):
    """Where an old line is in the new file, or None if a change touched it."""
    shift = 0
    for a, b, c, d in file_hunks:
        if b == 0:  # pure insertion after line a
            if line > a:
                shift += d
            continue
        if a <= line < a + b:
            return None
        if line >= a + b:
            shift += d - b
    return line + shift


def handlers_and_codes(commit, cwd):
    text = git("show", f"{commit}:node/server.js", cwd=cwd)
    text += git("show", f"{commit}:node/server_functions.js", cwd=cwd)
    handlers = set(re.findall(r"socket\.on\(\s*['\"]([^'\"]+)['\"]", text))
    codes = set(re.findall(r'fail_response\("([a-z_0-9]+)"', text))
    codes |= set(re.findall(r'response: ?"([a-z_0-9]+)"', text))
    return handlers, codes


def resolve(prefix, file):
    """(repo key, path) for a citation, or None. Mirrors srcHref in template.html: a bare name
    must have a folder, be an alias, or be a known top-level file of the live repo."""
    repo = {None: "source", "": "source", "common": "common"}.get(prefix)
    if repo is None:  # legacy: frozen repo, never moves
        return None
    path = ALIAS[repo].get(file)
    if path is None and ("/" in file or repo == "common" or file in ROOT_FILES):
        path = file
    return (repo, path) if path else None


def check_citations(repo, old, new, entries, fix=False):
    """Every citation into `repo` in content/: shifted (safe to rewrite) or touched (re-read)."""
    cwd = REPOS[repo]["dir"]
    cache = {}
    shifted, touched = [], []
    # Citations live in the Markdown and in the schema (`source`, `confirm.code`); both shift.
    # schema/live.json is generated from captures and has no citations to move.
    files = sorted(CONTENT.glob("*.md")) + sorted(
        p for p in (ROOT / "schema").rglob("*.json") if p.name != "live.json")
    for f in files:
        text = f.read_text()

        def repl(m):
            prefix, name, a, sep, b = m.group(1), m.group(2), int(m.group(3)), m.group(4), m.group(5)
            where = resolve(prefix, name)
            if not where or where[0] != repo:
                return m.group(0)
            path = where[1]
            if path not in cache:
                cache[path] = hunks(old, new, path, cwd)
            na = map_line(a, cache[path])
            nb = map_line(int(b), cache[path]) if b else None
            if na is None or (b and nb is None):
                touched.append((f.name, m.group(0)))
                return m.group(0)
            if na != a or (b and nb != int(b)):
                head = (f"{prefix}:" if prefix else "") + name
                new_ref = f"{head}:{na}" + (f"{sep}{nb}" if b else "")
                shifted.append((f.name, m.group(0), new_ref))
                return new_ref
            return m.group(0)

        new_text = SRC_RE.sub(repl, text)
        if fix and new_text != text:
            f.write_text(new_text)
    touched_entries = {}
    for fname, ref in touched:
        for e in entries:
            if ref in e["md"]:
                touched_entries.setdefault(e["id"], set()).add(ref)
    return shifted, touched, touched_entries


def live_repo_version(commit):
    m = re.search(r"Version\s*=\s*(\d+)", git("show", f"{commit}:version.js",
                                                 cwd=REPOS["source"]["dir"]))
    return int(m.group(1)) if m else None


def releases(commit):
    """Top-level entries of the live repo's update_notes.js, as dicts. It's a JS file, so this
    reads it with regexes keyed on its fixed layout: one tab before `{`, two before the fields
    (as of 2026-10-04). Older plain one-line notes have no `phrase`; they're skipped."""
    try:
        text = git("show", f"{commit}:update_notes.js", cwd=REPOS["source"]["dir"])
    except subprocess.CalledProcessError:
        return []
    out = []
    for block in re.split(r"\n\t\{\n", text)[1:]:
        field = lambda k: (re.search(rf'^\t\t{k}: (?:"((?:[^"\\]|\\.)*)"|null)', block, re.M)
                           or [None, None])[1]
        if field("phrase"):
            out.append({k: field(k) for k in ("phrase", "deployed", "date", "title", "note")})
    return out


def repo_section(repo, pins, live, entries, fix):
    """What changed in one repo: commits, releases (source only), protocol files, handlers,
    response codes, and the citations that moved."""
    cwd = REPOS[repo]["dir"]
    key = REPOS[repo]["pin"]
    old, new = pins[f"{key}_commit"], live[f"{key}_commit"]
    title = "Live code" if repo == "source" else "Common engine"
    ver = (f": version {pins['source_version']} -> {live['source_version']}"
           if repo == "source" else "")
    out = [f"## {title}{ver}", "", f"Compare: {pins[f'{key}_repo']}/compare/{old}...{new}", ""]
    try:
        log = git("log", "--format=%h %cd %s", "--date=short", f"{old}..{new}",
                  cwd=cwd).strip().splitlines()
        out += ["```", *log[:40], *(["…"] if len(log) > 40 else []), "```", ""]
    except subprocess.CalledProcessError:
        out += ["(The pinned commit is too far back to log; use the compare link.)", ""]
        return out
    if repo == "source":
        # update_notes.js is the game's own release list (newest first). A release gets
        # `deployed: "<date>"` when it ships; until then `deployed: null`.
        before = {r["phrase"]: r for r in releases(old)}
        shipped = [r for r in releases(new)
                   if r["deployed"] and not (before.get(r["phrase"]) or {}).get("deployed")]
        if shipped:
            out += ["### Releases shipped since the pin (update_notes.js)", ""]
            out += [f"- **{r['title']}** (deployed {r['deployed']}): {r['note']}" for r in shipped]
            out.append("")
        files = git("diff", "--name-only", old, new, cwd=cwd).split()
        proto = [f for f in files if f in PROTOCOL_FILES or f.startswith("node/logic/")]
        out += [f"**Files:** {len(files)} changed; protocol-relevant: " +
                (", ".join(f"`{f}`" for f in proto) if proto else "none"), ""]
        h_old, c_old = handlers_and_codes(old, cwd)
        h_new, c_new = handlers_and_codes(new, cwd)
        for label, s in (("New socket handlers (document them; add to SEND_GROUPS in build.py)",
                          h_new - h_old),
                         ("Removed socket handlers", h_old - h_new),
                         ("New response codes (add rows to the game_response table)",
                          c_new - c_old),
                         ("Removed response codes", c_old - c_new)):
            if s:
                out += [f"**{label}:** " + ", ".join(f"`{x}`" for x in sorted(s)), ""]
    shifted, touched, touched_entries = check_citations(repo, old, new, entries, fix=fix)
    out += [f"**Citations:** {len(shifted)} only shifted " +
            ("(rewritten by --fix-lines)" if fix else "(run with --fix-lines to rewrite them)") +
            f"; {len(touched)} point at lines the change touched.", ""]
    if touched_entries:
        out += ["### Entries whose cited lines changed (re-read the code)", ""]
        out += bullets(touched_entries, 120) + [""]
    return out


# --- report -------------------------------------------------------------------------------

def bullets(hits, limit=40):
    lines = [f"- [ ] `{eid}`: {', '.join(sorted(names)[:6])}" +
             (" …" if len(names) > 6 else "")
             for eid, names in sorted(hits.items())[:limit]]
    if len(hits) > limit:
        lines.append(f"- … and {len(hits) - limit} more")
    return lines


def g_section(pins, live, entries):
    new_G = fetch_g(live["g_version"])
    old_fp = json.loads(FINGERPRINT_FILE.read_text())
    old_path = G_CACHE / f"G_{pins['g_version']}.json"
    old_G = json.loads(old_path.read_text()) if old_path.exists() else None
    changes = diff_g(old_fp, new_G, old_G)
    out = [f"## G: {pins['g_version']} -> {live['g_version']}", ""]
    if old_G is None:
        out += ["Key-level comparison only (no local copy of the pinned G, so no field "
                "detail).", ""]
    art = {t: c for t, c in changes.items() if t in ART_TABLES}
    if art:
        out += ["Art/layout tables changed (not listed key by key): " + ", ".join(
            f"{t} ({len(c['added'])}+ {len(c['removed'])}- {len(c['changed'])}~)"
            for t, c in art.items()), ""]
    all_hits = {}
    for t, c in changes.items():
        if t in ART_TABLES:
            continue
        a, b = c["count"]
        head = f"### `{t}`" + (" (new table)" if c["new_table"] else "") + \
               (" (table removed)" if c["gone_table"] else "") + \
               (f": {a} -> {b} keys" if a != b else "")
        out += [head, ""]
        for label in ("added", "removed", "changed"):
            if c[label]:
                shown = c[label][:60]
                more = f" … +{len(c[label]) - 60}" if len(c[label]) > 60 else ""
                out.append(f"- **{label}** ({len(c[label])}): " +
                           ", ".join(f"`{k}`" for k in shown) + more)
        for k, lines in list(c.get("fields", {}).items())[:30]:
            out.append(f"  - `{k}`: " + "; ".join(lines[:8]) + (" …" if len(lines) > 8 else ""))
        if a != b:
            # Only when the number sits next to the table name: "items (638)", "638 items".
            near = re.compile(rf"\b{t}\W{{0,3}}\(?{a}\b|\b{a}\W+(?:\w+\W+){{0,3}}?{t}\b")
            for e in entries:
                if near.search(e["md"]):
                    all_hits.setdefault(e["id"], set()).add(f"count {a} of {t}?")
        out.append("")
        for eid, names in entries_mentioning(entries, c["changed"] + c["removed"],
                                             table=t).items():
            all_hits.setdefault(eid, set()).update(names)
    if all_hits:
        out += ["### Entries to re-check for G", ""] + bullets(all_hits, 80) + [""]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--report", help="also write the Markdown report to this file")
    ap.add_argument("--fix-lines", action="store_true",
                    help="rewrite citations whose lines only shifted in a new commit")
    ap.add_argument("--pin", action="store_true",
                    help="after an update pass: pin the live versions in versions.json")
    ap.add_argument("--fingerprint", action="store_true",
                    help="rebuild data/g-fingerprint.json from vendor/G/G_<g_version>.json")
    args = ap.parse_args()
    pins = json.loads(VERSIONS_FILE.read_text())

    if args.fingerprint:
        G = json.loads((G_CACHE / f"G_{pins['g_version']}.json").read_text())
        FINGERPRINT_FILE.parent.mkdir(exist_ok=True)
        FINGERPRINT_FILE.write_text(json.dumps(fingerprint(G), sort_keys=True) + "\n")
        print(f"wrote {FINGERPRINT_FILE.relative_to(ROOT)} for G {pins['g_version']}")
        return 0

    live = {"g_version": live_g_version()}
    for repo, r in REPOS.items():
        commit = live_source_commit(pins[f"{r['pin']}_repo"])
        live[f"{r['pin']}_commit"] = commit
        if commit != pins[f"{r['pin']}_commit"]:
            ensure_source(commit, r["dir"])
    live["source_version"] = (live_repo_version(live["source_commit"])
                              if live["source_commit"] != pins["source_commit"]
                              else pins["source_version"])

    if args.pin:
        changed = {k: (pins[k], v) for k, v in live.items() if pins[k] != v}
        if "g_version" in changed:
            G = fetch_g(live["g_version"])
            FINGERPRINT_FILE.write_text(json.dumps(fingerprint(G), sort_keys=True) + "\n")
        for repo, r in REPOS.items():
            if f"{r['pin']}_commit" in changed:
                git("checkout", "--quiet", live[f"{r['pin']}_commit"], cwd=r["dir"])
        pins.update(live)
        pins["pinned_on"] = date.today().isoformat()
        VERSIONS_FILE.write_text(json.dumps(pins, indent=2) + "\n")
        for k, (a, b) in changed.items():
            print(f"pinned {k}: {a} -> {b}")
        print("nothing to pin" if not changed else "rebuild with: python3 build.py")
        return 0

    entries = load_entries()
    sv = lambda d: f"`{d['source_commit'][:10]}` (version {d['source_version']})"
    out = [f"# Game update check, {date.today().isoformat()}", "",
           "| | Pinned | Live |", "|---|---|---|",
           f"| G version | {pins['g_version']} | {live['g_version']} |",
           f"| Live code | {sv(pins)} | {sv(live)} |",
           f"| Common engine | `{pins['common_commit'][:10]}` | `{live['common_commit'][:10]}` |", ""]
    drift = False
    if live["g_version"] != pins["g_version"]:
        drift = True
        out += g_section(pins, live, entries)
    for repo, r in REPOS.items():
        if live[f"{r['pin']}_commit"] != pins[f"{r['pin']}_commit"]:
            drift = True
            out += repo_section(repo, pins, live, entries, args.fix_lines)
    if not drift:
        out += ["Nothing changed. The reference matches the live game's pins."]
    else:
        out += ["## Next", "", "Follow docs/UPDATING.md: update the entries above, then "
                "`python3 scripts/check-updates.py --pin` and `python3 build.py`."]
    report = "\n".join(out) + "\n"
    print(report)
    if args.report:
        Path(args.report).write_text(report)
    return 10 if drift else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # network down, git missing...: say so, don't report "no change"
        print(f"check-updates: error: {e}", file=sys.stderr)
        sys.exit(1)
