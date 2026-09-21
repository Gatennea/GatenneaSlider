# -*- coding: utf-8 -*-
"""
正三角形密鋪滑塊核心邏輯（Stage B1：靜態雛形）。

座標系（斜座標，純整數）
------------------------------------------------------------------
以菱形胞 R(i, j) 為基本單元，其頂點 V(i,j) = i·e1 + j·e2：
    e1 = (1, 0)，e2 = (1/2, √3/2)   （純數學朝向，y 軸向上）
平面上的點一律以斜座標整數對 (a, b) 表示，含義為 a·e1 + b·e2，
因此所有幾何判定都是整數運算，不引入浮點誤差。

每個菱形胞含兩個單位三角：
    ▲(i, j) = {V, V+e1, V+e2}          尖朝上
    ▼(i, j) = {V+e1, V+e1+e2, V+e2}    尖朝下

滑塊單元 = 一個單位三角，位置記為 (i, j, up)：
    up=True → ▲(i, j)；up=False → ▼(i, j)

螢幕朝向（gui/triangle_view.py）：e2 畫到「右上」（pygame y 軸向下時取負），
所以 ▲ 在畫面上尖朝上、初始大三角形也是尖朝上的經典造型。

鄰接（共享一條邊，恰 3 個鄰居）
------------------------------------------------------------------
    ▲(i, j) ↔ ▼(i, j)、▼(i-1, j)、▼(i, j-1)
    ▼(i, j) ↔ ▲(i, j)、▲(i+1, j)、▲(i, j+1)

縫隙族（切割線）與可行移動方向
------------------------------------------------------------------
    'h'：j = line   （平行 e1，水平）    → 平移 ±e1       方向 'a' / 'd'
    'p'：i = line   （平行 e2）          → 平移 ±e2       方向 'e' / 'z'
    'n'：i+j = line （平行 e2-e1）       → 平移 ±(e2-e1)  方向 'w' / 'x'
任何整數斜座標平移都會把三角密鋪映射到自身，因此這 6 個方向
滑動後仍保持密鋪（垂直於縫隙的方向不在晶格上，不可行）。

鍵盤佈局（與螢幕方向對應，y 軸向下；六鍵正好圍住 S 成六邊形）：
        W(↖)  E(↗)
      A(←)   ·   D(→)
        Z(↙)  X(↘)

滑動操作（B2）
------------------------------------------------------------------
鍵盤只是捷徑：六個字母對應六個晶格方向，按鍵即「選穿過當前滑塊的
縫 + 沿該方向走 current_step 格」。主路徑是單次觸控拖動——手勢只提供
一個向量，由呼叫方投影吸附到六個方向中投影最大者，再交給
resolve_drag() 完成選組與步數夾緊。因此日後換成 12 向的新形狀，
只需擴充 DIRECTIONS / GAP_DIRECTIONS 兩張表，互動代碼不改。

復原判定
------------------------------------------------------------------
全部 k² 個單位三角拼成一個邊長 k 的實心大正三角形即通關；
位置不限（可平移），朝向不限（120°/240° 旋轉等效）。
實用凸包判定：頂點集凸包必須恰為三頂點、三邊長皆 k，
且殼內單位三角集合與當前局面完全一致。

已落實：建局 / 幾何 / 復原判定 / 矩陣視圖 / 地圖編碼 /
滑動（opt / try_move_ex / commit_move / resolve_drag）/ 打亂。
撤回重做與動畫（B3）、存讀檔 v2 三角分支（B4）另行處理。
"""

from __future__ import annotations

from game import Block

# 6 個晶格移動方向：字母 → 斜座標位移 (di, dj)
# 字母按螢幕方向佈局（見模組 docstring 的鍵盤圖）：W E / A D / Z X
DIRECTIONS = {
    'd': (1, 0),    # 右      +e1
    'a': (-1, 0),   # 左      -e1
    'e': (0, 1),    # 右上    +e2
    'z': (0, -1),   # 左下    -e2
    'w': (-1, 1),   # 左上    e2-e1
    'x': (1, -1),   # 右下    e1-e2
}

# 縫隙族 → 該族允許的移動方向（平行於縫隙線）
GAP_DIRECTIONS = {
    'h': ('a', 'd'),
    'p': ('e', 'z'),
    'n': ('w', 'x'),
}

