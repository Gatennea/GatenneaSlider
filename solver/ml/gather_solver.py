# -*- coding: utf-8 -*-
r"""
聚拢求解器 — 只做「聚拢」，不追求完整还原

与 emd/strategy 贪心的区别：
    1. 目标函数改为「聚拢度 = 重叠率」（0~1，1=还原，极限 0）。
    2. 无论是否还原，都返回动作序列 + 指标轨迹，不再用 False 丢弃进展。
    3. 停机条件：记录历史最优聚拢度，连续 patience 步没有改进就停机。
    4. 每步通过 progress_callback 上报当前指标，供 GUI 实时展示。

「聚拢度」指标（gather_metrics 返回）：
    score      : 聚拢度 = 重叠率 = 与 m×n 或 n×m 矩形的最佳重叠块数 / total
                 —— 平移不变、旋转/镜像/转置对称（矩形本身对称，且枚举两朝向）
    overlap    : 最佳重叠块数
    bbox       : 边界盒 (高, 宽)
    fill_rate  : 填充率 = m*n / bbox_area（辅助，用于 tiebreak/展示）
    over_area  : 超出目标面积的部分

运行测试：
    D:\python\python.exe -m solver.ml.gather_solver [m n step]
"""

import sys
import time
import random

from game import SliderMatrix
from solver.actions import enumerate_valid_actions, apply_action
from solver.state import snapshot, restore
from solver.table_core import canonicalize
from solver.ml.strategy_solver import _find_rep_cell


# ---------------------------------------------------------------------------
# 聚拢度指标
# ---------------------------------------------------------------------------
def max_overlap(coords, m, n):
    """与 m×n 或 n×m 矩形（任意平移）的最佳重叠方块数。

    平移不变：枚举所有矩形左上角位置。
    转置对称：同时考虑 m×n 与 n×m 两个朝向。
    用二维前缀和 O(1) 查询任意矩形内方块数。
    """
    total = m * n
    if len(coords) != total:
        return 0
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    min_r, max_r = min(rs), max(rs)
    min_c, max_c = min(cs), max(cs)

    best = 0
    for rh, cw in ((m, n), (n, m)):
        # 网格覆盖范围：所有可能被矩形覆盖到的格子
        gr0 = min_r - rh + 1   # 网格行 0 对应的实际行
        gc0 = min_c - cw + 1   # 网格列 0 对应的实际列
        R = (max_r + rh - 1) - gr0 + 1
        C = (max_c + cw - 1) - gc0 + 1

        # 二维前缀和 ps[i+1][j+1] = 前 i 行、前 j 列方块数之和
        ps = [[0] * (C + 1) for _ in range(R + 1)]
        grid = [[0] * C for _ in range(R)]
        for r, c in coords:
            ri = r - gr0
            ci = c - gc0
            if 0 <= ri < R and 0 <= ci < C:
                grid[ri][ci] = 1
        for i in range(R):
            row_acc = 0
            for j in range(C):
                row_acc += grid[i][j]
                ps[i + 1][j + 1] = ps[i][j + 1] + row_acc

        # 枚举矩形左上角 (r0, c0)
        for r0 in range(min_r - rh + 1, max_r + 1):
            ri = r0 - gr0
            r2 = ri + rh
            for c0 in range(min_c - cw + 1, max_c + 1):
                ci = c0 - gc0
                c2 = ci + cw
                cnt = ps[r2][c2] - ps[ri][c2] - ps[r2][ci] + ps[ri][ci]
                if cnt > best:
                    best = cnt
                    if best == total:
                        return total
    return best


def gather_score(coords, m, n):
    """聚拢度：0~1，1=还原，极限 0（重叠率）。"""
    total = m * n
    return max_overlap(coords, m, n) / total if total else 0.0


def gather_metrics(coords, m, n):
    """计算当前坐标集合的「聚拢度」指标。"""
    if not coords:
        return {'score': 0.0, 'overlap': 0, 'bbox': (0, 0),
                'bbox_area': 0, 'fill_rate': 0.0, 'over_area': float('inf')}
    total = m * n
    overlap = max_overlap(coords, m, n)
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    h = max(rs) - min(rs) + 1
    w = max(cs) - min(cs) + 1
    bbox_area = h * w
    fill_rate = total / bbox_area if bbox_area else 0.0
    over_area = max(0, bbox_area - total)
    return {'score': overlap / total, 'overlap': overlap, 'bbox': (h, w),
            'bbox_area': bbox_area, 'fill_rate': fill_rate, 'over_area': over_area}


