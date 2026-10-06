// AlSocket.cs: a minimal Socket.IO v4 client, written by hand on top of a
// plain WebSocket. It does enough to play Adventure Land, and no more.
// .NET 8. No NuGet packages.
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading.Channels;

namespace Albot;

public sealed class AlSocket
{
    private readonly ClientWebSocket _ws;
    // ClientWebSocket allows one send at a time. Pongs (reader task) and
    // your emits (any task) use this lock to take turns.
    private readonly SemaphoreSlim _sendLock = new(1, 1);

    private readonly object _lock = new(); // guards the six fields below
    private readonly Dictionary<string, List<Action<JsonElement>>> _handlers = new();
    private readonly List<Waiter> _waiters = new();
    private readonly Dictionary<string, List<JsonElement>> _early = new(); // events from before the first On/WaitForAsync
    private readonly List<(string Name, JsonElement Data)> _replay = new(); // kept events for the dispatcher (see Subscribed)
    private bool _listening; // true after the first On/WaitForAsync
    private bool _closed;

    // Reader task -> dispatcher task. Because they are separate, a slow
    // handler can't make us miss a ping. A null Name is not an event: it only
    // wakes the dispatcher, so that it gives out _replay (see Subscribed).
    private readonly Channel<(string? Name, JsonElement Data)> _events =
        Channel.CreateUnbounded<(string?, JsonElement)>();
    private Task _dispatcher = Task.CompletedTask;

    // CloseAsync waits this long for the clean end, then forces it (see CloseAsync).
    private static readonly TimeSpan CloseTimeout = TimeSpan.FromSeconds(5);

    private sealed record Waiter(string Name, Func<JsonElement, bool> Pred, TaskCompletionSource<JsonElement> Result);

    private AlSocket(ClientWebSocket ws) => _ws = ws;

    /// <summary>Completes when the connection has ended and the dispatcher has given out each event.</summary>
    public Task Completion => _dispatcher;

