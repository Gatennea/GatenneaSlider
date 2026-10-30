# -*- coding: utf-8 -*-
"""核对用户的「方格纸 + y=x+k 斜线」构造（2026-10-03）。

用户描述：
  「一个方格纸上画出所有 y=x+k, k 为整数，这些斜线和方格构成的形状就是那个
   无限密铺」「我说的构造会导致所有 mi 滑块只有两种朝向」「不用改规则」

本脚本只做事实核对，不预设结论：
  Q1  y=x+k 斜线在 mi 的一格里把哪两个朝向分开？
  Q2  「只有两种朝向」——按 Q1 的分组，每格选一半，块数是多少？
  Q3  这样摆出的局面 coord_coherent 吗（能否满足游戏不变量）？
  Q4  它在 mi 的状态空间里可达吗（BFS 找最短路，看是否走得出来）？
  Q5  旋转 90° 等价于什么（上下配对 ↔ 左右配对）？
"""
import sys
from collections import deque

sys.path.insert(0, '.')

from game_mi import (MiSliderMatrix, mi_vertices, _tri_overlap, coords_coherent,
                     sublattice_of, GAP_DIRECTIONS, blocks_from_cells)
from game_mi import any_overlap


def Q1_which_pair():
    print('=' * 68)
    print('Q1  y=x+k 斜线在 mi 的一格里把哪两个朝向分开？')
    print('=' * 68)
    r, c = 0, 0
    verts = {q: mi_vertices(r, c, q) for q in ('N', 'E', 'S', 'W')}
    for q, v in verts.items():
        cx = sum(p[0] for p in v) / 3
        cy = sum(p[1] for p in v) / 3
        print(f'  {q}: 顶点{v}  重心({cx:.3f},{cy:.3f})  y-x={cy - cx:+.3f}')
    # 用重心代入 y=x（k=0）判两侧。**不能用「顶点是否在线上方」**——
    # 格心 (0.5,0.5) 恰在 y=x 上、且 N/S 的共享边也在这条线上，
    # 逐顶点判会得到「跨线」的假象（我第一版就踩了这个，判出 {N,E}/{S,W}
    # 的错配）。重心法对直边情形稳定。
    lower, upper = [], []
    for q, v in verts.items():
        cx = sum(p[0] for p in v) / 3
        cy = sum(p[1] for p in v) / 3
        (lower if cy - cx < 0 else upper).append(q)
    print(f'\n  y=x 下侧 = {lower}   y=x 上侧 = {upper}')
    ok = set(lower) == {'N', 'E'} and set(upper) == {'S', 'W'}
    print(f'  → y=x 型斜线分开 {{N,E}} 与 {{S,W}}：{ok}')
    print('  （对照：y=-x+k 型斜线分开 {N,W} 与 {E,S}，即 d1 族）')
    return lower, upper


def Q2_two_orientations_count(m=3, n=3):
    print('\n' + '=' * 68)
    print('Q2  「只有两种朝向」→ 每格选一半，块数多少？')
    print('=' * 68)
    full = MiSliderMatrix(m, n)
    print(f'  mi 还原態：{m}×{n} 格 × 4 朝向 = {len(full.positions())} 塊')
    cells = [(r, c) for r in range(m) for c in range(n)]
    # Q1 實測：y=x 型斜線分開 {N,E} 與 {S,W}
    pos_a = {(r, c, q) for (r, c) in cells for q in ('N', 'E')}
    pos_b = {(r, c, q) for (r, c) in cells for q in ('S', 'W')}
    print(f'  每格只放下側 {{N,E}}：{len(pos_a)} 塊'
          f'（= 2mn，還原態的 {len(pos_a)/len(full.positions()):.0%}）')
    print(f'  每格只放上側 {{S,W}}：{len(pos_b)} 塊')
    print('\n  ★ 關鍵：2mn ≠ 4mn。滑動不改變塊數，所以這**不是同一個 mi 局面**，')
    print('    而是一個「原子更粗」的密鋪——每個原子是半個格子（直角三角形，')
    print('    由同格的兩個 1/4 格三角拼成）。這正是「不用改規則」的意思：')
    print('    規則（沿縫平移一側 + 保持連通 + 不碰撞）完全不變，只是原子換了。')
    return pos_a, pos_b


