# -*- coding: utf-8 -*-
"""D5：把可採納 PDB 經 D1 的 scorer= 接縫注入 GBFS，看值不值得往下走。

範圍**只在 4_4_2**（有全量 BFS 真值表）；PDB 由
experiments/script_build_pdb.py 預先建好（臨時檔、未入庫）。

對照組（同一批固定種子的安全打亂局面）：
  A  預設 heuristic_parts（現況，玩家側）
  B  純 PDB 下界當打分（h 越小越優先）
  C  PDB + 預設啟發做次級鍵（字典序混合，h 主導）
  D  表內真值距離（oracle 上界對照，不是可取得的資訊）

指標：找到「洞數嚴格變少」路徑的局數、平均展開節點、單段終態的真值距離、
牆鐘、PDB 查詢命中率。另外做**跨尺寸可採納性檢驗**：把 4_4_2 建出的 PDB
拿去查另一個尺寸的真值狀態，看 h 有沒有超過 dist（有反例就不能外推）。

結論要誠實：PDB 是「真值表壓縮」，不是擬合；但壓縮比高的 φ 通常 h 很弱，
h 很強的 φ 往往壓縮比接近 1（等於換個鍵把真值表重存一遍），那不算 PDB。
"""
import argparse
import os
import pickle
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import solver.search_core as sc  # noqa: E402
from solver import pdb as pdb_lib  # noqa: E402
from solver import table_core as tc  # noqa: E402
from solver.table_solver import load_table  # noqa: E402
from game import SliderMatrix  # noqa: E402

MISSING = 10 ** 6
M = N = 4
STEP = 2


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


def make_pdb_scorer(pdbs, use_default=False):
    """pdbs = [(pdb, abstractor), ...]；回傳符合 scorer 契約的 (score, holes)。"""
    hits = [0]
    calls = [0]

    def score(coords, m, n, step):
        calls[0] += 1
        h = pdb_lib.max_pdb_lookup(pdbs, coords)
        if h:
            hits[0] += 1
        holes = len(sc.fast_window(coords, m, n)[1])
        if use_default:
            return h * 100 + sc.heuristic_parts(coords, m, n, step)[0], holes
        return h, holes

    return score, hits, calls


def make_true_scorer(table):
    def score(coords, m, n, step):
        d = table.get(tc.canonicalize(coords), MISSING)
        return d, len(sc.fast_window(coords, m, n)[1])
    return score


def make_puzzles(seeds):
    out = []
    for seed in range(seeds):
        random.seed(1000 + seed)
        g = SliderMatrix(M, N)
        g.shuffle(M * N * 10, STEP)
        out.append((seed, frozenset(tuple(b.location) for b in g.blocks)))
    return out


