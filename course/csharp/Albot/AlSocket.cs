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

    private readonly object _lock = new(); // guards the five fields below
    private readonly Dictionary<string, List<Action<JsonElement>>> _handlers = new();
    private readonly List<Waiter> _waiters = new();
    private readonly Dictionary<string, List<JsonElement>> _early = new(); // events from before the first On/WaitForAsync
    private bool _listening; // true after the first On/WaitForAsync
    private bool _closed;

    // Reader task -> dispatcher task. Because they are separate, a slow
    // handler can't make us miss a ping.
    private readonly Channel<(string Name, JsonElement Data)> _events =
        Channel.CreateUnbounded<(string, JsonElement)>();
    private Task _dispatcher = Task.CompletedTask;

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

    // Gives events to handlers and waiters, in arrival order.
    private async Task Dispatch()
    {
        await foreach (var (name, data) in _events.Reader.ReadAllAsync())
            Deliver(name, data);
        lock (_lock)
        {
            _closed = true;
            foreach (var w in _waiters) w.Result.TrySetException(new WebSocketException("socket closed"));
            _waiters.Clear();
        }
    }

    // Gives one event to the handlers and waiters for its name.
    private void Deliver(string name, JsonElement data)
    {
        List<Action<JsonElement>> handlers;
        lock (_lock)
        {
            handlers = _handlers.TryGetValue(name, out var list) ? new(list) : new();
            foreach (var w in _waiters.Where(w => w.Name == name && SafePred(w, data)).ToList())
            {
                _waiters.Remove(w);
                w.Result.TrySetResult(data);
            }
        }
        foreach (var handler in handlers)
        {
            try { handler(data); }
            catch (Exception e) { Console.Error.WriteLine($"handler for \"{name}\" threw: {e}"); } // one bad handler must not stop the socket
        }
    }

    // Each On/WaitForAsync calls this. The server sends "welcome" immediately
    // after the handshake, before your code can call WaitForAsync("welcome").
    // AlSocket keeps all events from before the first On/WaitForAsync. The
    // first subscriber for an event name gets the kept events for that name.
    // They run on the thread that called On/WaitForAsync, one time.
    private void Subscribed(string name)
    {
        List<JsonElement>? kept;
        lock (_lock)
        {
            _listening = true;
            if (_early.Remove(name, out kept) is false) return;
        }
        foreach (var data in kept!) Deliver(name, data);
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
    /// the task.
    /// </summary>
    public Task<JsonElement> WaitForAsync(string name, Func<JsonElement, bool>? pred = null, TimeSpan? timeout = null)
    {
        // RunContinuationsAsynchronously: your code after the await must not
        // run inside the lock of the dispatcher.
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
        result.Task.ContinueWith(_ => timer.Dispose());
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

    /// <summary>Disconnect correctly: Socket.IO disconnect, then a normal WebSocket close.</summary>
    public async Task CloseAsync()
    {
        try { await SendRawAsync("41"); } catch (WebSocketException) { } // the connection is already gone
        await CloseOutputAsync();
        await Completion; // the reader sees the close of the server; the dispatcher ends
    }
}
