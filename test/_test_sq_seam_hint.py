# -*- coding: utf-8 -*-
"""无头验证：方形/三角点「画得出、点得到、选不动」的外沿缝要给提示。

对标米字格的 _mi_click_query（错位态锁死缝 → 「这条缝选不动（…）：…」）：
方形最外沿那圈缝只有一侧有滑块，点了既选不中也不该一声不响。
本文件守四件事：
  1. 点外沿缝 → 给「这条缝选不动（棋盘外沿，外侧没有滑块）」提示，
     且不改变选中态（selected_gap 仍为空、不误当第二下触控）；
  2. 点里面正常的缝 → 照旧选中，且不弹「选不动」；
  3. 点滑块 → 照旧选中滑块，不弹「选不动」；
  4. 缺块/异形外沿同样给提示（外沿判定走引擎 is_valid_*，不是写死矩形）。

执行：python test/_test_sq_seam_hint.py
"""
import os
import queue
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

HINT = '这条缝选不动（棋盘外沿，外侧没有滑块）：请选里面的缝'

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def boot(cells, m=4, n=4):
    gui = SliderGUI(m=m, n=n, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.game_mode = 'practice'
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    gui.new_puzzle(m, n, 2)
    gui._update_in_progress = False
    gui.game.apply_pattern(cells, {})
    gui.center_map()
    return gui


def click(gui, sx, sy):
    gui.macro_notify_msg = None
    gui.macro_notify_timer = 0
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(int(sx), int(sy))))
    gui.handle_events()
    return gui.macro_notify_msg


def scan(gui, pred, step=2):
    """扫出一个满足 pred(屏幕点) 的点。"""
    for y in range(0, gui.screen.get_height(), step):
        for x in range(0, gui.screen.get_width(), step):
            if pred((x, y)):
                return (x, y)
    return None


FULL = {(r, c) for r in range(4) for c in range(4)}


# ---- 1. 外沿缝：点了要有提示，且选中态不变 --------------------------------
gui = boot(FULL)
bounds = gui.game.get_boundaries()
rim_line = bounds['min_row'] - 1          # 最上沿那条（get_gap_at_pos 会否掉）


def on_rim(p):
    x, y = p
    return (gui.get_gap_at_pos(x, y) is None
            and gui.get_block_at_pos(x, y) is None
            and gui._rejected_seam_at(x, y) is not None)


rim_pt = scan(gui, on_rim)
check('1a 能扫到外沿缝的屏幕点', rim_pt is not None, f'{rim_pt}')
gui.selected_gap = None
gui.selected_block = None
msg = click(gui, *rim_pt)
check('1b 外沿缝给出「选不动」提示', msg == HINT, repr(msg))
check('1c 外沿缝没有被当成选中', gui.selected_gap is None,
      f'{gui.selected_gap}')
check('1d 外沿缝没有凭空选中滑块',
      not any(b.be_opted for b in gui.game.blocks))

# 选中一条真缝后再点外沿：不应把真缝吃掉，也不应误当第二下触控提交
gui.selected_gap = ('h', 1)
msg = click(gui, *rim_pt)
check('1e 已选真缝时点外沿：真缝仍在', gui.selected_gap == ('h', 1),
      f'{gui.selected_gap}')
check('1f 已选真缝时点外沿：仍给提示', msg == HINT, repr(msg))

# ---- 2. 里面的正常缝：照旧选中、不弹「选不动」 -----------------------------
gui = boot(FULL)


def on_inner(p):
    g = gui.get_gap_at_pos(*p)
    return g is not None and g[1] not in (bounds['min_row'] - 1, bounds['max_row'])


inner_pt = scan(gui, on_inner)
check('2a 能扫到内部缝的屏幕点', inner_pt is not None, f'{inner_pt}')
msg = click(gui, *inner_pt)
check('2b 内部缝照旧选中', gui.selected_gap is not None, f'{gui.selected_gap}')
check('2c 内部缝不弹「选不动」', (msg or '').find('选不动') < 0, repr(msg))

# ---- 3. 点滑块：照旧选块、不弹「选不动」 -----------------------------------
gui = boot(FULL)


def on_block(p):
    return gui.get_block_at_pos(*p) is not None and gui.get_gap_at_pos(*p) is None


blk_pt = scan(gui, on_block, step=4)
check('3a 能扫到滑块中心的屏幕点', blk_pt is not None, f'{blk_pt}')
msg = click(gui, *blk_pt)
check('3b 点滑块不弹「选不动」', (msg or '').find('选不动') < 0, repr(msg))

# ---- 4. 缺块形状（L 形）的外沿同样给提示 -----------------------------------
L_CELLS = {(r, c) for r in range(3) for c in range(3)}
gui = boot(L_CELLS, m=3, n=3)


def on_any_rim(p):
    return (gui.get_gap_at_pos(*p) is None
            and gui.get_block_at_pos(*p) is None
            and gui._rejected_seam_at(*p) is not None)


rim_pt2 = scan(gui, on_any_rim)
check('4a L 形下能扫到外沿缝', rim_pt2 is not None, f'{rim_pt2}')
msg = click(gui, *rim_pt2)
check('4b L 形外沿缝给出提示', msg == HINT, repr(msg))

# ---- 5. 选块填空模式不插嘴 -------------------------------------------------
gui = boot(FULL)
_orig_pick = gui._pick_fill_click
gui._pick_fill = {'await': 'block'}
gui._pick_fill_click = lambda x, y, b, g: None   # 只看提示，不真跑选填
msg = click(gui, *rim_pt)
check('5a 选块填空模式下不弹外沿缝提示',
      (msg or '').find('选不动') < 0, repr(msg))
gui._pick_fill = None
gui._pick_fill_click = _orig_pick

# ---- 6. 离棋盘更远的空白（拖地图起手）不念人 -------------------------------
gui = boot(FULL)
bounds = gui.game.get_boundaries()
unit = gui.board_view.cell_size + gui.board_view.gap_width
far_wx = (bounds['min_col'] + 0.5) * unit          # 第一列中線
far_wy = bounds['min_row'] * unit - 30             # 上沿往外 30px
fx, fy = gui.world_to_screen(far_wx, far_wy)
check('6a 远处空白点确实不在任何缝上',
      gui._rejected_seam_at(int(fx), int(fy)) is None)
msg = click(gui, int(fx), int(fy))
check('6b 远处空白不弹「选不动」（留白给拖地图）',
      (msg or '').find('选不动') < 0, repr(msg))

# ---- 汇总 ----------------------------------------------------------------
print()
if _failures:
    print(f'FAILED {len(_failures)}: ' + '; '.join(_failures))
    sys.exit(1)
print('ALL PASS')
