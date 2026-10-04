#!/usr/bin/env python3
"""Prints how much of the schema is confirmed (docs/WRITING.md, "Confirmation").

    python3 scripts/confirm-report.py            # counts, then every shape that is not confirmed
    python3 scripts/confirm-report.py --summary  # counts only
    python3 scripts/confirm-report.py --file schema/send/buy.json   # only the shapes of one file
    python3 scripts/confirm-report.py --json     # everything as JSON (for scripts)

A shape (one documented payload; apischema.shape_id says how each is named) is
  confirmed in code   its `confirm` has `code` citations and no `live_needed`
  confirmed live      schema/live.json has at least one capture of it and no mismatches
  unconfirmed         neither: no `confirm` key yet, or `live_needed` and no capture yet
Live mismatches (a capture that does not fit the schema) are listed apart: the schema or the
capture tool is wrong, and ALAPI_STRICT_CONFIRM=1 fails the build until it is fixed.

Exit status is 0: this is a report. The gate is `ALAPI_STRICT_CONFIRM=1 python3 build.py`.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import apischema  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--summary", action="store_true", help="print the counts only")
    ap.add_argument("--file", help="only the shapes of this schema file (schema/send/buy.json)")
    args = ap.parse_args()

    schema = apischema.Schema()
    shapes = schema.shapes()
    if args.file:
        shapes = [sh for sh in shapes if sh.file == args.file.lstrip("./")]
        if not shapes:
            raise SystemExit(f"no shapes in {args.file}")

    rows = []
    for sh in shapes:
        st = sh.state()
        if st["missing"]:
            reason = "no \"confirm\" key yet"
        elif not st["confirmed"] and st["live_needed"]:
            reason = "live needed: " + st["live_needed"]
        else:
            reason = None
        rows.append({"id": sh.id, "file": sh.file, "kind": sh.kind, "in_code": st["in_code"],
                     "live": st["live"], "count": st["count"], "last": st["last"],
                     "missing": st["missing"], "live_needed": st["live_needed"],
                     "confirmed": st["confirmed"], "reason": reason,
                     "mismatches": st["mismatches"]})

    total = len(rows)
    in_code = sum(r["in_code"] for r in rows)
    live = sum(r["live"] for r in rows)
    both = sum(r["in_code"] and r["live"] for r in rows)
    confirmed = sum(r["confirmed"] for r in rows)
    unconfirmed = [r for r in rows if not r["confirmed"]]
    mism = [r for r in rows if r["mismatches"]]
    live_data = schema.live or {}
    summary = {"shapes": total, "confirmed_in_code": in_code, "confirmed_live": live, "both": both,
               "confirmed": confirmed, "unconfirmed": len(unconfirmed),
               "unconfirmed_no_key": sum(1 for r in unconfirmed if r["missing"]),
               "no_confirm_key": sum(r["missing"] for r in rows),
               "live_needed_no_capture": sum(1 for r in unconfirmed if not r["missing"]),
               "live_mismatches": len(mism),
               "live_json": {"captured_at": live_data.get("captured_at"), "server": live_data.get("server")}
               if schema.live is not None else None}

    if args.json:
        print(json.dumps({"summary": summary, "shapes": rows}, indent=2))
        return

    def pct(n):
        return f"{n:5d}  ({100.0 * n / total:5.1f}%)" if total else f"{n:5d}"

    print(f"Shapes{' in ' + args.file if args.file else ''}: {total}")
    print(f"  confirmed in code      {pct(in_code)}")
    print(f"  confirmed live         {pct(live)}")
    print(f"  both                   {pct(both)}")
    print(f"  confirmed (either)     {pct(confirmed)}")
    print(f"  unconfirmed            {pct(len(unconfirmed))}")
    print(f"    no \"confirm\" key     {pct(summary['unconfirmed_no_key'])}")
    print(f"    live needed, no capture {summary['live_needed_no_capture']}")
    print(f"  live mismatches        {pct(len(mism))}")
    print(f"  without \"confirm\" (the ALAPI_STRICT_CONFIRM gate; live-confirmed ones too) "
          f"{summary['no_confirm_key']}")
    if schema.live is None:
        print("schema/live.json: not there yet (no live captures)")
    else:
        print(f"schema/live.json: captured {live_data.get('captured_at', '?')} on "
              f"{live_data.get('server', '?')}")
    if args.summary:
        return

    if mism:
        print("\nLive mismatches (fix the schema, or the capture tool):")
        for r in mism:
            print(f"  {r['id']}  ({r['file']})")
            for m in r["mismatches"]:
                print(f"      {apischema.mismatch_text(m)[:300]}")

    # Unconfirmed: the ones that wait for a live capture first (they say why), then the shapes
    # that have no `confirm` yet, grouped by file with a count, since that list is long while
    # the keys are being filled in.
    waiting = [r for r in unconfirmed if not r["missing"]]
    if waiting:
        print("\nUnconfirmed, waiting for a live capture:")
        for r in waiting:
            print(f"  {r['id']}: {r['live_needed']}")
    missing = [r for r in unconfirmed if r["missing"]]
    if missing:
        by_file = defaultdict(list)
        for r in missing:
            by_file[r["file"]].append(r["id"])
        print(f"\nUnconfirmed, no \"confirm\" key yet ({len(missing)} shapes in {len(by_file)} files):")
        for f in sorted(by_file):
            print(f"  {f} ({len(by_file[f])})")
            for sid in by_file[f]:
                print(f"      {sid}")


if __name__ == "__main__":
    main()
