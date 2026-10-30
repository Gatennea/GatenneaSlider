# -*- coding: utf-8 -*-
"""碎三角还原态几何 dump：看 rank 与平面几何的真实关系。

L_v 的 rank = P_y，但缝线 {rank=t} 在平面是 y=t/2，而 P_y=t 的块质心在
平面 y=t/6——差 3 倍。需要看清：缝线到底沿哪些块边、t 与块几何的对应。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.registry import make_board  # noqa: E402
from engine.shatter_geometry import _polygon_at  # noqa: E402

SQ3 = math.sqrt(3.0)


def main():
    board = make_board('shatter')
    spec = board.spec
    fams = {f.name: f for f in spec.seam_families}
    rows = []
    for k in sorted(board.keys, key=lambda k: (k[0][1], k[0][0])):
        p, o = k
        poly = _polygon_at(p, o)
        cx = sum(v[0] for v in poly) / 3.0
        cy = sum(v[1] for v in poly) / 3.0
        rv = {n: fams[n].rank_of(p, o) for n in ('L_v', 'L_d30', 'L_d150')}
        rows.append((p, o, cx, cy, rv,
                     [(round(v[0], 3), round(v[1], 3)) for v in poly]))
    print(f"{len(rows)} 块；按 P_y 排序。列：P | 角色 | 质心平面 | L_v/L_d30/L_d150 rank")
    for p, o, cx, cy, rv, poly in rows:
        print(f"P={p} {o:>3} 质心=({cx:7.3f},{cy:6.3f}) "
              f"rank L_v={rv['L_v']:4d} L_d30={rv['L_d30']:4d} "
              f"L_d150={rv['L_d150']:5d}  poly={poly}")

    # 关键对照：L_v 真实缝 t=6 的线（平面 y=3）附近有哪些块？
    print("\n== L_v t=6（平面 y=3.0）附近：质心 y∈[1,4] 的块 ==")
    for p, o, cx, cy, rv, poly in rows:
        if 1.0 <= cy <= 4.0:
            ymin = min(v[1] for v in poly)
            ymax = max(v[1] for v in poly)
            print(f"  P={p} {o:>3} 质心 y={cy:6.3f} y∈[{ymin:5.2f},{ymax:5.2f}] "
                  f"L_v rank={rv['L_v']}")

    print("\n== L_v t=7（平面 y=3.5）附近：质心 y∈[1,4.5] 的块 ==")
    for p, o, cx, cy, rv, poly in rows:
        if 1.0 <= cy <= 4.5:
            ymin = min(v[1] for v in poly)
            ymax = max(v[1] for v in poly)
            print(f"  P={p} {o:>3} 质心 y={cy:6.3f} y∈[{ymin:5.2f},{ymax:5.2f}] "
                  f"L_v rank={rv['L_v']}")


if __name__ == '__main__':
    main()
