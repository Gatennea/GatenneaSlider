# -*- coding: utf-8 -*-
"""搭积木编辑器的几何纯逻辑（零 pygame，可单测；GUI 只做绘制与事件）。

晶格（v1 固定）——标准三角晶格：整数坐标 (i,j) 经基
    basis = [[1, 0], [0.5, √3/2]]   （e1=(1,0)、e2=(0.5,√3/2)）
映到平面。选它是因为 **60° 旋转是该基下的整系数线性自同构**：
    R60(i,j) = (-j, i+j)，  镜像 M(i,j) = (i+j, -j)
——库形状的全部朝向 therefore 都是整数顶点，加载器/校验器/存档的
「整数坐标判身份」口径原样成立（碎三角那套 (kx,my) 基的旋转封闭性
要靠挑子格，这里天然封闭）。

三类纯函数：
1. **朝向图生成**：库形状 → D6 的 12 个像（去重、规范化、稳定排序）。
   单位等边三角形的对称群是 D3，12 个像去重后只剩 ▲/▼ 两个——
   与三角谜题的实际朝向数一致，可用来验证生成器。
2. **贴边吸附**：点击 → 候选 (p, 朝向)。候选 = 让新块的某条边**整条**
   贴上已有块的某条边（两端点分别相等）；相切不算碰撞，但正面积
   重叠的候选要滤掉（几何公理 A0 的用户侧前置）。
3. **缝族推导**：块边方向 → primitive 方向族 → 最小合法步长。
   只有**平行于块边**的方向才可能有活缝（缝线必须沿真实块边，
   见 model_loader.seam_lines 的判据）；步长由引擎验（k=1..max_k
   逐个造单族 spec 问 legal_moves，取第一个有合法移动的 k）——
   「步长作者写、引擎验」的自动化版，玩家不写任何数字。
"""
from math import atan2, degrees, gcd, sqrt

from . import geometry_ops as gops
from .board import Block, Board
from .model_loader import SCHEMA_BOARD, load_model

# 标准三角晶格基（与 docs/spec/模型文件_2026-10-24.md 的示例一致）
TRI_BASIS = ((1.0, 0.0), (0.5, sqrt(3.0) / 2.0))

# 缝族名 ↔ 落屏方向（step 的平面角 mod 180 取最近 30° 倍数）
_DIR_NAMES = {0: 'h', 30: 'd30', 60: 'd60', 90: 'v', 120: 'd120', 150: 'd150'}


# ----------------------------------------------------------------------
# 坐标与对称
# ----------------------------------------------------------------------
def to_plane(v):
    """整数格坐标 → 平面坐标。"""
    i, j = v
    return (i * TRI_BASIS[0][0] + j * TRI_BASIS[1][0],
            i * TRI_BASIS[0][1] + j * TRI_BASIS[1][1])


def to_lattice(xy):
    """平面坐标 → 实数格坐标（to_plane 的逆；不取整）。

    自由放置时用：点一下空白处，先求真实格坐标，再取最近整数点。
    基 TRI_BASIS = [[1,0],[0.5,√3/2]] 的逆是
        j = y / (√3/2),   i = x - j/2
    """
    x, y = xy
    j = y / TRI_BASIS[1][1]
    i = x - 0.5 * j
    return (i, j)


def rot60(v):
    """平面 60° 旋转（该基下是整系数线性自同构）。"""
    i, j = v
    return (-j, i + j)


def mirror(v):
    """平面 x 轴反射。"""
    i, j = v
    return (i + j, -j)


def _canon_cycle(verts):
    """顶点循环的规范形：全部旋转（含反向）里取字典序最小。

    必须保**邻接顺序**——吸附匹配靠「新块某条边 vs 已有块某条边」，
    按字典序排序顶点会把边结构打碎（排序后的相邻点不一定是真边）。
    反向也参与取最小 = 绕向归一（同一组顶点+同一邻接 = 同一块贴纸，
    绕向只是表示artifact；手性形状的镜像顶点集不同，不会被并扰）。
    """
    n = len(verts)
    best = None
    for seq in (verts, tuple(reversed(verts))):
        for s in range(n):
            cyc = tuple(seq[(s + i) % n] for i in range(n))
            if best is None or cyc < best:
                best = cyc
    return best


