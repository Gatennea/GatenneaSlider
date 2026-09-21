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
# 建局即还原态（与方形 new_puzzle 一致：打乱是独立动作）
check(gui.is_solved() is True, "建局即实心大三角：起手是还原态")
goal = gui.game.goal_cells()
check(set(gui.game.positions()) == goal, "建局位置 = 目标轮廓")
check(len(goal) == 36, f"目标轮廓 = 边长 6 的大三角（{len(goal)} 格）")
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

print("== 縫隙線渲染（選中紅線 / 未選中灰線 / 參考塊高亮）==")
gui.shuffle_puzzle()
from game_triangle import neighbors, side_of  # noqa: E402
cells = gui.game.positions()


def _pixel_count(color):
    """屏幕上该颜色的像素数（隔行隔列采样，够用）。"""
    n = 0
    w, h = gui.screen.get_size()
    for y in range(0, h, 2):
        for x in range(0, w, 4):
            if gui.screen.get_at((x, y))[:3] == color:
                n += 1
    return n


def _pixel_rows(color):
    """返回屏幕上出现该颜色的所有行号（隔行采样，够用）。"""
    rows = set()
    w, h = gui.screen.get_size()
    for y in range(0, h, 2):
        for x in range(0, w, 4):
            if gui.screen.get_at((x, y))[:3] == color:
                rows.add(y)
                break
    return sorted(rows)


def _block_color(block):
    cx, cy = view.piece_center(*tri_key(block))
    px, py = gui.world_to_screen(cx, cy)
    return gui.screen.get_at((int(px), int(py)))[:3]


def _seam_point(gap_type, line):
    """縫隙兩側相鄰塊公共邊的中點（世界座標）。

    這個點只落在該族縫隙線上：它不是格點（三族縫隙在此交叉），
    因此可以用來無歧義地驗證「點在這條縫上能選中它」。
    """
    for a in cells:
        if side_of(gap_type, line, a) != 0:
            continue
        for b in neighbors(a):
            if b in cells and side_of(gap_type, line, b) == 1:
                ax, ay = view.piece_center(*a)
                bx, by = view.piece_center(*b)
                return (ax + bx) / 2, (ay + by) / 2
    return None


# ---- 1. 选中的缝隙画红线，且线落在「被它分开的两侧相邻块」的公共边上 ----
seam_ok = True
for gap_type, line in gui.game.all_gaps():
    gui.selected_gap = (gap_type, line)
    gui.selected_block = None
    gui.draw_board()
    if gap_type == 'h':
        reds = _pixel_rows((255, 0, 0))
        _, seam_y = gui.world_to_screen(0.0, view.gap_h_y(line))
        near = any(abs(y - seam_y) <= 3 for y in reds)
    else:
        # 斜族：取公共边中点，检查该点附近有红像素
        wx, wy = _seam_point(gap_type, line)
        mx, my = gui.world_to_screen(wx, wy)
        w, h = gui.screen.get_size()
        near = any(abs(x - mx) <= 4 and abs(y - my) <= 4
                   for y in range(0, h, 2) for x in range(0, w, 4)
                   if gui.screen.get_at((x, y))[:3] == (255, 0, 0))
    if not near:
        seam_ok = False
        print(f"      縫隙 {gap_type}{line} 的紅線沒落在公共分界上")
check(seam_ok, "选中缝隙的红线落在真实分界（rank=line+1）上")

# ---- 2. 未选中的缝隙画灰线（与原版一致），选中的那条改画红线 ----
gui.selected_gap = None
gui.draw_board()
grays = _pixel_count(gui.colors['gap'])
check(grays > 0, f"未选中缝隙画成灰色（{grays} 个灰像素）")
gui.selected_gap = gui.game.all_gaps()[0]
gui.draw_board()
grays_after = _pixel_count(gui.colors['gap'])
reds = _pixel_count(gui.colors['line'])
check(grays_after < grays,
      f"选中后该缝隙不再画灰线（灰像素 {grays} → {grays_after}）")
check(reds > 0, f"选中后画出红线（{reds} 个红像素）")

