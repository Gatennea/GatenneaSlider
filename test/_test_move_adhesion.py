# -*- coding: utf-8 -*-
"""§55 护栏：滑后与其余块粘连时，选中应扩成整块而不是清空。

覆盖：
  A. 方形 6×6：选中左上组件向右滑一格后与右上组件粘连 → 选中扩为整块、
     另起一步；反推整块不是撤销
  B. 方形 3×3：缝仍分得开时，同一次选中连移两步 → 选中保留、历史合并
  C. 三角形：16 块盘面，n 缝一侧 9 块沿 w 滑后粘连 → 选中扩为整块
  D. 三维 3×3×3：r 缝一侧 2 块沿 c 推后粘连 → 选中扩为整块

运行：D:\\python\\python.exe test\\_test_move_adhesion.py
"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)
os.chdir(_PROJECT)

from GUI import SliderGUI          # noqa: E402
from game import Block            # noqa: E402

_fail = []


def check(name, cond, detail=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        _fail.append(name)


def set_cells(game, cells):
    game.blocks = [Block(list(c)) for c in sorted(cells)]
    game.update_matrix()


def selected(game):
    return [b for b in game.blocks if getattr(b, 'be_opted', False)]


def all_locs(game):
    return {tuple(b.location[:3]) for b in game.blocks}


gui = SliderGUI()
gui.save_readonly_flag = False
gui._readonly = False
gui.animation_enabled = False


def reset_history():
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    gui.step_count = 0
    gui._bump_move_session()


# ---------------------------------------------------------------------------
# A. 方形：滑后粘连
# ---------------------------------------------------------------------------
print('A. 方形 6×6：滑后粘连 → 选中扩为整块')
gui.new_puzzle(6, 6, 1)
cells = set()
# 上方三行：左 3×3 组件 + 右 2×3 组件，第 3 列空出；下方三行整行铺满。
for r in range(3):
    for c in range(3):
        cells.add((r, c))
for r in range(3):
    for c in range(4, 6):
        cells.add((r, c))
for r in range(3, 6):
    for c in range(6):
        cells.add((r, c))
set_cells(gui.game, cells)
reset_history()
gui.selected_gap = ('h', 2)
ref = next(b for b in gui.game.blocks if tuple(b.location) == (0, 0))
gui.game.opt('h', 2, ref)
gui.selected_block = ref
check('起手选中左上组件（9 块）', len(selected(gui.game)) == 9,
      str(len(selected(gui.game))))
before = all_locs(gui.game)
check('向右滑一格成功', bool(gui.move_selected_blocks('d')))
check('滑后已粘连 → 选中扩为整块（15 块）',
      len(selected(gui.game)) == 15, str(len(selected(gui.game))))
check('selected_gap 保留原缝', gui.selected_gap == ('h', 2),
      str(gui.selected_gap))
check('selected_block 仍在新片内', gui.selected_block in selected(gui.game))
check('粘连后历史独立（不并进上一条快照）',
      len(gui.game_history.history) == 2, str(len(gui.game_history.history)))
check('粘连提示说明改为整块',
      '整块' in (gui.macro_notify_msg or ''), gui.macro_notify_msg or '')
rev = bool(gui.move_selected_blocks('a'))
check('反推整块不是撤销：盘面不能恢复原状',
      (not rev) or all_locs(gui.game) != before)
if rev:
    check('反推整块独立成第三步',
          len(gui.game_history.history) == 3,
          str(len(gui.game_history.history)))
check('反推后仍保留整块选中',
      len(selected(gui.game)) == 15, str(len(selected(gui.game))))


# ---------------------------------------------------------------------------
# B. 方形：连续滑动仍保留选中
# ---------------------------------------------------------------------------
print('B. 方形 3×3：缝仍分得开 → 连续两步不清')
gui.new_puzzle(3, 3, 1)
set_cells(gui.game, {(0, 1), (0, 2), (1, 0), (1, 1), (1, 2),
                     (2, 0), (2, 1), (2, 2)})
reset_history()
gui.selected_gap = ('h', 1)
ref = next(b for b in gui.game.blocks if tuple(b.location) == (0, 1))
gui.game.opt('h', 1, ref)
gui.selected_block = ref
m1 = gui.move_selected_blocks('a')
m2 = gui.move_selected_blocks('a')
check('同一次选中可连移两步', bool(m1) and bool(m2), f'{m1}/{m2}')
check('两步后选中仍在', bool(selected(gui.game)),
      str(len(selected(gui.game))))
check('历史只多 1 条合并快照', len(gui.game_history.history) == 2,
      str(len(gui.game_history.history)))
check('合并快照 steps=2', gui.game_history.history[-1].get('steps') == 2,
      str(gui.game_history.history[-1].get('steps')))


# ---------------------------------------------------------------------------
# C. 三角形：p 缝一侧滑后粘连
# ---------------------------------------------------------------------------
print('C. 三角形：滑后粘连 → 选中扩为整块')
gui.new_triangle_puzzle(4, 1)
gui.game.blocks = [Block(list(loc)) for loc in [
    (-1, 1, False), (-1, 2, True), (-1, 2, False), (-1, 3, True),
    (0, 0, False), (0, 1, True), (1, 0, True), (1, 0, False),
    (1, 1, True), (2, 0, True), (2, 0, False), (2, 1, True),
    (2, 1, False), (2, 2, True), (3, 0, True), (3, 1, True),
]]
gui.game.update_matrix()
reset_history()
gui.selected_gap = ('n', 1)
ref = next(b for b in gui.game.blocks
           if tuple(b.location) == (1, 1, True))
gui.game.opt('n', 1, ref)
gui.selected_block = ref
check('起手选中 n 缝一侧 9 块', len(selected(gui.game)) == 9,
      str(len(selected(gui.game))))
before = all_locs(gui.game)
check('沿 w 滑一步成功', bool(gui.move_selected_blocks('w')))
check('滑后已粘连 → 选中扩为整块（11 块）',
      len(selected(gui.game)) == 11, str(len(selected(gui.game))))
check('selected_gap 保留原缝', gui.selected_gap == ('n', 1),
      str(gui.selected_gap))
rev = bool(gui.move_selected_blocks('x'))
check('反推整块不是撤销：盘面不能恢复原状',
      (not rev) or all_locs(gui.game) != before)
check('反推后仍保留整块选中',
      len(selected(gui.game)) == 11, str(len(selected(gui.game))))


# ---------------------------------------------------------------------------
# D. 三维：r 缝一侧推后粘连
# ---------------------------------------------------------------------------
print('D. 三维 3×3×3：推后粘连 → 选中扩为整块')
gui.new_cubic_puzzle(3, 3, 3, 1)
gui.game.blocks = [Block(list(loc)) for loc in [
    (-2, 0, -1), (-2, 0, 0), (-1, 0, -1), (-1, 0, 0), (-1, 0, 1),
    (-1, 1, 0), (-1, 2, -1), (-1, 2, 0), (0, 0, 0), (0, 0, 1),
    (0, 1, 1), (0, 2, 1), (1, 1, 0), (1, 1, 1), (1, 1, 2),
    (2, -1, 3), (2, 0, 2), (2, 0, 3), (2, 1, 0), (2, 1, 1),
    (2, 1, 2), (2, 2, 3), (2, 3, 3), (3, 1, 2), (3, 1, 3),
    (3, 2, 3), (3, 3, 3),
]]
gui.game.blocks = list(gui.game.blocks)     # force adapter sync
reset_history()
gui.selected_gap = ('r', 2)
ref = next(b for b in gui.game.blocks
           if tuple(b.location) == (2, 2, 3))
gui.game.opt('r', 2, ref)
gui.selected_block = ref
n_sel = len(selected(gui.game))
check('起手选中 r 缝一侧 2 块', n_sel == 2, str(n_sel))
before = all_locs(gui.game)
check('沿 c 推一步成功', bool(gui._cubic_push_letter('c')))
check('推后已粘连 → 选中扩为整块（23 块）',
      len(selected(gui.game)) == 23, str(len(selected(gui.game))))
check('selected_gap 保留原缝', gui.selected_gap == ('r', 2),
      str(gui.selected_gap))
rev = bool(gui._cubic_push_letter('C'))
check('反推整块不是撤销：盘面不能恢复原状',
      (not rev) or all_locs(gui.game) != before)
check('反推后仍保留整块选中',
      len(selected(gui.game)) == 23, str(len(selected(gui.game))))


# ---------------------------------------------------------------------------
# E. 动画路径：落位后同样扩成整块
# ---------------------------------------------------------------------------
print('E. 方形 6×6（动画）: 落位后粘连 → 选中扩为整块')
gui.animation_enabled = True
gui.animation_duration = 300
gui.new_puzzle(6, 6, 1)
cells = set()
for r in range(3):
    for c in range(3):
        cells.add((r, c))
for r in range(3):
    for c in range(4, 6):
        cells.add((r, c))
for r in range(3, 6):
    for c in range(6):
        cells.add((r, c))
set_cells(gui.game, cells)
reset_history()
gui.selected_gap = ('h', 2)
ref = next(b for b in gui.game.blocks if tuple(b.location) == (0, 0))
gui.game.opt('h', 2, ref)
gui.selected_block = ref
check('动画路径：右滑进入动画', bool(gui.move_selected_blocks('d'))
      and getattr(gui, 'animating', False))
gui.commit_animation()
check('动画落位后粘连 → 选中扩为整块（15 块）',
      len(selected(gui.game)) == 15, str(len(selected(gui.game))))
check('动画落位后 selected_gap 保留',
      gui.selected_gap == ('h', 2), str(gui.selected_gap))
gui.animation_enabled = False


print('=' * 60)
if _fail:
    print(f'结果：{len(_fail)} 项失败')
    for name in _fail:
        print('  ·', name)
    sys.exit(1)
print('结果：全部通过')
