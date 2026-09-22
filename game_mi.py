# -*- coding: utf-8 -*-
"""米字格（方格四切）謎題的建局、幾何與滑動（Stage M2）。

形態定義（已凍結，見 .zcode/plans/plan-mi-zige.md §2）
------------------------------------------------------------------
方格棋盤的每一格被兩條對角線切成 4 個直角等腰三角，**單元 = 一塊**，
身份 (r, c, q)，q ∈ {'N','E','S','W'}，表示該塊的斜邊（hypotenuse）
朝向格子的上／右／下／左格邊，也就是該塊趴在格子的哪一角：
    N(r,c) = {O, (c,r),   (c+1,r)}      斜邊 = 上格邊
    E(r,c) = {O, (c+1,r), (c+1,r+1)}    斜邊 = 右格邊
    S(r,c) = {O, (c,r+1), (c+1,r+1)}    斜邊 = 下格邊
    W(r,c) = {O, (c,r),   (c,r+1)}      斜邊 = 左格邊
座標為 (x, y) = (列, 行)，y 軸向下，格心 O = (c+½, r+½)。
每塊恰 3 條單位邊：一條格邊（長 1）+ 兩條半對角線（長 √2/2）；
角上的四塊互為邊相鄰（共享半對角線），與上下左右格的對應塊共享格邊。

邊相鄰表（每塊恰 3 鄰，與三角版同形）：
    N(r,c) ↔ W(r,c)、E(r,c)、S(r-1,c)
    E(r,c) ↔ N(r,c)、S(r,c)、W(r,c+1)
    S(r,c) ↔ E(r,c)、W(r,c)、N(r+1,c)
    W(r,c) ↔ N(r,c)、S(r,c)、E(r,c-1)

四族縫隙與 8 個移動方向
------------------------------------------------------------------
    'h'  格邊 y=r           rank = r
    'v'  格邊 x=c           rank = c
    'd1' "\" 對角線 y−x=k   rank = 2k + (0 if q∈{N,E} else 1)
    'd2' "/" 對角線 x+y=k+1 rank = 2k + (0 if q∈{N,W} else 1)   （k = r+c）
對角族的縫線把同格切成兩半（{N,E}｜{S,W}、{N,W}｜{E,S}），所以 rank 要
按朝向加 1；同一條對角線鏈上的格 k 相同，取同一個基值，因此一條鏈恰好
是完整的一條縫。因為 k 只有整數鏈有效，對角族的候選 line 一律是偶數。

8 個方向（每步 step 格，q 在平移下不變——沒有三角版的翻轉問題）：
        Q(↖)  W(↑)  E(↗)
        A(←)   ·    D(→)
        Z(↙)  S(↓)  X(↘)
'q'/'e'/'z'/'x' 走對角族，'w'/'s' 走 'v' 族，'a'/'d' 走 'h' 族。
"""

from __future__ import annotations

from game import Block

# 8 個移動方向：字母 → (Δrow, Δcol)，每步 step 格。
# 字母按鍵盤方位排布，與螢幕方向（y 軸向下）一致：
#       Q(↖)  W(↑)  E(↗)
#       A(←)   ·    D(→)
#       Z(↙)  S(↓)  X(↘)
DIRECTIONS = {
    'q': (-1, -1),
    'w': (-1, 0),
    'e': (-1, 1),
    'a': (0, -1),
    'd': (0, 1),
    'z': (1, -1),
    's': (1, 0),
    'x': (1, 1),
}

# 4 族縫隙 → 該族允許的移動方向（平行於縫隙線）
GAP_DIRECTIONS = {
    'h': ('a', 'd'),
    'v': ('w', 's'),
    'd1': ('q', 'x'),
    'd2': ('e', 'z'),
}

# 4-bit 矩陣的位序：一塊一位，N/E/S/W
_Q_BITS = {'N': 1, 'E': 2, 'S': 4, 'W': 8}
_Q_BY_BIT = {v: k for k, v in _Q_BITS.items()}

