# -*- coding: utf-8 -*-
"""验证点击解析在 A/B 重疊區的誤配（本 bug 的觸發路徑）。"""
import os, sys
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.mi_view import MiBoardView
from game_mi import MiSliderMatrix, any_overlap

v = MiBoardView(60.0, 4.0)
full = set(MiSliderMatrix(6, 6).positions())

# 滿盤 A 晶格：點在 A(0,0,'E') 方塊靠格心的一角（世界座標 = 格座標*60）
for gx, gy in [(0.9, 0.68), (0.95, 0.9), (0.68, 0.9), (0.6, 0.62)]:
    wx, wy = gx * 60, gy * 60
    bare = v.world_to_cell(wx, wy)
    filt = v.world_to_cell(wx, wy, cells=full)
    in_coords = bare in full if bare else None
    print(f'点击格坐标({gx},{gy}): 裸解析={bare} 在盘上={in_coords} '
          f'| 构造集过滤后={filt}')

# 該 bare key 若加入盤面是否重疊
add = v.world_to_cell(0.9 * 60, 0.68 * 60)
print('加入后 any_overlap =', any_overlap(full | {add}))

# 混合態：點在一個 B 層塊上（引擎走一步斜向產生的合法混合態）
g = MiSliderMatrix(6, 6)
d1 = [gp for gp in g.all_gaps() if gp[0] == 'd1']
g.opt(*d1[len(d1) // 2], g.blocks[0])
pos = g.try_move('x', 1)
g.commit_move(pos)
mixed = g.positions()
b_keys = [k for k in mixed if not float(k[0]).is_integer()]
print(f'混合态 B 层块数: {len(b_keys)}')
for k in b_keys[:3]:
    cx, cy = v.incenter(*k)
    bare = v.world_to_cell(cx, cy)
    filt = v.world_to_cell(cx, cy, cells=mixed)
    print(f'点 B 层块 {k} 内心: 裸解析={bare} 过滤后={filt}')
