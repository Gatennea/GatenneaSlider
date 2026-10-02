# -*- coding: utf-8 -*-
"""形态无关的梯度聚拢骨架。

《異形求解器計劃.md》§2 的移植判定：梯度骨架（`gather_solver.gather_solve`
+ `gradient_gather`）「**原样共享**，只需参数化的 gather_score 换成形态版」。
本模块就是这个共享骨架 —— 把方形骨架里所有形态相关处收敛成一份
**适配器协议**（§3），方形与三角形共用同一份循环逻辑。

与方形的差异只有三处，其余（patience 停机 / 历史最优回退 / aggressiveness
探索 / 候选排序 / 路径优化）全部原样：

  1. `shape_score(coords, spec)` 代替方形的 `gather_metrics`；
  2. 动作是 5 元组（带 rep），无「_find_rep_cell 事后找代表」这回事；
  3. 快照/恢复走适配器（引擎结构不同）。

**为什么共享而不是各写一份**：贪心骨架的价值全在那些调过的常数
（patience / aggressiveness / 排序键序 / 回退到历史最优），复制一份等于
这些调参结论只在一个形态生效。共享后任何一边改进另一边立刻受益。

用法（三角形）::

    from solver.ml.tri_adapter import TriSpec, shape_score, \\
        enumerate_actions, apply_action, snap, restore, tri_coords
    from solver.ml.shape_gather import ShapeGather
    sg = ShapeGather(shape_score, enumerate_actions, apply_action,
                     snap, restore, coords_of=tri_coords)
    res = sg.solve(game, TriSpec(k=4, step=2))
"""

import random
import time

__all__ = ['ShapeGather', 'solve_gather']


