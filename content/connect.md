# Connecting to Adventure Land

Source paths are relative to the live game's repository (`kaansoral/adventureland_mongodb`). Paths that start with `common:` are in its shared engine (`kaansoral/common_engine`).

## Overview

Adventure Land has two kinds of server:

1. **The website and HTTP API** at `https://adventure.land`. It is an Express app on MongoDB (main.js:1-91). It handles these jobs:
   - accounts (login, signup, auth tokens),
   - the character list and the server list,
   - mail, chat history and saved CODE,
   - the game data `G` (`/data.js`),
   - the token JSON API (`/mcp_api/<method>`) and the MCP server (`/mcp`).
2. **Game servers.** Each one is a Node.js process that runs `node/server.js <server key>`. The key selects a server definition from the private config (node/server.js:15-20). Each process serves one realm, for example `EU I` or `US PVP`. At startup it writes its own document `SR_<region><name>` to MongoDB, with `address`, `path` and `msgpack_path` (node/server.js:428-462).

The game server checks your login itself. When you send `auth`, it reads your user and character from MongoDB in one transaction (node/server.js:11608-11635). It does not call the HTTP API for this.

Steps from nothing to "my character is in the world and I can act":

1. Send `POST /api/signup_or_login` with JSON `{"email":..,"password":..,"only_login":true}`. Keep `user` and `auth` from the reply (api.js:120).
2. Send `POST /api/servers_and_characters` with the cookie `auth=<user>-<auth>`. Read `servers` and `characters` from the `infs` array (api.js:451-472).
3. Send `GET /data.js`. Remove the `var G=` prefix and the `;` suffix to get the game data JSON (web_assets.js:52).
4. Open a Socket.IO v4 WebSocket to `wss://<address>` with the server's `path` (node/server.js:81-87). Add the query `map_protocol=1`.
5. Wait for the `welcome` event (node/server.js:5019).
6. Send `loaded`. It makes the socket an observer. The server ignores `auth` until it receives `loaded` (node/server.js:11583-11585).
7. Send `auth` with `{user, character, auth}` (node/server.js:11563-11573).
8. Wait for `start` (success) or `game_error` / `disconnect_reason` (failure) (node/server.js:11944, 11640-11649, 11915).
9. Send game events (`move`, `attack`, `use`, ...). Listen for `player`, `entities`, `game_response` and the other events. Stay under the call-cost limit (see Rate limits). Socket.IO's own ping and pong keep the connection open. The game needs no other heartbeat.

## HTTP API

### Transport and encoding

The API has one dispatcher, `handle_api_call` (common:handlers.js:34-150). Two routes reach it:

| Route | How the server finds the method | How the server finds the arguments | Source |
|---|---|---|---|
| `/api/<method>` | the URL segment | the JSON or form body (POST), or the query string (GET) | common:handlers.js:1, 39 |
| `/api` | the body field `method` (or the query field) | the body field `arguments`, a **JSON string**, which replaces the body | main.js:875-888 |

- Send `Content-Type: application/json` or `application/x-www-form-urlencoded`. The app parses both (common:init.js:89-90). The official browser client posts JSON to `/api/<method>` (js/functions.js:19-25).
- On `/api`, the server parses `arguments` only when it is a string. If `arguments` is a JSON object, the body keeps the fields `method` and `arguments`. The validator then rejects the call with `invalid_field` (main.js:879-884, common:handlers.js:71-79).
- `/api` without a method replies HTTP 400 `{"failed":true,"reason":"no_method"}` (main.js:887).

Every method has a field list in `REF` (api.js:2150-2430, plus mcp_api.js:3036-3070 and common:admin.js:75). The dispatcher checks the call in this order, and stops at the first failure (common:handlers.js:42-140):

| Check | Reply |
|---|---|
| The method is not in `REF` | `{"failed":true,"reason":"invalid_call","name":<method>}` |
| The body has a field `F` with a true value | `{"failed":true,"reason":"invalid_field","field":"F"}` |
| The method has `P` and the request is not POST | `{"failed":true,"reason":"invalid_method","method":<verb>,"needed":"POST"}` |
| The method has `U` and the cookie gives no user | `{"failed":true,"reason":"not_logged_in","method":<verb>}` |
| A field is not in the method's list | `{"failed":true,"reason":"invalid_field","field":<name>}` |
| A `string` field is too short | the same, plus `minimum_length` (or `exact_length`) |
| An `email` field is not a valid email | the same, plus `not_email: true` |
| A `boolean` field is not JSON `true` or `false` | the same, plus `must_be: "boolean"` |
| A `number` field is not a number | the same, plus `must_be: "number"` |
| A required field is missing | `{"failed":true,"reason":"missing_field","field":<name>}` |
| The method throws | `{"failed":true,"reason":"exception"}` |

The argument types of `REF`, and what the dispatcher does with each value (common:handlers.js:72-127):

| Type | Accepted | Conversion |
|---|---|---|
| `string` | any value | `"" + value`. A number becomes its digits, `null` becomes `"null"`, and an object becomes `"[object Object]"`. `minimum` sets a minimum length. |
| `email` | a value that `purify_email` accepts | `"" + value`, then the purified email |
| `boolean` | JSON `true` or `false` only | none |
| `number` | a value with `isNaN(value)` false, for example `12` or `"12"` | none: the string `"12"` stays a string |
| `any` | any value | none: the method converts it, as the tables below say |

**Note:** In a form-encoded body, `true` arrives as the string `"true"`. Boolean fields such as `only_login` then fail with `must_be: "boolean"`. A JSON body, or the `/api` form with a JSON `arguments` string, carries real booleans.

### Response envelope

All API replies are HTTP 200 with a JSON object (common:handlers.js:28-32). The object is the method's result, for example `{"success":true}` or `{"failed":true,"reason":"..."}`. If the method added UI items, the server puts them in an `infs` array on the same object (common:handlers.js:30). The browser runs each item through `handle_information` (js/functions.js:6573).

The `infs` item types:

| `type` | Fields | Sent by | Source |
|---|---|---|---|
| `message` | `message` (HTML), `color` (optional) | most methods | api.js:118, 1476 |
| `success` | `message` (HTML) | methods that change the account | api.js:207, 258 |
| `chat_message` | `message` (HTML), `color` | `save_code`, `load_code` | api.js:1477, 1500 |
| `eval` | `code` (JavaScript for the browser client) | `signup_or_login` (wrong password), `quote_name`, `save_code` | api.js:122, 717, 1475, 1480 |
| `refresh` | – | `signup_or_login` with `mobile` | api.js:115 |
| `content` | `html` (the character selection HTML) | the account and character methods | adventure_functions.js:1627-1644 |
| `servers_and_characters` | see `servers_and_characters` | `servers_and_characters` | api.js:461-470 |
| `reload` | `address`, `path` | `can_reload` | api.js:908 |
| `mail` | `mail`, `more`, `cursor`, `cursored` | `pull_mail` | api.js:1252, 1296 |
| `messages` | `messages`, `more`, `cursor`, `cursored`, `mtype` | `pull_messages` | api.js:1317, 1358 |
| `unread` | `count`: the number of unread mails | `pull_mail`, `read_mail`, `delete_mail` | api.js:1246, 1297, 1308 |
| `friends`, `guild`, `merchants` | `chars` | `pull_friends`, `pull_guild`, `pull_merchants` | api.js:940, 965, 996 |
| `code` | `code`, `run`, `slot`, `save`, `name`, `v` (`name` and `v` only for a saved slot); from `load_gcode`, only `code` and `run: true` | `load_code`, `load_gcode` | api.js:1498, 1513, 2125 |
| `code_info` | `num` (the slot, as text), `name`, `v` (the version); or `num`, `delete: true` | `save_code` | api.js:1474, 1479 |
| `code_list` | `purpose` (the argument, echoed), `list`: `{<slot>: [name, version]}` | `list_codes` | api.js:1538 |
| `libraries` | `default_code`, `runner_functions`, `runner_compat`, `common_functions`: each the text of a JavaScript file | `load_libraries` | api.js:1525-1531 |
| `gcode` | `code`: the text of a file under `docs/` | `load_gcode` without `run` | api.js:2126 |
| `article` | `html`, `url`, and by branch `tutorial` + `track`, `guide` + `prev` + `next`, or `func` | `load_article` | api.js:2082-2117 |
| `tutorial_data` | the tutorial state (see `tutorial`), `track` (optional), `success: true` (optional), `next: true` (optional) | `tutorial`, `reset_tutorial` | api.js:1598-1603, 1628-1632 |
| `func` | `func: "stripe_result"`, `args`: `["success", <shells of the account after the payment>]`, `["failed"]` or `["declined"]` | `stripe_payment` | api.js:1965, 1995, 2033, 2037 |
| `map` | `data`: the map data of a resort map | `load_map` | api.js:2136 |

The `message` texts are HTML that the server makes with `phrase_html` (languages/index.js:252-254).

### Auth

- **The cookie.** `get_user` reads only a cookie (adventure_functions.js:371-389). The cookie name is `options.cookie_key`, which is in the private config. The tests use `auth` for production and `dev_auth` for development (node/test/auth_cookies.test.js:53).
- **The value** is `<user id>-<token>`. The server removes double quotes, splits at `-`, and adds the `US_` prefix to the id if it is missing (adventure_functions.js:366-369, 367-369).
- **The token** is 32 random bytes as 64 hex characters (adventure_functions.js:332). It is valid while it is in the user's `info.auths` list (adventure_functions.js:381).
- **Each login adds one token.** When the list already has 200 tokens, the server clears the whole list first. This logs out all older sessions (adventure_functions.js:331-341).
- **The cookie options:** path `/`, domain `.adventure.land`, max-age 5 years, `sameSite: lax`, and `secure` from the config (adventure_functions.js:1648-1656).
- The game pages also put the user id and the first token in the page as `user_id` and `user_auth` (htmls/base_script.html:7).
- `logout_everywhere` empties `auths`. It fails with `inthebank` while the account is in a bank (api.js:389-409).

#### Token lifetime and reuse

