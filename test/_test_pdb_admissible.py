# -*- coding: utf-8 -*-
"""D5 护栏：可採納 PDB 原型（2026-11-10）。

PDB 不是擬合、不是估算，而是真實狀態圖的**商圖**：抽象邊必須包含每條
真實動作的投影，再從目標沿**反向邊** BFS。任一條真實路徑投影後都是
抽象路徑（長度不增），所以 h(s) <= 真實最短距離。本護欄釘死：

  A. 靜態接線 + 防回流：solver/pdb.py 存在、 ABSTRACTORS 齊全；
     玩家側與生產求解鏈不得 import PDB（D5 是研究原型，不接預設）。
  B. 可採納性：3_3_1 小表逐態零反例、cone 封閉（表外後繼 0）、
     coarse2 必須真壓縮、max-PDB 仍可採納。
  C. 反向驗證（在護欄內自跑）：故意用錯邊方向 / 故意關掉反例檢查，
     指定斷言必須轉紅——證明這些檢查不是恒真裝飾。
  D. 注入接縫：PDB 打分能經 scorer= 跑完 GBFS，路徑可重放。

真刀反向驗證（撤原始碼接線）見當日 archive 裡的 _reverse_pdb.py。
執行：D:/python/python.exe -u test/_test_pdb_admissible.py
"""
import inspect
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import solver.search_core as sc  # noqa: E402
from solver import pdb as pdb_lib  # noqa: E402
from solver import table_core as tc  # noqa: E402
from solver.table_solver import load_table  # noqa: E402
from game import SliderMatrix  # noqa: E402

M = N = 3
STEP = 1
CASE = '3_3_1'
FAILURES = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        FAILURES.append(name)
    return ok


def static_checks():
    src = inspect.getsource(pdb_lib)
    check('A1 solver/pdb.py 提供商圖 PDB 與四個抽象鍵',
          all(k in pdb_lib.ABSTRACTORS for k in
              ('coarse2', 'coarse3', 'profile', 'holes'))
          and 'def build_quotient_pdb' in src
          and 'def verify_admissible' in src)
    check('A2 商圖用反向邊 BFS（rev[kn].add(ks) + rev.get(b)）',
          'rev[kn].add(ks)' in src and 'rev.get(b, ())' in src
          and 'goal_key' in src)
    check('A3 表外抽象鍵回退 0（可採納但弱），不是大常數',
          'pdb.get(abstractor(coords), 0)' in src
          or 'pdb.get(fn(coords), 0)' in src)

    prod = ['solver/auto_solver.py', 'solver/hybrid_solver.py',
            'solver/search_core.py', 'solver/__init__.py',
            'gui/auto_solve.py']
    leaked = []
    for rel in prod:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        s = open(p, encoding='utf-8').read()
        if 'from solver import pdb' in s or 'import solver.pdb' in s \
                or 'pdb_lib' in s:
            leaked.append(rel)
    check('A4 玩家側與生產求解鏈完全不引用 PDB', not leaked, str(leaked))


def build_all():
    table = load_table(M, N, STEP)
    names = ('coarse2', 'holes', 'profile')
    built, phis, stats = [], [], []
    for name in names:
        one, phi, st = pdb_lib.build_quotient_pdb(
            table, M, N, STEP, pdb_lib.ABSTRACTORS[name],
            workers=2, chunk=300, verbose=False)
        built.append((one, pdb_lib.ABSTRACTORS[name]))
        phis.append(phi)
        stats.append(st)
    return table, built, phis, stats


def admissibility_checks(table, built, phis, stats):
    singles = []
    for i, (one, fn) in enumerate(built):
        r = pdb_lib.verify_admissible(table, [(one, fn)], phi_maps=[phis[i]])
        singles.append(r)
        check('B%d 單張 %s 逐態可採納（零反例）'
              % (i + 1, ('coarse2', 'holes', 'profile')[i]),
              r['violations'] == 0 and r['checked'] == len(table),
              f"{r['checked']} 態 / 反例 {r['violations']}")
    check('B4 cone 封閉：三張商圖表外後繼全為 0',
          all(s['outside_successors'] == 0 for s in stats),
          str([s['outside_successors'] for s in stats]))
    check('B5 coarse2 是真壓縮（抽象節點遠少於真實狀態）',
          stats[0]['abstract_nodes'] < len(table) / 10,
          f"{stats[0]['abstract_nodes']} vs {len(table)}")
    mx = pdb_lib.verify_admissible(table, built, phi_maps=phis)
    check('B6 max-PDB 仍可採納（零反例）', mx['violations'] == 0,
          f"平均 h {mx['mean_h']:.3f}")


