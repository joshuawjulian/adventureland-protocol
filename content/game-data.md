# G: the game data object

G is one large object that holds all static game data: items, monsters, maps, skills and more. The browser client and your own client read it. The game server keeps its own copy. Data numbers on this page come from the live G with version 17478. Bare source paths point into the live game's code (`node/server.js:123`, `js/old_common_functions.js:826`, `main.js:443`).

## Getting G

| Step | Detail |
|---|---|
| URL | `GET https://adventure.land/data.js`. The web server serves it with `web_assets.serve_data` (`main.js:14`). The site's pages load it as `/data.js?v=<VERSION>&cache=1` (`htmls/base.html:29`, `htmls/index.html:64`). The server reads only the `reload` parameter. `v` and `cache` only change the URL for the browser cache. |
| Format | JavaScript, not JSON: `var G=<json>;\n` (`web_assets.js:52`). To get the JSON, remove the `var G=` prefix and the `;\n` suffix, then parse the rest. With `?reload=1`, the server adds two more lines: `add_log(...)` and `apply_backup()` (`web_assets.js:9`, `web_assets.js:55`). |
| Source of the data | `get_browser_data()` (`main.js:443`). It builds G from the `design/*.js` files that the web process loads at start (`main.js:54-77`). It reads `geometry` from the database records `MP_<map.key>` for each map without `ignore` (`main.js:444-449`). |
| Size | The compact JSON of version 17478 (no spaces, UTF-8) is 2,804,513 bytes (about 2.7 MB). `geometry` is 2,186,880 bytes of that (about 2.1 MB). The "Bytes" column below uses a different measure (JSON with spaces), so its numbers are larger. |
| Version number | `G.version` is the global `Version` from `version.js` (`main.js:30`, `main.js:451`). The game server reads the same file at its own start (`node/server.js:134`). It sends `G.version` as `version` in the socket `welcome` event (`node/server.js:4983`). Each game server also stores it as its `version` in the server list (`node/server.js:450`). The live G reports 17478. The pinned `version.js` says 15555. The source does not show how the deploy sets the live value (unclear from the source). |
| Caching on the server | The web process keeps one encoded copy in memory and rebuilds it every 30 s (`web_assets.js:36`, `web_assets.js:139-145`). A request never rebuilds it when a copy exists (`web_assets.js:69`). The reply has an `ETag` (a SHA-256 of the body) and `Cache-Control: public, no-cache` (`web_assets.js:12`, `web_assets.js:67`). With `?reload=1`, the reply has `Cache-Control: no-store`. |
| Compression | The server sends gzip when the request accepts it. If the request accepts neither gzip nor identity, the reply is HTTP 406 (`web_assets.js:24-33`). |
| When to fetch again | Compare `version` from `welcome` with the `version` of your cached copy. If they differ, fetch G again. Also fetch again when the socket event `reloaded` (`{change}`) arrives. The game server sends it after a live reload of its design files (`node/server.js:651`, `node/server.js:733`). The browser client then loads `/data.js?reload=1&timestamp=...` (`js/game.js:3120-3124`, `js/functions.js:7354-7363`). |
| Caching on your side | Store G under its version number, for example `G_17478.json`. Reuse the file while the version stays the same. |

**Note:** A live reload does not always change `G.version`. The web process also builds `data.js` from the design files that it loaded at its own start (`main.js:54-77`). The source does not show that `reload_server` refreshes the web process too. After `reloaded`, the new `data.js` can still hold the old data (unclear from the source).

**The browser client after a reload.** `apply_backup()` puts the old `G.maps` back and keeps generated geometry (`js/functions.js:7365-7370`). Thus the browser keeps its map data across a live reload.

**Generated maps are not in `data.js`.** The Cave of Many Dreams builds map floors at run time. The game server adds them to its own `G.maps` and `G.geometry` (`node/logic/generated_maps.js:55-64`). A client gets them through the socket event `map_chunk` in parts of 12,000 characters (`node/logic/generated_maps.js:178-221`).

**The game server's copy is different.** The game server does not download `data.js`. It evaluates the same `design/*.js` files and builds two objects (`node/server.js:470-549`):

- `G` has the keys of `data.js` except `docs`, `drops`, `upgrades`, `compounds` and `monster_gold` (`node/server.js:510-539`).
- `D` holds `upgrades`, `drops`, `compounds` and `monster_gold`, plus `odds` (`node/server.js:543-549`). No design file defines `odds`, so `D.odds` is `false`.
- `sprocess_game_data()` then changes both objects (`node/server_functions.js:42`). It also calls `process_game_data()` (`node/server_functions.js:163`, `js/old_common_functions.js:157`).

Thus some values that the server uses are not the values in `data.js`. The main example is `items[x].a` (see the items table). The server-side constants `B` are not part of G (`node/server.js:213-241`). They include `dist` 400, `sell_dist` 400, `door_dist` 112, `transporter_dist` 160 and `max_vision` 1000.

**Other ways to read G.** The token JSON API at `/mcp_api/get_game_data` and `/mcp_api/search_game_data` returns sections of the design data (`mcp_api.js:302-333`, `mcp_api.js:372-389`). It has no `version` key, no `geometry`, no `upgrades`, no `compounds` and no `monster_gold`. It needs a token (`mcp_api.js:3005-3008`). A full section has a lower rate limit (`mcp_api.js:146`).

## The top-level tables

G 17478 has 33 top-level keys. "Bytes" is the size of `json.dumps(value)`. "Server" tells where the game server keeps the table.

| Key | What it is | Entries | Bytes | Server | Example key(s) |
|---|---|---|---|---|---|
| `version` | Integer data version | (int) | 5 | `G` | `17478` |
| `achievements` | Named achievements. Some give an item title. | 17 | 1,590 | `G` | `reach40`, `firehazard`, `abtesting` |
| `animations` | Sprite-sheet animations | 100 | 11,890 | `G` | `burst`, `slash1` |
| `monsters` | Monster definitions | 149 | 68,149 | `G` | `goo`, `bee`, `franky` |
| `sprites` | Sprite sheets and the names in them | 187 | 36,525 | `G` | `rimedjinn` |
| `maps` | Map metadata: NPCs, monster packs, doors, spawn points, flags | 54 | 45,930 | `G` | `main`, `cave`, `bank` |
| `geometry` | Tiles, placements and collision lines for each map | 49 | 2,632,063 | `G` | `main`, `goobrawl` |
| `npcs` | NPC definitions | 141 | 42,482 | `G` | `scrolls`, `transporter` |
| `tilesets` | Tileset image files | 26 | 1,567 | `G` | `castle`, `water` |
| `imagesets` | Icon atlases | 8 | 874 | `G` | `skills`, `pack_20` |
| `items` | Item definitions | 638 | 166,778 | `G` | `blade`, `hpot0`, `gem0` |
| `sets` | Set bonuses by number of pieces | 21 | 5,611 | `G` | `wanderers` |
| `craft` | Craft recipes, keyed by the output item | 134 | 13,484 | `G` | `firebow` |
| `titles` | Item properties (`item.p`) | 14 | 1,332 | `G` | `shiny`, `glitched` |
| `tokens` | Token shops | 4 | 887 | `G` | `funtoken`, `pvptoken` |
| `dismantle` | Dismantle recipes, keyed by the input item | 21 | 1,308 | `G` | `daggerofthedead` |
| `conditions` | Buffs and debuffs (`entity.s[name]`) | 89 | 18,932 | `G` | `cursed`, `mluck` |
| `cosmetics` | Cosmetic layout and bundles | 18 | 11,439 | `G` | `bundle`, `head` |
| `projectiles` | Projectile visuals | 44 | 3,907 | `G` | `fireball` |
| `classes` | Character classes | 7 | 8,459 | `G` | `warrior`, `merchant` |
| `dimensions` | Sprite size and collision box | 81 | 1,995 | `G` | `goo` |
| `levels` | XP to finish each level | 200 | 3,794 | `G` | `"1"` to `"200"` |
| `upgrades` | Upgrade odds | 3 | 436 | `D` | `"0"`, `"1"`, `"2"` |
| `compounds` | Compound odds | 3 | 344 | `D` | `"0"`, `"1"`, `"2"` |
| `monster_gold` | Base gold for each monster type | 134 | 2,140 | `D` | `goo` (20) |
| `positions` | Icon and texture rectangles in atlases | 873 | 25,541 | `G` | `stone` |
| `skills` | Skills and abilities | 131 | 36,078 | `G` | `attack`, `5shot` |
| `games` | Tavern game settings | 5 | 3,012 | `G` | `slots`, `poker` |
| `events` | Event metadata | 12 | 66,387 | `G` | `goobrawl`, `dreams` |
| `images` | Image path to `{width, height, type}` | 225 | 19,346 | `G` | `/images/tiles/...` |
| `multipliers` | Economy constants | 6 | 139 | `G` | `shells_to_gold` |
| `docs` | Guide, tutorial and CODE reference data | 12 | 30,917 | global `docs` | `tutorial`, `rewards` |
| `drops` | Drop tables and exchange tables | 92 | 54,700 | `D` | `monsters`, `maps`, `gem0` |

