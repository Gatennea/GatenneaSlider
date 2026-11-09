# -*- coding: utf-8 -*-
"""D2 第二輪：從機制構造「進展估計」的證偽實驗（只在 4_4_2）。

背景：`script_bench_true_dist_scorer.py` 已證明「把表內真值距離注入打分」
能讓 GBFS 單段終態更接近還原，但那是查表、不是可取得的資訊，且 GBFS 的
終止判據仍是「洞數變少」。本輪換兩件事：

  1. 打分改成**從機制構造**（凸塊-缺口一對一配對、行列剖面缺陷、單軸
     位移分解），不看錶、不擬合、不掃參數；
  2. 終止判據也換成可注入的 stop_fn（見
     `solver/search_core.py::guided_reduce_one`），讓「打分變小」能直接
     當本段目標，而不是被「洞數變少」綁住。

⚠️ H2/H3 界線：這裡**不是**拿資料學距離、也不是估算 A* 下界；打分只吃
coords / m / n / step，真值表**只用來事後評估**（量方向正確率與解長），
絕不參與打分。護欄 `test/_test_solver_progress_scorer.py` 會靜態檢查這點。

驗收前就寫死的止損判據（不事後挑）：某個機制打分要**同時**滿足
  (a) 鄰居方向正確率比 `heuristic_parts` 高 ≥ 5 個百分點；
  (b) 貪心還原局數比基線多 ≥ 2 局；若兩邊都還原過半，
      還要步數中位不高於基線。
才算「值得繼續 D2」。任一不滿足就照實判止損，不外推到玩家尺寸。
⚠️ (b) 初版寫的是「步數中位低於基線」，小樣本實跑發現基線貪心
**0 局還原**、中位數是 None，判據根本不可判定；改成還原局數是
**更嚴格**的替代品（不是放寬），修正理由如實留在此處。
GBFS 單段對照只作旁證（終止判據不同源，不能拿來宣稱解出率提升）。

用法：D:/python/python.exe -u experiments/script_bench_progress_scorer.py \
          --sample 2000 --seeds 12
輸出只到 stdout，不落結果檔（避免 doclink 裸引用）。
"""
import argparse
import os
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import solver.search_core as sc  # noqa: E402
from solver import table_core as tc  # noqa: E402
from solver.ml.invariants import profile_defect  # noqa: E402
from solver.table_solver import load_table  # noqa: E402
from game import SliderMatrix  # noqa: E402

MISSING = 10 ** 6
M = N = 4
STEP = 2
CNT = M * N


# ---------------- 機制型進展估計（不看錶、不擬合） ----------------
def _pairs(holes, protr, cost_fn):
    """凸塊與缺口的一對一配對（兩者數量恆相等：|B| = |win| = m*n）。

    按成本升序貪心取不重複配對。這是**機制構造**：基線
    `heuristic_parts` 讓每個凸塊各自搶「最近缺口」，多個凸塊搶同一個
    缺口時會系統性低估；一對一配對直接消除這個低估。不是最優匹配，
    也不引入任何可調權重。
    """
    cand = []
    for p in protr:
        for q in holes:
            cand.append((cost_fn(p, q), p, q))
    cand.sort()
    used_p, used_q, total = set(), set(), 0
    for d, p, q in cand:
        if p in used_p or q in used_q:
            continue
        used_p.add(p)
        used_q.add(q)
        total += d
    # 數量相等 ⇒ 正常情況下全配對；保險起見把落單的也計一步
    total += (len(protr) - len(used_p)) + (len(holes) - len(used_q))
    return total


