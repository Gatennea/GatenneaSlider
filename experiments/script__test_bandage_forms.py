# -*- coding: utf-8 -*-
"""无头验证：三角 / 米字的捆绑内部缝点击 → 判定为选滑块（整组刚性），
以及跨形态的刚性约束（行棋时整组一起动、不能从内部缝切开）。

与 test/_test_bandage_click.py（方形版）同构，只是换成异形坐标。
"""

import os
import queue
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_mi import neighbors as mi_neighbors  # noqa: E402
from game_triangle import neighbors as tri_neighbors  # noqa: E402


def _boot(fn, *args):
    gui = SliderGUI(cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.game_mode = 'practice'
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    getattr(gui, fn)(*args)
    gui._update_in_progress = False
    gui.animation_enabled = False
    return gui


def _scan_gap(gui, target):
    """掃出一個命中 target 縫、且落在棋盤內的屏幕座標。"""
    W, H = gui.screen.get_width(), gui.screen.get_height()
    for y in range(1, H, 2):
        for x in range(1, W, 2):
            if gui.is_blank_area(x, y):
                continue
            if gui.get_gap_at_pos(x, y) == target:
                return (x, y)
    return None


def _seam_click_point(gui, gap, group_cells):
    """兩塊組員共邊的中點 → 屏幕座標（正好落在內部縫線上）。

    比全屏掃描可靠：掃描會在棋盤外沿的退化像素上誤命中（get_gap_at_pos
    對遠處點也會回最近縫）。
    """
    tri_mode = getattr(gui, 'triangle_mode', False)
    mi_mode = getattr(gui, 'mi_mode', False)
    view = (gui._tri_view() if tri_mode
            else gui._mi_view() if mi_mode else None)

    def center(c):
        if tri_mode:
            return view.piece_center(*c)
        if mi_mode:
            return view.piece_center(*c)
        x, y, w, h = gui.board_view.block_rect(*c)
        return (x + w / 2.0, y + h / 2.0)

    for a in group_cells:
        for b in group_cells:
            if tuple(a) >= tuple(b):
                continue
            if gui.game.seam_between_positions(a, b) != gap:
                continue
            ax, ay = center(a)
            bx, by = center(b)
            return gui.world_to_screen((ax + bx) / 2.0, (ay + by) / 2.0)
    return None


def _bind(gui, plan):
    pos = {tuple(b.location): b for b in gui.game.blocks}
    for gid, cells in plan:
        for c in cells:
            assert tuple(c) in pos, f'{c} 不在盤面'
            pos[tuple(c)].group = gid
    return pos


def _click(gui, p):
    gui.macro_notify_msg = None
    gui.macro_notify_timer = 0
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                         button=1, pos=p))
    gui.handle_events()


# ============ 1) 三角 ============
gui = _boot('new_triangle_puzzle', 6, 2)
cells = {tuple(b.location) for b in gui.game.blocks}
# 找一個三鄰塊俱全的 ▲，綁它 + 兩個鄰塊
seed = None
for p in sorted(c for c in cells if c[2] is True):
    on = [n for n in map(tuple, tri_neighbors(p)) if n in cells]
    if len(on) == 3:
        seed, nbs = p, on
        break
assert seed is not None
grp = [seed, nbs[0], nbs[1]]
pos = _bind(gui, [(1, grp)])
bi = gui.game.bandage_internal_seams()
print('三角 group =', grp)
print('三角 内部缝 =', sorted(bi))
assert len(bi) == 2, f'3 塊 V 形應有 2 條內部縫, got {sorted(bi)}'

# 找一條外縫作「已選縫」（不能是內部縫）
idx = {tuple(b.location): i for i, b in enumerate(gui.game.blocks)}
tx, ty = None, None
target = None
for gt, line in [('h', 1), ('h', 2), ('p', 1), ('p', 2), ('n', 1), ('n', 2)]:
    if (gt, line) in bi:
        continue
    if not gui.game.is_valid_gap(gt, line):
        continue
    p2 = _scan_gap(gui, (gt, line))
    if p2:
        target, (tx, ty) = (gt, line), p2
        break
assert target is not None, '找不到可用的外縫'
print('三角 预设外缝 =', target)

gui.selected_gap = target
for b in gui.game.blocks:
    b.be_opted = False
gui.selected_block = None

