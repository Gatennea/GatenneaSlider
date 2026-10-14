# -*- coding: utf-8 -*-
"""
A：正向可达性闭合检验 + C：可逆性猜想程序化验证。

来源：docs/math/遊戲衍生的數學問題.md
  - 第一问：状态拓扑图 x→y 单向弧 / 双向弧
  - 「任何操作都是有限步内可逆的」猜想；「单步不可逆只有一种：
    任意两个滑块由不相邻到相邻的瞬间（粘连）」

实验设计（一次正向 BFS 同时回答 A 和 C）：
  B    = 反向 BFS 表（table.pkl，可解集）
  锥   = 从 goal 出发用 forward_neighbors 做正向 BFS 得到的正向可达集

  A（闭合）：锥 ⊆ B？
      锥 − B 非空 ⟹ 存在「从目标正向走得到、却不可解」的状态——
      玩家打乱时可能走进死局（即文档里担心的不可根除 bug）。
  A（覆盖）：B ⊆ 锥？
      B − 锥 非空 ⟹ 存在可解状态无法从目标正向到达。
  两者都空 ⟺ 锥 == B，图在可解集上闭合。

  C（有限步可逆）：对每条边 x→y（x,y ∈ B），检验 y 能否有限步回到 x。
      锥 == B 时自动成立：y →* goal（y 可解）且 goal →* x（x 在正向锥内）。
      逐边直接检验：算 y 的正向邻居，看 x 是否在其中（一步可逆）；
      一步不可逆的边，若两端都在 B 内，则用「y→goal→x」拼出有限步逆。

  C（单步不可逆类型）：对每条一步不可逆的边，给出移动分量 comp 与方向 d，
      判定类型：
        粘连型   —— 移动后的分量 comp+d 在 y 中不再是任何分割线侧的
                     连通分量（被别的滑块贴住，无法单独选中退回）
        回移违规 —— comp+d 仍可单独选中，但整体回移 step 格时
                     碰撞或中途断连（逆操作本身违规）

用法：
  python experiments/math_repro/forward_closure.py 3_3_2 2_3_1 3_3_1
  python experiments/math_repro/forward_closure.py 4_4_3
"""

import argparse
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver import table_core as tc  # noqa: E402
from verify_coloring import load_table, parse_puzzle, render, table_key_to_cells  # noqa: E402


