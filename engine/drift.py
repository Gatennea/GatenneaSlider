# -*- coding: utf-8 -*-
"""整体平移消去（gauge）与防偏移——**板型无关**的通用件。

为什么放在几何引擎
------------------
一次合法移动的语义是：选某条缝的一侧、取其中一个连通分量 A，整体平移
δ = step·d，其余（补集 B）不动。于是恒有

    (A + δ, B)  =  (A, B − δ) + δ          （两个局面只差一个整体平移）

而「整体平移」在本谜题的规则里是**对称**（Board.translate 不改任何规则
属性，Board.canonical_key 已把平移归一；还原判定同样是形状口径）。所以
任一动作序列都有一整族等价改写，判等只需比 canonical_key。

防偏移就是在这族里做选择：**让静止的那部分尽可能大**。一旦某步推动的
片超过全盘一半，就把等价的「推补集」版本换进来，接着把这次整体平移记
进 ``off``，后续步的动作按 ``off`` 整体平移（这正是魔方「整体转体可
消去」的对偶：整体平移 = 零代价的对称分量）。

这一层只认 BoardSpec：方形 / 三角 / 米字 / 碎三角 / 模型文件共用一份，
不写任何形态分支。这也意味着它能覆盖 gui 里三套渲染、三套经典引擎，
以及 ``EngineGame``。

与 ``solver/anti_drift.py`` 的关系
----------------------------------
那份是方形专用旧件（走 fill_macro.build_game + h/v 两族）。本模块是它的
板型无关推广：缝族、rank 钩子、朝向、半整晶格都走 spec，因此三角的
h/p/n 三族、米字四族与碎三角多族自动在内。

术语：
  · **锚点（anchor）**：初始局面的质心（引擎坐标）。改写只接受「落点离
    锚点更近」的换侧——与方形旧件同口径，把残余漂移钉在 ≤1 格。
  · **off**：当前影子局面相对「初始坐标系」的累计整体平移。改写发生在
    影子坐标系里，所以喂进来的后续步先按 off 平移。
"""
from .board import (Board, Block, Move, _add, _connected_components,  # noqa: F401
                    _dot, _group_closure)


# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------
def _family_of(spec, name):
    for fam in spec.seam_families:
        if fam.name == name:
            return fam
    raise ValueError(
        f"板型 {spec.name!r} 没有缝族 {name!r}"
        f"（已有: {[f.name for f in spec.seam_families]}")


def _neg(v):
    return tuple(-x for x in v)


def _centroid(board):
    """局面质心（引擎坐标，浮点元组）；空局面返回 None。"""
    if not board.blocks:
        return None
    n = len(board.blocks)
    return tuple(sum(b.point[i] for b in board.blocks) / n
                 for i in range(len(board.blocks[0].point)))


def _dist(board, anchor):
    if anchor is None:
        return 0.0
    c = _centroid(board)
    if c is None:
        return 0.0
    return sum((x - y) ** 2 for x, y in zip(c, anchor)) ** 0.5


def shift_move(spec, move, delta) -> Move:
    """把一个 Move 整体平移 delta（缝号随之平移，方向/步数/选中片形状不变）。

    ``t' = t + f(delta)``（f = 该缝族的点部线性泛函）。米字 h/v 的 rank 钩子
    带朝向修正，但修正是**朝向常量**：整片平移后每块的 rank 增量恒等于
    f(delta)（本函数对每块逐一校验，不齐就显式抛错，绝不静默取一个近似）。
    """
    delta = tuple(delta)
    if not delta:
        raise ValueError("shift_move 的 delta 不能为空元组")
    if all(x == 0 for x in delta):
        return move
    fam = _family_of(spec, move.family)
    dt = _dot(fam.coeffs, delta)
    moved = tuple(sorted((_add(p, delta), o) for p, o in move.moved))
    # 校验 rank 平移一致（朝向修正可能是常量，也可能按朝向分侧——后者
    # 仍是常量，但必须逐块确认，不能假设）
    for p, o in move.moved:
        if fam.rank_of(_add(p, delta), o) - fam.rank_of(p, o) != dt:
            raise ValueError(
                f"缝族 {fam.name!r} 的 rank 在平移 {delta} 下不是常量增量"
                f"（块 {p!r}/{o!r}）——该族不支持整体平移重标号")
    return Move(fam.name, move.t + dt, move.side, move.direction,
                move.step, moved)


