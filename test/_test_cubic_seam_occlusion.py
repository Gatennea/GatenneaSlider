# -*- coding: utf-8 -*-
"""切面预览的遮挡：**渲染出来的红像素**逐点回投到切面上验证。

为什么换掉上一版（用户 2026-11-18「縫隙遮擋關係還是不對，有時看起來像是切在
另一層」）：上一版渲染是「整张切面减影子多边形」，验证也围着那套解析影子转，
渲染错了验证跟着错。现在渲法改了——切面按 1 格大小切块塞进画家序，遮挡关系
由「格 vs 块面」的深度序给出。验证也就换成一条**与渲染完全独立**的路：

  屏幕上每一个偏红的像素 → 按正交投影反解出它在切面上的世界点 →
  用射线/盒子求交（cubic_view.point_visible）判断这个点该不该被块挡住。

判据
  A. 偏红像素**必须**是「沿视线没被任何块挡住」的点（0 个例外）。这一条直接对应
     用户看到的病：被遮住的区域还画出红边/红面。
  B. 红像素回投出来的世界点必须落在切面自身的范围内（不外扩到盘外）。
  C. 斜视 + 拆分 0.35 时必须真有一部分红露出来（不能「全挡了」）。
  D. 正视 + 拆分 0.12（前层挡死）时红面积占比必须很小（不能整片压出来）。
  E. 切面格子：都落在同一张平面上、格数 = 缝口有块的格数、互不重叠。
"""

import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame                                        # noqa: E402
from engine.cubic_camera import CubicCamera          # noqa: E402
from engine import cubic_view as cv                  # noqa: E402
from engine import cubic_pick as cp                  # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, extra=None):
    if cond:
        _ok[0] += 1
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg}' + (f'  {extra}' if extra else ''))


def _is_red(px):
    r, g, b = px[:3]
    return r > 70 and r - g > 35 and r - b > 10


def _plane_uv(sx, sy, camera, scale, origin, axis, fixed, a, b):
    """屏幕像素 → 切面上的 (u, v)。正交投影，两行基向量构成 2×2 线性方程组。"""
    rows = camera.rows()
    r0, r1 = rows[0], rows[1]
    m00, m01 = r0[a], r0[b]
    m10, m11 = r1[a], r1[b]
    det = m00 * m11 - m01 * m10
    if abs(det) < 1e-9:
        return None                    # 切面侧对屏幕：投影退化，不该有红像素
    rhs0 = (sx - origin[0]) / scale - r0[axis] * fixed
    rhs1 = (origin[1] - sy) / scale - r1[axis] * fixed
    u = (rhs0 * m11 - m01 * rhs1) / det
    v = (m00 * rhs1 - rhs0 * m10) / det
    return u, v


