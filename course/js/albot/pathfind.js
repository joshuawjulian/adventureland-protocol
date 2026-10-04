// pathfind.js: a walkable grid of one map, built from G.geometry, and A* on
// it, so that a character can walk around walls. Node.js 22.18+. No packages.
//
// The server does not walk around walls for you. A `move` goes in a straight
// line, and a `move` from or to a point that is not walkable is a "line
// violation": the server sends the character to jail (node/server.js:11211-
// 11245). So a bot plans its own route, on its own copy of the walls.

/** @typedef {[number, number]} Point  a map position [x, y] */

// region grid
// 8 px cells: small enough that narrow passages stay open, big enough that
// `main` (3,936 x 3,272 px) is about 492 x 410 = 200,000 cells.
const CELL = 8;
// The box around the feet of a character that must stay clear of walls: 8 px
// to the left and right, 7 px up, 2 px down (the player "base",
// node/server.js:185).
const BASE_H = 8;
const BASE_V = 7;
const BASE_VN = 2;
// Half a cell more, so that "the nearest cell is walkable" also means "this
// exact point is walkable".
const MARGIN = CELL / 2;
// nearestFree() gives up after 40 cells (320 px): a point farther than that
// from walkable ground is outside the map.
const SEARCH_CELLS = 40;

/** @type {WeakMap<object, Map<string, Grid>>} G -> map name -> grid */
const cache = new WeakMap();

export class Grid {
  // The grid of `map` (a key of G.maps), from G.geometry[map]. It is built
  // once for each map and kept: building `main` takes about 100 ms.
  /** @param {Record<string, any>} G @param {string} map @returns {Grid} */
  static forMap(G, map) {
    let grids = cache.get(G);
    if (!grids) cache.set(G, (grids = new Map()));
    let grid = grids.get(map);
    if (!grid) {
      const geo = G.geometry?.[map];
      if (!geo) throw new Error(`no geometry for the map ${map} in G`);
      grid = new Grid(geo, G.maps[map]?.spawns ?? []);
      grids.set(map, grid);
    }
    return grid;
  }

  /** @param {Record<string, any>} geo  G.geometry[map] @param {number[][]} spawns  G.maps[map].spawns */
  constructor(geo, spawns) {
    this.minX = geo.min_x;
    this.minY = geo.min_y;
    this.w = Math.floor((geo.max_x - geo.min_x) / CELL) + 1;
    this.h = Math.floor((geo.max_y - geo.min_y) / CELL) + 1;
    const wall = new Uint8Array(this.w * this.h); // 1: too near a wall

    // Block each cell whose centre is in the rectangle [x0, x1] x [y0, y1].
    /** @param {number} x0 @param {number} y0 @param {number} x1 @param {number} y1 */
    const block = (x0, y0, x1, y1) => {
      const i0 = Math.max(0, Math.ceil((x0 - this.minX) / CELL));
      const i1 = Math.min(this.w - 1, Math.floor((x1 - this.minX) / CELL));
      const j0 = Math.max(0, Math.ceil((y0 - this.minY) / CELL));
      const j1 = Math.min(this.h - 1, Math.floor((y1 - this.minY) / CELL));
      for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) wall[j * this.w + i] = 1;
    };
    // x_lines are vertical walls [x, y1, y2]; y_lines are horizontal walls
    // [y, x1, x2]. A cell is blocked if the base box, standing there, would
    // touch the wall (with the margin).
    for (const [x, y1, y2] of geo.x_lines ?? []) {
      block(x - BASE_H - MARGIN, y1 - BASE_VN - MARGIN, x + BASE_H + MARGIN, y2 + BASE_V + MARGIN);
    }
    for (const [y, x1, x2] of geo.y_lines ?? []) {
      block(x1 - BASE_H - MARGIN, y - BASE_VN - MARGIN, x2 + BASE_H + MARGIN, y + BASE_V + MARGIN);
    }

