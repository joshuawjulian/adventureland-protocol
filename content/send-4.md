### `trade`
Shows or hides four trade slots (`trade1` to `trade4`) for any character, with no merchant stand.

<!-- schema -->

**Notes:**
- The handler has no class check and no stand check. While a merchant stand is open, the stand decides the trade slots (`get_trade_slots`, node/server_functions.js:4282-4298). A stand has 16 slots. A merchant at level 70 (or with a `cstand`) has 24, and at level 80 has 30. Then `p.trades` changes nothing that you can see.
- The `u` flag of the resend marks your character as changed. Clients nearby see the new slots in the next entity update.

**Example:**

```js
// sock: a connected AlSocket
// No game_response: the reply is a `player` update with the new slots.
const update = sock.waitFor("player", undefined, 5000);
sock.emit("trade", { event: "show" });
const me = await update;
console.log(Object.keys(me.slots).filter((k) => k.startsWith("trade")));
```

```ts
// sock: a connected AlSocket
interface PlayerUpdate { slots: Record<string, { name: string; price?: number } | null> }
// No game_response: the reply is a `player` update with the new slots.
const update = sock.waitFor<PlayerUpdate>("player", undefined, 5000);
sock.emit("trade", { event: "show" });
const me = await update;
console.log(Object.keys(me.slots).filter((k) => k.startsWith("trade")));
```

```python
# sock: a connected AlSocket
# No game_response: the reply is a `player` update with the new slots.
update = sock.wait_for("player", timeout=5)
await sock.emit("trade", {"event": "show"})
me = await update
print([k for k in me["slots"] if k.startswith("trade")])
```

```go
// sock: a connected *alsocket.Socket. Expect registers the wait before the emit.
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
wait := sock.Expect("player", nil) // registers now, before the emit
// No game_response: the reply is a `player` update with the new slots.
sock.Emit("trade", map[string]any{"event": "show"})
reply, err := wait(ctx)
if err != nil {
	return // no reply in time
}
var me struct {
	Slots map[string]json.RawMessage `json:"slots"`
}
if json.Unmarshal(reply, &me) == nil {
	for k := range me.Slots {
		if strings.HasPrefix(k, "trade") {
			fmt.Println(k)
		}
	}
}
```

```csharp
// sock: a connected AlSocket. Start the wait before the emit, then await it.
// No game_response: the reply is a `player` update with the new slots.
var update = sock.WaitForAsync("player", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("trade", new { @event = "show" });
var me = await update;
foreach (var slot in me.GetProperty("slots").EnumerateObject())
    if (slot.Name.StartsWith("trade")) Console.WriteLine(slot.Name);
```

```rust
// sock: a connected AlSocket. Register the wait first, then emit.
// No game_response: the reply is a `player` update with the new slots.
let reply = sock.wait_for("player", |_| true);
sock.emit("trade", json!({"event": "show"})).await?;
let me = reply.await?;
if let Some(slots) = me["slots"].as_object() {
    let trade: Vec<&String> = slots.keys().filter(|k| k.starts_with("trade")).collect();
    println!("{trade:?}");
}
```

```java
// sock: a connected AlSocket. waitFor registers at once; get() blocks for the reply.
// No game_response: the reply is a `player` update with the new slots.
var update = sock.waitFor("player", d -> true, Duration.ofSeconds(5));
sock.emit("trade", Map.of("event", "show"));
JsonNode me = update.get();
me.path("slots").fieldNames().forEachRemaining(k -> {
    if (k.startsWith("trade")) System.out.println(k);
});
```

**Source:** `node/server.js:12567`, `node/server_functions.js:4301` (`reslot_player`)

### `signup`
Puts your character on the list for the next server event.

<!-- schema -->

**Notes:** `collect_signups` reads the `signups` object when an event starts. For `abtesting`, it uses the list to assign teams.

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("game_response", (r) => r?.response === "signed_up", 5000);
sock.emit("signup", {});
await reply; // {response: "signed_up"}: no place, no other field
```

```ts
interface SignedUp { response: "signed_up" } // no place, no other field
const reply = sock.waitFor<SignedUp>("game_response", (r) => r?.response === "signed_up", 5000);
sock.emit("signup", {});
const r = await reply;
console.log(r.response);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("response") == "signed_up", timeout=5)
await sock.emit("signup", {})
await reply  # {"response": "signed_up"}: no place, no other field
```

```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
signedUp := func(d json.RawMessage) bool {
	var r struct{ Response string }
	return json.Unmarshal(d, &r) == nil && r.Response == "signed_up" // no place, no other field
}
wait := sock.Expect("game_response", signedUp) // registers now, before the emit
sock.Emit("signup", map[string]any{})
reply, err := wait(ctx)
if err != nil {
	return // no reply in time
}
fmt.Println(string(reply))
```

```csharp
var reply = sock.WaitForAsync("game_response",
    r => r.ValueKind == JsonValueKind.Object && r.TryGetProperty("response", out var c) && c.GetString() == "signed_up",
    TimeSpan.FromSeconds(5));
await sock.EmitAsync("signup", new { });
await reply; // {"response": "signed_up"}: no place, no other field
```

```rust
let reply = sock.wait_for("game_response", |r| r["response"] == "signed_up");
sock.emit("signup", json!({})).await?;
let r = reply.await?; // {"response": "signed_up"}: no place, no other field
println!("{}", r["response"]);
```

```java
var reply = sock.waitFor("game_response", r -> r.path("response").asText().equals("signed_up"), Duration.ofSeconds(5));
sock.emit("signup", Map.of());
reply.get(); // {"response": "signed_up"}: no place, no other field
```

**Source:** `node/server.js:12582`, `node/server_functions.js:2213` (`collect_signups`)

### `join`
Moves you to an active server event: goobrawl, crabxx, franky, icegolem or abtesting.

<!-- schema -->

**Notes:**
- The destinations (node/server.js:12607-12647):

  | Event | Destination | The server moves you if |
  |---|---|---|
  | goobrawl | the `goobrawl` map, spawn 0 | you are on a different map |
  | crabxx | `main` at (-1000, 1700) | you are more than 200 px away |
  | franky | `level2w` at (-300, 150) | you are more than 200 px away |
  | icegolem | `winterland` at (820, 425) | you are more than 100 px away |
  | abtesting | spawn 2 (team A) or spawn 3 (team B) of `abtesting` | you are not on the `abtesting` map with a team |

- abtesting: you get your saved team for this abtesting id, or a random `"A"` or `"B"`. The server saves it in `p.abtesting = [id, team]` and calls `save_state`.
- When no move is necessary, you get only the success reply.
- In a generated map (a dream cave), `transport_player_to` refuses the move (node/server.js:4647). You still get the success reply.

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("game_response", (r) => r?.place === "join", 5000);
sock.emit("join", { name: "goobrawl" });
const r = await reply;
if (r.failed) console.log("join failed:", r.response); // "cant_join", "no_merchants", ...
else console.log("joined"); // a `new_map` arrives too if the server moved you
```

```ts
interface JoinReply { response: string; place: "join"; failed?: true; success?: true }
const reply = sock.waitFor<JoinReply>("game_response", (r) => r?.place === "join", 5000);
sock.emit("join", { name: "goobrawl" });
const r = await reply;
if (r.failed) console.log("join failed:", r.response); // "cant_join", "no_merchants", ...
else console.log("joined"); // a `new_map` arrives too if the server moved you
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "join", timeout=5)
await sock.emit("join", {"name": "goobrawl"})
r = await reply
if r.get("failed"):
    print("join failed:", r["response"])  # "cant_join", "no_merchants", ...
else:
    print("joined")  # a `new_map` arrives too if the server moved you
```

