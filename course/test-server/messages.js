// messages.js: the live server's text messages, for the few phrases that the
// test server sends.
//
// The live server sends game_log, game_error, party_update and some
// game_response payloads as objects from localization.message()
// (languages/index.js:256-258):
//   {...fields, message: "<English text>", phrase: "<id>", phrase_args: {...}}
// The English texts below are copied from languages/en/server.js.

const PHRASES = {
  "server.game_log.authorization_in_progress": "Authorization in progress.", // en/server.js:126
  "server.game_error.authentication_failed": "Failed: {reason}", // en/server.js:659
  "server.game_error.capacity": "Can't accept more than {count} players at this time", // en/server.js:657
  "server.game_log.line_violation_detected": "Line violation detected", // en/server.js:210
  "server.game_log.make_sure_you_only_move_with_the_built_in_move_function":
    "Make sure you only move with the built-in move function", // en/server.js:236
  "server.game_log.gold": "{amount} gold", // en/server.js:190
  "server.game_log.invited_to_party": "Invited {invited} to party", // en/server.js:196
  "server.game_log.left_the_party": "Left the party", // en/server.js:206
  "server.game_log.left_your_current_party": "Left your current party", // en/server.js:208
  "server.game_log.unequip_your_offhand_item_to_use_this_two_handed_weapon":
    "Unequip your offhand item to use this two-handed weapon.", // en/server.js:296
  "server.party.joined": "{player} joined the party", // en/server.js:8
  "server.party.joined_with_invite": "{player} joined the party with {inviter}'s invite", // en/server.js:10
  "server.party.left": "{player} left the party", // en/server.js:12
  "server.item.found.a": "Found a {item}", // en/server.js:463
  "server.item.found.an": "Found an {item}",
  "server.item.found.many": "Found {item} [x{quantity}]",
  "server.item.named_found.a": "{player} found a {item}", // en/server.js:499
  "server.item.named_found.an": "{player} found an {item}",
  "server.item.named_found.many": "{player} found {item} [x{quantity}]",
  "server.kill.you.a": "You killed a {monster}", // en/server.js:555
  "server.kill.you.an": "You killed an {monster}",
  "server.kill.you.the": "You killed the {monster}",
  "server.kill.you.none": "You killed {monster}",
  "server.kill.player.a": "{player} killed a {monster}", // en/server.js:547
  "server.kill.player.an": "{player} killed an {monster}",
  "server.kill.player.the": "{player} killed the {monster}",
  "server.kill.player.none": "{player} killed {monster}",
};

// languages/index.js:256-258
export function message(id, params = {}, fields = {}) {
  const text = (PHRASES[id] || id).replace(/\{(\w+)\}/g, (all, key) => (key in params ? String(params[key]) : all));
  return Object.assign({}, fields, { message: text, phrase: id, phrase_args: params || {} });
}

function startsWithAn(name) {
  return /^[aeiou]/i.test(name);
}

// node/server_functions.js:4576-4589 (item_message)
export function itemMessage(template, item, G, params = {}, fields = {}) {
  const def = G.items[item.name];
  const form = item.q && item.q > 1 ? "many" : startsWithAn(def.name) ? "an" : "a";
  let name = def.name;
  if (form !== "many" && item.level) name += " +" + item.level;
  return message(template + "." + form, Object.assign({}, params, { item: name, quantity: item.q || 1 }), fields);
}

// node/server_functions.js:4591-4600 (kill_message)
export function killMessage(name, type, firstPerson, G) {
  const monster = G.monsters[type];
  const article = monster.prefix === "the" ? "the" : monster.prefix === "" ? "none" : startsWithAn(monster.name) ? "an" : "a";
  return message(
    "server.kill." + (firstPerson ? "you" : "player") + "." + article,
    { player: name, monster: monster.name },
    { color: "gray" },
  );
}
