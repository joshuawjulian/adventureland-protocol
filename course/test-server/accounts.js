// accounts.js: the "database" of the test server: one account and its
// characters. The live game keeps these in MongoDB; here they live in memory
// and POST /test/reset puts them back to the start.
//
// Fixed test data (docs/COURSE.md, "The local test server"). Programs and
// scripts/check-course.py rely on these exact values.

// The one test account. Not a secret: it exists only on this server.
export const ACCOUNT = {
  email: "tester@example.com",
  password: "test-password",
  user: "US_tester",
  auth: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
};

// The four fixed characters, in the order of the character list.
// All start on main at spawn 5 (-87, 673), level 1, like a new live character
// (api.js:497: main spawn on_death[1]). From there the goos are in view (vision is
// +-700 px in x and +-500 px in y) and a straight line to their box is clear of walls.
const FIXED = [
  // Tester starts at 40 % hp, so that a first program must heal (COURSE.md).
  { id: "CH_tester", name: "Tester", type: "warrior", hpRatio: 0.4 },
  { id: "CH_healer", name: "Healer", type: "priest" },
  { id: "CH_archer", name: "Archer", type: "ranger" },
  { id: "CH_merchy", name: "Merchy", type: "merchant" },
];

// Not live: live characters start with 0 gold. 10,000 gold lets the "supplies"
// and "gear-up" programs buy potions, a scroll0 (1,000) and a cscroll0 (6,400)
// before the first kill.
const START_GOLD = 10000;
// COURSE.md: hpot0 x 10 and mpot0 x 10. (Live create_character gives 200 of
// each with gift: 1, api.js:538-541. We keep `gift: 1`, so they sell for 1 gold
// as live gift items do, js/old_common_functions.js:786.)
const START_POTIONS = 10;

// Live accounts that signed up on the web get 5 character slots
// (adventure_functions.js:164-168). The fixed account uses 4, so one
// create_character works and the next fails with "reached_character_limit".
const CHARACTER_SLOTS = 5;

// adventure_functions.js:452: the characters that a name may use.
const NAME_CHARACTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_";
// design/game_design.js:1: the classes that create_character accepts.
const CHARACTER_TYPES = ["warrior", "paladin", "mage", "priest", "rogue", "ranger", "merchant"];

export class Accounts {
  constructor(G) {
    this.G = G;
    this.reset();
  }

  // Everything back to the start: the four characters, the bank, the session.
  reset() {
    this.user = {
      id: ACCOUNT.user,
      email: ACCOUNT.email,
      password: ACCOUNT.password,
      auths: [ACCOUNT.auth],
      cash: 0,
      // The bank of the account (live: user.info.gold and items0..items47).
      // Live signup gives 1,000 gold to the bank (api.js:168).
      bank: { gold: 1000, items0: [], items1: [] },
    };
    this.characters = []; // in list order
    for (const f of FIXED) {
      const main = this.G.maps.main;
      const spawn = main.spawns[main.on_death ? main.on_death[1] : 0];
      this.characters.push(this.newRecord(f.id, f.name, f.type, { x: spawn[0], y: spawn[1], potions: START_POTIONS, gold: START_GOLD, hpRatio: f.hpRatio }));
    }
  }

