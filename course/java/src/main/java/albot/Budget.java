// Budget.java: stay under the call-cost limit of the server, so that it does not disconnect us.
// Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
//
// Threads: emit() runs on the threads of your code, and the new_map handler runs on the
// dispatcher thread of AlSocket. So the list of calls is behind one lock: the methods that
// read or change it are synchronized. emit() sleeps OUTSIDE the lock, so that a wait for room
// never blocks the handlers.
package albot;

import java.util.ArrayDeque;
import java.util.Map;

public final class Budget {
    // region budget
    /**
     * The extra cost of each event (node/server.js:242-258). Every event costs 1 plus this.
     * The server allows 200 per 4 s for a socket with a character, 50 before `auth`
     * (node/server.js:4892-4943). Over the limit, it sends `disconnect_reason` "limitdc" and closes.
     */
    public static final Map<String, Double> EXTRA_COST = Map.ofEntries(
            Map.entry("auth", 2.0), Map.entry("move", 1.5), Map.entry("players", 12.0),
            Map.entry("secondhands", 16.0), Map.entry("friend", 24.0), Map.entry("send_updates", 12.0),
            Map.entry("cruise", 10.0), Map.entry("random_look", 10.0), Map.entry("equip", 3.0),
            Map.entry("unequip", 6.0), Map.entry("tracker", 50.0), Map.entry("ccreport", 3.0));
    /** 150, not 200: an event that makes the server resend `player` adds up to 2 that we cannot see. */
    public static final double LIMIT = 150;
    /** The window of the server: the last 4 s. */
    public static final long WINDOW_MS = 4000;

    private final AlSocket sock;
    private final ArrayDeque<double[]> calls = new ArrayDeque<>(); // {time in ms, cost}, oldest first

    /** Also counts each map change: the server adds 8 for it (add_call_cost(player, 8, "transport")). */
    public Budget(AlSocket sock, World world) {
        this.sock = sock;
        world.listen("new_map", d -> record(8));
    }

    /** The cost of one event: 1 plus its extra cost. */
    public static double cost(String event) {
        return 1 + EXTRA_COST.getOrDefault(event, 0.0);
    }

    private synchronized void record(double cost) {
        calls.addLast(new double[] {System.currentTimeMillis(), cost});
    }

    /** The total cost of the last 4 s. */
    public synchronized double spent() {
        long now = System.currentTimeMillis();
        while (!calls.isEmpty() && now - calls.peekFirst()[0] > WINDOW_MS) calls.pollFirst(); // forget old calls
        return calls.stream().mapToDouble(c -> c[1]).sum();
    }

    /** Waits until the last 4 s have room for this event, records its cost, then sends it. */
    public void emit(String event, Object payload) throws InterruptedException {
        double cost = cost(event);
        while (true) {
            long wait;
            synchronized (this) {
                if (spent() + cost <= LIMIT) {
                    record(cost); // in the same lock as the check: two threads cannot both use the last room
                    break;
                }
                // Until the oldest call leaves the window, plus 10 ms so that it is surely gone.
                wait = WINDOW_MS - (System.currentTimeMillis() - (long) calls.peekFirst()[0]) + 10;
            }
            Thread.sleep(Math.max(wait, 1));
        }
        sock.emit(event, payload);
    }

    /** emit with no payload. */
    public void emit(String event) throws InterruptedException {
        emit(event, null);
    }
    // endregion budget
}
