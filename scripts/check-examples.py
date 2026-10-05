#!/usr/bin/env python3
"""Compile-checks every reference example against the real AlSocket, in all seven languages.

The reference entries (content/send-*.md, content/receive.md) each end with an `**Example:**`
(or `#### Example`) section: one tab group of seven fenced blocks (js ts python go csharp rust java), see
docs/EXAMPLES.md. Those snippets assume a connected `sock`, the AlSocket that the Build a bot page
builds in its chapter "AlSocket" and keeps in course/<lang> (docs/COURSE.md). This script makes sure each
snippet compiles against *that* AlSocket, not a hand-made stub:

  1. It takes the AlSocket file of each language from the course library (AL_SOURCE below;
     learn-1.md shows the same files through includes). Change AlSocket there and the next run
     checks against the change.
  2. It takes every example tab group out of the reference files, keyed by the entry id the
     page uses (`### \\`buy\\`` in send-2.md -> send-buy; in receive.md -> recv-<name>).
  3. It wraps each snippet in a fixed per-language preamble (imports, a function that takes
     `sock`), one file per example, and writes one project per language under `.examples/`
     (git-ignored; the compilers' caches stay there and in named Docker volumes, so a rerun
     only recompiles).
  4. It compiles each project in Docker, in the images of docs/EXAMPLES.md, all languages at
     the same time, and maps each compiler error back to `content/<file>:<line> <entry> <lang>`.
  5. It also runs a few text checks ("lint") for known misuses of the AlSocket surface that
     compile but are wrong (see LINTS).

Usage (python3 and docker only; run from anywhere):

  python3 scripts/check-examples.py                        # everything
  python3 scripts/check-examples.py --lang go              # one language (repeatable)
  python3 scripts/check-examples.py --entry send-buy       # one entry (repeatable)
  python3 scripts/check-examples.py --file content/send-2.md
  python3 scripts/check-examples.py --generate-only        # write .examples/, compile nothing
  python3 scripts/check-examples.py -v                     # also print raw compiler output

Exit status: 0 all good, 1 any error (compile, lint, or a malformed example group).

The first run downloads images and packages (a few minutes, mostly Rust); later runs take
about a minute. The rules a snippet must follow to be checkable are in docs/EXAMPLES.md,
"Reference examples".
"""

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
BUILD = ROOT / ".examples"  # git-ignored; one sub-folder per language

# The reference files that hold `**Example:**` groups, and the id prefix of their entries
# (the same ids build.py gives them, so an error points at the page's #link).
REFERENCE = {
    "send-1.md": "send", "send-2.md": "send", "send-3.md": "send", "send-4.md": "send",
    "send-observer.md": "send", "receive.md": "recv",
}

# The seven fence tags, in the order docs/EXAMPLES.md requires.
LANGS = ["js", "ts", "python", "go", "csharp", "rust", "java"]

# Pinned tool and package versions. Jackson 2.18.2 and coder/websocket v1.8.13 are the ones
# learn-1.md ("Before you start") tells the reader to install; the rest are not pinned there,
# so they are hard-coded here to keep the check reproducible. Change a pin and the next run
# reinstalls (each language's setup compares a marker file).
PINS = {
    "typescript": "5.6.3",
    "types_node": "22.10.0",   # 22.x: the reader's Node; declares the global WebSocket
    "mypy": "1.13.0",
    "websockets": "13.1",      # learn-1: websockets 13+
    "coder_websocket": "v1.8.13",  # learn-1; v1.8.14+ needs Go 1.23
    "jackson": "2.18.2",       # learn-1
    "tokio": "1.40",
    "tokio_tungstenite": "0.24",
    "futures_util": "0.3",
    "serde": "1.0",
    "serde_json": "1.0",
}

# Docker images: the ones docs/EXAMPLES.md and learn-1.md name. JS and TS share node:22.
IMAGES = {
    "js": "node:22", "ts": "node:22", "python": "python:3.12-slim", "go": "golang:1.22",
    "csharp": "mcr.microsoft.com/dotnet/sdk:8.0", "rust": "rust:1",
    "java": "maven:3-eclipse-temurin-21",
}

# Named volumes for package caches, so a rerun downloads nothing. Prefixed so they're easy to
# find and remove (`docker volume ls | grep alapi-examples`).
VOL = "alapi-examples-"


