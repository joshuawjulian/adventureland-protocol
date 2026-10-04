#!/usr/bin/env python3
"""Checks live captures against the schema and writes schema/live.json.

    python3 scripts/check-captures.py                 # all of captures/**/*.jsonl
    python3 scripts/check-captures.py FILE.jsonl ...  # only these
    python3 scripts/check-captures.py -v              # also list every confirmed shape

The captures come from tools/capture/ (the live recorder): one JSON record per line, see
tools/capture/record.ts. This script:

  1. enumerates every documented shape of schema/ with its stable id (the ids of the
     confirmation spec: send/<event>/request, send/<event>/response/<name>[#with|#without],
     send/<event>/failure/<n>, send/<event>/also/<i>, the same under
     send/<event>/variant/<variant>/..., recv/<event>/payload, recv/<event>/variant/<name>,
     type/<Name>);
  2. walks each capture in order, per character:
       - an outgoing frame is a request: it confirms send/<event>/request (and the variant's);
       - an incoming frame confirms its recv/<event> payload (and the variant it fits);
       - an incoming frame is also matched to the request it answers: a game_response by its
         code (and place, request_id), any other event only when its payload ties it to the
         request (Matcher.identifies: see "Attribution" below);
       - the hitchhikers of a `player` update count as incoming frames of their own;
  3. validates each matched payload against the shape's type, field by field, and collects
     mismatches with their field paths;
  4. writes schema/live.json: per shape id {count, first, last, sample (one real payload,
     redacted and trimmed), mismatches}, plus `unmatched`: frames the docs do not know
     (events without a schema, codes that no shape of the request lists). Those are doc gaps.

Python 3 standard library only; the schema is read with apischema.Schema.

Matching rules worth knowing (they decide what "confirmed live" means):
  - Several failure rows of one request can answer with the same code ("no_target" for two
    different causes). The recorder writes a `probe` record with the shape ids the probe
    meant to hit; when one of the candidates is in that list, only it is credited. Without
    that, every candidate whose payload validates is credited.
  - A reply that is not a game_response (an `also` event, `chest_opened`, `ping_ack`, ...) is
    credited only when it is provably that reply: the most recent request on that character
    whose shapes list the event, and whose payload names it (our name as `attacker`/`id`/
    `name`/`owner`, the requested target, the `pid` of our `action`, the documented phrase
    key, the echoed payload) or which only that handler sends to that socket (DEDICATED).
    Within REPLY_WINDOW_MS, or PENDING_MS for a reply the docs say comes later; never after
    the request's game_response when the `order` puts the event before it; never before the
    replies the order puts ahead of it (to you). `player` (BRACKETED) is held until a later
    reply of the same request arrives. An event with no rule (party_update, merrit_status,
    an `{id, outside}` disappear, a `+500` regen text of another player, ...) never confirms a
    reply shape, only its recv/<event> shape.
  - The outgoing `auth` request is redacted at capture time; this script also redacts the
    user id in samples (schema/live.json is published).
"""

import glob
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import apischema  # noqa: E402
from apischema import (codes_of, forms, parse_type, variant_list, variant_name,  # noqa: E402
                       variant_values)

OUT = ROOT / "schema" / "live.json"
SERVER = "US V"  # HARD-CODED: the one server the owner authorized for captures

# How long after a request a non-game_response reply still counts as its reply. 1.5 s covers a
# round trip with room; the upgrade/compound results come later but as game_response hitchhikers,
# which are matched by code, not by time (PENDING_MS).
REPLY_WINDOW_MS = 1500
# How long a request stays a candidate for game_response replies. 40 s: an upgrade roll of a
# high level can take ~30 s (course/ts/albot/items.ts).
PENDING_MS = 40_000
MAX_MISMATCHES = 8  # distinct mismatches kept per shape


# ---------------------------------------------------------------------------------------------
# Validation: a value against a type expression or an object spec, collecting every problem.
# ---------------------------------------------------------------------------------------------

