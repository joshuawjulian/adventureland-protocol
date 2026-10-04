// probe.ts: send one request and collect everything that comes back for it.
//
// A probe is: a "probe" record in the capture (its id and the shape ids that it
// means to exercise), then the request, sent through the character's Budget (so
// the call-cost stays under the server's limit), then a wait while the replies
// come in. The matcher (scripts/check-captures.py) does the real work later; the
// frames collected here are only for the console and for the next step's
// decisions (for example "the buy worked, so the slot of the new item is N").
import type { Frame } from "./record.ts";
import type { Char, Session } from "./session.ts";
import { sleep } from "./session.ts";

export interface ProbeOptions {
  expect?: string[]; // shape ids that this probe means to exercise
  note?: string;
  // Stop waiting when this returns true for an incoming frame (default: a game_response whose
  // `place` is the event, or any bare-string game_response). The tail below still runs.
  until?: (f: Frame) => boolean;
  timeoutMs?: number; // the longest wait for `until` (default 2500)
  tailMs?: number; // the wait after `until` matched, for the late `also` events (default 400)
  raw?: boolean; // send with sock.emit directly (no Budget): only for the events before `auth`
}

export interface ProbeResult {
  frames: Frame[]; // every incoming frame of this character during the wait
  gr: unknown[]; // the game_response payloads among them (hitchhikers too)
}

// The minimum time between two probes of one character, so that probes never come in a burst.
// HARD-CODED: 300 ms is well under any server rate (200 call-cost per 4 s).
const SPACING_MS = 300;
const lastSent = new Map<string, number>();

/** Every `game_response` in a frame: the frame itself, or the hitchhikers of a `player`. */
export function responsesIn(f: Frame): unknown[] {
  if (f.event === "game_response") return [f.data];
  if (f.event === "player" && f.data && typeof f.data === "object") {
    const hh = (f.data as { hitchhikers?: [string, unknown][] }).hitchhikers ?? [];
    return hh.filter(([e]) => e === "game_response").map(([, d]) => d);
  }
  return [];
}

export function codeOf(r: unknown): string {
  if (typeof r === "string") return r;
  if (r && typeof r === "object") return String((r as { response?: unknown }).response);
  return String(r);
}

export async function probe(
  s: Session,
  c: Char,
  id: string,
  event: string,
  payload: unknown,
  opts: ProbeOptions = {},
): Promise<ProbeResult> {
  s.check();
  const wait = (lastSent.get(c.name) ?? 0) + SPACING_MS - Date.now();
  if (wait > 0) await sleep(wait);
  const place = (payload && typeof payload === "object" && (payload as { name?: string }).name && event === "skill")
    ? (payload as { name: string }).name
    : event;
  const until =
    opts.until ??
    ((f: Frame) =>
      responsesIn(f).some((r) => typeof r === "string" || (r as { place?: string })?.place === place));
  const frames: Frame[] = [];
  let matched = false;
  const stop = s.rec.listen((f) => {
    if (f.char !== c.name || f.dir !== "in") return;
    frames.push(f);
    if (!matched && until(f)) matched = true;
  });
  s.rec.write({ k: "probe", char: c.name, probe: id, event, expect: opts.expect ?? [], note: opts.note });
  lastSent.set(c.name, Date.now());
  if (opts.raw) c.m.sock.emit(event, payload);
  else await c.m.budget.emit(event, payload);
  const end = Date.now() + (opts.timeoutMs ?? 2500);
  while (!matched && Date.now() < end && !c.closedReason) await sleep(50);
  await sleep(opts.tailMs ?? 400);
  stop();
  // A handler that throws answers `game_error`, and the server's socket wrapper adds 16
  // call-cost for it (node/server.js, the `catch` of the wrapper). Before `auth` the limit is
  // only 50 per 4 s, so a few throws in a row are a `limitdc`. Wait one full window after each.
  if (frames.some((f) => f.event === "game_error")) await sleep(4200);
  const gr = frames.flatMap(responsesIn);
  const names = [...new Set(frames.map((f) => f.event))].filter((e) => e !== "entities" && e !== "player");
  console.log(`  ${c.name} ${id}: ${event} -> ${gr.map(codeOf).join(", ") || "(no game_response)"}${names.length ? "  [" + names.join(" ") + "]" : ""}`);
  return { frames, gr };
}

/** The first frame of `event` among the results, or undefined. */
export function first<T = unknown>(r: ProbeResult, event: string): T | undefined {
  return r.frames.find((f) => f.event === event)?.data as T | undefined;
}

/** True when a game_response with this code came back. */
export function got(r: ProbeResult, code: string): boolean {
  return r.gr.some((x) => codeOf(x) === code);
}
