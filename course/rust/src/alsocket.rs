// alsocket.rs: a minimal Socket.IO v4 client, written by hand on top of a
// plain WebSocket. It does enough to play Adventure Land, and no more.
//
//   cargo add tokio --features full
//   cargo add tokio-tungstenite --features rustls-tls-webpki-roots
//   cargo add futures-util serde_json

use std::collections::{HashMap, VecDeque};
use std::future::Future;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use serde_json::Value;
use tokio::sync::{mpsc, oneshot, watch, Notify};
use tokio::task::AbortHandle;
use tokio_tungstenite::connect_async;
use tokio_tungstenite::tungstenite::protocol::{frame::coding::CloseCode, CloseFrame};
use tokio_tungstenite::tungstenite::Message;

pub type Error = Box<dyn std::error::Error + Send + Sync>;
pub type Result<T> = std::result::Result<T, Error>;

type Handler = Arc<dyn Fn(&Value) + Send + Sync>;

struct Waiter {
    event: String,
    pred: Box<dyn Fn(&Value) -> bool + Send>,
    tx: oneshot::Sender<Value>,
}

// State that your code and the background tasks share.
#[derive(Default)]
struct Shared {
    handlers: HashMap<String, Vec<Handler>>,
    waiters: Vec<Waiter>,
    early: HashMap<String, Vec<Value>>, // events from before the first on/wait_for
    replay: VecDeque<(String, Value)>,  // kept events that the dispatcher must give out next
    listening: bool,                    // true after the first on/wait_for
    closed: bool,
}

// What the writer task must send next.
enum Out {
    Text(String),
    Close,
}

/// One connection to a game server. Three background tasks do the work:
/// the reader reads packets and answers pings at once, the writer owns the
/// sending half, and the dispatcher runs your handlers. Because they are
/// separate, a slow handler can't make us miss a ping.
pub struct AlSocket {
    out: mpsc::UnboundedSender<Out>,
    shared: Arc<Mutex<Shared>>,
    done: watch::Receiver<bool>, // true when the connection has ended
    replay: Arc<Notify>,         // wakes the dispatcher: kept events wait in `replay`
    force: Arc<Notify>,          // makes the reader stop now (see close and Drop)
    ended: Arc<AtomicBool>,      // true when the reader saw the end of the connection
    writer: AbortHandle,         // to stop a writer that waits on a dead connection
}

/// 5 s: the longest time that close() and drop wait for the server to answer
/// our close frame. A working server answers in much less; a server that is
/// gone (or a network that drops packets) never answers. Then we stop the
/// connection from our side, so that close() cannot wait forever.
const CLOSE_WAIT: Duration = Duration::from_secs(5);

// The next text message. Other frame types are ignored.
async fn next_text<S>(stream: &mut S) -> Result<String>
where
    S: StreamExt<Item = std::result::Result<Message, tokio_tungstenite::tungstenite::Error>>
        + Unpin,
{
    loop {
        match stream.next().await {
            Some(Ok(Message::Text(t))) => return Ok(t.to_string()),
            Some(Ok(Message::Close(_))) | None => return Err("closed during handshake".into()),
            Some(Ok(_)) => continue, // binary/ping frames: not part of the handshake
            Some(Err(e)) => return Err(e.into()),
        }
    }
}

// Give one event to the handlers and waiters for its name. The handlers run
// first, so a waiter that wakes up sees the state that the handlers made (for
// example, a world that already applied this "start").
fn deliver(shared: &Mutex<Shared>, name: &str, data: &Value) {
    // A copy of the list: a handler can call on() without a deadlock.
    let handlers = shared.lock().unwrap().handlers.get(name).cloned().unwrap_or_default();
    for handler in handlers {
        // A handler that panics gets a report. The dispatcher continues.
        if catch_unwind(AssertUnwindSafe(|| handler(data))).is_err() {
            eprintln!("alsocket: handler for {name:?} panicked");
        }
    }
    let mut s = shared.lock().unwrap();
    // Remove waiters whose caller stopped waiting (timeout).
    s.waiters.retain(|w| !w.tx.is_closed());
    // Give the payload to each waiter that matches, and remove it.
    let mut i = 0;
    while i < s.waiters.len() {
        let w = &s.waiters[i];
        // A predicate that panics counts as "no match".
        let matched =
            w.event == name && catch_unwind(AssertUnwindSafe(|| (w.pred)(data))).unwrap_or(false);
        if matched {
            let _ = s.waiters.swap_remove(i).tx.send(data.clone());
        } else {
            i += 1;
        }
    }
}

