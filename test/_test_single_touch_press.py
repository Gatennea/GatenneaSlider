# -*- coding: utf-8 -*-
"""护栏：方形单次触控「按在块上」必须先能起拖，不能被宽兜底选缝劫持。

背景：2026-11-07 给方形第一击接了 ±28 活缝宽兜底。cell 60 + gap 4 时，
格子内到最近缝中心的最大距离只有 32，"<32" 几乎覆盖整块，按下滑块会被
判成选缝、block 清空，单次触控的 _mouse_drag_state 根本记不下来。

本测试钉住事件层的“按下挂起、拖动丢弃、松手补选”三段：
  A. 按下：宽兜底 gap 仍返回，但 block 保留；selected_gap 暂不设置，
      _pending_gap_click 记下候选缝，_mouse_drag_state 有块。
  B. 拖动超过阈值：pending 清空，不再回头选缝（即使跟随初始化失败）。
  C. 没拖就松手：才补提交选缝，行为与旧点击一致。
  D. 右键取消：pending 一并作废。
  E. _sq_click_query 默认仍清 block，preserve_block=True 才保留。

执行：python test/_test_single_touch_press.py
"""
import os
import queue
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

_failed = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failed.append(name)
    return bool(cond)


def boot():
    g = SliderGUI(m=5, n=5, step=1, cmd_queue=queue.Queue(),
                  ext_state={'enabled': False, 'token': None})
    g.game_mode = 'practice'
    g.tutorial_active = False
    g.tut_show_prompt = False
    g.save_readonly_flag = False
    g.new_puzzle(5, 5, 1)
    g.game.apply_pattern({(r, c) for r in range(5) for c in range(5)}, {})
    g._update_in_progress = False
    g.center_map()
    pygame.event.clear()
    return g


def find_press_point(g):
    """找“按在块上、宽兜底命中活缝、窄带不命中”的点。"""
    w, h = g.screen.get_size()
    for y in range(h // 2 - 160, h // 2 + 160, 2):
        for x in range(w // 2 - 200, w // 2 + 200, 2):
            block = g.get_block_at_pos(x, y)
            if block is None:
                continue
            wide = g.get_gap_at_pos(x, y, tolerance=28.0)
            if wide is None or g.get_gap_at_pos(x, y, tight=True) is not None:
                continue
            return x, y, block, wide
    return None


def down(g, x, y):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(int(x), int(y))))
    g.handle_events()


def up(g, x, y):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, button=1, pos=(int(x), int(y))))
    g.handle_events()


# ---- A. 按下挂起：块命中保留，gap 不立即提交 ----------------------------
g = boot()
probe = find_press_point(g)
check('A0 找到「块 + 宽兜底缝」探测点', probe is not None, f'{probe}')
if probe:
    x, y, block, wide = probe
    down(g, x, y)
    check('A1 按下不立即选缝', g.selected_gap is None, f'{g.selected_gap}')
    check('A2 候选缝已挂起', g._pending_gap_click is not None,
          f'{getattr(g, "_pending_gap_click", None)}')
    check('A3 挂起的就是宽兜底缝',
          g._pending_gap_click and g._pending_gap_click['gap'] == wide,
          f'{getattr(g, "_pending_gap_click", None)} vs {wide}')
    check('A4 拖拽起点仍然记到了块',
          g._mouse_drag_state is not None
          and g._mouse_drag_state.get('block') is block,
          f'{getattr(g, "_mouse_drag_state", None)}')

    # C. 没拖动就松手 → 补提交选缝
    up(g, x, y)
    check('C1 松手没拖才补选缝', g.selected_gap == wide, f'{g.selected_gap}')
    check('C2 松手后 pending 清空', g._pending_gap_click is None)
    check('C3 松手后拖拽状态清空', g._mouse_drag_state is None)