# 地圖編碼：4-bit 值 ↔ 十六進位字元。'#'/單塊字母/'_' 只在導入端接受
_HEX = '0123456789abcdef'
_HEX_TO_BITS = dict(_Q_BITS)
_HEX_TO_BITS.update({'#': 15, '_': 0, '.': 0, 'n': 1, 'e': 2, 's': 4, 'w': 8})
for _i in range(16):
    _HEX_TO_BITS[_HEX[_i]] = _i


def mi_key(block) -> tuple:
    """Block → (r, c, q)。"""
    loc = block.location
    return (loc[0], loc[1], loc[2])


def mi_vertices(r: int, c: int, q: str) -> tuple:
    """單位塊的三個頂點（世界座標 (x, y)，浮點，供視圖繪製用）。

    對應形態定義的四個式子；格心是 (c+½, r+½)。
    """
    cx, cy = c + 0.5, r + 0.5
    if q == 'N':
        return ((cx, cy), (c, r), (c + 1, r))
    if q == 'E':
        return ((cx, cy), (c + 1, r), (c + 1, r + 1))
    if q == 'S':
        return ((cx, cy), (c, r + 1), (c + 1, r + 1))
    if q == 'W':
        return ((cx, cy), (c, r), (c, r + 1))
    raise ValueError(f"unknown quarter: {q}")


def neighbors(key: tuple) -> tuple:
    """單位塊的 3 個邊相鄰單位塊（共享一條單位邊）。"""
    r, c, q = key
    if q == 'N':
        return ((r, c, 'W'), (r, c, 'E'), (r - 1, c, 'S'))
    if q == 'E':
        return ((r, c, 'N'), (r, c, 'S'), (r, c + 1, 'W'))
    if q == 'S':
        return ((r, c, 'E'), (r, c, 'W'), (r + 1, c, 'N'))
    if q == 'W':
        return ((r, c, 'N'), (r, c, 'S'), (r, c - 1, 'E'))
    raise ValueError(f"unknown quarter: {q}")


def gap_rank(gap_type: str, key: tuple) -> int:
    """單位塊在該族縫隙座標下的「低位」索引（side_of 的判據）。

    'h'/'v' 族取格子行列：同格四塊坐在同一條格邊的同一側，取向無關。
    對角族的縫線穿過格心，把同格四塊切成兩半，必須看朝向——
    'd1'（"\\"）分 {N,E}｜{S,W}、'd2'（"/"）分 {N,W}｜{E,S}，故後半側 +1；
    同一條對角線鏈上的格 k 相同，基值一致，一條鏈就是一條完整的縫。
    """
    r, c, q = key
    if gap_type == 'h':
        return r
    if gap_type == 'v':
        return c
    if gap_type == 'd1':
        return 2 * (r - c) + (0 if q in ('N', 'E') else 1)
    if gap_type == 'd2':
        return 2 * (r + c) + (0 if q in ('N', 'W') else 1)
    raise ValueError(f"unknown gap type: {gap_type}")


def side_of(gap_type: str, line: int, key: tuple) -> int:
    """單位塊位於縫隙的哪一側：0 = 索引小的一側，1 = 大的一側。

    判據是 gap_rank：rank <= line 歸 0 側。縫隙線只經過單位塊的邊或
    頂點、不穿過內部，因此兩側劃分完備，不會有滑塊被漏掉或重複計入。
    """
    return 0 if gap_rank(gap_type, key) <= line else 1


def gap_index_range(gap_type: str, cells) -> range:
    """縫隙族的候選 line 範圍（保證線兩側都至少有一個滑塊）。

    cells：位置集合 (r, c, q)。候選範圍按 gap_rank 取，與 side_of 同一
    套判據；是否真的兩側非空由 is_valid_gap 複核。對角族只取偶數 line：
    奇數對應的「縫線」從格心與格邊中點之間穿過，會切開單位塊內部，
    不是合法切口（三角版的 'n' 族同類問題由 up 朝向了，這裡靠逐 2）。
    """
    if gap_type == 'h':
        rs = [r for r, _c, _q in cells]
        return range(min(rs), max(rs))
    if gap_type == 'v':
        cs = [c for _r, c, _q in cells]
        return range(min(cs), max(cs))
    if gap_type == 'd1':
        ks = [2 * (r - c) for r, c, _q in cells]
        return range(min(ks), max(ks) + 1, 2)
    if gap_type == 'd2':
        ks = [2 * (r + c) for r, c, _q in cells]
        return range(min(ks), max(ks) + 1, 2)
    raise ValueError(f"unknown gap type: {gap_type}")


