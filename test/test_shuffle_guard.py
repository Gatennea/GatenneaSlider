# -*- coding: utf-8 -*-
"""打乱死局黑名单防护的 headless 验证（不启动 GUI / 不需要 pygame 显示）。

三项检查：
  a. solver/deadend_blacklist.json 能加载、恰好 9 个哈希，且与
     trap_paths_4_4_2.json 的结论逐项一致；
  b. trap_paths 里 9 个死局态（traps[i].edges[-1].child_cells）全部被判为
     命中黑名单 —— 防护有效性的直接证据；外加端到端检查：把棋盘置成死局态
     再 shuffle，终态必须脱离黑名单（死局态向前封闭，防护不回复原态重打
     就出不去，这条同时验证了重打前的复位逻辑）；
  c. create_puzzle(4, 4, 2) 连跑 2000 次真实 shuffle：无终态落黑名单，
     并粗测单次防护判定耗时远小于单次 shuffle 耗时。

用法：
  python test/test_shuffle_guard.py
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from puzzle_types import create_puzzle  # noqa: E402
from solver import table_core as tc  # noqa: E402
from solver.deadend_guard import (has_deadend_guard, is_deadend,  # noqa: E402
                                  load_blacklist)

TRAP_PATHS = ROOT / 'experiments' / 'math_repro' / 'trap_paths_4_4_2.json'
M, N, STEP = 4, 4, 2
N_SHUFFLE = 2000
ATTEMPTS = M * N * 10  # 与 GUI 同参：attempts = m*n*10


def trap_cells(trap):
    """第 i 个死局态在规范坐标系下的格子集合 [(row, col), ...]。"""
    return [tuple(c) for c in trap['edges'][-1]['child_cells']]


def check_blacklist(traps):
    """a. 黑名单文件可加载、恰好 9 个哈希、与 trap_paths 结论一致。"""
    bl = load_blacklist()
    assert set(bl) == {'4_4_2'}, f'黑名单 key 异常: {set(bl)}'
    hashes = bl['4_4_2']
    assert isinstance(hashes, frozenset) and len(hashes) == 9, \
        f'应为恰好 9 个哈希，实际 {len(hashes)}'
    assert hashes == {t['state'] for t in traps}, '黑名单与 trap_paths 死局哈希不一致'
    assert tc.canonicalize(tc.goal_state(M, N)) not in hashes, '复原态不得进黑名单'
    print(f'a 通过: 黑名单 4_4_2 恰好 {len(hashes)} 个死局哈希')


def check_traps(traps):
    """b. 9 个死局态全部判为命中；死局态开局 shuffle 后必须脱离。"""
    for i, trap in enumerate(traps):
        cells = trap_cells(trap)
        assert tc.canonicalize(cells) == trap['state'], \
            f'trap[{i}] child_cells 规范化与 state 口径不符'
        assert is_deadend(M, N, STEP, cells), f'trap[{i}] 未被判为死局命中'
    assert not is_deadend(M, N, STEP, tc.goal_state(M, N)), '复原态不得判为死局'
    assert not has_deadend_guard(6, 6, STEP), '非 4_4_2 谜题不该启用防护'
    assert not is_deadend(6, 6, STEP, tc.goal_state(6, 6)), '非黑名单谜题不该命中'
    print(f'b 通过: {len(traps)}/9 个死局态全部命中黑名单')

    # 端到端：逐个把棋盘置成死局态再 shuffle，防护必须把终态带出黑名单。
    g = create_puzzle(M, N, STEP)
    for i, trap in enumerate(traps):
        for b, (r, c) in zip(g.blocks, trap_cells(trap)):
            b.location = [r, c]
        g.shuffle(ATTEMPTS, STEP, bias=0.0, min_score=0.75)
        final = {tuple(b.location) for b in g.blocks}
        assert not is_deadend(M, N, STEP, final), \
            f'从死局态 trap[{i}] 开局 shuffle 后终态仍是死局'
    print(f'b 通过(端到端): 从 {len(traps)} 个死局态开局 shuffle 均脱离黑名单')


def check_shuffles():
    """c. 2000 次真实 shuffle 无终态命中 + 防护开销可忽略。"""
    import random
    random.seed(20261012)
    g = create_puzzle(M, N, STEP)
    g.shuffle(ATTEMPTS, STEP, bias=0.0, min_score=0.75)  # 预热（含 solver 包首次导入）
    load_blacklist()  # 预热黑名单缓存，计时不含文件 IO

    shuffle_ms, guard_ms = [], []
    for _ in range(N_SHUFFLE):
        t0 = time.perf_counter()
        g.shuffle(ATTEMPTS, STEP, bias=0.0, min_score=0.75)
        t1 = time.perf_counter()
        coords = {tuple(b.location) for b in g.blocks}
        t2 = time.perf_counter()
        dead = is_deadend(M, N, STEP, coords)
        t3 = time.perf_counter()
        assert not dead, f'打乱终态落进黑名单: {sorted(coords)}'
        shuffle_ms.append((t1 - t0) * 1000)
        guard_ms.append((t3 - t2) * 1000)

    avg_s = sum(shuffle_ms) / len(shuffle_ms)
    avg_g = sum(guard_ms) / len(guard_ms)
    print(f'c 通过: {N_SHUFFLE} 次 shuffle 无终态命中黑名单；'
          f'单次 shuffle 均值 {avg_s:.3f}ms，单次防护判定均值 {avg_g:.3f}ms'
          f'（占 {avg_g / avg_s * 100:.2f}%）')
    assert avg_g < avg_s * 0.1, f'防护判定开销占比 {avg_g / avg_s:.2%}，超过 10%'


def main() -> int:
    t0 = time.perf_counter()
    traps = json.loads(TRAP_PATHS.read_text(encoding='utf-8'))['traps']
    assert len(traps) == 9, f'trap_paths 应有 9 个死局，实际 {len(traps)}'
    check_blacklist(traps)
    check_traps(traps)
    check_shuffles()
    print(f'全部通过，总耗时 {time.perf_counter() - t0:.1f}s')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
