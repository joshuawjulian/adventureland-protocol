# Writing style: Simplified Technical English

All prose on all three pages follows **ASD-STE100 Simplified Technical English** (STE), the
controlled-English standard from aerospace maintenance manuals. The owner asked for it on
2026-10-04. STE makes text easy to read for non-native speakers and easy to translate. These
are the rules we apply (adapted from STE Issue 9; we don't use the official approved-word
dictionary, but we do follow its spirit):

## Words

1. Use **simple, common words**. Write "use" instead of "utilize", "start" instead of
   "initiate", "about" instead of "approximately", "help" instead of "facilitate".
2. Use **one word for one meaning**, and keep it. If you call it a "character", don't later call
   it a "toon" or "avatar". If a word has a technical meaning here (event, entry, payload,
   socket), don't also use it in its everyday sense.
3. **Technical names and technical verbs are allowed**: event names, field names, code
   identifiers, protocol terms (`emit`, WebSocket, frame, handshake, cooldown, aggro). Define a
   technical term the first time it appears on a page.
4. **No phrasal verbs** when a single verb exists: "start" not "set up", "find" not
   "find out", "stop" not "shut down", "continue" not "keep on". (Code names like `set_home`
   are fine; they are technical names.)
5. **Noun clusters: three words maximum.** Write "the cooldown of the attack skill", not "attack
   skill cooldown timer value".
6. Use articles ("a", "the") and "that" where they make the sentence clear. Don't drop them to
   save space.

## Sentences

7. **Procedural text** (steps the reader does): **20 words maximum** per sentence. Use the
   **imperative** ("Send `loaded`."). **One instruction per sentence**, unless two actions
   happen at the same time. Put a condition first: "If the server sends `game_error`, stop."
8. **Descriptive text** (explanations): **25 words maximum** per sentence.
9. **Active voice.** "The server sends `start`", not "`start` is sent". Passive voice is only
   for when the actor is unknown or doesn't matter, and then sparingly.
10. **Simple tenses**: present, simple past, simple future. Avoid "would have been", "is being
    sent", and similar forms.
11. **Avoid -ing forms** as nouns or adjectives where a clearer form exists ("the queue of
    events" rather than "the pending queue"). Technical names are exempt.
12. **One topic per sentence.** Split sentences joined by "and", "which" or semicolons when each
    part is its own statement.

## Paragraphs and structure

13. **One topic per paragraph; six sentences maximum.** Start with the topic sentence.
14. Use **numbered lists for steps** in order, **bulleted lists** for unordered items, and
    **tables** for comparisons and field lists.
15. Put **warnings and cautions first**, before the step they apply to, as a blockquote:
    `> **Warning:** ...` (risk to the account or data) or `> **Caution:** ...` (risk of a kick,
    a lost item or wasted gold).
16. Write numbers as digits with units: "4 s", "200 call-cost", "1,000 gold".

## What STE does not change here

- **Accuracy rules stay**: write "unclear from the source" rather than guess; flag server bugs
  plainly; cite `file.js:LINE`.
- **Code and code comments** follow docs/EXAMPLES.md. Comments use short, plain English, and
  the same STE word choices, but they are not held to the sentence limits.
- Quoted identifiers, response codes and payloads stay exactly as the server spells them,
  typos included (`"chellenge"`).

## Example

Before: "Once you've gotten the welcome event, you'll want to go ahead and send loaded, which
is necessary because the server won't actually process auth until that's been received."

After: "Wait for `welcome`. Then send `loaded`. The server ignores `auth` until it receives
`loaded`."
