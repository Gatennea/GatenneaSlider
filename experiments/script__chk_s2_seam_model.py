# -*- coding: utf-8 -*-
"""S2 探索：碎三角盤面的「接觸邊界模型」事實核查。

要回答的問題（寫 code 前先驗證，不憑設計文檔的記憶）：
  1 還原態 48 塊的共邊對（兩塊恰有 2 個公共頂點 ⇒ 共邊）有多少條？
  2 各縫族的相鄰 rank 邊界（distinct ranks 的 distinct[1:]）有多少個候選？
  3 每個候選的「跨分區接觸邊」足跡是否非空？（連通性 ⇒ 有跨側邊？）
  4 候選裡有合法移動的（活縫）有幾個？legal_moves(1) 是不是 60 移？
  5 不同族的足跡會不會重疊（同一条接触边出现在多个候选里）？
  6 all_gaps()（引擎旧枚举）在还原态给多少个候选？
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.registry import make_board
from gui.board_view import SpecPolygonView

board = make_board('shatter')
spec = board.spec
view = SpecPolygonView(spec, cell_size=60.0)

print(f"塊數 = {board.block_count}")

# ---- 1 共邊對 ----
polys = {}
for b in board.blocks:
    polys[(b.point, b.orient)] = frozenset(view.unit_polygon(b.point, b.orient))
keys = sorted(polys)
edges = []
for i in range(len(keys)):
    for j in range(i + 1, len(keys)):
        common = polys[keys[i]] & polys[keys[j]]
        if len(common) == 2:
            edges.append((keys[i], keys[j], tuple(sorted(common))))
print(f"共邊對 = {len(edges)}")

# ---- 2/3 各族候選 + 足跡 ----
def candidates():
    out = []
    for fi, fam in enumerate(spec.seam_families):
        vals = {k: fam.rank_of(k[0], k[1]) for k in board.keys}
        distinct = sorted(set(vals.values()))
        for t in distinct[1:]:
            out.append((fi, fam, t))
    return out

cands = candidates()
print(f"\n各族相鄰 rank 邊界候選 = {len(cands)}")
per_fam = {}
for fi, fam, t in cands:
    per_fam.setdefault(fam.name, 0)
    per_fam[fam.name] += 1
print(f"各族候選數 = {per_fam}")

# 足跡：跨分區接觸邊
empty_fp = []
for fi, fam, t in cands:
    n = 0
    for ka, kb, _pts in edges:
        ra = fam.rank_of(ka[0], ka[1])
        rb = fam.rank_of(kb[0], kb[1])
        if (ra < t) != (rb < t):
            n += 1
    if n == 0:
        empty_fp.append((fam.name, t))
print(f"足跡為空的候選 = {len(empty_fp)} {empty_fp[:8]}")

# ---- 4 活縫 ----
lm = board.legal_moves(1)
live_seams = {(m.family, m.t) for m in lm}
print(f"\nlegal_moves(1) = {len(lm)} 移；活縫(族,t) = {len(live_seams)} 條")
live_fams = {}
for fam_name, t in live_seams:
    live_fams.setdefault(fam_name, 0)
    live_fams[fam_name] += 1
print(f"活縫按族 = {live_fams}")

# 候選 vs 活縫對照
dead = [(fam.name, t) for _fi, fam, t in cands if (fam.name, t) not in live_seams]
print(f"候選中死縫 = {len(dead)}/{len(cands)}")
dead_fams = {}
for fam_name, t in dead:
    dead_fams.setdefault(fam_name, 0)
    dead_fams[fam_name] += 1
print(f"死縫按族 = {dead_fams}")

# ---- 5 足跡重疊：同一条接触边被几个候选共享 ----
edge_use = {}
for fi, fam, t in cands:
    for ei, (ka, kb, _pts) in enumerate(edges):
        ra = fam.rank_of(ka[0], ka[1])
        rb = fam.rank_of(kb[0], kb[1])
        if (ra < t) != (rb < t):
            edge_use.setdefault(ei, []).append((fam.name, t))
multi = {ei: v for ei, v in edge_use.items() if len(v) > 1}
print(f"\n被多個候選共享的接觸邊 = {len(multi)}/{len(edges)}")
for ei, v in list(multi.items())[:10]:
    print(f"  邊{ei}: {v}")

# ---- 6 all_gaps ----
from engine.adapter import EngineGame
g = EngineGame(board, kind='shatter')
ag = g.all_gaps()
print(f"\nadapter.all_gaps() = {len(ag)} 個")
ag_live = [gp for gp in ag if (gp[0], g._line_to_t(*gp)) in live_seams]
print(f"其中活縫 = {len(ag_live)}")
