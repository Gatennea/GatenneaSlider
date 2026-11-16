# -*- coding: utf-8 -*-
"""状态栏段间不重合护栏（2026-11-17，§四十四.6）。

用户报：「求解器运行时宏指令的蓝色字提示有时会和底栏其他字重合」。
根因：宏状态段（执行宏蓝 / 录制红）从缩放段向左**无界**延伸，谜题段
**硬居中不避让**——宏名一长就跨过中线与谜题段叠字。

修法（gui/renderer.draw_status_bar 段间避让）：左组右界当墙；宏段先定位
（超宽省略号截断）；谜题段在 [左组右界, 宏段左界] 夹缝内居中（放不下也
截断）；宏段最后画。绘制时回填 _status_puzzle_rect / _status_macro_rect /
_status_zoom_rect / _status_left_right 供本护栏直接量（与
_settings_content_rect 同一先例）。

判据：
  A. 求解执行中 + 超长宏名（修复前必叠字）：宏段存在、谜题段存在，
     宏/谜题/缩放三段两两不相交，且都落在左组右界之右；
  B. 无宏段：谜题段存在且未被截断、在夹缝内；
  C. 录制红段：存在且同样不叠。

执行：D:/python/python.exe test/_test_statusbar_no_overlap.py
"""
import os
import queue
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from GUI import SliderGUI                                 # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, extra))
    if not cond:
        _failures.append(name)


def no_pair_overlap(tag, rects):
    """给定 {名: rect}，两两不相交。"""
    names = [k for k, v in rects.items() if v is not None]
    bad = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a = rects[names[i]]
            b = rects[names[j]]
            if a.colliderect(b):
                # colliderect 认定有交集；报出重叠宽度帮助定位
                ov = min(a.right, b.right) - max(a.left, b.left)
                bad.append((names[i], names[j], ov))
    check('%s 各段两两不相交（%d 段）' % (tag, len(names)), not bad, str(bad))


def main():
    gui = SliderGUI(m=4, n=4, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.new_puzzle(4, 4, 2)

    # ---- A. 求解执行中 + 超长宏名（修复前：蓝字段跨过中线压谜题段） ----
    gui.macro_executing = True
    gui.macro_exec_name = '超长宏名' * 20          # 160 字宽远超中线
    gui.macro_exec_index = 3
    gui.macro_exec_ops = [None] * 17
    gui.draw_status_bar()
    check('A1 蓝色宏字段画出（超宽已截断仍存在）',
          gui._status_macro_rect is not None
          and gui._status_macro_rect.width > 0,
          str(gui._status_macro_rect))
    check('A2 谜题段画出', gui._status_puzzle_rect is not None,
          str(getattr(gui, '_status_puzzle_text', '')))
    no_pair_overlap('A 执行宏', {
        'macro': gui._status_macro_rect,
        'puzzle': gui._status_puzzle_rect,
        'zoom': gui._status_zoom_rect,
    })
    check('A3 三段都在左组右界之右',
          gui._status_puzzle_rect.left >= gui._status_left_right
          and gui._status_macro_rect.left >= gui._status_left_right,
          f'left_right={gui._status_left_right} '
          f'pz={gui._status_puzzle_rect.left} mc={gui._status_macro_rect.left}')

    # ---- B. 无宏段：谜题段回到夹缝中央正常显示 ----
    gui.macro_executing = False
    gui.draw_status_bar()
    check('B1 无宏时宏段回填 None', gui._status_macro_rect is None)
    check('B2 谜题段未被截断',
          gui._status_puzzle_rect is not None
          and not gui._status_puzzle_text.endswith('…'),
          gui._status_puzzle_text)
    no_pair_overlap('B 无宏', {
        'puzzle': gui._status_puzzle_rect,
        'zoom': gui._status_zoom_rect,
    })

    # ---- C. 录制红段同样不叠 ----
    gui.macro_recording = True
    gui.macro_recording_steps = list(range(120))   # 步数多 → 文本长
    gui.draw_status_bar()
    check('C1 录制红段画出', gui._status_macro_rect is not None,
          str(gui._status_macro_rect))
    no_pair_overlap('C 录制中', {
        'macro': gui._status_macro_rect,
        'puzzle': gui._status_puzzle_rect,
        'zoom': gui._status_zoom_rect,
    })
    gui.macro_recording = False

    print('==== %s（%d 项失败）'
          % ('全部通过' if not _failures else '有失败', len(_failures)))
    return 1 if _failures else 0


if __name__ == '__main__':
    sys.exit(main())
