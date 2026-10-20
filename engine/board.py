# -*- coding: utf-8 -*-
"""板型（BoardSpec）与局面（Board）——几何引擎的规则层。

一句话：**一个板型 = 一份数据；一个局面 = 一份不可变状态；合法移动 =
纯函数**。GUI、求解器、数学实验都只同这一层对话（见
docs/spec/几何引擎.md）。

模型（与 docs/math/异形推广方案_2026-10-16.md 的「板型 B」同构）：

    板型 = (格点 Λ×朝向 Ω, 方向生成元 D, 缝族 Σ, 还原态 S₀, 块数 K)
    局面 = Λ×Ω 上的有限块集合（每块 = 点 + 朝向 + 捆绑组）
    合法移动 = 选一条缝 σ、取其一侧的某个连通分量 C（捆绑组整组拖动）、
              沿平行于 σ 的方向 d 平移 step 个单位；要求途中不碰撞、
              每步后整体仍单一连通、两侧都非空。

与现有三引擎的关系（P0 原型范围）：
  · 方形板型已与 game.SliderMatrix 差分对齐（test/_test_geometry_engine.py：
    移动结果集合 / 规范形 / 还原判定逐项全等）；
  · 三角 / 米字板型的参数表已在数学文档给出，实例化属 P2（米字的
    「锁死缝」判据走本层的 seam_clear 钩子，三角的凸包还原判定走
    solved_check 钩子——两个钩子就是为它们预留的）；
  · 三维立方晶格 preset 用于验证「核心零改动延伸维度」（见 registry）。

纯逻辑零 pygame；所有不合法输入显式抛错（AGENTS.md §2）。
"""

from dataclasses import dataclass

from .lattice import Lattice


# ----------------------------------------------------------------------
# 基础小工具
# ----------------------------------------------------------------------
def _dot(coeffs, point) -> int:
    """线性泛函求值：f(p) = Σ coeffs[i] * p[i]。"""
    return sum(c * p for c, p in zip(coeffs, point))


def _add(point, delta):
    return tuple(point[i] + delta[i] for i in range(len(point)))


def _connected_components(points, lattice):
    """按 lattice 邻接把点集拆成连通分量（list[frozenset]）。"""
    remaining = set(points)
    comps = []
    while remaining:
        seed = remaining.pop()
        comp = {seed}
        stack = [seed]
        while stack:
            p = stack.pop()
            for q in lattice.neighbors(p):
                if q in remaining:
                    remaining.discard(q)
                    comp.add(q)
                    stack.append(q)
        comps.append(frozenset(comp))
    return comps


def _is_connected(points, lattice) -> bool:
    """点集是否单一连通（空集视为连通，与既有引擎口径一致）。"""
    if not points:
        return True
    return len(_connected_components(points, lattice)) == 1


def _group_closure(comp, point_map):
    """捆绑扩展：分量所在的捆绑组整组拖入（组是刚体，缝切不开组）。

    与 game.SliderMatrix.opt 的捆绑扩展同语义：组员在盘面远处也会被
    拉扯进选中片，碰撞由移动校验拒绝（捆绑魔方「转不动」体感）。
    """
    gids = {point_map[p].group for p in comp if point_map[p].group}
    if not gids:
        return frozenset(comp)
    out = set(comp)
    changed = True
    while changed:  # 不动点迭代（组 id 唯一标识一组，实际一轮即收敛）
        changed = False
        for p, b in point_map.items():
            if b.group in gids and p not in out:
                out.add(p)
                changed = True
    return frozenset(out)


# ----------------------------------------------------------------------
# 数据类
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Block:
    """一个滑块块：格点 + 朝向标签 + 捆绑组号。

    · point: 整数坐标元组（长度 = lattice.dim；半整晶格见 Lattice.scale）；
    · orient: 朝向标签（方形为 ''；三角 'up'/'down'；米字 'N/E/S/W'）。
      平移不改变朝向；
    · group: 捆绑组号（0 = 未捆绑；自由捆绑模式，docs/spec/bandaged_mode.md）。

    ⚠️ P0 边界：局面的唯一性键是 **point**（同点不能有两块）。米字
    「同格心 4 朝向」需要 (point, orient) 联合键，属 P2 第一件工作
    （见 docs/spec/几何引擎.md §3 硬骨头 7）；本类的 orient 字段与
    相关校验是为它预留的数据位，P0 只用到 ''。
    """

    point: tuple
    orient: str = ''
    group: int = 0


