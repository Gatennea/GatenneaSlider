# -*- coding: utf-8 -*-
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from game import SliderMatrix
from solver.state import restore, snapshot
from solver.actions import enumerate_valid_actions, apply_action
from solver.ml.gather_solver import gather_solve

def load_fail(path):
    d = json.load(open(path, encoding='utf-8'))
    p = d['puzzle']; b0 = d['history']['snapshots'][0]
    mat = b0['matrix']; bd = b0['bounds']
    blocks = [[bd['min_row']+i, bd['min_col']+j] for i in range(len(mat)) for j in range(len(mat[i])) if mat[i][j]==1]
    return {'m':p['m'],'n':p['n'],'step':p['step'],'blocks':blocks}

def probe(label, make_game):
    g = make_game()
    total = g.m * g.n
    cands = enumerate_valid_actions(g, 2)
    print(f"[{label}] blocks={len(g.blocks)} total={total} cands={len(cands)}")
    ok_apply = 0; bad_apply = 0; bad_count = 0
    for act in cands[:8]:
        snap = snapshot(g)
        before = len(g.blocks)
        ok = apply_action(g, act, 2)
        after = len(g.blocks)
        restore(g, snap)
        if not ok:
            bad_apply += 1
        else:
            ok_apply += 1
            if after != total:
                bad_count += 1
    print(f"  前8候选: apply成功={ok_apply} 失败={bad_apply} 成功但丢块={bad_count}")

print("=== 全新 8x8 打乱 ===")
import random
random.seed(7)
g = SliderMatrix(8,8); g.shuffle(attempts=120, step=2)
probe("fresh8", lambda: (lambda gg: gg)(g))
r = gather_solve(SliderMatrix(8,8).__class__(8,8) and (lambda: (g2:=SliderMatrix(8,8), g2.shuffle(attempts=120,step=2), g2)[2])(), step=2, max_steps=2000, patience=150, max_wait_time=20, target_gather_score=1.0, aggressiveness=0.2, optimize_path=True, stochastic=False)
print("  fresh8 gather: solved=",r['solved'],"steps=",len(r['actions']),"reason=",r['reason'],"sc=",round(r['end']['score'],4))

print("\n=== 还原 FAIL04 ===")
rec = load_fail('archives/失败04.json')
g4 = SliderMatrix(8,8); restore(g4, rec)
probe("FAIL04", lambda: g4)
r4 = gather_solve(SliderMatrix(8,8), step=2, max_steps=2000, patience=150, max_wait_time=20, target_gather_score=1.0, aggressiveness=0.2, optimize_path=True, stochastic=False)
# 重新还原（上面 probe 没改 g4，但保险起见）
g4b = SliderMatrix(8,8); restore(g4b, rec)
r4 = gather_solve(g4b, step=2, max_steps=2000, patience=150, max_wait_time=20, target_gather_score=1.0, aggressiveness=0.2, optimize_path=True, stochastic=False)
print("  FAIL04 gather: solved=",r4['solved'],"steps=",len(r4['actions']),"reason=",r4['reason'],"sc=",round(r4['end']['score'],4))
