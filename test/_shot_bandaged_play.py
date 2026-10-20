# -*- coding: utf-8 -*-
"""无头截图验证：把「演示-捆绑」样式按真实加载路径灌进游玩主棋盘，
渲染后存 PNG，肉眼确认捆绑组显示为「一整块实心矩形」而非连线。

用法：D:/python/python.exe test/_shot_bandaged_play.py
输出：screenshots/bandaged_play.png
"""
import os, sys, json, queue

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame
from GUI import SliderGUI
from gui import design_styles

OUT = os.path.join(_PROJ, 'screenshots', 'bandaged_play.png')

# —— 启动 GUI（无头），无需 HTTP / 主循环，直接命令式渲染 ——
cmd_queue = queue.Queue()
ext_state = {'enabled': False, 'token': None}
gui = SliderGUI(m=5, n=5, step=2, cmd_queue=cmd_queue, ext_state=ext_state)
gui.game_mode = 'practice'

# —— 真实加载路径：design_styles.load_style -> apply_pattern + set_goal_pattern ——
name = '演示-捆绑'
data = design_styles.load_style(gui.config_dir, name)
assert data, f'样式「{name}」加载失败'
cells = [tuple(p) for p in data['cells']]
groups = {}
for k, v in (data.get('groups') or {}).items():
    r, c = k.split(',')
    groups[(int(r), int(c))] = int(v)

gui.game.apply_pattern(cells, groups)
gui.game.set_goal_pattern(cells)
gui.current_m, gui.current_n, gui.current_step = gui.game.m, gui.game.n, data.get('step', 2)

# —— 渲染游玩主棋盘（draw_board 内部会调 _draw_bandaged_groups_play）——
gui.draw_board()
os.makedirs(os.path.dirname(OUT), exist_ok=True)
pygame.image.save(gui.screen, OUT)

# —— 报告：哪些块带了 group，gid 分布 ——
from collections import Counter
gc = Counter(getattr(b, 'group', 0) for b in gui.game.blocks)
print(f'已加载样式「{name}」: m={gui.game.m} n={gui.game.n} blocks={len(gui.game.blocks)}')
print(f'group 分布: {dict(gc)}  (0=未捆绑, 其余=捆绑组号)')
print(f'截图已存: {OUT}  ({gui.screen.get_width()}x{gui.screen.get_height()})')
