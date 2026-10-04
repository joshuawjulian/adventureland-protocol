# Live capture: the probe plan

`tools/capture/` records every Socket.IO frame in and out of the owner's characters on **US V**
(SETYWarrior, SETYPriest, SETYMage, SETYMerchant; nothing else is allowed, see `session.ts`).
`scripts/check-captures.py` matches the frames to the documented shapes and writes
`schema/live.json`.

```sh
python3 tools/capture/run.py <stage>        # Docker node:22; captures/<date>/<time>-<stage>.jsonl
python3 scripts/check-captures.py           # match + validate, writes schema/live.json
python3 scripts/confirm-report.py           # coverage: code vs live
```

- **Login.** `/home/julian/dev/al/claude-bot-old/credentials.json` (`userID`, `userAuth`) is mounted
  read-only into the container. The token never goes on a command line, into an environment
  variable of the container, or into a file: `record.ts` replaces the `auth` field of the `auth`
  request and every occurrence of the token (and of the cookie value) with `<REDACTED>` before a
  line is written. `check-captures.py` also removes user ids (`US_...`) from the samples.
- **Call cost.** Characters send through the course's `Budget` (150 of the server's 200 per 4 s).
  The bare observer socket has its own budget of 40 (the server allows 50 before `auth`), and
  after any `game_error` (the server adds 16 for a handler that throws) the runner waits 4.2 s.
  Probes of one character are at least 300 ms apart.
- **Stops.** `disconnect_reason` (kick, `limitdc`), a `gm` event, or an unexpected close aborts
  the stage (`session.ts`, `ABORT_ON`). Ctrl-C closes every socket cleanly.

## Scope (owner, 2026-10-04)

At first the plan covered every client event (stages `observer` to `death` in `probes.ts`). Then
the owner narrowed it: *"You don't need to live confirm if the code is good enough."* Since then,
only shapes whose `confirm` has `live_needed` are probed (the `targeted` stage). The other stages
stay in `probes.ts` as a ready plan, but **only the stages marked "ran" have been run**.

| Stage | Ran | What it does | Cost |
|---|---|---|---|
| `status` | yes | HTTP only: list the characters | none |
| `look` | yes | connect, print state, idle 10 s | none |
| `observer` | yes | a socket with `loaded` and no `auth`: the observer events, and the "No character" row of each handler that answers it; `auth` refusals (not an object; unknown character id); dead handlers | none |
| `targeted` | yes | the `live_needed` shapes that a normal account can reach (table below) | sold 1 `hpot1` (+60 gold); bought 5 `frogt` from Ponty (20 gold) |
| `fight` | yes | the three fighters fight gscorpions where they stand (150 s), then open the chests | potions; the mage looted 12,834 gold |
| `safe` | no | idle, ping, players, send_updates, property, a party of four (invite/accept/request/raccept/kick/leave and their failures), attack/heal and their failures, potions, chests | potions |
| `desert` | no | desertland NPCs: locksmith, scrollsmith (`destat`), Rook (`citizen_route`); the distance failures of main-only NPCs | none (no gold, so the paid paths fail) |
| `gather` | no | `town`, `stop`; the fighters go to main | none |
| `shop` | no | buy/sell/split/imove/send/destroy/throw/equip/unequip/equip_batch/activate/booster/convert/merge; upgrade a +0 `helmet` with `scroll0`; compound 3 `test_orb` with `cscroll0`; exchange one `anniversarygift`; monsterhunt; dismantle/craft failures | about 9,700 gold |
| `stand` | no | the merchant's stand; listings, wishlist, swap offer and giveaway of `test_orb`s, bought, sold and swapped by our own warrior | a few gold |
| `bank` | no | transport into the bank; deposit/withdraw 1 gold; store/move/retrieve one potion; unlock failures | none |
| `social` | no | say (party/private/public), cm, friend, magiport (mage to priest), skills and their failures, tavern/poker info, donate 1 gold, lost and found, secondhands, signup, mail failure, cx, interaction failures, join/enter/leave failures, set_home; `bless_server` and `buy_with_cash` with prices above the account's 600 shells (the payment fails later, so nothing is spent) | 1 gold |
| `duel` | no | warrior challenges mage; mage accepts; the mage walks out after the start (a duel saves and restores the state) | none |
| `jail` | no | a `move` with a wrong `m`; a move into a wall (jail), then `leave` | none |
| `death` | no | `harakiri` once on the level-7 merchant; `respawn` too early, then `respawn` | the death penalty of a level-7 character |

## The targeted probes (the `live_needed` shapes)

