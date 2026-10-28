# -*- coding: utf-8 -*-
r"""悬停缝隙高亮（2026-10-27 加）：三形态 + 模型板型都要「点前就看得见」。

用户 2026-10-26 提：「添加悬停在缝隙上的缝隙高亮，用处是在点击之前就知道
这里是否可以点。」要害是**高亮的判据必须和点击一致**——点亮了一条点下去却
选不中的缝，比不亮更糟（承诺了又做不到）。所以本脚本逐形态验三件事：

  1. 判据：``_hover_gap_at`` 与点击用的 ``get_gap_at_pos`` 同结果（通用通道
     连「±28 宽兜底」也一起比）；
  2. 几何：那条缝能算出线段（``_hover_seam_segments``；三形态各用各的
     view，通用通道走 ``_poly_seam_segments``）；
  3. 不重复：已经选中的那条不再悬停高亮（红线盖着，白线是噪音）。

外加一条：接了高亮之后 ``draw_board`` 不炸（绘制路径真的被调用到）。

跑法：D:/python/python.exe test/_test_hover_gap.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print('    FAIL:', msg)
    return bool(cond)


def scan_gap(gui, step=7, budget=40000):
    """扫屏幕找一条「点得动」的缝与其屏幕点（带预算，别扫到天荒地老）。"""
    n = 0
    for y in range(80, gui.screen_height - 40, step):
        for x in range(40, gui.screen_width - 40, step):
            n += 1
            if n > budget:
                return None, None
            g = gui.get_gap_at_pos(x, y)
            if g is not None:
                return g, (x, y)
    return None, None


def probe(gui, tag, step=7, budget=40000):
    gui.selected_gap = None
    gui._hover_key = None
    gap, pos = scan_gap(gui, step=step, budget=budget)
    if not check(gap is not None, f'{tag}：屏幕上应能扫到一条有效缝'):
        return
    hover = gui._hover_gap_at(*pos)
    check(hover == gap, f'{tag}：悬停判据应与点击一致（{hover} vs {gap}）')
    # 让缓存命中（dummy 下 pygame.mouse.get_pos() 恒 (0,0)，直接喂进去）
    gui.hover_gap = gap
    gui._hover_key = (tuple(pygame.mouse.get_pos()), gui.step_count,
                      gui.selected_gap)
    segs = gui._hover_seam_segments()
    check(bool(segs), f'{tag}：悬停缝应算出线段（{segs[:1]}）')
    gui.selected_gap = gap
    gui._hover_key = None
    check(gui._hover_seam_segments() == [],
          f'{tag}：已选中的那条不再悬停高亮')
    gui.selected_gap = None
    gui._hover_key = None
    try:
        gui.draw_board()
        ok = True
    except Exception:                       # noqa: BLE001
        import traceback
        traceback.print_exc()
        ok = False
    check(ok, f'{tag}：draw_board 应不炸')


def main():
    gui = SliderGUI(m=5, n=5, step=1)
    gui.animation_enabled = False
    gui.ui_mode = 'enhanced'

    gui.new_puzzle(5, 5, 1)
    probe(gui, '方形')

    gui.new_triangle_puzzle(3, 1)
    if hasattr(gui, '_fit_triangle_zoom'):
        gui.zoom = gui._fit_triangle_zoom()
    if hasattr(gui, '_center_triangle'):
        gui._center_triangle()
    probe(gui, '三角')

    gui.new_mi_puzzle(3, 3, 1)
    if hasattr(gui, '_fit_mi_zoom'):
        gui.zoom = gui._fit_mi_zoom()
    if hasattr(gui, '_center_mi'):
        gui._center_mi()
    probe(gui, '米字')

    from engine import model_registry
    model_registry.install()
    if 'shield' in model_registry.loaded():
        if gui.new_model_puzzle('shield', 1):
            if hasattr(gui, 'center_map'):
                gui.center_map()
            probe(gui, '模型 shield', step=20, budget=1200)
        else:
            check(False, '模型 shield 应能开局')
    else:
        print('    （跳过模型板型：shield 未注册）')

    print()
    if FAILS:
        print(f'共 {len(FAILS)} 项失败：')
        for f in FAILS:
            print('  ·', f)
        sys.exit(1)
    print('悬停缝隙高亮：三形态 + 模型板型全部通过')


if __name__ == '__main__':
    main()
