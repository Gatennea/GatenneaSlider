# -*- coding: utf-8 -*-
"""
从 repro_fast 的 dump 读各尺寸的最短回路（回到满盘所需的最少步数）。

状态机口径：repro_fast 的状态是「占位形状」（不含块标签），规范化后平移被商掉，
所以「满盘」在状态空间里只有一个表示（gid）。因此：
  - 从 gid 出发走一步再回来 = 长度 2 的平凡回路（推出去推回来），恒等；
  - 非平凡回路 = 一条边 u -> gid，且 dist[u] >= 2，长度 dist[u] + 1。

board 满盘判据：前 m 行全为 (1<<n)-1，其余行为 0（格数恒为 m*n）。

用法：
  python _loop_table.py                 # 扫 _work 下所有 dump，按 (m,n,s) 去重
  python _loop_table.py out_4x4_s2      # 只扫一个目录
"""
import os
import re
import sys
import numpy as np


def read_head(d):
    p = os.path.join(d, 'summary.txt')
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf8') as f:
            head = f.readline().strip()
    except Exception:
        return None
    mt = re.match(r'=== \((\d+),(\d+),(\d+)\) K=(\d+)', head)
    if not mt:
        return None
    return dict(m=int(mt.group(1)), n=int(mt.group(2)), s=int(mt.group(3)), k=int(mt.group(4)))


def scan(d, meta, chunk=1 << 20):
    bp = os.path.join(d, 'boards.bin')
    mp = os.path.join(d, 'membership.bin')
    ep = os.path.join(d, 'edges.bin')
    if not (os.path.exists(bp) and os.path.exists(mp) and os.path.exists(ep)):
        return None
    nst_b = os.path.getsize(bp) // 32
    nst_m = os.path.getsize(mp) // 16
    if nst_b == 0 or nst_b != nst_m:
        return None

    m, n = meta['m'], meta['n']
    rowmask = np.uint16((1 << n) - 1)

    b = np.memmap(bp, dtype=np.uint16, mode='r', shape=(nst_b, 16))
    mm = np.memmap(mp, dtype=np.uint8, mode='r', shape=(nst_b, 16))
    dist = np.ascontiguousarray(mm[:, 10:14]).view(np.int32).reshape(-1)

    # 1) 找满盘状态（规范形下应恰好一个）
    gids = []
    for st in range(0, nst_b, chunk):
        en = min(st + chunk, nst_b)
        rows = np.array(b[st:en])
        full = np.all(rows[:, :m] == rowmask, axis=1)
        if m < 16:
            full &= np.all(rows[:, m:] == 0, axis=1)
        idx = np.nonzero(full)[0]
        for i in idx:
            gids.append(st + int(i))
    n_full = len(gids)
    if n_full == 0:
        return dict(nst=nst_b, n_full=0, loop=None, triv=0, gid=None)
    # 取 dist==0 的那个（真起点）；否则取第一个
    gid = None
    for g in gids:
        if dist[g] == 0:
            gid = g
            break
    if gid is None:
        gid = gids[0]

    # 2) 扫边，找 u -> gid
    ne = os.path.getsize(ep) // 8
    ea = np.fromfile(ep, dtype=np.uint32, count=ne * 2).reshape(-1, 2)
    is_in = ea[:, 1] == gid
    us = ea[is_in, 0].astype(np.int64)
    du = dist[us] if len(us) else np.array([], dtype=np.int32)

    triv = int((du == 1).sum())                  # 1 步直达 = 平凡往返
    n_pos = int((du > 0).sum())
    # 非平凡：dist[u] >= 2
    nz = du[du >= 2]
    loop = int(nz.min()) + 1 if nz.size else None   # 回路长度 = dist[u] + 1

    return dict(nst=nst_b, n_full=n_full, gid=int(gid), n_edge=ne,
                triv=triv, n_in=n_pos, loop=loop,
                min_all=int(du[du > 0].min()) + 1 if n_pos else None)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    if len(sys.argv) > 1:
        targets = [os.path.join(here, sys.argv[1])]
    else:
        targets = []
        for name in sorted(os.listdir(here)):
            d = os.path.join(here, name)
            if os.path.isdir(d) and read_head(d):
                targets.append(d)

    rows = []
    for d in targets:
        meta = read_head(d)
        if not meta:
            continue
        name = os.path.basename(d)
        r = scan(d, meta)
        if not r:
            continue
        rows.append(dict(name=name, **meta, **r))
        print(f"{name:<14} ({meta['m']},{meta['n']},{meta['s']}) K={meta['k']:<3} "
              f"|A|={r['nst']:<10,} full={r['n_full']:<3} 平凡入边={r['triv']:<4} "
              f"最短回路={r['loop']}", flush=True)

    print("\n=== 按 (m,n,s) 去重（保留 |A| 最大者）===")
    print(f"{'(m,n,s)':<12}{'K':<4}{'|A|':<12}{'shortest loop':<15}{'trivial in':<12}{'source':<14}")
    bb = {}
    for r in rows:
        key = (r['m'], r['n'], r['s'])
        if key not in bb or r['nst'] > bb[key]['nst']:
            bb[key] = r
    for key in sorted(bb):
        r = bb[key]
        print(f"{str(key):<12}{r['k']:<4}{r['nst']:<12,}{str(r['loop']):<15}{r['triv']:<12}{r['name']:<14}")


if __name__ == '__main__':
    main()