def main():
    from GUI import SliderGUI
    cfg = tempfile.mkdtemp()
    gui = SliderGUI(m=4, n=4, step=1)
    gui.config_dir = cfg
    gui.config_path = os.path.join(cfg, 'config.json')
    gui.temp_history_path = os.path.join(cfg, 'temp_history.json')
    gui.tutorial_active = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui._cubic_camera_prefs = {}
    gui.new_cubic_puzzle(3, 3, 3, 1)
    gui.show_virtual_keyboard = False

    print('A/B. 红像素必须真的没被挡 + 落在切面范围内')
    poses = [('正+Z', CubicCamera.from_yaw_pitch(0, 0)),
             ('斜 35/25', CubicCamera.from_yaw_pitch(35, 25)),
             ('斜 -40/30', CubicCamera.from_yaw_pitch(-40, 30)),
             ('斜 10/-35', CubicCamera.from_yaw_pitch(10, -35)),
             ('斜 60/15', CubicCamera.from_yaw_pitch(60, 15))]
    total_red = 0
    violations = []
    outside = []
    for gap in (0.12, 0.35):
        for fam, line in (('r', 1), ('c', 1), ('d', 1), ('r', 0), ('c', 0), ('d', 0)):
            for name, cam in poses:
                gui.cubic_camera = cam
                gui.cubic_gap = gap
                gui.selected_gap = (fam, line)
                gui.cubic_view_label = name
                gui.draw_cubic_board()
                scene = gui._cubic_scene
                view_dir = cam.view_axis()
                boxes = cv.block_boxes(gui.game.blocks, gap)
                axis = cp.FAMILY_TO_WORLD_AXIS[fam]
                fixed = float(line + 1)
                a, b = [i for i in range(3) if i != axis]
                # 切面自身的范围（格子拼起来的外框）
                cells = cp.seam_plane_cells(fam, line, gui.game.blocks, gap=gap)
                if not cells:
                    continue
                lo = [min(p[i] for quad, _c in cells for p in quad) for i in range(3)]
                hi = [max(p[i] for quad, _c in cells for p in quad) for i in range(3)]
                for quad, _c in cells:
                    for p in quad:
                        if abs(p[axis] - fixed) > 1e-9:
                            violations.append(f'{fam}{line}@{name} 格子不在切面上')
                step = 3
                for sy in range(0, gui.screen_height, step):
                    for sx in range(0, gui.screen_width, step):
                        if not _is_red(gui.screen.get_at((sx, sy))):
                            continue
                        total_red += 1
                        uv = _plane_uv(sx, sy, cam, scene['scale'],
                                       scene['origin'], axis, fixed, a, b)
                        if uv is None:
                            violations.append(f'{fam}{line}@{name} 有红但投影退化')
                            continue
                        u, v = uv
                        # 容差 = 抗锯齿渗出的几个像素：切面按 2× 超采样再缩回，
                        # 边上 1–2px 的过渡色会落在格线外一点点（约 0.02 格）。
                        tol = 0.05
                        if not (lo[a] - tol <= u <= hi[a] + tol
                                and lo[b] - tol <= v <= hi[b] + tol):
                            outside.append(f'{fam}{line}@{name} 红点({u:.2f},{v:.2f}) 出界')
                            continue
                        point = [0.0, 0.0, 0.0]
                        point[axis] = fixed
                        point[a] = u
                        point[b] = v
                        if not cv.point_visible(tuple(point), boxes, view_dir):
                            violations.append(
                                f'{fam}{line}@{name} gap{gap} 像素({sx},{sy})→'
                                f'({u:.2f},{v:.2f}) 其实被块挡住却画了红')
    check(not violations, f'所有红像素都在「没被挡」的位置（{len(violations)} 个例外）',
          violations[:3])
    check(not outside, f'红像素都在切面范围内（{len(outside)} 个出界）', outside[:3])
    check(total_red > 200, f'确实有红画出来（采样到 {total_red} 个红像素）')

    print('C. 斜视 + 拆分 0.35：必须真有一部分露出来')
    gui.cubic_gap = 0.35
    gui.cubic_camera = CubicCamera.from_yaw_pitch(35, 25)
    gui.selected_gap = ('r', 1)
    gui.draw_cubic_board()
    red_obl = 0
    for sy in range(0, gui.screen_height, 2):
        for sx in range(0, gui.screen_width, 2):
            if _is_red(gui.screen.get_at((sx, sy))):
                red_obl += 1
    check(red_obl > 50, f'斜视 0.35 下切面露出来（{red_obl} 个采样红点）')

    print('D. 正视 + 拆分 0.12：前层挡死，红占比必须很小')
    gui.cubic_gap = 0.12
    gui.cubic_camera = CubicCamera.from_yaw_pitch(0, 0)
    gui.selected_gap = ('r', 1)
    gui.draw_cubic_board()
    red_front = 0
    for sy in range(0, gui.screen_height, 2):
        for sx in range(0, gui.screen_width, 2):
            if _is_red(gui.screen.get_at((sx, sy))):
                red_front += 1
    sampled = (gui.screen_height // 2 + 1) * (gui.screen_width // 2 + 1)
    ratio = red_front / float(sampled)
    check(ratio < 0.02, f'正视下切面几乎全被挡住（红占比 {ratio * 100:.1f}%）')

    print('E. 切面格子几何')
    cells = cp.seam_plane_cells('r', 1, gui.game.blocks, gap=0.12)
    check(len(cells) == 9, f'3×3×3 的 r·1 有 9 格（实际 {len(cells)}）')
    axis = cp.FAMILY_TO_WORLD_AXIS['r']
    check(all(abs(p[axis] - 2.0) < 1e-9 for quad, _c in cells for p in quad),
          '每一格都在 z=2 这张平面上')
    areas = []
    for quad, _c in cells:
        # 有向面积（平面内两轴）
        a, b = [i for i in range(3) if i != axis]
        s = 0.0
        for i in range(len(quad)):
            p0, p1 = quad[i], quad[(i + 1) % len(quad)]
            s += p0[a] * p1[b] - p1[a] * p0[b]
        areas.append(abs(s) / 2.0)
    total_area = sum(areas)
    expect = (3.0 - 0.12) ** 2
    check(abs(total_area - expect) < 1e-6,
          f'九格拼起来正好是切面自身面积（{total_area:.4f}，应 {expect:.4f}）')
    check(all(0.7 < x <= 1.0 + 1e-9 for x in areas),
          f'单格面积不超过 1（最大 {max(areas):.4f}）')
    centers = [c for _q, c in cells]
    check(len(set(centers)) == len(centers), '格子中心互不重合')

    print('F. 切面是**一整张矩形平面**（2026-11-18 用户口径）')
    edge = 3.0 - 0.12
    rect = cp.seam_plane_rect('r', 1, gui.game.blocks, gap=0.12, dims=(3, 3, 3))
    a2, b2 = [i for i in range(3) if i != axis]
    span_a = max(p[a2] for p in rect) - min(p[a2] for p in rect)
    span_b = max(p[b2] for p in rect) - min(p[b2] for p in rect)
    check(len(rect) == 4, '四角', len(rect))
    check(abs(span_a - edge) < 1e-9 and abs(span_b - edge) < 1e-9,
          f'一张矩形覆盖整盘（{span_a:.2f}×{span_b:.2f}）')
    check(all(abs(p[axis] - 2.0) < 1e-9 for p in rect), '四角共面')
    # 打散后（只剩一个块）仍是整幅矩形，不跟着块堆缩水
    lone = cp.seam_plane_rect('r', 1, gui.game.blocks[:1], gap=0.12, dims=(3, 3, 3))
    check(abs((max(p[a2] for p in lone) - min(p[a2] for p in lone)) - edge) < 1e-9,
          '只剩一块时切面还是整幅矩形（不会缩成一小片）')

    print('=' * 60)
    if _fail:
        print(f'结果：{_ok[0]} 项通过，{len(_fail)} 项失败')
        for m in _fail:
            print('  ·', m)
        sys.exit(1)
    print(f'结果：全部通过（{_ok[0]} 项通过，0 项失败）')


if __name__ == '__main__':
    main()
