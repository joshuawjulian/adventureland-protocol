"""
The machine-readable API schema (schema/*.json) and what is made from it.

    schema/types.json        shared named types (EntityId, ItemInstance, Character, ...)
    schema/send/<event>.json one client -> server event: request, responses, failures, also-sent
    schema/recv/<event>.json one server -> client event: payload, variants, senders

build.py imports this module to (1) check the schema, (2) expand the `<!-- schema -->` marker of
an entry in content/*.md into its Request / Responses / Also sent sections, (3) make one guide
entry per type, and (4) list, on each response-code entry, the requests that send it.
scripts/gen-types.py uses it to write typed definitions: `model()` walks the schema into
declarations, `typescript()` renders them (the other languages are in scripts/gen-types.py).

The format is described in docs/WRITING.md, "The schema". Python 3 standard library only, like
build.py: the host has no other toolchain (see CLAUDE.md).
"""

import json
import sys
import os
import re
from pathlib import Path

ROOT = Path(__file__).parent
SCHEMA = ROOT / "schema"

# ---------------------------------------------------------------------------------------------
# Type expressions
#
# A field's "type" is a small TypeScript-like expression, so that one string is readable in a
# table and maps directly onto every target language:
#   string integer number boolean null any object true false    primitives
#   "buy"  0  1                                                    literal values
#   ItemName                                                       a named type (schema/types.json)
#   T[]   [A, B]   Record<string, T>   A | B   (A | B)[]           array, tuple, map, union, group
# ---------------------------------------------------------------------------------------------

PRIMS = {"string", "integer", "number", "boolean", "null", "any", "object"}
# What each primitive accepts (Python's json: a JSON number with no fraction is an int; bool is a
# subclass of int, so it is ruled out by hand). `any` accepts everything.
PRIM_OK = {"string": lambda v: isinstance(v, str),
           "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
           "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
           "boolean": lambda v: isinstance(v, bool),
           "null": lambda v: v is None,
           "object": lambda v: isinstance(v, dict)}
_TOKEN = re.compile(r'\s*(?:("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?)|(\[\])|([A-Za-z_][A-Za-z0-9_]*)|(\S))')


def _tokens(text):
    pos, out = 0, []
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ValueError(f"bad type expression: {text!r}")
        pos = m.end()
        s, n, arr, ident, ch = m.groups()
        if s is not None:
            out.append(("lit", json.loads(s)))
        elif n is not None:
            out.append(("lit", json.loads(n)))
        elif arr:
            out.append(("op", "[]"))
        elif ident:
            out.append(("id", ident))
        elif ch:
            out.append(("op", ch))
    return out


def parse_type(text):
    """Parses a type expression into a tuple tree: ("prim", name), ("lit", value), ("ref", name),
    ("array", t), ("tuple", [t...]), ("record", t), ("union", [t...])."""
    toks = _tokens(text)
    i = 0

    def peek(v=None):
        if i < len(toks) and (v is None or toks[i][1] == v):
            return toks[i]
        return None

    def take(v):
        nonlocal i
        if not peek(v):
            raise ValueError(f"expected {v!r} in type {text!r}")
        i += 1

    def union():
        parts = [postfix()]
        while peek("|"):
            take("|")
            parts.append(postfix())
        return parts[0] if len(parts) == 1 else ("union", parts)

    def postfix():
        t = primary()
        while peek("[]"):
            take("[]")
            t = ("array", t)
        return t

    def primary():
        nonlocal i
        if i >= len(toks):
            raise ValueError(f"type {text!r} ends early")
        kind, v = toks[i]
        if kind == "lit":
            i += 1
            return ("lit", v)
        if kind == "id":
            i += 1
            if v == "true" or v == "false":
                return ("lit", v == "true")
            if v == "Record":
                take("<")
                key = union()
                if key != ("prim", "string"):
                    raise ValueError(f"Record keys must be string in {text!r}")
                take(",")
                val = union()
                take(">")
                return ("record", val)
            return ("prim", v) if v in PRIMS else ("ref", v)
        if v == "(":
            take("(")
            t = union()
            take(")")
            return t
        if v == "[":
            take("[")
            items = [union()]
            while peek(","):
                take(",")
                items.append(union())
            take("]")
            return ("tuple", items)
        raise ValueError(f"unexpected {v!r} in type {text!r}")

    tree = union()
    if i != len(toks):
        raise ValueError(f"trailing text in type {text!r}")
    return tree


def refs_of(tree):
    kind = tree[0]
    if kind == "ref":
        yield tree[1]
    elif kind in ("array", "record"):
        yield from refs_of(tree[1])
    elif kind in ("tuple", "union"):
        for t in tree[1]:
            yield from refs_of(t)




def lit_union(values):
    """A type expression for exactly these literal values: ["a", "b"] -> '"a" | "b"'."""
    return " | ".join(json.dumps(v) for v in values)


def as_list(value):
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def strict():
    """ALAPI_STRICT_TYPES=1 (the final check) turns the warnings of the schema into errors."""
    return bool(os.environ.get("ALAPI_STRICT_TYPES"))


def strict_confirm():
    """ALAPI_STRICT_CONFIRM=1 fails when a shape has no `confirm`, a citation of one is wrong, or
    schema/live.json lists mismatches. It is apart from ALAPI_STRICT_TYPES while the `confirm`
    keys are being filled in (2026-10-04); fold it into ALAPI_STRICT_TYPES once they are."""
    return bool(os.environ.get("ALAPI_STRICT_CONFIRM"))


def confirm_warn(msg):
    """A problem of the confirmation data: a warning, fatal under ALAPI_STRICT_CONFIRM=1."""
    if strict_confirm():
        raise SystemExit(msg)
    print(f"warning: {msg}", file=sys.stderr)


def _fail(msg):
    raise SystemExit(msg)


