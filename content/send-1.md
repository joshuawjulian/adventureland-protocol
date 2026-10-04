### `send_updates`
Asks the server to send again every entity in view, for the observer of the socket and for its character.

<!-- schema -->

**Limits:** Call cost: 13 (1, plus 12 from `CC`).

**Notes:**
- `send_updates` also passes while a cave conversation pauses your instance.
- A full snapshot replaces the view: the `disappear` events tell the client which entities to drop.

**Example:**

```js
// sock: a connected AlSocket
// The reply is one `entities` with type "all".
const reply = sock.waitFor("entities", undefined, 5000); // register first
sock.emit("send_updates", {});
const d = await reply;
console.log("entities for", d.map, d.type);
```

```ts
// The reply is one `entities` with type "all".
interface EntitiesData { map?: string; type?: string }
const reply = sock.waitFor<EntitiesData>("entities", undefined, 5000);
sock.emit("send_updates", {});
const d = await reply;
console.log("entities for", d.map, d.type);
```

```python
# The reply is one `entities` with type "all".
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("entities")
await sock.emit("send_updates", {})
d = await reply
print("entities for", d.get("map"), d.get("type"))
```

```go
// The reply is one `entities` with type "all".
wait := sock.Expect("entities", nil) // registers now, before the emit
if err := sock.Emit("send_updates", map[string]any{}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
raw, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var d struct {
	Map  string `json:"map"`
	Type string `json:"type"`
}
_ = json.Unmarshal(raw, &d)
fmt.Println("entities for", d.Map, d.Type)
```

```csharp
// The reply is one `entities` with type "all".
var reply = sock.WaitForAsync("entities", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("send_updates", new { });
var d = await reply;
Console.WriteLine($"entities for {(d.TryGetProperty("map", out var map) ? map.ToString() : "-")} {(d.TryGetProperty("type", out var type) ? type.ToString() : "-")}");
```

```rust
// The reply is one `entities` with type "all".
let wait = sock.wait_for("entities", |_| true);
sock.emit("send_updates", json!({})).await?;
let d = wait.await?;
println!("entities for {} {}", d["map"], d["type"]);
```

```java
// The reply is one `entities` with type "all".
var reply = sock.waitFor("entities", x -> true, Duration.ofSeconds(5));
sock.emit("send_updates", Map.of());
JsonNode d = reply.get(); // throws if no reply in 5 s
System.out.println("entities for" + " " + d.path("map").asText() + " " + d.path("type").asText());
```

**Source:** `node/server.js:5020`, `node/server_functions.js:3675`

### `loaded`
Tells the server that the client finished loading. The server then makes an observer for this socket at the position from `welcome` and starts to send entities to it.

<!-- schema -->

**Limits:** `loaded` works one time per socket, before `auth`.

**Notes:**
- The observer starts at the position from `welcome` with `vision = B.vision` (`[700, 500]`).
- If the socket connected with a `secret` query that matched a character, the observer links to that character (`observer.player`).
- The server resumes the instance of the observer if it was asleep.

**Example:**

```js
// sock: a connected AlSocket
// `loaded` works one time per socket, before `auth`.
const reply = sock.waitFor("entities", undefined, 5000); // register first
sock.emit("loaded", {});
const d = await reply;
console.log("observer sees", d.map, d.type);
```

```ts
// `loaded` works one time per socket, before `auth`.
interface EntitiesData { map?: string; type?: string }
const reply = sock.waitFor<EntitiesData>("entities", undefined, 5000);
sock.emit("loaded", {});
const d = await reply;
console.log("observer sees", d.map, d.type);
```

```python
# `loaded` works one time per socket, before `auth`.
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("entities")
await sock.emit("loaded", {})
d = await reply
print("observer sees", d.get("map"), d.get("type"))
```

```go
// `loaded` works one time per socket, before `auth`.
wait := sock.Expect("entities", nil) // registers now, before the emit
if err := sock.Emit("loaded", map[string]any{}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
raw, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var d struct {
	Map  string `json:"map"`
	Type string `json:"type"`
}
_ = json.Unmarshal(raw, &d)
fmt.Println("observer sees", d.Map, d.Type)
```

```csharp
// `loaded` works one time per socket, before `auth`.
var reply = sock.WaitForAsync("entities", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("loaded", new { });
var d = await reply;
Console.WriteLine($"observer sees {(d.TryGetProperty("map", out var map) ? map.ToString() : "-")} {(d.TryGetProperty("type", out var type) ? type.ToString() : "-")}");
```

```rust
// `loaded` works one time per socket, before `auth`.
let wait = sock.wait_for("entities", |_| true);
sock.emit("loaded", json!({})).await?;
let d = wait.await?;
println!("observer sees {} {}", d["map"], d["type"]);
```

```java
// `loaded` works one time per socket, before `auth`.
var reply = sock.waitFor("entities", x -> true, Duration.ofSeconds(5));
sock.emit("loaded", Map.of());
JsonNode d = reply.get(); // throws if no reply in 5 s
System.out.println("observer sees" + " " + d.path("map").asText() + " " + d.path("type").asText());
```

**Source:** `node/server.js:5028`, `node/logic/observer_broadcast.js:3`

### `cm`
Sends a "code message" (data of any type) to one or more characters on the same server.

<!-- schema -->

**Limits:** Call cost: `add × to.length × mult`. `mult` is 0.8 for more than one name, else 1. `add` is 1, or 2 if the JSON of `message` is longer than 100 characters.

**Notes:**
- **Server bug:** the call-cost checks for 1,000, 10,000 and 50,000 characters come after the check for 100, so they never apply. Thus `add` is never more than 2.
- Only characters on this server get the message. `cm` also passes while a cave conversation pauses your instance.

**Example:**

```js
// sock: a connected AlSocket
// `receivers` lists only the names online on this server.
const reply = sock.waitFor("game_response", (r) => r?.place === "cm", 5000); // register first
sock.emit("cm", { to: ["MyPriest", "MyMage"], message: "follow" });
const r = await reply;
if (r.failed) console.log("cm failed:", r.response);
else console.log("delivered to", r.receivers);
```

```ts
// `receivers` lists only the names online on this server.
interface CmReply { response: string; place: string; failed?: boolean; receivers?: unknown }
const reply = sock.waitFor<CmReply>("game_response", (r) => r?.place === "cm", 5000);
sock.emit("cm", { to: ["MyPriest", "MyMage"], message: "follow" });
const r = await reply;
if (r.failed) console.log("cm failed:", r.response);
else console.log("delivered to", r.receivers);
```

```python
# `receivers` lists only the names online on this server.
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "cm")
await sock.emit("cm", {"to": ["MyPriest", "MyMage"], "message": "follow"})
r = await reply
if r.get("failed"):
    print("cm failed:", r["response"])
else:
    print("delivered to", r.get("receivers"))
```

```go
// `receivers` lists only the names online on this server.
type reply struct {
	Response, Place string
	Failed          bool
	Receivers       json.RawMessage `json:"receivers"`
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "cm"
})
if err := sock.Emit("cm", map[string]any{"to": []string{"MyPriest", "MyMage"}, "message": "follow"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("cm failed:", r.Response)
} else {
	fmt.Println("delivered to", string(r.Receivers))
}
```

```csharp
// `receivers` lists only the names online on this server.
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("place", out var p) && p.GetString() == "cm", TimeSpan.FromSeconds(5));
await sock.EmitAsync("cm", new { to = new[] { "MyPriest", "MyMage" }, message = "follow" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"cm failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"delivered to {(r.TryGetProperty("receivers", out var receivers) ? receivers.ToString() : "-")}");
```

```rust
// `receivers` lists only the names online on this server.
let wait = sock.wait_for("game_response", |r| r["place"] == "cm");
sock.emit("cm", json!({"to": ["MyPriest", "MyMage"], "message": "follow"})).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("cm failed: {}", r["response"]);
} else {
    println!("delivered to {}", r["receivers"]);
}
```

```java
// `receivers` lists only the names online on this server.
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("cm"), Duration.ofSeconds(5));
sock.emit("cm", Map.of("to", List.of("MyPriest", "MyMage"), "message", "follow"));
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("cm failed: " + r.path("response").asText());
else
    System.out.println("delivered to" + " " + r.path("receivers"));
```

**Source:** `node/server.js:5077`, cost `node/server.js:4913`

