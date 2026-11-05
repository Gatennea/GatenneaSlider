# -*- coding: utf-8 -*-
"""锚点式打乱序列规划（2026-11-06）。

用户口径
--------
* 锚点 = 初始几何重心；偏移量 = Σ(每块几何中心 − 锚点) 的**向量求和**。
  化简后就是「当前坐标和 − 初始坐标和」，一步的贡献 = Σ(final) − Σ(moved)。
  因此不需要认块、不需要方向表、不需要知道晶格：四种形态 + 自定义样式 /
  捆绑 / 编辑器模型板型共用同一套算法。
* 序列像 ``a b a' c b' ...``：连续两步尽量不选平行缝（除非别无选择），
  正反向自然交替；末尾几步把重心往锚点收回来。
* **允许最多偏离多少距离 = MAX_DRIFT（格），是硬上限不是软偏好**：任何会
  把重心推过上限的候选都不收，全过程与终局都有保证。过紧的上限会自动
  抬到「1.25 个最小合法步」，避免 step=2 大盘直接冻住；只有当连续多次
  「所有候选都越界、整步作废」时（说明盘面被钉住、min_score 重洗空转），
  才收下离锚点最近的一步打破僵局，放完立刻恢复严格上限。
* 全程只在「合法步里挑」，不改选中机制、不改玩家操作、不改安全打乱的
  「先提交 → 验可逆 → 不可逆回滚」链路。

⚠️ 为什么做不到「正反向步数相等 ⇒ 重心精确为零」：一步的贡献是
``动块数 × step × 方向``，同一条缝两侧块数不同，a 与 a' 幅度不相等，
光靠按方向凑对消不掉。所以这里用硬上限把重心钉在锚点附近，收尾步再
尽量往回收；精确归零能碰上就碰上，碰不上也是亚格级的偏移。

实测（16 类盘型 × 8 独立打乱）：终局重心偏移由 1.1~20.8 格降到
0.2~0.5 格，过程中最大 1 格，终局去重数不减，record 正放 / 逆放证书
全通过。详见 .workbuddy/memory/2026-11-06.md。
"""
import math
import random

# 总开关。置 False 时四套 shuffle 完全走原来的「随机选一步」路径（随机序列
# 与旧版一致），供 A/B 实测与紧急回退用。
ENABLED = True

# 过程中允许的「每块平均漂移」上限（单位：格）。越大越自由、越接近原随机
# 打乱，但动画里图形会跑得更远；越小越贴锚点，但可选步数变少。
DEFAULT_MAX_DRIFT = 1.0
# 当前生效的漂移上限；DEFAULT_MAX_DRIFT 是出厂值，改这个可实测调参
MAX_DRIFT = DEFAULT_MAX_DRIFT
# 超阈值时的软偏置强度（exp(-alpha * 归一化后的差距)）
SOFT_ALPHA = 0.60
# 单步抽候选数：硬上限必须「有得挑」，普通步抽 SOFT_DRAWS 个，
# 收尾步抽更多做比较
SOFT_DRAWS = 6
CLOSING_DRAWS = 16
# 硬上限：永远不收会把偏移推过上限的候选（一个都不剩就整步作废）。
HARD_CAP = True
# 偏移已到上限的几成时，放开「不选平行缝」的预筛，别挡住能拉回来的缝族
CAP_RELAX_RATIO = 0.60
# 连续这么多次「所有候选都越界、整步作废」才放一步例外，打破僵局。
# 偶发全拒是硬上限的正常代价；连续全拒说明盘面被钉住了（min_score 重洗
# 会一直空转），这时收下离锚点最近的一步，放完立刻恢复严格上限。
CAP_RELAX_AFTER = 10
# 收尾最多补几步；连续走不动几步就放弃
CLOSING_LIMIT = 16
CLOSING_STALL = 6
# 判定「回到锚点」的容差（坐标和都是整数 / 半整数，误差只可能来自浮点）
ANCHOR_EPS = 1e-6


# --------------------------------------------------------------------------
# 向量小工具（坐标维数随形态变化：方形 2 维、三角 / 米字 3 维）
# --------------------------------------------------------------------------
def vadd(a, b):
    return tuple(x + y for x, y in zip(a, b))


def vlen(v):
    return math.sqrt(sum(float(x) * float(x) for x in v))


def _part_sum(positions, k):
    """第 k 维坐标和；非数值分量（米字的朝向 q='N'/'E'…）记 0。

    朝向不随平移改变，对「坐标和」的贡献恒为 0，跳过它不影响锚点定义。
    """
    try:
        return sum(float(p[k]) for p in positions)
    except (TypeError, ValueError):
        return 0.0


