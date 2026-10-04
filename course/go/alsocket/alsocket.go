// Package alsocket is a minimal Socket.IO v4 client, written by hand on top
// of a plain WebSocket. It does enough to play Adventure Land, and no more.
//
//	go get github.com/coder/websocket@v1.8.13   (v1.8.14+ needs Go 1.23)
package alsocket

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/coder/websocket"
)

// ErrClosed is the error when the connection has ended.
var ErrClosed = errors.New("alsocket: socket is closed")

// Handler gets the payload of an event as raw JSON (nil if there is no
// payload). Decode it with json.Unmarshal into the struct that you expect.
type Handler func(data json.RawMessage)

type event struct {
	name string
	data json.RawMessage
}

type waiter struct {
	name string
	pred func(json.RawMessage) bool
	ch   chan json.RawMessage // buffer of 1: a send never blocks
}

// Socket is one connection to a game server. You can call its methods from
// any goroutine.
//
// Two goroutines do the work: readLoop reads packets and answers pings at
// once, and dispatchLoop runs your handlers. Because they are separate, a
// slow handler can't make us miss a ping.
type Socket struct {
	conn *websocket.Conn

	mu        sync.Mutex // guards the five fields below
	handlers  map[string][]Handler
	waiters   map[*waiter]struct{}
	early     map[string][]json.RawMessage // payloads from before the first On/Expect
	listening bool                         // true after the first On/Expect
	closed    bool

	closing atomic.Bool   // Close sets it, so that readLoop knows the end was ours
	events  chan event    // readLoop -> dispatchLoop
	done    chan struct{} // closed when the connection has ended
}

// Connect opens the WebSocket and does the Socket.IO handshake. url is the
// full URL, for example "wss://de.adventure.land/ws1/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1".
func Connect(ctx context.Context, url string) (*Socket, error) {
	// 10 s: a working server answers in much less time. The ctx of the caller
	// can make it shorter.
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	conn, _, err := websocket.Dial(ctx, url, nil)
	if err != nil {
		return nil, err
	}
	// By default the library refuses messages over 32 KiB. AL's "start" and
	// "entities" payloads can be larger, so accept up to 16 MiB.
	conn.SetReadLimit(16 << 20)

	// Engine.IO "open": 0{"sid", "pingInterval", "pingTimeout", ...}
	if _, msg, err := conn.Read(ctx); err != nil || !strings.HasPrefix(string(msg), "0") {
		conn.Close(websocket.StatusProtocolError, "")
		return nil, fmt.Errorf("expected Engine.IO open, got %q (%v)", msg, err)
	}
	// Send Socket.IO "connect" for the default namespace "/".
	if err := conn.Write(ctx, websocket.MessageText, []byte("40")); err != nil {
		return nil, err
	}
	_, msg, err := conn.Read(ctx)
	if err != nil || !strings.HasPrefix(string(msg), "40") {
		// "44..." is CONNECT_ERROR: the server refused us.
		conn.Close(websocket.StatusProtocolError, "")
		return nil, fmt.Errorf("expected 40, got %q (%v)", msg, err)
	}

	s := &Socket{
		conn:     conn,
		handlers: map[string][]Handler{},
		waiters:  map[*waiter]struct{}{},
		early:    map[string][]json.RawMessage{},
		// If this buffer is full, readLoop waits, and pings get no answer.
		events: make(chan event, 1024),
		done:   make(chan struct{}),
	}
	go s.readLoop()
	go s.dispatchLoop()
	return s, nil
}

// readLoop reads all packets until the connection ends.
func (s *Socket) readLoop() {
	reason := "transport closed"
	for {
		_, msg, err := s.conn.Read(context.Background())
		if err != nil {
			if s.closing.Load() {
				reason = "closed by client"
			} else if code := websocket.CloseStatus(err); code != -1 {
				reason = fmt.Sprintf("transport closed (code %d)", code)
			} else {
				reason = "transport error: " + err.Error()
			}
			break
		}
		packet := string(msg)
		switch {
		case packet == "2":
			// Engine.IO ping. Send a pong at once. If you don't, the server
			// drops you after pingInterval + pingTimeout.
			s.write("3")
		case strings.HasPrefix(packet, "42"):
			// Socket.IO EVENT: 42["name", payload]. An ack id (digits) can
			// come between "42" and "[", so parse from the "[".
			var args []json.RawMessage
			var name string
			i := strings.IndexByte(packet, '[')
			if i < 0 || json.Unmarshal([]byte(packet[i:]), &args) != nil || len(args) == 0 ||
				json.Unmarshal(args[0], &name) != nil {
				log.Printf("alsocket: bad event packet %.80q", packet)
				continue
			}
			var data json.RawMessage // nil when there is no payload
			if len(args) > 1 {
				data = args[1]
			}
			s.mu.Lock()
			if !s.listening {
				// Nobody listens yet: keep the event (see subscribed).
				s.early[name] = append(s.early[name], data)
				s.mu.Unlock()
				continue
			}
			s.mu.Unlock()
			s.events <- event{name, data}
		case strings.HasPrefix(packet, "41"), packet == "1":
			// 41: the server closed our namespace. 1: Engine.IO close.
			s.conn.Close(websocket.StatusNormalClosure, "")
		}
		// AL does not use the other packets ("6" noop, binary packets, acks).
	}
	// socket.io-client reports the end as a local "disconnect" event, and so
	// does AlSocket. The server never sends an event with this name.
	reasonJSON, _ := json.Marshal(reason)
	s.events <- event{"disconnect", reasonJSON}
	close(s.events) // dispatchLoop stops after the last event
}