@dataclass(frozen=True)
class SeamFamily:
    """一条缝族：格空间被一族平行超平面切割。

    · name: 族名（方形 'h'/'v'；三角 'h'/'p'/'n'；米字 'h'/'v'/'d1'/'d2'；
      三维 'r'/'c'/'d'——词汇表随板型注册，不再有三处硬编码表）；
    · coeffs: 线性泛函系数，缝实例 t 的超平面 = {p : f(p) = t}，
      一侧 = {p : f(p) < t}（side=-1），另一侧 = {p : f(p) ≥ t}（side=+1）；
    · parallel: 与该缝平行的单位方向（f(d)=0），即这条缝允许的平移方向。

    ⚠️ P0 边界：侧判定只看点。米字对角族 d1/d2 的侧判定**依赖朝向**
    （game_mi.py 的 gap_rank 按朝向分侧），需要「orient 参与侧判定」
    的扩展点（side 钩子），属 P2（见 docs/spec/几何引擎.md §3 硬骨头 9）。
    """

    name: str
    coeffs: tuple
    parallel: tuple


@dataclass(frozen=True)
class Move:
    """一个合法移动（不可变值对象，可哈希、回放、进存档）。

    注意 t 与既有引擎「行号」差 1（t = line + 1，切分族双射等价）——
    P1 做宏回放 / 存档互通时需要一层映射（见 docs/spec/几何引擎.md §5）。
    """

    family: str
    t: int
    side: int                 # -1 / +1（被移动分量在缝的哪侧）
    direction: tuple          # 单位方向
    step: int                 # 单位步数（游戏的「等级」）
    moved: tuple              # 被移动的位置集合（排序元组）