# 螢幕單位向量（y 軸向下，與 pygame 一致）：用於手勢分區/虛擬鍵盤
DIRECTION_SCREEN = {
    'd': (1.0, 0.0),
    'a': (-1.0, 0.0),
    'e': (0.5, -0.8660254037844386),
    'z': (-0.5, 0.8660254037844386),
    'w': (-0.5, -0.8660254037844386),
    'x': (0.5, 0.8660254037844386),
}


def tri_vertices(i: int, j: int, up: bool) -> tuple:
    """單位三角的三個頂點（斜座標整數對）。"""
    if up:
        return ((i, j), (i + 1, j), (i, j + 1))
    return ((i + 1, j), (i + 1, j + 1), (i, j + 1))


def tri_key(block) -> tuple:
    """Block → (i, j, up)。"""
    loc = block.location
    return (loc[0], loc[1], bool(loc[2]))


def neighbors(key: tuple) -> tuple:
    """單位三角的 3 個邊相鄰單位三角。"""
    i, j, up = key
    if up:
        return ((i, j, False), (i - 1, j, False), (i, j - 1, False))
    return ((i, j, True), (i + 1, j, True), (i, j + 1, True))


def gap_rank(gap_type: str, key: tuple) -> int:
    """單位三角在該族縫隙座標下的「低位」索引（side_of 的判據）。

    'h' 族取 j、'p' 族取 i：同一菱形胞的 ▲/▼ 坐在同一條水平/60° 縫的
    同一側，取向無關。'n' 族取 i+j，但必須看朝向——▲(i,j) 與 ▼(i,j)
    同屬一個菱形胞，分隔二者的斜邊平行 e2−e1，正是 'n' 族的縫：▲ 在
    座標小的一側、▼ 在大的一側，所以 ▼ 要 +1。
    """
    i, j, up = key
    if gap_type == 'h':
        return j
    if gap_type == 'p':
        return i
    if gap_type == 'n':
        return i + j + (0 if up else 1)
    raise ValueError(f"unknown gap type: {gap_type}")


def side_of(gap_type: str, line: int, key: tuple) -> int:
    """單位三角位於縫隙的哪一側：0 = 索引小的一側，1 = 大的一側。

    判據是 gap_rank：rank <= line 歸 0 側。縫隙線只經過單位三角的邊或
    頂點、不穿過內部，因此兩側劃分完備，不會有滑塊被漏掉或重複計入。
    """
    return 0 if gap_rank(gap_type, key) <= line else 1


def gap_index_range(gap_type: str, cells) -> range:
    """縫隙族的候選 line 範圍（保證線兩側都至少有一個滑塊）。

    cells：位置集合 (i, j, up)。候選範圍按 gap_rank 取，與 side_of 同一
    套判據；是否真的兩側非空由 is_valid_gap 複核。
    """
    if gap_type == 'h':
        jjs = [j for _, j, _ in cells]
        return range(min(jjs), max(jjs))
    if gap_type == 'p':
        iis = [i for i, _, _ in cells]
        return range(min(iis), max(iis))
    if gap_type == 'n':
        ranks = [gap_rank('n', c) for c in cells]
        return range(min(ranks), max(ranks))
    raise ValueError(f"unknown gap type: {gap_type}")


def gap_for_direction(direction: str):
    """移動方向字母 → 所屬縫隙族；不相關時回 None。"""
    for gap_type, dirs in GAP_DIRECTIONS.items():
        if direction in dirs:
            return gap_type
    return None


def finger_line(gap_type: str, key: tuple) -> int:
    """穿過該單位三角的縫隙索引（單次觸控拖動的「縫隙線穿過手指」規則）。

    'h' 族索引是 j、'p' 族是 i、'n' 族是 i+j；取滑塊自身的索引，
    保證「一塊 + 一個方向族」對應唯一一條線，無需玩家去點看不見的縫。
    """
    i, j, _up = key
    if gap_type == 'h':
        return j
    if gap_type == 'p':
        return i
    if gap_type == 'n':
        return i + j
    raise ValueError(f"unknown gap type: {gap_type}")


def _cross(o, a, b) -> int:
    """整數叉積（符號等價於平面叉積，用於凸包與半平面判定）。

    平面座標取 (x, y) = (a + b/2, (√3/2)·b)，整體乘以 2/√3 化為整數：
        cross = ((2a+b) - (2o_a+o_b))·(b_y - o_b) - (a_y - o_a)·((2b_x+b_y) - (2o_x+o_y))
    """
    ox = 2 * o[0] + o[1]
    oy = o[1]
    ax = 2 * a[0] + a[1]
    ay = a[1]
    bx = 2 * b[0] + b[1]
    by = b[1]
    return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)


