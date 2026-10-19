#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_analyze_isolated_dead.py — 「孤立死分量」数学结构分析（只读，不写任何文件）

分析对象：experiments/math_repro/full_A/<case>/ 下 C++ 引擎全量枚举落盘的状态图
（membership.bin 16B/态、boards.bin 32B/态、edges.bin 8B/边，布局见 read_full_A.py）。

术语（与 docs/math 口径一致）：
  可解      = flags bit1 (inB)，即能走回还原态
  真死局    = flags bit2 (sink，出度 0)
  吸引盆    = flags bit3 (inBasinTrue)，能沿前向边走到某个真死局
  孤立死    = 不可解 且 不在吸引盆（= flags bit6 two_not_touching，脚本用前两个条件独立算出并核对）

对每个 case 输出：
  §1 集合计数复现（与 summary.txt 交叉核对）
  §2 孤立死子图导出与「边界封闭」验证（边界的进出边数）
  §3 SCC 分解（迭代 Tarjan，另用 Kosaraju 独立复核；跑前先过随机小图自测）
  §4 分量刻画：个数、大小直方图、单环/带弦、分量内平均出度、分量间边
  §5 孤立死状态整体出度/入度/dist 分布
  §6 对称性：boards.bin 规范形唯一性、形状自身 D4 自对称（稳定子）分布、
            平移诱导颜色置换的恒等性验证、mod 类着色向量核对
  §7 sink 特征 + 「不可解但能到死局」对比

用法：
  D:/python/python.exe _analyze_isolated_dead.py            # 缺省 4_4_2 4_4_3
  D:/python/python.exe _analyze_isolated_dead.py 4_4_2      # 指定 case
