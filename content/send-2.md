### `unlock`
Does nothing. The handler returns on its first line.

<!-- schema -->

**Example:**

```js
// The server ignores `unlock`: its handler starts with `return;`. It sends no reply.
```

```ts
// The server ignores `unlock`: its handler starts with `return;`. It sends no reply.
```

```python
# The server ignores `unlock`: its handler starts with `return;`. It sends no reply.
```

```go
// The server ignores `unlock`: its handler starts with `return;`. It sends no reply.
```

```csharp
// The server ignores `unlock`: its handler starts with `return;`. It sends no reply.
```

```rust
// The server ignores `unlock`: its handler starts with `return;`. It sends no reply.
```

```java
// The server ignores `unlock`: its handler starts with `return;`. It sends no reply.
```

**Source:** `node/server.js:6375-6440` (the `return` is at `node/server.js:6376`)

### `dismantle`
Breaks an item into parts at the Craftsman for a gold cost.

<!-- schema -->

**Limits:**
- Distance: within `B.sell_dist` (400 px) of the `craftsman` NPC on `main`. On `HARDCORE` and `TEST` the limit is 10,000,999 px.
- Compound item: the cost is `min(50,000,000, calculate_item_value(item) * 10)` gold, and you need 2 empty slots.
- Recipe: the cost is `G.dismantle[name].cost` gold.

**Notes:**
- The compound path does not check the lock `l` or the flag `b`.
- The compound path needs no `G.dismantle` recipe: any compound item at level 1 or more works, except a `booster`.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
const reply = sock.waitFor("game_response", (r) => r?.place === "dismantle");
sock.emit("dismantle", { num: 5 });
const r = await reply;
if (r.failed) console.log("dismantle failed:", r.response); // a code from the Failure table
else console.log(r.response, r.name);
```

```ts
interface DismantleReply {
  response: string;
  place: string;
  failed?: boolean;
  name: string;
  level?: number;
  cost?: number;
}
const reply = sock.waitFor<DismantleReply>("game_response", (r) => r?.place === "dismantle");
sock.emit("dismantle", { num: 5 });
const r = await reply;
if (r.failed) console.log("dismantle failed:", r.response);
else console.log(r.response, r.name);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "dismantle")
await sock.emit("dismantle", {"num": 5})
r = await reply
if r.get("failed"):
    print("dismantle failed:", r["response"])
else:
    print(r["response"], r["name"])
```

```go
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "dismantle" // a bare string fails to decode
})
if err := sock.Emit("dismantle", map[string]any{"num": 5}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Name string }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("dismantle failed:", r.Response)
} else {
	fmt.Println(r.Response, r.Name)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "dismantle");
await sock.EmitAsync("dismantle", new { num = 5 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"dismantle failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("name")}");
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "dismantle");
sock.emit("dismantle", json!({ "num": 5 })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("dismantle failed: {}", r["response"]);
} else {
    println!("{} {}", r["response"], r["name"]);
}
```

```java
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("dismantle"), Duration.ofSeconds(10));
sock.emit("dismantle", Map.of("num", 5));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("dismantle failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("name").asText());
```

**Source:** `node/server.js:6441-6513` (compound path `node/server.js:6453-6483`, recipe path `node/server.js:6484-6512`)

### `craft`
Combines inventory items by a `G.craft` recipe for a gold cost, at the Craftsman or at the quest NPC of the recipe.

<!-- schema -->

**Limits:**
- 1 to 9 ingredients.
- Distance: within `B.sell_dist` (400 px) of the `craftsman` NPC on `main`, or of the quest NPC of the recipe. On `HARDCORE` and `TEST` the limit is 10,000,999 px.
- Cost: `G.craft[recipe].cost` gold.

**Notes:**
- A recipe can have an `output`: the result is `output.name` with `data: output.data`. For example, `makeawishjar` gives a `cxjar` with `data: "makeawish"`.
- If an ingredient has a title (`p`) that is not a `misc` title, the result gets one of those titles at random.
- The result rolls for `p: "shiny"`: 1 in 500 for an upgrade item, 1 in 20,000 for a compound item (node/server.js:2029-2036).

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
const reply = sock.waitFor("game_response", (r) => r?.place === "craft");
sock.emit("craft", { items: [[0, 3], [1, 7]] });
const r = await reply;
if (r.failed) console.log("craft failed:", r.response); // a code from the Failure table
else console.log(r.response, r.name, r.num);
```

```ts
interface CraftReply {
  response: string;
  place: string;
  failed?: boolean;
  num?: number;
  name?: string;
}
const reply = sock.waitFor<CraftReply>("game_response", (r) => r?.place === "craft");
sock.emit("craft", { items: [[0, 3], [1, 7]] });
const r = await reply;
if (r.failed) console.log("craft failed:", r.response);
else console.log(r.response, r.name, r.num);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "craft")
await sock.emit("craft", {"items": [[0, 3], [1, 7]]})
r = await reply
if r.get("failed"):
    print("craft failed:", r["response"])
else:
    print(r["response"], r["name"], r["num"])
```

```go
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "craft" // a bare string fails to decode
})
if err := sock.Emit("craft", map[string]any{"items": [][]int{{0, 3}, {1, 7}}}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Name string; Num int }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("craft failed:", r.Response)
} else {
	fmt.Println(r.Response, r.Name, r.Num)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "craft");
await sock.EmitAsync("craft", new { items = new[] { new[] { 0, 3 }, new[] { 1, 7 } } });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"craft failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("name")} {r.GetProperty("num")}");
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "craft");
sock.emit("craft", json!({ "items": [[0, 3], [1, 7]] })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("craft failed: {}", r["response"]);
} else {
    println!("{} {} {}", r["response"], r["name"], r["num"]);
}
```

```java
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("craft"), Duration.ofSeconds(10));
sock.emit("craft", Map.of("items", List.of(List.of(0, 3), List.of(1, 7))));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("craft failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("name").asText() + " " + r.path("num").asText());
```

**Source:** `node/server.js:6514-6616` (payload check `node/server.js:6527-6537`, recipe lookup `node/server.js:6565-6568`, anniversary check `node/server.js:6569-6572`)

### `exchange`
Starts the exchange of an item, or of `e` units of a stack, for a random drop at Xyn or at a quest NPC.

<!-- schema -->

**Limits:**
- One exchange at a time for each character (`q.exchange`).
- Distance: within `B.sell_dist` (400 px) of Xyn (the exchange NPC on `main`), or of the quest NPC of the item. On `HARDCORE` and `TEST` the limit is 10,000,999 px.
- Timer: 3,000 to 6,000 ms at random (400 ms on `hardcore`). `massexchange` halves it. `massexchangepp` divides it by 10. The exchange removes the condition.

**Notes:**
- A row of a drop table is `[weight, kind, value, data, property]`. `kind` is `"gold"`, `"shells"`, `"empty"`, `"cx"`, `"cxbundle"`, `"open"` (roll the table `value`), or an item name with the quantity `value` (node/server_functions.js:4056-4141).
- After a roll that gives something, each row of the table `<id>_bonus` rolls once with its own chance. Each can add a result (node/server_functions.js:4145-4148).
- For the `cosmo*` tables, the server divides the weight of a cosmetic by 10 for each copy that you own.
- The `glitch` table adds the `glitched` title to upgrade, compound and character-slot items.
- The result items keep the PvP mark `v` of the exchanged item.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
// Success here means started: the drop comes 3-6 s later (game_log, player).
const reply = sock.waitFor("game_response", (r) => r?.place === "exchange");
sock.emit("exchange", { item_num: 4 });
const r = await reply;
if (r.failed) console.log("exchange failed:", r.response); // a code from the Failure table
else console.log(r.response, r.num);
```

```ts
interface ExchangeReply {
  response: string;
  place: string;
  failed?: boolean;
  in_progress?: boolean;
  num?: number;
}
// Success here means started: the drop comes 3-6 s later (game_log, player).
const reply = sock.waitFor<ExchangeReply>("game_response", (r) => r?.place === "exchange");
sock.emit("exchange", { item_num: 4 });
const r = await reply;
if (r.failed) console.log("exchange failed:", r.response);
else console.log(r.response, r.num);
```

```python
# Success here means started: the drop comes 3-6 s later (game_log, player).
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "exchange")
await sock.emit("exchange", {"item_num": 4})
r = await reply
if r.get("failed"):
    print("exchange failed:", r["response"])
else:
    print(r["response"], r["num"])
