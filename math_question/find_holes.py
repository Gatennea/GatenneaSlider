# -*- coding: utf-8 -*-
"""
建表漏洞检测实验

思路：
    1. 用游戏自身的 SliderMatrix.shuffle() 从复原状态随机游走，生成状态。
       shuffle 只执行「合法移动」（无碰撞 + 单一连通），因此产生的状态必然可达。
    2. 查表：若表中没有该状态 → 建表算法漏掉了可达状态，即存在漏洞。
    3. 漏洞状态记录并写入磁盘；命中状态仅计数后丢弃。
    生成与查表这两步在每个工作进程中串行执行，进程之间并行。

运行：
    D:\\python\\python.exe -m solver.find_holes [m n step] [--trials N] [--workers W]
    不带 m n step 时，自动遍历 solver/data 下所有已建表的等级。

参数：
    --trials N      每个等级检测的状态数（默认 200000）
    --workers W     并行进程数（默认 CPU 核数，上限 16）
    --batch B       每个并行任务的状态数（默认 500）
    --attempts A    打乱次数上限，实际取 [1, A] 内随机（默认 30）
    --seed S        随机种子基准（默认 20260910）
"""

import os
import sys
import math
import time
import random
import pickle
import argparse
import multiprocessing

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from solver import table_core as tc
except ImportError:
    import table_core as tc


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
HOLES_DIR = os.path.join(DATA_DIR, 'holes')

DEFAULT_TRIALS = 200000
DEFAULT_BATCH = 500
DEFAULT_ATTEMPTS = 30
DEFAULT_SEED = 20260910
DEFAULT_WORKERS = min(16, multiprocessing.cpu_count())


# ---------------------------------------------------------------------------
# 工作进程
# ---------------------------------------------------------------------------
_W = {}


def _init_worker(table_path, m, n, step):
    """每个工作进程加载一次表，缓存到进程全局。"""
    with open(table_path, 'rb') as f:
        _W['table'] = pickle.load(f)
    _W['m'] = m
    _W['n'] = n
    _W['step'] = step
    _W['total'] = m * n


def _worker_batch(args):
    """生成一批状态并查表，返回 (命中数, [(hash, 方块数), ...], 本批状态 hash 集合)。"""
    seed, trials, max_attempts = args
    from game import SliderMatrix

    rng = random.Random(seed)
    table = _W['table']
    m, n, step = _W['m'], _W['n'], _W['step']

    hits = 0
    misses = []
    seen = set()
    freq = {}
    for _ in range(trials):
        game = SliderMatrix(m, n)
        game.shuffle(attempts=rng.randint(1, max_attempts), step=step)
        coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        h = tc.canonicalize(coords)
        seen.add(h)
        if h in table:
            hits += 1
            d = table[h]
            freq[d] = freq.get(d, 0) + 1
        else:
            misses.append((h, len(coords)))
    return hits, misses, seen, freq


# ---------------------------------------------------------------------------
# walk 模式：几何偏置随机游走（Metropolis），不依赖数据库
# ---------------------------------------------------------------------------
def _energy(coords, m=4, n=4):
    """散度 = 1 - compute_score（与 game.py shuffle 的 _scatter 完全一致）。

    用项目标准启发函数 compute_score 的反值作为能量：
    0 = 复原态，越大越散。只用状态几何信息，不需要查表。
    平移/旋转/镜像不变。
    """
    pts = list(coords)
    if not pts:
        return 0.0
    rs = [r for r, _ in pts]
    cs = [c for _, c in pts]
    H = max(rs) - min(rs) + 1
    W = max(cs) - min(cs) + 1
    K = m * n
    fill_rate = K / (H * W) if H * W > 0 else 0.0
    min_dim, max_dim = min(m, n), max(m, n)
    target_ratio = max_dim / min_dim if min_dim > 0 else 1.0
    min_hw, max_hw = min(H, W), max(H, W)
    current_ratio = max_hw / min_hw if min_hw > 0 else 1.0
    max_ratio = max(current_ratio, target_ratio)
    aspect_error = abs(current_ratio - target_ratio) / max_ratio if max_ratio > 0 else 0.0
    score = 0.5 * fill_rate + 0.5 * (1.0 - aspect_error)
    return 1.0 - score


