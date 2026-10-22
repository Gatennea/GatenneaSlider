# -*- coding: utf-8 -*-
"""米字格几何（engine 整数坐标版）——P2 米字 preset 的几何层。

**坐标约定**（与 game_mi.py 的真实坐标换算，全部 ×2 转整数）：
  · 引擎点 ``point = (p0, p1) = (2r, 2c)``；真实坐标 = 点 / 2。
  · 合法点满足 ``p0 ≡ p1 (mod 2)``（= r 与 c 同整/同半，A/B 双晶格的
    代数形式，见 Lattice.parity_linear）。
  · 一块 = 直角等腰三角，身份 (point, orient)，orient ∈ {N,E,S,W}
    （斜边贴格子的上/右/下/左边）。

**为什么这些函数存在**（而不是复用 game_mi.py）：引擎纪律是不 import
任何 game*.py（见 engine/compat.py 同款说明）——本模块是米字几何在
引擎坐标下的**独立真值**，与 game_mi 的等价性由 test/_test_geometry_engine.py
的 L 节差分钉死（移动集合 / 缝隙有效性 / 连通性 / 还原判定 / 重叠）。

四族缝的**线分辨率**（本模块最微妙处，推导记在这里防后人踩）：
  · d1/d2 的 game rank 本就是 2× 实数线（rank = 2(r±c)+δ），线号也是
    2×（L = 2g），整数对整数 → 引擎 ``rank_e = game rank``、``t = L+1``；
  · h/v 的 game rank 是实数线（r 或 r−½），而错位态的候选线会出现
    **¼ 线**（gap_candidates 的相邻端点中点）——点部整数模型必须放大
    到 4× 线分辨率：``rank_e = 4×实数 rank``、``t = 4L+1``。此时
    ``rank_e < t ⟺ 实数 rank ≤ L`` 精确成立（¼ℤ 与 ½ℤ 之间无中间值）。
"""

# ----------------------------------------------------------------------
# 常量表
# ----------------------------------------------------------------------
#: 合法朝向（斜边朝向：N=上 E=右 S=下 W=左）
MI_ORIENTATIONS = ('N', 'E', 'S', 'W')

#: 每个朝向的方向向量（**点坐标单位**，(d_row, d_col)，y 轴向下）——
#: 对称群作用下朝向如何置换由它诱导（engine/board._orient_perm）。
MI_ORIENT_DIRS = {
    'N': (-1, 0),
    'E': (0, 1),
    'S': (1, 0),
    'W': (0, -1),
}

#: 8 个移动方向：字母 → 引擎整数位移（×2 真实坐标）。
#: 横竖一格 = ±1 格边（点 ±2）；斜向一格 = ±(½,½)（点 ±1）——斜向走的是
#: 「该族最短的可滑单元」，不是半格；等级 2 的斜向靠 step=2 连走两次。
MI_DIRECTIONS = {
    'q': (-1, -1),
    'w': (-2, 0),
    'e': (-1, 1),
    'a': (0, -2),
    'd': (0, 2),
    'z': (1, -1),
    's': (2, 0),
    'x': (1, 1),
}

#: 缝族 → 允许的移动方向（平行于缝；与 game_mi.GAP_DIRECTIONS 同字母）
MI_GAP_DIRECTIONS = {
    'h': ('a', 'd'),
    'v': ('w', 's'),
    'd1': ('q', 'x'),
    'd2': ('e', 'z'),
}

# 边相邻表（每块 5 邻：3 同晶格共享单位边 + 2 跨晶格共享半对角线）。
# 同晶格偏移是真实整数格 ×2（点 ±2）；跨晶格偏移是真实 ±½ ×2（点 ±1）。
_SAME_NEIGHBORS = {
    'N': ((0, 0, 'W'), (0, 0, 'E'), (-2, 0, 'S')),
    'E': ((0, 0, 'N'), (0, 0, 'S'), (0, 2, 'W')),
    'S': ((0, 0, 'E'), (0, 0, 'W'), (2, 0, 'N')),
    'W': ((0, 0, 'N'), (0, 0, 'S'), (0, -2, 'E')),
}
_CROSS_NEIGHBORS = {
    'N': ((-1, -1, 'S'), (-1, 1, 'S')),
    'E': ((-1, 1, 'W'), (1, 1, 'W')),
    'S': ((1, -1, 'N'), (1, 1, 'N')),
    'W': ((-1, -1, 'E'), (1, -1, 'E')),
}