```

```go
// Success here means started: the drop comes 3-6 s later (game_log, player).
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "exchange" // a bare string fails to decode
})
if err := sock.Emit("exchange", map[string]any{"item_num": 4}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Num int }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("exchange failed:", r.Response)
} else {
	fmt.Println(r.Response, r.Num)
}
```

```csharp
// Success here means started: the drop comes 3-6 s later (game_log, player).
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "exchange");
await sock.EmitAsync("exchange", new { item_num = 4 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"exchange failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("num")}");
```

```rust
// Success here means started: the drop comes 3-6 s later (game_log, player).
let reply = sock.wait_for("game_response", |r| r["place"] == "exchange");
sock.emit("exchange", json!({ "item_num": 4 })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("exchange failed: {}", r["response"]);
} else {
    println!("{} {}", r["response"], r["num"]);
}
```

```java
// Success here means started: the drop comes 3-6 s later (game_log, player).
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("exchange"), Duration.ofSeconds(10));
sock.emit("exchange", Map.of("item_num", 4));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("exchange failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("num").asText());
```

**Source:** `node/server.js:6617-6681` (timer end `node/server.js:14813-14826`, drop roll `node/server_functions.js:4029-4149`)

### `exchange_buy`
Spends token items (for example `monstertoken` or `funtoken`) at their NPC for an item from the `G.tokens` price list.

<!-- schema -->

**Limits:** Distance: within `B.sell_dist` (400 px) of the NPC of the token on `main`. On `HARDCORE` and `TEST` the limit is 10,000,999 px.

**Notes:**
- A price below 1 means that 1 token gives `parseInt(1 / price)` units. For example, `confetti` costs 0.01 `funtoken`, so 1 `funtoken` gives 100 `confetti`.
- The item rolls for `p: "shiny"`: 1 in 500 for an upgrade item, 1 in 20,000 for a compound item. The server sends no announcement.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
const reply = sock.waitFor("game_response", (r) => r?.place === "exchange_buy");
sock.emit("exchange_buy", { num: 2, name: "rabbitsfoot", q: 140 });
const r = await reply;
if (r.failed) console.log("exchange_buy failed:", r.response); // a code from the Failure table
else console.log(r.response, r.num);
```

```ts
interface ExchangeBuyReply {
  response: string;
  place: string;
  failed?: boolean;
  num?: number;
}
const reply = sock.waitFor<ExchangeBuyReply>("game_response", (r) => r?.place === "exchange_buy");
sock.emit("exchange_buy", { num: 2, name: "rabbitsfoot", q: 140 });
const r = await reply;
if (r.failed) console.log("exchange_buy failed:", r.response);
else console.log(r.response, r.num);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "exchange_buy")
await sock.emit("exchange_buy", {"num": 2, "name": "rabbitsfoot", "q": 140})
r = await reply
if r.get("failed"):
    print("exchange_buy failed:", r["response"])
else:
    print(r["response"], r["num"])
```

```go
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "exchange_buy" // a bare string fails to decode
})
if err := sock.Emit("exchange_buy", map[string]any{"num": 2, "name": "rabbitsfoot", "q": 140}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Num int }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("exchange_buy failed:", r.Response)
} else {
	fmt.Println(r.Response, r.Num)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "exchange_buy");
await sock.EmitAsync("exchange_buy", new { num = 2, name = "rabbitsfoot", q = 140 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"exchange_buy failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("num")}");
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "exchange_buy");
sock.emit("exchange_buy", json!({ "num": 2, "name": "rabbitsfoot", "q": 140 })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("exchange_buy failed: {}", r["response"]);
} else {
    println!("{} {}", r["response"], r["num"]);
}
```

```java
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("exchange_buy"), Duration.ofSeconds(10));
sock.emit("exchange_buy", Map.of("num", 2, "name", "rabbitsfoot", "q", 140));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("exchange_buy failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("num").asText());
```

**Source:** `node/server.js:6682-6740` (prices: `G.tokens`)

### `destat`
Removes the stat (`stat_type`) of an item at the Scrollsmith (desertland) for gold, and gives back the matching stat scrolls.

<!-- schema -->

**Limits:**
- Distance: within `B.sell_dist` (400 px) of the `scrollsmith` NPC on `desertland`. On `HARDCORE` and `TEST` the limit is 10,000,999 px.
- Cost: `needed * G.items[scroll].g * 10` gold. `needed` is `[1, 10, 100, 1000, 9999, 9999, 9999][grade]` scrolls, by the grade of the item at level 0. For example, an `int` stat on a grade-0 item costs `1 * 8,000 * 10` = 80,000 gold.

**Notes:** The server does not check the lock `l`.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
// With request_id, the success reply has scroll, quantity and cost.
const reply = sock.waitFor("game_response", (r) => r?.place === "destat");
sock.emit("destat", { num: 3, request_id: "destat-1" });
const r = await reply;
if (r.failed) console.log("destat failed:", r.response); // a code from the Failure table
else console.log(r.response, r.scroll, r.quantity, r.cost);
```

```ts
interface DestatReply {
  response: string;
  place: string;
  failed?: boolean;
  request_id?: string;
  num?: number;
  cost?: number;
  scroll?: string;
  quantity?: number;
}
// With request_id, the success reply has scroll, quantity and cost.
const reply = sock.waitFor<DestatReply>("game_response", (r) => r?.place === "destat");
sock.emit("destat", { num: 3, request_id: "destat-1" });
const r = await reply;
if (r.failed) console.log("destat failed:", r.response);
else console.log(r.response, r.scroll, r.quantity, r.cost);
```

```python
# With request_id, the success reply has scroll, quantity and cost.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "destat")
await sock.emit("destat", {"num": 3, "request_id": "destat-1"})
r = await reply
if r.get("failed"):
    print("destat failed:", r["response"])
else:
    print(r["response"], r["scroll"], r["quantity"], r["cost"])
```

```go
// With request_id, the success reply has scroll, quantity and cost.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "destat" // a bare string fails to decode
})
if err := sock.Emit("destat", map[string]any{"num": 3, "request_id": "destat-1"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Scroll string; Quantity int; Cost float64 }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("destat failed:", r.Response)
} else {
	fmt.Println(r.Response, r.Scroll, r.Quantity, r.Cost)
}
```

```csharp
// With request_id, the success reply has scroll, quantity and cost.
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "destat");
await sock.EmitAsync("destat", new { num = 3, request_id = "destat-1" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"destat failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("scroll")} {r.GetProperty("quantity")} {r.GetProperty("cost")}");
```

```rust
// With request_id, the success reply has scroll, quantity and cost.
let reply = sock.wait_for("game_response", |r| r["place"] == "destat");
sock.emit("destat", json!({ "num": 3, "request_id": "destat-1" })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("destat failed: {}", r["response"]);
} else {
    println!("{} {} {} {}", r["response"], r["scroll"], r["quantity"], r["cost"]);
}
```

```java
// With request_id, the success reply has scroll, quantity and cost.
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("destat"), Duration.ofSeconds(10));
sock.emit("destat", Map.of("num", 3, "request_id", "destat-1"));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("destat failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("scroll").asText() + " " + r.path("quantity").asText() + " " + r.path("cost").asText());
```

**Source:** `node/server.js:6742-6790` (cost `node/server.js:6766-6768`)

### `locksmith`
Locks, seals or unlocks an item at the Locksmith (desertland).

<!-- schema -->

**Limits:**
- Distance: within `B.sell_dist` (400 px) of the `locksmith` NPC on `desertland`. On `HARDCORE` and `TEST` the limit is 10,000,999 px.
- `lock`, `seal` and the first `unlock` of a sealed item cost 250,000 gold each. The last step of an unseal is free.
- An unseal takes 2 days.

**Notes:**
- `seal` does not check the `l` value now. A seal during an unseal starts the seal again. A seal of a sealed item costs 250,000 gold again.
- While an unseal runs, the item has `ld`: a JSON date string of the end time. The server sends it in `items`, but `ItemInstance` does not list it.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
// "locksmith_unsealing" (success: false, in_progress: true) is not a failure.
const reply = sock.waitFor("game_response", (r) => r?.place === "locksmith");
sock.emit("locksmith", { num: 6, operation: "lock" });
const r = await reply;
if (r.failed) console.log("locksmith failed:", r.response); // a code from the Failure table
else console.log(r.response);
```

```ts
interface LocksmithReply {
  response: string;
  place: string;
  failed?: boolean;
  reason?: string;
  hours?: number;
  in_progress?: boolean;
}
// "locksmith_unsealing" (success: false, in_progress: true) is not a failure.
const reply = sock.waitFor<LocksmithReply>("game_response", (r) => r?.place === "locksmith");
sock.emit("locksmith", { num: 6, operation: "lock" });
const r = await reply;
if (r.failed) console.log("locksmith failed:", r.response);
else console.log(r.response);
```

```python
# "locksmith_unsealing" (success: false, in_progress: true) is not a failure.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "locksmith")
await sock.emit("locksmith", {"num": 6, "operation": "lock"})
r = await reply
if r.get("failed"):
    print("locksmith failed:", r["response"])
else:
    print(r["response"])
```

```go
// "locksmith_unsealing" (success: false, in_progress: true) is not a failure.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "locksmith" // a bare string fails to decode
})
if err := sock.Emit("locksmith", map[string]any{"num": 6, "operation": "lock"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("locksmith failed:", r.Response)
} else {
	fmt.Println(r.Response)
}
```

```csharp
// "locksmith_unsealing" (success: false, in_progress: true) is not a failure.
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "locksmith");
await sock.EmitAsync("locksmith", new { num = 6, operation = "lock" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"locksmith failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")}");
```

```rust
// "locksmith_unsealing" (success: false, in_progress: true) is not a failure.
let reply = sock.wait_for("game_response", |r| r["place"] == "locksmith");
sock.emit("locksmith", json!({ "num": 6, "operation": "lock" })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("locksmith failed: {}", r["response"]);
} else {
    println!("{}", r["response"]);
}
```

```java
// "locksmith_unsealing" (success: false, in_progress: true) is not a failure.
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("locksmith"), Duration.ofSeconds(10));
sock.emit("locksmith", Map.of("num", 6, "operation", "lock"));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("locksmith failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText());
```

**Source:** `node/server.js:6791-6861`

### `compound`
Combines three identical items of the same level with a compound scroll (`cscroll`) and an optional offering. A success gives one item at level + 1. A failure destroys all three.

<!-- schema -->

**Limits:**
- One compound at a time for each character (`q.compound`).
- Distance: within `B.sell_dist` (400 px) of the compound NPC on `main`. On `HARDCORE` and `TEST` the limit is 10,000,999 px.
- Timer: 10,000 ms (1,200 ms on `hardcore`). `massproduction` halves it. `massproductionpp` divides it by 10. The compound removes the condition.
- Call cost: 1.

**Notes:**
- The server does not check the flag `b`.
- The base chance is `D.compounds[igrade][new_level]` (`design/upgrades.js:45`). `igrade` is the base grade of the item. From level 3, it is the grade at `level - 2`.
- A scroll of a higher grade: `chance * 1.1 + 0.001`, and the item gets 0.4 grace.
- With an offering, the multiplier is 1.64, 1.48, 1.36, 1.15 or 1.08, plus a grace term. The offering grade against the item grade selects the multiplier.
- Without an offering, a smaller grace term goes on top.
- The cap is `min(base * (3 + 0.6 * high), base + 0.2 + 0.05 * high)`. `high` is the grade difference of the scroll, or 1 for a better offering.
- A `booster` item always has the chance 0.9999999999999. With `gameplay` `"test"`, a compound always succeeds.
- On a success, the item keeps the first title (`p`) of the three, except `legacy`. It gets `o` (your name) when another character made it. A roll equal to the chance in its first four digits adds the `lucky` title. A `ctristone` at +1 becomes a `cdarktristone` with a chance of 1.2%.
- `q.compound.num` and the `num` of the results are `items[0]` as you sent it.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// No game_response at once on success: the result arrives as a hitchhiker
// ["game_response", {...}] in a later `player` event. A failure comes at once
// as game_response (see the Failure table); then this wait times out.
const isResult = (h) => h[0] === "game_response" && ["compound_success", "compound_fail"].includes(h[1]?.response);
const done = sock.waitFor("player", (p) => p.hitchhikers?.some(isResult), 20_000); // the compound timer is 10 s
sock.emit("compound", { items: [0, 1, 2], scroll_num: 10, clevel: 2 });
const result = (await done).hitchhikers.find(isResult)[1];
console.log(result.response, "level", result.level, "slot", result.num);
```

```ts
interface RollResult { response: string; level: number; num: number; stale?: boolean }
type Hitchhiker = [event: string, data: RollResult];
interface PlayerUpdate { hitchhikers?: Hitchhiker[] }
// No game_response at once on success: the result arrives as a hitchhiker
// ["game_response", {...}] in a later `player` event. A failure comes at once
// as game_response (see the Failure table); then this wait times out.
const isResult = (h: Hitchhiker) => h[0] === "game_response" && ["compound_success", "compound_fail"].includes(h[1]?.response);
const done = sock.waitFor<PlayerUpdate>("player", (p) => p.hitchhikers?.some(isResult) ?? false, 20_000);
sock.emit("compound", { items: [0, 1, 2], scroll_num: 10, clevel: 2 });
const result = (await done).hitchhikers!.find(isResult)![1];
console.log(result.response, "level", result.level, "slot", result.num);
```

```python
# No game_response at once on success: the result arrives as a hitchhiker
# ["game_response", {...}] in a later `player` event. A failure comes at once
# as game_response (see the Failure table); then this wait times out.
def result_of(p):
    for h in p.get("hitchhikers") or []:
        if h[0] == "game_response" and isinstance(h[1], dict) and h[1].get("response") in ("compound_success", "compound_fail"):
            return h[1]
    return None

done = sock.wait_for("player", lambda p: result_of(p) is not None, timeout=20)  # the compound timer is 10 s
await sock.emit("compound", {"items": [0, 1, 2], "scroll_num": 10, "clevel": 2})
result = result_of(await done)
print(result["response"], "level", result["level"], "slot", result["num"])
```

```go
// No game_response at once on success: the result arrives as a hitchhiker
// ["game_response", {...}] in a later `player` event. A failure comes at once
// as game_response (see the Failure table); then this wait times out.
type rollResult struct {
	Response   string
	Level, Num int
}
find := func(d json.RawMessage) (rollResult, bool) {
	var p struct{ Hitchhikers [][]json.RawMessage }
	_ = json.Unmarshal(d, &p)
	for _, h := range p.Hitchhikers {
		var r rollResult
		if len(h) == 2 && string(h[0]) == `"game_response"` && json.Unmarshal(h[1], &r) == nil &&
			(r.Response == "compound_success" || r.Response == "compound_fail") {
			return r, true
		}
	}
	return rollResult{}, false
}
wait := sock.Expect("player", func(d json.RawMessage) bool { _, ok := find(d); return ok })
if err := sock.Emit("compound", map[string]any{"items": []int{0, 1, 2}, "scroll_num": 10, "clevel": 2}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second) // the compound timer is 10 s
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
r, _ := find(data)
fmt.Println(r.Response, "level", r.Level, "slot", r.Num)
```

```csharp
// No game_response at once on success: the result arrives as a hitchhiker
// ["game_response", {...}] in a later `player` event. A failure comes at once
// as game_response (see the Failure table); then this wait times out.
JsonElement? Find(JsonElement p)
{
    if (!p.TryGetProperty("hitchhikers", out var hs)) return null;
    foreach (var h in hs.EnumerateArray())
        if (h[0].GetString() == "game_response" && h[1].ValueKind == JsonValueKind.Object
            && h[1].TryGetProperty("response", out var r) && r.GetString() is "compound_success" or "compound_fail")
            return h[1];
    return null;
}
var done = sock.WaitForAsync("player", p => Find(p) != null, TimeSpan.FromSeconds(20)); // the compound timer is 10 s
await sock.EmitAsync("compound", new { items = new[] { 0, 1, 2 }, scroll_num = 10, clevel = 2 });
var result = Find(await done)!.Value;
Console.WriteLine($"{result.GetProperty("response")} level {result.GetProperty("level")} slot {result.GetProperty("num")}");
```

```rust
// No game_response at once on success: the result arrives as a hitchhiker
// ["game_response", {...}] in a later `player` event. A failure comes at once
// as game_response (see the Failure table); then this wait times out.
fn find(p: &Value) -> Option<Value> {
    p["hitchhikers"].as_array()?.iter()
        .find(|h| h[0] == "game_response"
            && matches!(h[1]["response"].as_str(), Some("compound_success" | "compound_fail")))
        .map(|h| h[1].clone())
}
let done = sock.wait_for_timeout("player", |p| find(p).is_some(), Duration::from_secs(20)); // the compound timer is 10 s
sock.emit("compound", json!({ "items": [0, 1, 2], "scroll_num": 10, "clevel": 2 })).await?;
let result = find(&done.await?).ok_or("no result")?;
println!("{} level {} slot {}", result["response"], result["level"], result["num"]);
```

```java
// No game_response at once on success: the result arrives as a hitchhiker
// ["game_response", {...}] in a later `player` event. A failure comes at once
// as game_response (see the Failure table); then this wait times out.
Function<JsonNode, JsonNode> find = p -> {
    for (JsonNode h : p.path("hitchhikers")) {
        String code = h.path(1).path("response").asText();
        if (h.path(0).asText().equals("game_response") && (code.equals("compound_success") || code.equals("compound_fail"))) return h.get(1);
    }
    return null;
};
var done = sock.waitFor("player", p -> find.apply(p) != null, Duration.ofSeconds(20)); // the compound timer is 10 s
sock.emit("compound", Map.of("items", List.of(0, 1, 2), "scroll_num", 10, "clevel", 2));
JsonNode result = find.apply(done.get());
System.out.println(result.path("response").asText() + " level " + result.path("level") + " slot " + result.path("num"));
```

**Source:** `node/server.js:6862-7133` (chance `node/server.js:6954-7017`, timer `node/server.js:7036-7064`, digits `node/server.js:14776-14811`, result `node/server.js:14827-14886`)

### `upgrade`
Upgrades one item at the upgrade NPC with a `uscroll` (level + 1), a `pscroll` (a stat), or an offering (grace or `shiny`).

<!-- schema -->

**Limits:**
- One upgrade at a time for each character (`q.upgrade`).
- Distance: within `B.sell_dist` (400 px) of the upgrade NPC on `main`. On `HARDCORE` and `TEST` the limit is 10,000,999 px, so any position on `main` works.
- Timer of a `uscroll`: `500 * L * sqrt(L) * tmult` ms. `L` is the new level. `tmult` is 1, 1.5 or 2 for base grade 0, 1 or 2. On `hardcore` the timer is 500 ms.
- Timer of a `pscroll`: `2000 * tmult * tmult` ms. An offering alone: 1000 ms, or 2000 ms for the shiny attempt.
- `massproduction` halves the timer. `massproductionpp` divides it by 10. The upgrade removes the condition.
- A `pscroll` uses `[1, 10, 100, 1000, 9999, 9999, 9999][grade]` scrolls of the stack.
- Call cost: 1.

**Notes:**
- The `pscroll` path and the paths without a scroll do not check the lock `l`.
- `uscroll` chance: the base is `D.upgrades[igrade][new_level]` (`design/upgrades.js:1`). `igrade` is the base grade of the item.
- A grace term comes from the grace of the item, `igrace`, the failure counters of the character and of the server (`p.ugrace`, `S.ugrace`) and `p.ograce`.
- A scroll of a higher grade than the item, up to level 10: `chance * 1.2 + 0.01`, and the item gets 0.4 grace.
- With an offering, the multiplier is 1.7, 1.5, 1.4, 1.15 or 1.08, plus a grace term. The offering grade against the item grade selects the multiplier.
- The cap is `min(base + 0.36, base * 3)` with a better scroll or offering, else `min(base + 0.24, base * 2)`.
- Each character has a "lucky" inventory index (`p.item_num`, random from 0 to 41, node/server_functions.js:4409-4410). An upgrade from that index gets a better roll with a chance of 60% (node/server.js:7397).
- With `gameplay` `"test"`, a `uscroll` always succeeds.
- `pscroll`: the chance is 0.99999. An offering makes it certain and adds 1 grace.
- An offering of type `offering` without a scroll gives the item 0.5 grace. The chance is 1.
- Shiny attempt (an ingot or a nugget without a scroll): the chance is 0.16. It is 0.32 if the `offering` value is above the base grade. The value 2 also gives 0.32 for an item worth 20,000,000 or less. Then the server multiplies by `[2.8, 1.6, 1][base grade]`. A success sets `p` to `"shiny"`.
- A failure adds to the failure counters `p.ugrace` and `S.ugrace`. Later upgrades on the character and on the server get more grace from them. A success at a level sets both counters for that level to 0.
- Each `uscroll` attempt has a 2.5% chance to add 1 grace to the item.
- A roll equal to the chance in its first four digits adds `lucky` on a success (grade 1 or more). On a failure, it gives `essenceofgreed` (grade 1 or more, with a free slot).
- `q.upgrade.num` and the `num` of the results are `item_num` as you sent it, with no conversion.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// No game_response at once on success: the result arrives as a hitchhiker
// ["game_response", {...}] in a later `player` event. A failure comes at once
// as game_response (see the Failure table); then this wait times out.
const isResult = (h) => h[0] === "game_response" && ["upgrade_success", "upgrade_fail"].includes(h[1]?.response);
const done = sock.waitFor("player", (p) => p.hitchhikers?.some(isResult), 60_000); // the upgrade timer can be over 40 s at high levels
sock.emit("upgrade", { item_num: 0, scroll_num: 1, clevel: 5 });
const result = (await done).hitchhikers.find(isResult)[1];
console.log(result.response, "level", result.level, "slot", result.num);
```

```ts
interface RollResult { response: string; level: number; num: number; stale?: boolean }
type Hitchhiker = [event: string, data: RollResult];
interface PlayerUpdate { hitchhikers?: Hitchhiker[] }
// No game_response at once on success: the result arrives as a hitchhiker
// ["game_response", {...}] in a later `player` event. A failure comes at once
// as game_response (see the Failure table); then this wait times out.
const isResult = (h: Hitchhiker) => h[0] === "game_response" && ["upgrade_success", "upgrade_fail"].includes(h[1]?.response);
const done = sock.waitFor<PlayerUpdate>("player", (p) => p.hitchhikers?.some(isResult) ?? false, 60_000);
sock.emit("upgrade", { item_num: 0, scroll_num: 1, clevel: 5 });
const result = (await done).hitchhikers!.find(isResult)![1];
console.log(result.response, "level", result.level, "slot", result.num);
```

```python
# No game_response at once on success: the result arrives as a hitchhiker
# ["game_response", {...}] in a later `player` event. A failure comes at once
# as game_response (see the Failure table); then this wait times out.
def result_of(p):
    for h in p.get("hitchhikers") or []:
        if h[0] == "game_response" and isinstance(h[1], dict) and h[1].get("response") in ("upgrade_success", "upgrade_fail"):
            return h[1]
    return None

done = sock.wait_for("player", lambda p: result_of(p) is not None, timeout=60)  # the upgrade timer can be over 40 s at high levels
await sock.emit("upgrade", {"item_num": 0, "scroll_num": 1, "clevel": 5})
result = result_of(await done)
print(result["response"], "level", result["level"], "slot", result["num"])
```

```go
// No game_response at once on success: the result arrives as a hitchhiker
// ["game_response", {...}] in a later `player` event. A failure comes at once
// as game_response (see the Failure table); then this wait times out.
type rollResult struct {
	Response   string
	Level, Num int
}
find := func(d json.RawMessage) (rollResult, bool) {
	var p struct{ Hitchhikers [][]json.RawMessage }
	_ = json.Unmarshal(d, &p)
	for _, h := range p.Hitchhikers {
		var r rollResult
		if len(h) == 2 && string(h[0]) == `"game_response"` && json.Unmarshal(h[1], &r) == nil &&
			(r.Response == "upgrade_success" || r.Response == "upgrade_fail") {
			return r, true
		}
	}
	return rollResult{}, false
}
wait := sock.Expect("player", func(d json.RawMessage) bool { _, ok := find(d); return ok })
if err := sock.Emit("upgrade", map[string]any{"item_num": 0, "scroll_num": 1, "clevel": 5}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second) // the upgrade timer can be over 40 s at high levels
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
r, _ := find(data)
fmt.Println(r.Response, "level", r.Level, "slot", r.Num)
```

```csharp
// No game_response at once on success: the result arrives as a hitchhiker
// ["game_response", {...}] in a later `player` event. A failure comes at once
// as game_response (see the Failure table); then this wait times out.
JsonElement? Find(JsonElement p)
{
    if (!p.TryGetProperty("hitchhikers", out var hs)) return null;
    foreach (var h in hs.EnumerateArray())
        if (h[0].GetString() == "game_response" && h[1].ValueKind == JsonValueKind.Object
            && h[1].TryGetProperty("response", out var r) && r.GetString() is "upgrade_success" or "upgrade_fail")
            return h[1];
    return null;
}
var done = sock.WaitForAsync("player", p => Find(p) != null, TimeSpan.FromSeconds(60)); // the upgrade timer can be over 40 s at high levels
await sock.EmitAsync("upgrade", new { item_num = 0, scroll_num = 1, clevel = 5 });
var result = Find(await done)!.Value;
Console.WriteLine($"{result.GetProperty("response")} level {result.GetProperty("level")} slot {result.GetProperty("num")}");
```

```rust
// No game_response at once on success: the result arrives as a hitchhiker
// ["game_response", {...}] in a later `player` event. A failure comes at once
// as game_response (see the Failure table); then this wait times out.
fn find(p: &Value) -> Option<Value> {
    p["hitchhikers"].as_array()?.iter()
        .find(|h| h[0] == "game_response"
            && matches!(h[1]["response"].as_str(), Some("upgrade_success" | "upgrade_fail")))
        .map(|h| h[1].clone())
}
let done = sock.wait_for_timeout("player", |p| find(p).is_some(), Duration::from_secs(60)); // the upgrade timer can be over 40 s at high levels
sock.emit("upgrade", json!({ "item_num": 0, "scroll_num": 1, "clevel": 5 })).await?;
let result = find(&done.await?).ok_or("no result")?;
println!("{} level {} slot {}", result["response"], result["level"], result["num"]);
```

```java
// No game_response at once on success: the result arrives as a hitchhiker
// ["game_response", {...}] in a later `player` event. A failure comes at once
// as game_response (see the Failure table); then this wait times out.
Function<JsonNode, JsonNode> find = p -> {
    for (JsonNode h : p.path("hitchhikers")) {
        String code = h.path(1).path("response").asText();
        if (h.path(0).asText().equals("game_response") && (code.equals("upgrade_success") || code.equals("upgrade_fail"))) return h.get(1);
    }
    return null;
};
var done = sock.waitFor("player", p -> find.apply(p) != null, Duration.ofSeconds(60)); // the upgrade timer can be over 40 s at high levels
sock.emit("upgrade", Map.of("item_num", 0, "scroll_num", 1, "clevel", 5));
JsonNode result = find.apply(done.get());
System.out.println(result.path("response").asText() + " level " + result.path("level") + " slot " + result.path("num"));
```

**Source:** `node/server.js:7134-7566` (`uscroll` `node/server.js:7308`, `pscroll` `node/server.js:7502`, digits `node/server.js:14739-14773`, result `node/server.js:14887-14964`)

### `equip_batch`
Equips up to 15 inventory items in one call.

<!-- schema -->

**Limits:**
- 15 entries at most.
- Call cost: `1 + CC.equip * (0.5 + n / 2)`, which is `1 + 3 * (0.5 + n / 2)`. `n` is the length of the array that you send, before the server cuts it to 15 (node/server.js:4907-4912).
- Each equipped item adds 120 ms to `penalty_cd`, to a maximum of 120,000 ms.

**Notes:**
- The server does not check the lock `l`.
- The server stops your channeled actions (`c = {}`) before it checks the payload.
- Without a `penalty_cd`, the server adds it with `ms` = 120 for each equipped item, also when that is 0.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
// slots: one entry per equip, {num, slot} or an error code. It stops at the first error.
const reply = sock.waitFor("game_response", (r) => r?.place === "equip_batch");
sock.emit("equip_batch", [{ num: 0, slot: "mainhand" }, { num: 3, slot: "ring1" }]);
const r = await reply;
if (r.failed) console.log("equip_batch failed:", r.response); // a code from the Failure table
else console.log(r.response, r.slots);
```

```ts
interface EquipBatchReply {
  response: string;
  place: string;
  failed?: boolean;
  slots?: ({ num: number; slot: string } | string)[];
}
// slots: one entry per equip, {num, slot} or an error code. It stops at the first error.
const reply = sock.waitFor<EquipBatchReply>("game_response", (r) => r?.place === "equip_batch");
sock.emit("equip_batch", [{ num: 0, slot: "mainhand" }, { num: 3, slot: "ring1" }]);
const r = await reply;
if (r.failed) console.log("equip_batch failed:", r.response);
else console.log(r.response, r.slots);
```

```python
# slots: one entry per equip, {num, slot} or an error code. It stops at the first error.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "equip_batch")
await sock.emit("equip_batch", [{"num": 0, "slot": "mainhand"}, {"num": 3, "slot": "ring1"}])
r = await reply
if r.get("failed"):
    print("equip_batch failed:", r["response"])
else:
    print(r["response"], r["slots"])
```

```go
// slots: one entry per equip, {num, slot} or an error code. It stops at the first error.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "equip_batch" // a bare string fails to decode
})
if err := sock.Emit("equip_batch", []map[string]any{{"num": 0, "slot": "mainhand"}, {"num": 3, "slot": "ring1"}}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Slots json.RawMessage }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("equip_batch failed:", r.Response)
} else {
	fmt.Println(r.Response, string(r.Slots))
}
```

```csharp
// slots: one entry per equip, {num, slot} or an error code. It stops at the first error.
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "equip_batch");
await sock.EmitAsync("equip_batch", new[] { new { num = 0, slot = "mainhand" }, new { num = 3, slot = "ring1" } });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"equip_batch failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("slots")}");
```

```rust
// slots: one entry per equip, {num, slot} or an error code. It stops at the first error.
let reply = sock.wait_for("game_response", |r| r["place"] == "equip_batch");
sock.emit("equip_batch", json!([{ "num": 0, "slot": "mainhand" }, { "num": 3, "slot": "ring1" }])).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("equip_batch failed: {}", r["response"]);
} else {
    println!("{} {}", r["response"], r["slots"]);
}
```

```java
// slots: one entry per equip, {num, slot} or an error code. It stops at the first error.
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("equip_batch"), Duration.ofSeconds(10));
sock.emit("equip_batch", List.of(Map.of("num", 0, "slot", "mainhand"), Map.of("num", 3, "slot", "ring1")));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("equip_batch failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("slots"));
```

**Source:** `node/server.js:7569-7642` (call cost `node/server.js:4907-4912`)

### `equip`
Uses or equips one inventory item: gear, a trade listing, a potion, an elixir, a cosmetic jar, a licence or a spawner trap.

<!-- schema -->

**Limits:**
- Call cost: 1 + `CC.equip` (3) (node/server.js:251).
- Potion cooldown: `G.items[name].cooldown`, else 2,000 ms. An XP potion without `cooldown`: 0.1 ms.
- Gear: each equip adds 120 ms to `penalty_cd`, to a maximum of 120,000 ms.

**Notes:**
- The trade listing and the gear path do not check the lock `l`. The trade listing refuses `acl` and `v` items.
- The server stops your channeled actions (`c = {}`) before any check except the character check.
- A listed stack is a new item with only `name`, `q`, `level`, `v`, `data`, `p` and `ps` (`create_new_sitem`, node/server.js:1992-2007).

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
const reply = sock.waitFor("game_response", (r) => r?.place === "equip");
sock.emit("equip", { num: 0, slot: "mainhand" });
const r = await reply;
if (r.failed) console.log("equip failed:", r.response); // a code from the Failure table
else console.log(r.response, r.num);
```

```ts
interface EquipReply {
  response: string;
  place: string;
  failed?: boolean;
  num?: number;
  slot?: string;
  used?: string;
  ms?: number;
}
const reply = sock.waitFor<EquipReply>("game_response", (r) => r?.place === "equip");
sock.emit("equip", { num: 0, slot: "mainhand" });
const r = await reply;
if (r.failed) console.log("equip failed:", r.response);
else console.log(r.response, r.num);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "equip")
await sock.emit("equip", {"num": 0, "slot": "mainhand"})
r = await reply
if r.get("failed"):
    print("equip failed:", r["response"])
else:
    print(r["response"], r["num"])
```

```go
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "equip" // a bare string fails to decode
})
if err := sock.Emit("equip", map[string]any{"num": 0, "slot": "mainhand"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Num int }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("equip failed:", r.Response)
} else {
	fmt.Println(r.Response, r.Num)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "equip");
await sock.EmitAsync("equip", new { num = 0, slot = "mainhand" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"equip failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("num")}");
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "equip");
sock.emit("equip", json!({ "num": 0, "slot": "mainhand" })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("equip failed: {}", r["response"]);
} else {
    println!("{} {}", r["response"], r["num"]);
}
```

```java
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("equip"), Duration.ofSeconds(10));
sock.emit("equip", Map.of("num", 0, "slot", "mainhand"));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("equip failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("num").asText());
```

**Source:** `node/server.js:7643-7916` (trade listing `node/server.js:7677-7788`, potion `node/server.js:7823-7878`, gear `node/server.js:7879-7907`)

### `misc_npc`
A stub with no effect: it looks for an NPC that it never finds, and it sends nothing.

<!-- schema -->

**Notes:** **Server bug:** the handler looks up `npc` in `players`, which holds no NPC (node/server.js:7922). Thus it always returns before the distance check.

**Example:**

```js
// `misc_npc` has no effect: the handler never finds an NPC, and the server sends
// nothing.
```

```ts
// `misc_npc` has no effect: the handler never finds an NPC, and the server sends
// nothing.
```

```python
# `misc_npc` has no effect: the handler never finds an NPC, and the server sends
# nothing.
```

```go
// `misc_npc` has no effect: the handler never finds an NPC, and the server sends
// nothing.
```

```csharp
// `misc_npc` has no effect: the handler never finds an NPC, and the server sends
// nothing.
```

```rust
// `misc_npc` has no effect: the handler never finds an NPC, and the server sends
// nothing.
```

```java
// `misc_npc` has no effect: the handler never finds an NPC, and the server sends
// nothing.
```

**Source:** `node/server.js:7917-7932`

### `unequip`
Moves the item in an equipment slot or a trade slot back to the inventory.

<!-- schema -->

**Limits:** Call cost: 1 + `CC.unequip` (6) (node/server.js:252).

**Notes:** The giveaway check is only for `trade1` to `trade48`. A giveaway item in a gear slot can go back to the inventory.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
const reply = sock.waitFor("game_response", (r) => r?.place === "unequip");
sock.emit("unequip", { slot: "offhand" });
const r = await reply;
if (r.failed) console.log("unequip failed:", r.response); // a code from the Failure table
else console.log(r.response);
```

```ts
interface UnequipReply {
  response: string;
  place: string;
  failed?: boolean;
}
const reply = sock.waitFor<UnequipReply>("game_response", (r) => r?.place === "unequip");
sock.emit("unequip", { slot: "offhand" });
const r = await reply;
if (r.failed) console.log("unequip failed:", r.response);
else console.log(r.response);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "unequip")
await sock.emit("unequip", {"slot": "offhand"})
r = await reply
if r.get("failed"):
    print("unequip failed:", r["response"])
