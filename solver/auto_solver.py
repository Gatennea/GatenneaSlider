# -*- coding: utf-8 -*-
"""自动规划混合求解器（GUI 'hybrid' 入口，2026-10-02 用户需求）。

不再是一条固定流水线：按「期望耗时升序」规划候选求解器，逐个尝试，
任一全解立即采纳——**时间优先**（用户 2026-09-30 拍板：运算时间 > 解的
长度），且全解 = 聚拢度满值（复原窗即 m×n 满覆盖），两个目标在全解处
天然重合；全败时按聚拢度评估部分成果，续算或作断点返回。

规划顺序（依据 2026-09-30 验收 + 2026-10-02 路由探针
`experiments/_auto_route_probe.py` 的实测）：
    ① 查表 table_solve        亚秒级、保证最优——有表必跑，不可能吃亏
    ② 按空位数路由（洞数 = 窗口内空位数，毫秒级可测）：
        空位 ≤ 2 → 混合流水线先行（实测 5.1：混合 1.4s vs 补缺宏 57.2s）
        空位 ≥ 3 → 补缺宏先行（实测 06: 1.0s / 07: 0.98s，混合均超时）
      两路都会尝试，路由只定先后；落败方照常接力。
    ③ 全败时按聚拢度评估部分成果，续算或作断点返回。

部分成果链接（chaining）：补缺宏的 partial 若聚拢度高于初始局面，混合
流水线从该终态续算（动作前缀拼接，整链重放验证后才采纳）；整体失败时
返回聚拢度提升最大的部分成果（fill_partial 断点协议，GUI 播到断点供
观察/续跑）。

返回协议（与 GUI 对齐）：
    (actions4, rep_cells)          成功（actions 为四元组列表）
    {'type': 'fill_partial', ...}  未全解但有聚拢度提升的部分成果
    {'type': 'fill_fail', ...}     各候选均无成果
    False                          取消

注意：
· segment_cb 边算边播只在 fill_macro/gap_macro 单独作为算法时由 GUI
  建立；本入口统一整链返回，不做流式（播放体验换全链正确性校验）。
· hybrid_solve 本身保持纯算法不动（experiments/ 基线不受影响），
  hybrid_solve_with_table 保留为旧入口（固定「表→混合」两步）。
"""
import time
from copy import deepcopy

from solver.table_solver import table_solve
from solver.ml.gather_solver import gather_metrics
from solver.ml.fill_macro import (build_game, replay_and_verify,
                                  _replay_apply, window_of)
from solver.ml.gap_solver import solve_gap_macro
from solver.hybrid_solver import hybrid_solve
from solver.ml.invariants import profile_defect  # 平移无关 Φ（复用，非重写）

# 从补缺宏 partial 终态续算混合流水线的时间上限（秒）。续算属于「最后一搏」：
# 混合流水线的自然解出时间中位在秒级~十几秒，90 秒足够；到点归还部分成果，
# 落实「算不出来尽早发现、发现就停」（用户 2026-10-02 拍板）。
_CONTINUE_BUDGET = 90.0


def _end_state(coords0, acts, reps, m, n, step):
    """回放部分成果到临时盘。返回 (终态 coords, True)；回放失败 (None, False)。

    acts 为四元组列表，reps 平行对应（可含 None）；统一补成 5 元组回放，
    代表格精确定位分量，None 交引擎按侧首块兜底。
    """
    if not acts:
        return None, False
    a5 = []
    for i, a in enumerate(acts):
        rep = reps[i] if (reps and i < len(reps) and reps[i]) else None
        a5.append(tuple(a) + ((tuple(rep),) if rep else (None,)))
    g = build_game(coords0, m, n)
    if not _replay_apply(g, a5, m, n, step):
        return None, False
    return frozenset(tuple(b.location) for b in g.blocks), True


def _phi_of(coords, m, n):
    """行列剖面 L1 偏差（profile defect Φ）：平移无关，完美矩形（任何位置、含转置）
    得 0，越偏离合法复原形状越大。

    委托 `solver.ml.invariants.profile_defect`（已验证：位置无关、含转置取优、
    Φ=0 ⟺ 还原）；此处只做命名统一与「并列 tiebreak」语义注释。仅作**并列 tiebreak**
    用（聚拢度 score 完全相等时取 Φ 最小者），不单独排序。
    """
    return profile_defect(coords, m, n)


