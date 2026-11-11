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
        空位 = 1 → 补缺宏先行（单洞 ⟺ 恰 1 块在窗外，补缺宏确定性直解；
                   2026-11-11 修：内外洞一律，先前只覆盖贴边/角）
        空位 = 2 → 混合流水线先行（实测 5.1：混合 1.4s vs 补缺宏 57.2s）
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
  30s），0=不限时，>0=用户值——GUI 曾传设置页「最大等待秒数」
  （gather_params.max_wait_time，用户 2026-11-07 拍板由用户输入、复用
  聚拢停机参数）。到点停该阶段、已播段照常有效，落实「尽早发现、发现就停」。
· total_budget（整轮墙钟硬上限，2026-11-09 新增）：给整轮一个单调
  deadline，首个候选最多占 _TOTAL_SHARE_FIRST 比例、余额让渡给后续候选；
  到点连正在跑的候选也经 cancel_check 退出，已播段照常有效。
  stage_budget 保留原义供 HTTP/实验基线对照。
· idle_budget（连续无进展停机，2026-11-11 用户拍板，GUI 现行语义）：
  设置页「最大等待秒数」不再是「从开机到停机最多 T 秒」，而是**自上次
  采纳一段定稿动作起、连续 T 秒没有新进展才停**。滑动窗口，有进展就
  一直往后滑，绝不会因为「前面已经算久了」把快要复原的解砍掉
  （用户实测：明明离复原很近、再启动一次几秒就解开）。
  首个候选的无进展窗口取半，余额让渡给第二候选（沿用
  _TOTAL_SHARE_FIRST 的防饿死语义）；两路都停了才收尾。
  idle 模式下关掉候选自带的墙钟安全帽（补缺宏 30s / 混合 90s），
  否则那些固定帽子会先于「连续 T 秒无进展」砍停，语义又退回硬上限。
  total_budget 仍保留（可选硬上限，给 HTTP/实验用）；两者可并存，
  谁先到谁生效。
· 单洞收口（同轮，2026-11-11）：候选顺序按**初始局面**的洞数算死，
  而流式第一候选可能已把 flow['end'] 推到「恰好 1 洞」——这时第二候选
  仍按初始顺序走混合，单洞的补缺宏确定性快路径没被识别，停在
  fill_partial；玩家再点一次求解（以单洞态为起点）却 0.01s 复原
  （6×6 s2 三局实测 3/3）。故两候选跑完、未全解时用 flow['end'] 重测，
  命中单洞就补跑一次补缺宏（自带 5s 短帽、不吃 idle 窗口），把
  「再点一次」搬进本轮。⚠️ 这不是预算问题：只改 idle_budget 的 A/B
  解出率仍是 3/6，加上收口才把这类局收回。
· rng_seed（2026-11-09 新增）：整数随机种子，分别注入补缺宏链
  （random.Random(seed)）与混合聚拢轮（gather_solve 的 seed），**消除
  随机漂移**——同局面 / 同种子 / 同预算配置下解链通常逐位一致，A/B
  才可比。⚠️ 带墙钟预算时**不作绝对保证**：到点切断的时机受 CPU 调度
  影响，大盘 5 局种子探针里 4 局固定种子两次一致、1 局偶发不一致
  （该局单独复跑、带预热复跑都一致）。故 A/B 比成功数 / 墙钟 /
  聚拢度，别把 fp 相等当前提。不传时沿用旧行为：求解内部原本是
  `rng = rng or random.Random()` 无参播种 + 聚拢轮吃全局 random，
  同局面两次可能一个解出、一个只回部分成果（实测 6×6 seed=3）。
· hybrid_solve 本身保持纯算法不动（experiments/ 基线不受影响，其分段
  回调为可选参数），hybrid_solve_with_table 保留为旧入口（固定「表→混合」两步）。