// Give out the kept events that `subscribed` put in `replay`, oldest first.
// Take them under the lock, deliver them outside it (handlers lock it too).
fn drain_replay(shared: &Mutex<Shared>) {
    loop {
        let Some((name, data)) = shared.lock().unwrap().replay.pop_front() else { return };
        deliver(shared, &name, &data);
    }
}

impl AlSocket {
    /// Open the WebSocket and do the Socket.IO handshake. `url` is the full
    /// URL, for example "wss://de.adventure.land/ws1/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1".
    pub async fn connect(url: &str) -> Result<AlSocket> {
        // 10 s: a working server answers in much less time.
        let ten_s = Duration::from_secs(10);
        let (ws, _response) = tokio::time::timeout(ten_s, connect_async(url)).await??;
        let (mut sink, mut stream) = ws.split();

        let handshake = async {
            // Engine.IO "open": 0{"sid", "pingInterval", "pingTimeout", ...}
            let open = next_text(&mut stream).await?;
            if !open.starts_with('0') {
                return Err(format!("expected Engine.IO open, got {open:?}").into());
            }
            // Send Socket.IO "connect" for the default namespace "/".
            sink.send(Message::Text("40".into())).await?;
            let reply = next_text(&mut stream).await?;
            if !reply.starts_with("40") {
                // "44..." is CONNECT_ERROR: the server refused us.
                return Err(format!("expected 40, got {reply:?}").into());
            }
            Ok::<(), Error>(())
        };
        tokio::time::timeout(ten_s, handshake).await??;

        let (out_tx, mut out_rx) = mpsc::unbounded_channel::<Out>();
        let (event_tx, mut event_rx) = mpsc::unbounded_channel::<(String, Value)>();
        let (done_tx, done_rx) = watch::channel(false);
        let shared = Arc::new(Mutex::new(Shared::default()));
        let replay = Arc::new(Notify::new());
        let force = Arc::new(Notify::new());
        let ended = Arc::new(AtomicBool::new(false));

        // Writer: the only task that uses the sending half.
        let writer = tokio::spawn(async move {
            while let Some(out) = out_rx.recv().await {
                let result = match out {
                    Out::Text(text) => sink.send(Message::Text(text.into())).await,
                    Out::Close => {
                        // 1000 = normal closure.
                        let frame = CloseFrame {
                            code: CloseCode::Normal,
                            reason: "".into(),
                        };
                        let _ = sink.send(Message::Close(Some(frame))).await;
                        break;
                    }
                };
                if result.is_err() {
                    break; // the connection is gone; the reader sees it too
                }
            }
        });

        // Reader: all packets, until the connection ends, or until close() or
        // drop gives up on the server (`force`).
        let pong = out_tx.clone();
        let state = shared.clone();
        let (stop, saw_end) = (force.clone(), ended.clone());
        tokio::spawn(async move {
            let reason = loop {
                let next = tokio::select! {
                    // `biased`: a waiting stop wins over more packets.
                    biased;
                    _ = stop.notified() => break "closed by the client (no answer to the close in 5 s)".to_string(),
                    next = stream.next() => next,
                };
                let packet = match next {
                    Some(Ok(Message::Text(t))) => t.to_string(),
                    Some(Ok(Message::Close(frame))) => {
                        let code = frame.map(|f| u16::from(f.code)).unwrap_or(1005);
                        break format!("transport closed (code {code})");
                    }
                    Some(Ok(_)) => continue, // binary/ping/pong frames: AL doesn't use them
                    Some(Err(e)) => break format!("transport error: {e}"),
                    None => break "transport closed".to_string(),
                };
                if packet == "2" {
                    // Engine.IO ping. Send a pong at once. If you don't, the
                    // server drops you after pingInterval + pingTimeout.
                    let _ = pong.send(Out::Text("3".into()));
                } else if packet.starts_with("42") {
                    // Socket.IO EVENT: 42["name", payload]. An ack id (digits)
                    // can come between "42" and "[", so parse from the "[".
                    let start = packet.find('[').unwrap_or(packet.len());
                    match serde_json::from_str::<Vec<Value>>(&packet[start..]) {
                        Ok(mut args) if matches!(args.first(), Some(Value::String(_))) => {
                            // With no payload, data is Value::Null.
                            let data = if args.len() > 1 {
                                args.swap_remove(1)
                            } else {
                                Value::Null
                            };
                            let name = args[0].as_str().unwrap_or_default().to_string();
                            let mut s = state.lock().unwrap();
                            if !s.listening {
                                // Nobody listens yet: keep the event (see subscribed).
                                s.early.entry(name).or_default().push(data);
                                continue;
                            }
                            drop(s);
                            let _ = event_tx.send((name, data));
                        }
                        _ => eprintln!("alsocket: bad event packet {packet:.80}"),
                    }
                } else if packet.starts_with("41") || packet == "1" {
                    // 41: the server closed our namespace. 1: Engine.IO close.
                    let _ = pong.send(Out::Close);
                }
                // AL does not use the other packets ("6" noop, binary packets, acks).
            };
            // From now on, emit() fails at once (see emit).
            saw_end.store(true, Ordering::SeqCst);
            // Drop our half of the stream now. The writer ends at its next send
            // or at Out::Close; with both halves gone, the TCP connection closes.
            drop(stream);
            // socket.io-client reports the end as a local "disconnect" event,
            // and so does AlSocket. The server never sends this name.
            let _ = event_tx.send(("disconnect".to_string(), Value::String(reason)));
            // When event_tx is dropped here, the loop of the dispatcher ends
            // after the last event.
        });

        // Dispatcher: gives events to handlers and waiters, in arrival order.
        // The kept events of `replay` go first: they arrived before each event
        // that is still in the channel. `wake` tells it that replay has some.
        let state = shared.clone();
        let wake = replay.clone();
        tokio::spawn(async move {
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
            // The end. The same lock as `subscribed`: after this, nobody adds to
            // replay, and no wait_for registers.
            let waiters = {
                let mut s = state.lock().unwrap();
                s.closed = true;
                std::mem::take(&mut s.waiters)
            };
            // Dropping the senders fails each wait_for that still waits, one
            // time each. We drop them outside the lock, from our own copy.
            drop(waiters);
            let _ = done_tx.send(true);
        });

        Ok(AlSocket {
            out: out_tx,
            shared,
            done: done_rx,
            replay,
            force,
            ended,
            writer: writer.abort_handle(),
        })
    }