    // The walls do not say which side is the inside of the map. The server
    // finds it with a flood fill from the spawn points (server_bfs,
    // node/server_functions.js:4732). We do the same: only the cells that a
    // spawn can reach are walkable.
    this.free = new Uint8Array(this.w * this.h);
    /** @type {number[]} */
    const queue = [];
    for (const [sx, sy] of spawns) {
      const k = this.cell(sx, sy);
      if (k >= 0 && !wall[k] && !this.free[k]) {
        this.free[k] = 1;
        queue.push(k);
      }
    }
    while (queue.length) {
      const k = /** @type {number} */ (queue.pop()); // the order does not matter in a flood fill
      const i = k % this.w;
      const j = (k - i) / this.w;
      for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const ni = i + di;
        const nj = j + dj;
        if (ni < 0 || nj < 0 || ni >= this.w || nj >= this.h) continue;
        const nk = nj * this.w + ni;
        if (!wall[nk] && !this.free[nk]) {
          this.free[nk] = 1;
          queue.push(nk);
        }
      }
    }
  }

  // The index of the cell nearest to (x, y), or -1 outside the grid.
  /** @param {number} x @param {number} y */
  cell(x, y) {
    const i = Math.round((x - this.minX) / CELL);
    const j = Math.round((y - this.minY) / CELL);
    return i >= 0 && j >= 0 && i < this.w && j < this.h ? j * this.w + i : -1;
  }

  /** @param {number} k @returns {Point} the centre of cell k */
  point(k) {
    const i = k % this.w;
    return [this.minX + i * CELL, this.minY + ((k - i) / this.w) * CELL];
  }

  // Can a character stand at (x, y)? (Its nearest cell is walkable.)
  /** @param {number} x @param {number} y @returns {boolean} */
  safe(x, y) {
    const k = this.cell(x, y);
    return k >= 0 && this.free[k] === 1;
  }

  // Is the straight line from a to b clear of walls? It tests a point every
  // half cell (4 px). A wall is at least a margin away from each free cell,
  // so a line that crosses a wall always has a point in a blocked cell.
  /** @param {number} ax @param {number} ay @param {number} bx @param {number} by @returns {boolean} */
  lineClear(ax, ay, bx, by) {
    const n = Math.ceil(Math.hypot(bx - ax, by - ay) / (CELL / 2));
    for (let s = 0; s <= n; s++) {
      const t = n === 0 ? 0 : s / n;
      if (!this.safe(ax + (bx - ax) * t, ay + (by - ay) * t)) return false;
    }
    return true;
  }

  // The walkable cell nearest to (x, y), in rings around it; -1 if none is
  // in SEARCH_CELLS cells.
  /** @param {number} x @param {number} y */
  nearestFree(x, y) {
    const ci = Math.round((x - this.minX) / CELL);
    const cj = Math.round((y - this.minY) / CELL);
    for (let r = 0; r <= SEARCH_CELLS; r++) {
      for (let j = cj - r; j <= cj + r; j++) {
        for (let i = ci - r; i <= ci + r; i++) {
          if (Math.max(Math.abs(i - ci), Math.abs(j - cj)) !== r) continue; // the ring only
          if (i >= 0 && j >= 0 && i < this.w && j < this.h && this.free[j * this.w + i]) return j * this.w + i;
        }
      }
    }
    return -1;
  }
  // endregion grid

  // region find-path
  // The points to walk through from (sx, sy) to (gx, gy), not including the
  // start, or null when there is no path. Each pair of points next to each
  // other has a clear straight line, so each point is one `move`.
  /** @param {number} sx @param {number} sy @param {number} gx @param {number} gy @returns {Point[] | null} */
  findPath(sx, sy, gx, gy) {
    const start = this.nearestFree(sx, sy);
    const goal = this.cell(gx, gy);
    if (start < 0 || goal < 0 || !this.free[goal]) return null; // the goal must be walkable
    const n = this.w * this.h;
    const gi = goal % this.w;
    const gj = (goal - gi) / this.w;
    const cost = new Float64Array(n).fill(Infinity); // the best cost from the start
    const came = new Int32Array(n).fill(-1); // the cell before this one on the best path
    const done = new Uint8Array(n); // the closed set
    // The octile distance: the exact cost on an empty grid with diagonal
    // steps. It never overestimates, so A* finds the shortest path.
    /** @param {number} k */
    const guess = (k) => {
      const dx = Math.abs((k % this.w) - gi);
      const dy = Math.abs(Math.floor(k / this.w) - gj);
      return dx + dy + (Math.SQRT2 - 2) * Math.min(dx, dy);
    };
    const heap = new MinHeap();
    cost[start] = 0;
    heap.push(guess(start), start);
    while (heap.size) {
      const k = heap.pop();
      if (k === goal) break;
      if (done[k]) continue; // an old heap entry
      done[k] = 1;
      const i = k % this.w;
      const j = (k - i) / this.w;
      for (let dj = -1; dj <= 1; dj++) {
        for (let di = -1; di <= 1; di++) {
          if (!di && !dj) continue;
          const ni = i + di;
          const nj = j + dj;
          if (ni < 0 || nj < 0 || ni >= this.w || nj >= this.h) continue;
          const nk = nj * this.w + ni;
          if (!this.free[nk] || done[nk]) continue;
          // No diagonal step past a corner: both side cells must be free.
          if (di && dj && !(this.free[j * this.w + ni] && this.free[nj * this.w + i])) continue;
          const c = cost[k] + (di && dj ? Math.SQRT2 : 1);
          if (c < cost[nk]) {
            cost[nk] = c;
            came[nk] = k;
            heap.push(c + guess(nk), nk);
          }
        }
      }
    }
    if (goal !== start && came[goal] < 0) return null;

    // The cells from the start to the goal, as map points. The first point is
    // our real position when it is walkable, so that the first line is tested
    // from where we stand; the last point is the exact goal.
    /** @type {Point[]} */
    const cells = [];
    for (let k = goal; k !== -1; k = came[k]) cells.push(this.point(k));
    cells.reverse();
    if (this.safe(sx, sy)) cells[0] = [sx, sy];
    if (cells.length === 1) cells.push([gx, gy]);
    else cells[cells.length - 1] = [gx, gy];

    // Smooth the route: from each point, go to the farthest later point that
    // a straight line reaches. Each `move` costs call-cost, so fewer is better.
    /** @type {Point[]} */
    const out = [];
    let a = 0;
    while (a < cells.length - 1) {
      let b = a + 1;
      while (b + 1 < cells.length && this.lineClear(cells[a][0], cells[a][1], cells[b + 1][0], cells[b + 1][1])) b++;
      out.push(cells[b]);
      a = b;
    }
    return out;
  }
  // endregion find-path
}

