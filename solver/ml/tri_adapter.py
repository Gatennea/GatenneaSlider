# -*- coding: utf-8 -*-
"""三角形形态适配器（M1）。

《異形求解器計劃.md》§3 规定梯度骨架只认五个函数，每形态一份适配器：

    best_placement(coords, spec) -> region          # 目标框（M0 已完成）
    shape_score(coords, spec) -> float              # 聚拢度
    enumerate_actions(game, step) -> [act5]         # 含 rep 的 5 元组
    apply_action(game, act5, step) -> bool           # 真盘应用
    snap / restore(game)                            # 形态版快照

本模块实现后三个 + 快照；`shape_score` 直接包 M0 的 `best_placement.score`，
与 F2 调试面板**同一份数据源**（計劃 §4 铁律：面板显示与求解器同源）。

动作一律 5 元组 `(gap_type, line, side, dir, rep_key)`
────────────────────────────────────────────────────────
`side` 是 `side_of()` 的返回值（0 = 索引小的一侧、1 = 大的一侧），不是
"above/below" 这种人类词——三角形三族缝各有自己的索引轴，没有通用方位词。

`rep_key` = 被选连通分量里任一单元的 key。**必须有它**：同一条缝的两侧
可能各有多个连通分量，`opt` 只认「从哪个块起 DFS」，不指定起块就等于
把两侧所有分量混成一坨然后取第一个。方形 `actions.apply_action` 恒取
`_get_side_blocks(...)[0]`（4 元组）是已知欠账（Memory「已知未修缺陷」），
异形从第一天就不埋（計劃 §3 明确要求）。
"""

from solver.ml.shape_gather import ShapeGather
from game_triangle import (
    GAP_DIRECTIONS, TriangleSliderMatrix, gap_index_range, side_of,
)

__all__ = [
    'TriSpec', 'shape_score', 'enumerate_actions', 'apply_action',
    'snap', 'restore', 'tri_coords', 'score_of_game', 'tri_gather_solve',
]

# act5 = (gap_type, line, side, dir, rep_key)
Action5 = tuple


class TriSpec:
    """三角形形态的「规格」——骨架传给适配器的形态参数。

    只有 k（边长，单元总数 k²）与 step（滑动步长）是形态固有量；
    单元总数 total = k² 供骨架做「块数不变」校验。
    """

    __slots__ = ('k', 'step')

    def __init__(self, k: int, step: int):
        self.k = k
        self.step = step

    @property
    def total(self) -> int:
        return self.k * self.k

    def __repr__(self):
        return f'TriSpec(k={self.k}, step={self.step})'


# ---------------------------------------------------------------------------
# 坐标与聚拢度
# ---------------------------------------------------------------------------
def tri_coords(game) -> frozenset:
    """当前局面 → 单元集合 frozenset((i, j, up))。

    注意与方形的 `_game_coords` 不同：三角单元**带朝向分量 up**，且 up 在
    引擎里永不变（鏡像不可达，計劃 §5），所以坐标集合天然区分 ▲/▼。
    """
    return frozenset((b.location[0], b.location[1], b.location[2])
                     for b in game.blocks)


def shape_score(coords, spec: TriSpec) -> float:
    """聚拢度 = |coords ∩ 最佳放置| / k²，取值 0~1。

    **直接包 M0 的 `best_placement`**，不另写一份枚举：
    計劃 §4 的铁律是「调试面板画框与求解器必须共用同一结果」，而面板已经
    吃 `best_placement`；这里若自己枚举一遍，两边迟早漂移。

    score = 1.0 ⇔ 单元集与某个平移的大三角完全重合 ⇔ `game.is_solved()`
    （M0 的 T7 组 120/120 断言已验证这个口径等价）。
    """
    from solver.ml.tri_placement import best_placement
    return best_placement(coords, spec.k, spec.step).score


def score_of_game(game, spec: TriSpec) -> float:
    """便捷入口：直接吃 game。"""
    return shape_score(tri_coords(game), spec)


# ---------------------------------------------------------------------------
# 动作层
# ---------------------------------------------------------------------------
def enumerate_actions(game: TriangleSliderMatrix, step: int) -> list:
    """枚举当前状态下所有合法动作，返回 5 元组列表。

    合法动作 = 有效缝隙 × 2 侧 × 该族允许的移动方向，且**每个连通分量
    各算一个动作**（rep_key 不同）。这是与方形 4 元组版的实质差别：
    方形的 `enumerate_valid_actions` 只产出 (族, line, side, dir)，
    `apply_action` 再去猜代表块；异形反过来把 rep 固化进动作本身，
    「猜」这件事不发生。

    枚举范围直接吃引擎的 `all_gaps()`（含 `is_valid_gap` 复核），不自己
    按网格硬算——錯位态之类的合法性现状由引擎说了算（計劃 §6 末段）。
    """
    actions = []
    cells = game.positions()
    if not cells:
        return actions

    for gap_type, line in game.all_gaps():
        for side in (0, 1):
            side_cells = {c for c in cells
                          if side_of(gap_type, line, c) == side}
            if not side_cells:
                continue
            for rep in sorted(_components(game, gap_type, line, side_cells)):
                for d in GAP_DIRECTIONS[gap_type]:
                    actions.append((gap_type, line, side, d, rep))
    return actions


