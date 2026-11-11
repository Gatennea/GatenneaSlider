# -*- coding: utf-8 -*-
"""无限打乱 × 自动求解互斥：行为护栏（正向 + 真刀反向验证）。

用户 2026-11-12 报：无限打乱每格都在滑动，求解期间又禁止滑动，两者同时开
会得到「一边继续打乱、一边显示正在求解」的假状态。修法是两方向都堵，
判据收在 SessionMixin._mode_conflict_msg 一处。

本护栏**不查源码字串**，只盯被绕开的功能有没有真的启动：
  · 求解有没有起来 → 数 threading.Thread.start 的调用（真后台线程入口）；
  · 游走有没有起来 → 数 _infinite_shuffle_step 的调用（真续播入口）。
两组计数都是 spy，不跑真线程、不跑真动画。

A 组（正向）：所有入口在冲突局面下都拒绝，且提示明确；停止/取消路径、
「开关开着但游走没开始」的普通求解不受影响。
B 组（反向验证）：把共用判据在实例上中和成空（等价于「撤掉判据」），
同一批入口必须能把冲突局面**再制造出来**（spy 计数 > 0）。若 A 组之所以绿
是因为某个入口压根没走到启动、或被别的 guard 挡住，B 组就复现不出来 → 转红。
中和只改当前进程里的实例属性，不碰任何源文件，因此不需要还原保护，
也不会和并行跑的其它测试抢文件。

用法：D:/python/python.exe test/_test_infinite_solver_mutex.py
"""
import os
import queue
import sys
import threading
import time

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from gui.session import (  # noqa: E402
    SOLVER_BLOCKED_BY_SHUFFLE_MSG,
    SHUFFLE_BLOCKED_BY_SOLVER_MSG,
)

_FAILS = []
_OK = [0]


def check(name, cond, detail=''):
    if cond:
        _OK[0] += 1
        print('  ok  : ' + name)
    else:
        _FAILS.append(name)
        print('  FAIL: ' + name + ('  ' + detail if detail else ''))
    return bool(cond)


class Spies:
    """数「求解线程是否启动」与「无限打乱续播是否启动」。"""

    def __init__(self, gui):
        self.gui = gui
        self.thread_starts = 0
        self.shuffle_steps = 0
        self._orig_start = None
        self._orig_step = None

    def __enter__(self):
        self._orig_start = threading.Thread.start

        def counting_start(_thread, *a, **kw):
            self.thread_starts += 1
            return None  # 真后台线程一律不启动

        threading.Thread.start = counting_start
        self._orig_step = self.gui.__dict__.get('_infinite_shuffle_step')

        def spy_step():
            self.shuffle_steps += 1

        self.gui._infinite_shuffle_step = spy_step
        return self

    def __exit__(self, *exc):
        threading.Thread.start = self._orig_start
        if self._orig_step is None:
            self.gui.__dict__.pop('_infinite_shuffle_step', None)
        else:
            self.gui._infinite_shuffle_step = self._orig_step
        return False


def make():
    gui = SliderGUI(m=4, n=4, step=2)
    gui.animation_enabled = False
    gui._readonly = False
    gui.save_readonly_flag = False
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui.cmd_queue = queue.Queue()
    return gui


def base_state(g, switch_on=True):
    """回到「什么都没在跑」的干净态（开关可单独留着）。"""
    g.infinite_shuffle = switch_on
    g._infinite_shuffle_active = False
    g._infinite_shuffle_step_playing = False
    g._infinite_anchor = None
    g._auto_solve_running = False
    g._auto_solve_cancel = False
    g._auto_solve_done = False
    g._auto_solve_start_time = time.time()
    g._auto_streamed = False
    g._gradient_busy = False
    g._gradient_state = None
    g.macro_executing = False
    g.macro_exec_name = ''
    g.macro_recording = False
    g.animating = False
    g.anim_blocks = []
    g.timer_state = 'idle'
    g.game_mode = 'practice'
    g.tut_solution_replaying = False
    g._ann_recording = False
    g._readonly = False
    g.solver_algorithm = 'ida_star'
    g.macro_notify_msg = ''
    g.macro_notify_timer = 0
    g.macro_notify_persistent = False
    g._mode_conflict_notice_frames = 0
    g._api_solve_latch = None


def run_cmd(g, cmd):
    """走 HTTP / stdin 共用的命令队列，拿结构化回执。"""
    resp = queue.Queue()
    g.cmd_queue.put((cmd, resp))
    g.process_commands()
    try:
        return resp.get_nowait()
    except queue.Empty:
        return None


