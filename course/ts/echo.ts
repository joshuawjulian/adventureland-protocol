// echo.ts: open a WebSocket, send one text message, print the reply, close.
// Standalone: it uses no file of the albot library. Node.js 22.18+ has a global
// WebSocket, so it needs no packages.
// Run: node echo.ts   (the test server has an echo endpoint at ws://localhost:8022/echo)

const url = process.env.AL_ECHO_URL || "ws://localhost:8022/echo";
const ws = new WebSocket(url);

// Callbacks: the runtime calls them when something happens on the socket.
ws.addEventListener("open", () => {
  console.log("connected");
  ws.send("hello"); // one text frame
});
ws.addEventListener("message", (msg: MessageEvent) => {
  console.log(`received: ${msg.data}`); // an echo server sends the same text back
  ws.close(1000); // 1000 = a normal close
});
ws.addEventListener("close", () => console.log("closed"));
// An "error" always comes before a "close". Set a failure exit status for it.
ws.addEventListener("error", () => {
  console.error(`could not use ${url}`);
  process.exitCode = 1;
});