| Fact | Value | Source |
|---|---|---|
| Where a token is accepted | The `auth` cookie on every HTTP method marked "user", and the `auth` field of the socket [`auth`](#send-auth) event | adventure_functions.js:371-389 |
| Cookie value | `<user id>-<token>`; the `US_` prefix on the user id is optional | adventure_functions.js:366-369, 367-369 |
| Expiry | None by time. Valid while the token is in the account's `info.auths` list | adventure_functions.js:381 |
| New tokens | Each `signup_or_login` and each Steam sign-in adds one. Older tokens stay valid | adventure_functions.js:331-341, steam_signin.js:198-199 |
| Limit | 200 tokens. The login that would add the 201st clears the whole list first | adventure_functions.js:331-341 |
| Revocation | `logout_everywhere` empties the list | api.js:389-409 |
| Invalid or revoked token | HTTP methods reply `{failed: true, reason: "not_logged_in"}` | common:handlers.js:66 |
| API token (`mcp_...`) | A different credential, for the [token JSON API](#guide-token-json-api) only. Not accepted by the game socket | mcp_api.js |

### Endpoint list

The "Who" column:

- **user**: needs the auth cookie (`U` in `REF`).
- **public**: no cookie needed.

All methods except `get_servers`, `test` and `hi` need POST.

The Arguments column gives each field as `name: type` from `REF`. A `?` marks an optional field. The types are in "Transport and encoding". The Failures column gives the `reason` values of `{"failed":true,"reason":...}` that the method itself returns, in check order. The dispatcher failures (`not_logged_in`, `invalid_field`, `missing_field`, `exception`) apply to all methods. "tx" means a reason from the database transaction.

Many methods add the same two `infs` items on success: a `message` or `success` item, then a `content` item with the new selection HTML. The Result column writes this as "message + selection".

#### Account and login

| `method` | Who | Arguments | Result and `infs` | Failures | Source |
|---|---|---|---|---|---|
| `signup_or_login` | public | `email`: email; `password`: string (min 1); `only_login?`: boolean; `only_signup?`: boolean; `mobile?`: boolean | `{success, user, auth, language}`; sets the cookie; message + selection (with `mobile`: only `refresh`). See "Login" below | `cant_login_inside_bank`, `cant_signup_on_web`, `login_failed` (or a tx reason), `wrong_password`, `no_email`, `email_not_found`, `already_signed_up`, `too_many_signups_from_ip_wait`, `email_exists` (tx) | api.js:84-221 |
| `logout` | public | – | `{success: true}`; deletes the auth cookies and the Steam sign-in flow; message | – | api.js:382-387 |
| `logout_everywhere` | user | – | `{success: true}`; empties `auths` and `steam_auths`, makes a new `steam_auth_revision`, deletes the cookies; message | `inthebank`, tx | api.js:389-409 |
| `generate_token` | user | – | `{success, token, rotated}`: a new API token (`mcp_...`). `rotated` is true when an old token was replaced. `Cache-Control: no-store` | `token_generation_failed` | api.js:411-425, mcp_api.js:200-243 |
| `token_status` | user | – | `{success, active, recoverable, created, server_url, start_resource}`. `server_url` is `https://adventure.land/mcp`; `start_resource` is `adventureland://guide/start-here` | – | api.js:427-431, mcp_api.js:245-258 |
| `reveal_token` | user | – | `{success, token, server_url, start_resource}` | `token_not_found`, `token_unavailable` | api.js:433-443, mcp_api.js:260-272 |
| `revoke_token` | user | – | `{success, revoked}`. `revoked` is false when there was no token | `token_revoke_failed` | api.js:445-447, mcp_api.js:274-288 |
| `settings` | user | `setting`: string; `value?`: any | `setting: "language"`: `{success, language}`, no `infs`. Other settings: `{success: true}`, success + selection | language: `invalid_language`, `not_logged_in`. Others: `cant_make_changes_while_in_bank`; `steam_login`: `invalid_field`; tx | api.js:223-261, languages/index.js:108-116 |
| `change_email` | user | `email`: email | `{success: true}`; sends a new verification email; success + selection | `invalid_email`, `email_might_be_registered`, `email_already_verified`, `cant_make_changes_while_in_bank`, `change_email_once_every_18_hours`, `email_exists` (tx), `operation_failed` | api.js:263-303 |
| `change_password` | user | `epass`: string (min 1); `newpass1`: string (min 1); `newpass2`: string (min 1) | `{success: true}`; makes a new `steam_auth_revision`; success + selection | `cant_make_changes_while_in_bank`, `wrong_password`, `passwords_dont_match`, tx | api.js:305-327 |
| `password_reminder` | public | `email`: email | `{success: true}`; emails a `/reset/<uid>/<key>` link; success | `invalid_email`, `email_not_found`, `cant_make_changes_while_in_bank`, `already_sent_reminder_recently` (24 h), tx | api.js:353-380 |
| `reset_password` | public | `id`: string (the `<uid>` of the reset link); `key`: string (the `<key>`); `newpass1`: string (min 1); `newpass2`: string (min 1) | `{success: true}`; turns off Steam sign-in for the account; success | `passwords_dont_match`, `invalid_key`, `cant_make_changes_while_in_bank`, tx | api.js:329-351 |

The values of `settings` (api.js:223-261):

| `setting` | `value` | Effect |
|---|---|---|
| `"language"` | a language code (see "Phrases") | Saves the language of the account. A code not in the list gives `invalid_language` |
| `"email"` | any | A true value turns emails on. A false or absent value sets `info.dont_send_emails` |
| `"steam_login"` | boolean | Turns Steam sign-in on or off. The request must be a POST with an `Origin` header of the site, and exactly one auth cookie. Anything else gives `invalid_field` (steam_signin.js:208-225) |
| any other text | any | Nothing changes. The reply is a success |

**Note:** `change_password` accepts the stored password hash as `epass`, as well as the password (api.js:309).

#### Characters and servers

| `method` | Who | Arguments | Result and `infs` | Failures | Source |
|---|---|---|---|---|---|
| `servers_and_characters` | user | – | `infs`: `{type:"servers_and_characters", servers, characters, tutorial, merchant_tutorial, code_list, mail, rewards}`. See below | – | api.js:451-472 |
| `get_servers` | public, GET or POST | – | `{success, servers:[{address, path, msgpack_path, region, name, pvp, gameplay}]}` | – | api.js:884-900 |
| `can_reload` | user | `region`: string; `name`: string; `pvp?`: any (not used) | `{success, reload}`; if `reload`, `infs`: `{type:"reload", address, path}` | – | api.js:902-913 |
| `load_bank` | user | – | `{success, gold, packs:{items0..items47}}`, at most 42 slots per pack. A pack that is not an array is left out | – | api.js:73-81 |
| `create_character` | user | `name`: string; `char`: string; `look?`: any (`parseInt(look) \|\| 0`) | `{success: true}`; message + selection | `character_type_not_allowed`, `invalid_look`, `please_enter_a_name`, `invalid_name`, `name_used`, `cant_make_changes_while_in_bank`, `too_many_characters_from_ip`, `cant_create_more_than_18`, `reached_character_limit`, `character_exists` (tx), `creation_failed` | api.js:474-589 |
| `delete_character` | user | `name`: string | `{success: true}`; also deletes the CODE slot of the character; message + selection | `no_character`, `not_owner`, `character_in_game`, `cant_make_changes_while_in_bank`, `wait_<N>_minutes`, tx, `something_went_wrong` | api.js:784-835 |
| `rename_character` | user | `name`: string; `nname`: string | `{success: true}`; two messages (the cost, the new name) + selection | `no_character`, `not_owner`, `character_in_game`, `rename_once_every_32_hours`, `invalid_name`, `name_used`, `cant_make_changes_while_in_bank`, `not_enough_shells`, `duplicate_click` (tx) | api.js:639-699 |
| `quote_name` | user | `name`: string; `nname`: string | `{success: true}`; the price is only in an `eval` item: `show_alert('Costs <N> shells')` | `invalid_name`, `name_used` | api.js:701-719 |
| `transfer_character` | user | `name`: string; `id`: string (the user id of the receiver); `auth`: string (the `transfer_auth` of the receiver) | `{success: true}`; costs 500 shells; message + selection | `no_character`, `not_owner`, `character_in_game`, `receiver_not_found_or_wrong_auth`, `cant_make_changes_while_in_bank`, `not_enough_shells`, `duplicate_click` (tx), `something_went_wrong` | api.js:721-782 |
| `sort_characters` | user | `characters`: string, the character names separated by commas | `{success: true}`; message + selection | `something_went_wrong` | api.js:591-637 |
| `edit_character` | user | `name`: string; `operation`: string | `{success: true}`; message (its text tells the new privacy) + selection | `no_character`, `not_owner`, `character_in_game`, `something_went_wrong` | api.js:837-866 |
| `disconnect_character` | user | `name`: string; `selection?`: boolean | `{success: true}`; message, + selection when `selection` is true | `no_character`, `not_owner`, `character_not_in_game` | api.js:868-880 |

Rules of the character methods:

| Rule | Value | Source |
|---|---|---|
| Classes for `char` | `warrior`, `paladin`, `mage`, `priest`, `rogue`, `ranger`, `merchant` | design/game_design.js:1, api.js:480 |
| `look` | An index into `classes[char].looks`. An index at or past the end gives `invalid_look` | api.js:478, 481 |
| New name (`create_character`) | The server removes spaces and tabs. Then 4 to 12 characters from `a-z`, `A-Z`, `0-9` and `_` | api.js:24-31, 483-484; adventure_functions.js:452 |
| New name (`rename_character`, `quote_name`) | 1 to 12 characters from the same set | api.js:33-40, 649, 705 |
| Character slots | 5 free slots, or 8 for an account with a Steam id (`pid`); the account's `slots` can raise this, to at most 18 | adventure_functions.js:164-168 |
| Slots after signup | 8 for a signup from the desktop clients or Steam, 5 from the web | api.js:192 |
| A character past the free slots | 200 shells; it adds one slot | api.js:14-22, 560-563 |
| Characters from one IP | `too_many_characters_from_ip` after more than 12 | api.js:15, 491 |
| Rename price | 1 character: 160,000 shells; 2: 48,000; 3: 24,000; 4: 2,400; 5 or more: 640 | api.js:653-661 |
| Delete and transfer | Both set `last_delete`. A delete within 180 minutes of the last one gives `wait_<N>_minutes`, where `N` is the minutes left | api.js:750, 793, 824 |
| `transfer_auth` | 10 random characters. `sort_characters` makes a new one. The selection page shows it to the receiver | api.js:626, htmls/contents/selection.html:171 |
| `sort_characters` order | The listed characters first, in the given order. Characters that are not in the list follow, in their old order. The account name becomes the first character that is not private | api.js:595-627 |
| `edit_character` operations | Only `"toggle_privacy"` changes something. Another value saves the character unchanged and replies with success | api.js:850, 858 |
| "In game" | The character has a `server` value | adventure_functions.js:1001-1004 |

#### Mail, messages and chat

| `method` | Who | Arguments | Result and `infs` | Failures | Source |
|---|---|---|---|---|---|
| `pull_mail` | user | `cursor?`: any (an offset; `max(0, parseInt(cursor) \|\| 0)`) | `infs`: `{type:"mail", mail, more, cursor, cursored}`, 40 per page, then `{type:"unread", count}`. See "Mail" below | – | api.js:1250-1299 |
| `read_mail` | user | `mail`: string (the mail id; the `ML_` prefix is optional) | `{success: true}`; `infs`: `{type:"unread", count}` | tx | api.js:1232-1248 |
| `delete_mail` | user | `mid`: string (the full mail id, `ML_...`) | `{success: true}`; `infs`: `unread`, then a message | `cant_delete` | api.js:1301-1312 |
| `pull_messages` | user | `type?`: string (default `"all"`); `cursor?`: any (an offset; `parseInt`) | `infs`: `{type:"messages", messages, more, cursor, cursored, mtype}`, 200 per page | – | api.js:1314-1362 |
| `pull_chat` | public; a private conversation needs the cookie | `server?`: string (a server id, `SR_...`); `character?`: string; `to?`: string; `cursor?`: string; `after?`: string | `{success, messages, more, cursor, after}`, 80 per page | `invalid_cursor`, `server_not_found`, `not_logged_in`, `invalid_name` | api.js:1037-1075 |
| `pull_chats` | user | `cursor?`: string; `after?`: string | `{success, chats, more, cursor, after, characters}`, 40 conversations per page | `invalid_cursor` | api.js:1099-1165 |
| `send_message` | user | `character`: string (your character); `message`: string; `server?`: string (a server id, for a public message); `to?`: string (a character name, for a private message) | `{success: true}`. The game server sends the line | `banned`, `invalid_message`, `invalid_name`, `not_owner`, `character_not_found`, `message_self`, `server_not_found`, `chat_unavailable`, `muted`, `chat_slowdown`, `wrong_server` | api.js:1168-1230, node/logic/chat.js:60-140 |
| `pull_friends` | user | – | `infs`: `{type:"friends", chars}` | – | api.js:917-942 |
| `pull_guild` | user | – | `infs`: `{type:"guild", chars}`. An account without a guild gets `{success: true}` and no `infs` | – | api.js:944-967 |
| `pull_merchants` | user | – | `infs`: `{type:"merchants", chars}` | – | api.js:969-998 |

The fields of the items:

| Item | Fields | Source |
|---|---|---|
| `messages` item (`pull_messages`) | `fro`, `to`, `message`, `type`, `id`, `server`, `date` (ISO 8601 without milliseconds). All values are strings | api.js:1345-1355 |
| `messages` item (`pull_chat`), `latest` (`pull_chats`) | `id` (`MS_...`), `fro`, `to` (an array of names), `message`, `type`, `server`, `date` (ISO 8601) | api.js:1002-1012 |
| `chats` item (`pull_chats`) | `{type: "private", character, to, latest}`: one per pair of characters, newest first. On the first page (no `cursor`), also one `{type: "server", server, latest}` per game server; `latest` can be `null` | api.js:1139-1152, 1077-1097 |
| `characters` item (`pull_chats`) | `name`, `online` (boolean), `server` (`""` when offline); at most 100 | api.js:1106-1110, 1160-1162 |
| `chars` item (`friends`, `guild`) | `name`, `level`, `type`, `afk`, `owner_name`, `owner`, `server`. Only online characters that are not private | api.js:927-934, 952-959 |
| `chars` item (`merchants`) | `name`, `level`, `afk`, `skin`, `cx`, `stand`, `x`, `y`, `map`, `server`, `slots: {"trade<N>": item}`. Only online merchants with a stand | api.js:976-993 |

Rules of the chat methods:

| Rule | Value | Source |
|---|---|---|
| `pull_messages` `type` | `"all"`: all messages of the account. `"private"`, `"party"`: that type. Any other value `X`: the public channel `"~X"`, for example a server id | api.js:1316-1326 |
| `pull_chat` query | With `server`: the public chat of that server. Without it: the private conversation between `character` and `to` (1 to 12 name characters each) | api.js:1042-1064 |
| Chat cursor | `"<ISO date>\|MS_<id>"`, at most 100 characters. `cursor` gets older messages; `after` gets newer messages. Both together give `invalid_cursor` | api.js:1014-1021, 1039-1041, 1103 |
| Reply cursors | `cursor` is set when `more` is true. `after` is the newest message of the page, or `"<now>\|MS_0"` on an empty page | api.js:1023-1035 |
| `send_message` target | Exactly one of `to` (private) and `server` (public). `to` with `server` gives `invalid_name` | api.js:1204-1210 |
| `send_message` text | Not blank, at most 1,200 characters | api.js:1200, 1179 |
| `send_message` rate | 400 ms between two messages of one account (`chat_slowdown`) | api.js:1186-1193 |

#### CODE

| `method` | Who | Arguments | Result and `infs` | Failures | Source |
|---|---|---|---|---|---|
| `save_code` | user | `slot`: any (a string or a number); `code?`: any (a string; needed unless the call deletes); `name?`: any (a string, at most 100 characters); `log?`, `auto?`, `electron?`: any (flags) | `{success: true}`; `infs`: `code_info`, then an `eval` (not with `electron`), then a `message` or `chat_message` with `color` | `not_logged_in`, `invalid_field` + `field` (`slot`, `name` or `code`), `no_slot`, `code_too_large` + `max_bytes`, `received_bytes`; `code_rate_limited` + `retry_after_ms`; `code_storage_full` + `max_slots`, `max_bytes`; `not_found`; `save_failed` | api.js:1385-1487 |
| `load_code` | user | `name`: any (a string or a number: the slot number or the slot name; `"0"` is the default code); `run?`, `log?`, `pure?`, `save?`: any (flags) | `{success: true}`; `infs`: `code`, then a `message` (with `log`) or `chat_message` (without `save`). With `pure`: only `{code}`, without `success` | `invalid_field` + `field: "name"`; `not_found` (+ a `chat_message`; with `pure`, the reply is `{code: "say('Code not found'); set_status('Not Found')"}`) | api.js:1489-1522 |
| `list_codes` | user | `purpose?`: string | `{success: true}`; `infs`: `code_list` | – | api.js:1535-1540 |
| `load_libraries` | user | – | `{success: true}`; `infs`: `libraries` | – | api.js:1524-1533 |
| `load_gcode` | user | `file`: string (a path below `docs/`); `run?`: any | `{success: true}`; `infs`: `code` with `run: true`, or `gcode` | `{failed: true}` without a `reason` when `file` has `..`; `exception` for a missing file | api.js:2122-2128 |

Rules of `save_code` (api.js:1385-1487):

| Rule | Value |
|---|---|
| Slot | `"1"` to `"100"`, or the id of a character of the account. Other text gives `no_slot`. At most 100 characters, no NUL |
| Delete | `name: "DELETE"`. A delete of a slot that does not exist gives `not_found`. A save with the name `"DELETE"` gives `invalid_field` |
| Name | Converted with `to_filename`. Without a name, the server keeps the old name, else uses the character name or the slot |
| Version | Each save adds 1 to the version (`v`) of the slot |
| Limits | 1 MiB per slot, 128 MiB and 118 slots per account. A save that makes a slot smaller always passes the account limits |
| Rate | A burst of 10 saves; one save comes back each 2 s. Deletes count too |

#### Tutorial, articles, maps and payments

| `method` | Who | Arguments | Result and `infs` | Failures | Source |
|---|---|---|---|---|---|
| `load_article` | public | `name`: string; `func?`: any; `tutorial?`: any; `guide?`: any; `track?`: string; `url?`: string | `{success: true}`; `infs`: `article`. The first true flag of `tutorial`, `guide`, `func` picks the folder: `docs/tutorial/`, `docs/guide/` (then `docs/articles/`), `docs/functions/`; else `docs/articles/` | A missing guide gives an "article not found" HTML. A missing file in the other branches gives `exception` | api.js:2079-2120 |
| `tutorial` | user | `task?`: string; `step?`: any (`parseInt`); `lesson?`: string (the key of the current lesson); `track?`: string (absent or `"merchant"`) | `{success: true}`; `infs`: `tutorial_data`, then a `message` with `color` (not when the task is for another lesson) | `invalid` (bad `track`), `failed` | api.js:1542-1607 |
| `reset_tutorial` | user | `track?`: string (absent or `"merchant"`) | `{success: true}`; `infs`: `tutorial_data`, then a `message` | `invalid`, `failed` | api.js:1609-1635 |
| `load_map` | user | `key`: string | `{success: true}`; `infs`: `map` | `{failed: true}` without a `reason`, + a `message` (`deck_not_found`) when the map does not exist or is not a resort map | api.js:2130-2138 |
| `copy_map` | user (map editors) | `from`: string; `to`: string | `{success: true}`; a message | `no_permission`, `cant_copy_over_map_in_use` | api.js:2044-2060 |
| `delete_map` | user (map editors) | `name`: string | `{success: true}`; a message | `no_permission`, `cant_delete_map_in_use` | api.js:2062-2077 |
| `stripe_payment` | user | `usd`: any (`max(1, parseInt(usd))`); `response?`: any (the Stripe token object; the server reads `id`) | `{success: true}`; `infs`: `func` `["success", <shells of the account>]`, then success | `issue_with_token_or_usd`, `transaction_failed`, `card_declined`, `payment_failed`; each with a `func` item | api.js:1958-2040 |
| `steam_payment_start` | user | `ticket`: string; `usd`: number (1, 10, 25, 100 or 500); `sandbox?`: boolean | `{success, order_id, shells, sandbox, steam_url}` | `tauri_required`, `invalid_amount`, `steam_account_required`, `steam_auth_failed`, `purchase_creation_failed`, `steam_not_configured`, `steam_purchase_failed`, `steam_checkout_unavailable` | api.js:1840-1898 |
| `steam_payment_finish` | user | `order_id`: string (1 to 20 digits); `authorized`: boolean | `{success, cash, shells, already_delivered}`; a success item | `tauri_required`, `invalid_order`, `steam_account_mismatch`, `steam_payment_pending`, `steam_purchase_failed`, `steam_purchase_cancelled`, `delivery_failed` | api.js:1799, 1837, 1900-1956 |
| `mainframe_*` (7 methods) | user | as in "Token JSON API", but `character`: string (min 1), `request_id`: string (min 8), `code_slot`: string (min 1) | the same replies as the token JSON API | the same, and `rate_limited` + `retry_after_ms` as an HTTP 200 reply | mcp_api.js:3028-3070 |
| `test` | public, any verb | `number?`: number; `must?`: string | `{success: true}` | – | api.js:2140-2142 |
| `hi` | public, any verb | `hello?`: boolean | `{success: true, response: "hello"}` | – | api.js:2144-2146 |

The tutorial state (`tutorial`, `merchant_tutorial`, and the fields of `tutorial_data`; adventure_functions.js:1184-1236):

| Field | Meaning |
|---|---|
| `step` | The index of the current lesson |
| `task` | The first task that is not complete, or `false` |
| `completed` / `pending` | The tasks of the current lesson that are complete / not complete |
| `completed_tasks` | All complete tasks of the track |
| `completed_lessons` | The keys of the complete lessons |
| `progress` | The percent of the current lesson that is complete |
| `can_continue` | The current lesson is complete (not present after the last lesson) |
| `onboarding_finished` | The main track's onboarding is complete (always false for `"merchant"`) |
| `finished` | `true` after the last lesson |

Shells for a payment: 1 USD gives 75 shells. Other amounts give 80 per USD, plus 8% from 25 USD, 16% from 100 USD and 24% from 500 USD. An event bonus can add more (api.js:1649-1655). Steam payments need the desktop client (Tauri) and an account made through Steam (`platform: "steam"`) (api.js:1843-1848).

**Server bug:** `rename_character` and `quote_name` set the price to 0 for a first rename of a new character. The next line sets it back to 640, so the free rename never happens (api.js:659-660, 708-709).

### Other routes

| Route | Method | Purpose | Source |
|---|---|---|---|
| `/data.js` | any | Game data `G` as JavaScript (`var G={...};\n`) | main.js:14 |
| `/phrases/<language>.js` | GET | The phrase catalog of one language. See "Phrases" below | main.js:16 |
| `/js/<file>`, `/css/<file>` | GET | The client's JavaScript and CSS (from `js/` and `css/`, then common_engine's). `Cache-Control: public, max-age=2592000` | common:init.js:77-80, web_assets.js:123-133 |
| `/images/<file>` | GET | Images: sprites, tilesets and UI. 30-day cache | common:init.js:81 |
| `/sounds/<file>` | GET | Sounds and music. 30-day cache | main.js:15 |
| `/hub` | GET | The external Hub page (servers, characters) | main.js:168-196 |
| `/comm` | GET | Redirects with HTTP 301 to `/hub`, with the same query | main.js:167 |
| `/code.js?name=<slot or name>` | any | Raw saved CODE of the logged-in user | main.js:413-440 |
| `/`, `/character/<name>/in/<region>/<name>`, `/server/<region>/<name>` | GET | The game page | main.js:159-164, 338-376 |
| `/character/<name>`, `/player/<name>`, `/characters`, `/merchants` | GET | HTML profile pages | main.js:261-335 |
| `/mainframe` | GET | Character control and AI tokens | main.js:199-207 |
| `/update-notes?offset=N` | GET | `{notes, more}`, 20 per page | main.js:815-820 |
| `/ev/<uid>/<v>` | GET | The link of the verification email. Marks the email as verified; HTML message page | main.js:379-399 |
| `/reset/<uid>/<key>` | GET | The link of `password_reminder`. HTML form that calls `reset_password` with `id: <uid>`, `key: <key>` | main.js:402-411, htmls/contents/password_reset.html:37 |
| `/r/<ref>` | GET | Sets the `referrer` cookie and the referrer of the IP to the user `<ref>`, then redirects to `/`. A later signup stores this referrer | main.js:861-871, api.js:63-70 |
| `/steam-signin...`, `/steam-signup...` | GET / POST | Steam sign-in and Steam sign-up, HTML forms. See "Steam sign-in and sign-up" below | main.js:101-156 |
| `/shells`, `/steam-purchase` | GET | Payment pages (HTML) | main.js:488-502 |
| `/steam-purchase-status?order_id=<id>&token=<48 hex>` | GET | `{state: "complete", shells}`, `{state: "failed"}` or `{state: "processing"}`; HTTP 404 `{state: "invalid"}` for a bad order or token | main.js:504-516 |
| `/map/<name>` (GET, POST), `/communitymaps/<name>`, `/editmap`, `/editmap/<name>` (GET, POST), `/maps/<order>`, `/communityselector`, `/communityselector/<name>` | GET / POST | The resort and community map editor. `POST /map/<user id>_<1-10>` with `data` saves a resort map and replies with its size in characters | main.js:518-688 |
| `/docs/...`, `/codes`, `/vscode`, `/vscode/<file>`, `/runner`, `/executor`, `/logs`, `/realm/<map>`, `/allnotes`, `/steam-news`, `/roadmap`, `/privacy`, `/terms`, `/contact`, `/credits`, `/linux`, `/macos`, `/drm-free`, `/it-is-what-it-is`, `/rearm`, `/robots.txt`, `/sitemap.xml` | GET | HTML pages and site files | main.js:240-870 |
| `/mcp_api`, `/mcp_api/<method>` | GET `/mcp_api`, POST `/mcp_api/<method>` (a GET of a method gives HTTP 404) | The token JSON API | mcp_api.js:3072-3076 |
| `/mcp` | GET / POST | The MCP server (Streamable HTTP, `Authorization: Bearer <token>`) | mcp_api.js:3248-3251 |

The paths in `G` are site paths. `G.sprites[..].file`, `G.tilesets[..].file`, `G.imagesets[..].file` and `G.animations[..].file` are, for example, `/images/tiles/map/castle.png?v=2`. The URL is `https://adventure.land` plus the path. The keys of `G.images` are the same paths without `?v=...`, with `width`, `height` and `type`.

These routes are not for clients. They need a key, an admin account or a local address:

| Route | Source |
|---|---|
| `/x/defer` (local address and `defer_key` only) | common:handlers.js:3-20 |
| `/admin/executor`, `/admin/renderer`, `/admin/make/user/admin` | common:admin.js:7-29 |
| `/internal/bots/control`, `/internal/mainframe/code`, `/admin/mainframe`, `/admin/mainframe/state` | admin_bots.js:684-789 |
| `/admin`, `/admin/users`, `/admin/refresh` | admin_dashboard.js:695-729 |
| On each game server: `GET /` ("Hello World!"), and the keyed router at `api_path` (`/shutdown`, `/cupdate`, `/new_friend`, `/lost_friend`, `/eval`), which `server_eval` uses | node/server.js:31, 741-817; adventure_functions.js:1444-1496 |

### Important endpoints in detail

#### Login: `signup_or_login`

Request:
```
POST https://adventure.land/api/signup_or_login
Content-Type: application/json

{"email":"me@example.com","password":"hunter2","only_login":true}
```

The server does these checks in this order (api.js:85-221):

1. The account is in a bank (`server` has a value), and both `last_online` and `last_auth` are less than 15 minutes old: `cant_login_inside_bank`.
2. The User-Agent is not Electron or `AdventureLandTauri/`, and `only_login` is not set: `cant_signup_on_web` (adventure_functions.js:624-636). `only_login: true` skips this check.
3. The email exists, `only_signup` is not set, and the password matches: the server adds a token and sets the cookie. A failed transaction gives `login_failed` (or its own reason).
4. The email exists, `only_signup` is not set, and the password is wrong: `wrong_password`. `infs` has `{"type":"eval","code":"$('.passwordui').show()"}`.
5. No email: `no_email`. With `only_login` and an unknown email: `email_not_found`.
6. With `only_signup` and a known email: `already_signed_up`.
7. The IP of the request already has 3 signups: `too_many_signups_from_ip_wait` (api.js:134).
8. Else the server makes a new account. An email that the transaction finds in use gives `email_exists` (api.js:139).

A new account gets 1,000 gold in the bank, the packs `items0` and `items1`, and a verification email. It gets 8 character slots from a desktop client and 5 otherwise (api.js:156-192, 206). The reply has the same fields as a login, with `infs` `success` + selection (api.js:207-220).

The dispatcher checks `email` and `password` before the method runs. A bad email gives `invalid_field` with `not_email`, and an empty password gives `invalid_field` with `minimum_length` (api.js:2154-2155).

Response:
```json
{"success":true,"user":"US_<29 chars>","auth":"<64 hex chars>","language":"en",
 "infs":[{"type":"message","message":"Logged In!"},{"type":"content","html":"<selection html>"}]}
```
- `Set-Cookie: auth=US_<id>-<token>` comes with it (api.js:113).
- With `mobile: true`, `infs` has only `{"type":"refresh"}` (api.js:114-117).

**Example:**

```js
// POST /api/signup_or_login. Each password login adds 1 token to the account.
async function signupOrLogin() {
  const res = await fetch("https://adventure.land/api/signup_or_login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // only_login must be JSON true. Without it, the reason is "cant_signup_on_web".
    body: JSON.stringify({ email: process.env.AL_EMAIL, password: process.env.AL_PASSWORD, only_login: true }),
  });
  const data = await res.json(); // HTTP 200 also when the login fails
  if (data.success !== true) throw new Error(`login failed: ${data.reason}`); // e.g. "wrong_password"
  return { user: data.user, auth: data.auth }; // AL_AUTH = `${user}-${auth}`
}
```

```ts
// POST /api/signup_or_login. Each password login adds 1 token to the account.
type LoginReply =
  | { success: true; user: string; auth: string; language: string }
  | { failed: true; reason: string; success?: undefined };

async function signupOrLogin(): Promise<{ user: string; auth: string }> {
  const res = await fetch("https://adventure.land/api/signup_or_login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // only_login must be JSON true. Without it, the reason is "cant_signup_on_web".
    body: JSON.stringify({ email: process.env.AL_EMAIL, password: process.env.AL_PASSWORD, only_login: true }),
  });
  const data = (await res.json()) as LoginReply; // HTTP 200 also when the login fails
  if (data.success !== true) throw new Error(`login failed: ${data.reason}`); // e.g. "wrong_password"
  return { user: data.user, auth: data.auth }; // AL_AUTH = `${user}-${auth}`
}
```

```python
# POST /api/signup_or_login. Each password login adds 1 token to the account.
# http: an httpx.AsyncClient. Returns (user, auth); AL_AUTH = f"{user}-{auth}".
async def signup_or_login(http: httpx.AsyncClient) -> tuple[str, str]:
    body = {"email": os.environ["AL_EMAIL"], "password": os.environ["AL_PASSWORD"],
            "only_login": True}  # must be JSON true, else reason "cant_signup_on_web"
    res = await http.post("https://adventure.land/api/signup_or_login", json=body)
    data = res.json()  # HTTP 200 also when the login fails
    if data.get("success") is not True:
        raise RuntimeError(f"login failed: {data.get('reason')}")  # e.g. "wrong_password"
    return data["user"], data["auth"]
```

```go
// SignupOrLogin sends POST /api/signup_or_login. Each password login adds 1 token
// to the account. AL_AUTH = user + "-" + auth.
func SignupOrLogin() (user, auth string, err error) {
	// only_login must be JSON true. Without it, the reason is "cant_signup_on_web".
	body, _ := json.Marshal(map[string]any{
		"email": os.Getenv("AL_EMAIL"), "password": os.Getenv("AL_PASSWORD"), "only_login": true,
	})
	res, err := http.Post("https://adventure.land/api/signup_or_login", "application/json", bytes.NewReader(body))
	if err != nil {
		return "", "", err
	}
	defer res.Body.Close()
	var reply struct { // HTTP 200 also when the login fails
		Success bool   `json:"success"`
		User    string `json:"user"`
		Auth    string `json:"auth"`
		Reason  string `json:"reason"` // e.g. "wrong_password"
	}
	if err := json.NewDecoder(res.Body).Decode(&reply); err != nil {
		return "", "", err
	}
	if !reply.Success {
		return "", "", fmt.Errorf("login failed: %s", reply.Reason)
	}
	return reply.User, reply.Auth, nil
}
```

```csharp
// POST /api/signup_or_login. Each password login adds 1 token to the account.
// http: one shared HttpClient. AL_AUTH = $"{User}-{Auth}".
async Task<(string User, string Auth)> SignupOrLogin()
{
    var body = new
    {
        email = Environment.GetEnvironmentVariable("AL_EMAIL"),
        password = Environment.GetEnvironmentVariable("AL_PASSWORD"),
        only_login = true, // must be JSON true, else reason "cant_signup_on_web"
    };
    var res = await http.PostAsJsonAsync("https://adventure.land/api/signup_or_login", body);
    var data = await res.Content.ReadFromJsonAsync<JsonElement>(); // HTTP 200 also on failure
    if (!data.TryGetProperty("success", out var ok) || ok.ValueKind != JsonValueKind.True)
        throw new Exception($"login failed: {data.GetProperty("reason")}"); // e.g. "wrong_password"
    return (data.GetProperty("user").GetString()!, data.GetProperty("auth").GetString()!);
}
```

```rust
// POST /api/signup_or_login. Each password login adds 1 token to the account.
// Error = Box<dyn std::error::Error + Send + Sync>. Returns (user, auth); AL_AUTH = "<user>-<auth>".
async fn signup_or_login(http: &reqwest::Client) -> Result<(String, String), Error> {
    let body = json!({
        "email": std::env::var("AL_EMAIL")?,
        "password": std::env::var("AL_PASSWORD")?,
        "only_login": true, // must be JSON true, else reason "cant_signup_on_web"
    });
    let url = "https://adventure.land/api/signup_or_login";
    let reply: Value = http.post(url).json(&body).send().await?.json().await?; // HTTP 200 also on failure
    if reply["success"] != json!(true) {
        return Err(format!("login failed: {}", reply["reason"]).into()); // e.g. "wrong_password"
    }
    let (Some(user), Some(auth)) = (reply["user"].as_str(), reply["auth"].as_str()) else {
        return Err("no user or auth in the reply".into());
    };
    Ok((user.to_string(), auth.to_string()))
}
```

```java
// POST /api/signup_or_login. Each password login adds 1 token to the account.
// HTTP: a java.net.http.HttpClient. JSON: a Jackson ObjectMapper. AL_AUTH = user + "-" + auth.
record Session(String user, String auth) {}

static Session signupOrLogin() throws Exception {
    // only_login must be JSON true. Without it, the reason is "cant_signup_on_web".
    var body = Map.of("email", System.getenv("AL_EMAIL"), "password", System.getenv("AL_PASSWORD"), "only_login", true);
    var req = HttpRequest.newBuilder(URI.create("https://adventure.land/api/signup_or_login"))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(JSON.writeValueAsString(body))).build();
    JsonNode reply = JSON.readTree(HTTP.send(req, HttpResponse.BodyHandlers.ofString()).body());
    if (!reply.path("success").asBoolean(false)) { // HTTP 200 also when the login fails
        throw new Exception("login failed: " + reply.path("reason").asText()); // e.g. "wrong_password"
    }
    return new Session(reply.path("user").asText(), reply.path("auth").asText());
}
```

#### `servers_and_characters`

Request: `POST /api/servers_and_characters` with body `{}` and the cookie.

Response (api.js:461-471, adventure_functions.js:761-776, 811-844):
```json
{"success":true,"infs":[{
  "type":"servers_and_characters",
  "servers":[{"name":"I","region":"EU","players":42,"key":"SR_EUI",
              "address":"<host>","path":"<socket.io path>","msgpack_path":"<path>"}],
  "characters":[{"id":"CH_<29 chars>","name":"MyMage","level":80,"type":"mage",
                 "online":123456,"server":"SR_EUI","secret":"<24 chars>",
                 "skin":"..","cx":{},"in":"main","map":"main","x":0,"y":0,"home":"EUI","rip":..}],
  "tutorial":{..},"merchant_tutorial":{..},"code_list":{"1":["name",3]},"mail":0,"rewards":[]}]}
```
- `servers` lists only servers with `online: true` that the config marks as active. The order is EU, US, ASIA, then by name (adventure_functions.js:673-690).
- `key` is the database id of the server, `SR_<region><name>`. A character's `server` has the same form (node/server.js:462, 11625).
- `online` is the time in ms since `last_online`, or `0` when the character is offline. `server` and `secret` are present only when the character is online (adventure_functions.js:827-833). Use `server` to find online characters.
- Characters with `online` set come first (adventure_functions.js:850-852).
- `home` is `<region><name>` without the `SR_` prefix (node/server_functions.js:1098).
- On the host `cloudflare.adventure.land`, the list has only the `de.adventure.land` servers, with that address replaced (adventure_functions.js:708-713).

**Example:**

```js
// POST /api/servers_and_characters with the cookie auth=<user>-<auth> (the text in AL_AUTH).
async function serversAndCharacters() {
  const res = await fetch("https://adventure.land/api/servers_and_characters", {
    method: "POST",
    headers: { "Content-Type": "application/json", Cookie: `auth=${process.env.AL_AUTH}` },
    body: "{}",
  });
  const data = await res.json();
  if (data.failed) throw new Error(data.reason); // "not_logged_in": the token is not valid
  // The data is in the infs item of type "servers_and_characters".
  const { servers, characters } = data.infs.find((i) => i.type === "servers_and_characters");
  for (const s of servers) console.log(s.key, s.players, s.address, s.path); // key: "SR_" + region + name
  for (const c of characters) console.log(c.name, c.id, c.type, c.level, c.server ?? "offline");
  return { servers, characters };
}
```

```ts
// POST /api/servers_and_characters with the cookie auth=<user>-<auth> (the text in AL_AUTH).
interface ServerEntry {
  key: string; // "SR_" + region + name, e.g. "SR_EUI"
  region: string; name: string; players: number; address: string; path: string; msgpack_path: string;
}
interface CharacterEntry {
  id: string; name: string; type: string; level: number; online: number; // id: "CH_..."
  server?: string; secret?: string; // only while the character is online
}
type Inf = { type: string; servers?: ServerEntry[]; characters?: CharacterEntry[] };

async function serversAndCharacters() {
  const res = await fetch("https://adventure.land/api/servers_and_characters", {
    method: "POST",
    headers: { "Content-Type": "application/json", Cookie: `auth=${process.env.AL_AUTH}` },
    body: "{}",
  });
  const data = (await res.json()) as { failed?: true; reason?: string; infs?: Inf[] };
  if (data.failed) throw new Error(data.reason); // "not_logged_in": the token is not valid
  const inf = data.infs?.find((i) => i.type === "servers_and_characters");
  return { servers: inf?.servers ?? [], characters: inf?.characters ?? [] };
}
```

```python
# POST /api/servers_and_characters with the cookie auth=<user>-<auth> (the text in AL_AUTH).
async def servers_and_characters(http: httpx.AsyncClient) -> dict:
    res = await http.post("https://adventure.land/api/servers_and_characters", json={},
                          headers={"Cookie": f"auth={os.environ['AL_AUTH']}"})
    data = res.json()
    if data.get("failed"):
        raise RuntimeError(data.get("reason"))  # "not_logged_in": the token is not valid
    # The data is in the infs item of type "servers_and_characters".
    inf = next(i for i in data["infs"] if i["type"] == "servers_and_characters")
    for s in inf["servers"]:
        print(s["key"], s["players"], s["address"], s["path"])  # key: "SR_" + region + name
    for c in inf["characters"]:
        print(c["name"], c["id"], c["type"], c["level"], c.get("server", "offline"))
    return inf
```

```go
// Server and Character are items of the servers_and_characters lists.
type Server struct {
	Key     string `json:"key"` // "SR_" + Region + Name, e.g. "SR_EUI"
	Region  string `json:"region"`
	Name    string `json:"name"`
	Players int    `json:"players"`
	Address string `json:"address"`
	Path    string `json:"path"`
}
type Character struct {
	ID     string `json:"id"` // "CH_..."
	Name   string `json:"name"`
	Type   string `json:"type"`
	Level  int    `json:"level"`
	Server string `json:"server"` // empty while offline
	Secret string `json:"secret"` // empty while offline
}

// ServersAndCharacters sends POST /api/servers_and_characters with the cookie
// auth=<user>-<auth> (the text in AL_AUTH).
func ServersAndCharacters() ([]Server, []Character, error) {
	req, _ := http.NewRequest("POST", "https://adventure.land/api/servers_and_characters", strings.NewReader("{}"))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Cookie", "auth="+os.Getenv("AL_AUTH"))
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, nil, err
	}
	defer res.Body.Close()
	var reply struct {
		Failed bool   `json:"failed"`
		Reason string `json:"reason"` // "not_logged_in": the token is not valid
		Infs   []struct {
			Type       string      `json:"type"`
			Servers    []Server    `json:"servers"`
			Characters []Character `json:"characters"`
		} `json:"infs"`
	}
	if err := json.NewDecoder(res.Body).Decode(&reply); err != nil {
		return nil, nil, err
	}
	if reply.Failed {
		return nil, nil, errors.New(reply.Reason)
	}
	for _, inf := range reply.Infs {
		if inf.Type == "servers_and_characters" {
			return inf.Servers, inf.Characters, nil
		}
	}
	return nil, nil, errors.New("no servers_and_characters item in infs")
}
```

```csharp
// POST /api/servers_and_characters with the cookie auth=<user>-<auth> (the text in AL_AUTH).
async Task<JsonElement> ServersAndCharacters()
{
    using var req = new HttpRequestMessage(HttpMethod.Post, "https://adventure.land/api/servers_and_characters")
    {
        Content = JsonContent.Create(new { }),
    };
    req.Headers.Add("Cookie", $"auth={Environment.GetEnvironmentVariable("AL_AUTH")}");
    using var res = await http.SendAsync(req);
    var data = await res.Content.ReadFromJsonAsync<JsonElement>();
    if (data.TryGetProperty("failed", out _))
        throw new Exception(data.GetProperty("reason").GetString()); // "not_logged_in": the token is not valid
    // The data is in the infs item of type "servers_and_characters".
    var inf = data.GetProperty("infs").EnumerateArray().First(i => i.GetProperty("type").GetString() == "servers_and_characters");
    foreach (var s in inf.GetProperty("servers").EnumerateArray()) // key: "SR_" + region + name
        Console.WriteLine($"{s.GetProperty("key")} {s.GetProperty("players")} {s.GetProperty("address")} {s.GetProperty("path")}");
    foreach (var c in inf.GetProperty("characters").EnumerateArray()) // server: only while online
        Console.WriteLine($"{c.GetProperty("name")} {c.GetProperty("id")} {(c.TryGetProperty("server", out var sv) ? sv.GetString() : "offline")}");
    return inf;
}
```

```rust
// POST /api/servers_and_characters with the cookie auth=<user>-<auth> (the text in AL_AUTH).
async fn servers_and_characters(http: &reqwest::Client) -> Result<Value, Error> {
    let reply: Value = http
        .post("https://adventure.land/api/servers_and_characters")
        .header("Cookie", format!("auth={}", std::env::var("AL_AUTH")?))
        .json(&json!({}))
        .send().await?.json().await?;
    if reply["failed"] == json!(true) {
        return Err(format!("{}", reply["reason"]).into()); // "not_logged_in": the token is not valid
    }
    // The data is in the infs item of type "servers_and_characters".
    let inf = reply["infs"].as_array().and_then(|a| a.iter().find(|i| i["type"] == "servers_and_characters"))
        .ok_or("no servers_and_characters item in infs")?;
    for s in inf["servers"].as_array().into_iter().flatten() {
        println!("{} {} {} {}", s["key"], s["players"], s["address"], s["path"]); // key: "SR_" + region + name
    }
    for c in inf["characters"].as_array().into_iter().flatten() {
        println!("{} {} {}", c["name"], c["id"], c["server"].as_str().unwrap_or("offline"));
    }
    Ok(inf.clone())
}
```

```java
// POST /api/servers_and_characters with the cookie auth=<user>-<auth> (the text in AL_AUTH).
static JsonNode serversAndCharacters() throws Exception {
    var req = HttpRequest.newBuilder(URI.create("https://adventure.land/api/servers_and_characters"))
            .header("Content-Type", "application/json")
            .header("Cookie", "auth=" + System.getenv("AL_AUTH"))
            .POST(HttpRequest.BodyPublishers.ofString("{}")).build();
    JsonNode reply = JSON.readTree(HTTP.send(req, HttpResponse.BodyHandlers.ofString()).body());
    if (reply.path("failed").asBoolean(false)) { // "not_logged_in": the token is not valid
        throw new Exception(reply.path("reason").asText());
    }
    for (JsonNode inf : reply.path("infs")) {
        if (!inf.path("type").asText().equals("servers_and_characters")) continue;
        for (JsonNode s : inf.path("servers")) // key: "SR_" + region + name
            System.out.println(s.path("key").asText() + " " + s.path("players").asInt() + " " + s.path("address").asText() + s.path("path").asText());
        for (JsonNode c : inf.path("characters")) // server: only while online
            System.out.println(c.path("name").asText() + " " + c.path("id").asText() + " " + c.path("server").asText("offline"));
        return inf;
    }
    throw new Exception("no servers_and_characters item in infs");
}
```

#### `get_servers`

Request: `GET /api/get_servers`, without a cookie. `POST` also works (api.js:2260).

Response (api.js:884-900), from the live server on 2026-10-04:
```json
{"success":true,"servers":[
  {"address":"de.adventure.land","path":"/ws1/","msgpack_path":"/ws1-msgpack/","region":"EU","name":"I","pvp":"","gameplay":"normal"},
  {"address":"de.adventure.land","path":"/ws3/","msgpack_path":"/ws3-msgpack/","region":"EU","name":"PVP","pvp":true,"gameplay":"normal"}]}
```
- The servers are the same as in `servers_and_characters`, in the same order (adventure_functions.js:673-690, 698-703).
- The entries have no `key` and no `players`. The key of a server is `SR_<region><name>`, for example `SR_EUI` (node/server.js:462).
- `pvp` is the server's `info.pvp`. In the live list, it is `true` on PvP servers and `""` (an empty string) on the other servers.
- In the live list, `path` and `msgpack_path` end with `/`, for example `/ws1/`.

**Example:**

```js
// GET /api/get_servers: public, no cookie.
async function getServers() {
  const data = await (await fetch("https://adventure.land/api/get_servers")).json();
  // Fields: address, path, msgpack_path, region, name, pvp (true or ""), gameplay.
  for (const s of data.servers) console.log(s.region, s.name, s.address, s.path, s.pvp === true);
  return data.servers;
}
```

```ts
// GET /api/get_servers: public, no cookie.
interface PublicServer {
  address: string; // e.g. "de.adventure.land"
  path: string; // e.g. "/ws1/"
  msgpack_path: string;
  region: string; // "EU", "US", "ASIA"
  name: string; // "I", "II", "PVP", ...
  pvp: true | ""; // "" on non-PvP servers
  gameplay: string; // "normal", "hardcore", ...
}

async function getServers(): Promise<PublicServer[]> {
  const res = await fetch("https://adventure.land/api/get_servers");
  const data = (await res.json()) as { success: true; servers: PublicServer[] };
  for (const s of data.servers) console.log(s.region, s.name, s.address, s.path, s.pvp === true);
  return data.servers;
}
```

```python
# GET /api/get_servers: public, no cookie.
async def get_servers(http: httpx.AsyncClient) -> list[dict]:
    res = await http.get("https://adventure.land/api/get_servers")
    servers: list[dict] = res.json()["servers"]
    # Fields: address, path, msgpack_path, region, name, pvp (True or ""), gameplay.
    for s in servers:
        print(s["region"], s["name"], s["address"], s["path"], s["pvp"] is True)
    return servers
```

```go
// PublicServer is one item of the get_servers list.
type PublicServer struct {
	Address     string `json:"address"` // e.g. "de.adventure.land"
	Path        string `json:"path"`    // e.g. "/ws1/"
	MsgpackPath string `json:"msgpack_path"`
	Region      string `json:"region"` // "EU", "US", "ASIA"
	Name        string `json:"name"`   // "I", "II", "PVP", ...
	PvP         any    `json:"pvp"`    // true, or "" on non-PvP servers
	Gameplay    string `json:"gameplay"`
}

// GetServers sends GET /api/get_servers: public, no cookie.
func GetServers() ([]PublicServer, error) {
	res, err := http.Get("https://adventure.land/api/get_servers")
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	var reply struct {
		Servers []PublicServer `json:"servers"`
	}
	if err := json.NewDecoder(res.Body).Decode(&reply); err != nil {
		return nil, err
	}
	for _, s := range reply.Servers {
		fmt.Println(s.Region, s.Name, s.Address, s.Path, s.PvP == true)
	}
	return reply.Servers, nil
}
```

```csharp
// GET /api/get_servers: public, no cookie.
async Task<JsonElement> GetServers()
{
    var data = await http.GetFromJsonAsync<JsonElement>("https://adventure.land/api/get_servers");
    // Fields: address, path, msgpack_path, region, name, pvp (true or ""), gameplay.
    var servers = data.GetProperty("servers");
    foreach (var s in servers.EnumerateArray())
    {
        bool pvp = s.GetProperty("pvp").ValueKind == JsonValueKind.True;
        Console.WriteLine($"{s.GetProperty("region")} {s.GetProperty("name")} {s.GetProperty("address")} {s.GetProperty("path")} {pvp}");
    }
    return servers;
}
```

```rust
// GET /api/get_servers: public, no cookie.
async fn get_servers(http: &reqwest::Client) -> Result<Vec<Value>, Error> {
    let mut reply: Value = http.get("https://adventure.land/api/get_servers").send().await?.json().await?;
    let Value::Array(servers) = reply["servers"].take() else {
        return Err("no servers in the reply".into());
    };
    // Fields: address, path, msgpack_path, region, name, pvp (true or ""), gameplay.
    for s in &servers {
        let (region, name) = (s["region"].as_str().unwrap_or(""), s["name"].as_str().unwrap_or(""));
        let (address, path) = (s["address"].as_str().unwrap_or(""), s["path"].as_str().unwrap_or(""));
        println!("{region} {name} {address} {path} {}", s["pvp"] == true);
    }
    Ok(servers)
}
```

```java
// GET /api/get_servers: public, no cookie.
static JsonNode getServers() throws Exception {
    var req = HttpRequest.newBuilder(URI.create("https://adventure.land/api/get_servers")).GET().build();
    JsonNode servers = JSON.readTree(HTTP.send(req, HttpResponse.BodyHandlers.ofString()).body()).path("servers");
    // Fields: address, path, msgpack_path, region, name, pvp (true or ""), gameplay.
    for (JsonNode s : servers) {
        boolean pvp = s.path("pvp").asBoolean(false); // "" is false
        System.out.println(s.path("region").asText() + " " + s.path("name").asText() + " "
                + s.path("address").asText() + " " + s.path("path").asText() + " " + pvp);
    }
    return servers;
}
```

#### Game data `G`

- `GET https://adventure.land/data.js` returns `var G={...};\n` (web_assets.js:52).
- `G` has 33 keys (main.js:443-485). The first 16: `version`, `achievements`, `animations`, `monsters`, `sprites`, `maps`, `geometry`, `npcs`, `tilesets`, `imagesets`, `items`, `sets`, `craft`, `titles`, `tokens`, `dismantle`. The other 17: `conditions`, `cosmetics`, `projectiles`, `classes`, `dimensions`, `levels`, `upgrades`, `compounds`, `monster_gold`, `positions`, `skills`, `games`, `events`, `images`, `multipliers`, `docs`, `drops`.
- The server builds the file in memory and refreshes it every 30 s (web_assets.js:36, 49-63). The reply has `Cache-Control: public, no-cache`, an `ETag`, and gzip when the client accepts it (web_assets.js:24-34, 67).
- `reload=1` adds two lines of client JavaScript to the end and sets `no-store` (web_assets.js:9, 66-67).
- If the server has no copy of the file yet and cannot make one, the reply is HTTP 503 with `Retry-After: 1` (web_assets.js:66-70).
- `G.version` is `Version` from version.js: 15555 in the file at the pinned commit (version.js:1). The live value is higher, 17478 on 2026-10-04. With `Local` on, each start of main.js adds 1 to the number in version.js (main.js:33-40). `welcome` carries `version: G.version`, so a client can check its cached `G` (node/server.js:4983). The game pages also have `var VERSION='<version>'` (htmls/base_script.html:32).

**Example:**

```js
// GET /data.js: public. The body is JavaScript (`var G={...};`), not JSON.
async function getG() {
  const js = await (await fetch("https://adventure.land/data.js")).text();
  // The JSON is the text from the first "{" to the last "}".
  const G = JSON.parse(js.slice(js.indexOf("{"), js.lastIndexOf("}") + 1));
  console.log(G.version, Object.keys(G.items).length); // the version, and the number of items
  return G;
}
```

```ts
// GET /data.js: public. The body is JavaScript (`var G={...};`), not JSON.
interface GData {
  version: number;
  items: Record<string, { name: string; g: number }>; // type only the tables that you read
  monsters: Record<string, { hp: number; xp: number }>;
}

async function getG(): Promise<GData> {
  const js = await (await fetch("https://adventure.land/data.js")).text();
  // The JSON is the text from the first "{" to the last "}".
  const G = JSON.parse(js.slice(js.indexOf("{"), js.lastIndexOf("}") + 1)) as GData;
  console.log(G.version, Object.keys(G.items).length); // the version, and the number of items
  return G;
}
```

```python
# GET /data.js: public. The body is JavaScript (`var G={...};`), not JSON.
async def get_g(http: httpx.AsyncClient) -> dict:
    js = (await http.get("https://adventure.land/data.js")).text
    # The JSON is the text from the first "{" to the last "}".
    G: dict = json.loads(js[js.index("{") : js.rindex("}") + 1])
    print(G["version"], len(G["items"]))  # the version, and the number of items
    return G
```

```go
// GetG sends GET /data.js: public. The body is JavaScript (`var G={...};`), not JSON.
func GetG() (map[string]json.RawMessage, error) {
	res, err := http.Get("https://adventure.land/data.js")
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	js, err := io.ReadAll(res.Body)
	if err != nil {
		return nil, err
	}
	// The JSON is the text from the first "{" to the last "}".
	start, end := bytes.IndexByte(js, '{'), bytes.LastIndexByte(js, '}')
	if start < 0 || end < start {
		return nil, errors.New("data.js: no JSON object")
	}
	var G map[string]json.RawMessage // decode each table later, into its own type
	if err := json.Unmarshal(js[start:end+1], &G); err != nil {
		return nil, err
	}
	var version int
	_ = json.Unmarshal(G["version"], &version)
	fmt.Println(version, len(G)) // the version, and the number of tables
	return G, nil
}
```

```csharp
// GET /data.js: public. The body is JavaScript (`var G={...};`), not JSON.
async Task<JsonElement> GetG()
{
    var js = await http.GetStringAsync("https://adventure.land/data.js");
    // The JSON is the text from the first "{" to the last "}".
    var G = JsonDocument.Parse(js[js.IndexOf('{')..(js.LastIndexOf('}') + 1)]).RootElement;
    int items = G.GetProperty("items").EnumerateObject().Count();
    Console.WriteLine($"{G.GetProperty("version").GetInt32()} {items}"); // the version, and the number of items
    return G;
}
```

```rust
// GET /data.js: public. The body is JavaScript (`var G={...};`), not JSON.
async fn get_g(http: &reqwest::Client) -> Result<Value, Error> {
    let js = http.get("https://adventure.land/data.js").send().await?.text().await?;
    // The JSON is the text from the first "{" to the last "}".
    let (start, end) = (js.find('{').ok_or("no {")?, js.rfind('}').ok_or("no }")?);
    let g: Value = serde_json::from_str(&js[start..=end])?;
    let items = g["items"].as_object().map_or(0, |m| m.len());
    println!("{} {}", g["version"], items); // the version, and the number of items
    Ok(g)
}
```

```java
// GET /data.js: public. The body is JavaScript (`var G={...};`), not JSON.
static JsonNode getG() throws Exception {
    var req = HttpRequest.newBuilder(URI.create("https://adventure.land/data.js")).GET().build();
    String js = HTTP.send(req, HttpResponse.BodyHandlers.ofString()).body();
    // The JSON is the text from the first "{" to the last "}".
    JsonNode G = JSON.readTree(js.substring(js.indexOf('{'), js.lastIndexOf('}') + 1));
    System.out.println(G.path("version").asInt() + " " + G.path("items").size()); // the version, and the number of items
    return G;
}
```

#### `disconnect_character`

- Arguments: `{"name":"<character name>"}`.
- Failures: `no_character`, `not_owner`, `character_not_in_game`. "In game" means only that the character has a `server` value (adventure_functions.js:1001-1004).
- On success, the API makes that game server run `player.socket.disconnect()` (api.js:876, adventure_functions.js:1490-1496).
- `infs` has a message. With `selection: true`, it also has the selection HTML (api.js:877-878).

#### Mail

- `pull_mail` returns 40 mails per page, newest first. While `more` is true, send the returned `cursor` to get the next page (api.js:1250-1299).
- Each mail has `fro`, `to`, `message`, `subject`, `sent`, `id`, and `item` and `taken` when it carries an item. `sent` is a JavaScript `Date` string. `item` is the item in the client form (`simplify_item`) (api.js:1274-1293).
- A mail of a cave award or of the Tracktrix gift also has `subject_message` and `body_message`. Each is a localization object without `message`, for example `{"phrase":"server.cave.mail_subject"}` (api.js:1282-1289). See "Phrases" below.
- `read_mail {mail:<id>}` marks a mail as read and returns the unread count. The `ML_` prefix is optional (api.js:1243).
- Sending mail and taking items happen on the game socket (`mail`, `mail_take_item`).

#### Phrases: `/phrases/<language>.js`

Many socket payloads carry text as a localization object `{message, phrase, phrase_args}`: for example `game_log`, `game_error`, `notice`, `server_message` and `pm`. The server makes it with `localization.message(id, args, fields)` (languages/index.js:256-258):

| Field | Value |
|---|---|
| `message` | The English text, already resolved on the server |
| `phrase` | The id of the text in the phrase catalog, for example `"server.game_log.slain_by"` |
| `phrase_args` | An object with the values for the placeholders, `{}` when there are none |

The phrase catalog of a language comes from `GET https://adventure.land/phrases/<language>.js`. The route is public (main.js:16, languages/index.js:294-313):

| Fact | Value | Source |
|---|---|---|
| Languages | `en`, `tr`, `ru`, `es`, `pt-BR`, `de`, `ja`, `fr`, `pl`, `ko`, `zh-Hans`, `zh-Hant`, `th`, `es-419`, `uk`, `it`, `cs`, `hu`, `pt-PT`, `vi`, `sv`, `nl`, `da`, `id`, `fi`, `no`, `ro`, `el`, `bg`, `ms`, `ar`, `fil` | js/phrases.js:7-40 |
| Body | `phrase.load("<language>",{"<id>":"<text>",...});` and a newline. `Content-Type: application/javascript` | languages/index.js:304, 309 |
| The object | JSON. The server writes `<`, `>`, `&`, U+2028 and U+2029 as `\uXXXX` escapes, which JSON reads back as the same characters | languages/index.js:301-303 |
| Texts | The English text of each id, replaced by the translation where the language has one | languages/index.js:228-236 |
| Ids | Only the domains for the browser: `client`, `code`, `definitions`, `editor`, `errors`, `game`, `interface`, `language`, `mainframe`, `page_actions`, `services`, two `docs.` ids, and the `server.` ids of the socket messages (`server.game_log`, `server.game_error`, `server.notice`, `server.server_message`, `server.pm`, `server.party`, and others) | languages/index.js:165-200 |
| Unknown language | HTTP 404, text `Unknown language` | languages/index.js:296 |
| Encoding | gzip when `Accept-Encoding` allows it. HTTP 406 when the request accepts neither gzip nor identity | languages/index.js:298-299, 307 |
| Cache | `Cache-Control: public, max-age=2592000` (30 days) | languages/index.js:310 |
| The game page | Loads `/js/phrases.js`, then `/phrases/<language>.js?v=<version>` | htmls/language.html:1-2 |

The official client turns a localization object into text with `phrase.message(data)` (js/phrases.js:95-115, 157-161). The steps:

1. If the payload is not an object, the payload is the text. If it has no `phrase`, the text is `message`.
2. If `phrase_args.count` is a number, find the plural category of `count` in the language (`Intl.PluralRules`: `zero`, `one`, `two`, `few`, `many` or `other`). If the catalog has the id `<phrase>.<category>`, use that id.
3. Get the template of the id from the catalog. If the catalog does not have the id, the template is the id.
4. Replace each `{name}` in the template with `phrase_args[name]`. A name starts with a letter or `_`, then letters, digits or `_`. A `{name}` without an argument stays as it is. A `null` value becomes an empty string.
5. If an argument is an object with a string `phrase`, resolve it with the same steps and its own `phrase_args`. The client stops after 4 levels and uses an empty string.
6. For HTML output, the client escapes each argument value (`&`, `<`, `>`, `"`, `'`). It does not escape the template.

For example, `{"message":"Slain by Goo","phrase":"server.game_log.slain_by","phrase_args":{"attacker":"Goo"}}` gives "Von Goo erschlagen" with the `de` catalog. Its template is `"Von {attacker} erschlagen"` (languages/de/server.json:122).

`phrase.error(reason)` turns an HTTP `reason` into text in the same way: it uses the id `error.<reason>` when the catalog has it, else `error.unexpected`. `wait_<N>_minutes` uses `error.wait_minutes` with `{minutes: N}` (js/phrases.js:162-169).

**Example:**

```js
// GET /phrases/<language>.js: public. The body is JavaScript: phrase.load("<language>",{...});
async function fetchPhrases(language) {
  const js = await (await fetch(`https://adventure.land/phrases/${language}.js`)).text();
  // The catalog is the JSON object from the first "{" to the last "}".
  return JSON.parse(js.slice(js.indexOf("{"), js.lastIndexOf("}") + 1));
}

