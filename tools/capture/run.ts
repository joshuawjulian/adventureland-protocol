// run.ts: the entry point. Runs one stage of the probe plan with recording on.
//
//   node run.ts <stage> [Name,Name,...]
//
// Normally started by run.py (docker node:22, credentials mounted read-only).
// Writes captures/<YYYY-MM-DD>/<HHMMSS>-<stage>.jsonl under the repo root.
// Ctrl-C (or SIGTERM) stops cleanly: closes every socket, then exits.
import { join } from "node:path";
import { install, Recorder } from "./record.ts";
import { readCredentials, Session, ALLOWED } from "./session.ts";
import { STAGES } from "./probes.ts";

const stage = process.argv[2];
if (!stage || !STAGES[stage]) {
  console.log(`usage: node run.ts <stage> [Name,...]\nstages: ${Object.keys(STAGES).join(", ")}`);
  process.exit(2);
}
const def = STAGES[stage];
const names = process.argv[3] ? process.argv[3].split(",") : def.chars ?? ALLOWED;

const auth = readCredentials();
const now = new Date();
const day = now.toISOString().slice(0, 10);
const hms = now.toISOString().slice(11, 19).replaceAll(":", "");
const root = process.env.CAPTURE_ROOT || join(import.meta.dirname, "..", "..");
const file = join(root, "captures", day, `${hms}-${stage}.jsonl`);
// The secrets: the token alone, and the cookie value "<user>-<token>".
const rec = new Recorder(file, [auth.auth, `${auth.user}-${auth.auth}`]);
install(rec);
console.log(`recording to captures/${day}/${hms}-${stage}.jsonl`);

const s = new Session(rec, auth);
let stopping = false;
const finish = async (code: number) => {
  if (stopping) return;
  stopping = true;
  await s.stop();
  console.log(`wrote ${rec.lines} records`);
  process.exit(code);
};
process.on("SIGINT", () => { s.abort("SIGINT"); void finish(130); });
process.on("SIGTERM", () => { s.abort("SIGTERM"); void finish(143); });

try {
  rec.note(`stage ${stage} start`, { stage, chars: names });
  await s.init();
  if (def.connect !== false) await s.connectAll(names);
  await def.run(s);
  rec.note(`stage ${stage} end`, { stage });
  await finish(s.abortReason ? 1 : 0);
} catch (err) {
  console.log(`stage ${stage} stopped: ${err instanceof Error ? err.message : String(err)}`);
  if (err instanceof Error && err.stack) console.log(err.stack.split("\n").slice(1, 4).join("\n"));
  rec.note(`stage ${stage} failed: ${String(err)}`);
  await finish(1);
}