### `say`
Sends a chat message. It goes to the public chat of the server by default, to the party with `party`, or to one character with `name`.

<!-- schema -->

**Limits:** 400 ms between messages. 15 s between messages with `code`. 1,200 characters.

**Notes:**
- A filter in `node/logic/chat.js` stops repeated messages and bursts from going to Discord and to the saved chat history. The filter does not stop the `chat_log`.
- `say` also passes while a cave conversation pauses your instance.

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("game_response", (r) => r?.place === "say", 5000); // register first
sock.emit("say", { message: "hello" });
const r = await reply;
if (r.failed) console.log("say failed:", r.response);
else console.log("message sent");
```

```ts
interface SayReply { response: string; place: string; failed?: boolean }
const reply = sock.waitFor<SayReply>("game_response", (r) => r?.place === "say", 5000);
sock.emit("say", { message: "hello" });
const r = await reply;
if (r.failed) console.log("say failed:", r.response);
else console.log("message sent");
```

```python
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "say")
await sock.emit("say", {"message": "hello"})
r = await reply
if r.get("failed"):
    print("say failed:", r["response"])
else:
    print("message sent")
```

```go
type reply struct {
	Response, Place string
	Failed          bool
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "say"
})
if err := sock.Emit("say", map[string]any{"message": "hello"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("say failed:", r.Response)
} else {
	fmt.Println("message sent")
}
```

```csharp
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("place", out var p) && p.GetString() == "say", TimeSpan.FromSeconds(5));
await sock.EmitAsync("say", new { message = "hello" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"say failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"message sent");
```

```rust
let wait = sock.wait_for("game_response", |r| r["place"] == "say");
sock.emit("say", json!({"message": "hello"})).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("say failed: {}", r["response"]);
} else {
    println!("message sent");
}
```

```java
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("say"), Duration.ofSeconds(5));
sock.emit("say", Map.of("message", "hello"));
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("say failed: " + r.path("response").asText());
else
    System.out.println("message sent");
```

**Source:** `node/server.js:5092`, `node/logic/chat.js:60`

### `ping_trig`
Measures latency. The server sends the payload back without change.

<!-- schema -->

**Example:**

```js
// sock: a connected AlSocket
// The latency is the time from emit to `ping_ack`.
const reply = sock.waitFor("ping_ack", undefined, 5000); // register first
sock.emit("ping_trig", { id: 17 });
const d = await reply;
console.log("ping_ack for id", d.id);
```

```ts
// The latency is the time from emit to `ping_ack`.
interface PingAckData { id?: number }
const reply = sock.waitFor<PingAckData>("ping_ack", undefined, 5000);
sock.emit("ping_trig", { id: 17 });
const d = await reply;
console.log("ping_ack for id", d.id);
```

```python
# The latency is the time from emit to `ping_ack`.
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("ping_ack")
await sock.emit("ping_trig", {"id": 17})
d = await reply
print("ping_ack for id", d.get("id"))
```

```go
// The latency is the time from emit to `ping_ack`.
wait := sock.Expect("ping_ack", nil) // registers now, before the emit
if err := sock.Emit("ping_trig", map[string]any{"id": 17}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
raw, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var d struct {
	Id float64 `json:"id"`
}
_ = json.Unmarshal(raw, &d)
fmt.Println("ping_ack for id", d.Id)
```

```csharp
// The latency is the time from emit to `ping_ack`.
var reply = sock.WaitForAsync("ping_ack", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("ping_trig", new { id = 17 });
var d = await reply;
Console.WriteLine($"ping_ack for id {(d.TryGetProperty("id", out var id) ? id.ToString() : "-")}");
```

```rust
// The latency is the time from emit to `ping_ack`.
let wait = sock.wait_for("ping_ack", |_| true);
sock.emit("ping_trig", json!({"id": 17})).await?;
let d = wait.await?;
println!("ping_ack for id {}", d["id"]);
```

```java
// The latency is the time from emit to `ping_ack`.
var reply = sock.waitFor("ping_ack", x -> true, Duration.ofSeconds(5));
sock.emit("ping_trig", Map.of("id", 17));
JsonNode d = reply.get(); // throws if no reply in 5 s
System.out.println("ping_ack for id" + " " + d.path("id").asText());
```

**Source:** `node/server.js:5126`

### `target`
Sets the target of your character and a second "focus" entity. Other players see what you target.

<!-- schema -->

**Limits:** `target` costs half of a normal event (`call_modifier` 0.5). The handler also calls `reduce_call_cost()`.

**Notes:**
- Other clients see your `target` in the entity of your character, with the value that you sent.
- **Server bug:** if the focus entity has `screenshot`, the handler changes `target.going_x`, not the focus, and throws when `target` is `null`. No entity sets `screenshot` now, so this does not occur.
- `target` also passes while a cave conversation pauses your instance.

**Example:**

```js
// sock: a connected AlSocket
// An unknown id gives success too, with target null.
const reply = sock.waitFor("game_response", (r) => r?.place === "target", 5000); // register first
sock.emit("target", { id: "1234567" });
const r = await reply;
if (r.failed) console.log("target failed:", r.response);
else console.log("target set");
```

```ts
// An unknown id gives success too, with target null.
interface TargetReply { response: string; place: string; failed?: boolean }
const reply = sock.waitFor<TargetReply>("game_response", (r) => r?.place === "target", 5000);
sock.emit("target", { id: "1234567" });
const r = await reply;
if (r.failed) console.log("target failed:", r.response);
else console.log("target set");
```

```python
# An unknown id gives success too, with target null.
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "target")
await sock.emit("target", {"id": "1234567"})
r = await reply
if r.get("failed"):
    print("target failed:", r["response"])
else:
    print("target set")
```

```go
// An unknown id gives success too, with target null.
type reply struct {
	Response, Place string
	Failed          bool
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "target"
})
if err := sock.Emit("target", map[string]any{"id": "1234567"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("target failed:", r.Response)
} else {
	fmt.Println("target set")
}
```

```csharp
// An unknown id gives success too, with target null.
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("place", out var p) && p.GetString() == "target", TimeSpan.FromSeconds(5));
await sock.EmitAsync("target", new { id = "1234567" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"target failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"target set");
```

```rust
// An unknown id gives success too, with target null.
let wait = sock.wait_for("game_response", |r| r["place"] == "target");
sock.emit("target", json!({"id": "1234567"})).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("target failed: {}", r["response"]);
} else {
    println!("target set");
}
```

```java
// An unknown id gives success too, with target null.
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("target"), Duration.ofSeconds(5));
sock.emit("target", Map.of("id", "1234567"));
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("target failed: " + r.path("response").asText());
else
    System.out.println("target set");
