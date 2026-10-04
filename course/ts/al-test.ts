// al-test.ts: send AlSocket through the handshake of a game session on the
// test server: welcome, loaded, auth, start, 3 s with no activity, ping_trig.
// It uses only albot/alsocket.ts. Node.js 22.18+, no packages.
// Run: node al-test.ts   (the test server must run; AL_WS_URL changes the URL)
import { AlSocket } from "./albot/alsocket.ts";

// Only the fields that this test reads. The real payloads have many more.
interface Welcome { region: string; name: string; version: number }
interface Entities { type: "all" | "xy"; monsters: { id: string; type: string }[] }
interface Start { id: string; map: string; x: number; y: number } // `id` is the name
interface PingAck { id: string }

// The default is the first server of the test server ("EU I").
const url = process.env.AL_WS_URL || "ws://localhost:8022/ws1/?EIO=4&transport=websocket";

const sock = await AlSocket.connect(url);
console.log(`connected to ${url}`);
sock.on<unknown>("game_error", (e) => console.log("game_error:", JSON.stringify(e)));
sock.on<string>("disconnect", (reason) => console.log(`disconnect: ${reason}`));

// 1. The server sends "welcome" to each new socket.
const welcome = await sock.waitFor<Welcome>("welcome");
console.log(`welcome: ${welcome.region} ${welcome.name}, version ${welcome.version}`);

// 2. Send "loaded". The reply is one full "entities" view (type "all").
//    Register the wait BEFORE the emit, so that a fast reply cannot come first.
const view = sock.waitFor<Entities>("entities", (d) => d.type === "all");
sock.emit("loaded", { success: 1, width: 1920, height: 1080, scale: 2 });
console.log(`entities: ${(await view).monsters.length} monster(s)`);

// 3. Log in the test character. HARD-CODED: the fixed account of the test
//    server (course/test-server/accounts.js). Part 1 has no login code yet;
//    Part 2 reads the login from AL_AUTH. This token works on the test server only.
const started = sock.waitFor<Start>("start");
sock.emit("auth", {
  user: "US_tester",
  auth: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  character: "CH_tester",
  no_html: "1",
  passphrase: "",
});
const me = await started;
console.log(`start: ${me.id} on ${me.map} at ${Math.round(me.x)},${Math.round(me.y)}`);

// 4. Do nothing for 3 s. The server sends pings in this time. If our pong
//    does not work, the server drops us and the next step fails.
await new Promise((resolve) => setTimeout(resolve, 3000));
const ack = sock.waitFor<PingAck>("ping_ack", (d) => d.id === "42");
sock.emit("ping_trig", { id: "42" });
console.log(`ping_ack after 3 s idle: ${(await ack).id}`);

console.log("OK");
sock.close(); // then AlSocket's "disconnect" handler prints the reason
