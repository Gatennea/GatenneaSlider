# -*- coding: utf-8 -*-
"""碎三角板型（'shatter' 全 / 'shatter_lattice' 单位边）headless 可玩性验证。

执行：python test/_test_shatter.py
约定：脚本型回归（check 收集失败，退出码非 0 即失败），零 pygame。

**本文件在 2026-10-24 整体重写**（旧基线的「60 移 / 活缝清单 / 绿底缝恒
inert」全部作废）：旧基线是拿错误模型自证出来的，见下。

重写后钉死的三条公理（这是碎三角能不能玩的全部要害）：
  A1 缝是**直线**      —— 每条缝的全部接触边严格共线；且没有任何块被线劈开。
                          （旧实现逐整数 t 枚举，绝大多数 t 的线穿块内部，
                          画到盘面上就是锯齿缝。）
  A2 缝两侧能**真滑**  —— 沿缝平移的**中间位置**也不重叠。锯齿缝做不到：
                          它要靠两侧锯齿互相穿透才能"合上"，引擎只看端点
                          所以判合法，物理上根本推不动——这正是「折线根本
                          滑不动」的由来。
  A3 走法**两步可逆**  —— 每个合法移动都存在精确逆移动（安全打乱前提）。

覆盖：
  1 注册表            —— 两个预设已注册、缝族数 6 / 3。
  2 还原态构造        —— 48 块、is_solved、几何零重叠、单一连通。
  3 缝族/方向一致性   —— 每方向平行于所在缝族（f(d)=0）、方向表封闭。
  4 缝线是直线（A1）  —— 12 条缝、接触边严格共线、不劈块、两侧非空。
  5 合法移动与物理性  —— 非冻形；每个移动途中不重叠（A2）、落位不重叠、仍连通。
  6 每步可逆（A3）    —— 还原态全部合法移动都有精确逆移动。
  7 安全打乱          —— 打乱 N 步后反转撤销路径精确回到还原态。
  8 overlap 钩子      —— ① 不误杀相邻块；② 同址异形必判重叠。
  9 两个预设          —— 单位边预设走法 ⊆ 全集，且全集严格更多。
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import (  # noqa: E402
    board_types,
    frozen,
    make_board,
    safe_scramble,
    verify_path,
)
from engine.board import _connected_components  # noqa: E402
from engine.shatter_geometry import (  # noqa: E402
    _block_vertices,
    _overlap_hook,
    _polygon_at,
    _tri_overlap,
    _vertex_rank,
)

SQ3 = math.sqrt(3.0)
failures = []


def check(cond, msg):
    if cond:
        print(f"  ok: {msg}")
    else:
        failures.append(msg)
        print(f"  FAIL: {msg}")


def _overlap_pairs(keys):
    """任取两块做 SAT，返回正面积重叠的对（共边不算）。"""
    ks = list(keys)
    polys = {k: _polygon_at(k[0], k[1]) for k in ks}
    bad = []
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            if _tri_overlap(polys[ks[i]], polys[ks[j]]):
                bad.append((ks[i], ks[j]))
    return bad


def _plane_delta(d, frac=1.0):
    """C 坐标位移 → 平面位移（frac 可取小数，用于扫中间位置）。"""
    return (d[0] * SQ3 / 6.0 * frac, d[1] / 6.0 * frac)


def _translate(poly, dx, dy):
    return tuple((v[0] + dx, v[1] + dy) for v in poly)


# ======================================================================
print("== 1 注册表 ==")
types = board_types()
check('shatter' in types, f"'shatter' 已注册（当前: {types}）")
check('shatter_lattice' in types, "'shatter_lattice' 已注册")

b_full = make_board('shatter')
b_lat = make_board('shatter_lattice')
check(len(b_full.spec.seam_families) == 6,
      f"'shatter' 缝族数 = 6（实际 {len(b_full.spec.seam_families)}）")
check(len(b_lat.spec.seam_families) == 3,
      f"'shatter_lattice' 缝族数 = 3（实际 {len(b_lat.spec.seam_families)}）")
check([f.name for f in b_full.spec.seam_families]
      == ['h', 'd30', 'd60', 'v', 'd120', 'd150'],
      f"缝族按线方向命名（实际 {[f.name for f in b_full.spec.seam_families]}）")

# ======================================================================
print("== 2 还原态构造 ==")
check(b_full.block_count == 48, f"48 块（实际 {b_full.block_count}）")
check(b_full.is_solved(), "还原态 is_solved 真")
check(_overlap_pairs(b_full.keys) == [], "还原态几何零重叠")
check(len(_connected_components(b_full.keys, b_full.spec)) == 1, "还原态单一连通")
check(not b_full.translate((12, 0)).is_solved(),
      "整体平移判未还原（精确拼合语义生效）")

# ======================================================================
print("== 3 缝族/方向一致性 ==")
for b, tag in ((b_full, 'shatter'), (b_lat, 'shatter_lattice')):
    dir_set = set(b.spec.directions)
    bad = []
    for fam in b.spec.seam_families:
        for d in fam.parallel:
            if d not in dir_set:
                bad.append((fam.name, d, 'dir-not-listed'))
            if fam.coeffs[0] * d[0] + fam.coeffs[1] * d[1] != 0:
                bad.append((fam.name, d, 'not-parallel'))
    check(not bad, f"{tag} 每方向平行于所在缝族且 f(d)=0（异常 {bad}）")
check(len(set(b_full.spec.directions)) == len(b_full.spec.directions),
      "方向表无重复")
check(len(b_lat.spec.directions) == 6, "单位边预设 6 个方向")

# ======================================================================
print("== 4 缝线是直线（A1） ==")
from gui.board_view import SpecPolygonView  # noqa: E402

view = SpecPolygonView(b_full.spec, cell_size=40.0)
origin = view.origin_of(b_full)
cands = view.seam_candidates(b_full)
check(len(cands) == 12, f"还原态真实缝线 12 条（实际 {len(cands)}）")
by_fam = {}
for gt, ln in cands:
    by_fam.setdefault(gt, []).append(ln)
check(by_fam.get('d30') and len(by_fam['d30']) == 3
      and len(by_fam['v']) == 3 and len(by_fam['d150']) == 3,
      f"单位边三族各 3 条（实际 { {k: len(v) for k, v in by_fam.items()} }）")
check(len(by_fam.get('h', [])) == 1 and len(by_fam.get('d60', [])) == 1
      and len(by_fam.get('d120', [])) == 1,
      "0/60/120 三族各 1 条（盘面台阶形，各只切出一个角）")

worst_off = 0.0
no_footprint = 0
for gt, ln in cands:
    segs = view.seam_segments(b_full, gt, ln, origin)
    pts = [p for seg in segs for p in seg]
    if len(pts) < 2:
        no_footprint += 1
        continue
    x0, y0 = pts[0]
    far = max(pts, key=lambda p: (p[0] - x0) ** 2 + (p[1] - y0) ** 2)
    dx, dy = far[0] - x0, far[1] - y0
    L = math.hypot(dx, dy)
    off = max(abs((p[0] - x0) * dy - (p[1] - y0) * dx) / L for p in pts)
    worst_off = max(worst_off, off)
check(no_footprint == 0, f"每条候选缝都有接触边足迹（空足迹 {no_footprint} 条）")
check(worst_off < 1e-6,
      f"全部 12 条缝的足迹严格共线（最大垂距 {worst_off:.1e} 像素）")

# 线不劈块：每条缝的 t 不在任何块的顶点 rank 区间内部
cut_bad = []
for fam in b_full.spec.seam_families:
    ts = [t for t, _ln in b_full.spec.seam_lines(b_full, fam)]
    spans = [(min(rs), max(rs)) for rs in
             ([_vertex_rank(fam.coeffs, p) for p in _block_vertices(k)]
              for k in b_full.keys)]
    cut_bad += [(fam.name, t) for t in ts
                if any(lo < t < hi for lo, hi in spans)]
check(not cut_bad, f"没有任何缝线劈开块（违例 {cut_bad[:4]}）")

# ======================================================================
print("== 5 合法移动与物理性（A2） ==")
mv_full = b_full.legal_moves(1)
mv_lat = b_lat.legal_moves(1)
check(len(mv_full) > 0, f"还原态合法移动非空（{len(mv_full)} 个）")
check(len(mv_lat) > 0, f"单位边预设合法移动非空（{len(mv_lat)} 个）")
check(not frozen(b_full, 1), "不冻形")

# 5a 每个移动：两侧各非空、选中片整片在一侧
side_bad = []
for m in mv_full:
    fam = next(f for f in b_full.spec.seam_families if f.name == m.family)
    vals = {fam.rank_of(p, o) for p, o in m.moved}
    if m.side == -1 and not all(v < m.t for v in vals):
        side_bad.append((m.family, m.t, 'side-'))
    if m.side == 1 and not all(v >= m.t for v in vals):
        side_bad.append((m.family, m.t, 'side+'))
    if len(m.moved) >= b_full.block_count:
        side_bad.append((m.family, m.t, 'whole-board'))
check(not side_bad, f"选中片整片落在缝的一侧且非全盘（违例 {side_bad[:3]}）")

# 5b 物理性：平移**途中**（1/4、1/2、3/4）被移动侧与定侧零重叠。
#     这是「直线缝」的判定性证据——锯齿缝在这一步会大面积重叠。
mid_bad = []
for m in mv_full:
    dx, dy = _plane_delta(m.direction)
    moved0 = [_polygon_at(p, o) for p, o in m.moved]
    rest = [_polygon_at(p, o) for p, o in (b_full.keys - frozenset(m.moved))]
    for frac in (0.25, 0.5, 0.75):
        fx, fy = dx * frac, dy * frac
        hit = 0
        mv = [_translate(t, fx, fy) for t in moved0]
        for a in mv:
            for b in rest:
                if _tri_overlap(a, b):
                    hit += 1
        if hit:
            mid_bad.append((m.family, m.t, frac, hit))
check(not mid_bad,
      f"全部 {len(mv_full)} 个移动在途中位置都不重叠（违例 {mid_bad[:3]}）")

# 5c 落位：几何零重叠 + 单一连通
after_bad = []
for m in mv_full:
    nb = b_full.apply(m)
    if _overlap_pairs(nb.keys) or len(_connected_components(nb.keys, b_full.spec)) != 1:
        after_bad.append((m.family, m.t))
check(not after_bad, f"全部移动落位后零重叠且单一连通（违例 {after_bad[:3]}）")

# ======================================================================
print("== 6 每步可逆（A3） ==")
from engine.analysis import _find_inverse  # noqa: E402

n_inv = sum(1 for m in mv_full if _find_inverse(b_full, m, 1) is not None)
check(n_inv == len(mv_full),
      f"还原态全部 {len(mv_full)} 个合法移动都有精确逆移动（实际 {n_inv}）")

# ======================================================================
print("== 7 安全打乱（终态可解） ==")
SCRAMBLE = 10
rng = random.Random(20261024)
final, path, undo = safe_scramble(b_full, 1, SCRAMBLE, rng)
check(1 <= len(path) <= SCRAMBLE,
      f"安全打乱产出可逆路径（实际 {len(path)} 步）")
check(len(undo) == len(path), "每步记录撤销移动")
check(not final.is_solved(), "打乱终态不是还原态")
check(verify_path(b_full, path) == final, "路径重放与终态一致")
check(verify_path(final, tuple(reversed(undo))) == b_full,
      "反转撤销路径精确回到还原态（字面解法，终态确有解）")
check(_overlap_pairs(final.keys) == [], "打乱终态几何零重叠")

# ======================================================================
print("== 8 overlap 钩子（几何 SAT） ==")
kA = next(iter(b_full.keys))
pA, oA = kA
edge_map = {}
for k in b_full.keys:
    vs = _block_vertices(k)
    for i in range(3):
        a, c = vs[i], vs[(i + 1) % 3]
        e = (a, c) if a <= c else (c, a)
        edge_map.setdefault(e, []).append(k)
neighbour = next(((ks[0], ks[1]) for ks in edge_map.values() if len(ks) > 1), None)
check(neighbour is not None, "还原态存在共边相邻块")
if neighbour is not None:
    kA2, kB2 = neighbour
    check(_overlap_hook({(kB2[0], kA2[1])}, {kB2}) is True,
          "异形块平移到同址 → overlap 钩子判重叠（真拦截）")
    check(_overlap_hook({kA2}, {kB2}) is False,
          "共边相邻的两块 → overlap 判不重叠（不误杀）")

# ======================================================================
print("== 9 两个预设 ==")
moved_lat = {m.moved for m in mv_lat}
moved_full = {m.moved for m in mv_full}
check(moved_lat <= moved_full, "单位边预设的选中片 ⊆ 全集")
check(len(moved_full) > len(moved_lat),
      f"全集严格多于单位边预设（{len(moved_full)} vs {len(moved_lat)}）——"
      f"0/60/120 三族确实贡献走法（旧模型里它们恒 inert）")
check(len(mv_full) == 48,
      f"还原态 48 个合法移动 = 12 缝 × 2 侧 × 2 向（实际 {len(mv_full)}）")

# ======================================================================
print("\n" + ("全部通过" if not failures else f"{len(failures)} 项失败"))
if failures:
    for f in failures:
        print("  -", f)
    sys.exit(1)