```

**Source:** `node/server.js:5129`, cost `node/server.js:4899`

### `ureward`
Claims the account reward for the tutorial. The only reward that the handler accepts is `c0`.

<!-- schema -->

**Notes:**
- No reply has `place`. A claim of the same character that runs already gets no reply.
- The cosmetic goes to the account (`acx`). The roll gives less weight to cosmetics that you own: each copy divides the weight by 10 (node/server_functions.js:4043-4050).

**Example:**

```js
// sock: a connected AlSocket
// Replies have no `place`: a bare string or {response: "reward_..."}.
const reply = sock.waitFor("game_response", (r) => JSON.stringify(r).includes('"reward_'), 5000);
sock.emit("ureward", { name: "c0" });
console.log("reward reply:", await reply);
```

```ts
// Replies have no `place`: a bare string or {response: "reward_..."}.
type RewardReply = string | { response: string; reason?: string; rewards?: string[] };
const reply = sock.waitFor<RewardReply>("game_response", (r) => JSON.stringify(r).includes('"reward_'), 5000);
sock.emit("ureward", { name: "c0" });
const r = await reply;
if (typeof r === "string") console.log(r); // reward_notverified or reward_already
else console.log(r.response, r.reason ?? r.rewards);
```

```python
# Replies have no `place`: a bare string or {response: "reward_..."}.
reply = sock.wait_for("game_response", lambda r: '"reward_' in json.dumps(r))
await sock.emit("ureward", {"name": "c0"})
r = await reply
print(r if isinstance(r, str) else (r["response"], r.get("reason"), r.get("rewards")))
```

```go
// Replies have no `place`: a bare string or {response: "reward_..."}.
wait := sock.Expect("game_response", func(d json.RawMessage) bool { return strings.Contains(string(d), `"reward_`) })
if err := sock.Emit("ureward", map[string]any{"name": "c0"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
fmt.Println("reward reply:", string(d))
```

```csharp
// Replies have no `place`: a bare string or {response: "reward_..."}.
var reply = sock.WaitForAsync("game_response", x => x.GetRawText().Contains("\"reward_"), TimeSpan.FromSeconds(5));
await sock.EmitAsync("ureward", new { name = "c0" });
Console.WriteLine($"reward reply: {(await reply).GetRawText()}");
```

```rust
// Replies have no `place`: a bare string or {response: "reward_..."}.
let wait = sock.wait_for("game_response", |r| r.to_string().contains("\"reward_"));
sock.emit("ureward", json!({"name": "c0"})).await?;
println!("reward reply: {}", wait.await?);
```

```java
// Replies have no `place`: a bare string or {response: "reward_..."}.
var reply = sock.waitFor("game_response", r -> r.toString().contains("\"reward_"), Duration.ofSeconds(5));
sock.emit("ureward", Map.of("name", "c0"));
System.out.println("reward reply: " + reply.get());
```

**Source:** `node/server.js:5184`, `docs/directory.js:377`, `adventure_functions.js:1172`

### `creward`
Claims a one-time class reward from `G.classes[<your class>].rewards`. The handler is broken: see Notes.

<!-- schema -->

**Notes:** **Server bug:** the handler does not declare `player`. It uses the `player` variable of the connection function. Only the `secret` query loop sets that variable, and it holds the last character in `players`, not the matched one. With G version 17478, `creward` has no working path.

**Example:**

```js
// sock: a connected AlSocket
// creward never succeeds: the handler is broken (see Notes).
```

```ts
// creward never succeeds: the handler is broken (see Notes).
```

```python
# creward never succeeds: the handler is broken (see Notes).
```

```go
// creward never succeeds: the handler is broken (see Notes).
```

```csharp
// creward never succeeds: the handler is broken (see Notes).
```

```rust
// creward never succeeds: the handler is broken (see Notes).
```

```java
// creward never succeeds: the handler is broken (see Notes).
```

**Source:** `node/server.js:5231`, connection loop `node/server.js:4991`

### `cx`
Puts on or removes a cosmetic (skin, hair, hat, wings and others) from the cosmetics that you own.

<!-- schema -->

**Notes:**
- The sprite type of `name` (`T[name]`, from `G.sprites`) decides the slot, not `slot`. If `name` has no slot, the server makes no change and still replies with success.
- `cx` with only `slot` clears that slot. A clear of `skin` does nothing.

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("game_response", (r) => r?.place === "cx", 5000); // register first
sock.emit("cx", { slot: "hat", name: "hat221" });
const r = await reply;
if (r.failed) console.log("cx failed:", r.response);
else console.log("cosmetic set");
```

```ts
interface CxReply { response: string; place: string; failed?: boolean }
const reply = sock.waitFor<CxReply>("game_response", (r) => r?.place === "cx", 5000);
sock.emit("cx", { slot: "hat", name: "hat221" });
const r = await reply;
if (r.failed) console.log("cx failed:", r.response);
else console.log("cosmetic set");
```

```python
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "cx")
await sock.emit("cx", {"slot": "hat", "name": "hat221"})
r = await reply
if r.get("failed"):
    print("cx failed:", r["response"])
else:
    print("cosmetic set")
```

```go
type reply struct {
	Response, Place string
	Failed          bool
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "cx"
})
if err := sock.Emit("cx", map[string]any{"slot": "hat", "name": "hat221"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("cx failed:", r.Response)
} else {
	fmt.Println("cosmetic set")
}
```

```csharp
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("place", out var p) && p.GetString() == "cx", TimeSpan.FromSeconds(5));
await sock.EmitAsync("cx", new { slot = "hat", name = "hat221" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"cx failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"cosmetic set");
```

```rust
let wait = sock.wait_for("game_response", |r| r["place"] == "cx");
sock.emit("cx", json!({"slot": "hat", "name": "hat221"})).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("cx failed: {}", r["response"]);
} else {
    println!("cosmetic set");
}
```

```java
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("cx"), Duration.ofSeconds(5));
sock.emit("cx", Map.of("slot", "hat", "name", "hat221"));
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("cx failed: " + r.path("response").asText());
else
    System.out.println("cosmetic set");
```

**Source:** `node/server.js:5248`, `js/old_common_functions.js:289`

### `gm`
Moderation and teleport commands for GMs. The server ignores it for each character whose `role` is not `"gm"`.

<!-- schema -->

**Notes:**
- Only a character with `role` `"gm"` can use `gm`.
- `jail` sends nothing to the GM.
- `jump` and `mjump` write to the global variable `pulled`, which the handler does not declare.

**Example:**

```js
// sock: a connected AlSocket
// gm is for GMs only. The server ignores it from other characters.
```

```ts
// gm is for GMs only. The server ignores it from other characters.
```

```python
# gm is for GMs only. The server ignores it from other characters.
```

```go
// gm is for GMs only. The server ignores it from other characters.
```

```csharp
// gm is for GMs only. The server ignores it from other characters.
```

```rust
// gm is for GMs only. The server ignores it from other characters.
```

```java
// gm is for GMs only. The server ignores it from other characters.
```

**Source:** `node/server.js:5282`, `languages/index.js:256`

### `monsterhunt`
Talks to the Monster Hunter NPC. It starts a hunt, or it completes a finished hunt for a monster token.

<!-- schema -->

**Limits:** How the server picks the hunt:
- The Monster Hunter must be within `B.sell_dist` (400 px) on `main`. On `HARDCORE` and `TEST` the limit is 10,000,999 px, so any position on `main` works.
- The account level is the highest level of any online character of the account, its `max_stats.level`, and the characters in its encouragement group.
- Account level below 30: always 10 `goo`.
- Otherwise, the server picks the highest-level live monster in a normal map instance. Its type must not have an active hunt marker on this server, and the monster must have no target.
- Below level 60, only beginner types qualify.
- Minimum account level per beginner type:

  | `goo` | `bee` | `crab` | `snake` | `squig` | `armadillo` | `croc` | `tortoise` | `squigtoad` | `bat` |
  |---|---|---|---|---|---|---|---|---|---|
  | 1 | 30 | 32 | 34 | 36 | 40 | 44 | 48 | 52 | 56 |

- Count: `max(1, min(cap, parseInt(1200 × max(1, spawns) / (hp / 1000) / (respawn + 0.25))))`. `spawns` is the total spawn count of that type in G. `cap` is 500 from level 60, else `10 + floor((level - 30) × 490 / 30)`.
- Hardcore: the count becomes `max(1, parseInt(count / 10))`.
- From account level 60, the server sets a 20-minute marker `monsterhunt_<type>` in `server.s`. Other characters on this server then do not get that type.

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("game_response", (r) => r?.place === "monsterhunt", 5000); // register first
sock.emit("monsterhunt", {});
const r = await reply;
if (r.failed) console.log("monsterhunt failed:", r.response);
else console.log("started / completed:", r.started, r.completed);
```

```ts
interface MonsterhuntReply { response: string; place: string; failed?: boolean; started?: boolean; completed?: boolean }
const reply = sock.waitFor<MonsterhuntReply>("game_response", (r) => r?.place === "monsterhunt", 5000);
sock.emit("monsterhunt", {});
const r = await reply;
if (r.failed) console.log("monsterhunt failed:", r.response);
else console.log("started / completed:", r.started, r.completed);
```

```python
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "monsterhunt")
await sock.emit("monsterhunt", {})
r = await reply
if r.get("failed"):
    print("monsterhunt failed:", r["response"])
else:
    print("started / completed:", r.get("started"), r.get("completed"))
```

```go
type reply struct {
	Response, Place string
	Failed          bool
	Started         bool `json:"started"`
	Completed       bool `json:"completed"`
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "monsterhunt"
})
if err := sock.Emit("monsterhunt", map[string]any{}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("monsterhunt failed:", r.Response)
} else {
	fmt.Println("started / completed:", r.Started, r.Completed)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("place", out var p) && p.GetString() == "monsterhunt", TimeSpan.FromSeconds(5));
