# Server to client events

## Delivery helpers

The server uses a small set of helpers to send events. This table tells which sockets each helper reaches.

| Helper | Defined at | Who receives |
|---|---|---|
| `socket.emit(event, data)` / `player.socket.emit(...)` | (socket.io) | One socket: the requester, or a player that the code finds by name. |
| `game_response(code, data)` | `node/server_functions.js:3385` | The socket whose handler runs now (`current_socket`). The `socket.on` wrapper sets it at `node/server.js:4898`. The helper sets `data.response = code`. |
| `fail_response(code, place, data)` | `node/server_functions.js:3393` | The same socket. It sends `game_response` with `response`, `place` and `failed: true`. `place` defaults to `ls_method`, the name of the socket event (set at `node/server.js:4886`). A string as third argument becomes `{reason: <string>}`. An object as first argument sends `response: "data"`. |
| `success_response(code, place, data)` | `node/server_functions.js:3421` | The same socket. It sends `game_response` with `response`, `place` and `success: true`, unless the data already has `success: false`. An object as first argument sends `response: "data"`, and it overwrites any `response` key inside that object. |
| `xy_emit(entity, event, data, must)` | `node/server_functions.js:3744` | Every non-NPC player in `entity.in` whose vision box (`player.vision`, from `B.vision`) contains `entity.x`, `entity.y`. It also reaches the player whose id is `must`, and every observer in that instance whose vision box contains the point. The server encodes the payload once and sends it to a socket.io room per socket id (`collect_fanout`, `node/server_functions.js:3712`). Special case for `light`: a rogue or invisible player nearer than 300 gets `{name, affected: 1}` instead, loses invisibility and gets a resend (`node/server_functions.js:3762`). |
| `remove_entity_emit(entity, event, data, args)` | `node/server_functions.js:3834` | Used for removals (`disappear`, `death`). It reaches every player and observer that the server sent the entity to (`seen`, in any instance), plus everyone who can see the entity now. With `args.quiet`, it reaches only the sockets in `seen`. |
| `instance_emit(name, event, data)` | `node/server_functions.js:3540` | Every non-NPC player in the instance `name` (or an instance object). Observers do not receive it. When `gameplay == "hardcore"`, all events except `tavern` and `dice` go through `broadcast` instead. |
| `party_emit(party, event, data, args)` | `node/server_functions.js:3553` | Every member of `parties[party]`. With `args.instance`, only the members in that instance. |
| `broadcast(event, data)` | `node/server_functions.js:3495` | Every socket on every socket.io endpoint of this server process (`game_ios`), including observers without a character. |
| `realm_broadcast(event, data)` | `node/server_functions.js:3489` | Adds `data.sname` (the origin server) and calls `servers_eval` (`adventure_functions.js:1483`). That runs `broadcast` on every game server, this one included. |
| `disappearing_text(socket, entity, text, args)` | `node/server_functions.js:3956` | Sends `disappearing_text`. With `args.xy`: through `xy_emit` around `entity`. With `args.party`: through `party_emit`. Otherwise: only `socket`. |
| `resend(player, events)` | `node/server.js:4550` | Sends `player` to that player only. `events` is a list separated by `+`: `u` marks the player for an `entities` update, `cid` increments `cid`, `nc` skips the stat calculation, `reopen` sets `reopen: true` in the payload. |

**Localized text.** Most text payloads come from `localization.message(id, params, fields)` (`languages/index.js:256`). The result is an object: `{message, phrase, phrase_args, ...fields}`. `message` is the English text. `phrase` is the phrase key, and `phrase_args` holds its parameters. Some call sites send a plain string.

**Hitchhikers.** The server does not send some events directly. It pushes them to `player.hitchhikers` as `[event, data]` pairs. The next `player` event carries them as `data.hitchhikers` (`node/server.js:4579-4581`). The official client replays each pair as a separate socket event (`js/game.js:3220-3226`). These are all the hitchhikers:

| Pair | Payload | When | Source |
|---|---|---|---|
| `["game_response", ...]` | `{response: "condition", name, cevent: true, duration, from?}` | A condition starts on a character. `duration` is in ms. `from` is the name of the source, when known. | `node/server_functions.js:3244-3349` |
| `["game_response", ...]` | `{response: "skill_immune", skill}` | The target of a skill is immune to it. | `node/server.js:10670`, `node/server.js:10709` |
| `["game_response", ...]` | `{response: "compound_success", level, num, up?, stale?}` | A compound succeeds. `up` is the `extra` level gain, only when it is not 0. | `node/server.js:14831-14840` |
| `["game_response", ...]` | `{response: "compound_fail", level, num, stale?}` | A compound fails. | `node/server.js:14861-14864` |
| `["game_response", ...]` | `{response: "upgrade_offering_success", stale?}` | An upgrade with an offering succeeds. An `upgrade_success` follows. | `node/server.js:14903` |
| `["game_response", ...]` | `{response: "upgrade_success_stat", stat_type, num, stale?}` | A stat scroll succeeds. `stat_type` is the stat of the scroll. An `upgrade_success` follows. | `node/server.js:14907-14915` |
| `["game_response", ...]` | `{response: "upgrade_success", level, num, stale?}` | An upgrade succeeds. `level` is the old level plus 1, also when the level does not change. | `node/server.js:14922-14925` |
| `["game_response", ...]` | `{response: "upgrade_fail", level, num, stale?}` | An upgrade fails. | `node/server.js:14940-14943` |
| `["game_response", "monsterhunt_started"]` | a bare string | A monster hunt starts. | `node/server.js:5433` |
| `["eval", ...]` | `{code: "skill_timeout('<skill>',<ms>)"}` | Login: one pair for each skill of the class that is still on cooldown. | `node/server_functions.js:4427-4438` |

`num` is the inventory index of the item. `stale: true` is present only when the queue entry survived a logout (`init_player_exit`, `node/server_functions.js:4511-4513`). Otherwise `stale` is absent.

**Monster events.** A monster attack on a player sends `hit` at once through `xy_emit`, because `mode.instant_monster_attacks` is 1 (`node/server.js:292`, `node/server.js:4342-4344`). The other branch adds `["hit", data]` to a local `events` array that the server never sends (`node/server.js:4346`). Monster heals add `["ui", {type: "mheal", ...}]` to the `events` of the monster in the next `entities` update (`node/server.js:14106`). The official client replays these pairs as events (`js/game.js:678`).

## Session and connection

### `welcome`
The server sends it right after a socket connects, before any login. It names the server and gives the start position of the observer camera.

<!-- schema -->

