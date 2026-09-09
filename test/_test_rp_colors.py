# -*- coding: utf-8 -*-
"""验证：列表最好绿/最差红/其他默认；摘要第二行=单次最好/平均最好/总平均"""
import os, sys
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame
from GUI import SliderGUI
from records import format_time

GREEN = (120, 220, 120); RED = (255, 90, 90); DEF = (210, 210, 210); GRAY = (110, 110, 120)

gui = SliderGUI(m=6, n=6, step=1)
gui.show_records_panel = True
gui.draw_menu_bar()
key = gui._rp_current_key()

# 数据：6 条有效 + 1 DNF，最好 1000，最差 9000，DNF
times = [3000, 1000, 5000, 9000, 4000, 2000, 0]  # 最后一条 DNF
ids = []
for t in times[:-1]:
    ids.append(gui.records.add_record(key, 5, 5, 2, "111", t, 10, False))
ids.append(gui.records.add_record(key, 5, 5, 2, "111", 0, 0, True))  # DNF

def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    globals()['_ok'] = globals().get('_ok', True) and cond

series = gui.records.series(key)
st = gui.records.stats(key)

# 1. stats 含 mean（与记录直接计算值比对，兼容历史遗留数据）
recs = gui.records.get_records(key)
valid_all = [r['time_ms'] for r in recs if not r['dnf']]
expect_mean = sum(valid_all) / len(valid_all)
check("stats 含总平均 mean", 'mean' in st and abs(st['mean'] - expect_mean) < 1e-6)

# 2. _rp_value_style 各分支
a5s = [a for _, a, _ in series]
best_a5 = min(a for a in a5s if isinstance(a, (int, float)))
worst_a5 = max(a for a in a5s if isinstance(a, (int, float)))
txt, col = gui._rp_value_style(1000, 1000, 9000)
check("单次最好标绿", col == GREEN)
txt, col = gui._rp_value_style(9000, 1000, 9000)
check("单次最差标红", col == RED)
txt, col = gui._rp_value_style(4000, 1000, 9000)
check("其他默认色", col == DEF)
txt, col = gui._rp_value_style('DNF', best_a5, worst_a5)
check("DNF 标红", col == RED)
txt, col = gui._rp_value_style(None, best_a5, worst_a5)
check("None 灰色-", col == GRAY)
txt, col = gui._rp_value_style(best_a5, best_a5, worst_a5)
check("Ao5 最好标绿", col == GREEN)
txt, col = gui._rp_value_style(worst_a5, best_a5, worst_a5)
check("Ao5 最差标红", col == RED)

# 3. 完整绘制面板（含摘要分段换行、行着色）不崩溃
gui.rp_pos = [100, 60]
gui.draw_records_panel()
check("面板绘制无异常", True)

# 4. 摘要分段文本渲染验证（宽度不超面板则单行）
seg1 = f"单次最好 {format_time(st['best'])}"
seg2 = f"平均最好 {format_time(best_a5)}"
seg3 = f"总平均 {format_time(st['mean'])}"
w1 = gui.status_font.render(seg1, True, GREEN).get_width()
w2 = gui.status_font.render(seg2, True, GREEN).get_width()
w3 = gui.status_font.render(seg3, True, DEF).get_width()
print(f"  段宽: {w1}/{w2}/{w3}, 面板可用 {320-20}")
check("摘要段渲染宽度合理", w1 > 0 and w2 > 0 and w3 > 0)

# 5. 空分组边界：新 key 无成绩
st0 = gui.records.stats('9~9*9')
check("空分组 mean=None", st0['mean'] is None)

print("ALL PASS" if globals().get('_ok', True) else "SOME FAILED")
sys.exit(0 if globals().get('_ok', True) else 1)
