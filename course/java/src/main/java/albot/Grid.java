// Grid.java: a walkable grid of one map, built from G.geometry, and A* on it, so that a
// character can walk around walls. Java 21. Maven: com.fasterxml.jackson.core:jackson-databind:2.18.2
//
// The server does not walk around walls for you. A `move` goes in a straight line, and a `move`
// from or to a point that is not walkable is a "line violation": the server sends the character
// to jail (node/server.js:11211-11245). So a bot plans its own route, on its own copy of the walls.
//
// Threads: a Grid does not change after forMap builds it, so many threads can read it. The cache
// of forMap is synchronized.
package albot;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.IdentityHashMap;

public final class Grid {
    // region grid
    // 8 px cells: small enough that narrow passages stay open, big enough that `main`
    // (3,936 x 3,272 px) is about 492 x 410 = 200,000 cells.
    static final int CELL = 8;
    // The box around the feet of a character that must stay clear of walls: 8 px to the left and
    // right, 7 px up, 2 px down (the player "base", node/server.js:185).
    static final double BASE_H = 8, BASE_V = 7, BASE_VN = 2;
    // Half a cell more, so that "the nearest cell is walkable" also means "this exact point is walkable".
    static final double MARGIN = CELL / 2.0;
    // nearestFree() gives up after 40 cells (320 px): a point farther than that from walkable
    // ground is outside the map.
    static final int SEARCH_CELLS = 40;

    /**
     * G -> map name -> grid. By identity: GData is a record, and its equals and hashCode would
     * compare all of G each time.
     */
    private static final Map<GData, Map<String, Grid>> CACHE = new IdentityHashMap<>();

    private final double minX, minY;
    private final int w, h;
    private final boolean[] free; // true: a character can stand in this cell

    /**
     * The grid of `map` (a key of G.maps), from G.geometry[map]. It is built once for each map and
     * kept: building `main` takes about 100 ms.
     */
    public static Grid forMap(GData G, String map) {
        synchronized (CACHE) {
            Map<String, Grid> grids = CACHE.computeIfAbsent(G, k -> new HashMap<>());
            Grid grid = grids.get(map);
            if (grid == null) {
                JsonNode geo = G.raw().path("geometry").path(map);
                if (!geo.isObject()) throw new IllegalArgumentException("no geometry for the map " + map + " in G");
                grid = new Grid(geo, G.raw().path("maps").path(map).path("spawns"));
                grids.put(map, grid);
            }
            return grid;
        }
    }

    private Grid(JsonNode geo, JsonNode spawns) {
        minX = geo.path("min_x").asDouble();
        minY = geo.path("min_y").asDouble();
        w = (int) Math.floor((geo.path("max_x").asDouble() - minX) / CELL) + 1;
        h = (int) Math.floor((geo.path("max_y").asDouble() - minY) / CELL) + 1;
        boolean[] wall = new boolean[w * h]; // true: too near a wall

        // x_lines are vertical walls [x, y1, y2]; y_lines are horizontal walls [y, x1, x2]. A cell
        // is blocked if the base box, standing there, would touch the wall (with the margin).
        for (JsonNode l : geo.path("x_lines")) {
            double x = l.path(0).asDouble(), y1 = l.path(1).asDouble(), y2 = l.path(2).asDouble();
            block(wall, x - BASE_H - MARGIN, y1 - BASE_VN - MARGIN, x + BASE_H + MARGIN, y2 + BASE_V + MARGIN);
        }
        for (JsonNode l : geo.path("y_lines")) {
            double y = l.path(0).asDouble(), x1 = l.path(1).asDouble(), x2 = l.path(2).asDouble();
            block(wall, x1 - BASE_H - MARGIN, y - BASE_VN - MARGIN, x2 + BASE_H + MARGIN, y + BASE_V + MARGIN);
        }

        // The walls do not say which side is the inside of the map. The server finds it with a
        // flood fill from the spawn points (server_bfs, node/server_functions.js:4732). We do the
        // same: only the cells that a spawn can reach are walkable.
        free = new boolean[w * h];
        var queue = new ArrayDeque<Integer>();
        for (JsonNode s : spawns) {
            int k = cell(s.path(0).asDouble(), s.path(1).asDouble());
            if (k >= 0 && !wall[k] && !free[k]) {
                free[k] = true;
                queue.push(k);
            }
        }
        int[][] dirs = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
        while (!queue.isEmpty()) {
            int k = queue.pop(); // the order does not matter in a flood fill
            int i = k % w, j = k / w;
            for (int[] d : dirs) {
                int ni = i + d[0], nj = j + d[1];
                if (ni < 0 || nj < 0 || ni >= w || nj >= h) continue;
                int nk = nj * w + ni;
                if (!wall[nk] && !free[nk]) {
                    free[nk] = true;
                    queue.push(nk);
                }
            }
        }
    }

    /** Blocks each cell whose centre is in the rectangle [x0, x1] x [y0, y1]. */
    private void block(boolean[] wall, double x0, double y0, double x1, double y1) {
        int i0 = Math.max(0, (int) Math.ceil((x0 - minX) / CELL));
        int i1 = Math.min(w - 1, (int) Math.floor((x1 - minX) / CELL));
        int j0 = Math.max(0, (int) Math.ceil((y0 - minY) / CELL));
        int j1 = Math.min(h - 1, (int) Math.floor((y1 - minY) / CELL));
        for (int j = j0; j <= j1; j++) for (int i = i0; i <= i1; i++) wall[j * w + i] = true;
    }