def _d_manhattan(p, q, step):
    return max(1, (abs(p[0] - q[0]) + abs(p[1] - q[1])) // step)


def _d_axes(p, q, step):
    """單軸位移分解：合法步一次只沿一個軸，兩個軸都要修至少兩步。"""
    dr = (abs(p[0] - q[0]) + step - 1) // step
    dc = (abs(p[1] - q[1]) + step - 1) // step
    return max(1, dr + dc)


def _parts(coords, m, n, step, cost_fn, with_phi):
    _win, holes, protr = sc.fast_window(coords, m, n)
    # 洞數是基線的第一項，必須保留：少了它，一對一配對反而會比
    # heuristic_parts 系統性偏低（初版護欄 C3 抓到 0/20）。
    h = len(holes) + _pairs(holes, protr,
                            lambda p, q: cost_fn(p, q, step))
    if with_phi:
        # Φ 只作次級鍵（沿用 auto_solver 裡「並列 tiebreak」的既有設計），
        # 主鍵仍是配對成本；不做加權、不掃係數。
        return h * 1000 + profile_defect(coords, m, n)
    return h


def scorer_default(coords, m, n, step):
    return sc.heuristic_parts(coords, m, n, step)


def scorer_pair(coords, m, n, step):
    h = _parts(coords, m, n, step, _d_manhattan, False)
    return h, len(sc.fast_window(coords, m, n)[1])


def scorer_pair_phi(coords, m, n, step):
    h = _parts(coords, m, n, step, _d_manhattan, True)
    return h, len(sc.fast_window(coords, m, n)[1])


def scorer_axes(coords, m, n, step):
    h = _parts(coords, m, n, step, _d_axes, False)
    return h, len(sc.fast_window(coords, m, n)[1])


SCORERS = {
    'S0': scorer_default,     # 現況 heuristic_parts
    'S1': scorer_pair,         # 一對一配對
    'S2': scorer_pair_phi,     # 一對一配對 + Φ 次級鍵
    'S3': scorer_axes,         # 單軸位移分解
}


# ---------------- 評估（真值只在這裡出現） ----------------
def sample_states(table, count, seed):
    """從全量表按 dist 分層抽樣，避免只抽到淺層。"""
    items = list(table.items())
    rng = random.Random(seed)
    buckets = {}
    for h, d in items:
        buckets.setdefault(d, []).append(h)
    chosen = []
    for d in sorted(buckets):
        take = max(1, round(count * len(buckets[d]) / len(items)))
        pool = buckets[d]
        chosen += [(h, d) for h in
                   (rng.sample(pool, take) if len(pool) > take else pool)]
    if len(chosen) > count:
        chosen = rng.sample(chosen, count)
    return chosen


def direction_accuracy(table, states):
    """每個抽樣態：打分選出的鄰居是否讓真值距離嚴格下降。"""
    out = {k: [0, 0] for k in SCORERS}
    for h, d0 in states:
        coords = frozenset(tc.int_to_coords(h, CNT))
        nbrs = sc.expand(coords, STEP)
        if not nbrs:
            continue
        scored = {}
        for nb, _a, _r in nbrs:
            nd = table.get(tc.canonicalize(nb), MISSING)
            for name, fn in SCORERS.items():
                v = fn(nb, M, N, STEP)[0]
                # 只比打分；同分保留 expand 順序裡先遇到的那個。
                # 初版曾用 (v, nd) 比大小，等於讓真值距離在同分時
                # 參與選鄰居 —— 違反「真值只做事後評估」的前提。
                if name not in scored or v < scored[name][0]:
                    scored[name] = (v, nd)
        for name in SCORERS:
            ok, tot = out[name]
            out[name] = [ok + (1 if scored[name][1] < d0 else 0), tot + 1]
    return {k: (v[0] / v[1] if v[1] else 0.0, v[1]) for k, v in out.items()}


def greedy(table, coords, fn, max_steps=400):
    """每步選打分最小的鄰居；只接受打分嚴格變小，避免原地打轉。

    真值表只用於判斷「是否已還原」與統計步數，不參與選步。
    """
    cur = frozenset(coords)
    v = fn(cur, M, N, STEP)[0]
    for k in range(max_steps):
        if table.get(tc.canonicalize(cur), MISSING) == 0:
            return k, True
        best, bestv = None, v
        for nb, _a, _r in sc.expand(cur, STEP):
            nv = fn(nb, M, N, STEP)[0]
            if nv < bestv:
                best, bestv = nb, nv
        if best is None:
            return k, False
        cur, v = best, bestv
    return max_steps, False


def replay_path(coords, path, step):
    cur = frozenset(coords)
    for act, rep in path:
        nxt = None
        for new, a, r in sc.expand(cur, step):
            if a == act and r == rep:
                nxt = new
                break
        if nxt is None:
            return None
        cur = nxt
    return cur


def puzzles(seeds):
    out = []
    for seed in range(seeds):
        random.seed(1000 + seed)
        g = SliderMatrix(M, N)
        g.shuffle(M * N * 10, STEP)
        out.append((seed, frozenset(tuple(b.location) for b in g.blocks)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sample', type=int, default=2000)
    ap.add_argument('--seeds', type=int, default=12)
    ap.add_argument('--budget', type=int, default=3000)
    args = ap.parse_args()

    t_load = time.perf_counter()
    table = load_table(M, N, STEP)
    assert table, '4_4_2 全量表不存在，本實驗只適用有表的尺寸'
    print('表載入 %d 態 / %.2fs' % (len(table), time.perf_counter() - t_load))

    # ---- 指標一：方向正確率（抽樣態，真值只在此處） ----
    states = sample_states(table, args.sample, seed=20261110)
    acc = direction_accuracy(table, states)
    print('\n[1] 鄰居方向正確率（抽 %d 態，打分選的鄰居讓真值距離下降）'
          % len(states))
    for name in SCORERS:
        a, tot = acc[name]
        print('    %s %-22s %.1f%% (%d 態)' % (name, '—', 100 * a, tot))

    # ---- 指標二：貪心全解（同一批固定種子） ----
    puz = puzzles(args.seeds)
    print('\n[2] 貪心還原（每步選打分最小且嚴格變小的鄰居，最多 400 步）')
    greedy_rows = {}
    for name, fn in SCORERS.items():
        rows = []
        t0 = time.perf_counter()
        for seed, coords in puz:
            steps, solved = greedy(table, coords, fn)
            rows.append((steps, solved))
        dt = time.perf_counter() - t0
        solved_steps = [s for s, ok in rows if ok]
        greedy_rows[name] = {
            'solved': len(solved_steps),
            'median': statistics.median(solved_steps) if solved_steps else None,
            'dt': dt,
        }
        print('    %s 還原 %d/%d，步數中位 %s，牆鐘 %.2fs'
              % (name, len(solved_steps), len(rows),
                 greedy_rows[name]['median'], dt))

    # ---- 指標三：GBFS 單段（把「換打分」與「換終止判據」分開看） ----
    # S1h = 只換打分、終止判據仍是洞數變少；其餘 S1~S3 兩者一起換。
    groups = [('S0', None, False), ('S1h', SCORERS['S1'], False)]
    groups += [(k, SCORERS[k], True) for k in ('S1', 'S2', 'S3')]
    print('\n[3] GBFS 單段（S0 全預設；S1h 只換打分；'
          'S1~S3 打分＋stop_fn=打分變小）')
    gbfs_rows = {k: [] for k, _f, _s in groups}
    for seed, coords in puz:
        d0 = table.get(tc.canonicalize(coords), MISSING)
        for name, fn, use_stop in groups:
            if fn is None:
                scorer, stop = None, None
            else:
                scorer = fn
                base = fn(coords, M, N, STEP)[0]
                stop = (lambda v, holes, _b=base: v < _b) if use_stop else None
            t0 = time.perf_counter()
            path, expanded = sc.guided_reduce_one(
                coords, M, N, STEP, budget=args.budget,
                scorer=scorer, stop_fn=stop)
            dt = time.perf_counter() - t0
            end = replay_path(coords, path, STEP) if path else coords
            dend = (table.get(tc.canonicalize(end), MISSING)
                    if end is not None else None)
            gbfs_rows[name].append({'found': path is not None,
                                    'plen': len(path) if path else 0,
                                    'expanded': expanded,
                                    'd_end': dend, 'dt': dt, 'd0': d0})
    for name, rows in gbfs_rows.items():
        found = sum(r['found'] for r in rows)
        ex = statistics.mean(r['expanded'] for r in rows)
        de = statistics.mean(r['d_end'] for r in rows
                             if r['d_end'] is not None)
        ln = statistics.mean(r['plen'] for r in rows)
        print('    %s 找到 %d/%d，平均展開 %.1f，平均段長 %.1f，'
              '平均終態距離 %.2f'
              % (name, found, len(rows), ex, ln, de))

    # ---- 止損判據（開跑前寫死，不事後挑） ----
    base_acc = acc['S0'][0]
    base_med = greedy_rows['S0']['median']
    base_solved = greedy_rows['S0']['solved']
    half = len(puz) / 2
    print('\n[4] 止損判據：方向正確率 ≥ 基線 + 5pp 且 '
          '貪心還原局數 ≥ 基線 + 2')
    winners = []
    for name in ('S1', 'S2', 'S3'):
        a = acc[name][0]
        med = greedy_rows[name]['median']
        solved = greedy_rows[name]['solved']
        pass_acc = a >= base_acc + 0.05
        pass_steps = solved >= base_solved + 2
        if base_solved >= half and solved >= half:
            pass_steps = pass_steps and (med is not None
                                         and base_med is not None
                                         and med <= base_med)
        print('    %s 方向 %.1f%%（基線 %.1f%%，%s）｜貪心還原 %d/%d'
              '（基線 %d，%s）｜步數中位 %s'
              % (name, 100 * a, 100 * base_acc, '過' if pass_acc else '不過',
                 solved, len(puz), base_solved,
                 '過' if pass_steps else '不過', med))
        if pass_acc and pass_steps:
            winners.append(name)
    if winners:
        print('    結論：%s 通過兩項，D2 值得在有真值尺寸繼續；'
              '仍不可外推到玩家大尺寸。' % ', '.join(winners))
    else:
        print('    結論：**止損**。機制型進展估計沒有同時打贏現有打分，'
              '照 H3 的界線不再掃權重／換公式碰運氣；'
              'D2 這條推斷在 4_4_2 上未獲支持，不外推到玩家尺寸。')
    print('    ⚠️ GBFS 對照只作旁證：終止判據不同源，不能拿來宣稱解出率提升。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
