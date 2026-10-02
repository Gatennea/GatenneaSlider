# -*- coding: utf-8 -*-
"""異形「最佳放置」：目標框枚舉（M0 第一步，計劃 §4）。

方形铁律（見《術語規定》§4）：**調試面板畫框與求解器必須共用同一結果**——
目標框不是求解器的內部細節，而是 GUI 與求解器的共用地基。所以本模組是純
邏輯、可單測，GUI 與求解器都調它，不各寫一套。

本模組只做 tri（米字第二期，§6）。核心結論（2026-10-03 實測，證據見
`experiments/_tri_mod_probe.py` 與計劃 §5）：

  1. **可達放置只有 1 個朝向 × 全部平移。** 大三角在斜座標下**沒有 120°
     旋轉對稱**（窮舉仿射對稱：k=2..5 都只有恆等與 `(i,j)→(j,i)` 轉置兩個；
     幾何驗證：繞重心旋轉 120° 後頂點集合完全變樣）。計劃原寫的「3 個旋轉
     朝向」是錯的，已修正。
  2. **放置偏移必須是 step 的倍數。** `(i%step, j%step)` 類計數在引擎真實
     滑動下守恆（k=2..5 × step=1..3 共 441 步零變化），但在任意幾何平移下
     不守恆 —— 所以枚舉時用 mod 網格過濾是**合法性依據**，不是經驗性過濾。

介面與方形的 `find_best_window` 對稱（計劃 §3 的 `best_placement`）：

    best_placement(coords, k, step) -> TriPlacement
"""
from collections import Counter

from game_triangle import TriangleSliderMatrix
from gui.cell_class import cell_class

__all__ = ['TriPlacement', 'best_placement', 'goal_shape',
           'overlap_at', 'placement_offset_ok']


class TriPlacement:
    """一次「最佳放置」的結果。

    屬性
    ----
    offset : (di, dj)
        目標大三角相對原點的平移量（**必定是 step 的整數倍**，見模組 docstring）。
    cells  : frozenset
        放置後的目標形狀單元集（`offset` 與原點 goal 合併）。
    overlap : int
        |coords ∩ cells|，即聚拢度分子。
    coords : frozenset
        參與枚舉的輸入（正規化後）。

    與方形 `_TargetRegion` 的對齊點：`offset` ≡ 方形的 `(r0, c0)`，
    `cells` ≡ 方形的窗口單元集。GUI 畫框與求解器聚拢度都吃這個結構。
    """

    __slots__ = ('offset', 'cells', 'overlap', 'coords', 'k', 'step',
                 'mod_match')

    def __init__(self, offset, cells, overlap, coords, k, step,
                 mod_match=False):
        self.offset = offset
        self.cells = cells
        self.overlap = overlap
        self.coords = coords
        self.k = k
        self.step = step
        # mod 類分佈是否與盤面吻合（診斷用，見 best_placement 末尾）
        self.mod_match = mod_match

    @property
    def score(self):
        """聚拢度 = 重疊數 / k²。score=1.0 ⇔ 完全重合 ⇔ is_solved。"""
        return self.overlap / (self.k * self.k) if self.k else 0.0

    def __repr__(self):
        return (f'TriPlacement(offset={self.offset}, overlap={self.overlap}/'
                f'{self.k * self.k}, score={self.score:.3f})')


def goal_shape(k):
    """原點版目標形狀（k² 單元，斜座標 `(i, j, up)`）。"""
    return frozenset(TriangleSliderMatrix(k).positions())


def placement_offset_ok(offset, step):
    """放置偏移是否合法（必須是 step 的整數倍）。

    這是**合法性判據**不是經驗性過濾：三族滑動的 delta 都是 step × 單位向量
    （實測 step=2 時 h=(±2,0)、p=(0,±2)、n=(±2,∓2)，零噪聲），而類計數
    `(i%step, j%step)` 在滑動下守恆 —— 所以任何可達的目標位置，其相對原點
    的偏移必是 step 的倍數。反過來，非 step 倍數的偏移**物理上不可能到達**，
    枚舉時必須排除（否則會把聚拢度引導到不可達方向）。
    """
    if step <= 1:
        return True
    return offset[0] % step == 0 and offset[1] % step == 0