**Notes:**
- The official client answers with [`loaded`](#send-loaded). After `loaded`, the server makes the socket an observer and sends `entities` with `type: "all"` (`node/server.js:5028-5054`).
- Server bug: the code reads `instance.info` for `socket.first_map` before it sets `first_map` (`node/server.js:4982-4985`). Thus `info` is always `{}`.
- If the start map is a generated map, `map_chunk` events come before `welcome`.

**Example:**

```js
// sock: a connected AlSocket
// The server and the start position of the camera.
sock.on("welcome", (data) => {
  console.log(data.region, data.name, data.pvp, data.gameplay, data.map, data.in, data.x, data.y, data.S, data.character);
});
```

```ts
// The server and the start position of the camera.
interface WelcomePayload {
  region: string;
  name: string;
  pvp: boolean;
  gameplay: string;
  map: string;
  in: string;
  x: number;
  y: number;
  S: Record<string, unknown>;
  character?: Record<string, unknown>;
}
sock.on<WelcomePayload>("welcome", (data) => {
  console.log(data.region, data.name, data.pvp, data.gameplay, data.map, data.in, data.x, data.y, data.S, data.character);
});
```

```python
# The server and the start position of the camera.
def on_welcome(data: dict) -> None:
    print(data["region"], data["name"], data["pvp"], data["gameplay"], data["map"], data["in"], data["x"], data["y"], data["S"], data.get("character"))

sock.on("welcome", on_welcome)
```

```go
// The server and the start position of the camera.
type WelcomePayload struct {
	Region    string         `json:"region"`
	Name      string         `json:"name"`
	PvP       bool           `json:"pvp"`
	Gameplay  string         `json:"gameplay"`
	Map       string         `json:"map"`
	In        string         `json:"in"`
	X         float64        `json:"x"`
	Y         float64        `json:"y"`
	S         map[string]any `json:"S"`
	Character map[string]any `json:"character"` // optional
}
sock.On("welcome", func(raw json.RawMessage) {
	var data WelcomePayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Region, data.Name, data.PvP, data.Gameplay, data.Map, data.In, data.X, data.Y, data.S, data.Character)
})
```

```csharp
// The server and the start position of the camera.
sock.On("welcome", data =>
{
    string? region = data.GetProperty("region").GetString();
    string? name = data.GetProperty("name").GetString();
    bool pvp = data.GetProperty("pvp").GetBoolean();
    string? gameplay = data.GetProperty("gameplay").GetString();
    string? map = data.GetProperty("map").GetString();
    string? instance = data.GetProperty("in").GetString();
    double x = data.GetProperty("x").GetDouble();
    double y = data.GetProperty("y").GetDouble();
    JsonElement s = data.GetProperty("S");
    JsonElement? character = data.TryGetProperty("character", out var characterEl) ? characterEl : null;
    Console.WriteLine($"{region} {name} {pvp} {gameplay} {map} {instance} {x} {y} {s} {character}");
});
```

```rust
// The server and the start position of the camera.
sock.on("welcome", |data| {
    let region = data["region"].as_str().unwrap_or_default();
    let name = data["name"].as_str().unwrap_or_default();
    let pvp = data["pvp"].as_bool().unwrap_or(false);
    let gameplay = data["gameplay"].as_str().unwrap_or_default();
    let map = data["map"].as_str().unwrap_or_default();
    let instance = data["in"].as_str().unwrap_or_default();
    let x = data["x"].as_f64().unwrap_or(0.0);
    let y = data["y"].as_f64().unwrap_or(0.0);
    let s = &data["S"];
    let character = data.get("character"); // optional
    println!("{region} {name} {pvp} {gameplay} {map} {instance} {x} {y} {s} {character:?}");
});
```

```java
// The server and the start position of the camera.
sock.on("welcome", data -> {
    String region = data.path("region").asText();
    String name = data.path("name").asText();
    boolean pvp = data.path("pvp").asBoolean();
    String gameplay = data.path("gameplay").asText();
    String map = data.path("map").asText();
    String instance = data.path("in").asText();
    double x = data.path("x").asDouble();
    double y = data.path("y").asDouble();
    JsonNode s = data.path("S");
    JsonNode character = data.get("character"); // optional: null when absent
    System.out.println(region + " " + name + " " + pvp + " " + gameplay + " " + map + " " + instance + " " + x + " " + y + " " + s + " " + character);
});
```

**Source:** `node/server.js:4977-5019`.

### `start`
The server sends it after a successful character login. It is the full start state of the character.

<!-- schema -->

**Notes:**
- `info` is `instance.info`. The same object is in `new_map` and `map_info`. It has one of these forms:
  - `{}`: most instances.
  - A duel instance: `{seconds, active, A, B, id}`. `seconds` is 60 (20 on a development server). `A` and `B` are the teams: `player_to_summary` objects with `active: true` (`node/server.js:12238-12246`).
  - The `tavern`: `{dice, num, seconds}`. `dice` is `"bets"`, `"roll"` or `"lock"`. `num` is the dice result as a string, for example `"47.31"`. The server removes `num` during `"roll"`. `seconds` counts the bet phase (`node/server_functions.js:1359-1361`, `1405-1419`, `1556-1557`).
  - A floor of the Cave of Many Dreams: `{zone: {run, floor, expires}}`. `expires` is a time in ms (`node/logic/generated_maps.js:101`).
- `code` has two meanings. Without code text it is the boolean `code` flag of `player_to_client`. With code text, the source text replaces the flag.

**Example:**

```js
// sock: a connected AlSocket
// The full state of the character after auth.
sock.on("start", (data) => {
  console.log(data.id, data.ctype, data.level, data.map, data.in, data.x, data.y, data.gold, data.ipass, data.home, data.entities);
});
```

```ts
// The full state of the character after auth.
interface StartPayload {
  id: string;
  ctype: string;
  level: number;
  map: string;
  in: string;
  x: number;
  y: number;
  gold: number;
  ipass: string;
  home: string;
  entities: Record<string, unknown>;
}
sock.on<StartPayload>("start", (data) => {
  console.log(data.id, data.ctype, data.level, data.map, data.in, data.x, data.y, data.gold, data.ipass, data.home, data.entities);
});
```

```python
# The full state of the character after auth.
def on_start(data: dict) -> None:
    print(data["id"], data["ctype"], data["level"], data["map"], data["in"], data["x"], data["y"], data["gold"], data["ipass"], data["home"], data["entities"])

sock.on("start", on_start)
```

```go
// The full state of the character after auth.
type StartPayload struct {
	ID       string         `json:"id"`
	Ctype    string         `json:"ctype"`
	Level    int            `json:"level"`
	Map      string         `json:"map"`
	In       string         `json:"in"`
	X        float64        `json:"x"`
	Y        float64        `json:"y"`
	Gold     float64        `json:"gold"`
	Ipass    string         `json:"ipass"`
	Home     string         `json:"home"`
	Entities map[string]any `json:"entities"`
}
sock.On("start", func(raw json.RawMessage) {
	var data StartPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.ID, data.Ctype, data.Level, data.Map, data.In, data.X, data.Y, data.Gold, data.Ipass, data.Home, data.Entities)
})
```

```csharp
// The full state of the character after auth.
sock.On("start", data =>
{
    string? id = data.GetProperty("id").GetString();
    string? ctype = data.GetProperty("ctype").GetString();
    int level = data.GetProperty("level").GetInt32();
    string? map = data.GetProperty("map").GetString();
    string? instance = data.GetProperty("in").GetString();
    double x = data.GetProperty("x").GetDouble();
    double y = data.GetProperty("y").GetDouble();
    double gold = data.GetProperty("gold").GetDouble();
    string? ipass = data.GetProperty("ipass").GetString();
    string? home = data.GetProperty("home").GetString();
    JsonElement entities = data.GetProperty("entities");
    Console.WriteLine($"{id} {ctype} {level} {map} {instance} {x} {y} {gold} {ipass} {home} {entities}");
});
```

```rust
// The full state of the character after auth.
sock.on("start", |data| {
    let id = data["id"].as_str().unwrap_or_default();
    let ctype = data["ctype"].as_str().unwrap_or_default();
    let level = data["level"].as_i64().unwrap_or(0);
    let map = data["map"].as_str().unwrap_or_default();
    let instance = data["in"].as_str().unwrap_or_default();
    let x = data["x"].as_f64().unwrap_or(0.0);
    let y = data["y"].as_f64().unwrap_or(0.0);
    let gold = data["gold"].as_f64().unwrap_or(0.0);
    let ipass = data["ipass"].as_str().unwrap_or_default();
    let home = data["home"].as_str().unwrap_or_default();
    let entities = &data["entities"];
    println!("{id} {ctype} {level} {map} {instance} {x} {y} {gold} {ipass} {home} {entities}");
});
```

```java
// The full state of the character after auth.
sock.on("start", data -> {
    String id = data.path("id").asText();
    String ctype = data.path("ctype").asText();
    int level = data.path("level").asInt();
    String map = data.path("map").asText();
    String instance = data.path("in").asText();
    double x = data.path("x").asDouble();
    double y = data.path("y").asDouble();
    double gold = data.path("gold").asDouble();
    String ipass = data.path("ipass").asText();
    String home = data.path("home").asText();
    JsonNode entities = data.path("entities");
    System.out.println(id + " " + ctype + " " + level + " " + map + " " + instance + " " + x + " " + y + " " + gold + " " + ipass + " " + home + " " + entities);
});
```

**Source:** `node/server.js:11919-11944` (`auth` handler).

### `ping_ack`
The reply to `ping_trig`.

<!-- schema -->

**Notes:**
- The server does not read the payload. It sends back any value, also a string or a number. The fields above are the ones that the official client sends.
- To measure the ping, keep the send time for each `id`. Compare it with the time when `ping_ack` arrives.

**Example:**

```js
// sock: a connected AlSocket
// `id` is the value that ping_trig sent.
sock.on("ping_ack", (data) => {
  console.log(data.id);
});
```

```ts
// `id` is the value that ping_trig sent.
interface PingAckPayload {
  id: unknown;
}
sock.on<PingAckPayload>("ping_ack", (data) => {
  console.log(data.id);
});
```

```python
# `id` is the value that ping_trig sent.
def on_ping_ack(data: dict) -> None:
    print(data["id"])

sock.on("ping_ack", on_ping_ack)
```

```go
// `id` is the value that ping_trig sent.
type PingAckPayload struct {
	ID any `json:"id"`
}
sock.On("ping_ack", func(raw json.RawMessage) {
	var data PingAckPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.ID)
})
```

```csharp
// `id` is the value that ping_trig sent.
sock.On("ping_ack", data =>
{
    JsonElement id = data.GetProperty("id");
    Console.WriteLine($"{id}");
});
```

```rust
// `id` is the value that ping_trig sent.
sock.on("ping_ack", |data| {
    let id = &data["id"];
    println!("{id}");
});
```

```java
// `id` is the value that ping_trig sent.
sock.on("ping_ack", data -> {
    JsonNode id = data.path("id");
    System.out.println(id);
});
```

**Source:** `node/server.js:5127`.

### `disconnect_reason`
The server sends it before it disconnects a socket, or broadcasts it before a shutdown.

<!-- schema -->

**Notes:**
- The payload is a plain string, not an object.
- For a shutdown, the server does not disconnect the socket at once. It stops 10 s later.

**Example:**

```js
// sock: a connected AlSocket
// A reason code or a text. The socket closes next.
sock.on("disconnect_reason", (reason) => {
  console.log(reason);
});
```

```ts
// A reason code or a text. The socket closes next.
sock.on<string>("disconnect_reason", (reason) => {
  console.log(reason);
});
```

```python
# A reason code or a text. The socket closes next.
def on_disconnect_reason(reason: str) -> None:
    print(reason)

sock.on("disconnect_reason", on_disconnect_reason)
```

```go
// A reason code or a text. The socket closes next.
sock.On("disconnect_reason", func(raw json.RawMessage) {
	var reason string
	if err := json.Unmarshal(raw, &reason); err != nil {
		return
	}
	fmt.Println(reason)
})
```

```csharp
// A reason code or a text. The socket closes next.
sock.On("disconnect_reason", data =>
{
    string? reason = data.GetString();
    Console.WriteLine(reason);
});
```

```rust
// A reason code or a text. The socket closes next.
sock.on("disconnect_reason", |data| {
    let reason = data.as_str().unwrap_or_default();
    println!("{reason}");
});
```

```java
// A reason code or a text. The socket closes next.
sock.on("disconnect_reason", data -> {
    String reason = data.asText();
    System.out.println(reason);
});
```

**Source:** `node/server.js:4939-4961` (call cost), `node/server.js:11914-11916` (`auth`), `node/server.js:13152-13160` (`shutdown`).

### `limitdcreport`
The server sends it right before a `limitdc` disconnect.

<!-- schema -->

**Notes:**
- `calls` has the same form as in `ccreport`: a list of `[time, event, cost]` entries. Find the event with the highest cost to see what to slow down.
- `disconnect_reason` `"limitdc"` comes next, then the server closes the socket.

**Example:**

```js
// sock: a connected AlSocket
// Find the event with the highest cost before the limitdc disconnect.
sock.on("limitdcreport", (data) => {
  let worst = ["", "", 0];
  for (const call of data.calls) if (call[2] > worst[2]) worst = call;
  console.log(`above ${data.climit}: ${worst[1]} cost ${worst[2]}`, data.method);
});
```

```ts
// Find the event with the highest cost before the limitdc disconnect.
interface LimitdcreportPayload {
  calls: [string, string, number][];
  climit: number;
  total: number;
  method?: string;
}
sock.on<LimitdcreportPayload>("limitdcreport", (data) => {
  let worst: [string, string, number] = ["", "", 0];
  for (const call of data.calls) if (call[2] > worst[2]) worst = call;
  console.log(`above ${data.climit}: ${worst[1]} cost ${worst[2]}`, data.method);
});
```

```python
# Find the event with the highest cost before the limitdc disconnect.
def on_limitdcreport(data: dict) -> None:
    worst = max(data["calls"], key=lambda call: call[2], default=["", "", 0])
    print(f"above {data['climit']}: {worst[1]} cost {worst[2]}", data.get("method"))

sock.on("limitdcreport", on_limitdcreport)
```

```go
// Find the event with the highest cost before the limitdc disconnect.
type LimitdcreportPayload struct {
	Calls  [][]any `json:"calls"`
	Climit int     `json:"climit"`
	Total  int     `json:"total"`
	Method string  `json:"method"` // optional
}
sock.On("limitdcreport", func(raw json.RawMessage) {
	var data LimitdcreportPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	worst, cost := "", 0.0
	for _, call := range data.Calls {
		if c, ok := call[2].(float64); ok && c > cost {
			worst, cost = fmt.Sprint(call[1]), c
		}
	}
	fmt.Println("above", data.Climit, worst, cost, data.Method)
})
```

```csharp
// Find the event with the highest cost before the limitdc disconnect.
sock.On("limitdcreport", data =>
{
    string worst = "";
    double cost = 0;
    foreach (JsonElement call in data.GetProperty("calls").EnumerateArray())
        if (call[2].GetDouble() > cost) { worst = call[1].GetString() ?? ""; cost = call[2].GetDouble(); }
    int climit = data.GetProperty("climit").GetInt32();
    string? method = data.TryGetProperty("method", out var methodEl) ? methodEl.GetString() : null;
    Console.WriteLine($"above {climit}: {worst} cost {cost} {method}");
});
```

```rust
// Find the event with the highest cost before the limitdc disconnect.
sock.on("limitdcreport", |data| {
    let (mut worst, mut cost) = ("", 0.0);
    for call in data["calls"].as_array().into_iter().flatten() {
        let c = call[2].as_f64().unwrap_or(0.0);
        if c > cost { worst = call[1].as_str().unwrap_or_default(); cost = c; }
    }
    let climit = data["climit"].as_i64().unwrap_or(0);
    let method = data["method"].as_str(); // optional
    println!("above {climit}: {worst} cost {cost} {method:?}");
});
```

```java
// Find the event with the highest cost before the limitdc disconnect.
sock.on("limitdcreport", data -> {
    String worst = "";
    double cost = 0;
    for (JsonNode call : data.path("calls")) {
        if (call.path(2).asDouble() > cost) { worst = call.path(1).asText(); cost = call.path(2).asDouble(); }
    }
    int climit = data.path("climit").asInt();
    String method = data.path("method").asText(null); // optional
    System.out.println("above " + climit + ": " + worst + " cost " + cost + " " + method);
});
```

**Source:** `node/server.js:4939-4943`, `node/server.js:4947-4961`.

### `ccreport`
The reply to the client's `ccreport` request.

<!-- schema -->

**Notes:**
- `calls` is a list of `[time, event, cost]` entries, not an object. Add the costs to get the call cost now. The server disconnects above `climit`.
- `climit` is always `limits.calls`, also on a socket without a character. The real limit of such a socket is a quarter of it (`node/server.js:4905-4906`).

**Example:**

```js
// sock: a connected AlSocket
// `calls` holds [time, event, cost] for the last 4 s.
sock.on("ccreport", (data) => {
  let cost = 0;
  for (const call of data.calls) cost += call[2];
  console.log(`cost ${cost} of ${data.climit}, ${data.total} events`);
});
```

```ts
// `calls` holds [time, event, cost] for the last 4 s.
interface CcreportPayload {
  calls: [string, string, number][];
  climit: number;
  total: number;
}
sock.on<CcreportPayload>("ccreport", (data) => {
  let cost = 0;
  for (const call of data.calls) cost += call[2];
  console.log(`cost ${cost} of ${data.climit}, ${data.total} events`);
});
```

```python
# `calls` holds [time, event, cost] for the last 4 s.
def on_ccreport(data: dict) -> None:
    cost = sum(call[2] for call in data["calls"])
    print(f"cost {cost} of {data['climit']}, {data['total']} events")

sock.on("ccreport", on_ccreport)
```

```go
// `calls` holds [time, event, cost] for the last 4 s.
type CcreportPayload struct {
	Calls  [][]any `json:"calls"`
	Climit int     `json:"climit"`
	Total  int     `json:"total"`
}
sock.On("ccreport", func(raw json.RawMessage) {
	var data CcreportPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	cost := 0.0
	for _, call := range data.Calls {
		if c, ok := call[2].(float64); ok {
			cost += c
		}
	}
	fmt.Println("cost", cost, "of", data.Climit, "events", data.Total)
})
```

```csharp
// `calls` holds [time, event, cost] for the last 4 s.
sock.On("ccreport", data =>
{
    double cost = 0;
    foreach (JsonElement call in data.GetProperty("calls").EnumerateArray())
        cost += call[2].GetDouble();
    int climit = data.GetProperty("climit").GetInt32();
    int total = data.GetProperty("total").GetInt32();
    Console.WriteLine($"cost {cost} of {climit}, {total} events");
});
```

```rust
// `calls` holds [time, event, cost] for the last 4 s.
sock.on("ccreport", |data| {
    let cost: f64 = data["calls"]
        .as_array()
        .map(|calls| calls.iter().map(|call| call[2].as_f64().unwrap_or(0.0)).sum())
        .unwrap_or(0.0);
    let climit = data["climit"].as_i64().unwrap_or(0);
    let total = data["total"].as_i64().unwrap_or(0);
    println!("cost {cost} of {climit}, {total} events");
});
```

```java
// `calls` holds [time, event, cost] for the last 4 s.
sock.on("ccreport", data -> {
    double cost = 0;
    for (JsonNode call : data.path("calls")) cost += call.path(2).asDouble();
    int climit = data.path("climit").asInt();
    int total = data.path("total").asInt();
    System.out.println("cost " + cost + " of " + climit + ", " + total + " events");
});
```

**Source:** `node/server.js:5437-5439`, `node/server_functions.js:5336-5362` (`add_call_cost`).

### `reloaded`
The server sends it after a live reload of the game data (`G`, `D`).

<!-- schema -->

**Notes:**
- The server does not send the new `G`. A client that keeps `G` must load it again over HTTP. The official client loads `/data.js` again (`js/functions.js:7354-7363`).

**Example:**

```js
// sock: a connected AlSocket
// The server reloaded its game data.
sock.on("reloaded", (data) => {
  console.log(data.change);
});
```

```ts
// The server reloaded its game data.
interface ReloadedPayload {
  change: string;
}
sock.on<ReloadedPayload>("reloaded", (data) => {
  console.log(data.change);
});
```

```python
# The server reloaded its game data.
def on_reloaded(data: dict) -> None:
    print(data["change"])

sock.on("reloaded", on_reloaded)
```

```go
// The server reloaded its game data.
type ReloadedPayload struct {
	Change string `json:"change"`
}
sock.On("reloaded", func(raw json.RawMessage) {
	var data ReloadedPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Change)
})
```

```csharp
// The server reloaded its game data.
sock.On("reloaded", data =>
{
    string? change = data.GetProperty("change").GetString();
    Console.WriteLine($"{change}");
});
```

```rust
// The server reloaded its game data.
sock.on("reloaded", |data| {
    let change = data["change"].as_str().unwrap_or_default();
    println!("{change}");
});
```

```java
// The server reloaded its game data.
sock.on("reloaded", data -> {
    String change = data.path("change").asText();
    System.out.println(change);
});
```

**Source:** `node/server.js:733`.

### `map_chunk`
A part of a generated map (the Cave of Many Dreams). The server sends the map before `welcome` or `new_map` when the destination is a generated map.

<!-- schema -->

**Notes:**
- Join the `text` of all parts in `index` order. Then parse the result as JSON: it is a `MapChunkBundle`. Add each floor to `G.maps` and `G.geometry` before you handle `welcome` or `new_map`.
- Only a socket that connected with `map_protocol=1` can go to a generated map (`node/logic/generated_maps.js:47`). For any other socket, `send_generated_maps` throws `client_update_required` (`node/logic/generated_maps.js:186`).
- After the parts, the server sends a `drop` for each cave chest on that floor (`cave_send_chests`, `node/logic/cave_of_many_dreams.js:530-541`).

**Example:**

```js
// sock: a connected AlSocket
// Join `text` of all parts in `index` order, then parse it as JSON.
sock.on("map_chunk", (data) => {
  console.log(data.run, data.index, data.count, data.text);
});
```

```ts
// Join `text` of all parts in `index` order, then parse it as JSON.
interface MapChunkPayload {
  run: string;
  index: number;
  count: number;
  text: string;
}
sock.on<MapChunkPayload>("map_chunk", (data) => {
  console.log(data.run, data.index, data.count, data.text);
});
```

```python
# Join `text` of all parts in `index` order, then parse it as JSON.
def on_map_chunk(data: dict) -> None:
    print(data["run"], data["index"], data["count"], data["text"])

sock.on("map_chunk", on_map_chunk)
```

```go
// Join `text` of all parts in `index` order, then parse it as JSON.
type MapChunkPayload struct {
	Run   string `json:"run"`
	Index int    `json:"index"`
	Count int    `json:"count"`
	Text  string `json:"text"`
}
sock.On("map_chunk", func(raw json.RawMessage) {
	var data MapChunkPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Run, data.Index, data.Count, data.Text)
})
```

```csharp
// Join `text` of all parts in `index` order, then parse it as JSON.
sock.On("map_chunk", data =>
{
    string? run = data.GetProperty("run").GetString();
    int index = data.GetProperty("index").GetInt32();
    int count = data.GetProperty("count").GetInt32();
    string? text = data.GetProperty("text").GetString();
    Console.WriteLine($"{run} {index} {count} {text}");
});
```

```rust
// Join `text` of all parts in `index` order, then parse it as JSON.
sock.on("map_chunk", |data| {
    let run = data["run"].as_str().unwrap_or_default();
    let index = data["index"].as_i64().unwrap_or(0);
    let count = data["count"].as_i64().unwrap_or(0);
    let text = data["text"].as_str().unwrap_or_default();
    println!("{run} {index} {count} {text}");
});
```

```java
// Join `text` of all parts in `index` order, then parse it as JSON.
sock.on("map_chunk", data -> {
    String run = data.path("run").asText();
    int index = data.path("index").asInt();
    int count = data.path("count").asInt();
    String text = data.path("text").asText();
    System.out.println(run + " " + index + " " + count + " " + text);
});
```

**Source:** `node/logic/generated_maps.js:178-218`.

### `observer_broadcast`
The state of the automatic camera, for the public broadcast observer. The camera follows active groups of players and moves every 250 ms.

<!-- schema -->

**Notes:**
- The server moves the observer itself. When the group changes, or the camera moves more than 200 px, the server sends `new_map` (`transport_observer_to`). Otherwise it only moves the view (`node/logic/observer_broadcast.js:188-200`).
- The camera skips characters that are invisible, in stealth, in an instance, or on a PvP map (`node/logic/observer_broadcast.js:59-67`).
- A group that has only characters in the town square is not a group choice. The town shot shows them when 6 or more are there.

**Example:**

```js
// sock: a connected AlSocket
// The position and group of the broadcast camera.
sock.on("observer_broadcast", (data) => {
  console.log(data.group, data.kind, data.map, data.x, data.y, data.online);
});
```

```ts
// The position and group of the broadcast camera.
interface ObserverBroadcastPayload {
  group: string | null;
  kind: "group" | "town" | "waiting";
  map: string;
  x: number;
  y: number;
  online: number;
}
sock.on<ObserverBroadcastPayload>("observer_broadcast", (data) => {
  console.log(data.group, data.kind, data.map, data.x, data.y, data.online);
});
```

```python
# The position and group of the broadcast camera.
def on_observer_broadcast(data: dict) -> None:
    print(data["group"], data["kind"], data["map"], data["x"], data["y"], data["online"])

sock.on("observer_broadcast", on_observer_broadcast)
```

```go
// The position and group of the broadcast camera.
type ObserverBroadcastPayload struct {
	Group  string  `json:"group"`
	Kind   string  `json:"kind"`
	Map    string  `json:"map"`
	X      float64 `json:"x"`
	Y      float64 `json:"y"`
	Online int     `json:"online"`
}
sock.On("observer_broadcast", func(raw json.RawMessage) {
	var data ObserverBroadcastPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Group, data.Kind, data.Map, data.X, data.Y, data.Online)
})
```

```csharp
// The position and group of the broadcast camera.
sock.On("observer_broadcast", data =>
{
    string? group = data.GetProperty("group").GetString();
    string? kind = data.GetProperty("kind").GetString();
    string? map = data.GetProperty("map").GetString();
    double x = data.GetProperty("x").GetDouble();
    double y = data.GetProperty("y").GetDouble();
    int online = data.GetProperty("online").GetInt32();
    Console.WriteLine($"{group} {kind} {map} {x} {y} {online}");
});
```

```rust
// The position and group of the broadcast camera.
sock.on("observer_broadcast", |data| {
    let group = data["group"].as_str().unwrap_or_default();
    let kind = data["kind"].as_str().unwrap_or_default();
    let map = data["map"].as_str().unwrap_or_default();
    let x = data["x"].as_f64().unwrap_or(0.0);
    let y = data["y"].as_f64().unwrap_or(0.0);
    let online = data["online"].as_i64().unwrap_or(0);
    println!("{group} {kind} {map} {x} {y} {online}");
});
```

```java
// The position and group of the broadcast camera.
sock.on("observer_broadcast", data -> {
    String group = data.path("group").asText();
    String kind = data.path("kind").asText();
    String map = data.path("map").asText();
    double x = data.path("x").asDouble();
    double y = data.path("y").asDouble();
    int online = data.path("online").asInt();
    System.out.println(group + " " + kind + " " + map + " " + x + " " + y + " " + online);
});
```

**Source:** `node/logic/observer_broadcast.js:49-201` (`update_broadcast_observer`), `node/logic/observer_broadcast.js:173-187` (the emit).

### `tauri_auth`
The desktop (Tauri) Steam check succeeded at login.

<!-- schema -->

**Example:**

```js
// sock: a connected AlSocket
// The desktop Steam check succeeded.
sock.on("tauri_auth", (data) => {
  console.log(data.status, data.pid, data.ticket_received);
});
```

```ts
// The desktop Steam check succeeded.
interface TauriAuthPayload {
  status: string;
  pid: string;
  ticket_received: boolean;
}
sock.on<TauriAuthPayload>("tauri_auth", (data) => {
  console.log(data.status, data.pid, data.ticket_received);
});
```

```python
# The desktop Steam check succeeded.
def on_tauri_auth(data: dict) -> None:
    print(data["status"], data["pid"], data["ticket_received"])

sock.on("tauri_auth", on_tauri_auth)
```

```go
// The desktop Steam check succeeded.
type TauriAuthPayload struct {
	Status         string `json:"status"`
	PID            string `json:"pid"`
	TicketReceived bool   `json:"ticket_received"`
}
sock.On("tauri_auth", func(raw json.RawMessage) {
	var data TauriAuthPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Status, data.PID, data.TicketReceived)
})
```

```csharp
// The desktop Steam check succeeded.
sock.On("tauri_auth", data =>
{
    string? status = data.GetProperty("status").GetString();
    string? pid = data.GetProperty("pid").GetString();
    bool ticketReceived = data.GetProperty("ticket_received").GetBoolean();
    Console.WriteLine($"{status} {pid} {ticketReceived}");
});
```

```rust
// The desktop Steam check succeeded.
sock.on("tauri_auth", |data| {
    let status = data["status"].as_str().unwrap_or_default();
    let pid = data["pid"].as_str().unwrap_or_default();
    let ticket_received = data["ticket_received"].as_bool().unwrap_or(false);
    println!("{status} {pid} {ticket_received}");
});
```

```java
// The desktop Steam check succeeded.
sock.on("tauri_auth", data -> {
    String status = data.path("status").asText();
    String pid = data.path("pid").asText();
    boolean ticketReceived = data.path("ticket_received").asBoolean();
    System.out.println(status + " " + pid + " " + ticketReceived);
});
```

**Source:** `node/server_functions.js:936`, `node/server_functions.js:966`.

### `tauri_auth_error`
The desktop (Tauri) Steam check failed at login. The login continues with platform `web`.

<!-- schema -->

**Notes:**
- This is not a login failure. The server sets the platform to `web`, and the login continues to `start`.

**Example:**

```js
// sock: a connected AlSocket
// The desktop Steam check failed. The login continues.
sock.on("tauri_auth_error", (data) => {
  console.log(data.reason, data.stage, data.ticket_received);
});
```

```ts
// The desktop Steam check failed. The login continues.
interface TauriAuthErrorPayload {
  reason: string;
  stage: string;
  ticket_received: boolean;
}
sock.on<TauriAuthErrorPayload>("tauri_auth_error", (data) => {
  console.log(data.reason, data.stage, data.ticket_received);
});
```

```python
# The desktop Steam check failed. The login continues.
def on_tauri_auth_error(data: dict) -> None:
    print(data["reason"], data["stage"], data["ticket_received"])

sock.on("tauri_auth_error", on_tauri_auth_error)
```

```go
// The desktop Steam check failed. The login continues.
type TauriAuthErrorPayload struct {
	Reason         string `json:"reason"`
	Stage          string `json:"stage"`
	TicketReceived bool   `json:"ticket_received"`
}
sock.On("tauri_auth_error", func(raw json.RawMessage) {
	var data TauriAuthErrorPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Reason, data.Stage, data.TicketReceived)
})
```

```csharp
// The desktop Steam check failed. The login continues.
sock.On("tauri_auth_error", data =>
{
    string? reason = data.GetProperty("reason").GetString();
    string? stage = data.GetProperty("stage").GetString();
    bool ticketReceived = data.GetProperty("ticket_received").GetBoolean();
    Console.WriteLine($"{reason} {stage} {ticketReceived}");
});
```

```rust
// The desktop Steam check failed. The login continues.
sock.on("tauri_auth_error", |data| {
    let reason = data["reason"].as_str().unwrap_or_default();
    let stage = data["stage"].as_str().unwrap_or_default();
    let ticket_received = data["ticket_received"].as_bool().unwrap_or(false);
    println!("{reason} {stage} {ticket_received}");
});
```

```java
// The desktop Steam check failed. The login continues.
sock.on("tauri_auth_error", data -> {
    String reason = data.path("reason").asText();
    String stage = data.path("stage").asText();
    boolean ticketReceived = data.path("ticket_received").asBoolean();
    System.out.println(reason + " " + stage + " " + ticketReceived);
});
```

**Source:** `node/server_functions.js:925-962`, `node/server.js:11844-11856`.

### `test`
The reply to the client's `test` event.

<!-- schema -->

**Example:**

```js
// sock: a connected AlSocket
// The server date.
sock.on("test", (data) => {
  console.log(data.date);
});
```

```ts
// The server date.
interface TestPayload {
  date: string;
}
sock.on<TestPayload>("test", (data) => {
  console.log(data.date);
});
```

```python
# The server date.
def on_test(data: dict) -> None:
    print(data["date"])

sock.on("test", on_test)
```

```go
// The server date.
type TestPayload struct {
	Date string `json:"date"`
}
sock.On("test", func(raw json.RawMessage) {
	var data TestPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Date)
})
```

```csharp
// The server date.
sock.On("test", data =>
{
    string? date = data.GetProperty("date").GetString();
    Console.WriteLine($"{date}");
});
```

```rust
// The server date.
sock.on("test", |data| {
    let date = data["date"].as_str().unwrap_or_default();
    println!("{date}");
});
```

```java
// The server date.
sock.on("test", data -> {
    String date = data.path("date").asText();
    System.out.println(date);
});
```

**Source:** `node/server.js:5588`.

## World state

### `entities`
Position and state updates for the players and monsters that the receiver can see.

<!-- schema -->

**Notes:**
- Each entity in an `"xy"` frame is a complete object, not a change. Replace the old object. The code says that changes broke the official client (`node/server.js:13705`).
- A monster leaves out most stats that are equal to `G.monsters[type]`. A monster at full health has no `hp`.
- When the receiver moved 65 px or arrived, the `"xy"` frame also has every entity in view (`node/server.js:13716-13737`).
- When an entity leaves the vision box, dies or becomes invisible, the server sends `disappear` with `outside: true`. Before a `type: "all"` frame, the server sends that `disappear` for each entity that the client had and that is not in the new frame.
- A `type: "all"` frame includes the receiver itself in `players`, in the stranger form. An `"xy"` frame does not.
- If the socket has too much unsent data (`B.xy_backlog_limit`), the server skips the tick. It sends a `type: "all"` frame when the socket drains.
- `new_map` and `start` carry a `type: "all"` frame in their `entities` field. The server does not send it again as an `entities` event.
- The official client ignores the frame if `in` is not its current instance.
- The `"xy"` frame is a pre-built JSON text (`RawFrame`, `node/json_parser.js`). On the wire it is a normal Socket.IO JSON event.
- Server bug: a monster can have an entry in this tick without `events` and then attack. The code then sets `events` to the attack events and appends them again. Each event is in the list twice (`node/server.js:15184-15187`). With the default `mode.instant_monster_attacks`, these events are empty, so the bug does not show.

**Example:**

```js
// sock: a connected AlSocket
// Monsters hold only the fields that differ from G.monsters[type].
sock.on("entities", (data) => {
  console.log(data.type, data.in, data.map);
  for (const p of data.players) console.log(p.id, p.x, p.y);
  for (const m of data.monsters) console.log(m.id, m.type, m.x, m.y);
});
```

```ts
// Monsters hold only the fields that differ from G.monsters[type].
interface EntitiesPayload {
  type: string;
  in: string;
  map: string;
  players: { id: string; x: number; y: number }[];
  monsters: { id: string; type: string; x: number; y: number }[];
}
sock.on<EntitiesPayload>("entities", (data) => {
  console.log(data.type, data.in, data.map);
  for (const p of data.players) console.log(p.id, p.x, p.y);
  for (const m of data.monsters) console.log(m.id, m.type, m.x, m.y);
});
```

```python
# Monsters hold only the fields that differ from G.monsters[type].
def on_entities(data: dict) -> None:
    print(data["type"], data["in"], data["map"])
    for p in data["players"]:
        print(p["id"], p["x"], p["y"])
    for m in data["monsters"]:
        print(m["id"], m["type"], m["x"], m["y"])

sock.on("entities", on_entities)
```

```go
// Monsters hold only the fields that differ from G.monsters[type].
type EntitiesPayload struct {
	Type    string `json:"type"`
	In      string `json:"in"`
	Map     string `json:"map"`
	Players []struct {
		ID string  `json:"id"`
		X  float64 `json:"x"`
		Y  float64 `json:"y"`
	} `json:"players"`
	Monsters []struct {
		ID   string  `json:"id"`
		Type string  `json:"type"`
		X    float64 `json:"x"`
		Y    float64 `json:"y"`
	} `json:"monsters"`
}
sock.On("entities", func(raw json.RawMessage) {
	var data EntitiesPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Type, data.In, data.Map)
	for _, p := range data.Players {
		fmt.Println(p.ID, p.X, p.Y)
	}
	for _, m := range data.Monsters {
		fmt.Println(m.ID, m.Type, m.X, m.Y)
	}
})
```

```csharp
// Monsters hold only the fields that differ from G.monsters[type].
sock.On("entities", data =>
{
    string? typeName = data.GetProperty("type").GetString();
    string? instance = data.GetProperty("in").GetString();
    string? map = data.GetProperty("map").GetString();
    Console.WriteLine($"{typeName} {instance} {map}");
    foreach (JsonElement p in data.GetProperty("players").EnumerateArray())
    {
        string? id = p.GetProperty("id").GetString();
        double x = p.GetProperty("x").GetDouble();
        double y = p.GetProperty("y").GetDouble();
        Console.WriteLine($"{id} {x} {y}");
    }
    foreach (JsonElement m in data.GetProperty("monsters").EnumerateArray())
    {
        string? id = m.GetProperty("id").GetString();
        string? mType = m.GetProperty("type").GetString();
        double x = m.GetProperty("x").GetDouble();
        double y = m.GetProperty("y").GetDouble();
        Console.WriteLine($"{id} {mType} {x} {y}");
    }
});
```

```rust
// Monsters hold only the fields that differ from G.monsters[type].
sock.on("entities", |data| {
    let type_name = data["type"].as_str().unwrap_or_default();
    let instance = data["in"].as_str().unwrap_or_default();
    let map = data["map"].as_str().unwrap_or_default();
    println!("{type_name} {instance} {map}");
    for p in data["players"].as_array().into_iter().flatten() {
        let id = p["id"].as_str().unwrap_or_default();
        let x = p["x"].as_f64().unwrap_or(0.0);
        let y = p["y"].as_f64().unwrap_or(0.0);
        println!("{id} {x} {y}");
    }
    for m in data["monsters"].as_array().into_iter().flatten() {
        let id = m["id"].as_str().unwrap_or_default();
        let type_name = m["type"].as_str().unwrap_or_default();
        let x = m["x"].as_f64().unwrap_or(0.0);
        let y = m["y"].as_f64().unwrap_or(0.0);
        println!("{id} {type_name} {x} {y}");
    }
});
```

```java
// Monsters hold only the fields that differ from G.monsters[type].
sock.on("entities", data -> {
    String typeName = data.path("type").asText();
    String instance = data.path("in").asText();
    String map = data.path("map").asText();
    System.out.println(typeName + " " + instance + " " + map);
    for (JsonNode p : data.path("players")) {
        String id = p.path("id").asText();
        double x = p.path("x").asDouble();
        double y = p.path("y").asDouble();
        System.out.println(id + " " + x + " " + y);
    }
    for (JsonNode m : data.path("monsters")) {
        String id = m.path("id").asText();
        String mType = m.path("type").asText();
        double x = m.path("x").asDouble();
        double y = m.path("y").asDouble();
        System.out.println(id + " " + mType + " " + x + " " + y);
    }
});
```

**Source:** `node/server.js:13675-13754` (`send_xy_updates`), `node/server_functions.js:3675-3708` (`send_all_xy`).

### `player`
The full state of your character. Most actions that change the character send it.

<!-- schema -->

**Notes:**
- Each `player` is a full state, not a change. Replace the old state.
- Handle `hitchhikers` in order, after you apply the state. They hold results that were waiting, for example the result of an `upgrade` or a `compound`.
- Other characters in view arrive in `entities`, with fewer fields (`player_to_client` with `stranger`).

**Example:**

```js
// sock: a connected AlSocket
// The full state of the character.
sock.on("player", (data) => {
  console.log(data.hp, data.max_hp, data.mp, data.max_mp, data.map, data.x, data.y, data.gold, data.items, data.hitchhikers);
});
```

```ts
// The full state of the character.
interface PlayerPayload {
  hp: number;
  max_hp: number;
  mp: number;
  max_mp: number;
  map: string;
  x: number;
  y: number;
  gold: number;
  items: unknown[];
  hitchhikers?: unknown[];
}
sock.on<PlayerPayload>("player", (data) => {
  console.log(data.hp, data.max_hp, data.mp, data.max_mp, data.map, data.x, data.y, data.gold, data.items, data.hitchhikers);
});
```

```python
# The full state of the character.
def on_player(data: dict) -> None:
    print(data["hp"], data["max_hp"], data["mp"], data["max_mp"], data["map"], data["x"], data["y"], data["gold"], data["items"], data.get("hitchhikers"))

sock.on("player", on_player)
```

```go
// The full state of the character.
type PlayerPayload struct {
	Hp          float64 `json:"hp"`
	MaxHp       float64 `json:"max_hp"`
	Mp          float64 `json:"mp"`
	MaxMp       float64 `json:"max_mp"`
	Map         string  `json:"map"`
	X           float64 `json:"x"`
	Y           float64 `json:"y"`
	Gold        float64 `json:"gold"`
	Items       []any   `json:"items"`
	Hitchhikers []any   `json:"hitchhikers"` // optional
}
sock.On("player", func(raw json.RawMessage) {
	var data PlayerPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Hp, data.MaxHp, data.Mp, data.MaxMp, data.Map, data.X, data.Y, data.Gold, data.Items, data.Hitchhikers)
})
```

```csharp
// The full state of the character.
sock.On("player", data =>
{
    double hp = data.GetProperty("hp").GetDouble();
    double maxHp = data.GetProperty("max_hp").GetDouble();
    double mp = data.GetProperty("mp").GetDouble();
    double maxMp = data.GetProperty("max_mp").GetDouble();
    string? map = data.GetProperty("map").GetString();
    double x = data.GetProperty("x").GetDouble();
    double y = data.GetProperty("y").GetDouble();
    double gold = data.GetProperty("gold").GetDouble();
    JsonElement items = data.GetProperty("items");
    JsonElement? hitchhikers = data.TryGetProperty("hitchhikers", out var hitchhikersEl) ? hitchhikersEl : null;
    Console.WriteLine($"{hp} {maxHp} {mp} {maxMp} {map} {x} {y} {gold} {items} {hitchhikers}");
});
```

```rust
// The full state of the character.
sock.on("player", |data| {
    let hp = data["hp"].as_f64().unwrap_or(0.0);
    let max_hp = data["max_hp"].as_f64().unwrap_or(0.0);
    let mp = data["mp"].as_f64().unwrap_or(0.0);
    let max_mp = data["max_mp"].as_f64().unwrap_or(0.0);
    let map = data["map"].as_str().unwrap_or_default();
    let x = data["x"].as_f64().unwrap_or(0.0);
    let y = data["y"].as_f64().unwrap_or(0.0);
    let gold = data["gold"].as_f64().unwrap_or(0.0);
    let items = &data["items"];
    let hitchhikers = data.get("hitchhikers"); // optional
    println!("{hp} {max_hp} {mp} {max_mp} {map} {x} {y} {gold} {items} {hitchhikers:?}");
});
```

```java
// The full state of the character.
sock.on("player", data -> {
    double hp = data.path("hp").asDouble();
    double maxHp = data.path("max_hp").asDouble();
    double mp = data.path("mp").asDouble();
    double maxMp = data.path("max_mp").asDouble();
    String map = data.path("map").asText();
    double x = data.path("x").asDouble();
    double y = data.path("y").asDouble();
    double gold = data.path("gold").asDouble();
    JsonNode items = data.path("items");
    JsonNode hitchhikers = data.get("hitchhikers"); // optional: null when absent
    System.out.println(hp + " " + maxHp + " " + mp + " " + maxMp + " " + map + " " + x + " " + y + " " + gold + " " + items + " " + hitchhikers);
});
```

**Source:** `node/server.js:855-958` (`player_to_client`), `node/server.js:4550-4596` (`resend`)

### `disappear`
An entity left view or stopped existing (transport, invisibility, disconnect, monster removal), or a skill target is not there.

<!-- schema -->

**Notes:**
- Remove the entity `id` from the local world. Only `outside` means that the entity can still exist.
- For `not_there`, the official client rejects the promise of the skill in `place`.
- `remove_entity_emit` tracks what each client has (`seen`). A client that had the entity gets the event even when the entity is now out of its view (`node/server_functions.js:3834-3866`).
- `death` is the other form of a monster removal. With `silent`, only the clients that had the monster get `disappear`.

**Example:**

```js
// sock: a connected AlSocket
// Remove the entity `id` from the local world state.
sock.on("disappear", (data) => {
  console.log(data.id, data.reason, data.outside);
});
```

```ts
// Remove the entity `id` from the local world state.
interface DisappearPayload {
  id: string;
  reason?: string;
  outside?: boolean;
}
sock.on<DisappearPayload>("disappear", (data) => {
  console.log(data.id, data.reason, data.outside);
});
```

```python
# Remove the entity `id` from the local world state.
def on_disappear(data: dict) -> None:
    print(data["id"], data.get("reason"), data.get("outside"))

sock.on("disappear", on_disappear)
```

```go
// Remove the entity `id` from the local world state.
type DisappearPayload struct {
	ID      string `json:"id"`
	Reason  string `json:"reason"`  // optional
	Outside bool   `json:"outside"` // optional
}
sock.On("disappear", func(raw json.RawMessage) {
	var data DisappearPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.ID, data.Reason, data.Outside)
})
```

```csharp
// Remove the entity `id` from the local world state.
sock.On("disappear", data =>
{
    string? id = data.GetProperty("id").GetString();
    string? reason = data.TryGetProperty("reason", out var reasonEl) ? reasonEl.GetString() : null;
    bool? outside = data.TryGetProperty("outside", out var outsideEl) ? outsideEl.GetBoolean() : null;
    Console.WriteLine($"{id} {reason} {outside}");
});
```

```rust
// Remove the entity `id` from the local world state.
sock.on("disappear", |data| {
    let id = data["id"].as_str().unwrap_or_default();
    let reason = data["reason"].as_str(); // optional
    let outside = data["outside"].as_bool(); // optional
    println!("{id} {reason:?} {outside:?}");
});
```

```java
// Remove the entity `id` from the local world state.
sock.on("disappear", data -> {
    String id = data.path("id").asText();
    String reason = data.path("reason").asText(null); // optional
    JsonNode outside = data.get("outside"); // optional: null when absent
    System.out.println(id + " " + reason + " " + outside);
});
```

**Source:** `node/server_functions.js:3834-3866` (`remove_entity_emit`), `node/server.js:4596-4660` (`transport_monster_to`, `transport_player_to`), `node/server.js:13699`, `node/server.js:9920`.

### `new_map`
The server sends it when a player or observer moves to another map or instance.

<!-- schema -->

**Notes:**
- Before `new_map`, the receiver gets `disappear` (`outside: true`) for each entity of the old view that is not in the new frame.
- Others at the old position get `disappear` with `reason: "transport"`.
- A generated destination (the Cave of Many Dreams) sends `map_chunk` events first.
- A character also gets `player` right after `new_map` (`resend`, `node/server.js:4757`).
- The code also builds an `eval` field, but in a disabled block (`if (0 && ...)`). Its value is `undefined`, so JSON leaves it out (`node/server.js:4727-4738`).

**Example:**

```js
// sock: a connected AlSocket
// `m` is the new map change counter.
sock.on("new_map", (data) => {
  console.log(data.name, data.in, data.x, data.y, data.m, data.effect, data.entities);
});
```

```ts
// `m` is the new map change counter.
interface NewMapPayload {
  name: string;
  in: string;
  x: number;
  y: number;
  m: number;
  effect: unknown;
  entities: Record<string, unknown>;
}
sock.on<NewMapPayload>("new_map", (data) => {
  console.log(data.name, data.in, data.x, data.y, data.m, data.effect, data.entities);
});
```

```python
# `m` is the new map change counter.
def on_new_map(data: dict) -> None:
    print(data["name"], data["in"], data["x"], data["y"], data["m"], data["effect"], data["entities"])

sock.on("new_map", on_new_map)
```

```go
// `m` is the new map change counter.
type NewMapPayload struct {
	Name     string         `json:"name"`
	In       string         `json:"in"`
	X        float64        `json:"x"`
	Y        float64        `json:"y"`
	M        int            `json:"m"`
	Effect   any            `json:"effect"`
	Entities map[string]any `json:"entities"`
}
sock.On("new_map", func(raw json.RawMessage) {
	var data NewMapPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name, data.In, data.X, data.Y, data.M, data.Effect, data.Entities)
})
```

```csharp
// `m` is the new map change counter.
sock.On("new_map", data =>
{
    string? name = data.GetProperty("name").GetString();
    string? instance = data.GetProperty("in").GetString();
    double x = data.GetProperty("x").GetDouble();
    double y = data.GetProperty("y").GetDouble();
    int m = data.GetProperty("m").GetInt32();
    JsonElement effect = data.GetProperty("effect");
    JsonElement entities = data.GetProperty("entities");
    Console.WriteLine($"{name} {instance} {x} {y} {m} {effect} {entities}");
});
```

```rust
// `m` is the new map change counter.
sock.on("new_map", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    let instance = data["in"].as_str().unwrap_or_default();
    let x = data["x"].as_f64().unwrap_or(0.0);
    let y = data["y"].as_f64().unwrap_or(0.0);
    let m = data["m"].as_i64().unwrap_or(0);
    let effect = &data["effect"];
    let entities = &data["entities"];
    println!("{name} {instance} {x} {y} {m} {effect} {entities}");
});
```

```java
// `m` is the new map change counter.
sock.on("new_map", data -> {
    String name = data.path("name").asText();
    String instance = data.path("in").asText();
    double x = data.path("x").asDouble();
    double y = data.path("y").asDouble();
    int m = data.path("m").asInt();
    JsonNode effect = data.path("effect");
    JsonNode entities = data.path("entities");
    System.out.println(name + " " + instance + " " + x + " " + y + " " + m + " " + effect + " " + entities);
});
```

**Source:** `node/server.js:4640-4758` (`transport_player_to`), `node/server.js:4614-4638` (`transport_observer_to`).

### `correction`
The server's position for the player.

<!-- schema -->

**Notes:**
- Set the local position of the character to `x`, `y`. The server does not use the position that the client sends: it only compares it.
- The `move` still takes effect. The character moves from the server position to `going_x`, `going_y`.

**Example:**

```js
// sock: a connected AlSocket
// The position of the character on the server.
sock.on("correction", (data) => {
  console.log(data.x, data.y);
});
```

```ts
// The position of the character on the server.
interface CorrectionPayload {
  x: number;
  y: number;
}
sock.on<CorrectionPayload>("correction", (data) => {
  console.log(data.x, data.y);
});
```

```python
# The position of the character on the server.
def on_correction(data: dict) -> None:
    print(data["x"], data["y"])

sock.on("correction", on_correction)
```

```go
// The position of the character on the server.
type CorrectionPayload struct {
	X float64 `json:"x"`
	Y float64 `json:"y"`
}
sock.On("correction", func(raw json.RawMessage) {
	var data CorrectionPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.X, data.Y)
})
```

```csharp
// The position of the character on the server.
sock.On("correction", data =>
{
    double x = data.GetProperty("x").GetDouble();
    double y = data.GetProperty("y").GetDouble();
    Console.WriteLine($"{x} {y}");
});
```

```rust
// The position of the character on the server.
sock.on("correction", |data| {
    let x = data["x"].as_f64().unwrap_or(0.0);
    let y = data["y"].as_f64().unwrap_or(0.0);
    println!("{x} {y}");
});
```

```java
// The position of the character on the server.
sock.on("correction", data -> {
    double x = data.path("x").asDouble();
    double y = data.path("y").asDouble();
    System.out.println(x + " " + y);
});
```

**Source:** `node/server.js:11248-11256` (`move`), `node/logic/instance_pause.js:107` (cave pause).

### `death`
A monster died. `remove_monster` sends it; its default `method` is `"death"`.

<!-- schema -->

**Notes:**
- `remove_monster` sends `death` by default. With `method: "disappear"` or with `silent`, it sends `disappear` with the same fields. With `silent`, only the clients that had the monster get it.
- `death` has no literal `emit("death"` in the code. The event name is the value of `args.method` (`node/server.js:13354-13356`, `node/server.js:13401`).

**Example:**

```js
// sock: a connected AlSocket
// The monster `id` died.
sock.on("death", (data) => {
  console.log(data.id, data.luckm);
});
```

```ts
// The monster `id` died.
interface DeathPayload {
  id: string;
  luckm: number;
}
sock.on<DeathPayload>("death", (data) => {
  console.log(data.id, data.luckm);
});
```

```python
# The monster `id` died.
def on_death(data: dict) -> None:
    print(data["id"], data["luckm"])

sock.on("death", on_death)
```

```go
// The monster `id` died.
type DeathPayload struct {
	ID    string  `json:"id"`
	Luckm float64 `json:"luckm"`
}
sock.On("death", func(raw json.RawMessage) {
	var data DeathPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.ID, data.Luckm)
})
```

```csharp
// The monster `id` died.
sock.On("death", data =>
{
    string? id = data.GetProperty("id").GetString();
    double luckm = data.GetProperty("luckm").GetDouble();
    Console.WriteLine($"{id} {luckm}");
});
```

```rust
// The monster `id` died.
sock.on("death", |data| {
    let id = data["id"].as_str().unwrap_or_default();
    let luckm = data["luckm"].as_f64().unwrap_or(0.0);
    println!("{id} {luckm}");
});
```

```java
// The monster `id` died.
sock.on("death", data -> {
    String id = data.path("id").asText();
    double luckm = data.path("luckm").asDouble();
    System.out.println(id + " " + luckm);
});
```

**Source:** `node/server.js:13350-13401`.

### `map_info`
The state of a duel: the countdown and the two teams. The server sends it each second while the duel runs.

<!-- schema -->

**Notes:**
- The first `map_info` comes about 1 s after `new_map`. `new_map` already has the same object in `info`.
- When one team has no active member, the duel ends. The server then stops `map_info` and announces the winner in `game_chat`.

**Example:**

```js
// sock: a connected AlSocket
// `seconds` counts down to the fight. A and B are the teams.
sock.on("map_info", (data) => {
  console.log(data.id, data.seconds, data.active);
  for (const p of data.A) console.log("A", p.name, p.hp, p.max_hp, p.active);
  for (const p of data.B) console.log("B", p.name, p.hp, p.max_hp, p.active);
});
```

```ts
// `seconds` counts down to the fight. A and B are the teams.
interface MapInfoMember {
  name: string;
  hp: number;
  max_hp: number;
  active: boolean;
}
interface MapInfoPayload {
  id: string;
  seconds: number;
  active: boolean;
  A: MapInfoMember[];
  B: MapInfoMember[];
}
sock.on<MapInfoPayload>("map_info", (data) => {
  console.log(data.id, data.seconds, data.active);
  for (const p of data.A) console.log("A", p.name, p.hp, p.max_hp, p.active);
  for (const p of data.B) console.log("B", p.name, p.hp, p.max_hp, p.active);
});
```

```python
# `seconds` counts down to the fight. A and B are the teams.
def on_map_info(data: dict) -> None:
    print(data["id"], data["seconds"], data["active"])
    for team in ("A", "B"):
        for p in data[team]:
            print(team, p["name"], p["hp"], p["max_hp"], p["active"])

sock.on("map_info", on_map_info)
```

```go
// `seconds` counts down to the fight. A and B are the teams.
type MapInfoMember struct {
	Name   string `json:"name"`
	Hp     int64  `json:"hp"`
	MaxHp  int64  `json:"max_hp"`
	Active bool   `json:"active"`
}
type MapInfoPayload struct {
	ID      string           `json:"id"`
	Seconds int64            `json:"seconds"`
	Active  bool             `json:"active"`
	A       []MapInfoMember `json:"A"`
	B       []MapInfoMember `json:"B"`
}
sock.On("map_info", func(raw json.RawMessage) {
	var data MapInfoPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.ID, data.Seconds, data.Active)
	for _, p := range data.A {
		fmt.Println("A", p.Name, p.Hp, p.MaxHp, p.Active)
	}
	for _, p := range data.B {
		fmt.Println("B", p.Name, p.Hp, p.MaxHp, p.Active)
	}
})
```

```csharp
// `seconds` counts down to the fight. A and B are the teams.
sock.On("map_info", data =>
{
    string? id = data.GetProperty("id").GetString();
    long seconds = data.GetProperty("seconds").GetInt64();
    bool active = data.GetProperty("active").GetBoolean();
    Console.WriteLine($"{id} {seconds} {active}");
    foreach (string team in new[] { "A", "B" })
    {
        foreach (JsonElement p in data.GetProperty(team).EnumerateArray())
        {
            string? name = p.GetProperty("name").GetString();
            long hp = p.GetProperty("hp").GetInt64();
            long maxHp = p.GetProperty("max_hp").GetInt64();
            bool pActive = p.GetProperty("active").GetBoolean();
            Console.WriteLine($"{team} {name} {hp} {maxHp} {pActive}");
        }
    }
});
```

```rust
// `seconds` counts down to the fight. A and B are the teams.
sock.on("map_info", |data| {
    let id = data["id"].as_str().unwrap_or_default();
    let seconds = data["seconds"].as_i64().unwrap_or(0);
    let active = data["active"].as_bool().unwrap_or(false);
    println!("{id} {seconds} {active}");
    for team in ["A", "B"] {
        for p in data[team].as_array().into_iter().flatten() {
            let name = p["name"].as_str().unwrap_or_default();
            let hp = p["hp"].as_i64().unwrap_or(0);
            let max_hp = p["max_hp"].as_i64().unwrap_or(0);
            let p_active = p["active"].as_bool().unwrap_or(false);
            println!("{team} {name} {hp} {max_hp} {p_active}");
        }
    }
});
```

```java
// `seconds` counts down to the fight. A and B are the teams.
sock.on("map_info", data -> {
    String id = data.path("id").asText();
    long seconds = data.path("seconds").asLong();
    boolean active = data.path("active").asBoolean();
    System.out.println(id + " " + seconds + " " + active);
    for (String team : List.of("A", "B")) {
        for (JsonNode p : data.path(team)) {
            String name = p.path("name").asText();
            long hp = p.path("hp").asLong();
            long maxHp = p.path("max_hp").asLong();
            boolean pActive = p.path("active").asBoolean();
            System.out.println(team + " " + name + " " + hp + " " + maxHp + " " + pActive);
        }
    }
});
```

**Source:** `node/server.js:12233-12246` (the duel instance), `node/server_functions.js:2899-3011` (the loop).

### `light`
A `light` skill or a monster `mlight` event showed the invisible players nearby.

<!-- schema -->

**Notes:**
- A character with `affected` loses `invis`, and the server sets `last.invis`. The server does not check if the character was invisible: a visible rogue nearby also gets `affected`.
- The character that gets `affected` does not also get the form without it.

**Example:**

```js
// sock: a connected AlSocket
// `affected` is 1 for a rogue or an invisible player nearby.
sock.on("light", (data) => {
  console.log(data.name, data.affected);
});
```

```ts
// `affected` is 1 for a rogue or an invisible player nearby.
interface LightPayload {
  name: string;
  affected?: number;
}
sock.on<LightPayload>("light", (data) => {
  console.log(data.name, data.affected);
});
```

```python
# `affected` is 1 for a rogue or an invisible player nearby.
def on_light(data: dict) -> None:
    print(data["name"], data.get("affected"))

sock.on("light", on_light)
```

```go
// `affected` is 1 for a rogue or an invisible player nearby.
type LightPayload struct {
	Name     string `json:"name"`
	Affected int    `json:"affected"` // optional
}
sock.On("light", func(raw json.RawMessage) {
	var data LightPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name, data.Affected)
})
```

```csharp
// `affected` is 1 for a rogue or an invisible player nearby.
sock.On("light", data =>
{
    string? name = data.GetProperty("name").GetString();
    int? affected = data.TryGetProperty("affected", out var affectedEl) ? affectedEl.GetInt32() : null;
    Console.WriteLine($"{name} {affected}");
});
```

```rust
// `affected` is 1 for a rogue or an invisible player nearby.
sock.on("light", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    let affected = data["affected"].as_i64(); // optional
    println!("{name} {affected:?}");
});
```

```java
// `affected` is 1 for a rogue or an invisible player nearby.
sock.on("light", data -> {
    String name = data.path("name").asText();
    JsonNode affected = data.get("affected"); // optional: null when absent
    System.out.println(name + " " + affected);
});
```

**Source:** `node/server.js:10174`, `node/server.js:14246`, `node/server_functions.js:3762-3766`.

### `blocker`
The reply to the client's `blocker` request. It tells if the arena PvP blocker lets players through.

<!-- schema -->

**Notes:**
- If the request `type` is not `"pvp"`, the server sends nothing.
- If the server has no `arena` instance, the handler throws and sends nothing (`node/server.js:5592`).

**Example:**

```js
// sock: a connected AlSocket
// `allow` is 1 when the arena lets players through.
sock.on("blocker", (data) => {
  console.log(data.type, data.allow);
});
```

```ts
// `allow` is 1 when the arena lets players through.
interface BlockerPayload {
  type: string;
  allow?: number;
}
sock.on<BlockerPayload>("blocker", (data) => {
  console.log(data.type, data.allow);
});
```

```python
# `allow` is 1 when the arena lets players through.
def on_blocker(data: dict) -> None:
    print(data["type"], data.get("allow"))

sock.on("blocker", on_blocker)
```

```go
// `allow` is 1 when the arena lets players through.
type BlockerPayload struct {
	Type  string `json:"type"`
	Allow int    `json:"allow"` // optional
}
sock.On("blocker", func(raw json.RawMessage) {
	var data BlockerPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Type, data.Allow)
})
```

```csharp
// `allow` is 1 when the arena lets players through.
sock.On("blocker", data =>
{
    string? typeName = data.GetProperty("type").GetString();
    int? allow = data.TryGetProperty("allow", out var allowEl) ? allowEl.GetInt32() : null;
    Console.WriteLine($"{typeName} {allow}");
});
```

```rust
// `allow` is 1 when the arena lets players through.
sock.on("blocker", |data| {
    let type_name = data["type"].as_str().unwrap_or_default();
    let allow = data["allow"].as_i64(); // optional
    println!("{type_name} {allow:?}");
});
```

```java
// `allow` is 1 when the arena lets players through.
sock.on("blocker", data -> {
    String typeName = data.path("type").asText();
    JsonNode allow = data.get("allow"); // optional: null when absent
    System.out.println(typeName + " " + allow);
});
```

**Source:** `node/server.js:5593-5595`.

### `emote`
A player used an emote skill (a skill with `emote` in `G.skills`).

<!-- schema -->

**Example:**

```js
// sock: a connected AlSocket
// `variation` is 0, 1 or 2.
sock.on("emote", (data) => {
  console.log(data.name, data.player, data.target, data.variation);
});
```

```ts
// `variation` is 0, 1 or 2.
interface EmotePayload {
  name: string;
  player: string;
  target?: string;
  variation: number;
}
sock.on<EmotePayload>("emote", (data) => {
  console.log(data.name, data.player, data.target, data.variation);
});
```

```python
# `variation` is 0, 1 or 2.
def on_emote(data: dict) -> None:
    print(data["name"], data["player"], data.get("target"), data["variation"])

sock.on("emote", on_emote)
```

```go
// `variation` is 0, 1 or 2.
type EmotePayload struct {
	Name      string `json:"name"`
	Player    string `json:"player"`
	Target    string `json:"target"` // optional
	Variation int    `json:"variation"`
}
sock.On("emote", func(raw json.RawMessage) {
	var data EmotePayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name, data.Player, data.Target, data.Variation)
})
```

```csharp
// `variation` is 0, 1 or 2.
sock.On("emote", data =>
{
    string? name = data.GetProperty("name").GetString();
    string? player = data.GetProperty("player").GetString();
    string? target = data.TryGetProperty("target", out var targetEl) ? targetEl.GetString() : null;
    int variation = data.GetProperty("variation").GetInt32();
    Console.WriteLine($"{name} {player} {target} {variation}");
});
```

```rust
// `variation` is 0, 1 or 2.
sock.on("emote", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    let player = data["player"].as_str().unwrap_or_default();
    let target = data["target"].as_str(); // optional
    let variation = data["variation"].as_i64().unwrap_or(0);
    println!("{name} {player} {target:?} {variation}");
});
```

```java
// `variation` is 0, 1 or 2.
sock.on("emote", data -> {
    String name = data.path("name").asText();
    String player = data.path("player").asText();
    String target = data.path("target").asText(null); // optional
    int variation = data.path("variation").asInt();
    System.out.println(name + " " + player + " " + target + " " + variation);
});
```

**Source:** `node/server.js:10076-10081`.

### `poke`
A player poked someone.

<!-- schema -->

**Notes:**
- Without the `poker` gloves, the server sends nothing. After 50 pokes in one session, you get a `game_log` instead (`node/server.js:9560-9562`).
- `name` is not checked. Do not trust it as a character name.

**Example:**

```js
// sock: a connected AlSocket
// `who` poked `name`.
sock.on("poke", (data) => {
  console.log(data.name, data.level, data.who);
});
```

```ts
// `who` poked `name`.
interface PokePayload {
  name: string;
  level: number;
  who: string;
}
sock.on<PokePayload>("poke", (data) => {
  console.log(data.name, data.level, data.who);
});
```

```python
# `who` poked `name`.
def on_poke(data: dict) -> None:
    print(data["name"], data["level"], data["who"])

sock.on("poke", on_poke)
```

```go
// `who` poked `name`.
type PokePayload struct {
	Name  string  `json:"name"`
	Level float64 `json:"level"`
	Who   string  `json:"who"`
}
sock.On("poke", func(raw json.RawMessage) {
	var data PokePayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name, data.Level, data.Who)
})
```

```csharp
// `who` poked `name`.
sock.On("poke", data =>
{
    string? name = data.GetProperty("name").GetString();
    double level = data.GetProperty("level").GetDouble();
    string? who = data.GetProperty("who").GetString();
    Console.WriteLine($"{name} {level} {who}");
});
```

```rust
// `who` poked `name`.
sock.on("poke", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    let level = data["level"].as_f64().unwrap_or(0.0);
    let who = data["who"].as_str().unwrap_or_default();
    println!("{name} {level} {who}");
});
```

```java
// `who` poked `name`.
sock.on("poke", data -> {
    String name = data.path("name").asText();
    double level = data.path("level").asDouble();
    String who = data.path("who").asText();
    System.out.println(name + " " + level + " " + who);
});
```

**Source:** `node/server.js:9554-9572`.

### `citizen`
An animation or effect of a town NPC (a citizen).

<!-- schema -->

**Notes:** the `dealer` forms are animations only; the server picks each act so that every viewer sees the same one (`node/logic/tavern_dealer.js:1-4`).

**Example:**

```js
// sock: a connected AlSocket
// The other fields depend on `type`.
sock.on("citizen", (data) => {
  switch (data.type) {
    case "repair":
      console.log(data.target, data.x, data.y);
      break;
    case "lamp":
      console.log(data.x, data.y);
      break;
    case "route_marks":
      console.log(data.destination);
      break;
    case "dealer":
      console.log(data.id, data.act);
      break;
    default:
      console.log(data.type);
  }
});
```

```ts
// The other fields depend on `type`.
interface CitizenPayload {
  type: string;
  target?: string;
  x?: number;
  y?: number;
  destination?: string;
  id?: string;
  act?: string;
}
sock.on<CitizenPayload>("citizen", (data) => {
  switch (data.type) {
    case "repair":
      console.log(data.target, data.x, data.y);
      break;
    case "lamp":
      console.log(data.x, data.y);
      break;
    case "route_marks":
      console.log(data.destination);
      break;
    case "dealer":
      console.log(data.id, data.act);
      break;
    default:
      console.log(data.type);
  }
});
```

```python
# The other fields depend on `type`.
def on_citizen(data: dict) -> None:
    match data["type"]:
        case "repair":
            print(data["target"], data["x"], data["y"])
        case "lamp":
            print(data["x"], data["y"])
        case "route_marks":
            print(data["destination"])
        case "dealer":
            print(data["id"], data["act"])
        case _:
            print(data["type"])

sock.on("citizen", on_citizen)
```

```go
// The other fields depend on `type`.
type CitizenPayload struct {
	Type        string  `json:"type"`
	Target      string  `json:"target"`
	X           float64 `json:"x"`
	Y           float64 `json:"y"`
	Destination string  `json:"destination"`
	ID          string  `json:"id"`
	Act         string  `json:"act"`
}
sock.On("citizen", func(raw json.RawMessage) {
	var data CitizenPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	switch data.Type {
	case "repair":
		fmt.Println(data.Target, data.X, data.Y)
	case "lamp":
		fmt.Println(data.X, data.Y)
	case "route_marks":
		fmt.Println(data.Destination)
	case "dealer":
		fmt.Println(data.ID, data.Act)
	default:
		fmt.Println(data.Type)
	}
})
```

```csharp
// The other fields depend on `type`.
sock.On("citizen", data =>
{
    string? typeName = data.GetProperty("type").GetString();
    switch (typeName)
    {
        case "repair":
        {
            string? target = data.GetProperty("target").GetString();
            double x = data.GetProperty("x").GetDouble();
            double y = data.GetProperty("y").GetDouble();
            Console.WriteLine($"{target} {x} {y}");
            break;
        }
        case "lamp":
        {
            double x = data.GetProperty("x").GetDouble();
            double y = data.GetProperty("y").GetDouble();
            Console.WriteLine($"{x} {y}");
            break;
        }
        case "route_marks":
        {
            string? destination = data.GetProperty("destination").GetString();
            Console.WriteLine($"{destination}");
            break;
        }
        case "dealer":
        {
            string? id = data.GetProperty("id").GetString();
            string? act = data.GetProperty("act").GetString();
            Console.WriteLine($"{id} {act}");
            break;
        }
        default:
            Console.WriteLine(typeName);
            break;
    }
});
```

```rust
// The other fields depend on `type`.
sock.on("citizen", |data| {
    match data["type"].as_str().unwrap_or_default() {
        "repair" => {
            let target = data["target"].as_str().unwrap_or_default();
            let x = data["x"].as_f64().unwrap_or(0.0);
            let y = data["y"].as_f64().unwrap_or(0.0);
            println!("{target} {x} {y}");
        }
        "lamp" => {
            let x = data["x"].as_f64().unwrap_or(0.0);
            let y = data["y"].as_f64().unwrap_or(0.0);
            println!("{x} {y}");
        }
        "route_marks" => {
            let destination = data["destination"].as_str().unwrap_or_default();
            println!("{destination}");
        }
        "dealer" => {
            let id = data["id"].as_str().unwrap_or_default();
            let act = data["act"].as_str().unwrap_or_default();
            println!("{id} {act}");
        }
        other => println!("{other}"),
    }
});
```

```java
// The other fields depend on `type`.
sock.on("citizen", data -> {
    String typeName = data.path("type").asText();
    switch (typeName) {
        case "repair" -> {
            String target = data.path("target").asText();
            double x = data.path("x").asDouble();
            double y = data.path("y").asDouble();
            System.out.println(target + " " + x + " " + y);
        }
        case "lamp" -> {
            double x = data.path("x").asDouble();
            double y = data.path("y").asDouble();
            System.out.println(x + " " + y);
        }
        case "route_marks" -> {
            String destination = data.path("destination").asText();
            System.out.println(destination);
        }
        case "dealer" -> {
            String id = data.path("id").asText();
            String act = data.path("act").asText();
            System.out.println(id + " " + act);
        }
        default -> System.out.println(typeName);
    }
});
```

**Source:** `node/server.js:15376-15465` (repair and lamp loops), `node/server.js:11056-11079` (route marks), `node/logic/tavern_dealer.js:29-86` (dealer).

## Combat

### `action`
An attack, heal or projectile skill started. The result arrives later as `hit`.

<!-- schema -->

**Notes:**
- The attacker also gets the same object as a `game_response`, with `response: "data"` and `place` (the skill) (node/server.js:3609-3612).
- A reflection sends the same object again: `attacker` and `target` change places, and `pid`, `x`, `y`, `m` and `reflect` are new (node/server.js:3784-3791). It also has `map`, `in`, `response` and `place`, because the server added them to the object after the first send.
- **Server bug:** a reflected `action` keeps the `eta` of the first projectile. The server times the hit of the reflection from the real distance (node/server.js:3776-3778), so `eta` can be wrong.

**Example:**

```js
// sock: a connected AlSocket
// The result arrives later as `hit` with the same `pid`.
sock.on("action", (data) => {
  console.log(data.attacker, data.target, data.type, data.pid, data.eta, data.damage, data.heal);
});
```

```ts
// The result arrives later as `hit` with the same `pid`.
interface ActionPayload {
  attacker: string;
  target: string;
  type: string;
  pid: string;
  eta: number;
  damage?: number;
  heal?: number;
}
sock.on<ActionPayload>("action", (data) => {
  console.log(data.attacker, data.target, data.type, data.pid, data.eta, data.damage, data.heal);
});
```

```python
# The result arrives later as `hit` with the same `pid`.
def on_action(data: dict) -> None:
    print(data["attacker"], data["target"], data["type"], data["pid"], data["eta"], data.get("damage"), data.get("heal"))

sock.on("action", on_action)
```

```go
// The result arrives later as `hit` with the same `pid`.
type ActionPayload struct {
	Attacker string  `json:"attacker"`
	Target   string  `json:"target"`
	Type     string  `json:"type"`
	PID      string  `json:"pid"`
	Eta      float64 `json:"eta"`
	Damage   float64 `json:"damage"` // optional
	Heal     float64 `json:"heal"`   // optional
}
sock.On("action", func(raw json.RawMessage) {
	var data ActionPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Attacker, data.Target, data.Type, data.PID, data.Eta, data.Damage, data.Heal)
})
```

```csharp
// The result arrives later as `hit` with the same `pid`.
sock.On("action", data =>
{
    string? attacker = data.GetProperty("attacker").GetString();
    string? target = data.GetProperty("target").GetString();
    string? typeName = data.GetProperty("type").GetString();
    string? pid = data.GetProperty("pid").GetString();
    double eta = data.GetProperty("eta").GetDouble();
    double? damage = data.TryGetProperty("damage", out var damageEl) ? damageEl.GetDouble() : null;
    double? heal = data.TryGetProperty("heal", out var healEl) ? healEl.GetDouble() : null;
    Console.WriteLine($"{attacker} {target} {typeName} {pid} {eta} {damage} {heal}");
});
```

```rust
// The result arrives later as `hit` with the same `pid`.
sock.on("action", |data| {
    let attacker = data["attacker"].as_str().unwrap_or_default();
    let target = data["target"].as_str().unwrap_or_default();
    let type_name = data["type"].as_str().unwrap_or_default();
    let pid = data["pid"].as_str().unwrap_or_default();
    let eta = data["eta"].as_f64().unwrap_or(0.0);
    let damage = data["damage"].as_f64(); // optional
    let heal = data["heal"].as_f64(); // optional
    println!("{attacker} {target} {type_name} {pid} {eta} {damage:?} {heal:?}");
});
```

```java
// The result arrives later as `hit` with the same `pid`.
sock.on("action", data -> {
    String attacker = data.path("attacker").asText();
    String target = data.path("target").asText();
    String typeName = data.path("type").asText();
    String pid = data.path("pid").asText();
    double eta = data.path("eta").asDouble();
    JsonNode damage = data.get("damage"); // optional: null when absent
    JsonNode heal = data.get("heal"); // optional: null when absent
    System.out.println(attacker + " " + target + " " + typeName + " " + pid + " " + eta + " " + damage + " " + heal);
});
```

**Source:** `node/server.js:3547-3612` (`commence_attack`), `node/server.js:3809` (reflection).

### `hit`
Damage, a heal, a miss or an evade reached an entity.

<!-- schema -->

**Notes:**
- Monster attacks send `hit` directly, as player attacks do. `mode.instant_monster_attacks` is `1` (node/server.js:292), so the `events.push(["hit", def])` branch (node/server.js:4346) does not run. That array is local and the server never sends it.
- Only `HitBurn` has no `pid`. Only `HitReflect` has no `source`.
- **Server bug:** every `hit` of a reflected projectile has the `pid` of the first `action`. It does not have the new `pid` of the reflected `action`, because `def.pid` does not change (node/server.js:3784).
- **Server bug:** one attack uses one `def` object for all its targets. The server clears only some flags between targets (node/server.js:3964-3973). So `crit`, `lifesteal`, `manasteal`, `goldsteal`, `sneak`, `trigger` and `deepfreeze` can stay from an earlier target of the same splash or stack.
- With `stacked`, every target gets `unintentional: true`, also the target of the `action` (node/server.js:3891-3897).

**Example:**

```js
// sock: a connected AlSocket
// `pid` matches the `action` that started the attack.
sock.on("hit", (data) => {
  console.log(data.id, data.hid, data.pid, data.source, data.damage, data.heal, data.kill, data.miss);
});
```

```ts
// `pid` matches the `action` that started the attack.
interface HitPayload {
  id: string;
  hid: string;
  pid?: string; // absent on a burn tick
  source?: string; // absent on a reflect
  damage?: number;
  heal?: number;
  kill?: boolean;
  miss?: boolean;
}
sock.on<HitPayload>("hit", (data) => {
  console.log(data.id, data.hid, data.pid, data.source, data.damage, data.heal, data.kill, data.miss);
});
```

```python
# `pid` matches the `action` that started the attack.
def on_hit(data: dict) -> None:
    print(data["id"], data["hid"], data.get("pid"), data.get("source"), data.get("damage"), data.get("heal"), data.get("kill"), data.get("miss"))

sock.on("hit", on_hit)
```

```go
// `pid` matches the `action` that started the attack.
type HitPayload struct {
	ID     string  `json:"id"`
	HID    string  `json:"hid"`
	PID    string  `json:"pid"`    // optional: absent on a burn tick
	Source string  `json:"source"` // optional: absent on a reflect
	Damage float64 `json:"damage"` // optional
	Heal   float64 `json:"heal"`   // optional
	Kill   bool    `json:"kill"`   // optional
	Miss   bool    `json:"miss"`   // optional
}
sock.On("hit", func(raw json.RawMessage) {
	var data HitPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.ID, data.HID, data.PID, data.Source, data.Damage, data.Heal, data.Kill, data.Miss)
})
```

```csharp
// `pid` matches the `action` that started the attack.
sock.On("hit", data =>
{
    string? id = data.GetProperty("id").GetString();
    string? hid = data.GetProperty("hid").GetString();
    string? pid = data.TryGetProperty("pid", out var pidEl) ? pidEl.GetString() : null;
    string? source = data.TryGetProperty("source", out var sourceEl) ? sourceEl.GetString() : null;
    double? damage = data.TryGetProperty("damage", out var damageEl) ? damageEl.GetDouble() : null;
    double? heal = data.TryGetProperty("heal", out var healEl) ? healEl.GetDouble() : null;
    bool? kill = data.TryGetProperty("kill", out var killEl) ? killEl.GetBoolean() : null;
    bool? miss = data.TryGetProperty("miss", out var missEl) ? missEl.GetBoolean() : null;
    Console.WriteLine($"{id} {hid} {pid} {source} {damage} {heal} {kill} {miss}");
});
```

```rust
// `pid` matches the `action` that started the attack.
sock.on("hit", |data| {
    let id = data["id"].as_str().unwrap_or_default();
    let hid = data["hid"].as_str().unwrap_or_default();
    let pid = data["pid"].as_str(); // optional
    let source = data["source"].as_str(); // optional: absent on a reflect
    let damage = data["damage"].as_f64(); // optional
    let heal = data["heal"].as_f64(); // optional
    let kill = data["kill"].as_bool(); // optional
    let miss = data["miss"].as_bool(); // optional
    println!("{id} {hid} {pid:?} {source:?} {damage:?} {heal:?} {kill:?} {miss:?}");
});
```

```java
// `pid` matches the `action` that started the attack.
sock.on("hit", data -> {
    String id = data.path("id").asText();
    String hid = data.path("hid").asText();
    String pid = data.path("pid").asText(null); // optional
    String source = data.path("source").asText(null); // optional: absent on a reflect
    JsonNode damage = data.get("damage"); // optional: null when absent
    JsonNode heal = data.get("heal"); // optional: null when absent
    JsonNode kill = data.get("kill"); // optional: null when absent
    JsonNode miss = data.get("miss"); // optional: null when absent
    System.out.println(id + " " + hid + " " + pid + " " + source + " " + damage + " " + heal + " " + kill + " " + miss);
});
```

**Source:** `node/server.js:3707-4468` (`complete_attack`), `node/server.js:14059-14065`, `node/server.js:14676-14682` (burn ticks).

### `kill_credit`
The player got credit for a monster kill.

<!-- schema -->

**Notes:** for a monster that is not cooperative, the credit goes to the target of the monster, not to the last hit. `kill_monster` makes the killer the target only when the monster has no target (node/server.js:2882-2888).

**Example:**

```js
// sock: a connected AlSocket
// The kill counts for this player.
sock.on("kill_credit", (data) => {
  console.log(data.mtype);
});
```

```ts
// The kill counts for this player.
interface KillCreditPayload {
  mtype: string;
}
sock.on<KillCreditPayload>("kill_credit", (data) => {
  console.log(data.mtype);
});
```

```python
# The kill counts for this player.
def on_kill_credit(data: dict) -> None:
    print(data["mtype"])

sock.on("kill_credit", on_kill_credit)
```

```go
// The kill counts for this player.
type KillCreditPayload struct {
	Mtype string `json:"mtype"`
}
sock.On("kill_credit", func(raw json.RawMessage) {
	var data KillCreditPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Mtype)
})
```

```csharp
// The kill counts for this player.
sock.On("kill_credit", data =>
{
    string? mtype = data.GetProperty("mtype").GetString();
    Console.WriteLine($"{mtype}");
});
```

```rust
// The kill counts for this player.
sock.on("kill_credit", |data| {
    let mtype = data["mtype"].as_str().unwrap_or_default();
    println!("{mtype}");
});
```

```java
// The kill counts for this player.
sock.on("kill_credit", data -> {
    String mtype = data.path("mtype").asText();
    System.out.println(mtype);
});
```

**Source:** `node/server.js:2738`, `node/server.js:2790`, `node/server.js:2831`.

### `skill_timeout`
Tells the client to start (or start again) a cooldown.

<!-- schema -->

**Notes:**
- `attack`, `heal` and the skills that share the `attack` cooldown (`3shot`, `5shot`, `piercingshot`, `fanofknives`, `arcane_needle`) send no `skill_timeout`. `G.skills.attack` has no `cooldown`, so `consume_skill` stops (node/server_functions.js:3456-3462).
- `ms` already includes `penalty`.
- At login, cooldowns that are not over arrive as `eval` hitchhikers with the code `skill_timeout('<skill>',<ms>)`, not as this event (node/server_functions.js:4423-4438).

**Example:**

```js
// sock: a connected AlSocket
// Start the cooldown of `name`: `ms` (it already includes `penalty`).
sock.on("skill_timeout", (data) => {
  console.log(data.name, data.ms, data.penalty);
});
```

```ts
// Start the cooldown of `name`: `ms` (it already includes `penalty`).
interface SkillTimeoutPayload {
  name: string;
  ms: number;
  penalty?: number;
}
sock.on<SkillTimeoutPayload>("skill_timeout", (data) => {
  console.log(data.name, data.ms, data.penalty);
});
```

```python
# Start the cooldown of `name`: `ms` (it already includes `penalty`).
def on_skill_timeout(data: dict) -> None:
    print(data["name"], data["ms"], data.get("penalty"))

sock.on("skill_timeout", on_skill_timeout)
```

```go
// Start the cooldown of `name`: `ms` (it already includes `penalty`).
type SkillTimeoutPayload struct {
	Name    string  `json:"name"`
	Ms      float64 `json:"ms"`
	Penalty float64 `json:"penalty"` // optional
}
sock.On("skill_timeout", func(raw json.RawMessage) {
	var data SkillTimeoutPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name, data.Ms, data.Penalty)
})
```

```csharp
// Start the cooldown of `name`: `ms` (it already includes `penalty`).
sock.On("skill_timeout", data =>
{
    string? name = data.GetProperty("name").GetString();
    double ms = data.GetProperty("ms").GetDouble();
    double? penalty = data.TryGetProperty("penalty", out var penaltyEl) ? penaltyEl.GetDouble() : null;
    Console.WriteLine($"{name} {ms} {penalty}");
});
```

```rust
// Start the cooldown of `name`: `ms` (it already includes `penalty`).
sock.on("skill_timeout", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    let ms = data["ms"].as_f64().unwrap_or(0.0);
    let penalty = data["penalty"].as_f64(); // optional
    println!("{name} {ms} {penalty:?}");
});
```

```java
// Start the cooldown of `name`: `ms` (it already includes `penalty`).
sock.on("skill_timeout", data -> {
    String name = data.path("name").asText();
    double ms = data.path("ms").asDouble();
    JsonNode penalty = data.get("penalty"); // optional: null when absent
    System.out.println(name + " " + ms + " " + penalty);
});
```

**Source:** `node/server_functions.js:3464` (`consume_skill`), `node/server.js:1630`, `node/logic/instance_pause.js:47`.

### `duel`
The server sends it to the challenged player when someone challenges them to a duel.

<!-- schema -->

**Notes:** the challenge also sends the `game_response` codes `challenge_sent` (to the challenger) and `challenge_received` (to the challenged character) (node/server.js:12213-12216).

**Example:**

```js
// sock: a connected AlSocket
// `event` is always "chellenge" (the server spelling).
sock.on("duel", (data) => {
  console.log(data.event, data.name);
});
```

```ts
// `event` is always "chellenge" (the server spelling).
interface DuelPayload {
  event: string;
  name: string;
}
sock.on<DuelPayload>("duel", (data) => {
  console.log(data.event, data.name);
});
```

```python
# `event` is always "chellenge" (the server spelling).
def on_duel(data: dict) -> None:
    print(data["event"], data["name"])

sock.on("duel", on_duel)
```

```go
// `event` is always "chellenge" (the server spelling).
type DuelPayload struct {
	Event string `json:"event"`
	Name  string `json:"name"`
}
sock.On("duel", func(raw json.RawMessage) {
	var data DuelPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Event, data.Name)
})
```

```csharp
// `event` is always "chellenge" (the server spelling).
sock.On("duel", data =>
{
    string? eventName = data.GetProperty("event").GetString();
    string? name = data.GetProperty("name").GetString();
    Console.WriteLine($"{eventName} {name}");
});
```

```rust
// `event` is always "chellenge" (the server spelling).
sock.on("duel", |data| {
    let event_name = data["event"].as_str().unwrap_or_default();
    let name = data["name"].as_str().unwrap_or_default();
    println!("{event_name} {name}");
});
```

```java
// `event` is always "chellenge" (the server spelling).
sock.on("duel", data -> {
    String eventName = data.path("event").asText();
    String name = data.path("name").asText();
    System.out.println(eventName + " " + name);
});
```

**Source:** `node/server.js:12212`.

### `pvp_list`
The reply to `list_pvp`: the last 200 PvP kills on this server.

<!-- schema -->

**Notes:** the list is in memory only. It is empty after a server restart.

**Example:**

```js
// sock: a connected AlSocket
// Newest kills first.
sock.on("pvp_list", (data) => {
  console.log(data.code);
  for (const [attacker, victim] of data.list) console.log(attacker, victim);
});
```

```ts
// Newest kills first.
interface PvPListPayload {
  code?: unknown; // absent when the request had no `code`
  list: [attacker: string, victim: string][];
}
sock.on<PvPListPayload>("pvp_list", (data) => {
  console.log(data.code);
  for (const [attacker, victim] of data.list) console.log(attacker, victim);
});
```

```python
# Newest kills first.
def on_pvp_list(data: dict) -> None:
    print(data.get("code"))  # absent when the request had no `code`
    for kill in data["list"]:
        print(*kill)

sock.on("pvp_list", on_pvp_list)
```

```go
// Newest kills first.
type PvPListPayload struct {
	Code any     `json:"code"`
	List [][]any `json:"list"`
}
sock.On("pvp_list", func(raw json.RawMessage) {
	var data PvPListPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Code)
	for _, kill := range data.List {
		fmt.Println(kill...)
	}
})
```

```csharp
// Newest kills first.
sock.On("pvp_list", data =>
{
    // `code` is absent when the request had no `code`.
    JsonElement? code = data.TryGetProperty("code", out var codeEl) ? codeEl : null;
    Console.WriteLine($"{code}");
    foreach (JsonElement kill in data.GetProperty("list").EnumerateArray())
    {
        string? attacker = kill[0].GetString();
        string? victim = kill[1].GetString();
        Console.WriteLine($"{attacker} {victim}");
    }
});
```

```rust
// Newest kills first.
sock.on("pvp_list", |data| {
    let code = &data["code"];
    println!("{code}");
    for kill in data["list"].as_array().into_iter().flatten() {
        let attacker = &kill[0];
        let victim = &kill[1];
        println!("{attacker} {victim}");
    }
});
```

```java
// Newest kills first.
sock.on("pvp_list", data -> {
    JsonNode code = data.path("code");
    System.out.println(code);
    for (JsonNode kill : data.path("list")) {
        JsonNode attacker = kill.path(0);
        JsonNode victim = kill.path(1);
        System.out.println(attacker + " " + victim);
    }
});
```

**Source:** `node/server.js:12917`.

## Responses and messages

### `game_response`
The reply channel for requests. Most handlers send their result or their failure as `game_response`.

<!-- schema -->

**Notes:**
- Match a reply to its request by `place`. A bare string and some objects have no `place`; see the entry of the request for its exact replies.
- Many handlers send an object only when the request has `request_id`, and a bare string or nothing when it does not.
- Some codes go to another player, not to the requester: `challenge_received`, `challenge_accepted`, `duel_started`, `cx_received`, `item_received`, `gold_received`, `got_picked`, `giveaway_join`. `mail_received` goes to each character of the account.
- `enter` with `place: "dreams"` replies with a `game_response` that has no `response` field: `{place: "enter", success: true, ...}` or `{place: "enter", failed: true, reason}` (`node/logic/generated_maps.js:582-584`).
- Every code has its own entry, with its exact replies. Filter the index to *Response codes*, or search for the code.

**Example:**

```js
// sock: a connected AlSocket
// A bare string is the code itself.
sock.on("game_response", (data) => {
  if (typeof data === "string") {
    console.log(data);
    return;
  }
  console.log(data.response, data.place, data.failed, data.success, data.reason);
});
```

```ts
// A bare string is the code itself.
interface GameResponsePayload {
  response: string;
  place: string;
  failed?: boolean;
  success?: boolean;
  reason?: string;
}
sock.on<string | GameResponsePayload>("game_response", (data) => {
  if (typeof data === "string") {
    console.log(data);
    return;
  }
  console.log(data.response, data.place, data.failed, data.success, data.reason);
});
```

```python
# A bare string is the code itself.
def on_game_response(data: str | dict) -> None:
    if isinstance(data, str):
        print(data)
        return
    print(data["response"], data["place"], data.get("failed"), data.get("success"), data.get("reason"))

sock.on("game_response", on_game_response)
```

```go
// A bare string is the code itself.
type GameResponsePayload struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`  // optional
	Success  bool   `json:"success"` // optional
	Reason   string `json:"reason"`  // optional
}
sock.On("game_response", func(raw json.RawMessage) {
	var code string
	if json.Unmarshal(raw, &code) == nil {
		fmt.Println(code) // a bare string
		return
	}
	var data GameResponsePayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Response, data.Place, data.Failed, data.Success, data.Reason)
})
```

```csharp
// A bare string is the code itself.
sock.On("game_response", data =>
{
    if (data.ValueKind == JsonValueKind.String)
    {
        Console.WriteLine(data.GetString()); // a bare string
        return;
    }
    string? response = data.GetProperty("response").GetString();
    string? place = data.GetProperty("place").GetString();
    bool? failed = data.TryGetProperty("failed", out var failedEl) ? failedEl.GetBoolean() : null;
    bool? success = data.TryGetProperty("success", out var successEl) ? successEl.GetBoolean() : null;
    string? reason = data.TryGetProperty("reason", out var reasonEl) ? reasonEl.GetString() : null;
    Console.WriteLine($"{response} {place} {failed} {success} {reason}");
});
```

```rust
// A bare string is the code itself.
sock.on("game_response", |data| {
    if let Some(code) = data.as_str() {
        println!("{code}"); // a bare string
        return;
    }
    let response = data["response"].as_str().unwrap_or_default();
    let place = data["place"].as_str().unwrap_or_default();
    let failed = data["failed"].as_bool(); // optional
    let success = data["success"].as_bool(); // optional
    let reason = data["reason"].as_str(); // optional
    println!("{response} {place} {failed:?} {success:?} {reason:?}");
});
```

```java
// A bare string is the code itself.
sock.on("game_response", data -> {
    if (data.isTextual()) {
        System.out.println(data.asText()); // a bare string
        return;
    }
    String response = data.path("response").asText();
    String place = data.path("place").asText();
    JsonNode failed = data.get("failed"); // optional: null when absent
    JsonNode success = data.get("success"); // optional: null when absent
    String reason = data.path("reason").asText(null); // optional
    System.out.println(response + " " + place + " " + failed + " " + success + " " + reason);
});
```

**Source:** `node/server_functions.js:3385-3446` (helpers), `node/server.js:10990-10997` (skill replies)

### `game_log`
A line for the log panel of the player: errors without a response code, loot, gold, and so on. About 140 call sites send it.

<!-- schema -->

**Notes:**
- `phrase_args` values are strings at most call sites (`String(...)`), but some pass numbers (for example `item_message` passes `quantity` as a number, node/server_functions.js:4586).
- The `duel` handler sends its failures as `game_log` when the request has no `request_id`, and as `game_response` when it has one (node/server.js:12193-12196).

**Example:**

```js
// sock: a connected AlSocket
// Usually a localized object; sometimes a plain string.
sock.on("game_log", (data) => {
  if (typeof data === "string") {
    console.log(data);
    return;
  }
  console.log(data.message, data.color);
});
```

```ts
// Usually a localized object; sometimes a plain string.
interface GameLogPayload {
  message: string;
  color?: string;
}
sock.on<string | GameLogPayload>("game_log", (data) => {
  if (typeof data === "string") {
    console.log(data);
    return;
  }
  console.log(data.message, data.color);
});
```

```python
# Usually a localized object; sometimes a plain string.
def on_game_log(data: str | dict) -> None:
    if isinstance(data, str):
        print(data)
        return
    print(data["message"], data.get("color"))

