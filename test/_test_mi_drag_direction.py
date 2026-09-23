# -*- coding: utf-8 -*-
"""米字格「按住并拖动」的定向：位移向量投到已选缝隙的切向定方向。

交互定案（2026-09-22，规划 §3）：米字格**不做单次触控**——不是「一次触控要
同时决定哪条缝＋哪一侧＋朝哪边」，而是单纯的方向太多（八向），手指一抖就滑错，
误触面太大。两次触控里第一下只选缝隙；第二下「按下」只选中滑块组，方向只由
第二下「拖动」给出：位移向量落在选中缝隙**法线的哪一侧**，就是哪一侧
（＝切向投影的符号）。第二下不拖 → 方向留给虚拟键盘。

本文件守五件事：
  1. 第二下按下不拖：只选组、提示「选中滑块组 共N个」、棋盘一步不动，
     松手后再按方向键确能移动（虚拟键盘路径照旧）；
  2. 沿切向拖过一格 → 提交一格，方向 = 该族的正/负方向字母（横竖各两向）；
  3. 纯法向拖动（切向投影落在瞄准容差内）→ 不进跟随、不移动、组仍选中；
  4. 轻拖（切向过了容差、却不到半格）→ 松手不移动；
  5. 拖过可达上限 → 夹紧到上限、提示不可继续。

手势一律走真实事件队列：MOUSEBUTTONDOWN → MOUSEMOTION → MOUSEBUTTONUP，
与玩家手上那一套完全同一条代码路径。位移按块物件比對前後位置得出
（连通组整组平移后中间格被同组块重新占据，位置集合差凑不出位移）。

执行：python test/_test_mi_drag_direction.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_mi import DIRECTIONS as MI_DIRECTIONS  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def mi_key(b):
    return (b.location[0], b.location[1], b.location[2])


def keys():
    """全部 (r, c, q) 的有序表：比對「盤面有沒有變」用。"""
    return sorted(tuple(mi_key(b)) for b in gui.game.blocks)


def snap_ids():
    """塊物件 → (r, c, q)。物件身份不會因移動而變，才能推出位移。"""
    return {id(b): tuple(mi_key(b)) for b in gui.game.blocks}


def move_delta(before, after):
    """比對同一批塊物件的前後位置，推出這一次滑動的 (dr, dc)；
    沒動、或各塊位移不一致時回 None。"""
    moved = [k for k in before if k not in after or after[k] != before[k]]
    if not moved or any(k not in after for k in moved):
        return None
    deltas = {(round(after[k][0] - before[k][0], 3),
               round(after[k][1] - before[k][1], 3)) for k in moved}
    return deltas.pop() if len(deltas) == 1 else None


def fire(evt):
    """把单个事件推入 pygame 队列并驱动一次事件循环。"""
    pygame.event.post(evt)
    gui.handle_events()


def down(pos):
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': pos}))


def move(pos):
    fire(pygame.event.Event(pygame.MOUSEMOTION,
                            {'pos': pos, 'rel': (0, 0), 'buttons': (1, 0, 0)}))


def up(pos):
    fire(pygame.event.Event(pygame.MOUSEBUTTONUP, {'button': 1, 'pos': pos}))


def seam_screen(gt, line, frac=0.3):
    """縫線段 frac 處的屏幕坐标（第一下的落點）。

    線段中點常落在格角/格心（多條單位邊等距 0），那時命中的是平手裁決而
    不是這條縫本身，故取 30% 處。
    """
    seg = view.gap_segment(gt, line, hull)
    if seg is None:
        return None
    wx = seg[0][0] + (seg[1][0] - seg[0][0]) * frac
    wy = seg[0][1] + (seg[1][1] - seg[0][1]) * frac
    sx, sy = gui.world_to_screen(wx, wy)
    return int(round(sx)), int(round(sy))


def block_screen(blk):
    sx, sy = gui.world_to_screen(*view.piece_center(*mi_key(blk)))
    return int(round(sx)), int(round(sy))


def dir_vec(letter, cells=1.0):
    """沿方向字母拖 cells 格的屏幕位移向量。

    「一格」按該字母在 (行,列) 上的位移算：橫豎 = 1、斜向 = ½，所以斜向拖
    一格的屏幕距離是橫豎的 √2/2（與 engine 的 DIRECTIONS 同一把尺）。
    """
    dr, dc = MI_DIRECTIONS[letter]
    s = view.cell_size * gui.zoom
    return (dc * s * cells, dr * s * cells)


def normal_vec(gt, sign, cells=1.0):
    """沿該族法向拖 cells 格的屏幕位移向量（純法向 = 判不出方向的手勢）。"""
    n = gui.MI_GAP_AXES[gt][1]
    s = view.cell_size * gui.zoom
    return (n[0] * sign * s * cells, n[1] * sign * s * cells)


def add(pos, vec):
    return (int(round(pos[0] + vec[0])), int(round(pos[1] + vec[1])))


hull = []


def fresh(gt, line):
    """建新局 + 第一下點選 (gt, line)，回傳該縫的屏幕落點。"""
    global hull
    gui.new_mi_puzzle(6, 6, 1)
    hull = view.board_hull(gui.game.positions())
    gui.selected_gap = None
    gui.selected_block = None
    gui.macro_notify_msg = ''
    sp = seam_screen(gt, line)
    if sp is not None:
        down(sp)
    return sp


def pick_group(direction):
    """當前選中縫下找一塊：它所在的組沿 direction 滑得動一格。"""
    gt, line = gui.selected_gap
    for b in gui.game.blocks:
        gui.game.opt(gt, line, b)
        movable = bool(gui.game.try_move_ex(direction, 1)[0])
        gui.game._clear_selection()
        if movable:
            return b
    return None


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False        # 無頭只讀陷阱：載入後 new_puzzle 會靜默失敗
view = gui._mi_view()

# ================================================================ 1
print("== 1. 第二下按下不拖：只選組，方向留給虛擬鍵盤 ==")
sp = fresh('h', 2)
check("第一下選中橫縫", gui.selected_gap == ('h', 2), str(gui.selected_gap))
BASE = keys()
blk = pick_group('d')
check("找得到可點的塊", blk is not None)
if blk is not None:
    bp = block_screen(blk)
    check("塊內心確實命中該塊", gui.get_block_at_pos(*bp) is blk)
    down(bp)
    n = len([b for b in gui.game.blocks if b.be_opted])
    check("按下只選中滑塊組", 0 < n < len(gui.game.blocks), f"實得 {n} 塊")
    check("提示就是「选中滑块组 共N个」",
          gui.macro_notify_msg == f"选中滑块组 共{n}个", gui.macro_notify_msg or '')
    check("按下這一步棋盤沒動", keys() == BASE)
    up(bp)
    check("鬆手也沒動、步數仍是 0",
          keys() == BASE and gui.step_count == 0, f"step_count={gui.step_count}")
    check("從未進入跟隨", gui.drag_following is False)
    before = snap_ids()
    ok = gui.move_selected_blocks('d', 1)
    check("隨後按方向鍵確能移動一格",
          ok and move_delta(before, snap_ids()) == (0, 1),
          str(move_delta(before, snap_ids())))

# ================================================================ 2
print("== 2. 沿切向拖過一格 → 提交一格，方向由切向符號定 ==")
for gt, line, direction in (('h', 2, 'd'), ('h', 2, 'a'),
                            ('v', 3, 's'), ('v', 3, 'w'),
                            ('d1', 0, 'x'), ('d1', 0, 'q'),
                            ('d2', 4, 'e'), ('d2', 4, 'z')):
    fresh(gt, line)
    check(f"{gt} {line}：第一下選中縫", gui.selected_gap == (gt, line),
          str(gui.selected_gap))
    blk = pick_group(direction)
    check(f"{gt} {line}：有沿 {direction} 滑得動的組", blk is not None)
    if blk is None:
        continue
    base = keys()
    bp = block_screen(blk)
    down(bp)
    n = len([b for b in gui.game.blocks if b.be_opted])
    check(f"{gt} {direction}：按下先選組（{n} 塊）", 0 < n < len(gui.game.blocks))
    to = add(bp, dir_vec(direction, 1.0))
    move(to)
    check(f"{gt} {direction}：進了跟隨且方向鎖定",
          gui.drag_following and gui.drag_follow_direction == direction,
          f"方向={getattr(gui, 'drag_follow_direction', None)}")
    want_u = MI_DIRECTIONS[direction]
    got_u = gui.drag_follow_offset
    check(f"{gt} {direction}：預覽偏移 = 一步 {want_u}",
          abs(got_u[0] - want_u[0]) < 0.01 and abs(got_u[1] - want_u[1]) < 0.01,
          f"實得 {tuple(round(v, 3) for v in got_u)}")
    before = snap_ids()
    up(to)
    check(f"{gt} {direction}：鬆手提交一格",
          move_delta(before, snap_ids()) == want_u,
          str(move_delta(before, snap_ids())))
    check(f"{gt} {direction}：步數 = 1", gui.step_count == 1,
          f"step_count={gui.step_count}")
    check(f"{gt} {direction}：提交後選中態還留著",
          gui.selected_gap == (gt, line)
          and len([b for b in gui.game.blocks if b.be_opted]) == n)
    check(f"{gt} {direction}：盤面確實變了", keys() != base)

# ================================================================ 3
print("== 3. 纯法向拖动：判不出方向，只當選中 ==")
for gt, line, direction in (('h', 2, 'd'), ('v', 3, 's')):
    fresh(gt, line)
    blk = pick_group(direction)
    check(f"{gt} {line}：有可用組合", blk is not None)
    if blk is None:
        continue
    base = keys()
    bp = block_screen(blk)
    down(bp)
    n = len([b for b in gui.game.blocks if b.be_opted])
    to = add(bp, normal_vec(gt, 1, 2.0))
    move(to)
    check(f"{gt}：纯法向拖动不進跟隨", gui.drag_following is False)
    up(to)
    check(f"{gt}：纯法向拖动不移動",
          keys() == base and gui.step_count == 0, f"step_count={gui.step_count}")
    still = len([b for b in gui.game.blocks if b.be_opted])
    check(f"{gt}：滑塊組仍留在選中態", still == n > 0, f"{n} → {still}")

# ================================================================ 4
print("== 4. 轻拖（過了容差、不到半格）：鬆手不移動 ==")
s = view.cell_size * gui.zoom
tol = max(3.0, s / 12.0)
px = max(tol * 1.6, 16.0)
check(f"轻拖像素量夹在容差與半格之間（px={px:.0f} tol={tol:.1f} 半格={s/2:.0f}）",
      tol < px < s * 0.5)
if tol < px < s * 0.5:
    fresh('h', 2)
    blk = pick_group('d')
    check("有可用組合", blk is not None)
    if blk is not None:
        base = keys()
        bp = block_screen(blk)
        down(bp)
        to = add(bp, dir_vec('d', px / s))
        move(to)
        check("輕拖也進跟隨（方向照給）", gui.drag_following is True)
        up(to)
        check("不到半格 → 不移動",
              keys() == base and gui.step_count == 0,
              f"step_count={gui.step_count}")
        check("選中態還在", len([b for b in gui.game.blocks if b.be_opted]) > 0)

# ================================================================ 5
print("== 5. 拖過可達上限：夾緊 + 提示不可繼續 ==")
fresh('h', 2)
blk = pick_group('d')
check("有可用組合", blk is not None)
if blk is not None:
    base = keys()
    bp = block_screen(blk)
    down(bp)
    to = add(bp, dir_vec('d', 1.0))
    move(to)                       # 先進跟隨，才有 max_cells 可讀
    max_cells = gui.drag_follow_max_cells
    print(f"     本方向可達上限 = {max_cells} 格")
    check("讀得到可達上限", max_cells >= 0)
    to = add(bp, dir_vec('d', max_cells + 3.0))
    move(to)
    check("越限時標記 invalid", gui.drag_follow_invalid is True)
    want_u = MI_DIRECTIONS['d']
    got_u = (want_u[0] * max_cells, want_u[1] * max_cells)
    got_off = gui.drag_follow_offset
    check(f"偏移夾緊到 {max_cells} 格",
          abs(got_off[0] - got_u[0]) < 0.01 and abs(got_off[1] - got_u[1]) < 0.01,
          f"實得 {tuple(round(v, 3) for v in got_off)}")
    before = snap_ids()
    up(to)
    check(f"提交的就是 {max_cells} 格",
          move_delta(before, snap_ids()) == (0, max_cells),
          str(move_delta(before, snap_ids())))

print()
if _failures:
    print(f"FAIL {len(_failures)} 项: " + "; ".join(_failures))
    sys.exit(1)
print("mi drag_direction PASS")
pygame.quit()
