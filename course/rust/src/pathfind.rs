// pathfind.rs: a walkable grid of one map, made from G.geometry, and A* on it,
// so that a character can walk around walls (Part 3, "Distance, range and
// movement").
//
// The server does not walk around walls for you. A `move` goes in a straight
// line, and a `move` from or to a point that is not walkable is a "line
// violation": the server sends the character to jail (node/server.js:11211-
// 11245). So a bot plans its own route, on its own copy of the walls.

use std::cmp::{Ordering, Reverse};
use std::collections::BinaryHeap;

use serde_json::Value;

use crate::alsocket::Result;
use crate::gdata::GData;

// region grid
/// 8 px cells: small enough that narrow passages stay open, big enough that
/// `main` (3,936 x 3,272 px) is about 492 x 410 = 200,000 cells.
const CELL: f64 = 8.0;
/// The box around the feet of a character that must stay clear of walls: 8 px
/// to the left and right, 7 px up, 2 px down (the player "base",
/// node/server.js:185).
const BASE_H: f64 = 8.0;
const BASE_V: f64 = 7.0;
const BASE_VN: f64 = 2.0;
/// Half a cell more, so that "the nearest cell is walkable" also means "this
/// exact point is walkable".
const MARGIN: f64 = CELL / 2.0;
/// nearest_free() gives up after 40 cells (320 px): a point farther than that
/// from walkable ground is outside the map.
const SEARCH_CELLS: i64 = 40;

/// The walkable cells of one map.
pub struct Grid {
    min_x: f64, // the map coordinates of cell (0, 0)
    min_y: f64,
    w: i64, // the width and height in cells
    h: i64,
    free: Vec<bool>, // true: a character can stand in this cell
}

impl Grid {
    /// The grid of `map`, from G.geometry[map] and the spawns of G.maps[map].
    /// Building `main` takes some time: keep the grid (Travel keeps one per map).
    pub fn for_map(g: &GData, map: &str) -> Result<Grid> {
        let geo = &g.other["geometry"][map];
        if !geo.is_object() {
            return Err(format!("no geometry for the map {map} in G").into());
        }
        Ok(Grid::new(geo, &g.other["maps"][map]["spawns"]))
    }

    /// `geo`: G.geometry[map]. `spawns`: G.maps[map].spawns.
    pub fn new(geo: &Value, spawns: &Value) -> Grid {
        let f = |key: &str| geo[key].as_f64().unwrap_or(0.0);
        let (min_x, min_y) = (f("min_x"), f("min_y"));
        let w = ((f("max_x") - min_x) / CELL).floor() as i64 + 1;
        let h = ((f("max_y") - min_y) / CELL).floor() as i64 + 1;
        let mut grid = Grid { min_x, min_y, w, h, free: vec![false; (w * h) as usize] };
        let mut wall = vec![false; (w * h) as usize]; // true: too near a wall

        // Block each cell whose centre is in the rectangle [x0, x1] x [y0, y1].
        let mut block = |x0: f64, y0: f64, x1: f64, y1: f64| {
            let i0 = ((x0 - min_x) / CELL).ceil().max(0.0) as i64;
            let i1 = (((x1 - min_x) / CELL).floor() as i64).min(w - 1);
            let j0 = ((y0 - min_y) / CELL).ceil().max(0.0) as i64;
            let j1 = (((y1 - min_y) / CELL).floor() as i64).min(h - 1);
            for j in j0..=j1 {
                for i in i0..=i1 {
                    wall[(j * w + i) as usize] = true;
                }
            }
        };
        // x_lines are vertical walls [x, y1, y2]; y_lines are horizontal walls
        // [y, x1, x2]. A cell is blocked if the base box, standing there, would
        // touch the wall (with the margin).
        let line = |v: &Value| (v[0].as_f64().unwrap_or(0.0), v[1].as_f64().unwrap_or(0.0), v[2].as_f64().unwrap_or(0.0));
        for v in geo["x_lines"].as_array().into_iter().flatten() {
            let (x, y1, y2) = line(v);
            block(x - BASE_H - MARGIN, y1 - BASE_VN - MARGIN, x + BASE_H + MARGIN, y2 + BASE_V + MARGIN);
        }
        for v in geo["y_lines"].as_array().into_iter().flatten() {
            let (y, x1, x2) = line(v);
            block(x1 - BASE_H - MARGIN, y - BASE_VN - MARGIN, x2 + BASE_H + MARGIN, y + BASE_V + MARGIN);
        }

        // The walls do not say which side is the inside of the map. The server
        // finds it with a flood fill from the spawn points (server_bfs,
        // node/server_functions.js:4732). We do the same: only the cells that a
        // spawn can reach are walkable.
        let mut queue: Vec<usize> = Vec::new();
        for s in spawns.as_array().into_iter().flatten() {
            if let Some(k) = grid.cell(s[0].as_f64().unwrap_or(0.0), s[1].as_f64().unwrap_or(0.0)) {
                if !wall[k] && !grid.free[k] {
                    grid.free[k] = true;
                    queue.push(k);
                }
            }
        }
        while let Some(k) = queue.pop() {
            // The order does not matter in a flood fill.
            let (i, j) = (k as i64 % w, k as i64 / w);
            for (di, dj) in [(1, 0), (-1, 0), (0, 1), (0, -1)] {
                let (ni, nj) = (i + di, j + dj);
                if ni < 0 || nj < 0 || ni >= w || nj >= h {
                    continue;
                }
                let nk = (nj * w + ni) as usize;
                if !wall[nk] && !grid.free[nk] {
                    grid.free[nk] = true;
                    queue.push(nk);
                }
            }
        }
        grid
    }