def _worker_walk(args):
    """几何偏置游走采样一批「不同」状态并查表。

    机制：
        - 沿正向移动图游走（只走合法移动，保证可达性）
        - Metropolis 接受准则：向高能（更散）移动必接受，向低能移动以
          exp(-beta*dE) 概率接受 → 驻留质量偏向深层
        - 去重：只有走到「本链未见过」的状态才算一个样本
        - 停滞保护：连续 stall_limit 步走不出新状态则从目标态重启
    """
    seed, trials, beta, burn_in, stall_limit = args
    table = _W['table']
    m, n, step = _W['m'], _W['n'], _W['step']
    total = m * n
    rng = random.Random(seed)

    goal = tc.goal_state(m, n)

    def fresh_chain():
        """从目标态出发，burn-in 若干步后返回 (coords, hash, energy, visited)。"""
        cur = goal
        h = tc.canonicalize(cur)
        e = _energy(cur, m, n)
        visited = {h}
        for _ in range(burn_in):
            nbrs = tc.forward_neighbors(cur, step, total)
            if not nbrs:
                break
            nh = rng.choice(list(nbrs))
            ne = _energy(tc.int_to_coords(nh, total), m, n)
            if ne < e and rng.random() >= math.exp(beta * (ne - e)):
                continue  # 拒绝下降
            cur = frozenset(tc.int_to_coords(nh, total))
            h, e = nh, ne
            visited.add(h)
        return cur, h, e, visited

    cur, cur_h, cur_e, visited = fresh_chain()
    stalls = 0
    hits = 0
    misses = []
    seen = set()
    freq = {}
    collected = 0

    while collected < trials:
        nbrs = tc.forward_neighbors(cur, step, total)
        if not nbrs:
            cur, cur_h, cur_e, visited = fresh_chain()
            stalls = 0
            continue
        nh = rng.choice(list(nbrs))
        ncoords = frozenset(tc.int_to_coords(nh, total))
        ne = _energy(ncoords, m, n)
        # Metropolis 接受
        if ne < cur_e and rng.random() >= math.exp(beta * (ne - cur_e)):
            pass  # 拒绝：留在原地
        else:
            cur, cur_h, cur_e = ncoords, nh, ne

        if cur_h in visited:
            stalls += 1
            if stalls >= stall_limit:
                cur, cur_h, cur_e, visited = fresh_chain()
                stalls = 0
            continue

        # 新状态：查表计一个样本
        stalls = 0
        visited.add(cur_h)
        seen.add(cur_h)
        collected += 1
        if cur_h in table:
            hits += 1
            d = table[cur_h]
            freq[d] = freq.get(d, 0) + 1
        else:
            misses.append((cur_h, total))

    return hits, misses, seen, freq


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def _discover_tables():
    """扫描 data 目录，返回所有已建表（存在 table.pkl）的 (m, n, step)。"""
    found = []
    if not os.path.isdir(DATA_DIR):
        return found
    for name in sorted(os.listdir(DATA_DIR)):
        parts = name.split('_')
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            continue
        if os.path.exists(os.path.join(DATA_DIR, name, 'table.pkl')):
            found.append(tuple(int(p) for p in parts))
    return found


def _render(coords):
    """坐标集合渲染为 '#' / '.' 文本网格。"""
    coords = set(coords)
    if not coords:
        return '(空)'
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    min_r, max_r = min(rs), max(rs)
    min_c, max_c = min(cs), max(cs)
    return '\n'.join(
        ''.join('#' if (r, c) in coords else '.' for c in range(min_c, max_c + 1))
        for r in range(min_r, max_r + 1)
    )


