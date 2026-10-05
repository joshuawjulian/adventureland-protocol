# Part 3 · Building a bot

## Designing a bot

Parts 1 and 2 gave you the parts of a client. You have `AlSocket`, the login, the game data
**G** and the handshake. You also have the world, the actions and the replies. Part 3 puts them together into a **bot**: a
program that plays one or more characters without a person. At the end of this part, your bot
levels, buys potions, sells loot, wears better gear, upgrades it, and runs a party with a
merchant.

Part 3 adds five modules to the library `albot`, and four programs:

| Module | What it does | Chapter |
|---|---|---|
| `pathfind` | A grid of the walls of a map, and A* on it. | [Distance, range and movement](#learn-distance-range-and-movement) |
| `travel` | Walk around walls, go through doors, use the transporter, leave jail. | [Distance, range and movement](#learn-distance-range-and-movement) |
| `farmer` | The decisions of a fighter: one tick at a time. | [A complete farming bot](#learn-a-complete-farming-bot) |
| `items` | The inventory, NPC shops, equipment, `send`, the bank, upgrades and compounds. | [Supplies, loot and gear](#learn-supplies-loot-and-gear) |
| `party` | Several characters in one program, a party, a new character. | [A party and a merchant](#learn-a-party-and-a-merchant) |

| Program | What it does |
|---|---|
| `farm` | Farms monsters until you stop it. It heals, loots, respawns, leaves jail and reconnects. |
| `supplies` | Farms, and goes to the town when its potions or its bag space run low. |
| `party-merchant` | Three fighters in a party farm. A merchant collects their loot, sells it and banks the gold. |
| `gear-up` | Upgrades a coat to +3 and compounds rings, with a stop rule. |

### Three layers

A bot has three layers. Each layer has one job.

| Layer | Job | In the library |
|---|---|---|
| Connection | Send and receive events. Answer pings. Report a disconnect. | `alsocket` ([AlSocket](#learn-alsocket)) |
| State store | Keep the latest known world: your character (`me`), monsters, chests, cooldowns. | `world`, `cooldowns` ([Reading the world](#learn-reading-the-world)) |
| Decisions | Look at the state. Choose the next action. Send it. | `farmer` and the programs of this part |

```text
                  game server
                      |  WebSocket (Socket.IO frames)
                      v
   +---------------------------------------+
   | Connection (AlSocket)                 |
   |   pings, frames, "disconnect"         |
   +---------------------------------------+
        | events: start, player, entities,     ^ actions: move, attack,
        | death, drop, skill_timeout, ...      | equip, open_chest, ...
        v                                      |
   +----------------------+   reads   +----------------------+
   | State store          |---------->| Decisions: tick()    |
   |  World: me, monsters,|           |  every 100 ms:       |
   |  chests; Cooldowns   |           |  survive > loot >    |
   |  (handlers write it) |           |  fight > walk        |
   +----------------------+           +----------------------+
```

The arrows go one way. Event handlers write the state store and do nothing else. The tick
reads the state store and sends actions. This separation makes the bot easy to test: you can
give the tick a state that you made by hand.

### A tick on a timer

A **tick** is one run of the decision function. The bots of this part run a tick every 100 ms.
Each tick looks at the world and does the most important thing that applies now:

1. If the character is dead, respawn. Do nothing else.
2. If health or mana is low and the potion timer is ready, drink a potion.
3. If a chest waits, open it.
4. If a target is in range and the attack is ready, attack.
5. If no target is in range, walk to one.

The tick does not remember what it did before. Each tick starts again from the top. If a
monster attacks you during a walk, the next tick sees low health and drinks a potion. You do
not need code that cancels the walk.

Some reactions need no timer. When the server sends [`invite`](#recv-invite), a handler can
record it at once. Keep these reactions small. Put each decision that compares several needs in
the tick.

### Do not block

A handler must return quickly. The connection delivers events one at a time. A slow handler
holds back each event after it, and the pings too. The server closes a socket that does not
answer a ping in 12 s (`node/server.js:83-84`).

- Do not wait for a reply inside a handler.
- Do not run a long search (for example a path search) inside a handler. Run it in the tick.
- A tick can wait for a reply, as `request` does. The handlers still run during the wait.

> **Caution:** In Go, C#, Rust and Java, handlers run on a different thread from the tick. The
> library keeps each state behind one lock. Do not hold a lock while you send: the send can
> wait.

Part 2 already has the two other parts of the design. [Cooldowns](#learn-hearing-back) tells
when each skill and the potion timer are ready. The budget of [Call-cost and
kicks](#learn-hearing-back) keeps each socket below the call-cost limit. Each module of Part 3
sends through them.

### Project layout

Part 2 had you copy the complete library of your language into your project. The new modules of
this part are in the same folder. If your copy is older than this part, copy these files again:

| Language | Module files | Program files |
|---|---|---|
| JavaScript | `albot/pathfind.js`, `travel.js`, `farmer.js`, `items.js`, `party.js` | `farm.js`, `supplies.js`, `party-merchant.js`, `gear-up.js` |
| TypeScript | the same names with `.ts` | the same names with `.ts` |
| Python | `albot/pathfind.py`, `travel.py`, `farmer.py`, `items.py`, `party.py` | `farm.py`, `supplies.py`, `party_merchant.py`, `gear_up.py` |
| Go | the folders `pathfind/`, `travel/`, `farmer/`, `items/`, `party/` | `cmd/farm/`, `cmd/supplies/`, `cmd/party-merchant/`, `cmd/gear-up/` |
| C# | `Albot/Pathfind.cs`, `Travel.cs`, `Farmer.cs`, `Items.cs`, `Party.cs` | the folders `Farm`, `Supplies`, `PartyMerchant`, `GearUp`, each with its `.csproj`, and `Course.sln` |
| Rust | `src/pathfind.rs`, `travel.rs`, `farmer.rs`, `items.rs`, `party.rs`, and `src/lib.rs` | `src/bin/farm.rs`, `supplies.rs`, `party-merchant.rs`, `gear-up.rs` |
| Java | `src/main/java/albot/Grid.java`, `Travel.java`, `Farmer.java`, `Items.java`, `Party.java` | `src/main/java/Farm.java`, `Supplies.java`, `PartyMerchant.java`, `GearUp.java` |

The `actions` module keeps only the actions of Part 2. Part 3 puts its new actions in the new
modules.

### Before a bot plays on the live game

> **Warning:** The rules of the game allow code, but they do not clearly allow a client that
> you wrote yourself. The rule says: "you can do pretty much everything with Code, and the
> game, we are even exploring allowing non-UI botting". It continues: "but, please don't DDOS
> the game, or intentionally abuse bugs you find" (`languages/en/pages.js:1162-1163`). The bots of this part are
> non-UI clients. Read the current rules in the game before you run one. You accept the risk.

| Safe | Risky |
|---|---|
| Log in with the password one time, then use `AL_AUTH`. | A password login on each start. At 200 tokens, the account loses all of them ([Logging in](#learn-logging-in-and-choosing-a-server)). |
| [The reconnect rule](#learn-alsocket): 30 s, then double, at most 300 s. | A reconnect after a few seconds. Many fast logins look like an attack ("don't DDOS the game"). |
| Each event through the budget. The programs of this part stay far below 150 call-cost in 4 s. | More than 200 call-cost in 4 s: the server disconnects the character ([Call-cost and kicks](#learn-hearing-back)). |
| At most 3 fighting characters and 1 merchant online (`languages/en/docs.js:4954`). | More characters through a second account, a VPN or a second computer (`languages/en/pages.js:1168-1169`). |
| Code that you tested on the test server first. | New code on the live game. A `move` to a point that is not walkable sends the character to jail. |
| Some contact with other players, on average once each week. | A bot that plays 24/7 with no contact. The account can get a temporary ban (`languages/en/docs.js:4918`). |

> **Caution:** Do step 2 of [Before you start](#learn-before-you-start) (one login through the
> Steam or Mac App Store client) before a bot plays. Else each character that your program
> logs in can get the condition `authfail`: luck −85%, gold −85%, xp −20%
> (`node/server.js:11856-11870`).

To move a program from the test server to the live game:

1. Run it on the test server, and compare its output with the output in this part.
2. Unset `AL_BASE_URL`. The programs then use `https://adventure.land`.
3. Set `AL_AUTH` to your token (from `login` in [Logging in](#learn-logging-in-and-choosing-a-server)).
4. Set `AL_SERVER` to a normal server near you, for example `EUI` or `USI`.
5. Set `AL_CHARACTER` to the name of your character, with the same capital letters.
6. Unset `AL_RECONNECT_MS`. The live default is 30 s.

> **Caution:** Do not choose a server whose name contains `PVP` or `HARDCORE`. On those servers,
> other players can attack your character (`node/server.js:416`), and a death can drop items
> ([Servers, regions and PvP](#game-what-adventure-land-is)).

## Distance, range and movement

To attack, you must be in range. To be in range, you must walk. To walk, you must know where
the walls are. This chapter explains how the map stores walls, how a bot finds a path, and how
it goes to other maps. It adds the modules `pathfind` and `travel`.

### Coordinates and range

A position is `x` and `y` in map pixels. `y` grows down. The `x` of an entity is the middle of
its body, and `y` is its feet. Each map has its own coordinates. Two entities on different
maps, or in different instances (`in`), are never in range. `speed` is in pixels per second: a
character with a `speed` of 55 walks 55 px in 1 s.

The server measures range as the gap between two hit boxes, not between two centres.
`World.distance` does the same ([Distance and range](#learn-reading-the-world)). Your
`range` comes from the class and the weapon. A mage has a `range` of 170 with the starter
staff: 120 from `G.classes.mage.range` and 50 from `G.items.staff.range`. A warrior with the
starter blade has 23.

An NPC service has its own distance. The server measures it between the two positions, not the
boxes:

| Service | Distance | Source |
|---|---|---|
| [`buy`](#send-buy), [`sell`](#send-sell), [`upgrade`](#send-upgrade), [`compound`](#send-compound) | 400 px from the NPC | `B.sell_dist`, `node/server.js:220` |
| [`send`](#send-send) to another character | 400 px, same map | `B.dist`, `node/server.js:219` |
| A door ([`transport`](#send-transport)) | 112 px from the box of the door | `B.door_dist`, `node/server.js:221` |
| The transporter NPC | 160 px | `B.transporter_dist`, `node/server.js:223` |

### Walls: G.geometry

[`G.geometry[map]`](#g-geometry) holds the walls of each map. There are two lists of line
segments:

- `x_lines`: vertical walls, each `[x, y1, y2]`.
- `y_lines`: horizontal walls, each `[y, x1, x2]`.

`min_x`, `min_y`, `max_x` and `max_y` give the edges of the map. Nothing else blocks a walk.
NPCs and monsters do not block you.

### Why a straight line is not enough

[`move`](#send-move) sends `going_x, going_y`, and the server walks you in a straight line. The
server does not go around a wall for you. It also checks the two points of each `move`.

> **Warning:** The server checks your reported position `x, y` and your destination
> `going_x, going_y` on its walk map, `smap_data` (`node/server.js:11211-11245`). If either
> point is not walkable, the server logs a "Line violation" and sends the character to the map
> `jail`. A character that another player hit in PvP (the `block` condition) also dies
> (`defeat_player`, `node/server.js:4499-4531`). Never send a `move` to a point that you did not
> check.

The test server is stricter: a `move` whose straight line crosses a wall also sends the
character to jail. A bot that walks around walls passes both checks. So a bot needs
**pathfinding**: a search for a walkable route around the walls.

### A grid and A*

`pathfind` makes a grid in three steps:

1. **Make a grid.** Divide the map into square cells of 8 px. Block each cell where the
   character's box, standing there, touches a wall. The box of a player is 8 px to each side,
   7 px up and 2 px down from its feet (`node/server.js:185`). Add half a cell of margin.
2. **Find the inside.** The walls do not tell which side is inside the map. Start at the spawn
   points in `G.maps[map].spawns`, and mark each free cell that you can reach from a spawn. The
   server makes its own walk map the same way (`node/server_functions.js:4732`). Only these
   cells are walkable.
3. **Search.** A* finds the shortest route of cells. Its estimate is the octile distance,
   which never overestimates on a grid with diagonal steps.

The route has a point every 8 px. Each `move` costs 2.5 call-cost, so `findPath` **smooths** the
route. From each point, it jumps to the farthest later point that a straight line reaches. A
straight line is clear when each point on it, every 4 px, is in a walkable cell. The result is
a short list of **waypoints**, and each waypoint is one `move`.

The grid of `main` has about 200,000 cells. `Grid.forMap` builds it one time for each map and
keeps it.

<!-- include course/js/albot/pathfind.js region=grid -->

<!-- include course/ts/albot/pathfind.ts region=grid -->

<!-- include course/python/albot/pathfind.py region=grid -->

<!-- include course/go/pathfind/pathfind.go region=grid -->

<!-- include course/csharp/Albot/Pathfind.cs region=grid -->

<!-- include course/rust/src/pathfind.rs region=grid -->

<!-- include course/java/src/main/java/albot/Grid.java region=grid -->

`findPath` is the search and the smoothing:

<!-- include course/js/albot/pathfind.js region=find-path -->

<!-- include course/ts/albot/pathfind.ts region=find-path -->

<!-- include course/python/albot/pathfind.py region=find-path -->

<!-- include course/go/pathfind/pathfind.go region=find-path -->

<!-- include course/csharp/Albot/Pathfind.cs region=find-path -->

<!-- include course/rust/src/pathfind.rs region=find-path -->

<!-- include course/java/src/main/java/albot/Grid.java region=find-path -->

![The Mainland town with a grid of 8 px cells, a straight line through a fountain and an A* path around it](img/learn/pathfinding.png "An illustration on the Mainland town art, with a grid of 8 px cells. The straight line to the goal crosses the fountain. A* finds a path around it.")

### Walking a path

`Travel.walkTo(x, y)` asks the grid for a path and walks it with `moveTo` of Part 2, one
waypoint at a time. If the goal is not walkable, it walks to the nearest walkable point. It
stops and returns false when something changes the plan: a `correction`, a death, a door or
jail. The next tick then decides again.

<!-- include course/js/albot/travel.js region=walk-to -->

<!-- include course/ts/albot/travel.ts region=walk-to -->

<!-- include course/python/albot/travel.py region=walk-to -->

<!-- include course/go/travel/travel.go region=walk-to -->

<!-- include course/csharp/Albot/Travel.cs region=walk-to -->

<!-- include course/rust/src/travel.rs region=walk-to -->

<!-- include course/java/src/main/java/albot/Travel.java region=walk-to -->

### Jail and leave

If a character is in jail, send [`leave`](#send-leave) `{}`. The server sends it to the town:
spawn 0 of `main`, about (0, 0) (`node/server.js:5864-5885`). `leave` fails with
`transport_failed` while the character is dead, and with `cant_escape` on most maps or with
more than 5 monsters on it.

<!-- include course/js/albot/travel.js region=leave-jail -->

<!-- include course/ts/albot/travel.ts region=leave-jail -->

<!-- include course/python/albot/travel.py region=leave-jail -->

<!-- include course/go/travel/travel.go region=leave-jail -->

<!-- include course/csharp/Albot/Travel.cs region=leave-jail -->

<!-- include course/rust/src/travel.rs region=leave-jail -->

<!-- include course/java/src/main/java/albot/Travel.java region=leave-jail -->

### Doors and other maps

A map can lead to other maps in two ways:

- **Doors.** `G.maps[map].doors` lists them. A door is
  `[x, y, width, height, to_map, to_spawn, own_spawn, lock]`. Walk to the spawn point
  `G.maps[map].spawns[own_spawn]`, which is next to the door. Then send
  [`transport`](#send-transport) `{to: to_map, s: to_spawn}`. The server measures 112 px from
  the box of the door. A door with a `lock` value needs a key first.
- **The transporter.** Alia (the NPC `transporter`) stands in some towns. Within 160 px of her,
  `transport` `{to, s}` goes to each place of `G.npcs.transporter.places`: map → spawn.

The server answers `transport` with success, and sends [`new_map`](#recv-new_map) first. The
bank is different. It is a "mount" map, so the answer is `{in_progress: true}`, and `new_map`
comes after the server loads your account (`node/server.js:5983-6050`). `Travel.transport`
waits for `new_map` in both cases. Each map change adds 8 to your call-cost
(`node/server.js:4726`).

<!-- include course/js/albot/travel.js region=transport -->

<!-- include course/ts/albot/travel.ts region=transport -->

<!-- include course/python/albot/travel.py region=transport -->

<!-- include course/go/travel/travel.go region=transport -->

<!-- include course/csharp/Albot/Travel.cs region=transport -->

<!-- include course/rust/src/travel.rs region=transport -->

<!-- include course/java/src/main/java/albot/Travel.java region=transport -->

The doors and the transporter make a **graph of maps**: each map is a node, and each door or
place is an edge. `Travel.route` searches this graph breadth first, so the route has the fewest
map changes. `goToMap` walks to each door on the route and goes through it. For example, the
route from `main` to `bank` is one door: walk to spawn 3 of `main` (168, -134), then send
`transport` `{to: "bank", s: 0}`.

<!-- include course/js/albot/travel.js region=route -->

<!-- include course/ts/albot/travel.ts region=route -->

<!-- include course/python/albot/travel.py region=route -->

<!-- include course/go/travel/travel.go region=route -->

<!-- include course/csharp/Albot/Travel.cs region=route -->

<!-- include course/rust/src/travel.rs region=route -->

<!-- include course/java/src/main/java/albot/Travel.java region=route -->

Game guide: [Travel](#game-maps-and-the-world) and [The main maps](#game-maps-and-the-world).

### Limits of this method

- Your extrapolated position can be a little wrong. Near a corner, the server can stop you, or
  send [`correction`](#recv-correction). `walkTo` then returns false, and the next tick makes
  a new path from the corrected position.
- The margin of half a cell closes some very narrow gaps. On `main`, all paths that the bots of
  this part need stay open.
- A map with no geometry in G has no grid. `Grid.forMap` then fails with a clear message.

## A complete farming bot

This chapter builds the first long-running bot. It logs in, connects one character and
**farms**: it kills monsters again and again for experience (xp) and loot. It adds the module
`farmer` and the program `farm`.

Game guide: [Your first hour](#game-what-adventure-land-is) and
[Leveling and progression](#game-leveling-and-progression).

### What you need

1. **A character that fights.** A merchant cannot fight well. Any other class can kill goos
   ([Classes](#game-classes)). A new character starts on `main`, near the goos, with 200
   `hpot0` and 200 `mpot0` (`api.js:497-541`).
2. **The library and the programs of your language**, as in [Project layout](#learn-designing-a-bot).
3. **The test server**, running in its own terminal (step 6 of [Before you start](#learn-before-you-start)).
4. **The variables of Part 2**: `AL_BASE_URL`, `AL_AUTH`, `AL_SERVER` and `AL_CHARACTER`. Set
   `AL_RECONNECT_MS=2000` for the test server, so that a reconnect test is quick.

### What the bot does

`Farmer.tick` does the first item of this list that applies, and returns:

1. **Dead** (`me.rip`): respawn. `Actions.respawn` waits the rest of the 12 s
   (`node/server.js:224`).
2. **In jail**: send `leave`.
3. **On another map** (a door, the bank, a respawn elsewhere): `goToMap` back to `main`.
4. **Health below 70%, or mana below 30%**, and the potion timer is ready: `heal`. It drinks a
   potion if the bag has one, else it uses the free regeneration ([Healing with
   potions](#learn-acting-in-the-world)).
5. **A chest** from [`drop`](#recv-drop): open all chests. A chest waits 8 minutes only.
6. **No target**: take the nearest monster of the current type. If none is in view, walk to the
   middle of its spawn box in `G.maps[map].monsters`.
7. **Too far**: `walkTo` a point at `range - 10` px from the target, on the line to us.
8. **In range**, and `attack` is ready: attack.

The target is dead when the server sends [`death`](#recv-death) with its id, or a
[`hit`](#recv-hit) with `kill`. The farmer then counts the kill and chooses again.

<!-- include course/js/albot/farmer.js region=tick -->

<!-- include course/ts/albot/farmer.ts region=tick -->

<!-- include course/python/albot/farmer.py region=tick -->

<!-- include course/go/farmer/farmer.go region=tick -->

<!-- include course/csharp/Albot/Farmer.cs region=tick -->

<!-- include course/rust/src/farmer.rs region=tick -->

<!-- include course/java/src/main/java/albot/Farmer.java region=tick -->

### Choose a target

A goo gives 100 xp. Level 10 needs about 49 goos. Later, a stronger monster gives xp faster. The
game guide has the order: [the Mainland ladder](#game-what-adventure-land-is) in "Your first
day". It goes goo, bee, crab, snake, squig, armadillo, croc, tortoise. Its rule: go to the next
monster when you kill the current one in one or two hits.

`Farmer.nextType` applies that rule. It counts our hits on each target. When each of the last 3
kills took 2 hits or fewer, it goes one step up the ladder.

> **Caution:** Before your bot goes up the ladder, read the next monster in [Where to
> level](#game-leveling-and-progression). Its damage per second must be less than the healing of
> your potions. A bee has `aggro` 1: it attacks first.

<!-- include course/js/albot/farmer.js region=ladder -->

<!-- include course/ts/albot/farmer.ts region=ladder -->

<!-- include course/python/albot/farmer.py region=ladder -->

<!-- include course/go/farmer/farmer.go region=ladder -->

<!-- include course/csharp/Albot/Farmer.cs region=ladder -->

<!-- include course/rust/src/farmer.rs region=ladder -->

<!-- include course/java/src/main/java/albot/Farmer.java region=ladder -->

<!-- include course/js/albot/farmer.js region=next-type -->

<!-- include course/ts/albot/farmer.ts region=next-type -->

<!-- include course/python/albot/farmer.py region=next-type -->

<!-- include course/go/farmer/farmer.go region=next-type -->

<!-- include course/csharp/Albot/Farmer.cs region=next-type -->

<!-- include course/rust/src/farmer.rs region=next-type -->

<!-- include course/java/src/main/java/albot/Farmer.java region=next-type -->

### The program

`farm` connects with `Bot.connect`, then runs `Farmer.tick` every 100 ms. Around the tick, it
does three more things:

- **Reconnect.** When the socket closes, it applies [the reconnect rule](#learn-alsocket) with
  `reconnectDelayMs`: wait, then a new `Bot.connect`, with a new socket and the full handshake.
  After a session of 5 minutes, the wait starts again at the first value.
- **Stop cleanly.** Ctrl-C ends the loop. The program closes the socket and prints a summary.
- **Stop after a time.** A number on the command line is the run time in seconds. Without it,
  the bot runs until you stop it.

<!-- include course/js/farm.js -->

<!-- include course/ts/farm.ts -->

<!-- include course/python/farm.py -->

<!-- include course/go/cmd/farm/main.go -->

<!-- include course/csharp/Farm/Program.cs -->

<!-- include course/rust/src/bin/farm.rs -->

<!-- include course/java/src/main/java/Farm.java -->

### Run it on the test server

The test server can drop the socket and put the character in jail on a timer. Then you see the
reconnect and the jail code work. The command line below does what `scripts/check-course.py`
does.

1. Reset the test server: `curl -X POST http://localhost:8022/test/reset`.
2. Tell it to drop `Tester` 5 s after the next `start`:
   `curl -X POST 'http://localhost:8022/test/drop?character=Tester&after_start_ms=5000'`.
3. Tell it to send `Tester` to jail 10 s after that `start`:
   `curl -X POST 'http://localhost:8022/test/jail?character=Tester&after_start_ms=10000'`.
4. Set `AL_RECONNECT_MS=2000`.
5. Run the command of your language with the argument `25`.

On Windows PowerShell, use `Invoke-RestMethod -Method Post '<url>'` in place of `curl -X POST`.

| Language | Command |
|---|---|
| JavaScript | `node farm.js 25` |
| TypeScript | `node farm.ts 25` |
| Python | `python farm.py 25` |
| Go | `go run ./cmd/farm 25` |
| C# | `dotnet run --project Farm -- 25` |
| Rust | `cargo run --bin farm -- 25` |
| Java | `mvn -q compile exec:java -Dexec.mainClass=Farm -Dexec.args=25` |

The output of a real run follows. The ids, the positions and the text of the disconnect reason
are different in each run and in each language:

```
in game as Tester (warrior, level 1) on main at -87,673
target: goo 12 at -4,727
killed goo 12
chest Cc561OsXD1v3hE0ipH0woRK8ZIZxUs: +90024 gold, 5 item(s)
target: goo 11 at 5,740
disconnected: transport closed (code 1005); reconnect in 2 s
in game as Tester (warrior, level 1) on main at -15,720
target: goo 16 at 2,748
killed goo 16
chest Y0CZ0uiJuRBPskfySNnxDNZMotQHLs: +20 gold, 0 item(s)
target: goo 10 at -20,741
in jail: leave
left jail: on main at 10,-12
farmed 26 s: 2 kill(s), level 2, 100044 gold
OK
```

After `left jail`, the character is in the town. The next ticks walk it back to the goos around
the walls, which takes about 13 s at a speed of 55. Without the two test controls, there is no
`disconnected` line and no jail.

### Run it on the live game

Do the steps of [Before a bot plays on the live game](#learn-designing-a-bot). Then run the
command without a number: the bot runs until you stop it. A new character starts near the goos.
A character that is somewhere else walks to `main` and to the goos first.

### Stop it

Press Ctrl-C one time. The program finishes the tick, closes the socket, prints the summary
line and `OK`. Press Ctrl-C a second time to stop at once. In both cases the server saves the
character. Wait 30 s before you start the bot again, or the login can get "Authorization in
progress" ([the reconnect rule](#learn-alsocket)).

### If the character dies

The farmer respawns 12 s after a death, at spawn 5 of `main`, near the goos. A death costs xp
on the live game ([Death and respawn](#game-stats-and-combat)). If the character dies again and
again:

- The monster is too strong for the level or the gear. Go down the ladder: set the type in the
  program to `goo`, and remove the `nextType` call.
- The character has no potions. The free regeneration gives 50 HP each 4 s only. The next
  chapter buys potions.
- Several monsters with `aggro` attack at the same time. Farm a monster with `aggro` 0.

### Run two characters

Start one process for each character, each with its own `AL_CHARACTER`, in two terminals. Start
the second one some seconds after the first one. Each socket has its own call-cost budget.
[A party and a merchant](#learn-a-party-and-a-merchant) runs several characters in one program.

### If it fails

| What you see | Cause | What to do |
|---|---|---|
| `connect failed: login failed: authorization_in_progress` | The server still saves the last session. | Nothing: the bot waits and tries again, as the reconnect rule says. |
| `connect failed: login failed: ingame` | The character plays in another program or browser. | Close the other client. |
| `the server says: limitdc` | Too many events in 4 s. | Send each event through the budget. Do not lower `TICK_MS` below 100 ms. |
| `the server says: limits` | Too many of your characters are online. | Close a character. A new try fails too. |
| `in jail: leave` again and again | A `move` in your own code goes to a blocked point. | Use `walkTo` for each walk. |
| `no geometry for the map ...` | G has no walls for that map. | On the test server, only `main`, `bank`, `jail` and `woffice` exist. |
| No `target` line | No monster of the type is in view, and the walk to its spawn box failed. | Check that the character is on `main`. On the test server, reset it. |

## Supplies, loot and gear

A farming bot uses potions, and its bag fills with loot. This chapter makes the bot look after
itself: after each chest, it wears better gear. When potions or bag space run low, it walks to
the town. There it sells the loot, buys potions and the basic armor, and goes back to farm. The
chapter adds the module `items` and the program `supplies`.

Game guide: [Your first day](#game-what-adventure-land-is), [Inventory](#game-items-and-equipment)
and [NPC prices](#game-gold-and-the-economy).

### The inventory

Three fields of [`player`](#recv-player) describe what your character carries:

| Field | What it holds |
|---|---|
| `me.items` | The inventory: 42 slots (`isize`, `node/server.js:1456`). Each slot is an item `{name, q, level, ...}` or null. |
| `me.slots` | The equipment: slot name → item, for example `mainhand`, `helmet`, `chest`, `ring1`. |
| `me.esize` | The number of empty inventory slots. |

![The stats, the equipment slots and the inventory slots in the official client](img/learn/inventory.png "Stats, equipment and inventory in the official client. Your program reads the same data from player: items, slots and esize.")

The **slot number** of an item (`num`) is its index in `me.items`. Most item events take it. A
`player` update can move items, so read the slot number again immediately before you use it.

`Items.find`, `count` and `freeSlots` read these fields. `npcSelling(name)` finds the NPC on
your map that sells an item, from `G.maps[map].npcs` and `G.npcs[id].items`.

<!-- include course/js/albot/items.js region=find -->

<!-- include course/ts/albot/items.ts region=find -->

<!-- include course/python/albot/items.py region=find -->

<!-- include course/go/items/items.go region=find -->

<!-- include course/csharp/Albot/Items.cs region=find -->

<!-- include course/rust/src/items.rs region=find -->

<!-- include course/java/src/main/java/albot/Items.java region=find -->

### Buying and selling

Both events need an NPC within 400 px (`B.sell_dist`, `node/server.js:220`):

- [`buy`](#send-buy) `{name, quantity}` needs an NPC that sells the item. The price is
  `G.items[name].g` for each one. The answer is `buy_success` with `cost` and `num`, or a
  failure: `distance`, `buy_cost` (not enough gold) or `buy_cant_space`.
- [`sell`](#send-sell) `{num, quantity}` works with any NPC that has a shop. The NPC pays 60% of
  `g` (`G.multipliers.buy_to_sell`), and 1 gold for a gift item. The answer is
  `gold_received` with `gold`.

The bot stands within 350 px, not 400 px, because its position is an estimate.

<!-- include course/js/albot/items.js region=shop -->

<!-- include course/ts/albot/items.ts region=shop -->

<!-- include course/python/albot/items.py region=shop -->

<!-- include course/go/items/items.go region=shop -->

<!-- include course/csharp/Albot/Items.cs region=shop -->

<!-- include course/rust/src/items.rs region=shop -->

<!-- include course/java/src/main/java/albot/Items.java region=shop -->

Which items are **loot to sell**? `isLoot` uses the rules of the game guide ([A merchant in
practice](#game-gold-and-the-economy)): keep potions, scrolls and offerings. Also keep jewelry:
three copies at +0 make one +1 ring ([Gearing up](#learn-gearing-up-upgrades-and-compounds)).
Never sell a locked item (`l`), or an upgrade in progress (`placeholder`). Sell the rest.

<!-- include course/js/albot/items.js region=rules -->

<!-- include course/ts/albot/items.ts region=rules -->

<!-- include course/python/albot/items.py region=rules -->

<!-- include course/go/items/items.go region=rules -->

<!-- include course/csharp/Albot/Items.cs region=rules -->

<!-- include course/rust/src/items.rs region=rules -->

<!-- include course/java/src/main/java/albot/Items.java region=rules -->

> **Caution:** A full bag is the most frequent problem of a bot. With no space, `open_chest`
> fails with `loot_no_space`, and the loot goes to another party member or to the Lost and Found. Keep 5 or
> more slots free ([Inventory](#game-items-and-equipment)).

### Wearing better gear

[`equip`](#send-equip) `{num, slot}` puts an item on. The old item goes back to the bag.
Without `slot`, the server takes the slot from the item type. A weapon that your class cannot
use fails with `cant_equip`. [`unequip`](#send-unequip) `{slot}` takes an item off.

`equipBetter` uses a simple rule: wear an item if its slot is empty, or if the slot holds the
same item at a lower level. Rings and earrings have two slots each. To compare different items,
use their stats ([Gear is more important than level](#game-leveling-and-progression)).

<!-- include course/js/albot/items.js region=equip -->

<!-- include course/ts/albot/items.ts region=equip -->

<!-- include course/python/albot/items.py region=equip -->

<!-- include course/go/items/items.go region=equip -->

<!-- include course/csharp/Albot/Items.cs region=equip -->

<!-- include course/rust/src/items.rs region=equip -->

<!-- include course/java/src/main/java/albot/Items.java region=equip -->

### The restock rule

`supplies` checks its supplies after each chest. It goes to the town when one of these is true:

- fewer than 20 `hpot0` or 20 `mpot0`;
- fewer than 5 free slots.

In the town, it walks to Wynifred (`fancypots`), at (-35, -162) on `main`, and does these
steps:

1. Sell each item that `isLoot` accepts.
2. Buy `hpot0` and `mpot0` up to 50 of each (20 gold each).
3. Buy the basic armor that it does not wear from Gabriel (`basics`, 54 px away): gloves (3,400),
   a coat (6,000) and pants (7,800). It keeps 2,000 gold for potions.
4. Wear what is better.

Then the farmer walks back to the goos.

<!-- include course/js/supplies.js region=rules -->

<!-- include course/ts/supplies.ts region=rules -->

<!-- include course/python/supplies.py region=rules -->

<!-- include course/go/cmd/supplies/main.go region=rules -->

<!-- include course/csharp/Supplies/Program.cs region=rules -->

<!-- include course/rust/src/bin/supplies.rs region=rules -->

<!-- include course/java/src/main/java/Supplies.java region=rules -->

<!-- include course/js/supplies.js region=town -->

<!-- include course/ts/supplies.ts region=town -->

<!-- include course/python/supplies.py region=town -->

<!-- include course/go/cmd/supplies/main.go region=town -->

<!-- include course/csharp/Supplies/Program.cs region=town -->

<!-- include course/rust/src/bin/supplies.rs region=town -->

<!-- include course/java/src/main/java/Supplies.java region=town -->

### The program

<!-- include course/js/supplies.js -->

<!-- include course/ts/supplies.ts -->

<!-- include course/python/supplies.py -->

<!-- include course/go/cmd/supplies/main.go -->

<!-- include course/csharp/Supplies/Program.cs -->

<!-- include course/rust/src/bin/supplies.rs -->

<!-- include course/java/src/main/java/Supplies.java -->

### Run it

1. Reset the test server: `curl -X POST http://localhost:8022/test/reset`.
2. Run the command of your language with the argument `1`: one town trip, then stop.

| Language | Command |
|---|---|
| JavaScript | `node supplies.js 1` |
| TypeScript | `node supplies.ts 1` |
| Python | `python supplies.py 1` |
| Go | `go run ./cmd/supplies 1` |
| C# | `dotnet run --project Supplies -- 1` |
| Rust | `cargo run --bin supplies -- 1` |
| Java | `mvn -q compile exec:java -Dexec.mainClass=Supplies -Dexec.args=1` |

The output of a real run on the test server:

```
in game as Tester (warrior, level 1) on main at -87,673
target: goo 12 at -4,727
killed goo 12
chest SlnzCyYRoWyjdTtQ1yf2En1eJlBA6K: +90027 gold, 5 item(s)
equip ringsj: ring1
equip ringsj: ring2
equip hpbelt: belt
supplies low: 9 hpot0, 10 mpot0, 38 free slot(s)
walk to fancypots at -35,-162
sell gem0: +144000 gold
buy hpot0 x41: 820 gold
buy mpot0 x40: 800 gold
buy gloves x1: 3400 gold
buy coat x1: 6000 gold
buy pants x1: 7800 gold
equip gloves: gloves
equip coat: chest
equip pants: pants
bag: 50 hpot0, 50 mpot0, 39 free slot(s), 225207 gold
OK
```

The first chest has the first-drop bonus: much gold, three rings, a belt and a gem. The bot
wears two rings and the belt, and keeps the third ring for a compound. The test character
starts with 10 potions of each kind, so the first check sends it to the town. On the live game,
a new character has 200 of each, and the first town trip comes much later.

On the live game, run it without a number. It farms and makes a town trip each time that the
rule says so. Stop it with Ctrl-C.

### If it fails

| What you see | Cause | What to do |
|---|---|---|
| `buy hpot0: distance` | The character is more than 400 px from the NPC. | The walk failed. Check that the character is on `main`. |
| `buy coat: buy_cost` | Not enough gold. | Normal for a new character. The bot buys the armor on a later trip. |
| `buy hpot0: buy_cant_space` | The bag is full. | Sell first; the program does. Check `isLoot` for your items. |
| No `sell` line | Nothing in the bag is loot by the rules. | Correct. Rings, belts and scrolls stay. |
| `equip ...` does not come for a weapon | `cant_equip`: your class cannot use it. | Correct. Sell it, or give it to the merchant. |

## A party and a merchant

You can play several characters at the same time. This chapter runs three fighters and one
merchant in one program. The fighters farm in a **party**. The merchant walks to them, takes
their loot and gold, sells the loot and puts the gold in the bank. The chapter adds the module
`party` and the program `party-merchant`.

![A merchant at its stand in the Mainland town, with its inventory open](img/learn/merchant.png "A merchant in town. In this chapter, your merchant takes the loot of the fighters, sells it and puts the gold in the bank.")

Game guide: [Parties](#game-social-and-multiplayer), [A merchant in
practice](#game-gold-and-the-economy) and [The bank](#game-items-and-equipment).

### How many characters

> **Warning:** Respect the character limits. The game rules ask players not to go past them
> with a VPN, a second server or a second account (`languages/en/pages.js:1168-1169`). A character
> over the limit gets `disconnect_reason` `"limits"`, and its socket closes
> (`node/server.js:11914-11916`).

The live server checks the limit when a character logs in (`is_player_allowed`,
`node/server_functions.js:383-437`):

- A merchant does not count toward the limit, but the account can have only one merchant online
  (`node/server_functions.js:399-406`, `:411`).
- For the other classes, the limit is `options.character_limit` on each game server. That value
  comes from a configuration file that is not in the public repository. Thus the live number is
  unclear from the source.
- The game's own guide says: "You can have at most 3 characters and 1 merchant online at any
  time" (`languages/en/docs.js:4954`). Use that number.

### Several characters in one program

The program logs in one time, reads the lists of servers and characters one time, and loads G
one time. Then `connectMember` opens one socket for each character. It calls `Bot.connectWith`:
the steps of `Bot.connect` without the HTTP calls. Each character has its own `World`,
`Cooldowns`, `Budget` and `Actions`, because the server counts the call-cost for each socket.

<!-- include course/js/albot/party.js region=member -->

<!-- include course/ts/albot/party.ts region=member -->

<!-- include course/python/albot/party.py region=member -->

<!-- include course/go/party/party.go region=member -->

<!-- include course/csharp/Albot/Party.cs region=member -->

<!-- include course/rust/src/party.rs region=member -->

<!-- include course/java/src/main/java/albot/Party.java region=member -->

To share information between your characters, read the state of the other `Member` in your
program. You do not need the game's [`cm`](#send-cm) event for characters in one program.

### Making a merchant

A **merchant** is a class that does not fight. It sells, buys, upgrades and keeps the gold
([Merchant](#game-classes)). Make one with the HTTP call `create_character` `{name, char}`
(`api.js:474-588`). The name has 4 to 12 letters, digits or `_`, and nobody may use it already
(`api.js:24-31`). The failures include `name_used`, `invalid_name` and `reached_character_limit`.

<!-- include course/js/albot/party.js region=create-character -->

<!-- include course/ts/albot/party.ts region=create-character -->

<!-- include course/python/albot/party.py region=create-character -->

<!-- include course/go/party/party.go region=create-character -->

<!-- include course/csharp/Albot/Party.cs region=create-character -->

<!-- include course/rust/src/party.rs region=create-character -->

<!-- include course/java/src/main/java/albot/Party.java region=create-character -->

`party-merchant --create-merchant <Name>` calls it and stops. The test server has a merchant
already: `Merchy`.

### Forming a party

A **party** is a group of up to 10 characters: 9 invitations from the leader
(`limits.party`), 10 members at most (`limits.party_max`, `node/server.js:256-260`). The
fighters share the xp of a kill and the gold of a chest. A merchant gets no share. The rules
are in [Parties](#game-social-and-multiplayer).

1. The leader sends [`party`](#send-party) `{event: "invite", name}`.
2. The other character gets [`invite`](#recv-invite) `{name}`.
3. It sends `party` `{event: "accept", name}` with the name of the leader.
4. Each member gets [`party_update`](#recv-party_update) `{list, party}`. `list` holds the names,
   the leader first.

<!-- include course/js/albot/party.js region=party -->

<!-- include course/ts/albot/party.ts region=party -->

<!-- include course/python/albot/party.py region=party -->

<!-- include course/go/party/party.go region=party -->

<!-- include course/csharp/Albot/Party.cs region=party -->

<!-- include course/rust/src/party.rs region=party -->

<!-- include course/java/src/main/java/albot/Party.java region=party -->

### Giving items and gold

[`send`](#send-send) gives items or gold to another character on the same map, within 400 px
(`node/server.js:8463-8560`):

- `{name, num, q}` gives `q` of the item in slot `num`. The answer is `item_sent`, or
  `distance` or `send_no_space`.
- `{name, gold}` gives gold. Between characters of one account, the receiver gets all of it. To
  another account, it gets 97.5%.

<!-- include course/js/albot/items.js region=send -->

<!-- include course/ts/albot/items.ts region=send -->

<!-- include course/python/albot/items.py region=send -->

<!-- include course/go/items/items.go region=send -->

<!-- include course/csharp/Albot/Items.cs region=send -->

<!-- include course/rust/src/items.rs region=send -->

<!-- include course/java/src/main/java/albot/Items.java region=send -->

In `party-merchant`, each fighter checks the merchant after each tick. When the merchant is in
its view and within 300 px, the fighter gives all items except its potions. It also gives its
gold above 20,000. The merchant walks to each fighter that has loot, and waits there until the
fighter gave all.

### The bank

The bank keeps gold and items for all characters of the account. It is a separate map with a
door in `main`, at spawn 3 (168, -134). `goToMap("bank")` walks there and sends `transport`.
Inside, send [`bank`](#send-bank) `{operation: "deposit", amount}` or `"withdraw"`. The answer
has `place: "bank"` and the `gold` moved (`node/server.js:9257-9282`).

<!-- include course/js/albot/items.js region=bank -->

<!-- include course/ts/albot/items.ts region=bank -->

<!-- include course/python/albot/items.py region=bank -->

<!-- include course/go/items/items.go region=bank -->

<!-- include course/csharp/Albot/Items.cs region=bank -->

<!-- include course/rust/src/items.rs region=bank -->

<!-- include course/java/src/main/java/albot/Items.java region=bank -->

> **Caution:** Most actions fail inside the bank with [`cant_in_bank`](#code-cant_in_bank).
> Leave the bank before you fight, send items or upgrade. Only one character of the account can
> be in the bank at one time.

### The program

The program does these steps:

1. Choose the team: `AL_CHARACTER` is the leader. The next two fighters of your character list
   join it, and your first merchant.
2. Connect the four characters, one after the other.
3. Form the party.
4. Run the three fighter loops and the merchant at the same time.
5. The merchant waits for loot, collects it, sells it to `fancypots`, banks its gold above
   50,000, and goes back to `main`. This is one **trip**.
6. After the number of trips on the command line, stop all four characters.

<!-- include course/js/party-merchant.js region=choose -->

<!-- include course/ts/party-merchant.ts region=choose -->

<!-- include course/python/party_merchant.py region=choose -->

<!-- include course/go/cmd/party-merchant/main.go region=choose -->

<!-- include course/csharp/PartyMerchant/Program.cs region=choose -->

<!-- include course/rust/src/bin/party-merchant.rs region=choose -->

<!-- include course/java/src/main/java/PartyMerchant.java region=choose -->

<!-- include course/js/party-merchant.js region=fighter -->

<!-- include course/ts/party-merchant.ts region=fighter -->

<!-- include course/python/party_merchant.py region=fighter -->

<!-- include course/go/cmd/party-merchant/main.go region=fighter -->

<!-- include course/csharp/PartyMerchant/Program.cs region=fighter -->

<!-- include course/rust/src/bin/party-merchant.rs region=fighter -->

<!-- include course/java/src/main/java/PartyMerchant.java region=fighter -->

<!-- include course/js/party-merchant.js region=merchant -->

<!-- include course/ts/party-merchant.ts region=merchant -->

<!-- include course/python/party_merchant.py region=merchant -->

<!-- include course/go/cmd/party-merchant/main.go region=merchant -->

<!-- include course/csharp/PartyMerchant/Program.cs region=merchant -->

<!-- include course/rust/src/bin/party-merchant.rs region=merchant -->

<!-- include course/java/src/main/java/PartyMerchant.java region=merchant -->

The complete program:

<!-- include course/js/party-merchant.js -->

<!-- include course/ts/party-merchant.ts -->

<!-- include course/python/party_merchant.py -->

<!-- include course/go/cmd/party-merchant/main.go -->

<!-- include course/csharp/PartyMerchant/Program.cs -->

<!-- include course/rust/src/bin/party-merchant.rs -->

<!-- include course/java/src/main/java/PartyMerchant.java -->

### Run it

1. Reset the test server: `curl -X POST http://localhost:8022/test/reset`.
2. Keep `AL_CHARACTER=Tester`.
3. Run the command of your language with the argument `1`: one merchant trip.

| Language | Command |
|---|---|
| JavaScript | `node party-merchant.js 1` |
| TypeScript | `node party-merchant.ts 1` |
| Python | `python party_merchant.py 1` |
| Go | `go run ./cmd/party-merchant 1` |
| C# | `dotnet run --project PartyMerchant -- 1` |
| Rust | `cargo run --bin party-merchant -- 1` |
| Java | `mvn -q compile exec:java -Dexec.mainClass=PartyMerchant -Dexec.args=1` |

The output of a real run, without the `target`, `killed` and `chest` lines of the fighters:

```
team: Tester, Healer, Archer; merchant: Merchy
in game as Tester (warrior, level 1) on main at -87,673
in game as Healer (priest, level 1) on main at -87,673
in game as Archer (ranger, level 1) on main at -87,673
in game as Merchy (merchant, level 1) on main at -87,673
party: Tester, Healer, Archer, Merchy
Healer: gave 0 item(s) and 20007 gold to Merchy
Archer: gave 0 item(s) and 20007 gold to Merchy
Merchy: walk to Tester at -77,680
Tester: gave 5 item(s) and 20007 gold to Merchy
Merchy: walk to fancypots at -35,-162
Archer: gave 0 item(s) and 300080 gold to Merchy
Healer: gave 0 item(s) and 300080 gold to Merchy
Tester: gave 5 item(s) and 300080 gold to Merchy
Merchy: sold 1 item(s): +288000 gold
Merchy: in the bank: deposited 1208261 gold
Merchy: back on main at 168,-134
OK
```

The party chests give their items to the first member with space, so `Tester` collects the
items. The first chest of each fighter has the first-drop bonus, so the gold is large. The
merchant still gets gifts while it walks away: it stays in view for some seconds. The gems
stack in one slot, so the merchant sells one stack. It keeps the rings and the belts for
compounds.

On the live game, check the limits first. Then run it without a number: the merchant makes a
trip each time that the fighters have loot. Stop it with Ctrl-C.

### If it fails

| What you see | Cause | What to do |
|---|---|---|
| `AL_CHARACTER must be a fighter` | `AL_CHARACTER` names a merchant. | Name a fighter. It leads the party. |
| `no merchant on this account` | You have no merchant. | Run with `--create-merchant <Name>` first. |
| `create_character failed: name_used` | Another player has that name. | Choose another name. |
| `... got no invitation` | The invitation did not arrive in 5 s. | Check that all four are on the same server (`AL_SERVER`). |
| The server says `limits` | Too many of your characters are online. | Close the characters that play in the browser. |
| No `gave` line | The merchant does not come within 300 px, or it is not in the fighter's view. | Check that the walk of the merchant works. On the test server, reset it. |
| `Merchy: in the bank: deposited 0 gold` | The merchant has 50,000 gold or less. | Correct. |

## Gearing up: upgrades and compounds

An upgrade makes an item stronger, one level at a time, and a failure destroys the item. A
compound combines three identical items into one item of the next level. Gear is more
important than level for the strength of a character ([Gear is more important than
level](#game-leveling-and-progression)). This chapter adds the program `gear-up`: it upgrades a
coat to +3 and compounds rings, with a stop rule.

![Cue, the upgrade NPC, and the upgrade window with a bow, a scroll and the chance 99.99%](img/learn/upgrade.png "Cue, the upgrade NPC in the Mainland town, and the upgrade window of the official client. Your program sends upgrade and compound to Cue.")

Game guide: [Upgrading and compounding](#game-upgrading-and-compounding), and in it [Your first
upgrade, step by step](#game-upgrading-and-compounding), [The odds](#game-upgrading-and-compounding)
and [A progression plan](#game-upgrading-and-compounding).

### The steps

1. Buy the item if you do not have it.
2. Stand within 400 px of Lucas (`scrolls`, -464, -96) and of Cue (`newupgrade`, -207, -220).
   The middle of the two is about 140 px from each.
3. Buy a scroll of the right grade from Lucas: `scroll0` for an upgrade, `cscroll0` for a
   compound of normal items. The grade of the scroll must be at least the grade of the item
   (`node/server.js:7176-7193`).
4. Ask for the chance: send the event with `calculate: true`. The server uses nothing and
   answers `upgrade_chance` or `compound_chance` with `chance`. The chance includes grace, which
   only the server knows.
5. If the stop rule allows it, send the same event without `calculate`.
6. Wait for the result: a hitchhiker `game_response` `upgrade_success` or `upgrade_fail`
   (`compound_success` or `compound_fail`) with `level` and `num`.

### Upgrade and compound in code

[`upgrade`](#send-upgrade) is `{item_num, scroll_num, clevel, calculate}`. `clevel` must be
the item's level now, or the server answers `upgrade_mismatch` (`node/server.js:7166-7168`).
[`compound`](#send-compound) is `{items: [a, b, c], scroll_num, clevel, calculate}`.

The result comes late, as a **hitchhiker** inside a `player` update. An upgrade to +N takes
0.5 × N × √N s, and a compound takes 10 s (`node/server.js:7427`, `:7037`). While it runs, the
slot holds a `placeholder` item. The failures before the roll are different: some are bare
strings (`"upgrade_no_scroll"`), and some are objects with `place`. So `Items` keeps the last
50 `game_response` events that reach `world.listen`, hitchhikers too. `upgrade` and `compound`
search them for the first answer about their event.

<!-- include course/js/albot/items.js region=upgrade -->

<!-- include course/ts/albot/items.ts region=upgrade -->

<!-- include course/python/albot/items.py region=upgrade -->

<!-- include course/go/items/items.go region=upgrade -->

<!-- include course/csharp/Albot/Items.cs region=upgrade -->

<!-- include course/rust/src/items.rs region=upgrade -->

<!-- include course/java/src/main/java/albot/Items.java region=upgrade -->

### The stop rule

The game guide gives the plan ([A progression plan](#game-upgrading-and-compounding)):

- Take each piece to +3 first. The base chances for a normal item are 99.99%, 98% and 95%.
- Stop at +3 when you have no spare copy. At +4 the chance is 70%, and a failure leaves the
  slot empty. Upgrade a spare copy above +3, and wear it only after a success.
- Compound jewelry while the chance is high: +0 to +1 is 99%. +2 is 75%: wait for more copies.
- Ask the server first, every time.

`gear-up` puts this into two constants: a target level of 3, and a minimum chance of 0.9 from
`calculate`.

<!-- include course/js/gear-up.js region=rules -->

<!-- include course/ts/gear-up.ts region=rules -->

<!-- include course/python/gear_up.py region=rules -->

<!-- include course/go/cmd/gear-up/main.go region=rules -->

<!-- include course/csharp/GearUp/Program.cs region=rules -->

<!-- include course/rust/src/bin/gear-up.rs region=rules -->

<!-- include course/java/src/main/java/GearUp.java region=rules -->

<!-- include course/js/gear-up.js region=upgrade-loop -->

<!-- include course/ts/gear-up.ts region=upgrade-loop -->

<!-- include course/python/gear_up.py region=upgrade-loop -->

<!-- include course/go/cmd/gear-up/main.go region=upgrade-loop -->

<!-- include course/csharp/GearUp/Program.cs region=upgrade-loop -->

<!-- include course/rust/src/bin/gear-up.rs region=upgrade-loop -->

<!-- include course/java/src/main/java/GearUp.java region=upgrade-loop -->

`findGroup` finds three items with the same name and level that compound
(`G.items[name].compound`):

<!-- include course/js/gear-up.js region=compound-loop -->

<!-- include course/ts/gear-up.ts region=compound-loop -->

<!-- include course/python/gear_up.py region=compound-loop -->

<!-- include course/go/cmd/gear-up/main.go region=compound-loop -->

<!-- include course/csharp/GearUp/Program.cs region=compound-loop -->

<!-- include course/rust/src/bin/gear-up.rs region=compound-loop -->

<!-- include course/java/src/main/java/GearUp.java region=compound-loop -->

### The program

<!-- include course/js/gear-up.js -->

<!-- include course/ts/gear-up.ts -->

<!-- include course/python/gear_up.py -->

<!-- include course/go/cmd/gear-up/main.go -->

<!-- include course/csharp/GearUp/Program.cs -->

<!-- include course/rust/src/bin/gear-up.rs -->

<!-- include course/java/src/main/java/GearUp.java -->

### Run it

1. Reset the test server: `curl -X POST http://localhost:8022/test/reset`.
2. Run the command of your language.

| Language | Command |
|---|---|
| JavaScript | `node gear-up.js` |
| TypeScript | `node gear-up.ts` |
| Python | `python gear_up.py` |
| Go | `go run ./cmd/gear-up` |
| C# | `dotnet run --project GearUp` |
| Rust | `cargo run --bin gear-up` |
| Java | `mvn -q compile exec:java -Dexec.mainClass=GearUp` |

The output of a real run on the test server. In this run, the upgrade to +3 failed, and the
coat is gone:

```
in game as Tester (warrior, level 1) on main at -87,673
target: goo 12 at -4,727
killed goo 12
chest nAg05rkSsAJZiD8UY6ehDmzwbYtplI: +90026 gold, 5 item(s)
walk to basics at -89,-165
buy coat x1: 6000 gold
walk to scrolls and newupgrade at -335,-158
buy scroll0 x1: 1000 gold
upgrade coat +0 -> +1: success (chance 1.00)
buy scroll0 x1: 1000 gold
upgrade coat +1 -> +2: success (chance 0.98)
buy scroll0 x1: 1000 gold
upgrade coat +2 -> +3: fail (chance 0.95)
buy cscroll0 x1: 6400 gold
compound ringsj +0 x3 -> +1: success (chance 0.99)
equip ringsj: ring1
equip hpbelt: belt
gear: chest -, ring1 ringsj +1, ring2 -, belt hpbelt +0
OK
```

The rolls of the test server depend on the order of all random events, so your run can differ.
A 95% chance fails 1 time in 20. In a run with no failure, the coat is +3 and the last lines are
`equip coat: chest` and `gear: chest coat +3, ...`.

On the live game, the first chest of a character has no rings, so the compound part finds no
group. Collect rings first, or give them to the character that upgrades. In a party, the
merchant usually upgrades ([Merchant](#game-classes)).

### If it fails

| What you see | Cause | What to do |
|---|---|---|
| `buy coat: buy_cost` | Not enough gold: a coat costs 6,000. | Farm longer. |
| `upgrade coat: distance` | The character is more than 400 px from Cue. | Check the walk to the middle point. |
| `upgrade coat: upgrade_mismatch` | `clevel` is not the level of the item. | Read `me.items[num].level` immediately before the event. `upgrade` does. |
| `upgrade coat: upgrade_incompatible_scroll` | The scroll grade is below the item grade. | Use `scroll1` from +7 on a normal item. |
| `upgrade coat: no answer` | No result in 30 s. | Look at the output of the test server. A disconnect in the roll keeps the item on the live game. |
| `stop: the chance for +4 is 0.70` | The stop rule. | Correct. Upgrade a spare copy. |

## Where to go next

Your bot now levels, buys supplies, sells loot, gears up, and runs a party with a merchant. This
chapter lists the next steps. Each one uses the reference for its details.

### Events and bosses

The server announces world events and bosses in the server state **S**: in `welcome`, in
[`server_info`](#recv-server_info) and in [`game_event`](#recv-game_event). The
[event lifecycle](#s-event-lifecycle) lists when each one starts, where it spawns, and how to
[`join`](#send-join) it. A bot can watch S and send its party to an event. Bosses hit much
harder than goos, so test your survival logic first. The game guide has
[Events, bosses and seasons](#game-events-bosses-and-seasons).

### Better pathfinding

- **Speed.** Cache paths between common points, or use a coarser grid for long distances.
- **Danger.** Add a cost to cells near aggressive monsters, so that the route avoids them.
- **Other maps.** Add the transporter's price and the maps that need a key to `route`.

### A merchant stand

The merchant of this part sells to NPCs for 60% of the value. A stand sells to players for
more. [A merchant in practice](#game-gold-and-the-economy) gives the steps:
[`merchant`](#send-merchant) opens the stand, and [`equip`](#send-equip) with a `trade` slot
lists an item.

### Persistence

The bot forgets everything when it stops. Save what is expensive to learn again: the cached G
([Getting the game data](#learn-getting-the-game-data)), the auth token, and your own
statistics. Do not save the world state. It is old after a reconnect.

### Logging and metrics

Write one line for each important event: a kill, a death, a disconnect with its reason, a failed
request. Count kills, gold and xp each hour. Record the `cc` value from `player`. If a bot dies
or disconnects often, these numbers show the cause.

### Be a good member of the game

> **Warning:** Read the current rules of the game before you run a bot for a long time. The
> rules below come from the pages in the live repository. They can change.

- The game allows code. Its rules say "you can do pretty much everything with Code"
  (`languages/en/pages.js:1162-1163`). The same rule says that the game is "exploring allowing
  non-UI botting", so a client of your own is not clearly allowed yet. It also asks players
  not to overload the servers ("don't DDOS the game") and not to use bugs.
- Respect the character limits (`languages/en/pages.js:1168-1169`).
- One account for each player (`languages/en/docs.js:4951`).
- An account that plays 24/7 without any contact with other players can get a temporary
  ban. The rule asks for some social activity, on average once each week
  (`languages/en/docs.js:4918`).
- Stay far below the call-cost limit. Each character has "a limited amount of calls"
  (`languages/en/docs.js:4928`).
- Do not sell items or gold for real money (`languages/en/pages.js:1159-1160`).

If you find a bug in the server, report it. The rules say that the game pays bug bounties.
