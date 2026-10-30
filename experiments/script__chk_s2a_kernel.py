# -*- coding: utf-8 -*-
"""S2a 縫幾何內核驗證：board_view 新方法 vs 引擎真值。

檢查項：
  1 seam_candidates 數量 = distinct rank 邊界（碎三角 121，舊 all_gaps 390）
  2 contact_edges 與引擎鄰接表集合相等（66）
  3 候選縫 ↔ legal_moves 活縫：活縫必在候選裡；候選 t 經 _line_to_t  round-trip
  4 seam_segments 非空且落在點擊附近（gap_candidates 命中已知活縫）
  5 gap_candidates 排序鍵與共享邊覆蓋（一條邊被多條候選縫共享）
  6 四形態全跑（square/tri/mi/shatter）不拋
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import make_board  # noqa: E402
from engine.registry import mi_spec, square_spec, tri_spec  # noqa: E402
from engine.shatter_geometry import shatter_spec  # noqa: E402
from gui.board_view import SpecPolygonView  # noqa: E402

fails = []


def check(cond, msg):
    print(f"  {'ok' if cond else 'FAIL'}: {msg}")
    if not cond:
        fails.append(msg)


# ---------- 碎三角主戰場 ----------
board = make_board('shatter')
view = SpecPolygonView(board.spec, cell_size=60.0)
origin = view.origin_of(board, 0.0)

print("== 1 候選縫收斂（390 → distinct 邊界）==")
cands = view.seam_candidates(board)
print(f"  候選縫 {len(cands)} 條")
# 舊 all_gaps 口徑（逐整數 t）對照
old = []
for fam in board.spec.seam_families:
    vals = {fam.rank_of(k[0], k[1]) for k in board.keys}
    lo, hi = min(vals), max(vals)
    for t in range(lo + 1, hi + 1):
        old.append((fam.name, (t - 1) / fam.line_scale))
print(f"  舊 all_gaps 口徑 {len(old)} 條")
check(len(cands) == 121, f"候選縫 == 121（實測 {len(cands)}）")
check(len(cands) < len(old), f"候選縫 < 舊口徑（{len(cands)} vs {len(old)}）")
check(len(set(cands)) == len(cands), "候選縫無重複")

print("== 2 接觸邊 vs 引擎鄰接表 ==")
edges = view.contact_edges(board, origin)
print(f"  接觸邊 {len(edges)} 條")
# 引擎鄰接：對每塊列 neighbor point 差集合；接觸邊給的是「共邊」對
adj_pairs = set()
bmap = board.block_map
for k in board.keys:
    for d in board.spec.lattice.adjacency[
            board.spec.lattice and __import__('engine.shatter_geometry',
                                              fromlist=['x'])._reduce_shatter(k[0])]:
        nb = (k[0][0] + d[0], k[0][1] + d[1])
        for ok in board.keys:
            if ok[0] == nb:
                adj_pairs.add(tuple(sorted([k, ok])))
ce_pairs = {tuple(sorted([a, b])) for (a, b), _seg in edges}
check(len(ce_pairs) == 66, f"接觸邊去重後 == 66（實測 {len(ce_pairs)}）")
check(ce_pairs == adj_pairs,
      f"接觸邊集合 == 引擎鄰接邊集合（差 {len(ce_pairs ^ adj_pairs)}）")

print("== 3 候選縫 ↔ legal_moves 活縫 ==")
moves = board.legal_moves(1)
live = {(m.family, m.t) for m in moves}
print(f"  合法移動 {len(moves)} 條，涉及 (族, t) {len(live)} 個")
# 候選 t = distinct rank 邊界 v 的首個整數 v+1（legal_moves 口径）
cand_t = {}
for fam in board.spec.seam_families:
    vals = sorted({fam.rank_of(k[0], k[1]) for k in board.keys})
    for v in vals[:-1]:
        cand_t[(fam.name, v + 1)] = v / fam.line_scale
missing = {ft for ft in live if ft not in cand_t}
check(not missing, f"活縫全在候選裡（缺 {sorted(missing)[:4]}）")
# round-trip：候選 line 經 _line_to_t 還原 t
from engine.adapter import create_adapter_puzzle  # noqa: E402
g = create_adapter_puzzle('shatter', 4, 4, 1)
bad_rt = []
for (fname, t), line in cand_t.items():
    if g._line_to_t(fname, line) != t:
        bad_rt.append((fname, line, t))
check(not bad_rt, f"line → t round-trip 全對（錯 {bad_rt[:3]}）")
# 候選縫 ↔ view.seam_candidates 完全一致
vc = set(view.seam_candidates(board))
bc = {(f, (int(l) if l == int(l) else l)) for (f, _t), l in cand_t.items()}
check(vc == bc, f"seam_candidates == 推導候選（差 {len(vc ^ bc)}）")

print("== 4/5 gap_candidates 命中與共享邊 ==")
# 點在一條真實足跡線段的中點上，必把該縫收進候選
hit_ok = 0
tested = 0
first_ok = 0
for (fname, line) in cands:
    segs = view.seam_segments(board, fname, line, origin)
    if not segs:
        continue
    tested += 1
    s = segs[0]
    mx, my = (s[0][0] + s[1][0]) / 2, (s[0][1] + s[1][1]) / 2
    got = view.gap_candidates(mx, my, board, origin)
    names = [(gt, ln) for gt, ln, _d in got]
    if (fname, line) in names:
        hit_ok += 1
    if names and names[0] == (fname, line):
        first_ok += 1
print(f"  點足跡線段中點：{hit_ok}/{tested} 收進候選，{first_ok} 條排第一")
check(hit_ok == tested and tested > 0,
      f"點縫足跡必命中該縫（{hit_ok}/{tested}）")
# 共享邊覆蓋統計：每條接觸邊屬於幾條候選縫
cover = {}
for (a, b), _seg in edges:
    pass
ranks = {}
for fam in board.spec.seam_families:
    ranks[fam.name] = {k: fam.rank_of(k[0], k[1]) for k in board.keys}
cnt = {}
for (a, b), _seg in edges:
    for fname, rk in ranks.items():
        ra, rb = rk[a], rk[b]
        if ra == rb:
            continue
        lo, hi = min(ra, rb), max(ra, rb)
        for (f2, t), line in cand_t.items():
            if f2 == fname and lo < t <= hi:
                cnt[(fname, line)] = cnt.get((fname, line), 0) + 1
multi = {k: v for k, v in cnt.items() if v > 1}
print(f"  被多條邊覆蓋的候選縫 {len(multi)} 個（樣本 "
      f"{sorted(multi.items(), key=lambda kv: -kv[1])[:3]}）")
check(len(cnt) >= 100, f"覆蓋統計到的候選縫數 {len(cnt)}")

print("== 6 四形態全跑不拋 ==")
for tag, b in [('square', make_board('square', m=4, n=4)),
               ('tri', make_board('tri', k=4)),
               ('mi', make_board('mi', m=3, n=3)),
               ('shatter_lattice', make_board('shatter_lattice'))]:
    try:
        v = SpecPolygonView(b.spec, cell_size=60.0)
        og = v.origin_of(b, 0.0)
        cs = v.seam_candidates(b)
        es = v.contact_edges(b, og)
        gc = v.gap_candidates(og[0] + 30, og[1] + 30, b, og)
        ss = v.seam_segments(b, cs[0][0], cs[0][1], og) if cs else []
        check(True, f"{tag}: 候選 {len(cs)} / 邊 {len(es)} / "
                    f"點擊候選 {len(gc)} / 首縫足跡 {len(ss)}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        check(False, f"{tag} 拋異常 {type(e).__name__}: {e}")

print()
if fails:
    print(f"共 {len(fails)} 項失敗")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("全部通過")
