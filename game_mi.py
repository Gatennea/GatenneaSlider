# -*- coding: utf-8 -*-
"""米字格（方格四切）謎題的建局、幾何與滑動。

形態定義（見 .zcode/plans/plan-mi-zige.md §2）
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

「一格」= 該族最短的可滑單元，與幾何長度無關（見
.zcode/plans/plan-mi-zige-diagonal-unit.md 術語段）：橫／豎一格是座標
±1（長 1 格邊）；**斜向一格是座標 ±(½,½)（長 √2/2 格邊）**，即舊版
整格斜向的一半。沒有「半格滑動」這種說法——斜向那一步就是一格；
等級 2 的斜向走兩格（±(1,1)），正是舊版等級 1 的斜距。

兩個晶格（斜向一格的直接後果，見規劃 §1.1）
------------------------------------------------------------------
斜向一格把整盤沿著一條斜縫切成兩半，各滑 ½ 格邊，於是位置出現兩種：
    A 晶格：r, c 都是整數（建局態）
    B 晶格：r, c 都是半整數（錯位態，= A 整體平移 (½,½)）
不變量是 r 與 c 同奇偶（要麼都整數、要麼都半整數），因此 r−c 與 r+c
恆為整數——兩族對角縫的 rank 公式不受影響，只有橫豎縫的 rank（就是
r、c 本身）會變成半整數。矩陣（每格 8 bit）與地圖（每格 2 個十六進位
字元）都按 floor 歸格、分晶格存放，見 update_matrix / export_map。

邊相鄰表（每塊 5 鄰：3 個同晶格 + 2 個跨晶格，見規劃 §1.4）
------------------------------------------------------------------
同晶格鄰不變；跨晶格鄰是斜向一格之後兩半唯一的相連通道，
    N(r,c) ↔ S(r−½,c−½)、S(r−½,c+½)
    E(r,c) ↔ W(r−½,c+½)、W(r+½,c+½)
    S(r,c) ↔ N(r+½,c−½)、N(r+½,c+½)
    W(r,c) ↔ E(r−½,c−½)、E(r+½,c−½)
這張表必須有：不擴鄰接的話，is_single_connected 會把每一次斜向一格
都判成「移動後滑塊會斷開」。

四族縫隙與 8 個移動方向
------------------------------------------------------------------
    'h'  格邊 y=g   rank = r   （引擎線號 L = g−1）
    'v'  格邊 x=g   rank = c   （L = g−1）
    'd1' "\" 對角線 y−x=g  rank = 2(r−c) + (0 if q∈{N,E} else 1)   （L = 2g）
    'd2' "/" 對角線 x+y=g  rank = 2(r+c) + (0 if q∈{N,W} else 1)   （L = 2(g−1)）
橫豎的引擎線號是「縫下側最後一行的行號」；對角族的引擎線號是幾何線號
的兩倍（rank 要按朝向 +1）。對角族的縫線把同格切成兩半（{N,E}｜
{S,W}、{N,W}｜{E,S}）；滿盤上只有偶數線號有效，奇數線號（兩條對角之間）
要等某條對角缺了半邊塊才可能出現，所以候選線必須由塊的跨度導出
（gap_candidates），不能按逐 2 的 range 生成。

8 個方向（每步 step 格，q 在平移下不變——沒有三角版的翻轉問題）：
        Q(↖)  W(↑)  E(↗)
        A(←)   ·    D(→)
        Z(↙)  S(↓)  X(↘)
'q'/'e'/'z'/'x' 走對角族（斜向一格 = ±½,±½），'w'/'s' 走 'v' 族，
'a'/'d' 走 'h' 族，步進都是 ±1。
"""

from __future__ import annotations

import math

from game import Block