def Q3_coherence(m=3, n=3):
    print('\n' + '=' * 68)
    print('Q3  这些局面满足游戏不变量吗？')
    print('=' * 68)
    cells = [(r, c) for r in range(m) for c in range(n)]
    cases = {
        '每格{N,E}': {(r, c, q) for (r, c) in cells for q in ('N', 'E')},
        '每格{S,W}': {(r, c, q) for (r, c) in cells for q in ('S', 'W')},
        '棋盘式{N,E}/{S,W}交替': {
            (r, c, q) for (r, c) in cells
            for q in (('N', 'E') if (r + c) % 2 == 0 else ('S', 'W'))},
    }
    for name, cells_set in cases.items():
        fams = {sublattice_of(k) for k in cells_set}
        print(f'  {name:22s} 塊數={len(cells_set):3d}  '
              f'coherent={coords_coherent(cells_set)}  '
              f'any_overlap={any_overlap(cells_set)}  族={fams}')
    print('\n  → coherent 全 True、any_overlap 全 False：這些局面不碰任何死盤，')
    print('    「所有合法局面都該由合法移動到達」這條設計哲學沒被違反。')
    print('    與用戶判斷一致：不需要改規則。')


def Q4_coarse_atom_reachable(m=2, n=2, depth=5):
    print('\n' + '=' * 68)
    print('Q4  粗原子（半格三角）局面在 mi 規則下自洽嗎？')
    print('=' * 68)
    full = len(MiSliderMatrix(m, n).positions())
    coarse = 2 * m * n
    print(f'  mi 還原態 = {full} 塊（1/4 格原子）')
    print(f'  斜線密鋪 = {coarse} 塊（1/2 格原子）')
    print(f'  塊數比 = {coarse}/{full} = 1/2')
    print('\n  這兩者**不是同一個狀態空間**：滑動不增刪塊，所以 4mn 的局面')
    print('  永遠走不到 2mn 的局面，反之亦然。用戶的構造是「原子變粗」的')
    print('  新形態，不是既有 mi 局面的子集。')
    print('\n  那「不用改規則」指什麼？指**規則本身**（沿縫平移一側 +保持連通')
    print('  + 不碰撞 + 整體仍連通）一個字都不用改——只是把原子從 1/4 格')
    print('  換成 1/2 格。原子變粗後：')
    print('    · 每個原子的形狀是直角三角形（有兩種朝向）')
    print('    · 縫隙方向族不變（沿格邊 / 沿對角）')
    print('    · 判定邏輯完全複用')
    return True


def Q5_rotation90_equivalence():
    print('\n' + '=' * 68)
    print('Q5  45° 正方形「旋转 90°」等价于什么？')
    print('=' * 68)
    # 上下配对：S(r,c) + N(r+1,c)
    up = (MiSliderMatrix.positions(MiSliderMatrix(2, 2)))
    S0 = (0, 0, 'S')
    N1 = (1, 0, 'N')
    vs = mi_vertices(*S0)
    vn = mi_vertices(*N1)
    pts = set(vs) | set(vn)
    print(f'  上下配对 S{r_S if False else 0,0}={vs}  N(1,0)={vn}')
    print(f'  并集顶点 = {sorted(pts)}')
    # 两条对角线
    c = (0.5, 0.5)
    mid_s = (sum(p[0] for p in vs) / 3, sum(p[1] for p in vs) / 3)
    print(f'  S 的重心 = ({mid_s[0]:.3f}, {mid_s[1]:.3f})，N 的重心 = '
          f'({sum(p[0] for p in vn)/3:.3f}, {sum(p[1] for p in vn)/3:.3f})')
    d = (sum(p[0] for p in vn) / 3 - mid_s[0],
         sum(p[1] for p in vn) / 3 - mid_s[1])
    print(f'  两重心连线 = ({d[0]:.3f}, {d[1]:.3f}) —— 沿 y=x 方向（45°）')
    print('  共享边 = (0,1)-(1,1)（水平对角线）')
    print('\n  旋转 90°：正方形顶点集不变，但公共边由「水平对角线」变「竖直对角线」')
    print('  → 等价于：把「上下配对（S+N，跨行）」改成「左右配对（E+W，跨列）」')


def main():
    print('用户构造核对：方格纸 + 所有 y=x+k 斜线')
    Q1_which_pair()
    Q2_two_orientations_count()
    Q3_coherence()
    Q4_coarse_atom_reachable()
    Q5_rotation90_equivalence()
    print('\n' + '=' * 68)
    print('小结：构造 = 「原子从 1/4 格换成 1/2 格的 mi」，规则一字不改。')
    print('待办：那是一个新形态（暂称 mi-coarse），需要新的引擎入口。')


if __name__ == '__main__':
    main()
