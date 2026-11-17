# -*- coding: utf-8 -*-
"""回归：三维「拆分」= 相邻块之间的渲染距离（§54 第 1 步）。

用户口径（2026-11-17）：「拆分的意思是兩個相鄰滑塊之間的距離，現在距離是 0，
就是完全未拆分。因為有拆分才能看遮擋關係。」

所以拆分是**渲染层的一个距离参数**（方案 §2.4「块按各自质心往外散」，滑条
留到渲染选项那一步），不是打乱棋局。本测试只钉投影层这条：

  A. gap=0（未拆分）：块贴死 → 实心 3×3×3 只有 27 个外表面，内部面照常剔除。
  B. gap>0（已拆分）：每个块缩成 (1-gap) 边长，相邻表面之间正好空出 gap；
     内部面不再剔除（缝里看得见）、面数随之增加；深度升序仍成立。
  C. 参数护栏：gap 必须在 [0,1)，越界显式 ValueError（不静默裁掉）。
  D. GUI：三维建局默认带一个非零拆分，整帧画得出来，拆分值进状态行。

跑法：D:/python/python.exe test/_test_cubic_gap.py
"""
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402

from engine.cubic_camera import CubicCamera  # noqa: E402
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
    return {(r, c, dep) for r in range(m) for c in range(n) for dep in range(d)}


CAM = CubicCamera.oblique_default()
CUBE3 = solid(3, 3, 3)

print('=' * 60)
print('A. gap=0：完全未拆分（贴死）')
faces0 = cv.collect_faces(CUBE3, CAM, scale=30.0, origin=(200.0, 200.0))
check(len(faces0) == 27, '实心 3×3×3 未拆分时只有 27 个外表面', len(faces0))
bar = {(0, 0, 0), (1, 0, 0)}
bar_faces = cv.collect_faces(bar, CubicCamera.identity(),
                            scale=30.0, origin=(100.0, 100.0))
check(len(bar_faces) == 1, '1×1×2 贴死时内部面被剔除，只剩 1 个前脸',
      len(bar_faces))

print('=' * 60)
print('B. gap>0：拆开，距离就是 gap')
GAP = 0.2
corners = cv.block_corners((0, 0, 0), GAP)
span = corners[1][0] - corners[0][0]
check(abs(span - (1.0 - GAP)) < 1e-12, '每块缩成 1-gap 边长', span)
a_max = cv.block_min_corner((0, 1, 0), GAP)[0]     # 右邻块的最小 x
b_min = cv.block_min_corner((0, 0, 0), GAP)[0] + (1.0 - GAP)  # 本块的最大 x
check(abs((a_max - b_min) - GAP) < 1e-12,
      '相邻两块表面之间的距离 = gap', a_max - b_min)

faces_gap = cv.collect_faces(CUBE3, CAM, scale=30.0, origin=(200.0, 200.0),
                             gap=GAP)
check(len(faces_gap) > 27, '拆开后露出缝里的面（面数 > 27）', len(faces_gap))
check(len(faces_gap) == 81, '斜视下每块 3 个可见面 × 27 块 = 81', len(faces_gap))
check(any(cv.neighbor_location(f['loc'], f['axis'], f['sign'])
          in CUBE3 for f in faces_gap),
      '内部面不再被剔除（缝里看得见）')
check(faces_gap == sorted(faces_gap, key=lambda f: f['depth']),
      '拆开后深度升序（远先近后）仍成立')

# 正对时侧面法向⊥视线仍被剔除，但 27 块各露一个正脸（前后重叠由画家算法处理）
front = cv.collect_faces(CUBE3, CubicCamera.identity(), scale=30.0,
                         origin=(200.0, 200.0), gap=GAP)
check(len(front) == 27, '正视拆开态：27 块各一个正脸', len(front))

print('=' * 60)
print('C. 参数护栏')
for bad in (-0.1, 1.0, 1.5):
    try:
        cv.block_min_corner((0, 0, 0), bad)
        check(False, f'gap={bad} 应报 ValueError')
    except ValueError:
        check(True, f'gap={bad} → ValueError（不静默裁剪）')

print('=' * 60)
print('D. GUI：默认带拆分，整帧可画')
from GUI import SliderGUI  # noqa: E402

pygame.init()
gui = SliderGUI(m=4, n=4, step=1)
gui.tut_show_prompt = False
gui.tutorial_active = False
# 隔离配置目录：测试不许碰仓库里那份 config/temp_history.json（会污染开局形态）
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_gap_')
gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
gui._readonly = False
gui.save_readonly_flag = False
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()

# 上次的三维相机存档（config.json 的 cubic_camera）会覆盖默认拆分；
# 这里要验「默认值」，先清掉那组偏好再建局。
gui._cubic_camera_prefs = {}
gui.new_cubic_puzzle(3, 3, 3, 1)
check(0.0 < gui.cubic_gap < 1.0, '三维建局默认带非零拆分', gui.cubic_gap)
check(abs(gui.cubic_gap - cv.DEFAULT_GAP) < 1e-12, '默认值取自 cubic_view.DEFAULT_GAP')
gui.draw_board()
check(True, '带拆分的整帧绘制不抛异常')

_probe = {}
for _y in range(0, gui.screen_height, 5):
    for _x in range(0, gui.screen_width, 5):
        _c = gui.screen.get_at((_x, _y))[:3]
        _probe[_c] = _probe.get(_c, 0) + 1
check(any(c == gui.colors['background'] for c in _probe),
      '拆开后背景透得出来（缝隙真的画出来了）')
check(len([c for c, n in _probe.items() if n > 200]) >= 3,
      '三面明暗仍在')

# 把拆分拉到 0：同一局应回到「27 个外表面」的贴死形态，且不崩
gui.cubic_gap = 0.0
gui.draw_board()
check(True, '拆分拉到 0 后仍能画（不崩、不报错）')
gui.cubic_gap = cv.DEFAULT_GAP

print('=' * 60)
print(f'结果：{"全部通过" if not _fail else "有失败"}（{_ok[0]} 项通过，'
      f'{len(_fail)} 项失败）')
if _fail:
    for msg in _fail:
        print('  - ' + msg)
sys.exit(1 if _fail else 0)
