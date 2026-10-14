# -*- coding: utf-8 -*-
"""
严格验证猜想「着色集合相同 ⟹ 可解」（docs/math/遊戲衍生的數學問題.md 第三问）。

貓九提出的验证法：算出「原始着色集合」的所有状态，看与反向 BFS 建表的数字是否一致。
本脚本把它做成严格实验：

  A = 所有满足 mod 类计数（= 目标矩形的原始着色集合）的单连通状态，取规范形状
  B = 反向 BFS 表的全部规范状态（table.pkl，完整表才可信）

  A == B  → 猜想在该尺寸上严格成立
  A ⊃ B  → 找到反例：着色相同却不可解的形状（猜想为假）
  B ⊄ A  → mod 条件口径理解有误（sanity 失败，先修脚本再谈结论）

口径（关键，读结论前必须明白）：
  1. 表的 key = 「平移归一 + D4 八对称」的形状规范形（table_core.canonicalize），
     而正向邻居只依赖形状、与绝对坐标相位无关，因此「形状 key 在表中」
     ⟺ 该形状的任意具体状态都能沿 dist 递减重放回目标。比较放在形状级是充分的。
  2. mod 条件对绝对坐标相位敏感（平移一格会置换各类）。枚举只产出
     「含原点且坐标 ≥0」的规范代表（每平移类唯一），再遍历 step² 个相位平移
     判定该平移类是否存在满足着色条件的状态，覆盖不重。
  3. 目标有两种朝向（m×n 与 n×m 转置也算解），任一朝向着色匹配即可。
  4. step=1 时 mod 条件无信息量（全盘同类），A 退化为「全部单连通形状」，
     此时已知差集 = 直线型（Free(m×n)−1 的那个 −1），是现成反例。

数据位置：优先 solver/data/<puzzle>/table.pkl，其次外部建表库
（E:\\program_project\\other\\doubaotest\\狀態拓撲圖分析\\）。
只认 table.pkl（成品表）；只有 checkpoint.pkl 的不完整表默认拒绝
（B 不完整会把 A−B 误报成反例），用 --partial 只做 B⊆A 的单向检查。

用法：
  python experiments/math_repro/verify_coloring.py 3_3_2 4_4_3
  python experiments/math_repro/verify_coloring.py --complete      # 跑全部完整表
  python experiments/math_repro/verify_coloring.py 4_4_2 --with-all # 连「全部单连通形状」一起枚举（K=16 极慢）
"""

import argparse
import pickle
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver.table_core import canonicalize  # noqa: E402

DATA_DIRS = [
    ROOT / 'solver' / 'data',
    Path(r'E:\program_project\other\doubaotest\狀態拓撲圖分析'),
]

# 完整表（成品 table.pkl 存在）；不完整表要用 --partial 显式开启
COMPLETE_DEFAULT = ['2_3_1', '3_3_1', '3_3_2', '4_4_2', '4_4_3']

DIRS4 = ((-1, 0), (1, 0), (0, -1), (0, 1))


# ---------------------------------------------------------------------------
# 表加载
# ---------------------------------------------------------------------------
def load_table(puzzle, partial=False):
    """返回 (dist_dict, 路径, 是否完整)。只认成品 table.pkl 为完整。"""
    for d in DATA_DIRS:
        t = d / puzzle / 'table.pkl'
        if t.exists():
            with open(t, 'rb') as f:
                return pickle.load(f), t, True
    if not partial:
        return None, None, False
    for d in DATA_DIRS:
        c = d / puzzle / 'checkpoint.pkl'
        if c.exists():
            with open(c, 'rb') as f:
                data = pickle.load(f)
            frontier = data.get('frontier')
            return data['dist'], c, (not frontier)
    return None, None, False


def parse_puzzle(puzzle):
    """'3_3_2' -> (3, 3, 2)"""
    m, n, step = (int(x) for x in puzzle.split('_'))
    return m, n, step


