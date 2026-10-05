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
from solver.ml.mi_adapter import mi_gather_solve


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

# ---------------------------------------------------------------------------
# 形态识别 + 统一入口（2026-10-05）
#
# 之前的做法是给异形**各加一个注册表入口**（'tri_gather' / 'mi_gather'），
# GUI 还要在切形态时把 solver_algorithm 静默改成对应 key。用户指出这不对：
# **不同谜题应该用同一个入口**（菜单里就一个「聚拢」），形态差异是内部实现
# 细节，不该暴露成两个菜单项、也不该由 GUI 去猜该用哪个。
# ---------------------------------------------------------------------------

FORM_LABELS = {'square': '方形', 'triangle': '三角形', 'mi': '米字格'}
_ALL_FORMS = ('square', 'triangle', 'mi')


def game_form(game) -> str:
    """返回谜题形态：'square' | 'triangle' | 'mi'。

    按**类名**判定而不是按 GUI 的 `triangle_mode`/`mi_mode` 旗标 ——
    求解器不该依赖 GUI 状态：命令行 / HTTP / 测试直接把 game 传进来
    也要能分对（GUI 旗标只在 GUI 进程里存在）。
    """
    name = type(game).__name__
    if name == 'MiSliderMatrix':
        return 'mi'
    if name == 'TriangleSliderMatrix':
        return 'triangle'
    return 'square'


def form_label(form) -> str:
    return FORM_LABELS.get(form, form)


def gather_solve_unified(game, step: int = None, cancel_check=None,
                         progress_callback=None, **kwargs):
    """「聚拢」的**统一入口**：三种谜题形态共用这一个入口，内部按形态分发。

    方形  → `gather_solve`
    三角形 → `tri_gather_solve`
    米字格 → `mi_gather_solve`

    三个被分发到的函数签名一致（含 `gather_params` 的 None 透传），
    所以 GUI 侧不需要为形态做任何特判。
    """
    form = game_form(game)
    if form == 'mi':
        fn = mi_gather_solve
    elif form == 'triangle':
        fn = tri_gather_solve
    else:
        fn = gather_solve
    return fn(game, step=step, cancel_check=cancel_check,
              progress_callback=progress_callback, **kwargs)


# 各算法支持的谜题形态。**缺省 = 只支持方形** —— 方形以外的算法大多是
# 方形语义（4 元组动作 + 矩形目标形状 + 整数坐标），套到异形上会静默走错，
# 所以新算法必须**显式声明**自己支持异形，不能靠缺省蒙对。
SOLVER_FORM_SUPPORT = {
    'gather': ('square', 'triangle', 'mi'),
}


def solver_supports(algorithm, form) -> bool:
    """algorithm 在 form 形态上是否可用。"""
    return form in SOLVER_FORM_SUPPORT.get(algorithm, ('square',))


def unsupported_solver_msg(algorithm, form) -> str:
    """「当前谜题没有 xxx 求解算法功能」的标准文案。

    之前异形遇到不支持的算法是**静默自动切换**到 tri_gather/mi_gather，
    用户看不到自己选的算法被换掉了。改为明确告知「没有这个功能」并列出
    该形态目前可用的算法，由用户自己决定。
    """
    name = SOLVER_ALGORITHMS.get(algorithm, ('求解器',))[0].strip()
    ok_keys = [k for k in SOLVER_ALGORITHMS if solver_supports(k, form)]
    ok_names = '、'.join(SOLVER_ALGORITHMS[k][0].strip() for k in ok_keys)
    return (f"当前谜题（{form_label(form)}）没有「{name}」求解算法功能"
            f"（该形态目前仅支持：{ok_names}）")


SOLVER_ALGORITHMS = {
    'ida_star': ('  IDA*求解', solve),
    'fast': ('  IDA*快速', solve_fast),
    'greedy': ('  贪心爬山', solve_greedy),
    'table':  ('  查表求解', table_solve),
    #'intelligence': ('  AI求解', ai_solve),
    #'emd': ('  EMD求解', emd_greedy_solve),
    #'strategy': ('  策略求解', strategy_solve),
    #'distance': ('  距离求解', distance_solve),
    # 三形态共用的统一入口（内部按 game 形态分发，见 gather_solve_unified）
    'gather': ('  聚拢', gather_solve_unified),
    'gather_gradient': ('  梯度聚拢', gradient_gather),
    #'human_ai': ('  人类模仿', ai_human_solve),
    'fill_macro': ('  填洞宏', solve_fill_macro),
    'gap_macro': ('  补缺宏', solve_gap_macro),
    'hybrid':   ('  混合求解（自动规划）', auto_solve),
}

# 注：'tri_gather' / 'mi_gather' 作为**独立入口已移除**（2026-10-05）——
# 形态不该各占一个菜单项。两个函数仍保留（供统一入口分发与测试直接调用），
# 但不再出现在注册表里。

__all__ = ['solve', 'solve_fast', 'solve_greedy', 'SOLVER_ALGORITHMS',
           'apply_action', 'enumerate_valid_actions',
           'game_form', 'form_label', 'gather_solve_unified',
           'SOLVER_FORM_SUPPORT', 'solver_supports', 'unsupported_solver_msg']
