### `trade_sell`
Sells an item from your inventory to a buy order on the merchant stand of another player. A buy order is a trade slot whose item has the `b` flag.

<!-- schema -->

**Limits:**
- Range: `B.dist` (400 px) to the buyer, on the same map and in the same instance.
- Tax: you get `round(price * q * (1 - tax))`, where `tax` is your own rate: 0.01 to 0.05 by level (node/server.js:1718-1725). The buyer pays `price * q`.

**Notes:**
- The server takes the item from the first inventory slot that matches: the same `name` and `level`, at least `q` units, and no lock. You cannot choose the slot.
- A merchant on either side gets XP: 3.2 times the tax of the sale, at the tax rate of that merchant. A trade between characters of the same account gives no XP.
- Both sides add a line to their trade history (see [`trade_history`](#send-trade_history)).

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "trade_sell");
sock.emit("trade_sell", { id: "MerchantBob", slot: "trade3", rid: "AbCd", q: 5 });
const r = await reply;
if (r.failed) console.log("trade_sell failed:", r.response);
else console.log("sold");
```

```ts
interface TradeSellRequest { id: string; slot: string; rid?: string; q?: number }
interface GameResponse { response: string; place?: string; failed?: boolean }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "trade_sell");
const req: TradeSellRequest = { id: "MerchantBob", slot: "trade3", rid: "AbCd", q: 5 };
sock.emit("trade_sell", req);
const r = await reply;
if (r.failed) console.log("trade_sell failed:", r.response);
else console.log("sold");
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "trade_sell")
await sock.emit("trade_sell", {"id": "MerchantBob", "slot": "trade3", "rid": "AbCd", "q": 5})
r = await reply
if r.get("failed"):
    print("trade_sell failed:", r["response"])
else:
    print("sold")
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "trade_sell"
})
sock.Emit("trade_sell", map[string]any{"id": "MerchantBob", "slot": "trade3", "rid": "AbCd", "q": 5})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed {
	fmt.Println("trade_sell failed:", r.Response)
} else {
	fmt.Println("sold")
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "trade_sell");
await sock.EmitAsync("trade_sell", new { id = "MerchantBob", slot = "trade3", rid = "AbCd", q = 5 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"trade_sell failed: {r.GetProperty("response")}");
else
    Console.WriteLine("sold");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "trade_sell");
sock.emit("trade_sell", json!({"id": "MerchantBob", "slot": "trade3", "rid": "AbCd", "q": 5})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("trade_sell failed: {}", r["response"]);
} else {
    println!("sold");
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "trade_sell".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("trade_sell", Map.of("id", "MerchantBob", "slot", "trade3", "rid", "AbCd", "q", 5));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
if (r.path("failed").asBoolean())
    System.out.println("trade_sell failed: " + r.path("response").asText());
else
    System.out.println("sold");
```

**Source:** `node/server.js:8822-8953`. Merchant XP: `node/server_functions.js:746-751`. That is the second `merchant_xp_logic` in the file, and it replaces the first one at `node/server_functions.js:730`.

### `trade_buy`
Buys an item that another player sells for gold in a trade slot of their merchant stand.

<!-- schema -->

**Limits:**
- Range: `B.dist` (400 px) to the seller, on the same map.
- Tax: the seller gets `round(price * q * (1 - tax))`, where `tax` is the rate of the seller (node/server.js:1718-1725). You pay `price * q`.

**Notes:**
- `num` in the `ui` event is the `num` of your request, not your inventory slot. The server does not send the slot that got the item.
- If you and the seller are on different accounts, the server sets `src: "tb"` on the listing object. For an item that does not stack, that object is the item that you get. Clients do not get `src`.
- Merchants get XP as in [`trade_sell`](#send-trade_sell). Both sides add a line to their trade history.

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "trade_buy");
sock.emit("trade_buy", { id: "MerchantBob", slot: "trade1", rid: "AbCd", q: 1 });
const r = await reply;
if (r.failed) console.log("trade_buy failed:", r.response);
else console.log("bought");
```

```ts
interface TradeBuyRequest { id: string; slot: string; rid?: string; q?: number }
interface GameResponse { response: string; place?: string; failed?: boolean }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "trade_buy");
const req: TradeBuyRequest = { id: "MerchantBob", slot: "trade1", rid: "AbCd", q: 1 };
sock.emit("trade_buy", req);
const r = await reply;
if (r.failed) console.log("trade_buy failed:", r.response);
else console.log("bought");
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "trade_buy")
await sock.emit("trade_buy", {"id": "MerchantBob", "slot": "trade1", "rid": "AbCd", "q": 1})
r = await reply
if r.get("failed"):
    print("trade_buy failed:", r["response"])
else:
    print("bought")
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "trade_buy"
})
sock.Emit("trade_buy", map[string]any{"id": "MerchantBob", "slot": "trade1", "rid": "AbCd", "q": 1})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed {
	fmt.Println("trade_buy failed:", r.Response)
} else {
	fmt.Println("bought")
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "trade_buy");
await sock.EmitAsync("trade_buy", new { id = "MerchantBob", slot = "trade1", rid = "AbCd", q = 1 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"trade_buy failed: {r.GetProperty("response")}");
else
    Console.WriteLine("bought");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "trade_buy");
sock.emit("trade_buy", json!({"id": "MerchantBob", "slot": "trade1", "rid": "AbCd", "q": 1})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("trade_buy failed: {}", r["response"]);
} else {
    println!("bought");
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "trade_buy".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("trade_buy", Map.of("id", "MerchantBob", "slot", "trade1", "rid", "AbCd", "q", 1));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
if (r.path("failed").asBoolean())
    System.out.println("trade_buy failed: " + r.path("response").asText());
else
    System.out.println("bought");
```

**Source:** `node/server.js:8954-9060`

### `trade_swap`
Accepts a trade offer on the merchant stand of another player. You give the item that the offer asks for and get the listed item, with no gold.

<!-- schema -->

**Limits:** a merchant below level 70 gets XP: `round(value * tax * 3.2)`, where `value` is the lower of the two item values. The XP limit per partner account is the XP for one level at the current level of the merchant, in a 5-day window. The server tracks at most 120 partner accounts in that window. A trade between characters of the same account gives no XP.

**Notes:**
- A trade offer is a trade slot whose item has a `want` (a [`TradeWant`](#type-tradewant)) instead of a `price`. The stand owner makes it with `equip` and a `want` value.
- The server takes `want.q` units (1 for an item that does not stack) from slot `num`. It clears the trade slot and gives you the listed item without its `want` and `rid`.
- If you and the owner are on different accounts, both items get `src: "ts"`. Clients do not get `src`.
- Both sides add a swap line to their trade history: `["swap", partner, given, 0, received]`.

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "trade_swap");
sock.emit("trade_swap", { id: "MerchantBob", slot: "trade2", rid: "AbCd", num: 7, item: { name: "staff", level: 8 } });
const r = await reply;
if (r.failed) console.log("trade_swap failed:", r.response);
else console.log("swapped, listed item now in slot", r.num);
```

```ts
interface TradeSwapRequest { id: string; slot: string; rid: string; num: number; item: { name: string; level?: number; q?: number } }
interface GameResponse { response: string; place?: string; failed?: boolean; num?: number }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "trade_swap");
const req: TradeSwapRequest = { id: "MerchantBob", slot: "trade2", rid: "AbCd", num: 7, item: { name: "staff", level: 8 } };
sock.emit("trade_swap", req);
const r = await reply;
if (r.failed) console.log("trade_swap failed:", r.response);
else console.log("swapped, listed item now in slot", r.num);
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "trade_swap")
await sock.emit("trade_swap", {"id": "MerchantBob", "slot": "trade2", "rid": "AbCd", "num": 7, "item": {"name": "staff", "level": 8}})
r = await reply
if r.get("failed"):
    print("trade_swap failed:", r["response"])
else:
    print("swapped, listed item now in slot", r["num"])
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`
	Num      int    `json:"num"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "trade_swap"
})
sock.Emit("trade_swap", map[string]any{"id": "MerchantBob", "slot": "trade2", "rid": "AbCd", "num": 7, "item": map[string]any{"name": "staff", "level": 8}})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed {
	fmt.Println("trade_swap failed:", r.Response)
} else {
	fmt.Println("swapped, listed item now in slot", r.Num)
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "trade_swap");
await sock.EmitAsync("trade_swap", new { id = "MerchantBob", slot = "trade2", rid = "AbCd", num = 7, item = new { name = "staff", level = 8 } });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"trade_swap failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"swapped, listed item now in slot {r.GetProperty("num")}");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "trade_swap");
sock.emit("trade_swap", json!({"id": "MerchantBob", "slot": "trade2", "rid": "AbCd", "num": 7, "item": {"name": "staff", "level": 8}})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("trade_swap failed: {}", r["response"]);
} else {
    println!("swapped, listed item now in slot {}", r["num"]);
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "trade_swap".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("trade_swap", Map.of("id", "MerchantBob", "slot", "trade2", "rid", "AbCd", "num", 7, "item", Map.of("name", "staff", "level", 8)));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
if (r.path("failed").asBoolean())
    System.out.println("trade_swap failed: " + r.path("response").asText());
else
    System.out.println("swapped, listed item now in slot" + " " + r.path("num").asText());
```

**Source:** `node/server.js:9061-9176`. Checks: `seen_item_matches` at `node/server_functions.js:4263`, `trade_want_matches` at `js/old_common_functions.js:484`, `trade_want_normalize` at `js/old_common_functions.js:469`. XP: `trade_swap_xp` at `node/server_functions.js:753`.

### `trade_history`
Asks for the trade history of your character.

<!-- schema -->

**Limits:** the server keeps the last 40 lines.

**Notes:** a new purchase or sale can have the same event, partner, item name and level as the last line. Then the server adds its quantity and price to that line. A swap always gets a new line.

**Example:**

```js
// sock: a connected AlSocket
// The reply is its own event, `trade_history`. Start the wait before the emit.
const reply = sock.waitFor("trade_history");
sock.emit("trade_history", {});
// A line: [event, name, item, price], or ["swap", name, given, 0, received]
for (const [event, name, item, price] of await reply) console.log(event, name, item.name, price);
```

```ts
interface TradeItem { name: string; level?: number; q?: number }
/** [event, name, item, price], or ["swap", name, given, 0, received] */
type TradeLine = [event: "buy" | "sell" | "swap", name: string, item: TradeItem, price: number, received?: TradeItem];
const reply = sock.waitFor<TradeLine[]>("trade_history");
sock.emit("trade_history", {});
for (const [event, name, item, price] of await reply) console.log(event, name, item.name, price);
```

```python
# sock: a connected AlSocket; this runs in an async function
reply = sock.wait_for("trade_history")  # the reply is its own event
await sock.emit("trade_history", {})
# A line: [event, name, item, price], or ["swap", name, given, 0, received]
for event, name, item, price, *received in await reply:
    print(event, name, item["name"], price)
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
wait := sock.Expect("trade_history", nil) // the reply is its own event
sock.Emit("trade_history", map[string]any{})
d, err := wait(ctx)
// A line: [event, name, item, price], or ["swap", name, given, 0, received]
var lines [][]any
if err != nil || json.Unmarshal(d, &lines) != nil {
	fmt.Println("no reply:", err)
	return
}
for _, l := range lines {
	fmt.Println(l[0], l[1], l[2].(map[string]any)["name"], l[3])
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("trade_history");
await sock.EmitAsync("trade_history", new { });
// A line: [event, name, item, price], or ["swap", name, given, 0, received]
foreach (var line in (await reply).EnumerateArray())
    Console.WriteLine($"{line[0]} {line[1]} {line[2].GetProperty("name")} {line[3]}");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
let reply = sock.wait_for("trade_history", |_: &Value| true); // the reply is its own event
sock.emit("trade_history", json!({})).await?;
// A line: [event, name, item, price], or ["swap", name, given, 0, received]
for line in reply.await?.as_array().cloned().unwrap_or_default() {
    println!("{} {} {} {}", line[0], line[1], line[2]["name"], line[3]);
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("trade_history"); // the reply is its own event
sock.emit("trade_history", Map.of());
// A line: [event, name, item, price], or ["swap", name, given, 0, received]
for (JsonNode line : reply.get())
    System.out.println(line.get(0).asText() + " " + line.get(1).asText() + " "
            + line.get(2).path("name").asText() + " " + line.get(3));
```

**Source:** `node/server.js:9177-9184`. Lines: `add_to_trade_history` at `node/server_functions.js:342`.

### `merchant`
Opens or closes your merchant stand. To open it, you use a stand item from your inventory.

<!-- schema -->

**Limits:** the number of open trade slots depends on the stand and your class. All characters get 16. A merchant gets 24 at level 70 or with a `cstand`, and 30 at level 80 (`get_trade_slots`, `node/server_functions.js:4282`).

**Notes:**
- `merchant` with no fields closes an open stand. It never opens one.
- The server marks the stand item with `b: "stand"` (clients do not get `b`). Requests that refuse an item with `b`, for example `trade_sell` and `trade_swap`, refuse the stand item while the stand is open.
- Each request resets the market patron state of the stand (`market_patron_reset`, node/logic/market_patron_runtime.js:9-14).

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "merchant");
sock.emit("merchant", { num: 12 });
const r = await reply;
if (r.failed) console.log("merchant failed:", r.response);
else console.log("stand open");
```

```ts
interface MerchantRequest { num?: number; close?: boolean }
interface GameResponse { response: string; place?: string; failed?: boolean }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "merchant");
const req: MerchantRequest = { num: 12 };
sock.emit("merchant", req);
const r = await reply;
if (r.failed) console.log("merchant failed:", r.response);
else console.log("stand open");
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "merchant")
await sock.emit("merchant", {"num": 12})
r = await reply
if r.get("failed"):
    print("merchant failed:", r["response"])
else:
    print("stand open")
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "merchant"
})
sock.Emit("merchant", map[string]any{"num": 12})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed {
	fmt.Println("merchant failed:", r.Response)
} else {
	fmt.Println("stand open")
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "merchant");
await sock.EmitAsync("merchant", new { num = 12 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"merchant failed: {r.GetProperty("response")}");
else
    Console.WriteLine("stand open");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "merchant");
sock.emit("merchant", json!({"num": 12})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("merchant failed: {}", r["response"]);
} else {
    println!("stand open");
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "merchant".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("merchant", Map.of("num", 12));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
if (r.path("failed").asBoolean())
    System.out.println("merchant failed: " + r.path("response").asText());
else
    System.out.println("stand open");
```

**Source:** `node/server.js:9185-9219`

### `imove`
Moves or swaps the items in two inventory slots. If the two items can stack, the server merges them.

<!-- schema -->

**Notes:**
- When the items stack, slot `a` of the request gets the stack, also when `a` is the higher index.
- Two items of the same stackable kind that do not fit in one stack swap. They do not merge in part.

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "imove");
sock.emit("imove", { a: 0, b: 5 });
const r = await reply;
if (r.failed) console.log("imove failed:", r.response);
else console.log("moved");
```

```ts
interface ImoveRequest { a: number; b: number }
interface GameResponse { response: string; place?: string; failed?: boolean }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "imove");
const req: ImoveRequest = { a: 0, b: 5 };
sock.emit("imove", req);
const r = await reply;
if (r.failed) console.log("imove failed:", r.response);
else console.log("moved");
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "imove")
await sock.emit("imove", {"a": 0, "b": 5})
r = await reply
if r.get("failed"):
    print("imove failed:", r["response"])
