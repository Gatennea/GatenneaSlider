# -*- coding: utf-8 -*-
"""三维命中：屏幕点 → 可见面 → 切面缝 / 块（§54 第 3 步）。

投影是**正交**（`cubic_view.project_point` 就是 origin + scale·(x, −y)），所以
「射线求交」退化成正交射线：屏幕点直接命中画家算法排好序的面多边形，**按画家
序倒着测**（最近的先测）就等价于按深度取最近的那一面——不必再解一次射线方程，
也不会和渲染结果对不上（渲染画哪一面，这里就认哪一面）。

本模块纯计算，不 import pygame（与 engine 其余模块同一条纪律）。
"""

#: cubic_view 的 axis（0=X, 1=Y, 2=Z）→ 逻辑坐标下标 (r, c, d) 与缝族名。
#: 世界映射是 X=c / Y=d / Z=r（见 cubic_view 模块头）。
AXIS_TO_LOC_INDEX = {0: 1, 1: 2, 2: 0}
AXIS_TO_FAMILY = {0: 'c', 1: 'd', 2: 'r'}
#: 缝族 → 逻辑坐标下标（预览平面与判定共用）
FAMILY_TO_LOC_INDEX = {'r': 0, 'c': 1, 'd': 2}
FAMILY_TO_WORLD_AXIS = {'r': 2, 'c': 0, 'd': 1}


def point_in_quad(point, quad, tol: float = 0.0) -> bool:
    """点在凸四边形内（屏幕坐标；十字叉积同号即可，含边界）。"""
    signs = set()
    for i in range(4):
        ax, ay = quad[i]
        bx, by = quad[(i + 1) % 4]
        cross = (bx - ax) * (point[1] - ay) - (by - ay) * (point[0] - ax)
        if cross > tol:
            signs.add(1)
        elif cross < -tol:
            signs.add(-1)
    return len(signs) <= 1


def hit_face(faces, point):
    """屏幕点 → 最近的一片可见面（faces 按画家序：远的在前）。

    倒序测：先测画得最靠前的那一片，命中即返回——这就是「前块挡后块」的命中
    语义。没命中返回 None。
    """
    for face in reversed(faces or ()):
        if point_in_quad(point, face['pts']):
            return face
    return None


def face_is_internal(face, locations) -> bool:
    """该面另一侧是否还有块（= 内部面 = 一条可以选的缝）。"""
    loc, axis, sign = face['loc'], face['axis'], face['sign']
    other = list(loc)
    other[AXIS_TO_LOC_INDEX[axis]] += sign
    return tuple(other) in locations


def seam_of_face(face, is_valid_gap):
    """面 → (缝族, 缝线号)。

    面的两侧是块 v 与 v+sign；缝线号 = 这两块之间的边界（序号小的一侧）。
    若那条线两侧不同时非空（贴外沿的面），退回另一条相邻线再试；都不行返回
    None（= 这一面没挨着任何可选的切面）。
    """
    family = AXIS_TO_FAMILY[face['axis']]
    idx = AXIS_TO_LOC_INDEX[face['axis']]
    v = int(face['loc'][idx])
    primary = v if face['sign'] > 0 else v - 1
    fallback = v - 1 if face['sign'] > 0 else v
    for line in (primary, fallback):
        if is_valid_gap(family, line):
            return (family, line)
    return None


def seam_plane_polygon(family, line, blocks, pad: float = 0.0):
    """切面预览的四角（世界坐标）。

    切面是「坐标 = line+1」那张格点平面（与引擎 ``t = line + 1`` 同一口径），
    另外两轴按当前块的包围盒取（pad 默认 0：白线正好压在棋盘轮廓上，不外扩成
    一圈「浮在空中的框」）。
    """
    locs = [(int(b.location[0]), int(b.location[1]), int(b.location[2]))
            if hasattr(b, 'location') else tuple(int(v) for v in b)
            for b in blocks]
    if not locs:
        return None
    axis = FAMILY_TO_WORLD_AXIS[family]
    # 逻辑坐标 (r, c, d) → 世界坐标 (X, Y, Z) = (c, d, r)：cubic_view 的映射
    world = [(p[1], p[2], p[0]) for p in locs]
    lo = [min(p[i] for p in world) for i in range(3)]
    hi = [max(p[i] for p in world) + 1 for i in range(3)]
    fixed = float(line + 1)
    a, b = [i for i in range(3) if i != axis]
    lo_a, hi_a = lo[a] - pad, hi[a] + pad
    lo_b, hi_b = lo[b] - pad, hi[b] + pad
    corners = []
    for u, v in ((lo_a, lo_b), (hi_a, lo_b), (hi_a, hi_b), (lo_a, hi_b)):
        point = [0.0, 0.0, 0.0]
        point[axis] = fixed
        point[a] = u
        point[b] = v
        corners.append(tuple(point))
    return corners


def block_at_location(blocks, loc):
    """按 (r,c,d) 找出块对象（选中态要写 be_opted）。"""
    for b in blocks:
        if tuple(int(v) for v in b.location[:3]) == tuple(int(v) for v in loc[:3]):
            return b
    return None
