# -*- coding: utf-8 -*-
"""S2 探索②：容差匹配下的共边事实 + 邻接 vs 几何共边的一致性。

探索①发现「共边对 = 34」远低于三角剖分的期望值（~60）——疑点是
_polygon_at 的浮点平移让同一顶点在两块里算出 slightly different 的值，
frozenset 精确相交漏掉了它们。本脚本用容差匹配重数，并与引擎的显式
邻接表（整数顶点精确判定）对照，回答：
  1 容差匹配的共边对是多少？引擎邻接表给出的盘内邻接边是多少？两者一致吗？
  2 容差匹配后，空足迹候选还有几个？
  3 活缝（15 条）的足迹覆盖多少条边？死缝的足迹呢？
  4 每条接触边被几个活缝共享？（点一条缝时真正的歧义面）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.registry import make_board
from gui.board_view import SpecPolygonView

VTOL = 1e-6

board = make_board('shatter')
spec = board.spec
view = SpecPolygonView(spec, cell_size=60.0)

polys = {}
for b in board.blocks:
    polys[(b.point, b.orient)] = tuple(tuple(round(c, 9) for c in v)
                                       for v in view.unit_polygon(b.point, b.orient))
keys = sorted(polys)


def close(a, b):
    return abs(a[0] - b[0]) <= VTOL and abs(a[1] - b[1]) <= VTOL


def shared_verts(pa, pb):
    """pa/pb 的公共顶点（容差匹配），返回公共顶点的代表列表。"""
    out = []
    for va in pa:
        for vb in pb:
            if close(va, vb) and not any(close(va, o) for o in out):
                out.append(va)
    return out


edges = []          # (ka, kb, [公共顶点...])
for i in range(len(keys)):
    for j in range(i + 1, len(keys)):
        common = shared_verts(polys[keys[i]], polys[keys[j]])
        if len(common) == 2:
            edges.append((keys[i], keys[j], common))
print(f"容差匹配共边对 = {len(edges)}")

# 引擎邻接表给出的盘内邻接边（点级）
keyset = set(board.keys)
adj_edges = set()
for k in board.keys:
    for q, _o in spec.lattice.neighbors_of(k[0], k[1]):
        kq = (q, dict((kk[0], kk[1]) for kk in board.keys).get(q))
        # 邻接表按点给邻居；同点最多一块（显式邻接模式），直接查盘面键
        for kk in board.keys:
            if kk[0] == q:
                pair = tuple(sorted([k, kk]))
                adj_edges.add(pair)
print(f"引擎邻接边（盘内，按点） = {len(adj_edges)}")

geo_pairs = {tuple(sorted([a, b])) for a, b, _c in edges}
print(f"几何共边 ⊆ 邻接？ {geo_pairs <= adj_edges}；邻接 ⊆ 几何共边？ {adj_edges <= geo_pairs}")
print(f"仅邻接有（非几何共边） = {len(adj_edges - geo_pairs)}；仅几何有 = {len(geo_pairs - adj_edges)}")
for p in list(adj_edges - geo_pairs)[:6]:
    print(f"   仅邻接: {p}")
for p in list(geo_pairs - adj_edges)[:6]:
    print(f"   仅几何: {p}")


# ---- 候选 + 足跡（几何共边）----
def candidates():
    out = []
    for fam in spec.seam_families:
        vals = {k: fam.rank_of(k[0], k[1]) for k in board.keys}
        for t in sorted(set(vals.values()))[1:]:
            out.append((fam, t))
    return out


cands = candidates()
empty_fp = []
for fam, t in cands:
    n = sum(1 for ka, kb, _c in edges
            if (fam.rank_of(ka[0], ka[1]) < t) != (fam.rank_of(kb[0], kb[1]) < t))
    if n == 0:
        empty_fp.append((fam.name, t))
print(f"\n候選 = {len(cands)}；容差匹配后空足迹候选 = {len(empty_fp)} {empty_fp}")

# ---- 活缝 ----
lm = board.legal_moves(1)
live = sorted({(m.family, m.t) for m in lm})
print(f"\n活缝 = {len(live)}: {live}")

live_edges = set()
for fam_name, t in live:
    fam = next(f for f in spec.seam_families if f.name == fam_name)
    for ei, (ka, kb, _c) in enumerate(edges):
        if (fam.rank_of(ka[0], ka[1]) < t) != (fam.rank_of(kb[0], kb[1]) < t):
            live_edges.add(ei)
print(f"活缝足迹覆盖的接触边 = {len(live_edges)}/{len(edges)}")

# 每条边被几个活缝共享
from collections import Counter
cnt = Counter()
for fam_name, t in live:
    fam = next(f for f in spec.seam_families if f.name == fam_name)
    for ei, (ka, kb, _c) in enumerate(edges):
        if (fam.rank_of(ka[0], ka[1]) < t) != (fam.rank_of(kb[0], kb[1]) < t):
            cnt[ei] += 1
print(f"每条边的活缝共享数分佈: {dict(Counter(cnt.values()))}")

# 活缝足迹大小
for fam_name, t in live:
    fam = next(f for f in spec.seam_families if f.name == fam_name)
    fp = [ei for ei, (ka, kb, _c) in enumerate(edges)
          if (fam.rank_of(ka[0], ka[1]) < t) != (fam.rank_of(kb[0], kb[1]) < t)]
    print(f"  活缝 ({fam_name}, {t}): 足跡 {len(fp)} 邊")

# 沒被任何活缝覆盖的边：点击它们应该「选不动」
dead_edges = [ei for ei in range(len(edges)) if ei not in live_edges]
print(f"\n不被任何活缝覆盖的接触边 = {len(dead_edges)}/{len(edges)}")