else:
    print("moved")
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "imove"
})
sock.Emit("imove", map[string]any{"a": 0, "b": 5})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed {
	fmt.Println("imove failed:", r.Response)
} else {
	fmt.Println("moved")
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "imove");
await sock.EmitAsync("imove", new { a = 0, b = 5 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"imove failed: {r.GetProperty("response")}");
else
    Console.WriteLine("moved");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "imove");
sock.emit("imove", json!({"a": 0, "b": 5})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("imove failed: {}", r["response"]);
} else {
    println!("moved");
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "imove".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("imove", Map.of("a", 0, "b", 5));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
if (r.path("failed").asBoolean())
    System.out.println("imove failed: " + r.path("response").asText());
else
    System.out.println("moved");
```

**Source:** `node/server.js:9220-9256`

### `bank`
Does all bank operations: deposit and withdraw gold, unlock bank packs, and move items in a pack or between a pack and your inventory. It works only on a bank map.

<!-- schema -->

**Limits:**
- A pack holds 42 slots (0 to 41).
- `move` and `swap` work only on the bank map of the pack (`bank`, `bank_b` or `bank_u`). `deposit`, `withdraw` and `unlock` work on any bank map.

**Notes:**
- A `swap` removes the `m` and `v` flags from the inventory item.
- A `swap` that finds no empty slot uses slot 0 (the pack for a store, the inventory for a retrieve). Then the store or retrieve adds to a stack there, or fails with `storage_full` or `inventory_full`.
- `withdraw` and `deposit` send two `game_response` events: `data`, then the real code. A gold `unlock` does the same with `bank_new_pack`.
- **Server bug:** `move` and `swap` accept a `pack` that is not a bank pack when `player.user` has a value for it (for example `"gold"`). Then the handler throws on `bank_packs[pack][0]`, and you get `game_error` "ERROR!" (node/server.js:9373, 9403).

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "bank");
sock.emit("bank", { operation: "deposit", amount: 100000 });
const r = await reply;
if (r.failed) console.log("bank failed:", r.response);
else console.log("deposited", r.gold);
```

```ts
interface BankRequest { operation: "withdraw" | "deposit" | "unlock" | "move" | "swap"; amount?: number }
interface GameResponse { response: string; place?: string; failed?: boolean; gold?: number }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "bank");
const req: BankRequest = { operation: "deposit", amount: 100000 };
sock.emit("bank", req);
const r = await reply;
if (r.failed) console.log("bank failed:", r.response);
else console.log("deposited", r.gold);
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "bank")
await sock.emit("bank", {"operation": "deposit", "amount": 100000})
r = await reply
if r.get("failed"):
    print("bank failed:", r["response"])
else:
    print("deposited", r["gold"])
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`
	Gold     int    `json:"gold"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "bank"
})
sock.Emit("bank", map[string]any{"operation": "deposit", "amount": 100000})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed {
	fmt.Println("bank failed:", r.Response)
} else {
	fmt.Println("deposited", r.Gold)
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "bank");
await sock.EmitAsync("bank", new { operation = "deposit", amount = 100000 });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"bank failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"deposited {r.GetProperty("gold")}");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "bank");
sock.emit("bank", json!({"operation": "deposit", "amount": 100000})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("bank failed: {}", r["response"]);
} else {
    println!("deposited {}", r["gold"]);
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "bank".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("bank", Map.of("operation", "deposit", "amount", 100000));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
if (r.path("failed").asBoolean())
    System.out.println("bank failed: " + r.path("response").asText());
else
    System.out.println("deposited" + " " + r.path("gold").asText());
```

**Source:** `node/server.js:9257`

### `throw`
Throws an item from your inventory at a map position. The item must have `throw` in `G.items` (for example, `confetti`, `firecrackers`, `whiteegg` or `smoke`). This is the `throw` event, not the `throw` skill.

<!-- schema -->

**Limits:** range: `player.str * 3` px from you (the check does not stop the throw, see Notes). Each throw uses one item.

**Notes:**
- The effect depends on the item. `confetti` and `firecrackers` make you "thrilling" (`player.thrilling`) for 20 s and 200 s.
- `firecrackers` stop the chase of monsters within 64 px of the target position. This applies only to a monster whose target passes `is_same(you, target, 1)`: the same character, account, IP address, coop, party or team (node/server_functions.js:505-525).
- `whiteegg`: each monster within 32 px of the target position that has no target starts to attack you.
- **Server bug:** the `too_far` check sends the failure but does not stop the handler. The throw still happens, and you then also get the success reply.

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "throw");
sock.emit("throw", { num: 10, x: 120, y: -40 });
const r = await reply;
// too_far arrives first, then success (server bug)
if (r.failed) console.log("throw failed:", r.response);
else console.log("thrown");
```

```ts
interface ThrowRequest { num: number; x: number; y: number }
interface GameResponse { response: string; place?: string; failed?: boolean }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "throw");
const req: ThrowRequest = { num: 10, x: 120, y: -40 };
sock.emit("throw", req);
const r = await reply;
// too_far arrives first, then success (server bug)
if (r.failed) console.log("throw failed:", r.response);
else console.log("thrown");
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "throw")
await sock.emit("throw", {"num": 10, "x": 120, "y": -40})
r = await reply
# too_far arrives first, then success (server bug)
if r.get("failed"):
    print("throw failed:", r["response"])
else:
    print("thrown")
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "throw"
})
sock.Emit("throw", map[string]any{"num": 10, "x": 120, "y": -40})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed { // too_far arrives first, then success (server bug)
	fmt.Println("throw failed:", r.Response)
} else {
	fmt.Println("thrown")
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "throw");
await sock.EmitAsync("throw", new { num = 10, x = 120, y = -40 });
var r = await reply;
// too_far arrives first, then success (server bug)
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"throw failed: {r.GetProperty("response")}");
else
    Console.WriteLine("thrown");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "throw");
sock.emit("throw", json!({"num": 10, "x": 120, "y": -40})).await?;
let r = reply.await?;
// too_far arrives first, then success (server bug)
if r["failed"] == true {
    println!("throw failed: {}", r["response"]);
} else {
    println!("thrown");
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "throw".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("throw", Map.of("num", 10, "x", 120, "y", -40));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
// too_far arrives first, then success (server bug)
if (r.path("failed").asBoolean())
    System.out.println("throw failed: " + r.path("response").asText());
else
    System.out.println("thrown");
```

**Source:** `node/server.js:9484`

### `poke`
Pokes another player. It works only while you wear the `poker` gloves.

<!-- schema -->

**Limits:** 50 pokes, counted in `player.pokes`. No code resets or saves the counter; whether it persists after a logout is unclear from the source.

**Example:**

```js
// sock: a connected AlSocket
// Players near the poker get `poke`. A failure sends nothing, or a game_log.
sock.on("poke", (d) => console.log(`${d.who} poked ${d.name}, level ${d.level}`));
sock.emit("poke", { name: "SomePlayer" });
```

```ts
interface PokeRequest { name: string }
interface PokeEvent { name: string; level: 1 | 2 | 3 | 4; who: string }
sock.on<PokeEvent>("poke", (p) => console.log(`${p.who} poked ${p.name}, level ${p.level}`));
const req: PokeRequest = { name: "SomePlayer" };
sock.emit("poke", req);
```

```python
# sock: a connected AlSocket; this runs in an async function
def on_poke(d: Any) -> None:
    print(f"{d['who']} poked {d['name']}, level {d['level']}")

sock.on("poke", on_poke)
await sock.emit("poke", {"name": "SomePlayer"})
```

```go
// sock: a connected *alsocket.Socket
sock.On("poke", func(d json.RawMessage) {
	var p struct {
		Name  string `json:"name"`
		Level int    `json:"level"`
		Who   string `json:"who"`
	}
	if json.Unmarshal(d, &p) == nil {
		fmt.Printf("%s poked %s, level %d\n", p.Who, p.Name, p.Level)
	}
})
sock.Emit("poke", map[string]any{"name": "SomePlayer"})
```

```csharp
// sock: a connected AlSocket
sock.On("poke", d => Console.WriteLine(
    $"{d.GetProperty("who")} poked {d.GetProperty("name")}, level {d.GetProperty("level")}"));
await sock.EmitAsync("poke", new { name = "SomePlayer" });
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
sock.on("poke", |d: &Value| println!("{} poked {}, level {}", d["who"], d["name"], d["level"]));
sock.emit("poke", json!({"name": "SomePlayer"})).await?;
```

```java
// sock: a connected AlSocket
sock.on("poke", d -> System.out.println(
        d.path("who").asText() + " poked " + d.path("name").asText() + ", level " + d.path("level")));
sock.emit("poke", Map.of("name", "SomePlayer"));
```

**Source:** `node/server.js:9554`

### `merge`
Merges a pet container item into another container item in your equipment slots. The first container keeps the pet data.

<!-- schema -->

**Notes:**
- **Server bug:** the handler reads `type` on the item in the slot, not on `G.items` (node/server.js:9580). An item in a slot has no `type` field (see [`ItemInstance`](#type-iteminstance)). So every merge fails with `merge_mismatch`.
- In G 17478 the only item of type `container` is `monsterbox`, and no item has a `pet` property.
- If the checks passed, the server would copy `G.items[pet item].pet` into `data` of the container and clear the `pet` slot.

**Example:**

```js
// sock: a connected AlSocket
// Two equipment slots that hold container items (example names; which slots can is unclear).
const container = "mainhand", pet = "offhand";
// The replies are bare strings: "merge_complete" or "merge_mismatch".
const reply = sock.waitFor("game_response", (d) => d === "merge_complete" || d === "merge_mismatch");
sock.emit("merge", { container, pet });
console.log(await reply);
```

```ts
interface MergeRequest { container: string; pet: string }
type MergeReply = "merge_complete" | "merge_mismatch"; // bare strings, not objects
const container = "mainhand", pet = "offhand"; // example slot names
const reply = sock.waitFor<MergeReply>("game_response", (d) => d === "merge_complete" || d === "merge_mismatch");
const req: MergeRequest = { container, pet };
sock.emit("merge", req);
const r = await reply;
console.log(r === "merge_complete" ? "merged" : "mismatch");
```

```python
# sock: a connected AlSocket
container, pet = "mainhand", "offhand"  # example slot names
reply = sock.wait_for("game_response", lambda d: d in ("merge_complete", "merge_mismatch"))
await sock.emit("merge", {"container": container, "pet": pet})
print(await reply)  # a bare string
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
container, pet := "mainhand", "offhand" // example slot names
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var s string // the replies are bare strings
	return json.Unmarshal(d, &s) == nil && (s == "merge_complete" || s == "merge_mismatch")
})
sock.Emit("merge", map[string]any{"container": container, "pet": pet})
d, err := wait(ctx)
var s string
if err == nil && json.Unmarshal(d, &s) == nil {
	fmt.Println(s)
}
```

```csharp
// sock: a connected AlSocket
var (container, pet) = ("mainhand", "offhand"); // example slot names
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.String
    && d.GetString() is "merge_complete" or "merge_mismatch");