else:
    print(r["response"])
```

```go
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "unequip" // a bare string fails to decode
})
if err := sock.Emit("unequip", map[string]any{"slot": "offhand"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("unequip failed:", r.Response)
} else {
	fmt.Println(r.Response)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "unequip");
await sock.EmitAsync("unequip", new { slot = "offhand" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"unequip failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")}");
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "unequip");
sock.emit("unequip", json!({ "slot": "offhand" })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("unequip failed: {}", r["response"]);
} else {
    println!("{}", r["response"]);
}
```

```java
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("unequip"), Duration.ofSeconds(10));
sock.emit("unequip", Map.of("slot", "offhand"));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("unequip failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText());
```

**Source:** `node/server.js:7933-7958`

### `secondhands`
Gets the list of items that players sold to NPCs, from Ponty (the secondhands merchant).

<!-- schema -->

**Limits:**
- Call cost: 1 + `CC.secondhands` (16) (node/server.js:246).
- Distance: within 500 px of Ponty (`secondhands` on `main`). This check does not use `B.sell_dist`, so it is the same on every server.

**Notes:** A paused instance does not refuse `secondhands`: it is on the allow-list (node/logic/instance_pause.js:94).

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Without request_id, the list arrives as a `secondhands` event.
// A failure is a bare game_response string ("distance"); then this wait times out.
const list = sock.waitFor("secondhands");
sock.emit("secondhands");
for (const item of await list) console.log(item.rid, item.name, item.level ?? 0, item.q ?? 1);
```

```ts
interface ListedItem {
  rid: string; // the id for sbuy
  name: string;
  level?: number;
  q?: number;
  p?: string; // title
}
// A failure is a bare game_response string ("distance"); then this wait times out.
const list = sock.waitFor<ListedItem[]>("secondhands");
sock.emit("secondhands");
for (const item of await list) console.log(item.rid, item.name, item.level ?? 0, item.q ?? 1);
```

```python
# A failure is a bare game_response string ("distance"); then this wait times out.
items = sock.wait_for("secondhands")
await sock.emit("secondhands")
for item in await items:
    print(item["rid"], item["name"], item.get("level", 0), item.get("q", 1))
```

```go
// A failure is a bare game_response string ("distance"); then this wait times out.
wait := sock.Expect("secondhands", nil)
if err := sock.Emit("secondhands", nil); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var items []struct { Rid, Name string; Level, Q int }
if err := json.Unmarshal(data, &items); err != nil {
	return err
}
for _, it := range items {
	fmt.Println(it.Rid, it.Name, it.Level, it.Q) // Q is 0 for an item that does not stack
}
```

```csharp
// A failure is a bare game_response string ("distance"); then this wait times out.
var list = sock.WaitForAsync("secondhands");
await sock.EmitAsync("secondhands");
foreach (var item in (await list).EnumerateArray())
    Console.WriteLine($"{item.GetProperty("rid")} {item.GetProperty("name")}");
```

```rust
// A failure is a bare game_response string ("distance"); then this wait times out.
let list = sock.wait_for("secondhands", |_| true);
sock.emit("secondhands", Value::Null).await?;
for item in list.await?.as_array().into_iter().flatten() {
    println!("{} {}", item["rid"], item["name"]);
}
```

```java
// A failure is a bare game_response string ("distance"); then this wait times out.
var list = sock.waitFor("secondhands");
sock.emit("secondhands", null);
for (JsonNode item : list.get()) System.out.println(item.path("rid").asText() + " " + item.path("name").asText());
```

**Source:** `node/server.js:7959-7973` (list rules `node/server_functions.js:590-639`)

### `lostandfound`
Gets the list of lost items from the Lost and Found NPC (woffice), or with `"info"`, the donated gold total of the server.

<!-- schema -->

**Limits:** Distance: within 500 px of the `lostandfound` NPC on `woffice`. This check does not use `B.sell_dist`.

**Notes:**
- The `"info"` payload needs no donation and works at any distance.
- The server does not save `player.donation`: it lasts until you log out (node/server.js:8648).

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Without request_id, the list arrives as a `lostandfound` event.
// A failure is a bare game_response string ("lostandfound_donate", "distance"); then this wait times out.
const list = sock.waitFor("lostandfound");
sock.emit("lostandfound");
for (const item of await list) console.log(item.rid, item.name, item.level ?? 0, item.q ?? 1);
```

```ts
interface ListedItem {
  rid: string; // the id for sbuy
  name: string;
  level?: number;
  q?: number;
  p?: string; // title
}
// A failure is a bare game_response string ("lostandfound_donate", "distance"); then this wait times out.
const list = sock.waitFor<ListedItem[]>("lostandfound");
sock.emit("lostandfound");
for (const item of await list) console.log(item.rid, item.name, item.level ?? 0, item.q ?? 1);
```

```python
# A failure is a bare game_response string ("lostandfound_donate", "distance"); then this wait times out.
items = sock.wait_for("lostandfound")
await sock.emit("lostandfound")
for item in await items:
    print(item["rid"], item["name"], item.get("level", 0), item.get("q", 1))
```

```go
// A failure is a bare game_response string ("lostandfound_donate", "distance"); then this wait times out.
wait := sock.Expect("lostandfound", nil)
if err := sock.Emit("lostandfound", nil); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var items []struct { Rid, Name string; Level, Q int }
if err := json.Unmarshal(data, &items); err != nil {
	return err
}
for _, it := range items {
	fmt.Println(it.Rid, it.Name, it.Level, it.Q) // Q is 0 for an item that does not stack
}
```

```csharp
// A failure is a bare game_response string ("lostandfound_donate", "distance"); then this wait times out.
var list = sock.WaitForAsync("lostandfound");
await sock.EmitAsync("lostandfound");
foreach (var item in (await list).EnumerateArray())
    Console.WriteLine($"{item.GetProperty("rid")} {item.GetProperty("name")}");
```

```rust
// A failure is a bare game_response string ("lostandfound_donate", "distance"); then this wait times out.
let list = sock.wait_for("lostandfound", |_| true);
sock.emit("lostandfound", Value::Null).await?;
for item in list.await?.as_array().into_iter().flatten() {
    println!("{} {}", item["rid"], item["name"]);
}
```

```java
// A failure is a bare game_response string ("lostandfound_donate", "distance"); then this wait times out.
var list = sock.waitFor("lostandfound");
sock.emit("lostandfound", null);
for (JsonNode item : list.get()) System.out.println(item.path("rid").asText() + " " + item.path("name").asText());
```

**Source:** `node/server.js:7974-7996` (list rules `node/server_functions.js:641-670`)

### `split`
Moves part of a stack into the first empty inventory slot.

<!-- schema -->

**Notes:** The new stack is a copy from `cache_item`, so it has no `grace`, `o`, `oo` or `src`.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
const reply = sock.waitFor("game_response", (r) => r?.place === "split");
sock.emit("split", { num: 7, quantity: 50 });
const r = await reply;
if (r.failed) console.log("split failed:", r.response); // a code from the Failure table
else console.log(r.response, r.from, r.to, r.q);
```

```ts
interface SplitReply {
  response: string;
  place: string;
  failed?: boolean;
  from?: number;
  to?: number;
  q?: number;
}
const reply = sock.waitFor<SplitReply>("game_response", (r) => r?.place === "split");
sock.emit("split", { num: 7, quantity: 50 });
const r = await reply;
if (r.failed) console.log("split failed:", r.response);
else console.log(r.response, r.from, r.to, r.q);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "split")
await sock.emit("split", {"num": 7, "quantity": 50})
r = await reply
if r.get("failed"):
    print("split failed:", r["response"])
else:
    print(r["response"], r["from"], r["to"], r["q"])
```

```go
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "split" // a bare string fails to decode
})
if err := sock.Emit("split", map[string]any{"num": 7, "quantity": 50}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; From int; To int; Q int }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("split failed:", r.Response)
} else {
	fmt.Println(r.Response, r.From, r.To, r.Q)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "split");
await sock.EmitAsync("split", new { num = 7, quantity = 50 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"split failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("from")} {r.GetProperty("to")} {r.GetProperty("q")}");
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "split");
sock.emit("split", json!({ "num": 7, "quantity": 50 })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("split failed: {}", r["response"]);
} else {
    println!("{} {} {} {}", r["response"], r["from"], r["to"], r["q"]);
}
```

```java
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("split"), Duration.ofSeconds(10));
sock.emit("split", Map.of("num", 7, "quantity", 50));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("split failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("from").asText() + " " + r.path("to").asText() + " " + r.path("q").asText());
```

**Source:** `node/server.js:7997-8045`

### `sell`
Sells an inventory item, or part of a stack, to a nearby NPC merchant for its gold value.

<!-- schema -->

**Limits:** Distance: nearer than `B.sell_dist` (400 px) to a merchant NPC on your map. On `HARDCORE` and `TEST` the limit is 10,000,999 px.

**Notes:**
- A character with a `computer` can sell at any distance. Then the server uses the first merchant of `main`, so the `ui` event goes to clients near that NPC.
- `calculate_item_value` starts at `G.items[name].g * 0.6` (the full `g` for a `cash` item). Each level multiplies it, and scroll costs go on top. An item with `expires` is worth 1/8. A `gift` item is worth 1 (`js/old_common_functions.js:783-822`).
- After the reply, some items go into the list of Ponty (see `secondhands`). These are items that no NPC sells, upgrade items at +7 or more, and compound items at +2 or more. Items with `cash`, `expires` or `acl` do not.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
const reply = sock.waitFor("game_response", (r) => r?.place === "sell");
sock.emit("sell", { num: 12, quantity: 1 });
const r = await reply;
if (r.failed) console.log("sell failed:", r.response); // a code from the Failure table
else console.log(r.response, r.gold);
```

```ts
interface SellReply {
  response: string;
  place: string;
  failed?: boolean;
  gold?: number;
  item?: { name: string; level?: number; q?: number };
}
const reply = sock.waitFor<SellReply>("game_response", (r) => r?.place === "sell");
sock.emit("sell", { num: 12, quantity: 1 });
const r = await reply;
if (r.failed) console.log("sell failed:", r.response);
else console.log(r.response, r.gold);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "sell")
await sock.emit("sell", {"num": 12, "quantity": 1})
r = await reply
if r.get("failed"):
    print("sell failed:", r["response"])
