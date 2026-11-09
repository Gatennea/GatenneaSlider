# -*- coding: utf-8 -*-
"""D4：DFS 整形邊並行的 ABAB 實測（**不保證賺**，見 H4）。

⚠️ 現況先講清楚（2026-11-10 親自 grep 呼叫鏈）：判據文檔 D4 寫的
「已寫好的 DFS 整形邊並行基礎設施已就位但沒接」**過時了** ——
`solver/ml/fill_macro.py::solve_multi_search` 裡的 `_couples()` 早就呼叫
`_run_couples_parallel(..., first_only=False)`（`:2531`），只差
`_PARALLEL_ENABLED` 預設關（`GATENNEA_PARALLEL=1` 才開）。
所以 D4 剩下的不是「接線」，是**開／關到底賺不賺**。本腳本不改任何
生產碼。

做法：每個 case 各起一個**獨立子進程**（環境變數在 import 時就讀，
同進程切換會污染進程池冷啟動），A=關、B=開，按 ABAB 交替跑兩輪，
降低機器負載漂移。指標只比**解出數與牆鐘**（求解內部隨機，解長會漂移，
見 `.workbuddy/memory/MEMORY.md` 的量測紀律）。

**開跑前寫死的止損判據**：並行版中位牆鐘 ≤ 串列版 × 0.8 **且**
解出數不少於串列版，才算「賺、可以考慮開」；否則**維持預設關**，
如實報加速比，不為了讓它好看去挑局面或調預算。

用法：D:/python/python.exe -u experiments/script_bench_dfs_parallel.py \
          --cases 4 --time-budget 12 --node-budget 40
輸出只到 stdout，不落結果檔（避免 doclink 裸引用）。
"""
import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MISSING = -1


def worker_main(argv):
    """子進程：設好開關 → import → 跑一局 → 輸出一行 JSON。"""
    mode = argv['mode']
    os.environ['GATENNEA_PARALLEL'] = '1' if mode == 'on' else '0'
    import solver.ml.fill_macro as fm
    from game import SliderMatrix  # noqa: E402

    enabled = fm._PARALLEL_ENABLED
    assert enabled == (mode == 'on'), '開關沒生效：%s / %s' % (mode, enabled)

    counter = {'calls': 0, 'ran': 0}
    orig = fm._run_couples_parallel

    def spy(*a, **k):
        got, ran = orig(*a, **k)
        counter['calls'] += 1
        if ran:
            counter['ran'] += 1
        return got, ran

    fm._run_couples_parallel = spy

    random.seed(argv['seed'])
    g = SliderMatrix(argv['m'], argv['n'])
    g.shuffle(argv['m'] * argv['n'] * 10, argv['step'])
    coords = frozenset(tuple(b.location) for b in g.blocks)

    t0 = time.perf_counter()
    try:
        acts, stats = fm.solve_multi_search(
            coords, argv['m'], argv['n'], argv['step'],
            node_budget=argv['node_budget'],
            time_budget=argv['time_budget'])
        dt = time.perf_counter() - t0
    except Exception as e:
        print(json.dumps({'mode': mode, 'error': repr(e),
                         'dt': time.perf_counter() - t0}))
        return 0

    solved = False
    if acts is not None and not stats.get('partial'):
        try:
            g2 = fm.build_game(coords, argv['m'], argv['n'])
            solved = (fm._replay_apply(g2, acts, argv['m'], argv['n'],
                                       argv['step'])
                      and g2.is_solved())
        except Exception:
            solved = False
    print(json.dumps({
        'mode': mode, 'seed': argv['seed'], 'dt': round(dt, 3),
        'solved': bool(solved), 'partial': bool(stats.get('partial')),
        'steps': len(acts) if acts else 0,
        'nodes': stats.get('nodes', MISSING),
        'enabled': enabled,
        'parallel_calls': counter['calls'],
        'parallel_ran': counter['ran'],
    }))
    return 0