await sock.EmitAsync("merge", new { container, pet });
Console.WriteLine((await reply).GetString());
```

```rust
// sock: a connected AlSocket
let (container, pet) = ("mainhand", "offhand"); // example slot names
let reply = sock.wait_for("game_response", |d: &Value| d == "merge_complete" || d == "merge_mismatch");
sock.emit("merge", json!({"container": container, "pet": pet})).await?;
println!("{}", reply.await?); // a bare string
```

```java
// sock: a connected AlSocket
String container = "mainhand", pet = "offhand"; // example slot names
var reply = sock.waitFor("game_response",
        d -> d.isTextual() && List.of("merge_complete", "merge_mismatch").contains(d.asText()),
        Duration.ofSeconds(5));
sock.emit("merge", Map.of("container", container, "pet", pet));
System.out.println(reply.get().asText()); // a bare string
```

**Source:** `node/server.js:9573`

### `activate`
Activates an equipped item (`etherealamulet`, `angelwings`, `tristone`, `darktristone`) or an inventory item (`frozenstone`, `bkey`, `ukey`, `dkey`).

<!-- schema -->

**Notes:**
- `angelwings` turns the `snow_angel` temporary skin (`tskin`) on or off.
- `tristone` and `darktristone` remove any temporary skin that is on. Otherwise they set a skin that depends on the item level and the gender of the character, and add 1 to `player.tactivations`.
- When `player.tactivations` is exactly 100, the next `tristone` or `darktristone` activation only removes the skin. The count then goes to 101, and later activations set skins again (node/server.js:9620, 9639).
- `frozenstone`: the server uses one. This handler has no other effect for it.
- A `num` slot that is empty, or an item with no branch here, still gets the `player` update with `reopen: true` (node/server.js:9710).

**Example:**

```js
// sock: a connected AlSocket
// A dkey in inventory slot 7. The replies are bare strings, for example
// "bank_pack_unlocked" or "only_in_bank". Some paths send no game_response.
const reply = sock.waitFor("game_response", (d) => typeof d === "string", 3000);
sock.emit("activate", { num: 7 });
console.log(await reply);
```

```ts
interface ActivateRequest { slot?: string; num?: number }
// The replies are bare strings. The predicate checks it; the type parameter only tells tsc.
const reply = sock.waitFor<string>("game_response", (d) => typeof d === "string", 3000);
const req: ActivateRequest = { num: 7 }; // a dkey in inventory slot 7
sock.emit("activate", req);
const code = await reply; // "bank_pack_unlocked", "only_in_bank", ...
console.log(code);
```

```python
# sock: a connected AlSocket; this runs in an async function
# A dkey in inventory slot 7. The replies are bare strings. Some paths send none.
reply = sock.wait_for("game_response", lambda d: isinstance(d, str), timeout=3)
await sock.emit("activate", {"num": 7})
print(await reply)  # "bank_pack_unlocked", "only_in_bank", ...
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
// A dkey in inventory slot 7. The replies are bare strings. Some paths send none.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var s string
	return json.Unmarshal(d, &s) == nil
})
sock.Emit("activate", map[string]any{"num": 7})
d, err := wait(ctx)
var code string // "bank_pack_unlocked", "only_in_bank", ...
if err == nil && json.Unmarshal(d, &code) == nil {
	fmt.Println(code)
}
```

```csharp
// sock: a connected AlSocket
// A dkey in inventory slot 7. The replies are bare strings. Some paths send none.
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.String,
    TimeSpan.FromSeconds(3));
await sock.EmitAsync("activate", new { num = 7 });
Console.WriteLine((await reply).GetString()); // "bank_pack_unlocked", "only_in_bank", ...
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// A dkey in inventory slot 7. The replies are bare strings. Some paths send none.
let reply = sock.wait_for_timeout("game_response", |d: &Value| d.is_string(), Duration::from_secs(3));
sock.emit("activate", json!({"num": 7})).await?;
println!("{}", reply.await?); // "bank_pack_unlocked", "only_in_bank", ...
```

```java
// sock: a connected AlSocket
// A dkey in inventory slot 7. The replies are bare strings. Some paths send none.
var reply = sock.waitFor("game_response", JsonNode::isTextual, Duration.ofSeconds(3));
sock.emit("activate", Map.of("num", 7));
System.out.println(reply.get().asText()); // "bank_pack_unlocked", "only_in_bank", ...
```

**Source:** `node/server.js:9591`

### `booster`
Activates an XP, luck or gold booster in your inventory, or changes it to a different booster type.

<!-- schema -->

**Notes:**
- `activate` sets `expires` to the time now plus 30 days plus 2 days per level of the item. On a booster that has `expires` already, it changes nothing.
- `shift` changes the name of the item. It also sets `xpm`, `goldm` and `luckm` to 1, and adds 240 ms to the `penalty_cd` condition (up to 120,000 ms).

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "booster");
sock.emit("booster", { num: 3, action: "shift", to: "goldbooster" });
const r = await reply;
if (r.failed) console.log("booster failed:", r.response);
else console.log("booster is now", r.name);
```

```ts
interface BoosterRequest { num: number; action: "activate" | "shift"; to?: "xpbooster" | "luckbooster" | "goldbooster" }
interface GameResponse { response: string; place?: string; failed?: boolean; name?: string }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "booster");
const req: BoosterRequest = { num: 3, action: "shift", to: "goldbooster" };
sock.emit("booster", req);
const r = await reply;
if (r.failed) console.log("booster failed:", r.response);
else console.log("booster is now", r.name);
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "booster")
await sock.emit("booster", {"num": 3, "action": "shift", "to": "goldbooster"})
r = await reply
if r.get("failed"):
    print("booster failed:", r["response"])
else:
    print("booster is now", r["name"])
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`
	Name     string `json:"name"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "booster"
})
sock.Emit("booster", map[string]any{"num": 3, "action": "shift", "to": "goldbooster"})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed {
	fmt.Println("booster failed:", r.Response)
} else {
	fmt.Println("booster is now", r.Name)
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "booster");
await sock.EmitAsync("booster", new { num = 3, action = "shift", to = "goldbooster" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"booster failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"booster is now {r.GetProperty("name")}");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "booster");
sock.emit("booster", json!({"num": 3, "action": "shift", "to": "goldbooster"})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("booster failed: {}", r["response"]);
} else {
    println!("booster is now {}", r["name"]);
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "booster".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("booster", Map.of("num", 3, "action", "shift", "to", "goldbooster"));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
if (r.path("failed").asBoolean())
    System.out.println("booster failed: " + r.path("response").asText());
else
    System.out.println("booster is now" + " " + r.path("name").asText());
```

**Source:** `node/server.js:9713`

### `convert`
Converts a stone booster (`stoneofxp`, `stoneofgold`, `stoneofluck`) into shells. These items are no longer in the game.

<!-- schema -->

**Notes:**
- The amount is 3,600 shells. A stone with `expires` gives `round(600 - hsince(expires) * 100 / 24)`: 600 at the expiry time, 100 less per day after it (node/server.js:9756-9758).
- More than 6 days after `expires` the amount is below 0. Then `add_shells` subtracts shells from your character (node/server.js:4765).
- On a `hardcore` or `test` server, `add_shells` does nothing, but the server still removes the stone (node/server.js:4761-4763).
- **Server bug:** the handler does not check for a character. If the socket has no character, the handler throws, and you get `game_error` "ERROR!".

**Example:**

```js
// sock: a connected AlSocket
// No game_response: success sends a game_log about the shells, then `player`.
const update = sock.waitFor("player", undefined, 3000);
sock.emit("convert", { num: 3 });
const me = await update;
console.log("slot 3 is now", me.items[3]); // null: the server removes the whole slot
```

```ts
interface ConvertRequest { num: number }
interface PlayerUpdate { items: ({ name: string } | null)[] }
const update = sock.waitFor<PlayerUpdate>("player", undefined, 3000);
const req: ConvertRequest = { num: 3 };
sock.emit("convert", req);
const me = await update;
console.log("slot 3 is now", me.items[3]); // null: the server removes the whole slot
```

```python
# sock: a connected AlSocket; this runs in an async function
# No game_response: success sends a game_log about the shells, then `player`.
update = sock.wait_for("player", timeout=3)
await sock.emit("convert", {"num": 3})
me = await update
print("slot 3 is now", me["items"][3])  # None: the server removes the whole slot
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
// No game_response: success sends a game_log about the shells, then `player`.
wait := sock.Expect("player", nil)
sock.Emit("convert", map[string]any{"num": 3})
d, err := wait(ctx)
var me struct {
	Items []json.RawMessage `json:"items"`
}
if err == nil && json.Unmarshal(d, &me) == nil && len(me.Items) > 3 {
	fmt.Println("slot 3 is now", string(me.Items[3])) // null: the server removes the whole slot
}
```

```csharp
// sock: a connected AlSocket
// No game_response: success sends a game_log about the shells, then `player`.
var update = sock.WaitForAsync("player", null, TimeSpan.FromSeconds(3));
await sock.EmitAsync("convert", new { num = 3 });
var me = await update;
Console.WriteLine($"slot 3 is now {me.GetProperty("items")[3]}"); // null: the slot is removed
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// No game_response: success sends a game_log about the shells, then `player`.
let update = sock.wait_for_timeout("player", |_: &Value| true, Duration::from_secs(3));
sock.emit("convert", json!({"num": 3})).await?;
let me = update.await?;
println!("slot 3 is now {}", me["items"][3]); // null: the server removes the whole slot
```

```java
// sock: a connected AlSocket
// No game_response: success sends a game_log about the shells, then `player`.
var update = sock.waitFor("player", d -> true, Duration.ofSeconds(3));
sock.emit("convert", Map.of("num", 3));
JsonNode me = update.get();
System.out.println("slot 3 is now " + me.path("items").get(3)); // null: the slot is removed
```

**Source:** `node/server.js:9741`

### `skill`
Uses a class skill, an item skill or an emote. `attack` and `heal` are short forms of this event. The handler does a shared set of checks, then runs one branch for each skill.

<!-- schema -->

**Limits:**
- Call cost: 1 for the event. Each `player` update that the skill causes adds 0.05 (`call_modifier` of `skill`, node/server.js:4899).
- MP: the skill costs `G.skills[name].mp * (100 - mp_reduction) / 100` (`consume_mp`, node/server_functions.js:3364-3383). With the `restore_mp` attribute, a roll can give you 2 times the MP instead. `burst` spends all your MP. `cburst` spends the MP of each pair. `energize` spends the MP that it gives. `absorb` on a target that fails `is_same` level 1 spends 6 times the cost.
- Cooldown: `G.skills[name].cooldown` times `cooldown_multiplier`, plus `penalty_cd` up to 10,000 ms. A skill with `share` uses and starts the cooldown of the shared skill (node/server_functions.js:3448-3467). On each request, the server sets `G.skills.attack.cooldown` to your `attack_ms` (node/server.js:9778).
- Range: the `range` of the skill (else your `range`), times `range_multiplier`, plus `range_bonus`, plus your level for `throw`. The server also accepts up to `xrange` more and subtracts the part that it used. A `fixed_range` skill gets no `xrange`. A `global` skill has no range.
- Targets: `ids` keeps 3 entries (`3shot`) or 5 (`5shot`, `fanofknives`); `targets` keeps 16 pairs.

