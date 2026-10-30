# -*- coding: utf-8 -*-
"""探针：高级选项（设计画布）进入/退出是否原样还原，以及是否残留标注模式。

用法：D:/python/python.exe experiments/script__probe_adv.py
输出：screenshots/probe_adv_{0_before,1_design,2_after}.png
"""
import os
import sys
import queue

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from gui import design_styles  # noqa: E402

OUT = os.path.join(_PROJ, 'screenshots')
os.makedirs(OUT, exist_ok=True)


def shot(gui, tag):
    gui.draw_board()
    gui.draw_right_panel()
    gui.draw_status_bar()
    gui.draw_annotation_mode()
    gui.draw_menu_bar()
    path = os.path.join(OUT, f'probe_adv_{tag}.png')
    pygame.image.save(gui.screen, path)
    print('shot ->', path)


def state(gui):
    coords = frozenset((int(b.location[0]), int(b.location[1]))
                       for b in gui.game.blocks)
    groups = tuple(sorted(
        (int(b.location[0]), int(b.location[1]), int(getattr(b, 'group', 0)))
        for b in gui.game.blocks if getattr(b, 'group', 0)))
    return {
        'cells': coords,
        'groups': groups,
        'm': gui.current_m, 'n': gui.current_n, 'step': gui.current_step,
        'game_m': gui.game.m, 'game_n': gui.game.n,
        'blocks': len(gui.game.blocks),
        'game_mode': gui.game_mode,
        'ann_mode': getattr(gui, 'annotation_mode', None),
        'create_mode': gui.create_mode,
        'ann_view': getattr(gui, '_ann_view', None),
        'ann_sub': getattr(gui, '_ann_sub_dialog', None),
        'style_goal': getattr(gui, '_ann_style_goal', None),
        'goal': gui.game.goal_pattern,
        'step_count': gui.step_count,
        'hi': gui.game_history.history_index,
        'n_hist': len(gui.game_history.history),
        'solved': gui.game.is_solved(),
    }


def show(tag, gui, verbose=False):
    st = state(gui)
    print(f'--- {tag}')
    for k, v in st.items():
        if verbose or k in ('m', 'n', 'step', 'game_m', 'game_n', 'blocks',
                            'game_mode', 'ann_mode', 'create_mode',
                            'ann_view', 'ann_sub', 'style_goal',
                            'step_count', 'hi', 'n_hist', 'solved'):
            print(f'    {k} = {v}')
    return st


gui = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                ext_state={'enabled': False, 'token': None})
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.game_mode = 'practice'
gui.new_puzzle(4, 4, 1)

# 造一个样式：3×3 缺角 + 左上 2×2 捆绑
sname = 'probe_adv'
design_styles.delete_style(gui.config_dir, sname)
cells = [[r, c] for r in range(3) for c in range(3) if (r, c) != (2, 2)]
groups = {(0, 0): 1, (0, 1): 1, (1, 0): 1, (1, 1): 1}
design_styles.save_style(gui.config_dir, sname, {
    'version': 1, 'name': sname, 'm': 3, 'n': 3, 'step': 1,
    'cells': cells, 'groups': {f'{r},{c}': g for (r, c), g in groups.items()},
})

gui._ann_design_start_style(sname)
gui.center_map()
before = show('BEFORE 样式局', gui)
shot(gui, '0_before')

# —— 进入高级选项 ——
gui._ann_open_advanced()
mid = show('IN DESIGN', gui)
shot(gui, '1_design')

# —— 点「退出」按钮（真实按钮分发路径） ——
gui._ann_btn_build_cancel()
after = show('AFTER 退出', gui)
shot(gui, '2_after')

print('\n=== 差异（before vs after）===')
for k in before:
    if before[k] != after[k]:
        print(f'  [DIFF] {k}: {before[k]!r} -> {after[k]!r}')
print('\n=== 进入时画布内容 vs 进入前 ===')
print('  before cells =', sorted(before['cells']))
print('  canvas  cells =', sorted(gui._ann_build_coords) if True else None)
print('  canvas  groups =', gui._ann_design_groups)
print('  m/n/step =', mid['m'], mid['n'], mid['step'])

design_styles.delete_style(gui.config_dir, sname)
