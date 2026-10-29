# -*- coding: utf-8 -*-
"""形态无关的几何原语（引擎内部公用件）。

为什么单独一个模块
------------------
碎三角接入时把「共边连通 / 凸多边形重叠 / 边占用表」这套算法写通了，但它们
当时只服务碎三角，其余三个板型仍走查表邻接。要做「模型文件驱动新板型」，
这套算法必须能被任意「形状 + 放置表」复用，所以抽到这里：

* **只吃多边形，不问板型**：所有函数的输入都是顶点序列，不含任何形状字面量。
* **坐标分两层**：整数格坐标用于**身份判定**（共边、去重、缝线），平面坐标
  用于**几何判定**（重叠）。整数层不用浮点，避免「精确 float 相等只数出
  一半共边」那类坑。
* **零 pygame**：渲染层自己把格坐标经 basis 换成平面再换屏幕。

坐标约定：`verts_of(key) -> ((x, y), ...)` 返回**整数格坐标**顶点；
`plane_of(key) -> ((x, y), ...)` 返回平面坐标顶点（浮点）。
"""
import math

#: 重叠判定容差：仅相切（共边 / 共顶点）算**不重叠**。相邻滑块本就共边，
#: 若把贴合判成重叠，整个谜题会被误锁死。
EPS = 1e-9


def convex_overlap(p1, p2, eps=EPS):
    """两个**凸**多边形是否正面积重叠（分离轴定理）。

    只对凸多边形成立（本项目的滑块都是三角形/方形，均凸）。相切不算重叠。
    """
    n1, n2 = len(p1), len(p2)
    axes = []
    for poly, n in ((p1, n1), (p2, n2)):
        for i in range(n):
            ax, ay = poly[i]
            bx, by = poly[(i + 1) % n]
            axes.append((-(by - ay), bx - ax))
    for ax, ay in axes:
        proj1 = [ax * v[0] + ay * v[1] for v in p1]
        proj2 = [ax * v[0] + ay * v[1] for v in p2]
        if min(proj1) >= max(proj2) - eps or min(proj2) >= max(proj1) - eps:
            return False
    return True


def bbox(poly):
    """凸多边形的轴对齐包围盒 (min_x, min_y, max_x, max_y)（仅用于剪枝）。"""
    xs = [v[0] for v in poly]
    ys = [v[1] for v in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def boxes_overlap(b1, b2):
    """两包围盒是否相交（含边界相切）。"""
    return not (b1[2] < b2[0] or b2[2] < b1[0] or b1[3] < b2[1] or b2[3] < b1[1])


def polygon_area(poly):
    """鞋带公式面积（绝对值）；退化多边形为 0。"""
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def centroid(poly):
    """顶点的平均值（不是面积质心）。

    滑块位置用的是「顶点平均」而不是面积质心：整数格下顶点平均可能带分母
    （三角形是 /3），所以调用方通常再乘一个缩放因子存成整数；本函数只给
    需要浮点的场景用。
    """
    n = len(poly)
    if not n:
        return (0.0, 0.0)
    return (sum(v[0] for v in poly) / n, sum(v[1] for v in poly) / n)


def point_in_tri(px, py, pts):
    """点是否在三角形内（含边界）：三边同侧法，任意绕向都对。

    为什么抽到这里：三角视图（gui/triangle_view）与米字视图（gui/mi_view）
    各写了一份**逐字相同**的 ``_point_in_tri``，命中判据分叉就是「同一个
    点在一个视图里算中、在另一个里算不中」那类 bug 的温床。两份都不含
    任何板型知识（纯三点叉积符号），正好是本模块定位的形态无关原语。

    判据：把点与每条边做叉积，三者同号（或含 0）即在内部/边上；一正一负
    说明点在某一边的外侧。比重心坐标法少一次除法，也不怕退化三角形。
    """
    (ax, ay), (bx, by), (cx, cy) = pts
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)


def edge_lengths(poly):
    """各边长（浮点）。边 e_i = poly[i] -> poly[i+1]，与 `edge_map` 同序。"""
    n = len(poly)
    out = []
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        out.append(math.hypot(x2 - x1, y2 - y1))
    return out


def _edge_key(a, b):
    return (a, b) if a <= b else (b, a)


def edge_map(verts_by_key):
    """边占用表：边（两端整数格点，排序后）→ 占用它的块键列表。

    整数坐标保证「同一物理边」在相邻两块里得到**完全相同**的键，不需要
    浮点容差。返回值里的列表顺序 = 输入迭代顺序。
    """
    out = {}
    for key, vs in verts_by_key.items():
        n = len(vs)
        for i in range(n):
            e = _edge_key(vs[i], vs[(i + 1) % n])
            out.setdefault(e, []).append(key)
    return out


def shared_edge_owners(verts_by_key, min_owners=2):
    """只保留被 ≥ min_owners 块共用的边（即「内部接触边」）。"""
    return {e: o for e, o in edge_map(verts_by_key).items()
            if len(o) >= min_owners}


def components(keys, verts_of):
    """按「共边」求连通分量（几何连通，与坐标在不在基本域无关）。

    `verts_of(key)` 返回该块的整数格顶点；两块共享 ≥2 个顶点即视为连通
    （等价于共享一条边——本项目所有滑块都是多边形，重合两点必共边）。

    返回 tuple[frozenset[key], ...]（顺序按发现顺序，稳定）。
    """
    keys = frozenset(keys)
    if not keys:
        return ()
    vmap = {k: tuple(verts_of(k)) for k in keys}
    adj = {}
    for owners in shared_edge_owners(vmap).values():
        for i in range(len(owners)):
            for j in range(i + 1, len(owners)):
                a, b = owners[i], owners[j]
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
    out = []
    seen = set()
    for seed in keys:
        if seed in seen:
            continue
        seen.add(seed)
        comp = {seed}
        stack = [seed]
        while stack:
            k = stack.pop()
            for nb in adj.get(k, ()):
                if nb not in seen:
                    seen.add(nb)
                    comp.add(nb)
                    stack.append(nb)
        out.append(frozenset(comp))
    return tuple(out)


def is_connected(keys, verts_of):
    """整盘是否单一连通（滑动合法性硬条件之一）。"""
    return len(components(keys, verts_of)) <= 1
