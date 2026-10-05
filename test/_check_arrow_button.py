# -*- coding: utf-8 -*-
"""箭头按键（贴图版）验收：三形态 / 跟随 / 缩放只跟 zoom / 点击=虚拟键盘 / 禁用不画。

执行：``D:/python/python.exe -u test/_check_arrow_button.py``
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402

FAILS = []


def check(cond, msg):
    print(('   OK   ' if cond else '   FAIL ') + msg)
    if not cond:
        FAILS.append(msg)


def centres(gui):
    """重算几何，返回 [(方向, 中心, 角度, 可走)]。"""
    annot = gui._get_gap_direction_annotation()
    return annot['buttons'] if annot else []


gui = SliderGUI(m=5, n=5, step=1)
gui.animation_enabled = False
gui.ui_mode = 'enhanced'
pygame.display.set_mode((1200, 800))
gui.screen = pygame.display.get_surface()

# ------------------------------------------------------------------ 方形
print('\n===== 方形 5×5 横缝 h=2 =====')
gui.new_puzzle(5, 5, 1)
anchor = gui.game.blocks[0]
gui.game.opt('h', 2, anchor)
gui.selected_gap = ('h', 2)
gui.selected_block = anchor
gui.draw_board()
btns = centres(gui)
check(len(btns) == 2, f'两端几何都算出来（{len(btns)}）')
size = gui._arrow_button_size()
check(all(abs(gui._arrow_sprite(a).get_width() - gui._arrow_sprite(a).get_height()) <= 0
          for _d, _c, a, _m in btns), '贴图为正方画布')
check(len(gui._arrow_buttons) >= 1, f'命中矩形已生成（{len(gui._arrow_buttons)}，禁用端不算）')
for d, (ax, ay), ang, mv in btns:
    check(0 <= ax <= gui.screen_width and 0 <= ay <= gui.screen_height,
          f'端 {d} 中心在屏内 ({ax:.0f},{ay:.0f})')

# ---- 缩放：大小只跟 zoom 走，方向无关
print('\n===== 缩放（只跟 zoom，与方向无关）=====')
s1 = [gui._arrow_sprite(a).get_width() for _d, _c, a, _m in btns]
gui.zoom = 1.6
s2 = [gui._arrow_sprite(a).get_width() for _d, _c, a, _m in centres(gui)]
check(max(s2) == min(s2), f'zoom=1.6 时各方向同尺寸 {set(s2)}')
check(max(s2) > max(s1), f'zoom 变大 → 按键变大 {max(s1)} → {max(s2)}')
check(max(s2) == max(gui._arrow_sprite(a).get_width()
                     for _d, _c, a, _m in centres(gui)), '缩放结果与方向无关')
gui.zoom = 1.0

# ---- 平移：camera 变了按键跟着走
print('\n===== 平移跟随 =====')
before = {d: c for d, c, _a, _m in centres(gui)}
gui.camera_x += 60
after = {d: c for d, c, _a, _m in centres(gui)}
check(all(abs(after[d][0] - before[d][0] - 60) < 0.6 for d in before),
      'camera_x +60 → 按键中心同步 +60px')
gui.camera_x -= 60

# ---- 拖拽跟随：drag_follow_offset 生效（用户报的「箭头留原地」）
print('\n===== 拖拽跟随（核心回归）=====')
before = {d: c for d, c, _a, _m in centres(gui)}
gui.drag_following = True
gui.drag_follow_offset = (0.0, 1.0)     # 沿列方向拖 1 格
after = {d: c for d, c, _a, _m in centres(gui)}
moved = {d: (after[d][0] - before[d][0], after[d][1] - before[d][1]) for d in before}
check(all(abs(dx) + abs(dy) > 1 for dx, dy in moved.values()),
      f'拖拽 1 格 → 按键跟着挪动 { {d: (round(v[0]), round(v[1])) for d, v in moved.items()} }')
step_px = gui.cell_size * gui.zoom + gui.gap_width * gui.zoom
check(all(abs(abs(dx) - step_px) < 1.5 for dx, dy in moved.values()),
      f'位移量 = 一格 {step_px:.1f}px（不是整格倍数也不是 0）')
gui.drag_following = False
gui.drag_follow_offset = (0.0, 0.0)

# ---- 点击 = 虚拟键盘（走 1 格）
print('\n===== 点击按键（与虚拟键盘同效果）=====')
gui.draw_board()
hit_dir = None
for d, rect in gui._arrow_buttons:
    hit_dir = d
    cx, cy = rect.center
    break
check(gui._arrow_button_hit(cx, cy) == hit_dir, f'命中检测返回方向 {hit_dir}')
check(gui._arrow_button_hit(cx - 500, cy) is None, '远处不命中')

before_hist = len(gui.game_history.history)
before_pos = {id(b): tuple(b.location) for b in gui.game.blocks if b.be_opted}
gui._arrow_button_click(hit_dir)
after_pos = {id(b): tuple(b.location) for b in gui.game.blocks}
moved_blocks = sum(1 for k, v in before_pos.items() if after_pos.get(k) != v)
check(moved_blocks == len(before_pos), f'点击后选中切片整体移动（{moved_blocks}/{len(before_pos)} 块）')
check(len(gui.game_history.history) > before_hist,
      f'历史步进 +{len(gui.game_history.history) - before_hist}（与虚拟键盘同为一次移动）')

# ---- 鼠标锚点：按键摆在上一次选中滑块的那一点两侧
print('\n===== 鼠标锚点（选中滑块那一下的位置）=====')
import math  # noqa: E402
gui.new_puzzle(5, 5, 1)
anchor = gui.game.blocks[0]
gui.game.opt('h', 2, anchor)
gui.selected_gap = ('h', 2)
gui.selected_block = anchor
mx, my = gui.screen_width // 2, int(gui.screen_height * 0.35)
gui._gap_anchor_world = gui.screen_to_world(mx, my)
btns_m = centres(gui)
(d_a, c_a, _a1, _m1), (d_b, c_b, _a2, _m2) = btns_m
mid = ((c_a[0] + c_b[0]) / 2, (c_a[1] + c_b[1]) / 2)
check(abs(mid[0] - mx) < 1.0 and abs(mid[1] - my) < 1.0,
      f'两按键中点 = 鼠标点 ({mid[0]:.0f},{mid[1]:.0f}) vs ({mx},{my})')
check(abs(math.dist(c_a, c_b) - 1.6 * gui._arrow_button_size()) < 2.0,
      f'两键间距 = 1.6×边长（{math.dist(c_a, c_b):.0f}px，不互相吃点击）')
axis = (c_b[0] - c_a[0], c_b[1] - c_a[1])
check(abs(axis[1]) < 1.0, '横缝：两键沿水平推行轴分列左右（不是上下）')
m_before = {d: c for d, c, _a, _m in btns_m}
gui.camera_y += 40
btns_p = {d: c for d, c, _a, _m in centres(gui)}
check(all(abs(btns_p[d][1] - m_before[d][1] - 40) < 0.6 for d in btns_p),
      'camera_y +40 → 按键随该棋盘位置移动（记的是世界坐标，不是死的屏幕点）')
gui.camera_y -= 40
gui._gap_anchor_world = None
fallback = {d: c for d, c, _a, _m in centres(gui)}
check(any(abs(fallback[d][1] - m_before[d][1]) > 1 for d in fallback),
      '清空锚点 → 回退到切片外沿（几何照旧算得出）')

# ---- 禁用端不画、也不给点击
print('\n===== 禁用态（不画、不可点）=====')
# 初始盘是满盘（25 块无空位），两端都走得动，造不出天然的禁用端。
# 直接注入 maxstep（几何里唯一判断可走否的输入）来验收这段分支。
gui.new_puzzle(5, 5, 1)
anchor = gui.game.blocks[0]
gui.game.opt('h', 2, anchor)
gui.selected_gap = ('h', 2)
gui.selected_block = anchor
bt = centres(gui)
d0, d1 = bt[0][0], bt[1][0]
gui._gap_maxstep = {d0: 0, d1: 0}          # 两端都走不动
bt2 = centres(gui)
check(all(not mv for _d, _c, _a, mv in bt2), 'maxstep=0 → 两端判为禁用')
check(not gui._arrow_buttons, '禁用端不生成命中矩形（画与命中同源）')
gui._gap_maxstep = {d0: 3, d1: 0}          # 只一端可走
bt3 = centres(gui)
check([d for d, _r in gui._arrow_buttons] == [d0],
      f'只有可走端 {d0} 有命中矩形（另一端 {d1} 禁用）')

# ------------------------------------------------------------------ 三角 / 米字
print('\n===== 三角 =====')
gui.new_triangle_puzzle(3, 1)
if hasattr(gui, '_fit_triangle_zoom'):
    gui._fit_triangle_zoom()
gui._center_triangle()
from game_triangle import gap_index_range  # noqa: E402
cells = gui.game.positions()
rng = gap_index_range('n', cells)
line = rng[len(rng) // 2]
tb = gui.game.blocks[len(gui.game.blocks) // 2]
gui.game.opt('n', line, tb)
gui.selected_gap = ('n', line)
gui.selected_block = tb
gui.draw_board()
btns_tri = centres(gui)
check(len(btns_tri) == 2, f'三角两端几何算出来（{len(btns_tri)}）')
check(bool(gui._arrow_buttons), '三角命中矩形已生成')
b0 = {d: c for d, c, _a, _m in btns_tri}
gui.drag_following = True
gui.drag_follow_offset = (0.5, 0.0)
b1 = {d: c for d, c, _a, _m in centres(gui)}
gui.drag_following = False
gui.drag_follow_offset = (0.0, 0.0)
check(all(abs(b1[d][0] - b0[d][0]) + abs(b1[d][1] - b0[d][1]) > 1 for d in b0),
      '三角：拖拽跟随时按键跟着走')

print('\n===== 米字 =====')
gui.new_mi_puzzle(3, 3, 1)
gui._fit_mi_zoom()
gui._center_mi()
mb = gui.game.blocks[len(gui.game.blocks) // 2]
gui.game.opt('d1', 0, mb)
gui.selected_gap = ('d1', 0)
gui.selected_block = mb
gui.draw_board()
btns_mi = centres(gui)
check(len(btns_mi) == 2, f'米字两端几何算出来（{len(btns_mi)}）')
check(bool(gui._arrow_buttons), '米字命中矩形已生成')
m0 = {d: c for d, c, _a, _m in btns_mi}
gui.drag_following = True
gui.drag_follow_offset = (0.0, 0.5)
m1 = {d: c for d, c, _a, _m in centres(gui)}
gui.drag_following = False
gui.drag_follow_offset = (0.0, 0.0)
check(all(abs(m1[d][0] - m0[d][0]) + abs(m1[d][1] - m0[d][1]) > 1 for d in m0),
      '米字：拖拽跟随时按键跟着走')

# ---- 朴素模式不画
print('\n===== 朴素模式 =====')
gui.ui_mode = 'plain'
check(gui._arrow_button_hit(0, 0) is None, 'plain 模式不生成按键')
gui.ui_mode = 'enhanced'

print('\n===== 结论 =====')
print('全部通过' if not FAILS else f'{len(FAILS)} 项失败：')
for f in FAILS:
    print('  -', f)
