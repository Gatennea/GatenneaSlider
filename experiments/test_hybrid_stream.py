# -*- coding: utf-8 -*-
"""headless 验证 hybrid 多段播放的核心逻辑（不依赖 pygame）。

验证两件事：
1. 分段播放一致性：把 auto_solve 上报的各段动作按队列顺序接到棋盘上，必须
   重建求解器的完整解（尤其「补缺宏前缀 + 混合流水线续算后缀」的续算情形）。
2. 历史最优 checkpoint 选择：聚拢度 score 最高；完全并列（1e-9 内）取 Φ 最小。
"""
import sys
sys.path.insert(0, '.')

import random
import time

from game import SliderMatrix
from solver import auto_solver as auto_mod
from solver.auto_solver import auto_solve, _phi_of
from solver.ml.fill_macro import build_game, _replay_apply, replay_and_verify
from solver.ml.invariants import is_solved_by_profile


def concat_stages_equals_full(size, seed, step, budget):
    random.seed(seed)
    g = SliderMatrix(*size)
    g.shuffle(attempts=80 if size[0] <= 4 else 150, step=step)
    coords0 = frozenset(tuple(b.location) for b in g.blocks)

    stages = []
    label_order = []

    def cb(s):
        stages.append(s)
        label_order.append(s['label'])

    # 时间上限 cancel_check：hybrid_solve 内部无自有时限，必须靠 cancel 收口，
    # 否则在无解的 partial 续算分支会无限跑（生产由 GUI 的 gen 化 cancel 收口）。
    t0 = time.time()
    def cc():
        return (time.time() - t0) >= budget

    r = auto_solve(g, step, stage_cb=cb, time_budget=budget,
                   cancel_check=cc)
    # 重放：从 coords0 起，逐段把动作接到棋盘（同 GUI 逐段播放）
    cur = coords0
    concat_len = 0
    for s in stages:
        a5 = [tuple(a) + ((tuple(rp),) if rp else (None,))
              for a, rp in zip(s['actions'], s['reps'])]
        gg = build_game(cur, g.m, g.n)
        if not _replay_apply(gg, a5, g.m, g.n, step):
            return False, 'replay 失败 @ %s' % s['label']
        cur = frozenset(tuple(b.location) for b in gg.blocks)
        concat_len += len(s['actions'])
        # 逐段校验：每段上报的 end 必须等于「动作重放后的真实棋盘态」——
        # 专门抓续算分支「后缀从 coords0 重放」导致的 checkpoint 坐标错误。
        if cur != s['end']:
            return False, ('段 %s 的 end 坐标与重放落点不符（end=%s, 实=%s）'
                           % (s['label'], sorted(s['end']), sorted(cur)))

    # 期望终态
    if isinstance(r, tuple):  # 全解
        a5 = [tuple(a) + ((tuple(rp),) if rp else (None,))
              for a, rp in zip(r[0], r[1])]
        ge = build_game(coords0, g.m, g.n)
        ok = _replay_apply(ge, a5, g.m, g.n, step)
        final = frozenset(tuple(b.location) for b in ge.blocks)
        expect_solved = True
    elif isinstance(r, dict) and r.get('type') == 'fill_partial':
        # 全败：期望终态 = 最后一段的 end（即最优 partial）
        final = stages[-1]['end'] if stages else coords0
        expect_solved = False
    else:
        # fill_fail / False（含取消）：无完整解。若已流出部分成果段，则终态 =
        # 最后一段的 end（最优 partial，与 GUI 的 best-restore 一致）；否则无动作、
        # 终态 = coords0（标 SKIP）。注意：取消（r=False）但带 partial 段是合法契约——
        # 求解器返回 False、GUI 靠 _auto_best 恢复到最高聚拢度段。
        if not stages:
            return None, 'SKIP（预算内未解出，auto_solve 返回 %s）' % type(r).__name__
        final = stages[-1]['end']
        expect_solved = False

    ok_consistent = (cur == final)
    # 复原是「位置无关」判定（任一个 m×n 连续矩形都算），不能用固定窗口的边界检查
    ok_solved = (expect_solved == is_solved_by_profile(final, g.m, g.n))
    return (ok_consistent and ok_solved,
            'stages=%s concat=%d final_match=%s solved_match=%s'
            % (label_order, concat_len, ok_consistent, ok_solved))


def best_selection_rule():
    """复刻 _update_auto_best 的比较规则，验证 score 优先 + Φ 并列最小。"""
    def better(new_score, new_phi, best_score, best_phi):
        return (best_score is None
                or new_score > best_score + 1e-9
                or (abs(new_score - best_score) <= 1e-9
                    and new_phi < best_phi - 1e-9))
    # 场景：初始 score=0.5,phi=10；段A score=0.9,phi=4（更好）；段B score=0.9,phi=6
    # （同分但 Φ 更大→不选）；段C score=0.95,phi=2（更好）
    best = {'score': 0.5, 'phi': 10.0}
    assert better(0.9, 4.0, best['score'], best['phi'])
    best = {'score': 0.9, 'phi': 4.0}
    assert not better(0.9, 6.0, best['score'], best['phi'])  # 同分 Φ 更大
    assert better(0.95, 2.0, best['score'], best['phi'])
    # 并列精确相等选 Φ 小
    best = {'score': 0.9, 'phi': 4.0}
    assert not better(0.9, 4.0, best['score'], best['phi'])   # 完全相等不选
    assert better(0.9, 3.9, best['score'], best['phi'])
    return True