def _game_coords(game):
    return frozenset((b.location[0], b.location[1]) for b in game.blocks)


# ---------------------------------------------------------------------------
# Mod 不變量（着色器規律）
# ---------------------------------------------------------------------------
def _count_by_mod(coords, step):
    """統計每種 (r%step, c%step) 類別的方塊數量。"""
    counts = {}
    for r, c in coords:
        key = (r % step, c % step)
        counts[key] = counts.get(key, 0) + 1
    return counts


def detect_target_corner(coords, m, n, step):
    """根據着色不變量預判目標窗口的左上角模偏移 (r0, c0)。

    返回 (r0, c0) 或 None：
      - step 整除 m 且整除 n：所有 (r0,c0) 均可，無法約束 → 回傳 None
      - 否則：枚舉 step×step 種可能偏移，選出「與當前方塊計數完全吻合」的那一種；
        若有零或多個吻合，回傳_None（表示偏移不明確，不強加約束）。

    當 m 不被 step 整除而 n 被整除時，r0 唯一但 c0 任意（所有 c0 等價），
    此時固定選 (r0, 0)。
    """
    if step <= 1:
        return None
    if m % step == 0 and n % step == 0:
        return None

    block_counts = _count_by_mod(coords, step)

    def count_window(mw, nw, R, C):
        """mw×nw 窗口從 (R,C) 開始的 mod 類別分佈。"""
        cnts = {}
        for r in range(R, R + mw):
            for c in range(C, C + nw):
                cat = (r % step, c % step)
                cnts[cat] = cnts.get(cat, 0) + 1
        return cnts

    # 枚舉所有 (R, C)，記錄同時吻合 (m,n) 和 (n,m) 朝向的解
    # 優先選 r0（當 m 不整除 step 時有約束），c0 取第一匹配
    matches = [
        (R, C) for R in range(step) for C in range(step)
        if count_window(m, n, R, C) == block_counts
    ]
    if not matches:
        return None
    # 若 m 不整除 step，r0 是唯一約束；用第一個 r0 對應的最小 C
    if m % step != 0:
        best_r0 = matches[0][0]
        c_candidates = [C for R, C in matches if R == best_r0]
        return (best_r0, min(c_candidates))
    # 否則返回第一匹配（r0 任意，c0 唯一或有約束）
    return matches[0]


def _is_mod_compliant(coords, step, r0, c0):
    """計算當前狀態相對目標窗口 (r0,c0) 的「mod 一致性分」。

    每個方塊的 mod 類別 ((r-r0)%step, (c-c0)%step) 落在 block_counts 中時得分 +1；
    得分越高代表狀態越貼近目標窗口（而非某個錯誤的偏移）。
    用於排序時優先選擇 mod 更接近目標的候選。
    """
    bc = _count_by_mod(coords, step)
    score = 0
    for r, c in coords:
        cat = ((r - r0) % step, (c - c0) % step)
        score += bc.get(cat, 0)
    return score


# ---------------------------------------------------------------------------
# 路径优化：去环 + 徘徊压缩
# ---------------------------------------------------------------------------
_DIR_INV = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}


def _moved_group(before_coords, after_coords):
    """一步执行后移动的方块坐标集合（落点），用于判断「移动的是不是同一部分」"""
    return frozenset(c for c in after_coords if c not in before_coords)


def _moved_shape_key(coords):
    """移动部分（落点集合）的形状键：坐标归一化（减最小行/列）后 frozenset。

    平移不变：同一组方块不管被推到哪个位置，形状键都相同。
    用于徘徊识别——「移动的部分形状没变」。
    """
    if not coords:
        return frozenset()
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    min_r, min_c = min(rs), min(cs)
    return frozenset((r - min_r, c - min_c) for r, c in coords)


def _is_same_op_reverse(a, c):
    """动作 a 与 c 是否同缝隙、同侧、方向互为反向"""
    return (a[0] == c[0] and a[1] == c[1] and a[2] == c[2]
            and _DIR_INV.get(a[3]) == c[3])


