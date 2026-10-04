### `o:home`
Observer sockets only. Moves the camera of the observer back to the character that it follows.

<!-- schema -->

**Notes:**
- An observer follows a character only if the socket connected with the `secret` handshake query of that character (`node/server.js:4989`). A broadcast observer (`broadcast=1` query) follows no character.
- A socket with no `secret` query is a desktop socket. A socket with `secret` is a desktop socket only with the `desktop` query (`node/server.js:4988`).

**Example:**

```js
// sock: a connected AlSocket, opened as an observer of your character
const moved = sock.waitFor("new_map", undefined, 5000);
sock.emit("o:home");
const map = await moved;
console.log("camera on", map.name, map.x, map.y);
```

```ts
interface NewMap { name: string; in: string; x: number; y: number; m: number; entities: unknown }
// sock: an observer socket of your character
const moved = sock.waitFor<NewMap>("new_map", undefined, 5000);
sock.emit("o:home");
const map = await moved;
console.log("camera on", map.name, map.x, map.y);
```

```python
# sock: an observer socket of your character
moved = sock.wait_for("new_map", timeout=5)
await sock.emit("o:home")
m = await moved
print("camera on", m["name"], m["x"], m["y"])
```

```go
// sock: an observer socket of your character
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
wait := sock.Expect("new_map", nil) // registers now, before the emit
sock.Emit("o:home", nil)
reply, err := wait(ctx)
if err != nil {
	return // no reply in time
}
var m struct {
	Name string
	X, Y float64
}
if json.Unmarshal(reply, &m) == nil {
	fmt.Println("camera on", m.Name, m.X, m.Y)
}
```

```csharp
// sock: an observer socket of your character
var moved = sock.WaitForAsync("new_map", null, TimeSpan.FromSeconds(5));
await sock.EmitAsync("o:home");
var m = await moved;
Console.WriteLine($"camera on {m.GetProperty("name")} {m.GetProperty("x")} {m.GetProperty("y")}");
```

```rust
// sock: an observer socket of your character
let reply = sock.wait_for("new_map", |_| true);
sock.emit("o:home", Value::Null).await?;
let m = reply.await?;
println!("camera on {} {} {}", m["name"], m["x"], m["y"]);
```

```java
// sock: an observer socket of your character
var moved = sock.waitFor("new_map", d -> true, Duration.ofSeconds(5));
sock.emit("o:home", null);
JsonNode m = moved.get();
System.out.println("camera on " + m.path("name").asText() + " " + m.path("x") + " " + m.path("y"));
```

**Source:** `node/server.js:5055`, `node/server.js:4614` (`transport_observer_to`)

### `o:command`
Observer sockets only. Sends the payload to the client of the followed character as `code_eval`.

<!-- schema -->

**Notes:** A broadcast observer follows no character, so this event always fails for it (`node/test/observer_broadcast.test.js:102`).

**Example:**

```js
// sock: a connected AlSocket, opened as an observer of your character
// No reply to the observer. The character's socket gets `code_eval` with this payload.
sock.emit("o:command", { command: "1+1" });
```

```ts
interface ObserverCommand { command: string } // any payload: the server does not read it
// sock: an observer socket of your character
// No reply to the observer. The character's socket gets `code_eval` with this payload.
const payload: ObserverCommand = { command: "1+1" };
sock.emit("o:command", payload);
```

```python
# sock: an observer socket of your character
# No reply to the observer. The character's socket gets `code_eval` with this payload.
await sock.emit("o:command", {"command": "1+1"})
```

```go
// sock: an observer socket of your character
// No reply to the observer. The character's socket gets `code_eval` with this payload.
sock.Emit("o:command", map[string]any{"command": "1+1"})
```

```csharp
// sock: an observer socket of your character
// No reply to the observer. The character's socket gets `code_eval` with this payload.
await sock.EmitAsync("o:command", new { command = "1+1" });
```

```rust
// sock: an observer socket of your character
// No reply to the observer. The character's socket gets `code_eval` with this payload.
sock.emit("o:command", json!({"command": "1+1"})).await?;
```

```java
// sock: an observer socket of your character
// No reply to the observer. The character's socket gets `code_eval` with this payload.
sock.emit("o:command", Map.of("command", "1+1"));
```

**Source:** `node/server.js:5066`
