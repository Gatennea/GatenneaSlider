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


def _point_seg_distance(point, a, b) -> float:
    """点到线段的距离（屏幕像素）。"""
    px, py = point
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 <= 1e-12:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / seg2
    t = max(0.0, min(1.0, t))
    qx, qy = ax + t * dx, ay + t * dy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


def _shared_vertex(a, b, tol: float = 1.0) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _point_quad_distance(point, quad) -> float:
    """点到凸四边形的距离（在内部为 0）。"""
    if point_in_quad(point, quad):
        return 0.0
    best = float('inf')
    for i in range(len(quad)):
        best = min(best, _point_seg_distance(point, quad[i], quad[(i + 1) % len(quad)]))
    return best


def seam_edge_distance(faces, hit_face, point, band: float = 28.0) -> float:
    """点到「这条面旁边的缝线」的距离（像素）；没有缝线时返回 inf。

    注意块之间**有拆分缝隙**（gap>0 时两块的面并不共边，中间隔着一条缝带），
    所以不能按「共享顶点」认缝。这里反过来认：面的某条边的中点若贴着另一块
    **同轴同符号**的面（距离 ≈ 缝宽像素）就算缝边——那条边就是缝在画面上的
    位置。用户 2026-11-17 实测：双击选块时第一次点击被当成「选缝」，缝跟着跳；
    现在只有点在这条边附近才算，点面内其它位置不动缝。
    """
    pts = hit_face.get('pts') or []
    loc = hit_face.get('loc')
    axis, sign = hit_face.get('axis'), hit_face.get('sign')
    others = [f for f in (faces or ())
              if f is not hit_face and f.get('loc') != loc
              and f.get('axis') == axis and f.get('sign') == sign]
    best = float('inf')
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        for other in others:
            if _point_quad_distance(mid, other.get('pts') or ()) <= band:
                best = min(best, _point_seg_distance(point, a, b))
                break
    return best


def face_is_internal(face, locations) -> bool:
    """该面另一侧是否还有块（= 内部面 = 一条可以选的缝）。"""
    loc, axis, sign = face['loc'], face['axis'], face['sign']
    other = list(loc)
    other[AXIS_TO_LOC_INDEX[axis]] += sign
    return tuple(other) in locations


#: 世界轴 → 缝族名（X=c / Y=d / Z=r）
WORLD_AXIS_TO_FAMILY = {0: 'c', 1: 'd', 2: 'r'}


def _screen_axis_dir(scene, world_axis) -> tuple:
    """世界轴在屏幕上的方向（含缩放；y 向下）。"""
    cam = scene['camera']
    scale = float(scene['scale'])
    v = [0.0, 0.0, 0.0]
    v[world_axis] = 1.0
    c = cam.to_camera(tuple(v))
    dx, dy = scale * c[0], -scale * c[1]
    n = (dx * dx + dy * dy) ** 0.5 or 1.0
    return (dx / n, dy / n)


