# -*- coding: utf-8 -*-
"""異形「最佳放置」：米字格目标框枚举（M3 第一步，計劃 §4/§6）。

方形铁律（見《術語規定》§4）：**調試面板畫框與求解器必須共用同一結果**。
本模組是 mi 版的 `find_best_window`，GUI 與求解器都調它。

mi 與 tri 的三處實質差別（**全部來自實測，不是照抄**，
證據見 `experiments/_mi_mod_probe.py`）：

1. **轉置也算還原。** `game_mi.is_solved` 判 m×n 或 n×m 兩種高寬都放行，
   所以枚舉有**兩個目標形狀**（tri 只有一個）。這是計劃 §6 拍板的。
2. **換晶格（B 檔目標）只在 step=1 時存在。** 錯位態的塊坐標是半整數，
   目標形狀要落 B 檔就得整體偏移 (½,½)。實測 step=2/3 時這個偏移會翻
   `(r±c)%step` 的類分佈 —— 與 `gui/cell_class` 文檔「step 偶數時晶格是
   不變量、類匹配自動排除另一晶格」自洽：引擎的斜向最短單位是 ½ 格 ×step，
   step≥2 時那是整數位移，**根本換不了晶格**。所以偏移的奇偶一致性要
   顯式判，不能只靠類分佈。
3. **mod 約束的形狀不是「偏移是 step 的倍數」。** mi 的類是
   `((r+c)%step, (r−c)%step)`，平移 (dr,dc) 把整個類分佈平移
   `((dr+dc)%step, (dr−dc)%step)`。偏移合法 ⟺ 該餘數對把目標的類計數
   映回自身。實測：step=2 時 4×4 的整格合法偏移是 3×3 **全 9 個**（不是
   只有 step 的倍數）；step=3 時整格只剩 (0,0) 但半格有一批。
   這個「類自同構餘數對集合 S(step)」是**可預計算的**，見 `_mod_auts`。

   另外：`(0.5, 0)`（一軸半格、一軸整格）這種**奇偶不一致**的偏移，
   類分佈在 step=2 下碰巧匹配 —— 但它是**遊戲走不出來的死盤座標**
   （`game_mi.coords_coherent` 的閘門）。所以合法性 = S 檢查 ∧ 奇偶一致，
   兩條都要。

介面與 tri 版對稱（計劃 §3 的 `best_placement`）::

    best_placement(coords, m, n, step) -> MiPlacement
"""
import math
from collections import Counter
from functools import lru_cache

from game_mi import MiSliderMatrix
from gui.cell_class import cell_class

__all__ = ['MiPlacement', 'best_placement', 'goal_shape', 'goal_shapes',
           'overlap_at', 'placement_offset_ok', 'mod_auts']

_QBITS = {'N': 1, 'E': 2, 'S': 4, 'W': 8}
_QUARTERS = ('N', 'E', 'S', 'W')


class MiPlacement:
    """一次「最佳放置」的結果。

    屬性
    ----
    offset : (dr, dc)
        目標矩陣相對原點的平移量。**兩個分量同為整數或同為半整數**
        （奇偶一致，否則是走不到的死盤座標）；step≥2 時只可能是整數。
    cells  : frozenset
        放置後的目標形狀單元集（`(r, c, q)`）。
    overlap : int
        |coords ∩ cells|，即聚攏度分子。
    shape  : (h, w)
        命中的目標矩陣高寬（可能是轉置後的 n×m）。
    lattice : 0 / 1
        0 = A 檔（整數座標）、1 = B 檔（半整數座標，錯位態）。

    與 tri 的 `TriPlacement` 對齊：score = overlap / (4mn)，
    score = 1.0 ⇔ 與某個放置完全重合 ⇔ `game.is_solved()`。
    """

    __slots__ = ('offset', 'cells', 'overlap', 'coords', 'm', 'n', 'step',
                 'shape', 'lattice', 'mod_match')

    def __init__(self, offset, cells, overlap, coords, m, n, step,
                 shape=None, lattice=0, mod_match=False):
        self.offset = offset
        self.cells = cells
        self.overlap = overlap
        self.coords = coords
        self.m = m
        self.n = n
        self.step = step
        self.shape = shape or (m, n)
        self.lattice = lattice
        self.mod_match = mod_match

    @property
    def total(self):
        """目標單元總數 4mn。"""
        return 4 * self.m * self.n

    @property
    def score(self):
        """聚攏度 = 重疊數 / 4mn。score=1.0 ⇔ 完全重合 ⇔ is_solved。"""
        return self.overlap / self.total if self.m and self.n else 0.0

    def __repr__(self):
        return (f'MiPlacement(offset={self.offset}, shape={self.shape}, '
                f'lat={self.lattice}, overlap={self.overlap}/{self.total}, '
                f'score={self.score:.3f})')