// Turns {message, phrase, phrase_args} into text, with the steps of js/phrases.js.
function resolvePhrase(catalog, language, data, depth = 0) {
  if (data === null || typeof data !== "object") return data; // a bare string is the text
  if (!data.phrase) return data.message;
  const args = data.phrase_args ?? {};
  let id = data.phrase;
  if (typeof args.count === "number") { // plural: "<id>.one", "<id>.other", ...
    const plural = `${id}.${new Intl.PluralRules(language).select(args.count)}`;
    if (Object.hasOwn(catalog, plural)) id = plural;
  }
  const template = Object.hasOwn(catalog, id) ? catalog[id] : id; // an unknown id is its own text
  return template.replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (match, name) => {
    if (!Object.hasOwn(args, name)) return match; // no argument: keep "{name}"
    const value = args[name];
    if (value && typeof value === "object" && typeof value.phrase === "string")
      return depth < 4 ? resolvePhrase(catalog, language, value, depth + 1) : ""; // a nested phrase
    return value == null ? "" : String(value);
  });
}
// const de = await fetchPhrases("de");
// resolvePhrase(de, "de", gameLog); // "Von Goo erschlagen"
```

```ts
// GET /phrases/<language>.js: public. The body is JavaScript: phrase.load("<language>",{...});
type Catalog = Record<string, string>;
interface Localized {
  message?: string; // the English text
  phrase?: string; // the id in the catalog, e.g. "server.game_log.slain_by"
  phrase_args?: Record<string, unknown>;
}

