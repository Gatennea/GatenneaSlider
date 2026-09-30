# -*- coding: utf-8 -*-
"""分析新手教程第4关（缺口）存档：重建动作、重放、逐步渲染，
并尝试自动识别 外层共轭 A … A' 的嵌套结构。
"""
import argparse
import json
import os

from experiments import harness as H

ARCH = os.path.join(H.ROOT, 'beginner_archive')


def load_save(sub):
    with open(os.path.join(ARCH, f'{sub}.json'), encoding='utf-8') as f:
        return json.load(f)


def initial_coords(save):
    s0 = save['history']['snapshots'][0]
    b = s0['bounds']
    coords = set()
    for r, row in enumerate(s0['matrix']):
        for c, v in enumerate(row):
            if v:
                coords.add((r + b['min_row'], c + b['min_col']))
    return frozenset(coords)


def infer_action(mi):
    gt, gl, d = mi['gap_type'], mi['gap_line'], mi['direction']
    moved = mi['moved_positions']
    if gt == 'h':
        side = 'above' if moved[0][0] <= gl else 'below'
    else:
        side = 'left' if moved[0][1] <= gl else 'right'
    # 每步可能滑动 k×基础步长，step 以 move_info 记录为准
    return (gt, gl, side, d), tuple(moved[0]), mi['step']


def build_actions(save):
    """返回 [(action, rep_cell, move_step), ...]。"""
    out = []
    for s in save['history']['snapshots'][1:]:
        mi = s.get('move_info')
        if mi:
            out.append(infer_action(mi))
    return out


def render(coords, label=''):
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    r0, r1, c0, c1 = min(rs), max(rs), min(cs), max(cs)
    print(f"-- {label} ({len(coords)}格)")
    for r in range(r0, r1 + 1):
        print('   ' + ''.join('#' if (r, c) in coords else '.'
                              for c in range(c0, c1 + 1)))


def analyze(sub, show_steps=False):
    save = load_save(sub)
    m, n, step = save['puzzle']['m'], save['puzzle']['n'], save['puzzle']['step']
    coords0 = initial_coords(save)
    steps = build_actions(save)

    g = H.load_game({'m': m, 'n': n, 'step': step, 'coords': sorted(coords0)})
    print(f"\n===== 子关 {sub}  {m}x{n} step{step}  共{len(steps)}步 =====")
    render(coords0, '初始(缺口)')
    if show_steps:
        for i, (a, rep, mstep) in enumerate(steps):
            from experiments.exp9_rep import _apply_with_rep
            _apply_with_rep(g, a, mstep, rep)
            render(H.coords_of(g), f'步{i+1} {a} step{mstep}')
    else:
        from experiments.exp9_rep import _apply_with_rep
        for a, rep, mstep in steps:
            _apply_with_rep(g, a, mstep, rep)
    print(f"   重放复原: {g.is_solved()}")
    return [a for a, _, _ in steps], g.is_solved()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sub', default='4.1')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--steps', action='store_true')
    args = ap.parse_args()
    if args.all:
        for k in range(1, 7):
            analyze(f'4.{k}', args.steps)
    else:
        analyze(args.sub, True)


if __name__ == '__main__':
    main()
