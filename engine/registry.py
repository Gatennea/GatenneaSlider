# -*- coding: utf-8 -*-
"""板型注册表 + 内置板型 preset（几何引擎的「谜题定义」入口）。

定义新谜题 = 写一个 BoardSpec（代码基石）并 register_board_type。
GUI 绘制层（P3）将直接消费 spec.cell_polygon 等钩子把板型画出来。

当前 preset：
  · 'square'  方形密铺（Z²、4 邻接、D4、m×n 还原态）——已与现有引擎
    差分对齐；
  · 'cubic'   立方密铺（Z³、6 邻接、48 对称、m×n×d 还原态）——用于
    验证「核心零改动延伸到三维」（用户方向里的三维预留）；
  · 'mi'      米字格（半整双晶格 scale=2、N/E/S/W 朝向 5 邻接、四族缝
    带朝向修正的 rank、span 锁死缝、错位态 SAT 重叠）——P2 落地，
    与 game_mi.MiSliderMatrix 差分对拍见测试 L 节。

三角 preset 属 P2 剩余件：参数表见 docs/math/异形推广方案_2026-10-16.md
§2（格空间/方向/缝/还原态/块数五件套齐全），落地时要处理 D3 显式
对称表（lattice.symmetry 当前仅 hyperoctahedral）与还原态 120° 轨道
的 solved_check 口径。

纪律：未知板型名显式 KeyError，不静默兜底（AGENTS.md §2）。
"""

from . import mi_geometry
from .board import Block, Board, BoardSpec, SeamFamily
from .lattice import Lattice, cubic_lattice, square_lattice

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
# 米字 preset（P2：方格四切，半整双晶格 + 朝向）
# ----------------------------------------------------------------------
def mi_lattice() -> Lattice:
    """米字格点：半整双晶格（scale=2、p0≡p1 mod 2）+ 带朝向 5 邻接。"""
    return Lattice(dim=2, scale=2, parity_linear=(1, 1),
                   orient_steps=mi_geometry.MI_ORIENT_STEPS)


def mi_spec(m: int, n: int, name: str = 'mi') -> BoardSpec:
    """米字格板型：m×n 实心矩形为还原态（每格 N/E/S/W 四块俱全）。

    参数与既有引擎一致：m 行 n 列；step（等级）是移动参数不进板型。
    与 game_mi.MiSliderMatrix 的对应关系（引擎单位）：
      · point = (2r, 2c)，合法 ⟺ p0≡p1 (mod 2)；
      · 8 方向 / 4 缝族见 mi_geometry（h/v 的 t = 4L+1、d1/d2 的 t = L+1）；
      · seam_clear = span 锁死（线切进任何块内部即锁死）；
      · overlap = 错位态 SAT（跨 sub-lattice 族的正面积重叠）；
      · 还原判定 = 规范形（联合 D4：平移/换晶格/转置都算还原，与
        game_mi.is_solved 的「实心矩形每格 4 块俱全」等价——L4 节对拍）。
    """
    for v, label in ((m, 'm'), (n, 'n')):
        if type(v) is not int or v < 1:
            raise ValueError(f"mi_spec 的 {label} 须为正整数，收到 {v!r}")
    D = mi_geometry.MI_DIRECTIONS
    return BoardSpec(
        name=name,
        lattice=mi_lattice(),
        directions=tuple(D.values()),
        seam_families=(
            SeamFamily('h', (2, 0), (D['a'], D['d']),
                       rank=mi_geometry.rank_h, line_scale=4),
            SeamFamily('v', (0, 2), (D['w'], D['s']),
                       rank=mi_geometry.rank_v, line_scale=4),
            SeamFamily('d1', (1, -1), (D['q'], D['x']),
                       rank=mi_geometry.rank_d1),
            SeamFamily('d2', (1, 1), (D['e'], D['z']),
                       rank=mi_geometry.rank_d2),
        ),
        orientations=mi_geometry.MI_ORIENTATIONS,
        orient_dirs=tuple(mi_geometry.MI_ORIENT_DIRS[q]
                          for q in mi_geometry.MI_ORIENTATIONS),
        goal_blocks=tuple(Block((2 * r, 2 * c), q)
                          for r in range(m) for c in range(n)
                          for q in mi_geometry.MI_ORIENTATIONS),
        # seam_clear 契约 = True 表示「可用」；seam_locked 是「锁死」，取反接入
        seam_clear=lambda fam, t, board: not mi_geometry.seam_locked(fam, t, board),
        overlap=mi_geometry.has_overlap,
    )


def mi_board(m: int, n: int) -> Board:
    return make_board('mi', m=m, n=n)


# ----------------------------------------------------------------------
# 内置注册
# ----------------------------------------------------------------------
register_board_type('square', square_spec)
register_board_type('cubic', cubic_spec)
register_board_type('mi', mi_spec)