async function fetchPhrases(language: string): Promise<Catalog> {
  const js = await (await fetch(`https://adventure.land/phrases/${language}.js`)).text();
  // The catalog is the JSON object from the first "{" to the last "}".
  return JSON.parse(js.slice(js.indexOf("{"), js.lastIndexOf("}") + 1)) as Catalog;
}

// Turns {message, phrase, phrase_args} into text, with the steps of js/phrases.js.
function resolvePhrase(catalog: Catalog, language: string, data: Localized | string, depth = 0): string {
  if (typeof data !== "object" || data === null) return data; // a bare string is the text
  if (!data.phrase) return data.message ?? "";
  const args = data.phrase_args ?? {};
  let id = data.phrase;
  if (typeof args.count === "number") { // plural: "<id>.one", "<id>.other", ...
    const plural = `${id}.${new Intl.PluralRules(language).select(args.count)}`;
    if (Object.hasOwn(catalog, plural)) id = plural;
  }
  const template = Object.hasOwn(catalog, id) ? catalog[id] : id; // an unknown id is its own text
  return template.replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (match: string, name: string) => {
    if (!Object.hasOwn(args, name)) return match; // no argument: keep "{name}"
    const value = args[name];
    if (value && typeof value === "object" && typeof (value as Localized).phrase === "string")
      return depth < 4 ? resolvePhrase(catalog, language, value as Localized, depth + 1) : ""; // a nested phrase
    return value == null ? "" : String(value);
  });
}
```

```python
# GET /phrases/<language>.js: public. The body is JavaScript: phrase.load("<language>",{...});
# http: an httpx.AsyncClient.
async def fetch_phrases(http: httpx.AsyncClient, language: str) -> dict[str, str]:
    js = (await http.get(f"https://adventure.land/phrases/{language}.js")).text
    # The catalog is the JSON object from the first "{" to the last "}".
    catalog: dict[str, str] = json.loads(js[js.index("{") : js.rindex("}") + 1])
    return catalog


PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def to_text(value: Any) -> str:
    # The same text as JavaScript's String(value) for null, booleans and whole numbers.
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def resolve_phrase(catalog: dict[str, str], data: Any, depth: int = 0) -> Any:
    """Turns {message, phrase, phrase_args} into text, with the steps of js/phrases.js."""
    if not isinstance(data, dict):
        return data  # a bare string is the text
    if not data.get("phrase"):
        return data.get("message")
    args: dict[str, Any] = data.get("phrase_args") or {}
    pid: str = data["phrase"]
    count = args.get("count")
    if isinstance(count, (int, float)) and not isinstance(count, bool):
        # English plural rule only. Other languages need CLDR plural rules (Intl.PluralRules in JS).
        plural = f"{pid}.{'one' if count == 1 else 'other'}"
        if plural in catalog:
            pid = plural
    template = catalog.get(pid, pid)  # an unknown id is its own text

    def replace(match: re.Match[str]) -> str:
        if match.group(1) not in args:
            return match.group(0)  # no argument: keep "{name}"
        value = args[match.group(1)]
        if isinstance(value, dict) and isinstance(value.get("phrase"), str):
            return to_text(resolve_phrase(catalog, value, depth + 1)) if depth < 4 else ""
        return to_text(value)

    return PLACEHOLDER.sub(replace, template)
```

```go
// GET /phrases/<language>.js: public. The body is JavaScript: phrase.load("<language>",{...});
func FetchPhrases(language string) (map[string]string, error) {
	res, err := http.Get("https://adventure.land/phrases/" + language + ".js")
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	body, err := io.ReadAll(res.Body)
	if err != nil {
		return nil, err
	}
	// The catalog is the JSON object from the first "{" to the last "}".
	js := string(body)
	start, end := strings.Index(js, "{"), strings.LastIndex(js, "}")
	if start < 0 || end < start {
		return nil, fmt.Errorf("phrases %s: HTTP %d", language, res.StatusCode)
	}
	catalog := map[string]string{}
	err = json.Unmarshal([]byte(js[start:end+1]), &catalog)
	return catalog, err
}

var placeholder = regexp.MustCompile(`\{([a-zA-Z_][a-zA-Z0-9_]*)\}`)

// ResolvePhrase turns {message, phrase, phrase_args} into text, with the steps of js/phrases.js.
// data is a decoded JSON payload (json.Unmarshal into an any). English plural rule only.
func ResolvePhrase(catalog map[string]string, data any, depth int) string {
	obj, ok := data.(map[string]any)
	if !ok {
		text, _ := data.(string) // a bare string is the text
		return text
	}
	id, _ := obj["phrase"].(string)
	if id == "" {
		text, _ := obj["message"].(string)
		return text
	}
	args, _ := obj["phrase_args"].(map[string]any)
	if count, ok := args["count"].(float64); ok {
		category := "other"
		if count == 1 {
			category = "one"
		}
		if _, ok := catalog[id+"."+category]; ok {
			id += "." + category
		}
	}
	template, ok := catalog[id]
	if !ok {
		template = id // an unknown id is its own text
	}
	return placeholder.ReplaceAllStringFunc(template, func(match string) string {
		value, ok := args[match[1:len(match)-1]]
		if !ok {
			return match // no argument: keep "{name}"
		}
		switch v := value.(type) {
		case nil:
			return ""
		case string:
			return v
		case map[string]any:
			if _, nested := v["phrase"].(string); nested {
				if depth < 4 {
					return ResolvePhrase(catalog, v, depth+1)
				}
				return ""
			}
		}
		text, _ := json.Marshal(value) // numbers and booleans as JSON writes them
		return string(text)
	})
}
```

```csharp
// GET /phrases/<language>.js: public. The body is JavaScript: phrase.load("<language>",{...});
// http: an HttpClient.
async Task<Dictionary<string, string>> FetchPhrases(string language)
{
    var js = await http.GetStringAsync($"https://adventure.land/phrases/{language}.js");
    // The catalog is the JSON object from the first "{" to the last "}".
    var json = js[js.IndexOf('{')..(js.LastIndexOf('}') + 1)];
    return JsonSerializer.Deserialize<Dictionary<string, string>>(json)!;
}

// Turns {message, phrase, phrase_args} into text, with the steps of js/phrases.js. English plural rule only.
string ResolvePhrase(Dictionary<string, string> catalog, JsonElement data, int depth = 0)
{
    if (data.ValueKind != JsonValueKind.Object) return data.ValueKind == JsonValueKind.String ? data.GetString()! : ""; // a bare string is the text
    if (!data.TryGetProperty("phrase", out var phrase) || phrase.ValueKind != JsonValueKind.String || phrase.GetString() == "")
        return data.TryGetProperty("message", out var message) ? message.GetString() ?? "" : "";
    var args = data.TryGetProperty("phrase_args", out var a) && a.ValueKind == JsonValueKind.Object ? a : default;
    var id = phrase.GetString()!;
    if (args.ValueKind == JsonValueKind.Object && args.TryGetProperty("count", out var count) && count.ValueKind == JsonValueKind.Number)
    {
        var plural = id + "." + (count.GetDouble() == 1 ? "one" : "other");
        if (catalog.ContainsKey(plural)) id = plural;
    }
    var template = catalog.TryGetValue(id, out var text) ? text : id; // an unknown id is its own text
    return System.Text.RegularExpressions.Regex.Replace(template, @"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", match =>
    {
        if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty(match.Groups[1].Value, out var value))
            return match.Value; // no argument: keep "{name}"
        if (value.ValueKind == JsonValueKind.Null) return "";
        if (value.ValueKind == JsonValueKind.String) return value.GetString()!;
        if (value.ValueKind == JsonValueKind.Object && value.TryGetProperty("phrase", out var nested) && nested.ValueKind == JsonValueKind.String)
            return depth < 4 ? ResolvePhrase(catalog, value, depth + 1) : ""; // a nested phrase
        return value.GetRawText(); // numbers and booleans as JSON writes them
    });
}
```

```rust
// GET /phrases/<language>.js: public. The body is JavaScript: phrase.load("<language>",{...});
use std::collections::HashMap;

async fn fetch_phrases(http: &reqwest::Client, language: &str) -> Result<HashMap<String, String>, Error> {
    let url = format!("https://adventure.land/phrases/{language}.js");
    let js = http.get(url).send().await?.text().await?;
    // The catalog is the JSON object from the first "{" to the last "}".
    let (start, end) = (js.find('{').ok_or("no catalog")?, js.rfind('}').ok_or("no catalog")?);
    Ok(serde_json::from_str(&js[start..=end])?)
}

/// Turns {message, phrase, phrase_args} into text, with the steps of js/phrases.js.
/// English plural rule only.
fn resolve_phrase(catalog: &HashMap<String, String>, data: &Value, depth: u32) -> String {
    let Some(obj) = data.as_object() else {
        return data.as_str().unwrap_or_default().to_string(); // a bare string is the text
    };
    let Some(mut id) = obj.get("phrase").and_then(Value::as_str).filter(|p| !p.is_empty()).map(str::to_string) else {
        return obj.get("message").and_then(Value::as_str).unwrap_or_default().to_string();
    };
    let empty = serde_json::Map::new();
    let args = obj.get("phrase_args").and_then(Value::as_object).unwrap_or(&empty);
    if let Some(count) = args.get("count").and_then(Value::as_f64) {
        let plural = format!("{id}.{}", if count == 1.0 { "one" } else { "other" });
        if catalog.contains_key(&plural) {
            id = plural;
        }
    }
    let template = catalog.get(&id).cloned().unwrap_or(id); // an unknown id is its own text
    // Replace each {name}: a letter or "_", then letters, digits or "_".
    let (mut out, mut rest) = (String::new(), template.as_str());
    while let Some(open) = rest.find('{') {
        out.push_str(&rest[..open]);
        let after = &rest[open + 1..];
        let len = after.find(|c: char| !(c.is_ascii_alphanumeric() || c == '_')).unwrap_or(after.len());
        let name = &after[..len];
        let valid = !name.is_empty() && !name.starts_with(|c: char| c.is_ascii_digit()) && after[len..].starts_with('}');
        let Some(value) = args.get(name).filter(|_| valid) else {
            out.push('{'); // not a placeholder, or no argument: keep the text
            rest = after;
            continue;
        };
        out.push_str(&match value {
            Value::Null => String::new(),
            Value::String(s) => s.clone(),
            Value::Object(o) if o.get("phrase").is_some_and(Value::is_string) => {
                if depth < 4 { resolve_phrase(catalog, value, depth + 1) } else { String::new() }
            }
            other => other.to_string(), // numbers and booleans as JSON writes them
        });
        rest = &after[len + 1..];
    }
    out.push_str(rest);
    out
}
```

```java
// GET /phrases/<language>.js: public. The body is JavaScript: phrase.load("<language>",{...});
// HTTP: an HttpClient. JSON: an ObjectMapper.
static JsonNode fetchPhrases(String language) throws Exception {
    HttpRequest req = HttpRequest.newBuilder(URI.create("https://adventure.land/phrases/" + language + ".js")).build();
    String js = HTTP.send(req, HttpResponse.BodyHandlers.ofString()).body();
    // The catalog is the JSON object from the first "{" to the last "}".
    return JSON.readTree(js.substring(js.indexOf('{'), js.lastIndexOf('}') + 1));
}

