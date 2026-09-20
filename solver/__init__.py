# -*- coding: utf-8 -*-
"""
求解器包

提供滑塊遊戲的自動求解功能。

模塊：
    state       - 狀態編碼、歸一化、快照保存/恢復
    actions     - 動作枚舉、apply_action、逆向檢測
    heuristic   - Score 計算、啟發函數
    ida_star    - IDA* 求解器（含 Transposition Table）
    greedy      - 貪心爬山求解器

三種算法：
    solve()         - IDA* 最少步求解
    solve_fast()    - IDA* 快速模式（不保證最優）
    solve_greedy()  - 貪心爬山（最快的非最優解）

使用方式：
    from solver import solve, solve_fast, solve_greedy

    # 求解一個打亂的遊戲
    game = SliderMatrix(4, 4)
    game.shuffle(attempts=100, step=2)

    solution = solve(game, step=2)   # 返回 Action 列表
    if solution:
        for action in solution:
            apply_action(game, action, step=2)
        print("已復原!")
"""

from solver.ida_star import ida_star_solve as solve
from solver.ida_star import ida_star_solve as _ida_star_solve
from solver.greedy import greedy_hill_climbing_solve
from solver.actions import apply_action, enumerate_valid_actions


def solve_fast(game, step: int, max_depth: int = 80,
               cancel_check=None, progress_callback=None):
    """IDA* 快速模式求解（不保證最小步數，但更快找到解）"""
    return _ida_star_solve(game, step=step, max_depth=max_depth,
                            cancel_check=cancel_check,
                            progress_callback=progress_callback,
                            fast_mode=True)


def solve_greedy(game, step: int, max_steps: int = 500,
                 cancel_check=None, progress_callback=None):
    """貪心爬山求解（最快的非最優解）"""
    return greedy_hill_climbing_solve(game, step=step, max_steps=max_steps,
                                       cancel_check=cancel_check,
                                       progress_callback=progress_callback)


# 算法名稱和對應函數的對照表
from solver.table_solver import table_solve
from solver.ml.gather_solver import gather_solve
from solver.ml.gather_solver import gradient_gather
from solver.ml.human_solver import ai_human_solve
from solver.ml.fill_macro import solve_fill_macro

SOLVER_ALGORITHMS = {
    'ida_star': ('  IDA*求解', solve),
    'fast': ('  IDA*快速', solve_fast),
    'greedy': ('  贪心爬山', solve_greedy),
    'table':  ('  查表求解', table_solve),
    #'intelligence': ('  AI求解', ai_solve),
    #'emd': ('  EMD求解', emd_greedy_solve),
    #'strategy': ('  策略求解', strategy_solve),
    #'distance': ('  距离求解', distance_solve),
    'gather': ('  聚拢', gather_solve),
    'gather_gradient': ('  梯度聚拢', gradient_gather),
    #'human_ai': ('  人类模仿', ai_human_solve),
    'fill_macro': ('  填洞宏', solve_fill_macro),
}

__all__ = ['solve', 'solve_fast', 'solve_greedy', 'SOLVER_ALGORITHMS',
           'apply_action', 'enumerate_valid_actions']