sock.on("game_log", on_game_log)
```

```go
// Usually a localized object; sometimes a plain string.
type GameLogPayload struct {
	Message string `json:"message"`
	Color   string `json:"color"` // optional
}
sock.On("game_log", func(raw json.RawMessage) {
	var code string
	if json.Unmarshal(raw, &code) == nil {
		fmt.Println(code) // a bare string
		return
	}
	var data GameLogPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Message, data.Color)
})
```

```csharp
// Usually a localized object; sometimes a plain string.
sock.On("game_log", data =>
{
    if (data.ValueKind == JsonValueKind.String)
    {
        Console.WriteLine(data.GetString()); // a bare string
        return;
    }
    string? message = data.GetProperty("message").GetString();
    string? color = data.TryGetProperty("color", out var colorEl) ? colorEl.GetString() : null;
    Console.WriteLine($"{message} {color}");
});
```

```rust
// Usually a localized object; sometimes a plain string.
sock.on("game_log", |data| {
    if let Some(code) = data.as_str() {
        println!("{code}"); // a bare string
        return;
    }
    let message = data["message"].as_str().unwrap_or_default();
    let color = data["color"].as_str(); // optional
    println!("{message} {color:?}");
});
```

```java
// Usually a localized object; sometimes a plain string.
sock.on("game_log", data -> {
    if (data.isTextual()) {
        System.out.println(data.asText()); // a bare string
        return;
    }
    String message = data.path("message").asText();
    String color = data.path("color").asText(null); // optional
    System.out.println(message + " " + color);
});
```

**Source:** `node/server.js:1353`, `node/logic/tavern.js:114` (examples).

### `game_error`
An error to show clearly.

<!-- schema -->

**Notes:** a request with a `null` payload makes most handlers throw, so it gets `"ERROR!"` (see [Every request](#guide-every-request)).

**Example:**

```js
// sock: a connected AlSocket
// A plain string, or a localized object.
sock.on("game_error", (data) => {
  if (typeof data === "string") {
    console.log(data);
    return;
  }
  console.log(data.message, data.reason);
});
```

```ts
// A plain string, or a localized object.
interface GameErrorPayload {
  message: string;
  reason?: string;
}
sock.on<string | GameErrorPayload>("game_error", (data) => {
  if (typeof data === "string") {
    console.log(data);
    return;
  }
  console.log(data.message, data.reason);
});
```

```python
# A plain string, or a localized object.
def on_game_error(data: str | dict) -> None:
    if isinstance(data, str):
        print(data)
        return
    print(data["message"], data.get("reason"))