def predicate_unit(g):
    """判据本身：只认「真的在跑」，设置开关开着不算。"""
    base_state(g)
    check('P1 都空闲 → 两个方向都放行',
          g._mode_conflict_msg('solve') == ''
          and g._mode_conflict_msg('infinite_shuffle') == '')

    g.infinite_shuffle = True
    check('P2 无限打乱开关常开但游走没开始 → 求解照常放行',
          g._mode_conflict_msg('solve') == '')

    g._infinite_shuffle_active = True
    check('P3 游走在跑 → 拦求解，文案取常量',
          g._mode_conflict_msg('solve') == SOLVER_BLOCKED_BY_SHUFFLE_MSG)
    check('P4 游走在跑 → 不再拦「开游走」',
          g._mode_conflict_msg('infinite_shuffle') == '')

    base_state(g)
    g._auto_solve_running = True
    check('P5 求解在跑 → 拦开游走，文案取常量',
          g._mode_conflict_msg('infinite_shuffle') == SHUFFLE_BLOCKED_BY_SOLVER_MSG)
    check('P6 求解在跑 → 不再拦求解（那一下是取消）',
          g._mode_conflict_msg('solve') == '')

    g.macro_executing = True
    g.macro_exec_name = '自动求解'
    g._auto_solve_running = False
    check('P7 解法宏播放中（后台已停）也算求解在跑',
          g._mode_conflict_msg('infinite_shuffle') == SHUFFLE_BLOCKED_BY_SOLVER_MSG)


def forward(g, sp):
    print('[A] 正向：冲突局面造不出来')
    # A1 打乱中 → 核心求解入口（按钮 / 快捷键 / 教程 / 菜单都汇到这里）
    base_state(g)
    g._infinite_shuffle_active = True
    t0 = sp.thread_starts
    g._start_auto_solve()
    check('A1 打乱中点求解：求解线程没起、running 没置位',
          sp.thread_starts == t0 and not g._auto_solve_running,
          'threads=%d running=%s' % (sp.thread_starts - t0,
                                     g._auto_solve_running))
    check('A1 打乱中点求解：明确提示且给常驻通知留了窗口',
          g.macro_notify_msg == SOLVER_BLOCKED_BY_SHUFFLE_MSG
          and g._mode_conflict_notice_frames > 0,
          repr(g.macro_notify_msg))

    # A2 打乱中 → 结构化入口（_do_solve，命令面板 / HTTP 的公共前置）
    base_state(g)
    g._infinite_shuffle_active = True
    t0 = sp.thread_starts
    ok, msg = g._do_solve()
    check('A2 打乱中 _do_solve 返回 ok=False 与原句拒绝',
          ok is False and msg == SOLVER_BLOCKED_BY_SHUFFLE_MSG
          and sp.thread_starts == t0,
          'ok=%s msg=%r' % (ok, msg))

    # A3 打乱中 → HTTP / stdin 的 solve 指令
    base_state(g)
    g._infinite_shuffle_active = True
    t0 = sp.thread_starts
    rep = run_cmd(g, 'solve')
    check('A3 打乱中 solve 指令回执是拒绝，不假报「已启动」',
          isinstance(rep, dict) and rep.get('ok') is False
          and rep.get('message') == SOLVER_BLOCKED_BY_SHUFFLE_MSG
          and sp.thread_starts == t0,
          repr(rep))

    # A4 求解中 → 打乱入口（开关已开 = 本次要开游走）
    base_state(g)
    g._auto_solve_running = True
    s0 = sp.shuffle_steps
    g.shuffle_puzzle(confirm=False)
    check('A4 求解中调用打乱：游走没起、状态没被置位',
          sp.shuffle_steps == s0 and not g._infinite_shuffle_active,
          'steps=%d active=%s' % (sp.shuffle_steps - s0,
                                  g._infinite_shuffle_active))
    check('A4 求解中调用打乱：明确提示',
          g.macro_notify_msg == SHUFFLE_BLOCKED_BY_SOLVER_MSG,
          repr(g.macro_notify_msg))

    # A5 求解中 → 直接调无限打乱启动方法（绕开 shuffle_puzzle 的兜底）
    base_state(g)
    g._auto_solve_running = True
    s0 = sp.shuffle_steps
    g._start_infinite_shuffle()
    check('A5 求解中直接开游走也被拦',
          sp.shuffle_steps == s0 and not g._infinite_shuffle_active,
          'steps=%d active=%s' % (sp.shuffle_steps - s0,
                                  g._infinite_shuffle_active))

    # A6 求解中 → HTTP / stdin 的 shuffle 指令
    base_state(g)
    g._auto_solve_running = True
    s0 = sp.shuffle_steps
    rep = run_cmd(g, 'shuffle')
    check('A6 求解中 shuffle 指令回执是拒绝，不假报「已打乱」',
          isinstance(rep, dict) and rep.get('ok') is False
          and rep.get('message') == SHUFFLE_BLOCKED_BY_SOLVER_MSG
          and sp.shuffle_steps == s0 and not g._infinite_shuffle_active,
          repr(rep))

    # A7 互斥不能挡住「停止打乱」
    base_state(g)
    g._infinite_shuffle_active = True
    s0 = sp.shuffle_steps
    g.shuffle_puzzle(confirm=False)
    check('A7 打乱中再打乱仍能正常停止',
          not g._infinite_shuffle_active and sp.shuffle_steps == s0,
          'active=%s' % g._infinite_shuffle_active)

    # A8 互斥不能挡住「取消求解」
    base_state(g)
    g._auto_solve_running = True
    t0 = sp.thread_starts
    g._start_auto_solve()
    check('A8 求解中再点求解仍能正常取消',
          g._auto_solve_cancel is True
          and g.macro_notify_msg != SOLVER_BLOCKED_BY_SHUFFLE_MSG
          and sp.thread_starts == t0,
          'cancel=%s msg=%r' % (g._auto_solve_cancel,
                                g.macro_notify_msg))

    # A9 反向护栏：开关常开但游走没开始，求解照常可用（别误伤）
    base_state(g)
    t0 = sp.thread_starts
    g._start_auto_solve()
    check('A9 开关常开、游走没开始 → 求解真的能启动',
          sp.thread_starts == t0 + 1 and g._auto_solve_running,
          'threads=%d running=%s' % (sp.thread_starts - t0,
                                     g._auto_solve_running))