await sock.EmitAsync("monsterhunt", new { });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"monsterhunt failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"started / completed: {(r.TryGetProperty("started", out var started) ? started.ToString() : "-")} {(r.TryGetProperty("completed", out var completed) ? completed.ToString() : "-")}");
```

```rust
let wait = sock.wait_for("game_response", |r| r["place"] == "monsterhunt");
sock.emit("monsterhunt", json!({})).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("monsterhunt failed: {}", r["response"]);
} else {
    println!("started / completed: {} {}", r["started"], r["completed"]);
}
```

```java
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("monsterhunt"), Duration.ofSeconds(5));
sock.emit("monsterhunt", Map.of());
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("monsterhunt failed: " + r.path("response").asText());
else
    System.out.println("started / completed:" + " " + r.path("started").asText() + " " + r.path("completed").asText());
```

**Source:** `node/server.js:5395`, `node/logic/monster_hunts.js:16`, `node/logic/monster_hunts.js:30`

### `ccreport`
Asks for the call-cost (rate-limit) state of this socket. It is a debug event.

<!-- schema -->

**Limits:** Call cost: 4 (1, plus 3 from `CC`).

**Notes:** `ccreport` also passes while a cave conversation pauses your instance.

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("ccreport", undefined, 5000); // register first
sock.emit("ccreport", {});
const d = await reply;
console.log("call-cost limit, total calls:", d.climit, d.total);
```

```ts
interface CcreportData { climit?: number; total?: number }
const reply = sock.waitFor<CcreportData>("ccreport", undefined, 5000);
sock.emit("ccreport", {});
const d = await reply;
console.log("call-cost limit, total calls:", d.climit, d.total);
```

```python
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("ccreport")
await sock.emit("ccreport", {})
d = await reply
print("call-cost limit, total calls:", d.get("climit"), d.get("total"))
```

```go
wait := sock.Expect("ccreport", nil) // registers now, before the emit
if err := sock.Emit("ccreport", map[string]any{}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
raw, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var d struct {
	Climit float64 `json:"climit"`
	Total  float64 `json:"total"`
}
_ = json.Unmarshal(raw, &d)
fmt.Println("call-cost limit, total calls:", d.Climit, d.Total)
```

```csharp
var reply = sock.WaitForAsync("ccreport", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("ccreport", new { });
var d = await reply;
Console.WriteLine($"call-cost limit, total calls: {(d.TryGetProperty("climit", out var climit) ? climit.ToString() : "-")} {(d.TryGetProperty("total", out var total) ? total.ToString() : "-")}");
```

```rust
let wait = sock.wait_for("ccreport", |_| true);
sock.emit("ccreport", json!({})).await?;
let d = wait.await?;
println!("call-cost limit, total calls: {} {}", d["climit"], d["total"]);
```

```java
var reply = sock.waitFor("ccreport", x -> true, Duration.ofSeconds(5));
sock.emit("ccreport", Map.of());
JsonNode d = reply.get(); // throws if no reply in 5 s
System.out.println("call-cost limit, total calls:" + " " + d.path("climit").asText() + " " + d.path("total").asText());
```

**Source:** `node/server.js:5437`

### `tracker`
Asks for the Monster Tracker data: your kill statistics, exchange statistics and drop tables.

<!-- schema -->

**Limits:** Call cost: 51 (1, plus 50 from `CC`). The payload holds every drop table of the game, so it is large.

**Notes:** `tracker` also passes while a cave conversation pauses your instance.

**Example:**

```js
// sock: a connected AlSocket
// No reply unless a tracker or supercomputer is in the inventory.
const reply = sock.waitFor("tracker", undefined, 5000); // register first
sock.emit("tracker", {});
const d = await reply;
console.log("max stats:", d.max);
```

```ts
// No reply unless a tracker or supercomputer is in the inventory.
interface TrackerData { max?: unknown }
const reply = sock.waitFor<TrackerData>("tracker", undefined, 5000);
sock.emit("tracker", {});
const d = await reply;
console.log("max stats:", d.max);
```

```python
# No reply unless a tracker or supercomputer is in the inventory.
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("tracker")
await sock.emit("tracker", {})
d = await reply
print("max stats:", d.get("max"))
```

```go
// No reply unless a tracker or supercomputer is in the inventory.
wait := sock.Expect("tracker", nil) // registers now, before the emit
if err := sock.Emit("tracker", map[string]any{}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
raw, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var d struct {
	Max json.RawMessage `json:"max"`
}
_ = json.Unmarshal(raw, &d)
fmt.Println("max stats:", string(d.Max))
```

```csharp
// No reply unless a tracker or supercomputer is in the inventory.
var reply = sock.WaitForAsync("tracker", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("tracker", new { });
var d = await reply;
Console.WriteLine($"max stats: {(d.TryGetProperty("max", out var max) ? max.ToString() : "-")}");
```

```rust
// No reply unless a tracker or supercomputer is in the inventory.
let wait = sock.wait_for("tracker", |_| true);
sock.emit("tracker", json!({})).await?;
let d = wait.await?;
println!("max stats: {}", d["max"]);
```

```java
// No reply unless a tracker or supercomputer is in the inventory.
var reply = sock.waitFor("tracker", x -> true, Duration.ofSeconds(5));
sock.emit("tracker", Map.of());
JsonNode d = reply.get(); // throws if no reply in 5 s
System.out.println("max stats:" + " " + d.path("max"));
```

**Source:** `node/server.js:5440`, `node/server.js:1465`

### `set_home`
Makes this server the home server of your character and removes hop sickness.

<!-- schema -->

**Limits:** One change per 36 hours.

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("game_response", (r) => r?.place === "set_home", 5000); // register first
sock.emit("set_home", {});
const r = await reply;
if (r.failed) console.log("set_home failed:", r.response, r.hours);
else console.log("home server:", r.home);
```

```ts
interface SetHomeReply { response: string; place: string; failed?: boolean; home?: string; hours?: number }
const reply = sock.waitFor<SetHomeReply>("game_response", (r) => r?.place === "set_home", 5000);
sock.emit("set_home", {});
const r = await reply;
if (r.failed) console.log("set_home failed:", r.response, r.hours);
else console.log("home server:", r.home);
```

```python
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "set_home")
await sock.emit("set_home", {})
r = await reply
if r.get("failed"):
    print("set_home failed:", r["response"], r.get("hours"))
else:
    print("home server:", r.get("home"))
```

```go
type reply struct {
	Response, Place string
	Failed          bool
	Home            string  `json:"home"`
	Hours           float64 `json:"hours"`
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "set_home"
})
if err := sock.Emit("set_home", map[string]any{}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("set_home failed:", r.Response, r.Hours)
} else {
	fmt.Println("home server:", r.Home)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("place", out var p) && p.GetString() == "set_home", TimeSpan.FromSeconds(5));
await sock.EmitAsync("set_home", new { });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"set_home failed: {r.GetProperty("response")} {(r.TryGetProperty("hours", out var hours) ? hours.ToString() : "-")}");
else
    Console.WriteLine($"home server: {(r.TryGetProperty("home", out var home) ? home.ToString() : "-")}");
```

```rust
let wait = sock.wait_for("game_response", |r| r["place"] == "set_home");
sock.emit("set_home", json!({})).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("set_home failed: {} {}", r["response"], r["hours"]);
} else {
    println!("home server: {}", r["home"]);
}
```

```java
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("set_home"), Duration.ofSeconds(5));
sock.emit("set_home", Map.of());
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("set_home failed: " + r.path("response").asText() + " " + r.path("hours").asText());
else
    System.out.println("home server:" + " " + r.path("home").asText());