  // A character record, as the live database keeps it (api.js:510-560).
  newRecord(id, name, type, opts) {
    const cls = this.G.classes[type];
    const look = (cls.looks && cls.looks[0]) || [type, {}];
    // Starter gear: the class base_slots plus a helmet and shoes (api.js:542, 554-555).
    const slots = JSON.parse(JSON.stringify(cls.base_slots || {}));
    slots.helmet = { name: "helmet", level: 0, gift: 1 };
    slots.shoes = { name: "shoes", level: 0, gift: 1 };
    return {
      id,
      name,
      type,
      level: 1,
      xp: 0,
      gold: opts.gold,
      items: [
        { name: "hpot0", q: opts.potions, gift: 1 },
        { name: "mpot0", q: opts.potions, gift: 1 },
      ],
      slots,
      skin: look[0],
      cx: look[1] || {},
      map: "main",
      in: "main",
      x: opts.x,
      y: opts.y,
      hp: null, // null: full hp at the first login (then hpRatio applies)
      mp: null,
      hpRatio: opts.hpRatio || 1,
      rip: false,
      // p.first: the live "first drop" bonus (node/server.js:2428-2435). The
      // first chest of the character has 100,000 more gold, 3 ringsj, an hpbelt
      // and a gem0. Live sets it for the first character of a new player
      // (node/server.js:16252-16278). The test characters all have it, so that
      // chests with items, loot_no_space and compound can be tested at once.
      p: { first: opts.first !== false, ugrace: {}, ograce: 0 },
      server: "", // "SR_EUI" while online (or while the save after a disconnect runs)
      online: false,
      last_online: new Date(),
      created: new Date(),
    };
  }

  get(id) {
    return this.characters.find((c) => c.id === id) || null;
  }

  getByName(name) {
    const n = String(name).toLowerCase(); // simplify_name (adventure_functions.js:94-96)
    return this.characters.find((c) => c.name.toLowerCase() === n) || null;
  }

  // The session cookie "auth=<user>-<auth>" (adventure_functions.js:371-385):
  // split at "-", the user id gets "US_" if it has none.
  userFromCookie(cookieHeader) {
    if (!cookieHeader) return null;
    const m = /(?:^|;\s*)auth=([^;]*)/.exec(cookieHeader);
    if (!m) return null;
    const parts = decodeURIComponent(m[1]).replace(/"/g, "").split("-");
    let id = parts[0];
    if (id && !id.startsWith("US_")) id = "US_" + id;
    if (id !== this.user.id || !this.user.auths.includes(parts[1])) return null;
    return this.user;
  }

  // adventure_functions.js:821-843 (character_to_dict)
  characterToDict(c) {
    const data = { id: c.id, name: c.name, level: c.level, type: c.type, online: 0 };
    if (c.online) {
      data.online = Date.now() - c.last_online.getTime(); // ms since the login
      data.server = c.server;
      data.secret = "12"; // live: a per-login secret for the browser reconnect; unused here
    }
    if (c.rip) data.rip = c.rip;
    data.skin = c.skin;
    data.cx = c.cx;
    data.in = c.in;
    data.map = c.map;
    data.x = c.x;
    data.y = c.y;
    return data;
  }

  // adventure_functions.js:845-855: online characters first.
  characterList() {
    const list = this.characters.map((c) => this.characterToDict(c));
    list.sort((a, b) => (b.online ? 1 : 0) - (a.online ? 1 : 0));
    return list;
  }

  // api.js:474-584 (create_character_api), without the shells and IP limits.
  createCharacter(name, ctype) {
    if (!ctype || !CHARACTER_TYPES.includes(ctype) || !this.G.classes[ctype]) return { failed: true, reason: "character_type_not_allowed" };
    if (!name) return { failed: true, reason: "please_enter_a_name" };
    name = name.replace(/ /g, "").replace(/\t/g, "");
    // is_name_allowed (api.js:24-31): 4 to 12 characters of NAME_CHARACTERS.
    if (name.length < 4 || name.length > 12 || [...name].some((ch) => !NAME_CHARACTERS.includes(ch))) return { failed: true, reason: "invalid_name" };
    if (this.getByName(name)) return { failed: true, reason: "name_used" };
    if (this.characters.length >= CHARACTER_SLOTS) return { failed: true, reason: "reached_character_limit" };
    // A new live character starts at main spawn on_death[1] (spawn 5, near the
    // goos), with 200 hpot0/mpot0 and 0 gold (api.js:497, 538-541).
    const main = this.G.maps.main;
    const spawn = main.spawns[main.on_death ? main.on_death[1] : 0];
    const id = "CH_" + name.toLowerCase();
    this.characters.push(this.newRecord(id, name, ctype, { x: spawn[0], y: spawn[1], potions: 200, gold: 0, first: false }));
    return { success: true, name };
  }
}