# ---------------------------------------------------------------------------------------------
# Reading the Markdown
# ---------------------------------------------------------------------------------------------

def load_slug():
    """build.py's slug(), without running build.py (importing it builds every entry and exits
    on any content error). Parsed out of its source, so the ids can't drift from the page's."""
    tree = ast.parse((ROOT / "build.py").read_text())
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "slug"), None)
    if fn is None:
        sys.exit("check-examples: build.py has no slug() function")
    scope = {"re": re}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "build.py", "exec"), scope)
    return scope["slug"]


slug = load_slug()


def fenced_blocks(lines, start=0, end=None):
    """Yields (tag, first_body_line_index, body_lines) for each ``` fence in lines[start:end].
    Indices are 0-based into `lines`."""
    end = len(lines) if end is None else end
    i = start
    while i < end:
        m = re.match(r"^```(\S*)\s*$", lines[i])
        if m:
            j = i + 1
            while j < end and not lines[j].startswith("```"):
                j += 1
            yield m.group(1), i + 1, lines[i + 1:j]
            i = j + 1
        else:
            i += 1


# Where each language's AlSocket lives: the course library (docs/COURSE.md). The Build a bot page shows
# these files through includes, so the course code is the single source of truth.
AL_SOURCE = {
    "js": "course/js/albot/alsocket.js",
    "ts": "course/ts/albot/alsocket.ts",
    "python": "course/python/albot/alsocket.py",
    "go": "course/go/alsocket/alsocket.go",
    "csharp": "course/csharp/Albot/AlSocket.cs",
    "rust": "course/rust/src/alsocket.rs",
    "java": "course/java/src/main/java/albot/AlSocket.java",
}


def extract_alsocket():
    """Returns {lang: source} of the course's AlSocket files. Fails loudly if one is missing."""
    found = {}
    for lang, rel in AL_SOURCE.items():
        f = ROOT / rel
        if not f.is_file():
            sys.exit(f"check-examples: no AlSocket for {lang}: {rel} is missing")
        found[lang] = f.read_text()
    return found


class Snippet:
    """One language's block of one entry's example."""

    def __init__(self, entry, lang, body, first_line):
        self.entry = entry          # Entry
        self.lang = lang
        self.lines = body           # the code, as a list of lines
        self.first_line = first_line  # 1-based line in the .md of self.lines[0]


class Entry:
    def __init__(self, file, id_, line):
        self.file = file            # "send-2.md"
        self.id = id_               # "send-buy"
        self.line = line            # 1-based line of the `### ` heading
        self.snippets = {}          # lang -> Snippet
        self.problems = []          # structural problems of the tab group


def extract_examples(files):
    """Returns [Entry] for every entry of `files` that has an `**Example:**` section. Entries
    without one are counted in `skipped` (receive.md's prose-only sections, for example)."""
    entries, skipped = [], []
    for name in files:
        lines = (CONTENT / name).read_text().splitlines()
        prefix = REFERENCE[name]
        i, current, in_example = 0, None, False
        while i < len(lines):
            line = lines[i]
            if line.startswith("```"):
                # A fence: skip to its end so a `###` inside code isn't read as a heading.
                j = i + 1
                while j < len(lines) and not lines[j].startswith("```"):
                    j += 1
                if in_example and current:
                    tag = line[3:].strip()
                    if tag in current.snippets:
                        current.problems.append(f"two `{tag}` blocks")
                    current.snippets.setdefault(tag, Snippet(current, tag, lines[i + 1:j], i + 2))
                    current.order.append(tag)
                i = j + 1
                continue
            if line.startswith("### ") or line.startswith("## "):
                if current and not current.has_example:
                    skipped.append(current.id)
                current, in_example = None, False
                if line.startswith("### "):
                    heading = line[4:].strip()
                    m = re.match(r"`([^`]+)`", heading)  # build.py's code_name()
                    current = Entry(name, f"{prefix}-{slug(m.group(1) if m else heading)}", i + 1)
                    current.has_example, current.order = False, []
                    entries.append(current)
            elif current and line.strip() in ("**Example:**", "#### Example"):
                # Schema-rendered entries use a `####` heading instead of a bold label.
                in_example, current.has_example = True, True
            elif current and in_example and line.startswith(("**", "#### ")):
                in_example = False  # **Source:** (or any next section) ends the example
            i += 1
        if current and not current.has_example:
            skipped.append(current.id)
    entries = [e for e in entries if e.has_example]
    for e in entries:
        if e.order != LANGS:
            e.problems.append(f"tab group is {' '.join(e.order) or 'empty'}; "
                              f"expected {' '.join(LANGS)}")
    return entries, skipped


