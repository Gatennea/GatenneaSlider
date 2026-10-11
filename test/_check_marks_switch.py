# -*- coding: utf-8 -*-
"""棋盘「标记」开关脱离调试面板的验证（临时脚本，不入库）。

背景：右下角新增「标记」后实测无效果——记号绘制的外层闸门仍是
`show_metrics_panel`，面板默认关闭 → 单开标记什么都不画。本脚本锁死
「记号与面板是两个独立开关」的解耦行为。

执行：``D:/python/python.exe -u test/_check_marks_switch.py``
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

# 清掉副本 config 里可能残留的 board_marks_enabled（本目录跑 HTTP 测试时
# 存过 true），否则它会在启动时恢复、盖掉源码默认值，干扰默认值断言。
import json  # noqa: E402

_cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'config', 'config.json')
if os.path.exists(_cfg):
    try:
        with open(_cfg, encoding='utf-8') as _f:
            _d = json.load(_f)
        if isinstance(_d, dict) and 'board_marks_enabled' in _d:
            _d.pop('board_marks_enabled')
            with open(_cfg, 'w', encoding='utf-8') as _f:
                json.dump(_d, _f, ensure_ascii=False)
    except Exception as _e:  # 配置清理失败无所谓，只是断言会不准
        print(f"  (跳过 config 清理: {_e})")

from GUI import SliderGUI  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.new_puzzle(4, 4, 2)

print("\n--- 默认状态 ---")
check("默认不画记号（与解耦前观感一致）",
      gui.board_marks_enabled is False, f"={gui.board_marks_enabled}")
check("默认调试面板关闭",
      gui.show_metrics_panel is False, f"={gui.show_metrics_panel}")

calls = []
gui._draw_target_window = lambda *a, **k: calls.append('win') or None
gui._draw_debug_holes = lambda *a, **k: calls.append('holes') or None

print("\n--- 四种开关组合 ---")
gui.show_metrics_panel = False
gui.board_marks_enabled = True
calls.clear()
gui.draw_board()
check("只开标记（面板关）→ 记号照画",
      calls == ['win', 'holes'], f"calls={calls}")

gui.show_metrics_panel = True
gui.board_marks_enabled = False
calls.clear()
gui.draw_board()
check("只开面板（标记关）→ 不画记号",
      calls == [], f"calls={calls}")

gui.show_metrics_panel = True
gui.board_marks_enabled = True
calls.clear()
gui.draw_board()
check("两者都开 → 记号照画",
      calls == ['win', 'holes'], f"calls={calls}")

gui.show_metrics_panel = False
gui.board_marks_enabled = False
calls.clear()
gui.draw_board()
check("两者都关 → 不画记号", calls == [], f"calls={calls}")

print("\n--- 点选空位也应跟随标记开关 ---")
gui.board_marks_enabled = True
gui.show_metrics_panel = False
gui._pending_hole_pick = None
try:
    gui.get_hole_at_pos(10, 10)
    _sel_ok = True
except Exception as e:
    _sel_ok = False
    print(f"  get_hole_at_pos 抛异常: {e}")
check("只开标记时仍可点选空位（函数可调用且不因面板关闭而短路）",
      _sel_ok)

print("\n=== 结果 ===")
print("PASS" if not _failures else f"FAIL: {_failures}")
sys.exit(1 if _failures else 0)
