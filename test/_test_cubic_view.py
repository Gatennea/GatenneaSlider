# -*- coding: utf-8 -*-
"""回归：三维投影层与相机姿态（§54 第 1 步「能画出来」）。

方案真源 `docs/spec/三维扩展方案_正方体单元_2026-11-17.md` §2.1/§2.2、§6 第 1 条：
几个立方体摆成长方体，从标准视角渲染，**前块挡后块、三面可见、凹坑可见**。
这步不过后面全是空中楼阁，所以先用可判定的几何性质钉住投影层：

  A. 相机：六正对视角的 z 轴就是六个世界轴；identity 正对 +Z；斜视姿态「没正对」；
     最近正对视角吸附正确；slerp 端点稳定。
  B. 可见面：实心 3×3×3 正对一面时恰好 9 个面（全是被看的那一面）；
     斜视（三面朝观察者）时恰好 27 个；顶视图朝上的是 +Y 面。
  C. 内部面与背面：1×1×2 竖排时只有 9 个面、且不含背面（内部面被吃掉）。
  D. 遮挡顺序：正对时前一层的所有面都排在后一层之后（画家算法「远先近后」）。
  E. 投影几何：单块正面是边长 = scale 的正方形；屏幕上 y 向下（+Y 在上方）。

跑法：D:/python/python.exe test/_test_cubic_view.py
"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

from engine.cubic_camera import CubicCamera, FACE_BASIS  # noqa: E402
from engine import cubic_view as cv  # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg} {extra}')
    return bool(cond)


def solid(m, n, d):
    """实心 m×n×d 的位置集合（r, c, d 三元组，裸元组输入）。"""
    return {(r, c, dep) for r in range(m) for c in range(n) for dep in range(d)}


print('=' * 60)
print('A. 相机姿态')

views = CubicCamera.face_views()
check(len(views) == 6, '六正对视角')
for i, cam in enumerate(views):
    z = cam.view_axis()
    want = FACE_BASIS[i][2]
    check(all(abs(a - b) < 1e-9 for a, b in zip(z, want)),
          f'第 {i} 个视角 z 轴 = {want}', z)
    check(cam.is_axis_aligned(), f'第 {i} 个视角是正对姿态')

check(CubicCamera.identity().is_axis_aligned(), 'identity 是正对姿态')
check(CubicCamera.identity().view_axis() == (0.0, 0.0, 1.0),
      'identity 正对 +Z（从 r 增大一侧看）')

obl = CubicCamera.oblique_default()
check(not obl.is_axis_aligned(), '默认斜视不是正对姿态')
snap = obl.nearest_face_view()
check(snap.is_axis_aligned() and snap.view_axis()[2] > 0.9,
      '斜视吸附回「正面」', snap.view_axis())

mid = views[0].slerp(views[2], 0.5)
check(abs(sum(a * b for a, b in zip(mid.q, mid.q)) - 1.0) < 1e-9,
      'slerp 结果仍是单位四元数')
check(views[0].slerp(views[2], 0.0).view_axis() == views[0].view_axis(),
      'slerp t=0 保持起点')
dot_end = sum(a * b for a, b in
              zip(views[0].slerp(views[2], 1.0).q, views[2].q))
check(abs(dot_end) > 0.999, 'slerp t=1 到终点（允许反号等价）')

print('=' * 60)
print('B. 可见面数量（正对 / 斜视）')

front = CubicCamera.identity()
cube = solid(3, 3, 3)
faces = cv.collect_faces(cube, front, scale=30.0, origin=(100.0, 100.0))
check(len(faces) == 9, '正对看得见的那一面：9 个面（3×3）', len(faces))
check(all(f['axis'] == 2 and f['sign'] == 1 for f in faces),
      '正对时全是 +Z 面（其余被背面剔除）')

top = views[4]
faces_top = cv.collect_faces(cube, top, scale=30.0, origin=(100.0, 100.0))
check(len(faces_top) == 9, '顶视图 9 个面', len(faces_top))
check(all(f['axis'] == 1 and f['sign'] == 1 for f in faces_top),
      '顶视图朝上的是 +Y 面')

faces_obl = cv.collect_faces(cube, obl, scale=30.0, origin=(100.0, 100.0))
check(len(faces_obl) == 27, '斜视三面朝观察者：27 个面', len(faces_obl))
axes = {f['normal'] for f in faces_obl}
check(len(axes) == 3 and all(sum(v for v in n) > 0.5 for n in axes),
      '斜视只露三个「正号」法向', axes)

print('=' * 60)
print('C. 内部面 / 背面')

bar = {(0, 0, 0), (1, 0, 0)}
faces_bar = cv.collect_faces(bar, front, scale=30.0, origin=(100.0, 100.0))
check(len(faces_bar) == 1, '1×1×2 正对时只剩前脸 1 个面'
      '（侧面法向⊥视线全被剔除）', len(faces_bar))
check(faces_bar[0]['loc'] == (1, 0, 0) and faces_bar[0]['sign'] == 1,
      '留下的是前块（r 大）的 +Z 面', faces_bar[0]['loc'])
check(not any(f['axis'] == 2 and f['sign'] == -1 for f in faces_bar),
      '背面（-Z）被剔除')
check(not any(f['loc'] == (0, 0, 0) for f in faces_bar),
      '后块一片都不画（前脸是内部面、其余被剔除）')

print('=' * 60)
print('D. 遮挡顺序（画家算法：远先近后）')

# 两块沿 r 隔一格摆（不共面）：正对时完全重叠，前块必须后画才能挡住后块
stack = {(0, 0, 0), (2, 0, 0)}
faces_stack = cv.collect_faces(stack, front, scale=40.0, origin=(100.0, 100.0))
rear = [f for f in faces_stack if f['loc'] == (0, 0, 0)]
near = [f for f in faces_stack if f['loc'] == (2, 0, 0)]
check(len(rear) == 1 and len(near) == 1, '两块各露一个正脸',
      (len(rear), len(near)))
check(min(f['depth'] for f in near) > max(f['depth'] for f in rear),
      '前块（r=2）比后块（r=0）近', (rear[0]['depth'], near[0]['depth']))
check(faces_stack[0]['loc'] == (0, 0, 0),
      '排序：后块先画', [f['loc'] for f in faces_stack])
check(all(abs(a - b) < 1e-6
          for pa, pb in zip(rear[0]['pts'], near[0]['pts'])
          for a, b in ((pa[0], pb[0]), (pa[1], pb[1]))),
      '两块正脸投影完全重叠（正是「前挡后」的场景）')
check(faces_stack == sorted(faces_stack, key=lambda f: f['depth']),
      'collect_faces 自己就按深度升序返回')

print('=' * 60)
print('E. 投影几何')

single = {(0, 0, 0)}
scale, origin = 40.0, (100.0, 100.0)
f0 = cv.collect_faces(single, front, scale=scale, origin=origin)
check(len(f0) == 1 and f0[0]['axis'] == 2, '单块正对只画 1 个面', f0)
pts = f0[0]['pts']
side_x = abs(pts[1][0] - pts[0][0])
side_y = abs(pts[2][1] - pts[1][1])
check(abs(side_x - scale) < 1e-6 and abs(side_y - scale) < 1e-6,
      '正面被投成 scale 边长的正方形', (side_x, side_y))

# 顶视图（+Y 朝观察者）时，Y 轴朝屏幕里，屏幕上的「上」是 -Z；用底面块验证
# 「世界 y 越大 → 屏幕 y 越小」这条映射（相机 y 轴 = 屏幕向上）。
up_cam = CubicCamera.identity()
a = cv.project_point((0.0, 0.0, 0.0), up_cam, scale, origin)
b = cv.project_point((0.0, 1.0, 0.0), up_cam, scale, origin)
check(a[1] > b[1], '世界 y 增大 → 屏幕 y 减小（y 轴向下）', (a, b))
check(a[2] == 0.0 and b[2] == 0.0, '正对时同一 Z 面深度相同')

scene = cv.build_scene(cube, front, 640, 480)
check(scene['block_count'] == 27, 'scene 报块数 27', scene['block_count'])
check(len(scene['faces']) == 9 and scene['scale'] > 0, 'build_scene 装进画面')

print('=' * 60)
print(f'结果：{"全部通过" if not _fail else "有失败"}（{_ok[0]} 项通过，'
      f'{len(_fail)} 项失败）')
if _fail:
    for msg in _fail:
        print('  - ' + msg)
sys.exit(1 if _fail else 0)
