# -*- coding: utf-8 -*-
"""诊断 forward_closure 大尺寸「逃逸/缺口」：E1（反向生成器） vs E2（正向生成器）一致性。

  E1 = {(q,p) : p ∈ B, q ∈ predecessors(p)}      反向生成器认为的正向边 q→p
  E2 = {(q,y) : q ∈ B, y ∈ forward_neighbors(q)}  正向生成器认为的正向边 q→y

预期（两者互逆、表完整）：E1 == E2，且 E1/E2 的所有端点都在 B 内。

差异解释：
  E1 − E2  : predecessors 生成了正向不可复现的「假前驱」
             → 表里混入垃圾状态 → 正向锥到不了 → 缺口(B−锥)
  E2 − E1 (y ∉ B) : forward_neighbors 的真边 predecessors 漏了
             → 该真边的目标没进表 → 逃逸(锥−B)
  E2 − E1 (y ∈ B) : 表内状态间的边被反向漏掉（说明反向图不完整，
             但不影响该状态已由别的路径入表）
  E1 中 q ∉ B : 当前代码生成的前驱不在表内 → 表是旧版代码建的（stale）

用法：
  python experiments/math_repro/edge_consistency.py --quick    # 只查日志里的 6 条逃逸样例边（秒级）
  python experiments/math_repro/edge_consistency.py 4_4_3      # 全量 E1/E2 对比（几十分钟）
  python experiments/math_repro/edge_consistency.py 4_4_2 --sample 20000  # 抽样对比
"""

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver import table_core as tc  # noqa: E402
from verify_coloring import load_table, parse_puzzle, render, table_key_to_cells  # noqa: E402

# forward_closure 日志里的逃逸边样例 (x_hash, y_hash)
ESCAPE_SAMPLES = {
    '4_4_3': [
        (26960769438285125911036711521534736097265866699405171716478833132803,
         26960769438285125909575187583458629436176380193204937505647341405185),
        (26960769438285125909575187583458629436176380193204937505647341405185,
         1766900985905872181781037178685759560664280306162051764311337295551923461),
        (26960769438260988736508070238563879163698240405052759437064580498184,
         26960769438260988736508137140799474755567668638985036226036622557960),
    ],
    '4_4_2': [
        (26960769450815384134599493936218591856362130879448560512829420470793,
         26960769438260989101883524172439718216568404258595897281511078494729),
        (26960771026392056525809552922684567173991496910727256927378898092553,
         26960771026392056525809552922684567173991496910764150415526317195785),
        (26960769438285125908113685860375251190369875575366318652370201281032,
         26960769438285125908113685860375251190369875575366319215320154702344),
    ],
}


def quick(puzzle):
    m, n, step = parse_puzzle(puzzle)
    total = m * n
    table, path, _ = load_table(puzzle)
    B = set(table.keys())
    print(f'[{puzzle}] 表 B={len(B):,}  快查 {len(ESCAPE_SAMPLES[puzzle])} 条逃逸样例边')
    for x, y in ESCAPE_SAMPLES[puzzle]:
        cells = set(tc.int_to_coords(x, total))
        t0 = time.time()
        fwd = tc.forward_neighbors(cells, step, total)
        t1 = time.time()
        preds = tc.predecessors(cells, m, n, step)
        t2 = time.time()
        print(f'  边 x→y: x∈B={x in B}  y∈B={y in B}  '
              f'forward_neighbors含y={y in fwd}  predecessors(x)含y={y in preds}  '
              f'(fwd {t1-t0:.2f}s, pred {t2-t1:.2f}s)')
    print('  解读: forward含y=是 → 边合法；predecessors(x)含y=否 → 反向生成器漏了该真边'
          '（逃逸根因）；两者都否 → 我的正向边生成有 bug')