class Validator:
    def __init__(self, schema):
        self.s = schema
        self._trees = {}

    def tree(self, text):
        t = self._trees.get(text)
        if t is None:
            t = self._trees[text] = parse_type(text)
        return t

    def check_type(self, text_or_tree, v, path):
        """Returns (errors, refs): errors as [(path, kind, message)], refs = the named types that
        the value matched (only along the passing members of unions)."""
        tree = self.tree(text_or_tree) if isinstance(text_or_tree, str) else text_or_tree
        return self._t(tree, v, path)

    def _t(self, tree, v, path):
        kind = tree[0]
        if kind == "lit":
            if v != tree[1] or isinstance(v, bool) != isinstance(tree[1], bool):
                return [(path, "type", f"{short(v)} is not {json.dumps(tree[1])}")], set()
            return [], set()
        if kind == "prim":
            ok = {"string": lambda x: isinstance(x, str),
                  "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
                  "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
                  "boolean": lambda x: isinstance(x, bool),
                  "null": lambda x: x is None,
                  "object": lambda x: isinstance(x, dict)}.get(tree[1], lambda x: True)
            if not ok(v):
                return [(path, "type", f"{short(v)} is not a {tree[1]}")], set()
            return [], set()
        if kind == "ref":
            name = tree[1]
            t = self.s.types[name]
            if "type" in t:
                errs, refs = self._t(self.tree(t["type"]), v, path)
            else:
                errs, refs = self.check_object(t, v, path, name)
            return errs, (refs | {name}) if not errs else refs
        if kind == "array":
            if not isinstance(v, list):
                return [(path, "type", f"{short(v)} is not an array")], set()
            errs, refs = [], set()
            for i, x in enumerate(v):
                e, r = self._t(tree[1], x, f"{path}[{i}]")
                errs += e
                refs |= r
                if len(errs) > 20:
                    break
            return errs, refs
        if kind == "record":
            if not isinstance(v, dict):
                return [(path, "type", f"{short(v)} is not an object")], set()
            errs, refs = [], set()
            for k, x in v.items():
                e, r = self._t(tree[1], x, f"{path}.{k}")
                errs += e
                refs |= r
                if len(errs) > 20:
                    break
            return errs, refs
        if kind == "tuple":
            if not isinstance(v, list) or len(v) != len(tree[1]):
                return [(path, "type", f"{short(v)} is not a {len(tree[1])}-tuple")], set()
            errs, refs = [], set()
            for i, (t, x) in enumerate(zip(tree[1], v)):
                e, r = self._t(t, x, f"{path}[{i}]")
                errs += e
                refs |= r
            return errs, refs
        if kind == "union":
            best = None
            for t in tree[1]:
                e, r = self._t(t, v, path)
                if not e:
                    return [], r
                if best is None or len(e) < len(best):
                    best = e
            if len(best) == 1:
                return best, set()
            return [(path, "type", f"{short(v)} matches no member of the union; closest: "
                     + "; ".join(f"{p}: {m}" for p, _, m in best[:3]))], set()
        return [(path, "type", f"unknown type node {kind}")], set()

    def check_object(self, spec, v, path, name=None, undeclared=None):
        """An object spec ({fields, extends, open}). `undeclared` forces (True) or skips (False)
        the check for fields the spec does not declare; default: checked unless the spec is open."""
        if not isinstance(v, dict):
            return [(path, "type", f"{short(v)} is not an object" + (f" ({name})" if name else ""))], set()
        fields = self.s.all_fields(spec)
        errs, refs = [], set()
        names = set()
        for f in fields:
            names.add(f["name"])
            if f["name"] in v:
                e, r = self.check_type(f["type"], v[f["name"]], f"{path}.{f['name']}")
                errs += e
                refs |= r
            elif not f.get("optional"):
                errs.append((f"{path}.{f['name']}", "missing", "required field is absent"))
        check_extra = (not self.s.is_open(spec)) if undeclared is None else undeclared
        if check_extra:
            for k in v:
                if k not in names:
                    errs.append((f"{path}.{k}", "undeclared", f"field not in the docs (value {short(v[k])})"))
        return errs, refs


def short(v, n=60):
    t = json.dumps(v, separators=(",", ":"), default=str)
    return t if len(t) <= n else t[: n - 3] + "..."


# ---------------------------------------------------------------------------------------------
# Shapes: apischema's (Schema.shapes(), shape ids by apischema.shape_id). This catalog adds what
# the matcher needs on top: which send event a reply belongs to, its variant and request_id
# form, the codes a game_response reply can carry, and the events it can arrive on.
# ---------------------------------------------------------------------------------------------

_VARIANT = re.compile(r"^send/(?P<ev>[^/]+)/variant/(?P<v>.+)/(?:request|response|failure|also)(?:/|$)")


def response_codes(schema, spec):
    """The codes of a game_response reply spec: its `response` field's literals, else
    code/codes/code_type. None: any code."""
    if not spec:
        return None
    if spec.get("fields") or spec.get("extends"):
        for f in schema.all_fields(spec):
            if f["name"] == "response":
                tree = parse_type(f["type"])
                if tree[0] == "lit":
                    return {tree[1]}
                if tree[0] == "union" and all(t[0] == "lit" for t in tree[1]):
                    return {t[1] for t in tree[1]}
    codes = codes_of(spec)
    if codes:
        return set(codes)
    if spec.get("code_type"):
        tree = parse_type(spec["code_type"])
        if tree[0] == "lit":
            return {tree[1]}
        if tree[0] == "union" and all(t[0] == "lit" for t in tree[1]):
            return {t[1] for t in tree[1]}
    return None