def goal_shape(m, n):
    """原點版目標形狀（m×n 棋盤的全部單位塊，4mn 個）。"""
    return frozenset((r, c, q)
                     for r in range(m) for c in range(n) for q in _QUARTERS)


def goal_shapes(m, n):
    """兩個目標形狀：m×n 與 n×m（轉置算還原，計劃 §6 已拍板）。

    m == n 時只回一個 —— 此時兩個形狀逐單元相同，枚舉兩遍純浪費。
    """
    a = goal_shape(m, n)
    if m == n:
        return (a,)
    return (a, frozenset((c, r, q)
                         for r in range(m) for c in range(n)
                         for q in _QUARTERS))


# ---------------------------------------------------------------------------
# mod 約束
# ---------------------------------------------------------------------------
@lru_cache(maxsize=64)
def mod_auts(m, n, step):
    """類自同構餘數對集合 S(step) = { (u, v) : 類計數按 (u,v) 平移後不變 }。

    為什麼要預計算而不是逐偏移比對：偏移域是 O(盤面尺寸²) 個候選，
    每個都做一次 4mn 長的 Counter 比對太貴（聚攏度每步要算幾百次）。
    S 只依賴 (m, n, step)，快取一次之後偏移檢查是 O(1) 的集合查表。

    推導：平移 (dr, dc) 讓每塊的 `r+c` 變 `dr+dc`、`r−c` 變 `dr−dc`，
    所以類分佈整體平移 `((dr+dc)%step, (dr−dc)%step)`。合法偏移 ⟺ 該
    餘數對 ∈ S。
    """
    step = max(1, int(step))
    goal = goal_shape(m, n)
    base = Counter(cell_class((r, c), step, 'mi') for r, c, _q in goal)
    out = set()
    for u in range(step):
        for v in range(step):
            shifted = Counter(((a + u) % step, (b + v) % step)
                              for a, b in base.elements())
            if shifted == base:
                out.add((u, v))
    return frozenset(out)


def placement_offset_ok(offset, step, m, n):
    """放置偏移是否合法：**類自同構 ∧ 奇偶一致**（兩條都要，缺一不可）。

    - 類自同構：`((dr+dc)%step, (dr−dc)%step)` ∈ S（mod 約束的本體）。
      實測 290 步引擎真實滑動零反例（`experiments/_mi_mod_probe.py` A 段）。
    - 奇偶一致：`2dr` 與 `2dc` 同奇偶，即兩個分量同為整數或同為半整數。
      **這條不是多餘的**：step=2 時偏移 (0.5, 0) 的類分佈碰巧匹配，但它
      對應「r 整數 / c 半整數」這種遊戲走不出來的死盤座標
      （`game_mi.coords_coherent`）。只查類會把聚攏度引導到不可達方向。

    step=1 退化成「只查奇偶」：類此時沒有資訊（全部 (0,0)），這與
    `cell_class` 文檔一致（1 級時位置類毫無區分力）。
    """
    dr, dc = offset
    if (round(2 * dr) & 1) != (round(2 * dc) & 1):
        return False        # 奇偶不一致：死盤座標
    step = max(1, int(step))
    if step <= 1:
        return True
    return ((round(dr + dc) % step, round(dr - dc) % step)
            in mod_auts(m, n, step))