def convex_hull(points) -> list:
    """斜座標點集的凸包（Andrew 單調鏈，逆時針，去重點）。"""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def half_chain(seq) -> list:
        out = []
        for p in seq:
            while len(out) >= 2 and _cross(out[-2], out[-1], p) <= 0:
                out.pop()
            out.append(p)
        return out

    lower = half_chain(pts)
    upper = half_chain(reversed(pts))
    return lower[:-1] + upper[:-1]


def _point_in_convex(p, hull) -> bool:
    """點是否在凸包內部或邊上（hull 為逆時針）。"""
    n = len(hull)
    for t in range(n):
        if _cross(hull[t], hull[(t + 1) % n], p) < 0:
            return False
    return True


def cells_inside_triangle(hull) -> set:
    """凸包（三角形）內部包含的全部單位三角集合。"""
    amin = min(p[0] for p in hull)
    amax = max(p[0] for p in hull)
    bmin = min(p[1] for p in hull)
    bmax = max(p[1] for p in hull)
    inside = set()
    for i in range(amin - 1, amax + 2):
        for j in range(bmin - 1, bmax + 2):
            for up in (True, False):
                verts = tri_vertices(i, j, up)
                if all(_point_in_convex(v, hull) for v in verts):
                    inside.add((i, j, up))
    return inside


def hull_area_units(verts) -> int:
    """點集凸包的面積，以「單位三角個數」為單位（整數）。

    平面座標取 (X, Y) = (2a+b, b)（斜座標的整數線性變換，面積放大 2 倍），
    鞋帶公式求和後除以 2 即得單位三角數。邊長 k 的實心大正面積恰為 k²，
    因此這是一個與形態無關的散度基準：任何非三角形局面也能量得到面積。
    """
    hull = convex_hull(verts)
    if len(hull) < 3:
        return 0
    total = 0
    n = len(hull)
    for t in range(n):
        a1, b1 = hull[t]
        a2, b2 = hull[(t + 1) % n]
        total += (2 * a1 + b1) * b2 - (2 * a2 + b2) * b1
    return abs(total) // 2