// dispatchLoop gives events to handlers and waiters, in arrival order.
func (s *Socket) dispatchLoop() {
	for ev := range s.events {
		s.deliver(ev)
	}
	s.mu.Lock()
	s.closed = true
	s.mu.Unlock()
	close(s.done) // wakes each WaitFor that still waits
}

// deliver gives one event to the handlers and waiters for its name.
func (s *Socket) deliver(ev event) {
	s.mu.Lock()
	handlers := append([]Handler(nil), s.handlers[ev.name]...)
	var matched []*waiter
	for w := range s.waiters {
		if w.name == ev.name && safePred(w, ev.data) {
			matched = append(matched, w)
			delete(s.waiters, w)
		}
	}
	s.mu.Unlock()
	// Handlers first, then waiters. Thus, when a wait returns, the handlers
	// of the same event (for example, the ones that update your copy of the
	// world) have already run.
	for _, h := range handlers {
		safeCall(ev.name, h, ev.data)
	}
	for _, w := range matched {
		w.ch <- ev.data // the buffer has room for 1, so this never blocks
	}
}

// subscribed runs after each On/Expect. The server sends "welcome"
// immediately after the handshake, before your code can call WaitFor.
// AlSocket keeps all events from before the first On/Expect. The first
// subscriber for an event name gets the kept events for that name. They
// run on the goroutine that called On/Expect, one time.
func (s *Socket) subscribed(name string) {
	s.mu.Lock()
	s.listening = true
	kept := s.early[name]
	delete(s.early, name)
	s.mu.Unlock()
	for _, data := range kept {
		s.deliver(event{name, data})
	}
}

// safePred runs the predicate of a waiter. A panic counts as "no match".
func safePred(w *waiter, data json.RawMessage) (match bool) {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("alsocket: predicate for %q panicked: %v", w.name, r)
			match = false
		}
	}()
	return w.pred(data)
}

// safeCall runs one handler. A panic goes to the log and the program continues.
func safeCall(name string, h Handler, data json.RawMessage) {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("alsocket: handler for %q panicked: %v", name, r)
		}
	}()
	h(data)
}

func (s *Socket) write(packet string) error {
	// 10 s: if a write takes longer, the connection is dead.
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return s.conn.Write(ctx, websocket.MessageText, []byte(packet))
}

// Emit sends an event: 42["name", data]. With nil data, it sends no payload.
// data can be anything that encoding/json can encode (a struct, a map, ...).
func (s *Socket) Emit(name string, data any) error {
	args := []any{name}
	if data != nil {
		args = append(args, data)
	}
	b, err := json.Marshal(args)
	if err != nil {
		return err
	}
	return s.write("42" + string(b))
}

// On calls handler for each event called name from now on. Handlers run one
// at a time on the dispatch goroutine, so keep them fast.
func (s *Socket) On(name string, handler Handler) {
	s.mu.Lock()
	s.handlers[name] = append(s.handlers[name], handler)
	s.mu.Unlock()
	s.subscribed(name)
}

// Expect starts to wait for the next event called name for which pred
// returns true (nil pred: any event). It registers the waiter immediately
// and returns a function that blocks until the result. Use it for the reply
// to an event that you send next. pred runs while the socket holds its
// lock, so pred must not call Socket methods.
//
//	wait := sock.Expect("start", nil)
//	sock.Emit("auth", ...)
//	me, err := wait(ctx)
func (s *Socket) Expect(name string, pred func(json.RawMessage) bool) func(context.Context) (json.RawMessage, error) {
	if pred == nil {
		pred = func(json.RawMessage) bool { return true }
	}
	w := &waiter{name: name, pred: pred, ch: make(chan json.RawMessage, 1)}
	s.mu.Lock()
	closed := s.closed
	if !closed {
		s.waiters[w] = struct{}{}
	}
	s.mu.Unlock()
	s.subscribed(name)

	return func(ctx context.Context) (json.RawMessage, error) {
		if closed {
			return nil, ErrClosed
		}
		select {
		case data := <-w.ch:
			return data, nil
		case <-ctx.Done(): // your timeout
			s.mu.Lock()
			delete(s.waiters, w)
			s.mu.Unlock()
			return nil, fmt.Errorf("waiting for %q: %w", name, ctx.Err())
		case <-s.done:
			select {
			case data := <-w.ch: // it came just before the end
				return data, nil
			default:
				return nil, ErrClosed
			}
		}
	}
}

// WaitFor blocks until the next event called name for which pred returns
// true (nil pred: any event), until ctx is done, or until the socket closes.
// Put a timeout on ctx (context.WithTimeout), or it can wait forever.
func (s *Socket) WaitFor(ctx context.Context, name string, pred func(json.RawMessage) bool) (json.RawMessage, error) {
	return s.Expect(name, pred)(ctx)
}

// Done is closed when the connection has ended and dispatchLoop has given
// out each event.
func (s *Socket) Done() <-chan struct{} { return s.done }

// Close disconnects correctly: Socket.IO disconnect, then a normal
// WebSocket close.
func (s *Socket) Close() error {
	s.closing.Store(true)
	s.write("41") // if the connection is already gone, the error does not matter
	return s.conn.Close(websocket.StatusNormalClosure, "")
}
