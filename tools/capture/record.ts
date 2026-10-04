// record.ts: records every Socket.IO frame in and out of every socket of this
// process, into one JSONL file (captures/<date>/<run>.jsonl, git-ignored).
//
// How: before the first AlSocket.connect(), install() replaces the global
// WebSocket class with a subclass that writes each frame down and then does
// what the original does. AlSocket (course/ts/albot/alsocket.ts) is not
// changed; it only ever sees the original behavior. The tap is installed once
// per process.
//
// One line per record. Kinds of record:
//   {"k":"frame","t":ISO,"ms":epoch ms,"char":"SETYMage","dir":"in"|"out","event":"name","data":payload}
//       one Socket.IO EVENT packet (42[...]). `data` is absent when the packet had no payload.
//       `ack` is the ack id when the packet had one (AL does not use acks; recorded in case).
//   {"k":"eio","t",...,"char","dir","packet":"40"}   Engine.IO/Socket.IO control packets other
//       than ping/pong (open "0{...}", connect "40", close "41", error "44"). Pings and pongs
//       ("2"/"3") are counted, not written: they are noise.
//   {"k":"ws","t",...,"char","what":"open"|"close","code":1000}   the WebSocket itself.
//   {"k":"probe","t",...,"char","probe":"buy.cost","expect":["send/buy/failure/2"],"note":...}
//       written by the probe runner just BEFORE the request(s) of one probe. The matcher in
//       scripts/check-captures.py uses `expect` to tell apart failure rows whose replies look
//       the same (for example two rows that both answer "no_target").
//   {"k":"note","t",...,"text":...}   free text: stage start/end, alerts.
//
// SECRETS. The login token must never reach a file. Two independent guards:
//   1. the outgoing `auth` event's `auth` field is replaced with "<REDACTED>";
//   2. every line is searched for the token text (and for the "<user>-<token>"
//      cookie value) before it is written, and each hit is replaced with
//      "<REDACTED>". So the token cannot leak through any other field either.
import { appendFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

export const REDACTED = "<REDACTED>";

/** A decoded Socket.IO event, as the listeners of Recorder.listen() get it. */
export interface Frame {
  char: string;
  dir: "in" | "out";
  event: string;
  data: unknown;
  ms: number;
}

export class Recorder {
  readonly file: string;
  readonly #secrets: string[]; // texts that must never be written
  #pings = 0; // Engine.IO pings/pongs seen (not written)
  #lines = 0;
  // Listeners for decoded frames: the probe runner uses them to see every reply of a probe,
  // whatever its event name (AlSocket can only listen to one name at a time).
  #listeners = new Set<(f: Frame) => void>();

  constructor(file: string, secrets: string[]) {
    this.file = file;
    // Longest first, so that the cookie value "<user>-<token>" is replaced as a whole.
    this.#secrets = secrets.filter((s) => s && s.length >= 16).sort((a, b) => b.length - a.length);
    mkdirSync(dirname(file), { recursive: true });
  }

  get lines(): number {
    return this.#lines;
  }

  get pings(): number {
    return this.#pings;
  }

  /** Writes one record. The `t` and `ms` timestamps are added here. */
  write(rec: Record<string, unknown>): void {
    const now = Date.now();
    let line = JSON.stringify({ t: new Date(now).toISOString(), ms: now, ...rec });
    for (const s of this.#secrets) line = line.replaceAll(s, REDACTED);
    // Synchronous append: a crash or a kill never loses the frames before it, and the order
    // of lines is the order of events in this one-threaded process.
    appendFileSync(this.file, line + "\n");
    this.#lines++;
  }

  note(text: string, extra: Record<string, unknown> = {}): void {
    this.write({ k: "note", text, ...extra });
  }

  /** Calls `fn` for each decoded frame (in and out) until the returned function is called. */
  listen(fn: (f: Frame) => void): () => void {
    this.#listeners.add(fn);
    return () => this.#listeners.delete(fn);
  }

  /** One raw text frame of a socket. `char` is the label of the socket (the character name). */
  frame(char: string, dir: "in" | "out", packet: string): void {
    if (packet === "2" || packet === "3") {
      this.#pings++;
      return;
    }
    if (packet.startsWith("42")) {
      // 42<ack id?>["event", payload]. The ack id (digits) sits between "42" and "[".
      const open = packet.indexOf("[");
      const ack = packet.slice(2, open);
      let args: unknown[];
      try {
        args = JSON.parse(packet.slice(open)) as unknown[];
      } catch {
        this.write({ k: "eio", char, dir, packet: packet.slice(0, 200), error: "unparsable 42 packet" });
        return;
      }
      const event = String(args[0]);
      const rec: Record<string, unknown> = { k: "frame", char, dir, event };
      if (args.length > 1) rec.data = args[1];
      if (args.length > 2) rec.more = args.slice(2); // AL never sends more than one argument
      if (ack) rec.ack = ack;
      // Guard 1: the auth request carries the token in `auth`.
      if (dir === "out" && event === "auth" && rec.data && typeof rec.data === "object") {
        rec.data = { ...(rec.data as object), auth: REDACTED };
      }
      this.write(rec);
      const f: Frame = { char, dir, event, data: rec.data, ms: Date.now() };
      for (const fn of this.#listeners) {
        try {
          fn(f);
        } catch (err) {
          console.error("frame listener threw:", err);
        }
      }
      return;
    }
    // Other control packets: open (0{...}), connect (40), close (41, 1), errors (44).
    this.write({ k: "eio", char, dir, packet: packet.slice(0, 500) });
  }
}

// The label for the next WebSocket that is constructed. AlSocket.connect() constructs its
// WebSocket synchronously, so: setLabel(name); then call connect. Connects run one at a time.
let nextLabel = "?";
export function setLabel(label: string): void {
  nextLabel = label;
}

let installed = false;

/** Replaces globalThis.WebSocket with a recording subclass. Call before the first connect. */
export function install(rec: Recorder): void {
  if (installed) return;
  installed = true;
  const Original = globalThis.WebSocket;
  class TappedWebSocket extends Original {
    readonly label: string;
    constructor(url: string | URL, protocols?: string | string[]) {
      super(url, protocols);
      const label = nextLabel;
      this.label = label;
      // This listener is added in the constructor, so it runs before AlSocket's own
      // "message" listener: the incoming frame is written before any handler reacts to it
      // (and before any frame that the handler sends).
      this.addEventListener("message", (ev: MessageEvent) => rec.frame(label, "in", String(ev.data)));
      this.addEventListener("open", () => rec.write({ k: "ws", char: label, what: "open" }));
      this.addEventListener("close", (ev: CloseEvent) =>
        rec.write({ k: "ws", char: label, what: "close", code: ev.code, reason: ev.reason }),
      );
    }
    override send(data: string | ArrayBufferLike | Blob | ArrayBufferView): void {
      rec.frame(this.label, "out", String(data));
      super.send(data);
    }
  }
  globalThis.WebSocket = TappedWebSocket as typeof WebSocket;
}