#: Lattice.orient_steps 表：朝向 → ((点位移, 朝向位移), ...)
#: （手写表用扁平三元组 (d0, d1, orient) 便于目视校对，这里嵌套成 lattice 要的形状）
MI_ORIENT_STEPS = tuple(
    (q, tuple(((d0, d1), o) for d0, d1, o in
              _SAME_NEIGHBORS[q] + _CROSS_NEIGHBORS[q]))
    for q in MI_ORIENTATIONS)


# ----------------------------------------------------------------------
# 三角几何（顶点 / 重叠）
# ----------------------------------------------------------------------
def mi_vertices(point, orient: str) -> tuple:
    """单位块的 3 个顶点（引擎整数坐标，(x, y) = (列, 行)，×2 真实值）。

    对应 game_mi.mi_vertices 的四个式子 ×2；格心 = (p1+1, p0+1)。
    公式线性，半整晶格（B 晶格）原样可用。
    """
    p0, p1 = point
    cx, cy = p1 + 1, p0 + 1
    if orient == 'N':
        return ((cx, cy), (p1, p0), (p1 + 2, p0))
    if orient == 'E':
        return ((cx, cy), (p1 + 2, p0), (p1 + 2, p0 + 2))
    if orient == 'S':
        return ((cx, cy), (p1, p0 + 2), (p1 + 2, p0 + 2))
    if orient == 'W':
        return ((cx, cy), (p1, p0), (p1, p0 + 2))
    raise ValueError(f"unknown quarter: {orient}")


def sublattice_of(key) -> tuple:
    """sub-lattice 族 = (p0 奇偶, p1 奇偶)。合法位置只有 (0,0)=A 与
    (1,1)=B 两族；同族两块永不重叠（每族各自铺满平面一个子区域，
    game_mi 穷举实测零反例），跨族才需跑几何。"""
    return (key[0][0] & 1, key[0][1] & 1)


def _tri_overlap(a: tuple, b: tuple) -> bool:
    """两块是否有正面积重叠（共边/共点不算）。

    SAT：六根分离轴 = 两个三角形的边法线；任一轴上投影只碰边界
    （有等号）即分离。顶点已是整数，精确比较无浮点误差。
    """
    for tri, other in ((a, b), (b, a)):
        for i in range(len(tri)):
            (x1, y1) = tri[i]
            (x2, y2) = tri[(i + 1) % len(tri)]
            ex, ey = x2 - x1, y2 - y1
            ta = [ey * px - ex * py for (px, py) in tri]
            tb = [ey * px - ex * py for (px, py) in other]
            if max(ta) <= min(tb) or max(tb) <= min(ta):
                return False
    return True


def _bbox(verts):
    return (min(v[0] for v in verts), min(v[1] for v in verts),
            max(v[0] for v in verts), max(v[1] for v in verts))


def has_overlap(moved, rest) -> bool:
    """两簇块键之间是否有几何重叠（含同键）——BoardSpec.overlap 钩子。

    与 game_mi._has_overlap 同标准：先查键相交（同键 = 同三角），
    再对**跨 sub-lattice 族**对跑 SAT（错位态下不同键的两块可以
    正面积重叠，「键集合不相交」放它们过去就是死盘）。
    """
    if not moved or not rest:
        return False
    if moved & rest:
        return True
    ns = [(k, sublattice_of(k), _bbox(mi_vertices(*k))) for k in rest]
    for a in moved:
        fa = sublattice_of(a)
        va = mi_vertices(*a)
        ax1, ay1, ax2, ay2 = _bbox(va)
        for b, fb, (bx1, by1, bx2, by2) in ns:
            if fa == fb:
                continue
            if ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1:
                continue
            if _tri_overlap(va, mi_vertices(*b)):
                return True
    return False


