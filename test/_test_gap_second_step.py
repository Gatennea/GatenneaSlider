# -*- coding: utf-8 -*-
"""护栏：缝隙命中带按交互阶段切换，选中缝之后要能选中滑块。

用户 2026-11-07 报：某次「加大选缝判定范围」之后，选中缝隙反而难以选中
滑块。根因不在宽兜底本身，而在两下点击共用一条命中带——事件层
``if gap is not None`` 优先于「点块」分支，第二下点在滑块里、离缝十来像素
也会被判成「重新选缝」（点同一条缝还会直接取消选中）。

正解（本护栏钉住）：第一击沿用精准带 ±10 + 点偏进相邻块的 ±28 宽兜底；
**已选中缝后的第二下**四种形态一律收到 `GAP_TOL_SECOND`（2 世界单位），
只有真的压在缝线上才判成换缝/取消，其余都落到选块。

覆盖方形 / 三角 / 米字 / 通用多边形（碎三角模型）四种形态，每组都跑完整
`handle_events` 而不是只查几何函数。末尾有「反向验证」：临时撤掉收窄，
第二击必须重新选不中滑块，证明这组断言真的抓得住回流。

执行：python test/_test_gap_second_step.py
"""
import inspect
import os
import queue
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from gui.board_view import GAP_TOL_FIRST, GAP_TOL_SECOND  # noqa: E402

_failed = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failed.append(name)
    return bool(cond)


def boot(kind):
    g = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                  ext_state={'enabled': False, 'token': None})
    g.game_mode = 'practice'
    g.tutorial_active = False
    g.tut_show_prompt = False
    g.save_readonly_flag = False
    if kind == 'sq':
        g.new_puzzle(4, 4, 2)
        g.game.apply_pattern({(r, c) for r in range(4) for c in range(4)}, {})
    elif kind == 'tri':
        g.new_triangle_puzzle(4, 2)
    elif kind == 'mi':
        g.new_mi_puzzle(4, 4, 2)
    elif kind == 'generic':
        g.new_model_puzzle('shatter', 1)
    g._update_in_progress = False
    g.center_map()
    return g


def click(g, x, y):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(int(x), int(y))))
    g.handle_events()


def find_near_seam_block(g):
    """找「第一击判成缝、第二击判成块」的点：点在滑块里但贴着缝。"""
    w, h = g.screen.get_size()
    for y in range(h // 2 - 130, h // 2 + 130, 4):
        for x in range(w // 2 - 170, w // 2 + 170, 4):
            try:
                seam = g.get_gap_at_pos(x, y)
                if seam is None or g.get_block_at_pos(x, y) is None:
                    continue
                if g.get_gap_at_pos(x, y, tight=True) is None:
                    return x, y, seam
            except Exception:
                continue
    return None


# ---- 1. 常量与接线（防「收窄」被改回单一命中带） -------------------------
check('1a 第二击命中带严格小于第一击',
      0 < GAP_TOL_SECOND < GAP_TOL_FIRST,
      f'{GAP_TOL_SECOND} < {GAP_TOL_FIRST}')
_sq_src = inspect.getsource(SliderGUI._sq_click_query)
_mi_src = inspect.getsource(SliderGUI._mi_click_query)
check('1b 方形/三角/通用按 selected_gap 传 tight',
      'tight=second_step' in _sq_src)
check('1c 米字格第二击用同一个收窄常量',
      'GAP_TOL_SECOND' in _mi_src and 'second_step' in _mi_src)

# ---- 2~5. 四种形态：第一击选缝不变，第二击能选中滑块 ---------------------
for kind in ('sq', 'tri', 'mi', 'generic'):
    probe = find_near_seam_block(boot(kind))
    check(f'2 {kind} 能找到「贴缝的滑块内」探测点', probe is not None,
          f'{probe}')
    if probe is None:
        continue
    x, y, seam = probe

    g = boot(kind)
    click(g, x, y)
    check(f'3 {kind} 第一击照旧选中缝', g.selected_gap == seam,
          f'{g.selected_gap} vs {seam}')
    check(f'4 {kind} 第一击不选块', g.selected_block is None)

    g = boot(kind)
    g.selected_gap = seam
    click(g, x, y)
    check(f'5 {kind} 第二击选中滑块（本次修复点）',
          g.selected_block is not None,
          f'{tuple(g.selected_block.location) if g.selected_block else None}')
    check(f'6 {kind} 第二击没有把缝取消/换掉',
          g.selected_gap == seam, f'{g.selected_gap}')

# ---- 7. 换缝仍可达：收窄不等于「再也点不到缝」 ---------------------------
g = boot('sq')
v = g.board_view
unit = v.cell_size + v.gap_width
gw = v.gap_width
wx = 1 * unit + v.cell_size / 2
g.selected_gap = ('h', 1)
sx, sy = g.world_to_screen(wx, 3 * unit - gw / 2)
click(g, sx, sy)
check('7 点在下一条缝线上仍能换缝', g.selected_gap == ('h', 2),
      f'{g.selected_gap}')

# ---- 8. 反向验证：撤掉收窄，第二击必须重新选不中滑块 ----------------------
probe = find_near_seam_block(boot('sq'))
if probe:
    x, y, seam = probe
    g = boot('sq')
    g.selected_gap = seam
    _orig = SliderGUI.get_gap_at_pos

    def _no_tight(self, sx, sy, tolerance=None, *, tight=False):
        return _orig(self, sx, sy, tolerance, tight=False)

    SliderGUI.get_gap_at_pos = _no_tight
    try:
        click(g, x, y)
    finally:
        SliderGUI.get_gap_at_pos = _orig
    check('8 反向：去掉收窄后第二击选不中滑块（护栏确实抓得住）',
          g.selected_block is None,
          f'gap={g.selected_gap} block={g.selected_block}')

# ---- 汇总 ----------------------------------------------------------------
print()
if _failed:
    print(f'FAILED {len(_failed)}: ' + '; '.join(_failed))
    sys.exit(1)
print('ALL PASS')