@dataclass(frozen=True)
class BoardSpec:
    """板型：定义一种谜题所需的全部数据（「代码作为基石」的载体）。

    字段：
        name: 板型名（注册表键）。
        lattice: 格点（坐标/邻接/对称群）。
        directions: 方向生成元 D（单位步偏移；每步须平行于至少一条缝族）。
        seam_families: 缝族 Σ。
        orientations: 合法朝向标签（() = 无朝向，如方形）。
        goal_blocks: 还原态 S₀（Block 元组）。
        seam_clear: 可选钩子 (family, t, board) -> bool。返回 False =
            该缝被「锁死」（几何上切不动）——米字双重晶格错位态下横竖缝
            整条穿过块内部的 span 判据就是它（P2 落地）；None = 无锁死。
        solved_check: 可选钩子 (board) -> bool，覆盖默认的「与还原态
            规范化相等」（三角的凸包+边长+内部计数判定属此类，P2 落地）。
        cell_polygon: 可选钩子 (point, orient) -> 多边形顶点元组。
            纯几何、零 pygame——GUI 绘制层据此画格子（「GUI 上绘制」
            的数据接口；方形给单位方格，米字给直角等腰三角）。

    ⚠️ P0 边界（诚实声明，防 P2 排期误判）：本板型模型已覆盖「半整
    坐标 + 奇偶晶格 + 任意维度 + 声名式锁死/还原钩子」，但**尚未**
    覆盖米字的三处结构性需求——同点多朝向联合键、orient 进规范形、
    对角缝朝向相关侧判定（详见 docs/spec/几何引擎.md §3 硬骨头 7/8/9）。
    """

    name: str
    lattice: object               # Lattice
    directions: tuple
    seam_families: tuple
    orientations: tuple = ()
    goal_blocks: tuple = ()
    seam_clear: object = None
    solved_check: object = None
    cell_polygon: object = None

    def __post_init__(self):
        if not isinstance(self.lattice, Lattice):
            raise TypeError(
                f"板型 {self.name!r} 的 lattice 须为 Lattice 实例，"
                f"收到 {type(self.lattice).__name__}")
        if not self.directions:
            raise ValueError(f"板型 {self.name!r} 的方向表为空（永冻板型）")
        if not self.seam_families:
            raise ValueError(f"板型 {self.name!r} 的缝族为空（永冻板型）")
        for hook_name in ('seam_clear', 'solved_check', 'cell_polygon'):
            hook = getattr(self, hook_name)
            if hook is not None and not callable(hook):
                raise TypeError(
                    f"板型 {self.name!r} 的 {hook_name} 须可调用或 None，"
                    f"收到 {type(hook).__name__}")
        lat = self.lattice
        dim = lat.dim
        # 方向表：整数、分量 ∈ {-1,0,1}、至少一个非零、长度=dim
        for d in self.directions:
            if (not isinstance(d, tuple) or len(d) != dim
                    or not all(isinstance(x, int) for x in d)
                    or any(x not in (-1, 0, 1) for x in d) or not any(d)):
                raise ValueError(
                    f"板型 {self.name!r} 的方向 {d!r} 非法："
                    f"须为长度 {dim}、分量 ∈ {{-1,0,1}} 的整数元组")
        # 缝族：泛函长度=dim；parallel 非空、⊆ directions、且 f(d)=0
        dir_set = set(self.directions)
        for fam in self.seam_families:
            if (not isinstance(fam.coeffs, tuple) or len(fam.coeffs) != dim
                    or not all(isinstance(x, int) for x in fam.coeffs)):
                raise ValueError(
                    f"板型 {self.name!r} 缝族 {fam.name!r} 的泛函系数非法")
            if not fam.parallel:
                raise ValueError(
                    f"板型 {self.name!r} 缝族 {fam.name!r} 没有平行方向")
            for d in fam.parallel:
                if d not in dir_set:
                    raise ValueError(
                        f"板型 {self.name!r} 缝族 {fam.name!r} 的平行方向 "
                        f"{d!r} 不在方向表内")
                if _dot(fam.coeffs, d) != 0:
                    raise ValueError(
                        f"板型 {self.name!r} 缝族 {fam.name!r} 的方向 {d!r} "
                        f"不平行于该缝（f(d)={_dot(fam.coeffs, d)}）")
        # 每个方向至少平行于一条缝族（否则永不被任何缝允许）
        for d in self.directions:
            if not any(_dot(fam.coeffs, d) == 0 for fam in self.seam_families):
                raise ValueError(
                    f"板型 {self.name!r} 的方向 {d!r} 不平行于任何缝族，"
                    f"该方向永不可用")
        # 朝向标签
        for b in self.goal_blocks:
            if self.orientations and b.orient not in self.orientations:
                raise ValueError(
                    f"板型 {self.name!r} 还原态块的朝向 {b.orient!r} "
                    f"不在合法朝向 {self.orientations} 内")
            if not self.orientations and b.orient != '':
                raise ValueError(
                    f"板型 {self.name!r} 未声明朝向，还原态块却带 "
                    f"{b.orient!r}")
        # 还原态自检：块数 > 0、点不重复、点在格上、单一连通
        if self.goal_blocks:
            pts = [b.point for b in self.goal_blocks]
            if len(set(pts)) != len(pts):
                raise ValueError(f"板型 {self.name!r} 还原态存在重复坐标")
            for p in pts:
                if not lat.valid(p):
                    raise ValueError(
                        f"板型 {self.name!r} 还原态坐标 {p!r} 不在格上")
            if not _is_connected(set(pts), lat):
                raise ValueError(f"板型 {self.name!r} 还原态不单一连通")

    def goal_canonical(self):
        """还原态的规范形（is_solved 的比较基准）。

        P1 起缓存：BoardSpec 不可变（frozen），还原态规范形永远不变 →
        缓存永不过期。frozen dataclass 挂私有字段用 object.__setattr__
        （与 Board.__post_init__ 整理 blocks 同手法）。注意空还原态返回
        ()（falsy 但不能用真值判缓存——用 ``is None``）。
        """
        cached = getattr(self, '_goal_canonical', None)
        if cached is None:
            cached = Board(self, self.goal_blocks).canonical_key()
            object.__setattr__(self, '_goal_canonical', cached)
        return cached