```

**Source:** `node/server.js:5523`

### `code`
Tells the server whether your character runs code, so that the server can show it.

<!-- schema -->

**Notes:** `code` also passes while a cave conversation pauses your instance.

**Example:**

```js
// sock: a connected AlSocket
// No game_response: read the next `player` update.
const reply = sock.waitFor("player", undefined, 5000); // register first
sock.emit("code", { run: true });
const d = await reply;
console.log("code flag:", d.code);
```

```ts
// No game_response: read the next `player` update.
interface PlayerData { code?: boolean }
const reply = sock.waitFor<PlayerData>("player", undefined, 5000);
sock.emit("code", { run: true });
const d = await reply;
console.log("code flag:", d.code);
```

```python
# No game_response: read the next `player` update.
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("player")
await sock.emit("code", {"run": True})
d = await reply
print("code flag:", d.get("code"))
```

```go
// No game_response: read the next `player` update.
wait := sock.Expect("player", nil) // registers now, before the emit
if err := sock.Emit("code", map[string]any{"run": true}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
raw, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var d struct {
	Code bool `json:"code"`
}
_ = json.Unmarshal(raw, &d)
fmt.Println("code flag:", d.Code)
```

```csharp
// No game_response: read the next `player` update.
var reply = sock.WaitForAsync("player", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("code", new { run = true });
var d = await reply;
Console.WriteLine($"code flag: {(d.TryGetProperty("code", out var code) ? code.ToString() : "-")}");
```

```rust
// No game_response: read the next `player` update.
let wait = sock.wait_for("player", |_| true);
sock.emit("code", json!({"run": true})).await?;
let d = wait.await?;
println!("code flag: {}", d["code"]);
```

```java
// No game_response: read the next `player` update.
var reply = sock.waitFor("player", x -> true, Duration.ofSeconds(5));
sock.emit("code", Map.of("run", true));
JsonNode d = reply.get(); // throws if no reply in 5 s
System.out.println("code flag:" + " " + d.path("code").asText());
```

**Source:** `node/server.js:5536`

### `property`
Changes the presence flags: the "typing" indicator or the AFK status.

<!-- schema -->

**Limits:** The handler gives back the call cost when `afk` changes. It also does this when it sets `typing`, unless 3,000 ms or more of `typing` remain.

**Notes:** `property` also passes while a cave conversation pauses your instance.

**Example:**

```js
// sock: a connected AlSocket
// A `player` update comes only if a flag changed.
const reply = sock.waitFor("player", undefined, 5000); // register first
sock.emit("property", { afk: true });
const d = await reply;
console.log("afk:", d.afk);
```

```ts
// A `player` update comes only if a flag changed.
interface PlayerData { afk?: unknown }
const reply = sock.waitFor<PlayerData>("player", undefined, 5000);
sock.emit("property", { afk: true });
const d = await reply;
console.log("afk:", d.afk);
```

```python
# A `player` update comes only if a flag changed.
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("player")
await sock.emit("property", {"afk": True})
d = await reply
print("afk:", d.get("afk"))
```

```go
// A `player` update comes only if a flag changed.
wait := sock.Expect("player", nil) // registers now, before the emit
if err := sock.Emit("property", map[string]any{"afk": true}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
raw, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var d struct {
	Afk json.RawMessage `json:"afk"`
}
_ = json.Unmarshal(raw, &d)
fmt.Println("afk:", string(d.Afk))
```

```csharp
// A `player` update comes only if a flag changed.
var reply = sock.WaitForAsync("player", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("property", new { afk = true });
var d = await reply;
Console.WriteLine($"afk: {(d.TryGetProperty("afk", out var afk) ? afk.ToString() : "-")}");
```

```rust
// A `player` update comes only if a flag changed.
let wait = sock.wait_for("player", |_| true);
sock.emit("property", json!({"afk": true})).await?;
let d = wait.await?;
println!("afk: {}", d["afk"]);
```

```java
// A `player` update comes only if a flag changed.
var reply = sock.waitFor("player", x -> true, Duration.ofSeconds(5));
sock.emit("property", Map.of("afk", true));
JsonNode d = reply.get(); // throws if no reply in 5 s
System.out.println("afk:" + " " + d.path("afk"));
```

**Source:** `node/server.js:5548`

### `cruise`
Sets a cruise speed (a speed limit) for your character. The payload is a bare number, not an object.

<!-- schema -->

**Limits:** Call cost: 11 (1, plus 10 from `CC`).

**Example:**

```js
// sock: a connected AlSocket
// The payload is a bare number, not an object.
const reply = sock.waitFor("game_response", (r) => r?.place === "cruise", 5000); // register first
sock.emit("cruise", 50);
const r = await reply;
if (r.failed) console.log("cruise failed:", r.response);
else console.log("cruise speed:", r.speed);
```

```ts
// The payload is a bare number, not an object.
interface CruiseReply { response: string; place: string; failed?: boolean; speed?: number }
const reply = sock.waitFor<CruiseReply>("game_response", (r) => r?.place === "cruise", 5000);
sock.emit("cruise", 50);
const r = await reply;
if (r.failed) console.log("cruise failed:", r.response);
else console.log("cruise speed:", r.speed);
```

```python
# The payload is a bare number, not an object.
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "cruise")
await sock.emit("cruise", 50)
r = await reply
if r.get("failed"):
    print("cruise failed:", r["response"])
else:
    print("cruise speed:", r.get("speed"))
```

```go
// The payload is a bare number, not an object.
type reply struct {
	Response, Place string
	Failed          bool
	Speed           float64 `json:"speed"`
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "cruise"
})
if err := sock.Emit("cruise", 50); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("cruise failed:", r.Response)
} else {
	fmt.Println("cruise speed:", r.Speed)
}
```

```csharp
// The payload is a bare number, not an object.
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("place", out var p) && p.GetString() == "cruise", TimeSpan.FromSeconds(5));
await sock.EmitAsync("cruise", 50);
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"cruise failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"cruise speed: {(r.TryGetProperty("speed", out var speed) ? speed.ToString() : "-")}");
```

```rust
// The payload is a bare number, not an object.
let wait = sock.wait_for("game_response", |r| r["place"] == "cruise");
sock.emit("cruise", json!(50)).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("cruise failed: {}", r["response"]);
} else {
    println!("cruise speed: {}", r["speed"]);
}
```

```java
// The payload is a bare number, not an object.
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("cruise"), Duration.ofSeconds(5));
sock.emit("cruise", 50);
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("cruise failed: " + r.path("response").asText());
else
    System.out.println("cruise speed:" + " " + r.path("speed").asText());
```

**Source:** `node/server.js:5575`

### `test`
Tests the connection. The server replies with its time.

<!-- schema -->

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("test", undefined, 5000); // register first
sock.emit("test", { test: "hello" });
const d = await reply;
console.log("server time:", d.date);
```

```ts
interface TestData { date?: string }
const reply = sock.waitFor<TestData>("test", undefined, 5000);
sock.emit("test", { test: "hello" });
const d = await reply;
console.log("server time:", d.date);
```

```python
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("test")
await sock.emit("test", {"test": "hello"})
d = await reply
print("server time:", d.get("date"))
```

```go
wait := sock.Expect("test", nil) // registers now, before the emit
if err := sock.Emit("test", map[string]any{"test": "hello"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
raw, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var d struct {
	Date string `json:"date"`
}
_ = json.Unmarshal(raw, &d)
fmt.Println("server time:", d.Date)
```

```csharp
var reply = sock.WaitForAsync("test", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("test", new { test = "hello" });
var d = await reply;
Console.WriteLine($"server time: {(d.TryGetProperty("date", out var date) ? date.ToString() : "-")}");
```

```rust
let wait = sock.wait_for("test", |_| true);
sock.emit("test", json!({"test": "hello"})).await?;
let d = wait.await?;
println!("server time: {}", d["date"]);
```

```java
var reply = sock.waitFor("test", x -> true, Duration.ofSeconds(5));
sock.emit("test", Map.of("test", "hello"));
JsonNode d = reply.get(); // throws if no reply in 5 s
System.out.println("server time:" + " " + d.path("date").asText());
```

**Source:** `node/server.js:5584`

### `blocker`
Asks if a gated feature is open. The handler knows only the PvP arena.

<!-- schema -->

**Example:**

```js
// sock: a connected AlSocket
// `allow` is 1 if the arena is open, else absent.
const reply = sock.waitFor("blocker", undefined, 5000); // register first
sock.emit("blocker", { type: "pvp" });
const d = await reply;
console.log("arena allow:", d.allow);
```

```ts
// `allow` is 1 if the arena is open, else absent.
interface BlockerData { allow?: unknown }
const reply = sock.waitFor<BlockerData>("blocker", undefined, 5000);
sock.emit("blocker", { type: "pvp" });
const d = await reply;
console.log("arena allow:", d.allow);
```

```python
# `allow` is 1 if the arena is open, else absent.
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("blocker")
await sock.emit("blocker", {"type": "pvp"})
d = await reply
print("arena allow:", d.get("allow"))
```

