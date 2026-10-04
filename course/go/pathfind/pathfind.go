// Package pathfind finds a path around the walls of a map: a grid of
// walkable cells built from G.geometry, and A* on that grid.
//
// The server does not walk around walls for you. A `move` goes in a straight
// line, and a `move` from or to a point that is not walkable is a "line
// violation": the server sends the character to jail (node/server.js:11211-
// 11245). So a bot plans its own route, on its own copy of the walls.
//
// Concurrency: a Grid does not change after ForMap builds it, so many
// goroutines can read it. The cache of ForMap has its own lock.
package pathfind

import (
	"container/heap"
	"encoding/json"
	"fmt"
	"math"
	"sync"

	"albot/gdata"
)

// Point is a position on a map, in px.
type Point struct{ X, Y float64 }

// region grid

// 8 px cells: small enough that narrow passages stay open, big enough that
// `main` (3,936 x 3,272 px) is about 492 x 410 = 200,000 cells.
const cell = 8.0

// The box around the feet of a character that must stay clear of walls: 8 px
// to the left and right, 7 px up, 2 px down (the player "base",
// node/server.js:185).
const (
	baseH  = 8.0
	baseV  = 7.0
	baseVN = 2.0
)

// margin: half a cell more, so that "the nearest cell is walkable" also means
// "this exact point is walkable".
const margin = cell / 2

// searchCells: NearestFree gives up after 40 cells (320 px). A point farther
// than that from walkable ground is outside the map.
const searchCells = 40

// Grid is the walkable grid of one map.
type Grid struct {
	MinX, MinY float64 // the map position of cell (0, 0)
	W, H       int     // the size in cells
	Free       []bool  // true = a character can stand in this cell
}

// geometry is G.geometry[map]: the edges of the map and its walls.
type geometry struct {
	MinX   float64     `json:"min_x"`
	MinY   float64     `json:"min_y"`
	MaxX   float64     `json:"max_x"`
	MaxY   float64     `json:"max_y"`
	XLines [][]float64 `json:"x_lines"` // vertical walls [x, y1, y2]
	YLines [][]float64 `json:"y_lines"` // horizontal walls [y, x1, x2]
}

// The grids that ForMap built: G -> map name -> grid.
var (
	cacheMu sync.Mutex
	cache   = map[*gdata.GData]map[string]*Grid{}
)

// ForMap returns the grid of mapName (a key of G.maps), from
// G.geometry[mapName]. It builds each grid once and keeps it: building `main`
// takes about 100 ms.
func ForMap(G *gdata.GData, mapName string) (*Grid, error) {
	cacheMu.Lock()
	defer cacheMu.Unlock()
	if g, ok := cache[G][mapName]; ok {
		return g, nil
	}
	var geos map[string]geometry
	if err := json.Unmarshal(G.Tables["geometry"], &geos); err != nil {
		return nil, fmt.Errorf("G.geometry: %w", err)
	}
	geo, ok := geos[mapName]
	if !ok {
		return nil, fmt.Errorf("no geometry for the map %s in G", mapName)
	}
	var maps map[string]struct {
		Spawns [][]float64 `json:"spawns"`
	}
	if err := json.Unmarshal(G.Tables["maps"], &maps); err != nil {
		return nil, fmt.Errorf("G.maps: %w", err)
	}
	g := build(geo, maps[mapName].Spawns)
	if cache[G] == nil {
		cache[G] = map[string]*Grid{}
	}
	cache[G][mapName] = g
	return g, nil
}