```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
isJoin := func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "join"
}
wait := sock.Expect("game_response", isJoin) // registers now, before the emit
sock.Emit("join", map[string]any{"name": "goobrawl"})
reply, err := wait(ctx)
if err != nil {
	return // no reply in time
}
var r struct {
	Response string
	Failed   bool
}
if json.Unmarshal(reply, &r) == nil && r.Failed {
	fmt.Println("join failed:", r.Response) // "cant_join", "no_merchants", ...
} // on success, a `new_map` arrives too if the server moved you
```

```csharp
var reply = sock.WaitForAsync("game_response",
    r => r.ValueKind == JsonValueKind.Object && r.TryGetProperty("place", out var p) && p.GetString() == "join",
    TimeSpan.FromSeconds(5));
await sock.EmitAsync("join", new { name = "goobrawl" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"join failed: {r.GetProperty("response")}"); // "cant_join", "no_merchants", ...
else
    Console.WriteLine("joined"); // a `new_map` arrives too if the server moved you
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "join");
sock.emit("join", json!({"name": "goobrawl"})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("join failed: {}", r["response"]); // "cant_join", "no_merchants", ...
} else {
    println!("joined"); // a `new_map` arrives too if the server moved you
}
```

```java
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("join"), Duration.ofSeconds(5));
sock.emit("join", Map.of("name", "goobrawl"));
JsonNode r = reply.get();
if (r.path("failed").asBoolean())
    System.out.println("join failed: " + r.path("response").asText()); // "cant_join", "no_merchants", ...
else
    System.out.println("joined"); // a `new_map` arrives too if the server moved you
```

**Source:** `node/server.js:12593`, `node/server_functions.js:3421` (`success_response`)

### `stop`
Cancels an action in progress: stealth (invis), a channel, a town teleport or a revival.

<!-- schema -->

**Notes:**
- An unknown `action`, or nothing to cancel, is not an error. You still get the success reply.
- The `stop` event also works while the server pauses your instance (`node/logic/instance_pause.js:96`).

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("game_response", (r) => r?.place === "stop", 5000);
sock.emit("stop", { action: "town" });
await reply; // always {response: "data", place: "stop", success: true}
```

```ts
interface StopReply { response: "data"; place: "stop"; success: true }
const reply = sock.waitFor<StopReply>("game_response", (r) => r?.place === "stop", 5000);
sock.emit("stop", { action: "town" });
const r = await reply; // the server never fails this event
console.log(r.success);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "stop", timeout=5)
await sock.emit("stop", {"action": "town"})
await reply  # always {"response": "data", "place": "stop", "success": True}
```

```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
isStop := func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "stop"
}
wait := sock.Expect("game_response", isStop) // registers now, before the emit
sock.Emit("stop", map[string]any{"action": "town"})
reply, err := wait(ctx)
if err != nil {
	return // no reply in time
}
fmt.Println(string(reply)) // always {"response": "data", "place": "stop", "success": true}
```

```csharp
var reply = sock.WaitForAsync("game_response",
    r => r.ValueKind == JsonValueKind.Object && r.TryGetProperty("place", out var p) && p.GetString() == "stop",
    TimeSpan.FromSeconds(5));
await sock.EmitAsync("stop", new { action = "town" });
await reply; // always {"response": "data", "place": "stop", "success": true}
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "stop");
sock.emit("stop", json!({"action": "town"})).await?;
reply.await?; // always {"response": "data", "place": "stop", "success": true}
```

```java
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("stop"), Duration.ofSeconds(5));
sock.emit("stop", Map.of("action", "town"));
reply.get(); // always {"response": "data", "place": "stop", "success": true}
```

**Source:** `node/server.js:12656`, `node/server.js:13756` (`step_out_of_invis`)

### `tarot`
An unfinished tarot reading at the `twitch` NPC. It checks the distance and your tarot conditions, then does nothing.

<!-- schema -->

**Notes:**
- G has a `games.tarot` definition (NPC `twitch`, 78 cards, `hours: 23`), but no server code uses it. The code that makes tarot conditions is only a comment (`design/conditions.js:866`).
- With G version 17478, no map lists a `twitch` NPC. Thus every call with a character gets `"distance"`, and `tarot_exists` does not occur.

**Example:**

```js
// tarot is unfinished: when the checks pass, the server sends nothing.
```

```ts
// tarot is unfinished: when the checks pass, the server sends nothing.
```

```python
# tarot is unfinished: when the checks pass, the server sends nothing.
```

```go
// tarot is unfinished: when the checks pass, the server sends nothing.
```

```csharp
// tarot is unfinished: when the checks pass, the server sends nothing.
```

```rust
// tarot is unfinished: when the checks pass, the server sends nothing.
```

```java
// tarot is unfinished: when the checks pass, the server sends nothing.
```

**Source:** `node/server.js:12697`, `design/games.js:2`

### `bet`
Places a wager in the tavern: dice, Fortune's Wheel (`"wheel"`), slots, or roulette (dev servers only).

<!-- schema -->

**Limits:**

| Game | Stake | At one time |
|---|---|---|
| dice | 10,000–100,000,000,000 gold; the net win is at most 40% of `S.gold - house_debt()` | 1 active bet |
| wheel | 10,000–100,000,000,000 gold; the net win is at most 40% of `S.gold - house_debt()` | 1 spin until it settles (4 s) |
| slots | 1,000,000 gold per pull | 1 pull until it settles (3.6 s) |
| roulette | 1 gold or more | 5 active bets |

**Notes:**
- dice odds: `100/num` for `"down"` and `100/(100-num)` for `"up"`. The server caps them at 10,000 and cuts them to 2 decimals. `win` is `parseInt(gold * odds)`. `edge` is `ceil((gold * odds - gold) * house_edge() / 100)` (node/server.js:12794-12806).
- The dice round runs in `tavern_loop`, once each second. The table takes bets for 30 s, then rolls. 10 s later the server settles the gold (`lock`). 1.6 s later each player gets the result. 2 s later the next round opens (node/server_functions.js:1405-1592).
- A merchant that wins a dice bet also gets `edge * 7.2` XP (node/server_functions.js:1437-1439).
- wheel and slots decide the result when the server takes the stake. The `ui` event (`index`, `stops`) and `q.wheel` or `q.slots` in the `player` update show it before the animation ends.
- If you disconnect, the server returns your open dice stakes. A wheel spin or slots pull settles at once with no messages.
- If a restart starts, `tavern_close` returns every unsettled stake (the Refund reply and the refund events in Also sent).
- On `hardcore` servers, the server replaces the next roll with the last roll in 7% of rounds. It does this after it publishes `hex`. In those rounds, the `num` that the server reveals does not match the `text` behind the commitment (`node/server_functions.js:1589`).
- **Server bug:** the roulette loop has `&& 0` in its condition, so it never runs (`node/server_functions.js:1594`). A roulette bet never settles. You get the stake back only when you disconnect.

**Example:**

```js
// sock: a connected AlSocket
// With request_id, failures and the result are objects. The result comes after the roll (up to 45 s).
const id = "dice-1";
const reply = sock.waitFor("game_response", (r) => r?.request_id === id, 60000);
sock.emit("bet", { type: "dice", num: 50, dir: "up", gold: 100000, request_id: id });
const r = await reply;
if (r.failed) console.log("bet failed:", r.response); // "tavern_not_yet", "gold_not_enough", ...
else console.log(r.won ? "won" : "lost", "roll", r.roll, "net", r.net);
```

```ts
interface DiceResult {
  request_id: string; place: "dice"; response: string; failed?: true;
  won?: boolean; roll?: number; num?: number; direction?: string;
  wager?: number; payout?: number; net?: number; edge?: number;
}
// With request_id, failures and the result are objects. The result comes after the roll (up to 45 s).
const id = "dice-1";
const reply = sock.waitFor<DiceResult>("game_response", (r) => r?.request_id === id, 60000);
sock.emit("bet", { type: "dice", num: 50, dir: "up", gold: 100000, request_id: id });
const r = await reply;
if (r.failed) console.log("bet failed:", r.response); // "tavern_not_yet", "gold_not_enough", ...
else console.log(r.won ? "won" : "lost", "roll", r.roll, "net", r.net);
```

```python
# With request_id, failures and the result are objects. The result comes after the roll (up to 45 s).
rid = "dice-1"
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("request_id") == rid, timeout=60)
await sock.emit("bet", {"type": "dice", "num": 50, "dir": "up", "gold": 100000, "request_id": rid})
r = await reply
if r.get("failed"):
    print("bet failed:", r["response"])  # "tavern_not_yet", "gold_not_enough", ...
