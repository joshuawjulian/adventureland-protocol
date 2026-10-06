// alsocket.js: a minimal Socket.IO v4 client, written by hand on top of a
// plain WebSocket. It does enough to play Adventure Land, and no more.
// Runtime: Node.js 22+ (WebSocket is built in). No npm packages.

export class AlSocket {
  #ws; // the WebSocket
  #handlers = new Map(); // event name -> [handler, ...] from on()
  #waiters = new Set(); // waitFor() calls that wait for an event
  #early = new Map(); // event name -> [payload, ...] from before the first on()/waitFor()
  #listening = false; // true after the first on()/waitFor()
  #closed = false;
  /** @type {ReturnType<typeof setTimeout> | null} */
  #closeTimer = null; // close(): the 5 s limit for the end of the connection

  constructor(ws) {
    this.#ws = ws;
  }

  // Open the WebSocket and do the Socket.IO handshake. `url` is the full
  // URL, for example "wss://de.adventure.land/ws1/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1".
  static connect(url, timeoutMs = 10_000) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      const sock = new AlSocket(ws);
      let connected = false;
      // 10 s by default: a working server answers in much less time.
      const timer = setTimeout(() => {
        reject(new Error("connect timed out"));
        ws.close();
      }, timeoutMs);

      ws.addEventListener("message", (msg) => {
        const packet = String(msg.data); // Socket.IO v4 uses text frames
        if (packet.startsWith("0")) {
          // Engine.IO "open": 0{"sid", "pingInterval", "pingTimeout", ...}.
          // Reply with Socket.IO "connect" for the default namespace "/".
          ws.send("40");
        } else if (packet.startsWith("40")) {
          // The server accepted the connection to the namespace.
          connected = true;
          clearTimeout(timer);
          resolve(sock);
        } else if (packet.startsWith("44")) {
          // Socket.IO CONNECT_ERROR: the server refused us.
          clearTimeout(timer);
          reject(new Error("server refused connect: " + packet.slice(2)));
          ws.close();
        } else {
          sock.#onPacket(packet);
        }
      });

      // An "error" always comes before a "close", so the cleanup is in "close".
      ws.addEventListener("error", () => {});
      ws.addEventListener("close", (ev) => {
        clearTimeout(timer);
        if (!connected) reject(new Error(`connection closed during handshake (code ${ev.code})`));
        sock.#shutdown(`transport closed (code ${ev.code})`);
      });
    });
  }

  // All packets after the handshake come here.
  #onPacket(packet) {
    if (packet === "2") {
      // Engine.IO ping from the server. Send a pong at once. If you don't,
      // the server drops you after pingInterval + pingTimeout.
      this.#ws.send("3");
    } else if (packet.startsWith("42")) {
      // Socket.IO EVENT: 42["name", payload]. An ack id (digits) can come
      // between "42" and "[", so parse from the "[".
      let args;
      try {
        args = JSON.parse(packet.slice(packet.indexOf("[")));
      } catch (err) {
        // A bad frame must not stop the program: an exception that leaves a
        // WebSocket listener is an uncaught exception, and Node.js exits.
        // Log the frame and continue with the next one.
        console.error("bad event frame, ignored:", packet.slice(0, 200), err);
        return;
      }
      this.#deliver(args[0], args[1]); // with no payload, args[1] is undefined
    } else if (packet.startsWith("41") || packet === "1") {
      // 41: the server closed our namespace. 1: Engine.IO close.
      this.#ws.close();
    }
    // AL does not use the other packets ("6" noop, binary packets, acks).
  }

  // Give one event to the handlers and waiters for its name.
  #deliver(event, data) {
    if (!this.#listening) {
      // Nobody listens yet: keep the event (see #subscribed).
      if (!this.#early.has(event)) this.#early.set(event, []);
      this.#early.get(event).push(data);
      return;
    }
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
      if (w.event !== event) continue;
      let match = false;
      try {
        match = w.pred(data);
      } catch (err) {
        console.error(`waitFor predicate for "${event}" threw:`, err); // an error counts as "no match"
      }
      if (match) w.resolve(data);
    }
  }

  // Each on()/waitFor() calls this. The server sends "welcome" immediately
  // after the handshake, before your code can call waitFor("welcome").
  // AlSocket keeps all events from before the first on()/waitFor(). The
  // first subscriber for an event name gets the kept events for that name.
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

  // Send an event: 42["name", data]. With no `data`, send no payload.
  emit(event, data) {
    if (this.#closed) throw new Error("socket is closed");
    const args = data === undefined ? [event] : [event, data];
    this.#ws.send("42" + JSON.stringify(args));
  }

  // Call `handler(data)` for each `event` from now on.
  on(event, handler) {
    if (!this.#handlers.has(event)) this.#handlers.set(event, []);
    this.#handlers.get(event).push(handler);
    this.#subscribed(event);
  }

  // Resolve with the payload of the next `event` for which pred(data) is true.
  // Reject after `timeoutMs`, or if the socket closes first. The waiter
  // starts when you call waitFor(), so you can call it, then emit, then await.
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

  // Disconnect correctly: Socket.IO disconnect, then a normal WebSocket close.
  // close() returns at once. The local "disconnect" event comes later, from
  // the WebSocket "close" event. If that event does not come in 5 s (a server
  // that never answers the close), end the session here: 5 s is far more than
  // a working close takes, and short enough that a program can go on.
  close() {
    if (this.#closed || this.#closeTimer) return;
    if (this.#ws.readyState === WebSocket.OPEN) this.#ws.send("41");
    this.#ws.close(1000);
    this.#closeTimer = setTimeout(() => this.#shutdown("closed by us (no close from the server in 5 s)"), 5000);
    this.#closeTimer.unref(); // this timer alone must not keep Node.js running
  }

  // This runs one time, when the connection ends for any cause.
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
}