# ---------------------------------------------------------------------------------------------
# Wrapping snippets into compilable files
# ---------------------------------------------------------------------------------------------

class Unit:
    """A generated source file, with a map from its lines back to the Markdown."""

    def __init__(self, snippet, path):
        self.snippet = snippet
        self.path = path            # relative to the language's project folder
        self.out = []               # generated lines
        self.src = []               # parallel: 1-based .md line, or None for preamble lines

    def add(self, text, md_line=None):
        for t in text.split("\n"):
            self.out.append(t)
            self.src.append(md_line)

    def add_snippet(self, indices, indent=""):
        """Adds the snippet lines at `indices` (0-based into the snippet), keeping their .md
        line numbers."""
        sn = self.snippet
        for k in indices:
            self.out.append((indent + sn.lines[k]) if sn.lines[k].strip() else "")
            self.src.append(sn.first_line + k)

    def md_line(self, line):
        """The .md line for generated line `line` (1-based); preamble lines map to the nearest
        snippet line before them, else to the first."""
        k = min(max(line, 1), len(self.src)) - 1
        while k >= 0 and self.src[k] is None:
            k -= 1
        return self.src[k] if k >= 0 else self.snippet.first_line

    def text(self):
        return "\n".join(self.out) + "\n"


def split_toplevel(lines, starts):
    """Splits a snippet into (hoisted, rest): line-index lists. A hoisted declaration starts at
    column 0 with a line matching `starts`, and runs until its braces and parentheses balance
    (a one-line declaration ends on its own line). Used for Go and C#, where types (and Go
    funcs) can't sit inside a function body the way the snippet shows them."""
    hoisted, rest, i = [], [], 0
    while i < len(lines):
        if re.match(starts, lines[i]):
            depth, j = 0, i
            while j < len(lines):
                code = re.sub(r'"(\\.|[^"\\])*"|//.*', "", lines[j])  # ignore strings, comments
                depth += code.count("{") + code.count("(") - code.count("}") - code.count(")")
                if depth <= 0 and (j > i or not code.rstrip().endswith((",", "=>"))):
                    break
                j += 1
            hoisted.extend(range(i, min(j, len(lines) - 1) + 1))
            i = j + 1
        else:
            rest.append(i)
            i += 1
    return hoisted, rest


def ident(entry_id):
    """An identifier made from an entry id: send-o-home -> send_o_home."""
    return re.sub(r"[^A-Za-z0-9]", "_", entry_id)


def wrap_js(sn):
    u = Unit(sn, f"ex/{sn.entry.id}.js")
    u.add('import { AlSocket } from "../alsocket.js";\n\n/** @param {AlSocket} sock */\n'
          "export async function example(sock) {")
    u.add_snippet(range(len(sn.lines)), "  ")
    u.add("}")
    return u


def wrap_ts(sn):
    # TS allows interfaces and types inside a function, so the snippet goes in as it is.
    u = Unit(sn, f"ex/{sn.entry.id}.ts")
    u.add('import { AlSocket } from "../alsocket.ts";\n\n'
          "export async function example(sock: AlSocket) {")
    u.add_snippet(range(len(sn.lines)), "  ")
    u.add("}")
    return u


def wrap_python(sn):
    # Classes (TypedDict) and functions are fine inside a function, so no hoisting.
    u = Unit(sn, f"ex/{ident(sn.entry.id)}.py")
    u.add("import asyncio\nimport json\nimport os\nimport time\n"
          "from typing import Any, Literal, NotRequired, TypedDict\n\n"
          "from alsocket import AlSocket\n\n\n"
          "async def example(sock: AlSocket) -> None:")
    u.add_snippet(range(len(sn.lines)), "    ")
    u.add("    pass")  # an all-comment snippet still makes a valid body
    return u