else:
    print("won" if r["won"] else "lost", "roll", r["roll"], "net", r["net"])
```

```go
// With request_id, failures and the result are objects. The result comes after the roll (up to 45 s).
ctx, cancel := context.WithTimeout(ctx, 60*time.Second)
defer cancel()
type DiceResult struct {
	RequestID string `json:"request_id"`
	Response  string
	Failed    bool
	Won       bool
	Roll, Net float64
}
mine := func(d json.RawMessage) bool {
	var r DiceResult
	return json.Unmarshal(d, &r) == nil && r.RequestID == "dice-1"
}
wait := sock.Expect("game_response", mine) // registers now, before the emit
sock.Emit("bet", map[string]any{"type": "dice", "num": 50, "dir": "up", "gold": 100000, "request_id": "dice-1"})
reply, err := wait(ctx)
if err != nil {
	return // no reply in time
}
var r DiceResult
if json.Unmarshal(reply, &r) != nil {
	return
}
if r.Failed {
	fmt.Println("bet failed:", r.Response) // "tavern_not_yet", "gold_not_enough", ...
} else {
	fmt.Println("won:", r.Won, "roll", r.Roll, "net", r.Net)
}
```

```csharp
// With request_id, failures and the result are objects. The result comes after the roll (up to 45 s).
const string id = "dice-1";
var reply = sock.WaitForAsync("game_response",
    r => r.ValueKind == JsonValueKind.Object && r.TryGetProperty("request_id", out var q) && q.GetString() == id,
    TimeSpan.FromSeconds(60));
await sock.EmitAsync("bet", new { type = "dice", num = 50, dir = "up", gold = 100000, request_id = id });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"bet failed: {r.GetProperty("response")}"); // "tavern_not_yet", "gold_not_enough", ...
else
    Console.WriteLine($"won: {r.GetProperty("won")} roll {r.GetProperty("roll")} net {r.GetProperty("net")}");
```

```rust
// With request_id, failures and the result are objects. The result comes after the roll (up to 45 s).
let reply = sock.wait_for_timeout("game_response", |r| r["request_id"] == "dice-1", Duration::from_secs(60));
sock.emit("bet", json!({"type": "dice", "num": 50, "dir": "up", "gold": 100000, "request_id": "dice-1"})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("bet failed: {}", r["response"]); // "tavern_not_yet", "gold_not_enough", ...
} else {
    println!("won: {} roll {} net {}", r["won"], r["roll"], r["net"]);
}
```

```java
// With request_id, failures and the result are objects. The result comes after the roll (up to 45 s).
String id = "dice-1";
var reply = sock.waitFor("game_response", r -> r.path("request_id").asText().equals(id), Duration.ofSeconds(60));
sock.emit("bet", Map.of("type", "dice", "num", 50, "dir", "up", "gold", 100000, "request_id", id));
JsonNode r = reply.get();
if (r.path("failed").asBoolean())
    System.out.println("bet failed: " + r.path("response").asText()); // "tavern_not_yet", "gold_not_enough", ...
else
    System.out.println("won: " + r.path("won") + " roll " + r.path("roll") + " net " + r.path("net"));
```

**Source:** `node/server.js:12712`, `node/logic/tavern_wheel.js:11` (`tavern_wheel_bet`), `node/logic/tavern_wheel.js:52` (settle), `node/logic/tavern_slots.js:32` (`tavern_slots_bet`), `node/logic/tavern_slots.js:71` (settle), `node/server_functions.js:1399` (`tavern_loop`, dice), `node/server_functions.js:1384` (`house_edge`), `node/logic/tavern.js:6` (`tavern_closing`), `design/games.js:10` (wheel and slots definitions)

### `tavern`
Gets the house edge and the largest net win that the house accepts now.

<!-- schema -->

**Notes:** The handler does not need a character.

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("tavern", (d) => d?.event === "info", 5000);
sock.emit("tavern", { event: "info" });
const info = await reply;
console.log("edge", info.edge, "% max net win", info.max);
```

```ts
interface TavernInfo { event: "info"; edge: number; max: number; game?: string }
const reply = sock.waitFor<TavernInfo>("tavern", (d) => d?.event === "info", 5000);
sock.emit("tavern", { event: "info" });
const info = await reply;
console.log("edge", info.edge, "% max net win", info.max);
```

```python
reply = sock.wait_for("tavern", lambda d: isinstance(d, dict) and d.get("event") == "info", timeout=5)
await sock.emit("tavern", {"event": "info"})
info = await reply
print("edge", info["edge"], "% max net win", info["max"])
```

```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
type TavernInfo struct {
	Event     string
	Edge, Max float64
}
isInfo := func(d json.RawMessage) bool {
	var t TavernInfo
	return json.Unmarshal(d, &t) == nil && t.Event == "info"
}
wait := sock.Expect("tavern", isInfo) // registers now, before the emit
sock.Emit("tavern", map[string]any{"event": "info"})
reply, err := wait(ctx)
if err != nil {
	return // no reply in time
}
var info TavernInfo
if json.Unmarshal(reply, &info) == nil {
	fmt.Println("edge", info.Edge, "% max net win", info.Max)
}
```

```csharp
var reply = sock.WaitForAsync("tavern",
    d => d.ValueKind == JsonValueKind.Object && d.TryGetProperty("event", out var e) && e.GetString() == "info",
    TimeSpan.FromSeconds(5));
await sock.EmitAsync("tavern", new { @event = "info" });
var info = await reply;
Console.WriteLine($"edge {info.GetProperty("edge")} % max net win {info.GetProperty("max")}");
```

```rust
let reply = sock.wait_for("tavern", |d| d["event"] == "info");
sock.emit("tavern", json!({"event": "info"})).await?;
let info = reply.await?;
println!("edge {} % max net win {}", info["edge"], info["max"]);
```

```java
var reply = sock.waitFor("tavern", d -> d.path("event").asText().equals("info"), Duration.ofSeconds(5));
sock.emit("tavern", Map.of("event", "info"));
JsonNode info = reply.get();
System.out.println("edge " + info.path("edge") + " % max net win " + info.path("max"));
```

**Source:** `node/server.js:12867`, `node/server_functions.js:1384` (`house_edge`), `node/server_functions.js:1364` (`house_debt`)

### `poker`
Sends one request to Tavern Hold'em, the five-seat no-limit Texas Hold'em table in the tavern.

<!-- schema -->

**Limits:** From `G.games.poker`:

| Rule | Value |
|---|---|
| Blinds | By server name: I 100,000/200,000; II 1,000,000/2,000,000; III 5,000,000/10,000,000. Other names use IV: 10,000,000/20,000,000. PvP servers use 100,000,000/200,000,000. |
| Buy-in | 40 to 200 big blinds |
| Rake | 2% of each awarded pot, maximum 10 big blinds per pot. An uncalled bet goes back with no rake. |
| Clock | 20 s per decision. Then a 30 s time bank, once per hand. Then the server checks for you if it can, or folds. |
| Seats | 5. One seat per account (`player.owner`). The stools are around the table at (-168, -52) on the `tavern` map. |
| Between hands | A hand starts when 2 or more seats are ready. It waits 3 s after a new seat and 10 s after a showdown. |