else:
    print(r["response"], r["gold"])
```

```go
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "sell" // a bare string fails to decode
})
if err := sock.Emit("sell", map[string]any{"num": 12, "quantity": 1}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Gold float64 }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("sell failed:", r.Response)
} else {
	fmt.Println(r.Response, r.Gold)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "sell");
await sock.EmitAsync("sell", new { num = 12, quantity = 1 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"sell failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("gold")}");
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "sell");
sock.emit("sell", json!({ "num": 12, "quantity": 1 })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("sell failed: {}", r["response"]);
} else {
    println!("{} {}", r["response"], r["gold"]);
}
```

```java
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("sell"), Duration.ofSeconds(10));
sock.emit("sell", Map.of("num", 12, "quantity", 1));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("sell failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("gold").asText());
```

**Source:** `node/server.js:8046-8097` (list rule `node/server_functions.js:590-639`)

### `buy_shells`
Does nothing: the server answers that the exchange of gold for shells is no longer possible.

<!-- schema -->

**Example:**

```js
// `buy_shells` always fails: the server sends game_log "No longer possible" and changes
// nothing.
```

```ts
// `buy_shells` always fails: the server sends game_log "No longer possible" and changes
// nothing.
```

```python
# `buy_shells` always fails: the server sends game_log "No longer possible" and changes
# nothing.
```

```go
// `buy_shells` always fails: the server sends game_log "No longer possible" and changes
// nothing.
```

```csharp
// `buy_shells` always fails: the server sends game_log "No longer possible" and changes
// nothing.
```

```rust
// `buy_shells` always fails: the server sends game_log "No longer possible" and changes
// nothing.
```

```java
// `buy_shells` always fails: the server sends game_log "No longer possible" and changes
// nothing.
```

**Source:** `node/server.js:8098-8143` (reply `node/server.js:8099`)

### `buy_with_cash`
Buys an item from the shop for shells (the premium currency). The payment goes through the account database, so the item comes later.

<!-- schema -->

**Limits:**
- Only items with a `cash` price, and not `ignore` or `p2w`. Not on `hardcore` or `test` servers.
- Cost: `G.items[name].cash * quantity` shells.

**Notes:** The payment runs as a transaction in the account database (`tx`, common:mongodb_functions.js:57-111). The item comes only after it succeeds.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Two replies: at once {in_progress: true} or a failure, then the result after the shell payment.
const first = sock.waitFor("game_response", (r) => r?.place === "buy_with_cash");
sock.emit("buy_with_cash", { name: "cosmo0", quantity: 1 });
const r0 = await first;
if (r0.failed) console.log("buy_with_cash failed:", r0.response);
else {
  // The final reply always comes after the first one, so this wait can start now.
  const r = await sock.waitFor("game_response", (d) => ["shell_purchase_complete", "shell_purchase_failed"].includes(d?.response));
  console.log(r.response, r.name, r.quantity, r.cost, r.reason);
}
```

```ts
interface ShellReply {
  response: string;
  place?: string;
  failed?: boolean;
  in_progress?: boolean;
  name?: string;
  quantity?: number;
  cost?: number; // shells
  reason?: string;
}
const first = sock.waitFor<ShellReply>("game_response", (r) => r?.place === "buy_with_cash");
sock.emit("buy_with_cash", { name: "cosmo0", quantity: 1 });
const r0 = await first;
if (r0.failed) console.log("buy_with_cash failed:", r0.response);
else {
  const r = await sock.waitFor<ShellReply>("game_response", (d) => ["shell_purchase_complete", "shell_purchase_failed"].includes(d?.response));
  console.log(r.response, r.name, r.quantity, r.cost, r.reason);
}
```

```python
first = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "buy_with_cash")
await sock.emit("buy_with_cash", {"name": "cosmo0", "quantity": 1})
r0 = await first
if r0.get("failed"):
    print("buy_with_cash failed:", r0["response"])
else:
    # The final reply always comes after the first one, so this wait can start now.
    r = await sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("response") in ("shell_purchase_complete", "shell_purchase_failed"))
    print(r["response"], r.get("name"), r.get("quantity"), r.get("cost"), r.get("reason"))
```

```go
isObj := func(d json.RawMessage, r any) bool { return json.Unmarshal(d, r) == nil } // a bare string fails
// Register both waits before Emit. The final wait is not used if the first reply is a failure.
waitFirst := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return isObj(d, &r) && r.Place == "buy_with_cash"
})
waitFinal := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Response string }
	return isObj(d, &r) && strings.HasPrefix(r.Response, "shell_purchase_")
})
if err := sock.Emit("buy_with_cash", map[string]any{"name": "cosmo0", "quantity": 1}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
defer cancel()
data, err := waitFirst(ctx)
if err != nil {
	return err
}
var r0 struct { Response string; Failed bool }
if isObj(data, &r0); r0.Failed {
	fmt.Println("buy_with_cash failed:", r0.Response)
	return nil
}
if data, err = waitFinal(ctx); err != nil {
	return err
}
fmt.Println(string(data))
```

```csharp
var first = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "buy_with_cash");
await sock.EmitAsync("buy_with_cash", new { name = "cosmo0", quantity = 1 });
var r0 = await first;
if (r0.TryGetProperty("failed", out _))
    Console.WriteLine($"buy_with_cash failed: {r0.GetProperty("response")}");
else // the final reply always comes after the first one, so this wait can start now
    Console.WriteLine(await sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
        && d.TryGetProperty("response", out var c) && c.GetString() is "shell_purchase_complete" or "shell_purchase_failed"));
```

```rust
let first = sock.wait_for("game_response", |r| r["place"] == "buy_with_cash");
sock.emit("buy_with_cash", json!({ "name": "cosmo0", "quantity": 1 })).await?;
let r0 = first.await?;
if r0["failed"] == true {
    println!("buy_with_cash failed: {}", r0["response"]);
} else {
    // The final reply always comes after the first one, so this wait can start now.
    let r = sock.wait_for("game_response", |d| matches!(d["response"].as_str(), Some("shell_purchase_complete" | "shell_purchase_failed"))).await?;
    println!("{r}");
}
```

```java
var first = sock.waitFor("game_response", d -> d.path("place").asText().equals("buy_with_cash"), Duration.ofSeconds(10));
sock.emit("buy_with_cash", Map.of("name", "cosmo0", "quantity", 1));
JsonNode r0 = first.get();
if (r0.path("failed").asBoolean()) System.out.println("buy_with_cash failed: " + r0.path("response").asText());
else System.out.println(sock.waitFor("game_response", d -> d.path("response").asText().startsWith("shell_purchase_"), Duration.ofSeconds(10)).get());
```

**Source:** `node/server.js:8144-8230` (final reply `node/server.js:8149-8163`)

### `bless_server`
Spends 1,200 shells to bless the current server for 3 days, with an announcement on all servers of the realm.

<!-- schema -->

**Limits:**
- Cost: 1,200 shells. Not on `hardcore` or `test` servers.
- The blessing lasts 4,320 minutes (3 days). `bless_loop` counts it down each minute.

**Notes:**
- A new blessing restarts the counter, also while a blessing runs.
- While the blessing runs, every character on the server has the condition `patronsgrace` (`G.conditions.patronsgrace`: `luck` 5, `gold` 20, `xp` 25, `speed` 1). `E.blessed_minutes` and `E.blessed_by` show it in the server events.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Two replies: at once {in_progress: true} or a failure, then the result after the shell payment.
const first = sock.waitFor("game_response", (r) => r?.place === "bless_server");
sock.emit("bless_server", { request_id: "bless-1" });
const r0 = await first;
if (r0.failed) console.log("bless_server failed:", r0.response);
else {
  // The final reply always comes after the first one, so this wait can start now.
  const r = await sock.waitFor("game_response", (d) => d?.response === "bless_result");
  console.log(r.response, r.result, r.minutes, r.reason);
}
```

```ts
interface ShellReply {
  response: string;
  place?: string;
  failed?: boolean;
  in_progress?: boolean;
  result?: string; // "blessed" or "blessed_fail"
  minutes?: number;
  reason?: string;
}
const first = sock.waitFor<ShellReply>("game_response", (r) => r?.place === "bless_server");
sock.emit("bless_server", { request_id: "bless-1" });
const r0 = await first;
if (r0.failed) console.log("bless_server failed:", r0.response);
else {
  const r = await sock.waitFor<ShellReply>("game_response", (d) => d?.response === "bless_result");
  console.log(r.response, r.result, r.minutes, r.reason);
}
```

```python
first = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "bless_server")
await sock.emit("bless_server", {"request_id": "bless-1"})
r0 = await first
if r0.get("failed"):
    print("bless_server failed:", r0["response"])