# ---------------------------------------------------------------------------
# 正向边生成（镜像 forward_neighbors，额外带回移动分量与方向）
# ---------------------------------------------------------------------------
def _try_ext(B, comp, gap_type, L, side, D, step, total, out):
    d_unit = (D[0] // step if D[0] else 0, D[1] // step if D[1] else 0)
    non_sel = B - set(comp)
    cur = set(comp)
    for _ in range(step):
        cur = {(r + d_unit[0], c + d_unit[1]) for r, c in cur}
        if cur & non_sel:
            return
        if not tc.is_single_connected(cur | non_sel):
            return
    result = non_sel | cur
    if len(result) == total:
        out.append((tc.canonicalize(frozenset(result)), frozenset(comp), d_unit))


def forward_edges(cells, step, total):
    """[(result_hash, 移动分量comp, 单位方向d_unit), ...]，遍历逻辑同 forward_neighbors。"""
    B = set(cells)
    out = []
    rows = [r for r, _ in B]
    cols = [c for _, c in B]
    min_r, max_r = min(rows), max(rows)
    min_c, max_c = min(cols), max(cols)
    for L in range(min_r, max_r):
        for side in ('above', 'below'):
            for comp in tc._side_components(B, 'h', L, side):
                for sign in (-1, 1):
                    _try_ext(B, comp, 'h', L, side, (0, sign * step), step, total, out)
    for L in range(min_c, max_c):
        for side in ('left', 'right'):
            for comp in tc._side_components(B, 'v', L, side):
                for sign in (-1, 1):
                    _try_ext(B, comp, 'v', L, side, (sign * step, 0), step, total, out)
    return out


def shift_back_illegal(y_cells, moved, d_unit, step):
    """在 y 中把 moved 沿 -d_unit 整体回移 step 格：是否碰撞/中途断连。"""
    non_sel = y_cells - moved
    cur = set(moved)
    for _ in range(step):
        cur = {(r - d_unit[0], c - d_unit[1]) for r, c in cur}
        if cur & non_sel:
            return True
        if not tc.is_single_connected(cur | non_sel):
            return True
    return False


# ---------------------------------------------------------------------------
def analyze(puzzle, sample=3):
    m, n, step = parse_puzzle(puzzle)
    table, path, complete = load_table(puzzle)
    if table is None:
        print(f'[{puzzle}] 找不到表，跳过')
        return None
    B = set(table.keys())
    total = m * n
    goal = tc.canonicalize(tc.goal_state(m, n))

    print('=' * 66)
    print(f'[{puzzle}] K={total} step={step}  表 B={len(B):,}  {path}'
          f'{"" if complete else "  ⚠表不完整"}')
    assert goal in B, 'goal 不在表内？表口径异常'

    t0 = time.time()
    queue = deque([goal])
    visited = {goal}          # 正向锥
    edge_cache = {}           # x_hash -> 去重后的 [(y_hash, comp, d)]（x 用规范代表帧）
    cells_cache = {}          # hash -> 规范代表格集
    escapes = {}              # y -> (x, comp, d)：y 不在 B 内的首条出边
    n_edges = 0

    def cells_of(h):
        if h not in cells_cache:
            cells_cache[h] = frozenset(tc.int_to_coords(h, total))
        return cells_cache[h]

    while queue:
        h = queue.popleft()
        cells = set(cells_of(h))
        raw = forward_edges(cells, step, total)
        edges = []
        seen = set()
        for y, comp, d in raw:
            # 去重键用 (comp, d)：同状态同分量同方向的重复仅来自不同分割线，
            # 是同一操作；不能按 (y_hash, d) 去重——不同物理结果可能规范形相同
            if (comp, d) in seen:
                continue
            seen.add((comp, d))
            edges.append((y, comp, d))
        edge_cache[h] = edges

        for y, comp, d in edges:
            n_edges += 1
            if y not in B and y not in escapes:
                escapes[y] = (h, comp, d)
            if y not in visited:
                visited.add(y)
                queue.append(y)

    # 逐边一步可逆性（只对「边的终点」按需取规范帧邻居）
    def edges_of(h):
        if h not in edge_cache:
            raw = forward_edges(set(cells_of(h)), step, total)
            edge_cache[h] = list({(y, cc, dd) for y, cc, dd in raw})
        return edge_cache[h]

    # 一步不可逆边的分类——全部在 x 的规范帧里做（y_abs 与 comp 同帧）：
    #   粘连型   moved=comp+d 在 y_abs 中不再是任何分割线侧的连通分量
    #   回移违规 moved 仍可单独选中，但整体回移有碰撞/中途断连
    #   异常     理论上不可出现（可选中 ⇒ 回移各步恰是正向路径倒放，必合法）
    irr = []
    n_rev = 0
    for h, edges in list(edge_cache.items()):
        x_cells = set(cells_of(h))
        for y, comp, d in edges:
            # 反向存在性在规范帧判定：canonicalize 平移/对称不变，判定无歧义
            back = any(y2 == h for y2, _, _ in edges_of(y))
            if back:
                n_rev += 1
                continue
            # 分类必须回到 x 的绝对帧：y_abs 才与 comp、moved 同一坐标系
            # 注意 edges 里存的是单位方向 d_unit，整步位移 = d_unit * step
            moved = {(r + d[0] * step, c + d[1] * step) for r, c in comp}
            y_abs = (x_cells - set(comp)) | moved
            # 选中与轴绑定：h 线只能水平滑（D=(0,±step)），v 线只能垂直滑，
            # 反向移动必须能由对应轴的分割线选出 moved 才算「仍可选中」
            gap = 'h' if d[0] == 0 else 'v'
            if moved not in _all_side_components(y_abs, gap):
                kind = '粘连型'
            elif shift_back_illegal(y_abs, moved, d, step):
                kind = '回移违规'
            else:
                kind = '异常'
            irr.append((h, y, comp, d, kind))

    dt = time.time() - t0
    reach = visited
    esc = reach - B
    miss = B - reach

    print(f'  正向锥 |锥| = {len(reach):,}   用时 {dt:.1f}s')
    print(f'  A 闭合: 锥 − B = {len(esc):,} '
          f'{"✓ 正向移动永远不离开可解集" if not esc else "✗ 存在逃出可解集的状态!"}')
    print(f'  A 覆盖: B − 锥 = {len(miss):,} '
          f'{"✓ 每个可解状态都能从目标正向到达" if not miss else "✗ 存在到不了的状态!"}')
    print(f'  边数 {n_edges:,}；一步可逆 {n_rev:,}；一步不可逆 {len(irr):,}')

    if esc:
        print('  ✗ 逃逸状态样例（正向可达但不可解 = 真死局）:')
        for y in list(esc)[:sample]:
            x, comp, d = escapes[y]
            print(f'    边 {x} -> {y}  comp={sorted(comp)} d={d}')
            print(render(table_key_to_cells(y, total)))
    if miss:
        print('  ✗ 锥外可解状态样例:')
        for h in list(miss)[:sample]:
            print(render(table_key_to_cells(h, total)))

    if irr:
        by_kind = {}
        for e in irr:
            by_kind[e[4]] = by_kind.get(e[4], 0) + 1
        print(f'  一步不可逆分类: {by_kind}')
        for h, y, comp, d, kind in irr[:sample]:
            print(f'    [{kind}] {h} -> {y}  comp={sorted(comp)} d={d}')

    # C 总判定
    finite_ok = (not esc) and (not miss)
    print(f'  C 有限步可逆猜想: '
          f'{"✓ 验证成立（锥 == B，任一边 y→*goal→*x 拼出有限步逆）" if finite_ok else "✗ 发现反例/缺口"}')

    return {'puzzle': puzzle, 'B': len(B), 'reach': len(reach),
            'escapes': len(esc), 'missing': len(miss), 'edges': n_edges,
            'irr': len(irr), 'irr_kinds': by_kind if irr else {},
            'finite_ok': finite_ok, 'secs': round(dt, 1)}


def _all_side_components(cells, gap_type=None):
    """状态「分割线一侧的连通分量」集合；gap_type='h'/'v' 时只取该轴的线。"""
    cells = set(cells)
    out = set()
    rows = [r for r, _ in cells]
    cols = [c for _, c in cells]
    if gap_type != 'v':
        for L in range(min(rows), max(rows)):
            for side in ('above', 'below'):
                for comp in tc._side_components(cells, 'h', L, side):
                    out.add(frozenset(comp))
    if gap_type != 'h':
        for L in range(min(cols), max(cols)):
            for side in ('left', 'right'):
                for comp in tc._side_components(cells, 'v', L, side):
                    out.add(frozenset(comp))
    return out


def main():
    ap = argparse.ArgumentParser(description='正向闭合 + 可逆性检验')
    ap.add_argument('puzzles', nargs='+', help='如 2_3_1 3_3_1 3_3_2 4_4_3')
    ap.add_argument('--sample', type=int, default=3, help='每类样例渲染数')
    args = ap.parse_args()

    results = []
    for p in args.puzzles:
        try:
            r = analyze(p, sample=args.sample)
            if r:
                results.append(r)
        except FileNotFoundError:
            print(f'[{p}] 找不到表，跳过')
        print()

    print('=' * 66)
    print('汇总：')
    for r in results:
        line = (f"  {r['puzzle']:<8} B={r['B']:>8,} 锥={r['reach']:>8,} "
                f"逃逸={r['escapes']:>4,} 缺口={r['missing']:>4,} "
                f"边={r['edges']:>8,} 一步不可逆={r['irr']:>5,} "
                f"{'✓猜想成立' if r['finite_ok'] else '✗有反例'} {r['secs']}s")
        print(line)


if __name__ == '__main__':
    main()
