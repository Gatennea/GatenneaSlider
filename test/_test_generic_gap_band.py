# -*- coding: utf-8 -*-
"""回归：模型板型缝隙命中与「假缝」提示（碎三角 shatter）。

两个用户报的症状，同一个根因家族：
  A. 点细缝线时偏出 ~12px（落进相邻块），get_gap_at_pos 默认 ±10 世界单位
     带就漏掉 → 选不上。修复：没选中缝时把「活缝兜底带」放大到 ±28。
  B. 走位后，通用通道把每块多边形整圈描灰线当缝，但可选中缝只认「两块共享
     的完整边」；外沿边与走位造成的 T 接切口也画成同样的线，点它们时
     gap=None、块命中，事件层当普通点块而静默 → 「选不中又不提示」。
     修复：点在这种非可选边线上时收掉块命中并明确提示。

脚本风格（conftest 管理子进程执行），无头跑。
"""
import os
import sys
import queue

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

# 与 gui/move.py 中 _sq_click_query 兜底、GUI.get_gap_at_pos 一致
WIDE_TOL = 28.0
NARROW_TOL = 10.0


_failed = 0


def check(cond, msg):
    global _failed
    if cond:
        print(f"  ok: {msg}")
        return True
    print(f"  FAIL: {msg}")
    _failed += 1
    return False


def do_one_move(g):
    """走一步合法移动（与 GUI / 撤销测试同契约）。"""
    for gap_type, line in g.all_gaps():
        for d in g._gap_directions(gap_type):
            g.opt(gap_type, line, g.blocks[0])
            if not any(b.be_opted for b in g.blocks):
                continue
            final = g.try_move(d, 1)
            if final:
                g.commit_move(final)
                return True
    return False


def find_offset_point(gui):
    """找一个偏置点 P：落进相邻块（块命中非 None），但窄带(±10)漏掉该活缝、
    放大带(±28)能选中它——正是「点偏进块、选不上」的情形。"""
    g = gui.game
    spec = g.spec
    view = gui._polygon_view()
    origin = gui._poly_view_origin(view)
    for fam in spec.seam_families:
        for line in range(-90, 91):
            if not (g.is_valid_gap(fam.name, line)
                    and g.is_live_gap(fam.name, line)):
                continue
            segs = view.seam_segments(g.board, fam.name, line, origin)
            for (ax, ay), (bx, by) in segs:
                dx, dy = (bx - ax), (by - ay)
                ln = (dx * dx + dy * dy) ** 0.5
                if ln < 1e-6:
                    continue
                nx, ny = -dy / ln, dx / ln  # 单位法线
                mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
                for d in range(11, 23):
                    for s in (1, -1):
                        px, py = mx + s * d * nx, my + s * d * ny
                        psx, psy = gui.world_to_screen(px, py)
                        ixs, iys = int(round(psx)), int(round(psy))
                        if (gui.get_gap_at_pos(ixs, iys,
                                               tolerance=NARROW_TOL) is None
                                and gui.get_block_at_pos(ixs, iys) is not None
                                and gui.get_gap_at_pos(ixs, iys,
                                                       tolerance=WIDE_TOL)
                                is not None):
                            return (fam.name, line, (px, py))
    return None


def find_phantom_edge(gui):
    """找一条「画得出、却不是可选缝」的块边线，返回块内一个贴近它的点。

    判定：块多边形的某条边，其中点沿「朝质心」方向内移 2~6 世界单位后，
    块命中非 None 且 ±28 内查不到任何活缝——说明这条边不是两块共享的完整
    缝（外沿 / T 接切口）。返回 (block_location, px, py) 或 None。
    """
    g = gui.game
    view = gui._polygon_view()
    origin = gui._poly_view_origin(view)
    seen = set()
    for b in g.blocks:
        loc = tuple(b.location)
        pt = loc[:2]
        oo = loc[2] if len(loc) > 2 else ''
        poly = view.world_polygon(pt, oo, origin)
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        n = len(poly)
        for i in range(n):
            ax, ay = poly[i]
            bx, by = poly[(i + 1) % n]
            key = tuple(sorted([(round(ax, 1), round(ay, 1)),
                                (round(bx, 1), round(by, 1))]))
            if key in seen:
                continue
            seen.add(key)
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            vx, vy = cx - mx, cy - my
            ln = (vx * vx + vy * vy) ** 0.5
            if ln < 1e-6:
                continue
            for d in (2.0, 3.0, 4.0, 5.0, 6.0):
                px, py = mx + vx / ln * d, my + vy / ln * d
                psx, psy = gui.world_to_screen(px, py)
                ixs, iys = int(round(psx)), int(round(psy))
                if (gui.get_gap_at_pos(ixs, iys, tolerance=WIDE_TOL) is None
                        and gui.get_block_at_pos(ixs, iys) is not None):
                    return (list(b.location), px, py)
    return None


