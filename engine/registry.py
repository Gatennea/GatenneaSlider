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
  · 'tri'     三角密铺（斜坐标 Z²、up/down 朝向 3 邻接、3 缝族 h/p/n、
    中心反演对称 + 还原态 120° 轨道 solved_check）——P2 落地，与
    game_triangle.TriangleSliderMatrix 差分对拍见测试 M 节。
  · 'shatter' 碎三角（双形状非正则密铺：红=边长1正三角 / 绿=30-30-120
    等腰；48 块 = 4 单元；显式邻接 Lattice + 几何 SAT overlap + 精确拼合
    solved_check；6 缝族全开）。首个「显式邻接」泛化的真实受益板型——
    边邻接图不规则（18 种邻接签名），固定偏移表表达不了。
  · 'shatter_lattice' 碎三角·晶格（同几何，仅 3 条晶格缝，绿底缝关闭）。

三角 preset 的还原态 120° 旋转轨道走 solved_check 钩子（凸包）；其 6 折
旋转群不闭合于「朝向=方向向量」机制，故对称群用最小合法的 C2（中心反演），
还原判据不依赖本群大小（§4.2 真问题用钩子规避）。

纪律：未知板型名显式 KeyError，不静默兜底（AGENTS.md §2）。
"""

from . import mi_geometry
from . import tri_geometry
from .board import Block, Board, BoardSpec, SeamFamily
from .lattice import Lattice, cubic_lattice, square_lattice
from .shatter_geometry import shatter_spec


# ----------------------------------------------------------------------
# cell_polygon：把「每个形态长什么样」写成数据（P3b 通用渲染的数据源头）
#
# 这三个函数是解释器路线的第一步：GUI 不该知道 square/tri/mi 各自怎么画，
# 只该调用 spec.cell_polygon(point, orient) 拿到多边形。纯绘制用途，
# 引擎逻辑（移动/邻接/连通）完全不看它们，故补它们无回归风险。
#   · square：无现成函数，自写单位方格；
#   · tri：复用 tri_geometry.tri_vertices 的斜坐标，**必须**乘以单位三角基
#     转成平面（斜坐标直接当笛卡尔会铺成平行四边形网，不是正三角）；
#   · mi：mi_geometry.mi_vertices 已是平面 (x=列, y=行)、且与 game_mi 顶点
#     公式同源（×2），直接透传。
# ----------------------------------------------------------------------
def _square_cell_polygon(point, orient=''):
    """方形块的平面多边形：单位方格（point=(行, 列) → 平面 x=列、y=行）。"""
    r, c = point
    return ((c, r), (c + 1, r), (c + 1, r + 1), (c, r + 1))


# 单位正三角的斜坐标基：斜坐标 (i, j) 的平面位置 = i·e1 + j·e2，
# e1·e2 = cos 60°，故三点张成正三角形而非平行四边形。
_TRI_PLANE_BASIS = ((1.0, 0.0), (0.5, 0.8660254037844386))


def _tri_cell_polygon(point, orient=''):
    """三角块的平面多边形：tri_vertices 的斜坐标乘单位三角基转真平面坐标。"""
    i, j = point
    e1, e2 = _TRI_PLANE_BASIS
    return tuple((a * e1[0] + b * e2[0], a * e1[1] + b * e2[1])
                 for (a, b) in tri_geometry.tri_vertices(i, j, orient))


def _mi_cell_polygon(point, orient=''):
    """米字块的平面多边形：mi_vertices 已是平面 (x=列, y=行)，直接透传。"""
    return mi_geometry.mi_vertices(point, orient)

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
        cell_polygon=_square_cell_polygon,
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
        cell_polygon=_mi_cell_polygon,
    )


def mi_board(m: int, n: int) -> Board:
    return make_board('mi', m=m, n=n)


# ----------------------------------------------------------------------
# 三角 preset（P2：正三角形密铺，斜坐标 Z² + up/down 朝向）
# ----------------------------------------------------------------------
def tri_lattice() -> Lattice:
    """三角密铺格点：斜坐标 Z²（scale=1，全整数合法）、up/down 三邻、
    中心反演对称（交换二色，使朝向集闭合；还原走 solved_check 钩子）。
    """
    return Lattice(dim=2, scale=1,
                   orient_steps=tri_geometry.TRI_ORIENT_STEPS,
                   symmetry='central_inversion')


def _tri_goal_blocks(k: int) -> tuple:
    """边长 k 实心正三角形的还原态块集合（▲: i+j≤k-1；▼: i+j≤k-2）。

    块数 = k² 恰为实心正三角形面积（game_triangle 同口径）。
    """
    blocks = []
    for i in range(k):
        for j in range(k - i):
            blocks.append(Block((i, j), 'up'))
    for i in range(k - 1):
        for j in range(k - 1 - i):
            blocks.append(Block((i, j), 'down'))
    return tuple(blocks)


def tri_spec(k: int, name: str = 'tri', default_shape: bool = True) -> BoardSpec:
    """三角密铺板型：边长 k 实心正三角形为还原态（默认）；可传
    default_shape=False + 自定义 goal_blocks 作设计态（精确比目标）。

    与 game_triangle.TriangleSliderMatrix 的对应关系（引擎单位）：
      · point = (i, j) 斜坐标；orient ∈ {up, down}；合法点 = 全整数；
      · 6 方向 / 3 缝族（h/p 取向无关走 coeffs、n 带朝向修正钩子）；
      · seam_clear = None（三角无缝被锁死，与 game 一致）；
      · overlap = None（三角块无半格偏移，键相交即碰撞，同方形）；
      · 还原判定 = solved_check 钩子（凸包轨道：任意平移 / 120°/240°
        旋转等效），不依赖本群（三角 6 折旋转不闭合于朝向方向机制）。
    """
    if type(k) is not int or k < 2:
        raise ValueError(f"tri_spec 的 k 须为 ≥ 2 的整数，收到 {k!r}")

    def _solved(board: Board) -> bool:
        """还原判定（与 game_triangle.is_solved 逐字同标准）。

        默认还原态（default_shape=True）= 边长 k 实心正三角形，位置/朝向
        不限（平移 + 120°/240° 旋转等效）→ 走凸包几何判据；自定义设计态
        （default_shape=False）= 位置集合与还原态逐块相同即还原。
        """
        goal_keys = {(b.point, b.orient) for b in board.spec.goal_blocks}
        keys = board.keys
        if len(keys) != len(goal_keys):
            return False
        if keys == goal_keys:
            return True
        if not default_shape:
            return False
        if len(keys) != k * k:
            return False
        verts = set()
        for ij, up in keys:
            verts.update(tri_geometry.tri_vertices(ij[0], ij[1], up))
        hull = tri_geometry.convex_hull(verts)
        if len(hull) != 3:
            return False
        target = k * k
        for t in range(3):
            da = hull[(t + 1) % 3][0] - hull[t][0]
            db = hull[(t + 1) % 3][1] - hull[t][1]
            if da * da + da * db + db * db != target:
                return False
        # cells_inside_triangle 返回 (i, j, up_bool)，转成引擎键 ((i,j), orient) 再比
        inside = tri_geometry.cells_inside_triangle(hull)
        inside_keys = {((i, j), 'up' if up else 'down')
                       for (i, j, up) in inside}
        return inside_keys == keys

    D = tri_geometry.TRI_DIRECTIONS
    return BoardSpec(
        name=name,
        lattice=tri_lattice(),
        directions=tuple(D.values()),
        seam_families=(
            SeamFamily('h', (0, 1), (D['a'], D['d'])),
            SeamFamily('p', (1, 0), (D['e'], D['z'])),
            SeamFamily('n', (1, 1), (D['w'], D['x']),
                       rank=tri_geometry.rank_n),
        ),
        orientations=tri_geometry.TRI_ORIENTATIONS,
        orient_dirs=tuple(tri_geometry.TRI_ORIENT_DIRS[o]
                          for o in tri_geometry.TRI_ORIENTATIONS),
        goal_blocks=_tri_goal_blocks(k),
        solved_check=_solved,
        cell_polygon=_tri_cell_polygon,
    )


def tri_board(k: int) -> Board:
    return make_board('tri', k=k)


# ----------------------------------------------------------------------
# 内置注册
# ----------------------------------------------------------------------
register_board_type('square', square_spec)
register_board_type('cubic', cubic_spec)
register_board_type('mi', mi_spec)
register_board_type('tri', tri_spec)
# 碎三角（双形状非正则密铺，显式邻接板型的首个真实受益者）：
#   'shatter'    = 碎三角（全）：6 缝族全开；
#   'shatter_lattice' = 碎三角·晶格：仅 3 条晶格缝（绿底缝关闭）。
register_board_type('shatter', lambda **kw: shatter_spec(full=True, **kw))
register_board_type('shatter_lattice',
                    lambda **kw: shatter_spec(full=False, **kw))
