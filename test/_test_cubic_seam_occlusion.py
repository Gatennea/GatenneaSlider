# -*- coding: utf-8 -*-
"""切面预览的遮挡：解析影子多边形 vs 逐点射线，两种独立方法互证。

为什么单独立一个文件（用户 2026-11-18「你验证的不充分啊，有的时候这个遮挡画得
毛毛糙糙的」）：
  · 之前只靠肉眼截图验收，采样法的锯齿、投影方向写反都漏在截图里；
  · 切面的可见性有两条完全独立的算法——(1) 逐点沿视线做射线/盒子求交（精确但只能
    逐点求值）；(2) 把每个块的 AABB 沿视线投到切面上求凸包再用多边形扣掉（渲染实际
    用的那条）。两条在这个尺度上必须逐点一致，不一致就是渲染在骗人。

判据
  A. 6 个相机姿态 × 3 个切面族 × 2 条缝 × 2 种拆分 = 72 组，每组 20×20 采样点，
     两条算法逐点一致（允许 0 个不一致）。
  B. 正视 + 拆分 0.12：平行屏幕的 r·1 切面整片在块内部 → 可见点占比必须很小
     （旧版会整片画出来，这条能抓住回潮）。
  C. 斜视 + 拆分 0.35：同一条切面必须真有一部分露出来（否则就是「全挡了」——
     说明影子算多了，也同样不对）。
  D. 影子多边形必须都是凸的、顶点数 ≤ 8（AABB 沿视线投影最多六边形）。
"""

import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.cubic_camera import CubicCamera          # noqa: E402
from engine import cubic_view as cv                  # noqa: E402
from engine import cubic_pick as cp                  # noqa: E402
from engine.adapter import create_adapter_puzzle     # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, extra=None):
    if cond:
        _ok[0] += 1
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg}' + (f'  {extra}' if extra else ''))


def in_poly2d(x, y, hull):
    """点在凸/凹简单多边形内（射线交叉计数）。"""
    res = False
    n = len(hull)
    for i in range(n):
        ax, ay = hull[i]
        bx, by = hull[(i + 1) % n]
        if (ay > y) != (by > y):
            xin = (bx - ax) * (y - ay) / (by - ay) + ax
            if x < xin:
                res = not res
    return res


def _plane_samples(poly, axis, others, n):
    lo = [min(p[i] for p in poly) for i in others]
    hi = [max(p[i] for p in poly) for i in others]
    step = [(hi[k] - lo[k]) / float(n) for k in range(2)]
    fixed = poly[0][axis]
    for i in range(n):
        for j in range(n):
            pt = [0.0, 0.0, 0.0]
            pt[axis] = fixed
            pt[others[0]] = lo[0] + step[0] * (i + 0.5)
            pt[others[1]] = lo[1] + step[1] * (j + 0.5)
            yield tuple(pt)


game = create_adapter_puzzle('cubic', 3, 3, 1, depth=3)
CAMS = (
    ('front', CubicCamera.from_yaw_pitch(0.0, 0.0)),
    ('obl+', CubicCamera.from_yaw_pitch(14.0, -14.0)),
    ('obl-', CubicCamera.from_yaw_pitch(-14.0, 14.0)),
    ('tilt45', CubicCamera.from_yaw_pitch(32.0, -24.0)),
    ('tilt90', CubicCamera.from_yaw_pitch(60.0, -55.0)),
    ('tilt120', CubicCamera.from_yaw_pitch(-70.0, 40.0)),
)

print('A. 解析影子 vs 逐点射线：逐点一致')
total = 0
mismatch = 0
first_bad = None
for gap in (0.12, 0.35):
    boxes = cv.block_boxes(game.blocks, gap)
    for fam in ('r', 'c', 'd'):
        for line in (0, 1):
            poly = cp.seam_plane_polygon(fam, line, game.blocks, gap=gap)
            for name, cam in CAMS:
                view = cam.view_axis()
                shadows, axis = cv.seam_shadow_polygons(poly, boxes, view)
                if shadows is None:                 # 近乎侧对，走采样兜底
                    continue
                others = [i for i in range(3) if i != axis]
                hulls2d = [[(p[others[0]], p[others[1]]) for p in s]
                           for s in shadows]
                for pt in _plane_samples(poly, axis, others, 20):
                    total += 1
                    vis_ray = cv.point_visible(pt, boxes, view)
                    vis_shadow = not any(in_poly2d(pt[others[0]], pt[others[1]], h)
                                         for h in hulls2d)
                    if vis_ray != vis_shadow:
                        mismatch += 1
                        if first_bad is None:
                            first_bad = (gap, fam, line, name, pt, vis_ray, vis_shadow)