// A binary min-heap of (priority, value) pairs. JavaScript has none built in.
class MinHeap {
  /** @type {number[]} */ #p = [];
  /** @type {number[]} */ #v = [];
  get size() {
    return this.#v.length;
  }
  /** @param {number} p @param {number} v */
  push(p, v) {
    let i = this.#v.length;
    this.#p.push(p);
    this.#v.push(v);
    while (i > 0) {
      const up = (i - 1) >> 1;
      if (this.#p[up] <= this.#p[i]) break;
      this.#swap(up, i);
      i = up;
    }
  }
  pop() {
    const top = this.#v[0];
    const lastP = /** @type {number} */ (this.#p.pop());
    const lastV = /** @type {number} */ (this.#v.pop());
    if (this.#v.length) {
      this.#p[0] = lastP;
      this.#v[0] = lastV;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1;
        const r = l + 1;
        let m = i;
        if (l < this.#v.length && this.#p[l] < this.#p[m]) m = l;
        if (r < this.#v.length && this.#p[r] < this.#p[m]) m = r;
        if (m === i) break;
        this.#swap(m, i);
        i = m;
      }
    }
    return top;
  }
  /** @param {number} a @param {number} b */
  #swap(a, b) {
    [this.#p[a], this.#p[b]] = [this.#p[b], this.#p[a]];
    [this.#v[a], this.#v[b]] = [this.#v[b], this.#v[a]];
  }
}