**Notes:**
- Players play against other players. The house keeps only the rake.
- The seat keeps a copy of the stack in `player.p.poker`. If the server stops without a cash-out, your next login returns that stack.
- If a hand still runs on a different live server, the login fails with `game_error` "Your poker hand is still running on another server ..." (`poker_hand_active`).
- At a restart, the server cancels the current hand and returns every chip in it with no rake. Then it cashes out all seats.
- The dealer NPC Venn sends animations and lines to nearby clients as `citizen` events with `type: "dealer"`.
- The hand runs on a 1 s tick (`tavern_poker_tick`, node/logic/tavern_poker.js:1242-1281):
  1. Before the deal, the server saves every stack in one transaction. The button moves clockwise. Heads-up, the button posts the small blind and acts first before the flop.
  2. The server shuffles with `crypto.randomInt`. `commit` is the HMAC-SHA256 of the deck order (joined with `","`) with a random `key`. After the hand, `key` and `order` let a client check `commit`.
  3. The streets are preflop, flop, turn and river. After the last decision of a street, the next street comes 0.8 s later. If only one player can act, it comes 2.5 s later.
  4. At showdown, the server makes a side pot for each all-in level. Ties split the pot. Odd gold goes to the winners nearest after the button.
  5. The server saves all awards in one transaction. Then `hand.results` shows the winners, the returned gold, the hand names and the shown cards.
- A seat leaves the table in these cases. The stack then goes back to your gold, with `game_log` `poker_cash_out`.
  - You send `leave`.
  - You move more than 60 px from your stool, 12 s or more after you sat down. The seat leaves after the hand.
  - You disconnect, and 5 min pass. The seat stays in the next 2 hands and plays them by the clock, then sits out. When you log in again in time, you get `game_log` `poker_back` and the table state.
  - The seat sits out for more than 5 min. A seat with less than one big blind sits out after the hand.

**Example:**

```js
// sock: a connected AlSocket
// Every reply is a game_response with place "poker". request_id tells the replies apart.
const joined = sock.waitFor("game_response", (r) => r?.request_id === "join-1", 5000);
sock.emit("poker", { event: "join", gold: 20000000, request_id: "join-1" });
const j = await joined;
if (j.failed) return console.log("join failed:", j.response, j.min ?? "", j.max ?? "");
console.log("seat", j.seat, "stack", j.stack, "blinds", j.blinds);

// Later, when the `poker` state shows hand.acting === j.seat:
const acted = sock.waitFor("game_response", (r) => r?.request_id === "act-1", 5000);
sock.emit("poker", { event: "act", action: "raise", amount: 800000, request_id: "act-1" });
const a = await acted; // amount: the total bet on this street, not the extra gold
if (a.failed) console.log("act failed:", a.response); // "poker_not_your_turn", "poker_min_raise", ...
else console.log(a.action, "added", a.amount, "pot", a.pot);
```

```ts
interface PokerReply {
  response: string; place: "poker"; request_id?: string; failed?: true; success?: true;
  min?: number; max?: number; // poker_buyin, poker_min_raise
  seat?: number; stack?: number; buyin?: number; blinds?: [number, number]; // join
  action?: string; amount?: number; pot?: number; // act
}
const isReply = (id: string) => (r: PokerReply) => r?.request_id === id;
// Every reply is a game_response with place "poker". request_id tells the replies apart.
const joined = sock.waitFor<PokerReply>("game_response", isReply("join-1"), 5000);
sock.emit("poker", { event: "join", gold: 20000000, request_id: "join-1" });
const j = await joined;
if (j.failed) return console.log("join failed:", j.response, j.min ?? "", j.max ?? "");
console.log("seat", j.seat, "stack", j.stack, "blinds", j.blinds);

// Later, when the `poker` state shows hand.acting === j.seat:
const acted = sock.waitFor<PokerReply>("game_response", isReply("act-1"), 5000);
sock.emit("poker", { event: "act", action: "raise", amount: 800000, request_id: "act-1" });
const a = await acted; // amount: the total bet on this street, not the extra gold
if (a.failed) console.log("act failed:", a.response); // "poker_not_your_turn", "poker_min_raise", ...
else console.log(a.action, "added", a.amount, "pot", a.pot);
```

```python
def is_reply(rid: str):
    return lambda r: isinstance(r, dict) and r.get("request_id") == rid

# Every reply is a game_response with place "poker". request_id tells the replies apart.
joined = sock.wait_for("game_response", is_reply("join-1"), timeout=5)
await sock.emit("poker", {"event": "join", "gold": 20000000, "request_id": "join-1"})
j = await joined
if j.get("failed"):
    print("join failed:", j["response"], j.get("min"), j.get("max"))
    return
print("seat", j["seat"], "stack", j["stack"], "blinds", j["blinds"])

# Later, when the `poker` state shows hand["acting"] == j["seat"]:
acted = sock.wait_for("game_response", is_reply("act-1"), timeout=5)
await sock.emit("poker", {"event": "act", "action": "raise", "amount": 800000, "request_id": "act-1"})
a = await acted  # amount: the total bet on this street, not the extra gold
if a.get("failed"):
    print("act failed:", a["response"])  # "poker_not_your_turn", "poker_min_raise", ...
else:
    print(a["action"], "added", a["amount"], "pot", a["pot"])
```

```go
type PokerReply struct {
	Response, Action string
	RequestID        string `json:"request_id"`
	Failed           bool
	Min, Max         float64 // poker_buyin, poker_min_raise
	Seat             int
	Stack, Pot       float64
	Amount           float64 // act: the gold added now
}
// ask emits one poker request and waits for the game_response with its request_id.
ask := func(payload map[string]any) (r PokerReply) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	mine := func(d json.RawMessage) bool {
		var x PokerReply
		return json.Unmarshal(d, &x) == nil && x.RequestID == payload["request_id"]
	}
	wait := sock.Expect("game_response", mine) // registers now, before the emit
	sock.Emit("poker", payload)
	if reply, err := wait(ctx); err == nil {
		json.Unmarshal(reply, &r)
	}
	return r // empty on a timeout
}
j := ask(map[string]any{"event": "join", "gold": 20000000, "request_id": "join-1"})
if j.Failed {
	fmt.Println("join failed:", j.Response, j.Min, j.Max)
	return
}
// Later, when the `poker` state shows hand.acting == j.Seat. amount is the total bet on this street.
a := ask(map[string]any{"event": "act", "action": "raise", "amount": 800000, "request_id": "act-1"})
fmt.Println(a.Response, a.Action, "added", a.Amount, "pot", a.Pot) // "poker_not_your_turn", ...
```

```csharp
// Every reply is a game_response with place "poker". request_id tells the replies apart.
async Task<JsonElement> Ask(object payload, string id)
{
    var reply = sock.WaitForAsync("game_response",
        r => r.ValueKind == JsonValueKind.Object && r.TryGetProperty("request_id", out var q) && q.GetString() == id,
        TimeSpan.FromSeconds(5));
    await sock.EmitAsync("poker", payload);
    return await reply;
}
var j = await Ask(new { @event = "join", gold = 20000000, request_id = "join-1" }, "join-1");
if (j.TryGetProperty("failed", out _)) { Console.WriteLine($"join failed: {j.GetProperty("response")}"); return; }
Console.WriteLine($"seat {j.GetProperty("seat")} stack {j.GetProperty("stack")} blinds {j.GetProperty("blinds")}");

// Later, when the `poker` state shows hand.acting == seat. amount is the total bet on this street.
var a = await Ask(new { @event = "act", action = "raise", amount = 800000, request_id = "act-1" }, "act-1");
if (a.TryGetProperty("failed", out _))
    Console.WriteLine($"act failed: {a.GetProperty("response")}"); // "poker_not_your_turn", "poker_min_raise", ...
else
    Console.WriteLine($"{a.GetProperty("action")} added {a.GetProperty("amount")} pot {a.GetProperty("pot")}");
```

