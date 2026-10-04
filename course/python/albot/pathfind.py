# pathfind.py: a walkable grid of one map, built from G.geometry, and A* on
# it, so that a character can walk around walls.
#
# The server does not walk around walls for you. A `move` goes in a straight
# line, and a `move` from or to a point that is not walkable is a "line
# violation": the server sends the character to jail (node/server.js:11211-
# 11245). So a bot plans its own route, on its own copy of the walls.
import heapq
import math
from typing import Any

from .gdata import GData

Point = tuple[float, float]  # a map position (x, y)

# region grid
# 8 px cells: small enough that narrow passages stay open, big enough that
# `main` (3,936 x 3,272 px) is about 492 x 410 = 200,000 cells.
CELL = 8
# The box around the feet of a character that must stay clear of walls: 8 px
# to the left and right, 7 px up, 2 px down (the player "base",
# node/server.js:185).
BASE_H = 8
BASE_V = 7
BASE_VN = 2
# Half a cell more, so that "the nearest cell is walkable" also means "this
# exact point is walkable".
MARGIN = CELL / 2
# nearest_free() gives up after 40 cells (320 px): a point farther than that
# from walkable ground is outside the map.
SEARCH_CELLS = 40

# id(G) -> map name -> grid. Building `main` takes about 1 s in Python, so
# each map is built once and kept.
_cache: dict[int, dict[str, "Grid"]] = {}


