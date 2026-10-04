# S: server-wide event state (`server_info`)

S tells a client which events run on the game server now: bosses, arenas, holidays, duels and the server blessing. Bare source paths point into the live game's code (`node/server.js:123`, `node/server_functions.js:2374`). Data numbers come from the live G with version 17478.

## What S is

**Naming.** On the game server, this object is the global `E` ("server event data", `node/server.js:203`). The server also has a global `S`, but that one holds saved server data (sold items, the blessing timer, grace counters). The server never sends that `S` to clients. The browser client keeps `E` in its own global `S` (`js/game.js:206`). This page uses "S" for the object that clients receive.

**How a client receives it.**

| Socket event | When | Payload | Browser client |
|---|---|---|---|
| `welcome` | On socket connect, before login | `data.S` holds the full object (`node/server.js:5017`, emitted at `node/server.js:5019`) | `S = data.S` (`js/game.js:1584`) |
| `start` | After a character logs in | `data.s_info` holds the full object (`node/server.js:11931`, emitted at `node/server.js:11944`) | `S = data.s_info`, then it deletes `s_info` from the character data (`js/game.js:1721`, `js/game.js:1732`) |
| `server_info` | The server sends it to every socket on the game server, on both socket endpoints (`node/server_functions.js:3028-3032`, `broadcast` at `node/server_functions.js:3495-3496`) | The full object each time. It is never a diff. | `S = data; render_server();` (`js/game.js:3093-3096`) |
| `hardcore_info` | HARDCORE server only: every 60 s, and when a character wins a reward | `{E: <full object>, achiever?: name}` (`node/server_functions.js:5688`, `node/server_functions.js:5893`) | `S = data.E` (`js/game.js:3097-3101`) |

Each message carries the whole object. Thus, replace your copy each time. Do not merge. If a key is missing from the new object, the server removed it.

**When the server sends `server_info`.**

| Trigger | Source |
|---|---|
| A timer every 24 s while `server.live` | `node/server.js:16509-16517` |
| `event_loop` runs every 1 s (`node/server_functions.js:3139`). At the end of a tick, it sends S if `change` is true, if any top-level entry has a truthy `target`, or if `E.duels` has an entry. | `node/server_functions.js:3014-3022` |
| A seasonal boss gets a spawn timer or spawns (an immediate send inside the loop) | `node/server_functions.js:2659`, `node/server_functions.js:2670` |
| The anniversary state changes | `node/server_functions.js:2370` |
| A PvP kill in A/B Testing changes the score | `node/server.js:2942-2945` |
| A duel starts, or a duel ends | `node/server.js:12287`, `node/server_functions.js:3005-3006` |

`broadcast_e(true)`, called before `welcome` and `start`, sends nothing because `dont_send` is true (`node/server.js:5016`, `node/server.js:11930`, `node/server_functions.js:3028-3031`).

> **Note:** During a season, the server sends S about once per second while a seasonal boss waits to spawn. Each tick, the cleanup step deletes the `{live: false}` entry of the boss and sets `change` (`node/server_functions.js:2681-2686`). A later step in the same tick adds the entry again (`node/server_functions.js:2801-2806`). `slenderman` is not in the cleanup list, so it does not cause this.

**Value types.** `end`, `spawn` and `signup_end` are JavaScript `Date` objects on the server. Both socket encoders turn a `Date` into an ISO-8601 string (`node/msgpack_parser.js:42` for MessagePack). The browser client reads them with `new Date(...)` (`js/html.js:834`). The `anniversary` entry is different: its `next` and `expires` fields are numbers in ms since 1970 (`node/logic/anniversary_event.js:170`, `node/logic/anniversary_event.js:174`).

## Shape

S is a flat object. Its top-level keys belong to these families.

