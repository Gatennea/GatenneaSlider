# -*- coding: utf-8 -*-
"""临时：确定性 / 随机可复现 自检（不进 git，运行完即删）。
按子代理 Task C 规格：4x4, shuffle(attempts=40, step=2), optimize_path=True。
"""
import sys, random
sys.path.insert(0, '.')
from game import SliderMatrix
from solver.state import snapshot, restore
from solver.ml.gather_solver import gather_solve

def make_disk():
    g = SliderMatrix(4, 4)
    g.shuffle(attempts=40, step=2)
    return snapshot(g)

def run_on(disk, **kw):
    g = SliderMatrix(4, 4)
    restore(g, disk)
    return gather_solve(g, step=2, max_steps=500, patience=150,
                       max_wait_time=15, target_gather_score=1.0,
                       aggressiveness=0.2, optimize_path=True, **kw)

print("== 1. 确定性臂可复现（stochastic=False 跑两次）==")
disk = make_disk()
r1 = run_on(disk, stochastic=False, seed=None)
r2 = run_on(disk, stochastic=False, seed=None)
a1, a2 = r1['actions'], r2['actions']
ok1 = (a1 == a2) and (r1['seed'] is None and r2['seed'] is None)
print("  actions 完全相同:", a1 == a2, "  len:", len(a1), len(a2))
print("  seed 字段均为 None:", r1['seed'] is None and r2['seed'] is None)
print("  => PASS" if ok1 else "  => FAIL")

print("== 2. 随机臂固定种子可复现（stochastic=True seed=999 跑两次）==")
disk = make_disk()
s1 = run_on(disk, stochastic=True, seed=999)
s2 = run_on(disk, stochastic=True, seed=999)
ok2 = (s1['actions'] == s2['actions']) and (s1['seed'] == 999 and s2['seed'] == 999)
print("  actions 完全相同:", s1['actions'] == s2['actions'], "  len:", len(s1['actions']), len(s2['actions']))
print("  seed 字段==999:", s1['seed'] == 999 and s2['seed'] == 999)
print("  => PASS" if ok2 else "  => FAIL")

print("== 3. 随机臂 vs 确定性臂轨迹不同 + kick 触发情况 ==")
disk = make_disk()
rd = run_on(disk, stochastic=False, seed=None)
rs = run_on(disk, stochastic=True, seed=999)
diff = rd['actions'] != rs['actions']
print("  actions 不同(应=True):", diff)
print("  确定性 len", len(rd['actions']), " 随机 len", len(rs['actions']))
print("  随机臂 kicks 触发次数:", rs['kicks'], " seed:", rs['seed'])

print("\nSUMMARY: 1=", "PASS" if ok1 else "FAIL",
      " 2=", "PASS" if ok2 else "FAIL",
      " 3_differs=", diff)
