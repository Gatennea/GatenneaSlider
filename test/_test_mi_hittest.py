# -*- coding: utf-8 -*-
"""米字格点击裁定：点滑块中部只能算点滑块，绝不能顺手把棋盘滑走。

用户报告（手动测试米字格）：「在不点虚拟键盘、不拖拽的情况下，滑块理应
不动，实际上却动了」。真根因在 gui/mi_view.py 的 gap_at 容差：米字格把每格
按两条对角线切成 4 个直角等腰三角形，單位塊內心到三邊都只有 12.4px，而
玩家瞄的是三角形的視覺中心（畫出去的那個三角的重心），它離最近的一條縫
（格邊）只有約 10px。舊容差 max(4.0, cell_size*0.15) = 9px 已經超過這個
距離，於是「點在方塊中間」有接近一半的概率被裁定成「點在縫上」——而選中
縫之後，下一次點在任何一塊上就走兩次觸控的第二下分支。全程沒碰虛擬鍵盤、
也沒拖拽，滑塊卻自己滑走了。實測（test/_dbg_mi_hit.py）：9px 時塊內均勻
採樣 93% 判成縫、53% 走真實屏幕路徑也判成縫；視覺中心上下抖 4~6px 就有
1/3 誤判。

現在容差取 cell_size/12（一格 60px 時 5px）：縫的可點帶寬 10px，是視覺裂
縫（gap_width=4）的 2.5 倍，視覺中心也還留著 5px 以上的餘量。

本文件守兩件事：
  1. 點方塊中部（含幾像素瞄準誤差）→ 不選中縫、不動棋盤；
  2. 點縫（含裂縫寬度內）→ 照樣選中縫，按住塊拖一格仍提交一步。
只放寬容差會同時破壞 2，只收緊會破壞手感，兩邊都要量。

执行：python test/_test_mi_hittest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_mi import mi_key, mi_vertices  # noqa: E402
from gui.mi_view import _point_seg_dist  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def fire(e):
    pygame.event.post(e)
    gui.handle_events()


def click(sx, sy):
    """一次点击（只发 BUTTONDOWN；位移 0，不会进拖拽分支）。"""
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(sx), int(sy))}))


def drawn_center(key):
    """画出去的那个三角形的重心（玩家眼睛裡「方塊中間」的位置）。"""
    poly = view.piece_polygon(*key, inset=True)
    return (sum(p[0] for p in poly) / 3.0, sum(p[1] for p in poly) / 3.0)


def edge_midpoints(key):
    """三個真實頂點兩兩相連的三條邊中點（都在縫的中心線上）。"""
    verts = [view.to_world(x, y) for (x, y) in mi_vertices(*key)]
    return [((verts[i][0] + verts[(i + 1) % 3][0]) / 2.0,
             (verts[i][1] + verts[(i + 1) % 3][1]) / 2.0)
            for i in range(3)]


# ================================================================ 建局
print("== 建局 ==")
gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False        # 無頭只讀陷阱：載入後 new_puzzle 會靜默失敗
check("new_mi_puzzle 6×6 等級2", gui.new_mi_puzzle(6, 6, 2) is True)
view = gui._mi_view()
cells = gui.game.positions()
hull = view.board_hull(cells)
tol = max(3.0, view.cell_size / 12.0)
check(f"容差 {tol:.1f}px（一格 {view.cell_size}px，視覺裂縫 {view.gap_width}px）",
      tol > 0 and tol < view.cell_size * 0.1)

# ================================================================ 点块中部不算点缝
print("== 點方塊中間不算點縫 ==")
bad_center, bad_jitter, bad_margin = [], [], []
worst = None
for key in sorted(cells):
    poly = view.piece_polygon(*key, inset=True)
    gx, gy = drawn_center(key)
    ix, iy = view.incenter(*key)
    for (wx, wy), what in (((gx, gy), '視覺中心'), ((ix, iy), '內心')):
        if view.gap_at(wx, wy, cells) is not None:
            bad_center.append((key, what))
    # 視覺中心 ±2px（四向 + 四角）：瞄準誤差該被容忍
    for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2),
                   (2, 2), (-2, 2), (2, -2), (-2, -2)):
        if view.gap_at(gx + dx, gy + dy, cells) is not None:
            bad_jitter.append((key, (dx, dy)))
    # 餘量：視覺中心到最近那條縫中心線的距離，扣掉可點半寬
    margin = min(_point_seg_dist(gx, gy, poly[i], poly[(i + 1) % 3])
                 for i in range(3)) + view.gap_width / 2.0 - tol
    if worst is None or margin < worst:
        worst, worst_key = margin, key
    if margin < 2.0:
        bad_margin.append((key, round(margin, 2)))

check(f"全部 {len(cells)} 塊的視覺中心/內心都不選中縫隙（異常 {len(bad_center)}）",
      not bad_center, str(bad_center[:4]))
check(f"視覺中心 ±2px 抖動也不選中縫隙（異常 {len(bad_jitter)}）",
      not bad_jitter, str(bad_jitter[:4]))
check(f"最小的視覺中心餘量 {worst:.1f}px（塊 {worst_key}）≥ 2px",
      not bad_margin, str(bad_margin[:4]))

# ================================================================ 点缝仍选得中
print("== 點縫仍選得中 ==")
bad_seam, bad_crack = [], []
n_edge = 0
for key in sorted(cells):
    for i, (mx, my) in enumerate(edge_midpoints(key)):
        n_edge += 1
        want = view.gap_at(mx, my, cells)
        if want is None:
            bad_seam.append((key, i))
            continue
        # 裂縫內的點（中心線 ±2px，即 gap_width 全寬）也該選中同一條縫：
        # 收容差不能收到比畫出來的裂縫還窄
        p, t = None, None
        verts = [view.to_world(x, y) for (x, y) in mi_vertices(*key)]
        for j in range(3):
            a, b = verts[j], verts[(j + 1) % 3]
            if abs((a[0] + b[0]) / 2.0 - mx) < 1e-9 and \
                    abs((a[1] + b[1]) / 2.0 - my) < 1e-9:
                p, t = a, b
                break
        L = ((t[0] - p[0]) ** 2 + (t[1] - p[1]) ** 2) ** 0.5
        nx, ny = (t[1] - p[1]) / L, -(t[0] - p[0]) / L
        for s in (-view.gap_width / 2.0, view.gap_width / 2.0):
            got = view.gap_at(mx + nx * s, my + ny * s, cells)
            if got != want:
                bad_crack.append((key, i, s, want, got))
check(f"{n_edge} 條單位邊中點都選中縫隙（異常 {len(bad_seam)}）",
      not bad_seam, str(bad_seam[:4]))
check(f"裂縫全寬內的點選中同一條縫（異常 {len(bad_crack)}）",
      not bad_crack, str(bad_crack[:4]))

# ================================================================ 行为层
print("== 不碰虛擬鍵盤、不拖拽：連點方塊中間，棋盤一步都不該動 ==")
gui.new_mi_puzzle(6, 6, 2)
before = set(gui.game.positions())
keys = sorted(cells)
step = max(1, len(keys) // 14)
sample = keys[::step]
bad_move, bad_gap, bad_hit, bad_drag = [], [], [], []
n_click = 0
for key in sample:
    gx, gy = drawn_center(key)
    sx, sy = gui.world_to_screen(gx, gy)
    if gui.get_block_at_pos(int(sx), int(sy)) is None:
        bad_hit.append(key)
        continue
    click(sx, sy)
    n_click += 1
    if gui.selected_gap is not None:
        bad_gap.append((key, gui.selected_gap))
    if gui.drag_following:
        bad_drag.append(key)
    if set(gui.game.positions()) != before:
        bad_move.append(key)
    # 中途把局面恢復回去，讓下一次點擊仍從同一局面出發（逐塊獨立判定）
    if bad_move:
        break
check(f"{n_click} 次點擊都落在塊上（落空 {len(bad_hit)}）",
      n_click >= 10 and not bad_hit, str(bad_hit[:4]))
check(f"{n_click} 次點塊中間，一次縫隙都沒選中（異常 {len(bad_gap)}）",
      n_click >= 10 and not bad_gap, str(bad_gap[:4]))
check(f"從未進入拖拽跟隨（異常 {len(bad_drag)}）", not bad_drag,
      str(bad_drag[:4]))
check(f"棋盤一步都沒動（異常 {len(bad_move)}）", not bad_move, str(bad_move[:4]))
check(f"步數仍是 0（實得 {gui.step_count}）", gui.step_count == 0)
check("局面與開局完全相同", set(gui.game.positions()) == before)

# 两段交替点（A→B→A→B）：幽灵移动的原始形态是「先点到一块、
# 再点到另一块」——两次点击分属不同块才会触发第二下分支
gui.new_mi_puzzle(6, 6, 2)
before = set(gui.game.positions())
pair = [k for k in keys if gui.get_block_at_pos(
    *[int(v) for v in gui.world_to_screen(*drawn_center(k))]) is not None]
for a, b in zip(pair[::2], pair[1::2]):
    click(*gui.world_to_screen(*drawn_center(a)))
    click(*gui.world_to_screen(*drawn_center(b)))
check(f"交替點擊 {len(pair[::2])} 組塊，棋盤仍一步未動",
      set(gui.game.positions()) == before and gui.step_count == 0,
      f"step_count={gui.step_count}")
check("交替點擊後也沒有選中縫隙",
      gui.selected_gap is None)

# ================================================================ 正对照
print("== 正對照：點縫 + 按住塊拖一格仍能提交一步 ==")
gui.new_mi_puzzle(6, 6, 2)
before = set(gui.game.positions())


def probe():
    """找一組（縫, 錨點, 塊, 方向）：第一下點縫、按住塊拖一格能提交一步。"""
    for gt in ('h', 'v', 'd1', 'd2'):
        for line in sorted({l for (g, l) in gui.game.all_gaps() if g == gt}):
            seg = view.gap_segment(gt, line, hull)
            if seg is None:
                continue
            at = (seg[0][0] + (seg[1][0] - seg[0][0]) * 0.3,
                  seg[0][1] + (seg[1][1] - seg[0][1]) * 0.3)
            sx, sy = gui.world_to_screen(*at)
            if gui.get_gap_at_pos(int(sx), int(sy)) != (gt, line):
                continue
            for blk in gui.game.blocks:
                for d in (gui.MI_GAP_AXES[gt][2], gui.MI_GAP_AXES[gt][3]):
                    gui.game.opt(gt, line, blk)
                    movable = bool(
                        gui.game.try_move_ex(d, gui.current_step)[0])
                    gui.game._clear_selection()
                    if movable:
                        return (gt, line), (sx, sy), blk, d
    return None, None, None, None


gap, anchor_xy, blk, direction = probe()
check("找到可用的縫＋塊＋方向", gap is not None, str(gap))
if gap is not None:
    before = set(gui.game.positions())
    # 先問出這次會動的是哪一組（與兩次觸控選中的是同一組）
    gui.game.opt(gap[0], gap[1], blk)
    group = {mi_key(b) for b in gui.game.blocks if b.be_opted}
    gui.game._clear_selection()
    check(f"選中組共 {len(group)} 塊", len(group) > 0)
    click(*anchor_xy)
    check(f"第一下點縫選中 {gap}", gui.selected_gap == gap)
    check("選縫時沒有動過棋盤", set(gui.game.positions()) == before)
    bsx, bsy = gui.world_to_screen(*view.piece_center(*mi_key(blk)))
    click(bsx, bsy)
    check("第二下先選中滑塊組、還沒有提交",
          gui.selected_block is blk and gui.step_count == 0,
          f"step_count={gui.step_count}")
    # 位移向量沿該族切向、正向 → 拖一格
    tangent = gui.MI_GAP_AXES[gap[0]][0]
    sign = 1.0 if direction == gui.MI_GAP_AXES[gap[0]][2] else -1.0
    step_px = view.cell_size * gui.zoom
    tx = int(round(bsx + tangent[0] * sign * step_px))
    ty = int(round(bsy + tangent[1] * sign * step_px))
    fire(pygame.event.Event(pygame.MOUSEMOTION,
                            {'pos': (tx, ty), 'rel': (0, 0),
                             'buttons': (1, 0, 0)}))
    check(f"位移向量落在切向{'正' if sign > 0 else '負'}側 → 方向 {direction}",
          gui.drag_following and gui.drag_follow_direction == direction,
          f"實得 {getattr(gui, 'drag_follow_direction', None)}")
    fire(pygame.event.Event(pygame.MOUSEBUTTONUP, {'button': 1, 'pos': (tx, ty)}))
    check("鬆手提交了一步", gui.step_count == 1,
          f"step_count={gui.step_count}")
    check("局面確實變了", set(gui.game.positions()) != before)
    from game_mi import DIRECTIONS as MI_DIR
    dv = MI_DIR[direction]
    moved = {(r + dv[0] * gui.current_step, c + dv[1] * gui.current_step, q)
             for (r, c, q) in group}
    expect = moved | (before - group)
    check(f"選中組沿 {direction} 移動 {gui.current_step} 格，其餘不動",
          set(gui.game.positions()) == expect)

print()
if _failures:
    print(f"共 {len(_failures)} 項失敗:")
    for n in _failures:
        print("  -", n)
    sys.exit(1)
print("全部通過")