# ---------------------------------------------------------------------------
# 着色（mod 类计数）条件
# ---------------------------------------------------------------------------
def class_dist(cells, step):
    cnt = Counter(((r % step, c % step) for r, c in cells))
    return frozenset(cnt.items())


def target_variants(m, n, step):
    """目标矩形在「两种朝向 × step² 个相位平移」下的全部合法着色集合。

    状态 S 满足着色条件 ⟺ class_dist(S) 落在这个集合里
    （对 S 做相位平移 与 对目标做反向相位平移 等价；
    变体集对相位平移封闭，所以「存在相位匹配」与「相位 0 分布落在此集」是同一件事）。
    返回 (frozenset[frozenset[(类,计数)]], list[list[int]] 按类索引的数组版)。
    """
    out = set()
    for a, b in {(m, n), (n, m)}:
        base = Counter()
        for r in range(a):
            for c in range(b):
                base[(r % step, c % step)] += 1
        for dr in range(step):
            for dc in range(step):
                shifted = frozenset(
                    (((kr + dr) % step, (kc + dc) % step), v)
                    for (kr, kc), v in base.items()
                )
                out.add(shifted)
    arrays = []
    for v in out:
        arr = [0] * (step * step)
        for (kr, kc), val in v:
            arr[kr * step + kc] = val
        arrays.append(arr)
    return frozenset(out), arrays


# ---------------------------------------------------------------------------
# 平移规范枚举：所有 |S|=K 单连通形状（min r = min c = 0）
# ---------------------------------------------------------------------------
def enumerate_states(K, target_arrays, step, on_state, progress_every=200_000):
    """从 {(0,0)} 起做连通扩展，枚举「平移规范（min r = min c = 0）」的全部
    |S|=K 单连通形状——与 canonicalize 的平移规范口径一致，覆盖不重不漏。

    注意：不能要求「含原点」，平移规范形状的 min 角可能是个空位
    （如 T 形缺角），「含原点 + 坐标 ≥0」的表示会漏掉这些形状。

    target_arrays 非空时做着色前缀剪枝：前缀计数必须能逐类 ≤ 某个合法变体。
    着色条件「存在相位使分布匹配」在平移下不变（变体集对相位平移封闭），
    所以在平移规范后的坐标上做剪枝与在任意代表上等价，不会误剪。

    on_state(cells)：每产出一个状态回调一次（流式，不整体落内存）。
    visited 用「排序打包 key」去重，每个平移规范状态只展开一次子树。

    返回 (状态数, 生成中触发的扩展数)。
    """
    if K <= 0:
        return 0, 0
    ncls = step * step

    def pack(cells):
        # 每格码 +1：否则含 (0,0) 的形状首格码为 0，高位补零会让
        # 「K 格形状」的 key 撞上「K-1 格形状」的 key，被 visited 误杀
        h = 0
        for r, c in sorted(cells):
            h = (h << 16) | ((r << 8 | c) + 1)
        return h

    def counts_of(cells):
        arr = [0] * ncls
        for r, c in cells:
            arr[(r % step) * step + (c % step)] += 1
        return arr

    def feasible(counts):
        for arr in target_arrays:
            for k in range(ncls):
                if counts[k] > arr[k]:
                    break
            else:
                return True
        return False

    start = frozenset({(0, 0)})
    visited = {pack(start)}
    n_states = 0
    n_expand = 0

    def rec(cells, counts):
        nonlocal n_states, n_expand
        if len(cells) == K:
            n_states += 1
            on_state(cells)
            if progress_every and n_states % progress_every == 0:
                print(f'    ... 已产出 {n_states:,} 个状态', flush=True)
            return
        n_expand += 1
        # 候选 = cells 的全部 4 邻居（含负坐标）。
        # 每层重算：增量维护前沿在「不同生成序到达同一状态」时可能不一致，
        # 而 visited 只给第一次展开机会，一次不全就永久漏形状——正确性优先。
        cand = set()
        for r, c in cells:
            for dr, dc in DIRS4:
                q = (r + dr, c + dc)
                if q not in cells:
                    cand.add(q)
        for nb in cand:
            # cells 已 min=0，加入 nb 后只需按 nb 负分量平移即可重新规范
            r0 = nb[0] if nb[0] < 0 else 0
            c0 = nb[1] if nb[1] < 0 else 0
            merged = cells | {nb}
            if r0 or c0:
                new = frozenset((r - r0, c - c0) for r, c in merged)
            else:
                new = merged
            if target_arrays is not None:
                nc = counts_of(new)
                if not feasible(nc):
                    continue
            else:
                nc = counts_of(new)
            p = pack(new)
            if p in visited:
                continue
            visited.add(p)
            rec(new, nc)

    rec(start, counts_of(start))
    return n_states, n_expand