class ShapeGather:
    """形态无关的贪心聚拢求解器。

    构造参数即計劃 §3 的适配器协议（外加 coords_of / is_solved 两个
    形态自带的读接口）::

        shape_score(coords, spec)      -> float   # 聚拢度 0~1
        enumerate_actions(game, step)  -> [act5]  # 含 rep 的动作
        apply_action(game, act, step)  -> bool    # 真盘应用
        snap(game) / restore(game, s)             # 快照
        coords_of(game)                -> frozenset
        is_solved(game)                -> bool    # 默认取 game.is_solved

    `spec` 是形态规格（方形用 (m, n, step)，三角用 TriSpec），骨架只把它
    原样传给 `shape_score`。
    """

    def __init__(self, shape_score, enumerate_actions, apply_action,
                 snap, restore, coords_of, is_solved=None,
                 canonicalize=None, mod_filter=None, optimize_path=None):
        self.shape_score = shape_score
        self.enumerate_actions = enumerate_actions
        self.apply_action = apply_action
        self.snap = snap
        self.restore = restore
        self.coords_of = coords_of
        self.is_solved = is_solved or (lambda g: g.is_solved())
        # canonicalize：平移归一化的状态键。**必须有**——整盘可以当一个连通
        # 分量整体滑走，不归一化则「同一局面的不同平移」被当成不同状态，
        # visited 永远命中不了，去环与防徘徊全部失效（方形 `gather_solve`
        # 用 solver.table_core.canonicalize；不给则退化为 coords_of 本身，
        # 此时求解质量会明显下降 —— 这是实测踩到的）。
        self.canonicalize = canonicalize or (lambda c: frozenset(c))
        # mod_filter(coords, step) -> bool：着色不变量过滤（方形
        # `_is_mod_compliant`）。None = 无约束。
        self.mod_filter = mod_filter
        # optimize_path(actions, start_hash, hashes) -> actions：去环压缩
        # （方形 `_optimize_path`）。None = 不做。
        self.optimize_path = optimize_path

    # ------------------------------------------------------------------
    def solve(self, game, spec, step, max_steps=300, patience=150,
              max_wait_time=30.0, target_score=1.0, aggressiveness=0.2,
              cancel_check=None, progress_callback=None):
        """贪心聚拢主循环。

        参数与方形 `gather_solve` **同名同义、默认值也照抄**（patience=150、
        aggressiveness=0.2）—— 这些是方形上反复调过的常数，异形没有理由先
        设成更保守的猜测。三角形批量实测若显示需要不同的值，那是实测结论，
            不是拍脑袋的起点（把默认值当实验变量会导致「方形调参结论」与
            「异形默认值」互相污染）。

        返回 dict（与方形一致的键名，便于对照报告）：
            type / actions / solved / reason / score / best_score /
            best_step / steps / elapsed
        """
        sc = self.shape_score
        started = time.time()

        actions = []
        trace = []
        hashes = []        # 每步执行后的 canonical hash（去环用）
        visited = set()
        stuck = 0
        no_improve = 0

        start_hash = self.canonicalize(self.coords_of(game))
        start_snap = self.snap(game)   # 路径优化重放验证的起点
        cur_score = sc(self.coords_of(game), spec)
        best_score = cur_score
        best_snap = self.snap(game)
        best_idx = 0

        reason = 'max_steps'
        step_iter = range(max_steps) if max_steps is not None else iter(int, 1)
        for i in step_iter:
            if cancel_check and cancel_check():
                reason = 'cancelled'
                break
            if self.is_solved(game):
                reason = 'solved'
                break
            if (max_wait_time is not None and max_wait_time > 0
                    and time.time() - started >= max_wait_time):
                reason = 'timeout'
                break

            cur_score = sc(self.coords_of(game), spec)
            if target_score is not None and cur_score >= target_score - 1e-9:
                reason = 'target'
                break

            if cur_score > best_score + 1e-9:
                best_score = cur_score
                best_snap = self.snap(game)
                best_idx = len(actions)
                no_improve = 0
            else:
                no_improve += 1

            if progress_callback:
                progress_callback({
                    'stage': 'gather', 'step': i,
                    'score': cur_score, 'best_score': best_score,
                    'n_actions': len(actions),
                })

            if patience is not None and no_improve >= patience:
                reason = 'no_improve'
                break

            key = self.canonicalize(self.coords_of(game))
            if key in visited:
                stuck += 1
                if stuck > 5:
                    reason = 'stuck'
                    break
            visited.add(key)

            candidates = self.enumerate_actions(game, step)
            if not candidates:
                reason = 'no_candidates'
                break

            # ---- 试每个候选，落回原位；只在可执行且不改块数时计分 ----
            snap0 = self.snap(game)
            n_cells = len(self.coords_of(game))
            scored = []
            for act in candidates:
                if not self.apply_action(game, act, step):
                    self.restore(game, snap0)
                    continue
                new_coords = self.coords_of(game)
                if len(new_coords) != n_cells:
                    # 块数变了 = 有单元被吞/被生，不是合法形态内动作
                    self.restore(game, snap0)
                    continue
                s = sc(new_coords, spec)
                h = self.canonicalize(new_coords)
                mod_ok = (self.mod_filter(new_coords, step)
                          if self.mod_filter is not None else True)
                scored.append((s, h in visited, act, h, mod_ok))
                self.restore(game, snap0)

            if not scored:
                # 全不可执行 → 随机走一步（可能解开「所有动作都撞墙」的死结）
                picked = None
                for _ in range(3):
                    act = random.choice(candidates)
                    if self.apply_action(game, act, step):
                        picked = act
                        break
                    self.restore(game, snap0)
                if picked is None:
                    reason = 'no_candidates'
                    break
                actions.append(picked)
                hashes.append(self.canonicalize(self.coords_of(game)))
                trace.append(sc(self.coords_of(game), spec))
                continue

            if aggressiveness is not None and aggressiveness > 0 \
                    and len(scored) > 1:
                best_val = max(x[0] for x in scored)
                pool = [x for x in scored if x[0] >= best_val - aggressiveness]
            else:
                pool = scored

            # 排序：未访问优先 → 聚拢度高 → mod 约束 → 动作字典序（确定性）
            # **不要用状态集合排序**：那是 O(n log n) 的大对象比较，每步每个
            # 候选都算一次，纯浪费。方形的 tiebreak 用 bbox_area（形态相关，
            # 异形无对应），这里改用动作本身 —— act5 是小元组、可哈希、
            # 跨形态通用，足以保证「同样分数取同一个动作」的可复现性。
            # mod_ok 排在聚拢度之后：与方形 `gather_solve` 的排序键
            # (visited, -score, -mod_ok, bbox_area) 同序同权。
            pool.sort(key=lambda x: (x[1], -x[0], -x[4], x[2]))
            act = pool[0][2]

            self.restore(game, snap0)
            if not self.apply_action(game, act, step):
                reason = 'invalid_action'
                break
            actions.append(act)
            hashes.append(self.canonicalize(self.coords_of(game)))
            trace.append(sc(self.coords_of(game), spec))

        # ---- 未还原则回退到历史最优（丢弃无改进的尾步）----
        if not self.is_solved(game):
            self.restore(game, best_snap)
            actions = actions[:best_idx]
            hashes = hashes[:best_idx]
            trace = trace[:best_idx]

        # ---- 路径优化：去环 + 徘徊压缩 ----
        # **真盘重放终裁**（計劃 §3）：优化只在「从起始局面重放优化后的动作
        # 序列，末态与原路径末态 canonical 相等」时才采纳。这是我第一版写错
        # 的地方——写成了 `canonicalize(coords) == canonicalize(coords)`，
        # 同一表达式自比恒真，等于没验证。
        if (not self.is_solved(game) and self.optimize_path is not None
                and len(actions) >= 2):
            optimized = self.optimize_path(actions, start_hash, hashes)
            if optimized and len(optimized) < len(actions):
                # 记下原路径末态与起始局面，然后真盘重放验证
                orig_end = self.canonicalize(self.coords_of(game))
                probe_snap = self.snap(game)
                self.restore(game, start_snap)
                ok = True
                for a in optimized:
                    if not self.apply_action(game, a, step):
                        ok = False
                        break
                if ok and self.canonicalize(self.coords_of(game)) == orig_end:
                    actions = optimized
                    trace = trace[:len(optimized)]
                    hashes = hashes[:len(optimized)]
                else:
                    self.restore(game, probe_snap)

        end_score = sc(self.coords_of(game), spec)
        if self.is_solved(game):
            best_score = end_score
            reason = 'solved'

        return {
            'type': 'gather',
            'actions': actions,
            'solved': self.is_solved(game),
            'reason': reason,
            'score': end_score,
            'best_score': best_score,
            'best_step': best_idx,
            'steps': len(actions),
            'trace': trace,
            'elapsed': time.time() - started,
        }


