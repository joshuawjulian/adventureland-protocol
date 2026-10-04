// Cooldowns.java: our copy of the cooldown timers, so that we do not send requests that fail.
// The server keeps the true timers; it tells us about them with events.
// Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
//
// Threads: the handlers run on the dispatcher thread of AlSocket, and ready() runs on the
// thread of your loop. So the timers are behind one lock: every method is synchronized.
package albot;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.HashMap;
import java.util.Map;
import java.util.regex.Pattern;

public final class Cooldowns {
    // region cooldowns
    // "pot_timeout(2000)": the potion timer started (node/server.js:7826-7878).
    static final Pattern POT = Pattern.compile("^pot_timeout\\((\\d+)");
    // "skill_timeout('ethereal',120)": a few skills start their cooldown this way.
    static final Pattern SKILL = Pattern.compile("^skill_timeout\\('([^']+)',\\s*(\\d+)");

    private final GData G;
    // Skill name (or "potion", the one timer that all potions share) -> the time in ms when it is ready.
    private final Map<String, Long> readyAt = new HashMap<>();

    /** Listens through world.listen, so that hitchhikers count too. */
    public Cooldowns(World world) {
        this.G = world.G;
        world.listen("skill_timeout", d -> start(d.path("name").asText(), d.path("ms").asDouble())); // after each skill
        world.listen("game_response", d -> {
            String code = d.path("response").asText(); // a string game_response has no fields: ""
            if (code.equals("cooldown")) start(d.path("skill").asText(d.path("place").asText()), d.path("ms").asDouble());
            if (code.equals("not_ready")) start("potion", d.path("ms").asDouble()); // the potion timer still runs
        });
        world.listen("eval", d -> {
            String code = d.isTextual() ? d.asText() : d.path("code").asText(); // a string or {code}
            var pot = POT.matcher(code);
            if (pot.find()) start("potion", Double.parseDouble(pot.group(1)));
            var skill = SKILL.matcher(code);
            if (skill.find()) start(skill.group(1), Double.parseDouble(skill.group(2)));
        });
    }

    /** The timer of `name` runs for `ms` from now. Also the skill whose cooldown it shares (3shot -> attack). */
    public synchronized void start(String name, double ms) {
        long at = System.currentTimeMillis() + (long) ms;
        readyAt.put(name, at);
        GData.SkillDef skill = G.skills().get(name);
        if (skill != null && skill.share() != null) readyAt.put(skill.share(), at);
    }

    /** True when the timer of `name` does not run. */
    public synchronized boolean ready(String name) {
        return msLeft(name) == 0;
    }

    /** The time in ms until `name` is ready; 0 when it is ready. */
    public synchronized long msLeft(String name) {
        return Math.max(0, readyAt.getOrDefault(name, 0L) - System.currentTimeMillis());
    }
    // endregion cooldowns
}