func build(geo geometry, spawns [][]float64) *Grid {
	g := &Grid{MinX: geo.MinX, MinY: geo.MinY}
	g.W = int(math.Floor((geo.MaxX-geo.MinX)/cell)) + 1
	g.H = int(math.Floor((geo.MaxY-geo.MinY)/cell)) + 1
	wall := make([]bool, g.W*g.H) // true: too near a wall

	// Block each cell whose centre is in the rectangle [x0, x1] x [y0, y1].
	block := func(x0, y0, x1, y1 float64) {
		i0 := max(0, int(math.Ceil((x0-g.MinX)/cell)))
		i1 := min(g.W-1, int(math.Floor((x1-g.MinX)/cell)))
		j0 := max(0, int(math.Ceil((y0-g.MinY)/cell)))
		j1 := min(g.H-1, int(math.Floor((y1-g.MinY)/cell)))
		for j := j0; j <= j1; j++ {
			for i := i0; i <= i1; i++ {
				wall[j*g.W+i] = true
			}
		}
	}
	// A cell is blocked if the base box, standing there, would touch the
	// wall (with the margin).
	for _, l := range geo.XLines {
		if len(l) >= 3 {
			x, y1, y2 := l[0], l[1], l[2]
			block(x-baseH-margin, y1-baseVN-margin, x+baseH+margin, y2+baseV+margin)
		}
	}
	for _, l := range geo.YLines {
		if len(l) >= 3 {
			y, x1, x2 := l[0], l[1], l[2]
			block(x1-baseH-margin, y-baseVN-margin, x2+baseH+margin, y+baseV+margin)
		}
	}

	// The walls do not say which side is the inside of the map. The server
	// finds it with a flood fill from the spawn points (server_bfs,
	// node/server_functions.js:4732). We do the same: only the cells that a
	// spawn can reach are walkable.
	g.Free = make([]bool, g.W*g.H)
	var queue []int
	for _, s := range spawns {
		if len(s) < 2 {
			continue
		}
		if k := g.cell(s[0], s[1]); k >= 0 && !wall[k] && !g.Free[k] {
			g.Free[k] = true
			queue = append(queue, k)
		}
	}
	for len(queue) > 0 {
		k := queue[len(queue)-1] // the order does not matter in a flood fill
		queue = queue[:len(queue)-1]
		i, j := k%g.W, k/g.W
		for _, d := range [4][2]int{{1, 0}, {-1, 0}, {0, 1}, {0, -1}} {
			ni, nj := i+d[0], j+d[1]
			if ni < 0 || nj < 0 || ni >= g.W || nj >= g.H {
				continue
			}
			nk := nj*g.W + ni
			if !wall[nk] && !g.Free[nk] {
				g.Free[nk] = true
				queue = append(queue, nk)
			}
		}
	}
	return g
}

// cell is the index of the cell nearest to (x, y), or -1 outside the grid.
func (g *Grid) cell(x, y float64) int {
	i := int(math.Round((x - g.MinX) / cell))
	j := int(math.Round((y - g.MinY) / cell))
	if i < 0 || j < 0 || i >= g.W || j >= g.H {
		return -1
	}
	return j*g.W + i
}

// Point is the centre of cell k.
func (g *Grid) Point(k int) Point {
	return Point{g.MinX + float64(k%g.W)*cell, g.MinY + float64(k/g.W)*cell}
}

// Safe reports whether a character can stand at (x, y): its nearest cell is
// walkable.
func (g *Grid) Safe(x, y float64) bool {
	k := g.cell(x, y)
	return k >= 0 && g.Free[k]
}

// LineClear reports whether the straight line (ax, ay) -> (bx, by) is clear
// of walls. It tests a point every half cell (4 px). A wall is at least a
// margin away from each free cell, so a line that crosses a wall always has
// a point in a blocked cell.
func (g *Grid) LineClear(ax, ay, bx, by float64) bool {
	n := int(math.Ceil(math.Hypot(bx-ax, by-ay) / (cell / 2)))
	for s := 0; s <= n; s++ {
		t := 0.0
		if n > 0 {
			t = float64(s) / float64(n)
		}
		if !g.Safe(ax+(bx-ax)*t, ay+(by-ay)*t) {
			return false
		}
	}
	return true
}

// NearestFree is the walkable cell nearest to (x, y), in rings around it;
// -1 if none is within searchCells cells.
func (g *Grid) NearestFree(x, y float64) int {
	ci := int(math.Round((x - g.MinX) / cell))
	cj := int(math.Round((y - g.MinY) / cell))
	for r := 0; r <= searchCells; r++ {
		for j := cj - r; j <= cj+r; j++ {
			for i := ci - r; i <= ci+r; i++ {
				if max(abs(i-ci), abs(j-cj)) != r {
					continue // the ring only
				}
				if i >= 0 && j >= 0 && i < g.W && j < g.H && g.Free[j*g.W+i] {
					return j*g.W + i
				}
			}
		}
	}
	return -1
}

func abs(v int) int {
	if v < 0 {
		return -v
	}
	return v
}