check(mismatch == 0,
      f'两种遮挡算法在 {total} 个采样点上逐点一致（不一致 {mismatch}）',
      extra=str(first_bad))

print('B. 正视下面向相机的整层块一个都不能被「看穿」')
gap = 0.12
boxes = cv.block_boxes(game.blocks, gap)
front = CubicCamera.from_yaw_pitch(0.0, 0.0)
poly = cp.seam_plane_polygon('r', 1, game.blocks, gap=gap)
shadows, axis = cv.seam_shadow_polygons(poly, boxes, front.view_axis())
others = [i for i in range(3) if i != axis]
visible = 0


def _covered(x, y):
    """(x, y) 这一点正上方有没有 r=2 那一层的块（有 = 挡住了）。"""
    from engine import cubic_view as _cv
    for box in boxes:
        if (box[0] - 1e-9 <= x <= box[3] + 1e-9
                and box[1] - 1e-9 <= y <= box[4] + 1e-9
                and box[5] >= 2.0):
            return True
    return False


for pt in _plane_samples(poly, axis, others, 24):
    if cv.point_visible(pt, boxes, front.view_axis()):
        visible += 1
        check(not _covered(pt[others[0]], pt[others[1]]),
              f'正视可见点 {tuple(round(v, 2) for v in pt)} 必须是落在缝里的（上方有块就不该可见）')
check(visible <= 0.25 * 576,
      f'正视 r·1 可见采样点 {visible}/576 只该是缝里那点面积（≤144）')

print('C. 斜视 + 大拆分下同一条切面必须真露出来')
gap = 0.35
boxes = cv.block_boxes(game.blocks, gap)
obl = CubicCamera.from_yaw_pitch(32.0, -24.0)
visible = sum(1 for pt in _plane_samples(poly, axis, others, 24)
              if cv.point_visible(pt, boxes, obl.view_axis()))
check(visible > 0, f'斜视 + 拆分 0.35 时 r·1 可见采样点 {visible}/576（不该是 0）')

print('D. 影子多边形是凸的、顶点数合理')
for gap in (0.12, 0.35):
    boxes = cv.block_boxes(game.blocks, gap)
    for fam in ('r', 'c', 'd'):
        for line in (0, 1):
            poly = cp.seam_plane_polygon(fam, line, game.blocks, gap=gap)
            shadows, axis = cv.seam_shadow_polygons(
                poly, boxes, CubicCamera.from_yaw_pitch(14.0, -14.0).view_axis())
            if shadows is None:
                continue
            others = [i for i in range(3) if i != axis]
            for hull in shadows:
                check(3 <= len(hull) <= 8,
                      f'{fam}·{line} gap={gap} 影子顶点数 {len(hull)} 在 3..8')

print('E. 像素级互证：渲染出来的切面蒙版 vs 每个像素中心反投影后的精确可见性')
# 这一条是「验证不充分」的直接回应：不看截图，逐像素对账。做法是把屏幕像素中心
# 反投影回切面平面（screen = origin + scale*(vx,-vy)，世界 w = t·z + vx·right +
# vy·up，用 w[axis]=切面坐标解 t），每个像素做一次精确射线判定，再读渲染实际贴上
# 的半透明图层 alpha 比。只判 3×3 邻域期望一致的「内部像素」，边缘一圈留给抗锯齿。
import tempfile                                        # noqa: E402
import pygame                                          # noqa: E402
from GUI import SliderGUI                              # noqa: E402