## The important tables in detail

### items (638)

The key of an item definition is the item name. An inventory item is `{name, q?, level?, p?, stat_type?, l?, v?, ...}`. The stats of an item come from that instance plus `G.items[name]`, through `calculate_item_properties` (see the formulas below).

Item `type` values and their counts:

| Group | Types (count) |
|---|---|
| Gear | weapon 98, chest 36, helmet 33, orb 27, ring 26, gloves 25, shoes 22, amulet 21, pants 16, earring 16, cape 15, belt 14, shield 12, source 6, quiver 6, misc_offhand 2 |
| Upgrade materials | pscroll 22, uscroll 5, cscroll 4, offering 3, booster 3 |
| Use and trade | material 72, elixir 33, quest 25, gem 23, misc 8, pot 7, cosmetics 6, box 5, dungeon_key 5, throw 4, token 4, tool 3, stone 3, bank_key 3, chrysalis 3 |
| Other | placeholder 2, jar 2, stand 2, computer 2, spawner 2, skill_item 2, test 1, tome 1, licence 1, qubics 1, xp 1, tracker 1, activator 1, flute 1, petlicence 1, container 1 |

| Field | Type | Count | Meaning | How the live code uses it |
|---|---|---|---|---|
| `name`, `skin`, `explanation` | str | 638, 638, 349 | Display name, icon name (a key of `positions`), tooltip | Client only |
| `type` | str | 638 | Item category (list above) | Equip slot logic. Upgrade needs a `uscroll` or `pscroll` (`node/server.js:7179`). Compound needs a `cscroll` (`node/server.js:6923`). Token shops need `token` (`node/server.js:6690`). |
| `g` | int | 638 | Base gold value | NPC price is `quantity * g` (`node/server.js:8442`). It is the base of `calculate_item_value` too. |
| `s` | int | 236 | Maximum stack size. No `s` means the item does not stack. | `can_stack` (`js/old_common_functions.js:407`). A buy caps the quantity at `s` (`node/server.js:8416`). Without `s`, the quantity is 1. |
| `e` | int | 45 | Quantity that one exchange uses. The item is exchangeable. | The `exchange` handler needs `D.drops[name]`, or `D.drops[name + level]` for an upgradable or compoundable item. It takes `e` items (`node/server.js:6642-6656`). Values: 1 (40 items), 20 (2), 10, 40, 50. |
| `quest` | str | 10 | The NPC that exchanges this item | The exchange distance check uses `G.quests[quest]`, else the main Exchanger (`node/server.js:6647`) |
| `grades` | [int×4] | 375 | Levels at which the item reaches grade 1, 2, 3 and 4. `0` means the item starts at that grade. | `calculate_item_grade`, default `[9,10,11,12]` (`js/old_common_functions.js:773`). Most common: `[0,7,10,12]` (62), `[0,0,9,10]` (42), `[0,0,6,7]` (35). |
| `upgrade` | dict | 263 | Stat gain for each upgrade level. The item is upgradable. | `calculate_item_properties` adds it for each level, times a level multiplier (`js/old_common_functions.js:1022`) |
| `compound` | dict | 111 | Stat gain for each compound level. The item is compoundable. | Same function, with other multipliers (`js/old_common_functions.js:1031`) |
| `tier` | number | 245 | Item tier | At +10, an item with tier 3 or more and a `stat` gets 2 more `stat` (`js/old_common_functions.js:1045`) |
| `a` | bool or 2 | 188 | Announce level. In `data.js` it is the design value (150 × `true`, 38 × `2`). | The game server replaces it for every item at load. It uses `round(value / 5,000,000)` of the item at +7 (upgradable), +3 (compoundable) or +0. `event` makes it 2 and `rare` makes it 12 (`node/server_functions.js:54-71`). |
| `edge` | int | 16 | More levels for the `a` value | `node/server_functions.js:57`, `node/server_functions.js:60` |
| Stat fields: `armor`, `resistance`, `attack`, `range`, `speed`, `hp`, `mp`, `str`, `dex`, `int`, `vit`, `for`, `luck`, `gold`, `xp`, `evasion`, `reflection`, `lifesteal`, `manasteal`, `crit`, `critdamage`, `apiercing`, `rpiercing`, `dreturn`, `frequency`, `mp_cost`, `mp_reduction`, `output`, `courage`, `mcourage`, `pcourage`, the `*resistance` fields, `miss`, `stun`, `blast`, `explosion`, `breaks`, `charisma`, `cuteness`, `awesomeness`, `bling` | number | varies | Flat stat bonuses | `calculate_item_properties` adds them. `apply_stats` then adds them to the player (`node/server.js:1288`). |
| `stat` | int (gear) or str (`pscroll`) | 154 | On gear: stat points for a stat scroll. On a `pscroll`: the stat name, for example `"str"`. | An upgrade with a `pscroll` sets `item.stat_type` (`node/server.js:7527`). Then `prop[stat_type] += stat * mult[stat_type]` (`js/old_common_functions.js:1059`). |
| `scroll` | bool | 122 | The item takes stat scrolls | Design time only: it adds `stat` and `upgrade.stat` (`design/items.js:2272-2280`). No live server reference. |
| `extra_stat`, `protection` | int, bool | 87, 22 | Design values | Only the design code reads them (`design/items.js:2277-2291`). No live server reference. |
| `exclusive` | bool | 100 | Keeps the item out of the `glitch` and `lglitch` tables | Design time only (`design/drops.js:1737`, `design/drops.js:1755`) |
| `wtype` | str | 101 | Weapon type (`bow`, `staff`, `fist`, ...) | Class weapon modifiers (`node/server.js:1544`). Skill `wtype` checks (`node/server.js:9875`). |
| `damage_type` | str | 99 | `physical`, `magical` or `pure` | The mainhand value replaces the class value in an attack (`node/server.js:3257-3259`) |
| `projectile` | str | 32 | Projectile for attacks | The mainhand value replaces the class value (`node/server.js:3241-3243`) |
| `class` | [str] | 82 | Classes that get the stats | `calculate_player_stats` ignores the item for other classes (`node/server.js:1522`) |
| `set` | str | 110 | Set name, a key of `G.sets` | Counted for set bonuses (`node/server.js:1555`) |
| `ability`, `attr0`, `attr1` | str, number | 41, 32, 2 | Weapon ability and its values | `player.a[ability] = {attr0, attr1}` (`node/server.js:1534`) |
| `aura` | str | 1 | Aura from the item | `node/server.js:1540` |
| `gain` | str | 3 | Booster stat: `xp`, `luck` or `gold` | An active booster in the inventory sets `player["x" + gain]` (`node/server.js:1475-1478`) |
| `days` | int | 6 | Booster duration in days | Compound of boosters (`node/server.js:7108`) |
| `ignore` | bool | 35 | Hidden or retired item | A shell purchase fails with `invalid` (`node/server.js:8168`). It also keeps the item out of the `glitch` tables (`design/drops.js:1737`). |
| `cash` | int | 6 | Price in shells (`cosmo0` to `cosmo5`) | `buy_with_cash` cost is `cash * quantity` (`node/server.js:8177`). It also changes the value formula. |
| `markup` | int | 2 | Value divisor (`scroll3` 10, `cscroll3` 20) | `calculate_item_value` (`js/old_common_functions.js:788`) |
| `grade` | number | 17 | Grade of a scroll or offering | The scroll grade must be at least the item's grade (`node/server.js:6923`, `node/server.js:7182`). A higher grade raises the odds. `scroll4` has grade 3.6. A failed upgrade with it does not destroy the item (`node/server.js:7489-7494`). |
| `offering` | number | 5 | Ingots and nuggets: the grade for a "shiny" roll | An upgrade with only such an item and no scroll can make the item `shiny` (`node/server.js:7217-7274`) |
| `gives` | [[stat, amount]] | 8 | Potion effect | `node/server.js:7838` |
| `cooldown` | int | 6 | Potion cooldown in ms | `node/server.js:7871` |
| `duration` | number | 33 | Elixir duration in hours | `node/server.js:7797-7799` |
| `withdrawal` | str | 4 | Condition after the elixir ends | `node/server.js:7793-7794` |
| `charge` | int | 3 | Charges that a skill takes (`skills[x].slot`) | `node/server.js:9982` |
| `legacy` | dict | 4 | Stat changes when `item.p == "legacy"`. `null` removes the stat. | `js/old_common_functions.js:1049` |
| `<class>` or `<map>` (`warrior`, `paladin`, `rogue`, `cave`, `halloween`, `spookytown`, `crypt`, `winterland`) | dict | 1 to 3 | More stats for that class or on that map | `adopt_extras` in `calculate_item_properties` (`js/old_common_functions.js:886`) |
| `event`, `rare` | bool | 23, 2 | Event or rare item | They set `a` on the server |
| Client fields: `cx`, `xcx`, `skin_a`, `skin_r`, `skin_c`, `trex`, `acolor`, `hat`, `stand`, `onclick`, `action` | various | 1 to 144 | Visual and UI data | Client only |
| Other fields: `multiplier` (22), `opens`, `eat`, `throw`, `unlocks`, `spawn`, `monster`, `npc`, `credit`, `note`, `special`, `xscroll`, `gold_reward`, `cavalry`, `delia`, `nopo`, `debuff`, `projectile_test` | various | 1 to 22 | Specific to one item | `multiplier` appears in the item tooltip (`js/html.js:5049`). An item with `debuff` removes non-persistent debuffs (`node/server.js:7862-7866`). For the others, the use is unclear from the source. |

