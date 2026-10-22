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

**块的身份 = (point, orient) 联合键**（P2 硬骨 7）：米字「同格心 4 块
（N/E/S/W）」要求局面唯一性键是联合键而非 point——方形 Ω={∅} 时退化为
点键，(point, '') 与 point 一一对应，既有差分行为不变。

与现有三引擎的关系：
  · 方形板型已与 game.SliderMatrix 差分对齐（test/_test_geometry_engine.py：
    移动结果集合 / 规范形 / 还原判定逐项全等）；
  · 米字板型（P2）已落地：半整晶格（scale=2 + 奇偶）、带朝向 5 邻接、
    四族缝的朝向相关 rank、span 锁死缝（seam_clear）、错位态几何重叠
    （overlap 钩子，SAT）；与 game_mi.MiSliderMatrix 差分对拍见测试 L 节；
  · 三角板型属 P2 剩余件（D3 对称表 + up/down 朝向 + 还原态轨道口径，
    solved_check 钩子就是为它预留的）；
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


def _connected_components(keys, spec):
    """按 spec 邻接把**块键** (point, orient) 集合拆成连通分量。

    邻接的唯一来源 = spec.lattice.neighbors_of：无朝向板型走点级偏移
    （方形/立方），带朝向板型按联合键查 orient_steps 表（米字 5 邻）。
    """
    remaining = set(keys)
    lat = spec.lattice
    comps = []
    while remaining:
        seed = remaining.pop()
        comp = {seed}
        stack = [seed]
        while stack:
            p, o = stack.pop()
            for q in lat.neighbors_of(p, o):
                if q in remaining:
                    remaining.discard(q)
                    comp.add(q)
                    stack.append(q)
        comps.append(frozenset(comp))
    return comps


def _is_connected(keys, spec) -> bool:
    """键集合是否单一连通（空集视为连通，与既有引擎口径一致）。"""
    if not keys:
        return True
    return len(_connected_components(keys, spec)) == 1


def _group_closure(comp, block_map):
    """捆绑扩展：分量所在的捆绑组整组拖入（组是刚体，缝切不开组）。

    与 game.SliderMatrix.opt 的捆绑扩展同语义：组员在盘面远处也会被
    拉扯进选中片，碰撞由移动校验拒绝（捆绑魔方「转不动」体感）。
    """
    gids = {block_map[k].group for k in comp if block_map[k].group}
    if not gids:
        return frozenset(comp)
    out = set(comp)
    changed = True
    while changed:  # 不动点迭代（组 id 唯一标识一组，实际一轮即收敛）
        changed = False
        for k, b in block_map.items():
            if b.group in gids and k not in out:
                out.add(k)
                changed = True
    return frozenset(out)


def _orient_perm(spec, sym):
    """自同构 sym 诱导的朝向置换 {orient: orient'}（P2 硬骨 8）。

    机制：每个朝向 orient 在 spec.orient_dirs 里配一个方向向量（点坐标
    单位，如米字 N=(−1,0)）；sym 是点空间的线性映射，把它作用到方向
    向量上，落到哪个朝向的方向，该朝向就被映射到它。方形 Ω={∅} 时
    置换为恒等（orient 恒 ''）。

    sym 把某朝向的方向向量映到朝向集之外 = 该对称对这个板型不合法
    （朝向集没跟着对称闭包）——显式抛错，不静默产出错规范形。
    """
    if not spec.orientations:
        return {'': ''}
    dir_to_orient = dict(zip(spec.orient_dirs, spec.orientations))
    out = {}
    for o, d in zip(spec.orientations, spec.orient_dirs):
        o2 = dir_to_orient.get(sym(d))
        if o2 is None:
            raise ValueError(
                f"板型 {spec.name!r} 的自同构把朝向 {o!r} 的方向 {d} 映到 "
                f"{sym(d)}，不在朝向表 {spec.orientations} 内——朝向集对"
                f"自同构群不封闭，规范形会出错")
        out[o] = o2
    return out


