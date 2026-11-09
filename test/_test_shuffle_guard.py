# -*- coding: utf-8 -*-
"""打乱健壮性：死局黑名单移除后（2026-11-10，取代旧的黑名单有效性验证）。

安全打乱每一步都过可逆性校验，整条路径反过来就是一条现成解法，终态
必然落在可解核内，所以不再需要任何黑名单防护（2026-10-18 起实测
30 局零命中，2026-11-10 移除）。本护栏守住「拿掉之后没有退化」：

  a. 静态防回流：防护模块与数据档不存在，生产码 / 打包 / 实验 / 测试
     里没有任何对它们的 import 或路径引用；
  b. 4_4_2 连跑 2000 次真实 shuffle（与旧护栏同规模），每次终态确实
     被打乱（不等于复原态）；
  c. 抽样 30 局带 record：逆序重放每一步都能精确回到打乱前状态，
     与 _test_safe_shuffle.py 同口径的端到端证书。

用法：
  python test/_test_shuffle_guard.py
"""

import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from puzzle_types import create_puzzle  # noqa: E402
from game import SliderMatrix  # noqa: E402

M, N, STEP = 4, 4, 2
N_SHUFFLE = 2000
N_CERT = 30
ATTEMPTS = M * N * 10  # 与 GUI 同参：attempts = m*n*10

# 只把这些文件当「接线」检查；docs/ 与 archive/ 里的历史记录不算回流。
SCAN_FILES = (
    'game.py', 'engine/adapter.py', 'main.py', 'Gatenneaslider.spec',
    'experiments/script_blindspot_scan.py', 'test/_test_safe_shuffle.py',
)
FORBIDDEN = (
    'from solver.deadend_guard import',
    'import solver.deadend_guard',
    'deadend_blacklist.json',
    'has_deadend_guard',
    'is_deadend(',
)


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    return ok


def check_no_guard():
    """a. 模块/数据档已删，且没有任何接线残留。"""
    ok = True
    ok &= check('a1 防护模块已删除',
                not (ROOT / 'solver' / 'deadend_guard.py').exists())
    ok &= check('a2 黑名单数据档已删除',
                not (ROOT / 'solver' / 'deadend_blacklist.json').exists())
    hits = []
    for rel in SCAN_FILES:
        text = (ROOT / rel).read_text(encoding='utf-8')
        for token in FORBIDDEN:
            if token in text:
                hits.append(f'{rel}:{token}')
    ok &= check('a3 生产码/打包/实验/测试无黑名直接线残留',
                not hits, '; '.join(hits[:4]))
    return ok


def undo_with_record(g, records):
    """把打乱记录逆序真的走一遍（方形；与 _test_safe_shuffle 同口径）。"""
    for rec in reversed(records):
        gap_type, line = rec['gap']
        moved = {tuple(p) for p in rec['moved']}
        final_set = set(rec['final'])
        trig = next((b for b in g.blocks
                     if tuple(b.location) in final_set), None)
        if trig is None:
            return False
        g.opt(gap_type, line, trig)
        if not any(b.be_opted for b in g.blocks):
            return False
        dirs = ('a', 'd') if gap_type == 'h' else ('w', 's')
        ok = False
        for d in dirs:
            back = g.try_move(d, rec['step'])
            if back and {tuple(p) for p in back} == moved:
                g.commit_move(back)
                ok = True
                break
        if not ok:
            for b in g.blocks:
                b.be_opted = False
            return False
    return True


def check_shuffles():
    """b. 2000 次真实 shuffle：终态都确实被打乱。"""
    random.seed(20261012)
    g = create_puzzle(M, N, STEP)
    goal = {tuple(b.location) for b in g.blocks}
    t0 = time.perf_counter()
    for i in range(N_SHUFFLE):
        g.shuffle(ATTEMPTS, STEP, bias=0.0, min_score=0.75)
        final = {tuple(b.location) for b in g.blocks}
        if final == goal:
            return check(f'b {N_SHUFFLE} 次 shuffle 终态均被打乱', False,
                         f'第 {i} 次等于复原态')
    dt = time.perf_counter() - t0
    return check(f'b {N_SHUFFLE} 次 shuffle 终态均被打乱', True,
                 f'{dt:.1f}s')


def check_certificates():
    """c. 抽样 30 局：逆序重放 record 精确回到打乱前状态。"""
    ok = True
    for seed in range(N_CERT):
        random.seed(9000 + seed)
        g = SliderMatrix(M, N)
        pre = [tuple(b.location) for b in g.blocks]
        recs = []
        g.shuffle(ATTEMPTS, STEP, record=recs)
        final = [tuple(b.location) for b in g.blocks]
        undo = undo_with_record(g, recs)
        after = [tuple(b.location) for b in g.blocks]
        good = bool(recs) and pre != final and undo and after == pre
        ok &= check(f'c seed={seed} 逆向证书', good,
                    f'{len(recs)} 步')
    return ok


def main() -> int:
    t0 = time.perf_counter()
    all_ok = True
    all_ok &= check_no_guard()
    all_ok &= check_shuffles()
    all_ok &= check_certificates()
    print(f'{"[OK] 无黑名单打乱健壮性全部通过" if all_ok else "[FAILED] 存在失败项"}，'
          f'总耗时 {time.perf_counter() - t0:.1f}s')
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
