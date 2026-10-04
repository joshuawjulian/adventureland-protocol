// Party.java: several characters in one program, a party, and a new character.
// Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
//
// The program logs in once, reads the server and character lists once and loads G once. Then
// connectMember() opens one socket for each character. Each character has its own World,
// Cooldowns, Budget and Actions: the server counts the call-cost for each socket.
//
// Threads: the party state (list, invites) is behind the lock of the Party object: the
// dispatcher writes it, the program's threads read it.
package albot;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class Party {
    // region member
    /**
     * One character in the game: the same parts as a Bot. (Bot's constructor is private, and a
     * Member needs no HTTP of its own.)
     */
    public record Member(String name, AlSocket sock, GData G, World world, Cooldowns cooldowns,
                         Budget budget, Actions act, Api.Character character) {
        public void close() {
            sock.close();
        }
    }

    /**
     * Connects one character with a login, a server and a G that we already have:
     * Bot.connectWith (Bot.connect without the HTTP calls).
     */
    public static Member connectMember(Api.Auth auth, Api.Server server, Api.Character character, GData G)
            throws IOException, InterruptedException, Bot.LoginError {
        Bot bot = Bot.connectWith(auth, server, character, G);
        return new Member(character.name(), bot.sock, G, bot.world, bot.cooldowns, bot.budget, bot.act, character);
    }
    // endregion member

    // region create-character
    /**
     * Makes a new character on the account: HTTP `create_character` {name, char}
     * (api.js:474-588). The name: 4 to 12 letters, digits or "_", not used by anyone
     * (api.js:24-31). The answer is {success: true}, or {failed: true, reason}: "name_used",
     * "invalid_name", "reached_character_limit", ...
     */
    public static JsonNode createCharacter(Api.Auth auth, String name, String ctype) throws IOException, InterruptedException {
        JsonNode r = Api.apiCall("create_character", Map.of("name", name, "char", ctype), auth);
        if (r.path("failed").asBoolean()) throw new IOException("create_character failed: " + r.path("reason").asText());
        return r;
    }
    // endregion create-character

    // region party
    // The party of one character. The server sends `invite` {name} to the character that gets an
    // invitation, and `party_update` {list, party} to each member when the party changes
    // (node/server.js:12357-12546).
    private final Actions act;
    private List<String> list = List.of(); // the names in our party, the leader first; guarded by `this`
    private final Set<String> invites = new HashSet<>(); // who invited us; guarded by `this`

    public Party(World world, Actions act) {
        this.act = act;
        world.listen("invite", d -> {
            synchronized (this) { invites.add(d.path("name").asText()); }
        });
        // {} (no list) when we left or the party ended.
        world.listen("party_update", d -> {
            List<String> names = new java.util.ArrayList<>();
            for (JsonNode n : d.path("list")) names.add(n.asText());
            synchronized (this) { list = List.copyOf(names); }
        });
    }

    /** The names in our party, the leader first. Empty when we are in no party. */
    public synchronized List<String> list() {
        return list;
    }

    /**
     * Invites `name` (a character on this server). The answer is a success with place "party",
     * or "invalid" (no such character), "party_full".
     */
    public Actions.GameResponse invite(String name) throws InterruptedException {
        return act.request("party", Map.of("event", "invite", "name", name));
    }

    /** Accepts the invitation of `name`. It fails with "invitation_expired" when there was no invitation. */
    public Actions.GameResponse accept(String name) throws InterruptedException {
        return act.request("party", Map.of("event", "accept", "name", name));
    }

    public Actions.GameResponse leave() throws InterruptedException {
        return act.request("party", Map.of("event", "leave"));
    }

    /** Waits until `name` invited us (true), or `ms` passed (false). */
    public boolean waitInvite(String name, long ms) throws InterruptedException {
        return Travel.waitUntil(() -> {
            synchronized (this) { return invites.contains(name); }
        }, ms);
    }

    /** waitInvite with 5 s. */
    public boolean waitInvite(String name) throws InterruptedException {
        return waitInvite(name, 5000);
    }
    // endregion party
}
