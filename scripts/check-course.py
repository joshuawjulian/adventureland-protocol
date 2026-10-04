#!/usr/bin/env python3
"""Builds the course library in all seven languages and runs its programs against the local
test server (docs/COURSE.md).

What it does:

  1. Copies each `course/<lang>` project and `course/test-server` to `.course-build/` (git-ignored),
     so the build output and package caches never land in course/.
  2. Starts the test server in Docker (`node:22`) on a private Docker network, with the pinned G
     (`vendor/G/G_17478.json`), and waits until it answers HTTP.
  3. Builds all languages at the same time, each in its image of docs/EXAMPLES.md, with package
     caches in named Docker volumes (`alapi-course-*`; a rerun downloads nothing).
  4. Runs the programs of each language, one language at a time (they share the test server's
     characters), after a `POST /test/reset`. Each program must exit with status 0 and print the
     lines of docs/COURSE.md ("The programs"); EXPECT below holds those lines as patterns.
  5. Prints a table (language x program) and exits 1 if anything failed.

Usage (python3 and docker only; run from anywhere):

  python3 scripts/check-course.py                    # everything
  python3 scripts/check-course.py --lang go          # one language (repeatable)
  python3 scripts/check-course.py --program al-test  # one program (repeatable)
  python3 scripts/check-course.py --build-only       # compile, run nothing
  python3 scripts/check-course.py -v                 # also print build and program output

The first run downloads images and packages (several minutes, mostly Rust and Java); later runs
take a few minutes, most of it the programs themselves (al-test idles 3 s on purpose).

To add a program (Parts 2 and 3): add it to PROGRAMS and EXPECT, with its file name in each
language (NAMES), in the same pass as docs/COURSE.md.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COURSE = ROOT / "course"
BUILD = ROOT / ".course-build"
G_FILE = ROOT / "vendor" / "G" / "G_17478.json"  # the pinned G (versions.json g_version)

LANGS = ["js", "ts", "python", "go", "csharp", "rust", "java"]
IMAGES = {
    "js": "node:22", "ts": "node:22", "python": "python:3.12-slim", "go": "golang:1.22",
    "csharp": "mcr.microsoft.com/dotnet/sdk:8.0", "rust": "rust:1",
    "java": "maven:3-eclipse-temurin-21",
}
# One network and one server container per run, so that several runs (one per language, for
# example) can go at the same time without seeing each other's test server.
RUN_ID = f"{os.getpid()}"
NETWORK = f"alapi-course-{RUN_ID}"
SERVER = f"alapi-course-server-{RUN_ID}"  # container name
HOST = "al-test-server"         # its name on the network, as the programs see it
PORT = 8022                     # TEST_PORT's default
VOL = "alapi-course-"

# Build output and caches: kept in .course-build between runs, never copied from course/.
KEEP = {"node_modules", ".venv", "__pycache__", ".mypy_cache", "bin", "obj", "target",
        ".al-cache", "cp.txt", "G.json"}

# Pins that are not in a project file (the projects pin their own packages).
MYPY = "mypy==1.13.0"

# Build commands, run in /w (the copied project). Package caches live in the volumes.
BUILD_CMD = {
    "js": "npm install --no-audit --no-fund --silent && npx tsc -p . --pretty false",
    "ts": "npm install --no-audit --no-fund --silent && npx tsc -p . --pretty false",
    # The venv lives in a volume; it is rebuilt when requirements.txt changes (marker file).
    "python": ('h=$(cat requirements.txt | md5sum | cut -c1-12); '
               'if [ "$(cat /venv/.req 2>/dev/null)" != "$h" ]; then rm -rf /venv/* && '
               f'python -m venv /venv && /venv/bin/pip install -q -r requirements.txt {MYPY} && '
               'echo "$h" > /venv/.req; fi; '
               '/venv/bin/python -m compileall -q albot *.py && '
               '/venv/bin/mypy --python-version 3.11 --no-error-summary --hide-error-context '
               '--no-color-output --cache-dir .mypy_cache albot *.py'),
    # GOTOOLCHAIN=local: never download a newer Go than the image's 1.22 (the reader's).
    "go": ("export GOTOOLCHAIN=local; go mod download && go vet ./... && "
           "mkdir -p bin && go build -o bin/ ./cmd/..."),
    "csharp": "dotnet build Course.sln -nologo -v q -clp:NoSummary",
    "rust": "cargo build -q --bins --message-format short",
    "java": ("mvn -q -B compile dependency:build-classpath -Dmdep.outputFile=cp.txt "
             "-Dmdep.includeScope=runtime"),
}
VOLUMES = {
    "js": [f"{VOL}npm:/root/.npm"], "ts": [f"{VOL}npm:/root/.npm"],
    "python": [f"{VOL}venv:/venv", f"{VOL}pip:/root/.cache/pip"],
    "go": [f"{VOL}gomod:/go/pkg/mod", f"{VOL}gocache:/root/.cache/go-build"],
    "csharp": [f"{VOL}nuget:/root/.nuget/packages"],
    "rust": [f"{VOL}cargo:/usr/local/cargo/registry"],
    "java": [f"{VOL}m2:/root/.m2"],
}

# The programs that run now, in this order (docs/COURSE.md "The programs").
PROGRAMS = ["servers", "echo", "al-test", "login", "connect", "first-kill",
            "farm", "supplies", "gear-up", "party-merchant"]

# Each program's name per language (docs/COURSE.md, the program table).
NAMES = {
    "servers": {"js": "servers", "python": "servers", "go": "servers", "csharp": "Servers",
                "rust": "servers", "java": "Servers"},
    "echo": {"js": "echo", "python": "echo", "go": "echo", "csharp": "Echo", "rust": "echo",
             "java": "Echo"},
    "al-test": {"js": "al-test", "python": "al_test", "go": "al-test", "csharp": "AlTest",
                "rust": "al-test", "java": "AlTest"},
    "login": {"js": "login", "python": "login", "go": "login", "csharp": "Login",
              "rust": "login", "java": "Login"},
    "connect": {"js": "connect", "python": "connect", "go": "connect", "csharp": "Connect",
                "rust": "connect", "java": "Connect"},
    "first-kill": {"js": "first-kill", "python": "first_kill", "go": "first-kill",
                   "csharp": "FirstKill", "rust": "first-kill", "java": "FirstKill"},
    "farm": {"js": "farm", "python": "farm", "go": "farm", "csharp": "Farm", "rust": "farm",
             "java": "Farm"},
    "supplies": {"js": "supplies", "python": "supplies", "go": "supplies", "csharp": "Supplies",
                 "rust": "supplies", "java": "Supplies"},
    "gear-up": {"js": "gear-up", "python": "gear_up", "go": "gear-up", "csharp": "GearUp",
                "rust": "gear-up", "java": "GearUp"},
    "party-merchant": {"js": "party-merchant", "python": "party_merchant", "go": "party-merchant",
                       "csharp": "PartyMerchant", "rust": "party-merchant",
                       "java": "PartyMerchant"},
}

# Command-line arguments per program (Part 3: the long-running bots stop after a time or a count).
ARGS = {"farm": "25", "supplies": "1", "party-merchant": "1"}

# Test controls to POST after the reset and before the program (docs/COURSE.md, the test server).
# farm: the server drops Tester's socket 5 s after its first `start` (the reconnect rule), and
# sends it to jail 10 s after that first `start` (the `leave` code).
SETUP = {
    "farm": ["/test/drop?character=Tester&after_start_ms=5000",
             "/test/jail?character=Tester&after_start_ms=10000"],
}


def run_cmd(lang, program):
    """The shell command that runs one program (after the build), in /w."""
    n = NAMES[program]["js" if lang == "ts" else lang]
    return {
        "js": f"node {n}.js", "ts": f"node {n}.ts", "python": f"/venv/bin/python {n}.py",
        "go": f"bin/{n}", "csharp": f"dotnet {n}/bin/Debug/net8.0/{n}.dll",
        "rust": f"target/debug/{n}", "java": f'java -cp "target/classes:$(cat cp.txt)" {n}',
    }[lang] + (f" {ARGS[program]}" if program in ARGS else "")


# The test account (docs/COURSE.md "The local test server").
AUTH = "US_tester-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
BASE_ENV = {
    "AL_BASE_URL": f"http://{HOST}:{PORT}",
    "AL_AUTH": AUTH, "AL_SERVER": "EUI", "AL_CHARACTER": "Tester",
    "AL_WS_URL": f"ws://{HOST}:{PORT}/ws1/?EIO=4&transport=websocket",
    "AL_ECHO_URL": f"ws://{HOST}:{PORT}/echo",
    "AL_RECONNECT_MS": "2000",
}
# Per program: changes to BASE_ENV (None removes a variable).
ENV = {
    # login checks the password path: no AL_AUTH, so it must log in and print the save lines.
    "login": {"AL_AUTH": None, "AL_EMAIL": "tester@example.com", "AL_PASSWORD": "test-password"},
}
TIMEOUT = {"al-test": 30, "first-kill": 120, "farm": 90, "supplies": 120, "gear-up": 150,
           "party-merchant": 150}  # seconds; others 30

# The lines each program must print, in this order (other lines may come between).
N = r"-?\d+"
WS = rf"ws://{HOST}:{PORT}"
EXPECT = {
    "servers": [
        r"^status: 200 application/json; charset=utf-8$",
        rf"^EU I: {WS}/ws1/\?EIO=4&transport=websocket&map_protocol=1&no_graphics=1$",
        rf"^US I: {WS}/ws2/\?EIO=4&transport=websocket&map_protocol=1&no_graphics=1$",
    ],
    "echo": [r"^connected$", r"^received: hello$", r"^closed$"],
    "al-test": [
        rf"^connected to {WS}/ws1/\?EIO=4&transport=websocket$",
        r"^welcome: EU I, version \d+$",
        r"^entities: \d+ monster\(s\)$",
        rf"^start: Tester on main at {N},{N}$",
        r"^ping_ack after 3 s idle: 42$",
        r"^OK$",
        r"^disconnect: .+",
    ],
    "login": [
        r"^Logged in with the password\. Save this value, and use it from now on:$",
        rf"^  export AL_AUTH='{re.escape(AUTH)}'$",
        rf"^  PowerShell: \$env:AL_AUTH = '{re.escape(AUTH)}'$",
        r"^user id: US_tester$",
        r"^servers \(AL_SERVER, players, address, path\):$",
        rf"^  EUI\s+\d+\s+{HOST}:{PORT}\s+/ws1/$",
        rf"^  USI\s+\d+\s+{HOST}:{PORT}\s+/ws2/$",
        r"^characters \(AL_CHARACTER, class, level, id, status\):$",
        r"^  Tester\s+warrior\s+\d+\s+CH_tester\s+offline$",
    ],
    "connect": [
        r"^welcome: EU I, version \d+$",
        rf"^in game as Tester \(warrior, level \d+\) on main at {N},{N}$",
        r"^OK$",
    ],
    "first-kill": [
        rf"^in game as Tester \(warrior, level \d+\) on main at {N},{N}$",
        r"^heal hp: \d+/\d+$",
        rf"^target: goo \S+ at {N},{N}$",
        r"^killed goo \S+$",
        r"^chest \S+: \+\d+ gold, \d+ item\(s\)$",
        r"^xp: \d+/\d+, level \d+$",
        r"^OK$",
    ],
    "farm": [
        rf"^in game as Tester \(warrior, level \d+\) on main at {N},{N}$",
        r"^disconnected: .+; reconnect in 2 s$",
        rf"^in game as Tester \(warrior, level \d+\) on main at {N},{N}$",
        r"^in jail: leave$",
        rf"^left jail: on main at {N},{N}$",
        r"^farmed \d+ s: [1-9]\d* kill\(s\), level \d+, \d+ gold$",
        r"^OK$",
    ],
    "supplies": [
        rf"^in game as Tester \(warrior, level \d+\) on main at {N},{N}$",
        r"^killed goo \S+$",
        r"^chest \S+: \+\d+ gold, 5 item\(s\)$",
        r"^equip hpbelt: belt$",
        r"^supplies low: \d+ hpot0, \d+ mpot0, \d+ free slot\(s\)$",
        rf"^walk to fancypots at {N},{N}$",
        r"^sell gem0: \+\d+ gold$",
        r"^buy hpot0 x\d+: \d+ gold$",
        r"^buy coat x1: 6000 gold$",
        r"^equip coat: chest$",
        r"^bag: 50 hpot0, 50 mpot0, \d+ free slot\(s\), \d+ gold$",
        r"^OK$",
    ],
    "gear-up": [
        rf"^in game as Tester \(warrior, level \d+\) on main at {N},{N}$",
        r"^killed goo \S+$",
        r"^buy coat x1: 6000 gold$",
        rf"^walk to scrolls and newupgrade at {N},{N}$",
        r"^buy scroll0 x1: 1000 gold$",
        r"^upgrade coat \+0 -> \+1: (success|fail) \(chance \d\.\d\d\)$",
        r"^buy cscroll0 x1: 6400 gold$",
        r"^compound ringsj \+0 x3 -> \+1: (success|fail) \(chance \d\.\d\d\)$",
        r"^gear: chest .+, ring1 .+, ring2 .+, belt .+$",
        r"^OK$",
    ],
    "party-merchant": [
        r"^team: Tester, Healer, Archer; merchant: Merchy$",
        rf"^in game as Tester \(warrior, level \d+\) on main at {N},{N}$",
        rf"^in game as Healer \(priest, level \d+\) on main at {N},{N}$",
        rf"^in game as Archer \(ranger, level \d+\) on main at {N},{N}$",
        rf"^in game as Merchy \(merchant, level \d+\) on main at {N},{N}$",
        r"^party: Tester, Healer, Archer, Merchy$",
        rf"^Merchy: walk to \w+ at {N},{N}$",
        r"^\w+: gave [1-9]\d* item\(s\) and \d+ gold to Merchy$",
        rf"^Merchy: walk to fancypots at {N},{N}$",
        r"^Merchy: sold \d+ item\(s\): \+\d+ gold$",
        r"^Merchy: in the bank: deposited \d+ gold$",
        rf"^Merchy: back on main at {N},{N}$",
        r"^OK$",
    ],
}


# ---------------------------------------------------------------------------------------------

def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def is_output(rel):
    """Build output or a cache (KEEP): never copied, never deleted. Under src/ nothing is
    output: Rust keeps its programs in src/bin/."""
    return rel.parts[0] != "src" and any(p in KEEP for p in rel.parts)


def sync(src, dst):
    """Copies the files of `src` to `dst` and deletes files in `dst` that `src` no longer has,
    except build output and caches (KEEP)."""
    dst.mkdir(parents=True, exist_ok=True)
    want = set()
    for f in src.rglob("*"):
        rel = f.relative_to(src)
        if is_output(rel) or not f.is_file():
            continue
        want.add(rel)
        out = dst / rel
        if not out.exists() or out.read_bytes() != f.read_bytes():
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, out)
    for f in sorted(dst.rglob("*"), reverse=True):
        rel = f.relative_to(dst)
        if is_output(rel):
            continue
        if f.is_file() and rel not in want:
            f.unlink()
        elif f.is_dir() and not any(f.iterdir()):
            f.rmdir()


def docker_run(lang, script, env=None, timeout=3600):
    """Runs `script` (bash) in the language's image, with the copied project at /w, on the
    test network. Returns (output, exit status). Files the container makes go back to us."""
    owner = f"{os.getuid()}:{os.getgid()}"
    args = ["docker", "run", "--rm", "--network", NETWORK, "-v", f"{BUILD / lang}:/w", "-w", "/w"]
    for v in VOLUMES[lang]:
        args += ["-v", v]
    for k, v in (env or {}).items():
        args += ["-e", f"{k}={v}"]
    wrapped = f"{script}\nrc=$?; chown -R {owner} /w 2>/dev/null; exit $rc"
    try:
        p = sh(args + [IMAGES[lang], "bash", "-c", wrapped], timeout=timeout)
        return p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        return f"check-course: timed out after {timeout} s", -1


def start_server():
    """Starts the test server; returns its HTTP base URL as seen from the host."""
    sh(["docker", "rm", "-f", SERVER])
    srv = BUILD / f"test-server-{RUN_ID}"
    sync(COURSE / "test-server", srv)
    owner = f"{os.getuid()}:{os.getgid()}"
    # npm ci when there is a lock file (the exact pinned packages), then the server itself.
    script = ("(npm ci --no-audit --no-fund --silent || npm install --no-audit --no-fund --silent)"
              f" && chown -R {owner} /w && exec node server.js")
    p = sh(["docker", "run", "-d", "--name", SERVER, "--network", NETWORK,
            "--network-alias", HOST, "-p", f"127.0.0.1::{PORT}",
            "-v", f"{srv}:/w", "-w", "/w",
            "-v", f"{G_FILE}:/g/G.json:ro", "-v", f"{VOL}npm:/root/.npm",
            "-e", "TEST_G_FILE=/g/G.json", "-e", "TEST_QUIET=1",
            "node:22", "bash", "-c", script])
    if p.returncode != 0:
        sys.exit(f"check-course: could not start the test server:\n{p.stderr}")
    port = sh(["docker", "port", SERVER, str(PORT)]).stdout.strip().splitlines()[0].rsplit(":", 1)[1]
    base = f"http://127.0.0.1:{port}"
    for _ in range(180):  # npm ci on the first run takes a while
        try:
            urllib.request.urlopen(f"{base}/api/get_servers", timeout=2).read()
            return base
        except Exception:
            if sh(["docker", "inspect", "-f", "{{.State.Running}}", SERVER]).stdout.strip() != "true":
                break
            time.sleep(1)
    logs = sh(["docker", "logs", SERVER])
    sys.exit(f"check-course: the test server did not start:\n{logs.stdout}{logs.stderr}")


def stop_server():
    sh(["docker", "rm", "-f", SERVER])
    shutil.rmtree(BUILD / f"test-server-{RUN_ID}", ignore_errors=True)


def post(base, path):
    req = urllib.request.Request(f"{base}{path}", data=b"", method="POST")
    urllib.request.urlopen(req, timeout=10).read()


def check_output(program, out):
    """Returns the first expected pattern that is missing (in order), or None."""
    lines = out.splitlines()
    i = 0
    for pat in EXPECT[program]:
        while i < len(lines) and not re.search(pat, lines[i]):
            i += 1
        if i == len(lines):
            return pat
        i += 1
    return None


def post_cmd(lang, path):
    """A shell command that POSTs to the test server from inside the language's image."""
    url = f"http://{HOST}:{PORT}{path}"
    if IMAGES[lang] == "node:22":
        return f"node -e \"fetch('{url}',{{method:'POST'}})\" 2>/dev/null"
    return (f"(curl -s -X POST '{url}' || wget -q -O- --post-data= '{url}' || "
            f"python3 -c \"import urllib.request as u;u.urlopen(u.Request('{url}',data=b''))\")"
            " >/dev/null 2>&1")


