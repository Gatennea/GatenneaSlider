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
# 同理还有面板可见性——它持久化在 `panels.metrics.visible`（不是顶层键），
# 本机 config 里存着 true，会把「默认调试面板关闭」断言打红。
import json  # noqa: E402

_cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'config', 'config.json')
_orig_panels = None
if os.path.exists(_cfg):
    try:
        with open(_cfg, encoding='utf-8') as _f:
            _d = json.load(_f)
        if isinstance(_d, dict):
            if isinstance(_d.get('panels'), dict):
                _orig_panels = _d['panels']
                _m = dict(_d['panels'].get('metrics') or {})
                _m['visible'] = False
                _d['panels']['metrics'] = _m
            if 'board_marks_enabled' in _d:
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

# 默认值断言用完，把原面板布局写回去——别把用户的保存状态改掉。
if _orig_panels is not None:
    try:
        with open(_cfg, encoding='utf-8') as _f:
            _d = json.load(_f)
        _d['panels'] = _orig_panels
        with open(_cfg, 'w', encoding='utf-8') as _f:
            json.dump(_d, _f, ensure_ascii=False)
    except Exception as _e:
        print(f"  (跳过 config 还原: {_e})")

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

print("\n--- 选洞能力已删除（2026-10-12 用户决定，由标注选空位取代）---")
# 调试面板的「点洞选中 + 记录样本」整体删除：选中态、待选态、样本记录
# 入口都不在了。几何查询 get_hole_at_pos 保留给「选块填空」点空位那一步
# （纯函数、无选中语义、方形专用），绝不能因为删选中把它一起删没。
check("selected_hole 选中态已删除", not hasattr(gui, 'selected_hole'))
check("_pending_hole_pick 待选态已删除",
      not hasattr(gui, '_pending_hole_pick'))
check("选洞样本记录入口已删除",
      not hasattr(gui, '_record_hole_selection')
      and not hasattr(gui, '_record_mi_hole_selection'))
try:
    hit = gui.get_hole_at_pos(10, 10)
    _sel_ok = True
except Exception as e:
    _sel_ok = False
    print(f"  get_hole_at_pos 抛异常: {e}")
check("几何查询 get_hole_at_pos 仍可用且不抛（选块填空点空位用）",
      _sel_ok and hit is None)

print("\n=== 结果 ===")
print("PASS" if not _failures else f"FAIL: {_failures}")
sys.exit(1 if _failures else 0)