```rust
// Every reply is a game_response with place "poker". request_id tells the replies apart.
async fn ask(sock: &AlSocket, payload: Value) -> Result<Value> {
    let id = payload["request_id"].clone();
    let reply = sock.wait_for("game_response", move |r| r["request_id"] == id);
    sock.emit("poker", payload).await?;
    reply.await
}
let j = ask(sock, json!({"event": "join", "gold": 20000000, "request_id": "join-1"})).await?;
if j["failed"] == true {
    println!("join failed: {} min {} max {}", j["response"], j["min"], j["max"]);
    return Ok(());
}
println!("seat {} stack {} blinds {}", j["seat"], j["stack"], j["blinds"]);

// Later, when the `poker` state shows hand.acting == seat. amount is the total bet on this street.
let a = ask(sock, json!({"event": "act", "action": "raise", "amount": 800000, "request_id": "act-1"})).await?;
if a["failed"] == true {
    println!("act failed: {}", a["response"]); // "poker_not_your_turn", "poker_min_raise", ...
} else {
    println!("{} added {} pot {}", a["action"], a["amount"], a["pot"]);
}
```

```java
// Every reply is a game_response with place "poker". request_id tells the replies apart.
static JsonNode ask(AlSocket sock, Map<String, Object> payload) throws Exception {
    String id = (String) payload.get("request_id");
    var reply = sock.waitFor("game_response", r -> r.path("request_id").asText().equals(id), Duration.ofSeconds(5));
    sock.emit("poker", payload);
    return reply.get();
}

static void poker(AlSocket sock) throws Exception {
    JsonNode j = ask(sock, Map.of("event", "join", "gold", 20000000, "request_id", "join-1"));
    if (j.path("failed").asBoolean()) {
        System.out.println("join failed: " + j.path("response").asText() + " " + j.path("min") + " " + j.path("max"));
        return;
    }
    System.out.println("seat " + j.path("seat") + " stack " + j.path("stack") + " blinds " + j.path("blinds"));

    // Later, when the `poker` state shows hand.acting == seat. amount is the total bet on this street.
    JsonNode a = ask(sock, Map.of("event", "act", "action", "raise", "amount", 800000, "request_id", "act-1"));
    if (a.path("failed").asBoolean())
        System.out.println("act failed: " + a.path("response").asText()); // "poker_not_your_turn", ...
    else
        System.out.println(a.path("action").asText() + " added " + a.path("amount") + " pot " + a.path("pot"));
}
```

**Source:** `node/server.js:12875`, `node/logic/tavern_poker.js:515` (`tavern_poker_request`), `node/logic/tavern_poker.js:548` (join), `node/logic/tavern_poker.js:619` (leave), `node/logic/tavern_poker.js:633` (sit), `node/logic/tavern_poker.js:646` (act), `node/logic/tavern_poker.js:760` (`tavern_poker_apply`), `node/logic/tavern_poker.js:679` (deal), `node/logic/tavern_poker.js:924` (showdown), `node/logic/tavern_poker.js:1242` (tick), `node/logic/tavern_poker.js:429` (state), `design/games.js:54`, `node/server.js:11620`

### `play`
Does nothing. The handler body is empty.

<!-- schema -->

**Example:**

```js
// The play handler is empty: the server does nothing and sends no reply.
```

```ts
// The play handler is empty: the server does nothing and sends no reply.
```

```python
# The play handler is empty: the server does nothing and sends no reply.
```

```go
// The play handler is empty: the server does nothing and sends no reply.
```

```csharp
// The play handler is empty: the server does nothing and sends no reply.
```

```rust
// The play handler is empty: the server does nothing and sends no reply.
```

```java
// The play handler is empty: the server does nothing and sends no reply.
```

**Source:** `node/server.js:12880`

### `pet`
Meant to make your pet appear as a monster named "Skimpy" that follows you. It always fails with an error.

<!-- schema -->

**Notes:** **Server bug:** no code in the live server sets `player.pet`. `new_monster` gets `type: undefined`, and `get_monster_dimensions` reads `G.monsters[undefined].size`. This throws.

**Example:**

```js
// pet always fails: the server throws and sends game_error "ERROR!".
```

```ts
// pet always fails: the server throws and sends game_error "ERROR!".
```

```python
# pet always fails: the server throws and sends game_error "ERROR!".
```

```go
// pet always fails: the server throws and sends game_error "ERROR!".
```

```csharp
// pet always fails: the server throws and sends game_error "ERROR!".
```

```rust
// pet always fails: the server throws and sends game_error "ERROR!".
```

```java
// pet always fails: the server throws and sends game_error "ERROR!".
```

**Source:** `node/server.js:12881`, `js/old_common_functions.js:695`, `node/server.js:4950` (error handler)

### `whistle`
Meant to move your pet monster to your position. The handler reads `player` but does not declare it.

<!-- schema -->

**Notes:** **Server bug:** `player` resolves to a `var player` in the connection function (`node/server.js:4991`). Only a socket that connected with a `secret` handshake query sets it. Then `player` is the last character that the connection loop read, which can be a different character. That character has no `monster`, because `pet` always fails.

**Example:**

```js
// whistle is broken: a normal socket gets game_error "ERROR!".
```

```ts
// whistle is broken: a normal socket gets game_error "ERROR!".
```

```python
# whistle is broken: a normal socket gets game_error "ERROR!".
```

```go
// whistle is broken: a normal socket gets game_error "ERROR!".
```

```csharp
// whistle is broken: a normal socket gets game_error "ERROR!".
```

```rust
// whistle is broken: a normal socket gets game_error "ERROR!".
```

```java
// whistle is broken: a normal socket gets game_error "ERROR!".
```

**Source:** `node/server.js:12897`

### `list_pvp`
Gets the most recent PvP kills on this server.

<!-- schema -->

**Notes:** The handler does not need a character.

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("pvp_list", (d) => d?.code === 1, 5000);
sock.emit("list_pvp", { code: 1 });
const { list } = await reply;
for (const [attacker, victim] of list) console.log(attacker, "defeated", victim); // newest first
```

```ts
interface PvpList { code: unknown; list: [attacker: string, victim: string][] }
const reply = sock.waitFor<PvpList>("pvp_list", (d) => d?.code === 1, 5000);
sock.emit("list_pvp", { code: 1 });
const { list } = await reply;
for (const [attacker, victim] of list) console.log(attacker, "defeated", victim); // newest first
```

```python
reply = sock.wait_for("pvp_list", lambda d: isinstance(d, dict) and d.get("code") == 1, timeout=5)
await sock.emit("list_pvp", {"code": 1})
data = await reply
for attacker, victim in data["list"]:  # newest first
    print(attacker, "defeated", victim)
```

```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
type PvpList struct {
	Code any
	List [][2]string // [attacker, victim], newest first
}
isMine := func(d json.RawMessage) bool {
	var p PvpList
	return json.Unmarshal(d, &p) == nil && p.Code == float64(1) // JSON numbers decode as float64
}
wait := sock.Expect("pvp_list", isMine) // registers now, before the emit
sock.Emit("list_pvp", map[string]any{"code": 1})
reply, err := wait(ctx)
if err != nil {
	return // no reply in time
}
var p PvpList
if json.Unmarshal(reply, &p) == nil {
	for _, kill := range p.List {
		fmt.Println(kill[0], "defeated", kill[1])
	}
}
```

```csharp
var reply = sock.WaitForAsync("pvp_list",
    d => d.ValueKind == JsonValueKind.Object && d.TryGetProperty("code", out var c) && c.ValueKind == JsonValueKind.Number && c.GetInt32() == 1,
    TimeSpan.FromSeconds(5));
