# -*- coding: utf-8 -*-
"""
EMD 测距仪 + 贪心求解器 v2

使用游戏原生 enumerate_valid_actions 枚举候选，apply_action 临时执行，
save/restore 快照实现 undo，计算 EMD 后选最优。

运行：
    D:\python\python.exe -m solver.ml.emd_solver [m n step]
"""

import sys, time, random
from game import SliderMatrix
from solver.actions import enumerate_valid_actions, apply_action
from solver.state import snapshot, restore
from solver.table_core import canonicalize, _side_components


# ---------------------------------------------------------------------------
# EMD 测距仪
# ---------------------------------------------------------------------------
def _centroid(coords):
    n = len(coords)
    if n == 0:
        return 0.0, 0.0
    sr = sum(r for r, _ in coords)
    sc = sum(c for _, c in coords)
    return sr / n, sc / n


def _target_points(m, n):
    return [(r, c) for r in range(m) for c in range(n)]


def _shift_to_origin(coords, cr, cc):
    return [(round(r - cr), round(c - cc)) for r, c in coords]


def emd_distance(coords, m, n):
    current = list(coords)
    target = _target_points(m, n)
    if len(current) != len(target):
        return float('inf')
    cr, cc = _centroid(current)
    tr, tc = _centroid(target)
    cur = _shift_to_origin(current, cr, cc)
    tar = _shift_to_origin(target, tr, tc)
    cur.sort(key=lambda p: (p[0], p[1]))
    tar.sort(key=lambda p: (p[0], p[1]))
    total = 0.0
    for (r1, c1), (r2, c2) in zip(cur, tar):
        total += abs(r1 - r2) + abs(c1 - c2)
    return total


# ---------------------------------------------------------------------------
# 孔洞检测
# ---------------------------------------------------------------------------
def count_holes(grid_2d):
    rows, cols = len(grid_2d), len(grid_2d[0]) if grid_2d else 0
    if rows == 0 or cols == 0:
        return 0
    visited = [[False] * cols for _ in range(rows)]
    stack = []
    for r in range(rows):
        for c in [0, cols - 1]:
            if grid_2d[r][c] == 0 and not visited[r][c]:
                visited[r][c] = True; stack.append((r, c))
    for c in range(cols):
        for r in [0, rows - 1]:
            if grid_2d[r][c] == 0 and not visited[r][c]:
                visited[r][c] = True; stack.append((r, c))
    while stack:
        r, c = stack.pop()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                if grid_2d[nr][nc] == 0 and not visited[nr][nc]:
                    visited[nr][nc] = True; stack.append((nr, nc))
    holes = 0
    for r in range(rows):
        for c in range(cols):
            if grid_2d[r][c] == 0 and not visited[r][c]:
                holes += 1
    return holes


# ---------------------------------------------------------------------------
# EMD 贪心求解
# ---------------------------------------------------------------------------
def emd_greedy_solve(game, step: int, max_steps=500,
                     cancel_check=None, progress_callback=None):
    m, n = game.m, game.n
    total = m * n
    actions = []
    rep_cells = []
    visited = set()

    for i in range(max_steps):
        if cancel_check and cancel_check():
            return None
        if game.is_solved():
            break
        if progress_callback:
            progress_callback({'step': i + 1, 'total': max_steps})

        coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        ch = canonicalize(coords)
        if ch in visited:
            act = random.choice(candidates) if candidates else None
            if act and apply_action(game, act, step):
                actions.append(act)
                continue
            break
        visited.add(ch)

        # 当前 EMD
        cur_emd = emd_distance(coords, m, n)

        # 枚举候选动作
        candidates = enumerate_valid_actions(game, step)
        if not candidates:
            break

        # 保存快照
        snap = snapshot(game)

        best_action = None
        best_rep = None
        best_penalty = cur_emd + 999  # 允许不减小 EMD
        best_emd = float('inf')
        all_actions = []  # 收集所有可执行的动作

        for action in candidates:
            # 临时执行
            if not apply_action(game, action, step):
                restore(game, snap)
                continue

            # 计算 EMD
            new_coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
            if len(new_coords) != total:
                restore(game, snap)
                continue

            emd = emd_distance(new_coords, m, n)

            # 孔洞惩罚（轻量）
            nr = [r for r, _ in new_coords]; nc = [c for _, c in new_coords]
            mr2, mc2 = min(nr), min(nc)
            n2 = frozenset((r - mr2, c - mc2) for r, c in new_coords)
            nrm = max(r for r, _ in n2) + 1; ncm = max(c for _, c in n2) + 1
            g2d = [[0] * ncm for _ in range(nrm)]
            for r, c in n2:
                g2d[r][c] = 1
            holes = count_holes(g2d)
            penalty = emd - 0.1 * holes / total * emd  # EMD主导，孔洞微调

            # 记录代表方格
            _, _, side, _ = action
            gap_type, gap_line = action[0], action[1]
            comps = _side_components(coords, gap_type, gap_line, side)
            rep_cell = next(iter(comps[0])) if comps else None

            if penalty < best_penalty:
                best_penalty = penalty
                best_emd = emd
                best_action = action
                best_rep = rep_cell

            all_actions.append(action)

            # 恢复快照
            restore(game, snap)

        # 如果 EMD 完全不下降，随机扰动
        if best_emd >= cur_emd and all_actions:
            for _ in range(5):
                act = random.choice(all_actions)
                if apply_action(game, act, step):
                    actions.append(act)
                    comps2 = _side_components(coords, act[0], act[1], act[2])
                    rep_cells.append(next(iter(comps2[0])) if comps2 else None)
                    if (i + 1) % 20 == 0:
                        print(f"  EMD 步 {i+1}: 随机扰动 emd={best_emd:.0f}", flush=True)
                    break
            else:
                restore(game, snap)
                break
            continue

        # 正式执行最佳动作
        restore(game, snap)
        ok = apply_action(game, best_action, step)
        if not ok:
            break
        actions.append(best_action)
        rep_cells.append(best_rep)

        if (i + 1) % 20 == 0:
            print(f"  EMD 步 {i+1}: emd={best_emd:.0f}", flush=True)

    if game.is_solved():
        return actions, rep_cells
    return False


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------
def main():
    m, n, step = 4, 4, 2
    if len(sys.argv) > 3:
        m, n, step = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])

    total_tests = 20
    success = 0
    total_steps = 0
    total_time = 0.0

    print(f"EMD 贪心求解器 v2 — {m}x{n} step={step}")
    print(f"共 {total_tests} 次测试\n")

    for trial in range(total_tests):
        game = SliderMatrix(m, n)
        game.shuffle(attempts=100, step=step)

        t0 = time.time()
        result = emd_greedy_solve(game, step=step)
        elapsed = time.time() - t0

        if result:
            acts, _ = result
            steps = len(acts)
            success += 1
            total_steps += steps
            total_time += elapsed
            print(f"  测试 {trial+1:2d}: OK  {steps:3d}步  {elapsed:.1f}s")
        else:
            print(f"  测试 {trial+1:2d}: FAIL  {elapsed:.1f}s")

    print(f"\n{'='*50}")
    print(f"成功率: {success}/{total_tests} ({100*success/total_tests:.0f}%)")
    if success > 0:
        print(f"平均步数: {total_steps/success:.1f}")
        print(f"平均耗时: {total_time/success:.1f}s")


if __name__ == '__main__':
    main()
