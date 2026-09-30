# -*- coding: utf-8 -*-
"""实验7：逐段定位混合链拼接断点。

对每个 seed，按 hybrid 的真实顺序执行三段，并在每段后：
- 把"截至目前的动作"在全新游戏上重放；
- 比较重放态与求解器实际态的规范 key。
第一个 key 不一致的段就是病根。
"""
import argparse

from experiments import harness as H
from solver.state import snapshot, restore
from solver import table_core as TC


def key_of_coords(coords):
    return TC.canonicalize(frozenset(coords))


def diagnose(snap):
    from solver.ml.gather_solver import gradient_gather
    from solver.ml.fill_macro import solve_fill_macro
    from solver.table_solver import table_solve

    step = snap['step']
    print(f"\n== seed={snap['seed']} ==")

    # 段1：梯度聚拢
    g = H.load_game(snap)
    r = gradient_gather(g, step)
    A = list(r['actions'])
    actual_key = key_of_coords(H.coords_of(g))
    okA, gA = H.replay(snap, A)
    rep_key = key_of_coords(H.coords_of(gA))
    print(f"  [聚拢] 动作{len(A)} actual={actual_key} 重放={rep_key} "
          f"一致={actual_key == rep_key} 重放已解={okA}")

    if g.is_solved():
        return

    gathered = snapshot(g)
    s_gathered = H.gather_metrics(H.coords_of(g), g.m, g.n)['score']

    # 段2：填洞（与 exp6 完全一致的处理）
    res = solve_fill_macro(g, step)
    f = []
    if isinstance(res, tuple):
        f = list(res[0])
    elif isinstance(res, dict) and res.get('type') == 'fill_partial':
        f = list(res.get('actions', []))
    restore(g, gathered)
    for a in f:
        H.apply_action(g, a, step)
    if H.gather_metrics(H.coords_of(g), g.m, g.n)['score'] < s_gathered:
        restore(g, gathered)
        f = []
    actual_key2 = key_of_coords(H.coords_of(g))
    okAF, gAF = H.replay(snap, A + f)
    rep_key2 = key_of_coords(H.coords_of(gAF))
    print(f"  [填洞] 动作{len(f)} actual={actual_key2} 重放={rep_key2} "
          f"一致={actual_key2 == rep_key2} 重放已解={okAF}")
    if g.is_solved():
        return

    # 段3：查表
    r2 = table_solve(g, step)
    if not isinstance(r2, tuple):
        print(f"  [查表] 未返回路径: {r2}")
        return
    tpath, _reps = r2
    tpath = list(tpath)
    actual_solved = g.is_solved()
    okAll, gAll = H.replay(snap, A + f + tpath)
    print(f"  [查表] 动作{len(tpath)} 求解器实态已解={actual_solved} "
          f"全链路重放已解={okAll}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', default='1000,1016,1018')
    ap.add_argument('--configs', default='4x4x2')
    args = ap.parse_args()
    m, n, st = args.configs.split('x')
    for s in args.seeds.split(','):
        snap = H.gen_state(int(m), int(n), int(st), int(s))
        diagnose(snap)


if __name__ == '__main__':
    main()