def gap_for_direction(direction: str):
    """移動方向字母 → 所屬縫隙族；不相關時回 None。"""
    for gap_type, dirs in GAP_DIRECTIONS.items():
        if direction in dirs:
            return gap_type
    return None


def _convex_hull(points) -> list:
    """整數點集的凸包（Andrew 單調鏈，逆時針，去重點）。"""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def half_chain(seq) -> list:
        out = []
        for p in seq:
            while len(out) >= 2 and _cross2(out[-2], out[-1], p) <= 0:
                out.pop()
            out.append(p)
        return out

    lower = half_chain(pts)
    upper = half_chain(reversed(pts))
    return lower[:-1] + upper[:-1]


def _cross2(o, a, b) -> int:
    """整數叉積（凸包與面積判定用）。"""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def hull_area_units(keys) -> int:
    """位置集合凸包的面積，以「單位塊個數」為單位（整數）。

    頂點座標都是 ½ 的倍數，整體乘 2 後為整數點，鞋帶公式求和除以 8 得
    格面積；一塊 = ¼ 格，故單位塊數 = 4 × 格面積 = |Σ| / 2。實心 m×n
    棋盤恰為 4mn 塊，因此這是一個與形態無關的散度基準。
    """
    verts = set()
    for key in keys:
        for (x, y) in mi_vertices(*key):
            verts.add((int(round(2 * x)), int(round(2 * y))))
    hull = _convex_hull(verts)
    if len(hull) < 3:
        return 0
    total = 0
    n = len(hull)
    for t in range(n):
        x1, y1 = hull[t]
        x2, y2 = hull[(t + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) // 2


class MiSliderMatrix:
    """米字格滑塊矩陣（與 SliderMatrix / TriangleSliderMatrix 同契約）。

    差異處：
    - Block.location 為 [r, c, q] 三元素，q ∈ {'N','E','S','W'}；
    - matrix 為每格 4-bit 網格（bit0=N、bit1=E、bit2=S、bit3=W）。
    """

    # 快照/矩陣的位序表：history.restore_snapshot 靠這個類屬性認出 4-bit 網格
    # （SliderMatrix 也有 m/n，不能靠它區分形態）
    Q_ORDER = ('N', 'E', 'S', 'W')

    __slots__ = ('m', 'n', 'blocks', 'matrix', 'matrix_bounds')

    def __init__(self, m: int = 6, n: int = 6):
        if m < 1 or n < 1:
            raise ValueError("mi board m/n must be >= 1")
        self.m = m
        self.n = n
        self.blocks = []
        for r in range(m):
            for c in range(n):
                for q in ('N', 'E', 'S', 'W'):
                    self.blocks.append(_make_block(r, c, q))
        self.matrix = None
        self.matrix_bounds = None
        self.update_matrix()

    def goal_cells(self) -> set:
        """目標輪廓：實心 m×n 棋盤的全部單位塊位置集合。"""
        return {(r, c, q)
                for r in range(self.m) for c in range(self.n)
                for q in ('N', 'E', 'S', 'W')}

    # ---------- 位置集合 ----------
    def positions(self) -> set:
        """全部滑塊位置 (r, c, q) 集合。"""
        return {mi_key(b) for b in self.blocks}

    def get_boundaries(self) -> dict:
        """滑塊所在格的邊界（row/col，與方形同鍵名）。"""
        if not self.blocks:
            return {'min_row': 0, 'max_row': 0, 'min_col': 0, 'max_col': 0}
        rs = [b.location[0] for b in self.blocks]
        cs = [b.location[1] for b in self.blocks]
        return {
            'min_row': min(rs), 'max_row': max(rs),
            'min_col': min(cs), 'max_col': max(cs),
        }

    # ---------- 矩陣視圖（每格 4-bit）----------
    def update_matrix(self):
        """重建 4-bit 矩陣：每格一位一塊，N=1/E=2/S=4/W=8，空=0。"""
        if not self.blocks:
            self.matrix = []
            self.matrix_bounds = {'min_row': 0, 'max_row': 0,
                                  'min_col': 0, 'max_col': 0}
            return
        bounds = self.get_boundaries()
        min_r, max_r = bounds['min_row'], bounds['max_row']
        min_c, max_c = bounds['min_col'], bounds['max_col']
        self.matrix = [[0] * (max_c - min_c + 1) for _ in range(max_r - min_r + 1)]
        self.matrix_bounds = bounds
        for block in self.blocks:
            r, c, q = mi_key(block)
            self.matrix[r - min_r][c - min_c] |= _Q_BITS[q]

    def get_matrix(self) -> list:
        if self.matrix is None:
            self.update_matrix()
        return self.matrix

    def block_at(self, key: tuple):
        """位置 (r, c, q) → Block；不存在回 None。"""
        for block in self.blocks:
            if mi_key(block) == key:
                return block
        return None

    # ---------- 縫隙 ----------
    def is_valid_gap(self, gap_type: str, line: int) -> bool:
        """縫隙有效性：線兩側都必須有滑塊（不在邊界上）。"""
        if gap_type not in GAP_DIRECTIONS:
            return False
        cells = self.positions()
        if not cells:
            return False
        sides = {side_of(gap_type, line, c) for c in cells}
        return sides == {0, 1}

    def all_gaps(self) -> list:
        """當前全部有效縫隙 (type, line)。"""
        cells = self.positions()
        out = []
        for gap_type in ('h', 'v', 'd1', 'd2'):
            for line in gap_index_range(gap_type, cells):
                if self.is_valid_gap(gap_type, line):
                    out.append((gap_type, line))
        return out

    # ---------- 選組 ----------
    def opt(self, gap_type: str, line: int, selected_block) -> None:
        """按縫隙切分連通組，標記 selected_block 所在的那一側。

        契約與方形/三角形版一致：第一個參數是縫隙族而非方向，DFS 用 3-鄰接
        （同格四塊兩兩相鄰 + 鄰格同朝向一塊），且不跨越縫隙線。
        """
        for block in self.blocks:
            block.be_opted = False
        if gap_type not in GAP_DIRECTIONS:
            return
        if selected_block is None:
            return
        cells = self.positions()
        start = mi_key(selected_block)
        if start not in cells:
            return
        side = side_of(gap_type, line, start)
        same_side = {c for c in cells if side_of(gap_type, line, c) == side}
        visited = set()
        stack = [start]
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            for nb in neighbors(cur):
                if nb in same_side and nb not in visited:
                    stack.append(nb)
        for block in self.blocks:
            if mi_key(block) in visited:
                block.be_opted = True

    # ---------- 移動 ----------
    def _check_step(self, moved: set, non_selected: set) -> tuple:
        """單步合法性：無碰撞 + 整體單一連通（與方形版 check_move_valid 對齊）。"""
        if moved & non_selected:
            return False, 'collision'
        if not self.is_single_connected(moved | non_selected):
            return False, 'disconnected'
        return True, ''

    def try_move_ex(self, direction: str, step: int) -> tuple:
        """預測-驗證：逐步推進，全部通過才回傳最終位置。

        返回 (positions, reason)：
            positions: [[r, c, q], ...]，與選中滑塊順序一一對應；
            reason: '' 成功；'no_selection' 無選中或方向不識別；
                    'collision' / 'disconnected' 見 _check_step。
        """
        selected = [b for b in self.blocks if b.be_opted]
        non_selected = [b for b in self.blocks if not b.be_opted]
        if not selected:
            return [], 'no_selection'
        if direction not in DIRECTIONS:
            return [], 'no_selection'
        delta = DIRECTIONS[direction]
        non_sel = {mi_key(b) for b in non_selected}
        current = [list(b.location) for b in selected]
        for _ in range(step):
            nxt = [[c[0] + delta[0], c[1] + delta[1], c[2]] for c in current]
            nxt_set = {(p[0], p[1], p[2]) for p in nxt}
            ok, reason = self._check_step(nxt_set, non_sel)
            if not ok:
                return [], reason
            current = nxt
        return current, ''

    def try_move(self, direction: str, step: int) -> list:
        """同方形版契約：只回傳最終位置，失敗為空列表。"""
        positions, _reason = self.try_move_ex(direction, step)
        return positions

    def commit_move(self, final_positions: list) -> None:
        """提交移動結果（與方形版同義：按選中順序寫回 location）。"""
        selected = [b for b in self.blocks if b.be_opted]
        for i, block in enumerate(selected):
            block.location = list(final_positions[i])

    def _clear_selection(self) -> None:
        for block in self.blocks:
            block.be_opted = False

    # ---------- 打亂 ----------
    def compute_score(self) -> float:
        """聚攏度 = 4mn / 凸包面積（以單位塊為面積單位）。

        實心 m×n 棋盤的面積恰為 4mn 塊，故復原態得分 1.0；越散凸包越大、
        得分越低。用整數鞋帶公式算任意凸包面積，因此非矩形局面（打亂中間態）
        也有分辨力，可作為打亂的散度指標。
        """
        cells = self.positions()
        if not cells:
            return 0.0
        area = hull_area_units(cells)
        if area <= 0:
            return 0.0
        target = 4 * self.m * self.n
        return min(1.0, target / area)

    def _scatter(self) -> float:
        """散度 = 1 - compute_score（0 = 復原態，越大越散）。"""
        return 1.0 - self.compute_score()

    def _scatter_of(self, cells: set) -> float:
        """給定位置集合的散度（不依賴 self.blocks，供 Metropolis 預估用）。"""
        if not cells:
            return 1.0
        area = hull_area_units(cells)
        if area <= 0:
            return 1.0
        return 1.0 - min(1.0, (4 * self.m * self.n) / area)

    def _random_move(self, step: int, bias: float, cur_scatter: float):
        """執行一次隨機合法滑動；回傳 (是否移動, 新的散度)。"""
        import math
        import random
        gaps = self.all_gaps()
        if not gaps:
            return False, cur_scatter
        gap_type, line = random.choice(gaps)
        direction = random.choice(GAP_DIRECTIONS[gap_type])
        block = random.choice(self.blocks)
        self.opt(gap_type, line, block)
        final_positions = self.try_move(direction, step)
        if not final_positions:
            self._clear_selection()
            return False, cur_scatter
        if bias > 0:
            non_sel = {mi_key(b) for b in self.blocks if not b.be_opted}
            cand_scatter = self._scatter_of(
                non_sel | {tuple(p) for p in final_positions})
            # Metropolis：候選更緊湊（散度下降）時按概率拒絕，使打亂偏向深層狀態
            if cand_scatter < cur_scatter:
                if random.random() >= math.exp(bias * (cand_scatter - cur_scatter)):
                    self._clear_selection()
                    return False, cur_scatter
            cur_scatter = cand_scatter
        self.commit_move(final_positions)
        self._clear_selection()
        return True, cur_scatter

    def shuffle(self, attempts: int, step: int, bias: float = 0.0,
                min_score: float = 0.75) -> None:
        """隨機打亂（純邏輯）：隨機選縫隙/方向/滑塊，重複合法滑動。

        參數意義與方形版一致：bias>0 用 Metropolis 準則偏向更散的狀態；
        min_score 為聚攏度下限，太高就重洗（最多 attempts*3 次重試）。
        """
        cur_scatter = self._scatter()
        for _ in range(attempts):
            _moved, cur_scatter = self._random_move(step, bias, cur_scatter)
        if min_score is None:
            return
        for _ in range(attempts * 3):
            if self.compute_score() <= min_score:
                break
            for _attempt in range(attempts):
                _moved, cur_scatter = self._random_move(step, bias, cur_scatter)
        self._clear_selection()

    # ---------- 連通性 ----------
    @staticmethod
    def is_single_connected(cells: set) -> bool:
        """3-鄰接下是否單一連通分量。"""
        if not cells:
            return True
        start = next(iter(cells))
        visited = set()
        stack = [start]
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            for nb in neighbors(cur):
                if nb in cells and nb not in visited:
                    stack.append(nb)
        return len(visited) == len(cells)

    # ---------- 復原判定 ----------
    def is_solved(self) -> bool:
        """佔用格子構成實心 m×n（或 n×m）矩形，且矩形內每格 4 塊俱全。"""
        counts = {}
        for key in self.positions():
            cell = (key[0], key[1])
            counts[cell] = counts.get(cell, 0) + 1
        if not counts:
            return False
        if any(v != 4 for v in counts.values()):
            return False
        rs = [r for r, _ in counts]
        cs = [c for _, c in counts]
        min_r, max_r = min(rs), max(rs)
        min_c, max_c = min(cs), max(cs)
        height = max_r - min_r + 1
        width = max_c - min_c + 1
        if not ((height == self.m and width == self.n) or
                (height == self.n and width == self.m)):
            return False
        return len(counts) == height * width

    # ---------- 地圖編碼 ----------
    def export_map(self) -> str:
        """導出為每格一字元的矩陣（十六進位位元 = 該格的 4-bit 網格）。

        位元 N=1、E=2、S=4、W=8，故 '0'=空、'f'=四塊俱全、其餘取中間值：
        '1'=僅 N、'2'=僅 E、'3'=N+E……規劃原稿只列了 '#'/'n'/'e'/'s'/'w'/'_'
        六種，但打亂後的局面會出現「一格里只有 2~3 塊」（移動會把某格的其中
        幾塊整組帶走），六種字符表達不了，所以按 4-bit 的本義用十六進位。
        行號列號分別是 (r - min_row, c - min_col)，導入時直接當 (r, c)。
        '#' 與 'n/e/s/w' 在導入端仍接受（手寫地圖方便），僅導出不用。
        """
        bounds = self.get_boundaries()
        min_r, max_r = bounds['min_row'], bounds['max_row']
        min_c, max_c = bounds['min_col'], bounds['max_col']
        grid = {}
        for block in self.blocks:
            r, c, q = mi_key(block)
            grid[(r, c)] = grid.get((r, c), 0) | _Q_BITS[q]
        rows = []
        for r in range(min_r, max_r + 1):
            line = []
            for c in range(min_c, max_c + 1):
                line.append(_HEX[grid.get((r, c), 0)])
            rows.append(''.join(line))
        return '\n'.join(rows)

    def import_map(self, map_str: str) -> bool:
        """從 export_map 的字元矩陣導入（行=r，列=c）。

        接受十六進位位元（'0'~'f'，大小寫皆可）、'#'=四塊俱全、
        'n/e/s/w'（單塊，大小寫皆可）、'_' 或 '.'=空。
        """
        lines = [line.strip() for line in map_str.strip().split('\n')
                 if line.strip()]
        if not lines:
            return False
        width = len(lines[0])
        if any(len(line) != width for line in lines):
            return False
        blocks = []
        for r, line in enumerate(lines):
            for c, ch in enumerate(line):
                v = _HEX_TO_BITS.get(ch.lower())
                if v is None:
                    return False
                for q in ('N', 'E', 'S', 'W'):
                    if v & _Q_BITS[q]:
                        blocks.append(_make_block(r, c, q))
        if not blocks:
            return False
        self.blocks = blocks
        self.update_matrix()
        return True


def _make_block(r: int, c: int, q: str) -> Block:
    return Block([r, c, q])