"""
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent / "full_A"
DEFAULT_CASES = ["4_4_2", "4_4_3"]

# flags 位（read_full_A.py 口径）
F_IN_CONE = 1 << 0
F_IN_B = 1 << 1
F_SINK = 1 << 2
F_BASIN = 1 << 3
F_CONE_NOT_B = 1 << 4
F_EXT_PRED = 1 << 5
F_TWO_NOT = 1 << 6
F_SOLVABLE = 1 << 7


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------
def load_case(name):
    d = BASE / name
    if not d.is_dir():
        sys.exit(f"目录不存在: {d}")
    raw = np.fromfile(d / "membership.bin", dtype=np.uint8)
    n = raw.size // 16
    mem = raw.reshape(n, 16)
    ids = np.ascontiguousarray(mem[:, 0:4]).view(np.uint32).ravel()
    flags = mem[:, 4].copy()
    outdeg = np.ascontiguousarray(mem[:, 6:8]).view(np.uint16).ravel().astype(np.int64)
    indeg = np.ascontiguousarray(mem[:, 8:10]).view(np.uint16).ravel().astype(np.int64)
    dist = np.ascontiguousarray(mem[:, 10:14]).view(np.int32).ravel().astype(np.int64)
    boards = np.fromfile(d / "boards.bin", dtype=np.uint16).reshape(n, 16)
    ep = d / "edges.bin"
    edges = np.fromfile(ep, dtype=np.uint32).reshape(-1, 2).astype(np.int64)
    return {"name": name, "n": n, "ids": ids, "flags": flags,
            "outdeg": outdeg, "indeg": indeg, "dist": dist,
            "boards": boards, "edges": edges}


# ---------------------------------------------------------------------------
# CSR 邻接 + 迭代 Tarjan / Kosaraju
# ---------------------------------------------------------------------------
def build_csr(n, edges, node_subset=None):
    """edges: (E,2) 全图边；node_subset: 布尔掩码（None=全图，编号=全局 id）。
    给定子集时返回子图 CSR（局部编号 0..k-1，保留两端都在子集内的边）。
    返回 (indptr, indices)。"""
    if node_subset is None:
        u, v = edges[:, 0], edges[:, 1]
        m = n
    else:
        keep = node_subset[edges[:, 0]] & node_subset[edges[:, 1]]
        local = np.full(n, -1, dtype=np.int64)
        k = int(node_subset.sum())
        local[np.flatnonzero(node_subset)] = np.arange(k)
        u, v = local[edges[keep, 0]], local[edges[keep, 1]]
        m = k
    deg = np.bincount(u, minlength=m)
    indptr = np.zeros(m + 1, dtype=np.int64)
    np.cumsum(deg, out=indptr[1:])
    order = np.argsort(u, kind="stable")
    indices = v[order]
    return indptr, indices


def tarjan_scc(n, indptr, indices):
    """迭代版 Tarjan（显式栈，无递归）。返回 comp: (n,) 分量编号。"""
    index = np.full(n, -1, dtype=np.int64)
    low = np.zeros(n, dtype=np.int64)
    onstack = np.zeros(n, dtype=bool)
    scc_stack = []
    comp = np.full(n, -1, dtype=np.int64)
    counter = 0
    ncomp = 0
    for s in range(n):
        if index[s] != -1:
            continue
        index[s] = low[s] = counter
        counter += 1
        scc_stack.append(s)
        onstack[s] = True
        work = [(s, indptr[s])]
        while work:
            v, p = work[-1]
            advanced = False
            while p < indptr[v + 1]:
                w = indices[p]
                p += 1
                if index[w] == -1:
                    work[-1] = (v, p)
                    index[w] = low[w] = counter
                    counter += 1
                    scc_stack.append(w)
                    onstack[w] = True
                    work.append((w, indptr[w]))
                    advanced = True
                    break
                elif onstack[w] and index[w] < low[v]:
                    low[v] = index[w]
            if advanced:
                continue
            work[-1] = (v, p)
            if p >= indptr[v + 1]:
                work.pop()
                if work:
                    u = work[-1][0]
                    if low[v] < low[u]:
                        low[u] = low[v]
                if low[v] == index[v]:
                    while True:
                        w = scc_stack.pop()
                        onstack[w] = False
                        comp[w] = ncomp
                        if w == v:
                            break
                    ncomp += 1
    return comp, ncomp


def kosaraju_scc(n, indptr, indices):
    """迭代版 Kosaraju（独立实现，用于交叉复核 Tarjan）。"""
    # 反图 CSR：反邻接 rev[v] = {u : (u,v) ∈ E}（需要每条边的源点）
    src = np.repeat(np.arange(n, dtype=np.int64), np.diff(indptr))
    rudeg = np.bincount(indices, minlength=n)
    rindptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(rudeg, out=rindptr[1:])
    pos = rindptr[:-1].copy()
    rev = np.zeros(len(indices), dtype=np.int64)
    for i in range(len(indices)):
        w = indices[i]
        rev[pos[w]] = src[i]
        pos[w] += 1
    # 第一遍：正图 DFS 后序
    seen = np.zeros(n, dtype=bool)
    post = []
    for s in range(n):
        if seen[s]:
            continue
        seen[s] = True
        stack = [(s, indptr[s])]
        while stack:
            v, p = stack[-1]
            if p < indptr[v + 1]:
                stack[-1] = (v, p + 1)
                w = indices[p]
                if not seen[w]:
                    seen[w] = True
                    stack.append((w, indptr[w]))
            else:
                post.append(v)
                stack.pop()
    # 第二遍：反图按后序逆序
    comp = np.full(n, -1, dtype=np.int64)
    seen[:] = False
    ncomp = 0
    for s in reversed(post):
        if seen[s]:
            continue
        seen[s] = True
        comp[s] = ncomp
        stack = [s]
        while stack:
            v = stack.pop()
            for p in range(rindptr[v], rindptr[v + 1]):
                w = rev[p]
                if not seen[w]:
                    seen[w] = True
                    comp[w] = ncomp
                    stack.append(w)
        ncomp += 1
    return comp, ncomp


def scc_selftest(rounds=300, nmax=14):
    """随机小图上：Tarjan / Kosaraju / 暴力传递闭包三者分区必须一致。"""
    rng = np.random.default_rng(20261020)
    for _ in range(rounds):
        n = int(rng.integers(2, nmax + 1))
        e = int(rng.integers(0, 3 * n))
        edges = np.stack([rng.integers(0, n, e), rng.integers(0, n, e)], axis=1)
        indptr, indices = build_csr(n, edges)
        c1, k1 = tarjan_scc(n, indptr, indices)
        c2, k2 = kosaraju_scc(n, indptr, indices)

        def norm(c):
            groups = {}
            for i, ci in enumerate(c):
                groups.setdefault(ci, set()).add(i)
            return sorted(tuple(sorted(g)) for g in groups.values())

        # 暴力 ground truth：自反传递闭包后取互相可达类
        reach = np.zeros((n, n), dtype=bool)
        np.fill_diagonal(reach, True)
        if len(edges):
            reach[edges[:, 0], edges[:, 1]] = True
        for k in range(n):
            reach |= reach[:, k:k + 1] & reach[k:k + 1, :]
        gt = set()
        for i in range(n):
            for j in range(i, n):
                if reach[i, j] and reach[j, i]:
                    gt.add(tuple(sorted(np.flatnonzero(reach[i] & reach[:, i]).tolist())))
        brute = sorted(gt)
        assert norm(c1) == brute, ("Tarjan 与暴力不一致", n, edges)
        assert norm(c2) == brute, ("Kosaraju 与暴力不一致", n, edges)
    return True


# ---------------------------------------------------------------------------
# boards / 对称性工具
# ---------------------------------------------------------------------------
def board_cells(rows):
    """(16,) u16 行数组 -> 坐标集合 [(r,c)]。"""
    cells = []
    for r in range(16):
        m = int(rows[r])
        c = 0
        while m:
            if m & 1:
                cells.append((r, c))
            m >>= 1
            c += 1
    return cells


def normalize(cells):
    """平移归一：min r = min c = 0，返回 frozenset。"""
    r0 = min(r for r, _ in cells)
    c0 = min(c for _, c in cells)
    return frozenset((r - r0, c - c0) for r, c in cells)


def pack(cells):
    rows = [0] * 16
    for r, c in cells:
        rows[r] |= 1 << c
    return tuple(rows)


D8 = [
    lambda r, c: (r, c),
    lambda r, c: (r, -c),
    lambda r, c: (-r, c),
    lambda r, c: (-r, -c),
    lambda r, c: (c, r),
    lambda r, c: (c, -r),
    lambda r, c: (-c, r),
    lambda r, c: (-c, -r),
]


def d8_orbit_size(cells):
    """形状在 D4 下的轨道大小（自由多联骨牌意义下）。"""
    images = set()
    for f in D8:
        images.add(pack(normalize([f(r, c) for r, c in cells])))
    return len(images)


def class_counts(cells, s):
    """mod s 类计数向量：dict[(r%s, c%s)] -> count。"""
    cnt = Counter((r % s, c % s) for r, c in cells)
    return cnt


def target_phase_vectors(m, n, s):
    """m×n（及转置）矩形在 s² 个相位平移下的全部合法类计数向量集合。"""
    out = set()
    for a, b in {(m, n), (n, m)}:
        base = class_counts([(r, c) for r in range(a) for c in range(b)], s)
        for dr in range(s):
            for dc in range(s):
                shifted = Counter()
                for (kr, kc), v in base.items():
                    shifted[((kr + dr) % s, (kc + dc) % s)] += v
                out.add(frozenset(shifted.items()))
    return out


def render_board(rows):
    cells = board_cells(rows)
    if not cells:
        return "(empty)"
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    lines = []
    for r in range(min(rs), max(rs) + 1):
        m = int(rows[r])
        s = "".join("#" if (m >> c) & 1 else "." for c in range(min(cs), max(cs) + 1))
        lines.append(s.rstrip("."))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主分析
# ---------------------------------------------------------------------------
def hist_line(cnt: Counter, max_show=14):
    items = sorted(cnt.items())
    parts = [f"{k}×{v}" for k, v in items[:max_show]]
    if len(items) > max_show:
        parts.append(f"…（共 {len(items)} 种）")
    return ", ".join(parts)


def analyze(name):
    t0 = time.time()
    C = load_case(name)
    n = C["n"]
    flags = C["flags"]
    edges = C["edges"]
    outdeg = C["outdeg"]
    indeg = C["indeg"]
    dist = C["dist"]
    boards = C["boards"]

    print("=" * 74)
    print(f"### case {name}   |A| = {n:,}   edges = {len(edges):,}")
    print("=" * 74)

    # ---------------- §1 集合计数复现 ----------------
    print("\n[§1 集合计数复现]")
    assert np.array_equal(C["ids"], np.arange(n)), "id 不是 0..N-1"
    in_cone = (flags & F_IN_CONE) != 0
    in_B = (flags & F_IN_B) != 0
    sink = (flags & F_SINK) != 0
    basin = (flags & F_BASIN) != 0
    two_not_flag = (flags & F_TWO_NOT) != 0
    unsolvable = ~in_B
    iso = unsolvable & ~basin                      # 孤立死：不可解 且 不在吸引盆
    unsolv_but_basin = unsolvable & basin          # 不可解但能走到真死局
    print(f"  inCone            = {in_cone.sum():,}")
    print(f"  inB(可解)         = {in_B.sum():,}")
    print(f"  不可解 A−B        = {unsolvable.sum():,}")
    print(f"  sink(真死局)      = {sink.sum():,}   （其中在B内 = {(sink & in_B).sum()}）")
    print(f"  inBasinTrue       = {basin.sum():,}")
    print(f"  孤立死(不可解&非盆)= {iso.sum():,}   bit6(two_not_touching) = {two_not_flag.sum():,}"
          f"   一致={np.array_equal(iso, two_not_flag)}")
    print(f"  不可解但能到死局  = {unsolv_but_basin.sum():,}"
          f"   （其中 cone\\B 逃逸态 = {(unsolv_but_basin & in_cone).sum()}，"
          f"cone 外 = {(unsolv_but_basin & ~in_cone).sum()}）")
    # 一致性：B ⊆ basin ?
    print(f"  B ⊆ basin 检查: B−basin = {(in_B & ~basin).sum()}")
    print(f"  sink ⊆ basin 检查: sink−basin = {(sink & ~basin).sum()}")
    # 度数校验：membership.outdeg 与 edges.bin 实际出边必须一致
    real_out = np.bincount(edges[:, 0], minlength=n)
    real_in = np.bincount(edges[:, 1], minlength=n)
    assert np.array_equal(real_out, outdeg), "outdeg 与 edges.bin 不一致"
    assert np.array_equal(real_in, indeg), "indeg 与 edges.bin 不一致"
    assert edges[:, 0].max() < n and edges[:, 1].max() < n, "边端点越界"
    n_self = int((edges[:, 0] == edges[:, 1]).sum())
    self_states = np.zeros(n, dtype=bool)
    self_states[edges[edges[:, 0] == edges[:, 1], 0]] = True
    print(f"  边端点越界检查: 通过")
    print(f"  membership.outdeg/indeg 与 edges.bin 双向一致: 通过")
    print(f"  自环边(u→v, u=v) = {n_self} 条，涉及 {int(self_states.sum())} 个状态"
          f"（对称形状移动后规范形映射回自身；其中孤立死状态 "
          f"{int((self_states & iso).sum())} 个）")
    dup = len(edges) - len(np.unique(edges, axis=0))
    print(f"  重复边 = {dup}")

    # ---------------- §2 孤立死子图 + 边界封闭 ----------------
    print("\n[§2 孤立死子图导出与边界封闭验证]")
    n_iso = int(iso.sum())
    iso_idx = np.flatnonzero(iso)
    # 边界：iso → 非 iso、非 iso → iso 的边数（后继封闭预言前者为 0）
    out_boundary = int((iso[edges[:, 0]] & ~iso[edges[:, 1]]).sum())
    in_boundary = int((~iso[edges[:, 0]] & iso[edges[:, 1]]).sum())
    print(f"  孤立死状态 = {n_iso:,}")
    print(f"  孤立死 → 非孤立死 的边 = {out_boundary}   （后继封闭：孤立死状态的所有出路都还在孤立死集内，"
          f"即整个孤立死区『只进不出』）")
    print(f"  非孤立死 → 孤立死 的边 = {in_boundary}   （入口边：外界（可解/到死局侧）一步踏进来的通道）")
    if in_boundary:
        m = (~iso[edges[:, 0]]) & iso[edges[:, 1]]
        for w, u in edges[m]:
            def tags(i):
                t = []
                if in_B[i]:
                    t.append("可解B")
                if basin[i]:
                    t.append("到死局basin")
                if in_cone[i]:
                    t.append("cone内")
                if not t:
                    t.append("孤立死")
                return "+".join(t)
            print(f"    入口边: {w} -> {u}  源[{tags(w)}] → 目标[{tags(u)}]"
                  f"（源出度 {outdeg[w]}）")
    indptr, indices = build_csr(n, edges, node_subset=iso)
    sub_edges = int((indptr[1:] - indptr[:-1]).sum())
    print(f"  诱导子图: {n_iso:,} 节点 / {sub_edges:,} 边")

    # ---------------- §3 SCC ----------------
    print("\n[§3 SCC 分解（迭代 Tarjan；Kosaraju 独立复核；随机小图自测先行）]")
    assert scc_selftest(), "Tarjan/Kosaraju 小图自测失败"
    comp, ncomp = tarjan_scc(n_iso, indptr, indices)
    comp2, ncomp2 = kosaraju_scc(n_iso, indptr, indices)
    same = ncomp == ncomp2 and len({frozenset(np.flatnonzero(comp == k).tolist())
                                     for k in range(ncomp)} ^
                                  {frozenset(np.flatnonzero(comp2 == k).tolist())
                                   for k in range(ncomp2)}) == 0
    print(f"  Tarjan: {ncomp} 个 SCC；Kosaraju: {ncomp2} 个 SCC；划分一致 = {same}")
    assert same
    sizes = Counter(int((comp == k).sum()) for k in range(ncomp))
    print(f"  分量大小直方图（大小×个数）: {hist_line(sizes)}")
    big = sorted(sizes.items(), key=lambda kv: (-kv[0], kv[1]))[:5]
    print(f"  最大分量 top5: {big}")

    # ---------------- §4 分量内部结构 ----------------
    print("\n[§4 分量内部结构]")
    # 分量内出度（逐边统计，local 编号 0..n_iso-1）
    edge_src = np.repeat(np.arange(n_iso, dtype=np.int64), np.diff(indptr))
    edge_dst = indices
    same_comp = comp[edge_src] == comp[edge_dst]
    inter_comp_edges = int((~same_comp).sum())
    print(f"  跨分量的边（分量 A → 分量 B）= {inter_comp_edges}"
          f"   → 孤立死区{'是' if inter_comp_edges == 0 else '不是'}若干互不相连的孤岛")
    internal_outdeg = np.zeros(n_iso, dtype=np.int64)
    np.add.at(internal_outdeg, edge_src[same_comp], 1)
    # 分量级统计
    comp_size = np.zeros(ncomp, dtype=np.int64)
    np.add.at(comp_size, comp, 1)
    comp_edges = np.zeros(ncomp, dtype=np.int64)
    np.add.at(comp_edges, comp[edge_src[same_comp]], 1)
    # 每个分量的自环边数（local 意义下 u==v）
    self_loop_edge = edge_src == edge_dst
    comp_selfloops = np.zeros(ncomp, dtype=np.int64)
    np.add.at(comp_selfloops, comp[edge_src[self_loop_edge & same_comp]], 1)
    single_cycle = 0
    chorded = 0
    singleton = 0
    selfloop_singleton = 0
    chord_hist = Counter()
    for k in range(ncomp):
        sz = comp_size[k]
        ec = comp_edges[k]
        if sz == 1:
            singleton += 1
            if int(comp_selfloops[k]) == 1:
                selfloop_singleton += 1
        elif ec == sz:
            single_cycle += 1
        else:
            chorded += 1
            chord_hist[int(ec - sz)] += 1
    print(f"  单点分量 = {singleton}（其中带自环的永动单点 = {selfloop_singleton}），"
          f"单环分量（E=|V|，无弦） = {single_cycle}，"
          f"带弦分量 = {chorded}")
    if chord_hist:
        print(f"  带弦分量的弦数（E−|V|）分布: {hist_line(chord_hist, max_show=60)}")
    node_internal = internal_outdeg[comp >= 0]
    print(f"  分量内出度: 平均 = {node_internal.mean():.3f}，"
          f"最大 = {node_internal.max()}，分布: {hist_line(Counter(node_internal.tolist()))}")
    # 每个分量内部：出度全为 1 的分量数（严格功能图单环的充分条件）
    strict_cycle = 0
    for k in range(ncomp):
        if comp_size[k] > 1 and comp_edges[k] == comp_size[k]:
            members = np.flatnonzero(comp == k)
            if np.all(internal_outdeg[members] == 1):
                strict_cycle += 1
    print(f"  其中节点级出度全为 1 的严格单环分量 = {strict_cycle}")
    # 凝聚结构：每个 SCC 缩成一点后的出/入边（须在 comp_size 之后）
    out_inter = np.zeros(ncomp, dtype=np.int64)
    in_inter = np.zeros(ncomp, dtype=np.int64)
    cross = ~same_comp
    np.add.at(out_inter, comp[edge_src[cross]], 1)
    np.add.at(in_inter, comp[edge_dst[cross]], 1)
    bottom = np.flatnonzero(out_inter == 0)
    srcs = np.flatnonzero(in_inter == 0)
    print(f"  凝聚图（每分量缩为一点）: {ncomp} 点 / {inter_comp_edges} 边")
    print(f"  汇分量（无出区边，永远的永动陷阱底）= {len(bottom)} 个，"
          f"大小分布 {hist_line(Counter(int(comp_size[k]) for k in bottom))}")
    print(f"  源分量（无入区边）= {len(srcs)} 个，"
          f"大小分布 {hist_line(Counter(int(comp_size[k]) for k in srcs))}")

    # ---------------- §5 孤立死状态整体分布 ----------------
    print("\n[§5 孤立死状态整体出度/入度/dist]")
    io_out = outdeg[iso]
    io_in = indeg[iso]
    io_dist = dist[iso]
    print(f"  总出度: 平均 = {io_out.mean():.3f}，范围 {io_out.min()}~{io_out.max()}"
          f"  分布: {hist_line(Counter(io_out.tolist()))}")
    print(f"  总入度: 平均 = {io_in.mean():.3f}，范围 {io_in.min()}~{io_in.max()}"
          f"  分布: {hist_line(Counter(io_in.tolist()))}")
    print(f"  dist: 取值集合 = {sorted(set(io_dist.tolist()))}"
          f"   （不在 B 内，回程距离无定义）")
    print(f"  出度为 0 的孤立死状态 = {int((io_out == 0).sum())}（应为 0：出度 0 即真死局、必在吸引盆）")
    # 对照：全图出度均值
    print(f"  对照 全图平均出度 = {outdeg.mean():.3f}，不可解(非孤立死)平均出度 = "
          f"{outdeg[unsolv_but_basin].mean():.3f}")

    # ---------------- §6 对称性 ----------------
    print("\n[§6 对称性（boards.bin 规范形）]")
    ub = np.unique(boards, axis=0)
    print(f"  全图不同规范形数 = {len(ub):,} / |A| = {n:,}"
          f"   （每顶点即一个 D4 等价类；任意两不同顶点互不为 D4 像）")
    orbit_sizes = []
    trans_invariant_ok = True
    iso_boards = boards[iso]
    for rows in iso_boards:
        cells = board_cells(rows)
        orbit_sizes.append(d8_orbit_size(cells))
        # 平移诱导颜色置换：平移后重新归一必须回到同一规范形（顶点不变）
        for dr, dc in ((1, 0), (0, 1), (1, 1)):
            t = pack(normalize([(r + dr, c + dc) for r, c in cells]))
            if t != tuple(int(x) for x in rows):
                trans_invariant_ok = False
    stab = Counter(8 // k for k in orbit_sizes)
    orb = Counter(orbit_sizes)
    print(f"  孤立死形状的 D4 轨道大小分布: {hist_line(orb)}")
    print(f"  对应自对称群阶（稳定子 8/轨道大小）分布: {hist_line(stab)}")
    print(f"  平移(1,0)/(0,1)/(1,1) 后规范形不变（平移诱导的颜色置换不产生新顶点）: "
          f"{'全部通过' if trans_invariant_ok else '存在反例!'}")
    # mod 类着色向量核对
    _m, _n, s_s = (int(x) for x in name.split("_"))
    legal = target_phase_vectors(_m, _n, s_s)
    bad = 0
    vecs = Counter()
    for rows in iso_boards:
        cnt = class_counts(board_cells(rows), s_s)
        vecs[frozenset(cnt.items())] += 1
        if frozenset(cnt.items()) not in legal:
            bad += 1
    print(f"  mod{s_s} 类计数向量全部合法（目标矩形某相位）: {'是' if bad == 0 else f'否({bad})'}；"
          f"孤立死状态的类计数向量种数 = {len(vecs)}")
    for v, c in sorted(vecs.items(), key=lambda kv: -kv[1]):
        print(f"    向量 {dict(sorted(v))} × {c}")

    # 分量样例渲染
    print("\n  [分量样例]")
    order = sorted(range(ncomp), key=lambda k: (-comp_size[k], k))
    shown = 0
    for k in order:
        if shown >= 3:
            break
        members = np.flatnonzero(comp == k)
        sz = comp_size[k]
        ec = comp_edges[k]
        if sz >= 2:
            exemplar = iso_idx[members[0]]
            print(f"  -- 分量#{k}: {sz} 态 / {ec} 内边，代表状态 id={exemplar}:")
            print(render_board(boards[exemplar]))
            print()
            shown += 1
    if singleton:
        k1 = next(k for k in range(ncomp) if comp_size[k] == 1)
        exemplar = iso_idx[int(np.flatnonzero(comp == k1)[0])]
        print(f"  -- 单点分量#{k1}: 代表状态 id={exemplar}:")
        print(render_board(boards[exemplar]))

    # ---------------- §7 sink 与不可解对比 ----------------
    print("\n[§7 sink 特征与不可解结构对比]")
    sk = np.flatnonzero(sink)
    print(f"  sink 数 = {len(sk):,}")
    print(f"  sink 的 dist: {sorted(set(dist[sk].tolist()))}（不在 B，回程距离无定义）")
    print(f"  sink 的入度: 平均 = {indeg[sk].mean():.2f}，范围 {indeg[sk].min()}~{indeg[sk].max()}"
          f"  分布: {hist_line(Counter(indeg[sk].tolist()))}")
    print(f"  sink 在吸引盆内 = {int(basin[sk].sum())}/{len(sk)}（真死局自身算能走到死局）")
    ubb = unsolv_but_basin
    print(f"  不可解但能到死局 = {int(ubb.sum()):,}："
          f"平均出度 {outdeg[ubb].mean():.2f}、平均入度 {indeg[ubb].mean():.2f}")
    print(f"  不可解且孤立     = {n_iso:,}："
          f"平均出度 {outdeg[iso].mean():.2f}、平均入度 {indeg[iso].mean():.2f}")
    print(f"  对比: 不可解总数 {int(unsolvable.sum()):,} = 可到死局 {int(ubb.sum()):,} "
          f"+ 孤立 {n_iso:,}")
    print(f"  孤立死态中处在 cone（打乱可达）内的 = {int((iso & in_cone).sum()):,}"
          f"（即自动打乱有可能一步踩进的永动陷阱），cone 外 = {int((iso & ~in_cone).sum()):,}")
    print(f"  对照 cone\\B 逃逸态总数 = {int((in_cone & ~in_B).sum()):,}"
          f"（其中到死局 {int((in_cone & ~in_B & basin).sum()):,}、"
          f"永动陷阱 {int((in_cone & ~in_B & ~basin).sum()):,}）")

    print(f"\n[耗时 {time.time() - t0:.1f}s]")
    return {"case": name, "n": n, "iso": n_iso, "ncomp": ncomp,
            "sizes": dict(sizes), "inter_comp_edges": inter_comp_edges,
            "out_boundary": out_boundary, "in_boundary": in_boundary,
            "single_cycle": single_cycle, "chorded": chorded, "singleton": singleton,
            "selfloop_singleton": selfloop_singleton, "strict_cycle": strict_cycle,
            "self_loops_total": n_self, "self_states_total": int(self_states.sum()),
            "self_states_iso": int((self_states & iso).sum())}


def main():
    cases = sys.argv[1:] or DEFAULT_CASES
    print("孤立死分量分析（只读模式，不写任何文件）")
    results = []
    for name in cases:
        results.append(analyze(name))
        print()
    print("=" * 74)
    print("汇总")
    print("=" * 74)
    for r in results:
        print(f"  {r['case']}: |A|={r['n']:,} 孤立死={r['iso']} SCC={r['ncomp']} "
              f"单点={r['singleton']}(自环永动 {r['selfloop_singleton']}) "
              f"单环={r['single_cycle']} 带弦={r['chorded']} "
              f"跨分量边={r['inter_comp_edges']} 边界(出/入)={r['out_boundary']}/{r['in_boundary']} "
              f"全图自环={r['self_loops_total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
