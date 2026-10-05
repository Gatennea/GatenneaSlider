# -*- coding: utf-8 -*-
r"""离线复现「填洞宏冷冻elliJ卡住 + IndexError」——棋盘从 5050 现场抓下来。

现场（`GET /status`）：
    puzzle=2~8*8，64 块，row -30..-15，col -10..0，step=2，step_count=8
    `GET /solver/status`：algorithm=fill_macro，state=cancelled，
    elapsed_ms 冻结在 122025，progress.nodes 停在 **0**（stage=宏级搜索）

nodes=0 的意义：DFS 每 20 节点才 emit 一次进度，进 DFS 后**一次都没发** →
说明它卡在**第一个节点内部**（`_couples` / `_reshape_edges`），而这两个函数
的串行成本注释里自己写了「数十秒」。cancel_check / 时间预算只写在 dfs() 开头，
单节点内部的几十秒里**完全不检查** → 取消不掉、界面无响应。

跑法：``D:/python/python.exe -u experiments/_repro_fill_macro_freeze.py``
"""

import json
import os
import sys
import time
import traceback

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from game import SliderMatrix  # noqa: E402
from solver.ml.fill_macro import solve_fill_macro  # noqa: E402

BOARD = os.path.join(_ROOT, 'experiments', '_frozen_board.json')

with open(BOARD, encoding='utf-8') as f:
    d = json.load(f)

m, n, step = d['m'], d['n'], d['step']
coords = [(b['row'], b['col']) for b in d['blocks']]
print(f'棋盘 {m}x{n} step={step}，{len(coords)} 块')

game = SliderMatrix(m, n)
for b, loc in zip(game.blocks, coords):
    b.location = [loc[0], loc[1]]
game.update_matrix()   # 注：方形 SliderMatrix 没有 _clear_selection（那是 tri/mi 的）
print('is_solved =', game.is_solved())

t0 = time.time()
_last = [0.0]


def progress(**info):
    now = time.time()
    if now - _last[0] >= 5:
        _last[0] = now
        print(f'  [{now - t0:6.1f}s] stage={info.get("stage")} '
              f'nodes={info.get("nodes")} {str(info.get("path_preview"))[:40]}')


print('\n=== 启动 fill_macro（与 GUI 一致：cancel_check=None 拿不到取消信号）===')
try:
    res = solve_fill_macro(game, step=step, cancel_check=None,
                           progress_callback=progress)
    dt = time.time() - t0
    print(f'\n结束 {dt:.1f}s → {type(res).__name__}')
    print('  结果摘要：', str(res)[:300])
except Exception as e:
    dt = time.time() - t0
    print(f'\n★ 复现到异常（{dt:.1f}s）：{type(e).__name__}: {e}')
    traceback.print_exc()

print('\ndone.')
