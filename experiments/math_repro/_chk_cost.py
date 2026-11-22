"""置換的「成本模型」探勘：把還原態能實現的每個置換，配上它的

  * 置換型（循環型別）
  * 動到的格數 n_moved（非不動點）
  * 支撐直徑 diam（動到的格之間的最大曼哈頓距離）
  * 支撐格數 / 支撐跨度（行跨度、列跨度）

再看最短步數跟誰有關。目的是找「換兩格為甚麼比轉一圈貴」的量化來源，
給 02/04 用；不是證明。

用法：D:\\python\\python.exe _chk_cost.py <dump_dir> <s> <goal_id>
"""
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import numpy as np

import _chk_labels as CL


def stats(v):
    v = sorted(v)
    n = len(v)
    med = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
    return min(v), med, sum(v) / n, max(v)


def main(d, s, g):
    bd = np.fromfile(os.path.join(d, 'boards.bin'), dtype='<u2').reshape(-1, 16)
    S = CL.cells_of(bd, g)
    start = frozenset((r, c, (r, c)) for (r, c) in S)
    dist = CL.bfs(start, s)
    print('dump=%s s=%d goal=%d 格數=%d' % (os.path.basename(d.rstrip('\\/')), s, g, len(S)))
    print('可達帶標籤狀態: %d' % len(dist))

    perms = []
    for k, dd in dist.items():
        if {(r, c) for (r, c, _) in k} != frozenset(S):
            continue
        mapping = {lab: (r, c) for (r, c, lab) in k}
        if len(mapping) != len(S):
            continue
        moved = [lab for lab, dst in mapping.items() if lab != dst]
        typ = CL.cycle_type(mapping)
        if moved:
            diam = max(abs(a[0] - b[0]) + abs(a[1] - b[1])
                       for a in moved for b in moved)
        else:
            diam = 0
        rspan = max(p[0] for p in moved) - min(p[0] for p in moved) if moved else 0
        cspan = max(p[1] for p in moved) - min(p[1] for p in moved) if moved else 0
        perms.append(dict(d=dd, typ=typ, moved=len(moved), diam=diam,
                          rspan=rspan, cspan=cspan))

    print('回到還原態的置換: %d 個' % len(perms))
    print('\n[按置換型]')
    groups = {}
    for p in perms:
        groups.setdefault(p['typ'], []).append(p['d'])
    for t, v in sorted(groups.items(), key=lambda x: (x[0], )):
        mn, med, mean, mx = stats(v)
        print('   %-20s n=%-4d min=%-3d med=%-5.1f mean=%-5.2f max=%-3d' % (str(t), len(v), mn, med, mean, mx))

    print('\n[按「動到的格數 n_moved」]')
    for nm in sorted({p['moved'] for p in perms}):
        v = [p['d'] for p in perms if p['moved'] == nm]
        mn, med, mean, mx = stats(v)
        print('   n_moved=%-3d 個數=%-4d min=%-3d med=%-5.1f mean=%-5.2f max=%-3d' % (nm, len(v), mn, med, mean, mx))

    print('\n[按支撐直徑 diam]')
    for dm in sorted({p['diam'] for p in perms}):
        v = [p['d'] for p in perms if p['diam'] == dm]
        mn, med, mean, mx = stats(v)
        print('   diam=%-3d 個數=%-4d min=%-3d med=%-5.1f mean=%-5.2f max=%-3d' % (dm, len(v), mn, med, mean, mx))

    print('\n[按 (n_moved, 循環個數)]')
    keyf = lambda p: (p['moved'], len(p['typ']))
    for kk in sorted({keyf(p) for p in perms}):
        v = [p['d'] for p in perms if keyf(p) == kk]
        mn, med, mean, mx = stats(v)
        print('   moved=%-3d cyc=%-2d 個數=%-4d min=%-3d med=%-5.1f max=%-3d' % (kk[0], kk[1], len(v), mn, med, mx))

    print('\n[逐型逐支撐]（只列 n<=6 的型）')
    for t in sorted(groups, key=lambda t: (len(t), t)):
        if len(t) > 6:
            continue
        items = sorted([(p['d'], t, p['moved'], p['diam'], p['rspan'], p['cspan'])
                        for p in perms if p['typ'] == t])
        for it in items:
            print('   d=%-3d %-16s moved=%d diam=%d span=(%d,%d)' % it)


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
