// http.js: the HTTP side of the test server: the API (/api/<method>), the game
// data (/data.js), the hub page (/hub), and the test-control endpoints.
//
// The live API is common_engine/handlers.js (vendor/common_engine) with the
// methods of vendor/adventureland_mongodb/api.js. Every reply has status 200,
// also for errors, with `Content-Type: application/json; charset=utf-8`
// (handlers.js:28-32; Express adds "; charset=utf-8"). Errors are
// {failed: true, reason, ...}. Extra replies go in `infs`.

import { ACCOUNT } from "./accounts.js";

const JSON_TYPE = "application/json; charset=utf-8";

// The methods that the test server knows, with the live field rules
// (api.js:2150-2260, REF). P: POST only. U: needs the session cookie.
const REF = {
  signup_or_login: {
    P: true,
    email: { type: "email" },
    password: { type: "string", minimum: 1 },
    only_login: { type: "boolean", optional: true },
    only_signup: { type: "boolean", optional: true },
    mobile: { type: "boolean", optional: true },
  },
  servers_and_characters: { P: true, U: true },
  create_character: {
    P: true,
    U: true,
    name: { type: "string" },
    char: { type: "string" },
    look: { type: "any", optional: true },
  },
  get_servers: {},
};

// adventure_functions.js:256-275 (purify_email), the checks only.
function purifyEmail(email) {
  email = email.replace(/[ \t\n\r]/g, "").toLowerCase();
  const parts = email.split("@");
  if (parts.length !== 2) throw new Error("invalid_email");
  const domain = parts[1].split(".");
  if (domain.length < 2 || domain[1].length < 2) throw new Error("invalid_email");
  return email;
}

function readBody(req) {
  return new Promise((resolve) => {
    let body = "";
    req.on("data", (c) => {
      body += c;
      if (body.length > 1e6) req.destroy(); // a test server needs no big bodies
    });
    req.on("end", () => resolve(body));
    req.on("error", () => resolve(""));
  });
}

// The request arguments: the JSON body (ALClient posts JSON), or a form body,
// or the URL query for GET.
function parseArgs(req, url, body) {
  if (req.method !== "POST") return Object.fromEntries(url.searchParams);
  const type = req.headers["content-type"] || "";
  if (type.includes("application/x-www-form-urlencoded")) return Object.fromEntries(new URLSearchParams(body));
  if (!body.trim()) return {};
  try {
    const parsed = JSON.parse(body);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return null;
  }
}

function send(res, status, type, body, headers = {}) {
  res.writeHead(status, Object.assign({ "Content-Type": type, "Content-Length": Buffer.byteLength(body) }, headers));
  res.end(body);
}

function sendJson(res, json, infs, headers) {
  if (infs && infs.length) json.infs = infs; // handlers.js:30
  send(res, 200, JSON_TYPE, JSON.stringify(json), headers);
}