    // Each on/wait_for calls this. The server sends "welcome" immediately
    // after the handshake, before your code can call wait_for("welcome").
    // AlSocket keeps all events from before the first on/wait_for. The first
    // subscriber for an event name gets the kept events for that name, one
    // time. They go to the dispatcher (through `replay`), like every other
    // event: the handlers run on the dispatcher task, one at a time, before
    // each event that is still in the channel.
    fn subscribed(&self, event: &str) {
        let mut s = self.shared.lock().unwrap();
        s.listening = true;
        if s.closed {
            return; // the dispatcher has ended: nobody would give them out
        }
        let kept = s.early.remove(event).unwrap_or_default();
        if kept.is_empty() {
            return;
        }
        s.replay.extend(kept.into_iter().map(|data| (event.to_string(), data)));
        drop(s);
        // The dispatcher can wait on an empty channel: wake it. If it is busy,
        // Notify keeps the wake for its next wait.
        self.replay.notify_one();
    }

    /// Send an event: 42["name", data]. With `Value::Null`, send no payload.
    ///
    /// `Ok` means that the frame is in the queue of the writer task, not that
    /// it is on the network. After the reader saw the end of the connection,
    /// emit fails at once. A frame that you queue in the short time before
    /// that (the connection broke, but nothing noticed it yet) is lost
    /// without an error. The `disconnect` event is the reliable sign of the end.
    pub async fn emit(&self, event: &str, data: Value) -> Result<()> {
        if self.ended.load(Ordering::SeqCst) {
            return Err("socket is closed".into());
        }
        let args = if data.is_null() {
            vec![Value::from(event)]
        } else {
            vec![Value::from(event), data]
        };
        let packet = format!("42{}", serde_json::to_string(&args)?);
        self.out
            .send(Out::Text(packet))
            .map_err(|_| "socket is closed".into())
    }

