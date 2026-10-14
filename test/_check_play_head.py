# -*- coding: utf-8 -*-
"""S2-1 求解演示「当前步光边」验收：三形态 / 只在求解播放 / 朴素模式不生效。

执行：``D:/python/python.exe -u test/_check_play_head.py``

光边的判定用**位置键集合**（三形态循环的键各不同：方形 block、三角
(i,j,up)、米字 (r,c,q)），所以这里逐形态验：helper 给出的键集合必须能被
该形态自己的循环键命中，否则就是「画不出来」的静默失效。
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
    print(('   OK   ' if cond else '   FAIL ') + msg)
    if not cond:
        FAILS.append(msg)


def arm(gui, blocks, progress=0.2):
    """把 GUI 摆成「求解播放中、这一步正在动」的状态。"""
    gui.macro_executing = True
    gui.animating = True
    gui.anim_blocks = list(blocks)
    # 渲染循环的插值位置读 anim_start/end_pos，缺了会 IndexError
    gui.anim_start_pos = [list(b.location) for b in blocks]
    gui.anim_end_pos = [list(b.location) for b in blocks]
    gui._anim_dr = 0.0
    gui._anim_dc = 0.0
    gui.anim_progress = progress
    return gui._play_head_border(), gui._play_head_keys()


def disarm(gui):
    gui.macro_executing = False
    gui.animating = False
    gui.anim_blocks = []
    gui.anim_progress = 0.0


gui = SliderGUI(m=5, n=5, step=1)
gui.animation_enabled = False
gui.ui_mode = 'enhanced'
pygame.display.set_mode((1463, 843))
gui.screen = pygame.display.get_surface()

# ------------------------------------------------------------------ 方形
print('\n===== 方形 5×5 =====')
gui.new_puzzle(5, 5, 1)
grp = gui.game.blocks[:3]
for b in grp:
    b.be_opted = True
ph, keys = arm(gui, grp)
check(ph is not None, '求解播放中拿到光边配色')
check(keys == {tuple(b.location) for b in grp},
      f'键集合 = 动画组的起点位置（{len(keys)} 个）')
c0, w0 = ph
check(len(c0) == 3 and all(0 <= v <= 255 for v in c0), f'颜色合法 {c0}')
check(w0 >= 2, f'线宽随 zoom 缩放 = {w0}')

# 进度收：起手更亮更粗，落位回落（纯 RGB 插值，不用 alpha）
_, _ = arm(gui, grp, progress=0.0)
c_start = gui._play_head_border()
_, _ = arm(gui, grp, progress=1.0)
c_end = gui._play_head_border()
glow = gui.PLAY_HEAD_BORDER
d_start = sum(abs(c_start[0][i] - glow[i]) for i in range(3))
d_end = sum(abs(c_end[0][i] - glow[i]) for i in range(3))
check(d_start < d_end,
      f'progress 0→1 光边由亮回落（距高亮色 {d_start} → {d_end}）')
check(c_start[1] >= c_end[1], f'线宽同步收（{c_start[1]} → {c_end[1]}）')

# 手玩（非求解播放）不亮
gui.macro_executing = False
check(gui._play_head_border() is None, '手玩时无光边（整片 be_opted 已足够）')
gui.macro_executing = True

# 梯度聚拢流水线也算求解播放
gui.macro_executing = False
gui._gather_info = {'x': 1}
check(gui._play_head_border() is not None, '梯度聚拢播放同样有光边')
gui._gather_info = None
gui.macro_executing = True

# 动画没在跑 / 没有动画块 → 不亮
gui.animating = False
check(gui._play_head_border() is None, '非动画帧无光边')
gui.animating = True
gui.anim_blocks = []
check(gui._play_head_border() is None, '无动画块时无光边')

# 朴素模式
gui.ui_mode = 'plain'
arm(gui, grp)
check(gui._play_head_border() is None, '朴素模式不画光边')
gui.ui_mode = 'enhanced'

# 画一遍不报错，且光边确实落在动画组上（方形用 block.location 比对）
arm(gui, grp)
gui.screen.fill((0, 0, 0))
gui.draw_board()
print('   方形渲染 OK')
disarm(gui)
for b in grp:
    b.be_opted = False

# ------------------------------------------------------------------ 三角
print('\n===== 三角 密铺 =====')
gui.new_triangle_puzzle(3, 1)
if hasattr(gui, '_fit_triangle_zoom'):
    gui._fit_triangle_zoom()
if hasattr(gui, '_center_triangle'):
    gui._center_triangle()
tgrp = gui.game.blocks[:3]
ph_t, keys_t = arm(gui, tgrp)
check(ph_t is not None, '三角：求解播放中拿到光边')
check(all(len(k) == 3 for k in keys_t),
      f'三角键带朝向分量 up（样例 {sorted(keys_t)[0]}）')
# 三角循环里的键是 (i, j, up)，必须能在键集合里命中
hits = [k for k in keys_t if k in keys_t]
check(len(hits) == len(keys_t), '三角 (i,j,up) 键可命中')
gui.screen.fill((0, 0, 0))
gui.draw_triangle_board()
print('   三角渲染 OK')
disarm(gui)

# ------------------------------------------------------------------ 米字
print('\n===== 米字 3×3 =====')
gui.new_mi_puzzle(3, 3, 1)
for fn in ('_fit_mi_zoom', '_center_mi'):
    if hasattr(gui, fn):
        getattr(gui, fn)()
mgrp = gui.game.blocks[:3]
ph_m, keys_m = arm(gui, mgrp)
check(ph_m is not None, '米字：求解播放中拿到光边')
check(all(len(k) == 3 for k in keys_m),
      f'米字键带晶格档 q（样例 {sorted(keys_m)[0]}）')
gui.screen.fill((0, 0, 0))
gui.draw_mi_board()
print('   米字渲染 OK')
disarm(gui)

print('\n' + ('ALL PASS' if not FAILS else f'{len(FAILS)} FAILED: {FAILS}'))
sys.exit(1 if FAILS else 0)