def _norm(verts):
    """规范化：平移使**包围盒最小角**落在 (0,0)，再取循环规范形。

    锚点取包围盒角而不是顶点——这是与引擎三角 preset 对齐的关键：
    preset 的 ▼ 锚在自身多边形外的包围盒角（off = {(1,0),(1,1),(0,1)}），
    ▲ 锚在左下顶点。取bbox角后，编辑器摆出的 ▲▼ 盘与 preset 的
    (点, 朝向) 逐项同形，缝族 rank（= coeffs·点）也就同形，
    自动推导出的族与 preset 的 h/p/n 三族一致。
    """
    vs = [tuple(v) for v in verts]
    bx = min(v[0] for v in vs)
    by = min(v[1] for v in vs)
    return _canon_cycle([(x - bx, y - by) for x, y in vs])


def normalize(verts):
    """``_norm`` 的公开版（编辑器 Mixin 查「旋转/镜像后是哪個像」要用）。"""
    return _norm(verts)


def d6_images(verts):
    """形状顶点 → D6 全部像（去重、规范化、稳定排序）。

    顺序确定：6 个旋转各先自身后镜像（k=0..5）。对称形状自动去重
    （单位等边三角形 → 2 个像：▲/▼）。
    """
    out = []
    seen = set()
    cur = tuple(tuple(v) for v in verts)
    for _ in range(6):
        for m in (False, True):
            img = _norm(tuple(mirror(v) if m else v for v in cur))
            if img not in seen:
                seen.add(img)
                out.append(img)
        cur = tuple(rot60(v) for v in cur)
    return tuple(out)


def _primitive(d):
    """边向量 → primitive 方向（除 gcd、规范符号：首个非零分量为正）。"""
    g = gcd(abs(d[0]), abs(d[1])) or 1
    dx, dy = d[0] // g, d[1] // g
    if dx < 0 or (dx == 0 and dy < 0):
        dx, dy = -dx, -dy
    return (dx, dy)


def _normal_of(d):
    """与 d 垂直的整数向量（缝族 coeffs：rank = coeffs·v，缝线 ⊥ coeffs）。"""
    n = (d[1], -d[0])
    return _primitive(n)


def direction_name(step):
    """步长向量 → 缝族名（按落屏方向；step 与 -step 同族，角取 mod 180）。"""
    x, y = to_plane(step)
    ang = degrees(atan2(y, x)) % 180.0
    best = min(_DIR_NAMES, key=lambda a: min(abs(ang - a), abs(ang - a + 180),
                                             abs(ang - a - 180)))
    return _DIR_NAMES[best]


# ----------------------------------------------------------------------
# 点与多边形
# ----------------------------------------------------------------------
def point_in_poly(p, poly, eps=1e-9):
    """射线法；边上也算在内（吸附容差）。"""
    x, y = p
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if _dist_point_seg(p, (x1, y1), (x2, y2)) <= eps:
            return True
    inside = False
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xin > x:
                inside = not inside
    return inside


def _dist_point_seg(p, a, b):
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 1e-18:
        return sqrt((px - ax) ** 2 + (py - ay) ** 2)
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return sqrt((px - cx) ** 2 + (py - cy) ** 2)


def dist_point_poly(p, poly):
    """点到多边形距离（内部为 0）。"""
    if point_in_poly(p, poly):
        return 0.0
    n = len(poly)
    return min(_dist_point_seg(p, poly[i], poly[(i + 1) % n])
               for i in range(n))


def poly_of(point, offs):
    """(位置, 顶点偏移) → 平面多边形。"""
    return tuple(to_plane((point[0] + ox, point[1] + oy)) for ox, oy in offs)


