#!/usr/bin/env python3
"""Writes the socket API as an AsyncAPI 3.0 document (JSON), so that code generators and doc
tools (AsyncAPI Studio, @asyncapi/generator, Modelina, ...) can read it.

    python3 scripts/gen-asyncapi.py                  # writes site/asyncapi.json
    python3 scripts/gen-asyncapi.py -o OUT.json      # somewhere else ("-" for stdout)

Python 3 standard library only. It reads the schema through apischema.py (Schema() and its
helpers: parts, forms, flat_replies, failure_fields, variant_request, place, reply_object,
shape_id, Shape.state), never the JSON files directly, so it sees exactly what the page and the
typed definitions see. scripts/check-asyncapi.py validates the output with the official parser.

How the schema maps (docs/WRITING.md, "AsyncAPI export"):

    schema/types.json, event "types"   components.schemas.<Name>
    send request                       components.schemas.<Event>Request (variants: one schema
                                       per variant + a oneOf with a `discriminator`)
                                       components.messages["send.<event>"]
                                       operations["send.<event>"] (action: send)
    send responses (+ request_id form) components.schemas.<Event><Name>[With|Without]RequestId
                                       components.messages["reply.<event>.<name>[.with|.without]"]
    send failures on game_response     components.schemas.<Event>Failure (union of every form)
                                       components.messages["fail.<event>"]
    failures on another event          components.messages["fail.<event>.<other event>"]
    the replies                        operations["send.<event>"].reply.messages
    send also, order, failure rows     x-al-also, x-al-order, x-al-failures on the operation
    recv payload (+ variants)          components.schemas.<Event>Event
                                       components.messages["recv.<event>"]
                                       operations["receive.<event>"] (action: receive)
    `confirm` and schema/live.json     x-al-confirm on each schema / message (Shape.state())

Everything goes through one channel, `socket`: Socket.IO has one connection per game server and
tells events apart by name. The message `name` is the Socket.IO event name; the message key (the
`send.` / `reply.` / `recv.` prefix) keeps the two directions apart (`eval`, `friend`, ... exist
both ways).

Hard-coded on purpose (they are facts of the protocol, not of the schema): the Engine.IO query
(`EIO=4&transport=websocket`), the game's own query (`map_protocol=1&no_graphics=1`), and the
example server address and path (from content/connect.md, "Connecting to a game server").
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import apischema  # noqa: E402  (the path insert above makes the repo root importable)
from apischema import (parse_type, pascal, forms, codes_of, code_type_of, variant_list,  # noqa: E402
                       variant_name, variant_id, failure_fields, shape_id, FORM_SUFFIX)

ASYNCAPI = "3.0.0"
CHANNEL = "socket"
REF_CHANNEL = {"$ref": f"#/channels/{CHANNEL}"}
SCHEMA_REF = "#/components/schemas/"

# The JSON value classes that tell union members apart ("integer" is a "number").
ALL_TYPES = frozenset({"string", "number", "boolean", "null", "object", "array"})
JTYPE = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean",
         "null": "null", "object": "object", "array": "array"}


def key(text):
    """A component / message / operation key: AsyncAPI 3 allows [A-Za-z0-9._-] only, so `o:home`
    becomes `o_home`. The message `name` keeps the real event name."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", text)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "x"


