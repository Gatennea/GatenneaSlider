# -*- coding: utf-8 -*-
"""三维命中：屏幕点 → 可见面 → 切面缝 / 块（§54 第 3 步）。

投影是**正交**（`cubic_view.project_point` 就是 origin + scale·(x, −y)），所以
「射线求交」退化成正交射线：屏幕点直接命中画家算法排好序的面多边形，**按画家
序倒着测**（最近的先测）就等价于按深度取最近的那一面——不必再解一次射线方程，
也不会和渲染结果对不上（渲染画哪一面，这里就认哪一面）。

本模块纯计算，不 import pygame（与 engine 其余模块同一条纪律）。
"""

from engine.cubic_view import layout_anchor

#: cubic_view 的 axis（0=X, 1=Y, 2=Z）→ 逻辑坐标下标 (r, c, d) 与缝族名。
#: 世界映射是 X=c / Y=d / Z=r（见 cubic_view 模块头）。
AXIS_TO_LOC_INDEX = {0: 1, 1: 2, 2: 0}
AXIS_TO_FAMILY = {0: 'c', 1: 'd', 2: 'r'}
#: 缝族 → 逻辑坐标下标（预览平面与判定共用）
FAMILY_TO_LOC_INDEX = {'r': 0, 'c': 1, 'd': 2}
FAMILY_TO_WORLD_AXIS = {'r': 2, 'c': 0, 'd': 1}


def seam_plane_coord(line, gap: float = 0.0, anchor=None) -> float:
    """逻辑缝线 line → 世界平面坐标。

    拆分是「块大小不变、中心距拉到 1+gap」，整堆以 anchor 为中心对称散开：
    第 line 与 line+1 块之间的空隙中心在
    ``(line + 1) * (1 + gap) - anchor * gap``；gap=0 时仍是 ``line + 1``。
    anchor 默认 0.5（第一格中心），与 `block_min_corner` 的默认一致。
    """
    a = 0.5 if anchor is None else float(anchor)
    return float(line + 1) * (1.0 + float(gap)) - a * float(gap)


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
    """点中一块的某个面 → 它所属的内部切面；外表面返回 None。

    2026-11-19 用户口径：三維滑塊**不能選中表面上的切面**。舊版這裡會在
    「面外側那條線」不是內部切面時，退回塊的另一條邊界；結果對着最外層的
    表面右鍵，會悄悄選中表面之下一層的切面——玩家點的是 A，選中的是 B。
    現在只接受真正的內部面（兩側都有塊的牆），不再退回另一條邊界。

    內部面的線號：面在座標 v，法向 sign>0 時這塊在縫的低側，牆立在 v+1 上
    → 縫線 v；sign<0 時在高側，牆立在 v 上 → 縫線 v-1。
    """
    if locations is None or not face_is_internal(face, locations):
        return None
    family = AXIS_TO_FAMILY[face['axis']]
    idx = AXIS_TO_LOC_INDEX[face['axis']]
    v = int(face['loc'][idx])
    line = v if face['sign'] > 0 else v - 1
    if not is_valid_gap(family, line):
        return None
    return (family, line)


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
    if locations is None or not face_is_internal(face, locations):
        return None
    family = AXIS_TO_FAMILY[face['axis']]
    idx = AXIS_TO_LOC_INDEX[face['axis']]
    v = int(face['loc'][idx])
    line = v if face['sign'] > 0 else v - 1
    if not is_valid_gap(family, line):
        return None
    return (family, line)


def seam_plane_polygon(family, line, blocks, pad: float = 0.0, gap: float = 0.0):
    """切面预览的四角（世界坐标）。

    切面是「两块之间的空隙中心」那张平面（拆分后以块堆包围盒中心对称散开），
    另外两轴按当前块的实际外表面取。``gap`` 必须与渲染用的拆分一致：块大小恒
    为 1，只有中心距变成 1+gap，切面要正好压在块堆外轮廓上，不能把空隙算成
    额外外扩。``pad`` 默认 0。
    """
    locs = [(int(b.location[0]), int(b.location[1]), int(b.location[2]))
            if hasattr(b, 'location') else tuple(int(v) for v in b)
            for b in blocks]
    if not locs:
        return None
    axis = FAMILY_TO_WORLD_AXIS[family]
    # 逻辑坐标 (r, c, d) → 世界坐标 (X, Y, Z) = (c, d, r)：cubic_view 的映射
    world = [(p[1], p[2], p[0]) for p in locs]
    anchor = layout_anchor(locs)
    pitch = 1.0 + float(gap)
    half = float(gap) / 2.0
    lo = [min(p[i] for p in world) * pitch + half - anchor[i] * gap
          for i in range(3)]
    hi = [(max(p[i] for p in world) + 1) * pitch - half - anchor[i] * gap
          for i in range(3)]
    fixed = seam_plane_coord(line, gap, anchor[axis])
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