    /// Call `handler(&data)` for each `event` from now on. Handlers run one
    /// at a time on the dispatcher task, so keep them fast.
    pub fn on(&self, event: &str, handler: impl Fn(&Value) + Send + Sync + 'static) {
        let mut s = self.shared.lock().unwrap();
        s.handlers
            .entry(event.to_string())
            .or_default()
            .push(Arc::new(handler));
        drop(s);
        self.subscribed(event);
    }

    /// The payload of the next `event` for which `pred(&data)` is true. It
    /// fails after 10 s, or if the socket closes first. This is not an
    /// `async fn` on purpose: the call registers the waiter immediately.
    /// Thus you can call it, then emit, then `.await` it.
    pub fn wait_for(
        &self,
        event: &str,
        pred: impl Fn(&Value) -> bool + Send + 'static,
    ) -> impl Future<Output = Result<Value>> + 'static {
        self.wait_for_timeout(event, pred, Duration::from_secs(10))
    }

    /// The same as `wait_for`, with your timeout.
    pub fn wait_for_timeout(
        &self,
        event: &str,
        pred: impl Fn(&Value) -> bool + Send + 'static,
        timeout: Duration,
    ) -> impl Future<Output = Result<Value>> + 'static {
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
        if registered {
            self.subscribed(event);
        }
        let event = event.to_string();
        async move {
            if !registered {
                return Err("socket is closed".into());
            }
            match tokio::time::timeout(timeout, rx).await {
                Ok(Ok(data)) => Ok(data),
                Ok(Err(_)) => Err("socket closed".into()),
                Err(_) => Err(format!("timed out waiting for {event:?}").into()),
            }
        }
    }

    /// Disconnect correctly: Socket.IO disconnect, then a normal WebSocket
    /// close. Returns when the connection has ended and the dispatcher has
    /// given out each event. If the server does not answer in 5 s, it stops
    /// the connection from our side, and returns soon after.
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

    // Queue the Socket.IO disconnect and the WebSocket close frame.
    fn start_close(&self) {
        let _ = self.out.send(Out::Text("41".into()));
        let _ = self.out.send(Out::Close);
    }

    // Stop without the server: the reader leaves its loop (and sends
    // `disconnect`), and the writer stops. Both halves of the WebSocket are
    // dropped, so the TCP connection closes.
    fn force_close(&self) {
        self.force.notify_one();
        self.writer.abort();
    }
}

/// A dropped AlSocket closes its connection, the same as close() but without
/// the wait. Without this, the reader would answer pings forever (it holds a
/// sender of the writer's queue for the pongs), and the character would stay
/// in the game. Call close().await when you can: it waits for the end.
impl Drop for AlSocket {
    fn drop(&mut self) {
        if *self.done.borrow() {
            return; // the connection has ended already
        }
        self.start_close();
        // Give the server 5 s to answer the close frame, then stop. This needs
        // a task; outside a Tokio runtime the tasks end with the runtime anyway.
        if let Ok(rt) = tokio::runtime::Handle::try_current() {
            let (force, writer, mut done) = (self.force.clone(), self.writer.clone(), self.done.clone());
            rt.spawn(async move {
                if tokio::time::timeout(CLOSE_WAIT, done.wait_for(|ended| *ended)).await.is_err() {
                    force.notify_one();
                    writer.abort();
                }
            });
        }
    }
}