await sock.EmitAsync("list_pvp", new { code = 1 });
var data = await reply;
foreach (var kill in data.GetProperty("list").EnumerateArray()) // [attacker, victim], newest first
    Console.WriteLine($"{kill[0]} defeated {kill[1]}");
```

```rust
let reply = sock.wait_for("pvp_list", |d| d["code"] == 1);
sock.emit("list_pvp", json!({"code": 1})).await?;
let data = reply.await?;
for kill in data["list"].as_array().into_iter().flatten() {
    println!("{} defeated {}", kill[0], kill[1]); // [attacker, victim], newest first
}
```

```java
var reply = sock.waitFor("pvp_list", d -> d.path("code").asInt() == 1, Duration.ofSeconds(5));
sock.emit("list_pvp", Map.of("code", 1));
for (JsonNode kill : reply.get().path("list")) // [attacker, victim], newest first
    System.out.println(kill.get(0).asText() + " defeated " + kill.get(1).asText());
```

**Source:** `node/server.js:12909`, `node/server.js:3021` (where kills go into the list)

### `players`
Gets the list of online characters on this server.

<!-- schema -->

**Limits:** Each `players` call costs 12 call-cost (`CC.players`, `node/server.js:245`).

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("players", undefined, 5000);
sock.emit("players", {});
const list = await reply; // an array, not an object
for (const p of list) console.log(p.name, p.type, p.level, p.map, p.afk ? "afk" : "");
```

```ts
interface OnlinePlayer {
  name: string; map: string; age: number; level: number; type: string;
  afk: 0 | 1; party: string; kills?: number; // kills: PvP servers only
}
const reply = sock.waitFor<OnlinePlayer[]>("players", undefined, 5000);
sock.emit("players", {});
const list = await reply; // an array, not an object
for (const p of list) console.log(p.name, p.type, p.level, p.map, p.afk ? "afk" : "");
```

```python
reply = sock.wait_for("players", timeout=5)
await sock.emit("players", {})
for p in await reply:  # a list, not a dict
    print(p["name"], p["type"], p["level"], p["map"], "afk" if p["afk"] else "")
```

```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
wait := sock.Expect("players", nil) // registers now, before the emit
sock.Emit("players", map[string]any{})
reply, err := wait(ctx)
if err != nil {
	return // no reply in time
}
var list []struct { // an array, not an object
	Name, Map, Type, Party string
	Level, Age, AFK        int // afk: 0 or 1
}
if json.Unmarshal(reply, &list) == nil {
	for _, p := range list {
		fmt.Println(p.Name, p.Type, p.Level, p.Map, p.AFK)
	}
}
```

```csharp
var reply = sock.WaitForAsync("players", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("players", new { });
foreach (var p in (await reply).EnumerateArray()) // an array, not an object
    Console.WriteLine($"{p.GetProperty("name")} {p.GetProperty("type")} {p.GetProperty("level")} {p.GetProperty("map")} afk={p.GetProperty("afk")}");
```

```rust
let reply = sock.wait_for("players", |_| true);
sock.emit("players", json!({})).await?;
let list = reply.await?; // an array, not an object
for p in list.as_array().into_iter().flatten() {
    println!("{} {} {} {} afk={}", p["name"], p["type"], p["level"], p["map"], p["afk"]);
}
```

```java
var reply = sock.waitFor("players", d -> true, Duration.ofSeconds(5));
sock.emit("players", Map.of());
for (JsonNode p : reply.get()) // an array, not an object
    System.out.println(p.path("name").asText() + " " + p.path("type").asText() + " " + p.path("level")
            + " " + p.path("map").asText() + " afk=" + p.path("afk"));
```

**Source:** `node/server.js:12919`

### `pets`
Gets the pet records in your character data (`player.p.pets`).

<!-- schema -->

**Notes:**
- **Server bug:** the reply goes out on the `players` event, not on a `pets` event.
- The contents of a pet record are unclear from the source.

**Example:**

```js
// sock: a connected AlSocket
// The reply arrives on the `players` event (server bug), as an array.
const reply = sock.waitFor("players", undefined, 5000);
sock.emit("pets", {});
const records = await reply;
console.log(records.length, "pet records");
```

```ts
// The reply arrives on the `players` event (server bug), as an array.
// The fields of a pet record are unclear from the source.
const reply = sock.waitFor<Record<string, unknown>[]>("players", undefined, 5000);
sock.emit("pets", {});
const records = await reply;
console.log(records.length, "pet records");
```

```python
# The reply arrives on the `players` event (server bug), as a list.
reply = sock.wait_for("players", timeout=5)
await sock.emit("pets", {})
records = await reply
print(len(records), "pet records")
```

```go
// The reply arrives on the `players` event (server bug), as an array.
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
wait := sock.Expect("players", nil) // registers now, before the emit
sock.Emit("pets", map[string]any{})
reply, err := wait(ctx)
if err != nil {
	return // no reply in time
}
var records []json.RawMessage // the fields of a pet record are unclear from the source
if json.Unmarshal(reply, &records) == nil {
	fmt.Println(len(records), "pet records")
}
```

```csharp
// The reply arrives on the `players` event (server bug), as an array.
var reply = sock.WaitForAsync("players", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("pets", new { });
var records = await reply;
Console.WriteLine($"{records.GetArrayLength()} pet records");
```

```rust
// The reply arrives on the `players` event (server bug), as an array.
let reply = sock.wait_for("players", |_| true);
sock.emit("pets", json!({})).await?;
let records = reply.await?;
println!("{} pet records", records.as_array().map_or(0, |a| a.len()));
```

```java
// The reply arrives on the `players` event (server bug), as an array.
var reply = sock.waitFor("players", d -> true, Duration.ofSeconds(5));
sock.emit("pets", Map.of());
System.out.println(reply.get().size() + " pet records");
```

**Source:** `node/server.js:12955`

### `harakiri`
Kills your own character.

<!-- schema -->

**Notes:**
- `defeat_player` runs first (node/server.js:4499-4532). On a generated map (a dream cave run), it only kills you.
- Elsewhere, `defeat_player` adds 1 to `player.violations`. If a different character hit you recently (`s.block.f`), that character gets the PvP kill and its rewards.
- If you are still alive after that, `rip` kills you: `hp` becomes 0 and `rip` becomes `true`.

**Example:**

```js
// sock: a connected AlSocket
const update = sock.waitFor("player", (me) => Boolean(me?.rip), 5000);
sock.emit("harakiri", {});
const me = await update;
console.log("dead:", me.rip); // true, or the name of the gravestone
```

```ts
interface PlayerUpdate { rip?: boolean | string } // true, or the name of the gravestone
const update = sock.waitFor<PlayerUpdate>("player", (me) => Boolean(me?.rip), 5000);
sock.emit("harakiri", {});
const me = await update;
console.log("dead:", me.rip);
```

```python
update = sock.wait_for("player", lambda me: isinstance(me, dict) and bool(me.get("rip")), timeout=5)
await sock.emit("harakiri", {})
me = await update
print("dead:", me["rip"])  # True, or the name of the gravestone
```

