# -*- coding: utf-8 -*-
"""捆绑组的统一渲染原语（自由捆绑 / 设计模式，docs/spec/bandaged_mode.md）。

把「同组滑块」画成一整块实心矩形，但**不引入任何新颜色**——复用游戏
现有的块填充色（普通块色 / 选中色），只做两件事：
  1. 同组相邻格填同一种现有色并桥接内部缝隙 → 内部网格线消失，读成一块；
  2. 只在组外边界描一条加粗轮廓（沿用现有 border 色系，仅加深/加粗）。

这样既不破坏画风（没有橙/蓝/绿等新色），又能一眼看出「这几块是胶粘的
刚性整体」。纯 pygame、零依赖、可离屏 Surface 单测。

对外 API
-------
::

    piece_edge_flags(poly, nb_polys) -> list[bool]
    interior_angle(poly, idx) -> float
    shared_edge_index(poly_a, poly_b) -> int | None
    bridge_quad(edge_a, edge_b) -> [(x, y)] * 4
    draw_group_pieces(screen, pieces, bridges, to_screen,
                      fill, fill_sel, outline_color, outline_width)
    draw_group_chunks(screen, groups, get_rect, gap_px, fill, fill_sel,
                      outline_color, outline_width, is_selected=None)

v4 起三角 / 米字的 Block 也有 group 字段（见 bandage.py），异形走
`draw_group_pieces`（多边形逐块填色 + 组内填缝），方形仍走 `draw_group_chunks`
（矩形拼块），两者观感一致。
"""

import math

import pygame


def _round_pt(p, nd=3):
    """点坐标舍入到 nd 位小数（浮点比较收敛；三角/米字顶点含 cos30 等无理数）。"""
    return (round(p[0], nd), round(p[1], nd))


def _darker(rgb, f=0.6):
    return tuple(int(max(0, min(255, ch * f))) for ch in rgb)


def piece_edge_flags(poly, nb_polys) -> list:
    """poly 各边是否与「某个同组邻块」共用（逐邻块判，任一邻块共用即真）。

    注意：不能把所有邻块的顶点并成一个集合再判——并集会让夹角处两条边
    同时命中「两个邻块的点」，三角/A 形里整块边会被全判成内部边。
    """
    n = len(poly)
    flags = [False] * n
    pa = [_round_pt(p) for p in poly]
    for nb in nb_polys:
        bset = {_round_pt(p) for p in nb}
        for idx in range(n):
            if flags[idx]:
                continue
            if pa[idx] in bset and pa[(idx + 1) % n] in bset:
                flags[idx] = True
    return flags


def interior_angle(poly, idx) -> float:
    """多边形在第 idx 个顶点处的内角（弧度，0~π）。

    用于判断「该顶点是否被同组块完整围住」：把各块在该点的内角相加，
    和 ≈ 2π 才是组**内部**的点（补色圆点只该画在这里），否则这个点落在
    组的外边界上，画圆就会像截图那样在轮廓外鼓出一个小凸包。
    """
    n = len(poly)
    v = poly[idx]
    a = poly[(idx - 1) % n]
    b = poly[(idx + 1) % n]
    ax, ay = a[0] - v[0], a[1] - v[1]
    bx, by = b[0] - v[0], b[1] - v[1]
    na = math.hypot(ax, ay)
    nb = math.hypot(bx, by)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    cosv = max(-1.0, min(1.0, (ax * bx + ay * by) / (na * nb)))
    return math.acos(cosv)


def shared_edge_index(poly_a, poly_b):
    """两多边形共用边的下标（在 poly_a 的边序列里）；不共边回 None。"""
    pa = [_round_pt(p) for p in poly_a]
    pb = {_round_pt(p) for p in poly_b}
    n = len(pa)
    for idx in range(n):
        if pa[idx] in pb and pa[(idx + 1) % n] in pb:
            return idx
    return None