# ----------------------------------------------------------------------
# 四族缝的 rank 与 span（引擎单位）
# ----------------------------------------------------------------------
def rank_h(point, orient: str) -> int:
    """h 族（横缝）rank = 4×实数 rank：N 块尖朝下扣半格（−2），其余整格。"""
    return 2 * point[0] - (2 if orient == 'N' else 0)


def rank_v(point, orient: str) -> int:
    """v 族（竖缝）rank = 4×实数 rank：W 块尖朝右扣半格（−2），其余整格。"""
    return 2 * point[1] - (2 if orient == 'W' else 0)


def rank_d1(point, orient: str) -> int:
    """d1 族（"\\"）rank = 2(r−c) + 朝向修正（{N,E} 不加、{S,W} 加 1）。"""
    return (point[0] - point[1]) + (0 if orient in ('N', 'E') else 1)


def rank_d2(point, orient: str) -> int:
    """d2 族（"/"）rank = 2(r+c) + 朝向修正（{N,W} 不加、{E,S} 加 1）。"""
    return (point[0] + point[1]) + (0 if orient in ('N', 'W') else 1)


def span_t(family, point, orient: str) -> tuple:
    """块在族 family 的缝坐标跨度（引擎 t 单位的**开**区间）。

    线 t 严格落进跨度内部 = 切块 = 该缝锁死（is_valid_gap 判据）。
    h/v 由实数跨度 ×4+1 折算（N/S/W/E 只占半格的朝向，跨度含奇数
    端点）；d1/d2 由 2× 跨度 +1 折算（前半侧朝向 (k−2,k)、后半侧 (k,k+2)）。
    """
    p0, p1 = point
    if family.name == 'h':
        if orient == 'N':
            return (2 * p0 - 3, 2 * p0 - 1)
        if orient == 'S':
            return (2 * p0 - 1, 2 * p0 + 1)
        return (2 * p0 - 3, 2 * p0 + 1)      # E/W 占满整格高
    if family.name == 'v':
        if orient == 'W':
            return (2 * p1 - 3, 2 * p1 - 1)
        if orient == 'E':
            return (2 * p1 - 1, 2 * p1 + 1)
        return (2 * p1 - 3, 2 * p1 + 1)      # N/S 占满整格宽
    if family.name == 'd1':
        k = p0 - p1
        return (k - 1, k + 1) if orient in ('N', 'E') else (k + 1, k + 3)
    if family.name == 'd2':
        k = p0 + p1
        return (k - 1, k + 1) if orient in ('N', 'W') else (k + 1, k + 3)
    raise ValueError(f"unknown gap family: {family.name!r}")


def seam_locked(family, t, board) -> bool:
    """span 锁死判据（BoardSpec.seam_clear 钩子）：t 切进任何块即锁死。

    与 game_mi._valid_line 的跨度判据同标准：线只经过块的边或顶点时
    不切块（t 落在跨度端点上），严格落进内部才锁死。
    """
    for b in board.blocks:
        lo, hi = span_t(family, b.point, b.orient)
        if lo < t < hi:
            return True
    return False


# ----------------------------------------------------------------------
# 块的几何顶点（散度/聚拢度用；真实坐标 (x, y)，与 game_mi.mi_vertices
# 同式，供差分对拍）
# ----------------------------------------------------------------------
def block_vertices(r, c, q: str) -> tuple:
    """单位块的三个顶点（**真实坐标** (x, y)，浮点；格心 = (c+½, r+½)）。

    公式是线性的，半整数坐标（错位态）原样可用。与 game_mi.mi_vertices
    逐式同形——引擎侧自持一份，避免反向依赖旧引擎；等价性由测试钉死。
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
    raise ValueError(f"unknown quarter: {q!r}")