gi = sorted(bi)[0]
p_in = _seam_click_point(gui, gi, grp)
assert p_in is not None, f'組內找不到共邊 {gi} 的兩塊'
_click(gui, p_in)
msg = gui.macro_notify_msg
print('三角 內部縫點擊反饋 =', repr(msg))
assert '选不动' not in (msg or ''), f'內部縫仍彈「選不動」: {msg!r}'
opted = {tuple(b.location) for b in gui.game.blocks if b.be_opted}
assert set(grp).issubset(opted), f'整組未被選中: opted={sorted(opted)}'
assert gui.selected_gap == target, f'selected_gap 被污染: {gui.selected_gap}'

# 剛性：整組一起走（選一條不切組的縫，向垂直方向走 1 格）
before = {tuple(b.location) for b in gui.game.blocks if b.group == 1}
assert len(before) == 3
print('三角 OK：內部縫→整組選中，共', len(opted), '塊')

# ============ 2) 米字 ============
gui = _boot('new_mi_puzzle', 4, 2)
cells = [tuple(b.location) for b in gui.game.blocks]
cellset = set(cells)
# 取同格四塊整胞
by_cell = {}
for p in cells:
    by_cell.setdefault((int(p[0]), int(p[1])), []).append(p)
quad = [v for v in by_cell.values() if len(v) == 4][0]
pos = _bind(gui, [(7, quad)])
bi = gui.game.bandage_internal_seams()
print('米字 group =', quad)
print('米字 内部缝 =', sorted(bi))
assert len(bi) == 2, f'同格四塊應有 2 條內部縫(對角兩條), got {sorted(bi)}'

target = None
p_out = None
for gt, line in [('h', 1), ('h', 2), ('v', 1), ('v', 2),
                 ('d1', 0), ('d1', 1), ('d2', 0), ('d2', 1)]:
    if (gt, line) in bi or not gui.game.is_valid_gap(gt, line):
        continue
    q = _scan_gap(gui, (gt, line))
    if q:
        target, p_out = (gt, line), q
        break
assert target is not None, '找不到可用的外縫（米字）'
print('米字 预设外缝 =', target)

gui.selected_gap = target
for b in gui.game.blocks:
    b.be_opted = False
gui.selected_block = None

gi = sorted(bi)[0]
p_in = _seam_click_point(gui, gi, quad)
assert p_in is not None, f'組內找不到共邊 {gi} 的兩塊'
_click(gui, p_in)
msg = gui.macro_notify_msg
print('米字 內部縫點擊反饋 =', repr(msg))
assert '选不动' not in (msg or ''), f'內部縫仍彈「選不動」: {msg!r}'
opted = {tuple(b.location) for b in gui.game.blocks if b.be_opted}
assert set(quad).issubset(opted), f'整胞未被選中: opted={sorted(opted)}'
assert gui.selected_gap == target, f'selected_gap 被污染: {gui.selected_gap}'

print('米字 OK：內部縫→整胞選中，共', len(opted), '塊')

# ============ 3) 剛性不變量：opt 永遠把整組拖進選中片 ============
# 「就算選的是一條會把組切開的縫，opt 也要把另一側的組員拖進來」
# ——所有組員同時被選中 ⇒ 移動是整組平移 ⇒ 組永遠切不開。
from game_triangle import side_of as tri_side_of  # noqa: E402
from game_triangle import gap_index_range as tri_gap_range  # noqa: E402

gui = _boot('new_triangle_puzzle', 5, 2)
cells = {tuple(b.location) for b in gui.game.blocks}
pair = None
for p in sorted(c for c in cells if c[2] is True):
    for q in map(tuple, tri_neighbors(p)):
        if q[2] is False and q[0] == p[0] and q[1] == p[1] and q in cells:
            pair = (p, q)
            break
    if pair:
        break
assert pair, '找不到同胞 ▲+▼'
pos = _bind(gui, [(5, list(pair))])
checked = 0
for gt in ('h', 'p', 'n'):
    for line in tri_gap_range(gt, cells):
        if not gui.game.is_valid_gap(gt, line):
            continue
        if tri_side_of(gt, line, pair[0]) == tri_side_of(gt, line, pair[1]):
            continue        # 這條縫不切組，驗不到擴張
        for b in gui.game.blocks:
            b.be_opted = False
        gui.game.opt(gt, line, pos[pair[0]])
        opted2 = {tuple(b.location) for b in gui.game.blocks if b.be_opted}
        assert set(pair).issubset(opted2), (
            f'切組縫 {gt},{line} 上 opt 沒把整組拖進來: {sorted(opted2)}')
        checked += 1
print('三角 剛性不變量 OK：', checked, '條切組縫全部整組選中')
assert checked > 0, '沒驗到任何切組縫'

print('ALL OK')