**Notes:**
- `id` can be a number or a string. See [`EntityId`](#type-entityid).
- A failure of the shared checks costs no MP and starts no cooldown. The charges of a `slot` item go before the range and item checks, so a later failure does not give them back. Once the branch runs, most branches spend the MP and start the cooldown also when the effect fails. Only a `commence_attack` failure of a single-target skill keeps the cooldown free.
- Some keys of `G.skills` have no branch: `stop`, `use_hp`, `use_mp`, `use_town`, `stack`, `mtangle`, monster skills such as `fireball`, and `utility` keys such as `esc`. They pass the shared checks and get the default success. They have no effect, but a skill with a `cooldown` starts it: `use_hp` and `regen_hp` start the `use_hp` cooldown. HP and MP potions are the `use` event.
- `paladin_aura` reads `id || state`, so the server ignores `state` when the request has an `id`.
- **Server bug:** `magiport` on a PvP server (or with `mode.pve_safe_magiports` off) assigns and reads the undeclared variable `ported` (node/server.js:10819-10821). While no code assigned it, the read throws, and you get `game_error` `"ERROR!"`.
- **Server bug:** the `commence_attack` failure `target_gone` has no `place` (node/server.js:3162). It cannot happen for a character: `cavalry_attack_valid` is true for every attacker that is not cavalry (node/logic/cavalry.js:393-394).

What each branch does. The replies are in Responses and Also sent; "default success" is the **Success** reply.

| Skill `name` | Request fields | Effect |
|---|---|---|
| emotes: `boop`, `drop_egg`, `fart`, `headwiggle`, `hearts_single`, `highfive`, `ikissyou`, `joy`, `jump`, `makeawish`, `mirrordance`, `pocketstorm`, `spotlight`, `superjump`, `wiggle` | `id` for `boop`, `highfive`, `ikissyou`, `spotlight` | Spends the MP of the emote. Clients nearby get `emote`. During the anniversary, `ikissyou` on the featured character can claim a reward. |
| `arcane_needle`, `attack`, `burst`, `curse`, `heal`, `mentalburst`, `piercingshot`, `poisonarrow`, `purify`, `quickpunch`, `quickstab`, `shield_slam`, `smash`, `snowball`, `supershot`, `taunt`, `zapperzap` | `id` | `commence_attack`: a projectile to the target. `curse` adds party DPS credit on success. |
| `selfheal` | none | `commence_attack` with you as the target. |
| `invis` | none | Adds `invis` (if you are not invisible now). The cooldown (`reuse_cooldown`) starts when you become visible again (node/server.js:13756-13767). |
| `pickpocket` | `id`, `request_id` | Starts the `pickpocket` channel (`duration_min` to `duration_max`). At the end, it takes one item with `v` from a random slot of the target, if the target is within 20 px. |
| `fishing`, `mining` | `request_id` | Starts the channel if a zone of that type is next to you and you do not move. At the end, a 10% (`fishing`) or 20% (`mining`) roll gives a drop of the zone, and the tool can break (`breaks`). |
| `light` | none | Clients nearby get `light`. Rogues and invisible characters within 300 px lose `invis`. |
| `charge` | none | Adds `charging` for `duration`. |
| `dash` | `x`, `y` | Moves you at speed 500 to a safe spot near the point (within 50 px of you). Adds `dash` (1,000 ms). |
| `cleansing_light` | `id` | Removes each `cleansable` condition from the target. |
| `guardians_oath` | `id` | Adds `guardians_oath` to the target. Part of the damage to the target then goes to you. |
| `beacon_of_resolve` | none | Adds the condition to each living character within `range` that passes `is_same` level 3, you included. |
| `paladin_aura` | `id` or `state` | Selects the aura state. |
| `hardshell`, `power`, `xpower`, `shelter` | none | Adds the condition of the skill to you. |
| `mshield`, `aether_shield` | none | Turns the condition on or off. Each one removes the other. |
| `mcourage`, `mfrenzy`, `massproduction`, `massproductionpp`, `massexchange`, `massexchangepp` | none | Adds the condition of the skill to you. |
| `throw` | `id`, `num` | Removes one unit of the item. `essenceoffire` adds `eburn`, `essenceoflife` adds `eheal`. Another item does `random * attack * 15` or `random * armor * 24` damage; the target keeps at least 1 HP. |
| `phaseout` | none | Adds `phasedout` to you. |
| `pcoat` | none | Adds `poisonous` to you. |
| `entangle`, `tangle` | `id` | Adds `tangled` to the target and stops it. |
| `4fingers` | `id` | Adds `fingered` and `stunned` (`duration` minus 2,000 ms) to the target. |
| `revive` | `id` | If the target is dead with full HP, it gets a `revival` channel of 8,000 ms. Then it is alive. |
| `cburst` | `targets` | One projectile for each pair, with damage from its MP. It skips duplicates, MP of 0, invisible or invincible targets, you, and targets out of range. |
| `partyheal` | none | A heal to each party member (to you without a party). The server does not check their distance. |
| `darkblessing`, `warcry` | none | Adds the condition to each character within `range`. On a PvP map, only to characters that pass `is_same` level 1. |
| `3shot`, `5shot`, `fanofknives` | `ids` | One projectile for each kept id. It skips duplicates, missing, dead, invisible or invincible targets, you, and targets out of range. |
| `track` | none | You get `track`. |
| `agitate` | none | Monsters within `range` that have no target, or that target a character that passes `is_same` level 1, start to attack you. |
| `absorb` | `id` | Monsters that attack the target attack you instead. On a target that fails `is_same` level 1, it needs level 75 and 6 times the MP, and works only 5% of the time. |
| `stomp` | none | Adds `stunned` to monsters within `range`, and in PvP to characters that fail `is_same` level 1. |
| `scare` | none | Monsters that attack you stop. |
| `huntersmark` | `id` | Adds `marked` to the target. |
| `charm` | `id` | Adds `charmed` to the monster with a chance of `player.a.charm.attr0` percent. |
| `cleave`, `shadowstrike` | none | One projectile for each monster within `range`, and in PvP each character that fails `is_same` level 1. |
| `magiport` | `id` | Offer path (not PvP, `mode.pve_safe_magiports` on): the target gets `magiport` and accepts it with the `magiport` event. Other path: the server pulls the target to you. |
| `blink` | `x`, `y`, `direction` | Teleports you to a safe spot near the point on your map, after 200 ms. A GM pays no MP. |
| `warp` | `x`, `y`, `in`, `direction` | As `blink`, but to the instance `in`. |
| `mluck` | `id` | Adds `mluck` to the target, unless it has a `strong` `mluck` from another merchant. The buff is `strong` when the target is on your account. |
| `rspeed`, `reflection` | `id` | Adds the condition to the target. |
| `energize` | `id`, `mp` | Moves MP from you to the target, and adds `energized`. |
| `alchemy` | none | Removes one unit of the first item without `l`, and gives you its value times the rate in gold. |
| `temporalsurge` | none | Each respawn timer within 160 px gets `time * 0.85 - 1000`. |

**Example:**

```js
// sock: a connected AlSocket
// Three ranger skills. The reply has place = the skill name, not "skill".
for (const payload of [
  { name: "supershot", id: "52381" }, // one target: the reply is the action object
  { name: "3shot", ids: ["52381", "52382", "52383"] }, // the reply adds pids and targets
  { name: "huntersmark", id: "52381" }, // the default success reply
]) {
  const reply = sock.waitFor("game_response", (d) => d?.place === payload.name);
  sock.emit("skill", payload);
  const r = await reply;
  if (r.failed) console.log(`${payload.name} failed: ${r.response}`, r.ms ?? r.reason ?? "");
  else console.log(`${payload.name} ok`, r.pid ?? "");
}
```

```ts
interface SkillRequest { name: string; id?: string; ids?: string[]; [field: string]: unknown }
interface SkillReply {
  response: string; place?: string; failed?: boolean;
  ms?: number; reason?: string; // failures: cooldown time left, or a commence_attack reason
  pid?: string; pids?: string[]; // attack-type successes
}
const skills: SkillRequest[] = [
  { name: "supershot", id: "52381" }, // one target: the reply is the action object
  { name: "3shot", ids: ["52381", "52382", "52383"] }, // the reply adds pids and targets
  { name: "huntersmark", id: "52381" }, // the default success reply
];
for (const payload of skills) {
  const reply = sock.waitFor<SkillReply>("game_response", (d) => d?.place === payload.name);
  sock.emit("skill", payload);
  const r = await reply;
  if (r.failed) console.log(`${payload.name} failed: ${r.response}`, r.ms ?? r.reason ?? "");
  else console.log(`${payload.name} ok`, r.pid ?? "");
}
```

```python
# sock: a connected AlSocket; this runs in an async function
# Three ranger skills. The reply has place = the skill name, not "skill".
skills: list[dict[str, Any]] = [
    {"name": "supershot", "id": "52381"},  # one target: the reply is the action object
    {"name": "3shot", "ids": ["52381", "52382", "52383"]},  # the reply adds pids and targets
    {"name": "huntersmark", "id": "52381"},  # the default success reply
]
for payload in skills:
    name = payload["name"]
    reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == name)
    await sock.emit("skill", payload)
    r = await reply
    if r.get("failed"):
        print(name, "failed:", r["response"], r.get("ms") or r.get("reason") or "")
    else:
        print(name, "ok", r.get("pid", ""))
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
// Three ranger skills. The reply has place = the skill name, not "skill".
type reply struct {
	Response string  `json:"response"`
	Place    string  `json:"place"`
	Failed   bool    `json:"failed"`
	MS       float64 `json:"ms"`     // cooldown: time left
	Reason   string  `json:"reason"` // commence_attack failures
	PID      string  `json:"pid"`    // attack-type successes
}
for _, payload := range []map[string]any{
	{"name": "supershot", "id": "52381"},
	{"name": "3shot", "ids": []string{"52381", "52382", "52383"}},
	{"name": "huntersmark", "id": "52381"},
} {
	name := payload["name"].(string)
	wait := sock.Expect("game_response", func(d json.RawMessage) bool {
		var r reply
		return json.Unmarshal(d, &r) == nil && r.Place == name
	})
	sock.Emit("skill", payload)
	d, err := wait(ctx)
	var r reply
	if err != nil || json.Unmarshal(d, &r) != nil {
		fmt.Println(name, "no reply:", err)
	} else if r.Failed {
		fmt.Println(name, "failed:", r.Response, r.MS, r.Reason)
	} else {
		fmt.Println(name, "ok", r.PID)
	}
}
```

```csharp
// sock: a connected AlSocket
// Three ranger skills. The reply has place = the skill name, not "skill".
var skills = new Dictionary<string, object>[]
{
    new() { ["name"] = "supershot", ["id"] = "52381" },
    new() { ["name"] = "3shot", ["ids"] = new[] { "52381", "52382", "52383" } },
    new() { ["name"] = "huntersmark", ["id"] = "52381" },
};
foreach (var payload in skills)
{
    var name = (string)payload["name"];
    var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
        && d.TryGetProperty("place", out var p) && p.GetString() == name);
    await sock.EmitAsync("skill", payload);
    var r = await reply;
    Console.WriteLine(r.TryGetProperty("failed", out _) ? $"{name} failed: {r}" : $"{name} ok: {r}");
}
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// Three ranger skills. The reply has place = the skill name, not "skill".
for payload in [
    json!({"name": "supershot", "id": "52381"}),
    json!({"name": "3shot", "ids": ["52381", "52382", "52383"]}),
    json!({"name": "huntersmark", "id": "52381"}),
] {
    let name = payload["name"].as_str().unwrap_or_default().to_string();
    let place = name.clone(); // the predicate owns its copy ('static)
    let reply = sock.wait_for("game_response", move |d: &Value| d["place"] == place.as_str());
    sock.emit("skill", payload).await?;
    let r = reply.await?;
    if r["failed"] == true {
        println!("{name} failed: {} {} {}", r["response"], r["ms"], r["reason"]);
    } else {
        println!("{name} ok {}", r["pid"]);
    }
}
```

```java
// sock: a connected AlSocket
// Three ranger skills. The reply has place = the skill name, not "skill".
List<Map<String, Object>> skills = List.of(
        Map.of("name", "supershot", "id", "52381"),
        Map.of("name", "3shot", "ids", List.of("52381", "52382", "52383")),
        Map.of("name", "huntersmark", "id", "52381"));
for (var payload : skills) {
    String name = (String) payload.get("name");
    var reply = sock.waitFor("game_response", d -> name.equals(d.path("place").asText()), Duration.ofSeconds(5));
    sock.emit("skill", payload);
    JsonNode r = reply.get();
    if (r.path("failed").asBoolean()) System.out.println(name + " failed: " + r);
    else System.out.println(name + " ok: " + r.path("pid").asText());
}
```

**Source:** `node/server.js:9764-10997`. Cooldown: `consume_skill` at `node/server_functions.js:3448-3467`. Attacks: `commence_attack` at `node/server.js:3159-3612`. Channel ends: `node/server.js:14984-15114`.

### `click`
A deprecated event. The server only replies with a message.

<!-- schema -->

**Notes:** the handler does not check for a character.

**Example:**

```js
// sock: a connected AlSocket
const log = sock.waitFor("game_log");
sock.emit("click", {});
console.log((await log).message); // "'click' method is deprecated."
```

```ts
interface GameLog { message: string; phrase?: string; phrase_args?: unknown }
const log = sock.waitFor<GameLog>("game_log");
sock.emit("click", {});
console.log((await log).message); // "'click' method is deprecated."
```

```python
# sock: a connected AlSocket; this runs in an async function
log = sock.wait_for("game_log")
await sock.emit("click", {})
print((await log)["message"])  # "'click' method is deprecated."
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
wait := sock.Expect("game_log", nil)
sock.Emit("click", map[string]any{})
d, err := wait(ctx)
var log struct {
	Message string `json:"message"`
}
if err == nil && json.Unmarshal(d, &log) == nil {
	fmt.Println(log.Message) // "'click' method is deprecated."
}
```

```csharp
// sock: a connected AlSocket
var log = sock.WaitForAsync("game_log");
await sock.EmitAsync("click", new { });
Console.WriteLine((await log).GetProperty("message")); // "'click' method is deprecated."
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
let log = sock.wait_for("game_log", |_: &Value| true);
sock.emit("click", json!({})).await?;
println!("{}", log.await?["message"]); // "'click' method is deprecated."
```

```java
// sock: a connected AlSocket
var log = sock.waitFor("game_log");
sock.emit("click", Map.of());
System.out.println(log.get().path("message").asText()); // "'click' method is deprecated."
```

**Source:** `node/server.js:10999`

### `attack`
Attacks a monster or a character. It is a short form of `skill` with `name: "attack"`.

<!-- schema -->

**Limits:**
- Cooldown: `attack_ms` = `round(1000 / frequency)` ms (node/server.js:1627), plus `penalty_cd` up to 10,000 ms. A failure in `commence_attack` does not start the cooldown.
- MP: `mp_cost` for each attack.
- Range: `range` plus `xrange`. `xrange` is up to 25 px; it comes back at 5 px per second (node/server.js:16240).
- Call cost: 1 for the event. The handler calls the `skill` handler directly, so the socket wrapper runs one time with the event name `attack`. Each `player` update that the attack causes adds 1 or 2 more. With `skill` and `name: "attack"`, these updates cost 0.05 each (node/server.js:4899).

**Notes:**
- `id` can be a number or a string. See [`EntityId`](#type-entityid).
- The attack sets your `target` before most `commence_attack` checks. A failed attack can still change your target.
- **Server bug:** the reject of a cavalry check has no `place` (node/server.js:3162). It cannot happen for a character, because `cavalry_attack_valid` is always true for a non-cavalry attacker (node/logic/cavalry.js:393-394).
- A success reply has no `success: true`. Tell success from failure by `failed`.
- An attack ends your invisibility (`step_out_of_invis`). The server then sends `skill_timeout` for `invis` and a `player` before `action`.

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "attack");
sock.emit("attack", { id: "52381" });
const r = await reply;
// a target that is gone sends `disappear` (reason "not_there"), not game_response
if (r.failed) console.log("attack failed:", r.response, r.reason);
else console.log("projectile lands in ms:", r.eta);
```

```ts
interface AttackRequest { id: string }
interface GameResponse { response: string; place?: string; failed?: boolean; eta?: number; reason?: string }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "attack");
const req: AttackRequest = { id: "52381" };
sock.emit("attack", req);
const r = await reply;
// a target that is gone sends `disappear` (reason "not_there"), not game_response
if (r.failed) console.log("attack failed:", r.response, r.reason);
else console.log("projectile lands in ms:", r.eta);
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "attack")
await sock.emit("attack", {"id": "52381"})
r = await reply
# a target that is gone sends `disappear` (reason "not_there"), not game_response
if r.get("failed"):
    print("attack failed:", r["response"], r.get("reason"))