else:
    # The final reply always comes after the first one, so this wait can start now.
    r = await sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("response") == "bless_result")
    print(r["response"], r.get("result"), r.get("minutes"), r.get("reason"))
```

```go
isObj := func(d json.RawMessage, r any) bool { return json.Unmarshal(d, r) == nil } // a bare string fails
// Register both waits before Emit. The final wait is not used if the first reply is a failure.
waitFirst := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return isObj(d, &r) && r.Place == "bless_server"
})
waitFinal := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Response string }
	return isObj(d, &r) && r.Response == "bless_result"
})
if err := sock.Emit("bless_server", map[string]any{"request_id": "bless-1"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
defer cancel()
data, err := waitFirst(ctx)
if err != nil {
	return err
}
var r0 struct { Response string; Failed bool }
if isObj(data, &r0); r0.Failed {
	fmt.Println("bless_server failed:", r0.Response)
	return nil
}
if data, err = waitFinal(ctx); err != nil {
	return err
}
fmt.Println(string(data))
```

```csharp
var first = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "bless_server");
await sock.EmitAsync("bless_server", new { request_id = "bless-1" });
var r0 = await first;
if (r0.TryGetProperty("failed", out _))
    Console.WriteLine($"bless_server failed: {r0.GetProperty("response")}");
else // the final reply always comes after the first one, so this wait can start now
    Console.WriteLine(await sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
        && d.TryGetProperty("response", out var c) && c.GetString() == "bless_result"));