# Go: packages a snippet may use without importing (the preamble imports them and marks each
# used, so an unused one isn't an error).
GO_IMPORTS = {"context": "context.Background", "encoding/json": "json.Marshal",
              "errors": "errors.New", "fmt": "fmt.Sprint", "log": "log.Println",
              "os": "os.Getenv", "strings": "strings.Contains", "time": "time.Now",
              "strconv": "strconv.Itoa", "sync": "new(sync.Mutex)", "math": "math.Abs",
              "sort": "sort.Ints", "slices": "slices.Contains[[]int, int]"}


def wrap_go(sn):
    # Go allows local types but not local funcs or methods; hoist both (and types, so a hoisted
    # func can use them) to package level. Each example is its own package, so names can't clash.
    d = ident(sn.entry.id)
    u = Unit(sn, f"ex/{d}/ex_{d}.go")  # not <d>.go: recv_test.go would be a test file
    hoisted, rest = split_toplevel(sn.lines, r"^(type|func) ")
    imports = "\n".join(f'\t"{p}"' for p in GO_IMPORTS)
    used = "\n".join(f"\t_ = {v}" for v in GO_IMPORTS.values())
    u.add(f"package {d}\n\nimport (\n{imports}\n\n\t\"albot/alsocket\"\n)\n\nvar (\n{used}\n)\n")
    u.add_snippet(hoisted)
    # ctx: the snippets may assume "a context with a deadline", as docs/EXAMPLES.md says.
    # A named result, so a snippet may end early with a bare `return` or with `return err`.
    u.add("\nfunc Run(ctx context.Context, sock *alsocket.Socket) (err error) {")
    u.add_snippet(rest, "\t")
    # A final top-level `return ...` makes another return unreachable (go vet), so add
    # `return nil` only when the snippet doesn't end with one.
    code = [sn.lines[k] for k in rest if sn.lines[k].strip()
            and not sn.lines[k].strip().startswith("//")]
    if not (code and code[-1].startswith("return")):
        u.add("\treturn nil")
    u.add("}")
    return u


CS_TYPE = (r"^(?:(?:public|internal|private|sealed|readonly|static|abstract|partial|file)\s+)*"
           r"(?:record|class|struct|enum|interface)\b")


def wrap_csharp(sn):
    # C# has no local types: hoist records/classes/structs/enums into the example's namespace.
    # Local functions (`static string Str(...) => ...;`) are fine inside the method.
    u = Unit(sn, f"Ex/{ident(sn.entry.id)}.cs")
    hoisted, rest = split_toplevel(sn.lines, CS_TYPE)
    u.add(f"namespace Ex_{ident(sn.entry.id)};\n")
    u.add_snippet(hoisted)
    u.add("\nstatic class Example\n{\n    public static async Task Run(AlSocket sock)\n    {")
    u.add_snippet(rest, "        ")
    u.add("    }\n}")
    return u


def wrap_rust(sn):
    # Rust allows items (structs, fns, impls) inside a function, so no hoisting.
    u = Unit(sn, f"src/ex_{ident(sn.entry.id)}.rs")
    u.add("use super::*;\n\npub async fn run(sock: &AlSocket) -> Result<()> {")
    u.add_snippet(range(len(sn.lines)), "    ")
    u.add("    Ok(())\n}")
    return u


# A Java method declared at column 0 (`static JsonNode ask(AlSocket sock, ...) {`). It needs a
# modifier, so a local record (`record Reply(...)`) or a statement never matches.
JAVA_METHOD = r"^(?:(?:public|private|protected|static|final)\s+)+[\w<>\[\],.? ]+\s+\w+\s*\("


def wrap_java(sn):
    # Java 16+ allows local records, interfaces and enums, but no local methods: hoist methods
    # into the example's class, the statements go into run().
    cls = f"Ex_{ident(sn.entry.id)}"
    u = Unit(sn, f"src/main/java/{cls}.java")
    hoisted, rest = split_toplevel(sn.lines, JAVA_METHOD)
    u.add("import albot.AlSocket;\nimport com.fasterxml.jackson.databind.*;\nimport com.fasterxml.jackson.databind.node.*;\n"
          "import java.time.Duration;\nimport java.util.*;\nimport java.util.concurrent.*;\n"
          "import java.util.function.*;\n\n"
          f"final class {cls} {{")
    u.add_snippet(hoisted, "    ")
    u.add("    static void run(AlSocket sock) throws Exception {")
    u.add_snippet(rest, "        ")
    u.add("    }\n}")
    return u


