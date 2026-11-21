# -*- coding: utf-8 -*-
"""光照原语：面内微倒角 + 色彩偏移（§六十二 / §六十五 / §六十六）。

纯 pygame、零依赖（不 import renderer / group_render），供
`gui/renderer.py`（二维三形态 + 三维面片 + 方形/聚合板）与
`gui/group_render.py`（捆绑组）共用同一亮度方向与幅度——前端三形态
铁律 §3「一處 helper、三形態各接一次」的公共落点。

屏幕左上光 (-0.55, -0.75)：面内每条边压一条窄带，亮度按边法向投影
决定——上/左提亮、下/右压暗，方向与 `engine/cubic_view.py::face_shade`
的相机相对主光一致。

draw_group_pieces / draw_group_chunks（纯 pygame 零依赖模块）要给捆绑组
压同一套倒角，但不能反向依赖 renderer——调用方把本模块的
`_draw_face_bevel` 以 `bevel=` 可调用参数传入，那边只管按签名调用。
"""

import pygame

#: 倒角带设计厚度（屏幕像素，调用方按 zoom 缩放后传 inset_px）。
#: §65 修正（2026-11-21 用户：「捆绑块和普通滑块厚度不一样」）：原 inset
#: 是**比例制**（0.15=向质心收 15%），带厚 = 0.15×(边中到质心距离)——
#: 普通 60px 块带≈4.5px、2×2 捆绑 126px 块≈9.5px、1×5 长条端头≈22px，
#: 同一盘三种厚度。5.0 取自原比例制在 60px 普通块上的厚度（4.5）取整，
#: 普通块观感不变、大块带收薄到与它一致。小块（算出的 inset 超 0.45 会
#: 令带越过质心自交）按 0.45 夹紧，退化为随块缩小——画不下就缩，不翻转。
BEVEL_INSET_PX = 5.0


def _shade255(color, offset):
    """给 RGB 加固定偏移并夹回 0..255（整型三元组）。"""
    return (max(0, min(255, int(color[0]) + offset)),
            max(0, min(255, int(color[1]) + offset)),
            max(0, min(255, int(color[2]) + offset)))