```

```rust
let first = sock.wait_for("game_response", |r| r["place"] == "bless_server");
sock.emit("bless_server", json!({ "request_id": "bless-1" })).await?;
let r0 = first.await?;
if r0["failed"] == true {
    println!("bless_server failed: {}", r0["response"]);
} else {
    // The final reply always comes after the first one, so this wait can start now.
    let r = sock.wait_for("game_response", |d| d["response"] == "bless_result").await?;
    println!("{r}");
}
```

```java
var first = sock.waitFor("game_response", d -> d.path("place").asText().equals("bless_server"), Duration.ofSeconds(10));
sock.emit("bless_server", Map.of("request_id", "bless-1"));
JsonNode r0 = first.get();
if (r0.path("failed").asBoolean()) System.out.println("bless_server failed: " + r0.path("response").asText());
else System.out.println(sock.waitFor("game_response", d -> d.path("response").asText().equals("bless_result"), Duration.ofSeconds(10)).get());
```

**Source:** `node/server.js:8231-8325` (success `node/server.js:8285-8309`, `bless_loop` `node/server.js:15694-15718`)

### `sbuy`
Buys an item back from the secondhands list of Ponty, or with `f`, from the Lost and Found list.

<!-- schema -->

**Limits:**
- Ponty charges 2 times the item value (3 times for a `cash` item). Lost and Found charges 4 times.
- Distance: within 500 px of the NPC. This check does not use `B.sell_dist`.

**Notes:** Without `request_id`, the server does not check the donation for Lost and Found (node/server.js:8349), and a success sends no `game_response`: wait for the new `secondhands` (or `lostandfound`) list (node/server.js:8391-8401).

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
// With request_id, place is "secondhands" ("lostandfound" with f: true).
const reply = sock.waitFor("game_response", (r) => r?.place === "secondhands");
sock.emit("sbuy", { rid: "aB3xQ", request_id: "sbuy-1" });
const r = await reply;
if (r.failed) console.log("sbuy failed:", r.response); // a code from the Failure table
else console.log(r.response, r.rid, r.cost);
```