else:
    print("projectile lands in ms:", r["eta"])
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string  `json:"response"`
	Place    string  `json:"place"`
	Failed   bool    `json:"failed"`
	Eta      float64 `json:"eta"`
	Reason   string  `json:"reason"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "attack"
})
sock.Emit("attack", map[string]any{"id": "52381"})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed { // a target that is gone sends `disappear` (reason "not_there"), not game_response
	fmt.Println("attack failed:", r.Response, r.Reason)
} else {
	fmt.Println("projectile lands in ms:", r.Eta)
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "attack");
await sock.EmitAsync("attack", new { id = "52381" });
var r = await reply;
// a target that is gone sends `disappear` (reason "not_there"), not game_response
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"attack failed: {r.GetProperty("response")} {(r.TryGetProperty("reason", out var reason) ? reason : default)}");
else
    Console.WriteLine($"projectile lands in ms: {r.GetProperty("eta")}");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "attack");
sock.emit("attack", json!({"id": "52381"})).await?;
let r = reply.await?;
// a target that is gone sends `disappear` (reason "not_there"), not game_response
if r["failed"] == true {
    println!("attack failed: {} {}", r["response"], r["reason"]);
} else {
    println!("projectile lands in ms: {}", r["eta"]);
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "attack".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("attack", Map.of("id", "52381"));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
// a target that is gone sends `disappear` (reason "not_there"), not game_response
if (r.path("failed").asBoolean())
    System.out.println("attack failed: " + r.path("response").asText() + " " + r.path("reason").asText());
else
    System.out.println("projectile lands in ms:" + " " + r.path("eta").asText());
```

**Source:** `node/server.js:11003-11005`. The `skill` envelope: `node/server.js:9764-10031`, `node/server.js:10984-10997`. Attack logic: `commence_attack` at `node/server.js:3159-3612`.

### `heal`
Heals a target. It is a short form of `skill` with `name: "heal"`.

<!-- schema -->

**Limits:**
- Cooldown: `heal` shares the attack cooldown (`share: "attack"`): `attack_ms` = `round(1000 / frequency)` ms (node/server.js:1627), plus `penalty_cd` up to 10,000 ms. A heal starts the cooldown of `attack`, and an attack starts the cooldown of `heal`. A failure in `commence_attack` does not start the cooldown.
- MP: `mp_cost` for each heal. The server does not check your MP first (see Notes).
- Range: `range` plus `xrange`, as for `attack`.
- Class: priest only (a character with `role: "gm"` can use it with any class).
- Call cost: 1 for the event. The handler calls the `skill` handler directly, so the socket wrapper runs one time with the event name `heal`. Each `player` update that the heal causes adds 1 or 2 more.

**Notes:**
- The heal amount in the action is your `heal` stat, or your `attack` when `heal` is 0 (node/server.js:3298-3300). For a priest, `heal` is `attack` before the `output` multiplier (node/server.js:1656-1659). The `hit` applies `B.heal_multiplier` and the defenses of the target (node/server.js:3985-3999).
- A heal can target you (use your own name), another character, or a monster. Silence and the `konami` skin stop `heal` (they do not stop `attack`).
- A heal ignores the PvP, party, guild and `safe` map checks of `attack`. Only `duelland` stops a heal between characters that are not both in the duel.
- The server does not check MP for `heal`: `commence_attack` checks MP only for `attack` and some other skills (node/server.js:3337-3340). With less MP than `mp_cost`, the heal still goes, and your MP goes to 0 (node/server_functions.js:3364-3382).
- A success reply has no `success: true`. Tell success from failure by `failed`.
- The heal sets your `target` before most `commence_attack` checks. A failed heal can still change your target.

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "heal");
sock.emit("heal", { id: "FriendlyWarrior" });
const r = await reply;
if (r.failed) console.log("heal failed:", r.response, r.reason);
else console.log("heal amount:", r.heal);
```

```ts
interface HealRequest { id: string }
interface GameResponse { response: string; place?: string; failed?: boolean; heal?: number; reason?: string }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "heal");
const req: HealRequest = { id: "FriendlyWarrior" };
sock.emit("heal", req);
const r = await reply;
if (r.failed) console.log("heal failed:", r.response, r.reason);
else console.log("heal amount:", r.heal);
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "heal")
await sock.emit("heal", {"id": "FriendlyWarrior"})
r = await reply
if r.get("failed"):
    print("heal failed:", r["response"], r.get("reason"))
else:
    print("heal amount:", r["heal"])
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string  `json:"response"`
	Place    string  `json:"place"`
	Failed   bool    `json:"failed"`
	Heal     float64 `json:"heal"`
	Reason   string  `json:"reason"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "heal"
})
sock.Emit("heal", map[string]any{"id": "FriendlyWarrior"})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed {
	fmt.Println("heal failed:", r.Response, r.Reason)
} else {
	fmt.Println("heal amount:", r.Heal)
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "heal");
await sock.EmitAsync("heal", new { id = "FriendlyWarrior" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"heal failed: {r.GetProperty("response")} {(r.TryGetProperty("reason", out var reason) ? reason : default)}");
else
    Console.WriteLine($"heal amount: {r.GetProperty("heal")}");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "heal");
sock.emit("heal", json!({"id": "FriendlyWarrior"})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("heal failed: {} {}", r["response"], r["reason"]);
} else {
    println!("heal amount: {}", r["heal"]);
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "heal".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("heal", Map.of("id", "FriendlyWarrior"));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
if (r.path("failed").asBoolean())
    System.out.println("heal failed: " + r.path("response").asText() + " " + r.path("reason").asText());
else
    System.out.println("heal amount:" + " " + r.path("heal").asText());
```

**Source:** `node/server.js:11006-11008`. The `skill` envelope: `node/server.js:9764-10031`, `node/server.js:10984-10997`. Heal logic: `commence_attack` at `node/server.js:3159-3612`.

### `interaction`
Interacts with objects and NPCs on the map: the new-year tree, the orbs, the lever, Rook, the Cave of Many Dreams and the cavalry.

<!-- schema -->

**Limits:** `citizen_route`: 1 request per 10 s. `merrit_info`: the server ignores a second request within 3 s.

**Notes:**
- The lever also takes the bare string as the payload: `socket.emit("interaction", "the_lever")`.
- In a paused instance, the server refuses `interaction` like most events. Only `type: "cave"` with `action` `vote`, `state`, `info`, `talk` or `exit` still works (node/logic/instance_pause.js:101-106).
- The konami sequence: send `move` with `key` `"u"`, `"u"`, `"d"`, `"d"`, `"l"`, `"r"`, `"l"`, `"r"`, then `interaction` `{key: "B"}`, then `{key: "A"}`.
- If the run is paused, `cave` `talk` sends the state of the vote, not a chat.

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "interaction");
sock.emit("interaction", { type: "newyear_tree", request_id: "tree-1" });
const r = await reply;
// request_id: replies are objects, not bare strings
if (r.failed) console.log("interaction failed:", r.response);
else console.log("got a funtoken:", r.received_token);
```

```ts
interface InteractionRequest { type: string; request_id?: string }
interface GameResponse { response: string; place?: string; failed?: boolean; received_token?: boolean }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "interaction");
const req: InteractionRequest = { type: "newyear_tree", request_id: "tree-1" };
sock.emit("interaction", req);
const r = await reply;
// request_id: replies are objects, not bare strings
if (r.failed) console.log("interaction failed:", r.response);
else console.log("got a funtoken:", r.received_token);
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "interaction")
await sock.emit("interaction", {"type": "newyear_tree", "request_id": "tree-1"})
r = await reply
# request_id: replies are objects, not bare strings
if r.get("failed"):
    print("interaction failed:", r["response"])
