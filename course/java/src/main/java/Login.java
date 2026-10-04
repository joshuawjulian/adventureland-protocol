// Login.java: log in over HTTP, then list the game servers and your characters.
// Uses albot.Api. Java 21; Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
// First run:  AL_EMAIL=you@example.com AL_PASSWORD=... mvn -q compile exec:java -Dexec.mainClass=Login
// Later runs: AL_AUTH=<user>-<auth> mvn -q compile exec:java -Dexec.mainClass=Login
//             (the first run prints the AL_AUTH value to save)
import albot.Api;

public class Login {
    public static void main(String[] args) throws Exception {
        Api.Auth auth = Api.login(); // AL_AUTH, or the password (then it prints the AL_AUTH value)
        System.out.println("user id: " + auth.user());
        var lists = Api.serversAndCharacters(auth);

        // AL_SERVER is region + name, for example "EUI".
        System.out.println("servers (AL_SERVER, players, address, path):");
        for (var s : lists.servers()) {
            System.out.printf("  %-8s %3d  %s  %s%n", s.region() + s.name(), s.players(), s.address(), s.path());
        }
        // AL_CHARACTER is the name. The id (CH_...) is what the socket `auth` sends.
        System.out.println("characters (AL_CHARACTER, class, level, id, status):");
        for (var c : lists.characters()) {
            String status = c.server() == null ? "offline" : "online on " + c.server(); // server: only while online
            System.out.printf("  %-8s %-9s %3d  %s  %s%n", c.name(), c.type(), c.level(), c.id(), status);
        }
    }
}
