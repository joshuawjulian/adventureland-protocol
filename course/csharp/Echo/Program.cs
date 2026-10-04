// Echo/Program.cs: open a WebSocket, send one text message, read the reply,
// close. Standalone: it does not use the albot library.
// .NET 8, no packages.   Run (in course/csharp): dotnet run --project Echo
// AL_ECHO_URL: a plain WebSocket echo server (default: the one of the test server).
using System.Net.WebSockets;
using System.Text;

var url = Environment.GetEnvironmentVariable("AL_ECHO_URL") is { Length: > 0 } u ? u : "ws://localhost:8022/echo";
using var ws = new ClientWebSocket();
await ws.ConnectAsync(new Uri(url), CancellationToken.None);
Console.WriteLine("connected");

// One text frame. "true": this frame is the end of the message.
await ws.SendAsync(Encoding.UTF8.GetBytes("hello"), WebSocketMessageType.Text, true, CancellationToken.None);

// The await gives the thread back to the runtime until a message arrives.
// A small buffer is enough here; AlSocket shows how to join long messages.
var buffer = new byte[4096];
var result = await ws.ReceiveAsync(buffer, CancellationToken.None);
Console.WriteLine($"received: {Encoding.UTF8.GetString(buffer, 0, result.Count)}");

// A normal close (code 1000): we send a close frame and wait for the close frame of the server.
await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "", CancellationToken.None);
Console.WriteLine("closed");
