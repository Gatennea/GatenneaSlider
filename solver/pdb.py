# -*- coding: utf-8 -*-
"""可採納 Pattern Database 原型（D5，研究用，**不接生產預設**）。

這不是學距離、也不是估算。做法是把真實狀態圖投影成小得多的「商圖」：

    φ: 狀態 -> 抽象鍵
    抽象邊 a->b 存在，若且唯若存在真實動作 s->s' 使 φ(s)=a, φ(s')=b
    從 φ(goal) 沿邊的**反向**做 BFS，得到每個抽象鍵到目標的最短抽象距離

任一條真實路徑投影後都是抽象路徑（長度不增），所以
    h(s) = abst_dist[φ(s)] <= 真實最短距離 dist[s]
即**可採納下界**。多個 φ 各建一張 PDB，取 max 仍然可採納。

真實狀態圖只能取自有全量 BFS 表的尺寸（目前 4_4_2 / 4_4_3 / 3_3_1 等），
所以這個原型只在有真值的尺寸上驗證，不外推成玩家大尺寸的現成能力。
玩家側 `guided_reduce_one(scorer=None)` 完全不受影響。

用法見 experiments/script_bench_pdb_scorer.py、experiments/script_build_pdb.py。
"""
import collections
import multiprocessing
import os
import pickle

from solver import table_core as tc


# ---------------------------------------------------------------------------
# 抽象鍵：全部是「純座標函數」，與 m/n 無關（方便做跨尺寸可採納性檢驗）
# ---------------------------------------------------------------------------
def _normalized(coords):
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    mr, mc = min(rs), min(cs)
    return [(r - mr, c - mc) for r, c in coords]