def parallel_families(spec, direction):
    """与该方向平行（f(d)=0）的缝族——换侧只能用这些族的缝。"""
    return tuple(f for f in spec.seam_families
                 if _dot(f.coeffs, direction) == 0)


def _flip_candidates(board, move):
    """把「推 A」换成「推补集 B」的候选 Move（不校验，逐个交给 move_ok）。

    推导：B − δ 必须是一次合法移动，即 B 恰好是某条缝某一侧的**一个**
    连通分量（捆绑闭包后仍等于 B）。缝只能取自与 δ 平行的族；对每个这样的
    族，能「只切出 B」的缝号只有两个端点（t = max(rank B)+1 且 B 在下侧，
    或 t = max(rank A)+1 且 B 在上侧）——其余 t 都会把两侧的块并进来。
    这与方形旧件「遍历同族各线找同分量」等价，但不用枚举整棵移动树。
    """
    moved = frozenset(move.moved)
    rest = frozenset(board.keys) - moved
    if not rest or len(rest) >= len(moved):
        # 只有「原步推的是多数」才值得换侧；否则本来就是小片在滑。
        return ()
    out = []
    d = _neg(move.direction)
    for fam in parallel_families(board.spec, move.direction):
        ranks_moved = {fam.rank_of(p, o) for p, o in moved}
        ranks_rest = {fam.rank_of(p, o) for p, o in rest}
        lo_r, hi_r = min(ranks_rest), max(ranks_rest)
        lo_m, hi_m = min(ranks_moved), max(ranks_moved)
        # B 在下侧：t 介于 (max rank B, min rank A]
        if hi_r < lo_m:
            t = hi_r + 1
            out.append(Move(fam.name, t, -1, d, move.step,
                            tuple(sorted(rest))))
        # B 在上侧
        if hi_m < lo_r:
            t = hi_m + 1
            out.append(Move(fam.name, t, 1, d, move.step,
                            tuple(sorted(rest))))
    return tuple(out)


def flip_move(board, move):
    """返回一个与 move **形状等价**（只差整体平移）的「推补集」Move，或 None。

    合法性走 Board.move_ok（完整 legal_moves 语义：单侧连通分量 + 捆绑
    闭包 + 锁死缝 + 逐步碰撞/连通），因此不会给出引擎侧不认的动作。
    """
    for cand in _flip_candidates(board, move):
        if board.move_ok(cand):
            return cand
    return None


def shift_delta(move):
    """Move 的位移向量 step·direction（引擎点单位）。"""
    return tuple(move.step * x for x in move.direction)


def component_move(board, family, t, side, direction, step, key):
    """按「缝 + 侧 + 代表块」还原一条 Move（经典动作格式 → 引擎动作）。

    GUI/求解器的动作只记代表块（rep），选中片由引擎的连通分量决定；本函数
    用与 ``legal_moves`` 同一套判据（同侧连通分量 + 捆绑闭包）把它补全，
    再用 ``move_ok`` 逐项复核。代表块不在指定侧、分量补不齐、动作不合法，
    一律显式抛 ValueError —— 绝不静默换一个分量（那正是「回放播到一半走歪」
    的经典来源）。
    """
    fam = _family_of(board.spec, family)
    keys = board.keys
    key = (tuple(key[0]), key[1])
    if key not in keys:
        raise ValueError(f"代表块 {key!r} 不在当前局面")
    side_set = frozenset(
        k for k in keys
        if (fam.rank_of(k[0], k[1]) < t) == (side == -1))
    if key not in side_set:
        raise ValueError(
            f"代表块 {key!r} 不在缝 {family!r} t={t} 的 side={side} 一侧")
    comp = None
    for c in _connected_components(side_set, board.spec):
        if key in c:
            comp = c
            break
    if comp is None:
        raise ValueError(f"代表块 {key!r} 找不到所在的连通分量")
    moved = _group_closure(comp, board.block_map)
    mv = Move(fam.name, t, side, direction, step, tuple(sorted(moved)))
    if not board.move_ok(mv):
        raise ValueError(
            f"补全后的动作不合法: {family} t={t} side={side} "
            f"d={direction} step={step} 选中 {len(moved)} 块")
    return mv