def reverse_checks(table, built, phis, stats):
    """護欄內的反向驗證：真正會破壞商圖的是「漏邊」，不是邊方向。

    ⚠️ 實測教訓：coarse2 的抽象圖近似無向，把邊方向反過來 BFS 結果一樣、
    可採納性仍是零反例，所以「邊方向」不是個能轉紅的反向驗證。
    漏邊則會讓抽象節點大量不可達、h 退化成 0（回退機制反而掩蓋了反例），
    因此要靠「邊數完備 / 可達節點數」這類不變量抓，不能只靠 h<=dist。
    """
    import collections
    fn = pdb_lib.ABSTRACTORS['profile']
    phi = phis[2]
    goal = fn(tc.goal_state(M, N))
    full = collections.defaultdict(set)
    partial = collections.defaultdict(set)
    expected_edges = 0
    for h in table:
        B = set(tc.int_to_coords(h, M * N))
        nb = list(tc.forward_neighbors(B, STEP, M * N))
        expected_edges += len(nb)
        for x in nb:
            if x in phi:
                full[phi[x]].add(phi[h])
        if nb and nb[0] in phi:
            partial[phi[nb[0]]].add(phi[h])

    def bfs(rev):
        d = {goal: 0}
        q = collections.deque([goal])
        while q:
            b = q.popleft()
            for a in rev.get(b, ()):
                if a not in d:
                    d[a] = d[b] + 1
                    q.append(a)
        return d

    d_full, d_partial = bfs(full), bfs(partial)
    check('C1 商圖邊完備：三張邊數都等於全表正向邊總數',
          all(s['edges'] == expected_edges for s in stats),
          f"{[s['edges'] for s in stats]} vs {expected_edges}")
    check('C2 反向驗證：故意漏邊會讓可達抽象節點大幅下降',
          len(d_partial) < len(d_full) / 2,
          f'{len(d_partial)} vs {len(d_full)}')

    # 故意把 PDB 值吹大，檢查邏輯必須報反例（不是恒真）
    fake = {k: 10 ** 6 for k in built[0][0]}
    r_fake = pdb_lib.verify_admissible(table, [(fake, built[0][1])],
                                       phi_maps=[phis[0]])
    check('C3 反向驗證：故意誇大的 PDB 必然被判不可採納',
          r_fake['violations'] > 0, f"反例 {r_fake['violations']}")


def injection_checks(built):
    """PDB 打分經 scorer= 注入 GBFS 能跑完、路徑可重放。"""
    def score(coords, m, n, step):
        h = pdb_lib.max_pdb_lookup(built, coords)
        return h, len(sc.fast_window(coords, m, n)[1])

    ok = 0
    for seed in (1, 7, 42):
        random.seed(seed)
        g = SliderMatrix(M, N)
        g.shuffle(M * N * 10, STEP)
        coords = frozenset(tuple(b.location) for b in g.blocks)
        path, expanded = sc.guided_reduce_one(
            coords, M, N, STEP, budget=2000, scorer=score)
        if path is None:
            continue
        cur = coords
        good = True
        for act, rep in path:
            nxt = next((new for new, a, r in sc.expand(cur, STEP)
                        if a == act and r == rep), None)
            if nxt is None:
                good = False
                break
            cur = nxt
        ok += good
    check('D1 PDB 打分注入 GBFS 後路徑可逐步重放', ok >= 2, f'{ok}/3')


def main():
    static_checks()
    table, built, phis, stats = build_all()
    admissibility_checks(table, built, phis, stats)
    reverse_checks(table, built, phis, stats)
    injection_checks(built)
    print('==== %s（%d 項失敗）' % (
        '全部通過' if not FAILURES else '有失敗', len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
