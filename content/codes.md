# Response codes

Every code that can arrive as `game_response` `{response: "<code>"}`, or as a bare string
`game_response "<code>"`. The build turns each row into its own entry (`code-<code>`). See the
`game_response` entry in `receive.md` for the shared fields.

**Response codes.** 258 codes, including `data` and the `<quest>_success` pattern. The list comes from every `fail_response("x")`, `success_response("x")`, bare `game_response` string and `response: "x"` literal in `node/` of the live code. It also includes the codes of local helpers: `interaction_failure`, `bet_failure` and the poker `fail()`. The `finish_*` helpers of `mail`, `mail_take_item`, `buy_with_cash`, `bless_server`, `bank` and `friend` also send codes.

Some codes come from variables: `donate_` plus `thx`, `low` or `gum` (`node/server.js:8671`), `elixir` (`node/server.js:7915`), `<quest>_success` (`node/server.js:14821`), `cave_paused` and `poker_min_raise`. The `duel` helper `duel_failure()` sends its reason (for example `already_dueling` or `pvp_zone`) as `reason` of a `data` reply, not as a code (`node/server.js:12194`). The `bank` handler now sends `bank_withdraw`, `bank_store` and the gold `bank_new_pack` as a second `game_response`, after the `data` reply (`node/server.js:9479-9482`).

The official client (js/game.js) also checks for codes that the live server never sends. They are `only_in_home`, `not_in_party`, `miss`, `locked`, `bank_restrictions`, `tavern_too_many_bets`, `cant_reach`, `op_unavailable`, `craft_atleast2`. The table leaves them out.

