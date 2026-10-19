# -*- coding: utf-8 -*-
"""格点（Lattice）——几何引擎的坐标层。

坐标模型（整个引擎的地基， deliberately 极简）：
  · 一个「点」= 长度为 ``dim`` 的整数元组；真实几何坐标 = 整数 / ``scale``。
    - 方形 ``Z²``：``scale=1``，点 = (r, c)；
    - 米字半整晶格（P2 预位）：``scale=2``，点 = (2r, 2c)，合法性约束
      ``2r ≡ 2c (mod 2)``（即 p≡q，A/B 双晶格的代数形式）。
  · 邻接 = 点 + ``neighbor_steps`` 里的偏移。方形 4 邻接、三角 3 邻接、
    米字 5 邻接（3 同晶格 + 2 跨晶格）**只是换一张偏移表**，无分支代码。
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


@dataclass(frozen=True)
class Lattice:
    """格点：坐标维度、缩放、合法性约束、邻接表、自同构群。

    字段：
        dim: 坐标维度（2=平面，3=立体；引擎核心按任意维度写）。
        scale: 坐标都是整数，真实坐标 = 整数 / scale（半整晶格填 2）。
        neighbor_steps: 连通性邻接偏移表（整数元组，长度须为 dim）。
        parity_linear: 可选合法性约束——点 p 合法当且仅当
            ``sum(parity_linear[i]*p[i]) % 2 == 0``（米字双晶格填 (1,1)）。
        symmetry: 自同构群生成方式，当前仅 'hyperoctahedral'
            （轴置换 × 符号翻转；对 Z^d 及其半整子格均封闭）。
    """

    dim: int
    scale: int = 1
    neighbor_steps: tuple = ()
    parity_linear: tuple = None
    symmetry: str = 'hyperoctahedral'

    def __post_init__(self):
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
        if self.symmetry not in ('hyperoctahedral',):
            raise ValueError(
                f"不支持的自同构群: {self.symmetry!r}"
                f"（当前仅 'hyperoctahedral'；三角等特殊群待 P2 扩展）")

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
        """
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
