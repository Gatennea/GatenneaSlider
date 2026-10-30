# -*- coding: utf-8 -*-
"""探针：碎三角合法移动的落点性质（决定拖拽选缝规则的实证依据）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.registry import make_board

b = make_board('shatter')
print('blocks:', len(b.blocks), 'families:', [f.name for f in b.spec.seam_families])
moves = b.legal_moves(1)
print('legal_moves(1):', len(moves))

# 逐条看：落点是否与停留块重叠、是否自撞（frozenset 去重会缩容）
self_collide = 0
stay_collide = 0
empty_dest = 0
for mv in moves:
    delta = tuple(mv.step * x for x in mv.direction)
    moved = set(mv.moved)
    rest = b.keys - moved
    new_keys = [((p[0] + delta[0], p[1] + delta[1]), o) for p, o in moved]
    if len(set(new_keys)) != len(new_keys):
        self_collide += 1
    if set(new_keys) & rest:
        stay_collide += 1
    if not (set(new_keys) & rest):
        empty_dest += 1
print('self_collide:', self_collide, 'stay_collide:', stay_collide,
      'clean:', empty_dest)

# 抽一条活缝看细节：L_v 的某条
from collections import Counter
cnt = Counter((mv.family, mv.t) for mv in moves)
print('(family,t) 分布:', dict(cnt))

# 取 L_v 家族第一条移动，打印移动块数、方向、以及落点原先是否为空
fam_name = 'L_v'
sample = [mv for mv in moves if mv.family == fam_name][:4]
old_keys = set(b.keys)
for mv in sample:
    delta = tuple(mv.step * x for x in mv.direction)
    moved = set(mv.moved)
    rest = old_keys - moved
    new_keys = {((p[0] + delta[0], p[1] + delta[1]), o) for p, o in moved}
    vacant = [k for k in new_keys if k not in old_keys]
    onto_rest = new_keys & rest
    print(f'{mv.family} t={mv.t} side={mv.side} dir={mv.direction} '
          f'moved={len(moved)} rest={len(rest)} '
          f'新位置原先为空={len(vacant)} 压在停留块上={len(onto_rest)}')
