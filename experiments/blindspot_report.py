# -*- coding: utf-8 -*-
"""盲区覆盖 + 解长质量汇总：读 results/blindspot/rounds.jsonl 出报告数据。

用法：D:/python/python.exe experiments/blindspot_report.py
产出（stdout，人读汇总；正式结论由 AI 整理成 results/blindspot/汇总.md 入库）。
"""

import glob
import json
import os
import statistics
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUNDS = os.path.join(ROOT, 'experiments', 'results', 'blindspot', 'rounds.jsonl')
SAVE_DIR = os.path.join(ROOT, 'save', 'blindspot')

# 数学复现锁定值（docs/math/ 权威）
GODS_NUMBER = {(4, 4, 2): 17, (4, 4, 3): 29}


def load():
    if not os.path.exists(ROUNDS):
        return []
    rows = []
    for line in open(ROUNDS, encoding='utf-8'):
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def main():
    rows = load()
    if not rows:
        print('无数据（先跑 blindspot_scan.py）')
        return
    by_size = defaultdict(list)
    for r in rows:
        by_size[(r['m'], r['n'], r['step'], r.get('src'))].append(r)

    print('=' * 72)
    print('盲区覆盖 + 解长质量汇总（共 %d 局）' % len(rows))
    print('=' * 72)
    for key in sorted(by_size, key=str):
        m, n, step, src = key
        rs = by_size[key]
        outs = Counter(r['outcome'] for r in rs)
        solved = [r for r in rs if r['outcome'] == 'solved']
        failed = [r for r in rs if r['outcome'] in ('partial', 'fail')]
        print()
        print('【%dx%d 等级%d｜%s】%d 局' % (m, n, step, src, len(rs)))
        print('  结局：%s' % '，'.join('%s×%d' % (k, v)
                                     for k, v in outs.most_common()))
        if solved:
            dts = [r['dt'] for r in solved]
            acts = [r['n_actions'] for r in solved if r.get('n_actions')]
            layers = Counter(r.get('solve_layer') or '?' for r in solved)
            print('  解出 %d 局：耗时中位 %.1fs（最短 %.1f / 最长 %.1f）'
                  % (len(solved), statistics.median(dts), min(dts), max(dts)))
            print('  解长：中位 %.0f 步（最短 %d / 最长 %d）'
                  % (statistics.median(acts), min(acts), max(acts)))
            print('  分层：%s' % '，'.join('%s×%d' % (k, v)
                                        for k, v in layers.most_common()))
            god = GODS_NUMBER.get((m, n, step))
            if god and acts:
                med = statistics.median(acts)
                if all((r.get('solve_layer') or '').find('查表') >= 0
                       for r in solved):
                    print('  ★ vs 上帝之数 %d（最坏最短）：本批解长中位 %.0f 步'
                          '——全部查表解出（=各局最短），差距 0；注意上帝之数'
                          '是最坏情况上界，不是每局最短' % (god, med))
                else:
                    print('  ★ 解长 vs 上帝之数 %d（全局最坏最短）：中位 %.0f 步'
                          '、最长 %d 步' % (god, med, max(acts)))
                    over = [a for a in acts if a > god]
                    if over:
                        print('    ★超最短上界 %d 步的局：%d/%d（解长 %s）'
                              '——上帝之数=最坏最短，故每局最短都 ≤%d；'
                              '这些局的求解器解长超出最短上界，即明确的'
                              '优化空间（最差 %.1f 倍）'
                              % (god, len(over), len(acts),
                                 sorted(over, reverse=True), god,
                                 max(over) / god))
        if failed:
            phis = [r['phi'] for r in failed if r.get('phi') is not None]
            de = Counter(str(r.get('deadend')) for r in failed)
            saves = [r for r in failed if r.get('save_file')]
            print('  失败 %d 局：Φ 中位 %s；死局标注 %s；存档 %d 个'
                  % (len(failed),
                     ('%.1f' % statistics.median(phis)) if phis else '-',
                     '/'.join('%s×%d' % (k, v) for k, v in de.items()),
                     len(saves)))

    # 失败样本存档盘点
    n_saves = len(glob.glob(os.path.join(SAVE_DIR, '*.json'))) \
        if os.path.isdir(SAVE_DIR) else 0
    print()
    print('失败样本存档（save/blindspot/）：%d 个' % n_saves)

    # 豆包三岔口的第一刀：失败集中在少数几类 / 五花八门 / 极少
    all_fail = [r for r in rows if r['outcome'] in ('partial', 'fail')]
    corpus_fail = [r for r in all_fail if r.get('src') == 'corpus']
    save_fail = [r for r in all_fail if r.get('src') == 'save_mid']
    print()
    print('失败样本构成：语料局（必然可解）失败 %d 局 = 真·能力盲区；'
          '存档中盘局失败 %d 局（可能含真死局，死局标注见上）'
          % (len(corpus_fail), len(save_fail)))
    total_corpus = len([r for r in rows if r.get('src') == 'corpus'])
    if total_corpus:
        print('语料局失败率：%.1f%%（%d/%d）——豆包三岔口判据：'
              '失败极少→现状够用；集中少数类→手写公式；散开→才考虑 AI 挖掘'
              % (100.0 * len(corpus_fail) / total_corpus,
                 len(corpus_fail), total_corpus))


if __name__ == '__main__':
    main()
