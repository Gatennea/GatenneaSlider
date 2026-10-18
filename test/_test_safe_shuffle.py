# -*- coding: utf-8 -*-
"""安全打乱回归测试（2026-10-18，对齐网页版 shuffle_safe）。

核心断言：打乱终态**保证有解**——record 逆序真的逐步走一遍（每步由
opt/try_move 判定合法、落点精确匹配），必须回到打乱前状态。这就是
「开局自带一条已知解法」的端到端证书，与网页版 certify-shuffle.mjs
同口径。

覆盖：三形态（方形/三角/米字）证书、死局黑名单退休（4_4_2 零命中）、
打乱强度 A/B（安全不弱于普通）、record 与演示动画重放兼容。
"""
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game
from game import SliderMatrix, commit_shuffle_step
from game_mi import MiSliderMatrix
from game_triangle import TriangleSliderMatrix
from game_triangle import GAP_DIRECTIONS as TRI_DIRS
from game_mi import GAP_DIRECTIONS as MI_DIRS


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    return ok


def gap_dirs_for(g, gap_type):
    if isinstance(g, MiSliderMatrix):
        return MI_DIRS[gap_type]
    if isinstance(g, TriangleSliderMatrix):
        return TRI_DIRS[gap_type]
    return ('a', 'd') if gap_type == 'h' else ('w', 's')


def undo_with_record(g, records):
    """把打乱记录逆序真的走一遍（端到端证书）。

    每步：用该步 final 位置上的块触发同缝 opt（几何选中同一组），遍历
    方向找落点 == moved 并提交。返回是否全程走通。
    """
    for rec in reversed(records):
        gap_type, line = rec['gap']
        moved = {tuple(p) for p in rec['moved']}
        final_set = set(rec['final'])
        trig = None
        for b in g.blocks:
            if tuple(b.location) in final_set:
                trig = b
                break
        if trig is None:
            return False
        g.opt(gap_type, line, trig)
        if not any(b.be_opted for b in g.blocks):
            return False
        ok = False
        for d in gap_dirs_for(g, gap_type):
            back = g.try_move(d, rec['step'])
            if back and {tuple(p) for p in back} == moved:
                g.commit_move(back)
                ok = True
                break
        if not ok:
            for b in g.blocks:
                b.be_opted = False
            return False
        for b in g.blocks:
            b.be_opted = False
    return True


def replay_forward(g, records):
    """把打乱记录正序走一遍（演示动画重放语义）：从 pre 到终态。"""
    for rec in records:
        gap_type, line = rec['gap']
        final_set = set(rec['final'])
        trig = None
        for b in g.blocks:
            if tuple(b.location) in rec['moved']:
                trig = b
                break
        if trig is None:
            return False
        g.opt(gap_type, line, trig)
        if not any(b.be_opted for b in g.blocks):
            return False
        back = g.try_move(rec['direction'], rec['step'])
        if not back or [tuple(p) for p in back] != [tuple(p) for p in rec['final']]:
            for b in g.blocks:
                b.be_opted = False
            return False
        g.commit_move(back)
        for b in g.blocks:
            b.be_opted = False
    return True


def make_square(m, n, step):
    random.seed()
    return SliderMatrix(m, n), step


