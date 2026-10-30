# -*- coding: utf-8 -*-
"""碎三角合法移动的物理语义：L_v t=6 的移动到底搬了哪些块、搬到哪。

若 rank 分区与几何脱节，则 GUI 的缝线绘制/命中必须另找几何实在
（真实共享边），本脚本把「移动前后块位置」打出来对照布局图。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.registry import make_board  # noqa: E402
from engine.shatter_geometry import _polygon_at  # noqa: E402


def cen(p, o):
    poly = _polygon_at(p, o)
    return (sum(v[0] for v in poly) / 3.0, sum(v[1] for v in poly) / 3.0)


def main():
    board = make_board('shatter')
    spec = board.spec
    moves = [m for m in board.legal_moves(1) if m.family == 'L_v']
    print(f"L_v 合法移动 {len(moves)} 个：")
    for m in moves:
        print(f"  t={m.t} side={m.side} dir={m.direction} "
              f"moved={len(m.moved)} 块")

    # 逐个应用，打印搬动块的质心前后
    for m in moves[:6]:
        nb = board.apply(m)
        moved = set(m.moved)
        print(f"\n== 应用 t={m.t} side={m.side} dir={m.direction} ==")
        for k in sorted(moved):
            c0 = cen(k[0], k[1])
            nk = (k[0][0] + m.direction[0], k[0][1] + m.direction[1]), k[1]
            c1 = cen(nk[0], nk[1])
            print(f"  {k[0]} {k[1]:>3} 质心 ({c0[0]:6.3f},{c0[1]:5.3f})"
                  f" → ({c1[0]:6.3f},{c1[1]:5.3f})")
        # 移动后是否仍还原态之外（is_solved 应变假）
        print(f"  移动后 is_solved={nb.is_solved()}，块数={nb.block_count}")
        # 该移动可逆？（apply 逆方向）
        inv = type(m)(m.family, m.t, -m.side,
                      tuple(-x for x in m.direction), m.step, m.moved)
        back = nb.apply(inv)
        print(f"  逆应用后 is_solved={back.is_solved()}")


if __name__ == '__main__':
    main()
