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
    ③ 全败时按聚拢度（并列 Φ 最小，见 partial_better）评估部分成果，
       续算或作断点返回。

部分成果链接（chaining）：2026-11-07 泛化为「流式链」——补缺宏 partial
不再只是混合的种子，而是**所有后续候选的起点**：谁播完一段，下一候选就
从该段终态续算（逐段各自验证拼接）；整体失败时返回聚拢度最高（并列 Φ
最小）的部分成果（fill_partial 断点协议，GUI 播到断点供观察/续跑）。

返回协议（与 GUI 对齐）：
    (actions4, rep_cells)          成功（actions 为四元组列表）
    {'type': 'fill_partial', ...}  未全解但有聚拢度提升的部分成果
    {'type': 'fill_fail', ...}     各候选均无成果
    False                          取消

注意：
· 分段流式（2026-11-07 用户拍板「核心思想」）：候选求解器每算完一段
  「定稿不再改」的动作即上报 stage_cb，GUI **边算边播**、后台继续算；
  后续候选从已播终态续算（棋盘播到哪、下一段从哪算起）。不传 stage_cb
  时仍整链返回（HTTP/headless 无感），但内部同样按流式链记账。
· stage_budget（每候选阶段墙钟上限）：None=内置默认（混合 90s / 补缺宏
  30s），0=不限时，>0=用户值——GUI 传设置页「最大等待秒数」
  （gather_params.max_wait_time，用户 2026-11-07 拍板由用户输入、复用
  聚拢停机参数）。到点停该阶段、已播段照常有效，落实「尽早发现、发现就停」。
· hybrid_solve 本身保持纯算法不动（experiments/ 基线不受影响，其分段
  回调为可选参数），hybrid_solve_with_table 保留为旧入口（固定「表→混合」两步）。
