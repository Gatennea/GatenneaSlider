# -*- coding: utf-8 -*-
"""
三角形密鋪 GUI 無頭煙霧測試（Stage B1 建立，B2 起同步更新）。

執行：python test/_test_triangle_render.py
涵蓋：建局即實心大三角（打亂為獨立動作）、狀態欄判定、繪製不崩潰、
      命中外覆蓋、相機居中、互動護欄（滑動/打亂開放，求解器/競速攔截）、
      存檔 v2 三角分支往返。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import tempfile  # noqa: E402

failures = []


def check(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        failures.append(msg)


from GUI import SliderGUI  # noqa: E402
from game_triangle import TriangleSliderMatrix, tri_key  # noqa: E402

gui = SliderGUI()
gui.save_readonly_flag = False

print("== 建局 ==")
check(gui.new_triangle_puzzle(6, 2) is True, "new_triangle_puzzle(6, 2) 成功")
check(gui.triangle_mode is True, "triangle_mode 标记置位")
check(isinstance(gui.game, TriangleSliderMatrix), "game 为 TriangleSliderMatrix")
check(len(gui.game.blocks) == 36, f"滑块数 = 36（实际 {len(gui.game.blocks)}）")
check(gui.current_m == 6 and gui.current_n == 6 and gui.current_step == 2,
      "current_m/n/step 同步")
# 建局即还原态（与方形 new_puzzle 一致：打乱是独立动作），目标轮廓已记录
check(gui.is_solved() is True, "建局即实心大三角：起手是还原态")
check(set(gui.game.positions()) == set(gui._tri_goal_cells),
      "建局位置 = 目标轮廓")
check(len(gui._tri_goal_cells) == 36,
      f"目标轮廓 = 边长 6 的大三角（{len(gui._tri_goal_cells)} 格）")
check(gui.step_count == 0, "步数归零")
check(len(gui.game_history.history) == 1, "历史仅存初始态这一条快照")
check(gui.new_triangle_puzzle(6, 6) is False, "等级 >= 边长被拒绝")
check(gui.new_triangle_puzzle(1, 1) is False, "边长 < 2 被拒绝")

print("== 繪製 ==")
view = gui._tri_view()
gui.draw_board()
gui.draw_status_bar()
gui.draw_menu_bar()
gui.draw_right_panel()
check(True, "draw_board/status_bar/menu_bar/right_panel 不崩潰")
# 取第一個滑塊，採樣其重心像素：應為方塊填充色
key = tri_key(gui.game.blocks[0])
px, py = view.piece_center(*key)
sx, sy = gui.world_to_screen(px, py)
sampled = gui.screen.get_at((int(sx), int(sy)))[:3]
check(sampled == gui.colors['block'][:3],
      f"滑塊重心像素 = 方塊色 {sampled}")

print("== 命中外覆蓋 ==")
blk0 = gui.game.blocks[0]
world_cx, world_cy = view.piece_center(*tri_key(blk0))
sx, sy = gui.world_to_screen(world_cx, world_cy)
hit = gui.get_block_at_pos(int(sx), int(sy))
check(hit is not None and tri_key(hit) == tri_key(blk0), "世界座標 → 滑塊命中")
check(gui.get_gap_at_pos(int(sx), int(sy)) is None, "滑塊內部不命中縫隙")
# 三角形外的一點（遠離棋盤）
far_x = int(sx + 4000)
check(gui.get_block_at_pos(far_x, int(sy)) is None, "棋盤外不命中滑塊")

print("== 相機居中 ==")
gui.zoom = 1.0
gui.center_map()
box = view.bounding_box(gui.game.positions())
board_cx = (box[0] + box[2]) / 2
board_cy = (box[1] + box[3]) / 2
scx, scy = gui.world_to_screen(board_cx, board_cy)
expect_cx = (gui.screen_width - gui.right_panel_width) / 2
expect_cy = (gui.menu_bar_height +
             (gui.screen_height - gui.menu_bar_height - gui.status_bar_height) / 2)
check(abs(scx - expect_cx) < 1.0 and abs(scy - expect_cy) < 1.0,
      f"棋盤居中於可視區（{scx:.0f},{scy:.0f} vs {expect_cx:.0f},{expect_cy:.0f}）")
gui.ensure_blocks_visible()
check(True, "ensure_blocks_visible 在三角模式下直接返回（不崩潰）")

print("== 状态栏判定 ==")
# 建局即实心大三角：先确认初始就是还原态，再打乱确认会变成非还原态
from game import Block  # noqa: E402
check(gui.is_solved() is True, "建局态走 GUI 层判定为复原")
gui.shuffle_puzzle()
check(gui.is_solved() is False, "打乱后判为非复原")
gui.game.blocks = [Block(list(key)) for key in gui._tri_goal_cells]
check(gui.is_solved() is True, "摆回目标大三角后判复原")

print("== 互動護欄（B2 起滑動/打亂開放，求解器與競速仍攔截）==")
gui.macro_notify_msg = ''
gui.selected_gap = None
gui.selected_block = gui.game.blocks[0]
gui.move_selected_blocks('d')
check('尚未实现' not in gui.macro_notify_msg,
      f"滑動已開放（不再被攔截）：{gui.macro_notify_msg}")
before = set(gui.game.positions())
gui.shuffle_puzzle()
check(set(gui.game.positions()) != before, "打乱已开放（局面改变）")
gui.macro_notify_msg = ''
gui._start_auto_solve()
check('尚未实现' in gui.macro_notify_msg, f"自动求解仍被攔截：{gui.macro_notify_msg}")
gui.macro_notify_msg = ''
gui._timer_enter_ready()
check(gui.timer_state == 'ready', "競速就緒態已開放（B5）")
check(gui.timer_puzzle_key == f'2~tri6', f"競速 key = {gui.timer_puzzle_key}")

print("== 切回方形 ==")
check(gui.new_puzzle(6, 6, 2) is True, "new_puzzle 成功")
check(gui.triangle_mode is False, "triangle_mode 已清除")
check(not isinstance(gui.game, TriangleSliderMatrix), "game 回到 SliderMatrix")
gui.draw_board()
check(True, "方形繪製仍正常（無回歸）")

print("== 存檔 v2 三角分支 ==")
gui.new_triangle_puzzle(6, 2)
saved_positions = set(gui.game.positions())
data = gui._build_save_data()
check(data['version'] == 2 and data['puzzle']['type'] == 'triangle'
      and data['puzzle']['triangle_side'] == 6, "存檔寫入 type=triangle / triangle_side")
snap_matrix = data['history']['snapshots'][0]['matrix']
flat = [v for row in snap_matrix for v in row]
check(all(v in (0, 1, 2, 3) for v in flat), "快照矩陣取值均在 0..3（2-bit 菱形網格）")
bits = sum(bin(v).count('1') for v in flat)
check(bits == 36, f"快照矩陣覆蓋全部 36 個單元三角（實際 {bits}）")
tmp = tempfile.mktemp(suffix='.json')
import json  # noqa: E402
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(data, f)
try:
    gui.new_puzzle(5, 5, 2)
    gui._load_save_data(data)
    check(gui.triangle_mode is True, "載入後 triangle_mode 復原")
    check(isinstance(gui.game, TriangleSliderMatrix), "載入後 game 為三角形")
    check(gui.game.k == 6 and len(gui.game.blocks) == 36, "載入後邊長/塊數正確")
    check(set(gui.game.positions()) == saved_positions, "載入後位置與存檔一致")
    check(gui.step_count == 0, "載入後步數一致")
    gui.draw_board()
    check(True, "載入後繪製正常")
finally:
    if os.path.exists(tmp):
        os.remove(tmp)

print()
if failures:
    print(f"共 {len(failures)} 項失敗")
    sys.exit(1)
print("全部通過")
