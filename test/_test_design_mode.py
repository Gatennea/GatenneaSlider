# -*- coding: utf-8 -*-
"""设计还原态（自定义样式）无头测试。

锁的事：
  · 入口分离：手动构造/随机生成 = 造打乱局面；设计 = 造还原态样式
    （创造模式首页独立按钮，构造工具条不再有设计控件）
  · 设计画布：点格增删滑块 + 捆绑/解绑（点两个已有滑块 = 沿路径捆绑；
    点组内滑块 = 整组解绑；ESC 取消待配对第一点）
  · 保存样式：JSON 落盘 + 冻形拦截（3×3 L 形零合法移动，拒绝保存）
  · 样式开局：goal_pattern 设置 + D4 八变换判定（旋转/翻面都算还原）
  · 退出设计/取消构造/清空画布时设计态一并不残留
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


gui = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                ext_state={'enabled': True, 'token': 'T', 'port': 5050})
gui.tut_show_prompt = False
gui.tutorial_active = False
# 归一开局：测试假设 4×4 step1（启动时会从 temp_history 恢复任意旧局）
gui.new_puzzle(4, 4, 1)

# 清理可能残留的测试样式
for nm in ('_测试样式', '_冻形'):
    design_styles.delete_style(gui.config_dir, nm)


def enter_design():
    """创造模式首页 → [设计还原态]（真实入口路径）。"""
    gui.game_mode = 'create'
    gui._ann_btn_design()


def enter_build():
    """创造模式首页 → [手动构造]（真实入口路径）。"""
    gui.game_mode = 'create'
    gui._ann_btn_manual_build()


def place(coords):
    for p in coords:
        if p not in gui._ann_build_coords:
            gui._ann_build_toggle(p)
    gui._ann_rebuild_game_from_coords()


def remove(coords):
    for p in coords:
        if p in gui._ann_build_coords:
            gui._ann_build_toggle(p)
    gui._ann_rebuild_game_from_coords()


# ---------------------------------------------------------------- 入口分离
print('--- D0 入口分离：设计 = 还原态，手动构造 = 打乱态 ---')
gui.game_mode = 'create'
gui._ann_view = 'home'
# 首页按钮注册齐全（方形：手动构造/随机生成/设计还原态/样式库）
gui._ann_draw_bar()
home_btns = set(gui._ann_btn_rects)
check('D0a 首页有[设计还原态]按钮', 'design' in home_btns, f'{sorted(home_btns)}')
check('D0b 首页有[样式库]按钮', 'style_lib' in home_btns)
check('D0c 首页仍有[手动构造][随机生成]',
      'manual_build' in home_btns and 'random_gen' in home_btns)

enter_design()
check('D0d 进入设计视图', gui._ann_view == 'design'
      and gui._ann_sub_dialog == 'design')
check('D0e 设计画布初始 = 满矩形还原态（4×4=16 颗）',
      len(gui._ann_build_coords) == 16, f'{len(gui._ann_build_coords)}')
check('D0f 设计无捆绑无错误', gui._ann_design_groups == {}
      and gui._ann_design_bind_active is False)
check('D0g 设计态冻形缓存就绪（满盘可动）',
      gui._ann_design_frozen is False)

# 设计画布删减出 L 形后，冻形缓存实时更新
remove([(3, 0), (3, 1), (3, 2), (3, 3), (2, 1), (2, 2), (2, 3), (1, 1),
        (1, 2), (1, 3)])   # 剩 (0,0)(0,1)(0,2)(0,3)(1,0)(2,0) = 3×3 L 形冻形
check('D0h 冻形缓存实时更新（L 形 → True）',
      gui._ann_design_frozen is True and len(gui._ann_build_coords) == 6)

enter_build()
check('D0i 构造工具条无设计控件残留（矩形已清空）',
      gui._ann_design_btn_rects == {} and gui._ann_design_name_rect is None)
check('D0j 构造不带设计态（捆绑/样式/下拉全空）',
      gui._ann_design_groups == {} and gui._ann_design_bind_active is False
      and gui._ann_design_style_menu is None)
# 构造视图点击不会激活样式名输入（防上次设计会话残留矩形吞点击）
gui._ann_design_name_rect = pygame.Rect(0, 0, 50, 20)
gui._ann_build_dialog_rect = pygame.Rect(0, 0, 800, 600)
gui._ann_design_name_active = False
gui._ann_build_dialog_click(10, 10)
check('D0k 构造视图点击不激活样式名输入', gui._ann_design_name_active is False)

# ---------------------------------------------------------------- 捆绑/解绑
print('\n--- D1 设计画布：捆绑与解绑 ---')
enter_design()
remove([(3, 0), (3, 1), (3, 2), (3, 3), (2, 1), (2, 2), (2, 3), (1, 1),
        (1, 2), (1, 3)])
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
gui._ann_build_dialog_event(
    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0,
                       unicode='', scancode=0))
check('D1d ESC 取消待配对第一点', gui._ann_design_bind_first is None)

# 点组内滑块 = 解绑整组
gui._ann_design_click((0, 1))
check('D1e 点组内滑块整组解绑', gui._ann_design_groups == {})

# 不连通两点不可捆（中间空位）
place([(2, 2)])
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
print('\n--- D2 设计画布：样式保存与冻形拦截 ---')
enter_design()
remove([(3, 0), (3, 1), (3, 2), (3, 3), (2, 1), (2, 2), (2, 3), (1, 1),
        (1, 2), (1, 3)])   # 3×3 L 形冻形
gui._ann_design_style_name = '_冻形'
gui._ann_design_save_style()
check('D2a 冻形拒绝保存（L 形 3×3 零合法移动）',
      design_styles.load_style(gui.config_dir, '_冻形') is None
      and '冻形' in (gui._ann_build_error or ''))

enter_design()
remove([(3, 0), (3, 1), (3, 2), (3, 3), (2, 2), (2, 3), (1, 2), (1, 3)])
# 剩 2×3+2 = 8 颗可动棋形：(0,0..2)(1,0..1)(2,0..1)(3,0)
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
    check('D2d 样式 cells 数正确', len(data['cells']) == 8)

# ---------------------------------------------------------------- 样式开局
print('\n--- D3 样式开局与 D4 判定 ---')
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
print('\n--- D4 退出设计/取消构造不残留 ---')
enter_design()
remove([(3, 0), (3, 1), (3, 2), (3, 3), (2, 1), (2, 2), (2, 3), (1, 1),
        (1, 2), (1, 3)])
gui._ann_design_bind_active = True
gui._ann_design_click((0, 0))
gui._ann_design_click((1, 0))
n_groups = len(set(gui._ann_design_groups.values()))
gui._ann_build_clear()
check('D4a 清空画布连带清捆绑', n_groups == 1
      and gui._ann_design_groups == {})

enter_design()
gui._ann_design_bind_active = True
gui._ann_design_click((0, 0))
gui._ann_design_click((0, 1))
gui._ann_design_cancel()
check('D4b 退出设计清设计态并回首页',
      gui._ann_design_groups == {}
      and gui._ann_design_bind_active is False
      and gui._ann_view == 'home'
      and gui._ann_sub_dialog is None)

# 退出设计后局面恢复（进入设计前的棋盘原样回来）
check('D4c 退出设计恢复进入前局面',
      len(gui.game.blocks) == 16
      and gui.game.is_solved())

enter_build()
place([(0, 0), (0, 1)])
gui._ann_design_bind_active = True
gui._ann_design_click((0, 0))
gui._ann_design_click((0, 1))
gui._ann_build_cancel()
check('D4d 取消构造清设计态',
      gui._ann_design_groups == {}
      and gui._ann_design_bind_active is False
      and gui._ann_view == 'home')

# 测试样式清理
for nm in ('_测试样式', '_冻形'):
    design_styles.delete_style(gui.config_dir, nm)

print('\n===', 'ALL PASS' if not _failures else f'{len(_failures)} FAILURES',
      '===')
sys.exit(1 if _failures else 0)