def cross_size_check(pdbs, case, sample=2000, seed=20261110):
    """把 4_4_2 建出的 PDB 用到另一尺寸的真值狀態，檢查 h <= dist。

    只讀 checkpoint.pkl 的 dist（反向 BFS 已發現的狀態，其層數即最短距離）；
    該檔未收斴也沒關係，已記錄狀態的 dist 仍然精確。
    """
    path = os.path.join(ROOT, 'solver', 'data', case, 'checkpoint.pkl')
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        dist = pickle.load(f)['dist']
    items = list(dist.items())
    if sample and len(items) > sample:
        items = random.Random(seed).sample(items, sample)
    m, n = (int(x) for x in case.split('_')[:2])
    cnt = m * n
    viol = 0
    covered = 0
    sum_h = 0
    for h, d in items:
        coords = set(tc.int_to_coords(h, cnt))
        hv = pdb_lib.max_pdb_lookup(pdbs, coords)
        sum_h += hv
        if hv > 0:
            covered += 1
        if hv > d:
            viol += 1
    return {'case': case, 'checked': len(items), 'violations': viol,
            'covered': covered, 'mean_h': sum_h / len(items) if items else 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', type=int, default=8)
    ap.add_argument('--budget', type=int, default=3000)
    ap.add_argument('--pdb', default='archive/scratch_2026-11-10/pdb_442.pkl')
    ap.add_argument('--cross', default='5_5_2,4_4_3,3_3_1')
    args = ap.parse_args()

    pdb_path = os.path.join(ROOT, args.pdb)
    if not os.path.exists(pdb_path):
        print('找不到 PDB 暫存檔，請先跑 experiments/script_build_pdb.py')
        return 2
    with open(pdb_path, 'rb') as f:
        saved = pickle.load(f)
    pdbs = [(one, pdb_lib.ABSTRACTORS[name]) for one, name in saved['pdb']]
    print('載入 %d 張 PDB：%s' % (len(pdbs), [n for _o, n in saved['pdb']]))
    for i, (_one, name) in enumerate(saved['pdb']):
        print('  %-8s 抽象節點 %d' % (name, len(pdbs[i][0])))

    table = load_table(M, N, STEP)
    puzzles = make_puzzles(args.seeds)

    groups = {}
    groups['A'] = (None, None)
    b_score, b_hits, b_calls = make_pdb_scorer(pdbs, use_default=False)
    groups['B'] = (b_score, (b_hits, b_calls))
    c_score, c_hits, c_calls = make_pdb_scorer(pdbs, use_default=True)
    groups['C'] = (c_score, (c_hits, c_calls))
    groups['D'] = (make_true_scorer(table), None)
    # E/F 只用 coarse2：這才是「真壓縮」的 PDB（4_4_2 上 559504→1438）。
    # holes / profile 的抽象節點數接近真實狀態數，等於把真值表換個鍵重存，
    # 必須分開看，否則會把「查表」誤讀成「PDB 有效」。
    only_coarse = [pdbs[0]]
    e_score, _e_hits, _e_calls = make_pdb_scorer(only_coarse, use_default=False)
    f_score, _f_hits, _f_calls = make_pdb_scorer(only_coarse, use_default=True)
    groups['E'] = (e_score, None)
    groups['F'] = (f_score, None)

    rows = []
    for seed, coords in puzzles:
        d0 = table.get(tc.canonicalize(coords), MISSING)
        rec = {'seed': seed, 'd0': d0}
        for name, (scorer, _counter) in groups.items():
            t0 = time.perf_counter()
            path, expanded = sc.guided_reduce_one(
                coords, M, N, STEP, budget=args.budget, scorer=scorer)
            dt = time.perf_counter() - t0
            end = replay_path(coords, path, STEP) if path else coords
            dend = (table.get(tc.canonicalize(end), MISSING)
                    if end is not None else None)
            rec[name] = {'found': path is not None,
                         'plen': len(path) if path else 0,
                         'expanded': expanded, 'd_end': dend, 'dt': dt}
        rows.append(rec)
        print('seed=%-4d d0=%-3d | ' % (seed, d0) +
              ' | '.join('%s %-5s ex=%-5d d_end=%-8s' % (
                  name, rec[name]['found'], rec[name]['expanded'],
                  rec[name]['d_end']) for name in 'ABDEF'))

    def agg(name, key):
        vals = [r[name][key] for r in rows if r[name][key] is not None]
        return statistics.mean(vals) if vals else float('nan')

    print('\n彙總（%d 局，budget=%d）' % (len(rows), args.budget))
    print('  A 預設 / B 全 PDB / C 全 PDB+預設 / D 真值 oracle / '
          'E 僅 coarse2 / F 僅 coarse2+預設')
    for name in 'ABCDEF':
        print('  %s 找到 %d/%d，平均展開 %.1f，平均終態距離 %.2f，平均牆鐘 %.3fs'
              % (name, sum(r[name]['found'] for r in rows), len(rows),
                 agg(name, 'expanded'), agg(name, 'd_end'), agg(name, 'dt')))
    print('  PDB 查詢命中 %d/%d（%.1f%%）'
          % (b_hits[0], b_calls[0],
             100 * b_hits[0] / b_calls[0] if b_calls[0] else 0))

    better = (agg('B', 'd_end') < agg('A', 'd_end') - 0.5
              or agg('C', 'd_end') < agg('A', 'd_end') - 0.5
              or agg('B', 'expanded') < agg('A', 'expanded') * 0.8
              or agg('C', 'expanded') < agg('A', 'expanded') * 0.8)
    print('\n結論一：全 PDB 打分%s（A 終態 %.2f，B %.2f，C %.2f；'
          '展開 A %.1f，B %.1f，C %.1f）'
          % ('有可量測收益' if better else '沒有明顯收益，止損',
             agg('A', 'd_end'), agg('B', 'd_end'), agg('C', 'd_end'),
             agg('A', 'expanded'), agg('B', 'expanded'), agg('C', 'expanded')))
    print('      ⚠️ B 與 D（真值 oracle）數值相同不是 PDB 神效：holes 的抽象節點'
          '數接近真實狀態數，等於把全量表換個鍵重存。')
    print('結論二：只用真壓縮的 coarse2（559504→1438，389×）'
          '終態 %.2f（E）/ %.2f（F），對照 A %.2f、D %.2f；'
          '展開 E %.1f / F %.1f。'
          % (agg('E', 'd_end'), agg('F', 'd_end'),
             agg('A', 'd_end'), agg('D', 'd_end'),
             agg('E', 'expanded'), agg('F', 'expanded')))
    print('      這才是「不靠真值表、有機會外推」的 PDB 該有的成本，'
          '要連同壓縮比一起讀，不能只看 h 強不強。')
    print('      GBFS 終止判據是「洞數變少」，不是 h 變小；D 是 oracle 上界，'
          '不是可取得的資訊。')

    print('\n跨尺寸可採納性檢驗（把 4_4_2 的 PDB 拿去查別的尺寸）：')
    for case in args.cross.split(','):
        if not case:
            continue
        r = cross_size_check(pdbs, case)
        if r is None:
            print('  %s：無 checkpoint，跳過' % case)
            continue
        r2 = cross_size_check([pdbs[0]], case)
        print('  %s 檢查 %d 態｜全 PDB 覆蓋 %.1f%%、反例 %d、平均 h %.2f｜'
              '僅 coarse2 覆蓋 %.1f%%、反例 %d、平均 h %.2f'
              % (r['case'], r['checked'],
                 100 * r['covered'] / r['checked'], r['violations'], r['mean_h'],
                 100 * r2['covered'] / r2['checked'], r2['violations'],
                 r2['mean_h']))
    print('  反例 > 0 ⇒ 商圖邊不覆蓋該尺寸的動作，PDB 不能外推；'
          '反例 = 0 也只是抽樣證據，不是證明。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