# 8 個移動方向：字母 → (Δrow, Δcol)，每步 step 格。
# 字母按鍵盤方位排布，與螢幕方向（y 軸向下）一致：
#       Q(↖)  W(↑)  E(↗)
#       A(←)   ·    D(→)
#       Z(↙)  S(↓)  X(↘)
# 橫豎一格 = ±1（長 1 格邊）；斜向一格 = ±(½,½)（長 √2/2 格邊）——
# 斜向走的是「該族最短的可滑單元」，不是半格。等級 2 的斜向靠 step=2
# 連走兩次 ±(½,½) 得到舊版的 ±(1,1)。
DIRECTIONS = {
    'q': (-0.5, -0.5),
    'w': (-1, 0),
    'e': (-0.5, 0.5),
    'a': (0, -1),
    'd': (0, 1),
    'z': (0.5, -0.5),
    's': (1, 0),
    'x': (0.5, 0.5),
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


def mi_vertices(r, c, q: str) -> tuple:
    """單位塊的三個頂點（世界座標 (x, y)，浮點，供視圖繪製用）。

    對應形態定義的四個式子；格心是 (c+½, r+½)。公式是線性的，所以
    半整數座標（錯位態）原樣可用。
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


# 單位塊的 3 個同晶格邊相鄰（共享一條單位邊）
_SAME_NEIGHBORS = {
    'N': ((0, 0, 'W'), (0, 0, 'E'), (-1, 0, 'S')),
    'E': ((0, 0, 'N'), (0, 0, 'S'), (0, 1, 'W')),
    'S': ((0, 0, 'E'), (0, 0, 'W'), (1, 0, 'N')),
    'W': ((0, 0, 'N'), (0, 0, 'S'), (0, -1, 'E')),
}

# 單位塊的 2 個跨晶格邊相鄰（B 晶格鄰，也是共享一條半對角線單位邊）。
# 斜向一格之後兩半互相錯開半格，只剩這兩條邊相連；這張表缺了，
# is_single_connected 會把每一次斜向一格都判成 disconnected。
# 表對稱：N(r,c) ↔ S(r−½,c±½) 映回 S(r,c) ↔ N(r+½,c∓½)。
_CROSS_NEIGHBORS = {
    'N': ((-0.5, -0.5, 'S'), (-0.5, 0.5, 'S')),
    'E': ((-0.5, 0.5, 'W'), (0.5, 0.5, 'W')),
    'S': ((0.5, -0.5, 'N'), (0.5, 0.5, 'N')),
    'W': ((-0.5, -0.5, 'E'), (0.5, -0.5, 'E')),
}


def neighbors(key: tuple) -> tuple:
    """單位塊的 5 個邊相鄰單位塊（共享一條單位邊）。

    3 個同晶格鄰 + 2 個跨晶格鄰。r/c 可以是半整數（錯位態），
    ±½ 的偏移把 B 晶格鄰映回整數座標。
    """
    r, c, q = key
    if q not in _SAME_NEIGHBORS:
        raise ValueError(f"unknown quarter: {q}")
    same = _SAME_NEIGHBORS[q]
    cross = _CROSS_NEIGHBORS[q]
    return tuple((r + dr, c + dc, dq) for dr, dc, dq in same + cross)


def gap_rank(gap_type: str, key: tuple) -> float:
    """單位塊在該族縫隙座標下的「低位」索引（side_of 的判據）。

    'h'/'v' 族取格子行列：同格四塊坐在同一條格邊的同一側，取向無關。
    對角族的縫線穿過格心，把同格四塊切成兩半，必須看朝向——
    'd1'（"\\"）分 {N,E}｜{S,W}、'd2'（"/"）分 {N,W}｜{E,S}，故後半側 +1；
    同一條對角線鏈上的格 k 相同，基值一致，一條鏈就是一條完整的縫。
    錯位態下 r−c 與 r+c 仍是整數，所以對角族的 rank 恆為整數；
    橫豎的 rank 就是 r、c，會是半整數（side_of 照樣正確）。
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


def span(gap_type: str, key: tuple) -> tuple:
    """單位塊在該族縫隙座標下的跨度（引擎線號區間），見規劃 §1.3。

    縫線只要整條落在同一區域，塊就只待在它的一側；線一旦嚴格落進跨度
    內部就把這塊切開了 —— 這正是 is_valid_gap 的判據。
    引擎線號與幾何線號的關係（h/v 的 L = g−1，d1 的 L = 2g，d2 的
    L = 2(g−1)）已經折算進來，所以橫豎的跨度是 (r−1, r) 而不是 (r, r+1)。
    """
    r, c, q = key
    if gap_type == 'h':
        return (r - 1, r)
    if gap_type == 'v':
        return (c - 1, c)
    if gap_type == 'd1':
        k = 2 * (r - c)
    elif gap_type == 'd2':
        k = 2 * (r + c)
    else:
        raise ValueError(f"unknown gap type: {gap_type}")
    # 對角族：前半側（rank 不加 1 的朝向）佔 (k−2, k)，後半側佔 (k, k+2)
    if (gap_type == 'd1' and q in ('N', 'E')) or \
            (gap_type == 'd2' and q in ('N', 'W')):
        return (k - 2, k)
    return (k, k + 2)


def side_of(gap_type: str, line, key: tuple) -> int:
    """單位塊位於縫隙的哪一側：0 = 索引小的一側，1 = 大的一側。

    判據是 gap_rank：rank <= line 歸 0 側。縫隙線只經過單位塊的邊或
    頂點、不穿過內部，因此兩側劃分完備，不會有滑塊被漏掉或重複計入；
    line 可以是半整數（錯位態的橫豎縫就是半整數線號）。
    注意：這個 0/1 只保證是「縫的兩側」這個二分，兩側的組成要由
    is_valid_gap 先確認縫合法才談得上；縫無效時 opt 會直接放棄選組。
    """
    return 0 if gap_rank(gap_type, key) <= line else 1


def gap_candidates(gap_type: str, cells) -> list:
    """縫隙族的候選 line：全部跨度端點，外加相鄰端點的中點。

    端點是「沿著某條塊邊」的縫。中點是另一類：兩條同族塊邊之間整條空帶
    （缺了半條對角鏈的帶洞局面）時，帶子中間那條線也把盤面切成同樣的
    兩半——規劃 §1.3 末段說的「奇數 line（兩條對角之間）」就是它，只由
    端點生成候選就永遠提不出來。同一個空帶裡各位置的劃分相同，取中點
    一個代表就夠；它是否真的不切塊、兩側非空，由 is_valid_gap 複核
    （滿盤上中點全都切在塊裡，所以正常局面不會多出縫來）。
    """
    if gap_type not in GAP_DIRECTIONS:
        raise ValueError(f"unknown gap type: {gap_type}")
    ends = set()
    for key in cells:
        lo, hi = span(gap_type, key)
        ends.add(lo)
        ends.add(hi)
    out = set(ends)
    ordered = sorted(ends)
    for a, b in zip(ordered, ordered[1:]):
        out.add((a + b) / 2.0)
    # 整數值一律回 int：端點本來就是整數，別在中點也是整數時翻成 float
    # （線號會經 HTTP/終端指令傳來傳去，1 與 1.0 雖相等，顯示上統一好看）
    return sorted(int(v) if float(v).is_integer() else v for v in out)


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


# ---------- 跨晶格重疊判定（規劃 §1.5）----------
def lattice_of(key: tuple) -> int:
    """晶格類：0 = A（整數座標，建局態）、1 = B（半整數座標）。

    合法位置必有 2r 與 2c 同奇偶（見模組 docstring 的不變量），所以看
    2r 的奇偶就夠了。
    """
    return int(round(2.0 * key[0])) & 1


def _int_verts(key: tuple) -> list:
    """單位塊頂點乘 2 轉整數（塊座標都是 ½ 的倍數，轉換無誤差）。"""
    return [(int(round(2.0 * x)), int(round(2.0 * y)))
            for (x, y) in mi_vertices(*key)]


def _tri_overlap(a: tuple, b: tuple) -> bool:
    """兩塊是否有正面積重疊（共邊／共點不算）。

    SAT：六根分離軸 = 兩個三角形的邊法線；只要有一根軸上兩邊的投影只
    碰到邊界（有等號）就算分離，只有每根軸都嚴格重疊才是重疊。座標乘 2
    轉整數後全是精確比較，沒有浮點誤差。
    """
    pa, pb = _int_verts(a), _int_verts(b)
    for tri, other in ((pa, pb), (pb, pa)):
        for i in range(len(tri)):
            (x1, y1) = tri[i]
            (x2, y2) = tri[(i + 1) % len(tri)]
            ex, ey = x2 - x1, y2 - y1
            ta = [ey * px - ex * py for (px, py) in tri]
            tb = [ey * px - ex * py for (px, py) in other]
            if max(ta) <= min(tb) or max(tb) <= min(ta):
                return False
    return True


def _has_overlap(moved: set, non_selected: set) -> bool:
    """兩組位置之間是否存在正面積重疊的跨晶格塊對。

    §1.2 只證了「沿縫滑動時移動側與靜止側不重疊」，但 opt 移動的是一側
    的一個連通分量，同側的其它分量留在 non_selected 裡，錯位態下它們可
    以互相正面積重疊，而位置 key 不同 → 「集合不相交」放它們過去。
    同晶格的兩塊一定不重疊（單一晶格鋪滿平面、不重不漏），故只有跨晶格
    對才跑幾何，先用晶格類與包圍盒粗過濾。
    """
    if not moved or not non_selected:
        return False
    boxes = {}

    def _box(key):
        got = boxes.get(key)
        if got is None:
            vs = _int_verts(key)
            got = (min(p[0] for p in vs), min(p[1] for p in vs),
                   max(p[0] for p in vs), max(p[1] for p in vs))
            boxes[key] = got
        return got

    for a in moved:
        lat = lattice_of(a)
        ax1, ay1, ax2, ay2 = _box(a)
        for b in non_selected:
            if lat == lattice_of(b):
                continue
            bx1, by1, bx2, by2 = _box(b)
            if ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1:
                continue
            if _tri_overlap(a, b):
                return True
    return False


class MiSliderMatrix:
    """米字格滑塊矩陣（與 SliderMatrix / TriangleSliderMatrix 同契約）。

    差異處：
    - Block.location 為 [r, c, q] 三元素，q ∈ {'N','E','S','W'}；斜向一格
      之後 r/c 可以是半整數（B 晶格），見模組 docstring；
    - matrix 為每格 8-bit 網格：bit0~3 = A 晶格四塊（N/E/S/W），
      bit4~7 = B 晶格（同一格錯開半格的）四塊。
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

    # ---------- 矩陣視圖（每格 8-bit）----------
    def _matrix_bounds(self) -> dict:
        """矩陣對應的格邊界：每格的格號 = (floor(r), floor(c))。

        A 晶格塊 (R,C) 與 B 晶格塊 (R+½,C+½) 同屬幾何格 (R,C)，所以
        矩陣永遠是整數格號；錯位態的 min_row 也會是 floor 後的值。
        """
        if not self.blocks:
            return {'min_row': 0, 'max_row': 0, 'min_col': 0, 'max_col': 0}
        rs = [b.location[0] for b in self.blocks]
        cs = [b.location[1] for b in self.blocks]
        return {
            'min_row': math.floor(min(rs)), 'max_row': math.floor(max(rs)),
            'min_col': math.floor(min(cs)), 'max_col': math.floor(max(cs)),
        }

    def update_matrix(self):
        """重建 8-bit 矩陣：格 = (floor(r), floor(c))，每格 8 bit。

        bit 0~3 = A 晶格（整數座標）的四個 q，bit 4~7 = B 晶格（半整數
        座標）的四個 q——兩套三角正好鋪滿同一格。錯位態下座標是半整數，
        舊的「整數格索引」會直接 TypeError，故一律按 floor 歸格。
        """
        if not self.blocks:
            self.matrix = []
            self.matrix_bounds = {'min_row': 0, 'max_row': 0,
                                  'min_col': 0, 'max_col': 0}
            return
        bounds = self._matrix_bounds()
        min_r, max_r = bounds['min_row'], bounds['max_row']
        min_c, max_c = bounds['min_col'], bounds['max_col']
        self.matrix = [[0] * (max_c - min_c + 1) for _ in range(max_r - min_r + 1)]
        self.matrix_bounds = bounds
        for block in self.blocks:
            r, c, q = mi_key(block)
            self.matrix[math.floor(r) - min_r][math.floor(c) - min_c] |= \
                _Q_BITS[q] << (4 * lattice_of((r, c, q)))

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
    def _valid_line(self, gap_type: str, line, cells) -> bool:
        """規劃 §1.3 的精確判據（cells 由調用方算好，避免重掃 blocks）。

        一條線有效 ⇔ 它不嚴格落在任何一塊的跨度內部，且兩側都至少有一塊。
        錯位態下不能用 rank 二分判斷：半整數位置會把「騎在線上」的塊誤判
        到某一側，而那種塊其實是被縫切開的。
        """
        below = above = False
        for key in cells:
            lo, hi = span(gap_type, key)
            if lo < line < hi:
                return False
            if hi <= line:
                below = True
            else:
                above = True
        return below and above

    def is_valid_gap(self, gap_type: str, line) -> bool:
        """縫隙有效性：不被任何塊切開 + 線兩側都必須有滑塊。"""
        if gap_type not in GAP_DIRECTIONS:
            return False
        cells = self.positions()
        if not cells:
            return False
        return self._valid_line(gap_type, line, cells)

    def all_gaps(self) -> list:
        """當前全部有效縫隙 (type, line)。"""
        cells = self.positions()
        if not cells:
            return []
        out = []
        for gap_type in ('h', 'v', 'd1', 'd2'):
            for line in gap_candidates(gap_type, cells):
                if self._valid_line(gap_type, line, cells):
                    out.append((gap_type, line))
        return out

    # ---------- 選組 ----------
    def opt(self, gap_type: str, line, selected_block) -> None:
        """按縫隙切分連通組，標記 selected_block 所在的那一側。

        契約與方形/三角形版一致：第一個參數是縫隙族而非方向，DFS 用
        5-鄰接（3 個同晶格 + 2 個跨晶格），且不跨越縫隙線。縫由 UI 傳來
        時可能不合法（線切進了某塊），此時 side_of 的劃分沒有意義，直接
        放棄選組而不是猜一側。
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
        if not self._valid_line(gap_type, line, cells):
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
        """單步合法性：無碰撞 + 跨晶格無正面積重疊 + 整體單一連通。

        位置集合不相交只能擋同晶格碰撞；錯位態下兩個不同 key 的塊可以
        正面積重疊（規劃 §1.5），所以要補幾何判定。
        """
        if moved & non_selected:
            return False, 'collision'
        if _has_overlap(moved, non_selected):
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
        """佔用格子構成實心 m×n（或 n×m）矩形，且矩形內每格 4 塊俱全。

        只問形狀、容許整體平移（規劃 §3.2 決議）：一條斜縫的兩半朝同向
        各滑一格就能在整數／半數座標之間換晶格，所以「錯開半格的實心矩形」
        也算復原，不要求回到建局那張整數格圖。半整數座標只用於 min/max
        與計數，判據本身照舊。
        """
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
        """導出為字元矩陣（行=floor(r)，列=floor(c)）。

        對齊態（沒有半整數塊）導出舊的每格一字元格式：十六進位位元 =
        該格 A 晶格的 4-bit 網格（N=1、E=2、S=4、W=8），'0'=空、
        'f'=四塊俱全。規劃原稿只列了 '#'/'n'/'e'/'s'/'w'/'_' 六種，但
        打亂後的局面會出現「一格里只有 2~3 塊」，六種字符表達不了，所以
        按 4-bit 的本義用十六進位。

        一旦出現錯位態的半整數塊，同一格裡要放 8 塊，改為帶 `mi8` 標記行
        的 8-bit 格式：每格兩個十六進位字元，前一個是 A 晶格 nibble、
        後一個是 B 晶格 nibble。`mi8` 裡有非十六進位字元 'i'，不可能被
        誤讀成舊格式的地圖行，所以導入端能無歧義分辨兩種格式。
        '#' 與 'n/e/s/w' 在導入端仍接受（手寫地圖方便），僅導出不用。
        """
        keys = [mi_key(b) for b in self.blocks]
        if not keys:
            return ''
        shifted = any(lattice_of(k) for k in keys)
        grid = {}
        for (r, c, q) in keys:
            R, C = math.floor(r), math.floor(c)
            grid[(R, C)] = grid.get((R, C), 0) | \
                (_Q_BITS[q] << (4 * lattice_of((r, c, q))))
        min_r = min(R for (R, _C) in grid)
        max_r = max(R for (R, _C) in grid)
        min_c = min(C for (_R, C) in grid)
        max_c = max(C for (_R, C) in grid)
        rows = []
        for R in range(min_r, max_r + 1):
            line = []
            for C in range(min_c, max_c + 1):
                v = grid.get((R, C), 0)
                if shifted:
                    line.append(_HEX[v & 15] + _HEX[(v >> 4) & 15])
                else:
                    line.append(_HEX[v & 15])
            rows.append(''.join(line))
        head = 'mi8\n' if shifted else ''
        return head + '\n'.join(rows)

    def import_map(self, map_str: str) -> bool:
        """從 export_map 的字元矩陣導入（行=R，列=C）。

        兩種格式都能吃：帶 `mi8` 標記行的是 8-bit 格式（每格兩個十六進位
        字元，前 A 晶格 nibble、後 B 晶格 nibble，B nibble 的位元對應
        (R+½, C+½) 的四塊）；不帶標記行的是舊的每格一字元格式，只有 A
        晶格四塊（位元 N=1、E=2、S=4、W=8）。舊格式另接受 '#'=四塊俱全、
        'n/e/s/w'（單塊）、'_' 或 '.'=空。
        """
        lines = [line.strip() for line in map_str.strip().split('\n')
                 if line.strip()]
        if not lines:
            return False
        eight = lines[0].lower() == 'mi8'
        if eight:
            lines = lines[1:]
        if not lines:
            return False
        per = 2 if eight else 1
        width = len(lines[0])
        if width == 0 or width % per or any(len(line) != width for line in lines):
            return False
        cols = width // per
        blocks = []
        for R, line in enumerate(lines):
            for i in range(cols):
                chunk = line[i * per:(i + 1) * per]
                vals = [_HEX_TO_BITS.get(ch.lower()) for ch in chunk]
                if any(v is None for v in vals):
                    return False
                for q in ('N', 'E', 'S', 'W'):
                    if vals[0] & _Q_BITS[q]:
                        blocks.append(_make_block(R, i, q))
                    if len(vals) > 1 and vals[1] & _Q_BITS[q]:
                        blocks.append(_make_block(R + 0.5, i + 0.5, q))
        if not blocks:
            return False
        self.blocks = blocks
        self.update_matrix()
        return True


def _make_block(r, c, q: str) -> Block:
    return Block([r, c, q])
