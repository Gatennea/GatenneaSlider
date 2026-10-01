# -*- coding: utf-8 -*-
"""cancel 生效验证：2 秒后触发停止，统计退出耗时。"""
import json
import sys
import os
import time
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import build_game  # noqa: E402
from solver.ml.gap_solver import solve_gap_macro  # noqa: E402

path = os.path.join(_ROOT, 'save', '2-6-7-20261001-161826.json')
with open(path, encoding='utf-8') as f:
    doc = json.load(f)
m, n = doc['puzzle']['m'], doc['puzzle']['n']
step = doc['puzzle']['step']
snap = doc['history']['snapshots'][0]
b = snap['bounds']
coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                   for i, row in enumerate(snap['matrix'])
                   for j, v in enumerate(row) if v)
g = build_game(coords, m, n)

cancel = {'flag': False}
res_box = {}


def run():
    t0 = time.time()
    res_box['res'] = solve_gap_macro(
        g, step, cancel_check=lambda: cancel['flag'])
    res_box['secs'] = time.time() - t0


th = threading.Thread(target=run, daemon=True)
th.start()
time.sleep(2.0)
t_stop = time.time()
cancel['flag'] = True
th.join(timeout=30)
print('停止请求后 %.2fs 退出 (alive=%s)' % (time.time() - t_stop, th.is_alive()))
print('总耗时 %.2fs, 结果: %s' % (res_box.get('secs', -1),
                                 str(res_box.get('res'))[:120]))
