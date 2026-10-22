# -*- coding: utf-8 -*-
"""格点（Lattice）——几何引擎的坐标层。

坐标模型（整个引擎的地基， deliberately 极简）：
  · 一个「点」= 长度为 ``dim`` 的整数元组；真实几何坐标 = 整数 / ``scale``。
    - 方形 ``Z²``：``scale=1``，点 = (r, c)；
    - 米字半整晶格（P2 已落地）：``scale=2``，点 = (2r, 2c)，合法性约束
      ``2r ≡ 2c (mod 2)``（即 p≡q，A/B 双晶格的代数形式）。
  · 邻接 = 点 + ``neighbor_steps`` 里的偏移。方形 4 邻接、三角 3 邻接、
    米字 5 邻接（3 同晶格 + 2 跨晶格）**只是换一张偏移表**，无分支代码。
  · **带朝向的板型**（米字 N/E/S/W）邻接查 ``orient_steps`` 表：偏移
    同时含点位移与朝向位移，按 (point, orient) 联合查——同格心四块
    互为邻或不邻取决于朝向，点级偏移表表达不了。
  · 自同构群 = 规范化（canonicalize）的对称来源。默认「超八面体群」
    （轴置换 × 符号翻转）：2 维即 D4 八变换（与 solver/table_core 的
    canonicalize 同源），3 维即立方体 48 变换。特殊格（如三角密铺的
    点群是 D3 六变换，且数学文档另测得「可达放置」只有恒等 + 转置——
    两者不是一回事）在 P2 用显式对称表覆盖。

设计红线（延续 AGENTS.md §2 / §10）：
  · 纯逻辑，零 pygame，可 headless 测试；
  · 不认识的参数**显式报错**，绝不静默兜底。
"""

from dataclasses import dataclass
from itertools import permutations, product


# 邻接缓存硬上限（条目数；超出即停止缓存，只慢不影响正确性）
_NBR_CACHE_CAP = 1 << 18