    /// The index of the cell nearest to (x, y), or None outside the grid.
    pub fn cell(&self, x: f64, y: f64) -> Option<usize> {
        let i = ((x - self.min_x) / CELL).round() as i64;
        let j = ((y - self.min_y) / CELL).round() as i64;
        (i >= 0 && j >= 0 && i < self.w && j < self.h).then(|| (j * self.w + i) as usize)
    }

    /// The centre of cell `k`, as a map point.
    pub fn point(&self, k: usize) -> (f64, f64) {
        let (i, j) = (k as i64 % self.w, k as i64 / self.w);
        (self.min_x + i as f64 * CELL, self.min_y + j as f64 * CELL)
    }

    /// Can a character stand at (x, y)? (Its nearest cell is walkable.)
    pub fn safe(&self, x: f64, y: f64) -> bool {
        self.cell(x, y).is_some_and(|k| self.free[k])
    }

    /// Is the straight line from (ax, ay) to (bx, by) clear of walls? It tests
    /// a point every half cell (4 px). A wall is at least a margin away from
    /// each free cell, so a line that crosses a wall always has a point in a
    /// blocked cell.
    pub fn line_clear(&self, ax: f64, ay: f64, bx: f64, by: f64) -> bool {
        let n = ((bx - ax).hypot(by - ay) / (CELL / 2.0)).ceil() as i64;
        (0..=n).all(|s| {
            let t = if n == 0 { 0.0 } else { s as f64 / n as f64 };
            self.safe(ax + (bx - ax) * t, ay + (by - ay) * t)
        })
    }

    /// The walkable cell nearest to (x, y), in rings around it; None if none is
    /// within SEARCH_CELLS cells.
    pub fn nearest_free(&self, x: f64, y: f64) -> Option<usize> {
        let ci = ((x - self.min_x) / CELL).round() as i64;
        let cj = ((y - self.min_y) / CELL).round() as i64;
        for r in 0..=SEARCH_CELLS {
            for j in cj - r..=cj + r {
                for i in ci - r..=ci + r {
                    if (i - ci).abs().max((j - cj).abs()) != r {
                        continue; // the ring only
                    }
                    if i >= 0 && j >= 0 && i < self.w && j < self.h && self.free[(j * self.w + i) as usize] {
                        return Some((j * self.w + i) as usize);
                    }
                }
            }
        }
        None
    }
    // endregion grid