```go
// `allow` is 1 if the arena is open, else absent.
wait := sock.Expect("blocker", nil) // registers now, before the emit
if err := sock.Emit("blocker", map[string]any{"type": "pvp"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
raw, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var d struct {
	Allow json.RawMessage `json:"allow"`
}
_ = json.Unmarshal(raw, &d)
fmt.Println("arena allow:", string(d.Allow))
```

```csharp
// `allow` is 1 if the arena is open, else absent.
var reply = sock.WaitForAsync("blocker", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("blocker", new { type = "pvp" });
var d = await reply;
Console.WriteLine($"arena allow: {(d.TryGetProperty("allow", out var allow) ? allow.ToString() : "-")}");
```

```rust
// `allow` is 1 if the arena is open, else absent.
let wait = sock.wait_for("blocker", |_| true);
sock.emit("blocker", json!({"type": "pvp"})).await?;
let d = wait.await?;
println!("arena allow: {}", d["allow"]);
```

```java
// `allow` is 1 if the arena is open, else absent.
var reply = sock.waitFor("blocker", x -> true, Duration.ofSeconds(5));
sock.emit("blocker", Map.of("type", "pvp"));
JsonNode d = reply.get(); // throws if no reply in 5 s
System.out.println("arena allow:" + " " + d.path("allow"));
```

**Source:** `node/server.js:5590`

### `mail_take_item`
Takes the item (or the gold) attached to a mail message and puts it in your inventory.

<!-- schema -->

**Notes:**
- **Server bug:** for an attachment that is not a valid item, the handler calls `ex("invalid_item")` outside a transaction. `ex` does not exist there, so this ends as `reason: "coms_failure"`.
- The server marks the mail with a claim before it adds the item. If it cannot add the item, it releases the claim.

**Example:**

```js
// sock: a connected AlSocket
// Replies have no `place`: match on the mail `id`.
const reply = sock.waitFor("game_response", (r) => r?.id === "ML_abc123", 5000); // register first
sock.emit("mail_take_item", { id: "ML_abc123" });
const r = await reply;
if (r.failed) console.log("mail_take_item failed:", r.response, r.reason);
else console.log("took item / gold:", r.item, r.gold);
```

```ts
// Replies have no `place`: match on the mail `id`.
interface MailTakeItemReply { response: string; id: string; failed?: boolean; item?: unknown; gold?: unknown; reason?: string }
const reply = sock.waitFor<MailTakeItemReply>("game_response", (r) => r?.id === "ML_abc123", 5000);
sock.emit("mail_take_item", { id: "ML_abc123" });
const r = await reply;
if (r.failed) console.log("mail_take_item failed:", r.response, r.reason);
else console.log("took item / gold:", r.item, r.gold);
```

```python
# Replies have no `place`: match on the mail `id`.
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("id") == "ML_abc123")
await sock.emit("mail_take_item", {"id": "ML_abc123"})
r = await reply
if r.get("failed"):
    print("mail_take_item failed:", r["response"], r.get("reason"))
else:
    print("took item / gold:", r.get("item"), r.get("gold"))
```

```go
// Replies have no `place`: match on the mail `id`.
type reply struct {
	Response, Id string
	Failed       bool
	Item         json.RawMessage `json:"item"`
	Gold         json.RawMessage `json:"gold"`
	Reason       string          `json:"reason"`
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Id == "ML_abc123"
})
if err := sock.Emit("mail_take_item", map[string]any{"id": "ML_abc123"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("mail_take_item failed:", r.Response, r.Reason)
} else {
	fmt.Println("took item / gold:", string(r.Item), string(r.Gold))
}
```

```csharp
// Replies have no `place`: match on the mail `id`.
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("id", out var p) && p.GetString() == "ML_abc123", TimeSpan.FromSeconds(5));
await sock.EmitAsync("mail_take_item", new { id = "ML_abc123" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"mail_take_item failed: {r.GetProperty("response")} {(r.TryGetProperty("reason", out var reason) ? reason.ToString() : "-")}");
else
    Console.WriteLine($"took item / gold: {(r.TryGetProperty("item", out var item) ? item.ToString() : "-")} {(r.TryGetProperty("gold", out var gold) ? gold.ToString() : "-")}");
```

```rust
// Replies have no `place`: match on the mail `id`.
let wait = sock.wait_for("game_response", |r| r["id"] == "ML_abc123");
sock.emit("mail_take_item", json!({"id": "ML_abc123"})).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("mail_take_item failed: {} {}", r["response"], r["reason"]);
} else {
    println!("took item / gold: {} {}", r["item"], r["gold"]);
}
```

```java
// Replies have no `place`: match on the mail `id`.
var reply = sock.waitFor("game_response", r -> r.path("id").asText().equals("ML_abc123"), Duration.ofSeconds(5));
sock.emit("mail_take_item", Map.of("id", "ML_abc123"));
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("mail_take_item failed: " + r.path("response").asText() + " " + r.path("reason").asText());
else
    System.out.println("took item / gold:" + " " + r.path("item") + " " + r.path("gold"));
```

**Source:** `node/server.js:5599`

### `mail`
Sends mail to a character, with the item in inventory slot 0 if you ask for it. It costs 48,000 gold, or 360,000 gold with an item.

<!-- schema -->

**Limits:** 48,000 gold per mail, or 360,000 gold with an item. The server takes the gold after all checks.

**Notes:**
- The server does not give the gold back if the delivery fails.
- For `coms_failure`, an attached item is always lost.
- A missing or non-string `to` throws before the first database call. Thus `mail_failed` with `coms_failure` comes first, before `player` and `mail_sending`.

**Example:**

```js
// sock: a connected AlSocket
// Register both waits first. The second reply has no `place`; match on `to`.
const first = sock.waitFor("game_response", (r) => r?.place === "mail", 5000);
const later = sock.waitFor("game_response", (r) => r?.to === "SomePlayer" && !!r.cevent, 30000);
sock.emit("mail", { to: "SomePlayer", subject: "Hi", message: "Here you go", item: true });
const r = await first;
if (r.failed) return console.log("mail failed:", r.response);
const done = await later; // mail_sent or mail_failed
console.log(done.response, done.reason ?? "");
```

```ts
interface MailReply { response: string; place?: string; failed?: boolean; to?: string; cevent?: string; reason?: string }
// Register both waits first. The second reply has no `place`; match on `to`.
const first = sock.waitFor<MailReply>("game_response", (r) => r?.place === "mail", 5000);
const later = sock.waitFor<MailReply>("game_response", (r) => r?.to === "SomePlayer" && !!r.cevent, 30000);
sock.emit("mail", { to: "SomePlayer", subject: "Hi", message: "Here you go", item: true });
const r = await first;
if (r.failed) return console.log("mail failed:", r.response);
const done = await later; // mail_sent or mail_failed
console.log(done.response, done.reason ?? "");
```

```python
# Start both waits first. The second reply has no `place`; match on `to`.
first = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "mail")
later = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("to") == "SomePlayer" and "cevent" in r, timeout=30)
await sock.emit("mail", {"to": "SomePlayer", "subject": "Hi", "message": "Here you go", "item": True})
r = await first
if r.get("failed"):
    later.close()  # drop the second wait; it ends with its timeout
    print("mail failed:", r["response"])
    return
done = await later  # mail_sent or mail_failed
print(done["response"], done.get("reason"))
```

```go
type reply struct {
	Response, Place, To, Cevent, Reason string
	Failed                              bool
}
match := func(ok func(reply) bool) func(json.RawMessage) bool {
	return func(d json.RawMessage) bool { var r reply; return json.Unmarshal(d, &r) == nil && ok(r) }
}
// Register both waits first. The second reply has no `place`; match on `to`.
first := sock.Expect("game_response", match(func(r reply) bool { return r.Place == "mail" }))
later := sock.Expect("game_response", match(func(r reply) bool { return r.To == "SomePlayer" && r.Cevent != "" }))
if err := sock.Emit("mail", map[string]any{"to": "SomePlayer", "subject": "Hi", "message": "Here you go", "item": true}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
defer cancel()
var r reply
d, err := first(ctx)
if _ = json.Unmarshal(d, &r); err != nil || r.Failed {
	fmt.Println("mail failed:", r.Response)
	return err
}
if d, err = later(ctx); err != nil { // mail_sent or mail_failed
	return err
}
_ = json.Unmarshal(d, &r)
fmt.Println(r.Response, r.Reason)
```