def _optimize_path(start_hash, actions, rep_cells, trace, hashes, moved_groups):
    """路径优化：去环 + 徘徊压缩。

    去环：状态重复（canonical hash 相同）的段之间是废步，删除；
         最后一步无条件保留，保证终点状态不变。
    徘徊压缩：连续两步「同缝隙、同侧、方向相反 且 移动部分形状相同」
              = 来回徘徊（推出去又推回来），两步行等价于没走，删除。
              —— 形状用哈希比较（平移不变），符合「移动部分形状没变」的判据。
              同方向连续推两步形状也不变，但方向相同不是徘徊，不会被误删。
    返回优化后的 (actions, rep_cells, trace)。不做规则重放验证（调用方负责）。
    """
    if len(actions) < 2:
        return actions, rep_cells, trace

    # 每步移动部分的形状键
    shapes = [_moved_shape_key(mg) for mg in moved_groups]

    # 1. 去环：只保留「首次出现」的状态，跳过回到旧状态的环
    seen = {start_hash}
    new_a, new_r, new_t, new_s = [], [], [], []
    last = len(actions) - 1
    for i, (act, rep, tr, h) in enumerate(zip(actions, rep_cells, trace, hashes)):
        if h in seen and i < last:
            continue
        seen.add(h)
        new_a.append(act)
        new_r.append(rep)
        new_t.append(tr)
        new_s.append(shapes[i])
    actions, rep_cells, trace, shapes = new_a, new_r, new_t, new_s

    # 2. 徘徊压缩：连续两步互逆 + 移动部分形状相同
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(actions) - 1:
            if (_is_same_op_reverse(actions[i], actions[i + 1])
                    and shapes[i] == shapes[i + 1] and shapes[i]):
                del actions[i + 1]
                del actions[i]
                del rep_cells[i + 1]
                del rep_cells[i]
                del trace[i + 1]
                del trace[i]
                del shapes[i + 1]
                del shapes[i]
                changed = True
            else:
                i += 1

    return actions, rep_cells, trace


