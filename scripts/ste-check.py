#!/usr/bin/env python3
"""Mechanical checks for docs/STYLE.md (Simplified Technical English) on content/*.md.

It can't judge word choice or meaning; it catches what a script can:

  long      a sentence over 25 words (20 in a numbered or bulleted step that starts with a verb)
  para      a paragraph over 6 sentences
  passive   "is/are/was/were/be/been/being + past participle" (a hint, not always wrong)
  phrasal   common phrasal verbs that have a one-word STE replacement
  word      words STE replaces with simpler ones (utilize -> use, ...)

Code blocks, tables, headings and inline code are skipped. Usage:

  python3 scripts/ste-check.py content/learn-1.md [more files]   # list problems
  python3 scripts/ste-check.py --summary content/*.md             # counts per file
"""

import re
import sys
from pathlib import Path

LIMIT_DESC, LIMIT_PROC, LIMIT_PARA = 25, 20, 6

# STE-style replacements for words writers reach for. Not the official dictionary; the common
# offenders. Hard-coded because the list is short and easy to extend.
WORDS = {
    "utilize": "use", "utilise": "use", "initiate": "start", "commence": "start",
    "terminate": "stop", "approximately": "about", "facilitate": "help",
    "subsequently": "then", "prior to": "before", "in order to": "to",
    "additionally": "also", "numerous": "many", "sufficient": "enough",
    "however": "but", "therefore": "thus/so", "obtain": "get", "require": "need",
    "demonstrate": "show", "via": "through", "e.g.": "for example", "i.e.": "that is",
    "etc.": "(list them)", "basically": "(delete)", "simply": "(delete)",
    "just": "(delete if filler)", "actually": "(delete)",
}
PHRASAL = ["set up", "find out", "shut down", "keep on", "carry out", "figure out",
           "go ahead", "look up", "pick up", "turn on", "turn off", "fill in", "fill out",
           "come up", "end up", "make sure", "point out", "check out", "hold on", "give up"]
PASSIVE = re.compile(r"\b(is|are|was|were|be|been|being)\s+(\w+ly\s+)?(\w+ed|sent|done|"
                     r"made|given|taken|known|shown|seen|written|built|kept|left|held|set|"
                     r"put|read|run|thrown|found|lost|paid|sold|bought|hit|split|chosen)\b",
                     re.I)
# Words that make a bulleted/numbered line a procedural step (imperative first word).
STEP_VERBS = set("""add ask build call change check close compare connect copy count create
define delete download emit fetch find get give install keep let listen load look make move
open parse pick print put read reconnect remove repeat replace reply run save send set show
start stop store subscribe take test try update use wait walk watch write""".split())


def prose_blocks(text):
    """Yields (line_no, paragraph_text, is_list_item) for prose only."""
    in_code = False
    para, start = [], 0
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            if para:
                yield start, " ".join(para), False
                para = []
            continue
        if in_code:
            continue
        s = line.strip()
        if not s or s.startswith(("|", "#", "<!--", "<div", "</div")):
            if para:
                yield start, " ".join(para), False
                para = []
            continue
        item = re.match(r"([-*]|\d+\.)\s+", s)
        if item:
            if para:
                yield start, " ".join(para), False
                para = []
            yield n, s[item.end():], True
            continue
        if not para:
            start = n
        para.append(s.lstrip("> "))
    if para:
        yield start, " ".join(para), False


def clean(t):
    t = re.sub(r"`[^`]*`", "X", t)  # inline code counts as one word
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[*_]", "", t)
    return t


def sentences(t):
    # Split on . ! ? followed by space + capital/quote/digit; keeps "e.g. x" mostly whole.
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", t) if s.strip()]


def check(path):
    out = []
    text = Path(path).read_text()
    for n, para, is_item in prose_blocks(text):
        c = clean(para)
        sents = sentences(c)
        if not is_item and len(sents) > LIMIT_PARA:
            out.append((n, "para", f"{len(sents)} sentences"))
        for s in sents:
            words = re.findall(r"[\w'’-]+", s)
            proc = is_item and words and words[0].lower() in STEP_VERBS
            limit = LIMIT_PROC if proc else LIMIT_DESC
            if len(words) > limit:
                out.append((n, "long", f"{len(words)} words: {s[:90]}…"))
        low = " " + c.lower() + " "
        for w, r in WORDS.items():
            if re.search(rf"(?<![\w.]){re.escape(w)}(?![\w])", low):
                out.append((n, "word", f'"{w}" -> {r}'))
        for p in PHRASAL:
            if re.search(rf"\b{p}\b", low):
                out.append((n, "phrasal", f'"{p}"'))
        for m in PASSIVE.finditer(c):
            out.append((n, "passive", m.group(0)))
    return out


def main():
    args = sys.argv[1:]
    summary = "--summary" in args
    files = [a for a in args if not a.startswith("--")]
    total = 0
    for f in files:
        probs = check(f)
        total += len(probs)
        if summary:
            kinds = {}
            for _, k, _ in probs:
                kinds[k] = kinds.get(k, 0) + 1
            print(f"{f}: {len(probs)} " + " ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
        else:
            for n, k, msg in probs:
                print(f"{f}:{n}: {k}: {msg}")
    return 1 if total and not summary else 0


if __name__ == "__main__":
    sys.exit(main())
