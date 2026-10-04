"""
Includes: a chapter embeds code from course/ instead of a copy of it.

    <!-- include course/python/albot/alsocket.py -->
    <!-- include course/go/world/world.go region=apply-entities -->
    <!-- include course/test-server/server.js region=auth lang=js -->

The comment must be alone on its line. The build replaces it with one fenced block:

- The path is relative to the repository root.
- The fence tag comes from `lang=`, else from the path (`course/<lang>/...` for the seven course
  languages), else from the file extension (EXT below).
- `region=NAME` takes only the lines between `<c> region NAME` and `<c> endregion NAME`, where
  <c> is the file's comment token (`//`, `#`, `--` or `<!--`). The common indent is removed.
- Region marker lines (of any region) never appear in the output.
- A missing file, a missing region, or an empty region stops the build with the line of the
  include, so a renamed file can't silently drop code from a chapter.

Seven includes in a row (one per language, in the order of docs/EXAMPLES.md) become seven
adjacent fenced blocks, and the page shows them as one tab group, like hand-written blocks.

No dependencies beyond Python 3. build.py uses expand(); scripts may import it too.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# The seven course languages: a path under course/<lang>/ takes that tag.
COURSE_LANGS = {"js", "ts", "python", "go", "csharp", "rust", "java"}
# Fence tags by file extension, for paths outside course/<lang>/ (the test server, configs).
EXT = {
    ".js": "js", ".mjs": "js", ".ts": "ts", ".py": "python", ".go": "go", ".cs": "csharp",
    ".rs": "rust", ".java": "java", ".json": "json", ".toml": "toml", ".xml": "xml",
    ".csproj": "xml", ".sln": "text", ".sh": "sh", ".ps1": "powershell", ".txt": "text",
    ".mod": "text", ".yml": "yaml", ".yaml": "yaml",
}

INCLUDE_RE = re.compile(r"^<!--\s*include\s+(\S+)((?:\s+\w+=\S+)*)\s*-->\s*$")
# A region marker line: a comment token, then "region NAME" or "endregion NAME".
MARKER_RE = re.compile(r"^\s*(?://|#|--|<!--)\s*(end)?region\s+([\w-]+)\b.*$")


class IncludeError(Exception):
    pass


def fence_tag(path, lang=None):
    if lang:
        return lang
    parts = Path(path).parts
    if len(parts) > 1 and parts[0] == "course" and parts[1] in COURSE_LANGS:
        return parts[1]
    return EXT.get(Path(path).suffix, "text")


def extract(path, region=None):
    """Returns the code of `path` (or of one region of it) without region marker lines."""
    file = ROOT / path
    if not file.is_file():
        raise IncludeError(f"no such file: {path}")
    lines = file.read_text().splitlines()
    if region is not None:
        starts = [i for i, l in enumerate(lines)
                  if (m := MARKER_RE.match(l)) and not m.group(1) and m.group(2) == region]
        if len(starts) != 1:
            raise IncludeError(f"{path}: region '{region}' found {len(starts)} times")
        s = starts[0]
        e = next((i for i in range(s + 1, len(lines))
                  if (m := MARKER_RE.match(lines[i])) and m.group(1) and m.group(2) == region),
                 None)
        if e is None:
            raise IncludeError(f"{path}: region '{region}' has no 'endregion {region}'")
        lines = lines[s + 1:e]
    lines = [l for l in lines if not MARKER_RE.match(l)]
    # Trim blank lines at both ends, then the common indent (a region inside a class).
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise IncludeError(f"{path}: region '{region}' is empty" if region else f"{path} is empty")
    indent = min(len(l) - len(l.lstrip()) for l in lines if l.strip())
    lines = [l[indent:] if l.strip() else "" for l in lines]
    if any(l.startswith("```") for l in lines):
        raise IncludeError(f"{path}: a line starts with ``` and would end the fence")
    return "\n".join(lines)


def expand(text, source="?", strict=True, warn=None):
    """Replaces each include line of `text` with a fenced block. `source` names the file in
    error messages. Raises IncludeError. With strict=False, a missing file or region is only
    reported through warn(message), and the block says that the code is missing (for work in
    progress: build.py makes it fatal under ALAPI_STRICT_TYPES=1)."""
    out, fence = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fence = not fence  # an include line inside a code block is shown, not expanded
        m = None if fence else INCLUDE_RE.match(line.strip())
        if not m:
            if not fence and line.lstrip().startswith("<!-- include"):
                raise IncludeError(f"{source}:{n}: malformed include: {line.strip()}")
            out.append(line)
            continue
        path, opts = m.group(1), dict(o.split("=", 1) for o in m.group(2).split())
        unknown = set(opts) - {"region", "lang"}
        if unknown:
            raise IncludeError(f"{source}:{n}: unknown include option {sorted(unknown)}")
        try:
            code = extract(path, opts.get("region"))
        except IncludeError as e:
            if strict:
                raise IncludeError(f"{source}:{n}: {e}") from None
            if warn:
                warn(f"{source}:{n}: {e}")
            code = f"(missing: {e})"
        out.append(f"```{fence_tag(path, opts.get('lang'))}\n{code}\n```")
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")
