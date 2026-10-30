# -*- coding: utf-8 -*-
"""填洞去留消融数据汇总：读 experiments/results/fillin/*.jsonl 出配对表。

用法：D:/python/python.exe experiments/script_fillin_report.py
"""

import glob
import json
import os
import statistics
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, 'experiments', 'results', 'fillin')


def load():
    rows = []
    for f in sorted(glob.glob(os.path.join(RESULTS, '*.jsonl'))):
        for line in open(f, encoding='utf-8'):
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def main():
    rows = load()
    if not rows:
        print('无数据')
        return
    groups = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for r in rows:
        key = (r['level'], r['m'], r['n'], r['step'])
        groups[key][r['seed']][r.get('rep', 0)][r['flag']] = r

    print('%-6s %-10s %5s %5s %8s %8s %8s %8s %s' % (
        '层', '尺寸', '对数', '轮数', 'on中位', 'off中位', 'on/off', '步数差', '判定'))
    for key in sorted(groups):
        level, m, n, step = key
        seeds = groups[key]
        # 配对按 rep：要求同一 rep 内 on/off 都在（同轮配对才同机器状态）
        pairs = []  # (rep, seed, on, off)
        for seed, reps in sorted(seeds.items()):
            for rep, d in sorted(reps.items()):
                if 'on' in d and 'off' in d:
                    pairs.append((rep, seed, d['on'], d['off']))
        if not pairs:
            continue
        n_reps = len(set(p[0] for p in pairs))
        # on/off 各自跨 rep 取中位（压制单轮噪声）
        on_dts = [p[2]['dt'] for p in pairs]
        off_dts = [p[3]['dt'] for p in pairs]
        on_med = statistics.median(on_dts)
        off_med = statistics.median(off_dts)
        ratio = (on_med / off_med) if off_med > 0 else float('inf')
        outs = defaultdict(int)
        for _, _, on, off in pairs:
            outs['%s/%s' % (on['outcome'][:4], off['outcome'][:4])] += 1
        # 步数差（仅双方 solved 且有动作数的对，按 rep 配对取中位）
        step_diffs = []
        for _, _, on, off in pairs:
            if on.get('n_actions') and off.get('n_actions'):
                step_diffs.append(on['n_actions'] - off['n_actions'])
        sd = ('%+.0f' % statistics.median(step_diffs)) if step_diffs else '-'
        # 判定（双方均 solved 的配对做快慢判断）
        comparable = [(on['dt'], off['dt']) for _, _, on, off in pairs
                      if on['outcome'] == 'solved'
                      and off['outcome'] == 'solved']
        # 同层归因子集：on/off 解法层相同（不同层的对，差异来自补缺宏
        # 30s 墙钟预算的调度运气——同层同解长都曾差 20 倍——不可归因于
        # 填洞宏）。L2b 的关键口径：只有同层对能回答「删填洞亏不亏」。
        same_layer = [(on['dt'], off['dt'], on['n_actions'], off['n_actions'])
                      for _, _, on, off in pairs
                      if on['outcome'] == 'solved'
                      and off['outcome'] == 'solved'
                      and (on.get('labels') or [None])[0]
                      == (off.get('labels') or [None])[0]]
        if comparable:
            off_wins = sum(1 for a, b in comparable if b < a * 0.95)
            on_wins = sum(1 for a, b in comparable if a < b * 0.95)
            ties = len(comparable) - off_wins - on_wins
            verdict = 'off快%d/平%d/on快%d' % (off_wins, ties, on_wins)
        else:
            verdict = '无可比对(均超时?)'
        sl_verdict = ''
        if same_layer:
            sl_off = sum(1 for a, b, _, _ in same_layer if b < a * 0.95)
            sl_on = sum(1 for a, b, _, _ in same_layer if a < b * 0.95)
            sl_ties = len(same_layer) - sl_off - sl_on
            sl_verdict = '同层%d对:off快%d/平%d/on快%d' % (
                len(same_layer), sl_off, sl_ties, sl_on)
        print('%-6s %-10s %5d %5d %8.1f %8.1f %8.2f %8s %s %s' % (
            level, '%dx%d s%d' % (m, n, step), len(pairs), n_reps,
            on_med, off_med, ratio, sd, verdict, sl_verdict))
    print()
    print('口径：on=混合内含填洞宏（现状）/ off=已删（hybrid_use_fill=False）；')
    print('     on/off >1 表示 off 快；步数差 = on−off 的中位（负=off 解更长）；')
    print('     多轮数据按 rep 配对、跨 rep 取中位（补缺宏 30s 墙钟预算有调度')
    print('     非确定性——同盘面同层同解长耗时仍可差 20 倍，单轮数据不可信）。')
    print('     「同层N对」= on/off 解法层相同的配对子集——只有它能归因于')
    print('     填洞宏；异层对的差异主要来自补缺宏预算运气，看全部对会误判。')


if __name__ == '__main__':
    main()