# ----------------------------------------------------------------------
# 数据类
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Block:
    """一个滑块块：格点 + 朝向标签 + 捆绑组号。

    · point: 整数坐标元组（长度 = lattice.dim；半整晶格见 Lattice.scale，
      米字 point = (2r, 2c)）；
    · orient: 朝向标签（方形为 ''；三角 'up'/'down'；米字 'N/E/S/W'）。
      平移不改变朝向；
    · group: 捆绑组号（0 = 未捆绑；自由捆绑模式，docs/spec/bandaged_mode.md）。

    块的身份 = (point, orient) 联合键：米字同格心 4 块靠朝向区分
    （P2 硬骨 7）；方形退化为点键。
    """

    point: tuple
    orient: str = ''
    group: int = 0


@dataclass(frozen=True)
class SeamFamily:
    """一条缝族：格空间被一族平行超平面切割。

    · name: 族名（方形 'h'/'v'；三角 'h'/'p'/'n'；米字 'h'/'v'/'d1'/'d2'；
      三维 'r'/'c'/'d'——词汇表随板型注册，不再有三处硬编码表）；
    · coeffs: **点部**线性泛函系数。两个用途：① rank 钩子为 None 时
      缝实例 t 的超平面 = {p : f(p) = t}；② 平行性校验——该族允许的
      平移方向 d 须满足 f(d) = 0（与 orient 无关的点部判据）；
    · parallel: 与该缝平行的单位方向（f(d)=0），即这条缝允许的平移方向；
    · rank: 可选钩子 (point, orient) -> int，**覆盖**点部泛函给出每块
      的缝坐标（side 判据 = rank < t）。米字四族全带朝向修正（h/v 的
      N/W 扣半格、d1/d2 按朝向分侧），且 h/v 的线分辨率是 4× 几何线
      （错位态会出现 ¼ 线）；None = 纯线性泛函（方形/立方）。

    ⚠️ 朝向相关 side 的实现落点：legal_moves / locked_seams 一律走
    ``rank_of(point, orient)``，钩子非空时**不再看 coeffs 算 rank**。
    · line_scale: 引擎缝号 t 与**外部线号** L 的换算比例，
      ``t = line_scale · L + 1``（compat 桥用来对齐 history 动作 dict 的
      gap_line）。方形/立方 = 1；米字 h/v = 4（错位态有 ¼ 线，点部整数
      模型必须 4× 线分辨率）；米字 d1/d2 = 1（game rank 本就是 2× 线）。
      该比例同时刻画 rank 单位：rank = line_scale × 外部 rank。
    """

    name: str
    coeffs: tuple
    parallel: tuple
    rank: object = None
    line_scale: int = 1

    def __post_init__(self):
        if self.rank is not None and not callable(self.rank):
            raise TypeError(
                f"缝族 {self.name!r} 的 rank 须可调用或 None，"
                f"收到 {type(self.rank).__name__}")
        if type(self.line_scale) is not int or self.line_scale < 1:
            raise ValueError(
                f"缝族 {self.name!r} 的 line_scale 须为正整数，"
                f"收到 {self.line_scale!r}")

    def rank_of(self, point, orient='') -> int:
        """块 (point, orient) 在该族缝坐标下的 rank（side 判据）。"""
        if self.rank is not None:
            return self.rank(point, orient)
        return _dot(self.coeffs, point)


@dataclass(frozen=True)
class Move:
    """一个合法移动（不可变值对象，可哈希、回放、进存档）。

    · t 与既有引擎「行号」的关系随板型而定（方形 t = line + 1；米字
      h/v 是 4× 线号 +1、d1/d2 是 line + 1）——P1 的映射层按板型吸收，
      见 engine/compat.py；
    · moved: 被移动的**块键** (point, orient) 集合（排序元组）。米字
      同格心 4 块靠朝向区分，选中片必须是键集而非点集（P2 硬骨 7）；
      方形退化为 ((r,c), '') 键，compat 层剥朝向还原点。
    """

    family: str
    t: int
    side: int                 # -1 / +1（被移动分量在缝的哪侧）
    direction: tuple          # 单位方向
    step: int                 # 单位步数（游戏的「等级」）
    moved: tuple              # 被移动的块键集合（排序元组）