```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
type PlayerUpdate struct {
	Rip any `json:"rip"` // true, or the name of the gravestone
}
isDead := func(d json.RawMessage) bool {
	var me PlayerUpdate
	return json.Unmarshal(d, &me) == nil && me.Rip != nil && me.Rip != false
}
wait := sock.Expect("player", isDead) // registers now, before the emit
sock.Emit("harakiri", map[string]any{})
reply, err := wait(ctx)
if err != nil {
	return // no reply in time
}
fmt.Println("dead:", string(reply) != "")
```

```csharp
// rip is true, or the name of the gravestone
var update = sock.WaitForAsync("player",
    me => me.ValueKind == JsonValueKind.Object && me.TryGetProperty("rip", out var rip) && rip.ValueKind is JsonValueKind.True or JsonValueKind.String,
    TimeSpan.FromSeconds(5));
await sock.EmitAsync("harakiri", new { });
var me = await update;
Console.WriteLine($"dead: {me.GetProperty("rip")}");
```

```rust
// rip is true, or the name of the gravestone
let reply = sock.wait_for("player", |me| me["rip"] == true || me["rip"].is_string());
sock.emit("harakiri", json!({})).await?;
let me = reply.await?;
println!("dead: {}", me["rip"]);
```

```java
// rip is true, or the name of the gravestone
var update = sock.waitFor("player", me -> me.path("rip").asBoolean() || me.path("rip").isTextual(), Duration.ofSeconds(5));
sock.emit("harakiri", Map.of());
System.out.println("dead: " + update.get().path("rip"));
```

**Source:** `node/server.js:12966`, `node/server.js:4499` (`defeat_player`)

### `deepsea`
Disabled: the handler returns at once.

<!-- schema -->

**Notes:** The dead code after the `return` changes your skin to `"deepsea"`.

**Example:**

```js
// deepsea is disabled: the handler returns at once and sends no reply.
```

```ts
// deepsea is disabled: the handler returns at once and sends no reply.
```

```python
# deepsea is disabled: the handler returns at once and sends no reply.
```

```go
// deepsea is disabled: the handler returns at once and sends no reply.
```

```csharp
// deepsea is disabled: the handler returns at once and sends no reply.
```

```rust
// deepsea is disabled: the handler returns at once and sends no reply.
```

```java
// deepsea is disabled: the handler returns at once and sends no reply.
```

**Source:** `node/server.js:12982`

### `blend`
Disabled: the handler returns at once.

<!-- schema -->

**Notes:** The dead code after the `return` gives you the skin of the nearest monster in your instance, as a temporary skin (`player.tskin`).

**Example:**

```js
// blend is disabled: the handler returns at once and sends no reply.
```

```ts
// blend is disabled: the handler returns at once and sends no reply.
```

```python
# blend is disabled: the handler returns at once and sends no reply.
```

```go
// blend is disabled: the handler returns at once and sends no reply.
```

```csharp
// blend is disabled: the handler returns at once and sends no reply.
```

```rust
// blend is disabled: the handler returns at once and sends no reply.
```

```java
// blend is disabled: the handler returns at once and sends no reply.
```

**Source:** `node/server.js:12996`

### `skin`
GM only. Sets your temporary skin to any name.

<!-- schema -->

**Example:**

```js
// skin is for GM characters only. Other characters get no reply.
```

```ts
// skin is for GM characters only. Other characters get no reply.
```

```python
# skin is for GM characters only. Other characters get no reply.
```

```go
// skin is for GM characters only. Other characters get no reply.
```

```csharp
// skin is for GM characters only. Other characters get no reply.
```

```rust
// skin is for GM characters only. Other characters get no reply.
```

```java
// skin is for GM characters only. Other characters get no reply.
```

**Source:** `node/server.js:13020`

### `legacify`
Does nothing to items. It was meant to mark old `fury` and `starkillers` items as `"legacy"`.

<!-- schema -->

**Notes:** The item condition starts with `0 &&`, so it never matches.

**Example:**

```js
// legacify changes no items. The only reply is a player update.
```

```ts
// legacify changes no items. The only reply is a player update.
```

```python
# legacify changes no items. The only reply is a player update.
```

```go
// legacify changes no items. The only reply is a player update.
```

```csharp
// legacify changes no items. The only reply is a player update.
```

```rust
// legacify changes no items. The only reply is a player update.
```

```java
// legacify changes no items. The only reply is a player update.
```

**Source:** `node/server.js:13028`

### `requested_ack`
Answers the `"requesting_ack"` connection check. The server only writes it to its log.

<!-- schema -->

**Notes:** The live server never sends `requesting_ack`. The only server reference is a comment (`node/server.js:13041`). The browser client still listens for it (`js/game.js:1878`).

**Example:**

```js
// The live server never sends requesting_ack, so a client has no reason to send requested_ack.
```

```ts
// The live server never sends requesting_ack, so a client has no reason to send requested_ack.
```

```python
# The live server never sends requesting_ack, so a client has no reason to send requested_ack.
```

```go
// The live server never sends requesting_ack, so a client has no reason to send requested_ack.
```

```csharp
// The live server never sends requesting_ack, so a client has no reason to send requested_ack.
```

```rust
// The live server never sends requesting_ack, so a client has no reason to send requested_ack.
```

```java
// The live server never sends requesting_ack, so a client has no reason to send requested_ack.
```

**Source:** `node/server.js:13040`

### `disconnect`
The built-in socket.io event for a closed connection. The server removes your character here.

<!-- schema -->

**Notes:**
- First, the server cancels a character login in progress and removes the socket. If the socket has a character, the steps are (node/server.js:13053-13141):
  1. Set `player.dc = true`, and remember the character for the server information.
  2. Run `defeat_player`, except on a generated map. This gives a pending PvP attacker the kill.
  3. If you were moving and are within 800 px of your destination, put you at the destination.
  4. Remove you from your party.
  5. Send `disappear` to nearby clients.
  6. Return the gold of your open dice bets. Settle your wheel spin and slots pull. Mark your poker seat as disconnected.
  7. Remove your pet monster.
  8. Remove you from `players` and from the instance. Destroy your solo instance, if you have one.
  9. Restore your state with `restore_state`. On a generated map, `generated_disconnect` keeps your cave state instead.
  10. Queue you in `dc_players` for the next save, and run `sync_loop`. On `hardcore` or `test` servers, save you at once.
- If the socket was an observer, the server removes the observer.

**Example:**

```js
// sock: a connected AlSocket
// Do not emit "disconnect". Close the socket: the server then runs its disconnect handler.
sock.close();
```

```ts
// Do not emit "disconnect". Close the socket: the server then runs its disconnect handler.
sock.close();
```

```python
# Do not emit "disconnect". Close the socket: the server then runs its disconnect handler.
await sock.close()
```

```go
// Do not emit "disconnect". Close the socket: the server then runs its disconnect handler.
sock.Close()
```

```csharp
// Do not emit "disconnect". Close the socket: the server then runs its disconnect handler.
await sock.CloseAsync();
```

```rust
// Do not emit "disconnect". Close the socket: the server then runs its disconnect handler.
sock.close().await?;
```

```java
// Do not emit "disconnect". Close the socket: the server then runs its disconnect handler.
sock.close();
```

**Source:** `node/server.js:13044`

### `shutdown`
Admin only. Starts the shutdown of the server after 10 s, with an optional reason for all clients.

<!-- schema -->

**Example:**

```js
// Admin only: a normal client never sends shutdown. A wrong pass gets no reply.
```

```ts
// Admin only: a normal client never sends shutdown. A wrong pass gets no reply.
```

```python
# Admin only: a normal client never sends shutdown. A wrong pass gets no reply.
```

```go
// Admin only: a normal client never sends shutdown. A wrong pass gets no reply.
```

```csharp
// Admin only: a normal client never sends shutdown. A wrong pass gets no reply.
```

```rust
// Admin only: a normal client never sends shutdown. A wrong pass gets no reply.
```