# ----------------------------------------------------------------------
# 贴边吸附
# ----------------------------------------------------------------------
def snap_candidates(images, placed, click_xy, *, max_dist=None):
    """贴边吸附候选。

    参数
    ----
    images : 选中形状的全部朝向图（``d6_images`` 输出）
    placed : ``{(p, o): offs}`` 已放置块（offs = 该块整数顶点）
    click_xy : 点击的平面坐标
    max_dist : 候选与点击的最大距离（平面单位；None = 不限）

    返回
    ----
    ``[(p, img_idx, poly, dist)]`` 按 dist 升序、去重。
    候选生成：新块的某条边两端点**恰好等于**已有块某条边两端点
    （整条边贴上，不是只碰一个角）；首次放置（placed 空）时每朝向
    给 p=(0,0)。与已有块正面积重叠的候选滤掉（共边相切保留）。
    """
    cands = {}
    if placed:
        placed_polys = {k: poly_of(k[0], offs) for k, offs in placed.items()}
        edges = []
        # ⚠️ 边表必须是**物理整数顶点**（point + offs），不能拿局部 offs：
        # 局部边表等于假设所有块都锚在原点——贴到非原点块时会凭空造出/
        # 漏掉候选（探针 v4 抓到：菱形条带第 4 块贴 ▲(1,0) 时全错）。
        for k, offs in placed.items():
            pt = k[0]
            n = len(offs)
            for i in range(n):
                edges.append((
                    (pt[0] + offs[i][0], pt[1] + offs[i][1]),
                    (pt[0] + offs[(i + 1) % n][0],
                     pt[1] + offs[(i + 1) % n][1])))
        for idx, img in enumerate(images):
            n = len(img)
            for i in range(n):
                a, b = img[i], img[(i + 1) % n]
                for c, d in edges:
                    # 新块边 (a,b) 贴上已有边 (c,d)：a→c、b→d（或反向）。
                    # p 由第一对应点求出，再验证第二对应点——**不能**要求
                    # a==c（那只会放行 p=(0,0) 的候选，把贴到别处边上的
                    # 候选全杀光）。
                    for (ea, eb, ec, ed) in ((a, b, c, d), (b, a, c, d)):
                        p = (ec[0] - ea[0], ec[1] - ea[1])
                        if (p[0] + eb[0], p[1] + eb[1]) != ed:
                            continue
                        poly = poly_of(p, img)
                        if any(gops.convex_overlap(poly, pp)
                               for pp in placed_polys.values()):
                            continue
                        cands[(p, idx)] = poly
    else:
        for idx, img in enumerate(images):
            cands[((0, 0), idx)] = poly_of((0, 0), img)
    out = []
    for (p, idx), poly in cands.items():
        dist = dist_point_poly(click_xy, poly)
        if max_dist is not None and dist > max_dist:
            continue
        out.append((p, idx, poly, dist))
    out.sort(key=lambda t: (t[3], t[0], t[1]))
    return out


def block_at(placed, click_xy):
    """点击命中哪个已放置块（最上面的小索引块优先；返回 key 或 None）。"""
    hits = []
    for k, offs in placed.items():
        if point_in_poly(click_xy, poly_of(k[0], offs)):
            hits.append(k)
    if not hits:
        return None
    return sorted(hits)[0]


def can_place(images, idx, p, placed):
    """(朝向, 位置) 放上去是否与已有块无重叠。"""
    poly = poly_of(p, images[idx])
    for k, offs in placed.items():
        if gops.convex_overlap(poly, poly_of(k[0], offs)):
            return False
    return True


