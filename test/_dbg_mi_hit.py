# -*- coding: utf-8 -*-
"""米字格点击裁定：换几个容差，量「点滑块中部」与「点缝隙」各自的命中率。"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import random  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_mi import mi_key, mi_vertices  # noqa: E402

gui = SliderGUI(m=6, n=6, step=1)
gui.save_readonly_flag = False
gui.new_mi_puzzle(6, 6, 1)
view = gui._mi_view()
cells = gui.game.positions()
S = view.cell_size

blk = gui.game.blocks[0]
key = mi_key(blk)
tri = [view.to_world(x, y) for (x, y) in mi_vertices(*key)]
cx, cy = view.incenter(*key)
centroid = (sum(p[0] for p in tri) / 3.0, sum(p[1] for p in tri) / 3.0)


def interior_point(frac_from_center):
    """从内心朝三个顶点各走 frac，取三点。"""
    return [(cx + (vx - cx) * frac_from_center, cy + (vy - cy) * frac_from_center)
            for (vx, vy) in tri]


def seam_point():
    """三条真实缝隙线上的点（各边中点）。"""
    pts = []
    for i in range(3):
        a = tri[i]
        b = tri[(i + 1) % 3]
        pts.append(((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0))
    return pts


print(f"内心 ({cx:.1f},{cy:.1f})  视觉中心 ({centroid[0]:.1f},{centroid[1]:.1f})  "
      f"视觉中心到最近缝 = "
      f"{min(view.gap_line_distance('h', 0, *centroid), 0):.1f}")
for tol in (9.0, 7.0, 6.0, 5.0, 4.0, 3.0):
    # 视觉中心三点采样
    mid_hits = sum(1 for p in interior_point(0.0)
                   if view.gap_at(p[0], p[1], cells, tolerance=tol) is not None)
    # 从视觉中心朝最近边挪 ±2/±4px
    jitter = []
    for p in [centroid]:
        for dx, dy in ((0, -4), (0, 4), (-4, 0), (4, 0), (0, -6), (0, 6)):
            jitter.append((p[0] + dx, p[1] + dy))
    jitter_hits = sum(1 for p in jitter
                      if view.gap_at(p[0], p[1], cells, tolerance=tol) is not None)
    # 缝隙线上
    seam_hits = sum(1 for p in seam_point()
                    if view.gap_at(p[0], p[1], cells, tolerance=tol) is not None)
    # 均匀采样块内
    random.seed(11)
    inside = gapn = 0
    for _ in range(3000):
        while True:
            x = random.uniform(0, S)
            y = random.uniform(0, S)
            if view.world_to_cell(x, y, cells) == key:
                break
        inside += 1
        if view.gap_at(x, y, cells, tolerance=tol) is not None:
            gapn += 1
    print(f"容差 {tol:4.1f}px：视觉中心命中缝隙 {mid_hits}/3，"
          f"中心±4~6px 命中 {jitter_hits}/{len(jitter)}，"
          f"缝隙线命中 {seam_hits}/3，"
          f"块内均匀命中 {gapn}/{inside} ({gapn/inside*100:.0f}%)")