def overlap_at(coords, shape):
    """|coords ∩ shape|。三角沒有方形那套二維前綴和（k² ≤ 64，暴力即可）。"""
    return len(coords & shape)


def _offset_domain(coords, k, step):
    """枚舉範圍：讓覆蓋窗口盡量貼合邊界盒，外擴 1 格。

    目標大三角平移 `offset` 後要盡可能罩住現有單元，否則錯過最優位置。
    邊界盒 `[min_i, max_i] × [min_j, max_j]`，平移量從 `-k` 到 `+k` 覆蓋
    「目標形狀左上角落在邊界盒任何位置」的情形。
    """
    if not coords:
        return [(0, 0)]
    is_ = [i for i, _j, _u in coords]
    js = [j for _i, j, _u in coords]
    lo_i, hi_i = min(is_), max(is_)
    lo_j, hi_j = min(js), max(js)
    return [(lo_i + di, lo_j + dj)
            for di in range(-k, k + 1)
            for dj in range(-k, k + 1)]


def best_placement(coords, k, step):
    """枚舉所有合法放置，返回重疊最大者（並列時取偏移字典序最小）。

    coords : iterable
        當前單元集 `(i, j, up)`。允許含任何坐標（引擎會給出真局面）。
    k      : int
        目標大三角邊長（單元數 k²）。
    step   : int
        等級（放置偏移的模約束）。step ≤ 1 時不約束（退化情形，無害）。

    與方形 `find_best_window` 的差異：方形枚舉 m×n 與 n×m 兩種高寬（轉置算
    還原），**tri 沒有這個分支** —— 計劃 §5 實測大三角只有 `(i,j)→(j,i)`
    轉置對稱，但那個變換把 goal 映到自身、不是新的放置，等價於同一個形狀。
    """
    cells = frozenset(coords)
    k = max(1, int(k))
    step = max(1, int(step))

    # 類計數：滑動不變量，用來剔除物理上不可達的偏移（雙重把關，見下）
    target_mods = Counter(cell_class((i, j), step, 'triangle') for i, j, _u in cells)

    goal = goal_shape(k)
    best = None
    for di, dj in _offset_domain(cells, k, step):
        if not placement_offset_ok((di, dj), step):
            continue
        shape = frozenset((i + di, j + dj, u) for (i, j, u) in goal)
        ov = overlap_at(cells, shape)
        if best is None or ov > best.overlap:
            best = TriPlacement((di, dj), shape, ov, cells, k, step)
        elif ov == best.overlap and (di, dj) < best.offset:
            best = TriPlacement((di, dj), shape, ov, cells, k, step)
    if best is None:
        best = TriPlacement((0, 0), goal, 0, cells, k, step)

    # mod 一致性分（借方形 `_is_mod_compliant` 的思路）：若最優放置的類分佈與
    # 當前盤面差異很大，說明枚舉範圍或 mod 約束有問題。**只診斷不裁決**——
    # 貪心求解器寧可要一個「類不合但幾何貼合」的框，也不要 0 重疊的框。
    best_mods = Counter(cell_class((i, j), step, 'triangle')
                        for i, j, _u in best.cells)
    best.mod_match = (best_mods == target_mods)
    return best


def _game_coords(game):
    """引擎局面 → 座標集（與方形版同名函數同契約）。"""
    return frozenset(tuple(b.location) for b in game.blocks)


def best_placement_of_game(game, k=None, step=None):
    """引擎直接入口（GUI 與求解器都用這個，避免兩處各轉一次坐標）。"""
    k = k if k is not None else game.k
    step = step if step is not None else getattr(game, 'step', 1)
    return best_placement(_game_coords(game), k, step)