sock.on("game_error", on_game_error)
```

```go
// A plain string, or a localized object.
type GameErrorPayload struct {
	Message string `json:"message"`
	Reason  string `json:"reason"` // optional
}
sock.On("game_error", func(raw json.RawMessage) {
	var code string
	if json.Unmarshal(raw, &code) == nil {
		fmt.Println(code) // a bare string
		return
	}
	var data GameErrorPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Message, data.Reason)
})
```

```csharp
// A plain string, or a localized object.
sock.On("game_error", data =>
{
    if (data.ValueKind == JsonValueKind.String)
    {
        Console.WriteLine(data.GetString()); // a bare string
        return;
    }
    string? message = data.GetProperty("message").GetString();
    string? reason = data.TryGetProperty("reason", out var reasonEl) ? reasonEl.GetString() : null;
    Console.WriteLine($"{message} {reason}");
});
```

```rust
// A plain string, or a localized object.
sock.on("game_error", |data| {
    if let Some(code) = data.as_str() {
        println!("{code}"); // a bare string
        return;
    }
    let message = data["message"].as_str().unwrap_or_default();
    let reason = data["reason"].as_str(); // optional
    println!("{message} {reason:?}");
});
```

```java
// A plain string, or a localized object.
sock.on("game_error", data -> {
    if (data.isTextual()) {
        System.out.println(data.asText()); // a bare string
        return;
    }
    String message = data.path("message").asText();
    String reason = data.path("reason").asText(null); // optional
    System.out.println(message + " " + reason);
});
```

**Source:** `node/server.js:4964` (socket wrapper), `node/server.js:11587-11975` (`auth`).

### `disappearing_text`
Floating text over an entity or a point (damage numbers, `+gold`, `NO HITS`, and so on).

<!-- schema -->

**Notes:**
- Most helper calls set `xy`. So a client gets the texts of all entities near it, not only the texts of its own character.
- The helper has a `party` option (`party_emit`), but no call site uses it (node/server_functions.js:3992-3993).

**Example:**

```js
// sock: a connected AlSocket
// Floating text at `x`, `y`.
sock.on("disappearing_text", (data) => {
  console.log(data.message, data.x, data.y, data.id);
});
```

```ts
// Floating text at `x`, `y`.
interface DisappearingTextPayload {
  message: string | number; // a number only for a potion that takes HP
  x: number;
  y: number;
  id?: string;
}
sock.on<DisappearingTextPayload>("disappearing_text", (data) => {
  console.log(data.message, data.x, data.y, data.id);
});
```

```python
# Floating text at `x`, `y`.
def on_disappearing_text(data: dict) -> None:
    print(data["message"], data["x"], data["y"], data.get("id"))

sock.on("disappearing_text", on_disappearing_text)
```

```go
// Floating text at `x`, `y`.
type DisappearingTextPayload struct {
	Message any     `json:"message"` // a string, or a number for a potion that takes HP
	X       float64 `json:"x"`
	Y       float64 `json:"y"`
	ID      string  `json:"id"` // optional
}
sock.On("disappearing_text", func(raw json.RawMessage) {
	var data DisappearingTextPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Message, data.X, data.Y, data.ID)
})
```

```csharp
// Floating text at `x`, `y`.
sock.On("disappearing_text", data =>
{
    // ToString() works for a string and for a number (a potion that takes HP).
    string message = data.GetProperty("message").ToString();
    double x = data.GetProperty("x").GetDouble();
    double y = data.GetProperty("y").GetDouble();
    string? id = data.TryGetProperty("id", out var idEl) ? idEl.GetString() : null;
    Console.WriteLine($"{message} {x} {y} {id}");
});
```

```rust
// Floating text at `x`, `y`.
sock.on("disappearing_text", |data| {
    // A string, or a number for a potion that takes HP.
    let message = match &data["message"] {
        Value::String(text) => text.clone(),
        other => other.to_string(),
    };
    let x = data["x"].as_f64().unwrap_or(0.0);
    let y = data["y"].as_f64().unwrap_or(0.0);
    let id = data["id"].as_str(); // optional
    println!("{message} {x} {y} {id:?}");
});
```

```java
// Floating text at `x`, `y`.
sock.on("disappearing_text", data -> {
    String message = data.path("message").asText(); // also works for a number
    double x = data.path("x").asDouble();
    double y = data.path("y").asDouble();
    String id = data.path("id").asText(null); // optional
    System.out.println(message + " " + x + " " + y + " " + id);
});
```

**Source:** `node/server_functions.js:3956-3996` (`disappearing_text` helper), `node/server.js:3059`, `node/server.js:11382`.

### `server_message`
A server-wide announcement line (level ups, rare finds, high upgrades, big chest loot, events that start or end).

<!-- schema -->

**Notes:**
- A message from another server has `sname`, and its `message` has no server name. `broadcast` adds `" [<sname>]"` to `message` only after it sends the event, for the Discord copy and the log (node/server_functions.js:3496-3500).
- On hardcore servers, `instance_emit` sends to everyone, so PvP kill lines go to the whole server (node/server_functions.js:3542-3544).

**Example:**

```js
// sock: a connected AlSocket
// A server-wide announcement.
sock.on("server_message", (data) => {
  console.log(data.message, data.color, data.type, data.name);
});
```

```ts
// A server-wide announcement.
interface ServerMessagePayload {
  message: string;
  color: string;
  type?: string;
  name?: string;
}
sock.on<ServerMessagePayload>("server_message", (data) => {
  console.log(data.message, data.color, data.type, data.name);
});
```

```python
# A server-wide announcement.
def on_server_message(data: dict) -> None:
    print(data["message"], data["color"], data.get("type"), data.get("name"))