At load, the game server adds these fields (`node/server_functions.js:43-73`):

- `igrade` is `calculate_item_grade(def)` at level 0: the base grade 0, 1 or 2. It selects the row of the `upgrades` and `compounds` tables. The server sets `lostearring.igrade` to 2 (`node/server_functions.js:73`).
- `igrace` is 1, -1 or -2 for base grade 0, 1 or 2. It is part of the upgrade grace.
- `a` gets its new value (see the `a` row).

`process_game_data` also adds fields, on the server and in the browser (`js/old_common_functions.js:157-259`):

- `G.items[x].id` is the item key.
- `G.items[x].buy` is `true` when an NPC sells the item for gold.
- `G.items[x].buy_with_cash` is `true` when an NPC lists a `cash` item. Such an item is not for sale for gold, except with `p2w` (`js/old_common_functions.js:239-243`). No item in G 17478 has `p2w`.

**Server bug:** For a `p2w` item, the server multiplies the buy cost by `G.inflation` (`node/server.js:8444`). G has no `inflation` key, so the cost would be `NaN`. No live item has `p2w`, so this bug has no effect now.

```json
"blade": {"type":"weapon","wtype":"short_sword","tier":1,"skin":"blade","damage_type":"physical",
  "upgrade":{"range":1.5,"attack":4},"name":"Blade","g":8400,"grades":[7,9,10,12],"range":5,"attack":15}
"intring": {"type":"ring","skin":"intring","int":2,"compound":{"int":2},"name":"Ring of Intelligence","g":24000,"grades":[3,5,6,7]}
```

### monsters (149)

| Field | Type | Count | Meaning | How the live code uses it |
|---|---|---|---|---|
| `name`, `skin` | str | 149 | Display name and sprite | Client |
| `hp`, `attack`, `range`, `frequency`, `speed`, `xp`, `damage_type`, `aggro`, `rage`, `armor`, `resistance`, `evasion`, `avoidance`, `reflection`, `dreturn`, `apiercing`, `rpiercing`, `crit`, `lifesteal`, `explosion`, `for`, `phresistance`, `difficulty` | number or str | varies | Base stats | `new_monster` copies these fields, and some flags, to the monster (`node/server.js:13496-13538`). `max_hp` is `hp` (`node/server.js:13566`). |
| `mp` | int | 142 | Design value `ceil(hp*2/100)` | The server ignores it and computes the same formula (`node/server.js:13539`) |
| `charge` | int | 61 | Speed while the monster has a target | `node/server.js:1793`. Without `charge`, `process_game_data` sets it from `speed` (×1.2 to ×2, `js/old_common_functions.js:160-168`). |
| `respawn` | number | 149 | Seconds until a new monster appears. `-1` means never. | Above 200, the delay is `respawn × (720 to 1200)` ms. Else it is `respawn × 1000 + (0 to 900)` ms (`node/server.js:13360-13385`). A `grow` pack at 2/3 of its count or less gets a new monster after 25 ms (`node/server.js:13369-13370`). |
| `respawn_as` | str | 3 | The type of the next monster in the pack | `node/server.js:13426-13427` |
| `aggro` | 0 to 1 | 149 | Chance to attack nearby players | Above 0.99 the monster always becomes aggressive. Else the chance is `aggro` on each check (`node/server.js:14317`). |
| `rage` | 0 to 1 | 142 | How long a monster stays on its target | If the target did not attack for 20 s, the monster stops when `random > rage × 0.99` (`node/server.js:14397`). An aggressive monster takes a new target with chance `rage − player.aggro_diff` (`node/server.js:15178`). |
| `cooperative` | bool | 27 | Shared-credit boss | Each player's share is `points^0.65 / total` (`node/server.js:2724`). Every 10 players raise `B.drop_table_multiplier` by 1 (`node/server.js:2733`). |
| `special` | bool | 14 | No automatic respawn | `node/server.js:13360-13362` |
| `stationary`, `roam` | bool | 25, 10 | Does not move, or walks around | `node/server.js:14416`, `node/server.js:14543`. A `stationary` pack uses `monster_gold` as its gold (`node/server_functions.js:228`). |
| `humanoid` | bool | 30 | Humanoid flag | Damage rules (`node/server_functions.js:3366`) |
| `announce` | str (color) | 18 | Server message on spawn | `node/server.js:13621-13640` |
| `difficulty` | number | 43 | Gold multiplier. `0` means no gold. | `node/server_functions.js:226`, `node/server.js:2415` |
| `abilities` | dict | 42 | Monster skills, for example `{"weakness_aura":{"aura":true,"condition":"weakness","radius":100,"cooldown":4000}}` | It becomes `monster.a` (`node/server.js:13543-13545`) |
| `spawns` | [[interval or "hp:x", type, count?]] | 17 | Helpers that appear while the monster has a target | `node/server.js:14321-14330` |
| `s` | dict | 3 | Start conditions | `node/server.js:13540-13542` |
| `slots` | dict | 25 | Equipped items | Copied to the monster |
| `achievements` | [[kills, "stat", stat, amount]] | 114 | Permanent bonus at a kill count | With a tracker, `calculate_player_stats` adds them (`node/server.js:1496`) |
| `rbuff`, `cbuff` | str, list | 3, 5 | Condition for each player with kill credit. `cbuff` is `[[max_level, condition], ...]`. | `node/server.js:2742-2752` |
| `1hp`, `global`, `immune`, `peaceful`, `drop_on_hit`, `escapist`, `supporter`, `passive`, `poisonous` | bool | 1 to 16 | Behavior flags | `1hp`: global drop odds ×1000 (`node/server.js:2286`). `global`: the chest appears at the player (`node/server.js:2421`). `immune`: only skills with `pierces_immunity` hit (`node/server.js:3435`). |
| `aa`, `hit`, `unlist`, `cute`, `hide`, `orientation`, `prefix`, `size`, `explanation`, `projectile`, `charge_skin`, `balance`, `trap`, `pet`, `operator`, `goldsteal` | various | 1 to 32 | Mostly visual | Client, or unclear from the source |

```json
"goo": {"name":"Goo","speed":6,"charge":12,"hp":100,"xp":100,"attack":5,"damage_type":"physical","respawn":1,
  "range":15,"frequency":0.4,"aggro":0,"aa":1,"achievements":[[10,"stat","hp",5],[100,"stat","hp",10]],
  "skin":"goo","rage":0,"mp":2}
```

**Server bug:** `process_game_data` sets `max_hp` only for monsters without `charge`, because the loop skips them first (`js/old_common_functions.js:162`, `js/old_common_functions.js:169`). The server does not depend on it, because `new_monster` sets `max_hp` itself.

### maps (54)

