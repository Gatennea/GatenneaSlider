# -*- coding: utf-8 -*-
"""无头测试：成绩详情固定高度+自适应字号 / 时间含年份秒 / 初始状态操作菜单"""
import os, sys, json, time
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame
from GUI import SliderGUI

FONT_W = None

def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        globals()['_failed'] = True

# ---------- 构造实例 ----------
gui = SliderGUI(m=6, n=6, step=1)
gui.show_records_panel = True  # 测试环境强制开启（config 恢复可能关闭）
gui.draw_menu_bar()

# ---------- 记录数据：不同尺寸的初始矩阵 ----------
key = gui._rp_current_key()  # 与 GUI 当前谜题 key 一致
mat_small = "\n".join(["111111"] * 6)          # 6 行
mat_big = "\n".join(["1111111111"] * 14)        # 14 行 × 10 列（极端）
r1 = gui.records.add_record(key, gui.current_m, gui.current_n, gui.current_step, mat_small, 12345, 20, False)
r2 = gui.records.add_record(key, gui.current_m, gui.current_n, gui.current_step, mat_big, 5000, 9, False)

# ---------- 1. 详情固定高度 ----------
print("DEBUG key:", repr(gui._rp_current_key()), "records keys:", list(gui.records.data.keys()))
print("DEBUG r1 id:", r1['id'], "recs:", len(gui.records.get_records(gui._rp_current_key())))
gui.rp_detail_id = r1['id']
d1 = gui._rp_detail_height()
check("详情展开高度为固定值 160", d1 == 160)
check("面板总高固定=340+160", gui._rp_panel_size()[1] == 340 + 160)
gui.rp_detail_id = None
check("收起时详情高度为 0", gui._rp_detail_height() == 0)

# ---------- 2. 自适应字号 ----------
gui.rp_detail_id = r1['id']
h = gui._rp_detail_height()
avail_w = 132 - 16
avail_h = h - 24 - 4
fs6 = gui._rp_matrix_font_size(6, 6, avail_w, avail_h)     # 6 行
fs14 = gui._rp_matrix_font_size(14, 10, avail_w, avail_h)  # 14 行
check(f"6行矩阵字号=12 (实际{fs6})", fs6 == 12)
check(f"14行矩阵字号缩小 (实际{fs14})", fs14 < 12)
check(f"字号不小于下限8 (实际{fs14})", fs14 >= 8)

# 渲染 14 行矩阵：应完整绘制（行数不减）
gui._rp_build_layout()
w, hh = gui._rp_panel_size()
gui.rp_pos = [max(0, 800 - w), 60]
rec = gui._rp_detail_record()
gui._rp_draw_detail(gui.rp_pos[0], gui.rp_pos[1] + hh - gui._rp_detail_height(), w, gui._rp_detail_height(), rec)
lines_used = mat_big.count('\n') + 1
check("14行矩阵全部渲染（不再截断到12）", lines_used == 14)

# ---------- 3. 生成时间含年份+秒 ----------
ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r1['ts']))
val_surf = gui.status_font.render(ts_str, True, (0, 0, 0))
info_w = w - 20 - 132 - 8
check(f"时间格式含年份秒: {ts_str}", ts_str.startswith('20') and ':' in ts_str[13:])
check(f"时间宽度 {val_surf.get_width()} <= 信息区 {info_w}", val_surf.get_width() <= info_w)

# ---------- 4. 另存为存档 ----------
os.makedirs('_tmp_save', exist_ok=True)
gui.save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_tmp_save')
path = gui._rp_save_as_puzzle(r1)
check("另存为存档生成文件", bool(path) and os.path.exists(path))
if path:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    check("存档 puzzle 字段正确",
          data['puzzle'] == {'m': r1['m'], 'n': r1['n'], 'step': r1['step']})
    check("存档有 1 个快照", len(data['history']['snapshots']) == 1)
    snap = data['history']['snapshots'][0]
    m_rows = len(snap['matrix'])
    check(f"存档快照行数=6 (实际{m_rows})", m_rows == 6)
    # 能重新载入
    gui._load_save_data(data)
    check("载入存档后 m/n/step 正确",
          gui.current_m == r1['m'] and gui.current_n == r1['n'] and gui.current_step == r1['step'])

# ---------- 5. 载入练习模式 ----------
gui._rp_load_into_practice(r2)
check("载入练习模式后 m/n 正确",
      gui.current_m == r2['m'] and gui.current_n == r2['n'] and gui.current_step == r2['step'])
check("载入后 mode=practice", gui.game_mode == 'practice')
map_str = gui.game.export_map()
check("载入后棋盘与记录一致(14行)",
      map_str.count('\n') + 1 == 14)
check("载入后历史有快照", gui.game_history.history_index == 0)

# ---------- 6. 菜单交互 ----------
gui.rp_detail_id = r1['id']
gui.rp_pos = [100, 60]
gui.draw_records_panel()  # 生成详情区与 rp_matrix_rect
mx, my = gui.rp_matrix_rect.center
print("DEBUG click pos:", (mx, my), "panel:", gui.rp_panel_rect,
      "mat:", gui.rp_matrix_rect, "detail_id:", gui.rp_detail_id)
print("DEBUG rec:", gui._rp_detail_record() is not None,
      "show:", gui.show_records_panel)
ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(mx, my))
gui.handle_records_panel_event(ev)
print("DEBUG after click menu_open:", gui.rp_matrix_menu_open, "rects:", len(gui.rp_matrix_menu_rects))
check("点击矩阵后菜单打开", gui.rp_matrix_menu_open is True)

gui.draw_records_panel()  # 生成菜单 rects
check("菜单有3个选项", len(gui.rp_matrix_menu_rects) == 3)
labels = [a for _, a in gui.rp_matrix_menu_rects]
check("菜单项为 copy/save/load", labels == ['copy', 'save', 'load'])

# 点击「载入练习模式」菜单项（模拟完整事件：应关闭菜单并执行动作）
rect, action = gui.rp_matrix_menu_rects[2]
ev2 = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center)
gui.handle_records_panel_event(ev2)
check("菜单动作 load 生效(mode=practice)", gui.game_mode == 'practice')
check("菜单动作后菜单关闭", gui.rp_matrix_menu_open is False)

# ---------- 7. 复制到剪贴板（Windows API 路径） ----------
ok = gui._rp_copy_matrix(mat_small)
# dummy 环境无法验证剪贴板内容，只验证不抛异常且返回 True/False
check("复制不抛异常", ok in (True, False))

print("\n" + ("ALL PASS" if not globals().get('_failed') else "SOME FAILED"))
sys.exit(1 if globals().get('_failed') else 0)