def main():
    all_ok = True

    # ---------- T1 方形证书 ----------
    for seed in (1, 7, 42):
        random.seed(seed)
        g = SliderMatrix(4, 4)
        pre = [tuple(b.location) for b in g.blocks]
        recs = []
        g.shuffle(4 * 4 * 10, 2, record=recs)
        final = [tuple(b.location) for b in g.blocks]
        ok = undo_with_record(g, recs)
        after = [tuple(b.location) for b in g.blocks]
        all_ok &= check(f'T1 方形 4x4x2 證書 seed={seed}',
                        ok and after == pre and pre != final and len(recs) > 0,
                        f'{len(recs)} 步')

    # ---------- T2 三角证书 ----------
    for seed in (3, 11):
        random.seed(seed)
        g = TriangleSliderMatrix(4)
        pre = [tuple(b.location) for b in g.blocks]
        recs = []
        g.shuffle(4 * 4 * 10, 1, record=recs)
        final = [tuple(b.location) for b in g.blocks]
        ok = undo_with_record(g, recs)
        after = [tuple(b.location) for b in g.blocks]
        all_ok &= check(f'T2 三角 k=4 證書 seed={seed}',
                        ok and after == pre and pre != final,
                        f'{len(recs)} 步')

    # ---------- T3 米字证书 ----------
    for seed in (5, 13):
        random.seed(seed)
        g = MiSliderMatrix(4, 4)
        pre = [tuple(b.location) for b in g.blocks]
        recs = []
        g.shuffle(4 * 4 * 10, 2, record=recs)
        final = [tuple(b.location) for b in g.blocks]
        ok = undo_with_record(g, recs)
        after = [tuple(b.location) for b in g.blocks]
        all_ok &= check(f'T3 米字 4x4x2 證書 seed={seed}',
                        ok and after == pre and pre != final,
                        f'{len(recs)} 步')

    # ---------- T4 死局黑名单退休（4_4_2 安全打乱下零命中） ----------
    from solver.deadend_guard import is_deadend
    hits = 0
    trials = 30
    for seed in range(trials):
        random.seed(1000 + seed)
        g = SliderMatrix(4, 4)
        g.shuffle(4 * 4 * 10, 2)
        if is_deadend(4, 4, 2, {tuple(b.location) for b in g.blocks}):
            hits += 1
    all_ok &= check('T4 死局黑名單零命中', hits == 0, f'{hits}/{trials}')

    # ---------- T5 强度 A/B：安全不弱于普通 ----------
    def _bypass_commit(game_, gap_type, line, block, direction, step_,
                       directions, final_positions, record=None):
        """无校验直提（A/B 专用：模拟打安全补丁前的普通打乱）。"""
        if record is not None:
            from game import record_shuffle_move
            record_shuffle_move(record, game_, gap_type, line, direction,
                                step_, final_positions)
        game_.commit_move(final_positions)
        for b in game_.blocks:
            b.be_opted = False
        return True

    def run_ab(n):
        safe_scores, plain_scores = [], []
        for seed in range(n):
            random.seed(seed)
            g = SliderMatrix(4, 4)
            g.shuffle(4 * 4 * 10, 2, min_score=None)
            safe_scores.append(g.compute_score())
            # 普通打乱：临时把提交函数换成无校验直提（A/B 只测强度）
            orig = game.commit_shuffle_step
            game.commit_shuffle_step = _bypass_commit
            try:
                random.seed(seed)
                g2 = SliderMatrix(4, 4)
                g2.shuffle(4 * 4 * 10, 2, min_score=None)
                plain_scores.append(g2.compute_score())
            finally:
                game.commit_shuffle_step = orig
        return safe_scores, plain_scores

    safe_s, plain_s = run_ab(20)
    ms, ps = statistics.mean(safe_s), statistics.mean(plain_s)
    all_ok &= check('T5 強度 A/B：安全不弱於普通', ms <= ps + 0.02,
                    f'安全 {ms:.3f} vs 普通 {ps:.3f}')

    # ---------- T6 演示动画兼容：record 正放重放复现终态 ----------
    random.seed(9)
    g = SliderMatrix(4, 4)
    pre = [tuple(b.location) for b in g.blocks]
    recs = []
    g.shuffle(4 * 4 * 10, 2, record=recs)
    final = [tuple(b.location) for b in g.blocks]
    for i, b in enumerate(g.blocks):
        b.location = list(pre[i])
    ok = replay_forward(g, recs)
    all_ok &= check('T6 record 正放重放復現終態（演示動畫語義）',
                    ok and [tuple(b.location) for b in g.blocks] == final)

    # ---------- T7 性能冒烟：8x8 安全打乱耗时可接受 ----------
    import time
    random.seed(3)
    g = SliderMatrix(8, 8)
    t0 = time.time()
    g.shuffle(8 * 8 * 10, 2, min_score=None)
    dt = time.time() - t0
    all_ok &= check('T7 8x8 安全打亂耗時', dt < 10.0, f'{dt:.1f}s')

    print('[OK] 安全打亂全部通過' if all_ok else '[FAILED] 安全打亂存在失敗項')
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
