# -*- coding: utf-8 -*-
"""活缝分区的接触边界测定（S2 设计决断的最后一票）。

对每个活缝 (family, t)（legal_moves 反证），计算其分区
{rank<t} | {rank≥t} 的接触边界 = 跨分区的共享边集合。
若接触边界非空 ⇒ 共享边模型可offer该缝；若为空 ⇒ 两侧几何不相接，
共享边模型 structurally 无法覆盖它（必须另想几何）。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.registry import make_board  # noqa: E402
from engine.shatter_geometry import _polygon_at  # noqa: E402

TOL = 1e-6


def shared_edges(polys):
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

    moves1 = board.legal_moves(1)
    live = {}
    for m in moves1:
        live.setdefault(m.family, set()).add(m.t)

    print(f"活缝分区接触边界（{len(edges)} 条共享边）：")
    for fam in spec.seam_families:
        for t in sorted(live.get(fam.name, ())):
            lo_keys = {k for k in keys if fam.rank_of(k[0], k[1]) < t}
            hi_keys = keys - lo_keys
            contact = [(ka, kb, seg) for ka, kb, seg in edges
                       if (ka in lo_keys) != (kb in lo_keys)]
            # 接触边方向角（度）
            angs = []
            for _ka, _kb, seg in contact:
                dx, dy = seg[1][0] - seg[0][0], seg[1][1] - seg[0][1]
                angs.append(round(math.degrees(math.atan2(dy, dx)) % 180, 1))
            print(f"  {fam.name} t={t}: 下侧 {len(lo_keys)} 块 / 上侧 "
                  f"{len(hi_keys)} 块，接触边 {len(contact)} 条，"
                  f"方向角 {sorted(angs)}")


if __name__ == '__main__':
    main()
