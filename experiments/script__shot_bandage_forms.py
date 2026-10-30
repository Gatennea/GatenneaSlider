# -*- coding: utf-8 -*-
"""三角 / 米字捆绑组渲染截图（人工查看用，纯离屏）。

造局后手工给指定小group塞 group（模拟设计态捆绑），再截图：
  1. 三角：3 块「凹角」组 + 2 块组（同胞 ▲+▼ = 菱形）
  2. 米字：同格 4 块整胞 + 3 块凹角组
  3. 三角：选中态（be_opted=True）填充色是否跟随

输出到 experiments/_shot_bandage_{tri,mi,tri_sel}.png
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_mi import neighbors as mi_neighbors  # noqa: E402
from game_triangle import neighbors as tri_neighbors  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))


def set_groups(gui, plan):
    """plan = [(gid, [位置, ...]), ...]；位置必须在盘面上。"""
    pos = {tuple(b.location): b for b in gui.game.blocks}
    for gid, cells in plan:
        for c in cells:
            if tuple(c) not in pos:
                print('  !! 不在盤面:', c)
                continue
            pos[tuple(c)].group = gid


def report(gui):
    groups = {}
    for b in gui.game.blocks:
        if b.group:
            groups.setdefault(b.group, []).append(tuple(b.location))
    for gid, cells in sorted(groups.items()):
        print(f'  gid={gid} n={len(cells)} {cells}')


def shoot(gui, name, method):
    getattr(gui, method)()
    path = os.path.join(OUT, name)
    pygame.image.save(gui.screen, path)
    print('saved:', path)
    report(gui)


def find(gui, pred):
    return [tuple(b.location) for b in gui.game.blocks if pred(tuple(b.location))]


# ================= 1) 三角 =================
gui = SliderGUI()
gui.animation_enabled = False
gui.new_triangle_puzzle(6, 2)

# 3 块凹角组：找一個「三個鄰塊都在盤面上」的 ▲，綁它 + 兩個鄰塊 →
# 天然一個 V 形凹角（三塊共享一個頂點，中間那塊被夾住）
cells_tri = {tuple(b.location) for b in gui.game.blocks}
best = None
for p in sorted(c for c in cells_tri if c[2] is True):
    nbs = [tuple(n) for n in tri_neighbors(p)]
    on = [n for n in nbs if n in cells_tri]
    if len(on) == 3:
        best = (p, on)
        break
if best is None:
    best = max(((p, [n for n in map(tuple, tri_neighbors(p)) if n in cells_tri])
                for p in cells_tri if p[2] is True), key=lambda t: len(t[1]))
p, on = best
print('凹角組 seed =', p, '邻块 =', on)
gid1 = [p, on[0], on[1]]
set_groups(gui, [(1, gid1)])

# 2 块组：同胞 ▲+▼（菱形，最紧的一种捆绑）
same = [(p2, q) for p2 in cells_tri if p2[2] is True
        for q in [tuple(n) for n in tri_neighbors(p2)]
        if q[2] is False and q[0] == p2[0] and q[1] == p2[1]
        and p2 not in gid1 and q not in gid1 and q in cells_tri]
if same:
    p2, q = same[-1]
    set_groups(gui, [(2, [p2, q])])
shoot(gui, '_shot_bandage_tri.png', 'draw_triangle_board')

# ================= 2) 三角选中态 =================
for b in gui.game.blocks:
    b.be_opted = bool(b.group)
shoot(gui, '_shot_bandage_tri_sel.png', 'draw_triangle_board')
for b in gui.game.blocks:
    b.be_opted = False

# ================= 3) 米字 =================
gui.new_mi_puzzle(4, 2)
cells = [tuple(b.location) for b in gui.game.blocks]

# 整胞 4 块
by_cell = {}
for p in cells:
    by_cell.setdefault((int(p[0]), int(p[1])), []).append(p)
quads = [v for v in by_cell.values() if len(v) == 4]
set_groups(gui, [(200, quads[0])])
used = set(quads[0])

# 3 块凹角组：取一块 N，加上它的两个邻块（同格 E + 下方）
cand = [p for p in cells if p[2] == 'N' and p not in used]
for p in cand:
    nbs = [tuple(n) for n in mi_neighbors(p) if tuple(n) in set(cells)]
    trio = [p] + nbs[:2]
    if len(trio) == 3 and not (set(trio) & used):
        set_groups(gui, [(300, trio)])
        break
shoot(gui, '_shot_bandage_mi.png', 'draw_mi_board')

print('OK')