def sum_positions(positions, dim):
    return tuple(_part_sum(positions, k) for k in range(dim))


def clear_flags(blocks):
    """没有 _clear_selection 的旧引擎（方形 / 三角）用的清选中回调。"""
    for b in blocks:
        b.be_opted = False


def is_parallel(k1, k2):
    """两条缝是否平行。

    给了 SeamFamily.coeffs（法向泛函）就用二维叉积判；没给就退化成
    「同一缝族名」——本项目所有预设里同族即平行，不同族不平行。
    """
    if isinstance(k1, tuple) and isinstance(k2, tuple) and len(k1) == 2 \
            and len(k2) == 2 and all(isinstance(x, (int, float))
                                     for x in k1 + k2):
        return k1[0] * k2[1] - k1[1] * k2[0] == 0
    return k1 == k2


# --------------------------------------------------------------------------
# 一步候选
# --------------------------------------------------------------------------
class StepCandidate:
    """一次「选缝 → 选片 → 平移」的试算结果（尚未提交）。"""

    __slots__ = ('gap_type', 'line', 'direction', 'block', 'moved', 'final',
                 'delta', 'parallel')

    def __init__(self, gap_type, line, direction, block, moved, final,
                 parallel):
        self.gap_type = gap_type
        self.line = line
        self.direction = direction
        self.block = block
        self.moved = tuple(tuple(p) for p in moved)
        self.final = tuple(tuple(p) for p in final)
        dim = len(self.moved[0]) if self.moved else 0
        # Σ(final) − Σ(moved)：这一步对「坐标和」的贡献
        self.delta = tuple(_part_sum(self.final, k) -
                           _part_sum(self.moved, k)
                           for k in range(dim))
        self.parallel = parallel

    @property
    def moved_set(self):
        return frozenset(self.moved)

    @property
    def final_set(self):
        return frozenset(self.final)


def _parallel_key(gap_type, parallel_keys):
    if parallel_keys is None:
        return gap_type
    return parallel_keys.get(gap_type, gap_type)


def draw_candidates(game, step, gaps, dirs_of, count=1, clear=None,
                    blocks=None, parallel_keys=None, rng=None):
    """从当前局面抽若干合法候选步（**只读试算，不提交**）。

    gaps      : [(gap_type, line), ...]，调用方已经做过「不选平行缝」过滤
    dirs_of   : gap_type → 该族方向字母表的可调用
    count     : 抽几次；失败的试算直接丢掉
    clear     : 清选中态的回调；None 时只清 be_opted
    blocks    : 块列表（EngineGame 用 .blocks 属性，语义一致）
    parallel_keys : gap_type → 法向泛函（可选，用于跨族平行判定）
    """
    rnd = rng or random
    blocks = blocks if blocks is not None else game.blocks
    out = []
    if not gaps or not blocks:
        return out
    for _ in range(max(1, count)):
        gap_type, line = rnd.choice(gaps)
        dirs = dirs_of(gap_type)
        if not dirs:
            continue
        direction = rnd.choice(dirs)
        block = rnd.choice(blocks)
        if clear is not None:
            clear()
        else:
            clear_flags(blocks)
        game.opt(gap_type, line, block)
        moved = tuple(tuple(b.location) for b in blocks if b.be_opted)
        if not moved:
            continue
        final = game.try_move(direction, step)
        if not final:
            continue
        out.append(StepCandidate(gap_type, line, direction, block, moved,
                                 final, _parallel_key(gap_type,
                                                      parallel_keys)))
    if clear is not None:
        clear()
    else:
        clear_flags(blocks)
    return out


def reapply(game, cand, step, clear=None, blocks=None,
            parallel_keys=None):
    """重新施加选中并刷新试算结果，返回 (final_positions, fresh_candidate)。

    draw_candidates 结束时清了选中态，EngineGame 的 try_move_ex 还会写
    ``_pending_board`` —— 提交前必须用**中选的那一步**再试算一次，否则
    commit_move 拿到的可能是最后一次试算的局面。
    """
    blocks = blocks if blocks is not None else game.blocks
    if clear is not None:
        clear()
    else:
        clear_flags(blocks)
    game.opt(cand.gap_type, cand.line, cand.block)
    moved = tuple(tuple(b.location) for b in blocks if b.be_opted)
    if not moved:
        if clear is not None:
            clear()
        else:
            clear_flags(blocks)
        return None
    final = game.try_move(cand.direction, step)
    if not final:
        if clear is not None:
            clear()
        else:
            clear_flags(blocks)
        return None
    fresh = StepCandidate(cand.gap_type, cand.line, cand.direction, cand.block,
                          moved, final,
                          _parallel_key(cand.gap_type, parallel_keys))
    return list(final), fresh