def warn(msg):
    if strict():
        raise SystemExit(msg)
    print(f"warning: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------------------------
# The keys of each part of a schema file. A key that starts with "_" is a comment. Any other key
# that is not here is a typo, or a format that this module does not know (and so would silently
# leave off the page and out of the types): a warning, fatal under ALAPI_STRICT_TYPES=1.
# docs/WRITING.md, "The schema", describes every key.
# ---------------------------------------------------------------------------------------------

_SHAPE = {"fields", "extends", "type", "open", "summary", "example", "example_trimmed"}
_CODE = {"code", "codes", "code_type"}
# `confirm` (docs/WRITING.md, "Confirmation") sits on every object that is one shape: a request
# (top level or of a variant), a response and each of its `request_id` forms, a failure row, an
# `also` entry, a receive payload and each of its variants, and a named type.
_CONFIRM = {"confirm"}
KEYS = {
    "send": {"event", "source", "types", "trigger", "request", "variants", "responses",
             "failures", "also", "order"},
    "request": {"fields", "others", "example", "note", "type"} | _CONFIRM,
    "variants": {"key", "intro", "list"},
    "variant": {"name", "value", "other", "match", "when", "request", "same_as", "place",
                "responses", "failures", "also", "order", "source"},
    "response": {"name", "event", "when", "via", "kind", "source", "note",
                 "with_request_id", "without_request_id"} | _SHAPE | _CODE | _CONFIRM,
    "response_form": {"event", "via", "kind", "note", "none"} | _SHAPE | _CODE | _CONFIRM,
    "failures": {"event", "place", "place_from", "intro", "rows"},
    "row": {"when", "source", "replies", "branch", "form", "extra", "event", "example", "place",
            "note", "close", "see", "with_request_id", "without_request_id"} | _CODE | _CONFIRM,
    "reply": {"form", "extra", "event", "example", "place", "note", "close", "see",
              "with_request_id", "without_request_id", "source"} | _CODE,
    "reply_form": {"form", "extra", "event", "example", "place", "note", "close", "see",
                   "none"} | _CODE,
    "also": {"name", "event", "to", "when", "source", "no_entry", "via"} | _SHAPE | _CODE | _CONFIRM,
    "recv": {"event", "to", "payload", "example", "example_trimmed", "variants", "senders",
             "types"},
    "payload": {"fields", "extends", "type", "open"} | _CONFIRM,
    "recv_variant": {"name", "type", "when", "example", "example_trimmed", "source", "has",
                     "reply_to"} | _CONFIRM,
    "sender": {"what", "source"},
    "field": {"name", "type", "description", "optional", "default", "coerce", "example"},
    "type": {"summary", "type", "fields", "extends", "open", "description", "example",
             "example_trimmed", "source"} | _CONFIRM,
    "confirm": {"code", "note", "live_needed"},
}

# The two reply forms that depend on `request_id` (docs/WRITING.md, "Replies that depend on
# request_id"): each is a reply of its own, or {"none": true} when the server sends nothing.
FORMS = (("with_request_id", "With `request_id`"), ("without_request_id", "Without `request_id`"))
# What a form takes from the reply around it when it does not say otherwise.
INHERIT = ("event", "code", "codes", "code_type", "place", "via")


def forms(item):
    """The forms of a response or a failure reply: [(label, spec)], with label None for a reply
    that does not depend on `request_id`, and spec None for "the server sends nothing"."""
    if not any(k in item for k, _ in FORMS):
        return [(None, item)]
    out = []
    for key, label in FORMS:
        f = item.get(key)
        if f is None or f.get("none"):
            out.append((label, None))
            continue
        spec = {k: item[k] for k in INHERIT if k in item}
        spec.update(f)
        out.append((label, spec))
    return out


def codes_of(item):
    """The response codes a reply can carry: `codes` (a list), else `code`."""
    return as_list(item.get("codes")) or as_list(item.get("code"))


def code_type_of(item):
    """The type expression of the `response` value of a reply."""
    if item.get("code_type"):
        return item["code_type"]
    return lit_union(codes_of(item))


def variant_values(v):
    return as_list(v.get("value"))


def variant_list(s):
    """The request variants of a send schema (empty for an event without variants)."""
    v = s.get("variants")
    return v.get("list", []) if isinstance(v, dict) else []


def variant_title(s, v):
    key = s["variants"]["key"]
    vals = variant_values(v)
    if vals:
        return ", ".join(f'`{key}: {json.dumps(x)}`' for x in vals)
    if v.get("other"):
        return f"any other `{key}`"
    return v.get("name", "?")


def variant_name(v):
    """The name of a variant: `name`, else its first value."""
    if v.get("name"):
        return v["name"]
    vals = variant_values(v)
    return str(vals[0]) if vals else "Other"


# ---------------------------------------------------------------------------------------------
# Shape ids (docs/WRITING.md, "Confirmation"). A shape is one documented payload: a request, a
# reply, a failure row, an also-sent event, a receive payload or one of its forms, a named type.
# Its id is a stable string that schema/live.json (written by the live-capture tool) and the
# `confirm` checks use. `shape_id` is the only place that builds one; keep it that way, because
# the ids of live.json must match these exactly.
#
#   send/<event>/request                      send/<event>/variant/<v>/request
#   send/<event>/response/<name>[#with|#without]
#   send/<event>/variant/<v>/response/<name>[#with|#without]
#   send/<event>/failure/<n>                  send/<event>/variant/<v>/failure/<n>
#   send/<event>/also/<i>                     send/<event>/variant/<v>/also/<i>
#   recv/<event>/payload                      recv/<event>/variant/<name, else 1-based index>
#   type/<TypeName>
#
# <v> is `variant_id`: the first `value` of the variant (a string as is, other values as JSON:
# `true`), else its `name`. <n> counts every failure row of the table, 1-based in schema order,
# so it is the # column of the page; a `branch` row has a number but is no shape. <i> is 1-based.
# ---------------------------------------------------------------------------------------------

# The two request_id forms of a reply, as the suffix of its id.
FORM_SUFFIX = {"with_request_id": "with", "without_request_id": "without"}


def variant_id(v):
    """The <v> of a variant in a shape id: its first value, else its name."""
    vals = variant_values(v)
    if vals:
        return vals[0] if isinstance(vals[0], str) else json.dumps(vals[0])
    return variant_name(v)


def shape_id(section, event=None, part=None, key=None, variant=None, form=None):
    """The id of one shape.

    section: "send", "recv" or "type".
    send: part is "request", "response", "failure" or "also"; key is the response name, the
          1-based row number or the 1-based also index (none for "request"); variant is the
          `variant_id` (None for the shared part); form is "with" / "without" for one
          request_id form of a response.
    recv: part is "payload" or "variant"; key is the variant's name (or 1-based index).
    type: key is the type name.

        shape_id("send", "buy", "failure", 2)                  -> "send/buy/failure/2"
        shape_id("send", "upgrade", "request", variant="true") -> "send/upgrade/variant/true/request"
        shape_id("recv", "game_response", "variant", "Failure")-> "recv/game_response/variant/Failure"
        shape_id("type", key="ItemInstance")                   -> "type/ItemInstance"
    """
    if section == "type":
        return f"type/{key}"
    if section == "recv":
        return f"recv/{event}/payload" if part == "payload" else f"recv/{event}/variant/{key}"
    if section != "send" or part not in ("request", "response", "failure", "also"):
        raise ValueError(f"no shape id for {section}/{part}")
    base = f"send/{event}" + (f"/variant/{variant}" if variant is not None else "")
    out = f"{base}/request" if part == "request" else f"{base}/{part}/{key}"
    return out + (f"#{form}" if form else "")


# ---------------------------------------------------------------------------------------------
# Loading and checking
# ---------------------------------------------------------------------------------------------


class Schema:
    def __init__(self, root=SCHEMA):
        self.types = json.loads((root / "types.json").read_text())["types"]
        self.local = {}  # type name -> the file that defines it (for event-local types)
        self.send = {}
        self.recv = {}
        for kind, store in (("send", self.send), ("recv", self.recv)):
            for f in sorted((root / kind).glob("*.json")):
                spec = json.loads(f.read_text())
                spec["_file"] = f"schema/{kind}/{f.name}"
                spec["_kind"] = kind
                if spec.get("event") is None:
                    raise SystemExit(f"{spec['_file']}: no \"event\"")
                store[spec["event"]] = spec
                # An event file may define types that only it uses; they join the global names.
                for name, t in spec.get("types", {}).items():
                    if name in self.types:
                        # Two definitions of one name: the second is ignored. While event files
                        # are written in parallel this can happen; ALAPI_STRICT_TYPES=1 (the
                        # final check) makes it fatal, also for identical copies.
                        msg = f"{spec['_file']}: type {name} is already defined"
                        if strict():
                            raise SystemExit(msg)
                        if self.types[name] != t:
                            print(f"warning: {msg} differently; kept the first", file=sys.stderr)
                        continue
                    self.types[name] = t
                    self.local[name] = spec["_file"]
        # Gaps that the checks collect, to list all of them at once (fatal under
        # ALAPI_STRICT_TYPES=1): a reply or payload without a literal example, a field without
        # an explicit "optional" (docs/WRITING.md, "The schema": "Every shape has an example"
        # and "Every field says optional or not").
        self.gaps = {"example": [], "optional": []}
        self.check()
        self.report_gaps()
        # Confirmation (docs/WRITING.md, "Confirmation"): the `confirm` keys, and the captures
        # of schema/live.json (absent until the live-capture tool writes it).
        self.live = load_live(root)
        self.check_confirm()

    # -- checks ---------------------------------------------------------------------------------

    def _keys(self, where, kind, obj):
        if not isinstance(obj, dict):
            raise SystemExit(f"{where}: expected an object for {kind}")
        bad = [k for k in obj if not k.startswith("_") and k not in KEYS[kind]]
        if bad:
            warn(f"{where}: unknown {kind} keys {bad}")

    def _check_type(self, where, text):
        try:
            tree = parse_type(text)
        except ValueError as e:
            raise SystemExit(f"{where}: {e}")
        for r in refs_of(tree):
            if r not in self.types:
                raise SystemExit(f"{where}: unknown type {r} in {text!r}")
        return tree

    def all_fields(self, spec):
        """The fields of an object spec, with the fields of its `extends` base first. A field in
        the spec replaces the base field of the same name (for example a literal `place`)."""
        base = []
        if spec.get("extends"):
            base = self.all_fields(self.types[spec["extends"]])
        own = spec.get("fields", [])
        names = {f["name"] for f in own}
        return [f for f in base if f["name"] not in names] + own

    def is_open(self, spec):
        return spec.get("open") or (spec.get("extends") and self.is_open(self.types[spec["extends"]]))

    def _check_fields(self, where, fields):
        names = [f.get("name") for f in fields]
        if len(set(names)) != len(names):
            raise SystemExit(f"{where}: a field name is twice in one table: {names}")
        for f in fields:
            self._keys(f"{where}.{f.get('name')}", "field", f)
            for k in ("name", "type", "description"):
                if k not in f:
                    raise SystemExit(f"{where}: field {f.get('name')} has no \"{k}\"")
            self._check_type(f"{where}.{f['name']}", f["type"])
            # Required or optional is a fact of the handler, not a default: every field says it.
            if not isinstance(f.get("optional"), bool):
                self.gaps["optional"].append(f"{where}.{f['name']}")

    def _check_example(self, where, spec, example, trimmed=False, soft=True):
        """A literal example must use only declared fields (unless the object is open) and must
        have every field that is not optional, unless it says `"example_trimmed": true` (for
        payloads with dozens of fields)."""
        trimmed = trimmed or spec.get("example_trimmed")
        if not isinstance(example, dict) or not spec.get("fields") and not spec.get("extends"):
            return
        fields = self.all_fields(spec)
        names = {f["name"] for f in fields}
        if not self.is_open(spec):
            extra = set(example) - names
            if extra:
                raise SystemExit(f"{where}: example has undeclared fields {sorted(extra)}")
        missing = [f["name"] for f in fields if not f.get("optional") and f["name"] not in example]
        if missing and not trimmed:
            raise SystemExit(f"{where}: example lacks required fields {missing}")
        # Literal fields must hold their literal (a wrong `response` or `place` is a real error).
        for f in fields:
            tree = parse_type(f["type"])
            if f["name"] in example and tree[0] == "lit" and example[f["name"]] != tree[1]:
                (warn if soft else _fail)(f"{where}: example {f['name']} is {example[f['name']]!r}, but its "
                                 f"type is the literal {tree[1]!r}")

    def check_value(self, where, text, value, trimmed=False):
        """Checks a literal example against a type expression, as far as the shapes go: named
        object types (and arrays and records of them) are checked field by field; literal
        types must match; unions pass when one member passes. A mismatch is a warning, fatal
        under ALAPI_STRICT_TYPES=1."""
        try:
            self._match(where, parse_type(text), value, trimmed, raise_=True)
        except SystemExit as e:
            warn(str(e))

    def _match(self, where, tree, value, trimmed, raise_=False):
        kind = tree[0]
        try:
            if kind == "lit":
                if value != tree[1]:
                    raise SystemExit(f"{where}: {value!r} is not {tree[1]!r}")
            elif kind == "prim":
                if not PRIM_OK.get(tree[1], lambda v: True)(value):
                    raise SystemExit(f"{where}: {value!r} is not a {tree[1]}")
            elif kind == "ref":
                t = self.types[tree[1]]
                if "type" in t:
                    self._match(where, parse_type(t["type"]), value, trimmed, True)
                elif not isinstance(value, dict):
                    raise SystemExit(f"{where}: {str(value)[:60]!r} is not an object ({tree[1]})")
                else:
                    self._check_example(f"{where} ({tree[1]})", t, value, trimmed, soft=False)
            elif kind == "array":
                if not isinstance(value, list):
                    raise SystemExit(f"{where}: {str(value)[:60]!r} is not an array")
                for i, x in enumerate(value):
                    self._match(f"{where}[{i}]", tree[1], x, trimmed, True)
            elif kind == "record":
                if not isinstance(value, dict):
                    raise SystemExit(f"{where}: {str(value)[:60]!r} is not an object")
                for k, x in value.items():
                    self._match(f"{where}.{k}", tree[1], x, trimmed, True)
            elif kind == "tuple":
                if not isinstance(value, list) or len(value) != len(tree[1]):
                    raise SystemExit(f"{where}: {str(value)[:60]!r} is not a {len(tree[1])}-tuple")
                for i, (t, x) in enumerate(zip(tree[1], value)):
                    self._match(f"{where}[{i}]", t, x, trimmed, True)
            elif kind == "union":
                errors = []
                for t in tree[1]:
                    try:
                        self._match(where, t, value, trimmed, True)
                        return True
                    except SystemExit as e:
                        errors.append(str(e))
                raise SystemExit(f"{where}: {str(value)[:80]!r} matches no member of the union: "
                                 + " / ".join(errors[:4]))
            return True
        except SystemExit:
            if raise_:
                raise
            return False

    def _check_shape(self, w, r):
        """A response, a form of one, or an `also` entry: its fields, type and example."""
        if r.get("extends"):
            self._check_type(w, r["extends"])
        if r.get("type"):
            self._check_type(w, r["type"])
        self._check_fields(w, r.get("fields", []))
        if "example" in r:
            if r.get("fields") or r.get("extends"):
                self._check_example(w, r, r["example"])
            elif r.get("type"):
                self.check_value(f"{w} example", r["type"], r["example"], r.get("example_trimmed"))
            elif r.get("event") in self.recv:
                # A reply with only a `summary` (a `player` update, `new_map`, `start`): its
                # example is checked against the payload of the receive schema of its event.
                p = self.recv[r["event"]].get("payload", {})
                if p.get("fields") or p.get("extends"):
                    self._check_example(f"{w} example", p, r["example"], r.get("example_trimmed"))
                elif p.get("type"):
                    self.check_value(f"{w} example", p["type"], r["example"], r.get("example_trimmed"))

    def _check_response(self, w, r, also=False):
        self._keys(w, "also" if also else "response", r)
        if r.get("kind") not in (None, "none", "close"):
            raise SystemExit(f"{w}: kind is \"none\" (no reply) or \"close\" (the server closes the "
                             f"socket), not {r.get('kind')!r}")
        if "when" not in r:
            raise SystemExit(f"{w}: no \"when\"")
        if also and "to" not in r:
            raise SystemExit(f"{w}: no \"to\"")
        fs = forms(r)
        if fs[0][0] is not None and not all(k in r for k, _ in FORMS):
            raise SystemExit(f"{w}: give both \"with_request_id\" and \"without_request_id\" "
                             f"(one can be {{\"none\": true}})")
        for label, spec in fs:
            if spec is None:
                continue
            wf = f"{w} ({label})" if label else w
            if label:
                self._keys(wf, "response_form", r[FORMS[0][0] if label == FORMS[0][1] else FORMS[1][0]])
            if spec.get("kind"):
                continue
            if "event" not in spec:
                raise SystemExit(f"{wf}: no \"event\"")
            if not (spec.get("fields") or spec.get("type") or spec.get("summary") or spec.get("extends")):
                raise SystemExit(f"{wf}: give \"fields\", \"extends\", \"type\" or \"summary\"")
            if not also and "example" not in spec:
                self.gaps["example"].append(f"{wf}: no \"example\" (on {spec['event']})")
            self._check_shape(wf, spec)

    def _check_reply(self, w, rep, names):
        self._keys(w, "reply", rep)
        fs = forms(rep)
        if fs[0][0] is not None and not all(k in rep for k, _ in FORMS):
            raise SystemExit(f"{w}: give both \"with_request_id\" and \"without_request_id\"")
        for label, spec in fs:
            if spec is None:
                continue
            wf = f"{w} ({label})" if label else w
            if label:
                self._keys(wf, "reply_form", rep[FORMS[0][0] if label == FORMS[0][1] else FORMS[1][0]])
            if spec.get("see") and spec["see"] not in names:
                raise SystemExit(f"{wf}: \"see\" names no response: {spec['see']!r} (have {names})")
            if spec.get("close") or spec.get("see"):
                continue
            form = spec.get("form", "failure")
            if form not in ("failure", "bare", "plain", "object"):
                raise SystemExit(f"{wf}: unknown form {form}")
            if spec.get("event") and spec["event"] != "game_response":
                if "example" not in spec:
                    raise SystemExit(f"{wf}: a reply on {spec['event']} needs an \"example\"")
                continue
            if form != "object" and not codes_of(spec):
                raise SystemExit(f"{wf}: no \"code\" (or \"codes\")")
            if spec.get("code_type"):
                self._check_type(wf, spec["code_type"])
            self._check_fields(wf, spec.get("extra", []))

    def _check_request(self, where, req, others_ok=True):
        self._keys(where, "request", req)
        if req.get("type"):
            self._check_type(where, req["type"])
            if req.get("fields"):
                raise SystemExit(f"{where}: give \"fields\" (an object) or \"type\" (another value), "
                                 f"not both")
            if "example" in req and req["example"] is not None:
                self.check_value(f"{where} example", req["type"], req["example"])
            return
        self._check_fields(where, req.get("fields", []))

    def check(self):
        for name, t in self.types.items():
            where = f"type {name}"
            self._keys(where, "type", t)
            if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", name):
                raise SystemExit(f"{where}: type names are PascalCase")
            if "summary" not in t:
                raise SystemExit(f"{where}: no \"summary\"")
            if "type" in t:
                self._check_type(where, t["type"])
                if "example" in t:
                    self.check_value(f"{where} example", t["type"], t["example"], t.get("example_trimmed"))
            else:
                if t.get("extends"):
                    self._check_type(where, t["extends"])
                    if "type" in self.types[t["extends"]]:
                        raise SystemExit(f"{where}: extends {t['extends']}, which is not an object type")
                self._check_fields(where, t.get("fields", []))
                if "example" in t:
                    self._check_example(where, t, t["example"])
        for ev, s in self.send.items():
            self._check_send(ev, s)
        for ev, s in self.recv.items():
            self._check_recv(ev, s)

    def _check_send(self, ev, s):
        where = s["_file"]
        self._keys(where, "send", s)
        req = s.get("request")
        if req is None:
            raise SystemExit(f"{where}: no \"request\" (use {{\"fields\": []}} for no payload)")
        self._check_request(f"{where} request", req)
        if req.get("fields"):
            if "example" not in req:
                raise SystemExit(f"{where}: the request has fields but no \"example\"")
            if variant_list(s):
                # The Send line of an event with variants shows one whole payload: it must fit
                # one of the variants (not only the shared fields).
                errs = []
                for v in variant_list(s):
                    full = self.variant_request(s, v)
                    if full.get("type"):
                        continue
                    try:
                        self._check_example(f"{where} request", full, req["example"], soft=False)
                        errs = None
                        break
                    except SystemExit as e:
                        errs.append(str(e))
                if errs:
                    warn(f"{where}: the request example fits no variant: {errs[0]}")
            else:
                self._check_example(f"{where} request", req, req["example"])
        # Every response name is unique in the event, variants too: each names a type.
        names = [r.get("name", "Reply") for _, part in self.parts(s) for r in part.get("responses", [])]
        if len(set(names)) != len(names) or "Failure" in names:
            raise SystemExit(f"{where}: response names must be unique in the event (variants too), "
                             f"and \"Failure\" is taken by the failures (it names the type "
                             f"{pascal(ev)}Failure): {names}")
        fail = s.get("failures", {})
        if fail:
            self._keys(f"{where} failures", "failures", fail)
        if fail.get("place_from"):
            if fail["place_from"] not in {f["name"] for f in req.get("fields", [])}:
                raise SystemExit(f"{where}: place_from names no request field: {fail['place_from']}")
        vs = s.get("variants")
        if vs is not None:
            self._keys(f"{where} variants", "variants", vs)
            key = vs.get("key")
            kf = next((f for f in req.get("fields", []) if f["name"] == key), None)
            if kf is None:
                raise SystemExit(f"{where}: variants.key {key!r} is not a request field")
            ktree = parse_type(kf["type"])
            allowed = None
            if ktree[0] == "lit":
                allowed = {ktree[1]}
            elif ktree[0] == "union" and all(t[0] == "lit" for t in ktree[1]):
                allowed = {t[1] for t in ktree[1]}
            vnames = [variant_name(v) for v in variant_list(s)]
            if len(set(vnames)) != len(vnames):
                raise SystemExit(f"{where}: variant names must be unique: {vnames}")
            seen = set()
            for v in variant_list(s):
                w = f"{where} variant {variant_name(v)}"
                self._keys(w, "variant", v)
                if "when" not in v:
                    raise SystemExit(f"{w}: no \"when\"")
                vals = variant_values(v)
                if not vals and not v.get("other") and not v.get("match") and not v.get("request", {}).get("type"):
                    raise SystemExit(f"{w}: give \"value\", \"other\": true, \"match\" or a "
                                     f"request \"type\"")
                for x in vals:
                    if allowed is not None and x not in allowed:
                        raise SystemExit(f"{w}: value {x!r} is not in the type of `{key}`: {kf['type']}")
                    if x in seen:
                        raise SystemExit(f"{w}: value {x!r} is in two variants")
                    seen.add(x)
                if v.get("same_as") and v["same_as"] not in vnames:
                    raise SystemExit(f"{w}: same_as names no variant: {v['same_as']}")
                vr = v.get("request", {})
                self._check_request(f"{w} request", vr)
                if vr.get("fields") and "example" not in vr:
                    raise SystemExit(f"{w}: the variant has request fields but no \"example\"")
                if "example" in vr and not vr.get("type"):
                    full = self.variant_request(s, v)
                    self._check_example(f"{w} request", full, vr["example"])
                    if vals and vr["example"].get(key) not in vals:
                        raise SystemExit(f"{w}: the example's {key} is not one of {vals}")
                if v.get("failures"):
                    self._keys(f"{w} failures", "failures", v["failures"])
        elif "variants" in req or "discriminator" in req:
            warn(f"{where}: request variants go in a top-level \"variants\" "
                 f"({{key, list}}), docs/WRITING.md")
        for part_v, part in self.parts(s):
            pw = where if part_v is None else f"{where} variant {variant_name(part_v)}"
            for r in part.get("responses", []):
                self._check_response(f"{pw} {r.get('name')}", r)
            for a in part.get("also", []):
                self._check_response(f"{pw} also {a.get('event')}", a, also=True)
            o = part.get("order")
            if o is not None and not isinstance(o, (list, dict)):
                raise SystemExit(f"{pw}: order is a list, or an object of lists (one per path)")
            for row in part.get("failures", {}).get("rows", []):
                w = f"{pw} failure {row.get('when', '')[:40]!r}"
                self._keys(w, "row", row)
                if "when" not in row:
                    raise SystemExit(f"{w}: no \"when\"")
                if row.get("branch"):
                    if part_v is not None:
                        raise SystemExit(f"{w}: a branch row is only for the shared failures")
                    continue
                for rep in self.replies(row):
                    self._check_reply(w, rep, names)

    def _check_recv(self, ev, s):
        where = s["_file"]
        self._keys(where, "recv", s)
        p = s.get("payload", {})
        self._keys(f"{where} payload", "payload", p)
        if p.get("type"):
            self._check_type(where, p["type"])
        if p.get("extends"):
            self._check_type(where, p["extends"])
        self._check_fields(f"{where} payload", p.get("fields", []))
        if "example" in s:
            if p.get("fields") or p.get("extends"):
                self._check_example(f"{where} example", p, s["example"], s.get("example_trimmed"))
            elif p.get("type"):
                self.check_value(f"{where} example", p["type"], s["example"], s.get("example_trimmed"))
        if "example" not in s and not s.get("variants"):
            self.gaps["example"].append(f"{where}: the payload has no \"example\"")
        for x in s.get("senders", []):
            self._keys(f"{where} sender", "sender", x)
        for v in s.get("variants", []):
            w = f"{where} variant {v.get('name')}"
            self._keys(w, "recv_variant", v)
            self._check_type(w, v["type"])
            if "example" not in v:
                self.gaps["example"].append(f"{w}: no \"example\"")
            if "example" in v:
                self.check_value(f"{w} example", v["type"], v["example"], v.get("example_trimmed"))

    def report_gaps(self):
        """Lists every gap that the checks found. Under ALAPI_STRICT_TYPES=1 any gap fails the
        build; otherwise it is one warning per kind of gap."""
        what = {"example": "replies or payloads without a literal example",
                "optional": "fields without an explicit \"optional\": true or false"}
        msgs = [f"{len(v)} {what[k]}:\n  " + "\n  ".join(v) for k, v in self.gaps.items() if v]
        if not msgs:
            return
        if strict():
            raise SystemExit("schema gaps (ALAPI_STRICT_TYPES=1):\n" + "\n".join(msgs))
        for k, v in self.gaps.items():
            if v:
                print(f"warning: {len(v)} {what[k]} (ALAPI_STRICT_TYPES=1 lists them)", file=sys.stderr)

    # -- confirmation ---------------------------------------------------------------------------
    # docs/WRITING.md, "Confirmation". Every shape (see shape_id) carries `confirm`: the exact
    # lines of the live code that build it (`code`), or what the code cannot settle
    # (`live_needed`). schema/live.json adds what live captures saw. Missing keys and live
    # mismatches are listed here; ALAPI_STRICT_CONFIRM=1 makes them fatal.

    def check_confirm(self):
        self._shapes, self._by_id = [], {}
        for sh in self._walk_shapes():
            if sh.id in self._by_id:
                confirm_warn(f"{sh.where}: the shape id {sh.id} is taken already by "
                             f"{self._by_id[sh.id].where}; give the two different names")
                continue
            self._by_id[sh.id] = sh
            self._shapes.append(sh)
            if sh.confirm is not None:
                _check_confirm(sh.where, sh.confirm)
        missing = [sh for sh in self._shapes if sh.confirm is None]
        live = (self.live or {}).get("shapes", {})
        for sid, rec in live.items():
            if sid in self._by_id:
                self._by_id[sid].live = rec
        unknown = sorted(set(live) - set(self._by_id))
        mism = [sh for sh in self._shapes if sh.live and sh.live.get("mismatches")]
        if unknown:
            # Stale captures (a shape was renamed or removed): a warning only; the next run of
            # the capture check rewrites live.json.
            print(f"warning: schema/live.json has {len(unknown)} shape ids that the schema does "
                  f"not have: {', '.join(unknown[:5])}{' ...' if len(unknown) > 5 else ''}",
                  file=sys.stderr)
        if strict_confirm() and (missing or mism):
            lines = [f"  {sh.id}  ({sh.file})" for sh in missing]
            lines += [f"  {sh.id}: {mismatch_text(m)[:200]}" for sh in mism for m in sh.live["mismatches"][:3]]
            raise SystemExit(f"confirmation gaps (ALAPI_STRICT_CONFIRM=1): {len(missing)} shapes "
                             f"without \"confirm\", {len(mism)} shapes with live mismatches:\n"
                             + "\n".join(lines))
        if missing:
            print(f"warning: {len(missing)} of {len(self._shapes)} shapes have no \"confirm\" "
                  f"(python3 scripts/confirm-report.py lists them)", file=sys.stderr)
        if mism:
            print(f"warning: {len(mism)} shapes have mismatches in schema/live.json "
                  f"(python3 scripts/confirm-report.py lists them)", file=sys.stderr)

    def shapes(self):
        """Every shape, in page order: each event you send (request, responses, failures, also;
        the shared part, then each variant), each event you receive, each named type."""
        return list(self._shapes)

    def shape(self, sid):
        """The Shape with this id, or None."""
        return self._by_id.get(sid)

    def _walk_shapes(self):
        for ev, s in self.send.items():
            f = s["_file"]
            for v, part in self.parts(s):
                vid = None if v is None else variant_id(v)
                at = f if v is None else f"{f} variant {variant_name(v)}"
                # The request. The shared request of an event with variants is checked against
                # each variant's whole request (one must fit).
                if v is None:
                    req = s["request"]
                    target = (("variants", s) if variant_list(s) else _request_target(req))
                else:
                    req = v.get("request") or {}
                    full = self.variant_request(s, v)
                    target = ("type", full["type"]) if full.get("type") else ("object", full)
                yield Shape(self, shape_id("send", ev, "request", variant=vid), "request", ev, f,
                            f"{at} request", req, target, "send", [ev])
                for r in part.get("responses", []):
                    name = r.get("name", "Reply")
                    if not any(k in r for k in FORM_SUFFIX):
                        yield Shape(self, shape_id("send", ev, "response", name, vid), "response", ev,
                                    f, f"{at} response {name}", r, _reply_target(self, r), "recv",
                                    _events(r))
                        continue
                    for key, suffix in FORM_SUFFIX.items():
                        form = r.get(key)
                        if not isinstance(form, dict):
                            continue
                        spec = None if form.get("none") else dict(
                            {k: r[k] for k in INHERIT if k in r}, **form)
                        yield Shape(self, shape_id("send", ev, "response", name, vid, suffix),
                                    "response", ev, f, f"{at} response {name} ({key})", form,
                                    _reply_target(self, spec), "recv", _events(spec),
                                    inherited=r.get("confirm"))
                for n, row in enumerate(part.get("failures", {}).get("rows", []), 1):
                    if row.get("branch"):
                        continue
                    yield Shape(self, shape_id("send", ev, "failure", n, vid), "failure", ev, f,
                                f"{at} failure {n}", row, ("failure", s, v, row), "recv",
                                self._failure_events(s, v, row))
                for i, a in enumerate(part.get("also", []), 1):
                    yield Shape(self, shape_id("send", ev, "also", i, vid), "also", ev, f,
                                f"{at} also {i} ({a.get('event')})", a, _reply_target(self, a),
                                "recv", _events(a))
        for ev, s in self.recv.items():
            f = s["_file"]
            p = s.get("payload") or {}
            target = ("object", p) if p.get("fields") or p.get("extends") else ("type", p.get("type", "any"))
            yield Shape(self, shape_id("recv", ev, "payload"), "payload", ev, f, f"{f} payload", p,
                        target, "recv", [ev])
            for i, v in enumerate(s.get("variants", []), 1):
                key = v.get("name") or i
                yield Shape(self, shape_id("recv", ev, "variant", key), "variant", ev, f,
                            f"{f} variant {key}", v, ("type", v["type"]), "recv", [ev])
        for name, t in self.types.items():
            yield Shape(self, shape_id("type", key=name), "type", None,
                        self.local.get(name, "schema/types.json"), f"type {name}", t,
                        ("type", name), None, [])

    def _failure_replies(self, s, v, row):
        """The replies a failure row can send, as (label, event, target): each request_id form
        apart; a `see` reply as the targets of the response it names; `close` left out."""
        out = []
        for label, rep in self.flat_replies(row):
            if rep.get("close"):
                continue
            if rep.get("see"):
                for _, part in self.parts(s):
                    for r in part.get("responses", []):
                        if r.get("name") == rep["see"]:
                            for flabel, spec in forms(r):
                                out.append((flabel or label, (spec or {}).get("event"),
                                            _reply_target(self, spec)))
                continue
            ev = self.failure_event(s, rep)
            if ev != "game_response":
                p = self.recv.get(ev, {}).get("payload")
                if p is None:
                    target = ("type", "any")  # an event with no receive schema: not checked
                elif p.get("fields") or p.get("extends"):
                    target = ("object", p)
                else:
                    target = ("type", p.get("type", "any"))
            else:
                fields = failure_fields(self, s, v, rep)
                target = ("type", code_type_of(rep)) if fields is None else ("object", {"fields": fields})
            code = (codes_of(rep) or [""])[0]
            out.append((" ".join(x for x in (label, code) if x) or None, ev, target))
        return out

    def _failure_events(self, s, v, row):
        return list(dict.fromkeys(ev for _, ev, _ in self._failure_replies(s, v, row) if ev))

    def payload_errors(self, shape, payload, event=None):
        """The mismatches between a concrete payload (a real capture) and a shape: a list of
        short messages, empty when the payload fits. `shape` is a Shape or a shape id. `event`
        is the socket event the payload came on; when given, a shape that never arrives on it
        is a mismatch, and a failure row only tries its replies on that event.

        Unlike the checks of the examples (which allow trimmed examples), this is strict: a
        required field that is missing, a field that the schema does not declare (unless the
        object is `open`), and a value of the wrong type at any depth are each a mismatch."""
        sh = self.shape(shape) if isinstance(shape, str) else shape
        if sh is None:
            return [f"{shape}: no such shape"]
        if event is not None and sh.events and event not in sh.events:
            return [f"{sh.id}: arrives on {', '.join(sh.events)}, not on {event}"]
        kind = sh.target[0]
        if kind == "failure":
            _, s, v, row = sh.target
            tries = [(label, t) for label, ev, t in self._failure_replies(s, v, row)
                     if event is None or ev == event]
            if not tries:
                return [f"{sh.id}: no reply of this row arrives on {event}"]
            best = None
            for label, t in tries:
                errs = self._target_errors(sh.id, t, payload)
                if not errs:
                    return []
                if best is None or len(errs) < len(best[1]):
                    best = (label, errs)
            label, errs = best
            return [f"(closest reply: {label}) {e}" if label else e for e in errs]
        if kind == "variants":
            s = sh.target[1]
            best = None
            for v in variant_list(s):
                full = self.variant_request(s, v)
                t = ("type", full["type"]) if full.get("type") else ("object", full)
                errs = self._target_errors(sh.id, t, payload)
                if not errs:
                    return []
                if best is None or len(errs) < len(best[1]):
                    best = (variant_name(v), errs)
            return [f"(closest variant: {best[0]}) {e}" for e in best[1]] if best else []
        return self._target_errors(sh.id, sh.target, payload)

    def _target_errors(self, where, target, value):
        kind = target[0]
        if kind == "none":
            return [f"{where}: the schema says that the server sends nothing here"]
        if kind == "object":
            return self._object_errors(where, target[1], value)
        if kind == "type":
            return self._value_errors(where, parse_type(target[1]), value)
        if kind == "recv":
            p = self.recv[target[1]].get("payload", {})
            if p.get("fields") or p.get("extends"):
                return self._object_errors(where, p, value)
            return self._value_errors(where, parse_type(p.get("type", "any")), value)
        raise ValueError(target)

    def _object_errors(self, where, spec, value):
        if not isinstance(value, dict):
            return [f"{where}: {_short(value)} is not an object"]
        out = []
        fields = self.all_fields(spec)
        names = {f["name"] for f in fields}
        if not self.is_open(spec):
            extra = sorted(set(value) - names)
            if extra:
                out.append(f"{where}: undeclared fields {extra}")
        missing = [f["name"] for f in fields if not f.get("optional") and f["name"] not in value]
        if missing:
            out.append(f"{where}: missing required fields {missing}")
        for f in fields:
            if f["name"] in value:
                out += self._value_errors(f"{where}.{f['name']}", parse_type(f["type"]), value[f["name"]])
        return out

    def _value_errors(self, where, tree, value):
        kind = tree[0]
        if kind == "lit":
            same = value == tree[1] and isinstance(value, bool) == isinstance(tree[1], bool)
            return [] if same else [f"{where}: {_short(value)} is not {json.dumps(tree[1])}"]
        if kind == "prim":
            return [] if PRIM_OK.get(tree[1], lambda v: True)(value) else \
                [f"{where}: {_short(value)} is not a {tree[1]}"]
        if kind == "ref":
            t = self.types[tree[1]]
            if "type" in t:
                return self._value_errors(where, parse_type(t["type"]), value)
            return self._object_errors(f"{where} ({tree[1]})", t, value)
        if kind == "array":
            if not isinstance(value, list):
                return [f"{where}: {_short(value)} is not an array"]
            return [e for i, x in enumerate(value) for e in self._value_errors(f"{where}[{i}]", tree[1], x)]
        if kind == "record":
            if not isinstance(value, dict):
                return [f"{where}: {_short(value)} is not an object"]
            return [e for k, x in value.items() for e in self._value_errors(f"{where}.{k}", tree[1], x)]
        if kind == "tuple":
            if not isinstance(value, list) or len(value) != len(tree[1]):
                return [f"{where}: {_short(value)} is not a {len(tree[1])}-tuple"]
            return [e for i, (t, x) in enumerate(zip(tree[1], value))
                    for e in self._value_errors(f"{where}[{i}]", t, x)]
        if kind == "union":
            tries = []
            for t in tree[1]:
                errs = self._value_errors(where, t, value)
                if not errs:
                    return []
                tries.append(errs)
            # A member that got past the top level (the value is an object and the member an
            # object type, but a field is wrong) is the one the payload meant: report its own
            # errors, the fewest of such members. Else one line that names every member.
            deep = [e for e in tries if not any(x.startswith(f"{where}: ") for x in e)]
            if deep:
                return min(deep, key=len)
            return [f"{where}: {_short(value)} matches no member of the union: "
                    + " / ".join(e[0] for e in tries[:4])]
        raise ValueError(tree)

    # -- helpers ----------------------------------------------------------------------------------

    @staticmethod
    def parts(s):
        """(variant, part) for the shared part of a send schema (variant None), then each
        request variant. A part has responses, failures, also and order."""
        yield None, s
        for v in variant_list(s):
            yield v, v

    def variant_request(self, s, v):
        """The whole request of one variant: the shared fields, with the key field narrowed to
        the variant's values (left out for a variant matched another way), then the variant's
        own fields. An own field replaces a shared field of the same name."""
        vr = v.get("request", {})
        if vr.get("type"):
            return vr
        key = s["variants"]["key"]
        own = vr.get("fields", [])
        names = {f["name"] for f in own}
        fields = []
        for f in s["request"].get("fields", []):
            if f["name"] in names:
                continue
            if f["name"] == key:
                vals = variant_values(v)
                if vals:
                    f = dict(f, type=lit_union(vals))
                    f.pop("optional", None)
                elif v.get("other"):
                    # "Any other value": the primitive of the key's literal union, not the union.
                    tree = parse_type(f["type"])
                    lits = [x[1] for x in tree[1]] if tree[0] == "union" and all(
                        x[0] == "lit" for x in tree[1]) else [tree[1]] if tree[0] == "lit" else None
                    if lits:
                        f = dict(f, type="string" if all(isinstance(x, str) for x in lits) else "number")
                else:
                    continue
            fields.append(f)
        out = {"fields": fields + own}
        if "example" in vr:
            out["example"] = vr["example"]
        return out

    @staticmethod
    def replies(row):
        """A failure row is either {"code": ...} (one reply) or {"replies": [...]} (zero or more,
        in the order the server sends them)."""
        if "replies" in row:
            return row["replies"]
        return [{k: v for k, v in row.items() if k not in ("when", "source", "confirm")}]

    def flat_replies(self, row):
        """Every reply a row can send, with the `request_id` forms apart: [(label, reply)]."""
        out = []
        for rep in self.replies(row):
            for label, spec in forms(rep):
                if spec is not None:
                    out.append((label, spec))
        return out

    def failure_event(self, s, rep):
        return rep.get("event") or s.get("failures", {}).get("event", "game_response")

    def place(self, s, v=None, rep=None):
        """The `place` of a failure reply: (the example value, a type expression). From the
        reply, the variant, the shared failures, `place_from` (a request field: the skill
        name), else the event name."""
        if rep is not None and "place" in rep:
            return rep["place"], json.dumps(rep["place"])
        vf = (v or {}).get("failures", {})
        for holder in (v or {}, vf):
            if "place" in holder:
                return holder["place"], json.dumps(holder["place"])
        fail = s.get("failures", {})
        pf = vf.get("place_from") or fail.get("place_from")
        if pf:
            vals = variant_values(v) if v is not None else []
            if vals and pf == s.get("variants", {}).get("key"):
                return vals[0], lit_union(vals)
            field = next(f for f in s["request"]["fields"] if f["name"] == pf)
            ex = (v or {}).get("request", {}).get("example") or s["request"].get("example") or {}
            return (ex.get(pf, f"<{pf}>") if isinstance(ex, dict) else f"<{pf}>"), field["type"]
        p = fail.get("place", s["event"])
        return p, json.dumps(p)

    def reply_object(self, place, rep, code=None):
        """The literal payload of one failure reply, built from its form and its extra fields.
        `code` picks one of `codes`."""
        if rep.get("event") and rep.get("event") != "game_response":
            return rep.get("example")
        if "example" in rep:
            return rep["example"]
        code = code or (codes_of(rep) or [None])[0]
        form = rep.get("form", "failure")
        if form == "bare":
            return code
        obj = {} if form == "object" else {"response": code}
        if form == "failure":
            obj.update({"place": place, "failed": True})
        for f in rep.get("extra", []):
            obj[f["name"]] = example_value(f)
        return obj


def example_value(field):
    """The example value of a field: its "example", or the value of a literal type."""
    if "example" in field:
        return field["example"]
    tree = parse_type(field["type"])
    if tree[0] == "lit":
        return tree[1]
    return f"<{field['name']}>"


# ---------------------------------------------------------------------------------------------
# Confirmation: shapes, `confirm`, schema/live.json (docs/WRITING.md, "Confirmation")
#
# The public API (the live-capture tool, scripts/check-captures.py, imports it):
#   schema = apischema.Schema()             loads and checks everything (live.json too)
#   apischema.shape_ids(schema)             every shape id, in page order
#   schema.shapes() / schema.shape(sid)     Shape objects (see the class)
#   apischema.shape_id(...)                 builds one id (the only place that does)
#   apischema.check_payload(schema, sid, payload, event=None)
#                                           mismatches of a real payload, [] when it fits
#   shape.state()                           what is confirmed (code, live, mismatches)
# ---------------------------------------------------------------------------------------------

# A citation of `confirm.code`: `path:line` or `path:line-line`, with an optional `common:` (the
# common_engine repo) or `legacy:` (the old App Engine repo) prefix, as the page links them
# (SRC_RE in template.html). One range per string: list several strings for several places.
CITATION = re.compile(r"^(?:(common|legacy):)?((?:[\w.-]+/)*[\w.-]+\.(?:js|py|html|json)):(\d+)(?:-(\d+))?$")
# Where each prefix's files are (scripts/fetch-source.sh); a citation past the end of its file
# is wrong. Skipped when the folder is not there (a fresh clone without vendor/).
VENDOR = {None: ROOT / "vendor" / "adventureland_mongodb",
          "common": ROOT / "vendor" / "common_engine",
          "legacy": ROOT / "vendor" / "adventureland"}
_LINES = {}


def _line_count(path):
    if path not in _LINES:
        _LINES[path] = len(path.read_text(errors="replace").splitlines()) if path.is_file() else None
    return _LINES[path]


def _check_confirm(where, c):
    """`confirm` is {"code": [citations], "live_needed": "why", "note": "..."}: `code` (a list
    of citations) and/or `live_needed` (a non-empty string). A bad form is fatal; a citation
    that points past the end of its file is a warning (fatal under ALAPI_STRICT_CONFIRM=1)."""
    w = f"{where} confirm"
    if not isinstance(c, dict):
        raise SystemExit(f"{w}: expected an object {{\"code\": [...], \"live_needed\": \"...\"}}")
    bad = [k for k in c if not k.startswith("_") and k not in KEYS["confirm"]]
    if bad:
        raise SystemExit(f"{w}: unknown keys {bad} (code, live_needed, note)")
    code = c.get("code", [])
    if not isinstance(code, list) or not all(isinstance(x, str) for x in code):
        raise SystemExit(f"{w}: \"code\" is a list of strings such as \"node/server.js:8460-8470\"")
    if "live_needed" in c and (not isinstance(c["live_needed"], str) or not c["live_needed"].strip()):
        raise SystemExit(f"{w}: \"live_needed\" is a sentence: why the code is not enough")
    if "note" in c and not isinstance(c["note"], str):
        raise SystemExit(f"{w}: \"note\" is a string")
    if not code and "live_needed" not in c:
        raise SystemExit(f"{w}: give \"code\" (citations) or \"live_needed\" (why the code is not enough)")
    for x in code:
        m = CITATION.match(x)
        if not m:
            raise SystemExit(f"{w}: {x!r} is not a citation `path:line` or `path:line-line` "
                             f"(one range per string; a full path such as node/server.js)")
        prefix, path, a, b = m.groups()
        a, b = int(a), int(b or a)
        if b < a or a < 1:
            raise SystemExit(f"{w}: {x!r}: the range runs backwards")
        root = VENDOR[prefix]
        if not root.is_dir():
            continue
        n = _line_count(root / path)
        if n is None:
            confirm_warn(f"{w}: {x!r}: no file {root.relative_to(ROOT) / path}")
        elif b > n:
            confirm_warn(f"{w}: {x!r}: the file has {n} lines")


def load_live(root=SCHEMA):
    """schema/live.json (written by the live-capture tool, never by hand), or None when it does
    not exist yet. {"captured_at", "server", "shapes": {shape id: {"count", "first", "last",
    "sample", "mismatches": [...]}}}."""
    f = Path(root) / "live.json"
    if not f.exists():
        return None
    data = json.loads(f.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("shapes", {}), dict):
        raise SystemExit("schema/live.json: expected {\"shapes\": {shape id: {...}}}")
    for sid, rec in data.get("shapes", {}).items():
        if not isinstance(rec, dict) or not isinstance(rec.get("count", 0), int) \
                or not isinstance(rec.get("mismatches", []), list):
            raise SystemExit(f"schema/live.json: {sid}: expected {{\"count\": n, \"mismatches\": [...], ...}}")
    return data


def mismatch_text(m):
    """One mismatch of schema/live.json as one line: the capture tool writes objects
    ({"path", "problem", "kind", "at", "char", "payload"}); a plain string is shown as is."""
    if isinstance(m, dict):
        where = m.get("path", "?")
        when = f" [{m['at'][:19]}]" if m.get("at") else ""
        return f"{where}: {m.get('problem', m.get('kind', '?'))}{when}"
    return str(m)


def _short(value):
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def _request_target(req):
    """What a request payload is checked against: its type, its object, or (no fields) any value:
    the server ignores the payload."""
    if req.get("type"):
        return ("type", req["type"])
    if req.get("fields"):
        return ("object", req)
    return ("type", "any")


def _reply_target(schema, spec):
    """What a reply (a response, one of its forms, an also entry) is checked against."""
    if spec is None or spec.get("kind"):
        return ("none",)
    if spec.get("fields") or spec.get("extends"):
        return ("object", spec)
    if spec.get("type"):
        return ("type", spec["type"])
    if spec.get("event") in schema.recv:
        return ("recv", spec["event"])  # a `summary` reply: the payload of its receive schema
    return ("type", "any")


def _events(spec):
    return [spec["event"]] if spec and spec.get("event") and not spec.get("kind") else []


class Shape:
    """One documented payload.

    id         its shape id (shape_id), the key of schema/live.json
    kind       "request", "response", "failure", "also", "payload", "variant" or "type"
    event      the event of its schema file (None for a type of schema/types.json)
    file       the schema file, such as "schema/send/buy.json"
    where      a readable place for messages
    holder     the JSON object that carries `confirm`
    confirm    the effective `confirm` (a request_id form without its own takes the one of its
               response), or None
    live       its record in schema/live.json, or None
    direction  "send" (a request: client to server), "recv" (server to client), None (a type)
    events     the socket events it can arrive on (a request: its own event; a failure row:
               each event its replies use; a type: none)
    target     what check_payload checks a payload against (internal)
    """

    def __init__(self, schema, sid, kind, event, file, where, holder, target, direction, events,
                 inherited=None):
        self.schema, self.id, self.kind, self.event, self.file = schema, sid, kind, event, file
        self.where, self.holder, self.target = where, holder, target
        self.direction, self.events = direction, events
        self.confirm = holder.get("confirm", inherited) if isinstance(holder, dict) else inherited
        self.live = None

    @property
    def sends_nothing(self):
        """True for "the server sends nothing" or "closes the socket": no payload to capture."""
        return self.target[0] == "none"

    def check(self, payload, event=None):
        return self.schema.payload_errors(self, payload, event)

    def state(self):
        """What is confirmed: {"in_code": bool (citations and no live_needed), "live": bool (at
        least one capture and no mismatches), "confirmed": either, "code": [...],
        "live_needed": str or None, "note": str or None, "count": int, "last": "YYYY-MM-DD" or
        None, "mismatches": [...], "missing": bool (no confirm key)}."""
        c = self.confirm or {}
        rec = self.live or {}
        mism = rec.get("mismatches") or []
        in_code = bool(c.get("code")) and not c.get("live_needed")
        live = rec.get("count", 0) > 0 and not mism
        return {"in_code": in_code, "live": live, "confirmed": in_code or live,
                "code": c.get("code", []), "live_needed": c.get("live_needed"), "note": c.get("note"),
                "count": rec.get("count", 0), "last": (rec.get("last") or "")[:10] or None,
                "mismatches": mism, "missing": self.confirm is None}

    def __repr__(self):
        return f"Shape({self.id!r})"


def shape_ids(schema=None):
    """Every shape id of the schema, in page order (loads the schema when none is given)."""
    return [sh.id for sh in (schema or Schema()).shapes()]


def check_payload(schema, sid, payload, event=None):
    """The mismatches between a real payload and the shape `sid` (a list of messages; empty when
    it fits). See Schema.payload_errors."""
    return schema.payload_errors(sid, payload, event)


# ---------------------------------------------------------------------------------------------
# Markdown rendering (the reference page)
# ---------------------------------------------------------------------------------------------


def type_anchor(name):
    return f"type-{name.lower()}"


def md_type(tree):
    """A type tree as Markdown for a table cell: code spans, named types as links."""
    kind = tree[0]
    if kind == "prim":
        return f"`{tree[1]}`"
    if kind == "lit":
        return f"`{json.dumps(tree[1])}`"
    if kind == "ref":
        return f"[`{tree[1]}`](#{type_anchor(tree[1])})"
    if kind == "array":
        inner = md_type(tree[1])
        return f"({inner})`[]`" if tree[1][0] == "union" else f"{inner}`[]`"
    if kind == "record":
        return f"`Record<string,` {md_type(tree[1])}`>`"
    if kind == "tuple":
        return "`[`" + "`,` ".join(md_type(t) for t in tree[1]) + "`]`"
    if kind == "union":
        return " \\| ".join(md_type(t) for t in tree[1])
    raise ValueError(tree)


def md_type_text(text):
    return md_type(parse_type(text))


def cell(text):
    """Table cells: a raw `|` would end the cell, also inside code spans (GFM)."""
    return re.sub(r"(?<!\\)\|", r"\\|", text.replace("\n", " "))


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def json_block(value):
    text = compact(value)
    if len(text) > 76:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    return f"```json\n{text}\n```"


# The text of the one row of a field table that has no fields. Every entry shows its tables even
# when they are empty (owner, 2026-10-04: "Even on an empty payload I want the layout on all pages
# to be the same"), so an empty table says "None" in a row of its own instead of disappearing.
NONE_CELL = "-"


def none_row(columns, text):
    """One table row that says that a table is empty: `-` in each cell, `text` in the last."""
    return "| " + " | ".join([NONE_CELL] * (columns - 1) + [text]) + " |"


def field_rows(fields, request, overrides=(), empty="None."):
    """A field table. `overrides`: names to mark as replacing a field of the base type. With no
    fields, the table has one row that says `empty`."""
    head = "| Field | Type | Required | Description |" if request else \
        "| Field | Type | Present | Description |"
    rows = [head, "|---|---|---|---|"]
    if not fields:
        rows.append(none_row(4, cell(empty)))
    for f in fields:
        desc = f["description"]
        if f["name"] in overrides:
            desc = "(Replaces the field of the base type.) " + desc
        if "default" in f:
            desc += f" Default: `{compact(f['default'])}`."
        if f.get("coerce"):
            desc += f" The server reads it as: {f['coerce']}."
        if request:
            need = "no" if f.get("optional") else "yes"
        else:
            need = "optional" if f.get("optional") else "always"
        rows.append(f"| `{f['name']}` | {cell(md_type_text(f['type']))} | {need} | {cell(desc)} |")
    return "\n".join(rows)


def event_link(event, kind="recv"):
    return f"[`{event}`](#{kind}-{re.sub(r'[^a-z0-9_]+', '-', event.lower()).strip('-')})"


def code_link(code):
    return f"[`{code}`](#code-{re.sub(r'[^a-z0-9_]+', '-', code.lower()).strip('-')})"


# `node/server.js:10, 20-30` -> `node/server.js:10, node/server.js:20-30`: the page links each
# `file:line` (SRC_RE in template.html), and a bare line number after a comma has no file.
_SRC_LIST = re.compile(r"((?:[\w.-]+/)*[\w.-]+\.(?:js|py|html)):(\d+(?:\s*-\s*\d+)?)((?:,\s*\d+(?:\s*-\s*\d+)?)+)")


def link_sources(text):
    def expand(m):
        path, first, rest = m.groups()
        more = [x.strip() for x in rest.split(",") if x.strip()]
        return ", ".join(f"{path}:{x}" for x in [first] + more)
    return _SRC_LIST.sub(expand, text)


def src(text):
    return f"Source: {link_sources(text)}." if text else ""


def numbered(steps):
    return "\n".join(f"{n}. {step}" for n, step in enumerate(steps, 1))


class Renderer:
    def __init__(self, schema):
        self.s = schema

    # -- confirmation ---------------------------------------------------------------------------

    def confirm_md(self, sid, short=False):
        """The status line of one shape (docs/WRITING.md, "Confirmation"). Every shape shows one,
        so that every entry has the same layout. `short`: the text of a table cell."""
        sh = self.s.shape(sid)
        st = sh.state() if sh else {"missing": True}
        if st["missing"]:
            return "Not yet." if short else "*Not yet confirmed.*"
        cites = ", ".join(st["code"])
        out = []
        if st["in_code"]:
            out.append(f"Code: {cites}." if short else f"*Confirmed in code:* {cites}.")
        if st["live"]:
            n = st["count"]
            when = f", {st['last']}" if st["last"] else ""
            out.append(f"Live: {n}{when}." if short else
                       f"*Confirmed live:* {n} capture{'s' if n != 1 else ''}{when}.")
        if st["mismatches"]:
            k = len(st["mismatches"])
            out.append(f"Live mismatch: {k}." if short else
                       f"*Live captures disagree:* {k} mismatch{'es' if k != 1 else ''}, under review.")
        if not st["in_code"] and not st["live"]:
            why = st["live_needed"].rstrip(".")
            out.append(f"Not yet: {why}." if short else f"*Not yet confirmed:* {why}.")
        if not st["in_code"] and cites:
            out.append(f"Partly in code: {cites}." if short else f"In code, partly: {cites}.")
        if st["note"] and not short:
            # The note is its own sentence (a table cell stays short and leaves it out).
            out.append(st["note"][0].upper() + st["note"][1:].rstrip(".") + ".")
        return " ".join(out)

    def ev_link(self, event, no_entry=False):
        """A link to the receive entry of an event, or plain code when it has none."""
        if no_entry:
            return f"`{event}`"
        return event_link(event)

    # -- objects ------------------------------------------------------------------------------

    def object_md(self, spec, request=False):
        """The field table of an object spec, with a line for its `extends` base."""
        parts = []
        if "type" in spec and not spec.get("fields"):
            parts.append(f"Type: {md_type_text(spec['type'])}.")
            return "\n\n".join(parts)
        if spec.get("extends"):
            base = spec["extends"]
            parts.append(f"All fields of {md_type_text(base)}, and these:" if spec.get("fields")
                         else f"All fields of {md_type_text(base)}.")
        if spec.get("fields"):
            parts.append(field_rows(spec["fields"], request))
        elif not spec.get("extends") and not spec.get("open"):
            parts.append("An empty object: `{}`.")
        if spec.get("open"):
            parts.append("The object can have more fields than these.")
        return "\n\n".join(parts)

    # -- send ---------------------------------------------------------------------------------

    def send_line(self, ev, example):
        if example is None:
            return f'`socket.emit("{ev}")`'
        return f'`socket.emit("{ev}", {compact(example)})`'

    def request_md(self, req, ev=None, trigger=False):
        """The Request section. It has the same parts for every event, also with no payload: the
        field table (one "None" row when there are no fields), "Other fields", the note, and a
        JSON block (`{}` when the request has no fields: the server ignores the payload)."""
        out = []
        if req.get("type"):
            tree = parse_type(req["type"])
            objs = tree[0] == "union" and any(x[0] == "ref" and "type" not in self.s.types[x[1]]
                                              for x in tree[1])
            what = "One of the types in the Type column." if objs else \
                "The payload is not an object: it is the value itself."
            # `any`: the handler reads nothing, so the payload can be left out.
            need = "no" if req["type"] == "any" else "yes"
            out.append("| Field | Type | Required | Description |\n|---|---|---|---|\n"
                       f"| (the payload) | {cell(md_type_text(req['type']))} | {need} | {what} |")
        else:
            empty = ("No fields. The server runs this handler itself; the client sends nothing."
                     if trigger else "No fields. The server ignores the payload.")
            out.append(field_rows(req.get("fields", []), request=True, empty=empty))
        if req.get("others"):
            out.append(f"Other fields: {req['others']}.")
        if req.get("note"):
            out.append(req["note"])
        if "example" in req and req["example"] is not None:
            out.append(json_block(req["example"]))
        elif trigger:
            out.append("No JSON: the client does not send this event.")
        elif not req.get("fields") and not req.get("type"):
            # No fields: send the event alone. An empty object is the same to the server.
            out.append(f'Send the event alone: `socket.emit("{ev}")`. The server also accepts an '
                       f"object, and ignores it:")
            out.append(json_block({}))
        else:
            out.append("No example: see the note.")
        return out

    def order_md(self, order, title="On success, the server sends, in this order:"):
        if not order:
            return []
        if isinstance(order, dict):
            out = [title.replace(", in this order:", ". The order of each path:")]
            for path, steps in order.items():
                out.append(f"*{path}:*\n\n" + numbered(steps))
            return out
        return [title + "\n\n" + numbered(order)]

    def send_md(self, ev):
        s = self.s.send[ev]
        out = []
        req = s["request"]
        # The page's Copy button takes the first code span after **Send:** (build.py).
        if s.get("trigger"):
            out.append(f"**Trigger:** {s['trigger']}")
        else:
            out.append(f"**Send:** {self.send_line(ev, req.get('example'))}")
        out.append("#### Request")
        out += self.request_md(req, ev, bool(s.get("trigger")))
        out.append(self.confirm_md(shape_id("send", ev, "request")))
        vs = s.get("variants")
        if vs:
            out.append(self.variants_table(s))

        out.append("#### Responses")
        out += self.part_md(s, None)
        out.append("#### Also sent")
        out.append("Events that go to other clients, or to you later or as a side effect.")
        out += self.also_md(s.get("also", []), "None." if not variant_list(s) else
                            "None for every variant. A variant can add its own: see its block.",
                            ev=ev)
        for v in variant_list(s):
            out.append(f"#### Variant: {variant_title(s, v)}")
            out += self.variant_md(ev, s, v)
        return "\n\n".join(x for x in out if x)

    def variants_table(self, s):
        vs = s["variants"]
        key = vs["key"]
        parts = [f"The field `{key}` selects the variant. Each variant has its own fields, replies "
                 f"and checks, in its block below; the fields above apply to all of them."]
        if vs.get("intro"):
            parts.append(vs["intro"])
        rows = [f"| Variant | `{key}` | Own fields | What it does |", "|---|---|---|---|"]
        for v in variant_list(s):
            vals = variant_values(v)
            value = ", ".join(f"`{json.dumps(x)}`" for x in vals) if vals else (
                "any other" if v.get("other") else (
                    f"none: {md_type_text(v['request']['type'])}" if v.get("request", {}).get("type")
                    else ""))
            own = ", ".join(f"`{f['name']}`" for f in v.get("request", {}).get("fields", [])) or "-"
            if v.get("match"):
                value += f" ({v['match']})" if vals or value else v["match"]
            rows.append(f"| {variant_name(v)} | {cell(value)} | {cell(own)} | {cell(v['when'])} |")
        parts.append("\n".join(rows))
        return "\n\n".join(parts)

    def part_md(self, s, v):
        """Order, responses and failures of the shared part (v None) or of one variant. Each part
        has all three, also when one is empty, so that every entry has the same layout."""
        part = s if v is None else v
        vid = None if v is None else variant_id(v)
        out = []
        rs = part.get("responses", [])
        if part.get("order"):
            out += self.order_md(part["order"])
        elif rs and all(r.get("kind") == "none" for r in rs):
            out.append("On success, the server sends nothing.")
        elif rs:
            out.append("On success, the server sends the replies below.")
        elif v is None and variant_list(s):
            out.append("On success, the replies depend on the variant: see its block.")
        else:
            out.append("On success, the server sends nothing.")
        for r in rs:
            out.append(self.response_md(r, s["event"], vid))
        out.append(self.failures_md(s, v))
        return out

    def variant_md(self, ev, s, v):
        """One variant block: what it does, then Request, Responses (with Failure), Also sent and
        Source, always in this order and always all of them (a "None" row when one is empty)."""
        out = [v["when"]]
        vr = v.get("request", {})
        if vr.get("type"):
            out.append("**Request:**\n\n| Field | Type | Required | Description |\n|---|---|---|---|\n"
                       f"| (the payload) | {cell(md_type_text(vr['type']))} | yes | The payload is not "
                       f"an object: it is the value itself. |")
        else:
            out.append("**Request:** the fields of the variant, after the shared fields:\n\n"
                       + field_rows(vr.get("fields", []), True, empty="None: no fields of its own."))
        if vr.get("note"):
            out.append(vr["note"])
        # A variant without own fields can leave out its example: the shared fields and the
        # key field make the whole payload, and the Send line at the top may show it.
        ex = vr.get("example")
        out.append("Example: " + (self.send_line(ev, ex) if "example" in vr else
                                  "none of its own: the shared fields with the key field set "
                                  "to the value of the variant."))
        out.append(self.confirm_md(shape_id("send", ev, "request", variant=variant_id(v))))
        if v.get("same_as"):
            same = next(x for x in variant_list(s) if variant_name(x) == v["same_as"])
            out.append(f"**Responses:** the replies are those of the variant {variant_title(s, same)}.")
        else:
            out.append("**Responses:**")
        out += self.part_md(s, v)
        out.append("**Also sent:**")
        out += self.also_md(v.get("also", []),
                            "None of its own. The shared events (above) apply.",
                            ev=ev, vid=variant_id(v))
        out.append(src(v["source"]) if v.get("source") else "Source: the Source of the entry.")
        return out

    def also_md(self, also, empty="None.", ev=None, vid=None):
        out = []
        rows = ["| Event | To | When | Payload | Confirmed |", "|---|---|---|---|---|"]
        if not also:
            rows.append(f"| {NONE_CELL} | {NONE_CELL} | {empty} | {NONE_CELL} | {NONE_CELL} |")
        for i, a in enumerate(also, 1):
            if a.get("example") is not None:
                payload = f"`{compact(a['example'])}`"
                if a.get("type"):
                    payload = f"{md_type_text(a['type'])}: {payload}"
            elif a.get("type"):
                payload = md_type_text(a["type"])
            else:
                payload = a.get("summary", "")
            name = self.ev_link(a["event"], a.get("no_entry"))
            if a.get("name"):
                name += f" ({a['name']})"
            codes = codes_of(a)
            if codes:
                name += " " + " or ".join(code_link(c) for c in codes)
            status = self.confirm_md(shape_id("send", ev, "also", i, vid), short=True)
            rows.append(f"| {name} | {a['to']} | {cell(a['when'])} | {cell(payload)} | {cell(status)} |")
        out.append("\n".join(rows))
        for a in also:
            if a.get("fields") or a.get("extends"):
                label = f" ({a['name']})" if a.get("name") else ""
                out.append(f"Fields of {self.ev_link(a['event'], a.get('no_entry'))}{label}:\n\n"
                           + self.object_md(a))
        return out

    def response_md(self, r, ev, vid=None):
        """One reply block. The status line of the shape ends it; a reply with two request_id
        forms has one status line under each form (each form is a shape)."""
        name = r.get("name", "Reply")
        title = f"**{name}:** "
        sid = shape_id("send", ev, "response", name, vid)
        if r.get("kind") == "none":
            return title + "no reply. " + r["when"] + "\n\n" + self.confirm_md(sid)
        if r.get("kind") == "close":
            return title + "the server closes the socket. " + r["when"] + "\n\n" + self.confirm_md(sid)
        fs = forms(r)
        if fs[0][0] is None:
            title += self.reply_title(r)
            parts = [title, r["when"]]
            parts += self.shape_md(r)
        else:
            parts = [title + "two forms, by `request_id`.", r["when"]]
            for (label, spec), suffix in zip(fs, FORM_SUFFIX.values()):
                fline = self.confirm_md(shape_id("send", ev, "response", name, vid, suffix))
                if spec is None:
                    parts.append(f"*{label}:* the server sends nothing. {fline}")
                    continue
                if spec.get("kind") == "close":
                    parts.append(f"*{label}:* the server closes the socket. {fline}")
                    continue
                parts.append(f"*{label}:* {self.reply_title(spec)}")
                parts += self.shape_md(spec)
                parts.append(fline)
        if r.get("note"):
            parts.append(r["note"])
        if r.get("source"):
            parts.append(src(r["source"]))
        if fs[0][0] is None:
            parts.append(self.confirm_md(sid))
        return "\n\n".join(parts)

    def reply_title(self, r):
        t = self.ev_link(r["event"])
        codes = codes_of(r)
        if r.get("code_type") and codes:
            t += f" (`response` is {md_type_text(r['code_type'])}, for example `{codes[0]}`)"
        elif codes:
            t += " " + " or ".join(code_link(c) for c in codes)
        if r.get("via"):
            t += f", as {r['via']}"
        return t

    def shape_md(self, r):
        parts = []
        if r.get("summary"):
            parts.append(r["summary"])
        if r.get("type") and not r.get("fields"):
            parts.append(f"Payload: {md_type_text(r['type'])}.")
        elif r.get("fields") or r.get("extends"):
            parts.append(self.object_md(r))
        if "example" in r:
            if r.get("example_trimmed"):
                # A trimmed reply example leaves out fields of the full payload that this reply
                # does not change (docs/WRITING.md, "The schema"): say so, so that nobody reads
                # it as the whole payload.
                if r.get("event") == "player":
                    parts.append("Example, trimmed: only the changed fields. The server sends the "
                                 "whole character; see the receive entry for every field.")
                else:
                    parts.append("Example, trimmed: only the fields that matter for this reply. "
                                 "See the receive entry for every field.")
            parts.append(json_block(r["example"]))
        return parts

    def failures_md(self, s, v=None):
        ev = s["event"]
        fail = s.get("failures", {})
        part_fail = fail if v is None else v.get("failures", {})
        fevent = fail.get("event", "game_response")
        rows_all = [row for _, p in self.s.parts(s) for row in p.get("failures", {}).get("rows", [])]
        # The shared sentence about GameResponseFailure only where it is true: the failures
        # arrive as game_response, and some reply has the default form (docs/WRITING.md).
        uses_failure = any(self.s.failure_event(s, rep) == "game_response"
                           and not rep.get("close") and not rep.get("see")
                           and rep.get("form", "failure") == "failure"
                           for row in rows_all if not row.get("branch")
                           for _, rep in self.s.flat_replies(row))
        place, _ = self.s.place(s, v)
        on_event = any(self.s.failure_event(s, rep) == fevent and not rep.get("close") and not rep.get("see")
                       for row in rows_all if not row.get("branch") for _, rep in self.s.flat_replies(row))
        if v is None:
            parts = [f"**Failure:** {self.ev_link(fevent)}" if on_event else "**Failure:**"]
            text = ""
            if fevent == "game_response" and uses_failure:
                if fail.get("place_from"):
                    pl = f"`place` set to the `{fail['place_from']}` of the request"
                else:
                    pl = f"`place: \"{place}\"`"
                text = (f"Unless the Reply column shows another form, a failure is a "
                        f"[`GameResponseFailure`](#type-gameresponsefailure) with {pl}. ")
            if rows_all:
                text += ("The server runs the checks in this order and sends the reply of the first "
                         "that fails. ")
            text += ("Before " + ("these checks" if rows_all else "the handler runs") + ", every "
                     "request goes through the [shared steps](#guide-every-request) (call cost, "
                     "paused instances, errors).")
            parts.append(text)
        else:
            parts = ["**Failure:**"]
            vp = v.get("place", v.get("failures", {}).get("place"))
            if vp is not None:
                parts.append(f"In this variant, `place` is `\"{vp}\"`.")
            elif fail.get("place_from") and variant_values(v):
                parts.append(f"In this variant, `place` is the value of `{fail['place_from']}`.")
        if part_fail.get("intro"):
            parts.append(part_fail["intro"])
        rows = ["| # | Condition | Reply | Confirmed |", "|---|---|---|---|"]
        if not part_fail.get("rows"):
            if v is not None:
                rows.append("| - | None: the variant has no checks of its own. | - | - |")
            elif variant_list(s):
                rows.append("| - | None: no check runs before the checks of the variant. | - | - |")
            else:
                rows.append("| - | None: the handler has no check that fails. | - | - |")
        branch_seen = False
        vid = None if v is None else variant_id(v)
        for n, row in enumerate(part_fail.get("rows", []), 1):
            if row.get("branch"):
                branch_seen = True
                rows.append(f"| {n} | {cell(row['when'])} | The checks of the variant (see its block). | - |")
                continue
            cells = [self.reply_md(s, v, rep) for rep in self.s.replies(row)] or ["Nothing."]
            status = self.confirm_md(shape_id("send", ev, "failure", n, vid), short=True)
            rows.append(f"| {n} | {cell(row['when'])} | {cell(', then '.join(cells))} | {cell(status)} |")
        parts.append("\n".join(rows))
        if v is None and not branch_seen and any(x.get("failures", {}).get("rows") for x in variant_list(s)):
            parts.append("Then the checks of the variant run (see its block).")
        first = next(((n, rep) for n, row in enumerate(part_fail.get("rows", []), 1)
                      if not row.get("branch")
                      for _, rep in self.s.flat_replies(row)
                      if rep.get("form", "failure") == "failure" and codes_of(rep)
                      and self.s.failure_event(s, rep) == "game_response"
                      and not rep.get("close") and not rep.get("see")), None)
        if first:
            n, rep = first
            parts.append(f"Example (row {n}):")
            parts.append(json_block(self.s.reply_object(self.s.place(s, v, rep)[0], rep)))
        return "\n\n".join(parts)

    def reply_md(self, s, v, rep):
        fs = forms(rep)
        if fs[0][0] is not None:
            out = []
            for label, spec in fs:
                out.append(f"{label}: " + ("nothing" if spec is None else self._reply_md(s, v, spec)))
            text = ". ".join(out)
        else:
            text = self._reply_md(s, v, rep)
        if rep.get("note") and fs[0][0] is not None:
            text += f" ({rep['note']})"
        return text

    def _reply_md(self, s, v, rep):
        place = self.s.place(s, v, rep)[0]
        if rep.get("close"):
            text = "the server closes the socket"
        elif rep.get("see"):
            text = f"the **{rep['see']}** reply"
        elif self.s.failure_event(s, rep) != "game_response":
            text = self.ev_link(self.s.failure_event(s, rep))
            if "example" in rep:
                text += f" `{compact(rep['example'])}`"
        else:
            form = rep.get("form", "failure")
            codes = codes_of(rep)
            clink = " or ".join(code_link(c) for c in codes)
            if rep.get("code_type"):
                clink = f"`{codes[0]}` (`response` is {md_type_text(rep['code_type'])})"
            if form == "bare":
                text = f"{clink} as a bare string: `{compact(codes[0])}`"
            elif form in ("plain", "object"):
                text = (f"{clink} as " if clink else "as ") + f"`{compact(self.s.reply_object(place, rep))}`"
            else:
                text = clink
                extra = {f["name"]: example_value(f) for f in rep.get("extra", [])}
                if "place" in rep:
                    extra = {"place": rep["place"], **extra}
                if extra:
                    text += f" plus `{compact(extra)}`"
        if rep.get("note"):
            text += f" ({rep['note']})"
        return text

    # -- recv ---------------------------------------------------------------------------------

    def recv_md(self, ev):
        s = self.s.recv[ev]
        p = s.get("payload", {})
        out = ["#### Payload"]
        if p.get("type"):
            out.append(f"Type: {md_type_text(p['type'])}.")
        if s.get("variants"):
            rows = ["| Form | Type | When | Example | Confirmed |", "|---|---|---|---|---|"]
            for i, v in enumerate(s["variants"], 1):
                name = v["name"]
                if v.get("has"):
                    name += " (has " + ", ".join(f"`{k}`" for k in as_list(v["has"])) + ")"
                when = v["when"]
                if v.get("reply_to"):
                    when += " In reply to " + ", ".join(event_link(e, "send") for e in as_list(v["reply_to"])) + "."
                if v.get("source"):
                    when += f" Source: {link_sources(v['source'])}."
                status = self.confirm_md(shape_id("recv", ev, "variant", v.get("name") or i), short=True)
                rows.append(f"| {cell(name)} | {cell(md_type_text(v['type']))} | {cell(when)} | "
                            f"`{cell(compact(v['example']))}` | {cell(status)} |")
            out.append("\n".join(rows))
            if any(v.get("has") for v in s["variants"]):
                out.append("The forms have no tag field: tell them apart by the fields they have.")
        if p.get("extends"):
            base = self.s.types[p["extends"]]
            own = {f["name"] for f in p.get("fields", [])}
            out.append(f"All fields of {md_type_text(p['extends'])}, then the fields that only "
                       f"this event has" + (" or that it changes." if own & {f['name'] for f in self.s.all_fields(base)} else "."))
            out.append(field_rows([f for f in self.s.all_fields(base) if f["name"] not in own], False))
            if p.get("fields"):
                over = own & {f["name"] for f in self.s.all_fields(base)}
                out.append("Only in this event:\n\n" + field_rows(p["fields"], False, over))
        elif p.get("fields"):
            out.append(field_rows(p["fields"], False))
        else:
            # A payload that is not an object with fields of its own (a union of forms, a bare
            # string, an array) still gets the field table, with one row for the whole payload,
            # so that every receive entry has the same layout.
            ptype = p.get("type", "any")
            what = ("One of the forms in the table above." if s.get("variants") else
                    "The whole payload.")
            out.append("| Field | Type | Present | Description |\n|---|---|---|---|\n"
                       f"| (the payload) | {cell(md_type_text(ptype))} | always | {what} |")
        for name, t in s.get("types", {}).items():
            body = self.object_md(t)
            out.append(f"**`{name}`**: {t['summary']}\n\n" + body)
        if "example" in s:
            if s.get("example_trimmed"):
                out.append("Example, trimmed to some of the fields:")
            out.append(json_block(s["example"]))
        elif s.get("variants"):
            # No example of the whole payload: the first form's example stands for it.
            v = s["variants"][0]
            out.append(f"Example ({v['name']}):")
            out.append(json_block(v["example"]))
        out.append(self.confirm_md(shape_id("recv", ev, "payload")))
        out.append("#### Sent to")
        out.append(s["to"][0].upper() + s["to"][1:] + ".")
        senders = s.get("senders", [])
        replies = self.replies_to(ev)
        out.append("#### Sent by")
        lines = [f"- {x['what'].rstrip('.')} ({link_sources(x['source'])})." if x.get("source")
                 else f"- {x['what']}" for x in senders]
        lines.append("- In reply to: " + (", ".join(event_link(e, "send") for e in replies)
                                          if replies else "none of the events you send") + ".")
        out.append("\n".join(lines))
        return "\n\n".join(out)

    def events_of(self, s):
        """Every event that a send schema says the server sends for it."""
        evs = set()
        for _, part in self.s.parts(s):
            for r in part.get("responses", []) + part.get("also", []):
                for _, spec in forms(r):
                    if spec is not None and spec.get("event") and not r.get("no_entry"):
                        evs.add(spec["event"])
            for row in part.get("failures", {}).get("rows", []):
                if row.get("branch"):
                    continue
                for _, rep in self.s.flat_replies(row):
                    if not rep.get("close") and not rep.get("see"):
                        evs.add(self.s.failure_event(s, rep))
        if s.get("failures"):
            evs.add(s["failures"].get("event", "game_response"))
        return evs

    def replies_to(self, recv_event):
        """The send events whose schema says that they cause `recv_event`."""
        return sorted(ev for ev, s in self.s.send.items() if recv_event in self.events_of(s))

    # -- types and codes ----------------------------------------------------------------------

    def type_md(self, name):
        t = self.s.types[name]
        out = []
        if t.get("description"):
            out.append(t["description"])
        if "type" in t:
            out.append(f"**Type:** {md_type_text(t['type'])}")
        else:
            out.append("**Fields:**")
            out.append(self.object_md(t))
        if "example" in t:
            out.append("**Example:**" + (" (trimmed to some of the fields)" if t.get("example_trimmed") else ""))
            out.append(json_block(t["example"]))
        out.append(self.confirm_md(shape_id("type", key=name)))
        users = self.type_users(name)
        if users:
            out.append("**Used by:** " + ", ".join(users) + ".")
        if t.get("source"):
            out.append(f"**Source:** {link_sources(t['source'])}")
        return "\n\n".join(out)

    def send_type_texts(self, s):
        """Every type expression that a send schema uses."""
        out = []
        def shape(r):
            for f in r.get("fields", []):
                out.append(f["type"])
            for k in ("type", "extends", "code_type"):
                if r.get(k):
                    out.append(r[k])
        shape(s["request"])
        for v in variant_list(s):
            shape(v.get("request", {}))
        for _, part in self.s.parts(s):
            for r in part.get("responses", []) + part.get("also", []):
                for _, spec in forms(r):
                    if spec is not None:
                        shape(spec)
            for row in part.get("failures", {}).get("rows", []):
                if row.get("branch"):
                    continue
                for _, rep in self.s.flat_replies(row):
                    for f in rep.get("extra", []):
                        out.append(f["type"])
                    if rep.get("code_type"):
                        out.append(rep["code_type"])
        return out

    def type_users(self, name):
        """Links to the types and events whose fields name this type."""
        def uses(texts):
            return any(name in refs_of(parse_type(t)) for t in texts)

        out = []
        for other, t in self.s.types.items():
            texts = [f["type"] for f in t.get("fields", [])] + [t[k] for k in ("type", "extends") if t.get(k)]
            if other != name and uses(texts):
                out.append(f"[`{other}`](#{type_anchor(other)})")
        for ev, s in self.s.send.items():
            if uses(self.send_type_texts(s)):
                out.append(event_link(ev, "send"))
        for ev, s in self.s.recv.items():
            p = s.get("payload", {})
            texts = [f["type"] for f in p.get("fields", [])] + [p[k] for k in ("type", "extends") if p.get(k)]
            texts += [v["type"] for v in s.get("variants", [])]
            if uses(texts):
                out.append(event_link(ev, "recv"))
        return out

    def types_overview_md(self):
        rows = ["| Type | What it is |", "|---|---|"]
        for name in sorted(self.s.types):
            rows.append(f"| [`{name}`](#{type_anchor(name)}) | {cell(self.s.types[name]['summary'])} |")
        return TYPES_INTRO + "\n\n" + "\n".join(rows)

    def code_md(self, code):
        """The exact replies that carry `code`, from every send schema: the responses and the
        failure rows (each `request_id` form apart), and the `game_response` events that go to
        other characters (`also`, for example the receiver of `send`)."""
        rows = []
        # A code entry such as `<quest>_success` stands for codes built at run time: it gets the
        # replies with a `code_type` whose example code fits the pattern.
        pattern = re.compile("^" + re.sub(r"<[^>]+>", ".+", re.escape(code).replace(r"\<", "<").replace(r"\>", ">")) + "$") \
            if "<" in code else None

        def has(item):
            cs = codes_of(item)
            if code in cs:
                return True
            return bool(pattern and item.get("code_type") and any(pattern.match(c) for c in cs))

        def with_code(obj, c):
            if isinstance(obj, dict) and obj.get("response") != c and "response" in obj:
                return dict(obj, response=c)
            return obj

        for ev, s in sorted(self.s.send.items()):
            for v, part in self.s.parts(s):
                pre = "" if v is None else f"{variant_title(s, v)}: "
                for r in part.get("responses", []):
                    for label, spec in forms(r):
                        if spec is None or not has(spec) or "example" not in spec:
                            continue
                        when = pre + r["when"] + (f" ({label})" if label else "")
                        if spec.get("via"):
                            when += f" (as {spec['via']})"
                        rows.append((ev, when, spec["example"] if pattern else with_code(spec["example"], code)))
                for a in part.get("also", []):
                    if a["event"] == "game_response" and (has(a) or (
                            isinstance(a.get("example"), dict) and a["example"].get("response") == code)):
                        if "example" in a:
                            rows.append((ev, pre + a["when"] + f" (to {a['to']})", with_code(a["example"], code)))
                for row in part.get("failures", {}).get("rows", []):
                    if row.get("branch"):
                        continue
                    for label, rep in self.s.flat_replies(row):
                        if has(rep) and self.s.failure_event(s, rep) == "game_response" \
                                and not rep.get("close") and not rep.get("see"):
                            place = self.s.place(s, v, rep)[0]
                            when = pre + row["when"] + (f" ({label})" if label else "")
                            rows.append((ev, when, self.s.reply_object(place, rep, None if pattern else code)))
        # Always the section, also with no rows: every code entry has the same layout.
        out = ["#### Exact replies", "| Request | When | Payload |", "|---|---|---|"]
        if not rows:
            out.append(f"| {NONE_CELL} | None: no request in the schema sends this code as a "
                       f"direct reply. See **Sent from**. | {NONE_CELL} |")
        for ev, when, obj in rows:
            out.append(f"| {event_link(ev, 'send')} | {cell(when)} | `{cell(compact(obj))}` |")
        return "\n".join(out[:1]) + "\n\n" + "\n".join(out[1:])


# ---------------------------------------------------------------------------------------------
# The layout of an entry. Every entry of one kind has the same `####` sections in the same order,
# also when one is empty (owner, 2026-10-04: "Even on an empty payload I want the layout on all
# pages to be the same"). The renderer above makes the schema sections; the hand-written ones
# (Limits, Notes, Example, Source) come from content/*.md, and `finish_entry` adds an empty one
# ("None.") where the Markdown has none. Variant blocks (`#### Variant: ...`) sit between Also
# sent and Limits.
# ---------------------------------------------------------------------------------------------

SECTIONS = {
    "send": ["Request", "Responses", "Also sent", "Limits", "Notes", "Example", "Source"],
    "recv": ["Payload", "Sent to", "Sent by", "Notes", "Example", "Source"],
    "code": ["Exact replies"],
}
# Headings that may sit between the fixed sections (and where).
EXTRA_SECTIONS = {"send": re.compile(r"Variant: ")}
_H4 = re.compile(r"(?m)^#### (.+?)\s*$")


def finish_entry(kind, name, md):
    """Adds each missing fixed section of `kind` (as "None."), then checks that the fixed
    sections are all there, once each, in order, and that no other `####` heading is in the
    entry. A wrong order or an unknown heading is a warning, fatal under ALAPI_STRICT_TYPES=1."""
    want = SECTIONS[kind]
    heads = [m.group(1) for m in _H4.finditer(md)]
    for i, sec in enumerate(want):
        if sec in heads:
            continue
        # Put it before the next fixed section that is there, else at the end.
        nxt = next((s for s in want[i + 1:] if s in heads), None)
        block = f"#### {sec}\n\nNone.\n\n"
        if nxt is None:
            md = md.rstrip() + "\n\n" + block.rstrip()
        else:
            m = re.search(rf"(?m)^#### {re.escape(nxt)}\s*$", md)
            md = md[:m.start()] + block + md[m.start():]
        heads = [m.group(1) for m in _H4.finditer(md)]
    fixed = [h for h in heads if h in want]
    other = [h for h in heads if h not in want and not (
        kind in EXTRA_SECTIONS and EXTRA_SECTIONS[kind].match(h))]
    if fixed != want or other:
        warn(f"{kind} entry `{name}`: the sections are {heads}; every {kind} entry has "
             f"{want}, in this order, once each" + (f", and no other heading ({other})" if other else ""))
    return md


TYPES_INTRO = """\
Every field in the reference has a type. A type is a primitive, a literal value, or a named type
from this list. Each named type has its own entry.

| Notation | Meaning |
|---|---|
| `string`, `integer`, `number`, `boolean`, `null` | JSON values. `integer` is a JSON number with no fraction. |
| `any`, `object` | Any JSON value; any JSON object. |
| `"buy"`, `true`, `0` | Exactly this value. |
| `T[]` | An array of `T`. |
| `[A, B]` | An array of exactly two values: an `A`, then a `B`. |
| `Record<string, T>` | An object whose keys are strings and whose values are `T`. |
| `A \\| B` | An `A` or a `B`. |

In a request table, **Required** "no" means that you can leave the field out. In a response
table, **Present** "optional" means that the server leaves the field out in some cases. The
server sends no `undefined` values: such a field is absent from the JSON.

The schema in `schema/` (JSON files) is the source of these tables. `scripts/gen-types.py`
makes typed definitions from it (TypeScript, Python, Go, C#, Rust and Java)."""


# ---------------------------------------------------------------------------------------------
# Typed definitions (scripts/gen-types.py)
#
# `model(schema)` walks the schema once and returns a list of declarations that every language
# generator renders (scripts/gen-types.py has the other six languages): named types, then for
# each event you send its request, its replies and its failure union, then each event you
# receive. A declaration is one of
#   ("object", name, doc, {"fields": [...], "extends": base or None, "open": bool})
#   ("alias", name, doc, type_expression)
#   ("union", name, doc, [member type names or expressions])   a union of other declarations
# Inline objects (a failure reply such as {response, place, failed, extras}) become object
# declarations of their own, so that every language can name them.
# ---------------------------------------------------------------------------------------------


def pascal(name):
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[^A-Za-z0-9]+", name) if p)


class Model:
    def __init__(self, schema):
        self.schema = schema
        self.decls = []
        self.names = set()
        self.client = []    # (event, request type or None)
        self.replies = {}   # event -> [type names]: the game_response replies to a request
        self.server = {}    # event -> type name
        self.triggers = []  # (event, text): handlers that the client does not emit

    def name(self, want, first="Reply"):
        """A unique declaration name: `want`, or `want` + `first` ("Reply" for a reply that
        meets a named type of the same name), then `want` + "2", "3", ... when it is taken."""
        n, i = want, 1
        while n in self.names:
            n = want + (first if i == 1 else str(i))
            i += 1
        self.names.add(n)
        return n

    def add(self, kind, name, doc, body):
        self.decls.append((kind, name, doc, body))
        return name

    def obj(self, name, doc, spec):
        return self.add("object", name, doc, {"fields": spec.get("fields", []),
                                              "extends": spec.get("extends"),
                                              "open": bool(self.schema.is_open(spec))})


def model(schema):
    m = Model(schema)
    m.names |= set(schema.types)
    for name, t in schema.types.items():
        if "type" in t:
            m.add("alias", name, t["summary"], t["type"])
        else:
            m.obj(name, t["summary"], t)

    # Received events first get their names, so that a reply can point at them.
    recv_names = {ev: m.name(f"{pascal(ev)}Event") for ev in schema.recv}

    for ev, s in schema.send.items():
        base = pascal(ev)
        # -- the request ---------------------------------------------------------------
        req = s["request"]
        if variant_list(s):
            members = []
            for v in variant_list(s):
                full = schema.variant_request(s, v)
                vn = m.name(f"{base}Request{pascal(variant_name(v))}")
                doc = f"`{ev}`, variant {variant_name(v)}: {v['when']}"
                if full.get("type"):
                    m.add("alias", vn, doc, full["type"])
                else:
                    m.obj(vn, doc, full)
                members.append(vn)
            rname = m.add("union", m.name(f"{base}Request"), f"`{ev}`: the payload you send (one "
                          f"of the variants, by `{s['variants']['key']}`).", members)
        elif req.get("type"):
            rname = m.add("alias", m.name(f"{base}Request"), f"`{ev}`: the payload you send.", req["type"])
        elif req.get("fields"):
            rname = m.obj(m.name(f"{base}Request"), f"`{ev}`: the payload you send.", req)
        else:
            rname = None
        if s.get("trigger"):
            m.triggers.append((ev, s["trigger"]))
        else:
            m.client.append((ev, rname))

        # -- replies -------------------------------------------------------------------
        gr = []  # the game_response replies (for ClientReplies)
        for v, part in schema.parts(s):
            for r in part.get("responses", []):
                if r.get("kind"):
                    continue
                want = f"{base}{pascal(r['name'])}"
                fs = [(label, spec) for label, spec in forms(r) if spec is not None and not spec.get("kind")]
                made = []
                for label, spec in fs:
                    n = m.name(want + (pascal(label.replace("`", "")) if label and len(fs) > 1 else ""))
                    doc = f"`{ev}` reply{' (' + label.replace('`', '') + ')' if label else ''}: {r['when']}"
                    t = response_decl(m, n, doc, spec, recv_names)
                    if t:
                        made.append(t)
                        if spec.get("event") == "game_response":
                            gr.append(t)
                if len(made) > 1:
                    m.add("union", m.name(want), f"`{ev}` reply: {r['when']}", made)

        # -- failures ------------------------------------------------------------------
        members = []
        seen = {}
        for v, part in schema.parts(s):
            for row in part.get("failures", {}).get("rows", []):
                if row.get("branch"):
                    continue
                for label, rep in schema.flat_replies(row):
                    if rep.get("close") or rep.get("see") or schema.failure_event(s, rep) != "game_response":
                        continue
                    fields = failure_fields(schema, s, v, rep)
                    if fields is None:  # a bare string
                        key = ("bare", code_type_of(rep))
                        if key not in seen:
                            seen[key] = code_type_of(rep)
                            members.append(code_type_of(rep))
                        continue
                    key = json.dumps(fields, sort_keys=True)
                    if key in seen:
                        continue
                    codes = codes_of(rep)
                    if codes and not rep.get("code_type"):
                        suffix = pascal(codes[0])
                    else:
                        # No fixed code: name it after a literal `reason`, if it has one.
                        reason = next((parse_type(f["type"]) for f in fields if f["name"] == "reason"), None)
                        suffix = pascal(str(reason[1])) if reason and reason[0] == "lit" else "Reply"
                    n = m.name(f"{base}Failure{suffix}", "2")
                    m.obj(n, f"`{ev}` failure: {row['when']}", {"fields": fields})
                    seen[key] = n
                    members.append(n)
        if members:
            fname = m.add("union", m.name(f"{base}Failure"), f"`{ev}`: every failure reply on "
                          f"`game_response`, in check order.", members)
            gr.append(fname)
        if gr:
            m.replies[ev] = list(dict.fromkeys(gr))

    for ev, s in schema.recv.items():
        p = s.get("payload", {})
        n = recv_names[ev]
        doc = f"`{ev}`: the payload you receive."
        if p.get("fields") or p.get("extends"):
            m.obj(n, doc, p)
        else:
            m.add("alias", n, doc, p.get("type", "any"))
        m.server[ev] = n
    return m


def response_decl(m, n, doc, spec, recv_names):
    """The declaration of one reply shape; returns its name, or None when the reply has no
    shape of its own (a big payload that its receive entry describes: then an alias to it)."""
    if spec.get("fields") or spec.get("extends"):
        return m.obj(n, doc, spec)
    if spec.get("type"):
        return m.add("alias", n, doc, spec["type"])
    if spec.get("event") in recv_names:
        return m.add("alias", n, doc, recv_names[spec["event"]])
    return None


def failure_fields(schema, s, v, rep):
    """The fields of one failure reply as an object (None for a bare string)."""
    form = rep.get("form", "failure")
    if form == "bare":
        return None
    fields = []
    if form != "object":
        fields.append({"name": "response", "type": code_type_of(rep), "description": "The code."})
    if form == "failure":
        fields.append({"name": "place", "type": schema.place(s, v, rep)[1], "description": "The place."})
        fields.append({"name": "failed", "type": "true", "description": "Always true."})
    names = {f["name"] for f in fields}
    for f in rep.get("extra", []):
        if f["name"] in names:
            fields = [x for x in fields if x["name"] != f["name"]]
        fields.append({k: f[k] for k in ("name", "type", "description", "optional") if k in f})
    return fields


# -- TypeScript --------------------------------------------------------------------------------

def ts_type(tree):
    kind = tree[0]
    if kind == "prim":
        return {"integer": "number", "object": "Record<string, unknown>", "any": "unknown"}.get(tree[1], tree[1])
    if kind == "lit":
        return json.dumps(tree[1])
    if kind == "ref":
        return tree[1]
    if kind == "array":
        inner = ts_type(tree[1])
        return f"({inner})[]" if tree[1][0] == "union" else f"{inner}[]"
    if kind == "record":
        return f"Record<string, {ts_type(tree[1])}>"
    if kind == "tuple":
        return "[" + ", ".join(ts_type(t) for t in tree[1]) + "]"
    if kind == "union":
        return " | ".join(ts_type(t) for t in tree[1])
    raise ValueError(tree)


def ts_doc(text, indent=""):
    text = re.sub(r"\s+", " ", text).strip().replace("*/", "* /")
    return f"{indent}/** {text} */\n"


def ts_key(name):
    return name if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name) else json.dumps(name)


