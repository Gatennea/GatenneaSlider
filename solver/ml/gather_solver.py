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
# 主求解函数
# ---------------------------------------------------------------------------
def gather_solve(game, step: int, max_steps=500, patience=100,
                 cancel_check=None, progress_callback=None):
    """贪心聚拢：每步选聚拢度（重叠率）最高的动作，连续 patience 步无改进则停机。

    返回 dict：
        type    : 'gather'
        actions : Action 列表
        rep_cells : 每步代表方格坐标
        solved  : 是否恰好还原
        start   : 起点指标
        end     : 终点指标
        best    : 历史最优指标
        trace   : 每步指标（执行后）
    """
    m, n = game.m, game.n
    total = m * n

    actions = []
    rep_cells = []
    trace = []
    visited = set()
    stuck = 0

    start_metrics = gather_metrics(_game_coords(game), m, n)
    best_score = 0.0
    best_metrics = start_metrics
    best_snap = snapshot(game)
    best_idx = 0
    no_improve = 0

    for i in range(max_steps):
        if cancel_check and cancel_check():
            break
        if game.is_solved():
            break

        coords = _game_coords(game)
        cur = gather_metrics(coords, m, n)

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
        if no_improve >= patience:
            break

        ch = canonicalize(coords)
        if ch in visited:
            stuck += 1
            if stuck > 5:
                break
        visited.add(ch)

        candidates = enumerate_valid_actions(game, step)
        if not candidates:
            break

        snap = snapshot(game)
        scored = []  # (score, bbox_area, action, result_hash)
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
            scored.append((met['score'], met['bbox_area'], act, nh))
            restore(game, snap)

        if not scored:
            # 无候选：随机扰动
            for _ in range(3):
                act = random.choice(candidates)
                if apply_action(game, act, step):
                    actions.append(act)
                    rep_cells.append(_find_rep_cell(game, act))
                    trace.append(gather_metrics(_game_coords(game), m, n))
                    break
            else:
                break
            continue

        # 优先未访问，再聚拢度最高，再边界盒面积最小（凸起更近）
        scored.sort(key=lambda x: (x[3] in visited, -x[0], x[1]))
        _, _, best_action, _ = scored[0]

        restore(game, snap)
        rep = _find_rep_cell(game, best_action)
        if rep is None:
            act = random.choice(candidates)
            if apply_action(game, act, step):
                rep = _find_rep_cell(game, act) or (0, 0)
                actions.append(act)
                rep_cells.append(rep)
                trace.append(gather_metrics(_game_coords(game), m, n))
                continue
            break

        ok = apply_action(game, best_action, step)
        if not ok:
            break
        actions.append(best_action)
        rep_cells.append(rep)
        trace.append(gather_metrics(_game_coords(game), m, n))

    # 若未还原，回退到历史最优状态（丢弃无改进的尾步）
    if not game.is_solved():
        restore(game, best_snap)
        actions = actions[:best_idx]
        rep_cells = rep_cells[:best_idx]
        trace = trace[:best_idx]

    end_metrics = gather_metrics(_game_coords(game), m, n)
    if game.is_solved():
        best_metrics = end_metrics  # 已还原时，最优即最终状态

    return {
        'type': 'gather',
        'actions': actions,
        'rep_cells': rep_cells,
        'solved': game.is_solved(),
        'start': start_metrics,
        'end': end_metrics,
        'best': best_metrics,
        'trace': trace,
    }


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------
def main():
    m, n, step = 4, 4, 2
    if len(sys.argv) > 3:
        m, n, step = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])

    total_tests = 10
    print(f"聚拢求解器 — {m}x{n} step={step}\n")

    solved_cnt = 0
    for t in range(total_tests):
        g = SliderMatrix(m, n)
        g.shuffle(attempts=100, step=step)
        t0 = time.time()
        r = gather_solve(g, step=step)
        el = time.time() - t0
        s, e = r['start'], r['end']
        mark = '复原' if r['solved'] else '未复原'
        if r['solved']:
            solved_cnt += 1
        print(f"  测试{t+1:2d}: {len(r['actions']):3d}步 {el:.1f}s  "
              f"聚拢度 {s['score']:.3f}→{e['score']:.3f}  "
              f"边界盒 {s['bbox'][0]}x{s['bbox'][1]}→{e['bbox'][0]}x{e['bbox'][1]}  {mark}")

    print(f"\n复原率: {solved_cnt}/{total_tests}（聚拢本身不保证还原）")


if __name__ == '__main__':
    main()