```csharp
static string Str(JsonElement r, string k) => r.ValueKind == JsonValueKind.Object && r.TryGetProperty(k, out var v) ? v.ToString() : "";
// Register both waits first. The second reply has no `place`; match on `to`.
var first = sock.WaitForAsync("game_response", x => Str(x, "place") == "mail", TimeSpan.FromSeconds(5));
var later = sock.WaitForAsync("game_response", x => Str(x, "to") == "SomePlayer" && Str(x, "cevent") != "", TimeSpan.FromSeconds(30));
await sock.EmitAsync("mail", new { to = "SomePlayer", subject = "Hi", message = "Here you go", item = true });
var r = await first;
if (Str(r, "failed") != "") { Console.WriteLine($"mail failed: {Str(r, "response")}"); return; }
var done = await later; // mail_sent or mail_failed
Console.WriteLine($"{Str(done, "response")} {Str(done, "reason")}");
```

```rust
// Register both waits first. The second reply has no `place`; match on `to`.
let first = sock.wait_for_timeout("game_response", |r| r["place"] == "mail", Duration::from_secs(5));
let later = sock.wait_for_timeout("game_response", |r| r["to"] == "SomePlayer" && r.get("cevent").is_some(), Duration::from_secs(30));
sock.emit("mail", json!({"to": "SomePlayer", "subject": "Hi", "message": "Here you go", "item": true})).await?;
let r = first.await?;
if r["failed"] == true {
    println!("mail failed: {}", r["response"]);
    return Ok(());
}
let done = later.await?; // mail_sent or mail_failed
println!("{} {}", done["response"], done["reason"]);
```

```java
// Register both waits first. The second reply has no `place`; match on `to`.
var first = sock.waitFor("game_response", r -> r.path("place").asText().equals("mail"), Duration.ofSeconds(5));
var later = sock.waitFor("game_response", r -> r.path("to").asText().equals("SomePlayer") && r.has("cevent"), Duration.ofSeconds(30));
sock.emit("mail", Map.of("to", "SomePlayer", "subject", "Hi", "message", "Here you go", "item", true));
JsonNode r = first.get();
if (r.path("failed").asBoolean()) {
    System.out.println("mail failed: " + r.path("response").asText());
    return;
}
JsonNode done = later.get(); // mail_sent or mail_failed
System.out.println(done.path("response").asText() + " " + done.path("reason").asText());
```

**Source:** `node/server.js:5708`

### `leave`
Leaves the jail, `cyberland`, a solo instance or the Cave of Many Dreams. It sends you back to the start map.

<!-- schema -->

**Notes:** In a cave map, the handler checks nothing: it removes you from the run even when you cannot walk.

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("game_response", (r) => r?.place === "leave", 5000); // register first
sock.emit("leave", {});
const r = await reply;
if (r.failed) console.log("leave failed:", r.response);
else console.log("left, now in main");
```

```ts
interface LeaveReply { response: string; place: string; failed?: boolean }
const reply = sock.waitFor<LeaveReply>("game_response", (r) => r?.place === "leave", 5000);
sock.emit("leave", {});
const r = await reply;
if (r.failed) console.log("leave failed:", r.response);
else console.log("left, now in main");
```

```python
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "leave")
await sock.emit("leave", {})
r = await reply
if r.get("failed"):
    print("leave failed:", r["response"])
else:
    print("left, now in main")
```

```go
type reply struct {
	Response, Place string
	Failed          bool
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "leave"
})
if err := sock.Emit("leave", map[string]any{}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("leave failed:", r.Response)
} else {
	fmt.Println("left, now in main")
}
```

```csharp
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("place", out var p) && p.GetString() == "leave", TimeSpan.FromSeconds(5));
await sock.EmitAsync("leave", new { });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"leave failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"left, now in main");
```

```rust
let wait = sock.wait_for("game_response", |r| r["place"] == "leave");
sock.emit("leave", json!({})).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("leave failed: {}", r["response"]);
} else {
    println!("left, now in main");
}
```

```java
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("leave"), Duration.ofSeconds(5));
sock.emit("leave", Map.of());
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("leave failed: " + r.path("response").asText());
else
    System.out.println("left, now in main");
```

**Source:** `node/server.js:5864`, `node/logic/generated_maps.js:230`

### `transport`
Moves you through a door, or uses the Transporter NPC to go to a different map. It also starts entry to and exit from the bank.

<!-- schema -->

**Limits:** Door range `B.door_dist` (112 px). Transporter range `B.transporter_dist` (160 px). Bank entry costs 32 call-cost, bank exit 16.

**Notes:**
- GMs, and characters in `woffice` on a `hardcore` server, skip both distance checks and count as Transporter users.
- A failed bank exit disconnects the socket with no reply (`not_in_game` or `bank_owner_lost`, node/server.js:16700-16703).

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("game_response", (r) => r?.place === "transport", 5000); // register first
sock.emit("transport", { to: "winterland", s: 1 });
const r = await reply;
if (r.failed) console.log("transport failed:", r.response, r.reason);
else console.log("moved; bank mount in progress:", r.in_progress);
```

```ts
interface TransportReply { response: string; place: string; failed?: boolean; in_progress?: boolean; reason?: string }
const reply = sock.waitFor<TransportReply>("game_response", (r) => r?.place === "transport", 5000);
sock.emit("transport", { to: "winterland", s: 1 });
const r = await reply;
if (r.failed) console.log("transport failed:", r.response, r.reason);
else console.log("moved; bank mount in progress:", r.in_progress);
```

```python
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "transport")
await sock.emit("transport", {"to": "winterland", "s": 1})
r = await reply
if r.get("failed"):
    print("transport failed:", r["response"], r.get("reason"))
else:
    print("moved; bank mount in progress:", r.get("in_progress"))
```

```go
type reply struct {
	Response, Place string
	Failed          bool
	InProgress      bool   `json:"in_progress"`
	Reason          string `json:"reason"`
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "transport"
})
if err := sock.Emit("transport", map[string]any{"to": "winterland", "s": 1}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("transport failed:", r.Response, r.Reason)
} else {
	fmt.Println("moved; bank mount in progress:", r.InProgress)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("place", out var p) && p.GetString() == "transport", TimeSpan.FromSeconds(5));
await sock.EmitAsync("transport", new { to = "winterland", s = 1 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"transport failed: {r.GetProperty("response")} {(r.TryGetProperty("reason", out var reason) ? reason.ToString() : "-")}");
else
    Console.WriteLine($"moved; bank mount in progress: {(r.TryGetProperty("in_progress", out var inProgress) ? inProgress.ToString() : "-")}");
```

```rust
let wait = sock.wait_for("game_response", |r| r["place"] == "transport");
sock.emit("transport", json!({"to": "winterland", "s": 1})).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("transport failed: {} {}", r["response"], r["reason"]);
} else {
    println!("moved; bank mount in progress: {}", r["in_progress"]);
}
```

```java
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("transport"), Duration.ofSeconds(5));
sock.emit("transport", Map.of("to", "winterland", "s", 1));
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("transport failed: " + r.path("response").asText() + " " + r.path("reason").asText());
else
    System.out.println("moved; bank mount in progress:" + " " + r.path("in_progress").asText());
```

**Source:** `node/server.js:5887`, `node/logic/generated_maps.js:149`

### `enter`
Enters an instanced dungeon (crypt, winter instance, spider instance, tomb), the Cave of Many Dreams, or a duel as a spectator. A key item makes a new dungeon instance. `name` joins an instance that exists.

<!-- schema -->

**Limits:** 120 px from the dungeon entrance. One key per new dungeon instance.

**Notes:**
- `place: "dreams"` uses `enter_dreams` (node/logic/generated_maps.js:578). Its replies have no `response` field.
- If a run of yours exists and you left it by a disconnect, `enter_dreams` puts you back in that run.
- The GM place `cgallery` makes a solo gallery instance with NPCs that show each cosmetic.

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("game_response", (r) => r?.place === "enter", 5000); // register first
sock.emit("enter", { place: "crypt" });
const r = await reply;
if (r.failed) console.log("enter failed:", r.response);
else console.log("entered a new crypt instance");
```

```ts
interface EnterReply { response: string; place: string; failed?: boolean }
const reply = sock.waitFor<EnterReply>("game_response", (r) => r?.place === "enter", 5000);
sock.emit("enter", { place: "crypt" });
const r = await reply;
if (r.failed) console.log("enter failed:", r.response);
else console.log("entered a new crypt instance");
```

```python
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "enter")
await sock.emit("enter", {"place": "crypt"})
r = await reply
if r.get("failed"):
    print("enter failed:", r["response"])
