# -*- coding: utf-8 -*-
"""
规则求解器 v3 — EMD 贪心 + 循环检测 + 死锁随机扰动

极简策略：每步选 EMD 最小的动作。卡死时随机走几步。
接口与 table_solve / ai_solve 一致。
"""

import sys, time, random
from game import SliderMatrix
from solver.actions import enumerate_valid_actions, apply_action
from solver.state import snapshot, restore
from solver.table_core import canonicalize, _side_components
from solver.ml.emd_solver import emd_distance


def _find_rep_cell(game, action):
    """找到动作对应的代表方格坐标——与 apply_action 的 _get_side_blocks 逻辑一致。"""
    gap_type, gap_line, side, _ = action
    for b in game.blocks:
        if gap_type == 'h':
            if side == 'above' and b.location[0] <= gap_line:
                return (b.location[0], b.location[1])
            if side == 'below' and b.location[0] > gap_line:
                return (b.location[0], b.location[1])
        else:
            if side == 'left' and b.location[1] <= gap_line:
                return (b.location[0], b.location[1])
            if side == 'right' and b.location[1] > gap_line:
                return (b.location[0], b.location[1])
    return None


def strategy_solve(game, step: int, max_steps=1000,
                   cancel_check=None, progress_callback=None):
    m, n = game.m, game.n
    total = m * n
    actions = []
    rep_cells = []
    visited = set()
    stuck = 0
    no_improve = 0  # EMD 连续不降的步数

    for i in range(max_steps):
        if cancel_check and cancel_check():
            return None
        if game.is_solved():
            break

        coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        cur_emd = emd_distance(coords, m, n)

        if progress_callback and i % 10 == 0:
            progress_callback({'step': i + 1, 'total': max_steps, 'emd': cur_emd})

        # 太久不改善，提前放弃
        if no_improve > 80:
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
        # 收集所有可执行动作的 (emd, action, result_hash)
        scored = []
        for act in candidates:
            if not apply_action(game, act, step):
                restore(game, snap)
                continue
            new_coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
            if len(new_coords) != total:
                restore(game, snap)
                continue
            emd = emd_distance(new_coords, m, n)
            nh = canonicalize(new_coords)
            scored.append((emd, act, nh))
            restore(game, snap)

        if not scored:
            # 随机扰动
            for _ in range(3):
                act = random.choice(candidates)
                if apply_action(game, act, step):
                    actions.append(act)
                    rep_cells.append(_find_rep_cell(game, act))
                    break
            else:
                break
            continue

        # 选 EMD 最小且未访问过的
        scored.sort(key=lambda x: (x[2] in visited, x[0]))
        best_emd, best_action, best_nh = scored[0]

        # 执行
        restore(game, snap)
        rep = _find_rep_cell(game, best_action)
        if rep is None:
            # 找不到代表格，跳过这一步用随机
            act = random.choice(candidates)
            if apply_action(game, act, step):
                rep = _find_rep_cell(game, act) or (0, 0)
                actions.append(act)
                rep_cells.append(rep)
                continue
            break
        ok = apply_action(game, best_action, step)
        if not ok:
            break
        actions.append(best_action)
        rep_cells.append(rep)

        # 追踪改善
        if best_emd < cur_emd:
            no_improve = 0
        else:
            no_improve += 1

    if game.is_solved():
        return actions, rep_cells
    return False


# ── 测试 ──
def main():
    m, n, step = 4, 4, 2
    if len(sys.argv) > 3:
        m, n, step = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    total_tests = 20
    ok = 0; steps_sum = 0; time_sum = 0.0
    print(f"规则求解器 v3 — {m}x{n} step={step}\n")
    for t in range(total_tests):
        g = SliderMatrix(m, n)
        g.shuffle(attempts=100, step=step)
        t0 = time.time()
        r = strategy_solve(g, step=step)
        el = time.time() - t0
        if r:
            acts, _ = r; ok += 1; steps_sum += len(acts); time_sum += el
            print(f"  测试{t+1:2d}: OK  {len(acts):3d}步  {el:.1f}s")
        else:
            print(f"  测试{t+1:2d}: FAIL  {el:.1f}s")
    print(f"\n成功率: {ok}/{total_tests} ({100*ok/total_tests:.0f}%)")
    if ok: print(f"平均步数: {steps_sum/ok:.1f}  平均耗时: {time_sum/ok:.1f}s")

if __name__ == '__main__':
    main()
