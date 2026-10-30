# -*- coding: utf-8 -*-
"""复现：米字格创造模式增删方块可造成跨晶格直接重疊。"""
from game_mi import MiSliderMatrix, any_overlap, coords_coherent

def report(title, cells):
    print(f'{title}: n={len(cells)} coherent={coords_coherent(cells)} '
          f'overlap={any_overlap(cells)}')

# 用引擎自己走一步斜向，產生合法的混合晶格（错位）态
g = MiSliderMatrix(6, 6)
gaps = g.all_gaps()
d1 = [gp for gp in gaps if gp[0] == 'd1']
print('d1 gaps:', d1[:4], '...')
gap_type, line = d1[len(d1) // 2]
g.opt(gap_type, line, g.blocks[0])
pos = g.try_move('x', 1)
print('move ok:', bool(pos))
if pos:
    g.commit_move(pos)
mixed = g.positions()
report('引擎走一步斜向后的合法混合态', mixed)

# 从合法混合态出发，模拟用户点选追加一个几何上压在别层块上的位置
for add in [(0.5, 0.5, 'N'), (0.5, 0.5, 'W'), (1, 1.5, 'S')]:
    report(f'混合态 + {add}', mixed | {add})

# 场景：对齐态满盘（构造画布常见初始态）+ 用户点到 B 层空位
full = set(MiSliderMatrix(6, 6).positions())
report('满盘 A 晶格（合法）', full)
report('满盘 + (0.5,0.5,N)（当前 GUI 允许放入 → 直接重疊）', full | {(0.5, 0.5, 'N')})
