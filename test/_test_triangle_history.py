# -*- coding: utf-8 -*-
"""無頭測試：三角形密鋪的撤回/重做與動畫（Stage B3）。

覆蓋：快照每步一條（不合并）、undo/redo 位置與步數往返、
      undo/redo 動畫播完後狀態一致、動畫中繪製不崩潰、
      _move_delta 六向換算、選中閃爍高亮、跳步、方形無迴歸。
"""
import os, sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from GUI import SliderGUI  # noqa: E402
from game_triangle import (  # noqa: E402
    TriangleSliderMatrix, DIRECTIONS,
)

_failed = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ''))
    if not cond:
        _failed.append(name)


gui = SliderGUI()
gui.save_readonly_flag = False
gui.animation_enabled = False  # 先關動畫：讓移動立即提交，便於斷言快照粒度
K = 4
gui.new_triangle_puzzle(K, 1)


def positions():
    return set(gui.game.positions())


def square_positions():
    """方形棋盤的位置集合（SliderMatrix 沒有 positions()）。"""
    return {(b.location[0], b.location[1]) for b in gui.game.blocks}


def play_any():
    """在同一選中會話內任選一個當前可動的方向動一次（回傳是否成功）。

    刻意不清 session、只清 selected_gap：這樣方形會把兩次移動合并成一條
    快照，而三角必須每步一條——正是要測的差異。
    """
    for letter in DIRECTIONS:
        gui.selected_block = gui.game.blocks[0]
        gui.selected_gap = None
        if gui.move_selected_blocks(letter):
            return True
    return False


def drain_animation(limit=2000):
    """驅動動畫到結束，回傳播了幾幀。

    必須讓出真實時間：動畫進度按 pygame.time.get_ticks() 計算，緊密循環
    可能在一個毫秒內跑完，progress 永遠是 0。
    """
    import time
    frames = 0
    while gui.animating and frames < limit:
        gui.update_animation()
        frames += 1
        time.sleep(0.002)
    return frames


# ---------------------------------------------------------------- 快照粒度
print("=== 快照粒度（三角不合并）===")
start = positions()
hist0 = len(gui.game_history.history)
ok1 = play_any()
snap1 = len(gui.game_history.history)
ok2 = play_any()
snap2 = len(gui.game_history.history)
check("兩次移動都成功", ok1 and ok2)
check("每步各占一條快照", snap1 == hist0 + 1 and snap2 == hist0 + 2,
      f"{hist0} → {snap1} → {snap2}")
check("步數 = 2", gui.step_count == 2, gui.step_count)
check("局面已改變", positions() != start)
check("打亂態始終單一連通",
      TriangleSliderMatrix.is_single_connected(positions()))
after_two = positions()

# ---------------------------------------------------------------- undo/redo
print("=== undo / redo 往返 ===")
gui.animation_enabled = False
gui.undo()
check("undo 回到上一步", positions() != after_two)
check("undo 後步數 = 1", gui.step_count == 1, gui.step_count)
check("undo 後仍連通", TriangleSliderMatrix.is_single_connected(positions()))
after_one = positions()
gui.undo()
check("再 undo 回到初始打亂態", positions() == start)
check("步數歸零", gui.step_count == 0, gui.step_count)
check("已到起點：無步可撤", gui.game_history.can_undo() is False)
gui.undo()
check("無步可撤時 undo 不改變局面", positions() == start)
gui.redo()
check("redo 前進一步", positions() == after_one)
check("redo 後步數 = 1", gui.step_count == 1, gui.step_count)
gui.redo()
check("redo 再前進一步", positions() == after_two)
check("redo 後步數 = 2", gui.step_count == 2, gui.step_count)
check("已到末點：無步可重做", gui.game_history.can_redo() is False)

print("=== 撤銷/重做動畫 ===")
gui.animation_enabled = True
gui.animation_duration = 30
gui.undo()
check("undo 進入動畫", gui.animating is True and gui._undo_redo_type == 'undo')
check("動畫中繪製不崩潰（draw_board）", gui.draw_board() is None)
frames = drain_animation()
check("動畫已播完", not gui.animating and frames > 0, f"{frames} 幀")
check("動畫結束後位置 = 動畫前一步", positions() == after_one)
check("動畫結束後步數 = 1", gui.step_count == 1, gui.step_count)
check("動畫結束後仍連通", TriangleSliderMatrix.is_single_connected(positions()))
gui.redo()
check("redo 進入動畫", gui.animating is True and gui._undo_redo_type == 'redo')
drain_animation()
check("redo 動畫結束後位置 = 動畫前一步", positions() == after_two)
check("redo 後步數 = 2", gui.step_count == 2, gui.step_count)
gui.animation_enabled = False

print("=== 選中閃爍高亮（三角 3 元組位置）===")
gui.undo()
gui.selection_animation_enabled = True
mi = gui.game_history.history[gui.game_history.history_index].get('move_info')
check("該步帶 move_info", mi is not None)
if mi is not None:
    gui._flash_move_selection(mi, True)
    check("高亮選中了滑塊組", len(gui._sel_anim_blocks) > 0,
          f"{len(gui._sel_anim_blocks)} 塊")
    check("高亮位置都是合法 3 元組",
          all(len(b.location) == 3 for b in gui._sel_anim_blocks))
    gui.draw_board()
    check(True, "高亮態繪製不崩潰")
    gui._clear_sel_anim()
    check("清除後無殘留", not gui._sel_anim_blocks)
gui.selection_animation_enabled = False

print("=== _move_delta 六向換算 ===")
for letter, (di, dj) in DIRECTIONS.items():
    got = gui._move_delta({'direction': letter, 'step': 1})
    check(f"方向 {letter} → ({di},{dj})", got == (di, dj), f"實際 {got}")
    got2 = gui._move_delta({'direction': letter, 'step': 3})
    check(f"方向 {letter} × 3 步", got2 == (di * 3, dj * 3), f"實際 {got2}")

print("=== 跳步 ===")
n = len(gui.game_history.history)
gui.jump_to_history_index(0)
check("跳到第 0 條", positions() == start and gui.step_count == 0)
gui.jump_to_history_index(n - 1)
check("跳到末條", gui.step_count == n - 1, f"{gui.step_count} vs {n - 1}")
check("跳步後仍連通", TriangleSliderMatrix.is_single_connected(positions()))

print("=== 方形無迴歸 ===")
gui.new_puzzle(6, 6, 2)
gui.game.opt('h', 1, gui.game.blocks[0])
check("方形移動仍正常", gui.move_selected_blocks('a') is True)
snap_before = square_positions()
gui.undo()
check("方形 undo 仍正常", square_positions() != snap_before)
gui.redo()
check("方形 redo 仍正常", square_positions() == snap_before)
gui.animation_enabled = True
gui.animation_duration = 30
gui.undo()
check("方形 undo 動畫啟動", gui.animating)
drain_animation()
check("方形 undo 動畫播完", not gui.animating)

print()
if _failed:
    print(f"共 {len(_failed)} 項失敗")
    sys.exit(1)
print("全部通過")