class Catalog:
    def __init__(self, schema):
        self.s = schema
        self.v = Validator(schema)
        self.shapes = {sh.id: sh for sh in schema.shapes()}
        self.replies = {}  # send event -> [Shape] (responses, failure rows, also)
        self.requests = {}  # send event -> {variant id or None: Shape}
        self.recv = {}  # recv event -> (payload Shape, [variant Shapes])
        self.codes = {}  # shape id -> set of codes, or None (any) -- game_response replies only
        self.form = {}  # shape id -> "with" / "without" / None
        self.variant = {}  # shape id -> variant id or None
        self.unsolicited = {}  # game_response code -> [recv variant Shapes] that document it alone
        self._orders = {}  # (send event, variant id) -> parse_order() result
        responses = {}  # (send event, response name) -> [Shape] (for failure rows that `see` one)
        for sh in schema.shapes():
            m = _VARIANT.match(sh.id)
            self.variant[sh.id] = m.group("v") if m else None
            self.form[sh.id] = sh.id.rsplit("#", 1)[1] if "#" in sh.id else None
            if sh.direction == "send" and sh.kind == "request":
                self.requests.setdefault(sh.event, {})[self.variant[sh.id]] = sh
            elif sh.kind in ("response", "also"):
                self.replies.setdefault(sh.event, []).append(sh)
                spec = sh.target[1] if sh.target[0] == "object" else sh.holder
                self.codes[sh.id] = response_codes(schema, spec if isinstance(spec, dict) else None) \
                    or response_codes(schema, sh.holder if isinstance(sh.holder, dict) else None)
                if sh.kind == "response":
                    name = sh.id.split("/response/", 1)[1].split("#")[0]
                    responses.setdefault((sh.event, name), []).append(sh)
            elif sh.kind == "failure":
                self.replies.setdefault(sh.event, []).append(sh)
            elif sh.kind == "payload":
                self.recv[sh.event] = (sh, self.recv.get(sh.event, (None, []))[1])
            elif sh.kind == "variant":
                sh.has = (sh.holder or {}).get("has") or []
                pay, vs = self.recv.get(sh.event, (None, []))
                self.recv[sh.event] = (pay, vs + [sh])
                # A game_response variant whose type is one named object type with a literal
                # `response` (`condition`, `ex_condition`) documents a code that comes without
                # a request. Its codes: such a frame is not a doc gap when no request fits.
                if sh.event == "game_response":
                    tname = (sh.holder or {}).get("type")
                    spec = schema.types.get(tname) if isinstance(tname, str) else None
                    for c in (response_codes(schema, spec) if isinstance(spec, dict) else None) or ():
                        self.unsolicited.setdefault(c, []).append(sh)
        # Failure rows: the union of the codes of their replies (a `see` reply: the codes of
        # that response). None when one reply takes any code (the `object` form).
        for sh in schema.shapes():
            if sh.kind != "failure":
                continue
            _, s, v, row = sh.target
            codes = set()
            for _, rep in schema.flat_replies(row):
                if rep.get("close"):
                    continue
                if rep.get("see"):
                    for r in responses.get((sh.event, rep["see"]), []):
                        c = self.codes.get(r.id)
                        codes = None if c is None or codes is None else codes | c
                    continue
                if schema.failure_event(s, rep) != "game_response":
                    continue
                c = response_codes(schema, rep) if rep.get("form", "failure") != "object" else None
                codes = None if c is None or codes is None else codes | c
            self.codes[sh.id] = codes

    def errors(self, sh, payload, event=None):
        """apischema's mismatches for this payload, as (path, kind, message)."""
        out = []
        for msg in sh.check(payload, event):
            text = re.sub(r"^\((?:closest [^)]*)\) ", "", msg)
            path, _, rest = text.partition(": ")
            path = path.replace(sh.id, "$", 1) if path.startswith(sh.id) else path
            kind = "undeclared" if "undeclared" in rest else "missing" if "missing required" in rest else "type"
            out.append((path, kind, rest or msg))
        return out

    def refs(self, sh, payload):
        """The named types that a passing payload used (to credit type/<Name>)."""
        t = sh.target
        try:
            if t[0] == "object":
                errs, refs = self.v.check_object(t[1], payload, "$")
            elif t[0] == "type":
                errs, refs = self.v.check_type(t[1], payload, "$")
            elif t[0] == "recv":
                p = self.s.recv[t[1]].get("payload", {})
                if p.get("fields") or p.get("extends"):
                    errs, refs = self.v.check_object(p, payload, "$")
                else:
                    errs, refs = self.v.check_type(p.get("type", "any"), payload, "$")
            else:
                return set()
        except (KeyError, ValueError):
            return set()
        return refs if not errs else {r for r in refs}

    def specs(self, sh, event):
        """The documented reply objects of a reply shape on `event` (for their examples and
        `when`): the response or `also` entry itself, or the replies of a failure row that use
        that event (with the row's `when`)."""
        if sh.kind == "failure":
            _, s, _, row = sh.target
            out = []
            for _, rep in self.s.flat_replies(row):
                if rep.get("close") or rep.get("see") or self.s.failure_event(s, rep) != event:
                    continue
                out.append(dict(rep, when=row.get("when", "")))
            return out
        h = sh.holder if isinstance(sh.holder, dict) else {}
        t = sh.target[1] if sh.target[0] == "object" and isinstance(sh.target[1], dict) else {}
        return [dict(t, **h)]

    def phrases(self, sh, event):
        """The phrase keys the schema gives for this reply: its examples' `phrase`, a literal
        `phrase` field, and the phrase names in backticks of a `when` that talks of phrases."""
        out = set()
        for spec in self.specs(sh, event):
            ex = spec.get("example")
            if isinstance(ex, dict) and isinstance(ex.get("phrase"), str):
                out.add(ex["phrase"])
            for f in spec.get("fields") or []:
                if f.get("name") == "phrase":
                    tree = parse_type(f["type"])
                    lits = [tree] if tree[0] == "lit" else tree[1] if tree[0] == "union" else []
                    out |= {x[1] for x in lits if x[0] == "lit" and isinstance(x[1], str)}
            when = spec.get("when") or ""
            if "phrase" in when:
                out |= {t for t in _TICK.findall(when)
                        if re.fullmatch(r"[a-z0-9_.]+", t) and (t.startswith("server.") or ("_" in t and len(t) >= 8))}
        return out

    def is_later(self, sh, event):
        """A reply the docs say comes later (a timer, a projectile, a payment): it may arrive
        long after the request."""
        for spec in self.specs(sh, event):
            w = (spec.get("when") or "").strip()
            if re.match(r"^later\b", w, re.I) or "timer ends" in w or "after `eta`" in w:
                return True
        return False

    def order(self, event, vid):
        """parse_order() of the request part (the variant's `order`, else the shared one)."""
        key = (event, vid)
        if key not in self._orders:
            s = self.s.send[event]
            o = s.get("order")
            for v in variant_list(s):
                if apischema.variant_id(v) == vid and v.get("order") is not None:
                    o = v["order"]
            self._orders[key] = parse_order(o, self.s.recv) if o else {"pre": set(), "preds": {}, "paths": []}
        return self._orders[key]

# ---------------------------------------------------------------------------------------------
# Variants of a request: which one a payload is.
# ---------------------------------------------------------------------------------------------

def truthy(x):
    return x not in (None, False, 0, "", [], {})


# The variants that the schema matches with prose ("match"), as code. Keyed by event, then the
# variant name. Each gets the payload (a dict, or another value).
MATCH = {
    "activate": {"Equipment": lambda d: truthy(d.get("slot")), "Inventory": lambda d: not truthy(d.get("slot"))},
    "cx": {"Clear": lambda d: truthy(d.get("slot")) and "name" not in d,
           "Put on": lambda d: "name" in d or not truthy(d.get("slot"))},
    "equip": {"Trade listing": lambda d: str(d.get("slot", "")).startswith("trade") and not d.get("consume"),
              "Use or equip": lambda d: True},
    "property": {"AFK": lambda d: not truthy(d.get("typing"))},
    "say": {"Private": lambda d: not truthy(d.get("party")) and truthy(d.get("name")),
            "Public": lambda d: not truthy(d.get("party")) and not truthy(d.get("name"))},
    "send": {"Item": lambda d: "num" in d, "Gold": lambda d: "num" not in d and "gold" in d,
             "Cosmetic": lambda d: "num" not in d and "gold" not in d and "cx" in d,
             "None": lambda d: not any(k in d for k in ("num", "gold", "cx"))},
    "upgrade": {"Upgrade": lambda d: not truthy(d.get("calculate"))},
    "interaction": {"Konami": lambda d: "key" in d},
}


