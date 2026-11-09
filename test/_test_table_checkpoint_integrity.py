# -*- coding: utf-8 -*-
"""建表斷點完整性护栏（2026-11-10，D5 全量建表那一半）。

實測：solver/data 下 4_4_1 / 5_5_2 / 5_5_3 只有 checkpoint.pkl，沒有
meta.json + table.pkl，**三個斷點都不完整**（在批次中途存下來的）：
  · 5_5_3 抽 30 個已記錄狀態 → 515 個未記錄前驅，外推約 2.2 萬漏態
  · 5_5_2 第 4 層抽 30 個 → 473 個，外推約 730 萬漏態
  · 4_4_1 第 7 層抽 30 個 → 171 個，外推約 1184 萬漏態

⚠️ 5_5_3 的 frontier 是 0：拿 BuildWorker.load_checkpoint() 續跑會直接跳過
BFS 主迴圈、走 save_checkpoint(final=True)，寫出一張「1278 態 / 直徑 2」的
**假全量表**。所以本護欄釘死：這些 case 不能當真值表用，也必須能被
飽和抽樣抓出漏態。完整表只有有 meta.json + table.pkl 的那幾檔。

執行：D:/python/python.exe -u test/_test_table_checkpoint_integrity.py
"""
import os
import pickle
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solver import table_core as tc  # noqa: E402
from solver.table_solver import load_table  # noqa: E402

INCOMPLETE = [('4_4_1', 4, 4, 1), ('5_5_2', 5, 5, 2), ('5_5_3', 5, 5, 3)]
COMPLETE = [('2_3_1', 2, 3, 1), ('3_3_1', 3, 3, 1),
            ('3_3_2', 3, 3, 2), ('4_4_2', 4, 4, 2), ('4_4_3', 4, 4, 3)]
SAMPLE = 6
FAILURES = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        FAILURES.append(name)
    return ok


def data_dir(case):
    return os.path.join(ROOT, 'solver', 'data', case)


def main():
    # A. 完整表：meta / table / 狀態數三者一致
    for case, m, n, step in COMPLETE:
        d = data_dir(case)
        meta_path = os.path.join(d, 'meta.json')
        tbl_path = os.path.join(d, 'table.pkl')
        ok = os.path.exists(meta_path) and os.path.exists(tbl_path)
        if ok:
            t = load_table(m, n, step)
            import json
            meta = json.load(open(meta_path, encoding='utf-8'))
            ok = len(t) == meta['total_states']
        check(f'A {case} 有 meta+table 且狀態數一致', ok)

    # B. 不完整斷點：沒有 meta/table，load_table 拿不到真值表
    for case, m, n, step in INCOMPLETE:
        d = data_dir(case)
        has_final = (os.path.exists(os.path.join(d, 'meta.json'))
                     and os.path.exists(os.path.join(d, 'table.pkl')))
        check(f'B {case} 沒有 final 產物（不得被當全量表）', not has_final)
        # load_table 會刻意回退 checkpoint（docstring 明說「建表中回退」）：
        # 對已記錄狀態 dist 仍精確，只是覆蓋率低，所以這裡只釘住「不是空」，
        # 真正要擋的是拿它去建商圖（見 D2）。
        check(f'B {case} load_table 回退到 checkpoint（非完整表）',
              bool(load_table(m, n, step)))

        # C. 飽和抽樣必須能抓到漏態（直接呼叫 table_core.predecessors）
        ck = os.path.join(d, 'checkpoint.pkl')
        with open(ck, 'rb') as f:
            dist = pickle.load(f)['dist']
        seeds = random.Random(20261110).sample(list(dist), SAMPLE)
        new = 0
        cnt = m * n
        for h in seeds:
            B = set(tc.int_to_coords(h, cnt))
            for p in tc.predecessors(B, m, n, step):
                if p not in dist:
                    new += 1
        check(f'C {case} 抽 {SAMPLE} 個仍抓得到未記錄前驅（斷點不完整）',
              new > 0, f'新增 {new}')

    # D. 飽和檢查工具還在（別讓後人拿 build_table 直接續跑）
    tool = os.path.join(ROOT, 'experiments', 'script_bench_full_table_cost.py')
    src = open(tool, encoding='utf-8').read() if os.path.exists(tool) else ''
    check('D1 飽和抽樣工具存在且支援 --sample / --layer-value',
          '--sample' in src and '--layer-value' in src
          and 'predecessors' in src)

    pdb_script = os.path.join(ROOT, 'experiments', 'script_build_pdb.py')
    ps = open(pdb_script, encoding='utf-8').read()
    check('D2 建 PDB 前強制要求完整 meta+table（靜態）',
          'require_complete_table' in ps and 'return 2' in ps)
    # 真的拿不完整 case 跑一次，必須被拒絕（不能只靠靜態字串）
    import subprocess
    p = subprocess.run([sys.executable, '-u', pdb_script,
                        '--case', '5_5_3', '--sample', '1'],
                       cwd=ROOT, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=120)
    out = p.stdout.decode('utf-8', 'replace')
    check('D3 不完整斷點真的被建 PDB 腳本拒絕',
          p.returncode == 2 and '拒絕' in out, out.strip()[:80])

    print('==== %s（%d 項失敗）' % (
        '全部通過' if not FAILURES else '有失敗', len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