@dataclass(frozen=True)
class Lattice:
    """格点：坐标维度、缩放、合法性约束、邻接表、自同构群。

    字段：
        dim: 坐标维度（2=平面，3=立体；引擎核心按任意维度写）。
        scale: 坐标都是整数，真实坐标 = 整数 / scale（半整晶格填 2）。
        neighbor_steps: 连通性邻接偏移表（整数元组，长度须为 dim）。
            点级邻接（方形/立方）；orient_steps 非空时本表退居为
            「无朝向板型」的邻接，两者至少其一非空。
        parity_linear: 可选合法性约束——点 p 合法当且仅当
            ``sum(parity_linear[i]*p[i]) % 2 == 0``（米字双晶格填 (1,1)）。
        symmetry: 自同构群生成方式：
            · 'hyperoctahedral'（默认）：轴置换 × 符号翻转；对 Z^d 及其
              半整子格均封闭（方形 D4 / 立方 48 / 米字双晶格）；
            · 'central_inversion'：仅 恒等 + 中心反演 x→−x；三角密铺的
              真实对称（中心反演交换 up/down 二色，使朝向集闭合）。
              三角的 6 折旋转群不闭合于「朝向=方向向量」机制（60° 旋转
              把单一朝向方向映到 6 个不同晶格方向），故用 C2 作最小合法
              对称——还原判定走 solved_check 钩子（凸包），不依赖本群。
        orient_steps: 可选**带朝向**邻接表：
            ``((orient, ((dpoint, dorient), ...)), ...)``——每块按
            (point, orient) 联合查偏移（米字 5 邻：3 同晶格 + 2 跨晶格，
            同格心四块互为邻或不邻取决于朝向）。非空 = 该板型的连通性
            按联合键走；空 = 点级邻接（orient 恒 '' 的板型）。
            表内 dorient 必须也是表内 orient（封闭才可能连通）。
    """

    dim: int
    scale: int = 1
    neighbor_steps: tuple = ()
    parity_linear: tuple = None
    symmetry: str = 'hyperoctahedral'
    orient_steps: tuple = ()

    def __post_init__(self):
        # 邻接记忆化缓存（不是 dataclass 字段：不参与 eq/repr，纯加速件）。
        # ⚠️ 为什么必须缓存：连通性判定是引擎最热的内环（一次 6×6 打乱
        #    里 neighbors_of 被调 ~900 万次）。邻接表本身是常量，逐次重算
        #    dict(self.orient_steps) + 元组拼接纯属浪费。缓存按 (point,
        #    orient) 索引，条目数天然被盘面规模封住；仍加硬上限防异常板型
        #    无限膨胀（超上限即退化成不缓存，行为不变，只慢）。
        object.__setattr__(self, '_nbr_cache', {})
        object.__setattr__(self, '_orient_table', dict(self.orient_steps))
        if type(self.dim) is not int or self.dim < 1:
            raise ValueError(f"Lattice.dim 须为正整数，收到 {self.dim!r}")
        if type(self.scale) is not int or self.scale < 1:
            raise ValueError(f"Lattice.scale 须为正整数，收到 {self.scale!r}")
        for s in self.neighbor_steps:
            if not isinstance(s, tuple) or len(s) != self.dim:
                raise ValueError(
                    f"neighbor_steps 元素须为长度 {self.dim} 的元组，收到 {s!r}")
            if not all(type(x) is int for x in s):
                raise ValueError(f"neighbor_steps 元素须为整数元组，收到 {s!r}")
        if self.parity_linear is not None:
            if (not isinstance(self.parity_linear, tuple)
                    or len(self.parity_linear) != self.dim
                    or not all(type(x) is int for x in self.parity_linear)):
                raise ValueError(
                    f"parity_linear 须为长度 {self.dim} 的整数元组或 None，"
                    f"收到 {self.parity_linear!r}")
            # 只有「全同系数」（如米字 (1,1)：各分量同奇偶）对超八面体群
            # 封闭；混合系数（如 (1,0)）的约束在轴置换下不保持，绝不当
            # 对称用——显式拒绝，不静默产出错的规范形。
            if len(set(self.parity_linear)) != 1 or self.parity_linear[0] not in (0, 1):
                raise ValueError(
                    f"parity_linear 只支持全同系数（如 (1,1)），收到 "
                    f"{self.parity_linear!r}（混合系数对自同构群不封闭）")
        if self.symmetry not in ('hyperoctahedral', 'central_inversion'):
            raise ValueError(
                f"不支持的自同构群: {self.symmetry!r}"
                f"（当前仅 'hyperoctahedral' / 'central_inversion'）")
        # ---- orient_steps：带朝向邻接表（米字 5 邻）----
        if self.orient_steps:
            if self.neighbor_steps:
                raise ValueError(
                    "orient_steps 与 neighbor_steps 二选一：带朝向板型的"
                    "邻接全走 orient_steps，不允许两张表并存（防歧义）")
            orients = []
            for entry in self.orient_steps:
                if (not isinstance(entry, tuple) or len(entry) != 2
                        or not isinstance(entry[0], str) or not entry[0]
                        or not isinstance(entry[1], tuple) or not entry[1]):
                    raise ValueError(
                        f"orient_steps 元素须为 (orient, 非空偏移元组)，"
                        f"收到 {entry!r}")
                orients.append(entry[0])
            if len(set(orients)) != len(orients):
                raise ValueError(f"orient_steps 的 orient 重复: {orients}")
            oset = set(orients)
            for orient, offs in self.orient_steps:
                for off in offs:
                    if (not isinstance(off, tuple) or len(off) != 2
                            or not isinstance(off[0], tuple)
                            or len(off[0]) != self.dim
                            or not all(type(x) is int for x in off[0])
                            or off[1] not in oset):
                        raise ValueError(
                            f"orient {orient!r} 的偏移 {off!r} 非法："
                            f"须为 (长度 {self.dim} 的整数点位移, 表内 orient)")

    # ------------------------------------------------------------------
    # 坐标合法性
    # ------------------------------------------------------------------
    def valid(self, point) -> bool:
        """点是否落在格上（维度 + 整数 + 奇偶约束）。"""
        if not isinstance(point, tuple) or len(point) != self.dim:
            return False
        if not all(isinstance(x, int) for x in point):
            return False
        if self.parity_linear is not None:
            acc = 0
            for c, x in zip(self.parity_linear, point):
                acc += c * x
            if acc % 2 != 0:
                return False
        return True

    # ------------------------------------------------------------------
    # 邻接（连通性判据的唯一来源）
    # ------------------------------------------------------------------
    def neighbors(self, point):
        """点的全部邻点（在格内的邻居_step 平移）。"""
        for s in self.neighbor_steps:
            q = tuple(point[i] + s[i] for i in range(self.dim))
            if self.valid(q):
                yield q

    def neighbors_of(self, point, orient=''):
        """(point, orient) 的全部邻接块 → **元组** ((point', orient'), ...)。

        带朝向板型（orient_steps 非空）按联合键查偏移表——同格心四块
        互为邻或不邻取决于朝向（米字 N 与 S 只共顶点、不共边），点级
        偏移表表达不了这种关系。表路径**不做 valid 复核**：表由板型
        定义者保证封闭（米字表从合法点只会走到合法点），复核只会掩盖
        表错误；下游按键集合成员判定，坏键自然落空。

        无朝向板型（方形/立方）走点级邻接，orient 原样带回（恒 ''）。

        ⚠️ 返回**元组不是生成器**（记忆化的代价，见 __post_init__ 的缓存
        说明）：调用方一律 ``for q in lat.neighbors_of(...)``，语义不变；
        想拿生成器自行 ``iter(...)``。
        """
        cache = self._nbr_cache
        key = (point, orient)
        hit = cache.get(key)
        if hit is not None:
            return hit
        if self._orient_table:
            out = tuple((tuple(point[i] + dpoint[i]
                               for i in range(self.dim)), dorient)
                        for dpoint, dorient in self._orient_table.get(orient, ()))
        else:
            out = tuple((q, orient) for q in self.neighbors(point))
        if len(cache) < _NBR_CACHE_CAP:
            cache[key] = out
        return out

    # ------------------------------------------------------------------
    # 自同构群（规范化的对称来源）
    # ------------------------------------------------------------------
    def iter_symmetries(self):
        """产出全部自同构（point -> point 的纯函数）。

        超八面体群 = 轴置换 × 符号翻转：
          · dim=2 → 8 个（D4：4 旋转 × 翻面），与 table_core 的八变换一致；
          · dim=3 → 48 个（立方体全对称，含反射）。
        半整子格（parity_linear=(1,1)）对该群封闭（P+Q 的奇偶在置换与
        取反下不变），故米字晶格可直接复用本群。

        'central_inversion' = 仅 恒等 + 中心反演（x→−x）：三角密铺的真实
        对称，且中心反演交换 up/down 二色，使三角朝向集闭合（见 symmetry
        字段 docstring）。还原判定走 solved_check 钩子，不依赖本群大小。
        """
        if self.symmetry == 'central_inversion':
            def _id(p):
                return p

            def _neg(p):
                return tuple(-x for x in p)

            yield _id
            yield _neg
            return
        for perm in permutations(range(self.dim)):
            for signs in product((1, -1), repeat=self.dim):
                def sym(p, perm=perm, signs=signs):
                    return tuple(signs[i] * p[perm[i]]
                                 for i in range(self.dim))
                yield sym


def square_lattice() -> Lattice:
    """方形密铺：Z²、4 邻接、无奇偶约束。"""
    return Lattice(dim=2, scale=1,
                   neighbor_steps=((1, 0), (-1, 0), (0, 1), (0, -1)))


def cubic_lattice() -> Lattice:
    """立方密铺（三维演示用）：Z³、6 邻接。"""
    return Lattice(dim=3, scale=1,
                   neighbor_steps=((1, 0, 0), (-1, 0, 0),
                                   (0, 1, 0), (0, -1, 0),
                                   (0, 0, 1), (0, 0, -1)))
