# -*- coding: utf-8 -*-
"""碎三角真实缝几何地面真值 v2（S2 前置实证）。

修正 v1 的坐标 bug：顶点 (kx,my) = LOCAL顶点 - LOCAL质心 + P/3 是**有理数**
（分母 3），不能 round 成整数；只有最终 rank = dot(coeffs, 顶点) 才是
可 round 的整数（贴边时精确等于 t）。

回答：
  Q1  哪些 t 真的有合法移动（legal_moves 反证）——已知：每族 5 条，共 15 缝。
  Q2  真实缝的线 {rank=t} 是否恰好沿 Tile 边（顶点 rank 精确 = t）？
  Q3  假缝（有候选无移动）的线是否切进块内部（顶点 rank 跨 t 两侧）？
  Q4  绿底缝（G_*，恒 inert）的贴边情况——它们贴边却无移动，说明
      「贴边」只是必要不充分条件，还需 is_valid_gap/seam_clear 语义。

坐标约定：P = 3×质心（(kx,my) 系统，整数）；顶点 (kx,my) 有理；
rank = dot(coeffs, (kx,my))；平面 (vx,vy) → (kx,my) = (vx·2/√3, vy·2)。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.registry import make_board  # noqa: E402
from engine.shatter_geometry import _polygon_at  # noqa: E402

SQ3 = math.sqrt(3.0)
TOL = 1e-6


def vrank(fam, vx, vy):
    """平面顶点的缝坐标 rank（有理数的浮点近似，误差 ~1e-15）。"""
    return fam.coeffs[0] * (vx * 2.0 / SQ3) + fam.coeffs[1] * (vy * 2.0)


def vdir(fam, ax, ay, bx, by):
    """边方向是否平行于该族允许的平移方向（平面角，叉积判据）。"""
    dpx, dpy = (bx - ax) * 2.0 / SQ3, (by - ay) * 2.0   # 边方向→(kx,my)
    for pv in fam.parallel:
        cross = abs(dpx * pv[1] - dpy * pv[0])
        dot = dpx * pv[0] + dpy * pv[1]
        if cross <= TOL * max(1.0, abs(dot)):
            return True
    return False


def main():
    board = make_board('shatter')
    spec = board.spec
    keys = board.keys
    print(f"板型 {spec.name}：{len(keys)} 块，{len(spec.seam_families)} 缝族")

    moves1 = board.legal_moves(1)
    real = {}
    for m in moves1:
        real.setdefault(m.family, set()).add(m.t)
    print(f"legal_moves(1) = {len(moves1)} 个移动")

    allpolys = {k: _polygon_at(k[0], k[1]) for k in keys}

    for fam in spec.seam_families:
        vals = {k: fam.rank_of(k[0], k[1]) for k in keys}
        lo, hi = min(vals.values()), max(vals.values())
        cand = list(range(lo + 1, hi + 1))
        rt = set(real.get(fam.name, set()))
        print(f"\n== 族 {fam.name} coeffs={fam.coeffs} parallel={fam.parallel} ==")
        print(f"  rank [{lo},{hi}] 候选 {len(cand)} 真实 {len(rt)}：{sorted(rt)}")

        edge_on = {}      # t -> 贴边数（顶点 rank 精确 = t 且方向平行）
        cut = {}          # t -> 被切块数（顶点 rank 跨 t 两侧）
        for k, poly in allpolys.items():
            n = len(poly)
            vr = [vrank(fam, vx, vy) for vx, vy in poly]
            for t in cand:
                below = sum(1 for r in vr if r < t - TOL)
                above = sum(1 for r in vr if r > t + TOL)
                if below and above:
                    cut[t] = cut.get(t, 0) + 1
            for i in range(n):
                ax, ay = poly[i]
                bx, by = poly[(i + 1) % n]
                if not vdir(fam, ax, ay, bx, by):
                    continue
                ra, rb = vr[i], vr[(i + 1) % n]
                if abs(ra - rb) > TOL:
                    continue
                tr = round(ra)
                if abs(ra - tr) <= TOL and tr in cand:
                    edge_on[tr] = edge_on.get(tr, 0) + 1

        rts = sorted(rt)
        miss = [t for t in rts if edge_on.get(t, 0) == 0]
        fake_edge = [t for t in cand if t not in rt and edge_on.get(t, 0) > 0]
        fake_cut = [t for t in cand if t not in rt and cut.get(t, 0) > 0]
        fake_clean = [t for t in cand
                      if t not in rt and edge_on.get(t, 0) == 0
                      and cut.get(t, 0) == 0]
        print(f"  Q2 真实 t 不贴边：{miss}")
        print(f"  Q3 假缝切块：{len(fake_cut)}/{len(cand)-len(rt)} 个；"
              f"假缝贴边（ inert 族才有）：{len(fake_edge)} 个 {fake_edge[:10]}")
        print(f"     假缝既不贴边也不切块：{len(fake_clean)} 个 {fake_clean[:10]}")
        # 贴边 t 的全集 vs 真实 t：差集就是「贴边但引擎不给移动」的
        all_edge = sorted(t for t in cand if edge_on.get(t, 0) > 0)
        print(f"     贴边 t 全集 {len(all_edge)}：{all_edge}")
        # 真实缝的贴边数分布（一条缝被几对块共享）
        print(f"     真实缝贴边数：{ {t: edge_on.get(t, 0) for t in rts} }")


if __name__ == '__main__':
    main()
