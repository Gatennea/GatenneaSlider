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

import hashlib
import random
import time

__all__ = ['ShapeGather', 'solve_gather', 'stable_seed',
           'shape_restart_kwargs']


def stable_seed(coords):
    """由初始坐标派生**跨进程稳定**的随机种子。

    不能用内置 `hash()`：集合迭代序与 PYTHONHASHSEED 会让它每次跑都变，
    玩家同一盘连点两次求解会拿到不同结果。坐标一律转成字符串再排序，
    米字格的半整数 / 三元组 rep 也照常稳定。
    """
    key = repr(sorted(tuple(map(str, c)) for c in coords)).encode('utf-8')
    return int.from_bytes(hashlib.md5(key).digest()[:4], 'big')


def shape_restart_kwargs(coords, stochastic=None, seed=None,
                         max_kicks=3, kick_moves=3):
    """把异形统一入口的 `stochastic` 翻译成 ShapeGather.solve 的参数。

    三种语义（待办 §三十四 第 6 条，2026-11-11 生产参数 A/B 实测）：
      · None（**异形默认**）＝只开 ③ 随机踢、关掉 ② 随机挑步。
        实测完整 stochastic（②+③）会把贪心骨架打坏（平均聚拢度
        0.8279 → 0.8170），只开 ③ 才提高（→ 0.8427）。seed 由初始
        坐标稳定派生，同盘连点两次结果一致、可复现。
      · True ＝完整 stochastic（与方形 `gather_solve` 同义），实验用。
      · False＝全关，移植前逐位一致（回归 / 对照实验用）。

    ⚠️ 返回的参数**只喂 ShapeGather.solve**，不经过 `gather_solve_unified`
    的按形态分发：方形 `gather_solve` 没有 random_pick / kick /
    restart_on_kick 这三个参数，透传过去会 TypeError。
    """
    if stochastic is None:
        return dict(stochastic=False, random_pick=False, kick=True,
                    restart_on_kick=False,
                    seed=stable_seed(coords) if seed is None else seed,
                    max_kicks=max_kicks, kick_moves=kick_moves)
    if stochastic:
        return dict(stochastic=True, random_pick=None, kick=None,
                    restart_on_kick=False, seed=seed,
                    max_kicks=max_kicks, kick_moves=kick_moves)
    return dict(stochastic=False, random_pick=False, kick=False,
                restart_on_kick=False, seed=None,
                max_kicks=max_kicks, kick_moves=kick_moves)


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
              cancel_check=None, progress_callback=None,
              stochastic=False, seed=None, max_kicks=3, kick_moves=3,
              random_pick=None, kick=None, restart_on_kick=False):
        """贪心聚拢主循环。

        参数与方形 `gather_solve` **同名同义、默认值也照抄**（patience=150、
        aggressiveness=0.2）—— 这些是方形上反复调过的常数，异形没有理由先
        设成更保守的猜测。三角形批量实测若显示需要不同的值，那是实测结论，
            不是拍脑袋的起点（把默认值当实验变量会导致「方形调参结论」与
            「异形默认值」互相污染）。

        随机探索（2026-11-11 从方形 `gather_solve` 移植，待办 §三十四 第 6 条；
        原先只有方形有，异形没有）：
            stochastic : False（默认）= 完全确定性，与移植前**逐位一致**，
                         便于回归与 A/B 对照；True = ② aggressiveness band
                         内随机挑步 + ③ 卡住（连续 patience 步无改进历史最优）
                         时随机踢 `kick_moves` 步跳出局部最优，最多
                         `max_kicks` 脚（iterated local search）。
            seed       : 固定随机源，保证同 seed 同盘可复现；None 且
                         stochastic=True 时随机生成并写进返回字典。
            random_pick / kick : 把 ②（band 内随机挑步）与 ③（卡住随机踢）
                         **拆成两个独立开关**，None = 跟随 stochastic（此时
                         与方形语义完全一致）。拆开是 2026-11-11 异形 A/B
                         实测所需：完整 stochastic 的 ② 会破坏贪心骨架，
                         只有 ③ 有希望提高平均最终聚拢度。
            restart_on_kick : 踢完清空 visited 并把 stuck 归零。异形状态
                         空间小，扰动后极易立刻撞回旧状态、被 `stuck > 5`
                         掐断，等于「踢了白踢」；清掉去环集合才是一次真正
                         的随机重启。默认 False = 与方形原实现一致。
        与方形一样，随机源是**局部** `random.Random`，不吃全局 random 模块
        的状态 —— 显式给 seed 时，即便调用方随后用了全局 random 也不漂移。

        返回 dict（与方形一致的键名，便于对照报告）：
            type / actions / solved / reason / score / best_score /
            best_step / steps / elapsed，另带 stochastic / seed / kicks。
        """
        sc = self.shape_score
        started = time.time()

        _random_pick = stochastic if random_pick is None else random_pick
        _kick = stochastic if kick is None else kick

        actions = []
        trace = []
        hashes = []        # 每步执行后的 canonical hash（去环用）
        visited = set()
        stuck = 0
        no_improve = 0

        # 随机性（stochastic 探索）：默认走全局 random.choice，与移植前
        # 逐位一致；显式 seed 或开 stochastic 时改用局部 Random。
        if stochastic or _random_pick or _kick or seed is not None:
            if seed is None:
                seed = random.randrange(1 << 31)
            rng = random.Random(seed)
        else:
            rng = None
        rchoice = rng.choice if rng is not None else random.choice
        kick_count = 0

        def _do_kick(k):
            """随机扰动当前局面 k 步（iterated local search 的「踢」）。

            与方形 `_do_kick` 同构：每步从真实合法动作里随机挑一个，
            成功的步照常记进 actions / hashes / trace，末尾「回退到历史
            最优」会把它们连同无改进尾步一起截掉，不会污染返回的解法。

            ⚠️ **不能照抄方形的「失败即 break」**：异形（尤其米字错位态）
            的 `enumerate_actions` 里大量动作当下不可执行（跨晶格碰撞 /
            rep 落到别的分量），随机挑一个失败就把整脚废掉，实测每脚
            平均只走 1 步 ⇒ 扰动强度约等于零，A/B 里「踢了白踢」。
            这里改成失败还原后**继续重试**，每脚真的走满 k 步（或候选
            试完 `3k` 次仍不够才收）。这是移植时按形态适配，不是改语义。
            """
            applied = 0
            for _ in range(k * 3):
                if applied >= k:
                    break
                cands = self.enumerate_actions(game, step)
                if not cands:
                    break
                a = rchoice(cands)
                snap_k = self.snap(game)
                n_before = len(self.coords_of(game))
                if not self.apply_action(game, a, step):
                    self.restore(game, snap_k)
                    continue
                coords = self.coords_of(game)
                if len(coords) != n_before:
                    self.restore(game, snap_k)
                    continue
                actions.append(a)
                hashes.append(self.canonicalize(coords))
                trace.append(sc(coords, spec))
                applied += 1
            return applied > 0

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

            # 停机 / 随机踢：连续 patience 步没有改进历史最优。
            # ③ 开 stochastic 时先随机踢一脚（最多 max_kicks 次）再判停机，
            #   踢成功就重置 no_improve 继续贪心，等价于一次随机重启。
            if patience is not None and no_improve >= patience:
                if _kick and kick_count < max_kicks and _do_kick(kick_moves):
                    kick_count += 1
                    no_improve = 0
                    if restart_on_kick:
                        # 新一轮局部搜索：旧的去环集合会把扰动后的路全堵死，
                        # 清掉并把当前态设为新起点（不清会让下一轮立刻
                        # stuck>5 停机，踢等于没发生）。
                        visited.clear()
                        stuck = 0
                        visited.add(self.canonicalize(self.coords_of(game)))
                    continue
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
                    act = rchoice(candidates)
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
            # 选步：② stochastic 时在 band 内随机挑（优先没访问过的状态），
            # 默认仍走原来的确定性排序，逐位一致。
            if _random_pick and rng is not None and len(pool) > 1:
                unvisited = [x for x in pool if not x[1]]
                choose_from = unvisited if unvisited else pool
                act = rchoice(choose_from)[2]
            else:
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
            'stochastic': stochastic,
            'seed': seed,
            'kicks': kick_count,
            'random_pick': _random_pick,
            'kick': _kick,
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