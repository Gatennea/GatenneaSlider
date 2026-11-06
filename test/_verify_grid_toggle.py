# -*- coding: utf-8 -*-
"""离屏验证「绘制网格」开关：四种原版盘（矩形/数字/三角/米字）。

验收口径（2026-11-06 用户第四轮校正）：
  关 = 只画相邻滑块的公共边 —— 滑块相接处有缝线，空位/洞口一律无。
即「开」与「关」的差异**只应该出现在空位/洞口**，块与块相接处两者都该有线。

为了让空位可见，先手动删掉盘面中间几块造出洞，再各渲染 开/关 两帧：
  - 统计 colors['gap'] / colors['grid'] 像素数（开≠关 才算生效）；
  - 存图供人工核对空位是否干净。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
from GUI import SliderGUI

_HERE = os.path.dirname(os.path.abspath(__file__))


def count_color(surf, color):
    """统计与给定 RGB 完全相等的像素数。"""
    px = pygame.surfarray.array3d(surf)
    r, g, b = color
    mask = (px[:, :, 0] == r) & (px[:, :, 1] == g) & (px[:, :, 2] == b)
    return int(mask.sum())


def render_pair(gui, label):
    gap = gui.colors['gap'][:3]
    grid = gui.colors['grid'][:3]
    out = {}
    for state in (True, False):
        gui.draw_grid = state
        gui.draw_board()
        out[state] = (count_color(gui.screen, gap), count_color(gui.screen, grid))
        tag = 'ON' if state else 'OFF'
        pygame.image.save(
            gui.screen, os.path.join(_HERE, f'_verify_grid_{label}_{tag}.png'))
    gui.draw_grid = True
    return out


def drop(gui, pred, label):
    before = len(gui.game.blocks)
    gui.game.blocks = [b for b in gui.game.blocks if not pred(b)]
    print(f"  [{label}] blocks {before} -> {len(gui.game.blocks)}")


def check_empty_clean(gui, screen_points, label):
    """关网格状态下，空位（被挖掉的块）中心必须是纯背景色。

    这是「不接的地方都没线」的量化判据：整条缝线沿凸包拉通的做法会让
    这些点落在灰色线上，改成「只画相接处/铺块底」后应当全部是背景色。
    """
    bg = tuple(gui.colors['background'][:3])
    bad = []
    for (sx, sy) in screen_points:
        sx, sy = int(round(sx)), int(round(sy))
        if 0 <= sx < gui.screen.get_width() and 0 <= sy < gui.screen.get_height():
            px = tuple(gui.screen.get_at((sx, sy))[:3])
            if px != bg:
                bad.append(((sx, sy), px))
    print(f"  [{label}] 空位中心 {len(screen_points)} 点，非背景 {len(bad)} 点"
          + (f"，例：{bad[:3]}" if bad else "  OK"))
    return bad


def check_seam_present(gui, screen_pt, label):
    """相接处必须有缝色——「所有滑块相接的地方都有线」的量化判据。"""
    sx, sy = int(round(screen_pt[0])), int(round(screen_pt[1]))
    px = tuple(gui.screen.get_at((sx, sy))[:3])
    ok = px == tuple(gui.colors['gap'][:3])
    print(f"  [{label}] 相接处像素 {px} " + ("OK" if ok else "FAIL(应为 gap 色)"))
    return ok


def shared_edge_mid(view, ka, kb):
    """两块未内缩多边形的公共边中点（世界坐标）；不共享边回 None。"""
    pa = view.piece_polygon(*ka, inset=False)
    pb = view.piece_polygon(*kb, inset=False)
    common = [p for p in pa
              if any(abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6
                     for q in pb)]
    if len(common) != 2:
        return None
    return ((common[0][0] + common[1][0]) / 2.0,
            (common[0][1] + common[1][1]) / 2.0)


gui = SliderGUI(m=5, n=5, step=1)
gui.animation_enabled = False

# ---------- 矩形（与数字同一套绘制路径，数字只是多画编号） ----------
gui.new_puzzle(5, 5, 1)
drop(gui, lambda b: tuple(b.location) in {(2, 2), (2, 3)}, 'rect')
rect_res = render_pair(gui, 'rect')
_cell, _gap, _step = gui._board_px()
check_empty_clean(gui, [(c * _step + _cell / 2 + gui.camera_x,
                         r * _step + _cell / 2 + gui.camera_y)
                        for (r, c) in [(2, 2), (2, 3)]], 'rect')

# ---------- 数字 ----------
gui.new_puzzle(5, 5, 1)
gui.numbered = True
drop(gui, lambda b: tuple(b.location) in {(2, 2), (2, 3)}, 'num')
num_res = render_pair(gui, 'num')
check_empty_clean(gui, [(c * _step + _cell / 2 + gui.camera_x,
                         r * _step + _cell / 2 + gui.camera_y)
                        for (r, c) in [(2, 2), (2, 3)]], 'num')
check_seam_present(gui, (1 * _step + _cell / 2 + gui.camera_x,
                         2 * _step + _cell + _gap / 2 + gui.camera_y), 'num')

# ---------- 米字 ----------
from game_mi import mi_key  # noqa: E402

gui.new_mi_puzzle(4, 4, 1)
drop(gui, lambda b: tuple(mi_key(b)[:2]) in {(2, 2), (2, 3)}, 'mi')
mi_res = render_pair(gui, 'mi')
_mv = gui._mi_view()
check_empty_clean(gui, [gui.world_to_screen(*_mv.piece_center(r, c, q))
                        for (r, c) in [(2, 2), (2, 3)]
                        for q in ('N', 'S', 'E', 'W')], 'mi')
_m = shared_edge_mid(_mv, (1, 1, 'N'), (1, 1, 'W'))
check_seam_present(gui, gui.world_to_screen(*_m), 'mi')

# ---------- 三角 ----------
from game_triangle import tri_key  # noqa: E402

try:
    gui.new_triangle_puzzle(4, 1)
    drop(gui, lambda b: tuple(tri_key(b)) in
         {(1, 1, True), (1, 1, False), (2, 1, True)}, 'tri')
    tri_res = render_pair(gui, 'tri')
    _tv = gui._tri_view()
    check_empty_clean(gui, [gui.world_to_screen(*_tv.piece_center(*k))
                            for k in [(1, 1, True), (1, 1, False), (2, 1, True)]],
                      'tri')
    _m = shared_edge_mid(_tv, (0, 0, True), (0, 0, False))
    check_seam_present(gui, gui.world_to_screen(*_m), 'tri')
except Exception as e:
    tri_res = f"ERR: {e}"

print("colors['gap'] =", gui.colors['gap'], " colors['grid'] =", gui.colors['grid'])
print("RECT (gap,grid) ON/OFF:", rect_res)
print("NUM  (gap,grid) ON/OFF:", num_res)
print("MI   (gap,grid) ON/OFF:", mi_res)
print("TRI  (gap,grid) ON/OFF:", tri_res)