# ---------------------------------------------------------------------------
# 主求解函数
# ---------------------------------------------------------------------------
def gather_solve(game, step: int, max_steps=500, patience=150,
                 max_wait_time=20, target_gather_score=1.0, aggressiveness=0.2,
                 cancel_check=None, progress_callback=None,
                 target_corner=None):
    """贪心聚拢：每步选聚拢度（重叠率）最高的动作，连续 patience 步无改进则停机。

    参数（传 None 表示「不设限」）：
        max_steps         : 最大步数上限（None = 无限，靠其他停机条件退出）
        patience          : 连续多少步聚拢度无改进历史最优则停机（None = 不因停滞停机）
        max_wait_time     : 求解时间上限（秒），None 或 0 表示不限时
        target_gather_score : 聚拢度达到该值即提前停机（None = 不设目标；1.0 = 完全还原）
        aggressiveness    : 激进程度 = 允许每步选择的聚拢度比「当前最佳候选」
                            低多少（None = 不设限，任意候选都允许）
        target_corner     : (r0, c0) 预先判定的目标窗口左上角模偏移；None = 自动探测
    """
    m, n = game.m, game.n
    total = m * n

    actions = []
    rep_cells = []
    trace = []
    hashes = []        # 每步执行后的 canonical hash
    moved_groups = []  # 每步移动的方块组
    visited = set()
    stuck = 0

    # 检测目标角点（着色不变量约束）
    if target_corner is None:
        start_coords = _game_coords(game)
        target_corner = detect_target_corner(start_coords, m, n, step)
    # target_corner 为 None 表示「无 mod 约束」（step 整除 m 且整除 n）
    _mod_compliant = (_is_mod_compliant
                      if target_corner is not None else None)
    _mod_r0, _mod_c0 = target_corner if target_corner else (0, 0)

    start_time = time.time()
    start_hash = canonicalize(_game_coords(game))
    start_metrics = gather_metrics(_game_coords(game), m, n)
    best_score = 0.0
    best_metrics = start_metrics
    best_snap = snapshot(game)
    best_idx = 0
    no_improve = 0

    reason = 'max_steps'  # 默认：步数上限耗尽（或 None 时仅剩其他停机条件）
    step_iter = range(max_steps) if max_steps is not None else iter(int, 1)
    for i in step_iter:
        if cancel_check and cancel_check():
            reason = 'cancelled'
            break
        if game.is_solved():
            reason = 'solved'
            break
        if max_wait_time is not None and max_wait_time > 0 and time.time() - start_time >= max_wait_time:
            reason = 'timeout'
            break

        coords = _game_coords(game)
        cur = gather_metrics(coords, m, n)

        # 达到目标聚拢度即停机
        if target_gather_score is not None and cur['score'] >= target_gather_score - 1e-9:
            reason = 'target'
            break

        # 更新历史最优聚拢度
        if cur['score'] > best_score + 1e-9:
            best_score = cur['score']
            best_metrics = cur
            best_snap = snapshot(game)
            best_idx = len(actions)
            no_improve = 0
        else:
            no_improve += 1

        if progress_callback:
            progress_callback({
                'stage': 'gather', 'step': i, 'total': max_steps,
                'score': cur['score'], 'best_score': best_score,
                'overlap': cur['overlap'], 'bbox': cur['bbox'],
                'fill_rate': cur['fill_rate'],
            })

        # 停机：连续 patience 步没有改进历史最优
        if patience is not None and no_improve >= patience:
            reason = 'no_improve'
            break

        ch = canonicalize(coords)
        if ch in visited:
            stuck += 1
            if stuck > 5:
                reason = 'stuck'
                break
        visited.add(ch)

        candidates = enumerate_valid_actions(game, step)
        if not candidates:
            reason = 'no_candidates'
            break

        snap = snapshot(game)
        scored = []  # (score, bbox_area, action, result_hash, mod_compliant)
        for act in candidates:
            if not apply_action(game, act, step):
                restore(game, snap)
                continue
            new_coords = _game_coords(game)
            if len(new_coords) != total:
                restore(game, snap)
                continue
            met = gather_metrics(new_coords, m, n)
            nh = canonicalize(new_coords)
            mod_ok = _mod_compliant is None or _mod_compliant(new_coords, step, _mod_r0, _mod_c0)
            scored.append((met['score'], met['bbox_area'], act, nh, mod_ok))
            restore(game, snap)

        if not scored:
            # 无候选：随机扰动
            for _ in range(3):
                act = random.choice(candidates)
                before = _game_coords(game)
                if apply_action(game, act, step):
                    actions.append(act)
                    rep_cells.append(_find_rep_cell(game, act))
                    after = _game_coords(game)
                    trace.append(gather_metrics(after, m, n))
                    hashes.append(canonicalize(after))
                    moved_groups.append(_moved_group(before, after))
                    break
            else:
                reason = 'no_candidates'
                break
            continue

        # 激进程度：允许聚拢度比最佳候选低 aggressiveness 的范围内选，用于探索
        if aggressiveness is not None and aggressiveness > 0 and len(scored) > 1:
            best_val = max(s[0] for s in scored)
            threshold = best_val - aggressiveness
            pool = [s for s in scored if s[0] >= threshold]
        else:
            pool = scored

        # 优先未访问，再聚拢度最高，再 mod 分高，再边界盒面积最小
        pool.sort(key=lambda x: (x[3] in visited, -x[0], -x[4], x[1]))
        _, _, best_action, _, _ = pool[0]

        restore(game, snap)
        rep = _find_rep_cell(game, best_action)
        if rep is None:
            act = random.choice(candidates)
            before = _game_coords(game)
            if apply_action(game, act, step):
                rep = _find_rep_cell(game, act) or (0, 0)
                actions.append(act)
                rep_cells.append(rep)
                after = _game_coords(game)
                trace.append(gather_metrics(after, m, n))
                hashes.append(canonicalize(after))
                moved_groups.append(_moved_group(before, after))
                continue
            reason = 'no_candidates'
            break

        before = _game_coords(game)
        ok = apply_action(game, best_action, step)
        if not ok:
            reason = 'invalid_action'
            break
        after = _game_coords(game)
        actions.append(best_action)
        rep_cells.append(rep)
        trace.append(gather_metrics(after, m, n))
        hashes.append(canonicalize(after))
        moved_groups.append(_moved_group(before, after))

    # 若未还原，回退到历史最优状态（丢弃无改进的尾步）
    if not game.is_solved():
        restore(game, best_snap)
        actions = actions[:best_idx]
        rep_cells = rep_cells[:best_idx]
        trace = trace[:best_idx]
        hashes = hashes[:best_idx]
        moved_groups = moved_groups[:best_idx]

    # 路径优化：去环 + 徘徊压缩（重放验证，失败则保留原路径）
    if not game.is_solved() and len(actions) >= 2:
        snap_opt = snapshot(game)
        final_coords = _game_coords(game)
        opt_a, opt_r, opt_t = _optimize_path(
            start_hash, actions, rep_cells, trace, hashes, moved_groups)
        if _verify_replay(snap_opt, step, opt_a, final_coords):
            actions, rep_cells, trace = opt_a, opt_r, opt_t

    end_metrics = gather_metrics(_game_coords(game), m, n)
    if game.is_solved():
        best_metrics = end_metrics  # 已还原时，最优即最终状态
        reason = 'solved'

    return {
        'type': 'gather',
        'actions': actions,
        'rep_cells': rep_cells,
        'solved': game.is_solved(),
        'reason': reason,
        'start': start_metrics,
        'end': end_metrics,
        'best': best_metrics,
        'trace': trace,
    }


