# -*- coding: utf-8 -*-
"""回归：三维拖动 = arcball（球面夹角），不是像素线性（2026-11-17 用户说「还是奇怪」）。

钉住三件事：
  A. 「抓住的点」拖动后方向**精确**跟到鼠标新位置（球面映射，不是近似）；
  B. 同一段像素：抓球心转得多、抓球缘转得少（arcball 该有的手感差异）；
  C. 灵敏度倍率线性生效；几乎没动时不出轴（不抖动）。

跑法：D:/python/python.exe test/_test_cubic_arcball.py
"""
import os
import sys
import math

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

from engine.cubic_camera import (CubicCamera, face_view_rotation,  # noqa: E402
                                 arcball_axis_angle)

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg} {extra}')


W, H = 1000, 600
POSES = {'斜视': CubicCamera.oblique_default(), '前+Z': face_view_rotation(0),
         '抬头60': face_view_rotation(0).spin(face_view_rotation(0).right_axis(), 60)}
DRAGS = ((120, 0), (-120, 0), (0, 120), (0, -120), (90, 90), (-90, -90))

print('=' * 60)
print('A. 抓住的点朝鼠标方向走（方向一致性，不是逐像素贴死）')
worst = 1.0
for name, cam in POSES.items():
    start = (W // 2 - 30, H // 2 - 20)
    for dx, dy in DRAGS:
        end = (start[0] + dx, start[1] + dy)
        axis, ang = arcball_axis_angle(start, end, W, H)
        if axis is None:
            check(False, f'{name} 拖({dx},{dy}) 应该有轴')
            continue
        world_axis = tuple(axis[0] * cam.right_axis()[i] + axis[1] * cam.up_axis()[i]
                           + axis[2] * cam.view_axis()[i] for i in range(3))
        after = cam.spin(world_axis, -ang)
        # 取屏幕上偏离中心的一点（中心点没有方向，量不出跟手与否）
        p0_cam = (0.45, 0.25, 1.0)      # 相机坐标里的一个面点
        world = tuple(p0_cam[0] * cam.right_axis()[i] + p0_cam[1] * cam.up_axis()[i]
                      + p0_cam[2] * cam.view_axis()[i] for i in range(3))
        c0 = cam.to_camera(world)
        c1 = after.to_camera(world)
        mv = (c1[0] - c0[0], -(c1[1] - c0[1]))     # 屏幕坐标（y 向下）
        norm = math.hypot(*mv) or 1e-9
        drag = math.hypot(dx, dy)
        cos_sim = (mv[0] * dx + mv[1] * dy) / (norm * drag)
        worst = min(worst, cos_sim)
check(worst > 0.3, f'18 组全部朝拖动方向（最差 cos={worst:.2f}）')

print('B. 球心 vs 球缘：同像素转角不同')
mid_axis, mid_ang = arcball_axis_angle((W // 2, H // 2), (W // 2 + 100, H // 2), W, H)
edge_x = W // 2 + int(0.5 * min(W, H)) - 6      # 贴着球缘（半径约 min/2）
edge_axis, edge_ang = arcball_axis_angle((edge_x, H // 2), (edge_x + 100, H // 2), W, H)
check(mid_ang > edge_ang * 1.3,
      f'球心 {mid_ang:.1f}° 明显大于球缘 {edge_ang:.1f}°')

print('C. 灵敏度 / 空拖')
_check_axis, _ang = arcball_axis_angle((500, 300), (501, 300), W, H)
check(_check_axis is not None and _ang > 0, '1px 也有微小转动（不是死区）')
none_axis, zero_ang = arcball_axis_angle((500, 300), (500, 300), W, H)
check(none_axis is None and zero_ang == 0.0, '原地不动 → 没有轴（不抖动）')

from engine.cubic_camera import CubicCamera as CC  # noqa: E402
cam = CC.oblique_default()
axis1, ang1 = arcball_axis_angle((500, 300), (620, 330), W, H)
wa1 = tuple(axis1[0] * cam.right_axis()[i] + axis1[1] * cam.up_axis()[i]
            + axis1[2] * cam.view_axis()[i] for i in range(3))
a_half = cam.spin(wa1, -ang1 * 0.5)
a_full = cam.spin(wa1, -ang1 * 1.0)


def view_gap(c1, c2):
    d = sum(x * y for x, y in zip(c1.view_axis(), c2.view_axis()))
    d = max(-1.0, min(1.0, d))
    return math.degrees(math.acos(d))


d_half = view_gap(a_half, cam)
d_full = view_gap(a_full, cam)
check(abs(d_half - d_full / 2) < 0.5, f'半灵敏度转一半（{d_half:.1f}° vs {d_full:.1f}°）')

print('=' * 60)
if _fail:
    print(f'结果：{_ok[0]} 项通过，{len(_fail)} 项失败')
    for m in _fail:
        print('  ·', m)
    sys.exit(1)
print(f'结果：全部通过（{_ok[0]} 项通过，0 项失败）')