WRAP = {"js": wrap_js, "ts": wrap_ts, "python": wrap_python, "go": wrap_go,
        "csharp": wrap_csharp, "rust": wrap_rust, "java": wrap_java}


# ---------------------------------------------------------------------------------------------
# The projects: fixed files, AlSocket, and the compile command per language
# ---------------------------------------------------------------------------------------------

def tsconfig(js):
    # The tsconfig of learn-1 "Before you start", plus allowJs/checkJs for the JS tab. JS is
    # checked without `strict` (plain JS has no annotations, so implicit any is normal).
    strict = "false" if js else "true"
    extra = '"allowJs": true, "checkJs": true, ' if js else ""
    return ('{ "compilerOptions": { "target": "es2022", "module": "nodenext", '
            '"moduleResolution": "nodenext", "strict": %s, "noEmit": true, %s'
            '"allowImportingTsExtensions": true, "types": ["node"], "lib": ["es2022"], '
            '"skipLibCheck": true }, "include": ["alsocket.*", "ex"] }\n' % (strict, extra))


def node_setup(js):
    ext = "js" if js else "ts"
    files = {"package.json": '{ "private": true, "type": "module" }\n',
             "tsconfig.json": tsconfig(js)}
    pins = f"typescript@{PINS['typescript']} @types/node@{PINS['types_node']}"
    cmd = (f'if [ "$(cat node_modules/.pins 2>/dev/null)" != "{pins}" ]; then '
           f"npm i --no-audit --no-fund --silent --no-save {pins} >/dev/null && "
           f'echo "{pins}" > node_modules/.pins; fi; '
           "npx tsc -p . --pretty false")
    return files, f"alsocket.{ext}", cmd, [f"{VOL}npm:/root/.npm"]


def python_setup():
    pins = f"mypy=={PINS['mypy']} websockets=={PINS['websockets']}"
    # The venv lives in a volume: mypy and websockets install once. mypy checks the example
    # files; alsocket.py is only followed (its own internals aren't the subject).
    cmd = (f'if [ "$(cat /venv/.pins 2>/dev/null)" != "{pins}" ]; then '
           f"python -m venv /venv && /venv/bin/pip install -q {pins} && "
           f'echo "{pins}" > /venv/.pins; fi; '
           "MYPYPATH=/w /venv/bin/mypy --python-version 3.11 --check-untyped-defs "
           "--follow-imports=silent --no-error-summary --hide-error-context --no-color-output "
           "--cache-dir .mypy_cache ex")
    return {}, "alsocket.py", cmd, [f"{VOL}python:/venv"]


def go_setup():
    files = {"go.mod": f"module albot\n\ngo 1.22\n\nrequire github.com/coder/websocket "
                       f"{PINS['coder_websocket']}\n"}
    # GOTOOLCHAIN=local: never download a newer Go than the image's 1.22 (the reader's).
    cmd = ("export GOTOOLCHAIN=local GOFLAGS=-mod=mod; go mod download >/dev/null 2>&1; "
           "go vet ./... 2>&1; a=$?; go build ./... 2>&1; exit $((a | $?))")
    return files, "alsocket/alsocket.go", cmd, [f"{VOL}gomod:/go/pkg/mod",
                                                 f"{VOL}gocache:/root/.cache/go-build"]


def csharp_setup():
    files = {
        "Examples.csproj": (
            '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n'
            "    <TargetFramework>net8.0</TargetFramework>\n    <OutputType>Library</OutputType>\n"
            "    <ImplicitUsings>enable</ImplicitUsings>\n    <Nullable>enable</Nullable>\n"
            "    <NoWarn>CS1998;CS8321;CS0168;CS0219</NoWarn>\n"
            "  </PropertyGroup>\n</Project>\n"),
        # What a C# reader's Program.cs would have at the top; ImplicitUsings adds System,
        # System.Linq, System.Threading.Tasks, System.Collections.Generic, ...
        "Usings.cs": ("global using Albot;\nglobal using System.Net.WebSockets;\nglobal using System.Text.Json;\n"
                      "global using System.Text.Json.Nodes;\n"
                      "global using System.Text.Json.Serialization;\n"),
    }
    cmd = "dotnet build -nologo -v q -clp:NoSummary -p:GenerateFullPaths=true 2>&1"
    return files, "AlSocket.cs", cmd, [f"{VOL}nuget:/root/.nuget/packages"]


