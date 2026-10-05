# Writing and regenerating entries

How the content in `content/` was produced, so new entries match the existing ones and any file
can be redone the same way. Source paths below are relative to `vendor/adventureland/`
(`bash scripts/fetch-source.sh` if it's missing).

## The reference is neutral

The API reference (reference.html) is for **lookup while coding**. It states what the server does,
nothing else (owner, 2026-10-04: "neutral, just useful for lookups so I know how to code
things"). Teaching, advice, recommendations, strategy, "you should", history ("changed from the
old server") and opinions go in Build a bot or the game guide, never here. Facts that matter when you
code stay: limits, costs, cooldowns, exact replies, and server bugs (stated as facts:
"**Server bug:** ..."). No Caution/Warning blockquotes in the reference: state the fact as a
plain "**Note:**" or "**Server bug:**" paragraph. Warnings and advice belong in Build a bot. Prose follows docs/STYLE.md.

Every entry of one kind has the same sections, in the same order, with the same labels. Omit a
section only when it has nothing. Shapes on the wire come from the schema (`schema/`, see "The
schema"); never leave a reply shape implicit.

## How an event entry is built: schema plus Markdown

Each socket event has two parts:

| Part | File | Holds |
|---|---|---|
| The schema | `schema/send/<event>.json`, `schema/recv/<event>.json`, `schema/types.json` | Everything on the wire: every field of the request, every reply (success and each failure, in check order), every event that the server sends as a result, each with a type, a "present" flag and a literal JSON example. |
| The entry | the `### \`event\`` section in `content/send-*.md` or `content/receive.md` | The summary sentence, the `<!-- schema -->` line, then **Limits**, **Notes**, **Example**, **Source**. |

`build.py` replaces the `<!-- schema -->` line with sections that `apischema.py` renders from the
schema. The schema is the source of truth for shapes: the typed definitions
(`scripts/gen-types.py`) come from the same files. Write a shape in one place only, the schema;
the Markdown never repeats a field table.

The build fails when a schema file has no entry, an entry has the marker but no schema, a type
name is unknown, an example has a field that the schema does not declare (or lacks a required
one), or a link points nowhere. `ALAPI_STRICT_TYPES=1 python3 build.py` (the final check) also
fails on the two rules of "Every shape has an example" and "Every field says optional or not"
below, and on an entry whose sections are not the set of its kind, in order (see "One layout for
every entry"); it prints the list of offenders. An entry without a schema still builds in the old format (Fails /
Success tables); convert it when you touch it.

## Entry format: an event you send

In `content/send-*.md`:

```markdown
### `event_name`
One sentence: what it does, in game terms.

<!-- schema -->

**Limits:** call cost, cooldown, range, quantity caps (only if any).

**Notes:** quirks and server bugs, as facts (only if any).

**Example:** (seven-language tab group, docs/EXAMPLES.md "Reference examples")

**Source:** `node/server.js:LINE-LINE`
```

The page shows these sections, in this order. The build makes the first three from the schema;
on such an entry it also turns the bold labels into headings of the same size.

1. **Send** line: `socket.emit("event", <request example>)`. The page's Copy button uses it.
2. **Request**: the field table (Field, Type, Required, Description; with the default and how
   the server converts the value), "Other fields: ...", and the literal JSON example.
3. **Responses**: "On success, the server sends, in this order:" (a numbered list), then one
   block for each reply to you: a title (`Name: event code`, and "as a hitchhiker in `player`"
   when it rides in `player`), when it is sent, the field table (Present: always or optional),
   the literal JSON example, and its source. Then the **Failure** block: one sentence that gives
   the shared shape (`GameResponseFailure` with `place`, only when a failure has that shape),
   and the table # / Condition / Reply in
   the order the handler checks. A Reply cell is a code link plus the extra fields as JSON, or
   another form ("as a bare string", "as `{...}`" with no `place`, another event, "Nothing"),
   or several replies joined by "then". One full JSON example of a failure follows.
4. **Also sent**: events to other clients, or to you later or as a side effect: Event / To /
   When / Payload (a literal JSON example, or one sentence), then the field table of each event
   that has fields there.
5. For an event with variants: one block per variant (its own fields, replies, failures and
   also-sent events), after **Also sent**.
6. **Limits**, **Notes**, **Example**, **Source** (hand-written).

The first sentence becomes the summary in the index. Rows of the failure table are in the order
the handler checks them.

### One layout for every entry

Every entry of one kind has the same sections in the same order, also when a section is empty
(owner, 2026-10-04: "Even on an empty payload I want the layout on all pages to be the same").
An empty section shows a "None" row or the line "None.", never nothing.

| Kind | Sections (`####`), in order |
|---|---|
| Event you send | Request, Responses, Also sent, (one Variant block per variant), Limits, Notes, Example, Source |
| Event you receive | Payload, Sent to, Sent by, Notes, Example, Source |
| Response code | Exact replies |

Inside them, the parts are always there too:

- **Request**: the field table (one row "No fields. The server ignores the payload." when there
  are none; one row "(the payload)" for a payload that is not an object), then the JSON block.
  An event with no fields gets `socket.emit("town")` on the Send line and `{}` in the JSON block
  (the server ignores the payload, so an object works too). A handler with a `trigger` gets
  "No JSON: the client does not send this event."
- **Responses**: the "On success" line (the order list, or "the server sends nothing"), each
  reply, then **Failure** with its table ("None" row when nothing fails).
- **Also sent**: the table ("None" row when nothing).
- **Variant** blocks: what it does, **Request** (its own fields, "None" row), Example,
  **Responses** with **Failure**, **Also sent**, Source.
- **Payload** (receive): the field table (one "(the payload)" row for a union, a string or an
  array), then the JSON block (the first form's example when there is no example of the whole).
- **Sent by** lists "In reply to: none of the events you send" when nothing names the event.
- **Exact replies** (code) has a "None" row when no schema sends the code.

The renderer (`apischema.py`) makes the schema sections; `apischema.finish_entry` (called by
`build.py`) adds a missing hand-written section (Limits, Notes, Example, Source) as "None." and
checks the order. Entries in the old format (no `<!-- schema -->`, such as `heal`) are not
checked; convert them.

## Entry format: an event you receive

In `content/receive.md`, under its `##` section (Session and connection, World state, Combat,
Responses and messages, Social, Items and economy, Events and misc):

```markdown
### `event_name`
One sentence: when the server sends it.

<!-- schema -->

**Notes:** (only if any)

**Example:** (seven-language tab group: a handler that reads the payload)

**Source:** one or two `file:line` locations.
```

From the schema the page shows **Payload** (a Type line for a union; a Form / Type / When /
Example table for variants; for `extends`, the full field table of the base type, then "Only in
this event"; the literal JSON example), **Sent to**, and **Sent by**: the call sites from the
schema plus "In reply to:", a list of every send event whose schema names this event. The
build makes that list, so do not write it by hand.

## Guide entries in the reference (`content/connect.md`)

Protocol facts in tables and numbered sequences (a handshake is a sequence of messages, not
advice). No "you should", no recommendations, no tutorials: those are in Build a bot.

## Response codes

The codes live in **one table** in `content/codes.md`, with columns
`Code | Meaning | Example source`. The build turns each row into its own entry, so a new code is
a new row. The build also adds **Exact replies** to each code entry: a table of each request
whose schema sends the code, with the condition and the exact JSON object (from the failure rows
and the responses). Thus the code entry needs no hand-written shapes.

## The schema

JSON, hand-edited, read with the Python standard library only (no YAML on the host). Two-space
indent; one field per line. A key that starts with `_` is a comment.

### Type expressions

Every `"type"` (and `"extends"`) is a short expression. The page renders it, with links to named
types; the generators map it to each language.

| Notation | Meaning |
|---|---|
| `string` `integer` `number` `boolean` `null` `any` `object` | JSON values. `integer` is a number with no fraction. |
| `"buy"` `true` `0` | Exactly this value (a literal). Use literals for fixed `response`, `place`, `type` and `reason` values. |
| `ItemName` | A named type from `schema/types.json` (PascalCase). |
| `T[]`, `(A \| B)[]` | An array. |
| `[A, B]` | A tuple. |
| `Record<string, T>` | An object with string keys. |
| `A \| B` | A union, for example `string \| GameResponseFailure` or `boolean \| "code"`. |

### Fields

```json
{"name": "quantity", "type": "integer", "optional": true, "default": 1,
 "coerce": "`min(max(parseInt(quantity) || 0, 1), G.items[name].s || 9999)`",
 "description": "How many to buy.", "example": 100}
```

| Key | Need | Meaning |
|---|---|---|
| `name` | yes | The JSON key, exactly as the server reads or writes it. |
| `type` | yes | A type expression. Use a named type whenever one fits (`EntityId`, `InventoryIndex`, `ItemName`, `MapName`, `CharacterName`, `Milliseconds`, ...). Add a named type when a value has the same meaning in two or more events. |
| `description` | yes | STE prose (docs/STYLE.md). Constraints and meaning; cite `file:line` for anything unusual. |
| `optional` | yes | `true`: you can leave it out (request), or the server leaves it out in some cases (reply). `false`: required (request), always present (reply). Always give it, see below. |
| `default` | no | The value the server uses when the field is absent. |
| `coerce` | no | How the handler converts the value (`parseInt`, `to_number`, `!=` against a number, "none: used as an array key"). This answers "can I send a string?". |
| `example` | no | The value for generated examples (failure rows). A literal type is its own example. |

#### Every field says optional or not

Every field (request, reply, failure `extra`, `also`, receive payload, named type) has
`"optional": true` or `"optional": false`. Nothing relies on a default: "required" is a fact
you read in the handler. A request field is optional when the handler reads it with a fallback
(`parseInt(data.num) || 0`, `if (data.x)` around an optional part, `to_number`) so that a
request without it can still succeed; give the fallback in `default`. It is required when the
request fails, throws or does nothing without it. A reply field is optional when some path of
the handler leaves it out. `ALAPI_STRICT_TYPES=1` fails on a field without the key.

#### Every shape has an example

Every reply has a literal JSON `example`: each response, and each `with_request_id` /
`without_request_id` form of one that has a payload; also a response that has only a `summary`
(a `player` update, `new_map`, `start`, `merrit_status`, `observer_broadcast`). For those,
write `"example_trimmed": true` and show only the fields that matter for the reply (for a
`player` update: `id` and the changed fields, `{"id": "Merlin", "target": "48213"}`). The build
checks such an example against the payload of the receive schema of its event (declared fields
only, values of the right type; the required fields can be missing because it is trimmed), and
the page says "Example, trimmed: only the changed fields." Every receive payload has an
`example`, or every one of its `variants` has one. A request with fields has an `example`
(already fatal). Exempt: `kind: "none"` / `"close"` responses, and failure replies with `see`
(they point at a response that has its example). `ALAPI_STRICT_TYPES=1` fails on a gap and
lists every one.

### `schema/types.json`

`{"types": {"Name": {...}}}`. A type has `summary` (one sentence; the index row), and either
`type` (an expression: an alias such as `EntityId = string | integer`) or `fields` (an object;
with `extends` to add fields to another object type, and `"open": true` when the server adds
fields that the schema does not list). Optional: `description`, `example`,
`"example_trimmed": true` (the example leaves out required fields; for objects with dozens of
fields), `source`. An event file can define more types under its own `"types"` key; they share
one name space. Each type becomes a guide entry `type-<name in lower case>` in the group Types,
with **Used by** links that the build makes. The guide entry `guide-types` explains the notation
and lists every type.

### `schema/send/<event>.json`

```json
{
  "event": "buy",
  "source": "node/server.js:8409-8461",
  "request": {"fields": [...], "others": "ignored", "example": {"name": "hpot0", "quantity": 100}},
  "responses": [
    {"name": "Success", "event": "game_response", "code": "buy_success",
     "when": "All checks pass. ...", "extends": "GameResponseSuccess",
     "fields": [...], "example": {...}, "source": "node/server.js:8460"}
  ],
  "failures": {"event": "game_response", "place": "buy", "intro": "(optional)", "rows": [
    {"when": "No character, or the character is in the bank.", "code": "cant_in_bank", "source": "..."},
    {"when": "...", "code": "too_far", "extra": [{"name": "dist", "type": "number", "description": "...", "example": 241.7}]},
    {"when": "...", "code": "upgrade_no_item", "form": "bare"},
    {"when": "...", "replies": [
      {"code": "attack_failed", "form": "plain", "extra": [...]},
      {"code": "data", "extra": [{"name": "reason", "type": "\"merchant\"", "description": "Why."}]}]},
    {"when": "The target is not there.", "replies": [
      {"event": "disappear", "example": {"id": "48213", "place": "attack", "reason": "not_there"}}]},
    {"when": "No character.", "replies": []}
  ]},
  "also": [
    {"event": "ui", "to": "nearby", "when": "Success. ...", "fields": [...], "example": {...}},
    {"event": "player", "to": "you", "when": "Success, before the `game_response`.", "summary": "..."}
  ],
  "order": ["`ui` to clients nearby", "`player` to you", "`game_response` `buy_success` to you"]
}
```

The build checks every key: an unknown key is a warning (fatal under `ALAPI_STRICT_TYPES=1`),
because the page and the types would leave it out without a word.

- `trigger` (only for a handler that the client does not emit, such as `disconnect` and
  `error`): one sentence that says how the handler runs. The page shows **Trigger** in place of
  the **Send** line, and the types leave the event out of `ClientEvents`.
- `request`: the payload.
  - An object: `fields` (empty or absent: no payload; then `note` can say what the server does
    with data, and the page shows `socket.emit("event")` and `{}`), `others` (what happens to
    other keys), `example` (required when there are fields), `note`.
  - Any other value: `type` (a type expression: `"number"` for `cruise`, `"EquipBatchEntry[]"`
    for `equip_batch`, `"any"` for `ping_trig`), `example`, `note`. The page says that the
    payload is not an object.
- `responses`: each reply to the sender, success first, then other non-failure replies
  (`calculate` results, progress events, hitchhikers). Keys: `name` (unique in the event,
  variants too; not `Failure`), `event`, `code` (for `game_response`), `when`, `via` (for example
  "a hitchhiker in `player`"), then the shape: `fields` and/or `extends`, or `type`, or only
  `summary` for a big payload that has its own receive entry (`player`). Always give `example`
  (with `"example_trimmed": true` for a `summary` reply; see "Every shape has an example"). Also:
  - `codes`: a list, when the code changes with the case (`donate_thx`, `donate_gum`,
    `donate_low`): each code gets the reply in its **Exact replies**. `code_type`: a type
    expression for a code that is built at run time (`"string"` for `<quest>_success`), with
    `code` as the example.
  - `kind`: `"none"` (the server sends nothing at all: `play`, `deepsea`, `blend`,
    `requested_ack`, `error`) or `"close"` (the server closes the socket). Such a response has
    only `name`, `kind`, `when`, `source`.
  - `with_request_id` + `without_request_id`: the reply has two forms (see below).
- `failures`: `event` (default `game_response`), `place` (default: the event name),
  `place_from` (a request field whose value is the `place`: `"name"` for `skill`), `intro`,
  `rows`. One row per check, in handler order. A row is one reply (its keys in the row) or
  `replies` (zero or more, in send order). A reply:
  - `code` (or `codes`, `code_type` as above) and `form`: `failure` (default:
    `{response, place, failed: true}` plus `extra`), `bare` (the string only), `plain`
    (`{response}` plus `extra`, no `place` or `failed`; add `failed` as an extra field when the
    server sends it), `object` (only the `extra` fields, no `response`: `{place, failed,
    reason}` of `enter` `dreams`).
  - `place`: this reply's `place`, when it is not the one of the table.
  - `event` + literal `example`: a reply on another event (`game_log`, `disappear`).
  - `close: true`: the server closes the socket. `see: "<response name>"`: the reply is one of
    the responses (a check that ends in a success, such as `charm_failed` then the default
    success).
  - `note`: a short remark in the Reply cell.
  - `with_request_id` + `without_request_id`: two forms (see below).
  - The row `{"branch": true, "when": "..."}` (only in the shared table of an event with
    variants) marks the place where the checks of the variant run.
  The page gives the sentence "a failure is a `GameResponseFailure` with `place`" only when the
  failures arrive as `game_response` and at least one reply has the `failure` form.
- `also`: `event`, `to` (`you`, `nearby`, `party`, `everyone`, or a sentence), `when`, and
  `fields` + `example`, or `type` + `example`, or `summary`. `name`: a label when the event is in
  the list more than once. `code` / `codes`: for a `game_response` to another character (the
  receiver of `send`); it is then in the code's **Exact replies** too. `no_entry: true`: the event
  has no receive entry (the page shows plain code, no link).
- `order`: the order of the success path, as short phrases with code spans. When there are
  several success paths, an object: `{"Normal": [...], "From the bank": [...]}`.

#### Replies that depend on `request_id`

Many handlers answer with an object when the request has a `request_id`, and with a bare
string, another event or nothing when it does not. Write one response (or one failure reply)
with both forms, not two rows:

```json
{"when": "You are more than 500 px from the NPC.", "code": "distance",
 "with_request_id": {"form": "failure", "extra": [{"name": "request_id", "type": "any", "description": "..."}]},
 "without_request_id": {"form": "bare"}}
```

Each form is a reply (or a response shape) of its own; it takes `event`, `code`, `codes`,
`code_type`, `place` and `via` from around it when it does not give them. `{"none": true}` is
"the server sends nothing". The page shows both forms in one cell or block; the types make a
union of the two.

#### Variants: one event, several requests

An event whose handler branches on a request field (`skill` on `name`, `party` on `event`,
`bank` on `operation`, `interaction` on `type`, `poker` on `event`) has `variants`. The top level
holds the shared part (the shared request fields, the key field among them, the shared
responses, the checks that run before the branch, the shared `also`); each variant holds its own
part:

```json
"variants": {
  "key": "event",
  "intro": "(optional)",
  "list": [
    {"value": "join", "when": "Sits down, or adds gold to your stack between hands.",
     "request": {"fields": [{"name": "gold", "type": "integer", "description": "..."}],
                 "example": {"event": "join", "gold": 20000000}},
     "responses": [...], "failures": {"rows": [...]}, "also": [...], "order": [...]},
    {"value": ["sit_out", "sit_in"], "name": "Sit out or in", "when": "..."},
    {"other": true, "name": "Other", "when": "Any other value: ..."},
    {"name": "Konami", "match": "`key` and no `type`", "when": "...", "request": {"fields": [...]}},
    {"name": "Lever (bare)", "request": {"type": "\"the_lever\"", "example": "the_lever"},
     "same_as": "the_lever", "when": "The payload is the bare string."}
  ]
}
```

- `value`: the value of the key field (or a list of values) that selects the variant. `other:
  true`: every other value (the key field is then typed as its primitive, `string`). `match`: a sentence for a variant that another field selects (the
  key field is then not in its request). A variant with `request.type` is a payload that is not
  an object.
- `name`: the variant's name (default: its first value). It names the generated types.
- `request`: the variant's own fields (they come after the shared fields; an own field replaces
  a shared field of the same name, for example to make it required) and its `example` (the
  whole payload, required when there are own fields).
- `same_as`: the variant has the replies of another variant.
- `place`: the `place` of the variant's failures, when it is not the shared one.
- `responses`, `failures` (`rows`, `intro`, `place`), `also`, `order`, `source`: as at the top
  level, for this variant only.

The top-level `request.example` (the **Send** line) is one whole payload that fits one of the
variants. The page shows the shared part, a table of the variants under **Request**, then one
block per variant. The types are a discriminated union: `<Event>Request = <Event>Request<Variant> | ...`,
each with the key field narrowed to its values.

### `schema/recv/<event>.json`

```json
{
  "event": "player",
  "to": "you: only the socket of the character",
  "payload": {"extends": "Character", "fields": [...]},
  "example": {...},
  "example_trimmed": true,
  "variants": [{"name": "Bare string", "type": "string", "when": "...", "example": "upgrade_no_item",
                "source": "node/server.js:123"}],
  "senders": [{"what": "`resend(player, events)`: the usual path.", "source": "node/server.js:4550-4596"}]
}
```

`payload` is an object spec (`fields`, `extends`, `open`) or `{"type": "<union>"}` with
`variants` that explain each form (bare string vs object, objects keyed by `type`). A variant
has `name`, `type`, `when`, `example` (checked against `type`), `source`, and optionally `has`
(the fields that tell an untagged form apart: `["outside"]`) and `reply_to` (the send events
whose reply is this form). With `extends`, a field of the same name replaces the base field;
the page leaves the base row out and lists the new one under "Only in this event". `senders`
lists call sites; the build adds "In reply to" from the send schemas. A `source` with several
lines of one file (`node/server.js:10, 20-30`) links each line.

### Confirmation

Owner (2026-10-04): "I want every single one of these payloads confirmed." Each **shape** (one
documented payload) is confirmed in the live code, and where the code cannot settle it, by a
live capture. Shape ids (`apischema.shape_id`, the only place that builds them):
`send/<event>/request`, `send/<event>/response/<name>` (`#with` / `#without` for the
`request_id` forms), `send/<event>/failure/<n>` (the # of the failure table), `send/<event>/also/<i>`
(each with `/variant/<v>/` after the event for a variant: its first value, else its name),
`recv/<event>/payload`, `recv/<event>/variant/<name>`, `type/<Name>`.

On the object of each shape (a request, a response or one of its forms, a failure row, an `also`
entry, a receive `payload` or variant, a named type), a hand-written `confirm`:

```json
"confirm": {"code": ["node/server.js:8446-8448", "node/server_functions.js:3393-3419"]}
"confirm": {"code": ["node/server.js:4550-4594"], "live_needed": "The keys come from G at run time."}
```

- `code`: the exact lines where the server builds the payload or makes the check, one
  `path:line` or `path:line-line` per string (full path; `common:` for common_engine). Cite the
  helper too when it adds fields (`fail_response`, `success_response`, `resend`, `xy_emit`).
  Read the lines: the build checks the form and that each range is inside its file, not the
  content.
- `live_needed`: a sentence, when the code cannot settle the shape (private config, live data or
  G content, a payload built dynamically, timing). `code` then lists what the code does show.
- `note` (optional): a short remark; the page shows it after the citations.
- A request_id form without its own `confirm` takes the one of its response.

`schema/live.json` is written by `scripts/check-captures.py` from git-ignored captures, never by
hand. The build merges it by shape id. Each shape on the page shows one status line (a
**Confirmed** column in the failure, also-sent and form tables): "Confirmed in code: ...",
"Confirmed live: 12 captures, 2026-10-04.", "Live captures disagree: ...", or "Not yet confirmed:
<live_needed>". `python3 scripts/confirm-report.py` prints the coverage and every unconfirmed
shape (`--summary`, `--file schema/send/buy.json`, `--json`). `ALAPI_STRICT_CONFIRM=1 python3
build.py` fails on a shape without `confirm`, a citation outside its file, or a live mismatch.
It is apart from `ALAPI_STRICT_TYPES` until every shape has its key. The models are `buy`,
`attack`, `upgrade` (send) and `player`, `game_response` (receive).

The capture tool uses `apischema.Schema().shapes()` / `.shape(id)` and
`apischema.check_payload(schema, id, payload, event)` (or `shape.check(payload, event)`): a
strict check of a real payload (every required field, no undeclared field unless `open`, the type
of every value at any depth), which returns a list of mismatches.

### How to write one (the conversion procedure)

1. Read the handler from `socket.on("event"` to the next `socket.on`, and every helper it calls
   that sends something (`fail_response`, `success_response`, `resend`, `xy_emit`, ...).
2. Request: list each `data.x` that the handler reads, with how it converts it (`coerce`) and
   what happens when it is absent (`optional`, `default`). Use named types.
3. Failures: one row per `return` that sends something (or nothing), in source order, with the
   exact form: `fail_response` → `failure`; `socket.emit("game_response", "x")` → `bare`;
   `socket.emit("game_response", {response})` → `plain` or `failure` by its keys. Copy every
   extra key into `extra`. A check whose reply depends on `request_id` is one row with
   `with_request_id` and `without_request_id`. A handler that branches on a request field gets
   `variants`, not conditions that start with the value.
4. Success: follow the success path to the end. Each `emit` to the sender is a response; each
   emit to others (or later, through timers, `q`, hitchhikers) is in `also`. Write `order`.
5. Give a literal example for every reply and payload (trimmed for a `summary` reply), and
   `"optional": true` or `false` on every field; take values from G
   (`vendor/G/G_<version>.json`) so they are real.
6. Put the hand parts in the Markdown entry. Run `python3 build.py`, then
   `python3 scripts/check-examples.py --entry send-<event>` and `python3 scripts/ste-check.py` on
   the file. `python3 scripts/gen-types.py | tail` shows the generated types;
   `python3 scripts/check-types.py` compiles them in all seven languages.
7. Give every shape its `confirm` (see "Confirmation") from the lines you read in step 1;
   `python3 scripts/confirm-report.py --file schema/send/<event>.json` lists what is left.

### Typed definitions from the schema

`python3 scripts/gen-types.py` writes the types in seven languages (`--lang ts|python|go|csharp|
rust|java`, `-o FILE`, or `--all DIR`). All of them render one walk of the schema,
`apischema.model()`, so they name the same things:

| Declaration | From |
|---|---|
| one type per named type | `schema/types.json` and the `types` of the event files |
| `<Event>Request` | the request; for an event with variants, a union of `<Event>Request<Variant>`, each with the key field narrowed to its values |
| `<Event><Name>` | each response (`<Event><Name>WithRequestId` / `WithoutRequestId` and their union for a response with two forms; an alias to `<Recv>Event` for a response that only has a `summary`) |
| `<Event>Failure` | a union of every failure reply on `game_response` (one object type per distinct reply, `<Event>Failure<Code>`; bare codes as string literals) |
| `<Event>Event` | each event you receive |
| `ClientEvents`, `ClientReplies`, `ServerEvents` (TypeScript) | event name → request; → the `game_response` replies and failures; → payload. Python has `CLIENT_EVENTS` / `SERVER_EVENTS` dicts of type names. Handlers with a `trigger` are not in `ClientEvents`. |

A generated name that a named type has already gets `Reply` (a failure: `2`, `3`, ...) at the end.

`python3 scripts/check-types.py` runs the strict schema check, then compiles every language in
Docker (tsc --strict, mypy --strict, go vet + go build, dotnet build, cargo build, mvn compile).
How the schema maps:

| Schema | TypeScript | Python | Go | C# | Rust | Java |
|---|---|---|---|---|---|---|
| object type | `interface` | `TypedDict` (functional syntax; `NotRequired[...]` for optional) | `struct`, `json:"x,omitempty"`; pointer for an optional scalar and for every named struct | `sealed record`, `[JsonPropertyName]`, `required` / nullable | `struct`, `#[serde(rename)]`, `Option<T>` + `skip_serializing_if`; `Box` for a named struct | nested `record` with `@JsonProperty`, `@JsonInclude(NON_NULL)` |
| `extends` | `extends` (`Omit<Base, ...>` when a field replaces a base field) | base fields copied in | base fields copied in | base fields copied in | base fields copied in | base fields copied in |
| `"open": true` | `[key: string]: unknown` | a comment | `Extra map[string]json.RawMessage` (`json:"-"`) | `[JsonExtensionData]` | `#[serde(flatten)] extra: Map` | `@JsonIgnoreProperties(ignoreUnknown = true)` |
| literal, union of literals | the literal(s) | `Literal[...]` | the primitive | the primitive | an `enum` of renamed unit variants (strings) | the boxed primitive |
| `T \| null` | `T \| null` | `T \| None` | pointer | nullable | `Option<T>` | nullable (boxed) |
| union of shapes | the union | the union | `json.RawMessage` | `JsonElement` | `serde_json::Value` | `JsonNode` |
| declared union (request, failure) | the union | the union | `json.RawMessage` | `JsonElement` (comment) | `#[serde(untagged)] enum` | `sealed interface` that the records implement (else `JsonNode`) |
| alias | `type` | `TypeAlias` | `type X = ...` | inlined at each use | `pub type` | inlined at each use |
| `integer` / `number` | `number` | `int` / `float` | `int64` / `float64` | `long` / `double` | `i64` / `f64` | `Long` / `Double` |
| `any` / `object` | `unknown` / `Record<string, unknown>` | `Any` / `dict[str, Any]` | `any` / `map[string]any` | `JsonElement` / `Dictionary<string, JsonElement>` | `Value` / `Map<String, Value>` | `JsonNode` / `Map<String, JsonNode>` |
| tuple | tuple | `tuple[...]` | `[]any` | `JsonElement` | a Rust tuple | `JsonNode` |

### AsyncAPI export

`python3 scripts/gen-asyncapi.py` (`-o PATH`, default `site/asyncapi.json`) writes the socket API
as one AsyncAPI 3.0 JSON document for code generators and doc tools. It reads the schema only
through `apischema.Schema()` and its helpers, like the type generators. How it maps:

| Schema | AsyncAPI |
|---|---|
| a named type | `components.schemas.<Name>`: an object is `properties` + `required` (every field without `"optional": true`) + `additionalProperties: false` (`true` when `open`); `extends` is flattened, with `x-al-extends` naming the base |
| a type expression | literal: `const`; union of literals: `enum`; union: `oneOf` when no two members can match one value (with `discriminator` when a required literal field tells object members apart), else `anyOf`; tuple: draft-07 `items` array; `Record<string, T>`: `additionalProperties` |
| a request | `components.schemas.<Event>Request` (variants: one schema per variant, joined by `oneOf` + `discriminator: <key>` where possible); message `send.<event>`; operation `send.<event>` (`action: send`) |
| a response (each `request_id` form) | schema `<Event><Name>[With\|Without]RequestId`, message `reply.<event>[.<variant>].<name>[.with\|.without]`; a `summary` reply points at the receive schema |
| the failures | schema `<Event>Failure` (every `game_response` form, keyed by `response`), message `fail.<event>`; a failure on another event: `fail.<event>.<other>` |
| the replies to a request | `operations.send.<event>.reply.messages`; a reply with `request_id` gets a `correlationId` |
| a receive event | schema `<Event>Event` (its `variants` as `oneOf`/`anyOf` members with `title`), message `recv.<event>`, operation `receive.<event>` |

The message `name` is the Socket.IO event name (a key like `o:home` becomes `o_home`). Every
message carries the schema's JSON examples (failure rows: `apischema.reply_object` per code and
form). What AsyncAPI has no slot for is in `x-al-*` keys: `x-al-order`, `x-al-also`,
`x-al-failures` (check → reply rows, in handler order), `x-al-no-reply` (`kind: none` / `close`
responses and `{"none": true}` forms), `x-al-variants`, `x-al-confirm` (`Shape.state()`: code
lines, live captures, `live_needed`), `x-al-shape-id`, `x-al-coerce`, `x-al-source`,
`x-al-trigger` (no send operation), `x-al-example-trimmed`. Handlers with a `trigger` get a
message but no operation.

`python3 scripts/check-asyncapi.py` (Docker) validates the output with `@asyncapi/parser` (the
library of `asyncapi validate`) and fails on any error. It also checks each schema against the
draft-07 meta-schema and each example against its payload with Ajv: a mismatch is a warning (on
a trimmed example, info), because an example that does not fit its schema is a schema bug.

## Prompts used (2026-10-04)

Each area was written by one reader working through its slice of the source, with these
instructions (abridged; the rules are what matter):

**Events you send**, per slice of `socket.on("...")` handlers in `node/server.js` (one handler
runs until the next `socket.on`): document each event in the format above; read helpers in
`node/server_functions.js` and `js/common_functions.js` as needed; for the huge `skill` handler,
document the shared envelope and checks, then a table of each skill branch with its extra
fields and checks; document admin, internal or deprecated handlers in one short entry that says
so; never invent behavior, write "unclear from the source"; no intro or outro, only entries.

**Events you receive**: every event the server emits (grep `.emit("`, plus helpers like
`xy_emit`, `party_emit`, `instance_emit`), grouped by the sections above; a "Delivery helpers"
section explaining who each helper reaches; and an **exhaustive** `game_response` code table
(grep every `fail_response("...")` / `response: "..."` literal), including hitchhiker codes
that arrive inside `player` updates.

**Connecting** (`connect.md`): overview of the steps from nothing to acting in the world; every
HTTP endpoint in `api.py` / `main.py`; the socket.io handshake with exact payloads; observers;
rate limits and kicks with exact numbers; units and conventions. Cross-check against ALClient
(`Game.js`, `Character.js`, `Observer.js`) and mark mismatches **[live differs]**.

**G** (`game-data.md`): how it's fetched and versioned; every top-level key with counts; the
important tables field by field with how the server uses each field and one trimmed real
example; the formulas that read G (item value, grade, damage multiplier, xp per level, upgrade
and compound odds), with `file:line`. Explore the JSON with python3 (the current G is cached at
`vendor/G/G_<version>.json`; `scripts/check-updates.py` downloads new versions there).

**S** (`server-events.md`): how a client receives it (event names, full vs partial), its shape,
a table of every key with when it appears and disappears, and the lifecycle of the recurring
events (world bosses, crabxx, goobrawl, holidays), with `file:line`.

## Checking

After editing, run `python3 build.py`; it fails on missing or duplicate entries. To check
coverage of response codes against the source:

```sh
grep -ohE 'fail_response\("[a-z_0-9]+"|response: ?"[a-z_0-9]+"' \
  vendor/adventureland/node/server.js vendor/adventureland/node/server_functions.js \
  | grep -oE '"[a-z_0-9]+"' | tr -d '"' | sort -u \
  | while read c; do grep -q "$c" content/*.md || echo "missing: $c"; done
```

## Known server quirks (worth keeping visible in entries)

Live code, as of the pinned commit in versions.json:

- Duel invites arrive as `event: "chellenge"` (typo in the server).
- Some handlers reply with a bare string (`game_response "distance"`) instead of
  `{response: ...}`. Several (`bet`, `tavern`, `eval`, `donate`, ...) switch to objects when the
  request carries a `request_id`.
- Upgrade, compound and exchange results aren't replies: they arrive later via `q_data` and as
  "hitchhikers" inside the next `player` event, which the client replays as events.
- `game_log` / `game_chat` payloads are localization objects `{message, phrase, phrase_args}`.
- Broken or disabled handlers: `pet` (always throws: nothing sets `player.pet`), `whistle`
  (reads an undeclared `player`), `blend` (starts with `return;`), `tarot` (unfinished),
  `deepsea` and `legacify` (disabled). `emotion` no longer exists: emotes are skills.
- The roulette settle loop is disabled with `&& 0` (`node/server_functions.js:1594`); roulette
  bets (dev servers only) never settle.
- On hardcore servers, about 7% of dice rounds replace the roll with the last roll **after**
  the HMAC commitment is published (`node/server_functions.js:1588-1590`), so the revealed
  number doesn't match the committed text.
- `magiport` (the skill) reads an undeclared `ported` on its non-pve-safe path (`node/server.js:10819-10821`); `convert` and `move` (with `pet`/`key`) throw when there is no character.
- `bank` withdraw/deposit/unlock send two `game_response` events: one rewritten to `data`, then one with the real code (`bank_withdraw`, `bank_store`, `bank_new_pack`).
- Duels: `E.duels[id].active` is never true (the loop copies `instance.active`, but the flag is on `instance.info`), so `enter` never refuses a started duel.
- `cm` with no `message` (`JSON.stringify(undefined).length`, node/server.js:4917) or no `to` (`data.to.forEach`, node/server.js:5082) throws (+16 call-cost, `game_error`).
- `mail` takes its gold after all checks but never refunds it; a missing `to` throws and the
  attached item is lost.
- A socket is kicked above 200 call-cost per 4 s (50 without a character). While an instance
  is paused, most events get `cave_paused` / `cave_entering` (`node/logic/instance_pause.js`).