def _draw_face_bevel(surface, pts, fill, strength=30.0, inset=0.15,
                     corner_inset=0.0, edge_inset_px=0.0, edges=None,
                     inset_px=None):
    """面内多边微倒角：沿面的每条屏幕边压一条窄带，亮度按
    「屏幕左上光」(-0.55, -0.75) 的边法向投影决定——上/左提亮、下/右压暗，
    方向与 `engine/cubic_view.py::face_shade` 的相机相对主光一致。

    这是三维面片倒角画法（renderer 三维绘制段，2026-11-19 实体感三件套
    之二）抽出来的**公共唯一来源**：三维渲染、二维方形/三角/米字三形态、
    捆绑组共用同一函数，保证开态下各处的亮度方向与幅度完全一致。

    pts    : 面的屏幕坐标顶点序列（>=3，任意多边形；三角/米字的块面
             不是四边形，所以是 n 边而不是硬编码 4 边）
    fill   : 面底色 RGB——带色 = 底色 + 偏移，不引入新色相
    strength: 偏移幅度（三维原值 30）
    inset  : 带宽**比例**（从边向质心收 inset 比例，三维原值 0.15）——
             仅在 inset_px=None 时生效。比例制带厚随块尺寸变，三维面片
             尺寸统一无此问题；二维一律传 inset_px（见下）。
    corner_inset: 端点沿边向内收的像素数——矩形有圆角（_block_corner），
             端点落在角点会把圆角外的角隅补成直角；圆角形态传半径让带
             不触及角部，圆角由随后的 border 层照画。
    edge_inset_px: 整条边沿法向朝质心推入的像素数（§六十六 蓝色溢出修复）
             ——倒角带从**边框内沿**开始、不碰边界线，灰色边框独占边界，
             提亮色不渗到框外。调用方按当前 border_w 传 border_w/2；
             默认 0 保持旧调用（无边框/三维旧口径）零变化。
    edges   : 只压这些下标的边（集合/列表），None=全部（§六十五 捆绑组
             只沿**组外轮廓**压带，组内共用边跳过——否则组内重现分隔线，
             违背「一整块刚体」观感）。
    inset_px: 带厚**固定像素**（§65 修正：厚度不随块尺寸变，捆绑块与
             普通块同厚）。用**角平分线内缩**（每顶点沿两邻边内法向的
             角平分线收 t/sin(θ/2)，法向厚度精确 = t、端头交匯在正确的
             内缩角）——不能用「端点向质心收比例」：长条的质心离端点远，
             收边的水平分量被放大（306×60 长条端头被斜切进 25.5px，用户
             11-21 截图「最上面的长条画的不好」）。调用方传
             `BEVEL_INSET_PX * zoom`（AA 路径再 ×S）；None=用比例 inset
             （向质心收，三维旧口径零变化——立方体面片是正多边形，两法
             结果一致）。
    """
    n = len(pts)
    if n < 3:
        return
    edge_set = None if edges is None else set(edges)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    lx, ly = -0.55, -0.75
    llen = (lx * lx + ly * ly) ** 0.5
    # inset_px 模式：预计算每边**精确内法向**（垂直于边、朝质心）与
    # 每个顶点的角平分线内缩点——带内沿 = 相邻两边内缩线的交点。
    q_pts = None
    if inset_px:
        nrm = []
        for e in range(n):
            a0, b0 = pts[e], pts[(e + 1) % n]
            dx, dy = b0[0] - a0[0], b0[1] - a0[1]
            dl = (dx * dx + dy * dy) ** 0.5
            if dl <= 1e-9:
                nrm.append(None)
                continue
            ux, uy = dy / dl, -dx / dl        # 垂直于边的单位向量
            mmx, mmy = (a0[0] + b0[0]) / 2.0, (a0[1] + b0[1]) / 2.0
            if ux * (cx - mmx) + uy * (cy - mmy) < 0:
                ux, uy = -ux, -uy             # 翻到朝质心一侧 = 内法向
            nrm.append((ux, uy))
        q_pts = []
        for i in range(n):
            n1 = nrm[(i - 1) % n]             # 前边（共享顶点 pts[i] 的尾）
            n2 = nrm[i]                       # 后边（共享顶点 pts[i] 的头）
            if n1 is None or n2 is None:
                q_pts.append(pts[i])
                continue
            bx, by = n1[0] + n2[0], n1[1] + n2[1]
            bl = (bx * bx + by * by) ** 0.5
            if bl <= 1e-9:
                # 两法向反向（180° 退化角）：无角平分线，直接按后边法向推
                q_pts.append((pts[i][0] + n2[0] * inset_px,
                              pts[i][1] + n2[1] * inset_px))
                continue
            dot = max(-1.0, min(1.0, n1[0] * n2[0] + n1[1] * n2[1]))
            # θ = 两内法向夹角 = 180° − 内角 α；顶点到内缩交点的距离
            # = t/sin(α/2) = t/cos(θ/2)，cos(θ/2)=sqrt((1+cosθ)/2)。
            # （曾误写成 sqrt((1−dot)/2)=sin(θ/2)=cos(α/2)：矩形 α=90°
            #  时 sin=cos 巧合相等，三角 60°/120° 角就算错——三角开态
            #  背景侧 1px 越界即此。）
            sin_half = ((1.0 + dot) / 2.0) ** 0.5
            if sin_half < 1e-6:
                sin_half = 1e-6
            scale = inset_px / sin_half
            q_pts.append((pts[i][0] + bx / bl * scale,
                          pts[i][1] + by / bl * scale))
    for e in range(n):
        if edge_set is not None and e not in edge_set:
            continue
        a = pts[e]
        b = pts[(e + 1) % n]
        if corner_inset:
            # 沿边把两端各向内收 corner_inset 像素（限在边长内）
            ex, ey = b[0] - a[0], b[1] - a[1]
            elen = (ex * ex + ey * ey) ** 0.5
            if elen > 2.0 * corner_inset:
                t = corner_inset / elen
                a = (a[0] + ex * t, a[1] + ey * t)
                b = (b[0] - ex * t, b[1] - ey * t)
        mx = (a[0] + b[0]) / 2.0
        my = (a[1] + b[1]) / 2.0
        nx, ny = mx - cx, my - cy
        nlen = (nx * nx + ny * ny) ** 0.5
        if nlen <= 1e-9:
            continue
        if edge_inset_px:
            # 沿边法向（外法向 nx,ny 的反向 = 朝质心）把整条边推入
            # edge_inset_px 像素——带的外沿（a,b 边）落在边界线内侧，
            # 灰框独占边界（§六十六：提亮蓝不渗出灰框）。
            a = (a[0] - nx / nlen * edge_inset_px,
                 a[1] - ny / nlen * edge_inset_px)
            b = (b[0] - nx / nlen * edge_inset_px,
                 b[1] - ny / nlen * edge_inset_px)
        dot = (nx * lx + ny * ly) / (nlen * llen)
        off = int(strength * dot)
        if q_pts is not None:
            # 固定厚度：内沿用预计算的角平分线内缩点（原顶点，不随
            # corner_inset/edge_inset 的外沿推入移动——带内沿是几何内缩角）
            q1 = q_pts[e]
            q2 = q_pts[(e + 1) % n]
        else:
            # 比例制（三维旧口径零变化）：端点向质心收 inset 比例
            q1 = (a[0] + (cx - a[0]) * inset, a[1] + (cy - a[1]) * inset)
            q2 = (b[0] + (cx - b[0]) * inset, b[1] + (cy - b[1]) * inset)
        pygame.draw.polygon(surface, _shade255(fill, off), (a, b, q2, q1))