# ---------------------------------------------------------------------------
# 单个谜题的验证
# ---------------------------------------------------------------------------
def verify(puzzle, with_all=False, partial=False, sample_limit=5):
    m, n, step = parse_puzzle(puzzle)
    K = m * n
    table, path, complete = load_table(puzzle, partial=partial)
    if table is None:
        print(f'[{puzzle}] 找不到表数据，跳过。')
        return None

    print('=' * 64)
    print(f'[{puzzle}] K={K} step={step}  表: {path}  '
          f'{"完整" if complete else "⚠ 不完整（只做 B⊆A 单向检查）"}')

    targets, target_arrays = target_variants(m, n, step)

    # 着色剪枝：只在「验证着色条件」时开启；--with-all 的 A_all 走无剪枝枚举
    arrays_for_enum = None if with_all else target_arrays

    A_mod = set()
    A_all = set() if with_all else None
    counter = {'n': 0, 'mod': 0}

    def on_state(cells):
        counter['n'] += 1
        if with_all:
            A_all.add(canonicalize(cells))
        if class_dist(cells, step) in targets:
            counter['mod'] += 1
            A_mod.add(canonicalize(cells))

    t0 = time.time()
    n_states, n_expand = enumerate_states(K, arrays_for_enum, step, on_state)
    dt = time.time() - t0

    B = set(table.keys())
    print(f'  枚举: 含原点规范状态 {n_states:,}（展开 {n_expand:,}，{dt:.1f}s），'
          f'其中满足着色条件 {counter["mod"]:,} → A 规范形状 {len(A_mod):,}')
    print(f'  表 B 规范状态 {len(B):,}')

    result = {'puzzle': puzzle, 'A': len(A_mod), 'B': len(B),
              'complete': complete, 'states': n_states, 'secs': round(dt, 1)}

    # sanity：可达必满足着色条件 → B 必须 ⊆ A_mod
    missing = B - A_mod
    if missing:
        print(f'  ✗ sanity 失败：B 有 {len(missing):,} 个状态不在 A 中（mod 口径理解有误）')
        for h in list(missing)[:sample_limit]:
            print('     ', sorted(table_key_to_cells(h, K)))
        result['sanity_fail'] = len(missing)
        return result

    extra = A_mod - B
    if not complete:
        print('  表不完整：无法判定 A−B（差集可能只是 BFS 没跑完），仅确认 B⊆A ✓')
        result['extra'] = None
        return result

    if not extra:
        print(f'  ✓ A == B（{len(B):,}）：着色集合相同 ⟹ 可解 在该尺寸严格成立')
        result['extra'] = 0
        result['example_cells'] = []
    else:
        print(f'  ✗ A ⊃ B：存在 {len(extra):,} 个「着色相同但不可解」的形状 → 猜想为假')
        cells_list = [table_key_to_cells(h, K) for h in sorted(extra)]
        for cells in cells_list[:sample_limit]:
            print('     反例形状:')
            print(render(cells))
        result['extra'] = len(extra)
        result['example_cells'] = cells_list
        result['example_keys'] = sorted(extra)

    if with_all:
        only_all = A_all - A_mod
        unsolved_all = A_all - B
        print(f'  参考: 全部单连通形状 {len(A_all):,}；不满足着色 {len(only_all):,}；'
              f'不可解形状总数 A_all−B = {len(unsolved_all):,}')
        result['A_all'] = len(A_all)
        result['unsolved_all'] = len(unsolved_all)
    return result