def seam_plane_cells(family, line, blocks, gap: float = 0.0):
    """切面按**格**切成的四边形列表（世界坐标），用来插进画家序里画。

    为什么要按格切，而不是整张面 + 影子多边形：整张面是一块大凸多边形，它的
    「面心深度」只有一个值，压在块堆里时前后关系只能整体判一次——从斜角看，同
    一张面上有的部分该被前面的块挡住、有的部分该露出来，一个深度值做不到，于是
    「看起来像切在另一层」（2026-11-18 用户反复报）。切成 1 格大小之后，每一格
    与每个块的前后关系都是明确的（块边长 1 格），各自按深度插进同一张绘制序，
    遮挡关系由画家算法自然给出，误差只可能落在格与格的交界上。

    只取「缝口有块」的格：切面两侧都没块的格根本不存在可看的东西，画出来就是
    凭空悬在空中的红面。每格就是该块的横截面（边长恒为 1），拆分拉大后格与
    格之间的空隙本身不铺红面。

    返回 [(四个世界点, 该格中心的世界坐标)]。
    """
    locs = [(int(b.location[0]), int(b.location[1]), int(b.location[2]))
            if hasattr(b, 'location') else tuple(int(v) for v in b)
            for b in blocks]
    if not locs:
        return []
    axis = FAMILY_TO_WORLD_AXIS[family]
    anchor = layout_anchor(locs)
    fixed = seam_plane_coord(line, gap, anchor[axis])
    # 逻辑 (r,c,d) → 世界 (X,Y,Z) = (c,d,r)，与 cubic_view 同一映射
    world = [(p[1], p[2], p[0]) for p in locs]
    lo = [min(p[i] for p in world) for i in range(3)]
    hi = [max(p[i] for p in world) + 1 for i in range(3)]
    a, b = [i for i in range(3) if i != axis]
    n_a = int(round(hi[a] - lo[a]))
    n_b = int(round(hi[b] - lo[b]))
    if n_a <= 0 or n_b <= 0:
        return []
    pitch = 1.0 + float(gap)
    half = float(gap) / 2.0
    # 缝口有块 = 这一格在切面轴上紧挨着块（line 或 line+1 那一层）
    side = set()
    for p in world:
        coord = p[axis]
        if int(round(coord)) in (int(line), int(line) + 1):
            side.add((p[a], p[b]))
    cells = []
    for i in range(n_a):
        for j in range(n_b):
            key_logical = (lo[a] + i, lo[b] + j)
            if key_logical not in side:
                continue
            # 每格就是该块在切面上的横截面：块大小恒为 1，格间空隙不连成面。
            u0 = (lo[a] + i) * pitch + half - anchor[a] * gap
            v0 = (lo[b] + j) * pitch + half - anchor[b] * gap
            u1 = u0 + 1.0
            v1 = v0 + 1.0
            corners = []
            for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
                point = [0.0, 0.0, 0.0]
                point[axis] = fixed
                point[a] = u
                point[b] = v
                corners.append(tuple(point))
            center = [0.0, 0.0, 0.0]
            center[axis] = fixed
            center[a] = (u0 + u1) / 2.0
            center[b] = (v0 + v1) / 2.0
            cells.append((corners, tuple(center)))
    return cells


def seam_plane_rect(family, line, blocks, gap: float = 0.0, dims=None):
    """切面**整块矩形**（世界坐标四角，按平面内两轴顺序排）。

    与 seam_plane_cells 同一套几何口径，但**不按格拆**，也不按「缝口有没有块」
    筛选。为什么：2026-11-18 用户要的是「一张矩形平面」，按格拼出来一是盘面被
    打散后会在没有相邻块的地方缺格子（看起来一块块浮着），二是格与格的边界在
    半透明叠加下会加深成网格线。

    遮挡改由渲染层解决：切面是一张平面，每个块整块都在它的一侧，所以
    「先画背面块 → 画整张面 → 再画相机侧块」就得到与真实前后一致的结果。

    范围口径（用户 2026-11-18 再次纠正）：**按当前块堆的包围盒**取，不按棋盘
    原始尺寸。盘面被推散后块会跑到原始棋盘之外，包围盒可能比 m×n×d 大也可能
    小，切面必须跟着真实的块堆走。`dims` 只在**一块都没有**时兜底用。
    """
    locs = [(int(b.location[0]), int(b.location[1]), int(b.location[2]))
            if hasattr(b, 'location') else tuple(int(v) for v in b)
            for b in blocks]
    if locs:
        # 逻辑 (r,c,d) → 世界 (X,Y,Z) = (c,d,r)，与 cubic_view 同一映射
        world = [(p[1], p[2], p[0]) for p in locs]
        lo = [min(p[i] for p in world) for i in range(3)]
        hi = [max(p[i] for p in world) + 1 for i in range(3)]
    elif dims and len(dims) == 3 and all(int(v) >= 1 for v in dims):
        m, n, dd = (int(v) for v in dims)
        lo = [0.0, 0.0, 0.0]
        hi = [float(n), float(dd), float(m)]
    else:
        return []
    axis = FAMILY_TO_WORLD_AXIS[family]
    a, b = [i for i in range(3) if i != axis]
    if hi[a] <= lo[a] or hi[b] <= lo[b]:
        return []
    pitch = 1.0 + float(gap)
    half = float(gap) / 2.0
    anchor = tuple((lo[i] + hi[i]) / 2.0 for i in range(3))
    fixed = seam_plane_coord(line, gap, anchor[axis])
    # 切面要**和块堆外轮廓一样大**：块大小恒为 1，中心距是 1+gap，整堆以
    # 包围盒中心对称散开，所以两端各是「第一块外表面」到「最后一块外表面」。
    u0 = lo[a] * pitch + half - anchor[a] * gap
    u1 = hi[a] * pitch - half - anchor[a] * gap
    v0 = lo[b] * pitch + half - anchor[b] * gap
    v1 = hi[b] * pitch - half - anchor[b] * gap
    corners = []
    for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
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
