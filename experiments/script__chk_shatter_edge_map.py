# -*- coding: utf-8 -*-
"""共享边 → (族, t) 映射实验（S2 点缝几何设计决断用）。

规则候选（来自方形惯例的推广）：两块共享一条边、且在某族下 rank 不同
（r_lo < r_hi）⇒ 该边是族 seam(t=r_hi) 的接触边界的一部分（t = 上侧
块的 rank，与方形「行 r-1 与行 r 的界 ⇒ t=r」同惯例）。

本脚本回答：
  Q1  还原态共有多少条共享边？每条的 rank 对（按族）？
  Q2  该规则生成的候选缝集 vs 引擎活缝集（legal_moves 反证）的覆盖率？
  Q3  一条边会被多少族同时认领（歧义度）？
  Q4  活缝的接触边数 vs 死缝的接触边数——有无可分性？
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.registry import make_board  # noqa: E402
from engine.shatter_geometry import _polygon_at  # noqa: E402

TOL = 1e-6


def shared_edges(polys):
    """全部共享边：两块多边形有恰好两个公共顶点（容差）⇒ 共享边。"""
    keys = list(polys)
    out = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            common = []
            for p in polys[keys[i]]:
                for q in polys[keys[j]]:
                    if abs(p[0] - q[0]) <= TOL and abs(p[1] - q[1]) <= TOL:
                        common.append(p)
                        break
            if len(common) == 2:
                out.append((keys[i], keys[j], tuple(common)))
    return out


def main():
    board = make_board('shatter')
    spec = board.spec
    keys = board.keys
    polys = {k: _polygon_at(k[0], k[1]) for k in keys}
    edges = shared_edges(polys)
    print(f"共享边 {len(edges)} 条（48 块还原态）")

    moves1 = board.legal_moves(1)
    live = {}
    for m in moves1:
        live.setdefault(m.family, set()).add(m.t)

    # Q1/Q3：每条边按族认领
    claim = {}       # (family, t) -> [边...]
    edge_fams = {}   # 边 -> 认领族数
    for ka, kb, seg in edges:
        nfam = 0
        for fam in spec.seam_families:
            ra = fam.rank_of(ka[0], ka[1])
            rb = fam.rank_of(kb[0], kb[1])
            if ra == rb:
                continue
            rlo, rhi = min(ra, rb), max(ra, rb)
            claim.setdefault((fam.name, rhi), []).append(seg)
            nfam += 1
        edge_fams[(ka, kb)] = nfam

    from collections import Counter
    print(f"\nQ3 每条边被几个族认领：{dict(Counter(edge_fams.values()))}")

    for fam in spec.seam_families:
        cand = sorted(t for (f, t) in claim if f == fam.name)
        lv = live.get(fam.name, set())
        # 规则候选按「分区等价」折算到引擎代表 t：同分区只留最小 t
        part = {}
        for t in cand:
            key = frozenset(k for k in keys
                            if fam.rank_of(k[0], k[1]) < t)
            part.setdefault(key, []).append(t)
        rep = {min(v) for v in part.values()}
        print(f"\n== {fam.name} ==")
        print(f"  规则候选 {len(cand)} 个：{cand}")
        print(f"  折算分区代表 {len(rep)} 个：{sorted(rep)}")
        print(f"  引擎活缝 {len(lv)} 个：{sorted(lv)}")
        cover = lv & rep
        print(f"  Q2 活缝被规则覆盖：{len(cover)}/{len(lv)} "
              f"{'✅' if len(cover) == len(lv) else '❌ 漏: ' + str(sorted(lv - rep))}")
        extra = sorted(rep - lv)
        print(f"  规则多出（死缝）：{len(extra)} 个 {extra}")
        # Q4：活/死缝的接触边数
        live_edges = [len(claim.get((fam.name, t), [])) for t in sorted(lv)]
        dead_edges = [len(claim.get((fam.name, t), [])) for t in extra]
        print(f"  Q4 活缝接触边数：{live_edges}")
        print(f"     死缝接触边数：{dead_edges}")


if __name__ == '__main__':
    main()