class TriangleSliderMatrix:
    """正三角形密鋪滑塊矩陣。

    與 SliderMatrix 盡量保持相同契約（blocks / matrix / matrix_bounds /
    get_boundaries / update_matrix / is_solved），差異處：
    - Block.location 為 [i, j, up] 三元素；
    - matrix 為菱形胞 2-bit 網格（bit0=▲ 存在，bit1=▼ 存在）。
    """

    __slots__ = ('k', 'm', 'n', 'blocks', 'matrix', 'matrix_bounds')

    def __init__(self, k: int = 6):
        if k < 2:
            raise ValueError("triangle side k must be >= 2")
        self.k = k
        self.m = k
        self.n = k
        self.blocks = []
        # ▲(i, j)：i, j >= 0 且 i+j <= k-1
        for i in range(k):
            for j in range(k - i):
                self.blocks.append(_make_block(i, j, True))
        # ▼(i, j)：i, j >= 0 且 i+j <= k-2
        for i in range(k - 1):
            for j in range(k - 1 - i):
                self.blocks.append(_make_block(i, j, False))
        self.matrix = None
        self.matrix_bounds = None
        self.update_matrix()

    def goal_cells(self) -> set:
        """目標輪廓：邊長 k 實心大三角形（尖朝上）的單位三角位置集合。

        分布與建局一致；導入局部地圖後目標輪廓不隨之改變。
        供測試構造「已還原」局面與另存為謎題判斷形態用。
        """
        cells = {(i, j, True) for i in range(self.k) for j in range(self.k - i)}
        cells |= {(i, j, False)
                  for i in range(self.k - 1) for j in range(self.k - 1 - i)}
        return cells

    # ---------- 位置集合 ----------
    def positions(self) -> set:
        """全部滑塊位置 (i, j, up) 集合。"""
        return {tri_key(b) for b in self.blocks}

    def get_boundaries(self) -> dict:
        """滑塊在斜座標下的邊界（row=i, col=j，與方形同鍵名）。"""
        if not self.blocks:
            return {'min_row': 0, 'max_row': 0, 'min_col': 0, 'max_col': 0}
        iis = [b.location[0] for b in self.blocks]
        jjs = [b.location[1] for b in self.blocks]
        return {
            'min_row': min(iis), 'max_row': max(iis),
            'min_col': min(jjs), 'max_col': max(jjs),
        }

    # ---------- 矩陣視圖（菱形胞 2-bit）----------
    def update_matrix(self):
        """重建 0/1/2/3 矩陣：0=空、1=僅▲、2=僅▼、3=▲▼俱全。"""
        if not self.blocks:
            self.matrix = []
            self.matrix_bounds = {'min_row': 0, 'max_row': 0, 'min_col': 0, 'max_col': 0}
            return
        bounds = self.get_boundaries()
        min_i, max_i = bounds['min_row'], bounds['max_row']
        min_j, max_j = bounds['min_col'], bounds['max_col']
        rows = max_i - min_i + 1
        cols = max_j - min_j + 1
        self.matrix = [[0] * cols for _ in range(rows)]
        self.matrix_bounds = bounds
        for block in self.blocks:
            i, j, up = tri_key(block)
            self.matrix[i - min_i][j - min_j] |= 1 if up else 2

    def get_matrix(self) -> list:
        if self.matrix is None:
            self.update_matrix()
        return self.matrix

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
        for gap_type in ('h', 'p', 'n'):
            for line in gap_index_range(gap_type, cells):
                if self.is_valid_gap(gap_type, line):
                    out.append((gap_type, line))
        return out

    # ---------- 選組（B2）----------
    def opt(self, gap_type: str, line: int, selected_block) -> None:
        """按縫隙切分連通組，標記 selected_block 所在的那一側。

        契約與方形版 SliderMatrix.opt 一致：第一個參數是縫隙族而非方向，
        DFS 用 3-鄰接（▲↔▼ 交錯），且不跨越縫隙線。
        """
        for block in self.blocks:
            block.be_opted = False
        if gap_type not in GAP_DIRECTIONS:
            return
        cells = self.positions()
        start = tri_key(selected_block)
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
            if tri_key(block) in visited:
                block.be_opted = True

    # ---------- 移動（B2）----------
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
            positions: [[i, j, up], ...]，與選中滑塊順序一一對應；
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
        non_sel = {tri_key(b) for b in non_selected}
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

    def block_at(self, key: tuple):
        """位置 (i, j, up) → Block；不存在回 None。"""
        for block in self.blocks:
            if tri_key(block) == key:
                return block
        return None

    def resolve_drag(self, key: tuple, direction: str, steps: int) -> tuple:
        """單次觸控拖動解析：手指下的滑塊 + 一個晶格方向 → 可行移動。

        這是「優先單次觸控拖動」的落點：呼叫方只負責把手勢向量吸附到
        六個晶格方向之一（取投影最大者），剩下的選組/步數夾緊都在這裡，
        因此以後形狀改成 12 向也只換 DIRECTIONS 表。

        縫隙線優先取穿過手指那條；無效時依序外推鄰近線，讓按在外沿
        也有合理手感。步數從 steps 遞減嘗試，實現「拖到哪算哪、能走
        幾格走幾格」。

        返回 (positions, gap_type, line, reason, steps)；
        positions 為空即失敗，此時 steps 為 0。成功時會留下 opt 選中態，
        失敗時清空選中態。
        """
        if direction not in DIRECTIONS:
            return [], None, None, 'bad_direction', 0
        if key not in self.positions():
            return [], None, None, 'no_block', 0
        gap_type = gap_for_direction(direction)
        base = finger_line(gap_type, key)
        cells = self.positions()
        for dist in range(0, self.k + 1):
            for line in ({base - dist, base + dist} if dist else {base}):
                if line not in gap_index_range(gap_type, cells):
                    continue
                if not self.is_valid_gap(gap_type, line):
                    continue
                block = self.block_at(key)
                if block is None:
                    return [], gap_type, line, 'no_block', 0
                self.opt(gap_type, line, block)
                for n in range(max(1, steps), 0, -1):
                    positions, reason = self.try_move_ex(direction, n)
                    if positions:
                        return positions, gap_type, line, '', n
        self._clear_selection()
        return [], gap_type, base, 'no_move', 0

    def _clear_selection(self) -> None:
        for block in self.blocks:
            block.be_opted = False

    # ---------- 打亂（B2）----------
    def compute_score(self) -> float:
        """聚攏度 = k² / 凸包面積（以單位三角為面積單位）。

        實心大正三角的面積恰為 k²，故復原態得分 1.0；越散凸包越大、
        得分越低。用整數鞋帶公式算任意凸包面積，因此非三角形局面
        （打亂中間態）也有分辨力，可作為打亂的散度指標。
        """
        cells = self.positions()
        if not cells:
            return 0.0
        verts = set()
        for key in cells:
            verts.update(tri_vertices(*key))
        area = hull_area_units(verts)
        if area <= 0:
            return 0.0
        return min(1.0, (self.k * self.k) / area)

    def _scatter(self) -> float:
        """散度 = 1 - compute_score（0 = 復原態，越大越散）。"""
        return 1.0 - self.compute_score()

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
            for b in self.blocks:
                b.be_opted = False
            return False, cur_scatter
        if bias > 0:
            non_sel = {tri_key(b) for b in self.blocks if not b.be_opted}
            cand_scatter = self._scatter_of(non_sel | {tuple(p) for p in final_positions})
            # Metropolis：候選更緊湊（散度下降）時按概率拒絕，使打亂偏向深層狀態
            if cand_scatter < cur_scatter:
                if random.random() >= math.exp(bias * (cand_scatter - cur_scatter)):
                    for b in self.blocks:
                        b.be_opted = False
                    return False, cur_scatter
            cur_scatter = cand_scatter
        self.commit_move(final_positions)
        for b in self.blocks:
            b.be_opted = False
        return True, cur_scatter

    def _scatter_of(self, cells: set) -> float:
        """給定位置集合的散度（不依賴 self.blocks，供 Metropolis 預估用）。"""
        if not cells:
            return 1.0
        verts = set()
        for key in cells:
            verts.update(tri_vertices(*key))
        area = hull_area_units(verts)
        if area <= 0:
            return 1.0
        return 1.0 - min(1.0, (self.k * self.k) / area)

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
        for b in self.blocks:
            b.be_opted = False

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
        """全部 k² 個單位三角拼成邊長 k 的實心大正三角形（位置/朝向不限）。"""
        cells = self.positions()
        if len(cells) != self.k * self.k:
            return False
        verts = set()
        for key in cells:
            verts.update(tri_vertices(*key))
        hull = convex_hull(verts)
        if len(hull) != 3:
            return False
        target = self.k * self.k
        for t in range(3):
            da = hull[(t + 1) % 3][0] - hull[t][0]
            db = hull[(t + 1) % 3][1] - hull[t][1]
            if da * da + da * db + db * db != target:
                return False
        return cells_inside_triangle(hull) == cells

    # ---------- 地圖編碼 ----------
    def export_map(self) -> str:
        """導出為菱形胞字元矩陣：'#'=▲▼俱全 '^'=僅▲ 'v'=僅▼ '_'=空。"""
        bounds = self.get_boundaries()
        min_i, max_i = bounds['min_row'], bounds['max_row']
        min_j, max_j = bounds['min_col'], bounds['max_col']
        grid = {}
        for block in self.blocks:
            i, j, up = tri_key(block)
            grid[(i, j)] = grid.get((i, j), 0) | (1 if up else 2)
        rows = []
        for i in range(min_i, max_i + 1):
            line = []
            for j in range(min_j, max_j + 1):
                v = grid.get((i, j), 0)
                line.append('#' if v == 3 else ('^' if v == 1 else ('v' if v == 2 else '_')))
            rows.append(''.join(line))
        return '\n'.join(rows)

    def import_map(self, map_str: str) -> bool:
        """從 export_map 的字元矩陣導入（行=斜座標 i，列=斜座標 j）。"""
        lines = [line.strip() for line in map_str.strip().split('\n') if line.strip()]
        if not lines:
            return False
        width = len(lines[0])
        if any(len(line) != width for line in lines):
            return False
        blocks = []
        for r, line in enumerate(lines):
            for c, ch in enumerate(line):
                if ch == '#':
                    blocks.append(_make_block(r, c, True))
                    blocks.append(_make_block(r, c, False))
                elif ch == '^':
                    blocks.append(_make_block(r, c, True))
                elif ch == 'v':
                    blocks.append(_make_block(r, c, False))
                elif ch != '_':
                    return False
        if not blocks:
            return False
        self.blocks = blocks
        self.update_matrix()
        return True


def _make_block(i: int, j: int, up: bool) -> Block:
    return Block([i, j, up])