export function makeHttpHandler(ctx) {
  // The data.js text is made once: G does not change while the server runs.
  const dataJs = "var G=" + JSON.stringify(ctx.G) + ";\n"; // web_assets.js:52
  const stats = ctx.stats;

  // The game servers in the live order (EU, US, ASIA). `address` is the Host
  // header of the request, so that the URLs work from localhost and from
  // another Docker container (COURSE.md).
  function serverList(req) {
    const host = req.headers.host || `localhost:${ctx.settings.port}`;
    return ctx.worlds.map((w) => ({ w, address: host }));
  }

  async function api(req, res, url, method) {
    stats.api++;
    const body = await readBody(req);
    const query = parseArgs(req, url, body);
    const infs = [];
    const ref = REF[method];
    // handlers.js:34-140: the generic checks of the live dispatcher.
    if (!ref) return sendJson(res, { failed: true, reason: "invalid_call", name: method });
    if (query === null) return sendJson(res, { failed: true, reason: "exception" });
    if (query.F) return sendJson(res, { failed: true, reason: "invalid_field", field: "F" });
    if (ref.P && req.method !== "POST") return sendJson(res, { failed: true, reason: "invalid_method", method: req.method, needed: "POST" });
    let user = null;
    if (ref.U) {
      user = ctx.accounts.userFromCookie(req.headers.cookie);
      if (!user) return sendJson(res, { failed: true, reason: "not_logged_in", method: req.method });
    }
    for (const q of Object.keys(query)) {
      const rule = ref[q];
      if (!rule || ["P", "U", "F"].includes(q)) return sendJson(res, { failed: true, reason: "invalid_field", field: q });
      if (rule.type === "string") {
        query[q] = "" + query[q];
        if (rule.minimum && query[q].length < rule.minimum) return sendJson(res, { failed: true, reason: "invalid_field", field: q, minimum_length: rule.minimum });
      }
      if (rule.type === "email") {
        try {
          query[q] = purifyEmail("" + query[q]);
        } catch {
          return sendJson(res, { failed: true, reason: "invalid_field", field: q, not_email: true });
        }
      }
      if (rule.type === "boolean" && query[q] !== true && query[q] !== false) return sendJson(res, { failed: true, reason: "invalid_field", field: q, must_be: "boolean" });
    }
    for (const q in ref) {
      if (["P", "U", "F"].includes(q)) continue;
      if (!ref[q].optional && query[q] === undefined) return sendJson(res, { failed: true, reason: "missing_field", field: q });
    }

    if (method === "signup_or_login") {
      // api.js:84-133. The web cannot sign up: without only_login the live
      // server answers "cant_signup_on_web" (api.js:93), even for a known email.
      if (!query.only_login) return sendJson(res, { failed: true, reason: "cant_signup_on_web" });
      if (query.email !== ACCOUNT.email) return sendJson(res, { failed: true, reason: "email_not_found" });
      if (query.password !== ACCOUNT.password) {
        infs.push({ type: "eval", code: "$('.passwordui').show()" });
        return sendJson(res, { failed: true, reason: "wrong_password" }, infs);
      }
      stats.logins++;
      // Live makes a new auth on each login (get_new_auth); the test server
      // always gives the fixed one, so that AL_AUTH stays valid.
      const cookie = `auth=${ACCOUNT.user}-${ACCOUNT.auth}; Max-Age=157680000; Path=/; SameSite=Lax`;
      infs.push({ type: "message", message: "Logged In!" }); // en/server.js:44
      // Live also adds {type: "content", html: <the character selection page>}; left out.
      return sendJson(res, { success: true, user: ACCOUNT.user, auth: ACCOUNT.auth, language: "en" }, infs, { "Set-Cookie": cookie });
    }

    if (method === "servers_and_characters") {
      // api.js:451-472 and adventure_functions.js:761-776 (servers_to_client)
      const servers = serverList(req).map(({ w, address }) => ({
        name: w.name,
        region: w.region,
        players: Object.keys(w.players).length,
        key: w.serverId,
        address,
        path: w.path,
        msgpack_path: w.msgpackPath,
      }));
      const tutorial = { step: 0, completed: [], completed_tasks: [], pending: [], completed_lessons: [], onboarding_finished: true, finished: true, task: false, progress: 100 };
      infs.push({
        type: "servers_and_characters",
        servers,
        characters: ctx.accounts.characterList(),
        tutorial,
        merchant_tutorial: tutorial,
        code_list: {},
        mail: 0,
        rewards: [],
      });
      return sendJson(res, { success: true }, infs);
    }

    if (method === "create_character") {
      // api.js:474-584
      const r = ctx.accounts.createCharacter(query.name, query.char);
      if (r.failed) return sendJson(res, r);
      stats.created++;
      infs.push({ type: "success", message: `${r.name} is alive!` }); // en/server.js:36
      return sendJson(res, { success: true }, infs);
    }

    if (method === "get_servers") {
      // api.js:884-900: a different field set from servers_and_characters.
      const servers = serverList(req).map(({ w, address }) => ({
        address,
        path: w.path,
        msgpack_path: w.msgpackPath,
        region: w.region,
        name: w.name,
        pvp: false,
        gameplay: "normal",
      }));
      return sendJson(res, { success: true, servers });
    }
  }

  return async function handle(req, res) {
    stats.http++;
    const url = new URL(req.url, "http://localhost");
    const path = url.pathname;
    try {
      const m = /^\/api\/([^/]+)\/?$/.exec(path);
      if (m) return await api(req, res, url, m[1]);
      if (path === "/data.js") {
        // web_assets.js:24-35, 52: "var G=<json>;\n" as application/javascript.
        stats.data_js++;
        return send(res, 200, "application/javascript; charset=utf-8", dataJs, { "Cache-Control": "public, no-cache" });
      }
      if (path === "/hub") {
        // main.js:168-195 renders htmls/comm.html; htmls/base_script.html:32
        // has `var VERSION='<version>'`. This page has that line only.
        const html = `<!doctype html>\n<html><head><meta charset="utf-8"><title>Adventure Land test server</title>\n<script>\n\tvar VERSION='${ctx.G.version}';\n</script></head>\n<body><p>A fake Adventure Land for the course. It is not the game.</p></body></html>\n`;
        return send(res, 200, "text/html; charset=utf-8", html, { "Cache-Control": "no-store" });
      }
      if (path === "/test/reset" && req.method === "POST") {
        await readBody(req);
        ctx.resetAll();
        return sendJson(res, { success: true });
      }
      // /test/drop and /test/jail: now, or with after_start_ms=N, N ms after
      // the next `start` of that character (armed: the program can start later).
      if ((path === "/test/drop" || path === "/test/jail") && req.method === "POST") {
        await readBody(req);
        const action = path.slice(6); // "drop" or "jail"
        const name = url.searchParams.get("character") || "";
        const after = url.searchParams.get("after_start_ms");
        if (after !== null) {
          if (!name) return sendJson(res, { failed: true, reason: "character is required with after_start_ms" });
          ctx.armed.push({ name, action, ms: Number(after) || 0 });
          return sendJson(res, { success: true, armed: true });
        }
        if (action === "jail") {
          let jailed = 0;
          for (const w of ctx.worlds) jailed += w.jailCharacter(name);
          return sendJson(res, { success: true, jailed });
        }
        let dropped = 0;
        for (const w of ctx.worlds) dropped += w.dropCharacter(name);
        stats.drops += dropped;
        return sendJson(res, { success: true, dropped });
      }
      if (path === "/test/stats" && req.method === "GET") {
        return sendJson(res, { ...stats, servers: ctx.worlds.map((w) => w.summary()) });
      }
      // Paths of the Socket.IO servers are answered by engine.io before this.
      send(res, 404, "text/plain; charset=utf-8", "Not found\n");
    } catch (e) {
      console.log(`HTTP ${req.method} ${req.url}: ${e && e.stack}`);
      stats.errors++;
      if (!res.headersSent) sendJson(res, { failed: true, reason: "exception" });
    }
  };
}