def full(puzzle, sample=0):
    m, n, step = parse_puzzle(puzzle)
    total = m * n
    table, path, complete = load_table(puzzle)
    B = set(table.keys())
    states = sorted(B)
    if sample and sample < len(states):
        random.seed(0)
        states = random.sample(states, sample)
    print('=' * 66)
    print(f'[{puzzle}] B={len(B):,} 完整={complete}  '
          f'{"全量" if not sample or sample >= len(B) else f"抽样 {len(states):,}"} 对比 E1 vs E2')

    t0 = time.time()
    E1 = set()
    q_outside = 0
    for i, p in enumerate(states):
        cells = set(tc.int_to_coords(p, total))
        for q in tc.predecessors(cells, m, n, step):
            E1.add((q, p))
            if q not in B:
                q_outside += 1
        if (i + 1) % 2000 == 0:
            print(f'  E1 进度 {i+1:,}/{len(states):,}  ({time.time()-t0:.0f}s)', flush=True)
    print(f'  E1(predecessors) = {len(E1):,} 条  其中 q∉B {q_outside:,}  ({time.time()-t0:.0f}s)')

    t1 = time.time()
    E2 = set()
    for i, q in enumerate(states):
        cells = set(tc.int_to_coords(q, total))
        for y in tc.forward_neighbors(cells, step, total):
            E2.add((q, y))
        if (i + 1) % 5000 == 0:
            print(f'  E2 进度 {i+1:,}/{len(states):,}  ({time.time()-t1:.0f}s)', flush=True)
    print(f'  E2(forward_neighbors) = {len(E2):,} 条  ({time.time()-t1:.0f}s)')

    miss_fwd = E1 - E2          # 假前驱
    miss_pred_in = {(q, y) for q, y in E2 - E1 if y in B}
    miss_pred_out = {(q, y) for q, y in E2 - E1 if y not in B}
    out_targets = {y for _, y in E2 if y not in B}

    print(f'  E1 − E2 (假前驱，导致缺口) = {len(miss_fwd):,}')
    for q, p in list(miss_fwd)[:3]:
        print(f'    predecessors({p}) 含 q，但 forward_neighbors(q) 不含 p；q∈B={q in B}')
        print('    q ='); print(render(table_key_to_cells(q, total)))
        print('    p ='); print(render(table_key_to_cells(p, total)))
    print(f'  E2 − E1 目标在B内 (反向漏边) = {len(miss_pred_in):,}')
    for q, y in list(miss_pred_in)[:3]:
        print(f'    forward_neighbors({q}) 含 y∈B，但 predecessors(q) 不含 y')
        print('    q ='); print(render(table_key_to_cells(q, total)))
        print('    y ='); print(render(table_key_to_cells(y, total)))
    print(f'  E2 − E1 目标不在B (逃逸边) = {len(miss_pred_out):,}，'
          f'涉及目标状态 {len(out_targets):,} 个（对照 forward_closure 逃逸数）')
    for q, y in list(miss_pred_out)[:3]:
        print(f'    forward_neighbors({q}) 含 y∉B，predecessors(q) 也不含 y；q∈B={q in B}')
        print('    q ='); print(render(table_key_to_cells(q, total)))
        print('    y ='); print(render(table_key_to_cells(y, total)))

    if not miss_fwd and not miss_pred_out and not q_outside:
        print('  ✓ E1/E2 在抽样范围内一致，逃逸/缺口更可能是表 stale（旧版代码建表）')
    print(f'  总用时 {time.time()-t0:.0f}s')


def main():
    ap = argparse.ArgumentParser(description='predecessors vs forward_neighbors 一致性检验')
    ap.add_argument('puzzles', nargs='*', default=['4_4_3'])
    ap.add_argument('--quick', action='store_true', help='只查日志逃逸样例边')
    ap.add_argument('--sample', type=int, default=0, help='抽样状态数（0=全量）')
    args = ap.parse_args()

    for p in args.puzzles:
        if args.quick:
            quick(p)
        else:
            full(p, sample=args.sample)
        print()


if __name__ == '__main__':
    main()