static final java.util.regex.Pattern PLACEHOLDER = java.util.regex.Pattern.compile("\\{([a-zA-Z_][a-zA-Z0-9_]*)\\}");

// Turns {message, phrase, phrase_args} into text, with the steps of js/phrases.js. English plural rule only.
static String resolvePhrase(JsonNode catalog, JsonNode data, int depth) {
    if (!data.isObject()) return data.asText(); // a bare string is the text
    String phrase = data.path("phrase").asText("");
    if (phrase.isEmpty()) return data.path("message").asText();
    JsonNode args = data.path("phrase_args");
    String id = phrase;
    if (args.path("count").isNumber()) {
        String plural = id + "." + (args.path("count").asDouble() == 1 ? "one" : "other");
        if (catalog.has(plural)) id = plural;
    }
    String template = catalog.has(id) ? catalog.get(id).asText() : id; // an unknown id is its own text
    return PLACEHOLDER.matcher(template).replaceAll(match -> {
        JsonNode value = args.get(match.group(1));
        String text;
        if (value == null) text = match.group(); // no argument: keep "{name}"
        else if (value.isNull()) text = "";
        else if (value.path("phrase").isTextual()) text = depth < 4 ? resolvePhrase(catalog, value, depth + 1) : "";
        else if (value.isValueNode()) text = value.asText(); // strings, numbers, booleans
        else text = value.toString();
        return java.util.regex.Matcher.quoteReplacement(text);
    });
}
```

#### Steam sign-in and sign-up

Two flows of HTML forms let a browser use a Steam account. Both use Steam OpenID 2.0 (`https://steamcommunity.com/openid/login`) and need the host `adventure.land`, `www.adventure.land` or `cloudflare.adventure.land` (steam_signup.js:3-15). A POST needs an `Origin` header of the same site and the `state` value of the form. When the request already has a valid auth cookie, each step only redirects to `/`.

Steam sign-in logs in to an existing account of the Steam id (steam_signin.js:153-159). The account has Steam sign-in turned on (`settings` `steam_login`), or comes from Steam sign-up. The flow cookie is `__Host-al_steam_signin`, valid for 5 minutes (steam_signin.js:5, 14-15).

| Step | Request | Reply | Source |
|---|---|---|---|
| 1 | `GET /steam-signin` | HTML form with `state`; sets the flow cookie | steam_signin.js:109-115 |
| 2 | `POST /steam-signin/start` with `state` | HTTP 303 to Steam, with `openid.return_to` = `/steam-signin/callback?state=<new state>` | steam_signin.js:116-126 |
| 3 | `GET /steam-signin/callback?state=...&openid.*` (Steam redirects here) | The server checks the signature with Steam. HTTP 303 to `/steam-signin/accounts` | steam_signin.js:127-144 |
| 4 | `GET /steam-signin/accounts`; `POST` with `more=yes` and `state` for the next page | HTML list of at most 20 accounts: a one-use `handle`, the account name, a masked email, and the first 3 character names | steam_signin.js:145-187 |
| 5 | `POST /steam-signin/complete` with `state` and `account=<handle>` | A new token in `auths` and `steam_auths`; sets the auth cookie; HTTP 303 to `/` | steam_signin.js:188-207 |
| – | `POST /steam-signin/cancel` with `state` | Deletes the flow; HTTP 303 to `/` | steam_signin.js:234-237 |

Steam sign-up makes a new account for a Steam account that owns the game (Steam app 777150). The flow cookie is `al_steam_signup`, signed, valid for 20 minutes, with the path `/steam-signup` (steam_signup.js:5-6, 51-62, 136-142).

| Step | Request | Reply | Source |
|---|---|---|---|
| 1 | `GET /steam-signup` | HTML form with `state`; sets the flow cookie | steam_signup.js:183-188 |
| 2 | `POST /steam-signup/start` with `state` | HTTP 303 to Steam | steam_signup.js:189-196 |
| 3 | `GET /steam-signup/callback?state=...&openid.*` | The server checks the signature and the ownership of the game. HTTP 303 to `/steam-signup` (now a form for email and password) | steam_signup.js:197-205 |
| 4 | `POST /steam-signup/complete` with `state`, `email` (at most 254 characters) and `password` (1 to 1,024 characters) | Runs the signup of `signup_or_login` with `only_signup`. The account gets `platform: "steam"`, `pid: <Steam id>` and 8 character slots. HTTP 303 to `/` | steam_signup.js:206-228, api.js:132-192 |

A Steam sign-up account has an email and a password, so `signup_or_login` can also log it in.

Errors in both flows give an HTML page (steam_signin.js:97-106, steam_signup.js:169-179). The status is HTTP 400 for a failed check, and HTTP 503 when Steam or the server is not available. Step 4 of sign-up shows the form again with one of `error.already_signed_up`, `error.email_exists`, `error.too_many_signups_from_ip_wait`, `error.invalid_field` or `pages.steam_signup.failed` (steam_signup.js:214-223). Sign-in allows 4,000 requests in total, 120 per IP and 40 per Steam id in each 5 minutes (steam_signin.js:53-69). Sign-up allows 20 attempts per IP in 5 minutes (steam_signup.js:143-154).

## Connecting to a game server

### Socket.IO servers and options

Each game server runs two Socket.IO v4 servers on one HTTP server (node/server.js:81-100):

| Endpoint | Path | Parser | Transports | Client packet limit |
|---|---|---|---|---|
| Default | the server's `path` | standard JSON Socket.IO frames | default | default |
| MessagePack | the server's `msgpack_path` | Adventure Land's positional MessagePack | WebSocket only | 64 KiB |

- Both use `pingInterval: 4000` and `pingTimeout: 12000`, and CORS `origin: "*"` (node/server.js:50-54, 83-84, 94-96).
- Neither uses per-message deflate (node/server.js:56-57).
- The default endpoint speaks standard JSON frames. node/json_parser.js only encodes some frames faster, with the same bytes (node/json_parser.js:2-7).
- The MessagePack endpoint needs the game's own parser from `https://adventure.land/js/socket.io-msgpack-parser.min.js`. Generic MessagePack parsers do not work with it (docs/articles/X.sub-msgpack.html:22). Each packet is an array, for example `[2, ["hello", "you"]]` for an event (docs/articles/X.sub-msgpack.html:74-79).
- The browser client connects to `path` with `transports: ["websocket"]` (js/game.js:1527-1541).

Connect like this:

```js
io("wss://" + server.address, {path: server.path, transports: ["websocket"],
  query: "map_protocol=1&no_graphics=1"})
```

Query parameters (node/server.js:4861-4876, 4989-5011; node/logic/observer_broadcast.js:3-6):

| Parameter | Meaning |
|---|---|
| `map_protocol=1` | The client understands generated maps. Without it, the server cannot send a generated map, and it throws `client_update_required` (node/logic/generated_maps.js:186). |
| `no_graphics=1` | Generated maps arrive without tile data. |
| `secret=<character secret>` | Observe that online character (see Observing). |
| `desktop=1` | With `secret`: the camera sits 120 px below the character. |
| `broadcast=1` | A public camera that follows active groups (see Observing). |
| `server_method` | Internal. The server disconnects the socket at once. |

### Handshake sequence

The WebSocket URL is `wss://<address><path>?EIO=4&transport=websocket&map_protocol=1&no_graphics=1`, with one `/` at the end of `path`. `address` and `path` come from the server list (`servers_and_characters` or `get_servers`). `EIO=4` and `transport=websocket` are the Engine.IO v4 query. The table above describes the other parameters.

**Example:**

```js
// The WebSocket URL of a game server, from the address and path of its server-list entry.
// The live path ends with "/" ("/ws1/"): remove one "/" from the end, then add one.
function socketUrl(address, path) {
  return `wss://${address}${path.replace(/\/?$/, "/")}?EIO=4&transport=websocket&map_protocol=1&no_graphics=1`;
}
// socketUrl("de.adventure.land", "/ws1/")
//   == "wss://de.adventure.land/ws1/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1"
```

```ts
// The WebSocket URL of a game server, from the address and path of its server-list entry.
// The live path ends with "/" ("/ws1/"): remove one "/" from the end, then add one.
function socketUrl(address: string, path: string): string {
  return `wss://${address}${path.replace(/\/?$/, "/")}?EIO=4&transport=websocket&map_protocol=1&no_graphics=1`;
}
```

```python
# The WebSocket URL of a game server, from the address and path of its server-list entry.
# The live path ends with "/" ("/ws1/"): remove the "/" at the end, then add one.
def socket_url(address: str, path: str) -> str:
    return f"wss://{address}{path.rstrip('/')}/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1"
```

```go
// SocketURL is the WebSocket URL of a game server, from the address and path of its
// server-list entry. The live path ends with "/" ("/ws1/"): remove it, then add one.
func SocketURL(address, path string) string {
	return "wss://" + address + strings.TrimSuffix(path, "/") + "/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1"
}
```

```csharp
// The WebSocket URL of a game server, from the address and path of its server-list entry.
// The live path ends with "/" ("/ws1/"): remove the "/" at the end, then add one.
string SocketUrl(string address, string path) =>
    $"wss://{address}{path.TrimEnd('/')}/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1";