def run_case(case, mode):
    args = ['--worker', '--mode', mode,
            '--seed', str(case['seed']), '--m', str(case['m']),
            '--n', str(case['n']), '--step', str(case['step']),
            '--time-budget', str(case['time_budget']),
            '--node-budget', str(case['node_budget'])]
    env = os.environ.copy()
    env['GATENNEA_PARALLEL'] = '1' if mode == 'on' else '0'
    env['PYTHONHASHSEED'] = '0'
    t0 = time.perf_counter()
    try:
        p = subprocess.run([sys.executable, '-u', __file__] + args,
                           cwd=ROOT, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=180)
        dt = time.perf_counter() - t0
        lines = [ln for ln in p.stdout.decode('utf-8', 'replace')
                 .splitlines() if ln.startswith('{')]
        if not lines:
            return {'mode': mode, 'error': 'no-json', 'dt': dt,
                    'stderr': p.stderr.decode('utf-8', 'replace')[-300:]}
        rec = json.loads(lines[-1])
        rec['wall'] = dt
        return rec
    except subprocess.TimeoutExpired:
        return {'mode': mode, 'error': 'timeout', 'wall': 180.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', type=int, default=4)
    ap.add_argument('--time-budget', type=float, default=12)
    ap.add_argument('--node-budget', type=int, default=40)
    ap.add_argument('--rounds', type=int, default=2)
    args = ap.parse_args()

    cases = []
    for i in range(args.cases):
        cases.append({'seed': 1000 + i, 'm': 4, 'n': 4, 'step': 2,
                      'time_budget': args.time_budget,
                      'node_budget': args.node_budget})
    print('D4：DFS 整形邊並行 ABAB（%d 局 × %d 輪 × 2 組，'
          'time_budget=%gs / node_budget=%d）'
          % (len(cases), args.rounds, args.time_budget, args.node_budget))
    print('⚠️ H4 已聲明「不保證賺」；止損判據開跑前寫死：'
          '中位牆鐘 ≤ 串列 × 0.8 且解出數不少，否則維持關。')

    rows = {'off': [], 'on': []}
    for rnd in range(args.rounds):
        # ABAB：每輪交替順序，抵銷機器負載漂移
        order = ('off', 'on', 'on', 'off') if rnd % 2 == 0 \
            else ('on', 'off', 'off', 'on')
        for ci, case in enumerate(cases):
            mode = order[ci % 4]
            rec = run_case(case, mode)
            rows[mode].append(rec)
            print('  輪%d 局%d %-3s %s' % (
                rnd + 1, ci, mode,
                ('%.2fs 解出=%s 節點=%s 並行批次=%d/%d'
                 % (rec.get('dt', rec.get('wall', -1)),
                    rec.get('solved'), rec.get('nodes'),
                    rec.get('parallel_ran', 0),
                    rec.get('parallel_calls', 0)))
                if 'error' not in rec else 'ERROR %s' % rec['error']))

    def agg(mode):
        good = [r for r in rows[mode] if 'error' not in r]
        errs = [r for r in rows[mode] if 'error' in r]
        dts = [r['dt'] for r in good]
        return {
            'ok': len(good), 'errors': len(errs),
            'solved': sum(1 for r in good if r.get('solved')),
            'median': statistics.median(dts) if dts else None,
            'ran_batches': sum(r.get('parallel_ran', 0) for r in good),
            'calls': sum(r.get('parallel_calls', 0) for r in good),
        }

    a, b = agg('off'), agg('on')
    print('\n彙總：串列(關) %s' % a)
    print('      並行(開) %s' % b)
    if b['ran_batches'] == 0:
        print('⚠️ 並行批次一次都沒跑起來（tasks<2 或池不可用）：'
              '本輪開關等於沒生效，結論只能記「無法量」，別說「並行沒用」。')
        return 0
    if a['median'] is None or b['median'] is None:
        print('有效樣本不足，不做判定。')
        return 0
    ratio = b['median'] / a['median']
    win = ratio <= 0.8 and b['solved'] >= a['solved']
    print('中位牆鐘 %.2fs → %.2fs（%.3f×，1/%.3f）；解出 %d → %d'
          % (a['median'], b['median'], ratio,
             ratio if ratio else 0, a['solved'], b['solved']))
    if win:
        print('結論：**賺**。達到「≤0.8× 且解出數不少」門檻，'
              '才值得再談要不要改預設開關（產品決策，本輪不改）。')
    else:
        print('結論：**維持預設關**。沒達到開跑前寫死的門檻，'
              'spawn + 序列化吃掉收益（H4 早有輪詢層負收益實測），'
              '別為了好看去挑局面或調預算。')
    return 0


if __name__ == '__main__':
    # worker 模式：第一個參數是 --worker，其餘交給 worker_main
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        kv = {}
        rest = sys.argv[2:]
        for i in range(0, len(rest), 2):
            kv[rest[i].lstrip('-').replace('-', '_')] = rest[i + 1]
        for k in ('seed', 'm', 'n', 'step', 'node_budget'):
            kv[k] = int(kv[k])
        kv['time_budget'] = float(kv['time_budget'])
        sys.exit(worker_main(kv))
    sys.exit(main())