"""
import time
import traceback
from copy import deepcopy

from solver.table_solver import table_solve
from solver.ml.gather_solver import gather_metrics
from solver.ml.fill_macro import build_game, _replay_apply, window_of
from solver.ml.gap_solver import solve_gap_macro
from solver.hybrid_solver import hybrid_solve
from solver.ml.invariants import profile_defect  # 平移无关 Φ（复用，非重写）

# 候选阶段墙钟上限的内置默认（秒）：stage_budget=None 时对混合流水线生效，
# 且 2026-11-07 起**同时覆盖「初始局面直跑」与「续算」两分支**——此前只有
# 续算有 90s 上限，直跑分支无自有时限，实测表现为「卡在聚攏+GBFS 不停機、
# 全程零输出」（用户 2026-11-07 报）。混合自然解出时间中位在秒级~十几秒，
# 90 秒足够；到点归还部分成果，落实「算不出来尽早发现、发现就停」（2026-10-02 拍板）。
# GUI 侧由设置页「最大等待秒数」接管：启用=用户值（0=不限时），
# 禁用=回退本默认（与补缺/填洞宏的 30s 内置帽同构）。
_STAGE_BUDGET_DEFAULT = 90.0


def partial_better(sc_new, phi_new, sc_old, phi_old):
    """部分成果择优规则（单一真源，2026-10-15 解耦修复）。

    聚拢度高者胜；完全并列（1e-9 内）取 Φ（剖面缺陷）最小。
    sc_old/phi_old 为 None 表示「尚无最优」（新来者直接胜出）。

    为什么抽成模块级函数：修复前择优规则分裂两处且不一致——求解器
    keep_partial 只比聚拢度（并列先到先得），「并列取 Φ 最小」只在 GUI
    _update_auto_best 实现。后果：① headless 调用方（HTTP API / 实验 /
    批量实验）拿到的 fill_partial 断点并非同规则最优；② 流式播放时
    keep_partial 并列选中的段会被上报播放，GUI 只能在收到的段之间择优，
    救不回没收到的更好段；③ run_hybrid 的续算起点 best['end'] 也建立
    在该次优选择上。择优属于求解器领域知识，GUI 恢复点
    （gui/auto_solve.py _update_auto_best）现引用同一函数，物理同源。
    """
    if sc_old is None:
        return True
    if sc_new > sc_old + 1e-9:
        return True
    return abs(sc_new - sc_old) <= 1e-9 and phi_new < phi_old - 1e-9


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
               stage_cb=None, time_budget=None, stage_budget=None,
               **_kwargs):
    """自动规划入口：查表 → 补缺宏 → 混合流水线，全解即停，全败取最优部分。

    stage_cb（2026-10-10 新增）：分阶段流式回调。每当一个候选求解器产出可播的
    动作段，调用 `stage_cb({'label','actions','reps','end','score','phi','solved'})`
    —— GUI 据此**边算边播**每段动画并维护恢复点 checkpoint，取消时恢复到该态
    （多段播放设计哲学：不让人觉得卡死、进度不反悔、打断停在聚拢度最高态）。
    择优规则 = `partial_better`（聚拢度高者胜、并列 Φ 最小），GUI 恢复点
    选择引用同一函数——规则单一真源，UI 只负责播放与恢复。不传 stage_cb
    则不流式（保持旧的非流式返回协议，供 HTTP/headless 等调用方无感使用）；
    此时 fill_partial 断点同样是该规则下的最优，与流式路径一致。

    流式链（2026-11-07 起）：补缺宏与混合流水线都**分段**上报——每段是
    「定稿、不再修改」的动作前缀（flow，只增不改），后续候选一律从
    flow['end'] 续算（棋盘播到哪、下一段从哪算起），杜绝「段已播出、下一
    候选却从初始局面算」的错位。

    stage_budget：每候选阶段墙钟上限（秒）。None=内置默认（混合
    _STAGE_BUDGET_DEFAULT、补缺/填洞沿用各自 30s），0=不限时，>0=用户值
    （GUI 传设置页「最大等待秒数」）。到点该阶段停机、已播段照常有效。

    time_budget：整体会话上限（秒，沿用；headless/experiments 用，
    与候选间 out_of_time 配合），与 stage_budget 相互独立。
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
            traceback.print_exc()   # §2：except 必须打 traceback，不许静默吞

    def out_of_time():
        return time_budget is not None and (time.time() - t0) >= time_budget

    def score_of(cs):
        return gather_metrics(cs, m, n)['score']

    # 已复原：空解（GUI 显示 already_solved）
    if build_game(coords0, m, n).is_solved():
        return [], []

    score0 = score_of(coords0)
    best = None   # {'score', 'phi', 'actions'(4), 'reps', 'end', 'src'}

    # 流式链（flow）：已采纳/已上报的累积前缀——只增不改，是「定稿段」的
    # 真源。后续候选一律从 flow['end'] 续算，返回的整链解也由它拼出。
    flow = {'acts': [], 'reps': [], 'end': coords0}

    def advance(label, acts, reps, end):
        """采纳一段已定稿动作：并入 flow → 按 partial_better 记整链部分
        成果 → 上报 stage_cb 播放（stage_cb 为空时只记账，headless 无感）。

        acts/reps = 本段新动作（世界绝对坐标），end = 本段重放终态——由
        各候选自己验证（补缺宏 _end_state / 混合 replay / 查表回放），此处
        不再整链重放（旧行为 keep_partial 每段从 coords0 重放整链，流式
        分段后改为「逐段各自验证、整链等价」，与 GUI 逐段播放同一语义）。
        择优规则仍是 partial_better（单一真源，见其 docstring）。
        """
        nonlocal best
        acts = list(acts)
        reps = list(reps or [])
        if len(reps) < len(acts):
            reps += [None] * (len(acts) - len(reps))
        chain_acts = flow['acts'] + acts
        chain_reps = flow['reps'] + reps
        flow['acts'] = chain_acts
        flow['reps'] = chain_reps
        flow['end'] = end
        sc = score_of(end)
        ph = _phi_of(end, m, n)
        if partial_better(sc, ph,
                          best['score'] if best else None,
                          best['phi'] if best else None):
            best = {'score': sc, 'phi': ph, 'actions': chain_acts,
                    'reps': chain_reps, 'end': end, 'src': label}
        emit_stage(label, acts, reps, end, sc,
                   build_game(end, m, n).is_solved())

    def advance_from(start_coords, label, acts, reps):
        """验证并采纳（从 start_coords 重放本段）。失败返回 False。"""
        if not acts:
            return False
        end, ok = _end_state(start_coords, acts, reps, m, n, step)
        if not ok or end is None:
            return False
        advance(label, acts, reps, end)
        return True

    def stage_outcome(seg_base):
        """候选结束时的返回分型：本阶段有新采纳段 → partial（成果保留），
        一段都没有 → fail。"""
        return ('partial',) if len(flow['acts']) > seg_base else ('fail',)

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
        """补缺宏：从 flow['end'] 续算（已播到哪、从哪算起），分段流式采纳。
        返回 ('solved', 全链 acts, 全链 reps) / ('partial',) / ('fail',)。"""
        seed = flow['end']
        seg_base = len(flow['acts'])
        emit('自动规划·补缺宏',
             '空位%d个，%s' % (len(holes),
                               'couple→贴边setup→带移让位链→DFS兜底'))

        def gseg(label, acts5):
            """分段回调（label, 5 元组动作）：换算 4 元组+rep，从当前已播
            终态验证后采纳。已播出的段不再修改（核心思想：定稿即播）。"""
            acts4 = [tuple(a)[:4] for a in acts5]
            reps4 = [tuple(a)[4] if len(a) > 4 else None for a in acts5]
            if not advance_from(flow['end'], label or '补缺宏·段',
                                acts4, reps4):
                print('[自动规划] 补缺宏分段验证失败，丢弃该段（%s 步）'
                      % len(acts4))

        # 每阶段墙钟上限：None=禁用/未传 → 补缺宏沿用内置 30s 安全帽；
        # 0=用户显式不限时；>0=用户值（设置页「最大等待秒数」）。
        gap_kwargs = ({} if stage_budget is None
                      else {'time_budget': stage_budget})
        try:
            gres = solve_gap_macro(build_game(seed, m, n), step,
                                   cancel_check=cancel_check,
                                   progress_callback=progress_callback,
                                   segment_cb=gseg, **gap_kwargs)
        except Exception as e:
            traceback.print_exc()
            gres = {'type': 'fill_fail', 'reason': '补缺宏异常: %s' % e}
        if isinstance(gres, tuple):
            # 单洞快路径（自身不分段）：整段从当前终态验证采纳后即全解。
            # 已有分段时元组按「余量」验证（契约上二者互斥，此分支只作
            # 安全兜底：验证不过就保留已播段，绝不谎报全解）。
            if advance_from(flow['end'], '补缺宏', gres[0], gres[1]):
                return ('solved', flow['acts'], flow['reps'])
            return stage_outcome(seg_base)
        if isinstance(gres, dict):
            gtype = gres.get('type')
            rest = list(gres.get('actions') or [])
            rreps = list(gres.get('rep_cells') or [])
            if gtype == 'fill_stream' and gres.get('solved'):
                # 流式全解：分段回调已播前段，这里只验证采纳「未播余量」
                rest_ok = ((not rest)
                           or advance_from(flow['end'], '补缺宏',
                                           rest, rreps))
                if rest_ok and len(flow['acts']) > seg_base:
                    return ('solved', flow['acts'], flow['reps'])
                print('[自动规划] 补缺宏全解声称无法验证，按部分成果收口')
                return stage_outcome(seg_base)
            if gtype in ('fill_stream', 'fill_partial'):
                if rest:
                    advance_from(flow['end'], '补缺宏·部分', rest, rreps)
                return stage_outcome(seg_base)
            # fill_fail（超时/取消/异常）：已播段仍有效（如贪心流式后超时）
            return stage_outcome(seg_base)
        return stage_outcome(seg_base)

    def run_hybrid():
        """混合流水线：从 flow['end'] 续算，聚拢段/搜索段分段流式采纳。
        全解 → ('solved', 全链 acts, 全链 reps)；否则见 stage_outcome。"""
        seed = flow['end']
        seg_base = len(flow['acts'])
        if seed is coords0:
            note = '初始局面'
        else:
            note = '已播前缀终态（聚拢度 %.3f→%.3f）' % (score0, score_of(seed))
        emit('自动规划·混合流水线', '聚拢+GBFS，从%s' % note)

        def hseg(seg):
            # 混合段的 end 即世界坐标（其 base = flow['end']），直通采纳
            advance(seg['label'], seg.get('actions'), seg.get('reps'),
                    seg['end'])

        # 每阶段墙钟上限（用户 2026-11-07 拍板「由用户输入」）：
        # stage_budget=None → 内置默认（覆盖直跑与续算两分支——修复前直跑
        # 分支无自有时限，实测「卡在聚攏+GBFS 不停機」）；0=不限时；>0=用户值。
        # 到点经 cancel_check 让聚拢逐轮、搜索逐节点退出，已播段照常有效。
        budget = _STAGE_BUDGET_DEFAULT if stage_budget is None else stage_budget
        if budget:
            deadline = time.time() + budget

            def stage_cancel():
                return cancelled() or time.time() >= deadline
        else:
            stage_cancel = cancelled
        try:
            hres = hybrid_solve(build_game(seed, m, n), step,
                                cancel_check=stage_cancel,
                                progress_callback=progress_callback,
                                segment_cb=hseg)
        except Exception:
            traceback.print_exc()
            hres = False
        if not isinstance(hres, tuple):
            return stage_outcome(seg_base)
        if len(flow['acts']) == seg_base:
            # 分段回调未触发（experiments 直改 hybrid_solve 的 mock / 理论
            # 边界）：按整链补记。标签沿用旧协议——script_test_hybrid_stream
            # 的「混合流水线·续算」断言依赖它。
            label = '混合流水线·续算' if seed is not coords0 else '混合流水线'
            if not advance_from(seed, label, hres[0], hres[1] or []):
                return ('fail',)   # 整链验证不过：不谎报全解，已播段保留
        return ('solved', flow['acts'], flow['reps'])

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
                'score': best['score'], 'phi': best['phi'],
                'reason': ('自动规划：各求解器均未全解，返回聚拢度提升最大的'
                           '部分成果（%s，聚拢度 %.3f→%.3f，Φ %.1f）'
                           % (best['src'], score0, best['score'], best['phi'])),
                'solver_name': '自动规划'}
    return {'type': 'fill_fail',
            'reason': '自动规划：查表/补缺宏/混合流水线均未全解',
            'solver_name': '自动规划'}