| Shape | Probe | Result |
|---|---|---|
| `send/pets/response/Success` | `pets` | confirmed |
| `send/interaction/variant/merrit_info/response/Market patron` | `interaction {type: "merrit_info"}` | confirmed |
| `send/interaction/variant/cavalry/failure/1` | `interaction {type: "cavalry"}` (no `tracker`) | confirmed |
| `send/interaction/variant/cavalry/response/Cavalry` | the success needs a `tracker` and a fight the cavalry accepts | not reached |
| `send/interaction/variant/cave/response/Cave visit` | `interaction {type: "cave", action: "info"}` | confirmed |
| `send/interaction/variant/cave/response/Cave state`, `Cave chat`, `also/2`, `type/CaveLimits`, `type/CaveShop` | need an open Cave of Many Dreams run (one opening per account per day, a party of up to 3 at (816, 1200) on main) | not run |
| `send/bless_server/response/Result#with` | `bless_server {request_id}` with 600 shells: `data`, then `blessed_fail` and `bless_result` | confirmed |
| `send/bless_server/response/Result#without` | `bless_server {}`: `data`, then `blessed_fail`, but no `bless_result` | not seen (the docs say it comes only with `request_id`, so this form may never come) |
| `send/bless_server/response/Blessed` | needs 1,200 shells spent (the account has 600) | not run |
| `send/buy_with_cash/response/Complete` | needs shells spent (the cheapest cash item, `cosmo2`, is 129 shells) | not run: ask the owner first |
| `recv/ui/variant/Sale to an NPC`, `type/UiNpcSell` | `sell` one `hpot1` next to `basics` | confirmed |
| `recv/ui/variant/Secondhands or lost and found`, `type/UiResale` | `sbuy` of the cheapest Ponty listing (cap 3,000 gold) | confirmed |
| `send/open_chest/response/Opened` | a gscorpion kill, then `open_chest` | confirmed |
| `send/open_chest/also/5` | an announced (rare or shiny) drop: chance | not seen |
| `send/open_chest/also/6` | a chest with encouragement receipts of another account | not testable alone |
| `send/eval/also/1` | `eval` on `cyberland` with spares on the server | not run |
| `send/disconnect/also/5` | a disconnect while seated at poker (needs a buy-in of 40 big blinds, 4,000,000 gold or more) | not affordable |
| `send/o:home/also/1` | an observer that follows a character in a dream cave run | not testable (needs the `secret` handshake) |
| `send/interaction/variant/dailytask/response/Daily task` | G 17478 has no `dailytask` ref | impossible |
| `send/gm/variant/ban/response/Ban`, `send/ureward/failure/6` | GM only; a database error | impossible |

## Not live-testable (any stage)

| Event | Why |
|---|---|
| `gm`, `shutdown`, `notice`, `render`, `eval` with `pass` | GM or admin only (`role: "gm"` or `keys.ACCESS_MASTER`). Not sent. |
| `error`, `disconnect` | Reserved Socket.IO event names; `disconnect` runs when the socket closes and sends nothing back to it. |
| `o:home`, `o:command` (success) | Need an observer that follows a character (the `secret` handshake of the official client). The failure rows were sent from the observer socket. |
| `creward` (success), `ureward` (success), `join_giveaway` (success) | Need `auth_id` (a Steam or Mac App Store login) or a verified account. |
| `whistle`, `pet` (success) | Dead code: `pet` never makes a monster, so `whistle` always fails. |
| `blend`, `deepsea`, `unlock`, `play`, `requested_ack` | The handler does nothing (sent once from the observer: nothing came back). |
| `bet` (slots), `poker` (seat) | 1,000,000 gold a pull; 40 big blinds a seat. More than the account has. |
| `mail` (success), `locksmith` lock/seal/unlock (success) | 48,000 and 250,000 gold. More than the account has. |

## How frames are matched (`scripts/check-captures.py`)

- Outgoing frame: `send/<event>/request` and the variant's request. A probe that aims at a failure
  row sends a wrong request on purpose; that is not reported as a request mismatch.
- Incoming frame: `recv/<event>/payload` and the first variant whose `has` keys and type fit.
  The hitchhikers of `player` count as frames of their own.
- `game_response`: credited to the most recent request on that character whose shapes take the
  code (and whose event, skill name or `type` is the `place`). When the probe named the shape
  ids it meant (`expect`), only those are credited; else every candidate that validates.
- Any other reply event: credited to the most recent request within 1.5 s that lists that event.
  `action`, `player`, `hit` and other broadcasts can come from other causes in that window, so
  the `also` counts are approximate. The payload check is exact.
- Validation is apischema's `payload_errors` (strict: missing, undeclared and wrongly typed fields).
- `unmatched` in `live.json`: events without a schema, and codes that no shape of the request has
  (doc gaps).