# ----------------------------------------------------------------------
# 有状态改写器（流式逐段上报也复用同一实例）
# ----------------------------------------------------------------------
class FrameRewriter:
    """把动作序列改写成「大片不动、小片滑」的等价序列。

    用法::

        rw = FrameRewriter(board0)          # board0 = 初始局面
        new_moves = rw.feed(moves)          # moves 在**初始坐标系**里
        rw.end_board, rw.off, rw.flips

    ``feed`` 可分段调用（流式求解）：内部影子局面跨段前进，off 也跨段累积。

    不增不删步数：每步仍是一条合法移动，终态只是整体平移了 off。
    """

    def __init__(self, board0, anchor=None):
        if not isinstance(board0, Board):
            raise TypeError(
                f"FrameRewriter 需要 Board，收到 {type(board0).__name__}")
        self.board = board0
        self.anchor = _centroid(board0) if anchor is None else anchor
        self.off = tuple(0 for _ in self.anchor)
        self.flips = 0
        self.flip_idx = []
        self.n_seen = 0

    # -- 对外 ---------------------------------------------------------
    def feed(self, moves):
        out = []
        for raw in moves:
            if not isinstance(raw, Move):
                raise TypeError(f"feed 只收 Move，收到 {type(raw).__name__}")
            idx = self.n_seen
            self.n_seen += 1
            mv = shift_move(self.board.spec, raw, self.off)
            if not self.board.move_ok(mv):
                raise ValueError(
                    f"第 {idx} 步在影子局面不合法（off={self.off}）: "
                    f"{mv.family} t={mv.t} side={mv.side} d={mv.direction} "
                    f"step={mv.step} moved={len(mv.moved)} 块")
            nxt = self.board.apply(mv)
            flip = flip_move(self.board, mv)
            chosen, chosen_board = mv, nxt
            if flip is not None:
                fbd = self.board.apply(flip)
                # flip 与 nxt 只差整体平移：形状必然相同（构造保证）。
                # 只接受「离锚点更近」的那一侧，避免把大片反向推。
                if _dist(fbd, self.anchor) < _dist(nxt, self.anchor) - 1e-9:
                    self.off = tuple(a - b for a, b in
                                     zip(self.off, shift_delta(mv)))
                    chosen, chosen_board = flip, fbd
                    self.flips += 1
                    self.flip_idx.append(idx)
            self.board = chosen_board
            out.append(chosen)
        return out

    def feed_one(self, move):
        return self.feed([move])[0]


def rewrite_moves(board0, moves):
    """一次性改写整条 Move 序列 → (new_moves, end_board, flips)。"""
    rw = FrameRewriter(board0)
    new_moves = rw.feed(list(moves))
    return new_moves, rw.board, rw.flips


def rewrite_keys(spec, keys, moves, groups=None):
    """按块键集合造初始局面再改写（便捷入口；有捆绑组时传 groups）。"""
    board0 = Board.from_keys(spec, keys, groups)
    return rewrite_moves(board0, moves)


# ----------------------------------------------------------------------
# 显示侧：逐帧质心偏移（供三形态渲染共用）
# ----------------------------------------------------------------------
def drift_offsets(board0, boards):
    """每个局面质心相对 board0 的偏移（浮点向量），长度 = len(boards)+1。

    GUI 只需把返回的偏移从渲染位置扣掉，就能让整盘停在原地；
    与 ``solver/anti_drift.drift_offsets`` 同义，但吃 Board（任意板型）。
    """
    c0 = _centroid(board0)
    if c0 is None:
        return []
    out = [tuple(0.0 for _ in c0)]
    for b in boards:
        c = _centroid(b)
        out.append(tuple(x - y for x, y in zip(c, c0)))
    return out


def block_keys(coords, orientations=None):
    """(坐标[, 朝向]) 列表 → 块键集合（造 Board 用的小工具）。

    ``orientations`` 为 None 时全部当无朝向板型；给了就与逐项对齐
    （三角/米字的坐标本身已带朝向分量时用 ``key`` 形式直接传）。
    """
    if orientations is None:
        return frozenset((tuple(p), '') for p in coords)
    out = set()
    for p, o in zip(coords, orientations):
        out.add((tuple(p), o))
    return frozenset(out)