# ---------------------------------------------------------------------------
# 智能梯度聚拢
# ---------------------------------------------------------------------------
def predict_params(game, step: int) -> dict:
    """先验参数预测：只依据棋盘固有特征（尺寸、块数、初始聚拢度）确定参数。

    不依赖任何运行期反馈，全部信息在求解前即可取得：
        - 块数越多，搜索空间越大 → 步数上限 / 停滞容忍 / 时间上限同步放大
        - 初始聚拢度越低（越散）→ 需要越激进（允许临时下降以探索）
        - 初始聚拢度已接近 (total-1)/total 时，直接不设限（需求：几乎还原时
          可以放手聚拢到完成；时间保留 30s 保险避免失控）
    """
    m, n = game.m, game.n
    total = m * n
    met = gather_metrics(_game_coords(game), m, n)
    score0 = met['score']

    # 几乎还原：放手搜索（需求：重叠 (m*n-1)/(m*n) 时可完全不设限）
    if score0 >= (total - 1) / total - 1e-9:
        return {
            'max_steps': None, 'patience': None, 'max_wait_time': 30,
            'target_gather_score': 1.0, 'aggressiveness': 0.0,
        }

    max_steps = max(200, min(3000, int(20 + total * 10)))       # 4x4→200  7x7→510
    patience = max(60, min(800, int(max_steps * 0.3)))          # 与步数上限联动
    max_wait_time = max(10, min(120, int(10 + total * 0.8)))    # 4x4→22s  7x7→49s
    aggressiveness = 0.2 if score0 < 0.6 else 0.1               # 越散越激进
    return {
        'max_steps': max_steps, 'patience': patience,
        'max_wait_time': max_wait_time,
        'target_gather_score': 1.0, 'aggressiveness': aggressiveness,
    }


def stage_params(base_params: dict, stage_idx: int) -> dict:
    """第 stage_idx 阶段的参数：在第 0 阶段基础参数上放宽。

    每阶段：patience ×2、max_steps ×2、aggressiveness +0.1（≤0.5）。
    被 gradient_gather（一次性）与 GUI 逐阶段播放共用，保证参数一致。
    """
    p = dict(base_params)
    if stage_idx > 0:
        if p.get('patience') is not None:
            p['patience'] = int(p['patience'] * (2 ** stage_idx))
        if p.get('max_steps') is not None:
            p['max_steps'] = int(p['max_steps'] * (2 ** stage_idx))
        if p.get('aggressiveness') is not None:
            p['aggressiveness'] = min(0.5, p['aggressiveness'] + 0.1 * stage_idx)
    return p