else:
    print("got a funtoken:", r["received_token"])
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response      string `json:"response"`
	Place         string `json:"place"`
	Failed        bool   `json:"failed"`
	ReceivedToken bool   `json:"received_token"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "interaction"
})
sock.Emit("interaction", map[string]any{"type": "newyear_tree", "request_id": "tree-1"})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed { // request_id: replies are objects, not bare strings
	fmt.Println("interaction failed:", r.Response)
} else {
	fmt.Println("got a funtoken:", r.ReceivedToken)
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "interaction");
await sock.EmitAsync("interaction", new { type = "newyear_tree", request_id = "tree-1" });
var r = await reply;
// request_id: replies are objects, not bare strings
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"interaction failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"got a funtoken: {r.GetProperty("received_token")}");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "interaction");
sock.emit("interaction", json!({"type": "newyear_tree", "request_id": "tree-1"})).await?;
let r = reply.await?;
// request_id: replies are objects, not bare strings
if r["failed"] == true {
    println!("interaction failed: {}", r["response"]);
} else {
    println!("got a funtoken: {}", r["received_token"]);
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "interaction".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("interaction", Map.of("type", "newyear_tree", "request_id", "tree-1"));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
// request_id: replies are objects, not bare strings
if (r.path("failed").asBoolean())
    System.out.println("interaction failed: " + r.path("response").asText());
else
    System.out.println("got a funtoken:" + " " + r.path("received_token").asText());
```

**Source:** `node/server.js:11009`. Cave: `cave_interaction` at `node/logic/cave_of_many_dreams.js:1888`. Cavalry: `cavalry_interaction` at `node/logic/cavalry.js:190`. Market patron: `market_patron_info` at `node/logic/market_patron_runtime.js:72`.

### `mreport`
A debug event: the server replies with the distance between your position on the server and a point that you send.

<!-- schema -->

**Notes:** `mreport` works in a paused instance (it is on the allow-list, node/logic/instance_pause.js:80).

**Example:**

```js
// sock: a connected AlSocket
// The reply is a game_log with a bare string, not a message object.
const log = sock.waitFor("game_log", (d) => typeof d === "string");
sock.emit("mreport", { x: 100, y: 200 });
console.log("distance:", Number(await log));
```

```ts
interface MreportRequest { x: number; y: number }
const log = sock.waitFor<unknown>("game_log", (d) => typeof d === "string"); // a bare string
const req: MreportRequest = { x: 100, y: 200 };
sock.emit("mreport", req);
console.log("distance:", Number(await log));
```

```python
# sock: a connected AlSocket; this runs in an async function
# The reply is a game_log with a bare string, not a message object.
log = sock.wait_for("game_log", lambda d: isinstance(d, str))
await sock.emit("mreport", {"x": 100, "y": 200})
print("distance:", float(await log))
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
// The reply is a game_log with a bare string, not a message object.
wait := sock.Expect("game_log", func(d json.RawMessage) bool {
	var s string
	return json.Unmarshal(d, &s) == nil
})
sock.Emit("mreport", map[string]any{"x": 100, "y": 200})
d, err := wait(ctx)
var dist string
if err == nil && json.Unmarshal(d, &dist) == nil {
	fmt.Println("distance:", dist)
}
```

```csharp
// sock: a connected AlSocket
// The reply is a game_log with a bare string, not a message object.
var log = sock.WaitForAsync("game_log", d => d.ValueKind == JsonValueKind.String);
await sock.EmitAsync("mreport", new { x = 100, y = 200 });
Console.WriteLine($"distance: {(await log).GetString()}");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// The reply is a game_log with a bare string, not a message object.
let log = sock.wait_for("game_log", |d: &Value| d.is_string());
sock.emit("mreport", json!({"x": 100, "y": 200})).await?;
println!("distance: {}", log.await?);
```

```java
// sock: a connected AlSocket
// The reply is a game_log with a bare string, not a message object.
var log = sock.waitFor("game_log", JsonNode::isTextual, Duration.ofSeconds(5));
sock.emit("mreport", Map.of("x", 100, "y", 200));
System.out.println("distance: " + log.get().asText());
```

**Source:** `node/server.js:11171`

### `move`
Starts to move your character to a destination. The server calculates the movement.

<!-- schema -->

**Limits:** call cost 2.5: 1 for the event plus 1.5 from `CC` (node/server.js:242-255).

**Notes:**
- A move never sets your position from the client. The server moves you from its own `x`, `y` toward `going_x`, `going_y`, and other clients see the movement in `entities`.
- A move resets the market patron session of a merchant (`market_patron_reset`).
- In a paused instance, the refusal of `move` also sends `correction` with your position (node/logic/instance_pause.js:107).
- **Server bug:** with no character, a move with `key` throws, and you get `game_error` `"ERROR!"`. `pet` makes the handler use `player.monster`, which nothing sets, so `pet` with `key` throws too.

**Example:**

```js
// sock: a connected AlSocket
const x = 0, y = 0; // your position now
const m = 0; // `m` from your last `player` or `start`
// No reply. If your x, y is more than 132 px off, the server sends `correction`.
sock.on("correction", (d) => console.log(`server position: ${d.x}, ${d.y}`));
sock.emit("move", { x, y, going_x: 150, going_y: 20, m });
```

```ts
interface MoveRequest { x: number; y: number; going_x: number; going_y: number; m: number; pet?: boolean; key?: string }
interface Correction { x: number; y: number }
const x = 0, y = 0; // your position now
const m = 0; // `m` from your last `player` or `start`
sock.on<Correction>("correction", (d) => console.log(`server position: ${d.x}, ${d.y}`));
const req: MoveRequest = { x, y, going_x: 150, going_y: 20, m };
sock.emit("move", req);
```

```python
# sock: a connected AlSocket
x, y = 0, 0  # your position now
m = 0  # `m` from your last `player` or `start`
# No reply. If your x, y is more than 132 px off, the server sends `correction`.
sock.on("correction", lambda d: print(f"server position: {d['x']}, {d['y']}"))
await sock.emit("move", {"x": x, "y": y, "going_x": 150, "going_y": 20, "m": m})
```

```go
// sock: a connected *alsocket.Socket
x, y := 0.0, 0.0 // your position now
m := 0           // `m` from your last `player` or `start`
// No reply. If your x, y is more than 132 px off, the server sends `correction`.
sock.On("correction", func(d json.RawMessage) {
	var c struct{ X, Y float64 }
	json.Unmarshal(d, &c)
	fmt.Printf("server position: %v, %v\n", c.X, c.Y)
})
sock.Emit("move", map[string]any{"x": x, "y": y, "going_x": 150, "going_y": 20, "m": m})
```

```csharp
// sock: a connected AlSocket
double x = 0, y = 0; // your position now
int m = 0; // `m` from your last `player` or `start`
// No reply. If your x, y is more than 132 px off, the server sends `correction`.
sock.On("correction", d => Console.WriteLine($"server position: {d.GetProperty("x")}, {d.GetProperty("y")}"));
await sock.EmitAsync("move", new { x, y, going_x = 150, going_y = 20, m });
```

```rust
// sock: a connected AlSocket
let (x, y) = (0.0, 0.0); // your position now
let m = 0; // `m` from your last `player` or `start`
// No reply. If your x, y is more than 132 px off, the server sends `correction`.
sock.on("correction", |d: &Value| println!("server position: {}, {}", d["x"], d["y"]));
sock.emit("move", json!({"x": x, "y": y, "going_x": 150, "going_y": 20, "m": m})).await?;
```

```java
// sock: a connected AlSocket
double x = 0, y = 0; // your position now
int m = 0; // `m` from your last `player` or `start`
// No reply. If your x, y is more than 132 px off, the server sends `correction`.
sock.on("correction", d -> System.out.println("server position: " + d.path("x") + ", " + d.path("y")));
sock.emit("move", Map.of("x", x, "y", y, "going_x", 150, "going_y", 20, "m", m));
```

**Source:** `node/server.js:11183`

### `open_chest`
Takes the loot from a chest that a monster dropped. Without a party, you get all of it. In a party, the server gives each item to one member at random, weighted by `share`, and divides the gold by `share`.

<!-- schema -->

**Limits:** distance and age lower the gold, but they are not failures. If you are more than 400 px from the chest, `goldm` is 1 and `dry` is `true`. If the chest is older than 8 minutes, `goldm` is 1 and `stale` is `true`. An encouragement chest always has `goldm: 1`.

**Notes:**
- In a party, each item goes to a member that has space for it. If no member has space, the item goes to the lost and found. Shells in the chest (`cash`) go to you (`add_shells`).
- **Server bug:** without a party, the space check ignores the PvP items: `all_items.concat(chest.pvp_items)` does not change `all_items` (node/server.js:11313). A PvP item that does not fit goes to the lost and found.
- A cave chest goes through `cave_open_chest`, and its failures use the same `place: "open_chest"`.

**Example:**

```js
// sock: a connected AlSocket
// Success is `chest_opened`. A failure is game_response with place "open_chest".
const opened = sock.waitFor("chest_opened", (d) => d.id === "c1234");
const failed = sock.waitFor("game_response", (d) => d?.place === "open_chest");
sock.emit("open_chest", { id: "c1234" });
const r = await Promise.race([opened, failed]);
if (r.failed) console.log("open_chest failed:", r.response);
else if (r.gone) console.log("the chest is gone");
else console.log(`${r.gold} gold, ${r.items?.length ?? 0} items`);
```

```ts
interface OpenChestRequest { id: string }
// One type for both replies: chest_opened, or game_response (response, place, failed).
interface ChestReply {
  id?: string; gold?: number; goldm?: number; items?: { name: string }[]; gone?: boolean; dry?: boolean; stale?: boolean;
  response?: string; place?: string; failed?: boolean;
}
const opened = sock.waitFor<ChestReply>("chest_opened", (d) => d.id === "c1234");
const failed = sock.waitFor<ChestReply>("game_response", (d) => d?.place === "open_chest");
const req: OpenChestRequest = { id: "c1234" };
sock.emit("open_chest", req);
const r = await Promise.race([opened, failed]);
if (r.failed) console.log("open_chest failed:", r.response);
else if (r.gone) console.log("the chest is gone");
else console.log(`${r.gold} gold, ${r.items?.length ?? 0} items`);
```

```python
# sock: a connected AlSocket; this runs in an async function
# Success is `chest_opened`. A failure is game_response with place "open_chest".
opened = asyncio.create_task(sock.wait_for("chest_opened", lambda d: d.get("id") == "c1234"))
failed = asyncio.create_task(sock.wait_for(
    "game_response", lambda d: isinstance(d, dict) and d.get("place") == "open_chest"))
await sock.emit("open_chest", {"id": "c1234"})
done, pending = await asyncio.wait({opened, failed}, return_when=asyncio.FIRST_COMPLETED)
for task in pending:
    task.cancel()
r = done.pop().result()
if r.get("failed"):
    print("open_chest failed:", r["response"])
elif r.get("gone"):
    print("the chest is gone")
else:
    print(r.get("gold"), "gold,", len(r.get("items", [])), "items")
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
// Success is `chest_opened`. A failure is game_response with place "open_chest".
field := func(key, value string) func(json.RawMessage) bool {
	return func(d json.RawMessage) bool {
		var m map[string]any
		return json.Unmarshal(d, &m) == nil && m[key] == value
	}
}
opened := sock.Expect("chest_opened", field("id", "c1234"))
failed := sock.Expect("game_response", field("place", "open_chest"))
sock.Emit("open_chest", map[string]any{"id": "c1234"})
ctx, cancel := context.WithCancel(ctx)
defer cancel() // stops the wait that loses
got := make(chan json.RawMessage, 2)
for _, wait := range []func(context.Context) (json.RawMessage, error){opened, failed} {
	go func() {
		if d, err := wait(ctx); err == nil {
			got <- d
		}
	}()
}
var d json.RawMessage
select {
case d = <-got:
case <-ctx.Done():
	fmt.Println("no reply")
	return
}
var r struct {
	Response string            `json:"response"`
	Failed   bool              `json:"failed"`
	Gone     bool              `json:"gone"`
	Gold     float64           `json:"gold"`
	Items    []json.RawMessage `json:"items"`
}
json.Unmarshal(d, &r)
if r.Failed {
	fmt.Println("open_chest failed:", r.Response)
} else if r.Gone {
	fmt.Println("the chest is gone")
} else {
	fmt.Println(r.Gold, "gold,", len(r.Items), "items")
}
```

