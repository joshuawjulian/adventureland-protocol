#!/usr/bin/env python3
"""Validates the AsyncAPI export (scripts/gen-asyncapi.py) with the official parser, in Docker.

    python3 scripts/check-asyncapi.py            # generate into .examples/asyncapi/, then validate
    python3 scripts/check-asyncapi.py FILE.json  # validate this file (for example site/asyncapi.json)
    python3 scripts/check-asyncapi.py -v         # also print every warning (else a count per rule)

It runs `@asyncapi/parser` (the library behind `asyncapi validate` and AsyncAPI Studio) in
node:22: the JSON Schema of the AsyncAPI 3.0 spec, then its Spectral rule set (references,
operation messages that are in their channel, unused components, ...). Exit status 0 when the
parser reports no error; warnings, infos and hints are listed but do not fail.

The npm cache is the `alapi-examples-npm` volume of scripts/check-examples.py, so the package
downloads once. PARSER pins the version: bump it on purpose, and read the parser's changelog.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".examples" / "asyncapi"   # git-ignored, like the other check outputs
PARSER = "3.6.3"   # @asyncapi/parser, 2026-10-04
IMAGE = "node:22"

# Parses /w/doc.json and prints one JSON line per diagnostic, then a summary line.
# Severity: 0 error, 1 warning, 2 info, 3 hint (Spectral).
VALIDATE_JS = r"""
const fs = require("fs");
const { Parser } = require("@asyncapi/parser");
(async () => {
  const parser = new Parser();
  const { document, diagnostics } = await parser.parse(fs.readFileSync("/w/doc.json", "utf8"));
  const names = ["error", "warning", "info", "hint"];
  for (const d of diagnostics) {
    console.log(JSON.stringify({ severity: names[d.severity], code: d.code, message: d.message,
                                 path: (d.path || []).join(".") }));
  }
  const summary = { parsed: !!document };
  if (document) {
    summary.channels = document.channels().length;
    summary.operations = document.operations().length;
    summary.messages = document.components().messages().length;
    summary.schemas = document.components().schemas().length;
  }
  // The parser checks the document's structure and references, not the payload schemas
  // themselves, and not the examples. Ajv (a dependency of the parser, draft-07: the base of the
  // AsyncAPI Schema format) does both.
  const Ajv = require("ajv");
  const raw = JSON.parse(fs.readFileSync("/w/doc.json", "utf8"));
  // strict: false, because the x-al-* keys and AsyncAPI's string `discriminator` are not
  // draft-07 keywords (draft-07 ignores unknown keywords).
  const ajv = new Ajv({ strict: false, allErrors: false });
  ajv.addSchema({ $id: "https://alapi.invalid/doc.json", components: { schemas: raw.components.schemas } });
  for (const [name, s] of Object.entries(raw.components.schemas)) {
    if (!ajv.validateSchema(s)) {
      console.log(JSON.stringify({ severity: "error", code: "json-schema-invalid",
        message: ajv.errorsText(ajv.errors), path: "components.schemas." + name }));
    }
  }
  const cache = {};
  const check = (ref) => cache[ref] || (cache[ref] = ajv.compile({ $ref: "https://alapi.invalid/doc.json" + ref }));
  let examples = 0;
  for (const [name, m] of Object.entries(raw.components.messages)) {
    if (!m.payload || !m.payload.$ref) continue;
    (m.examples || []).forEach((ex, i) => {
      examples++;
      const v = check(m.payload.$ref);
      if (!v(ex.payload)) {
        // A trimmed example leaves out required fields on purpose: a warning.
        const sev = m["x-al-example-trimmed"] ? "info" : "warning";
        console.log(JSON.stringify({ severity: sev, code: "example-does-not-match-payload",
          message: ajv.errorsText(v.errors), path: `components.messages.${name}.examples.${i}` }));
      }
    });
  }
  summary.examplesChecked = examples;
  console.log("SUMMARY " + JSON.stringify(summary));
})().catch((e) => { console.error(e); process.exit(2); });
"""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbose = "-v" in sys.argv
    WORK.mkdir(parents=True, exist_ok=True)
    doc = WORK / "doc.json"
    if args:
        doc.write_bytes(Path(args[0]).read_bytes())
    else:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "gen-asyncapi.py"), "-o", str(doc)],
                       check=True)
    (WORK / "validate.js").write_text(VALIDATE_JS)
    (WORK / "package.json").write_text('{ "private": true }\n')
    owner = f"{os.getuid()}:{os.getgid()}"
    script = (f'if [ "$(cat node_modules/.pins 2>/dev/null)" != "parser@{PARSER}" ]; then '
              f"npm i --no-audit --no-fund --silent --no-save @asyncapi/parser@{PARSER} >/dev/null && "
              f'echo "parser@{PARSER}" > node_modules/.pins; fi; node validate.js; rc=$?; '
              f"chown -R {owner} /w 2>/dev/null; exit $rc")
    r = subprocess.run(["docker", "run", "--rm", "-v", f"{WORK}:/w", "-w", "/w",
                        "-v", "alapi-examples-npm:/root/.npm", IMAGE, "bash", "-c", script],
                       capture_output=True, text=True)
    diags, summary = [], None
    for line in r.stdout.splitlines():
        if line.startswith("SUMMARY "):
            summary = json.loads(line[8:])
        elif line.startswith("{"):
            diags.append(json.loads(line))
    if summary is None:
        print((r.stdout + r.stderr).strip())
        raise SystemExit("asyncapi: the parser did not run")
    by = {}
    for d in diags:
        by.setdefault(d["severity"], []).append(d)
    for sev in ("error", "warning", "info", "hint"):
        items = by.get(sev, [])
        if not items:
            continue
        counts = {}
        for d in items:
            counts[d["code"]] = counts.get(d["code"], 0) + 1
        print(f"{sev}s: {len(items)} (" + ", ".join(f"{c}: {n}" for c, n in sorted(counts.items())) + ")")
        for d in items if (verbose or sev == "error") else []:
            print(f"    {d['code']}: {d['message']}  at {d['path']}")
    print("asyncapi: " + json.dumps(summary))
    if by.get("error") or not summary.get("parsed"):
        raise SystemExit("asyncapi: the document does not validate")
    print("asyncapi: ok (no errors)")


if __name__ == "__main__":
    main()