def variant_of(s, payload):
    vs = variant_list(s)
    if not vs:
        return None
    key = s["variants"]["key"]
    if not isinstance(payload, dict):
        for v in vs:  # a request "type" variant: the payload is a bare value
            if v.get("request", {}).get("type") and payload in variant_values(v) + [
                    json.loads(v["request"]["type"]) if v["request"]["type"].startswith('"') else None]:
                return v
        return None
    val = payload.get(key)
    for v in vs:
        if "value" in v and val in variant_values(v) and not (isinstance(val, bool) != any(
                isinstance(x, bool) for x in variant_values(v))):
            return v
    m = MATCH.get(s["event"], {})
    for v in vs:
        fn = m.get(variant_name(v))
        if fn and "value" not in v and fn(payload):
            return v
    for v in vs:
        if v.get("other"):
            return v
    return None


# ---------------------------------------------------------------------------------------------
# Walking the captures
# ---------------------------------------------------------------------------------------------

class Tally:
    def __init__(self):
        self.shapes = {}  # id -> {count, first, last, sample, mismatches, _keys}
        self.unmatched = {"events_in": {}, "events_out": {}, "codes": {}, "unattributed_codes": {}}

    def hit(self, sid, t, payload):
        e = self.shapes.setdefault(sid, {"count": 0, "first": t, "last": t, "sample": None,
                                         "mismatches": []})
        e["count"] += 1
        e["first"] = min(e["first"] or t, t)
        e["last"] = max(e["last"] or t, t)
        if e["sample"] is None and payload is not ...:
            e["sample"] = sample(payload)

    def miss(self, sid, t, errs, payload, char):
        e = self.shapes.setdefault(sid, {"count": 0, "first": None, "last": None, "sample": None,
                                         "mismatches": []})
        e.setdefault("mismatch_count", 0)
        e["mismatch_count"] += 1
        known = {(m["path"], m["problem"]) for m in e["mismatches"]}
        for path, kind, msg in errs:
            norm = re.sub(r"\[\d+\]", "[]", path)
            if (norm, msg) in known or len(e["mismatches"]) >= MAX_MISMATCHES:
                continue
            known.add((norm, msg))
            e["mismatches"].append({"at": t, "char": char, "path": norm, "kind": kind, "problem": msg,
                                    "payload": sample(payload)})

    def gap(self, kind, key, t, payload, extra=None):
        d = self.unmatched[kind].setdefault(key, {"count": 0, "first": t, "sample": sample(payload)})
        d["count"] += 1
        if extra:
            d.update(extra)


USER_ID = re.compile(r"\bUS_\d+\b")


def sample(v, depth=0):
    """A copy small enough to publish: arrays cut to 5 items, deep objects cut, user ids out."""
    if isinstance(v, str):
        return USER_ID.sub("US_<REDACTED>", v)
    if isinstance(v, list):
        out = [sample(x, depth + 1) for x in v[:5]]
        if len(v) > 5:
            out.append(f"... {len(v) - 5} more")
        return out
    if isinstance(v, dict):
        if depth > 4:
            return {"...": f"{len(v)} fields"}
        items = list(v.items())
        out = {k: sample(x, depth + 1) for k, x in items[:60]}
        if len(items) > 60:
            out["..."] = f"{len(items) - 60} more fields"
        return out
    return v


def load(paths):
    """Yields (file, records) per capture file, in file order."""
    for p in paths:
        recs = []
        with open(p) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        yield p, recs


def expand(recs):
    """Frames in order, with the hitchhikers of each `player` as frames of their own."""
    for r in recs:
        if r.get("k") == "probe":
            yield r
            continue
        if r.get("k") != "frame":
            continue
        yield r
        if r["dir"] == "in" and r["event"] == "player" and isinstance(r.get("data"), dict):
            for hh in r["data"].get("hitchhikers") or []:
                if isinstance(hh, list) and hh:
                    yield {"k": "frame", "t": r["t"], "ms": r["ms"], "char": r["char"], "dir": "in",
                           "event": hh[0], "data": hh[1] if len(hh) > 1 else None, "via": "hitchhiker"}


def expected(sid, expect):
    """True when a probe named this shape (a probe may leave off the #with/#without form)."""
    return sid in expect or sid.split("#", 1)[0] in expect


# ---------------------------------------------------------------------------------------------
# Attribution: is this incoming frame provably the reply to this request?
#
# A game_response names its request (place, request_id, code), so reply_code() can match it.
# Every other event carries no such link, and many of them are broadcasts: another player's
# "+500" regen is a `disappearing_text` too, and arrives on our socket within a second of our
# `sbuy`. Being "a reply the schema lists, shortly after the request" proved nothing (it once
# credited send/sbuy/failure/5 seven times with strangers' regen texts). So a non-game_response
# frame is credited to a request only when a rule below ties the payload to the request: our
# character's name in the actor field, the request's target id, the projectile id of our
# `action`, a phrase key the schema documents for that reply, an echo of the request, or an
# event that only that handler sends, to that socket alone.
#
# An event with no rule here (party_update, cave, poker, upgrade, merrit_status, drop, ...)
# never confirms a reply shape live, however well it fits. Its frames still confirm
# recv/<event>/payload: any received frame is a real sample of the receive event.
# ---------------------------------------------------------------------------------------------

# HARD-CODED: events that only request handlers send, and only to the socket that sent the
# request (each one's `to` and `senders` in schema/recv/ say so). On the requesting socket,
# soon after a request whose replies list it, such a frame can only be that reply.
DEDICATED = {"blocker", "ccreport", "pvp_list", "secondhands", "lostandfound", "start",
             "tauri_auth", "tauri_auth_error", "test", "trade_history", "tracker", "gm",
             "simple_eval", "players", "correction", "track", "q_data"}

