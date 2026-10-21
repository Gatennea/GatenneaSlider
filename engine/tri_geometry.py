# -*- coding: utf-8 -*-
"""三角密铺几何（engine 斜坐标版）——P2 三角 preset 的几何层。

**坐标约定**（与 game_triangle.py 同套斜坐标，纯整数，无浮点）：
  · 引擎点 ``point = (i, j)``（斜坐标整数对，基 e1=(1,0)、e2=(1/2,√3/2)）；
  · 一块 = 单位三角，身份 (point, orient)，orient ∈ {'up', 'down'}
    （▲/▼，斜边朝向）；同一格心 (i,j) 同时容下 ▲(i,j) 与 ▼(i,j) —— 正是
    引擎 (point, orient) 联合键要区分的「同格心两块」。

**为什么独立写**（与 engine/compat.py 同源说明）：引擎纪律是不 import 任何
game*.py。本模块是三角几何在引擎坐标下的**独立真值**，与 game_triangle 的
等价性由 test/_test_geometry_engine.py 的 M 节差分钉死（移动集合 / 缝隙
有效性 / 连通性 / 还原判定轨道 / 重叠）。

缝族与 game_triangle 逐项对应：
  · 'h'  j = line  → 平行 e1，方向 a/d，rank = j（朝向无关）
  · 'p'  i = line  → 平行 e2，方向 e/z，rank = i（朝向无关）
  · 'n'  i+j = line → 平行 e2−e1，方向 w/x，rank = i+j+(0 if up else 1)
    （'n' 缝正是 ▲(i,j) 与 ▼(i,j) 共用的斜边，必须按朝向 +1 分侧）

还原态轨道（§4.2 的真问题）：正三角形有 120°/240° 旋转等效，solved_check
走凸包判定（顶点集凸包恰三顶点、三边平方长皆 k²、壳内单位三角集合等于
当前局面）——这是与 game_triangle.is_solved 逐字同标准的几何判据。
"""

# ----------------------------------------------------------------------
# 常量表
# ----------------------------------------------------------------------
#: 合法朝向（▲ / ▼）
TRI_ORIENTATIONS = ('up', 'down')

#: 每个朝向的方向向量（**点坐标单位**，(di, dj)，斜坐标）——对称群（中心
#: 反演）作用下朝向如何置换由它诱导（engine/board._orient_perm）。中心
#: 反演把 up 的方向映到 down 的方向，使朝向集闭合（见 lattice.symmetry）。
TRI_ORIENT_DIRS = {
    'up': (1, 0),
    'down': (-1, 0),
}

#: 6 个晶格移动方向：字母 → 斜坐标位移 (di, dj)（与 game_triangle.DIRECTIONS
#: 逐项一致；等价性由 M 节差分钉死）。
TRI_DIRECTIONS = {
    'd': (1, 0),     # 右      +e1
    'a': (-1, 0),    # 左      −e1
    'e': (0, 1),     # 右上    +e2
    'z': (0, -1),    # 左下    −e2
    'w': (-1, 1),    # 左上    e2−e1
    'x': (1, -1),    # 右下    e1−e2
}

#: 缝族 → 允许的移动方向（平行于缝；与 game_triangle.GAP_DIRECTIONS 同字母）
TRI_GAP_DIRECTIONS = {
    'h': ('a', 'd'),
    'p': ('e', 'z'),
    'n': ('w', 'x'),
}

#: 带朝向邻接表（Lattice.orient_steps）：每块 3 邻（共享一条边）。
#: up 的邻居全是 down（同格心 / 下方 / 左下方），down 反之；嵌套成
#: lattice 要的 ((点位移), 朝向位移) 形状。
TRI_ORIENT_STEPS = (
    ('up', (((0, 0), 'down'), ((-1, 0), 'down'), ((0, -1), 'down'))),
    ('down', (((0, 0), 'up'), ((1, 0), 'up'), ((0, 1), 'up'))),
)


# ----------------------------------------------------------------------
# 还原判定几何（斜坐标整数运算，无浮点误差；移植自 game_triangle）
# ----------------------------------------------------------------------
def _cross(o, a, b) -> int:
    """整数叉积（符号等价于平面叉积；平面坐标取 (x, y) = (2a+b, b) 放大 2×）。"""
    ox = 2 * o[0] + o[1]
    oy = o[1]
    ax = 2 * a[0] + a[1]
    ay = a[1]
    bx = 2 * b[0] + b[1]
    by = b[1]
    return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)


def convex_hull(points) -> list:
    """斜坐标点集的凸包（Andrew 单调链，逆时针，去重点）。"""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def half_chain(seq):
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
    """点是否在凸包内部或边上（hull 逆时针）。"""
    n = len(hull)
    for t in range(n):
        if _cross(hull[t], hull[(t + 1) % n], p) < 0:
            return False
    return True


def tri_vertices(i: int, j: int, up) -> tuple:
    """单位三角的三个顶点（斜坐标整数对）。up 为布尔或 'up'/'down'。"""
    up = (up == 'up') if isinstance(up, str) else bool(up)
    if up:
        return ((i, j), (i + 1, j), (i, j + 1))
    return ((i + 1, j), (i + 1, j + 1), (i, j + 1))


def cells_inside_triangle(hull) -> set:
    """凸包（三角形）内部包含的全部单位三角集合。"""
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


# ----------------------------------------------------------------------
# 缝族 rank（引擎单位；h/p 取向无关走 coeffs，仅 n 带朝向修正钩子）
# ----------------------------------------------------------------------
def rank_n(point, orient: str) -> int:
    """'n' 族（平行于 e2−e1）rank：i+j + (up 不加 / down +1)。

    ▲(i,j) 与 ▼(i,j) 共用一条 'n' 缝（它的斜边），必须按朝向分侧——
    这正是 SeamFamily.rank 钩子的用武之地（h/p 的 rank 取向无关，直接
    用 coeffs 算，不挂钩子）。
    """
    return point[0] + point[1] + (0 if orient == 'up' else 1)