def bridge_quad(edge_a, edge_b):
    """两条「对边」（各两个端点）→ 填缝四边形（按最近端点配成不自交的四边）。"""
    a1, a2 = edge_a
    b1, b2 = edge_b
    d = lambda p, q: (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2   # noqa: E731
    if d(a2, b1) + d(a1, b2) <= d(a2, b2) + d(a1, b1):
        return [a1, a2, b1, b2]
    return [a1, a2, b2, b1]


def draw_group_pieces(screen, pieces, bridges, to_screen, fill, fill_sel,
                      outline_color, outline_width, dots=()):
    """多边形形态的捆绑组：整组填色 + 内部缝隙填平 + 只描组外边界。

    与方形 `draw_group_chunks` 同一套观感（复用现有块色/边框色，不引入新色）：
      1. 每块按**普通块形状**（已内缩 gap/2）填同一种色 → 组外留出正常间隙，
         与普通块并排时视觉一致；
      2. 组内共用边铺一块**同色四边形**——它正好是两侧内缩边之间的空隙，
         天然落在组内、不會像粗线段那样在 60° 外角戳出组外；
      3. 只对「非共用边」重描边框 → 外轮廓就是普通块的边框，不会出现双线。

    参数
    ----
    pieces        : [(poly_inset, internal_flags, selected), ...]
                    poly_inset 是普通块形状（视图 inset=True）；
                    internal_flags[i] 为真表示第 i 条边与同组邻块共用
    bridges       : [(quad_world, selected), ...] 组内共用边的填缝四边形
                    （端点取两侧**内缩**多边形的对应边，逐条由调用方配好）
    to_screen     : (wx, wy) -> (sx, sy)
    dots          : [(vertex_world, radius_world, selected), ...] 补点表。
                    组内 **≥3 块共用**的顶点，各块内缩后会在该点周围漏出一个
                    ≈gap 的小洞（米字同格四块的中心就是典型），由调用方按
                    「顶点 → 到内缩顶点的最大距离」算好半径，这里补一个同色
                    圆盖住。方形那套 draw_group_chunks 的「四格交点小方块」同理。
    """
    # 第一遍：填平内部缝隙 + 各块填色
    for quad, sel in bridges:
        pygame.draw.polygon(screen, fill_sel if sel else fill,
                            [to_screen(*p) for p in quad])
    for poly, internal, selected in pieces:
        pygame.draw.polygon(
            screen, fill_sel if selected else fill,
            [to_screen(*p) for p in poly])
    # 1.5 遍：多块共用顶点的小洞（半径按世界单位给，用 to_screen 现算像素）
    for v, r, sel in dots:
        sx, sy = to_screen(*v)
        ex, ey = to_screen(v[0] + r, v[1])
        rad = int(round(((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5))
        if rad >= 1:
            pygame.draw.circle(screen, fill_sel if sel else fill,
                               (int(round(sx)), int(round(sy))), rad)
    # 第二遍：只描组外边界（第二遍画，避免被相邻组员的填充盖掉）
    for poly, internal, selected in pieces:
        n = len(poly)
        for idx in range(n):
            if internal[idx]:
                continue
            pygame.draw.line(screen, outline_color, to_screen(*poly[idx]),
                             to_screen(*poly[(idx + 1) % n]), outline_width)


def draw_group_chunks(screen, groups, get_rect, gap_px, fill, fill_sel,
                      outline_color, outline_width, is_selected=None):
    """把同组格画成一整块实心矩形（无内部网格线 + 单一外轮廓）。

    参数
    ----
    screen        : pygame 绘制目标面（主屏或离屏 Surface 均可）
    groups        : {gid: [(r,c), ...]}（格坐标；屏幕位置由 get_rect 决定）
    get_rect      : (r,c) -> (x, y, size)；返回该格屏幕像素（左上 + 边长）
    gap_px        : 相邻格之间的缝隙像素宽（用于内部桥接，使缝隙处无缝）
    fill          : 未选中块使用的现有填充色（如 colors['block']）
    fill_sel      : 选中块使用的现有填充色（如 colors['block_selected']）
    outline_color : 外轮廓色（现有 border 色系，仅加粗/加深，不引入新色）
    outline_width : 外轮廓线宽
    is_selected   : (r,c) -> bool；该格是否处于选中态（决定用 fill 还是
                    fill_sel）。构造画布无选中概念时传 None。
    """
    if is_selected is None:
        is_selected = lambda r, c: False

    # 第一遍：填色（每格整块填充 + 内部相邻缝隙桥接）
    # 整块填充覆盖每格自带边框 → 同组格之间不再有网格线，读成一块。
    for gid, cells in groups.items():
        pos = set(cells)
        for (r, c) in cells:
            x, y, sz = get_rect(r, c)
            f = fill_sel if is_selected(r, c) else fill
            pygame.draw.rect(screen, f, (x, y, sz, sz))
            # 桥接右侧 / 下方内部缝隙（同一组相邻 → 无缝）
            if (r, c + 1) in pos:
                pygame.draw.rect(screen, f, (x + sz, y, gap_px, sz))
            if (r + 1, c) in pos:
                pygame.draw.rect(screen, f, (x, y + sz, sz, gap_px))
            # 四格交点的小方块（2x2 组中心 / L 形内角）：横竖桥接都盖不到，
            # 右+下同时在组时补上，否则中心漏出一个背景色小点
            if (r, c + 1) in pos and (r + 1, c) in pos:
                pygame.draw.rect(screen, f, (x + sz, y + sz, gap_px, gap_px))

    # 第二遍：外轮廓（只描组外边界，内部相邻边不描，读作一整块）
    ow = outline_width
    for gid, cells in groups.items():
        pos = set(cells)
        for (r, c) in cells:
            x, y, sz = get_rect(r, c)
            if (r, c + 1) not in pos:
                pygame.draw.line(screen, outline_color, (x + sz, y), (x + sz, y + sz), ow)
            if (r, c - 1) not in pos:
                pygame.draw.line(screen, outline_color, (x, y), (x, y + sz), ow)
            if (r + 1, c) not in pos:
                pygame.draw.line(screen, outline_color, (x, y + sz), (x + sz, y + sz), ow)
            if (r - 1, c) not in pos:
                pygame.draw.line(screen, outline_color, (x, y), (x + sz, y), ow)