sock.on("server_message", on_server_message)
```

```go
// A server-wide announcement.
type ServerMessagePayload struct {
	Message string `json:"message"`
	Color   string `json:"color"`
	Type    string `json:"type"` // optional
	Name    string `json:"name"` // optional
}
sock.On("server_message", func(raw json.RawMessage) {
	var data ServerMessagePayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Message, data.Color, data.Type, data.Name)
})
```

```csharp
// A server-wide announcement.
sock.On("server_message", data =>
{
    string? message = data.GetProperty("message").GetString();
    string? color = data.GetProperty("color").GetString();
    string? typeName = data.TryGetProperty("type", out var typeNameEl) ? typeNameEl.GetString() : null;
    string? name = data.TryGetProperty("name", out var nameEl) ? nameEl.GetString() : null;
    Console.WriteLine($"{message} {color} {typeName} {name}");
});
```

```rust
// A server-wide announcement.
sock.on("server_message", |data| {
    let message = data["message"].as_str().unwrap_or_default();
    let color = data["color"].as_str().unwrap_or_default();
    let type_name = data["type"].as_str(); // optional
    let name = data["name"].as_str(); // optional
    println!("{message} {color} {type_name:?} {name:?}");
});
```

```java
// A server-wide announcement.
sock.on("server_message", data -> {
    String message = data.path("message").asText();
    String color = data.path("color").asText();
    String typeName = data.path("type").asText(null); // optional
    String name = data.path("name").asText(null); // optional
    System.out.println(message + " " + color + " " + typeName + " " + name);
});
```

**Source:** `node/server.js:1326`, `node/server.js:1335`, `node/server_functions.js:4576` (`item_message`).

### `notice`
A system notice for everyone (live reload failure, event monsters, Goo Brawl, admin notice).

<!-- schema -->

**Notes:** the payload has no `color`. `broadcast` sets `data.color = "orange"` only after it sends the event, for the log (node/server_functions.js:3496-3503).

**Example:**

```js
// sock: a connected AlSocket
// A system notice for everyone.
sock.on("notice", (data) => {
  console.log(data.message);
});
```

```ts
// A system notice for everyone.
interface NoticePayload {
  message: string;
}
sock.on<NoticePayload>("notice", (data) => {
  console.log(data.message);
});
```

```python
# A system notice for everyone.
def on_notice(data: dict) -> None:
    print(data["message"])

sock.on("notice", on_notice)
```

```go
// A system notice for everyone.
type NoticePayload struct {
	Message string `json:"message"`
}
sock.On("notice", func(raw json.RawMessage) {
	var data NoticePayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Message)
})
```

```csharp
// A system notice for everyone.
sock.On("notice", data =>
{
    string? message = data.GetProperty("message").GetString();
    Console.WriteLine($"{message}");
});
```

```rust
// A system notice for everyone.
sock.on("notice", |data| {
    let message = data["message"].as_str().unwrap_or_default();
    println!("{message}");
});
```

```java
// A system notice for everyone.
sock.on("notice", data -> {
    String message = data.path("message").asText();
    System.out.println(message);
});
```

**Source:** `node/server.js:736`, `node/server.js:13165`, `node/server_functions.js:2557`.

### `ui`
A visual event about an entity: level up, skill animations, NPC trades, sends, resists, tavern games and so on. The official client uses it for effects and log lines.

<!-- schema -->

**Notes:**

- Each `type` value belongs to exactly one form, so a client can switch on `type`. Skill forms use the skill name as `type`, sometimes with a suffix (`_fail`, `_start`, `_none`, `_resist`).
- `xy_emit` centers on one entity, so only clients that see that entity get the event. `-$`, `+$`, `+$p` and `+$f` center on the NPC. `+$$` from `trade_sell` centers on the buyer, and from `trade_buy` on the seller. `mlevel`, `disengage` and `<condition>_resist` center on the entity in `id`.
- `-$` and `+$`: a character with `computer` and no NPC in range uses the first merchant of `main` (node/server.js:8072-8074, 8431-8433). Then `id` is that NPC, and only clients near that NPC on `main` get the event.
- `darkblessing` and `warcry` have only `type` (node/server.js:10506). The payload does not tell who used the skill. A client can only guess from the characters in view.
- Server bug: `+$$` from `trade_buy` sends `num: data.num`, the `num` of the request (node/server.js:9054). The handler never reads `data.num`, so `num` is usually absent. It is not the slot that got the item.
- `mheal` never arrives as its own socket event. It is a `["ui", {...}]` pair in the `events` of a monster in `entities` (node/server.js:1069-1071, 14106, 14121). See Monster events in Delivery helpers.

**Example:**

```js
// sock: a connected AlSocket
// The other fields depend on `type`.
sock.on("ui", (data) => {
  switch (data.type) {
    case "level_up":
      console.log(data.name);
      break;
    case "+$$":
      console.log(data.seller, data.buyer, data.item);
      break;
    case "fishing_none":
      console.log(data.name);
      break;
    default:
      console.log(data.type);
  }
});
```

```ts
// The other fields depend on `type`. Three of the forms:
interface UiLevelUp { type: "level_up"; name: string }
interface UiTrade { type: "+$$"; seller: string; buyer: string; item: { name: string; q?: number; price?: number }; slot: string }
interface UiGatherNone { type: "fishing_none" | "mining_none"; name: string; cevent: true }
sock.on<{ type: string }>("ui", (data) => {
  switch (data.type) {
    case "level_up":
      console.log((data as UiLevelUp).name);
      break;
    case "+$$": {
      const t = data as UiTrade;
      console.log(t.seller, t.buyer, t.item);
      break;
    }
    case "fishing_none":
      console.log((data as UiGatherNone).name);
      break;
    default:
      console.log(data.type);
  }
});
```

```python
# The other fields depend on `type`.
def on_ui(data: dict) -> None:
    match data["type"]:
        case "level_up":
            print(data["name"])
        case "+$$":
            print(data["seller"], data["buyer"], data["item"])
        case "fishing_none":
            print(data["name"])
        case _:
            print(data["type"])

sock.on("ui", on_ui)
```

```go
// The other fields depend on `type`.
type UiPayload struct {
	Type   string         `json:"type"`
	Name   string         `json:"name"`
	Seller string         `json:"seller"`
	Buyer  string         `json:"buyer"`
	Item   map[string]any `json:"item"`
}
sock.On("ui", func(raw json.RawMessage) {
	var data UiPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	switch data.Type {
	case "level_up":
		fmt.Println(data.Name)
	case "+$$":
		fmt.Println(data.Seller, data.Buyer, data.Item)
	case "fishing_none":
		fmt.Println(data.Name)
	default:
		fmt.Println(data.Type)
	}
})
```

```csharp
// The other fields depend on `type`.
sock.On("ui", data =>
{
    string? typeName = data.GetProperty("type").GetString();
    switch (typeName)
    {
        case "level_up":
        {
            string? name = data.GetProperty("name").GetString();
            Console.WriteLine($"{name}");
            break;
        }
        case "+$$":
        {
            string? seller = data.GetProperty("seller").GetString();
            string? buyer = data.GetProperty("buyer").GetString();
            JsonElement item = data.GetProperty("item");
            Console.WriteLine($"{seller} {buyer} {item}");
            break;
        }
        case "fishing_none":
        {
            string? name = data.GetProperty("name").GetString();
            Console.WriteLine($"{name}");
            break;
        }
        default:
            Console.WriteLine(typeName);
            break;
    }
});
```

```rust
// The other fields depend on `type`.
sock.on("ui", |data| {
    match data["type"].as_str().unwrap_or_default() {
        "level_up" => {
            let name = data["name"].as_str().unwrap_or_default();
            println!("{name}");
        }
        "+$$" => {
            let seller = data["seller"].as_str().unwrap_or_default();
            let buyer = data["buyer"].as_str().unwrap_or_default();
            let item = &data["item"];
            println!("{seller} {buyer} {item}");
        }
        "fishing_none" => {
            let name = data["name"].as_str().unwrap_or_default();
            println!("{name}");
        }
        other => println!("{other}"),
    }
});
```

```java
// The other fields depend on `type`.
sock.on("ui", data -> {
    String typeName = data.path("type").asText();
    switch (typeName) {
        case "level_up" -> {
            String name = data.path("name").asText();
            System.out.println(name);
        }
        case "+$$" -> {
            String seller = data.path("seller").asText();
            String buyer = data.path("buyer").asText();
            JsonNode item = data.path("item");
            System.out.println(seller + " " + buyer + " " + item);
        }
        case "fishing_none" -> {
            String name = data.path("name").asText();
            System.out.println(name);
        }
        default -> System.out.println(typeName);
    }
});
```

**Source:** `node/server.js:1343`, `node/server.js:10154-10163`, `node/server.js:15062-15067`, `node/logic/tavern_slots.js:67`, `node/logic/tavern_wheel.js:48`, `node/logic/cave_of_many_dreams.js:16`.

### `eval`
Asks the client to run a code snippet (UI timers and visual effects).

<!-- schema -->

**Notes:**
- A client that runs `eval` code runs whatever the server sends. The function name and the arguments are readable from the text.
- The cooldowns at login arrive only as `skill_timeout('<skill>',<ms>)` code, not as `skill_timeout` events.

**Example:**

```js
// sock: a connected AlSocket
// Code text, for example "pot_timeout(4000)".
sock.on("eval", (data) => {
  if (typeof data === "string") {
    console.log(data);
    return;
  }
  console.log(data.code);
});
```

```ts
// Code text, for example "pot_timeout(4000)".
interface EvalPayload {
  code: string;
}
sock.on<string | EvalPayload>("eval", (data) => {
  if (typeof data === "string") {
    console.log(data);
    return;
  }
  console.log(data.code);
});
```

```python
# Code text, for example "pot_timeout(4000)".
def on_eval(data: str | dict) -> None:
    if isinstance(data, str):
        print(data)
        return
    print(data["code"])

sock.on("eval", on_eval)
```

```go
// Code text, for example "pot_timeout(4000)".
type EvalPayload struct {
	Code string `json:"code"`
}
sock.On("eval", func(raw json.RawMessage) {
	var code string
	if json.Unmarshal(raw, &code) == nil {
		fmt.Println(code) // a bare string
		return
	}
	var data EvalPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Code)
})
```

```csharp
// Code text, for example "pot_timeout(4000)".
sock.On("eval", data =>
{
    if (data.ValueKind == JsonValueKind.String)
    {
        Console.WriteLine(data.GetString()); // a bare string
        return;
    }
    string? code = data.GetProperty("code").GetString();
    Console.WriteLine($"{code}");
});
```

```rust
// Code text, for example "pot_timeout(4000)".
sock.on("eval", |data| {
    if let Some(code) = data.as_str() {
        println!("{code}"); // a bare string
        return;
    }
    let code = data["code"].as_str().unwrap_or_default();
    println!("{code}");
});
```

```java
// Code text, for example "pot_timeout(4000)".
sock.on("eval", data -> {
    if (data.isTextual()) {
        System.out.println(data.asText()); // a bare string
        return;
    }
    String code = data.path("code").asText();
    System.out.println(code);
});
```

**Source:** `node/server.js:7878`, `node/server.js:9537`, `node/server.js:16981`.

### `simple_eval`
The reply to the admin-only `render` request (needs `data.pass == keys.ACCESS_MASTER`).

<!-- schema -->

**Notes:** `render` also sends `player` with `reopen` after the reply, and throws there when the socket has no character (node/server.js:13196).

**Example:**

```js
// sock: a connected AlSocket
// Admin only: the reply to render.
sock.on("simple_eval", (data) => {
  console.log(data.code);
});
```

```ts
// Admin only: the reply to render.
interface SimpleEvalPayload {
  code: string;
}
sock.on<SimpleEvalPayload>("simple_eval", (data) => {
  console.log(data.code);
});
```

```python
# Admin only: the reply to render.
def on_simple_eval(data: dict) -> None:
    print(data["code"])

sock.on("simple_eval", on_simple_eval)
```

```go
// Admin only: the reply to render.
type SimpleEvalPayload struct {
	Code string `json:"code"`
}
sock.On("simple_eval", func(raw json.RawMessage) {
	var data SimpleEvalPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Code)
})
```

```csharp
// Admin only: the reply to render.
sock.On("simple_eval", data =>
{
    string? code = data.GetProperty("code").GetString();
    Console.WriteLine($"{code}");
});
```

```rust
// Admin only: the reply to render.
sock.on("simple_eval", |data| {
    let code = data["code"].as_str().unwrap_or_default();
    println!("{code}");
});
```

```java
// Admin only: the reply to render.
sock.on("simple_eval", data -> {
    String code = data.path("code").asText();
    System.out.println(code);
});
```

**Source:** `node/server.js:13182-13190`.

### `code_eval`
Sends an `o:command` from an observer socket to the socket of the observed player, so the player's code can react.

<!-- schema -->

**Notes:** the payload is exactly what the observer sent in [`o:command`](#send-o-command). The official client runs `data.code || data` as code (js/game.js:3205-3209).

**Example:**

```js
// sock: a connected AlSocket
// What the observer sent in o:command.
sock.on("code_eval", (data) => {
  console.log(data);
});
```

```ts
// What the observer sent in o:command.
sock.on("code_eval", (data) => {
  console.log(data);
});
```

```python
# What the observer sent in o:command.
def on_code_eval(data: object) -> None:
    print(data)

sock.on("code_eval", on_code_eval)
```

```go
// What the observer sent in o:command.
sock.On("code_eval", func(raw json.RawMessage) {
	fmt.Println(string(raw))
})
```

```csharp
// What the observer sent in o:command.
sock.On("code_eval", data =>
{
    Console.WriteLine(data.GetRawText());
});
```

```rust
// What the observer sent in o:command.
sock.on("code_eval", |data| {
    println!("{data}");
});
```

```java
// What the observer sent in o:command.
sock.on("code_eval", data -> {
    System.out.println(data);
});
```

**Source:** `node/server.js:5075`.

## Social

### `party_update`
The party changed: someone joined or left, or the info of a member changed.

<!-- schema -->

**Notes:**
- Read every form the same way: if `list` is absent or `false`, you are not in a party. Then replace your list and the member info.
- The party name is the name of the leader, the first name in `list`. When the leader leaves, the next member becomes the leader, so the party name changes.
- The member that leaves gets only the empty object from the `party` handler. On `disconnect` it gets nothing.
- `party` leaves out a member that is not on this server now. `send_party_update` also removes that member from the party (`node/server.js:1219-1222`).

**Example:**

```js
// sock: a connected AlSocket
// `list` is absent or false when you are not in a party.
sock.on("party_update", (data) => {
  if (data.message) console.log(data.message);
  for (const name of data.list || []) {
    const m = data.party[name];
    if (m) console.log(name, m.level, m.type, m.map, m.share);
  }
});
```

```ts
// `list` is absent or false when you are not in a party.
interface PartyUpdateMember {
  level: number;
  type: string;
  map: string;
  share: number;
  rip?: true | string;
}
interface PartyUpdatePayload {
  list?: string[] | false;
  party?: Record<string, PartyUpdateMember>;
  message?: string;
  leave?: 1;
}
sock.on<PartyUpdatePayload>("party_update", (data) => {
  if (data.message) console.log(data.message);
  for (const name of data.list || []) {
    const m = data.party?.[name];
    if (m) console.log(name, m.level, m.type, m.map, m.share);
  }
});
```

```python
# `list` is absent or false when you are not in a party.
def on_party_update(data: dict) -> None:
    if "message" in data:
        print(data["message"])
    party = data.get("party") or {}
    for name in data.get("list") or []:
        m = party.get(name)
        if m:
            print(name, m["level"], m["type"], m["map"], m["share"])

sock.on("party_update", on_party_update)
```

```go
// `list` is absent or false when you are not in a party.
type PartyUpdateMember struct {
	Level int     `json:"level"`
	Type  string  `json:"type"`
	Map   string  `json:"map"`
	Share float64 `json:"share"`
}
type PartyUpdatePayload struct {
	List    json.RawMessage              `json:"list"`    // optional: an array or false
	Party   map[string]PartyUpdateMember `json:"party"`   // optional
	Message string                       `json:"message"` // optional
}
sock.On("party_update", func(raw json.RawMessage) {
	var data PartyUpdatePayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	if data.Message != "" {
		fmt.Println(data.Message)
	}
	var list []string
	_ = json.Unmarshal(data.List, &list) // false or absent: list stays empty
	for _, name := range list {
		if m, ok := data.Party[name]; ok {
			fmt.Println(name, m.Level, m.Type, m.Map, m.Share)
		}
	}
})
```

```csharp
// `list` is absent or false when you are not in a party.
sock.On("party_update", data =>
{
    if (data.TryGetProperty("message", out var message)) Console.WriteLine(message.GetString());
    if (!data.TryGetProperty("list", out var list) || list.ValueKind != JsonValueKind.Array) return;
    JsonElement party = data.GetProperty("party");
    foreach (JsonElement n in list.EnumerateArray())
    {
        string name = n.GetString() ?? "";
        if (!party.TryGetProperty(name, out var m)) continue;
        Console.WriteLine($"{name} {m.GetProperty("level").GetInt32()} {m.GetProperty("type").GetString()} {m.GetProperty("map").GetString()} {m.GetProperty("share").GetDouble()}");
    }
});
```

```rust
// `list` is absent or false when you are not in a party.
sock.on("party_update", |data| {
    if let Some(message) = data["message"].as_str() {
        println!("{message}");
    }
    let Some(list) = data["list"].as_array() else { return };
    for name in list.iter().filter_map(|n| n.as_str()) {
        let m = &data["party"][name];
        if m.is_object() {
            println!("{name} {} {} {} {}", m["level"], m["type"], m["map"], m["share"]);
        }
    }
});
```

```java
// `list` is absent or false when you are not in a party.
sock.on("party_update", data -> {
    if (data.has("message")) System.out.println(data.get("message").asText());
    JsonNode list = data.get("list");
    if (list == null || !list.isArray()) return;
    for (JsonNode n : list) {
        JsonNode m = data.path("party").path(n.asText());
        if (m.isObject()) System.out.println(n.asText() + " " + m.get("level").asInt() + " " + m.get("type").asText() + " " + m.get("map").asText() + " " + m.get("share").asDouble());
    }
});
```

**Source:** `node/server.js:1137-1226`, `node/server.js:12441-12453`, `node/server_functions.js:3647-3666`.

### `invite`
Someone invited this player to their party.

<!-- schema -->

**Notes:**
- An invite does not expire with time. It stays valid until you accept it (`node/server.js:12418`, `:12429`).
- If you accept while you are in another party, you leave that party first.

**Example:**

```js
// sock: a connected AlSocket
// To accept: party with event "accept" and this name.
sock.on("invite", (data) => {
  console.log(data.name);
});
```

```ts
// To accept: party with event "accept" and this name.
interface InvitePayload {
  name: string;
}
sock.on<InvitePayload>("invite", (data) => {
  console.log(data.name);
});
```

```python
# To accept: party with event "accept" and this name.
def on_invite(data: dict) -> None:
    print(data["name"])

sock.on("invite", on_invite)
```

```go
// To accept: party with event "accept" and this name.
type InvitePayload struct {
	Name string `json:"name"`
}
sock.On("invite", func(raw json.RawMessage) {
	var data InvitePayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name)
})
```

```csharp
// To accept: party with event "accept" and this name.
sock.On("invite", data =>
{
    string? name = data.GetProperty("name").GetString();
    Console.WriteLine($"{name}");
});
```

```rust
// To accept: party with event "accept" and this name.
sock.on("invite", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    println!("{name}");
});
```

```java
// To accept: party with event "accept" and this name.
sock.on("invite", data -> {
    String name = data.path("name").asText();
    System.out.println(name);
});
```

**Source:** `node/server.js:12375`.

### `request`
Someone asked to join the party of this player.

<!-- schema -->

**Notes:**
- The request ends when the other character joins or starts a party. It does not expire with time (`node/server.js:12434`, `:12454-12455`, `:12502-12503`).
- If the other character is in a party when you accept, it leaves that party first.

**Example:**

```js
// sock: a connected AlSocket
// To accept: party with event "raccept" and this name.
sock.on("request", (data) => {
  console.log(data.name);
});
```

```ts
// To accept: party with event "raccept" and this name.
interface RequestPayload {
  name: string;
}
sock.on<RequestPayload>("request", (data) => {
  console.log(data.name);
});
```

```python
# To accept: party with event "raccept" and this name.
def on_request(data: dict) -> None:
    print(data["name"])

sock.on("request", on_request)
```

```go
// To accept: party with event "raccept" and this name.
type RequestPayload struct {
	Name string `json:"name"`
}
sock.On("request", func(raw json.RawMessage) {
	var data RequestPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name)
})
```

```csharp
// To accept: party with event "raccept" and this name.
sock.On("request", data =>
{
    string? name = data.GetProperty("name").GetString();
    Console.WriteLine($"{name}");
});
```

```rust
// To accept: party with event "raccept" and this name.
sock.on("request", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    println!("{name}");
});
```

```java
// To accept: party with event "raccept" and this name.
sock.on("request", data -> {
    String name = data.path("name").asText();
    System.out.println(name);
});
```

**Source:** `node/server.js:12395`.

### `chat_log`
Public chat, or an NPC or monster that speaks.

<!-- schema -->

**Notes:**
- Use `p` to tell player chat from NPC lines. An NPC line has no `p`.
- The server sends player chat to all sockets before its spam check. The spam check only stops the Discord relay and the saved chat history (`node/logic/chat.js:115-117`).
- Player chat reaches only this server. Other servers do not get it.

**Example:**

```js
// sock: a connected AlSocket
// `p` is true for player chat.
sock.on("chat_log", (data) => {
  console.log(data.owner, data.message, data.id, data.p);
});
```

```ts
// `p` is true for player chat.
interface ChatLogPayload {
  owner: string;
  message: string;
  id: string;
  p?: boolean;
}
sock.on<ChatLogPayload>("chat_log", (data) => {
  console.log(data.owner, data.message, data.id, data.p);
});
```

```python
# `p` is true for player chat.
def on_chat_log(data: dict) -> None:
    print(data["owner"], data["message"], data["id"], data.get("p"))

sock.on("chat_log", on_chat_log)
```

```go
// `p` is true for player chat.
type ChatLogPayload struct {
	Owner   string `json:"owner"`
	Message string `json:"message"`
	ID      string `json:"id"`
	P       bool   `json:"p"` // optional
}
sock.On("chat_log", func(raw json.RawMessage) {
	var data ChatLogPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Owner, data.Message, data.ID, data.P)
})
```

```csharp
// `p` is true for player chat.
sock.On("chat_log", data =>
{
    string? owner = data.GetProperty("owner").GetString();
    string? message = data.GetProperty("message").GetString();
    string? id = data.GetProperty("id").GetString();
    bool? p = data.TryGetProperty("p", out var pEl) ? pEl.GetBoolean() : null;
    Console.WriteLine($"{owner} {message} {id} {p}");
});
```

```rust
// `p` is true for player chat.
sock.on("chat_log", |data| {
    let owner = data["owner"].as_str().unwrap_or_default();
    let message = data["message"].as_str().unwrap_or_default();
    let id = data["id"].as_str().unwrap_or_default();
    let p = data["p"].as_bool(); // optional
    println!("{owner} {message} {id} {p:?}");
});
```

```java
// `p` is true for player chat.
sock.on("chat_log", data -> {
    String owner = data.path("owner").asText();
    String message = data.path("message").asText();
    String id = data.path("id").asText();
    JsonNode p = data.get("p"); // optional: null when absent
    System.out.println(owner + " " + message + " " + id + " " + p);
});
```

**Source:** `node/logic/chat.js:115`, `node/server.js:2921`, `node/server_functions.js:2755`.

### `game_chat`
A system line for the chat panel (GM mute feedback, duel results).

<!-- schema -->

**Notes:**
- The live server sends only objects. The official client also accepts a bare string and a `sound` field (`js/game.js:1924-1932`), but no server code sends them.
- At the end of a duel, each duel player and each character in the instance gets the winner line once. Characters near the winning duel player then also get the defeat line.

**Example:**

```js
// sock: a connected AlSocket
// A system line for the chat panel.
sock.on("game_chat", (data) => {
  console.log(data.message, data.color);
});
```

```ts
// A system line for the chat panel.
interface GameChatPayload {
  message: string;
  color?: string;
}
sock.on<GameChatPayload>("game_chat", (data) => {
  console.log(data.message, data.color);
});
```

```python
# A system line for the chat panel.
def on_game_chat(data: dict) -> None:
    print(data["message"], data.get("color"))

sock.on("game_chat", on_game_chat)
```

```go
// A system line for the chat panel.
type GameChatPayload struct {
	Message string `json:"message"`
	Color   string `json:"color"` // optional
}
sock.On("game_chat", func(raw json.RawMessage) {
	var data GameChatPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Message, data.Color)
})
```

```csharp
// A system line for the chat panel.
sock.On("game_chat", data =>
{
    string? message = data.GetProperty("message").GetString();
    string? color = data.TryGetProperty("color", out var colorEl) ? colorEl.GetString() : null;
    Console.WriteLine($"{message} {color}");
});
```

```rust
// A system line for the chat panel.
sock.on("game_chat", |data| {
    let message = data["message"].as_str().unwrap_or_default();
    let color = data["color"].as_str(); // optional
    println!("{message} {color:?}");
});
```

```java
// A system line for the chat panel.
sock.on("game_chat", data -> {
    String message = data.path("message").asText();
    String color = data.path("color").asText(null); // optional
    System.out.println(message + " " + color);
});
```

**Source:** `node/server.js:5299`, `node/server.js:12351`, `node/server_functions.js:2965`.

### `pm`
A private message. The sender gets a copy too.

<!-- schema -->

**Notes:**
- Use `to` to tell your copy from a message to you. Only your copy and the failure notice have `to`.
- A failed delivery arrives as a second `pm` after your copy. Its `message` is the localized `(FAILED)` text, not your text.
- If the recipient exists but is offline, you get only your copy. The server saves the message in the chat history of both accounts (`node/logic/chat.js:112-113`).

**Example:**

```js
// sock: a connected AlSocket
// `to` is only in the copy of the sender.
sock.on("pm", (data) => {
  console.log(data.owner, data.message, data.to, data.xserver);
});
```

```ts
// `to` is only in the copy of the sender.
interface PmPayload {
  owner: string;
  message: string;
  to?: string;
  xserver?: boolean;
}
sock.on<PmPayload>("pm", (data) => {
  console.log(data.owner, data.message, data.to, data.xserver);
});
```

```python
# `to` is only in the copy of the sender.
def on_pm(data: dict) -> None:
    print(data["owner"], data["message"], data.get("to"), data.get("xserver"))

