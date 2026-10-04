#!/usr/bin/env python3
"""Checks the typed definitions that scripts/gen-types.py makes from schema/: the strict schema
check, then each language's output compiled in Docker.

    python3 scripts/check-types.py               # all seven
    python3 scripts/check-types.py --lang ts     # one (ts python go csharp rust java)
    python3 scripts/check-types.py -v            # print the compiler output also on success
    python3 scripts/check-types.py --no-strict   # skip step 1 (while schema files are mid-edit)

Step 1 loads the schema with ALAPI_STRICT_TYPES=1 (no duplicate types, no unknown keys or
types, every example valid). Step 2 writes every language into .examples/types/<lang>/
(git-ignored) and compiles it in the images of docs/EXAMPLES.md, with the package caches of
scripts/check-examples.py (the `alapi-examples-*` volumes):

    ts      node:22                       tsc --strict
    python  python:3.12-slim              mypy --strict
    go      golang:1.22                   go vet, go build
    csharp  mcr.microsoft.com/dotnet/sdk  dotnet build (nullable enabled, warnings as errors off)
    rust    rust:1                        cargo build (serde, serde_json)
    java    maven:3-eclipse-temurin-21    mvn compile (jackson-databind)

The languages compile in parallel. Exit status 0 only when all pass.
"""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".examples" / "types"
VOL = "alapi-examples-"  # the cache volumes of scripts/check-examples.py

# Versions: the pins of scripts/check-examples.py, so one download serves both scripts.
TS, MYPY, JACKSON = "5.6.3", "1.13.0", "2.18.2"

PROJECTS = {
    "ts": {
        "image": "node:22",
        "files": {
            "package.json": '{ "private": true, "type": "module" }\n',
            "tsconfig.json": '{ "compilerOptions": { "target": "es2022", "module": "nodenext", '
                             '"moduleResolution": "nodenext", "strict": true, "noEmit": true, '
                             '"skipLibCheck": true, "lib": ["es2022"], "types": [] }, '
                             '"include": ["al-api.ts"] }\n',
        },
        "cmd": f'if [ "$(cat node_modules/.pins 2>/dev/null)" != "typescript@{TS}" ]; then '
               f"npm i --no-audit --no-fund --silent --no-save typescript@{TS} >/dev/null && "
               f'echo "typescript@{TS}" > node_modules/.pins; fi; npx tsc -p . --pretty false',
        "volumes": [f"{VOL}npm:/root/.npm"],
    },
    "python": {
        "image": "python:3.12-slim",
        "files": {},
        # The venv of check-examples has mypy already; typing_extensions comes with mypy.
        "cmd": f'if ! /venv/bin/mypy --version 2>/dev/null | grep -q "{MYPY}"; then '
               f"python -m venv /venv && /venv/bin/pip install -q mypy=={MYPY}; fi; "
               "/venv/bin/mypy --strict --python-version 3.11 --no-error-summary "
               "--cache-dir .mypy_cache al_api.py",
        "volumes": [f"{VOL}python:/venv"],
    },
    "go": {
        "image": "golang:1.22",
        "files": {"go.mod": "module alapi\n\ngo 1.22\n"},
        "cmd": "export GOTOOLCHAIN=local; go vet ./... 2>&1; a=$?; go build ./... 2>&1; exit $((a | $?))",
        "volumes": [f"{VOL}gocache:/root/.cache/go-build"],
    },
    "csharp": {
        "image": "mcr.microsoft.com/dotnet/sdk:8.0",
        "files": {
            "AlApi.csproj": '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n'
                            "    <TargetFramework>net8.0</TargetFramework>\n"
                            "    <OutputType>Library</OutputType>\n    <Nullable>enable</Nullable>\n"
                            "    <ImplicitUsings>enable</ImplicitUsings>\n"
                            "  </PropertyGroup>\n</Project>\n",
        },
        "cmd": "dotnet build -nologo -v q -clp:NoSummary 2>&1 | grep -v ' warning ' ; exit ${PIPESTATUS[0]}",
        "volumes": [f"{VOL}nuget:/root/.nuget/packages"],
    },
    "rust": {
        "image": "rust:1",
        "files": {
            "Cargo.toml": '[package]\nname = "al-api"\nversion = "0.1.0"\nedition = "2021"\n\n'
                          '[lib]\npath = "src/al_api.rs"\n\n[dependencies]\n'
                          'serde = { version = "1.0", features = ["derive"] }\nserde_json = "1.0"\n',
        },
        "cmd": "cargo build -q --message-format short 2>&1",
        "volumes": [f"{VOL}cargo:/usr/local/cargo/registry"],
    },
    "java": {
        "image": "maven:3-eclipse-temurin-21",
        "files": {
            "pom.xml": f"""<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>alapi</groupId>
  <artifactId>alapi</artifactId>
  <version>1</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>{JACKSON}</version>
    </dependency>
  </dependencies>
</project>
""",
        },
        "cmd": "mvn -q -B compile 2>&1",
        "volumes": [f"{VOL}m2:/root/.m2"],
    },
}


def run(lang):
    p = PROJECTS[lang]
    proj = OUT / lang
    for name, text in p["files"].items():
        (proj / name).parent.mkdir(parents=True, exist_ok=True)
        (proj / name).write_text(text)
    owner = f"{os.getuid()}:{os.getgid()}"
    args = ["docker", "run", "--rm", "-v", f"{proj}:/w", "-w", "/w"]
    for v in p["volumes"]:
        args += ["-v", v]
    script = f"{p['cmd']}; rc=$?; chown -R {owner} /w 2>/dev/null; exit $rc"
    start = time.time()
    r = subprocess.run(args + [p["image"], "bash", "-c", script], capture_output=True, text=True)
    return lang, r.returncode, (r.stdout + r.stderr).strip(), time.time() - start


def strict_check():
    print("schema: strict check ...", flush=True)
    env = dict(os.environ, ALAPI_STRICT_TYPES="1")
    r = subprocess.run([sys.executable, "-c", "import apischema; apischema.Schema()"], cwd=ROOT,
                       env=env, capture_output=True, text=True)
    if r.returncode:
        print((r.stdout + r.stderr).strip())
        raise SystemExit("schema: the strict check failed")


def main():
    args = sys.argv[1:]
    langs = [args[args.index("--lang") + 1]] if "--lang" in args else list(PROJECTS)
    verbose = "-v" in args
    if "--no-strict" not in args:
        strict_check()
    subprocess.run([sys.executable, str(ROOT / "scripts" / "gen-types.py"), "--all", str(OUT)],
                   check=True, capture_output=True)
    failed = []
    with ThreadPoolExecutor(len(langs)) as pool:
        for lang, rc, out, secs in pool.map(run, langs):
            print(f"{lang}: {'ok' if rc == 0 else 'FAILED'} ({secs:.0f} s)")
            if out and (rc or verbose):
                lines = out.splitlines()
                print("\n".join("    " + x for x in lines[:60]))
                if len(lines) > 60:
                    print(f"    ... {len(lines) - 60} more lines")
            if rc:
                failed.append(lang)
    if failed:
        raise SystemExit(f"failed: {' '.join(failed)}")


if __name__ == "__main__":
    main()