def rust_setup(units):
    mods = "\n".join(f"mod {Path(u.path).stem};" for u in units)
    files = {
        "Cargo.toml": (
            '[package]\nname = "al-examples"\nversion = "0.1.0"\nedition = "2021"\n\n'
            "[dependencies]\n"
            f'tokio = {{ version = "{PINS["tokio"]}", features = ["full"] }}\n'
            f'tokio-tungstenite = {{ version = "{PINS["tokio_tungstenite"]}", '
            'features = ["rustls-tls-webpki-roots"] }\n'
            f'futures-util = "{PINS["futures_util"]}"\n'
            f'serde = {{ version = "{PINS["serde"]}", features = ["derive"] }}\n'
            f'serde_json = "{PINS["serde_json"]}"\n'),
        # The names a snippet may use without importing: what a reader's main.rs would have.
        "src/main.rs": (
            "#![allow(unused, unreachable_code)]\nmod alsocket;\n\n"
            "use alsocket::{AlSocket, Result};\nuse serde::{Deserialize, Serialize};\n"
            "use serde_json::{json, Value};\nuse std::sync::{Arc, Mutex};\n"
            f"use std::time::Duration;\n\n{mods}\n\n#[tokio::main]\nasync fn main() {{}}\n"),
    }
    cmd = "cargo build -q --message-format short 2>&1"
    return files, "src/alsocket.rs", cmd, [f"{VOL}cargo:/usr/local/cargo/registry"]


def java_setup():
    files = {"pom.xml": f"""<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>albot</groupId>
  <artifactId>examples</artifactId>
  <version>1</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>{PINS['jackson']}</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <!-- javac stops at 100 errors by default; show them all. -->
          <compilerArgs><arg>-Xmaxerrs</arg><arg>100000</arg></compilerArgs>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
"""}
    cmd = "mvn -q -B compile 2>&1"
    return files, "src/main/java/albot/AlSocket.java", cmd, [f"{VOL}m2:/root/.m2"]


def setup(lang, units):
    return {"js": lambda: node_setup(True), "ts": lambda: node_setup(False),
            "python": python_setup, "go": go_setup, "csharp": csharp_setup,
            "rust": lambda: rust_setup(units), "java": java_setup}[lang]()


# Compiler output -> (file basename, line, message). One pattern covers all seven:
#   tsc:   ex/send-buy.ts(12,5): error TS2339: ...
#   mypy:  ex/send_buy.py:12: error: ...
#   go:    ex/send_buy/send_buy.go:12:5: ...
#   dotnet:/w/Ex/send_buy.cs(12,5): error CS0103: ... [/w/Examples.csproj]
#   rustc: src/ex_send_buy.rs:12:5: error[E0308]: ...
#   javac: [ERROR] /w/src/main/java/Ex_send_buy.java:[12,5] ...
# Which matching lines are errors (the rest are warnings and notes, which don't fail the check).
IS_ERROR = {
    "js": lambda l: "error TS" in l, "ts": lambda l: "error TS" in l,
    "python": lambda l: ": error:" in l, "go": lambda l: True,
    "csharp": lambda l: ": error " in l, "rust": lambda l: re.search(r": error(\[|:)", l),
    "java": lambda l: l.startswith("[ERROR]"),
}
ERR_RE = re.compile(r"([\w.\-]+\.(?:js|ts|py|go|cs|rs|java))(?::\[|\(|:)(\d+)[,:\]]?\d*[\])]?:?\s*(.*)")


def write_project(lang, units, alsocket):
    """Writes .examples/<lang>: fixed files, AlSocket, one file per example. Old example files
    are removed first (an entry that was deleted must not keep compiling); caches stay."""
    files, al_path, cmd, volumes = setup(lang, units)
    proj = BUILD / lang
    for sub in ("ex", "Ex", "src"):
        if (proj / sub).exists():
            shutil.rmtree(proj / sub)
    for rel, text in list(files.items()) + [(al_path, alsocket[lang])]:
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (proj / rel).write_text(text)
    if lang == "java":  # Maven's incremental build can keep classes of deleted files
        shutil.rmtree(proj / "target" / "classes", ignore_errors=True)
    for u in units:
        (proj / u.path).parent.mkdir(parents=True, exist_ok=True)
        (proj / u.path).write_text(u.text())
    return cmd, volumes