| Key family | Form | Fields | Meaning |
|---|---|---|---|
| `schedule` | object, on normal servers | `time_offset`, `dailies`, `nightlies`, `night` | Server clock and the event schedule (`node/server.js:203-210`) |
| Daily or nightly boss (`crabxx`, `franky`, `icegolem`) | live only | `live: true`, `map`, `hp`, `max_hp`, `target`, `x`, `y`, `end` | The boss is alive. `end` is the event timeout (`node/server_functions.js:2522-2531`). |
| Seasonal boss (`mrpumpkin`, `mrgreen`, `slenderman`, `grinch`, `snowman`, `dragold`, `pinkgoo`, `wabbit`) | not live | `live: false`, `spawn` | The boss is not alive. `spawn` is the next spawn time (`node/server_functions.js:2658`, `node/server_functions.js:2803`). |
| same | live | `live: true`, `map`, `hp`, `max_hp`, `target`, plus `x` and `y` | The boss is alive (`node/server_functions.js:2664-2669`, `node/server_functions.js:2700-2708`). `slenderman` has no `x`/`y`. |
| `tiger` | live only | `live: true`, `map`, `hp`, `max_hp`, `target` | No `x`/`y` (`node/server_functions.js:2690-2694`) |
| Arena event (`goobrawl`) | object | `end` | The event runs until `end` (`node/server_functions.js:2553`) |
| Arena event (`abtesting`) | object | `end`, `signup_end`, `A`, `B`, `id` | Team battle (`node/server_functions.js:2855`) |
| Holiday flags (`halloween`, `holidayseason`, `lunarnewyear`, `valentines`, `egghunt`) | `true` | none | The season is on. The key is absent when the season is off (`node/server_functions.js:2674-2680`). |
| `anniversary` | object | `active`, `live`, `next`, and during a round `round`, `expires`, `target`, `id`, `available`, `skin`, `cx`, `map`, `x`, `y` | The anniversary event (`node/logic/anniversary_event.js:166-185`) |
| `duels` | map of instance name to duel | `challenger`, `a`, `vs`, `b`, `instance`, `seconds`, `active`, `id` | Duels (`node/server.js:12268-12277`, `node/server.js:12286`) |
| `blessed_minutes`, `blessed_by` | number, string | none | Server blessing (Patron's Grace) (`node/server.js:15694-15705`) |
| `rewards`, `minutes` | object, number | see below | HARDCORE server only (`node/server_functions.js:3106-3135`) |

### Field details

| Field | Type | Meaning |
|---|---|---|
| `live` | boolean | `true` when the monster exists. `false` in the waiting form. |
| `map` | string | Map of the monster |
| `hp`, `max_hp` | number | Current and maximum HP. The loop updates them every second while the boss lives, except for `slenderman`. |
| `target` | string or absent | Name of the monster's target. The browser shows "JOIN" when it is set (`js/html.js:835`). A truthy `target` on any entry makes the loop send S every second. |
| `x`, `y` | number | Monster position. Absent for `slenderman`, which teleports, and for `tiger`. |
| `end` | date string | `crabxx`, `franky` and `icegolem`: the timeout. The boss stays after `end` while a player attacked it in the last 20 s (`node/server_functions.js:2495`). `goobrawl` and `abtesting`: the end of the event. |
| `spawn` | date string | Next spawn time of a seasonal boss |
| `abtesting.A`, `abtesting.B` | number | Team scores. Each PvP kill of the other team adds 1 (`node/server.js:2942`). They are not team sizes. |
| `abtesting.signup_end` | date string | Start + 60 s. The `join` handler accepts players for 120 s after the start (`node/server.js:12625-12630`). |
| `abtesting.id` | string | 5 random characters. The server saves your team in `player.p.abtesting = [id, team]`, so a rejoin keeps the team (`node/server.js:12632-12641`). |
| `schedule.time_offset` | number | Hours from UTC for the region: EU 1, US −5, ASIA 7 (`node/server.js:339-343`, `node/server.js:365`). The browser uses it to show server time (`js/game.js:1030`). |
| `schedule.dailies` | number[] | Local hours at which a daily event starts: `[13, 20]` |
| `schedule.nightlies` | number[] | Local hours at which a nightly event starts: `[23]` |
| `schedule.night` | boolean | `true` from local hour 0 to 5 (`node/server_functions.js:2380-2384`). At night, monsters move at 70 % speed (`node/server.js:1828-1830`). Monsters also fall asleep more often (`node/server.js:14279`). |
| `duels[id].seconds`, `duels[id].active` | number, boolean | Start values: 60 (20 on a Dev server) and `false` (`node/server.js:12274-12275`). See the duel bug below. |
| `duels[id].a`, `duels[id].b` | string[] | Team lists: the challenger's party and the opponent's party. When the duel starts, the server keeps only the players who are present (`node/server_functions.js:2934-2953`). |
| `anniversary.active` | boolean | Always `true` when the key exists |
| `anniversary.live` | boolean | `true` while a round has a target |
| `anniversary.next` | number (ms) | Start of the next 30-minute slot |
| `anniversary.round`, `expires` | number | Round id (the slot number) and the end of the 5-minute round window |
| `anniversary.target`, `id`, `skin`, `cx`, `map`, `x`, `y` | various | The character to visit. `x` and `y` are rounded. |
| `anniversary.available` | boolean | `true` while visitors can still claim a reward from the target |
| `blessed_minutes` | number | Minutes of blessing left. It goes down by 1 every 60 s (`node/server.js:15694-15698`). |
| `blessed_by` | string | The character who blessed the server |
| `rewards` | object | HARDCORE: reward slot to character name or `null`, plus a `"!participation"` text (`node/server_functions.js:3107-3131`) |
| `minutes` | number | HARDCORE: minutes left in the round. It starts at 340 (12 on a Dev server) and goes down by 1 every 60 s (`node/server_functions.js:3132-3135`, `node/server_functions.js:5681-5687`). |

## Every key

| Key | Kind | When it appears / disappears | Notable fields | Source |
|---|---|---|---|---|
| `schedule` | other | Always there on normal servers. Absent on HARDCORE, where `init_server` replaces `E`. | `time_offset`, `dailies`, `nightlies`, `night` | `node/server.js:203-210`; `node/server_functions.js:2378-2384` |
| `crabxx` | boss monster (daily) | Added on the tick after Giga Crab spawns. Removed when the boss dies or the event times out. | live form + `end` | `node/server_functions.js:2486-2548` |
| `franky` | boss monster (nightly) | Same as `crabxx` | live form + `end` | `node/server_functions.js:2486-2548` |
| `icegolem` | boss monster (nightly) | Same as `crabxx` | live form + `end` | `node/server_functions.js:2486-2548` |
| `goobrawl` | event (daily) | Added when the daily starts. Removed after `G.events.goobrawl.duration` (540 s). | `end` | `node/server_functions.js:2550-2581` |
| `abtesting` | event (daily) | Added when the daily starts. Removed after `G.events.abtesting.duration` (480 s). | `end`, `signup_end`, `A`, `B`, `id` | `node/server_functions.js:2814-2864` |
| `mrpumpkin` | boss monster (seasonal, halloween) | While `halloween` is on: `{live: false, spawn}` while it waits, the live form while it lives | live or waiting | `node/server_functions.js:2650-2673`, `node/server_functions.js:2695-2710`, `node/server_functions.js:2801-2806` |
| `mrgreen` | boss monster (seasonal, halloween) | Same as `mrpumpkin` | live or waiting | same |
| `slenderman` | boss monster (seasonal, halloween) | Same pattern. The live entry has no `x`/`y`. The server writes it only at spawn. It does not update it each tick. | live (no x/y) or waiting | `node/server_functions.js:2642`, `node/server_functions.js:2660-2670` |
| `grinch` | boss monster (seasonal, holidayseason) | Same as `mrpumpkin` | live or waiting | same as `mrpumpkin` |
| `snowman` | boss monster (seasonal, holidayseason; also off-season) | During `holidayseason`: same as `mrpumpkin`. Off-season: only a live entry while a snowman lives. | live or waiting | `node/server_functions.js:2630-2637`, `node/server_functions.js:2644` |
| `dragold` | boss monster (seasonal, lunarnewyear) | Same as `mrpumpkin` | live or waiting | `node/server_functions.js:2645` |
| `pinkgoo` | boss monster (seasonal, valentines) | Same as `mrpumpkin`. The tick update fills `x`/`y`. | live or waiting | `node/server_functions.js:2647` |
| `wabbit` | boss monster (seasonal, egghunt) | Same as `mrpumpkin`. The tick update fills `x`/`y`. | live or waiting | `node/server_functions.js:2648` |
| `tiger` | boss monster | A live entry (no `x`/`y`) while a tiger exists. Its `eventmap` line is a comment, so nothing in the live code spawns a tiger. | live (no x/y) | `node/server_functions.js:2646`, `node/server_functions.js:2690-2694` |
| `halloween` | holiday flag | `true` while `events.halloween` is truthy, else absent | none | `node/server_functions.js:2674-2680` |
| `holidayseason` | holiday flag | Same | none | same |
| `lunarnewyear` | holiday flag | Same | none | same |
| `valentines` | holiday flag | Same | none | same |
| `egghunt` | holiday flag | Same | none | same |
| `anniversary` | event (seasonal) | Present while `events.anniversary === true`, which is the default. The server sets it again on each tick. | `active`, `live`, `next`, round fields | `node/server_functions.js:2340-2343`; `node/logic/anniversary_event.js:121` |
| `duels` | other | Created on the first duel. Never deleted. A duel's entry goes away when the duel ends, so it can be `{}`. | one object for each duel | `node/server.js:12265-12287`; `node/server_functions.js:2899-3011` |
| `blessed_minutes` | other | Present while the server blessing is on. Deleted when it ends. | number | `node/server.js:8288`, `node/server.js:15694-15705` |
| `blessed_by` | other | Same as `blessed_minutes` | string | same |
| `rewards` | other (HARDCORE) | The whole life of a HARDCORE server | slot to name | `node/server_functions.js:3106-3131` |
| `minutes` | other (HARDCORE) | The whole life of a HARDCORE server | number | `node/server_functions.js:3132-3135`, `node/server_functions.js:5681-5687` |

Total: 26 keys.

**Not in S:**

- `goblin` and `hide_and_seek` are `events` switches with empty handlers (`node/server_functions.js:2808-2812`).
- Kill counters spawn `goldenbat`, `goldenbot`, `cutebee`, `manyeye`, `mimic` and `paledino` (`node/server_functions.js:2603-2628`). The server never writes them to `E`.
- The Cave of Many Dreams (`G.events.dreams`) has its own socket event, `cave`, for each player in a run (`node/logic/cave_of_many_dreams.js:1882`). It is not in S.
- The newer server systems in `node/logic/` do not write to `E`: `cavalry.js`, `encouragement.js`, `monster_hunts.js` and `server_information.js`. `server_information.js` holds private data about recent characters on each server for the server itself (`node/logic/server_information.js:3-4`).

## Event lifecycle

### Event switches (`events`)

The global `events` object on the server decides what runs (`node/server.js:302-328`). The seasons are hard-coded there. In the pinned code, `anniversary` is `true` and every season is off. Some values change at start:

- If `holidayseason` is on, `events.snowman` becomes 60 (`node/server.js:333-335`, `node/server_functions.js:274-275`).
- If `valentines` is on, `events.pinkgoo` becomes 60 (`node/server.js:336-338`).
- The HARDCORE setup sets `events.egghunt = 0.1` (`node/server_functions.js:147`).
- The DUNGEON server turns every switch off, and every number becomes 9999999999 or stays 0 (`node/server.js:402-408`).

Only the scheduler and the end of an event change the switches at run time (`node/server_functions.js:2391`, `node/server_functions.js:2400`, `node/server_functions.js:2503`, `node/server_functions.js:2514`). `start_event()` (`node/server_functions.js:3034`) has no callers.

### Daily and nightly scheduler

- Every second, `event_loop` computes the local hour `ch = (UTC hour + 24 + time_offset) % 24` (`node/server_functions.js:2378`).
- When `ch` is in `schedule.dailies` (13 or 20), the next event of the queue `["crabxx", "goobrawl", "abtesting"]` starts. The server shuffles this queue at boot (`node/server.js:329-330`).
- When `ch` is 23, the next event of `["icegolem", "franky"]` starts (`node/server.js:331-332`).
- The started event moves from the front of its queue to the back. Then `events[name] = true` (`node/server_functions.js:2386-2402`).
- The scheduler does nothing in the first 2 minutes after the server starts. `last_daily` stops an hour from starting two events.
- Result: two dailies and one nightly each day, in turn.

| Event | Spawn location | S entry | End | Join (`socket.emit("join", {name})`) |
|---|---|---|---|---|
| `crabxx` (Giga Crab) | `main`, at the `crabx` pack (`node/server_functions.js:2033-2046`) | Live form + `end`, from the tick after the spawn | After 2400 s (`G.events.crabxx.duration`), when no player attacked it for 20 s. Or when it dies (`node/server_functions.js:2492-2520`). | Moves you to `main` (−1000, 1700) when you are more than 200 px away (`node/server.js:12611-12614`) |
| `franky` | `level2w`, first pack (`node/server_functions.js:2072-2084`) | Same | Same, 2400 s | Moves you to `level2w` (−300, 150) (`node/server.js:12615-12618`) |
| `icegolem` | `winterland`, box [782, 396, 889, 450], roams (`node/server_functions.js:2085-2092`) | Same | Same, 2400 s | Moves you to `winterland` (820, 425) when you are more than 100 px away (`node/server.js:12619-12622`) |
| `goobrawl` | The `goobrawl` map. While it has fewer than 6 monsters, each tick adds a `bgoo` with chance 0.3. 1 % of those are an `rgoo` instead (`node/server_functions.js:2565-2580`). | `{end}` | 540 s (`node/server_functions.js:2558-2564`) | Moves you to the `goobrawl` map (`node/server.js:12607-12610`) |
| `abtesting` | The `abtesting` instance, created at the start. Players who used `signup` move in, split into teams A and B (`node/server_functions.js:2213-2240`). | `{end, signup_end, A, B, id}` | 480 s. The winning team gets the `abtesting` exchange table. The losers get `abtesting_loser`. Then the server removes the instance (`node/server_functions.js:2815-2851`). | Accepted for 120 s after the start, or later if you rejoin with the same `id`. You get a random team, or your saved one (`node/server.js:12623-12650`). |

`crabxx` has one more rule. While the big crab `crabx` lives, Giga Crab takes only 1 damage from each hit (`node/server_functions.js:2532-2543`).

`join` fails with `no_merchants`, `cant_when_sick` (hopsickness), `cant_in_bank` or `cant_join` (`node/server.js:12593-12655`). A name works only while its `events[...]` switch is on, or while `E.abtesting` exists for A/B Testing. A late A/B join fails with `join_too_late`. `G.events[name].join` is `true` for these five events. The browser `smart_move` calls `join` when `G.events[name].join` and `S[name]` are both truthy (`js/runner_functions.js:2503-2504`).

The server also sends these messages:

- At a boss spawn: `game_event` `{name, map, x?, y?}` (`node/server_functions.js:2017-2211`).
- At the end or defeat of a boss: `notice` (`node/server_functions.js:2499-2514`).
- For A/B Testing: `server_message` at the start and at the result.
- For Goo Brawl: `notice` at the start and at the end.

**Server bug:** At the end of A/B Testing, a winner or loser with a full inventory makes the loop call `socket.emit`. No variable `socket` exists in that scope (`node/server_functions.js:2841-2846`). This appears to throw a `ReferenceError`, which the `try` of `event_loop` catches. If so, the remaining players get no prize and the server does not remove the instance. This reading is not confirmed at run time.

### Seasonal bosses

The `eventmap` list ties each boss to its season (`node/server_functions.js:2639-2649`).

| Season switch | Boss | Spawn location | Respawn (`G.monsters[x].respawn`) |
|---|---|---|---|
| `halloween` | `mrpumpkin` | Its pack in the map data (`node/server_functions.js:2093-2114`) | 3240 s |
| `halloween` | `mrgreen` | Its pack in the map data | 5640 s |
| `halloween` | `slenderman` | A random spot on `cave`, `halloween` or `spookytown`. It teleports when shot, when a player comes within 600 px, or every 2 minutes (`node/server_functions.js:2115-2124`, `node/server_functions.js:2404-2441`). | 600 s |
| `holidayseason` | `grinch` | Its pack in the map data. It then hunts random players (see below). | 43200 s |
| `holidayseason` | `snowman` | `winterland` [682, −967, 1482, −779] (`node/server_functions.js:2047-2062`) | 3600 s |
| `lunarnewyear` | `dragold` | `cave` [1018, −940, 1385, −624] (`node/server_functions.js:2063-2071`) | 10800 s |
| `valentines` | `pinkgoo` | A random pack on `main`, `cave`, `halloween` or `winterland` (`node/server_functions.js:2018-2032`) | 3600 s |
| `egghunt` | `wabbit` | A random pack on `main`, `cave`, `halloween`, `winterland`, `tunnel`, `mansion` or `winter_cave`. It roams (`node/server_functions.js:2135-2149`). | 3600 s |

`create_instance` skips packs with `special` (`node/server_functions.js:1921-1923`). Thus these bosses appear only through `spawn_special_monster` (`node/server_functions.js:2017`).

Lifecycle while the season switch is on (`node/server_functions.js:2650-2673`):

1. If the boss is not alive and has no timer, the server sets a timer. The first time, it is now + 120 s. After a kill, the timer is 0, so it is now + `respawn` seconds. Then `E[x] = {live: false, spawn}`, and the server sends S.
2. When the timer passes, the boss spawns. `E[x]` becomes the live form, and the server sends S.
3. While the boss lives, each tick updates `hp`, `target`, `x` and `y` (`node/server_functions.js:2695-2710`). The tick does not update `slenderman`.
4. When the boss dies, `monster_c[x]` is 0. On the next tick, step 1 starts again.

The Grinch hunts. With no target, it picks a random online player with chance `0.1 × players` on each tick. It skips players below level 50 with chance 0.92, and players on `safe`, instance or `irregular` maps (`node/server_functions.js:2762-2793`). A target in the `xmassweater` chest item makes it stop (`node/server_functions.js:2743-2752`).

**Off-season snowman.** `holidayseason` is off, but `events.snowman` is 1200 (minutes) by default. A snowman spawns `events.snowman × 60` seconds (20 h) after the last one is gone (`node/server_functions.js:2630-2637`). S has a `snowman` entry only while it lives.

These bosses have no `join` handler. Go to `S[x].map`, `x` and `y` yourself. The browser client offers a link that calls `smart_move(S[x])` (`js/html.js:369-383`).

### Anniversary

The anniversary event runs while `events.anniversary === true` (`node/server_functions.js:2245-2247`). It is the default in the pinned code (`node/server.js:303`). Each `event_loop` tick calls `anniversary_tick()` first (`node/server_functions.js:2376`, `node/server_functions.js:2310`).

1. The server splits time into 30-minute slots. A round can start only in the first 5 minutes of a slot (`node/logic/anniversary_event.js:13-14`, `node/logic/anniversary_event.js:129-142`).
2. At the round start, the server picks one target from the eligible online characters (`node/logic/anniversary_event.js:109-120`). The previous target is not picked again if another one exists. A character of age 30 days or less and level 40 or less counts 4 times. An active (not AFK) character counts 4 times.
3. Every other online character gets the condition `anniversary_visit` for 5 minutes (`node/logic/anniversary_event.js:151-157`).
4. A visitor with that condition uses the skill whose `emote` is `ikissyou` on the target, within 80 px (`node/server.js:9816`, `node/server.js:10066`, `node/logic/anniversary_event.js:198-225`). Each visitor gets a cake slice for their account and an `anniversarygift`. The target gets the same for their own account.
5. `E.anniversary` updates on each tick. The server sends S when the value changes. A new round also sends a `server_message` (`node/server_functions.js:2340-2372`).

Eligible targets must be on `main`, `winterland`, `desertland`, `halloween`, `hut`, `woffice` or `d_e`, not in an instance (`node/logic/anniversary_event.js:15`, `node/logic/anniversary_event.js:60-73`). They must be near the map's first spawn point (600 px) with a free walk to it (`node/server_functions.js:2249-2265`).

The server also adds the NPC `anniversary_baker` to `main` while the event is on (`node/server_functions.js:2310-2338`). Recipes with `quest: "anniversary_baker"` work only then.

### Duels

Duels use the socket event `duel` (`node/server.js:12191`):

- `{event: "challenge"}` sends a challenge (`node/server.js:12204`).
- `{event: "accept"}` creates a `duelland` instance and adds `E.duels[id]` (`node/server.js:12218-12287`).
- `{event: "enter", id}` lets party members join (`node/server.js:12309`).

Each tick, `event_loop` counts down the instance's `info.seconds`. It starts the duel and ends it when one side has no active players. At the end, it names the winner, deletes `E.duels[id]` and sends S (`node/server_functions.js:2899-3008`).

**Server bug:** On each tick, the loop copies `instance.active` and `instance.seconds` into the S entry (`node/server_functions.js:3009-3010`). These fields live in `instance.info`, not on the instance. After the first tick, `E.duels[id].active` and `.seconds` are `undefined`, so JSON leaves them out. Read the countdown from the `map_info` event (`instance.info`) instead (`node/server_functions.js:3011`).

### Server blessing

A player who spends shells sets `S.blessed_minutes = 4320` (3 days) and `S.blessed_by` in saved server data (`node/server.js:8288-8289`). The server then calls `bless_loop` at once, and every 60 s after that (`node/server.js:8298`, `node/server.js:15718`). `bless_loop` decreases the minutes by 1. It copies them to `E.blessed_minutes` and `E.blessed_by`. It gives every player the `patronsgrace` condition. At 0, it deletes both keys (`node/server.js:15694-15716`).

`bless_loop` does not send S itself. The change reaches clients with the next `server_info`, up to 24 s later.

### HARDCORE servers

`init_server` replaces `E` with `{rewards, minutes}` (`node/server_functions.js:3105-3135`). That removes `schedule`. `event_loop` first calls `anniversary_tick()`, so an `anniversary` key can still appear. Then it reads `E.schedule.time_offset` (`node/server_functions.js:2378`). On HARDCORE, this appears to throw on every tick, so none of the events above run. This reading is not confirmed at run time.

On HARDCORE, state arrives through `hardcore_info` and the 24 s `server_info`. `hardcore_loop` decreases `minutes` every 60 s. It also sets `rewards.leader` to the highest-level character. At 0, it mails the rewards and stops the server (`node/server_functions.js:5670-5689`).