def main():
    global _failed
    _failed = 0
    gui = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 5053})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.animation_enabled = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    ok = gui.new_model_puzzle('shatter', 1)
    check(ok, "new_model_puzzle('shatter',1) 成功建局")
    # new_model_puzzle 内部已 center_map()，相机已就位

    # ① 缝中点本身用窄带即能选中（回归非退化：正常点缝仍工作）
    P0 = find_offset_point(gui)
    check(P0 is not None, "找到偏置点（块命中、窄带漏缝、宽带选中）")
    fam_name, line, P = P0
    view = gui._polygon_view()
    origin = gui._poly_view_origin(view)
    segs = view.seam_segments(gui.game.board, fam_name, line, origin)
    (ax, ay), (bx, by) = segs[0]
    smx, smy = gui.world_to_screen((ax + bx) / 2.0, (ay + by) / 2.0)
    g0, _b0 = gui._sq_click_query(int(round(smx)), int(round(smy)))
    check(g0 is not None, f"缝中点点击仍选中缝 {fam_name}")

    psx, psy = gui.world_to_screen(*P)

    # ② 修复前提：该偏置点用窄带(±10)确实选不到缝
    narrow = gui.get_gap_at_pos(int(round(psx)), int(round(psy)),
                                tolerance=NARROW_TOL)
    check(narrow is None, "该偏置点用窄带(±10)确实选不到缝（bug 前提成立）")

    # ③ 放大带(±28)应能在同一点选中缝
    wide = gui.get_gap_at_pos(int(round(psx)), int(round(psy)),
                              tolerance=WIDE_TOL)
    check(wide is not None, f"放大带(±28)在同一点能选中缝 {wide}")

    # ④ 关键：_sq_click_query（selected_gap=None 时）应优先当点缝
    gui.selected_gap = None
    gq, bq = gui._sq_click_query(int(round(psx)), int(round(psy)))
    check(gq is not None,
          f"_sq_click_query（未选中态）优先选缝而非静默落空 -> {gq}")
    check(bq is None,
          "_sq_click_query 选缝后块命中作废（与现有否决缝处理一致）")

    # ⑤ 已选中缝后第二步：点偏进块不应被误判成取消选中
    gui.selected_gap = (fam_name, line)
    gq2, bq2 = gui._sq_click_query(int(round(psx)), int(round(psy)))
    check(gq2 is None and bq2 is not None,
          "已选中缝后、点偏进块：不被误判成取消选中（仍当点块选哪侧滑）")

    # ⑥ 假缝（画得出、却不是可选缝）：走一步后出现，点它必须给提示
    moved = do_one_move(gui.game)
    check(moved, "碎三角能走一步（走位后才会出现假缝）")
    PH = find_phantom_edge(gui)
    check(PH is not None, "找到一条「画得出却不是缝」的边线")
    if PH is not None:
        _loc, px, py = PH
        gui.selected_gap = None
        gui.macro_notify_msg = ''
        phsx, phsy = gui.world_to_screen(px, py)
        pg, pb = gui._sq_click_query(int(round(phsx)), int(round(phsy)))
        check(pg is None, "假缝不会被误选成缝")
        check(bool(gui.macro_notify_msg),
              f"点假缝有提示（实际：{gui.macro_notify_msg!r}）")

    print(f"\n结果：{'全部通过' if _failed == 0 else str(_failed) + ' 项失败'}")
    sys.exit(1 if _failed else 0)


if __name__ == '__main__':
    main()