| Field | Type | Count | Meaning |
|---|---|---|---|
| `key` | str | 54 | Database key of the geometry (`MP_<key>`) |
| `name` | str | 54 | Display name |
| `npcs` | list | 54 | `{id, position:[x,y,dir?]}`, `{id, positions:[...]}` or `{id, boundary}`. `id` is a key of `G.npcs`. |
| `monsters` | list | 53 | Monster packs (see below) |
| `doors` | list | 54 | `[x, y, w, h, to_map, to_spawn, own_spawn, flag?, extra?]` (see below) |
| `spawns` | list | 54 | `[x, y, direction?, scatter?]` arrival points |
| `quirks` | list | 40 | `[x, y, w, h, kind, ...]` clickable objects: `sign`, `upgrade`, `compound`, `info`, ... |
| `on_death` | [map, spawn] | 8 | Where a character goes on respawn. Default: `on_death` of the start map, else `["main", 0]` (`node/server.js:6301`). |
| `on_exit` | [map, spawn] | 7 | Where a character goes at login if the map is closed (`node/server.js:11744-11748`) |
| `instance` | bool | 10 | Instanced map |
| `ignore` | bool | 5 | Disabled map with no `geometry` |
| `pvp` | bool | 6 | PvP on any server (`is_in_pvp`, `node/server_functions.js:483`) |
| `safe` | bool | 6 | No hostile skills or attacks (`node/server.js:9894`, `node/server.js:3447`) |
| `mount` | bool | 4 | Bank maps: to enter one opens your bank (`node/server_functions.js:1916`) |
| `irregular` | bool | 5 | Left out of some monster lists and Grinch targets (`node/server_functions.js:2768`) |
| `drop_norm` | int | 38 | Old drop normalizer. No live code reads it. Drop odds use `max_hp / 1000` (`node/server.js:2280`). |
| `lux` | number | 40 | Light level (client) |
| `seasonal_npcs` | list | 1 | NPCs for a season. The anniversary baker comes from here (`node/server_functions.js:2318`). |
| `animatables` | dict | 2 | Animated scenery. An entry with `collision` adds collision lines to the geometry (`js/old_common_functions.js:201-215`). |
| `outside`, `day`, `weather`, `fx`, `world`, `machines`, `zones`, `traps`, `ref`, `event`, `code`, `loss`, `safe_pvp`, `small_steps`, `no_bounds`, `unlist`, `freeze_multiplier`, `burn_multiplier`, `old_monsters` | various | 1 to 12 | Other data. `zones` has fishing and mining areas. `machines` has the tavern game positions. `ref` has named points. |

`process_game_data` adds these fields to each map without `ignore` (`js/old_common_functions.js:194-256`):

- `data`: the map's `G.geometry` entry.
- `items`: item name to the NPCs on this map that sell it.
- `merchants`: all NPCs with `items`.
- `ref`: NPC id to `{map, in, x, y, id}`.
- `upgrade`, `compound` and `exchange`: the coordinates of those NPCs.
- It also fills `G.quests`: quest key to NPC coordinates.

Pack fields:

| Field | Meaning |
|---|---|
| `type`, `count` | Monster type and number of monsters |
| `boundary`, `position` + `radius`, `polygon`, `random` | Where the monsters appear |
| `boundaries` with `stype: "randomrespawn"` | A list of `[map, x1, y1, x2, y2]`. Each respawn picks one. |
| `grow`, `roam`, `special` | Growth, free walking, no automatic spawn |
| `rage` | A box. Players inside it become targets (`node/server.js:13955-13990`). |
| `gatekeeper` | While this monster lives, a `"protected"` door stays closed (`node/server.js:5961-5970`). |

**Doors.** A door works when you are within `B.door_dist` (112) of a `w × h` box at `spawns[door[6]]`. `data.s` must equal `door[5]` (`node/server.js:5924-5943`). Index 7 can be:

- `"ulocked"`: a bank vault. It needs `user.unlocked[map]` (`node/server.js:5974`).
- `"protected"`: closed while a `gatekeeper` lives.
- `"key"`, with the key item at index 8. These doors use the socket event `enter`.

```json
"main": {"key":"jayson_ALMap2_v2","name":"Mainland",
  "npcs":[{"id":"newupgrade","position":[-207,-220]}],
  "monsters":[{"type":"crab","boundary":[-1353,-254,-1052,122],"count":8,"grow":true}],
  "doors":[[-965,-176,24,30,"woffice",0,1],[168,-149,32,40,"bank",0,3]],
  "spawns":[[0,0,0,100],[-968,-163],[535,1677]]}
```

### geometry (49)

`G.geometry[name]` exists for each map without `ignore` (49 of 54).

| Field | Count | Meaning |
|---|---|---|
| `min_x`, `min_y`, `max_x`, `max_y` | 49 | Map bounds |
| `x_lines` | 48 | `[x, y1, y2]` vertical walls, sorted by x. `can_move` tests them (`js/old_common_functions.js:1499`). |
| `y_lines` | 48 | `[y, x1, x2]` horizontal walls, sorted by y |
| `tiles` | 49 | `[tileset, x, y, w, h?, ...]`: a rectangle of `G.tilesets[tileset].file` |
| `default` | 48 | Index of the background tile |
| `placements` | 49 | `[tile, x, y]` or `[tile, x1, y1, x2, y2]` ground tiles |
| `groups` | 42 | Multi-tile objects |
| `animations`, `lights`, `nights` | 2, 4, 1 | Animated tiles and light layers (client) |
| `polygons` | 6 | Named polygons, for example fishing zones |
| `points`, `rectangles` | 15 | Editor markers. No game code reads them. |

The collision box of an entity comes from `set_base` (`js/old_common_functions.js:1352`). If `G.dimensions[type][3]` exists, `base.h` is that value and `base.v` is `min(9.9, dimensions[4])`. Else the box comes from the sprite size.

### npcs (141)

| Field | Count | Meaning |
|---|---|---|
| `id`, `name`, `skin`, `color`, `cx` | 141, 132, 141, 85, 51 | Identity and visuals |
| `role` | 141 | Behavior. Counts: `items` 48, `citizen` 30, `merchant` 10, `quest` 6, `cavalry` 4, and one each of 43 other roles (`newupgrade`, `compound`, `exchange`, `transport`, `craftsman`, `locksmith`, `scrollsmith`, `anniversary_crafter`, `dreamkeeper`, ...). |
| `items` | 12 | Shop list (item names and `null` gaps). A buy needs you within `B.sell_dist` (400) of one seller (`node/server.js:8426`). |
| `places` | 1 | Transporter: `{map: spawn_index}` (`node/server.js:5951`) |
| `quest` | 12 | Quest or exchange key. `process_game_data` puts the NPC's coordinates in `G.quests` (`js/old_common_functions.js:253`). |
| `token` | 4 | Token item for a token shop NPC |
| `cavalry` | 4 | Stats of a cavalry sentry (`node/logic/cavalry.js:269`) |
| `market` | 1 | `citizen22` (Merrit Wick) only: the settings of the market patron (`node/logic/market_patron_runtime.js:6-7`). `areas` (rectangles on `main` where a stand qualifies), `npc_clearance`, `stand_clearance`, `front_clearance`, `front_width` (space around a stand), `settle_ms` (time a stand stays in place first), `anchor_tolerance`, `max_observation_gap`, `hour_ms` (time between rewards for one account), `radius`, `stops`, `handoff`, `shell_floor`, `shell_zero` (the shell chance) (`node/logic/market_patron.js:4-70`). `exchange` is the same table as `drops.marketparcel`. The client shows `chase` and the shell chances (`js/html.js:8468`). |
| `citizen_lamp_stops` | 1 | `citizen20` (Wick, `citizen_behavior: "lamplighter"`) only: `[[x, y], ...]`. At each stop, the server sends `citizen` `{type: "lamp", x, y}` to clients nearby (`node/server.js:15447-15465`). |
| `says`, `interaction`, `side_interaction`, `type`, `atype`, `aspeed`, `speed`, `level`, `hp`, `delay`, `seek`, `moving`, `citizen_behavior`, `steps`, `pack`, `slots`, `class`, ... | various | Dialogue, animation and citizen movement |

```json
"scrolls": {"role":"merchant","items":["scroll0","cscroll0","strscroll","intscroll","dexscroll","scroll1","cscroll1",null,null,null,"scroll2","cscroll2",null,null],
  "skin":"scrolls","says":"Good Luck","name":"Lucas","id":"scrolls"}
```

### skills (131)

`type` counts: `skill` 86, `monster` 19, `utility` 13, `ability` 9, `passive` 1, `gm` 1, none 2. The socket `skill` handler checks the fields below (`node/server.js:9764`).

