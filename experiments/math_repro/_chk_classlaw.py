"""檢驗「逐類三檔律」：穩定子 G 是否等於各著色類獨立取 {1（不動）, k（只能整體輪換）, k!（全對稱）} 的乘積。

讀 `_work/sweep_shapes_*_s*.csv`，從 shape 字串重算著色類大小（s 取命令列）。

用法：D:\\python\\python.exe _chk_classlaw.py <csv> <s>
"""
import csv
import sys
from collections import Counter
from itertools import product as iproduct
from math import factorial


def parse_shape(txt):
    rows = txt.split('/')
    return {(r, c) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == '#'}


def class_sizes(S, s):
    d = {}
    for (r, c) in S:
        k = (r % s, c % s)
        d[k] = d.get(k, 0) + 1
    return sorted(d.values(), reverse=True)


def options(k):
    if k <= 1:
        return [(1, '1')]
    if k == 2:
        return [(1, '1'), (2, 'k')]          # 2! = 2 與 k 同值
    return [(1, '1'), (k, 'k'), (factorial(k), 'k!')]


def all_products(sizes):
    out = {1: [()]}
    for k in sizes:
        nxt = {}
        for p, ways in out.items():
            for v, tag in options(k):
                np_ = p * v
                nxt.setdefault(np_, [])
                for w in ways:
                    nxt[np_].append(w + ((k, tag),))
        out = nxt
    return out


def main(path, s):
    rows = list(csv.DictReader(open(path, encoding='utf-8')))
    ok = bad = 0
    bad_rows = []
    tag_stats = Counter()
    for row in rows:
        S = parse_shape(row['shape'])
        sizes = class_sizes(S, s)
        G = int(row['G'])
        bound = int(row['bound'])
        prods = all_products(sizes)
        if G in prods:
            ok += 1
            # 取「能用最少 k! 的」寫法，方便看是輪換還是全對稱
            best = min(prods[G], key=lambda w: (sum(1 for _, t in w if t == 'k!'),
                                                sum(1 for _, t in w if t == 'k')))
            tag_stats[tuple(sorted((k, t) for k, t in best if t != '1'))] += 1
        else:
            bad += 1
            bad_rows.append((row['shape'], sizes, G, bound))
    print('檢查 %d 個形狀：符合「逐類三檔」%d 個、不符 %d 個' % (len(rows), ok, bad))
    print('\n(活著的類：大小＋檔位) → 次數:')
    for k, v in tag_stats.most_common():
        print('   %-28s %d' % (str(k), v))
    if bad_rows:
        print('\n不符的例子:')
        for r in bad_rows[:12]:
            print('   %-24s 類=%s G=%d 上界=%d' % r)


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