def _components(game, gap_type: str, line: int, side_cells: set) -> list:
    """某一侧的连通分量列表，每个分量回一个代表 key。

    与引擎 `opt` 的 DFS **同一套判据**：3-邻接（`neighbors`）+ 不跨缝。
    两者必须一致——否则枚举出的 rep 在 `opt` 里会落到别的分量上，动作
    静默变成另一个动作（这类 bug 极难从「解出来了」以外的现象察觉）。
    """
    from game_triangle import neighbors
    comps = []
    visited = set()
    for start in sorted(side_cells):
        if start in visited:
            continue
        comp = set()
        stack = [start]
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp.add(cur)
            for nb in neighbors(cur):
                if nb in side_cells and nb not in comp:
                    stack.append(nb)
        visited |= comp
        comps.append(min(comp))     # 代表块取字典序最小 → 确定性
    return comps


def apply_action(game: TriangleSliderMatrix, action: Action5,
                 step: int) -> bool:
    """在真盘上执行一个 5 元组动作。成功返回 True，失败返回 False。

    流程与方形 `actions.apply_action` 同构（清选中 → opt → try_move →
    commit_move → 清选中），差别只有两点：
      1. `opt` 吃 **rep_key 指定的确切块**，不猜；
      2. `try_move` 用引擎的 `try_move_ex` 拿 reason，便于诊断。

    dist > step 的动作**不在这里拆**（07 教训：引擎一次只滑 step 格）。
    骨架若要移动更远，应自己连滑 ceil(dist/step) 次并逐步更新 rep。
    """
    gap_type, line, side, move_dir, rep_key = action
    game._clear_selection()
    rep_block = game.block_at(rep_key)
    if rep_block is None:
        return False
    # rep 必须真在指定那一侧，否则动作被静默改写（opt 会按 rep 实际侧 DFS）
    if side_of(gap_type, line, rep_key) != side:
        return False
    game.opt(gap_type, line, rep_block)
    final_positions, reason = game.try_move_ex(move_dir, step)
    if not final_positions:
        game._clear_selection()
        return False
    game.commit_move(final_positions)
    game._clear_selection()
    return True


# ---------------------------------------------------------------------------
# 快照 / 恢复（重放终裁用；計劃 §3「真盘重放终裁原则」）
# ---------------------------------------------------------------------------
def snap(game: TriangleSliderMatrix) -> dict:
    """抓快照：位置列表 + is_solved。

    只存位置不够——求解器中途会把 game 停在「非最优但合法」的状态，
    恢复时需要知道那状态是不是已还原（骨架的停机判断依赖它）。
    """
    return {
        'locations': [list(b.location) for b in game.blocks],
        'solved': game.is_solved(),
    }


def restore(game: TriangleSliderMatrix, s: dict) -> None:
    """恢复快照。**不重建 blocks 对象**（保持外部持有的引用有效）。"""
    for b, loc in zip(game.blocks, s['locations']):
        b.location = list(loc)
    game._clear_selection()
    game.update_matrix()

# ---------------------------------------------------------------------------
# 统一入口：与方形求解器同签名，供 SOLVER_ALGORITHMS 注册表 / GUI 使用
# ---------------------------------------------------------------------------
def tri_gather_solve(game, step: int = None, cancel_check=None,
                     progress_callback=None, max_steps=500, patience=150,
                     max_wait_time=30.0, target_score=1.0, aggressiveness=0.2,
                     **kw):
    """三角聚拢求解——签名与方形 `gather_solve` 对齐。

    为什么单独包一层而不是直接用 `ShapeGather`：
      · GUI 的 `solve_thread` 按 `solver_func(game, step=..., cancel_check=...,
        progress_callback=...)` 统一签名调用，注册表里的每个算法都得吃这套；
      · 方形版还吃 `gather_params`（max_steps / patience / ... 逐项可能为
        None 表示不设限），这里同样支持——**None 透传给 ShapeGather.solve**，
        它的每个停机条件都是「None = 不设限」，语义一致。

    `step` 缺省用 game 自己的（`TriangleSliderMatrix` 不存 step，从外部传入）。
    返回 dict 额外带 `type='gather'` 以便 GUI 走 `_handle_gather_result`
    的同一条路径（計劃 §8 M4：异形 GUI 放行走梯度聚拢）。
    """
    sg = ShapeGather(shape_score, enumerate_actions, apply_action,
                     snap, restore, tri_coords)
    spec = TriSpec(k=game.k, step=step)
    # 方形侧「禁用的参数传 None」：把 None 从 kw 里摘掉，让 solve 用默认值
    params = {k: v for k, v in
              dict(max_steps=max_steps, patience=patience,
                   max_wait_time=max_wait_time, target_score=target_score,
                   aggressiveness=aggressiveness).items()
              if v is not None}
    res = sg.solve(game, spec, step, cancel_check=cancel_check,
                   progress_callback=progress_callback, **params)
    res['type'] = 'gather'
    # GUI 的 _handle_gather_result 会读 result['start'/'end'] 拿 bbox 做文案；
    # 异形没有这两段指标（见 GUI.py 的 is_shape 分支），不给键即可。
    return res