else:
    print("entered a new crypt instance")
```

```go
type reply struct {
	Response, Place string
	Failed          bool
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "enter"
})
if err := sock.Emit("enter", map[string]any{"place": "crypt"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("enter failed:", r.Response)
} else {
	fmt.Println("entered a new crypt instance")
}
```

```csharp
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("place", out var p) && p.GetString() == "enter", TimeSpan.FromSeconds(5));
await sock.EmitAsync("enter", new { place = "crypt" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"enter failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"entered a new crypt instance");
```

```rust
let wait = sock.wait_for("game_response", |r| r["place"] == "enter");
sock.emit("enter", json!({"place": "crypt"})).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("enter failed: {}", r["response"]);
} else {
    println!("entered a new crypt instance");
}
```

```java
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("enter"), Duration.ofSeconds(5));
sock.emit("enter", Map.of("place", "crypt"));
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("enter failed: " + r.path("response").asText());
else
    System.out.println("entered a new crypt instance");
```

**Source:** `node/server.js:6058`, `node/logic/generated_maps.js:578`, `node/logic/generated_maps.js:434`

### `town`
Starts the "town" channel. When it ends, it teleports you to spawn 0 of your current map.

<!-- schema -->

**Limits:** 3,000 ms channel.

**Notes:**
- A `move` does not stop the channel: `G.conditions.town.can_move` is `true`. `stop` with `action` `"town"`, `"teleport"` or `"channeling"` stops it (node/server.js:12672-12684).
- A second `town` while the channel runs does not restart it.

**Example:**

```js
// sock: a connected AlSocket
// Success has success: false and in_progress: true.
const reply = sock.waitFor("game_response", (r) => r?.place === "town", 5000); // register first
sock.emit("town", {});
const r = await reply;
if (r.failed) console.log("town failed:", r.response);
else console.log("town channel started (3 s)");
```

```ts
// Success has success: false and in_progress: true.
interface TownReply { response: string; place: string; failed?: boolean }
const reply = sock.waitFor<TownReply>("game_response", (r) => r?.place === "town", 5000);
sock.emit("town", {});
const r = await reply;
if (r.failed) console.log("town failed:", r.response);
else console.log("town channel started (3 s)");
```

```python
# Success has success: false and in_progress: true.
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "town")
await sock.emit("town", {})
r = await reply
if r.get("failed"):
    print("town failed:", r["response"])
else:
    print("town channel started (3 s)")
```

```go
// Success has success: false and in_progress: true.
type reply struct {
	Response, Place string
	Failed          bool
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "town"
})
if err := sock.Emit("town", map[string]any{}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("town failed:", r.Response)
} else {
	fmt.Println("town channel started (3 s)")
}
```

```csharp
// Success has success: false and in_progress: true.
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("place", out var p) && p.GetString() == "town", TimeSpan.FromSeconds(5));
await sock.EmitAsync("town", new { });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"town failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"town channel started (3 s)");
```

```rust
// Success has success: false and in_progress: true.
let wait = sock.wait_for("game_response", |r| r["place"] == "town");
sock.emit("town", json!({})).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("town failed: {}", r["response"]);
} else {
    println!("town channel started (3 s)");
}
```

```java
// Success has success: false and in_progress: true.
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("town"), Duration.ofSeconds(5));
sock.emit("town", Map.of());
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("town failed: " + r.path("response").asText());
else
    System.out.println("town channel started (3 s)");
```

**Source:** `node/server.js:6254`

### `respawn`
Brings your dead character back to life, at the death point of the map or, with `safe`, in `woffice`.

<!-- schema -->

**Limits:** 12,000 ms after death (`B.rip_time`). No wait on the `HARDCORE` and `TEST` servers.

**Notes:** `respawn` also passes while a cave conversation pauses your instance.

**Example:**

```js
// sock: a connected AlSocket
const reply = sock.waitFor("game_response", (r) => r?.place === "respawn", 5000); // register first
sock.emit("respawn", {});
const r = await reply;
if (r.failed) console.log("respawn failed:", r.response, r.ms);
else console.log("respawned");
```

```ts
interface RespawnReply { response: string; place: string; failed?: boolean; ms?: number }
const reply = sock.waitFor<RespawnReply>("game_response", (r) => r?.place === "respawn", 5000);
sock.emit("respawn", {});
const r = await reply;
if (r.failed) console.log("respawn failed:", r.response, r.ms);
else console.log("respawned");
```

```python
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "respawn")
await sock.emit("respawn", {})
r = await reply
if r.get("failed"):
    print("respawn failed:", r["response"], r.get("ms"))
else:
    print("respawned")
```

```go
type reply struct {
	Response, Place string
	Failed          bool
	Ms              float64 `json:"ms"`
}
// Expect registers the waiter now, before the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "respawn"
})
if err := sock.Emit("respawn", map[string]any{}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
d, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var r reply
_ = json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("respawn failed:", r.Response, r.Ms)
} else {
	fmt.Println("respawned")
}
```

```csharp
var reply = sock.WaitForAsync("game_response", x => x.ValueKind == JsonValueKind.Object
    && x.TryGetProperty("place", out var p) && p.GetString() == "respawn", TimeSpan.FromSeconds(5));
await sock.EmitAsync("respawn", new { });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"respawn failed: {r.GetProperty("response")} {(r.TryGetProperty("ms", out var ms) ? ms.ToString() : "-")}");
else
    Console.WriteLine($"respawned");
```

```rust
let wait = sock.wait_for("game_response", |r| r["place"] == "respawn");
sock.emit("respawn", json!({})).await?;
let r = wait.await?;
if r["failed"] == true {
    println!("respawn failed: {} {}", r["response"], r["ms"]);
} else {
    println!("respawned");
}
```

```java
var reply = sock.waitFor("game_response", r -> r.path("place").asText().equals("respawn"), Duration.ofSeconds(5));
sock.emit("respawn", Map.of());
JsonNode r = reply.get(); // throws if no reply in 5 s
if (r.path("failed").asBoolean())
    System.out.println("respawn failed: " + r.path("response").asText() + " " + r.path("ms").asText());
else
    System.out.println("respawned");
```

**Source:** `node/server.js:6271`

### `random_look`
Replies with a hint to use the cosmetics gallery. This is an old handler: no code after its first line runs.

<!-- schema -->

**Limits:** Call cost: 11 (1, plus 10 from `CC`).

**Notes:** The code after the first line (a random look from body, head and hair sprites) does not run.

**Example:**

```js
// sock: a connected AlSocket
// The reply is a bare string.
const reply = sock.waitFor("game_log", undefined, 5000); // register first
sock.emit("random_look", {});
const d = await reply;
console.log("hint:", d);
```

```ts
// The reply is a bare string.
const reply = sock.waitFor<string>("game_log", undefined, 5000);
sock.emit("random_look", {});
const d = await reply;
console.log("hint:", d);
```

```python
# The reply is a bare string.
# Start the wait first, so the reply can't arrive before it.
reply = sock.wait_for("game_log")
await sock.emit("random_look", {})
d = await reply
print("hint:", d)
```

```go
// The reply is a bare string.
wait := sock.Expect("game_log", nil) // registers now, before the emit
if err := sock.Emit("random_look", map[string]any{}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
raw, err := wait(ctx)
if err != nil {
	return err // no reply in 5 s
}
var d string
_ = json.Unmarshal(raw, &d)
fmt.Println("hint:", d)
```

```csharp
// The reply is a bare string.
var reply = sock.WaitForAsync("game_log", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("random_look", new { });
var d = await reply;
Console.WriteLine($"hint: {d}");
```

```rust
// The reply is a bare string.
let wait = sock.wait_for("game_log", |_| true);
sock.emit("random_look", json!({})).await?;
let d = wait.await?;
println!("hint: {}", d);
```

```java
// The reply is a bare string.
var reply = sock.waitFor("game_log", x -> true, Duration.ofSeconds(5));
sock.emit("random_look", Map.of());
JsonNode d = reply.get(); // throws if no reply in 5 s
System.out.println("hint:" + " " + d.asText());
```

**Source:** `node/server.js:6311`