def run_docker(lang, cmd, volumes):
    """Runs `cmd` in the language's image with the project at /w. Returns (output, exit
    status, seconds).
    Files the container creates are handed back to the host user, so .examples/ stays ours."""
    proj = BUILD / lang
    owner = f"{os.getuid()}:{os.getgid()}"
    args = ["docker", "run", "--rm", "-v", f"{proj}:/w", "-w", "/w"]
    for v in volumes:
        args += ["-v", v]
    script = f"{cmd}; rc=$?; chown -R {owner} /w 2>/dev/null; exit $rc"
    start = time.time()
    try:
        p = subprocess.run(args + [IMAGES[lang], "bash", "-c", script], capture_output=True,
                           text=True, timeout=3600)
        out, rc = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        out, rc = "check-examples: docker run timed out after 3600 s", -1
    return out, rc, time.time() - start


# ---------------------------------------------------------------------------------------------
# Lint: compiles, but uses AlSocket wrongly
# ---------------------------------------------------------------------------------------------

# (language or "*", pattern, message). Checked line by line on each snippet.
LINTS = [
    ("python", r"create_task\(\s*sock\.wait_for|create_task\(\s*$",
     "wait_for registers when called; assign it and await it, no create_task"),
    ("python", r"asyncio\.sleep\(0\)", "no sleep(0) needed: wait_for registers when called"),
    ("rust", r"yield_now", "no yield_now needed: wait_for registers when called"),
    ("rust", r"join!", "no join! needed: call wait_for, then emit, then .await the wait"),
    ("rust", r"timeout\([^)]*sock\.wait_for|timeout\(\s*$",
     "use sock.wait_for_timeout(event, pred, duration) for a custom timeout"),
]
# The first wait must come before the first emit (register before you send). Receive entries
# are handlers and usually don't emit, so this only fires when both appear.
WAIT_RE = r"\b(waitFor|wait_for|wait_for_timeout|WaitForAsync|Expect)\b"
EMIT_RE = r"\b(emit|Emit|EmitAsync)\("


def lint(sn):
    found = []
    for k, line in enumerate(sn.lines):
        code = re.sub(r"(//|#).*$", "", line) if sn.lang == "python" else re.sub(r"//.*$", "", line)
        for lang, pat, msg in LINTS:
            if lang in (sn.lang, "*") and re.search(pat, code):
                found.append((sn.first_line + k, msg))
    waits = [k for k, l in enumerate(sn.lines) if re.search(WAIT_RE, l)]
    emits = [k for k, l in enumerate(sn.lines) if re.search(EMIT_RE, l)
             and not l.lstrip().startswith(("//", "#"))]
    if sn.lang == "go" and emits and any("WaitFor(" in l for l in sn.lines):
        found.append((sn.first_line + emits[0],
                      "use wait := sock.Expect(name, pred) before Emit, then wait(ctx)"))
    # Racing two waits needs tasks (asyncio.wait takes tasks, not coroutines), so create_task
    # is right there.
    if sn.lang == "python" and "asyncio.wait(" in "\n".join(sn.lines):
        found = [f for f in found if "create_task" not in f[1]]
    if waits and emits and emits[0] < waits[0]:
        found.append((sn.first_line + emits[0], "emit before the wait: register the wait first"))
    return found