| Field | Count | Meaning and server use |
|---|---|---|
| `name`, `skin`, `explanation`, `type` | 131, 120, 129, 129 | Identity |
| `mp` | 79 | MP cost. The check needs `mp × (100 − mp_reduction) / 100` (`node/server.js:9842`). |
| `level` | 40 | Minimum character level (`node/server.js:9849`) |
| `cooldown` | 81 | Own cooldown in ms, kept in `player.last[name]`. For `attack`, the handler sets it to `player.attack_ms` on each call (`node/server.js:9778`). |
| `share`, `cooldown_multiplier` | 10, 8 | The skill uses the cooldown and last use of `share`, times `cooldown_multiplier` (`node/server.js:9855-9858`) |
| `reuse_cooldown` | 4 | Cooldown when `cooldown` is absent (`node/server.js:9860`) |
| `class` | 65 | Classes that can use it. A GM can use all skills (`node/server.js:9871`). |
| `wtype` | 13 | Needed mainhand weapon type, a string or a list (`node/server.js:9875`) |
| `offhand_type` | 1 | Needed offhand (`node/server.js:9889`) |
| `hostile` | 45 | Fails on a `safe` map. Cannot target yourself (`node/server.js:9894`). |
| `target` | 38 | `true`, `"player"` or `"monster"` (`node/server.js:9899`) |
| `global` | 1 | No range check and no vision check |
| `emote`, `no_self` | 15, 4 | Emote skills. You need the cosmetic `emote` in `p.acx` (`node/server.js:9827`). |
| `requirements` | 1 | `player[k] >= v` for each key (`node/server.js:9954`) |
| `slot` | 10 | `[[slot, item], ...]`. You need one of these items equipped. It uses `G.items[item].charge` charges (`node/server.js:9962-9990`). |
| `range`, `range_multiplier`, `range_bonus`, `fixed_range` | 35, 4, 3, 2 | Range is `range` or `player.range`, times `range_multiplier`, plus `range_bonus`. `player.xrange` adds to it unless `fixed_range` (`node/server.js:10001-10027`). |
| `use_range` | 18 | Client hint: the skill uses the attack range |
| `max_targets` | 1 | Target cap for multi-target skills (`node/server.js:9799`) |
| `consume` | 7 | Item that one use takes (`node/server.js:10033`) |
| `condition`, `duration`, `duration_min`, `duration_max` | 36, 36, 3, 3 | Condition and its duration |
| `merchant_use` | 1 | `node/server.js:3211` |
| `exclusive_condition` | 2 | Condition that the skill removes (`node/server.js:3637`) |
| `heal` | 3 | The skill heals (`heal`, `partyheal`, `selfheal`). `commence_attack` sets `info.heal` and `info.positive` (`node/server.js:3271-3276`). |
| `kill_buff` | 1 | Condition that the attacker gets when the skill kills the target. `purify` gives `purifier` (`node/server.js:4287-4288`). |
| `max` | 1 | `stack` only: the cap of the rogue stack bonus. Each rogue hit adds 1 to `target.s.stack.s`, up to `max` (2000). The hit adds that number to its damage (`node/server.js:4020-4024`). |
| `armor_multiplier`, `armor_cap` | 1, 1 | `shield_slam` only: damage is `attack × damage_multiplier + min(max(armor, 0), armor_cap) × armor_multiplier` (`node/server.js:3416-3420`) |
| `rpiercing` | 1 | `arcane_needle` only: resistance piercing of the hit (500) (`node/server.js:3347`) |
| `apiercing` | 1 | `piercingshot` only (500). The server does not read it. It uses a fixed `info.apiercing = 500` (`node/server.js:3344`). |
| `mp_return_levels` | 2 | `aether_shield`, `guardians_oath`: `[[level, ratio], ...]`. A paladin gets back `floor(hp_loss × ratio)` MP, with the ratio of the highest level reached, up to `max_mp` (`node/server.js:3620-3632`). |
| `link_range` | 1 | `guardians_oath` only: the oath stops when the guardian is farther than this from the target (360) (`node/server.js:3654`) |
| `negative`, `nprop` | 1, 1 | `throw` only: an item is a harmful throw if its name is in `negative`, or if it has one of the `nprop` properties (`attack`, `armor`) (`node/server.js:10316-10322`) |
| `rank_levels`, `states`, `default_state` | 1 each | `paladin_aura` only. The rank is the number of `rank_levels` that the paladin reached. `states[name]` gives `name`, `condition` and `values` (`{stat: [value per rank]}`). A paladin with no valid state gets `default_state` (`node/server.js:15763-15784`). |
| `monsters` | 3 | `true` on `entangle` and `mtangle`, `false` on `4fingers`. The server does not read it (no read found in `node/`). |
| `ui`, `persistent`, `code`, `action`, `toggle`, `skins`, `inventory`, `positive`, `list`, `no_reflection`, `complementary`, `set_speed`, `warning`, `variance` | varies | Client data. The server does not read these from `G.skills` (no read found in `node/`). `arcane_needle` sets `no_reflection` itself (`node/server.js:3348`). |
| `damage_multiplier`, `damage`, `damage_type`, `projectile`, `pierces_immunity`, `procs`, `multi`, `aura`, `party`, `levels`, `ratio`, `output`, `cooldown_group`, ... | varies | Values for one skill |

```json
"supershot": {"type":"skill","class":["ranger"],"name":"Supershot","wtype":["bow","crossbow"],"damage_multiplier":1.5,
  "cooldown":30000,"range_multiplier":3,"range_bonus":20,"mp":400,"target":true,"hostile":true,"damage_type":"physical"}
"5shot": {"class":["ranger"],"level":75,"mp":320,"cooldown_multiplier":1,"multi":true,"share":"attack","damage_multiplier":0.5}
```

### classes (7)

`warrior`, `paladin`, `rogue`, `ranger`, `mage`, `priest`, `merchant`. `calculate_player_stats` reads them (`node/server.js:1301`).

| Field | Meaning and use |
|---|---|
| `stats`, `lstats` | Base stat and stat for each level: `stats + level × lstats`. Add `(level − 40) × lstats` above 40, `(level − 55) × lstats` above 55 and `(level − 65) × lstats` above 65. Subtract `(level − 80) × lstats` above 80. Then round down (`node/server.js:1430-1445`). |
| `main_stat` | Attack is `item_attack × main_stat / 20`. Paladin uses `str/20 + int/40` (`node/server_functions.js:1745-1751`, `node/server.js:1587`). Priest attack is ×1.6 (`node/server.js:1590`). |
| `attack`, `hp`, `mp`, `armor`, `resistance`, `range`, `speed`, `frequency`, `output`, `mp_cost`, `damage_type`, `courage`, `mcourage`, `pcourage`, and the element resistances `bmresistance`, `fzresistance`, `phresistance`, `pnresistance`, `stresistance` | Base values |
| `mainhand`, `doublehand`, `offhand` | `{wtype: stat changes}` for the weapon types the class can use (`node/server.js:1544`, `node/server.js:1549`) |
| `base_slots`, `looks`, `xcx` | Start equipment and looks. `process_game_data` adds free cosmetics to `xcx` (`js/old_common_functions.js:171-182`). |
| `projectile`, `description`, `side_stat`, `brave` | Visual and other data |

```json
"ranger": {"stats":{"str":3,"dex":10,"int":8,"vit":2,"for":1},"lstats":{"str":0.2,"dex":1,"int":0.25,"vit":0.3,"for":0.02},
  "main_stat":"dex","attack":45,"hp":160,"mp":60,"speed":45,"range":15,"frequency":0.4,"armor":10,"resistance":80}
```

### conditions (89)

An entity keeps conditions as `entity.s[name] = {ms, ...}`. `calculate_player_stats` adds the stat fields of each condition, and of the `entity.s` entry, to the player (`node/server.js:1566-1573`). `add_condition` uses `duration` when the caller gives no time (`node/server_functions.js:3236`). If `defense` names a stat, the target resists with chance `target[defense] / 100` (`node/server_functions.js:3246-3250`).

| Field | Count | Meaning |
|---|---|---|
| `name`, `skin`, `explanation`, `ui` | 89, 88, 87, 70 | Display |
| `duration`, `duration_min` | 70, 4 | Default time in ms |
| `buff`, `debuff` | 44, 29 | Kind. Purify and similar effects remove them unless `persistent` (`node/server.js:4026-4034`). |
| `persistent`, `cleansable` | 20, 20 | Removal rules. `cleansable` conditions are the ones that cleanse removes (`node/server.js:10225`). |
| `technical`, `aura`, `channel`, `blocked`, `can_move`, `special`, `encouragement` | 1 to 6 | Flags |
| Stat fields: `speed`, `frequency`, `luck`, `gold`, `xp`, `output`, `armor`, `resistance`, `incdmgamp`, `evasion`, `str`, `dex`, `for`, `courage`, `mcourage`, `pcourage`, `mp_cost`, `avoidance`, `lifesteal`, ... | varies | Stat changes |
| `frequencym`, `potionsm`, `healm` | 2, 1, 1 | Multipliers |
| `defense` | 5 | Stat that resists it |
| `interval`, `damage`, `heal`, `intensity`, `phases`, `set_speed`, `cap_reflection` | 1 to 4 | Values for one condition |
| `attr0` | 1 | `sanguine` (`lifesteal`): the name of a field. When an aura condition reaches a player nearby, the server copies `player.aura[name].attr0` of the source into that field of the condition (`node/server.js:15910-15913`). |

