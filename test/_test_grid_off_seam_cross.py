# -*- coding: utf-8 -*-
"""关网格后缝十字交叉角补全护栏（2026-11-17，§四十四.2）。

用户 2026-11-17 报：「关闭绘制网格之后矩形谜题的缝隙绘制有问题，表现为
交叉处有空白」。根因：关网格分支只画「两个格子都有滑块」的缝段，段长恰为
一格宽（只到块边为止），横竖缝的十字交叉角（gap×gap 的小方块）没有任何
一段缝矩形盖到 → 露背景。开网格态整条缝带铺满，所以两态对比下交叉处
明显缺一块。

修复：相接缝段在两端各延伸一个缝宽。延伸段落在行/列缝区（相邻块之间），
不侵入任何块；开网格态同一位置本来就有整条缝带，画风与开态对齐。

判据（无头离屏，像素级）：
  A. 满块盘关网格：内部 16 个十字交叉角全部为缝色（修复前全为背景）；
  B. 挖洞后洞心仍为背景色（「空位无线」语义不回归）；
  C. 相接缝中段仍为缝色（原有语义不变）；
  D. 开网格交叉角为缝色（两态画风一致的对照口径）。

执行：D:/python/python.exe test/_test_grid_off_seam_cross.py
"""
import os
import queue
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame                                             # noqa: E402
from GUI import SliderGUI                                 # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, extra))
    if not cond:
        _failures.append(name)


def px(gui, x, y):
    x, y = int(round(x)), int(round(y))
    return tuple(gui.screen.get_at((x, y))[:3])


def main():
    gui = SliderGUI(m=5, n=5, step=1, cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.game_mode = 'practice'
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    gui.animation_enabled = False
    gui.new_puzzle(5, 5, 1)
    for attr in ('_update_in_progress',):
        setattr(gui, attr, False)

    gap_col = tuple(gui.colors['gap'][:3])
    bg_col = tuple(gui.colors['background'][:3])
    cell, gap, step = gui._board_px()
    cam_x = int(round(gui.camera_x))
    cam_y = int(round(gui.camera_y))

    # ---- A. 满盘：关网格，内部交叉角必须 gap 色 ----
    gui.draw_grid = False
    gui.draw_board()
    bad = []
    # 内部交叉角 (r,c)：行缝 r 与列缝 c 的交会小方块中心
    # （band 起点 = j*step-gap，见 renderer.draw_board 缝带循环）
    for r in range(4):
        for c in range(4):
            x = (c + 1) * step - gap + gap // 2 + cam_x
            y = (r + 1) * step - gap + gap // 2 + cam_y
            p = px(gui, x, y)
            if p != gap_col:
                bad.append(((r, c), p))
    check('A 关网格：满盘内部 16 个十字交叉角全为缝色', not bad,
          str(bad[:4]))

    # ---- B. 挖洞：洞心必须仍是背景（空位无线语义不回归）----
    gui.game.blocks = [b for b in gui.game.blocks
                       if tuple(b.location) != (2, 2)]
    gui.draw_board()
    hx = 2 * step + cell // 2 + cam_x
    hy = 2 * step + cell // 2 + cam_y
    check('B 关网格：洞心仍为背景色', px(gui, hx, hy) == bg_col,
          str(px(gui, hx, hy)))

    # ---- C. 相接缝中段仍为 gap 色（缝号0 = 块列0|1 之间，行2高度：
    #        该处块 (2,0)(2,1) 都在，修复前后都必须有线）----
    sx = 1 * step - gap + gap // 2 + cam_x
    sy = 2 * step + cell // 2 + cam_y
    check('C 关网格：相接缝中段仍为缝色', px(gui, sx, sy) == gap_col,
          str(px(gui, sx, sy)))

    # ---- D. 开网格对照：交叉角同为 gap 色（两态画风一致）----
    gui.draw_grid = True
    gui.draw_board()
    x = 2 * step - gap + gap // 2 + cam_x
    y = 2 * step - gap + gap // 2 + cam_y
    check('D 开网格：交叉角为缝色（对照口径）', px(gui, x, y) == gap_col,
          str(px(gui, x, y)))

    print('==== %s（%d 项失败）'
          % ('全部通过' if not _failures else '有失败', len(_failures)))
    return 1 if _failures else 0


if __name__ == '__main__':
    sys.exit(main())
