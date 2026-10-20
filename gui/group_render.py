# -*- coding: utf-8 -*-
"""捆绑组的统一渲染原语（自由捆绑 / 设计模式，docs/spec/bandaged_mode.md）。

把「同组滑块」画成一整块实心矩形，但**不引入任何新颜色**——复用游戏
现有的块填充色（普通块色 / 选中色），只做两件事：
  1. 同组相邻格填同一种现有色并桥接内部缝隙 → 内部网格线消失，读成一块；
  2. 只在组外边界描一条加粗轮廓（沿用现有 border 色系，仅加深/加粗）。

这样既不破坏画风（没有橙/蓝/绿等新色），又能一眼看出「这几块是胶粘的
刚性整体」。纯 pygame、零依赖、可离屏 Surface 单测。

注：三角 / 米字形态当前没有 group 字段，调用方已自行跳过。
"""

import pygame


def _darker(rgb, f=0.6):
    return tuple(int(max(0, min(255, ch * f))) for ch in rgb)


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
