#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
按「剖面缺陷 Φ」分档抽取真实棋盘样本（供官网形状画廊 / 体检注解图使用）。

每个 Φ 档抽若干个：优先抽可还原且步数接近该档平均的，另有回不来的则单独抽。
输出 JSON：{phi: [ {rows, overlap, phi, adj, h, w, solvable, sink, dist}, ... ]}

用法：
    D:\python\python.exe pick_phi_samples.py 4_4_2
"""
import sys, os, json, argparse
import numpy as np
from shape_stats import load_mem, compute, GRID

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def ascii_board(rows):
    nz = [i for i, v in enumerate(rows) if v]
    if not nz:
        return "(empty)"
    rmin, rmax = min(nz), max(nz)
    cmax = 0
    for v in rows:
        cmax = max(cmax, v.bit_length() - 1)
    out = []
    for r in range(rmin, rmax + 1):
        out.append("".join("#" if (rows[r] >> c) & 1 else "." for c in range(cmax + 1)))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("puzzle")
    ap.add_argument("--root", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "full_A"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--chunk", type=int, default=200000)
    ap.add_argument("--per", type=int, default=4)
    args = ap.parse_args()

    m, n, s = (int(x) for x in args.puzzle.split("_"))
    d = os.path.join(args.root, args.puzzle)
    mem = load_mem(os.path.join(d, "membership.bin"))
    flags = mem["flags"].astype(np.int32)
    dist = mem["dist"].astype(np.int32)
    solvable = ((flags >> 7) & 1)
    sink = ((flags >> 2) & 1)
    inb = ((flags >> 1) & 1)

    buckets = {}   # phi -> list of rec
    idx_global = 0
    with open(os.path.join(d, "boards.bin"), "rb") as f:
        total = os.path.getsize(os.path.join(d, "boards.bin")) // 32
        while idx_global < total:
            cnt = min(args.chunk, total - idx_global)
            arr = np.frombuffer(f.read(cnt * 32), dtype="<u2").reshape(cnt, GRID)
            r = compute(arr, m, n)
            sol = solvable[idx_global:idx_global + cnt]
            snk = sink[idx_global:idx_global + cnt]
            ib = inb[idx_global:idx_global + cnt]
            ds = dist[idx_global:idx_global + cnt]
            for i in range(cnt):
                ph = int(r["phi"][i])
                lst = buckets.setdefault(ph, [])
                rec = dict(rows=[int(x) for x in arr[i]], overlap=int(r["overlap"][i]),
                           phi=ph, adj=int(r["adj"][i]), h=int(r["h"][i]), w=int(r["w"][i]),
                           solvable=int(sol[i]), sink=int(snk[i]),
                           dist=int(ds[i]) if ib[i] == 1 else None,
                           idx=idx_global + i)
                if len(lst) < args.per * 4:
                    lst.append(rec)
                else:
                    # 保留：可还原的按步数分散，回不来的优先留
                    bad = [x for x in lst if not x["solvable"]]
                    good = [x for x in lst if x["solvable"]]
                    if not rec["solvable"] and len(bad) < args.per:
                        lst[len(good):len(good)] = [rec]
                        lst.pop()
                    elif rec["solvable"] and len(good) < args.per:
                        lst.append(rec)
                        lst.pop(0)
            idx_global += cnt

    # 每档整理：先回不来的（最多 per/2），再可还原的按步数排序取中间
    out = {}
    for ph, lst in buckets.items():
        bad = sorted([x for x in lst if not x["solvable"]], key=lambda x: -x["overlap"])[:max(1, args.per // 2)]
        good = sorted([x for x in lst if x["solvable"] and x["dist"] is not None],
                      key=lambda x: x["dist"])
        pick = []
        if good:
            mid = len(good) // 2
            order = [mid]
            k = 1
            while len(order) < min(len(good), args.per):
                if mid - k >= 0:
                    order.append(mid - k)
                if mid + k < len(good) and len(order) < min(len(good), args.per):
                    order.append(mid + k)
                k += 1
            pick = [good[i] for i in order]
        out[str(ph)] = bad + pick

    p = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 f"phi_samples_{args.puzzle}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(dict(puzzle=f"{m}x{n}x{s}", m=m, n=n, s=s, buckets=out), f,
                  ensure_ascii=False, separators=(",", ":"))
    print(f"写出 {p} ({os.path.getsize(p)/1024:.1f} KB)")
    for ph in sorted(out, key=lambda x: int(x)):
        for r in out[ph][:2]:
            print(f"--- Φ={ph} 可还原={r['solvable']} 步数={r['dist']} 聚拢={r['overlap']} bbox={r['h']}x{r['w']}")
            print(ascii_board(r["rows"]))


if __name__ == "__main__":
    main()