    /** The index of the cell nearest to (x, y), or -1 outside the grid. */
    public int cell(double x, double y) {
        long i = Math.round((x - minX) / CELL), j = Math.round((y - minY) / CELL); // Math.round: as JS
        return i >= 0 && j >= 0 && i < w && j < h ? (int) (j * w + i) : -1;
    }

    /** The centre {x, y} of cell k. */
    public double[] point(int k) {
        return new double[] {minX + (k % w) * CELL, minY + (k / w) * CELL};
    }

    /** Can a character stand at (x, y)? (Its nearest cell is walkable.) */
    public boolean safe(double x, double y) {
        int k = cell(x, y);
        return k >= 0 && free[k];
    }

    /**
     * Is the straight line from a to b clear of walls? It tests a point every half cell (4 px). A
     * wall is at least a margin away from each free cell, so a line that crosses a wall always has
     * a point in a blocked cell.
     */
    public boolean lineClear(double ax, double ay, double bx, double by) {
        int n = (int) Math.ceil(Math.hypot(bx - ax, by - ay) / (CELL / 2.0));
        for (int s = 0; s <= n; s++) {
            double t = n == 0 ? 0 : (double) s / n;
            if (!safe(ax + (bx - ax) * t, ay + (by - ay) * t)) return false;
        }
        return true;
    }

    /** The walkable cell nearest to (x, y), in rings around it; -1 if none is in SEARCH_CELLS cells. */
    public int nearestFree(double x, double y) {
        long ci = Math.round((x - minX) / CELL), cj = Math.round((y - minY) / CELL);
        for (int r = 0; r <= SEARCH_CELLS; r++) {
            for (long j = cj - r; j <= cj + r; j++) {
                for (long i = ci - r; i <= ci + r; i++) {
                    if (Math.max(Math.abs(i - ci), Math.abs(j - cj)) != r) continue; // the ring only
                    if (i >= 0 && j >= 0 && i < w && j < h && free[(int) (j * w + i)]) return (int) (j * w + i);
                }
            }
        }
        return -1;
    }
    // endregion grid

    // region find-path
    /**
     * The points {x, y} to walk through from (sx, sy) to (gx, gy), not including the start, or
     * null when there is no path. Each pair of points next to each other has a clear straight
     * line, so each point is one `move`.
     */
    public List<double[]> findPath(double sx, double sy, double gx, double gy) {
        int start = nearestFree(sx, sy);
        int goal = cell(gx, gy);
        if (start < 0 || goal < 0 || !free[goal]) return null; // the goal must be walkable
        int n = w * h, gi = goal % w, gj = goal / w;
        double[] cost = new double[n]; // the best cost from the start
        Arrays.fill(cost, Double.POSITIVE_INFINITY);
        int[] came = new int[n]; // the cell before this one on the best path
        Arrays.fill(came, -1);
        boolean[] done = new boolean[n]; // the closed set
        // A heap entry: {priority, cell}. Java's PriorityQueue is a binary heap.
        var heap = new PriorityQueue<double[]>((a, b) -> Double.compare(a[0], b[0]));
        cost[start] = 0;
        heap.add(new double[] {guess(start, gi, gj), start});
        while (!heap.isEmpty()) {
            int k = (int) heap.poll()[1];
            if (k == goal) break;
            if (done[k]) continue; // an old heap entry
            done[k] = true;
            int i = k % w, j = k / w;
            for (int dj = -1; dj <= 1; dj++) {
                for (int di = -1; di <= 1; di++) {
                    if (di == 0 && dj == 0) continue;
                    int ni = i + di, nj = j + dj;
                    if (ni < 0 || nj < 0 || ni >= w || nj >= h) continue;
                    int nk = nj * w + ni;
                    if (!free[nk] || done[nk]) continue;
                    // No diagonal step past a corner: both side cells must be free.
                    if (di != 0 && dj != 0 && !(free[j * w + ni] && free[nj * w + i])) continue;
                    double c = cost[k] + (di != 0 && dj != 0 ? Math.sqrt(2) : 1);
                    if (c < cost[nk]) {
                        cost[nk] = c;
                        came[nk] = k;
                        heap.add(new double[] {c + guess(nk, gi, gj), nk});
                    }
                }
            }
        }
        if (goal != start && came[goal] < 0) return null;

        // The cells from the start to the goal, as map points. The first point is our real
        // position when it is walkable, so that the first line is tested from where we stand;
        // the last point is the exact goal.
        List<double[]> cells = new ArrayList<>();
        for (int k = goal; k != -1; k = came[k]) cells.add(point(k));
        Collections.reverse(cells);
        if (safe(sx, sy)) cells.set(0, new double[] {sx, sy});
        if (cells.size() == 1) cells.add(new double[] {gx, gy});
        else cells.set(cells.size() - 1, new double[] {gx, gy});

        // Smooth the route: from each point, go to the farthest later point that a straight line
        // reaches. Each `move` costs call-cost, so fewer is better.
        List<double[]> out = new ArrayList<>();
        int a = 0;
        while (a < cells.size() - 1) {
            int b = a + 1;
            while (b + 1 < cells.size()
                    && lineClear(cells.get(a)[0], cells.get(a)[1], cells.get(b + 1)[0], cells.get(b + 1)[1])) b++;
            out.add(cells.get(b));
            a = b;
        }
        return out;
    }

    /**
     * The octile distance from cell k to the goal: the exact cost on an empty grid with diagonal
     * steps. It never overestimates, so A* finds the shortest path.
     */
    private double guess(int k, int gi, int gj) {
        int dx = Math.abs(k % w - gi), dy = Math.abs(k / w - gj);
        return dx + dy + (Math.sqrt(2) - 2) * Math.min(dx, dy);
    }
    // endregion find-path
}
