# -*- coding: utf-8 -*-
"""D5：在有全量 BFS 真值表的尺寸上建可採納 PDB，並逐態驗證。

範圍只限 solver/data 裡**已有完整 table.pkl + meta.json** 的尺寸
（3_3_1 / 3_3_2 / 2_3_1 / 4_4_2 / 4_4_3）。斷點未收斂的 4_4_1 / 5_5_2
不能拿來建 PDB（cone 不完整會漏邊、h 會偏大）。

每張 PDB 都是真實狀態圖的商圖 BFS（見 solver/pdb.py），不是擬合、不是估算；
輸出可採納性逐態檢查結果（反例必須 0）、壓縮比、平均 h、h>0 覆蓋率。
結果檔是臨時產物、未入庫，別在文件裡引用它的路徑。

用法：
  D:/python/python.exe -u experiments/script_build_pdb.py --case 3_3_1
  D:/python/python.exe -u experiments/script_build_pdb.py --case 4_4_2 --workers 12
"""
import argparse
import json
import os
import pickle
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solver import pdb as pdb_lib  # noqa: E402
from solver.table_solver import load_table  # noqa: E402


def require_complete_table(case, m, n, step):
    """商圖 PDB 只能用**完整** cone：load_table 會回退到建表中的 checkpoint，
    那些檔的 dist 層不完整（2026-11-10 實測 4_4_1 / 5_5_2 / 5_5_3 都漏了
    數萬到千萬個狀態），拿去建商圖會漏邊、h 偏大，結論全錯。
    """
    import json
    d = os.path.join(ROOT, 'solver', 'data', case)
    meta_path = os.path.join(d, 'meta.json')
    tbl_path = os.path.join(d, 'table.pkl')
    if not (os.path.exists(meta_path) and os.path.exists(tbl_path)):
        print('拒絕：%s 沒有 meta.json + table.pkl，只是建表中的斷點，'
              '不能用來建商圖 PDB。先跑 '
              'experiments/script_bench_full_table_cost.py 做飽和檢查。' % case)
        return False
    meta = json.load(open(meta_path, encoding='utf-8'))
    if meta.get('total_states') != len(load_table(m, n, step) or {}):
        print('拒絕：%s 的 meta 狀態數與 table.pkl 不一致。' % case)
        return False
    return True


def run(args):
    m, n, step = (int(x) for x in args.case.split('_'))
    if not require_complete_table(args.case, m, n, step):
        return 2
    table = load_table(m, n, step)
    print('CASE %s  真值表 %d 態，直徑 %d'
          % (args.case, len(table), max(table.values())), flush=True)

    names = args.abstractors.split(',')
    built = []
    phi_maps = []
    summary = {'case': args.case, 'states': len(table), 'pdb': []}
    for name in names:
        fn = pdb_lib.ABSTRACTORS[name]
        t0 = time.time()
        print('  --- 建 %s ---' % name, flush=True)
        one, phi, st = pdb_lib.build_quotient_pdb(
            table, m, n, step, fn, workers=args.workers,
            chunk=args.chunk, verbose=True)
        # 單張也要逐態可採納
        chk = pdb_lib.verify_admissible(
            table, [(one, fn)], phi_maps=[phi], sample=args.sample,
            seed=args.seed)
        dt = time.time() - t0
        print('    單張驗證：檢查 %d 態，反例 %d，平均 h %.3f，h>0 %.1f%%，'
              '耗時 %.1fs' % (chk['checked'], chk['violations'],
                             chk['mean_h'], chk['nonzero_ratio'] * 100, dt),
              flush=True)
        built.append((one, fn))
        phi_maps.append(phi)
        summary['pdb'].append({
            'name': name, **st, **chk, 'seconds': round(dt, 2),
            'compression': round(len(table) / max(1, st['abstract_nodes']), 1),
        })

    # max-PDB 仍可採納（每張都 <= dist，取 max 也 <= dist）
    t0 = time.time()
    mx = pdb_lib.verify_admissible(
        table, built, phi_maps=phi_maps, sample=args.sample, seed=args.seed)
    print('  MAX-PDB 驗證：檢查 %d 態，反例 %d，平均 h %.3f，h>0 %.1f%%，'
          '耗時 %.1fs' % (mx['checked'], mx['violations'], mx['mean_h'],
                         mx['nonzero_ratio'] * 100, time.time() - t0), flush=True)
    summary['max_pdb'] = mx

    any_viol = mx['violations'] or any(p['violations'] for p in summary['pdb'])
    any_outside = any(p['outside_successors'] for p in summary['pdb'])
    print('  結論：可採納性 %s；cone 封閉性 %s'
          % ('✅ 零反例' if not any_viol else '❌ 有反例',
             '✅ 表外後繼 0' if not any_outside else '⚠️ 有表外後繼'), flush=True)

    if args.save:
        os.makedirs(os.path.dirname(args.save), exist_ok=True)
        with open(args.save, 'wb') as f:
            pickle.dump({'pdb': [(one, name) for (one, _fn), name
                                 in zip(built, names)],
                         'summary': summary}, f,
                        protocol=pickle.HIGHEST_PROTOCOL)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    return 0 if not any_viol else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', default='3_3_1')
    ap.add_argument('--abstractors', default='coarse2,holes,profile')
    ap.add_argument('--workers', type=int, default=0)
    ap.add_argument('--chunk', type=int, default=2000)
    ap.add_argument('--sample', type=int, default=0)
    ap.add_argument('--seed', type=int, default=20261110)
    ap.add_argument('--save', default='')
    ap.add_argument('--out', default='')
    sys.exit(run(ap.parse_args()))


if __name__ == '__main__':
    main()
