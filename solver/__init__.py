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
from solver.ml.tri_adapter import tri_gather_solve


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
from solver.ml.gap_solver import solve_gap_macro
from solver.hybrid_solver import hybrid_solve
from solver.auto_solver import auto_solve


def hybrid_solve_with_table(game, step, cancel_check=None,
                            progress_callback=None, **kwargs):
    """「混合求解」的入口包装：**有表先用表，無表才走混合**。

    依據 2026-09-30 驗收（`experiments/ACCEPTANCE_混合求解器验收.md`）：
    hybrid 的定位是「免表兜底、非最優」——4×4 step2 上解長中位是最優的 17.2 倍
    （最差 136.8），單局耗時中位 12.2s；而查表是亞秒級且**保證最優**。
    故在已有距離表的尺寸上必須優先查表，避免「12 秒換一個 17 倍長的解」。

    注意：這裡只在**入口層**分流，`hybrid_solve` 本身保持純算法，
    `experiments/` 裡直接 import hybrid_solve 的基線不受影響。
    """
    try:
        res = table_solve(game, step, cancel_check=cancel_check,
                          progress_callback=progress_callback)
    except Exception:
        res = None
    if res is not None and res is not False:
        return res  # 查表成功（元組或空列表 = 已在目標態）
    return hybrid_solve(game, step, cancel_check=cancel_check,
                        progress_callback=progress_callback, **kwargs)

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
    'gap_macro': ('  补缺宏', solve_gap_macro),
    'hybrid':   ('  混合求解（自动规划）', auto_solve),
    # 异形（三角形）：M1 落地后放行 GUI 放行（計劃 §8 M4）。三角只能走这个
    # —— 查表/补缺宏/DFS 都是方形语义，GUI 侧 `_start_auto_solve` 也据此
    # 拦掉其它算法。
    'tri_gather': ('  聚拢（三角形）', tri_gather_solve),
}

__all__ = ['solve', 'solve_fast', 'solve_greedy', 'SOLVER_ALGORITHMS',
           'apply_action', 'enumerate_valid_actions']
