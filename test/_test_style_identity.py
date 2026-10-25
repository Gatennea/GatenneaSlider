# -*- coding: utf-8 -*-
"""回归：格子画布（还原态设计）样式局的身份显示

用户验收要求（2026-10-20）：
1. 样式局（含「重置」之后）不得被当成官方预设谜题——谜题菜单里不能给
   「矩形 3×3 等级1」这类档位打 ✓，底部状态行也不能说「当前：矩形 3×3 等级1」；
2. 底部栏中间位置显示样式标题，不再另起一截「目标：样式「…」」。

断言方式：把 status_font 换成记录型包装，直接看 draw_status_bar 实际渲染了
哪些字符串（比采样像素稳，且能区分「谜题：」与「样式：」两种前缀）。
"""
import os
import queue
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from gui import design_styles  # noqa: E402

SNAME = '状态栏测试样式'
_failures = []


def check(name, cond, detail=''):
    if cond:
        print(f'[PASS] {name} {detail}')
    else:
        print(f'[FAIL] {name} {detail}')
        _failures.append(name)


class RecordingFont:
    """包住真实字体：记录 render 的文本，绘制行为完全不变。"""

    def __init__(self, font):
        self._font = font
        self.texts = []

    def render(self, text, *args, **kwargs):
        self.texts.append(text)
        return self._font.render(text, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._font, name)


def status_texts(gui):
    """渲染一次状态栏，返回它画过的全部字符串。"""
    real = gui.status_font
    rec = RecordingFont(real)
    gui.status_font = rec
    try:
        gui.draw_status_bar()
    finally:
        gui.status_font = real
    return rec.texts


design_styles.delete_style(SliderGUI().config_dir, SNAME)

gui = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                ext_state={'enabled': True, 'token': 'T', 'port': 5050})
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.new_puzzle(4, 4, 1)

# 样式：3×3 满块（尺寸等级正好撞上官方「矩形 3×3 等级1」档位）
design_styles.save_style(gui.config_dir, SNAME, {
    'version': 1, 'name': SNAME, 'm': 3, 'n': 3, 'step': 1,
    'cells': [[r, c] for r in range(3) for c in range(3)],
    'groups': {},
})

# ---------------------------------------------------------------- S1 普通局
print('--- S1 官方档位局：底部显示「谜题：」且菜单给该档位打 ✓ ---')
texts = status_texts(gui)
check('S1a 非样式局中间显示「谜题：」',
      any(t.startswith('谜题：') for t in texts), f'{texts}')
check('S1b 非样式局无「样式：」', not any(t.startswith('样式：') for t in texts))
check('S1c 非样式局无「目标：」残留', not any('目标：' in t for t in texts))
check('S1d 普通局 4×4 等级1 是当前档位',
      gui._preset_is_current(('矩形 4×4 等级1', 4, 4, 1)))

# ---------------------------------------------------------------- S2 样式局
print('\n--- S2 样式局：中间显示样式标题，官方档位不再算当前 ---')
gui._ann_design_start_style(SNAME)
check('S2a 样式局落在 3×3 等级1 的同名尺寸上',
      (gui.current_m, gui.current_n, gui.current_step) == (3, 3, 1),
      f'{gui.current_m}×{gui.current_n} 等级{gui.current_step}')

texts = status_texts(gui)
check('S2b 中间显示「样式：<名>」',
      f'样式：{SNAME}' in texts, f'{texts}')
check('S2c 不再显示「谜题：<key>」',
      not any(t.startswith('谜题：') for t in texts))
check('S2d 不再显示「目标：样式…」',
      not any('目标：' in t for t in texts))

check('S2e 官方档位「矩形 3×3 等级1」不再打 ✓（尺寸虽撞上）',
      not gui._preset_is_current(('矩形 3×3 等级1', 3, 3, 1)))
check('S2f 自定义预设条目才打 ✓',
      gui._preset_is_current((SNAME, '__custom__', SNAME)))
check('S2g 别的自定义预设不打 ✓',
      not gui._preset_is_current(('别的样式', '__custom__', '别的样式')))
check('S2h 菜单底部状态行说样式',
      gui._current_puzzle_label() == f'样式「{SNAME}」',
      f'{gui._current_puzzle_label()!r}')

# ---------------------------------------------------------------- S3 重置后
print('\n--- S3 「重置」之后仍是样式局（不得退回预设谜题） ---')
gui.shuffle_puzzle()
if getattr(gui, '_shuffle_demo_final', None) is not None:
    gui._finish_shuffle_demo()
check('S3a 打乱后非还原态', not gui.game.is_solved())
gui.reset_puzzle()
check('S3b 重置后仍是样式局（goal 与名字都在）',
      gui._ann_style_goal == SNAME
      and gui.game.goal_pattern is not None
      and gui.game.is_solved(),
      f'goal={gui._ann_style_goal!r}')
texts = status_texts(gui)
check('S3c 重置后底部仍显示样式标题',
      f'样式：{SNAME}' in texts
      and not any(t.startswith('谜题：') for t in texts), f'{texts}')
check('S3d 重置后官方档位仍不打 ✓',
      not gui._preset_is_current(('矩形 3×3 等级1', 3, 3, 1)))

# ---------------------------------------------------------------- S4 切回普通局
print('\n--- S4 切回官方档位：身份恢复 ---')
gui.new_puzzle(4, 4, 1)
texts = status_texts(gui)
check('S4a 新谜题清掉样式身份',
      gui._ann_style_goal is None
      and any(t.startswith('谜题：') for t in texts), f'{texts}')
check('S4b 官方档位重新打 ✓',
      gui._preset_is_current(('矩形 4×4 等级1', 4, 4, 1)))

design_styles.delete_style(gui.config_dir, SNAME)
print('\n===', 'ALL PASS' if not _failures else f'{len(_failures)} FAILURES', '===')
sys.exit(1 if _failures else 0)
