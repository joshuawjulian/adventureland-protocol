// Connect.java: log in, enter the game with one character, print where it is, leave.
// Uses albot.Bot. Java 21; Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
// Run: AL_AUTH=<user>-<auth> AL_CHARACTER=<name> mvn -q compile exec:java -Dexec.mainClass=Connect
//      (AL_SERVER is optional: without it, the program uses the first server of the list.)
import albot.Bot;

public class Connect {
    public static void main(String[] args) throws Exception {
        Bot bot = Bot.connect(); // HTTP login, G, socket, handshake
        try {
            System.out.printf("welcome: %s %s, version %d%n", bot.welcome.path("region").asText(),
                    bot.welcome.path("name").asText(), bot.welcome.path("version").asInt());
            synchronized (bot.world) { // the dispatcher thread changes `me`: hold the lock to read it
                var me = bot.world.me;
                // `start` has no `name`: the id of a character is its name.
                System.out.printf("in game as %s (%s, level %d) on %s at %d,%d%n",
                        me.path("id").asText(), me.path("ctype").asText(), me.path("level").asInt(),
                        me.path("map").asText(), Math.round(me.path("x").asDouble()), Math.round(me.path("y").asDouble()));
            }
            System.out.println("OK");
        } finally {
            bot.close(); // the server then saves the character and marks it offline
        }
    }
}
