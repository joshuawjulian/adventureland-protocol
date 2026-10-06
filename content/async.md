## The async model of your language

The protocol is the same for every language, but each language runs concurrent work in a
different way. JavaScript and Python use one event loop on one thread. Go, C#, Rust and Java
use more than one thread. This section first tells what the protocol asks of your client. Then
it tells how each of the seven languages does it, and which mistakes are typical for it.

The boxes with the label **Your language** change with the language in the top bar. A click on
a tab in a box changes the language on all pages. The course library
[`AlSocket`](#learn-alsocket) is the model for each box. Its code applies each rule here, and
it compiles and runs in all seven languages.

This entry is the short version. The lecture after it is the long version. It builds a complete
mental model of async in your language, from the runtime up to `AlSocket`:

| Chapter | What you learn |
|---|---|
| [Async 1: Why a client needs concurrency](#guide-async-1-why-a-client-needs-concurrency) | The problem, for all languages: blocking I/O, threads and event loops. |
| [Async 2: The runtime](#guide-async-2-the-runtime) | What runs your code, on which threads, and in which order. |
| [Async 3: The unit of async work](#guide-async-3-the-unit-of-async-work) | The type for work that is not done yet, and how to make one by hand. |
| [Async 4: What `await` does](#guide-async-4-what-await-does) | The mechanics of a wait, step by step. |
| [Async 5: Several things at the same time](#guide-async-5-several-things-at-the-same-time) | Start work, then wait for all of it, for the first, or for each. |
| [Async 6: Cancellation, timeouts and errors](#guide-async-6-cancellation-timeouts-and-errors) | How to stop work, and where an error goes. |
| [Async 7: Shared state](#guide-async-7-shared-state) | When two parts of your code can see the same data, and how to keep it correct. |
| [Async 8: AlSocket, read with these eyes](#guide-async-8-alsocket-read-with-these-eyes) | The course socket, part by part, with each concept named. |
| [Async 9: Seeing it run](#guide-async-9-seeing-it-run) | Tools that show what your program does, and the typical mistakes. |

### What the protocol asks of your client

| Fact of the protocol | Source | What your client must do |
|---|---|---|
| The server sends an Engine.IO ping (`2`) every 4 s. If no pong (`3`) comes back in 12 s, it closes the socket. | node/server.js:83-84 | Send each pong from a part of your code that your own work cannot hold back. |
| Most events arrive without a request: `entities`, `player`, `hit`, `death`, chat. They arrive at any time. | | Keep one handler for each event that changes your state. Register it before you need it. |
| One socket is one ordered stream. The server runs the handlers of one socket in arrival order, on one Node.js thread. | node/server.js:4883-4975 | Give events to your handlers in arrival order, one at a time. |
| The server uses no Socket.IO acknowledgements. Its wrapper calls each handler with the payload only. | node/server.js:4885, 4945 | Treat each reply as a separate event. Find it by its name and its content. |
| Most replies have no request id. Some handlers echo `request_id` (see [Every request](#guide-every-request)). | | Start to wait for the reply before you send. Send one request for each `place` at a time. |
| Some handlers wait for the database, for example `auth`. Their replies can come after the replies to later events. | node/server.js:11563 | Match a reply by its content, not by its position in the stream. |
| The call-cost limit is 200 in the last 4 s (see [Rate limits](#guide-rate-limits-and-anti-abuse)). Cooldowns are durations in ms. | node/server.js:256-260 | Use timers and a clock that only goes forward. |

Thus each client has the same four parts, in each language:

1. **A reader.** It reads each frame and sends each pong at once. It does nothing slow.
2. **A dispatcher.** It gives each event to its handlers, and to the code that waits for it, in
   arrival order.
3. **Waiters.** A waiter is a promise, future or channel that completes when a matching event
   arrives. Your code starts the waiter, then sends, then waits.
4. **A tick.** A loop on a timer. It reads your state and sends actions. It is the only part
   that waits for replies.

### Where your code runs

<div data-lang="js ts">

Node.js runs all of your code on **one thread**, the event loop. A WebSocket `message`, a timer
and the continuation after each `await` are all tasks on that thread. A task runs until it
returns or reaches an `await`. Nothing interrupts it.

- **There is no separate reader.** `AlSocket` sends the pong and calls your handlers in the same
  `message` listener (`#onPacket`, then `#deliver`). A ping waits behind each task that runs at
  that time.
- **Handlers and the tick never run at the same time.** Thus you need no locks.
- **Your state can change at each `await`.** Other events run during the wait. After an
  `await`, read the state again. Do not use a value that you read before it.
- **A promise starts its work when you make it.** `waitFor` registers its waiter in the
  `Promise` constructor, which runs at once. Thus `waitFor`, then `emit`, then `await` is
  correct.
- **Microtasks run when the current task ends.** The continuation of an `await` runs before the
  next timer or the next network read. Frames that arrive in one network read can all run
  first. `AlSocket` uses microtasks: it gives the kept early events (for example `welcome`) in a
  microtask, after `waitFor` registered its waiter.

TypeScript has the same model at run time. The types add one rule:
`waitFor<Welcome>("welcome")` gives a `Promise<Welcome>`, but nothing checks the JSON at run
time. A wrong type is a wrong assumption, not an error.

</div>

<div data-lang="python">

`asyncio` runs all of your coroutines on **one thread**, the event loop. A coroutine runs until
it reaches an `await` that must wait. Only then can another coroutine run.

- **The reader is one background task.** `AlSocket.connect` starts it with
  `asyncio.create_task(sock._read_loop())`. It sends each pong and calls your handlers in the
  same task.
- **A plain handler (`def`) runs inside the reader.** A ping waits until it returns.
- **An `async def` handler runs as its own task.** `_deliver` runs it as a task with
  `asyncio.ensure_future`, keeps a reference until it ends, and prints its error. It does not hold back the reader. But it runs later, so the next
  events can arrive first.
- **Handlers and the tick never run at the same time.** Thus you need no locks. Your state can
  change at each `await`, so read it again after one.
- **A coroutine does nothing until you await it.** A call to an `async def` function only makes
  a coroutine object. Thus `wait_for` is a plain `def` on purpose. It registers its future at
  once, and then returns a coroutine for the result.
- **Keep a reference to each task.** The event loop keeps only a weak reference to a task. A
  task that nothing references can disappear before it ends.

</div>

<div data-lang="go">

Go runs goroutines on several threads. The scheduler can stop a goroutine at almost any point.
A blocking call blocks only its own goroutine, so blocking code is normal Go.

- **`alsocket` uses two goroutines.** `readLoop` reads each frame, sends each pong, and puts
  each event on a channel. `dispatchLoop` takes the events from that channel and runs your
  handlers, then your waiters.
- **The channel has a buffer of 1,024 events.** If your handlers are slow and the buffer
  fills, `readLoop` blocks. Then no pong goes out, and the server closes the socket after 12 s.
- **Handlers run on the dispatch goroutine. Your tick runs on another goroutine.** They run at
  the same time. Each shared value needs a lock (`sync.Mutex`). The `world`, `cooldowns` and
  `budget` packages each keep one.
- **Go has no futures.** Thus `alsocket` has `Expect`. It registers the waiter now and returns a
  function. A call to that function blocks until the reply, the end of the `ctx`, or the end of
  the socket. `WaitFor` is `Expect` followed by the call, so it cannot register before you send.
- **The waiter gets the event after the handlers.** When `wait(ctx)` returns, the handlers of
  that event (for example the ones that update the world) already ran.
- **Run your tests with `go run -race` or `go test -race`.** The race detector finds a value
  that two goroutines use without the lock.

</div>

<div data-lang="csharp">

.NET runs each `Task` on the **thread pool**. A console program has no
`SynchronizationContext`. Thus the code after an `await` can continue on a different pool
thread from the code before it.

- **`AlSocket` uses two tasks.** `Task.Run(ReadLoop)` reads each frame, sends each pong, and
  writes each event to an unbounded `Channel`. `Task.Run(Dispatch)` reads the channel and runs
  your handlers. A slow handler cannot delay a pong.
- **Handlers run on the dispatcher. Your tick runs on another pool thread.** They run at the
  same time. Each shared value needs a lock. `World` has one object, `Gate`, for its state and for the
  state of `Farmer`.
- **One send at a time.** `ClientWebSocket` allows only one `SendAsync` at a time. `AlSocket`
  puts each send, the pongs too, behind a `SemaphoreSlim`.
- **A `Task` starts when you make it.** `WaitForAsync` registers its waiter before it returns
  the task. Thus `WaitForAsync`, then `EmitAsync`, then `await` is correct.
- **The waiter wakes after the handlers of the same event.** `Deliver` runs the handlers, then
  completes the waiter. The waiter uses `RunContinuationsAsynchronously`, so your code after the
  `await` continues on another pool thread. The dispatcher continues with later events at the
  same time, so read shared state under its lock.

</div>

<div data-lang="rust">

`#[tokio::main]` starts the **multi-thread runtime**: one worker thread for each CPU core.
Tokio moves tasks between the workers. A future does nothing until something polls it, and
`.await` polls it.

- **`AlSocket` uses three tasks.** The reader reads each frame and puts each pong on the
  channel of the writer. The writer owns the sending half of the WebSocket, so only one task
  sends. The dispatcher runs your handlers, then your waiters.
- **Handlers are plain closures (`Fn(&Value) + Send + Sync`), not futures.** They run on the dispatcher task, on some worker thread. Your tick runs on another task, at the
  same time.
- **Shared state is `Arc<Mutex<...>>`.** The course uses `std::sync::Mutex` and never holds a
  guard across an `.await`. The compiler helps here. The guard of `std::sync::Mutex` is not
  `Send`, so `tokio::spawn` refuses a future that holds one across an `.await`.
- **`wait_for` is a plain `fn`, not an `async fn`, on purpose.** An `async fn` runs no code
  until the first poll. A plain `fn` registers the waiter at the call, then returns a `'static`
  future. Thus `wait_for`, then `emit`, then `.await` is correct.
- **To drop a future cancels it.** `request` puts the wait in `tokio::time::timeout`. When the timeout ends, `timeout` drops the wait. The dispatcher then removes the waiter, because its
  `oneshot` receiver is gone.
- **The waiter gets the event after the handlers.** When your `.await` returns, the handlers of
  that event already ran.

</div>

<div data-lang="java">

Java 21 has two kinds of threads. A **platform thread** is an operating-system thread. A
**virtual thread** is a cheap thread that the JVM moves on and off a platform thread when it
blocks. Blocking code is normal Java. A `CompletableFuture` holds a result that is not ready.

- **The HTTP client calls `AlSocket` on its own threads.** `AlSocket` is a
  `WebSocket.Listener`. The client calls `onText` for one message at a time.
  `AlSocket` asks for the next message with `ws.request(1)` at the end of `onText`. `onText` sends the pong and
  puts each event in a `LinkedBlockingQueue`.
- **The dispatcher is a virtual thread** (`Thread.ofVirtual()`). It takes events from the queue
  and runs your handlers.
- **Your program runs on the main thread** with blocking calls: `Thread.sleep`, and `get()` on
  the future of `waitFor`. Handlers and the tick run at the same time. Shared state is behind `synchronized`.
 
- **One send at a time.** `java.net.http.WebSocket` allows one send at a time. `AlSocket`
  chains each send after the one before it.
- **The waiter gets the event after the handlers.** When `get()` returns, the handlers of that
  event already ran. `thenApplyAsync` moves your code to the common `ForkJoinPool`, so the
  dispatcher continues with later events at the same time.

</div>

### Sending a request and waiting for the reply

> **Caution:** Start the wait before you send. If you send first, a fast reply can arrive
> before the wait starts. The wait then misses it and ends at its timeout.

1. Start the wait for `game_response` with a predicate on `place`. Do not wait for it yet.
2. Send the event.
3. Wait for the result of step 1, with a timeout.
4. If the timeout ends first, treat the request as "no reply". Some failures send another
   event and no `game_response`. An example is `attack` on a monster that is gone
   ([`disappear`](#recv-disappear)).

This is `request` from the course, in each language:

<!-- include course/js/albot/actions.js region=request -->

<!-- include course/ts/albot/actions.ts region=request -->

<!-- include course/python/albot/actions.py region=request -->

<!-- include course/go/actions/actions.go region=request -->

<!-- include course/csharp/Albot/Actions.cs region=request -->

<!-- include course/rust/src/actions.rs region=request -->

<!-- include course/java/src/main/java/albot/Actions.java region=request -->

<div data-lang="js ts">

- **Do not `await` the wait in step 1.** `await sock.waitFor(...)` waits before the send, so the
  send never occurs. Keep the promise in a variable, as `request` does.
- **Handle each rejection of a promise that you keep.** If your code throws between step 1 and
  step 3, nothing awaits the kept promise. Its later rejection is an unhandled rejection. Since
  Node.js 15, an unhandled rejection stops the process. If you can leave before step 3, add
  `reply.catch(() => {})` first.
- **To run requests at the same time,** use `Promise.all` or `Promise.allSettled`. Use
  different `place` values, or the replies can mix.
- **A timeout does not stop the server.** The request can still succeed after your timeout.
  Read the next `player` before you send it again.

</div>

<div data-lang="python">

- **Do not await `wait_for` in step 1.** `await sock.wait_for(...)` waits before the send.
  Keep the coroutine in a variable, as `request` does.
- **Await each `emit`.** `emit` is a coroutine. Without `await`, `emit` sends nothing, and Python
  shows "coroutine ... was never awaited".
- **The timeout raises `TimeoutError`.** Since Python 3.11, `asyncio.TimeoutError` is the
  built-in `TimeoutError`. `request` catches it and returns `None`.
- **Cancellation is an exception too.** `task.cancel()` raises `asyncio.CancelledError` at the
  `await` of that task. Do not catch it with `except Exception` and continue; it is a
  `BaseException` on purpose.
- **To run requests at the same time,** use `asyncio.gather` or an `asyncio.TaskGroup`. Use
  different `place` values, or the replies can mix.

</div>

<div data-lang="go">

- **Use `Expect` for each request, not `WaitFor`.** `WaitFor` blocks before it returns, so you
  cannot send after it registers.
- **Give each wait a deadline.** Use `context.WithTimeout`, and `defer cancel()`. A wait with
  `context.Background()` and no reply blocks its goroutine until the socket closes.
- **Check `ErrNoReply` with `errors.Is`.** `Request` returns it when the timeout ends. Other
  errors mean that the socket closed or the send failed.
- **To run requests at the same time,** start one goroutine for each, and collect the results
  on a channel or with a `sync.WaitGroup`. Use different `place` values, or the replies can mix.

</div>

<div data-lang="csharp">

- **Do not `await` the wait in step 1.** Keep the `Task` in a variable, as `RequestAsync` does.
- **Do not use `.Result` or `.Wait()`.** In a console program they do not deadlock, but they
  block a pool thread for the whole wait. Many of them make the pool slow to start new work,
  and your handlers wait too.
- **The timeout throws `TimeoutException`.** A closed socket throws `WebSocketException`.
  `RequestAsync` returns `null` for a timeout only.
- **To run requests at the same time,** use `Task.WhenAll`. Use different `place` values, or the
  replies can mix.

</div>

<div data-lang="rust">

- **Do not `.await` the wait in step 1.** Keep the future in a variable, as `request` does.
  The waiter already exists, because `wait_for` registered it.
- **Await each future that you make, or drop it on purpose.** A future that nobody
  polls never completes. The compiler warns about an unused `#[must_use]` future.
- **Put the timeout around the wait** with `tokio::time::timeout`. Its `Err` means "no reply".
  An `Err` inside its `Ok` means that the socket closed.
- **To wait for the first of several things,** use `tokio::select!`. The branches that lose are
  dropped, and thus cancelled.
- **To run requests at the same time,** use `tokio::join!` or `futures_util::future::join_all`.
  Use different `place` values, or the replies can mix.

</div>

<div data-lang="java">

- **Do not call `get()` on the future in step 1.** Keep the future in a variable, as `request`
  does.
- **`get()` wraps each failure in an `ExecutionException`.** Its cause is a `TimeoutException`
  (from `orTimeout`) or an `IOException` (the socket closed). `request` returns `null` for a
  timeout, and throws an `UncheckedIOException` when the socket closed.
- **Prefer `get()` with a timeout, or `orTimeout`, over `join()` without one.** A future
  without a timeout can wait forever.
- **To run requests at the same time,** use `CompletableFuture.allOf`, or one virtual thread for
  each request. Use different `place` values, or the replies can mix.

</div>

### Handlers: what must not occur in one

A handler is on the path of each event after it. Keep each handler short: change your state,
and return. Do not wait for a reply inside a handler.

<div data-lang="js ts">

- **A long loop in a handler stops everything.** No other event, no timer and no pong runs
  until it returns. Events wait in the socket, and the server closes the connection after 12 s
  without a pong.
- **An `async` handler does not stop the reader at its `await`.** `AlSocket` calls it and does
  not wait for the promise that it returns. The rest of the handler runs later, after other
  events. Thus an `async` handler can apply an old event after a newer one.
- **`AlSocket` only logs a rejection of an `async` handler.** It catches a throw and logs a
  rejected promise, then continues. Put `try`/`catch` inside each `async` handler to react to
  the error.

</div>

<div data-lang="python">

- **A long loop in a plain handler stops everything.** No other coroutine and no pong runs until
  it returns. The server closes the connection after 12 s without a pong.
- **An `async def` handler runs as a task.** Its code after an `await` runs later, after other
  events. Thus it can apply an old event after a newer one. Prefer plain `def` handlers that
  only change state.
- **Do not call blocking functions in a coroutine:** `time.sleep`, `requests`, a synchronous
  `httpx.Client`, a large file read. Each one stops the event loop. Use `asyncio.sleep` and
  `httpx.AsyncClient`.
- **To find slow callbacks,** run with `PYTHONASYNCIODEBUG=1`. In debug mode, asyncio logs each
  callback that takes more than 100 ms.

</div>

<div data-lang="go">

- **Do not wait for a reply inside a handler.** The reply must come through the dispatch
  goroutine, and that goroutine is in your handler. The wait ends only at its deadline. Without
  a deadline, it never ends.
- **Do not send on an unbuffered channel from a handler** if the receiver can be slow. The
  handler blocks, and the dispatch goroutine blocks with it.
- **A predicate runs while the socket holds its lock.** It must not call methods of the
  `Socket`, or it deadlocks.
- **For long work, start a goroutine** from the handler, and return. That goroutine must take
  the locks itself.

</div>

<div data-lang="csharp">

- **Do not wait for a reply inside a handler.** The reply must come through the dispatcher, and
  the dispatcher is in your handler. The wait ends only at its timeout.
- **Handlers are `Action<JsonElement>`, not `Func<Task>`.** An `async` lambda as a handler is an
  `async void` method. Its exceptions do not come back to `AlSocket`, and an exception in an
  `async void` method stops the process. Do not use `async` handlers.
- **`lock` cannot contain an `await`.** The compiler refuses it (CS1996). Copy what you need
  inside the lock, then `await` outside it, as `Farmer.TickAsync` does.

</div>

<div data-lang="rust">

- **Do not block the dispatcher.** A handler is a plain closure, so it cannot `.await`. Do not
  use `block_on` inside it, and do not wait on a `std::sync::mpsc` channel there.
- **Do not lock a mutex that the tick can hold across a slow call.** The handler then waits for
  the tick. The course never holds a lock across an `.await`, so each lock is short.
- **A panic in a handler does not stop the socket.** `deliver` catches it with `catch_unwind`
  and continues. A `std::sync::Mutex` that a panic left locked is "poisoned". `Farmer` reads
  it again with `unwrap_or_else(|e| e.into_inner())`.
- **For long work, `tokio::spawn` a task** from the handler. Give it clones of the `Arc` values
  that it needs.

</div>

<div data-lang="java">

- **Do not call `get()` or `join()` inside a handler.** The reply must come through the
  dispatcher thread, and that thread is in your handler. The wait ends only at its timeout.
- **Keep `synchronized` blocks short.** In Java 21, a virtual thread that blocks inside
  `synchronized` keeps its platform thread ("pinning"). Java 24 removed this limit (JEP 491).
  The dispatcher is a virtual thread.
- **Do not throw checked exceptions out of a handler.** A handler is a `Consumer<JsonNode>`.
  `AlSocket` catches each `RuntimeException` and continues.
- **For long work, start a virtual thread** from the handler with `Thread.startVirtualThread`.

</div>

### Long work: path searches and other CPU work

An A* search on a large map can take a long time. Where it runs decides what waits for it.

<div data-lang="js ts">

On the one thread, a long search holds back each event, timer and pong. Two methods help:

- **Split the work.** Do a part of the search, then `await new Promise(r => setImmediate(r))`,
  then continue. Events run between the parts.
- **Use a worker thread** (`node:worker_threads`). It runs the search on another thread and
  sends the path back as a message. A worker has its own memory, so send it the map data.

In the course, `pathfind` runs in the tick. A tick that searches holds back events for that
time. On the test server and on normal maps, this time is short.

</div>

<div data-lang="python">

On the one thread, a long search holds back each event and each pong. Python has one more
limit: the global interpreter lock (GIL). Only one thread runs Python code at a time.

- **`asyncio.to_thread(fn, ...)`** runs `fn` on another thread. This helps for blocking I/O. It
  does not help much for CPU work in pure Python, because of the GIL.
- **For CPU work, use a process:** `loop.run_in_executor(ProcessPoolExecutor(), fn, ...)`. The
  arguments and the result go between the processes as pickles.
- **Or split the work,** with `await asyncio.sleep(0)` between the parts.

In the course, `pathfind` runs in the tick, on the event loop.

</div>

<div data-lang="go">

A search in your tick goroutine blocks only that goroutine. The reader and the dispatcher
continue. Nothing else is necessary.

Do not run a long search inside a handler. The dispatch goroutine then waits, and the events
after it wait in the buffer of 1,024.

</div>

<div data-lang="csharp">

A search in your tick blocks only the pool thread that runs it. The reader and the dispatcher
continue on other threads.

- **For a long search, use `Task.Run(() => grid.FindPath(...))`** and `await` it. The tick then
  frees its thread during the search.
- **Use `Task.Delay`, not `Thread.Sleep`, in async code.** `Thread.Sleep` blocks a pool thread.

</div>

<div data-lang="rust">

> **Caution:** Do not block a worker thread of Tokio. A blocked worker cannot run the other
> tasks on it, the reader included.

- **For a long search, use `tokio::task::spawn_blocking`.** It runs the closure on a separate
  thread pool for blocking work. `.await` its `JoinHandle` for the path.
- **Use `tokio::time::sleep`, not `std::thread::sleep`,** in async code.
- **Do not use `reqwest::blocking`** inside the runtime. Use the async `reqwest::Client`.

In the course, `pathfind` runs in the tick task. On normal maps, the search is short.

</div>

<div data-lang="java">

A search on the main thread blocks only the main thread. The listener and the dispatcher
continue.

- **Virtual threads are for waits, not for CPU work.** A virtual thread that computes keeps its
  platform thread. For many searches at the same time, use a fixed pool of platform threads
  (`Executors.newFixedThreadPool`).
- **`Thread.sleep` is correct here.** On the main thread it blocks only that thread. On a
  virtual thread, it frees the platform thread.

</div>

### Timers and the tick

The course runs a tick every 100 ms. Cooldowns are durations in ms. Measure durations with a
**monotonic clock**: a clock that only goes forward. A wall clock can jump when the system time
changes.

<div data-lang="js ts">

- **Use a loop with `await sleep(ms)`**, as `farm` does. The next tick starts only after the
  last one ends.
- **Do not use `setInterval` with an `async` function.** `setInterval` does not wait for the
  promise. A tick that waits 2 s for a reply then runs at the same time as the next ticks.
- **`performance.now()` is monotonic.** `Date.now()` is the wall clock. The course uses `performance.now()` for every
  duration. In Docker on WSL2, the wall clock jumped by seconds.

</div>

<div data-lang="python">

- **Use a loop with `await asyncio.sleep(seconds)`**, as `farm` does. The next tick starts only
  after the last one ends.
- **`time.monotonic()` is monotonic.** `time.time()` is the wall clock. `loop.call_later` and
  `loop.time()` use the monotonic clock.
- **`asyncio.timeout(seconds)`** (Python 3.11+) puts a deadline on a block of `await`s.

</div>

<div data-lang="go">

- **Use a loop with `time.Sleep`**, as `cmd/farm` does, or a `time.Ticker`. A `Ticker` drops
  ticks when your loop is slow. It does not send them all later.
- **`time.Now()` has a monotonic reading.** `time.Since(t)` and `t.Sub(u)` use it. Thus
  durations are correct also when the wall clock jumps.
- **Stop a loop with a `ctx`.** `cmd/farm` uses `signal.NotifyContext`, so Ctrl-C cancels the
  `ctx`.

</div>

<div data-lang="csharp">

- **Use a loop with `await Task.Delay(ms)`**, as `Farm` does, or `PeriodicTimer` (.NET 6+) with
  `await timer.WaitForNextTickAsync()`. Both wait for the last tick to end.
- **Do not use `System.Threading.Timer` with an `async` callback.** It does not wait for the
  task, so ticks can run at the same time.
- **`Environment.TickCount64` and `Stopwatch` are monotonic.** `DateTime.Now` is the wall
  clock.

</div>

<div data-lang="rust">

- **Use a loop with `tokio::time::sleep(TICK).await`**, as `farm` does, or
  `tokio::time::interval`.
- **Set the missed-tick behavior of an `interval`.** The default is `Burst`: after a slow tick,
  it fires many ticks at once to catch up. `set_missed_tick_behavior(MissedTickBehavior::Delay)`
  stops that.
- **`std::time::Instant` and `tokio::time::Instant` are monotonic.** `SystemTime` is the wall
  clock.

</div>

<div data-lang="java">

- **Use a loop with `Thread.sleep(ms)`**, as `Farm` does, or a
  `ScheduledExecutorService` with `scheduleWithFixedDelay`. Fixed delay waits for the last tick
  to end.
- **`System.nanoTime()` is monotonic.** `System.currentTimeMillis()` is the wall clock. The
  course uses `World.nowMs()`, which reads `System.nanoTime()`. A wall clock that jumped back
  2.3 s once made a walk fail in the course tests.

</div>

### When the connection ends

When the connection ends, for any cause, `AlSocket` gives a local `disconnect` event with a
reason. Then each waiter fails. Stop the tick, then reconnect with the full handshake (see
[Disconnection](#guide-connecting-to-a-game-server) and
[AlSocket](#learn-alsocket), "When the connection breaks").

<div data-lang="js ts">

- A waiter rejects with an `Error` whose message starts with `socket closed`. `emit` throws
  `socket is closed`.
- **Stop on Ctrl-C** with `process.on("SIGINT", ...)`. `farm` sets a flag, ends the tick, closes
  the socket, then calls `process.exit(0)`. The signal handler keeps Node.js alive otherwise.

</div>

<div data-lang="python">

- A waiter raises `ConnectionError`. `emit` raises `ConnectionError("socket is closed")`.
- **Stop on Ctrl-C** with `loop.add_signal_handler(signal.SIGINT, ...)`. Windows does not have
  it, so there Ctrl-C raises `KeyboardInterrupt`, and `asyncio.run` cancels the main task.
- **`await sock.close()`** waits for the reader task to end, for at most 5 s.

</div>

<div data-lang="go">

- A waiter returns `ErrClosed`. `sock.Done()` is a channel that closes when the dispatcher has
  given out the last event. Use it in a `select` with your tick.
- **Stop on Ctrl-C** with `signal.NotifyContext`, and give that `ctx` to `b.Act.SetContext`.
  Each wait of the actions then ends at once.
- **`sock.Close()` waits** until the dispatcher has given out the last event, for at most 5 s.

</div>

<div data-lang="csharp">

- A waiter throws `WebSocketException`. `sock.Completion` is a `Task` that completes when the
  dispatcher has given out the last event.
- **Stop on Ctrl-C** with `Console.CancelKeyPress`. Set `e.Cancel = true`, or the process ends
  at once. For `docker stop` (SIGTERM), `Farm` uses `PosixSignalRegistration`.
- **`CloseAsync` returns after at most 5 s.** If the server does not answer the close, it
  aborts the WebSocket.

</div>

<div data-lang="rust">

- A waiter returns `Err("socket closed")`. `sock.close().await` returns when the dispatcher has
  given out the last event, or after at most 5 s. Then it stops the connection itself.
- **A dropped `AlSocket` also closes its connection.** Its `Drop` sends `41` and a close frame.
- **Stop on Ctrl-C** with `tokio::signal::ctrl_c()`, on its own task. `farm` sets a flag that
  the tick loop reads.

</div>

<div data-lang="java">

- `get()` on a waiter throws an `ExecutionException` with an `IOException` as its cause.
  `sock.done()` is a future that completes when the dispatcher has given out the last event.
- **`close()` waits at most 5 s.** Then it closes the transport itself and returns.
- **Stop on Ctrl-C** with `Runtime.getRuntime().addShutdownHook(...)`. The JVM runs the hook on
  SIGINT and SIGTERM, then ends. `Farm` makes its hook wait, for at most 10 s, until the
  loop has closed the socket.

</div>

## Async 1: Why a client needs concurrency

This chapter is the same for all languages. It states the problem that each async model
solves. The next chapters show how your language solves it.

### The problem: one program, four clocks

An Adventure Land client must do several things, and each one has its own clock:

| What | When it occurs | What occurs if you are late |
|---|---|---|
| The server sends a ping (`2`). | Every 4 s (node/server.js:83). | Without a pong in 12 s, the server closes the socket (node/server.js:84). |
| The server sends world events: `entities`, `player`, `hit`, `death`, chat. | At any time, many times each second near monsters. | Your view of the world becomes old. You attack a monster that is gone. |
| Your tick decides and sends an action. | Every 100 ms in the course. | Your character stands still. |
| Your code waits for a reply, for example the `game_response` of a `buy`. | One round trip, usually less than 1 s. You stop at 2 s. | Your tick stops while it waits, unless something else can run. |

A simple program does one thing at a time. Look at this program, in pseudocode:

```text
loop:
    frame = socket.read()        # waits until the server sends something
    handle(frame)
    if attack_ready(): send attack
```

`socket.read()` **blocks**: the program stops on this line until a frame arrives. While it
waits, the program cannot attack. Now turn the program around:

```text
loop:
    if attack_ready(): send attack
    sleep(100 ms)                # waits, and reads nothing
```

Now the program cannot read. The pings stay in the socket, and after 12 s the server closes
the connection. Neither order works. The program must wait for two or more things at the
same time. **Concurrency** is the ability to have more than one task in progress at the same
time. Each async model is a method to get it.

### An example second of a session

The times here are an example, not a measurement. They show how the events of a session mix.

```text
time   from the server                  your program
-----  -------------------------------  -------------------------------------------
  0 ms                                  tick: target in range, attack ready
  1 ms                                  send  42["attack",{"id":"48213"}]
                                        start a wait for game_response (place "attack")
 31 ms  42["entities",{...}]            handler: update monsters
 48 ms  42["game_response",{"response":"data","place":"attack",...}]
                                        the wait ends: the attack started
 52 ms  42["hit",{"hid":"Wizard","id":"48213",...}]
                                        handler: monster 48213 lost health
100 ms                                  tick: nothing ready
140 ms  2   (an Engine.IO ping)         reader: send 3 at once
200 ms                                  tick: health low, potion ready, send use_hp
...
```

Your program must read at 31 ms, 48 ms, 52 ms and 140 ms, while the tick runs every 100 ms. It
must also wait for one reply among the other events. Nothing in this stream tells which reply
belongs to which request, except its content (see
[The async model of your language](#guide-the-async-model-of-your-language)).

### Blocking and non-blocking I/O

The operating system gives a program two kinds of socket read:

- **A blocking read.** The thread stops until data arrives. This is simple, but one thread can
  wait for only one thing.
- **A non-blocking read, with a notification.** The read returns at once, also when there is
  no data. The program then asks the system to tell it when data arrives. On Linux, the
  system call is `epoll`. On macOS, it is `kqueue`. On Windows, it is an I/O completion port
  (IOCP). One thread can wait on thousands of sockets and timers with one call.

Every async model uses one of these two. Most use both: a notification for the
network, and blocking threads for work that the system cannot notify, such as many file
operations.

### Two families: threads and event loops

**Threads.** The program starts more than one thread. Each thread runs code one statement after
the other, and it can block. The operating system decides when each thread runs: for
example, one thread reads the socket, and another runs the tick. This is easy to write. But two threads can change
the same data at the same time, so the program needs locks.

**An event loop.** The program has one thread with a loop. The loop asks the system for the
next ready event: a frame, a timer, a completed write. It runs the code for that event, then it
asks again. Your code must never block, because a block stops the loop.

Instead, your code starts an operation and gives a continuation: the code to run when the
operation completes. Callbacks, promises, futures and `await` are different ways to write a continuation.

Most modern runtimes mix the two. They run many small tasks on a few threads:

| Language | Family | The unit of work | Where a switch can occur | Code runs in parallel |
|---|---|---|---|---|
| JavaScript, TypeScript | event loop | promise, async function | only at `await`, or when a callback returns | no (yes with worker threads) |
| Python | event loop | coroutine, `Task` | only at `await` | no (yes with processes) |
| Go | many goroutines on a few threads | goroutine | at almost any point | yes |
| C# | continuations on a thread pool | `Task` | at `await` for one task; at any point between threads | yes |
| Rust (Tokio) | tasks on a few threads | `Future`, task | only at `.await` for one task; at any point between threads | yes |
| Java 21 | threads, virtual or platform | `Thread`, `CompletableFuture` | at almost any point | yes |

### Concurrency and parallelism

These two words have different meanings:

- **Concurrency**: more than one task is in progress. A single thread can do it, if it changes
  between tasks.
- **Parallelism**: more than one task runs at the same instant, on different CPU cores.

An AL bot needs concurrency. It rarely needs parallelism, because most of its time is a wait
for the network. Parallelism helps only for CPU work, such as a long path search.

### Cooperative and preemptive

- **Cooperative**: a task runs until it gives control back, at an `await` or at its end.
  Between two such points, no other task of the same thread can run. This makes reasoning
  easy, but one slow task stops all the others.
- **Preemptive**: the scheduler can stop a task at almost any point and run another. One slow
  task cannot stop the others. But any two lines of your code can have other work between
  them, so shared data needs protection.

Keep these two questions in mind for each chapter: **where can a switch occur**, and **which
code can run at the same instant as mine**. The answers decide where your handlers run, if you
need locks, and why `AlSocket` has its design.

## Async 2: The runtime

The runtime is the part of your language that decides which code runs, on which thread, and
when. This chapter shows the threads in a running bot, the queues of the scheduler, and how it
waits for the network.

<div data-lang="js ts">

#### One process, three layers

A running Node.js program has three layers. **V8** compiles and runs your JavaScript. **libuv**
is a C library that owns the event loop and talks to the operating system. **Node.js** itself
is the glue: it gives V8 functions such as `setTimeout`, `fs.readFile` and the built-in
`WebSocket`, and connects them to libuv.

Your JavaScript runs on one thread only: the **main thread**. V8 has one call stack there. The
event loop runs on the same thread. Thus the loop can only do its work when your code returns.
This one fact explains most of this lecture.

#### The threads of a running bot

The process has more than one thread, but only one of them runs your code. This program lists
them. It reads `/proc`, so it runs on Linux only (Docker `node:22` is fine).

```js
// threads.mjs: list the threads of this Node.js process (Linux only: it reads /proc).
import { readdirSync, readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";

function threads() {
  // Each entry of /proc/self/task is one thread. "comm" is its name.
  const names = readdirSync("/proc/self/task").map((id) =>
    readFileSync(`/proc/self/task/${id}/comm`, "utf8").trim());
  const count = {};
  for (const n of names) count[n] = (count[n] ?? 0) + 1;
  return count;
}

console.log("at start:", threads());
await readFile("/etc/hostname"); // the first async fs call starts the libuv thread pool
console.log("after an async fs call:", threads());
```

Output on Node.js 22 (`node threads.mjs`):

```text
at start: { node: 6, DelayedTaskSche: 1 }
after an async fs call: { node: 6, DelayedTaskSche: 1, 'libuv-worker': 4 }
```

| Thread | How many | What it does | Runs your JS? |
|---|---|---|---|
| main (`node`) | 1 | V8, your code, the event loop, all socket I/O | yes |
| V8 platform workers (`node`) | 4 (`--v8-pool-size`) | Garbage collection and compilation in the background | no |
| `DelayedTaskSche` | 1 | Timers for the V8 platform tasks | no |
| SIGUSR1 watcher (`node`) | 1 | Waits for `SIGUSR1`, the signal that starts the inspector | no |
| `libuv-worker` | 4 (`UV_THREADPOOL_SIZE`), started at first use | Blocking work: `fs`, `dns.lookup`, some `crypto`, `zlib` | no |

You can check the table. With `--v8-pool-size=2` the program shows 4 `node` threads, and with
`--disable-sigusr1` one fewer.

The game socket uses none of the extra threads. A TCP socket is non-blocking. The main thread
asks the kernel (epoll on Linux, kqueue on macOS, IOCP on Windows) to report when it can read.
The thread pool helps one time per connection: `dns.lookup` resolves the host name of the game server
on a pool thread, because `getaddrinfo` blocks. `fetch` for the HTTP login also runs its sockets
on the main thread.

#### The loop and its phases

The event loop is a `while` loop in libuv (`uv_run`). Each turn goes through fixed **phases**.
Each phase has its own queue of callbacks.

```text
          ┌───────────────────────────┐
     ┌───>│ timers                    │  setTimeout / setInterval callbacks that are due
     │    ├───────────────────────────┤
     │    │ pending callbacks         │  a few I/O callbacks that libuv put off (some TCP errors)
     │    ├───────────────────────────┤
     │    │ idle, prepare             │  internal to Node.js
     │    ├───────────────────────────┤
     │    │ poll                      │  wait in epoll_wait, then run the I/O callbacks:
     │    │                           │  the WebSocket "message" events of AlSocket run here
     │    ├───────────────────────────┤
     │    │ check                     │  setImmediate callbacks
     │    ├───────────────────────────┤
     │    │ close callbacks           │  "close" of handles, for example a destroyed socket
     │    └─────────────┬─────────────┘
     └──────────────────┘  stop when no handle or request keeps the loop alive

  After EACH callback above: run the process.nextTick queue to empty,
  then the microtask queue (promise jobs, queueMicrotask) to empty.
```

The **poll** phase is where the process sleeps. Here, libuv calls `epoll_wait` with a
timeout. The timeout is the time until the next timer is due, or zero if `setImmediate`
callbacks wait. Four things wake
the thread:

- A file descriptor is ready: data arrived on the game socket.
- The timeout ends: a timer is due.
- A `uv_async` signal: a pool thread finished its work, or a worker thread sent a message.
- A signal such as `SIGINT`, through a pipe that libuv watches.

The loop stops when nothing keeps it alive: no open socket, no active timer, no pending
request. An open `AlSocket` keeps it alive. So does each `setTimeout` of a waiter.

In this lecture, a **task** is one callback that the loop calls from a phase. A timer callback
is a task. One WebSocket `message` event is a part of a task (see below).

#### The two queues between tasks

V8 has its own queue: the **microtask queue**. A settled promise puts its reactions there as
**promise jobs**. `queueMicrotask(fn)` puts `fn` there. Node.js adds a second queue,
**`process.nextTick`**.

When a task returns, Node.js empties the `nextTick` queue, then the
microtask queue. It repeats this until both are empty. Only then does the loop continue.

Since Node.js 11, this occurs after each callback, not after each phase.

```js
// order.cjs: one of each kind of job, queued from plain synchronous code.
console.log("1. sync: start");
setTimeout(() => console.log("6. timers phase: setTimeout 0"), 0);
setImmediate(() => console.log("7. check phase: setImmediate"));
Promise.resolve().then(() => console.log("4. microtask: promise job"));
queueMicrotask(() => console.log("5. microtask: queueMicrotask"));
process.nextTick(() => console.log("3. nextTick queue"));
console.log("2. sync: end");
```

```text
1. sync: start
2. sync: end
3. nextTick queue
4. microtask: promise job
5. microtask: queueMicrotask
6. timers phase: setTimeout 0
7. check phase: setImmediate
```

Two details change this output. First, the order of lines 6 and 7 can differ from run to run.
The main script runs before the first turn of the loop. A 1 ms timer may or may not be due at
the first timers phase.

Second, save the same code as `order.mjs`, and lines 4 and 5 come
before line 3. In an ES module, the top-level code runs inside a promise job. V8 empties the
microtask queue before Node.js gets control back, so the `nextTick` queue waits. The course
uses ES modules (`"type": "module"`).

Inside an I/O callback, the order never changes. This program starts in the poll phase:

```js
// phases.mjs: the order of the phases, seen from an I/O callback.
import { readFile } from "node:fs";

readFile(import.meta.filename, () => {
  // We are in the poll phase now: an I/O callback.
  console.log("1. poll phase: the readFile callback");
  setTimeout(() => console.log("5. timers phase (next turn of the loop): setTimeout 0"), 0);
  setImmediate(() => console.log("4. check phase (this turn): setImmediate"));
  Promise.resolve().then(() => console.log("3. microtask, after the callback"));
  process.nextTick(() => console.log("2. nextTick, before the microtasks"));
});

// Two timers that are due at the same time: the microtasks of the first run
// before the second timer starts (Node.js 11 and later).
setTimeout(() => {
  console.log("A. timer 1");
  Promise.resolve().then(() => console.log("B. microtask of timer 1"));
}, 50);
setTimeout(() => console.log("C. timer 2"), 50);
```

```text
1. poll phase: the readFile callback
2. nextTick, before the microtasks
3. microtask, after the callback
4. check phase (this turn): setImmediate
5. timers phase (next turn of the loop): setTimeout 0
A. timer 1
B. microtask of timer 1
C. timer 2
```

#### Cooperative, with one kind of switch point

Nothing preempts your JavaScript. V8 can stop the thread for garbage collection, but it never
runs other JavaScript in the middle of yours. A switch from one piece of your code to another
occurs at one point only: **when the call stack is empty**. That is the end of a task, or the
end of a microtask. An `await` causes a switch only because it makes the async function return
([Async 4](#guide-async-4-what-await-does) shows how). A long `for` loop has no such point.

#### The path of one frame from the game server

This is the path of each Socket.IO frame through the course client. All of it runs on the main
thread, in the poll phase.

```text
 kernel: bytes arrive on the TCP socket
   │  epoll_wait returns: fd is readable
   ▼
 libuv: read() into a buffer, call Node.js
   ▼
 undici (the built-in WebSocket): parse the WebSocket frames in the buffer
   │  for EACH complete frame: dispatch a "message" event, synchronously
   ▼
 AlSocket "message" listener ──> #onPacket(packet)
   │   "2" (ping)  ──> ws.send("3")          the pong is written in this task
   │   "42[...]"   ──> #deliver(name, data)  your handlers, then the waiters
   ▼
 the stack is empty: nextTick queue, then microtasks
   (the code after each `await` that a waiter woke runs here)
```

One TCP read can hold more than one frame. The undici parser handles all of them in one loop.
Thus their `message` events run in one task, with no microtasks between them. A check program with a tiny
WebSocket server sent frames `A` and `B` in one TCP write, and `C` 50 ms later. Each listener
queued a microtask:

```text
message A
message B
  microtask after A
  microtask after B
message C
  microtask after C
```

Thus "a microtask runs before the next event" is true between TCP reads, not between frames.
This matters in Async 4: when your code continues after `await reply`, the events after the
reply can already be in the world.

#### Why a long loop costs you the connection

The server sends a ping (`2`) every 4 s and closes the socket if no pong (`3`) arrives in 12 s.
`AlSocket` writes the pong in the `message` listener. That listener is a callback of the poll
phase. If your code holds the thread, the poll phase does not run, and the ping stays in the
kernel buffer. The pong cannot go out, even if the ping arrived early.

This program shows it against the course test server. Start the server with short ping times,
so that you wait about 3 s, not 16 s:
`TEST_PING_INTERVAL=1000 TEST_PING_TIMEOUT=2000 node server.js` in `course/test-server`. Save
the program in `course/js`.

```js
// pong-block.js: a long synchronous loop holds back the pong.
// Start the test server with short ping times, so that you wait 3 s, not 16 s:
//   TEST_PING_INTERVAL=1000 TEST_PING_TIMEOUT=2000 node server.js
import { AlSocket } from "./albot/alsocket.js";

const url = process.env.AL_WS_URL ?? "ws://localhost:8022/ws1/?EIO=4&transport=websocket";
const t0 = performance.now();
const at = () => `${((performance.now() - t0) / 1000).toFixed(1)} s`; // time since start

const sock = await AlSocket.connect(url);
console.log(at(), "connected");
sock.on("disconnect", (reason) => console.log(at(), "disconnect:", reason));

setTimeout(() => {
  console.log(at(), "start 5 s of CPU work, with no await in it");
  const end = performance.now() + 5000;
  while (performance.now() < end) {} // a path search, a big JSON file, a slow loop...
  console.log(at(), "the loop ends; now the queued events run");
}, 500);
```

```text
0.0 s connected
0.5 s start 5 s of CPU work, with no await in it
5.5 s the loop ends; now the queued events run
5.5 s disconnect: transport closed (code 1005)
```

The server closed the socket at about 3 s. The client learned it at 5.5 s, because the
`close` event also waited for the loop. With the live values, the limit is a pause of about
12 s to 16 s. But each pause of 100 ms already makes each event and each timer 100 ms late.
[Async 5](#guide-async-5-several-things-at-the-same-time) shows the two cures: split the
work, or move it to a worker thread.

</div>

<div data-lang="python">

This chapter is about CPython 3.12 with `asyncio`, on Linux. The course runs on 3.11+. Where 3.11
and 3.12 differ, the text says so. The source of `asyncio` is plain Python in `Lib/asyncio/`.
Open it when a sentence here is not enough: the loop is about 2,000 lines, and most of it is
easy to read.

#### One thread, one loop

`asyncio.run(main())` does five things, in this order:

1. It makes a new event loop.
2. It wraps `main()` in a Task.
3. It runs the loop until that Task ends.
4. It cancels each task that is still alive, and waits for them.
5. It stops the default thread pool and closes the loop.

The loop is an object with a `while` loop inside. It runs on the thread that called
`asyncio.run`, the main thread. Each coroutine of your bot runs on this thread: the reader of
`AlSocket`, each handler, the tick, the HTTP calls of `httpx`. The loop never moves a coroutine
to another thread.

The loop class depends on the operating system. On Linux it is `_UnixSelectorEventLoop` over an
`EpollSelector`. On macOS the selector is `KqueueSelector`. On Windows, the default since
Python 3.8 is `ProactorEventLoop`, which uses I/O completion ports (IOCP). The model of this
chapter is the selector loop. The proactor has the same queues, but it waits for completed
operations, not for ready sockets.

#### The threads of a running bot

A bot has fewer threads than you can expect. This program connects an `AlSocket` and lists
the threads and the tasks:

```python
# rt_threads.py (fragment: `fakeal` is a small fake game server of the checks;
# with the course test server, use its URL instead)
import asyncio
import threading

import fakeal
from alsocket import AlSocket


def show(when: str) -> None:
    names = sorted(t.name for t in threading.enumerate())
    print(f"{when}: {names}")


async def main(url: str) -> None:
    show("before connect")
    sock = await AlSocket.connect(url)  # "localhost": a DNS lookup
    show("after connect ")
    print("tasks:", sorted(t.get_coro().__qualname__ for t in asyncio.all_tasks()))
    await sock.close()


with fakeal.server() as url:
    asyncio.run(main(url))
show("after asyncio.run")
```

It prints:

```text
before connect: ['MainThread']
after connect : ['MainThread', 'asyncio_0']
tasks: ['AlSocket._read_loop', 'main']
after asyncio.run: ['MainThread']
```

| Thread | What runs on it |
|---|---|
| `MainThread` | The loop, and thus all of your coroutines, all handlers and all timers. |
| `asyncio_0`, `asyncio_1`, ... | The default thread pool of the loop. The loop makes it at the first use. `connect` used it for `getaddrinfo`, because the C function that resolves a host name blocks. `asyncio.to_thread` and `run_in_executor(None, ...)` use it too. It has `min(32, cpus + 4)` threads at most. |

`websockets` makes no thread. Timers make no thread. There is no "reader thread": the reader is
a task on the main thread. A host name that is an IP address skips the thread pool.

#### What is inside the loop

The loop keeps three structures:

- **The ready queue** (`loop._ready`), a `deque` of `Handle` objects. A handle is a callback
  plus its arguments. `loop.call_soon(f, x)` appends one.
- **The timer heap** (`loop._scheduled`), a heap of `TimerHandle` objects, sorted by their
  time. `loop.call_later(delay, f)` and `loop.call_at(when, f)` push one. The clock is
  `loop.time()`, which is `time.monotonic()`.
- **The selector**, one `epoll` object. Each socket that the loop watches is in it, with the
  callback for "readable" or "writable".

The loop also owns a socket pair, the **self-pipe**. Its read end is in the selector. A byte on
it wakes the loop. Chapter [Shared state](#guide-async-7-shared-state) shows why this matters.

#### One iteration: `_run_once`

`run_forever` calls `_run_once` in a loop. One call is one iteration. This is
`base_events.py` of 3.12, in short:

```text
_run_once():
  1. timeout = 0                    if the ready queue is not empty
             = first timer - now    else, if there is a timer
             = None (forever)       else
  2. events = selector.select(timeout)        <- epoll_wait: the thread sleeps here
  3. for each ready socket: append its callback to the ready queue
  4. for each timer that is due: move it from the heap to the ready queue
  5. n = len(ready queue)
     run exactly n handles, oldest first      <- your code runs only here
     (a handle that a callback adds now waits for the NEXT iteration)
```

Step 5 is the only place where the loop calls your code. Step 2 is the only place where the
thread sleeps. Step 5 counts the queue before it starts. Thus a callback that schedules
another callback cannot hold the loop forever: the new one waits behind the next `select`.

This program shows the order:

```python
# rt_order.py: the order in which the event loop runs callbacks.
import asyncio


async def main() -> None:
    loop = asyncio.get_running_loop()
    # _selector is private: we read it here only to show what is under the loop.
    print(type(loop).__name__, "with", type(loop._selector).__name__)
    loop.call_later(0, print, "4. timer (call_later 0): ready after the poll")
    loop.call_soon(print, "1. call_soon A")

    def b() -> None:
        print("2. call_soon B, which adds C")
        loop.call_soon(print, "5. C: added during a pass, so it waits for the next pass")

    loop.call_soon(b)
    loop.call_soon(print, "3. call_soon D")
    print("0. main still runs: nothing above has run yet")
    await asyncio.sleep(0.01)  # main gives the thread back to the loop here


asyncio.run(main())
```

It prints:

```text
_UnixSelectorEventLoop with EpollSelector
0. main still runs: nothing above has run yet
1. call_soon A
2. call_soon B, which adds C
3. call_soon D
4. timer (call_later 0): ready after the poll
5. C: added during a pass, so it waits for the next pass
```

The timer runs after D, although it has a delay of 0. Step 4 moves it to the ready queue
behind A, B and D. C runs last, in the next iteration.

#### What wakes the loop

The thread sleeps in `epoll_wait`. Three things end that sleep:

- **A socket becomes readable or writable.** For the game socket, this is a TCP segment from
  the server.
- **The timeout ends.** The loop computed it from the first timer, for example the
  `asyncio.sleep(0.1)` of the tick.
- **A byte arrives on the self-pipe.** `loop.call_soon_threadsafe` writes it. The signal
  handlers of `loop.add_signal_handler` write it too.

Nothing else wakes the loop. A plain `call_soon` from another thread adds a handle, but the
loop does not see it until one of the three things occurs.

#### Cooperative, and where a switch can occur

The loop runs one handle at a time, and each handle runs to its end. A task is not one handle.
Each **step** of a task is one handle. A step runs the coroutine until it must wait for
something that is not done. Then the step returns, and the loop runs the next handle.

Thus `asyncio` is cooperative. A switch between tasks can occur only at an `await` that
suspends. Not every `await` suspends:

- `await some_coroutine()` is a function call. If the coroutine returns without a wait, no
  switch occurs.
- `await sock.emit(...)` normally does not switch. `websockets` writes the frame into the
  kernel buffer at once. It waits only when that buffer is full.
- `await asyncio.sleep(0)` always switches. It is the explicit "let the others run".

Between two switches, your code owns the thread. Nothing can stop it: no other task, no timer,
no pong. Python threads can still interrupt it, because the operating system schedules
threads. But a bot that uses only the loop has no other thread that runs Python code.

#### What this means for AL

The server pings every 4 s, and closes the socket if no pong comes in 12 s. In `AlSocket`, the
reader task sends each pong. The reader can run only when the task that owns the thread
reaches an `await` that suspends.

This program connects to a fake server that pings every 1 s. The server reports how late each
pong was. The tick then blocks the thread with `time.sleep`:

```python
# rt_block.py (fragment: `url` is a fake game server that pings every 1 s
# and sends an event `pong_ms` with the delay of each pong)
async def main(url: str) -> None:
    sock = await AlSocket.connect(url)
    t0 = time.monotonic()
    sock.on("pong_ms", lambda ms: print(f"{time.monotonic() - t0:4.1f} s: pong was {ms} ms late"))
    await asyncio.sleep(1.5)  # a good wait: the reader runs during it
    print(f"{time.monotonic() - t0:4.1f} s: the tick blocks for 1.5 s (time.sleep)")
    time.sleep(1.5)  # a BAD wait: the thread, and thus the loop, stops here
    print(f"{time.monotonic() - t0:4.1f} s: the tick gives the thread back")
    await asyncio.sleep(1.2)
    await sock.close()
```

It prints (the ms values can differ a little):

```text
 1.0 s: pong was 1 ms late
 1.5 s: the tick blocks for 1.5 s (time.sleep)
 3.0 s: the tick gives the thread back
 3.0 s: pong was 999 ms late
 3.0 s: pong was 1 ms late
 4.0 s: pong was 1 ms late
```

The ping of second 2 waited in the kernel buffer for 1 s. When the thread came back, one
`select` returned both pings, and the reader answered them in one step. On the live server,
a block of 12 s or more closes the connection. A slow `def` handler, a large JSON parse or a
long path search in the tick has the same effect as `time.sleep`.

```text
 one thread: MainThread
 +---------------------------------------------------------------------+
 | epoll_wait(timeout) -> socket readable / timer due / self-pipe byte |
 |        |                                                            |
 |        v                                                            |
 | ready queue: [read_ready] [reader step] [tick step] [timer] ...     |
 |        |  run each one to its end, one at a time                    |
 |        v                                                            |
 | reader step: parse frames, send "3", call def handlers              |
 | tick step:   read World, emit, then await (= give the thread back)  |
 +---------------------------------------------------------------------+
   asyncio_0..N: thread pool, only for blocking calls (getaddrinfo, to_thread)
```

</div>

<div data-lang="go">

In Go, you write blocking code: `conn.Read`, `time.Sleep`, a receive from a channel. The
runtime makes that code concurrent. To understand Go's async model, you must know what the
runtime does when your goroutine blocks. This chapter shows the machine. The next chapters
use it.

#### G, M and P

The Go scheduler has three kinds of objects. Their names come from the runtime source
(`runtime/runtime2.go`).

| Name | What it is | How many |
|---|---|---|
| **G** | A goroutine: a stack, a saved program counter and a state. | As many as you start. Each stack starts small (2 KB, adjusted from the average since Go 1.19) and grows. |
| **M** | A "machine": one operating-system thread. | As many as necessary. Most of them are idle. |
| **P** | A "processor": the right to run Go code. Each P has its own run queue. | Exactly `GOMAXPROCS`. |

An M must hold a P to run a G. Thus `GOMAXPROCS` is the number of goroutines that run Go code
at the same moment. The default is the number of CPUs (`runtime.NumCPU()`). Go 1.25 also reads
the CPU limit of a Linux container. Go 1.22, the course pin, does not.

```text
                          global run queue: [G G]
                                   |
      P0                  P1                  P2                  P3
   runnext: G7         runnext: -          runnext: -          runnext: -
   local:  [G9 G4]     local:  [G12]       local:  []          local:  []
      |                   |                   |                   |
      M0 runs G1          M3 runs G24         M1 runs G5          (idle: no M)

   netpoller (epoll)   G34 waits until fd 7 can be read     (readLoop)
   timers of each P    G1 sleeps until now + 100 ms          (your tick)
   sysmon (an M without a P): preempts long Gs, takes Ps from syscalls, polls the network
```

#### The order of the scheduler

When a G stops (it blocks, ends, or the runtime preempts it), its M calls the scheduler to find the next
G. In Go 1.22, `findRunnable` in `runtime/proc.go` looks in this order:

1. The timers of this P. A timer that expired makes its goroutine runnable.
2. The global run queue, one time in 61 calls. This keeps the global queue fair.
3. `runnext`, then the local run queue of this P. The local queue holds 256 Gs.
4. The global run queue.
5. The netpoller, without a wait. It returns the goroutines whose sockets are ready.
6. **Work stealing.** It tries the other Ps in random order, 4 rounds. It takes half of the
   run queue of a P that has work.
7. If all of this finds nothing, the M releases its P. One M then waits in the netpoller
   until a socket is ready or the next timer expires.

`runnext` is a slot for one G. When a goroutine wakes another one, for example with a send on
a channel, the woken G goes into `runnext`. It runs next on the same P, so the data that the
first G wrote is still in the cache of that CPU.

#### The netpoller: how `conn.Read` blocks without a thread

`readLoop` in `alsocket` calls `s.conn.Read`. Below it, the Go `net` package keeps each socket
in non-blocking mode. The read follows these steps:

1. The `net` package calls the `read` system call. No data is there, so the kernel returns
   `EAGAIN` at once.
2. The `net` package calls `runtime_pollWait`. The runtime parks the goroutine: it saves the
   G, marks it "waiting", and does not put it in a queue.
3. The M calls the scheduler and runs a different G. The thread is not blocked.
4. When bytes arrive, the kernel marks the socket ready in **epoll** (Linux). Go registered
   each socket in epoll when it opened it. macOS and BSD use **kqueue**. Windows uses an I/O
   completion port (**IOCP**).
5. An M calls `netpoll`. This occurs in the scheduler (steps 5 and 7 of the list above), and
   in `sysmon` when nothing polled for 10 ms. `netpoll` returns the parked Gs, and the
   runtime puts them in a run queue.
6. Later, an M runs the G. The G does the `read` again, and now it gets the bytes.

Thus a goroutine that waits for the network costs only its stack. This program starts 1,000
goroutines that wait in `conn.Read`, then 100 goroutines that wait in a raw system call:

```go
// threads: 1,000 goroutines that wait in conn.Read use few OS threads.
// 100 goroutines that wait in a raw blocking syscall use about 100 threads.
// Linux only: it reads the thread count from /proc/self/status.
package main

import (
	"fmt"
	"net"
	"os"
	"runtime"
	"strings"
	"syscall"
	"time"
)

// threads returns the number of OS threads of this process.
func threads() string {
	b, _ := os.ReadFile("/proc/self/status")
	for _, line := range strings.Split(string(b), "\n") {
		if strings.HasPrefix(line, "Threads:") {
			return strings.TrimSpace(strings.TrimPrefix(line, "Threads:"))
		}
	}
	return "?"
}

func main() {
	fmt.Println("GOMAXPROCS:", runtime.GOMAXPROCS(0), "NumCPU:", runtime.NumCPU())
	fmt.Println("at start:  goroutines", runtime.NumGoroutine(), "threads", threads())

	// A TCP server on loopback that accepts and then never writes.
	ln, _ := net.Listen("tcp", "127.0.0.1:0")
	go func() {
		for {
			c, err := ln.Accept()
			if err != nil {
				return
			}
			_ = c // keep it open; send nothing
		}
	}()
	// 1,000 clients. Each one blocks in Read: the netpoller parks the
	// goroutine, and its thread goes back to run other goroutines.
	for i := 0; i < 1000; i++ {
		c, err := net.Dial("tcp", ln.Addr().String())
		if err != nil {
			panic(err)
		}
		go func() {
			buf := make([]byte, 1)
			c.Read(buf) // never returns in this demo
		}()
	}
	time.Sleep(500 * time.Millisecond)
	fmt.Println("1000 Reads: goroutines", runtime.NumGoroutine(), "threads", threads())

	// 100 goroutines in a blocking syscall that the netpoller does not know.
	// Each one holds its OS thread. sysmon takes the P away from it, and the
	// runtime starts a new thread to run the other goroutines.
	for i := 0; i < 100; i++ {
		go func() {
			ts := syscall.Timespec{Sec: 2}
			syscall.Nanosleep(&ts, nil)
		}()
	}
	time.Sleep(500 * time.Millisecond)
	fmt.Println("100 syscalls: goroutines", runtime.NumGoroutine(), "threads", threads())
}
```

On a machine with 4 CPUs, it prints this. The thread counts can differ a little from run to
run.

```text
GOMAXPROCS: 4 NumCPU: 4
at start:  goroutines 1 threads 5
1000 Reads: goroutines 1002 threads 7
100 syscalls: goroutines 1101 threads 103
```

#### System calls and the handoff of the P

Some calls block in the kernel, and the netpoller cannot help. Examples are a read from a
regular file, a DNS lookup through the C library, and `syscall.Nanosleep` above. For these, the runtime uses a
**handoff**:

1. Before the call, the G marks its P as "in a system call" (`entersyscall`).
2. The thread blocks in the kernel, with the G on it.
3. `sysmon` sees the P in this state for at least 20 µs. It takes the P away.
4. The runtime gives the P to another M, or starts a new M. Go code continues on the other
   Gs.
5. When the call returns, the G tries to get a P again. If none is free, the G goes to the
   global run queue, and its M sleeps.

This is why the last line above shows 103 threads. The handoff keeps your program alive, but
each blocked call holds a thread. For an AL client this is rare: almost all of its waits are
network waits, timers and channels.

#### Preemption: where a switch can occur

Go scheduling is **preemptive**. You cannot count on a goroutine to run without a pause.
A switch can occur at these points:

- **At each block:** a channel operation, a `select`, a locked mutex, `time.Sleep`, network
  I/O. The goroutine parks itself.
- **At a function call.** The entry of most functions checks the stack size. The runtime uses
  this check to ask a goroutine to stop.
- **At almost any instruction, since Go 1.14.** `sysmon` marks each G that ran for more than
  10 ms. If the G does not stop at a function call, the runtime sends a signal (`SIGURG` on
  Unix) to its thread. The signal handler saves the state of the G and switches to the
  scheduler. This is **asynchronous preemption**.

Before Go 1.14, a loop without function calls could hold its P forever. This program shows
the difference with one P:

```go
// preempt: one P, one goroutine in a tight loop with no function calls.
// Since Go 1.14 the runtime stops it with a signal (async preemption), so
// the ticker goroutine still runs. With GODEBUG=asyncpreemptoff=1 it can't.
package main

import (
	"fmt"
	"runtime"
	"time"
)

func main() {
	runtime.GOMAXPROCS(1) // one P: only one goroutine runs at a time
	start := time.Now()
	go func() {
		for i := 0; ; i++ { // no calls, no channel ops: no cooperative switch point
		}
	}()
	for i := 1; i <= 3; i++ {
		time.Sleep(100 * time.Millisecond) // main needs the P back to continue
		fmt.Printf("tick %d after %v\n", i, time.Since(start).Round(10*time.Millisecond))
	}
}
```

With Go 1.22, it prints this (the times can differ by some ms):

```text
tick 1 after 120ms
tick 2 after 220ms
tick 3 after 330ms
```

Each tick is about 10 ms late: the time slice of the loop. With
`GODEBUG=asyncpreemptoff=1`, the program prints nothing and never ends.

The result for you: two goroutines that use the same variable can interleave at any
instruction, also on one CPU. [Async 7](#guide-async-7-shared-state) builds on this.

#### The goroutines of a running AL bot

A course program such as `cmd/farm` has these goroutines while it plays:

| Goroutine | Started by | What it does | Where it usually waits |
|---|---|---|---|
| main | the runtime | Your tick loop: `time.Sleep(tick)`, `f.Tick()`, each `Request`. | `[sleep]`, or `[select]` in a wait for a reply |
| `readLoop` | `alsocket.Connect` | Reads each frame, sends each pong, puts each event on a channel. | `[IO wait]` in the netpoller |
| `dispatchLoop` | `alsocket.Connect` | Takes each event from the channel and runs the handlers and waiters. | `[select]` on its two channels |
| `timeoutLoop` | `coder/websocket` | Closes the connection when the `ctx` of a `Read` or `Write` ends. | `[select]` |
| signal goroutines | `os/signal`, and the `go func` in `cmd/farm` | Wait for Ctrl-C, cancel the `ctx`, print `stopping`. | on a channel |

The runtime also has its own goroutines (the garbage collector, the finalizer). The threads
are a few more than `GOMAXPROCS`, and they are not tied to these goroutines. Each thread runs
whichever goroutine the scheduler gives it. Thus "the thread of the dispatcher" does not
exist in Go. Only "the dispatch goroutine" exists.

</div>

<div data-lang="csharp">

.NET has no event loop that your code must share. It has the **thread pool**: a set of
operating-system threads that run small work items. Your `async` code becomes many work
items. Each one runs on whichever pool thread is free. The facts here are for .NET 8.

#### The threads of a running client

This program connects a `ClientWebSocket` to a small server in the same process. It receives
three frames. Then it lists the threads of the process by their Linux names.

```csharp
// threads: which threads run an async WebSocket client in .NET 8 on Linux.
using System.Net;
using System.Net.WebSockets;
using System.Text;

// A small WebSocket server in the same process. It sends "2" (an Engine.IO
// ping) three times, 300 ms apart.
var listener = new HttpListener();
listener.Prefixes.Add("http://localhost:5005/");
listener.Start();
_ = Task.Run(async () =>
{
    var ctx = await listener.GetContextAsync();
    var ws = (await ctx.AcceptWebSocketAsync(null)).WebSocket;
    for (var i = 0; i < 3; i++)
    {
        await Task.Delay(300);
        await ws.SendAsync("2"u8.ToArray(), WebSocketMessageType.Text, true, default);
    }
});

Log("Main starts");
var client = new ClientWebSocket();
await client.ConnectAsync(new Uri("ws://localhost:5005/"), default);
Log("after await ConnectAsync");
var buffer = new byte[16];
for (var i = 0; i < 3; i++)
{
    // The thread waits for nothing here: ReceiveAsync returns a pending task,
    // and the code below runs later, when the socket engine sees data.
    var r = await client.ReceiveAsync(buffer, default);
    Log($"received \"{Encoding.UTF8.GetString(buffer, 0, r.Count)}\"");
}

// Each thread of this process, by its Linux name (15 characters at most).
var names = Directory.GetDirectories("/proc/self/task")
    .Select(t => File.ReadAllText(Path.Combine(t, "comm")).Trim())
    .GroupBy(n => n).OrderBy(g => g.Key);
Console.WriteLine($"{Environment.ProcessorCount} CPUs; threads of this process:");
foreach (var g in names) Console.WriteLine($"  {g.Count()} x {g.Key}");

static void Log(string what) =>
    Console.WriteLine($"thread {Environment.CurrentManagedThreadId,2} (pool: {Thread.CurrentThread.IsThreadPoolThread,-5}) {what}");
```

Output on Linux in Docker (the thread ids and the count of workers can differ):

```text
thread  1 (pool: False) Main starts
thread  5 (pool: True ) after await ConnectAsync
thread  8 (pool: True ) received "2"
thread  5 (pool: True ) received "2"
thread  7 (pool: True ) received "2"
4 CPUs; threads of this process:
  1 x .NET Debugger
  1 x .NET DebugPipe
  1 x .NET EventPipe
  1 x .NET Finalizer
  1 x .NET SigHandler
  1 x .NET Sockets
  1 x .NET SynchManag
  1 x .NET Tiered Com
  1 x .NET Timer
  1 x .NET TP Gate
  4 x .NET TP Worker
  1 x dotnet
```

Look at the first lines. `Main` starts on thread 1, the main thread. After the first `await`,
the same method continues on thread 5, a pool thread. Each `await` that must wait can move the
method to another thread. The method is one piece of code, but no one thread owns it.

These are the threads that matter for a bot:

| Thread (Linux name) | What it does |
|---|---|
| `dotnet` (the main thread) | Runs `Main` until its first real wait. Then it blocks until the `Task` of `Main` ends. |
| `.NET TP Worker` | The workers of the thread pool. They run your code, your handlers and each continuation. |
| `.NET TP Gate` | The gate thread. Every 500 ms it checks if the workers make progress, and adds a worker if not. |
| `.NET Sockets` | The socket engine. It waits in `epoll_wait` for all sockets of the process. |
| `.NET Timer` | Waits for the next timer: `Task.Delay`, `CancellationTokenSource` timeouts, `PeriodicTimer`. |
| `.NET SigHandler` | Receives signals such as SIGINT and SIGTERM, for `Console.CancelKeyPress` and `PosixSignalRegistration`. |
| `.NET Finalizer` | Runs finalizers after a garbage collection. [Async 6](#guide-async-6-cancellation-timeouts-and-errors) shows why it matters for async code. |

The other threads serve the debugger, diagnostics (`EventPipe`) and the JIT (`Tiered Com` is
the tiered compilation worker). They do not run your code.

#### The thread pool: queues and workers

A worker runs a loop: take a work item, run it, take the next one. A work item is a `Task` or
a small object with an `Execute` method. The pool keeps two kinds of queues:

- **One global queue** (first in, first out). Work from a thread that is not a pool thread goes
  here, for example the work of the socket engine and of the timer thread.
- **One local queue for each worker.** Work that a pool thread queues goes to its own local
  queue. The worker takes from its own queue first, newest first. An idle worker steals from
  the other queues, oldest first.

```text
                        global queue  ──────────────┐
  .NET Sockets  ──queue──►  [ ][ ][ ]               │
  .NET Timer    ──queue──►                          ▼
                                       ┌── worker 1: local [ ][ ] ──► runs MoveNext()
                                       ├── worker 2: local [ ]    ──► runs a handler
                                       └── worker 3: local        ──► steals, or waits
  .NET TP Gate: every 500 ms, "did anything leave the queues?" If not: add a worker.
```

The pool starts with few threads, and it creates them as it needs them. The **minimum** is the
count of CPUs (`ThreadPool.GetMinThreads`). Below the minimum, the pool adds a worker at once
when work arrives. Above it, two mechanisms decide:

- **Hill climbing.** The pool measures the throughput (completed items per second) at different
  thread counts. It keeps the count that gives the best throughput. This works well for CPU
  work that does not block.
- **Starvation detection.** The gate thread checks every 500 ms. If items wait and no worker
  took an item in that time, it adds one worker.

A blocked worker is a lost worker. The pool cannot tell `Thread.Sleep(5000)` from 5 s of
useful work. This program shows the difference that it makes. It blocks 20 workers, then asks
when a short item can run:

```csharp
// pool: the size of the thread pool, and how fast it grows when all of its
// threads block. Run: pool sleep  (Thread.Sleep)  or  pool result  (.Result)
using System.Diagnostics;

ThreadPool.GetMinThreads(out var minWorker, out var minIo);
ThreadPool.GetMaxThreads(out var maxWorker, out var maxIo);
Console.WriteLine($"CPUs {Environment.ProcessorCount}; min threads {minWorker} worker, {minIo} I/O; max {maxWorker} worker, {maxIo} I/O");

var mode = args.Length > 0 ? args[0] : "sleep";
var clock = Stopwatch.StartNew();
// 20 work items that each block a pool thread for 5 s.
for (var i = 0; i < 20; i++)
    _ = Task.Run(() =>
    {
        if (mode == "sleep") Thread.Sleep(5000);  // the pool cannot see this block
        else Task.Delay(5000).Wait();             // a sync wait on a Task: the pool sees it
    });
// A short work item, queued after them: how long until a thread is free for it?
var probe = Task.Run(() => clock.ElapsedMilliseconds);

// The main thread is not a pool thread, so it can watch while the pool is full.
while (!probe.IsCompleted)
{
    Console.WriteLine($"{clock.ElapsedMilliseconds,5} ms: {ThreadPool.ThreadCount,2} pool threads, {ThreadPool.PendingWorkItemCount,2} items wait");
    Thread.Sleep(250);
}
Console.WriteLine($"the short item started after {probe.Result} ms");
```

Output with `docker run --cpus 2` (shortened; the times differ a little from run to run):

```text
$ pool sleep
CPUs 2; min threads 2 worker, 1 I/O; max 32767 worker, 1000 I/O
    5 ms:  2 pool threads, 19 items wait
 1004 ms:  3 pool threads, 18 items wait
 2008 ms:  4 pool threads, 17 items wait
 4014 ms:  7 pool threads, 14 items wait
 8022 ms: 11 pool threads,  5 items wait
the short item started after 10004 ms

$ pool result
CPUs 2; min threads 2 worker, 1 I/O; max 32767 worker, 1000 I/O
    1 ms:  2 pool threads, 19 items wait
  253 ms:  9 pool threads, 12 items wait
 1006 ms: 15 pool threads,  6 items wait
 2010 ms: 20 pool threads,  1 items wait
the short item started after 2056 ms
```

With `Thread.Sleep`, the pool adds about one thread for each 500 ms to 1 s. The short item
waits 10 s. In a bot, that item can be the continuation that sends a pong, and the server
closes the socket after 12 s. With `.Wait()` on a `Task`, the pool knows that the thread
blocks. The .NET 8 pool then adds threads much faster. That is a repair, not a license:
each extra thread costs memory, and the short item still waits 2 s.

#### How socket I/O completes

`await client.ReceiveAsync(...)` does not keep a thread in a wait. On Linux, it goes like this:

1. The worker tries the `recv` system call at once. If data is there, the call completes
   synchronously, and the method continues on the same thread.
2. If no data is there, the socket engine records the operation. `ReceiveAsync` returns an
   incomplete task. The method returns to the worker, and the worker takes the next item.
3. The `.NET Sockets` thread waits in `epoll_wait` for all sockets of the process. When data
   arrives, the kernel wakes it.
4. The socket engine does not run your code on its own thread. It queues a work item to the
   pool.
5. A worker runs the item. It reads the data, completes the task, and runs the rest of your
   method.

The count of engine threads on x64 is the CPU count / 30, at least 1. The environment variable
`DOTNET_SYSTEM_NET_SOCKETS_INLINE_COMPLETIONS=1` makes the engine run continuations on its own
thread. Do not use it for a bot: a slow continuation then stops all sockets.

On Windows, the operating system does the I/O itself (overlapped I/O). It puts each completion
in an **I/O completion port** (IOCP). In .NET 8, the pool has poller threads, named
`.NET ThreadPool IO`, that call `GetQueuedCompletionStatusEx`. They also queue the
continuation to the workers. Thus your code runs on a worker on both systems. On Linux, the
"I/O threads" of `GetMinThreads` have no role for sockets.

A timer works the same way. The `.NET Timer` thread waits for the next due time. Then it
queues the due timers to the pool, and a worker completes the `Task.Delay` task.

#### Preemptive threads, sequential methods

Pool threads are operating-system threads. The kernel can stop each one at any instruction and
run another. Thus two pieces of your code on two workers can run **in parallel**, at the same
instant, on two cores.

One `async` method is different. It runs one step at a time, in order. A step ends at an
`await` whose task is not complete. The next step starts only after that task completes. Two
steps of the same method never overlap.

So inside one method, think "sequential, but the thread can change at each `await`". Between
two methods that run at the same time, think "real threads, real races".

This is the picture of a running course bot. Each box is a chain of steps that the pool runs.
No box owns a thread.

```text
  .NET Sockets (epoll)                     .NET Timer
        │ frame ready                          │ 100 ms passed
        ▼                                      ▼
 ┌─ ReadLoop (Task.Run) ───────┐        ┌─ Farm: tick loop (Main) ─────────┐
 │ await ReceiveTextAsync      │        │ await Task.Delay(100)            │
 │ "2"  -> await SendRawAsync  │        │ await farmer.TickAsync()         │
 │ "42" -> Channel.TryWrite ───┼──┐     │   lock (Gate) { copy state }     │
 └─────────────────────────────┘  │     │   await RequestAsync("attack")   │
                                  ▼     └──────────────────▲───────────────┘
 ┌─ Dispatch (Task.Run) ─────────────┐                     │ waiter completes
 │ await foreach (ReadAllAsync)      │                     │ (on another worker)
 │ Deliver: handlers, then waiters ──┼─────────────────────┘
 │ handlers: lock (Gate) { update }  │
 └───────────────────────────────────┘
```

The reader and the dispatcher are separate on purpose. A pong is one `SendAsync` in the reader.
A slow handler delays the dispatcher, but not the reader. The channel between them has no
limit, so the reader never waits for the dispatcher.

</div>

<div data-lang="rust">

Rust has `async` and `.await` in the language, but no runtime in the standard library. The
language gives you the `Future` trait and a compiler that turns an `async fn` into a value that
implements it. Something else must call that value until it completes. In the course, that
something is **Tokio 1.40**. This chapter shows what Tokio starts, which thread runs which part
of an AL bot, and how the threads sleep and wake.

#### What `#[tokio::main]` makes

`#[tokio::main]` is a macro. It changes your `async fn main` into a plain `fn main` that
builds a runtime and gives your future to it. The result is about this (a fragment):

```rust
// fragment: about what the macro makes
fn main() {
    let body = async { /* the body of your async fn main */ };
    tokio::runtime::Builder::new_multi_thread()
        .enable_all() // the I/O driver and the timer
        .build()
        .expect("Failed building the Runtime")
        .block_on(body) // runs `body` on THIS thread until it is done
}
```

Two facts follow from this code, and the rest of the chapter depends on them:

- **The future of `main` runs on the main thread.** `block_on` polls it there. It is not a
  task on a worker thread, and no worker can take it.
- **Each `tokio::spawn` makes a task** that the worker threads run. A task is a future that
  the runtime owns, in a heap allocation, with a state word and a queue link.

This small program shows it. It prints the thread that runs each part:

```rust
// Which thread runs what, under #[tokio::main] (the multi-thread runtime).
use std::thread;

fn here() -> String {
    // The name and id of the OS thread that runs this line.
    let t = thread::current();
    format!("{} {:?}", t.name().unwrap_or("?"), t.id())
}

#[tokio::main]
async fn main() {
    // The future of main runs on the main thread (Runtime::block_on).
    println!("main future:   {}", here());
    // A spawned task runs on a worker thread.
    let task = tokio::spawn(async { here() }).await.unwrap();
    println!("spawned task:  {task}");
    // spawn_blocking runs the closure on the blocking pool.
    let blocking = tokio::task::spawn_blocking(here).await.unwrap();
    println!("spawn_blocking: {blocking}");
    let workers = tokio::runtime::Handle::current().metrics().num_workers();
    println!("workers: {workers} (one per CPU core)");
}
```

On a machine with 4 cores, it prints this (the thread ids can differ):

```text
main future:   main ThreadId(1)
spawned task:  tokio-runtime-worker ThreadId(5)
spawn_blocking: tokio-runtime-worker ThreadId(6)
workers: 4 (one per CPU core)
```

Note that the workers and the blocking threads have the same default name. Only the id tells
them apart.

#### The threads of a running AL bot

When `farm` plays, these threads exist:

| Thread | How many | What runs on it in the course |
|---|---|---|
| `main` | 1 | The future of `main`: `Bot::connect`, the session loop, and each `farmer.tick()`. |
| worker (`tokio-runtime-worker`) | one per CPU core | The three tasks of `AlSocket` (reader, writer, dispatcher), the Ctrl-C task, the connection tasks of `reqwest`. |
| blocking pool (same name) | 0 to 512, made on demand | DNS lookups. `TcpStream::connect` with a host name calls `getaddrinfo` there. |

The number of workers comes from `std::thread::available_parallelism()`, or from the
environment variable `TOKIO_WORKER_THREADS`. In a container with a limit of 1 CPU, you get 1
worker. Then the reader, the writer and the dispatcher share one thread.

A blocking thread that has no work for 10 s ends. There is no separate timer thread and no
separate I/O thread. The workers run the timer and the I/O driver themselves, as you see
below.

#### One worker, step by step

Each worker has a **local run queue** of 256 tasks and one extra place, the **LIFO slot**. All
workers share one **inject queue**. A worker repeats this loop:

1. Take the next task. Usually it comes from the LIFO slot, then from the local queue. From
   time to time, the worker reads the inject queue first, so that the inject queue never
   starves. Tokio 1.40 tunes this interval from the measured time of each poll.
2. Poll the task once. A poll runs the code of the task until it returns `Ready` or `Pending`.
3. After the poll, run the task in the LIFO slot, if there is one. At most 3 of these run in a
   row.
4. After each 61 tasks, check the I/O driver and the timer without sleep (the
   `event_interval`).
5. If no task is ready, try to **steal** half of the local queue of another worker.
6. If it finds nothing, **park**: sleep until something wakes the thread.

Parking is where the operating system enters. One parked worker takes the **driver**. The
driver is the I/O reactor and the timer wheel together. That worker sleeps in the system call
of the reactor, with a timeout of the next timer. The other parked workers sleep on a condition
variable.

```text
                 inject queue (tasks woken from outside the workers)
                        |              |
        +---------------v--+       +---v--------------+
        | worker 0         |       | worker 1         |
        |  LIFO slot [ ]   | steal |  LIFO slot [ ]   |
        |  local [t t t ]  |<----->|  local [t ]      |
        +--------+---------+       +--------+---------+
                 | parks with the driver    | parks on a condvar
                 v                          v
        mio: epoll_wait(timeout = next timer)   (kqueue on macOS, IOCP on Windows)
                 |
        the kernel: the TCP socket to the game server has bytes
```

#### The reactor: mio

Tokio uses the crate **mio** for the system calls. On Linux, mio uses `epoll`. On macOS and
the BSDs, it uses `kqueue`. On Windows, it uses IOCP. All three answer one question: "which of
these sockets can I read or write now?"

A Tokio `TcpStream` is a socket in non-blocking mode that the reactor knows. A read on it either
returns bytes at once, or says "not now". On "not now", Tokio stores the waker of the current
task in the record of that socket, and the task returns `Pending`. Later, `epoll_wait`
reports the socket as readable. The driver then calls `wake()` on the stored waker. Chapter
[Async 3](#guide-async-3-the-unit-of-async-work) explains wakers in detail.

The timer works in the same way. Each `tokio::time::sleep` is an entry in a **timing wheel**
with 6 levels of 64 slots and a resolution of 1 ms. When the driver runs, it fires the entries
that are due and wakes their tasks.

#### What wakes a sleeping worker

A worker sleeps until one of these occurs:

- **A socket becomes ready.** The worker that holds the driver returns from `epoll_wait`.
- **A timer is due.** The timeout of `epoll_wait` ends.
- **Another thread schedules a task.** For example, the main thread calls `tokio::spawn`, or
  a waker fires on a thread that is not a worker. The task goes to the inject queue, and Tokio
  unparks one worker.

#### Cooperative, with a budget

Tokio is **cooperative**. A worker switches to another task only when the current poll returns.
A poll returns only at its end, or at an `.await` that is not ready. There is no timer interrupt and no forced
switch. A task that runs a long loop without such an `.await` holds its worker for the whole
loop.

This program shows the cost. A task named "pong" wants to run every 100 ms. Another task
calls `std::thread::sleep` for 1 s, which blocks the thread and not only the task:

```rust
// A task that blocks its thread holds back the other tasks on that thread.
// "pong" wants to run every 100 ms. "handler" blocks the thread for 1 s.
use std::time::{Duration, Instant};

async fn demo(label: &str) {
    let start = Instant::now();
    let pong = tokio::spawn(async move {
        for _ in 0..4 {
            tokio::time::sleep(Duration::from_millis(100)).await;
            println!("  pong at {:>4} ms", start.elapsed().as_millis());
        }
    });
    tokio::time::sleep(Duration::from_millis(150)).await;
    // WRONG on purpose: std::thread::sleep blocks the OS thread, not only this task.
    tokio::spawn(async { std::thread::sleep(Duration::from_secs(1)) });
    pong.await.unwrap();
    println!("{label}: done at {} ms", start.elapsed().as_millis());
}

fn main() {
    // One thread: the blocked handler stops pong too.
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    println!("current_thread runtime:");
    rt.block_on(demo("current_thread"));
    // Two workers: another worker runs pong.
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build().unwrap();
    println!("multi_thread runtime, 2 workers:");
    rt.block_on(demo("multi_thread"));
}
```

The output (the ms values can differ by a few):

```text
current_thread runtime:
  pong at  101 ms
  pong at 1156 ms
  pong at 1260 ms
  pong at 1362 ms
current_thread: done at 1362 ms
multi_thread runtime, 2 workers:
  pong at  101 ms
  pong at  203 ms
  pong at  305 ms
  pong at  406 ms
multi_thread: done at 407 ms
```

With one thread, the second pong is about 1 s late. In AL, a pong that is 12 s late ends the
connection. With two workers, the free worker runs pong. Thus the multi-thread runtime hides a
blocked worker, but only while another worker is free. With 1 CPU, it hides nothing.

Tokio adds one more protection: the **cooperative budget**. Each time a worker polls a task,
the task gets 128 units. Each operation on a Tokio resource (a channel receive, a socket read, a
timer) uses one unit. When the budget is empty, the next such operation returns `Pending`, even
if it is ready, and wakes the task again at once. Thus a loop that always finds a ready message
still gives the thread back after 128 operations. The budget cannot help with code that does not
use Tokio resources, for example a long A* search.

This program shows the budget on a `current_thread` runtime, where only a yield lets another
task run. A dispatcher task finds 300 events ready in its channel:

```rust
// Cooperative budget: a task that always finds a ready message still yields.
// Tokio gives each task a budget of 128 operations for each poll.
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

#[tokio::main(flavor = "current_thread")] // one thread: only a yield lets "other" run
async fn main() {
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel();
    for i in 0..300 {
        tx.send(i).unwrap(); // 300 events wait in the channel
    }
    drop(tx);
    let count = Arc::new(AtomicUsize::new(0));

    let c = count.clone();
    let dispatcher = tokio::spawn(async move {
        // Each recv() is ready at once. Without a budget, this loop would
        // never give the thread back until the channel is empty.
        while let Some(_event) = rx.recv().await {
            c.fetch_add(1, Ordering::SeqCst);
        }
    });
    let c = count.clone();
    let other = tokio::spawn(async move {
        println!("other task runs; the dispatcher took {} events", c.load(Ordering::SeqCst));
    });
    dispatcher.await.unwrap();
    other.await.unwrap();
    println!("the dispatcher took all {} events", count.load(Ordering::SeqCst));
}
```

It prints:

```text
other task runs; the dispatcher took 128 events
the dispatcher took all 300 events
```

The dispatcher never reached an `.await` that was not ready. The budget alone made it yield
after 128 events.

#### The AL picture

In a running `farm`, the main thread runs the tick. The workers run the reader, the writer and
the dispatcher of `AlSocket`. These parts run **in parallel**, on different OS threads. A
handler and the tick can touch the `World` at the same instant. That is why the course puts
each shared state behind a lock ([Async 7](#guide-async-7-shared-state)).

The pong path has four steps. The worker with the driver wakes the reader. The reader puts
`"3"` on a channel. The channel wakes the writer. The writer sends. No step waits for a
handler or for the tick.

</div>

<div data-lang="java">

Java has no event loop for your code. It has threads, and in Java 21 it has two kinds of them. Everything else in this lecture (futures, timeouts, `AlSocket`) sits on top of these two kinds. Thus this chapter starts with the threads, not with an API.

#### Platform threads

A **platform thread** is a thin wrapper around one operating-system thread. `new Thread(...)`, `Thread.ofPlatform()`, the `main` thread and every thread of a classic thread pool are platform threads. The kernel schedules them. It is **preemptive**: the kernel can stop a platform thread after any machine instruction and run another one. On a machine with 4 cores, 4 platform threads run at the same moment, in parallel.

A platform thread is expensive. It has a native stack (often 1 MB of reserved address space), a kernel object, and a kernel context switch for each switch. A few thousand of them are fine. A hundred thousand are not.

When a platform thread blocks, for example in `Thread.sleep` or in `future.get()`, the kernel takes it off the CPU. The thread uses no CPU, but it still exists, with its full stack, until the call returns.

#### Virtual threads

A **virtual thread** (final in Java 21, JEP 444) is a `java.lang.Thread` that the JVM schedules, not the kernel. It has two parts:

- A **continuation**: the stack frames of the virtual thread, as an object in the heap. The JVM can stop a continuation at a point, keep its frames, and continue it later.
- A **scheduler**: a `ForkJoinPool` that is only for virtual threads. It is not the common pool. It works in FIFO mode. Its parallelism is the number of cores by default (`-Djdk.virtualThreadScheduler.parallelism` changes it).

The platform threads of that pool are the **carriers**. Their names are `ForkJoinPool-1-worker-1`, `-2`, and so on. To run a virtual thread, the scheduler **mounts** its continuation on a free carrier. The carrier then executes the frames of the virtual thread as its own.

The important event is a blocking call. Assume a virtual thread calls `Thread.sleep`, `BlockingQueue.take`, `CompletableFuture.get`, `ReentrantLock.lock` or a read on a socket. The JDK code of these calls does not block the carrier. It calls `LockSupport.park`, which, on a virtual thread, **unmounts** the continuation. The frames stay in the heap, and the carrier is free for the next virtual thread in the queue.

The wait ends with an `unpark`, the end of the sleep, or data on the socket. Then the JDK gives the continuation back to the scheduler. A free carrier mounts it, maybe a different one, and the blocking call returns.

```text
 virtual threads (heap objects)        scheduler: ForkJoinPool-1 (FIFO)       carriers (OS threads)
 +---------------------+               +------------------------------+       +--------------------+
 | vt-0  frames: run() |--- mount ---> | queue of runnable vthreads   | ----> | worker-1: runs vt-0|
 | vt-1  parked (sleep)|               +------------------------------+       | worker-2: runs vt-2|
 | vt-2  frames: ...   |  <-- unmount at park(): frames stay in the heap,       | worker-3: idle     |
 +---------------------+      the carrier takes the next vthread              +--------------------+
```

This program shows the mount, the unmount and the cost:

```java
// Carriers.java: a virtual thread runs on a carrier (a platform thread of the scheduler).
// At a blocking call it unmounts; later it mounts again, maybe on another carrier.
// Run: java Carriers.java
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public class Carriers {
    public static void main(String[] args) throws Exception {
        System.out.println("main:   " + Thread.currentThread());

        // toString of a virtual thread shows "@<carrier>" while it is mounted.
        List<Thread> threads = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            threads.add(Thread.ofVirtual().name("vt-" + i).start(() -> {
                System.out.println("before: " + Thread.currentThread());
                try { Thread.sleep(100); } catch (InterruptedException e) { return; } // unmounts here
                System.out.println("after:  " + Thread.currentThread());
            }));
        }
        for (Thread t : threads) t.join();

        // 100,000 virtual threads that each block for 1 s: they need only a few carriers.
        Instant start = Instant.now();
        List<Thread> many = new ArrayList<>();
        for (int i = 0; i < 100_000; i++) {
            many.add(Thread.startVirtualThread(() -> {
                try { Thread.sleep(1000); } catch (InterruptedException e) { /* end */ }
            }));
        }
        for (Thread t : many) t.join();
        System.out.println("100000 sleeps of 1 s took " + Duration.between(start, Instant.now()).toMillis() / 100 * 100 + " ms (about)");
        System.out.println("platform threads now: " + Thread.getAllStackTraces().size());
    }
}
```

On a 4-core container (the carriers and the order can differ):

```text
main:   Thread[#1,main,5,main]
before: VirtualThread[#22,vt-0]/runnable@ForkJoinPool-1-worker-1
before: VirtualThread[#25,vt-2]/runnable@ForkJoinPool-1-worker-3
before: VirtualThread[#24,vt-1]/runnable@ForkJoinPool-1-worker-2
after:  VirtualThread[#25,vt-2]/runnable@ForkJoinPool-1-worker-1
after:  VirtualThread[#24,vt-1]/runnable@ForkJoinPool-1-worker-2
after:  VirtualThread[#22,vt-0]/runnable@ForkJoinPool-1-worker-4
100000 sleeps of 1 s took 1300 ms (about)
platform threads now: 11
```

`vt-2` started on `worker-3` and continued on `worker-1`. 100,000 threads slept at the same time, but the JVM had only 11 platform threads. `Thread.getAllStackTraces()` does not list virtual threads.

#### Preemptive or cooperative?

Both, at two levels. Keep the two levels apart:

- **Between virtual threads on one carrier, the switch is cooperative.** A virtual thread leaves its carrier only at a blocking call. Java 21 does not time-slice virtual threads. A virtual thread in a long CPU loop keeps its carrier until the loop ends.
- **Between OS threads, the switch is preemptive.** Each carrier is an OS thread. Thus your virtual thread runs in parallel with the other carriers, the `main` thread and the threads of the HTTP client.

For shared memory, only the second level matters. Code on a virtual thread has the same data races as code on a platform thread. Never treat virtual threads as "single-threaded, like JavaScript".

There is one exception to the unmount rule: **pinning**. In Java 21, a virtual thread cannot unmount while it is inside a `synchronized` block or method, or inside a native frame. A blocking call there blocks the carrier too. Chapter [Async 4](#guide-async-4-what-await-does) shows this in a program.

#### How the wait for I/O works

The kernel tells the JVM when a socket has data. On Linux it uses `epoll`, on macOS `kqueue`. Two parts of the JDK use this:

- **`java.net.http.HttpClient`** has its own thread, `HttpClient-1-SelectorManager`. It runs a `java.nio.channels.Selector` loop over all sockets of that client. When a socket has data, it gives the work to the executor of the client. The default executor is a cached pool of platform threads, `HttpClient-1-Worker-N`. `AlSocket` uses this path.
- **Blocking socket calls on a virtual thread** (`Socket.getInputStream().read()`, for example) use a JDK poller. The virtual thread parks; the poller unparks it when the socket is ready. The course does not use this path.

#### The threads of a running AL bot

This program connects the course `AlSocket` to a small fake server, then lists each thread:

```java
// BotThreads.java: connect the course AlSocket to a fake server, then list each thread.
// FakeAl is a test helper of the checks (a WebSocket and Socket.IO server in one class).
import albot.AlSocket;
import java.util.List;
import java.util.TreeSet;

public class BotThreads {
    public static void main(String[] args) throws Exception {
        var server = new FakeAl();
        server.serve(List.of("sleep:300", "42[\"welcome\",{}]", "sleep:300", "42[\"hit\",{}]", "sleep:300"));
        AlSocket sock = AlSocket.connect(server.url());
        sock.waitFor("welcome").get();
        sock.on("hit", d -> System.out.println("handler on: " + Thread.currentThread()));
        Thread.sleep(600);
        System.out.println("main on:    " + Thread.currentThread());
        var names = new TreeSet<String>();
        for (Thread t : Thread.getAllStackTraces().keySet()) names.add(t.getName() + (t.isDaemon() ? " (daemon)" : ""));
        names.forEach(n -> System.out.println("  " + n));
    }
}
```

```text
handler on: VirtualThread[#29,alsocket-dispatch]/runnable@ForkJoinPool-1-worker-1
main on:    Thread[#1,main,5,main]
  Common-Cleaner (daemon)
  CompletableFutureDelayScheduler (daemon)
  Finalizer (daemon)
  ForkJoinPool-1-worker-1 (daemon)
  ForkJoinPool-1-worker-2 (daemon)
  ForkJoinPool.commonPool-worker-1 (daemon)
  HttpClient-1-SelectorManager (daemon)
  HttpClient-1-Worker-0 (daemon)
  HttpClient-1-Worker-1 (daemon)
  HttpClient-1-Worker-2 (daemon)
  Notification Thread (daemon)
  Reference Handler (daemon)
  Signal Dispatcher (daemon)
  fake-reader (daemon)
  fake-server (daemon)
  main
```

The two `fake-*` threads belong to the fake server. The others are the threads of every Java AL bot:

| Thread | Kind | What it does for the bot |
|---|---|---|
| `main` | platform | Your program: login, handshake, the tick loop. It blocks in `Thread.sleep` and `get()`. |
| `HttpClient-1-SelectorManager` | platform | The `epoll` loop of the HTTP client. It reads the bytes of the WebSocket. |
| `HttpClient-1-Worker-N` | platform | Calls the `WebSocket.Listener` methods of `AlSocket`: `onText`, the pong, the queue. (The first calls can come on a common-pool thread.) |
| `alsocket-dispatch` | **virtual** | Takes each event from the queue and runs your handlers. Not in the list above, because it is virtual. |
| `ForkJoinPool-1-worker-N` | platform | The carriers of the virtual threads. |
| `ForkJoinPool.commonPool-worker-N` | platform | Runs `thenApplyAsync` stages, for example the last stage of each `waitFor`. |
| `CompletableFutureDelayScheduler` | platform | The timer of `orTimeout`: it fails each waiter at its timeout. |
| the rest | platform | The JVM itself: references, finalizers, signals (Ctrl-C). |

So code runs in at least four places at the same time: `main`, a listener thread, the dispatcher, and the common pool. The ping of the server arrives on a listener thread. That thread does not wait for your handlers, so a slow handler cannot hold back a pong. The rest of this lecture is about how these threads hand work to each other.

</div>

## Async 3: The unit of async work

Each language has a type for "work that is not done yet". Your code holds it, gives it to other
code, and waits for it. This chapter shows that type, its states, and how to make one by hand.
An `AlSocket` waiter is exactly that: a value that one part of the code completes when the
reply arrives.

<div data-lang="js ts">

#### A promise is a result, not the work

The unit of async work in JavaScript is the **`Promise`**. A promise is an object that holds a
result that is not there yet. It is not the work itself. The work is whatever will call
`resolve` or `reject` later: a timer, a socket event, a pool thread. You cannot run, pause or
stop a promise. You can only read its result when it comes.

A promise has three states:

```text
               resolve(value)
   pending ───────────────────> fulfilled (has a value)
      │
      └──────────────────────> rejected  (has a reason, usually an Error)
               reject(error)

   fulfilled and rejected together are "settled". A promise settles one time only.
```

A promise also keeps a list of **reactions**: the callbacks of `then`, `catch`, `finally` and
`await`. When it settles, it puts one promise job for each reaction on the microtask queue. If
you add a reaction to a promise that is already settled, the job goes on the queue at once. A
reaction never runs inside the `then` call. It always runs later, from the microtask queue.

#### Eager: the executor runs at once

`new Promise(executor)` calls `executor(resolve, reject)` immediately, before the constructor
returns. Any work that the executor starts is already running when you get the promise. An
async function is eager in the same way: its body runs at the call, up to its first `await`.

```js
// states.mjs: the three states of a promise, and an executor that runs at once.
import { inspect } from "node:util";

const pending = new Promise(() => {});           // nothing ever settles it
const fulfilled = Promise.resolve({ x: 1 });
const rejected = Promise.reject("no reply");
rejected.catch(() => {});                         // handled, so Node.js does not stop

console.log(inspect(pending));
console.log(inspect(fulfilled));
console.log(inspect(rejected));

const p = new Promise((resolve, reject) => {
  console.log("executor: runs now, inside new Promise");
  resolve("first");
  resolve("second");                              // ignored: a promise settles one time only
  reject(new Error("too late"));                  // ignored too
});
console.log("after new Promise:", inspect(p));
p.then((v) => console.log("then:", v));
console.log("end of the script");
```

```text
Promise { <pending> }
Promise { { x: 1 } }
Promise { <rejected> 'no reply' }
executor: runs now, inside new Promise
after new Promise: Promise { 'first' }
end of the script
then: first
```

Note the last two lines. `p` had its value before the call to `then`. But the callback ran
after `end of the script`. A reaction always goes through the queue.

Two rules come from "settles one time". A second `resolve` or `reject` does nothing and throws
nothing. Thus a waiter can have a timer and an event that both try to settle it, and the first
one wins. Also, you can resolve a promise with another promise, or with any object that has a `then`
method. Then the first promise follows the second: it settles when the second settles.

#### Make a promise from a callback or an event

Most of the async API of Node.js is promises already (`fs/promises`, `fetch`,
`timers/promises`). For anything else, you make the promise yourself. The pattern is always
the same: keep `resolve` and `reject`, and call one of them later from the callback.

The course's `sleep` turns a timer callback into a promise:

```js
// fragment: the sleep of the course
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
```

An event is the same, with one more step: remove the listener when the promise settles. This
standalone program makes a one-shot waiter with a timeout, from an `EventTarget`. It is the
same shape as the waiter of `AlSocket`. It also shows why the waiter must exist before you
send.

```js
// oneshot.mjs: a promise made from an event, with a timeout. Same shape as AlSocket's waiter.
const server = new EventTarget(); // stands in for the socket

function waitFor(name, timeoutMs) {
  return new Promise((resolve, reject) => {
    const onEvent = (ev) => { done(); resolve(ev.detail); };   // exit 1: the event
    const timer = setTimeout(() => {                           // exit 2: the timeout
      done();
      reject(new Error(`timed out waiting for "${name}"`));
    }, timeoutMs);
    const done = () => { clearTimeout(timer); server.removeEventListener(name, onEvent); };
    server.addEventListener(name, onEvent);                    // registered NOW, in the executor
  });
}

// A fake server that answers 5 ms after each send.
function send(place) {
  setTimeout(() => server.dispatchEvent(new CustomEvent("game_response", { detail: { place } })), 5);
}

// Right: start the wait, send, then await.
const reply = waitFor("game_response", 100);
send("attack");
console.log("1.", await reply);

// Wrong: send, wait for something else (Budget can sleep), then start the wait.
send("attack");
await new Promise((r) => setTimeout(r, 20)); // the reply arrives during this sleep
try {
  await waitFor("game_response", 100);
} catch (err) {
  console.log("2.", err.message);            // nobody was there to receive it
}
```

```text
1. { place: 'attack' }
2. timed out waiting for "game_response"
```

Node.js 22 also has `Promise.withResolvers()`. It returns `{ promise, resolve, reject }`, so you
can keep the two functions outside an executor. It is the same object, with less nesting.
`events.once(emitter, name)` from `node:events` makes a promise from an `EventEmitter` event.

#### The waiter of AlSocket

This is `waitFor` from `course/js/albot/alsocket.js`, exactly as it is:

```js
// fragment: course/js/albot/alsocket.js
  waitFor(event, pred = () => true, timeoutMs = 10_000) {
    return new Promise((resolve, reject) => {
      if (this.#closed) return reject(new Error("socket is closed"));
      const w = {
        event,
        pred,
        resolve: (data) => { done(); resolve(data); },
        reject: (err) => { done(); reject(err); },
      };
      const timer = setTimeout(() => w.reject(new Error(`timed out waiting for "${event}"`)), timeoutMs);
      const done = () => { clearTimeout(timer); this.#waiters.delete(w); };
      this.#waiters.add(w);
      this.#subscribed(event);
    });
  }
```

Read it with the model of this chapter:

- The executor runs inside `waitFor`. Thus the waiter is in `#waiters` when `waitFor` returns.
  The caller can then `emit`, and a fast reply finds the waiter.
- The waiter object `w` is the bridge. It holds the `resolve` and `reject` of this one promise.
  Other code (`#deliver`, `#shutdown`) calls them later, from other tasks.
- The promise has three exits: `#deliver` calls `w.resolve` on a match, the timer calls
  `w.reject`, and `#shutdown` calls `w.reject` when the socket closes. Each exit calls `done()`
  first. `done()` clears the timer and removes the waiter, so the other exits cannot fire.
- If two exits fire anyway, the promise ignores the second one. Settles one time.
- On a closed socket, the promise is born rejected. [Async 6](#guide-async-6-cancellation-timeouts-and-errors) shows the cost of
  that.

#### TypeScript: what `Promise<T>` adds

TypeScript gives the promise a type parameter: `Promise<T>` is "a result of type `T`, later".
The TS `AlSocket` has the same code, with types:

```ts
// fragment: course/ts/albot/alsocket.ts
  waitFor<T = unknown>(event: string, pred: (data: T) => boolean = () => true, timeoutMs = 10_000): Promise<T> {
```

Inside, it calls `resolve(data as T)`. That `as T` is the whole check. The data is JSON from
the server, and nothing compares it with `T` at run time.

Node.js 22.18 runs `.ts` files by **type stripping**: it removes the types and runs the rest. So
`waitFor<Welcome>("welcome")` gives a `Promise<Welcome>`, but the value inside is whatever the
server sent. If the server changes a field, your types are wrong and nothing says so. Check the
fields that you depend on, or parse the payload with a schema library at the socket edge.

Two more types are useful. `Promise<never>` is a promise that can only reject. The TS
`enterGame` uses it for `failed`, the promise of each login failure. `Awaited<T>` is the type
that `await` gives for `T`, with nested promises removed.

</div>

<div data-lang="python">

`asyncio` has three types for work that is not done. They are often mixed up, because `await`
accepts all three. Each one has a different job.

#### Coroutine, Future, Task

| Type | What it is | Who runs it | Starts |
|---|---|---|---|
| coroutine | A paused function frame: the code of an `async def`, its local variables, its position. | Whoever calls its `send` method. | Never by itself. |
| `asyncio.Future` | A box for one result or one exception, plus a list of callbacks. It has no code. | Nobody. Someone calls `set_result` or `set_exception`. | It is "started" when someone has the work to complete it. |
| `asyncio.Task` | A Future that drives one coroutine. Its result is the return value of the coroutine. | The loop, one step at a time. | At the next iteration of the loop after `create_task`. |

A Task **is** a Future (`Task` is a subclass of `Future`). Thus you can `await` a Task, add a
done callback to it, or cancel it, as with any Future.

#### A call to an `async def` runs nothing

`attack()` on an `async def attack` does not run the body. It makes a coroutine object in the
state `CORO_CREATED`. The body runs only when something calls `send` on it. A Task does that.
An `await` in another coroutine does that too, through its own Task.

```python
# unit_lazy.py: a call to an async def runs no code. A Task starts it, later.
import asyncio
import inspect


async def attack() -> str:
    print("   attack: the body runs now")
    await asyncio.sleep(0)
    return "done"


async def main() -> None:
    coro = attack()  # no output: this only makes a coroutine object
    print("1.", coro.__class__.__name__, inspect.getcoroutinestate(coro))
    task = asyncio.create_task(coro)  # wraps it and schedules its first step
    print("2. task made:", task.done(), "- the body has not run yet")
    await asyncio.sleep(0)  # give the loop one pass
    print("3.", inspect.getcoroutinestate(coro), "- it waits at its own await")
    print("4.", await task, inspect.getcoroutinestate(coro))
    attack()  # made and dropped: Python warns when the object is collected


asyncio.run(main())
```

It prints:

```text
1. coroutine CORO_CREATED
2. task made: False - the body has not run yet
   attack: the body runs now
3. CORO_SUSPENDED - it waits at its own await
4. done CORO_CLOSED
unit_lazy.py:20: RuntimeWarning: coroutine 'attack' was never awaited
  attack()  # made and dropped: Python warns when the object is collected
RuntimeWarning: Enable tracemalloc to get the object allocation traceback
```

Two facts come from this output:

- **A coroutine is lazy.** A forgotten `await` is not an error. Python only warns when the
  garbage collector frees the coroutine. In a bot, `sock.emit("attack", ...)` without
  `await` sends nothing, and the warning can come much later.
- **A Task is lazy by one iteration.** `create_task` puts the first step in the ready queue.
  The body starts when the current step gives the thread back.

Python 3.12 adds an option: `asyncio.eager_task_factory`. With it, `create_task` runs the first
step at once, inside the call, up to the first `await` that suspends:

```python
# unit_eager.py: Python 3.12 can run the first step of a task at once.
import asyncio


async def work(n: int) -> None:
    print(f"   work {n}: first step")
    await asyncio.sleep(0)
    print(f"   work {n}: second step")


async def main() -> None:
    t1 = asyncio.create_task(work(1))
    print("after create_task(work(1))")
    asyncio.get_running_loop().set_task_factory(asyncio.eager_task_factory)  # 3.12+
    t2 = asyncio.create_task(work(2))
    print("after create_task(work(2)) with the eager factory")
    await asyncio.gather(t1, t2)


asyncio.run(main())
```

It prints:

```text
after create_task(work(1))
   work 2: first step
after create_task(work(2)) with the eager factory
   work 1: first step
   work 2: second step
   work 1: second step
```

The course does not use the eager factory. All text here assumes the default.

#### The states of a Future

A Future has three states: `PENDING`, `FINISHED` (with a result or an exception) and
`CANCELLED`. It leaves `PENDING` one time only. A second `set_result` raises
`InvalidStateError`.

When a Future leaves `PENDING`, it does not call its callbacks. It gives each one to
`loop.call_soon`. Thus a callback never runs inside `set_result`. It runs in a later step of
the loop.

You make a Future by hand with `loop.create_future()`. You give it to the code that waits, and
you complete it from a callback: a timer, a socket event, a handler. This is the bridge from
"something happens later" to "a coroutine waits for it":

```python
# unit_future.py: a Future made by hand, completed by a callback.
# This is the pattern of every waiter in AlSocket.
import asyncio


def reply_later(seconds: float, value: str) -> asyncio.Future[str]:
    """A plain def: it makes the future NOW and returns it."""
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[str] = loop.create_future()
    # Some later event (here a timer; in AlSocket, a frame) completes it.
    loop.call_later(seconds, fut.set_result, value)
    return fut


async def main() -> None:
    fut = reply_later(0.1, "game_response")
    print("1.", fut)  # pending
    print("2. result:", await fut)  # the task sleeps until set_result runs
    print("3.", fut)  # finished

    failed = asyncio.get_running_loop().create_future()
    failed.set_exception(ConnectionError("socket closed"))
    print("4.", failed)
    try:
        failed.result()  # result() raises the stored exception
    except ConnectionError as err:
        print("5. result() raised", repr(err))

    gone = asyncio.get_running_loop().create_future()
    gone.cancel()
    print("6.", gone, gone.cancelled())
    try:
        gone.set_result(1)  # a future completes only one time
    except asyncio.InvalidStateError as err:
        print("7.", type(err).__name__, err)


asyncio.run(main())
```

It prints:

```text
1. <Future pending>
2. result: game_response
3. <Future finished result='game_response'>
4. <Future finished exception=ConnectionError('socket closed')>
5. result() raised ConnectionError('socket closed')
6. <Future cancelled> True
7. InvalidStateError invalid state
```

#### The waiter of `AlSocket`

`AlSocket.wait_for` is this pattern, with a timer and a predicate:

```python
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        # Mark the error of the future as read when the future ends. The
        # coroutine below raises it again for the code that awaits. Code that
        # never awaits (an emit failed first) then gets no "Future exception
        # was never retrieved" log.
        fut.add_done_callback(_retrieve)
        if self._closed:
            fut.set_exception(ConnectionError("socket is closed"))
        else:
            waiter = (event, pred or (lambda _: True), fut)
            self._waiters.append(waiter)
```

Then it starts a timer (`loop.call_later(timeout, expire)`) that sets `TimeoutError` on the
future. It adds a second done callback, `cleanup`, that cancels the timer and removes the
waiter. The first done callback, `_retrieve`, is the subject of
[Cancellation, timeouts and errors](#guide-async-6-cancellation-timeouts-and-errors). Last,
it returns a coroutine:

```python
        async def result() -> Any:
            return await fut

        return result()
```

`wait_for` is a plain `def` on purpose. If it were an `async def`, the call would only make a
coroutine, and nothing would register. The waiter would exist only at the `await`, after the
`emit`. As a plain `def`, it registers the future and starts the timer during the call. The
coroutine that it returns is lazy, but it contains no work. It only waits for a future that
already exists.

This fragment follows one waiter. It reads the private list `_waiters` only to show it:

```python
# unit_waiter.py (fragment: `url` is a fake game server that answers
# `attack` with `player`, then `game_response`, after 50 ms)
async def main(url: str) -> None:
    sock = await AlSocket.connect(url)
    sock.on("welcome", lambda _: None)  # take the kept welcome; not needed here
    reply = sock.wait_for("game_response", lambda d: d.get("place") == "attack", timeout=2)
    name, _, fut = sock._waiters[0]
    here = os.path.dirname(os.path.abspath(__file__)) + "/"
    print("1. registered:", name, repr(fut).replace(here, ""))
    print("2. reply is a", type(reply).__name__)
    await sock.emit("attack", {"id": "goo1"})
    print("3. sent:", repr(fut).replace(here, ""))
    data = await reply
    print("4. resumed:", fut._state, data["response"])
    print("5. waiters left:", len(sock._waiters))
    await sock.close()
```

It prints:

```text
1. registered: game_response <Future pending cb=[_retrieve() at alsocket.py:264, AlSocket.wait_for.<locals>.cleanup() at alsocket.py:201]>
2. reply is a coroutine
3. sent: <Future pending cb=[_retrieve() at alsocket.py:264, AlSocket.wait_for.<locals>.cleanup() at alsocket.py:201]>
4. resumed: FINISHED data
5. waiters left: 0
```

At line 5 the list is already empty. The future had three callbacks: `_retrieve`, `cleanup`,
then the wake-up of the main task, which `await` added. `set_result` gave all three to
`call_soon`, in that order. Thus `cleanup` ran before `main` continued.

`enter_game` in `bot.py` uses the same tool for a different case. Its future `outcome` has
several possible ends: `start`, `game_error`, `disconnect_reason`, the local `disconnect`.
Each handler checks `outcome.done()` first, because only the first end counts.

#### Who keeps a task alive

The loop does not keep your tasks. `asyncio` records each task in a `weakref.WeakSet`. That
set is what `asyncio.all_tasks()` reads. A weak reference does not keep an object alive.

While a task waits, these things hold it:

- **The ready queue**, while a step of the task is in it.
- **The future that it waits for.** The wake-up callback of the task is in the callback list
  of that future. If a timer or a socket holds that future, the task stays alive.
- **Your variables.**

If none of these holds the task, the garbage collector can free it before it ends:

```python
# unit_weak.py: the loop keeps only a weak reference to a task.
import asyncio
import gc


async def wait_forever(name: str) -> None:
    fut = asyncio.get_running_loop().create_future()  # only this task knows fut
    try:
        await fut
    finally:
        print(f"   {name}: finally runs (the coroutine is closed)")


async def main() -> None:
    keep = asyncio.create_task(wait_forever("kept"))  # a strong reference
    asyncio.create_task(wait_forever("dropped"))  # no reference: only a weak one
    await asyncio.sleep(0)  # both run to their await
    print("tasks before gc:", len(asyncio.all_tasks()))
    gc.collect()  # the cycle task -> coroutine -> future -> task is garbage
    print("tasks after gc: ", len(asyncio.all_tasks()))
    keep.cancel()


asyncio.run(main())
```

It prints:

```text
tasks before gc: 3
   dropped: finally runs (the coroutine is closed)
Task was destroyed but it is pending!
task: <Task pending name='Task-3' coro=<wait_forever() done, defined at unit_weak.py:6> wait_for=<Future pending cb=[Task.task_wakeup()]>>
tasks after gc:  2
   kept: finally runs (the coroutine is closed)
```

The dropped task waited for a future that only it knew. Task, coroutine and future made a
cycle with no reference from outside. The collector freed the whole cycle.

`AlSocket` keeps its reader in `self._reader`, so the reader is safe. It keeps the task of
each `async def` handler in a set, `_handler_tasks`, until the task ends. An earlier version
gave the handler to `asyncio.ensure_future` and kept no reference. Such a task survived while
it waited for a timer or a socket, because the loop holds those. It could disappear if it
waited for a future that nothing else held.

Keep a reference to each task that you make. Put it in a set and remove it in a done callback, or use a `TaskGroup` (see
[Several things at the same time](#guide-async-5-several-things-at-the-same-time)).

</div>

<div data-lang="go">

In JavaScript, the unit of async work is a value: a `Promise`. In Go, the unit is a running
function: a **goroutine**. A goroutine has no result and no handle. A result must travel on a
**channel**. Thus Go splits the "future" of other languages in two parts: a goroutine does the
work, and a channel carries the result.

#### A goroutine: start, states, end

The statement `go f(x)` evaluates `f` and `x` at once. Then it makes a new G and puts it in
the run queue of the current P. The goroutine is **eager**: it is runnable at once, and the
statement returns without a wait. Nothing can stop the new goroutine from the outside.

A G is always in one of these states. A goroutine dump shows the state of each one in
brackets, with the reason for a wait (Async 9 shows how to get one).

```text
               go f()
                 |
                 v
   +-------> runnable  ---- an M with a P takes it ---->  running
   |             ^                                          |  |  |
   |             |        preempted (10 ms, or a signal)    |  |  |
   |             +------------------------------------------+  |  |
   |                                                            |  |
   |   woken: a channel op, a timer,      parks: chan, select,  |  |
   |   the netpoller, an Unlock           Sleep, I/O, Lock      |  |
   +--------------------------------  waiting  <----------------+  |
                                    [chan receive] [select]        |
                                    [IO wait] [sleep]              |
                                                                   v
                                          f returns, or panics -> dead
```

A goroutine ends only when its function returns, or when it calls `runtime.Goexit`. A panic
that nothing recovers ends the whole program (see
[Async 6](#guide-async-6-cancellation-timeouts-and-errors)). There is no `Kill`, no `Cancel`
and no `Join`. To know that a goroutine ended, you need a signal from it: a channel, a
`sync.WaitGroup`, or an `errgroup.Group`.

#### Channels: the other half

A channel is a queue with a lock, inside the runtime. It has a capacity. Each operation on
it can park the goroutine that does it.

- **Unbuffered** (`make(chan T)`): a send waits until a receiver takes the value. The two
  goroutines meet. The value goes directly from the stack of the sender to the receiver.
- **Buffered** (`make(chan T, n)`): a send waits only when the buffer has `n` values. A
  receive waits only when the buffer is empty.
- **`close(ch)`**: no more values come. Each receive after the buffer is empty returns at
  once, with the zero value and `ok == false`. A close wakes **all** receivers. This makes a
  closed channel a broadcast signal. `alsocket` uses this: `close(s.done)` wakes each waiter.
- **A nil channel** blocks forever, on send and on receive. In a `select`, a nil channel is a
  case that never fires. You can set a channel variable to `nil` to stop a case.

| Operation | nil channel | open channel | closed channel |
|---|---|---|---|
| `ch <- v` | blocks forever | blocks until there is room or a receiver | panics |
| `<-ch` | blocks forever | blocks until there is a value | returns the zero value at once |
| `close(ch)` | panics | closes it | panics |

Only the sender closes a channel, and only one time. In `alsocket`, `readLoop` is the only
sender on `s.events`. Thus `readLoop` closes it.

#### A future made by hand

You can make a "future" from a goroutine and a channel of capacity 1. The function below
starts the work at once and returns a function that waits for the result:

```go
// future: a "future" in Go is a goroutine plus a channel of size 1.
// Async starts the work at once (eager) and returns a function that waits.
package main

import (
	"fmt"
	"time"
)

type result[T any] struct {
	v   T
	err error
}

// Async runs f on a new goroutine now. The returned function blocks until
// f returns. It keeps the result, so you can call it again. Call it from
// one goroutine only: r and got have no lock.
func Async[T any](f func() (T, error)) func() (T, error) {
	ch := make(chan result[T], 1) // size 1: the goroutine never blocks, even if nobody waits
	go func() {
		v, err := f()
		ch <- result[T]{v, err}
	}()
	var r result[T]
	var got bool
	return func() (T, error) {
		if !got {
			r, got = <-ch, true
		}
		return r.v, r.err
	}
}

func main() {
	start := time.Now()
	slow := func(name string, d time.Duration) func() (string, error) {
		return func() (string, error) { time.Sleep(d); return name, nil }
	}
	a := Async(slow("bank", 200*time.Millisecond))  // starts now
	b := Async(slow("items", 300*time.Millisecond)) // starts now too
	va, _ := a()
	vb, _ := b()
	fmt.Println(va, vb, "after", time.Since(start).Round(100*time.Millisecond))
}
```

It prints:

```text
bank items after 300ms
```

The two waits overlap, so the total is 300 ms, not 500 ms. Note the capacity of 1. With an
unbuffered channel, a goroutine whose caller never waits blocks forever on its send. That is
a goroutine leak (see [Async 9](#guide-async-9-seeing-it-run)).

#### The waiter of `AlSocket`: a channel and a registration

A reply from the server is not the result of a goroutine that you started. It is an event
that the dispatch goroutine finds later. Thus the waiter of `alsocket` has a different
shape. It is a struct in a set, with a channel of capacity 1:

```go
type waiter struct {
	name string
	pred func(json.RawMessage) bool
	ch   chan json.RawMessage // buffer of 1: a send never blocks
}
```

`Expect` makes the waiter and puts it in `s.waiters` under the lock, **before it returns**.
Then it returns a function that waits on `w.ch`. The dispatch goroutine finds the waiter
when a matching event arrives, removes it from the set, and sends the payload on `w.ch`.
This is the Go form of `new Promise(resolve => ...)`: the registration is the constructor,
and the send is `resolve`.

The program below makes the same waiter with fewer parts. It shows the three cases that the
buffer of 1 handles:

```go
// waiter: a one-shot waiter made by hand from a channel, the way alsocket's
// Expect makes one. An event source calls deliver; a goroutine waits.
package main

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

type bus struct {
	mu      sync.Mutex
	waiters map[chan string]string // channel -> event name that it waits for
}

// expect registers the waiter NOW and returns the function that waits.
func (b *bus) expect(name string) func(context.Context) (string, error) {
	ch := make(chan string, 1) // buffer of 1: deliver never blocks
	b.mu.Lock()
	b.waiters[ch] = name
	b.mu.Unlock()
	return func(ctx context.Context) (string, error) {
		select {
		case v := <-ch: // the event came
			return v, nil
		case <-ctx.Done(): // we gave up: remove the waiter
			b.mu.Lock()
			delete(b.waiters, ch)
			b.mu.Unlock()
			return "", ctx.Err()
		}
	}
}

// deliver is the "callback": the source calls it for each event.
func (b *bus) deliver(name, payload string) {
	b.mu.Lock()
	var matched []chan string
	for ch, n := range b.waiters {
		if n == name {
			matched = append(matched, ch)
			delete(b.waiters, ch) // one shot: a waiter completes one time
		}
	}
	b.mu.Unlock()
	for _, ch := range matched {
		ch <- payload // never blocks: the buffer is empty and has room for 1
	}
}

func main() {
	b := &bus{waiters: map[chan string]string{}}

	// 1. Register, then the event comes (on another goroutine), then wait.
	wait := b.expect("start")
	go b.deliver("start", `{"id":"Me"}`)
	v, err := wait(context.Background())
	fmt.Println("1:", v, err)

	// 2. The event comes BEFORE the wait: the buffer keeps it.
	wait = b.expect("start")
	b.deliver("start", `{"id":"Early"}`) // nobody receives yet; no block
	v, err = wait(context.Background())
	fmt.Println("2:", v, err)

	// 3. The wait times out first. A late deliver finds no waiter.
	wait = b.expect("start")
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	_, err = wait(ctx)
	fmt.Println("3:", errors.Is(err, context.DeadlineExceeded))
	b.deliver("start", `{"id":"Late"}`)
	fmt.Println("3: deliver returned; waiters left:", len(b.waiters))
}
```

It prints:

```text
1: {"id":"Me"} <nil>
2: {"id":"Early"} <nil>
3: true
3: deliver returned; waiters left: 0
```

Case 2 is the reason for the order "register, send, wait". The reply can arrive before your
goroutine reaches the wait. The buffer holds it. Case 3 is the reason for the capacity of 1
in `deliver`. If the waiter goes away between the match and the send, the send still does
not block the dispatcher.

`Expect` is lazy in one way and eager in another. The registration is eager: it occurs in
the call. The wait is lazy: it occurs only when you call the returned function. A promise in
JavaScript has the same split.

</div>

<div data-lang="csharp">

The unit of async work in .NET is `Task` (no result) and `Task<T>` (a result of type `T`). A
`Task` is a **promise**: an object that will hold an outcome later. It is not a thread, and
it is not code. Code that has the task can ask its state, wait for it, and attach a
continuation. Some other code completes it.

#### Two kinds of Task, one type

The same type has two uses:

- **A delegate task** holds code to run. `Task.Run(() => ...)` makes one and gives it to a
  **`TaskScheduler`**. The default scheduler, `TaskScheduler.Default`, puts it on the thread
  pool. A worker then runs the delegate.
- **A promise task** holds no code. An `async` method returns one. A
  `TaskCompletionSource` makes one. A socket operation returns one. Something else completes
  it: the end of the `async` method, a call to `SetResult`, the socket engine.

`await` does not care which kind it gets. It only waits for the outcome.

A task has these states (`task.Status`). The arrows show the normal path:

```text
 delegate task:  Created ──Start──► WaitingToRun ──► Running ──┐
                 (new Task only)    (in a queue)    (a worker) │
                                                               ├──► RanToCompletion
 promise task:   WaitingForActivation ─────────────────────────┤    Faulted  (an exception)
                 (an async method, a TCS, a socket read)       └──► Canceled (an OperationCanceledException)
```

The three end states are final. A completed task never changes again. Thus you can await it
many times, from many threads, and get the same result each time.

#### Tasks are hot

A `Task` that you get is already started. An `async` method runs on your thread, at the call,
until its first `await` that must wait. Then it returns the task. The rest of the method runs
later, without you. Nothing more is necessary to start it. `new Task(...)` makes a cold
task, but you almost never need one.

```csharp
// unit: the states of a Task, hot tasks, and a Task made by hand.

// 1. A Task from an async method is "hot": the method already runs.
var hot = WorkAsync("hot");
Console.WriteLine($"hot task returned, status {hot.Status}");
await hot;
Console.WriteLine($"after await: {hot.Status}");

// 2. A cold Task (new Task) does nothing until Start. You almost never need one.
var cold = new Task(() => Console.WriteLine("  cold task runs"));
Console.WriteLine($"cold task: {cold.Status}");
cold.Start();
await cold;

// 3. A Task by hand: TaskCompletionSource. Nothing runs; somebody completes it.
var source = new TaskCompletionSource<string>();
Console.WriteLine($"TCS task: {source.Task.Status}");
_ = Task.Run(async () => { await Task.Delay(50); source.SetResult("welcome"); });
Console.WriteLine($"TCS result: {await source.Task}, status {source.Task.Status}");

// 4. Failed and canceled are states too.
var failed = Task.FromException(new InvalidOperationException("bad"));
var canceled = Task.FromCanceled(new CancellationToken(true));
Console.WriteLine($"failed: {failed.Status}, IsFaulted {failed.IsFaulted}; canceled: {canceled.Status}");

// 5. Where an exception goes: an async method puts it in its task;
//    a plain method that returns a Task throws at the call.
var t = ThrowsAsync();                       // no exception here
Console.WriteLine($"async method: call returned, status {t.Status}");
try { _ = ThrowsNow(); } catch (Exception e) { Console.WriteLine($"plain method: threw at the call: {e.Message}"); }

// 6. ValueTask: no allocation when the result is ready at once.
Console.WriteLine($"ValueTask ready at once: IsCompleted {CachedAsync(true).IsCompleted}");
Console.WriteLine($"ValueTask result: {await CachedAsync(false)}");

static async Task WorkAsync(string name)
{
    Console.WriteLine($"  {name}: runs on the caller's thread until its first await");
    await Task.Delay(10);
    Console.WriteLine($"  {name}: continues after the await");
}

static async Task ThrowsAsync() { await Task.Yield(); throw new Exception("in the task"); }
static Task ThrowsNow() => throw new Exception("socket closed");

static async ValueTask<int> CachedAsync(bool ready)
{
    if (ready) return 42;   // no await: completes synchronously, no Task object
    await Task.Delay(10);
    return 43;
}
```

Output:

```text
  hot: runs on the caller's thread until its first await
hot task returned, status WaitingForActivation
  hot: continues after the await
after await: RanToCompletion
cold task: Created
  cold task runs
TCS task: WaitingForActivation
TCS result: welcome, status RanToCompletion
failed: Faulted, IsFaulted True; canceled: Canceled
async method: call returned, status WaitingForActivation
plain method: threw at the call: socket closed
ValueTask ready at once: IsCompleted True
ValueTask result: 43
```

Part 5 matters for `AlSocket`. `WaitForAsync` is a plain method, not `async`. Thus on a closed
socket it throws `WebSocketException` at the call, before you have a task. `RequestAsync` is
`async`, so the same exception goes into the task of `RequestAsync`.

#### ValueTask

A `Task` is an object on the heap. A method that often completes at once, without a wait,
wastes that object. `ValueTask<T>` is a struct that holds either the result or a task (or
a reusable source). For example, the `Memory<byte>` overload of `ClientWebSocket.ReceiveAsync`
returns a `ValueTask`. A read that finds data at once then costs no task object.

A `ValueTask` has rules that a `Task` does not have. Await it **one time** only. Do not await it
from two places. Do not read `.Result` before it completes. After your await, its source can
serve the next operation. If you need more, call `.AsTask()` one time and keep the
`Task`.

#### TaskCompletionSource: a Task by hand

Events from the server are not method calls that return. They arrive on the dispatcher, at
any time. To turn "the next `game_response` with `place: "attack"`" into something that you
can `await`, you need a promise that you complete yourself. `TaskCompletionSource<T>` is that
promise. It has two sides:

- `tcs.Task` is the side that you give away. Code awaits it.
- `tcs.SetResult(x)`, `SetException(e)` and `SetCanceled()` complete it. The `TrySet...` forms
  return `false` instead of an exception when the task is already complete. Thus the first
  completion wins, and later ones do nothing.

This is the waiter of `AlSocket`, from `WaitForAsync`:

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, WaitForAsync
var result = new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);
var waiter = new Waiter(name, pred ?? (_ => true), result);
lock (_lock)
{
    if (_closed) throw new WebSocketException("socket closed");
    _waiters.Add(waiter);
}
```

The waiter is in the list before `WaitForAsync` returns. The dispatcher calls
`w.Result.TrySetResult(data)` when a matching event arrives. A timer calls
`result.TrySetException(new TimeoutException(...))`. The end of the dispatcher calls
`TrySetException(new WebSocketException("socket closed"))`. Three parties race, and `TrySet`
lets the first one win.

#### RunContinuationsAsynchronously

When a task completes, it runs its continuations. By default, a continuation of `await` can
run **inline**: on the thread that completes the task, inside the call to `SetResult`. For a
waiter, that thread is the dispatcher. This program shows what inline means when the thread
that completes the task holds a lock:

```csharp
// tcs: where the code after "await tcs.Task" runs, with and without
// RunContinuationsAsynchronously. "dispatcher" plays the role of the AlSocket
// dispatcher: it completes the waiter while it holds a lock.
var gate = new object();

await Show(TaskCreationOptions.None);
await Show(TaskCreationOptions.RunContinuationsAsynchronously);

async Task Show(TaskCreationOptions options)
{
    Console.WriteLine($"--- {options}");
    var waiter = new TaskCompletionSource<int>(options);
    var user = Task.Run(async () =>
    {
        await waiter.Task;
        // Which thread are we on, and do we hold the lock of the dispatcher?
        Log($"code after await (holds the lock: {Monitor.IsEntered(gate)})");
    });
    await Task.Delay(100); // the user task now waits at its await

    var dispatcher = new Thread(() =>
    {
        lock (gate)
        {
            Log("dispatcher: TrySetResult");
            waiter.TrySetResult(1);
            Log("dispatcher: TrySetResult returned");
        }
    });
    dispatcher.Start();
    dispatcher.Join();
    await user;
}

static void Log(string what) => Console.WriteLine($"  thread {Environment.CurrentManagedThreadId,2}: {what}");
```

Output (the thread ids can differ):

```text
--- None
  thread  8: dispatcher: TrySetResult
  thread  8: code after await (holds the lock: True)
  thread  8: dispatcher: TrySetResult returned
--- RunContinuationsAsynchronously
  thread 10: dispatcher: TrySetResult
  thread 10: dispatcher: TrySetResult returned
  thread  9: code after await (holds the lock: False)
```

Without the option, the code after `await` runs on the thread that completes the task, before
`TrySetResult` returns, with the locks of that thread. In `AlSocket`, your code after `await
reply` would then run on the dispatcher thread. Your code is then the dispatcher. No later
event and no handler runs until your code reaches its next real `await`. If your code waits
for the next reply with a blocking call, it waits for itself.

With the option, `TrySetResult` only queues your continuation to the pool, and returns. The
dispatcher continues with the next waiter and the next event. Your code runs on a worker, maybe
on the same thread after the dispatcher gave it back to the pool.

The comment in `AlSocket` says it in short: your code after the await "must not run on the
dispatcher". Use this option for each `TaskCompletionSource` that a handler or a dispatcher
completes. `Bot.EnterGameAsync` does the same for its `start` signal.

The price: your code after `await reply` runs at the same time as the dispatcher, which
continues with the later events. [Async 8](#guide-async-8-alsocket-read-with-these-eyes) shows
what that means for your state.

</div>

<div data-lang="rust">

In Rust, the unit of async work is a value of a type that implements the trait
`std::future::Future`. This chapter shows that trait, and what a "poll" and a "waker" are. Then
it makes a future by hand. At the end, it shows the waiter of `AlSocket`, a future that a
channel completes.

#### The trait

This is the whole trait, from the standard library (a fragment):

```rust
// fragment: from std::future and std::task
pub trait Future {
    type Output;
    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output>;
}

pub enum Poll<T> {
    Ready(T),
    Pending,
}
```

A future is a value that someone can ask, "are you done?". `poll` answers with `Ready(value)`
or with `Pending`. That is the only operation. There is no "start", no "then", no callback list.

Three rules come with `poll`:

1. **A poll must not block.** If the result is not ready, the future arranges a wake-up and
   returns `Pending` at once.
2. **Before it returns `Pending`, a future must arrange a call of `cx.waker().wake()`** for
   the time when progress is possible. If nobody calls it, nobody polls the future
   again. The future then waits forever.
3. **After `Ready`, do not poll again.** The future of an `async fn` panics if you do.

The executor is the code that calls `poll`. In Tokio, the executor is the loop of a worker,
or `block_on` on the main thread. The reactor is the code that calls `wake`. This split is the
core of the model:

```text
  executor (worker loop)                       reactor / other code
  ----------------------                       --------------------
  poll(task) ---> future: "not ready"
                  stores cx.waker() ---------> kept by the socket, timer or channel
           <---- Pending
  runs other tasks, or parks
                                               the event occurs: waker.wake()
  task is in a queue again <------------------ (schedules the task)
  poll(task) ---> future: "ready"
           <---- Ready(value)
```

#### The `Waker` and the `Context`

A `Context` holds a reference to a `Waker`, for this one poll. A `Waker` is a pointer to the
task plus a table of functions. `wake()` calls the "schedule" function of that table.

In Tokio, the waker of a task points to the task header. A call to `wake()` puts the task in
a run queue. If the call comes from a worker thread of the same runtime, the task goes into the
LIFO slot of that worker. Otherwise, it goes into the inject queue, and Tokio unparks a worker.
The waker of the `main` future is different: it unparks the main thread.

Who calls `wake` in an AL bot:

| Future | Who calls `wake()` |
|---|---|
| a read on the WebSocket (`stream.next()`) | the I/O driver, after `epoll_wait` reports the socket |
| `tokio::time::sleep`, `timeout` | the time driver, when the entry is due |
| `oneshot::Receiver`, `mpsc::Receiver::recv` | the `send` of the other half |
| `JoinHandle` | the task, when it ends |

A wake during a poll is not lost. The task state has a bit for "notified". If a wake arrives
while the task runs, Tokio polls it again after the current poll.

#### A future by hand

This program writes a future from nothing. A helper thread plays the part of the reactor. It
sleeps, sets a flag, and calls `wake()`:

```rust
// A future made by hand. A helper thread plays the part of the reactor:
// it sets `done` and calls wake(). Then the executor polls again.
use std::future::Future;
use std::pin::Pin;
use std::sync::{Arc, Mutex};
use std::task::{Context, Poll, Waker};
use std::time::Duration;

#[derive(Default)]
struct State {
    done: bool,
    waker: Option<Waker>, // the waker of the last poll
}

struct Delay {
    state: Arc<Mutex<State>>,
    polls: u32,
}

impl Delay {
    fn new(ms: u64) -> Delay {
        let state = Arc::new(Mutex::new(State::default()));
        let s = state.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(ms));
            let mut st = s.lock().unwrap();
            st.done = true;
            println!("  helper thread: done, call wake()");
            if let Some(w) = st.waker.take() {
                w.wake(); // tells the executor: poll this task again
            }
        });
        Delay { state, polls: 0 }
    }
}

impl Future for Delay {
    type Output = u32;
    fn poll(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<u32> {
        self.polls += 1;
        let mut st = self.state.lock().unwrap();
        if st.done {
            println!("  poll {}: Ready", self.polls);
            return Poll::Ready(self.polls);
        }
        // Not done: keep the waker, so that the helper can wake us. Keep the
        // newest one: the task can move to another worker between polls.
        st.waker = Some(cx.waker().clone());
        println!("  poll {}: Pending", self.polls);
        Poll::Pending
    }
}

#[tokio::main]
async fn main() {
    let polls = Delay::new(50).await;
    println!("ready after {polls} polls");
}
```

It prints:

```text
  poll 1: Pending
  helper thread: done, call wake()
  poll 2: Ready
ready after 2 polls
```

The executor polled two times. Between the polls, the main thread slept. Nothing checked the
flag in a loop. The check and the store of the waker occur under one lock. Without that lock,
the helper could set `done` after the check but before the store. Then nobody would call the
new waker.

#### Lazy: no poll, no work

A future does nothing until something polls it. A call to an `async fn` runs **no line** of
its body. It only builds the state machine and returns it. This program polls by hand to show
it:

```rust
// A future does nothing until something polls it. We poll by hand here.
use std::future::Future;
use std::pin::pin;
use std::task::{Context, Poll};

use futures_util::task::noop_waker;

async fn body() -> u32 {
    println!("  the body runs");
    42
}

fn main() {
    let fut = body(); // makes the state machine; runs no line of body()
    println!("made the future");
    let mut fut = pin!(fut); // poll needs Pin<&mut Self>
    let waker = noop_waker(); // a waker that does nothing (we poll by hand)
    let mut cx = Context::from_waker(&waker);
    println!("poll 1");
    match fut.as_mut().poll(&mut cx) {
        Poll::Ready(v) => println!("Ready({v})"),
        Poll::Pending => println!("Pending"),
    }
}
```

It prints:

```text
made the future
poll 1
  the body runs
Ready(42)
```

Compare JavaScript, where `new Promise(fn)` runs `fn` at once. A Rust future is a plan, not an
action in progress. If you drop it before the first poll, its body never runs.

To start the work without a wait, use `tokio::spawn`. It gives the future to the runtime, and a
worker polls it soon. The returned `JoinHandle` is itself a future, for the result.

#### The lifecycle of a Tokio task

```text
  spawn ──> Idle+Notified ──poll──> Running ──Pending──> Idle (waits for a wake)
                 ^                     |                   |
                 └──────── wake ───────┼───────────────────┘
                                       └──Ready / panic──> Complete ──> JoinHandle gets it
  abort(), or the runtime shuts down ──> Cancelled: the future is dropped at its next poll
```

#### Make a future from an event: `oneshot`

An AL client must turn "an event arrives on the socket" into "a future completes". In Rust, the
tool for that is `tokio::sync::oneshot`. A `oneshot::channel()` gives two halves. The
`Receiver` is a future. The `Sender` has `send(value)`, which stores the value and wakes the
receiver. If the code drops the `Sender` without a send, the receiver completes with an error.

This is the waiter of `AlSocket`, in small:

```rust
// The AlSocket waiter in small: register a oneshot sender now, return a
// future for the receiver. The "dispatcher" completes it later.
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tokio::sync::oneshot;

#[derive(Default, Clone)]
struct Sock {
    waiters: Arc<Mutex<Vec<(String, oneshot::Sender<String>)>>>,
}

impl Sock {
    // A plain fn: the push runs at the call, not at the first poll.
    fn wait_for(&self, event: &str) -> impl std::future::Future<Output = Option<String>> + 'static {
        let (tx, rx) = oneshot::channel();
        self.waiters.lock().unwrap().push((event.to_string(), tx));
        async move { rx.await.ok() } // Err: the sender was dropped (socket closed)
    }
    // The dispatcher side: complete each waiter of this event.
    fn deliver(&self, event: &str, data: &str) {
        let mut ws = self.waiters.lock().unwrap();
        ws.retain(|w| !w.1.is_closed()); // drop waiters that nobody waits on
        let mut i = 0;
        while i < ws.len() {
            if ws[i].0 == event {
                let (_, tx) = ws.swap_remove(i);
                let _ = tx.send(data.to_string()); // wakes the task that awaits rx
            } else {
                i += 1;
            }
        }
    }
}

#[tokio::main]
async fn main() {
    let sock = Sock::default();
    let reply = sock.wait_for("game_response"); // 1. register
    let s = sock.clone();
    tokio::spawn(async move {
        // 2. the "server" answers fast, before main awaits
        s.deliver("game_response", "attack ok");
    });
    tokio::time::sleep(Duration::from_millis(20)).await;
    println!("reply: {:?}", reply.await); // 3. the value waits in the oneshot

    let lost = sock.wait_for("start");
    sock.waiters.lock().unwrap().clear(); // the socket closes: senders dropped
    println!("after close: {:?}", lost.await);
}
```

It prints:

```text
reply: Some("attack ok")
after close: None
```

The reply arrived before `main` reached `.await`. The value waited in the channel. This is
why the order "register, send, await" is safe.

Note the shape of `wait_for`. It is a plain `fn` that returns `impl Future`. The work that must
occur now (the push of the sender) is in the `fn` body. The work that must wait (the receive)
is in the `async move` block. If `wait_for` were an `async fn`, the push would run only at the
first poll, after your `emit`. A fast reply would then find no waiter.

The course's `AlSocket::wait_for_timeout` has exactly this shape:

```rust
        let (tx, rx) = oneshot::channel();
        let registered = {
            let mut s = self.shared.lock().unwrap();
            if !s.closed {
                s.waiters.push(Waiter {
                    event: event.to_string(),
                    pred: Box::new(pred),
                    tx,
                });
            }
            !s.closed
        };
```

Then it returns `async move { ... tokio::time::timeout(timeout, rx).await ... }`. The `'static`
in its return type means that the future borrows nothing from the socket. You can keep it, give
it to another task, or put it in a `select!`.

</div>

<div data-lang="java">

In JavaScript a `Promise` is the unit of async work. Java has two units, and you use both in an AL bot:

- **`Thread`** (platform or virtual): a sequence of code that runs. You wait for its end with `join()`.
- **`Future<T>`**, and its rich form **`CompletableFuture<T>`**: a box for a result that is not ready. You wait for the result with `get()` or `join()`.

The two are separate on purpose. A thread is "something that runs". A future is "a value that will exist". A future does not need a thread. This is the key to `AlSocket`.

#### A future is a box, not work

`new CompletableFuture<String>()` starts nothing. It makes an empty box in the heap, with no thread behind it. Any thread can later fill the box with `complete(value)` or `completeExceptionally(error)`. The first fill wins. Each later fill returns `false` and changes nothing.

A future has one of four states. Java 19 added `Future.state()`, so you can print them:

```java
// States.java: the life of a CompletableFuture that we complete by hand.
// Run: java States.java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class States {
    public static void main(String[] args) throws Exception {
        var f = new CompletableFuture<String>();          // no work, no thread: an empty box
        System.out.println("new:      " + f.state());      // Future.state() is new in Java 19
        System.out.println("complete: " + f.complete("first"));  // true: we filled the box
        System.out.println("again:    " + f.complete("second")); // false: the first result wins
        System.out.println("state:    " + f.state() + ", get() = " + f.get());

        var g = new CompletableFuture<String>();
        g.completeExceptionally(new java.io.IOException("socket closed"));
        System.out.println("failed:   " + g.state());
        try { g.get(); } catch (ExecutionException e) { System.out.println("get():    ExecutionException, cause " + e.getCause()); }
        try { g.join(); } catch (CompletionException e) { System.out.println("join():   CompletionException, cause " + e.getCause()); }

        var h = new CompletableFuture<String>();
        h.cancel(true);
        System.out.println("cancel:   " + h.state() + ", isCompletedExceptionally = " + h.isCompletedExceptionally());
        try { h.get(); } catch (java.util.concurrent.CancellationException e) { System.out.println("get():    CancellationException (no wrapper)"); }
    }
}
```

```text
new:      RUNNING
complete: true
again:    false
state:    SUCCESS, get() = first
failed:   FAILED
get():    ExecutionException, cause java.io.IOException: socket closed
join():   CompletionException, cause java.io.IOException: socket closed
cancel:   CANCELLED, isCompletedExceptionally = true
get():    CancellationException (no wrapper)
```

The state `RUNNING` is a misleading name for an empty box: nothing runs. It only means "not complete".

```text
                 complete(v)
   RUNNING  ------------------->  SUCCESS   (get() returns v)
  (empty)   -- completeExceptionally(e) -->  FAILED    (get() throws ExecutionException(e))
            ------ cancel(...) --------->  CANCELLED (get() throws CancellationException)
   each arrow happens at most once; the first one wins
```

#### Eager or lazy?

The box is neither: it has no work. The question is about the code that fills it.

- `CompletableFuture.supplyAsync(fn)` and `executor.submit(fn)` are **eager**. They give `fn` to a pool at once. The work runs whether or not anyone waits for the result.
- Whoever has the reference fills a future that you make with `new`. In `AlSocket`, that is the dispatcher thread, when the matching event arrives.

Nothing in Java is lazy in the Rust or Python sense. No `poll` and no `await` drives the work. A thread drives it.

#### Inside the box: a stack of dependents

A `CompletableFuture` holds two fields: the result, and a stack of **dependents**. A dependent is a small object for each stage that you add with `thenApply`, `whenComplete`, `handle`, and for each thread that waits in `get()`. When a thread calls `complete`, it sets the result with one compare-and-set. Then that same thread pops each dependent and runs it, or wakes its waiting thread. This detail decides which thread runs your code. Chapter [Async 4](#guide-async-4-what-await-does) uses it.

#### A future from a callback: the waiter

An AL reply is an event on the socket, not the return value of a call. To wait for it, you need a future that the event fills. This is the pattern, in about 50 lines:

```java
// MiniWaiter.java: the waiter of AlSocket, made small. A dispatcher thread takes events from
// a queue and completes the first waiter whose name matches. Nobody else completes it.
// Run: java MiniWaiter.java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;

public class MiniWaiter {
    record Event(String name, String data) {}
    record Waiter(String name, CompletableFuture<String> result) {}

    static final BlockingQueue<Event> events = new LinkedBlockingQueue<>();
    static final List<Waiter> waiters = new ArrayList<>(); // guarded by `waiters`

    // Make an empty future, register it, return it. No thread waits yet.
    static CompletableFuture<String> waitFor(String name) {
        var result = new CompletableFuture<String>();
        synchronized (waiters) { waiters.add(new Waiter(name, result)); }
        return result;
    }

    // The "server": it answers 10 ms after each emit, on another thread.
    static void emit(String name) {
        CompletableFuture.delayedExecutor(10, TimeUnit.MILLISECONDS)
                .execute(() -> events.add(new Event("game_response", "reply to " + name)));
    }

    public static void main(String[] args) throws Exception {
        Thread.ofVirtual().name("dispatch").start(() -> {
            try {
                while (true) {
                    Event ev = events.take(); // blocks; the virtual thread unmounts here
                    synchronized (waiters) {
                        var it = waiters.iterator();
                        while (it.hasNext()) {
                            Waiter w = it.next();
                            if (w.name().equals(ev.name())) { it.remove(); w.result().complete(ev.data()); break; }
                        }
                        // No waiter matched: the event is gone. Nothing keeps it.
                    }
                }
            } catch (InterruptedException e) { /* end */ }
        });

        // Right: register, then send, then block.
        var reply = waitFor("game_response");
        emit("attack");
        System.out.println("right order: " + reply.get(1, TimeUnit.SECONDS));

        // Wrong: send, then (too late) register.
        emit("heal");
        Thread.sleep(50); // stands for any delay: a GC pause, a slow line, a context switch
        try {
            waitFor("game_response").get(1, TimeUnit.SECONDS);
        } catch (TimeoutException e) {
            System.out.println("wrong order: TimeoutException, the reply came before the waiter");
        }
    }
}
```

```text
right order: reply to attack
wrong order: TimeoutException, the reply came before the waiter
```

The second case is a real race. The reply and the registration run on different threads. If the reply wins, the dispatcher finds no waiter and drops the event. The `sleep(50)` only makes the loss certain for the demo.

#### The waiter of `AlSocket`

`AlSocket.waitFor` is the same pattern, with a predicate and a timeout. The method makes the box and registers it under the lock of the socket:

```java
var result = new CompletableFuture<JsonNode>();
var waiter = new Waiter(event, pred == null ? d -> true : pred, result);
synchronized (lock) {
    if (closed) return CompletableFuture.failedFuture(new IOException("socket closed"));
    waiters.add(waiter);
}
```

Then it builds a short chain on the box, and returns the end of the chain:

```java
var future = result.orTimeout(timeout.toMillis(), TimeUnit.MILLISECONDS)
        .whenComplete((d, e) -> { synchronized (lock) { waiters.remove(waiter); } })
        .thenApplyAsync(d -> d);
```

- `orTimeout` arms a timer on `result`. If the timer fires first, it fails `result` with a `TimeoutException`. It returns `result` itself, not a new future.
- `whenComplete` adds a dependent that removes the waiter from the list, for each kind of end.
- `thenApplyAsync(d -> d)` copies the value into a new future, on a pool thread. Chapter [Async 8](#guide-async-8-alsocket-read-with-these-eyes) explains why.

The caller gets `future`, the end of the chain, not `result`. A cancel of `future` does not travel back to `result`, because a stage only reacts to the stages before it. Thus `waitFor` adds one more dependent:

```java
future.whenComplete((d, e) -> result.cancel(false)); // no effect if result is complete
```

If you cancel `future`, this cancels `result`. The `whenComplete` on `result` then removes the waiter at once, not at its timeout.

When `waitFor` returns, the waiter is in the list. Nothing waits on it yet. That is why `request` can call `waitFor`, then `emit`, then `get()`, in this order, with no race.

</div>

## Async 4: What `await` does

A wait looks like one line of code. Underneath, it stops your function, frees the thread, and
continues the function later. This chapter shows the mechanics, step by step, with one call of
the course as the example: `request` sends [`attack`](#send-attack) and waits for its
`game_response`.

<div data-lang="js ts">

#### What an async function call does

An `async function` is a function that returns a promise and can stop in the middle. A call to
it does four things:

1. Make a new promise, the **result promise** of this call.
2. Run the body synchronously, as a normal function, up to the first `await`.
3. At that `await`, save the state of the function and return the result promise.
4. Later, when the awaited value settles, continue the body from that `await`.

```js
// awaitvalue.mjs: await always gives the thread back, even for a plain value.
async function f() {
  console.log("2. f: before the await");
  await 42;                                // 42 is not a promise, and f still stops here
  console.log("5. f: after the await");
}

console.log("1. main: call f");
const p = f();                             // f runs until its first await, then returns
console.log("3. main: f returned", p);
queueMicrotask(() => console.log("6. main: a microtask queued after the call"));
console.log("4. main: end of the script");
```

```text
1. main: call f
2. f: before the await
3. main: f returned Promise { <pending> }
4. main: end of the script
5. f: after the await
6. main: a microtask queued after the call
```

Line 2 shows the eager part: the body runs inside the call. Line 5 shows that `await 42`
stopped `f`, though nothing was there to wait for. Line 6 comes after line 5, because `f`
queued its continuation first.

#### What `await x` does, step by step

The specification defines `await x` with promise operations. V8 does the same, with fast paths:

1. Turn `x` into a promise: `PromiseResolve(x)`. A native promise stays the same object. Any
   other value becomes a new promise that is already fulfilled with it.
2. Add a reaction to that promise. Its two callbacks are "continue the function with this
   value" and "continue the function by throwing this reason".
3. **Suspend** the function. Save its frame, and return to whoever called it or resumed it.
4. When the promise settles, the reaction becomes a promise job on the microtask queue.
5. The job **resumes** the function. The value of `await` is the fulfilment value. Or the
   `await` throws the reason, as a `throw` statement at that line would.

Step 3 is the reason that `await` on a value that is ready still yields. The specification
never runs the continuation inside the `await`. It always goes through the queue. This gives
one rule that you can trust: the code after an `await` never runs before the code that
follows the call. Without it, the same function would run synchronously for some values and
asynchronously for others.

#### The function as a resumable frame

A normal function keeps its locals in a stack frame, and the frame is gone when it returns. An
async function must keep its locals across a return. V8 compiles an async function as a
**generator** underneath. The locals live in registers, and at each `await` V8 copies the live
registers into a heap object, the generator object of the call. To resume, it copies them back
and jumps to the saved point.

You can see this in the bytecode. Save this as `frame.mjs`:

```js
// frame.mjs: a small async function, to read its bytecode.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function twoWaits(a) {
  const b = a + 1;      // a local that must live across the waits
  await sleep(1);
  await sleep(1);
  return b;
}
console.log(await twoWaits(1));
```

Run `node --print-bytecode --print-bytecode-filter=twoWaits frame.mjs`. These are the lines that
matter, from Node.js 22 (addresses removed):

```text
SwitchOnGeneratorState r0, [0], [2] { 0: @49, 1: @90 }   on resume: jump to point 0 or 1
InvokeIntrinsic [_AsyncFunctionEnter], r2-r3             make the result promise
AddSmi [1], [0]                                          b = a + 1 (b is in register r1)
...
InvokeIntrinsic [_AsyncFunctionAwaitUncaught], r3-r4     first await: add the reaction
SuspendGenerator r0, r0-r2, [0]                          save r0..r2 (b too), return
ResumeGenerator r0, r0-r2                                @49: restore r0..r2
InvokeIntrinsic [_GeneratorGetResumeMode], r0-r0         fulfilled? else ReThrow
...
SuspendGenerator r0, r0-r2, [1]                          second await
ResumeGenerator r0, r0-r2                                @90
...
InvokeIntrinsic [_AsyncFunctionResolve], r3-r4           return b: fulfil the result promise
```

The function has one entry and two resume points. `SuspendGenerator` is the `return` of step 3.
`ResumeGenerator` is the entry for step 5. The value `b` survives because it is in `r1`, which
is in the saved range. A whole try block is also in the frame: the handler table covers the
resume points, so a rejected `await` lands in your `catch`.

TypeScript makes the same model visible. With `--target es2015` (no native `async`), `tsc`
writes the function as a generator and a small driver:

```ts
// downlevel.ts: one async function, to see what tsc makes of it for old targets.
async function twoWaits(a: number): Promise<number> {
  const b = a + 1;
  await sleep(1);
  await sleep(1);
  return b;
}
declare function sleep(ms: number): Promise<void>;
```

The output of `tsc --target es2015` (TypeScript 5.6), shortened to the parts that matter:

```text
function twoWaits(a) {
    return __awaiter(this, void 0, void 0, function* () {
        const b = a + 1;
        yield sleep(1);
        yield sleep(1);
        return b;
    });
}
// __awaiter, inside: step(result) {
//   result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
```

Each `await` became `yield`. The driver calls `generator.next(value)` from a `then` callback.
That is steps 2 to 5 in plain JavaScript. The course targets ES2022, so `tsc` keeps native
`async`, and Node.js runs the `.ts` files with their `async` as written. In TypeScript, the
return type of an async function must be `Promise<T>`. A non-promise return type is error
TS1064.

#### How many turns does a wait cost?

Each `await` costs at least one turn of the microtask queue. Some cost more. This program counts:

```js
// ticks.mjs: how many microtask turns does each kind of wait take?
// A counter queues one microtask per turn. Each async function logs the
// turn on which it continues.
let turn = 0;
function counter(max) {
  queueMicrotask(function step() {
    turn++;
    if (turn < max) queueMicrotask(step);
  });
}
const report = (name) => console.log(`${name}: continued after turn ${turn}`);

const native = Promise.resolve(1);
const thenable = { then(resolve) { resolve(1); } }; // not a real promise

async function inner() { return native; }          // returns a promise from an async function

counter(10);
(async () => { await native; report("await native promise   "); })();
(async () => { await 1; report("await plain value       "); })();
(async () => { await thenable; report("await thenable          "); })();
(async () => { await inner(); report("await async fn (return p)"); })();
native.then(() => report("native.then             "));
```

```text
await native promise   : continued after turn 1
await plain value       : continued after turn 1
native.then             : continued after turn 1
await thenable          : continued after turn 2
await async fn (return p): continued after turn 3
```

A native promise costs one turn, the same as `then`. Since V8 7.2 (Node.js 12), `await` reuses a
native promise and does not wrap it, so it costs one turn, not three. A thenable costs one more
turn: V8 must call its `then` in a job of its own. An async function that returns a promise
costs two more: its result promise must follow the returned promise. These turns are cheap.
But they decide the order of continuations, so do not write code that depends on that order.

#### Trace: one `attack` through the course

`act.attack(id)` calls `request`. This is `request` in `course/js/albot/actions.js`:

```js
// fragment: course/js/albot/actions.js
  async request(event, payload, place = event, timeoutMs = 2000) {
    const reply = this.sock.waitFor("game_response", responseFor(place), timeoutMs);
    // Mark a failure of `reply` as handled now. If budget.emit() throws (the
    // socket is closed), we leave before `await reply`, and Node.js would stop
    // the process for its unhandled rejection. The `await reply` below still
    // gets the same rejection.
    reply.catch(() => {});
    await this.budget.emit(event, payload);
    try {
      return normalize(await reply);
    } catch (err) {
      if (String(err?.message).startsWith("timed out")) return null;
      throw err; // the socket closed: the caller must know
    }
  }
```

This program follows one call against the test server. It wraps `sock.emit` to print each send,
and adds a handler for `game_response`. Save it in `course/js`.

```js
// trace.js: follow one act.attack() call through the event loop.
import { Bot } from "./albot/bot.js";

const bot = await Bot.connect();
const { sock, world, act } = bot;
const log = (line) => console.log(line);

// Show each send. (The method is public, so we can wrap it.)
const emit = sock.emit.bind(sock);
sock.emit = (event, data) => { log(`   sock.emit("${event}")`); emit(event, data); };
// A handler for the reply, registered like the World's handlers.
sock.on("game_response", (d) => log(`   handler: game_response "${d.response}"`));

const goo = world.nearestMonster("goo");
log("1. main: call act.attack()");
const pending = act.attack(goo.id);
log("2. main: attack() returned " + String(pending));
queueMicrotask(() => log("3. microtask: main went on; attack() waits inside"));
const r = await pending;
log(`4. main: after await: response "${r?.response}", place "${r?.place}"`);
bot.close();
```

```text
downloaded G version 17478
1. main: call act.attack()
   sock.emit("attack")
2. main: attack() returned [object Promise]
3. microtask: main went on; attack() waits inside
   handler: game_response "too_far"
4. main: after await: response "too_far", place "attack"
```

The first line comes from `loadG`. Tester stands at the spawn point, so the goo is out of range
and the server answers `too_far`. Here is what happened, on one thread:

```text
TASK 1 (main code)
  attack(id) ──> request("attack", {id})          eager: the body runs now
    waitFor(...)       the executor adds waiter w to #waiters, starts its 2 s timer
    reply.catch(...)   a reaction on reply: a later rejection has a handler
    budget.emit(...)   an async function, also eager; spent() is low, so no sleep:
                       sock.emit writes 42["attack",{id}] to the socket   ("sock.emit")
                       budget.emit returns a promise that is already fulfilled
    await <that promise>   SUSPEND request; return its result promise to attack
  attack returns a pending promise                                         ("2.")
  main: await pending      SUSPEND the module code
  stack empty ──> microtasks:
    "3." runs; request resumes after the Budget await
    await reply            SUSPEND again (reply is still pending)
  queues empty ──> the loop goes to poll and sleeps in epoll_wait

TASK 2 (poll phase, about 1 ms later on localhost)
  "message" ──> #onPacket ──> #deliver("game_response", {...})
    1. handlers: the World's dispatch, Cooldowns, the trace handler        ("handler")
    2. waiters: w.pred(data) is true ──> w.resolve(data)
         done(): clear the timer, remove w;  resolve(): queue a promise job
  stack empty ──> microtasks:
    request resumes at "await reply": normalize(...), return ──> fulfil its promise
    attack's promise follows it (two more turns)
    the module code resumes at "await pending"                             ("4.")
```

Two facts come from this trace. First, `sock.emit` ran before `attack()` returned. The body of
an async function is synchronous up to the first `await` that must wait, and `Budget` had room.

Second, the handlers ran before the waiter resolved, and long before your continuation. When
line "4." runs, the World already holds the state that this reply changed. If the same TCP
read held more frames after the reply, their handlers ran too, before line "4.". So after
each `await`, read the world again.

</div>

<div data-lang="python">

The last chapter said that a Task "runs the coroutine one step at a time". This chapter shows
what a step is. The answer is old Python: a coroutine is a generator with a different name,
and `await` is `yield from` with type checks.

#### Generators: `yield` and `send`

A generator function pauses at each `yield`. The caller resumes it with `send(value)`. The
`yield` expression then has that value. When the function returns, `send` raises
`StopIteration`, and `StopIteration.value` is the return value.

A coroutine has the same machine. `coro.send(None)` runs it to its next pause. The value that
comes out of `send` is what the innermost awaitable yielded. When the coroutine returns,
`send` raises `StopIteration`.

`await x` does three things:

1. It calls `x.__await__()`, which must return an iterator. A coroutine is its own iterator.
2. It passes each value that the iterator yields **up**, out of the outermost `send`. It
   passes each value that the caller sends **down**, into the iterator.
3. When the iterator returns, the return value becomes the value of the `await` expression.

Thus a chain of coroutines (`farm` awaits `tick`, `tick` awaits `attack`, `attack` awaits
`request`, `request` awaits `reply`) is one channel. Only the innermost object yields. The
others pass the value through. If nothing in the chain yields, each `await` is an ordinary
call, and no switch occurs.

This program drives coroutines by hand, with no loop:

```python
# await_gen.py: the machine under `await`, by hand.
import asyncio
import types


# 1. A generator stops at each yield. send() resumes it with a value.
def gen():
    got = yield "first yield"
    print("   gen got", got)
    return "the return value"


g = gen()
print("1.", g.send(None))  # start: runs to the first yield
try:
    g.send(42)  # resume: `got` is 42; the generator returns
except StopIteration as stop:
    print("2. StopIteration.value =", stop.value)


# 2. An awaitable is an object whose __await__ returns an iterator.
class Ask:
    def __await__(self):
        answer = yield "Ask yields this to the driver"
        return answer


async def coro():
    x = await Ask()  # `await` = `yield from Ask().__await__()`
    return x * 2


c = coro()
print("3.", c.send(None))  # the yield of Ask comes out of c.send
try:
    c.send(21)  # the driver sends a value back in
except StopIteration as stop:
    print("4. coroutine returned", stop.value)


# 3. A real asyncio Future yields ITSELF to whoever drives the coroutine.
async def waits_for(fut):
    return await fut


loop = asyncio.new_event_loop()
fut = loop.create_future()
c2 = waits_for(fut)
out = c2.send(None)
print("5. yielded the future itself:", out is fut, "| blocking flag:", out._asyncio_future_blocking)
fut.set_result("payload")
try:
    c2.send(None)  # the driver resumes it after the future is done
except StopIteration as stop:
    print("6. coroutine returned", stop.value)
loop.close()


# 4. asyncio.sleep(0) is a bare `yield`: "run me again in the next pass".
@types.coroutine
def bare_yield():
    yield


async def polite():
    await bare_yield()
    return "after one pass"


c3 = polite()
print("7. bare yield gives", c3.send(None))
```

It prints:

```text
1. first yield
   gen got 42
2. StopIteration.value = the return value
3. Ask yields this to the driver
4. coroutine returned 42
5. yielded the future itself: True | blocking flag: True
6. coroutine returned payload
7. bare yield gives None
```

Line 5 is the key to `asyncio`. `Future.__await__` in `futures.py` is three lines:

```python
    def __await__(self):
        if not self.done():
            self._asyncio_future_blocking = True
            yield self  # This tells Task to wait for completion.
        if not self.done():
            raise RuntimeError("await wasn't used with future")
        return self.result()  # May raise too.
```

A Future that is already done does not yield. Its `await` returns the result at once, with no
switch. A pending Future yields **itself**, up through the whole chain, to the Task. The Task
then knows what its coroutine waits for.

#### The Task step

`Task.__step` in `tasks.py` is the driver. This is its core, in short (fragment; the real code
also handles cancellation and bad yields):

```python
# fragment: Task.__step of Lib/asyncio/tasks.py (3.12), shortened
def __step(self, exc=None):
    try:
        if exc is None:
            result = self._coro.send(None)  # run to the next yield
        else:
            result = self._coro.throw(exc)  # resume with an exception
    except StopIteration as stop:
        super().set_result(stop.value)  # the coroutine returned
    except BaseException as e:
        super().set_exception(e)  # the coroutine raised
    else:
        if getattr(result, "_asyncio_future_blocking", None):
            result._asyncio_future_blocking = False
            result.add_done_callback(self.__wakeup)  # wake me when it is done
            self._fut_waiter = result
        elif result is None:
            self._loop.call_soon(self.__step)  # bare yield: run again next pass
```

`__wakeup(future)` calls `future.result()`. If that raises, it calls `__step(exc)`, which
throws the exception into the coroutine, at the `await`. Else it calls `__step()`, which sends
`None`. The `await` inside the coroutine then calls `self.result()` again and gets the value.

CPython runs a C version of this class (the `_asyncio` module). That is why reprs show
`Task.task_wakeup()`. The C version follows the Python one, and the Python one is the easier
read.

#### The whole machine in 60 lines

This toy has the shape of `asyncio`: a ready queue, a timer heap, a Future that yields itself,
and a Task that steps a coroutine. It has no I/O, no cancellation and no error checks:

```python
# mini_loop.py: a toy event loop, Future and Task in 60 lines.
# The shape is the shape of asyncio (base_events.py, futures.py, tasks.py),
# without I/O, cancellation or error checks.
import heapq
import itertools
import time
from collections import deque

ready: deque = deque()  # callbacks to run in the next pass
timers: list = []  # heap of (when, seq, callback)
seq = itertools.count()  # breaks ties in the heap


def call_soon(cb, *args):
    ready.append(lambda: cb(*args))


def call_later(delay, cb, *args):
    heapq.heappush(timers, (time.monotonic() + delay, next(seq), lambda: cb(*args)))


class Future:
    def __init__(self):
        self.done, self.result, self.callbacks = False, None, []

    def set_result(self, value):
        self.done, self.result = True, value
        for cb in self.callbacks:  # never called directly: always through the queue
            call_soon(cb, self)

    def __await__(self):
        if not self.done:
            yield self  # "Task, wait for me"
        return self.result


class Task(Future):
    def __init__(self, coro):
        super().__init__()
        self.coro = coro
        call_soon(self.step)  # the first step runs in a later pass, not now

    def step(self, _fut=None):
        try:
            fut = self.coro.send(None)  # run the coroutine to its next yield
        except StopIteration as stop:
            self.set_result(stop.value)  # the coroutine returned
            return
        fut.callbacks.append(self.step)  # wake me when that future is done


def sleep(delay):
    fut = Future()
    call_later(delay, fut.set_result, None)
    return fut


def run(main_coro):
    main = Task(main_coro)
    while not main.done:  # one iteration = one "_run_once"
        timeout = 0 if ready else max(0, timers[0][0] - time.monotonic())
        time.sleep(timeout)  # asyncio: selector.select(timeout) here
        while timers and timers[0][0] <= time.monotonic():
            ready.append(heapq.heappop(timers)[2])
        for _ in range(len(ready)):  # only what is ready NOW
            ready.popleft()()
    return main.result


async def char(name, delay):
    for i in range(2):
        print(f"{name}: tick {i}")
        await sleep(delay)
    return name


async def main():
    a, b = Task(char("Ranger", 0.03)), Task(char("Priest", 0.05))
    return [await a, await b]


print(run(main()))
```

It prints:

```text
Ranger: tick 0
Priest: tick 0
Ranger: tick 1
Priest: tick 1
['Ranger', 'Priest']
```

Read `run` next to the `_run_once` diagram of [The runtime](#guide-async-2-the-runtime). The
real loop replaces `time.sleep(timeout)` with `selector.select(timeout)`, so that a socket can
end the sleep early.

#### Trace: `request` sends `attack` and waits for `game_response`

This is `request` in `actions.py`:

```python
    async def request(self, event: str, payload: Any, place: str | None = None,
                      timeout_ms: float = 2000) -> GameResponse | None:
        """Send `event` and wait for the game_response whose `place` is `place`
        (the event name by default). None if no reply comes in time: some
        failures send another event instead (attack: `disappear`)."""
        await self.budget.wait_for_room(event)  # first, so that it does not use the timeout
        reply = self.sock.wait_for("game_response", response_for(place or event), timeout=timeout_ms / 1000)
        try:
            await self.budget.emit(event, payload)
        except BaseException:
            # The send failed (the socket closed) or we were cancelled: nobody
            # will await `reply`. Close it, so Python does not warn "coroutine
            # ... was never awaited". The waiter ends at its timer, or at the close.
            reply.close()
            raise
        try:
            return normalize(await reply)
        except TimeoutError:
            return None
```

A trace program wraps `Handle._run`, the one method through which the loop calls a callback.
It prints each callback that the loop runs during one request. The request uses the same steps
as `Actions.request`, without the budget. The fake server answers after 50 ms with `player`,
then `game_response`:

```text
    0.1 ms  waiter registered; now emit
    0.6 ms  emit returned without a switch; now await reply
   53.0 ms  loop runs: _SelectorSocketTransport._read_ready
   53.2 ms  loop runs: step of task reader
   53.3 ms  handler: player {'mp': 90}
   53.5 ms  loop runs: _retrieve
   53.5 ms  loop runs: AlSocket.wait_for.<locals>.cleanup
   53.5 ms  loop runs: step of task main
   53.5 ms  request resumes with the reply
```

The times can differ. The two frames can also arrive in two reads, which gives two
`_read_ready` lines. Step by step:

1. `wait_for_room` finds room. It returns without a suspension.
2. `wait_for` makes the future, appends the waiter, and starts the 2 s timer. It returns the
   coroutine `result()`. Nothing waits yet.
3. `budget.emit` records the cost and awaits `sock.emit`. `websockets` writes the frame
   `42["attack",{"id":"goo1"}]` to the kernel. No `await` in this chain suspends.
4. `await reply` starts `result()`, which awaits the future. The future is pending, so it
   yields itself. The yield goes up through `result`, `request`, `attack`, `tick` and `farm`,
   to the Task. The Task adds its wake-up callback to the future. The step ends.
5. The loop sleeps in `epoll_wait` for 50 ms. Nothing of the bot runs. (In a real bot, other
   events and pings arrive here, and the reader handles them.)
6. The socket becomes readable. The loop runs `_read_ready`. It reads the bytes and gives them
   to `websockets`. `websockets` parses two frames and completes the future on which the
   reader waits. That adds the reader step to the ready queue.
7. The reader step runs. `async for` gets `player`. `_deliver` calls the `def` handlers. The
   next frame is already in the queue of `websockets`, so `recv` does not suspend. The reader
   gets `game_response`, calls its handlers, and finds the waiter. The predicate matches.
   `fut.set_result(data)` queues `_retrieve`, `cleanup` and the wake-up of the main task.
8. `_retrieve` marks the future as read. `cleanup` cancels the timer and removes the waiter.
9. The main task steps. `Future.__await__` returns the payload, `result()` returns it, and
   `request` continues at `normalize(...)`.

```text
 main task                         loop                       reader task
 ---------                         ----                       -----------
 wait_for: fut + timer
 emit: frame to kernel (no switch)
 await reply -> fut yields itself
   step ends ---------------------> epoll_wait(<= 2 s)
                                    socket readable
                                    _read_ready -> websockets
                                    reader step -------------> "player": def handlers
                                                               "game_response": handlers,
                                                               then fut.set_result(data)
                                    cleanup (timer, waiter)
 step: await returns data <-------- main step
```

The handlers of `game_response` ran before `request` continued. That is always so in Python,
for two reasons. `_deliver` calls the handlers before it checks the waiters. And
`set_result` only queues the wake-up, so the main task resumes after the reader step ends.

</div>

<div data-lang="go">

Go has no `await`. A Go function that waits for the network has the same signature as a
function that adds two numbers. This chapter shows why Go does not need `await`, and what
occurs, step by step, when your code waits for a reply from the server.

#### Colorless functions

In JavaScript, Python, C# and Rust, a function that waits must be `async`. Only an `async`
function can call it with `await`. Thus each function has a "color", and the color spreads up
the call chain.

Go has one color. Each goroutine has its own stack, and the runtime can park any goroutine at
any call. Thus a plain call can wait, and the caller continues when the callee returns.
`actions.Attack` calls `Request`, which waits up to 2 s for a reply. `Farmer.Tick` calls
`Attack` as a plain function.

The cost moves to other places:

- **You cannot see a wait in a signature.** A function can block for seconds, and its type
  does not say it. The course states it in each package comment: "the methods block the
  goroutine that calls them".
- **Concurrency is the decision of the caller.** A function that waits runs in sequence. To
  run it at the same time as other work, the caller starts a goroutine with `go`.
- **Each goroutine needs a stack.** It starts at 2 KB and grows. A goroutine costs more than
  a promise, but 10,000 waiting goroutines use only tens of MB.

#### What stands in for a future: `Expect`

In other languages, the pattern "start the wait, send, then wait" uses a future. You make the
future, you send, then you `await` the future. Go has no future type. Thus `alsocket` returns
a **function** from `Expect`. A call to that function is the `await`:

```go
	wait := a.sock.Expect("game_response", ResponseFor(place)) // 1. register the wait
	if err := a.budget.Emit(event, payload); err != nil {      // 2. send
		forget(wait) // nothing was sent: remove the waiter now
		return GameResponse{}, err
	}
	session := a.Context()
	ctx, cancel := context.WithTimeout(session, timeout) // the timeout runs inside the session
	defer cancel()
	data, err := wait(ctx) // 3. block until the reply, the timeout, the end of the session or of the socket
```

`session` is the context of the whole session, for example the one that Ctrl-C cancels.
[Async 6](#guide-async-6-cancellation-timeouts-and-errors) explains it.

`WaitFor` exists too. It is `Expect` followed at once by the call. It blocks before it
returns, so you cannot send between the two parts. Use `WaitFor` only for an event that you
do not cause.

#### What a wait does in the runtime

The function that `Expect` returns does a `select` on three channels:

```go
		select {
		case data := <-w.ch:
			return data, nil
		case <-ctx.Done(): // your timeout
			s.mu.Lock()
			_, waiting := s.waiters[w]
			delete(s.waiters, w)
			s.mu.Unlock()
			if !waiting {
				// deliver took the waiter first: the reply came at the same
				// time as the deadline, and select chose the deadline (it
				// chooses at random when both are ready). The reply is on
				// its way to w.ch: deliver sends it after the handlers of
				// that event. Take it.
				return <-w.ch, nil
			}
			return nil, fmt.Errorf("waiting for %q: %w", name, ctx.Err())
		case <-s.done:
```

The runtime function `selectgo` does the `select`. When no case is ready, it does these
steps:

1. It locks the three channels.
2. It looks at the cases in a random order. If one is ready, it does that case and returns.
   The random order prevents one case from always winning.
3. No case is ready. It makes a record for this goroutine (a `sudog`) on each of the three
   channels. The record says "this G waits to receive here".
4. It parks the goroutine with the reason `select`, and unlocks the channels.
5. The M calls the scheduler and runs a different G.

Later, the dispatch goroutine does `w.ch <- ev.data`. The send finds the `sudog` of the
waiting goroutine. It copies the value directly to that goroutine. Then it calls `goready`,
which puts the goroutine in `runnext` of the current P. When the waiting goroutine runs
again, `selectgo` removes its records from the other two channels and returns case 1.

A `select` is a wait for the first of several events. It is the Go form of `Promise.race`,
with one difference. The cases that lose are not "cancelled": they never started anything.

#### One call, step by step

This program runs the real `actions.Request("attack", ...)` from the course against a small
fake server on `127.0.0.1`. The fake server answers `attack` after 200 ms with a `hit` event,
then a `game_response`. The program prints the goroutine of each step. While `Request`
waits, it also prints the state of each goroutine. The helpers `fakeal.ServeIfChild` and
`fakeal.StartProcess` run the fake server in a child process, so that its goroutines do not
show in the list.

```go
// trace: one real course call, actions.Request("attack", ...), against a
// fake server on 127.0.0.1. It prints which goroutine does each step, and
// the state of each goroutine while Request waits.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"
	"runtime"
	"strings"
	"time"

	"albot/actions"
	"albot/alsocket"
	"albot/budget"
	"albot/cooldowns"
	"albot/gdata"
	"albot/world"
	"checks/fakeal"
)

// gid reads the goroutine id from the stack header. For demos only: Go has
// no API for it on purpose.
func gid() string {
	b := make([]byte, 64)
	b = b[:runtime.Stack(b, false)]
	return strings.Fields(string(b))[1]
}

var start = time.Now()

func say(format string, args ...any) {
	fmt.Printf("%4dms g%-3s %s\n", time.Since(start).Milliseconds(), gid(), fmt.Sprintf(format, args...))
}

func main() {
	fakeal.ServeIfChild() // the fake server runs in a child process
	url, stop := fakeal.StartProcess(fakeal.Options{ReplyDelay: 200 * time.Millisecond, HitBeforeGR: true})
	defer stop()

	sock, err := alsocket.Connect(context.Background(), url)
	if err != nil {
		panic(err)
	}
	defer sock.Close()
	if _, err := sock.WaitFor(context.Background(), "welcome", nil); err != nil {
		panic(err)
	}
	w := world.New(sock, &gdata.GData{})
	act := actions.New(sock, w, cooldowns.New(w), budget.New(sock, w))
	sock.On("hit", func(json.RawMessage) { say("handler: hit") })
	sock.On("game_response", func(json.RawMessage) { say("handler: game_response") })

	// While Request waits, print each goroutine: its state (in [brackets])
	// and its first function in albot (or else its top function).
	go func() {
		time.Sleep(100 * time.Millisecond)
		buf := make([]byte, 1<<16)
		buf = buf[:runtime.Stack(buf, true)]
		for _, block := range strings.Split(string(buf), "\n\n") {
			lines := strings.Split(block, "\n")
			head := regexp.MustCompile(`^goroutine (\d+) \[([^\]]+)\]`).FindStringSubmatch(lines[0])
			fn := lines[1]
			for _, l := range lines[1:] {
				if strings.HasPrefix(l, "albot/") {
					fn = l
					break
				}
			}
			fn = fn[:strings.LastIndex(fn, "(")]
			fmt.Printf("        g%-3s %-16s %s\n", head[1], "["+head[2]+"]", fn)
		}
	}()

	say("Request: Expect, Emit, then wait")
	r, err := act.Request("attack", map[string]any{"id": "goo1"}, "attack", 2*time.Second)
	say("Request returned: response=%q place=%q err=%v", r.Response, r.Place, err)
}
```

It prints this. The goroutine numbers, the order of the list and the times can differ.

```text
   6ms g1   Request: Expect, Emit, then wait
        g9   [running]        main.main.func3
        g1   [select]         albot/alsocket.(*Socket).Expect.func2
        g20  [IO wait]        albot/alsocket.(*Socket).readLoop
        g8   [select]         github.com/coder/websocket.(*Conn).timeoutLoop
        g21  [select]         albot/alsocket.(*Socket).dispatchLoop
 208ms g21  handler: hit
 208ms g21  handler: game_response
 209ms g1   Request returned: response="data" place="attack" err=<nil>
```

Read the dump in the middle. `g1` (main) waits in the `select` of the waiter. `readLoop`
waits in the netpoller (`IO wait`). `dispatchLoop` waits in a `select` on its two channels.
No thread blocks. The process uses almost no CPU during the 200 ms.

Now the full path of the call, with each concept of the last chapters:

1. **g1, `Expect`.** It locks `s.mu`, adds the waiter to `s.waiters`, and unlocks. No park
   occurs, unless another goroutine holds `s.mu`.
2. **g1, `budget.Emit`, then `sock.Emit`.** `conn.Write` writes the frame to the TCP socket.
   The kernel has room in its send buffer, so the `write` system call returns at once.
3. **g1, `wait(ctx)`.** `selectgo` finds no ready case. It parks g1 with the reason `select`.
   The M of g1 runs other Gs, or waits in the netpoller.
4. **The kernel.** The bytes of the `hit` frame arrive. epoll marks the socket ready.
5. **An M, in `findRunnable` or `sysmon`.** `netpoll` returns `readLoop`. The runtime puts
   it in a run queue.
6. **`readLoop`.** Its `read` now gets the bytes. It parses `42["hit",...]` and sends the
   event on `s.events`. `dispatchLoop` waits on that channel in its `select`. Thus the send
   copies the event to it and puts it in `runnext`. `readLoop` calls `conn.Read` again and parks.
7. **`dispatchLoop`.** It runs `deliver` for `hit`: your handler prints. Then the
   `game_response` follows the same path, steps 4 to 6.
8. **`dispatchLoop`, `deliver` for `game_response`.** It finds the waiter of g1, because the
   predicate `ResponseFor("attack")` returns true. It runs the handlers first, then sends on
   `w.ch`. The send wakes g1.
9. **g1.** `selectgo` returns case 1. `Request` returns. The deferred `cancel()` releases the
   timer of the `ctx`.

In step 8, the handlers run before the send to the waiter. Thus, when `Request` returns, the
handlers of that `game_response` already ran. [Async 8](#guide-async-8-alsocket-read-with-these-eyes)
returns to this order.

Compare this with `await` in JavaScript. There, the function returns to the event loop at
the `await`, and a microtask continues it later. In Go, nothing returns. The goroutine
stops in the middle of `selectgo`, with its whole stack intact. The runtime starts it again
at the same place. The "state machine" of other languages is here the stack of the
goroutine.

</div>

<div data-lang="csharp">

`await` is not a feature of the runtime. The C# compiler rewrites each `async` method into a
class or struct, and the runtime only sees ordinary calls. This chapter opens that rewrite.

#### What the compiler makes

Take this method:

```csharp
public static class Demo
{
    public static async Task<int> AddLaterAsync(int a, int b)
    {
        await Task.Delay(10);
        var sum = a + b;
        await Task.Delay(10);
        return sum;
    }
}
```

The compiler moves its body into a nested type that implements `IAsyncStateMachine`. The
`[AsyncStateMachine]` attribute on the method names that type, so reflection can show it:

```csharp
// statemachine: what the compiler makes of an async method, and the same
// machine written by hand. The program is this code, the Demo class above,
// and the ByHand class below.
using System.Reflection;
using System.Runtime.CompilerServices;

// 1. The compiler's machine, seen through reflection.
var method = typeof(Demo).GetMethod(nameof(Demo.AddLaterAsync))!;
var machine = method.GetCustomAttribute<AsyncStateMachineAttribute>()!.StateMachineType;
Console.WriteLine($"{machine.Name}: {(machine.IsValueType ? "struct" : "class")}, implements {string.Join(", ", machine.GetInterfaces().Select(i => i.Name))}");
foreach (var f in machine.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
    Console.WriteLine($"  field {f.Name,-16} {Short(f.FieldType)}");
Console.WriteLine($"AddLaterAsync(2, 3) = {await Demo.AddLaterAsync(2, 3)}");

// 2. The same method, as a machine by hand.
Console.WriteLine($"AddLaterByHand(2, 3) = {await ByHand.AddLaterAsync(2, 3)}");

static string Short(Type t) => t.IsGenericType
    ? $"{t.Name[..t.Name.IndexOf('`')]}<{string.Join(", ", t.GetGenericArguments().Select(Short))}>"
    : t.Name;
```

Output of a Release build (`dotnet run -c Release`):

```text
<AddLaterAsync>d__0: struct, implements IAsyncStateMachine
  field <>1__state       Int32
  field <>t__builder     AsyncTaskMethodBuilder<Int32>
  field a                Int32
  field b                Int32
  field <sum>5__2        Int32
  field <>u__1           TaskAwaiter
AddLaterAsync(2, 3) = 5
```

Each field has a job:

| Field | Job |
|---|---|
| `<>1__state` | Where to continue. -1: running, or not started. 0, 1, ...: stopped at that `await`. -2: done. |
| `<>t__builder` | The `AsyncTaskMethodBuilder<int>`. It owns the `Task<int>` that the caller gets. |
| `a`, `b` | The parameters. They must live on after the method returns to its caller. |
| `<sum>5__2` | A local that is used after an `await`. The compiler "hoists" it into a field. |
| `<>u__1` | The awaiter of the `await` that waits now. Both `await`s here share it, because they have the same type. |

A Debug build makes a `class`, so the debugger can see the fields. A Release build makes a
`struct`, so a method that never waits allocates no machine on the heap.

#### The machine, by hand

This is what the compiler writes for a method with one `await`, in a form that you can read.
It compiles and runs. The compiler's own form uses `switch` and `goto`, but the steps are the
same.

```csharp
// What the compiler writes for a method with ONE await (the release form: a struct).
public static class ByHand
{
    public static Task<int> AddLaterAsync(int a, int b)
    {
        var sm = new Machine { Builder = AsyncTaskMethodBuilder<int>.Create(), State = -1, A = a, B = b };
        sm.Builder.Start(ref sm);   // runs MoveNext now, on this thread
        return sm.Builder.Task;     // the hot task that the caller awaits
    }

    private struct Machine : IAsyncStateMachine
    {
        public int State;                          // -1 running, 0 waits at await 0, -2 done
        public AsyncTaskMethodBuilder<int> Builder;
        public int A, B;                           // the parameters, now fields
        private TaskAwaiter _awaiter;              // the awaiter, kept across the wait

        public void MoveNext()
        {
            int result;
            try
            {
                TaskAwaiter awaiter;
                if (State != 0)
                {
                    Console.WriteLine($"  MoveNext (state {State}): start, thread {Environment.CurrentManagedThreadId}");
                    awaiter = Task.Delay(10).GetAwaiter();
                    if (!awaiter.IsCompleted)
                    {
                        State = 0;
                        _awaiter = awaiter;
                        // Box the struct (first time only), register MoveNext as
                        // the continuation, and RETURN: the thread is free now.
                        Builder.AwaitUnsafeOnCompleted(ref awaiter, ref this);
                        Console.WriteLine("  MoveNext: returns to its caller");
                        return;
                    }
                }
                else
                {
                    Console.WriteLine($"  MoveNext (state {State}): resume, thread {Environment.CurrentManagedThreadId}");
                    awaiter = _awaiter;
                    _awaiter = default;
                    State = -1;
                }
                awaiter.GetResult();   // throws here if the awaited task failed
                result = A + B;
            }
            catch (Exception e)
            {
                State = -2;
                Builder.SetException(e);   // the task becomes Faulted
                return;
            }
            State = -2;
            Builder.SetResult(result);     // the task becomes RanToCompletion
        }

        public void SetStateMachine(IAsyncStateMachine stateMachine) => Builder.SetStateMachine(stateMachine);
    }
}
```

The second part of the program prints this (the thread ids can differ):

```text
  MoveNext (state -1): start, thread 5
  MoveNext: returns to its caller
  MoveNext (state 0): resume, thread 5
AddLaterByHand(2, 3) = 5
```

Read the machine as the answer to "what does `await` do". At each `await`, `MoveNext` does
this:

1. Call the expression, then `GetAwaiter()` on its result.
2. Ask `awaiter.IsCompleted`. If it is `true`, go to step 6 at once. No thread change and no
   allocation occur.
3. Else, save the state number and the awaiter in fields.
4. Call `Builder.AwaitUnsafeOnCompleted(ref awaiter, ref this)`. The first time, this copies the
   struct to the heap ("boxing"). It also captures the `ExecutionContext` (the values of
   `AsyncLocal<T>`). Then it registers "call `MoveNext` again" with the awaiter.
5. **Return.** The thread goes back to its caller. For a pool thread, the caller is the loop of
   the worker, which takes the next item.
6. Later, the awaited task completes. It calls `MoveNext` again. The state number selects the
   code after the `await`. `GetResult()` returns the value, or throws the exception of the task.

The exception in step 6 is the one that the task holds. `MoveNext` catches it like any other
exception, so `try`/`catch` around an `await` works. If nothing catches it, `SetException`
stores it in the task of this method. The exception moves up the chain of awaits, one task at a
time.

#### The awaiter pattern

`await x` compiles for any `x` that has a `GetAwaiter()` method (an instance or extension
method). The awaiter must have `bool IsCompleted`, `GetResult()`, and implement
`INotifyCompletion` (`OnCompleted(Action)`). `ICriticalNotifyCompletion` adds
`UnsafeOnCompleted`, which skips the capture of the `ExecutionContext`, because the builder
already did it. This awaiter logs each call that the compiler makes:

```csharp
// awaiter: "await x" works on any x with the awaiter pattern. This one logs
// each call that the compiler makes. Then: SynchronizationContext and ConfigureAwait.
using System.Runtime.CompilerServices;

Console.WriteLine($"SynchronizationContext.Current is {(SynchronizationContext.Current is null ? "null" : "set")}");
var n = await new Pause(50);
Console.WriteLine($"await gave {n}, thread {Environment.CurrentManagedThreadId}");

// A context that runs posted work on one thread of its own, like a UI thread.
var context = new OneThreadContext();
await context.RunAsync(async () =>
{
    Console.WriteLine($"in context: thread {Environment.CurrentManagedThreadId}");
    await Task.Delay(10);
    Console.WriteLine($"after await: thread {Environment.CurrentManagedThreadId} (back in the context)");
    await Task.Delay(10).ConfigureAwait(false);
    Console.WriteLine($"after ConfigureAwait(false): thread {Environment.CurrentManagedThreadId}, context {(SynchronizationContext.Current is null ? "null" : "set")}");
});

// The awaiter pattern: GetAwaiter(), then IsCompleted, OnCompleted, GetResult.
readonly struct Pause(int ms)
{
    public PauseAwaiter GetAwaiter() { Console.WriteLine("  GetAwaiter"); return new PauseAwaiter(Task.Delay(ms)); }
}

readonly struct PauseAwaiter(Task delay) : INotifyCompletion
{
    public bool IsCompleted { get { Console.WriteLine($"  IsCompleted: {delay.IsCompleted}"); return delay.IsCompleted; } }
    public void OnCompleted(Action continuation)
    {
        Console.WriteLine("  OnCompleted: keep the continuation, return");
        delay.ContinueWith(_ => continuation());
    }
    public int GetResult() { Console.WriteLine($"  GetResult on thread {Environment.CurrentManagedThreadId}"); return 7; }
}

sealed class OneThreadContext : SynchronizationContext
{
    private readonly System.Collections.Concurrent.BlockingCollection<(SendOrPostCallback, object?)> _queue = new();
    public override void Post(SendOrPostCallback d, object? state)
    {
        Console.WriteLine("  context.Post");
        _queue.Add((d, state));
    }
    public Task RunAsync(Func<Task> body)
    {
        var done = new TaskCompletionSource();
        var thread = new Thread(() =>
        {
            SetSynchronizationContext(this);
            body().ContinueWith(t => { done.SetResult(); _queue.CompleteAdding(); });
            foreach (var (d, s) in _queue.GetConsumingEnumerable()) d(s);
        });
        thread.Start();
        return done.Task;
    }
}
```

Output (the thread ids can differ):

```text
SynchronizationContext.Current is null
  GetAwaiter
  IsCompleted: False
  OnCompleted: keep the continuation, return
  GetResult on thread 7
await gave 7, thread 7
in context: thread 9
  context.Post
after await: thread 9 (back in the context)
after ConfigureAwait(false): thread 7, context null
```

The first part shows the pattern. The compiler calls `GetAwaiter`, then `IsCompleted`, then
`OnCompleted` with "the rest of the method" as an `Action`. Later the awaiter calls that
action, and the compiler calls `GetResult`.

#### SynchronizationContext and ConfigureAwait

The awaiter of `Task` does one more thing in step 4. It looks at
`SynchronizationContext.Current`. If the thread has a context, the continuation does not run
where the task completes. It goes to `context.Post(...)`. A UI framework uses a context that
posts to its UI thread, so the code after `await` runs on the UI thread again.

If the thread has no context, the awaiter checks `TaskScheduler.Current`. If that is not the
default scheduler, the continuation goes there.

The second part of the output shows both cases. In the context, the code after `await
Task.Delay(10)` came back to thread 9 through `Post`. After `ConfigureAwait(false)`, it did not:
it ran on pool thread 7, and the context was gone.

**A console program has no `SynchronizationContext`**. The first output line shows it. Thus,
in the course, a continuation runs on the thread that completes the task, or on a pool thread
that the completion queues. `ConfigureAwait(false)` changes nothing there. It matters in a
library that a UI program or an old ASP.NET program can call.

In .NET 8,
`ConfigureAwait(ConfigureAwaitOptions)` also exists. `SuppressThrowing` waits without the
exception, and `ForceYielding` always continues asynchronously.

The context is also the cause of the famous deadlock: `.Result` on the UI thread blocks the
thread that the continuation needs. In a console program, this deadlock cannot occur. The cost
of `.Result` there is the blocked pool thread of [Async 2](#guide-async-2-the-runtime).

#### One real call, step by step

`Actions.RequestAsync` sends an event and waits for its `game_response`:

```csharp
// fragment of course/csharp/Albot/Actions.cs, RequestAsync
var reply = _sock.WaitForAsync("game_response", ResponseFor(place ?? evt), TimeSpan.FromMilliseconds(timeoutMs));
// If the emit throws (the socket closed), we never await `reply`. That is
// safe: AlSocket marks the failure of each wait as observed.
await _budget.EmitAsync(evt, payload);
try { return Normalize(await reply); }
catch (TimeoutException) { return null; }
```

This program runs the same three steps against the real `AlSocket` and a fake server in the
same process. Put it in a console project with a copy of `course/csharp/Albot/AlSocket.cs`.
Each line shows its thread.

```csharp
// trace: one request through the real AlSocket (a copy of course/csharp/Albot/AlSocket.cs),
// against a fake Socket.IO server in the same process. Each line shows its thread.
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using Albot;

FakeServer.Start("http://localhost:5006/");
Log("main: connect");
var sock = await AlSocket.ConnectAsync("ws://localhost:5006/?EIO=4&transport=websocket");
Log("main: connected");

// A handler for the same event, as World has one.
sock.On("game_response", d => Log($"handler: game_response {d.GetProperty("response")}"));

// The three lines of RequestAsync: register, send, await.
var reply = sock.WaitForAsync("game_response", d =>
{
    Log("predicate: runs in Deliver, inside the lock of AlSocket");
    return d.TryGetProperty("place", out var p) && p.GetString() == "attack";
}, TimeSpan.FromSeconds(2));
Log($"main: waiter registered, task {reply.Status}");
await sock.EmitAsync("attack", new { id = "48213" });
Log("main: attack sent, now await");
var data = await reply;
Log($"main: after await, place {data.GetProperty("place")}");
await sock.CloseAsync();
Log("main: closed");

static void Log(string what) => Console.WriteLine($"thread {Environment.CurrentManagedThreadId,2}: {what}");

// The fake game: the Socket.IO handshake, then one game_response for each attack.
static class FakeServer
{
    public static void Start(string prefix)
    {
        var listener = new HttpListener();
        listener.Prefixes.Add(prefix);
        listener.Start();
        _ = Task.Run(async () =>
        {
            var ctx = await listener.GetContextAsync();
            var ws = (await ctx.AcceptWebSocketAsync(null)).WebSocket;
            await Send(ws, "0{\"sid\":\"x\",\"pingInterval\":4000,\"pingTimeout\":12000}");
            var buffer = new byte[4096];
            while (true)
            {
                var r = await ws.ReceiveAsync(buffer, default);
                if (r.MessageType == WebSocketMessageType.Close)
                {
                    if (ws.State == WebSocketState.CloseReceived) await ws.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "", default);
                    return;
                }
                var text = Encoding.UTF8.GetString(buffer, 0, r.Count);
                if (text == "40") await Send(ws, "40{\"sid\":\"y\"}");
                else if (text.StartsWith("42[\"attack\""))
                {
                    await Task.Delay(30); // one round trip
                    await Send(ws, "42[\"game_response\",{\"response\":\"data\",\"place\":\"attack\",\"pid\":\"p1\"}]");
                }
                else if (text == "41") await ws.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "", default);
            }
        });
    }

    static Task Send(WebSocket ws, string text) =>
        ws.SendAsync(Encoding.UTF8.GetBytes(text), WebSocketMessageType.Text, true, default);
}
```

Output (the thread ids can differ from run to run):

```text
thread  1: main: connect
thread  7: main: connected
thread  7: main: waiter registered, task WaitingForActivation
thread  7: main: attack sent, now await
thread  5: predicate: runs in Deliver, inside the lock of AlSocket
thread  5: handler: game_response data
thread  5: main: after await, place attack
thread  7: main: closed
```

In this run, the code after `await` ran on thread 5, the thread of the dispatcher. That is not
inline. The dispatcher finished the event and gave its thread back to the pool. Then the pool
gave the same thread the queued continuation. In other runs, it is another thread.

Now follow `RequestAsync("attack", new { id })` through the machine:

1. The tick calls `AttackAsync`, which calls `RequestAsync`. `MoveNext` starts on the tick's
   current thread, here thread 7.
2. `WaitForAsync` makes a `TaskCompletionSource`, puts the waiter in `_waiters` under
   `_lock`, starts a 2 s timer, and returns the task. The task is `WaitingForActivation`.
3. `_budget.EmitAsync` takes the budget lock, records the cost, and calls `SendRawAsync`. That
   method awaits `_sendLock.WaitAsync()`, then `_ws.SendAsync(...)`. If both complete at once,
   `IsCompleted` is `true` at each `await`, and `MoveNext` continues without a stop.
4. `await reply`: the task is not complete. `MoveNext` saves state 1 and the awaiter. It
   registers itself on the task and returns. Thread 7 is free. The tick waits, but no thread
   waits for it.
5. The frame `42["game_response",{...}]` arrives. The `.NET Sockets` thread wakes in
   `epoll_wait` and queues a work item. A worker completes the `ReceiveAsync` of `ReadLoop`.
   `ReadLoop` parses the frame and writes it to the channel.
6. The dispatcher continues from `await foreach` on thread 5. `Deliver` takes `_lock`, copies
   the handlers, runs the predicate, and removes the waiter from the list. Then it leaves the
   lock.
7. Thread 5 runs the handlers of `game_response`. Then it calls `TrySetResult(data)` on the
   waiter. Because of `RunContinuationsAsynchronously`, that call only queues the continuation,
   and returns.
8. A worker (here thread 5 again, after the dispatcher returned) takes the continuation from
   the queue. It calls `MoveNext` of `RequestAsync` in state 1. `GetResult()` returns the
   payload. `Normalize` runs, and `SetResult` completes the task of `RequestAsync`.
9. `AttackAsync` is not `async`: it returns the task of `RequestAsync` as it is. Thus the next
   machine is `Farmer.TickAsync`. Its continuation runs inline, on the same thread, inside that
   `SetResult`.

When step 8 starts, the handlers of the reply have run. But the dispatcher continues with the
next events, so step 8 can run in parallel with their handlers.
[Async 8](#guide-async-8-alsocket-read-with-these-eyes) returns to this point.

</div>

<div data-lang="rust">

`.await` is not a function call and not a thread switch. The compiler turns each `async fn`
into a type: an enum with one variant for each point where the function can stop. `.await`
becomes a loop that polls the inner future and returns `Pending` to its own caller when the
inner future is not ready. This chapter builds that enum by hand, explains why it needs `Pin`,
and then traces one real `attack` request through the course code.

#### What `.await` expands to

Inside an `async` body, `expr.await` is about this (pseudo-code; `yield` is not real syntax
here):

```text
let mut fut = IntoFuture::into_future(expr);
loop {
    match Pin::new_unchecked(&mut fut).poll(cx) {   // cx: the Context of OUR poll
        Poll::Ready(value) => break value,
        Poll::Pending => yield Poll::Pending,       // return Pending to our caller;
                                                    // the next poll of us resumes HERE
    }
}
```

Two points matter:

- **The `Context` passes down.** Your future gets a `cx` from its caller and gives the same
  `cx` to the inner future. Thus the waker that a socket stores at the bottom is the waker of the
  whole task at the top.
- **`Pending` passes up.** Each level returns `Pending` to the level above it, until the task
  returns `Pending` to the worker. The worker then runs other tasks. "Suspend" means only this:
  the stack frames return. The local variables that must survive move into the future value.

#### The state machine, by hand

This `async fn` has two `.await` points:

```rust
async fn two_steps(rx: oneshot::Receiver<u32>) -> u32 {
    tokio::time::sleep(Duration::from_millis(10)).await; // await point 1
    let v = rx.await.unwrap(); // await point 2
    v + 1
}
```

The compiler makes a type that is close to the enum below. Each variant holds the variables
that are alive across that `.await`. The complete program compares both forms:

```rust
// An async fn, and the state machine that the compiler makes of it, by hand.
use std::future::Future;
use std::pin::Pin;
use std::task::{Context, Poll};
use std::time::Duration;

use tokio::sync::oneshot;
use tokio::time::Sleep;

// The async fn: two .await points, so three states in between.
async fn two_steps(rx: oneshot::Receiver<u32>) -> u32 {
    tokio::time::sleep(Duration::from_millis(10)).await; // await point 1
    let v = rx.await.unwrap(); // await point 2
    v + 1
}

// The same, by hand. Each variant holds the locals that live across an await.
enum TwoSteps {
    Start { rx: oneshot::Receiver<u32> },
    // Sleep is !Unpin, so we box it. The compiler stores it inline and
    // uses Pin to promise that it never moves.
    Sleeping { rx: Option<oneshot::Receiver<u32>>, sleep: Pin<Box<Sleep>> },
    Receiving { rx: oneshot::Receiver<u32> },
    Done,
}

impl Future for TwoSteps {
    type Output = u32;
    fn poll(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<u32> {
        let this = &mut *self; // TwoSteps is Unpin: every field is Unpin
        loop {
            match this {
                TwoSteps::Start { .. } => {
                    // The code before the first await: make the sleep.
                    let TwoSteps::Start { rx } = std::mem::replace(this, TwoSteps::Done) else { unreachable!() };
                    let sleep = Box::pin(tokio::time::sleep(Duration::from_millis(10)));
                    *this = TwoSteps::Sleeping { rx: Some(rx), sleep };
                    println!("  state: Start -> Sleeping");
                }
                TwoSteps::Sleeping { rx, sleep } => {
                    // Poll the inner future. Pending: return Pending too.
                    if sleep.as_mut().poll(cx).is_pending() {
                        println!("  state: Sleeping, sleep is Pending -> return Pending");
                        return Poll::Pending;
                    }
                    let rx = rx.take().unwrap();
                    *this = TwoSteps::Receiving { rx };
                    println!("  state: Sleeping -> Receiving");
                }
                TwoSteps::Receiving { rx } => match Pin::new(rx).poll(cx) {
                    Poll::Pending => {
                        println!("  state: Receiving, rx is Pending -> return Pending");
                        return Poll::Pending;
                    }
                    Poll::Ready(v) => {
                        *this = TwoSteps::Done;
                        println!("  state: Receiving -> Done");
                        return Poll::Ready(v.unwrap() + 1);
                    }
                },
                TwoSteps::Done => panic!("polled after Ready"),
            }
        }
    }
}

#[tokio::main]
async fn main() {
    let (tx, rx) = oneshot::channel();
    let by_hand = TwoSteps::Start { rx };
    // Send the value later, from another task.
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_millis(30)).await;
        let _ = tx.send(41);
    });
    println!("by hand: {}", by_hand.await);

    let (tx, rx) = oneshot::channel();
    let _ = tx.send(41);
    let fut = two_steps(rx);
    println!("size of the async fn future: {} bytes", std::mem::size_of_val(&fut));
    println!("async fn: {}", fut.await);
}
```

It prints (the size depends on the compiler version; this is Rust 1.99):

```text
  state: Start -> Sleeping
  state: Sleeping, sleep is Pending -> return Pending
  state: Sleeping -> Receiving
  state: Receiving, rx is Pending -> return Pending
  state: Receiving -> Done
by hand: 42
size of the async fn future: 144 bytes
async fn: 42
```

Read the trace as the life of one task. Poll 1 runs the code before the first `.await`, then
stops at the sleep. The timer wakes the task. Poll 2 finishes the sleep and stops at the
receiver. The `send` wakes the task, and poll 3 finishes.

Between the polls, no thread holds this code. The whole "paused function" is 144 bytes inside
the future of its caller. In a spawned task, those bytes are part of one heap allocation of the
runtime.

This also explains the cost model of Rust async. A future is a plain value of a known size.
There is no stack for each task and no allocation for each `.await`. `tokio::spawn` makes one
allocation for the whole task. A nested `async fn` is a field inside its caller's enum.

#### `Pin`: why a future must not move

The compiler stores inline what the hand-written enum puts in a `Box`. That creates a problem
when a variable that lives across an `.await` borrows another such variable. The course has a
real case. In `AlSocket::connect`, the `handshake` block borrows `stream` and `sink`, and
`connect` awaits it:

```rust
        let (mut sink, mut stream) = ws.split();

        let handshake = async {
            // Engine.IO "open": 0{"sid", "pingInterval", "pingTimeout", ...}
            let open = next_text(&mut stream).await?;
```

While `connect` waits at `tokio::time::timeout(ten_s, handshake).await`, the state of `connect`
contains `stream` and also `handshake`. `handshake` holds a pointer to `stream`. Thus the
future of `connect` points into itself. If you move that future to another address after the
first poll, the pointer still points to the old address.

`Pin<&mut Self>` prevents the move. A pinned value stays at its address until its drop.
`poll` takes `Pin<&mut Self>`, so a future can rely on this from its first poll. Before the first
poll, nothing points inside, and a move is safe. That is why you can return a future from a
function and then `.await` it.

The mental model is enough for daily work:

- **`Unpin`** is an auto trait for types that do not care about moves. Most types are `Unpin`.
  The futures of `async` blocks are not.
- **To pin**, put the future in a `Box` (`Box::pin`), or pin it on the stack (`std::pin::pin!`
  or `tokio::pin!`). `tokio::spawn` boxes each task, and thus pins it.
- **You meet `Pin` when you poll by reference.** For example, `select!` in a loop on
  `&mut fut` needs a pinned `fut`. The compiler error names `Unpin`; `tokio::pin!(fut)` fixes it.

#### A trace: `attack` and its `game_response`

The course's [`attack`](#send-attack) is `request("attack", {id})`. This is `request` from
`actions.rs`:

```rust
        let place = place.unwrap_or(event);
        // 1 day: in effect no timeout of its own. The timeout below decides,
        // so that "no reply" (None) and "socket closed" (Err) stay different.
        let day = Duration::from_secs(86_400);
        let reply = self.sock.wait_for_timeout("game_response", response_for(place), day);
        self.budget.emit(event, payload).await?;
        let ms = Duration::from_millis(timeout_ms.unwrap_or(2000)); // 2 s: replies take < 0.5 s
        match tokio::time::timeout(ms, reply).await {
            Ok(data) => Ok(Some(normalize(&data?))),
            Err(_) => Ok(None), // dropping `reply` also removes the waiter
        }
```

`farmer.tick()` calls `act.attack(id).await` on the main thread. Follow it step by step:

1. **`wait_for_timeout` runs now.** It is a plain `fn`. It locks `Shared`, pushes a `Waiter`
   with a `oneshot::Sender`, and unlocks. It returns the future `reply`. Nobody polls `reply`
   yet.
2. **`budget.emit(...).await`.** Its first poll locks the list of the budget, finds room, and
   records the cost. Then it calls `sock.emit`, an `async fn` that formats
   `42["attack",{"id":...}]` and puts it on the unbounded channel of the writer. A send on an
   unbounded channel never waits. Thus this whole `.await` completes in its first poll. The
   channel wakes the writer task.
3. **A worker polls the writer.** It sends the frame on the WebSocket.
4. **`timeout(ms, reply).await`.** `Timeout::poll` polls `reply` first. `reply` polls an
   inner `timeout(1 day, rx)`, which polls `rx`. `rx` is empty. It stores the waker of the
   main future and returns `Pending`. Each level registers its timer in the wheel and returns
   `Pending`. `farmer.tick()`, the session loop and `main` return `Pending` to `block_on`.
5. **The main thread parks.** No thread runs your tick now.
6. **The reply arrives.** The worker that holds the driver returns from `epoll_wait`. It wakes
   the reader task. The reader parses `42["game_response",{..."place":"attack"}]` and sends it
   on the event channel. That wakes the dispatcher, into the LIFO slot of the same worker.
7. **The dispatcher runs `deliver`.** First the handlers: `World` locks its state, and
   `Cooldowns` reads `cooldown` failures. Then the waiters: the predicate matches `place`, and
   `tx.send(data)` stores the payload and calls the waker of the main future.
8. **The main thread wakes.** `block_on` polls `main` again. The poll goes down the same chain
   of enums to the `Timeout` in step 4. `rx` is `Ready`. `normalize` runs, and `attack`
   returns `Some(GameResponse)`.

If no reply comes in 2 s, the time driver wakes the main thread instead. `Timeout` returns
`Err(Elapsed)`, and `timeout` drops `reply`. The drop of `rx` closes the oneshot. The next
`deliver` sees `tx.is_closed()` and removes the waiter.

Note that `Timeout::poll` polls the inner future before it checks its own timer. If the reply
and the deadline are both ready at the same poll, the reply wins.

</div>

<div data-lang="java">

Java has no `await` keyword. This is a design decision, not a gap. JavaScript, Python, C# and Rust split each function into two kinds: functions that block and functions that return a future. Java 21 keeps one kind of function. It makes blocking cheap instead. This chapter shows what a blocking wait does on each kind of thread, then traces one real `request` from the course.

#### The two ways to continue after a future

You have two ways to run code after a future completes:

1. **Block:** call `get()` or `join()`. The current thread stops until the box is full. The next line of your method then runs on the same thread, with all its local variables. This is the style of the course.
2. **Chain:** call `thenApply`, `thenCompose`, `whenComplete`. You give a function to the future. Some thread runs it later. Your current method continues at once. This is the callback style of Java 8.

`await` in other languages makes style 2 look like style 1: the compiler cuts your method into callbacks. Java gets style 1 without a compiler change, because a blocked virtual thread costs almost nothing.

#### What `get()` does on a platform thread

`main` is a platform thread. `future.get()` on an incomplete future does this, in JDK 21:

1. `get` calls `waitingGet`. It pushes a `Signaller` (a dependent that knows the waiting thread) onto the stack of the future.
2. The `Signaller` calls `LockSupport.park`. On a platform thread, this is a kernel wait (a `futex` on Linux). The OS thread sleeps.
3. Another thread calls `complete`. It runs the dependents, and the `Signaller` calls `LockSupport.unpark(main)`.
4. The kernel wakes `main`. `get` reads the result and returns it.

During the wait, the OS thread exists and keeps its stack. For one `main` thread, this is no problem.

#### What `get()` does on a virtual thread

Steps 1 and 3 are the same. Step 2 is different. `LockSupport.park` sees a virtual thread and calls `VirtualThread.park`. That method **yields the continuation**: the frames of the virtual thread stay in the heap, and the carrier returns to the scheduler. In step 4, `unpark` puts the virtual thread back in the queue of the scheduler. A carrier mounts it, and `get` returns.

You can see these frames in a thread dump of a virtual thread that waits in `BlockingQueue.take` (from chapter [Async 9](#guide-async-9-seeing-it-run)):

```text
"java.base/java.lang.VirtualThread.park(VirtualThread.java:596)",
"java.base/java.lang.System$2.parkVirtualThread(System.java:2644)",
"java.base/jdk.internal.misc.VirtualThreads.park(VirtualThreads.java:54)",
"java.base/java.util.concurrent.locks.LockSupport.park(LockSupport.java:369)",
...
"java.base/java.util.concurrent.LinkedBlockingQueue.take(LinkedBlockingQueue.java:435)",
```

So on a virtual thread, `get()` is the Java equivalent of `await`. The difference: the JVM, not the compiler, saves the frames. Thus every method in the stack can block, and no method needs a special type.

#### Pinning: when the virtual thread cannot leave

In Java 21, a virtual thread cannot unmount while a `synchronized` frame or a native frame is on its stack. The JVM implements `synchronized` with the identity of the OS thread, so the continuation must stay on that thread. A park there blocks the carrier. This is **pinning**.

```java
// Pinning.java: one carrier thread, two virtual threads. A waits for a future; B completes it.
// Run: java -Djdk.virtualThreadScheduler.parallelism=1 Pinning.java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class Pinning {
    static final Object lock = new Object();

    static void trial(boolean pin) throws InterruptedException {
        var future = new CompletableFuture<String>();
        Thread a = Thread.ofVirtual().start(() -> {
            try {
                if (pin) {
                    synchronized (lock) { // Java 21: a park in here keeps the carrier
                        System.out.println("A: " + future.get(1, TimeUnit.SECONDS));
                    }
                } else {
                    System.out.println("A: " + future.get(1, TimeUnit.SECONDS));
                }
            } catch (Exception e) {
                System.out.println("A: " + e.getClass().getSimpleName());
            }
        });
        Thread b = Thread.ofVirtual().start(() -> future.complete("value from B"));
        a.join();
        b.join();
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("without synchronized:");
        trial(false);
        System.out.println("with synchronized:");
        trial(true);
    }
}
```

On Java 21 (`eclipse-temurin:21`):

```text
without synchronized:
A: value from B
with synchronized:
A: TimeoutException
```

With one carrier, A parks inside `synchronized` and keeps the only carrier. B cannot run until A gives up at its timeout. Without a timeout, this is a deadlock. Java 24 changed this (JEP 491): `synchronized` no longer pins. The same program on Java 25 prints `A: value from B` twice. Native frames still pin in Java 24 and later.

The scheduler of Java 21 does not add a carrier for a pinned thread. With 4 cores you have 4 carriers. Four pinned waits stop all virtual threads of the program. The course avoids the problem: it never blocks inside `synchronized`.

#### Which thread runs a chained stage?

Style 2 has a rule that surprises many readers. A stage without `Async` in its name runs on whichever thread makes it ready:

```java
// WhichThread.java: which thread runs a stage of a CompletableFuture?
// Run: java WhichThread.java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class WhichThread {
    static String me() { return Thread.currentThread().getName(); }

    public static void main(String[] args) throws Exception {
        // 1. A stage that we add BEFORE the future completes runs on the thread that completes it.
        var f = new CompletableFuture<String>();
        var a = f.thenApply(s -> "thenApply ran on " + me());
        var b = f.thenApplyAsync(s -> "thenApplyAsync ran on " + me());
        Thread.ofPlatform().name("completer").start(() -> f.complete("x")).join();
        System.out.println(a.join());
        System.out.println(b.join());

        // 2. A stage that we add AFTER it completes runs at once, on the thread that adds it.
        System.out.println(f.thenApply(s -> "late thenApply ran on " + me()).join());

        // 3. orTimeout fails the future on a JDK timer thread; the next stage runs there.
        var g = new CompletableFuture<String>();
        var c = g.orTimeout(100, TimeUnit.MILLISECONDS)
                 .handle((s, e) -> e + " seen on " + me());
        System.out.println(c.join());
    }
}
```

```text
thenApply ran on completer
thenApplyAsync ran on ForkJoinPool.commonPool-worker-1
late thenApply ran on main
java.util.concurrent.TimeoutException seen on CompletableFutureDelayScheduler
```

The rules:

- `thenApply` (no `Async`): the thread that calls `complete` runs the stage, inside its call to `complete`. If the future is already complete, the thread that adds the stage runs it.
- `thenApplyAsync(fn)`: the stage goes to the **common pool**, `ForkJoinPool.commonPool()`. Its size is the number of cores minus 1. (On a machine with 1 or 2 cores, the default is a new thread for each task.)
- `thenApplyAsync(fn, executor)`: the stage goes to your executor.

Thus a plain `thenApply` on an `AlSocket` waiter would run your code on the dispatcher thread, inside the lock of the socket. `waitFor` ends its chain with `thenApplyAsync` to prevent this.

#### `get` and `join`

Both block. They differ only in their exceptions:

| Call | Interrupted | Future failed with `e` | Cancelled | Own timeout |
|---|---|---|---|---|
| `get()` | throws `InterruptedException` | throws `ExecutionException` (cause `e`) | `CancellationException` | n/a |
| `get(t, unit)` | throws `InterruptedException` | `ExecutionException` (cause `e`) | `CancellationException` | throws `TimeoutException`; the future stays incomplete |
| `join()` | ignores it and continues to wait | throws `CompletionException` (cause `e`) | `CancellationException` | n/a |

`get` is from `Future` and uses checked exceptions. `join` is from `CompletableFuture` and uses unchecked ones, so it fits in a lambda. The course uses `get()` in its blocking methods, because they declare `InterruptedException` anyway.

#### A trace of one `request`

`Actions.request` is three lines:

```java
var reply = sock.waitFor("game_response", responseFor(place), Duration.ofMillis(timeoutMs));
budget.emit(event, payload);
try {
    return normalize(reply.get());
```

This program runs the same three steps against a fake server, and logs the thread of each step. A handler for `game_response` takes 200 ms:

```java
// TraceRequest.java: one request through the course AlSocket, with the thread of each step.
// The fake server answers `attack` with a game_response. A handler for game_response is slow.
import albot.AlSocket;
import java.time.Duration;
import java.util.List;

public class TraceRequest {
    static long t0 = System.nanoTime();
    static void log(String what) {
        System.out.printf("%4d ms  %-34s %s%n", (System.nanoTime() - t0) / 1_000_000, Thread.currentThread().getName(), what);
    }

    public static void main(String[] args) throws Exception {
        var server = new FakeAl();
        server.onClient = text -> {
            if (text.startsWith("42[\"attack\"")) {
                try { server.send("42[\"game_response\",{\"response\":\"data\",\"place\":\"attack\"}]"); } catch (Exception e) { }
            }
        };
        server.serve(List.of("sleep:200", "42[\"welcome\",{}]", "sleep:2000"));
        AlSocket sock = AlSocket.connect(server.url());
        sock.waitFor("welcome").get();
        sock.on("game_response", d -> {
            log("handler starts");
            try { Thread.sleep(200); } catch (InterruptedException e) { }
            log("handler ends");
        });
        t0 = System.nanoTime();
        log("waitFor (register the waiter)");
        var reply = sock.waitFor("game_response", d -> "attack".equals(d.path("place").asText()), Duration.ofSeconds(2))
                .thenApply(d -> { log("thenApply after waitFor"); return d; });
        log("emit attack");
        sock.emit("attack", java.util.Map.of("id", "1"));
        log("get() blocks");
        var d = reply.get();
        log("get() returned " + d);
        Thread.sleep(300);
        System.exit(0);
    }
}
```

```text
   0 ms  main                               waitFor (register the waiter)
   2 ms  main                               emit attack
  46 ms  main                               get() blocks
  47 ms  alsocket-dispatch                  handler starts
 254 ms  alsocket-dispatch                  handler ends
 254 ms  ForkJoinPool.commonPool-worker-1   thenApply after waitFor
 264 ms  main                               get() returned {"response":"data","place":"attack"}
```

The times can differ. Step by step:

1. `main` calls `waitFor`. It makes the box, adds the waiter under `lock`, and builds the chain. Nothing waits yet.
2. `main` calls `emit`. `send` adds a `sendText` to the chain of sends and returns a future at once. `main` does not wait for the bytes to leave.
3. `main` calls `get()` on the end of the chain. `main` is a platform thread, so the OS thread parks. In `PartyMerchant`, the fighters call `request` on virtual threads; there the virtual thread unmounts.
4. The server answers. `HttpClient-1-SelectorManager` reads the bytes. A listener thread calls `onText`, which parses `42[...]` and puts an `Event` in the queue.
5. `alsocket-dispatch` returns from `events.take()`. `deliver` copies the handlers and the waiters of `game_response` under `lock`. Then it leaves `lock` and runs the handlers. The handler sleeps 200 ms.
6. After the handlers, `deliver` tests the predicate under `lock` and removes the waiter. Outside `lock`, it calls `complete(data)`.
7. Inside `complete`, the dispatcher runs the dependents: `whenComplete` removes the waiter again (no effect), and `thenApplyAsync` submits a task to the common pool.
8. A common-pool thread runs the copy stage and your `thenApply`, then completes the last future. Its `Signaller` unparks `main`.
9. `main` wakes, and `get()` returns. The handler of the same event already ended.

Step 9 is a rule of `AlSocket` in all seven languages: when a wait returns, the handlers of that event already ran. Chapter [Async 8](#guide-async-8-alsocket-read-with-these-eyes) shows why the Java version once broke this rule.

</div>

## Async 5: Several things at the same time

A bot does many things at once: it reads, it ticks, it waits for replies, and it can control
more than one character. This chapter shows how to start work without a wait for it. Then it shows how to wait for all
of it, for the first part, or for each part as it ends.

<div data-lang="js ts">

#### Concurrency on one thread

JavaScript gives you concurrency without parallelism. Many operations can be in progress at
the same time. Only one piece of JavaScript runs at a time. Your operations make progress in
the gaps: each `await` that must wait ends a piece, and the loop runs whatever is ready next.

To start work without waiting for it, call the async function and do not `await` the result.
The call runs the body up to the first `await`, and then you have a promise. To wait for it,
`await` that promise later. So "start" and "wait" are two separate steps in JavaScript. The
`request` of the course uses this: `waitFor` starts the wait, `emit` sends, `await reply` waits.

#### The four combinators

`Promise` has four static methods that wait for a list of promises. None of them starts
anything. The work started when you made each promise.

| Method | Fulfils when | Rejects when | Use in AL |
|---|---|---|---|
| `Promise.all(ps)` | all fulfil; values in input order | the first one rejects | wait for each character's loop |
| `Promise.allSettled(ps)` | all settle; never rejects | never | send to several targets and read each result |
| `Promise.race(ps)` | the first settles, if it fulfils | the first settles, if it rejects | a wait with a deadline |
| `Promise.any(ps)` | the first fulfils | all reject (`AggregateError`) | the first of several possible replies |

```js
// combinators.mjs: four ways to wait for several promises.
// fakeRequest stands in for act.request(): it settles after `ms`.
const fakeRequest = (name, ms, ok = true) =>
  new Promise((resolve, reject) =>
    setTimeout(() => (ok ? resolve(`${name} ok`) : reject(new Error(`${name} failed`))), ms));

const t0 = performance.now();
const at = () => `${String(Math.round(performance.now() - t0)).padStart(3)} ms`;

// all: every result, in the order of the input. The first rejection rejects it.
const both = await Promise.all([fakeRequest("heal", 200), fakeRequest("loot", 100)]);
console.log(at(), "all:", both); // after 200 ms: the two ran at the same time
try {
  await Promise.all([fakeRequest("heal", 200), fakeRequest("loot", 100, false)]);
} catch (err) {
  console.log(at(), "all rejected:", err.message); // after 100 ms, not 200
}

// allSettled: never rejects. One {status, value | reason} for each input.
const settled = await Promise.allSettled([fakeRequest("heal", 100), fakeRequest("loot", 50, false)]);
console.log(at(), "allSettled:", settled.map((s) => s.status));

// race: the first to settle, fulfilled or rejected. The other one still runs.
const first = await Promise.race([fakeRequest("slow", 300), fakeRequest("fast", 50)]);
console.log(at(), "race:", first);

// any: the first to fulfil. It rejects only if all reject (AggregateError).
const firstOk = await Promise.any([fakeRequest("a", 50, false), fakeRequest("b", 100)]);
console.log(at(), "any:", firstOk);
try {
  await Promise.any([fakeRequest("a", 10, false), fakeRequest("b", 20, false)]);
} catch (err) {
  console.log(at(), "any rejected:", err.constructor.name, err.errors.map((e) => e.message));
}
```

```text
203 ms all: [ 'heal ok', 'loot ok' ]
312 ms all rejected: loot failed
413 ms allSettled: [ 'fulfilled', 'rejected' ]
466 ms race: fast ok
567 ms any: b ok
588 ms any rejected: AggregateError [ 'a failed', 'b failed' ]
```

The times differ by a few ms from run to run. Look at line 2: `all` rejected at 100 ms, but the
`heal` timer still ran to 200 ms. A combinator stops the wait, never the work. The losers of
`race` and the rest of a failed `all` continue, and their results go nowhere. The combinators
attach a handler to each input, so a later rejection of a loser is not "unhandled".

To run two requests at the same time, give them different `place` values. Two waiters for the
same `place` both match the first reply.

#### A request with a deadline

`AlSocket.waitFor` has its own timer, so `request` needs no `race`. When you wrap a promise that
has no timeout, the usual form is `Promise.race([work, timeout])`. Clear the timer when the work
wins. An active timer keeps the process alive, and a timer that rejects later with nothing
attached ends it (Async 6).

#### Two characters on one program

`party-merchant.js` runs three characters on one thread. Each has its own `Bot`, so each has its
own WebSocket, its own World and its own `Budget`. The program starts the fighters and does not
wait for them. It waits for them only at the end:

```js
// fragment: course/js/party-merchant.js
/** @type {unknown} */
let failure = null; // the first error of a fighter (null: none)
const fighting = crew.slice(0, -1).map((f) =>
  fighterLoop(f).catch((err) => {
    console.log(`${f.m.name}: stopped: ${/** @type {Error} */ (err).message}`);
    failure ??= err;
    stop = true;
  }),
);
let done = 0;
try {
  while (!stop && (trips === 0 || done < trips)) {
    if (await merchantTrip()) done++;
  }
} finally {
  // Also when the merchant failed: end the fighters' loops, wait for them
  // (this never rejects: each one has its catch), and close every socket.
  stop = true;
  await Promise.all(fighting);
  for (const c of crew) c.m.close();
}
```

Each `fighterLoop` runs to its first `await sleep(TICK_MS)` and returns a promise. Then the
merchant loop starts. From then on, three loops and three sockets share one thread:

```text
time ─────────────────────────────────────────────────────────────────>
main thread: [fighter 1 tick][msg s1][merchant][msg s3][fighter 2 tick][msg s2]...
               each box runs to its next await, then the loop picks the next ready task
```

A slow handler on socket 1 delays the pongs of sockets 2 and 3. All three share the 12 s
limit of Async 2.

Look at the `.catch` on each fighter. It is there from the start, not only at the end. An
earlier version of the program had `fighterLoop(f)` alone, and only the `Promise.all` at the end
handled the fighters. Until that line, a rejection of a fighter had no handler. When a fighter's
socket closed, its `request` threw, and Node.js stopped the whole process at once (Async 6). The
other sockets stayed open, and the merchant stopped in the middle of a trip.

Now the `catch` prints the error at once and sets `stop`. Each loop checks `stop`, so the other
fighters and the merchant end at their next check. The `finally` waits for all fighters and
closes every socket, also when the merchant itself failed. This gives structured concurrency by
hand: the program ends only after every task that it started.

#### The tick runs while handlers run

The tick of `farm.js` is `await sleep(TICK_MS); await farmer.tick();` in a loop. Each `await`
in the tick (a `request`, a walk) lets the loop deliver events. So "while the tick waits for
an attack reply, the `entities` handler moves a monster" is the normal case. They never run at
the same instant. They interleave at the awaits of the tick. [Async 7](#guide-async-7-shared-state) is about what
that does to your state.

Do not use `setInterval(tick, 100)` with an async `tick`. `setInterval` calls `tick` every
100 ms and ignores the promise that it returns. A tick that waits 2 s for a reply then has 20
other ticks running beside it.

#### Fire and forget

A promise that you start and never `await` is "fire and forget". It is sometimes correct: a
log write, or a `move` that has no reply. It has three risks:

- **A rejection has no handler.** Since Node.js 15, that stops the process.
- **You lose the order.** Nothing waits, so the next step can start before this one ends.
- **You lose the end.** The program can call `process.exit` while the work still runs.

If you mean it, say it in the code. Add `.catch(...)` to handle the error. In TypeScript, the
lint rule `@typescript-eslint/no-floating-promises` finds each promise that you drop by
mistake. It needs type information (`parserOptions.projectService`):

```ts
// tick.ts: three ways to start a promise and not wait for it.
declare function request(event: string): Promise<string | null>;

export async function tick(): Promise<void> {
  request("attack");                   // reported: a floating promise
  void request("attack");              // allowed: `void` says "on purpose"
  request("attack").catch(() => {});   // allowed: the rejection has a handler
}
```

```text
/w/lint/tick.ts
  5:3  error  Promises must be awaited, end with a call to .catch, end with a call to .then with a rejection handler or be explicitly marked as ignored with the `void` operator  @typescript-eslint/no-floating-promises
```

`tsc` itself accepts all three lines. Note that `void` only silences the rule. A rejection of
a `void` promise still stops the process. Use `void` for promises that cannot reject.

JavaScript has no built-in structured concurrency: no scope that waits for its child tasks and
cancels them when one fails. You build it from parts. Keep the promises that you start, pass an
`AbortSignal` to each (Async 6), and `await Promise.allSettled(...)` in a `finally`.

#### Long work: split it

CPU work blocks the thread, but you can cut it into parts. After each part, wait for the loop
with `setImmediate`. Pending I/O, and thus each ping, runs in the poll phase before the check
phase that resumes you. A `Promise.resolve()` does not help here: a microtask runs before the
loop continues.

```js
// fragment: a search that gives the loop a turn after each 1,000 nodes
const nextTurn = () => new Promise((resolve) => setImmediate(resolve));
for (let i = 0; i < nodes.length; i++) {
  expand(nodes[i]);
  if (i % 1000 === 999) await nextTurn(); // events, timers and pongs run here
}
```

This keeps the pongs on time, but the search takes longer, and the world can change between
the parts.

#### Parallelism: worker threads

For real parallel work, Node.js has `node:worker_threads`. A worker is a second V8 isolate on
its own thread, with its own heap and its own event loop. It shares no JavaScript objects with
the main thread. You send it data with `postMessage`, and the worker gets a copy (the structured
clone algorithm). A path search over a large map is the AL example. The search runs on the
worker, and the main thread keeps its pongs on time.

```js
// worker.mjs: CPU work on a worker thread, while the main thread keeps its timers.
import { Worker } from "node:worker_threads";

const t0 = performance.now();
const at = () => `${String(Math.round(performance.now() - t0)).padStart(4)} ms`;

// The worker's code. It has its own V8 isolate, heap and event loop.
const code = `
  const { parentPort, workerData } = require("node:worker_threads");
  let sum = 0;
  for (let i = 0; i < workerData.n; i++) sum += i % 7; // stands in for a path search
  parentPort.postMessage(sum);                        // a copy goes to the main thread
`;

// A "pong" timer on the main thread: it must run every 500 ms.
const timer = setInterval(() => console.log(at(), "main thread: timer"), 500);

const worker = new Worker(code, { eval: true, workerData: { n: 1e9 } });
worker.on("message", (sum) => {
  console.log(at(), "main thread: the worker sent", sum);
  clearInterval(timer);
});
```

```text
 501 ms main thread: timer
1002 ms main thread: timer
1503 ms main thread: timer
2004 ms main thread: timer
2506 ms main thread: timer
2529 ms main thread: the worker sent 2999999997
```

The times depend on the CPU. Each timer is on time, while 1 billion steps run on the other
thread. The worker's message arrives on the main thread as a task, through the `uv_async`
wake-up of Async 2. A worker costs a few MB and some ms to start, so start one and keep it.
Send it the map grid one time, then send each search as a small message.

</div>

<div data-lang="python">

#### Concurrency on one thread

`asyncio` gives concurrency, not parallelism. Many tasks can be in progress, but only one runs
at a time, on one thread. The tasks interleave at their `await`s. The waits overlap; the CPU
work does not.

For an AL bot, almost all time is waiting: for a reply, for a cooldown, for the next tick.
Thus one thread can run several characters. `party_merchant.py` runs four characters in one
program: four sockets, four reader tasks, three fighter loops and the merchant, all on the
main thread. If each step is short, the characters do not hold each other back.

#### Start without waiting: `create_task`

`await coro()` runs the coroutine inside your task. Your task waits until it returns.
`asyncio.create_task(coro())` makes a new task and returns at once. Your task continues, and
the new task starts at the next iteration. Later, `await task` gives its result, or raises its
exception.

A task that nobody awaits is "fire and forget". It has three problems:

- **The loop keeps only a weak reference.** The garbage collector can free a task that waits
  for a future that only it holds (see [The unit of async work](#guide-async-3-the-unit-of-async-work)).
- **Its error goes nowhere.** Nobody calls `result()`. Python logs "Task exception was never
  retrieved" when it frees the task, and the program continues as if all is well.
- **Nobody cancels it at the end.** It can still use a socket that you closed.

If you need a background task, keep it in a set, and remove it when it ends:

```python
# fragment: keep a strong reference to each background task
background: set[asyncio.Task[None]] = set()

task = asyncio.create_task(log_loop())
background.add(task)
task.add_done_callback(background.discard)
```

A better tool for most cases is a `TaskGroup`.

#### Wait for all: `gather` and `TaskGroup`

`asyncio.gather(a, b)` wraps each coroutine in a task and waits for all of them. It returns the
results in the order of the arguments. `asyncio.TaskGroup` (Python 3.11+) is an `async with`
block. The block does not end until each task that you started in it ends.

The two differ when a task fails. This program has three characters. One or two of them
raise `ConnectionError`:

```python
# tog_taskgroup.py: gather vs TaskGroup when one task fails.
import asyncio


async def character(name: str, fail_after: float | None) -> str:
    try:
        for tick in range(3):
            await asyncio.sleep(0.1)
            if fail_after is not None and tick * 0.1 >= fail_after:
                raise ConnectionError(f"{name}: socket closed")
        return f"{name}: 3 ticks"
    except asyncio.CancelledError:
        print(f"   {name} was cancelled")
        raise  # always re-raise CancelledError


async def main() -> None:
    # gather: the first error comes out; the other task CONTINUES alone.
    other = asyncio.create_task(character("Priest", None))
    try:
        await asyncio.gather(character("Ranger", 0.0), other)
    except ConnectionError as err:
        print("gather raised:", err, "| Priest done?", other.done())
    print("Priest later:", await other)

    # gather(return_exceptions=True): errors become results.
    print(await asyncio.gather(character("Ranger", 0.0), character("Priest", None),
                               return_exceptions=True))

    # TaskGroup: one error cancels the others; all errors come out together.
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(character("Ranger", 0.0))
            tg.create_task(character("Mage", 0.0))
            tg.create_task(character("Priest", None))
    except* ConnectionError as group:
        print("TaskGroup raised", type(group).__name__,
              [str(e) for e in group.exceptions])


asyncio.run(main())
```

It prints:

```text
gather raised: Ranger: socket closed | Priest done? False
Priest later: Priest: 3 ticks
[ConnectionError('Ranger: socket closed'), 'Priest: 3 ticks']
   Priest was cancelled
TaskGroup raised ExceptionGroup ['Ranger: socket closed', 'Mage: socket closed']
```

| | `gather` | `TaskGroup` |
|---|---|---|
| One task fails | `gather` raises the first error at once. The other tasks continue, and nobody waits for them. | The group cancels the other tasks, waits for them, then raises. |
| Two tasks fail | You see the first error only. | You see all errors in one `ExceptionGroup`. |
| The task that waits is cancelled | It cancels the children. | It cancels the children. |
| Errors as values | `return_exceptions=True` | Catch inside each child. |

An `ExceptionGroup` (Python 3.11+) holds several exceptions. `except* ConnectionError` matches
the part of the group with that type, and lets the rest of the group continue upward. A
`TaskGroup` always raises a group, even for one error. Thus a plain `except ConnectionError`
around it never matches.

`TaskGroup` gives structured concurrency: no task outlives the block that started it. Prefer it
when the tasks belong together.

`party_merchant.py` shows the difference. An earlier version ran the fighter loops with
`gather`, and the merchant trips outside it. If the socket of one fighter closed, the other
fighters continued, and nobody saw the error until the trips ended. Now the fighters and the
merchant are tasks of one `TaskGroup`:

```python
    try:
        async with asyncio.TaskGroup() as tg:
            for f in fighters:
                tg.create_task(fighter_loop(f))
            tg.create_task(merchant_loop())
    except ExceptionGroup as group:
        # The group holds each error. Print the others; raise the first, so
        # that main() prints it as `<type>: <message>`, as for one character.
        for err in group.exceptions[1:]:
            print(f"also: {type(err).__name__}: {err}", file=sys.stderr)
        raise group.exceptions[0] from None
```

When one character fails, the group cancels the others at once. The `finally` of
`merchant_loop` sets `stop`, so in a normal end the fighters leave their loops.

#### Wait for the first, or for each one

`asyncio.wait(tasks, return_when=FIRST_COMPLETED)` returns two sets, `done` and `pending`, when
the first task ends. It cancels nothing. You must cancel the pending tasks yourself.
`asyncio.as_completed(aws)` gives the results in the order in which they end:

```python
# tog_combinators.py: wait for all, for the first, for each as it ends.
import asyncio
import time

t0 = time.monotonic()


def ms() -> str:
    return f"{1000 * (time.monotonic() - t0):4.0f} ms"


async def reply(name: str, seconds: float) -> str:
    """Stands for request(): a wait for a game_response."""
    await asyncio.sleep(seconds)
    return name


async def main() -> None:
    global t0
    # 1. Sequential: the waits add up.
    t0 = time.monotonic()
    a = await reply("attack", 0.2)
    b = await reply("heal", 0.3)
    print(f"{ms()}  sequential: {a}, {b}")

    # 2. gather: both wait at the same time; results in argument order.
    t0 = time.monotonic()
    both = await asyncio.gather(reply("attack", 0.2), reply("heal", 0.3))
    print(f"{ms()}  gather: {both}")

    # 3. The first that ends: asyncio.wait with FIRST_COMPLETED.
    t0 = time.monotonic()
    tasks = {asyncio.create_task(reply("game_response", 0.2)),
             asyncio.create_task(reply("disappear", 0.1))}
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    print(f"{ms()}  first: {[t.result() for t in done]}, still pending: {len(pending)}")
    for t in pending:
        t.cancel()  # wait() does not cancel the others; you must

    # 4. Each as it ends: as_completed.
    t0 = time.monotonic()
    for next_done in asyncio.as_completed([reply("slow", 0.3), reply("fast", 0.1)]):
        name = await next_done
        print(f"{ms()}  as_completed: {name}")


asyncio.run(main())
```

It prints (the ms values can differ a little):

```text
 501 ms  sequential: attack, heal
 300 ms  gather: ['attack', 'heal']
 100 ms  first: ['disappear'], still pending: 1
 100 ms  as_completed: fast
 301 ms  as_completed: slow
```

Case 3 is an AL case. An `attack` on a monster that is gone gets no `game_response`. It gets
[`disappear`](#recv-disappear). To react to whichever comes first, start one waiter for each,
then `wait` with `FIRST_COMPLETED`.

#### A request with a timeout

`request` has a timeout, but it uses no combinator. The waiter of `AlSocket` has its own timer.
At the end of the timer, `expire` sets `TimeoutError` on the future. Around any other wait, use
`async with asyncio.timeout(seconds):`. The next chapter shows how both work.

#### The tick and the handlers

A bot has at least two tasks: the reader of each socket, and your tick. They never run at the
same time, but they interleave at each `await` of the tick:

```text
 tick task                          reader task
 world.advance(); me = world.me
 await act.attack(id) ---suspend--> "player": World.on_player merges into me
                                    "hit":    Farmer._on_hit counts the hit
                                    "game_response": waiter done
 <-------------------------resume--
 reads me again: it already has the new mp
```

Two rules follow. First, a `def` handler runs as one piece, inside the reader step. It sees a
consistent world, and nobody sees half of its change. Second, the tick sees new state after
each `await` that suspended. A value that the tick read before the `await` can be old.

An `async def` handler is different. `_deliver` starts it as a separate task. Its first step
runs after the reader step. Thus the reader can process the next events first.

Its code after an internal `await` runs even later. Two such handlers for two `player` events can finish in
the other order. The course uses only `def` handlers for this reason.

To run two characters, start one tick loop for each, in one `TaskGroup`:

```python
# fragment: two characters, one thread; `bots` come from Bot.connect_with
async def play(bot: Bot, farmer: Farmer) -> None:
    while True:
        await asyncio.sleep(0.1)  # TICK
        await farmer.tick()


async with asyncio.TaskGroup() as tg:
    for bot, farmer in zip(bots, farmers):
        tg.create_task(play(bot, farmer))
```

If one socket closes, its `farmer.tick()` raises. The group then cancels the other loop, and
you can reconnect both, or catch the error inside `play` to keep the other one alive.

</div>

<div data-lang="go">

In Go, "at the same time" means "on different goroutines". This chapter shows how to start
work without a wait. Then it shows how to wait for all, for the first, or for each. It also
shows how to stop the others when one fails.

#### Concurrency and parallelism in Go

**Concurrency** is the structure: more than one goroutine is in progress. **Parallelism** is
the execution: more than one goroutine runs at the same instant, on different CPUs. In Go,
you write concurrency with `go`. The runtime gives you parallelism up to `GOMAXPROCS`.

For an AL client, parallelism is a side effect, not the goal. Your bot waits almost all of
the time. But the side effect is important. Your handlers and your tick can run at the same
instant on two CPUs. Thus each shared value needs a lock, also when the machine has one CPU
(preemption, [Async 2](#guide-async-2-the-runtime)).

#### Start without a wait

`go f()` starts `f` and continues. Use it in these cases:

- **A loop that runs for the whole session.** `alsocket` starts `readLoop` and
  `dispatchLoop` this way.
- **Long work that a handler must not do.** A handler starts a goroutine and returns. The
  dispatch goroutine continues with the next event.
- **One goroutine for each character.** `cmd/party-merchant` runs each fighter on its own
  goroutine.

A goroutine that nothing waits for ("fire and forget") has three risks:

1. **A panic in it ends the program.** Nothing can catch it from the outside.
2. **An error from it goes nowhere.** It has no return value that a caller can read.
3. **It can outlive its data.** A goroutine that still uses a socket after `Close` gets
   `ErrClosed` on each call, or blocks forever on a channel that nobody reads.

Thus give each goroutine an owner: a piece of code that waits for its end and reads its
error.

#### Wait for all: `sync.WaitGroup`

A `WaitGroup` is a counter. `Add(1)` before the `go` statement, `Done()` at the end of the
goroutine (with `defer`), and `Wait()` blocks until the counter is 0. This is the pattern of
`cmd/party-merchant`:

```go
	var wg sync.WaitGroup
	for _, f := range fighting {
		wg.Add(1)
		go func(f *crewMember) {
			defer wg.Done()
			// An error after the stop is only the stop itself (context.Canceled).
			if err := fighterLoop(f); err != nil && !isStopped() {
				fail(fmt.Errorf("%s: %w", f.m.Name, err)) // the others stop at once
			}
		}(f)
	}
```

Two details make this code correct:

- **`Add` comes before `go`.** If the goroutine called `Add`, `Wait` could run first, see 0,
  and return.
- **Each goroutine reports its error at once.** `fail` keeps the first error and cancels a
  context. The next section shows why this matters.

The parameter `f` of the closure is a habit from Go 1.21 and earlier. Before Go 1.22, a `for`
loop had one variable for all its iterations. Each goroutine then saw the last value. Since
Go 1.22, each iteration has a new variable, so `go func() { fighterLoop(f) }()` is also
correct. The `go` line in `go.mod` decides the rule: the course says `go 1.22`.

#### Wait for all, and stop at the first error: `errgroup`

A `WaitGroup` does not carry errors, and it does not stop the other goroutines. The package
`golang.org/x/sync/errgroup` adds both. `errgroup.WithContext` gives a group and a `ctx`.
When the first goroutine returns an error, the group cancels that `ctx`. `Wait` returns the
first error.

This program runs two characters, each on its own socket, against two fake servers. The
second server never answers `attack`. The program uses the real course `actions.Request`:

```go
// together: two characters in one program. Each has its own socket and its
// own goroutine. errgroup waits for both, and cancels the other one when
// one fails.
package main

import (
	"context"
	"fmt"
	"time"

	"golang.org/x/sync/errgroup"

	"albot/actions"
	"albot/alsocket"
	"albot/budget"
	"albot/cooldowns"
	"albot/gdata"
	"albot/world"
	"checks/fakeal"
)

// play connects one character and attacks n times, one per 100 ms tick.
func play(ctx context.Context, url, name string, n int) error {
	sock, err := alsocket.Connect(ctx, url)
	if err != nil {
		return err
	}
	defer sock.Close() // runs on every return path, also on an error
	if _, err := sock.WaitFor(ctx, "welcome", nil); err != nil {
		return err
	}
	w := world.New(sock, &gdata.GData{})
	act := actions.New(sock, w, cooldowns.New(w), budget.New(sock, w))
	act.SetContext(ctx) // the end of the group also ends a Request in progress
	for i := 1; i <= n; i++ {
		select {
		case <-ctx.Done(): // the group was cancelled: stop this character
			return ctx.Err()
		case <-time.After(100 * time.Millisecond): // the tick
		}
		r, err := act.Request("attack", map[string]any{"id": "goo"}, "attack", time.Second)
		if err != nil {
			return fmt.Errorf("%s: %w", name, err)
		}
		fmt.Printf("%s: attack %d -> %s\n", name, i, r.Response)
	}
	return nil
}

func main() {
	fakeal.ServeIfChild()
	ok, stop1 := fakeal.StartProcess(fakeal.Options{ReplyDelay: 20 * time.Millisecond})
	defer stop1()
	mute, stop2 := fakeal.StartProcess(fakeal.Options{NoReply: true}) // never replies

	// Round 1: both servers reply. Wait for all.
	g, ctx := errgroup.WithContext(context.Background())
	g.Go(func() error { return play(ctx, ok, "Ranger", 2) })
	g.Go(func() error { return play(ctx, ok, "Priest", 2) })
	fmt.Println("round 1:", g.Wait())

	// Round 2: the Priest's server never replies. Its Request returns
	// ErrNoReply after 1 s; errgroup cancels ctx, and the Ranger stops too,
	// also in the middle of a Request.
	g, ctx = errgroup.WithContext(context.Background())
	g.Go(func() error { return play(ctx, ok, "Ranger", 100) })
	g.Go(func() error { return play(ctx, mute, "Priest", 100) })
	fmt.Println("round 2:", g.Wait())
	stop2()
}
```

It prints this. The order of the lines in round 1, and the number of Ranger attacks in round
2, can differ.

```text
Ranger: attack 1 -> data
Priest: attack 1 -> data
Ranger: attack 2 -> data
Priest: attack 2 -> data
round 1: <nil>
Ranger: attack 1 -> data
Ranger: attack 2 -> data
Ranger: attack 3 -> data
Ranger: attack 4 -> data
Ranger: attack 5 -> data
Ranger: attack 6 -> data
Ranger: attack 7 -> data
Ranger: attack 8 -> data
Ranger: attack 9 -> data
round 2: Priest: no reply in time
```

In round 2, the Priest's `Request` waits 1 s and returns `ErrNoReply`. The group cancels
`ctx`. If the Ranger is between two attacks, it sees the end in the `select` and returns. If
it is in a `Request`, that wait ends at once too, because `act.SetContext(ctx)` gave the
group's context to its actions (see [Async 6](#guide-async-6-cancellation-timeouts-and-errors)).

The course program `cmd/party-merchant` does the same with a `WaitGroup` and its own
context, because the course uses only the standard library. Its `fail` keeps the first error
and cancels the context `play`. Each character's actions use `play`. Thus the other
characters stop at once, also in the middle of a walk or a wait for a reply. An earlier
version only collected the errors on a channel after the merchant's trips. A fighter whose
socket closed then stayed silent for minutes, and the others played on without it.

#### Wait for the first: `select`

`select` waits for the first of several channel operations. The course uses it in three
places:

- **A reply or a timeout.** The waiter of `Expect` selects on `w.ch`, `ctx.Done()` and
  `s.done`.
- **A sleep that can stop early.** `cmd/farm` selects on `ctx.Done()` and `time.After(d)`.
- **The first result of `auth`.** `bot.EnterGame` selects on its `result` channel and
  `ctx.Done()`.

A `select` with a `default` case never blocks. `EnterGame` uses this to keep only the first
result of `auth`:

```go
	result := make(chan error, 1)
	report := func(err error) {
		select {
		case result <- err:
		default: // a result is already there: only the first one counts
		}
	}
```

`start`, `game_error`, `disconnect_reason` and `disconnect` each call `report`. The first
one fills the buffer. The others take the `default` case, so the dispatch goroutine never
blocks.

#### Wait for each as it ends

To process results in the order they finish, give all goroutines one channel, and read it
`n` times. The receive order is the order of the sends. If you do not know `n`, close the
channel after a `WaitGroup` and read it with `range`:

```go
	// fragment: results arrive in the order the goroutines finish
	go func() { wg.Wait(); close(results) }()
	for r := range results {
		fmt.Println(r)
	}
```

#### The tick and the handlers

In a course program, two goroutines do the work of one character: the main goroutine runs
the tick, and the dispatch goroutine runs the handlers. They run at the same time, and you do
not decide when one interrupts the other. `World` handlers can change `Me` while
`Farmer.Tick` reads it. The course uses one lock for each shared object, and copies.
[Async 7](#guide-async-7-shared-state) shows how.

</div>

<div data-lang="csharp">

In .NET, concurrency and parallelism come together. Each task that you start is in progress at
the same time as yours (concurrency). Because the pool has several workers, its steps can
also run at the same instant as yours, on another core (parallelism). You never ask for the
second. You get it.

#### To start is not to wait

A call to an `async` method starts it (it is hot, see [Async 3](#guide-async-3-the-unit-of-async-work)).
`await` only waits. Thus "start several, then wait" is two separate lines:

```csharp
// fragment (FakeRequest is in the program below)
var a = FakeRequest("attack", 300);   // started
var b = FakeRequest("heal", 100);     // started; a runs too
var all = await Task.WhenAll(a, b);   // wait for both
```

If you write `await FakeRequest(...)` on each line, the second starts only after the first
ends. The code looks the same, but the time is the sum, not the maximum.

Work that only computes is different. An `async` method runs on your thread until its first
real wait. A method with no wait never gives the thread back. To put CPU work on another
thread, use `Task.Run(() => ...)`. The overview uses this for a long path search.

#### Waiting for all, the first, or each

```csharp
// together: start several tasks, then wait for all, for the first, or with a time limit.
using System.Diagnostics;

var clock = Stopwatch.StartNew();
string T() => $"{clock.ElapsedMilliseconds,4} ms";

// 1. Start three "requests" at once. Each runs while the others run.
var a = FakeRequest("attack", 300);
var b = FakeRequest("heal", 100);
var c = FakeRequest("open_chest", 200);
var all = await Task.WhenAll(a, b, c);  // waits for the slowest: about 300 ms, not 600
Console.WriteLine($"{T()} WhenAll: {string.Join(", ", all)}");

// 2. The first one to end. WhenAny returns the task that ended; the others continue.
clock.Restart();
var first = await Task.WhenAny(FakeRequest("slow", 300), FakeRequest("fast", 100));
Console.WriteLine($"{T()} WhenAny: {await first}");

// 3. Each one as it ends (.NET 8 has no Task.WhenEach; .NET 9 adds it).
clock.Restart();
var pending = new List<Task<string>> { FakeRequest("x", 150), FakeRequest("y", 50), FakeRequest("z", 100) };
while (pending.Count > 0)
{
    var done = await Task.WhenAny(pending);
    pending.Remove(done);
    Console.WriteLine($"{T()} ended: {await done}");
}

// 4. A time limit on a wait: WaitAsync (.NET 6+). The work itself continues.
clock.Restart();
try { await FakeRequest("respawn", 500).WaitAsync(TimeSpan.FromMilliseconds(200)); }
catch (TimeoutException) { Console.WriteLine($"{T()} WaitAsync: TimeoutException"); }

// 5. Two failures: await throws the first one; Task.Exception has both.
var both = Task.WhenAll(Fail("too_far"), Fail("cooldown"));
try { await both; }
catch (Exception e) { Console.WriteLine($"await threw: {e.Message}"); }
Console.WriteLine($"Exception has: {string.Join(", ", both.Exception!.InnerExceptions.Select(x => x.Message))}");

static async Task<string> FakeRequest(string name, int ms) { await Task.Delay(ms); return name; }
static async Task Fail(string code) { await Task.Delay(10); throw new Exception(code); }
```

Output (the times differ by a few ms; in part 5 the order of the two codes can differ):

```text
 304 ms WhenAll: attack, heal, open_chest
  98 ms WhenAny: fast
  54 ms ended: y
 104 ms ended: z
 153 ms ended: x
 205 ms WaitAsync: TimeoutException
await threw: cooldown
Exception has: cooldown, too_far
```

Three details are easy to miss:

- **`WhenAny` returns a `Task<Task<T>>`.** Its result is the task that ended, not its value.
  Await that task to get the value, or its exception. `WhenAny` itself never throws.
- **The losers continue.** After `WhenAny`, the slow request still runs. After `WaitAsync`, the
  wait for "respawn" still runs. Only the wait of your code ended. To stop the work, you need a
  `CancellationToken` ([Async 6](#guide-async-6-cancellation-timeouts-and-errors)).
- **`await` on `WhenAll` throws only one exception.** The task holds an `AggregateException`
  with all of them. `await` unwraps it and throws the first. Read `task.Exception` for the
  others.

#### Structured concurrency, by hand

C# has no scope that waits for each task that started inside it. Each task lives until it
ends, also when its caller has returned. The discipline is yours: **each task that you start,
you also await**, in one place, with `WhenAll`. One `CancellationToken` for the group lets you
stop all of it.

Two characters in one program are a good example. Each one has its own socket, `World` and
`Farmer`. They share only the thread pool:

```csharp
// Two characters in one program. Each one has its own socket, World and
// Farmer; they share only the thread pool. Members of a static class, with
// "using Albot;" and the course library.
public static async Task RunPartyAsync(string nameA, string nameB, CancellationToken ct)
{
    var auth = await Api.LoginAsync();
    var (servers, characters) = await Api.ServersAndCharactersAsync(auth);
    var server = Api.FindServer(servers);
    var g = await GData.LoadGAsync();

    // Start both connections, then wait for both: about one handshake of time, not two.
    var a = Bot.ConnectWithAsync(auth, server, Api.FindCharacter(characters, nameA), g);
    var b = Bot.ConnectWithAsync(auth, server, Api.FindCharacter(characters, nameB), g);
    var bots = await Task.WhenAll(a, b);

    // One tick loop for each character. WhenAll ends when both loops end.
    await Task.WhenAll(bots.Select(bot => FarmAsync(bot, ct)));
}

private static async Task FarmAsync(Bot bot, CancellationToken ct)
{
    var farmer = new Farmer(bot.World, bot.Act, bot.Cooldowns, new Travel(bot.World, bot.Act), bot.Character.Name + ": ");
    try
    {
        while (!ct.IsCancellationRequested)
        {
            await Task.Delay(100, ct);  // throws OperationCanceledException at Ctrl-C
            await farmer.TickAsync();
        }
    }
    catch (OperationCanceledException) { } // a normal stop
    finally { await bot.CloseAsync(); }     // runs for a stop and for an error
}
```

This process now runs six long tasks: a reader, a dispatcher and a tick loop for each character.
The pool runs them on its workers, as many at the same instant as there are cores. Two
characters do not need two threads. They need two chains of steps that never block.

A defect in this sketch: if one loop throws, `WhenAll` waits for the other loop, which runs
until Ctrl-C. To stop the group at the first error, give the loops a linked
`CancellationTokenSource`, and cancel it in a `catch`.

#### Fire and forget

`_ = SomethingAsync();` starts a task and drops it. The discard `_` only tells the compiler
that you mean it (inside an `async` method, it warns without it: CS4014). Three things go with the task:

- **Its exception.** Nobody awaits the task, so nobody sees its failure. It becomes an
  "unobserved" exception, which [Async 6](#guide-async-6-cancellation-timeouts-and-errors)
  shows. The bot continues without the work, and without a message.
- **Its end.** Nothing can wait for it at shutdown. The process can end in its middle.
- **Its order.** It runs at the same time as the code after it, maybe on another core.

`AlSocket` uses fire and forget one time, and it handles all three. `_ = Task.Run(sock.ReadLoop)`
starts the reader. `ReadLoop` catches every exception itself and turns it into a `disconnect`
event. Its end reaches the dispatcher through `_events.Writer.Complete()`, and the end of the
dispatcher is the `Completion` task that `CloseAsync` awaits.

The worst form is an `async` lambda given to an `Action`, such as a handler. The compiler makes
it an `async void` method. Nothing can even hold its task. [Async 6](#guide-async-6-cancellation-timeouts-and-errors)
shows how its exception ends the process.

#### Channel<T>: a queue between tasks

`AlSocket` needs the reader and the dispatcher to run separately, but in one order. A
`System.Threading.Channels.Channel<T>` is the tool: a thread-safe queue with an async read.

- `Channel.CreateUnbounded<T>()` has no limit. `Writer.TryWrite` always succeeds at once, so the
  writer never waits. `CreateBounded<T>(n)` makes the writer wait (`WriteAsync`) when the queue
  is full.
- `Reader.ReadAllAsync()` gives an `IAsyncEnumerable<T>`. `await foreach` takes each item in
  order. When the queue is empty, it waits without a thread.
- `Writer.Complete()` ends the channel. The reader gets the items that remain, and then
  `await foreach` ends.

The order of the channel is the order of the stream. One reader task writes, and one
dispatcher task reads, so the handlers see the events in arrival order. This is the same rule as
the server, which runs the handlers of one socket in arrival order. The unbounded channel has a
cost: if handlers are slower than the server, the queue grows without limit. In the course,
handlers only change state, so that does not occur.

</div>

<div data-lang="rust">

Rust gives you two separate tools for "more than one thing at a time". **Concurrency inside
one task**: one future polls several futures, and they take turns on one thread. **Tasks**:
`tokio::spawn` gives a future to the runtime, and the workers can run tasks in parallel. The
difference is real in Rust, because the multi-thread runtime runs tasks on many cores at once.

#### Inside one task: `join!` and `select!`

`tokio::join!(a, b)` makes one future that polls `a` and `b`. Both make progress while the
task waits, but they never run at the same instant. They are fields of one state machine, polled
by one thread. `join!` needs no `Send` and no `'static`, so the futures can borrow local
variables.

`tokio::select!` polls several futures and finishes with the first one that completes. Then it
**drops the others**. A dropped future stops for good
([Async 6](#guide-async-6-cancellation-timeouts-and-errors)).

#### Tasks: `spawn` and `JoinSet`

`tokio::spawn(fut)` returns a `JoinHandle<T>` at once. The task runs whether or not you await
the handle. Awaiting the handle gives `Result<T, JoinError>`.

`tokio::task::JoinSet` holds many tasks. `join_next().await` gives the result of the next task
that ends, in the order they end. When you drop a `JoinSet`, it aborts all of its tasks. That
makes it the structured choice: the tasks cannot outlive the scope that owns the set.

This program shows all four:

```rust
// Concurrency on one task (join!, select!) and parallelism with tasks (spawn, JoinSet).
use std::time::{Duration, Instant};

use tokio::task::JoinSet;
use tokio::time::sleep;

// A fake request: the reply comes after `ms`.
async fn request(name: &str, ms: u64) -> String {
    sleep(Duration::from_millis(ms)).await;
    format!("{name} ({ms} ms)")
}

#[tokio::main]
async fn main() {
    let t = Instant::now();
    // join!: both futures on THIS task. One poll of the task polls both.
    let (a, b) = tokio::join!(request("attack", 100), request("heal", 50));
    println!("join!: {a}, {b} after {} ms", t.elapsed().as_millis());

    // select!: the first branch to finish wins. The other future is dropped.
    let t = Instant::now();
    tokio::select! {
        r = request("attack", 300) => println!("select!: {r}"),
        _ = sleep(Duration::from_millis(100)) => println!("select!: timeout after {} ms", t.elapsed().as_millis()),
    }

    // JoinSet: one task per character; results in the order they end.
    let t = Instant::now();
    let mut set = JoinSet::new();
    for (name, ms) in [("Ranger", 120), ("Priest", 40), ("Mage", 80)] {
        set.spawn(async move { request(name, ms).await });
    }
    while let Some(done) = set.join_next().await {
        println!("JoinSet: {} at {} ms", done.unwrap(), t.elapsed().as_millis());
    }
}
```

The output (the ms values can differ by a few):

```text
join!: attack (100 ms), heal (50 ms) after 101 ms
select!: timeout after 102 ms
JoinSet: Priest (40 ms) at 42 ms
JoinSet: Mage (80 ms) at 83 ms
JoinSet: Ranger (120 ms) at 122 ms
```

`join!` took 100 ms, not 150 ms: the two waits overlap. The `select!` stopped the 300 ms
request at 100 ms. The `JoinSet` gave the results in the order of their end, not in the order
of the spawns.

`try_join!` is `join!` for futures that return `Result`. It stops at the first `Err` and drops
the other futures.

#### Why `spawn` asks for `Send + 'static`

The signature of `tokio::spawn` in Tokio 1.40 is:

```rust
// fragment: the signature only
pub fn spawn<F>(future: F) -> JoinHandle<F::Output>
where
    F: Future + Send + 'static,
    F::Output: Send + 'static,
```

Each bound has one reason:

- **`'static`**: the task can live longer than the function that spawned it. Thus the task
  must own its data. It cannot borrow a local of its caller.
- **`Send`**: between two polls, the task can move to another worker thread, for example when
  an idle worker steals it. Thus everything that the task keeps across an `.await` must be safe
  to move to another thread.

The compiler checks both, and its messages teach the model. A borrow of a local:

```rust
// Does NOT compile, on purpose: a spawned task borrows a local of main.
#[tokio::main]
async fn main() {
    let name = String::from("Ranger");
    let task = tokio::spawn(async {
        println!("{}", name); // a borrow of `name`, which lives on main's stack
    });
    task.await.unwrap();
}
```

The compiler refuses it:

```text
error[E0373]: async block may outlive the current function, but it borrows `name`, which is owned by the current function
 --> src/bin/not_static.rs:5:29
  |
5 |     let task = tokio::spawn(async {
  |                             ^^^^^ may outlive borrowed value `name`
6 |         println!("{}", name); // a borrow of `name`, which lives on main's stack
  |                        ---- `name` is borrowed here
```

The fix is `async move`, plus a clone of each `Arc` that the task needs. That is why the course
types (`World`, `Budget`, `Actions`) are cheap handles around an `Arc`: a clone shares the
same state.

The `Send` error appears when a task keeps a non-`Send` value across an `.await`. The common
case is a `std::sync::MutexGuard`. [Async 7](#guide-async-7-shared-state) shows that error.
Note the words "across an await". A non-`Send` value that your code drops before the `.await`
is not part of the state machine, so it does not matter.

#### `spawn_blocking` and `block_in_place`

A worker must not block (see [Async 2](#guide-async-2-the-runtime)). For work that blocks or
computes for a long time, Tokio has two exits:

- **`tokio::task::spawn_blocking(closure)`** runs a plain closure on the blocking pool and
  returns a `JoinHandle`. Use it for a long A* search, a large file, or a blocking library.
  Like `spawn`, it needs `Send + 'static`.
- **`tokio::task::block_in_place(closure)`** runs the closure on the current thread. First it
  gives the worker's queues to a new thread, so that the other tasks continue. It can borrow
  locals, because it does not move the work. It panics on a `current_thread` runtime.

The course needs neither. Its `pathfind` runs inside the tick, on the main thread, and the
main thread is not a worker. A long search there holds back only the tick. The reader and the
dispatcher continue on the workers.

#### AL: what runs at the same time in the course

- **A tick while handlers run.** The tick runs on the main thread. The dispatcher runs on a
  worker. They run in parallel, on two cores. That is the reason for each lock in the course.
- **A request with a timeout.** `request` puts `tokio::time::timeout` around the wait. That is
  a `select!` of two futures: the reply and a timer.
The two other cases need code.

**The first of several replies.** `enter_game` in `bot.rs` waits for `start`, `game_error`,
`game_log`, `disconnect_reason` or `disconnect`, whichever comes first:

```rust
    tokio::select! {
        biased;
        Ok(_) = start => Ok(welcome),
        Ok(e) = error => Err(login_error(error_reason(&e))),
        Ok(_) = busy => Err(login_error("authorization_in_progress")),
        Ok(r) = reason => Err(login_error(r.as_str().unwrap_or("disconnect_reason"))),
        Ok(r) = gone => Err(login_error(r.as_str().unwrap_or("disconnect"))),
        else => Err(login_error("timeout")),
    }
```

Without `biased;`, `select!` polls the branches in a random order on each poll, for fairness.
With it, `select!` polls them from the top down. If the value of a branch does not match its
pattern (here, an `Err`), `select!` turns that branch off. The `else` branch runs when all
branches are off.

**Two characters in one program.** `party-merchant` spawns one task for each fighter into a
`JoinSet`, and runs the merchant on the main future:

```rust
    let mut fighting = JoinSet::new();
    for f in &crew[..crew.len() - 1] {
        let (f, merchant) = (f.clone(), merchant_name.clone());
        let name = f.m.name.clone();
        // catch_unwind: a panic becomes a value with the fighter's name, not
        // only a line on stderr and a JoinError without a name.
        fighting.spawn(async move { (name, AssertUnwindSafe(fighter_loop(f, merchant)).catch_unwind().await) });
    }
```

The main future then runs a `select!` of two branches: one trip of the merchant, and
`fighting.join_next()`. A fighter must not end while the program plays. If one ends, the second
branch wins at once. The program prints the reason, drops the trip, and stops the others:

```rust
            // A fighter ended. Before the stop, that is a failure: report it
            // now and stop. (select! drops the merchant's trip at its .await.)
            Some(ended) = fighting.join_next() => {
                if let Some(why) = why_ended(ended) {
                    eprintln!("{why}; stopping the others");
                    result = Err(why.into());
                    break;
                }
            }
```

Each fighter has its own `AlSocket`, thus its own reader, writer and dispatcher. With four
characters, that is 12 socket tasks plus 3 fighter tasks on the workers. Tasks are cheap. The
number of workers stays one per core.

#### Fire and forget

A `JoinHandle` that you drop does not stop its task. The task continues, detached. This is
easy, and it has three risks:

1. **Nobody sees its result or its error.** A detached task that returns `Err` loses the error.
   A detached task that panics prints the panic message, and nothing else occurs.
2. **Nobody waits for its end.** When `main` returns, the runtime drops the remaining tasks at
   their next `.await`. Work in progress stops in the middle.
3. **It can hold resources.** Nobody keeps the handles of the three tasks of `AlSocket`. They
   hold the WebSocket open until the connection ends. Thus `AlSocket` needs a `Drop` that ends
   them ([Async 6](#guide-async-6-cancellation-timeouts-and-errors)).

Keep each `JoinHandle`, or use a `JoinSet`, unless the task is truly independent of the rest.

</div>

<div data-lang="java">

In Java, concurrency and parallelism come together. Each thread that you start can run on its own core at the same moment. Thus "start two things" also means "two things touch memory at the same time". This chapter covers how to start work, and how to wait for all of it, for the first result, or for each result in turn. Chapter [Async 7](#guide-async-7-shared-state) covers the memory side.

#### Three ways to start work

| Call | What runs the work | What you get |
|---|---|---|
| `Thread.ofVirtual().start(r)`, `Thread.startVirtualThread(r)` | a new virtual thread | a `Thread`: `join()` waits for its end |
| `executor.submit(callable)` | a thread of the executor | a `Future<T>`: `get()` waits for the result or the error |
| `CompletableFuture.supplyAsync(fn)` | the common pool (or the executor that you pass) | a `CompletableFuture<T>` |

For blocking work, such as a character loop that calls `request`, use a virtual thread. A virtual thread for each task is the normal Java 21 style. Do not pool virtual threads: they are cheap, and a pool only limits them. To limit concurrency (for example, at most 3 requests at a time), use a `Semaphore`.

`Executors.newVirtualThreadPerTaskExecutor()` gives an `ExecutorService` that starts a new virtual thread for each `submit`. Since Java 19, `ExecutorService` is `AutoCloseable`. Its `close()` waits until each submitted task ends. A try-with-resources block thus cannot end while one of its tasks still runs.

Do not use `supplyAsync` without an executor for blocking work. It puts the work on the common pool. That pool is small (cores minus 1) and it also runs the last stage of each `AlSocket` waiter. Blocking calls there make every `waitFor` slow.

#### Waiting for all, the first, or each

```java
// Together.java: start work without waiting, then wait for all, for the first, or for each.
// Run: java Together.java
import java.util.List;
import java.util.concurrent.*;

public class Together {
    // A stand-in for a request: it blocks for `ms`, then returns a result.
    static String reply(String name, long ms) throws InterruptedException {
        Thread.sleep(ms);
        return name + " after " + ms + " ms";
    }

    public static void main(String[] args) throws Exception {
        // 1. One virtual thread per task. close() (end of try) waits for every task.
        try (ExecutorService pool = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> a = pool.submit(() -> reply("ranger", 300));
            Future<String> b = pool.submit(() -> reply("priest", 100));
            System.out.println("all:   " + a.get() + ", " + b.get()); // wait for both

            // 2. The first that succeeds; invokeAny cancels the others.
            String first = pool.invokeAny(List.of(() -> reply("slow", 500), () -> reply("fast", 50)));
            System.out.println("first: " + first);

            // 3. Each as it ends: a CompletionService gives the futures in end order.
            var cs = new ExecutorCompletionService<String>(pool);
            cs.submit(() -> reply("c", 200));
            cs.submit(() -> reply("d", 50));
            System.out.println("each:  " + cs.take().get() + ", then " + cs.take().get());

            // 4. Fire and forget: the exception goes into a Future that nobody reads.
            pool.submit(() -> { throw new IllegalStateException("lost"); });
        }
        // The same with CompletableFuture: allOf / anyOf. supplyAsync uses the common pool.
        var x = CompletableFuture.supplyAsync(() -> "x");
        var y = CompletableFuture.supplyAsync(() -> "y");
        CompletableFuture.allOf(x, y).join();
        System.out.println("allOf: " + x.join() + y.join());
        // A plain thread that throws: the default handler prints the stack trace.
        Thread.startVirtualThread(() -> { throw new IllegalStateException("printed"); }).join();
        System.out.println("end");
    }
}
```

```text
all:   ranger after 300 ms, priest after 100 ms
first: fast after 50 ms
each:  d after 50 ms, then c after 200 ms
allOf: xy
Exception in thread "" java.lang.IllegalStateException: printed
	at Together.lambda$main$9(Together.java:38)
	at java.base/java.lang.VirtualThread.run(VirtualThread.java:329)
end
```

The tools in order:

- **All:** `get()` on each `Future`, or `invokeAll(tasks)`. For `CompletableFuture`, `allOf(...)` gives a `CompletableFuture<Void>` that completes when all complete. It fails if one fails, but only after all of them end.
- **First:** `invokeAny(tasks)` returns the first result that succeeds and cancels the rest. `CompletableFuture.anyOf(...)` completes with the first result or the first error. It cancels nothing.
- **Each in end order:** an `ExecutorCompletionService` puts each future in a `BlockingQueue` when it ends. `take()` gives them in that order.

#### Structured concurrency

The try-with-resources executor is a weak form of **structured concurrency**: tasks cannot outlive the block. It has two gaps. A failure of one task does not cancel the others. And the `close()` waits for every task, also the ones whose result you no longer need.

Java has an API for the full model, `java.util.concurrent.StructuredTaskScope`. In Java 21 it is a **preview API** (JEP 453). It needs `--enable-preview`, and its shape changed in later releases. The course does not use it, and this lecture does not teach it.

#### Fire and forget

Fire and forget is risky in Java for one reason: an error has no default reader.

- `executor.submit(...)` keeps the exception in its `Future`. If nobody calls `get()`, nobody sees it. The `"lost"` task above printed nothing.
- `Thread.start` with no `Future`: an uncaught exception ends that thread only. The default handler prints the stack trace on `System.err`. The program continues.
- `supplyAsync` and every other `CompletableFuture` stage keep the exception in the future. Nothing prints it.

The course has one fire-and-forget call on purpose: `emit`. `AlSocket.emit` returns the future of the send, and `Budget.emit` does not wait for it. Nobody reads that future, so `Budget.emit` adds a stage that logs a failure:

```java
sock.emit(event, payload).whenComplete((r, e) -> {
    if (e != null) System.err.println("budget: send of \"" + event + "\" failed: " + e);
});
```

A send fails only when the connection is gone. Then the local `disconnect` event and the failed waiters report it too. The log line makes sure that the failure is never silent.

#### AL: two characters in one program

`PartyMerchant` runs each fighter on its own virtual thread and the merchant on `main`:

```java
List<Thread> fighting = new ArrayList<>();
for (Crew f : crew.subList(0, crew.size() - 1)) {
    fighting.add(Thread.ofVirtual().name("fighter-" + f.m().name()).start(() -> {
        try {
            fighterLoop(f);
        } catch (InterruptedException e) {
            // the program ends
        } catch (RuntimeException e) {
            failed.compareAndSet(null, f.m().name() + ": " + e.getMessage()); // the first error wins
            System.out.println(f.m().name() + " failed: " + e.getMessage() + "; stop");
            stop = true;
        }
    }));
}
```

Each fighter has its own `AlSocket`, thus its own listener calls and its own dispatcher. Each fighter loop blocks in `Thread.sleep` and in `request`. The virtual threads unmount at each block, so three loops and three dispatchers share a few carriers. At the end, the merchant sets `stop` and calls `join()` on each fighter thread.

The `catch (RuntimeException e)` is the structured part, done by hand. An earlier version caught only `InterruptedException`. A fighter whose socket closed then died with a stack trace, and the others played on without it. Now the first error sets the `volatile` flag `stop`. The other fighters and the merchant read it, end their loops, and close every socket in a `finally`. The program then prints `FAILED:` with that first error and exits with status 1.

#### AL: a request with a timeout

There are three timeouts, and they differ:

```java
var w = sock.waitFor("game_response", Actions.responseFor("attack"), Duration.ofSeconds(2)); // fragment
JsonNode r1 = w.get(2, TimeUnit.SECONDS);      // a limit on THIS wait; w stays incomplete
var w2 = w.orTimeout(2, TimeUnit.SECONDS);     // fails w itself; each waiter of w sees the failure
var w3 = w.completeOnTimeout(NullNode.instance, 2, TimeUnit.SECONDS); // fills w with a default value
```

`waitFor` uses `orTimeout` on the inner box. Thus the timeout also removes the waiter from the socket, through `whenComplete`. A `get(t, unit)` alone does not do this: the box stays incomplete, so the waiter stays in the list. Thus `request` cancels its future in a `finally`. If an interrupt ends the wait early, the socket forgets the waiter at once.

#### AL: a tick that runs while handlers run

`Farm` runs `farmer.tick()` on `main` every 100 ms. The dispatcher runs the handlers of `World`, `Cooldowns` and `Farmer` at the same time, on its virtual thread. The two meet only in shared objects behind locks. A slow tick does not delay a handler, and a slow handler does not delay a tick. The exception: one of them holds a lock that the other needs.

</div>

## Async 6: Cancellation, timeouts and errors

Work that started must sometimes stop: a reply does not come, the socket closes, or you press
Ctrl-C. This chapter shows how your language stops work and how it puts a time limit on a wait. It
also shows where an error goes when async code fails.

<div data-lang="js ts">

#### A promise cannot be cancelled

Async 3 said that a promise is a result, not the work. That is why JavaScript has no
`promise.cancel()`. Nothing in a promise knows how to stop the timer, the socket or the loop
that will settle it. You can only stop waiting: stop reading the result. Then the work
continues, and its result goes nowhere.

Thus cancellation in JavaScript is cooperative. The code that does the work must check a
signal, and stop itself. The standard signal is **`AbortSignal`**, from an
**`AbortController`**:

- `controller.abort(reason)` sets `signal.aborted` to `true`, stores `signal.reason`, and fires
  the `abort` event of the signal.
- `AbortSignal.timeout(ms)` is a signal that aborts itself after `ms`, with a `TimeoutError`.
- `AbortSignal.any([a, b])` aborts when the first of its inputs aborts.
- Many APIs of Node.js take `{ signal }`: `fetch`, `timers/promises`, `events.once`, `fs`
  reads, and child processes. They reject with an `AbortError` when the signal aborts.

```js
// abort.mjs: cancellation in JavaScript is a signal that the code checks.
import { setTimeout as sleep } from "node:timers/promises";

const t0 = performance.now();
const at = () => `${String(Math.round(performance.now() - t0)).padStart(3)} ms`;

// 1. A timeout signal. The sleep of node:timers/promises listens to it.
try {
  await sleep(1000, undefined, { signal: AbortSignal.timeout(100) });
} catch (err) {
  console.log(at(), "1.", err.name, "because of", err.cause.name); // cause: the reason of the signal
}

// 2. Your own controller: one abort() stops each wait that got its signal.
const stop = new AbortController();
setTimeout(() => stop.abort(new Error("Ctrl-C")), 100);
const results = await Promise.allSettled([
  sleep(1000, "a", { signal: stop.signal }),
  sleep(1000, "b", { signal: stop.signal }),
]);
console.log(at(), "2.", results.map((r) => `${r.status} (${r.reason.cause.message})`).join(", "));

// 3. A promise without a signal cannot be stopped. race() only stops the wait.
const work = sleep(300).then(() => console.log(at(), "3. the slow work still ended"));
const winner = await Promise.race([work, sleep(50, "timeout")]);
console.log(at(), "3. race gave:", winner);
```

```text
107 ms 1. AbortError because of TimeoutError
211 ms 2. rejected (Ctrl-C), rejected (Ctrl-C)
262 ms 3. race gave: timeout
512 ms 3. the slow work still ended
```

The times can differ by a few ms. Case 1 and case 2 cancel the work: the `sleep` cleared its
timer. Case 3 only stops the wait.

An aborted wait does not disappear. It **rejects**, and the rejection travels up through each
`await`, as an exception does. Each `finally` on the way runs. That is your cleanup point. Put
the code that must run (close a socket, remove a waiter, clear a timer) in `finally`.

#### A wait that never ends

There is one trap in this model. An async function that awaits a promise that never settles
stays suspended forever. Its `finally` never runs. When nothing references that promise, the
garbage collector removes the frame, and nothing reports it. Thus each wait needs an exit:
a timeout, a signal, or the end of its source. Each `AlSocket` waiter has two such exits, its
timer and `#shutdown`.

#### How the course cancels

The course uses no `AbortSignal`. It uses two other forms of cooperative cancellation:

- **Timeouts on each wait.** `waitFor` rejects after `timeoutMs`. `request` turns that
  rejection into `null`: "no reply". The waiter is gone, and `done()` cleared its timer. The
  server is not told. The `attack` can still succeed after your timeout.
- **A flag that the loops check.** In `farm.js`, `SIGINT` sets `stop = true`. Each loop checks
  `stop` at the top. The `wait` function sleeps in steps of 200 ms and checks `stop` after each
  step. So Ctrl-C ends the program within one tick, with a clean `close`.

If you add a signal to your own client, give `waitFor` an optional `signal`, and call
`w.reject(signal.reason)` from its `abort` event. Remove that listener in `done()`.

#### How an error travels

In an async function, `throw` rejects the result promise. In the caller, `await` on that
promise throws the same error, at the line of the `await`. So `try`/`catch` around `await`
works as it does around synchronous code. The error crosses each task boundary on the way.
V8 still shows the chain of awaiting functions in the stack trace
([Async 9](#guide-async-9-seeing-it-run)).

A rejection that no `await` and no `catch` receives is an **unhandled rejection**. V8 tells
Node.js about each promise that rejects with no handler. Node.js keeps a list. After the
current task and its microtasks end, it checks the list. A promise that still has no handler
then counts as unhandled.

Since Node.js 15, the default mode is `--unhandled-rejections=throw`. Node.js first emits the
`unhandledRejection` event on `process`. If no listener handles it, Node.js throws the reason
as an uncaught exception, and the process stops with exit code 1. Before Node.js 15, it only
printed a warning.

```js
// unhandled.mjs: a rejection that nobody handles in time stops Node.js.
const reply = Promise.reject(new Error("socket closed")); // like a waiter after a close
console.log("1. a rejected promise, with no handler yet");
await null; // microtasks run; the promise is still unhandled
console.log("2. still running after one microtask turn");
setTimeout(() => {
  console.log("3. too late: a handler in the next macrotask");
  reply.catch(() => {});
}, 0);
```

```text
1. a rejected promise, with no handler yet
2. still running after one microtask turn
file:///w/unhandled.mjs:2
const reply = Promise.reject(new Error("socket closed")); // like a waiter after a close
                             ^

Error: socket closed
    at file:///w/unhandled.mjs:2:30
    at ModuleJob.run (node:internal/modules/esm/module_job:343:25)
    at async onImport.tracePromise.__proto__ (node:internal/modules/esm/loader:681:26)
    at async asyncRunEntryPointWithESMLoader (node:internal/modules/run_main:117:5)

Node.js v22.23.3
```

The exit code is 1. The handler can come late inside the same task, but not in a later task.
The `request` pattern keeps a promise (`reply`) across an `await`. While `request` waits for the
`Budget`, `reply` has no handler. That is safe while `reply` is still pending. It is not safe if
`reply` is already rejected.

In TypeScript with `strict`, the variable of `catch (err)` has the type `unknown`. A rejection
can carry any value, not only an `Error`. Check it with `err instanceof Error` before you read
`err.message`.

#### AL: what happens to each waiter when the socket closes

When the WebSocket closes for any cause, its `close` listener calls `#shutdown`:

```js
// fragment: course/js/albot/alsocket.js
  #shutdown(reason) {
    if (this.#closed) return;
    this.#closed = true;
    if (this.#closeTimer) clearTimeout(this.#closeTimer);
    // socket.io-client reports the end as a local "disconnect" event, and so
    // does AlSocket. The server never sends an event with this name.
    this.#listening = true;
    this.#deliver("disconnect", reason);
    // Copy, clear, then fail each one: w.reject() removes w from the set.
    const waiters = [...this.#waiters];
    this.#waiters.clear();
    for (const w of waiters) w.reject(new Error(`socket closed: ${reason}`));
  }
```

In order: the socket marks itself closed, your `disconnect` handlers run, then each waiter
rejects with `socket closed: <reason>`. Each `w.reject` calls `done()`, which clears the timer and
removes the waiter from the set. Thus `#shutdown` first copies the set and clears it, and then
fails the copies. A loop must not iterate a collection that its own body changes. No waiter
stays behind, and each one fails one time. From then on, `emit` throws `socket is closed`, and `waitFor` returns a
promise that is already rejected.

That last fact meets a gap of the `request` pattern. On a closed socket, `waitFor` rejects at
once. Then `budget.emit` throws, and `request` leaves before `await reply`. In an earlier
version of the course, nothing handled `reply` on that path. The caller could catch the error of
`request`, and the process still stopped. That version printed this, after `request threw`:

```text
Error: socket is closed
    at file:///w/course/albot/alsocket.js:140:39
    at new Promise (<anonymous>)
    at AlSocket.waitFor (file:///w/course/albot/alsocket.js:139:12)
    at Actions.request (file:///w/course/albot/actions.js:64:29)
```

The fix is one line, right after `waitFor`: `reply.catch(() => {})`. It adds a reaction to
`reply`, so its rejection has a handler from the start. The `catch` makes a new promise and
does not change `reply`. The `await reply` later still gets the same rejection, so a timeout
still gives `null`, and a closed socket still throws. This program shows the fixed code against
the test server:

```js
// closed-request.js: a request on a closed socket, in the JS course code.
import { Bot } from "./albot/bot.js";

const bot = await Bot.connect();
bot.sock.on("disconnect", (reason) => console.log("disconnect:", reason));
bot.close();
await new Promise((r) => setTimeout(r, 200)); // the close event arrives

try {
  await bot.act.request("use", { item: "hp" });
} catch (err) {
  console.log("request threw:", err.message);
}
await new Promise((r) => setTimeout(r, 100));
console.log("still running"); // the old code never got here
```

```text
downloaded G version 17478
disconnect: transport closed (code 1000)
request threw: socket is closed
still running
```

The TypeScript `request` had no such crash, but it had a different fault. It used
`.then(normalize, () => null)`, which turns each rejection into `null`. Thus a socket that closed
during the wait looked like "no reply", and the caller did not learn of the close. Now the TS
`request` has the same shape as the JS one:

```ts
// fragment: course/ts/albot/actions.ts
    // The wait starts here, before the emit.
    const reply = this.sock.waitFor("game_response", responseFor(place), timeoutMs);
    // Mark a failure of `reply` as handled now. If budget.emit() throws (the
    // socket is closed), we leave before `await reply`, and Node.js would stop
    // the process for its unhandled rejection. The `await reply` below still
    // gets the same rejection.
    reply.catch(() => {});
    await this.budget.emit(event, payload);
    try {
      return normalize(await reply);
    } catch (err) {
      if (err instanceof Error && err.message.startsWith("timed out")) return null; // no reply in time
      throw err; // the socket closed: the caller must know
    }
```

The same program as `closed-request.ts`, in `course/ts`, prints the same four lines. Use this
pattern each time that you keep a promise across an `await`: attach a handler at once, and
await the promise later.

</div>

<div data-lang="python">

#### Cancellation is an exception at an `await`

`task.cancel()` does not stop a task. It asks the task to stop. The task stops only at its
next suspension. The call does two things:

- If the task waits for a future, `cancel` cancels that future (`_fut_waiter.cancel()`). The
  wake-up of the task then runs, finds a cancelled future, and calls
  `__step(CancelledError())`.
- If the task is in the ready queue, `cancel` sets a flag, `_must_cancel`. The next step
  throws `CancelledError` instead of a `send`.

In both cases, the Task uses `coro.throw(CancelledError())`. The exception appears at the
`await` where the coroutine paused. From there it travels up like any exception. `finally`
blocks run. `async with` blocks run their exit. If the coroutine lets the exception out, the
Task enters the state `CANCELLED`.

```python
# cancel_basics.py: what task.cancel() does, step by step.
import asyncio


async def tick_loop() -> None:
    try:
        while True:
            try:
                await asyncio.sleep(1)  # CancelledError comes out of THIS await
            except Exception:
                print("   never printed: CancelledError is not an Exception")
    finally:
        print("   finally: close files, remove waiters, ...")


async def main() -> None:
    task = asyncio.create_task(tick_loop())
    await asyncio.sleep(0.1)
    print("1. cancel() returns", task.cancel(), "- a request, not a stop")
    print("2. done right after cancel()?", task.done())
    try:
        await task
    except asyncio.CancelledError:
        print("3. await task raised CancelledError; cancelled():", task.cancelled())
    print("4. CancelledError is a BaseException:",
          issubclass(asyncio.CancelledError, BaseException),
          "| an Exception:", issubclass(asyncio.CancelledError, Exception))


asyncio.run(main())
```

It prints:

```text
1. cancel() returns True - a request, not a stop
2. done right after cancel()? False
   finally: close files, remove waiters, ...
3. await task raised CancelledError; cancelled(): True
4. CancelledError is a BaseException: True | an Exception: False
```

Three consequences:

- **Nothing can cancel the code between two `await`s.** A long path search with no `await`
  inside runs to its end. A blocking call such as `time.sleep` also runs to its end.
- **`CancelledError` is a `BaseException`** (since Python 3.8). Thus `except Exception` does
  not catch it, and a retry loop with `except Exception: continue` does not eat a
  cancellation. If you catch it yourself, re-raise it.
- **A task can refuse.** A coroutine that catches `CancelledError` and continues breaks the
  tools above it. `TaskGroup` and `asyncio.timeout` count cancellations with
  `Task.cancelling()` and `Task.uncancel()` (Python 3.11+). They work only if the error
  arrives where they expect it.

#### A cancelled wait in `AlSocket`

The waiter needs no special code for cancellation. If you cancel a task that waits in
`result()`, the Task cancels the future of the waiter. A cancelled future has left
`PENDING`, so its done callback, `cleanup`, runs. `cleanup` cancels the timer and removes the waiter from
`_waiters`. The output of `cancel_socket.py` below shows it (lines 1 and 2).

#### Timeouts: two kinds

`asyncio.timeout(seconds)` (Python 3.11+) is a context manager. At entry, it schedules a timer
with `loop.call_at`. If the timer fires, it cancels the current task. At exit, it sees the
`CancelledError` that it caused, and raises `TimeoutError` instead, with the
`CancelledError` as `__cause__`. Since 3.11, `asyncio.TimeoutError` is the built-in
`TimeoutError`. In 3.12, `asyncio.wait_for` uses `asyncio.timeout` inside.

```python
# cancel_timeout.py: asyncio.timeout cancels the block, then raises TimeoutError.
import asyncio


async def slow_reply() -> str:
    try:
        await asyncio.sleep(5)
        return "reply"
    except asyncio.CancelledError:
        print("   inside: CancelledError at the await")
        raise


async def main() -> None:
    try:
        async with asyncio.timeout(0.1):  # Python 3.11+
            await slow_reply()
    except TimeoutError as err:
        print("1. outside: TimeoutError; it is asyncio.TimeoutError:",
              TimeoutError is asyncio.TimeoutError, "| cause:", type(err.__cause__).__name__)
    # shield: the timeout cancels the WAIT, not the work inside.
    work = asyncio.create_task(asyncio.sleep(0.2, result="the work ended"))
    try:
        async with asyncio.timeout(0.1):
            await asyncio.shield(work)
    except TimeoutError:
        print("2. the wait timed out; the work continues:", await work)


asyncio.run(main())
```

It prints:

```text
   inside: CancelledError at the await
1. outside: TimeoutError; it is asyncio.TimeoutError: True | cause: CancelledError
2. the wait timed out; the work continues: the work ended
```

The timer of an `AlSocket` waiter is the other kind. `expire` does not cancel a task. It sets
`TimeoutError` on the future, as a result. The task that awaits the future gets that error
at its `await`. No `CancelledError` occurs. `request` catches `TimeoutError` and returns
`None`.

`enter_game` uses both kinds. Each `wait_for` has its own timer. An `asyncio.timeout` around
the whole handshake limits the total time.

Neither kind stops the server. A timeout ends your wait, but the `attack` is already on the
wire. The server can still do it, and the `game_response` can still arrive. It then matches no
waiter, and only the handlers see it.

#### How an error travels

A coroutine raises. The Task catches the exception in `__step` and stores it with
`set_exception`. The Task is a Future, so it queues its callbacks. A coroutine that awaits the
task resumes, `Future.__await__` calls `result()`, and `result()` raises the stored exception
again, in the awaiter, at its `await`. The traceback has the frames of both coroutines.

Thus an exception in async code travels the same way as in plain code, as long as someone
awaits each task. The problems start where nobody awaits.

#### Errors that nobody observes

A Future that holds an exception records whether someone read it, with `result()` or
`exception()`. When the garbage collector frees a Future with an exception that nobody read,
`Future.__del__` reports it to the exception handler of the loop. The default handler logs it
to the `asyncio` logger. The message is "Future exception was never retrieved", or "Task
exception was never retrieved" for a Task. 

**The program continues.** Unlike Node.js, Python does not stop on such an error. You see a
log line, possibly much later, and the bot continues with a broken part.

The first version of the course made both messages. An `async def` handler raised. Then the
bot called `request` on a closed socket. The log showed this, and the bot continued:

```text
Task exception was never retrieved
future: <Task finished name='Task-3' coro=<main.<locals>.bad_handler() done, defined at cancel_unseen.py:19> exception=KeyError('mp')>
Traceback (most recent call last):
  File "cancel_unseen.py", line 21, in bad_handler
    raise KeyError("mp")  # AlSocket runs this coroutine as a task; nobody awaits it
    ^^^^^^^^^^^^^^^^^^^^
KeyError: 'mp'
request raised: socket is closed
cancel_unseen.py:30: RuntimeWarning: coroutine 'AlSocket.wait_for.<locals>.result' was never awaited
  print("request raised:", err)
RuntimeWarning: Enable tracemalloc to get the object allocation traceback
Future exception was never retrieved
future: <Future finished exception=ConnectionError('socket is closed')>
ConnectionError: socket is closed
main ends
```

Three objects were never observed:

1. **The task of the handler.** `_deliver` made it with `ensure_future` and dropped it. Nobody
   called `result()`, so Python logged the error when it freed the task. That can be much
   later than the error, or never.
2. **The coroutine `reply`.** On a closed socket, `emit` raised before `await reply`. A
   coroutine that never starts gives "was never awaited" when Python frees it.
3. **The future inside `reply`.** `wait_for` put `ConnectionError` in it at once. Nobody read
   it, so Python logged "Future exception was never retrieved".

The fix has one part for each object:

1. `_deliver` keeps each handler task in `_handler_tasks`. A done callback, `_handler_done`,
   removes the task and prints its error at once, with its traceback.
2. `request` closes `reply` when the send fails. `close()` on a coroutine that never started
   only marks it as finished, so Python has nothing to warn about.
3. `wait_for` adds the done callback `_retrieve` to each future. It calls `fut.exception()`,
   so asyncio counts the error as read. This does not hide the error: `await` still raises it.

This fragment runs the same steps with the fixed code. Its `request` has the steps of the new
`Actions.request`, without the budget:

```python
# cancel_unseen.py (fragment: `url` is a fake game server that answers
# `attack` with `player`)
async def request(sock: AlSocket, event: str, payload: object) -> object:
    # The steps of Actions.request, without the budget.
    reply = sock.wait_for("game_response", lambda d: d.get("place") == event, timeout=2)
    try:
        await sock.emit(event, payload)  # raises on a closed socket
    except BaseException:
        reply.close()  # nobody will await `reply`: close it
        raise
    return await reply


async def main(url: str) -> None:
    sock = await AlSocket.connect(url)

    async def bad_handler(data: object) -> None:
        await asyncio.sleep(0)
        raise KeyError("mp")  # AlSocket runs this coroutine as a task

    sock.on("player", bad_handler)
    await sock.emit("attack", {"id": "goo1"})  # the fake answers with `player`
    await asyncio.sleep(0.2)
    await sock.close()
    try:
        await request(sock, "attack", {"id": "goo1"})
    except ConnectionError as err:
        print("request raised:", err)
    gc.collect()  # make the logs come now, not at the end
    print("main ends")
```

It prints:

```text
Traceback (most recent call last):
  File "cancel_unseen.py", line 25, in bad_handler
    raise KeyError("mp")  # AlSocket runs this coroutine as a task
    ^^^^^^^^^^^^^^^^^^^^
KeyError: 'mp'
request raised: socket is closed
main ends
```

The handler error now comes at once, from `_handler_done`. The request error comes once, from
the `await` that raised it. Your own "wait_for, then emit" code needs the same `close()`:
`wait_for` cannot know that you will never await its coroutine.

To make other unobserved errors loud, install your own handler with
`loop.set_exception_handler`. It can log the error and stop the bot.

#### When the socket closes

The reader task ends its `async for` when the connection ends. Then its `finally` calls
`_shutdown`:

```python
        self._closed = True
        # socket.io-client reports the end as a local "disconnect" event, and
        # so does AlSocket. The server never sends an event with this name.
        self._listening = True
        self._deliver("disconnect", reason)
        # Take the list, then fail each waiter in it, one time. (cleanup runs
        # later, from the loop, and finds its waiter gone: that is fine.)
        waiters, self._waiters = self._waiters, []
        for _, _, fut in waiters:
            if not fut.done():
                fut.set_exception(ConnectionError(f"socket closed: {reason}"))
```

In this order: the handlers of `disconnect` run, then each open waiter gets `ConnectionError`.
`_shutdown` takes the list before it fails the waiters.

In Python, iteration over the live list
was also safe, because `set_exception` only queues `cleanup`. But a list that nothing else can
change is easier to trust, and `cleanup` now accepts a waiter that is already gone.
Each task that waits for a reply resumes later, with that error at its `await`. A later
`emit` raises `ConnectionError("socket is closed")`. A later `wait_for` returns a coroutine
that raises the same error.

```python
# cancel_socket.py (fragment: `url` is a fake game server that closes the
# socket after 0.5 s)
async def main(url: str) -> None:
    sock = await AlSocket.connect(url)  # the fake closes the socket after 0.5 s
    sock.on("disconnect", lambda reason: print("3. handler: disconnect:", reason))

    # A wait that we cancel: its future is cancelled too, and cleanup removes it.
    task = asyncio.create_task(sock.wait_for("start", timeout=10))
    await asyncio.sleep(0)
    print("1. waiters:", len(sock._waiters))
    task.cancel()
    await asyncio.sleep(0)  # the task runs its cancellation ...
    await asyncio.sleep(0)  # ... and the done callback (cleanup) runs one pass later
    print("2. waiters after cancel:", len(sock._waiters))

    # A wait that the close ends.
    try:
        await sock.wait_for("game_response", timeout=10)
    except ConnectionError as err:
        print("4. waiter:", err)
    try:
        await sock.emit("attack", {"id": "goo1"})
    except ConnectionError as err:
        print("5. emit:", err)
```

It prints:

```text
1. waiters: 1
2. waiters after cancel: 0
3. handler: disconnect: transport closed (code 1000)
4. waiter: socket closed: transport closed (code 1000)
5. emit: socket is closed
```

There is a short gap between the end of the TCP connection and `_shutdown`. In that gap,
`emit` passes its `_closed` check, and `ws.send` raises the `ConnectionClosed` of
`websockets`. That class is an `Exception`, but not a `ConnectionError`. An earlier version
let it out, so the caller got a different error in the gap. Now `emit` catches it and raises
`ConnectionError("socket is closed")`, the same error as after `_shutdown`.

</div>

<div data-lang="go">

Go has no forced cancellation. Nothing can stop a goroutine from the outside. A goroutine
stops because it reads a signal and returns. This chapter shows that signal (`context`), how
cleanup works (`defer`), how errors travel, and what a `panic` does.

#### `context`: a signal that goes down a tree

A `context.Context` carries a `Done()` channel, an error, and an optional deadline.

- `context.Background()` is the root. It never ends.
- `context.WithCancel(parent)` gives a child and a `cancel` function.
- `context.WithTimeout(parent, d)` gives a child that ends after `d`, or when you call
  `cancel`, or when the parent ends.
- When a context ends, the runtime closes its `Done()` channel. Each child ends too. A close
  wakes every goroutine that waits on the channel.
- `ctx.Err()` then returns `context.Canceled` or `context.DeadlineExceeded`.

```text
   signal.NotifyContext(Background)        ends on Ctrl-C
      |
      +-- WithTimeout(ctx, 30 s)            EnterGame: the whole handshake
      |      |
      |      +-- the waiter of "welcome"    ends at 30 s, or at Ctrl-C
      |
      +-- errgroup.WithContext(ctx)         ends at the first error
             +-- character 1
             +-- character 2
```

A context is a request to stop, not an order. It has an effect only where code reads it:

- **A `select` with `case <-ctx.Done()`.** The waiter of `Expect` and the `wait` helper of
  `cmd/farm` do this.
- **A function that takes a `ctx`.** Most I/O libraries take one: `websocket.Dial`,
  `conn.Read`, `conn.Write`, `http.NewRequestWithContext`.
- **A loop that checks `ctx.Err()`** at each iteration. The tick loop of `cmd/farm` checks it
  in `running()`.

Code that does not read it does not stop. `time.Sleep` does not read a context. To make a
sleep that stops, use a `select` on a timer and `ctx.Done()`. `budget.Emit` does this when it
waits for room in the budget:

```go
		timer := time.NewTimer(wait)
		select {
		case <-timer.C:
		case <-ctx.Done(): // Ctrl-C or the end of the group: do not wait up to 4 s
			timer.Stop()
			return ctx.Err()
		}
```

#### A context for the whole session

A Go convention says: pass the `ctx` as the first parameter of each function that waits. The
course follows it for each network call of `api` and `bot`. But `Attack`, `Heal`, `MoveTo`,
`WalkTo` and `Tick` have no `ctx` parameter. Thus a Ctrl-C used to end the tick loop only at
its next tick. A `Request` in progress waited its full 2 s, and a `Respawn` its full 12 s.

The course now keeps one context for the session in `Actions`. `SetContext` sets it, and
gives it to `Budget` too:

```go
		// Ctrl-C also ends a wait in progress (a reply, a walk, the 12 s
		// before a respawn), not only the loop at its next tick.
		b.Act.SetContext(ctx)
```

Each wait of `Actions`, `Budget`, `Items` and `Travel` then reads it. This is a compromise. A
context in a struct is against the usual advice, because it hides who can end a call. Here it
keeps the signatures of four packages, and one line in the program covers all of them. Set it
one time, before the first action. Do not use it for a deadline of one call.

Each `WithCancel` and `WithTimeout` gives a `cancel` function. Call it when the work ends,
usually with `defer cancel()`. Until then, the parent keeps a reference to the child, and a
timeout keeps its timer. `go vet` reports a `cancel` that some path does not call (the
`lostcancel` check).

> **Caution:** In `coder/websocket`, the end of the `ctx` of a `Read` or `Write` closes the
> whole connection, not only the call. Thus `readLoop` reads with `context.Background()`. A
> timeout on a read would end the session.

#### What happens to a cancelled wait

When the `ctx` of a wait ends, the waiter of `Expect` does these things:

1. `selectgo` returns the case `<-ctx.Done()`.
2. The waiter locks `s.mu`. It notes if it is still in `s.waiters`, and removes itself.
3. If it was still there, no reply came. A later reply finds no waiter and goes only to the
   handlers. The wait returns the error `waiting for "game_response": context deadline
   exceeded`. The `%w` in its format keeps `context.DeadlineExceeded` inside it.
4. If it was not there, `deliver` took it first: the reply came. The wait then receives the
   reply from `w.ch` and returns it.

Step 4 closes a gap that comes from the random order of `select`. The reply and the deadline
can both be ready when the goroutine runs. Then `select` picks one at random. An earlier
version of `Expect` always trusted that choice. In a test with 200 waits that had both
ready, 97 to 102 returned the deadline error although the reply was in `w.ch`. With the
check, none did.

The lesson: when a `select` has two ready cases, your code must give the same answer for
each.

`Request` turns its own timeout into `ErrNoReply`, and keeps each other error:

```go
	data, err := wait(ctx) // 3. block until the reply, the timeout, the end of the session or of the socket
	if errors.Is(err, context.DeadlineExceeded) && session.Err() == nil {
		return GameResponse{}, ErrNoReply // our own timeout, not the end of the session
	}
```

The test of `session.Err()` is necessary because the timeout is a child of the session
context. If the session ends, the wait ends with the error of the session, for example
`context.Canceled` on Ctrl-C. That is a stop, not "no reply".

A cancelled wait does not cancel the request on the server. The `attack` is already sent.
It can still succeed after your timeout.

#### Cleanup: `defer`

`defer f()` runs `f` when the function returns, by any path: a normal `return`, an error
`return`, or a panic. Deferred calls run in reverse order. The course uses `defer` for three
kinds of cleanup:

- `defer cancel()` after each `WithTimeout`.
- `defer s.mu.Unlock()` (in `World.Dispatch`, `CopyMe` and more), so that an early `return`
  cannot leave the lock held.
- `defer wg.Done()` in a goroutine, so that `Wait` returns also if the goroutine fails.

`defer` runs in the goroutine that registered it. It does not run if another goroutine
panics, because then the whole program ends.

#### Errors are values

A Go function returns its error as a value. The error does not travel by itself. Each caller
must check it and return it. Wrap it with `fmt.Errorf("...: %w", err)` to add context. Test
it with `errors.Is` (for a value such as `alsocket.ErrClosed`) or `errors.As` (for a type
such as `*bot.LoginError`).

An error that nobody checks disappears without a message. Go has no "unhandled rejection".
`_ = sock.Emit(...)` drops the error on purpose. A goroutine that returns an error to nobody
drops it too. This is why `errgroup` and an error channel exist.

#### A panic ends the program

A `panic` unwinds the stack of its goroutine and runs each `defer`. If a deferred function
calls `recover()`, the panic stops there. If no `recover` stops it, **the whole program
ends**, with exit status 2. `recover` works only in the goroutine that panics:

```go
// panicgo: a panic in any goroutine ends the whole program. recover in
// main cannot catch it: recover works only in the goroutine that panics.
package main

import (
	"fmt"
	"time"
)

func main() {
	defer func() { fmt.Println("main's recover:", recover()) }() // never runs
	go func() {
		var m map[string]int
		m["hp"] = 1 // panic: assignment to entry in nil map
	}()
	time.Sleep(100 * time.Millisecond)
	fmt.Println("never printed")
}
```

It prints this on stderr (the paths are shorter here) and ends with exit status 2:

```text
panic: assignment to entry in nil map

goroutine 18 [running]:
main.main.func2()
	.../panicgo/main.go:14 +0x28
created by main.main in goroutine 1
	.../panicgo/main.go:12 +0x3b
```

Thus `alsocket` recovers in each handler and each predicate, on the dispatch goroutine. A
bug in one handler goes to the log. The other handlers and the socket continue:

```go
func safeCall(name string, h Handler, data json.RawMessage) {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("alsocket: handler for %q panicked: %v", name, r)
		}
	}()
	h(data)
}
```

A goroutine that you start yourself has no such guard. If it can panic, put a `recover` in
it, or let the program end. `recover` cannot stop some runtime errors. `fatal error:
concurrent map writes` is one ([Async 7](#guide-async-7-shared-state)).

#### When the socket closes

When the connection ends, `readLoop` notes the reason and closes `s.events`.
`dispatchLoop` gives out each event that is still in the channel. Then it gives the local
`disconnect` event with the reason, sets `closed`, and closes `s.done`. Each waiter then
ends:

| Where the waiter is | What it gets |
|---|---|
| It waits in `select` | The case `<-s.done` fires. A reply that came just before the end still wins: the code checks `w.ch` again. Else `ErrClosed`. |
| It calls `Expect` after the end | `Expect` sees `closed` and does not register. The wait returns `ErrClosed` at once. |
| It has a deadline that ends first | Its `ctx` error, as before. |
| `Emit` after the end | The error of `conn.Write`. |

This program shows the first two rows and the last one. The fake server closes the socket
after 300 ms, and never answers `attack`:

```go
// closed: what each waiter sees when the server closes the socket.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"albot/alsocket"
	"checks/fakeal"
)

func main() {
	fakeal.ServeIfChild()
	// The server never replies to attack, and closes the socket after 300 ms.
	url, stop := fakeal.StartProcess(fakeal.Options{NoReply: true, CloseAfter: 300 * time.Millisecond})
	defer stop()
	sock, err := alsocket.Connect(context.Background(), url)
	if err != nil {
		panic(err)
	}
	sock.On("disconnect", func(d json.RawMessage) { fmt.Println("handler: disconnect", string(d)) })

	// A waiter with no deadline: only the end of the socket can end it.
	wait := sock.Expect("game_response", nil)
	_ = sock.Emit("attack", map[string]any{"id": "goo"})
	_, err = wait(context.Background())
	fmt.Println("waiter:", err, "| is ErrClosed:", errors.Is(err, alsocket.ErrClosed))

	<-sock.Done() // closed after the dispatcher gave out the last event
	_, err = sock.WaitFor(context.Background(), "start", nil)
	fmt.Println("new wait after the end:", err)
	fmt.Println("emit after the end:", sock.Emit("attack", nil) != nil)
}
```

It prints:

```text
handler: disconnect "transport closed (code 1001)"
waiter: alsocket: socket is closed | is ErrClosed: true
new wait after the end: alsocket: socket is closed
emit after the end: true
```

The handler of `disconnect` runs before the waiter wakes. The reason is the order in
`dispatchLoop`: it delivers the last event, then it closes `s.done`.

</div>

<div data-lang="csharp">

.NET cannot stop a task from the outside. No API kills a running task or a thread. Cancellation
is **cooperative**: one part of the code asks, and the work stops at a point that it chooses.
Errors travel the other way, from the work to the code that awaits it.

#### The model: a source and its tokens

A `CancellationTokenSource` (CTS) owns the request. A `CancellationToken` is a read-only view of
it, a small struct that you pass to the work. The two sides have different abilities:

- The **source** can `Cancel()`, or `CancelAfter(ms)`. The constructor `new
  CancellationTokenSource(timeout)` is the same as `CancelAfter`.
- The **token** can tell `IsCancellationRequested`, throw with `ThrowIfCancellationRequested()`,
  and `Register(callback)`.

`Cancel()` sets a flag, then runs the registered callbacks, on the thread that calls `Cancel`.
For `CancelAfter`, that thread is a pool thread that the timer uses. That is all. Nothing
interrupts the code that runs. The work sees the request in one of two ways:

1. Your loop reads the token, at points that you choose, and throws.
2. You pass the token to an API: `Task.Delay`, `ReceiveAsync`, `HttpClient.SendAsync`,
   `SemaphoreSlim.WaitAsync`. The API registers a callback that ends its operation, and the
   await throws.

Both throw `OperationCanceledException`. Its subclass `TaskCanceledException` comes from some
APIs. Always catch `OperationCanceledException`, which covers both. An `async` method that ends
with this exception does not become `Faulted`, but `Canceled`.

```csharp
// cancel: CancellationToken is a request to stop. The work must look at it.
using System.Diagnostics;

var clock = Stopwatch.StartNew();
string T() => $"{clock.ElapsedMilliseconds,4} ms";

// 1. A token that cancels itself after 200 ms. Task.Delay watches the token.
using var cts = new CancellationTokenSource();
cts.CancelAfter(200);
var delay = Task.Delay(5000, cts.Token);
try { await delay; }
catch (OperationCanceledException e) { Console.WriteLine($"{T()} {e.GetType().Name}, task status {delay.Status}"); }

// 2. A loop that checks the token itself (cooperative), with cleanup in finally.
clock.Restart();
using var stop = new CancellationTokenSource(250);
try { await TickLoop(stop.Token); }
catch (OperationCanceledException) { Console.WriteLine($"{T()} tick loop canceled"); }

// 3. Linked tokens: "Ctrl-C" OR "this request takes too long".
clock.Restart();
using var shutdown = new CancellationTokenSource();     // the whole program
using var perRequest = CancellationTokenSource.CreateLinkedTokenSource(shutdown.Token);
perRequest.CancelAfter(1000);                           // this one request
_ = Task.Run(async () => { await Task.Delay(100); shutdown.Cancel(); }); // Ctrl-C at 100 ms
try { await Task.Delay(5000, perRequest.Token); }
catch (OperationCanceledException)
{
    Console.WriteLine($"{T()} canceled by {(shutdown.IsCancellationRequested ? "shutdown" : "timeout")}");
}

// 4. Code that ignores the token does not stop.
clock.Restart();
using var ignored = new CancellationTokenSource(50);
await Task.Run(() => Thread.Sleep(300), CancellationToken.None);
Console.WriteLine($"{T()} Thread.Sleep ran to its end; token canceled: {ignored.IsCancellationRequested}");

// 5. Register: run a callback at cancel. AlSocket uses this for its timeout.
using var timer = new CancellationTokenSource(50);
var waiter = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
timer.Token.Register(() => waiter.TrySetException(new TimeoutException("no reply")));
try { await waiter.Task; } catch (TimeoutException e) { Console.WriteLine($"waiter: {e.Message}"); }

static async Task TickLoop(CancellationToken ct)
{
    var ticks = 0;
    try
    {
        while (true)
        {
            ct.ThrowIfCancellationRequested();
            ticks++;
            await Task.Delay(100, ct);
        }
    }
    finally { Console.WriteLine($"  finally: {ticks} ticks, clean up here"); }
}
```

Output (the times can differ by a few ms):

```text
 208 ms TaskCanceledException, task status Canceled
  finally: 3 ticks, clean up here
 250 ms tick loop canceled
  98 ms canceled by shutdown
 300 ms Thread.Sleep ran to its end; token canceled: True
waiter: no reply
```

A **linked** source (part 3) cancels when any of its parents cancels, or when its own timer
ends. This is the normal form for a request: one token for "the program stops", one timer for
"this request is too slow".

Cleanup is the normal `finally`, `using` and `await using` of C#. They run when the exception of
the cancellation passes, as for any other exception. Dispose each `CancellationTokenSource` that
has a timer. Its timer otherwise stays in the timer queue until it fires.

#### A cancellation can cost the connection

A canceled `ReceiveAsync` on a `ClientWebSocket` does not only end the wait. It aborts the
connection:

```text
TaskCanceledException; socket state now Aborted
```

The program for this line calls `ReceiveAsync` with a 200 ms token. Its server sends nothing.
Thus `AlSocket` uses a token only in `ConnectAsync`, for the 10 s handshake. There, a
failure ends the connection anyway. `ReadLoop` reads with `CancellationToken.None`, and it
ends only when the connection ends. To stop it, close the socket.

#### Three kinds of timeout

| Form | What ends | What you catch |
|---|---|---|
| A token with `CancelAfter`, passed to the operation | The operation itself | `OperationCanceledException` |
| `task.WaitAsync(timeout)` (.NET 6+) | Only your wait. The operation continues. | `TimeoutException` |
| A timer that completes a `TaskCompletionSource` | The waiter, as its owner decides | Whatever the owner sets |

`AlSocket.WaitForAsync` uses the third form:

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, WaitForAsync
var timer = new CancellationTokenSource(timeout ?? TimeSpan.FromSeconds(10));
timer.Token.Register(() =>
{
    lock (_lock) _waiters.Remove(waiter);
    result.TrySetException(new TimeoutException($"timed out waiting for \"{name}\""));
});
result.Task.ContinueWith(t =>
{
    timer.Dispose();
    // Reading Exception marks a failure as observed. Without this, a wait
    // that nobody awaits (for example, the emit after it threw) fails
    // later as an "unobserved task exception". An await still throws.
    _ = t.Exception;
});
```

When the timer ends, the callback removes the waiter and fails the task. The waiter cannot leak.
When the task ends first, for any reason, `ContinueWith` disposes the source and its timer. A
reply after the timeout finds no waiter, and the handlers get it as usual. The last line of the
continuation belongs to the next section.

`RequestAsync` takes no `CancellationToken`. To stop a tick at Ctrl-C without a wait of 2 s,
add `WaitAsync(ct)` to the wait. It ends your wait at once. The waiter still ends at its own
timer, so nothing leaks:

```csharp
// RequestAsync with a CancellationToken. WaitAsync(ct) gives up the WAIT at
// Ctrl-C; the waiter in AlSocket still ends at its own timeout.
public static async Task<GameResponse?> RequestAsync(AlSocket sock, string evt, object payload, CancellationToken ct)
{
    var reply = sock.WaitForAsync("game_response", Actions.ResponseFor(evt), TimeSpan.FromSeconds(2));
    await sock.EmitAsync(evt, payload);
    // A cancel throws OperationCanceledException here. `reply` then ends later,
    // at its timer, and nobody awaits it: AlSocket marks that failure observed.
    try { return Actions.Normalize(await reply.WaitAsync(ct)); }
    catch (TimeoutException) { return null; }
}
```

#### How an error travels

An exception in an `async` method does not go up the stack of threads. It goes into the task
(`SetException`), and the task becomes `Faulted`. The next `await` on that task throws it again
in the awaiting method. Then that method's task holds it, and so on, up the chain of awaits.
The runtime keeps the original stack trace. The line `--- End of stack trace from previous
location ---` marks each place where the exception crossed an `await`.

An exception reaches you only if some code awaits the task (or reads `.Result`, `.Wait()` or
`.Exception`). We call a `Faulted` task that nobody reads **unobserved**. When the garbage collector
finalizes it, the runtime raises `TaskScheduler.UnobservedTaskException`. Since .NET Framework
4.5, the process does not stop:

```csharp
// unobserved: a failed Task that nobody awaits. Its exception goes nowhere,
// until the GC finalizes the task and raises UnobservedTaskException.
TaskScheduler.UnobservedTaskException += (_, e) =>
{
    Console.WriteLine($"UnobservedTaskException: {e.Exception.InnerException!.Message}");
    e.SetObserved(); // only marks it as seen; the process continues either way
};

Forget();
await Task.Delay(100);   // the task has failed by now; nothing happened
Console.WriteLine("100 ms later: no message yet");
GC.Collect();            // the finalizer of the task raises the event
GC.WaitForPendingFinalizers();
Console.WriteLine("the process continues");

// Not inlined, so that no local keeps the task alive in Main.
[System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
static void Forget() => _ = Task.Run(() => throw new TimeoutException("timed out waiting for \"game_response\""));
```

Output:

```text
100 ms later: no message yet
UnobservedTaskException: timed out waiting for "game_response"
the process continues
```

Without the `GC.Collect()`, the message comes at some later collection, or never. Thus an
unobserved exception is a silent one. Subscribe to the event in each bot, and log it.

`async void` is the opposite case. Its exception has no task to go to. With no
`SynchronizationContext`, the runtime throws it on a pool thread, and the process ends:

```csharp
// asyncvoid: an exception in an async void method ends the process.
// AlSocket handlers are Action<JsonElement>, so an async lambda becomes async void.
Action<string> handler = async data =>
{
    await Task.Delay(10);
    throw new InvalidOperationException($"bad {data}");
};
try
{
    handler("hit");      // returns at the first await; the try sees nothing
    Console.WriteLine("handler returned");
}
catch (Exception) { Console.WriteLine("never printed"); }
await Task.Delay(500);
Console.WriteLine("never printed either");
```

Output on Linux (exit code 134, SIGABRT):

```text
handler returned
Unhandled exception. System.InvalidOperationException: bad hit
   at Program.<>c.<<<Main>$>b__0_0>d.MoveNext() in /w/Program.cs:line 6
--- End of stack trace from previous location ---
   at System.Threading.Tasks.Task.<>c.<ThrowAsync>b__128_1(Object state)
   at System.Threading.ThreadPoolWorkQueue.Dispatch()
   at System.Threading.PortableThreadPool.WorkerThread.WorkerThreadStart()
```

The `try` in `Deliver` of `AlSocket` cannot help. The handler returned at its first `await`, and
the exception came later, on another thread. `UnobservedTaskException` cannot help either.
Only a `try`/`catch` inside the lambda can.

#### Each waiter when the socket closes

When the connection ends, for any cause, `ReadLoop` writes a local `disconnect` event and
completes the channel. The dispatcher gives out the last events, then fails each open waiter:

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, Dispatch
List<Waiter> left;
lock (_lock)
{
    _closed = true;
    left = new(_waiters);
    _waiters.Clear();
}
foreach (var w in left) w.Result.TrySetException(new WebSocketException("socket closed"));
```

The copy is the important part. A failed task starts callbacks, and a callback can change the
list: the timer callback of a waiter removes it. If such a callback runs inline, in a loop over
that list, the loop throws `InvalidOperationException`, and the dispatcher dies. An earlier
version failed each waiter inside the loop. In C#, the lock and `RunContinuationsAsynchronously`
kept the callbacks out of the loop, so it did not break. The same loop in the Java course broke.

With a copy, the loop is safe without those two conditions, and each waiter fails exactly once.

This program closes an `AlSocket` with one waiter open, then tries to use it. It uses a copy of
`AlSocket.cs` and the `FakeServer` class of the program in
[Async 4](#guide-async-4-what-await-does):

```csharp
// closed: what each kind of wait does when the AlSocket closes.
// Add the FakeServer class of the trace program, and a copy of AlSocket.cs.
using System.Net;
using System.Net.WebSockets;
using System.Text;
using Albot;

FakeServer.Start("http://localhost:5007/");
var sock = await AlSocket.ConnectAsync("ws://localhost:5007/?EIO=4&transport=websocket");

// A waiter that is still open when the socket closes.
var pending = sock.WaitForAsync("game_response", null, TimeSpan.FromSeconds(30));
await sock.CloseAsync();
try { await pending; }
catch (Exception e) { Console.WriteLine($"open waiter: {e.GetType().Name}: {e.Message}"); }

// A new wait after the close throws at the call, not at the await.
try { _ = sock.WaitForAsync("game_response"); }
catch (Exception e) { Console.WriteLine($"WaitForAsync after close: {e.GetType().Name} at the call"); }

// A send after the close.
try { await sock.EmitAsync("attack", new { id = "1" }); }
catch (Exception e) { Console.WriteLine($"EmitAsync after close: {e.GetType().Name}: {e.Message}"); }
```

Output:

```text
open waiter: WebSocketException: socket closed
WaitForAsync after close: WebSocketException at the call
EmitAsync after close: WebSocketException: The WebSocket is in an invalid state ('Closed') for this operation. Valid states are: 'Open, CloseReceived'
```

So each wait of the course ends: with the reply, with `TimeoutException` at its timer, or with
`WebSocketException` at the close. `RequestAsync` returns `null` only for the timeout. The
`WebSocketException` goes up to the tick loop of `Farm`, which treats it as a lost connection.

One path used to leave a task unobserved. In `RequestAsync`, if `EmitAsync` throws, the method
leaves before `await reply`. The waiter then fails later, at its timer or at the close, and
nobody reads it. Now the continuation of each waiter reads `t.Exception` (the fragment of
`WaitForAsync` above). That read marks the failure as observed. A test that forgets one wait
and then forces a collection shows the difference:

```text
old AlSocket:   unobserved: TimeoutException: timed out waiting for "never"
                unobserved task exceptions: 1
fixed AlSocket: unobserved task exceptions: 0
```

The fix is in `AlSocket`, not in `RequestAsync`, so it also covers `OpenChestAsync` and your own
code. An `await` on the task still throws: only the silent path changed.

</div>

<div data-lang="rust">

Rust has no "cancel" call for a future. It has something simpler: **drop**. A future that
nobody polls makes no progress, and a future that you drop never runs again. Its locals run
their `Drop` code, and that is the cleanup. This chapter explains what that means for each
`.await`, for timeouts, for tasks, and for the waiters of `AlSocket` when the socket closes.

#### Drop is cancellation

A future stops only at an `.await` that returns `Pending`. If its owner drops it there, the
code after that `.await` never runs. Rust drops the variables that the state machine holds at
that point. A `Drop` impl is the Rust form of `finally`.

From the point of view of the future, this cancellation is not a choice. It cannot refuse, delay, or
run async cleanup. But it is also safe in one way: a drop can occur only at an `.await`, never
in the middle of synchronous code. Between two `.await` points, your code runs to the end.

#### Three ways to cancel, and one way not to

```rust
// Cancellation in Rust: a dropped future stops at its last .await, and its
// locals run Drop. JoinHandle reports abort and panic as a JoinError.
use std::time::Duration;

use tokio::time::{sleep, timeout};

// A value that prints when it is dropped: our "finally".
struct Guard(&'static str);
impl Drop for Guard {
    fn drop(&mut self) {
        println!("  drop: {}", self.0);
    }
}

async fn slow_wait() -> &'static str {
    let _g = Guard("the waiter of slow_wait");
    sleep(Duration::from_secs(10)).await; // never ends in this demo
    println!("  this line never runs");
    "reply"
}

#[tokio::main]
async fn main() {
    // 1. timeout drops the inner future when the time ends.
    let r = timeout(Duration::from_millis(50), slow_wait()).await;
    println!("timeout: {r:?}");

    // 2. abort() cancels a spawned task at its next .await.
    let task = tokio::spawn(slow_wait());
    sleep(Duration::from_millis(10)).await; // let it start
    task.abort();
    let e = task.await.unwrap_err();
    println!("abort: is_cancelled = {}", e.is_cancelled());

    // 3. A panic ends only its task. The JoinHandle gets it.
    let task = tokio::spawn(async {
        let _g = Guard("the task that panics");
        panic!("bad payload");
    });
    let e = task.await.unwrap_err();
    println!("panic: is_panic = {}", e.is_panic());

    // 4. A dropped JoinHandle does NOT cancel the task. It runs on, detached.
    drop(tokio::spawn(async {
        sleep(Duration::from_millis(20)).await;
        println!("  the detached task still ran");
    }));
    sleep(Duration::from_millis(50)).await;
    println!("end of main");
}
```

It prints (the panic message goes to stderr, so its place in the output can differ):

```text
  drop: the waiter of slow_wait
timeout: Err(Elapsed(()))
  drop: the waiter of slow_wait
abort: is_cancelled = true

thread 'tokio-runtime-worker' (1322) panicked at src/bin/cancel.rs:38:9:
bad payload
note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
  drop: the task that panics
panic: is_panic = true
  the detached task still ran
end of main
```

1. **`tokio::time::timeout(d, fut)`** returns `Err(Elapsed)` when `d` ends first, and drops
   `fut`. The guard runs, and "this line never runs" never runs.
2. **`JoinHandle::abort()`** marks the task as cancelled. The runtime drops its future at the
   next poll. If the task is in the middle of a poll on another worker, the drop occurs when that
   poll returns. The handle then gives a `JoinError` with `is_cancelled()`.
3. **A panic** in a task unwinds that task only. The runtime catches it, runs the drops, and
   stores the panic in the `JoinHandle`. `is_panic()` is true, and `into_panic()` gives the
   payload back.
4. **A dropped `JoinHandle`** does not cancel anything. Only `abort()`, a dropped `JoinSet`, or
   the end of the runtime cancels a task.

#### Cancel safety

Drop at an `.await` is safe for memory, but not always safe for your data. A future is **cancel
safe** if a drop at any `.await` loses nothing. This matters most in `select!` inside a loop,
where `select!` drops the losing branches on each turn.

- `mpsc::Receiver::recv` is cancel safe. A message that it did not return stays in the
  channel.
- `oneshot::Receiver` is cancel safe when you poll it through `&mut`.
- `tokio::sync::Mutex::lock` is cancel safe, but a drop loses the place in its FIFO queue.
- A read that fills a buffer in several steps (for example `read_exact`) is not. A drop
  loses the bytes that it read so far.

The course's `select!` in `enter_game` owns its five futures. When one wins, `select!` drops
the four others. Each of them holds a `oneshot::Receiver` of a waiter. The drop closes the
receiver, and the dispatcher removes those waiters at its next `deliver`:

```rust
    // Remove waiters whose caller stopped waiting (timeout).
    s.waiters.retain(|w| !w.tx.is_closed());
```

That is cancellation that reaches across tasks without a single "cancel" call. The main
future drops a receiver, and the dispatcher on a worker sees a closed channel.

#### A timeout does not stop the server

The 2 s timeout of `request` ends your wait. It does not undo the `emit`. The frame is already
on the wire, and the server can still act on it. The `game_response` can arrive after the
timeout. Then no waiter matches it, and only the handlers see it. Read the next `player` before
you send the same request again.

#### How errors travel

In async Rust, an error is a value, the same as in synchronous Rust. `?` after an `.await`
returns the `Err` to the caller future, which returns it to its caller, up to `main`. The
course uses one error type for this, `Box<dyn std::error::Error + Send + Sync>`. The `Send +
Sync` part lets an error cross a task boundary inside a `JoinHandle`.

A panic is not a value. It unwinds the stack of the current poll. In a spawned task, the runtime
catches it, as above. On the main future, nothing catches it: `block_on` unwinds, and the
program ends. A panic inside an `AlSocket` handler is a third case: `deliver` wraps each call in
`catch_unwind`, prints a line, and continues with the next handler.

**An error that nobody reads disappears.** There is no "unhandled rejection" in Rust.
`#[must_use]` warns when you ignore a `Result` or a future, but a detached task can still
return `Err` into a `JoinHandle` that nobody awaits. A panic in such a task prints its message
and ends that task. The program continues without it.

An earlier version of `party-merchant` had this problem. It awaited the fighters only after the
last trip, with `if let Ok(Err(e)) = task.await`. A fighter that lost its socket showed its
error only at the end. A fighter that panicked gave `Err(JoinError)`, and the pattern ignored
it. The program then printed "OK".

The course now watches the fighters during the play ([Async 5](#guide-async-5-several-things-at-the-same-time)).
Each fighter task returns its name and its result, and `catch_unwind` turns a panic into a
value. `why_ended` reads all the cases:

```rust
fn why_ended(ended: Ended) -> Option<String> {
    match ended {
        Ok((_, Ok(Ok(())))) => None,
        Ok((name, Ok(Err(e)))) => Some(format!("{name} stopped: {e}")),
        Ok((name, Err(panic))) => {
            // A panic payload is a &str or a String in practice.
            let text = panic.downcast_ref::<&str>().map(|s| s.to_string()).or_else(|| panic.downcast_ref::<String>().cloned());
            Some(format!("{name} panicked: {}", text.unwrap_or_else(|| "?".into())))
        }
        Err(e) => Some(format!("a fighter task failed: {e}")), // aborted: not in this program
    }
}
```

The match has no `_` arm. Thus the compiler checks that each case gives a line or a
deliberate `None`.

#### AL: what happens to each waiter when the socket closes

The end of a connection travels through `AlSocket` in a fixed order:

1. The reader gets a Close frame, an error, or the end of the stream. It leaves its loop with a
   reason. (`close()` and `Drop` can also stop it, see below.)
2. The reader marks the socket as ended, so that `emit` fails from now on. It sends the local
   event `disconnect` with the reason, then ends. The end drops `event_tx`.
3. The dispatcher delivers the events that are still in the channel, then `disconnect`. Your
   `disconnect` handlers run, and a waiter for `disconnect` gets the reason.
4. `recv()` returns `None`, because all senders are gone. The dispatcher sets `closed`, takes
   the list of waiters out of the lock, drops it, and sends `true` on the `watch` channel:

```rust
            let waiters = {
                let mut s = state.lock().unwrap();
                s.closed = true;
                std::mem::take(&mut s.waiters)
            };
            // Dropping the senders fails each wait_for that still waits, one
            // time each. We drop them outside the lock, from our own copy.
            drop(waiters);
            let _ = done_tx.send(true);
```

5. The drop of the list drops each `oneshot::Sender`. Each waiting `rx` completes with `RecvError`. Each
   `wait_for` future returns `Err("socket closed")`.
6. In `request`, `timeout` returns `Ok(Err(..))`. `data?` returns the error to the tick.
   `farm` stores the reason and leaves its play loop.
7. A `wait_for` after this point does not register. It returns `Err("socket is closed")` at
   its first poll.

There is no leak of waiters and no waiter that waits forever. The drop of the senders is the
signal.

#### Close, with a time limit, and close on drop

`close()` sends `41` and a WebSocket close frame, then waits for step 4 on the `watch`
receiver. A server that is gone never answers the close frame. Thus `close()` waits for at most
5 s. Then it stops the connection from our side: a `Notify` makes the reader leave its loop, and
`abort()` stops the writer. With both halves of the WebSocket dropped, the TCP connection
closes. Steps 2 to 5 then run as usual, so your `disconnect` handlers still run.

An earlier version had no time limit and no `Drop`. A drop of `AlSocket` did not close the
connection. The reader held a clone of the writer's sender, for the pongs, so the writer never
ended. The reader continued to answer pings, and the character stayed online.

Now `Drop` sends
the same close frame, and a small task stops the connection after 5 s if the server does not
answer. `Drop` cannot `.await`, so it cannot wait for the end. Call `close().await` when you
can, as `farm` does before each reconnect.

</div>

<div data-lang="java">

Java has no forced cancellation. The JVM cannot stop a thread from the outside in a safe way (`Thread.stop` throws `UnsupportedOperationException` since Java 20). Cancellation is **cooperative**: you ask a thread to stop, and its code decides when.

#### Interruption is the cancellation signal

Each thread has an **interrupt flag**. `t.interrupt()` sets it. Then two things can happen:

- If `t` is in a blocking call that supports interruption, the call ends with `InterruptedException`. Examples are `sleep`, `join`, `BlockingQueue.take`, `Future.get`, `Object.wait`, `Condition.await`. The call clears the flag when it throws.
- If `t` computes, nothing happens. The code must read the flag itself, with `Thread.currentThread().isInterrupted()`.

`InterruptedException` is a checked exception on purpose. It forces each method that blocks to decide what cancellation means. There are two correct answers:

1. Declare `throws InterruptedException` and let it travel up. The course does this in `Actions`, `Travel` and `Farmer.tick`.
2. Catch it, and set the flag again with `Thread.currentThread().interrupt()`, so that the caller still sees the request. `AlSocket.dispatch` does this.

The wrong answer is to catch it and continue. The thread then forgets that someone asked it to stop.

Note: `CompletableFuture.join()` does not react to an interrupt. It continues to wait. Use `get()` in code that must be possible to cancel.

#### `Future.cancel` and `CompletableFuture.cancel`

These two methods have the same signature and different behavior:

```java
// Cancel.java: Future.cancel(true) interrupts the thread; CompletableFuture.cancel does not.
// Run: java Cancel.java
import java.util.concurrent.*;

public class Cancel {
    static void work(String who) {
        try {
            Thread.sleep(500); // a blocking call: it checks the interrupt flag
            System.out.println(who + ": finished the sleep");
        } catch (InterruptedException e) {
            System.out.println(who + ": InterruptedException, flag now " + Thread.currentThread().isInterrupted());
        } finally {
            System.out.println(who + ": finally runs");
        }
    }

    public static void main(String[] args) throws Exception {
        try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<?> f = pool.submit(() -> work("executor task"));
            Thread.sleep(100);
            System.out.println("cancel(true) -> " + f.cancel(true));
        }
        CompletableFuture<Void> cf = CompletableFuture.runAsync(() -> work("runAsync task"));
        Thread.sleep(100);
        System.out.println("cf.cancel(true) -> " + cf.cancel(true) + ", state " + cf.state());
        try { cf.join(); } catch (CancellationException e) { System.out.println("join(): CancellationException"); }
        Thread.sleep(600); // the task still runs to its end
    }
}
```

```text
cancel(true) -> true
executor task: InterruptedException, flag now false
executor task: finally runs
cf.cancel(true) -> true, state CANCELLED
join(): CancellationException
runAsync task: finished the sleep
runAsync task: finally runs
```

- A `Future` from an executor knows its thread. `cancel(true)` interrupts that thread. The task sees `InterruptedException`, and its `finally` runs.
- A `CompletableFuture` is only a box. It does not know which thread fills it. `cancel(true)` completes the box with a `CancellationException`, and the argument has no effect. The work continues to its end, and its result goes nowhere.

For an `AlSocket` waiter, this means: to cancel a wait, you cancel the box. No other thread waits on it, so there is no thread to interrupt.

#### What happens to a cancelled or timed-out wait

A thread in `get()` on a box wakes when the box completes for any reason. It then throws:

- `ExecutionException` if the box failed. The cause is the original error: `TimeoutException` from `orTimeout`, `IOException` from `AlSocket`.
- `CancellationException` (unchecked, no wrapper) if someone cancelled the box.
- `InterruptedException` if someone interrupted the waiting thread. The box does not change. The waiter of `AlSocket` stays in the list until its own timeout, unless you cancel the future, as `request` does.

#### How an error travels through a chain

Each stage of a chain catches what its function throws and fails its own future with it. The error then skips each `thenApply` and `thenAccept` stage after it. It stops at the first `exceptionally`, `handle` or `whenComplete`, or at the `get()`/`join()` at the end. Between stages, the JDK wraps the error in a `CompletionException`. `get()` unwraps it and puts the original in an `ExecutionException`. Thus, read `getCause()`, as `Bot.waitWelcome` does:

```java
} catch (ExecutionException e) {
    throw new LoginError(e.getCause() instanceof TimeoutException ? "timeout" : String.valueOf(e.getCause().getMessage()));
}
```

#### Errors that nobody reads

Java never stops the program for an error that nobody reads. That is convenient and dangerous:

| Where the error happens | What Java does |
|---|---|
| in a `CompletableFuture` stage | keeps it in the future, silently, until a `get`, `join` or handler reads it |
| in a task of `executor.submit` | keeps it in the `Future`, silently |
| in `Thread.run` (no future) | the thread ends; the `UncaughtExceptionHandler` prints the stack trace; the other threads continue |
| in `main` | `main` ends with a stack trace; the JVM continues while non-daemon threads run |

The third row is the risky one for an AL bot. If the dispatcher thread dies, the program continues. The listener still answers pings, so the server keeps the connection. But no handler and no waiter receives another event. `deliver` catches each `RuntimeException` of a handler for this reason. An `Error` (for example `StackOverflowError`) is not a `RuntimeException`, and it ends the dispatcher.

#### Cleanup

Java has `finally` and try-with-resources. Both run for each kind of exit, interruption included. In async code, put the cleanup where the work ends, not where it starts. `waitFor` does this with `whenComplete`: the waiter leaves the list on success, on timeout and on close, from the thread that completes the box.

At the process level, `Farm` uses a shutdown hook. The JVM runs it on SIGINT (Ctrl-C) and SIGTERM. The hook sets the `volatile` flag `stop` and waits for at most 10 s on a `CountDownLatch`. The main loop sees `stop`, closes the socket and counts the latch down.

#### AL: each waiter when the socket closes

When the connection ends, the HTTP client calls `onClose` or `onError` on a listener thread. Both call `end`, which puts two items in the queue: a local `disconnect` event and the marker `END`. The dispatcher gives out every event before them in order, then `disconnect` to its handlers. After `END`, it runs this:

```java
List<Waiter> left;
synchronized (lock) {
    closed = true;
    left = new ArrayList<>(waiters);
    waiters.clear();
    replay.clear();
}
for (Waiter w : left) w.result().completeExceptionally(new IOException("socket closed"));
done.complete(null);
```

Each waiter fails one time with `IOException("socket closed")`. A new `waitFor` fails at once, because `closed` is true. Then `done()` completes. `request` turns the failure into an `UncheckedIOException`, so a tick loop stops. A timeout is different: `request` returns `null` for it, because "no reply" is a normal answer in AL.

The copy is the lesson of this section. An earlier version looped over `waiters` itself, inside `lock`. But `completeExceptionally` runs the dependents of the box on the same thread. One dependent is the `whenComplete` of `waitFor`, which removes the waiter from `waiters`. `synchronized` is reentrant, so the lock did not stop it. The list changed under its own iterator:

```text
waiter: java.io.IOException: socket closed
Exception in thread "alsocket-dispatch" java.util.ConcurrentModificationException
	at java.base/java.util.ArrayList$Itr.checkForComodification(ArrayList.java:1095)
	at java.base/java.util.ArrayList$Itr.next(ArrayList.java:1049)
	at albot.AlSocket.dispatch(AlSocket.java:175)
	at java.base/java.lang.VirtualThread.run(VirtualThread.java:329)
done() did not complete in 2 s
```

With one waiter, or three or more, the dispatcher died, and `done()` never completed. With two, the iterator stopped early, and the second waiter failed only at its timeout. Now the dispatcher fails a private copy, and the callbacks change only the shared list. The same check now prints this:

```text
waiter: java.io.IOException: socket closed
done() completed
```

The general rule is in chapter [Async 7](#guide-async-7-shared-state): a `complete` call runs other code on your thread. Never complete a future while you iterate a collection that its callbacks can change.

`close()` has its own limit. It waits for `done` for at most 5 s. If the server does not answer, or a handler never returns, `close()` calls `ws.abort()` and `end(...)`, then returns. The waiters fail as soon as the dispatcher is free.

</div>

## Async 7: Shared state

Your handlers write the state of the world. Your tick reads it. This chapter shows when these two can run at the same instant in your language, and what can
then go wrong. It also shows how the course keeps `World`, `Cooldowns` and `Budget` correct.

<div data-lang="js ts">

#### No data races, still race conditions

The memory model of JavaScript is short for your code: one thread per isolate. Two pieces of
your JavaScript never run at the same instant, so two writes to one object never overlap. There
are no torn values, no stale caches, and no need for `volatile` or memory barriers. A worker
thread has its own heap, so it cannot see your objects at all.

That removes data races. It does not remove race conditions. The rule that replaces locks is
this: **the code between two `await`s runs as one piece**. No other JavaScript runs in the
middle of it. At each `await` that must wait, any other code can run: handlers, other loops,
timers. Each `await` is a point where the world can change under you.

#### The lost update at an `await`

```js
// interleave.mjs: one thread, no data race, and still a lost update.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const state = { potions: 1 };

// Two loops (two ticks, or a tick and a handler) both want to drink.
async function drink(who) {
  if (state.potions > 0) {             // 1. check
    await sleep(10);                   // 2. wait: the other loop runs here
    state.potions -= 1;                // 3. act on a value that is now old
    console.log(`${who} drank; potions left: ${state.potions}`);
  }
}
await Promise.all([drink("tick A"), drink("tick B")]);

// The fix: check and act with no await between them.
state.potions = 1;
async function drinkSafe(who) {
  if (state.potions <= 0) return;
  state.potions -= 1;                  // take it now, in the same task as the check
  await sleep(10);                     // then wait for the reply
  console.log(`${who} drank; potions left: ${state.potions}`);
}
await Promise.all([drinkSafe("tick A"), drinkSafe("tick B")]);
```

```text
tick A drank; potions left: 0
tick B drank; potions left: -1
tick A drank; potions left: 0
```

The first version checks, waits, then acts. Both loops passed the check before either one
acted. The fix moves the `await` out of the check-and-act.

In AL, the same shape appears in
`heal`: it checks `cooldowns.ready("potion")`, then awaits the `request`. Two loops for one
character could both pass the check. The server then answers the second with `not_ready`. That
costs call-cost and nothing more, but the shape is the same.

#### How the course keeps its state safe

The course has one loop per character. Its handlers change state, and its tick reads state and
sends. With the rule above, each part is easy to check.

**World.** Every handler of `World` is synchronous. `onPlayer` merges the update into `me` in
one piece. `applyEntities` replaces the monsters in one piece. No reader can see half an
update. Two details matter for the tick:

- `onPlayer` and `onNewMap` change `me` in place, with `Object.assign`. So `const me =
  world.me` at the top of a tick stays current across the awaits of the tick. `onStart`
  replaces `me` with a new object, but `start` arrives one time per session, before the tick.
- `applyEntities` replaces each monster object. A monster object that you keep across an
  `await` can be an old copy. `Farmer` keeps the id (`this.target`) and reads
  `world.monsters.get(this.target)` again on the next tick.

**Cooldowns.** Its handlers write a `Map` of times. The tick reads it with `ready(name)`, which
compares with `performance.now()` at the call. No lock is necessary, because each write runs as
one piece.

All the times of the course come from `performance.now()`, a clock that only goes forward.
`Date.now()` is the wall clock. It can jump when the system sets its time. In a Docker container
on WSL2, a check program saw the wall clock jump 1 s forward, then 3.4 s back. An earlier
version of the course used `Date.now()`. Then a walk that `World.advance` measured across such a
jump ended 2 s short of its goal, and `walkTo` failed.

**Budget.** Its `emit` can run from more than one loop at a time (a fighter and its `Items`, for
example). It stays correct because of where its `await` is:

```js
// fragment: course/js/albot/budget.js
  async emit(event, payload) {
    const cost = this.cost(event);
    while (this.spent() + cost > LIMIT) {
      // Sleep until the oldest call leaves the window (+10 ms of margin).
      await sleep(WINDOW_MS - (performance.now() - this.#calls[0][0]) + 10);
    }
    this.#calls.push([performance.now(), cost]);
    this.sock.emit(event, payload);
  }
```

The last check of `spent()`, the `push` and the `sock.emit` have no `await` between them. They
run as one piece. A caller that slept checks again in the `while`, because another caller can
have used the room during the sleep. This is the general fix: after an `await`, check again.

#### An async lock, when you need one

Sometimes a sequence must not interleave with itself, and it must `await` in the middle. An
example is a merchant trip: walk, sell, bank. JavaScript has no built-in async mutex, but a
promise chain is one:

```js
// mutex.mjs: an async lock from a promise chain. Each caller waits for the one before it.
class Mutex {
  #last = Promise.resolve();
  // Runs fn() after every earlier fn() has ended. Returns what fn() returns.
  run(fn) {
    const result = this.#last.then(fn);
    this.#last = result.catch(() => {}); // a failed fn must not block the next one
    return result;
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const lock = new Mutex();
const t0 = performance.now();
const job = (name) => lock.run(async () => {
  console.log(`${String(Math.round(performance.now() - t0)).padStart(3)} ms ${name} starts`);
  await sleep(100); // held across the await: the next job waits for this one
});
await Promise.all([job("trip 1"), job("trip 2"), job("trip 3")]);
```

```text
  0 ms trip 1 starts
104 ms trip 2 starts
205 ms trip 3 starts
```

This lock stays held across `await`s on purpose, so it serializes whole sequences.

It has the usual risks of a lock. A job that calls `lock.run` again from inside waits for itself, and never
ends. A job that never settles blocks every later job. Give each job a timeout. Handlers must
never take such a lock: a handler is synchronous, and it cannot wait.

#### Real shared memory: workers only

A worker shares nothing by default. `postMessage` copies the data. The one exception is a
`SharedArrayBuffer`: raw bytes that two threads see at the same time. For those bytes, the
real memory model applies, and you use `Atomics` (`Atomics.add`, `Atomics.load`,
`Atomics.wait`, `Atomics.notify`). A bot rarely needs this. Send the map to a path-search
worker one time, then send small messages.

TypeScript adds no run-time protection. Type stripping removes `readonly` and `private` with the
other types. Only the `#name` fields of JavaScript, as in `AlSocket` and `World`, are private at run
time.

</div>

<div data-lang="python">

#### The memory model, as far as you need it

All coroutines of a bot run on one thread. Thus the questions of a threaded memory model do
not apply to them. There are no torn writes, no stale caches, and no reordering that another
task can see.
A write is visible to the next line that runs, in any task.

The unit of atomicity is the code between two suspensions. From the moment a step starts to
the moment its coroutine yields, no other task runs. A `def` handler is entirely inside one
step of the reader. Thus each handler applies its event as one atomic change.

What you lose is atomicity across an `await`. Each `await` that suspends is a point where any
other task, and any handler, can run and change the state.

#### A race on one thread

The classic bug is "check, await, act". The check is true when it runs. Other tasks run during
the `await`. The act then uses a check that is old:

```python
# state_interleave.py: one thread, and still a race: check, await, act.
import asyncio

LIMIT = 10  # the call-cost room left, in this toy


class Budget:
    def __init__(self) -> None:
        self.spent = 0
        self.lock = asyncio.Lock()

    async def spend_bad(self, cost: int) -> None:
        if self.spent + cost <= LIMIT:  # 1. check
            await asyncio.sleep(0)  # 2. an await: other tasks run here
            self.spent += cost  # 3. act on a check that is now old

    async def spend_good(self, cost: int) -> None:
        if self.spent + cost <= LIMIT:  # check and act with no await between:
            self.spent += cost  # no other task can run in this gap
        await asyncio.sleep(0)  # now it is safe to wait

    async def spend_locked(self, cost: int) -> None:
        async with self.lock:  # when the gap MUST contain an await
            if self.spent + cost <= LIMIT:
                await asyncio.sleep(0)
                self.spent += cost


async def main() -> None:
    for name in ("spend_bad", "spend_good", "spend_locked"):
        b = Budget()
        await asyncio.gather(*(getattr(b, name)(4) for _ in range(5)))
        print(f"{name:12} spent {b.spent} of {LIMIT}")


asyncio.run(main())
```

It prints:

```text
spend_bad    spent 20 of 10
spend_good   spent 8 of 10
spend_locked spent 8 of 10
```

All five tasks of `spend_bad` passed the check before any of them added its cost. On a real
server, a budget that overspends like this gets the socket closed with `limitdc`.

#### How the course keeps its state safe

The course uses no lock in Python. It keeps three rules instead:

- **Handlers are `def`.** `World`, `Cooldowns` and `Budget` change their state only in plain
  handlers and plain methods. Each change is complete before any other code runs.
- **Check and act with no suspension between.** `Budget.emit` awaits `wait_for_room`. When the
  room exists, `wait_for_room` returns without a suspension, and `emit` records the cost on the
  next line. Then it awaits `sock.emit`. The check and the record are in one step.
- **Read again after an `await`.** `Farmer.tick` reads `world.me` and the target at its start,
  does one action, and returns. The next tick reads fresh state.

`me` is a reference to the same dict for the whole session. `World.on_start` does
`self.me.clear()` and `self.me.update(...)`, and `on_player` merges into it. Thus a reference
that the tick holds always shows the newest values. The other side of this: two lines of the
tick can see different values, if an `await` is between them.

#### `asyncio.Lock` and its relatives

`asyncio.Lock`, `Event`, `Condition`, `Semaphore` and `Queue` coordinate tasks on one loop.
They are not thread-safe. Inside, each one is a list of Futures: `acquire` on a held lock makes
a Future and awaits it, and `release` completes the first one.

A lock is useful only when the protected section must contain an `await`, as in
`spend_locked`. Without an `await`, the section is already atomic. Hold a lock across a long
wait only with care. Each task that needs the lock waits too.

A `def` handler cannot take an `asyncio.Lock`, because it cannot await. This is good for the reader: a handler never waits for the tick. Keep each handler
small, and let it change state without a lock.

`farm.py` uses an `asyncio.Event` (`stopping`). The signal handler sets it, and `wait()` ends
early when the flag goes up.

#### Threads and the GIL

Python threads are operating-system threads. The global interpreter lock (GIL) lets only one
of them run Python bytecode at a time. A thread gives the GIL back when it blocks in I/O, in
`time.sleep`, and in many C functions. A thread that computes gives it back at the switch
interval, 5 ms by default (`sys.getswitchinterval()`).

Thus a thread helps an `asyncio` bot in one case: it takes a blocking call off the loop
thread. `asyncio.to_thread(fn, *args)` (Python 3.9+) runs `fn` in the default thread pool and
gives you an awaitable for its result. For CPU work in pure Python, a thread keeps the loop
alive, but it does not make the work faster. The work and the loop share one GIL. A process has
its own interpreter and its own GIL:

```python
# state_gil.py: threads, the GIL, and processes, for CPU work in pure Python.
import asyncio
import time
from concurrent.futures import ProcessPoolExecutor


def search(n: int) -> int:
    """Stands for an A* search: pure-Python CPU work."""
    total = 0
    for i in range(n):
        total += i % 7
    return total


N = 20_000_000  # about 0.5 s on the test machine


async def on_loop(n: int) -> int:
    return search(n)  # no await inside: the loop waits for all of it


async def heartbeat(stop: asyncio.Event) -> None:
    """The reader stands in here: does the loop still get the thread?"""
    beats, late = 0, 0.0
    while not stop.is_set():
        t = time.monotonic()
        await asyncio.sleep(0.01)
        late = max(late, time.monotonic() - t - 0.01)
        beats += 1
    print(f"   loop: {beats} beats, worst delay {1000 * late:.0f} ms")


async def timed(label: str, coro) -> None:
    stop = asyncio.Event()
    hb = asyncio.create_task(heartbeat(stop))
    t = time.monotonic()
    await coro
    print(f"{label:28} {time.monotonic() - t:.2f} s")
    stop.set()
    await hb


async def main() -> None:
    loop = asyncio.get_running_loop()
    await timed("1 search, on the loop", on_loop(N))
    await timed("1 search, to_thread", asyncio.to_thread(search, N))
    await timed("2 searches, 2 threads", asyncio.gather(
        asyncio.to_thread(search, N), asyncio.to_thread(search, N)))
    with ProcessPoolExecutor(2) as pool:
        await loop.run_in_executor(pool, search, 1)  # start the 2 processes first
        await timed("2 searches, 2 processes", asyncio.gather(
            loop.run_in_executor(pool, search, N), loop.run_in_executor(pool, search, N)))


if __name__ == "__main__":
    asyncio.run(main())
```

It prints, on a machine with 4 cores (the values depend on the machine):

```text
1 search, on the loop        0.54 s
   loop: 0 beats, worst delay 0 ms
1 search, to_thread          0.51 s
   loop: 31 beats, worst delay 7 ms
2 searches, 2 threads        1.06 s
   loop: 58 beats, worst delay 41 ms
2 searches, 2 processes      0.51 s
   loop: 48 beats, worst delay 4 ms
```

- **On the loop**, the search stops everything: zero heartbeats.
- **In a thread**, the loop runs, but slower: 31 beats of about 50, because the search holds
  the GIL for 5 ms at a time.
- **Two threads** take twice as long as one. They do not run in parallel.
- **Two processes** take the time of one. `run_in_executor` with a `ProcessPoolExecutor`
  sends the arguments and the result as pickles. A map grid is large, so give each worker
  process its grid one time, not with each call.

The GIL protects the objects of the interpreter, not your invariants. A check-then-act in two
threads is a real race, and a switch can occur between any two bytecodes. If you use threads,
let them compute and return a value. Do not let them change `World`.

> **Note:** Python 3.13 has an optional build without the GIL ("free-threaded", PEP 703,
> `python3.13t`). The course does not use it, and the normal build of 3.12 has the GIL.

#### From a thread back to the loop

The loop, its Futures and its queues are not thread-safe. A thread must not call
`fut.set_result` or `loop.call_soon`. Use `loop.call_soon_threadsafe(callback, *args)`. It
appends the handle and writes one byte to the self-pipe, so that `epoll_wait` returns:

```python
# state_threadsafe.py: why a thread must use call_soon_threadsafe.
import asyncio
import threading
import time


async def wait_from_thread(safe: bool) -> None:
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    loop.call_later(1.0, lambda: None)  # the only other thing that wakes the loop

    def worker() -> None:  # runs on another thread
        time.sleep(0.1)
        if safe:
            loop.call_soon_threadsafe(fut.set_result, "path")  # queue it AND wake the loop
        else:
            fut.set_result("path")  # WRONG: touches the loop from another thread

    t0 = time.monotonic()
    threading.Thread(target=worker).start()
    await fut
    print(f"{'call_soon_threadsafe' if safe else 'set_result from the thread':26}"
          f" -> resumed after {time.monotonic() - t0:.1f} s")


asyncio.run(wait_from_thread(False))
asyncio.run(wait_from_thread(True))
```

It prints:

```text
set_result from the thread -> resumed after 1.0 s
call_soon_threadsafe       -> resumed after 0.1 s
```

The wrong call queued the wake-up of the task, but the loop slept on. It woke only when the
unrelated 1 s timer fired. `to_thread` and `run_in_executor` do the right thing for you. The
thread pool completes a `concurrent.futures.Future`. Then `asyncio` copies the result to its
own Future with `call_soon_threadsafe`. To start a coroutine on the loop from another thread, use
`asyncio.run_coroutine_threadsafe(coro, loop)`.

</div>

<div data-lang="go">

In JavaScript and Python, your code runs on one thread, and state changes only at an
`await`. Go is different. Your tick and your handlers run on different goroutines, on
different CPUs, and the scheduler can switch at almost any instruction. Two goroutines that
use the same variable without synchronization have a **data race**. This chapter gives the
part of the Go memory model that you need, then the tools, then the rules of the course.

#### The memory model in four rules

The Go memory model is at [go.dev/ref/mem](https://go.dev/ref/mem). Go 1.19 revised it. It
defines when a read in one goroutine sees a write in another. It uses the relation **happens-before**.

1. **In one goroutine,** each statement happens before the next one.
2. **A synchronizing operation** creates an edge between goroutines. The edges that the
   course uses:
   - A send on a channel happens before the receive of that value completes.
   - The close of a channel happens before a receive that returns because of the close.
   - `mu.Unlock()` happens before the next `mu.Lock()` returns.
   - The `go` statement happens before the new goroutine starts.
   - `wg.Done()` happens before the `wg.Wait()` that it releases returns.
   - An atomic operation that reads a value happens after the atomic write of that value.
3. **A data race** is a write and another access to the same memory location, from two
   goroutines, with no happens-before order between them.
4. **A program without data races** behaves as if the goroutines took turns, one operation
   at a time ("sequentially consistent"). A program with a data race has no such promise.
   It can see a half-written value. A map can break its own internal structure.

Thus the rule is simple: each shared value needs one of the edges of rule 2 between each
write and each other access.

#### A race in AL terms

A `player` handler writes `Me["hp"]` on the dispatch goroutine. Your tick reads `Me["hp"]`
on the main goroutine. This program does that 100,000 times, with and without a lock:

```go
// maprace: a "dispatch" goroutine writes Me, the "tick" goroutine reads it,
// with no lock. Go maps are not safe for this: the runtime can stop the
// program with a fatal error, and -race reports the race.
//
//	go run ./maprace          (no lock: fatal error, usually)
//	go run ./maprace lock     (with a sync.Mutex: correct)
package main

import (
	"fmt"
	"os"
	"sync"
)

func main() {
	useLock := len(os.Args) > 1
	var mu sync.Mutex
	me := map[string]any{"hp": 100.0}
	var wg sync.WaitGroup
	wg.Add(2)
	go func() { // the dispatch goroutine: a `player` handler
		defer wg.Done()
		for i := 0; i < 100000; i++ {
			if useLock {
				mu.Lock()
			}
			me["hp"] = float64(i)
			if useLock {
				mu.Unlock()
			}
		}
	}()
	go func() { // the tick goroutine
		defer wg.Done()
		for i := 0; i < 100000; i++ {
			if useLock {
				mu.Lock()
			}
			_ = me["hp"]
			if useLock {
				mu.Unlock()
			}
		}
	}()
	wg.Wait()
	fmt.Println("hp:", me["hp"])
}
```

Without the lock, the runtime usually stops the program (exit status 2):

```text
fatal error: concurrent map read and map write
```

The map code of the runtime has a cheap check for this case. It is a `fatal error`, not a
`panic`, so `recover` cannot stop it. With the lock (`go run ./maprace lock`), it prints:

```text
hp: 99999
```

The fatal error is luck. A race on a `float64` field or on a slice header has no such check.
The program continues with a wrong value. To find those, use the race detector.

#### The race detector

`go run -race`, `go build -race` and `go test -race` add code to each memory access. At run
time, this code tracks the happens-before edges. It reports each pair of accesses that have
no edge between them. The race detector needs cgo, so a C compiler must be on the machine.
The `golang:1.22` image has one. The same program with `-race` prints this first (the
addresses differ, and the paths are shorter here):

```text
==================
WARNING: DATA RACE
Read at 0x00c000108090 by goroutine 8:
  runtime.mapaccess1_faststr()
      $GOROOT/src/runtime/map_faststr.go:13 +0x0
  main.main.func2()
      .../maprace/main.go:39 +0xf5

Previous write at 0x00c000108090 by goroutine 7:
  runtime.mapassign_faststr()
      $GOROOT/src/runtime/map_faststr.go:203 +0x0
  main.main.func1()
      .../maprace/main.go:27 +0x135

Goroutine 8 (running) created at:
  main.main()
      .../maprace/main.go:33 +0x350

Goroutine 7 (running) created at:
  main.main()
      .../maprace/main.go:21 +0x244
==================
```

Line 39 is the read in the tick, line 27 is the write in the handler. Lines 33 and 21 are
the `go` statements. This program still ends with the fatal error after the report. A
program that ends normally prints `Found 1 data race(s)` and exits with status 66. The
detector finds only the races that occur in that run.

Run your bot with `-race` against the test server or the live game for some minutes. The cost is high: the Go documentation gives 5 to 10 times
the memory and 2 to 20 times the time. Do not use it in normal play.

#### The tools

| Tool | Use it for | In the course |
|---|---|---|
| `sync.Mutex` | One owner at a time for a group of fields. | `World`, `Cooldowns`, `Budget`, `Farmer`, `Actions.diedAt`, the `Socket` maps. |
| `sync.RWMutex` | Many readers or one writer. Only better when reads are long and many. | Not used. A short `Mutex` is simpler and as fast here. |
| `sync/atomic` | One word: a flag, a counter. `atomic.Bool`, `atomic.Int64` (Go 1.19+). | `Socket.closing`: `Close` sets it, `readLoop` reads it. |
| A channel | To move a value, and its ownership, to another goroutine. | `s.events` (reader to dispatcher), `w.ch` (dispatcher to waiter). |

"Do not communicate by sharing memory; instead, share memory by communicating." This Go
proverb describes the channels of `alsocket`. `readLoop` makes an `event` and sends it. After
the send, only `dispatchLoop` uses it. The channel is the happens-before edge, and no lock is
necessary.

Not all state fits this model. `World` is a large structure that many goroutines read. A
channel for each read would be slow and hard to read. Thus the course uses a mutex for
state, and channels for events and replies. Use each tool where it fits.

#### How the course keeps `World`, `Cooldowns` and `Budget` safe

**`World` embeds a `sync.Mutex`, and the handlers run with it held.** Each socket handler of
`World` calls `Dispatch`, which locks, then calls the handlers of that event:

```go
func (w *World) Dispatch(name string, data json.RawMessage) {
	w.Lock()
	defer w.Unlock()
	w.dispatchLocked(name, data)
}
```

Thus a handler that you register with `w.Listen` can read and write each field without a
lock call of its own. The tick reads through methods that lock: `CopyMe`, `CopyMonster`,
`NearestMonster`, `ChestIDs`. Each returns a **copy**. After the method unlocks, a handler
can change `Me` again, but your copy does not change. Thus `Farmer.Tick` decides on a
consistent picture.

`Clone` copies only the top level of the map. This is correct because the handlers never
change a nested value in place. They replace the whole field. If you write a handler that
changes a nested map in place, a copy shares that nested map, and you have a race again.

**A Go mutex is not reentrant.** A handler that runs under the `World` lock must not call
`CopyMe` or `Listen`. Each of them locks again. The goroutine then waits for itself forever.
The comment on `World.Listen` states this rule.

**The lock order is always `World` first.** The `hit` handler of `Farmer` runs with the
`World` lock held, then locks `f.mu`. The `Cooldowns` and `Actions` handlers do the same with
their own locks. No code locks `f.mu` (or the others) and then the `World` lock. If two
goroutines took two locks in opposite orders, each could hold one and wait for the other.
That is a deadlock.

**The course holds no lock across a wait.** A lock that you hold during a wait for the network holds back each
handler that needs it. `Budget.Emit` shows the rule:

```go
		// Wait until the oldest cost leaves the window (+10 ms of margin).
		wait := WindowMs*time.Millisecond - time.Since(b.spent[0].at) + 10*time.Millisecond
		ctx := b.ctx
		b.mu.Unlock() // never wait with the lock: the new_map handler needs it
```

It computes the wait and reads its context under the lock, unlocks, then waits. `Farmer.Tick` follows the same
rule: it copies `f.target` under `f.mu`, unlocks, then calls `Attack`, which waits up to 2 s.

**`Cooldowns` and `Budget` each have their own mutex.** Their handlers (`skill_timeout`,
`new_map`) run on the dispatch goroutine. Your tick calls `Ready` and `Emit` on the main
goroutine. Each method locks for a few microseconds. `time.Now()` in Go has a monotonic
reading, so `time.Until(readyAt)` is correct also when the wall clock jumps.

</div>

<div data-lang="csharp">

In JavaScript and Python, your code runs on one thread, and state changes only at an `await`.
In .NET, it is not so. A handler on the dispatcher and your tick run on two pool threads, at
the same instant, on two cores. Shared state needs the same care as in any threaded program.

#### Who runs at the same time as whom

In a running course bot, these pieces of code can run at the same instant:

| Code | Thread |
|---|---|
| `ReadLoop`: parse a frame, send a pong | a worker |
| `Dispatch`: `Deliver`, the predicates, all handlers (also the kept early events) | another worker, one event at a time |
| Your tick, and each `await` continuation in it | another worker, which can change at each `await` |
| The timeout callback of a `WaitForAsync` | a worker that the timer uses |
| The signal handlers of Ctrl-C and SIGTERM | the `.NET SigHandler` thread |

Inside one `async` method, the steps run one after the other, also when the thread changes.
The hand-off between steps goes through the task and the pool queue. Both use interlocked
operations, so the next step sees each write of the step before it. You do not need a lock for
the locals of one method. You need one for each value that two of the rows above share.

#### What goes wrong without a lock

```csharp
// race: two threads add 1 to the same int 1,000,000 times each.
const int N = 1_000_000;

var plain = 0;
Both(() => plain++);                       // read, add, write: three steps
Console.WriteLine($"plain ++     : {plain:N0}");

var atomic = 0;
Both(() => Interlocked.Increment(ref atomic)); // one atomic step
Console.WriteLine($"Interlocked  : {atomic:N0}");

var locked = 0;
var gate = new object();
Both(() => { lock (gate) locked++; });     // one thread at a time
Console.WriteLine($"lock         : {locked:N0}");

static void Both(Action add)
{
    var threads = Enumerable.Range(0, 2).Select(_ => new Thread(() => { for (var i = 0; i < N; i++) add(); })).ToList();
    threads.ForEach(t => t.Start());
    threads.ForEach(t => t.Join());
}
```

Output (the first number differs from run to run):

```text
plain ++     : 1,109,468
Interlocked  : 2,000,000
lock         : 2,000,000
```

`plain++` lost about 890,000 additions. Two threads read the same old value, and both wrote
back old value + 1. In the bot, the same occurs with a `Dictionary`. A handler adds a monster
while the tick enumerates the monsters. The result is an `InvalidOperationException`, or a
broken dictionary that throws later, in other code.

#### The .NET memory model, the part you need

The [.NET memory model](https://github.com/dotnet/runtime/blob/main/docs/design/specs/Memory-model.md)
gives few promises for ordinary reads and writes:

- A read or write of an aligned value up to the pointer size is **atomic**: `int`, `bool`, a
  reference, and `long` on a 64-bit system. You never read half of a value.
- The compiler, the JIT and the CPU can **reorder** ordinary reads and writes, if one thread
  alone cannot see the change. Another thread can see it.
- The JIT can **combine** reads of the same location. A loop that reads a plain field can read
  it one time only.

This program shows the last point. Build it with `-c Release`:

```csharp
// hoist: a plain bool that another thread sets. In a Release build the JIT can
// read it once, before the loop, and the loop never ends. Volatile.Read fixes it.
var mode = args.Length > 0 ? args[0] : "plain";
var flag = new Flag();
var worker = new Thread(() =>
{
    long spins = 0;
    if (mode == "plain") while (!flag.Stop) spins++;
    else while (!Volatile.Read(ref flag.Stop)) spins++;
    Console.WriteLine("worker saw Stop");
}) { IsBackground = true };
worker.Start();
Thread.Sleep(1000);       // let the JIT optimize the loop
flag.Stop = true;
Console.WriteLine(worker.Join(2000) ? $"{mode}: the loop ended" : $"{mode}: the loop still runs after 2 s");

class Flag { public bool Stop; }
```

Output of a Release build, with the argument `plain`, then `volatile`:

```text
plain: the loop still runs after 2 s
worker saw Stop
volatile: the loop ended
```

A Debug build ends in both cases, which hides the defect. The tools that give order are these:

- **`Volatile.Read` / `Volatile.Write`**, or the `volatile` keyword on a field. A volatile read
  is an *acquire*: no later access moves before it. A volatile write is a *release*: no earlier
  access moves after it. Use them for one flag that one thread writes and another reads.
- **`Interlocked`** (`Increment`, `Add`, `Exchange`, `CompareExchange`). Each call is atomic and
  a full fence. Use it for a counter or a single reference.
- **`lock`** (`Monitor.Enter` and `Monitor.Exit`). Enter is an acquire, and exit is a release.
  Between them, only one thread runs. Use it for each group of values that must change
  together.

The memory model also promises one useful thing for free. A write of a reference to an object is
a release for the fields of that object. A thread that sees the reference also sees the fields
that the constructor wrote.

#### lock, and why it cannot contain an await

`lock (obj) { ... }` is `Monitor.Enter(obj)` and `Monitor.Exit(obj)` in a `try`/`finally`. A
monitor belongs to a **thread**. The thread that holds it can enter it again (it is
re-entrant), and only that thread can exit it. An `await` can move the method to another thread.
The exit would then run on a thread that does not hold the lock. Thus the compiler refuses it:

```csharp
// lockawait: the compiler refuses an await inside lock.
var gate = new object();
lock (gate)
{
    await Task.Delay(10);
}
```

```text
/w/Program.cs(5,5): error CS1996: Cannot await in the body of a lock statement [/w/lockawait.csproj]
```

The rule also has a second reason. A lock held across a wait of 2 s blocks each handler that
needs it for 2 s. In the course, that is the whole dispatcher, and with it every waiter.

#### SemaphoreSlim: a lock for async code

`SemaphoreSlim(1, 1)` is a counter with one place. `await WaitAsync()` takes the place, or
waits without a thread until it is free. `Release()` gives it back. It does not belong to a
thread, so the release can run on another thread. It is not re-entrant: a second `WaitAsync`
from the same flow waits for itself forever.

```csharp
// asynclock: SemaphoreSlim(1, 1) is a lock that you can hold across an await.
// Two tasks "send" at the same time; the semaphore makes them take turns.
var sendLock = new SemaphoreSlim(1, 1);
var clock = System.Diagnostics.Stopwatch.StartNew();

await Task.WhenAll(Send("pong"), Send("attack"));

async Task Send(string what)
{
    await sendLock.WaitAsync();   // waits without a blocked thread
    try
    {
        Console.WriteLine($"{clock.ElapsedMilliseconds,4} ms: start {what}, thread {Environment.CurrentManagedThreadId}");
        await Task.Delay(100);    // an await inside the "lock": allowed here
        Console.WriteLine($"{clock.ElapsedMilliseconds,4} ms: end {what}, thread {Environment.CurrentManagedThreadId}");
    }
    finally { sendLock.Release(); } // the release can run on another thread: SemaphoreSlim allows it
}
```

Output (the thread ids can differ):

```text
   1 ms: start pong, thread 1
 111 ms: end pong, thread 5
 112 ms: start attack, thread 7
 213 ms: end attack, thread 5
```

`AlSocket` uses exactly this for `_sendLock`. `ClientWebSocket` allows one `SendAsync` at a time.
The reader sends pongs, and your tasks send events, so they take turns on the semaphore.

#### How the course keeps its state correct

The course uses one rule for each shared object: **one lock, held only for reads and writes in
memory, never across an `await`**.

- **`World`** has one lock object, `Gate`, for `Me`, `Monsters`, `Players`, `Chests`, and also
  for the state of `Farmer` and `Actions._diedAt`. `World.Listen` registers each handler through
  `World.Dispatch`, which runs it with `Gate` held. Thus all handlers of the world see and leave
  a consistent state.
- **`Cooldowns`** and **`Budget`** each have their own private lock. Their methods take it. A
  caller never sees it.
- **`AlSocket`** has `_lock` for its tables (handlers, waiters, early events) and `_sendLock`
  for the WebSocket.

The tick copies what it needs under the lock, then waits outside it. This is the start of
`Farmer.TickAsync`:

```csharp
// fragment of course/csharp/Albot/Farmer.cs, TickAsync
lock (_world.Gate)
{
    _world.Advance(); // positions at this moment
    var me = _world.Me;
    rip = me.Bool("rip");
    map = me.Str("map");
```

`Budget.EmitAsync` follows the same rule when the budget is full. It computes the wait inside
the lock, then waits outside: `await Task.Delay(...); // never wait with the lock held`.

Two locks need an order, or two threads can each hold one and wait for the other. In the course,
`World.Listen` holds `Gate` while it calls `Sock.On`, which takes `_lock`. So the order is
`Gate`, then `_lock`. The dispatcher never holds `_lock` while it runs handlers. It copies the
list of handlers inside the lock, and calls them after.

One place breaks the pattern: a
`WaitForAsync` predicate runs inside `_lock`. **A predicate must not take `Gate`**, or a
predicate on the dispatcher and a `Listen` on your thread can deadlock. Keep predicates to
reads of their own payload, as `ResponseFor` does.

`Farm/Program.cs` has two values that cross threads without `Gate`. The first one is the
request to stop. The Ctrl-C handler sets it, and the tick loop reads it. It is a
`CancellationTokenSource`, which is safe between threads, and which `Task.Delay` can also wait
for:

```csharp
// fragment of course/csharp/Farm/Program.cs, region stop
using var stopping = new CancellationTokenSource();
```

The second one is `lost`, the reason of a `disconnect`. A handler writes it, and the loop reads
it:

```csharp
// fragment of course/csharp/Farm/Program.cs, region session
world.Listen("disconnect", r => Interlocked.CompareExchange(ref lost, r?.ToString() ?? "disconnect", null));
```

The loop reads it with `Volatile.Read(ref lost)`. `CompareExchange` keeps the first reason, and
it is a full fence. An earlier version used a plain `bool stop` and a plain `string? lost`.
That worked in practice, because each turn of the loop passes an `await`. But nothing in the
memory model promised it: it was the `hoist` program above, with a lucky shape.

.NET 9 adds `System.Threading.Lock`, a type made for `lock`. It changes the speed, not the rules
of this chapter.

</div>

<div data-lang="rust">

In Go, C#, Java and Rust, two threads can touch the same memory at the same instant. Rust is
different in one way: **safe Rust cannot compile a data race**. The type system tracks which
values may cross threads, and which values threads may share. It uses two auto traits, `Send`
and `Sync`. This chapter explains those traits, the two kinds of
mutex, and why the course uses the plain `std::sync::Mutex`.

#### Real parallelism in the course

Recall the threads from [Async 2](#guide-async-2-the-runtime). The dispatcher runs your
handlers on a worker. The tick runs on the main thread. When a `player` event and a tick occur
at the same moment, two cores touch `World` at the same moment. In JavaScript or Python, this
cannot occur. In Rust, it occurs, and the compiler forces you to decide what protects the data.

#### `Send` and `Sync`

- A type is **`Send`** if you can move a value of it to another thread. Most types are. `Rc`
  is not, because two threads could change its counter at the same time. A
  `std::sync::MutexGuard` is not, because on some operating systems, only the thread that locked a
  mutex can unlock it.
- A type is **`Sync`** if you can share a `&T` between threads. `T` is `Sync` exactly when
  `&T` is `Send`. `Cell` and `RefCell` are not `Sync`. `Mutex<T>` is `Sync` when `T` is
  `Send`.

The compiler derives both traits for your types from their fields. You never write them. A
future is a type too: its fields are the variables that live across each `.await`. Thus an
`async` block is `Send` only if everything that it holds across an `.await` is `Send`. That is
how `tokio::spawn` can refuse a future that is not safe to move between workers.

The usual pattern for shared state is `Arc<Mutex<T>>`. `Arc` gives shared ownership across
threads, and `Mutex` gives exclusive access to `T`. `Arc<T>` alone gives only `&T`, so you
cannot change `T` through it without a lock or an atomic.

#### `std::sync::Mutex` across an `.await`: the compiler says no

```rust
// Does NOT compile, on purpose: a std::sync::MutexGuard across an .await in a spawned task.
use std::sync::{Arc, Mutex};
use std::time::Duration;

#[tokio::main]
async fn main() {
    let world = Arc::new(Mutex::new(0u32));
    let w = world.clone();
    tokio::spawn(async move {
        let mut hp = w.lock().unwrap();
        tokio::time::sleep(Duration::from_millis(10)).await; // the guard lives across this .await
        *hp += 1;
    });
}
```

The compiler refuses it and names the guard:

```text
error: future cannot be sent between threads safely
   --> src/bin/not_send.rs:9:5
    |
  9 | /     tokio::spawn(async move {
 10 | |         let mut hp = w.lock().unwrap();
 11 | |         tokio::time::sleep(Duration::from_millis(10)).await; // the guard lives across this .await
 12 | |         *hp += 1;
 13 | |     });
    | |______^ future created by async block is not `Send`
    |
    = help: within `{async block@src/bin/not_send.rs:9:18: 9:28}`, the trait `Send` is not implemented for `std::sync::MutexGuard<'_, u32>`
note: future is not `Send` as this value is used across an await
   --> src/bin/not_send.rs:11:55
    |
 10 |         let mut hp = w.lock().unwrap();
    |             ------ has type `std::sync::MutexGuard<'_, u32>` which is not `Send`
 11 |         tokio::time::sleep(Duration::from_millis(10)).await; // the guard lives across this .await
    |                                                       ^^^^^ await occurs here, with `mut hp` maybe used later
```

This error protects you from more than the `Send` rule. A guard held across an `.await` keeps
the lock for the whole wait. The dispatcher's handler then blocks its worker on that lock. If
the wait needs the dispatcher (for example, a `game_response`), the program deadlocks.

> **Caution:** The check covers only futures that need `Send`. The main future of
> `#[tokio::main]` does not need `Send`, because it never leaves the main thread. There, a
> `std::sync::MutexGuard` across an `.await` compiles. The course holds no guard across an
> `.await` in any place, by rule.

#### Two mutexes, two jobs

| | `std::sync::Mutex` | `tokio::sync::Mutex` |
|---|---|---|
| `lock()` | blocks the thread until free | a future: the task waits, the thread runs other tasks |
| guard across `.await` | not `Send`; a bad idea | allowed; that is its purpose |
| speed | fast; no allocation | slower; a queue of waiters |
| poison on panic | yes | no |
| order of waiters | no promise | FIFO |

Use the std mutex for short sections that do not wait: lock, read or change, unlock. Use the Tokio mutex only when you must hold the lock across an `.await`. An example is one
sender on a resource during a slow write. The Tokio documentation gives the same advice.

The course uses only `std::sync::Mutex`, and copies data out before each `.await`. This is
`Actions::move`:

```rust
        let payload = {
            let mut w = self.world.lock(); // ends before the .await below
            let payload = json!({
                "x": num(&w.me, "x"), "y": num(&w.me, "y"),
                "going_x": x, "going_y": y,
                "m": w.me.get("m").cloned().unwrap_or(json!(0)),
            });
            // The server does the same with its copy, so step() moves ours.
            w.me.insert("going_x".into(), json!(x));
            w.me.insert("going_y".into(), json!(y));
            w.me.insert("moving".into(), json!(true));
            payload
        };
        self.budget.emit("move", payload).await
```

The block `{ ... }` ends the guard before the `.await`. The same pattern is in `Budget::emit`
("the lock ends here, before the .await") and in `Farmer::tick`.

This program puts the rules together. A handler task changes `hp`; the tick copies `hp` inside
the lock and waits outside it. Then an async mutex holds its guard across an `.await`, and a
`watch` channel carries the latest value:

```rust
// std::sync::Mutex for short sections; tokio::sync::Mutex when the guard must
// live across an .await; watch for "the latest value".
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tokio::sync::watch;

#[derive(Default)]
struct World {
    hp: u32,
}

#[tokio::main]
async fn main() {
    let world = Arc::new(Mutex::new(World { hp: 1000 }));

    // The "dispatcher": a handler changes the world on another task.
    let w = world.clone();
    let handler = tokio::spawn(async move {
        for _ in 0..500 {
            w.lock().unwrap().hp -= 1; // short: lock, change, unlock
            tokio::task::yield_now().await;
        }
    });

    // The "tick": copy what it needs inside the lock, then await outside it.
    for _ in 0..3 {
        let hp = world.lock().unwrap().hp; // the guard ends at the semicolon
        println!("tick reads hp {hp}");
        tokio::time::sleep(Duration::from_millis(1)).await;
    }
    handler.await.unwrap();

    // An async Mutex: the guard may live across an .await (one sender at a time).
    let sink = Arc::new(tokio::sync::Mutex::new(Vec::<String>::new()));
    let mut tasks = Vec::new();
    for i in 0..3 {
        let sink = sink.clone();
        tasks.push(tokio::spawn(async move {
            let mut s = sink.lock().await; // waits without blocking the thread
            tokio::time::sleep(Duration::from_millis(5)).await; // held across .await: allowed
            s.push(format!("frame {i}"));
        }));
    }
    for t in tasks {
        t.await.unwrap();
    }
    println!("sent {} frames, one at a time", sink.lock().await.len());

    // watch: the receiver sees the latest value. AlSocket uses it for "done".
    let (tx, mut rx) = watch::channel(false);
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_millis(10)).await;
        let _ = tx.send(true);
    });
    rx.wait_for(|done| *done).await.unwrap();
    println!("the socket is done; final hp {}", world.lock().unwrap().hp);
}
```

One run printed this. The first three values depend on timing and differ from run to run:

```text
tick reads hp 1000
tick reads hp 500
tick reads hp 500
sent 3 frames, one at a time
the socket is done; final hp 500
```

The final value is always 500. Each change happens under the lock, so no decrement disappears.

#### Channels: share by sending

A channel moves ownership of a value from one task to another. No lock is visible to you. Tokio
has four kinds, and `AlSocket` uses three of them:

- **`mpsc`**: many senders, one receiver, a queue. `AlSocket` has two unbounded ones: `Out`
  frames to the writer, and events to the dispatcher. Unbounded means that a send never waits.
  The reader can never block on a slow dispatcher, so the pong always goes out. The price is
  memory: if the handlers are too slow for a long time, the queue grows without a limit.
- **`oneshot`**: one value, one time. Each waiter.
- **`watch`**: one value that changes; receivers see the latest one. The "done" flag.
- **`broadcast`**: each receiver gets each value. The course does not use it.

#### Poisoning

A `std::sync::Mutex` becomes **poisoned** when a thread panics while it holds the guard. Later,
`lock()` returns `Err(PoisonError)`. The data is still there, maybe half changed. The course handlers run while the dispatcher holds the `World` lock, and a handler can panic. `deliver` catches that panic, but
the `World` mutex is now poisoned. Thus `World::lock` takes the data anyway:

```rust
    pub fn lock(&self) -> MutexGuard<'_, WorldState> {
        self.state.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }
```

`Cooldowns`, `Budget` and `Farmer` do the same. That choice says: "a half-applied event is
better than a dead bot". The next full `entities` or `player` event corrects the state.

#### Lock order

The course has several locks, and a handler can take two at once. The `hit` handler of `Farmer`
runs with `World` locked, then locks `FarmerState`. `Cooldowns` handlers run with `World`
locked, then lock the cooldown map. A deadlock needs two locks taken in opposite orders. The
course avoids it with one rule: **`World` first, and no code locks `World` while it holds
another course lock**. The comment at the top of `cooldowns.rs` states this rule for its file.

#### Atomics and the memory model

For one flag, a lock is too much.

`farm` uses a `static STOP: AtomicBool` that the Ctrl-C task
sets and the tick reads, with `Ordering::SeqCst`. An atomic is a single value that all threads
see change at once, without a lock. Rust's memory model is the C++ one: a `Release` store and an
`Acquire` load of the same atomic make a happens-before edge. A `Mutex` gives you that edge for
all the data it protects. A channel gives it for the value it moves. If you use only these
tools, you do not need to think about orderings.

</div>

<div data-lang="java">

In JavaScript and Python, handlers and the tick share one thread, and the state changes only at an `await`. In Java, they share memory across threads that run at the same time. A data race is real here: two threads can read and write one field in the same nanosecond. Two problems follow, and you need both in your model.

#### Problem 1: atomicity

`count++` is three steps: read, add, write. Two threads can both read 5 and both write 6. The program loses one update:

```java
// Race.java: two threads add 1,000,000 each to a counter, three ways.
// Run: java Race.java
import java.util.concurrent.atomic.AtomicLong;

public class Race {
    static long plain = 0;                         // no lock: a data race
    static long locked = 0;                        // guarded by Race.class
    static final AtomicLong atomic = new AtomicLong();

    public static void main(String[] args) throws Exception {
        Runnable add = () -> {
            for (int i = 0; i < 1_000_000; i++) {
                plain++;                               // read, add, write: three steps
                synchronized (Race.class) { locked++; } // one thread at a time
                atomic.incrementAndGet();              // one atomic read-add-write
            }
        };
        Thread a = Thread.ofPlatform().start(add), b = Thread.ofPlatform().start(add);
        a.join();
        b.join(); // join: everything the thread wrote happens-before join returns
        System.out.println("plain:  " + plain);
        System.out.println("locked: " + locked);
        System.out.println("atomic: " + atomic.get());
    }
}
```

```text
plain:  1940741
locked: 2000000
atomic: 2000000
```

The first number is different on each run. The other two are always 2,000,000.

#### Problem 2: visibility

The second problem is less obvious. Without a rule that connects two threads, a thread may never see a write of another thread. The JIT compiler can keep a field in a register, and the CPU can reorder writes. Both are legal:

```java
// Visibility.java: a loop that reads a plain field can miss a write from another thread.
// Run: java Visibility.java
public class Visibility {
    static boolean plainStop = false;          // no happens-before edge to the reader
    static volatile boolean volatileStop = false;

    public static void main(String[] args) throws Exception {
        Thread a = Thread.ofPlatform().daemon().start(() -> { long n = 0; while (!plainStop) n++; });
        Thread b = Thread.ofPlatform().daemon().start(() -> { long n = 0; while (!volatileStop) n++; });
        Thread.sleep(1000);  // the JIT compiles the loops in this time
        plainStop = true;
        volatileStop = true;
        a.join(2000);
        b.join(2000);
        System.out.println("plain loop ended:    " + !a.isAlive());
        System.out.println("volatile loop ended: " + !b.isAlive());
    }
}
```

```text
plain loop ended:    false
volatile loop ended: true
```

On HotSpot, the compiled loop reads `plainStop` once and never again. The Java Memory Model allows this. A different JVM or CPU can give a different result, which is exactly the problem.

#### The Java Memory Model in one rule

The Java Memory Model (JLS chapter 17) defines **happens-before**, an order between actions in different threads. The rule: if write W happens-before read R, then R sees W (or a later write). If no happens-before chain connects them, the program has a **data race**, and R can see an old value.

These are the edges that you use in an AL bot:

| Edge | From | To |
|---|---|---|
| Program order | each action of a thread | each later action of the same thread |
| Monitor | the end of a `synchronized` block on `x` | each later start of a `synchronized` block on `x` |
| `volatile` | a write of a `volatile` field | each later read of that field |
| Thread start | `t.start()` | the first action of `t` |
| Thread end | the last action of `t` | the return of `t.join()` |
| Concurrent collections | `queue.put(x)`, `map.put(k, v)` | the `take`/`get` that returns that item |
| Futures | `complete(v)` | the return of `get()`/`join()` and each dependent stage |
| Locks and atomics | `unlock()`, an atomic write | the next `lock()`, an atomic read of that value |

Happens-before is transitive. This is why `AlSocket` needs no extra fence for its events. The listener thread builds a `JsonNode`, then calls `events.add`. The dispatcher returns from `events.take()`, then reads the node. The queue gives the edge, so the dispatcher sees the full node.

#### The tools

- **`synchronized`** gives mutual exclusion and the monitor edge. It is reentrant: a thread that holds a lock can take it again. The course uses it everywhere. In Java 21, a virtual thread that blocks inside it pins its carrier (chapter [Async 4](#guide-async-4-what-await-does)).
- **`volatile`** gives visibility and order for one field, with no lock. It does not make `x++` atomic. Use it for a flag that one thread writes and others read: `Farm.stop`.
- **Atomics** (`AtomicInteger`, `AtomicReference`, ...) give atomic read-modify-write with compare-and-set (CAS), with no lock. `Farm` uses `lost.compareAndSet(null, reason)`: the first reason wins, and later ones change nothing.
- **`java.util.concurrent.locks`**: `ReentrantLock` adds `tryLock`, a timed lock, an interruptible lock and `Condition`. It parks with `LockSupport`, so a virtual thread unmounts while it waits for the lock or blocks inside it. Prefer it to `synchronized` if Java 21 code must block while it holds a lock.
- **`ConcurrentHashMap`** is safe for many threads with no outer lock. Its reads do not lock. Each single call is atomic, and `compute`, `merge` and `putIfAbsent` are atomic read-modify-writes. A sequence of calls is not atomic: `if (!m.containsKey(k)) m.put(k, v)` is a race. Use `putIfAbsent`.
- **`BlockingQueue`** moves objects between threads with the happens-before edge. `LinkedBlockingQueue` has no size limit by default: `put` never blocks. `ArrayBlockingQueue` has a fixed size: `put` blocks when it is full.

#### Holding a lock across a wait

In Java, "a wait" means a blocking call. Do not block while you hold a lock that a handler needs. Consider this mistake in a tick:

```java
synchronized (world) {                        // fragment: the WRONG way
    var r = act.attack(world.nearestMonster().path("id").asText()); // blocks up to 2 s
}
```

The reply is a `game_response`, and `World` has handlers for it (the ones of `Cooldowns` and `Actions`). `deliver` runs those handlers before it completes the waiter. Each of them needs the `world` lock, and the tick holds it. Thus the dispatcher blocks, and the waiter can never complete. The tick waits for the full timeout of 2 s, and `attack` returns `null`. Only then does the tick release the lock.

In Java 21, a fighter that does this on a virtual thread also pins its carrier for the 2 s. Copy what you need inside the lock. Then act outside it.

#### How the course keeps state safe

The course uses one design for each shared object: one lock, short critical sections, and no blocking inside them.

- **`World` has one lock: the `World` object.** Each public method is `synchronized`, and `World.dispatch` runs every handler of the world inside that lock. Thus a handler always sees a consistent world, and your code reads it with `synchronized (world) { ... }`.
- **`Cooldowns`, `Budget`, `Farmer`, `Party` each lock their own object.** Their handlers run through `world.listen`, so they run inside the `World` lock and then take their own. The order is always `world` first, then the object. `Farmer.tick` takes the locks in the same order:

```java
synchronized (world) {
    String current;
    synchronized (this) { current = target; } // World lock, then ours: the order of the handlers too
```

  One order for all threads means no deadlock between these locks.
- **`Farmer.tick` copies, then acts.** It reads `hp`, `map`, `range` and the target inside the locks, into local variables. It calls `act.heal` or `act.attack` after it leaves them. Those calls block on the network.
- **`Budget.emit` sleeps outside its lock.** It checks and records the cost inside `synchronized (this)`, then sleeps outside it if the window is full. A full window thus never holds back the `new_map` handler, which records the cost of a map change.
- **`AlSocket` has its own `lock` and `sendLock`.** It runs handlers outside `lock`, so a handler can call `on`, `waitFor` or `emit`. A predicate of `waitFor` runs inside `lock`. Keep each predicate a pure test of the payload. A predicate that takes the `World` lock would take two locks in the opposite order of `World.listen`, which holds `world` and then calls `sock.on`.

</div>

## Async 8: AlSocket, read with these eyes

[`AlSocket`](#learn-alsocket) is about 200 to 330 lines in each language. This chapter reads it
in the order of a session: connect, read, answer the ping, dispatch, wait, send, close. Each
part names the concept from the earlier chapters that it uses.

<div data-lang="js ts">

#### Read it in the order of a session

`course/js/albot/alsocket.js` has 171 lines. Each part uses one idea from the earlier chapters.
The TS file `course/ts/albot/alsocket.ts` has the same code with types, so this reading covers
both. The quotes are exact.

#### Connect and handshake: a promise around events

```js
// fragment: course/js/albot/alsocket.js
  static connect(url, timeoutMs = 10_000) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      const sock = new AlSocket(ws);
```

`connect` is the "make a promise from events" of Async 3. The executor opens the WebSocket and
adds three listeners. The promise has four exits: `resolve(sock)` on Socket.IO `40`, and `reject`
on `44`, on the timer, or on `close` before `40`. After a `44`, the `close` listener calls
`reject` a second time. That is safe, because a settled promise ignores it (settles one time).

The `message` listener stays for the whole session. After the handshake, it passes each packet
to `#onPacket`.

`WebSocket` is the global of Node.js 22, built from undici. Its events run on the main thread,
in the poll phase.

#### The reader and the pong: inside one task

```js
// fragment: course/js/albot/alsocket.js
  #onPacket(packet) {
    if (packet === "2") {
      // Engine.IO ping from the server. Send a pong at once. If you don't,
      // the server drops you after pingInterval + pingTimeout.
      this.#ws.send("3");
```

The JS client has no separate reader. The reader is the `message` listener, and the pong goes
out in the same task as the ping arrives. This is correct only while no task runs long. The
pong has no protection from your code (Async 2). Go, C#, Rust and Java put the reader on its
own thread or task. JavaScript cannot.

`JSON.parse` in `#onPacket` is inside a `try`. An exception that leaves an `EventTarget`
listener becomes an uncaught exception in Node.js, and the process stops. An earlier version had
no `try`, so one bad frame stopped the bot. Now `#onPacket` logs the bad frame and continues
with the next one, as the other languages do.

#### The dispatcher: handlers first, then waiters

```js
// fragment: course/js/albot/alsocket.js
    // Copies of both lists, made before any handler runs: a handler can call
    // on() or waitFor(). A new handler or waiter starts with the NEXT event,
    // not with this one. (A Set iterator also visits the entries that are
    // added while it runs.)
    const handlers = [...(this.#handlers.get(event) ?? [])];
    const waiters = [...this.#waiters];
    for (const handler of handlers) {
      try {
        const result = handler(data);
        // An `async` handler returns a promise, and AlSocket does not wait for
        // it. Its rejection would be unhandled, and Node.js 15+ then stops the
        // process. Log it, as we log a throw.
        if (typeof result?.then === "function") {
          result.then(undefined, (/** @type {unknown} */ err) => console.error(`async handler for "${event}" failed:`, err));
        }
      } catch (err) {
        console.error(`handler for "${event}" threw:`, err); // one bad handler must not stop the socket
      }
    }
    for (const w of waiters) {
```

`#deliver` runs inside the `message` task. Events run in arrival order, one at a time, because
there is one thread. Each handler runs synchronously, in a `try`. Then each waiter gets the
event.

- **Handlers first.** The handlers of an event run before its waiter resolves, in all seven
  languages of the course. In JS, the continuation after `await` runs later still, in a
  microtask. So your code after `await reply` always sees the state that the reply's handlers
  wrote.
- **An async handler is not awaited.** `handler(data)` returns a promise, and `#deliver` does
  not wait for it. The handler's code after its first `await` runs later, after other events.
  The `try` only catches a synchronous throw. Thus `#deliver` adds a rejection handler to each
  promise that a handler returns, and logs the error. In an earlier version, such a rejection
  had no handler, and it stopped the process. Still, keep handlers synchronous.
- **The lists are copies.** A handler can call `on` or `waitFor`. In an earlier version,
  `#deliver` iterated the live `Set` of waiters. A JavaScript `Set` iterator also visits the
  entries that the loop adds while it runs. So a waiter that a handler added got the event that
  `#deliver` gave out at that time. Now `#deliver` copies both lists before the first handler
  runs. A new handler or waiter starts with the next event.

#### The early events: a microtask on purpose

```js
// fragment: course/js/albot/alsocket.js
  #subscribed(event) {
    this.#listening = true;
    const kept = this.#early.get(event);
    if (!kept) return;
    this.#early.delete(event);
    // In a microtask, so that waitFor() registers its waiter first.
    queueMicrotask(() => {
      for (const data of kept) this.#deliver(event, data);
    });
  }
```

The server sends `welcome` as soon as the namespace connects. That can be before your code
calls `waitFor("welcome")`. Until the first `on` or `waitFor`, `#deliver` keeps each event in
`#early`. The first subscriber of a name gets its kept events.

This uses Async 2 and Async 3 together. `on` and `waitFor` register first, then call
`#subscribed`. A `queueMicrotask` delivery runs when the current synchronous code ends. By then,
each handler and waiter that this code registers for the name is in place. A handler also never
runs inside the `on` call that registers it. And the next `message` task waits for the
microtasks, so no newer event comes before the kept one.

#### `on` and the waiter

`on(event, handler)` pushes the handler on a list and calls `#subscribed`. It has no `off`. The
login code of the course uses a `done` flag to make its handlers do nothing later.

`waitFor` is the hand-made promise of Async 3: the executor registers the waiter, the timer
and `#shutdown` are the other exits, and `done()` cleans up. `request` builds the rule "wait,
then send, then await" on it.

#### `emit` and the send rule

```js
// fragment: course/js/albot/alsocket.js
  emit(event, data) {
    if (this.#closed) throw new Error("socket is closed");
    const args = data === undefined ? [event] : [event, data];
    this.#ws.send("42" + JSON.stringify(args));
  }
```

`emit` is synchronous. It returns nothing to await. `ws.send` writes the frame in the current
task. There is no send queue in `AlSocket`, because one thread cannot make two sends overlap.
C# and Java need a lock or a chain for this.

The rate limit is one level up, in
`Budget.emit`. That method is async because it can sleep.

#### Close and the end

```js
// fragment: course/js/albot/alsocket.js
  close() {
    if (this.#closed || this.#closeTimer) return;
    if (this.#ws.readyState === WebSocket.OPEN) this.#ws.send("41");
    this.#ws.close(1000);
    this.#closeTimer = setTimeout(() => this.#shutdown("closed by us (no close from the server in 5 s)"), 5000);
    this.#closeTimer.unref(); // this timer alone must not keep Node.js running
  }
```

`close` starts the WebSocket close and returns. It does not run `#shutdown`. That runs later,
in the `close` event task, from the `close` listener of `connect`. So after `close()`,
`#closed` is still `false` for a short time, and your `disconnect` handler runs in a later
task.

If the server never answers the close, the `close` event does not come. An earlier version then
left each waiter to its own timer, and `disconnect` never came. Now `close` starts a 5 s timer
that calls `#shutdown` itself. `unref()` tells Node.js that this timer alone must not keep the
process alive. When the `close` event comes first, `#shutdown` clears the timer.

`#shutdown` then does three things in order: mark the socket closed, deliver `disconnect` to
the handlers, reject each waiter (Async 6). Nothing reconnects. The program makes a new
`AlSocket` for each connection.

#### What differs from the other languages

- **One thread for everything.** The reader, the pong, the dispatcher, your handlers and your
  tick share the main thread. The other languages give the reader its own thread or task.
- **No locks.** One thread makes them unnecessary for `AlSocket` and the course state.
- **Handlers first, then the waiter, then your continuation in a microtask.**
- **`close()` does not wait.** It returns at once. The `disconnect` event comes later, at
  most 5 s later. In the other languages, `close` waits for the end, at most 5 s.
- **The TS login code differs from the JS one.** TS `enterGame` registers `on("welcome")` and
  each failure before its first `await`, and uses `Promise.race([welcome, failed])`. JS
  `enterGame` awaits `waitFor("welcome")` first, then registers the other handlers. Both are
  correct, because `AlSocket` keeps the early events.

</div>

<div data-lang="python">

This chapter reads `course/python/albot/alsocket.py` in the order of a session. For each
part, it names the idea from the earlier chapters that the part uses.

#### Connect and handshake

```python
        async with asyncio.timeout(timeout):
            # ping_interval=None: stop the WebSocket pings of the library.
            # Socket.IO has its own ping and pong (below). One is enough.
            # max_size: accept messages up to 16 MiB (the default is 1 MiB).
            ws = await connect(url, ping_interval=None, max_size=16 * 2**20)
            # Engine.IO "open": 0{"sid", "pingInterval", "pingTimeout", ...}
            packet = await ws.recv()
```

- **`asyncio.timeout`** limits the whole handshake to 10 s: the DNS lookup, TCP, the
  WebSocket upgrade and two Socket.IO packets. If it fires, it cancels the current task at its
  `await`, and the block raises `TimeoutError`.
- **`connect`** uses the thread pool for `getaddrinfo` when the URL has a host name. That is
  the `asyncio_0` thread of [The runtime](#guide-async-2-the-runtime).
- **`ping_interval=None`** turns off the keepalive task of `websockets`. With it, the library
  starts no task of its own. The protocol works through callbacks of the transport.
- In this phase, `connect` reads with `ws.recv()` directly. No reader task exists yet.

#### The reader

```python
        sock = cls(ws)
        # From now on, one background task reads all packets.
        sock._reader = asyncio.create_task(sock._read_loop())
        return sock
```

- **`create_task`** starts the reader at the next iteration. `connect` returns first. Thus
  your code can call `on` and `wait_for` before the reader delivers the first event.
- **A strong reference** (`sock._reader`) keeps the task alive. `close` awaits it.

`_read_loop` is `async for packet in self._ws`. Each iteration awaits the next message. If
`websockets` already has a message in its queue, `recv` returns at once, without a
suspension. Thus one reader step can process many frames. The queue of `websockets` holds 16
frames by default. Above that, `websockets` stops reading from the transport until the reader
catches up, and the kernel buffer holds the rest.

#### The pong

```python
                if packet == "2":
                    # Engine.IO ping. Send a pong at once. If you don't, the
                    # server drops you after pingInterval + pingTimeout.
                    await self._ws.send("3")
```

- **The pong is inline in the reader.** No other task and no lock takes part. The reader
  answers a ping in the same step that reads it.
- **`await send` does not suspend** in the normal case. `websockets` writes the frame to the
  socket at once. It waits only when the write buffer is above its limit.
- **The weak point is the thread, not the code.** The reader can run only when the loop runs.
  A blocking call anywhere in the bot delays every pong (see `rt_block.py`).

#### The dispatcher

```python
        # Copies: a handler can call on() or wait_for(). A handler or a waiter
        # that is added now must not get the event that is delivered now.
        for handler in list(self._handlers.get(event, [])):
            try:
                result = handler(data)
                if inspect.isawaitable(result):  # an async handler runs as a task
                    task = asyncio.ensure_future(result)
                    self._handler_tasks.add(task)  # keep it alive until it ends
                    task.add_done_callback(self._handler_done)
            except Exception:
                traceback.print_exc()  # one bad handler must not stop the socket
```

- **The dispatcher is a plain function, inside the reader step.** There is no queue between
  reader and dispatcher. The events go to the handlers in arrival order, one at a time.
- **A `def` handler** runs to its end before the reader reads the next frame. A slow one
  delays everything, the pong included.
- **An `async def` handler** returns a coroutine. `ensure_future` wraps it in a task, and the
  task starts at the next iteration. Nobody awaits it, so the `try` cannot catch its errors.
  `_handler_tasks` keeps the task alive (a weak reference only would not), and
  `_handler_done` prints its error when it ends (see
  [Cancellation, timeouts and errors](#guide-async-6-cancellation-timeouts-and-errors)).
- **Copies of the lists.** A handler can call `on` or `wait_for` for the same event. The loops
  run over copies, so a handler or a waiter that is new does not get the event of now.
- **`except Exception`**, not `BaseException`. A `BaseException` from a handler, for example
  `SystemExit`, ends the reader.

After the handlers, `_deliver` checks each waiter of that event name. A match calls
`fut.set_result(data)`. **Handlers run first**, as in JS, Go and Rust. In Python the order
is even stronger. `set_result` only queues the wake-up. Thus the waiting task resumes after the
whole reader step, also after the handlers of later events in the same read.

#### The early events

```python
        # Soon, not now, so that wait_for() registers its waiter first.
        asyncio.get_running_loop().call_soon(replay)
```

- Until the first `on` or `wait_for`, `_deliver` keeps each event in `_early`, by name. The
  server sends `welcome` right after the handshake, before your code can wait for it.
- The first subscriber of a name gets the kept events of that name. `_subscribed` gives them
  with **`call_soon`**, not at once. `wait_for` calls `_subscribed` as its last step. If it
  replayed at once, `welcome` would reach `_deliver` before the caller had the coroutine.
  With `call_soon`, the replay is a later handle, after the current step.
- After the first subscription of any name, `_listening` is true. An event without a handler
  or a waiter then goes nowhere. Kept events of other names stay in `_early` until their first
  subscriber.

#### `on`

```python
    def on(self, event: str, handler: Callable[[Any], Any]) -> None:
        """Call handler(data) for each `event` from now on (sync or async)."""
        self._handlers.setdefault(event, []).append(handler)
        self._subscribed(event)
```

`on` is a plain `def`. It changes a dict and returns. No lock is necessary: the reader cannot
run while `on` runs. `World.listen` subscribes one dispatch function for each name. Thus the
handlers of `World`, `Cooldowns`, `Budget`, `Actions` and `Farmer` run in `listen` order.

#### The waiter

`wait_for` is the hand-made Future of [The unit of async work](#guide-async-3-the-unit-of-async-work):

- **`loop.create_future()`** makes the waiter. A plain `def` registers it during the call.
- **`loop.call_later(timeout, expire)`** is the timer. It sets `TimeoutError` as a result. It
  does not cancel a task.
- **`fut.add_done_callback(cleanup)`** removes the waiter and cancels the timer. It runs for
  each end: a match, the timer, the close, and a cancellation of the task that awaits.
- **`fut.add_done_callback(_retrieve)`** marks the error of the future as read. A caller that
  never awaits (its send failed) then leaves no "never retrieved" log.
- **The returned coroutine** is lazy, but it only awaits a future that exists.

This is why `request` can call `wait_for`, then `emit`, then `await`, with no gap in which a
reply could pass.

#### `emit` and the send rule

```python
        if self._closed:
            raise ConnectionError("socket is closed")
        args = [event] if data is None else [event, data]
        try:
            await self._ws.send("42" + json.dumps(args, separators=(",", ":")))
        except ConnectionClosed as err:
            # The connection ended, but the reader has not reported it yet.
            # Raise the same error as after the report.
            raise ConnectionError("socket is closed") from err
```

C# and Java need a lock or a chain to keep two sends apart. Python does not. `websockets`
writes each frame in one piece, inside one step, so two frames cannot mix. A pong from the
reader and an `emit` from the tick are always whole frames on the wire. `emit` is a coroutine,
so it does nothing without `await`. Each failure of `emit` is a `ConnectionError`: before
`_shutdown` (from `_closed`) and in the gap after the TCP end (from `ConnectionClosed`).

#### Close and the end

`close` sends `41`, closes the WebSocket, then awaits the reader task. The reader leaves its
`async for`, and its `finally` calls `_shutdown`. `_shutdown` runs one time. It delivers the
local `disconnect` to the handlers, then sets `ConnectionError` on each open waiter.

```python
        except asyncio.CancelledError:
            # Somebody cancelled the reader (close() after its time limit, or
            # asyncio.run at the end of the program). Nothing reads the socket
            # from now on, so close the transport at once: else the server
            # keeps the character online until its ping timeout.
            reason = "reader cancelled"
            self._abort()
            raise
        finally:
            # In `finally`, so that the end is reported for every cause, also a
            # cancellation: the `disconnect` event, then each waiter fails.
            self._shutdown(f"{reason} (code {self._ws.protocol.close_code})")
```

- **`finally`, because cancellation is an exception.** An earlier version called `_shutdown`
  after the `try`. A `CancelledError` at the `await` of the reader went past that line. Then
  no `disconnect` came, and each waiter ended only at its own timer.
- **`except asyncio.CancelledError` re-raises.** The reader drops the TCP connection, then
  lets the cancellation continue, so the task ends as cancelled.

`close` has a limit of 5 s:

```python
            async with asyncio.timeout(5):
                try:
                    await self._ws.send("41")
                except Exception:
                    pass  # the connection is already gone
                await self._ws.close()
                if self._reader:
                    await self._reader  # the reader ends and reports "disconnect"
        except TimeoutError:
            # Force the end: drop the TCP connection, and stop the reader. Its
            # `finally` reports "disconnect" and fails the waiters.
            self._abort()
            if self._reader:
                self._reader.cancel()
                await asyncio.wait([self._reader])  # wait() does not raise
```

Without the limit, a server that does not answer the close held `close` for 10 s, the close
timeout of `websockets`. Then `close` also waited for the reader. `asyncio.wait` waits for the reader without
the exception of the reader. Thus `close` returns normally, and the `disconnect` handlers ran
before it returns.

#### Differences from the other languages

| Point | Python today |
|---|---|
| Threads | One. Reader, dispatcher, handlers and tick share the loop thread. Go, C#, Rust and Java use more than one. |
| Order of handlers and waiter | Handlers first. The waiting task resumes after the reader step ends. |
| A slow handler | Delays the pong. In Go, C#, Rust and Java, the reader is separate from the dispatcher. |
| `async def` handler | Runs as its own task. `AlSocket` keeps a reference until it ends, and prints its error. |
| `request` on a closed socket | Raises `ConnectionError` from `emit`. `request` closes the unused `reply`, and `_retrieve` marks the error of its future as read, so nothing more is logged. |
| Cancelled reader | Drops the TCP connection and still reports `disconnect` (from `finally`). |
| `close` | Returns in 5 s at most. |

</div>

<div data-lang="go">

This chapter reads `course/go/alsocket/alsocket.go` in the order of a session. For each
part, it names the idea from the earlier chapters that the part uses. The quotes are exact
copies of the course code.

#### The shape: one struct, two goroutines, one lock

```go
	mu        sync.Mutex // guards the six fields below
	handlers  map[string][]Handler
	waiters   map[*waiter]struct{}
	early     map[string][]json.RawMessage // payloads from before the first On/Expect
	replay    []event                      // kept events that dispatchLoop gives out next
	listening bool                         // true after the first On/Expect
	closed    bool

	closing   atomic.Bool   // Close sets it, so that readLoop knows the end was ours
	events    chan event    // readLoop -> dispatchLoop
	wake      chan struct{} // subscribed -> dispatchLoop: "replay has events" (buffer of 1)
	quit      chan struct{} // closed by Close: readLoop stops a wait for a full buffer
	quitOnce  sync.Once     // Close can run more than one time; close(quit) only once
	endReason string        // why the connection ended; readLoop sets it before close(events)
	done      chan struct{} // closed when the connection has ended
```

Three tools from [Async 7](#guide-async-7-shared-state) are here. A mutex guards the maps
and lists that many goroutines use. An atomic flag carries one bit from `Close` to
`readLoop`. Four channels carry events, a wake signal, the "stop" of `Close`, and the end
signal. `endReason` has no lock. The close of `s.events` is its happens-before edge, as the
section on the end shows.

#### Connect and the handshake

`Connect` runs on the goroutine of the caller. It is plain blocking code with a deadline:

```go
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	conn, _, err := websocket.Dial(ctx, url, nil)
```

The Engine.IO `open` packet, the `40` that it sends, and the `40` reply are three blocking
calls in a row: `conn.Read`, `conn.Write`, `conn.Read`. Each one parks the goroutine in the
netpoller ([Async 2](#guide-async-2-the-runtime)). No goroutine exists yet for the socket.
The handshake needs none, because it is one conversation in order.

Then `Connect` makes the `Socket` and starts the two loops:

```go
		// If this buffer is full, readLoop waits, and pings get no answer.
		events: make(chan event, 1024),
		wake:   make(chan struct{}, 1),
		quit:   make(chan struct{}),
		done:   make(chan struct{}),
	}
	go s.readLoop()
	go s.dispatchLoop()
```

#### The reader and the pong

`readLoop` is the only goroutine that reads. This is a rule of the library: `Read` must not
run on two goroutines at once. It reads with `context.Background()`, because the end of a
read `ctx` closes the connection ([Async 6](#guide-async-6-cancellation-timeouts-and-errors)).

```go
		case packet == "2":
			// Engine.IO ping. Send a pong at once. If you don't, the server
			// drops you after pingInterval + pingTimeout.
			s.write("3")
```

The pong goes out on the reader goroutine, before the next read. Your handlers run on a
different goroutine. Thus a slow handler cannot delay a pong, with one limit. The reader
blocks when `s.events` is full:

```go
func (s *Socket) send(ev event) bool {
	select {
	case s.events <- ev: // the usual case: room in the buffer
		return true
	default:
	}
	select {
	case s.events <- ev:
		return true
	case <-s.quit:
		return false
	}
}
```

This send is the only place where your code can stop the reader. If your handlers fall
1,024 events behind, the send parks `readLoop`. Then no ping gets an answer, and the server
closes the socket after the 12 s of `pingTimeout`. The buffer is a choice. An unbounded
queue cannot stop the pongs, but it can grow without a limit. A bounded queue keeps memory
bounded, and turns a stuck handler into a disconnect.

The second `select` has one more case: `s.quit`, which `Close` closes. It matters only when
a handler never returns. An earlier version had a plain send here. With a stuck handler and a
full buffer, `readLoop` then waited on that send forever, also after `Close`. It never read
again, so it never saw the end of the connection.

Now `Close` releases it. `readLoop` drops the event that it held, but no goroutine could give
it out: it is the same as a frame that nobody read. The first `select`, with `default`, keeps the usual path free of that choice. Without it, a
send with room in the buffer could lose to a closed `quit`, because `select` chooses at
random.

#### The early events

The server sends `welcome` at once after the handshake. The reader starts before your code
can call `On` or `Expect`. Thus `readLoop` keeps each event while `listening` is false:

```go
			if !s.listening {
				// Nobody listens yet: keep the event (see subscribed).
				s.early[name] = append(s.early[name], data)
				s.mu.Unlock()
				continue
			}
```

The first `On` or `Expect` sets `listening`. Then `subscribed` moves the kept events of that
name to a list, `replay`, and wakes the dispatcher:

```go
	for _, data := range kept {
		s.replay = append(s.replay, event{name, data})
	}
	s.mu.Unlock()
	if len(kept) > 0 {
		select {
		case s.wake <- struct{}{}: // dispatchLoop can wait on its channels: wake it
		default: // a wake is already there; one is enough
		}
	}
```

The dispatcher gives out the list before its next event. Thus a kept event runs on the
dispatch goroutine, as each other event does. Two handlers never run at the same time.

An earlier version called `deliver` for the kept events directly in `subscribed`, **on the
goroutine that called `On` or `Expect`**. For a short moment, two goroutines then ran
handlers at the same time: yours (a kept event) and `dispatchLoop` (a new event). The rule
"one ordered stream" was broken. A test showed it: the kept `welcome` ran on the main
goroutine, and the next `game_response` on the dispatch goroutine.

Three details make the new design correct:

- **The wake channel has a buffer of 1, and the send has a `default`.** `subscribed` never
  waits for the dispatcher. More wakes than one carry no more information.
- **`s.events` is not the way.** It has a limit of 1,024, and `readLoop` already writes it. A send from
  `subscribed` could wait, and it could put the kept event behind newer ones.
- **`Expect` registers its waiter before it calls `subscribed`.** Thus the waiter is in the
  map when the dispatcher gives out the kept event.

There is a second Go detail. After the first `On` or `Expect`, the socket keeps nothing. In
Go, `welcome` can arrive before or after `World` registers its handlers, because the reader
runs on its own goroutine. Thus `bot.ConnectWith` calls `Expect("welcome", nil)` first, before
`world.New`. That `Expect` sets `listening`, and it catches `welcome` in both cases.

#### The dispatcher

```go
func (s *Socket) dispatchLoop() {
	for {
		s.replayKept() // kept events go before any event that came later
		select {
		case ev, ok := <-s.events:
			if !ok {
				s.end()
				return
			}
			s.replayKept() // subscribed can add some while we waited
			s.deliver(ev)
		case <-s.wake: // subscribed added kept events: the next loop gives them out
		}
	}
}
```

The receive returns `ok == false` when `readLoop` closed the channel and the buffer is empty.
This one goroutine gives each event to its handlers in arrival order, one at a time. It is
the Go form of "one ordered stream" from the overview. The second `replayKept` covers a
kept event that `subscribed` added while the `select` waited: it must still go before the
event that the `select` returned.

`deliver` copies the handlers and the matching waiters under the lock, then runs them after
the unlock:

```go
	// Handlers first, then waiters. Thus, when a wait returns, the handlers
	// of the same event (for example, the ones that update your copy of the
	// world) have already run.
	for _, h := range handlers {
		safeCall(ev.name, h, ev.data)
	}
	for _, w := range matched {
		w.ch <- ev.data // the buffer has room for 1, so this never blocks
	}
```

Three ideas are in these lines:

- **Copy under the lock, call after it.** A handler can call `On` or `Emit`, which lock
  `s.mu`. A Go mutex is not reentrant, so a call under the lock would deadlock. The
  predicates are the exception: they run under the lock, so a predicate must not call a
  `Socket` method.
- **Handlers first, then waiters.** JavaScript, Python and Rust use this order too. C# and
  Java complete the waiter first, then run the handlers. In Go, when `wait(ctx)` returns, the
  `World` already shows the event. Also, the send to `w.ch` is the happens-before edge to
  your goroutine. Thus your goroutine sees each write of the handlers.
- **`safeCall` recovers a panic.** A bug in one handler does not end the program
  ([Async 6](#guide-async-6-cancellation-timeouts-and-errors)).

Because one goroutine runs all handlers, a handler that waits for a reply waits forever. The
reply is in `s.events`, behind the handler. This program shows it:

```go
// handlerwait: a handler that waits for a reply. The reply must come through
// the dispatch goroutine, and that goroutine is in the handler. The wait can
// only end at its deadline.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"albot/alsocket"
	"checks/fakeal"
)

func main() {
	fakeal.ServeIfChild()
	// The server answers attack with a `hit`, then a game_response.
	url, stop := fakeal.StartProcess(fakeal.Options{ReplyDelay: 10 * time.Millisecond, HitBeforeGR: true})
	defer stop()
	sock, err := alsocket.Connect(context.Background(), url)
	if err != nil {
		panic(err)
	}
	defer sock.Close()
	if _, err := sock.WaitFor(context.Background(), "welcome", nil); err != nil {
		panic(err)
	}
	start := time.Now()
	done := make(chan struct{})
	sock.On("hit", func(json.RawMessage) { // WRONG: a wait inside a handler
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		// The game_response is already on its way, but it sits in the
		// events channel behind this handler. Nobody can deliver it.
		_, err := sock.WaitFor(ctx, "game_response", nil)
		fmt.Printf("handler after %v: %v\n", time.Since(start).Round(100*time.Millisecond), err)
		close(done)
	})
	_ = sock.Emit("attack", map[string]any{"id": "goo"})
	<-done
}
```

It prints:

```text
handler after 1s: waiting for "game_response": context deadline exceeded
```

The reply arrived after 10 ms. The handler still waited the full second.

#### `On` and the waiter

`On` appends the handler under the lock, then calls `subscribed`. `Expect` registers the
waiter under the lock, then returns the wait function from
[Async 3](#guide-async-3-the-unit-of-async-work). Note one detail of `Expect`:

```go
	s.mu.Lock()
	closed := s.closed
	if !closed {
		s.waiters[w] = struct{}{}
	}
	s.mu.Unlock()
```

The check of `closed` and the registration are in one locked section, and the call to
`subscribed` comes after it. `dispatchLoop` sets `closed` under the same lock before it
closes `s.done`. Thus either the waiter registers before the end, and `s.done` wakes it. Or
it sees `closed`, and returns `ErrClosed`. No waiter can fall between the two.

The wait function is the one from
[Async 6](#guide-async-6-cancellation-timeouts-and-errors). Its deadline case checks if
`deliver` already took the waiter, so a reply never loses to a deadline that comes at the
same time.

#### `Emit` and the send rule

```go
func (s *Socket) write(packet string) error {
	// 10 s: if a write takes longer, the connection is dead.
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return s.conn.Write(ctx, websocket.MessageText, []byte(packet))
}
```

`Emit` (from your goroutines) and the pong (from `readLoop`) both call `write`. In
`coder/websocket`, `Write` is safe to call from many goroutines at once. Each call takes the
write lock of the connection, so two frames never mix. Thus `alsocket` needs no lock and no
writer goroutine of its own. The C# and Java clients allow one send at a time, so their
`AlSocket` must order the sends itself.

`Emit` returns when the frame is in the kernel's send buffer, not when the server reads it.
The server sends no acknowledgements, so a reply is the only proof.

#### Close and the end

```go
func (s *Socket) Close() error {
	s.closing.Store(true)
	s.quitOnce.Do(func() { close(s.quit) })
	timer := time.NewTimer(closeWait)
	defer timer.Stop()
```

`Close` sets the atomic flag first. Then `readLoop` gets an error from `Read`, reads the
flag, and reports `"closed by client"`. Any other end gives the close code or the transport
error. In each case, the end follows the same order:

1. `readLoop` notes the reason in `endReason`, then closes `s.events`. A close never waits.
2. `dispatchLoop` gives out each event that is still in the channel.
3. `dispatchLoop` gives the local `disconnect` event with the reason, after every other
   event.
4. `dispatchLoop` sets `closed` under the lock, then closes `s.done`.
5. Each waiter wakes and returns `ErrClosed`. `sock.Done()` also unblocks.

`readLoop` writes `endReason` without the lock, and `dispatchLoop` reads it without the lock.
This is not a data race. The write comes before `close(s.events)` in `readLoop`. The close
happens before the receive that reports the closed channel. Thus the write happens before
the read ([Async 7](#guide-async-7-shared-state), rule 2).

An earlier version sent `disconnect` from `readLoop`, as a normal event on `s.events`. That
send could wait on a full buffer, like any other send. The new order needs no send at the
end, so `readLoop` always ends.

`Close` itself has a limit of 5 s (`closeWait`). It runs the clean close (`41`, then the
WebSocket close handshake) on a goroutine, and then it waits for `s.done`. If the 5 s end
first, it calls `conn.CloseNow`, which ends the connection without the handshake, and
returns an error. Thus `Close` cannot hang the program, also when the server does not
answer or a handler does not return. One result: do not call `Close` from a handler. The
dispatcher is then in your handler, `s.done` cannot close, and `Close` waits the full 5 s.

A handler that never returns is still your bug. `Close` releases `readLoop`, but nothing can
release the dispatch goroutine. A test with a stuck handler and 1,100 events behind it shows
the difference. Before the fix, `readLoop` stayed in `[chan send]` after `Close`. After the
fix, `Close` returned after 5 s, `readLoop` ended, and only the dispatch goroutine waited. When
the test released the handler, the dispatcher gave out the 1,024 buffered events, then
`disconnect`.

</div>

<div data-lang="csharp">

Now read [`AlSocket.cs`](#learn-alsocket) from top to bottom, in the order of a session. Each
part names the idea from the earlier chapters that it uses. Each quote is an exact copy of
lines in `course/csharp/Albot/AlSocket.cs`.

#### The fields: two locks, one channel

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, the fields
private readonly SemaphoreSlim _sendLock = new(1, 1);

private readonly object _lock = new(); // guards the six fields below
private readonly Dictionary<string, List<Action<JsonElement>>> _handlers = new();
private readonly List<Waiter> _waiters = new();
```

The class holds two kinds of lock, for two kinds of wait ([Async 7](#guide-async-7-shared-state)).
`_sendLock` is a `SemaphoreSlim`, because a send has an `await` inside it. `_lock` is a plain
`lock`, because the tables only change in memory. The `Channel` between the reader and the
dispatcher comes next. It has no limit, so the reader never waits for the dispatcher
([Async 5](#guide-async-5-several-things-at-the-same-time)).

#### Connect and handshake

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, ConnectAsync
using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));

var ws = new ClientWebSocket();
await ws.ConnectAsync(new Uri(url), timeout.Token);
```

`ConnectAsync` is an ordinary `async` method. It runs on your thread, and continues on pool
threads after each `await`. One token limits the whole handshake to 10 s. A cancellation here
aborts the socket ([Async 6](#guide-async-6-cancellation-timeouts-and-errors)), but a failed
handshake loses nothing. The method reads the Engine.IO `open` packet, sends `40`, and reads the
`40` reply. During the handshake, only this method reads, so it needs no reader task yet.

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, end of ConnectAsync
_ = Task.Run(sock.ReadLoop);
sock._dispatcher = Task.Run(sock.Dispatch);
return sock;
```

Here the two long tasks start. `ReadLoop` is fire and forget, done safely: it catches all of its
exceptions, and its end reaches the dispatcher through the channel. The class keeps the task of
the dispatcher. It is `Completion`, the task that ends when the session is over.

#### The reader and the pong

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, ReadLoop
var packet = await ReceiveTextAsync(CancellationToken.None);
```

`ReceiveTextAsync` joins the parts of one WebSocket message in a `MemoryStream`, because a
large `entities` can come in parts. Each `await ReceiveAsync` frees the thread until the
socket engine sees data ([Async 2](#guide-async-2-the-runtime)). The token is `None` on
purpose: a canceled receive would abort the connection.

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, ReadLoop
if (packet == "2")
{
    // Engine.IO ping. Send a pong at once. If you don't, the
    // server drops you after pingInterval + pingTimeout.
    await SendRawAsync("3");
}
```

The pong goes out from the reader itself. It waits only for `_sendLock`, that is, for the send
that runs now, if any. No handler is on this path. Thus a slow handler cannot delay a pong.

For an event (`42[...]`), the reader parses the JSON and **clones** the payload.
`JsonDocument` rents its memory from a pool and returns it at `Dispose`. The clone owns its own
memory, so the payload stays valid on other threads after the `using` ends.

#### The early events

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, ReadLoop
lock (_lock)
{
    if (!_listening)
    {
        // Nobody listens yet: keep the event (see Subscribed).
        if (!_early.TryGetValue(name, out var kept)) _early[name] = kept = new();
        kept.Add(data);
        continue;
    }
}
_events.Writer.TryWrite((name, data));
```

The server sends `welcome` at once after the handshake. The reader runs on its own thread, so
`welcome` can arrive before your code calls `WaitForAsync("welcome")`. Until the first `On` or
`WaitForAsync`, the reader keeps each event in `_early`. The check and the store are in one
`lock`, so no event can pass between "nobody listens" and "keep it".

`Subscribed` gives the kept events of a name to its first subscriber. It does not run them
itself. It moves them to the `_replay` list, and wakes the dispatcher:

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, Subscribed
lock (_lock)
{
    _listening = true;
    if (_early.Remove(name, out var kept) is false) return;
    foreach (var data in kept) _replay.Add((name, data));
}
_events.Writer.TryWrite((null, default)); // false after the end: then nothing listens anyway
```

The item `(null, default)` is not an event. It is a wake-up: the dispatcher can be idle in
`await foreach`, and an item in the channel makes it continue. An earlier version called
`Deliver` for the kept events directly, on the thread that called `On` or `WaitForAsync`. Then
two threads ran handlers at the same time: yours with a kept event, and the dispatcher with a
newer one. A newer event could reach a handler before an older, kept one. Now only the
dispatcher calls `Deliver`, so the handlers see one event at a time, in order.

**Only the first subscription of any name ends the keeping.** After it, an event with no
subscriber goes to the channel, and the dispatcher drops it. This is why `Bot.ConnectWithAsync`
calls `WaitForAsync("welcome")` before it creates the `World`.

#### The dispatcher

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, Dispatch
await foreach (var (name, data) in _events.Reader.ReadAllAsync())
{
    DeliverReplay(); // kept events first: they are older than this item
    if (name is not null) Deliver(name, data); // null: only a wake-up
}
```

One task reads the channel, so the events reach `Deliver` one at a time, in arrival order
([Async 5](#guide-async-5-several-things-at-the-same-time)). Before each item, the dispatcher
gives out the kept events in `_replay`, which are older than any item in the channel. Between two events, `await
foreach` waits without a thread. The worker that runs `Deliver` can change from one event to the
next. That does not matter, because the steps of one method never overlap.

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, Deliver
lock (_lock)
{
    // Copies, so that a handler can call On or WaitForAsync. A waiter that a
    // handler adds now does not get this event: only the waiters that
    // existed when the event arrived get it.
    handlers = _handlers.TryGetValue(name, out var list) ? new(list) : new();
    matched = _waiters.Where(w => w.Name == name && SafePred(w, data)).ToList();
    foreach (var w in matched) _waiters.Remove(w);
}
foreach (var handler in handlers)
{
    try { handler(data); }
    catch (Exception e) { Console.Error.WriteLine($"handler for \"{name}\" threw: {e}"); } // one bad handler must not stop the socket
}
// Outside the lock. RunContinuationsAsynchronously (WaitForAsync): the
// code after your await runs on a pool thread, not here.
foreach (var w in matched) w.Result.TrySetResult(data);
```

Read the order. **Inside the lock, `Deliver` only chooses. Outside it, it runs the handlers
first, and completes the waiters after them.** All seven languages of the course use this
order. Thus, when `await reply` returns, the `World` handler of the reply has run.

An earlier version completed the waiters first, inside the lock, and ran the handlers after.
Because of `RunContinuationsAsynchronously`, your code after `await reply` then ran at the same
time as the handlers of that same event. It could read a `World` that the reply had not yet
changed. The course had to work around it: `Bot.EnterGameAsync` still waits for `start` with
its own `On("start", ...)` handler, which comes after the one of `World`.

One race remains, and it is by design. Your code after `await` runs on a worker, while the
dispatcher continues with the next events. Read shared state under its lock, as
[Async 7](#guide-async-7-shared-state) shows. Do not expect it to stay as it was at the reply.

Each handler call has its own `try`/`catch`. One bad handler prints its exception and the
dispatcher continues. This works for an `Action`, but not for an `async` lambda, whose exception
comes later ([Async 6](#guide-async-6-cancellation-timeouts-and-errors)).

#### On, and the waiter

`On` adds the handler to the table under `_lock`, then calls `Subscribed`. `WaitForAsync` is the
`TaskCompletionSource` of [Async 3](#guide-async-3-the-unit-of-async-work) with the timer of
[Async 6](#guide-async-6-cancellation-timeouts-and-errors). Its key property is in its
signature: it is **not** `async`.

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, WaitForAsync
public Task<JsonElement> WaitForAsync(string name, Func<JsonElement, bool>? pred = null, TimeSpan? timeout = null)
```

A plain method runs to its end at the call. The waiter is in `_waiters` before the call returns.
Thus "`WaitForAsync`, then `EmitAsync`, then `await`" cannot miss a fast reply. An `async`
method would also register before its first `await`, but the plain method makes the rule
visible. The same choice makes a closed socket throw at the call, not at the `await`.

The predicate runs in `Deliver`, inside `_lock`, on the dispatcher. Keep it short, and never take
another lock in it ([Async 7](#guide-async-7-shared-state)). `SafePred` treats a predicate that
throws as "no match".

#### emit and the send rule

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, SendRawAsync
await _sendLock.WaitAsync();
try
{
    await _ws.SendAsync(Encoding.UTF8.GetBytes(packet), WebSocketMessageType.Text, true, CancellationToken.None);
}
finally { _sendLock.Release(); }
```

`ClientWebSocket` allows one send and one receive at the same time, not two sends. The reader
sends pongs, and any task of yours can call `EmitAsync`. The semaphore gives them turns. This is
the only place where the course holds a lock across an `await`. That is why it is a `SemaphoreSlim`.

`EmitAsync` returns the task of `SendRawAsync` without `async`. The send has ended when the task
completes. Nothing in the protocol tells you that the server read it.

#### Close and the end

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, CloseCleanlyAsync
try { await SendRawAsync("41"); } catch (WebSocketException) { } // the connection is already gone
await CloseOutputAsync();
await Completion; // the reader sees the close of the server; the dispatcher ends
```

The end goes through the same path for each cause: your `CloseAsync`, a close from the server,
or a network error.

1. `ReceiveTextAsync` returns `null`, or throws. `ReadLoop` leaves its loop with a reason.
2. `ReadLoop` writes the local `disconnect` event, then calls `_events.Writer.Complete()`.
3. The dispatcher gives out the events that remain, `disconnect` last.
4. `await foreach` ends. The dispatcher sets `_closed` and fails each open waiter with
   `WebSocketException("socket closed")`.
5. The `Dispatch` task completes. That is `Completion`, so `CloseAsync` returns.

The clean close can wait forever: the server may never answer, a send may never end, or a
handler may never return. An earlier version awaited `Completion` without a limit, and then
`CloseAsync` never returned. Now `CloseAsync` puts a limit of 5 s on the clean close, with the
`WaitAsync` of [Async 5](#guide-async-5-several-things-at-the-same-time):

```csharp
// fragment of course/csharp/Albot/AlSocket.cs, CloseAsync
var clean = CloseCleanlyAsync();
try
{
    // 5 s: the server answers a close in one round trip. Longer means that
    // the connection is dead (no answer, a send that never ends) or that a
    // handler never returns. Then a clean close is not possible.
    await clean.WaitAsync(CloseTimeout);
    return;
}
catch (TimeoutException) { }
catch (WebSocketException) { } // the connection broke during the close
// Force the end. Abort makes the ReceiveAsync of ReadLoop throw: the
// reader writes "disconnect" and ends, and the dispatcher fails the waiters.
_ws.Abort();
_ = clean.ContinueWith(t => _ = t.Exception); // its later failure is expected: mark it observed
```

After the limit, `_ws.Abort()` closes the connection at once, without a close frame. Steps 1
to 5 above then run, with "transport error" as the reason. `CloseAsync` does not wait for them
again. A test against a server that never answers the close shows the change:

```text
old AlSocket:   CloseAsync still waits after 10 s
fixed AlSocket: CloseAsync returned after 5 s
```

</div>

<div data-lang="rust">

This chapter reads the Rust `AlSocket` (`course/rust/src/alsocket.rs`) in the order of a
session. At each part, it names the idea from the earlier chapters that the code uses. See
[AlSocket](#learn-alsocket) for the complete file.

#### The parts at a glance

```text
  your code (main thread)             AlSocket tasks (worker threads)

  emit("attack") ──Out::Text──┐
                              ├──> mpsc Out ──> writer ──> WebSocket sink ──> server
           reader: "2" → "3" ─┘
                                                server ──> WebSocket stream ──> reader
                                                                                  │
                                                         mpsc (name, data) <──────┘
                                                                │
                                                                v
                                                           dispatcher: deliver()
                                                             1. handlers
  wait_for(...).await  <──── oneshot send ─────────────────  2. waiters
  close().await        <──── watch send(true) ─────────────  at the end
```

All shared state is one `Arc<Mutex<Shared>>`: the handlers, the waiters, the early events and
two flags.

#### 1. Connect and handshake

```rust
        let ten_s = Duration::from_secs(10);
        let (ws, _response) = tokio::time::timeout(ten_s, connect_async(url)).await??;
        let (mut sink, mut stream) = ws.split();
```

- **`timeout` and `??`** ([Async 6](#guide-async-6-cancellation-timeouts-and-errors)). The
  outer `?` is the timeout. The inner `?` is the error of the connection. On timeout,
  `timeout` drops `connect_async` in the middle, and its TCP socket closes.
- **`split()`** from `futures_util` makes two halves: a `Sink` for writes and a `Stream` for
  reads. They share the socket through a small lock inside, so two tasks can own one half each.

The handshake is an `async` block that borrows `sink` and `stream`. Thus the future of
`connect` refers to itself while it waits, and needs `Pin` ([Async 4](#guide-async-4-what-await-does)).
`connect` reads the Engine.IO open packet (`0{...}`), sends `40`, and expects `40` back.
Everything up to here runs in the caller's future, before any task exists.

#### 2. Three tasks

`connect` then makes the channels and spawns three tasks. Each `tokio::spawn` takes an
`async move` block that owns what it needs: the writer owns `sink`, the reader owns `stream`.
That satisfies `Send + 'static` ([Async 5](#guide-async-5-several-things-at-the-same-time)).
The code keeps only the `AbortHandle` of the writer, for a forced close (part 10). The tasks
run detached, and they end when their channels or their stream end.

#### 3. The writer, and the send rule

```rust
        let writer = tokio::spawn(async move {
            while let Some(out) = out_rx.recv().await {
                let result = match out {
                    Out::Text(text) => sink.send(Message::Text(text.into())).await,
```

A WebSocket sink can do one send at a time. Here only one task owns it, so the type system
enforces the rule. There is no lock. Other languages use a semaphore (C#) or a chain of futures
(Java) for the same rule. The writer stops at the first failed send or at `Out::Close`.

#### 4. The reader and the pong

```rust
                if packet == "2" {
                    // Engine.IO ping. Send a pong at once. If you don't, the
                    // server drops you after pingInterval + pingTimeout.
                    let _ = pong.send(Out::Text("3".into()));
```

- **The reader never runs your code.** It parses, answers pings, and passes events on. Thus no
  handler can delay a pong. ([Async 2](#guide-async-2-the-runtime))
- **The pong shares the writer's queue.** It goes behind any `emit` that is already in the
  queue. The queue is short in practice, so this costs little.
- **`pong.send` on an unbounded `mpsc` never waits.** The reader waits at one place only: a
  `select!` of `stream.next()` and a stop signal from `close()` (part 10). The I/O driver wakes
  the reader when bytes arrive.

For an event (`42[...]`), the reader parses the JSON and sends `(name, data)` on the event
channel. That channel has no limit either. The reader never waits for the dispatcher.

#### 5. The early events

```rust
                            let mut s = state.lock().unwrap();
                            if !s.listening {
                                // Nobody listens yet: keep the event (see subscribed).
                                s.early.entry(name).or_default().push(data);
                                continue;
                            }
                            drop(s);
```

The server sends `welcome` right after the handshake, maybe before `connect` returns to you.
Until the first `on` or `wait_for` of any name, the reader keeps each event in `early`. The
first subscriber of a name gets the kept events of that name, through `subscribed`. Note also
the explicit `drop(s)`: it ends the guard before the send, so the lock is short.

`subscribed` does not run the handlers itself. It moves the kept events into a `replay` queue
and wakes the dispatcher:

```rust
        s.replay.extend(kept.into_iter().map(|data| (event.to_string(), data)));
        drop(s);
        // The dispatcher can wait on an empty channel: wake it. If it is busy,
        // Notify keeps the wake for its next wait.
        self.replay.notify_one();
```

An earlier version called `deliver` on the caller's task, inside `on` or `wait_for`. Then a kept `welcome` ran its handlers on the main thread. At the
same time, the dispatcher could run the handlers of a newer event on a worker. That broke the rule "one event at a time, in
arrival order". Now all handlers run on the dispatcher task. The waiter of `wait_for` exists
before `subscribed` runs, so it still gets its kept event.

#### 6. The dispatcher and `deliver`

```rust
            loop {
                let next = tokio::select! {
                    next = event_rx.recv() => next,
                    _ = wake.notified() => {
                        drain_replay(&state);
                        continue;
                    }
                };
                drain_replay(&state); // before this event: it can be newer than them
                let Some((name, data)) = next else { break };
                deliver(&state, &name, &data);
            }
```

One task, one loop, one event at a time, in arrival order. The kept events of `replay` go
before each event that it takes from the channel, because they arrived first. The `Notify`
wakes the loop when the channel is empty but `replay` is not. That gives the server's guarantee
("one ordered stream") to your handlers. `deliver` is a plain `fn`. It has no `.await`, so
nothing can interleave inside it on this task.

```rust
    let handlers = shared.lock().unwrap().handlers.get(name).cloned().unwrap_or_default();
    for handler in handlers {
        // A handler that panics gets a report. The dispatcher continues.
        if catch_unwind(AssertUnwindSafe(|| handler(data))).is_err() {
```

- **A copy of the list, then unlock.** The handlers run without the `Shared` lock. A handler can
  call `on` and add a handler without a deadlock.
- **`Handler` is `Arc<dyn Fn(&Value) + Send + Sync>`.** `Fn`: the dispatcher calls it many
  times. `Send + Sync`: the dispatcher task moves between workers, and the table
  shares the `Arc`. A handler is synchronous. It cannot `.await`. That is on purpose: a handler only
  changes state ([Async 7](#guide-async-7-shared-state)).
- **`catch_unwind`** turns a panic in a handler into a printed line
  ([Async 6](#guide-async-6-cancellation-timeouts-and-errors)).
- **The cooperative budget** applies here. `event_rx.recv()` uses one unit for each event. After
  128 events in one poll, the dispatcher yields its worker, even if more events wait.

#### 7. Handlers first, then waiters

After the handlers, `deliver` locks `Shared` again, removes the waiters whose receiver is gone,
and completes each match:

```rust
        if matched {
            let _ = s.waiters.swap_remove(i).tx.send(data.clone());
```

**The order matters, and it differs between languages.** In Rust, as in JS, Python and Go, the
handlers of an event run before its waiter completes. When your `request` returns, `World`
already applied that event. In C# and Java, `deliver` completes the waiter first, and your code
can continue in parallel with those handlers.

Also note: `tx.send` does not run your code. It stores the value and calls the waker of your
task ([Async 3](#guide-async-3-the-unit-of-async-work)). Your code continues later, on its own
thread. The dispatcher continues with the next event at once.

#### 8. `on` and `wait_for`

`on` adds the handler under the lock, unlocks, and calls `subscribed`. `wait_for` is the
`oneshot` waiter of [Async 3](#guide-async-3-the-unit-of-async-work): a plain `fn` that
registers now and returns a `'static` future. Its timeout lives inside the returned future. Thus
the timer starts at the first poll, not at the call.

`request` passes a timeout of 1 day to `wait_for_timeout` and puts its own 2 s `timeout`
outside. The reason is in the error types. The inner future returns `Err` for both "timed
out" and "socket closed". The outer `timeout` returns `Err(Elapsed)` only for time. Thus
`request` can map time to `Ok(None)` and a closed socket to `Err`.

#### 9. `emit`

```rust
        self.out
            .send(Out::Text(packet))
            .map_err(|_| "socket is closed".into())
```

`emit` is an `async fn`, but its body has no `.await`. It completes at its first poll. It is
`async` so that the signature can stay the same if a later version must wait, for example on a
bounded channel. The real send happens later, on the writer task.

One consequence: `emit` returns `Ok` when the frame is in the queue, not when it is on the
wire. That is the contract of a queued send, and the comment of `emit` states it. An earlier
version also returned `Ok` after the reader saw the end, until the writer failed a send. Now the
reader sets a flag `ended` when it leaves its loop, and `emit` checks it first:

```rust
        if self.ended.load(Ordering::SeqCst) {
            return Err("socket is closed".into());
        }
```

A short gap stays: the connection broke, but the reader has not seen it yet. A frame that you queue then never arrives, and
no error tells you. TCP has the same gap for its own buffer. Thus your code
learns of a broken connection from the `disconnect` event, not from `emit`.

#### 10. Close and the end

```rust
    pub async fn close(&self) -> Result<()> {
        self.start_close();
        let mut done = self.done.clone();
        if tokio::time::timeout(CLOSE_WAIT, done.wait_for(|ended| *ended)).await.is_err() {
            self.force_close();
            // The reader stops at once now, and the dispatcher gives out what
            // is left. 1 s more is enough; a handler that never returns must not
            // keep close() waiting forever.
            let _ = tokio::time::timeout(Duration::from_secs(1), done.wait_for(|ended| *ended)).await;
        }
        Ok(())
    }
```

`start_close` queues the Socket.IO disconnect and a WebSocket Close frame. The writer sends both
and ends. The server answers the Close frame, and the reader ends. The dispatcher delivers the
last events and `disconnect`, then fails each waiter and sets `done`.

If the server does not answer in 5 s (`CLOSE_WAIT`), `force_close` notifies the reader and
aborts the writer. The reader leaves its `select!` with the reason "closed by the client", and
the end runs as usual. `Drop` does the same steps without the wait
([Async 6](#guide-async-6-cancellation-timeouts-and-errors)).

The differences from the other languages:

- **A `request` on a closed socket** returns `Err("socket is closed")` from `emit`. `request`
  drops the `reply` future, and the dispatcher removes its waiter (its receiver is gone).
  Nothing stays behind.
- **A drop of `AlSocket` closes the connection,** because Rust runs `Drop` at a known point.
  The languages with a garbage collector have no such point. There, only `close()` closes.

</div>

<div data-lang="java">

This chapter reads `course/java/src/main/java/albot/AlSocket.java` in the order of a session. Each part names the idea from the earlier chapters that it uses.

#### The fields: two locks, one queue, three futures

```java
private final Object lock = new Object(); // guards the seven fields below
```

`lock` guards `handlers`, `waiters`, `early`, `replay`, `listening`, `ended` and `closed`. A second lock, `sendLock`, guards `lastSend`. The class also has three futures: `handshake`, `done`, and the box of each waiter. The `LinkedBlockingQueue<Event> events` connects the listener and the dispatcher. The ideas: monitors and happens-before ([Async 7](#guide-async-7-shared-state)), futures as boxes ([Async 3](#guide-async-3-the-unit-of-async-work)).

#### Connect and handshake

```java
sock.ws = HttpClient.newHttpClient().newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .buildAsync(URI.create(url), sock)
        .get(10, TimeUnit.SECONDS);
sock.handshake.get(10, TimeUnit.SECONDS); // onPacket completes it
```

`buildAsync` starts the HTTP upgrade and returns a future at once. `main` blocks on it with `get(10 s)`. The Socket.IO handshake then runs on listener threads. `onPacket` sees the Engine.IO open packet `0{...}`, sends `40`, and completes `handshake` when `40` comes back. `main` blocks a second time on that future.

Each `get` here has a timeout, so a dead server cannot hang `connect`. The idea: block on a future with a timeout ([Async 4](#guide-async-4-what-await-does)).

Before the handshake completes, `onPacket` ignores every packet except `0`, `40` and `44`. The real server sends `welcome` only after `40`, so `AlSocket` loses nothing.

#### The reader: `onText` and flow control

`AlSocket` is a `WebSocket.Listener`. The HTTP client calls its methods. The `WebSocket.Listener` documentation guarantees that these calls run one at a time: "the next invocation may start only after the previous one has finished". It does not say which thread calls them. In a check with JDK 21, the first calls came on a common-pool thread, and the rest on `HttpClient-1-Worker-0`.

The WebSocket delivers messages only on demand. It keeps a counter of messages that it may still deliver. `request(n)` adds `n` to it. The counter starts at 0, so with no `request`, no message ever arrives:

```java
@Override
public void onOpen(WebSocket ws) {
    this.ws = ws;
    ws.request(1); // ask for the first message
}
```

`onText` gets a `CharSequence` and a flag `last`. A long message comes in parts, so `AlSocket` appends to `partial` until `last` is true. The sequential guarantee above makes a plain `StringBuilder` safe here. At the end, it asks for one more message and returns `null`:

```java
ws.request(1); // ask for the next message
return null;
```

The return value tells the WebSocket when it may reuse the `CharSequence`. `null` means "now". `AlSocket` copies the text with `toString()` first, so `null` is correct. With `request(1)` in each call, `AlSocket` never has more than one message in its hands. The ideas: callbacks on the threads of a library ([Async 2](#guide-async-2-the-runtime)), backpressure through `request(n)`.

#### The pong

```java
if (packet.equals("2")) {
    // Engine.IO ping. Send a pong at once. If you don't, the server
    // drops you after pingInterval + pingTimeout.
    send("3");
```

The pong goes out from the listener thread, inside `onText`. `send` never blocks (see below), and `onText` never waits for a handler. Thus the time from ping to pong does not depend on your code. This is the reason for the separate dispatcher.

#### The queue and the dispatcher

`onText` parses each `42[...]` packet into a name and a `JsonNode`, and calls `events.add(new Event(name, data))`. The queue has no size limit, so `add` never blocks the listener. If handlers are slow, the queue grows in memory, but pongs still go out. Go uses a buffer of 1,024 events and blocks the reader when it is full. Java chose memory over a blocked reader.

The dispatcher is a virtual thread:

```java
Thread.ofVirtual().name("alsocket-dispatch").start(sock::dispatch);
```

```java
while (true) {
    Event ev = events.take(); // blocks; the virtual thread unmounts here
    deliverReplay();
    if (ev == END) break;
    if (ev != WAKE) deliver(ev);
}
```

`take()` parks the virtual thread while the queue is empty, and the carrier is free. `deliverReplay` and the marker `WAKE` are for the early events (next section). One thread delivers all events, so handlers see the events in arrival order, one at a time. The queue gives the happens-before edge from the listener to the dispatcher. The ideas: virtual threads and unmount ([Async 2](#guide-async-2-the-runtime)), `BlockingQueue` ([Async 7](#guide-async-7-shared-state)).

#### The early events

The server sends `welcome` right after the handshake. Your code can call `waitFor("welcome")` only after `connect` returns. To close this gap, `onPacket` keeps each event in `early` while `listening` is false. The first `on` or `waitFor` of any name sets `listening`. Then `subscribed(name)` gives the kept events of that name to the dispatcher:

```java
synchronized (lock) {
    listening = true;
    List<JsonNode> kept = early.remove(name);
    if (kept == null) return;
    for (JsonNode data : kept) replay.add(new Event(name, data));
}
// The dispatcher can be blocked in take() on an empty queue: wake it.
events.add(WAKE);
```

`subscribed` moves the kept events into `replay`, a list under `lock`. The dispatcher may sleep in `take()` on an empty queue, so `subscribed` also puts the marker `WAKE` in the queue. After each `take()`, the dispatcher first delivers all of `replay`, then the item that it took. The kept events arrived before every event in the queue, so this keeps the arrival order. `waitFor` registers its waiter before it calls `subscribed`, so a kept `welcome` reaches the `welcome` waiter. Kept events of other names stay in `early` until the first subscriber of their name.

An earlier version delivered the kept events inline, on the thread that called `on` or `waitFor`, usually `main`. A handler then ran on `main` while the dispatcher ran other handlers at the same time. That broke the promise of one handler at a time, in arrival order. Now every handler runs on `alsocket-dispatch`. A check against a fake server shows the thread of a handler for a kept event: `main` before the change, `alsocket-dispatch` after it.

But from this moment, `onPacket` keeps no new events. Each new event goes to the queue, and the dispatcher drops an event that has no handler and no waiter yet. This is "the welcome race" of `docs/COURSE.md`. `Bot.connectWith` waits for `welcome` before it makes the `World`, so that the first subscriber is the `welcome` waiter.

#### `on`

```java
synchronized (lock) {
    handlers.computeIfAbsent(event, k -> new ArrayList<>()).add(handler);
}
subscribed(event);
```

A handler is a `Consumer<JsonNode>`. It cannot throw a checked exception and cannot return a future. `AlSocket` has no `off`. `Bot.sendAuth` relies on a property of futures for this: its handlers only complete `started`, and each `complete` after the first does nothing.

#### `deliver`: the handlers first, then the waiters

`deliver` works in three steps. First, under `lock`, it copies the handlers and the waiters of the event name. Second, outside `lock`, it runs each handler, each in a `try`/`catch` for `RuntimeException`. Third, it tests the waiters and completes the ones that match:

```java
List<Waiter> matched = new ArrayList<>();
synchronized (lock) {
    for (Waiter w : candidates) {
        // waiters.remove is false if the waiter already ended (timeout, cancel).
        if (safeTest(w, ev.data()) && waiters.remove(w)) matched.add(w);
    }
}
// Complete them outside the lock. Each one's code after get()/join() runs on
// its own thread, and its next stages on the common pool (see waitFor).
for (Waiter w : matched) w.result().complete(ev.data());
```

Each matching waiter completes, not only the first. Two waits for the same event with matching predicates both get it. A waiter that a handler adds during this event is not in `candidates`, so it waits for the next event.

The order is the same in all seven languages: the handlers first, then the waiters. When `request` returns, the `World` already contains the effect of its `game_response`. The trace in [Async 4](#guide-async-4-what-await-does) shows it: `get()` returned after the handler ended.

An earlier Java version completed the waiter first, inside `lock`, and ran the handlers after it. `complete` submitted the last stage to the common pool, and `main` woke at once. Thus `main` continued while the handlers of the same event still ran. In the old trace, `get()` returned 200 ms before the handler ended. Code after `request` could read a `World` without the effect of the reply. The cure was to change the order, and to call `complete` outside `lock`, as for the close in [Async 6](#guide-async-6-cancellation-timeouts-and-errors).

#### The waiter and `thenApplyAsync`

The comment in `waitFor` gives the reason for the last stage:

```java
// On timeout, remove the waiter. thenApplyAsync: the stages that you add
// to the future run on the common pool, never on the dispatcher thread.
```

Without it, a `thenApply` on the returned future runs on the dispatcher, in the middle of `deliver`. See "Which thread runs a chained stage?" in [Async 4](#guide-async-4-what-await-does). A blocking call there would stop all events. With it, your stages run on the common pool. A thread that waits in `get()` wakes on its own thread in both cases.

There is one more effect. The future that you get is not the box in the list. Thus `waitFor` adds `future.whenComplete((d, e) -> result.cancel(false))` ([Async 3](#guide-async-3-the-unit-of-async-work)). A cancel of your future cancels the box, and the waiter leaves the list at once.

#### `emit` and the send rule

`java.net.http.WebSocket` allows one send at a time. A `sendText` while another is not complete fails with `IllegalStateException`. Several threads send in an AL bot: the listener (pongs), `main` (actions), virtual threads (party members). `AlSocket` puts each send at the end of a chain:

```java
synchronized (sendLock) {
    // Start after the previous send, also if that send failed.
    lastSend = lastSend.handle((r, e) -> null).thenCompose(x -> ws.sendText(packet, true));
    return lastSend;
}
```

- `sendLock` makes "read `lastSend`, build the next link, write `lastSend`" atomic. Without it, two threads could chain after the same send, and two sends would run at once.
- `handle((r, e) -> null)` turns a failed send into a success, so one failure does not stop all later sends.
- `thenCompose` starts the next `sendText` when the previous one completes, on the thread that completes it.

Nobody blocks here. `send` returns the new end of the chain at once. Thus `onText` never blocks on a send of `main`. The pong only waits for its place in the chain of sends.

#### Close and the end

`close()` sends `41` (Socket.IO disconnect), then a WebSocket close frame through the same chain. Then it blocks on `done.get(5, TimeUnit.SECONDS)`. The server answers with its close frame. The HTTP client calls `onClose`, which calls `end(reason)`. Each end of the connection goes through `end`: a server close, a network error (`onError`), or your `close()`:

```java
events.add(new Event("disconnect", new TextNode(reason)));
events.add(END); // the dispatcher stops after the last event
```

The local `disconnect` event and the marker go through the same queue as real events. Thus your handlers see every event that arrived before the end, then `disconnect`, in order. After `END`, the dispatcher sets `closed`, fails the waiters and completes `done`.

`end` acts only one time. A flag `ended` under `lock` makes the second call return. This matters because three paths can call it: `onClose`, `onError` and `close()` itself.

`close()` waits at most 5 s. A server answers a close in much less time. A longer wait means a dead network, or a handler that never returns. Then `close()` calls `ws.abort()`, which closes the transport at once, and `end(...)`. It returns without more waiting.

An earlier version called `done.join()` with no timeout. With the old close bug of [Async 6](#guide-async-6-cancellation-timeouts-and-errors), `done` never completed, and `close()` blocked for ever.

#### Summary of the session

| Part | Thread | Idea |
|---|---|---|
| `connect` | `main`, blocked on two futures with timeouts | block with a limit |
| `onOpen`, `onText`, pong | a listener thread of the HTTP client | sequential callbacks, `request(1)` |
| queue | listener to dispatcher | `BlockingQueue`, happens-before |
| `dispatch`, `deliver`, handlers | virtual thread `alsocket-dispatch` | unmount in `take()`, one ordered consumer |
| kept early events | moved to `replay` by the caller of `on`/`waitFor`, delivered by the dispatcher | `WAKE` marker, arrival order |
| waiter | completed by the dispatcher, timed out by `CompletableFutureDelayScheduler`, last stage on the common pool | a hand-made future |
| `emit` | any thread; the send runs on the thread that completes the previous one | one send at a time, by chaining |
| `end`, `done` | listener thread, then dispatcher | the end is an event in the same queue |

</div>

## Async 9: Seeing it run

A mental model is good only if you can test it. This chapter shows tools that make the async work of your program visible. With them, you
can find a blocked loop, a deadlock, a leak, a race and a slow handler. It ends with the typical mistakes of your language.

<div data-lang="js ts">

#### What you can see, and what you look for

On one thread, most async bugs have one of five shapes. Each has a tool.

| You see | The likely cause | The tool |
|---|---|---|
| Late events, late timers, `disconnect` after a pause | a blocked loop: a long synchronous task | `monitorEventLoopDelay`, `--cpu-prof`, the inspector |
| The program waits forever, or exits early | a promise that nothing settles | exit code 13, `getActiveResourcesInfo`, the inspector |
| The process stops with an error from a promise | an unhandled rejection | the stack trace, async stack traces |
| More and more timers or memory | a leak of waiters or timers | `getActiveResourcesInfo`, heap snapshots |
| A wrong value after an `await` | interleaving (Async 7) | logs with times at each `await` |

#### A blocked loop: measure the delay

`node:perf_hooks` measures how late the loop is. `monitorEventLoopDelay` samples with a timer and
records how late each sample ran. `eventLoopUtilization` tells which part of the time the loop
was busy and not waiting in poll.

```js
// lag.mjs: measure how late the event loop is, from inside the program.
import { monitorEventLoopDelay, performance } from "node:perf_hooks";

const delay = monitorEventLoopDelay({ resolution: 10 }); // samples every 10 ms
delay.enable();
const elu0 = performance.eventLoopUtilization();

// A "handler" that blocks 300 ms, three times.
let runs = 0;
const timer = setInterval(() => {
  const end = performance.now() + 300;
  while (performance.now() < end) {}
  if (++runs === 3) {
    clearInterval(timer);
    delay.disable();
    const elu = performance.eventLoopUtilization(elu0);
    console.log(`max delay of the loop: ${(delay.max / 1e6).toFixed(0)} ms`);
    console.log(`busy part of the time: ${(elu.utilization * 100).toFixed(0)} %`);
  }
}, 100);
```

```text
max delay of the loop: 304 ms
busy part of the time: 90 %
```

The numbers differ a little from run to run. In a bot, log `delay.max` every minute and reset
the histogram (`delay.reset()`). A maximum near 1 s means that a pong was late by 1 s. A
maximum near 12 s means a disconnect.

To find which code blocks, record a CPU profile. `node --cpu-prof farm.js 60` writes a
`.cpuprofile` file when the process exits. Open it in Chrome DevTools (Performance panel). A
long bar of one function is your blocked loop. `World.advance`, `pathfind` and a large
`JSON.parse` are the usual names in a bot.

To find a slow handler without a profiler, time each handler. This is a fragment for your
client:

```js
// A wrapper for a handler: warn when it takes more than limitMs.
function timed(name, handler, limitMs = 20) {
  return (data) => {
    const t = performance.now();
    handler(data);
    const ms = performance.now() - t;
    if (ms > limitMs) console.warn(`handler for "${name}" took ${ms.toFixed(1)} ms`);
  };
}
// sock.on("entities", timed("entities", (d) => world.applyEntities(d)));
```

#### A wait that never ends

JavaScript cannot deadlock in the usual sense: no thread holds a lock. But an `await` can wait
for a promise that nothing will settle. Node.js shows this in two ways.

If nothing keeps the loop alive (no socket, no timer), the process ends. If the main module
still waits at a top-level `await`, Node.js prints a warning and exits with code 13:

```js
// hang.mjs: a promise that nothing can settle. Nothing else keeps Node.js alive.
const reply = new Promise(() => {}); // a waiter with no timer and no socket
console.log("waiting for the reply...");
await reply;
console.log("never printed");
```

```text
waiting for the reply...
Warning: Detected unsettled top-level await at file:///w/hang.mjs:4
await reply;
^
```

The exit code is 13. If an open socket keeps the loop alive, the process waits forever, with
the CPU at 0 %. Ask the process what keeps it alive with `process.getActiveResourcesInfo()`
(since Node.js 17.3):

```js
// resources.mjs: what keeps this process alive?
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
setInterval(() => {}, 1000);                 // a forgotten timer: a leak
const pending = sleep(5000);                 // a long wait
console.log(process.getActiveResourcesInfo());
process.exit(0);
```

```text
[ 'Timeout', 'Timeout' ]
```

In a bot, each pending `waitFor` has one `Timeout`. A count that only goes up is a leak of
waiters. A suspended async function has no entry: it is only a reaction on a promise. To see
which code waits, use the inspector.

#### The inspector

`node --inspect farm.js` starts the V8 inspector on port 9229. Open `chrome://inspect` in Chrome
and select the process. `--inspect-brk` stops before the first line. You can also start the
inspector later: send `SIGUSR1` to the process (`kill -USR1 <pid>`). That is the work of the
SIGUSR1 thread of Async 2.

In the Sources panel, "Pause" stops the main thread where it is. A blocked loop pauses inside
your long function. An idle loop shows no JavaScript at all. Breakpoints after an `await` show
the async call stack: the frames that awaited this one, across tasks. The Memory panel takes
heap snapshots. Compare two snapshots to find objects that only grow, such as waiter objects in
the `#waiters` `Set`.

#### Async stack traces

V8 rebuilds the chain of awaiting async functions when you create an error. This costs nothing
until the error. The frames show as `at async name`:

```js
// stacks.mjs: V8 keeps the chain of awaiting async functions in the stack trace.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function request() {
  await sleep(10);                       // the stack is empty when this continues...
  throw new Error("socket is closed");
}
async function heal() { return await request(); }
async function tick() { await heal(); }

try {
  await tick();
} catch (err) {
  console.log(err.stack);                // ...but the trace still names heal and tick
}
```

```text
Error: socket is closed
    at request (file:///w/stacks.mjs:6:9)
    at async heal (file:///w/stacks.mjs:8:32)
    at async tick (file:///w/stacks.mjs:9:25)
    at async file:///w/stacks.mjs:12:3
```

The chain works through `await` only. A callback of `setTimeout` or of an event listener starts
a new chain. So an error that a timer creates, such as the `timed out waiting for` error of a
waiter, has a short stack. Its message tells you more than its stack does.

For unhandled rejections, `process.on("unhandledRejection", (reason, promise) => ...)` lets you
log the reason before you decide to stop. With `--unhandled-rejections=strict`, the process stops
even if an `unhandledRejection` listener exists. Use it in tests.

#### Races of interleaving

There is no race detector for JavaScript, because there are no data races. An interleaving bug
is a logic bug (Async 7). Log with a time before and after each `await` in the suspect code,
and in each handler that writes the same state. The bug is always a write that came between
your read and your use. The cure is always the same: do the read and the use with no `await`
between them, or read again after the `await`.

#### A checklist: mistakes you can now explain

- **A long synchronous loop.** It holds back the poll phase, so pongs, events and timers wait.
  Split it, or use a worker.
- **`await waitFor(...)` before the send.** The `emit` runs only after the wait ends. Keep the
  promise; `emit`; then `await`.
- **A waiter started after an `await`.** The reply can arrive during that `await`, with no
  waiter there.
- **An async handler.** `AlSocket` does not await it. Its tail runs after newer events. The
  course `AlSocket` logs its rejections. A client without that handler stops on the first one.
- **`setInterval` with an async tick.** Ticks overlap. Use a loop with `await sleep`.
- **A wall clock for durations.** `Date.now()` can jump. Measure time with `performance.now()`.
- **A promise kept across an `await` with no handler.** If it rejects first, the process stops
  (Node.js 15 and later). Attach `.catch` early.
- **A floating promise.** No order, no end, no error. Await it, or mark it with `void` and a
  `.catch`.
- **A value read before an `await` and used after it.** Read the world again.
- **`Promise.race` as cancellation.** It stops the wait, not the work. Clear the timers of the
  losers.
- **A wait with no exit.** It never settles, and its `finally` never runs. Give each wait a
  timeout or a signal.
- **TypeScript types as checks.** `waitFor<T>` is a cast. Node.js removes the types before it runs
  the code.

</div>

<div data-lang="python">

The model of this lecture predicts what you see in a bot that goes wrong. This chapter gives
the tools that show the model in a running program.

#### Debug mode

Turn it on with one of these:

- the environment variable `PYTHONASYNCIODEBUG=1`,
- `python -X dev` (the development mode, which also shows `ResourceWarning`),
- `asyncio.run(main(), debug=True)`.

In debug mode, the loop does more checks and records more data:

- **Slow callbacks.** `_run_once` measures each handle. If one takes 100 ms or more
  (`loop.slow_callback_duration`), it logs a warning. A step of a task is a handle, so a tick
  that blocks shows here.
- **Where a coroutine came from.** A "never awaited" warning then has the traceback of the
  line that made the coroutine.
- **Where a handle or Future came from.** Log lines about them show the line that made them.
- **Thread checks.** `call_soon` and other calls that are not thread-safe raise
  `RuntimeError` when they run on the wrong thread.

```python
# obs_debug.py: what asyncio debug mode reports.
# Run: PYTHONASYNCIODEBUG=1 python obs_debug.py   (or python -X dev obs_debug.py)
import asyncio
import time


def slow_handler(data: object) -> None:
    time.sleep(0.25)  # stands for a slow plain handler: it blocks the loop


async def emit(event: str) -> None:
    await asyncio.sleep(0)


async def main() -> None:
    loop = asyncio.get_running_loop()
    print("debug:", loop.get_debug(), "| slow_callback_duration:", loop.slow_callback_duration)
    loop.call_soon(slow_handler, {"mp": 90})
    await asyncio.sleep(0.3)
    emit("attack")  # the missing await


asyncio.run(main())
```

It prints (the traceback is shorter here; the real one also has the frames of `asyncio`):

```text
debug: True | slow_callback_duration: 0.1
Executing <Handle slow_handler({'mp': 90}) at obs_debug.py:7 created at obs_debug.py:18> took 0.253 seconds
obs_debug.py:20: RuntimeWarning: coroutine 'emit' was never awaited
Coroutine created at (most recent call last)
  File "obs_debug.py", line 23, in <module>
    asyncio.run(main())
  ...
  File "obs_debug.py", line 20, in main
    emit("attack")  # the missing await
```

With `state_threadsafe.py` in debug mode, the wrong `set_result` from the thread raises
`RuntimeError: Non-thread-safe operation invoked on an event loop other than the current one`.
Without debug mode, it only made the loop late.

Debug mode makes the loop slower. Use it in tests and when you look for a problem, not all the
time. The loop logs through the `logging` module, logger `asyncio`. Call
`logging.basicConfig(level=logging.WARNING)` or lower to see it in a format that you choose.

#### Where each task waits

`asyncio.all_tasks()` gives each live task. `task.get_stack()` gives the frame where a waiting
task paused. `task.print_stack()` prints it. A dump of all tasks answers "why does nothing
happen?". It shows each task, and the `await` at which it waits.

A watchdog thread answers the
other question, "what blocks the loop?". It runs outside the loop, so it can see the loop when
the loop cannot run:

```python
# obs_watch.py: two small tools for a running bot.
#   1. dump_tasks(): where each task waits now.
#   2. a watchdog THREAD: if the loop stops for more than 1 s, print what it runs.
import asyncio
import sys
import threading
import time
import traceback


def dump_tasks() -> None:
    for task in asyncio.all_tasks():
        frames = task.get_stack()  # for a waiting task: the frame of its await
        where = (f"{frames[-1].f_code.co_name}:{frames[-1].f_lineno}" if frames else "-")
        print(f"   {task.get_name():8} waits in {where}")


def start_watchdog(loop: asyncio.AbstractEventLoop, limit: float = 1.0) -> None:
    beat = [time.monotonic()]
    main_id = threading.get_ident()  # the loop's thread

    def tick() -> None:  # runs ON the loop: proof that the loop is alive
        beat[0] = time.monotonic()
        loop.call_later(0.1, tick)

    def watch() -> None:  # runs on its own thread: it can see a blocked loop
        while True:
            time.sleep(limit / 2)
            if time.monotonic() - beat[0] > limit:
                frame = sys._current_frames()[main_id]
                line = traceback.format_stack(frame)[-1].strip().splitlines()[0]
                print(f"   WATCHDOG: loop blocked for {time.monotonic() - beat[0]:.1f} s at {line}")
                beat[0] = time.monotonic()  # report each block one time

    loop.call_soon(tick)
    threading.Thread(target=watch, daemon=True, name="watchdog").start()


async def tick_loop() -> None:
    await asyncio.sleep(0.2)
    time.sleep(1.6)  # a blocking call by mistake
    await asyncio.sleep(10)


async def main() -> None:
    start_watchdog(asyncio.get_running_loop())
    asyncio.current_task().set_name("main")
    t = asyncio.create_task(tick_loop(), name="tick")
    await asyncio.sleep(0.1)
    print("tasks now:")
    dump_tasks()
    await asyncio.sleep(2)
    t.cancel()


asyncio.run(main())
```

It prints:

```text
tasks now:
   main     waits in main:51
   tick     waits in tick_loop:40
   WATCHDOG: loop blocked for 1.4 s at File "obs_watch.py", line 41, in tick_loop
```

`main` is the task that runs `dump_tasks`, so its line is the current line. The watchdog
names the exact line of the blocking call. `sys._current_frames()` is a private function of
CPython, but it is stable and documented.

Count the tasks too. A number from `len(asyncio.all_tasks())` that grows during a session
shows a leak of tasks, for example from `async def` handlers that never end.

#### Tools outside the program

- **`faulthandler`.** `python -X faulthandler` prints the stacks of all threads on a crash.
  `faulthandler.dump_traceback_later(30, repeat=True)` prints them every 30 s, which finds a
  bot that hangs. `faulthandler.register(signal.SIGUSR1)` prints them when you send `SIGUSR1`
  to the process (not on Windows).
- **`py-spy dump --pid <pid>`** prints the stack of each thread of a running Python process,
  with no change to the program. On Linux it needs permission to trace the process: as a normal
  user with the default Ubuntu setting (`kernel.yama.ptrace_scope = 1`), it fails with
  "Permission Denied". Run it with `sudo`.

#### Races

Python has no race detector for `asyncio`. The race of [Shared state](#guide-async-7-shared-state)
is a logic race, and you find it by reasoning. For each `await` in a function, ask "what can
a handler change here?". To test that answer, put an `await asyncio.sleep(0)` at the suspicious
point. If the bug then appears, you found the gap.

#### Checklist: the mistakes you can now explain

| Symptom | Cause | Chapter |
|---|---|---|
| The server closes the socket after 12 s of silence; `disconnect` with a close code. | A blocking call (`time.sleep`, `requests`, sync `httpx.Client`, a long search) or a slow `def` handler held the loop thread. No pong went out. | Runtime |
| `RuntimeWarning: coroutine ... was never awaited`; an event is never sent. | A missing `await` before a coroutine, for example `sock.emit(...)`. | Unit |
| A background task ends with no trace. | Nothing held a strong reference to it. | Unit |
| A request always times out, but the reply is in the log. | The code awaited `wait_for` before `emit`, or registered the waiter after the send. | Unit, `await` |
| A value is old right after an `await`. | Other tasks and handlers ran during the `await`. | Shared state |
| The bot spends more call-cost than its budget. | Check, `await`, act. | Shared state |
| An `async def` handler applies an old event after a newer one. | It runs as its own task, later than the reader step. | Several things |
| "Task exception was never retrieved" in the log, and the bot continues. | Nobody awaited a task that raised, for example a `create_task` without `await`. (`AlSocket` prints the errors of `async def` handlers itself.) | Cancellation |
| "coroutine ... was never awaited" after a failed send. | Your own "wait_for, then emit" code: `emit` raised before `await`. Close the coroutine in an `except`, as `Actions.request` does. | Cancellation |
| Ctrl-C or a timeout does not stop a loop. | `except BaseException` or a bare `except` caught `CancelledError`, or the loop has no `await`. | Cancellation |
| A `TaskGroup` error is not caught by `except ConnectionError`. | `TaskGroup` raises an `ExceptionGroup`. Use `except*`. | Several things |
| A thread computes a path, but the loop gets slow. | The thread holds the GIL for 5 ms at a time. Use a process for CPU work. | Shared state |
| A result from a thread arrives late. | The thread called the loop directly, not through `call_soon_threadsafe`. | Shared state |

</div>

<div data-lang="go">

The Go runtime knows the state of each goroutine. This chapter shows how to ask it. Each tool
answers one question: which goroutines exist and where do they wait; which goroutines race;
where does the time go.

#### Which goroutines exist, and where they wait

**A full dump with Ctrl-\\.** Send `SIGQUIT` to a Go program (Ctrl-\\ in a terminal, or
`kill -QUIT <pid>`). The runtime prints the stack of each goroutine, then exits with status 2.
Each goroutine has a header such as `goroutine 34 [IO wait]:` or
`goroutine 1 [select, 2 minutes]:`. The text in brackets is the state from
[Async 3](#guide-async-3-the-unit-of-async-work). A duration appears when the wait is longer
than 1 minute.

Read the dump like this:

| You see | It means |
|---|---|
| `readLoop` in `[IO wait]` | Normal. The reader waits for the server. |
| `readLoop` in `[select]` inside `send` | The events buffer is full. The dispatcher is stuck. A disconnect follows in 12 s. |
| `dispatchLoop` in `[select]` at its own line | Normal. It waits for the next event. |
| `dispatchLoop` in `[select]` inside your handler | A handler waits for a reply. That is a bug ([Async 8](#guide-async-8-alsocket-read-with-these-eyes)). |
| A goroutine in `[sync.Mutex.Lock]` for a long time | Lock order, or a lock held across a wait ([Async 7](#guide-async-7-shared-state)). |
| Many goroutines with the same stack, in `[chan send]` | A leak. |

**A dump without an exit: `net/http/pprof`.** Import it, and start an HTTP server on
loopback. Then `curl 127.0.0.1:6060/debug/pprof/goroutine?debug=2` gives the same dump as
Ctrl-\\, and the program continues. With `debug=1`, it groups goroutines with the same stack
and counts them. That view finds leaks.

This program leaks one goroutine per call. Its timeout leaves a goroutine blocked on an
unbuffered channel:

```go
// leak: a timeout with an unbuffered channel leaks one goroutine each time.
// The goroutine profile groups the leaked goroutines by stack.
package main

import (
	"fmt"
	"net/http"
	_ "net/http/pprof" // adds /debug/pprof/ to http.DefaultServeMux
	"os"
	"runtime"
	"runtime/pprof"
	"time"
)

// lookup asks a slow source and gives up after 10 ms.
func lookup() (string, bool) {
	ch := make(chan string) // BUG: unbuffered. make(chan string, 1) fixes it.
	go func() {
		time.Sleep(50 * time.Millisecond) // the slow source
		ch <- "answer"                    // blocks forever: nobody receives any more
	}()
	select {
	case v := <-ch:
		return v, true
	case <-time.After(10 * time.Millisecond):
		return "", false
	}
}

func main() {
	go http.ListenAndServe("127.0.0.1:6060", nil) // curl 127.0.0.1:6060/debug/pprof/goroutine?debug=1
	for i := 0; i < 100; i++ {
		lookup()
	}
	time.Sleep(100 * time.Millisecond)
	fmt.Println("goroutines:", runtime.NumGoroutine())
	// The same text as the HTTP endpoint, written to stdout.
	pprof.Lookup("goroutine").WriteTo(os.Stdout, 1)
}
```

It prints this first (shortened; the addresses differ):

```text
goroutines: 102
goroutine profile: total 102
100 @ 0x43e24e 0x407e8d 0x407af7 0x686576 0x474921
#	0x686575	main.lookup.func1+0x35	.../leak/main.go:20
```

"100 @" means that 100 goroutines have this stack. Line 20 is the send. This is the same bug
that the capacity of 1 prevents in the `alsocket` waiter. A simple check in a long-running
bot: print `runtime.NumGoroutine()` each minute. A number that only grows is a leak.

`go tool pprof http://127.0.0.1:6060/debug/pprof/goroutine` opens the same data in the
interactive tool. The commands `top` and `traces` work on it.

#### Which goroutines race

Run with `-race` ([Async 7](#guide-async-7-shared-state)). A report gives the two accesses,
their goroutines, and where each goroutine started. Run the bot with `-race` against the test
server after each change to a handler or to the state.

`go vet` finds some concurrency bugs without a run: a `sync.Mutex` copied by value
(`copylocks`), and a `cancel` that some path does not call (`lostcancel`).

#### When nothing moves: deadlocks

If every goroutine waits on a channel or a lock, the runtime stops the program:

```go
// deadlock: every goroutine waits. The runtime sees it and stops.
package main

func main() {
	reply := make(chan string) // nobody will ever send
	<-reply
}
```

It prints this and exits with status 2:

```text
fatal error: all goroutines are asleep - deadlock!

goroutine 1 [chan receive]:
main.main()
```

Do not count on this check in a bot. It fires only when **no** goroutine can wake. A
goroutine in the netpoller (`readLoop`) or in a `time.Sleep` can always wake. Thus a bot with
a deadlock between two of its goroutines continues to run, without a message. Use a dump to
find it.

#### Where the time goes: `go tool trace`

The execution tracer records each scheduler event: each goroutine start, block, wake and
preemption, each system call, each GC phase. Use it when a tick is late but the CPU profile
shows nothing. Start it in your program, or with `go test -trace=trace.out`. Then open the
file with `go tool trace trace.out`, which starts a viewer in your browser.

```go
// tracing: write an execution trace, then open it with
//
//	go run ./tracing && go tool trace trace.out
package main

import (
	"context"
	"os"
	"runtime/trace"
	"sync"
	"time"
)

func main() {
	f, err := os.Create("trace.out")
	if err != nil {
		panic(err)
	}
	defer f.Close()
	if err := trace.Start(f); err != nil {
		panic(err)
	}
	defer trace.Stop()

	// A task groups the work of one tick; a region marks one step in it.
	// Both show by name in the "User-defined tasks/regions" views.
	ctx, task := trace.NewTask(context.Background(), "tick")
	var wg sync.WaitGroup
	for _, step := range []string{"pathfind", "decide"} {
		wg.Add(1)
		go func() { // Go 1.22: each iteration has its own `step`
			defer wg.Done()
			trace.WithRegion(ctx, step, func() { time.Sleep(20 * time.Millisecond) })
		}()
	}
	wg.Wait()
	task.End()
}
```

In the viewer, look for these signs:

- A handler region that is long. The dispatch goroutine is busy, and events wait in the
  buffer.
- A long gap between "unblock" and "start" of a goroutine. All Ps were busy: CPU work
  competes with your bot.
- Many system calls with a handoff. Something blocks in the kernel outside the netpoller.

`net/http/pprof` also serves a trace: `curl -o trace.out
'127.0.0.1:6060/debug/pprof/trace?seconds=5'`.

#### The scheduler itself: `GODEBUG=schedtrace`

`GODEBUG=schedtrace=1000` prints one line about the scheduler each 1,000 ms, on stderr. This
is the output of a program with 8 goroutines that compute on 4 Ps, with `schedtrace=250`:

```text
SCHED 0ms: gomaxprocs=4 idleprocs=2 threads=5 spinningthreads=1 needspinning=0 idlethreads=2 runqueue=0 [0 0 0 0]
SCHED 256ms: gomaxprocs=4 idleprocs=0 threads=5 spinningthreads=0 needspinning=1 idlethreads=0 runqueue=2 [1 1 0 0]
SCHED 511ms: gomaxprocs=4 idleprocs=0 threads=5 spinningthreads=0 needspinning=1 idlethreads=0 runqueue=2 [0 1 0 1]
```

`runqueue` is the global run queue. The list in brackets has the local run queue of each P.
`idleprocs=0` with full queues means that the CPUs are the limit. A healthy AL bot shows
`idleprocs` near `gomaxprocs` and queues at 0: it waits almost all of the time. Add
`scheddetail=1` for one line per P, M and G.

#### A checklist of Go mistakes you can now explain

- **A handler that waits for a reply.** It waits until its deadline, because the reply is
  behind it on the same goroutine.
- **A slow handler.** The events buffer fills, `readLoop` blocks on its send, no pong goes
  out, and the server closes the socket after 12 s.
- **`WaitFor` before `Emit`.** `WaitFor` blocks before the send. Use `Expect`.
- **A wait without a deadline.** It ends only when the socket closes.
- **A field that two goroutines use without the lock.** A data race. With a map, it can be a
  `fatal error` that `recover` cannot stop.
- **A `World` method called from a handler.** The handler holds the lock, and a Go mutex is
  not reentrant. The goroutine waits for itself.
- **A lock held across a wait or a sleep.** Each handler that needs the lock waits too.
- **A goroutine with no owner.** Its panic ends the program, and its error goes nowhere.
- **An unbuffered result channel with a timeout.** The sender blocks forever. It is a leak.
- **A `ctx` that you expect to stop `time.Sleep`.** Only code that reads the `ctx` stops.
- **A read deadline on the WebSocket.** In `coder/websocket`, it closes the connection.

</div>

<div data-lang="csharp">

A model is only good if you can test it on a running program. .NET has good tools for this. They
show two different things. The difference is the model of this lecture: **threads** have
stacks, but **an async method that waits has no stack**. It is an object on the heap (the state
machine of [Async 4](#guide-async-4-what-await-does)), linked to the task that it waits for. A
tool for threads cannot see it, and a tool for tasks can.

#### The test subject: a pool that starves

This program has the most common .NET defect: sync over async. Each "handler" blocks a pool
thread with `.Wait()` on an `async` call. The tick measures how late it is.

```csharp
// observe: a sync-over-async bug to look at with dotnet-counters and dotnet-stack.
// 32 "handlers" each block a pool thread with .Wait() on an async call.
using System.Diagnostics;

Console.WriteLine($"pid {Environment.ProcessId}");
for (var i = 0; i < 32; i++) _ = Task.Run(Handler);

var clock = Stopwatch.StartNew();
for (var tick = 0; tick < 60; tick++)
{
    var before = clock.ElapsedMilliseconds;
    await Task.Delay(100);
    var late = clock.ElapsedMilliseconds - before - 100;
    if (tick % 10 == 0)
        Console.WriteLine($"tick {tick,2}: late by {late,4} ms, {ThreadPool.ThreadCount,2} pool threads, {ThreadPool.PendingWorkItemCount,3} items wait");
}

static void Handler()
{
    while (true) WaitForReplyAsync().Wait(); // the bug: a blocked pool thread
}

static async Task WaitForReplyAsync() => await Task.Delay(1000);
```

Output with `--cpus 2` (shortened; the numbers differ from run to run):

```text
pid 139
tick  0: late by    8 ms,  7 pool threads,  26 items wait
tick 10: late by  101 ms, 20 pool threads,  23 items wait
tick 20: late by    4 ms, 34 pool threads,   0 items wait
```

For about 2 s, the tick is late, because its continuation waits in the queue behind blocked
workers. Then the pool has grown to 34 threads, and the tick is on time again. In a bot, the
pong and the dispatcher wait in the same queue.

#### dotnet-counters: the numbers of the runtime

Install the diagnostic tools once (`dotnet tool install -g dotnet-counters`, and the same for
`dotnet-stack` and `dotnet-dump`). `dotnet-counters ps` lists the .NET processes.
`dotnet-counters monitor -p <pid>` shows the counters of `System.Runtime` live.
`collect` writes them to a file. This is the starving program, one line each second:

```text
$ dotnet-counters collect -p <pid> --counters System.Runtime --format csv --refresh-interval 1
ThreadPool Thread Count                              19   23   27   31
ThreadPool Queue Length                              23   24   25   25
ThreadPool Completed Work Item Count (Count / 1 sec) 10    8    6    7
Monitor Lock Contention Count (Count / 1 sec)         2    1    1    1
```

(The CSV file has one row for each counter and second. Here they are in columns.) Read the
pattern: the thread count grows, the queue does not get shorter, and few items complete. That is
starvation. These counters answer most questions:

| Counter | It shows |
|---|---|
| `ThreadPool Thread Count` | Growth without end: something blocks workers. |
| `ThreadPool Queue Length` | Above 0 for long: work waits for a worker. Your continuations are late. |
| `ThreadPool Completed Work Item Count` | The real work rate. Low with a long queue: starvation. |
| `Monitor Lock Contention Count` | How often a `lock` had to wait. High: a lock is held too long. |
| `Number of Active Timers` | Each `Task.Delay` and each `WaitForAsync` timer. Growth without end: a leak. |
| `Exception Count` | Exceptions each second, also the ones that code catches. A storm of timeouts shows here. |

#### dotnet-stack: what each thread does now

`dotnet-stack report -p <pid>` prints the managed stack of each thread. On the starving program,
most threads look like this:

```text
Thread (0xE9):
  [Native Frames]
  System.Private.CoreLib!System.Threading.ManualResetEventSlim.Wait(int32,value class System.Threading.CancellationToken)
  System.Private.CoreLib!System.Threading.Tasks.Task.SpinThenBlockingWait(int32,value class System.Threading.CancellationToken)
  System.Private.CoreLib!System.Threading.Tasks.Task.InternalWaitCore(int32,value class System.Threading.CancellationToken)
  System.Private.CoreLib!System.Threading.Tasks.Task.Wait(int32,value class System.Threading.CancellationToken)
  System.Private.CoreLib!System.Threading.Tasks.Task.Wait()
  observe!Program.<<Main>$>g__Handler|0_0()
  System.Private.CoreLib!System.Threading.ExecutionContext.RunFromThreadPoolDispatchLoop(...)
  System.Private.CoreLib!System.Threading.Tasks.Task.ExecuteWithThreadLocal(...)
  System.Private.CoreLib!System.Threading.ThreadPoolWorkQueue.Dispatch()
  System.Private.CoreLib!System.Threading.PortableThreadPool+WorkerThread.WorkerThreadStart()
```

Read it from the bottom. A pool worker (`WorkerThreadStart`) took an item (`Dispatch`). The item
is `Handler`, and `Handler` blocks in `Task.Wait`. Count the threads with this stack, and you
have the count of lost workers. The main thread waits in
`TaskAwaiter.HandleNonSuccessAndDebuggerNotification`, called from `Program.<Main>`. The compiler
made a `Main` that blocks the main thread until the task of your `async Main` ends.

Note what is not in the report: the tick loop, and the 32 calls of `WaitForReplyAsync`. They
wait, so no thread runs them.

#### dotnet-dump: the tasks that wait

`dotnet-dump collect -p <pid>` writes a dump. `dotnet-dump analyze <file>` opens it with the
SOS commands. `dumpasync` lists the async state machines on the heap, with the task that each
one waits for:

```text
> dumpasync
STACK 1
00007a68c680e2d8 00007aa8d96a34a8 ( ) System.Threading.Tasks.Task+DelayPromise
  00007a68c680e380 00007aa8d96a94a0 (0) Program+<<<Main>$>g__WaitForReplyAsync|0_1>d
    00007a68c680e3d0 00007aa8d96aa408 () System.Threading.Tasks.Task+SetOnInvokeMres
```

Each "stack" is a chain of continuations: a `Task.Delay` promise, then the machine of
`WaitForReplyAsync` in state 0, then a `SetOnInvokeMres`. That last object is the continuation
of a thread that blocks in `.Wait()`. So the dump shows the defect from the task side.
`threadpool` shows the pool:

```text
> threadpool
Using the Portable thread pool.

CPU utilization:  0%
Workers Total:    16
Workers Running:  16
Workers Idle:     0
Worker Min Limit: 2
```

16 workers run, 0 are idle, and the CPU is at 0 %. Every worker waits, and none works.

#### A deadlock

Two threads that take two locks in opposite order wait for each other forever. This program
plays the tick (`Gate`, then the socket) and a bad predicate (the socket, then `Gate`):

```csharp
// deadlock: two threads take two locks in opposite order, and wait forever.
// Look at it with: dotnet-stack report -p <pid>, and dotnet-dump (syncblk).
var gate = new object();       // plays World.Gate
var sockLock = new object();   // plays the lock of AlSocket
Console.WriteLine($"pid {Environment.ProcessId}");

var tick = new Thread(() =>
{
    lock (gate) { Thread.Sleep(100); lock (sockLock) { } }   // Gate, then socket
}) { Name = "tick" };
var dispatcher = new Thread(() =>
{
    lock (sockLock) { Thread.Sleep(100); lock (gate) { } }   // socket, then Gate: wrong order
}) { Name = "dispatcher" };
tick.Start();
dispatcher.Start();
Console.WriteLine(tick.Join(3000) ? "no deadlock" : "deadlock: both threads still wait after 3 s");
Thread.Sleep(int.Parse(args.Length > 0 ? args[0] : "0"));  // time to attach the tools
Environment.Exit(0);
```

Output, then the tools (run it with the argument `60000` to keep it alive):

```text
pid 73
deadlock: both threads still wait after 3 s

$ dotnet-stack report -p 73
Thread (0x50):
  [Native Frames]
  deadlock!Program+<>c__DisplayClass0_0.<<Main>$>b__0()
...
$ dotnet-dump analyze core -c syncblk
Index         SyncBlock MonitorHeld Recursion Owning Thread Info          SyncBlock Owner
    1 00007BD770007808            3         1 00005791A79B9C00 52   9   00007bd812808fe8 System.Object
    2 00007BD770007860            3         1 00005791A79B89E0 51   8   00007bd812808fd0 System.Object
```

`dotnet-stack` shows each thread stopped in native code (the wait of `Monitor.Enter`) inside
its lambda. `syncblk` shows the two locks, each owned by one of the two threads (managed ids 9
and 8). `MonitorHeld` 3 means one owner (1) plus one thread that waits (2).

#### Visual Studio and a race

In Visual Studio, pause the program (Debug > Break All), then open Debug > Windows > Parallel
Stacks. Its **Threads** view merges the threads with the same stack into one box, as
`dotnet-stack` shows them. Its **Tasks** view shows the async chains, as `dumpasync` shows them,
with the source line of each `await`. The **Tasks** window lists each task and its state. JetBrains
Rider has a similar parallel stacks view.

.NET has no race detector like `go -race`. Use these methods:

- **Assert the lock.** In a method that needs `Gate`, add
  `Debug.Assert(Monitor.IsEntered(world.Gate), "lock world.Gate first");`. A Debug build fails
  at the first caller that forgot it.
- **Test in Release, under load.** The hoisted read of [Async 7](#guide-async-7-shared-state) does
  not occur in a Debug build. Run the bot near many monsters, so that the handlers and the tick
  often meet.
- **Look for the signs of a race:** an `InvalidOperationException` "Collection was modified", an
  `IndexOutOfRangeException` inside `Dictionary`, or a value that is wrong only sometimes.

For a slow handler, measure it. Wrap a handler when you register it:

```csharp
// Wraps a handler: logs each call that takes more than 20 ms. The
// dispatcher runs handlers one at a time, so a slow one delays all events.
public static Action<System.Text.Json.JsonElement> Timed(string name, Action<System.Text.Json.JsonElement> handler) => data =>
{
    var start = System.Diagnostics.Stopwatch.GetTimestamp();
    handler(data);
    var ms = System.Diagnostics.Stopwatch.GetElapsedTime(start).TotalMilliseconds;
    if (ms > 20) Console.Error.WriteLine($"slow handler for \"{name}\": {ms:F0} ms");
};
```

Use it as `sock.On("entities", Timed("entities", OnEntities))`.

#### The mistakes you can now explain

| Mistake | What occurs, and why |
|---|---|
| `.Result`, `.Wait()` or `Thread.Sleep` in async code | A blocked worker. The pool grows slowly, and continuations, pongs and handlers wait in the queue ([Async 2](#guide-async-2-the-runtime)). |
| `await sock.WaitForAsync(...)` before `EmitAsync` | The `await` waits for the reply before the send. Nothing is sent, and the wait ends at its timeout. Keep the task, send, then await ([Async 3](#guide-async-3-the-unit-of-async-work)). |
| A `TaskCompletionSource` without `RunContinuationsAsynchronously` | Your code after `await` runs on the thread that completes it, inside its locks ([Async 3](#guide-async-3-the-unit-of-async-work)). |
| An `async` lambda as a handler | `async void`. Its exception ends the process ([Async 6](#guide-async-6-cancellation-timeouts-and-errors)). |
| `_ = SomethingAsync()` with no plan | A lost exception, and no end to wait for ([Async 5](#guide-async-5-several-things-at-the-same-time)). |
| `await` on each request in turn | The time is the sum, not the maximum. Start them, then `Task.WhenAll` ([Async 5](#guide-async-5-several-things-at-the-same-time)). |
| A token on `ReceiveAsync` of the read loop | A cancel aborts the WebSocket ([Async 6](#guide-async-6-cancellation-timeouts-and-errors)). |
| `catch (Exception)` around a loop that you cancel | It also catches `OperationCanceledException`, and the loop continues. Catch it first ([Async 6](#guide-async-6-cancellation-timeouts-and-errors)). |
| A field that a handler writes and the tick reads, without a lock | A data race. Lost updates, a broken `Dictionary`, or a value that never changes ([Async 7](#guide-async-7-shared-state)). |
| A lock held across a wait | CS1996 for `lock`. With a `SemaphoreSlim`, every handler that needs it waits ([Async 7](#guide-async-7-shared-state)). |
| State read after `await reply` without the lock | The handlers of the reply ran, but the dispatcher continues with later events at the same time ([Async 8](#guide-async-8-alsocket-read-with-these-eyes)). |
| `System.Threading.Timer` with an `async` callback for the tick | The timer does not wait for the task, so ticks overlap ([The async model of your language](#guide-the-async-model-of-your-language)). |

</div>

<div data-lang="rust">

The model of the earlier chapters tells you what can go wrong. This chapter shows how to see it
in a running Rust bot: a blocked worker, a deadlock, a task that never ends, a slow handler. The
tools are `tracing` for logs with structure, `tokio-console` for a live view of tasks, runtime
metrics, and the usual native debuggers.

#### `tracing` and `RUST_LOG`

`tracing` is the logging crate of the Tokio project. It has two ideas that a plain `println!`
lacks:

- **An event** is one log line with fields: `info!(workers = 4, "runtime")`.
- **A span** is a period of time with a name and fields, for example one `request`. Events
  inside a span carry its name and fields. The span of `#[instrument]` enters at each poll of
  its future and exits at each `Pending`. Thus it stays correct across `.await` points, also
  when the task moves to another worker.

`#[instrument]` puts a span around each call of an `async fn`. `tracing-subscriber` prints the
events. Its `EnvFilter` reads the filter from the variable `RUST_LOG`:

```rust
// tracing: spans and events, filtered by RUST_LOG.
// Run: RUST_LOG=observe=debug cargo run --bin observe
use std::time::Duration;

use tracing::{debug, info, instrument, warn};

#[instrument(skip(payload))] // a span named "request" with the field `event`
async fn request(event: &str, payload: u32) -> Option<u32> {
    debug!("register the waiter, then emit");
    let reply = tokio::time::timeout(Duration::from_millis(50), async {
        tokio::time::sleep(Duration::from_millis(if event == "attack" { 10 } else { 100 })).await;
        payload
    })
    .await;
    if reply.is_err() {
        warn!("no reply in 50 ms");
    }
    reply.ok()
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .with_target(false)
        .without_time() // stable output for this page
        .with_ansi(false)
        .init();
    info!("tick starts");
    request("attack", 1).await;
    request("heal", 2).await;
    let m = tokio::runtime::Handle::current().metrics();
    info!(workers = m.num_workers(), alive_tasks = m.num_alive_tasks(), "runtime");
}
```

The crates for it are `tracing = "0.1"` and `tracing-subscriber = "0.3"` with the feature
`env-filter`. With `RUST_LOG=observe=debug`, it prints:

```text
 INFO tick starts
DEBUG request{event="attack"}: register the waiter, then emit
DEBUG request{event="heal"}: register the waiter, then emit
 WARN request{event="heal"}: no reply in 50 ms
 INFO runtime workers=4 alive_tasks=0
```

Without `RUST_LOG`, the filter shows only errors, and this program prints nothing. A filter is
a list of `target=level` pairs: `RUST_LOG=info,albot=debug,tungstenite=warn`. The target is
the module path. Tokio itself emits `tracing` events only when you build it with the feature
`tracing` and with `--cfg tokio_unstable`.

The course prints with `println!` and has no `tracing`. In your own client, put `#[instrument]`
on `request` and on the tick, and a `debug!` in each handler. Then one log shows, for each
reply, which request waited for it and how long.

#### `tokio-console`: a live view of each task

`tokio-console` is a terminal program. It connects to your bot and shows a row for each task. A row has the
name of the task and the place of its spawn. It also has the number of polls, the busy time and
the idle time. It also warns about some patterns, for example a task that lost its waker, or a task
that wakes itself too often.

It needs three changes to your bot, because the data comes from Tokio's unstable
instrumentation:

1. Add `console-subscriber = "0.4"`, and the Tokio feature `tracing`.
2. Build with `RUSTFLAGS="--cfg tokio_unstable"`.
3. Call `console_subscriber::init()` at the start of `main`.

```rust
// tokio-console: build with RUSTFLAGS="--cfg tokio_unstable", then run `tokio-console`.
use std::time::Duration;

#[tokio::main]
async fn main() {
    console_subscriber::init(); // serves the data on 127.0.0.1:6669
    let reader = tokio::task::Builder::new().name("reader").spawn(async {
        loop {
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    });
    let _ = reader;
    tokio::time::sleep(Duration::from_millis(300)).await;
    println!("OK");
}
```

`tokio::task::Builder` (also unstable) gives a task a name, so that the console shows "reader"
and not only a file and line. Install the console with `cargo install --locked tokio-console`,
and run `tokio-console` while the bot runs.

What to look for in an AL bot:

- **The dispatcher has a large "busy" time per poll.** A handler is slow.
- **A task count that grows each reconnect.** Some tasks of the old session do not end. For
  example, a task of yours that holds a clone of an `Arc<AlSocket>`: the socket then never
  drops.
- **A task that is idle and never woken.** A future that returned `Pending` without a stored
  waker, or a waiter whose event never comes.

#### Runtime metrics

`Handle::current().metrics()` has two stable values in Tokio 1.40: `num_workers()` and
`num_alive_tasks()`. Print them each minute in a long run. A value of `num_alive_tasks()` that
grows without a limit is a leak of tasks. The other metrics, such as the depth of the inject
queue or the busy time of each worker, need `tokio_unstable` in 1.40. Later versions made some
of them stable.

#### See a blocked worker or a deadlock

A deadlock in Rust async has two forms:

- **A thread deadlock.** Two `std::sync::Mutex` locks taken in opposite orders. The threads stop
  in a `futex` wait. Attach a native debugger and print all stacks:
  `gdb -p <pid> -batch -ex "thread apply all bt"` (or `rust-gdb`, `lldb`). Look for two
  `tokio-runtime-worker` threads, or `main`, inside `Mutex::lock`.
- **A logical deadlock.** No thread blocks, but a future waits for something that will
  never occur. For example, a handler waits on a channel that only the tick fills. The stacks
  show only parked workers. `tokio-console` shows the task as idle. A `tracing` span that opened
  and never closed shows where it waits.

A blocked worker (a long synchronous call in a task) has a clear sign in the stacks. The
worker thread is inside your code, not in `park`. In `tokio-console`, it shows as one poll that took
seconds.

#### Find a slow handler without tools

Time the handler and log when it is slow:

```rust
    // fragment: inside a handler
    let t = std::time::Instant::now();
    /* the work of the handler */
    if t.elapsed() > std::time::Duration::from_millis(20) {
        tracing::warn!(ms = t.elapsed().as_millis() as u64, "slow handler");
    }
```

Every handler shares one dispatcher. 20 ms in one handler is 20 ms of delay for each event
after it.

#### Races

Safe Rust has no data races, so there is no `-race` flag to run. The races that remain are
logical: an order of events that you did not expect. Examples are a reply that comes after its
timeout, or a tick that reads `World` between two related events. `tracing` with spans is the
tool for these: log the event names in the dispatcher and the decisions in the tick, then read
the order. If you write `unsafe` code, run the tests under Miri (`cargo +nightly miri test`),
which finds undefined behavior. Miri does not support most of Tokio's I/O, so test the pure
logic.

#### The checklist: mistakes you can now explain

- **A future that you never await does nothing.** `act.attack(id);` without `.await` sends
  nothing. The compiler warns "unused implementer of `Future` that must be used".
- **An `async fn` waiter registers too late.** The body runs at the first poll, after your
  `emit`. Register in a plain `fn` and return the future, as `wait_for` does.
- **`std::thread::sleep`, a blocking HTTP call, or a long search in a task** blocks a worker
  and every task in its queue. Use `tokio::time::sleep`, async `reqwest`, or `spawn_blocking`.
- **A `MutexGuard` across an `.await`** fails to compile in a spawned task. On the main future
  it compiles, and it can deadlock with the dispatcher.
- **A wait inside a handler** cannot complete, because the reply comes through the same
  dispatcher.
- **A dropped `JoinHandle` does not stop the task.** A dropped `AlSocket` closes its connection,
  but only when the last `Arc` to it drops, and without a wait. Prefer `close().await`.
- **`select!` drops the losing branches.** In a loop, only cancel-safe futures belong there.
- **A panic in a spawned task ends only that task.** Await its `JoinHandle` to see it.
- **A `timeout` stops your wait, not the server.** The action can still occur.
- **A poisoned mutex** is a sign that a handler panicked. The course reads it anyway; your code
  must decide too.

</div>

<div data-lang="java">

A Java bot that has a bug in its concurrency usually does not crash. It stops: a tick that never returns, a handler that never runs, a `close()` that never ends. The tools of this chapter answer one question: **where is each thread now, and what does it wait for?**

#### Make the threads readable first

A thread dump is only useful if you can read the names. Name each thread that you start: `Thread.ofVirtual().name("fighter-Ranger1").start(...)`. `AlSocket` names its dispatcher `alsocket-dispatch`. The anonymous thread in the [Async 5](#guide-async-5-several-things-at-the-same-time) demo printed `Exception in thread ""`. A name would tell you which task failed.

#### A program that is stuck

This program makes the two most common hangs of an AL bot. A dispatcher waits for events, and `main` waits for a reply that never comes.

```java
// Stuck.java: a "dispatcher" virtual thread waits on an empty queue, and main waits on a
// future that nobody completes. Run it, then take thread dumps with jstack and jcmd.
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.LinkedBlockingQueue;

public class Stuck {
    public static void main(String[] args) throws Exception {
        var events = new LinkedBlockingQueue<String>();
        Thread.ofVirtual().name("alsocket-dispatch").start(() -> {
            try { events.take(); } catch (InterruptedException e) { /* end */ }
        });
        new CompletableFuture<String>().get(); // waits for ever: a lost reply
    }
}
```

Find the process id with `jcmd` (no arguments) or `jps`. The commands below use `$pid`.

#### `jstack`: platform threads only

`jstack $pid` (the same as `jcmd $pid Thread.print`) prints each platform thread with its state and stack:

```text
"main" #1 [33] prio=5 os_prio=0 cpu=25.82ms elapsed=2.18s tid=0x000070972402ab90 nid=33 waiting on condition  [0x000070972aa5b000]
   java.lang.Thread.State: WAITING (parking)
	at jdk.internal.misc.Unsafe.park(java.base@21.0.12.1/Native Method)
	- parking to wait for  <0x000000069f84a7d0> (a java.util.concurrent.CompletableFuture$Signaller)
	at java.util.concurrent.locks.LockSupport.park(java.base@21.0.12.1/LockSupport.java:221)
	at java.util.concurrent.CompletableFuture$Signaller.block(java.base@21.0.12.1/CompletableFuture.java:1864)
	at java.util.concurrent.ForkJoinPool.unmanagedBlock(java.base@21.0.12.1/ForkJoinPool.java:3780)
```

Read it from the top: `main` is `WAITING (parking)` on a `CompletableFuture$Signaller`. That is a `get()` on a future, as in [Async 4](#guide-async-4-what-await-does). Further down, the stack shows your line, `Stuck.main(Stuck.java:12)`.

`jstack` also finds deadlocks between platform threads on monitors and on `java.util.concurrent` locks. It prints "Found one Java-level deadlock" with the threads and the locks of the cycle.

In Java 21, `jstack` does **not** show virtual threads. In the dump of `Stuck`, the name `alsocket-dispatch` occurs 0 times. A mounted virtual thread shows only as the frames of its carrier.

#### `jcmd Thread.dump_to_file`: virtual threads too

Java 21 added a new dump for virtual threads:

```text
jcmd $pid Thread.dump_to_file -format=json /tmp/threads.json
```

Without `-format=json`, the same command writes plain text. The JSON groups the threads by **container**: `<root>` for threads that you start directly, and one container for each executor or `ForkJoinPool`. The dispatcher is there, with the frames of its unmount:

```text
{
  "tid": "19",
  "name": "alsocket-dispatch",
  "stack": [
     "java.base\/java.lang.VirtualThread.park(VirtualThread.java:596)",
     "java.base\/java.lang.System$2.parkVirtualThread(System.java:2644)",
     "java.base\/jdk.internal.misc.VirtualThreads.park(VirtualThreads.java:54)",
     "java.base\/java.util.concurrent.locks.LockSupport.park(LockSupport.java:369)",
     "java.base\/java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionNode.block(AbstractQueuedSynchronizer.java:519)",
     "java.base\/java.util.concurrent.ForkJoinPool.unmanagedBlock(ForkJoinPool.java:3780)",
     "java.base\/java.util.concurrent.ForkJoinPool.managedBlock(ForkJoinPool.java:3725)",
     "java.base\/java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject.await(AbstractQueuedSynchronizer.java:1746)",
     "java.base\/java.util.concurrent.LinkedBlockingQueue.take(LinkedBlockingQueue.java:435)",
     "Stuck.lambda$main$0(Stuck.java:10)",
     "java.base\/java.lang.VirtualThread.run(VirtualThread.java:329)"
  ]
},
```

The JSON has no thread states and no lock owners. Read the top frames: `VirtualThread.park` means "unmounted, it waits". `LinkedBlockingQueue.take` means "a dispatcher with an empty queue", which is normal. A dispatcher inside one of your handlers, in `CompletableFuture.get`, is the bug "a handler waits for a reply".

Use `python3 -m json.tool` or a short Python script to filter a large dump. The JSON is easy to search for a thread name.

#### JFR: pinning and more, with no code change

Java Flight Recorder (JFR) records events inside the JVM at a low cost. Start it at launch:

```text
java -XX:StartFlightRecording:filename=rec.jfr -jar bot.jar
jfr print --events jdk.VirtualThreadPinned rec.jfr
```

Or start it on a running bot with `jcmd $pid JFR.start` and `jcmd $pid JFR.dump filename=rec.jfr`. For a virtual thread, the useful event is `jdk.VirtualThreadPinned`. It is on by default, and records each pinned park longer than 20 ms. The `Pinning` program of [Async 4](#guide-async-4-what-await-does) gives:

```text
jdk.VirtualThreadPinned {
  startTime = 23:24:46.190 (2026-10-05)
  duration = 1.00 s
  eventThread = "" (javaThreadId = 31, virtual)
  stackTrace = [
    java.lang.VirtualThread.parkOnCarrierThread(boolean, long) line: 689
    java.lang.VirtualThread.parkNanos(long) line: 648
    java.lang.System$2.parkVirtualThread(long) line: 2653
    jdk.internal.misc.VirtualThreads.park(long) line: 67
    java.util.concurrent.locks.LockSupport.parkNanos(Object, long) line: 267
    ...
  ]
}
```

`jfr print --stack-depth 64` shows the frames below the `...`, with your `synchronized` block. `jdk.VirtualThreadStart` and `jdk.VirtualThreadEnd` exist too, but are off by default. Turn them on to count virtual threads that never end (a leak). JDK Mission Control opens the same file in a GUI, with lock contention (`jdk.JavaMonitorEnter`) and a view of each thread over time.

In Java 21 only, `-Djdk.tracePinnedThreads=full` (or `short`) prints the stack each time a virtual thread parks while pinned. Java 24 removed this property, together with most of the pinning (JEP 491). It also changes the timing: with it, the `Pinning` program did not time out in one check.

#### Make the problem easy to see

Concurrency bugs depend on timing. Change the timing on purpose:

- **One carrier:** `-Djdk.virtualThreadScheduler.parallelism=1`. Pinning then stops everything at once, as in the `Pinning` demo.
- **A slow handler:** add `Thread.sleep(500)` to a handler for a test. The gap between "the waiter completes" and "the handler ends" then shows.
- **Many characters:** run `PartyMerchant` with more fighters. Lock contention grows with the number of threads.
- **Timestamps with thread names:** a log line with `Thread.currentThread().getName()`, as in `TraceRequest`, shows which thread did each step.

Java has no race detector like Go's `-race`. A data race shows only as a wrong value, sometimes. Your defense is the design of [Async 7](#guide-async-7-shared-state): each shared field is `final`, `volatile`, atomic, or guarded by one named lock. Write the name of the lock in a comment on the field, as the course does ("guarded by `this`").

#### A clock that jumps

A timing log can also find a bug outside your threads. The course program `gear-up` failed now and then with "could not walk". A log with `currentTimeMillis()` around `Thread.sleep` in `moveTo` showed this:

```text
DEBUG moveTo seconds=3.061179337481214 speed=60.334375 me=-32.0,456.0 move() took 1
DEBUG slept 1003
```

A sleep of 3,311 ms seemed to take 1,003 ms. `Thread.sleep` was correct. The wall clock jumped back by about 2.3 s during the sleep. The most likely cause is a clock sync of the Docker VM under load.

`World.advance` used the same wall clock, so it moved the character 2.3 s too little. The walk then looked unfinished. The cure: each duration in the course now uses `World.nowMs()`, which reads `System.nanoTime()`. That clock only goes forward.

#### A slow handler or a growing queue

`events` has no size limit, so slow handlers do not show as missed pongs. They show as a delay between server time and your reaction, and as heap growth. To measure it, log `System.nanoTime()` at the start and the end of a handler. Read the size of the queue with a debugger or in a test build. In a heap dump (`jcmd $pid GC.heap_dump /tmp/h.hprof`), many `AlSocket$Event` objects mean a slow dispatcher.

#### Checklist: the Java mistakes that you can now explain

- **`get()` or `join()` in a handler.** The dispatcher waits for an event that only the dispatcher can deliver. The wait ends only at its timeout.
- **Send, then `waitFor`.** The reply can arrive between the two calls, and the dispatcher drops it. Register first.
- **A plain field shared between the tick and a handler.** No happens-before edge: the tick can see an old value or a half-done update. Use a lock, `volatile` or an atomic.
- **A blocking call inside `synchronized` on a virtual thread (Java 21).** The virtual thread pins its carrier. With a few such waits, every virtual thread stops.
- **A lock held across `request`.** Every handler that needs the lock waits up to the timeout of the request.
- **Locks in two orders.** The course takes `world` first, then the object. A predicate or handler that reverses this order can deadlock.
- **`supplyAsync` without an executor for blocking work.** It fills the common pool, and the last stage of each waiter waits behind it.
- **`thenApply` on a waiter future and the dispatcher.** A stage without `Async` runs on the thread that completes the future.
- **`CompletableFuture.cancel(true)` to stop work.** It only fills the box. Use `Future.cancel(true)` from an executor, or interrupt the thread.
- **Swallowed `InterruptedException`.** Catch it only to set the flag again or to end the thread.
- **A `Future` that nobody reads.** Its exception is silent. A dead thread only prints to `System.err`.
- **A loop that completes futures over a shared list.** Each `complete` runs callbacks on your thread, and they can change the list. Copy it first, as `dispatch` does.
- **The wall clock for durations.** Use `System.nanoTime()` (the course: `World.nowMs()`), not `System.currentTimeMillis()`.
- **A virtual thread missing from `jstack`.** Use `jcmd <pid> Thread.dump_to_file -format=json`.

</div>
