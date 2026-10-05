# -*- coding: utf-8 -*-
"""复现「[自动求解] 出错: list index out of range」。

背景（2026-10-06 用户报）：
    config/config.json 里持久化的是 **旧的形态专用 key** `'mi_gather'` /
    `'tri_gather'`（2026-10-05 已从 SOLVER_ALGORITHMS 移除）。
    而 GUI 的 solve_thread 有一句 `SOLVER_ALGORITHMS.get(algorithm,
    SOLVER_ALGORITHMS['ida_star'])` —— 未知 key **静默兜底成 IDA\***。
    IDA* 是纯方形语义（h/v 缝隙 + 整数坐标），套到异形 game 上就可能抛异常。

本脚本逐个组合试：旧 key × 三种形态，打印真实 traceback。

跑法：``D:/python/python.exe -u experiments/_repro_auto_solve_indexerror.py``
"""

import os
import sys
import time
import traceback

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from GUI import SliderGUI  # noqa: E402
from solver import SOLVER_ALGORITHMS  # noqa: E402

gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False

DEADLINE_SEC = 4.0


def form_of(gui):
    try:
        from solver import game_form
        return game_form(gui.game)
    except Exception:
        return '?'


def setup_square(gui):
    gui.new_puzzle(4, 4, 2)
    import random
    random.seed(5)
    gui.game.shuffle(20, 2)


def setup_tri(gui):
    gui.new_triangle_puzzle(4, 2)
    import random
    random.seed(5)
    gui.game.shuffle(60, 2)


def setup_mi(gui):
    gui.new_mi_puzzle(3, 3, 2)
    import random
    random.seed(5)
    gui.game.shuffle(30, 2)


def try_pair(label, algo, setup):
    setup(gui)
    alg_name, solver_func = SOLVER_ALGORITHMS.get(
        algo, SOLVER_ALGORITHMS['ida_star'])
    mapped = alg_name.strip()
    kwargs = {}
    if algo == 'gather':
        for k, v in gui.gather_params.items():
            kwargs[k] = v if gui.gather_enabled.get(k, True) else None
    deadline = time.time() + DEADLINE_SEC
    try:
        solver_func(gui.game, step=gui.current_step,
                    cancel_check=lambda: time.time() > deadline,
                    progress_callback=lambda d: None, **kwargs)
        print(f'  OK   {label:12s} alg={algo:12s} → 实际执行 {mapped}')
    except Exception as e:
        print(f'  FAIL {label:12s} alg={algo:12s} → 实际执行 {mapped}：'
              f'{type(e).__name__}: {e}')
        traceback.print_exc()
        print('  ' + '-' * 60)


print('=== 旧形态专用 key（已从注册表移除）× 三种谜题形态 ===')
for algo in ('mi_gather', 'tri_gather'):
    for label, setup in (('方形', setup_square), ('三角', setup_tri),
                         ('米字格', setup_mi)):
        try_pair(label, algo, setup)

print()
print('=== 对照：正常统一入口 gather ===')
for label, setup in (('方形', setup_square), ('三角', setup_tri),
                     ('米字格', setup_mi)):
    try_pair(label, 'gather', setup)

print()
print('done.')
