# -*- coding: utf-8 -*-
"""设计态（自由捆绑 + 自定义样式）无头测试。

锁的事：
  · 构造画布上点两个已有滑块 = 沿路径捆绑（引擎 group 落到 Block）
  · 再点组内滑块 = 整组解绑；ESC 取消待配对第一点
  · 保存样式：JSON 落盘 + 冻形拦截（3×3 L 形零合法移动，拒绝保存）
  · 样式开局：goal_pattern 设置 + D4 八变换判定（旋转/翻面都算还原）
  · 构造取消/清空/重置时设计态一并不残留
"""
import os
import queue
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from gui import design_styles  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


def key_down(key, mod=0, unicode=''):
    pygame.event.post(pygame.event.Event(
        pygame.KEYDOWN, key=key, mod=mod, unicode=unicode, scancode=0))


def click(pos, button=1):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=button, pos=pos))


gui = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                ext_state={'enabled': True, 'token': 'T', 'port': 5050})
gui.tut_show_prompt = False
gui.tutorial_active = False

# 清理可能残留的测试样式
for nm in ('_测试样式', '_冻形'):
    design_styles.delete_style(gui.config_dir, nm)


def enter_build():
    """进创造模式 → 手动构造画布。"""
    gui.game_mode = 'create'
    gui._ann_sub_dialog = 'build'
    gui._ann_view = 'build'
    gui._ann_build_fields = {'m': '4', 'n': '4', 'step': '1'}
    gui._ann_build_numbered = False
    gui._ann_build_coords = set()
    gui._ann_build_error = ''
    gui._ann_design_reset()
    gui._ann_rebuild_game_from_coords()


def place(coords):
    for p in coords:
        if p not in gui._ann_build_coords:
            gui._ann_build_toggle(p)
    gui._ann_rebuild_game_from_coords()


# ---------------------------------------------------------------- 捆绑/解绑
print('--- 设计态：捆绑与解绑 ---')
enter_build()
place([(0, 0), (0, 1), (0, 2), (1, 0)])

gui._ann_design_bind_active = True
gui._ann_design_click((0, 0))          # 第一点
check('D1a 第一点进入待配对', gui._ann_design_bind_first == (0, 0))
gui._ann_design_click((0, 2))          # 第二点 → 路径捆绑
check('D1b 两点路径捆绑成一组',
      len(set(gui._ann_design_groups.values())) == 1
      and len(gui._ann_design_groups) == 3,
      f'{gui._ann_design_groups}')
check('D1c 捆绑落到 Block.group',
      all(b.group for b in gui.game.blocks
          if tuple(b.location) in {(0, 0), (0, 1), (0, 2)}),
      f'{[b.group for b in gui.game.blocks]}')

# ESC 取消待配对第一点
gui._ann_design_click((1, 0))          # 新第一点
key_down(pygame.K_ESCAPE)
gui._ann_build_dialog_event(
    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0,
                       unicode='', scancode=0))
check('D1d ESC 取消待配对第一点', gui._ann_design_bind_first is None)

# 点组内滑块 = 解绑整组
gui._ann_design_click((0, 1))
check('D1e 点组内滑块整组解绑', gui._ann_design_groups == {})

# 不连通两点不可捆（中间空位）
place([(0, 0), (2, 2)])
gui._ann_design_bind_first = None
gui._ann_design_click((0, 0))
gui._ann_design_click((2, 2))
check('D1f 不连通两点拒绝捆绑', gui._ann_design_groups == {})

# 捆绑工具关时点击 = 正常增删滑块
gui._ann_design_bind_active = False
n_before = len(gui._ann_build_coords)
gui._ann_build_toggle((3, 3))
check('D1g 工具关闭时点击照常增删',
      len(gui._ann_build_coords) == n_before + 1)

# ---------------------------------------------------------------- 样式存取
print('\n--- 设计态：样式保存与冻形拦截 ---')
enter_build()
place([(0, 0), (0, 1), (0, 2), (1, 0), (2, 0)])   # L 形（3×3 冻形）
gui._ann_design_style_name = '_冻形'
gui._ann_design_save_style()
check('D2a 冻形拒绝保存（L 形 3×3 零合法移动）',
      design_styles.load_style(gui.config_dir, '_冻形') is None
      and '冻形' in (gui._ann_build_error or ''))

enter_build()
place([(0, 0), (0, 1), (0, 2), (1, 0), (2, 0), (1, 1), (2, 1)])  # 可动棋形
gui._ann_design_bind_active = True
gui._ann_design_click((0, 0))
gui._ann_design_click((1, 0))
gui._ann_design_bind_active = False
gui._ann_design_style_name = '_测试样式'
gui._ann_design_save_style()
data = design_styles.load_style(gui.config_dir, '_测试样式')
check('D2b 可动棋形保存成功', data is not None)
if data:
    check('D2c 样式含捆绑', len(data.get('groups', {})) == 2,
          f"{data.get('groups')}")
    check('D2d 样式 cells 数正确', len(data['cells']) == 7)

# ---------------------------------------------------------------- 样式开局
print('\n--- 设计态：样式开局与 D4 判定 ---')
gui._ann_design_start_style('_测试样式')
# 无头环境主循环不推帧：演示动画停在「视觉=打乱前」，先把演示推到终态
# （与 _test_triangle_render/_test_numbered_p2 同一模式）
if getattr(gui, '_shuffle_demo_final', None) is not None:
    gui._finish_shuffle_demo()
check('D3a 开局后设置 goal_pattern', gui.game.goal_pattern is not None)
check('D3b 打乱后非还原态', not gui.game.is_solved())
check('D3c 标记样式目标局', gui._ann_style_goal == '_测试样式')
fit = gui.game.pattern_fit()
check('D3d 打乱强度达标（fit ≤ 0.75）', fit <= 0.75, f'fit={fit:.2f}')

# D4：把盘面摆成样式的旋转像 → 算还原
cells = sorted(gui.game.goal_pattern)
h = max(r for r, _ in cells)
w = max(c for _, c in cells)
rotated = {(c, h - r) for r, c in cells}
gui.game.apply_pattern(sorted(rotated))
check('D3e 旋转 90° 算还原（八变换判定）', gui.game.is_solved())

# 换常规新谜题 → goal 清空（默认矩形判定）
gui.new_puzzle(4, 4, 1)
check('D3f 新谜题清空自定义目标',
      gui.game.goal_pattern is None and gui._ann_style_goal is None)

# ---------------------------------------------------------------- 状态清理
print('\n--- 设计态：取消/清空不残留 ---')
enter_build()
place([(0, 0), (0, 1), (1, 0)])
gui._ann_design_bind_active = True
gui._ann_design_click((0, 0))
gui._ann_design_click((1, 0))
n_groups = len(set(gui._ann_design_groups.values()))
gui._ann_build_clear()
check('D4a 清空画布连带清捆绑', n_groups == 1
      and gui._ann_design_groups == {})

enter_build()
place([(0, 0), (0, 1)])
gui._ann_design_bind_active = True
gui._ann_design_click((0, 0))
gui._ann_design_click((0, 1))
gui._ann_build_cancel()
check('D4b 取消构造清设计态',
      gui._ann_design_groups == {}
      and gui._ann_design_bind_active is False
      and gui._ann_view == 'home')

# 测试样式清理
for nm in ('_测试样式', '_冻形'):
    design_styles.delete_style(gui.config_dir, nm)

print('\n===', 'ALL PASS' if not _failures else f'{len(_failures)} FAILURES',
      '===')
sys.exit(1 if _failures else 0)