```java
// Admin only: a normal client never sends shutdown. A wrong pass gets no reply.
```

**Source:** `node/server.js:13152`, `node/server.js:16931` (`shutdown_routine`)

### `notice`
Admin only. Sends a notice to every client.

<!-- schema -->

**Example:**

```js
// Admin only: a normal client never sends notice. A wrong pass gets no reply.
```

```ts
// Admin only: a normal client never sends notice. A wrong pass gets no reply.
```

```python
# Admin only: a normal client never sends notice. A wrong pass gets no reply.
```

```go
// Admin only: a normal client never sends notice. A wrong pass gets no reply.
```

```csharp
// Admin only: a normal client never sends notice. A wrong pass gets no reply.
```

```rust
// Admin only: a normal client never sends notice. A wrong pass gets no reply.
```

```java
// Admin only: a normal client never sends notice. A wrong pass gets no reply.
```

**Source:** `node/server.js:13161`

### `render`
Admin only. Runs JavaScript on the server and sends the output back for display.

<!-- schema -->

**Example:**

```js
// Admin only: a normal client never sends render. A wrong pass gets no reply.
```

```ts
// Admin only: a normal client never sends render. A wrong pass gets no reply.
```

```python
# Admin only: a normal client never sends render. A wrong pass gets no reply.
```

```go
// Admin only: a normal client never sends render. A wrong pass gets no reply.
```

```csharp
// Admin only: a normal client never sends render. A wrong pass gets no reply.
```

```rust
// Admin only: a normal client never sends render. A wrong pass gets no reply.
```

```java
// Admin only: a normal client never sends render. A wrong pass gets no reply.
```

**Source:** `node/server.js:13167`

### `error`
An empty handler. The comment says that a client `"error"` event stopped the server before.

<!-- schema -->

**Example:**

```js
// The error handler is empty: the server does nothing and sends no reply.
```

```ts
// The error handler is empty: the server does nothing and sends no reply.
```

```python
# The error handler is empty: the server does nothing and sends no reply.
```

```go
// The error handler is empty: the server does nothing and sends no reply.
```

```csharp
// The error handler is empty: the server does nothing and sends no reply.
```

```rust
// The error handler is empty: the server does nothing and sends no reply.
```

```java
// The error handler is empty: the server does nothing and sends no reply.
```

**Source:** `node/server.js:13198`

### `eval`
Two uses: with `command`, the "mainframe" terminal puzzle on the `cyberland` map; with `pass`, a raw server `eval` for admins.

<!-- schema -->

**Notes:**
- The mainframe commands (node/server.js:13224-13280). The handler tests them in this order:

  | Command | Message | Effect |
  |---|---|---|
  | `"hello"` | `"hi"` | none |
  | `"give"` | `"what?"` | none |
  | starts with `"swap"`, exactly 3 words, A and B in 0–41 | `"done"` | If `p.item_num` equals A, it becomes B. If it equals B, it becomes A. |
  | starts with `"swap"`, 3 words, A or B out of range or not a number (`parseInt` gives `NaN`) | `"ugh, ok"` | none |
  | starts with `"swap"`, a different word count | `"..."` | none |
  | `"stop"` | `"mechagnomes assemble"` | Each `mechagnome` monster with a target stops its pursuit |
  | starts with `"give"`, not `"give spares"` | `"no"` | none |
  | `"secret web mode"`, with `p.steam_id` or `p.mas_auth_id` | `"secret web mode unlocked"` | Sets `p.secret_web_mode = true` |
  | `"give spares"`, with spares | `"here you go"` | Drops `S.misc.spares` at (1, -88) with `drop_one_thing`, then empties the list |
  | `"give spares"`, no spares | `"come later"` | none |
  | other, without `player.supercomputer` | `"UNAUTHORIZED COMMAND"` | Each monster in the `cyberland` instance with no target attacks you |
  | other, with `player.supercomputer` | `"UNAUTHORIZED, COMRADE"` | none |

- `"secret web mode"` without a steam or mas id goes to the "other" rows.
- With a correct `pass`, the server runs `eval(data.code)` and sends nothing. This also happens after a mainframe command that did not fail.

**Example:**

```js
// sock: a connected AlSocket (the character is on the cyberland map)
const id = "mf-1";
const reply = sock.waitFor("game_response", (r) => r?.request_id === id, 5000);
sock.emit("eval", { command: "hello", request_id: id });
const r = await reply;
if (r.failed) console.log("mainframe:", r.response); // "not_connected" or "invalid"
else console.log("mainframe says", r.reply, "authorized:", r.authorized);
```

```ts
interface MainframeReply {
  response: string; place: "mainframe"; request_id: string; failed?: true;
  command: string; authorized: boolean; reply?: string;
}
// The character is on the cyberland map.
const id = "mf-1";
const reply = sock.waitFor<MainframeReply>("game_response", (r) => r?.request_id === id, 5000);
sock.emit("eval", { command: "hello", request_id: id });
const r = await reply;
if (r.failed) console.log("mainframe:", r.response); // "not_connected" or "invalid"
else console.log("mainframe says", r.reply, "authorized:", r.authorized);
```

```python
# The character is on the cyberland map.
rid = "mf-1"
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("request_id") == rid, timeout=5)
await sock.emit("eval", {"command": "hello", "request_id": rid})
r = await reply
if r.get("failed"):
    print("mainframe:", r["response"])  # "not_connected" or "invalid"
else:
    print("mainframe says", r["reply"], "authorized:", r["authorized"])
```

```go
// The character is on the cyberland map.
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
type MainframeReply struct {
	Response, Command, Reply string
	RequestID                string `json:"request_id"`
	Failed, Authorized       bool
}
mine := func(d json.RawMessage) bool {
	var r MainframeReply
	return json.Unmarshal(d, &r) == nil && r.RequestID == "mf-1"
}
wait := sock.Expect("game_response", mine) // registers now, before the emit
sock.Emit("eval", map[string]any{"command": "hello", "request_id": "mf-1"})
reply, err := wait(ctx)
if err != nil {
	return // no reply in time
}
var r MainframeReply
if json.Unmarshal(reply, &r) == nil {
	fmt.Println(r.Response, r.Reply, r.Authorized) // failed: "not_connected" or "invalid"
}
```

```csharp
// The character is on the cyberland map.
const string id = "mf-1";
var reply = sock.WaitForAsync("game_response",
    r => r.ValueKind == JsonValueKind.Object && r.TryGetProperty("request_id", out var q) && q.GetString() == id,
    TimeSpan.FromSeconds(5));
await sock.EmitAsync("eval", new { command = "hello", request_id = id });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"mainframe: {r.GetProperty("response")}"); // "not_connected" or "invalid"
else
    Console.WriteLine($"mainframe says {r.GetProperty("reply")} authorized: {r.GetProperty("authorized")}");
```

```rust
// The character is on the cyberland map.
let reply = sock.wait_for("game_response", |r| r["request_id"] == "mf-1");
sock.emit("eval", json!({"command": "hello", "request_id": "mf-1"})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("mainframe: {}", r["response"]); // "not_connected" or "invalid"
} else {
    println!("mainframe says {} authorized: {}", r["reply"], r["authorized"]);
}
```

```java
// The character is on the cyberland map.
String id = "mf-1";
var reply = sock.waitFor("game_response", r -> r.path("request_id").asText().equals(id), Duration.ofSeconds(5));
sock.emit("eval", Map.of("command", "hello", "request_id", id));
JsonNode r = reply.get();
if (r.path("failed").asBoolean())
    System.out.println("mainframe: " + r.path("response").asText()); // "not_connected" or "invalid"
else
    System.out.println("mainframe says " + r.path("reply").asText() + " authorized: " + r.path("authorized"));
```

**Source:** `node/server.js:13201`
