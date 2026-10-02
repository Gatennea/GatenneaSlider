# -*- coding: utf-8 -*-
"""用户新构造的几何内核：mi 无限密铺里「被横着切」的两块 = 45° 放的小正方形。

用户原话（2026-10-03）：
  「tri 可以是另一种 mi 的子集，要求无限密铺，再把所有被横着切的两个滑块
    组成的小正方形（在当前谜题中这个正方形是 45° 放的）旋转 90°」

本脚本只做纯几何核对，不做同构判断（构造的最后一跳还需要用户澄清）：
  G1  被 h 缝（水平格边）切开的一对 S(r,c) / N(r+1,c) 是否拼成一个正方形
  G2  该正方形是否 45° 放（边不沿格边、对角线沿格边）
  G3  旋转 90° 之后，这一对滑块的公共边由「水平对角线」变成「竖直对角线」
      —— 也就是同一对块改按 E(r,c)/W(r,c+1) 的方式配对
  G4  度量对照：这个 45° 正方形与三角形密铺的菱形胞（▲+▼）差多少
      （形状 / 边长 / 面积），用来定位「哪一步还不是等距变换」

跑法：python -u experiments/_mi_zige_square.py
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_mi import mi_vertices


def poly(vs):
    return [(x, y) for (x, y) in vs]


def area(vs) -> float:
    s = 0.0
    n = len(vs)
    for t in range(n):
        x1, y1 = vs[t]
        x2, y2 = vs[(t + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def side_len(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def is_square(vs) -> bool:
    """四边形是正方形：四边等长 + 面积 == 边长²。"""
    if len(vs) != 4:
        return False
    sides = [side_len(vs[t], vs[(t + 1) % 4]) for t in range(4)]
    ok = all(abs(s - sides[0]) < 1e-9 for s in sides)
    return ok and abs(area(vs) - sides[0] ** 2) < 1e-9


def rot90(pts, center):
    cx, cy = center
    return [(cx - (y - cy), cy + (x - cx)) for (x, y) in pts]


def convex_hull(points):
    pts = sorted(set(points))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo = []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    up = []
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def G1_G2_G3():
    print('=' * 70)
    print('G1-G3  被 h 缝切开的一对块 → 45° 正方形 → 转 90° 改配对')
    print('=' * 70)
    S = mi_vertices(0, 0, 'S')          # 下一格的下半（斜边 = 下格边）
    N = mi_vertices(1, 0, 'N')          # 下一格的上半（斜边 = 上格边）
    print(f'  S(0,0) = {poly(S)}')
    print(f'  N(1,0) = {poly(N)}')
    shared = set(map(tuple, S)) & set(map(tuple, N))
    print(f'  公共顶点（= 公共边两端）：{sorted(shared)}')
    hull = convex_hull(poly(S) + poly(N))
    print(f'  两块并集的凸包 = {poly(hull)}')
    print(f'  是正方形：{is_square(hull)}   边长 {side_len(hull[0], hull[1]):.6f}'
          f'   面积 {area(hull):.6f}')
    # 45° 放判定：正方形的两条对角线是否沿格边（水平/竖直）
    d = sorted((side_len(hull[0], hull[2]), side_len(hull[1], hull[3])), reverse=True)
    horiz = any(abs(hull[t][1] - hull[(t + 1) % 4][1]) < 1e-9
                and abs(hull[t][0] - hull[(t + 1) % 4][0]) > 1e-9
                for t in range(4))
    print(f'  对角线长 {d[0]:.6f} / {d[1]:.6f}（相等=正方形）')
    print(f'  含水平/竖直的边（= 对角线沿格边）：{horiz}  → 45° 放'
          f'（边不沿格边，只有对角线沿格边）')
    cx = sum(p[0] for p in hull) / 4
    cy = sum(p[1] for p in hull) / 4
    print(f'  正方形中心 = ({cx}, {cy})')

    print('\n  旋转 90° 后：')
    r = rot90(hull, (cx, cy))
    print(f'    顶点 = {[(round(x, 6), round(y, 6)) for (x, y) in r]}')
    print(f'    与原四边形同集合：{set(map(tuple, r)) == set(map(tuple, hull))}'
          f'  （正方形有 90° 对称，形状不变）')
    # 公共边在新配对下的角色
    newpair = sorted(shared)
    vertical = abs(newpair[0][0] - newpair[1][0]) < 1e-9
    print(f'    原公共边 {newpair} 是否竖直：{vertical}'
          f'  → 公共边成了竖直对角线')
    E = mi_vertices(0, 0, 'E')
    W = mi_vertices(0, 1, 'W')
    e_hull = convex_hull(poly(E) + poly(W))
    print(f'    对照：E(0,0)+W(0,1) 并集 = {poly(e_hull)}  是正方形：'
          f'{is_square(e_hull)}')
    print('    → 转 90° 等价于：把「上下配对（S+N）」改成「左右配对（E+W）」')


def G4():
    print('\n' + '=' * 70)
    print('G4  度量对照：45° 正方形（mi 侧） vs 菱形胞（tri 侧）')
    print('=' * 70)
    E = mi_vertices(0, 0, 'E')
    W = mi_vertices(0, 1, 'W')
    sq = convex_hull(poly(E) + poly(W))
    sq_area = area(sq)
    sq_side = side_len(sq[0], sq[1])

    # tri 菱形胞 ▲(0,0)+▼(0,0)，用纯数学朝向（y 轴向上）算
    e1 = (1.0, 0.0)
    e2 = (0.5, math.sqrt(3) / 2)

    def V(a, b):
        return (a * e1[0] + b * e2[0], a * e1[1] + b * e2[1])

    up = [V(0, 0), V(1, 0), V(0, 1)]
    dn = [V(1, 0), V(1, 1), V(0, 1)]
    rh = convex_hull(up + dn)
    rh_area = area(rh)
    rh_side = min(side_len(rh[t], rh[(t + 1) % 4]) for t in range(4))

    def angles(vs):
        out = []
        n = len(vs)
        for t in range(n):
            a = vs[(t - 1) % n]
            b = vs[t]
            c = vs[(t + 1) % n]
            v1 = (a[0] - b[0], a[1] - b[1])
            v2 = (c[0] - b[0], c[1] - b[1])
            dot = v1[0] * v2[0] + v1[1] * v2[1]
            n1 = math.hypot(*v1)
            n2 = math.hypot(*v2)
            out.append(round(math.degrees(math.acos(
                max(-1.0, min(1.0, dot / (n1 * n2))))), 4))
        return out

    print(f'  mi 45°正方形 : 边长 {sq_side:.6f}  面积 {sq_area:.6f}  '
          f'内角 {angles(sq)}')
    print(f'  tri 菱形胞   : 边长 {rh_side:.6f}  面积 {rh_area:.6f}  '
          f'内角 {angles(rh)}')
    print(f'  面积比 = {sq_area / rh_area:.6f}   边长比 = {sq_side / rh_side:.6f}')
    print(f'  √3/2 = {math.sqrt(3) / 2:.6f}（菱形胞面积，斜边=1）')
    print('  → 两者不是同一形状：正方形 90°/90°/90°/90° 对 菱形 60°/120°/60°/120°')
    print('  → 面积也不相等（1/2 对 √3/2），所以「旋转 90°」不是等距变换；')
    print('    若要接上 tri，必须是仿射（把正方形压成 60° 菱形）的意思。')


def main():
    G1_G2_G3()
    G4()


if __name__ == '__main__':
    main()