def gradient_gather(game, step: int, max_stages=4,
                    cancel_check=None, progress_callback=None,
                    base_params=None) -> dict:
    """智能梯度聚拢：多次调用普通聚拢，每阶段结束后若未完成，放宽参数再聚拢。

    阶段参数：
        第 0 阶段 = predict_params 先验生成的基础参数
        之后每阶段放宽：patience ×2、max_steps ×2、aggressiveness +0.1（≤0.5）
    终止：
        求解完成 / 用户取消 / 超时 / 真到头（no_candidates/invalid_action）
        / 阶段数达到上限（此时仍回退到全程历史最优）
    返回结构与 gather_solve 一致，另带 stages 字段（每阶段摘要）。
    """
    m, n = game.m, game.n
    if base_params is None:
        base_params = predict_params(game, step)

    all_actions, all_rep, all_trace = [], [], []
    stages = []
    start_metrics = gather_metrics(_game_coords(game), m, n)
    best_overall = start_metrics
    solved = False
    final_reason = 'stages_exhausted'
    stage_idx = 0

    while stage_idx < max_stages:
        p = stage_params(base_params, stage_idx)

        if progress_callback:
            progress_callback({'stage': 'gradient_stage', 'idx': stage_idx + 1,
                               'total': max_stages})

        r = gather_solve(game, step, cancel_check=cancel_check,
                         progress_callback=progress_callback, **p)
        all_actions += r['actions']
        all_rep += r['rep_cells']
        all_trace += r['trace']
        if r['best']['score'] > best_overall['score'] + 1e-9:
            best_overall = r['best']
        stages.append({
            'stage': stage_idx + 1,
            'params': {k: v for k, v in p.items()},
            'reason': r['reason'],
            'steps': len(r['actions']),
            'score': r['end']['score'],
        })

        if r['solved']:
            solved = True
            final_reason = 'solved'
            break
        # 这些原因表示无法继续（时间/取消/真到头）
        if r['reason'] in ('timeout', 'cancelled', 'no_candidates', 'invalid_action'):
            final_reason = r['reason']
            break
        # no_improve / stuck / max_steps：放宽参数进入下一阶段
        stage_idx += 1

    end_metrics = gather_metrics(_game_coords(game), m, n)
    if solved:
        best_overall = end_metrics
    return {
        'type': 'gather_gradient',
        'actions': all_actions,
        'rep_cells': all_rep,
        'solved': solved,
        'reason': final_reason,
        'start': start_metrics,
        'end': end_metrics,
        'best': best_overall,
        'trace': all_trace,
        'stages': stages,
    }


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------
def _verify_replay(snap0, step, actions, expect_coords):
    """从起点快照重放优化后的路径，验证终点状态与预期一致（避免优化破坏规则）"""
    g = SliderMatrix(snap0['m'], snap0['n'])
    restore(g, snap0)
    for act in actions:
        if not apply_action(g, act, step):
            return False
    return _game_coords(g) == expect_coords


def main():
    m, n, step = 4, 4, 2
    if len(sys.argv) > 3:
        m, n, step = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])

    # 可选参数：python -m solver.ml.gather_solver m n step [max_steps patience max_wait_time target aggressiveness]
    max_steps, patience, max_wait_time = 500, 100, 0.0
    target, aggressive = 1.0, 0.0
    if len(sys.argv) > 4:
        max_steps = int(sys.argv[4])
    if len(sys.argv) > 5:
        patience = int(sys.argv[5])
    if len(sys.argv) > 6:
        max_wait_time = float(sys.argv[6])
    if len(sys.argv) > 7:
        target = float(sys.argv[7])
    if len(sys.argv) > 8:
        aggressive = float(sys.argv[8])

    total_tests = 10
    print(f"聚拢求解器 — {m}x{n} step={step}  "
          f"max_steps={max_steps} patience={patience} max_wait={max_wait_time}s "
          f"target={target} 激进={aggressive}\n")

    solved_cnt = 0
    total_opt = 0
    for t in range(total_tests):
        g = SliderMatrix(m, n)
        g.shuffle(attempts=100, step=step)
        g0 = snapshot(g)
        t0 = time.time()
        r = gather_solve(g, step=step, max_steps=max_steps, patience=patience,
                         max_wait_time=max_wait_time, target_gather_score=target,
                         aggressiveness=aggressive)
        el = time.time() - t0
        s, e = r['start'], r['end']
        mark = '复原' if r['solved'] else '未复原'
        if r['solved']:
            solved_cnt += 1
        # 验证优化后的路径仍能到达终点状态
        if r['actions']:
            expect = frozenset((b.location[0], b.location[1]) for b in g.blocks)
            ok = _verify_replay(g0, step, r['actions'], expect)
        else:
            ok = True
        total_opt += len(r['trace']) - len(r['actions'])
        print(f"  测试{t+1:2d}: {len(r['actions']):3d}步 {el:.1f}s  "
              f"聚拢度 {s['score']:.3f}→{e['score']:.3f}  "
              f"边界盒 {s['bbox'][0]}x{s['bbox'][1]}→{e['bbox'][0]}x{e['bbox'][1]}  "
              f"{mark}  优化删除{max(0, len(r['trace'])-len(r['actions']))}步 重放验证{'OK' if ok else 'FAIL'}")

    print(f"\n复原率: {solved_cnt}/{total_tests}（聚拢本身不保证还原）")


if __name__ == '__main__':
    main()
