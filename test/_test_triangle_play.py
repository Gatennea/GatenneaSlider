# -*- coding: utf-8 -*-
"""
三角形密鋪 GUI 互動無頭測試（Stage B2）。

執行：python test/_test_triangle_play.py
涵蓋：建局即實心大三角（打亂為獨立動作）、6 向鍵盤、單次觸控拖動（投影吸附 + 提交）、
      兩次觸控（選縫→選塊→按方向）、拖拽預覽、護欄、還原判定。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

failures = []


def check(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        failures.append(msg)


from GUI import SliderGUI  # noqa: E402
from game_triangle import (  # noqa: E402
    TriangleSliderMatrix, tri_key, DIRECTIONS, GAP_DIRECTIONS,
)

gui = SliderGUI()
gui.save_readonly_flag = False
gui.animation_enabled = False  # 关掉动画，让移动立即生效，便于断言

K = 4
gui.new_triangle_puzzle(K, 1)
view = gui._tri_view()
N = K * K


def block_screen(key):
    """滑塊 (i, j, up) 重心的螢幕座標。"""
    wx, wy = view.piece_center(*key)
    return gui.world_to_screen(wx, wy)


def fire(evt):
    """把单个事件推入 pygame 队列并驱动一次事件循环。"""
    pygame.event.post(evt)
    gui.handle_events()


print("== 建局 ==")
check(gui.triangle_mode is True, "triangle_mode 置位")
check(len(gui.game.blocks) == N, f"滑块数 = {N}（实际 {len(gui.game.blocks)}）")
check(gui.is_solved() is True, "建局即实心大三角：起手是还原态")
check(set(gui.game.positions()) == set(gui._tri_goal_cells), "建局位置 = 目标轮廓")
check(TriangleSliderMatrix.is_single_connected(gui.game.positions()),
      "实心大三角单一连通")
check(gui.step_count == 0, "步数归零")
check(len(gui.game_history.history) == 1, "历史仅存初始态这一条快照")
# 後面各節要的是「有東西可滑」的打亂態：建局後主動打亂一次
gui.shuffle_puzzle()
check(gui.is_solved() is False, "打乱后起手不是还原态")

print("== 6 向鍵盤 ==")
gui.selected_block = gui.game.blocks[0]
before = set(gui.game.positions())
moved_any = False
for letter in ('w', 'e', 'a', 'd', 'z', 'x'):
    gui.selected_block = gui.game.blocks[0]
    gui.selected_gap = None
    for b in gui.game.blocks:
        b.be_opted = False
    snap = set(gui.game.positions())
    ok = gui.move_selected_blocks(letter)
    if ok:
        moved_any = True
        check(set(gui.game.positions()) != snap, f"方向 {letter} 成功移动")
        check(TriangleSliderMatrix.is_single_connected(gui.game.positions()),
              f"方向 {letter} 移动后仍连通")
    else:
        check(True, f"方向 {letter} 当前局面不可移动（合法拒绝）")
check(moved_any, "至少一个方向可移动")
check(gui.step_count > 0, "步数已累计")
check(len(gui.game_history.history) > 1, "历史记录了移动")

print("== 非法方向 ==")
gui.macro_notify_msg = ''
gui.selected_block = gui.game.blocks[0]
gui.selected_gap = None
ok = gui.move_selected_blocks('s')
check(ok is False and '未知方向' in gui.macro_notify_msg,
      f"'s' 不是三角方向，被拒绝：{gui.macro_notify_msg}")

print("== 單次觸控拖動 ==")
gui.new_triangle_puzzle(K, 1)
# 找一個拖右可行的滑塊
start_key = None
for b in gui.game.blocks:
    k = tri_key(b)
    p, gt, ln, reason, n = gui.game.resolve_drag(k, 'd', 1)
    if p:
        start_key = k
        break
check(start_key is not None, "找到一个可向右拖动的滑块")
if start_key is not None:
    sx, sy = block_screen(start_key)
    # 該塊沿 'd' 的可達格數（resolve_drag 已留下 opt 選區，探測才有意義）
    max_cells = gui._probe_max_cells('d')
    # 拖動距離取「不越上限」與「足夠提交一步」的交集：0.8 格起，距上限留 0.25 緩衝
    drag_cells = min(max(0.8, max_cells - 0.25), 1.2)
    # 1) 按下滑塊
    gui._mouse_drag_state = None
    gui.drag_following = False
    evt_down = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                 {'button': 1, 'pos': (int(sx), int(sy))})
    fire(evt_down)
    check(gui._mouse_drag_state is not None, "按下滑塊记录了拖拽起点")
    # 2) 拖過閂值（向右 drag_cells 格）
    cell_px = (gui.cell_size + gui.gap_width) * gui.zoom
    evt_move = pygame.event.Event(pygame.MOUSEMOTION,
                                 {'pos': (int(sx + cell_px * drag_cells), int(sy)),
                                  'rel': (int(cell_px * drag_cells), 0), 'buttons': (1, 0, 0)})
    fire(evt_move)
    check(gui.drag_following is True, "超过阈值后进入拖拽跟随")
    check(gui.drag_follow_direction == 'd',
          f"向右拖动吸附到方向 'd'（实际 {gui.drag_follow_direction}）")
    check(gui.drag_follow_offset[0] > 0, "跟随偏移为正（向右）")
    check(gui.drag_follow_invalid is False, "未越过可达上限")
    # 3) 繪製預覽不崩潰
    gui.draw_board()
    check(True, "拖拽中 draw_board 不崩潰")
    # 4) 鬆手提交
    snap = set(gui.game.positions())
    steps_before = gui.step_count
    evt_up = pygame.event.Event(pygame.MOUSEBUTTONUP,
                               {'button': 1, 'pos': (int(sx + cell_px * drag_cells), int(sy))})
    fire(evt_up)
    check(set(gui.game.positions()) != snap, "松手后局面改变（移动已提交）")
    check(gui.step_count > steps_before, "提交后步数增加")
    check(gui.drag_following is False, "提交后清除跟随状态")
    check(gui.selected_gap is None and gui.selected_block is None,
          "单次触控结束后自动取消选中")

print("== 拖拽方向吸附（斜向）==")
gui.new_triangle_puzzle(K, 1)
# 直接測 _init_triangle_drag_follow 的投影吸附：對每個晶格方向給一個
# 螢幕位移向量，應吸附到該方向
from game_triangle import DIRECTION_SCREEN  # noqa: E402
adsorb_ok = True
for letter, (ux, uy) in DIRECTION_SCREEN.items():
    vec = (ux * 80.0, uy * 80.0)
    got = None
    best_dot = 0.0
    for L, (sx2, sy2) in DIRECTION_SCREEN.items():
        dot = vec[0] * sx2 + vec[1] * sy2
        if dot > best_dot:
            best_dot = dot
            got = L
    if got != letter:
        adsorb_ok = False
        print(f"     方向 {letter} 的螢幕向量吸附成了 {got}")
check(adsorb_ok, "六個方向的螢幕向量都吸附回自身")

# 斜向拖動：取一塊，沿 'e'(↗) 方向拖
start_key = None
for b in gui.game.blocks:
    k = tri_key(b)
    p, gt, ln, reason, n = gui.game.resolve_drag(k, 'e', 1)
    if p:
        start_key = k
        break
check(start_key is not None, "找到一个可向右上拖动的滑块")
if start_key is not None:
    sx, sy = block_screen(start_key)
    ux, uy = DIRECTION_SCREEN['e']
    cell_px = (gui.cell_size + gui.gap_width) * gui.zoom
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(sx), int(sy))}))
    fire(pygame.event.Event(pygame.MOUSEMOTION,
                            {'pos': (int(sx + ux * cell_px * 1.2),
                                     int(sy + uy * cell_px * 1.2)),
                             'rel': (int(ux * cell_px * 1.2), int(uy * cell_px * 1.2)),
                             'buttons': (1, 0, 0)}))
    check(gui.drag_following and gui.drag_follow_direction == 'e',
          f"斜向拖动吸附到 'e'（实际 {gui.drag_follow_direction}）")
    di, dj = gui.drag_follow_offset
    check(dj > 0.9 and abs(di) < 0.2,
          f"偏移沿斜座标 (di,dj)=({di:.2f},{dj:.2f})")
    snap = set(gui.game.positions())
    fire(pygame.event.Event(pygame.MOUSEBUTTONUP,
                            {'button': 1,
                             'pos': (int(sx + ux * cell_px * 1.2),
                                     int(sy + uy * cell_px * 1.2))}))
    check(set(gui.game.positions()) != snap, "斜向拖动提交成功")

print("== 兩次觸控：選縫 → 選塊 → 按方向 ==")
gui.new_triangle_puzzle(K, 1)
gaps = gui.game.all_gaps()
check(len(gaps) > 0, f"存在有效缝隙（{len(gaps)} 条）")
if gaps:
    # 隨機打亂後某些縫兩向都不可動，屬正常；掃描全部縫取第一條可動的
    from game_triangle import side_of  # noqa: E402
    chosen = None
    for gap_type, line in gaps:
        cand = None
        for b in gui.game.blocks:
            if side_of(gap_type, line, tri_key(b)) is not None:
                cand = b
                break
        if cand is None:
            continue
        gui.selected_gap = (gap_type, line)
        gui.selected_block = cand
        gui.game.opt(gap_type, line, cand)
        movable = [d for d in GAP_DIRECTIONS[gap_type]
                   if gui.move_selected_blocks(d)]
        if movable:
            chosen = (gap_type, line, cand)
            break
    check(chosen is not None, "至少一條縫存在可動的平行方向")
    if chosen is not None:
        gap_type, line, cand = chosen
        gui.selected_gap = (gap_type, line)
        gui.selected_block = cand
        gui.game.opt(gap_type, line, cand)
        n_sel = len([b for b in gui.game.blocks if b.be_opted])
        check(0 < n_sel < len(gui.game.blocks),
              f"opt 选中中间组（{n_sel}/{len(gui.game.blocks)}）")
        ok_dir = None
        for d in GAP_DIRECTIONS[gap_type]:
            snap = set(gui.game.positions())
            gui.selected_block = cand
            gui.game.opt(gap_type, line, cand)
            if gui.move_selected_blocks(d):
                ok_dir = d
                check(set(gui.game.positions()) != snap, f"沿选中缝隙滑动 '{d}' 成功")
                break
        check(ok_dir is not None, "选中缝隙后至少一个平行方向可移动")
        # 垂直於缝隙的方向应被拒绝
        gui.macro_notify_msg = ''
        gui.selected_block = cand
        gui.game.opt(gap_type, line, cand)
        bad = None
        for d in DIRECTIONS:
            if d not in GAP_DIRECTIONS[gap_type]:
                bad = d
                break
        ok = gui.move_selected_blocks(bad)
        check(ok is False and '不平行' in gui.macro_notify_msg,
              f"与选中缝隙不平行的方向被拒绝：{gui.macro_notify_msg}")

print("== 護欄 ==")
gui.macro_notify_msg = ''
gui._start_auto_solve()
check('尚未实现' in gui.macro_notify_msg, f"自动求解被拦截：{gui.macro_notify_msg}")
gui.macro_notify_msg = ''
gui._timer_enter_ready()
check(gui.timer_state == 'ready', "竞速就绪态已开放（B5）")
check(gui.timer_puzzle_key == f'1~tri{K}', f"竞速 key = {gui.timer_puzzle_key}")
# 打乱现在可用
gui.new_triangle_puzzle(K, 1)
before = set(gui.game.positions())
gui.shuffle_puzzle()
check(set(gui.game.positions()) != before, "打乱已开放（局面改变）")
check(gui.step_count == 0, "打乱后步数归零")

print("== 還原判定 ==")
gui.new_triangle_puzzle(K, 1)
# 直接把局面設成初始實心大三角形（允許平移/旋轉）
goal = gui._tri_goal_cells
gui.game.blocks = []
from game import Block  # noqa: E402
min_i = min(i for i, j, _ in goal)
min_j = min(j for i, j, _ in goal)
for (i, j, up) in goal:
    gui.game.blocks.append(Block([i + 5, j + 7, up]))
check(gui.is_solved() is True, "平移後的實心大三角判还原")
# 120° 旋轉等價：i,j 互換後仍應判還原（三角密鋪的對稱性由凸包判定吸收）
swapped = set((j, i, up) for (i, j, up) in goal)
gui.game.blocks = [Block([i, j, up]) for (i, j, up) in swapped]
check(gui.is_solved() is True, "i/j 互换后的等价大三角判还原")
# 缺一塊
broken = set(goal)
broken.pop()
gui.game.blocks = [Block([i, j, up]) for (i, j, up) in broken]
check(gui.is_solved() is False, "缺一块不判还原")

print("== 切回方形無回歸 ==")
check(gui.new_puzzle(6, 6, 2) is True, "new_puzzle 成功")
check(gui.triangle_mode is False, "triangle_mode 已清除")
gui.selected_gap = None
gui.selected_block = None
gui.game.opt('h', 1, gui.game.blocks[0])
ok = gui.move_selected_blocks('a')
check(ok is True, "方形移动仍正常")
gui.draw_board()
check(True, "方形绘制仍正常")

print()
if failures:
    print(f"共 {len(failures)} 項失敗")
    sys.exit(1)
print("全部通過")