```

```rust
// The WebSocket URL of a game server, from the address and path of its server-list entry.
// The live path ends with "/" ("/ws1/"): remove the "/" at the end, then add one.
fn socket_url(address: &str, path: &str) -> String {
    let path = path.trim_end_matches('/');
    format!("wss://{address}{path}/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1")
}
```

```java
// The WebSocket URL of a game server, from the address and path of its server-list entry.
// The live path ends with "/" ("/ws1/"): remove one "/" from the end, then add one.
static String socketUrl(String address, String path) {
    return "wss://" + address + path.replaceAll("/$", "") + "/?EIO=4&transport=websocket&map_protocol=1&no_graphics=1";
}
```

1. **Server → `welcome`**, sent at once on connection (node/server.js:4977-5019):
   ```json
   {"region":"EU","name":"I","pvp":false,"gameplay":"normal","info":{},
    "version":15555,"x":0,"y":120,"map":"main","in":"main","S":{...}}
   ```
   - `S` is the server event state (`E`, see S) (node/server.js:5017).
   - `x`, `y`, `map` and `in` are where the observer camera starts. Without a secret, this is the current camera spot, plus 120 on `y` (node/server.js:4985-4988).
   - With a matching `secret`, `welcome` also has `character` (the full `player_to_client` data of that character) and that character's position (node/server.js:4989-5011).
   - **Server bug:** the server reads `info` from `socket.first_map` before it sets `first_map`. Thus `info` is always `{}` (node/server.js:4982, 4985).
   - `gameplay` is `normal`, `hardcore`, `test` or `dungeon` (node/server.js:367-411).
   - Compare `region` and `name` with the server that you selected.
2. **Client → `loaded`**:
   ```json
   {"success":1,"width":1920,"height":1080,"scale":2}
   ```
   The server ignores the payload. Vision is always `B.vision` = `[700, 500]` (node/server.js:217, 5045). The server makes an observer for this socket and sends one `entities` event of `type: "all"` (node/server.js:5028-5054). `loaded` works once per socket. The server ignores it when the socket already has a character or an observer, or when a login is in progress (node/server.js:5029).
3. **Client → `auth`**:
   ```json
   {"user":"US_<id>","character":"CH_<id>","auth":"<64 hex token>","code_slot":1,
    "no_html":"1","passphrase":""}
   ```
   The fields that the server reads (node/server.js:11563-11861):

   | Field | Meaning |
   |---|---|
   | `user` | The user id. The `US_` prefix is optional. |
   | `character` | The character id (`id` from `servers_and_characters`). The `CH_` prefix is optional. |
   | `auth` | The token from `signup_or_login` (not `<user>-<token>`). |
   | `code_slot` | Optional. A CODE slot number or name. `start` then carries the code. |
   | `passphrase` | Must be `"potato salad"` on `test` servers. |
   | `no_html` | Sets `afk: "code"`. If it is the name of an online character, that name becomes `controller`. |
   | `bot` | Compared with the private `BOT_MASTER` key. |
   | `epl`, `receipt`, `ticket` | Mac App Store, Steam and Tauri checks. |
   | `mainframe_session` | Used by the Mainframe service. |

   `width`, `height`, `scale` and `no_graphics` are not used.
4. **Checks before the login starts** (node/server.js:11564-11589). The server stops at the first one that applies:

   | Condition | Reply |
   |---|---|
   | `data` is not an object, or `user`, `character` or `auth` is not a string | none |
   | `test` server and a wrong `passphrase` | `game_log` "Wrong passphrase!" |
   | A login is in progress on this socket or for this character | `game_log` "Authorization in progress." |
   | The character is still saving after a disconnect (`dc_players`), or is online on this server | `game_log` "Authorization in progress." |
   | The server is not live, the socket did not send `loaded`, or the socket already has a character | none |
   | `max_players` characters are online | `game_error` "Can't accept more than 200 players at this time" |

5. **The login transaction** (node/server.js:11608-11652). In one MongoDB transaction, the server reads the user and the character. It then writes `server`, `online`, a new 24-character `secret` and `last_start` to the character. Failures come as `game_error` `{message: "Failed: <reason>", reason, phrase, phrase_args}`:

   | `reason` | Cause |
   |---|---|
   | `no_character` | The character does not exist, or it is not yours. |
   | `password_issue` | The user does not exist, or the token is not in its `auths`. |
   | `mainframe_issue` | `mainframe_session` is set and is not valid. |
   | `ingame` | The character's `server` is set: it is online, or its logout save is not complete. |
   | `poker_hand_active` | A poker hand is still open on another server. This one has its own message. |
   | `cancelled` | The 60 s login time ended. |
   | `exception` | The transaction failed. |

   Changed from the old server: there is no 40 s wait between two starts of a character. Only `ingame` stops a second start.
6. **The 60 s limit.** A login must finish in 60 s (node/logic/character_sessions.js:3). Then the server cancels it, releases the character, and disconnects the socket (node/server.js:11601-11605). At each step the server also checks that the socket is still connected and still an observer (node/logic/character_sessions.js:17-28). A failed step sends `game_error` `"ERROR!"` (node/server.js:11969-11978).
7. **Other failures after the transaction:**
   - `game_error` "Could not confirm your other characters. Please try again." (node/server.js:11873-11877).
   - `game_error` capacity again, if the server filled during the login (node/server.js:11879-11882).
   - **Over the online limit:** `disconnect_reason "limits"`, then a disconnect (node/server.js:11914-11916). See Rate limits.
8. **Success: `start`** (node/server.js:11918-11944). The payload is `player_to_client(player)` with all private fields (node/server.js:855-1003), plus these:
   ```json
   {"id":"MyMage","x":..,"y":..,"map":"main","in":"main","hp":..,"max_hp":..,"mp":..,"max_mp":..,
    "level":..,"xp":..,"max_xp":..,"gold":..,"cash":..,"ctype":"mage","owner":"US_..","skin":"..","cx":{..},
    "items":[ ...null for empty... ],"isize":42,"esize":N,"slots":{"mainhand":{..},..},
    "s":{..},"c":{..},"q":{..},"speed":..,"range":..,"cc":<current call cost>,
    "ipass":"<12 chars>","home":"EUI","friends":[..],"acx":..,"xcx":..,
    "info":{instance info},"base_gold":..,"s_info":{server events},
    "blessed_by":..,"blessed_minutes":..,
    "code":"..","code_slot":"1","code_version":N,
    "entities":{"type":"all","in":"main","map":"main","players":[..],"monsters":[..]}}
   ```
   - `blessed_*` appear only during a blessing. `code*` appear only if the server found the `code_slot`.
   - `id` is the character **name** (node/server.js:11779). The server keeps the `CH_` id as `real_id`.
   - Some saved maps do not allow a start: generated maps, and maps that are not open instances. Then the character starts at that map's `on_exit` spawn (node/server.js:11738-11751).

**`authfail` condition:** applies when `mode.drm_check` is on, the account is from after 2019-02-01 (`drm`), and the character has no `auth_id`. On the web platform, `auth_id` is the account's `pid`. The account gets a `pid` at its first login through the Steam or Mac App Store client (adventure_functions.js:950-968). Effect: luck −85, gold −85, xp −20, persistent (node/server.js:11856-11870, design/conditions.js:439-450). Accounts from before 2019-02-01 have `drm` false (adventure_functions.js:857-859).

The browser client sends `auth` only after the first `entities` of `type: "all"` arrives (js/game.js:519-527).

### What the client must keep sending

- **Nothing at the game level.** The Socket.IO ping and pong (4 s interval, 12 s timeout) keep the socket open (node/server.js:83-84). A Socket.IO v4 client does this itself.
- The old `ipass` check-in is off. The client has the code only as a comment (js/game.js:1815-1816), and the server loop has `if (0 && ...)` (node/server.js:16046). `start` still carries `ipass`.
- `send_updates` is optional. It makes the server send a new full `entities` (`type: "all"`) snapshot (node/server.js:5020-5027). It costs 12 call-cost points (node/server.js:248).
- `ping_trig <data>` comes back as `ping_ack <data>`. Use it to measure latency (node/server.js:5126-5128).
- `property {afk: true|false}` sets the AFK state. It has no effect when `afk` is `"code"` or `"bot"` (node/server.js:5548-5568).

### Disconnection and `disconnect_reason`

When the server disconnects you on purpose, it sends `disconnect_reason` (a string) first:

| Value | Cause | Source |
|---|---|---|
| `"limitdc"` | Call-cost limit (after `limitdcreport`) | node/server.js:4939-4943, 4952-4961 |
| `"limits"` | Too many characters online for this owner or IP | node/server.js:11914-11916 |
| `"Too many loose connections from your network. Simply reload to play."` | More than 5 sockets without a character from your IP. The server sends it to the *older* loose sockets. | node/server.js:4830-4852, 4878-4880 |
| `"Failed to check in. Your network might be too slow."` | The `ipass` check (off) | node/server.js:16042-16055 |
| any string | Admin `shutdown` with a `reason`, to everyone | node/server.js:13152-13160 |

Other cases:

- `disconnect_character` (HTTP), the 60 s login limit, and the Socket.IO ping timeout disconnect without a reason.
- On disconnect, the server ends duels, leaves the party, and sends `disappear {id, reason: "disconnect"}` to others nearby. It then puts the character in `dc_players` and starts `sync_loop` (node/server.js:13044-13141).
- `stop_call` saves the character and clears its `server`. When the save succeeds, the server removes the character from `dc_players` (node/server.js:16762-16812). `sync_loop` also runs every 24 s (node/server.js:16919).
- **Reconnecting:**
  - Open a new socket and do the full handshake again.
  - While the character is in `dc_players`, `auth` gets "Authorization in progress.". After the save, the character's `server` is clear and the login can continue.
  - If the save of the old session failed, the character keeps its `server` value, and `auth` fails with `ingame`. The source shows no automatic release after a game server crash; the procedure for that case is unclear from the source.
  - The client text for `limits` (js/game.js:394-400, languages/en/game.js:25):
    "You can have 3 characters and one merchant online at most."

## Every request

Every client-to-server event goes through one wrapper before its handler runs (node/server.js:4883-4975). The wrapper does these steps in this order. They apply to every send entry; the entries do not repeat them.

| # | Step | Result for the client | Source |
|---|---|---|---|
| 1 | A missing payload (`undefined`) becomes `{}`. `null` stays `null`. | Most handlers read `data.x`, so a `null` payload goes to step 5 | node/server.js:4893-4895 |
| 2 | The call cost goes up by 1, plus the event's extra cost from `CC` (see [Rate limits](#guide-rate-limits-and-anti-abuse)). If the total for the last 4 s is above the limit (200 with a character, 50 without), the handler does not run. `disconnect` is exempt. | `limitdcreport {calls, climit, total}`, then `disconnect_reason "limitdc"`, then the server closes the socket | node/server.js:4896-4943 |
| 3 | If the character's instance is paused, most events are refused (the allow-list is in [Paused instances](#guide-rate-limits-and-anti-abuse)). | `game_response {response: "data", failed: true, reason: "cave_paused" \| "cave_entering", place, request_id}`; a refused `move` also gets `correction {x, y}` | node/server.js:4944, node/logic/instance_pause.js:69-116 |
| 4 | The handler runs: see the event's entry. | The replies in the entry | |
| 5 | If the handler throws, the call cost goes up by 16. If that passes the limit, the server disconnects as in step 2 (`limitdcreport` also has `method`). | `game_error "ERROR!"` (a bare string) | node/server.js:4947-4968 |

**`request_id`:** handlers that support it accept any truthy value and echo it back unchanged in their replies. Its type in the entries is `any`. A handler that does not support it ignores it.

## Rate limits and anti-abuse

### Per-socket call cost (`limitdc`)

Every socket event goes through a wrapper (node/server.js:4882-4975):

- Each event adds **1** to the call log of the socket (`add_call_cost(-1)`, node/server.js:4897). Events in the `CC` table add their extra cost (node/server.js:4934-4937). The `CC` table (node/server.js:242-255):

  | Event | Extra cost |
  |---|---|
  | `auth` | 2 |
  | `move` | 1.5 |
  | `players` | 12 |
  | `secondhands` | 16 |
  | `friend` | 24 |
  | `send_updates` | 12 |
  | `cruise` | 10 |
  | `random_look` | 10 |
  | `equip` | 3 |
  | `unequip` | 6 |
  | `tracker` | 50 |
  | `ccreport` | 3 |

- `equip_batch` costs `3 × (0.5 + n/2)` for `n` items (node/server.js:4907-4912).
- `cm` costs `add × recipients × mult` (node/server.js:4913-4933). `add` is 1, or 2 when the JSON of the message is longer than 100 characters. The branches for more than 1,000, 10,000 and 50,000 never run, because the test for more than 100 comes first. `mult` is 0.8 when there is more than one recipient.
- `resend(player, ...)` adds more cost to the socket that sent the current event. A `u` resend adds `call_modifier`. A resend without `nc` adds `call_modifier` again. A `reopen` from another socket adds 4 times `call_modifier` (node/server.js:4550-4594). `call_modifier` is 0.1 for `open_chest`, 0.05 for `skill`, 0.5 for `target`, and 1 for other events (node/server.js:4899).
- Some handlers remove cost with `reduce_call_cost`, for example `target` and `property` (node/server_functions.js:5365-5386).
- An exception in a handler adds **16** and replies `game_error "ERROR!"` (node/server.js:4947-4966).
- The window is the **last 4,000 ms** (node/server_functions.js:5354-5356, 5396-5398).
- The limit is `limits.calls = 200` for a socket with a character, and `round(200/4) = 50` for a socket without one (node/server.js:256-260, 4891, 4900-4906).
- Above the limit, the server sends `limitdcreport {calls, climit, total}`, then `disconnect_reason "limitdc"`, then disconnects. The `disconnect` event is exempt (node/server.js:4939-4943).
- Your current cost is the `cc` field in `start` and `player` data (node/server.js:995-997). `ccreport` replies `ccreport {calls, climit, total}` (node/server.js:5437-5439). It always reports `climit: 200`, also for an observer with a limit of 50.

### Paused instances (`cave_paused`)

After the call-cost check, the wrapper asks `instance_block_action` (node/server.js:4944). If the character's instance is frozen, or the character is entering a zone, the server refuses most events (node/logic/instance_pause.js:69-116):

- The reply is `game_response {response: "data", failed: true, reason, place, request_id}`. `reason` is `cave_entering` while the character enters, and `cave_paused` otherwise. `place` is the skill name for `skill`, and the event name for other events.
- A refused `move` also gets `correction {x, y}`.
- The server always lets these events pass:

  `disconnect`, `error`, `loaded`, `ping_trig`, `requested_ack`, `ccreport`, `mreport`, `notice`, `send_updates`, `property`, `code`, `say`, `cm`, `party`, `friend`, `players`, `target`, `tracker`, `render`, `trade_history`, `secondhands`, `leave`, `stop`, `respawn`.
- `interaction` with `type: "cave"` and `action` `vote`, `state`, `info`, `talk` or `exit` also passes.

### Characters online at once

`is_player_allowed` runs after the login transaction (node/server_functions.js:383-437):

- Exempt: `bot` (a valid `BOT_MASTER`), `p.free`, the `licenced` condition, or the role `gm` (node/server_functions.js:376-381).
- **Merchants:** 1 merchant per owner on this server.
- **Other classes:** the server rejects the character if it finds more than `options.character_limit` same-owner non-merchant characters, this one included. The same count applies to characters with the same `auth_id`.
- The server rejects a second character with the same name.
- **IP:** the server rejects the character if more than `options.ip_limit × ipx` characters share its identity. The identity is the IP, or `mainframe:<owner>` for Mainframe characters (node/server_functions.js:815-817). `ipx` is 12 with an `auth_id`, else `player.ipx` or 1.
- `ip_limit` and `character_limit` are in the private config. HARDCORE and DUNGEON set both to 1, and TEST sets both to 5 (node/server.js:373-374, 387-388, 397-398). The browser text says "3 characters and one merchant" (languages/en/game.js:25).
- The count covers only this process's `players`, so the code enforces it **per game server**. A limit across servers is unclear from the source.

### Other limits

- **Characters per server:** `max_players = 200`, unless the server definition sets `max_players` (node/server.js:146, 459).
- **Loose sockets:** one IP can have 5 sockets without a character. A new socket above that makes the server disconnect the older loose sockets (node/server.js:4830-4852, 4878-4880).
- **Signups:** 3 per IP. The count decays by `hours / 24 / 1.2` when more than 12 hours passed since the last decay (api.js:134, adventure_functions.js:228-242).
- **Characters:** more than 12 recent creations from one IP gives `too_many_characters_from_ip`. An account has at most 18 characters. Above the slot count (5 on the web, 8 for Steam or desktop accounts), a new character costs 200 shells (api.js:14-22, 488-495, 554-557).
- **Movement:** the start and the end of a `move` must be walkable (`smap_data` below 2). If not, the server sends "Line violation detected". It then defeats the character and moves it to `jail` (node/server.js:11211-11243).

## Units and conventions

- **Coordinates** are map pixels. The server accepts floats (`parseFloat` in `move`, node/server.js:11189, 11207-11208).
  - Y increases downward. The server draws text "above" a character at `y - 32` (node/server.js:16029). The desktop observer camera is at `y + 120` (node/server.js:4987).
  - The character hitbox is `width 26`, `height 36` (node/server.js:11782-11783).
  - Spawn points are `G.maps[map].spawns[i] = [x, y]` (node/server.js:11747-11748).
- **`map` and `in`:**
  - `map` is the map name, a key of `G.maps` and `G.geometry`.
  - `in` is the instance id. For normal maps, `in == map`. Dungeons and other private instances get a random 24-character instance name (node/server.js:6082).
  - Entities, observers and position updates belong to one instance (node/server_functions.js:3675-3708).
- **`m`** counts map changes for each character. The server accepts a `move` only if `data.m == player.m` (node/server.js:11202).
- **Move payload:** `{"x":<current x>,"y":<current y>,"going_x":..,"going_y":..,"m":<player.m>}`. When the positions of the server and the client differ by more than 132 px, the server replies `correction {x, y}` (node/server.js:11248-11256).
- **Inventory:** `items` is an array from index 0, with `null` for empty slots. `isize` is 42. The server removes `null` entries after index 41. `esize` is the number of empty slots (node/server.js:1450-1463).
- **Bank packs:** `items0` … `items47` under `user` while the character is in the bank (js/old_common_functions.js:54-60).
- **Equipment slots** (`slots`): `ring1, ring2, earring1, earring2, belt, mainhand, offhand, helmet, chest, pants, shoes, gloves, amulet, orb, elixir, cape` (js/old_common_functions.js:104). Merchant stands also have `trade1` … `trade30` in use, from `trade_slots` up to `trade48` (js/old_common_functions.js:52-53, node/server_functions.js:4282-4299).
- **Item objects** (node/server_functions.js:4205-4232):
  - `name`: a key of `G.items`
  - `level`, `q` (quantity), `p` (special property, or upgrade state), `stat_type`
  - `m` (merchant luck), `v` (PvP), `l` (lock state), `b`, `r`, `skin`, `charges`, `data`
  - `expires`: a date string
  - `gift`, `acl` (account locked)
  - The server removes `grace, giveaway, gf, price, want, b, rid, list, o, oo, src` before it sends an item. Trade slots keep all fields except `grace, o, oo, src` (node/server_functions.js:4190-4203, 4234-4261).
- **Entity ids:** a character's `id` is its name (node/server.js:11779). Other characters carry `owner`, the owner's user id, unless the character is private (node/server.js:925). The `entities` payload is `{type: "all" or ..., in, map, players: [player_to_client(p, stranger)], monsters: [..]}` (node/server_functions.js:3676). When an entity leaves the view of a full refresh, the server sends `disappear {id, outside: true}` first (node/server_functions.js:3698-3700).
- **Ids in the database:** users `US_<29 chars>`, characters `CH_<29 chars>`, mail `ML_`, messages `MS_` (models.js:4, 33, 113, 125). Servers are `SR_<region><name>`, for example `SR_EUI` (node/server.js:462). A character's `home` has no prefix, for example `EUI`.
- **Times:**
  - Durations in conditions and skills are milliseconds, for example `s.notverified = {ms: 30*60*1000}` (node/server.js:11815).
  - `online` in the character list is the time in ms since `last_online` (adventure_functions.js:830).
  - Mail `sent` is a JavaScript `Date` string (api.js:1279). Message `date` is ISO `YYYY-MM-DDTHH:MM:SSZ` (api.js:1354). Chat `date` from `pull_chat` is a full ISO string with ms (api.js:1010).
- **Socket replies to actions** come as `game_response` objects: `{response, place: <event name>, success: true, ...}` or `{response, place, failed: true, ...}` (node/server_functions.js:3393-3446).
- **Localized messages:** `game_log`, `game_error` and other text events usually carry `{message, phrase, phrase_args, ...}`. `message` is the English text, and `phrase` is the key for other languages (languages/index.js:256-258). Some replies are still plain strings, for example `game_error "ERROR!"`.

## Observing without a character

Every socket that sends `loaded` becomes an observer. It gets `entities` and position updates for its instance until a successful `auth` (node/server.js:5028-5054, 11884-11886).

- **Without a secret**, the server selects the view:
  - Every 4 s, the server sets the camera spot to a random player who attacked in the last 3 s on a non-PvP map. If there is none, the spot is the merchant spot `main` (0, −50). On PvP servers the spot does not change from `winterland` (0, 0) (node/server.js:171-176, 15964-16001).
  - Every 13.2 s, an observer more than 200 px from the spot moves there with a `new_map` event (node/server.js:15931-15962, 4614-4638).
- **With `?secret=<character secret>`** (from `servers_and_characters`, only for your own online characters):
  - `welcome` includes that `character`, and the observer follows it (node/server.js:4989-5011, 15936-15946).
  - `o:home` moves the observer to the character (node/server.js:5055-5065).
  - `o:command <data>` sends `code_eval <data>` to the character's socket (node/server.js:5066-5076).
  - The secret is the random 24-character value that the game server made at `auth` (node/server.js:11593, 11629).
  - If the character is on a generated map, the secret works only with `map_protocol=1` (node/server.js:4992-4995).
- **With `?broadcast=1`** (no `secret`, no `no_graphics=1`, normal non-PvP servers only), the observer is a public broadcast camera. Every 250 ms the server sends `observer_broadcast {group, party, focus, map, x, y, online, remaining_ms, kind, available, town_players}` and moves the camera. It selects a new group every 30 s (node/logic/observer_broadcast.js:3-6, 173-199; node/server.js:15929).
- `send_updates` works for observers (node/server.js:5021-5023).
- The call-cost limit for a socket without a character is a quarter of the normal limit: 50 (node/server.js:4900-4906).

## Token JSON API

The token JSON API gives programs access to the game data and the account. It also controls CODE. One account token authorizes it (docs/articles/adventure-api.html:110-140).

### The token

- Make the token on the Mainframe page, or call `generate_token` with the auth cookie (api.js:411-425).
- The token is `mcp_` plus 43 base64url characters (mcp_api.js:3-4, 201).
- An account has one active token. A new token replaces the old one at once (mcp_api.js:210-243).
- `token_status` tells if a token exists. `reveal_token` returns it again, and `revoke_token` deletes it (mcp_api.js:245-288).
- The server rejects a token of a banned user (mcp_api.js:298).
- The token does not log in a game character. Socket `auth` needs the session token from `signup_or_login`.

**Note:** The token gives control of the account's saved CODE and Mainframe characters.

### Calls

Send `POST https://adventure.land/mcp_api/<method>` with a JSON body. Put the token in the body as `token`, next to the method's arguments:

```
curl https://adventure.land/mcp_api/get_servers \
  -H 'Content-Type: application/json' \
  -d '{"token":"YOUR_TOKEN"}'
```

`GET /mcp_api` returns `get_api_info`: the version, the method list with input schemas, and the rate limits (mcp_api.js:2042-2088, 3072-3075).

The server checks each call in this order (mcp_api.js:3000-3026, 2983-2998):

| Check | Reply |
|---|---|
| Unknown method | `{"failed":true,"reason":"invalid_call","name":<method>}` |
| The body is not a JSON object | `{"failed":true,"reason":"invalid_arguments"}` |
| No `token` | `{"failed":true,"reason":"missing_field","field":"token"}` |
| Bad token | `{"failed":true,"reason":"invalid_token"}` |
| Over the rate limit | HTTP 429, `Retry-After`, `{"failed":true,"reason":"rate_limited","retry_after_ms":N}` |
| Unknown field, or wrong type | `{"failed":true,"reason":"invalid_field","field":<name>}` |
| A required field is missing | `{"failed":true,"reason":"missing_field","field":<name>}` |
| The method throws | `{"failed":true,"reason":"exception"}` |

Types: `string` must be a JSON string. `number` must be a safe integer. `identifier` is a string or a number of 1 to 100 characters (mcp_api.js:2987-2991). All other replies are HTTP 200, so check `failed` in the body.

