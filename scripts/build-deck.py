#!/usr/bin/env python3
"""
Builds site/deck.html: the game guide as slides.

    python3 scripts/build-deck.py        (build.py runs it)

The slides are in deck/: deck.json (title, slide order, sections, fonts) and one
deck/slides/<id>.html per slide. Each slide file is one <section> on a fixed 1920 x 1080 canvas
with inline styles only. They were first made as a claude.ai slide deck, so they use that
format: <x-shape> for block arrows and <aside> for speaker notes. This script puts them on one
page with a small player: the canvas scales to the window, arrow keys / click / swipe change
slides, `#<slide id>` links to a slide, N shows the speaker notes.

Images are in site/img/deck/ (the game's own art, cut down for the web). A slide refers to them
as img/deck/<name>.png, relative to site/. No dependencies beyond Python 3.
"""

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECK = ROOT / "deck"

deck = json.loads((DECK / "deck.json").read_text())
slides = []
for sid in deck["order"]:
    text = (DECK / "slides" / f"{sid}.html").read_text().strip()
    # One <section id="<id>"> per file, the id equal to the file name: the hash links need it.
    if not re.match(rf'<section id="{re.escape(sid)}"', text):
        raise SystemExit(f"deck/slides/{sid}.html: must start with <section id=\"{sid}\"")
    missing = [p for p in re.findall(r'src="(img/deck/[^"]+)"', text) if not (ROOT / "site" / p).exists()]
    if missing:
        raise SystemExit(f"deck/slides/{sid}.html: missing image {missing[0]}")
    slides.append(text)

# Section starts: shown as the chapter name beside the slide counter.
starts = {s["start"]: s["description"] for s in deck["sections"].values()}
fonts = "&".join(f["href"].split("?", 1)[1].replace("&display=swap", "") for f in deck["faces"].values())

