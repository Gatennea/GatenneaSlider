#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
对「完整着色集 A」的每个状态计算形状指标，并做聚合统计（供官网可视化）。

指标（口径与引擎完全一致）：
    overlap  聚拢度分子：与 m×n / n×m 矩形（任意平移）的最佳重叠块数；聚拢度 = overlap / K
    bbox     边界盒 (高 h, 宽 w)；填充率 = K / (h*w)；盒内空格 = h*w - K
    phi      Φ 剖面缺陷（行/列计数 L1 偏差之和，含转置取优；0 = 已还原形状）
    adj      粘连度：四连通相邻格对数（实心 m×n 矩形取最大值 2K-m-n）

关联（来自 membership.bin）：flags / outdeg / indeg / dist（回程最少步数）

用法：
    D:\python\python.exe shape_stats.py 4_4_2 [--out <json>] [--chunk N]
"""
import sys, os, json, random, argparse
import numpy as np

GRID = 16
MEM_DT = np.dtype({
    "names": ["id", "flags", "pad", "outdeg", "indeg", "dist"],
    "formats": ["<u4", "u1", "u1", "<u2", "<u2", "<i4"],
    "itemsize": 16,
})


def load_mem(path):
    with open(path, "rb") as f:
        data = f.read()
    return np.frombuffer(data, dtype=MEM_DT, count=len(data) // 16)


def compute(arr, m, n):
    """arr: (chunk,16) uint16 行位掩码。返回各项指标数组。"""
    N = arr.shape[0]
    bits = ((arr[:, :, None] >> np.arange(GRID, dtype=np.uint16)) & 1).astype(np.uint8)

    rowsum = bits.sum(axis=2, dtype=np.int32)          # (N,16)
    colsum = bits.sum(axis=1, dtype=np.int32)          # (N,16)

    def extent(s):
        nz = s > 0
        has = nz.any(axis=1)
        lo = nz.argmax(axis=1)
        hi = GRID - 1 - nz[:, ::-1].argmax(axis=1)
        lo = np.where(has, lo, 0)
        hi = np.where(has, hi, -1)
        return lo, hi - lo + 1

    rlo, h = extent(rowsum)
    clo, w = extent(colsum)
    bbox_area = h * w
    K = m * n

    # ---- 聚拢度：与 m×n / n×m 矩形的最佳重叠 ----
    cum = np.cumsum(bits, axis=1, dtype=np.uint8)      # (N,16,16)
    best = np.zeros(N, dtype=np.int32)
    for rh, cw in ({(m, n), (n, m)}):
        for r0 in range(0, GRID - rh + 1):
            hi_i = r0 + rh - 1
            band = cum[:, hi_i, :].astype(np.int32)
            if r0 > 0:
                band = band - cum[:, r0 - 1, :]
            bcum = np.cumsum(band, axis=1, dtype=np.int32)
            for c0 in range(0, GRID - cw + 1):
                v = bcum[:, c0 + cw - 1]
                if c0 > 0:
                    v = v - bcum[:, c0 - 1]
                np.maximum(best, v, out=best)
    overlap = best

    # ---- Φ 剖面缺陷（含转置取优）----
    rs = np.sort(rowsum, axis=1)[:, ::-1]
    cs = np.sort(colsum, axis=1)[:, ::-1]

    def defect(s, n_top, per):
        d = np.abs(s[:, :n_top] - per).sum(axis=1) + s[:, n_top:].sum(axis=1)
        return d.astype(np.int32)

    a = defect(rs, m, n) + defect(cs, n, m)
    if m == n:
        phi = a
    else:
        b = defect(rs, n, m) + defect(cs, m, n)
        phi = np.minimum(a, b)

    # ---- 粘连度：四连通相邻格对数 ----
    adjh = (bits[:, :, :-1] & bits[:, :, 1:]).sum(axis=(1, 2), dtype=np.int32)
    adjv = (bits[:, :-1, :] & bits[:, 1:, :]).sum(axis=(1, 2), dtype=np.int32)
    adj = adjh + adjv

    return dict(overlap=overlap, h=h, w=w, bbox_area=bbox_area,
                holes=bbox_area - K, phi=phi, adj=adj, rlo=rlo, clo=clo)


class Agg:
    """按 (key) 聚合：count / solvable / sink / dist 和 / phi 和 / adj 和。"""

    def __init__(self):
        self.d = {}

    def add(self, key, n, sol, sink, dist_sum, dist_n, phi, adj):
        e = self.d.get(key)
        if e is None:
            e = self.d[key] = dict(count=0, sol=0, sink=0, dsum=0, dn=0, psum=0.0, asum=0.0)
        e["count"] += int(n)
        e["sol"] += int(sol)
        e["sink"] += int(sink)
        e["dsum"] += float(dist_sum)
        e["dn"] += int(dist_n)
        e["psum"] += float(phi)
        e["asum"] += float(adj)

    def as_list(self, name, extra=None):
        out = []
        for k, e in sorted(self.d.items()):
            rec = {}
            if name is not None:
                rec[name] = (k if not isinstance(k, tuple) else list(k))
            rec["count"] = e["count"]
            rec["solvable"] = e["sol"]
            rec["sink"] = e["sink"]
            rec["mean_dist"] = round(e["dsum"] / e["dn"], 2) if e["dn"] else None
            rec["mean_phi"] = round(e["psum"] / e["count"], 2)
            rec["mean_adj"] = round(e["asum"] / e["count"], 2)
            if extra:
                rec.update(extra(k))
            out.append(rec)
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("puzzle", help="形如 4_4_2")
    ap.add_argument("--root", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "full_A"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--chunk", type=int, default=200000)
    ap.add_argument("--samples", type=int, default=6)
    args = ap.parse_args()

    m, n, s = (int(x) for x in args.puzzle.split("_"))
    d = os.path.join(args.root, args.puzzle)
    K = m * n
    mem = load_mem(os.path.join(d, "membership.bin"))
    N = mem.shape[0]
    flags = mem["flags"].astype(np.int32)
    dist = mem["dist"].astype(np.int32)
    solvable = ((flags >> 7) & 1)
    sink = ((flags >> 2) & 1)
    inb = ((flags >> 1) & 1)

    print(f"[{args.puzzle}] m={m} n={n} s={s} K={K} |A|={N}")

    bp = os.path.join(d, "boards.bin")
    ag_gather = Agg()      # overlap
    ag_bbox = Agg()        # (h,w)
    ag_phi = Agg()         # phi
    ag_adj = Agg()         # adj
    ag_cross = Agg()       # (overlap, phi)
    ag_gd = Agg()          # (overlap, dist)
    ag_hole = Agg()        # holes in bbox
    ag_fill = Agg()        # fill class

    rnd = random.Random(20261017)
    res = {}               # overlap -> list of sample dicts
    sink_samples = []
    n_seen = 0
    max_h = max_w = 0

    def reservoir(key, rec):
        lst = res.setdefault(key, [])
        if len(lst) < args.samples:
            lst.append(rec)
        else:
            j = rnd.randrange(len(lst) + 1)
            if j < args.samples:
                lst[j] = rec

    with open(bp, "rb") as f:
        total_bytes = os.path.getsize(bp)
        nstates = total_bytes // 32
        idx = 0
        while idx < nstates:
            cnt = min(args.chunk, nstates - idx)
            raw = f.read(cnt * 32)
            arr = np.frombuffer(raw, dtype="<u2").reshape(cnt, GRID)
            r = compute(arr, m, n)
            fl = flags[idx:idx + cnt]
            ds = dist[idx:idx + cnt]
            sol = solvable[idx:idx + cnt]
            snk = sink[idx:idx + cnt]
            inb_ = inb[idx:idx + cnt]
            dist_valid = inb_ == 1
            dsum_arr = np.where(dist_valid, ds, 0).astype(np.int64)
            max_h = max(max_h, int(r["h"].max()))
            max_w = max(max_w, int(r["w"].max()))

            # 按各类分组求和
            def group(keys):
                """keys: array of int keys -> dict key -> (count, sol, sink, dsum, dn, psum, asum)"""
                out = {}
                order = np.argsort(keys, kind="stable")
                ks = keys[order]
                uniq, starts = np.unique(ks, return_index=True)
                ends = np.append(starts[1:], len(ks))
                for u, a0, b0 in zip(uniq, starts, ends):
                    sel = order[a0:b0]
                    c = int(b0 - a0)
                    ss = int(sol[sel].sum())
                    sk = int(snk[sel].sum())
                    dv = dist_valid[sel]
                    dn = int(dv.sum())
                    dsm = int(dsum_arr[sel].sum())
                    out[int(u)] = (c, ss, sk, dsm, dn,
                                   float(r["phi"][sel].sum()), float(r["adj"][sel].sum()))
                return out

            for key_arr, agg in ((r["overlap"], ag_gather), (r["phi"], ag_phi),
                                 (r["adj"], ag_adj), (r["holes"], ag_hole)):
                for u, v in group(key_arr.astype(np.int64)).items():
                    agg.add(u, *v)

            for key_arr, agg in ((r["h"] * 100 + r["w"], ag_bbox),
                                 (r["overlap"] * 1000 + r["phi"], ag_cross),
                                 (r["overlap"] * 100 + np.where(dist_valid, ds, -1), ag_gd)):
                for u, v in group(key_arr.astype(np.int64)).items():
                    agg.add(u, *v)

            # 样本
            for lvl in np.unique(r["overlap"]):
                sel = np.where(r["overlap"] == lvl)[0]
                for i in sel:
                    if rnd.random() > 0.35:
                        continue
                    gi = idx + int(i)
                    reservoir(int(lvl), dict(
                        idx=gi, overlap=int(lvl), phi=int(r["phi"][i]), adj=int(r["adj"][i]),
                        h=int(r["h"][i]), w=int(r["w"][i]),
                        solvable=int(sol[i]), sink=int(snk[i]),
                        dist=int(ds[i]) if dist_valid[i] else None,
                        rows=[int(x) for x in arr[i]],
                    ))
                    break
            for i in np.where(snk == 1)[0]:
                if len(sink_samples) < 12:
                    sink_samples.append(dict(
                        idx=idx + int(i), overlap=int(r["overlap"][i]), phi=int(r["phi"][i]),
                        adj=int(r["adj"][i]), h=int(r["h"][i]), w=int(r["w"][i]),
                        dist=None, rows=[int(x) for x in arr[i]]))

            idx += cnt
            n_seen += cnt
            print(f"  ... {n_seen}/{nstates}", end="\r", flush=True)
    print()

    def dec_bbox(k):
        return dict(h=k // 100, w=k % 100)

    def dec_cross(k):
        return dict(overlap=k // 1000, phi=k % 1000)

    def dec_gd(k):
        return dict(overlap=k // 100, dist=(k % 100) if (k % 100) >= 0 else None)

    out = dict(
        puzzle=f"{m}x{n}x{s}", m=m, n=n, s=s, K=K, total=int(N),
        max_h=max_h, max_w=max_w,
        gather=ag_gather.as_list("overlap"),
        bbox=ag_bbox.as_list("size", dec_bbox),
        phi=ag_phi.as_list("phi"),
        adj=ag_adj.as_list("adj"),
        holes=ag_hole.as_list("holes"),
        cross=ag_cross.as_list(None, dec_cross),
        gather_dist=ag_gd.as_list(None, dec_gd),
        samples={str(k): v for k, v in sorted(res.items())},
        sink_samples=sink_samples,
    )
    # cross / gather_dist 里把 dist=-1（不可还原）标成 null
    for rec in out["cross"]:
        pass
    for rec in out["gather_dist"]:
        if rec["dist"] == 99:
            rec["dist"] = None

    p = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 f"shape_stats_{args.puzzle}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"写出 {p}  ({os.path.getsize(p)/1024:.1f} KB)")
    print(f"  bbox 最大: h={max_h} w={max_w}")
    # 速览
    print("\n聚拢度 overlap : 局面数 / 可还原率 / 平均步数 / 平均Φ")
    for r in out["gather"]:
        print(f"  {r['overlap']:3d} : {r['count']:8d}  {100*r['solvable']/r['count']:6.2f}%  "
              f"{str(r['mean_dist']):>6}  {r['mean_phi']:6.2f}")
    print("\n边界盒 h x w : 局面数 / 可还原率 / 平均步数（前 12 大）")
    for r in sorted(out["bbox"], key=lambda x: -x["count"])[:12]:
        print(f"  {r['h']}x{r['w']} : {r['count']:8d}  {100*r['solvable']/r['count']:6.2f}%  {r['mean_dist']}")


if __name__ == "__main__":
    main()
