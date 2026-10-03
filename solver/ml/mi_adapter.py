# -*- coding: utf-8 -*-
"""米字格形态适配器（M3）。

《異形求解器計劃.md》§3 规定梯度骨架只认五个函数，每形态一份适配器：

    best_placement(coords, spec) -> region          # 目标框（M3 第一步已完成）
    shape_score(coords, spec) -> float              # 聚拢度
    enumerate_actions(game, step) -> [act5]         # 含 rep 的 5 元组
    apply_action(game, act5, step) -> bool          # 真盘应用
    snap / restore(game)                            # 形态版快照

本模块实现后三个 + 快照；`shape_score` 直接包 `mi_placement.best_placement.score`，
与 F2 调试面板**同一份数据源**（計劃 §4 铁律：面板显示与求解器同源）。

动作一律 5 元组 `(gap_type, line, side, dir, rep_key)`
────────────────────────────────────────────────────────
`rep_key` = 被选连通分量里任一单元的 key = `(r, c, q)`。与 tri 一样**必须有
它**：同一条缝的两侧可能各有多个连通分量，`opt` 只认「从哪个块起 DFS」。

**与 tri 适配器的三处实质差别（都不是抄得来的）**：

1. **坐标可能是半整数。** mi 斜滑一格是 (±½,±½)，错位态下 `block.location`
   是 `[0.5, 1.5, 'N']` 这种。所以 `snap`/`restore` **不能假设 int**，
   `_components` 的 `min()` 排序在混合 int/float 下仍然可用（数值可比），
   但 `rep_key` 进 `block_at()` 前不需要归一化 —— 引擎自己的
   `mi_key(block) == key` 比较已经处理（`commit_move` 已把整数组件归一化，
   非法 float 不会进 location）。
2. **`_components` 必须用 5 邻接。** tri 用 3 邻接，mi 的 `opt` 用的是
   `game_mi.neighbors` 的**全 5 条**（3 同晶格 + 2 跨晶格）。用 3 条会与
   `opt` 判据不一致 → 枚举出的 rep 在 `opt` 里落到别的分量，动作静默变成
   另一个动作（这类 bug 极难从「解出来了」以外的现象察觉）。
3. **`goal` 有两个形状。** `MiSpec` 传 (m, n)，`shape_score` 内部同时枚举
   m×n 与 n×m（轉置算還原，計劃 §6 拍板），`enumerate_actions` 不受影响。
"""

from solver.ml.shape_gather import ShapeGather
from game_mi import (
    GAP_DIRECTIONS, MiSliderMatrix, mi_key, neighbors as mi_neighbors,
    side_of,
)

__all__ = [
    'MiSpec', 'shape_score', 'enumerate_actions', 'apply_action',
    'snap', 'restore', 'mi_coords', 'score_of_game', 'mi_gather_solve',
]

# act5 = (gap_type, line, side, dir, rep_key)
Action5 = tuple


class MiSpec:
    """米字格形态的「规格」——骨架传给适配器的形态参数。

    m / n 是棋盘高宽（單元總數 4mn），step 是滑动步长。
    `total` 供骨架做「塊數不變」校驗。
    """

    __slots__ = ('m', 'n', 'step')

    def __init__(self, m: int, n: int, step: int):
        self.m = m
        self.n = n
        self.step = step

    @property
    def total(self) -> int:
        return 4 * self.m * self.n

    def __repr__(self):
        return f'MiSpec({self.m}x{self.n}, step={self.step})'


# ---------------------------------------------------------------------------
# 坐标与聚拢度
# ---------------------------------------------------------------------------
def mi_coords(game) -> frozenset:
    """当前局面 → 单元集合 frozenset((r, c, q))。

    坐標可能是半整數（錯位態），這是 mi 與方形/tri 的第一處形態差別。
    用 `mi_key` 而不是 `tuple(b.location)`：後者在某些路徑下會帶 list
    裡的別的東西，且 `mi_key` 是引擎自己的口徑。
    """
    return frozenset(mi_key(b) for b in game.blocks)


def shape_score(coords, spec: MiSpec) -> float:
    """聚拢度 = |coords ∩ 最佳放置| / 4mn，取值 0~1。

    **直接包 M3 第一步的 `best_placement`**，不另写一份枚举：計劃 §4 的
    铁律是「调试面板画框与求解器必须共用同一结果」，而面板已经吃
    `best_placement`；这里若自己枚举一遍，两边迟早漂移。

    score = 1.0 ⇔ 单元集与某个放置（m×n 或 n×m、A 档或 B 档）完全重合
    ⇔ `game.is_solved()`（`is_solved` 本就判两种高寬都放行，見計劃 §6）。
    """
    from solver.ml.mi_placement import best_placement
    return best_placement(coords, spec.m, spec.n, spec.step).score


