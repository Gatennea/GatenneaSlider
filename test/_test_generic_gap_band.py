# -*- coding: utf-8 -*-
"""回归：模型板型「点偏进相邻块、但附近有活缝」应优先选缝（放大判定带）。

复现 bug2：shield 等通用通道板型，点细缝线时只要偏出 ~12px（落进相邻块），
get_gap_at_pos 默认 ±10 世界单位带就漏掉，且块命中使「选不动」提示永不触发
→ 选不上也没反馈。修复：没选中缝时把判定带放大到 ±22，优先当点缝处理。

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

# 与 gui/move.py 中 _sq_click_query 兜底、GUI.get_gap_at_pos 默认一致
WIDE_TOL = 22.0
NARROW_TOL = 10.0
# cell_size=60、半格 30；放大带必须小于半格，否则会跨格误选对侧缝


_failed = 0


def check(cond, msg):
    global _failed
    if cond:
        print(f"  ok: {msg}")
        return True
    print(f"  FAIL: {msg}")
    _failed += 1
    return False


def find_offset_point(gui):
    """找一个偏置点 P：落进相邻块（块命中非 None），但窄带(±10)漏掉该活缝、
    放大带(±22)能选中它——正是用户「点偏进块、选不上」的情形。

    遍历每条活缝的每条缝段、两个法向、多个偏移距离，返回 (fam, line, P) 或 None。
    """
    g = gui.game
    spec = g.spec
    view = gui._polygon_view()
    origin = gui._poly_view_origin(view)
    for fam in spec.seam_families:
        for line in range(-40, 41):
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
    ok = gui.new_model_puzzle('shield', 1)
    check(ok, "new_model_puzzle('shield',1) 成功建局")
    # new_model_puzzle 内部已 center_map()，相机已就位

    # ① 缝中点本身用窄带即能选中（回归非退化：正常点缝仍工作）
    P0 = find_offset_point(gui)
    check(P0 is not None, "找到偏置点（块命中、窄带漏缝、宽带选中）")
    fam_name, line, P = P0
    # 用该缝中点确认正常选缝仍生效
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

    # ③ 放大带(±22)应能在同一点选中缝
    wide = gui.get_gap_at_pos(int(round(psx)), int(round(psy)),
                              tolerance=WIDE_TOL)
    check(wide is not None, f"放大带(±22)在同一点能选中缝 {wide}")

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

    print(f"\n结果：{'全部通过' if _failed == 0 else str(_failed) + ' 项失败'}")
    sys.exit(1 if _failed else 0)


if __name__ == '__main__':
    main()
