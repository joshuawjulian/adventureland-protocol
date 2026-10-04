#!/usr/bin/env python3
"""Runs one stage of the live-capture tool in Docker (node:22), the way scripts/check-course.py
runs the course: no Node.js on the host.

    python3 tools/capture/run.py <stage> [Name,Name,...]
    python3 tools/capture/run.py --list          # the stages

The login is the owner's bot login, /home/julian/dev/al/claude-bot-old/credentials.json
({userID, userAuth}). HARD-CODED path, overridable with AL_CREDS_FILE. The file is mounted
read-only at /creds.json; the token never goes on a command line or into the container's
environment (both are visible in `docker inspect`). record.ts redacts it from the captures.

The repo is mounted at /w; captures land in /w/captures/<date>/ (git-ignored). G is cached in
tools/capture/.al-cache (git-ignored).
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CREDS = os.environ.get("AL_CREDS_FILE", "/home/julian/dev/al/claude-bot-old/credentials.json")
IMAGE = "node:22"  # Node.js 22.18+ runs .ts files directly (docs/COURSE.md, pinned versions)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "--list"):
        args = ["--list"]
    if not Path(CREDS).is_file():
        sys.exit(f"no credentials file at {CREDS}")
    name = "alapi-capture-" + (args[0] if args[0] != "--list" else "list")
    cmd = [
        "docker", "run", "--rm", "--init", "--name", name,
        "-v", f"{ROOT}:/w",
        "-v", f"{CREDS}:/creds.json:ro",
        "-w", "/w/tools/capture",
        # Files written in /w belong to the host user, not root.
        "-u", f"{os.getuid()}:{os.getgid()}",
        IMAGE, "node", "--no-warnings", "run.ts", *[a for a in args if a != "--list"],
    ]
    try:
        sys.exit(subprocess.call(cmd))
    except KeyboardInterrupt:
        # docker run forwards the signal (--init); the stage closes its sockets and exits.
        subprocess.call(["docker", "stop", "-t", "10", name], stdout=subprocess.DEVNULL)
        sys.exit(130)


if __name__ == "__main__":
    main()