def abstract_coarse2(coords):
    """2×2 粗化：相鄰四格併成一個超級格，再用規範形合併 8 個對稱。"""
    return tc.canonicalize(frozenset((r // 2, c // 2)
                                     for r, c in _normalized(coords)))


def abstract_coarse3(coords):
    return tc.canonicalize(frozenset((r // 3, c // 3)
                                     for r, c in _normalized(coords)))


def abstract_profile(coords):
    """平移歸一後每行／每列的佔格數（丢掉格子的具體位置）。"""
    cs = _normalized(coords)
    h = max(r for r, _ in cs) + 1
    w = max(c for _, c in cs) + 1
    rows = [0] * h
    cols = [0] * w
    for r, c in cs:
        rows[r] += 1
        cols[c] += 1
    return (tuple(rows), tuple(cols))


def abstract_holes(coords):
    """包圍盒內的缺格（洞）形狀，規範形合併對稱。"""
    cs = set(_normalized(coords))
    h = max(r for r, _ in cs) + 1
    w = max(c for _, c in cs) + 1
    holes = frozenset((r, c) for r in range(h) for c in range(w)
                      if (r, c) not in cs)
    return tc.canonicalize(holes) if holes else 0


ABSTRACTORS = {
    'coarse2': abstract_coarse2,
    'coarse3': abstract_coarse3,
    'profile': abstract_profile,
    'holes': abstract_holes,
}


# ---------------------------------------------------------------------------
# 商圖邊（多進程：每個任務只回傳後繼 hash，抽象鍵查表在父進程做）
# ---------------------------------------------------------------------------
def _edges_worker(args):
    hashes, m, n, step = args
    total = m * n
    out = []
    for h in hashes:
        B = set(tc.int_to_coords(h, total))
        out.append((h, list(tc.forward_neighbors(B, step, total))))
    return out


def phi_map(table, m, n, abstractor):
    """全表狀態 -> 抽象鍵。"""
    total = m * n
    out = {}
    for h in table:
        out[h] = abstractor(set(tc.int_to_coords(h, total)))
    return out


def build_quotient_pdb(table, m, n, step, abstractor, workers=None,
                       chunk=2000, verbose=True):
    """回傳 (pdb, phi_by_hash, stats)。

    pdb: dict[抽象鍵] = 到目標的最短抽象步數（可採納下界）
    stats 裡 outside 是「真實正向後繼不在真值表內」的邊數；正常應為 0，
    非 0 代表 cone 不封閉或前/後繼生成不對稱，會讓 h 偏大。
    """
    workers = workers or min(12, max(2, (os.cpu_count() or 4) - 2))
    total = m * n
    phi = phi_map(table, m, n, abstractor)
    goal_key = abstractor(tc.goal_state(m, n))

    rev = collections.defaultdict(set)   # key_dst -> {key_src}
    outside = 0
    n_edges = 0
    hashes = list(table)
    tasks = [(hashes[i:i + chunk], m, n, step)
             for i in range(0, len(hashes), chunk)]

    pool = multiprocessing.Pool(processes=workers)
    try:
        for batch in pool.imap_unordered(_edges_worker, tasks):
            for h, nbrs in batch:
                ks = phi[h]
                for nh in nbrs:
                    kn = phi.get(nh)
                    if kn is None:
                        outside += 1
                        continue
                    rev[kn].add(ks)
                    n_edges += 1
    finally:
        pool.close()
        pool.join()

    # 從目標抽象節點沿「反向邊」BFS：rev[b] 是所有能一步到 b 的抽象節點
    pdb = {goal_key: 0}
    queue = collections.deque([goal_key])
    while queue:
        b = queue.popleft()
        d = pdb[b] + 1
        for a in rev.get(b, ()):
            if a not in pdb:
                pdb[a] = d
                queue.append(a)

    stats = {
        'abstract_nodes': len(set(phi.values())),
        'reachable_nodes': len(pdb),
        'real_states': len(table),
        'edges': n_edges,
        'outside_successors': outside,
        'goal_key': goal_key,
        'workers': workers,
    }
    if verbose:
        print('  PDB 抽象節點 %d（可達 %d）/ 真實狀態 %d，邊 %d，表外後繼 %d'
              % (stats['abstract_nodes'], stats['reachable_nodes'],
                 len(table), n_edges, outside), flush=True)
    return pdb, phi, stats


def pdb_lookup(pdb, abstractor, coords):
    """單張 PDB 查值；抽象鍵沒見過就回 0（可採納但弱）。"""
    return pdb.get(abstractor(coords), 0)


def max_pdb_lookup(pdbs, coords):
    """多張 PDB 取 max，仍可採納。pdbs = [(pdb, abstractor), ...]"""
    best = 0
    for pdb, fn in pdbs:
        v = pdb.get(fn(coords), 0)
        if v > best:
            best = v
    return best


def verify_admissible(table, pdbs, phi_maps=None, m=None, n=None,
                      abstractors=None, sample=0, seed=0):
    """逐態檢查 h(s) <= dist[s]。回傳 (檢查數, 反例數, 平均 h, h>0 比例)。

    可給 sample 抽樣（0 = 全表）。phi_maps 為 build_quotient_pdb 回傳的鍵表，
    沒給就現場算。反例必須是 0 —— 商圖邊完備時這在數學上必然成立，
    出現反例代表接線或狀態圖有 bug，不是「PDB 不準」。
    """
    import random
    items = list(table.items())
    if sample and sample < len(items):
        items = random.Random(seed).sample(items, sample)
    if phi_maps is None:
        total = m * n
        phi_maps = [phi_map(dict(items), m, n, fn) for _pdb, fn in pdbs]
    viol = 0
    sum_h = 0
    nonzero = 0
    for h, d in items:
        hv = 0
        for i, (pdb, _fn) in enumerate(pdbs):
            v = pdb.get(phi_maps[i][h], 0)
            if v > hv:
                hv = v
        sum_h += hv
        nonzero += (hv > 0)
        if hv > d:
            viol += 1
    return {
        'checked': len(items),
        'violations': viol,
        'mean_h': sum_h / len(items) if items else 0,
        'nonzero_ratio': nonzero / len(items) if items else 0,
    }


def save_pdb(path, pdb, stats):
    with open(path, 'wb') as f:
        pickle.dump({'pdb': pdb, 'stats': stats}, f,
                    protocol=pickle.HIGHEST_PROTOCOL)


def load_pdb(path):
    with open(path, 'rb') as f:
        o = pickle.load(f)
    return o['pdb'], o['stats']