def auto_solve(game, step, cancel_check=None, progress_callback=None,
               stage_cb=None, time_budget=None, **_kwargs):
    """自动规划入口：查表 → 补缺宏 → 混合流水线，全解即停，全败取最优部分。

    stage_cb（2026-10-10 新增）：分阶段流式回调。每当一个候选求解器产出可播的
    动作段，调用 `stage_cb({'label','actions','reps','end','score','phi','solved'})`
    —— GUI 据此**边算边播**每段动画、并按 `score`（并列取 `phi` 最小）维护历史
    最优 checkpoint，取消时恢复到该态（多段播放设计哲学：不让人觉得卡死、进度
    不反悔、打断停在聚拢度最高态）。不传则不流式（保持旧的非流式返回协议，供
    HTTP/headless 等调用方无感使用）。
    """
    t0 = time.time()
    m, n = game.m, game.n
    coords0 = frozenset(tuple(b.location) for b in game.blocks)

    def cancelled():
        return bool(cancel_check and cancel_check())

    def emit(stage, note=''):
        if progress_callback is None:
            return
        try:
            progress_callback({'stage': stage, 'nodes': 0,
                               'path_preview': note})
        except Exception:
            pass

    def emit_stage(label, actions4, reps, end_coords, score, solved):
        """每段产出即上报（若无 stage_cb 或终态缺失则静默跳过）。"""
        if stage_cb is None or end_coords is None:
            return
        try:
            phi = _phi_of(end_coords, m, n)
            stage_cb({'label': label,
                      'actions': list(actions4),
                      'reps': (list(reps) if reps
                               else [None] * len(actions4)),
                      'end': end_coords, 'score': score, 'phi': phi,
                      'solved': bool(solved)})
        except Exception:
            pass

    def out_of_time():
        return time_budget is not None and (time.time() - t0) >= time_budget

    def score_of(cs):
        return gather_metrics(cs, m, n)['score']

    # 已复原：空解（GUI 显示 already_solved）
    if build_game(coords0, m, n).is_solved():
        return [], []

    score0 = score_of(coords0)
    best = None   # {'score', 'actions'(4), 'reps', 'end', 'src'}

    def keep_partial(acts, reps, src):
        """记录部分成果，按「终态聚拢度」择优保留。"""
        nonlocal best
        if not acts:
            return
        end, ok = _end_state(coords0, acts, reps, m, n, step)
        if not ok or end is None:
            return
        sc = score_of(end)
        if best is None or sc > best['score'] + 1e-9:
            reps_pad = list(reps or []) + [None] * (len(acts) - len(reps or []))
            best = {'score': sc, 'actions': list(acts), 'reps': reps_pad,
                    'end': end, 'src': src}

    # ---- ① 查表：有表即最优，亚秒级，不可能吃亏 ----
    if not cancelled() and not out_of_time():
        emit('自动规划·①查表', '有表即最优路径')
        try:
            tres = table_solve(deepcopy(game), step,
                               cancel_check=cancel_check,
                               progress_callback=progress_callback)
        except Exception:
            tres = None
        if tres is not None and tres is not False:
            # (path, rep_cells)；空表/异常路径已在函数内处理
            end, ok = _end_state(coords0, tres[0], tres[1], m, n, step)
            if ok:
                emit_stage('①查表', tres[0], tres[1], end, 1.0, True)
            return tres[0], tres[1]
        # None=无表 / False=状态不在表中 → 落到下一候选

    # ---- ②③ 按空位数路由（探针 2026-10-02：空位≤2 混合快（5.1: 1.4s vs 57.2s），
    #      空位≥3 补缺宏快（06: 1.0s / 07: 0.98s，混合均超时）。两路都尝试，只定先后）----
    _reg, _ov, holes, _out = window_of(coords0, m, n, step)
    gap_first = len(holes) >= 3

    def run_gap():
        """补缺宏：全解 → ('solved', acts, reps)；部分 → ('partial',)；否则 ('fail',)。"""
        emit('自动规划·补缺宏',
             '空位%d个，%s' % (len(holes),
                               'couple→贴边setup→带移让位链→DFS兜底'))
        try:
            gres = solve_gap_macro(deepcopy(game), step,
                                   cancel_check=cancel_check,
                                   progress_callback=progress_callback)
        except Exception as e:
            gres = {'type': 'fill_fail', 'reason': '补缺宏异常: %s' % e}
        if isinstance(gres, tuple):
            end, ok = _end_state(coords0, gres[0], gres[1], m, n, step)
            if ok:
                emit_stage('补缺宏', gres[0], gres[1], end, 1.0, True)
            return ('solved', gres[0], gres[1])
        if isinstance(gres, dict):
            if gres.get('type') == 'fill_stream':
                # 未传 segment_cb 理论上不出现；兜底按成果处理
                if gres.get('solved'):
                    end, ok = _end_state(coords0, gres.get('actions', []),
                                         gres.get('rep_cells', []), m, n, step)
                    if ok:
                        emit_stage('补缺宏', gres.get('actions', []),
                                   gres.get('rep_cells', []), end, 1.0, True)
                    return ('solved', gres.get('actions', []),
                            gres.get('rep_cells', []))
                keep_partial(gres.get('actions', []),
                             gres.get('rep_cells', []), '补缺宏')
                if best is not None:
                    emit_stage('补缺宏·部分', best['actions'], best['reps'],
                               best['end'], best['score'], False)
                return ('partial',)
            if gres.get('type') == 'fill_partial':
                keep_partial(gres.get('actions', []),
                             gres.get('rep_cells', []), '补缺宏')
                if best is not None:
                    emit_stage('补缺宏·部分', best['actions'], best['reps'],
                               best['end'], best['score'], False)
                return ('partial',)
        return ('fail',)

    def run_hybrid():
        """混合流水线：优先从补缺宏 partial 终态续算。全解 → ('solved', a, r)。"""
        seed = coords0
        note = '初始局面'
        if best is not None and best['score'] > score0 + 1e-9:
            seed = best['end']
            note = '补缺宏部分成果终态（聚拢度 %.3f→%.3f）' % (score0, best['score'])
        emit('自动规划·混合流水线', '聚拢↔填洞交替+GBFS，从%s' % note)
        try:
            if seed is coords0:
                hres = hybrid_solve(build_game(seed, m, n), step,
                                    cancel_check=cancel_check,
                                    progress_callback=progress_callback)
            else:
                # 续算带 90s 上限：到点归还部分成果，尽早停（用户拍板）
                deadline = time.time() + _CONTINUE_BUDGET

                def seed_cancel():
                    return ((cancel_check is not None and cancel_check())
                            or time.time() >= deadline)

                hres = hybrid_solve(build_game(seed, m, n), step,
                                    cancel_check=seed_cancel,
                                    progress_callback=progress_callback)
        except Exception:
            hres = False
        if not isinstance(hres, tuple):
            return ('fail',)
        if seed is coords0:
            end, ok = _end_state(coords0, hres[0], hres[1], m, n, step)
            if ok:
                emit_stage('混合流水线', hres[0], hres[1], end, 1.0, True)
            return ('solved', hres[0], hres[1])
        # 前缀（部分成果，已在 run_gap 阶段作为「补缺宏·部分」流式播出）+ 后缀
        # （混合流水线续算）：整链重放验证后才采纳
        acts = list(best['actions']) + list(hres[0])
        reps = list(best['reps']) + list(hres[1] or [])
        a5 = [tuple(a) + ((tuple(r),) if r else (None,))
              for a, r in zip(acts, reps)]
        if replay_and_verify(coords0, m, n, step, a5):
            # 终态须用「前缀+后缀」整链从 coords0 重放得到（后缀单独从 coords0
            # 重放无意义，会污染 checkpoint 坐标）；播放时 GUI 已先播前缀再播后缀，
            # 落点恰为此整链终态。
            end, ok = _end_state(coords0, acts, reps, m, n, step)
            if ok:
                # 只播后缀：前缀已由「补缺宏·部分」播出，避免重复
                emit_stage('混合流水线·续算', hres[0], hres[1], end, 1.0, True)
            return ('solved', acts, reps)
        return ('fail',)

    for which in (['gap', 'hybrid'] if gap_first else ['hybrid', 'gap']):
        if cancelled() or out_of_time():
            break
        if which == 'gap':
            outcome = run_gap()
        else:
            outcome = run_hybrid()
        if outcome[0] == 'solved':
            return outcome[1], outcome[2]
        # partial / fail → 继续下一候选

    # ---- 收尾：全败 ----
    if cancelled():
        return False
    if best is not None and best['score'] > score0 + 1e-9:
        return {'type': 'fill_partial',
                'actions': best['actions'], 'rep_cells': best['reps'],
                'reason': ('自动规划：各求解器均未全解，返回聚拢度提升最大的'
                           '部分成果（%s，聚拢度 %.3f→%.3f）'
                           % (best['src'], score0, best['score'])),
                'solver_name': '自动规划'}
    return {'type': 'fill_fail',
            'reason': '自动规划：查表/补缺宏/混合流水线均未全解',
            'solver_name': '自动规划'}
