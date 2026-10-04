# -*- coding: utf-8 -*-
"""米字格调试面板（F2，M3）無頭測試。

執行：``D:/python/python.exe -u test/_test_mi_panel.py``

覆蓋：
  P1 `_mp_kind` / `_MP_SUPPORTED`：mi 算「已实装」而非「未实装」；
  P2 `_mp_current_metrics`：走 `mi_placement.best_placement`（**不是**方形
     `find_best_window`），還原態 score=1.0、overlap=4mn；
  P3 `_compute_target_region` 返回 `MiPlacement`，且**畫框與記號吃同一個
     對象**（計劃 §4 铁律：面板與求解器同源）；
  P4 `_draw_mi_target_frame` / `_draw_mi_marks` 真畫出東西（不拋異常、
     屏幕像素有變化），且錯位態下框仍在屏內（半格偏移不讓框飛出去）；
  P5 `get_hole_at_pos` 命中判定與 `_draw_mi_marks` 錨點是**同一個點**
     （紀律：能點到的洞 = 畫出的標記）；
  P6 選洞樣本落盤（`samples_mi.jsonl`）含片級 + 格級兩套坐標；
  P7 方形/三角形兩條老路徑未改坏（回歸）。
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI                       # noqa: E402
from game_mi import MiSliderMatrix              # noqa: E402
import solver.ml.mi_adapter as MA               # noqa: E402
from solver.ml.mi_placement import (            # noqa: E402
    MiPlacement, best_placement, goal_shapes, mod_auts)
from solver.ml.mi_holes import detect_mi_holes  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def screen_signature(gui):
    """屏幕像素簽名（用來證明「真畫出東西」）。

    用 `pygame.image.tobytes` 而非已弃用的 `tostring`（pygame-ce 2.3+ 会打
    DeprecationWarning，污染 -u 的輸出）。
    """
    return pygame.image.tobytes(gui.screen, 'RGB')


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False
gui.show_metrics_panel = True

# ================================================================ P1 支持表
print("\n--- P1 形态支持表：mi 算已实装 ---")
# 注意：启动时 GUI 会恢复上次存档（本机是三角局），所以初始 _mp_kind 是
# triangle 而非 square —— 断言「初始形态」前先显式建一个方形局更稳。
check("P1a 初始局 _mp_kind 與恢復的檔案一致（兩個形態旗標互斥）",
      gui._mp_kind() in ('square', 'triangle', 'mi')
      and not (gui.mi_mode and gui.triangle_mode),
      f"初始={gui._mp_kind()}")
gui.new_puzzle(4, 4, 2)
check("P1a2 方形局 _mp_kind = square", gui._mp_kind() == 'square')
gui.new_mi_puzzle(4, 4, 2)
check("P1b mi 局下 _mp_kind = mi", gui._mp_kind() == 'mi')
check("P1c mi 已在 _MP_SUPPORTED 裡（不再是「未实装」）",
      'mi' in gui._MP_SUPPORTED and 'mi' in gui._MP_SUPPORTED)
check("P1d 未实装文案分支對 mi 已讓位",
      '本形态尚未实装' not in str(gui._mp_unsupported_rows()))

# ================================================================ P2 指标
print("\n--- P2 指标走 mi_placement（計劃 §4 同源铁律）---")
gui.game.shuffle(0, 2)                      # 打乱 → 非還原態
met = gui._mp_current_metrics()
check("P2a 指標不是 None（mi 已实装）", met is not None)
gui.new_mi_puzzle(4, 4, 2)                  # 回到還原態
met = gui._mp_current_metrics()
check("P2c 還原態 聚拢度 100%",
      abs(met['score'] - 1.0) < 1e-9, f"{met['score']:.4f}")
check("P2d 還原態 重叠 = 4mn = 64", met['overlap'] == 64, str(met['overlap']))
check("P2e 填充率 = 1.0", abs(met['fill_rate'] - 1.0) < 1e-9)

# 與 best_placement 直接调用同值（同源验证）
coords = MA.mi_coords(gui.game)
direct = best_placement(coords, 4, 4, 2)
check("P2f 面板指标 == 直接 best_placement（同源，不是另算一份）",
      abs(met['score'] - direct.score) < 1e-12
      and met['overlap'] == direct.overlap)

# m≠n：两个形状枚举都在
gui.new_mi_puzzle(3, 5, 2)
met = gui._mp_current_metrics()
check("P2g 3×5 還原態 聚拢度 100% 且 重叠 = 4·3·5 = 60",
      abs(met['score'] - 1.0) < 1e-9 and met['overlap'] == 60,
      f"{met['score']:.4f} / {met['overlap']}")
check("P2h goal_shapes(3,5) 两形状且 m==n 时去重",
      len(goal_shapes(3, 5)) == 2 and len(goal_shapes(4, 4)) == 1)

# ================================================================ P3 目标窗口
print("\n--- P3 目标窗口返回 MiPlacement，且框/记号同源 ---")
gui.new_mi_puzzle(4, 4, 2)
region = gui._compute_target_region()
check("P3a _target_region 是 MiPlacement", isinstance(region, MiPlacement))
check("P3b _compute_target_region 把结果缓存进 _target_region",
      gui._target_region is region)
check("P3c placement 带 lattice 档 + 单元数 = 4mn（goal_shapes 是单元集）",
      region.lattice in (0, 1) and len(region.cells) == 4 * 4 * 4
      and len(goal_shapes(4, 4)) == 1,
      f"lattice={region.lattice} cells={len(region.cells)} "
      f"goal_shapes={len(goal_shapes(4,4))}")
# step=2 时 S = {(0,0),(1,1)}（实测值，不是「step 倍数」——见 _mi_mod_probe.py）
check("P3d mod_auts(4,4,2) == {(0,0),(1,1)} 且 step=1 时只有 (0,0)",
      set(mod_auts(4, 4, 2)) == {(0, 0), (1, 1)}
      and set(mod_auts(4, 4, 1)) == {(0, 0)},
      f"S(2)={sorted(mod_auts(4,4,2))} S(1)={sorted(mod_auts(4,4,1))}")

# 打乱后仍返回合法 placement（不崩、score 下降）
gui.game.shuffle(30, 2)
region2 = gui._compute_target_region()
check("P3e 打乱後仍是 MiPlacement 且 score < 1.0",
      isinstance(region2, MiPlacement) and region2.score < 1.0,
      f"score={region2.score:.3f}")

# ================================================================ P4 真画
print("\n--- P4 真畫出東西（目標框 + 記號）---")
gui.new_mi_puzzle(4, 4, 2)
gui.show_metrics_panel = True
gui._compute_target_region()
before = screen_signature(gui)
gui._draw_mi_target_frame()
after_frame = screen_signature(gui)
check("P4a _draw_mi_target_frame 真的改了屏幕像素（框畫出來了）",
      before != after_frame)

gui.screen.fill((0, 0, 0))
before2 = screen_signature(gui)
gui._draw_mi_marks()
after_marks = screen_signature(gui)
# 还原态**本来就该一个记号都不画**（无洞、无缺口、无凸起）——「像素无变化」
# 才是正确行为，这条要反过来当断言用：先确认还原态确实干净。
check("P4b 還原態無洞無凸起 → 一個記號都不畫（像素不變）",
      before2 == after_marks)

# 有洞的局面：抽掉正中一格 (1,1) 的**全部四片** → 該格成洞
# （mi 還原態的塊坐標是整數格 + NESW 四片，半整數只在錯位態出現）
gui.new_mi_puzzle(4, 4, 2)
g = gui.game
removed = [b for b in list(g.blocks)
           if b.location[0] == 1 and b.location[1] == 1]
check("P4c 正中格 (1,1) 有 4 片（測試前提）", len(removed) == 4,
      f"{len(removed)} 片，q={[b.location[2] for b in removed]}")
for b in removed:
    g.blocks.remove(b)
g.update_matrix()
gui._compute_target_region()
holes, _ = detect_mi_holes(MA.mi_coords(g), gui._target_region.cells, 2)
check("P4d 抽一整格 → 1 個洞且 type=hole",
      len(holes) == 1 and holes[0]['type'] == 'hole',
      f"{[(h['type'], h['size'], len(h['cells'])) for h in holes]}")
# **鎖住一個用戶驗收發現的 bug（2026-10-04）**：記號曾畫在**格心**，
# 而 mi 一格有 N/E/S/W 四片 —— 四片的記號全疊在同一點。正確錨點是
# 每一片自己的**內心**（實測四個內心兩兩相距 0.414 格，分得開）。
# 這裡直接驗「四片記號的屏幕坐標兩兩不重合」，讓這個 bug 無法悄悄回來。
check("P4e 洞帶片級 cells（缺 4 片 = 4 個記號，不是 1 個）",
      len(holes[0]['cells']) == 4, str(sorted(holes[0]['cells'])))
_pts = [gui._mi_mark_center(r, c, q) for (r, c, q) in holes[0]['cells']]
_mind = min(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
            for i, a in enumerate(_pts) for b in _pts[i + 1:])
check("P4e2 四片記號的屏幕坐标兩兩分開（不是疊在一點）", _mind > 8,
      f"最小間距 {_mind:.1f}px（舊版格心方案 = 0）")
gui.screen.fill((0, 0, 0))
b4 = screen_signature(gui)
gui._draw_mi_marks()
check("P4f 有洞時記號畫出來了", b4 != screen_signature(gui))

# 錯位態：半格偏移下框不能飛出屏
print("\n--- P4' 錯位態：半格偏移不讓框飛出屏 ---")
gui.new_mi_puzzle(4, 4, 2)
gui.current_step = 1
# 人造一个错位態：整盘滑半格
moved = 0
for b in gui.game.blocks:
    if b.location[0] == round(b.location[0]) or True:
        b.location[0] += 0.5
        b.location[1] += 0.5
        moved += 1
gui.game.update_matrix()
gui._compute_target_region()
has_half = any(abs(c[0] - round(c[0])) > 1e-9
               for c in MA.mi_coords(gui.game))
check("P4g 造出了錯位態（坐標含半整數）", has_half, f"{moved} 塊已平移")
gui.screen.fill((0, 0, 0))
b5 = screen_signature(gui)
region3 = gui._draw_mi_target_frame()
check("P4h 錯位態下畫框不拋異常且返回 region", isinstance(region3, MiPlacement))
drawn_ok = b5 != screen_signature(gui)
check("P4i 錯位態下框仍畫在屏內（像素有變化）", drawn_ok)
# 框的四角必须在屏内（用外接框数值验证，不是肉眼看）
bb = gui._mi_goal_bbox(region3.cells)
view = gui._mi_view()
r0, c0, hh, ww = bb
# 两层分开调：to_world 返回 (x, y) 元组，要拆开喂给 world_to_screen(x, y)
wx0, wy0 = view.to_world(c0, r0)
wx1, wy1 = view.to_world(c0 + ww, r0 + hh)
x0, y0 = gui.world_to_screen(wx0, wy0)
x1, y1 = gui.world_to_screen(wx1, wy1)
in_screen = (0 <= min(x0, x1) and max(x0, x1) <= gui.screen_width
             and 0 <= min(y0, y1) and max(y0, y1) <= gui.screen_height)
check("P4j 錯位態框的外接矩形完全在屏內", in_screen,
      f"x=[{min(x0,x1):.0f},{max(x0,x1):.0f}] "
      f"y=[{min(y0,y1):.0f},{max(y0,y1):.0f}] "
      f"屏={gui.screen_width}×{gui.screen_height}")

# ================================================================ P5 命中=繪製
print("\n--- P5 命中判定與繪製錨點同一點 ---")
gui.new_mi_puzzle(4, 4, 2)
gui.current_step = 2
g = gui.game
# 抽掉一整格 (2,2) 的四片 → 該格成洞
for b in list(g.blocks):
    if b.location[0] == 2 and b.location[1] == 2:
        g.blocks.remove(b)
g.update_matrix()
gui._compute_target_region()
# 直接用 _mi_mark_center 取屏幕点（這正是「能點到的洞 = 畫出的標記」的錨點）。
# 錨點是**每一片自己的內心**，所以要給 q。
cx, cy = gui._mi_mark_center(2, 2, 'N')
hit = gui.get_hole_at_pos(int(cx), int(cy))
check("P5a 點在 (2,2) 的 N 片內心 → 命中那個洞", hit is not None,
      f"{hit['type'] if hit else None}")
check("P5b 命中的洞含 (2,2,'N') 這一片",
      hit is not None and (2, 2, 'N') in [tuple(x) for x in hit['cells']],
      str(hit['cells']) if hit else 'None')
# 点在远离棋盘处 → 不命中
check("P5c 點空白處不命中",
      gui.get_hole_at_pos(2, 2) is None)

# 缩放一致性：命中半径随 zoom（修 bug 的回归锁）
gui.zoom = 1.0
c1 = gui._mi_mark_center(2, 2, 'N')
gui.zoom = 2.0
c2 = gui._mi_mark_center(2, 2, 'N')
check("P5d 錨點隨 zoom 縮放（坐標不是死的）", c1 != c2,
      f"{c1} vs {c2}")
# zoom=2 时，同一片内心的点仍应命中（半径同比例放大）
hit_z2 = gui.get_hole_at_pos(int(c2[0]), int(c2[1]))
check("P5e zoom=2 時該片內心仍命中（半徑與錨點同量綱）", hit_z2 is not None)
gui.zoom = 1.0

# ================================================================ P6 選洞樣本
print("\n--- P6 選洞樣本落盤（片級 + 格級）---")
sample_dir = os.path.join('save', '选洞样本')
sample_path = os.path.join(sample_dir, 'samples_mi.jsonl')
existed = os.path.exists(sample_path)
before_lines = 0
if existed:
    with open(sample_path, encoding='utf-8') as f:
        before_lines = sum(1 for _ in f)
gui.selected_hole = hit
gui._record_hole_selection()
check("P6a 樣本檔存在", os.path.exists(sample_path))
with open(sample_path, encoding='utf-8') as f:
    lines = [ln for ln in f.read().splitlines() if ln.strip()]
check("P6b 新增了一行", len(lines) == before_lines + 1,
      f"{before_lines} → {len(lines)}")
rec = json.loads(lines[-1])
check("P6c 記了 form=mi", rec.get('form') == 'mi')
check("P6d 有 offset/shape/lattice/mod_match",
      all(k in rec for k in ('offset', 'shape', 'lattice', 'mod_match')))
check("P6e 洞同時有片級 cells 與格級 cells_geo",
      rec['holes'] and all('cells' in h and 'cells_geo' in h
                           for h in rec['holes']))
check("P6f 選中洞索引非 -1（選中的洞在列表裡）",
      rec['selected_hole_index'] >= 0, str(rec['selected_hole_index']))
check("P6g 片級坐標是三元組（含 q）",
      all(len(c) == 3 for h in rec['holes'] for c in h['cells']))

# ================================================================ P7 老路徑回歸
print("\n--- P7 方形 / 三角形面板未改坏 ---")
gui.new_puzzle(4, 4, 2)
gui._compute_target_region()
check("P7a 方形 _target_region 仍是矩形三元組",
      isinstance(gui._target_region, tuple) and len(gui._target_region) == 3
      and len(gui._target_region[2]) == 2)
met_s = gui._mp_current_metrics()
check("P7b 方形指標可用（還原態 100%）",
      met_s is not None and abs(met_s['score'] - 1.0) < 1e-9)
gui.screen.fill((0, 0, 0))
b7 = screen_signature(gui)
gui._draw_target_window()
gui._draw_debug_holes()
check("P7c 方形畫框+記號不拋且有輸出", b7 != screen_signature(gui))

gui.new_triangle_puzzle(4, 2)
region_t = gui._compute_target_region()
check("P7d 三角 _target_region 帶 cells（TriPlacement）",
      hasattr(region_t, 'cells'))
gui.screen.fill((0, 0, 0))
b8 = screen_signature(gui)
gui._draw_tri_target_frame()
gui._draw_tri_marks()
check("P7e 三角畫框+記號不拋且有輸出", b8 != screen_signature(gui))
met_t = gui._mp_current_metrics()
check("P7f 三角指標可用（還原態 100%）",
      met_t is not None and abs(met_t['score'] - 1.0) < 1e-9)

# ================================================================ P8 分析指令闸门
print("\n--- P8 局面分析指令在 mi 下仍被闸门拦住 ---")
# `_analysis_holes` / `_analysis_window` 是**方形硬编码**（直接调
# `find_best_window` + `detect_holes`，都在吃 `b.location[0]/[1]`）。
# 它们靠 `GUI._form_blocked` → `_mi_blocked` 在入口拦住。
#
# 实测（2026-10-04）：绕过闸门直接调，mi 下**不抛异常、而是返回无意义结果**
# （窗口是方形公式算的 `{'r0':0,'c0':0,'rh':4,'cw':4,'overlap':16}`，
# 洞/凸起都是 0）。这正是「静默无输出比报错更糟」的典型 —— 所以闸门必须留着，
# 这几条断言就是防止未来拆闸门时忘了改下游。
gui.new_mi_puzzle(4, 4, 2)
check('P8a mi 下局面分析被拦（_form_blocked）',
      gui._form_blocked('局面分析') is True)
gui.new_triangle_puzzle(4, 2)
check('P8b tri 下局面分析被拦', gui._form_blocked('局面分析') is True)
gui.new_puzzle(4, 4, 2)
check('P8c 方形下局面分析放行（闸门只拦异形）',
      gui._form_blocked('局面分析') is False)
# 方形下确实能算出真窗口（证明 P8c 不是「永远返回 True 的假闸门」）
win = gui._analysis_window()
check('P8d 方形下能算出真窗口', bool(win) and 'r0' in win, str(win))
w, holes, protr = gui._analysis_holes()
check('P8e 方形下洞/凸起可算', holes is not None,
      f'{len(holes)} 洞 / {len(protr)} 凸起')

# ================================================================ P9 调用路径
print("\n--- P9 棋盘绘制路径真的会调起面板（2026-10-04 修的真漏）---")
# 教训：`show_metrics_panel` 分支原先只加在方形 `draw_board` 与三角路径里，
# **没加在 `draw_mi_board`** → mi 下面板数字正常但棋盘上永远没有框与记号。
# 而 P4 那些断言是**直接调** `_draw_mi_target_frame()`，绕过了这条路径，
# 所以照样全绿 —— 「被调用的方法对」≠「调用点存在」。
# 这几条断言只认**从 draw_mi_board 进去**的结果。
# **必须固定随机种子**：P9c 要看红/蓝/黄三类记号都在，而「这局有没有缺口」
# 取决于 shuffle 结果。不设种子时它跟着整条测试链的 random 状态漂 ——
# 我这次就撞上「这局只有洞和凸起、恰好没有缺口」，P9c 假红。
# seed 2 是挑过的：该局面三类记号都齐全（2 个小缺口[蓝] + 1 个大缺口[红]
# + 28 片凸起[黄]）。随便挑 seed 会出现「这局恰好没有红/蓝」的假红。
gui.new_mi_puzzle(4, 4, 2)
random.seed(2)
gui.game.shuffle(40, 2)
gui.show_metrics_panel = True
gui.screen.fill((0, 0, 0))
gui._fit_mi_zoom()
gui._center_mi()
gui.draw_mi_board()
reg = getattr(gui, '_target_region', None)
check('P9a draw_mi_board 之后 _target_region 被填上（调用点存在）',
      isinstance(reg, MiPlacement),
      f'{type(reg).__name__}')
# 框的颜色 (80,220,100) 真的落在屏幕上
green = sum(1
            for yy in range(0, gui.screen_height, 2)
            for xx in range(0, gui.screen_width, 2)
            if gui.screen.get_at((xx, yy))[:3] == (80, 220, 100))
check('P9b 目标框真的画在屏幕上了（绿像素 > 0）', green > 0, f'{green} 个采样点')
# 记号颜色（红=大洞 蓝=小洞/缺口 黄=凸起）也要有
marks = {'红': (255, 80, 80), '蓝': (80, 160, 255), '黄': (255, 210, 60)}
counts = {name: sum(1
                     for yy in range(0, gui.screen_height, 2)
                     for xx in range(0, gui.screen_width, 2)
                     if gui.screen.get_at((xx, yy))[:3] == rgb)
          for name, rgb in marks.items()}
check('P9c 洞/缺口/凸起记号都画出来了', all(v > 0 for v in counts.values()),
      str(counts))
# 关掉面板后不该再有这些记号（闸门是 show_metrics_panel 本身）
gui.show_metrics_panel = False
gui.screen.fill((0, 0, 0))
gui.draw_mi_board()
green_off = sum(1
                for yy in range(0, gui.screen_height, 2)
                for xx in range(0, gui.screen_width, 2)
                if gui.screen.get_at((xx, yy))[:3] == (80, 220, 100))
check('P9d 关掉面板后不再画框', green_off == 0, f'{green_off} 个采样点')

# ================================================================ P10 行数与高度
print("\n--- P10 面板高度按行数算（第 7 行不再被截断）---")
# mi 的指标是 7 行（多一行「mod 约束」），而面板高度原先**写死 6 行**
# → 最后一行画到面板外面，截图里表现为「mod 约束」被截断。
gui.new_mi_puzzle(4, 4, 2)
gui.show_metrics_panel = True
rows_m, _ = gui._mp_rows()
h_m = gui._mp_panel_size(len(rows_m))[1]
rows_s = None
gui.new_puzzle(4, 4, 2)
rows_s, _ = gui._mp_rows()
h_s = gui._mp_panel_size(len(rows_s))[1]
check('P10a mi 是 7 行且比方形高一行',
      len(rows_m) == 7 and h_m > h_s, f'mi {len(rows_m)} 行/{h_m}px，'
      f'方形 {len(rows_s)} 行/{h_s}px')
# 最后一行必须落在面板矩形之内（这是「不被截断」的充要条件）
gui.new_mi_puzzle(4, 4, 2)
gui.screen.fill((0, 0, 0))
gui.draw_metrics_panel()
rows_m, _ = gui._mp_rows()
last_y = (gui.mp_pos[1] + gui._MP_TITLE_H + gui._MP_PAD
          + gui._MP_ROW_H * (len(rows_m) - 1))
inside = last_y + gui._MP_ROW_H <= gui.mp_pos[1] + h_m
check('P10b 最后一行在面板矩形内（不被截断）', inside,
      f'末行底 {last_y + gui._MP_ROW_H} vs 面板底 {gui.mp_pos[1] + h_m}')
check('P10c mp_panel_rect 的高度与行数一致',
      gui.mp_panel_rect.height == h_m,
      f'rect={gui.mp_panel_rect.height} 期望={h_m}')
# 事件路径（拖动/点标题栏）用的行数推算也要一致，否则拖动时矩形会跳
check('P10d _mp_row_count 与实际行数一致（事件路径不失配）',
      gui._mp_row_count() == len(rows_m),
      f'{gui._mp_row_count()} vs {len(rows_m)}')

# ================================================================ P11 跨形态不串味
print("\n--- P11 切换形态后 _target_region 不串味（真 bug 回归）---")
# `_target_region` 的类型随形态变（方形三元组 / TriPlacement / MiPlacement），
# 原先三个建局入口都没清它 → mi 局切回方形后，方形分支 `region[0]` 直接
# `TypeError: 'MiPlacement' object is not subscriptable`。真实使用必然触发。
for first, second, tag in (
        ('mi', 'square', 'mi→方形'),
        ('mi', 'triangle', 'mi→三角'),
        ('square', 'mi', '方形→mi'),
        ('triangle', 'mi', '三角→mi'),
):
    if first == 'mi':
        gui.new_mi_puzzle(4, 4, 2)
    elif first == 'triangle':
        gui.new_triangle_puzzle(4, 2)
    else:
        gui.new_puzzle(4, 4, 2)
    reg_before = getattr(gui, '_target_region', 'CLEAN')
    if second == 'mi':
        gui.new_mi_puzzle(4, 4, 2)
    elif second == 'triangle':
        gui.new_triangle_puzzle(4, 2)
    else:
        gui.new_puzzle(4, 4, 2)
    check(f'P11 {tag} 切换后 _target_region 已清空',
          getattr(gui, '_target_region', None) is None,
          f'切换前={type(reg_before).__name__} 切换后='
          f'{type(getattr(gui, "_target_region", None)).__name__}')
    # 且切换后立刻算面板不得抛（这才是原来的崩点）
    try:
        rows_after, _ = gui._mp_rows()
        ok = len(rows_after) > 0
    except Exception as e:      # noqa: BLE001
        rows_after, ok = [], False
        check(f'P11 {tag} 切换后面板可算', False, f'{type(e).__name__}: {e}')
    if ok:
        check(f'P11 {tag} 切换后面板可算', True, f'{len(rows_after)} 行')

# ================================================================ 匯總
print("\n" + "=" * 60)
if _failures:
    print(f"[FAIL] {len(_failures)} 項未通過：")
    for name in _failures:
        print(f"   - {name}")
    sys.exit(1)
print("[OK] mi 調試面板 F2 全部通過")