"""
import random
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

# 整轮预算（total_budget）下首个候选最多占用的比例。不能让第一候选吃满
# 整轮：实测 6×6 补缺宏超时后，混合流水线仍能在续算里再播一段搜索段，
# 直接共享 deadline 会把第二候选饿死。余额自动让渡（用绝对 deadline，
# 第一候选提前结束时第二候选可用到整轮末尾）。
# 0.5 = 均分：2026-11-09 份额敏感性对照（6 局边界案 × 3 档，固定 rng_seed）
# 解出数 1/6 三档相同、墙钟均值 18.49/18.46/18.38s 基本持平，
# 部分成果聚拢度 σ 均值 0.9669 / 0.9601 / 0.9567 单调递减 → 取 0.5。
_TOTAL_SHARE_FIRST = 0.5

# 单洞收口（2026-11-11）：两候选跑完、续算态恰好 1 洞时补跑一次补缺宏的
# 墙钟短帽。单洞是 solve_gap_any 的确定性直解（实测 0.01s），5s 足够，
# 且不吃 idle 窗口（否则窗口刚过期时收口会被 cancel_check 立刻掐掉）。
_SINGLE_HOLE_CAP = 5.0


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
               rng_seed=None, total_budget=None, scorer=None,
               route_fn=None, stop_fn=None, idle_budget=None,
               bulk_static=True, **_kwargs):
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

    total_budget：整轮墙钟硬上限（秒，None/0=不限时）。与 stage_budget
    的「每候选各一份」不同，这是整轮共享的单调 deadline，且会传进正在
    跑的候选的 cancel_check；首个候选最多占 _TOTAL_SHARE_FIRST。
    idle_budget：连续无进展停机（秒，None/0=不启用，走 total_budget 旧
    语义）。GUI 现行参数：每采纳一段定稿动作就把停机时刻往后推 T 秒，
    连续 T 秒没有新段才停；首个候选窗口取半让给第二候选。详见模块
    docstring。启用时关掉候选自带的 30s/90s 墙钟安全帽，改由动态
    cancel_check 统一管。与 total_budget 可并存，谁先到谁生效。
    rng_seed：整数种子，注入补缺宏与混合聚拢轮；不传=旧随机行为。

    scorer / route_fn（2026-11-10，可注入实验接缝）：scorer 见
    search_core.guided_reduce_one（只经混合流水线生效）；route_fn 签名
    (holes, coords, m, n, step) -> bool，True=补缺宏先行，默认 None =
    len(holes) >= 3 or len(holes) == 1（2026-11-11 起单洞一律补缺宏先）。
    stop_fn（同轮 D2 第二轮）是 GBFS 的终止判据注入，
    签名 (value, holes) -> bool，默认 None = 洞数严格变少，同样只经混合
    流水线生效。**预设注入与旧版逐位一致**，玩家侧不传；三者只把
    「换一个打分 / 换一个路由 / 换一个终止判据」从改搜索核心降成换一个参数。
    """
    t0 = time.time()
    # 共享总预算（phase-sharing）：显式 total_budget 优先；否则若调用方只给了
    # time_budget（GUI/实验的常态），把它当作共享总预算，使「第二个候选」
    # 必然分到份额、不被第一个吃光——这是 2026-11-10 从盲区实测收回 7/8 局
    # 的根因修复（原默认不传 total_budget，混合流水线先跑会耗尽全部预算，
    # 补缺宏（对角缺口 0.0s 确定性可解）始终没机会，被误判为公式盲区）。
    _shared = total_budget if (total_budget is not None and total_budget > 0) \
        else (time_budget if (time_budget is not None and time_budget > 0)
              else None)
    total_deadline = (t0 + _shared) if _shared is not None else None
    # 连续无进展停机（2026-11-11）：滑动窗口，自上次「采纳一段定稿动作」起
    # _idle 秒。首个候选窗口取半（防第二候选被饿死，同 _TOTAL_SHARE_FIRST），
    # 有进展就不断往后滑 → 不再有「开机到停机最多 T 秒」的硬砍。
    _idle = (idle_budget if (idle_budget is not None and idle_budget > 0)
             else None)
    idle_window = [_idle * _TOTAL_SHARE_FIRST] if _idle is not None else None
    idle_deadline = ([t0 + idle_window[0]]
                     if _idle is not None else None)
    m, n = game.m, game.n
    coords0 = frozenset(tuple(b.location) for b in game.blocks)

    # 整体平移消去（防偏移·序列改写，2026-11-11 用户要求）：
    # 求解出的每步只确定「哪一片相对其余滑了 δ」，绝对位置还有一整个
    # 整体平移的自由度（复原判定只看形状，见 game.is_solved / try_move_ex
    # 的 all_selected 注释）。把它当魔方「整体转体」消去：能改成「推小片」
    # 就改（大片在画面上完全不动），改不动的把这次整体平移记进后续步的
    # 分割线坐标里吸收。写入 flow['acts'] 的因此是**改写后**的动作链（可
    # 直接从 coords0 回放到改写终态，终态只是整体挪了整格 → 仍算还原）；
    # 求解器自身续算仍用 flow['end'] 的原始绝对坐标。
    _rw = None
    if bulk_static:
        from solver.anti_drift import BulkStaticRewriter
        _rw = BulkStaticRewriter(coords0, m, n, step)

    def emit_rewrite(acts, reps, end):
        """→ (改写后 acts4, reps, 终态坐标)。关闭改写时原样返回。"""
        if _rw is None:
            return list(acts), list(reps or []), end
        reps = list(reps or [])
        if len(reps) < len(acts):
            reps += [None] * (len(acts) - len(reps))
        five = []
        for i, a in enumerate(acts):
            rp = reps[i]
            five.append(tuple(a)[:4] + (tuple(rp) if rp else None,))
        e_acts, e_end = _rw.feed(five)
        return ([tuple(a[:4]) for a in e_acts], [a[4] for a in e_acts], e_end)


    def cancelled():
        return bool(cancel_check and cancel_check())

    def touch_progress():
        """采纳一段定稿动作 = 有进展 → 把停机窗口往后滑 T 秒。"""
        if idle_deadline is not None:
            idle_deadline[0] = time.time() + idle_window[0]

    def idle_expired():
        return idle_deadline is not None and time.time() >= idle_deadline[0]

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
        if time_budget is not None and (time.time() - t0) >= time_budget:
            return True
        return total_deadline is not None and time.time() >= total_deadline

    def score_of(cs):
        return gather_metrics(cs, m, n)['score']

    # 已复原：空解（GUI 显示 already_solved）
    if build_game(coords0, m, n).is_solved():
        return [], []

    score0 = score_of(coords0)
    best = None   # {'score', 'phi', 'actions'(4), 'reps', 'end', 'src'}

    # 流式链（flow）：已采纳/已上报的累积前缀——只增不改，是「定稿段」的
    # 真源。后续候选一律从 flow['end'] 续算，返回的整链解也由它拼出。
    flow = {'acts': [], 'reps': [], 'end': coords0, 'single_hole': False}

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
        # 改写（整体平移消去）必须在并链之前：flow['acts'] 存的是改写后的链，
        # 与玩家盘面一致（可直接回放）；end 仍是求解器视角的原始终态。
        e_acts, e_reps, e_end = emit_rewrite(acts, reps, end)
        chain_acts = flow['acts'] + e_acts
        chain_reps = flow['reps'] + e_reps
        flow['acts'] = chain_acts
        flow['reps'] = chain_reps
        flow['end'] = end
        # 单洞预判（2026-11-11）：续算态一旦恰好 1 洞，就是 solve_gap_macro 的
        # 确定性直解（0.0s）。标记下来，让正在跑的混合候选**立刻让位**，别在
        # 1 洞态上再跑一遍 GBFS 白烧几秒（用户实测「最後階段硬靠 GBFS 搜一會
        # 才發現能用填洞補」的根因：路由只按初始局面算一次，续算态没重测）。
        try:
            _solved_now = build_game(end, m, n).is_solved()
            _hn = len(window_of(end, m, n, step)[2])
        except Exception:
            _solved_now, _hn = False, -1
        flow['single_hole'] = (_hn == 1 and not _solved_now)
        sc = score_of(end)
        ph = _phi_of(end, m, n)
        if partial_better(sc, ph,
                          best['score'] if best else None,
                          best['phi'] if best else None):
            best = {'score': sc, 'phi': ph, 'actions': chain_acts,
                    'reps': chain_reps, 'end': end, 'src': label}
        emit_stage(label, e_acts, e_reps, e_end, sc,
                   build_game(end, m, n).is_solved())
        touch_progress()   # 定稿段被采纳 = 有进展，滑动停机窗口

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

    def try_single_hole_closeout():
        """续算态恰好 1 洞时，直接跑确定性补缺宏收口（0.0s），返回 True=全解。

        单洞是 ``solve_gap_macro`` / ``solve_gap_any`` 的确定性直解，比在
        1 洞态上再跑一遍 GBFS 快几个数量级。用于两个时机：
          ① 每个候选开跑前（已单洞就别再跑整个候选）；
          ② 全部候选跑完的兜底。
        """
        if cancelled() or out_of_time():
            return False
        if not flow['acts'] or flow['end'] is coords0:
            return False
        if build_game(flow['end'], m, n).is_solved():
            return False
        _r, _o, holes2, _u = window_of(flow['end'], m, n, step)
        if len(holes2) != 1:
            return False
        seed2 = flow['end']
        try:
            gres2 = solve_gap_macro(build_game(seed2, m, n), step,
                                    time_budget=_SINGLE_HOLE_CAP,
                                    cancel_check=cancel_check)
        except Exception:
            traceback.print_exc()
            gres2 = None
        if isinstance(gres2, tuple) and advance_from(
                seed2, '补缺宏·单洞收口', gres2[0], gres2[1]):
            return True
        return False

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
                e_acts, e_reps, e_end = emit_rewrite(tres[0], tres[1], end)
                emit_stage('①查表', e_acts, e_reps, e_end, 1.0, True)
                return e_acts, e_reps
            return tres[0], tres[1]
        # None=无表 / False=状态不在表中 → 落到下一候选

    # ---- ②③ 按空位数路由（探针 2026-10-02：空位≤2 混合快（5.1: 1.4s vs 57.2s），
    #      空位≥3 补缺宏快（06: 1.0s / 07: 0.98s，混合均超时）。两路都尝试，只定先后）----
    _reg, _ov, holes, _out = window_of(coords0, m, n, step)
    # 默认路由：空位≥3 补缺宏先、空位=2 混合先（探针 5.1/06/07）。
    # 例外（2026-11-11）：单洞一律补缺宏先，与空位≥3 合并为 gap_first 初值。
    # 单洞时窗口必恰缺 1 格、等价于恰好 1 块在窗外，补缺宏(solve_gap_any)是
    # 确定性直解（0.0s）；若默认走混合(聚攏)先，会白烧聚攏/GBFS 时间再才填洞
    # （实测 5×5 s2 单内洞默认路由 7.5s、填洞先 0.01s，解同长却浪费时间）。
    # 先前只覆盖「单洞+贴边/角」漏了单内洞；现对内外洞一律强制补缺宏先
    # （盲区 CORNER 修复同一逻辑，范围放宽）。
    _gap_first_default = len(holes) >= 3 or len(holes) == 1
    gap_first = (route_fn(len(holes), coords0, m, n, step)
                 if route_fn is not None else _gap_first_default)

    def run_gap(phase_deadline=None):
        """补缺宏：从 flow['end'] 续算（已播到哪、从哪算起），分段流式采纳。
        返回 ('solved', 全链 acts, 全链 reps) / ('partial',) / ('fail',)。

        phase_deadline：整轮预算下本阶段的绝对截止时刻（None=沿用旧语义）。
        """
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
        if rng_seed is not None:
            # 每个候选各自从同一整数种子新建 Random，互不消耗状态，
            # 与「先跑哪个候选」无关，同局面同种子解链逐位一致。
            gap_kwargs['rng'] = random.Random(rng_seed)
        gap_cancel = cancel_check
        if phase_deadline is not None:
            left = max(0.01, phase_deadline - time.time())
            cur = gap_kwargs.get('time_budget')
            gap_kwargs['time_budget'] = (left if cur in (None, 0)
                                         else min(cur, left))

            def gap_cancel(_inner=cancel_check, _dl=phase_deadline):
                return ((_inner() if _inner is not None else False)
                        or time.time() >= _dl)
        elif idle_deadline is not None:
            # 连续无进展语义：补缺宏自带的 30s 墙钟帽会先于「连续 T 秒无进展」
            # 砍停，语义又退回硬上限 → 关掉，改由动态 cancel_check 统一管
            # （外部取消 / idle 窗口 / 可选 total_deadline，谁先到谁生效）。
            gap_kwargs['time_budget'] = 0

            def gap_cancel(_inner=cancel_check):
                return ((_inner() if _inner is not None else False)
                        or idle_expired()
                        or (total_deadline is not None
                            and time.time() >= total_deadline))
        try:
            gres = solve_gap_macro(build_game(seed, m, n), step,
                                   cancel_check=gap_cancel,
                                   progress_callback=progress_callback,
                                   segment_cb=gseg, **gap_kwargs)
        except Exception as e:
            traceback.print_exc()
            gres = {'type': 'fill_fail', 'reason': '补缺宏异常: %s' % e}
        if isinstance(gres, tuple):
            # 整段解（单洞快路径/自身不分段）：从当前已播终态验证采纳后即全解。
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

    def run_hybrid(phase_deadline=None):
        """混合流水线：从 flow['end'] 续算，聚拢段/搜索段分段流式采纳。
        全解 → ('solved', 全链 acts, 全链 reps)；否则见 stage_outcome。

        phase_deadline：整轮预算下本阶段的绝对截止时刻（None=沿用旧语义）。
        """
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
        if phase_deadline is not None:
            left = max(0.01, phase_deadline - time.time())
            budget = left if not budget else min(budget, left)
        elif idle_deadline is not None:
            # 连续无进展语义：混合流水线自带的 90s 帽同样要关掉（见 run_gap）
            budget = 0
        if budget:
            deadline = time.time() + budget

            def stage_cancel():
                if cancelled() or time.time() >= deadline:
                    return True
                # 续算态已单洞：立刻让位给确定性补缺宏快路径——别在 1 洞态
                # 上再 GBFS 一遍（用户实测「最後階段白搜几秒」的根因）。
                if flow.get('single_hole'):
                    return True
                return (total_deadline is not None
                        and time.time() >= total_deadline)
        else:
            def stage_cancel():
                return bool(cancelled()) or bool(flow.get('single_hole'))
        if idle_deadline is not None and phase_deadline is None:
            _stage_cancel_base = stage_cancel

            def stage_cancel(_base=_stage_cancel_base):
                return (_base() or idle_expired()
                        or (total_deadline is not None
                            and time.time() >= total_deadline))
        try:
            hres = hybrid_solve(build_game(seed, m, n), step,
                                cancel_check=stage_cancel,
                                progress_callback=progress_callback,
                                segment_cb=hseg, gather_seed=rng_seed,
                                scorer=scorer, stop_fn=stop_fn)
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

    _order = ['gap', 'hybrid'] if gap_first else ['hybrid', 'gap']
    for _idx, which in enumerate(_order):
        if cancelled() or out_of_time():
            break
        # 单洞预判：续算态已 1 洞 → 先跑确定性补缺宏，别让整个候选白跑。
        if flow.get('single_hole') and try_single_hole_closeout():
            return flow['acts'], flow['reps']
        if idle_window is not None:
            # 首个候选的无进展窗口取半、余额让给第二候选；每换一个候选都
            # 重发一份窗口（否则第一候选耗尽后第二候选一进来就已过期）。
            # ⚠️ idle 到期**不放进 out_of_time()**：那会让整轮直接 break，
            # 第二候选（常是 0.0s 确定性直解的那个）反而永远没机会。
            idle_window[0] = (_idle * _TOTAL_SHARE_FIRST
                              if _idx == 0 else _idle)
            idle_deadline[0] = time.time() + idle_window[0]
        phase_deadline = None
        if total_deadline is not None:
            # 首个候选让出 _TOTAL_SHARE_FIRST 之外的额度；第二候选直接用
            # 整轮 deadline（首候选提前结束时余额自动落到这里）。
            phase_deadline = (t0 + (total_deadline - t0) * _TOTAL_SHARE_FIRST
                              if _idx == 0 else total_deadline)
        if which == 'gap':
            outcome = run_gap(phase_deadline)
        else:
            outcome = run_hybrid(phase_deadline)
        if outcome[0] == 'solved':
            return outcome[1], outcome[2]
        # partial / fail → 继续下一候选

    # ---- 单洞收口（2026-11-11）：把「再点一次求解」搬进本轮 ----
    # 实测（6×6 s2 seed 2000/2001/2005）：第一候选补缺宏流式跑到预算用尽，
    # 已把局面推到「恰好 1 洞」，却停在 fill_partial；玩家再点一次求解，
    # 新的一轮以单洞态为起点走补缺宏确定性快路径，3/3 都 0.01s 复原。
    # 根因不是预算本身（把 20s 改成连续无进展停机，A/B 解出率仍 3/6），
    # 而是候选顺序按**初始局面**算死，续算态的单洞没被重新识别。
    # 这里在两候选跑完、尚未全解时用当前 flow['end'] 重测一次；命中单洞
    # 就补跑一次补缺宏，把「再点一次」变成一次求解内部的事。
    if try_single_hole_closeout():
        return flow['acts'], flow['reps']

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