def setup(lang, program):
    """The SETUP posts of a program, each followed by '; '."""
    return "".join(f"{post_cmd(lang, path)}; " for path in SETUP.get(program, []))


def run_programs(lang, programs, base):
    """Runs each program in one container (the build is already there). Returns
    {program: (ok, detail, output)}."""
    parts = []
    for prog in programs:
        env = dict(BASE_ENV)
        env.update(ENV.get(prog, {}))
        exports = " ".join(f"{k}='{v}'" for k, v in env.items() if v is not None)
        unsets = " ".join(k for k, v in env.items() if v is None)
        t = TIMEOUT.get(prog, 30)
        parts.append(
            f"echo '@@@ start {prog}'; "
            f"(unset AL_EMAIL AL_PASSWORD {unsets}; export {exports}; "
            f"timeout {t} {run_cmd(lang, prog)}) 2>&1; echo \"@@@ end {prog} rc=$?\"")
    # One reset per program, done from inside the network so the order is exact.
    reset = (f"node -e \"fetch('http://{HOST}:{PORT}/test/reset',{{method:'POST'}})\" 2>/dev/null"
             if IMAGES[lang] == "node:22" else
             f"(curl -s -X POST http://{HOST}:{PORT}/test/reset || "
             f"wget -q -O- --post-data= http://{HOST}:{PORT}/test/reset || "
             f"python3 -c \"import urllib.request as u;u.urlopen(u.Request('http://{HOST}:{PORT}/test/reset',data=b''))\")"
             " >/dev/null 2>&1")
    script = "\n".join(f"{reset}; {setup(lang, prog)}{p}" for prog, p in zip(programs, parts))
    post(base, "/test/reset")
    out, _ = docker_run(lang, script, timeout=60 + sum(TIMEOUT.get(p, 30) for p in programs))
    results = {}
    for prog in programs:
        m = re.search(rf"@@@ start {re.escape(prog)}\n(.*?)@@@ end {re.escape(prog)} rc=(-?\d+)",
                      out, re.S)
        if not m:
            results[prog] = (False, "did not run", out[-2000:])
            continue
        text, rc = m.group(1), int(m.group(2))
        missing = check_output(prog, text)
        if rc != 0:
            results[prog] = (False, f"exit status {rc}" + (" (timeout)" if rc == 124 else ""), text)
        elif missing:
            results[prog] = (False, f"missing line /{missing}/", text)
        else:
            results[prog] = (True, "", text)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", action="append", choices=LANGS, help="only this language")
    ap.add_argument("--program", action="append", choices=PROGRAMS, help="only this program")
    ap.add_argument("--build-only", action="store_true", help="compile, run nothing")
    ap.add_argument("-v", "--verbose", action="store_true", help="print all output")
    a = ap.parse_args()
    langs = a.lang or LANGS
    programs = a.program or PROGRAMS

    if sh(["docker", "info"]).returncode != 0:
        sys.exit("check-course: docker is not running")
    if not G_FILE.is_file():
        sys.exit(f"check-course: {G_FILE.relative_to(ROOT)} is missing "
                 "(bash scripts/fetch-source.sh)")
    for lang in langs:
        if not (COURSE / lang).is_dir():
            sys.exit(f"check-course: course/{lang} is missing")
        sync(COURSE / lang, BUILD / lang)

    base = None
    failed = False
    p = sh(["docker", "network", "create", NETWORK])
    if p.returncode != 0:
        sys.exit(f"check-course: docker network create failed:\n{p.stderr}")
    try:
        if not a.build_only:
            print("starting the test server ...", flush=True)
            base = start_server()

        def build(lang):
            t = time.time()
            out, rc = docker_run(lang, BUILD_CMD[lang])
            return lang, out, rc, time.time() - t

        print(f"building {', '.join(langs)} ...", flush=True)
        built = {}
        with ThreadPoolExecutor(len(langs)) as pool:
            for lang, out, rc, secs in pool.map(build, langs):
                built[lang] = (out, rc, secs)
                status = "ok" if rc == 0 else f"FAILED (exit {rc})"
                print(f"  {lang:<7} build {status} in {secs:.0f} s", flush=True)
                if rc != 0 or a.verbose:
                    print("    " + "\n    ".join(out.strip().splitlines()[-40:]))

        results = {}
        if not a.build_only:
            for lang in langs:
                if built[lang][1] != 0:
                    continue
                print(f"running {lang} ...", flush=True)
                results[lang] = run_programs(lang, programs, base)
                for prog, (ok, detail, text) in results[lang].items():
                    if not ok or a.verbose:
                        print(f"  --- {lang} {prog}: {'ok' if ok else detail}")
                        print("    " + "\n    ".join(text.strip().splitlines()[-40:]))
    finally:
        stop_server()
        sh(["docker", "network", "rm", NETWORK])

    # The table: one row per language.
    cols = ["build"] + ([] if a.build_only else programs)
    print()
    print(f"{'':<8}" + "".join(f"{c:>12}" for c in cols))
    for lang in langs:
        row = ["ok" if built[lang][1] == 0 else "FAIL"]
        if built[lang][1] != 0:
            failed = True
        for prog in ([] if a.build_only else programs):
            r = results.get(lang, {}).get(prog)
            row.append("-" if r is None else ("ok" if r[0] else "FAIL"))
            if r is not None and not r[0]:
                failed = True
        print(f"{lang:<8}" + "".join(f"{c:>12}" for c in row))
    print("\nall passed" if not failed else "\nsome checks failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