def square_gatherer():
    """方形适配器实例 —— 共享骨架 + 方形形态件。

    供对照实验用：`shape_gather.solve_gather` 是它的薄封装，M1 的验收
    「先跑方形回归确认共享骨架无误伤」靠的就是这个。
    """
    from solver.state import snapshot, restore
    from solver.actions import enumerate_valid_actions, apply_action
    from solver.table_core import canonicalize
    from solver.ml.gather_solver import gather_metrics

    def coords_of(g):
        return frozenset((b.location[0], b.location[1]) for b in g.blocks)

    def score(coords, sp):
        return gather_metrics(coords, sp[0], sp[1])['score']

    def optimize_path(actions, start_hash, hashes):
        """去环：删掉回到旧状态的步，最后一步无条件保留。"""
        seen = {start_hash}
        new = []
        last = len(actions) - 1
        for i, (a, h) in enumerate(zip(actions, hashes)):
            if h in seen and i < last:
                continue
            seen.add(h)
            new.append(a)
        return new

    return ShapeGather(
        score, enumerate_valid_actions, apply_action, snapshot, restore,
        coords_of, canonicalize=canonicalize, mod_filter=None,
        optimize_path=optimize_path,
    )


def solve_gather(game, spec, step, **kw):
    """方形便捷入口（对照实验用）。"""
    return square_gatherer().solve(game, spec, step, **kw)