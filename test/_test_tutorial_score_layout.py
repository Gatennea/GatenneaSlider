# -*- coding: utf-8 -*-
"""教程关卡列表「标题 vs 最高分」同行不重叠 —— 几何不变量测试。

背景：关卡列表面板里每个小关一行，左侧标题、右侧最高分。两者同字号
（dialog_font 18px）时，长标题（如「2.3 内部洞 + 底部大缺口」）会与
得分字重叠。修法：得分改用 status_font（14px）+ 标题按剩余空间截断。

本测试对全部真实小关标题、在「已过关/未过关」两种状态下断言：
  标题右缘 <= 得分左缘（不重叠）
并验证：得分字体确实小于标题字体；截断逻辑对最长标题生效；
面板整体绘制不抛异常。
"""
import os, sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame
pygame.init()
from GUI import SliderGUI
from gui.tutorial import (TUTORIAL_LEVELS, _sublevel_title,
                          _tut_best_text, _tut_score_text)

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


gui = SliderGUI(m=6, n=6, step=2)
gui.tut_show_prompt = False
gui.tutorial_active = True
gui.tut_selecting_levels = True

# 面板几何（与 _draw_level_select_panel 一致）
w, pad = 310, 12
r_width = w - pad * 2                      # 286

# 给每个小关都填一个最高分，全部标记已过关（最坏情况：✓ 前缀 + 得分）
for lv in TUTORIAL_LEVELS:
    for sid in lv['sublevels']:
        gui.tut_progress.setdefault('best_scores', {})[sid] = 95
        gui.tut_progress.setdefault('subcompleted', {}).setdefault(
            lv['id'], [])
        if sid not in gui.tut_progress['subcompleted'][lv['id']]:
            gui.tut_progress['subcompleted'][lv['id']].append(sid)

# 1) 绘制不抛异常
try:
    gui.draw_tutorial_panel()
    check('面板绘制无异常', True)
except Exception as e:
    check('面板绘制无异常', False, repr(e))

# 2) 得分字体小于标题字体
check('得分字体小于标题字体',
      gui.status_font.get_height() < gui.dialog_font.get_height(),
      f"status={gui.status_font.get_height()} < dialog={gui.dialog_font.get_height()}")

# 3) 逐行几何不变量：标题右缘 <= 得分左缘
mark = '✓'
worst = None
for lv in TUTORIAL_LEVELS:
    for sid in lv['sublevels']:
        label = f"{mark} {_sublevel_title(sid)}"
        score_surf = gui.status_font.render(_tut_best_text(95), True, (235, 195, 95))
        reserve = score_surf.get_width() + 10
        clipped = gui._tut_clip_text(label, gui.dialog_font,
                                     max(40, r_width - 20 - reserve))
        title_w = gui.dialog_font.size(clipped)[0]
        title_right = 10 + title_w                      # 相对行左缘
        score_left = r_width - 10 - score_surf.get_width()
        gap = score_left - title_right
        if worst is None or gap < worst[0]:
            worst = (gap, sid, clipped)
        if gap < 0:
            check(f'行不重叠 {sid}', False,
                  f'title_right={title_right} > score_left={score_left} label={clipped!r}')
check('全部小关行不重叠（含✓+得分最坏情况）', worst is not None and worst[0] >= 0,
      f'最小间隙 {worst[0]}px @ {worst[1]} ({worst[2]!r})')

# 4) 未过关（无得分、有锁图标）也不重叠：锁图标占位 28
for lv in TUTORIAL_LEVELS:
    for sid in lv['sublevels']:
        label = _sublevel_title(sid)
        clipped = gui._tut_clip_text(label, gui.dialog_font,
                                     max(40, r_width - 20 - 28))
        title_w = gui.dialog_font.size(clipped)[0]
        if 10 + title_w > r_width - 18:                 # 锁图标左缘
            check(f'未过关行不压锁图标 {sid}', False, clipped)
            break
else:
    check('未过关行不压锁图标', True)

# 5) 截断确实对最长标题生效（防回归：不能因改动退化成不裁切）
longest = max(TUTORIAL_LEVELS, key=lambda l: max(
    (gui.dialog_font.size(f"✓ {_sublevel_title(s)}")[0]
     for s in l['sublevels']), default=0))
sid_long = max(longest['sublevels'],
               key=lambda s: gui.dialog_font.size(f"✓ {_sublevel_title(s)}")[0])
raw = f"✓ {_sublevel_title(sid_long)}"
clipped = gui._tut_clip_text(raw, gui.dialog_font,
                             max(40, r_width - 20 - (gui.status_font.size(
                                 _tut_best_text(95))[0] + 10)))
check('最长标题被截断（防重叠闸门生效）', clipped != raw and clipped.endswith('…'),
      f'{raw!r} -> {clipped!r}')

# 6) _tut_clip_text 单元行为：短文本原样、超宽截断、max_w<=0 原样
check('clip: 短文本原样', gui._tut_clip_text('短', gui.dialog_font, 500) == '短')
check('clip: max_w<=0 原样返回', gui._tut_clip_text('无论如何', gui.dialog_font, 0) == '无论如何')

print()
if _failures:
    print(f"共 {len(_failures)} 项失败: {_failures}")
    sys.exit(1)
print("全部通过")
