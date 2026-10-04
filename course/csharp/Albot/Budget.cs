// Budget.cs: the call-cost budget. The server adds a cost for each event that
// we send, over the last 4 s. Above 200, it disconnects us ("limitdc").
// This class waits before an emit that would go over our limit.
//
// Threads: the new_map handler runs on the dispatcher thread of AlSocket, and
// EmitAsync runs on the thread of your program. So one lock guards the list.
namespace Albot;

// region budget
public sealed class Budget
{
    /// <summary>
    /// The extra cost of some events (node/server.js:242-258, CC). Each event
    /// costs 1, plus this (node/server.js:4892-4943).
    /// </summary>
    public static readonly IReadOnlyDictionary<string, double> ExtraCost = new Dictionary<string, double>
    {
        ["auth"] = 2, ["move"] = 1.5, ["players"] = 12, ["secondhands"] = 16, ["friend"] = 24,
        ["send_updates"] = 12, ["cruise"] = 10, ["random_look"] = 10, ["equip"] = 3, ["unequip"] = 6,
        ["tracker"] = 50, ["ccreport"] = 3,
    };

    /// <summary>150 of the server's 200: some replies resend `player` and add cost that we cannot see.</summary>
    public const double Limit = 150;
    /// <summary>The window of the server: the cost of the last 4 s counts.</summary>
    public const int WindowMs = 4000;

    private readonly AlSocket _sock;
    private readonly object _lock = new();
    private readonly Queue<(long At, double Cost)> _spent = new(); // oldest first; At in ms

    public Budget(AlSocket sock, World world)
    {
        _sock = sock;
        // A map change costs 8: add_call_cost(player, 8, "transport") (node/server.js:4726).
        world.Listen("new_map", _ => Record(8));
    }

    public double Cost(string evt) => 1 + ExtraCost.GetValueOrDefault(evt);

    /// <summary>The total cost of the last 4 s.</summary>
    public double Spent()
    {
        lock (_lock)
        {
            Prune();
            return _spent.Sum(s => s.Cost);
        }
    }

    /// <summary>Waits until the last 4 s have room for this event, records its cost, then sends it.</summary>
    public async Task EmitAsync(string evt, object? payload = null)
    {
        var cost = Cost(evt);
        while (true)
        {
            long wait;
            lock (_lock)
            {
                Prune();
                if (_spent.Count == 0 || _spent.Sum(s => s.Cost) + cost <= Limit)
                {
                    _spent.Enqueue((Environment.TickCount64, cost));
                    break;
                }
                // Full: wait until the oldest cost leaves the window (+10 ms to be sure).
                wait = _spent.Peek().At + WindowMs - Environment.TickCount64 + 10;
            }
            await Task.Delay(TimeSpan.FromMilliseconds(Math.Max(wait, 1))); // never wait with the lock held
        }
        await _sock.EmitAsync(evt, payload);
    }

    private void Record(double cost)
    {
        lock (_lock) _spent.Enqueue((Environment.TickCount64, cost));
    }

    // Removes the costs that are older than the window. Call it with _lock held.
    private void Prune()
    {
        var now = Environment.TickCount64;
        while (_spent.Count > 0 && now - _spent.Peek().At > WindowMs) _spent.Dequeue();
    }
}
// endregion budget