def shared_edge_segments(placed):
    """相邻块对的共享边**线段**：``[(key_a, key_b, (平面端点, 平面端点)), ...]``。

    判据与 ``gops.components`` 同源（共边 = 两块共享一条完整的边），
    复用它而不是自己写一遍「找公共顶点」——两处判据不一致会出现
    「渲染上说相邻、引擎上说不连通」的怪事。

    边表必须用**物理整数顶点**（见 ``snap_candidates`` 的同类注释）。
    """
    vmap = {}
    for k, offs in placed.items():
        pt = k[0]
        vmap[k] = tuple((pt[0] + ox, pt[1] + oy) for ox, oy in offs)
    out = []
    seen = set()
    for (a, b), owners in gops.shared_edge_owners(vmap).items():
        seg = (to_plane(a), to_plane(b))
        for i in range(len(owners)):
            for j in range(i + 1, len(owners)):
                ka, kb = owners[i], owners[j]
                pair = (ka, kb) if ka <= kb else (kb, ka)
                if pair in seen:
                    continue
                seen.add(pair)
                out.append((pair[0], pair[1], seg))
    out.sort(key=lambda t: (t[2][0][0], t[2][0][1], str(t[0]), str(t[1])))
    return out


def shared_edges(placed):
    """相邻块对的共享边：``[(key_a, key_b, 边中点平面坐标), ...]``。

    编辑器「点缝捆绑/解绑」的命中源（与设计态同一交互）；要线段本身
    （画组内缝）用 ``shared_edge_segments``。
    """
    return [(ka, kb, ((s[0][0] + s[1][0]) / 2.0, (s[0][1] + s[1][1]) / 2.0))
            for ka, kb, s in shared_edge_segments(placed)]


# ----------------------------------------------------------------------
# 缝族推导
# ----------------------------------------------------------------------
def edge_directions(placed):
    """全部已放置块的边方向（primitive、去重）。"""
    dirs = set()
    for offs in placed.values():
        n = len(offs)
        for i in range(n):
            d = (offs[(i + 1) % n][0] - offs[i][0],
                 offs[(i + 1) % n][1] - offs[i][1])
            if d != (0, 0):
                dirs.add(_primitive(d))
    return sorted(dirs)


def _trial_family_live(blocks, orientations, coeffs, step):
    """造「只有这一族」的 spec，问引擎有没有合法移动（有 → 活）。

    一律挂 ``rank: 'centroid'``（质心分侧）：锚点 rank 对 bbox 角不是
    顶点的朝向（如 ▼）会错判缝侧，详见 model_loader._centroid_rank。
    """
    doc = {
        'schema': SCHEMA_BOARD,
        'name': '_editor_trial',
        'basis': [list(r) for r in TRI_BASIS],
        'pos_scale': 1,
        'orientations': {lb: {'shape': 'x', 'off': [list(v) for v in offs]}
                         for lb, offs in orientations.items()},
        'tiles': [{'p': list(b.point), 'o': b.orient,
                   'g': int(getattr(b, 'group', 0) or 0)} for b in blocks],
        'seams': [{'name': 't', 'coeffs': list(coeffs), 'step': list(step),
                   'rank': 'centroid'}],
    }
    try:
        model = load_model(doc)
    except Exception:
        return 0
    board = Board(model.spec, model.spec.goal_blocks)
    return len(board.legal_moves(1))


def derive_families(blocks, orientations):
    """从当前摆放推导缝族。

    参数
    ----
    blocks : ``[Block(p, o, g), ...]`` 当前摆放（还原态）
    orientations : ``{标签: 整数顶点}`` 朝向表

    返回
    ----
    ``[(name, coeffs, step, n_moves)]``：按族名排序。没有任何合法移动的
    方向直接丢掉（活不起来的族写了也是装饰）。

    ⚠️ 步长恒取 primitive（k=1），**不试 k>1 的「传送」整步**：本编辑器
    的晶格是单位三角晶格（贴边吸附保证块间距即 1），GUI 一次点击 = 一个
    parallel 向量 × 步数档，且 ``slide`` 对每一步都做碰撞 + 连通校验——
    传送语义会跳过中间态检查（碎三角模型的 (6,0) 粗步之所以成立，是因为
    它的**位置晶格本身就是粗的**，中间位置不存在；单位晶格没有这个奢侈）。
    单调性：若「parallel=d、step=k」合法，则中途第 1 落点已通过碰撞 +
    连通校验，「parallel=d、step=1」必然合法——k 循环永远断在 k=1，
    写了也是死代码，故直接只试 k=1。
    """
    if not blocks:
        return []
    placed = {(b.point, b.orient): _offs_of(orientations, b.orient)
              for b in blocks}
    fams = []
    for d in edge_directions(placed):
        coeffs = _normal_of(d)
        n = _trial_family_live(blocks, orientations, coeffs, d)
        if n:
            fams.append((direction_name(d), coeffs, d, n))
    fams.sort(key=lambda t: t[0])
    return fams


