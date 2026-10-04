// echo.js: open a WebSocket, send one text message, read the reply.
// Standalone: it uses no file of the library. Node.js 22.18+ (WebSocket is built in).
// Run: node echo.js   (AL_ECHO_URL changes the server; default: the test server)
const url = process.env.AL_ECHO_URL || "ws://localhost:8022/echo";
const ws = new WebSocket(url);

// Callbacks: the runtime calls them when something happens.
ws.addEventListener("open", () => {
  console.log("connected");
  ws.send("hello"); // one text frame
});
ws.addEventListener("message", (msg) => {
  console.log("received:", msg.data);
  ws.close(1000); // 1000 = normal closure
});
ws.addEventListener("error", () => {
  process.exitCode = 1; // a failure; the "close" event follows
});
ws.addEventListener("close", () => console.log("closed"));
