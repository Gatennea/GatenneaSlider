# -*- coding: utf-8 -*-
"""板型注册表 + 内置板型 preset（几何引擎的「谜题定义」入口）。

定义新谜题 = 写一个 BoardSpec（代码基石）并 register_board_type。
GUI 绘制层（P3）将直接消费 spec.cell_polygon 等钩子把板型画出来。

当前 preset：
  · 'square'  方形密铺（Z²、4 邻接、D4、m×n 还原态）——已与现有引擎
    差分对齐；
  · 'cubic'   立方密铺（Z³、6 邻接、48 对称、m×n×d 还原态）——用于
    验证「核心零改动延伸到三维」（用户方向里的三维预留）。

三角 / 米字 preset 属 P2：参数表见 docs/math/异形推广方案_2026-10-16.md
§2（格空间/朝向/方向/缝族/还原态/块数五件套齐全），落地时要处理米字
半整邻接表与 span 锁死判据（seam_clear 钩子已为此预留）。

纪律：未知板型名显式 KeyError，不静默兜底（AGENTS.md §2）。
"""

from .board import Block, Board, BoardSpec, SeamFamily
from .lattice import cubic_lattice, square_lattice

_REGISTRY = {}


def register_board_type(name: str, factory):
    """注册一种板型。factory(**params) -> BoardSpec。

    同名重复注册**显式拒绝**（不静默覆盖——AGENTS.md §2：覆盖会让
    「换了个板型」这种事故无声无息）。
    """
    if not isinstance(name, str) or not name:
        raise ValueError(f"板型名须为非空字符串，收到 {name!r}")
    if not callable(factory):
        raise ValueError(f"板型 {name!r} 的 factory 须可调用")
    if name in _REGISTRY:
        raise ValueError(
            f"板型 {name!r} 已注册，拒绝静默覆盖（如需替换请先移除旧注册）")
    _REGISTRY[name] = factory


def get_board_type(name: str):
    """取已注册板型的 factory；未注册 → KeyError（带已注册清单）。"""
    if name not in _REGISTRY:
        raise KeyError(
            f"未注册的板型: {name!r}（已注册: {sorted(_REGISTRY)}）")
    return _REGISTRY[name]


def board_types():
    """全部已注册板型名（排序）。"""
    return tuple(sorted(_REGISTRY))


def make_board(name: str, **params) -> Board:
    """按板型名造一个还原态局面。"""
    spec = get_board_type(name)(**params)
    return Board(spec, spec.goal_blocks)


# ----------------------------------------------------------------------
# 方形 preset
# ----------------------------------------------------------------------
def square_spec(m: int, n: int, name: str = 'square') -> BoardSpec:
    """方形密铺板型：m×n 实心矩形为还原态。

    参数与既有引擎一致：m 行 n 列；step（等级）是移动参数不进板型。
    """
    for v, label in ((m, 'm'), (n, 'n')):
        if type(v) is not int or v < 1:
            raise ValueError(f"square_spec 的 {label} 须为正整数，收到 {v!r}")
    spec = BoardSpec(
        name=name,
        lattice=square_lattice(),
        directions=((1, 0), (-1, 0), (0, 1), (0, -1)),
        seam_families=(
            SeamFamily('h', (1, 0), ((0, 1), (0, -1))),
            SeamFamily('v', (0, 1), ((1, 0), (-1, 0))),
        ),
        goal_blocks=tuple(Block((i, j)) for i in range(m) for j in range(n)),
    )
    return spec


def square_board(m: int, n: int) -> Board:
    return make_board('square', m=m, n=n)


# ----------------------------------------------------------------------
# 立方 preset（三维演示）
# ----------------------------------------------------------------------
def cubic_spec(m: int, n: int, d: int, name: str = 'cubic') -> BoardSpec:
    """立方密铺板型（三维）：m×n×d 实心长方体为还原态。

    存在意义 = 证明引擎核心（坐标/邻接/缝/移动/规范化/还原）对维度
    无感：3 维只是 dim=3 + 3 条缝族 + 48 对称，核心零行改动。
    """
    for v, label in ((m, 'm'), (n, 'n'), (d, 'd')):
        if type(v) is not int or v < 1:
            raise ValueError(
                f"cubic_spec 的 {label} 须为正整数，收到 {v!r}")
    return BoardSpec(
        name=name,
        lattice=cubic_lattice(),
        directions=((1, 0, 0), (-1, 0, 0),
                    (0, 1, 0), (0, -1, 0),
                    (0, 0, 1), (0, 0, -1)),
        seam_families=(
            SeamFamily('r', (1, 0, 0), ((0, 1, 0), (0, -1, 0),
                                        (0, 0, 1), (0, 0, -1))),
            SeamFamily('c', (0, 1, 0), ((1, 0, 0), (-1, 0, 0),
                                        (0, 0, 1), (0, 0, -1))),
            SeamFamily('d', (0, 0, 1), ((1, 0, 0), (-1, 0, 0),
                                        (0, 1, 0), (0, -1, 0))),
        ),
        goal_blocks=tuple(Block((i, j, k))
                          for i in range(m) for j in range(n)
                          for k in range(d)),
    )


def cubic_board(m: int, n: int, d: int) -> Board:
    return make_board('cubic', m=m, n=n, d=d)


# ----------------------------------------------------------------------
# 内置注册
# ----------------------------------------------------------------------
register_board_type('square', square_spec)
register_board_type('cubic', cubic_spec)