# HARD-CODED: reply events the server can send more than once for one request (a game_log per
# item of a chest, a disappear per entity, a player update before and after a save, ...). Any
# other reply shape is credited at most once per request.
REPEATABLE = {"game_log", "disappear", "disappearing_text", "player", "map_chunk", "drop",
              "server_message", "q_data", "pm", "cave", "poker", "new_map"}

# HARD-CODED: reply events that come on your socket for many reasons, so often that one lands
# in any 1.5 s window (a fighting character gets about one `player` a second). Such a frame is
# held on the request and credited only when a later reply of the same request (by the order:
# the game_response, `chest_opened`, ...) arrives after it. Without such a reply it is never
# credited (move's "Channels stopped" `player`, for one, has nothing after it).
BRACKETED = {"player"}

# The fields of a request that can name the entity it acts on (attack/heal `id`, a target, a
# character name, a resale `rid`).
TARGET_KEYS = ("id", "target", "name", "to", "rid")

# A phrase key ends in an article that varies with the item ("server.item.found.a" / ".an").
_ARTICLE = re.compile(r"\.(?:a|an|some|the|many|one|plural)$")
_TICK = re.compile(r"`([^`]+)`")


def norm_phrase(p):
    return _ARTICLE.sub("", p) if isinstance(p, str) else p


def phrase_ok(phrase, allowed):
    """True when a payload's phrase key is one the schema documents for this reply: equal to an
    example's phrase (articles aside), or ending with a bare phrase name the `when` text gives
    (`listed_at_gold` for server.game_log.listed_at_gold)."""
    if not isinstance(phrase, str):
        return False
    for a in allowed:
        if norm_phrase(phrase) == norm_phrase(a) or phrase.endswith("." + a) \
                or norm_phrase(phrase).endswith("." + a):
            return True
    return False


def parse_order(order, events):
    """What the prose `order` of a request part says about timing, as
        pre:   events that the server sends only before the first `game_response` of the
               request (once a game_response of it has come, such a frame is not its reply);
        preds: event -> [set of events]: entries that come unconditionally before it and go to
               you, each a set of alternatives; at least one of each must already be credited.
    `events`: the names of the receive events (to tell `player` from `Action` in backticks).
    An order that is an object (one list per path) gives only `pre`, for events that come before
    the game_response in every path that has them."""
    def entry_events(e):
        return [t for t in _TICK.findall(e) if t in events or t == "game_response"]

    def later(e):
        return re.match(r"^(later|after|at the end|then|during)", e.strip(), re.I)

    def unconditional(e):
        """Starts with the event and has no condition ("only", "if", "for `x`", ...)."""
        e = re.sub(r"^now:\s*", "", e.strip())
        return e.startswith("`") and not re.search(
            r"\b(only|if|when|unless|until)\b|\bfor `|with `request_id`", e)

    lists = list(order.values()) if isinstance(order, dict) else [order or []]
    before, after = set(), set()
    for lst in lists:
        gr = next((i for i, e in enumerate(lst) if "game_response" in entry_events(e)), len(lst))
        for i, e in enumerate(lst):
            evs = set(entry_events(e)) - {"game_response"}
            # An entry that comes "later" (a timer, a projectile) is after the reply in effect.
            if i < gr and not later(e):
                before |= evs
            else:
                after |= evs
    preds = {}
    if isinstance(order, list):
        prior = []
        for e in order:
            evs = set(entry_events(e)) - {"game_response"}
            if later(e):
                break  # what comes later is not ordered against the replies before it
            if not unconditional(e):
                continue
            for ev in evs:
                preds.setdefault(ev, list(prior))
            if "to you" in e or "you included" in e:
                if evs:
                    prior.append(evs)
    # The entries of each path up to the first "later" one, as event sets (for follows()).
    paths = []
    for lst in lists:
        seq = []
        for e in lst:
            if later(e):
                break
            seq.append(set(entry_events(e)))
        paths.append(seq)
    return {"pre": before - after, "preds": preds, "paths": paths}


def follows(order, a, b):
    """True when the order puts an entry with event `b` after an entry with event `a`, in one
    path, both before anything "later"."""
    for seq in order["paths"]:
        ia = next((i for i, evs in enumerate(seq) if a in evs), None)
        if ia is not None and any(b in evs for evs in seq[ia + 1:]):
            return True
    return False


