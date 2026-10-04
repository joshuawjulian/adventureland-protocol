# Part 2: Items, economy and events

## Items and equipment

An **item** is almost anything that a character owns: weapons, armor, potions, scrolls, materials, tokens, and the merchant stand. This chapter tells what an item is, where your character wears it, and how you find it in the data that the server sends.

All numbers on this page come from the live game data **G version 17478** and from the live server code (`node/server.js`, `node/server_functions.js`, `js/old_common_functions.js`). A game update can change them. The citations link to the exact line. [Getting the game data](#learn-getting-the-game-data) shows how to download G.

### What a new character has

A new character starts with these items (`api.js:538-555`, `G.classes[class].base_slots`):

| Where | Items |
|---|---|
| Equipped | The weapon of its class at +0: a Blade (warrior), a Mace (paladin), a Claw (rogue), a Bow (ranger), a Staff (mage, priest, merchant). Also a Helmet and Shoes |
| Inventory | 200 small HP potions (`hpot0`) and 200 small MP potions (`mpot0`) |
| Mail, one time for each account | A Tracktrix (`tracker`), from Daisy. Take it with [`mail_take_item`](#send-mail_take_item) (`adventure_functions.js:1019`, sent at `node/server.js:11945`) |

All starter items have `gift: 1`. An NPC pays only 1 gold for a gift item. Thus do not sell them. Wear them, or upgrade them (next chapter).

### Where your items are in the data

The server sends your items in the [`start`](#recv-start) event and in each [`player`](#recv-player) update. [Reading the world](#learn-reading-the-world) shows how to keep them in your `me` object.

- `me.items` is an array with one entry for each inventory slot. The index of the array is the **slot number**. Most item events take this number (`num`, `item_num`). An empty slot is `null`.
- `me.slots` is an object with one key for each equipment slot (`mainhand`, `helmet`, ...). An empty slot is `null`.
- Each entry is an item **instance** (next section).

### Definition and instance

An item has two parts. A client needs both parts.

- The **definition** is in G, in `G.items[name]`. G 17478 has 638 item definitions. A definition holds the data that is the same for all copies: name, `type`, base price `g`, base stats, and the stat increase per level. See [items](#g-items) for all fields.
- The **instance** is the small object in an inventory slot or an equipment slot. The fields of an instance are:

| Field | Meaning |
|---|---|
| `name` | Key into `G.items` |
| `q` | Quantity, for items that stack |
| `level` | Upgrade or compound level. A new upgradable item has `0` |
| `p` | A **property** (also called a title): `"shiny"`, `"glitched"`, `"lucky"`, ... |
| `stat_type` | The attribute that a stat scroll gave the item (`"str"`, `"dex"`, ...) |
| `l` | Lock state: `"l"` locked, `"s"` sealed, `"u"` unsealing |
| `v` | PvP mark: the date when the character got the item on a PvP map. The item can drop on death |
| `m` | The item came from the Merchant's Luck skill. The value is the name of the player who had the buff |
| `acl` | Account lock: you cannot give the item to a different account |
| `expires` | End date for items with a time limit (boosters, elixirs) |
| `gift` | Starter gift item. It sells for 1 gold |
| `data` | Free data, for example the cosmetic inside a `cxjar` |
| `charges` | Charges of items that use them |

The server has its own list of fields in a comment at `node/server_functions.js:4204-4232`. The client never gets some fields. `cache_item` removes them before it sends an inventory slot (`node/server_functions.js:4190-4202`, `:4234`):

- `grace`: hidden upgrade luck (see the next chapter).
- `o` and `oo`: the names of the upgrader and the first owner.
- `src`, and the trade fields `b`, `price`, `rid`, `want`, `giveaway` and `list`.

 Items in **trade slots** keep the trade fields (see [Trades between players](#game-gold-and-the-economy)).

To get the stats of an item, combine the two parts. The function `calculate_item_properties(item)` (`js/old_common_functions.js:877`) does this. It starts with the stats of the definition. Then it adds the increase per level, the property, and the extra stats for a class or a map. A client that shows stats or compares gear needs a copy of this function.

### Equipment slots

A character has **16 equipment slots** (`character_slots`, `js/old_common_functions.js:104`):

| Slot | Item types that it holds | Count in G 17478 |
|---|---|---|
| `mainhand` | `weapon` | 98 weapons |
| `offhand` | `shield`, `quiver`, `source`, `misc_offhand`, or a second weapon if the class permits it | 12 + 6 + 6 + 2 |
| `helmet`, `chest`, `pants`, `shoes`, `gloves` | the type with the same name | 33, 36, 16, 22, 25 |
| `cape` | `cape` | 15 |
| `belt` | `belt` | 14 |
| `amulet` | `amulet` | 21 |
| `ring1`, `ring2` | `ring` | 26 |
| `earring1`, `earring2` | `earring` | 16 |
| `orb` | `orb` | 27 |
| `elixir` | `elixir`. When a character drinks an elixir, the elixir goes into this slot with an end time | 33 |

The class definition tells which weapon types a class can hold in each hand (`mainhand`, `offhand`, `doublehand` in [classes](#g-classes)). [Classes](#game-classes) explains each class.

A character with a stand also has **trade slots**, `trade1` to `trade30`. See [Trades between players](#game-gold-and-the-economy).

To equip an item:

1. Find the slot number of the item in `me.items`.
2. Send [`equip`](#send-equip) `{num}`. The server selects the equipment slot from the item type.
3. Read the next `player` update. The item is now in `me.slots`, and its old inventory slot holds the item that you took off, or `null`.

The same event also drinks potions and puts items on a stand. The [`equip`](#send-equip) entry lists its error replies.

### Item types

G 17478 puts its 638 items into 52 types. The most important types are:

| Group | Types (count) | What they do |
|---|---|---|
| Gear | weapon 98, chest 36, helmet 33, gloves 25, shoes 22, pants 16, cape 15, shield 12, quiver 6, source 6, misc_offhand 2 | A character wears them. Almost all are **upgradable** |
| Jewelry | ring 26, amulet 21, earring 16, belt 14, orb 27 | A character wears them. Almost all are **compoundable** |
| Consumables | pot 7, elixir 33, throw 4 | Potions give back HP or MP. Elixirs are buffs that last for hours |
| Upgrade materials | uscroll 5, cscroll 4, pscroll 22, offering 3 | You use them at the upgrade NPC (next chapter) |
| Exchange items | gem 23, box 5, quest 25 | You give them to an NPC for a random reward |
| Crafting | material 72 | Ingredients for the recipes in `G.craft` |
| Currency | token 4 | You spend them at token shops |
| Tools and keys | stand 2, computer 2, tracker 1, booster 3, bank_key 3, dungeon_key 5, licence 1, tome 1, ... | They change what a character can do |

An **NPC** (non-player character) is a character that the server controls, for example a shop keeper. A **buff** is a temporary bonus on a character.

In G 17478, 263 items have an `upgrade` table. These are weapons and armor. 111 items have a `compound` table. These are rings, earrings, amulets, belts, orbs, some offhand items and the three boosters.

### Levels and grades

Gear starts at **+0**. It can go up one level at a time. Gear goes up by **upgrade**, and jewelry goes up by **compound** (next chapter). Each level adds the increase per level of the item. At high levels, a multiplier makes the increase larger (`js/old_common_functions.js:1012-1040`):

| Level | Upgrade multiplier | Compound multiplier |
|---|---|---|
| 1 to 4 | 1 | 1 |
| 5 | 1 | 1.25 |
| 6 | 1 | 1.5 |
| 7 | 1.25 | 2 |
| 8 | 1.5 | 3 |
| 9 | 2 | 3 |
| 10 | 3 | 3 |
| 11, 12 | 1.25 | (compounds stop at 10) |

Example: a Blade (`G.items.blade`) has `attack: 15` and `upgrade: {attack: 4, range: 1.5}`.

| Blade | +0 | +1 | +3 | +5 | +7 | +8 | +9 | +10 | +12 |
|---|---|---|---|---|---|---|---|---|---|
| Attack | 15 | 19 | 27 | 35 | 44 | 50 | 58 | 70 | 80 |

A **grade** is a quality tier. The game shows these names (the official guide, `docs/guide/upgrading.html`):

| Grade | Name | Meaning |
|---|---|---|
| 0 | Normal | |
| 1 | High | |
| 2 | Rare | |
| 3 | Legendary | |
| 4 | Exalted | Maximum level. The server refuses more upgrades (`max_level`) |

The grade of an item changes with its level. Each definition has `grades: [a, b, c, d]`. These are the levels where grades 1, 2, 3 and 4 start (`calculate_item_grade`, `js/old_common_functions.js:773-781`). The default is `[9,10,11,12]`.

- The Blade has `[7,9,10,12]`. From +0 to +6 it is Normal. At +7 and +8 it is High, at +9 Rare, at +10 and +11 Legendary, and at +12 Exalted.
- A Ring of Intelligence has `[3,5,6,7]`. Its maximum level is +7.
- A `0` in the array means that the item starts at that grade. 62 items have `[0,7,10,12]`. They are High at +0.

The grade has two effects:

1. It decides which scroll the next level needs (next chapter).
2. The grade at +0 selects the row of the odds tables. The server calls this grade `igrade` (`node/server_functions.js:45`). Items with a higher `igrade` are harder to improve.

| Grade at +0 | Upgradable items | Compoundable items |
|---|---|---|
| 0 (Normal) | 60 | 43 |
| 1 (High) | 133 | 29 |
| 2 (Rare) | 68 | 36 |

### Properties (titles)

An instance can have one property in `p`. The properties are in `G.titles` ([titles](#g-titles)). A property adds stats to the item:

| Property | Effect | How you get it |
|---|---|---|
| `shiny` | Weapon: +4 attack (+7 for weapons that use two hands). Item with `stat`: +2 stat. Armor: +12 armor and +10 resistance. Other items: +1 str, int and dex (`js/old_common_functions.js:967-989`) | Chance of 1 in 500 for upgradable items and 1 in 20,000 for compoundable items. This applies to items from chests, crafts, exchanges and token shops (`node/server.js:2028-2036`). Also an upgrade attempt with only a metal offering (next chapter) |
| `glitched` | +1 to dex, int or str. The server selects the stat again **each time it calculates stats** (`js/old_common_functions.js:990-1005`) | Items from the `glitch` exchange table |
| `lucky` | +2 luck | An upgrade or compound succeeds on the exact percent (next chapter) |
| `superfast`, `fast` | +20 or +10 attack speed | Source "upgrade". The line of code that gave it is a comment (`node/server.js:7350`) |
| `sniper`, `firehazard`, `stomped`, `gooped`, `festive`, `abtesting` | Small stat bonuses | Achievements on the equipped item (see [Events, bosses and seasons](#game-events-bosses-and-seasons)) |
| `cavefound` | Shown as "Cave". Resistance +5. It marks an item from the Cave of Many Dreams | Cave rewards |
| `legacy`, `critmonger` | Changed stats or small bonuses | Given by hand |

A property stays on the item after a compound. The result takes the first property of the three items, except `legacy` (`node/server.js:7075-7079`).

### Stat scrolls

Some gear has a `stat` field. These are attribute points with no attribute yet. A **stat scroll** (`pscroll`, for example `strscroll`, 8,000 gold at Lucas) sets `stat_type` on the item. Then the item converts those points into that attribute.

- For most attributes, 1 point gives 1. Some attributes have a multiplier (`mult`, `js/old_common_functions.js:943-966`). Examples: armor and resistance ×2.25, speed ×0.325, crit ×0.125, gold and xp ×0.5.
- The number of scrolls increases with the grade of the item: 1, 10, 100, 1000, then 9999 (`node/server.js:7503`).
- A stat scroll almost never fails. The chance of success is 99.999%.
- To use one, send [`upgrade`](#send-upgrade) with the stat scroll in `scroll_num`.

### Stacks

An item stacks if its definition has `s`. The value of `s` is the maximum stack size. 236 items stack. 210 of them stack to 9999. The others stack to between 10 and 2000.

Two stacks merge only when all these conditions are true (`can_stack`, `js/old_common_functions.js:407-419`):

- The name is the same, and the total is not more than `s`.
- The property is the same. A property with `stackable: true` in G (for example `cavefound`) does not count.
- Both stacks have a PvP mark, or neither has one.
- The contents of jars are the same.
- Neither stack is locked or blocked.

To move or divide stacks, use [`split`](#send-split) and [`imove`](#send-imove).

### Inventory

The inventory has **42 slots**. The server sets `player.isize = 42` (`node/server.js:1456`). The field `esize` in the player data is the number of empty slots.

Some items have an effect when they are only in the inventory (`node/server.js:1460-1468`):

- An Ancient Computer (`computer`) lets a character use NPC shops, the upgrade NPC and some other services from any location.
- A Tracktrix (`tracker`) records kills and shows the drop tables of monsters. It also calls the cavalry (see [Events, bosses and seasons](#game-events-bosses-and-seasons)).
- A Super Computer (`supercomputer`) does both.

A full inventory is the most frequent problem for a bot. If a character has no space, loot goes to a different party member or to the Lost and Found. Many actions fail with `inventory_full`, `no_space` or `inv_size`. Keep 5 or more slots free, and send extra items to the merchant or the bank.

### The bank

The bank keeps items and gold for **all characters of the account**. Only one of your characters can be in the bank at one time. The door is in `main`. When a character enters a bank map, the server "mounts" the account (`node/server.js:5983-6050`). All bank actions use the [`bank`](#send-bank) event.

| Map | Packs | Price to open each pack (gold or shells) |
|---|---|---|
| `bank` (The Bank) | `items0`-`items7` | 2 are free. The others cost 75M-112.5M gold or 600-900 shells |
| `bank_b` (Basement) | `items8`-`items23` | 1 is free. The others cost 475M-1.675B gold or 1000-1200 shells |
| `bank_u` (Underground) | `items24`-`items47` | 1 is free. The others cost 2.075B-9.995B gold or 1350-1850 shells |

The prices are in the `bank_packs` table (`js/old_common_functions.js:54-103`). Each pack holds 42 items. You can use a pack only on its own floor.

The basement and the underground have locked doors. To open a door for the account, go into the bank. Then send [`activate`](#send-activate) with a key (`node/server.js:9661-9686`):

- `bkey` (The Bank Key) opens the basement. It drops from some monsters.
- `ukey` (a second "The Bank Key") opens the underground.
- `dkey` (Diamond Key) opens the next closed pack.

The server uses up the key. The bank packs are some of the largest gold sinks in the game.

### Locks

Smith, the Locksmith in `desertland`, locks items for 250,000 gold ([`locksmith`](#send-locksmith), `node/server.js:6791-6861`). He does not lock scrolls, offerings or tomes.

- A **locked** item (`l: "l"`) cannot be sold, sent, upgraded, compounded, destroyed or put on a stand. A lock prevents an error in a script from losing the item. To unlock it costs 250,000 gold.
- A **sealed** item (`l: "s"`) has stronger protection. The first unlock starts a wait of 2 days (`l: "u"`). After the wait, send the unlock again (`node/server.js:6819`).

> **Caution:** A bot must examine `l` before it sells or upgrades an item. A lock is usually a decision of the player.

## Upgrading and compounding

An upgrade is a gamble, and much of the game depends on it. You pay for a scroll and use it on an item. The server makes a random roll. If the roll succeeds, the item goes up one level. If the roll fails, the server **destroys** the item.

High levels are valuable because they are rare. They are rare because each high item costs many destroyed items. Most of the gold in the game goes into upgrades.

A **sink** is a game mechanic that removes gold or items from the economy. Upgrades are a sink: scrolls remove gold and failures remove items. In a game where bots farm 24 hours a day, the economy needs sinks. Without them, gold and items increase and all prices go up without limit.

### Where and with what

- **Upgrade and compound**: go to Cue (the `newupgrade` NPC) in `main`, at about (-207, -220). Cue does both. The server uses the position of Cue for both checks (`js/old_common_functions.js:251`). You must be within 400 px (`B.sell_dist`, `node/server.js:220`), or carry a computer.
- **Scrolls**: Lucas (the `scrolls` NPC) in `main`, at about (-464, -96), sells them.
- The events are [`upgrade`](#send-upgrade) and [`compound`](#send-compound). The result is not a direct reply. It comes some seconds later (see "Timing" below).

The prices are `g` in G 17478:

| Item | Type | Grade | NPC price |
|---|---|---|---|
| `scroll0` Upgrade Scroll | uscroll | 0 | 1,000 |
| `scroll1` High Upgrade Scroll | uscroll | 1 | 40,000 |
| `scroll2` Rare Upgrade Scroll | uscroll | 2 | 1,600,000 |
| `scroll3` Legendary Upgrade Scroll | uscroll | 3 | not sold (value 480M) |
| `scroll4` Ultimate Upgrade Scroll | uscroll | 3.6 | not sold |
| `cscroll0` / `cscroll1` / `cscroll2` | cscroll | 0 / 1 / 2 | 6,400 / 240,000 / 9,200,000 |
| `cscroll3` Legendary Compound Scroll | cscroll | 3 | not sold |
| `offeringp` Primling | offering | 1 | not sold (value 480,000) |
| `offering` Primordial Essence | offering | 2 | 27,420,000 at Garwyn (`premium` NPC) |
| `offeringx` Primordial X | offering | 3 | not sold |

**The scroll rule:** the grade of the scroll must be **equal to or more than the current grade of the item** (`node/server.js:7176-7193`).

- A Blade at +6 is Normal. A `scroll0` can take it to +7.
- At +7 the Blade is High. To go to +8, it needs a `scroll1`.
- The server accepts a scroll with a **higher** grade than necessary. It increases the chance (below).

### Your first upgrade, step by step

This procedure upgrades a +0 Coat to +1. It uses only the events above. [Gearing up: upgrades and compounds](#learn-gearing-up-upgrades-and-compounds) in the course shows the same steps in code.

1. Buy the item if you do not have it. Go to Gabriel (`basics`) in `main` and send [`buy`](#send-buy) `{name: "coat"}`. The price is 6,000 gold.
2. Go to Lucas. Send `buy` `{name: "scroll0", quantity: 1}`. The price is 1,000 gold.
3. Read the next `player` update. Find the slot numbers of the coat and the scroll in `me.items`.
4. Go to Cue. Stay within 400 px of (-207, -220).
5. Ask for the chance. Send `upgrade` `{item_num, scroll_num, clevel: 0, calculate: true}`. `clevel` is the current level of the item.
6. Read the reply: `game_response` `{response: "upgrade_chance", chance: 0.9999999, ...}`. The server used nothing.
7. If the chance is good enough for you, send the same packet without `calculate`.
8. Wait. The server sends a `player` update in which the slot of the coat holds a `placeholder` item. Do not move items in this time.
9. Read the result. About 1 s later, a `player` update holds a hitchhiker `game_response` `upgrade_success` or `upgrade_fail`. A **hitchhiker** is an event inside the `hitchhikers` list of a `player` update ([Waiting for a reply](#learn-hearing-back)).
10. On a success, the slot holds the coat with `level: 1`. On a failure, the slot is `null`.

If it fails before the roll, the server sends an error and uses nothing:

| Reply | Cause | What to do |
|---|---|---|
| `{response: "distance", place: "upgrade"}` | You are more than 400 px from Cue | Move closer to (-207, -220) |
| `"upgrade_mismatch"` | `clevel` is not the level of the item | Read `me.items[num].level` again |
| `"upgrade_incompatible_scroll"` | The scroll grade is below the item grade | Use the scroll of the current grade (scroll rule above) |
| `"upgrade_in_progress"` | The last upgrade has not ended | Wait for the hitchhiker |
| `{response: "item_locked"}` | The item is locked | Unlock it at Smith, or select a different item |
| `{response: "max_level"}` | The item is Exalted | Stop |

The [`upgrade`](#send-upgrade) entry lists all replies.

### The odds

The base chance comes from G. It is `G.upgrades[igrade][new_level]` or `G.compounds[igrade][new_level]` (the server reads the same tables from `D`, `node/server.js:7323`, `:6954`). Here `igrade` is the grade of the item at +0. See [upgrades / compounds](#g-upgrades-compounds) for the full tables. For an item that starts Normal:

| Upgrade to | +1 | +2 | +3 | +4 | +5 | +6 | +7 | +8 | +9 | +10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Base chance (`G.upgrades["0"]`) | 99.99999% | 98% | 95% | 70% | 60% | 40% | 25% | 15% | 7% | 2.4% |
| Chance that a new +0 item gets to this level | 100% | 98% | 93% | 65% | 39% | 16% | 3.9% | 0.59% | 0.041% | 0.001% |

The second row is the product of the base chances, without the bonuses below. Its inverse is the average number of new items that you destroy for one item at that level. For +7 the number is about 26. For +10 it is about 100,000. Thus a +10 item is an event for the full server.

The base chances for +11 and +12 are 14% and 11% in G 17478. These are higher than the 2.4% for +10. But +11 and +12 need grade 3 scrolls, and these scrolls are rare.

The server then changes the base chance (`node/server.js:7318-7410`):

1. **Scroll of a higher grade.** The scroll grade is more than the item grade, and the new level is +10 or less. Then `p = p × 1.2 + 0.01`. The server marks the attempt as "high".
2. **Offering.** An offering in the same packet multiplies the chance. The grade of the offering against the grade of the item sets the multiplier:
   - ×1.7 for two or more grades above, ×1.5 for one grade above, ×1.4 for equal.
   - ×1.15 for one grade below, ×1.08 for lower.
   - The server also adds a part of the grace. An offering above the grade of the item makes the attempt "high".
3. **Grace without an offering.** The server adds a small bonus from hidden luck counters (below).
4. **Cap.** The result cannot be more than `min(base + 0.24, base × 2)`. For a "high" attempt, the cap is `min(base + 0.36, base × 3)`. Thus no bonus can make a 2.4% roll certain.

A compound has the same pattern with different numbers (`node/server.js:6936-7016`):

- A scroll of a higher grade gives `p × 1.1 + 0.001`. This bonus has no level limit.
- An offering gives ×1.08 to ×1.64.
- The cap is `min(base × (3 + 0.6h), base + 0.2 + 0.05h)`. Here `h` is the number of grades between the scroll and the item.
- A compound of boosters always succeeds.

This function shows the upgrade formula. It shows how the parts combine. It cannot give the exact number of the server, because one input is hidden (next section). To get the exact number, use `calculate: true`.

```js
// Upgrade success chance, ported from the socket "upgrade" handler
// (node/server.js:7318-7410). Pure function: no socket needed.
// base:          G.upgrades[igrade][newLevel], where igrade is the item's grade at +0
// newLevel:      the level being attempted (current level + 1)
// itemGrade:     the item's grade now (0 normal ... 4 exalted), see calculate_item_grade
// scrollGrade:   G.items[scroll].grade (0, 1, 2, 3, or 3.6 for the Ultimate scroll)
// offeringGrade: G.items[offering].grade, or null when no offering is used
// graceSum:      the server's hidden "grace" total (see the text); 0 if unknown
function upgradeChance(base, newLevel, itemGrade, scrollGrade, offeringGrade, graceSum) {
  // Grace is scaled by the base odds and spread over the level (node/server.js:7345).
  const grace = (base * graceSum) / newLevel + graceSum / 1000;
  let p = base;
  let high = false; // a "high" attempt gets a looser cap at the end
  // A scroll of a higher grade than the item needs: x1.2 + 1 point, up to +10.
  if (scrollGrade > itemGrade && newLevel <= 10) {
    p = p * 1.2 + 0.01;
    high = true;
  }
  if (offeringGrade !== null) {
    // Offerings multiply the odds; how much depends on offering grade vs item grade.
    if (offeringGrade > itemGrade + 1) { p = p * 1.7 + grace * 4; high = true; }
    else if (offeringGrade > itemGrade) { p = p * 1.5 + grace * 1.2; high = true; }
    else if (offeringGrade === itemGrade) p = p * 1.4 + grace;
    else if (offeringGrade === itemGrade - 1) p = p * 1.15 + grace / 3.2;
    else p = p * 1.08 + grace / 4;
  } else {
    // No offering: grace alone, which is worth almost nothing at low levels.
    p += Math.max(0, grace / 4.8 - 0.4 / ((newLevel - 0.999) ** 2));
  }
  // Hard caps: never more than 2x (or 3x for "high" attempts) the table value.
  const cap = high ? Math.min(base + 0.36, base * 3) : Math.min(base + 0.24, base * 2);
  return Math.min(p, cap);
}
```

```ts
// Upgrade success chance, ported from the socket "upgrade" handler (node/server.js:7318-7410).
interface UpgradeAttempt {
  base: number;                 // G.upgrades[igrade][newLevel]; igrade = item grade at +0
  newLevel: number;             // current level + 1
  itemGrade: number;            // grade now: 0 normal, 1 high, 2 rare, 3 legendary, 4 exalted
  scrollGrade: number;          // G.items[scroll].grade (3.6 for the Ultimate scroll)
  offeringGrade: number | null; // G.items[offering].grade, or null for none
  graceSum: number;             // hidden server grace total (see the text); 0 if unknown
}

function upgradeChance(a: UpgradeAttempt): number {
  // Grace is scaled by the base odds and spread over the level (node/server.js:7345).
  const grace = (a.base * a.graceSum) / a.newLevel + a.graceSum / 1000;
  let p = a.base;
  let high = false; // "high" attempts get a looser cap at the end
  if (a.scrollGrade > a.itemGrade && a.newLevel <= 10) {
    p = p * 1.2 + 0.01; // over-grade scroll bonus
    high = true;
  }
  if (a.offeringGrade !== null) {
    const o = a.offeringGrade;
    if (o > a.itemGrade + 1) { p = p * 1.7 + grace * 4; high = true; }
    else if (o > a.itemGrade) { p = p * 1.5 + grace * 1.2; high = true; }
    else if (o === a.itemGrade) p = p * 1.4 + grace;
    else if (o === a.itemGrade - 1) p = p * 1.15 + grace / 3.2;
    else p = p * 1.08 + grace / 4;
  } else {
    p += Math.max(0, grace / 4.8 - 0.4 / ((a.newLevel - 0.999) ** 2));
  }
  // Hard caps: at most 2x the table value (3x for "high" attempts).
  const cap = high ? Math.min(a.base + 0.36, a.base * 3) : Math.min(a.base + 0.24, a.base * 2);
  return Math.min(p, cap);
}
```

```python
# Upgrade success chance, ported from the socket "upgrade" handler (node/server.js:7318-7410).
def upgrade_chance(base: float, new_level: int, item_grade: int, scroll_grade: float,
                   offering_grade: float | None = None, grace_sum: float = 0.0) -> float:
    """base = G["upgrades"][str(igrade)][str(new_level)]; grace_sum is the hidden
    server grace total described in the text (use 0 if you don't know it)."""
    # Grace is scaled by the base odds and spread over the level (node/server.js:7345).
    grace = base * grace_sum / new_level + grace_sum / 1000
    p = base
    high = False  # "high" attempts get a looser cap at the end
    if scroll_grade > item_grade and new_level <= 10:
        p = p * 1.2 + 0.01  # over-grade scroll bonus
        high = True
    if offering_grade is not None:
        if offering_grade > item_grade + 1:
            p, high = p * 1.7 + grace * 4, True
        elif offering_grade > item_grade:
            p, high = p * 1.5 + grace * 1.2, True
        elif offering_grade == item_grade:
            p = p * 1.4 + grace
        elif offering_grade == item_grade - 1:
            p = p * 1.15 + grace / 3.2
        else:
            p = p * 1.08 + grace / 4
    else:
        p += max(0.0, grace / 4.8 - 0.4 / (new_level - 0.999) ** 2)
    # Hard caps: at most 2x the table value (3x for "high" attempts).
    cap = min(base + 0.36, base * 3) if high else min(base + 0.24, base * 2)
    return min(p, cap)
```

```go
// UpgradeChance ports the odds math of the socket "upgrade" handler
// (node/server.js:7318-7410). Needs: import "math".
// base = G.upgrades[igrade][newLevel]; offeringGrade < 0 means "no offering";
// graceSum is the hidden server grace total described in the text (0 if unknown).
func UpgradeChance(base float64, newLevel int, itemGrade int, scrollGrade float64,
	offeringGrade float64, graceSum float64) float64 {
	L := float64(newLevel)
	ig := float64(itemGrade)
	// Grace is scaled by the base odds and spread over the level (node/server.js:7345).
	grace := base*graceSum/L + graceSum/1000
	p := base
	high := false // "high" attempts get a looser cap at the end
	if scrollGrade > ig && newLevel <= 10 {
		p = p*1.2 + 0.01 // over-grade scroll bonus
		high = true
	}
	switch {
	case offeringGrade < 0: // no offering: grace alone
		p += math.Max(0, grace/4.8-0.4/math.Pow(L-0.999, 2))
	case offeringGrade > ig+1:
		p, high = p*1.7+grace*4, true
	case offeringGrade > ig:
		p, high = p*1.5+grace*1.2, true
	case offeringGrade == ig:
		p = p*1.4 + grace
	case offeringGrade == ig-1:
		p = p*1.15 + grace/3.2
	default:
		p = p*1.08 + grace/4
	}
	// Hard caps: at most 2x the table value (3x for "high" attempts).
	limit := math.Min(base+0.24, base*2)
	if high {
		limit = math.Min(base+0.36, base*3)
	}
	return math.Min(p, limit)
}
```

```csharp
// Upgrade success chance, ported from the socket "upgrade" handler (node/server.js:7318-7410).
// baseP = G.upgrades[igrade][newLevel]; offeringGrade = null means no offering;
// graceSum is the hidden server grace total described in the text (0 if unknown).
static double UpgradeChance(double baseP, int newLevel, int itemGrade, double scrollGrade,
                            double? offeringGrade, double graceSum)
{
    // Grace is scaled by the base odds and spread over the level (node/server.js:7345).
    double grace = baseP * graceSum / newLevel + graceSum / 1000;
    double p = baseP;
    bool high = false; // "high" attempts get a looser cap at the end
    if (scrollGrade > itemGrade && newLevel <= 10)
    {
        p = p * 1.2 + 0.01; // over-grade scroll bonus
        high = true;
    }
    if (offeringGrade is double o)
    {
        if (o > itemGrade + 1) { p = p * 1.7 + grace * 4; high = true; }
        else if (o > itemGrade) { p = p * 1.5 + grace * 1.2; high = true; }
        else if (o == itemGrade) p = p * 1.4 + grace;
        else if (o == itemGrade - 1) p = p * 1.15 + grace / 3.2;
        else p = p * 1.08 + grace / 4;
    }
    else
    {
        p += Math.Max(0, grace / 4.8 - 0.4 / Math.Pow(newLevel - 0.999, 2));
    }
    // Hard caps: at most 2x the table value (3x for "high" attempts).
    double cap = high ? Math.Min(baseP + 0.36, baseP * 3) : Math.Min(baseP + 0.24, baseP * 2);
    return Math.Min(p, cap);
}
```

```rust
/// Upgrade success chance, ported from the socket "upgrade" handler (node/server.js:7318-7410).
/// `base` = G.upgrades[igrade][new_level]; `offering_grade` = None means no offering;
/// `grace_sum` is the hidden server grace total described in the text (0.0 if unknown).
fn upgrade_chance(base: f64, new_level: u32, item_grade: i32, scroll_grade: f64,
                  offering_grade: Option<f64>, grace_sum: f64) -> f64 {
    let l = new_level as f64;
    let ig = item_grade as f64;
    // Grace is scaled by the base odds and spread over the level (node/server.js:7345).
    let grace = base * grace_sum / l + grace_sum / 1000.0;
    let mut p = base;
    let mut high = false; // "high" attempts get a looser cap at the end
    if scroll_grade > ig && new_level <= 10 {
        p = p * 1.2 + 0.01; // over-grade scroll bonus
        high = true;
    }
    match offering_grade {
        Some(o) if o > ig + 1.0 => { p = p * 1.7 + grace * 4.0; high = true; }
        Some(o) if o > ig => { p = p * 1.5 + grace * 1.2; high = true; }
        Some(o) if o == ig => p = p * 1.4 + grace,
        Some(o) if o == ig - 1.0 => p = p * 1.15 + grace / 3.2,
        Some(_) => p = p * 1.08 + grace / 4.0,
        None => p += (grace / 4.8 - 0.4 / (l - 0.999).powi(2)).max(0.0),
    }
    // Hard caps: at most 2x the table value (3x for "high" attempts).
    let cap = if high { (base + 0.36).min(base * 3.0) } else { (base + 0.24).min(base * 2.0) };
    p.min(cap)
}
```

```java
// Upgrade success chance, ported from the socket "upgrade" handler (node/server.js:7318-7410).
// base = G.upgrades[igrade][newLevel]; offeringGrade = null means no offering;
// graceSum is the hidden server grace total described in the text (0 if unknown).
static double upgradeChance(double base, int newLevel, int itemGrade, double scrollGrade,
                            Double offeringGrade, double graceSum) {
    // Grace is scaled by the base odds and spread over the level (node/server.js:7345).
    double grace = base * graceSum / newLevel + graceSum / 1000;
    double p = base;
    boolean high = false; // "high" attempts get a looser cap at the end
    if (scrollGrade > itemGrade && newLevel <= 10) {
        p = p * 1.2 + 0.01; // over-grade scroll bonus
        high = true;
    }
    if (offeringGrade != null) {
        double o = offeringGrade;
        if (o > itemGrade + 1) { p = p * 1.7 + grace * 4; high = true; }
        else if (o > itemGrade) { p = p * 1.5 + grace * 1.2; high = true; }
        else if (o == itemGrade) p = p * 1.4 + grace;
        else if (o == itemGrade - 1) p = p * 1.15 + grace / 3.2;
        else p = p * 1.08 + grace / 4;
    } else {
        p += Math.max(0, grace / 4.8 - 0.4 / Math.pow(newLevel - 0.999, 2));
    }
    // Hard caps: at most 2x the table value (3x for "high" attempts).
    double cap = high ? Math.min(base + 0.36, base * 3) : Math.min(base + 0.24, base * 2);
    return Math.min(p, cap);
}
```

Example: a Normal item goes to +7 (base 25%). It uses a `scroll0`, no offering, and the grace total is 7. The chance is about 29.2%. With a `scroll1` (one grade higher), the chance is about 35.2%. With a `scroll1` and a Primordial Essence (grade 2), the chance is the "high" cap of 61%.

### Grace: the hidden luck counters

**Grace** is the pity system of the server. A **pity system** increases your chance after bad luck. It stops very long series of failures. AL has four counters (`node/server.js:7325-7345`, `:7457-7487`):

- **Item grace** (`item.grace`). It increases by 0.4 when you use a scroll of a higher grade. It also increases when you use an offering. At random (2.5% for each attempt) it increases by 1 (`node/server.js:7392`). An equipped item also gets 0.4 about one time in 15 hours of play (`node/server.js:16449-16469`). Grace stays with the item. The server never sends it in your inventory.
- **Player grace** for each level (`player.p.ugrace[level]`). Each failure at a level increases it. A success at that level sets it to 0.
- **Server grace** for each level (`S.ugrace[level]`). It is the same as player grace, but all players on the server share it. Its start value is 24 for each level (`node/server_functions.js:3193-3199`). A success by any player at that level sets it to 0. This value is on the server only. It is not in the `S` object that clients get.
- **Offering grace** (`player.p.ograce`). It increases when an attempt with an offering fails. It decreases after a success.

The formula uses this total: `max(0, min(L+1, item.grace + min(3, player_grace/4.5) + igrace) + min(6, server_grace/3) + ograce/3.2)`. Here `L` is the new level, and `igrace` is +1 for items that start Normal, -1 for High and -2 for Rare (`node/server_functions.js:44-52`).

You cannot calculate this total, because most of its inputs are hidden. Thus, ask the server:

1. Send the `upgrade` or `compound` packet with `calculate: true`.
2. Read the reply, a `game_response` `upgrade_chance` or `compound_chance` with the exact `chance` (`node/server.js:7411`, `:6990`).

The server uses the same code for this request, but it does not use any items. A careful bot asks for the chance before each expensive attempt.

### Two hidden rules in the roll

- **The lucky slot.** Each character has a secret inventory slot, `player.p.item_num`. The server selects it at random one time (`node/server_functions.js:4409-4410`). Upgrade an item in this slot, and 60% of the time the server makes your roll better (`result × 0.975 - 0.012`, `node/server.js:7397-7400`). When you move the item in that slot with `imove`, the lucky slot moves with it. The server does not send the slot to the client, so a bot cannot read it. The server log calls it "16 cheat".
- **Exact rolls.** Sometimes the first four decimals of the roll are the same as those of the chance (for example, both are `0.2924...`). Then a success adds the `lucky` property and the "lucky" achievement (`node/server.js:7469-7472`). For an upgrade, the item must be grade 1 or more. A failure with the same match gives the "unlucky" achievement, and also an `essenceofgreed` for an item of grade 1 or more (`node/server.js:7493-7498`).

### What a failure does

> **Caution:** A failed upgrade with a `uscroll` **destroys the item**. A failed compound destroys **all three** items.

After a failed upgrade, the slot of the item is empty. There is one exception: the Ultimate Upgrade Scroll (`scroll4`, grade 3.6). If an upgrade with this scroll fails, you keep the item at the same level (`node/server.js:7489-7492`). The reply is still `upgrade_fail`.

### Timing: why the result comes late

An upgrade or compound takes time. The official client shows the roll like a slot machine:

1. The server accepts the packet. It removes the scroll and the offering. The slot of the item becomes a `placeholder` item that holds the `chance` of the attempt. You get a `player` update.
2. While the timer runs, [`q_data`](#recv-q_data) events show the digits of the roll one at a time, and then `success` or `failure` (`node/server.js:14739-14810`).
3. When the timer ends, the next `player` update holds a hitchhiker `game_response`. This is `upgrade_success`, `upgrade_fail`, `compound_success` or `compound_fail` (`node/server.js:14827-14950`).

The server makes the roll at step 1. The rest is only a show. An upgrade takes `500 × L × √L` ms, ×1.5 for items that start High and ×2 for items that start Rare (`node/server.js:7427`). That is about 9 s for +7 and 16 s for +10. A compound takes 10 s (`node/server.js:7037`). The merchant skill **Mass Production** makes the next timer half as long, and **Mass Production++** makes it 10 times shorter.

Each character can do only one upgrade and one compound at a time (`upgrade_in_progress`, `compound_in_progress`). The server tells all players about valuable results with a `server_message`, for example "X received a +8 Blade" or "X lost ...". It does not do this for a character in stealth.

### Compounding

A compound is the jewelry version of an upgrade. You combine **three identical items** (same name, same level) with a compound scroll. If the roll succeeds, you get one item at the next level. If it fails, you get nothing. The base chances for jewelry that starts Normal (`G.compounds["0"]`) are:

| Compound to | +1 | +2 | +3 | +4 | +5 | +6 | +7 |
|---|---|---|---|---|---|---|---|
| Base chance | 99% | 75% | 40% | 25% | 20% | 10% | 8% |
| Average number of +0 items for one success | 3.0 | 12.1 | 91 | 1,091 | 16,364 | 490,909 | 18.4M |

The second row is `3 × (items for the level below) / chance`, without bonuses. There are two more rules:

- From +3, the server uses the grade of the item at `level - 2` to select the odds row, not the grade at +0 (`node/server.js:6943-6948`). When jewelry goes into a higher grade, it gets worse odds.
- The grace of a compound comes from the grace of all three items. Three items with high grace help each other.

To compound:

1. Put three identical items (same name, same level) in your inventory. Note their three slot numbers.
2. Buy a compound scroll of the right grade from Lucas (`cscroll0` for Normal items).
3. Go to Cue.
4. Send [`compound`](#send-compound) `{items: [a, b, c], scroll_num, clevel, calculate: true}`. Read `compound_chance`.
5. Send it again without `calculate`.
6. Wait about 10 s for the hitchhiker `compound_success` or `compound_fail`. On a success, the item is in slot `a`. Slots `b` and `c` are now empty.

### Attempts with only an offering

An upgrade packet with an offering and **no scroll** has a different effect (`node/server.js:7217-7307`):

- Some materials have an `offering` property: `goldnugget` 0, `bronzeingot` 0.1, `platinumnugget` 1, `goldingot` 1.1, `platinumingot` 2. Use one on a +0 item to try to make the item `shiny`. If the attempt fails, you keep the item.
- The base chance is 16%. It is 32% if the offering value of the material is more than the grade of the item at +0. It is also 32% if the value is 2 and the item value is 20M or less.
- The server then multiplies the chance by 2.8, 1.6 or 1 for items that start Normal, High or Rare.
- A material with an offering value below the grade of the item is refused (`upgrade_invalid_offering`).
- With a real `offering` item and no scroll, there is no roll. The item only gets 0.5 grace (`node/server.js:7287`).

### A progression plan

Upgrades are the main way to make a character stronger after the first levels ([Gear is more important than level](#game-leveling-and-progression)). The costs are the average gold for one item at that level. They include the destroyed copies and the scrolls, and they use the base chances without grace.

| Coat (`g` 6,000) | +3 | +4 | +5 | +6 | +7 | +8 |
|---|---|---|---|---|---|---|
| Average cost with `scroll0` (`scroll1` for +8) | 9.6k | 15k | 27k | 70k | 284k | 2.2M |
| NPC value of the result | 5.1k | 9.2k | 16.9k | 37.6k | 108k | 344k |

The Blade (`g` 8,400) and the Bow (`g` 16,000) follow the same curve. The cost is about 1.5× the price at +3, 4× at +5, 10× at +6 and 40× at +7. The NPC value is less than the cost at each level. Thus an upgrade is a purchase of stats, not an investment.

This plan starts where [Your first week](#game-what-adventure-land-is) ends. At that point each fighter has the basic set at +3 ([Your first day](#game-what-adventure-land-is)), and the account has a merchant.

**Step 1: take every piece to +4, and then to +5.** The chances are 70% and 60%. Do this for all pieces of all fighters before you go higher. Five pieces at +5 give more stats than one piece at +7.

**Step 2: use spares from +4.** At 70% and less, you lose items. Buy two or three copies of each piece. The merchant upgrades a copy that no fighter wears. Change the gear only after a success. Then a failure costs gold, but the fighter always has an item in the slot.

**Step 3: +6 and +7.** At 40% and 25%, a +7 piece costs about 40× a +0 piece. Upgrade the weapon first, because each level adds the most damage there. Then the armor.

**Step 4: +8 and higher.** +8 needs a `scroll1` (40,000 gold) at 15%. A +8 piece costs about 350× a +0 piece. Most players buy these items from other players. Your merchant can watch the stands for low prices (next chapter). Better gear (a higher `tier` in G) at a low level is often cheaper than basic gear at a high level.

**When a scroll of a higher grade pays.** A higher scroll costs more, but its chance is better. Make the decision with numbers:

1. Let `C` be the value that you risk: the item at its current level, in gold.
2. Ask the server for the chance with each scroll (`calculate: true`).
3. For each scroll, calculate `(C + scroll price) / chance`. This is the average cost of one success.
4. Use the scroll with the smaller result.

For a Normal item, `scroll1` at +7 pays only when `C` is more than about 160,000 gold. At lower levels, `scroll0` is almost always cheaper.

**Jewelry: when compounding pays.** Rings, earrings, amulets, belts and orbs come only from drops, crafts and exchanges. No NPC sells them. For example, the Ring of Small Joys (`ringsj`) drops from any monster in `main` with a chance of 1 in 1,430.

- Compound each group of three +0 copies to +1. The chance is 99%, and the scroll costs 6,400 gold. The NPC value of a +1 ring (48,747) is about the same as three +0 rings and the scroll (49,600). Thus +1 costs you almost nothing.
- Compound three +1 copies to +2 (75%). You need about 12 copies for one +2.
- Stop at +2 for most jewelry. +3 needs about 91 copies, and +4 about 1,091. Buy higher jewelry from players.
- Keep copies. Do not sell rings and earrings at +0 while you still collect a group of three.

**Grow the party together.** Take all items of all party members to +3, then all to +4. Do not take one item to a high level first.

**Before each expensive attempt, ask first.** Send it with `calculate: true`. Grace changes the chance, and only the server knows it.

## Gold and the economy

Gold is the main currency of the game. This chapter tells where gold comes from, where it goes (the sinks), and how players trade. It ends with a plan for a merchant character.

### Where gold comes from

| Source | Amount | Source code |
|---|---|---|
| Monster kills | `round(1 + mg×0.64×share + rand×mg×0.8×share) × monster_level × mult`. `mg` is `G.monster_gold[type]`. 3.1% of kills give ×10, and 0.2% give ×50 | `node/server.js:2393-2446`, `G.drops.gold` |
| Sales to NPCs | The item value (below). Usually 60% of the NPC price | `node/server.js:8079` |
| Exchanges | Many exchange tables have gold rewards (gems, envelopes, golden eggs, Anniversary Gifts) | [`exchange`](#send-exchange) |
| Sales to players | The price, minus sales tax | `node/server.js:8891`, `:9000` |
| PvP kills | A part of the gold that the dead character carried | `node/server.js:2939-3005` |

The server does not give kill gold directly to the character. The gold goes into the **chest** that the monster drops (see [Drops and loot](#game-drops-and-loot)). The steps when a character opens the chest are:

1. The server multiplies the gold by the gold multiplier of the **character that opens the chest** (`goldm`, from the `gold` stat).
2. The server takes 10% as tax into its gold pool (`server_tax`, `node/server_functions.js:715-727`).

At first, monsters give little gold. A Goo (`monster_gold` 20) at level 1 gives about 14-30 gold. The gold increases with the level and difficulty of the monster. Monsters with `difficulty: 0` give no gold.

### Where gold goes: the sinks

| Sink | Amount | Where |
|---|---|---|
| NPC purchases | Potions, scrolls, basic gear and boosters at full `g` | [`buy`](#send-buy) |
| Upgrade and compound scrolls | 1,000 to 9.2M each. Failures also destroy items | previous chapter |
| Chest tax | 10% of all chest gold | `node/server_functions.js:715` |
| Sales tax on player trades | 1% to 5% of the price. It depends on the level of the seller | `node/server.js:1718-1725` |
| Gold to a different account | 2.5% | `node/server.js:8558` |
| Mail | 48,000 gold. 360,000 with an item | `node/server.js:5746-5751` |
| Bank packs | 75M to 9.995B gold each | `js/old_common_functions.js:54` |
| Locksmith | 250,000 for each lock, seal or unlock | `node/server.js:6791` |
| Crafts and dismantles | The `cost` of the recipe (up to millions) | [craft / dismantle](#g-craft-134-dismantle) |
| Purchases from Ponty or the Lost and Found | 2× or 4× the item value | [`sbuy`](#send-sbuy) |
| Tavern | House edge of 0.5%-2% | `node/server_functions.js:1384` |
| Donations | Any amount to the gold pool of the server | [`donate`](#send-donate) |

Most taxes and fees do not disappear. They go into `S.gold`, the gold pool of the server. The tavern uses this pool to pay wins. The reply to `lostandfound "info"` also shows it. The gold that really leaves the game comes mainly from NPC purchases, scrolls and bank packs.

### NPC prices

NPC shops sell an item at its base price `g`. To buy `q` units costs `q × g` ([`buy`](#send-buy), `node/server.js:8442`). G 17478 has no `p2w` items, so the old `G.inflation` price increase never applies. You must be within 400 px of an NPC that sells the item, on the same map, or carry a computer.

A shop is an NPC with `role: "merchant"` and an `items` list. Important shops in `main`:

| NPC | Position | Sells |
|---|---|---|
| Gabriel (`basics`) | (-89, -165) | Starter gear: helmet, shoes, gloves, pants, coat, and a weapon for each class |
| Lucas (`scrolls`) | (-464, -96) | Upgrade, compound and stat scrolls |
| Ernis (`fancypots`) | (-35, -162) | Potions |
| Divian (`standmerchant`) | (-193, 680) | The merchant stand (`stand0`, 40,000) |
| Garwyn (`premium`) | (192, -564) | Boosters, Tomes of Protection, Primordial Essence |

To sell an item to an NPC, stand within 400 px of any shop NPC and send [`sell`](#send-sell) `{num, quantity}` (`node/server.js:8046-8097`). Any shop buys any item. The reply is `game_response` `gold_received` with the `gold`. Locked items and items on a stand cannot be sold. A gift item sells for 1 gold.

The NPC pays `calculate_item_value` (`js/old_common_functions.js:783-826`). This is 60% of `g`, with a large increase for each upgrade or compound level, plus an amount for the scrolls. Bots use the same function to decide between a stand and an NPC sale.

```js
// What an NPC pays for an item: a port of calculate_item_value
// (js/old_common_functions.js:783-826). item = an inventory item, G = the game data.
function itemValue(item, G) {
  if (!item) return 0;
  if (item.gift) return 1; // starter "gift" items always sell for 1 gold
  const def = G.items[item.name];
  // Shell-shop items keep their full g; everything else sells for 60% of g
  // (G.multipliers.buy_to_sell is the same 0.6, but the code hard-codes it).
  let value = def.cash ? def.g : def.g * 0.6;
  if (def.markup) value /= def.markup; // a few rare scrolls are marked down
  const level = item.level || 0;
  // NOTE: this fallback ([11,12]) differs from calculate_item_grade's [9,10,11,12].
  const grades = def.grades || [11, 12];
  const gradeAt = (i) => (i > grades[1] ? 2 : i > grades[0] ? 1 : 0);
  if (def.compound) {
    for (let i = 1; i <= level; i++) {
      value *= def.cash ? 1.5 : 3.2; // three items went into each level
      if (def.type !== "booster") value += G.items["cscroll" + gradeAt(i)].g / 2.4;
      else value *= 0.75;
    }
  }
  if (def.upgrade) {
    let scrolls = 0; // allowance for scrolls spent, added once at the end
    for (let i = 1; i <= level; i++) {
      scrolls += G.items["scroll" + gradeAt(i)].g / 2;
      if (i >= 7) { value *= 3; scrolls *= 1.32; }
      else if (i === 6) value *= 2.4;
      else if (i >= 4) value *= 2;
      if (i === 9) value = value * 2.64 + 400000;
      if (i === 10) value *= 5;
      if (i === 12) value *= 0.8;
    }
    value += scrolls;
  }
  if (item.expires) value /= 8; // time-limited items are worth an eighth
  return Math.round(value) || 0;
}
```

```ts
// What an NPC pays for an item: a port of calculate_item_value (js/old_common_functions.js:783-826).
interface ItemDef {
  g: number;                          // base price
  type: string;
  cash?: number;                      // shell price (cosmetics)
  markup?: number;                    // value divisor (rare scrolls)
  grades?: number[];
  upgrade?: Record<string, number>;   // present = upgradable
  compound?: Record<string, number>;  // present = compoundable
}
// The server sends gift: 1 on starter items (api.js:539), so accept a number or a boolean.
interface InventoryItem { name: string; level?: number; expires?: string; gift?: number | boolean }
interface GameData { items: Record<string, ItemDef> }

function itemValue(item: InventoryItem | null, G: GameData): number {
  if (!item) return 0;
  if (item.gift) return 1; // starter "gift" items always sell for 1 gold
  const def = G.items[item.name];
  // Shell-shop items keep their full g; everything else sells for 60% (hard-coded 0.6).
  let value = def.cash ? def.g : def.g * 0.6;
  if (def.markup) value /= def.markup;
  const level = item.level ?? 0;
  const grades = def.grades ?? [11, 12]; // NOTE: not calculate_item_grade's [9,10,11,12]
  const gradeAt = (i: number) => (i > grades[1] ? 2 : i > grades[0] ? 1 : 0);
  if (def.compound) {
    for (let i = 1; i <= level; i++) {
      value *= def.cash ? 1.5 : 3.2; // three items went into each level
      if (def.type !== "booster") value += G.items["cscroll" + gradeAt(i)].g / 2.4;
      else value *= 0.75;
    }
  }
  if (def.upgrade) {
    let scrolls = 0; // allowance for scrolls spent, added once at the end
    for (let i = 1; i <= level; i++) {
      scrolls += G.items["scroll" + gradeAt(i)].g / 2;
      if (i >= 7) { value *= 3; scrolls *= 1.32; }
      else if (i === 6) value *= 2.4;
      else if (i >= 4) value *= 2;
      if (i === 9) value = value * 2.64 + 400000;
      if (i === 10) value *= 5;
      if (i === 12) value *= 0.8;
    }
    value += scrolls;
  }
  if (item.expires) value /= 8; // time-limited items are worth an eighth
  return Math.round(value) || 0;
}
```

```python
import math

# What an NPC pays for an item: a port of calculate_item_value (js/old_common_functions.js:783-826).
def item_value(item: dict | None, G: dict) -> int:
    if not item:
        return 0
    if item.get("gift"):
        return 1  # starter "gift" items always sell for 1 gold
    d = G["items"][item["name"]]
    # Shell-shop items keep their full g; everything else sells for 60% (hard-coded 0.6).
    value = d["g"] if d.get("cash") else d["g"] * 0.6
    if d.get("markup"):
        value /= d["markup"]
    level = item.get("level") or 0
    grades = d.get("grades") or [11, 12]  # NOTE: not calculate_item_grade's [9,10,11,12]

    def grade_at(i: int) -> int:
        return 2 if i > grades[1] else 1 if i > grades[0] else 0

    # JS treats an empty table ({}) as present, so test for the key, not its truth value.
    if "compound" in d:
        for i in range(1, level + 1):
            value *= 1.5 if d.get("cash") else 3.2  # three items went into each level
            if d["type"] != "booster":
                value += G["items"][f"cscroll{grade_at(i)}"]["g"] / 2.4
            else:
                value *= 0.75
    if "upgrade" in d:
        scrolls = 0.0  # allowance for scrolls spent, added once at the end
        for i in range(1, level + 1):
            scrolls += G["items"][f"scroll{grade_at(i)}"]["g"] / 2
            if i >= 7:
                value *= 3
                scrolls *= 1.32
            elif i == 6:
                value *= 2.4
            elif i >= 4:
                value *= 2
            if i == 9:
                value = value * 2.64 + 400000
            if i == 10:
                value *= 5
            if i == 12:
                value *= 0.8
        value += scrolls
    if item.get("expires"):
        value /= 8  # time-limited items are worth an eighth
    # JS Math.round rounds halves up; Python's round() would round halves to even.
    return math.floor(value + 0.5)
```

```go
// What an NPC pays for an item: a port of calculate_item_value
// (js/old_common_functions.js:783-826). Needs: import ("fmt"; "math").

// ItemDef holds the G.items fields the formula reads; decode G with encoding/json.
type ItemDef struct {
	G        float64            `json:"g"`        // base price
	Type     string             `json:"type"`
	Cash     float64            `json:"cash"`     // shell price (cosmetics), 0 if none
	Markup   float64            `json:"markup"`   // value divisor (rare scrolls), 0 if none
	Grades   []int              `json:"grades"`
	Upgrade  map[string]float64 `json:"upgrade"`  // non-nil = upgradable
	Compound map[string]float64 `json:"compound"` // non-nil = compoundable
}

// Item is an inventory item as the server sends it.
type Item struct {
	Name    string `json:"name"`
	Level   int    `json:"level"`
	Expires string `json:"expires"`
	Gift    any    `json:"gift"` // the server sends gift: 1 (api.js:539); any accepts 1 or true
}

func ItemValue(item *Item, items map[string]ItemDef) int64 {
	if item == nil {
		return 0
	}
	if item.Gift != nil && item.Gift != false && item.Gift != 0.0 {
		return 1 // starter "gift" items always sell for 1 gold
	}
	def := items[item.Name]
	// Shell-shop items keep their full g; everything else sells for 60% (hard-coded 0.6).
	value := def.G * 0.6
	if def.Cash != 0 {
		value = def.G
	}
	if def.Markup != 0 {
		value /= def.Markup
	}
	grades := def.Grades
	if grades == nil {
		grades = []int{11, 12} // NOTE: not calculate_item_grade's [9,10,11,12]
	}
	gradeAt := func(i int) int {
		if i > grades[1] {
			return 2
		} else if i > grades[0] {
			return 1
		}
		return 0
	}
	if def.Compound != nil {
		for i := 1; i <= item.Level; i++ {
			if def.Cash != 0 {
				value *= 1.5
			} else {
				value *= 3.2 // three items went into each level
			}
			if def.Type != "booster" {
				value += items[fmt.Sprintf("cscroll%d", gradeAt(i))].G / 2.4
			} else {
				value *= 0.75
			}
		}
	}
	if def.Upgrade != nil {
		scrolls := 0.0 // allowance for scrolls spent, added once at the end
		for i := 1; i <= item.Level; i++ {
			scrolls += items[fmt.Sprintf("scroll%d", gradeAt(i))].G / 2
			switch {
			case i >= 7:
				value *= 3
				scrolls *= 1.32
			case i == 6:
				value *= 2.4
			case i >= 4:
				value *= 2
			}
			if i == 9 {
				value = value*2.64 + 400000
			}
			if i == 10 {
				value *= 5
			}
			if i == 12 {
				value *= 0.8
			}
		}
		value += scrolls
	}
	if item.Expires != "" {
		value /= 8 // time-limited items are worth an eighth
	}
	return int64(math.Floor(value + 0.5)) // JS Math.round: halves round up
}
```

```csharp
// What an NPC pays for an item: a port of calculate_item_value (js/old_common_functions.js:783-826).
// Needs: using System.Text.Json;
// item = an inventory item, g = the parsed game data (both System.Text.Json elements).
static long ItemValue(JsonElement? item, JsonElement g)
{
    if (item is not JsonElement it) return 0;
    // The server sends gift: 1 (api.js:539); accept true or any non-zero number.
    if (it.TryGetProperty("gift", out var gift) &&
        (gift.ValueKind == JsonValueKind.True || (gift.ValueKind == JsonValueKind.Number && gift.GetDouble() != 0)))
        return 1; // starter "gift" items always sell for 1 gold
    JsonElement items = g.GetProperty("items");
    JsonElement def = items.GetProperty(it.GetProperty("name").GetString()!);
    double Num(JsonElement e, string key) =>
        e.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : 0;
    bool cash = Num(def, "cash") != 0;
    // Shell-shop items keep their full g; everything else sells for 60% (hard-coded 0.6).
    double value = cash ? Num(def, "g") : Num(def, "g") * 0.6;
    if (Num(def, "markup") != 0) value /= Num(def, "markup");
    int level = (int)Num(it, "level");
    // NOTE: this fallback ([11,12]) differs from calculate_item_grade's [9,10,11,12].
    int[] grades = def.TryGetProperty("grades", out var gr)
        ? gr.EnumerateArray().Select(x => x.GetInt32()).ToArray() : new[] { 11, 12 };
    int GradeAt(int i) => i > grades[1] ? 2 : i > grades[0] ? 1 : 0;
    double ScrollG(string name) => Num(items.GetProperty(name), "g");
    if (def.TryGetProperty("compound", out _))
    {
        for (int i = 1; i <= level; i++)
        {
            value *= cash ? 1.5 : 3.2; // three items went into each level
            if (def.GetProperty("type").GetString() != "booster") value += ScrollG($"cscroll{GradeAt(i)}") / 2.4;
            else value *= 0.75;
        }
    }
    if (def.TryGetProperty("upgrade", out _))
    {
        double scrolls = 0; // allowance for scrolls spent, added once at the end
        for (int i = 1; i <= level; i++)
        {
            scrolls += ScrollG($"scroll{GradeAt(i)}") / 2;
            if (i >= 7) { value *= 3; scrolls *= 1.32; }
            else if (i == 6) value *= 2.4;
            else if (i >= 4) value *= 2;
            if (i == 9) value = value * 2.64 + 400000;
            if (i == 10) value *= 5;
            if (i == 12) value *= 0.8;
        }
        value += scrolls;
    }
    if (it.TryGetProperty("expires", out _)) value /= 8; // time-limited items are worth an eighth
    return (long)Math.Floor(value + 0.5); // JS Math.round: halves round up
}
```

```rust
use serde_json::Value;

/// What an NPC pays for an item: a port of calculate_item_value (js/old_common_functions.js:783-826).
/// `item` = an inventory item, `g` = the parsed game data.
fn item_value(item: Option<&Value>, g: &Value) -> i64 {
    let Some(item) = item else { return 0 };
    // The server sends gift: 1 (api.js:539); accept true or any non-zero number.
    if item["gift"].as_bool() == Some(true) || item["gift"].as_f64().is_some_and(|g| g != 0.0) {
        return 1; // starter "gift" items always sell for 1 gold
    }
    let items = &g["items"];
    let def = &items[item["name"].as_str().unwrap_or_default()];
    let num = |v: &Value| v.as_f64().unwrap_or(0.0); // missing field -> 0
    let cash = num(&def["cash"]) != 0.0;
    // Shell-shop items keep their full g; everything else sells for 60% (hard-coded 0.6).
    let mut value = if cash { num(&def["g"]) } else { num(&def["g"]) * 0.6 };
    if num(&def["markup"]) != 0.0 {
        value /= num(&def["markup"]);
    }
    let level = item["level"].as_i64().unwrap_or(0);
    // NOTE: this fallback ([11,12]) differs from calculate_item_grade's [9,10,11,12].
    let grades: Vec<i64> = def["grades"]
        .as_array()
        .map(|a| a.iter().filter_map(Value::as_i64).collect())
        .unwrap_or_else(|| vec![11, 12]);
    let grade_at = |i: i64| if i > grades[1] { 2 } else if i > grades[0] { 1 } else { 0 };
    if def.get("compound").is_some() {
        for i in 1..=level {
            value *= if cash { 1.5 } else { 3.2 }; // three items went into each level
            if def["type"] != "booster" {
                value += num(&items[format!("cscroll{}", grade_at(i))]["g"]) / 2.4;
            } else {
                value *= 0.75;
            }
        }
    }
    if def.get("upgrade").is_some() {
        let mut scrolls = 0.0; // allowance for scrolls spent, added once at the end
        for i in 1..=level {
            scrolls += num(&items[format!("scroll{}", grade_at(i))]["g"]) / 2.0;
            if i >= 7 {
                value *= 3.0;
                scrolls *= 1.32;
            } else if i == 6 {
                value *= 2.4;
            } else if i >= 4 {
                value *= 2.0;
            }
            if i == 9 { value = value * 2.64 + 400_000.0; }
            if i == 10 { value *= 5.0; }
            if i == 12 { value *= 0.8; }
        }
        value += scrolls;
    }
    if item.get("expires").is_some() {
        value /= 8.0; // time-limited items are worth an eighth
    }
    (value + 0.5).floor() as i64 // JS Math.round: halves round up
}
```

```java
// What an NPC pays for an item: a port of calculate_item_value (js/old_common_functions.js:783-826).
// item = an inventory item, g = the parsed game data (Jackson JsonNode trees).
static long itemValue(JsonNode item, JsonNode g) {
    if (item == null || item.isNull()) return 0;
    // The server sends gift: 1 (api.js:539); asBoolean() is true for true and for non-zero numbers.
    if (item.path("gift").asBoolean(false)) return 1; // starter "gift" items always sell for 1 gold
    JsonNode items = g.path("items");
    JsonNode def = items.path(item.path("name").asText());
    boolean cash = def.path("cash").asDouble(0) != 0;
    // Shell-shop items keep their full g; everything else sells for 60% (hard-coded 0.6).
    double value = cash ? def.path("g").asDouble() : def.path("g").asDouble() * 0.6;
    if (def.path("markup").asDouble(0) != 0) value /= def.path("markup").asDouble();
    int level = item.path("level").asInt(0);
    // NOTE: this fallback ([11,12]) differs from calculate_item_grade's [9,10,11,12].
    int g0 = def.has("grades") ? def.path("grades").get(0).asInt() : 11;
    int g1 = def.has("grades") ? def.path("grades").get(1).asInt() : 12;
    java.util.function.IntUnaryOperator gradeAt = i -> i > g1 ? 2 : i > g0 ? 1 : 0;
    if (def.has("compound")) {
        for (int i = 1; i <= level; i++) {
            value *= cash ? 1.5 : 3.2; // three items went into each level
            if (!"booster".equals(def.path("type").asText()))
                value += items.path("cscroll" + gradeAt.applyAsInt(i)).path("g").asDouble() / 2.4;
            else value *= 0.75;
        }
    }
    if (def.has("upgrade")) {
        double scrolls = 0; // allowance for scrolls spent, added once at the end
        for (int i = 1; i <= level; i++) {
            scrolls += items.path("scroll" + gradeAt.applyAsInt(i)).path("g").asDouble() / 2;
            if (i >= 7) { value *= 3; scrolls *= 1.32; }
            else if (i == 6) value *= 2.4;
            else if (i >= 4) value *= 2;
            if (i == 9) value = value * 2.64 + 400000;
            if (i == 10) value *= 5;
            if (i == 12) value *= 0.8;
        }
        value += scrolls;
    }
    if (item.has("expires")) value /= 8; // time-limited items are worth an eighth
    return Math.round(value); // Java's Math.round rounds halves up, like JS
}
```

The formula gives these values in G 17478:

| Item | +0 | +3 | +5 | +7 | +8 | +9 | +10 |
|---|---|---|---|---|---|---|---|
| Blade (`g` 8,400) | 5,040 | 6,540 | 22,660 | 149,772 | 467,954 | 3.9M | 58.9M |
| Ring of Intelligence (`g` 24,000) | 14,400 | 510,366 | 5.6M | 73.9M | (max +7) | | |

### Ponty and the Lost and Found

Two NPCs sell again the items that players lost or sold:

- **Ponty** (`secondhands`) in `main` sells items that players sold to NPCs. His price is 2× the value. He gets only some items: items that no NPC sells, gear at +7 or more, and jewelry at +2 or more. He does not get shell items, items with an end date, or items with `acl`. He keeps a maximum of 5 items with the same name and level, and 400 items in total (`secondhands_logic`, `node/server_functions.js:590-638`). See [`secondhands`](#send-secondhands) and [`sbuy`](#send-sbuy).
- **Ron** (`lostandfound`) in the Wizard's Crib (`woffice`) sells lost items for 4× the value. An item is lost when no party member has space for it from a chest. Items in chests that nobody opens for 48 hours also go to Ron (`node/server_functions.js:640-713`).

To use Ron, the character must first [`donate`](#send-donate) 1M gold or more to the gold pool. The server keeps this flag only on the online character. After you reconnect, donate again (`node/server.js:7984`, `:8646-8648`). A character with hop sickness cannot buy from Ron.

Sold and lost items do not disappear at once. Thus a patient bot can sometimes find low prices at these NPCs. For rare materials, Ponty can be cheaper than the drop rate.

### Trades between players

AL has no auction house. Players trade face to face:

- **Merchant stands.** To open a stand, send [`merchant`](#send-merchant) `{num}` with the slot of a stand item (`stand0`, or a computer, which acts as the `cstand`). The character sits on the stand, with items in trade slots (`get_trade_slots`, `node/server_functions.js:4282-4299`):
  - 16 slots usually.
  - 24 slots for a merchant at level 70 or more, or with a computer stand.
  - 30 slots for a merchant at level 80 or more.
- **Slots without a stand.** A character with no stand can send [`trade`](#send-trade) `{event: "show"}` to get 4 slots. The server does not limit stands to the merchant class.
- **Sell orders.** Send [`equip`](#send-equip) `{num, slot: "trade1", price, q}`. `price` is the gold for each unit. Other players buy with [`trade_buy`](#send-trade_buy).
- **Buy orders.** Send [`trade_wishlist`](#send-trade_wishlist) to ask for an item. Other players sell to the order with [`trade_sell`](#send-trade_sell).
- **Trade offers.** Send `equip` `{num, slot: "trade1", want: {name, level}}` to ask for a different item in return. Another player gives that item with [`trade_swap`](#send-trade_swap) (`node/server.js:9061`). No gold changes hands.
- **Giveaways.** Send `equip` `{num, slot, giveaway: true, minutes}`. Players enter with [`join_giveaway`](#send-join_giveaway). When the time ends, a random player who entered gets the item.
- **Direct transfer.** [`send`](#send-send) gives an item, gold or a cosmetic to a player near you. Gold to a different account loses 2.5%. Gold to a character of the same account has no fee. Bots use this to move loot to their merchant.
- **Mail.** [`mail`](#send-mail) goes to characters on other servers. It has a fee.

**Sales tax.** The character that gets the gold pays the tax. The rate depends on the level of that character (`node/server.js:1718-1725`). The tax goes into the gold pool of the server.

| Level of the seller | 1-20 | 21-50 | 51-60 | 61-70 | 71-80 | 81+ |
|---|---|---|---|---|---|---|
| Tax | 5% | 4% | 3% | 2.5% | 2% | 1% |

**Merchant XP.** **XP** (experience points) is what increases the level of a character. Merchants get no XP from kills. A merchant gets XP from these sources:

| Source | XP | Source code |
|---|---|---|
| A sale to or a purchase from a player of a different account | 3.2 × the tax of that trade, at the level of the merchant | `merchant_xp_logic`, `node/server_functions.js:746-751`, called at `node/server.js:8915-8920` |
| A trade offer, for a merchant below level 70 | 3.2 × the tax on the value of the items. At most one level of XP for each partner account in 5 days | `trade_swap_xp`, `node/server_functions.js:753-774` |
| Donations | 3.2 XP for each gold. 4 or 4.8 XP when the gold pool of the server is small | `node/server.js:8629-8680` |
| An open stand | "Marketing XP" every 3 hours: 1% of a level up to level 40, then less | `node/server.js:16003-16037` |

There is an older version of `merchant_xp_logic` at `node/server_functions.js:730`, but in JavaScript the later declaration wins.

### A merchant in practice

Most accounts have one merchant. The merchant does not fight. It sells the loot of the fighters, buys and upgrades their gear, and keeps the gold. An account can have 3 fighters and 1 merchant online at the same time ([Many characters and bots](#game-social-and-multiplayer)). [A party and a merchant](#learn-a-party-and-a-merchant) in the course shows the code.

1. Make a character of the class `merchant` with the HTTP method `create_character` ([HTTP API](#guide-http-api)).
2. Get 40,000 gold. Send it from a fighter with [`send`](#send-send) `{name, gold}`. There is no fee between your own characters.
3. Buy a stand. Go to Divian at (-193, 680) in `main`. Send `buy` `{name: "stand0"}`.
4. Go to the square of `main`, near (0, 0). Find a place more than 40 px from NPCs and more than 10 px from other stands.
5. Open the stand. Send [`merchant`](#send-merchant) `{num}` with the slot of the stand.
6. List items. Send [`equip`](#send-equip) `{num, slot: "trade1", price, q}` for each item. Use a price above the NPC value of the item, or the NPC is a better buyer.
7. Stay. A character on a stand moves at speed 10 (`node/server.js:1756`), and an attack closes the stand (`node/server.js:3468`).
8. Before the merchant walks, send `merchant` `{close: true}`.

**Merrit's parcels.** Keep the stand open, with one priced listing, in the square for 2 minutes. Then Merrit, an NPC that walks in the square, brings a Market Parcel. Each account gets one parcel each hour (`node/logic/market_patron.js`, `G.npcs.citizen22.market`).

Xyn exchanges a parcel for one result. The most probable results are 5 Upgrade Scrolls (30%), 2 Compound Scrolls (22%) and a High Upgrade Scroll (10%). For a new account, these scrolls pay for many upgrades.

The square is x -240 to 240 and y -120 to 144, plus an aisle at x -88 to 88 and y 144 to 360.

**What to do with each item of loot.** Use the NPC value as the minimum price. Then apply these rules in order:

1. Potions, scrolls and materials that you need: keep them.
2. Jewelry at +0: keep it until you have three copies, and compound it (previous chapter).
3. Gear that is better than the gear of a fighter: send it to that fighter.
4. Gear with a high NPC value, and rare materials: put them on the stand above the NPC value. Lower the price after a day without a sale.
5. All else: sell it to an NPC at once. Inventory space is worth more than a small profit.

**How a merchant gets better.** Stands at level 70 have 24 slots. Mass Production (level 30) halves upgrade timers. Merchant's Luck (level 40) gives +12 luck to any player for 1 hour ([Merchant](#game-classes)).

### Exchanges

An **exchange** changes an item into a random reward from a weighted table. The tables are in [drops](#g-drops). Items with an `e` field are exchangeable. The value of `e` is how many you must give at one time.

Most exchanges are at Xyn (the `exchange` NPC) in `main`, at (-25, -478). Some items have their own NPC (the `quest` field). The event is [`exchange`](#send-exchange). The result comes after a timer of 3-6 s, as `game_log` lines and changes to the inventory (`node/server.js:6617-6681`).

| Item | Number to give | NPC | Most probable results (G 17478) |
|---|---|---|---|
| `gem0` Raw Emerald | 1 | Xyn | Armor box 19%, 10 High Upgrade Scrolls 13%, 200k-800k gold |
| `gem1` Tiny Ruby | 1 | Xyn | Junk table 71%, armor box 21%, weapon box 7%, rarely shells or Primordial Essence |
| `marketparcel` Market Parcel | 1 | Xyn | Upgrade Scrolls, Compound Scrolls, seashells, leather (see the merchant section) |
| `armorbox`, `weaponbox` | 1 | Xyn | Random armor (usually basic +0 items) or a random weapon |
| `seashell` | 20 | Tristian (fisherman) | Basic elixirs. Very rarely a Fury |
| `leather` | 40 | Landon | A cape (93%). Rarely a better cape or an armor box |
| `gemfragment` | 50 | Mine Heathcliff | A stat amulet or a Raw Emerald |
| `candy0`, `candy1`, envelopes, eggs, ... | 1 | Xyn | Rewards for a season (see the events chapter) |
| `anniversarygift`, `sixcake` | 1 | Xyn | Rewards of the anniversary event |
| `cosmo0`-`cosmo5` | 1 | Haila | A random cosmetic. Each cosmetic that you have already is 10× less probable each time |

Items from the `glitch` table get the `glitched` property. A character can do only one exchange at a time.

### Token shops

Some activities give **tokens**. Tokens buy items from fixed price lists (`G.tokens`, [tokens](#g-tokens)) with [`exchange_buy`](#send-exchange_buy):

| Token | Source | Shop | Examples (price in tokens) |
|---|---|---|---|
| `monstertoken` | Monster hunts | Daisy (`monsterhunter`) | Tracktrix 4, armor box 5, monster hunter armor 7-15, `funtoken` 20 |
| `funtoken` | Daily events (Goo Brawl, Giga Crab), the holiday tree | Tricksy (`funtokens`) | Confetti (100 for each token), party hat 2, Rabbit's Foot 120 |
| `pvptoken` | Rare global drop on PvP servers (1 in 100,000) | Gn. Spence (`pvptokens`) | Weapon box 1, Harbringer 25, Hammer 120 |
| `friendtoken` | A friend starts to play | Fvona (`friendtokens`) | A gravestone cosmetic jar 4 |

### Crafts and dismantles

A **craft** combines specific items and a gold fee into a new item. `G.craft` has 134 recipes ([craft / dismantle](#g-craft-134-dismantle)). Examples:

- A Fire Bow is a `bow` and an `essenceoffire`, for 20,000 gold.
- Winged Boots are `shoes` and 20 feathers, for 120,000 gold.

Leo (`craftsman`) does 106 recipes. Cole (`mcollector`) does 14, Mira (`anniversary_baker`) 10, and the witch 4. Mira works only during the anniversary event. A crafted item can be shiny. See [`craft`](#send-craft).

A **dismantle** is the opposite of a craft. G has 21 recipes ([`dismantle`](#send-dismantle)). For example, a weapon "of the dead" becomes Monster Bones. A fire weapon gives its essence again.

You can also dismantle jewelry with a level above 0 at Leo. You get **three copies at one level lower**. The fee is 10× the value of the item, with a maximum of 50M (`node/server.js:6452-6475`). This lets you recover from a bad decision, but it is expensive. Boosters cannot be dismantled.

### Shells: the premium currency

**Shells** are the currency of the cash shop. Players buy them with real money on the website or in the Steam client. You cannot buy shells with gold: `buy_shells` replies "No longer possible" (`node/server.js:8099`).

> **Warning:** The rules of the game forbid the sale of gold or items for real money (`htmls/contents/terms.html`).

Characters can also get shells in the game:

- Very rare monster drops. A Goo has a chance of 1 in 8 million to drop 50 shells.
- Some exchange results. `5bucks` (Old Paper Money) gives "800 shells" 98% of the time.
- Level achievements: 50 to 200 shells at levels 50-80, and 20,000 at level 90 (`G.achievements`). Where the server gives these rewards is unclear from the source.
- Merrit sometimes gives 1 shell with a parcel. The chance is 0.5% at 0 shells and 0.001% at 10 or more.

What shells buy:

| Purchase | Cost | Event |
|---|---|---|
| Cosmetic boxes `cosmo0`-`cosmo5` | 129-1,399 shells | [`buy_with_cash`](#send-buy_with_cash) |
| Bank packs | 600-1,850 shells each (instead of gold) | [`bank`](#send-bank) `unlock` |
| A blessing on the server for 3 days. Patron's Grace gives all players +25% xp, +20% gold and +5 luck | 1,200 shells | [`bless_server`](#send-bless_server) |
| Mainframe: the game runs your saved CODE on its servers | 1 shell for each 40-60 minutes | (official client) |
| A character slot after the included 5 (8 with a platform id) | 200 shells | `create_character` (`api.js:559-563`) |

In G 17478, only the six cosmetic boxes have a shell price. Garwyn sells boosters, Tomes of Protection and Primordial Essence for gold. The server uses `G.multipliers.shells_to_gold` (32,000) to calculate the gold value of tables that contain shells.

### Boosters

The XP Booster, Gold Booster and Luck Booster cost 79.84M gold each at Garwyn. A booster gives +20% of its stat when the character carries it and it is **activated** ([`booster`](#send-booster)). Each level adds 12% xp, or 8% gold or luck. Activation starts a time of 30 days, plus 2 days for each level (`node/server.js:9724-9726`).

You can compound boosters like jewelry. A booster compound always succeeds. You can also **shift** a booster to one of the other two kinds. Boosters are usually purchases for characters at a high level.

### The bot economy

In AL, almost all players run code, and many characters play 24 hours a day. The mechanics above cause some results. These results are an analysis of the rules. The source does not state them.

- **Common drops are abundant.** Bots play thousands of hours each day. They make a large quantity of low gear, gold and common materials. The player price of these items goes down to the NPC sale price. Any player can sell to an NPC at any time, so this price is the minimum.
- **The NPC shop price is the maximum** for an item that an NPC sells. No player pays more than the shop price.
- **Destruction makes items scarce.** High gear is valuable because upgrades destroy most attempts. Boss materials are valuable because bosses come on timers. Players set the prices of these items.
- **Sinks keep the economy stable.** Gold comes into the game all the time. Without failed upgrades, scrolls, taxes and bank packs, all prices go up.
- **Information has value.** A bot can record stand prices from `pull_merchants` ([HTTP API](#guide-http-api)) or from stands near it. Then it can buy below the NPC value and sell again. This gives profit with no risk, and merchant XP.

## Drops and loot

When a monster dies, the server makes rolls for loot and puts the loot in a **chest** on the ground. This chapter tells which character gets the roll, how the roll works, and how a party shares a chest. [Looting chests](#learn-acting-in-the-world) in the course shows the code that opens a chest.

### Terms

- **RNG** (random number generator) is the game word for "chance". The server uses `Math.random()` for most rolls.
- A **drop table** is a list of possible drops and their chances. AL has two kinds (details in [drops](#g-drops)):
  - **Independent rolls.** Each entry gets its own roll. One kill can drop many items or no item. Monster drops, map drops and global drops use this kind.
  - **Weighted tables.** The server selects exactly one entry. The probability of an entry is proportional to its weight. Exchanges and boxes use this kind.
- **Luck** increases your chance on independent rolls.
- **Loot** is the gold and items that a monster drops.

### Which character gets the loot

For a usual monster, the loot and XP go to **the character that the monster attacks** when it dies (`issue_monster_award`, `node/server.js:2778`; `kill_monster`, `node/server.js:2869-2893`). This is not always the character that made the last hit. If the monster has no target, the server makes the last attacker its target first.

The modes HARDCORE and DUNGEON set `free_last_hits`. In these modes, the kill goes to the last attacker.

Thus the character that a monster attacks "owns" the monster. Usually this is the **tank**, the character that takes the hits of the party. If that character is in a party, the chest belongs to the party.

**Cooperative** monsters work differently. G 17478 has 19, with `cooperative: true`: all world and season bosses, the Phoenix, the Rharpy, the Rime Djinn, the Brawl Goos and some others. All characters that help get a reward (`issue_monster_awards`, `node/server.js:2717-2776`):

- While the monster is alive, it records **points** for each character. Points come from damage, from hits that the character takes, and from heals (`add_coop_points`, `node/server.js:13297-13316`).
- A character on its **home server** gets 5× points, unless it has Realm Fatigue. A character with Hop Sickness gets 1/4 of the points. (Both are in [Social and multiplayer](#game-social-and-multiplayer).)
- When the monster dies, the share of each character is `points^0.65 / Σ points^0.65`. The exponent makes the difference between strong and weak characters smaller.
- Each character with a share above 0.25% gets its **own** chest. The server makes the rolls with that share. The XP is `monster.xp × share × xpm`.
- For each 10 characters with a share above 0.08%, the server rolls the monster drop table one more time (`drop_table_multiplier`).
- Some monsters have the `1hp` flag. Each hit on them does 1 damage, for example on the Snowman and the Love Goo. For these monsters, each character gets a full roll, not a roll with its share.

### How a drop roll works

For each entry `[chance, item, ...]` in `G.drops.monsters[type]`, the item drops when this is true (`node/server.js:2325-2334`):

```
random() / (share × luckm × monster_level × monster_mult) < chance
```

- `share` is 1 for a usual kill. For a boss, it is the cooperative share.
- `luckm` is `1 + luck/100`, the luck multiplier of the character.
- `monster_level` is the current level of the monster. A monster that nobody kills slowly goes up in level. This multiplies its drop chances and its gold.
- An entry with a chance of 1 or more always drops. Boss tables use this. For example, Mr. Pumpkin always drops 5 Rare Candies and 10 Candies.

Map drops (`G.drops.maps[map]`) and global drops (`G.drops.maps.global`, for all monsters on all maps) use a different test: `random() / share / luckm / hp_mult / luckx < chance`. Here `hp_mult` is the maximum HP of the monster divided by 1000. Thus strong monsters give more map drops and global drops (`node/server.js:2288-2313`). `G.drops.maps.global_static` has no `hp_mult`. On PvP servers it holds the PvP token.

Examples from G 17478:

| Monster | Drops (chance for each kill at level 1, without luck) |
|---|---|
| Goo | Slime staff 1/5,000; Gooey slime 1/1,000; 50 shells 1/8,000,000 |
| Bee | Bee wings 1/100; Stinger 1/6,000 |
| Crab | Seashell 1/200; Reef glass 1/250; Crab claw 1/1,000 |
| Phoenix (cooperative) | Vitality scroll 70%; each stat earring 12%; each fire weapon 4%; Primling 1/600 |
| Ice Golem (event) | Frozen key, essence of frost, frost cores (always) |
| `main` map, all monsters | Ring of Small Joys 1/1,430; HP amulet and belt 1/1,670; Raw Emerald 1/14,000 |

`G.drops.monsters_home_server` adds more drops only for characters on their home server without Realm Fatigue (`node/server.js:2358-2370`). For example, Franky gives 10 bandages, and the Giga Crab gives 3 Reef Glass. The [`tracker`](#send-tracker) event of the Tracktrix sends the drop tables that the client can show.

### Luck

| Source of luck | Amount |
|---|---|
| Gear | The `luck` stat on items, the Lucky property (+2), set bonuses (`G.sets`) |
| Liquid Luck elixir (`elixirluck`) | +16 |
| Merchant's Luck buff (`mluck`, a merchant skill) | +12, for 1 hour |
| Party with members below level 60 | +10 for each of these members (`node/server.js:1187`) |
| Luck Booster | +20, and +8 for each level |
| Holiday Spirit (holiday season) | +20 |
| Easter Luck (a kill of the Wabbit) | +100 for 24 hours |
| Encouragement bonuses (new, returning or lone players) | Up to 5× luck on your own share (see the events chapter) |
| Hop Sickness | -80 |

Merchant's Luck has one more effect. The buffed character takes items from chests. For each item, there is a 2% chance that the merchant who gave the buff also gets a copy (`node/server.js:2080-2097`). The copy has the mark `m`.

### Chests

A kill with gold or items makes a chest. The server sends [`drop`](#recv-drop) with an `id` to the owner, or to the party members in the same instance. The look of the chest tells what it holds:

| Chest | Contents |
|---|---|
| `chest3` | Usual gold |
| `chest4` | Gold with the ×10 bonus |
| `chest5` | Gold with the ×50 bonus |
| `chest6` | Items or shells |

To open a chest, send [`open_chest`](#send-open_chest) `{id}`. The result is [`chest_opened`](#recv-chest_opened). The rules are (`node/server.js:11273-11470`):

- **The gold multiplier of the opener applies.** The multiplier is 1 if the opener is more than 400 px away (`dry`). It is also 1 if the chest is more than 8 minutes old (`stale`). Then the server takes the 10% tax.
- **Solo.** You must have space for all the items. If not, the open fails (`loot_no_space`).
- **In a party.** Each item goes to one member. The server selects the member at random from the members with space. The probability is proportional to the party share. Merchants have share 0, so they never get items this way. If no member has space, the item goes to the Lost and Found.
- **Gold in a party.** The server divides the gold by share. The gold of each member uses the multiplier of the opener.
- **Any chest id.** Any player who knows the id can open the chest. If the chest belongs to a different account, the server only writes "SEVERE - Cross Loot" to its log (`node/server.js:11306-11309`).
- **Old chests.** A chest that nobody opens for 48 hours disappears. Its gold goes to the gold pool, and its items go to the Lost and Found (`node/server_functions.js:693-713`).

The gold multiplier of the opener changes the gold of all party members. Thus a party often lets the character with the most gold gear open all chests. Open chests at once: after 8 minutes the gold bonus is lost.

**Starter bonus.** Some new accounts get a bonus on their first chest. The account must have a Steam or Mac App Store link, and it must be less than 100 hours old (`node/server.js:2428-2436`, `:16252-16279`). The bonus is 100,000 gold, three Rings of Small Joys, an HP belt and a Raw Emerald. An account with only an email and password does not get it.

### Shiny loot and marked loot

- An upgradable item from a chest has a chance of 1 in 500 to be `shiny`. A compoundable item has a chance of 1 in 20,000.
- On PvP maps and PvP servers, loot gets the `v` mark (the date). A character can lose marked items when it dies in PvP (see the next chapter).

## Events, bosses and seasons

The game also has content on a schedule and content at random. A bot must know about it, because it pays much more than usual monsters. The server shows live events in **S**, the object of server events ([What S is](#s-what-s-is)). [Event lifecycle](#s-event-lifecycle) gives the full timers. This chapter explains each event as game play.

The game adds content often. The list of releases is in `update_notes.js` in the live repository. This chapter describes the release of 2026-09-24 ("Rare Monsters, 15 Accessories and Trade Offers") and the releases before it.

### How to find and join an event

1. Read S. The server sends it in the `server_info` event and in `start` ([What S is](#s-what-s-is)). A key with `live: true` is a boss that is alive now. Most boss entries have `map`, `x` and `y`.
2. If the event has a `join` flag in `G.events`, send [`join`](#send-join) `{name}`. The server moves your character to the event.
3. If not, walk to the map and position in S.
4. If `join` fails with `no_merchants`, the character is a merchant. If it fails with `cant_when_sick`, the character has Hop Sickness.

### Daily and nightly events

Each game server has a schedule in the local time of its region (`S.schedule`, [schedule](#s-key-schedule)). The offset from UTC is +1 for EU, -5 for US and +7 for ASIA (`node/server.js:338-342`). At 13:00 and 20:00, the server starts the next **daily** event from a list. At 23:00, it starts the next **nightly** event (`node/server_functions.js:2386-2402`). Thus each server has two daily events and one nightly event each day.

| Event | Type | What happens | Rewards | Join |
|---|---|---|---|---|
| Giga Crab ([`crabxx`](#s-key-crabxx)) | daily | A large crab on the beach of `main` takes only 1 damage for each hit while its Huge Crabs are alive. The players must kill the Huge Crabs again and again. It lasts 40 minutes, or longer while players attack it | Funtokens (always some), seashells, crab claws | [`join`](#send-join) `"crabxx"` |
| Goo Brawl ([`goobrawl`](#s-key-goobrawl)) | daily | An island map with cooperative Brawl Goos. The server adds new goos all the time. 1% of new goos are a Rainbow Goo. It lasts 9 minutes | Funtokens, the drops of the Rainbow Goo | `join` `"goobrawl"` |
| A/B Testing ([`abtesting`](#s-key-abtesting)) | daily | PvP between two teams. Sign up with Bean ([`signup`](#send-signup)). The server puts you in team A or B. The score is kills. It lasts 8 minutes. There are no PvP penalties | The winners roll `G.drops.abtesting`, the losers `abtesting_loser`. 1,000 kills give the `abtesting` title on the orb | `join` `"abtesting"`, in the first 2 minutes |
| Franky ([`franky`](#s-key-franky)) | nightly | A boss in `level2w`. It calls weak mummies. It lasts 40 minutes, or longer while players attack it | Crypt keys, tomb keys, candy, Franky's pants | `join` `"franky"` |
| Ice Golem ([`icegolem`](#s-key-icegolem)) | nightly | A boss in `winterland`. It throws frost balls at all characters that attack it | Frozen key, essence of frost, frost cores | `join` `"icegolem"` |

While an event runs, [`join`](#send-join) moves you to it. Merchants cannot join. Characters with Hop Sickness cannot join.

### The Cave of Many Dreams

The Cave of Many Dreams (`G.events.dreams`) is a dungeon for a party of 1 to 3 characters. Each account gets 1 run each day. A run has 24 minutes and 3 floors. Monsters inside give 10× XP. A death inside costs no XP or gold.

The cave gives axes, scythes and Cave Amber. Leo crafts rare gear from Cave Amber. Cave rewards have the `cavefound` title. Some cave gold comes by mail.

To enter:

1. Bring all members of the party to Dorr (`dreamkeeper`) in `main`, within 160 px of (816, 1200).
2. Kill or leave all monsters that target a member. All members must be alive.
3. Send [`enter`](#send-enter) `{place: "dreams"}`.
4. Read the reply: `game_response` `{place: "enter", success: true, run, expires, level}`, or `failed: true` with a `reason`. The [`enter`](#send-enter) entry lists the reasons.

Inside the cave, the server sends the [`cave`](#recv-cave) event for choices and story text. A custom client needs more work here: each member must connect with the query parameter `map_protocol=1` ([`enter`](#send-enter)). The cave code is `node/logic/cave_of_many_dreams.js`.

### World bosses: how cooperative fights pay

All of these bosses are cooperative (see the previous chapter). A bot must decide three things:

- **Is the boss worth the time?** Bosses give very large XP: Franky 200M, Ice Golem 92M, Mr. Pumpkin 48M. The server divides the XP by contribution. Bosses also have rare drops.
- **Can the party stay alive?** The size of the contribution is not very important. The exponent `^0.65` gives a good share to small contributors. To stay alive is important. Join a live boss only if your healer can keep the party alive for a long time.
- **Home server bonus.** Characters get 5× points on their home server. To set the home server, send [`set_home`](#send-set_home) on that server (one time in 36 hours). Thus the home server is the best place for a bot to fight bosses.

The Rime Djinn in Frozen Cove is a newer cooperative monster. When one makes an ice shell, the players must break the shell together before it hits the party. It drops Rimeglass, and Leo crafts 3 items from it.

### Season events

A **season** is a holiday event that lasts some weeks. The operator of the game turns seasons on by hand. They are flags in the `events` object of the server (`node/server.js:302-327`). At the pinned commit, `anniversary` is on and the five holiday seasons are off. No code turns them on at a date.

When a season is on, its key is `true` in S ([`halloween`](#s-key-halloween), [`holidayseason`](#s-key-holidayseason), [`lunarnewyear`](#s-key-lunarnewyear), [`valentines`](#s-key-valentines), [`egghunt`](#s-key-egghunt)). Each season has an entry in `G.events`. When the server starts with a season on, it adds global drops for that season (`node/server_functions.js:267-292`).

| Season | More global drops | Bosses | Other changes |
|---|---|---|---|
| `halloween` | Candy 1/800, Rare Candy 1/20,000 | [Mr. Pumpkin](#s-key-mrpumpkin) (`halloween` map), [Mr. Green](#s-key-mrgreen) (`spookytown`), [Slenderman](#s-key-slenderman) (teleports on three maps) | The small bosses `jr` and `greenjr` come back each 8 minutes. Xyn exchanges candies for Halloween gear |
| `holidayseason` | Ornament, Mistletoe, Candy Cane, the "xN" puzzle pieces, Orb of Second Chances (1 in 100M) | [Grinch](#s-key-grinch) (teleports to characters at level 50 or more, takes their gold, heals itself), [Snowman](#s-key-snowman) (each hour, 1 damage for each hit) | All characters get Holiday Spirit (+20 luck, gold and xp) at their first login (`node/server_functions.js:4465`). The New Year tree in Winterland gives the buff again and a funtoken ([`interaction`](#send-interaction) `newyear_tree`). NPCs in Winterland take the drops. 400k damage on the Grinch gives the `festive` title on the cape |
| `lunarnewyear` | Brown Envelope 1/20,000; Old Paper Money 1 in 200M | [Dragold](#s-key-dragold) in `cave`, each 3 hours | Xyn exchanges envelopes, usually for gold. The code that makes the Tiger is a comment ([`tiger`](#s-key-tiger)) |
| `valentines` | Candy Pop 1/1,000. You can eat it, or exchange 10 at Xyn | [Love Goo](#s-key-pinkgoo) (`pinkgoo`), each hour in a random monster group. It avoids 98% of hits, and each hit does 1 damage | |
| `egghunt` | Golden Egg 1 in 200,000; Easter eggs 0.9% | [Wabbit](#s-key-wabbit), each hour in a random monster group | A kill gives Easter Luck (+100 luck for 24 hours). Nine eggs make a Basket of Eggs for Xyn |

Outside the holiday season, the Snowman also comes about one time each 20 hours (`node/server_functions.js:2630-2637`).

The season bosses come on a timer from `G.monsters[x].respawn`. In S, a boss shows first as `{live: false, spawn}` and then as live ([Event lifecycle](#s-event-lifecycle)). Most S entries for these bosses have `map`, `x` and `y`. Thus a client can go directly to the boss. The Love Goo and the Wabbit are in a random monster group, so their entries have no position.

### The anniversary event

The tenth anniversary ([`anniversary`](#s-key-anniversary), `node/logic/anniversary_event.js`) runs until the operator turns it off. It has three parts:

- **Drops.** All monsters can drop an Anniversary Gift (global chance 1/1,500) and a cake slice (1/50,000). Each account always finds the same one of six flavors (`sliceForAccount`, `node/logic/anniversary_event.js:20-24`). Trade with other players for the other five.
- **Kisses.** Every 30 minutes, each server that is not PvP selects one featured player. Other eligible players get an "Anniversary Visit" condition. They have 5 minutes to find the featured player and use the emote skill `ikissyou` on that player. The visitor and the featured player each get one slice and one Anniversary Gift. S shows the featured player in `anniversary`.
- **Cakes.** Bring one slice of each flavor and 100,000 gold to Mira (`anniversary_baker`) at (64, -88) in `main` for a Sixfold Cake. Xyn opens cakes and gifts. Mira also crafts 10 anniversary items.

Hop Sickness and Realm Fatigue block the kiss rewards. A merchant must be on its home server.

### Rare random monsters

Some monsters come from kill counters for the full server (`node/server_functions.js:2603-2627`). After the given number of kills of the usual monster, the server makes the rare one. The number is random in the range.

| Monster | Appears after about | Among |
|---|---|---|
| Golden Bat | 0-160,000 kills | bats |
| Cute Bee | 0-960,000 kills | bees |
| Golden Bot | 0-200,000 kills | targetrons and sparkbots |
| Many Eye | 0-30,000 kills | one-eyes (`oneeye`) |
| Mimic | 0-24,000 kills | kobolds |
| Pale Dino | 0-60,000 kills | dinos (`odino`) |

S does not show these monsters. Only the `announce` flag of the monster tells players about them. Only one Many Eye, Mimic or Pale Dino can be alive at a time.

### Monster hunts

A **monster hunt** is a quest that you can do again and again. Daisy (`monsterhunter`) in `main`, at (126, -413), gives them. The rules are in `node/logic/monster_hunts.js` and the handler at `node/server.js:5395-5436`.

1. Go to Daisy. Send [`monsterhunt`](#send-monsterhunt).
2. Read your conditions. The `monsterhunt` condition is `{id, c, ms, sn}`: kill `c` monsters of type `id` in `ms` milliseconds (30 minutes), on server `sn`. Kills by your party also count.
3. Kill the monsters on that server.
4. When `c` is 0, go back to Daisy and send `monsterhunt` again. You get 1 `monstertoken`.

Daisy selects the target from the **highest level of all characters of your account**:

- Below 30: 10 Goos.
- 30 to 59: the monster of the highest level among a list of easy monsters for your level (Bee at 30, Crab at 32, ... Bat at 56). The count is at most `10 + (level - 30) × 16`.
- 60 and more: the monster with the highest level on the server that nobody else hunts and that has no target. The count is `20 × 60 × spawns / (hp / 1000) / (respawn + 0.25)`, from 1 to 500. Then nobody else can get that monster for 20 minutes.

Merchants cannot get hunts (`monsterhunt_merchant`). At 60 and more, a hunt can be too difficult for your character. Then let it end. 4 tokens buy a Tracktrix, but each account already gets one by mail.

### Achievements

An **achievement** is a goal that the game records, often with a reward. `G.achievements` has 17 ([achievements](#g-achievements)) of three kinds:

- **Levels.** `reach40` gives a Tiny Ruby. `reach50` to `reach80` give 50-200 shells. `reach90` gives 20,000 shells. Where the server gives these rewards is unclear from the source.
- **Item counters.** When a count gets to its goal, the equipped item gets a **title**. Examples: `festive` (400k damage on the Grinch, cape), `abtesting` (1,000 A/B kills, orb), `gooped` (take 60M damage from Goos, pants), `stomped`, `firehazard`. The item itself keeps the count (`item_achievement_increment`, `node/server_functions.js:5846-5870`). The server sends [`achievement_progress`](#recv-achievement_progress) updates.
- **Special results.** For example `lucky` (an upgrade with an exact roll) and boss counts.

Each monster type also has **kill achievements** (`G.monsters[x].achievements`). For example, 10 Goo kills give +5 HP, and 100 give 10 more. These stat bonuses are permanent. But they apply only while the character carries a Tracktrix (`node/server.js:1484-1510`). Thus keep the Tracktrix in the inventory of each fighter.

The help page of the Tracktrix (`docs/guide/tracktrix.html`) gives the score:

- +1 for each kill by you or your party.
- +0.3 for each of your characters in your party or within 600 px.
- -0.3 for a kill more than 600 px from you, if your last kill was a different monster.
- -0.1 if a merchant of your party is within 600 px of the kill.

### The cavalry

The Tracktrix can call the **cavalry**. These are four NPC fighters: a warrior, a priest, a mage and a paladin. They help you against monsters near you (`node/logic/cavalry.js`). The settings are in `G.items.tracker.cavalry`:

- The monsters must be of level 3 or more, within 320 px, and attack you or your party.
- The help lasts 15 s. Then you wait `10 + level` minutes before the next call.
- A character below level 80 with no player of level 80 or more near it gets more help: up to 24 targets for 90 s.
- Kills by the cavalry count for the player who called it.

A client calls the cavalry with [`interaction`](#send-interaction) `{type: "cavalry"}`.

### Encouragement bonuses

New players, players who come back after 60 days, and accounts with only one fighter online get extra gold, XP and luck (`node/logic/encouragement.js`). [Bonuses for new and solo players](#game-leveling-and-progression) gives the multipliers. These rules matter for the economy:

- The extra loot follows your own contribution to each monster. It goes to you, not to the party or the chest opener.
- If your inventory is full, the extra loot waits in a chest that only that character can open.
- The bonuses do not change trades, NPC sales, fixed prizes or PvP.
- An account group with 25 or more characters gets no bonus.

### The tavern

The tavern is a map next to `main`. It has games of chance (`G.games`, [games](#g-games), `node/logic/tavern*.js`):

- **Dice.** Bet that a roll is above or below a number that you select. The payout odds are `100/num` (or `100/(100-num)`), minus the house edge. Bets are from 10,000 to 100B gold. See [`bet`](#send-bet) and [`tavern`](#send-tavern).
- **Fortune's Wheel.** 14 slices of Sun and Moon. Select a side. A win pays 2× the bet, minus the house edge on the win. The minimum bet is 10,000 gold.
- **Slots.** Each spin costs 1M gold. Prizes go from ale (1.2M) to a Glitch (1B, 6 in 30,000). The prizes average the stake. The house keeps only its edge from the net win.
- **Hold'em poker.** One table with 5 seats. The blinds depend on the server (100k/200k on I servers, up to 100M/200M on PvP). The house takes 2% of each pot, at most 10 big blinds.

The house edge is 0.5%-2%. It becomes smaller when the gold pool of the server becomes larger (`house_edge`, `node/server_functions.js:1384-1396`). On average, games of chance remove gold. The expected value is negative by the size of the house edge.

### PvP and duels

**PvP** (player versus player) means that characters can attack other characters.

> **Caution:** Before you go on a PvP map with valuable items, remember that marked items can drop at death.

- **Where.** On PvP servers (the `PVP` server name), PvP is everywhere. These servers also give ×1.15 luck, ×1.2 xp and ×1.25 gold (`node/server.js:416-423`). On all servers, maps with the `pvp` flag permit PvP. Examples are the Arena, A/B Testing and Duelland. Banks and some other maps are `safe`.
- **Losses.** The dead character loses some XP and some of the gold that it carries. The maximum gold loss is 100 at level 1 and 1M at level 75 or more (`node/server.js:2939-3005`). The killer gets 90% of the gold and 95% of the XP. If the killer is in a party, the party shares them.
- **XP loss amount.** The base is the larger of 1% of the XP for the level and 2% of the current XP, divided by 10.
- **Tome of Protection.** A character that carries an `xptome` loses 50× less XP. The tome is used up. The killer then gets 1.6M gold (`node/server.js:3029-3043`). Merchants lose no XP.
- **Marked items.** On PvP maps, items with the `v` mark can drop at death (`drop_something_pvp`, `node/server.js:2566-2597`). Each marked equipped item drops at 50% (30% for weapons). Each marked inventory item drops at 80% (50% for stacks). The items go into a chest that the killer can open.
- **Duels.** A duel is PvP with no risk. Send [`duel`](#send-duel) `challenge`, and the other player sends `accept`. Both parties go to a private `duelland` instance with no penalties. S lists active duels ([`duels`](#s-key-duels)). The server has a spelling error: the challenge comes as `event: "chellenge"` (`node/server.js:12212`).

### Server blessing

A player can spend 1,200 shells on [`bless_server`](#send-bless_server). Then the current server has a blessing for 3 days. All characters on it get Patron's Grace: +25% xp, +20% gold and +5 luck. S shows the blessing as [`blessed_minutes`](#s-key-blessed_minutes) and `blessed_by`. Favoré in `main` shows the price and the time that is left.

## Social and multiplayer

In AL, one person usually runs many characters. Thus "multiplayer" means your own characters together, and also other people. This chapter covers servers, parties, communication, and the rules for many characters.

### Servers and characters

- The servers are in regions (`EU`, `US`, `ASIA`). Their names are `I`, `II`, `PVP`, `HARDCORE` and others. All servers share the state of a character. A character that logs in on a different server continues from the same place (`docs/guide/limits.html`).
- Each character has a **home server**. The first server that the character enters becomes its home (`node/server_functions.js:1097-1099`). To change it, send [`set_home`](#send-set_home) on the new server (one time in 36 hours, `node/server.js:5523-5535`). Bean in `main` does this in the official client.
- **Hop Sickness.** A character of level 60 or more that enters a non-PvP server that is not its home gets this condition (`node/server_functions.js:1092-1104`). It gives -80 luck, gold and xp, and -20 output. It lasts 12 minutes of online play. A return to the home server clears it.
- **Realm Fatigue.** If another non-merchant character of the account was recently on a different server, a character gets Realm Fatigue for 30 minutes (`realmfatigue_logic`, `node/server_functions.js:1117-1159`). It blocks the home bonuses and the home drops. A return home does not clear it. Merchants do not get it.
- Characters on their home server also get 5× boss points and home drops. Thus keep all fighters of an account on one server.

### Parties

A **party** is a group of characters that share the rewards of kills. A party has a maximum of 9 members that are not merchants, and 10 names in total (`limits`, `node/server.js:256-260`).

To make a party, use the [`party`](#send-party) event:

1. Send `{event: "invite", name}` to a character, or `{event: "request", name}` to a member of a party.
2. The other side sends `accept` (for an invite) or `raccept` (for a request).
3. To go out of the party, send `leave`. A member can `kick` the members that joined after it.

The server sends [`party_update`](#recv-party_update) `{list, party}`. For each member, `party[name]` holds the `share`, level, position and the bonus percentages. [A party and a merchant](#learn-a-party-and-a-merchant) in the course shows the code.

**XP shares** (`issue_monster_award`, `node/server.js:2834-2866`). The server gives a usual kill to one party member. Then **each** party member on the server gets `round(monster.xp × xpm × share)`. The server does not test the distance or the map. A member far away also gets its share.

**The share** (`party_to_client`, `node/server.js:1138-1210`) is not equal for all members:

- Each member gives `pdps + 36,000`. The value `pdps` is a score of the recent damage, heals and hits taken by the member. It decreases by 20% each minute (`node/server.js:16096`). Priests count ×1.36.
- The server adds the values **for each account**. Then it divides the total of the account by the number of characters of that account in the party.
- `share = (total of the account / its number of characters) / total of the party`. The constant 36,000 gives a share to members that do nothing.
- **Merchants have share 0.** They get no kill XP. They do not make the share of other members smaller.

**Party bonuses** apply to all members (`node/server.js:1186-1188`, applied at `:1675-1685`):

| Bonus | Amount |
|---|---|
| XP | +10% with 2 members that are not merchants, +16% with 3, +20% / +24% / +25% / +30% / +36% with 4-8, +40% with 9 |
| Gold | +5% |
| Luck | +10 for each member below level 60 |

**Loot.** The party shares the chest of the member that gets the kill. Each item goes to one member by share, and the server divides the gold by share (see [Drops and loot](#game-drops-and-loot)). Party kills count for the monster hunts of all members. Cooperative bosses are different: their rewards follow the contribution of each character, not the party.

### Communication

| What | How | Notes |
|---|---|---|
| Public chat | [`say`](#send-say) `{message}`. All players on the server get [`chat_log`](#recv-chat_log) | Minimum 400 ms between messages. 15 s if the message has the code mark (`node/server.js:5099-5108`) |
| Party chat | `say` `{message, party: true}`. The party gets [`partym`](#recv-partym) | |
| Private message | `say` `{message, name}`. The target gets [`pm`](#recv-pm) | The server sends it to other servers if necessary |
| Code messages | [`cm`](#send-cm). The target gets [`cm`](#recv-cm) | Any data between the scripts of your own characters |
| Mail | [`mail`](#send-mail) | It has a fee. It goes to offline characters and can carry one item |
| Emotes | [`skill`](#send-skill) (an emote is a skill with `emote` in G) | |

### Friends

[`friend`](#send-friend) `request`, `accept` and `unfriend` change a list of friends on the backend. When you log in, your friends get an [`online`](#recv-online) notice (`notify_friends_emit`, `node/server_functions.js:451-459`). The item text of the Friend Token says that a friend who starts to play gives one token. Where the server gives the token is unclear from the source.

### Guilds

Guilds are only a stub:

- The account and character models have a `guild` field.
- An HTTP method lists the online characters of a guild (`pull_guild`, `api.js:944-952`).
- When the friendly fire mode is off, members of the same guild cannot hurt each other.

No socket event makes or joins a guild.

### Many characters and bots

AL is a programming game. To run characters with code is the normal way to play. It is not cheating.

The game has a code editor in the browser and a CODE API. Mainframe runs your CODE on the servers of the game. The guide tells how to run many characters (`docs/guide/multi.html`). The rules limit the number of characters, not the use of scripts.

> **Warning:** The rules below come from the official guide (`docs/guide/limits.html`, text in `languages/en/docs.js`). Read the guide on the live site before your bot depends on them.

The source and the rules of the game say:

- **Characters online at one time: 3 characters and 1 merchant** for each account. `is_player_allowed` enforces this on each game server (`node/server_functions.js:383-437`). Merchants do not count in the 3. But an account can have only one merchant online. The exact limit is in a private configuration file. See [Rate limits and anti-abuse](#guide-rate-limits-and-anti-abuse) for the tests.
- **IP addresses.** The server also limits the number of players from one IP address. Accounts that sign in through Steam or the Mac App Store have a much higher limit.
- **Licence to Kill.** A `licence` (25M gold at Crun) removes these limits for 7 minutes (`node/server.js:7818`). Its text says: "No one can bother you for having too many comrades in this realm!"
- **One account for each player.** All accounts of a player share the same limits. If you make accounts for other people, the system that enforces the limits can act on your accounts.
- **Each account must serve itself 80% of the time or more.** You can run the account of a different person. But if that account mainly helps your accounts, the game can ban all the accounts for up to one year.
- **Each account needs an active person.** Some accounts run 24/7 with no contact with other players. The game can ban them for a time. Social, active merchants prevent this. Contact with other players (for example on Discord) about one time each week also prevents it.
- **Other rules.** Do not sell game items for real money. Do not use offensive names, and do not bully. Do not use bugs: report them, and get a Bug Bounty Box. Do not send so many calls that it looks like an attack (`htmls/contents/terms.html`). [Rate limits and anti-abuse](#guide-rate-limits-and-anti-abuse) gives the limit of calls that disconnects a socket.

The mechanics also have effects on play with many characters:

- Your characters in one party share the share of one account.
- A merchant in the party does not decrease the XP of the fighters, and gets no chest items.
- A merchant near a kill decreases the Tracktrix kill score.
- Gold between your own characters has no fee.
- Two or more online fighters end the Lone Wolf bonus. Keep all fighters on one server, or Realm Fatigue blocks the home bonuses.