class Grid:
    @classmethod
    def for_map(cls, G: GData, map_name: str) -> "Grid":
        """The grid of one map, from G.geometry[map_name] and its spawn points."""
        grids = _cache.setdefault(id(G), {})
        if map_name not in grids:
            geo = G["geometry"].get(map_name)
            if not geo:
                raise RuntimeError(f"no geometry for the map {map_name} in G")
            grids[map_name] = cls(geo, G["maps"].get(map_name, {}).get("spawns", []))
        return grids[map_name]

    def __init__(self, geo: dict[str, Any], spawns: list[list[float]]) -> None:
        """Use for_map(). `geo` is G.geometry[map], `spawns` G.maps[map].spawns."""
        self.min_x = float(geo["min_x"])
        self.min_y = float(geo["min_y"])
        self.w = int((geo["max_x"] - geo["min_x"]) // CELL) + 1
        self.h = int((geo["max_y"] - geo["min_y"]) // CELL) + 1
        wall = bytearray(self.w * self.h)  # 1: too near a wall

        def block(x0: float, y0: float, x1: float, y1: float) -> None:
            """Block each cell whose centre is in the rectangle [x0, x1] x [y0, y1]."""
            i0 = max(0, math.ceil((x0 - self.min_x) / CELL))
            i1 = min(self.w - 1, math.floor((x1 - self.min_x) / CELL))
            j0 = max(0, math.ceil((y0 - self.min_y) / CELL))
            j1 = min(self.h - 1, math.floor((y1 - self.min_y) / CELL))
            for j in range(j0, j1 + 1):
                for i in range(i0, i1 + 1):
                    wall[j * self.w + i] = 1

        # x_lines are vertical walls [x, y1, y2]; y_lines are horizontal walls
        # [y, x1, x2]. A cell is blocked if the base box, standing there, would
        # touch the wall (with the margin).
        for x, y1, y2 in geo.get("x_lines") or []:
            block(x - BASE_H - MARGIN, y1 - BASE_VN - MARGIN, x + BASE_H + MARGIN, y2 + BASE_V + MARGIN)
        for y, x1, x2 in geo.get("y_lines") or []:
            block(x1 - BASE_H - MARGIN, y - BASE_VN - MARGIN, x2 + BASE_H + MARGIN, y + BASE_V + MARGIN)

        # The walls do not say which side is the inside of the map. The server
        # finds it with a flood fill from the spawn points (server_bfs,
        # node/server_functions.js:4732). We do the same: only the cells that a
        # spawn can reach are walkable.
        self.free = bytearray(self.w * self.h)
        queue: list[int] = []
        for sp in spawns:
            k = self.cell(sp[0], sp[1])
            if k >= 0 and not wall[k] and not self.free[k]:
                self.free[k] = 1
                queue.append(k)
        while queue:
            k = queue.pop()  # the order does not matter in a flood fill
            i, j = k % self.w, k // self.w
            for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= ni < self.w and 0 <= nj < self.h:
                    nk = nj * self.w + ni
                    if not wall[nk] and not self.free[nk]:
                        self.free[nk] = 1
                        queue.append(nk)

    def cell(self, x: float, y: float) -> int:
        """The index of the cell nearest to (x, y), or -1 outside the grid."""
        i = round((x - self.min_x) / CELL)
        j = round((y - self.min_y) / CELL)
        return j * self.w + i if 0 <= i < self.w and 0 <= j < self.h else -1

    def point(self, k: int) -> Point:
        """The centre of cell k."""
        return (self.min_x + (k % self.w) * CELL, self.min_y + (k // self.w) * CELL)

    def safe(self, x: float, y: float) -> bool:
        """Can a character stand at (x, y)? (Its nearest cell is walkable.)"""
        k = self.cell(x, y)
        return k >= 0 and self.free[k] == 1

    def line_clear(self, ax: float, ay: float, bx: float, by: float) -> bool:
        """Is the straight line from a to b clear of walls? It tests a point
        every half cell (4 px). A wall is at least a margin away from each free
        cell, so a line that crosses a wall always has a point in a blocked cell."""
        n = math.ceil(math.hypot(bx - ax, by - ay) / (CELL / 2))
        for s in range(n + 1):
            t = 0.0 if n == 0 else s / n
            if not self.safe(ax + (bx - ax) * t, ay + (by - ay) * t):
                return False
        return True

    def nearest_free(self, x: float, y: float) -> int:
        """The walkable cell nearest to (x, y), in rings around it; -1 if none
        is in SEARCH_CELLS cells."""
        ci = round((x - self.min_x) / CELL)
        cj = round((y - self.min_y) / CELL)
        for r in range(SEARCH_CELLS + 1):
            for j in range(cj - r, cj + r + 1):
                for i in range(ci - r, ci + r + 1):
                    if max(abs(i - ci), abs(j - cj)) != r:
                        continue  # the ring only
                    if 0 <= i < self.w and 0 <= j < self.h and self.free[j * self.w + i]:
                        return j * self.w + i
        return -1
    # endregion grid

    # region find-path
    def find_path(self, sx: float, sy: float, gx: float, gy: float) -> list[Point] | None:
        """The points to walk through from (sx, sy) to (gx, gy), not including
        the start, or None when there is no path. Each pair of points next to
        each other has a clear straight line, so each point is one `move`."""
        start = self.nearest_free(sx, sy)
        goal = self.cell(gx, gy)
        if start < 0 or goal < 0 or not self.free[goal]:
            return None  # the goal must be walkable
        w = self.w
        gi, gj = goal % w, goal // w
        cost: dict[int, float] = {start: 0.0}  # the best cost from the start
        came: dict[int, int] = {}  # the cell before this one on the best path
        done: set[int] = set()  # the closed set
        sqrt2 = math.sqrt(2)

        def guess(k: int) -> float:
            """The octile distance: the exact cost on an empty grid with
            diagonal steps. It never overestimates, so A* finds the shortest path."""
            dx, dy = abs(k % w - gi), abs(k // w - gj)
            return dx + dy + (sqrt2 - 2) * min(dx, dy)

        heap: list[tuple[float, int]] = [(guess(start), start)]
        while heap:
            _, k = heapq.heappop(heap)
            if k == goal:
                break
            if k in done:
                continue  # an old heap entry
            done.add(k)
            i, j = k % w, k // w
            for dj in (-1, 0, 1):
                for di in (-1, 0, 1):
                    if not di and not dj:
                        continue
                    ni, nj = i + di, j + dj
                    if not (0 <= ni < w and 0 <= nj < self.h):
                        continue
                    nk = nj * w + ni
                    if not self.free[nk] or nk in done:
                        continue
                    # No diagonal step past a corner: both side cells must be free.
                    if di and dj and not (self.free[j * w + ni] and self.free[nj * w + i]):
                        continue
                    c = cost[k] + (sqrt2 if di and dj else 1.0)
                    if c < cost.get(nk, math.inf):
                        cost[nk] = c
                        came[nk] = k
                        heapq.heappush(heap, (c + guess(nk), nk))
        if goal != start and goal not in came:
            return None

        # The cells from the start to the goal, as map points. The first point
        # is our real position when it is walkable, so that the first line is
        # tested from where we stand; the last point is the exact goal.
        cells: list[Point] = []
        k2: int | None = goal
        while k2 is not None:
            cells.append(self.point(k2))
            k2 = came.get(k2)
        cells.reverse()
        if self.safe(sx, sy):
            cells[0] = (sx, sy)
        if len(cells) == 1:
            cells.append((gx, gy))
        else:
            cells[-1] = (gx, gy)

        # Smooth the route: from each point, go to the farthest later point
        # that a straight line reaches. Each `move` costs call-cost, so fewer is better.
        out: list[Point] = []
        a = 0
        while a < len(cells) - 1:
            b = a + 1
            while b + 1 < len(cells) and self.line_clear(*cells[a], *cells[b + 1]):
                b += 1
            out.append(cells[b])
            a = b
        return out
    # endregion find-path