def _pixel_compare(seam, label):
    cfg = tempfile.mkdtemp()
    gui = SliderGUI()
    gui.config_dir = cfg
    gui.config_path = os.path.join(cfg, 'config.json')
    gui.temp_history_path = os.path.join(cfg, 'temp_history.json')
    gui.cubic_zoom = 1.4
    gui.new_cubic_puzzle(3, 3, 3, 1)
    gui.cubic_gap = 0.30
    gui._cubic_view(0)
    gui.selected_gap = seam
    gui.draw_right_panel()
    gui.draw_cubic_board()
    scene = gui._cubic_scene
    cam = gui.cubic_camera
    boxes = cv.block_boxes(gui.game.blocks, gui.cubic_gap)
    poly = cp.seam_plane_polygon(seam[0], seam[1], gui.game.blocks,
                                 gap=gui.cubic_gap)
    axis = {'r': 2, 'c': 0, 'd': 1}[seam[0]]
    others = [i for i in range(3) if i != axis]
    fixed = poly[0][axis]
    pts2d = [cv.project_point(w, cam, scene['scale'], scene['origin'])[:2]
             for w in poly]
    x0 = int(min(p[0] for p in pts2d)) - 1
    x1 = int(max(p[0] for p in pts2d)) + 1
    y0 = int(min(p[1] for p in pts2d)) - 1
    y1 = int(max(p[1] for p in pts2d)) + 1
    s = scene['scale']
    ox, oy = scene['origin']
    right, up, zax = cam.rows()
    lo = [min(p[i] for p in poly) for i in others]
    hi = [max(p[i] for p in poly) for i in others]
    mask = []
    for y in range(y0, y1 + 1):
        row = []
        for x in range(x0, x1 + 1):
            vx, vy = (x - ox) / s, -(y - oy) / s
            denom = zax[axis]
            if abs(denom) < 1e-6:
                row.append(False)
                continue
            t = (fixed - vx * right[axis] - vy * up[axis]) / denom
            w = (t * zax[0] + vx * right[0] + vy * up[0],
                 t * zax[1] + vx * right[1] + vy * up[1],
                 t * zax[2] + vx * right[2] + vy * up[2])
            if not (lo[0] - 1e-9 <= w[others[0]] <= hi[0] + 1e-9
                    and lo[1] - 1e-9 <= w[others[1]] <= hi[1] + 1e-9):
                row.append(False)
            else:
                row.append(cv.point_visible(w, boxes, zax))
        mask.append(row)

    shadows, _a = cv.seam_shadow_polygons(poly, boxes, zax)
    quad_pts = pts2d
    shadow_pts = [[cv.project_point(w, cam, scene['scale'],
                                   scene['origin'])[:2] for w in h]
                  for h in (shadows or [])]
    layer, pos = gui._cubic_seam_layer(quad_pts, shadow_pts)
    lw, lh = layer.get_size()
    bad = []
    interior = 0
    for j in range(1, len(mask) - 1):
        for i in range(1, len(mask[0]) - 1):
            nb = [mask[j + dj][i + di] for dj in (-1, 0, 1) for di in (-1, 0, 1)]
            if any(b != nb[0] for b in nb):
                continue
            interior += 1
            x, y = x0 + i, y0 + j
            alpha = 0
            if 0 <= x - pos[0] < lw and 0 <= y - pos[1] < lh:
                alpha = layer.get_at((x - pos[0], y - pos[1]))[3]
            if (nb[0] and alpha < 40) or ((not nb[0]) and alpha > 200):
                bad.append((x, y, nb[0], alpha))
    check(len(bad) == 0,
          f'{label} 逐像素一致（内部像素 {interior}，不一致 {len(bad)}）',
          extra=str(bad[:3]))


_pixel_compare(('r', 1), '像素级 斜视 r·1')
_pixel_compare(('d', 1), '像素级 斜视 d·1')

print('=' * 60)
if _fail:
    print(f'结果：{_ok[0]} 项通过，{len(_fail)} 项失败')
    sys.exit(1)
else:
    print(f'结果：全部通过（{_ok[0]} 项通过，0 项失败）')