def _offs_of(orientations, label):
    return tuple(tuple(v) for v in orientations[label])


def legal_move_count(blocks, orientations, families):
    """按给定缝族集合数合法移动（ families = [(name, coeffs, step), ...] ）。

    与 derive_families 同口径：一律挂 centroid rank。
    """
    if not blocks or not families:
        return 0
    doc = {
        'schema': SCHEMA_BOARD,
        'name': '_editor_count',
        'basis': [list(r) for r in TRI_BASIS],
        'pos_scale': 1,
        'orientations': {lb: {'shape': 'x', 'off': [list(v) for v in offs]}
                         for lb, offs in orientations.items()},
        'tiles': [{'p': list(b.point), 'o': b.orient,
                   'g': int(getattr(b, 'group', 0) or 0)} for b in blocks],
        'seams': [{'name': nm, 'coeffs': list(cf), 'step': list(st),
                   'rank': 'centroid'}
                  for nm, cf, st in families],
    }
    model = load_model(doc)
    board = Board(model.spec, model.spec.goal_blocks)
    return len(board.legal_moves(1))


def move_stats(blocks, orientations, families):
    """(合法移动数, 可动块数)（families 同 legal_move_count，4 元组也收）。

    为什么要可动块数：保存门要求「≥2 颗滑块动得了」。只数移动条数不够——
    一条移动可能只搬动一颗滑块（存出来是个一步就没的残局），而玩家想存的是
    「真能玩起来」的盘。

    ⚠️ 必须像本函数这样**按给定族另造一个 spec** 来数：编辑器的预览 spec
    收的是形状库全部方向的族（渲染用，会话期恒定），拿它数移动会让「关掉
    某条缝族」的开关完全失效（Mixin 2026-10-25 实测踩到）。
    """
    if not blocks or not families:
        return 0, 0
    fams = [(f[0], f[1], f[2]) for f in families]
    doc = {
        'schema': SCHEMA_BOARD,
        'name': '_editor_stats',
        'basis': [list(r) for r in TRI_BASIS],
        'pos_scale': 1,
        'orientations': {lb: {'shape': 'x', 'off': [list(v) for v in offs]}
                         for lb, offs in orientations.items()},
        'tiles': [{'p': list(b.point), 'o': b.orient,
                   'g': int(getattr(b, 'group', 0) or 0)} for b in blocks],
        'seams': [{'name': nm, 'coeffs': list(cf), 'step': list(st),
                   'rank': 'centroid'}
                  for nm, cf, st in fams],
    }
    model = load_model(doc)
    board = Board(model.spec, model.spec.goal_blocks)
    moves = board.legal_moves(1)
    movable = set()
    for mv in moves:
        movable |= set(mv.moved)
    return len(moves), len(movable)


def is_connected(blocks, orientations):
    """整盘是否单一连通（共边连通；A0 的用户侧实时版）。

    ⚠️ 必须用**物理整数顶点**（point + offs），不能拿锚点相对的 offs：
    两块锚点不同而 offs 相同的话，共边判定会把它们当成同一块的两个副本
    ——不连通的盘被判成连通（2026-10-25 测试抓到：相距 (0,0)/(3,9) 的
    两块 is_connected 恒 True，保存门的连通检查整个失效）。这与
    ``snap_candidates`` 边表那次是同一类错误，见那里的注释。
    """
    if not blocks:
        return False
    placed = {}
    for b in blocks:
        offs = _offs_of(orientations, b.orient)
        placed[(b.point, b.orient)] = tuple(
            (b.point[0] + ox, b.point[1] + oy) for ox, oy in offs)
    return gops.is_connected(frozenset(placed), lambda k: placed[k])