    /// <summary>
    /// Open the WebSocket and do the Socket.IO handshake. url is the full URL,
    /// for example "wss://de.adventure.land/ws1/?EIO=4&amp;transport=websocket".
    /// </summary>
    public static async Task<AlSocket> ConnectAsync(string url)
    {
        // 10 s: a working server answers in much less time.
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));

        var ws = new ClientWebSocket();
        await ws.ConnectAsync(new Uri(url), timeout.Token);
        var sock = new AlSocket(ws);

        // Engine.IO "open": 0{"sid", "pingInterval", "pingTimeout", ...}
        var open = await sock.ReceiveTextAsync(timeout.Token);
        if (open is null || !open.StartsWith('0'))
            throw new WebSocketException($"expected Engine.IO open, got {open}");
        // Send Socket.IO "connect" for the default namespace "/".
        await sock.SendRawAsync("40");
        var reply = await sock.ReceiveTextAsync(timeout.Token);
        if (reply is null || !reply.StartsWith("40"))
            // "44..." is CONNECT_ERROR: the server refused us.
            throw new WebSocketException($"expected 40, got {reply}");

        _ = Task.Run(sock.ReadLoop);
        sock._dispatcher = Task.Run(sock.Dispatch);
        return sock;
    }

    // One full text message, or null when the server closed the connection.
    // A large message can come in parts. This joins the parts.
    private async Task<string?> ReceiveTextAsync(CancellationToken ct)
    {
        var buffer = new byte[16 * 1024];
        using var message = new MemoryStream();
        while (true)
        {
            var result = await _ws.ReceiveAsync(buffer, ct);
            if (result.MessageType == WebSocketMessageType.Close) return null;
            message.Write(buffer, 0, result.Count);
            if (result.EndOfMessage) return Encoding.UTF8.GetString(message.ToArray());
        }
    }

    private async Task SendRawAsync(string packet)
    {
        await _sendLock.WaitAsync();
        try
        {
            await _ws.SendAsync(Encoding.UTF8.GetBytes(packet), WebSocketMessageType.Text, true, CancellationToken.None);
        }
        finally { _sendLock.Release(); }
    }

    // Reads all packets until the connection ends.
    private async Task ReadLoop()
    {
        string reason;
        try
        {
            while (true)
            {
                var packet = await ReceiveTextAsync(CancellationToken.None);
                if (packet is null)
                {
                    reason = $"transport closed (code {(int?)_ws.CloseStatus})";
                    break;
                }
                if (packet == "2")
                {
                    // Engine.IO ping. Send a pong at once. If you don't, the
                    // server drops you after pingInterval + pingTimeout.
                    await SendRawAsync("3");
                }
                else if (packet.StartsWith("42"))
                {
                    // Socket.IO EVENT: 42["name", payload]. An ack id (digits)
                    // can come between "42" and "[", so parse from the "[".
                    using var doc = JsonDocument.Parse(packet.AsMemory(packet.IndexOf('[')));
                    var args = doc.RootElement;
                    var name = args[0].GetString()!;
                    // Clone: the payload must stay after `doc` is disposed.
                    // With no payload, data is default (ValueKind Undefined).
                    var data = args.GetArrayLength() > 1 ? args[1].Clone() : default;
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
                }
                else if (packet.StartsWith("41") || packet == "1")
                {
                    // 41: the server closed our namespace. 1: Engine.IO close.
                    await CloseOutputAsync();
                }
                // AL does not use the other packets ("6" noop, binary packets, acks).
            }
            if (_ws.State == WebSocketState.CloseReceived) await CloseOutputAsync(); // reply to the close of the server
        }
        catch (Exception e) // network error, bad JSON, ...
        {
            reason = "transport error: " + e.Message;
        }
        // socket.io-client reports the end as a local "disconnect" event, and so
        // does AlSocket. The server never sends an event with this name.
        _events.Writer.TryWrite(("disconnect", JsonSerializer.SerializeToElement(reason)));
        _events.Writer.Complete(); // the dispatcher stops after the last event
    }

    // Gives events to handlers and waiters, in arrival order. This task is the
    // only one that calls Deliver, so handlers never run at the same time as
    // each other, and kept events (Subscribed) keep their place in the order.
    private async Task Dispatch()
    {
        await foreach (var (name, data) in _events.Reader.ReadAllAsync())
        {
            DeliverReplay(); // kept events first: they are older than this item
            if (name is not null) Deliver(name, data); // null: only a wake-up
        }
        DeliverReplay(); // a Subscribed that came after the last item
        // The end: each waiter fails, exactly once. Copy and clear the list
        // inside the lock, and fail the copies outside it. A waiter that fails
        // starts its own callbacks (its timer, ContinueWith); they must never
        // see a list that this loop is going through.
        List<Waiter> left;
        lock (_lock)
        {
            _closed = true;
            left = new(_waiters);
            _waiters.Clear();
        }
        foreach (var w in left) w.Result.TrySetException(new WebSocketException("socket closed"));
    }

    // Gives the kept events that Subscribed put in _replay, in arrival order.
    private void DeliverReplay()
    {
        List<(string Name, JsonElement Data)> replay;
        lock (_lock)
        {
            if (_replay.Count == 0) return;
            replay = new(_replay);
            _replay.Clear();
        }
        foreach (var (name, data) in replay) Deliver(name, data);
    }

    // Gives one event to the handlers, then to the waiters, for its name.
    // Handlers first: when a wait returns, the handlers of the same event (for
    // example, the ones that update the World) have already run.
    private void Deliver(string name, JsonElement data)
    {
        List<Action<JsonElement>> handlers;
        List<Waiter> matched;
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
    }

    // Each On/WaitForAsync calls this. The server sends "welcome" immediately
    // after the handshake, before your code can call WaitForAsync("welcome").
    // AlSocket keeps all events from before the first On/WaitForAsync. The
    // first subscriber for an event name gets the kept events for that name,
    // one time. They go to the dispatcher, like every other event: it gives
    // them out before the next event that it takes, in their arrival order.
    // The dispatcher can be idle (waiting for the channel), so wake it.
    private void Subscribed(string name)
    {
        lock (_lock)
        {
            _listening = true;
            if (_early.Remove(name, out var kept) is false) return;
            foreach (var data in kept) _replay.Add((name, data));
        }
        _events.Writer.TryWrite((null, default)); // false after the end: then nothing listens anyway
    }

    // A predicate that throws counts as "no match". The dispatcher continues.
    private static bool SafePred(Waiter w, JsonElement data)
    {
        try { return w.Pred(data); }
        catch (Exception e) { Console.Error.WriteLine($"waitFor predicate for \"{w.Name}\" threw: {e.Message}"); return false; }
    }

    /// <summary>Send an event: 42["name", data]. With no data, send no payload.</summary>
    public Task EmitAsync(string name, object? data = null)
    {
        object[] args = data is null ? [name] : [name, data];
        return SendRawAsync("42" + JsonSerializer.Serialize(args));
    }

    /// <summary>Call handler(data) for each event called name from now on.</summary>
    public void On(string name, Action<JsonElement> handler)
    {
        lock (_lock)
        {
            if (!_handlers.TryGetValue(name, out var list)) _handlers[name] = list = new();
            list.Add(handler);
        }
        Subscribed(name);
    }

    /// <summary>
    /// The payload of the next event called name for which pred(data) is
    /// true. Throws TimeoutException after timeout (default 10 s), or
    /// WebSocketException if the socket closes first. The call registers
    /// the waiter immediately. Thus you can call it, then emit, then await
    /// the task. When the task completes, the handlers of the same event
    /// have already run.
    /// </summary>
    public Task<JsonElement> WaitForAsync(string name, Func<JsonElement, bool>? pred = null, TimeSpan? timeout = null)
    {
        // RunContinuationsAsynchronously: your code after the await must not
        // run on the dispatcher. There it would hold back each later event, and
        // a wait for the next reply would wait for itself.
        var result = new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);
        var waiter = new Waiter(name, pred ?? (_ => true), result);
        lock (_lock)
        {
            if (_closed) throw new WebSocketException("socket closed");
            _waiters.Add(waiter);
        }

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
        Subscribed(name);
        return result.Task;
    }

    private async Task CloseOutputAsync()
    {
        await _sendLock.WaitAsync();
        try
        {
            if (_ws.State is WebSocketState.Open or WebSocketState.CloseReceived)
                await _ws.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "", CancellationToken.None);
        }
        finally { _sendLock.Release(); }
    }

    /// <summary>
    /// Disconnect correctly: Socket.IO disconnect, then a normal WebSocket close.
    /// Returns after 5 s at most, also when the server does not answer.
    /// </summary>
    public async Task CloseAsync()
    {
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
    }

    private async Task CloseCleanlyAsync()
    {
        try { await SendRawAsync("41"); } catch (WebSocketException) { } // the connection is already gone
        await CloseOutputAsync();
        await Completion; // the reader sees the close of the server; the dispatcher ends
    }
}