```ts
interface SbuyReply {
  response: string;
  place: string;
  failed?: boolean;
  request_id?: string;
  rid?: string;
  cost?: number;
  item?: { name: string; level?: number; q?: number };
}
// With request_id, place is "secondhands" ("lostandfound" with f: true).
const reply = sock.waitFor<SbuyReply>("game_response", (r) => r?.place === "secondhands");
sock.emit("sbuy", { rid: "aB3xQ", request_id: "sbuy-1" });
const r = await reply;
if (r.failed) console.log("sbuy failed:", r.response);
else console.log(r.response, r.rid, r.cost);
```

```python
# With request_id, place is "secondhands" ("lostandfound" with f: true).
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "secondhands")
await sock.emit("sbuy", {"rid": "aB3xQ", "request_id": "sbuy-1"})
r = await reply
if r.get("failed"):
    print("sbuy failed:", r["response"])
else:
    print(r["response"], r["rid"], r["cost"])
```

```go
// With request_id, place is "secondhands" ("lostandfound" with f: true).
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "secondhands" // a bare string fails to decode
})
if err := sock.Emit("sbuy", map[string]any{"rid": "aB3xQ", "request_id": "sbuy-1"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Rid string; Cost float64 }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("sbuy failed:", r.Response)
} else {
	fmt.Println(r.Response, r.Rid, r.Cost)
}
```

```csharp
// With request_id, place is "secondhands" ("lostandfound" with f: true).
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "secondhands");
await sock.EmitAsync("sbuy", new { rid = "aB3xQ", request_id = "sbuy-1" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"sbuy failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("rid")} {r.GetProperty("cost")}");
```

```rust
// With request_id, place is "secondhands" ("lostandfound" with f: true).
let reply = sock.wait_for("game_response", |r| r["place"] == "secondhands");
sock.emit("sbuy", json!({ "rid": "aB3xQ", "request_id": "sbuy-1" })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("sbuy failed: {}", r["response"]);
} else {
    println!("{} {} {}", r["response"], r["rid"], r["cost"]);
}
```

```java
// With request_id, place is "secondhands" ("lostandfound" with f: true).
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("secondhands"), Duration.ofSeconds(10));
sock.emit("sbuy", Map.of("rid", "aB3xQ", "request_id", "sbuy-1"));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("sbuy failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("rid").asText() + " " + r.path("cost").asText());
```

**Source:** `node/server.js:8326-8408` (donation check `node/server.js:8349`)

### `buy`
Buys an item for gold from an NPC shop near you.

<!-- schema -->

**Limits:**
- `quantity` is at most `G.items[name].s` (9999 for `hpot0`).
- The shop must be within `B.sell_dist`: 400 px (node/server.js:220). On the `HARDCORE` and `TEST` servers it is 10,000,999 px (node/server.js:377, 390). There, any shop on your map is near enough.
- Call cost: 1.

**Notes:**
- A character with a `computer` (or a `supercomputer`) can buy at any distance. Then the server uses the first merchant of `main` as the shop, so the `ui` event goes to clients near that NPC, not near you.
- With `gameplay` `"test"`, the server does not check `can_buy`.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
const reply = sock.waitFor("game_response", (r) => r?.place === "buy");
sock.emit("buy", { name: "hpot0", quantity: 100 });
const r = await reply;
if (r.failed) console.log("buy failed:", r.response); // a code from the Failure table
else console.log(r.response, r.name, r.q, r.num, r.cost);
```

```ts
interface BuyReply {
  response: string;
  place: string;
  failed?: boolean;
  name?: string;
  q?: number;
  num?: number;
  cost?: number;
}
const reply = sock.waitFor<BuyReply>("game_response", (r) => r?.place === "buy");
sock.emit("buy", { name: "hpot0", quantity: 100 });
const r = await reply;
if (r.failed) console.log("buy failed:", r.response);
else console.log(r.response, r.name, r.q, r.num, r.cost);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "buy")
await sock.emit("buy", {"name": "hpot0", "quantity": 100})
r = await reply
if r.get("failed"):
    print("buy failed:", r["response"])
else:
    print(r["response"], r["name"], r["q"], r["num"], r["cost"])
```

```go
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "buy" // a bare string fails to decode
})
if err := sock.Emit("buy", map[string]any{"name": "hpot0", "quantity": 100}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Name string; Q int; Num int; Cost float64 }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("buy failed:", r.Response)
} else {
	fmt.Println(r.Response, r.Name, r.Q, r.Num, r.Cost)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "buy");
await sock.EmitAsync("buy", new { name = "hpot0", quantity = 100 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"buy failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("name")} {r.GetProperty("q")} {r.GetProperty("num")} {r.GetProperty("cost")}");
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "buy");
sock.emit("buy", json!({ "name": "hpot0", "quantity": 100 })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("buy failed: {}", r["response"]);
} else {
    println!("{} {} {} {} {}", r["response"], r["name"], r["q"], r["num"], r["cost"]);
}
```

```java
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("buy"), Duration.ofSeconds(10));
sock.emit("buy", Map.of("name", "hpot0", "quantity", 100));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("buy failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("name").asText() + " " + r.path("q").asText() + " " + r.path("num").asText() + " " + r.path("cost").asText());
```

**Source:** `node/server.js:8409-8461` (shop list `js/old_common_functions.js:246`)

### `send`
Gives an item, gold or a cosmetic to another player who is near on the same map.

<!-- schema -->

**Limits:**
- Distance: the receiver is on your map, within `B.dist` (400 px).
- Gold mode has a fee of 2.5%. There is no fee for an amount of 1, or when the two characters have the same owner or IP (`is_same`, node/server_functions.js:505).
- Call cost: 1, plus 4 for the `player` update of the receiver (node/server.js:4584-4586).

**Notes:**
- `item_sent.num` is your slot. `item_received.num` and `ui.num` are the slot of the receiver.
- The server sets `src: "snd"` on the item object when the receiver has another owner (node/server.js:8515-8517). A single item carries it to the receiver. A sent stack is a new item without `src`; when you send part of a stack, the rest of your stack gets it. `ItemInstance` does not show `src`.
- The code has `fail_response("no_item")` for a quantity of 0, but the clamp makes it unreachable.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
// Gold mode. The sender gets gold_sent; the receiver gets gold_received.
const reply = sock.waitFor("game_response", (r) => r?.place === "send");
sock.emit("send", { name: "Bob", gold: 10000 });
const r = await reply;
if (r.failed) console.log("send failed:", r.response); // a code from the Failure table
else console.log(r.response, r.name, r.gold);
```

```ts
interface SendReply {
  response: string;
  place: string;
  failed?: boolean;
  name?: string;
  gold?: number;
  item?: unknown;
  q?: number;
  num?: number;
  cx?: string;
}
// Gold mode. The sender gets gold_sent; the receiver gets gold_received.
const reply = sock.waitFor<SendReply>("game_response", (r) => r?.place === "send");
sock.emit("send", { name: "Bob", gold: 10000 });
const r = await reply;
if (r.failed) console.log("send failed:", r.response);
else console.log(r.response, r.name, r.gold);
```

```python
# Gold mode. The sender gets gold_sent; the receiver gets gold_received.
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "send")
await sock.emit("send", {"name": "Bob", "gold": 10000})
r = await reply
if r.get("failed"):
    print("send failed:", r["response"])
else:
    print(r["response"], r["name"], r["gold"])
```

```go
// Gold mode. The sender gets gold_sent; the receiver gets gold_received.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "send" // a bare string fails to decode
})
if err := sock.Emit("send", map[string]any{"name": "Bob", "gold": 10000}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Name string; Gold float64 }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("send failed:", r.Response)
} else {
	fmt.Println(r.Response, r.Name, r.Gold)
}
```

```csharp
// Gold mode. The sender gets gold_sent; the receiver gets gold_received.
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "send");
await sock.EmitAsync("send", new { name = "Bob", gold = 10000 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"send failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("name")} {r.GetProperty("gold")}");
```

```rust
// Gold mode. The sender gets gold_sent; the receiver gets gold_received.
let reply = sock.wait_for("game_response", |r| r["place"] == "send");
sock.emit("send", json!({ "name": "Bob", "gold": 10000 })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("send failed: {}", r["response"]);
} else {
    println!("{} {} {}", r["response"], r["name"], r["gold"]);
}
```

```java
// Gold mode. The sender gets gold_sent; the receiver gets gold_received.
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("send"), Duration.ofSeconds(10));
sock.emit("send", Map.of("name", "Bob", "gold", 10000));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("send failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("name").asText() + " " + r.path("gold").asText());
```

**Source:** `node/server.js:8463-8628` (`src` `node/server.js:8515-8517`, gold fee `node/server.js:8557-8559`)

### `donate`
Gives gold to the gold pool of the server.

<!-- schema -->

**Notes:**
- The server does not save `player.donation`: it lasts until you log out.
- A donation of 5,000,000 or more goes into `S.logs.donate` (name, gold, XP rate).
- **Server bug:** with a full inventory, the `gum` of `donate_gum` goes to a new slot after slot 41 (`add_item` pushes it, node/server.js:2074-2079).

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
// With request_id, each reply is an object with place "donate".
const reply = sock.waitFor("game_response", (r) => r?.place === "donate");
sock.emit("donate", { gold: 1000000, request_id: "donate-1" });
const r = await reply;
if (r.failed) console.log("donate failed:", r.response); // a code from the Failure table
else console.log(r.response, r.gold, r.xprate);
```

```ts
interface DonateReply {
  response: string;
  place: string;
  failed?: boolean;
  gold?: number;
  xprate?: number;
  request_id?: string;
}
// With request_id, each reply is an object with place "donate".
const reply = sock.waitFor<DonateReply>("game_response", (r) => r?.place === "donate");
sock.emit("donate", { gold: 1000000, request_id: "donate-1" });
const r = await reply;
if (r.failed) console.log("donate failed:", r.response);
else console.log(r.response, r.gold, r.xprate);
```

```python
# With request_id, each reply is an object with place "donate".
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "donate")
await sock.emit("donate", {"gold": 1000000, "request_id": "donate-1"})
r = await reply
if r.get("failed"):
    print("donate failed:", r["response"])