def _offset_lattice(offset):
    """偏移落在哪個晶格檔：0 = A（整數）、1 = B（半整數）。"""
    return 1 if (round(2 * offset[0]) & 1) else 0


# ---------------------------------------------------------------------------
# 重疊查詢（前綴和）
# ---------------------------------------------------------------------------
def _masks_and_prefix(cells):
    """按晶格檔分兩張「每格塊數」二維前綴和。

    計劃 §6 預見的加速點：**每塊只屬一個晶格 → 按晶格分兩張二維前綴和**。
    這裡比計劃寫的還簡單一步：目標形狀要求每格四塊俱全，所以窗口匹配數
    就是「窗口內各格塊數之和」，**不需要按朝向分別計數** —— 用每格
    popcount(8-bit mask) 當格值即可。

    返回 `(prefix_A, prefix_B, min_r, min_c, max_r, max_c)`，前綴和是
    `[行][列]` 的二維累積表（多一圈 0 便於查詢）。
    """
    grid = [{}, {}]
    for r, c, _q in cells:
        R, C = math.floor(r), math.floor(c)
        lat = 1 if (int(2 * r) & 1) else 0
        grid[lat][(R, C)] = grid[lat].get((R, C), 0) + 1
    if not cells:
        return None, None, 0, 0, -1, -1
    min_r = min(math.floor(r) for r, _c, _q in cells)
    max_r = max(math.floor(r) for r, _c, _q in cells)
    min_c = min(math.floor(c) for _r, c, _q in cells)
    max_c = max(math.floor(c) for _r, c, _q in cells)
    out = []
    for lat in (0, 1):
        rows = max_r - min_r + 1
        cols = max_c - min_c + 1
        pre = [[0] * (cols + 1) for _ in range(rows + 1)]
        for (R, C), v in grid[lat].items():
            pre[R - min_r + 1][C - min_c + 1] = v
        for i in range(1, rows + 1):
            row, prev = pre[i], pre[i - 1]
            for j in range(1, cols + 1):
                row[j] += prev[j] + row[j - 1] - prev[j - 1]
        out.append(pre)
    return out[0], out[1], min_r, min_c, max_r, max_c


def _window_sum(pre, min_r, min_c, max_r, max_c, r0, c0, h, w):
    """窗口 [r0, r0+h) × [c0, c0+w) 內的塊數和（越界部分算 0）。"""
    if pre is None:
        return 0
    a, b = max(r0, min_r), min(r0 + h, max_r + 1)
    x, y = max(c0, min_c), min(c0 + w, max_c + 1)
    if a >= b or x >= y:
        return 0
    return (pre[b - min_r][y - min_c] - pre[a - min_r][y - min_c]
            - pre[b - min_r][x - min_c] + pre[a - min_r][x - min_c])


def overlap_at(coords, shape):
    """|coords ∩ shape|（給測試與除錯用的直算口徑）。

    求解路徑**不走這裡** —— 走 `_masks_and_prefix` 的 O(1) 窗口查詢。
    兩者必須一致，故測試 T6 會逐盤對拍。
    """
    return len(frozenset(coords) & frozenset(shape))


def _offset_domain(cells, m, n):
    """枚舉範圍：目標矩陣盡量罩住現有塊，外擴一圈。

    半格單位（×2 的整數）枚舉，所以整格與半格偏移都在域內；合法性由
    `placement_offset_ok` 裁。
    """
    if not cells:
        return [(0, 0)]
    rs = [r for r, _c, _q in cells]
    cs = [c for _r, c, _q in cells]
    lo_r, hi_r = math.floor(min(rs)), math.floor(max(rs))
    lo_c, hi_c = math.floor(min(cs)), math.floor(max(cs))
    # 目標矩陣左上角落在盤面任一格周圍 ±m/n 的範圍內即足夠覆蓋
    return [(di / 2.0, dj / 2.0)
            for di in range(2 * (lo_r - m - 1), 2 * (hi_r + 2))
            for dj in range(2 * (lo_c - n - 1), 2 * (hi_c + 2))]


