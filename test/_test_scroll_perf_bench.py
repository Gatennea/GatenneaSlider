# -*- coding: utf-8 -*-
"""滚动卡顿量化 bench（2026-11-17，用户报「滚动条比较卡顿（之前也是）」）。

量什么（无头、同机相对比较）：
  H1/H2 帮助框全文态：稳态单帧 draw_help_dialog 平均耗时 + 每帧
       _wrap_text 调用次数；
  S1  设置框长内容页（快捷键）稳态单帧 draw_settings_dialog 耗时。

基线（2026-11-17 修复前，同机实测）：H1 帮助滚动帧 avg=659.8ms max=1449ms、
每帧 _wrap_text ≈104 次、全文 wrap 一遍 269ms；修复后 H1 avg=8.1ms
（81 倍）、稳态 wrap=0。S1 设置页修复前后均 ~16-20ms（本就不卡）。

断言：
  R1 帮助稳态帧 _wrap_text 调用次数 = 0（全文已缓存，只剩 blit）；
  R2 帮助稳态单帧平均 < 25ms（基线 659.8 → 修复后 8.1，阈值留足余量）；
  R3 设置稳态单帧平均 < 25ms（本底 16-20ms）。

执行：D:/python/python.exe test/_test_scroll_perf_bench.py
"""
import os
import queue
import sys
import time

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


def boot():
    gui = SliderGUI(m=4, n=4, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.new_puzzle(4, 4, 2)
    return gui


def timed_frames(fn, n=30, scroll_fn=None):
    """滚动 n 帧：返回 (avg_ms, max_ms)。scroll_fn 每帧换滚动位置。"""
    dts = []
    for i in range(n):
        if scroll_fn is not None:
            scroll_fn(i)
        t0 = time.perf_counter()
        fn()
        dts.append((time.perf_counter() - t0) * 1000)
    return sum(dts) / len(dts), max(dts)


def main():
    gui = boot()

    # ---- H1/H2 帮助全文态 ----
    gui.show_help = True
    gui.help_query = ''
    # 计数 _wrap_text 每帧调用
    wrap_calls = [0]
    real_wrap = gui._wrap_text

    def counting_wrap(*a, **kw):
        wrap_calls[0] += 1
        return real_wrap(*a, **kw)

    gui._wrap_text = counting_wrap

    sb = gui.help_scrollbar
    gui.draw_help_dialog()            # 首帧（含布局）
    wrap_calls[0] = 0
    avg1, max1 = timed_frames(
        gui.draw_help_dialog, 30,
        scroll_fn=lambda i: sb.set_scroll(i * 30))
    per_frame_wrap = wrap_calls[0] / 30
    print('H1 帮助滚动帧耗时 avg=%.1fms max=%.1fms' % (avg1, max1))
    print('H2 每帧 _wrap_text 调用 ≈ %.0f 次' % per_frame_wrap)
    gui._wrap_text = real_wrap

    # 单独量：全文 wrap 一遍的开销（总高度循环的构成）
    t0 = time.perf_counter()
    lines = gui._load_help_lines()
    t_load = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    tw = 0
    for line, _h in lines:
        if line:
            tw += len(gui._wrap_text(line, gui.dialog_font, 495))
    t_wrap = (time.perf_counter() - t0) * 1000
    print('H3 _load_help_lines=%.2fms 全文wrap一遍=%.2fms (行=%d 折行=%d)'
          % (t_load, t_wrap, len(lines), tw))

    # ---- S1 设置框长内容页 ----
    gui.show_help = False
    gui.show_settings_dialog = True
    gui.settings_active_tab = 'keybindings'
    avg2, max2 = timed_frames(
        gui.draw_settings_dialog, 30,
        scroll_fn=lambda i: gui.settings_scrollbar.set_scroll(i * 40))
    print('S1 设置滚动帧耗时 avg=%.1fms max=%.1fms' % (avg2, max2))

    # ---- 断言（无条件；性能数字打印便于回归时定位）----
    check('R1 帮助稳态帧 wrap 调用=0', per_frame_wrap == 0,
          str(per_frame_wrap))
    check('R2 帮助滚动帧 avg<25ms', avg1 < 25, '%.1fms' % avg1)
    check('R3 设置滚动帧 avg<25ms', avg2 < 25, '%.1fms' % avg2)
    print('==== %s（%d 项失败）'
          % ('全部通过' if not _failures else '有失败', len(_failures)))
    return 1 if _failures else 0


if __name__ == '__main__':
    sys.exit(main())