def seam_at_point(scene, face, point, is_valid_gap):
    """点 → 画面上**那条**缝（族, 线号）+ 点到它的距离。

    旧实现 `seam_of_face` 按面的法向取缝族：点前面就相当于选中这块**背后**那
    张平行切面——那是一条在画面上根本看不见的缝（用户 2026-11-17 实测：点
    「贴着屏幕的那条缝」选出来的却是别的）。这里改成**按离点击最近的那条面
    边认缝**：一条面边沿着某个世界轴走，跨过它换的是另一个世界轴，缝族就是
    后者；块在这条边的一侧决定缝线号（下界 k → line=k-1，上界 k+1 → line=k）。

    返回 ``(dist, family, line)``；附近没有有效缝返回 ``None``。
    """
    pts = face.get('pts') or []
    if len(pts) < 4:
        return None
    cen = (sum(p[0] for p in pts) / float(len(pts)),
           sum(p[1] for p in pts) / float(len(pts)))
    axis = face['axis']
    inplane = [w for w in (0, 1, 2) if w != axis]
    best = None
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        ex, ey = b[0] - a[0], b[1] - a[1]
        en = (ex * ex + ey * ey) ** 0.5
        if en <= 1e-6:
            continue
        ex, ey = ex / en, ey / en
        along = None
        for w in inplane:
            sd = _screen_axis_dir(scene, w)
            if abs(ex * sd[0] + ey * sd[1]) > 0.85:      # 这条边跟这根世界轴走
                along = w
                break
        if along is None:
            continue
        across = [w for w in inplane if w != along][0]
        sd = _screen_axis_dir(scene, across)
        outward = ((mid[0] - cen[0]) * sd[0] + (mid[1] - cen[1]) * sd[1]) > 0
        fam = WORLD_AXIS_TO_FAMILY[across]
        idx = AXIS_TO_LOC_INDEX[across]
        k = int(face['loc'][idx])
        line = k if outward else k - 1
        if not is_valid_gap(fam, line):
            continue
        dist = _point_seg_distance(point, a, b)
        if best is None or dist < best[0]:
            best = (dist, fam, line)
    return best


def _is_internal_cut(family, line, locations) -> bool:
    """这条缝线是不是「块与块之间」的切面（两侧都真有块）。

    包围盒那层平面（最外侧）一侧永远没有块，不算——用户 2026-11-17：
    「外表面（只要不是包围盒的表面）也要可以选中」。
    """
    if not locations:
        return False
    idx = FAMILY_TO_LOC_INDEX[family]
    ks = [int(loc[idx]) for loc in locations]
    return any(k <= line for k in ks) and any(k >= line + 1 for k in ks)


def seam_of_face(face, is_valid_gap, locations=None):
    """点中一块的某个面 → 它所属的**内部切面**（不是包围盒平面）。

    2026-11-17 用户口径（扩大可选范围）：可点的面不止缝里的墙，**块的任意外
    表面**都算——但推出来的平面不能是包围盒那层。做法：先试「面外侧那条线」
    （sign>0 → v，sign<0 → v-1）是内部切面就用（缝里的墙走这条，天然命中）；
    否则退回「块的另一条边界」。所以点最前面那块的前脸，得到的是它与后面
    那层之间的切面（画面里与屏幕平行），不是包围盒那层，也不是斜的缝。

    外表面若两侧缺块（1×1×n 这类退化情形）→ 返回 None，不硬选。
    """
    family = AXIS_TO_FAMILY[face['axis']]
    idx = AXIS_TO_LOC_INDEX[face['axis']]
    v = int(face['loc'][idx])
    candidates = (v, v - 1) if face['sign'] > 0 else (v - 1, v)
    for line in candidates:
        if _is_internal_cut(family, line, locations) and is_valid_gap(family, line):
            return (family, line)
    return None


def seam_of_internal_face(face, is_valid_gap, locations=None):
    """「块与块之间的那块墙」→ (缝族, 缝线号)；不是内壁就返回 None。

    2026-11-17 用户口径：拆分渲染之后，缝里的那两面墙本来就画出来了（gap>0
    时不再剔除内部面），它们就是**看得见的缝**——直接拿它们当判定基准，比
    「按面边猜一条线」直观得多。外表面（贴棋盘边界、背后没有块）一律不算，
    否则会把包围盒的平面也当成缝（引擎其实允许「最外一层整体滑出去」，那是
    包围盒的平面，不该被点出来）。

    面在坐标 ``v``，法向 ``sign``：sign>0 时这块在缝的**低**侧，墙立在 v+1 上
    → 缝线号 v；sign<0 时在高侧，墙立在 v 上 → 缝线号 v-1。
    """
    if locations is not None and not face_is_internal(face, locations):
        return None
    family = AXIS_TO_FAMILY[face['axis']]
    idx = AXIS_TO_LOC_INDEX[face['axis']]
    v = int(face['loc'][idx])
    line = v if face['sign'] > 0 else v - 1
    if not is_valid_gap(family, line):
        return None
    return (family, line)


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