# ---- 2b. 缝隙线段必须落在棋形凸包内：不画到三角形外面的空白处 ----
# 方形版把缝隙线裁到棋盤矩形；三角版的棋形不是矩形，裁到棋形凸包。
# 原版先画线、后画滑块盖住，洞里也留一条直线，所以每条缝隙只画一段：
# 线段端点可以落在洞里（那里没有滑块），但整段都不能越出凸包。
import pygame as _pg  # noqa: E402
_orig_line = _pg.draw.line
_drawn = []


def _spy_line(surf, color, p1, p2, width=1):
    _drawn.append((tuple(color[:3]), p1, p2))
    return _orig_line(surf, color, p1, p2, width)


def _in_hull(pt, hull):
    """點是否在凸包內（含邊界）：凸多邊形要求所有邊的叉積同號。"""
    pos = neg = False
    n = len(hull)
    for k in range(n):
        x1, y1 = hull[k]
        x2, y2 = hull[(k + 1) % n]
        cr = (x2 - x1) * (pt[1] - y1) - (y2 - y1) * (pt[0] - x1)
        pos = pos or cr > 1e-6
        neg = neg or cr < -1e-6
    return not (pos and neg)


_pg.draw.line = _spy_line
try:
    gui.selected_gap = None
    gui.draw_board()
    gui.selected_gap = gui.game.all_gaps()[1]
    gui.draw_board()
finally:
    _pg.draw.line = _orig_line
gap_c = gui.colors['gap'][:3]
line_c = gui.colors['line'][:3]
hull = view.board_hull(cells)
outside = [d for d in _drawn
           if d[0] in (gap_c, line_c)
           and not (_in_hull(gui.screen_to_world(*d[1]), hull)
                    and _in_hull(gui.screen_to_world(*d[2]), hull))]
check(not outside,
      f"缝隙线段全部落在棋形凸包内（越界 {len(outside)} 条）")
for color, p1, p2 in outside[:3]:
    print(f"      越界线段 {color} {p1}→{p2}")
reds = [d for d in _drawn if d[0] == line_c]
check(len(reds) == 1,
      f"选中的缝隙只画一段红线（洞里也不断）：实际 {len(reds)} 段")

# ---- 3. 高亮只认 be_opted：单独选中一个滑块不高亮（与方形一致，
#          「未选缝隙就点滑块」在三角里也不再有反应）----
gui.selected_gap = None
ref = gui.game.blocks[0]
gui.selected_block = ref
for b in gui.game.blocks:
    b.be_opted = False
gui.draw_board()
check(_block_color(ref) == gui.colors['block'],
      f"仅 selected_block 不高亮（{_block_color(ref)}）")
# 选中缝隙后 opt 出的一组才高亮
gap_type, line = gui.game.all_gaps()[0]
gui.selected_gap = (gap_type, line)
gui.game.opt(gap_type, line, ref)
gui.draw_board()
opted = [b for b in gui.game.blocks if b.be_opted]
check(opted and _block_color(ref) == gui.colors['block_selected'],
      f"opt 出的滑块组高亮为选中色（{len(opted)} 个）")
check(_block_color(next(b for b in gui.game.blocks if not b.be_opted))
      == gui.colors['block'], "组外滑块保持原色")

# ---- 4. 缝隙点击命中：点在真实分界上能选中该缝隙 ----
gap_hit_ok = True
for gap_type, line in gui.game.all_gaps():
    wx, wy = _seam_point(gap_type, line)
    px, py = gui.world_to_screen(wx, wy)
    if gui.get_gap_at_pos(int(px), int(py)) != (gap_type, line):
        gap_hit_ok = False
        print(f"      點擊 {gap_type}{line} 的分界未命中")
check(gap_hit_ok, "点击真实分界能选中对应缝隙")
# 后续段落假设「刚建局」的状态：重建一盘
gui.new_triangle_puzzle(6, 2)

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
check(True, "ensure_blocks_visible 不崩潰")

print("== 状态栏判定 ==")
# 建局即实心大三角：先确认初始就是还原态，再打乱确认会变成非还原态
from game import Block  # noqa: E402
check(gui.is_solved() is True, "建局态走 GUI 层判定为复原")
gui.shuffle_puzzle()
check(gui.is_solved() is False, "打乱后判为非复原")
gui.game.blocks = [Block(list(key)) for key in gui.game.goal_cells()]
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
check(gui.timer_puzzle_key == '2~tri6', f"競速 key = {gui.timer_puzzle_key}")

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