    // region find-path
    /// The points to walk through from (sx, sy) to (gx, gy), without the start.
    /// None when there is no path. Each pair of points next to each other has
    /// a clear straight line, so each point is one `move`.
    pub fn find_path(&self, sx: f64, sy: f64, gx: f64, gy: f64) -> Option<Vec<(f64, f64)>> {
        let start = self.nearest_free(sx, sy)?;
        let goal = self.cell(gx, gy)?;
        if !self.free[goal] {
            return None; // the goal must be walkable
        }
        let n = (self.w * self.h) as usize;
        let (gi, gj) = (goal as i64 % self.w, goal as i64 / self.w);
        let mut cost = vec![f64::INFINITY; n]; // the best cost from the start
        let mut came: Vec<Option<usize>> = vec![None; n]; // the cell before this one on the best path
        let mut done = vec![false; n]; // the closed set
        // The octile distance: the exact cost on an empty grid with diagonal
        // steps. It never overestimates, so A* finds the shortest path.
        let guess = |k: usize| {
            let dx = (k as i64 % self.w - gi).abs() as f64;
            let dy = (k as i64 / self.w - gj).abs() as f64;
            dx + dy + (std::f64::consts::SQRT_2 - 2.0) * dx.min(dy)
        };
        // BinaryHeap is a max-heap: Reverse makes it give the smallest first.
        let mut heap = BinaryHeap::new();
        cost[start] = 0.0;
        heap.push(Reverse((Priority(guess(start)), start)));
        while let Some(Reverse((_, k))) = heap.pop() {
            if k == goal {
                break;
            }
            if done[k] {
                continue; // an old heap entry
            }
            done[k] = true;
            let (i, j) = (k as i64 % self.w, k as i64 / self.w);
            for dj in -1..=1 {
                for di in -1..=1 {
                    if di == 0 && dj == 0 {
                        continue;
                    }
                    let (ni, nj) = (i + di, j + dj);
                    if ni < 0 || nj < 0 || ni >= self.w || nj >= self.h {
                        continue;
                    }
                    let nk = (nj * self.w + ni) as usize;
                    if !self.free[nk] || done[nk] {
                        continue;
                    }
                    // No diagonal step past a corner: both side cells must be free.
                    let diagonal = di != 0 && dj != 0;
                    if diagonal && !(self.free[(j * self.w + ni) as usize] && self.free[(nj * self.w + i) as usize]) {
                        continue;
                    }
                    let c = cost[k] + if diagonal { std::f64::consts::SQRT_2 } else { 1.0 };
                    if c < cost[nk] {
                        cost[nk] = c;
                        came[nk] = Some(k);
                        heap.push(Reverse((Priority(c + guess(nk)), nk)));
                    }
                }
            }
        }
        if goal != start && came[goal].is_none() {
            return None;
        }

        // The cells from the start to the goal, as map points. The first point
        // is our real position when it is walkable, so that the first line is
        // tested from where we stand; the last point is the exact goal.
        let mut cells = Vec::new();
        let mut k = Some(goal);
        while let Some(c) = k {
            cells.push(self.point(c));
            k = came[c];
        }
        cells.reverse();
        if self.safe(sx, sy) {
            cells[0] = (sx, sy);
        }
        if cells.len() == 1 {
            cells.push((gx, gy));
        } else {
            *cells.last_mut().unwrap() = (gx, gy);
        }

        // Smooth the route: from each point, go to the farthest later point
        // that a straight line reaches. Each `move` costs call-cost, so fewer is better.
        let mut out = Vec::new();
        let mut a = 0;
        while a < cells.len() - 1 {
            let mut b = a + 1;
            while b + 1 < cells.len() && self.line_clear(cells[a].0, cells[a].1, cells[b + 1].0, cells[b + 1].1) {
                b += 1;
            }
            out.push(cells[b]);
            a = b;
        }
        Some(out)
    }
    // endregion find-path
}

/// An f64 that the heap can sort (f64 has no total order of its own).
#[derive(PartialEq)]
struct Priority(f64);
impl Eq for Priority {}
impl PartialOrd for Priority {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}
impl Ord for Priority {
    fn cmp(&self, other: &Self) -> Ordering {
        self.0.total_cmp(&other.0)
    }
}