def best_placement(coords, m, n, step):
    """枚舉所有合法放置，返回重疊最大者（並列時取 (lattice, shape, offset) 字典序）。

    coords : iterable
        當前單元集 `(r, c, q)`，r/c 可為半整數（錯位態 B 檔）。
    m, n   : int
        目標矩陣高寬。**枚舉 m×n 與 n×m 兩種**（轉置算還原，`is_solved` 已判）。
    step   : int
        等級（放置偏移的 mod 約束）。step ≤ 1 時不約束（退化情形，無害）。

    與 tri `best_placement` 的差異：多一個 `shape` 維度（轉置）、
    偏移是半格單位、mod 合法性查預計算的 S 集合。**坐標絕不假裝是整數** ——
    mi 是第一個真會產生半整數的形態（`game_mi.commit_move` 的 docstring
    記了這個坑：float 進 `range()` 直接 TypeError）。
    """
    cells = frozenset(coords)
    m, n = max(1, int(m)), max(1, int(n))
    step = max(1, int(step))

    pre_a, pre_b, min_r, min_c, max_r, max_c = _masks_and_prefix(cells)
    # goal_shapes 已處理 m == n 的去重，所以形狀列表長度就是實際要枚舉的個數：
    # m == n 時長度 1，否則長度 2。**這裡不能靠「(h,w) == (n,m) 就跳過」來去重**
    # —— m == n 時 (m,n) 與 (n,m) 字面相等，那個判斷會把唯一要算的形狀也跳掉，
    # 結果 best 永遠是 overlap=0 的兜底值（實測踩過：2×2/3×3/4×4 還原態全 0 分）。
    shapes = goal_shapes(m, n)
    shape_dims = [(m, n)] if m == n else [(m, n), (n, m)]

    best = None
    for off in _offset_domain(cells, m, n):
        if not placement_offset_ok(off, step, m, n):
            continue
        lat = _offset_lattice(off)
        pre = pre_a if lat == 0 else pre_b
        # 目標矩陣的 floor 網格起點：goal 裡的 (i,j) 是 0..h-1，加上偏移後
        # floor 仍是連續 h 個格（半格偏移時起點 = floor(偏移)）
        r0 = math.floor(off[0])
        c0 = math.floor(off[1])
        for goal, (h, w) in zip(shapes, shape_dims):
            ov = _window_sum(pre, min_r, min_c, max_r, max_c, r0, c0, h, w)
            key = (-ov, lat, h, w, off)
            if best is None or key < best[0]:
                cells_set = frozenset((r + off[0], c + off[1], q)
                                      for r, c, q in goal)
                best = (key, MiPlacement(off, cells_set, ov, cells, m, n,
                                         step, shape=(h, w), lattice=lat))
    if best is None:
        goal = shapes[0]
        best = (None, MiPlacement((0, 0), goal, 0, cells, m, n, step,
                                  shape=(m, n), lattice=0))

    place = best[1]
    # mod 一致性分（診斷用，同 tri）：最優放置的類分佈是否與盤面吻合。
    # **只診斷不裁決** —— 貪心寧要「類不合但幾何貼合」的框，也不要 0 重疊。
    if place.cells:
        place.mod_match = (Counter(cell_class((r, c), step, 'mi')
                                   for r, c, _q in place.cells)
                           == Counter(cell_class(k, step, 'mi') for k in cells))
    return place


def _game_coords(game):
    """引擎局面 → 座標集（與 tri 版同名函數同契約）。"""
    return frozenset(tuple(b.location) for b in game.blocks)


def best_placement_of_game(game, m=None, n=None, step=None):
    """引擎直接入口（GUI 與求解器都用這個，避免兩處各轉一次坐標）。"""
    m = m if m is not None else game.m
    n = n if n is not None else game.n
    step = step if step is not None else getattr(game, 'step', 1)
    return best_placement(_game_coords(game), m, n, step)