// endregion grid

// region find-path

// FindPath returns the points to walk through from (sx, sy) to (gx, gy), not
// including the start, or nil when there is no path. Each pair of points next
// to each other has a clear straight line, so each point is one `move`.
func (g *Grid) FindPath(sx, sy, gx, gy float64) []Point {
	start := g.NearestFree(sx, sy)
	goal := g.cell(gx, gy)
	if start < 0 || goal < 0 || !g.Free[goal] {
		return nil // the goal must be walkable
	}
	n := g.W * g.H
	gi, gj := goal%g.W, goal/g.W
	cost := make([]float64, n) // the best cost from the start
	for i := range cost {
		cost[i] = math.Inf(1)
	}
	came := make([]int32, n) // the cell before this one on the best path
	for i := range came {
		came[i] = -1
	}
	done := make([]bool, n) // the closed set
	// The octile distance: the exact cost on an empty grid with diagonal
	// steps. It never overestimates, so A* finds the shortest path.
	guess := func(k int) float64 {
		dx := math.Abs(float64(k%g.W - gi))
		dy := math.Abs(float64(k/g.W - gj))
		return dx + dy + (math.Sqrt2-2)*math.Min(dx, dy)
	}
	h := &minHeap{}
	cost[start] = 0
	heap.Push(h, entry{guess(start), start})
	for h.Len() > 0 {
		k := heap.Pop(h).(entry).k
		if k == goal {
			break
		}
		if done[k] {
			continue // an old heap entry
		}
		done[k] = true
		i, j := k%g.W, k/g.W
		for dj := -1; dj <= 1; dj++ {
			for di := -1; di <= 1; di++ {
				if di == 0 && dj == 0 {
					continue
				}
				ni, nj := i+di, j+dj
				if ni < 0 || nj < 0 || ni >= g.W || nj >= g.H {
					continue
				}
				nk := nj*g.W + ni
				if !g.Free[nk] || done[nk] {
					continue
				}
				// No diagonal step past a corner: both side cells must be free.
				if di != 0 && dj != 0 && !(g.Free[j*g.W+ni] && g.Free[nj*g.W+i]) {
					continue
				}
				step := 1.0
				if di != 0 && dj != 0 {
					step = math.Sqrt2
				}
				if c := cost[k] + step; c < cost[nk] {
					cost[nk] = c
					came[nk] = int32(k)
					heap.Push(h, entry{c + guess(nk), nk})
				}
			}
		}
	}
	if goal != start && came[goal] < 0 {
		return nil
	}

	// The cells from the start to the goal, as map points. The first point is
	// our real position when it is walkable, so that the first line is tested
	// from where we stand; the last point is the exact goal.
	var cells []Point
	for k := goal; k != -1; k = int(came[k]) {
		cells = append(cells, g.Point(k))
	}
	for a, b := 0, len(cells)-1; a < b; a, b = a+1, b-1 {
		cells[a], cells[b] = cells[b], cells[a]
	}
	if g.Safe(sx, sy) {
		cells[0] = Point{sx, sy}
	}
	if len(cells) == 1 {
		cells = append(cells, Point{gx, gy})
	} else {
		cells[len(cells)-1] = Point{gx, gy}
	}

	// Smooth the route: from each point, go to the farthest later point that
	// a straight line reaches. Each `move` costs call-cost, so fewer is better.
	var out []Point
	for a := 0; a < len(cells)-1; {
		b := a + 1
		for b+1 < len(cells) && g.LineClear(cells[a].X, cells[a].Y, cells[b+1].X, cells[b+1].Y) {
			b++
		}
		out = append(out, cells[b])
		a = b
	}
	return out
}

// endregion find-path

// A binary min-heap of (priority, cell) pairs, for container/heap.
type entry struct {
	p float64
	k int
}
type minHeap []entry

func (h minHeap) Len() int           { return len(h) }
func (h minHeap) Less(i, j int) bool { return h[i].p < h[j].p }
func (h minHeap) Swap(i, j int)      { h[i], h[j] = h[j], h[i] }
func (h *minHeap) Push(x any)        { *h = append(*h, x.(entry)) }
func (h *minHeap) Pop() any {
	old := *h
	e := old[len(old)-1]
	*h = old[:len(old)-1]
	return e
}
