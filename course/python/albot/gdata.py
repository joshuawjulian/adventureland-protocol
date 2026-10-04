# gdata.py: the game data G. Download it once per game version, keep it on
# disk, and read it as typed data.
# Needs: pip install httpx==0.27.2
#
# G holds every item, monster, skill, map and NPC of the game (about 2.8 MB of
# JSON). It changes only with a new game version, so we keep one file per
# version in .al-cache/ and download again only when the version changes.
import json
import os
import re
from typing import Any, NotRequired, TypedDict, cast
from urllib.parse import urlsplit

import httpx

from .api import base_url


# region types
# Typed views of three G tables, with only the fields that the course reads.
# G has many more fields and tables; the other tables are plain dicts here.
class ItemDef(TypedDict):
    name: str  # the display name
    type: str  # "weapon", "pot", "material", ...
    g: int  # the base value in gold (also the NPC price)
    s: NotRequired[int]  # the largest stack; absent: the item does not stack
    gives: NotRequired[list[list[Any]]]  # potions: [stat, amount] pairs, e.g. [["hp", 200]]
    cooldown: NotRequired[int]  # ms
    compound: NotRequired[dict[str, float]]  # the stats that each compound level adds; present: it compounds
    upgrade: NotRequired[dict[str, float]]  # the stats that each upgrade level adds; present: it upgrades


class MonsterDef(TypedDict):
    name: str
    hp: int
    attack: int
    speed: float  # px per second
    range: float  # px
    frequency: float  # attacks per second
    xp: int
    respawn: float  # SECONDS (unlike most durations); -1: never by itself
    damage_type: str  # "physical", "magical", "pure"
    size: NotRequired[float]  # a scale for the hit box (G.dimensions)


class SkillDef(TypedDict, total=False):  # every field is optional
    name: str
    type: str
    cooldown: int  # ms
    mp: int
    range: int
    share: str  # this skill uses the cooldown of that other skill
    level: int


class GData(TypedDict):
    version: int
    items: dict[str, ItemDef]
    monsters: dict[str, MonsterDef]
    skills: dict[str, SkillDef]
    dimensions: dict[str, list[float]]  # [width, height, ...] of a sprite or monster type
    maps: dict[str, Any]
    geometry: dict[str, Any]
    npcs: dict[str, Any]
    classes: dict[str, Any]
# endregion types


# region fetch-version
async def fetch_version(base: str) -> int | None:
    """The game page has the line var VERSION='17478' (htmls/base_script.html:32).
    None if the page has no such line."""
    async with httpx.AsyncClient(timeout=15) as http:  # 15 s: generous for one page
        res = await http.get(f"{base}/hub")
    res.raise_for_status()
    m = re.search(r"var\s+VERSION\s*=\s*'(\d+)", res.text)
    return int(m.group(1)) if m else None
# endregion fetch-version


# region download-g
async def download_g(base: str) -> GData:
    """/data.js is JavaScript: `var G={...};`. The JSON is the text from the
    first "{" to the last "}"."""
    async with httpx.AsyncClient(timeout=60) as http:  # 60 s: G is a few MB
        res = await http.get(f"{base}/data.js")
    res.raise_for_status()
    js = res.text
    return cast(GData, json.loads(js[js.index("{") : js.rindex("}") + 1]))
# endregion download-g


def cache_path(base: str, version: int | str) -> str:
    """.al-cache/<host>/G_<version>.json. <host> is the host and port of `base`
    with ":" changed to "_", so that the G of a test server never mixes with
    the live G."""
    host = urlsplit(base).netloc.replace(":", "_")
    return os.path.join(".al-cache", host, f"G_{version}.json")


# region load-g
async def load_g(base: str | None = None) -> GData:
    """G from the cache if we have this version, else from the server (and
    then into the cache)."""
    base = base or base_url()
    version = await fetch_version(base)
    if version is not None and os.path.exists(cache_path(base, version)):
        with open(cache_path(base, version), encoding="utf-8") as f:
            return cast(GData, json.load(f))
    G = await download_g(base)
    # Save under the version in G itself: /hub can lack the line.
    path = cache_path(base, G["version"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(G, f)
    print(f"downloaded G version {G['version']}")
    return G
# endregion load-g
