# -*- coding: utf-8 -*-
r"""第二轮 fuzz：**专找 IndexError**，并且补上第一轮漏掉的「已还原 / 几乎没打乱」的盘。

第一轮的坑：每个局面都 shuffle 过，**没试还原态**。而「无事可做」的盘恰恰是
`IndexError: list index out of range` 的高发场景（空列表被取 [0]）。

跑法：``D:/python/python.exe -u experiments/_fuzz_index_error.py``
"""

import os
import sys
import time
import traceback
from collections import defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from GUI import SliderGUI  # noqa: E402
from solver import SOLVER_ALGORITHMS  # noqa: E402

DEADLINE_SEC = 2.0

gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False

hits = defaultdict(list)
runs = 0


def run_one(label, algo_key, game):
    global runs
    alg_name, solver_func = SOLVER_ALGORITHMS[algo_key]
    kwargs = {}
    if algo_key == 'gather':
        for k, v in gui.gather_params.items():
            kwargs[k] = v if gui.gather_enabled.get(k, True) else None
    deadline = time.time() + DEADLINE_SEC
    runs += 1
    try:
        solver_func(game, step=gui.current_step,
                    cancel_check=lambda: time.time() > deadline,
                    progress_callback=lambda d: None, **kwargs)
    except Exception as e:
        hits[f'{type(e).__name__}: {e}'].append(
            (f'{label} | alg={algo_key} ({alg_name.strip()})',
             traceback.format_exc()))


import random  # noqa: E402

# ---------------------------------------------------------- 方形：全算法
for size in (3, 4, 5):
    for step in (1, 2):
        for shuf in (0, 15):           # ← 0 = 还原态（第一轮漏掉的）
            gui.new_puzzle(size, size, step)
            random.seed(11)
            if shuf:
                gui.game.shuffle(shuf, step)
            solved = gui.game.is_solved()
            label = f'方形{size}x{size} s{step} shuf{shuf}{"已还原" if solved else ""}'
            for algo_key in SOLVER_ALGORITHMS:
                run_one(label, algo_key, gui.game)

# ------------------------------------------------ 异形：只跑形态允许的 gather
for kind, args in (('new_triangle_puzzle', (4, 2)),
                   ('new_triangle_puzzle', (3, 1)),
                   ('new_mi_puzzle', (3, 3, 2)),
                   ('new_mi_puzzle', (4, 4, 1))):
    for shuf in (0, 30):
        getattr(gui, kind)(*args)
        random.seed(11)
        if shuf:
            gui.game.shuffle(shuf, gui.current_step)
        label = f'{kind}{args} shuf{shuf}'
        run_one(label, 'gather', gui.game)

print(f'\n===== 共 {runs} 次调用 =====')
if not hits:
    print('★ 没有复现出任何异常')
for key in sorted(hits):
    cases = hits[key]
    marker = '★ IndexError' if key.startswith('IndexError') else ''
    print(f'\n--- {marker} {key}  ×{len(cases)} ---')
    for desc, _ in cases[:8]:
        print(f'    {desc}')
    print('  首次 traceback：')
    for line in cases[0][1].strip().splitlines():
        print('   ', line)

print('\ndone.')