# --------------------------------------------------------------------------
# 规划器
# --------------------------------------------------------------------------
class AnchorPlanner:
    """一次 shuffle 对应一个实例；跟踪重心偏移、缝族与收尾步。"""

    def __init__(self, blocks, step, max_drift=DEFAULT_MAX_DRIFT,
                 parallel_keys=None, rng=None):
        self.step = step
        self.n = len(blocks)
        self.dim = len(blocks[0].location) if blocks else 0
        self.anchor = sum_positions([tuple(b.location) for b in blocks],
                                    self.dim)
        self.offset = (0.0,) * self.dim
        self.unit = None          # 一格在 location 坐标系下的长度（首步估出）
        self.min_step_drift = 0.0  # 最小一步带来的偏移，用来抬升过紧的上限
        self.prev_key = None
        self.prev_moved = None
        self.prev_final = None
        self.max_drift = max_drift
        self.parallel_keys = parallel_keys
        self.rng = rng or random
        self.steps = 0
        self.max_seen = 0.0
        self.soft_hits = 0
        self.forced_parallel = 0
        self.cap_hits = 0
        self.cap_streak = 0
        self.fallbacks = 0
        self.closing_steps = 0

    # ---- 度量 -----------------------------------------------------------
    def observe_unit(self, cands):
        """从候选步反推「一格有多长」，让阈值在不同晶格下都是格数。"""
        if self.unit is not None or not cands or not self.step:
            return
        vals = []
        for c in cands:
            k = len(c.moved)
            if k:
                u = vlen(c.delta) / (k * self.step)
                if u > 1e-9:
                    vals.append(u)
        if vals:
            vals.sort()
            self.unit = vals[len(vals) // 2]
            # 有些盘（方形 4×4 step=2）最小一步就要动 4 块，阈值设得比这
            # 还小会把所有候选全否决、打乱直接冻住。上限至少留出 1.25 个
            # 最小步，保证任何形态都走得动。
            self.min_step_drift = min(vlen(c.delta) for c in cands) / \
                self._scale()

    def _scale(self):
        return max(1e-9, (self.unit or 1.0) * max(1, self.n))

    def cap(self):
        """实际生效的偏移上限（格）。"""
        return max(self.max_drift, 1.25 * self.min_step_drift)

    def drift_cells(self):
        return vlen(self.offset) / self._scale()

    def is_anchored(self):
        return all(abs(x) <= ANCHOR_EPS for x in self.offset)

    # ---- 选步 -----------------------------------------------------------
    def candidate_count(self, closing=False):
        if closing:
            return CLOSING_DRAWS
        # 硬上限必须「有得挑」才有意义：每步至少抽 SOFT_DRAWS 个候选，
        # 否则只剩一个候选时要么越界、要么整步作废。
        if HARD_CAP:
            return SOFT_DRAWS
        if self.drift_cells() > self.max_drift:
            return SOFT_DRAWS
        return 1

    def _drift_after(self, cand):
        return vlen(vadd(self.offset, cand.delta)) / self._scale()

    def filter_gaps(self, gaps):
        """连续两步不选平行缝；当前可选缝全平行时原样返回（用户留的例外）。

        偏移贴近硬上限时不预筛——拉回偏移往往得用上一缝族，这里先放行，
        由 select 在候选层做「尽量不选平行缝」的偏好。
        """
        if self.prev_key is None or not gaps:
            return gaps
        if HARD_CAP and self.drift_cells() > CAP_RELAX_RATIO * self.cap():
            return gaps
        nonpar = [g for g in gaps
                  if not is_parallel(_parallel_key(g[0], self.parallel_keys),
                                     self.prev_key)]
        if nonpar:
            return nonpar
        self.forced_parallel += 1
        return gaps

    def _weighted(self, pool, alpha):
        scores = [vlen(vadd(self.offset, c.delta)) for c in pool]
        lo = min(scores)
        scale = self._scale()
        weights = [math.exp(-alpha * min(40.0, (s - lo) / scale))
                   for s in scores]
        total = sum(weights)
        x = self.rng.random() * total
        acc = 0.0
        for c, w in zip(pool, weights):
            acc += w
            if x <= acc:
                return c
        return pool[-1]

    def select(self, cands, closing=False):
        if not cands:
            return None
        self.observe_unit(cands)
        pool = cands
        # 别选「正好撤销上一步」的候选：那会原地蹭、也不会更乱
        if self.prev_moved is not None:
            filtered = [c for c in pool
                        if not (c.moved_set == self.prev_final and
                                c.final_set == self.prev_moved)]
            if filtered:
                pool = filtered
        if closing:
            # 收尾同样不许越界；确定性取「离锚点最近」的一步，让最后几步
            # 真的把图形收回来（加权抽样会漂，动画里看不出回锚）
            if HARD_CAP:
                within = [c for c in pool
                          if self._drift_after(c) <= self.cap()]
                if not within:
                    return None
                pool = within
            scores = [self._drift_after(c) for c in pool]
            lo = min(scores)
            return self.rng.choice([c for c, s in zip(pool, scores)
                                    if s <= lo + 1e-12])
        # 硬上限：偏移不许被推过 cap()，超出上限的候选一律不收、整步作废。
        # 但连续多次全拒会把盘面钉在聚拢态，min_score 重洗永远达不到
        # （2026-11-06 契约测试偶发 compute_score=1.000）：这时收下「离锚点
        # 最近」的一步打破僵局，放完立刻恢复严格上限，不做持久放宽。
        if HARD_CAP:
            allowed = [c for c in pool
                       if self._drift_after(c) <= self.cap()]
            if not allowed:
                self.cap_hits += 1
                self.cap_streak += 1
                if self.cap_streak < CAP_RELAX_AFTER:
                    return None
                self.cap_streak = 0
                pool = [min(pool, key=self._drift_after)]
            else:
                self.cap_streak = 0
                if len(allowed) < len(pool):
                    self.cap_hits += 1
                pool = allowed
        # 连续两步尽量不选平行缝（用户口径：「盡量」，不是硬禁）
        if self.prev_key is not None:
            nonpar = [c for c in pool
                      if not is_parallel(c.parallel, self.prev_key)]
            if nonpar:
                pool = nonpar
            else:
                self.forced_parallel += 1
        # 只有在硬上限都没兜住时才稀疏介入，避免每步都带偏置让打乱变保守
        if self.drift_cells() > self.cap():
            self.soft_hits += 1
            return self._weighted(pool, SOFT_ALPHA)
        return self.rng.choice(pool)

    # ---- 提交 / 收尾 ----------------------------------------------------
    def commit(self, cand, blocks, record_len=0):
        self.offset = vadd(self.offset, cand.delta)
        self.prev_key = cand.parallel
        self.prev_moved = cand.moved_set
        self.prev_final = cand.final_set
        self.steps += 1
        self.max_seen = max(self.max_seen, self.drift_cells())

    def finish(self, move_once, blocks, record=None, after_restore=None,
               limit=CLOSING_LIMIT, guard=None):
        """末尾补几步回到锚点。

        move_once()：走一步收尾步。可返回 bool，也可返回
        ``(是否走成, 新散度)``（三套旧 shuffle 的 _random_move 就是后者），
        散度在收尾阶段不再被消费，直接忽略即可。
        只保留**让重心更靠近锚点**的收尾步；一旦某步没帮上忙就撤掉它并
        结束，于是动画里最后几步是真正的「往回走」，不会白演几步再回退。
        guard：调用方给的「当前局面仍然合格」回调（如 min_score 聚拢度）。
        收尾是贪心往锚点收，偶尔会把图形重新拼紧、把题目变简单；一旦
        guard 变假就撤掉这一步并收尾，宁可留一点亚格级偏移也不牺牲难度。
        过程与终局的偏移上界由 HARD_CAP 保证。
        """
        def snapshot():
            return (tuple(tuple(b.location) for b in blocks),
                    len(record) if record is not None else 0,
                    self.offset)

        best = snapshot()
        stalled = 0
        for _ in range(limit):
            if self.is_anchored():
                break
            res = move_once()
            ok = res[0] if isinstance(res, tuple) else bool(res)
            if not ok:
                stalled += 1
                if stalled >= CLOSING_STALL:
                    break
                continue
            stalled = 0
            self.closing_steps += 1
            if guard is not None and not guard():
                # 这一步把题目变简单了：撤掉它，收尾到此为止
                self._apply(best, blocks, record)
                if after_restore is not None:
                    after_restore()
                break
            if vlen(self.offset) < vlen(best[2]) - 1e-9:
                best = snapshot()
            else:
                # 这一步没把重心拉近：撤销它，收尾到此为止
                self._apply(best, blocks, record)
                if after_restore is not None:
                    after_restore()
                break
        return self.is_anchored()

    def _apply(self, snapshot_value, blocks, record=None):
        locs, rec_len, off = snapshot_value
        for b, p in zip(blocks, locs):
            b.location = list(p)
        if record is not None:
            del record[rec_len:]
        self.offset = off
        self.fallbacks += 1
