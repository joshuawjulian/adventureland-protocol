#!/usr/bin/env bash
# Fetches the game's code at the commits pinned in versions.json, into vendor/ (git-ignored;
# the game's code is not ours to redistribute):
#
#   vendor/adventureland_mongodb  the live game: Express API + Node game server. Every
#                                 `node/server.js:1234` in content/ points here.
#   vendor/common_engine          its shared engine (cited as `common:js/file.js:N`).
#   vendor/adventureland          the old App Engine version, frozen (cited as `legacy:...`).
#
#   bash scripts/fetch-source.sh
set -euo pipefail
cd "$(dirname "$0")/.."
pin() { python3 -c "import json; print(json.load(open('versions.json'))['$1'])"; }

fetch() { # fetch <dir> <repo> <commit>
  local dir=$1 repo=$2 commit=$3
  if [ ! -d "$dir/.git" ]; then
    mkdir -p "$dir"
    git -C "$dir" init --quiet
    git -C "$dir" remote add origin "$repo"
  fi
  # A shallow fetch of exactly the pinned commit: fast, and enough to read. check-updates.py
  # deepens it when it needs history to diff against a newer commit.
  git -C "$dir" fetch --quiet --depth 1 origin "$commit"
  git -C "$dir" checkout --quiet "$commit"
  echo "$dir at $(git -C "$dir" log -1 --format='%h %cd')"
}

fetch vendor/adventureland_mongodb "$(pin source_repo)" "$(pin source_commit)"
fetch vendor/common_engine "$(pin common_repo)" "$(pin common_commit)"
fetch vendor/adventureland "$(pin legacy_repo)" "$(pin legacy_commit)"
