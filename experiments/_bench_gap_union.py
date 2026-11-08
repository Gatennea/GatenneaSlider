# -*- coding: utf-8 -*-
"""convoy 連通判定三級判定（_union_connected）的 ABAB 配對驗收。

背景（2026-11-07 硬局 cProfile）：補缺宏硬局 30s 預算裡 ~95% 燒在
`solve_multi_search → _convoy_fill → _legal_steps → _connected`（`_connected`
單項 36%、28 萬次 DFS）。新實現把「無接觸快拒 / rest 連通記憶化 / 星形橋接」
三級判定替代滿 DFS，**等價性已雙算 241 萬次 0 不一致**（22 案回歸語料）。

方法（消方差三件套）：
  · PYTHONHASHSEED=0（集合迭代序決定 dfs 探索序，否則 0.7s↔30s 級方差）
  · random.seed(20261107)（每局固定）
  · 舊版 = `git show HEAD:solver/ml/fill_macro.py`（只讀提取），逐輪交替運行，
    finally 必還原新版（結束後再驗一次文件含 _union_connected）。

⚠️ 本腳本會**臨時覆寫 solver/ml/fill_macro.py**（每輪換版），結束 finally
還原；中斷後可從打印的備份路徑（TEMP/fill_macro_union_bak.py）手工恢復。

跑法：python experiments/_bench_gap_union.py [--rounds 3]
結果落盤：experiments/_bench_gap_union_out.txt
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PROD = os.path.join(ROOT, 'solver', 'ml', 'fill_macro.py')
BACKUP = os.path.join(os.environ.get('TEMP', '.'), 'fill_macro_union_bak.py')
OUT = os.path.join(ROOT, 'experiments', '_bench_gap_union_out.txt')

CASES = ['beginner_archive/5.1.json', 'archives/失败01.json',
         'archives/失败02.json', 'archives/失败03.json']

# 子進程驅動（用 .replace 注入路徑/語料，不走 % 格式化——模板裡 % 太多）
BENCH_TMPL = r'''
import json, os, random, sys, time
ROOT = '__ROOT__'
CASES = __CASES__
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from solver.ml.fill_macro import build_game
from solver.ml.gap_solver import solve_gap_macro
total = 0.0
detail = []
for rel in CASES:
    random.seed(20261107)
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        doc = json.load(f)
    s0 = doc['history']['snapshots'][0]
    b0 = s0['bounds']
    coords = frozenset((b0['min_row'] + i, b0['min_col'] + j)
                       for i, row in enumerate(s0['matrix'])
                       for j, v in enumerate(row) if v)
    pz = doc['puzzle']
    t0 = time.time()
    res = solve_gap_macro(build_game(coords, pz['m'], pz['n']), pz['step'])
    dt = time.time() - t0
    total += dt
    kind = ('tuple %d' % len(res[0]) if isinstance(res, tuple)
            else (res.get('type') if isinstance(res, dict) else repr(res)))
    detail.append('%s=%.1fs/%s' % (rel.split('/')[-1], dt, kind))
    print('  %s  %6.1fs  %s' % (rel, dt, kind), flush=True)
print('TOTAL %.1f %s' % (total, ' | '.join(detail)))
'''
BENCH = (BENCH_TMPL.replace('__ROOT__', ROOT.replace('\\', '/'))
         .replace('__CASES__', repr(CASES)))


def write_version(which):
    if which == 'old':
        data = subprocess.check_output(
            ['git', 'show', 'HEAD:solver/ml/fill_macro.py'], cwd=ROOT)
        with open(PROD, 'wb') as f:
            f.write(data)
    else:
        shutil.copyfile(BACKUP, PROD)


def run_case(which):
    env = dict(os.environ)
    env['PYTHONHASHSEED'] = '0'
    r = subprocess.run([sys.executable, '-u', '-c', BENCH],
                       capture_output=True, text=True, env=env,
                       cwd=ROOT, encoding='utf-8', errors='replace')
    total_line = [l for l in r.stdout.splitlines() if l.startswith('TOTAL')]
    if r.returncode != 0 or not total_line:
        raise SystemExit('run %s failed rc=%s\n%s\n%s'
                         % (which, r.returncode, r.stdout[-2000:],
                            r.stderr[-2000:]))
    return total_line[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=3)
    args = ap.parse_args()
    shutil.copyfile(PROD, BACKUP)          # 新版備份（中斷恢復點）
    print('新版備份:', BACKUP, flush=True)
    lines = []
    results = {'old': [], 'new': []}
    try:
        for r in range(args.rounds):
            order = ('old', 'new') if r % 2 == 0 else ('new', 'old')
            got = {}
            for which in order:
                write_version(which)
                got[which] = run_case(which)
                print('[r%d %s] %s' % (r, which, got[which]), flush=True)
            results['old'].append(got['old'])
            results['new'].append(got['new'])
            lines.append('r%d order=%s\n  old: %s\n  new: %s'
                         % (r, order[0], got['old'], got['new']))
    finally:
        shutil.copyfile(BACKUP, PROD)      # 必還原新版
        print('已還原新版 →', PROD, flush=True)

    def totals(key):
        return [float(l.split('TOTAL ')[1].split()[0])
                for l in results[key]]
    to, tn = totals('old'), totals('new')
    wins = sum(1 for a, b in zip(to, tn) if b < a)
    mo, mn = sorted(to)[len(to) // 2], sorted(tn)[len(tn) // 2]
    summary = ('[ABAB %d 對] 舊中位 %.1fs / 新中位 %.1fs → %.3fx，'
               '新勝 %d/%d 輪' % (len(to), mo, mn, mo / mn if mn else 0,
                                  wins, len(to)))
    print(summary, flush=True)
    lines.append(summary)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('results ->', OUT)
    with open(PROD, encoding='utf-8') as f:
        if '_union_connected' not in f.read():
            raise SystemExit('⚠️ 還原失敗：生產文件缺 _union_connected')


if __name__ == '__main__':
    main()