With HTTP 429, `Retry-After` is in seconds: `retry_after_ms / 1000`, rounded up, and at least 1 (mcp_api.js:3009-3015).

**Example:**

```js
// POST /mcp_api/<method> with the API token ("mcp_...") in the JSON body.
async function mcpApi(method, token, args = {}) {
  for (;;) {
    const res = await fetch(`https://adventure.land/mcp_api/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, ...args }),
    });
    if (res.status === 429) { // rate_limited. Retry-After is in seconds; the body has retry_after_ms.
      await new Promise((ok) => setTimeout(ok, Number(res.headers.get("Retry-After") ?? 1) * 1000));
      continue;
    }
    const data = await res.json(); // all other replies are HTTP 200
    if (data.failed) throw new Error(`${method}: ${data.reason}`); // e.g. "invalid_token"
    return data;
  }
}
// const { servers } = await mcpApi("get_servers", token);
// const { data } = await mcpApi("get_game_data", token, { section: "items", name: "hpot0" });
```

```ts
// POST /mcp_api/<method> with the API token ("mcp_...") in the JSON body.
type McpReply = { success: true; [field: string]: unknown } | { failed: true; reason: string; retry_after_ms?: number };

async function mcpApi(method: string, token: string, args: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
  for (;;) {
    const res = await fetch(`https://adventure.land/mcp_api/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, ...args }),
    });
    if (res.status === 429) { // rate_limited. Retry-After is in seconds; the body has retry_after_ms.
      await new Promise((ok) => setTimeout(ok, Number(res.headers.get("Retry-After") ?? 1) * 1000));
      continue;
    }
    const data = (await res.json()) as McpReply; // all other replies are HTTP 200
    if ("failed" in data) throw new Error(`${method}: ${data.reason}`); // e.g. "invalid_token"
    return data;
  }
}
// const reply = await mcpApi("get_game_data", token, { section: "items", name: "hpot0" });
```

```python
# POST /mcp_api/<method> with the API token ("mcp_...") in the JSON body.
async def mcp_api(http: httpx.AsyncClient, method: str, token: str, **args: object) -> dict:
    while True:
        res = await http.post(f"https://adventure.land/mcp_api/{method}", json={"token": token, **args})
        if res.status_code == 429:  # rate_limited. Retry-After is in seconds; the body has retry_after_ms.
            await asyncio.sleep(int(res.headers.get("Retry-After", "1")))
            continue
        data: dict = res.json()  # all other replies are HTTP 200
        if data.get("failed"):
            raise RuntimeError(f"{method}: {data['reason']}")  # e.g. "invalid_token"
        return data

# reply = await mcp_api(http, "get_game_data", token, section="items", name="hpot0")
```

```go
// McpAPI sends POST /mcp_api/<method> with the API token ("mcp_...") in the JSON body.
// Example: McpAPI("get_game_data", token, map[string]any{"section": "items", "name": "hpot0"})
func McpAPI(method, token string, args map[string]any) (map[string]any, error) {
	body := map[string]any{"token": token}
	for k, v := range args {
		body[k] = v
	}
	buf, _ := json.Marshal(body)
	for {
		res, err := http.Post("https://adventure.land/mcp_api/"+method, "application/json", bytes.NewReader(buf))
		if err != nil {
			return nil, err
		}
		if res.StatusCode == http.StatusTooManyRequests { // rate_limited
			res.Body.Close()
			seconds, _ := strconv.Atoi(res.Header.Get("Retry-After")) // seconds; the body has retry_after_ms
			time.Sleep(time.Duration(max(seconds, 1)) * time.Second)
			continue
		}
		var reply map[string]any // all other replies are HTTP 200
		err = json.NewDecoder(res.Body).Decode(&reply)
		res.Body.Close()
		if err != nil {
			return nil, err
		}
		if reply["failed"] == true {
			return nil, fmt.Errorf("%s: %v", method, reply["reason"]) // e.g. "invalid_token"
		}
		return reply, nil
	}
}
```

```csharp
// POST /mcp_api/<method> with the API token ("mcp_...") in the JSON body.
// Example: await McpApi("get_game_data", token, new() { ["section"] = "items", ["name"] = "hpot0" })
async Task<JsonElement> McpApi(string method, string token, Dictionary<string, object>? args = null)
{
    var body = new Dictionary<string, object>(args ?? new()) { ["token"] = token };
    while (true)
    {
        using var res = await http.PostAsJsonAsync($"https://adventure.land/mcp_api/{method}", body);
        if (res.StatusCode == System.Net.HttpStatusCode.TooManyRequests) // rate_limited
        {
            // Retry-After is in seconds; the body has retry_after_ms.
            await Task.Delay(res.Headers.RetryAfter?.Delta ?? TimeSpan.FromSeconds(1));
            continue;
        }
        var data = await res.Content.ReadFromJsonAsync<JsonElement>(); // all other replies are HTTP 200
        if (data.TryGetProperty("failed", out _))
            throw new Exception($"{method}: {data.GetProperty("reason")}"); // e.g. "invalid_token"
        return data;
    }
}
```

```rust
// POST /mcp_api/<method> with the API token ("mcp_...") in the JSON body.
// Example: mcp_api(&http, "get_game_data", &token, json!({"section": "items", "name": "hpot0"})).await?
async fn mcp_api(http: &reqwest::Client, method: &str, token: &str, mut args: Value) -> Result<Value, Error> {
    args["token"] = json!(token); // args must be a JSON object
    loop {
        let res = http.post(format!("https://adventure.land/mcp_api/{method}")).json(&args).send().await?;
        if res.status() == reqwest::StatusCode::TOO_MANY_REQUESTS { // rate_limited
            // Retry-After is in seconds; the body has retry_after_ms.
            let secs = res.headers().get("Retry-After").and_then(|v| v.to_str().ok()?.parse().ok()).unwrap_or(1);
            tokio::time::sleep(std::time::Duration::from_secs(secs)).await;
            continue;
        }
        let reply: Value = res.json().await?; // all other replies are HTTP 200
        if reply["failed"] == true {
            return Err(format!("{method}: {}", reply["reason"]).into()); // e.g. "invalid_token"
        }
        return Ok(reply);
    }
}
```

```java
// POST /mcp_api/<method> with the API token ("mcp_...") in the JSON body.
// Example: mcpApi("get_game_data", token, Map.of("section", "items", "name", "hpot0"))
static JsonNode mcpApi(String method, String token, Map<String, Object> args) throws Exception {
    var body = new HashMap<String, Object>(args);
    body.put("token", token);
    var req = HttpRequest.newBuilder(URI.create("https://adventure.land/mcp_api/" + method))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(JSON.writeValueAsString(body))).build();
    while (true) {
        var res = HTTP.send(req, HttpResponse.BodyHandlers.ofString());
        if (res.statusCode() == 429) { // rate_limited. Retry-After is in seconds; the body has retry_after_ms.
            Thread.sleep(1000L * Long.parseLong(res.headers().firstValue("Retry-After").orElse("1")));
            continue;
        }
        JsonNode reply = JSON.readTree(res.body()); // all other replies are HTTP 200
        if (reply.path("failed").asBoolean(false)) {
            throw new Exception(method + ": " + reply.path("reason").asText()); // e.g. "invalid_token"
        }
        return reply;
    }
}
```

The methods (mcp_api.js:2090-2199). The Arguments column gives `name: type`; `?` marks an optional field. Every reply has `success: true` unless the Failures column applies.

| Method | Arguments | Reply | Failures | Source |
|---|---|---|---|---|
| `get_api_info` | – | `{success, name, version, game_version, interfaces: {json, mcp, session}, onboarding, rate_limits, docs, methods: [{name, description, input_schema}]}`. `GET /mcp_api` gives the same object | – | mcp_api.js:2042-2088 |
| `get_servers` | – | `{success, servers}`. Each server: `key` (the config key), `name`, `region`, `address`, `path`, `msgpack_path`, `players`, `online`, `pvp` (boolean), `gameplay`, `version`, `last_update` | – | mcp_api.js:335-356 |
| `get_game_data` | `section?`: string; `name?`: string | No `section`: `{success, version, sections, catalog: [{section, description, count, searchable}], workflow}`. `section` only: `{success, version, section, data}`. Both: `{success, version, section, name, data}` | `missing_field` + `field: "section"` (a `name` without a `section`), `invalid_section`, `not_found` | mcp_api.js:358-389 |
| `search_game_data` | `query`: string; `match?`: `"all"` or `"any"` (default `"all"`); `section?`: a searchable section; `limit?`: number (1 to 50, default 25) | `{success, version, query, match, tokens, count, limit, results}`. Each result: `section`, `name`, and if present `label`, `description`, `type`, `class`, `level`, `tier`, `skin`, `map`; then `matched_fields`: at most 5 `{path, value}` | `invalid_query` + `field`, `message`, `details: {code, max_length, received_length, max_terms, received_terms}`, `syntax`, `example`. `details.code` is `query_too_long` (over 500 characters), `no_search_terms` or `too_many_terms` (over 32). `invalid_section` | mcp_api.js:490-556 |
| `list_docs` | `query?`: string (at most 100 characters) | `{success, count, articles: [{name, title, keywords, section, docs_url}]}` | `invalid_query` | mcp_api.js:558-642 |
| `get_doc` | `name`: identifier | `{success, article, format: "text", content}`. `article` is an item of `list_docs`; `content` is the article as plain text | `not_found` | mcp_api.js:644-660 |
| `list_code_methods` | `query?`: string (at most 100 characters); `limit?`: number (1 to 50; default 25 with a query, all without) | `{success, count, available, query, semantic, methods: [{name, signature, docs_url, summary?}]}`. `semantic` is true when no method name has the query, and the server matched the words of the documentation | `invalid_query` | mcp_api.js:717-775 |
| `get_code_method` | `name`: identifier | `{success, name, documentation, docs_url, source: {file, line?, repository_url, note?}}` | `not_found` | mcp_api.js:677-694 |
| `list_codes` | – | `{success, codes: [{slot, name, version}]}` | – | mcp_api.js:787-795 |
| `get_code` | `slot`: identifier (a slot, or a slot name in any case) | `{success, code: {slot, name, version, code}}` | `not_found` | mcp_api.js:776-805 |
| `get_libraries` | – | `{success, libraries: {"default_code.js", "runner_functions.js", "runner_compat.js", "common_functions.js"}}`, each the text of the file | – | mcp_api.js:807-817 |
| `save_code` | `slot`: identifier; `code`: string; `name?`: string | `{success, code: {slot, name, version}}` | `invalid_name` (the name `"DELETE"`), and each failure of the HTTP `save_code` | mcp_api.js:819-835 |
| `delete_code` | `slot`: identifier | `{success, slot}` | each failure of the HTTP `save_code` (`not_found` for a slot that does not exist) | mcp_api.js:837-851 |
| `get_bank` | – | `{success, source: "last_account_snapshot", observed_at: null, retrieved_at, freshness, stale, mounted_character_id, gold, packs, note}`, and `warning` when `stale`. `stale` is true while a character has the bank open; `freshness` is then `"possibly_stale"`, else `"unverified"`. `packs`: `{items<N>: [item or null]}`, item `{name, level?, q?, stat_type?, p?, locked?, blocked?}` | – | mcp_api.js:1199-1242 |
| `plan_character_progression` | `character`: identifier; `objective?`: `balanced_farming`, `damage`, `survival`, `support`, `gold`, `luck` or `xp` | `{success, source: "mcp_progression_context", observed_at, snapshot_id, character, character_id, class, level, objective, current, objectives, game_model, starting_points, evidence, bank, policy, note}`. Context for an AI; it does not rank items or choose actions | `character_not_found`; `unsupported_character_class` + `retryable: false`, `requested_class`, `supported_classes`; `progression_failed` + `stage`, `retryable: true`, `action` | mcp_api.js:1761-1875 |
| `browser_code_status` | `character`: identifier | `{success, character, runtime: "browser", server, online: true, code_running}`. An offline character: `{success, character, runtime: "browser", online: false, code_running: false}` | the target and relay failures below | mcp_api.js:974-981 |
| `browser_code_start` | `character`: identifier; `slot`: identifier | The relay reply + `requested_state: "running"`, `slot`. When CODE already runs: the status + `already_running: true`, `slot` | `code_not_found`, the target and relay failures | mcp_api.js:983-994 |
| `browser_code_stop` | `character`: identifier | The relay reply + `requested_state: "stopped"`. When no CODE runs: the status + `already_stopped: true` | the target and relay failures | mcp_api.js:996-1005 |
| `browser_code_reload` | `character`: identifier; `slot`: identifier | The relay reply + `requested_state: "running"`, `slot` | `code_not_found`, the target and relay failures | mcp_api.js:1007-1015 |
| `browser_code_eval` | `character`: identifier; `code`: string (1 byte to 64 KiB) | The relay reply | `invalid_code` + `max_bytes: 65536`, `received_bytes`; the target and relay failures | mcp_api.js:1017-1023 |
| `mainframe_code_eval` | `character`: identifier; `code`: string (1 byte to 64 KiB) | The relay reply, for a character on the Mainframe | the same as `browser_code_eval` | mcp_api.js:1025-1031 |
| `mainframe_list_characters` | – | `{success, online, updated_at, shells, contract, characters, free_time?}`. Each character: `character`, `character_id`, `level`, `class`, `profile`, `access`, `assignment`, `available`, `runtime` | – | mcp_api.js:1884-1922 |
| `mainframe_get_dashboard` | – | The reply of `mainframe_list_characters` + `codes` (as in `list_codes`) + `servers: [{server, region, name, players, online, pvp}]` | – | mcp_api.js:2023-2040 |
| `mainframe_get_character` | `character`: identifier | `{success, contract, shells, character, character_id, profile, access, assignment, available, runtime, free_time?}`. This `profile` also has `equipment`, `inventory`, `conditions` and `quests` | `character_not_found` | mcp_api.js:1924-1946 |
| `mainframe_link_character` | `character`: identifier; `request_id`: string (16 to 100 characters from `A-Z a-z 0-9 _ . : @ -`); `code_slot`: identifier; `server?`: string | `{success, queued: true, contract, billing, assignment, runtime}`. `billing`: `{success, charged, replayed, auto_renew, billing_source, steam_hours_charged, shells_charged, shells, receipt, access, next_charge_at, assignment}` | `character_not_found`, `mainframe_unavailable`, `invalid_request_id`, `code_not_found`, `server_not_found`, `request_already_used` + `access`, `access_expired` + `access`, `link_failed`; tx: `account_in_bank`, `assignment_conflict`, `character_already_linked`, `character_in_game`, `idempotency_conflict`, `mainframe_billing_unavailable`, `not_enough_shells` | mcp_api.js:1948-1967, mainframe.js:5, 436-619 |
| `mainframe_disconnect_character` | `character`: identifier | `{success, queued: true, assignment, runtime}` | `character_not_found`, `invalid_assignment`, `disconnect_failed`; tx: `mainframe_unavailable`, `shared_group_unavailable` | mcp_api.js:1969-1980, mainframe.js:853-930 |
| `mainframe_get_logs` | `character`: identifier; `limit?`: number (1 to 100, default 100) | `{success, active, retention_days: 30, logs}` | `character_not_found` | mcp_api.js:1982-2008 |
| `mainframe_get_events` | `character`: identifier; `limit?`: number (1 to 100, default 100) | `{success, active, retention_days: 30, events}` | `character_not_found` | mcp_api.js:2010-2021 |

The `browser_code_*` and `mainframe_code_eval` methods open a socket to the game server of the character with the character's `secret`. They send the CODE as `o:command` (mcp_api.js:898-968):

| Reply | Fields | When |
|---|---|---|
| Status (relay without CODE) | `{success, character, runtime, server, online: true, code_running}` | After `welcome` |
| Relay with CODE | `{success, character, runtime, server, online: true, code_running_before, queued: true, confirmed: false}` | 100 ms after the server sent `o:command`. The reply does not confirm that the CODE ran |
| Target failure (+ `character`, `runtime` where known) | `character_not_found`; `runtime_mismatch` (a browser method on a Mainframe character; `runtime: "mainframe"`); `mainframe_unavailable` (`mainframe_code_eval` on a character that is not on the Mainframe); `character_offline`; `server_unavailable` | Before the socket opens (mcp_api.js:859-896) |
| Relay failure (+ `character`, `runtime`) | `comm_unavailable`, `comm_timeout` (5 s), `comm_disconnected`, `browser_session_unavailable` (the socket's `welcome` is for another character) | While the socket is open |

### Rate limits

Each token has one bucket per class. A bucket holds `burst` calls and refills at `rate_per_minute` (mcp_api.js:130-190):

| Class | Rate per minute | Burst | Methods |
|---|---|---|---|
| standard | 120 | 30 | all others |
| bulk | 12 | 4 | `get_bank`; `get_game_data` without `name` |
| progression | 6 | 2 | `plan_character_progression` |
| write | 30 | 10 | `save_code`, `delete_code`, `browser_code_*` except status, `mainframe_code_eval`, `mainframe_link_character`, `mainframe_disconnect_character` |

The `mainframe_*` methods on `/api/<method>` use the same buckets, keyed by the account (mcp_api.js:3028-3034).