```csharp
// sock: a connected AlSocket
// Success is `chest_opened`. A failure is game_response with place "open_chest".
var opened = sock.WaitForAsync("chest_opened", d => d.GetProperty("id").GetString() == "c1234");
var failed = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "open_chest");
await sock.EmitAsync("open_chest", new { id = "c1234" });
var r = await await Task.WhenAny(opened, failed);
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"open_chest failed: {r.GetProperty("response")}");
else if (r.TryGetProperty("gone", out _))
    Console.WriteLine("the chest is gone");
else
    Console.WriteLine($"{r.GetProperty("gold")} gold, {r.GetProperty("items").GetArrayLength()} items");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// Success is `chest_opened`. A failure is game_response with place "open_chest".
let opened = sock.wait_for("chest_opened", |d: &Value| d["id"] == "c1234");
let failed = sock.wait_for("game_response", |d: &Value| d["place"] == "open_chest");
sock.emit("open_chest", json!({"id": "c1234"})).await?;
let r = tokio::select! { r = opened => r?, r = failed => r? };
if r["failed"] == true {
    println!("open_chest failed: {}", r["response"]);
} else if r["gone"] == true {
    println!("the chest is gone");
} else {
    println!("{} gold, {} items", r["gold"], r["items"].as_array().map_or(0, |a| a.len()));
}
```

```java
// sock: a connected AlSocket
// Success is `chest_opened`. A failure is game_response with place "open_chest".
var opened = sock.waitFor("chest_opened", d -> "c1234".equals(d.path("id").asText()), Duration.ofSeconds(5));
var failed = sock.waitFor("game_response", d -> "open_chest".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("open_chest", Map.of("id", "c1234"));
JsonNode r = (JsonNode) CompletableFuture.anyOf(opened, failed).get();
if (r.path("failed").asBoolean()) System.out.println("open_chest failed: " + r.path("response").asText());
else if (r.path("gone").asBoolean()) System.out.println("the chest is gone");
else System.out.println(r.path("gold") + " gold, " + r.path("items").size() + " items");
```

**Source:** `node/server.js:11273`

### `auth`
Logs a character into this game server. The socket must be an observer: send `auth` after `loaded`.

<!-- schema -->

**Limits:** a login has 60 s to complete. Call cost: 2 more than a normal event (the `CC` table, node/server.js:242-255).

**Notes:**
- The saved map can refuse entry, or be a mount (the bank) or a generated map. Then the server puts the character at the `on_exit` spawn of that map.
- On a test server, the server adds a random number to the name.
- The server compares `bot` with `==`. If the server has no `BOT_MASTER` key, a missing `bot` also matches. Whether the live servers set the key is unclear from the source.

**Example:**

```js
// sock: a connected AlSocket that already sent `loaded`
// user, auth: from AL_AUTH (<userID>-<authToken>); character: the character id
const [user, auth] = process.env.AL_AUTH.split("-");
const character = "CH_123"; // `id` from servers_and_characters (example)
// Success is `start`. Most failures are game_error (some are game_log, or nothing).
const first = Promise.race([
  sock.waitFor("start", undefined, 60000).then((d) => ["start", d]),
  sock.waitFor("game_error", undefined, 60000).then((d) => ["game_error", d]),
]);
sock.emit("auth", { user, auth, character });
const [event, data] = await first;
if (event === "start") console.log(`in the game as ${data.name} on ${data.map}`);
else console.log("auth failed:", data.message ?? data); // "ERROR!" is a bare string
```

```ts
interface AuthRequest { user: string; auth: string; character: string; code_slot?: number | string; no_html?: string; epl?: string }
interface Start { name: string; map: string; x: number; y: number; [field: string]: unknown }
interface GameError { message: string; phrase?: string; reason?: string }
const first = Promise.race([
  sock.waitFor<Start>("start", undefined, 60000).then((data) => ({ ok: true as const, data })),
  sock.waitFor<GameError | string>("game_error", undefined, 60000).then((data) => ({ ok: false as const, data })),
]);
const [user, auth] = process.env.AL_AUTH!.split("-"); // AL_AUTH = <userID>-<authToken>
const req: AuthRequest = { user, auth, character: "CH_123" }; // character: `id` from servers_and_characters
sock.emit("auth", req);
const r = await first;
if (r.ok) console.log(`in the game as ${r.data.name} on ${r.data.map}`);
else console.log("auth failed:", typeof r.data === "string" ? r.data : r.data.message);
```

```python
# sock: a connected AlSocket that already sent `loaded`
# Success is `start`. Most failures are game_error (some are game_log, or nothing).
user, auth = os.environ["AL_AUTH"].split("-")  # AL_AUTH = <userID>-<authToken>
character = "CH_123"  # `id` from servers_and_characters (example)
started = asyncio.create_task(sock.wait_for("start", timeout=60))
error = asyncio.create_task(sock.wait_for("game_error", timeout=60))
await sock.emit("auth", {"user": user, "auth": auth, "character": character})
done, pending = await asyncio.wait({started, error}, return_when=asyncio.FIRST_COMPLETED)
for task in pending:
    task.cancel()
if started in done:
    me = started.result()
    print(f"in the game as {me['name']} on {me['map']}")
else:
    print("auth failed:", error.result())  # a message object, or "ERROR!"
```

```go
// sock: a connected *alsocket.Socket that already sent `loaded`; ctx: a context with a deadline
// Success is `start`. Most failures are game_error (some are game_log, or nothing).
user, auth, _ := strings.Cut(os.Getenv("AL_AUTH"), "-") // AL_AUTH = <userID>-<authToken>
character := "CH_123"                                    // `id` from servers_and_characters (example)
waits := map[string]func(context.Context) (json.RawMessage, error){
	"start":      sock.Expect("start", nil),
	"game_error": sock.Expect("game_error", nil),
}
sock.Emit("auth", map[string]any{"user": user, "auth": auth, "character": character})
ctx, cancel := context.WithCancel(ctx)
defer cancel() // stops the wait that loses
type result struct {
	event string
	data  json.RawMessage
}
got := make(chan result, 2)
for event, wait := range waits {
	go func() {
		if d, err := wait(ctx); err == nil {
			got <- result{event, d}
		}
	}()
}
var r result
select {
case r = <-got:
case <-ctx.Done():
	fmt.Println("no reply") // the login has 60 s
	return
}
if r.event == "start" {
	var me struct{ Name, Map string }
	json.Unmarshal(r.data, &me)
	fmt.Println("in the game as", me.Name, "on", me.Map)
} else {
	fmt.Println("auth failed:", string(r.data)) // a message object, or "ERROR!"
}
```

```csharp
// sock: a connected AlSocket that already sent `loaded`
// Success is `start`. Most failures are game_error (some are game_log, or nothing).
var al = Environment.GetEnvironmentVariable("AL_AUTH")!.Split('-'); // <userID>-<authToken>
var (user, auth, character) = (al[0], al[1], "CH_123"); // character: `id` from servers_and_characters
var started = sock.WaitForAsync("start", null, TimeSpan.FromSeconds(60));
var error = sock.WaitForAsync("game_error", null, TimeSpan.FromSeconds(60));
await sock.EmitAsync("auth", new { user, auth, character });
if (await Task.WhenAny(started, error) == started)
{
    var me = await started;
    Console.WriteLine($"in the game as {me.GetProperty("name")} on {me.GetProperty("map")}");
}
else
    Console.WriteLine($"auth failed: {await error}"); // a message object, or "ERROR!"
```

```rust
// sock: a connected AlSocket that already sent `loaded`; in an async fn that returns Result
// Success is `start`. Most failures are game_error (some are game_log, or nothing).
let al_auth = std::env::var("AL_AUTH")?; // <userID>-<authToken>
let (user, auth) = al_auth.split_once('-').ok_or("AL_AUTH has no '-'")?;
let character = "CH_123"; // `id` from servers_and_characters (example)
let started = sock.wait_for_timeout("start", |_: &Value| true, Duration::from_secs(60));
let error = sock.wait_for_timeout("game_error", |_: &Value| true, Duration::from_secs(60));
sock.emit("auth", json!({"user": user, "auth": auth, "character": character})).await?;
let (event, data) = tokio::select! { r = started => ("start", r?), r = error => ("game_error", r?) };
if event == "start" {
    println!("in the game as {} on {}", data["name"], data["map"]);
} else {
    println!("auth failed: {data}"); // a message object, or "ERROR!"
}
```

```java
// sock: a connected AlSocket that already sent `loaded`
// Success is `start`. Most failures are game_error (some are game_log, or nothing).
String[] al = System.getenv("AL_AUTH").split("-"); // <userID>-<authToken>
String user = al[0], auth = al[1], character = "CH_123"; // character: `id` from servers_and_characters
var started = sock.waitFor("start", d -> true, Duration.ofSeconds(60));
var error = sock.waitFor("game_error", d -> true, Duration.ofSeconds(60));
sock.emit("auth", Map.of("user", user, "auth", auth, "character", character));
CompletableFuture.anyOf(started, error).join();
if (started.isDone()) {
    JsonNode me = started.get();
    System.out.println("in the game as " + me.path("name").asText() + " on " + me.path("map").asText());
} else {
    System.out.println("auth failed: " + error.get()); // a message object, or "ERROR!"
}
```

**Source:** `node/server.js:11563-11985`. Steam (Tauri): `verify_tauri_steam_auth` at `node/server_functions.js:922`. Login state: `pending_logins`, `character_login_timeout`, `check_character_login` and `cancel_character_login` in `node/logic/character_sessions.js:2`. Limits: `is_player_allowed` at `node/server_functions.js:383`.

### `use`
Gives a small amount of HP or MP without a potion. It uses the potion cooldown.

<!-- schema -->

**Limits:** the potion cooldown is 4 s. `equip` of a potion uses the same cooldown.

**Notes:** an `item` other than `"hp"` or `"mp"` changes nothing and starts no cooldown, but the server still sends the success reply.

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "use");
sock.emit("use", { item: "hp" });
const r = await reply;
if (r.failed) console.log("use failed:", r.response, r.ms);
else console.log("used", r.used);
```

```ts
interface UseRequest { item: "hp" | "mp" }
interface GameResponse { response: string; place?: string; failed?: boolean; used?: string; ms?: number }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "use");
const req: UseRequest = { item: "hp" };
sock.emit("use", req);
const r = await reply;
if (r.failed) console.log("use failed:", r.response, r.ms);
else console.log("used", r.used);
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "use")
await sock.emit("use", {"item": "hp"})
r = await reply
if r.get("failed"):
    print("use failed:", r["response"], r.get("ms"))
else:
    print("used", r["used"])
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string  `json:"response"`
	Place    string  `json:"place"`
	Failed   bool    `json:"failed"`
	Used     string  `json:"used"`
	Ms       float64 `json:"ms"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "use"
})
sock.Emit("use", map[string]any{"item": "hp"})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed {
	fmt.Println("use failed:", r.Response, r.Ms)
} else {
	fmt.Println("used", r.Used)
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "use");
await sock.EmitAsync("use", new { item = "hp" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"use failed: {r.GetProperty("response")} {(r.TryGetProperty("ms", out var ms) ? ms : default)}");
else
    Console.WriteLine($"used {r.GetProperty("used")}");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "use");
sock.emit("use", json!({"item": "hp"})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("use failed: {} {}", r["response"], r["ms"]);
} else {
    println!("used {}", r["used"]);
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "use".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("use", Map.of("item", "hp"));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
if (r.path("failed").asBoolean())
    System.out.println("use failed: " + r.path("response").asText() + " " + r.path("ms").asText());
else
    System.out.println("used" + " " + r.path("used").asText());
```

**Source:** `node/server.js:11988-12026`

### `friend`
Sends, accepts or removes friend requests between accounts.

<!-- schema -->

**Limits:** 100 friends per account. Call cost: 24 more than a normal event (the `CC` table, node/server.js:242-255).