| Code | Meaning | Example source |
|---|---|---|
| `add_item` | An item went into your inventory through `add_item()` with logging on (`item`: the new item object). | `add_item()`, `node/server.js:2130` |
| `already_in_party` | The other character is already in your party. It is a `success_response` (`success: true`, place `party`), from `invite`, `request`, `accept` and `raccept`. | `party` handler, `node/server.js:12372` |
| `already_unlocked` | `activate` with a bank door key (`bank_b` or `bank_u`), but that door is already unlocked. Bare string. | `activate` handler, `node/server.js:9667` |
| `attack_failed` | `commence_attack()` refused the attack or skill: a merchant without a merchant skill or a dartgun, a player target outside PvP or an NPC target, or (hardcore servers only) a level gap above 10 with `reason: "level"`. Plain object `{response, id}`, no `place`. A `data` reject with `reason` `merchant`, `no_pvp` or `level_gap` follows. | `commence_attack()`, `node/server.js:3214` |
| `bank_new_pack` | A new bank pack opened. Gold path: `pack`, `gold`, `request_id`, `cevent`; it arrives after the `data` reply. Shells path: `pack`, `shells`, `request_id`, `cevent`, `success: true`. | `bank` handler, `node/server.js:9295` |
| `bank_new_pack_failed` | A bank pack bought with shells did not open. Fields: `pack`, `shells`, `request_id`, `cevent`, `failed: true`, `reason` (`nouser`, `purchase_failed` or a backend reason, `coms_failure`). | `bank` handler, `node/server.js:9328` |
| `bank_opi` | A bank operation is in progress: a bank mount or unmount (`transport`), a door unlock check (`transport`), or a pack unlock (`bank`). | `transport` handler, `node/server.js:5984` |
| `bank_opx` | The bank backend refused the bank mount. Plain object: `name` (the character in the bank, when `reason` is `already_in_bank`) and `reason`. | `sync_loop()`, `node/server.js:16638` |
| `bank_pack_unlocked` | `activate` unlocked a bank teller (pack) with an item. Bare string. | `activate` handler, `node/server.js:9707` |
| `bank_store` | Gold went into the bank (`gold`, `cevent: true`). It arrives after the `data` reply of `bank`. | `bank` handler, `node/server.js:9276` |
| `bank_unavailable` | `bank` refused: the character is not in the bank, or a bank mount or unmount is in progress. | `bank` handler, `node/server.js:9263` |
| `bank_withdraw` | Gold came out of the bank (`gold`, `cevent: true`). It arrives after the `data` reply of `bank`. | `bank` handler, `node/server.js:9270` |
| `bet_xshot` | Bet refused because the character has the `xshotted` condition. With `request_id`: place `dice`, `slots` or `wheel`, and `request_id`. Without: bare string. | `bet` handler, `node/server.js:12729` |
| `bless_result` | Second reply of `bless_server`, only when the request has `request_id`. `result` and `cevent` hold `blessed` or `blessed_fail`; also `request_id`. On success: `success: true`, `cost`, `blessed_by`, `minutes`. On failure: `failed: true`, `reason` (`nouser`, `purchase_failed` or a backend reason, `coms_failure`), `cost`. | `bless_server` handler, `node/server.js:8241` |
| `blessed` | The server blessing was bought. Bare string, no fields; the fields go to `bless_result`. | `bless_server` handler, `node/server.js:8295` |
| `blessed_fail` | The purchase of the server blessing failed at the backend. Bare string, no fields; the `reason` goes to `bless_result`. | `bless_server` handler, `node/server.js:8264` |
| `blink_failed` | `blink` or `warp` found no safe spot at the destination, or the `warp` instance does not exist. Place is the skill name. | `skill` handler, `node/server.js:10831` |
| `buy_cant_npc` | The NPCs do not sell this item (not in `can_buy`; test servers skip the check). | `buy` handler, `node/server.js:8421` |
| `buy_cant_space` | No inventory space for the purchase. | `buy` handler, `node/server.js:8424` |
| `buy_cost` | Not enough gold to buy. `buy`: no extra fields. `sbuy` with `request_id`: place `secondhands` or `lostandfound`, `request_id`, `rid`, `cost`; without `request_id`: bare string. | `sbuy` handler, `node/server.js:8378` |
| `buy_success` | NPC purchase succeeded (`cost`, `num`, `name`, `q`, `cevent: "buy"`). | `buy` handler, `node/server.js:8461` |
| `buyer_gold` | `trade_sell`: the buyer does not have the gold for price × `q`. | `trade_sell` handler, `node/server.js:8862` |
| `buyer_gone` | `trade_sell`: the buyer is not online, is an NPC, or is invisible. | `trade_sell` handler, `node/server.js:8837` |
| `cant` | `unequip` of the `elixir` slot. | `unequip` handler, `node/server.js:7939` |
| `cant_consume` | `equip` with `consume` on an item that cannot be consumed. | `equip` handler, `node/server.js:7909` |
| `cant_enter` | The map or instance cannot be entered: `transport` to an unknown or closed map, or to a cave you cannot enter, `enter` `duelland` with no such duel, or the `magiport` skill into or out of a cave (place `skill`). | `transport` handler, `node/server.js:5918` |
| `cant_equip` | The item does not fit the slot or the class (`can_equip_item()` returns `no`). | `equip` handler, `node/server.js:7895` |
| `cant_escape` | `leave`, `transport`, `enter` or `town` refused. `leave`: more than 5 monsters target you, or you are not in `jail`, `cyberland` or a solo instance. `transport` and `town`: more than 5 monsters target you. `enter`: more than 5 targets or the `block` condition. `town`: inside a cave run. | `leave` handler, `node/server.js:5882` |
| `cant_in_bank` | No character, or the character is in the bank. Also: the other trader is in the bank (`join_giveaway`, `trade_buy`, `trade_swap`); the `warp` instance has another bank mount (place `warp`); a `magiport` across a bank mount; `buy_with_cash` or `bless_server` on a hardcore or test server. `sbuy` with `request_id`: `request_id`, `rid`, place `secondhands` or `lostandfound`. `donate` with `request_id`: `request_id`, place `donate`. `destat`: `request_id` when sent. `sbuy` and `donate` without `request_id`: `{response}` only. | `dismantle` handler, `node/server.js:6446` |
| `cant_join` | `join` with an event name that is not running (`goobrawl`, `crabxx`, `franky`, `icegolem`, `abtesting`). | `join` handler, `node/server.js:12652` |
| `cant_kick` | `party` `kick` of a member who joined before you. | `party` handler, `node/server.js:12525` |
| `cant_respawn` | Respawn is not allowed yet; `ms` remaining. | `respawn` handler, `node/server.js:6285` |
| `cant_space` | `split`: no empty inventory slot. | `split` handler, `node/server.js:8007` |
| `cant_when_sick` | Blocked by the `hopsickness` condition: `join`, or `sbuy` from the lost and found. `sbuy` adds `goblin: true`; with `request_id` also `request_id`, `rid`, place `lostandfound`. | `sbuy` handler, `node/server.js:8358` |
| `cave_paused` | A Cave of Many Dreams chest cannot open while the run is paused. | `open_chest` handler, `node/server.js:11283` (reason from `cave_open_chest()`, `node/logic/cave_of_many_dreams.js:557`) |
| `cave_rescuer` | `respawn` inside a cave run: the server calls `cave_fallen()` instead of a respawn. | `respawn` handler, `node/server.js:6279` |
| `challenge_accepted` | Your duel challenge was accepted by `name`. Plain object, no `place`. | `duel` handler, `node/server.js:12233` |
| `challenge_received` | `name` challenged you to a duel. Plain object, no `place`. | `duel` handler, `node/server.js:12216` |
| `challenge_sent` | Your duel challenge to `name` was sent. With `request_id`: a `success_response` with place `duel` and `request_id`. Without: plain object `{response, name}`. | `duel` handler, `node/server.js:12214` |
| `charm_failed` | The `charm` skill roll failed (the MP is spent). Bare string. | `skill` handler, `node/server.js:10744` |
| `chat_slowdown` | `say` sent too fast: less than 400 ms after the last message, or less than 15 s for a message sent from CODE (`code` set). | `say` handler, `node/server.js:5100` |
| `compound_cant` | The item cannot be compounded (no `compound` in G). Bare string. | `compound` handler, `node/server.js:6921` |
| `compound_chance` | Compound probability preview (`calculate: true`, `chance`, `item`, `scroll`, `offering`, `grace`). | `compound` handler, `node/server.js:7026` |
| `compound_fail` | Compound finished and failed (`level`, `num`, `stale`). Hitchhiker. | `update_instance()`, `node/server.js:14863` |
| `compound_in_progress` | Another compound is in progress (`reason: "in_progress"`). | `compound` handler, `node/server.js:6882` |
| `compound_incompatible_scroll` | The scroll is not a `cscroll`, or its grade is below the grade of the items. Bare string. | `compound` handler, `node/server.js:6924` |
| `compound_invalid_offering` | The item at `offering_num` is not an offering. Bare string. | `compound` handler, `node/server.js:6886` |
| `compound_mismatch` | The three items differ in name or level. Bare string. | `compound` handler, `node/server.js:6915` |
| `compound_no_scroll` | No item at `scroll_num`. Bare string. | `compound` handler, `node/server.js:6889` |
| `compound_success` | Compound finished and succeeded (`level`, `num`, `stale`, `up`: the `extra` of the item, when set). Hitchhiker. | `update_instance()`, `node/server.js:14834` |
| `condition` | A condition was applied to you: `{response, name, cevent: true, duration}`, plus `from` when the call site names a source (`GameResponseCondition`). It arrives as a hitchhiker in the next `player` event, often with no request: from another character, a monster or the server. During the anniversary event, each eligible character online when a round's host is picked gets `name: "anniversary_visit"`, `duration: 300000` (`node/logic/anniversary_event.js:154`). A rewarded `ikissyou` gives you `anniversary_kiss`. Conditions set without `add_condition` (such as `penalty_cd`) send no `condition`. | `add_condition()`, `node/server_functions.js:3244` |
| `cooldown` | Skill is on cooldown (`skill`, `id`, `ms` remaining); `place` is the skill name. | `skill` handler, `node/server.js:9864` |
| `craft` | Craft succeeded (`num`, `name`, `cevent: true`). | `craft` handler, `node/server.js:6615` |
| `craft_cant` | No recipe matches the items, or the recipe belongs to the anniversary baker and the anniversary is not active. | `craft` handler, `node/server.js:6568` |
| `craft_cant_quantity` | Not enough of an ingredient in the given slots. | `craft` handler, `node/server.js:6607` |
| `cruise` | Cruise speed set (`speed`: `parseInt` of the payload; `null` when it is not a number). | `cruise` handler, `node/server.js:5582` |
| `cx_new` | New cosmetic unlocked (`name`, `acx`: all cosmetics you own, `from`). From a `cxjar` (`from: "cxjar"`), or from an exchange drop (`from`: the exchanged item, `bundle`: true for a `cxbundle` drop). Plain object. | `equip` handler, `node/server.js:7812` |
| `cx_not_found` | Cosmetic not found or not owned. | `cx` handler, `node/server.js:5268` |
| `cx_received` | You received a cosmetic from `name` (`cx`, `acx`: all cosmetics you own, `cevent: true`). Plain object. | `send` handler, `node/server.js:8613` |
| `cx_sent` | You sent a cosmetic to `name` (`cx`, `acx`, `cevent: true`, `place: "send"`; no `success`). | `send` handler, `node/server.js:8620` |
| `dash_failed` | `dash` could not move: the point is more than 50 away, or no safe spot at least 10 away. Bare string, then a `data` reject `{response, place}` with neither `failed` nor `success`. | `skill` handler, `node/server.js:10186` |
| `data` | Generic success or failure of the request named in `place` (defaults to the socket event name). It has `success: true` or `failed: true` and handler fields (`reason`, `in_progress`, `cevent`, `request_id`). Attack and skill results use it too; `commence_attack()` rejects give `reason` and `id`: `target_gone`, `friendly_target`, `skill_cant_use`, `skill_cant_slot`, `merchant`, `level_gap`, `no_pvp`, `no_mp`, `skill_immune`, `friendly`, `cave_paused`. Skill rejects also give `reason` `hp` and `no_target`. Other `reason` values: `cave_paused` and `cave_entering` (`node/logic/instance_pause.js:111`); `duel` reasons (`already_dueling`, `challenge_expired`, `duel_expired`, `not_your_duel`, `pvp_zone`, `duel_started`, `invalid`). **Server bug:** the skill rejects at `node/server.js:10161`, `10187`, `10200` and `10408` have neither `failed` nor `success`. | `duel` handler, `node/server.js:12194` |
| `defeated_by_a_monster` | You were killed by a monster (`monster` type, `xp` lost). | `defeated_by_a_monster()`, `node/server.js:13911` |
| `destroyed` | Item destroyed (`name`, `num`, `cevent: "destroy"`). | `destroy` handler, `node/server.js:8735` |
| `disabled` | You cannot act: you are dead (`craft`) or disabled (`skill`, place = the skill name). | `craft` handler, `node/server.js:6526` |
| `dismantle` | Item dismantled (`name`, `cevent: true`). A leveled compound item also gives `level` and `cost`. | `dismantle` handler, `node/server.js:6482` |
| `dismantle_cant` | The item is a booster, or it has no `G.dismantle` entry. | `dismantle` handler, `node/server.js:6462` |
| `distance` | Too far from the NPC, object or other character. Most handlers send `failure` with `place`. `compound` and `upgrade` send `{response, place, failed}`. With `request_id`: `sbuy` adds `request_id` and `rid` (place `secondhands` or `lostandfound`); `secondhands`, `lostandfound`, `destat` and `donate` add `request_id`; `interaction` adds `request_id` and `interaction`. Bare string: `secondhands`, `lostandfound`, `sbuy` and `interaction` without `request_id`, `misc_npc`, `tarot`. `donate` checks the distance only with `request_id`. | `monsterhunt` handler, `node/server.js:5401` |
| `donate_gum` | Donation from 100,000 gold to under 1,000,000 gold accepted. You get a `gum` item (`gold`, `xprate`). With `request_id`: also `success: true`, `place: "donate"`, `request_id`. | `donate` handler, `node/server.js:8671` |
| `donate_low` | Donation under 100,000 gold accepted (`gold`, `xprate`). With `request_id`: also `success: true`, `place: "donate"`, `request_id`. | `donate` handler, `node/server.js:8671` |
| `donate_thx` | Donation of 1,000,000 gold or more accepted. It unlocks the lost and found (`gold`, `xprate`). With `request_id`: also `success: true`, `place: "donate"`, `request_id`. | `donate` handler, `node/server.js:8671` |
| `dont_have_enough` | `trade_sell`: the buy listing in the buyer's `slot` wants fewer items than `q`. | `trade_sell` handler, `node/server.js:8859` |
| `door_unlocked` | `activate` unlocked a bank door (`bank_b` or `bank_u`) with a key. Bare string. | `activate` handler, `node/server.js:9673` |
| `duel_started` | A duel began (`challenger`, `vs`, `id`: the duel instance). Sent to the party members of both duelists, not to the duelists. | `duel` handler, `node/server.js:12291` |
| `elixir` | `equip` put an elixir from the inventory into the `elixir` slot (`num`, `success: true`, `place: "equip"`). | `equip` handler, `node/server.js:7915` (set at `node/server.js:7806`) |
| `error` | Server exception while opening a chest. | `open_chest` handler, `node/server.js:11560` |
| `ex_condition` | A condition of yours ran out: `{response, name}` (`GameResponseConditionEnded`). Sent at once (not a hitchhiker) from the timer loop, never as a reply to a request, then a `player` update. Only for conditions in `G.conditions`, including ones that came without a `condition` code, such as `penalty_cd` (teleports, magiport, equips, some item operations). | `update_instance()`, `node/server.js:14725` |
| `exception` | Server exception during `upgrade` or `compound` (`{response, place, failed}`). | `compound` handler, `node/server.js:7131` |
| `exchange_existing` | An exchange is already in progress. | `exchange` handler, `node/server.js:6623` |
| `exchange_notenough` | Not enough items: `exchange` needs `e` items of the stack; `exchange_buy` needs the token cost. | `exchange` handler, `node/server.js:6653` |
| `friend_already` | You are already friends, or the other character is on your account. It is a `success_response`. | `friend` handler, `node/server.js:12039` |
| `friend_complete` | The friend request was accepted (`success: true`, `friends`: the new list). With `request_id`: also `name`, `request_id`, `cevent`. | `friend` handler, `node/server.js:12106` |
| `friend_expired` | `friend` `accept`: no open request from `name`. | `friend` handler, `node/server.js:12057` |
| `friend_failed` | `friend` `accept` failed. `reason`: `nouser`, `bank` (one of the two users is in a bank), `100limit` (100 friends), `unknown`, `coms failure`. With `request_id`: also `name`, `request_id`, `cevent`. It has no `failed: true`. **Server bug:** the reason `coms failure` has a space, unlike `coms_failure` everywhere else (`node/server.js:12113`). | `friend` handler, `node/server.js:12066` |
| `friend_rleft` | `friend` `request`: no character with that `name` is on this server. | `friend` handler, `node/server.js:12036` |
| `friend_rsent` | Friend request sent. It is a `success_response`. | `friend` handler, `node/server.js:12043` |
| `friendly` | Attack refused (`id`): you are in a safe map, the target is in your party or guild (no friendly fire), or one side is not dueling in `duelland`. Plain object, then a `data` reject with `reason: "friendly"`. | `commence_attack()`, `node/server.js:3454` |
| `giveaway` | `unequip` of a trade slot that holds a giveaway. | `unequip` handler, `node/server.js:7944` |
| `giveaway_join` | Sent to the seller: `name` joined the giveaway in `slot` (`cevent: true`). | `join_giveaway` handler, `node/server.js:8780` |
| `gold_not_enough` | Not enough gold: `mail` (48,000; 360,000 with an item), `dismantle`, `craft`, `destat`, `locksmith` (250,000), `donate`, `trade_buy`, `bank` pack with gold, and the tavern games. `destat`: `request_id` when sent. `donate` with `request_id`: `request_id`, `gold`, place `donate`; without: bare string. Dice, slots and wheel: with `request_id`, place `dice`, `slots` or `wheel` and `request_id`; without, bare string. Poker: place `poker`. | `mail` handler, `node/server.js:5734` |
| `gold_received` | Gold received. `sell`: `gold`, `item`, `cevent: "sell"`, `success: true`. `send` from `name`: `gold`, `name`, `cevent: true`. The `alchemy` skill: `{response, gold}` only. | `sell` handler, `node/server.js:8095` |
| `gold_sent` | Gold sent to `name` (`gold`, `cevent: true`, `place: "send"`; no `success`). | `send` handler, `node/server.js:8582` |
| `gold_use` | Gold spent on a slots spin (`gold`, `game: "slots"`). | `tavern_slots_bet()`, `node/logic/tavern_slots.js:66` |
| `got_picked` | Sent to the target of a `pickpocket` that succeeded (`cevent: true`). | `update_instance()`, `node/server.js:15022` |
| `hmm` | The other trader is you: `join_giveaway`, `trade_sell`, `trade_buy` or `trade_swap` on your own slot. | `join_giveaway` handler, `node/server.js:8757` |
| `home_set` | Home server set (`home`). | `set_home` handler, `node/server.js:5534` |
| `in_progress` | A server blessing purchase of this character is already in progress. | `bless_server` handler, `node/server.js:8255` |
| `insufficient_q` | `trade_buy`: the listing has fewer items than `q`. | `trade_buy` handler, `node/server.js:8991` |
| `inv_size` | Not enough empty inventory slots: `dismantle`, `destat` (`request_id` when sent), `mail_take_item` (`id`, `request_id`, `failed: true`, `reason: "inv_size"`). | `dismantle` handler, `node/server.js:6459` |
| `invalid` | The request data is not valid (bad type, slot, index, name or target). Many handlers send it; for `skill`, place is the skill name. `secondhands` and `lostandfound` with no character: only with `request_id` (`request_id`). `interaction` with no character: only with `request_id` (`request_id`, `interaction`). `eval` (mainframe) with no character and `request_id`: place `mainframe` plus the `mainframe_result` fields. | `say` handler, `node/server.js:5097` |
| `invalid_target` | The skill cannot target this kind of entity (`id`). Also `ikissyou` (no `id`): the target is an NPC, disconnected or dead, you are dead, or the target is on another map or out of range. | `skill` handler, `node/server.js:9908` |
| `inventory_full` | No inventory space: `craft`, `exchange`, `exchange_buy`, or a `bank` pull. | `craft` handler, `node/server.js:6604` |
| `invitation_expired` | `party` `accept`: no open invitation from that character. | `party` handler, `node/server.js:12419` |
| `inviter_gone` | `magiport`: no open magiport offer from `name`, or that character is gone. A `magiport_gone` comes first. | `magiport` handler, `node/server.js:12564` |
| `item_blocked` | The item has the `b` flag, or (`mail`, `trade_sell`, `trade_swap`) the `v` flag of PvP loot. `destroy` adds `num`; `skill` uses the skill name as place. | `mail` handler, `node/server.js:5741` |
| `item_gone` | The listing is no longer in the `slot`, or its `rid` differs: `join_giveaway`, `trade_sell`, `trade_buy`, `trade_swap` (needs `rid`). `sbuy` with `request_id`: `request_id`, `rid`, place `secondhands` or `lostandfound`; without `request_id` only a `game_log`. | `sbuy` handler, `node/server.js:8405` |
| `item_locked` | The item is locked (`l`), or has `acl` where the handler checks it. `compound` and `upgrade` send `{response, place, failed}`; `destroy` adds `num`; `skill` uses the skill name as place. | `mail` handler, `node/server.js:5738` |
| `item_placeholder` | The slot holds a placeholder (the item is busy in an upgrade, compound or exchange). `destroy` adds `num`; `skill` uses the skill name as place. | `equip` handler, `node/server.js:7661` |
| `item_received` | You received an item from `name` (`item`: the item name, `q`, `num`: your slot, `cevent: true`). Plain object. | `send` handler, `node/server.js:8535` |
| `item_sent` | You sent an item to `name` (`item`: the item name, `q`, `num`: your slot, `cevent: true`, `place: "send"`; no `success`). | `send` handler, `node/server.js:8543` |
| `join_too_late` | `join` `abtesting` more than 120 s after the start, without a team from this round. | `join` handler, `node/server.js:12629` |
| `locksmith_alocked` | Item is already locked (`reason: "already_locked"`). | `locksmith` handler, `node/server.js:6842` |
| `locksmith_aunlocked` | Item is already unlocked (`reason: "already_unlocked"`). | `locksmith` handler, `node/server.js:6812` |
| `locksmith_cant` | Scrolls, offerings and tomes cannot be locked. | `locksmith` handler, `node/server.js:6807` |
| `locksmith_locked` | Item locked for 250,000 gold. Bare string. | `locksmith` handler, `node/server.js:6849` |
| `locksmith_sealed` | Item sealed for 250,000 gold. Bare string. | `locksmith` handler, `node/server.js:6856` |
| `locksmith_unlocked` | Item unlocked for 250,000 gold. Bare string. | `locksmith` handler, `node/server.js:6837` |
| `locksmith_unseal_complete` | The 48-hour unseal is over; the item is unlocked. Bare string. | `locksmith` handler, `node/server.js:6826` |
| `locksmith_unsealed` | Unsealing started for 250,000 gold; it takes 48 hours. Bare string. | `locksmith` handler, `node/server.js:6821` |
| `locksmith_unsealing` | Unseal still pending (`hours` left, `success: false`, `in_progress: true`). | `locksmith` handler, `node/server.js:6829` |
| `loot_failed` | The chest cannot be looted: a character chest of another character, you are in `woffice`, a bank map or invisible, or (cave chests) the wrong run, map or instance, dead, the run expired, more than 400 away, or the chest is gone. | `open_chest` handler, `node/server.js:11292` |
| `loot_no_space` | No space for the items in the chest. | `open_chest` handler, `node/server.js:11315` |
| `lostandfound_donate` | The lost and found needs a donation of 1,000,000 gold or more first. `lostandfound` with `request_id`: `request_id`, `reason: "donation_required"`; without: bare string. `sbuy` from the lost and found sends it only with `request_id` (`request_id`, `rid`, `reason`, place `lostandfound`); without `request_id`, `sbuy` does not check the donation. | `lostandfound` handler, `node/server.js:7986` |
| `lostandfound_info` | Reply to `lostandfound` `"info"`: `gold` is the gold reserve of the server. Plain object. | `lostandfound` handler, `node/server.js:7982` |
| `magiport_failed` | The `magiport` skill (non-pve-safe path) did not move the target (`id`). Plain object. **Server bug:** this path reads an undeclared variable `ported`; when nothing assigned it before, the handler throws (`node/server.js:10819-10821`). | `skill` handler, `node/server.js:10822` |
| `magiport_gone` | `magiport`: the magiporter `name` is gone, or the offer expired. Plain object; `inviter_gone` follows. | `magiport` handler, `node/server.js:12563` |
| `magiport_sent` | The magiport offer went to the target (`id`). Plain object. | `skill` handler, `node/server.js:10815` |
| `mail_failed` | The mail was not sent (`to`, `request_id`, `cevent`, `reason`: `nocharacter`, `nouser`, `unknown`, `coms_failure`). It has no `failed: true`. | `mail` handler, `node/server.js:5761` |
| `mail_item_already_taken` | The mail item cannot be taken (`id`, `request_id`, `failed: true`, `reason`: `invalid_mail`, `already_taken`, `no_item`). | `mail_take_item` handler, `node/server.js:5640` |
| `mail_item_taken` | You took the attachment of a mail. Fields: `id`, `request_id`, `cevent`, and `gold` (a gold attachment of a cave award) or `item` (the item). No `place`. | `mail_take_item` handler, `node/server.js:5686` |
| `mail_received` | You got new mail from the server: the tracktrix mail on the first `start` of the account, or a Cave of Many Dreams award (`count`: unread mails, maximum 100). It goes to every character of the account on this server. | `auth` handler, `node/server.js:11951`; `node/logic/cave_of_many_dreams.js:679` |
| `mail_sending` | The first reply of `mail`: the server took the gold and saves the mail now (`in_progress: true`, `received: "unknown"`). The result arrives later as `mail_sent` or `mail_failed`. **Server bug:** the handler sends the typo `sucess: false`, so `success_response` also sets `success: true`. | `mail` handler, `node/server.js:5862` |
| `mail_sent` | The mail was saved for `to`. Fields: `to`, `request_id`, `cevent: "mail_sent"`. No `place` or `success`. | `mail` handler, `node/server.js:5853` |
| `mail_take_item_failed` | The attachment could not be taken (`id`, `request_id`, `cevent`, `reason`). `reason` is a backend reason (`not_owner`, `wrong_character`), `claim_failed`, or `coms_failure` (an exception, also an attachment that is not a valid item). No `place`. | `mail_take_item` handler, `node/server.js:5663` |
| `max_level` | The item grade is 4, so it cannot go higher (`level`). From `compound`, and from `upgrade` with an upgrade scroll. | `compound` handler, `node/server.js:6903` |
| `merge_complete` | The pet container merged into the other container. A bare string. | `merge` handler, `node/server.js:9588` |
| `merge_mismatch` | One of the two slots holds no item of type `container`, the target container has a lower grade, or the target already holds `data`. A bare string. | `merge` handler, `node/server.js:9581` |
| `misc_fail` | `compound` got the same inventory index two times. | `compound` handler, `node/server.js:6927` |
| `monsterhunt` | `interaction` `dailytask` started a 1-hour daily task on `goo` (`monster`). A plain object. | `interaction` handler, `node/server.js:11146` |
| `monsterhunt_already` | Your monster hunt is not complete (monsters are left to kill). | `monsterhunt` handler, `node/server.js:5410` |
| `monsterhunt_merchant` | A merchant cannot take a monster hunt. A bare string. | `monsterhunt` handler, `node/server.js:5420` |
| `monsterhunt_started` | A new monster hunt started. A bare string, as a hitchhiker in the next `player` event. A `data` reply with `started: true` comes first. | `monsterhunt` handler, `node/server.js:5433` |
| `muted` | You are muted (`s.mute`), or you have no character. From `cm` and `say`. | `cm` handler, `node/server.js:5081` |
| `need_auth` | `join_giveaway` needs a game client authorization (`auth_id`), and the character has none. | `join_giveaway` handler, `node/server.js:8767` |
| `no_item` | No item at the inventory index of the request. From `craft`, `destat`, `locksmith`, `compound`, `equip`, `split`, `sell`, `send`, `destroy`, `trade_sell` (no matching item), `trade_swap` and `throw`. `compound` also sends it when `items` is not 3 integers, or when the item level is not `clevel`. `destroy` adds `num`; `destat` adds `request_id`. | `craft` handler, `node/server.js:6561` |
| `no_level` | Your level is below the `level` of the skill. `place` is the skill name. | `skill` handler, `node/server.js:9850` |
| `no_merchants` | A merchant cannot `join` an event. | `join` handler, `node/server.js:12599` |
| `no_mp` | Not enough MP. From `skill` (`place` is the skill name) and `energize` (the caster has 0 MP). From `commence_attack()`, it is a plain `{response: "no_mp"}`, and a `data` reply with `reason: "no_mp"` follows. | `skill` handler, `node/server.js:9846` |
| `no_skill` | The skill name is not in `G.skills`. | `skill` handler, `node/server.js:9790` |
| `no_space` | No inventory space for the item you get. From `unequip`, `buy_with_cash`, `trade_buy`, `trade_swap` (the rest of your stack plus the listed item), and `sbuy` with `request_id` (adds `request_id`, `rid`; without `request_id`, only floating text). | `unequip` handler, `node/server.js:7948` |
| `no_target` | The skill needs a target and `id` is absent, a hostile skill targets yourself, or a `no_self` emote targets yourself. | `skill` handler, `node/server.js:9901` |
| `non_friendly_target` | The target is not friendly enough for the skill. Emotes (not `ikissyou`): another instance, or not your party, account or friend. `cleansing_light`, `guardians_oath`: no target, yourself, an NPC, dead, or in another instance. `4fingers`: not in PvP and not your party or account. `absorb` on a target outside your party: below level 75 or below 6× the MP cost; else the server takes the MP and fails 95% of the time with this code. | `skill` handler, `node/server.js:9935` |
| `not_connected` | `eval` `command` (mainframe) with `request_id` from outside `cyberland`, or from a dead character. Fields: `request_id`, `command`, `authorized: true`; `place` is `mainframe`. Without `request_id`, only a `game_log`. | `eval` handler, `node/server.js:13218` |
| `not_enough` | The stack has fewer items than the `q` of a trade slot listing. | `equip` handler, `node/server.js:7687` |
| `not_enough_gold` | `buy_shells`: `gold` is below 1,000,000 (the minimum) or above your gold. A bare string. The live server never sends it: the handler first sends the `game_log` `no_longer_possible` and returns (`node/server.js:8099`). | `buy_shells` handler, `node/server.js:8106` |
| `not_in_a_party` | Party chat (`say` with `party`) while you are not in a party. | `say` handler, `node/server.js:5111` |
| `not_in_pvp` | The `throw` skill with a negative item (in `G.skills.throw.negative`, or with an `nprop` property) on a player outside PvP. | `skill` handler, `node/server.js:10325` |
| `not_in_tavern` | `bet`: no character, in the bank, or not on the `tavern` map. It is sent only with `request_id` (`place`, `request_id`); without it, nothing. Poker: in the bank, or not in the `tavern` instance (always an object, `place: "poker"`). | `bet` handler, `node/server.js:12725` |
| `not_in_this_server` | The server does not allow mail (`mode.prevent_external`). From `mail` (a failure), and from `mail_take_item` (fields `id`, `request_id`, `failed: true`, `reason: "not_in_this_server"`; no `place`). | `mail` handler, `node/server.js:5714` |
| `not_ready` | The potion cooldown is active (`ms` remaining). From `equip` of a potion and `use` of `hp`/`mp`. The `activate` of `etherealamulet` within 120 ms of the last one sends a bare string with no `ms`. | `equip` handler, `node/server.js:7828` |
| `nothing` | `activate` of `angelwings`: the item is below level 8, or your class is not mage or priest. A bare string. | `activate` handler, `node/server.js:9616` |
| `only_in_bank` | `activate` of `bkey`, `ukey` or `dkey` outside the bank. A bare string. | `activate` handler, `node/server.js:9664` |
| `party_full` | The party is full (`limits.party_max` or `limits.party`). `invite` and `raccept`: your party; `accept`: the party of the inviter. | `party` handler, `node/server.js:12365` |
| `pick_failed` | Pickpocket failed (`cevent: true`, `request_id`, `reason`). `reason`: `player_gone`, `distance` (more than 20 px), or `misfortune` (the random slot held no item with `v`). A plain object. | `update_instance()`, `node/server.js:14988` |
| `picked` | Pickpocket took an item (`cevent: true`, `request_id`). `slot` is always `"mainhand"`, not the slot of the item. A plain object. | `update_instance()`, `node/server.js:15014` |
| `player_gone` | The other player is not on this server (`name`). From party `accept`, `raccept` and `kick` (`kick` has no `name`). | `party` handler, `node/server.js:12410` |
| `poker_broke` | `sit_in`: your stack is smaller than the big blind (`min`). | `tavern_poker_sit()`, `node/logic/tavern_poker.js:637` |
| `poker_buyin` | The buy-in is out of range (`min`, `max`). For a seated player who adds chips, `min` is 1 and `max` is the room left to the maximum buy-in. | `tavern_poker_join()`, `node/logic/tavern_poker.js:562` |
| `poker_far` | You are more than 260 px from the poker table. | `tavern_poker_join()`, `node/logic/tavern_poker.js:558` |
| `poker_full` | All poker seats are taken. | `tavern_poker_join()`, `node/logic/tavern_poker.js:582` |
| `poker_in_hand` | You cannot add chips while your seat is in a hand. | `tavern_poker_join()`, `node/logic/tavern_poker.js:561` |
| `poker_invalid_action` | Unknown poker `event`, or from `act`: an unknown action, `check` while there is a bet to call, or a raise that you may not make now. | `tavern_poker_request()`, `node/logic/tavern_poker.js:545` |
| `poker_min_raise` | The bet is below the current bet plus the minimum raise (`min`, `max`: your bet plus your stack). | `tavern_poker_act()`, `node/logic/tavern_poker.js:653` (reason from `node/logic/tavern_poker.js:779`) |
| `poker_not_seated` | You have no seat at the poker table (`leave`, `act`, `sit_out`, `sit_in`). | `tavern_poker_leave()`, `node/logic/tavern_poker.js:621` |
| `poker_not_your_turn` | No hand is active, or it is not your turn to act. | `tavern_poker_act()`, `node/logic/tavern_poker.js:651` |
| `poker_saving` | The poker table is saving. Only `info` works now. | `tavern_poker_request()`, `node/logic/tavern_poker.js:539` |
| `poker_seat_taken` | The seat you asked for is taken. | `tavern_poker_join()`, `node/logic/tavern_poker.js:581` |
| `poker_seated` | A character of your account already sits at the table. | `tavern_poker_join()`, `node/logic/tavern_poker.js:577` |
| `poker_stool_far` | You do not stand at a free stool, or at the stool you asked for. | `tavern_poker_join()`, `node/logic/tavern_poker.js:583` |
| `poker_unavailable` | No payload, or the poker table or the tavern instance does not exist on this server. | `tavern_poker_request()`, `node/logic/tavern_poker.js:527` |
| `<quest>_success` | An exchange of an item with a `quest` finished. The code is the `quest` name plus `_success`; `suffix` is the exchange suffix or `""`. A plain object, sent directly (not a hitchhiker). | `update_instance()`, `node/server.js:14821` |
| `receiver_unavailable` | `send`: no character with that `name` on this server, or the receiver is in the bank. | `send` handler, `node/server.js:8472` |
| `request_expired` | Party `raccept`: no open request from that player. | `party` handler, `node/server.js:12467` |
| `revive_failed` | `revive`: the dead target does not have full HP (`id`). A plain object; the server takes the MP, and a `data` reply with `reason: "hp"` and no `failed` follows. | `skill` handler, `node/server.js:10409` |
| `reward_already` | The reward was already claimed. From `ureward` and `creward`. A bare string. | `ureward` handler, `node/server.js:5213` |
| `reward_notverified` | The character is not verified, or has no game client authorization (`auth_id`). From `ureward` and `creward`. A bare string. | `ureward` handler, `node/server.js:5190` |
| `reward_received` | The reward was given (`rewards`: the list of claimed rewards). A plain object. From `ureward` and `creward`. | `ureward` handler, `node/server.js:5222` |
| `reward_unavailable` | The `ureward` claim failed (`reason`: `tutorial_incomplete` or another backend reason, `character_gone`, or `server_error`). A plain object. | `ureward` handler, `node/server.js:5216` |
| `safety_check` | `exchange_buy`: `q` is not the quantity of the token stack (loose `!=`). | `exchange_buy` handler, `node/server.js:6703` |
| `scrollsmith_cant` | The item has no `stat_type` (or no scroll exists for it). Adds `request_id` when given. | `destat` handler, `node/server.js:6756` |
| `scrollsmith_success` | The stat was removed and you got its scrolls (`gold`: the cost). A plain object; a `data` reply follows. | `destat` handler, `node/server.js:6778` |
| `seller_gone` | The seller is not on this server, is an NPC, or is invisible. From `join_giveaway`, `trade_buy` and `trade_swap`. | `join_giveaway` handler, `node/server.js:8748` |
| `send_diff_owner` | Cosmetics can only go to characters of your own account. | `send` handler, `node/server.js:8596` |
| `send_no_cx` | You do not have a free copy of the cosmetic `cx`. | `send` handler, `node/server.js:8592` |
| `send_no_item` | No item at `num` (after `max(0, parseInt(num) \|\| 0)`). | `send` handler, `node/server.js:8481` |
| `send_no_space` | The receiver has no space for the item. | `send` handler, `node/server.js:8497` |
| `sh_time` | You set your home less than 36 hours ago (`hours`: hours left, a fraction). | `set_home` handler, `node/server.js:5529` |
| `shell_purchase_complete` | An item was bought with shells (`name`, `quantity`, `cost` in shells, `request_id`, `cevent`). No `place`. | `buy_with_cash` handler, `node/server.js:8223` |
| `shell_purchase_failed` | The shell purchase failed (`name`, `quantity`, `request_id`, `cevent`, `reason`: `nouser`, `not_enough`, `purchase_failed`, another backend reason, or `coms_failure`). No `place`. | `buy_with_cash` handler, `node/server.js:8186` |
| `signed_up` | The `signup` was recorded. A plain object with no fields. | `signup` handler, `node/server.js:12591` |
| `skill_cant_charges` | The item in the `slot` of the skill has fewer `charges` than the item's `charge`. | `skill` handler, `node/server.js:9991` |
| `skill_cant_incapacitated` | You are silenced or have the `konami` skin. Every skill except `attack`. | `skill` handler, `node/server.js:9785` |
| `skill_cant_item` | The skill consumes an item (`consume`), and there is none (or not at `num`). | `skill` handler, `node/server.js:10056` |
| `skill_cant_pve` | `huntersmark` on a player outside PvP who is not in your party or account. | `skill` handler, `node/server.js:10729` |
| `skill_cant_requirements` | A stat of the character is below the `requirements` of the skill. | `skill` handler, `node/server.js:9957` |
| `skill_cant_safe` | A hostile skill on a `safe` map. | `skill` handler, `node/server.js:9895` |
| `skill_cant_slot` | The item that the skill needs is not equipped (`slot`), or the offhand is not the `offhand_type`. Also a `reason` of a `data` reply from `commence_attack()`. | `skill` handler, `node/server.js:9890` |
| `skill_cant_use` | Your class cannot use the skill; `rimeshell` or `rimeshatter`; an emote you do not own (during the anniversary it adds `message`, `phrase`, `phrase_args`, `reason`, `rewarded: false`); `invis` while `marked`; `guardians_oath` with `reason` `outgoing_oath` or `incoming_oath`. Also a `reason` of a `data` reply from `commence_attack()`. | `skill` handler, `node/server.js:9793` |
| `skill_cant_wtype` | The mainhand weapon type is not the `wtype` of the skill. | `skill` handler, `node/server.js:9885` |
| `skill_immune` | A monster was immune to `stomp` or `scare` (`skill`). A plain object, as a hitchhiker. Also a `reason` of a `data` reply from `commence_attack()`. | `skill` handler, `node/server.js:10670` |
| `skill_no_item` | The `throw` skill: no item at `num`. | `skill` handler, `node/server.js:10308` |
| `slot_occuppied` | The trade slot holds an item. From `equip` to a trade slot, and `trade_wishlist` (there, a buy listing in the slot can be replaced). | `equip` handler, `node/server.js:7701` |
| `slots_fail` | The slot machine paid nothing. With `request_id`: `place: "slots"`, `request_id`, `success: true` (also on this code), `won`, `cost`, `payout`, `net`, `symbols`, `prize`, `edge`, `cut`. Without it, a bare string. | `tavern_slots_settle()`, `node/logic/tavern_slots.js:124` |
| `slots_spinning` | Your slot machine spin is not finished. | `tavern_slots_bet()`, `node/logic/tavern_slots.js:36` |
| `slots_success` | The slot machine paid out. Same fields as `slots_fail`. | `tavern_slots_settle()`, `node/logic/tavern_slots.js:124` |
| `sneaky` | The listing is not the right kind. `join_giveaway`: not a giveaway. `trade_sell`: not a buy listing (`b`), or a swap listing (`want`). `trade_buy`: a buy, giveaway or swap listing. `trade_swap`: not a swap listing, or also a buy or giveaway listing. | `join_giveaway` handler, `node/server.js:8764` |
| `storage_full` | `bank` `store`: the bank pack has no space for the item. | `bank` handler, `node/server.js:9461` |
| `target_alive` | `revive`: the target is not dead. | `skill` handler, `node/server.js:10403` |
| `target_invincible` | The target has the `invincible` condition. From `throw`, `entangle`, `tangle` and `4fingers`. | `skill` handler, `node/server.js:10304` |
| `target_lock` | The Konami code was entered in `interaction`: you get a target monster (`monster`), new every 15 days. A plain object. | `interaction` handler, `node/server.js:11164` |
| `tarot_exists` | A tarot condition is already active. A bare string. | `tarot` handler, `node/server.js:12708` |
| `tavern_closing` | The server is about to stop, so the tavern takes no wagers. From `bet` and poker `join`. A wager that the server refunds sends it with `request_id` only: `place`, `request_id`, `reason: "tavern_closing"`, `refund`. | `bet` handler, `node/server.js:12732` |
| `tavern_dice_exist` | You already have a bet. | `bet` handler, `node/server.js:12820` |
| `tavern_gold_not_enough` | The house gold cannot cover the possible payout. Dice and wheel: the net payout is above 40% of the house gold minus its debt. Slots: the largest prize is above the house gold minus its debt. | `bet` handler, `node/server.js:12817` |
| `tavern_not_yet` | The dice are not taking bets yet. | `bet` handler, `node/server.js:12811` |
| `tavern_too_late` | The dice are rolling now. | `bet` handler, `node/server.js:12808` |
| `tavern_unavailable` | The tavern instance does not exist. Sent only with `request_id`; without it, nothing. | `bet` handler, `node/server.js:12720` |
| `temporalsurge` | `temporalsurge` made the respawn timers within 160 px shorter: each is ×0.85, then −1,000 ms (`count`, `times`: the new timers in ms). A plain object. | `skill` handler, `node/server.js:10980` |
| `temporalsurge_none` | `temporalsurge` found no respawn timer within 160 px. A bare string; the MP is used. | `skill` handler, `node/server.js:10978` |
| `too_far` | The target or point is out of range. Skills add `dist` and `id`. **Server bug:** `throw` (the event) sends `too_far` without `return`, so the item is still thrown. | `throw` handler, `node/server.js:9507` |
| `trade_bspace` | `trade_sell`: the buyer has no space for the item. | `trade_sell` handler, `node/server.js:8888` |
| `trade_offer_invalid` | The `want` of a trade slot listing is not valid. | `equip` handler, `node/server.js:7694` |
| `trade_swap_match` | The item you offer for a swap does not match the `want` of the listing, or it is not the item in `item` (your inventory changed). | `trade_swap` handler, `node/server.js:9112` |
| `trade_swap_space` | The seller has no space for the item you offer. | `trade_swap` handler, `node/server.js:9117` |
| `transport_cant_dampened` | A transport through the transporter NPC while you have the `dampened` condition. | `transport` handler, `node/server.js:5956` |
| `transport_cant_invalid` | `enter` with a `name`: no instance with that name on this map type. | `enter` handler, `node/server.js:6136` |
| `transport_cant_item` | `enter`: you do not have the key item of the instance. | `enter` handler, `node/server.js:6140` |
| `transport_cant_locked` | The door leads to a bank level that the account has not unlocked. The async check (from outside the bank) sends `{response, failed: true, place: "transport"}`. | `transport` handler, `node/server.js:5979` |
| `transport_cant_protection` | The door is `protected`, and a gatekeeper monster is alive in the instance. | `transport` handler, `node/server.js:5969` |
| `transport_cant_reach` | `transport`: no door or transporter is in reach. `enter`: more than 120 px from the entrance, or an unknown `place`. | `transport` handler, `node/server.js:5959` |
| `transport_failed` | You cannot walk now, or you are in jail. From `transport`, `enter`, `town` and `leave`. `enter` also sends it on a server that is not `normal`. | `leave` handler, `node/server.js:5875` |
| `unfriend_complete` | The friendship ended (`name`, `request_id`, `cevent`, `friends`: the new list). | `friend` handler, `node/server.js:12178` |
| `unfriend_failed` | Unfriend failed (`name`, `request_id`, `cevent`, `reason`: `nouser`, `bank`, `unknown` or `coms_failure`). `bank`: one of the accounts is in the bank. | `friend` handler, `node/server.js:12142` |
| `upgrade_cant` | The item has no `upgrade` in G. A bare string. | `upgrade` handler, `node/server.js:7175` |
| `upgrade_chance` | Upgrade probability preview (`calculate: true`, `chance`, `item`, `grace`, and `offering` and/or `scroll`). | `upgrade` handler, `node/server.js:7232` |
| `upgrade_fail` | The upgrade finished and failed (`level`: the level it tried to reach, `num`, `stale`). A hitchhiker. | `update_instance()`, `node/server.js:14942` |
| `upgrade_in_progress` | Another upgrade is in progress. A bare string. | `upgrade` handler, `node/server.js:7146` |
| `upgrade_incompatible_scroll` | The scroll is not an upgrade scroll (`uscroll`) or a stat scroll (`pscroll`), a stat scroll is on an item without `stat`, or the item grade is above the scroll grade. A bare string. | `upgrade` handler, `node/server.js:7192` |
| `upgrade_invalid_offering` | The offering is not an offering item, or its `offering` grade is lower than the base grade of the item. A bare string. | `upgrade` handler, `node/server.js:7162` |
| `upgrade_mismatch` | The item level is not `clevel` (the level that the client saw). A bare string. | `upgrade` handler, `node/server.js:7168` |
| `upgrade_no_item` | No item at `item_num`. A bare string. | `upgrade` handler, `node/server.js:7153` |
| `upgrade_no_scroll` | No scroll and no offering at the given indexes. A bare string. | `upgrade` handler, `node/server.js:7165` |
| `upgrade_offering_success` | An upgrade with only an offering finished and succeeded (`stale`). A hitchhiker; `upgrade_success` follows. | `update_instance()`, `node/server.js:14903` |
| `upgrade_scroll_q` | Not enough stat scrolls (`q` needed, `h` you have). A plain object. | `upgrade` handler, `node/server.js:7505` |
| `upgrade_success` | The upgrade finished and succeeded (`level`: the new level, `num`, `stale`). A hitchhiker. **Server bug:** after a stat scroll, `level` is the item level plus 1, but the level does not change. | `update_instance()`, `node/server.js:14924` |
| `upgrade_success_stat` | A stat scroll upgrade finished (`stale`, `stat_type`, `num`). A hitchhiker; `upgrade_success` follows. | `update_instance()`, `node/server.js:14910` |
| `wheel_side` | The wheel `side` is not in `G.games.wheel.sides`. | `tavern_wheel_bet()`, `node/logic/tavern_wheel.js:15` |
| `wheel_spinning` | Your wheel spin is not finished. | `tavern_wheel_bet()`, `node/logic/tavern_wheel.js:16` |