def continue_path_end_correct():
    """确定性验证续算分支的 checkpoint 坐标（反向锁定之前的续算坐标 bug）。

    自然用例不触发续算（补缺宏 30s 到点常返回空 partial，混合从头算）。这里用
    4×4 的真实完整解切出「前缀 + 后缀」，并 monkeypatch：
        table_solve   -> None（强制走 gap/hybrid 路径，否则 4×4 查表直接返回）
        solve_gap_macro -> 返回前缀作为 fill_partial（设 best=prefix 终态）
        hybrid_solve  -> 返回后缀（从 best 终态续算）
    验证：续算段 '混合流水线·续算' 上报的 end == 整链 prefix+suffix 从 coords0
    重放的终态；且 auto_solve 返回的 (acts,reps) 重放后 == 该 end。
    """
    import random
    from solver.table_solver import table_solve

    random.seed(7)
    g = SliderMatrix(4, 4)
    g.shuffle(attempts=80, step=2)
    coords0 = frozenset(tuple(b.location) for b in g.blocks)

    # 取真实完整解（4×4 有表，table_solve 保证返回有效解）
    full = table_solve(auto_mod.deepcopy(g), 2, cancel_check=lambda: False,
                       progress_callback=None)
    if not isinstance(full, tuple) or not full[0]:
        return False, '无法取得 4×4 真实完整解（table_solve 返回 %s）' % type(full).__name__
    path, rep_cells = full
    if len(path) < 3:
        return False, '完整解过短（%d 步），无法切分前缀/后缀' % len(path)
    k = max(1, len(path) // 3)
    prefix = list(path[:k])
    prefix_reps = list(rep_cells[:k])
    suffix = list(path[k:])
    suffix_reps = list(rep_cells[k:])
    assert prefix and suffix, '前缀/后缀必须都非空'

    stages = []
    captured = {}

    def cb(s):
        stages.append(s)
        if s['label'] == '混合流水线·续算':
            captured['cont'] = s

    # 拼接整链动作，重放得到期望终态
    full_a5 = [tuple(a) + ((tuple(r),) if r else (None,))
               for a, r in zip(path, rep_cells)]
    gf = build_game(coords0, 4, 4)
    assert _replay_apply(gf, full_a5, 4, 4, 2), '完整解重放失败'
    final = frozenset(tuple(b.location) for b in gf.blocks)

    orig_table = auto_mod.table_solve
    orig_gap = auto_mod.solve_gap_macro
    orig_hybrid = auto_mod.hybrid_solve
    try:
        auto_mod.table_solve = lambda *a, **k: None
        auto_mod.solve_gap_macro = lambda *a, **k: {
            'type': 'fill_partial', 'actions': prefix, 'rep_cells': prefix_reps}
        auto_mod.hybrid_solve = lambda *a, **k: (suffix, suffix_reps)

        r = auto_solve(g, 2, stage_cb=cb, cancel_check=lambda: False)
    finally:
        auto_mod.table_solve = orig_table
        auto_mod.solve_gap_macro = orig_gap
        auto_mod.hybrid_solve = orig_hybrid

    if 'cont' not in captured:
        return False, '未触发续算段（stages=%s）' % [s['label'] for s in stages]
    cont_end = captured['cont']['end']

    # 校验 1：续算段 end == 整链重放终态
    if cont_end != final:
        return False, ('续算段 end 与整链终态不符（end=%d块,%s; final=%d块,%s）'
                       % (len(cont_end), sorted(cont_end)[:3],
                          len(final), sorted(final)[:3]))

    # 校验 2：返回的解重放到 final
    if not isinstance(r, tuple):
        return False, 'auto_solve 未返回全解（%s）' % type(r).__name__
    ra5 = [tuple(a) + ((tuple(rp),) if rp else (None,))
           for a, rp in zip(r[0], r[1])]
    gr = build_game(coords0, 4, 4)
    assert _replay_apply(gr, ra5, 4, 4, 2), '返回解重放失败'
    ret_final = frozenset(tuple(b.location) for b in gr.blocks)
    if ret_final != final:
        return False, '返回解终态与整链终态不符'

    # 校验 3：反向证明修复有意义——若按「后缀从 coords0 单独重放」（旧 bug 写法）
    # 得到的落点必然 != final，说明旧代码确会被此测试抓出。
    bad_end, ok = auto_mod._end_state(coords0, suffix, suffix_reps, 4, 4, 2)
    if ok and bad_end == final:
        return False, '旧 bug 写法巧合也得到正确 end（测试失去区分力）'

    return True, ('续算段 end 正确（=整链终态 %d 块），返回解一致；'
                  '旧 bug 写法落点=%s 已偏离' % (len(final),
                  sorted(bad_end)[:3] if ok else None))


if __name__ == '__main__':
    fails = 0
    print('== 分段播放一致性 ==')
    cases = [((4, 4), 7, 2), ((4, 4), 3, 2), ((5, 5), 11, 2),
             ((5, 5), 5, 2), ((6, 6), 2, 2), ((6, 6), 9, 2)]
    for (sz, sd, st) in cases:
        ok, msg = concat_stages_equals_full(sz, sd, st, 40)
        tag = 'PASS' if ok else ('SKIP' if ok is None else 'FAIL')
        print('  %s %s seed %d -> %s' % (tag, sz, sd, msg))
        if ok is False:
            fails += 1
    print('== 最优 checkpoint 选择规则 ==')
    ok = best_selection_rule()
    print(('  PASS' if ok else '  FAIL'), 'score 优先 + Φ 并列最小')
    if not ok:
        fails += 1
    print('== 续算分支 checkpoint 坐标（确定性） ==')
    ok, msg = continue_path_end_correct()
    print(('  PASS' if ok else '  FAIL'), msg)
    if not ok:
        fails += 1
    print('\n结果：', '全部通过' if fails == 0 else '%d 项失败' % fails)
    sys.exit(1 if fails else 0)