```json
"cursed": {"name":"Cursed","skin":"skill_curse","ui":true,"output":-20,"incdmgamp":20,"speed":-20,"duration":5000,"debuff":true,"cleansable":true}
```

### levels (200)

`G.levels["N"]` is the XP to go from level N to N+1. The keys are the strings `"1"` to `"200"`. The server sets `max_xp = G.levels[level]` and levels up while `xp >= max_xp` (`node/server.js:1305-1316`). Examples: `"1"` 200, `"2"` 250, `"50"` 5,800,000, `"100"` 300,000,000,000, `"200"` 940,000,000,000,000.

### upgrades / compounds (3 each)

Shape: `[igrade][new_level] = base chance`. `igrade` is the base grade of the item (0, 1 or 2). `new_level` is the level to reach, as a string key. `upgrades` covers +1 to +12. `compounds` covers +1 to +10. The game server reads them from `D.upgrades` and `D.compounds`.

| | +1 | +2 | +3 | +4 | +5 | +6 | +7 | +8 | +9 | +10 | +11 | +12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| upgrades 0 | .9999999 | .98 | .95 | .70 | .60 | .40 | .25 | .15 | .07 | .024 | .14 | .11 |
| upgrades 1 | .99998 | .97 | .94 | .68 | .58 | .38 | .24 | .14 | .066 | .018 | .13 | .10 |
| upgrades 2 | .97 | .94 | .92 | .64 | .52 | .32 | .232 | .13 | .062 | .015 | .12 | .09 |
| compounds 0 | .99 | .75 | .40 | .25 | .20 | .10 | .08 | .05 | .05 | .05 | | |
| compounds 1 | .90 | .70 | .40 | .20 | .15 | .08 | .05 | .05 | .05 | .03 | | |
| compounds 2 | .80 | .60 | .32 | .16 | .10 | .05 | .03 | .03 | .03 | .02 | | |

**Upgrade with a `uscroll`** (`node/server.js:7134`):

1. The base is `p0 = upgrades[def.igrade][new_level]` (`node/server.js:7323`).
2. The grace sum is `max(0, min(new_level + 1, item.grace + min(3, player ugrace / 4.5) + def.igrace) + min(6, server ugrace / 3) + player ograce / 3.2)` (`node/server.js:7325-7330`).
3. Then `grace = p0 × grace / new_level + grace / 1000` (`node/server.js:7345`).
4. If the scroll grade is above the item's grade and `new_level <= 10`, the chance is `p × 1.2 + 0.01` (`node/server.js:7352-7353`).
5. An offering multiplies the chance by 1.08 to 1.7 and adds a grace term. The multiplier depends on the offering grade against the item grade (`node/server.js:7360-7381`).
6. Without an offering, the chance gets `max(0, grace / 4.8 − 0.4 / (new_level − 0.999)²)` (`node/server.js:7388-7389`).
7. The cap is `min(p0 + 0.36, p0 × 3)` with a higher scroll or offering, else `min(p0 + 0.24, p0 × 2)` (`node/server.js:7403-7407`).

Two hidden rules change the roll. If you upgrade the same inventory slot as `player.p.item_num`, the roll becomes lower with chance 0.6 (`node/server.js:7397-7400`). With chance 0.025, the item gets 1 more grace (`node/server.js:7392-7395`).

**Compound with a `cscroll`** (`node/server.js:6862`):

1. `igrade` is `def.igrade`. At level 3 or more, it is the grade at `level − 2` (`node/server.js:6946-6948`).
2. The base is `p0 = compounds[igrade][new_level]` (`node/server.js:6954`).
3. A scroll with a higher grade gives `p × 1.1 + 0.001` (`node/server.js:6958-6959`).
4. An offering gives ×1.08 to ×1.64 plus grace (`node/server.js:6967-6996`). Without one, the chance gets `min(0.175, grace) / max(level − 1, 1)` (`node/server.js:6997-6999`).
5. The cap is `min(p0 × (3 + high × 0.6), p0 + 0.2 + high × 0.05)` (`node/server.js:7013-7016`). Boosters always succeed (`node/server.js:7009-7011`).

Send `calculate: true` in the `upgrade` or `compound` packet to get the chance (`node/server.js:7411`, `node/server.js:7026`).

Other upgrade paths use fixed chances:

- A `pscroll` always uses 0.99999 and needs 1, 10, 100, 1000 or 9999 scrolls for grade 0 to 4 (`node/server.js:7503-7525`).
- An item of type `offering` without a scroll always succeeds. It only adds 0.5 grace to the item (`node/server.js:7275-7306`).
- An item with `offering` and no scroll makes the item `shiny`. The chance is 0.16, or 0.32 for a higher offering. Then multiply by 2.8, 1.6 or 1 for base grade 0, 1 or 2 (`node/server.js:7217-7227`).

### sets (21)

Fields: `name`, `items` (member item names), `explanation`, and the keys `"1"` to `"7"`. Each digit key holds the bonus for that number of pieces. In the data, each tier holds only the new bonus. At load, the server adds the tiers together for 2 up to the number of items (`node/server_functions.js:250-262`). `calculate_player_stats` then applies `G.sets[set][count]` (`node/server.js:1560-1564`). A client must do the same addition.

```json
"wanderers": {"1":{},"2":{"hp":200},"3":{"mp":100},"4":{"gold":10},"5":{"luck":16},"name":"Wanderer's Set",
  "items":["wcap","wattire","wbreeches","wgloves","wshoes"]}
```

### drops (92)

The server keeps this table as `D.drops`. There are two kinds of list, with two kinds of roll.

**1. Independent rolls on a kill** (`roll_monster_drops`, `node/server.js:2277`). Each entry rolls on its own.

| List | An entry drops when | Source |
|---|---|---|
| `drops.maps.global_static` | `random / share / luckm / luckx / global_mult < p` | `node/server.js:2289` |
| `drops.maps.global` | `random / share / luckm / hp_mult / luckx / global_mult < p` | `node/server.js:2297` |
| `drops.maps[map]` | `random / share / luckm / hp_mult / luckx < p` | `node/server.js:2308` |
| `drops.monsters[type]` | `random / (share × luckm × level × mult) < p`, rolled `B.drop_table_multiplier` times | `node/server.js:2331`, `node/server.js:2340` |
| `drops.monsters_home_server[type]` | Same as monster drops, only for players on their home server | `node/server.js:2365` |
| `drops.konami` | Only for the `konami` skin. It replaces all other lists. | `node/server.js:2373` |

In these formulas, `hp_mult` is `monster.max_hp / 1000` (`node/server.js:2280`). `global_mult` is `monster.mult`, times 1000 for a `1hp` monster (`node/server.js:2286`). `luckx` starts at 1 and grows during a fight (`node/server.js:13347`). The anniversary items in `global` drop only while the anniversary event is on. Each account gets one cake slice flavor (`node/server.js:2298-2301`).

**2. Weighted tables.** All other list keys hold weighted tables: `gem0`, `armorbox`, `glitch`, `cosmo0`, `f1` (fishing), `m1` (mining), `<item><level>` for exchangeable upgradable items, and more. One use picks exactly one entry. The chance of an entry is `entry[0] / sum(entry[0])` (`exchange`, `node/server_functions.js:4029`; `chest_exchange`, `node/server_functions.js:4151`).

- A table named `<name>_bonus` gives independent extra rolls after a pick from `<name>` (`node/server_functions.js:4038`, `node/server_functions.js:4145-4148`). G 17478 has `sixcake_bonus` and `cave_finish_bonus`.
- For a table that starts with `cosmo`, the server divides the weight of a cosmetic that you have N times by 10^N (`node/server_functions.js:4043-4050`).
- A `glitch` pick that is upgradable, compoundable or wearable gets the title `glitched` (`node/server_functions.js:4110-4116`).

Entry formats:

| Entry | Meaning |
|---|---|
| `[p, item]` or `[p, item, q]` | Item, optional quantity |
| `[p, item, null, null, title]` | Item with the title `title` (exchange only, `node/server_functions.js:4117-4119`) |
| `[p, "open", table]` | Roll the named weighted table |
| `[p, "gold", amount]` | Gold |
| `[p, "shells", amount]` | Shells |
| `[p, "cx", name]` or `[p, "cxbundle", name]` | Cosmetic. In a chest, `cx` becomes a `cxjar` item (`node/server_functions.js:4175`). |
| `[p, "cxjar", q, data]` | Jar item with data |
| `[p, "empty"]` | Nothing |

Entry counts in G 17478: 1,477 items, 387 `cx`, 39 `gold`, 34 `open`, 24 `cxbundle`, 7 `cxjar`, 6 `shells`, 4 `empty`.

Keys that are not lists:

- `drops.gold` is `{base: 0.64, random: 0.8, x10: 0.03125, x50: 0.00208}` (see the kill gold formula below).
- `drops.maps` has `global`, `global_static` and 9 maps.
- `drops.monsters` has 117 entries. `drops.monsters_home_server` has 8.
- `drops.skins` is `{gold, silver, bronze, normal}`. No live code reads it (unclear from the source).

```json
"monsters": {"goo":[[1.25e-07,"shells",50],[0.0002,"slimestaff"],[0.001,"gslime"]]}
"gem1": [[0.1,"weaponbox"],[0.3,"armorbox"],[0.001,"offering"],[0.001,"shells",50],[1,"open","thrash"],[0.012,"gemfragment"]]
```

### monster_gold (134)

`{monster: base gold}`. The design sets it to the monster's `gold` value, or 1 (`design/monsters.js:1639`). 134 of the 149 monsters have an entry.

The live server uses it less than the name suggests. At load, it computes a gold value for each pack from the monster's HP, speed, attack, defenses and drop value (`node/server_functions.js:167-249`). It stores the result in `D.base_gold[type][map]`, and each monster takes the gold of its pack (`node/server.js:13450`). The kill gold uses `monster_gold` only when the monster has no pack gold (`node/server.js:2391-2394`). Stationary monsters and monsters with negative `xp` use `monster_gold` as their pack gold (`node/server_functions.js:228-230`). The `start` event sends `D.base_gold` to the client (`node/server.js:11929`).

### craft (134) / dismantle (21)

- `craft[output] = {items: [[q, name, level?], ...], cost, quest?, output?}`.
  - The server builds `D.craftmap` from the sorted list of `"name"` or `"name+level"` (`node/server_functions.js:149-162`).
  - A craft needs `cost` gold. You must be near the `craftsman`, or near the `quest` NPC when the recipe has `quest` (`node/server.js:6575-6588`).
  - `output` (1 recipe) gives another item, with optional `data` (`node/server.js:6600-6602`).
  - A recipe with `quest: "anniversary_baker"` works only during the anniversary event (`node/server.js:6571`).
- `dismantle[input] = {items: [[q, name], ...], cost}`. An entry with `q` below 1 is a chance (`node/server.js:6506`). A title without `misc` moves to the outputs (`node/server.js:6509`).

```json
"firebow": {"items":[[1,"bow"],[1,"essenceoffire"]],"cost":20000}
"daggerofthedead": {"items":[[1,"mbones"]],"cost":40}
```

### titles (14)

Item properties, kept as `item.p`. `calculate_item_properties` adds each stat key of the title to the item (`js/old_common_functions.js:1006-1011`). Fields: `title` (display), `type`, `source`, `achievement`, `misc`, `manual`, `improve`, `random_stat`, `stackable`, and stat keys.

- `shiny` and `glitched` have their own code (`js/old_common_functions.js:967-1005`).
- A `glitched` item gets a random +1 to `dex`, `int` or `str`. The result stays in the cache of item stats until a reload, so it is not stable (`js/old_common_functions.js:990`).
- A `stackable` title does not stop stacking (`js/old_common_functions.js:412`). `cavefound` is the only one.
- A `misc` title does not move to a craft or dismantle output (`node/server.js:6509`).

```json
"sniper": {"type":"mainhand","attack":2,"consecutive_200p_range_last_hits":1000000,"source":"achievement","title":"Sniper's"}
```

### achievements (17)

- `name` and `explanation` are display text.
- `count`, `rr` and `title` are for item achievements. `item_achievement_increment` counts on the item. At `count`, the item gets `title` (`node/server_functions.js:5846-5869`). The server sends `achievement_progress` at each step of `rr`.
- `item` and `shells` are level rewards (`reach40` to `reach90`). No live code reads them (unclear from the source).

### tokens (4)

`tokens[token_item][target] = price in tokens` (`exchange_buy`, `node/server.js:6682`).

- A price below 1 means that one token buys `1 / price` units (`node/server.js:6712-6718`).
- A target such as `cxjar-xgravestone2` gives the item `cxjar` with data `xgravestone2` (`node/server.js:6722-6725`).
- You must be within `B.sell_dist` of `G.maps.main.ref[npc or token + "s"]` (`node/server.js:6693`).

```json
"funtoken": {"confetti":0.01,"smoke":0.05,"partyhat":2,"mshield":10,"rabbitsfoot":120,"xshield":200,"exoarm":999}
```

### events (12)

Keys: `anniversary`, `abtesting`, `goobrawl`, `crabxx`, `franky`, `icegolem`, `holidayseason`, `lunarnewyear`, `valentines`, `egghunt`, `halloween`, `dreams`.

| Field | Meaning |
|---|---|
| `name`, `modal`, `sprite`, `announcement` | Display. `announcement` is `{color, accent, effect, text, title?}`, or `false`. |
| `type` | `daily` (4), `nightly` (2) or `seasonal` (6) |
| `duration` | Seconds. The server uses it for the event timers (`node/server_functions.js:2493`, `node/server_functions.js:2552`, `node/server_functions.js:2852`). |
| `join` | The socket event `join` can move you there. The browser `smart_move` uses it with `S` (`js/runner_functions.js:2503`). |
| `disabled`, `party`, `vote_ms`, `xp_multiplier`, `encounters`, `cast`, `merchant_stock`, `rare`, `rewards`, `gold_limit`, `amber_limit`, `camps`, `travelers` | Only on `dreams` (about 63 KB): the Cave of Many Dreams. `node/logic/cave_of_many_dreams.js` reads them (for example lines 110, 202 and 227). |

`G.events` describes the events. It does not switch them on. The server's own `events` object does that (see the S reference).

```json
"franky": {"name":"Franky","modal":"event-franky","sprite":"franky","announcement":{"color":"#9FCF6D","accent":"#C29BE7","effect":"sparks","text":"Franky is awake."},"duration":2400,"join":true,"type":"nightly"}
```

### games (5)

| Game | Fields |
|---|---|
| `dice` | `{}` |
| `wheel` | `min`, `spin`, `sides`, `slices` |
| `slots` | `gold`, `spin`, `draws`, `prizes`, `reels` |
| `poker` | `seats`, `blinds`, `buyin`, `rake`, `rake_cap`, `action_ms`, `bank_ms`, `grace_ms`, `showdown_ms`, `between_ms`, `blind_hands`, `stools`, `reach`, `block`, `ranks`, `suits`, `hands` |
| `tarot` | `npc`, `cards`, `hours` |

The tavern modules read `wheel`, `slots` and `poker` (`node/logic/tavern_wheel.js:12`, `node/logic/tavern_slots.js:33`, `node/logic/tavern_poker.js:7`). No live server code reads `dice` or `tarot`. Machine positions are in `G.maps.tavern.machines`.

### docs (12)

The web process loads `docs` from `docs/directory.js` and puts it in `data.js` (`main.js:80`, `main.js:482`). The game server loads the same file as a global `docs`, not as `G.docs` (`node/server.js:114`).

| Key | Shape | What the live code does with it |
|---|---|---|
| `tutorial`, `merchant_tutorial` | lists of lessons (37, 5) | The tutorial API checks tasks and lessons against them (`api.js:1553-1569`, `adventure_functions.js:1154-1188`) |
| `tasks` | dict (33) | Valid tutorial task names (`api.js:1560`) |
| `rewards` | `{"c0": [[1, "open", "cosmo0"]]}` | The socket event `ureward` gives `c0` once for each account, after the tutorial (`node/server.js:5184-5229`). Other names do nothing. |
| `interactions`, `interaction_map` | dicts (33, 6) | Client: help cards for NPCs, quirks, machines and doors (`js/game.js:876`, `js/game.js:1180-1191`) |
| `functions`, `documented` | lists of 215 CODE function names | Client: code hints and links (`js/functions.js:751`, `js/functions.js:2726`) |
| `guide`, `references`, `javascript`, `images` | lists and dicts | Client guide pages (`js/functions.js:738`, `api.js:2096`) |

### dimensions (81)

`[width, height, x_disp?, base.h?, base.v?]` for each sprite name. The first three are visual size and offset. Indices 3 and 4 set the collision box (`set_base`, `js/old_common_functions.js:1352`).

Examples: `"goo": [23,22,-3,1,6]`, `"default_character": [26,35]`.

### positions (873)

Most entries are `[imageset_or_tileset, col, row]` (860). Ten entries are `[tileset, x, y, w, h]`. Three entries have other lengths (1, 6 and 7). Item and skill `skin` values are keys here.

Examples: `"teaser_witch": ["teasers",0,0]`, `"stone": ["outside",672,104,16,20]`.

### cosmetics (18)

A dict with mixed shapes:

- `default_*_place`, `default_*_position` and `head_y`: numbers.
- `bundle` (`{name: [cosmetic names]}`) and `map` (`{old: new}`). `map_cx` and `all_cx` use them (`js/old_common_functions.js:274`, `js/old_common_functions.js:289`).
- `head`, `hair`, `hat`, `back`, `prop`, `head_animation`, `hat_animation`, `gravestone`, `no_upper`: layout data for each cosmetic.

### multipliers (6)

`{extra_shells: 0, shells_to_gold: 32000, buy_to_sell: 0.6, secondhands_mult: 2, secondhands_cash_mult: 3, lostandfound_mult: 4}`.

- `shells_to_gold` gives shells a gold value in `calculate_xvalue` (`node/server_functions.js:315`).
- `buy_to_sell` matches the default 0.6 in `calculate_item_value`. The function has its own hard-coded 0.6 and does not read this key (`js/old_common_functions.js:787`).
- For the other keys, the use is unclear from the source.

### Smaller asset tables

These tables are for the client only.

| Table | Entry shape |
|---|---|
| `animations` | `{file, frames, continuous?, alpha?, speed?, directional?, aspeed?, framefps?, scale?, size?, ...}` |
| `projectiles` | `{animation, speed, hit_animation, instant?, ray?, hit_text?, pure?}` |
| `sprites` | `{file, rows, columns, matrix, type?, size?, skip?, frames?}`. `matrix` names the sprite in each cell. `type` is `"full"` when absent (`js/old_common_functions.js:184-193`). |
| `tilesets` | `{file, frames?, frame_width?, light?}` |
| `imagesets` | `{file, size, rows, columns, load?}` |
| `images` | `{path: {width, height, type}}` |

## Formulas that read G

| Need | Function | Location | What it does |
|---|---|---|---|
| Item grade | `calculate_item_grade(def, item)` | `js/old_common_functions.js:773` | Returns 0 to 4: the number of `def.grades` levels that `item.level` reaches. Default `[9,10,11,12]`. Returns 0 if the item is neither upgradable nor compoundable. |
| Item value | `calculate_item_value(item, m = 0.6)` | `js/old_common_functions.js:783` | See below |
| Item stats | `calculate_item_properties(item, {class, map})` | `js/old_common_functions.js:877` | See below |
| Can stack | `can_stack(a, b, d)` | `js/old_common_functions.js:407` | Same name, total within `s` (`s === true` means 9999), same title unless `stackable`, same `data` for `cxjar`, same PvP mark, not locked (`l`) or blocked (`b`) |
| Damage multiplier | `damage_multiplier(defense)` | `js/old_common_functions.js:826` | Step-wise armor or resistance curve, limited to [0.05, 1.32]. The server uses `target[defense] − attacker[pierce] − info[pierce]` (`node/server.js:4049`). Fortitude uses `for × 5` (`node/server.js:4044`). |
| DPS multiplier | `dps_multiplier(defense)` | `js/old_common_functions.js:844` | The same curve without the limits. Used in the pack gold formula (`node/server_functions.js:184`). |
| Player stats | `calculate_player_stats(player)` | `node/server.js:1301` | Level-up loop through `G.levels`, `classes.stats` and `lstats`, gear through `calculate_item_properties`, class weapon changes, `G.sets`, `G.conditions`, monster achievements, `main_stat` attack |
| Monster stats | `calculate_monster_stats(monster)` | `node/server.js:1786` | Base stats from `G.monsters`, `charge` speed with a target, conditions. Level gives up to 12 steps of +12.5 % attack (+5 % for `grow` packs) (`node/server.js:1814-1826`). At night, speed is ×0.7 (`node/server.js:1828-1830`). |
| XP for a level | `G.levels[level]` | `node/server.js:1305` | XP to finish the current level |
| XP from a kill | `issue_monster_awards`, `issue_monster_award` | `node/server.js:2766`, `node/server.js:2813` | `monster.xp × share × xpm` for a shared kill. `monster.xp × xpm × mult` for a single kill. Merchants get no kill XP in a shared kill (`node/server.js:2763-2765`). |
| Upgrade chance | socket `upgrade` | `node/server.js:7134` | See upgrades / compounds |
| Compound chance | socket `compound` | `node/server.js:6862` | See upgrades / compounds |
| Kill gold and drops | `drop_something(player, monster, share)` | `node/server.js:2381` | Gold is `round(1 + GOLD × 0.64 × share + random × GOLD × 0.8 × share) × level × mult`. `GOLD` is the pack gold, else `monster_gold` (`node/server.js:2391-2400`). Then a 0.03125 chance of ×10 and a 0.00208 chance of ×50 (`node/server.js:2437-2446`). Then the independent rolls. |
| Drop entry to items | `drop_item_logic(drop, def, pvp)` | `node/server.js:2199` | Handles `shells`, `cxjar`, `open` and item entries |
| Weighted roll | `exchange(player, name)` | `node/server_functions.js:4029` | One weighted pick from `drops[name]`, then the `_bonus` rolls |
| Value of a table | `calculate_xvalue(arr, ...)` | `node/server_functions.js:296` | Expected gold value of a drop table. It uses `shells_to_gold`. |
| Load-time fields | `sprocess_game_data()` | `node/server_functions.js:42` | `igrade`, `igrace`, `a`, `D.craftmap`, `D.base_gold`, cumulative `sets`, seasonal global drops |
| Client preprocessing | `process_game_data()` | `js/old_common_functions.js:157` | Monster `charge`, class `xcx`, sprite types, `maps[m].data`, shop locations, `G.quests`, item `id` |
| Movement collision | `can_move(entity)` | `js/old_common_functions.js:1499` | Tests the move of each corner of the `base` box against `x_lines` and `y_lines` |
| Door distance (client) | `is_door_close`, `can_use_door` | `js/old_common_functions.js:1643`, `js/old_common_functions.js:1653` | Within 40 px of the door's spawn point or box. The server uses 112 (`B.door_dist`). |
| Skill checks | socket `skill` | `node/server.js:9764` | MP, level, cooldown or `share`, class, `wtype`, safe map, target, slot charges, range |
| Condition | `add_condition(target, name)` | `node/server_functions.js:3236` | Default duration from `G.conditions`, resistance roll through `defense` |

**Item value.** `calculate_item_value` works like this (`js/old_common_functions.js:783-822`):

1. A `gift` item is worth 1.
2. The base is `g × 0.6`, or `g` for a `cash` item. Divide by `markup` when present.
3. For a compound level i from 1 to the item level: multiply by 3.2 (1.5 for `cash`). Then add `cscroll<grade>.g / 2.4`, where the grade comes from `grades[0]` and `grades[1]`. Boosters instead get ×0.75.
4. For an upgrade level i: multiply by 2 at levels 4 and 5, 2.4 at 6, and 3 from 7. At 9, also ×2.64 and +400,000. At 10, ×5. At 12, ×0.8. Add half of a scroll price for each level.
5. Divide the value of an item with `expires` by 8. Round the result.

**Item stats.** `calculate_item_properties` works like this (`js/old_common_functions.js:877-1067`):

1. Copy the class or map extras of the item, if the wearer matches.
2. Add the title: `shiny`, `glitched`, or the stat keys of `G.titles[p]`.
3. For each level, add `upgrade` or `compound` times a multiplier. Upgrade: +7 ×1.25, +8 ×1.5, +9 ×2, +10 ×3, +11 and +12 ×1.25. Compound: +5 ×1.25, +6 ×1.5, +7 ×2, +8 and more ×3. From level 7, `stat` gets 1 more for each level.
4. Add the base stats of the definition. Apply `legacy`.
5. Round all values except `evasion`, `miss`, `reflection`, `dreturn`, `lifesteal`, `manasteal`, `attr0`, `attr1`, `crit`, `critdamage` and `breaks`.
6. If the item has `stat_type`, convert `stat` to that stat with the factor below.

| Stat | Factor | Stat | Factor |
|---|---|---|---|
| `str`, `dex`, `int`, `vit`, `for`, `luck` | 1 | `gold`, `xp`, `dreturn` | 0.5 |
| `armor`, `resistance`, `apiercing`, `rpiercing` | 2.25 | `speed`, `evasion`, `frequency` | 0.325 |
| `reflection`, `lifesteal` | 0.15 | `manasteal` | 0.04 |
| `crit` | 0.125 | `output` | 0.175 |
| `mp_cost` | −0.6 | | |

**Server bug:** `adopt_extras` has a bug for `upgrade` and `compound` extras. It loops over the keys of the whole extras object, not the keys of `ex.upgrade` (`js/old_common_functions.js:867-869`). Thus class or map extras with an `upgrade` key give wrong values. No item in G 17478 has such extras, so the bug has no effect now.