def score_of_game(game, spec: MiSpec) -> float:
    """便捷入口：直接吃 game。"""
    return shape_score(mi_coords(game), spec)


# ---------------------------------------------------------------------------
# 动作层
# ---------------------------------------------------------------------------
def enumerate_actions(game: MiSliderMatrix, step: int) -> list:
    """枚举当前状态下所有合法动作，返回 5 元组列表。

    合法动作 = 有效缝隙 × 2 侧 × 该族允许的移动方向，且**每个连通分量
    各算一个动作**（rep_key 不同）。

    枚举范围直接吃引擎的 `all_gaps()`（含 `_valid_line` 复核），不自己
    按网格硬算——錯位態下 h/v 縫會變成半整數線號、對角族的候選線由塊的跨度
    導出（`gap_candidates`），這些規則由引擎說了算（計劃 §6 末段）。
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


def _components(game, gap_type: str, line, side_cells: set) -> list:
    """某一侧的连通分量列表，每个分量回一个代表 key。

    与引擎 `opt` 的 DFS **同一套判据**：5-邻接（`game_mi.neighbors`）+
    不跨缝。两者必须一致——否则枚举出的 rep 在 `opt` 里会落到别的分量上，
    动作静默变成另一个动作（这类 bug 极难从「解出来了」以外的现象察觉）。

    代表块取字典序最小 → 确定性（`min(comp)`；坐標可能是半整數，但
    int/float 可比且 q 是 str，元組比較有全序，不会 TypeError）。
    """
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
            for nb in mi_neighbors(cur):
                if nb in side_cells and nb not in comp:
                    stack.append(nb)
        visited |= comp
        comps.append(min(comp))     # 代表块取字典序最小 → 确定性
    return comps


def apply_action(game: MiSliderMatrix, action: Action5, step: int) -> bool:
    """在真盘上执行一个 5 元组动作。成功返回 True，失败返回 False。

    流程与 tri 版同构（清选中 → opt → try_move_ex → commit_move → 清选中），
    差别只有两点：
      1. `opt` 吃 **rep_key 指定的确切块**，不猜；
      2. `try_move_ex` 用 reason 便于诊断（錯位態下失敗原因多一類
         'collision'：跨晶格正面積重疊，見 `game_mi._has_overlap`）。

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
def snap(game: MiSliderMatrix) -> dict:
    """抓快照：位置列表 + is_solved。

    只存位置不够——求解器中途会把 game 停在「非最优但合法」的状态，
    恢复时需要知道那状态是不是已还原（骨架的停机判断依赖它）。

    **位置原样存 list**（不做 int 化）：错位態的坐標是半整數，
    `commit_move` 已經把整数组件歸一化、半整數保持 float，存什么就恢复什么，
    往返不引入误差。
    """
    return {
        'locations': [list(b.location) for b in game.blocks],
        'solved': game.is_solved(),
    }


def restore(game: MiSliderMatrix, s: dict) -> None:
    """恢复快照。**不重建 blocks 对象**（保持外部持有的引用有效）。"""
    for b, loc in zip(game.blocks, s['locations']):
        b.location = list(loc)
    game._clear_selection()
    game.update_matrix()


# ---------------------------------------------------------------------------
# 统一入口：与方形求解器同签名，供 SOLVER_ALGORITHMS 注册表 / GUI 使用
# ---------------------------------------------------------------------------
def mi_gather_solve(game, step: int = None, cancel_check=None,
                    progress_callback=None, max_steps=500, patience=150,
                    max_wait_time=30.0, target_score=1.0, aggressiveness=0.2,
                    **kw):
    """米字格聚拢求解——签名与方形 `gather_solve`、tri `tri_gather_solve` 对齐。

    为什么单独包一层而不是直接用 `ShapeGather`：
      · GUI 的 `solve_thread` 按 `solver_func(game, step=..., cancel_check=...,
        progress_callback=...)` 统一签名调用，注册表里的每个算法都得吃这套；
      · 方形版还吃 `gather_params`（max_steps / patience / ... 逐项可能为
        None 表示不设限），这里同样支持——**None 透传给 ShapeGather.solve**，
        它的每个停机条件都是「None = 不设限」，语义一致。

    `step` 缺省用 game 自己的（`MiSliderMatrix` 不存 step，从外部传入）。
    返回 dict 额外带 `type='gather'` 以便 GUI 走 `_handle_gather_result`
    的同一条路径（計劃 §8 M4 的做法，mi 照搬）。
    """
    sg = ShapeGather(shape_score, enumerate_actions, apply_action,
                     snap, restore, mi_coords)
    spec = MiSpec(m=game.m, n=game.n, step=step)
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