# ---- B. 拖动超过阈值：pending 作废，不再回头选缝 -------------------------
g = boot()
probe = find_press_point(g)
if probe:
    x, y, _block, _wide = probe
    down(g, x, y)
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEMOTION, pos=(int(x + 20), int(y)),
        rel=(20, 0), buttons=(1, 0, 0)))
    g.handle_events()
    check('B1 拖动阈值后 pending 作废', g._pending_gap_click is None,
          f'{getattr(g, "_pending_gap_click", None)}')
    check('B1b 拖动确实进了单次触控跟随', g.drag_following,
          f'gap={g.selected_gap} block={tuple(g.drag_follow_block.location) if g.drag_follow_block else None}')
    gap_after_motion = g.selected_gap
    up(g, x + 20, y)
    check('B2 拖动松手后没有补选缝', g._pending_gap_click is None)
    check('B3 拖动松手按单次触控清空选中（不是补提交点击）',
          g.selected_gap is None, f'{g.selected_gap} (拖动中 {gap_after_motion})')

# ---- D. 右键取消：pending 一并作废 --------------------------------------
g = boot()
probe = find_press_point(g)
if probe:
    x, y, _block, _wide = probe
    down(g, x, y)
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=3, pos=(int(x), int(y))))
    g.handle_events()
    check('D1 右键后 pending 清空', g._pending_gap_click is None)
    up(g, x, y)
    check('D2 右键后松左键不再补选缝', g.selected_gap is None,
          f'{g.selected_gap}')

# ---- E. _sq_click_query 两种返回语义 -------------------------------------
g = boot()
probe = find_press_point(g)
if probe:
    x, y, block, wide = probe
    g.selected_gap = None
    g0, b0 = g._sq_click_query(x, y)
    check('E1 默认仍按旧语义清 block', g0 == wide and b0 is None,
          f'gap={g0} block={b0}')
    g.selected_gap = None
    g1, b1 = g._sq_click_query(x, y, preserve_block=True)
    check('E2 preserve_block 保留块命中', g1 == wide and b1 is block,
          f'gap={g1} block={b1}')

# ---- F. 真实拖动落子：带洞棋盘的右拖必须进入动画，不再变成点缝 --------
g = boot()
g.new_puzzle(4, 4, 1)
cells = {(r, c) for r in range(4) for c in range(4)} - {(0, 3)}
g.game.apply_pattern(cells, {})
g.center_map()
v = g.board_view
wx, wy = v.cell_to_world(0, 0)
x, y = g.world_to_screen(wx + v.cell_size / 2 + 8,
                         wy + v.cell_size / 2 + 8)
check('F0 带洞棋盘探测点仍同时命中块/宽缝',
      g.get_block_at_pos(x, y) is not None
      and g.get_gap_at_pos(x, y, tolerance=28.0) is not None)
down(g, x, y)
pygame.event.post(pygame.event.Event(
    pygame.MOUSEMOTION, pos=(int(x + 96), int(y)),
    rel=(96, 0), buttons=(1, 0, 0)))
g.handle_events()
check('F1 右拖进入单次触控跟随', g.drag_following,
      f'gap={g.selected_gap} max={getattr(g, "drag_follow_max_cells", None)}')
up(g, x + 96, y)
check('F2 松手提交了移动动画（不是补选缝）',
      g.animating and bool(getattr(g, 'anim_blocks', None)),
      f'animating={g.animating} blocks={len(getattr(g, "anim_blocks", []))}')

# ---- G. 只有两击模式时保持旧语义：按下即选缝，不吃成 pending --------
g = boot()
g.control_single_touch = False
probe = find_press_point(g)
if probe:
    x, y, _block, wide = probe
    down(g, x, y)
    check('G1 两击模式按下即选缝', g.selected_gap == wide,
          f'{g.selected_gap} vs {wide}')
    check('G2 两击模式不产生 pending', g._pending_gap_click is None)
    up(g, x, y)

print()
if _failed:
    print(f'FAILED {len(_failed)}: ' + '; '.join(_failed))
    sys.exit(1)
print('ALL PASS')