def table_key_to_cells(h, count):
    cells = []
    for _ in range(count):
        val = h % 65536
        cells.append((val // 256, val % 256))
        h //= 65536
    return cells


def render(cells):
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    r0, c0 = min(rs), min(cs)
    grid = [['·'] * (max(cs) - c0 + 1) for _ in range(max(rs) - r0 + 1)]
    for r, c in cells:
        grid[r - r0][c - c0] = '#'
    return '\n'.join(' '.join(row) for row in grid)


# ---------------------------------------------------------------------------
# 反例存档（Markdown）
# ---------------------------------------------------------------------------
def dump_md(results, out_path, cmd_line, max_render=30):
    from collections import Counter
    lines = []
    w = lines.append
    w('# 「着色集合相同但不可解」反例存档')
    w('')
    w(f'- 生成命令：`{cmd_line}`')
    w(f'- 生成时间：{time.strftime("%Y-%m-%d %H:%M:%S")}')
    w(f'- 生成脚本：`experiments/math_repro/verify_coloring.py`')
    w('')
    w('## 被验证的猜想')
    w('')
    w('> 一个状态的**着色集合**（各 mod step 位置类的格子计数）若和原始矩形的着色集合相同，')
    w('> 它就是可解的。')
    w('> —— [docs/math/遊戲衍生的數學問題.md](../docs/math/遊戲衍生的數學問題.md) 第三问')
    w('')
    w('## 验证方法')
    w('')
    w('1. **A = 着色相同集**：严格枚举全部「单连通 + |S| = m×n + 着色集合 ∈ 目标变体集」')
    w('   的平移规范形状（枚举器经两套独立实现互证：K=5 → 63、K=6 → 216、K=9 → 9,910，')
    w('   与盒枚举 brute-force 完全一致）。目标变体集含**两种朝向 × step² 个相位平移**。')
    w('2. **B = 可解集**：完整反向 BFS 表（`table.pkl`，从目标经反向移动严格建出）。')
    w('3. **判定**：`A − B` 非空 ⟹ 存在「着色相同却不可解」的形状，猜想为假。')
    w('   另做 sanity 检查 `B ⊆ A`（可达必满足着色条件），不通过则先修口径再谈结论。')
    w('')
    w('**口径**：形状比较在「平移归一 + D4 八对称」规范形上进行；正向邻居只依赖形状，')
    w('故形状 key 在表中 ⟺ 该形状任意具体状态可沿距离递减重放回目标。')
    w('')
    w('## 汇总')
    w('')
    w('| 谜题 | A 着色相同形状数 | B 可达形状数 | 反例数 A−B | sanity B⊆A |')
    w('|---|---:|---:|---:|---|')
    for r in results:
        if r.get('sanity_fail'):
            verdict = f"✗ 失败（{r['sanity_fail']}）"
            extra = '—'
        else:
            verdict = '✓ 通过'
            extra = '—' if r.get('extra') is None else f"{r['extra']:,}"
        w(f"| {r['puzzle']} | {r['A']:,} | {r['B']:,} | {extra} | {verdict} |")
    w('')

    for r in results:
        cells_all = r.get('example_cells')
        if r.get('sanity_fail') or cells_all is None:
            continue
        m, n, step = parse_puzzle(r['puzzle'])
        w('---')
        w('')
        w(f"## {r['puzzle']}：{m}×{n} 矩形，步长 {step}")
        w('')
        if not cells_all:
            w(f"A == B（{r['B']:,} 个形状），**无反例**——猜想在该尺寸严格成立。")
            w('')
            continue
        # 目标原始着色（相位 0、朝向 m×n）
        tgt = Counter()
        for rr in range(m):
            for cc in range(n):
                tgt[(rr % step, cc % step)] += 1
        w(f"共 **{len(cells_all)}** 个反例。目标 {m}×{n} 的原始着色（相位 0）："
          + '、'.join(f'类{k}={v}' for k, v in sorted(tgt.items()))
          + '（各类计数的多重集）。')
        w('')
        shown = cells_all[:max_render]
        for i, cells in enumerate(shown, 1):
            rs = [rr for rr, _ in cells]
            cs = [cc for _, cc in cells]
            h = max(rs) - min(rs) + 1
            wdt = max(cs) - min(cs) + 1
            cnt = Counter(((rr % step, cc % step) for rr, cc in cells))
            multi = sorted(cnt.values(), reverse=True)
            tgt_multi = sorted(tgt.values(), reverse=True)
            w(f"### 反例 {i}/{len(cells_all)}")
            w('')
            w(f'- 外接盒 {h}×{wdt}，坐标（平移规范，min=0）：`{sorted(cells)}`')
            w(f"- 各类计数：{dict(sorted(cnt.items()))}，多重集 {multi} "
              f"{'= 目标 ' + str(tgt_multi) + ' ✓' if multi == tgt_multi else '✗ 异常'}"
              f"（存在相位平移使着色与目标完全一致）")
            w('')
            w('```text')
            w(render(cells))
            w('```')
            w('')
        if len(cells_all) > len(shown):
            w(f"（其余 {len(cells_all) - len(shown)} 个反例未逐一渲染，"
              f"canonical key 列表见下）")
            w('')
        w('<details><summary>全部反例的 canonical key（B=表内 key，A−B=反例 key）</summary>')
        w('')
        w('```')
        w(' '.join(str(k) for k in r.get('example_keys', [])))
        w('```')
        w('')
        w('</details>')
        w('')

    w('---')
    w('')
    w('## 复现')
    w('')
    w('```powershell')
    w(cmd_line)
    w('```')
    w('')
    w('数据位置：`solver/data/<puzzle>/table.pkl` 或 '
      '`E:\\program_project\\other\\doubaotest\\狀態拓撲圖分析\\<puzzle>\\table.pkl`。')
    Path(out_path).write_text('\n'.join(lines), encoding='utf-8')
    print(f'存档已写入: {out_path}')


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='验证「着色集合相同 ⟹ 可解」猜想')
    ap.add_argument('puzzles', nargs='*', help='如 3_3_2 4_4_3；缺省用 --complete 清单')
    ap.add_argument('--complete', action='store_true', help='跑全部完整表尺寸')
    ap.add_argument('--partial', action='store_true', help='允许不完整表（只做 B⊆A 检查）')
    ap.add_argument('--with-all', action='store_true',
                    help='同时枚举「全部单连通形状」A_all（K=16 会极慢）')
    ap.add_argument('--dump-md', metavar='PATH',
                    help='把反例与验证结论写成 Markdown 存档，如 experiments/math_repro/反例存档.md')
    args = ap.parse_args()

    puzzles = args.puzzles
    if not puzzles:
        if not args.complete:
            ap.error('给尺寸参数，或用 --complete')
        puzzles = COMPLETE_DEFAULT

    results = []
    for p in puzzles:
        try:
            r = verify(p, with_all=args.with_all, partial=args.partial)
            if r:
                results.append(r)
        except FileNotFoundError:
            print(f'[{p}] 找不到表，跳过')
        print()

    print('=' * 64)
    print('汇总：')
    for r in results:
        line = (f"  {r['puzzle']:<8} A={r['A']:>9,}  B={r['B']:>9,}  "
                f"枚举状态 {r['states']:>10,}  {r['secs']}s")
        if r.get('sanity_fail'):
            line += '  ✗sanity失败'
        elif r.get('extra') is None:
            line += '  (表不完整，仅B⊆A)'
        elif r['extra'] == 0:
            line += '  ✓猜想成立'
        else:
            line += f"  ✗反例 {r['extra']:,}"
        print(line)

    if args.dump_md:
        cmd = 'D:\\python\\python.exe ' + ' '.join(sys.argv)
        dump_md(results, args.dump_md, cmd)


if __name__ == '__main__':
    main()
