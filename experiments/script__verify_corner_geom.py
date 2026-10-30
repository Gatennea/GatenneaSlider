# -*- coding: utf-8 -*-
"""数值验证：corner_radius 是否真的按设定值生效（量「尖角顶点 → 圆角弧」的距离）。"""
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
spec = g.game.board.spec

view = g._polygon_view()
origin = g._poly_view_origin(view)


def corner_inset(pts, seam_half, radius):
    """返回 (内缩后的尖角顶点 → 圆角多边形最近点) 的距离列表。

    几何上该距离应 ≈ radius（圆心在角平分线上距顶点 radius/sin(θ/2)，
    弧上距顶点最近的点正好是 radius）。
    """
    inset = g._offset_polygon_px(pts, -seam_half)
    rpoly = g._rounded_polygon_points(inset, radius)
    outs = []
    for v in inset:
        d = min(math.hypot(p[0] - v[0], p[1] - v[1]) for p in rpoly)
        outs.append(d)
    return outs


for sw, cr in ((4, 2), (6, 3), (8, 4), (10, 5), (12, 6)):
    object.__setattr__(spec, 'seam_width', sw)
    object.__setattr__(spec, 'corner_radius', cr)
    seam_half = sw / 2.0
    ds = []
    for blk in list(g.game.blocks)[:6]:
        key = g._visual_key(blk)
        point, orient = g._poly_key_parts(key)
        poly = view.world_polygon(point, orient, origin)
        pts = [g.world_to_screen(x, y) for (x, y) in poly]
        ds.extend(corner_inset(pts, seam_half, cr))
    ds.sort()
    print('seam=%2d radius=%d -> 实测角部内缩  min=%.2f median=%.2f max=%.2f  (期望≈%d)'
          % (sw, cr, ds[0], ds[len(ds)//2], ds[-1], cr))