sock.on("pm", on_pm)
```

```go
// `to` is only in the copy of the sender.
type PmPayload struct {
	Owner   string `json:"owner"`
	Message string `json:"message"`
	To      string `json:"to"`      // optional
	Xserver bool   `json:"xserver"` // optional
}
sock.On("pm", func(raw json.RawMessage) {
	var data PmPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Owner, data.Message, data.To, data.Xserver)
})
```

```csharp
// `to` is only in the copy of the sender.
sock.On("pm", data =>
{
    string? owner = data.GetProperty("owner").GetString();
    string? message = data.GetProperty("message").GetString();
    string? to = data.TryGetProperty("to", out var toEl) ? toEl.GetString() : null;
    bool? xserver = data.TryGetProperty("xserver", out var xserverEl) ? xserverEl.GetBoolean() : null;
    Console.WriteLine($"{owner} {message} {to} {xserver}");
});
```

```rust
// `to` is only in the copy of the sender.
sock.on("pm", |data| {
    let owner = data["owner"].as_str().unwrap_or_default();
    let message = data["message"].as_str().unwrap_or_default();
    let to = data["to"].as_str(); // optional
    let xserver = data["xserver"].as_bool(); // optional
    println!("{owner} {message} {to:?} {xserver:?}");
});
```

```java
// `to` is only in the copy of the sender.
sock.on("pm", data -> {
    String owner = data.path("owner").asText();
    String message = data.path("message").asText();
    String to = data.path("to").asText(null); // optional
    JsonNode xserver = data.get("xserver"); // optional: null when absent
    System.out.println(owner + " " + message + " " + to + " " + xserver);
});
```

**Source:** `node/logic/chat.js:75-113` (`deliver_chat_message`).

### `partym`
A party chat message.

<!-- schema -->

**Example:**

```js
// sock: a connected AlSocket
// A party chat line.
sock.on("partym", (data) => {
  console.log(data.owner, data.message, data.id);
});
```

```ts
// A party chat line.
interface PartymPayload {
  owner: string;
  message: string;
  id: string;
}
sock.on<PartymPayload>("partym", (data) => {
  console.log(data.owner, data.message, data.id);
});
```

```python
# A party chat line.
def on_partym(data: dict) -> None:
    print(data["owner"], data["message"], data["id"])

sock.on("partym", on_partym)
```

```go
// A party chat line.
type PartymPayload struct {
	Owner   string `json:"owner"`
	Message string `json:"message"`
	ID      string `json:"id"`
}
sock.On("partym", func(raw json.RawMessage) {
	var data PartymPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Owner, data.Message, data.ID)
})
```

```csharp
// A party chat line.
sock.On("partym", data =>
{
    string? owner = data.GetProperty("owner").GetString();
    string? message = data.GetProperty("message").GetString();
    string? id = data.GetProperty("id").GetString();
    Console.WriteLine($"{owner} {message} {id}");
});
```

```rust
// A party chat line.
sock.on("partym", |data| {
    let owner = data["owner"].as_str().unwrap_or_default();
    let message = data["message"].as_str().unwrap_or_default();
    let id = data["id"].as_str().unwrap_or_default();
    println!("{owner} {message} {id}");
});
```

```java
// A party chat line.
sock.on("partym", data -> {
    String owner = data.path("owner").asText();
    String message = data.path("message").asText();
    String id = data.path("id").asText();
    System.out.println(owner + " " + message + " " + id);
});
```

**Source:** `node/server.js:5113`.

### `cm`
A code message from another character. The `cm` request lets characters send data to each other.

<!-- schema -->

**Notes:**
- `cm` reaches only characters on the same server. The reply to the sender lists the names that got it (`receivers`).
- A name that appears two times in `to` gets the message two times.

**Example:**

```js
// sock: a connected AlSocket
// `message` can be any JSON value.
sock.on("cm", (data) => {
  console.log(data.name, data.message);
});
```

```ts
// `message` can be any JSON value.
interface CmPayload {
  name: string;
  message: unknown;
}
sock.on<CmPayload>("cm", (data) => {
  console.log(data.name, data.message);
});
```

```python
# `message` can be any JSON value.
def on_cm(data: dict) -> None:
    print(data["name"], data["message"])

sock.on("cm", on_cm)
```

```go
// `message` can be any JSON value.
type CmPayload struct {
	Name    string `json:"name"`
	Message any    `json:"message"`
}
sock.On("cm", func(raw json.RawMessage) {
	var data CmPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name, data.Message)
})
```

```csharp
// `message` can be any JSON value.
sock.On("cm", data =>
{
    string? name = data.GetProperty("name").GetString();
    JsonElement message = data.GetProperty("message");
    Console.WriteLine($"{name} {message}");
});
```

```rust
// `message` can be any JSON value.
sock.on("cm", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    let message = &data["message"];
    println!("{name} {message}");
});
```

```java
// `message` can be any JSON value.
sock.on("cm", data -> {
    String name = data.path("name").asText();
    JsonNode message = data.path("message");
    System.out.println(name + " " + message);
});
```

**Source:** `node/server.js:5086`.

### `friend`
Friend list events.

<!-- schema -->

**Notes:**
- Friends are accounts, not characters. `friends` holds account ids, so compare it with the `owner` of a character.
- `new` and `lost` come from the web server, after the database changes. They can arrive after the `game_response` of your own `accept` or `unfriend`.
- The official client also handles `event: "update"`, but no server code sends it.

**Example:**

```js
// sock: a connected AlSocket
// The other fields depend on `event`.
sock.on("friend", (data) => {
  switch (data.event) {
    case "request":
      console.log(data.name);
      break;
    case "new":
      console.log(data.name, data.friends);
      break;
    case "lost":
      console.log(data.friends);
      break;
    default:
      console.log(data.event);
  }
});
```

```ts
// The other fields depend on `event`.
interface FriendPayload {
  event: string;
  name?: string;
  friends?: unknown[];
}
sock.on<FriendPayload>("friend", (data) => {
  switch (data.event) {
    case "request":
      console.log(data.name);
      break;
    case "new":
      console.log(data.name, data.friends);
      break;
    case "lost":
      console.log(data.friends);
      break;
    default:
      console.log(data.event);
  }
});
```

```python
# The other fields depend on `event`.
def on_friend(data: dict) -> None:
    match data["event"]:
        case "request":
            print(data["name"])
        case "new":
            print(data["name"], data["friends"])
        case "lost":
            print(data["friends"])
        case _:
            print(data["event"])

sock.on("friend", on_friend)
```

```go
// The other fields depend on `event`.
type FriendPayload struct {
	Event   string `json:"event"`
	Name    string `json:"name"`
	Friends []any  `json:"friends"`
}
sock.On("friend", func(raw json.RawMessage) {
	var data FriendPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	switch data.Event {
	case "request":
		fmt.Println(data.Name)
	case "new":
		fmt.Println(data.Name, data.Friends)
	case "lost":
		fmt.Println(data.Friends)
	default:
		fmt.Println(data.Event)
	}
})
```

```csharp
// The other fields depend on `event`.
sock.On("friend", data =>
{
    string? eventName = data.GetProperty("event").GetString();
    switch (eventName)
    {
        case "request":
        {
            string? name = data.GetProperty("name").GetString();
            Console.WriteLine($"{name}");
            break;
        }
        case "new":
        {
            string? name = data.GetProperty("name").GetString();
            JsonElement friends = data.GetProperty("friends");
            Console.WriteLine($"{name} {friends}");
            break;
        }
        case "lost":
        {
            JsonElement friends = data.GetProperty("friends");
            Console.WriteLine($"{friends}");
            break;
        }
        default:
            Console.WriteLine(eventName);
            break;
    }
});
```

```rust
// The other fields depend on `event`.
sock.on("friend", |data| {
    match data["event"].as_str().unwrap_or_default() {
        "request" => {
            let name = data["name"].as_str().unwrap_or_default();
            println!("{name}");
        }
        "new" => {
            let name = data["name"].as_str().unwrap_or_default();
            let friends = &data["friends"];
            println!("{name} {friends}");
        }
        "lost" => {
            let friends = &data["friends"];
            println!("{friends}");
        }
        other => println!("{other}"),
    }
});
```

```java
// The other fields depend on `event`.
sock.on("friend", data -> {
    String eventName = data.path("event").asText();
    switch (eventName) {
        case "request" -> {
            String name = data.path("name").asText();
            System.out.println(name);
        }
        case "new" -> {
            String name = data.path("name").asText();
            JsonNode friends = data.path("friends");
            System.out.println(name + " " + friends);
        }
        case "lost" -> {
            JsonNode friends = data.path("friends");
            System.out.println(friends);
        }
        default -> System.out.println(eventName);
    }
});
```

**Source:** `node/server.js:12042`, `node/server.js:777`, `node/server.js:794`.

### `online`
A friend came online on some server.

<!-- schema -->

**Notes:**
- The login can be on any server. The server of the new character asks each server with online friends to send `online`.
- The server sends no event when a friend goes offline.

**Example:**

```js
// sock: a connected AlSocket
// A friend logged in.
sock.on("online", (data) => {
  console.log(data.name, data.server);
});
```

```ts
// A friend logged in.
interface OnlinePayload {
  name: string;
  server: string;
}
sock.on<OnlinePayload>("online", (data) => {
  console.log(data.name, data.server);
});
```

```python
# A friend logged in.
def on_online(data: dict) -> None:
    print(data["name"], data["server"])

sock.on("online", on_online)
```

```go
// A friend logged in.
type OnlinePayload struct {
	Name   string `json:"name"`
	Server string `json:"server"`
}
sock.On("online", func(raw json.RawMessage) {
	var data OnlinePayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name, data.Server)
})
```

```csharp
// A friend logged in.
sock.On("online", data =>
{
    string? name = data.GetProperty("name").GetString();
    string? server = data.GetProperty("server").GetString();
    Console.WriteLine($"{name} {server}");
});
```

```rust
// A friend logged in.
sock.on("online", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    let server = data["server"].as_str().unwrap_or_default();
    println!("{name} {server}");
});
```

```java
// A friend logged in.
sock.on("online", data -> {
    String name = data.path("name").asText();
    String server = data.path("server").asText();
    System.out.println(name + " " + server);
});
```

**Source:** `node/server_functions.js:457`.

### `magiport`
A mage offers to magiport this player.

<!-- schema -->

**Notes:**
- The answer is [`magiport`](#send-magiport). The offer does not expire with time. It is good for one use (`node/server.js:12553-12554`).
- On a PvP server, the skill sends no offer. It moves the target at once if `is_same` is true (same account, IP, party, team or `coop`), or if the target has no helmet. That path reads an undeclared `ported` (`node/server.js:10818-10821`), so it can throw.

**Example:**

```js
// sock: a connected AlSocket
// To accept: the magiport event with this name.
sock.on("magiport", (data) => {
  console.log(data.name);
});
```

```ts
// To accept: the magiport event with this name.
interface MagiportPayload {
  name: string;
}
sock.on<MagiportPayload>("magiport", (data) => {
  console.log(data.name);
});
```

```python
# To accept: the magiport event with this name.
def on_magiport(data: dict) -> None:
    print(data["name"])

sock.on("magiport", on_magiport)
```

```go
// To accept: the magiport event with this name.
type MagiportPayload struct {
	Name string `json:"name"`
}
sock.On("magiport", func(raw json.RawMessage) {
	var data MagiportPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name)
})
```

```csharp
// To accept: the magiport event with this name.
sock.On("magiport", data =>
{
    string? name = data.GetProperty("name").GetString();
    Console.WriteLine($"{name}");
});
```

```rust
// To accept: the magiport event with this name.
sock.on("magiport", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    println!("{name}");
});
```

```java
// To accept: the magiport event with this name.
sock.on("magiport", data -> {
    String name = data.path("name").asText();
    System.out.println(name);
});
```

**Source:** `node/server.js:10814`.

### `players`
The player list of the server, or the pets of the player.

<!-- schema -->

**Notes:**
- The replies to `players` and `pets` use the same event. If you send both, you cannot tell the replies apart by their name.
- The list has only the characters on this server. On a server that is not PvP, it leaves out characters in PvP areas.
- `afk` is a number here (0 or 1). In `player`, `afk` is a boolean, `"code"` or `"bot"`.

**Example:**

```js
// sock: a connected AlSocket
// The reply to players. The reply to pets has other fields.
sock.on("players", (data) => {
  for (const p of data) console.log(p.name, p.map, p.level, p.type);
});
```

```ts
// The reply to players. The reply to pets has other fields.
interface PlayersEntry {
  name: string;
  map: string;
  level: number;
  type: string;
}
sock.on<PlayersEntry[]>("players", (data) => {
  for (const p of data) console.log(p.name, p.map, p.level, p.type);
});
```

```python
# The reply to players. The reply to pets has other fields.
def on_players(data: list) -> None:
    for p in data:
        print(p["name"], p["map"], p["level"], p["type"])

sock.on("players", on_players)
```

```go
// The reply to players. The reply to pets has other fields.
type PlayersEntry struct {
	Name  string `json:"name"`
	Map   string `json:"map"`
	Level int    `json:"level"`
	Type  string `json:"type"`
}
sock.On("players", func(raw json.RawMessage) {
	var data []PlayersEntry
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	for _, p := range data {
		fmt.Println(p.Name, p.Map, p.Level, p.Type)
	}
})
```

```csharp
// The reply to players. The reply to pets has other fields.
sock.On("players", data =>
{
    foreach (JsonElement p in data.EnumerateArray())
    {
        string? name = p.GetProperty("name").GetString();
        string? map = p.GetProperty("map").GetString();
        int level = p.GetProperty("level").GetInt32();
        string? typeName = p.GetProperty("type").GetString();
        Console.WriteLine($"{name} {map} {level} {typeName}");
    }
});
```

```rust
// The reply to players. The reply to pets has other fields.
sock.on("players", |data| {
    for p in data.as_array().into_iter().flatten() {
        let name = p["name"].as_str().unwrap_or_default();
        let map = p["map"].as_str().unwrap_or_default();
        let level = p["level"].as_i64().unwrap_or(0);
        let type_name = p["type"].as_str().unwrap_or_default();
        println!("{name} {map} {level} {type_name}");
    }
});
```

```java
// The reply to players. The reply to pets has other fields.
sock.on("players", data -> {
    for (JsonNode p : data) {
        String name = p.path("name").asText();
        String map = p.path("map").asText();
        int level = p.path("level").asInt();
        String typeName = p.path("type").asText();
        System.out.println(name + " " + map + " " + level + " " + typeName);
    }
});
```

**Source:** `node/server.js:12953`, `node/server.js:12964`.

## Items and economy

### `drop`
A loot chest appeared for this player or party.

<!-- schema -->

**Example:**

```js
// sock: a connected AlSocket
// open_chest takes this `id`.
sock.on("drop", (data) => {
  console.log(data.id, data.chest, data.map, data.x, data.y, data.items);
});
```

```ts
// open_chest takes this `id`.
interface DropPayload {
  id: string;
  chest: string;
  map: string;
  x: number;
  y: number;
  items: number;
}
sock.on<DropPayload>("drop", (data) => {
  console.log(data.id, data.chest, data.map, data.x, data.y, data.items);
});
```

```python
# open_chest takes this `id`.
def on_drop(data: dict) -> None:
    print(data["id"], data["chest"], data["map"], data["x"], data["y"], data["items"])

sock.on("drop", on_drop)
```

```go
// open_chest takes this `id`.
type DropPayload struct {
	ID    string  `json:"id"`
	Chest string  `json:"chest"`
	Map   string  `json:"map"`
	X     float64 `json:"x"`
	Y     float64 `json:"y"`
	Items int     `json:"items"`
}
sock.On("drop", func(raw json.RawMessage) {
	var data DropPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.ID, data.Chest, data.Map, data.X, data.Y, data.Items)
})
```

```csharp
// open_chest takes this `id`.
sock.On("drop", data =>
{
    string? id = data.GetProperty("id").GetString();
    string? chest = data.GetProperty("chest").GetString();
    string? map = data.GetProperty("map").GetString();
    double x = data.GetProperty("x").GetDouble();
    double y = data.GetProperty("y").GetDouble();
    int items = data.GetProperty("items").GetInt32();
    Console.WriteLine($"{id} {chest} {map} {x} {y} {items}");
});
```

```rust
// open_chest takes this `id`.
sock.on("drop", |data| {
    let id = data["id"].as_str().unwrap_or_default();
    let chest = data["chest"].as_str().unwrap_or_default();
    let map = data["map"].as_str().unwrap_or_default();
    let x = data["x"].as_f64().unwrap_or(0.0);
    let y = data["y"].as_f64().unwrap_or(0.0);
    let items = data["items"].as_i64().unwrap_or(0);
    println!("{id} {chest} {map} {x} {y} {items}");
});
```

```java
// open_chest takes this `id`.
sock.on("drop", data -> {
    String id = data.path("id").asText();
    String chest = data.path("chest").asText();
    String map = data.path("map").asText();
    double x = data.path("x").asDouble();
    double y = data.path("y").asDouble();
    int items = data.path("items").asInt();
    System.out.println(id + " " + chest + " " + map + " " + x + " " + y + " " + items);
});
```

**Source:** `node/server.js:2454-2486`, `node/logic/cave_of_many_dreams.js:528`.

### `chest_opened`
The result of a chest open.

<!-- schema -->

**Notes:**
- In the party form, the server sends one object to each member in turn and changes `gold` before each send. Each member sees only its own share.

**Example:**

```js
// sock: a connected AlSocket
// `gone` is true when the chest does not exist.
sock.on("chest_opened", (data) => {
  console.log(data.id, data.opener, data.gold, data.goldm, data.items, data.gone);
});
```

```ts
// `gone` is true when the chest does not exist.
interface ChestOpenedPayload {
  id: string;
  opener?: string;
  gold?: number;
  goldm?: number;
  items?: unknown[];
  gone?: boolean;
}
sock.on<ChestOpenedPayload>("chest_opened", (data) => {
  console.log(data.id, data.opener, data.gold, data.goldm, data.items, data.gone);
});
```

```python
# `gone` is true when the chest does not exist.
def on_chest_opened(data: dict) -> None:
    print(data["id"], data.get("opener"), data.get("gold"), data.get("goldm"), data.get("items"), data.get("gone"))

sock.on("chest_opened", on_chest_opened)
```

```go
// `gone` is true when the chest does not exist.
type ChestOpenedPayload struct {
	ID     string  `json:"id"`
	Opener string  `json:"opener"` // optional
	Gold   float64 `json:"gold"`   // optional
	Goldm  float64 `json:"goldm"`  // optional
	Items  []any   `json:"items"`  // optional
	Gone   bool    `json:"gone"`   // optional
}
sock.On("chest_opened", func(raw json.RawMessage) {
	var data ChestOpenedPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.ID, data.Opener, data.Gold, data.Goldm, data.Items, data.Gone)
})
```

```csharp
// `gone` is true when the chest does not exist.
sock.On("chest_opened", data =>
{
    string? id = data.GetProperty("id").GetString();
    string? opener = data.TryGetProperty("opener", out var openerEl) ? openerEl.GetString() : null;
    double? gold = data.TryGetProperty("gold", out var goldEl) ? goldEl.GetDouble() : null;
    double? goldm = data.TryGetProperty("goldm", out var goldmEl) ? goldmEl.GetDouble() : null;
    JsonElement? items = data.TryGetProperty("items", out var itemsEl) ? itemsEl : null;
    bool? gone = data.TryGetProperty("gone", out var goneEl) ? goneEl.GetBoolean() : null;
    Console.WriteLine($"{id} {opener} {gold} {goldm} {items} {gone}");
});
```

```rust
// `gone` is true when the chest does not exist.
sock.on("chest_opened", |data| {
    let id = data["id"].as_str().unwrap_or_default();
    let opener = data["opener"].as_str(); // optional
    let gold = data["gold"].as_f64(); // optional
    let goldm = data["goldm"].as_f64(); // optional
    let items = data.get("items"); // optional
    let gone = data["gone"].as_bool(); // optional
    println!("{id} {opener:?} {gold:?} {goldm:?} {items:?} {gone:?}");
});
```

```java
// `gone` is true when the chest does not exist.
sock.on("chest_opened", data -> {
    String id = data.path("id").asText();
    String opener = data.path("opener").asText(null); // optional
    JsonNode gold = data.get("gold"); // optional: null when absent
    JsonNode goldm = data.get("goldm"); // optional: null when absent
    JsonNode items = data.get("items"); // optional: null when absent
    JsonNode gone = data.get("gone"); // optional: null when absent
    System.out.println(id + " " + opener + " " + gold + " " + goldm + " " + items + " " + gone);
});
```

**Source:** `node/server.js:11392`, `node/server.js:11552`, `node/server.js:11555`, `node/logic/cave_of_many_dreams.js:567`.

### `q_data`
The progress of an upgrade or compound while the timer runs: the digits of the hidden roll, and the success or failure flags.

<!-- schema -->

**Notes:**
- The roll is a number from 0 to 1 (`u_roll` or `c_roll`). `nums[0]` to `nums[2]` are its 4th, 3rd and 2nd decimal digits. `nums[3]` is its 1st decimal digit (node/server.js:14747-14758).
- Upgrade timing: a digit shows when the time left drops below `len*0.8`, `len*0.64`, `len*0.4` and `min(3000, len*0.3)`. The result shows below `min(2200, len*0.22)` (node/server.js:14747-14769).
- Compound timing: the digits show below 8,000, 6,400, 5,000 and 3,000 ms left. The result shows below 2,200 ms (node/server.js:14784-14807).
- The server sends `q_data` only on a change. A short timer (for example 500 ms on hardcore) can show several digits in one `q_data`.

**Example:**

```js
// sock: a connected AlSocket
// `p.nums` holds the digits of the roll shown so far.
sock.on("q_data", (data) => {
  console.log(data.num, data.p.nums, data.p.success, data.p.failure, data.q);
});
```

```ts
// `p.nums` holds the digits of the roll shown so far.
interface QDataPlaceholder {
  chance: number;
  name: string;
  level?: number;
  scroll?: string | null;
  offering?: string;
  nums: number[];
  success?: true;
  failure?: true;
}
interface QDataPayload {
  num: number;
  p: QDataPlaceholder;
  q: Record<string, { ms: number; len: number; num: number }>;
}
sock.on<QDataPayload>("q_data", (data) => {
  console.log(data.num, data.p.nums, data.p.success, data.p.failure, data.q);
});
```

```python
# `p.nums` holds the digits of the roll shown so far.
def on_q_data(data: dict) -> None:
    p = data["p"]
    print(data["num"], p["nums"], p.get("success"), p.get("failure"), data["q"])

sock.on("q_data", on_q_data)
```

```go
// `p.nums` holds the digits of the roll shown so far.
type QDataPlaceholder struct {
	Chance  float64 `json:"chance"`
	Name    string  `json:"name"`
	Nums    []int   `json:"nums"`
	Success bool    `json:"success"` // optional: false when absent
	Failure bool    `json:"failure"` // optional: false when absent
}
type QDataPayload struct {
	Num int                        `json:"num"`
	P   QDataPlaceholder           `json:"p"`
	Q   map[string]json.RawMessage `json:"q"`
}
sock.On("q_data", func(raw json.RawMessage) {
	var data QDataPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Num, data.P.Nums, data.P.Success, data.P.Failure, len(data.Q))
})
```

```csharp
// `p.nums` holds the digits of the roll shown so far.
sock.On("q_data", data =>
{
    int num = data.GetProperty("num").GetInt32();
    JsonElement p = data.GetProperty("p");
    JsonElement nums = p.GetProperty("nums");
    bool success = p.TryGetProperty("success", out _);
    bool failure = p.TryGetProperty("failure", out _);
    JsonElement q = data.GetProperty("q");
    Console.WriteLine($"{num} {nums} {success} {failure} {q}");
});
```

```rust
// `p.nums` holds the digits of the roll shown so far.
sock.on("q_data", |data| {
    let num = data["num"].as_i64().unwrap_or(0);
    let p = &data["p"];
    let nums = &p["nums"];
    let success = p["success"].as_bool().unwrap_or(false); // optional
    let failure = p["failure"].as_bool().unwrap_or(false); // optional
    let q = &data["q"];
    println!("{num} {nums} {success} {failure} {q}");
});
```

```java
// `p.nums` holds the digits of the roll shown so far.
sock.on("q_data", data -> {
    int num = data.path("num").asInt();
    JsonNode p = data.path("p");
    JsonNode nums = p.path("nums");
    boolean success = p.path("success").asBoolean(false); // optional
    boolean failure = p.path("failure").asBoolean(false); // optional
    JsonNode q = data.path("q");
    System.out.println(num + " " + nums + " " + success + " " + failure + " " + q);
});
```

**Source:** `node/server.js:14772`, `node/server.js:14809`.

### `upgrade`
Plays an NPC animation for an upgrade, compound, exchange or similar.

<!-- schema -->

**Notes:**
- It is only an animation. The result of your own upgrade or compound arrives as a `game_response` hitchhiker in `player`.

**Example:**

```js
// sock: a connected AlSocket
// `success` is 1 or 0.
sock.on("upgrade", (data) => {
  console.log(data.type, data.success);
});
```

```ts
// `success` is 1 or 0.
interface UpgradePayload {
  type: string;
  success: number;
}
sock.on<UpgradePayload>("upgrade", (data) => {
  console.log(data.type, data.success);
});
```

```python
# `success` is 1 or 0.
def on_upgrade(data: dict) -> None:
    print(data["type"], data["success"])

sock.on("upgrade", on_upgrade)
```

```go
// `success` is 1 or 0.
type UpgradePayload struct {
	Type    string `json:"type"`
	Success int    `json:"success"`
}
sock.On("upgrade", func(raw json.RawMessage) {
	var data UpgradePayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Type, data.Success)
})
```

```csharp
// `success` is 1 or 0.
sock.On("upgrade", data =>
{
    string? typeName = data.GetProperty("type").GetString();
    int success = data.GetProperty("success").GetInt32();
    Console.WriteLine($"{typeName} {success}");
});
```

```rust
// `success` is 1 or 0.
sock.on("upgrade", |data| {
    let type_name = data["type"].as_str().unwrap_or_default();
    let success = data["success"].as_i64().unwrap_or(0);
    println!("{type_name} {success}");
});
```

```java
// `success` is 1 or 0.
sock.on("upgrade", data -> {
    String typeName = data.path("type").asText();
    int success = data.path("success").asInt();
    System.out.println(typeName + " " + success);
});
```

**Source:** `node/server.js:14937`, `node/server.js:14852`, `node/server.js:6737`.

### `secondhands`
The item list of the secondhands NPC.

<!-- schema -->

**Notes:**
- With `request_id`, the list comes in a `game_response` `data` as `items`, in reverse order.
- The list holds at most 5 entries with the same `name` and `level`. At that limit, an item with a `p` replaces an entry without one (node/server_functions.js:624-638).
- A new stack of the same item adds to the `q` of the old entry and keeps its `rid` (node/server_functions.js:619-622).
- **Server bug:** the slot of a new entry is `S.sold.length % 400`. When the list has 400 entries, each new entry replaces entry 0, not the oldest entry (node/server_functions.js:632).

**Example:**

```js
// sock: a connected AlSocket
// Items for sale at the secondhands NPC.
sock.on("secondhands", (data) => {
  for (const item of data) console.log(item.name, item.level);
});
```

```ts
// Items for sale at the secondhands NPC.
interface SecondhandsEntry {
  name: string;
  level?: number;
}
sock.on<SecondhandsEntry[]>("secondhands", (data) => {
  for (const item of data) console.log(item.name, item.level);
});
```

```python
# Items for sale at the secondhands NPC.
def on_secondhands(data: list) -> None:
    for item in data:
        print(item["name"], item.get("level"))

