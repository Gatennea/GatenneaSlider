# -*- coding: utf-8 -*-
"""量碎三角在 zoom=1 下每一块的真实屏幕尺寸（边长的 min/中位/max）。"""
import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from GUI import SliderGUI

g = SliderGUI()
g.animation_enabled = False
g.new_model_puzzle('shatter', 1)
g.zoom = 1.0
g.center_map()

view = g._polygon_view()
origin = g._poly_view_origin(view)

lens = []
for blk in g.game.blocks:
    key = g._visual_key(blk)
    point, orient = g._poly_key_parts(key)
    poly = view.world_polygon(point, orient, origin)
    pts = [g.world_to_screen(x, y) for (x, y) in poly]
    n = len(pts)
    for k in range(n):
        a, b = pts[k], pts[(k + 1) % n]
        lens.append(math.hypot(b[0] - a[0], b[1] - a[1]))

lens.sort()
print('cell_size =', g.cell_size, ' zoom =', g.zoom)
print('tile edge px  min=%.1f  p25=%.1f  median=%.1f  p75=%.1f  max=%.1f'
      % (lens[0], lens[len(lens)//4], lens[len(lens)//2],
         lens[3*len(lens)//4], lens[-1]))
print('n_edges =', len(lens))
spec = g.game.board.spec
print('spec.seam_width =', spec.seam_width, ' spec.corner_radius =', spec.corner_radius)
print('  -> seam_half = %.2f px, radius = %.2f px'
      % (spec.seam_width / 2.0, spec.corner_radius))
print('  radius / median edge = %.1f%%'
      % (100.0 * spec.corner_radius / lens[len(lens)//2]))