# ---------------------------------------------------------------------------
# 单个等级的检测
# ---------------------------------------------------------------------------
def run_one(m, n, step, trials, workers, batch, max_attempts, seed,
            mode='shuffle', beta=0.15, chain_len=500):
    table_path = os.path.join(DATA_DIR, f'{m}_{n}_{step}', 'table.pkl')
    print('=' * 62)
    print(f'等级 {m}×{n} step={step}   模式={mode}   检测 {trials:,} 个状态   '
          f'进程数={workers}'
          + (f'  beta={beta}' if mode == 'walk' else f'  打乱次数上限={max_attempts}'))
    print('=' * 62, flush=True)

    if mode == 'walk':
        n_batches = max(1, (trials + chain_len - 1) // chain_len)
        tasks = [(seed + i * 7919, min(chain_len, trials - i * chain_len),
                  beta, max_attempts * 2, chain_len * 20)
                 for i in range(n_batches)]
        worker_fn = _worker_walk
    else:
        n_batches = max(1, (trials + batch - 1) // batch)
        tasks = [(seed + i * 7919, batch, max_attempts) for i in range(n_batches)]
        worker_fn = _worker_batch

    total_gen = 0
    hits = 0
    miss_map = {}          # hash -> 方块数
    distinct = set()       # 采样到的不同状态
    samp_freq = {}         # 距离 -> 采样次数
    done = 0
    t0 = time.time()

    pool = multiprocessing.Pool(
        processes=workers,
        initializer=_init_worker,
        initargs=(table_path, m, n, step),
    )
    try:
        for hits_i, misses, seen, freq in pool.imap_unordered(worker_fn, tasks):
            total_gen += hits_i + len(misses)
            hits += hits_i
            for h, cnt in misses:
                miss_map.setdefault(h, cnt)
            distinct |= seen
            for d, c in freq.items():
                samp_freq[d] = samp_freq.get(d, 0) + c
            done += 1
            if done % max(1, n_batches // 20) == 0 or done == n_batches:
                el = time.time() - t0
                print(f'  [{total_gen:>8,}/{trials:,}]  命中={hits:,}  '
                      f'不同状态={len(distinct):,}  漏洞={len(miss_map):,}  {el:.1f}s  '
                      f'({total_gen / el if el else 0:,.0f}/s)', flush=True)
    except KeyboardInterrupt:
        pool.terminate()
        pool.join()
        print('\n[中断] 已终止', flush=True)
        return None
    finally:
        pool.close()
        pool.join()

    elapsed = time.time() - t0

    # 采样覆盖率诊断：确认负结果有意义
    with open(table_path, 'rb') as f:
        table = pickle.load(f)
    table_size = len(table)
    coverage = len(distinct) / table_size if table_size else 0.0
    dist_hist = {}
    for h in distinct:
        d = table.get(h)
        if d is not None:
            dist_hist[d] = dist_hist.get(d, 0) + 1

    print(f'\n  检测完成: 共 {total_gen:,} 个状态，用时 {elapsed:.1f}s')
    print(f'  命中(在表中): {hits:,}   漏洞(不在表中): {len(miss_map):,}')
    print(f'  采样覆盖: 不同状态 {len(distinct):,} / 表内 {table_size:,} '
          f'= {coverage * 100:.2f}%')
    if dist_hist:
        ds = sorted(dist_hist)
        print(f'  采样距离范围: d={ds[0]} ~ d={ds[-1]}'
              f'（表最大距离 d={max(table.values())}）')
        print(f'  采样距离分布: ' + ' '.join(f'{d}:{dist_hist[d]:,}' for d in ds))

    # 采样频率分布 vs 数据库分布：检验打乱游走是否为「均匀采样」
    db_freq = {}
    for d in table.values():
        db_freq[d] = db_freq.get(d, 0) + 1
    print(f'\n  采样频率 vs 数据库分布（若两者成正比，则打乱≈全表均匀采样）')
    print(f'  {"d":>4}{"库内状态":>12}{"库内占比":>10}{"采样次数":>12}'
          f'{"采样占比":>10}{"采样/库内":>11}')
    for d in sorted(db_freq):
        db_p = db_freq[d] / table_size
        sp = samp_freq.get(d, 0) / total_gen if total_gen else 0.0
        ratio = (sp / db_p) if db_p else 0.0
        print(f'  {d:>4}{db_freq[d]:>12,}{db_p * 100:>9.2f}%'
              f'{samp_freq.get(d, 0):>12,}{sp * 100:>9.2f}%{ratio:>11.2f}x')

    if miss_map:
        os.makedirs(HOLES_DIR, exist_ok=True)
        out_path = os.path.join(HOLES_DIR, f'{m}_{n}_{step}_holes.txt')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write('═══ 建表漏洞检测报告 ═══\n')
            f.write(f'等级: {m}×{n} step={step}\n')
            f.write(f'检测状态数: {total_gen:,}\n')
            f.write(f'命中(在表中): {hits:,}\n')
            f.write(f'漏洞(不在表中): {len(miss_map):,}\n')
            f.write(f'用时: {elapsed:.1f}s\n\n')
            f.write('说明: shuffle 从复原状态出发只执行合法移动，产生的状态必然可达；\n')
            f.write('      完整建表应包含全部可达状态，故不在表中即为建表算法漏洞。\n\n')
            for i, (h, cnt) in enumerate(sorted(miss_map.items()), 1):
                coords = tc.int_to_coords(h, m * n)
                f.write(f'── 漏洞 #{i} ──\n')
                f.write(f'hash: {h}\n')
                f.write(f'方块数: {cnt}\n')
                f.write(_render(coords) + '\n\n')
        print(f'  漏洞已写入: {out_path}')
    else:
        print('  未发现漏洞')

    print(flush=True)
    return {
        'm': m, 'n': n, 'step': step,
        'total': total_gen, 'hits': hits, 'holes': len(miss_map),
        'distinct': len(distinct), 'coverage': coverage,
        'elapsed': elapsed,
    }


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='建表漏洞检测实验')
    ap.add_argument('mnstep', nargs='*', type=int,
                    help='可选: m n step，不填则遍历所有已建表等级')
    ap.add_argument('--trials', type=int, default=DEFAULT_TRIALS)
    ap.add_argument('--workers', type=int, default=DEFAULT_WORKERS)
    ap.add_argument('--batch', type=int, default=DEFAULT_BATCH)
    ap.add_argument('--attempts', type=int, default=DEFAULT_ATTEMPTS)
    ap.add_argument('--seed', type=int, default=DEFAULT_SEED)
    ap.add_argument('--mode', choices=('shuffle', 'walk'), default='shuffle',
                    help='shuffle=游戏打乱函数采样；walk=几何偏置Metropolis游走采样')
    ap.add_argument('--beta', type=float, default=0.15,
                    help='walk 模式能量偏置强度（越大越偏向深层）')
    ap.add_argument('--chain-len', type=int, default=500,
                    help='walk 模式每条马尔可夫链采集的不同状态数')
    args = ap.parse_args()

    if len(args.mnstep) == 3:
        targets = [tuple(args.mnstep)]
    elif len(args.mnstep) == 0:
        targets = _discover_tables()
        if not targets:
            print('错误: solver/data 下没有找到已建表的等级。')
            sys.exit(1)
    else:
        print('错误: 参数需为 0 个或 3 个 (m n step)')
        sys.exit(1)

    results = []
    for m, n, step in targets:
        r = run_one(m, n, step, args.trials, args.workers, args.batch,
                    args.attempts, args.seed, mode=args.mode, beta=args.beta,
                    chain_len=args.chain_len)
        if r:
            results.append(r)

    print('=' * 62)
    print('汇总')
    print('=' * 62)
    print(f'{"等级":<12}{"检测数":>10}{"不同状态":>10}{"覆盖率":>9}{"漏洞":>8}{"用时(s)":>10}')
    for r in results:
        print(f'{r["m"]}×{r["n"]} s{r["step"]:<8}{r["total"]:>10,}'
              f'{r["distinct"]:>10,}{r["coverage"] * 100:>8.2f}%'
              f'{r["holes"]:>8}{r["elapsed"]:>10.1f}')
    total_holes = sum(r['holes'] for r in results)
    print(f'\n合计漏洞: {total_holes}')
    if total_holes:
        print(f'详情见 {HOLES_DIR}')


if __name__ == '__main__':
    main()
