# cooldowns.py: when each skill is ready again.
#
# The server refuses a skill that is used too early (game_response "cooldown")
# and charges call-cost for the refusal. So we keep one "ready again at" time
# per name and check it before we act. Names are skill names ("attack",
# "supershot", ...) and "potion", the one timer that all potions and the free
# regeneration share.
import re
import time
from typing import Any

from .world import World


# region cooldowns
class Cooldowns:
    def __init__(self, world: World) -> None:
        self.G = world.G
        self._ready_at: dict[str, float] = {}  # name -> time.monotonic() seconds
        # Listen through world.listen, so that hitchhikers count too.
        # skill_timeout comes after each skill, attack included: {name, ms}.
        world.listen("skill_timeout", lambda d: self.start(d["name"], d["ms"]))
        world.listen("game_response", self._on_game_response)
        world.listen("eval", self._on_eval)

    def start(self, name: str, ms: float) -> None:
        """`name` is busy for `ms` milliseconds from now. A skill that shares its
        cooldown with another (G.skills[name].share) makes that one busy too."""
        at = time.monotonic() + ms / 1000
        self._ready_at[name] = at
        share = self.G["skills"].get(name, {}).get("share")
        if share:
            self._ready_at[share] = at

    def ready(self, name: str) -> bool:
        return time.monotonic() >= self._ready_at.get(name, 0)

    def ms_left(self, name: str) -> float:
        """Milliseconds until `name` is ready; 0 when it is ready now."""
        return max(0.0, (self._ready_at.get(name, 0) - time.monotonic()) * 1000)

    def _on_game_response(self, d: Any) -> None:
        if not isinstance(d, dict):
            return  # a bare string response has no time in it
        if d.get("response") == "cooldown":  # we were too early: ms is the rest
            self.start(d.get("skill") or d.get("place") or "attack", d.get("ms", 0))
        elif d.get("response") == "not_ready":  # a potion too early
            self.start("potion", d.get("ms", 0))

    def _on_eval(self, d: Any) -> None:
        """The server also sends timers as code for the browser to run:
        "pot_timeout(2000)" and "skill_timeout('ethereal',120)". The payload is
        a string or {code}. We read the two calls with a regular expression."""
        code = d if isinstance(d, str) else (d or {}).get("code", "")
        if pot := re.search(r"pot_timeout\((\d+)", code):
            self.start("potion", int(pot.group(1)))
        if skill := re.search(r"skill_timeout\('([^']+)',\s*(\d+)", code):
            self.start(skill.group(1), int(skill.group(2)))
# endregion cooldowns
