# Updating the reference after a game update

The reference is written **from the live game's open-source code**. `versions.json` pins what
it was written against:

| Pin | What it is | Where the live value comes from |
|---|---|---|
| `g_version` | The game data G | the front page, which loads `data.js?v=<version>` |
| `source_commit`, `source_version` | `kaansoral/adventureland_mongodb`, the live game's code, and its `version.js` | `git ls-remote` |
| `common_commit` | `kaansoral/common_engine`, its shared engine | `git ls-remote` |

Bare citations (`node/server.js:123`) point into `source_commit`; `common:` citations into
`common_commit`. `legacy_*` (the old App Engine repo) is frozen and not checked.

The live code deploys every few days. For it, the report lists the commits, **the releases
shipped since the pin** (from the game's own release list, `update_notes.js`), the
protocol-relevant files that changed, new or removed socket handlers and response codes, and the
cited lines that moved.

## How you find out

- **On GitHub:** `.github/workflows/game-update.yml` runs every day. If a pin is out of date,
  it opens (or updates) an issue with the label `game-update`. The issue body is the report.
- **Locally:** run the check yourself:

  ```sh
  python3 scripts/check-updates.py            # exit 0: no change; 10: change; 1: error
  ```

## The update pass

Do these steps in order.

1. Run the check and save the report:
   `python3 scripts/check-updates.py --report update.md`.
2. If the **live code** moved, rewrite the citations that only shifted:
   `python3 scripts/check-updates.py --fix-lines`. Read the shipped releases. Then re-read each
   entry under "Entries whose cited lines changed".
3. Document new socket handlers, and add each one to `SEND_GROUPS` in `build.py`. Add a row to
   the `game_response` table for each new response code.
4. If a protocol file changed (`api.js`, `node/json_parser.js`, `node/msgpack_parser.js`, the
   `auth` handler), re-check the Build a bot chapters on logging in and connecting. Re-run their
   example programs.
5. If **G** moved, go through "Entries to re-check for G". Update numbers, tables and examples.
   Update the counts in `content/game-data.md` headings (`### items (638)`). New items,
   monsters and maps can also need a sentence in the game guide.
6. Follow `docs/STYLE.md` and `docs/EXAMPLES.md` for every edit.
7. Pin the new versions: `python3 scripts/check-updates.py --pin`. This rewrites
   `versions.json` and `data/g-fingerprint.json`, and moves the clones in `vendor/`.
8. Rebuild with `python3 build.py`, check the pages, and publish (see `CLAUDE.md`).
9. Close the `game-update` issue.

> **Caution:** Run `--pin` only after the update pass. After `--pin`, the check reports "no
> change", and the list of affected entries is gone. Keep `update.md` until you finish.

## Field-level detail for G

The repo keeps only a fingerprint of the pinned G (one hash per key). The report can then say
"`items.hpot1` changed" but not how. If `vendor/G/G_<pinned version>.json` exists locally, the
report also shows the changed fields (`hp: 100 -> 120`). Keep the downloaded G files in
`vendor/G/`; the check saves each new version there.

## A prompt for a Claude session

> Run `python3 scripts/check-updates.py --report update.md` in
> /home/julian/dev/al/protocol. Do the update pass in docs/UPDATING.md for everything
> in the report. Read the live code and G for each change; don't guess. Follow
> docs/STYLE.md and docs/EXAMPLES.md. Run `--pin` and `python3 build.py` at the end. Report
> what you changed, entry by entry.
