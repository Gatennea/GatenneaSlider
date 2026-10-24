# -*- coding: utf-8 -*-
"""碎三角「直线缝」几何地面真值探测（不依赖引擎 rank/缝族模型）。

目的：回答唯一一个问题——**这个 48 块盘面里，哪些直线能干净地切开它、
并且切开后的两侧能沿这条线真的滑动（不重叠、仍连通）**。

判据全部用真实多边形算，绝不复用引擎的缝抽象（上一轮的错误正是
「用引擎自己的模型验证引擎自己」）：

  1. 候选线：过块顶点的直线（方向取密铺里出现的边方向）。
  2. 合法切割：**没有任何块被线劈开**（该块三顶点不跨线两侧）。
  3. 两侧非空。
  4. 滑动：沿线的晶格步长平移被选侧，要求
       · 与被选侧以外的块**零正面积重叠**（SAT）；
       · 全体块**仍单一连通**（按共享边判定）；
       · 平移后与被选侧以外仍有**共享边**（否则两半脱开）。

输出：每个方向下的全部合法直线 + 可行步长。这是重写缝族的唯一依据。
"""
import sys
from math import gcd

sys.path.insert(0, '.')

from engine.shatter_geometry import SQ3, _goal_blocks, _polygon_at  # noqa: E402

EPS = 1e-9


def to_p(v):
    """平面顶点 → 精确整数点 P=(kx,my)：plane(P)=(P_x√3/6, P_y/6)。"""
    return (round(v[0] * 2 / SQ3), round(v[1] * 2))


def to_plane(p):
    return (p[0] * SQ3 / 6.0, p[1] / 6.0)


def cross(v, p):
    """P 坐标叉积（与平面叉积同号、差正因子 √3）。"""
    return v[0] * p[1] - v[1] * p[0]


def canon_dir(dx, dy):
    g = gcd(abs(dx), abs(dy)) or 1
    dx //= g
    dy //= g
    if dx < 0 or (dx == 0 and dy < 0):
        dx, dy = -dx, -dy
    return (dx, dy)


def sat_overlap(t1, t2):
    """正面积重叠（贴合不算）。"""
    for tri in (t1, t2):
        for i in range(3):
            e = (tri[(i + 1) % 3][0] - tri[i][0], tri[(i + 1) % 3][1] - tri[i][1])
            ax = (-e[1], e[0])
            p1 = [ax[0] * v[0] + ax[1] * v[1] for v in t1]
            p2 = [ax[0] * v[0] + ax[1] * v[1] for v in t2]
            if min(p1) >= max(p2) - EPS or min(p2) >= max(p1) - EPS:
                return False
    return True


def translate(tri, dx, dy):
    return tuple((v[0] + dx, v[1] + dy) for v in tri)


def n_shared_edges(t1, t2):
    s1 = {frozenset((t1[i], t1[(i + 1) % 3])) for i in range(3)}
    s2 = {frozenset((t2[i], t2[(i + 1) % 3])) for i in range(3)}
    return len(s1 & s2)


def connected(tris):
    n = len(tris)
    if n == 0:
        return True
    seen = {0}
    stack = [0]
    while stack:
        i = stack.pop()
        for j in range(n):
            if j not in seen and n_shared_edges(tris[i], tris[j]) >= 1:
                seen.add(j)
                stack.append(j)
    return len(seen) == n


def main():
    keys = [(b.point, b.orient) for b in _goal_blocks()]
    polys = {k: [to_p(v) for v in _polygon_at(*k)] for k in keys}
    print(f"块数 = {len(keys)}")

    # ---- 边方向统计 ----
    dirs = {}
    for k, ps in polys.items():
        for i in range(3):
            a, b = ps[i], ps[(i + 1) % 3]
            d = canon_dir(b[0] - a[0], b[1] - a[1])
            dirs.setdefault(d, 0)
            dirs[d] += 1
    print("\n== 边方向分布（P 坐标原始方向，已归一化符号）==")
    for d in sorted(dirs, key=lambda t: (-dirs[t], t)):
        # 平面角
        import math
        ang = math.degrees(math.atan2(d[1], d[0] * SQ3)) % 180.0
        print(f"  {d}: {dirs[d]:3d} 条   平面角≈{ang:.1f}°")

    # ---- 枚举合法直线切割 ----
    print("\n== 合法直线切割（无块被劈开）与可行步长 ==")
    results = []
    for v, cnt in sorted(dirs.items(), key=lambda kv: -kv[1]):
        if cnt < 6:
            continue
        cs = sorted({cross(v, p) for ps in polys.values() for p in ps})
        for c in cs:
            straddle = 0
            side = {}
            for k, ps in polys.items():
                vals = [cross(v, p) - c for p in ps]
                if min(vals) < 0 < max(vals):
                    straddle += 1
                    break
                side[k] = 1 if min(vals) > 0 else (-1 if max(vals) < 0 else 0)
            if straddle:
                continue
            lo = [k for k, s in side.items() if s < 0]
            hi = [k for k, s in side.items() if s > 0]
            if not lo or not hi:
                continue
            results.append((v, c, lo, hi))

    # 去重/按方向输出，并对每个切割试步长
    import math
    shown = 0
    for v, c, lo, hi in results:
        # 步长：晶格向量 a(12,0)+b(6,18)，要求与线平行
        steps = []
        for a in range(-6, 7):
            for b in range(-6, 7):
                s = (12 * a + 6 * b, 18 * b)
                if s == (0, 0) or cross(v, s) != 0:
                    continue
                px, py = to_plane(s)
                steps.append((px * px + py * py, s))
        steps.sort()
        if not steps:
            continue
        best = None
        for mag2, s in steps[:6]:
            for sgn in (1, -1):
                sv = (s[0] * sgn, s[1] * sgn)
                dx, dy = to_plane(sv)
                moved = lo if len(lo) <= len(hi) else hi
                rest = hi if moved is lo else lo
                mv = [translate(polys[k], dx, dy) for k in moved]
                rs = [polys[k] for k in rest]
                bad = 0
                for t1 in mv:
                    for t2 in rs:
                        if sat_overlap(t1, t2):
                            bad += 1
                join = sum(1 for t1 in mv for t2 in rs if n_shared_edges(t1, t2) >= 1)
                conn = connected(mv + rs)
                if bad == 0 and conn and join > 0:
                    best = (sv, len(moved), len(rest), join, mag2)
                    break
            if best:
                break
        ang = math.degrees(math.atan2(v[1], v[0] * SQ3)) % 180.0
        tag = "OK" if best else "--"
        extra = (f"step={best[0]} 移{best[1]}块/留{best[2]}块 共边{best[3]}"
                 if best else "无可行步长")
        print(f"  [{tag}] dir={v} ({ang:5.1f}°) c={c:4d} "
              f"侧块数 {len(lo):2d}|{len(hi):2d}  {extra}")
        shown += 1
    print(f"\n合法切割总数 = {len(results)}")


if __name__ == '__main__':
    main()
