# -*- coding: utf-8 -*-
"""探针：捆绑组填色是否溢出「整组轮廓」（用户截图里那个小凸包）。

判据（与画法无关的硬不变量）：
  组内每一块都是按**完整多边形**内缩后填色的，桥接四边形也在两块之间，
  所以屏幕上任何一点「组的填充色」都必须落在**某个完整多边形的内部**
  （含边界附近 2px 容差）。溢出的像素 = 画到了组外 → 凸包。

同时对比修复前后：`interior_angle` 条件（组内角之和≈2π）才补点。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_triangle import neighbors as tri_neighbors  # noqa: E402


def point_in_poly(pt, poly, tol=0.0):
    """射线法；tol>0 时把「离边 tol 以内」也算命中（像素取整容差）。"""
    x, y = pt
    n = len(poly)
    inside = False
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        # 距离容差
        if tol:
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
            px, py = ax + t * dx, ay + t * dy
            if (x - px) ** 2 + (y - py) ** 2 <= tol * tol:
                return True
        if (ay > y) != (by > y):
            xin = ax + (y - ay) * (bx - ax) / (by - ay)
            if x < xin:
                inside = not inside
    return inside


def spill_pixels(gui, group_blocks, fill_rgb):
    """统计「填充色但不在任何完整多边形内」的像素数。"""
    view = gui._tri_view()
    polys = [view.piece_polygon(*tuple(b.location), inset=False)
             for b in group_blocks]
    polys = [[gui.world_to_screen(*p) for p in poly] for poly in polys]
    w, h = gui.screen.get_size()
    bad = []
    for y in range(h):
        for x in range(w):
            r, g, b, *_ = gui.screen.get_at((x, y))
            if abs(r - fill_rgb[0]) > 6 or abs(g - fill_rgb[1]) > 6 \
                    or abs(b - fill_rgb[2]) > 6:
                continue
            if not any(point_in_poly((x + 0.5, y + 0.5), poly, tol=2.0)
                       for poly in polys):
                bad.append((x, y))
    return bad


def main():
    gui = SliderGUI()
    gui.animation_enabled = False
    gui.new_triangle_puzzle(5, 2)
    cells = {tuple(b.location) for b in gui.game.blocks}
    seed = nbs = None
    for p in sorted(c for c in cells if c[2] is True):
        on = [n for n in map(tuple, tri_neighbors(p)) if n in cells]
        if len(on) == 3:
            seed, nbs = p, on
            break
    group = [seed, nbs[0], nbs[1]]
    pos = {tuple(b.location): b for b in gui.game.blocks}
    for b in pos.values():
        b.group = 0
    for c in group:
        pos[c].group = 1
        pos[c].be_opted = True      # 选中态 → 用 block_selected（绿），
        #                             与其它普通块（蓝）区分，溢出才好数
    gui.zoom = 3.0
    gui.draw_triangle_board()
    fill = gui.colors['block_selected']
    bad = spill_pixels(gui, [pos[c] for c in group], fill)
    print('组 =', group)
    print('溢出像素数 =', len(bad), bad[:8])
    # 裁剪放大看
    view = gui._tri_view()
    pts = [gui.world_to_screen(*view.piece_center(*c)) for c in group]
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    pad = 100
    box = pygame.Rect(int(min(xs)) - pad, int(min(ys)) - pad,
                      int(max(xs) - min(xs)) + 2 * pad,
                      int(max(ys) - min(ys)) + 2 * pad)
    box = box.clip(pygame.Rect(0, 0, *gui.screen.get_size()))
    sub = gui.screen.subsurface(box).copy()
    sub = pygame.transform.scale(sub, (sub.get_width() * 4, sub.get_height() * 4))
    out = os.path.join(os.path.dirname(__file__), '_probe_group_spill.png')
    pygame.image.save(sub, out)
    print('saved', out, box)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
