# -*- coding: utf-8 -*-
"""solver/anti_drift_engine.py 端到端：异形聚拢序列改写 + 漂移对比。"""
import random
import sys

ROOT = r'E:\program_project\other\doubaotest\slider\GatenneaSlider-doubao'
sys.path.insert(0, ROOT)

from game_triangle import TriangleSliderMatrix             # noqa: E402
from game_mi import MiSliderMatrix                         # noqa: E402
import solver.ml.tri_adapter as TA                         # noqa: E402
import solver.ml.mi_adapter as MA                          # noqa: E402
from solver.anti_drift_engine import rewrite_gather_actions  # noqa: E402

FAIL = []


def check(name, cond, detail=''):
    print(('  ok   ' if cond else '  FAIL ') + name + ('' if cond else '  ' + str(detail)))
    if not cond:
        FAIL.append(name)


def drift(coords0, coords1):
    mr0 = min(c[0] for c in coords0)
    mc0 = min(c[1] for c in coords0)
    mr1 = min(c[0] for c in coords1)
    mc1 = min(c[1] for c in coords1)
    return max(abs(mr1 - mr0), abs(mc1 - mc0))


def end_coords(game, actions, step, ad, coords_fn):
    for a in actions:
        if not ad.apply_action(game, a, step):
            return None
    return coords_fn(game)


def case(tag, make, solve, ad, coords_fn, step):
    print(f'--- {tag} ---')
    g = make()
    start_coords = coords_fn(g)
    snap = ad.snap(g)
    res = solve(g)
    acts = res['actions']
    print(f'  原: {len(acts)} 步, 分 {res["score"]:.3f}, {res["reason"]}')
    if not acts:
        return
    # 回到起点，量原路径终点漂移
    ad.restore(g, snap)
    raw_end = end_coords(g, acts, step, ad, coords_fn)
    d_raw = drift(start_coords, raw_end)
    # 用起点局面改写
    ad.restore(g, snap)
    out = rewrite_gather_actions(g, acts, step)
    print(f'  改写: applied={out["applied"]} flips={out["flips"]} {out["note"]}')
    check(f'{tag}: 改写生效', out['applied'], out['note'])
    if not out['applied']:
        return
    check(f'{tag}: 步数不变', len(out['actions']) == len(acts))
    ad.restore(g, snap)
    new_end = end_coords(g, out['actions'], step, ad, coords_fn)
    check(f'{tag}: 新序列可回放', new_end is not None)
    d_new = drift(start_coords, new_end)
    print(f'  漂移: {d_raw:.2f} → {d_new:.2f} 格')
    check(f'{tag}: 漂移下降', d_new <= d_raw + 1e-9, f'{d_raw} → {d_new}')
    check(f'{tag}: 形状不变',
          ad.tri_canonical(new_end) == ad.tri_canonical(raw_end)
          if tag.startswith('tri')
          else ad.mi_canonical(new_end) == ad.mi_canonical(raw_end))


def _move_to_act(spec, mv):
    """引擎 Move → 米字 5 元组动作（rep 取选中片里排序最小的块）。"""
    from engine.compat import direction_table
    fam = next(f for f in spec.seam_families if f.name == mv.family)
    raw = (mv.t - 1) / fam.line_scale
    line = int(raw) if float(raw).is_integer() else raw
    letter = next(k for k, v in direction_table(spec).items()
                  if v == mv.direction)
    side = 0 if mv.side == -1 else 1
    p, o = mv.moved[0]
    rep = tuple(int(x / 2) if (x / 2).is_integer() else x / 2 for x in p) + (o,)
    return (mv.family, line, side, letter, rep)


def _mi_big_walk(game, step, n):
    """在引擎盘上随机走 n 步，**偏向选中片大的动作**（大片推动正是防偏移的目标）。"""
    from engine.board import Board
    from engine.registry import mi_spec
    spec = mi_spec(game.m, game.n)
    keys = {((int(round(2 * b.location[0])),
              int(round(2 * b.location[1]))), b.location[2]): b.group
            for b in game.blocks}
    b = Board.from_keys(spec, frozenset(keys),
                        {k: v for k, v in keys.items() if v} or None)
    acts = []
    for _ in range(n):
        legal = sorted(b.legal_moves(step), key=lambda m: -len(m.moved))
        if not legal:
            break
        legal.sort(key=lambda m: -len(m.moved))
        pool = legal[:max(1, len(legal) // 4)]
        mv = random.choice(pool)
        acts.append(_move_to_act(spec, mv))
        b = b.apply(mv)
    return acts


def main():
    random.seed(0)
    case('tri k=4 s2 seed0',
         lambda: (lambda g: (g.shuffle(120, 2), g)[1])(TriangleSliderMatrix(4)),
         lambda g: TA.tri_gather_solve(g, step=2, max_steps=500, patience=150,
                                       max_wait_time=20.0),
         TA, TA.tri_coords, 2)

    random.seed(0)
    print('--- mi 3x3 s1 seed0：偏向大片的随机游走（逼出换侧）---')
    g = MiSliderMatrix(3, 3)
    g.shuffle(60, 1)
    start_coords = MA.mi_coords(g)
    acts = _mi_big_walk(g, 1, 20)
    snap0 = MA.snap(g)
    raw_end = end_coords(g, acts, 1, MA, MA.mi_coords)
    d_raw = drift(start_coords, raw_end)
    # 回到起点再改写（同一盘面；上一版测试在这里建了另一个 g2，取盘错误）
    MA.restore(g, snap0)
    out = rewrite_gather_actions(g, acts, 1, start_coords=start_coords)
    print(f'  序列 {len(acts)} 步')
    print(f'  改写: applied={out["applied"]} flips={out["flips"]} {out["note"]}')
    check('mi: 改写生效', out['applied'], out['note'])
    check('mi: 步数不变', len(out['actions']) == len(acts))
    if out['applied']:
        new_end = end_coords(g, out['actions'], 1, MA, MA.mi_coords)
        d_new = drift(start_coords, new_end)
        print(f'  漂移: {d_raw:.2f} → {d_new:.2f} 格')
        check('mi: 漂移下降', d_new <= d_raw + 1e-9, f'{d_raw} → {d_new}')
        check('mi: 形状不变',
              MA.mi_canonical(new_end) == MA.mi_canonical(raw_end))

    print()
    if FAIL:
        print(f'{len(FAIL)} 项失败: {FAIL}')
        return 1
    print('全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
