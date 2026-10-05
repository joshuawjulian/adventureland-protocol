## What Adventure Land is

Adventure Land is a small 2D MMORPG in which code, not a person at a keyboard, plays the characters.

> **Slides.** For a short, visual version of this guide, open [the game guide as slides](deck.html) (36 slides, with the game's own art).

An MMORPG (massively multiplayer online role-playing game) is a game world that many people share at the same time. Each person controls one or more **characters**. A character fights monsters, collects items and becomes stronger over time.

### A game for bots

A **bot** is a program that plays a game for you. Most MMOs ban bots. Adventure Land welcomes them.

The official client runs in a browser or on Steam. It has a code editor with the name CODE. In CODE, you write JavaScript that calls functions such as `attack(target)` or `move(x, y)`. Then your character plays without you. Players compete on the quality of their code, not on the speed of their hands.

The [Build a bot](#learn-before-you-start) course goes one step further. It does not write scripts for the official client. It replaces the client. Its program logs in over HTTP, opens a WebSocket to a game server and sends the socket events of the game directly. The [overview](#guide-overview) shows the full sequence on one page.

To write a good bot, you must know the game that the protocol describes. This guide tells you which class to play and how the server calculates damage. It also tells you where to go at each level, why characters die, and what to do in your first hour, day and week.

> **Sources.** This guide comes from the open-source code of the live game, `kaansoral/adventureland_mongodb` (pinned in `versions.json`). References such as `node/server.js:1301` link to that code. The numbers in the tables come from the game data **G**, version **17478** (`G_17478.json`). A game update can change them. A reference with `legacy:` points to the old version of the game and is only a historical note.

### The world

The world is a set of 2D maps that you see from above. The unit of distance is the pixel (px). A map has walls, doors to other maps, NPCs and monster spawn areas. [`G.geometry`](#g-geometry) holds the walls as collision lines.

An **NPC** (non-player character) is a character that the server controls, for example a shop keeper. The hub of the world is **Mainland** (`main`). Its town is near (0, 0). A new character starts in the south part of the town, at (−87, 673): spawn point 5 of `main` (`G.maps.main.on_death`, api.js:496). [`G.maps`](#g-maps) lists every map. [Maps and the world](#game-maps-and-the-world) describes them.

A **spawn area** is the box where one type of monster lives: the `boundary` of its entry in `G.maps[map].monsters`, as `[x1, y1, x2, y2]`. A dead monster returns after its `respawn` time, usually a few seconds (node/server.js:13366-13379). A monster that nobody attacks slowly becomes stronger ([Monsters gain levels too](#game-leveling-and-progression)). All characters on a server share the same monsters. Thus other players can make a good area crowded.

### Servers, regions and PvP

A **server** is one copy of the world that runs on its own. Each server has its own monsters, its own bosses and its own event state ([S](#s-what-s-is)). The name of a server has two parts: a region and a name. Together they make the **key** of the server, for example `EUI` or `USPVP` ([units and conventions](#guide-units-and-conventions)).

| Part | Values | Notes |
|---|---|---|
| Region | `EU`, `US`, `ASIA` | Each region has a clock offset from UTC: EU +1, US −5, ASIA +7 hours (node/server.js:339-343, 365). The offset sets the hours of night and of the daily events. |
| Name | `I`, `II`, `III`, `PVP` and others | The live server list tells you which servers are online ([the server list](#learn-logging-in-and-choosing-a-server)). The code also has special rules for the names `HARDCORE`, `TEST` and `DUNGEON` (node/server.js:367-410). |

**PvP** (player versus player) means that other players can attack your characters. On a normal server, only the maps with `pvp: true` allow PvP, for example the Arena. On a server whose name starts with `PVP` or `HARDCORE`, all maps allow PvP. In return, that server multiplies xp by 1.2, gold by 1.25 and luck by 1.15 (node/server.js:416-422).

On a PvP server, each item that drops gets a PvP mark (`v`). If another player kills your character there, each marked item can drop for the killer (`drop_something_pvp`, node/server.js:2566-2596). The chance is 50% for each equipped piece, 30% for the weapon and the offhand, 80% for each inventory item and 50% for each stack.

`HARDCORE` is a special server. It allows one character per account and gives very large xp and gold multipliers (node/server.js:367-385). A character that dies there loses a full level (node/server.js:13916-13919).

**Home server.** Each character has a home server (`p.home`). The first server that the character joins becomes its home. To change it, send [`set_home`](#send-set_home) on the new server. You can do this one time in 36 hours, else the reply is `sh_time` (node/server.js:5523-5535). The home server is important at level 60 and higher:

- A character of level 60 or more that joins a non-home server (not `PVP`) gets **Hop Sickness** (node/server_functions.js:1094-1104). For 12 minutes of play, it has −80% luck, gold and xp, and −20% damage output (`G.conditions.hopsickness`).
- On its home server, a character gets 5 × the points on cooperative bosses (node/server.js:13311-13314). It also rolls extra drop tables (`monsters_home_server`, node/server.js:2358-2371).
- **Realm Fatigue** stops these home bonuses for 30 minutes. It starts when another non-merchant character of your account was on a different server recently (`G.conditions.realmfatigue`, node/server_functions.js:1203-1205).

Thus keep all your fighters on one server, and make it their home.

### Accounts and characters

One **account** owns many characters. You log in to the account, and then you put one of its characters into the game.

The live code gives an account 5 character slots. An account that has a platform id (from a Steam or Mac App Store login) gets 8 slots. Each extra slot costs 200 shells, to a maximum of 18 characters (api.js:14-22, 559-563, adventure_functions.js:164-168). A character name has 4 to 12 characters (api.js:24-31).

Do these steps one time, before your bot plays:

1. Make an account in the desktop client (Steam or the Mac App Store). The website refuses new accounts with `cant_signup_on_web` (api.js:93). If you own the game on Steam, you can also use the Steam sign-up page (steam_signup.js:51-62).
2. Log in one time through the Steam or the Mac App Store client. This links a platform id to the account. An account made in that client already has the link.
3. In the game, create one character. Select its class with the help of [Which class to start with](#game-what-adventure-land-is) below.
4. Write down the name of the character. Your program needs it in `AL_CHARACTER`.

> **Caution:** If you skip step 2, the server gives each character the `authfail` condition: −85% luck, −85% gold and −20% xp (node/server.js:11863-11869). The same condition also stops the bonuses for new players ([Bonuses for new and solo players](#game-leveling-and-progression)). The [connecting guide](#guide-connecting-to-a-game-server) has the details.

A new character starts with these things (api.js:537-554):

- level 1, 0 xp and 0 gold;
- 200 HP potions (`hpot0`) and 200 MP potions (`mpot0`);
- a helmet and shoes, already equipped;
- the weapon of its class, already equipped (`G.classes[cls].base_slots`). This is a blade (warrior), a mace (paladin), a claw (rogue), a bow (ranger) or a staff (others).

> **Caution:** The starting items have `gift: 1`. An NPC pays only 1 gold for a gift item (js/old_common_functions.js:786). Do not sell them.

A second limit controls how many characters of one account can be **online at the same time** on one server. One merchant is always allowed. The limit for the other classes is `options.character_limit`, a value in a private configuration file. Thus the live number is unclear from the source ([characters online at once](#guide-rate-limits-and-anti-abuse)).

The game has two currencies:

| Currency | Source | Use |
|---|---|---|
| Gold | Monster kills, sales of items, trades with players | Almost everything: potions, scrolls, gear, crafting, fees |
| Shells | Real money. Some drop tables also contain `"shells"` entries, but they are rare | Character slots, cosmetics, some premium items. `G.items[x].cash` gives the price in shells |

### Which class to start with

[Classes](#game-classes) describes all seven classes. For your first character, use these rules:

1. Start with **one** fighter, not a party. The "Lone Wolf" bonus gives 3 × gold, xp and luck while you have one non-merchant character online (node/logic/encouragement.js:223-271). One bot is also easier to write and to correct.
2. Select a **ranger** or a **mage**. G calls the mage "ideal for beginners" and the ranger "very suitable for beginners" (`G.classes[cls].description`). Both attack from a distance: 70 px (ranger with its bow) or 170 px (mage with its staff). Slow monsters cannot touch them, so a simple bot that stands still and attacks survives.
3. Select a **warrior** if you want the most HP and the most damage at level 1. It has 624 HP and about 35 damage per second at level 1, but it must stand next to the monster.
4. Do not start with a **priest** or a **rogue**. G says that they are "not ideal for beginners". A priest does little damage alone.
5. Do not start with a **merchant**. A merchant gets no xp from kills (node/server.js:2810-2812). Add one later, when you have loot to sell.

This table shows each class at level 1 with its starting weapon. We calculated it from G with the code in [How the base stats grow](#game-classes):

| Class | Attack | Attacks per second | Range (px) | Damage per second | HP |
|---|---|---|---|---|---|
| Warrior | 68 | 0.51 | 23 | 35 | 624 |
| Paladin | 76 | 0.42 | 20 | 32 | 724 |
| Ranger | 59 | 0.43 | 70 | 25 | 320 |
| Rogue | 50 | 0.48 | 20 | 24 | 349 |
| Mage | 44 | 0.37 | 170 | 16 | 257 |
| Priest | 28 (heal 70) | 0.37 | 170 | 10 | 305 |
| Merchant | 3 | 0.07 | 70 | 0 | 109 |

### What a party is for

A **party** is a group of up to 10 characters that fight together and share rewards (node/server.js:256-260). A party helps in three ways:

- **Roles.** A tank takes the hits, a healer keeps the others alive, and the damage dealers kill. Together they can kill monsters that one character cannot ([The seven classes](#game-classes)).
- **Shared rewards.** Each member gets a part of the xp of each kill. The party also gives +10% to +40% xp, +5% gold and luck bonuses ([Xp from a kill](#game-leveling-and-progression)).
- **Shared loot.** The chest of a kill goes to the party, and the server divides it by share ([Drops and loot](#game-drops-and-loot)).

A party of two fighters loses the Lone Wolf bonus (3 ×). Thus a party is better only when it kills much more than one character can. Usually that is after your first week. [Social and multiplayer](#game-social-and-multiplayer) has the rules, and [A party and a merchant](#learn-a-party-and-a-merchant) has the code.

### A typical day

A typical account at the midgame runs a party: some fighters and one **merchant**. The merchant does not fight. It manages the items and the gold.

The daily loop has these steps:

1. **Farm.** The fighters stay at a spawn area and kill the same monster many times. "Farming" means this repeated kill for xp, gold and items.
2. **Sustain.** The fighters drink potions and heal, so they do not die. When the supplies are low, a character buys more.
3. **Loot.** Kills drop chests. Each item in a chest is the result of a random roll against a table in [`G.drops`](#g-drops).
4. **Improve gear.** The merchant buys scrolls and **upgrades** weapons and armor. It also **compounds** three identical accessories into one better accessory. Both actions can fail and destroy the item ([Upgrading and compounding](#game-upgrading-and-compounding)).
5. **Trade.** The merchant sells extra items to NPCs, or to other players from a merchant stand.
6. **Events.** At fixed hours, world bosses and arena events start for the full server ([S](#s-event-lifecycle)). Each character that helps to kill a boss gets a share of its loot.

A bot does this loop all day and all night. A person makes many decisions one time, for example "go to the next area when the party is strong enough". A bot needs each of these decisions as a written rule. The sections below give you the first rules.

### Your first hour

The goal of the first hour is level 10 and a bot that does not die. This path is for one ranger or mage. Your program must connect and act first: see [Acting in the world](#learn-acting-in-the-world).

1. Put the character into the game on a normal server, for example `EUI`.
2. Read your position from the `player` data. It is about (−87, 673).
3. Move to the goo spawn area: the box from (−282, 702) to (218, 872). It is directly south of the spawn point.
4. Select the nearest goo (`goo`, 100 HP, 100 xp) and send [`attack`](#send-attack).
5. Attack again each time the cooldown of the attack ends ([Cooldowns, attack speed and mana](#game-stats-and-combat)).
6. If your HP is 50 or more below the maximum, send [`use`](#send-use) `{item: "hp"}`. This free ability gives 50 HP. It uses the shared potion cooldown of 4 s (node/server.js:11988-12021).
7. If your HP is below half, drink an HP potion (`hpot0`, +200 HP) in place of step 6.
8. If your MP is low, send `use` `{item: "mp"}` (+100 MP) or drink an MP potion (`mpot0`, +300 MP).
9. When the character has 10 levels, go to [Your first day](#game-what-adventure-land-is).

You know that it works when these things happen:

- After each kill, the `xp` in your `player` data increases by 100. A chest appears ([`drop`](#recv-drop)). Open it as in [Looting chests](#learn-acting-in-the-world).
- Level 2 comes after 2 goos. Level 1 needs 200 xp (`G.levels["1"]`).
- Level 10 needs 4,910 xp in total: about 49 goos without bonuses. The bonuses for new players can make this 5 times faster ([Bonuses for new and solo players](#game-leveling-and-progression)).

If it fails:

| What you see | Cause | What to do |
|---|---|---|
| `game_response` `"cooldown"` | You attacked before the cooldown ended. | Wait for the `ms` in the reply ([Hearing back](#learn-hearing-back)). |
| `game_response` `"too_far"` | The goo is out of range. | Move nearer. A mage hits from 170 px, a ranger from 70 px. |
| `game_response` `"no_mp"` | MP is 0. | Do step 8. |
| `game_response` `"not_ready"` | The shared potion cooldown has not ended. | Wait for the `ms` in the reply. |
| `rip: true` in your `player` data | The character died. | See [Death and respawn](#game-stats-and-combat). Send [`respawn`](#send-respawn) after 12 s. |

### Your first day

The goal of the first day is about level 30, a full set of basic gear, and a merchant. The levels in this section are estimates for this guide, from the data in G. They are not official.

**Change the monster when it is too easy.** Use this rule: go to the next monster when you kill the current one in one or two hits. Before you go, examine the next monster in [Where to level](#game-leveling-and-progression):

- Its damage per second must be less than the HP that you get back. The free `regen_hp` gives 12.5 HP per second (50 HP each 4 s). An `hpot0` gives 100 HP per second (200 HP each 2 s), but each costs 20 gold.
- Monsters with `aggro` 1 attack you first. Thus more than one can attack you at the same time. Add their damage.
- Armor decreases physical damage, and resistance decreases magical damage ([The defense curve](#game-stats-and-combat)). A ranger does physical damage. A mage does magical damage.

**The Mainland ladder.** These monsters are all near the town. G 17478 gives their spawn boxes:

| Next monster | HP | Xp | Damage per second | Aggro | Spawn box in `main` |
|---|---|---|---|---|---|
| Goo (`goo`) | 100 | 100 | 2 | 0 | (−282, 702) to (218, 872) |
| Bee (`bee`) | 300 | 400 | 8 | 1 | (418, 994) to (668, 1208), and four more boxes |
| Tiny Crab (`crab`) | 400 | 500 | 10 | 0.2 | (−1353, −254) to (−1052, 122). 160 armor: better for a mage |
| Snake (`snake`) | 720 | 960 | 14 | 0 | (−254, 1812) to (90, 1990) |
| Squig (`squig`) | 1,000 | 600 | 4 | 0 | (−1353, 126) to (−998, 718) |
| Armadillo (`armadillo`) | 1,600 | 1,720 | 10 | 0 | (376, 1696) to (676, 1996) |
| Croc (`croc`) | 3,200 | 3,600 | 24 | 0.2 | (696, 1498) to (906, 1922) |
| Tortoise (`tortoise`) | 7,200 | 5,200 | 18 | 0 | (−1353, 720) to (−896, 1516). 200 armor |

> **Caution:** Do not go to the Huge Crabs (`crabx`) south-west of the town in your first day. They do 72 damage per second, have 210 armor, and attack first with the chance 0.5.

**Spend the gold.** Do these steps when you have the gold:

1. Keep about 2,000 gold for potions.
2. Buy the basic armor that you do not have from Gabriel (`basics`): gloves (3,400), a coat (6,000) and pants (7,800). The price is `G.items[name].g` (node/server.js:8442). See [`buy`](#send-buy).
3. Buy upgrade scrolls (`scroll0`, 1,000 gold) from Lucas (`scrolls`).
4. Upgrade each piece to +3 at Cue (`newupgrade`). The base chances are 99.99%, 98% and 95% ([Gear is more important than level](#game-leveling-and-progression)).
5. Sell the loot that you do not need to an NPC. An NPC pays 60% of the value (`G.multipliers.buy_to_sell`).

**Add a merchant.** When the fighter carries loot that it does not use, create a merchant on the same account. A merchant online does not stop the Lone Wolf bonus (node/logic/encouragement.js:223-236). It takes the loot and the gold, sells and upgrades. [A party and a merchant](#learn-a-party-and-a-merchant) shows the code.

### Your first week

The goal of the first week is about level 50, gear at +5 to +7, and a decision about a party. Again, the levels are estimates.

1. **Go to the next town.** When Mainland gives slow xp, talk to Alia (`transporter`) in the town. She takes you to Winterland or Desertland ([Travel](#game-maps-and-the-world)). Winterland has Arctic Bees and Wild Boars. Desertland has Porcupines and Scorpions.
2. **Set the home server.** Keep all fighters on one server, and send [`set_home`](#send-set_home) there before level 60 ([Servers, regions and PvP](#game-what-adventure-land-is)).
3. **Use the events.** Daily events start at 13:00 and 20:00, and nightly events at 23:00, in the local time of the server. Each character that helps to kill a world boss gets a share of the reward ([Events, bosses and seasons](#game-events-bosses-and-seasons)).
4. **Do monster hunts.** Daisy (`monsterhunter`) in the town gives a task to kill a number of one monster. The reward is monster tokens ([`monsterhunt`](#send-monsterhunt)).
5. **Get Merchant's Luck.** At level 40, your merchant gets `mluck`: +12 luck for 1 hour on any player ([Merchant](#game-classes)).
6. **Decide about a party.** Compare your xp per hour alone (with Lone Wolf) with an estimate for a party. A party is better when it can farm a monster that gives much more xp. For example, a warrior can tank and a priest can heal ([Party compositions](#game-classes)).
7. **Store items.** Put items that you keep in the bank, north of the town center ([`bank`](#send-bank)).

### From level 1 to the endgame

| Stage | Approximate levels | What happens |
|---|---|---|
| Start | 1-20 | Every character starts in Mainland. Goos, bees and crabs live near the town. Gear comes from the basics NPC. Upgrades to +3 almost always succeed. A level takes a few minutes. |
| Growth | 20-50 | The party moves to stronger Mainland monsters, the caves, Winterland and Desertland. The merchant gets Merchant's Luck at level 40. Gear quality starts to be more important than level. |
| Midgame | 50-70 | The Underground maps. Stronger party skills: Cleave, 3-Shot, Absorb Sins. Upgrades past +6 fail more often than they succeed, so good gear is expensive. Home server rules start at level 60. |
| Late game | 70-90 | Each level needs hundreds of millions of xp. Progress comes mostly from gear: higher upgrade levels, rare drops, crafted items. The dungeons that need keys: Crypt, Tomb, Spider Den, the lair of the Dark Mage. |
| Endgame | 90+ | Hunts for world bosses and instance bosses, for rare items. Gear at +10 and higher. Trade. |

These level ranges are an estimate for this guide, from the xp curve and the monster stats. They are not official. [Leveling and progression](#game-leveling-and-progression) shows the data.

## Classes

The class of a character sets its stats, its weapons and its skills. [`G.classes`](#g-classes) defines seven classes. You select the class when you create the character, and you cannot change it.

### The seven classes

MMO parties usually divide the work into three **roles**:

- **Tank**: the character that the monsters attack. A tank has much HP (health points) and armor. It pulls the attention of the monsters to itself.
- **DPS** (damage per second): a character whose job is to kill monsters quickly. The term also means the damage rate itself.
- **Healer** (also "support"): a character that keeps the other characters alive.

Adventure Land adds a fourth role, the **merchant**. The merchant does business. It does not fight.

| Class | Role | Main stat | Damage type | Base range | Base attacks/s | Weapons (mainhand) |
|---|---|---|---|---|---|---|
| Warrior | Tank, melee DPS | str | physical | 18 | 0.50 | sword, short sword, spear, mace, fist; two-handed axe, scythe, basher, great sword, rapier, bow |
| Paladin | Tank, support | str (and int) | physical | 15 | 0.40 | mace, sword, short sword |
| Rogue | Melee DPS | dex | physical | 15 | 0.45 | dagger, fist, stars; two-handed rapier, spear, short sword, bow |
| Ranger | Ranged DPS | dex | physical | 15 (bows add range) | 0.40 | bow, crossbow; two-handed fist, dagger |
| Mage | Ranged DPS | int | magical | 120 | 0.35 | staff, wand, wblade; great staff |
| Priest | Healer | int | magical | 120 | 0.35 | pmace, staff; two-handed wand |
| Merchant | Economy | int | none | 20 | 0.05 | many, mostly tools (rod, pickaxe) and the dartgun |

Source: `G.classes` (G 17478): the fields `main_stat`, `damage_type`, `range` and `frequency`, and the keys of `mainhand` and `doublehand`. Range is in pixels. The `range` of the weapon adds to it.

**Main stat.** Each class changes one attribute into damage. The server adds `weapon attack × main_stat / 20` to the attack of the character (`weapon_stat_attack`, node/server_functions.js:1745-1752). For example, a warrior with 100 str and a weapon with 50 attack gets +250 attack. The paladin is different: it uses `str/20 + int/40`.

**Damage type.** The damage type sets which defense stat decreases a hit. Armor decreases **physical** damage. Resistance decreases **magical** damage. **Pure** damage ignores both ([Stats and combat](#game-stats-and-combat)).

**Weapon modifiers.** Each weapon type changes some stats of the class. They are in `G.classes[cls].mainhand`, `doublehand` and `offhand` (node/server.js:1543-1555). The `frequency` values in these tables are hundredths of an attack per second: the server divides them by 100 (node/server.js:1295-1297). Some examples:

- A warrior with a basher gets −12 speed and −0.12 attacks per second.
- A mage with a wand gets +0.6 attacks per second and −18 `mp_cost`.
- A ranger with a crossbow gets +120 armor piercing and −0.36 attacks per second.

### How the base stats grow

Each class has five attributes: **str** (strength), **dex** (dexterity), **int** (intelligence), **vit** (vitality) and **for** (fortitude). Each attribute starts at the class value in `stats` and grows by `lstats` per level. The growth is faster at high levels (node/server.js:1430-1446):

| Levels | Gain per level |
|---|---|
| 1-40 | 1 × `lstats` |
| 41-55 | 2 × `lstats` |
| 56-65 | 3 × `lstats` |
| 66-80 | 4 × `lstats` |
| 81+ | 3 × `lstats` |

Gear and buffs add to these values. The attributes then set the derived stats: HP, MP (mana points), armor, resistance, attack speed and movement speed. [All stats](#game-stats-and-combat) gives the formulas. This table shows a character **with no gear**:

| Class | Lv 1 HP / MP | Lv 40 HP / MP | Lv 60 HP / MP | Lv 80 HP / MP | Main stat at 80 |
|---|---|---|---|---|---|
| Warrior | 624 / 55 | 2,477 / 400 | 4,779 / 665 | 8,847 / 1,050 | str 170 |
| Paladin | 724 / 220 | 2,577 / 1,000 | 4,879 / 1,775 | 8,947 / 3,000 | str 170, int 170 |
| Rogue | 349 / 80 | 1,292 / 395 | 2,465 / 630 | 4,684 / 955 | dex 170 |
| Ranger | 320 / 185 | 1,250 / 530 | 2,416 / 795 | 4,628 / 1,180 | dex 170 |
| Mage | 257 / 470 | 1,200 / 1,250 | 2,373 / 2,025 | 4,592 / 3,250 | int 170 |
| Priest | 305 / 470 | 1,507 / 1,250 | 3,053 / 2,025 | 5,861 / 3,250 | int 170 |
| Merchant | 109 / 400 | 820 / 1,180 | 1,725 / 1,955 | 3,458 / 3,180 | int 172 |

We calculated these values from `G.classes` (G 17478) with the formulas of the server (`calculate_player_stats`, node/server.js:1301). Real characters have much more, because gear adds attributes and HP.

The code below does the same calculation. `cls` is one entry of `G.classes`. `weaponAttack` is the total `attack` of the weapons; an offhand weapon counts at 70% (node/server.js:1526-1531). To run it, load G as in [Getting the game data](#learn-getting-the-game-data), then call `nakedStats` for a class and a level. The values must agree with the table above.

```js
// Naked stats from class + level, following calculate_player_stats (node/server.js:1301).
// cls is one entry of G.classes, e.g. G.classes.warrior.
function attributes(cls, level) {
  const out = {};
  for (const [stat, base] of Object.entries(cls.stats)) {
    const per = cls.lstats[stat];
    let v = base + level * per;
    // The per-level gain counts extra above these levels (node/server.js:1430-1446).
    if (level > 40) v += (level - 40) * per;
    if (level > 55) v += (level - 55) * per;
    if (level > 65) v += (level - 65) * per;
    if (level > 80) v -= (level - 80) * per;
    out[stat] = Math.floor(v);
  }
  return out;
}

function nakedStats(className, cls, level, weaponAttack = 0) {
  const a = attributes(cls, level);
  // Main-stat scaling of weapon attack; the server treats less than 5 as 5.
  const itemAttack = Math.max(weaponAttack, 5);
  const scale = className === "paladin" ? a.str / 20 + a.int / 40 : a[cls.main_stat] / 20;
  let attack = cls.attack + itemAttack * scale;
  if (className === "priest") attack *= 1.6;   // priests get x1.6 before output
  const heal = className === "priest" ? attack : 0; // a priest's heal ignores output
  attack = (attack * cls.output) / 100;           // output: priest 40, merchant 10, others 100
  return {
    ...a,
    maxHp: Math.round(cls.hp + a.str * 21 + a.vit * (48 + level / 3)),
    maxMp: Math.round(cls.mp + a.int * 15 + level * 5),
    armor: Math.round(cls.armor + Math.min(a.str, 160) + Math.max(0, a.str - 160) * 0.25),
    resistance: Math.round(cls.resistance + Math.min(a.int, 180) + Math.max(0, a.int - 180) * 0.25),
    frequency: cls.frequency + Math.min(level, 80) / 164 + Math.min(160, a.dex) / 640
      + Math.max(a.dex - 160, 0) / 925 + a.int / 1575, // attacks per second
    attack: Math.round(attack),
    heal: Math.round(heal),
  };
}
```

```ts
// Naked stats from class + level, following calculate_player_stats (node/server.js:1301).
type Attr = "str" | "dex" | "int" | "vit" | "for";

interface ClassDef { // the fields of a G.classes entry used here
  stats: Record<Attr, number>;
  lstats: Record<Attr, number>;
  main_stat: Attr;
  hp: number; mp: number; attack: number; armor: number; resistance: number;
  frequency: number; output: number;
}

interface NakedStats extends Record<Attr, number> {
  maxHp: number; maxMp: number; armor: number; resistance: number;
  frequency: number; attack: number; heal: number;
}

function attributes(cls: ClassDef, level: number): Record<Attr, number> {
  const out = {} as Record<Attr, number>;
  for (const stat of Object.keys(cls.stats) as Attr[]) {
    const per = cls.lstats[stat];
    let v = cls.stats[stat] + level * per;
    // The per-level gain counts extra above these levels (node/server.js:1430-1446).
    if (level > 40) v += (level - 40) * per;
    if (level > 55) v += (level - 55) * per;
    if (level > 65) v += (level - 65) * per;
    if (level > 80) v -= (level - 80) * per;
    out[stat] = Math.floor(v);
  }
  return out;
}

function nakedStats(className: string, cls: ClassDef, level: number, weaponAttack = 0): NakedStats {
  const a = attributes(cls, level);
  const itemAttack = Math.max(weaponAttack, 5); // the server treats less than 5 as 5
  const scale = className === "paladin" ? a.str / 20 + a.int / 40 : a[cls.main_stat] / 20;
  let attack = cls.attack + itemAttack * scale;
  if (className === "priest") attack *= 1.6;        // priests get x1.6 before output
  const heal = className === "priest" ? attack : 0; // a priest's heal ignores output
  attack = (attack * cls.output) / 100;             // output: priest 40, merchant 10, others 100
  return {
    ...a,
    maxHp: Math.round(cls.hp + a.str * 21 + a.vit * (48 + level / 3)),
    maxMp: Math.round(cls.mp + a.int * 15 + level * 5),
    armor: Math.round(cls.armor + Math.min(a.str, 160) + Math.max(0, a.str - 160) * 0.25),
    resistance: Math.round(cls.resistance + Math.min(a.int, 180) + Math.max(0, a.int - 180) * 0.25),
    frequency: cls.frequency + Math.min(level, 80) / 164 + Math.min(160, a.dex) / 640
      + Math.max(a.dex - 160, 0) / 925 + a.int / 1575, // attacks per second
    attack: Math.round(attack),
    heal: Math.round(heal),
  };
}
```

```python
# Naked stats from class + level, following calculate_player_stats (node/server.js:1301).
# cls is one entry of G.classes as a dict, e.g. G["classes"]["warrior"].
import math


def attributes(cls: dict, level: int) -> dict[str, int]:
    out = {}
    for stat, base in cls["stats"].items():
        per = cls["lstats"][stat]
        v = base + level * per
        # The per-level gain counts extra above these levels (node/server.js:1430-1446).
        if level > 40:
            v += (level - 40) * per
        if level > 55:
            v += (level - 55) * per
        if level > 65:
            v += (level - 65) * per
        if level > 80:
            v -= (level - 80) * per
        out[stat] = math.floor(v)
    return out


def js_round(x: float) -> int:
    # The server uses JS Math.round, which rounds halves up (182.5 -> 183).
    # Python's round() rounds halves to even (182.5 -> 182), so it can be 1 lower.
    return math.floor(x + 0.5)


def naked_stats(class_name: str, cls: dict, level: int, weapon_attack: float = 0) -> dict:
    a = attributes(cls, level)
    item_attack = max(weapon_attack, 5)  # the server treats less than 5 as 5
    if class_name == "paladin":
        scale = a["str"] / 20 + a["int"] / 40
    else:
        scale = a[cls["main_stat"]] / 20
    attack = cls["attack"] + item_attack * scale
    if class_name == "priest":
        attack *= 1.6  # priests get x1.6 before output
    heal = attack if class_name == "priest" else 0  # a priest's heal ignores output
    attack = attack * cls["output"] / 100  # output: priest 40, merchant 10, others 100
    return {
        **a,
        "max_hp": js_round(cls["hp"] + a["str"] * 21 + a["vit"] * (48 + level / 3)),
        "max_mp": js_round(cls["mp"] + a["int"] * 15 + level * 5),
        "armor": js_round(cls["armor"] + min(a["str"], 160) + max(0, a["str"] - 160) * 0.25),
        "resistance": js_round(cls["resistance"] + min(a["int"], 180) + max(0, a["int"] - 180) * 0.25),
        "frequency": cls["frequency"] + min(level, 80) / 164 + min(160, a["dex"]) / 640
        + max(a["dex"] - 160, 0) / 925 + a["int"] / 1575,  # attacks per second
        "attack": js_round(attack),
        "heal": js_round(heal),
    }
```

```go
// Naked stats from class + level, following calculate_player_stats (node/server.js:1301).
package stats

import "math"

// ClassDef holds the fields of a G.classes entry used here; the tags let
// encoding/json fill it straight from G.
type ClassDef struct {
	Stats      map[string]float64 `json:"stats"`
	Lstats     map[string]float64 `json:"lstats"`
	MainStat   string             `json:"main_stat"`
	HP         float64            `json:"hp"`
	MP         float64            `json:"mp"`
	Attack     float64            `json:"attack"`
	Armor      float64            `json:"armor"`
	Resistance float64            `json:"resistance"`
	Frequency  float64            `json:"frequency"`
	Output     float64            `json:"output"`
}

type NakedStats struct {
	Attr                            map[string]float64
	MaxHP, MaxMP, Armor, Resistance float64
	Frequency, AttackValue, Heal    float64
}

func Attributes(cls ClassDef, level float64) map[string]float64 {
	out := map[string]float64{}
	for stat, base := range cls.Stats {
		per := cls.Lstats[stat]
		v := base + level*per
		// The per-level gain counts extra above these levels (node/server.js:1430-1446).
		if level > 40 {
			v += (level - 40) * per
		}
		if level > 55 {
			v += (level - 55) * per
		}
		if level > 65 {
			v += (level - 65) * per
		}
		if level > 80 {
			v -= (level - 80) * per
		}
		out[stat] = math.Floor(v)
	}
	return out
}

func Naked(className string, cls ClassDef, level, weaponAttack float64) NakedStats {
	a := Attributes(cls, level)
	itemAttack := math.Max(weaponAttack, 5) // the server treats less than 5 as 5
	scale := a[cls.MainStat] / 20
	if className == "paladin" {
		scale = a["str"]/20 + a["int"]/40
	}
	attack := cls.Attack + itemAttack*scale
	heal := 0.0
	if className == "priest" {
		attack *= 1.6 // priests get x1.6 before output
		heal = attack // a priest's heal ignores output
	}
	attack = attack * cls.Output / 100 // output: priest 40, merchant 10, others 100
	return NakedStats{
		Attr:       a,
		MaxHP:      math.Round(cls.HP + a["str"]*21 + a["vit"]*(48+level/3)),
		MaxMP:      math.Round(cls.MP + a["int"]*15 + level*5),
		Armor:      math.Round(cls.Armor + math.Min(a["str"], 160) + math.Max(0, a["str"]-160)*0.25),
		Resistance: math.Round(cls.Resistance + math.Min(a["int"], 180) + math.Max(0, a["int"]-180)*0.25),
		Frequency: cls.Frequency + math.Min(level, 80)/164 + math.Min(160, a["dex"])/640 +
			math.Max(a["dex"]-160, 0)/925 + a["int"]/1575, // attacks per second
		AttackValue: math.Round(attack),
		Heal:        math.Round(heal),
	}
}
```

```csharp
// Naked stats from class + level, following calculate_player_stats (node/server.js:1301).
using System.Text.Json.Serialization;

// The fields of a G.classes entry used here; System.Text.Json fills it straight from G.
public record ClassDef(
    [property: JsonPropertyName("stats")] Dictionary<string, double> Stats,
    [property: JsonPropertyName("lstats")] Dictionary<string, double> Lstats,
    [property: JsonPropertyName("main_stat")] string MainStat,
    [property: JsonPropertyName("hp")] double Hp,
    [property: JsonPropertyName("mp")] double Mp,
    [property: JsonPropertyName("attack")] double Attack,
    [property: JsonPropertyName("armor")] double Armor,
    [property: JsonPropertyName("resistance")] double Resistance,
    [property: JsonPropertyName("frequency")] double Frequency,
    [property: JsonPropertyName("output")] double Output);

public record NakedStats(Dictionary<string, double> Attr, double MaxHp, double MaxMp,
    double Armor, double Resistance, double Frequency, double Attack, double Heal);

public static class Stats
{
    public static Dictionary<string, double> Attributes(ClassDef cls, int level)
    {
        var output = new Dictionary<string, double>();
        foreach (var (stat, baseValue) in cls.Stats)
        {
            double per = cls.Lstats[stat];
            double v = baseValue + level * per;
            // The per-level gain counts extra above these levels (node/server.js:1430-1446).
            if (level > 40) v += (level - 40) * per;
            if (level > 55) v += (level - 55) * per;
            if (level > 65) v += (level - 65) * per;
            if (level > 80) v -= (level - 80) * per;
            output[stat] = Math.Floor(v);
        }
        return output;
    }

    // MidpointRounding.AwayFromZero matches JS Math.round for the positive values here.
    static double R(double x) => Math.Round(x, MidpointRounding.AwayFromZero);

    public static NakedStats Naked(string className, ClassDef cls, int level, double weaponAttack = 0)
    {
        var a = Attributes(cls, level);
        double itemAttack = Math.Max(weaponAttack, 5); // the server treats less than 5 as 5
        double scale = className == "paladin" ? a["str"] / 20 + a["int"] / 40 : a[cls.MainStat] / 20;
        double attack = cls.Attack + itemAttack * scale;
        if (className == "priest") attack *= 1.6;          // priests get x1.6 before output
        double heal = className == "priest" ? attack : 0;  // a priest's heal ignores output
        attack = attack * cls.Output / 100;                // output: priest 40, merchant 10, others 100
        return new NakedStats(a,
            MaxHp: R(cls.Hp + a["str"] * 21 + a["vit"] * (48 + level / 3.0)),
            MaxMp: R(cls.Mp + a["int"] * 15 + level * 5),
            Armor: R(cls.Armor + Math.Min(a["str"], 160) + Math.Max(0, a["str"] - 160) * 0.25),
            Resistance: R(cls.Resistance + Math.Min(a["int"], 180) + Math.Max(0, a["int"] - 180) * 0.25),
            Frequency: cls.Frequency + Math.Min(level, 80) / 164.0 + Math.Min(160, a["dex"]) / 640
                + Math.Max(a["dex"] - 160, 0) / 925 + a["int"] / 1575, // attacks per second
            Attack: R(attack),
            Heal: R(heal));
    }
}
```

```rust
// Naked stats from class + level, following calculate_player_stats (node/server.js:1301).
// cargo add serde --features derive
use serde::Deserialize;
use std::collections::HashMap;

/// The fields of a G.classes entry used here; serde_json fills it straight from G.
#[derive(Deserialize)]
pub struct ClassDef {
    pub stats: HashMap<String, f64>,
    pub lstats: HashMap<String, f64>,
    pub main_stat: String,
    pub hp: f64,
    pub mp: f64,
    pub attack: f64,
    pub armor: f64,
    pub resistance: f64,
    pub frequency: f64,
    pub output: f64,
}

pub struct NakedStats {
    pub attr: HashMap<String, f64>,
    pub max_hp: f64,
    pub max_mp: f64,
    pub armor: f64,
    pub resistance: f64,
    pub frequency: f64,
    pub attack: f64,
    pub heal: f64,
}

pub fn attributes(cls: &ClassDef, level: f64) -> HashMap<String, f64> {
    let mut out = HashMap::new();
    for (stat, base) in &cls.stats {
        let per = cls.lstats[stat];
        let mut v = base + level * per;
        // The per-level gain counts extra above these levels (node/server.js:1430-1446).
        if level > 40.0 { v += (level - 40.0) * per; }
        if level > 55.0 { v += (level - 55.0) * per; }
        if level > 65.0 { v += (level - 65.0) * per; }
        if level > 80.0 { v -= (level - 80.0) * per; }
        out.insert(stat.clone(), v.floor());
    }
    out
}

pub fn naked(class_name: &str, cls: &ClassDef, level: f64, weapon_attack: f64) -> NakedStats {
    let a = attributes(cls, level);
    let item_attack = weapon_attack.max(5.0); // the server treats less than 5 as 5
    let scale = if class_name == "paladin" {
        a["str"] / 20.0 + a["int"] / 40.0
    } else {
        a[&cls.main_stat] / 20.0
    };
    let mut attack = cls.attack + item_attack * scale;
    let mut heal = 0.0;
    if class_name == "priest" {
        attack *= 1.6; // priests get x1.6 before output
        heal = attack; // a priest's heal ignores output
    }
    attack = attack * cls.output / 100.0; // output: priest 40, merchant 10, others 100
    let (s, i, d, vit) = (a["str"], a["int"], a["dex"], a["vit"]);
    NakedStats {
        max_hp: (cls.hp + s * 21.0 + vit * (48.0 + level / 3.0)).round(),
        max_mp: (cls.mp + i * 15.0 + level * 5.0).round(),
        armor: (cls.armor + s.min(160.0) + (s - 160.0).max(0.0) * 0.25).round(),
        resistance: (cls.resistance + i.min(180.0) + (i - 180.0).max(0.0) * 0.25).round(),
        frequency: cls.frequency + level.min(80.0) / 164.0 + d.min(160.0) / 640.0
            + (d - 160.0).max(0.0) / 925.0 + i / 1575.0, // attacks per second
        attack: attack.round(),
        heal: heal.round(),
        attr: a,
    }
}
```

```java
// Naked stats from class + level, following calculate_player_stats (node/server.js:1301).
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.HashMap;
import java.util.Map;

// The fields of a G.classes entry used here; Jackson fills it straight from G.
@JsonIgnoreProperties(ignoreUnknown = true)
record ClassDef(Map<String, Double> stats, Map<String, Double> lstats,
                @JsonProperty("main_stat") String mainStat, double hp, double mp, double attack,
                double armor, double resistance, double frequency, double output) {}

record NakedStats(Map<String, Double> attr, double maxHp, double maxMp, double armor,
                  double resistance, double frequency, double attack, double heal) {}

final class Stats {
    static Map<String, Double> attributes(ClassDef cls, int level) {
        Map<String, Double> out = new HashMap<>();
        cls.stats().forEach((stat, base) -> {
            double per = cls.lstats().get(stat);
            double v = base + level * per;
            // The per-level gain counts extra above these levels (node/server.js:1430-1446).
            if (level > 40) v += (level - 40) * per;
            if (level > 55) v += (level - 55) * per;
            if (level > 65) v += (level - 65) * per;
            if (level > 80) v -= (level - 80) * per;
            out.put(stat, Math.floor(v));
        });
        return out;
    }

    static NakedStats naked(String className, ClassDef cls, int level, double weaponAttack) {
        Map<String, Double> a = attributes(cls, level);
        double str = a.get("str"), dex = a.get("dex"), intel = a.get("int"), vit = a.get("vit");
        double itemAttack = Math.max(weaponAttack, 5); // the server treats less than 5 as 5
        double scale = className.equals("paladin") ? str / 20 + intel / 40 : a.get(cls.mainStat()) / 20;
        double attack = cls.attack() + itemAttack * scale;
        double heal = 0;
        if (className.equals("priest")) {
            attack *= 1.6; // priests get x1.6 before output
            heal = attack; // a priest's heal ignores output
        }
        attack = attack * cls.output() / 100; // output: priest 40, merchant 10, others 100
        return new NakedStats(a,
            Math.round(cls.hp() + str * 21 + vit * (48 + level / 3.0)),
            Math.round(cls.mp() + intel * 15 + level * 5),
            Math.round(cls.armor() + Math.min(str, 160) + Math.max(0, str - 160) * 0.25),
            Math.round(cls.resistance() + Math.min(intel, 180) + Math.max(0, intel - 180) * 0.25),
            cls.frequency() + Math.min(level, 80) / 164.0 + Math.min(160, dex) / 640
                + Math.max(dex - 160, 0) / 925 + intel / 1575, // attacks per second
            Math.round(attack),
            Math.round(heal));
    }
}
```

### Warrior

The warrior is the usual tank. With the paladin, it has the highest base HP. Each point of str also gives one point of armor, to a maximum of 160. The warrior can use many two-handed weapons. It also gets courage from str (`courage += round(str/30)`, node/server.js:1592-1594). Thus more monsters can attack a warrior before it becomes afraid ([Aggro, tanks and fear](#game-stats-and-combat)).

| Skill | Level | Effect | Use in a bot |
|---|---|---|---|
| Taunt (`taunt`) | 1 | Moves the target of a monster from a party member to the warrior (node/server.js:3370-3380). Cooldown 3 s, range 200 px | The main tank tool. If a monster attacks the priest or the mage, taunt it. |
| Charge (`charge`) | 1 | +30 speed for 3.2 s. Cooldown 40 s | Use it when the party walks between areas. |
| Dash (`dash`) | 1 | A short jump forward, over obstacles. 120 MP | Escape, short paths. |
| Cleave (`cleave`) | 52 | Hits all enemies in 160 px for 10% to 90% of attack (random) (node/server.js:3324-3330). Needs an axe or a scythe | Kill groups of weak monsters. |
| Stomp (`stomp`) | 52 | Stuns all enemies in 400 px for 3.2 s. Needs a basher | Emergency control of a crowd. |
| Hard Shell (`hardshell`) | 60 | +800 armor for 8 s. Speed becomes 10 | Survive a burst of physical damage. |
| Agitate (`agitate`) | 68 | Taunts all monsters in 320 px | Pull a full spawn area to the tank. |
| War Cry (`warcry`) | 70 | Party in 600 px: +0.1 attacks/s, +20 speed, +160 armor and +160 resistance for 8 s | Use it when it is ready during a fight. |

### Paladin

The paladin mixes str and int. It is a tank with a mace and a shield, and it protects its allies. It has the highest base HP. Str gives it armor, and int gives it resistance. It also gets pure courage from both (`pcourage += round(str/30 + int/30)`, node/server.js:1598-1600). The skill handler in the live server implements all paladin skills (node/server.js:10213-10290).

| Skill | Level | Effect |
|---|---|---|
| Heal (`selfheal`) | 1 | Heals the paladin for 400. 600 at level 60, 720 at 72, 800 at 80 (node/server.js:3360-3369) |
| Mana Shield (`mshield`) | 1 | Toggle. Damage removes MP before HP. 1 MP stops 1.5 HP of damage: 1.75 at level 70+, 2 at 80+, 2.4 at 90+, 3 at 100+. The shield keeps 200 MP (node/server.js:4212-4237) |
| Smash (`smash`) | 10 | A hit for 0.36 × attack. Needs a mace |
| Cleansing Light (`cleansing_light`) | 30 | Removes all `cleansable` conditions from one ally in 240 px. Not on yourself (node/server.js:10213-10235) |
| Guardian's Oath (`guardians_oath`) | 50 | For 8 s, the paladin takes 35% of the damage of one ally. The paladin keeps at least 1 HP, and the oath stops when the paladin is more than 360 px away. The HP that the paladin loses returns as MP: 40% at level 50, up to 100% at 110 (node/server.js:3678-3705, 10236-10256) |
| Purify (`purify`) | 60 | 2,000 pure damage. Removes each buff and debuff of the target, +400 damage for each (node/server.js:4026-4040). A kill gives the Purifier buff |
| Shield Slam (`shield_slam`) | 60 | A physical hit for 3 × attack + 12 × armor (armor counts to 1,000). Needs a shield. 2,000 MP. No crits and no item effects (node/server.js:3416-3420) |
| Paladin Aura (`paladin_aura`) | 60 | A permanent aura on near allies (320 px). Each use changes it to the next form: Bulwark (armor, HP), Sanctuary (resistance, MP), Zeal (output, attack speed), Warding (resistance to conditions). The values grow at levels 60, 70, 80, 90, 100 and 110 (node/server.js:15839-15847) |
| Aether Shield (`aether_shield`) | 60 | Toggle, in place of Mana Shield. Magical damage still removes HP, but the HP that you lose returns as MP: 50% at level 60, up to 100% at 110 (node/server.js:4271-4283) |
| Beacon of Resolve (`beacon_of_resolve`) | 70 | Party in 480 px: +15 fortitude and +1 of each courage for 8 s (node/server.js:10257-10276) |

### Rogue

The rogue is a fast melee DPS. Each rogue hit adds +1 damage to the next hits on the same target, for 10 s (the `stack` passive, node/server.js:4020-4025). `G.skills.stack.max` (2,000) sets the limit. Thus a rogue becomes stronger when it hits one target for a long time. Other players often ask rogues for the Rogue Swiftness buff.

| Skill | Level | Effect |
|---|---|---|
| Assassin's Smoke (`invis`) | 1 | The rogue is invisible until it attacks. While invisible, its attack is × 1.25 (node/server.js:1706-1709) |
| Quick Punch, Quick Stab | 1 | Extra hits for 0.25 × (fist) or 0.36 × (dagger) attack, between normal attacks. Cooldown 250 ms |
| Mental Burst (`mentalburst`) | 1 | A magical hit for 0.6 × attack. If it kills, the damage returns as MP (node/server.js:4377-4379). Needs 64 int |
| A Poisonous Touch (`pcoat`) | 1 | For 7 s, each hit poisons. Uses a poison sack |
| Pickpocket | 16 | Steals one PvP-marked item from a player |
| Rogue Swiftness (`rspeed`) | 40 | Buff for any player: +7 speed and +0.08 attacks/s for 45 minutes |
| Fan of Knives (`fanofknives`) | 65 | Five knives at a maximum of 5 targets that you select in 160 px, 0.85 × attack each. Needs the knife belt. Uses the cooldown of the attack (node/server.js:10507-10570) |
| Shadow Strike | 70 | Hits a random enemy in 360 px. Uses a shadow stone |

### Ranger

The ranger is the easiest DPS class. It has a long range with bows and does physical damage. Its multi-target shots use the cooldown of the normal attack. The G description calls the ranger "very suitable for beginners". Rangers have low HP, so range is their protection: they hit monsters before the monsters arrive.

| Skill | Level | Effect |
|---|---|---|
| Supershot | 1 | 1.5 × damage at 3 × range. Cooldown 30 s |
| Hunter's Mark (`huntersmark`) | 1 | The target gets 10% more damage for 10 s and cannot use stealth |
| Poison Arrow | 1 | A hit for 200 that poisons. Uses a poison sack |
| Track | 1 | Finds characters in 1,440 px |
| 3-Shot (`3shot`) | 60 | Attacks a maximum of 3 targets at 0.7 × damage, in place of a normal attack |
| 4 Finger Technique | 64 | Stuns a player for 5 s ("deep meditation"). A PvP tool |
| Piercing Shot | 72 | 0.75 × damage that ignores 500 armor |
| 5-Shot (`5shot`) | 75 | Attacks a maximum of 5 targets at 0.5 × damage |

3-Shot and 5-Shot cost only the MP of the skill. The arrows do not cost the normal MP of an attack (node/server.js:3312-3319, 10562). Thus rangers are very good against groups of weak monsters.

### Mage

The mage does magical ranged damage and has a very large MP pool. Resistance decreases magical damage, and most monsters have little resistance. Thus mages are good against monsters with high armor. Mages can also move other characters.

| Skill | Level | Effect | Use in a bot |
|---|---|---|---|
| Mana Burst (`burst`) | 1 | Uses all MP. 0.555 pure damage per MP | The last hit on a big target. |
| Blink | 1 | Teleports the mage to a near point. 1,600 MP | Escape, a new position. |
| Magiport | 1 | Pulls a player to the mage. 900 MP | Bring the party together without a walk. |
| Light | 1 | Shows invisible characters | PvP. |
| Energize (`energize`) | 20 | Gives MP to a player. The player also attacks faster for a short time | Give MP to the priest, so the heals do not stop. |
| Alchemy | 40 | Changes an item into gold | Not often useful. There is a risk. |
| Reflective Shield | 60 | An ally gets +20% reflection for 5 s | Against magical bosses. |
| Entangle | 72 | Roots a target. Uses an Essence of Nature | Control of a monster. |
| Controlled Mana Burst (`cburst`) | 75 | Uses a selected quantity of MP on many targets, 0.5 magical damage per MP | Kill many weak monsters at the same time. |
| Arcane Needle (`arcane_needle`) | 90 | A wand hit for 0.75 × attack that ignores 500 resistance and cannot be reflected (node/server.js:3346-3349) | Magical targets with high resistance. |

### Priest

The priest is the healer. The priest skill `heal` is a normal attack on an ally, and it uses the cooldown of the attack. Priests do little damage: their `output` is 40, so damage is 40% of attack after a ×1.6 bonus. Their heal uses the full ×1.6 attack (node/server.js:1589-1591, 1656-1659). Int gives them magical courage (`mcourage += round(int/30)`). The G description says: "Every serious party needs at least one priest."

| Skill | Level | Effect | Use in a bot |
|---|---|---|---|
| Heal (`heal`) | 1 | Heals one target for about the `heal` stat of the priest. Costs `mp_cost` | Heal the character with the lowest HP. |
| Party Heal (`partyheal`) | 1 | Heals all party members for 400 (600 at 60, 720 at 72, 800 at 80). 400 MP | Use it when two or more characters are hurt. |
| Curse (`curse`) | 1 | For 5 s, the target does 20% less damage, gets 20% more damage and moves 20 slower | Curse the target of the party. |
| Revive | 1 | Revives a dead player. Uses an Essence of Life | Prevent the walk after a respawn. |
| Absorb Sins (`absorb`) | 55 | Pulls all monsters that target an ally to the priest | Save an ally that is about to die. |
| Phase Out | 64 | +64 evasion, less speed. Uses a shadow stone | Survive. |
| Dark Blessing | 70 | Party in 600 px: +25% damage for 8 s | Use it when it is ready. |

Heals do not always give their full value (node/server.js:3985-3995):

- The resistance of the target decreases the heal at half strength: `damage_multiplier((resistance − rpiercing)/2)`.
- A poisoned target gets only 25% of the heal.
- On HARDCORE, the server multiplies all heals by 0.6 (`B.heal_multiplier`, node/server.js:376).

### Merchant

The merchant does not fight. Its normal attacks fail with `attack_failed`, except with a dartgun (node/server.js:3209-3215). With a dartgun, each shot costs 2 gold for each point of damage (node/server.js:3472-3477). The merchant has the most skills for items. Only a merchant can open a **merchant stand** to sell items to other players. Its base attack speed is 0.05 per second, and its `output` is 10.

| Skill | Level | Effect |
|---|---|---|
| Fishing, Mining | 16 | With a rod or a pickaxe at a fishing or mining zone: rolls the `f1` or `m1` drop table |
| Mass Production, Mass Production++ | 30, 60 | The next upgrade or compound is 50% or 90% faster |
| Mass Exchange, Mass Exchange++ | 40, 70 | The next exchange is 50% or 90% faster |
| Merchant's Luck (`mluck`) | 40 | Buff for any player: +12 luck for 1 hour. The merchant has a 2% chance to get a copy of the loot of that player |
| Throw Stuff | 60 | Throws an item at a target |
| Merchant's Courage, Merchant's Frenzy | 70, 85 | Emergency buffs: speed and evasion, or a short burst of attack speed |

**Merchants get no xp from kills.** The server skips merchants when it gives kill xp (node/server.js:2763, 2810, 2844). A merchant gets xp from these sources:

- Trades with other players: 3.2 xp per gold of tax on each trade (`merchant_xp_logic`, node/server_functions.js:746-751).
- Trade offers, below level 70: some xp from the value of the item, with a limit per partner (`trade_swap_xp`, node/server_functions.js:753).
- Gold given to the Lost and Found NPC with [`donate`](#send-donate): 3.2 to 4.8 xp per gold. The rate is higher when the server has less donated gold (node/server.js:8629-8667).
- "Marketing xp" every 3 hours while its stand is open (node/server.js:16003-16039). To level 40, it is 1/100 of the xp for its level. After level 40, it is less.

The G description says that the server and character limits do not apply to merchants. In the live code, an account can have one merchant online on each server (node/server_functions.js:399-410).

### Party compositions

A **party** has a maximum of 10 characters (`limits.party_max`, node/server.js:259). The members share xp and loot. Some usual compositions:

| Composition | Reason |
|---|---|
| One ranger or mage, plus a merchant | The start. Easy to code. The Lone Wolf condition gives 3 × gold, xp and luck while only one non-merchant character of the account is online (`G.conditions.encouragement_lonewolf`, node/logic/encouragement.js:223-271). |
| Warrior, priest, mage (or ranger), merchant | The usual party: tank, healer, DPS, economy. It survives almost all monsters that its gear allows. |
| Ranger, priest, mage, merchant | No tank. This works when the monsters die before they arrive. |
| Three rangers, merchant | Only DPS, for crowded areas of weak monsters. The party dies easily. |

[Xp from a kill](#game-leveling-and-progression) tells you how the party divides the xp of a kill.

## Stats and combat

Combat is automatic after you send an [`attack`](#send-attack). The server examines range and cooldown, and then sends a projectile. When the projectile arrives, the server calculates the damage from the attack of the attacker and the defense of the target.

### All stats

The stats are part of the data of the character (the `player` events). The function `calculate_player_stats` (node/server.js:1301) calculates them again after each change of gear, level or conditions. The server adds the values of gear and conditions to the base values of the class (`apply_stats`, node/server.js:1288).

| Stat | Meaning | Calculation or use |
|---|---|---|
| `str` | Strength | +21 max HP per point. +1 armor per point (0.25 above 160). +1/64 speed |
| `dex` | Dexterity | Attack speed: +1/640 per point to 160, then +1/925. +1/32 speed. Main stat of the rogue and the ranger |
| `int` | Intelligence | +15 max MP per point. +1 resistance per point (0.25 above 180). A small attack speed bonus. Main stat of the mage, the priest and the merchant |
| `vit` | Vitality | +`48 + level/3` max HP per point |
| `for` | Fortitude | Decreases damage from player attacks, like extra defense: `damage_multiplier(for × 5)` (node/server.js:4042-4045). 20 fortitude stops about 10% |
| `attack` | Damage of a normal hit | `class attack + max(weapon attack, 5) × main_stat/20`. ×1.6 for priests. Then × `output`/100 |
| `heal` | Healing of a priest heal | Priests only: their attack before `output` |
| `output` | Damage output, % | 100 for most classes, 40 for the priest, 10 for the merchant. A curse gives −20 |
| `frequency` | Attacks per second | Class base + `min(level,80)/164` + dex and int terms. The cooldown of the attack is `attack_ms = round(1000 / frequency)` (node/server.js:1621-1627) |
| `speed` | Movement in px per second | Class base + dex/32 + str/64 (each attribute counts to 256) + level terms (node/server.js:1603-1608). × 0.95 in Winterland |
| `range` | Attack range in px | Class base + weapon `range` |
| `armor` | Physical defense | See [The defense curve](#game-stats-and-combat) below |
| `resistance` | Magical defense | The same curve |
| `apiercing`, `rpiercing` | Armor piercing, resistance piercing | The server subtracts them from the defense of the target |
| `crit` | Chance (%) of a critical hit | A critical hit ("crit") multiplies damage by `2 + critdamage/100` |
| `critdamage` | Extra damage of a crit, % | |
| `evasion` | Chance (%) to avoid a **physical** hit | Maximum 50 for players (node/server.js:1759) |
| `reflection` | Chance (%) to send a **magical** hit back to its attacker | Maximum 30, or 50 with the Reflective Shield buff (node/server.js:1760) |
| `miss` | Chance (%) that your own attacks miss | Comes from unsuitable weapons. A warrior with a bow has 50 |
| `avoidance` | Chance (%) that attacks on you miss | Mostly on monsters |
| `lifesteal`, `manasteal` | % of the damage you do that returns to you as HP or MP | |
| `dreturn` | Damage return, % | A melee attacker (range less than 75) with physical damage gets this part of its hit back (node/server.js:4292-4308) |
| `mp_cost` | MP for each normal attack and each heal | Class base × `(1 + min(level,80)/10)`, + crit × 1.25, + lifesteal × 1.5, + manasteal/5, + piercing/15 (node/server.js:1637-1648). A mage at level 80 pays 45 MP for each attack |
| `courage`, `mcourage`, `pcourage` | The number of physical, magical or pure monsters that can target you before fear starts | See [Aggro, tanks and fear](#game-stats-and-combat) below |
| `luck`, `gold`, `xp` | Bonus % to the drop chance, the gold and the xp | The server changes them into the multipliers `luckm`, `goldm` and `xpm` (node/server.js:1692-1697) |
| `incdmgamp` | Increase of incoming damage, % | Cursed (+20) and Marked (+10) set it |

### How the server calculates a hit

An attack is a projectile. When you attack, `commence_attack` (node/server.js:3159) first makes sure that the hit is legal. For example, the attacker is not a merchant, the target is not in the party, and the map is not safe. Then it selects the projectile and the damage type and sends an [`action`](#recv-action) to the near characters. The travel time of the projectile is distance divided by projectile speed (node/server.js:3582-3586).

When the projectile arrives, `complete_attack` (node/server.js:3707) does these steps in this sequence:

1. **Reflection** (magical hits only): with the chance `target.reflection`%, the hit returns to the attacker at 0.9 to 1.1 × damage (node/server.js:3763-3812).
2. **Evasion** (physical hits only): with the chance `target.evasion`%, the hit does no damage. The event has `evade: true`.
3. **Miss**: with the chance `miss`% of the attacker or `avoidance`% of the target, the hit does no damage. It also misses a dead or absent target. The event has `miss: true`.
4. **Movement**: the target can be more than 72 px from the aim point of the projectile (108 px for heals). Then the hit misses with `avoid: true` (node/server.js:3833-3853).
5. **Damage**, for each target that the hit touches (node/server.js:4014-4057):
   - crit roll: × `(2 + critdamage/100)`;
   - rogue stack: + the number of stacks;
   - mob combo (see below) and a random roll: × combo × 0.9 to 1.1, rounded up;
   - fortitude (only against player attackers) and the defense curve: × `damage_multiplier(for × 5)` × `damage_multiplier(defense − piercing)`;
   - `incdmgamp`: × `(100 + incdmgamp)/100`.
6. **After the damage**: lifesteal and manasteal, Mana Shield, Guardian's Oath, the death check, damage return, and the [`hit`](#recv-hit) event to all near characters.

Step 4 is the reason why **kiting** works. Kiting means that you move away from a monster while you attack it. A slow projectile or a melee monster then cannot hit you.

Pure damage skips steps 1 and 2. Its damage is the damage of the skill, with no roll and no defense (node/server.js:4151-4153). Your client sees steps 1 to 4 as a `hit` event with `damage: 0` and one of `reflect`, `evade`, `miss` or `avoid`.

**A possible server bug.** `commence_attack` adds the `apiercing` or `rpiercing` of the attacker to the projectile (node/server.js:3487-3491). Then `complete_attack` subtracts the piercing of the attacker **and** the piercing of the projectile (node/server.js:4049). Thus the piercing stat of a character counts two times. It is unclear from the source if this is intentional.

### The defense curve

The function `damage_multiplier(defense)` (js/old_common_functions.js:826) changes armor or resistance into a damage multiplier. At first, each point of defense stops about 0.1% of the damage. In each later band of 100 points, a point stops a little less. The multiplier never goes below 0.05. Negative defense, from piercing or debuffs, increases the damage, to a maximum of 1.32.

| Defense | −300 | −100 | 0 | 100 | 200 | 400 | 600 | 800 | 1000 | 1500 | 2000+ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Damage multiplier | 1.15 | 1.09 | 1.00 | 0.90 | 0.80 | 0.62 | 0.46 | 0.35 | 0.27 | 0.07 | 0.05 |

Thus 200 armor stops one fifth of all physical damage. That is why tanks collect armor. A monster with 400 armor needs about 40% more time to kill with physical damage than a monster with no armor.

The code below calculates one hit. It does not include combos, splash damage, procs or Mana Shield. `pierce` is the piercing to subtract. To copy the possible bug above, give two times the piercing of the attacker. To use it, call `hitDamage` with the attack of the attacker and the defense of the target. For example, an attack of 100 against 0 defense gives 90 to 110.

```js
// damage_multiplier, js/old_common_functions.js:826. 100-point bands of defense each remove
// a little less damage per point; negative defense adds damage in 50-point bands.
const POS_RATES = [0.001, 0.001, 0.00095, 0.0009, 0.00082, 0.0007, 0.0006, 0.0005];
const NEG_RATES = [0.001, 0.00075, 0.0005];

function damageMultiplier(defense) {
  let reduction = 0;
  for (let i = 0; i < POS_RATES.length; i++) {
    reduction += Math.max(0, Math.min(100, defense - 100 * i)) * POS_RATES[i];
  }
  reduction += Math.max(0, defense - 800) * 0.0004; // above 800: 0.04% per point, no band
  let bonus = 0;
  for (let j = 0; j < NEG_RATES.length; j++) {
    bonus += Math.max(0, Math.min(50, -defense - 50 * j)) * NEG_RATES[j];
  }
  bonus += Math.max(0, -150 - defense) * 0.00025;
  return Math.min(1.32, Math.max(0.05, 1 - reduction + bonus)); // clamped to [0.05, 1.32]
}

// One physical or magical hit, following complete_attack (node/server.js:3707).
function hitDamage({ attack, critChance = 0, critDamage = 0, targetDefense = 0,
                     pierce = 0, targetFor = 0, attackerIsPlayer = true, incdmgamp = 0 }) {
  let dmg = attack;
  if (Math.random() * 100 < critChance) dmg *= 2 + critDamage / 100; // crit
  dmg = Math.ceil(dmg * (0.9 + Math.random() * 0.2));               // +-10% roll
  const fort = attackerIsPlayer && targetFor ? damageMultiplier(targetFor * 5) : 1;
  dmg = Math.ceil(dmg * fort * damageMultiplier(targetDefense - pierce));
  if (incdmgamp) dmg = Math.round((dmg * (100 + incdmgamp)) / 100);  // cursed, marked
  return dmg;
}
```

```ts
// damage_multiplier, js/old_common_functions.js:826. 100-point bands of defense each remove
// a little less damage per point; negative defense adds damage in 50-point bands.
const POS_RATES: readonly number[] = [0.001, 0.001, 0.00095, 0.0009, 0.00082, 0.0007, 0.0006, 0.0005];
const NEG_RATES: readonly number[] = [0.001, 0.00075, 0.0005];

function damageMultiplier(defense: number): number {
  let reduction = 0;
  POS_RATES.forEach((rate, i) => {
    reduction += Math.max(0, Math.min(100, defense - 100 * i)) * rate;
  });
  reduction += Math.max(0, defense - 800) * 0.0004; // above 800: 0.04% per point, no band
  let bonus = 0;
  NEG_RATES.forEach((rate, j) => {
    bonus += Math.max(0, Math.min(50, -defense - 50 * j)) * rate;
  });
  bonus += Math.max(0, -150 - defense) * 0.00025;
  return Math.min(1.32, Math.max(0.05, 1 - reduction + bonus)); // clamped to [0.05, 1.32]
}

interface HitInput {
  attack: number;           // attacker's attack (or the skill's damage)
  critChance?: number;      // attacker's crit, %
  critDamage?: number;      // attacker's critdamage, %
  targetDefense?: number;   // armor for physical, resistance for magical
  pierce?: number;          // piercing to subtract (see the double-count quirk)
  targetFor?: number;       // target's fortitude; only counts against player attackers
  attackerIsPlayer?: boolean;
  incdmgamp?: number;       // target's incoming damage amplification, %
}

// One physical or magical hit, following complete_attack (node/server.js:3707).
function hitDamage(h: HitInput): number {
  const { attack, critChance = 0, critDamage = 0, targetDefense = 0, pierce = 0,
          targetFor = 0, attackerIsPlayer = true, incdmgamp = 0 } = h;
  let dmg = attack;
  if (Math.random() * 100 < critChance) dmg *= 2 + critDamage / 100; // crit
  dmg = Math.ceil(dmg * (0.9 + Math.random() * 0.2));               // +-10% roll
  const fort = attackerIsPlayer && targetFor ? damageMultiplier(targetFor * 5) : 1;
  dmg = Math.ceil(dmg * fort * damageMultiplier(targetDefense - pierce));
  if (incdmgamp) dmg = Math.round((dmg * (100 + incdmgamp)) / 100);  // cursed, marked
  return dmg;
}
```

```python
# damage_multiplier, js/old_common_functions.js:826. 100-point bands of defense each remove
# a little less damage per point; negative defense adds damage in 50-point bands.
import math
import random

POS_RATES = [0.001, 0.001, 0.00095, 0.0009, 0.00082, 0.0007, 0.0006, 0.0005]
NEG_RATES = [0.001, 0.00075, 0.0005]


def damage_multiplier(defense: float) -> float:
    reduction = sum(max(0, min(100, defense - 100 * i)) * r for i, r in enumerate(POS_RATES))
    reduction += max(0, defense - 800) * 0.0004  # above 800: 0.04% per point, no band
    bonus = sum(max(0, min(50, -defense - 50 * j)) * r for j, r in enumerate(NEG_RATES))
    bonus += max(0, -150 - defense) * 0.00025
    return min(1.32, max(0.05, 1 - reduction + bonus))  # clamped to [0.05, 1.32]


def hit_damage(attack: float, crit_chance: float = 0, crit_damage: float = 0,
               target_defense: float = 0, pierce: float = 0, target_for: float = 0,
               attacker_is_player: bool = True, incdmgamp: float = 0) -> int:
    """One physical or magical hit, following complete_attack (node/server.js:3707)."""
    dmg = attack
    if random.random() * 100 < crit_chance:
        dmg *= 2 + crit_damage / 100  # crit
    dmg = math.ceil(dmg * (0.9 + random.random() * 0.2))  # +-10% roll
    fort = damage_multiplier(target_for * 5) if attacker_is_player and target_for else 1
    dmg = math.ceil(dmg * fort * damage_multiplier(target_defense - pierce))
    if incdmgamp:
        # floor(x + 0.5) copies JS Math.round (Python's round() rounds halves to even).
        dmg = math.floor(dmg * (100 + incdmgamp) / 100 + 0.5)  # cursed, marked
    return dmg
```

```go
package combat

import (
	"math"
	"math/rand"
)

// damage_multiplier, js/old_common_functions.js:826. 100-point bands of defense each remove
// a little less damage per point; negative defense adds damage in 50-point bands.
var posRates = []float64{0.001, 0.001, 0.00095, 0.0009, 0.00082, 0.0007, 0.0006, 0.0005}
var negRates = []float64{0.001, 0.00075, 0.0005}

// band clamps x into [0, width]: the part of the defense that falls inside one band.
func band(x, width float64) float64 { return math.Max(0, math.Min(width, x)) }

func DamageMultiplier(defense float64) float64 {
	reduction := 0.0
	for i, r := range posRates {
		reduction += band(defense-100*float64(i), 100) * r
	}
	reduction += math.Max(0, defense-800) * 0.0004 // above 800: 0.04% per point, no band
	bonus := 0.0
	for j, r := range negRates {
		bonus += band(-defense-50*float64(j), 50) * r
	}
	bonus += math.Max(0, -150-defense) * 0.00025
	return math.Min(1.32, math.Max(0.05, 1-reduction+bonus)) // clamped to [0.05, 1.32]
}

// Hit is one physical or magical hit. Pierce is the piercing to subtract
// (see the double-count quirk); TargetFor only counts against player attackers.
type Hit struct {
	Attack, CritChance, CritDamage              float64
	TargetDefense, Pierce, TargetFor, IncDmgAmp float64
	AttackerIsPlayer                            bool
}

// HitDamage follows complete_attack (node/server.js:3707).
func HitDamage(h Hit) float64 {
	dmg := h.Attack
	if rand.Float64()*100 < h.CritChance {
		dmg *= 2 + h.CritDamage/100 // crit
	}
	dmg = math.Ceil(dmg * (0.9 + rand.Float64()*0.2)) // +-10% roll
	fort := 1.0
	if h.AttackerIsPlayer && h.TargetFor > 0 {
		fort = DamageMultiplier(h.TargetFor * 5)
	}
	dmg = math.Ceil(dmg * fort * DamageMultiplier(h.TargetDefense-h.Pierce))
	if h.IncDmgAmp != 0 {
		dmg = math.Round(dmg * (100 + h.IncDmgAmp) / 100) // cursed, marked
	}
	return dmg
}
```

```csharp
// damage_multiplier, js/old_common_functions.js:826. 100-point bands of defense each remove
// a little less damage per point; negative defense adds damage in 50-point bands.
public static class Combat
{
    static readonly double[] PosRates = { 0.001, 0.001, 0.00095, 0.0009, 0.00082, 0.0007, 0.0006, 0.0005 };
    static readonly double[] NegRates = { 0.001, 0.00075, 0.0005 };

    public static double DamageMultiplier(double defense)
    {
        double reduction = 0;
        for (int i = 0; i < PosRates.Length; i++)
            reduction += Math.Max(0, Math.Min(100, defense - 100 * i)) * PosRates[i];
        reduction += Math.Max(0, defense - 800) * 0.0004; // above 800: 0.04% per point, no band
        double bonus = 0;
        for (int j = 0; j < NegRates.Length; j++)
            bonus += Math.Max(0, Math.Min(50, -defense - 50 * j)) * NegRates[j];
        bonus += Math.Max(0, -150 - defense) * 0.00025;
        return Math.Min(1.32, Math.Max(0.05, 1 - reduction + bonus)); // clamped to [0.05, 1.32]
    }

    // One physical or magical hit, following complete_attack (node/server.js:3707).
    // pierce: piercing to subtract (see the double-count quirk).
    public static double HitDamage(double attack, double critChance = 0, double critDamage = 0,
        double targetDefense = 0, double pierce = 0, double targetFor = 0,
        bool attackerIsPlayer = true, double incdmgamp = 0)
    {
        var rng = Random.Shared;
        double dmg = attack;
        if (rng.NextDouble() * 100 < critChance) dmg *= 2 + critDamage / 100; // crit
        dmg = Math.Ceiling(dmg * (0.9 + rng.NextDouble() * 0.2));           // +-10% roll
        double fort = attackerIsPlayer && targetFor > 0 ? DamageMultiplier(targetFor * 5) : 1;
        dmg = Math.Ceiling(dmg * fort * DamageMultiplier(targetDefense - pierce));
        if (incdmgamp != 0)
            dmg = Math.Round(dmg * (100 + incdmgamp) / 100, MidpointRounding.AwayFromZero);
        return dmg;
    }
}
```

```rust
// damage_multiplier, js/old_common_functions.js:826. 100-point bands of defense each remove
// a little less damage per point; negative defense adds damage in 50-point bands.
// cargo add rand
const POS_RATES: [f64; 8] = [0.001, 0.001, 0.00095, 0.0009, 0.00082, 0.0007, 0.0006, 0.0005];
const NEG_RATES: [f64; 3] = [0.001, 0.00075, 0.0005];

pub fn damage_multiplier(defense: f64) -> f64 {
    let band = |x: f64, width: f64| x.min(width).max(0.0);
    let mut reduction: f64 = POS_RATES
        .iter()
        .enumerate()
        .map(|(i, r)| band(defense - 100.0 * i as f64, 100.0) * r)
        .sum();
    reduction += (defense - 800.0).max(0.0) * 0.0004; // above 800: 0.04% per point, no band
    let mut bonus: f64 = NEG_RATES
        .iter()
        .enumerate()
        .map(|(j, r)| band(-defense - 50.0 * j as f64, 50.0) * r)
        .sum();
    bonus += (-150.0 - defense).max(0.0) * 0.00025;
    (1.0 - reduction + bonus).max(0.05).min(1.32) // clamped to [0.05, 1.32]
}

/// One physical or magical hit, following complete_attack (node/server.js:3707).
pub struct Hit {
    pub attack: f64,
    pub crit_chance: f64,
    pub crit_damage: f64,
    pub target_defense: f64,
    pub pierce: f64, // piercing to subtract (see the double-count quirk)
    pub target_for: f64,
    pub attacker_is_player: bool,
    pub incdmgamp: f64,
}

pub fn hit_damage(h: &Hit) -> f64 {
    let mut dmg = h.attack;
    if rand::random::<f64>() * 100.0 < h.crit_chance {
        dmg *= 2.0 + h.crit_damage / 100.0; // crit
    }
    dmg = (dmg * (0.9 + rand::random::<f64>() * 0.2)).ceil(); // +-10% roll
    let fort = if h.attacker_is_player && h.target_for > 0.0 {
        damage_multiplier(h.target_for * 5.0)
    } else {
        1.0
    };
    dmg = (dmg * fort * damage_multiplier(h.target_defense - h.pierce)).ceil();
    if h.incdmgamp != 0.0 {
        dmg = (dmg * (100.0 + h.incdmgamp) / 100.0).round(); // cursed, marked
    }
    dmg
}
```

```java
// damage_multiplier, js/old_common_functions.js:826. 100-point bands of defense each remove
// a little less damage per point; negative defense adds damage in 50-point bands.
import java.util.concurrent.ThreadLocalRandom;

final class Combat {
    private static final double[] POS_RATES = {0.001, 0.001, 0.00095, 0.0009, 0.00082, 0.0007, 0.0006, 0.0005};
    private static final double[] NEG_RATES = {0.001, 0.00075, 0.0005};

    static double damageMultiplier(double defense) {
        double reduction = 0;
        for (int i = 0; i < POS_RATES.length; i++)
            reduction += Math.max(0, Math.min(100, defense - 100 * i)) * POS_RATES[i];
        reduction += Math.max(0, defense - 800) * 0.0004; // above 800: 0.04% per point, no band
        double bonus = 0;
        for (int j = 0; j < NEG_RATES.length; j++)
            bonus += Math.max(0, Math.min(50, -defense - 50 * j)) * NEG_RATES[j];
        bonus += Math.max(0, -150 - defense) * 0.00025;
        return Math.min(1.32, Math.max(0.05, 1 - reduction + bonus)); // clamped to [0.05, 1.32]
    }

    /** One physical or magical hit, following complete_attack (node/server.js:3707).
     *  pierce: piercing to subtract (see the double-count quirk). */
    static double hitDamage(double attack, double critChance, double critDamage, double targetDefense,
                            double pierce, double targetFor, boolean attackerIsPlayer, double incdmgamp) {
        var rng = ThreadLocalRandom.current();
        double dmg = attack;
        if (rng.nextDouble() * 100 < critChance) dmg *= 2 + critDamage / 100; // crit
        dmg = Math.ceil(dmg * (0.9 + rng.nextDouble() * 0.2));              // +-10% roll
        double fort = attackerIsPlayer && targetFor > 0 ? damageMultiplier(targetFor * 5) : 1;
        dmg = Math.ceil(dmg * fort * damageMultiplier(targetDefense - pierce));
        if (incdmgamp != 0) dmg = Math.round(dmg * (100 + incdmgamp) / 100); // cursed, marked
        return dmg;
    }
}
```

### Cooldowns, attack speed and mana

A **cooldown** is the minimum time between two uses of the same action. Each skill has one in `G.skills[name].cooldown`, in milliseconds. The cooldown of the normal attack is `attack_ms = round(1000 / frequency)`. The server copies it into `G.skills.attack.cooldown` on each [`skill`](#send-skill) call (node/server.js:9778).

Some skills **share** the cooldown of a different skill (the `share` field in G). 3-Shot, 5-Shot, Piercing Shot, Fan of Knives, Arcane Needle and the priest heal all use the cooldown of `attack`. Thus you select one of them for each attack. A skill that you use too early fails with [`cooldown`](#code-cooldown), which gives the remaining milliseconds. When your attack speed changes, the server sends [`skill_timeout`](#recv-skill_timeout) with the correct wait (node/server.js:1628-1635).

**Attack speed** (`frequency` in the data) comes from the class base, the level, dex and int. Gear and buffs add to it. A warrior at level 1 with no gear attacks every 1.96 s. A rogue at level 80 with no gear attacks every 0.82 s. Buffs such as Energize, War Cry or Merchant's Frenzy add speed for a few seconds.

**Mana.** Each normal attack and each heal costs `mp_cost` MP (see [All stats](#game-stats-and-combat)). Each skill costs its `mp` from G. Without MP, an attack fails with [`no_mp`](#code-no_mp). Mages and priests use MP the fastest. Thus MP potions and Energize are very important for them.

**Potions and regeneration.** The live server has no passive regeneration of HP or MP. HP and MP return only from these sources:

- potions;
- the free abilities `regen_hp` and `regen_mp`;
- heals, lifesteal and manasteal;
- a new level, which fills HP and MP (node/server.js:1314, 1649-1652).

All of them share one potion cooldown:

| Source | Gives | Locks potions for | How to use it |
|---|---|---|---|
| `regen_hp` (free) | 50 HP | 4 s | [`use`](#send-use) `{item: "hp"}` (node/server.js:11988-12021) |
| `regen_mp` (free) | 100 MP | 4 s | `use` `{item: "mp"}` |
| `hpot0`, `hpot1` | +200 HP, +400 HP | 2 s | [`equip`](#send-equip) with the inventory slot of the potion (node/server.js:7823-7875) |
| `mpot0`, `mpot1` | +300 MP, +500 MP | 2 s | the same |

A potion with its own `cooldown` in G locks for that time. A potion that you use too early fails with [`not_ready`](#code-not_ready). Poison halves the value of potions. [Healing with potions](#learn-acting-in-the-world) shows the code.

### Aggro, tanks and fear

**Aggro** is the decision of a monster to attack a character. In Adventure Land, each monster has one `target` (the name of a player) at a time. These rules come from [`G.monsters`](#g-monsters) and the server:

- **Passive monsters** (`aggro: 0`) never start a fight. Goos and snakes are passive.
- **Aggressive monsters** make a check every 1.2 s, or every `1200/frequency` ms if that is longer (node/server.js:13943-13947). With the chance `aggro`, they become ready to attack. Above 0.99 the chance is 100% (node/server.js:14308-14319).
- A ready monster attacks a near player that is in front of it and in its range. With the chance `rage`, it also locks on that player and follows it (node/server.js:15170-15180).
- **A hit** makes a monster with no target select its attacker as the target. Monsters with `passive: true` are the exception (node/server.js:4390-4398).
- **Loss of interest**: if nobody attacks a monster for 20 s, it can stop. The chance on each check is `1 − rage × 0.99` ("bored", node/server.js:14397-14399). Monsters with a high `rage` follow you for a long time.
- A monster that follows a target moves at its `charge` speed, not at its `speed` (node/server.js:1792-1794).

**Tanking** is control of the monster targets. The warrior skills Taunt and Agitate, and the priest skill Absorb Sins, move the targets to one character. Thus the weak characters do not get hits. The main job of a tank bot is simple: if a monster targets a different party member, taunt the monster. The item stats `bling` and `cuteness` also change the chance that aggressive monsters attack you (`aggro_diff`, node/server.js:1610, 15175-15178).

**Fear.** The server counts the physical, magical and pure monsters that target each player (`targets_p`, `targets_m`, `targets_u`, node/server.js:13769-13820). When a count is more than the related courage stat, the player is afraid (node/server.js:1727-1751). The `fear` level is the largest difference:

| Fear | Speed | Attack |
|---|---|---|
| 1 | −20 | × 0.6 |
| 2 | −40 | × 0.4 |
| 3 | −70 | × 0.2 |
| 4, 5, 6+ | −80, −90, −100 | × 0.2 |

The base courage is small. The warrior has 5 courage, the priest has 5 magical courage, and the paladin has 5 pure courage. Most other values are 2, and the merchant has 1, 0 and 0 (`G.classes`). Thus a weak class with three monsters on it fights at a small part of its strength. This mechanic is the reason for tanks.

**Mobs.** A target with more than 3 monsters on it also gets a combo multiplier on each hit (node/server.js:3856-3920). The multiplier increases from 1.6 to 2, and above 10 hits it is `combo/4`. Its maximum is `max(300/attack, 1.2)`. Because of this maximum, a crowd of weak monsters does much more damage than their attack values show.

**Stacked characters.** Some of your characters, or of your party, can stand in the same 6×6 px cell (node/server_functions.js:1292-1299). Then one monster hit can touch all of them (node/server.js:3866-3911). Keep your characters a few pixels apart.

### Conditions

A **condition** is a timed effect on an entity: a **buff** (good) or a **debuff** (bad). The server stores it as `s[name] = {ms, ...}`. [`G.conditions`](#g-conditions) defines 89 conditions in G 17478. The server adds the stat fields of a condition like gear.

A priest or a paladin can remove a `cleansable` condition. Some conditions name a `defense` stat. Then the target resists the condition with the chance `defense/100` (`add_condition`, node/server_functions.js:3235-3249). These are the conditions that a bot sees most:

| Condition | Effect | Usual source |
|---|---|---|
| `stunned` | No movement, attacks or skills for 3.2 s (2 s from a gear proc). `phresistance` resists it | Stomp, the `stun` stat on gear |
| `frozen` | −40 speed, attack speed × 0.3, 5 s | Frost weapons, frostball, snowballs |
| `burned` | Damage over time, about the damage of the first hit each second | Fire weapons, fireball |
| `poisoned` | Attack speed × 0.9, potions × 0.5, heals × 0.25, 5 s | Poison Arrow, poisonous monsters |
| `cursed` | Output −20%, 20% more damage taken, −20 speed, 5 s | Priest Curse |
| `marked` | 10% more damage taken, no stealth, 10 s | Ranger Hunter's Mark |
| `weakness` | −30 speed, −10 str, −10 dex, 20 s | The weakness aura of some monsters |
| `tangled` | Maximum speed 24 | Entangle, tangle |
| `stoned`, `deepfreezed`, `fingered` | Like a stun | Some monsters and skills |
| `mluck`, `rspeed` | +12 luck for 1 hour; +7 speed and +0.08 attacks/s for 45 min | Merchant's Luck, Rogue Swiftness |
| `warcry`, `darkblessing`, `energized`, `beacon_of_resolve` | Combat buffs for the party | Warrior, priest, mage, paladin |
| `invincible` | No damage for 6 s after a respawn in a PvP area (node/server_functions.js:1032-1036) | Respawn |
| `block` | PvP block: after PvP, a safe exit is not possible for some time | An attack from a player |
| `hopsickness`, `realmfatigue` | Less luck, gold, xp and output; no home bonuses | A server change ([Servers, regions and PvP](#game-what-adventure-land-is)) |
| `authfail` | −85% luck, −85% gold, −20% xp | No platform link ([Accounts and characters](#game-what-adventure-land-is)) |

### Death and respawn

When the HP of a character becomes 0, the server calls `defeated_by_a_monster` (node/server.js:13884) or the PvP version of it. These things happen:

- **Xp loss.** The character loses the larger of 1% of the xp for its level and 2% of its current xp. The loss is never more than the current xp. In PvP areas, the server divides the loss by 10 (node/server.js:13890-13894). A character never loses a level, except on HARDCORE.
- **Tome of Protection.** A Tome of Protection (`xptome`) in the bag decreases the loss to 1/50. The server then removes the tome (node/server.js:13896-13906). The client gets [`defeated_by_a_monster`](#code-defeated_by_a_monster) with the xp loss.
- **The monster can gain a level.** This happens if the xp loss is large compared to the HP of the monster (node/server.js:13920-13936). Thus each new death to the same monster makes it stronger.
- **Gravestone.** The character stays dead (`rip: true`) for a minimum of 12 s (`B.rip_time`, node/server.js:224). A priest can revive it during that time.
- **Respawn.** After that time, send [`respawn`](#send-respawn). It moves the character to the `on_death` point of the map, usually the Mainland town. With `{safe: true}`, it moves the character to the Wizard's Crib (`woffice`). The character gets full HP and half MP (node/server.js:6271-6309). A respawn that is too early fails with [`cant_respawn`](#code-cant_respawn), with the remaining `ms`.
- **PvP deaths** can cost PvP-marked items ([Servers, regions and PvP](#game-what-adventure-land-is)).

Your own death arrives in your `player` data as `rip: true`. The [`death`](#recv-death) event is for monsters that die near you. [Dying and respawning](#learn-acting-in-the-world) shows the code.

## Leveling and progression

Characters get experience points (**xp**) when they kill monsters. Enough xp gives a new **level**, which increases the stats and makes new skills available.

### The xp curve

[`G.levels`](#g-levels)`[N]` is the xp that a character needs to go from level N to level N+1, for N = 1 to 200. The server keeps the xp toward the next level, not a total. It adds a level while `xp >= G.levels[level]` (node/server.js:1305-1316).

Each level costs about 22% more than the level before it. Thus the cost doubles about every 3.5 levels.

| Level | Xp for this level | Total xp to get this level |
|---|---|---|
| 1 | 200 | 0 |
| 10 | 1,300 | 4,910 |
| 20 | 11,000 | 45,910 |
| 30 | 90,000 | 376,910 |
| 40 | 720,000 | 3.06 million |
| 50 | 5.8 million | 24.8 million |
| 60 | 47 million | 201 million |
| 70 | 290 million | 1.43 billion |
| 80 | 1.6 billion | 8.87 billion |
| 90 | 15 billion | 63.0 billion |
| 100 | 300 billion | 873 billion |

The data comes from `G.levels` (G 17478). The table continues to level 200. But after level 90, a level needs much more xp than normal farming gives. Level 80 is a goal for a long time.

At level 70 and higher, the server tells all players on the server about each new level. At level 80 and higher, it tells all servers (node/server.js:1324-1343). G also has achievements that give items at levels 40 to 70 (`reach40` to `reach70`).

### Xp from a kill

A monster gives `G.monsters[type].xp` at level 1. For each level that the monster gains, it gives that quantity again. The killer gets:

```
xp = monster.xp × your xpm × monster.mult              (solo, node/server.js:2813)
xp = round(monster.xp × your xpm × your share) × monster.mult   (party, node/server.js:2835, 2847)
```

- `xpm` is `1 + xp%/100`. The xp% is the total of gear, conditions, the party bonus and server bonuses (node/server.js:1675-1697). Examples of conditions are xp boosters, holiday buffs and `newcomersblessing`.
- `monster.mult` is usually 1. A server stop changes it for each monster in a fight. The monster stays at 1 HP, and `mult` becomes the part of its HP that the attackers removed (node/server.js:16942-16951).
- The live code has **no penalty for level differences**. A character at level 80 gets the same xp from a goo as a character at level 1. For the level-80 character, it is only a very small part of a level.
- Merchants get no xp from kills.

**Party xp.** Each party member on the server gets a share of each kill. The share comes from the contribution score (`pdps`) of the character, divided by the total of the party (`party_to_client`, node/server.js:1138-1190). The contribution score contains:

- the damage that the character does;
- its healing, × 1.8;
- a quarter of the damage that it takes as a tank.

The server adds a fixed 36,000 to the score of each non-merchant member, and multiplies the score of a priest by 1.36. Characters of the same account get the average of their scores. The fixed value makes sure that support characters also get xp.

The party also gives each member an xp bonus for its size (node/server.js:1186-1188). The bonus is 10% for 2 non-merchant members and 40% for 9 or more. The party gives +5% gold. Each member below level 60 adds +10% luck for the party.

**World bosses and other `cooperative` monsters** use different rules (`issue_monster_awards`, node/server.js:2717-2776). Each contributor gets xp and a drop roll if its share is more than 0.25%. The share is `points^0.65` divided by the total. The size of the share sets the size of the reward. The last hit is not necessary. A character on its home server gets 5 × the points, and a character with Hop Sickness gets 1/4 (node/server.js:13308-13314).

### Bonuses for new and solo players

The live game adds three "encouragement" conditions (node/logic/encouragement.js:214-286). They multiply gold, xp and luck. If more than one applies, the server uses the product of them.

| Condition | When | Gold / xp / luck |
|---|---|---|
| New Player (`encouragement_new`) | The first 40 days after your first character. The xp part stops at level 80 | Days 1-10: 5 / 5 / 5. Days 11-20: 2 / 4 / 4. Days 21-30: 2 / 2 / 3. Days 31-40: 1.5 / 1.5 / 1.5 |
| Lone Wolf (`encouragement_lonewolf`) | Only one non-merchant character of your account is online, on all servers | 3 / 3 / 3 |
| Welcome Back (`encouragement_returning`) | You come back after more than 60 days away. It lasts half of the time that you were away, to a maximum of 90 days | 3 / 3 / 3 below level 80, 2 / 2 / 2 from level 80 |

The server does not multiply the base reward directly. It records the contribution of each character to each monster: damage, healing × 1.8 and a quarter of the damage taken. Then it pays the extra gold, xp and luck in proportion to that contribution (`encouragement_points`, `encouragement_xp`, node/logic/encouragement.js:333-407). For a monster that you kill alone, the result is close to the full multiplier.

> **Caution:** The `authfail` condition stops all three bonuses (node/logic/encouragement.js:218-219). Link a platform id first ([Accounts and characters](#game-what-adventure-land-is)).

### Monsters gain levels too

A monster with no target gains a level after a time of `max(3 min, max_hp × 30 ms)`. This time increases by × 2^0.3 for each level that the monster already has. The server checks every 16 s (node/server.js:16388-16420). Cute, peaceful and stationary monsters do not gain levels this way. When a monster selects a target, its timer starts again (node/server.js:4489).

Each new level gives the monster (`level_monster`, node/server.js:13319-13348; `calculate_monster_stats`, node/server.js:1813-1826):

- its base xp again;
- half of its base HP;
- 12.5% more attack, for a maximum of 12 levels. Spawn areas with `grow: true` give only 5%, and most Mainland areas have it;
- more attack speed and more movement speed;
- +0.25 to its `luckx`, a luck bonus for its drops.

The level of a monster also multiplies its gold (node/server.js:2396-2399). Thus monsters in an area that nobody farms can be much stronger than G says. They also give more xp and gold. The [`entities`](#recv-entities) event gives the real `level`, `hp` and `max_hp` of each monster. Use these values, not the values in G.

### Where to level: a derived table

The game has no official list of areas per level. We made the table below for this guide from `G.monsters` and the spawn lists in `G.maps` (G 17478). It is a start, not a rule. [Your first day](#game-what-adventure-land-is) gives the rule to change the monster.

The table sorts monsters into groups by their damage per second without armor (`attack × frequency`). Inside a group, it sorts them by HP. Armor decreases physical damage much ([The defense curve](#game-stats-and-combat)). Real monsters can also have more levels than G shows.

| Group | Monster (key) | Map | HP | Xp | Dmg/s | Type | Armor / Res | Aggro |
|---|---|---|---|---|---|---|---|---|
| Start | Goo (`goo`) | main | 100 | 100 | 2 | phys | 0 / 0 | 0 |
| Start | Bee (`bee`) | main | 300 | 400 | 8 | phys | 0 / 0 | 1 |
| Start | Tiny Crab (`crab`) | main | 400 | 500 | 10 | phys | 160 / 0 | 0.2 |
| Start | Snake (`snake`) | main, halloween | 720 | 960 | 14 | phys | 0 / 0 | 0 |
| Start | Rat (`rat`) | mansion | 820 | 640 | 40 | phys | 0 / 0 | 1 |
| Start | Squig (`squig`) | main | 1,000 | 600 | 4 | phys | 0 / 0 | 0 |
| Start | Armadillo (`armadillo`) | main | 1,600 | 1,720 | 10 | phys | 60 / 0 | 0 |
| Start | Arctic Bee (`arcticbee`) | winterland | 1,600 | 1,800 | 38 | phys | 0 / 0 | 1 |
| Start | Croc (`croc`) | main | 3,200 | 3,600 | 24 | phys | 40 / 0 | 0.2 |
| Start | Porcupine (`porcupine`) | desertland | 3,800 | 3,200 | 8 | phys | 120 / 0 | 1 |
| Start | Huge Crab (`crabx`) | main | 4,200 | 3,600 | 72 | phys | 210 / 0 | 0.5 |
| Start | Tortoise (`tortoise`) | main | 7,200 | 5,200 | 18 | phys | 200 / 0 | 0 |
| Start | Bat (`bat`) | cave | 9,600 | 8,000 | 35 | phys | 0 / 120 | 0.3 |
| Start | Spider (`spider`) | main | 18,000 | 12,000 | 80 | phys | 0 / 0 | 0.3 |
| Start | Scorpion (`scorpion`) | main | 24,000 | 20,000 | 80 | phys | 200 / 0 | 0.3 |
| Start | Scorpion (`gscorpion`) | desertland | 32,000 | 48,000 | 96 | phys | 300 / 0 | 0.3 |
| Mid | Pom Pom (`minimush`) | halloween | 500 | 600 | 120 | magic | 0 / 120 | 0.05 |
| Mid | Water Spirit (`iceroamer`) | winterland | 3,600 | 4,200 | 84 | magic | 0 / 0 | 0.2 |
| Mid | Poisio (`poisio`) | main | 3,600 | 4,000 | 144 | phys | 0 / 0 | 1 |
| Mid | Pom Pom (`bbpompom`) | winter_cave, level3 | 6,400 | 6,000 | 192 | magic | 0 / 160 | 0.2 |
| Mid | Wild Boar (`boar`) | winterland | 12,000 | 10,800 | 168 | phys | 100 / 0 | 1 |
| Mid | Ghost (`ghost`) | halloween | 12,000 | 16,000 | 200 | magic | 0 / 400 | 0.05 |
| Mid | Stone Worm (`stoneworm`) | spookytown | 2,200 | 2,400 | 216 | phys | 0 / 0 | 1 |
| Mid | Dark Hound (`wolfie`) | winterland | 19,200 | 16,400 | 256 | phys | 200 / 100 | 1 |
| Mid | Boo Boo (`booboo`) | spookytown | 8,000 | 12,000 | 264 | pure | 0 / 0 | 1.5 |
| Upper | Irradiated Goo (`cgoo`) | level2s, level4, arena | 2,400 | 4,800 | 384 | phys | 0 / 260 | 0.1 |
| Upper | Mole (`mole`) | tunnel | 12,400 | 8,000 | 384 | phys | 0 / 0 | 1 |
| Upper | Hawk (`bigbird`) | main | 32,000 | 30,000 | 384 | phys | 0 / 0 | 1 |
| Upper | White Wolf (`wolf`) | winterland | 48,000 | 48,800 | 384 | phys | 300 / 200 | 1 |
| Upper | Fire Spirit (`fireroamer`) | desertland | 84,000 | 64,200 | 384 | magic | 120 / 320 | 0.2 |
| Upper | Dryad (`dryad`) | mforest | 80,000 | 60,000 | 400 | magic | 65 / 100 | 0.1 |
| Upper | Dino (`odino`) | mforest | 165,000 | 140,000 | 495 | phys | 135 / 65 | 0.2 |
| Upper | Vampire Rat (`prat`) | level1 | 9,200 | 7,600 | 512 | phys | 160 / 0 | 1 |
| Upper | Mummy (`mummy`) | spookytown, level3, level4 | 12,000 | 16,000 | 504 | phys | 0 / 0 | 1.5 |
| Upper | Scorpion (`xscorpion`) | halloween | 140,000 | 172,000 | 576 | phys | 400 / 0 | 0.3 |
| Upper | Sprawling (`plantoid`) | desertland | 120,000 | 96,000 | 768 | phys | 160 / 190 | 0.2 |
| Late | Pink Goblin (`pinkgoblin`) | level2e | 420,000 | 460,000 | 960 | magic | 200 / 350 | 0 |
| Late | Spark Bot (`sparkbot`) | uhills | 325,000 | 400,000 | 1,176 | magic | 140 / 160 | 0.1 |
| Late | Targetron (`targetron`) | uhills | 325,000 | 400,000 | 1,176 | phys | 160 / 140 | 0.1 |
| Late | Pom Pom (`pppompom`) | level2n | 64,000 | 62,400 | 1,214 | phys | 0 / 480 | 0.2 |
| Late | Harpy (`harpy`) | winter_cove | 160,000 | 192,000 | 1,376 | magic | 160 / 600 | 0.01 |
| Late | One Eye (`oneeye`) | level2w | 420,000 | 582,000 | 1,440 | phys | 160 / 160 | 1 |
| Late | Kobold (`kobold`) | ucliffs | 640,000 | 680,000 | 1,680 | phys | 320 / 220 | 0.6 |
| Late | Black Scorpion (`bscorpion`) | desertland | 576,900 | 634,800 | 1,920 | phys | 500 / 240 | 0.8 |
| Endgame | Ent (`ent`) | desertland | 8,000,000 | 9,200,000 | 4,320 | phys | 100 / 100 | 0.2 |
| Endgame | Bosses of the Crypt, the Tomb, the Spider Den and the Dark Mage | instances (keys) | 0.2M - 18.7M | to 32M | to 10,640 | mixed | | |
| Endgame | World bosses (`franky`, `icegolem`, `crabxx`, seasonal) | different maps | 1M - 120M | to 200M | | | | |

The groups use the damage per second without armor: Start below 100, Mid 100-300, Upper 300-800, Late above 800. The table does not include rare monsters with long `respawn` times: Froggie, Squigtoad, Dracul, Skeletor, Stompy and the fairies. It also does not include special monsters.

One observation comes from the bot of the owner of this guide, not from the source. At level 46, its party found Irradiated Goo not safe, with about 340 damage per second after armor. At the same level, the snowman, wabbit, big goo, grinch and phoenix were safe.

A good farm has these qualities, in approximate order of importance:

1. It cannot kill you. The incoming damage per second is less than your heals and potions give back.
2. It dies quickly. It has low HP and low defense against your damage type.
3. It gives much xp per HP.
4. It respawns quickly.
5. There are enough monsters, so your characters never wait.

Monsters with **aggro 1** come to you. Monsters with **aggro 0** only fight back.

### Skills by level

The server compares your level with `G.skills[name].level`. Below that level, a skill fails with [`no_level`](#code-no_level). Skills with no level are available at level 1. This table shows each level requirement in G 17478:

| Level | Warrior | Paladin | Rogue | Ranger | Mage | Priest | Merchant |
|---|---|---|---|---|---|---|---|
| 10 | | Smash | | | | | |
| 16 | | | Pickpocket | | | | Fishing, Mining |
| 20 | | | | | Energize | | |
| 30 | | Cleansing Light | | | | | Mass Production |
| 40 | | | Rogue Swiftness | | Alchemy | | Merchant's Luck, Mass Exchange |
| 50 | | Guardian's Oath | | | | | |
| 52 | Cleave, Stomp | | | | | | |
| 55 | | | | | | Absorb Sins | |
| 60 | Hard Shell | Purify, Shield Slam, Paladin Aura, Aether Shield | | 3-Shot | Reflective Shield | | Mass Production++, Throw Stuff |
| 64 | | | | 4 Finger Technique | | Phase Out | |
| 65 | | | Fan of Knives | | | | |
| 68 | Agitate | | | | | | |
| 70 | War Cry | Beacon of Resolve | Shadow Strike | | | Dark Blessing | Merchant's Courage, Mass Exchange++ |
| 72 | | | | Piercing Shot | Entangle | | |
| 75 | | | | 5-Shot | Controlled Mana Burst | | |
| 85 | | | | | | | Merchant's Frenzy |
| 90 | | | | | Arcane Needle | | |

The check is in the skill handler (node/server.js:9849-9851). [Classes](#game-classes) describes each skill.

### Gear is more important than level

After the first few dozen levels, gear sets the limit of a character more than level does. A level gives a few attribute points. A better weapon or a +2 on your armor can give more. Thus progress is a loop: farm gold and items, then change them into better gear.

**Upgrades** improve gear. You combine an item with a scroll at the upgrade NPC. If the upgrade succeeds, the level of the item increases by one (+1, +2 and so on). Each level adds the `upgrade` values of the item to its stats.

An upgrade is an **RNG** gamble. RNG (random number generator) means that a random roll decides the result. The chance of success decreases with each level.

> **Caution:** A failed upgrade destroys the item. Upgrade a spare item, not the item that a character wears.

These are the base chances from [`G.upgrades`](#g-upgrades-compounds) for a normal item:

| To | +1 | +2 | +3 | +4 | +5 | +6 | +7 | +8 | +9 | +10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Chance | ~100% | 98% | 95% | 70% | 60% | 40% | 25% | 15% | 7% | 2.4% |

Scrolls of a higher grade (`scroll1`, `scroll2`), offerings and "grace" increase these chances. The grade of the item sets the scroll that you need. The [`upgrade`](#send-upgrade) entry gives the details. Accessories (rings, earrings, amulets) **compound** in place of an upgrade. Three identical items and a compound scroll make one item of the next level, with the same risk ([`compound`](#send-compound)).

The cost of an item at a high level increases very quickly. Each failure destroys all the gold and items in that item. Thus a bot needs a rule for the risk at each level, and a rule for when to stop. For example, the bot of the owner upgrades only when the chance is 90% or more (+3 on basic gear). It compounds only at 70% or more.

**Gear score.** Many MMOs add the values of all the gear of a character into one number: the "gear score". It tells how strong the character is. Adventure Land has no such number in G or in the server source. A bot that needs one must make its own. For example, it can calculate the damage per second that it does and gets against one monster, with the formulas of [Stats and combat](#game-stats-and-combat).

## Maps and the world

The world has 54 maps in [`G.maps`](#g-maps) (G 17478), and 49 of them are in use. Mainland is the hub. Doors, the transporter and instance keys connect it to all other places.

Five maps have `ignore: true`. The server and the client do not use them.

### Travel

- **Walk** with [`move`](#send-move) inside a map. [`G.geometry`](#g-geometry) holds the walls as line segments. The server refuses moves through a wall. Thus a bot needs its own pathfinding.
- **Doors** connect maps. Each door is a rectangle in `G.maps[map].doors`. Go to 112 px or less from it (`B.door_dist`, node/server.js:221). Then send [`transport`](#send-transport) with its destination.
- **The transporter** (the NPC Alia) teleports characters between towns. `G.npcs.transporter.places` lists `main`, `winterland`, `desertland` and `cyberland`, and also `test` and `d_e`. You must be 160 px or less from her (`B.transporter_dist`, node/server.js:223).
- **Town**: [`town`](#send-town) takes 3 s. Then it moves you to the main spawn point of your current map. It fails with [`cant_escape`](#code-cant_escape) if more than 5 monsters target you (node/server.js:6254-6267).
- **Instances** are private copies of a map for your group. Most need a key item and the [`enter`](#send-enter) event (see "Dangerous and special areas" below).
- **Magiport and Blink** are mage skills that move characters with no walk.

### The main maps

| Map (key) | Contents | Connections |
|---|---|---|
| Mainland (`main`) | The hub. The town at the center has almost all shops and services. Monsters for beginners all around. Mainland bosses: Giga Crab, Phoenix, Hawk | arena, bank, cave, gateway, halloween, hut, level1, mansion, mtunnel, tavern, tunnel, woffice |
| The Bank (`bank`, `bank_b`, `bank_u`) | Safe maps with the item storage of your account. The lower floors are locked for each account | main; level2 from the lowest floor |
| Wizard's Crib (`woffice`) | Safe. Lost and Found, the Wizard, the cavalry NPCs | main |
| The Tavern (`tavern`) | Bar, poker, dice and other games | main, resort_e |
| Mining Tunnel (`tunnel`) | Moles. The gem merchant | main |
| Cave of Darkness (`cave`) | Bats, Dracul. The door to the Crypt | main, level1, crypt |
| The Mansion (`mansion`) | Rats. The quest NPC Wynifreed. The door to the Tomb | main, tomb |
| Spooky Forest (`halloween`) | Snakes, ghosts, scorpions, Ms. Dracul, Mr. Pumpkin (Halloween) | main, level1, spookytown, mforest |
| Spooky Town (`spookytown`) | Mummies, Boo Boos, Stone Worms, Mr. Green | halloween, level2 |
| Mystical Forest (`mforest`) | Dryads, Dinos, fairies | halloween |
| Winterland (`winterland`) | The second town: transporter, leather quest. Bees, boars, wolves, Ice Golem, Stompy | level2n, winter_cave, winter_inn, winter_instance |
| Frozen Cave, Frozen Cove (`winter_cave`, `winter_cove`) | Pom Poms. Harpies, Rime Djinn | winterland |
| Desertland (`desertland`) | The third town: transporter, locksmith, scrollsmith. Scorpions, plants, Fire Spirits, Ent | level2s |
| Underground (`level1` to `level4`, `level2n/e/s/w`) | A network of tunnels with strong monsters: Vampire Rats, Irradiated Goo, Pink Goblins, One Eye, Franky | main, cave, halloween, spookytown, bank_u, winterland, desertland |
| Gateway (`gateway`) | An Underground hub to the cliffs, the hills and the Spider Den | main, ucliffs, uhills, spider_instance |
| Cyberland (`cyberland`) | Mech-a Gnomes | main (transporter) |
| Arena (`arena`) | A PvP map with Irradiated Goo and Skeletor | main |

`G.maps[map].monsters` has the full spawn lists. The table in [Where to level](#game-leveling-and-progression) shows where each monster lives.

### Dangerous and special areas

> **Caution:** On PvP maps, other players can kill your characters. On a PvP server, they can also take your PvP-marked items.

| Type | Maps | Notes |
|---|---|---|
| **PvP maps** (on all servers) | `arena`, `abtesting`, `dungeon0`, `cgallery`, `duelland` | Other players can kill you. The xp loss for a death is 1/10 of the normal loss. |
| **Safe maps** | `bank`, `bank_b`, `bank_u`, `d_e`, `hut`, `woffice` | No hostile attacks or skills ([`skill_cant_safe`](#code-skill_cant_safe)). |
| **Key dungeons** (instances) | Crypt (`cryptkey`), Tomb (`tombkey`), Lair of the Dark Mage (`frozenkey`), Spider Den (`spiderkey`) | Enter with the key in your bag. Most bosses inside have `respawn: -1`: they do not respawn, so a dead boss stays dead. The base value of each key is 50,000 gold. |
| **Event maps** | `goobrawl`, `abtesting`, `ship0` | Open during scheduled events ([S](#s-event-lifecycle)). |
| **The Underground** | `level1` to `level4`, `level2n/e/s/w` | Mostly aggressive monsters with high damage, near the doors. Do not walk through without preparation. |
| **Jail** | `jail` | The server puts characters there when they break the rules. |

**Night.** Night is from 00:00 to 05:59 in the local time of the server (`E.schedule.night`, node/server_functions.js:2378-2383). At night, monsters move at 70% of their speed (node/server.js:1828-1830). Some monsters also sleep.

**Events.** Daily events start at 13:00 and 20:00 in the local time of the server. Nightly events start at 23:00 ([`schedule`](#s-key-schedule), node/server.js:204-209). While a world boss is alive, S shows it with its map and position. Examples are [Franky](#s-key-franky), the [Ice Golem](#s-key-icegolem) and the [Giga Crab](#s-key-crabxx). Thus a bot can walk to it.

### NPCs and their services

[`G.npcs`](#g-npcs) defines the NPCs. `G.maps[map].npcs` gives their positions. To use most shops and services, you must be 400 px or less from the NPC (`B.sell_dist`, node/server.js:220). The coordinates below are Mainland pixels, except where the table names a different map.

| NPC | Position | Role | Use |
|---|---|---|---|
| Ernis (`fancypots`) | main (−35, −162); also halloween. Warin in winter_inn | Potions | `hpot0` and `mpot0` (+200 HP, +300 MP), `hpot1` and `mpot1` (+400, +500), with [`buy`](#send-buy) |
| Gabriel (`basics`) | main (−89, −165) | Basic gear | Helmet, coat, pants, shoes, gloves, blade, claw, staff, bow, wand, mace, wooden shield, basher, axe, reed scythe |
| Lucas (`scrolls`) | main (−464, −96) | Scrolls | Upgrade scrolls `scroll0`, `scroll1`, `scroll2`; compound scrolls `cscroll0`, `cscroll1`, `cscroll2`; stat scrolls |
| Cue (`newupgrade`) | main (−207, −220) | Upgrades | The place for [`upgrade`](#send-upgrade) and [`compound`](#send-compound) |
| Xyn (`exchange`) | main (−25, −478) | Exchange | Changes boxes, gems, candy and other exchange items into a random reward ([`exchange`](#send-exchange)) |
| Alia (`transporter`) | main (−83, −441); also winterland, desertland, halloween | Teleports | Travel between towns ([`transport`](#send-transport)) |
| Ponty (`secondhands`) | main (106, −47) | Secondhands | Sells again the items that players sold to NPCs, at 2 × their value ([`secondhands`](#send-secondhands), [`sbuy`](#send-sbuy)) |
| Ron (`lostandfound`) | woffice | Lost and Found | Lost items at 4 × their value. Takes gold gifts, which give merchants xp ([`lostandfound`](#send-lostandfound), [`donate`](#send-donate)) |
| Daisy (`monsterhunter`) | main (126, −413) | Monster hunts | Gives a quest to kill a number of one monster. The reward is monster tokens ([`monsterhunt`](#send-monsterhunt)) |
| Leo (`craftsman`) | main (92, 670) | Crafting | Combines items by the `G.craft` recipes ([`craft`](#send-craft)) |
| Divian (`standmerchant`) | main (−193, 680) | Stands | Sells the merchant stand (`stand0`) |
| Garwyn (`premium`) | main (192, −564) | Premium | Xp, gold and luck boosters, the Tome of Protection, offerings |
| Mr. Rich (`goldnpc`), tellers (`items0` and more) | bank | Bank | Storage for gold and items ([`bank`](#send-bank)) |
| Smith (`locksmith`) | desertland (316, −270) | Locks | Locks or seals items, so you cannot sell or upgrade them by mistake ([`locksmith`](#send-locksmith)) |
| Sir Bob (`scrollsmith`) | desertland (606, −1590) | Stat removal | Removes a stat scroll from an item and returns the scrolls, for gold ([`destat`](#send-destat)) |
| Crun (`thief`) | level2 | Shop | Higher scrolls (`scroll3`, `cscroll3`), Licence to Kill, soft-step gloves |
| Mine Heathcliff (`gemmerchant`) | tunnel | Quest | Takes gem fragments |
| Tristian (`fisherman`) | main (−1572, 552) | Quest | Takes seashells |
| Landon (`leathermerchant`) | winterland | Quest | Takes leather |
| Wynifreed (`pwincess`) | mansion | Quest | Takes the lost earring |
| Witch | halloween | Quest, crafting | Halloween exchanges |
| Token NPCs: Fvona, Tricksy, Gn. Spence | main | Token shops | Sell items for friend, fun and PvP tokens (`G.tokens`) |
| Haila (`appearance`), Pete, Rose, Ace | main | Other | Cosmetics, pets, lottery, PvP announcements |

Quest NPCs use the same [`exchange`](#send-exchange) event as Xyn. You give the item that the `quest` field of the NPC names. Then you get a roll on its drop table ([`G.drops`](#g-drops)).

### Where to find things

| Need | Place |
|---|---|
| Potions | Ernis, near the center of the Mainland town. Warin in the Winterland inn |
| Basic gear | Gabriel, near Ernis |
| Upgrade and compound scrolls | Lucas, west of the town. Crun in the Underground for the highest scrolls |
| An upgrade or a compound | Cue, north-west of the town center |
| A sale of loot | Any merchant NPC pays 60% of the item value (`G.multipliers.buy_to_sell`). Your merchant stand can get more |
| Storage | The Bank, north of the town center |
| Travel to a different town | Alia, the transporter, or the doors |
| An item that you sold by mistake | Ponty first, then Ron in the Wizard's Crib |
| A boss | [S](#s-what-s-is): the live list, with map and position |
