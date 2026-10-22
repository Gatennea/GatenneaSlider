# -*- coding: utf-8 -*-
"""高级选项 / 设计还原态（自定义样式）无头测试。

锁的事（2026-10-20 重做）：
  · 入口分离：创造模式首页不再有「设计还原态」按钮；设计改由谜题-自定义
    下的「高级选项」进入（_ann_open_advanced，练习模式），仍是造还原态样式。
    与手动构造（造打乱局面）语义分开，互不冲突。
  · 捆绑/解绑改走点缝：点两滑块之间的缝 = 合并两侧整组；点捆绑块内部缝 =
    沿整条缝解绑（贯穿整个捆绑块，不能只解一段长度为 1 的缝）。
  · 保存样式：JSON 落盘 + 「可打乱」判定（≥2 颗能滑且共用缝相连），
    不再做滑块数量 / mod 不变量校验；冻形/互不相连自然被「可打乱」拦下。
  · 样式开局：goal_pattern 设置 + D4 八变换判定（旋转/翻面都算还原）。
  · 谜题菜单：自定义预设经 _refresh_puzzle_presets 列入；导入按名查
    config/design_styles/<名>.json。
  · 退出设计/取消构造/清空画布时设计态一并不残留。
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


def enter_design():
    """创造模式 → 设计画布（_ann_btn_design 内部路径，仅用于画布逻辑）。"""
    gui.game_mode = 'create'
    gui._ann_btn_design()


def enter_advanced():
    """谜题菜单「高级选项」入口（练习模式真实路径）。"""
    gui.game_mode = 'practice'
    gui._ann_open_advanced()


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


def find_gap_screen(gt, line, along=None):
    """在屏幕上找一个会被识别为 (gt, line) 缝隙、且落在指定行/列上的点击位置。

    along = 垂直于缝的坐标索引（v-缝取列内行号 r；h-缝取行内列号 c），
    必须落在滑块实占范围内，否则 _ann_design_seam_click 会因「两侧不全有
    滑块」拒绝。传 None 则不限制。
    """
    unit = gui.board_view.cell_size + gui.board_view.gap_width
    for sx in range(0, gui.screen_width, 3):
        for sy in range(0, gui.screen_height, 3):
            if gui.get_gap_at_pos(sx, sy) != (gt, line):
                continue
            wx, wy = gui.screen_to_world(sx, sy)
            if along is not None:
                if gt == 'v' and int(wy // unit) != along:
                    continue
                if gt == 'h' and int(wx // unit) != along:
                    continue
            return sx, sy
    return None


# ---------------------------------------------------------------- 启动
gui = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                ext_state={'enabled': True, 'token': 'T', 'port': 5050})
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.new_puzzle(4, 4, 1)

for nm in ('_测试样式', '_不可打乱'):
    design_styles.delete_style(gui.config_dir, nm)
# 样式名经 sanitize_name 清洗：首尾的 ._ 会被去掉，故实际落盘/菜单名无前导下划线
SNAME = design_styles.sanitize_name('_测试样式')
UNAME = design_styles.sanitize_name('_不可打乱')

# ---------------------------------------------------------------- 入口分离
print('--- D0 入口分离：设计改由高级选项进入，与手动构造分离 ---')
gui.game_mode = 'create'
gui._ann_view = 'home'
gui._ann_draw_bar()
home_btns = set(gui._ann_btn_rects)
check('D0a 创造模式首页不再有[设计还原态]按钮', 'design' not in home_btns,
      f'{sorted(home_btns)}')
check('D0b 首页仍有[手动构造][随机生成]',
      'manual_build' in home_btns and 'random_gen' in home_btns)

enter_advanced()
check('D0c 高级选项进入设计视图', gui._ann_view == 'design'
      and gui._ann_sub_dialog == 'design')
check('D0d 高级选项不进隐藏标注模式（只开画布会话）',
      gui.annotation_mode is False and gui._ann_design_session is True
      and gui.game_mode == 'practice',
      f'ann={gui.annotation_mode} sess={gui._ann_design_session} '
      f'mode={gui.game_mode}')
check('D0e 画布初始 = 进入前那盘棋（4×4 满盘 → 16 颗）',
      len(gui._ann_build_coords) == 16, f'{len(gui._ann_build_coords)}')
check('D0f 设计无捆绑无错误', gui._ann_design_groups == {})
gui._ann_design_cancel()
check('D0g 退出设计回到练习模式并关 annotation_mode',
      gui.annotation_mode is False and gui._ann_view == 'home')
check('D0h 退出设计清掉画布会话', gui._ann_design_session is False)

# ---------------------------------------------------------------- 点缝绑/解
print('\n--- D1 设计画布：点缝捆绑 / 解绑 ---')
enter_advanced()  # 满 4×4

# 点 v-缝 line0（col0 与 col1 之间）在第 0 行处 → 捆绑 (0,0)(0,1)
pos = find_gap_screen('v', 0, along=0)
check('D1a 找到 v-缝 line0 的屏幕位置', pos is not None)
if pos:
    gui._ann_design_board_click(*pos)
    # 被捆绑的是某个 v-缝两侧的相邻两格（行号取决于命中点，断言与行无关）
    vals = [v for k, v in gui._ann_design_groups.items()]
    ok = len(gui._ann_design_groups) == 2 and len(set(vals)) == 1 and vals[0]
    check('D1b 点缝捆绑两侧成一组', ok, f'{gui._ann_design_groups}')

# 再点同一条缝（已是同组内部缝）→ 应触发解绑（贯穿整条线，单块→无捆绑）
pos2 = find_gap_screen('v', 0, along=0)
if pos2:
    gui._ann_design_board_click(*pos2)
    check('D1c 再点内部缝整组解绑（单块归零）', gui._ann_design_groups == {})

# 直接测核心方法：捆绑 (1,1)-(1,2) 与 (2,1)-(2,2) 再合并两组
gui._ann_design_groups = {}
gui._ann_design_next_gid = 1
gui._ann_design_bind_seam((1, 1), (1, 2))
gui._ann_design_bind_seam((2, 1), (2, 2))
g1 = gui._ann_design_groups[(1, 1)]
g2 = gui._ann_design_groups[(2, 1)]
check('D1d 两组分别建立', g1 != g2 and g1 and g2)
gui._ann_design_bind_seam((1, 1), (2, 1))  # 合并两组
merged = len({gui._ann_design_groups[p] for p in
              ((1, 1), (1, 2), (2, 1), (2, 2))})
check('D1e 两组合并为一个', merged == 1, f'{gui._ann_design_groups}')

# 解绑必须贯穿整条缝：建一个 2×2 捆绑块，点内部 h-缝 line0 只解下半行
gui._ann_design_groups = {}
gui._ann_design_next_gid = 2   # gid 1 已占用；新组必须从 2 起，否则解绑看不出变化
for p in ((0, 0), (0, 1), (1, 0), (1, 1)):
    gui._ann_design_groups[p] = 1
gui._ann_rebuild_game_from_coords()
pos_h = find_gap_screen('h', 0, along=0)
if pos_h:
    gui._ann_design_board_click(*pos_h)
    lower = {gui._ann_design_groups.get(p) for p in ((1, 0), (1, 1))}
    upper = {gui._ann_design_groups.get(p) for p in ((0, 0), (0, 1))}
    check('D1f 沿整条缝解绑：下半行换新组、上半保留',
          len(lower) == 1 and len(upper) == 1
          and lower != upper and None not in lower | upper,
          f'{gui._ann_design_groups}')
    # 同一缝不是内部缝时不应误伤：清掉后点一条两侧不同组的缝
    gui._ann_design_groups = {}
    gui._ann_rebuild_game_from_coords()

# 点格仍正常增删（与绑解互不冲突）：toggle 让 (3,3) 的在场状态翻转
gui._ann_design_groups = {}
had = (3, 3) in gui._ann_build_coords
n_before = len(gui._ann_build_coords)
gui._ann_build_toggle((3, 3))
flipped = ((3, 3) in gui._ann_build_coords) != had
check('D1g 点格增删分支可用',
      flipped and len(gui._ann_build_coords) == n_before + (-1 if had else 1))

# ---------------------------------------------------------------- 可打乱门
print('\n--- D2 可打乱判定（保存门） ---')
enter_advanced()
# 留一个 2×2 满块（边界盒正好填满，任何移动都碰撞 → 0 可动 → 不可打乱）
gui._ann_build_coords = {(0, 0), (0, 1), (1, 0), (1, 1)}
gui._ann_design_groups = {}
gui._ann_rebuild_game_from_coords()
gui._ann_design_style_name = UNAME
gui._ann_design_save_style()
check('D2a 不可打乱（2×2 满块，0 可动）拒绝保存',
      design_styles.load_style(gui.config_dir, UNAME) is None
      and gui._ann_build_error
      and '滑动' in gui._ann_build_error, f'err={gui._ann_build_error!r}')

enter_advanced()
# 留 3×3 满块（可动，可打乱）
gui._ann_build_coords = {(r, c) for r in range(3) for c in range(3)}
gui._ann_design_groups = {}
gui._ann_rebuild_game_from_coords()
gui._ann_design_style_name = SNAME
gui._ann_design_save_style()
data = design_styles.load_style(gui.config_dir, SNAME)
check('D2b 可动棋形（3×3）保存成功', data is not None)
if data:
    check('D2c 样式 cells 数正确', len(data['cells']) == 9)
    check('D2d 样式无捆绑时 groups 为空', data.get('groups') == {})

# ---------------------------------------------------------------- 菜单与开局
print('\n--- D3 预设列入谜题菜单 + 样式开局 + D4 判定 ---')
gui._refresh_puzzle_presets()
listed = [p for p in gui.puzzle_presets if len(p) == 3 and p[1] == '__custom__']
check('D3a 自定义预设列入谜题菜单', (SNAME, '__custom__', SNAME)
      in gui.puzzle_presets, f'{listed}')

gui._ann_design_start_style(SNAME)
check('D3b 开局后设置 goal_pattern', gui.game.goal_pattern is not None)
# 样式开局 = 建局即还原态，与官方预设（new_puzzle/new_triangle_puzzle）一致，
# 不自动打乱；打乱由玩家 Alt+S 或「编辑-打乱」另行触发。
check('D3c 开局即还原态（不自动打乱）', gui.game.is_solved())
check('D3d 标记样式目标局', gui._ann_style_goal == SNAME)
fit = gui.game.pattern_fit()
check('D3e 盘面与样式完全一致（fit == 1.0）', fit == 1.0, f'fit={fit:.2f}')
check('D3e2 未自动打乱：步数归零、历史仅建局快照',
      gui.step_count == 0 and len(gui.game_history.history) == 1
      and gui.game_history.history_index == 0,
      f'steps={gui.step_count} hist={len(gui.game_history.history)}')

# D4：把盘面摆成样式的旋转像 → 算还原
cells = sorted(gui.game.goal_pattern)
h = max(r for r, _ in cells)
rotated = {(c, h - r) for r, c in cells}
gui.game.apply_pattern(sorted(rotated))
check('D3f 旋转 90° 算还原（八变换判定）', gui.game.is_solved())

gui.new_puzzle(4, 4, 1)
check('D3g 新谜题清空自定义目标',
      gui.game.goal_pattern is None and gui._ann_style_goal is None)

# ---------------------------------------------------------------- 存档记名
print('\n--- D5 存档记录预设名 + 导入按名恢复还原目标 ---')
gui.use_compressed_save = False   # 固定走普通存档格式，验证 preset 字段与按名还原
gui._ann_design_start_style(SNAME)   # 开局即还原态，无打乱演示需要收尾
save_data = gui._build_save_data()
check('D5a 存档记录预设名',
      (save_data.get('puzzle') or {}).get('preset') == SNAME,
      f"{(save_data.get('puzzle') or {}).get('preset')!r}")

gui.new_puzzle(4, 4, 1)   # 切普通谜题：清掉 goal
check('D5b 导入前 goal 已清空', gui.game.goal_pattern is None)
gui._load_save_data(save_data)
check('D5c 导入后按名恢复 goal_pattern',
      gui.game.goal_pattern is not None and gui._ann_style_goal == SNAME,
      f'goal={gui._ann_style_goal!r}')

gui.new_puzzle(4, 4, 1)
plain = gui._build_save_data()
check('D5d 官方预设局不写 preset',
      'preset' not in (plain.get('puzzle') or {}))

# ---------------------------------------------------------------- 状态清理
print('\n--- D4 退出设计 / 取消构造不残留 ---')
gui.new_puzzle(4, 4, 1)  # 进入前确保是 16 满盘还原态
enter_advanced()
gui._ann_design_bind_seam((0, 0), (0, 1))
n_groups = len(set(gui._ann_design_groups.values()))
gui._ann_build_clear()
check('D4a 清空画布连带清捆绑', n_groups == 1
      and gui._ann_design_groups == {})

gui.new_puzzle(4, 4, 1)  # 重新确保满盘，作为进入前局面
enter_advanced()
gui._ann_design_bind_seam((0, 0), (0, 1))
gui._ann_design_cancel()
check('D4b 退出设计清设计态并回首页',
      gui._ann_design_groups == {}
      and gui._ann_view == 'home'
      and gui._ann_sub_dialog is None)

# 退出设计后局面恢复（进入设计前的棋盘原样回来）
check('D4c 退出设计恢复进入前局面',
      len(gui.game.blocks) == 16
      and gui.game.is_solved())

# ---------------------------------------------------------------- 复原
print('\n--- D6 样式局「复原」回到样式还原态（不退回默认满矩形） ---')
gui._ann_design_start_style(SNAME)
check('D6a 样式局开局即还原态', gui.game.is_solved())
gui.shuffle_puzzle()
if getattr(gui, '_shuffle_demo_final', None) is not None:
    gui._finish_shuffle_demo()
check('D6b 打乱后非还原态', not gui.game.is_solved())
gui.reset_puzzle()
check('D6c 复原回到样式还原态', gui.game.is_solved()
      and gui.game.pattern_fit() == 1.0
      and gui._ann_style_goal == SNAME,
      f'solved={gui.game.is_solved()} fit={gui.game.pattern_fit():.2f} '
      f'goal={gui._ann_style_goal!r}')

# ---------------------------------------------------------------- 入场/退出
print('\n--- D7 高级选项入场 = 进入前盘面；[退出]按钮不残留标注模式 ---')
GNAME = design_styles.sanitize_name('_带捆绑样式')
design_styles.delete_style(gui.config_dir, GNAME)
_c7 = [[r, c] for r in range(3) for c in range(3) if (r, c) != (2, 2)]
_g7 = {(0, 0): 1, (0, 1): 1, (1, 0): 1, (1, 1): 1}
design_styles.save_style(gui.config_dir, GNAME, {
    'version': 1, 'name': GNAME, 'm': 3, 'n': 3, 'step': 1,
    'cells': _c7, 'groups': {f'{r},{c}': g for (r, c), g in _g7.items()},
})
gui.new_puzzle(4, 4, 1)
gui._ann_design_start_style(GNAME)
before_cells = {(int(b.location[0]), int(b.location[1])) for b in gui.game.blocks}
before_groups = {(int(b.location[0]), int(b.location[1])): int(b.group)
                 for b in gui.game.blocks if getattr(b, 'group', 0)}
check('D7a 样式局带捆绑入场（前置条件）',
      len(before_cells) == 8 and len(before_groups) == 4, f'{before_groups}')
gui._ann_open_advanced()
check('D7b 画布 cells = 进入前盘面（不再重置成满矩形）',
      gui._ann_build_coords == before_cells,
      f'{sorted(gui._ann_build_coords)}')
check('D7c 画布带入进入前的捆绑组', gui._ann_design_groups == before_groups,
      f'{gui._ann_design_groups}')
check('D7d 进入不切模式（练习模式 + 未开标注模式）',
      gui.game_mode == 'practice' and gui.annotation_mode is False)
gui._ann_btn_build_cancel()   # 工具条[退出]的真实分发路径
after_cells = {(int(b.location[0]), int(b.location[1])) for b in gui.game.blocks}
after_groups = {(int(b.location[0]), int(b.location[1])): int(b.group)
                for b in gui.game.blocks if getattr(b, 'group', 0)}
check('D7e [退出]不残留标注模式（回到进入前的模式）',
      gui.annotation_mode is False and gui._ann_design_session is False
      and gui._ann_view == 'home' and gui.game_mode == 'practice')
check('D7f [退出]后盘面与捆绑与进入前一致',
      after_cells == before_cells and after_groups == before_groups
      and gui.game.is_solved(), f'{len(after_cells)}/{after_groups}')
design_styles.delete_style(gui.config_dir, GNAME)

# ---------------------------------------------------------------- 清理
for nm in ('_测试样式', '_不可打乱'):
    design_styles.delete_style(gui.config_dir, nm)

print('\n===', 'ALL PASS' if not _failures else f'{len(_failures)} FAILURES',
      '===')
sys.exit(1 if _failures else 0)