sock.on("secondhands", on_secondhands)
```

```go
// Items for sale at the secondhands NPC.
type SecondhandsEntry struct {
	Name  string `json:"name"`
	Level int    `json:"level"` // optional
}
sock.On("secondhands", func(raw json.RawMessage) {
	var data []SecondhandsEntry
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	for _, item := range data {
		fmt.Println(item.Name, item.Level)
	}
})
```

```csharp
// Items for sale at the secondhands NPC.
sock.On("secondhands", data =>
{
    foreach (JsonElement item in data.EnumerateArray())
    {
        string? name = item.GetProperty("name").GetString();
        int? level = item.TryGetProperty("level", out var levelEl) ? levelEl.GetInt32() : null;
        Console.WriteLine($"{name} {level}");
    }
});
```

```rust
// Items for sale at the secondhands NPC.
sock.on("secondhands", |data| {
    for item in data.as_array().into_iter().flatten() {
        let name = item["name"].as_str().unwrap_or_default();
        let level = item["level"].as_i64(); // optional
        println!("{name} {level:?}");
    }
});
```

```java
// Items for sale at the secondhands NPC.
sock.on("secondhands", data -> {
    for (JsonNode item : data) {
        String name = item.path("name").asText();
        JsonNode level = item.get("level"); // optional: null when absent
        System.out.println(name + " " + level);
    }
});
```

**Source:** `node/server.js:7972`, `node/server.js:8391`.

### `lostandfound`
The item list of the lost and found NPC. The request needs a donation first.

<!-- schema -->

**Notes:**
- With `request_id`, the list comes in a `game_response` `data` as `items`, in reverse order.
- The list has the same limits as `secondhands`: at most 5 entries per `name` and `level`, and 400 slots (node/server_functions.js:641-670). The same server bug applies: with 400 entries, each new entry replaces entry 0.

**Example:**

```js
// sock: a connected AlSocket
// Items at the lost and found NPC.
sock.on("lostandfound", (data) => {
  for (const item of data) console.log(item.name, item.level);
});
```

```ts
// Items at the lost and found NPC.
interface LostandfoundEntry {
  name: string;
  level?: number;
}
sock.on<LostandfoundEntry[]>("lostandfound", (data) => {
  for (const item of data) console.log(item.name, item.level);
});
```

```python
# Items at the lost and found NPC.
def on_lostandfound(data: list) -> None:
    for item in data:
        print(item["name"], item.get("level"))

sock.on("lostandfound", on_lostandfound)
```

```go
// Items at the lost and found NPC.
type LostandfoundEntry struct {
	Name  string `json:"name"`
	Level int    `json:"level"` // optional
}
sock.On("lostandfound", func(raw json.RawMessage) {
	var data []LostandfoundEntry
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	for _, item := range data {
		fmt.Println(item.Name, item.Level)
	}
})
```

```csharp
// Items at the lost and found NPC.
sock.On("lostandfound", data =>
{
    foreach (JsonElement item in data.EnumerateArray())
    {
        string? name = item.GetProperty("name").GetString();
        int? level = item.TryGetProperty("level", out var levelEl) ? levelEl.GetInt32() : null;
        Console.WriteLine($"{name} {level}");
    }
});
```

```rust
// Items at the lost and found NPC.
sock.on("lostandfound", |data| {
    for item in data.as_array().into_iter().flatten() {
        let name = item["name"].as_str().unwrap_or_default();
        let level = item["level"].as_i64(); // optional
        println!("{name} {level:?}");
    }
});
```

```java
// Items at the lost and found NPC.
sock.on("lostandfound", data -> {
    for (JsonNode item : data) {
        String name = item.path("name").asText();
        JsonNode level = item.get("level"); // optional: null when absent
        System.out.println(name + " " + level);
    }
});
```

**Source:** `node/server.js:7995`, `node/server.js:8391`.

### `trade_history`
The trade history of the player.

<!-- schema -->

**Example:**

```js
// sock: a connected AlSocket
// Each row: event, other player, item, price.
sock.on("trade_history", (data) => {
  for (const [event, other, item, price] of data) console.log(event, other, item, price);
});
```

```ts
// Each row: event, other player, item, price.
// price is null for a giveaway; a swap adds the received item at index 4.
type TradeHistoryRow = [event: string, other: string, item: Record<string, unknown>, price: number | null, received?: Record<string, unknown>];
sock.on<TradeHistoryRow[]>("trade_history", (data) => {
  for (const [event, other, item, price] of data) console.log(event, other, item, price);
});
```

```python
# Each row: event, other player, item, price.
def on_trade_history(data: list) -> None:
    for row in data:
        event_name, other, item = row[:3]
        price = row[3] if len(row) > 3 else None
        print(event_name, other, item, price)

sock.on("trade_history", on_trade_history)
```

```go
// Each row: event, other player, item, price.
sock.On("trade_history", func(raw json.RawMessage) {
	var data [][]any // each row mixes strings, objects and numbers
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	for _, row := range data {
		eventName, other, item := row[0], row[1], row[2]
		var price any
		if len(row) > 3 {
			price = row[3]
		}
		fmt.Println(eventName, other, item, price)
	}
})
```

```csharp
// Each row: event, other player, item, price.
sock.On("trade_history", data =>
{
    foreach (JsonElement row in data.EnumerateArray())
    {
        string? eventName = row[0].GetString();
        string? other = row[1].GetString();
        JsonElement item = row[2];
        // price is null for a giveaway, so check the kind first.
        double? price = row.GetArrayLength() > 3 && row[3].ValueKind == JsonValueKind.Number ? row[3].GetDouble() : null;
        Console.WriteLine($"{eventName} {other} {item} {price}");
    }
});
```

```rust
// Each row: event, other player, item, price.
sock.on("trade_history", |data| {
    for row in data.as_array().into_iter().flatten() {
        let event_name = row[0].as_str().unwrap_or_default();
        let other = row[1].as_str().unwrap_or_default();
        let item = &row[2];
        let price = row.get(3).and_then(|v| v.as_f64()); // optional
        println!("{event_name} {other} {item} {price:?}");
    }
});
```

```java
// Each row: event, other player, item, price.
sock.on("trade_history", data -> {
    for (JsonNode row : data) {
        String eventName = row.path(0).asText();
        String other = row.path(1).asText();
        JsonNode item = row.path(2);
        JsonNode price = row.get(3); // optional: null when absent
        System.out.println(eventName + " " + other + " " + item + " " + price);
    }
});
```

**Source:** `node/server.js:9183`, `node/server_functions.js:342-362`.

### `merrit_status`
The status of Merrit, the market patron NPC that gives a parcel to merchants with an open stand in town.

<!-- schema -->

**Notes:**
- `next_at` and `server_now` use the clock of the server. Use `next_at - server_now` for the wait, not your own clock.
- The server adds the `cooldown` reason only when it knows the cooldown of the account. It learns it from a `merrit_info` request or a gift on this server (node/logic/market_patron_runtime.js:58-59, 78, 222).

**Example:**

```js
// sock: a connected AlSocket
// Each reason tells why no visit comes now. The error form has only `reasons`.
sock.on("merrit_status", (data) => {
  if (data.next_at !== undefined) console.log("wait ms:", data.next_at - data.server_now);
  for (const r of data.reasons) console.log(r.code, r.name, r.distance, r.remaining_ms);
  if (data.last) console.log("last gift at", data.last.at);
});
```

```ts
// Each reason tells why no visit comes now. The error form has only `reasons`.
interface MerritStatusReason {
  code: string;
  name?: string;
  distance?: number;
  remaining_ms?: number;
}
interface MerritStatusReceipt {
  id: string;
  at: number; // ms since the Unix epoch
  name: string;
  shells: 0 | 1;
}
interface MerritStatusPayload {
  reasons: MerritStatusReason[];
  next_at?: number;
  server_now?: number;
  last?: MerritStatusReceipt | null;
  account_last?: MerritStatusReceipt | null;
  stand_opened?: boolean;
}
sock.on<MerritStatusPayload>("merrit_status", (data) => {
  if (data.next_at !== undefined && data.server_now !== undefined) console.log("wait ms:", data.next_at - data.server_now);
  for (const r of data.reasons) console.log(r.code, r.name, r.distance, r.remaining_ms);
  if (data.last) console.log("last gift at", data.last.at);
});
```

```python
# Each reason tells why no visit comes now. The error form has only `reasons`.
def on_merrit_status(data: dict) -> None:
    if "next_at" in data:
        print("wait ms:", data["next_at"] - data["server_now"])
    for r in data["reasons"]:
        print(r["code"], r.get("name"), r.get("distance"), r.get("remaining_ms"))
    if data.get("last"):
        print("last gift at", data["last"]["at"])

sock.on("merrit_status", on_merrit_status)
```

```go
// Each reason tells why no visit comes now. The error form has only `reasons`.
type MerritStatusReason struct {
	Code        string   `json:"code"`
	Name        string   `json:"name,omitempty"`
	Distance    *float64 `json:"distance,omitempty"`
	RemainingMs *float64 `json:"remaining_ms,omitempty"`
}
type MerritStatusPayload struct {
	Reasons   []MerritStatusReason `json:"reasons"`
	NextAt    *float64             `json:"next_at,omitempty"`    // absent in the error form
	ServerNow *float64             `json:"server_now,omitempty"` // absent in the error form
	Last      *struct {
		At float64 `json:"at"`
	} `json:"last,omitempty"` // null when no gift yet
}
sock.On("merrit_status", func(raw json.RawMessage) {
	var data MerritStatusPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	if data.NextAt != nil && data.ServerNow != nil {
		fmt.Println("wait ms:", *data.NextAt-*data.ServerNow)
	}
	for _, r := range data.Reasons {
		fmt.Println(r.Code, r.Name)
	}
	if data.Last != nil {
		fmt.Println("last gift at", data.Last.At)
	}
})
```

```csharp
// Each reason tells why no visit comes now. The error form has only `reasons`.
sock.On("merrit_status", data =>
{
    if (data.TryGetProperty("next_at", out var nextAt) && data.TryGetProperty("server_now", out var now))
        Console.WriteLine($"wait ms: {nextAt.GetDouble() - now.GetDouble()}");
    foreach (JsonElement r in data.GetProperty("reasons").EnumerateArray())
    {
        string? code = r.GetProperty("code").GetString();
        string? name = r.TryGetProperty("name", out var n) ? n.GetString() : null;
        Console.WriteLine($"{code} {name}");
    }
    if (data.TryGetProperty("last", out var last) && last.ValueKind == JsonValueKind.Object)
        Console.WriteLine($"last gift at {last.GetProperty("at").GetDouble()}");
});
```

```rust
// Each reason tells why no visit comes now. The error form has only `reasons`.
sock.on("merrit_status", |data| {
    if let (Some(next_at), Some(now)) = (data["next_at"].as_f64(), data["server_now"].as_f64()) {
        println!("wait ms: {}", next_at - now);
    }
    for r in data["reasons"].as_array().into_iter().flatten() {
        let code = r["code"].as_str().unwrap_or_default();
        let name = r["name"].as_str(); // optional
        println!("{code} {name:?}");
    }
    if let Some(at) = data["last"]["at"].as_f64() {
        println!("last gift at {at}");
    }
});
```

```java
// Each reason tells why no visit comes now. The error form has only `reasons`.
sock.on("merrit_status", data -> {
    if (data.has("next_at") && data.has("server_now"))
        System.out.println("wait ms: " + (data.get("next_at").asDouble() - data.get("server_now").asDouble()));
    for (JsonNode r : data.path("reasons")) {
        String code = r.path("code").asText();
        String name = r.path("name").asText(null); // optional
        System.out.println(code + " " + name);
    }
    JsonNode last = data.path("last");
    if (last.isObject()) System.out.println("last gift at " + last.path("at").asDouble());
});
```

**Source:** `node/logic/market_patron_runtime.js:65-71` (`market_patron_public_status`), `node/logic/market_patron.js:29-68` (reason codes).

### `merrit_gift`
Merrit gave a market parcel to this player.

<!-- schema -->

**Example:**

```js
// sock: a connected AlSocket
// A parcel from Merrit; `receipt.shells` is 1 when a shell came with it.
sock.on("merrit_gift", (data) => {
  console.log(data.id, data.receipt.item, data.receipt.shells, data.receipt.at);
});
```

```ts
// A parcel from Merrit; `receipt.shells` is 1 when a shell came with it.
interface MerritGiftReceipt {
  id: string;
  at: number; // ms since the Unix epoch
  character: string;
  name: string;
  item: "marketparcel";
  quantity: 1;
  shells: 0 | 1;
  reason: string;
  reason_phrase: string;
  reason_phrase_args: Record<string, unknown>;
}
interface MerritGiftPayload {
  id: string;
  receipt: MerritGiftReceipt;
}
sock.on<MerritGiftPayload>("merrit_gift", (data) => {
  console.log(data.id, data.receipt.item, data.receipt.shells, data.receipt.at);
});
```

```python
# A parcel from Merrit; `receipt.shells` is 1 when a shell came with it.
def on_merrit_gift(data: dict) -> None:
    receipt = data["receipt"]
    print(data["id"], receipt["item"], receipt["shells"], receipt["at"])

sock.on("merrit_gift", on_merrit_gift)
```

```go
// A parcel from Merrit; `receipt.shells` is 1 when a shell came with it.
type MerritGiftReceipt struct {
	ID     string  `json:"id"`
	At     float64 `json:"at"` // ms since the Unix epoch
	Name   string  `json:"name"`
	Item   string  `json:"item"`
	Shells int     `json:"shells"`
}
type MerritGiftPayload struct {
	ID      string            `json:"id"`
	Receipt MerritGiftReceipt `json:"receipt"`
}
sock.On("merrit_gift", func(raw json.RawMessage) {
	var data MerritGiftPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.ID, data.Receipt.Item, data.Receipt.Shells, data.Receipt.At)
})
```

```csharp
// A parcel from Merrit; `receipt.shells` is 1 when a shell came with it.
sock.On("merrit_gift", data =>
{
    string? id = data.GetProperty("id").GetString();
    JsonElement receipt = data.GetProperty("receipt");
    string? item = receipt.GetProperty("item").GetString();
    int shells = receipt.GetProperty("shells").GetInt32();
    double at = receipt.GetProperty("at").GetDouble();
    Console.WriteLine($"{id} {item} {shells} {at}");
});
```

```rust
// A parcel from Merrit; `receipt.shells` is 1 when a shell came with it.
sock.on("merrit_gift", |data| {
    let id = data["id"].as_str().unwrap_or_default();
    let receipt = &data["receipt"];
    let item = receipt["item"].as_str().unwrap_or_default();
    let shells = receipt["shells"].as_i64().unwrap_or(0);
    let at = receipt["at"].as_f64().unwrap_or(0.0);
    println!("{id} {item} {shells} {at}");
});
```

```java
// A parcel from Merrit; `receipt.shells` is 1 when a shell came with it.
sock.on("merrit_gift", data -> {
    String id = data.path("id").asText();
    JsonNode receipt = data.path("receipt");
    String item = receipt.path("item").asText();
    int shells = receipt.path("shells").asInt();
    double at = receipt.path("at").asDouble();
    System.out.println(id + " " + item + " " + shells + " " + at);
});
```

**Source:** `node/logic/market_patron_runtime.js:230`, `node/logic/market_patron_runtime.js:156-167` (the receipt).

### `tavern`
Tavern game events.

<!-- schema -->

**Notes:**
- The server decides the result of a wheel or slots spin when it takes the bet. It is in `q.wheel` or `q.slots` of your `player` during the spin (node/logic/tavern_wheel.js:27-39, node/logic/tavern_slots.js:54-65).
- A dice result goes only to the tavern instance. A slots or wheel result also goes to its owner outside the tavern (`tavern_result`, node/logic/tavern.js:11-14).
- The dice `gold` field changes meaning: the gross win on `"won"`, the stake on `"lost"`.
- The roulette form works only on a development server (node/server.js:12738-12740). The roulette rounds never settle (node/server_functions.js:1594).

**Example:**

```js
// sock: a connected AlSocket
// The other fields depend on `event`.
sock.on("tavern", (data) => {
  switch (data.event) {
    case "info":
      console.log(data.edge, data.max);
      break;
    case "bet":
      console.log(data.name, data.gold);
      break;
    case "won":
      console.log(data.name, data.type, data.gold, data.net);
      break;
    case "lost":
      console.log(data.name, data.type, data.gold);
      break;
    case "refund":
      console.log(data.name, data.gold);
      break;
    default:
      console.log(data.event);
  }
});
```

```ts
// The other fields depend on `event`.
interface TavernPayload {
  event?: string; // absent only in the dev-only roulette form
  edge?: number;
  max?: number;
  name?: string;
  gold?: number;
  type?: string;
  net?: number;
}
sock.on<TavernPayload>("tavern", (data) => {
  switch (data.event) {
    case "info":
      console.log(data.edge, data.max);
      break;
    case "bet":
      console.log(data.name, data.gold);
      break;
    case "won":
      console.log(data.name, data.type, data.gold, data.net);
      break;
    case "lost":
      console.log(data.name, data.type, data.gold);
      break;
    case "refund":
      console.log(data.name, data.gold);
      break;
    default:
      console.log(data.event);
  }
});
```

```python
# The other fields depend on `event`.
def on_tavern(data: dict) -> None:
    match data["event"]:
        case "info":
            print(data["edge"], data["max"])
        case "bet":
            print(data["name"], data["gold"])
        case "won":
            print(data["name"], data["type"], data["gold"], data["net"])
        case "lost":
            print(data["name"], data["type"], data["gold"])
        case "refund":
            print(data["name"], data["gold"])
        case _:
            print(data["event"])

sock.on("tavern", on_tavern)
```

```go
// The other fields depend on `event`.
type TavernPayload struct {
	Event string  `json:"event"`
	Edge  float64 `json:"edge"`
	Max   float64 `json:"max"`
	Name  string  `json:"name"`
	Gold  float64 `json:"gold"`
	Type  string  `json:"type"`
	Net   float64 `json:"net"`
}
sock.On("tavern", func(raw json.RawMessage) {
	var data TavernPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	switch data.Event {
	case "info":
		fmt.Println(data.Edge, data.Max)
	case "bet":
		fmt.Println(data.Name, data.Gold)
	case "won":
		fmt.Println(data.Name, data.Type, data.Gold, data.Net)
	case "lost":
		fmt.Println(data.Name, data.Type, data.Gold)
	case "refund":
		fmt.Println(data.Name, data.Gold)
	default:
		fmt.Println(data.Event)
	}
})
```

```csharp
// The other fields depend on `event`.
sock.On("tavern", data =>
{
    string? eventName = data.GetProperty("event").GetString();
    switch (eventName)
    {
        case "info":
        {
            double edge = data.GetProperty("edge").GetDouble();
            double max = data.GetProperty("max").GetDouble();
            Console.WriteLine($"{edge} {max}");
            break;
        }
        case "bet":
        {
            string? name = data.GetProperty("name").GetString();
            double gold = data.GetProperty("gold").GetDouble();
            Console.WriteLine($"{name} {gold}");
            break;
        }
        case "won":
        {
            string? name = data.GetProperty("name").GetString();
            string? typeName = data.GetProperty("type").GetString();
            double gold = data.GetProperty("gold").GetDouble();
            double net = data.GetProperty("net").GetDouble();
            Console.WriteLine($"{name} {typeName} {gold} {net}");
            break;
        }
        case "lost":
        {
            string? name = data.GetProperty("name").GetString();
            string? typeName = data.GetProperty("type").GetString();
            double gold = data.GetProperty("gold").GetDouble();
            Console.WriteLine($"{name} {typeName} {gold}");
            break;
        }
        case "refund":
        {
            string? name = data.GetProperty("name").GetString();
            double gold = data.GetProperty("gold").GetDouble();
            Console.WriteLine($"{name} {gold}");
            break;
        }
        default:
            Console.WriteLine(eventName);
            break;
    }
});
```

```rust
// The other fields depend on `event`.
sock.on("tavern", |data| {
    match data["event"].as_str().unwrap_or_default() {
        "info" => {
            let edge = data["edge"].as_f64().unwrap_or(0.0);
            let max = data["max"].as_f64().unwrap_or(0.0);
            println!("{edge} {max}");
        }
        "bet" => {
            let name = data["name"].as_str().unwrap_or_default();
            let gold = data["gold"].as_f64().unwrap_or(0.0);
            println!("{name} {gold}");
        }
        "won" => {
            let name = data["name"].as_str().unwrap_or_default();
            let type_name = data["type"].as_str().unwrap_or_default();
            let gold = data["gold"].as_f64().unwrap_or(0.0);
            let net = data["net"].as_f64().unwrap_or(0.0);
            println!("{name} {type_name} {gold} {net}");
        }
        "lost" => {
            let name = data["name"].as_str().unwrap_or_default();
            let type_name = data["type"].as_str().unwrap_or_default();
            let gold = data["gold"].as_f64().unwrap_or(0.0);
            println!("{name} {type_name} {gold}");
        }
        "refund" => {
            let name = data["name"].as_str().unwrap_or_default();
            let gold = data["gold"].as_f64().unwrap_or(0.0);
            println!("{name} {gold}");
        }
        other => println!("{other}"),
    }
});
```

```java
// The other fields depend on `event`.
sock.on("tavern", data -> {
    String eventName = data.path("event").asText();
    switch (eventName) {
        case "info" -> {
            double edge = data.path("edge").asDouble();
            double max = data.path("max").asDouble();
            System.out.println(edge + " " + max);
        }
        case "bet" -> {
            String name = data.path("name").asText();
            double gold = data.path("gold").asDouble();
            System.out.println(name + " " + gold);
        }
        case "won" -> {
            String name = data.path("name").asText();
            String typeName = data.path("type").asText();
            double gold = data.path("gold").asDouble();
            double net = data.path("net").asDouble();
            System.out.println(name + " " + typeName + " " + gold + " " + net);
        }
        case "lost" -> {
            String name = data.path("name").asText();
            String typeName = data.path("type").asText();
            double gold = data.path("gold").asDouble();
            System.out.println(name + " " + typeName + " " + gold);
        }
        case "refund" -> {
            String name = data.path("name").asText();
            double gold = data.path("gold").asDouble();
            System.out.println(name + " " + gold);
        }
        default -> System.out.println(eventName);
    }
});
```

**Source:** `node/server.js:12853`, `node/server_functions.js:1487-1528`, `node/logic/tavern.js:11-14`.

### `dice`
The state of the tavern dice round.

<!-- schema -->

**Notes:**
- One round takes about 43.6 s (node/server_functions.js:1406-1458, 1552). The bets take 30 s, the roll 10 s, the lock 1.6 s, and the pause before the next `bets` 2 s.
- **Server bug:** on hardcore servers, about 7% of rounds replace the roll with the last roll after the server publishes the commitment (`node/server_functions.js:1588-1590`). The revealed number then does not match the committed text.

**Example:**

```js
// sock: a connected AlSocket
// `num` is a string, for example "42.17".
sock.on("dice", (data) => {
  switch (data.state) {
    case "roll":
      console.log(data.state);
      break;
    case "lock":
      console.log(data.num, data.text, data.key);
      break;
    case "bets":
      console.log(data.hex, data.algorithm);
      break;
    default:
      console.log(data.state);
  }
});
```

```ts
// `num` is a string, for example "42.17".
interface DicePayload {
  state: string;
  num?: string;
  text?: string;
  key?: string;
  hex?: string;
  algorithm?: string;
}
sock.on<DicePayload>("dice", (data) => {
  switch (data.state) {
    case "roll":
      console.log(data.state);
      break;
    case "lock":
      console.log(data.num, data.text, data.key);
      break;
    case "bets":
      console.log(data.hex, data.algorithm);
      break;
    default:
      console.log(data.state);
  }
});
```

```python
# `num` is a string, for example "42.17".
def on_dice(data: dict) -> None:
    match data["state"]:
        case "roll":
            print(data["state"])
        case "lock":
            print(data["num"], data["text"], data["key"])
        case "bets":
            print(data["hex"], data["algorithm"])
        case _:
            print(data["state"])

sock.on("dice", on_dice)
```

```go
// `num` is a string, for example "42.17".
type DicePayload struct {
	State     string `json:"state"`
	Num       string `json:"num"`
	Text      string `json:"text"`
	Key       string `json:"key"`
	Hex       string `json:"hex"`
	Algorithm string `json:"algorithm"`
}
sock.On("dice", func(raw json.RawMessage) {
	var data DicePayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	switch data.State {
	case "roll":
		fmt.Println(data.State)
	case "lock":
		fmt.Println(data.Num, data.Text, data.Key)
	case "bets":
		fmt.Println(data.Hex, data.Algorithm)
	default:
		fmt.Println(data.State)
	}
})
```

```csharp
// `num` is a string, for example "42.17".
sock.On("dice", data =>
{
    string? state = data.GetProperty("state").GetString();
    switch (state)
    {
        case "roll":
        {
            Console.WriteLine(state);
            break;
        }
        case "lock":
        {
            string? num = data.GetProperty("num").GetString();
            string? text = data.GetProperty("text").GetString();
            string? key = data.GetProperty("key").GetString();
            Console.WriteLine($"{num} {text} {key}");
            break;
        }
        case "bets":
        {
            string? hex = data.GetProperty("hex").GetString();
            string? algorithm = data.GetProperty("algorithm").GetString();
            Console.WriteLine($"{hex} {algorithm}");
            break;
        }
        default:
            Console.WriteLine(state);
            break;
    }
});
```

```rust
// `num` is a string, for example "42.17".
sock.on("dice", |data| {
    match data["state"].as_str().unwrap_or_default() {
        "roll" => println!("roll"),
        "lock" => {
            let num = data["num"].as_str().unwrap_or_default();
            let text = data["text"].as_str().unwrap_or_default();
            let key = data["key"].as_str().unwrap_or_default();
            println!("{num} {text} {key}");
        }
        "bets" => {
            let hex = data["hex"].as_str().unwrap_or_default();
            let algorithm = data["algorithm"].as_str().unwrap_or_default();
            println!("{hex} {algorithm}");
        }
        other => println!("{other}"),
    }
});
```

```java
// `num` is a string, for example "42.17".
sock.on("dice", data -> {
    String state = data.path("state").asText();
    switch (state) {
        case "roll" -> System.out.println(state);
        case "lock" -> {
            String num = data.path("num").asText();
            String text = data.path("text").asText();
            String key = data.path("key").asText();
            System.out.println(num + " " + text + " " + key);
        }
        case "bets" -> {
            String hex = data.path("hex").asText();
            String algorithm = data.path("algorithm").asText();
            System.out.println(hex + " " + algorithm);
        }
        default -> System.out.println(state);
    }
});
```

**Source:** `node/server_functions.js:1414`, `node/server_functions.js:1453`, `node/server_functions.js:1587`.

### `poker`
The tavern poker table.

<!-- schema -->

**Notes:**
- To check a hand, compute `HMAC-SHA256(key, order.join(","))` in hex. It must equal `commit` from the start of the hand. The server deals from the end of `order` (`deck.pop()`): two cards to each seat in seat order, then the board (node/logic/tavern_poker.js:686-711).
- The `log` of the table keeps 8 events. `state` sends the last 6 (node/logic/tavern_poker.js:309-313, 453).
- On a hardcore server, `instance_emit` sends `poker` to every character on the server, not only to the tavern (node/server_functions.js:3542-3544).

**Example:**

```js
// sock: a connected AlSocket
// The other fields depend on `event`.
sock.on("poker", (data) => {
  switch (data.event) {
    case "state":
      console.log(data.seats, data.hand);
      break;
    case "cards":
      console.log(data.n, data.cards);
      break;
    default:
      console.log(data.event);
  }
});
```

```ts
// The other fields depend on `event`.
interface PokerPayload {
  event: string;
  seats?: unknown[];
  hand?: Record<string, unknown> | null; // null before the first hand
  n?: number;
  cards?: unknown[];
}
sock.on<PokerPayload>("poker", (data) => {
  switch (data.event) {
    case "state":
      console.log(data.seats, data.hand);
      break;
    case "cards":
      console.log(data.n, data.cards);
      break;
    default:
      console.log(data.event);
  }
});
```

```python
# The other fields depend on `event`.
def on_poker(data: dict) -> None:
    match data["event"]:
        case "state":
            print(data["seats"], data.get("hand"))
        case "cards":
            print(data["n"], data["cards"])
        case _:
            print(data["event"])

