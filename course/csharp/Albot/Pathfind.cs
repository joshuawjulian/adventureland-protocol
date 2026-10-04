// Pathfind.cs: a walkable grid of one map, built from G.geometry, and A* on
// it, so that a character can walk around walls.
//
// The server does not walk around walls for you. A `move` goes in a straight
// line, and a `move` from or to a point that is not walkable is a "line
// violation": the server sends the character to jail (node/server.js:11211-
// 11245). So a bot plans its own route, on its own copy of the walls.
//
// Threads: a Grid does not change after it is built, so any thread can use it.
// ForMap keeps one grid per map behind a lock.
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;

namespace Albot;

public sealed class Grid
{
    // region grid
    // 8 px cells: small enough that narrow passages stay open, big enough that
    // `main` (3,936 x 3,272 px) is about 492 x 410 = 200,000 cells.
    private const int Cell = 8;
    // The box around the feet of a character that must stay clear of walls: 8 px
    // to the left and right, 7 px up, 2 px down (the player "base", node/server.js:185).
    private const double BaseH = 8, BaseV = 7, BaseVn = 2;
    // Half a cell more, so that "the nearest cell is walkable" also means "this
    // exact point is walkable".
    private const double Margin = Cell / 2.0;
    // NearestFree() gives up after 40 cells (320 px): a point farther than that
    // from walkable ground is outside the map.
    private const int SearchCells = 40;

    // G -> map name -> grid. A weak table: a G that nobody uses goes away with its grids.
    private static readonly ConditionalWeakTable<GData, Dictionary<string, Grid>> Cache = new();

    private readonly double _minX, _minY;
    private readonly int _w, _h;
    private readonly bool[] _free; // true: a character can stand in this cell

    /// <summary>The grid of one map (a key of G.maps), from G.geometry[map]. It is
    /// built once for each map and kept: building `main` takes about 100 ms.</summary>
    public static Grid ForMap(GData G, string map)
    {
        var grids = Cache.GetValue(G, _ => []);
        lock (grids)
        {
            if (!grids.TryGetValue(map, out var grid))
            {
                var geo = G.Raw["geometry"]?[map] as JsonObject
                    ?? throw new InvalidOperationException($"no geometry for the map {map} in G");
                grid = new Grid(geo, G.Raw["maps"]?[map]?["spawns"] as JsonArray ?? []);
                grids[map] = grid;
            }
            return grid;
        }
    }

    private Grid(JsonObject geo, JsonArray spawns)
    {
        _minX = geo.Num("min_x");
        _minY = geo.Num("min_y");
        _w = (int)Math.Floor((geo.Num("max_x") - _minX) / Cell) + 1;
        _h = (int)Math.Floor((geo.Num("max_y") - _minY) / Cell) + 1;
        var wall = new bool[_w * _h]; // true: too near a wall

        // Block each cell whose centre is in the rectangle [x0, x1] x [y0, y1].
        void Block(double x0, double y0, double x1, double y1)
        {
            int i0 = Math.Max(0, (int)Math.Ceiling((x0 - _minX) / Cell));
            int i1 = Math.Min(_w - 1, (int)Math.Floor((x1 - _minX) / Cell));
            int j0 = Math.Max(0, (int)Math.Ceiling((y0 - _minY) / Cell));
            int j1 = Math.Min(_h - 1, (int)Math.Floor((y1 - _minY) / Cell));
            for (var j = j0; j <= j1; j++)
                for (var i = i0; i <= i1; i++) wall[j * _w + i] = true;
        }
        // x_lines are vertical walls [x, y1, y2]; y_lines are horizontal walls
        // [y, x1, x2]. A cell is blocked if the base box, standing there, would
        // touch the wall (with the margin).
        foreach (var l in geo["x_lines"] as JsonArray ?? [])
        {
            double x = l![0]!.GetValue<double>(), y1 = l[1]!.GetValue<double>(), y2 = l[2]!.GetValue<double>();
            Block(x - BaseH - Margin, y1 - BaseVn - Margin, x + BaseH + Margin, y2 + BaseV + Margin);
        }
        foreach (var l in geo["y_lines"] as JsonArray ?? [])
        {
            double y = l![0]!.GetValue<double>(), x1 = l[1]!.GetValue<double>(), x2 = l[2]!.GetValue<double>();
            Block(x1 - BaseH - Margin, y - BaseVn - Margin, x2 + BaseH + Margin, y + BaseV + Margin);
        }

        // The walls do not say which side is the inside of the map. The server
        // finds it with a flood fill from the spawn points (server_bfs,
        // node/server_functions.js:4732). We do the same: only the cells that a
        // spawn can reach are walkable.
        _free = new bool[_w * _h];
        var stack = new Stack<int>();
        foreach (var s in spawns)
        {
            var k = CellOf(s![0]!.GetValue<double>(), s[1]!.GetValue<double>());
            if (k >= 0 && !wall[k] && !_free[k]) { _free[k] = true; stack.Push(k); }
        }
        int[] di = [1, -1, 0, 0], dj = [0, 0, 1, -1];
        while (stack.Count > 0)
        {
            var k = stack.Pop(); // the order does not matter in a flood fill
            int i = k % _w, j = k / _w;
            for (var d = 0; d < 4; d++)
            {
                int ni = i + di[d], nj = j + dj[d];
                if (ni < 0 || nj < 0 || ni >= _w || nj >= _h) continue;
                var nk = nj * _w + ni;
                if (!wall[nk] && !_free[nk]) { _free[nk] = true; stack.Push(nk); }
            }
        }
    }

