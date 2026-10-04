// alsocket.rs: a minimal Socket.IO v4 client, written by hand on top of a
// plain WebSocket. It does enough to play Adventure Land, and no more.
//
//   cargo add tokio --features full
//   cargo add tokio-tungstenite --features rustls-tls-webpki-roots
//   cargo add futures-util serde_json

use std::collections::HashMap;
use std::future::Future;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use serde_json::Value;
use tokio::sync::{mpsc, oneshot, watch};
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
}

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

        // Writer: the only task that uses the sending half.
        tokio::spawn(async move {
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

        // Reader: all packets, until the connection ends.
        let pong = out_tx.clone();
        let state = shared.clone();
        tokio::spawn(async move {
            let reason = loop {
                let packet = match stream.next().await {
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
            // socket.io-client reports the end as a local "disconnect" event,
            // and so does AlSocket. The server never sends this name.
            let _ = event_tx.send(("disconnect".to_string(), Value::String(reason)));
            // When event_tx is dropped here, the loop of the dispatcher ends
            // after the last event.
        });

        // Dispatcher: gives events to handlers and waiters, in arrival order.
        let state = shared.clone();
        tokio::spawn(async move {
            while let Some((name, data)) = event_rx.recv().await {
                deliver(&state, &name, &data);
            }
            let mut s = state.lock().unwrap();
            s.closed = true;
            s.waiters.clear(); // dropping the senders fails each wait_for that still waits
            let _ = done_tx.send(true);
        });

        Ok(AlSocket {
            out: out_tx,
            shared,
            done: done_rx,
        })
    }

    // Each on/wait_for calls this. The server sends "welcome" immediately
    // after the handshake, before your code can call wait_for("welcome").
    // AlSocket keeps all events from before the first on/wait_for. The first
    // subscriber for an event name gets the kept events for that name. They
    // run on the task that called on/wait_for, one time.
    fn subscribed(&self, event: &str) {
        let kept = {
            let mut s = self.shared.lock().unwrap();
            s.listening = true;
            s.early.remove(event).unwrap_or_default()
        };
        for data in kept {
            deliver(&self.shared, event, &data);
        }
    }

    /// Send an event: 42["name", data]. With `Value::Null`, send no payload.
    pub async fn emit(&self, event: &str, data: Value) -> Result<()> {
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
    /// given out each event.
    pub async fn close(&self) -> Result<()> {
        let _ = self.out.send(Out::Text("41".into()));
        let _ = self.out.send(Out::Close);
        let mut done = self.done.clone();
        let _ = done.wait_for(|ended| *ended).await;
        Ok(())
    }
}