**Notes:**
- `friends` holds account ids, not character names.
- The server keeps open requests in memory, keyed by the two character names. They do not expire with time. A server restart removes them.
- `accept` without `request_id` gets no success reply. Wait for `friend` `{event: "new"}` instead.
- **Server bug:** the late `friend_failed` has no `failed: true` and no `place`, and one of its reasons is `"coms failure"`, with a space.

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "friend");
sock.emit("friend", { event: "request", name: "OtherPlayer" });
const r = await reply;
// success: "friend_rsent" or "friend_already"
if (r.failed) console.log("friend failed:", r.response);
else console.log("reply", r.response);
```

```ts
interface FriendRequest { event: "request" | "accept" | "unfriend"; name: string }
interface GameResponse { response: string; place?: string; failed?: boolean }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "friend");
const req: FriendRequest = { event: "request", name: "OtherPlayer" };
sock.emit("friend", req);
const r = await reply;
// success: "friend_rsent" or "friend_already"
if (r.failed) console.log("friend failed:", r.response);
else console.log("reply", r.response);
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "friend")
await sock.emit("friend", {"event": "request", "name": "OtherPlayer"})
r = await reply
# success: "friend_rsent" or "friend_already"
if r.get("failed"):
    print("friend failed:", r["response"])
else:
    print("reply", r["response"])
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "friend"
})
sock.Emit("friend", map[string]any{"event": "request", "name": "OtherPlayer"})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed { // success: "friend_rsent" or "friend_already"
	fmt.Println("friend failed:", r.Response)
} else {
	fmt.Println("reply", r.Response)
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "friend");
await sock.EmitAsync("friend", new { @event = "request", name = "OtherPlayer" });
var r = await reply;
// success: "friend_rsent" or "friend_already"
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"friend failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"reply {r.GetProperty("response")}");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "friend");
sock.emit("friend", json!({"event": "request", "name": "OtherPlayer"})).await?;
let r = reply.await?;
// success: "friend_rsent" or "friend_already"
if r["failed"] == true {
    println!("friend failed: {}", r["response"]);
} else {
    println!("reply {}", r["response"]);
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "friend".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("friend", Map.of("event", "request", "name", "OtherPlayer"));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
// success: "friend_rsent" or "friend_already"
if (r.path("failed").asBoolean())
    System.out.println("friend failed: " + r.path("response").asText());
else
    System.out.println("reply" + " " + r.path("response").asText());
```

**Source:** `node/server.js:12027-12190`. Account updates: `update_characters` at `adventure_functions.js:1498`, and the routes `/new_friend` and `/lost_friend` at `node/server.js:770-801`.

### `duel`
Challenges another character to a duel, accepts a challenge, or moves a party member into a duel that did not start.

<!-- schema -->

**Limits:**
- One open challenge for each challenger. A new `challenge` replaces the old one.
- The duel starts 60 s after `accept` (20 s on a dev server). Until then, the fighters have the `stunned` condition.
- `accept` is not possible on a PvP server, because every map there is a PvP area.

**Notes:**
- **Server bug:** the `duel_started` check of `enter` never fails. The event loop copies `instance.active` into `S.duels[id].active` (node/server_functions.js:3009), but the start sets `instance.info.active` (node/server_functions.js:2937). After the start, `enter` fails with `not_your_duel`, because the start replaces the team lists with the fighters in the instance (node/server_functions.js:2934-2953).
- **Server bug:** `accept` does not check the result of `transport_player_to`. A character in a dream cave cannot leave the cave this way (`generated_can_enter`, node/server.js:4647). The server still makes the duel, sets `team` and stuns the character (node/server.js:12248-12285).
- The `duel` event to the target spells its `event` as `"chellenge"`.

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "duel");
sock.emit("duel", { event: "challenge", name: "Rival", request_id: "duel-1" });
const r = await reply;
// with request_id, a failure is response "data" plus reason
if (r.failed) console.log("duel failed:", r.response, r.reason);
else console.log("challenge sent");
```

```ts
interface DuelRequest { event: "challenge" | "accept" | "enter"; name?: string; id?: string; request_id?: unknown }
interface GameResponse { response: string; place?: string; failed?: boolean; reason?: string }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "duel");
const req: DuelRequest = { event: "challenge", name: "Rival", request_id: "duel-1" };
sock.emit("duel", req);
const r = await reply;
// with request_id, a failure is response "data" plus reason
if (r.failed) console.log("duel failed:", r.response, r.reason);
else console.log("challenge sent");
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "duel")
await sock.emit("duel", {"event": "challenge", "name": "Rival", "request_id": "duel-1"})
r = await reply
# with request_id, a failure is response "data" plus reason
if r.get("failed"):
    print("duel failed:", r["response"], r.get("reason"))
else:
    print("challenge sent")
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`
	Reason   string `json:"reason"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "duel"
})
sock.Emit("duel", map[string]any{"event": "challenge", "name": "Rival", "request_id": "duel-1"})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed { // with request_id, a failure is response "data" plus reason
	fmt.Println("duel failed:", r.Response, r.Reason)
} else {
	fmt.Println("challenge sent")
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "duel");
await sock.EmitAsync("duel", new { @event = "challenge", name = "Rival", request_id = "duel-1" });
var r = await reply;
// with request_id, a failure is response "data" plus reason
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"duel failed: {r.GetProperty("response")} {(r.TryGetProperty("reason", out var reason) ? reason : default)}");
else
    Console.WriteLine("challenge sent");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "duel");
sock.emit("duel", json!({"event": "challenge", "name": "Rival", "request_id": "duel-1"})).await?;
let r = reply.await?;
// with request_id, a failure is response "data" plus reason
if r["failed"] == true {
    println!("duel failed: {} {}", r["response"], r["reason"]);
} else {
    println!("challenge sent");
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "duel".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("duel", Map.of("event", "challenge", "name", "Rival", "request_id", "duel-1"));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
// with request_id, a failure is response "data" plus reason
if (r.path("failed").asBoolean())
    System.out.println("duel failed: " + r.path("response").asText() + " " + r.path("reason").asText());
else
    System.out.println("challenge sent");
```

**Source:** `node/server.js:12191-12356`. Duel start and end: `node/server_functions.js:2899-3012`.

### `party`
Manages your party: invite, ask to join, accept an invite, accept a request, leave, and kick.

<!-- schema -->

**Limits:** A party has at most 10 members, and at most 9 members that are not merchants (`limits`, node/server.js:256-260).

**Notes:**
- The server does not check that you are the leader for `invite`. Any member can invite.
- `kick` removes only members that are after you in `list`. The leader is first, so the leader can remove every member.
- An invite or a request stays open until the target accepts it. The server has no timer for it (node/server.js:12380-12383, 12400-12403).
- `accept` and `raccept` remove the joining character from its old party first. A party of 2 ends when one member leaves.

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "party");
sock.emit("party", { event: "invite", name: "Friend" });
const r = await reply;
// success: "data", or "already_in_party"
if (r.failed) console.log("party failed:", r.response);
else console.log("reply", r.response);
```

```ts
interface PartyRequest { event: "invite" | "request" | "accept" | "raccept" | "leave" | "kick"; name?: string; id?: string }
interface GameResponse { response: string; place?: string; failed?: boolean }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "party");
const req: PartyRequest = { event: "invite", name: "Friend" };
sock.emit("party", req);
const r = await reply;
// success: "data", or "already_in_party"
if (r.failed) console.log("party failed:", r.response);
else console.log("reply", r.response);
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "party")
await sock.emit("party", {"event": "invite", "name": "Friend"})
r = await reply
# success: "data", or "already_in_party"
if r.get("failed"):
    print("party failed:", r["response"])
else:
    print("reply", r["response"])
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "party"
})
sock.Emit("party", map[string]any{"event": "invite", "name": "Friend"})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed { // success: "data", or "already_in_party"
	fmt.Println("party failed:", r.Response)
} else {
	fmt.Println("reply", r.Response)
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "party");
await sock.EmitAsync("party", new { @event = "invite", name = "Friend" });
var r = await reply;
// success: "data", or "already_in_party"
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"party failed: {r.GetProperty("response")}");
else
    Console.WriteLine($"reply {r.GetProperty("response")}");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "party");
sock.emit("party", json!({"event": "invite", "name": "Friend"})).await?;
let r = reply.await?;
// success: "data", or "already_in_party"
if r["failed"] == true {
    println!("party failed: {}", r["response"]);
} else {
    println!("reply {}", r["response"]);
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "party".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("party", Map.of("event", "invite", "name", "Friend"));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
// success: "data", or "already_in_party"
if (r.path("failed").asBoolean())
    System.out.println("party failed: " + r.path("response").asText());
else
    System.out.println("reply" + " " + r.path("response").asText());
```

**Source:** `node/server.js:12357-12547`. `leave_party`: `node/server_functions.js:3603-3667`. `party_to_client`: `node/server.js:1138-1213`.

### `magiport`
Accepts a magiport offer from a mage and teleports you to that mage. The offer comes from the `magiport` skill on a server that is not PvP (`mode.pve_safe_magiports`, node/server.js:10809).

<!-- schema -->

**Notes:**
- Each offer works one time. The server deletes it before the checks of the mount and the spot.
- The mage gets 2,000 `pdps` (party DPS credit) when `player.party == pulled.party`. **Server bug:** this is also true when neither of you is in a party (`null == null`, node/server_functions.js:4022-4024).

**Example:**

```js
// sock: a connected AlSocket
// Start the wait before the emit, so the reply cannot arrive first.
const reply = sock.waitFor("game_response", (d) => d?.place === "magiport");
sock.emit("magiport", { name: "SomeMage" });
const r = await reply;
if (r.failed) console.log("magiport failed:", r.response);
else console.log("teleporting");
```

```ts
interface MagiportRequest { name: string }
interface GameResponse { response: string; place?: string; failed?: boolean }
const reply = sock.waitFor<GameResponse>("game_response", (d) => d?.place === "magiport");
const req: MagiportRequest = { name: "SomeMage" };
sock.emit("magiport", req);
const r = await reply;
if (r.failed) console.log("magiport failed:", r.response);
else console.log("teleporting");
```

```python
# sock: a connected AlSocket; this runs in an async function
# wait_for registers the wait now; await it after the emit.
reply = sock.wait_for("game_response", lambda d: isinstance(d, dict) and d.get("place") == "magiport")
await sock.emit("magiport", {"name": "SomeMage"})
r = await reply
if r.get("failed"):
    print("magiport failed:", r["response"])
else:
    print("teleporting")
```

```go
// sock: a connected *alsocket.Socket; ctx: a context with a deadline
type reply struct {
	Response string `json:"response"`
	Place    string `json:"place"`
	Failed   bool   `json:"failed"`
}
// Expect registers the wait now; call wait(ctx) after the emit.
wait := sock.Expect("game_response", func(d json.RawMessage) bool {
	var r reply
	return json.Unmarshal(d, &r) == nil && r.Place == "magiport"
})
sock.Emit("magiport", map[string]any{"name": "SomeMage"})
d, err := wait(ctx)
var r reply
if err != nil || json.Unmarshal(d, &r) != nil {
	fmt.Println("no reply:", err)
} else if r.Failed {
	fmt.Println("magiport failed:", r.Response)
} else {
	fmt.Println("teleporting")
}
```

```csharp
// sock: a connected AlSocket
var reply = sock.WaitForAsync("game_response", d => d.ValueKind == JsonValueKind.Object
    && d.TryGetProperty("place", out var p) && p.GetString() == "magiport");
await sock.EmitAsync("magiport", new { name = "SomeMage" });
var r = await reply;
if (r.TryGetProperty("failed", out _))
    Console.WriteLine($"magiport failed: {r.GetProperty("response")}");
else
    Console.WriteLine("teleporting");
```

```rust
// sock: a connected AlSocket; this runs in an async fn that returns Result<_, Error>
// wait_for registers the wait now; .await it after the emit.
let reply = sock.wait_for("game_response", |d: &Value| d["place"] == "magiport");
sock.emit("magiport", json!({"name": "SomeMage"})).await?;
let r = reply.await?;
if r["failed"] == true {
    println!("magiport failed: {}", r["response"]);
} else {
    println!("teleporting");
}
```

```java
// sock: a connected AlSocket
var reply = sock.waitFor("game_response",
        d -> d.isObject() && "magiport".equals(d.path("place").asText()), Duration.ofSeconds(5));
sock.emit("magiport", Map.of("name", "SomeMage"));
JsonNode r = reply.get(); // throws ExecutionException after the timeout
if (r.path("failed").asBoolean())
    System.out.println("magiport failed: " + r.path("response").asText());
else
    System.out.println("teleporting");
```

**Source:** `node/server.js:12548-12566`. Teleport: `magiport_someone` at `node/server_functions.js:3999-4027`; the end of the condition at `node/server.js:14701-14721`.