page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(deck["title"])}: slides</title>
<meta name="description" content="How the Adventure Land MMO works, in {len(slides)} slides: classes, combat, leveling, items, upgrades, gold and events, with the game's own art.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{fonts}&display=swap">
<style>
/* The player. The slides carry their own inline styles; this sheet gives them the defaults of
   the slide format (no margins, heading sizes, ruled tables) and draws <x-shape>. */
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; height: 100%; background: #0d1020; color: #f4efe3; font-family: "IBM Plex Sans", Arial, sans-serif; overflow: hidden; }}
.bar {{ position: fixed; left: 0; right: 0; top: 0; height: 44px; display: flex; align-items: center; gap: 14px; padding: 0 14px; font-size: 14px; background: #0d1020; z-index: 2; }}
.bar a, .bar button {{ color: #bcc3d6; text-decoration: none; background: none; border: 1px solid #2e3550; border-radius: 6px; padding: 4px 10px; font: inherit; cursor: pointer; }}
.bar a:hover, .bar button:hover {{ color: #f4efe3; border-color: #8c93a8; }}
.bar .where {{ color: #8c93a8; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; flex: 1; }}
.bar .count {{ color: #f4efe3; font-variant-numeric: tabular-nums; }}
.stage {{ position: fixed; left: 0; right: 0; top: 44px; bottom: 0; overflow: hidden; }}
.stage.notes {{ bottom: 30vh; }}
/* The canvas keeps its 1920x1080 size and is centered and scaled with one transform (fit()). */
.canvas {{ position: absolute; left: 50%; top: 50%; width: 1920px; height: 1080px; transform-origin: center center; }}
.canvas > section {{ position: absolute; inset: 0; width: 1920px; height: 1080px; overflow: hidden; opacity: 0; visibility: hidden; transition: opacity .25s; }}
.canvas > section.on {{ opacity: 1; visibility: visible; }}
/* The slide format paints children in source order: a pinned backdrop listed first stays under
   the text. A browser paints pinned (absolute) boxes over normal flow, so flow children get
   position: relative too; then all of them stack in source order. */
.canvas > section > :not([style*="position:absolute"]) {{ position: relative; }}
.canvas h1, .canvas h2, .canvas h3, .canvas p, .canvas ul, .canvas ol, .canvas table {{ margin: 0; }}
.canvas h1 {{ font-size: 96px; font-weight: 600; line-height: 1.1; }}
.canvas h2 {{ font-size: 64px; font-weight: 600; line-height: 1.15; }}
.canvas h3 {{ font-size: 44px; font-weight: 600; line-height: 1.2; }}
.canvas p {{ font-size: 32px; line-height: 1.4; }}
.canvas ul, .canvas ol {{ padding-left: 1.3em; display: flex; flex-direction: column; gap: .5em; }}
.canvas table {{ border-collapse: collapse; }}
.canvas th, .canvas td {{ padding: .35em .6em; text-align: left; vertical-align: top; border-bottom: 1px solid rgba(128, 128, 128, .35); }}
.canvas th {{ font-weight: 600; }}
.canvas img {{ display: block; }}
.canvas a {{ color: inherit; }}
.canvas aside {{ display: none; }}
/* Block arrow of the slide format: the head is the last 40% of the box. */
x-shape {{ display: block; flex: none; }}
x-shape[kind="arrow-right"] {{ clip-path: polygon(0 30%, 60% 30%, 60% 0, 100% 50%, 60% 100%, 60% 70%, 0 70%); }}
.notes-panel {{ position: fixed; left: 0; right: 0; bottom: 0; height: 30vh; overflow: auto; padding: 14px 20px; background: #161a2b; border-top: 1px solid #2e3550; color: #bcc3d6; font-size: 16px; line-height: 1.6; display: none; }}
.notes-panel.on {{ display: block; }}
.hint {{ color: #8c93a8; }}
@media (max-width: 700px) {{ .hint, .bar .where {{ display: none; }} }}
</style>
</head>
<body>
<div class="bar">
  <a href="index.html">← Start</a>
  <span class="count" id="count"></span>
  <span class="where" id="where"></span>
  <span class="hint">← → to move · N for notes</span>
  <button type="button" id="notesBtn">Notes</button>
  <a href="game.html">Full guide</a>
</div>
<div class="stage" id="stage"><div class="canvas" id="canvas">
{chr(10).join(slides)}
</div></div>
<div class="notes-panel" id="notes"></div>
<script>
// Slide player. One slide has class "on"; the canvas is 1920x1080 and scales to the stage.
const SECTIONS = {json.dumps(starts, ensure_ascii=False)};
const slides = [...document.querySelectorAll("#canvas > section")];
const stage = document.getElementById("stage"), canvas = document.getElementById("canvas");
const notes = document.getElementById("notes");
let i = 0, where = "";

function fit() {{
  const s = Math.min(stage.clientWidth / 1920, stage.clientHeight / 1080);
  canvas.style.transform = `translate(-50%, -50%) scale(${{s}})`;
}}

function show(n, push) {{
  i = Math.max(0, Math.min(slides.length - 1, n));
  slides.forEach((s, k) => s.classList.toggle("on", k === i));
  // The chapter is the last section start at or before this slide.
  for (let k = 0; k <= i; k++) if (SECTIONS[slides[k].id]) where = SECTIONS[slides[k].id];
  document.getElementById("count").textContent = `${{i + 1}} / ${{slides.length}}`;
  document.getElementById("where").textContent = where;
  const aside = slides[i].querySelector("aside");
  notes.textContent = aside ? aside.textContent : "No notes for this slide.";
  if (push) history.replaceState(null, "", "#" + slides[i].id);
}}

function fromHash() {{
  const k = slides.findIndex((s) => "#" + s.id === location.hash);
  show(k < 0 ? 0 : k, false);
}}

document.addEventListener("keydown", (e) => {{
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  if (["ArrowRight", "PageDown", " "].includes(e.key)) {{ show(i + 1, true); e.preventDefault(); }}
  else if (["ArrowLeft", "PageUp"].includes(e.key)) {{ show(i - 1, true); e.preventDefault(); }}
  else if (e.key === "Home") show(0, true);
  else if (e.key === "End") show(slides.length - 1, true);
  else if (e.key === "n" || e.key === "N") toggleNotes();
}});
// Click the right two thirds to go on, the left third to go back. Links still work.
stage.addEventListener("click", (e) => {{
  if (e.target.closest("a")) return;
  show(e.clientX > window.innerWidth / 3 ? i + 1 : i - 1, true);
}});
let x0 = null;
stage.addEventListener("touchstart", (e) => {{ x0 = e.touches[0].clientX; }}, {{ passive: true }});
stage.addEventListener("touchend", (e) => {{
  if (x0 === null) return;
  const dx = e.changedTouches[0].clientX - x0; x0 = null;
  if (Math.abs(dx) > 40) show(dx < 0 ? i + 1 : i - 1, true);
}});
function toggleNotes() {{
  notes.classList.toggle("on");
  stage.classList.toggle("notes", notes.classList.contains("on"));
  fit();
}}
document.getElementById("notesBtn").addEventListener("click", toggleNotes);
window.addEventListener("resize", fit);
window.addEventListener("hashchange", fromHash);
fit();
fromHash();
</script>
</body>
</html>
"""

(ROOT / "site" / "deck.html").write_text(page)
print(f"site/deck.html: {len(slides)} slides, {len(page) // 1024} KB")
