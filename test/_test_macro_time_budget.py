# -*- coding: utf-8 -*-
r"""填洞宏 / 补缺宏的**墙钟总预算**回归锁。

起因（2026-10-06 用户报）：填洞宏执行阶段会莫名其妙卡住，界面无法重新选中 /
滑动 / 移动视角。离线复现（8×8 step2 散盘，棋盘从 5050 现场抓下）跑了
**183.6 秒** —— 根因是这条链只有**次数**上限（max_attempts / max_rounds），
**没有任何墙钟上限**，大散盘上每次 couple 尝试都很贵；求解线程 CPU 满载 →
主线程被 GIL 饿死 → 界面表现为完全卡住。

修法：GUI 入口 `solve_fill_macro` / `solve_gap_macro` 各加一条墙钟预算
（`time_budget`，默认 30s），到点走与用户取消**同一条** `_Cancelled` 出口，
保证在「轮 / DFS 节点」粒度上一定停得下来（实测 183.6s → 31.7s）。

本测试锁：
  P1 两个入口都接受 time_budget 参数；
  P2 极小预算下**快速返回**（不是烧几分钟）且标记为 timeout；
  P3 超时与「用户取消」文案可区分（timeout=True vs cancelled=True）；
  P4 默认预算是 30s 量级（不是 None / 0 = 永不超时）。

跑法：``D:/python/python.exe -u test/_test_macro_time_budget.py``
"""

import os
import random
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from game import SliderMatrix  # noqa: E402
from solver.ml.fill_macro import solve_fill_macro, _FILL_GUI_TIME_BUDGET  # noqa: E402
from solver.ml.gap_solver import solve_gap_macro, _GAP_GUI_TIME_BUDGET  # noqa: E402

_FAILURES = []


def check(desc, cond, extra=''):
    if not cond:
        _FAILURES.append(desc)
    print(f"[{'PASS' if cond else 'FAIL'}] {desc}"
          + (f'  {extra}' if extra else ''))


def scrambled(m=6, n=6, step=2, seed=7, times=60):
    g = SliderMatrix(m, n)
    random.seed(seed)
    g.shuffle(times, step)
    return g


# ===================================================== P1 签名接受 time_budget
print('\n--- P1 入口接受墙钟预算 ---')
import inspect  # noqa: E402

check('P1a solve_fill_macro 有 time_budget 参数',
      'time_budget' in inspect.signature(solve_fill_macro).parameters)
check('P1b solve_gap_macro 有 time_budget 参数',
      'time_budget' in inspect.signature(solve_gap_macro).parameters)

# ============================================ P2 极小预算 → 快速返回 + timeout
print('\n--- P2 极小预算必须立刻停（不能烧几分钟）---')
for name, fn in (('填洞宏', solve_fill_macro), ('补缺宏', solve_gap_macro)):
    g = scrambled()
    t0 = time.time()
    res = fn(g, step=2, cancel_check=None, progress_callback=None,
             time_budget=0.01)
    dt = time.time() - t0
    ok_fast = dt < 10.0
    is_fail = isinstance(res, dict) and res.get('type') == 'fill_fail'
    check(f'P2 {name} 极小预算快速返回（{dt:.2f}s < 10s）', ok_fast,
          f'{dt:.2f}s')
    if is_fail:
        check(f'P2 {name} 标记为 timeout（不是 cancelled）',
              res.get('timeout') is True and not res.get('cancelled'),
              str(res)[:90])
    else:
        # 极小预算下若恰好一步就解完也算正常，但必须快
        check(f'P2 {name} 未超时则也必须快速返回', ok_fast, str(res)[:90])

# ============================ P3 用户取消 vs 超时：文案/标记可区分
print('\n--- P3 取消与超时可区分 ---')
g = scrambled()
res_cancel = solve_fill_macro(g, step=2, cancel_check=lambda: True,
                              progress_callback=None, time_budget=30.0)
check('P3a 用户取消 → cancelled=True 且非 timeout',
      isinstance(res_cancel, dict) and res_cancel.get('cancelled') is True
      and not res_cancel.get('timeout'), str(res_cancel)[:90])

# ================================================== P4 默认预算是 30s 量级
print('\n--- P4 默认预算合理（有上限，不是永不超时）---')
check('P4a 填洞宏默认预算 > 0 且 ≤ 120s',
      0 < _FILL_GUI_TIME_BUDGET <= 120, str(_FILL_GUI_TIME_BUDGET))
check('P4b 补缺宏默认预算 > 0 且 ≤ 120s',
      0 < _GAP_GUI_TIME_BUDGET <= 120, str(_GAP_GUI_TIME_BUDGET))

print('\n' + '=' * 56)
if _FAILURES:
    print(f'FAILED {len(_FAILURES)} 项：')
    for f in _FAILURES:
        print('  -', f)
    sys.exit(1)
print('ALL PASS')
