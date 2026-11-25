# -*- coding: utf-8 -*-
"""奇偶层：把 289 条生成元投影成 4 位「每类是否奇置换」，在 GF(2)^4 上求最短。

为什么需要这一层：单类生成元在 4×4/s=2 下全部是 3-cycle（偶），闭包只有 A_4（12 阶）。
也就是说「每类各解一遍」只能覆盖偶排列（1/16 的联合排列），奇排列必须靠跨类公式翻转。
奇偶翻转是比 331,776 小得多的问题：16 个状态。
"""

import heapq
import re
from collections import defaultdict

M = N = 4
S = 2
P = M * N


def load(path):
    out = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line[0] not in '0123456789':
                continue
            m = re.search(r'@\s*(\d+)\s*$', line)
            if not m:
                continue
            depth = int(m.group(1))
            nums = [int(x) for x in re.findall(r'-?\d+', line[:m.start()])]
            if len(nums) < P:
                continue
            out.append((nums[:P], depth))
    return out


def klass(p):
    r, c = divmod(p, N)
    return (r % S, c % S)


def class_points(k):
    return [p for p in range(P) if klass(p) == k]


def parity_of(v, pts):
    """该类内置换的奇偶性（1=奇）。"""
    idx = {p: i for i, p in enumerate(pts)}
    seen = [False] * len(pts)
    cycles = 0
    moved = 0
    for i, p in enumerate(pts):
        if seen[i]:
            continue
        # 位置 i 上是标签 v[p]，去的位置 = idx[v[p]]
        j = i
        ln = 0
        while not seen[j]:
            seen[j] = True
            t = v[pts[j]]
            if t not in idx:
                return None
            j = idx[t]          # 下一跳
            ln += 1
        if ln > 1:
            cycles += 1
            moved += ln
    return (moved - cycles) % 2


def main(path):
    gens = load(path)
    pts = {k: class_points(k) for k in sorted({klass(p) for p in range(P)})}
    order = sorted(pts)

    vecs = []
    cls_dist = defaultdict(int)
    for v, dep in gens:
        sup = [t for t in range(P) if v[t] != t]
        nk = len({klass(p) for p in sup})
        cls_dist[nk] += 1
        bits = 0
        ok = True
        for bi, k in enumerate(order):
            par = parity_of(v, pts[k])
            if par is None:
                ok = False
                break
            if par:
                bits |= 1 << bi
        if ok:
            vecs.append((bits, dep, nk))

    print(f'{path}: {len(gens)} 条')
    print('涉及类数分布:', dict(sorted(cls_dist.items())))
    print()

    # 用 (bits, 权重) 跑 16 状态最短路
    uniq = {}
    for bits, dep, nk in vecs:
        if bits == 0:
            continue
        if bits not in uniq or dep < uniq[bits]:
            uniq[bits] = dep
    print(f'非平凡奇偶向量 {len(uniq)} 种：')
    for bits, dep in sorted(uniq.items(), key=lambda x: x[1]):
        s = format(bits, '04b')
        print(f'  bits={s} depth={dep}')
    print()

    # GF(2)^4 最短路（动作 = XOR bits，权 = depth）
    targets = range(16)
    res = {}
    for t in targets:
        best = {0: 0}
        pq = [(0, 0)]
        while pq:
            d, st = heapq.heappop(pq)
            if d > best.get(st, 1 << 30):
                continue
            for bits, w in uniq.items():
                ns = st ^ bits
                nd = d + w
                if nd < best.get(ns, 1 << 30):
                    best[ns] = nd
                    heapq.heappush(pq, (nd, ns))
        res[t] = best.get(t, None)

    print('奇偶层：把「目标奇数向量」翻成全偶的最短步数')
    for t in sorted(targets, key=lambda x: (res[x] if res[x] is not None else 99, x)):
        if res[t] is None:
            continue
        print(f'  {format(t,"04b")} -> {res[t]} 步')
    worst = max(v for v in res.values() if v is not None)
    print(f'  奇偶层最坏 = {worst} 步')

    print()
    print('可达性：奇偶层状态覆盖', len([t for t in targets if res[t] is not None]), '/16')
    return 0


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else '_s2_d8_gens.log'))