# ---------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", action="append", choices=LANGS, help="only this language")
    ap.add_argument("--entry", action="append", help="only this entry id (send-buy, recv-player)")
    ap.add_argument("--file", action="append", help="only this file (content/send-2.md)")
    ap.add_argument("--generate-only", action="store_true", help="write .examples/, don't compile")
    ap.add_argument("-v", "--verbose", action="store_true", help="print raw compiler output")
    a = ap.parse_args()

    files = list(REFERENCE)
    if a.file:
        want = {Path(f).name for f in a.file}
        unknown = want - set(REFERENCE)
        if unknown:
            sys.exit(f"check-examples: not a reference file: {', '.join(sorted(unknown))}")
        files = [f for f in files if f in want]
    langs = a.lang or LANGS

    alsocket = extract_alsocket()
    entries, skipped = extract_examples(files)
    if a.entry:
        unknown = set(a.entry) - {e.id for e in entries}
        if unknown:
            sys.exit(f"check-examples: no example for {', '.join(sorted(unknown))}")
        entries = [e for e in entries if e.id in a.entry]

    errors = []  # (file, md_line, entry_id, lang, message)
    for e in entries:
        for p in e.problems:
            errors.append((e.file, e.line, e.id, "-", p))
        for lang in langs:
            if lang in e.snippets:
                for line, msg in lint(e.snippets[lang]):
                    errors.append((e.file, line, e.id, lang, "lint: " + msg))

    units = {lang: [WRAP[lang](e.snippets[lang]) for e in entries if lang in e.snippets]
             for lang in langs}
    jobs = {lang: write_project(lang, units[lang], alsocket) for lang in langs}
    print(f"{len(entries)} examples in {', '.join(files)}; "
          f"{len(skipped)} entries have no example section")
    if a.generate_only:
        print(f"wrote {BUILD.relative_to(ROOT)}/")
        return 0

    def check(lang):
        cmd, volumes = jobs[lang]
        print(f"  {lang}: compiling {len(units[lang])} examples in {IMAGES[lang]} ...", flush=True)
        return lang, *run_docker(lang, cmd, volumes)

    results = {}
    with ThreadPoolExecutor(len(langs)) as pool:
        for lang, out, rc, secs in pool.map(check, langs):
            results[lang] = (out, rc, secs)

    stats = {}
    for lang in langs:
        out, rc, secs = results[lang]
        by_name = {Path(u.path).name: u for u in units[lang]}
        seen, harness = set(), []
        for raw in out.splitlines():
            m = ERR_RE.search(raw)
            if not m or not IS_ERROR[lang](raw):
                continue
            name, line, msg = m.group(1), int(m.group(2)), m.group(3).strip()
            if lang == "csharp":
                msg = re.sub(r"\s*\[/w/[^\]]+\]$", "", msg)
            u = by_name.get(name)
            if u is None:
                harness.append(raw.strip())  # an error in AlSocket or a fixed file
                continue
            sn = u.snippet
            key = (name, line, msg)
            if key in seen:
                continue
            seen.add(key)
            errors.append((sn.entry.file, u.md_line(line), sn.entry.id, lang, msg))
        if a.verbose:
            print(f"----- {lang} raw output -----\n{out.rstrip()}\n")
        for h in harness:
            errors.append(("(harness)", 0, "-", lang, h))
        # A failed run with no error we could place (a crash, a network problem, Docker not
        # running) still fails, with the end of its output.
        if not seen and not harness and rc != 0:
            tail = "\n    ".join(out.strip().splitlines()[-15:])
            errors.append(("(harness)", 0, "-", lang, "run failed:\n    " + tail))
        stats[lang] = secs

    # Summary: per language, how many examples and how many fail.
    print()
    print(f"{'language':<9} {'examples':>8} {'failing':>8} {'errors':>7} {'seconds':>8}")
    for lang in langs:
        mine = [x for x in errors if x[3] == lang]
        failing = len({x[2] for x in mine if x[2] != "-"})
        bad = "!" if any(x[2] == "-" for x in mine) else ""
        print(f"{lang:<9} {len(units[lang]):>8} {failing:>8} {len(mine):>7}{bad:1} "
              f"{stats[lang]:>7.0f}")
    structural = [x for x in errors if x[3] == "-"]
    if structural:
        print(f"tab groups: {len(structural)} malformed")

    if not errors:
        print("\nall examples compile")
        return 0
    print()
    for file, line, entry, lang, msg in sorted(errors, key=lambda x: (x[0], x[1], x[3])):
        where = f"content/{file}:{line}" if line else file
        print(f"{where}  {entry}  [{lang}]  {msg}")
    print(f"\n{len(errors)} problems in {len({(x[2], x[3]) for x in errors})} "
          f"example blocks")
    return 1


if __name__ == "__main__":
    sys.exit(main())