def typescript(schema):
    """TypeScript definitions for every type and every event in the schema."""
    m = model(schema)
    out = ["// Generated by scripts/gen-types.py from schema/. Do not edit by hand.\n"
           "// docs/WRITING.md, \"Typed definitions from the schema\", says how each part maps.\n"]
    for kind, name, doc, body in m.decls:
        if kind == "alias":
            out.append(ts_doc(doc) + f"export type {name} = {ts_type(parse_type(body))};\n")
        elif kind == "union":
            out.append(ts_doc(doc) + f"export type {name} =\n  | " +
                       "\n  | ".join(ts_type(parse_type(x)) for x in body) + ";\n")
        else:
            ext = ""
            if body.get("extends"):
                # A field that replaces a base field with a type that is not narrower (start's
                # `code`) would break `extends`; Omit<> takes the base field out first.
                base_names = {f["name"] for f in schema.all_fields(schema.types[body["extends"]])}
                over = [f["name"] for f in body["fields"] if f["name"] in base_names]
                ext = f" extends {body['extends']}" if not over else \
                    f" extends Omit<{body['extends']}, {' | '.join(json.dumps(n) for n in over)}>"
            text = ts_doc(doc) + f"export interface {name}{ext} {{\n"
            for f in body["fields"]:
                opt = "?" if f.get("optional") else ""
                fdoc = f.get("description", "") + (f" @default {compact(f['default'])}" if "default" in f else "")
                text += ts_doc(fdoc, "  ")
                text += f"  {ts_key(f['name'])}{opt}: {ts_type(parse_type(f['type']))};\n"
            if body["open"]:
                text += "  [key: string]: unknown;\n"
            out.append(text + "}\n")
    out.append("/** Client to server: event name -> the payload you send (`void`: no payload). */\n"
               "export interface ClientEvents {\n" +
               "".join(f"  {json.dumps(e)}: {t or 'void'};\n" for e, t in m.client) + "}\n")
    out.append("/** The `game_response` payloads that answer each event you send: its replies and "
               "its failures. Replies on other events are in each event's types. */\n"
               "export interface ClientReplies {\n" +
               "".join(f"  {json.dumps(e)}: {' | '.join(ts)};\n" for e, ts in m.replies.items()) + "}\n")
    out.append("/** Server to client: event name -> payload. */\nexport interface ServerEvents {\n" +
               "".join(f"  {json.dumps(e)}: {t};\n" for e, t in m.server.items()) + "}\n")
    if m.triggers:
        out.append("/** Handlers on the server that the client does not emit: "
                   + "; ".join(f"`{e}`: {re.sub(r'[*]', '', t)}" for e, t in m.triggers).replace("*/", "* /")
                   + " */\nexport type ServerHandlersNotEmitted = " +
                   " | ".join(json.dumps(e) for e, _ in m.triggers) + ";\n")
    return "\n".join(out)
