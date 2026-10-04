// al-test.js: send AlSocket through the whole session on the local test
// server: welcome, loaded, auth, 3 s with no activity, then a ping_trig.
// Uses albot/alsocket.js only. Node.js 22.18+.   Run: node al-test.js
import { AlSocket } from "./albot/alsocket.js";

// The full WebSocket URL of a game server (Part 2 gets it from the server list).
const url = process.env.AL_WS_URL || "ws://localhost:8022/ws1/?EIO=4&transport=websocket";

const sock = await AlSocket.connect(url);
console.log("connected to", url);
sock.on("game_error", (msg) => console.log("game_error:", msg));
sock.on("disconnect", (reason) => console.log("disconnect:", reason));

// 1. The server sends "welcome" to each new socket.
const welcome = await sock.waitFor("welcome");
console.log(`welcome: ${welcome.region} ${welcome.name}, version ${welcome.version}`);

// 2. Send "loaded". The answer is one full "entities" snapshot.
//    Register the wait BEFORE the emit, so that a fast answer cannot pass first.
const snapshot = sock.waitFor("entities", (d) => d.type === "all");
sock.emit("loaded", { success: 1, width: 1920, height: 1080, scale: 2 });
console.log(`entities: ${(await snapshot).monsters.length} monster(s)`);

// 3. Log in a character. HARD-CODED: the fixed account of the test server
//    (it exists only there). Part 1 has no login code yet; Part 2 reads AL_AUTH.
const started = sock.waitFor("start");
sock.emit("auth", {
  user: "US_tester",
  auth: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  character: "CH_tester", // the id, not the name
  no_html: "1",
  passphrase: "",
});
const me = await started;
console.log(`start: ${me.id} on ${me.map} at ${Math.round(me.x)},${Math.round(me.y)}`);

// 4. Do nothing for 3 s. The server sends pings during this time. If our
//    pong does not work, the server drops us and the next step fails.
await new Promise((resolve) => setTimeout(resolve, 3000));
const ack = sock.waitFor("ping_ack", (d) => d.id === "42");
sock.emit("ping_trig", { id: "42" });
console.log("ping_ack after 3 s idle:", (await ack).id);

sock.close();
console.log("OK"); // "disconnect: ..." follows when the close is complete