def jtype_of(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if value is None:
        return "null"
    return {str: "string", list: "array", dict: "object"}[type(value)]


def summaries():
    """The one-line summary of each entry, from content/*.md: the line after `### \\`event\\``.
    The schema files have no summary of their own; the Markdown entries do."""
    out = {"send": {}, "recv": {}}
    files = {"send": sorted((ROOT / "content").glob("send-*.md")),
             "recv": [ROOT / "content" / "receive.md"]}
    for kind, paths in files.items():
        for p in paths:
            lines = p.read_text().splitlines()
            for i, line in enumerate(lines):
                m = re.match(r"^### `([^`]+)`\s*$", line)
                if m and i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith("<!--"):
                    out[kind].setdefault(m.group(1), lines[i + 1].strip())
    return out


class Gen:
    def __init__(self, schema):
        self.s = schema
        self.schemas = {}       # components.schemas
        self.messages = {}      # components.messages (and the channel's messages)
        self.operations = {}
        self.names = set()      # schema names in use
        self.summary = summaries()

    # -- names and refs ---------------------------------------------------------------------------

    def name(self, want, first="Reply"):
        """A unique schema name (the rule of apischema.Model.name): `want`, then `want` + `first`,
        then `want` + 2, 3, ..."""
        n, i = want, 1
        while n in self.names:
            n = want + (first if i == 1 else str(i))
            i += 1
        self.names.add(n)
        return n

    def put(self, name, schema):
        self.schemas[name] = schema
        return {"$ref": SCHEMA_REF + name}

    def resolve(self, js, depth=0):
        while isinstance(js, dict) and "$ref" in js and depth < 50:
            js = self.schemas.get(js["$ref"][len(SCHEMA_REF):], {})
            depth += 1
        return js

    # -- confirmation ------------------------------------------------------------------------------

    def confirm(self, sid):
        """x-al-confirm: what is confirmed about one shape (apischema Shape.state(), trimmed to the
        keys that say something). Tolerates a schema without `confirm` keys yet."""
        sh = self.s.shape(sid) if hasattr(self.s, "shape") else None
        if sh is None:
            return None
        st = sh.state()
        out = {"shapeId": sid, "confirmed": st["confirmed"], "inCode": st["in_code"],
               "live": st["live"]}
        for k_in, k_out in (("code", "code"), ("live_needed", "liveNeeded"), ("note", "note"),
                            ("count", "liveCaptures"), ("last", "lastCapture"),
                            ("mismatches", "liveMismatches")):
            if st.get(k_in):
                out[k_out] = st[k_in]
        if st["missing"]:
            out["missing"] = True
        return out

    def tag(self, js, sid):
        """Adds x-al-shape-id and x-al-confirm to a schema or message, in place."""
        js["x-al-shape-id"] = sid
        c = self.confirm(sid)
        if c:
            js["x-al-confirm"] = c
        return js

    # -- type expressions -> JSON Schema -----------------------------------------------------------

    def tree(self, tree):
        kind = tree[0]
        if kind == "prim":
            p = tree[1]
            if p == "any":
                return {}
            return {"type": p}
        if kind == "lit":
            return {"type": "integer" if isinstance(tree[1], int) and not isinstance(tree[1], bool)
                    else jtype_of(tree[1]), "const": tree[1]}
        if kind == "ref":
            return {"$ref": SCHEMA_REF + tree[1]}
        if kind == "array":
            return {"type": "array", "items": self.tree(tree[1])}
        if kind == "tuple":
            # Draft-07 tuple form (AsyncAPI Schema is a superset of JSON Schema draft-07).
            return {"type": "array", "items": [self.tree(t) for t in tree[1]],
                    "minItems": len(tree[1]), "maxItems": len(tree[1]), "additionalItems": False}
        if kind == "record":
            return {"type": "object", "additionalProperties": self.tree(tree[1])}
        if kind == "union":
            lits = [t[1] for t in tree[1] if t[0] == "lit"]
            rest = [t for t in tree[1] if t[0] != "lit"]
            members = [self.tree(t) for t in rest]
            if lits:
                types = sorted({jtype_of(v) for v in lits})
                enum = {"enum": lits}
                if len(types) == 1:
                    enum = {"type": types[0], "enum": lits}
                if not rest:
                    return enum
                members.append(enum)
            return self.union(members)
        raise ValueError(tree)

    def expr(self, text):
        return self.tree(parse_type(text))

    # -- unions: oneOf only when the members cannot overlap -------------------------------------

    def sig(self, js):
        """What a schema can match, for the overlap test: ("lits", {(type, value)}), ("obj",
        {required literal fields}), or ("types", set of JSON value classes)."""
        js = self.resolve(js)
        if "const" in js:
            return ("lits", {(jtype_of(js["const"]), json.dumps(js["const"]))})
        if "enum" in js:
            return ("lits", {(jtype_of(v), json.dumps(v)) for v in js["enum"]})
        for k in ("oneOf", "anyOf"):
            if k in js:
                types = set()
                for m in js[k]:
                    s = self.sig(m)
                    types |= s[1] if s[0] == "types" else {t for t, _ in s[1]} if s[0] == "lits" else {"object"}
                return ("types", types)
        t = js.get("type")
        if t == "object" and "properties" in js:
            req = set(js.get("required", []))
            lits = {}
            for n, p in js["properties"].items():
                p = self.resolve(p)
                if n in req and ("const" in p or "enum" in p):
                    lits[n] = {json.dumps(v) for v in ([p["const"]] if "const" in p else p["enum"])}
            return ("obj", lits)
        if t:
            return ("types", {JTYPE[t]})
        return ("types", set(ALL_TYPES))

    def overlap(self, a, b):
        a, b = self.sig(a), self.sig(b)
        if a[0] == "obj" and b[0] == "obj":
            # Two object shapes are apart when one required literal field has no common value.
            return not any(n in b[1] and not (a[1][n] & b[1][n]) for n in a[1])
        if a[0] == "lits" and b[0] == "lits":
            return bool(a[1] & b[1])

        def types(s):
            return {t for t, _ in s[1]} if s[0] == "lits" else {"object"} if s[0] == "obj" else s[1]
        if a[0] == "lits" or b[0] == "lits":
            lits, other = (a, b) if a[0] == "lits" else (b, a)
            return bool({t for t, _ in lits[1]} & types(other))
        return bool(types(a) & types(b))

    def discriminator(self, members):
        """The property that tells object members apart: required in each, a literal in each,
        and no value shared. AsyncAPI's `discriminator` is that property's name."""
        objs = [self.resolve(m) for m in members]
        if len(objs) < 2 or not all(o.get("type") == "object" and "properties" in o for o in objs):
            return None
        sigs = [self.sig(o)[1] for o in objs]
        for prop in sigs[0]:
            if all(prop in s for s in sigs):
                seen = set()
                ok = True
                for s in sigs:
                    if seen & s[prop]:
                        ok = False
                        break
                    seen |= s[prop]
                if ok:
                    return prop
        return None

    def union(self, members, discriminate=True):
        if len(members) == 1:
            return members[0]
        apart = all(not self.overlap(a, b) for i, a in enumerate(members) for b in members[i + 1:])
        out = {"oneOf" if apart else "anyOf": members}
        if apart and discriminate:
            d = self.discriminator(members)
            if d:
                out["discriminator"] = d
        return out

    # -- objects and fields ------------------------------------------------------------------------

    def field(self, f):
        js = dict(self.expr(f["type"]))
        if f.get("description"):
            # Next to a $ref this is an annotation that draft-07 validators ignore and doc tools
            # show; the reason it is not wrapped in allOf is that code generators then make one
            # type per property.
            js["description"] = f["description"]
        if "default" in f:
            js["default"] = f["default"]
        if "example" in f:
            js["examples"] = [f["example"]]
        if f.get("coerce"):
            js["x-al-coerce"] = f["coerce"]
        return js

    def obj(self, fields, open_, extends=None):
        """An object schema from a field list (already flattened with Schema.all_fields).
        `extends` is flattened, not allOf: a field may replace a base field with a type that is
        not narrower, and a closed base (`additionalProperties: false`) would reject the new
        fields under allOf. x-al-extends keeps the name of the base."""
        js = {"type": "object", "properties": {f["name"]: self.field(f) for f in fields}}
        # Required unless `optional` is true, as in the TypeScript types: apischema's own fields
        # (failure_fields' response/place/failed, a narrowed variant key) have no `optional`.
        req = [f["name"] for f in fields if not f.get("optional")]
        if req:
            js["required"] = req
        js["additionalProperties"] = bool(open_)
        if extends:
            js["x-al-extends"] = {"$ref": SCHEMA_REF + extends}
        return js

    def spec_schema(self, spec):
        """A shape spec (fields/extends, or type, or a summary that points at a recv event)."""
        if spec.get("fields") or spec.get("extends"):
            return self.obj(self.s.all_fields(spec), self.s.is_open(spec), spec.get("extends"))
        if spec.get("type"):
            return self.expr(spec["type"])
        ev = spec.get("event")
        if ev in self.s.recv:
            return {"$ref": SCHEMA_REF + self.recv_names[ev]}
        return {}

    # -- named types -------------------------------------------------------------------------------

    def types(self):
        self.names |= set(self.s.types)
        for n, t in self.s.types.items():
            if "type" in t:
                js = dict(self.expr(t["type"]))
            else:
                js = self.obj(self.s.all_fields(t), self.s.is_open(t), t.get("extends"))
            out = {"title": n, "description": " ".join(x for x in (t.get("summary"), t.get("description")) if x)}
            out.update(js)
            if "example" in t:
                out["examples"] = [t["example"]]
                if t.get("example_trimmed"):
                    out["x-al-example-trimmed"] = True
            if t.get("source"):
                out["x-al-source"] = t["source"]
            self.put(n, self.tag(out, shape_id("type", key=n)))

    # -- events you receive ------------------------------------------------------------------------

    def recv(self):
        for ev, s in self.s.recv.items():
            name = self.recv_names[ev]
            p = s.get("payload") or {}
            sid = shape_id("recv", ev, "payload")
            variants = s.get("variants") or []
            if variants:
                members = []
                for i, v in enumerate(variants, 1):
                    m = dict(self.expr(v["type"]))
                    m.update({"title": v.get("name") or f"Variant {i}", "description": v.get("when", "")})
                    if "example" in v:
                        m["examples"] = [v["example"]]
                    for k in ("has", "reply_to", "source"):
                        if v.get(k):
                            m[f"x-al-{k.replace('_', '-')}"] = v[k]
                    self.tag(m, shape_id("recv", ev, "variant", v.get("name") or i))
                    members.append(m)
                js = self.union(members)
            else:
                js = dict(self.spec_schema(p) if (p.get("fields") or p.get("extends")) else
                          self.expr(p.get("type", "any")))
            js = dict({"title": name, "description": f"`{ev}`: the payload you receive."}, **js)
            if s.get("example") is not None:
                js["examples"] = [s["example"]]
            self.put(name, self.tag(js, sid))

            examples = []
            if "example" in s:
                examples.append({"name": "example", "payload": s["example"]})
            for i, v in enumerate(variants, 1):
                if "example" in v:
                    examples.append({"name": slug(v.get("name") or i), "summary": v.get("name") or f"Variant {i}",
                                     "payload": v["example"]})
            msg = {"name": ev, "title": f"{ev} (server to client)",
                   "summary": self.summary["recv"].get(ev, f"The `{ev}` event."),
                   "contentType": "application/json",
                   "payload": {"$ref": SCHEMA_REF + name}}
            if examples:
                msg["examples"] = examples
            if s.get("example_trimmed"):
                msg["x-al-example-trimmed"] = True
            if s.get("to"):
                msg["x-al-to"] = s["to"]
            if s.get("senders"):
                msg["x-al-senders"] = s["senders"]
            mkey = f"recv.{key(ev)}"
            self.messages[mkey] = self.tag(msg, sid)
            self.operations[f"receive.{key(ev)}"] = {
                "action": "receive", "channel": REF_CHANNEL,
                "title": f"Receive {ev}", "summary": msg["summary"],
                "messages": [{"$ref": f"#/channels/{CHANNEL}/messages/{mkey}"}]}

    # -- events you send ---------------------------------------------------------------------------

    def message(self, mkey, msg):
        self.messages[mkey] = msg
        return {"$ref": f"#/channels/{CHANNEL}/messages/{mkey}"}

    def sample(self, tree, name):
        """A value of the right type for a field without an `example` (the page shows the
        placeholder "<name>", which is not valid for a number)."""
        kind = tree[0]
        if kind == "lit":
            return tree[1]
        if kind == "prim":
            return {"integer": 0, "number": 0, "boolean": False, "null": None, "object": {}}.get(tree[1], f"<{name}>")
        if kind == "ref":
            t = self.s.types[tree[1]]
            return self.sample(parse_type(t["type"]), name) if "type" in t else t.get("example", {})
        if kind == "union":
            return self.sample(tree[1][0], name)
        return [] if kind in ("array", "tuple") else {}

    def fix_placeholders(self, ex, rep):
        """apischema.reply_object fills a field that has no example with "<name>"; replace it with
        a value of the field's type, so that the example validates."""
        if not isinstance(ex, dict):
            return ex
        for f in rep.get("extra", []):
            if f["name"] in ex and "example" not in f and ex[f["name"]] == f"<{f['name']}>":
                ex[f["name"]] = self.sample(parse_type(f["type"]), f["name"])
        return ex

    def correlate(self, msg, payload_js):
        """A reply that copies `request_id` back: an AsyncAPI correlationId on it."""
        p = self.resolve(payload_js)
        if "request_id" in p.get("properties", {}):
            msg["correlationId"] = {"description": "The server copies `request_id` of the request.",
                                    "location": "$message.payload#/request_id"}

    def send(self):
        for ev, s in self.s.send.items():
            base = pascal(ev)
            reply_refs, no_reply, also_out, failures_out, order = [], [], [], [], {}

            # -- the request ----------------------------------------------------------------
            req = s["request"]
            vl = variant_list(s)
            if vl:
                members = []
                for v in vl:
                    full = self.s.variant_request(s, v)
                    vn = self.name(f"{base}Request{pascal(variant_name(v))}")
                    js = dict(self.expr(full["type"])) if full.get("type") else \
                        self.obj(full["fields"], False)
                    js = dict({"title": vn, "description": f"`{ev}`, variant {variant_name(v)}: {v.get('when', '')}"}, **js)
                    if "example" in full:
                        js["examples"] = [full["example"]]
                    if v.get("match"):
                        js["x-al-match"] = v["match"]
                    if v.get("other"):
                        js["x-al-other"] = True
                    self.tag(js, shape_id("send", ev, "request", variant=variant_id(v)))
                    members.append(self.put(vn, js))
                rjs = self.union(members)
                rjs.setdefault("x-al-variant-key", s["variants"]["key"])
            elif req.get("type"):
                rjs = dict(self.expr(req["type"]))
            elif req.get("fields"):
                rjs = self.obj(req["fields"], False)
            else:
                rjs = None
            rname = None
            if rjs is not None:
                rname = self.name(f"{base}Request")
                rjs = dict({"title": rname, "description": f"`{ev}`: the payload you send."}, **rjs)
                if "example" in req:
                    rjs["examples"] = [req["example"]]
                for k in ("others", "note"):
                    if req.get(k):
                        rjs[f"x-al-{k}"] = req[k]
                self.put(rname, self.tag(rjs, shape_id("send", ev, "request")))

            # -- responses ------------------------------------------------------------------
            for v, part in self.s.parts(s):
                vid = None if v is None else variant_id(v)
                vtag = {} if v is None else {"x-al-variant": variant_name(v)}
                for r in part.get("responses", []):
                    rn = r.get("name", "Reply")
                    if r.get("kind"):
                        no_reply.append(dict({"name": rn, "kind": r["kind"], "when": r.get("when", ""),
                                              "shapeId": shape_id("send", ev, "response", rn, vid)}, **vtag))
                        continue
                    two = any(k in r for k in FORM_SUFFIX)
                    for label, spec in forms(r):
                        suffix = None
                        if two:
                            suffix = "with" if label.startswith("With ") else "without"
                        sid = shape_id("send", ev, "response", rn, vid, suffix)
                        if spec is None or spec.get("kind"):
                            no_reply.append(dict({"name": rn, "form": suffix, "kind": (spec or {}).get("kind", "none"),
                                                  "when": r.get("when", ""), "shapeId": sid}, **vtag))
                            continue
                        js = dict(self.spec_schema(spec))
                        if "$ref" not in js:
                            n = self.name(base + pascal(rn) + ({"with": "WithRequestId", "without": "WithoutRequestId"}.get(suffix, "")))
                            js = dict({"title": n, "description": f"`{ev}` reply ({rn}{', ' + label.replace('`', '') if label else ''}): {r.get('when', '')}"}, **js)
                            if "example" in spec:
                                js["examples"] = [spec["example"]]
                            payload = self.put(n, self.tag(js, sid))
                        else:
                            payload = js
                        msg = {"name": spec.get("event", "game_response"),
                               "title": f"{ev}: {rn}" + (f" ({label.replace('`', '')})" if label else ""),
                               "summary": r.get("when", ""), "contentType": "application/json",
                               "payload": payload}
                        if "example" in spec:
                            msg["examples"] = [{"name": slug(rn), "payload": spec["example"]}]
                        if spec.get("example_trimmed") or r.get("example_trimmed"):
                            msg["x-al-example-trimmed"] = True
                        if codes_of(spec):
                            msg["x-al-codes"] = codes_of(spec)
                        if spec.get("code_type"):
                            msg["x-al-code-type"] = spec["code_type"]
                        for k in ("via", "note", "source"):
                            if spec.get(k) or r.get(k):
                                msg[f"x-al-{k}"] = spec.get(k) or r.get(k)
                        msg.update(vtag)
                        self.correlate(msg, payload)
                        # reply.<event>[.<variant>].<name>[.with|.without]; a counter only if two
                        # names slug to the same key.
                        mkey = (f"reply.{key(ev)}" + (f".{slug(vid)}" if vid is not None else "")
                                + f".{slug(rn)}" + (f".{suffix}" if suffix else ""))
                        k0, i = mkey, 2
                        while mkey in self.messages:
                            mkey, i = f"{k0}.{i}", i + 1
                        reply_refs.append(self.message(mkey, self.tag(msg, sid)))

            # -- failures -------------------------------------------------------------------
            members, seen, examples, other = [], {}, [], {}
            for v, part in self.s.parts(s):
                vid = None if v is None else variant_id(v)
                for n_row, row in enumerate(part.get("failures", {}).get("rows", []), 1):
                    if row.get("branch"):
                        failures_out.append({"n": n_row, "branch": True, "when": row.get("when", ""),
                                             **({"variant": variant_name(v)} if v else {})})
                        continue
                    sid = shape_id("send", ev, "failure", n_row, vid)
                    rep_out = []
                    for rep in self.s.replies(row):
                        for label, spec in forms(rep):
                            entry = {}
                            if label:
                                entry["requestId"] = "with" if label.startswith("With ") else "without"
                            if spec is None:
                                entry["none"] = True
                                rep_out.append(entry)
                                continue
                            ev_out = self.s.failure_event(s, spec)
                            entry["event"] = ev_out
                            for k in ("note",):
                                if spec.get(k):
                                    entry[k] = spec[k]
                            if spec.get("close"):
                                entry["close"] = True
                                rep_out.append(entry)
                                continue
                            if spec.get("see"):
                                entry["see"] = spec["see"]
                                rep_out.append(entry)
                                continue
                            if codes_of(spec):
                                entry["codes"] = codes_of(spec)
                            if spec.get("code_type"):
                                entry["codeType"] = spec["code_type"]
                            place = self.s.place(s, v, spec)
                            if ev_out != "game_response":
                                # A failure on another event (disappear, game_log): one message
                                # per event, with the payload of its receive schema.
                                mkey = f"fail.{key(ev)}.{key(ev_out)}"
                                if mkey not in other:
                                    pl = {"$ref": SCHEMA_REF + self.recv_names[ev_out]} if ev_out in self.recv_names else {}
                                    other[mkey] = {"name": ev_out, "title": f"{ev}: failure on {ev_out}",
                                                   "summary": f"A failure of `{ev}` that arrives as `{ev_out}`.",
                                                   "contentType": "application/json", "payload": pl,
                                                   "examples": []}
                                if "example" in spec:
                                    other[mkey]["examples"].append({"name": f"row_{n_row}", "summary": row.get("when", ""),
                                                                    "payload": spec["example"]})
                                entry["message"] = {"$ref": f"#/channels/{CHANNEL}/messages/{mkey}"}
                                rep_out.append(entry)
                                continue
                            entry["form"] = spec.get("form", "failure")
                            if entry["form"] != "bare":
                                entry["place"] = place[0]
                            fields = failure_fields(self.s, s, v, spec)
                            if fields is None:
                                k = ("bare", code_type_of(spec))
                                if k not in seen:
                                    seen[k] = True
                                    members.append(self.expr(code_type_of(spec)))
                            else:
                                k = json.dumps(fields, sort_keys=True)
                                if k not in seen:
                                    codes = codes_of(spec)
                                    if codes and not spec.get("code_type"):
                                        sfx = pascal(codes[0])
                                    else:
                                        reason = next((parse_type(f["type"]) for f in fields if f["name"] == "reason"), None)
                                        sfx = pascal(str(reason[1])) if reason and reason[0] == "lit" else "Reply"
                                    fname = self.name(f"{base}Failure{sfx}", "2")
                                    fjs = dict({"title": fname, "description": f"`{ev}` failure: {row.get('when', '')}"},
                                               **self.obj(fields, False))
                                    seen[k] = self.put(fname, fjs)
                                    members.append(seen[k])
                                entry["schema"] = seen[k]
                            for c in (codes_of(spec) or [None]):
                                ex = self.fix_placeholders(self.s.reply_object(place[0], spec, c), spec)
                                if ex is not None:
                                    examples.append({"name": f"row_{n_row}" + (f"_{slug(c)}" if c else "")
                                                     + (f"_{entry['requestId']}" if label else ""),
                                                     "summary": row.get("when", ""), "payload": ex})
                            rep_out.append(entry)
                    out = {"n": n_row, "when": row.get("when", ""), "replies": rep_out, "shapeId": sid}
                    if v:
                        out["variant"] = variant_name(v)
                    if row.get("source"):
                        out["source"] = row["source"]
                    c = self.confirm(sid)
                    if c:
                        out["confirm"] = c
                    failures_out.append(out)
            if members:
                fname = self.name(f"{base}Failure")
                fjs = dict({"title": fname, "description": f"`{ev}`: every failure reply on `game_response`, "
                            "in check order. Bare strings are the code alone."}, **self.union(members))
                fref = self.put(fname, fjs)
                msg = {"name": "game_response", "title": f"{ev}: failure",
                       "summary": f"A failed `{ev}`: `game_response` with one of the codes in x-al-failures.",
                       "contentType": "application/json", "payload": fref}
                if examples:
                    msg["examples"] = examples
                self.correlate(msg, fref)
                reply_refs.append(self.message(f"fail.{key(ev)}", msg))
            for mkey, msg in other.items():
                if not msg["examples"]:
                    del msg["examples"]
                reply_refs.append(self.message(mkey, msg))

            # -- also-sent events and order -------------------------------------------------
            for v, part in self.s.parts(s):
                vid = None if v is None else variant_id(v)
                for i, a in enumerate(part.get("also", []), 1):
                    sid = shape_id("send", ev, "also", i, vid)
                    entry = {"event": a.get("event"), "to": a.get("to", ""), "when": a.get("when", ""),
                             "shapeId": sid}
                    for k in ("name", "summary", "via", "source"):
                        if a.get(k):
                            entry[k] = a[k]
                    if codes_of(a):
                        entry["codes"] = codes_of(a)
                    if v:
                        entry["variant"] = variant_name(v)
                    js = self.spec_schema(a)
                    if js and "$ref" not in js:
                        an = self.name(f"{base}Also{pascal(a.get('name') or a.get('event'))}")
                        js = dict({"title": an, "description": f"`{ev}` also sends `{a.get('event')}` "
                                   f"({a.get('to', '')}): {a.get('when', '')}"}, **js)
                        if "example" in a:
                            js["examples"] = [a["example"]]
                        js = self.put(an, self.tag(js, sid))
                    if js:
                        entry["payload"] = js
                    if "example" in a:
                        entry["example"] = a["example"]
                    if a.get("event") in self.s.recv:
                        entry["message"] = {"$ref": f"#/channels/{CHANNEL}/messages/recv.{key(a['event'])}"}
                    c = self.confirm(sid)
                    if c:
                        entry["confirm"] = c
                    also_out.append(entry)
                if part.get("order"):
                    order[variant_name(v) if v else "shared"] = part["order"]

            # -- the message and the operation ----------------------------------------------
            msg = {"name": ev, "title": f"{ev} (client to server)",
                   "summary": self.summary["send"].get(ev, f"The `{ev}` event."),
                   "contentType": "application/json"}
            if rname:
                msg["payload"] = {"$ref": SCHEMA_REF + rname}
                ex = []
                if "example" in req:
                    ex.append({"name": "example", "payload": req["example"]})
                for v in vl:
                    vex = (v.get("request") or {}).get("example")
                    if vex is not None and vex != req.get("example"):
                        ex.append({"name": slug(variant_name(v)), "summary": f"Variant {variant_name(v)}",
                                   "payload": vex})
                if ex:
                    msg["examples"] = ex
                self.correlate(msg, msg["payload"])
            elif s.get("trigger"):
                msg["description"] = "The client does not emit this event: " + s["trigger"] + (
                    " " + req["note"] if req.get("note") else "")
            else:
                msg["description"] = "No payload: `socket.emit(\"" + ev + "\")`." + (
                    " " + req["note"] if req.get("note") else "")
            if s.get("source"):
                msg["x-al-source"] = s["source"]
            if s.get("trigger"):
                msg["x-al-trigger"] = s["trigger"]
            mref = self.message(f"send.{key(ev)}", self.tag(msg, shape_id("send", ev, "request")))
            if s.get("trigger"):
                continue  # a server handler that the client does not emit: no send operation
            op = {"action": "send", "channel": REF_CHANNEL, "title": f"Send {ev}",
                  "summary": msg["summary"], "messages": [mref]}
            if reply_refs:
                op["reply"] = {"channel": REF_CHANNEL, "messages": reply_refs}
            if vl:
                op["x-al-variants"] = {
                    "key": s["variants"]["key"],
                    **({"intro": s["variants"]["intro"]} if s["variants"].get("intro") else {}),
                    "list": [{k2: x for k2, x in (("name", variant_name(v)), ("value", v.get("value")),
                                                  ("other", v.get("other")), ("match", v.get("match")),
                                                  ("sameAs", v.get("same_as")), ("when", v.get("when")))
                              if x is not None} for v in vl]}
            if order:
                op["x-al-order"] = order
            if failures_out:
                op["x-al-failures"] = failures_out
            if also_out:
                op["x-al-also"] = also_out
            if no_reply:
                op["x-al-no-reply"] = no_reply
            self.operations[f"send.{key(ev)}"] = op

    # -- the document ------------------------------------------------------------------------------

    def document(self):
        vers = json.loads((ROOT / "versions.json").read_text())
        self.names |= set(self.s.types)
        self.recv_names = {ev: self.name(f"{pascal(ev)}Event") for ev in self.s.recv}
        self.types()
        self.recv()
        self.send()
        src = vers["source_repo"]
        commit = vers["source_commit"]
        desc = f"""\
**Unofficial.** The Socket.IO protocol of the MMO [Adventure Land](https://adventure.land),
generated from the machine-readable schema of the Adventure Land API reference (`schema/`), which
is written from the live game's open-source server, [{src.split('github.com/')[-1]}]({src}) at
commit `{commit}` (server version {vers['source_version']}, G version {vers['g_version']}).
Adventure Land and its code belong to its author; the game's code is under the
"AdventureLandOnlyUse" license, which asks for attribution and a link to https://adventure.land.

**Connecting.** Get a server's `address` and `path` from the HTTP API (`servers_and_characters`
or `get_servers`), then open a Socket.IO v4 WebSocket to
`wss://{{address}}{{path}}/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1`. Each
message here is one Socket.IO event, `42["<name>", <payload>]` on the wire: the message `name`
is the event name, the payload is the JSON value. A message with no payload is
`socket.emit("<name>")`.

**HTTP API.** Login, the server list and character management are HTTP, not Socket.IO, so they
are not in this document: `POST https://adventure.land/api/<method>` with a JSON body (the
reference's "HTTP API" guide).

**Replies.** Most requests are answered on `game_response` with `place` (the request) and
`response` (the code); `fail.<event>` messages list every failure form, and `x-al-failures`
on each send operation gives the check, in handler order, behind each code. Several handlers
copy `request_id` from the request into the reply (correlationId).

**Extensions** (`x-al-*`, where AsyncAPI has no slot): `x-al-order` (send order of the success
path), `x-al-also` (events the server also sends, to you or to others), `x-al-failures` (check
-> reply rows), `x-al-no-reply` (cases where the server sends nothing or closes the socket),
`x-al-variants` (request variants), `x-al-confirm` (where the shape is confirmed: code lines of
the live server, or live captures), `x-al-coerce` (how the server converts a field),
`x-al-extends` (the base type of a flattened object), `x-al-source` (`path:line` in the server
code at the pinned commit)."""
        return {
            "asyncapi": ASYNCAPI,
            "id": "urn:adventureland:socket-api",
            "info": {
                "title": "Adventure Land socket API (unofficial)",
                "version": f"{vers['source_version']}+{commit[:12]}",
                "description": desc,
                "license": {"name": "Unofficial reference. Game code: AdventureLandOnlyUse "
                                    "(attribution and a link to https://adventure.land required)",
                            "url": f"{src}/blob/{commit}/LICENSE"},
                "externalDocs": {"description": "Adventure Land, the game", "url": "https://adventure.land"},
                "tags": [{"name": "unofficial"}, {"name": "socket.io"}],
                "x-al-versions": {k: x for k, x in vers.items() if not k.startswith("_")},
            },
            "defaultContentType": "application/json",
            "servers": {
                "game": {
                    "host": "{address}",
                    "protocol": "wss",
                    "pathname": "{path}",
                    "title": "A game server (Socket.IO v4, JSON frames)",
                    "description": "Each game server (EU I, US II, ...) has its own `address` and `path`; "
                                   "they come from the server list of the HTTP API and change. Add a "
                                   "`/` after `path`, then the query of the channel binding. A second "
                                   "endpoint at `msgpack_path` speaks the game's own MessagePack framing; "
                                   "it carries the same events and is not described here.",
                    "variables": {
                        "address": {"description": "`address` of the server list entry (host, maybe with a port).",
                                    "default": "de.adventure.land", "examples": ["de.adventure.land"]},
                        "path": {"description": "`path` of the server list entry (the Socket.IO path).",
                                 "default": "/ws1", "examples": ["/ws1"]},
                    },
                },
            },
            "channels": {
                CHANNEL: {
                    "address": "/",
                    "title": "The game socket",
                    "description": "The default Socket.IO namespace of a game server. Every event "
                                   "goes both ways on this one connection; the message `name` is the "
                                   "Socket.IO event name.",
                    "servers": [{"$ref": "#/servers/game"}],
                    "messages": {k: {"$ref": f"#/components/messages/{k}"} for k in self.messages},
                    "bindings": {"ws": {
                        "bindingVersion": "0.1.0",
                        "method": "GET",
                        "query": {
                            "type": "object",
                            "properties": {
                                "EIO": {"type": "string", "const": "4", "description": "Engine.IO protocol 4."},
                                "transport": {"type": "string", "const": "websocket"},
                                "map_protocol": {"type": "string", "const": "1",
                                                 "description": "The client understands generated maps; "
                                                                "without it the server cannot send one."},
                                "no_graphics": {"type": "string", "const": "1",
                                                "description": "Generated maps arrive without tile data."},
                                "secret": {"type": "string", "description": "Observe that online character."},
                                "desktop": {"type": "string", "const": "1"},
                                "broadcast": {"type": "string", "const": "1",
                                              "description": "A public camera that follows active groups."},
                            },
                            "required": ["EIO", "transport"],
                        },
                    }},
                },
            },
            "operations": self.operations,
            "components": {"schemas": self.schemas, "messages": self.messages},
        }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-o", default=str(ROOT / "site" / "asyncapi.json"), help="output file ('-': stdout)")
    args = ap.parse_args()
    doc = Gen(apischema.Schema()).document()
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if args.o == "-":
        sys.stdout.write(text)
        return
    Path(args.o).parent.mkdir(parents=True, exist_ok=True)
    Path(args.o).write_text(text)
    c = doc["components"]
    print(f"{args.o}: {len(text) // 1024} KiB, {len(c['schemas'])} schemas, {len(c['messages'])} messages, "
          f"{len(doc['operations'])} operations", file=sys.stderr)


if __name__ == "__main__":
    main()