sock.on("poker", on_poker)
```

```go
// The other fields depend on `event`.
type PokerPayload struct {
	Event string         `json:"event"`
	Seats []any          `json:"seats"`
	Hand  map[string]any `json:"hand"` // optional
	N     int            `json:"n"`
	Cards []any          `json:"cards"`
}
sock.On("poker", func(raw json.RawMessage) {
	var data PokerPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	switch data.Event {
	case "state":
		fmt.Println(data.Seats, data.Hand)
	case "cards":
		fmt.Println(data.N, data.Cards)
	default:
		fmt.Println(data.Event)
	}
})
```

```csharp
// The other fields depend on `event`.
sock.On("poker", data =>
{
    string? eventName = data.GetProperty("event").GetString();
    switch (eventName)
    {
        case "state":
        {
            JsonElement seats = data.GetProperty("seats");
            JsonElement? hand = data.TryGetProperty("hand", out var handEl) ? handEl : null;
            Console.WriteLine($"{seats} {hand}");
            break;
        }
        case "cards":
        {
            int n = data.GetProperty("n").GetInt32();
            JsonElement cards = data.GetProperty("cards");
            Console.WriteLine($"{n} {cards}");
            break;
        }
        default:
            Console.WriteLine(eventName);
            break;
    }
});
```

```rust
// The other fields depend on `event`.
sock.on("poker", |data| {
    match data["event"].as_str().unwrap_or_default() {
        "state" => {
            let seats = &data["seats"];
            let hand = data.get("hand"); // optional
            println!("{seats} {hand:?}");
        }
        "cards" => {
            let n = data["n"].as_i64().unwrap_or(0);
            let cards = &data["cards"];
            println!("{n} {cards}");
        }
        other => println!("{other}"),
    }
});
```

```java
// The other fields depend on `event`.
sock.on("poker", data -> {
    String eventName = data.path("event").asText();
    switch (eventName) {
        case "state" -> {
            JsonNode seats = data.path("seats");
            JsonNode hand = data.get("hand"); // optional: null when absent
            System.out.println(seats + " " + hand);
        }
        case "cards" -> {
            int n = data.path("n").asInt();
            JsonNode cards = data.path("cards");
            System.out.println(n + " " + cards);
        }
        default -> System.out.println(eventName);
    }
});
```

**Source:** `node/logic/tavern_poker.js:429-497` (`tavern_poker_state`), `node/logic/tavern_poker.js:501`, `node/logic/tavern_poker.js:510`, `node/logic/tavern_poker.js:733`.

## Events and misc

### `game_event`
A world event or boss appeared.

<!-- schema -->

**Notes:**

- `spawn_special_monster` also has a `game_event` for `tiger` (`node/server_functions.js:2133`). No live code spawns a tiger, because its `eventmap` line is a comment (`node/server_functions.js:2646`).
- The emits for `goldenbat` and `goldenbot` are comments (`node/server_functions.js:2163`, `node/server_functions.js:2177`). `cutebee`, `manyeye`, `mimic` and `paledino` spawn without a `game_event`.
- **Server bug:** `dragold` spawns in the box `[1018, -940, 1385, -624]` on `cave`, but the event sends `x: 900, y: -800`. These are the values of `snowman` (`node/server_functions.js:2066-2070`).
- The [S object](#s-shape) also shows each boss, with its live position and HP.

**Example:**

```js
// sock: a connected AlSocket
// A world event or boss appeared.
sock.on("game_event", (data) => {
  console.log(data.name, data.map, data.x, data.y);
});
```

```ts
// A world event or boss appeared.
interface GameEventPayload {
  name: string;
  map: string;
  x?: number;
  y?: number;
}
sock.on<GameEventPayload>("game_event", (data) => {
  console.log(data.name, data.map, data.x, data.y);
});
```

```python
# A world event or boss appeared.
def on_game_event(data: dict) -> None:
    print(data["name"], data["map"], data.get("x"), data.get("y"))

sock.on("game_event", on_game_event)
```

```go
// A world event or boss appeared.
type GameEventPayload struct {
	Name string  `json:"name"`
	Map  string  `json:"map"`
	X    float64 `json:"x"` // optional
	Y    float64 `json:"y"` // optional
}
sock.On("game_event", func(raw json.RawMessage) {
	var data GameEventPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name, data.Map, data.X, data.Y)
})
```

```csharp
// A world event or boss appeared.
sock.On("game_event", data =>
{
    string? name = data.GetProperty("name").GetString();
    string? map = data.GetProperty("map").GetString();
    double? x = data.TryGetProperty("x", out var xEl) ? xEl.GetDouble() : null;
    double? y = data.TryGetProperty("y", out var yEl) ? yEl.GetDouble() : null;
    Console.WriteLine($"{name} {map} {x} {y}");
});
```

```rust
// A world event or boss appeared.
sock.on("game_event", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    let map = data["map"].as_str().unwrap_or_default();
    let x = data["x"].as_f64(); // optional
    let y = data["y"].as_f64(); // optional
    println!("{name} {map} {x:?} {y:?}");
});
```

```java
// A world event or boss appeared.
sock.on("game_event", data -> {
    String name = data.path("name").asText();
    String map = data.path("map").asText();
    JsonNode x = data.get("x"); // optional: null when absent
    JsonNode y = data.get("y"); // optional: null when absent
    System.out.println(name + " " + map + " " + x + " " + y);
});
```

**Source:** `node/server_functions.js:2017-2148`.

### `server_info`
The server sends its event state S (`E` in the code) each time it changes and every 24 s. S holds boss timers, duels, `abtesting`, `goobrawl` and holidays.

<!-- schema -->

**Notes:**

- Each `server_info` replaces your copy of S. The page [S: server-wide event state](#s-what-s-is) documents every key, when it appears, and the event lifecycles.
- `welcome` (`S`) and `start` (`s_info`) carry the same object. On HARDCORE servers, `hardcore_info` also carries it.
- **Server bug:** each duel in `duels` loses `active` and `seconds` after its first pass of the duel loop. The loop copies them from `instance.active` and `instance.seconds`, which do not exist (`node/server_functions.js:3009-3010`).

**Example:**

```js
// sock: a connected AlSocket
// The event state E. Its keys depend on the active events.
sock.on("server_info", (data) => {
  console.log(data);
});
```

```ts
// The event state E. Its keys depend on the active events.
sock.on("server_info", (data) => {
  console.log(data);
});
```

```python
# The event state E. Its keys depend on the active events.
def on_server_info(data: object) -> None:
    print(data)

sock.on("server_info", on_server_info)
```

```go
// The event state E. Its keys depend on the active events.
sock.On("server_info", func(raw json.RawMessage) {
	fmt.Println(string(raw))
})
```

```csharp
// The event state E. Its keys depend on the active events.
sock.On("server_info", data =>
{
    Console.WriteLine(data.GetRawText());
});
```

```rust
// The event state E. Its keys depend on the active events.
sock.on("server_info", |data| {
    println!("{data}");
});
```

```java
// The event state E. Its keys depend on the active events.
sock.on("server_info", data -> {
    System.out.println(data);
});
```

**Source:** `node/server_functions.js:3028-3032`, `node/server_functions.js:3495-3496`.

### `achievement_success`
The player completed an achievement.

<!-- schema -->

**Notes:**

- The `upgrade` and `compound` handlers roll the result when they receive the request. Thus `"lucky"` or `"unlucky"` arrives at once, before the timer ends and before `q_data` or the hitchhiker result.
- `"unlucky"` is not a key of `G.achievements`. The server counts it in `player.p.achievements` all the same.
- The counter `"reflector"` (`node/server.js:3797`, `node/server.js:3800`) never sends anything: it is not in `G.achievements`, so `item_achievement_increment` returns at once (`node/server_functions.js:5847-5849`).

**Example:**

```js
// sock: a connected AlSocket
// An achievement is complete.
sock.on("achievement_success", (data) => {
  console.log(data.name);
});
```

```ts
// An achievement is complete.
interface AchievementSuccessPayload {
  name: string;
}
sock.on<AchievementSuccessPayload>("achievement_success", (data) => {
  console.log(data.name);
});
```

```python
# An achievement is complete.
def on_achievement_success(data: dict) -> None:
    print(data["name"])

sock.on("achievement_success", on_achievement_success)
```

```go
// An achievement is complete.
type AchievementSuccessPayload struct {
	Name string `json:"name"`
}
sock.On("achievement_success", func(raw json.RawMessage) {
	var data AchievementSuccessPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name)
})
```

```csharp
// An achievement is complete.
sock.On("achievement_success", data =>
{
    string? name = data.GetProperty("name").GetString();
    Console.WriteLine($"{name}");
});
```

```rust
// An achievement is complete.
sock.on("achievement_success", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    println!("{name}");
});
```

```java
// An achievement is complete.
sock.on("achievement_success", data -> {
    String name = data.path("name").asText();
    System.out.println(name);
});
```

**Source:** `node/server_functions.js:5841-5844`.

### `achievement_progress`
Progress on the achievement counter of an equipped item. The server sends it each time the count goes past a multiple of the `rr` step of the achievement.

<!-- schema -->

**Notes:**

- The counter is on the item (`item.ach`, `item.acc`), not on the character. When the count reaches `needed`, the server sends [`achievement_success`](#recv-achievement_success) instead and gives the item the title as its `p` property.
- Only `gooped` has an `rr` step (40,000) in G 17478. The other achievements send an event for each step of 1.

**Example:**

```js
// sock: a connected AlSocket
// Progress toward an achievement.
sock.on("achievement_progress", (data) => {
  console.log(data.name, data.count, data.needed);
});
```

```ts
// Progress toward an achievement.
interface AchievementProgressPayload {
  name: string;
  count: number;
  needed: number;
}
sock.on<AchievementProgressPayload>("achievement_progress", (data) => {
  console.log(data.name, data.count, data.needed);
});
```

```python
# Progress toward an achievement.
def on_achievement_progress(data: dict) -> None:
    print(data["name"], data["count"], data["needed"])

sock.on("achievement_progress", on_achievement_progress)
```

```go
// Progress toward an achievement.
type AchievementProgressPayload struct {
	Name   string  `json:"name"`
	Count  float64 `json:"count"`
	Needed float64 `json:"needed"`
}
sock.On("achievement_progress", func(raw json.RawMessage) {
	var data AchievementProgressPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Name, data.Count, data.Needed)
})
```

```csharp
// Progress toward an achievement.
sock.On("achievement_progress", data =>
{
    string? name = data.GetProperty("name").GetString();
    double count = data.GetProperty("count").GetDouble();
    double needed = data.GetProperty("needed").GetDouble();
    Console.WriteLine($"{name} {count} {needed}");
});
```

```rust
// Progress toward an achievement.
sock.on("achievement_progress", |data| {
    let name = data["name"].as_str().unwrap_or_default();
    let count = data["count"].as_f64().unwrap_or(0.0);
    let needed = data["needed"].as_f64().unwrap_or(0.0);
    println!("{name} {count} {needed}");
});
```

```java
// Progress toward an achievement.
sock.on("achievement_progress", data -> {
    String name = data.path("name").asText();
    double count = data.path("count").asDouble();
    double needed = data.path("needed").asDouble();
    System.out.println(name + " " + count + " " + needed);
});
```

**Source:** `node/server_functions.js:5846-5870`.

### `hardcore_info`
The state and reward winners of a HARDCORE server.

<!-- schema -->

**Notes:**

- The server fills a reward slot only while `E.minutes` is not 0. Each slot goes to the first character only.
- The kill list has `goo`, so the server adds a slot `first_goo` that is not in the start list. `first_wabbit` is in the start list, but no kill fills it. The level list has the class `"wabbit"`, which no character has (`node/server_functions.js:5886`, `node/server_functions.js:5906`).
- When `minutes` reaches 0, the server mails the rewards and stops. The last `hardcore_info` follows the shutdown call (`node/server_functions.js:5681-5688`).

**Example:**

```js
// sock: a connected AlSocket
// `achiever` is set when a player reached a milestone.
sock.on("hardcore_info", (data) => {
  console.log(data.E, data.achiever);
});
```

```ts
// `achiever` is set when a player reached a milestone.
interface HardcoreInfoPayload {
  E: Record<string, unknown>;
  achiever?: string;
}
sock.on<HardcoreInfoPayload>("hardcore_info", (data) => {
  console.log(data.E, data.achiever);
});
```

```python
# `achiever` is set when a player reached a milestone.
def on_hardcore_info(data: dict) -> None:
    print(data["E"], data.get("achiever"))

sock.on("hardcore_info", on_hardcore_info)
```

```go
// `achiever` is set when a player reached a milestone.
type HardcoreInfoPayload struct {
	E        map[string]any `json:"E"`
	Achiever string         `json:"achiever"` // optional
}
sock.On("hardcore_info", func(raw json.RawMessage) {
	var data HardcoreInfoPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.E, data.Achiever)
})
```

```csharp
// `achiever` is set when a player reached a milestone.
sock.On("hardcore_info", data =>
{
    JsonElement e = data.GetProperty("E");
    string? achiever = data.TryGetProperty("achiever", out var achieverEl) ? achieverEl.GetString() : null;
    Console.WriteLine($"{e} {achiever}");
});
```

```rust
// `achiever` is set when a player reached a milestone.
sock.on("hardcore_info", |data| {
    let e = &data["E"];
    let achiever = data["achiever"].as_str(); // optional
    println!("{e} {achiever:?}");
});
```

```java
// `achiever` is set when a player reached a milestone.
sock.on("hardcore_info", data -> {
    JsonNode e = data.path("E");
    String achiever = data.path("achiever").asText(null); // optional
    System.out.println(e + " " + achiever);
});
```

**Source:** `node/server_functions.js:5670-5689`, `node/server_functions.js:5882-5976`.

### `tracker`
The kill statistics of the character and the drop tables of the server, for the tracker UI.

<!-- schema -->

**Notes:**

- The character needs a `tracker` or a `supercomputer` in the inventory (`node/server.js:1464-1469`). Without one, the server does not reply.
- The handler always sends every drop table. Two branches limit the tables to 100 or more kills or exchanges. They are dead code, because their conditions contain `player.computer || 1` (`node/server.js:5467`, `node/server.js:5503-5507`).
- The tables are the live tables of the server, after the changes at server start (`sprocess_game_data`). Thus they can differ from `design/drops.js`, for example on HARDCORE servers (`node/server_functions.js:77-127`).
- The payload is large: it has the drop table of every monster and every exchange item.

**Example:**

```js
// sock: a connected AlSocket
// Kill and drop statistics.
sock.on("tracker", (data) => {
  console.log(data.monsters, data.drops, data.max);
});
```

```ts
// Kill and drop statistics.
interface TrackerPayload {
  monsters: Record<string, unknown>;
  drops: Record<string, unknown>;
  max: Record<string, unknown>;
}
sock.on<TrackerPayload>("tracker", (data) => {
  console.log(data.monsters, data.drops, data.max);
});
```

```python
# Kill and drop statistics.
def on_tracker(data: dict) -> None:
    print(data["monsters"], data["drops"], data["max"])

sock.on("tracker", on_tracker)
```

```go
// Kill and drop statistics.
type TrackerPayload struct {
	Monsters map[string]any `json:"monsters"`
	Drops    map[string]any `json:"drops"`
	Max      map[string]any `json:"max"`
}
sock.On("tracker", func(raw json.RawMessage) {
	var data TrackerPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Monsters, data.Drops, data.Max)
})
```

```csharp
// Kill and drop statistics.
sock.On("tracker", data =>
{
    JsonElement monsters = data.GetProperty("monsters");
    JsonElement drops = data.GetProperty("drops");
    JsonElement max = data.GetProperty("max");
    Console.WriteLine($"{monsters} {drops} {max}");
});
```

```rust
// Kill and drop statistics.
sock.on("tracker", |data| {
    let monsters = &data["monsters"];
    let drops = &data["drops"];
    let max = &data["max"];
    println!("{monsters} {drops} {max}");
});
```

```java
// Kill and drop statistics.
sock.on("tracker", data -> {
    JsonNode monsters = data.path("monsters");
    JsonNode drops = data.path("drops");
    JsonNode max = data.path("max");
    System.out.println(monsters + " " + drops + " " + max);
});
```

**Source:** `node/server.js:5440-5522`.

### `track`
The result of the ranger skill `track`.

<!-- schema -->

**Notes:**

- The array can be empty. The entries have no names and no positions.
- The skill sees invisible characters: they are in the list with `invis: true`.

**Example:**

```js
// sock: a connected AlSocket
// Sorted by distance. The entries have no names.
sock.on("track", (data) => {
  for (const t of data) console.log(t.sound, t.dist, t.invis);
});
```

```ts
// Sorted by distance. The entries have no names.
interface TrackEntry {
  sound: string;
  dist: number;
  invis?: boolean;
}
sock.on<TrackEntry[]>("track", (data) => {
  for (const t of data) console.log(t.sound, t.dist, t.invis);
});
```

```python
# Sorted by distance. The entries have no names.
def on_track(data: list) -> None:
    for t in data:
        print(t["sound"], t["dist"], t.get("invis"))

sock.on("track", on_track)
```

```go
// Sorted by distance. The entries have no names.
type TrackEntry struct {
	Sound string  `json:"sound"`
	Dist  float64 `json:"dist"`
	Invis bool    `json:"invis"` // optional
}
sock.On("track", func(raw json.RawMessage) {
	var data []TrackEntry
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	for _, t := range data {
		fmt.Println(t.Sound, t.Dist, t.Invis)
	}
})
```

```csharp
// Sorted by distance. The entries have no names.
sock.On("track", data =>
{
    foreach (JsonElement t in data.EnumerateArray())
    {
        string? sound = t.GetProperty("sound").GetString();
        double dist = t.GetProperty("dist").GetDouble();
        bool? invis = t.TryGetProperty("invis", out var invisEl) ? invisEl.GetBoolean() : null;
        Console.WriteLine($"{sound} {dist} {invis}");
    }
});
```

```rust
// Sorted by distance. The entries have no names.
sock.on("track", |data| {
    for t in data.as_array().into_iter().flatten() {
        let sound = t["sound"].as_str().unwrap_or_default();
        let dist = t["dist"].as_f64().unwrap_or(0.0);
        let invis = t["invis"].as_bool(); // optional
        println!("{sound} {dist} {invis:?}");
    }
});
```

```java
// Sorted by distance. The entries have no names.
sock.on("track", data -> {
    for (JsonNode t : data) {
        String sound = t.path("sound").asText();
        double dist = t.path("dist").asDouble();
        JsonNode invis = t.get("invis"); // optional: null when absent
        System.out.println(sound + " " + dist + " " + invis);
    }
});
```

**Source:** `node/server.js:10576-10606`.

### `cave`
State of a Cave of Many Dreams run (a generated dungeon for a party).

<!-- schema -->

**Notes:**

- Every form carries a full `state`. The examples in the table above show `state` with only some of its keys. [`CaveState`](#type-cavestate) has a full example.
- `state` is per character: `floor`, `doors` and `objectives` follow your floor, and `choice` can be the vote of the room that you talked to.
- The [`interaction`](#send-interaction) replies of the cave (`state`, `talk`, `vote`, `buy`, `exit`) are separate from this event. The `state` action returns the same snapshot.
- While a vote is open, the server pauses the run: `paused` is `true` and `remaining_ms` does not go down. Most requests of the members get `cave_paused` (see [Every request](#guide-every-request)).

**Example:**

```js
// sock: a connected AlSocket
// The other fields depend on `type`.
sock.on("cave", (data) => {
  switch (data.type) {
    case "state":
      console.log(data.state);
      break;
    case "cue":
      console.log(data.cue);
      break;
    case "chat":
      console.log(data.chat);
      break;
    case "ended":
      console.log(data.reason);
      break;
    default:
      console.log(data.type);
  }
});
```

```ts
// The other fields depend on `type`.
interface CavePayload {
  type: string;
  state?: Record<string, unknown>;
  cue?: Record<string, unknown>;
  chat?: Record<string, unknown>;
  reason?: string;
}
sock.on<CavePayload>("cave", (data) => {
  switch (data.type) {
    case "state":
      console.log(data.state);
      break;
    case "cue":
      console.log(data.cue);
      break;
    case "chat":
      console.log(data.chat);
      break;
    case "ended":
      console.log(data.reason);
      break;
    default:
      console.log(data.type);
  }
});
```

```python
# The other fields depend on `type`.
def on_cave(data: dict) -> None:
    match data["type"]:
        case "state":
            print(data["state"])
        case "cue":
            print(data["cue"])
        case "chat":
            print(data["chat"])
        case "ended":
            print(data["reason"])
        case _:
            print(data["type"])

sock.on("cave", on_cave)
```

```go
// The other fields depend on `type`.
type CavePayload struct {
	Type   string         `json:"type"`
	State  map[string]any `json:"state"`
	Cue    map[string]any `json:"cue"`
	Chat   map[string]any `json:"chat"`
	Reason string         `json:"reason"`
}
sock.On("cave", func(raw json.RawMessage) {
	var data CavePayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	switch data.Type {
	case "state":
		fmt.Println(data.State)
	case "cue":
		fmt.Println(data.Cue)
	case "chat":
		fmt.Println(data.Chat)
	case "ended":
		fmt.Println(data.Reason)
	default:
		fmt.Println(data.Type)
	}
})
```

```csharp
// The other fields depend on `type`.
sock.On("cave", data =>
{
    string? typeName = data.GetProperty("type").GetString();
    switch (typeName)
    {
        case "state":
        {
            JsonElement state = data.GetProperty("state");
            Console.WriteLine($"{state}");
            break;
        }
        case "cue":
        {
            JsonElement cue = data.GetProperty("cue");
            Console.WriteLine($"{cue}");
            break;
        }
        case "chat":
        {
            JsonElement chat = data.GetProperty("chat");
            Console.WriteLine($"{chat}");
            break;
        }
        case "ended":
        {
            string? reason = data.GetProperty("reason").GetString();
            Console.WriteLine($"{reason}");
            break;
        }
        default:
            Console.WriteLine(typeName);
            break;
    }
});
```

```rust
// The other fields depend on `type`.
sock.on("cave", |data| {
    match data["type"].as_str().unwrap_or_default() {
        "state" => {
            let state = &data["state"];
            println!("{state}");
        }
        "cue" => {
            let cue = &data["cue"];
            println!("{cue}");
        }
        "chat" => {
            let chat = &data["chat"];
            println!("{chat}");
        }
        "ended" => {
            let reason = data["reason"].as_str().unwrap_or_default();
            println!("{reason}");
        }
        other => println!("{other}"),
    }
});
```

```java
// The other fields depend on `type`.
sock.on("cave", data -> {
    String typeName = data.path("type").asText();
    switch (typeName) {
        case "state" -> {
            JsonNode state = data.path("state");
            System.out.println(state);
        }
        case "cue" -> {
            JsonNode cue = data.path("cue");
            System.out.println(cue);
        }
        case "chat" -> {
            JsonNode chat = data.path("chat");
            System.out.println(chat);
        }
        case "ended" -> {
            String reason = data.path("reason").asText();
            System.out.println(reason);
        }
        default -> System.out.println(typeName);
    }
});
```

**Source:** `node/logic/cave_of_many_dreams.js:1717-1887`, `node/logic/generated_maps.js:230-240`.

### `gm`
The reply to a GM-only `gm` request with `action: "jump_list"`.

<!-- schema -->

**Notes:** the `server_info` action of `gm` does not send anything, because its emit is a comment (`node/server.js:5392`).

**Example:**

```js
// sock: a connected AlSocket
// GM only: the names of all players on the server.
sock.on("gm", (data) => {
  console.log(data.action, data.ids);
});
```

```ts
// GM only: the names of all players on the server.
interface GmPayload {
  action: "jump_list";
  ids: string[];
}
sock.on<GmPayload>("gm", (data) => {
  console.log(data.action, data.ids);
});
```

```python
# GM only: the names of all players on the server.
def on_gm(data: dict) -> None:
    print(data["action"], data["ids"])

sock.on("gm", on_gm)
```

```go
// GM only: the names of all players on the server.
type GmPayload struct {
	Action string   `json:"action"`
	Ids    []string `json:"ids"`
}
sock.On("gm", func(raw json.RawMessage) {
	var data GmPayload
	if err := json.Unmarshal(raw, &data); err != nil {
		return
	}
	fmt.Println(data.Action, data.Ids)
})
```

```csharp
// GM only: the names of all players on the server.
sock.On("gm", data =>
{
    string? action = data.GetProperty("action").GetString();
    JsonElement ids = data.GetProperty("ids");
    Console.WriteLine($"{action} {ids}");
});
```

```rust
// GM only: the names of all players on the server.
sock.on("gm", |data| {
    let action = data["action"].as_str().unwrap_or_default();
    let ids = &data["ids"];
    println!("{action} {ids}");
});
```

```java
// GM only: the names of all players on the server.
sock.on("gm", data -> {
    String action = data.path("action").asText();
    JsonNode ids = data.path("ids");
    System.out.println(action + " " + ids);
});
```

**Source:** `node/server.js:5381-5386`.

### Events the official client listens for but the server never sends
`end`, `frequest`, `fx`, `game_chat_log`, `reopen` and `requesting_ack` have handlers in `js/game.js`. The live server code in `node/` never sends them. The client `reopen` behavior comes from `player.reopen` instead.

`bet` has an emit in the server, but no client can receive it. The roulette branch of the `bet` handler sends `bet` `{name, type: "roulette", odds, gold}` to the socket.io room `"roulette"` (`node/server.js:12783-12786`). That branch returns at once unless the server is a dev server (`node/server.js:12737-12740`). No code in `node/` puts a socket in the room `"roulette"`, so the room is always empty.