else:
    print(r["response"], r["gold"], r["xprate"])
```

```go
// With request_id, each reply is an object with place "donate".
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "donate" // a bare string fails to decode
})
if err := sock.Emit("donate", map[string]any{"gold": 1000000, "request_id": "donate-1"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Gold float64; Xprate float64 }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("donate failed:", r.Response)
} else {
	fmt.Println(r.Response, r.Gold, r.Xprate)
}
```

```csharp
// With request_id, each reply is an object with place "donate".
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "donate");
await sock.EmitAsync("donate", new { gold = 1000000, request_id = "donate-1" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"donate failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("gold")} {r.GetProperty("xprate")}");
```

```rust
// With request_id, each reply is an object with place "donate".
let reply = sock.wait_for("game_response", |r| r["place"] == "donate");
sock.emit("donate", json!({ "gold": 1000000, "request_id": "donate-1" })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("donate failed: {}", r["response"]);
} else {
    println!("{} {} {}", r["response"], r["gold"], r["xprate"]);
}
```

```java
// With request_id, each reply is an object with place "donate".
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("donate"), Duration.ofSeconds(10));
sock.emit("donate", Map.of("gold", 1000000, "request_id", "donate-1"));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("donate failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("gold").asText() + " " + r.path("xprate").asText());
```

**Source:** `node/server.js:8629-8679`

### `destroy`
Destroys an inventory item, with special effects near the "poof" statue in spookytown.

<!-- schema -->

**Limits:** `statue`: within `B.sell_dist` (400 px) of the poof statue in `spookytown`. On `HARDCORE` and `TEST` the limit is 10,000,999 px.

**Notes:**
- The server does not remove an item at level 13. It sends the success reply.
- With `statue` near the statue, a `shadowstone` gives the condition `invis` (99,999 ms).
- With `statue` near the statue, an upgrade item can come back at level 13. The chance is `1 / (3000013 * g * g)`, where `g` is the base grade + 1 (1 in 10,000 on `hardcore`).

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
const reply = sock.waitFor("game_response", (r) => r?.place === "destroy");
sock.emit("destroy", { num: 9, q: 1 });
const r = await reply;
if (r.failed) console.log("destroy failed:", r.response); // a code from the Failure table
else console.log(r.response, r.name, r.num);
```

```ts
interface DestroyReply {
  response: string;
  place: string;
  failed?: boolean;
  name?: string;
  num: number;
}
const reply = sock.waitFor<DestroyReply>("game_response", (r) => r?.place === "destroy");
sock.emit("destroy", { num: 9, q: 1 });
const r = await reply;
if (r.failed) console.log("destroy failed:", r.response);
else console.log(r.response, r.name, r.num);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "destroy")
await sock.emit("destroy", {"num": 9, "q": 1})
r = await reply
if r.get("failed"):
    print("destroy failed:", r["response"])
else:
    print(r["response"], r["name"], r["num"])
```

```go
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "destroy" // a bare string fails to decode
})
if err := sock.Emit("destroy", map[string]any{"num": 9, "q": 1}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool; Name string; Num int }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("destroy failed:", r.Response)
} else {
	fmt.Println(r.Response, r.Name, r.Num)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "destroy");
await sock.EmitAsync("destroy", new { num = 9, q = 1 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"destroy failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")} {r.GetProperty("name")} {r.GetProperty("num")}");
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "destroy");
sock.emit("destroy", json!({ "num": 9, "q": 1 })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("destroy failed: {}", r["response"]);
} else {
    println!("{} {} {}", r["response"], r["name"], r["num"]);
}
```

```java
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("destroy"), Duration.ofSeconds(10));
sock.emit("destroy", Map.of("num", 9, "q", 1));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("destroy failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText() + " " + r.path("name").asText() + " " + r.path("num").asText());
```

**Source:** `node/server.js:8680-8736` (statue `node/server.js:8703-8733`)

### `join_giveaway`
Enters the player into a giveaway that a merchant lists in a trade slot. The server records entries by account (`auth_id`).

<!-- schema -->

**Notes:** The server records one entry for each `auth_id`, so one Steam or Mac App Store account has one entry.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
const reply = sock.waitFor("game_response", (r) => r?.place === "join_giveaway");
sock.emit("join_giveaway", { id: "MerchantName", slot: "trade1", rid: "x7Qa" });
const r = await reply;
if (r.failed) console.log("join_giveaway failed:", r.response); // a code from the Failure table
else console.log(r.response);
```

```ts
interface JoinGiveawayReply {
  response: string;
  place: string;
  failed?: boolean;
}
const reply = sock.waitFor<JoinGiveawayReply>("game_response", (r) => r?.place === "join_giveaway");
sock.emit("join_giveaway", { id: "MerchantName", slot: "trade1", rid: "x7Qa" });
const r = await reply;
if (r.failed) console.log("join_giveaway failed:", r.response);
else console.log(r.response);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "join_giveaway")
await sock.emit("join_giveaway", {"id": "MerchantName", "slot": "trade1", "rid": "x7Qa"})
r = await reply
if r.get("failed"):
    print("join_giveaway failed:", r["response"])
else:
    print(r["response"])
```

```go
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "join_giveaway" // a bare string fails to decode
})
if err := sock.Emit("join_giveaway", map[string]any{"id": "MerchantName", "slot": "trade1", "rid": "x7Qa"}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("join_giveaway failed:", r.Response)
} else {
	fmt.Println(r.Response)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "join_giveaway");
await sock.EmitAsync("join_giveaway", new { id = "MerchantName", slot = "trade1", rid = "x7Qa" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"join_giveaway failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")}");
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "join_giveaway");
sock.emit("join_giveaway", json!({ "id": "MerchantName", "slot": "trade1", "rid": "x7Qa" })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("join_giveaway failed: {}", r["response"]);
} else {
    println!("{}", r["response"]);
}
```

```java
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("join_giveaway"), Duration.ofSeconds(10));
sock.emit("join_giveaway", Map.of("id", "MerchantName", "slot", "trade1", "rid", "x7Qa"));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("join_giveaway failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText());
```

**Source:** `node/server.js:8737-8789`

### `trade_wishlist`
Puts a wishlist entry (a "buy" request) in a trade slot of the player.

<!-- schema -->

**Limits:** `get_trade_slots` gives 16 slots with a stand. A merchant at level 70 or more, or with a `cstand`, gets 24. A merchant at level 80 or more gets 30. Without a stand, `p.trades` gives 4 slots.

**Example:**

```js
// sock: a connected AlSocket (Learn, "Socket.IO by hand")
// Register the wait before emit: the reply can arrive first.
const reply = sock.waitFor("game_response", (r) => r?.place === "trade_wishlist");
sock.emit("trade_wishlist", { slot: "trade2", name: "wbook0", q: 1, price: 2000000, level: 0 });
const r = await reply;
if (r.failed) console.log("trade_wishlist failed:", r.response); // a code from the Failure table
else console.log(r.response);
```

```ts
interface TradeWishlistReply {
  response: string;
  place: string;
  failed?: boolean;
}
const reply = sock.waitFor<TradeWishlistReply>("game_response", (r) => r?.place === "trade_wishlist");
sock.emit("trade_wishlist", { slot: "trade2", name: "wbook0", q: 1, price: 2000000, level: 0 });
const r = await reply;
if (r.failed) console.log("trade_wishlist failed:", r.response);
else console.log(r.response);
```

```python
reply = sock.wait_for("game_response", lambda r: isinstance(r, dict) and r.get("place") == "trade_wishlist")
await sock.emit("trade_wishlist", {"slot": "trade2", "name": "wbook0", "q": 1, "price": 2000000, "level": 0})
r = await reply
if r.get("failed"):
    print("trade_wishlist failed:", r["response"])
else:
    print(r["response"])
```

```go
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r struct{ Place string }
	return json.Unmarshal(d, &r) == nil && r.Place == "trade_wishlist" // a bare string fails to decode
})
if err := sock.Emit("trade_wishlist", map[string]any{"slot": "trade2", "name": "wbook0", "q": 1, "price": 2000000, "level": 0}); err != nil {
	return err
}
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
defer cancel()
data, err := wait(ctx)
if err != nil {
	return err
}
var r struct { Response string; Failed bool }
if err := json.Unmarshal(data, &r); err != nil {
	return err
}
if r.Failed {
	fmt.Println("trade_wishlist failed:", r.Response)
} else {
	fmt.Println(r.Response)
}
```

```csharp
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "trade_wishlist");
await sock.EmitAsync("trade_wishlist", new { slot = "trade2", name = "wbook0", q = 1, price = 2000000, level = 0 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"trade_wishlist failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"{r.GetProperty("response")}");
```

```rust
let reply = sock.wait_for("game_response", |r| r["place"] == "trade_wishlist");
sock.emit("trade_wishlist", json!({ "slot": "trade2", "name": "wbook0", "q": 1, "price": 2000000, "level": 0 })).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("trade_wishlist failed: {}", r["response"]);
} else {
    println!("{}", r["response"]);
}
```

```java
var reply = sock.waitFor("game_response", d -> d.path("place").asText().equals("trade_wishlist"), Duration.ofSeconds(10));
sock.emit("trade_wishlist", Map.of("slot", "trade2", "name", "wbook0", "q", 1, "price", 2000000, "level", 0));
JsonNode r = reply.get(); // blocks this thread until the reply
if (r.path("failed").asBoolean()) System.out.println("trade_wishlist failed: " + r.path("response").asText());
else System.out.println(r.path("response").asText());
```

**Source:** `node/server.js:8790-8821` (slots `node/server_functions.js:4282-4299`)