@dataclass(frozen=True)
class Board:
    """一个具体局面：不可变块集合 + 其板型。

    不可变（frozen + tuple 存储）是刻意设计：BFS / 差分测试 / 撤销栈
    都可以安全共享实例；移动 = 纯函数（apply 返回新 Board）。

    ⚠️ P0 边界：块按 point 唯一（同点不能叠两块）。米字「同格心 4
    朝向」需要 (point, orient) 联合键，属 P2（几何引擎.md §3 硬骨头 7）。
    """

    spec: object               # BoardSpec
    blocks: tuple              # 排序后的 Block 元组

    def __post_init__(self):
        if not isinstance(self.spec, BoardSpec):
            raise TypeError(
                f"Board.spec 须为 BoardSpec 实例，收到 {type(self.spec).__name__}")
        blocks = tuple(sorted(self.blocks,
                              key=lambda b: (b.point, b.orient, b.group)))
        object.__setattr__(self, 'blocks', blocks)
        spec = self.spec
        seen = set()
        for b in blocks:
            if b.point in seen:
                raise ValueError(f"局面存在重复坐标块: {b.point!r}")
            seen.add(b.point)
            if not spec.lattice.valid(b.point):
                raise ValueError(f"块坐标 {b.point!r} 不在板型格上")
            if spec.orientations:
                if b.orient not in spec.orientations:
                    raise ValueError(
                        f"块朝向 {b.orient!r} 不在板型 {spec.name!r} 的 "
                        f"合法朝向内")
            elif b.orient != '':
                raise ValueError(
                    f"板型 {spec.name!r} 未声明朝向，块却带 {b.orient!r}")

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------
    @classmethod
    def from_points(cls, spec, points, orient='', groups=None):
        """从点集造局面（groups: point -> 组号，可选）。"""
        groups = groups or {}
        return cls(spec, tuple(Block(tuple(p), orient, groups.get(tuple(p), 0))
                               for p in points))

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    @property
    def points(self):
        return frozenset(b.point for b in self.blocks)

    @property
    def point_map(self):
        return {b.point: b for b in self.blocks}

    @property
    def block_count(self):
        return len(self.blocks)

    def translate(self, delta):
        """整体平移（造测试态用；不改变任何规则属性）。"""
        return Board(self.spec, tuple(
            Block(_add(b.point, delta), b.orient, b.group)
            for b in self.blocks))

    # ------------------------------------------------------------------
    # 规范化 / 还原判定
    # ------------------------------------------------------------------
    def canonical_key(self):
        """规范形：全部自同构 × 平移归一，取字典序最小。

        与 solver/table_core.canonicalize 同源同语义（2 维即 D4 八变换），
        但按任意维度/任意格点生成——3 维自动得 48 对称，米字半整格自动
        兼容（其奇偶约束对超八面体群封闭）。

        ⚠️ P0 边界：只对**点集**规范化（orient / group 不参与）。这对
        Ω={∅}（方形）完备；米字的规范形需要 (point, orient) 联合变换
        （对称群含朝向置换），属 P2（几何引擎.md §3 硬骨头 8）。
        """
        pts = [b.point for b in self.blocks]
        if not pts:
            return ()
        dim = self.spec.lattice.dim
        best = None
        for sym in self.spec.lattice.iter_symmetries():
            tp = [sym(p) for p in pts]
            m = tuple(min(p[i] for p in tp) for i in range(dim))
            norm = tuple(sorted(
                tuple(p[i] - m[i] for i in range(dim)) for p in tp))
            if best is None or norm < best:
                best = norm
        return best

    def is_solved(self):
        """是否还原。默认 = 与还原态规范化相等（旋转/翻面都算）；
        板型可挂 solved_check 钩子覆盖（三角的凸包判定，P2）。"""
        if self.spec.solved_check is not None:
            return bool(self.spec.solved_check(self))
        if not self.spec.goal_blocks:
            raise ValueError(f"板型 {self.spec.name!r} 未定义还原态")
        return self.canonical_key() == self.spec.goal_canonical()

    # ------------------------------------------------------------------
    # 合法移动
    # ------------------------------------------------------------------
    def legal_moves(self, step: int):
        """枚举全部合法移动（完整动作空间，不是代表块近似）。

        与 GUI 锚定点击的语义一致：每条缝的每一侧、每一连通分量、每一
        平行方向、step 个单位（逐步校验碰撞与连通）。注意这与
        solver/actions.enumerate_valid_actions 的代表块枚举不同——后者
        每 (缝, 侧, 方向) 只试第一个块所在的分量（已知欠账，见
        solver/ml/tri_adapter.py 对 rep_key 的说明）；本层给完整空间。

        step 定义域 ≥ 1（等级 = 步长）。既有引擎 step=0 是「空转也算
        合法移动」的怪癖（try_move 返回原位），引擎显式拒绝这种废步。
        """
        if type(step) is not int or step < 1:
            raise ValueError(f"step 须为 ≥ 1 的整数，收到 {step!r}")
        spec = self.spec
        pts = self.points
        if not pts:
            return ()
        pmap = self.point_map
        lat = spec.lattice
        out = []
        for fam in spec.seam_families:
            vals = {p: _dot(fam.coeffs, p) for p in pts}
            lo, hi = min(vals.values()), max(vals.values())
            # t ∈ (lo, hi]：下侧必含 f=lo 的点、上侧必含 f=hi 的点，
            # 两端非空由取值范围保证（无需再查空侧）。
            for t in range(lo + 1, hi + 1):
                # 锁死缝（米字 span 判据的落点，P2）：几何上切不动
                if spec.seam_clear is not None and not spec.seam_clear(fam, t, self):
                    continue
                side_lo = frozenset(p for p in pts if vals[p] < t)
                side_hi = pts - side_lo
                for side, side_set in ((-1, side_lo), (1, side_hi)):
                    for comp in _connected_components(side_set, lat):
                        moved = _group_closure(comp, pmap)
                        if len(moved) == len(pts):
                            continue  # 全员选中 = 整体平移，拒绝
                        rest = pts - moved
                        for d in fam.parallel:
                            if self._slide_ok(moved, rest, d, step, lat):
                                out.append(Move(fam.name, t, side, d, step,
                                                tuple(sorted(moved))))
        return tuple(out)

    @staticmethod
    def _slide_ok(moved, rest, d, step, lattice):
        """逐步平移校验：每单位一步，查碰撞 + 整体单一连通（与
        game.try_move_ex 的逐步预测语义一致——中间态断开同样拒绝）。"""
        cur = moved
        for _ in range(step):
            nxt = frozenset(_add(p, d) for p in cur)
            if nxt & rest:
                return None
            if not _is_connected(nxt | rest, lattice):
                return None
            cur = nxt
        return cur

    def apply(self, move: Move):
        """应用移动，返回新局面（纯函数，原局不变）。

        move 必须来自本局面的 legal_moves——moved 含不在盘面上的坐标时
        显式抛错（防拿别局的 Move 误放，回放/存档层受益）。
        """
        mv = set(move.moved)
        missing = mv - self.points
        if missing:
            raise ValueError(
                f"移动的选中片含不在盘面上的坐标: {sorted(missing)[:3]}"
                f"（move 须来自同一局面的 legal_moves）")
        delta = tuple(move.step * x for x in move.direction)
        return Board(self.spec, tuple(
            Block(_add(b.point, delta) if b.point in mv else b.point,
                  b.orient, b.group)
            for b in self.blocks))

    def has_legal_move(self, step: int) -> bool:
        return bool(self.legal_moves(step))