    /// <summary>The index of the cell nearest to (x, y), or -1 outside the grid. (Floor of
    /// x + 0.5 rounds as JavaScript's Math.round does, so all languages agree.)</summary>
    public int CellOf(double x, double y)
    {
        var i = (int)Math.Floor((x - _minX) / Cell + 0.5);
        var j = (int)Math.Floor((y - _minY) / Cell + 0.5);
        return i >= 0 && j >= 0 && i < _w && j < _h ? j * _w + i : -1;
    }

    /// <summary>The centre of cell k, as a map point.</summary>
    public (double X, double Y) Point(int k) => (_minX + k % _w * Cell, _minY + k / _w * Cell);

    /// <summary>True if a character can stand at (x, y): its nearest cell is walkable.</summary>
    public bool Safe(double x, double y)
    {
        var k = CellOf(x, y);
        return k >= 0 && _free[k];
    }

    /// <summary>True if the straight line from a to b crosses no wall. It tests a
    /// point every half cell (4 px). A wall is at least a margin away from each free
    /// cell, so a line that crosses a wall always has a point in a blocked cell.</summary>
    public bool LineClear(double ax, double ay, double bx, double by)
    {
        var n = (int)Math.Ceiling(Math.Sqrt((bx - ax) * (bx - ax) + (by - ay) * (by - ay)) / (Cell / 2.0));
        for (var s = 0; s <= n; s++)
        {
            var t = n == 0 ? 0 : (double)s / n;
            if (!Safe(ax + (bx - ax) * t, ay + (by - ay) * t)) return false;
        }
        return true;
    }

    /// <summary>The walkable cell nearest to (x, y), in rings around it; -1 if none
    /// is in 40 cells.</summary>
    public int NearestFree(double x, double y)
    {
        var ci = (int)Math.Floor((x - _minX) / Cell + 0.5);
        var cj = (int)Math.Floor((y - _minY) / Cell + 0.5);
        for (var r = 0; r <= SearchCells; r++)
            for (var j = cj - r; j <= cj + r; j++)
                for (var i = ci - r; i <= ci + r; i++)
                {
                    if (Math.Max(Math.Abs(i - ci), Math.Abs(j - cj)) != r) continue; // the ring only
                    if (i >= 0 && j >= 0 && i < _w && j < _h && _free[j * _w + i]) return j * _w + i;
                }
        return -1;
    }
    // endregion grid

    // region find-path
    /// <summary>
    /// The points to walk through from (sx, sy) to (gx, gy), not including the
    /// start, or null when there is no path. Each pair of points next to each
    /// other has a clear straight line, so each point is one `move`.
    /// </summary>
    public List<(double X, double Y)>? FindPath(double sx, double sy, double gx, double gy)
    {
        var start = NearestFree(sx, sy);
        var goal = CellOf(gx, gy);
        if (start < 0 || goal < 0 || !_free[goal]) return null; // the goal must be walkable
        var n = _w * _h;
        int gi = goal % _w, gj = goal / _w;
        var cost = new double[n]; // the best cost from the start
        Array.Fill(cost, double.PositiveInfinity);
        var came = new int[n]; // the cell before this one on the best path
        Array.Fill(came, -1);
        var done = new bool[n]; // the closed set
        // The octile distance: the exact cost on an empty grid with diagonal
        // steps. It never overestimates, so A* finds the shortest path.
        double Guess(int k)
        {
            double dx = Math.Abs(k % _w - gi), dy = Math.Abs(k / _w - gj);
            return dx + dy + (Math.Sqrt(2) - 2) * Math.Min(dx, dy);
        }
        var heap = new PriorityQueue<int, double>(); // .NET has a min-heap built in
        cost[start] = 0;
        heap.Enqueue(start, Guess(start));
        while (heap.Count > 0)
        {
            var k = heap.Dequeue();
            if (k == goal) break;
            if (done[k]) continue; // an old heap entry
            done[k] = true;
            int i = k % _w, j = k / _w;
            for (var dj = -1; dj <= 1; dj++)
                for (var di = -1; di <= 1; di++)
                {
                    if (di == 0 && dj == 0) continue;
                    int ni = i + di, nj = j + dj;
                    if (ni < 0 || nj < 0 || ni >= _w || nj >= _h) continue;
                    var nk = nj * _w + ni;
                    if (!_free[nk] || done[nk]) continue;
                    // No diagonal step past a corner: both side cells must be free.
                    if (di != 0 && dj != 0 && !(_free[j * _w + ni] && _free[nj * _w + i])) continue;
                    var c = cost[k] + (di != 0 && dj != 0 ? Math.Sqrt(2) : 1);
                    if (c < cost[nk])
                    {
                        cost[nk] = c;
                        came[nk] = k;
                        heap.Enqueue(nk, c + Guess(nk));
                    }
                }
        }
        if (goal != start && came[goal] < 0) return null;

        // The cells from the start to the goal, as map points. The first point is
        // our real position when it is walkable, so that the first line is tested
        // from where we stand; the last point is the exact goal.
        var cells = new List<(double X, double Y)>();
        for (var k = goal; k != -1; k = came[k]) cells.Add(Point(k));
        cells.Reverse();
        if (Safe(sx, sy)) cells[0] = (sx, sy);
        if (cells.Count == 1) cells.Add((gx, gy));
        else cells[^1] = (gx, gy);

        // Smooth the route: from each point, go to the farthest later point that
        // a straight line reaches. Each `move` costs call-cost, so fewer is better.
        var output = new List<(double X, double Y)>();
        var a = 0;
        while (a < cells.Count - 1)
        {
            var b = a + 1;
            while (b + 1 < cells.Count && LineClear(cells[a].X, cells[a].Y, cells[b + 1].X, cells[b + 1].Y)) b++;
            output.Add(cells[b]);
            a = b;
        }
        return output;
    }
    // endregion find-path
}