def reverse(g, sp):
    """真刀反向验证：中和判据后，冲突局面必须真的能被再制造出来。"""
    print('[B] 反向验证：中和共用判据（等价于撤掉判据）')
    # 只覆盖当前实例的方法，源文件一个字节都不动，无需还原保护。
    g._mode_conflict_msg = lambda want: ''

    # B1 打乱中 → 求解真启动了（冲突局面重现）
    base_state(g)
    g._infinite_shuffle_active = True
    t0 = sp.thread_starts
    g._start_auto_solve()
    check('B1 撤掉判据后，打乱中求解线程真的起来了',
          sp.thread_starts > t0 and g._auto_solve_running
          and g._infinite_shuffle_active,
          'threads=%d running=%s' % (sp.thread_starts - t0,
                                     g._auto_solve_running))

    # B2 打乱中 → 结构化入口假报成功（A2/A3 的绿不是别的 guard 给的）
    base_state(g)
    g._infinite_shuffle_active = True
    t0 = sp.thread_starts
    ok, msg = g._do_solve()
    rep = run_cmd(g, 'solve')
    check('B2 撤掉判据后，_do_solve 与 solve 指令都放进去了',
          ok is True and sp.thread_starts > t0
          and isinstance(rep, dict) and rep.get('ok') is True,
          'ok=%s rep=%r' % (ok, rep))

    # B3 求解中 → 游走真的起来了（A4/A5 的绿不是别的 guard 给的）
    base_state(g)
    g._auto_solve_running = True
    s0 = sp.shuffle_steps
    g.shuffle_puzzle(confirm=False)
    check('B3 撤掉判据后，求解中打乱真的把游走开起来了',
          sp.shuffle_steps > s0 and g._infinite_shuffle_active
          and g._auto_solve_running,
          'steps=%d active=%s' % (sp.shuffle_steps - s0,
                                  g._infinite_shuffle_active))

    # B4 求解中 → shuffle 指令也假报成功
    base_state(g)
    g._auto_solve_running = True
    s0 = sp.shuffle_steps
    rep = run_cmd(g, 'shuffle')
    check('B4 撤掉判据后，shuffle 指令真的开起了游走',
          isinstance(rep, dict) and rep.get('ok') is True
          and sp.shuffle_steps > s0 and g._infinite_shuffle_active,
          repr(rep))


def main():
    g = make()
    with Spies(g) as sp:
        predicate_unit(g)
        forward(g, sp)
        reverse(g, sp)
    print('\n结果：%s（%d 项通过）' % (
        '全部通过' if not _FAILS else '%d 项失败' % len(_FAILS), _OK[0]))
    if _FAILS:
        for m in _FAILS:
            print('  · 失败：', m)
        sys.exit(1)


if __name__ == '__main__':
    main()
