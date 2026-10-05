# -*- coding: utf-8 -*-
r"""地毯式找「list index out of range」的触发条件。

逐个组合试：三种形态 × 若干尺寸/等级 × 若干随机种子 × 注册表里每个算法，
各自给一个短 deadline，把**所有异常按类型汇总**，每类打一条完整 traceback。

跑法：``D:/python/python.exe -u experiments/_fuzz_auto_solve.py``

背景：用户报「[自动求解] 出错: list index out of range」，但 GUI 的 except
只 print 了异常对象、**没打 traceback**，所以无法定位。已知的一条诱因是
config 里的旧形态专用 key 被静默兜底成 IDA*（见
``_repro_auto_solve_indexerror.py``）；本脚本继续找**剩下的**触发点。
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

DEADLINE_SEC = 3.0

gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False

hits = defaultdict(list)          # 异常类型 -> [(描述, traceback 文本)]
runs = 0


def _gather_kwargs(gui):
    """复刻 GUI solve_thread 给聚拢算法传参的方式（禁用的传 None）。"""
    out = {}
    for k, v in gui.gather_params.items():
        out[k] = v if gui.gather_enabled.get(k, True) else None
    return out


def boards():
    """(标签, setup 函数) 列表。"""
    import random

    def mk(kind, *a, **kw):
        shuf = kw.pop('shuf', 20)

        def _setup(g):
            getattr(g, kind)(*a)
            random.seed(kw.pop('seed', 1))
            try:
                g.game.shuffle(shuf, g.current_step)
            except Exception:
                pass
        return _setup

    out = []
    for step in (1, 2):
        for seed in (1, 7):
            out.append((f'方形4x4 s{step} seed{seed}',
                        mk('new_puzzle', 4, 4, step, shuf=20, seed=seed)))
            out.append((f'方形5x5 s{step} seed{seed}',
                        mk('new_puzzle', 5, 5, step, shuf=30, seed=seed)))
            out.append((f'三角k4 s{step} seed{seed}',
                        mk('new_triangle_puzzle', 4, step, shuf=60,
                           seed=seed)))
            out.append((f'米字3x3 s{step} seed{seed}',
                        mk('new_mi_puzzle', 3, 3, step, shuf=30, seed=seed)))
    return out


def run_one(label, algo_key):
    global runs
    alg_name, solver_func = SOLVER_ALGORITHMS[algo_key]
    kwargs = _gather_kwargs(gui) if algo_key == 'gather' else {}
    deadline = time.time() + DEADLINE_SEC
    runs += 1
    try:
        solver_func(gui.game, step=gui.current_step,
                    cancel_check=lambda: time.time() > deadline,
                    progress_callback=lambda d: None, **kwargs)
    except Exception as e:
        key = f'{type(e).__name__}: {e}'
        tb = traceback.format_exc()
        hits[key].append((f'{label} | alg={algo_key} ({alg_name.strip()})', tb))


for label, setup in boards():
    setup(gui)
    for algo_key in SOLVER_ALGORITHMS:
        run_one(label, algo_key)

print(f'\n===== 共 {runs} 次调用，异常 {sum(len(v) for v in hits.values())} 次 =====')
for key in sorted(hits):
    cases = hits[key]
    print(f'\n--- {key}  ×{len(cases)} ---')
    for desc, _tb in cases[:6]:
        print(f'    {desc}')
    print('  首次 traceback：')
    for line in cases[0][1].strip().splitlines():
        print('   ', line)

print('\ndone.')