class Matcher:
    def __init__(self, cat, tally):
        self.cat = cat
        self.s = cat.s
        self.t = tally
        self.pending = {}  # char -> [request dict], oldest first
        self.expect = {}  # char -> the `expect` set of the last probe record (for the next request)

    def credit(self, sh, t, payload):
        self.t.hit(sh.id, t, payload)
        for name in self.cat.refs(sh, payload):
            self.t.hit(f"type/{name}", t, ...)

    def check(self, sh, data, event, t, char, record=True):
        """Validates; on a pass credits the shape and returns True; on a fail records the
        mismatch (when `record`) and returns the errors."""
        errs = self.cat.errors(sh, data, event)
        if not errs:
            self.credit(sh, t, data)
            return True
        if record:
            self.t.miss(sh.id, t, errs, data, char)
        return errs

    def run(self, recs):
        for r in expand(recs):
            if r.get("k") == "probe":
                self.expect[r["char"]] = set(r.get("expect") or [])
                continue
            if r["dir"] == "out":
                self.out(r)
            else:
                self.inc(r)

    # -- requests -----------------------------------------------------------------------------

    def out(self, r):
        ev, data, t, char = r["event"], r.get("data"), r["t"], r["char"]
        s = self.s.send.get(ev)
        if s is None:
            self.t.gap("events_out", ev, t, data)
            return
        v = variant_of(s, data)
        vid = apischema.variant_id(v) if v is not None else None
        req = self.cat.requests.get(ev, {})
        # A probe that aims at a failure row sends a request that is wrong on purpose (a string
        # where an object goes, a missing field): that is not a doc mismatch of the request.
        on_purpose = any("/failure/" in x for x in self.expect.get(char, ()))
        for key in ([None, vid] if vid is not None else [None]):
            if key in req:
                self.check(req[key], data, ev, t, char, record=not on_purpose)
        rid = data.get("request_id") if isinstance(data, dict) else None
        # got: (shape id, event) pairs credited to this request; events: the events credited;
        # closed: a game_response of it came (replies the order puts before it are over);
        # failed: a failure row was credited (only that row's other replies can follow);
        # pid: the projectile id of its `action` (its `hit` carries the same); seen: the events
        # received on this socket since the request; tentative: `player` frames held until a
        # later reply of the request brackets them (see BRACKETED).
        p = {"event": ev, "variant": vid, "ms": r["ms"], "t": t, "data": data,
             "request_id": rid, "expect": self.expect.pop(char, set()),
             "got": set(), "events": set(), "closed": False, "failed": False, "pid": None,
             "seen": set(), "tentative": []}
        lst = self.pending.setdefault(char, [])
        lst.append(p)
        cutoff = r["ms"] - PENDING_MS
        while lst and lst[0]["ms"] < cutoff:
            lst.pop(0)

    # -- incoming -----------------------------------------------------------------------------

    def inc(self, r):
        ev, data, t, char = r["event"], r.get("data"), r["t"], r["char"]
        self.recv(ev, data, t, char)
        if ev == "game_response":
            self.reply_code(data, t, char, r["ms"])
        else:
            self.reply_event(ev, data, t, char, r["ms"])

    def recv(self, ev, data, t, char):
        if ev not in self.cat.recv:
            self.t.gap("events_in", ev, t, data)
            return
        pay, variants = self.cat.recv[ev]
        if pay is not None:
            self.check(pay, data, ev, t, char)
        if variants:
            # The variant: the first whose `has` keys are all there and whose type fits; else
            # the first that fits. No variant fits: the payload mismatch above says why.
            keyed = [v for v in variants if v.has and isinstance(data, dict) and all(k in data for k in v.has)]
            for v in keyed + [v for v in variants if v not in keyed]:
                if self.check(v, data, ev, t, char, record=False) is True:
                    return

    def candidates(self, p, event):
        """The reply shapes of request `p` that can arrive on `event`: its variant's and the
        shared part's, in the request_id form that fits the request."""
        out = []
        for sh in self.cat.replies.get(p["event"], []):
            if event not in (sh.events or []) or sh.sends_nothing:
                continue
            v = self.cat.variant[sh.id]
            if v is not None and v != p["variant"]:
                continue
            form = self.cat.form[sh.id]
            if form == "with" and p["request_id"] is None:
                continue
            if form == "without" and p["request_id"] is not None:
                continue
            out.append(sh)
        return out

    def _credit_best(self, p, cands, data, event, t, char, report_miss):
        """Validates `data` against each candidate and credits the passing ones (only the ones
        the probe expected, when it named any of them). Returns True when something was
        credited (or, with report_miss, when the closest candidate's mismatch was recorded)."""
        passing, best = [], None
        for sh in cands:
            errs = self.cat.errors(sh, data, event)
            if not errs:
                passing.append(sh)
            elif best is None or len(errs) < len(best[1]):
                best = (sh, errs)
        if passing:
            exp = [sh for sh in passing if expected(sh.id, p["expect"])]
            for sh in exp or passing:
                self.credit(sh, t, data)
                self.note(p, sh, event, data)
            return True
        if report_miss and best is not None:
            exp = [sh for sh in cands if expected(sh.id, p["expect"])]
            if exp:  # the probe said which row it meant: report against that one
                best = (exp[0], self.cat.errors(exp[0], data, event))
            self.t.miss(best[0].id, t, best[1], data, char)
            return True
        return False

    def reply_code(self, data, t, char, ms):
        code = data if isinstance(data, str) else (data.get("response") if isinstance(data, dict) else None)
        place = data.get("place") if isinstance(data, dict) else None
        rid = data.get("request_id") if isinstance(data, dict) else None
        order = list(reversed(self.pending.get(char, [])))
        if rid is not None:
            order = [p for p in order if p["request_id"] == rid] + [p for p in order if p["request_id"] != rid]

        def fits_place(p):
            if place is None or place == p["event"]:
                return True
            d = p["data"] if isinstance(p["data"], dict) else {}
            return place in (d.get("name"), d.get("type"), d.get("place"), d.get("event"))

        def has_code(sh):
            c = self.cat.codes.get(sh.id)
            return c is None or code in c

        # Pass 1: the most recent request whose shapes take this code (place fits) and validate.
        # Shapes that name the code come before shapes that take any code.
        for p in order:
            if not fits_place(p):
                continue
            cands = [sh for sh in self.candidates(p, "game_response") if has_code(sh)]
            named = [sh for sh in cands if self.cat.codes.get(sh.id) is not None]
            if named and self._credit_best(p, named, data, "game_response", t, char, False):
                return
            rest = [sh for sh in cands if sh not in named]
            if rest and self._credit_best(p, rest, data, "game_response", t, char, False):
                return
        # Pass 2: the reply names a place: the most recent request of that place gets it. The
        # docs have the code there, but the payload does not fit: a mismatch. The docs do not
        # have the code there: a doc gap.
        for p in order:
            if place is not None and fits_place(p):
                cands = [sh for sh in self.candidates(p, "game_response")
                         if self.cat.codes.get(sh.id) is not None and code in self.cat.codes[sh.id]]
                if cands:
                    self._credit_best(p, cands, data, "game_response", t, char, True)
                else:
                    self.t.gap("codes", f"{p['event']}: {code}", t, data,
                               {"request": sample(p["data"]), "place": place})
                return
        # No request fits: unsolicited (a death, an event of the world) or unknown. A code that
        # a game_response variant documents on its own (`condition`, `ex_condition`) is known:
        # recv() already credited the variant when the payload fits; when it does not, that is
        # a mismatch of the variant, not a gap.
        docs = self.cat.unsolicited.get(code)
        if docs:
            if not any(not self.cat.errors(sh, data, "game_response") for sh in docs):
                self.t.miss(docs[0].id, t, self.cat.errors(docs[0], data, "game_response"), data, char)
            return
        self.t.gap("unattributed_codes", f"{code} (place {place})", t, data)

    def note(self, p, sh, event, data):
        """Records on the request what was credited to it (see out() for the keys)."""
        p["got"].add((sh.id, event))
        p["events"].add(event)
        if event == "game_response":
            p["closed"] = True
        if sh.kind == "failure":
            p["failed"] = True
        if event == "action" and isinstance(data, dict):
            p["pid"] = data.get("pid")
        # A reply that the order puts after held frames: they came between the request and
        # this reply, so they are the request's own. Credit them now.
        if p["tentative"] and event not in BRACKETED:
            order = self.cat.order(p["event"], p["variant"])
            keep = []
            for held in p["tentative"]:
                cands, hdata, ht, hchar, hev = held
                if follows(order, hev, event):
                    self._credit_best(p, cands, hdata, hev, ht, hchar, False)
                else:
                    keep.append(held)
            p["tentative"] = keep

    def reply_event(self, ev, data, t, char, ms):
        """A frame that is not a game_response: credited to the most recent request on this
        socket that one of its reply shapes provably answers (identifies(), in its window, in
        the documented order). The frame is then marked seen for every pending request."""
        pending = self.pending.get(char, [])
        try:
            for p in reversed(pending):
                cands = [sh for sh in self.candidates(p, ev) if self.attributable(p, sh, ev, data, char, ms)]
                if cands and ev in BRACKETED:
                    # Held, not credited: see BRACKETED. The frame is claimed by this request.
                    if any(not self.cat.errors(sh, data, ev) for sh in cands):
                        p["tentative"].append((cands, data, t, char, ev))
                        return
                    continue
                if cands and self._credit_best(p, cands, data, ev, t, char, False):
                    return
            # A move shows only in the `entities` of the others (you are not in your own), so
            # its reply is looked for on the other sockets of the capture: our other characters
            # and the observer see the mover with the destination it sent.
            if ev == "entities":
                for other, lst in self.pending.items():
                    if other == char:
                        continue
                    for p in reversed(lst):
                        if p["event"] != "move":
                            continue
                        cands = [sh for sh in self.candidates(p, ev)
                                 if self.attributable(p, sh, ev, data, other, ms)]
                        if cands and self._credit_best(p, cands, data, ev, t, char, False):
                            return
        finally:
            for p in pending:
                p["seen"].add(ev)

    def attributable(self, p, sh, ev, data, char, ms):
        """True when `data` (on `ev`) can be the reply `sh` of request `p`, sent by `char`: in its window, not
        after the request is over by the documented order, and tied to it by identifies()."""
        later = self.cat.is_later(sh, ev)
        if ms - p["ms"] > (PENDING_MS if later else REPLY_WINDOW_MS):
            return False
        if (sh.id, ev) in p["got"] and ev not in REPEATABLE:
            return False  # one per request
        # A failed request sends nothing more but the other replies of its failure row; a
        # failure row cannot follow a reply of success either.
        if p["failed"] and not any(g[0] == sh.id for g in p["got"]):
            return False
        order = self.cat.order(p["event"], p["variant"])
        if not later and sh.kind == "failure" and p["events"] and not any(g[0] == sh.id for g in p["got"]):
            return False
        if not later:
            # The server writes one socket in order: once a game_response of the request has
            # come, the replies that the order puts before it are over.
            if p["closed"] and ev in order["pre"]:
                return False
            # Entries the order puts before this one, sent to you: one of each must have come.
            if sh.kind != "failure":
                have = p["events"] | {held[4] for held in p["tentative"]}
                for alts in order["preds"].get(ev, []):
                    if not (alts & have):
                        return False
        return self.identifies(p, sh, ev, data, char)

    def identifies(self, p, sh, ev, data, char):
        """The rule of each reply event: does the payload name this request or its character?
        No rule for the event: False (it cannot be told apart from the same event for another
        cause, so it never confirms a reply shape live)."""
        me = None if char == "observer" else char
        req = p["data"] if isinstance(p["data"], dict) else {}
        targets = {req[k] for k in TARGET_KEYS if isinstance(req.get(k), str)}
        d = data if isinstance(data, dict) else {}

        if ev in DEDICATED:
            return True
        if ev == "ping_ack":  # the handler echoes the payload
            return data == (p["data"] if p["data"] is not None else {})
        if ev == "action":  # our attack/heal on the requested target
            return (me is not None and d.get("attacker") == me and d.get("target") in targets
                    and p["event"] in (d.get("type"), d.get("source")))
        if ev == "hit":  # the projectile of our `action`
            return p["pid"] is not None and d.get("pid") == p["pid"] and d.get("hid") == me
        if ev == "skill_timeout":  # our cooldown of this skill (a stat change has `reason`)
            skill = "attack" if p["event"] in ("attack", "heal") else req.get("name") or p["event"]
            return "reason" not in d and d.get("name") == skill
        if ev == "player":  # our own update, on our socket
            return me is not None and d.get("id") == me
        if ev == "eval":  # the timer function the docs name ("pot_timeout(...)")
            code = d.get("code")
            for spec in self.cat.specs(sh, ev):
                ex = spec.get("example")
                fn = ex.get("code", "").split("(")[0] if isinstance(ex, dict) else None
                if fn and isinstance(code, str) and code.startswith(fn + "("):
                    return True
            return False
        if ev in ("game_log", "server_message", "disappearing_text", "game_chat"):
            phrases = self.cat.phrases(sh, ev)
            if isinstance(data, str):  # a bare-string game_log: the documented text itself
                return any(spec.get("example") == data for spec in self.cat.specs(sh, ev))
            if ev == "disappearing_text":
                # About us or our target; and the documented phrase, when the docs give one.
                if not ({d.get("id"), d.get("from")} & ({me} | targets) - {None}):
                    return False
                return phrase_ok(d.get("phrase"), phrases) if phrases else True
            if not phrase_ok(d.get("phrase"), phrases):
                return False
            if ev == "server_message":  # a broadcast: it must name us
                args = d.get("phrase_args") if isinstance(d.get("phrase_args"), dict) else {}
                return me is not None and me in (args.get("player"), d.get("name"))
            return True
        if ev in ("chat_log", "partym", "pm"):  # our own line, as sent
            return me is not None and d.get("owner") == me and d.get("message") == req.get("message")
        if ev == "cm":
            return me is not None and d.get("name") == me and d.get("message") == req.get("message")
        if ev == "chest_opened":  # the chest we opened
            return d.get("id") is not None and d.get("id") == req.get("id")
        if ev == "disappear":  # the entity we targeted, with the documented place and reason
            if d.get("id") not in targets:
                return False
            for spec in self.cat.specs(sh, ev):
                ex = spec.get("example") if isinstance(spec.get("example"), dict) else {}
                if "reason" in ex and d.get("reason") != ex["reason"]:
                    continue
                if "place" in ex and d.get("place") != p["event"]:
                    continue
                return True
            return False
        if ev == "ui":  # we are the actor, or the request's target is the subject
            return (me is not None and me in (d.get("name"), d.get("id"), d.get("from"))) \
                or (d.get("id") in targets)
        if ev in ("emote", "poke", "light"):
            return me is not None and d.get("name") == me
        if ev == "tavern":  # `info` goes to you only; bets and results go to the whole tavern
            return d.get("event") == "info" == req.get("event")
        if ev == "citizen":  # route_marks goes to the asker only
            return d.get("type") == "route_marks"
        if ev == "new_map":  # the map the request asked for (or the failure's fixed one: jail)
            names = {v for v in req.values() if isinstance(v, str)}
            if sh.kind == "failure":
                names |= {spec["example"].get("name") for spec in self.cat.specs(sh, ev)
                          if isinstance(spec.get("example"), dict)}
            return bool({d.get("name"), d.get("in")} & (names - {None}))
        if ev == "entities":
            if p["event"] == "loaded":  # the first frame of the new observer
                return d.get("type") == "all" and "entities" not in p["seen"]
            if p["event"] == "move":  # our entry with the destination we sent
                for e in d.get("players") or []:
                    if isinstance(e, dict) and e.get("id") == me and isinstance(e.get("going_x"), (int, float)) \
                            and isinstance(req.get("going_x"), (int, float)) \
                            and abs(e["going_x"] - req["going_x"]) < 1 and abs(e.get("going_y", 1e9) - req.get("going_y", 0)) < 1:
                        return True
            return False
        if ev == "game_error":
            # "ERROR!" names nothing. A throw is answered at once, in order; credit it only to
            # a probe that meant to make this handler throw, with no later request on the socket.
            return expected(sh.id, p["expect"]) and self.pending.get(char, [None])[-1] is p
        return False


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbose = "-v" in sys.argv
    paths = args or sorted(glob.glob(str(ROOT / "captures" / "**" / "*.jsonl"), recursive=True))
    if not paths:
        sys.exit("no captures (run tools/capture/run.py first)")
    schema = apischema.Schema()
    cat = Catalog(schema)
    tally = Tally()
    m = Matcher(cat, tally)
    frames = 0
    for p, recs in load(paths):
        frames += sum(1 for r in recs if r.get("k") == "frame")
        m.pending.clear()
        m.expect.clear()
        m.run(recs)

    shapes = {}
    for sid in sorted(tally.shapes):
        e = tally.shapes[sid]
        if sid not in cat.shapes:
            continue
        shapes[sid] = {k: v for k, v in e.items() if not (k == "sample" and v is None)}
    out = {
        "_comment": "Generated by scripts/check-captures.py from git-ignored captures/*.jsonl (tools/capture). Do not edit.",
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "server": SERVER,
        "captures": len(paths),
        "frames": frames,
        "shapes": shapes,
        "unmatched": tally.unmatched,
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")

    # Report.
    capturable = [sid for sid, sh in cat.shapes.items() if not sh.sends_nothing]
    confirmed = [sid for sid, e in shapes.items() if e.get("count")]
    mism = {sid: e for sid, e in shapes.items() if e.get("mismatches")}
    print(f"{len(paths)} capture file(s), {frames} frames")
    print(f"shapes: {len(cat.shapes)} documented, {len(capturable)} capturable, "
          f"{len(confirmed)} confirmed live, {len(mism)} with mismatches")
    for kind in ("request", "response", "failure", "also", "payload", "variant", "type"):
        allk = [s for s in cat.shapes.values() if s.kind == kind]
        ck = [s for s in allk if s.id in confirmed]
        print(f"  {kind:9} {len(ck):4} / {len(allk)}")
    sends = sorted({sid.split("/")[1] for sid in confirmed if sid.startswith("send/")})
    print(f"send events with a confirmed shape: {len(sends)} / {len(schema.send)}")
    if mism:
        print("\nMISMATCHES (payload differs from the docs):")
        for sid, e in mism.items():
            print(f"  {sid}  ({e.get('mismatch_count', 0)} frame(s), {e.get('count', 0)} ok)")
            for x in e["mismatches"]:
                print(f"      {x['kind']:10} {x['path']}: {x['problem']}")
    gaps = tally.unmatched
    if any(gaps.values()):
        print("\nUNMATCHED (the docs do not know these):")
        for kind, d in gaps.items():
            for k, x in sorted(d.items()):
                print(f"  {kind:18} {k}  x{x['count']}  e.g. {short(x['sample'], 140)}")
    if verbose:
        print("\nconfirmed:")
        for sid in confirmed:
            print(f"  {sid}  x{shapes[sid]['count']}")
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