@dataclass(frozen=True)
class BoardSpec:
    """板型：定义一种谜题所需的全部数据（「代码作为基石」的载体）。

    字段：
        name: 板型名（注册表键）。
        lattice: 格点（坐标/邻接/对称群）。
        directions: 方向生成元 D（单位步偏移；每步须平行于至少一条缝族）。
        seam_families: 缝族 Σ。
        orientations: 合法朝向标签（() = 无朝向，如方形）。非空时
            lattice.orient_steps 必须给出同集朝向的邻接表，且
            orient_dirs 必须等长配套。
        goal_blocks: 还原态 S₀（Block 元组）。
        orient_dirs: 每个朝向的方向向量（点坐标单位，与 orientations
            等长）——对称群作用下朝向如何置换由它诱导（硬骨 8）。
        seam_clear: 可选钩子 (family, t, board) -> bool。返回 False =
            该缝被「锁死」（几何上切不动）——米字 span 判据（线严格落进
            某块跨度内部 = 切块）就是它；None = 无锁死。
        solved_check: 可选钩子 (board) -> bool，覆盖默认的「与还原态
            规范化相等」（三角的还原态轨道判定属此类，P2 剩余件）。
        overlap: 可选钩子 (moved_keys, rest_keys) -> bool，返回 True =
            两簇块有几何重叠（含同键）。默认 None = 键相交即碰撞
            （方形/立方够用）；米字错位态下不同键的两块可能正面积
            重叠（跨 sub-lattice 族），必须挂 SAT 判定（P2）。
        cell_polygon: 可选钩子 (point, orient) -> 多边形顶点元组。
            纯几何、零 pygame——GUI 绘制层据此画格子（「GUI 上绘制」
            的数据接口；方形给单位方格，米字给直角等腰三角）。

    ⚠️ 三角板型尚未落地：它需要 D3 显式对称表（lattice.symmetry 当前
    仅 hyperoctahedral）与还原态轨道 solved_check，属 P2 剩余件。
    """

    name: str
    lattice: object               # Lattice
    directions: tuple
    seam_families: tuple
    orientations: tuple = ()
    goal_blocks: tuple = ()
    orient_dirs: tuple = ()
    seam_clear: object = None
    solved_check: object = None
    overlap: object = None
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
        for hook_name in ('seam_clear', 'solved_check', 'overlap',
                          'cell_polygon'):
            hook = getattr(self, hook_name)
            if hook is not None and not callable(hook):
                raise TypeError(
                    f"板型 {self.name!r} 的 {hook_name} 须可调用或 None，"
                    f"收到 {type(hook).__name__}")
        lat = self.lattice
        dim = lat.dim
        # 方向表：整数元组、至少一个非零、长度=dim。
        # （不限制分量 ∈ {-1,0,1}：米字 scale=2 的横竖一步就是 ±2——
        #  单位性由「一步 = 一个字母移动」的语义保证，不由分量幅值保证。）
        for d in self.directions:
            if (not isinstance(d, tuple) or len(d) != dim
                    or not all(isinstance(x, int) and not isinstance(x, bool)
                               for x in d)
                    or not any(d)):
                raise ValueError(
                    f"板型 {self.name!r} 的方向 {d!r} 非法："
                    f"须为长度 {dim}、至少一个非零分量的整数元组")
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
        # ---- 朝向三件套：orientations / orient_dirs / lattice.orient_steps
        if self.orientations:
            if not isinstance(self.orient_dirs, tuple) or \
                    len(self.orient_dirs) != len(self.orientations):
                raise ValueError(
                    f"板型 {self.name!r} 的 orient_dirs 须与 orientations "
                    f"等长（{len(self.orientations)}），收到 {self.orient_dirs!r}")
            for o, d in zip(self.orientations, self.orient_dirs):
                if not isinstance(o, str) or not o:
                    raise ValueError(f"朝向标签须为非空字符串，收到 {o!r}")
                if (not isinstance(d, tuple) or len(d) != dim
                        or not all(isinstance(x, int) for x in d) or not any(d)):
                    raise ValueError(
                        f"朝向 {o!r} 的方向向量 {d!r} 非法：须为长度 {dim}、"
                        f"至少一个非零分量的整数元组")
            table_orients = {o for o, _ in lat.orient_steps}
            if table_orients != set(self.orientations):
                raise ValueError(
                    f"板型 {self.name!r} 的 lattice.orient_steps 朝向集 "
                    f"{sorted(table_orients)} 与 orientations "
                    f"{sorted(self.orientations)} 不一致")
            # 朝向集必须对自同构群封闭（否则 canonical 的联合变换会漏/
            # 错映射朝向）——现在就穷举验证，不留给运行时炸。
            for sym in lat.iter_symmetries():
                _orient_perm(self, sym)
        elif lat.orient_steps:
            raise ValueError(
                f"板型 {self.name!r} 未声明朝向，lattice 却带了 orient_steps"
                f" 邻接表（矛盾）")
        elif self.orient_dirs:
            raise ValueError(
                f"板型 {self.name!r} 未声明朝向，却给了 orient_dirs")
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
        # 还原态自检：块数 > 0、(point,orient) 不重复、点在格上、单一连通
        if self.goal_blocks:
            pts = [(b.point, b.orient) for b in self.goal_blocks]
            if len(set(pts)) != len(pts):
                raise ValueError(f"板型 {self.name!r} 还原态存在重复块")
            for p in pts:
                if not lat.valid(p[0]):
                    raise ValueError(
                        f"板型 {self.name!r} 还原态坐标 {p[0]!r} 不在格上")
            if not _is_connected(set(pts), self):
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

    块的身份 = (point, orient) 联合键（P2 硬骨 7）：米字同格心 4 块
    靠朝向区分；方形退化为点键，行为与 P0 逐项一致。
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
            k = (b.point, b.orient)
            if k in seen:
                raise ValueError(f"局面存在重复块 (point, orient): {k!r}")
            seen.add(k)
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
        """从点集造局面（groups: point -> 组号，可选；orient 统一）。

        无朝向板型（方形/立方）的入口；米字等带朝向板型用 from_keys。
        """
        groups = groups or {}
        return cls(spec, tuple(Block(tuple(p), orient, groups.get(tuple(p), 0))
                               for p in points))

    @classmethod
    def from_keys(cls, spec, keys, groups=None):
        """从块键 (point, orient) 集合造局面（groups: 键 -> 组号，可选）。"""
        groups = groups or {}
        return cls(spec, tuple(Block(tuple(p), o, groups.get((tuple(p), o), 0))
                               for p, o in keys))

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    @property
    def points(self):
        return frozenset(b.point for b in self.blocks)

    @property
    def keys(self):
        """块键 (point, orient) 集合（局面身份的真正载体）。"""
        return frozenset((b.point, b.orient) for b in self.blocks)

    @property
    def block_map(self):
        return {(b.point, b.orient): b for b in self.blocks}

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

        **带朝向板型走 (point, orient) 联合变换**（P2 硬骨 8）：每个
        自同构除搬点之外，还按 orient_dirs 诱导朝向置换（对称群含朝向
        置换）——米字合法移动依赖 orient，只规范化点集会让「旋转后的
        同一局面」漏等价。无朝向板型（方形/立方）剥掉恒等的 orient，
        规范形与 P0 逐项同形（点元组序列）。
        """
        pts = [(b.point, b.orient) for b in self.blocks]
        if not pts:
            return ()
        spec = self.spec
        dim = spec.lattice.dim
        with_orient = bool(spec.orientations)
        best = None
        for sym in spec.lattice.iter_symmetries():
            opmap = _orient_perm(spec, sym)
            tp = [(sym(p), opmap[o]) for p, o in pts]
            m = tuple(min(p[i] for p, _ in tp) for i in range(dim))
            if with_orient:
                norm = tuple(sorted(
                    (tuple(p[i] - m[i] for i in range(dim)), o)
                    for p, o in tp))
            else:
                norm = tuple(sorted(
                    tuple(p[i] - m[i] for i in range(dim)) for p, _ in tp))
            if best is None or norm < best:
                best = norm
        return best

    def is_solved(self):
        """是否还原。默认 = 与还原态规范化相等（旋转/翻面都算）；
        板型可挂 solved_check 钩子覆盖（三角的还原态轨道，P2 剩余件）。"""
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

        侧判定走 ``SeamFamily.rank_of(point, orient)``（P2 硬骨 9：
        米字四族的缝坐标都带朝向修正，点部线性泛函只够方形/立方）。
        锁死缝走板型的 seam_clear 钩子（米字 span 判据的落点）。
        """
        if type(step) is not int or step < 1:
            raise ValueError(f"step 须为 ≥ 1 的整数，收到 {step!r}")
        spec = self.spec
        keys = self.keys
        if not keys:
            return ()
        bmap = self.block_map
        out = []
        # 同带去重：米字 h/v 的 4× 线分辨率下，同两条块边之间可能有多条
        # ¼ 线（如 L=0 / 0.25 / 0.5），它们划出**同一个分区**、同一个选中
        # 片——只留最小 t 的代表，否则合法移动列表里同一次拖动会重复出现
        # （方形/立方线号与分区一一对应，去重对它们是恒等变换）。
        seen = set()
        for fam in spec.seam_families:
            vals = {k: fam.rank_of(k[0], k[1]) for k in keys}
            lo, hi = min(vals.values()), max(vals.values())
            # t ∈ (lo, hi]：下侧必含 rank=lo 的块、上侧必含 rank=hi 的块，
            # 两端非空由取值范围保证（无需再查空侧）。
            for t in range(lo + 1, hi + 1):
                # 锁死缝（米字 span 判据的落点）：几何上切不动
                if spec.seam_clear is not None and not spec.seam_clear(fam, t, self):
                    continue
                side_lo = frozenset(k for k in keys if vals[k] < t)
                side_hi = keys - side_lo
                for side, side_set in ((-1, side_lo), (1, side_hi)):
                    for comp in _connected_components(side_set, spec):
                        moved = _group_closure(comp, bmap)
                        if len(moved) == len(keys):
                            continue  # 全员选中 = 整体平移，拒绝
                        rest = keys - moved
                        moved_key = tuple(sorted(moved))
                        for d in fam.parallel:
                            if not self._slide_ok(moved, rest, d, step, spec):
                                continue
                            ident = (fam.name, side, d, step, moved_key)
                            if ident in seen:
                                continue
                            seen.add(ident)
                            out.append(Move(fam.name, t, side, d, step,
                                            moved_key))
        return tuple(out)

    @staticmethod
    def _slide_ok(moved, rest, d, step, spec):
        """逐步平移校验：每单位一步，查碰撞 + 整体单一连通（与
        game.try_move_ex 的逐步预测语义一致——中间态断开同样拒绝）。

        碰撞判据：板型挂了 overlap 钩子就走几何判定（米字错位态下
        不同键的两块可能正面积重叠，键相交只是其特例）；否则键相交。
        """
        cur = moved
        overlap = spec.overlap
        for _ in range(step):
            nxt = frozenset((_add(p, d), o) for p, o in cur)
            if overlap is not None:
                if overlap(nxt, rest):
                    return None
            elif nxt & rest:
                return None
            if not _is_connected(nxt | rest, spec):
                return None
            cur = nxt
        return cur

    def apply(self, move: Move):
        """应用移动，返回新局面（纯函数，原局不变）。

        move 必须来自本局面的 legal_moves——moved 含不在盘面上的键时
        显式抛错（防拿别局的 Move 误放，回放/存档层受益）。
        """
        mv = set(move.moved)
        missing = mv - self.keys
        if missing:
            raise ValueError(
                f"移动的选中片含不在盘面上的块键: {sorted(missing)[:3]}"
                f"（move 须来自同一局面的 legal_moves）")
        delta = tuple(move.step * x for x in move.direction)
        return Board(self.spec, tuple(
            Block(_add(b.point, delta) if (b.point, b.orient) in mv else b.point,
                  b.orient, b.group)
            for b in self.blocks))

    def has_legal_move(self, step: int) -> bool:
        return bool(self.legal_moves(step))

    # ------------------------------------------------------------------
    # 单点平移（不枚举全空间）
    # ------------------------------------------------------------------
    def can_slide(self, moved, direction, step, fam=None, t=None):
        """**只校验这一次**平移能否成立（合法回最终选中片，否则 None）。

        与 legal_moves 的判据逐项一致——非空选中片、不能全员选中（整体
        平移无意义）、锁死缝（spec.seam_clear 钩子）、逐步碰撞、逐步单一
        连通——但**不枚举整棵合法移动树**。

        ⚠️ 为什么必须有这条通道：try_move / 打乱 / 拖动这类路径是「选中片
        已知、只问这一步行不行」，用 ``move in legal_moves(step)`` 判成员
        等于每次都把全空间算一遍。实测 6×6 s2 打乱 2777ms，其中 98% 烧在
        legal_moves 的枚举上（288 次调用 / 33.4s）；改走这里后同参数
        ≈40ms，与旧引擎同量级。枚举器留给求解器与 has_legal_move。

        缝族/缝号（fam, t）给了才查锁死缝——opt 那条路径已经保证选中片
        在同一侧，锁死缝是唯一还需要补的几何判据。
        """
        moved = frozenset(moved)
        if not moved:
            return None
        keys = self.keys
        if not moved <= keys:
            return None
        if len(moved) == len(keys):
            return None                      # 全员选中 = 整体平移
        if fam is not None and t is not None and self.spec.seam_clear is not None:
            if not self.spec.seam_clear(fam, t, self):
                return None
        rest = keys - moved
        return self._slide_ok(moved, rest, direction, step, self.spec)

    def move_ok(self, move) -> bool:
        """Move 是否是本局面的合法移动——**完整 legal_moves 语义**，
        但只算这一条缝，不枚举整棵树。

        比 can_slide 多一道「选中片必须是缝某一侧的某个连通分量的捆绑
        闭包」：can_slide 只管「推得动、不断开」，允许任意子集（这正是
        try_move 想要的——连按方向键时选中片不会因贴到邻块而被撑大，
        与旧引擎逐项一致）；而回放 / 存档校验要的是 legal_moves 那种
        「这一片确实是一次合法点击的产物」，故走本函数。

        只枚举本族本缝的 2 个侧面（每侧一次连通分量拆分），其余判据
        （锁死缝、逐步碰撞、逐步连通、非全员）与 legal_moves 逐项一致。
        """
        fam = next((f for f in self.spec.seam_families
                    if f.name == move.family), None)
        if fam is None or move.direction not in fam.parallel:
            return False
        if type(move.step) is not int or move.step < 1:
            return False
        keys = self.keys
        moved = frozenset(move.moved)
        if not moved or not moved <= keys or len(moved) == len(keys):
            return False
        if self.spec.seam_clear is not None and \
                not self.spec.seam_clear(fam, move.t, self):
            return False
        # 选中片整片落在缝的一侧（与 compat.action_to_move 同判据）
        vals = {fam.rank_of(p, o) for p, o in moved}
        if all(v < move.t for v in vals):
            side = -1
        elif all(v >= move.t for v in vals):
            side = 1
        else:
            return False
        if side != move.side:
            return False
        side_set = frozenset(k for k in keys
                             if (fam.rank_of(k[0], k[1]) < move.t)
                             == (side == -1))
        bmap = self.block_map
        for comp in _connected_components(side_set, self.spec):
            if _group_closure(comp, bmap) == moved:
                return self.can_slide(moved, move.direction, move.step) is not None
        return False

    def slide(self, moved, direction, step, fam=None, t=None):
        """过校验并应用：合法回新局面，非法回 None（can_slide + 落位）。"""
        final = self.can_slide(moved, direction, step, fam, t)
        if final is None:
            return None
        delta = tuple(step * x for x in direction)
        mv = frozenset(moved)
        return Board(self.spec, tuple(
            Block(_add(b.point, delta) if (b.point, b.orient) in mv else b.point,
                  b.orient, b.group)
            for b in self.blocks))
