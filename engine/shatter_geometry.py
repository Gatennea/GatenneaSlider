# -*- coding: utf-8 -*-
"""碎三角板型（双形状滑块：红=边长1正三角形 / 绿=30-30-120 等腰）。

这是几何引擎「显式邻接」泛化（engine/lattice.py 的 adjacency 字段）的
首个真实受益板型：碎三角的双形状密铺**不是正则晶格**（红内部块邻居
{R,R,G}、绿内部块邻居 {G,G,R}，18 种邻接签名），无法用固定偏移表表达，
故用邻接表定义连通性。滑动仍走引擎原生机制（整侧平移 + 逐步碰撞 +
整盘单一连通），碰撞走几何 SAT overlap 钩子、形状走 cell_polygon 钩子、
**连通性与缝线走几何钩子**（components / seam_lines）。

⚠️ 连通性为什么必须走几何（2026-10-24 定）：查表邻接按「折叠到基本域
残差」取邻居，而滑一个边长就会把 34–38 块送出那 24 个残差类 → 查不到
邻居 → 整侧被误判孤立。历史上正是这一步逼出了「只能用整周期当步长」的
错误结论，进而把缝逼成锯齿。现在连通性直接按「两多边形共边」判，与坐标
在不在基本域无关；缝也直接由「真实共边所在直线」给出。

坐标约定（详见 engine/shatter_geometry 设计笔记）：
  · 平面顶点 x = k·√3/2、y = m/2（k,m 整数）→ 换到 (X,Y)=(x/√3, y)，
    则 X=k/2、Y=m/2 为半整数 → ×6 得整数点 P=(6X, 6Y)。
  · plane(P) = (P_x·√3/6, P_y/6)。
  · 缝 = 沿真实块边的直线（六族：线 0/30/60/90/120/150°）；
    滑一步 = 沿缝一个边长（30/90/150 → 1，0/60/120 → √3）。
  · 周期平移 U=(12,0)、V=(6,18)（P 坐标，放置格 <U,V>），邻接表按残差折叠，
    覆盖任意可达位置（**仅用于 _build_adjacency 建表**，移动期连通性不走它）。

两个预设：
  · 'shatter'         = 碎三角（全）：六族全开；
  · 'shatter_lattice' = 碎三角·单位边：仅 'd30'/'v'/'d150' 三族。
两者共享同一几何（shatter_spec 的 full 参数切换缝族集）。
"""
import math
from functools import lru_cache
from itertools import product

from .board import Block, BoardSpec, SeamFamily
from .lattice import Lattice

SQ3 = math.sqrt(3.0)

# ---- 单元构造（与 experiments/script__chk_iso_puzzle.py 一致）----
A = (0.0, 0.0); B = (2 * SQ3, 0.0); C = (SQ3, 3.0)
J = (SQ3, 0.0); H = (SQ3 / 2, 1.5); I = (3 * SQ3 / 2, 1.5)
F = (SQ3 / 2, 0.5); G = (3 * SQ3 / 2, 0.5); D = (SQ3, 1.0); E = (SQ3, 2.0)
RED = {'6': (D, F, H), '5': (D, J, F), '4': (D, G, J), '3': (D, I, G),
       '2': (D, E, I), '1': (D, H, E)}
GRN = {'12': (A, F, H), '11': (A, F, J), '10': (B, G, J), '9': (B, G, I),
       '8': (C, E, I), '7': (C, H, E)}
LOCAL = list(RED.items()) + list(GRN.items())


def _P(i, j):
    return (2 * SQ3 * i + SQ3 * j, 3.0 * j)


def _unit_up(i, j):
    p = _P(i, j)
    return [(role, tuple((v[0] + p[0], v[1] + p[1]) for v in tri))
            for role, tri in LOCAL]


def _unit_down(i, j):
    dx, dy = 2 * SQ3 * i + SQ3 * j + SQ3, 3.0 * j + 3.0
    return [(role, tuple((v[0] + dx, dy - v[1]) for v in tri))
            for role, tri in LOCAL]


def _solved_tiles():
    """48 块还原态：4 单元拼盘（与 _chk_iso_puzzle ② 同构）。

    每块返回 (orient, 三角) 二元组：上单元块用标准角色 '1'..'12'，下单元块
    用反射角色 'r1'..'r12'（unit_down 的 (v[0]+dx, dy-v[1]) 是 y 反射 +
    平移，形状/朝向与上单元同角色不同，必须用独立 orient 区分，否则
    _polygon_at 重建成未反射标准三角 → 与邻块重叠）。
    """
    tiles = []
    for i in range(2):
        for j in range(2 - i):
            for role, tri in _unit_up(i, j):
                tiles.append((role, tri))
            if i + j <= 0:
                for role, tri in _unit_down(i, j):
                    tiles.append(('r' + role, tri))
    return tiles


# ---- 平面 → 整数点（scale6）----
def _plane_to_point(vx, vy):
    """顶点 (vx,vy) → (P_x, P_y) 整数点：P=(Σ k_i, Σ m_i)，精确整数。"""
    kx = round(vx * 2 / SQ3)            # vx = kx·√3/2
    my = round(vy * 2)                  # vy = my/2
    return (kx, my)


def _centroid_point(tri):
    """三角形质心 → 整数「C 坐标」点（每块唯一，精确无舍入）。

    坐标约定（关键，旧实现在此处混用两套坐标导致全盘错位）：
      · 顶点整数坐标 (kx, my)：plane(vx,vy) = (vx·2/√3, vy·2) 取整，
        三角形顶点恰好落在此整数格（等边/等腰都是）。
      · 质心在 (kx,my) 格上是「平均值」= (Σkx/3, Σmy/3)，一般**非整数**
        （如 role'1' 质心 = (7/3, 3)）。
      · 故取 3× 质心 = (Σkx, Σmy) 作为块的整数「C 坐标」——精确整数、
        平移线性，无 round 舍入损失。滑动方向 _DIRS、周期 _U/_V、rank
        钩子、plane() 全部统一在此坐标系（详见文件头与 _reduce_shatter）。

    ⚠️ 旧公式 ``round(Σvx*2/√3/3)`` 把质心四舍五入到整数格，丢掉了
    (Σkx mod 3)/3 的尾数（如 7/3→2），使「按 <U,V> 折叠」的残差算错、
    邻接度被撑爆。此处一律用精确的 (Σkx, Σmy)。
    """
    sx = sum(_plane_to_point(v[0], v[1])[0] for v in tri)  # Σ 顶点 kx
    sy = sum(_plane_to_point(v[0], v[1])[1] for v in tri)  # Σ 顶点 my
    return (sx, sy)                                        # 3× 精确质心


# ---- SAT（三角重叠，正面积才算）----
# ⚠️ 必须排除「仅共顶点 / 共边」的贴合：滑动合法态里相邻三角本就共边，
# 若把贴合判成重叠，整个谜题会被误锁死。故投影区间须严格分离（带 EPS）
# 才判为不重叠；仅相切（重叠宽度≈0）视为不重叠。
_EPS = 1e-9


def _tri_overlap(t1, t2):
    axes = []
    for tri in (t1, t2):
        for i in range(3):
            e = (tri[(i + 1) % 3][0] - tri[i][0], tri[(i + 1) % 3][1] - tri[i][1])
            axes.append((-e[1], e[0]))
    for ax in axes:
        p1 = [ax[0] * v[0] + ax[1] * v[1] for v in t1]
        p2 = [ax[0] * v[0] + ax[1] * v[1] for v in t2]
        # 任一侧投影严格分离（宽度 > EPS）→ 两三角不重叠
        if min(p1) >= max(p2) - _EPS or min(p2) >= max(p1) - _EPS:
            return False
    return True


def _bbox(tri):
    xs = [v[0] for v in tri]; ys = [v[1] for v in tri]
    return (min(xs), min(ys), max(xs), max(ys))


def _boxes_overlap(b1, b2):
    return not (b1[2] < b2[0] or b2[2] < b1[0] or b1[3] < b2[1] or b2[3] < b1[1])


def _gen_tiling(K):
    """生成 ±K 个放置格内的完整周期密铺三角（去重质心）。

    返回 [(centroid_P, verts_P, role, plane_tri), ...]：
      · centroid_P：质心整数点（换键 / 折叠用）；
      · verts_P：三顶点整数点（共 2 顶点 = 共边判据用）；
      · role：LOCAL 原始角色（'1'..'12'，决定红/绿朝向）；
      · plane_tri：三角原始平面坐标（overlap / cell_polygon 渲染用）。
    up(i,j) 与 down(i,j) 合起来覆盖所有放置格位置（down(i,j) 落在
    up(i,j+1) 处），故枚举 (i,j)∈[−K,K]² 即得完整密铺。
    """
    out = []
    seen = set()
    for i in range(-K, K + 1):
        for j in range(-K, K + 1):
            for role, tri in _unit_up(i, j) + _unit_down(i, j):
                c = _centroid_point(tri)
                if c in seen:
                    continue
                seen.add(c)
                rv = tuple(_plane_to_point(v[0], v[1]) for v in tri)
                out.append((c, rv, role, tri))
    return out


# ---- 块多边形（overlap / cell_polygon 用）----
# 块身份 = (point, orient)。orient 编码「形状 + 旋转(+反射)」：
#   · 上单元块 → 标准角色 '1'..'12'（LOCAL 标准三角，未反射）；
#   · 下单元块 → 'r'+角色（'r1'..'r12'），即标准三角沿水平轴的反射——unit_down
#     的 (v[0]+dx, dy-v[1]) 本质是 y 反射 + 平移，下单元块形状/朝向与上单元同角色
#     不同，须用独立标签区分；否则本函数会把下单元块重建成未反射标准三角，与邻块
#     重叠（还原态 20 处重叠的真凶）。块滑动是刚体平移——反射随块走，orient 一经
#     赋值不再改变；落点 R/G 残差都正确取标准（或反射）三角再平移即可（彻底解决
#     旧「(残差,orient)」建表在「G 块滑到 R 残差位」时查不到的 KeyError）。
_LOCAL_POLY = {role: tri for role, tri in LOCAL}   # 上单元（标准）角色 → 标准平面三角
for _r, _t in LOCAL:                               # 下单元（反射）角色 → y 反射三角
    _LOCAL_POLY['r' + _r] = tuple((v[0], -v[1]) for v in _t)


def _polygon_at(point, orient):
    """块 (point, orient=角色) 处的真实平面多边形（刚体平移，绝不改旋转）。"""
    tri = _LOCAL_POLY[orient]
    cx = sum(v[0] for v in tri) / 3.0
    cy = sum(v[1] for v in tri) / 3.0
    px = point[0] * SQ3 / 6.0
    py = point[1] / 6.0
    dx = px - cx
    dy = py - cy
    return tuple((v[0] + dx, v[1] + dy) for v in tri)


# ---- 缝族：线方向 = 密铺的真实边方向（重写 2026-10-24）----
# 换算：plane(C) = (C_x·√3/6, C_y/6)，故 rank 泛函 coeffs 在平面上的法向是
# (√3·c_x, 3·c_y)；{f=t} 的线方向与之垂直。六族（按**线的方向**命名）：
#     线 0°(h)  c=(0,1)   线 30° c=(-1,1)  线 60°  c=(-3,1)
#     线 90°(v) c=(1,0)   线 120° c=(3,1)  线 150° c=(1,1)
# 线的方向必须取自密铺里**真有长串共线边**的三族（实测 30/90/150 各 40 条；
# 0/60/120 只有 8 条、全在盘面外沿）——否则缝只能沿别的方向的边爬成锯齿。
#
# 滑动步长 = 沿缝 **一个边长**（与 experiments/script__shatter_proto.py 的 fam_step
# 同口径）：30/90/150 的边长 1（C 步长 3 格单位）、0/60/120 的边长 √3（C
# 步长 6 格单位）。这是唯一物理自洽的选择：缝是直线时两侧互为沿缝的刚体
# 平移，**途中任何位置都不重叠**；步长再取整周期（沿这些方向高达 6 个边长
# = 整个盘面高）就把半平面整体滑出盘面，等于没有移动。
#
# ⚠️ 旧实现（已全部作废，勿恢复）用「整周期向量」当步长，为了凑出非零步长
# 又把三条缝的**轴**选成 0/60/120/30/150 的错配组合，结果缝在盘面上呈锯齿；
# 而锯齿缝要滑动必须两侧互相穿透——引擎只看端点，端点因周期性恰好不重叠，
# 于是「合法」但物理上根本滑不动。这是碎三角一直玩不了的总根。
_SEAM_DEFS = (
    ('h',    (0, 1),  ((6, 0), (-6, 0))),        # 线 0°：沿 √3 步
    ('d30',  (-1, 1), ((3, 3), (-3, -3))),       # 线 30°：沿 1 步
    ('d60',  (-3, 1), ((3, 9), (-3, -9))),       # 线 60°：沿 √3 步
    ('v',    (1, 0),  ((0, 6), (0, -6))),        # 线 90°：沿 1 步
    ('d120', (3, 1),  ((-3, 9), (3, -9))),       # 线 120°：沿 √3 步
    ('d150', (1, 1),  ((3, -3), (-3, 3))),       # 线 150°：沿 1 步
)
# 步长 = 1 个边长的三族（红等边三角的边方向；也是密铺内部的 40 条边族）
_UNIT_SEAMS = ('d30', 'v', 'd150')

# ----------------------------------------------------------------------
# 方向字母词汇表（engine/compat.py 注册用；与 mi_geometry / tri_geometry
# 的同名常量同一职责——GUI 既有格式用字母，引擎用方向元组）
#
# 字母语义与另外三个板型对齐（屏幕坐标 y 轴向下）：
#   d 右 / a 左 / s 下 / w 上
#   x 右下(30°) / t 右下(60°) / f 左下(30°) / z 左下(60°)
#   r 右上(30°) / e 右上(60°) / g 左上(30°) / q 左上(60°)
# 平面换算：plane(P) = (P_x·√3/6, P_y/6)，故 (3,3) 落屏 (√3/2,1/2)=右下 30°、
# (3,9) 落屏 (√3/2,3/2)=右下 60°——**字母按落屏方向定，不按分量符号直觉定**
# （P 坐标各向异性）。
# 两张表与 spec 的各族 parallel 成员一一对应（move_to_action 要求
# 字母↔方向双射），'shatter_lattice' 只开 3 条单位边长缝 → 只要 6 个字母。
# ----------------------------------------------------------------------
SHATTER_DIRECTIONS = {
    'd': (6, 0),       # 右       线 0° 沿缝 +
    'a': (-6, 0),      # 左
    'x': (3, 3),       # 右下 30°  线 30° +
    'g': (-3, -3),     # 左上 30°
    't': (3, 9),       # 右下 60°  线 60° +
    'q': (-3, -9),     # 左上 60°
    's': (0, 6),       # 下       线 90° +
    'w': (0, -6),      # 上
    'z': (-3, 9),      # 左下 60°  线 120° +
    'e': (3, -9),      # 右上 60°
    'r': (3, -3),      # 右上 30°  线 150° +
    'f': (-3, 3),      # 左下 30°
}
SHATTER_LATTICE_DIRECTIONS = {
    'x': (3, 3), 'g': (-3, -3),
    's': (0, 6), 'w': (0, -6),
    'r': (3, -3), 'f': (-3, 3),
}

# 单位边长缝（'shatter_lattice' 只开这三族）/ 全部六族（'shatter'）
_UNIT_DIRS = _UNIT_SEAMS
_ALL_DIRS = tuple(d[0] for d in _SEAM_DEFS)

# 24 个朝向标签（身份标签 = 形状 + 旋转(+反射)，见 shatter_spec）：
#   · '1'..'12'      = 上单元块（标准三角，未反射）；
#   · 'r1'..'r12'    = 下单元块（同角色沿水平轴反射，形状/朝向不同）。
# trivial 对称下 _ORIENT_DIRS 仅用于 dir_to_orient 双射，须互异、非零即可；
# 这里给 12 个标准向量 + 12 个带 x=3 的互异向量，确保 24 个全互异。
_ROLES = tuple(r for r, _ in LOCAL) + tuple('r' + r for r, _ in LOCAL)
assert len(_ROLES) == 24
_ORIENT_DIRS = {
    '1': (1, 0), '2': (0, 1), '3': (1, 1), '4': (2, 0), '5': (0, 2), '6': (-1, 1),
    '7': (-1, 0), '8': (0, -1), '9': (-1, -1), '10': (-2, 0),
    '11': (0, -2), '12': (1, -1),
}
for _i, _r in enumerate(r for r, _ in LOCAL):
    _ORIENT_DIRS['r' + _r] = (3, _i - 6)   # 12 个互异、非零向量（(3,-6)..(3,5)）

# 周期平移（C 坐标 = 3× 精确质心，见 _centroid_point）：
#   碎三角无限密铺对 <U,V> 严格周期（实测 up(i+1,j)-up(i,j)≡(12,0)、
#   up(i,j+1)-up(i,j)≡(6,18) 对全部 12 角色成立；全密铺 up∪down 覆盖度
#   1.000 验证为真周期）。
#   ⚠️ 旧代码把周期写成 (4,0)/(2,6)——那是**未缩放的顶点格 (kx,my)** 版本，
#   与本文件统一的 C 坐标（3× 质心）差 3 倍，导致按 <U,V> 折叠残差错位、
#   邻接度被撑爆成 6–8、连通性碎成多个单元团。正确周期为下：
_U = (12, 0)
_V = (6, 18)


def _reduce_shatter(point):
    """碎三角基本域还原（与 Lattice._reduce_adj 同公式，建表阶段独立可用）。"""
    b = point[1] // _V[1]
    r_y = point[1] - b * _V[1]
    a = (point[0] - b * _V[0]) // _U[0]
    r_x = point[0] - a * _U[0] - b * _V[0]
    return (r_x, r_y)


# 块在「(残差, 朝向)」下的标准平面多边形表：整盘对 <U,V> 周期，每个
# (residue, orient) 唯一对应一个 LOCAL 三角；取代表三角平移到质心
# plane(point) 即得任意位置的真实多边形（含红/绿各自的旋转朝向）。
# ⚠️ 必须用足够大的 K 覆盖全部 24 个残差类（12R+12G）：K=2 时某些
# 残差（如 (2,10) 的绿块）尚未出现在枚举窗口内，会导致 _polygon_at
# 注：标准多边形改由 _LOCAL_POLY（按角色）直接提供，不再按 (残差,orient)
# 建表——避免「G 块滑到 R 残差位」查不到的 KeyError，且块旋转靠 orient=角色
# 固化，重叠/渲染都走刚体平移。_reduce_shatter/_U/_V 仅供 _build_adjacency 用。


def _build_adjacency():
    """碎三角双形状密铺的显式邻接：从**完整周期密铺**（处处六边形）折叠出
    「残差 → RAW 质心位移集」，按 <U,V> 还原、存未包裹真实位移。

    无限密铺的构造（经实测为真正 edge-to-edge 的三角-六边形密铺）：
      每个放置格位置 loc(i,j) 处放 上单元 up(i,j)（12 块▲为主）与
      下单元 down(i,j-1)（12 块▼为主）——二者同位互锁成 24 块六边形；
      六边形铺满平面，且对 <U,V> 平移不变（up/down 两族各自周期于
      <U,V>）。故整盘是**真正周期**的，按 <U,V> 折叠还原即正确，不会再
      出现「碎片三角把不同块型压成同残差、度被撑爆」的旧病。

    做法：在 ±K 个放置格内生成完整密铺（去重质心），枚举共 2 顶点边，
    存 RAW 位移 delta = c_j - c_i（真实小向量）到残差 reduce(c_i)，反向
    挂 reduce(c_j)。±K 足够大 → 中央残差的全部局部邻接都被覆盖（盘内
    每残差出现多次，取并集即完整）。查邻接走 Lattice.neighbors_of：
    ``point + d`` 对还原态块即精确实际质心、对任意可达位置即同周期像。

    ⚠️ 绝不存「残差差」reduce(c_j)-reduce(c_i)——那会被 <U,V> 包裹成
    周期像（如 (4,0)/(2,6)），把三角度 2–3 撑爆。必须存未包裹真实位移。
    """
    tris = _gen_tiling(4)
    n = len(tris)
    base = {}
    for i in range(n):
        vi = frozenset(tris[i][1])
        ci = tris[i][0]
        rp = _reduce_shatter(ci)
        for j in range(i + 1, n):
            if len(vi & frozenset(tris[j][1])) != 2:
                continue
            rq = _reduce_shatter(tris[j][0])
            d = (tris[j][0][0] - ci[0], tris[j][0][1] - ci[1])   # RAW
            if d == (0, 0):
                continue
            base.setdefault(rp, set()).add(d)
            base.setdefault(rq, set()).add((-d[0], -d[1]))
    # 自检（开发期防御）：碎三角是规整三角密铺，每块恰有 3 个共边邻居 →
    # 残差度恒为 3；残差 24 类（12 红 + 12 绿，红绿残差互不交——已实测
    # intersection=0，故可安全按残差单一键存邻接）。断言失败即几何回归。
    degs = [len(s) for s in base.values()]
    assert min(degs) >= 2 and max(degs) <= 3, \
        f"碎三角残差度须为 2–3（三角面），收到分布 {sorted(degs)}"
    assert len(base) == 24, f"碎三角应折出 24 个残差类（12R+12G），收到 {len(base)}"
    return {rp: tuple(sorted(s)) for rp, s in base.items()}


def _shatter_lattice():
    return Lattice(dim=2, scale=1, symmetry='trivial',
                   adjacency=_build_adjacency(), adj_periods=(_U, _V))


def _overlap_hook(moved_keys, rest_keys):
    """几何 SAT：被移动簇与定侧簇是否有正面积重叠（含同点）。

    orient 已是具体角色（形状 + 旋转），故每块多边形 = 该角色标准三角刚体
    平移——无论落点是 R 还是 G 残差都正确（刚体滑动不变旋转）。
    """
    if not moved_keys or not rest_keys:
        return False
    mv = {p: _polygon_at(p, o) for p, o in moved_keys}
    rs = {p: _polygon_at(p, o) for p, o in rest_keys}
    bmv = {p: _bbox(t) for p, t in mv.items()}
    brs = {p: _bbox(t) for p, t in rs.items()}
    for pm, tm in mv.items():
        bm = bmv[pm]
        for pr, tr in rs.items():
            if _boxes_overlap(bm, brs[pr]):
                if _tri_overlap(tm, tr):
                    return True
    return False


def _cell_polygon(point, orient=''):
    """块在 (point, orient=角色) 处的平面多边形（P3b 渲染器消费）。"""
    return _polygon_at(point, orient)


def _solved_check(board):
    """还原 = 精确拼合（拼图语义：键集与还原态逐块相同）。"""
    goal = {(b.point, b.orient) for b in board.spec.goal_blocks}
    return board.keys == goal


def _goal_blocks():
    tiles = _solved_tiles()
    out = []
    for orient, tri in tiles:
        p = _centroid_point(tri)
        out.append(Block(p, orient))   # orient = 上/下角色标签（形状 + 旋转 + 反射一体）
    return tuple(out)


# ----------------------------------------------------------------------
# 几何钩子：顶点表 / 连通性 / 缝线表（显式邻接板型必需的三件）
# ----------------------------------------------------------------------
@lru_cache(maxsize=8192)
def _block_vertices(key):
    """块键 → 三个顶点的整数 P 坐标（精确、缓存）。

    所有滑动步长在平面里都是 (k·√3/2, m/2) 的整数倍，故顶点 P 坐标恒为
    整数——共边判定可以精确比对，不需要浮点容差（曾有「精确 float 相等
    只数出一半共边」的坑，这里从数据源头消掉了浮点）。
    """
    point, orient = key
    return tuple(_plane_to_point(v[0], v[1])
                 for v in _polygon_at(point, orient))


def _vertex_rank(coeffs, p):
    """顶点在**块缝坐标尺度**下的 rank。

    块的位置 C = 三顶点 P 之和，故 rank(块) = Σ coeffs·P_v；于是把顶点
    rank 记作 r_v = 3·(coeffs·P_v)，就有 rank(块) = (r₁+r₂+r₃)/3。
    因此 {rank=t} 的缝线过某顶点 ⟺ t = r_v；块被线劈开 ⟺ min r_v < t < max r_v。
    """
    return 3 * (coeffs[0] * p[0] + coeffs[1] * p[1])


def _edge_owner_map(keys):
    """共边索引：边（两端整数 P，排序）→ 占用它的块键列表。"""
    out = {}
    for k in keys:
        vs = _block_vertices(k)
        for i in range(3):
            a, b = vs[i], vs[(i + 1) % 3]
            e = (a, b) if a <= b else (b, a)
            out.setdefault(e, []).append(k)
    return out


def _components(keys):
    """几何连通分量（spec.components 钩子）。

    ⚠️ 为什么不能用查表式邻接：`Lattice.neighbors_of` 的显式邻接按「折叠到
    基本域残差」取邻居，块一旦落到残差表外就查不到邻居（实测：按 1 个边长
    平移后 34–38 块落到 24 个残差类之外）→ 整侧被误判成孤立，滑动一律被
    拒。共边判定只看真实多边形，与坐标在不在基本域无关，这才是「物理连通」
    的本义。
    """
    keys = frozenset(keys)
    if not keys:
        return ()
    adj = {}
    for owners in _edge_owner_map(keys).values():
        if len(owners) < 2:
            continue
        for i in range(len(owners)):
            for j in range(i + 1, len(owners)):
                a, b = owners[i], owners[j]
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
    comps = []
    seen = set()
    for seed in keys:
        if seed in seen:
            continue
        seen.add(seed)
        comp = {seed}
        stack = [seed]
        while stack:
            p = stack.pop()
            for q in adj.get(p, ()):
                if q not in seen:
                    seen.add(q)
                    comp.add(q)
                    stack.append(q)
        comps.append(frozenset(comp))
    return tuple(comps)


def _seam_lines(board, fam):
    """该族在当前局面下的**真实缝线** ((t, line), ...)（spec.seam_lines 钩子）。

    判据：存在一条跨块接触边，整条落在 {rank = t} 上（两端点 rank 相等）。
    这样的线天然沿块边走、绝不劈开任何块——这正是「直线缝」的定义。旧的
    「逐整数 t 枚举」不满足它：那些 t 里绝大多数线是穿块内部的，画到盘面上
    就是锯齿（因为真正有边的方向只有三条，而枚举不认边）。

    外部线号 line = t - 1，与 engine/compat 的 gap_line = t - 1 口径一致。

    ⚠️ 性能：``_seam_clear`` 会对**每条候选缝**调一次本函数，而候选有几百条
    ——不缓存时同一个局面要把整族缝线重算几百遍（实测 10 次 all_gaps() 触发
    2500 次本函数，占掉全部耗时）。按「局面键集合 + 族」缓存后，同一局面
    只算一次；局面一变键集合就变，自然不会读到旧结果。
    """
    return _seam_lines_cached(frozenset(board.keys), fam.name,
                              tuple(fam.coeffs))


@lru_cache(maxsize=16)
def _seam_lines_cached(keys, _fam_name, coeffs):
    """``_seam_lines`` 的真正实现（按局面键集合 + 族系数缓存）。"""
    ts = set()
    for (a, b), owners in _edge_owner_map(keys).items():
        if len(owners) < 2:
            continue
        ra = _vertex_rank(coeffs, a)
        if ra == _vertex_rank(coeffs, b):
            ts.add(ra)
    # 硬过滤：线必须**整条**沿块边走——盘面是台阶形，一条局部贴边的直线
    # 会在别处穿过块内部（实测不过滤时 12 条里只剩 1 条真缝，其余 11 条
    # 都劈块）。块被劈 ⟺ 该块三顶点 rank 跨 t 两侧。
    spans = []
    for k in keys:
        rs = [_vertex_rank(coeffs, p) for p in _block_vertices(k)]
        spans.append((min(rs), max(rs)))
    out = [t for t in sorted(ts)
           if not any(lo < t < hi for lo, hi in spans)]
    return tuple((t, t - 1) for t in out)


def _seam_clear(fam, t, board):
    """该缝号是不是**真实缝线**（spec.seam_clear 钩子）。

    存在理由：``is_valid_gap`` 只问「两侧都有块」，不会问「这条线是不是沿
    块边」——碎三角早先没有 seam_clear，于是任意整数线号都被判「有效」，
    选到劈块的线就画出锯齿。这里把判据收严成「t 在 _seam_lines 里」。
    """
    return any(tt == t for tt, _ln in _seam_lines(board, fam))


def shatter_spec(full: bool = True, name: str = 'shatter') -> BoardSpec:
    """碎三角板型：48 块（4 单元）还原态；双形状（红等边 / 绿等腰）。

    orient 编码「形状 + 旋转」：12 个角色 '1'..'12'（红 '1'..'6' / 绿
    '7'..'12'），每块是固定形状 + 固定旋转——滑动是刚体平移，旋转随块走，
    重叠与渲染都按角色取标准三角再平移。

    full=True → 六族全开（'shatter'：线 0/30/60/90/120/150°）；
    full=False → 仅三条单位边长缝 'd30'/'v'/'d150'（'shatter_lattice'）。

    可玩性口径（2026-10-24 重写，旧「整周期步长」全部废弃）：
      · 缝 = 一条**直线**，沿真实块边；由 _seam_lines 几何给出，
        绝不做逐整数 t 枚举（那是锯齿的来源）；
      · 滑动 = 沿缝一个边长（30/90/150 → 1，0/60/120 → √3）；
      · 合法性 = 不重叠（SAT）+ 每步后几何连通（_components），
        不再依赖折叠残差的查表邻接。
    """
    names = _ALL_DIRS if full else _UNIT_DIRS
    families = []
    for fname, coeffs, parallel in _SEAM_DEFS:
        if fname not in names:
            continue
        families.append(SeamFamily(fname, coeffs, parallel, line_scale=1))
    directions = tuple(p for fam in families for p in fam.parallel)
    return BoardSpec(
        name=name,
        lattice=_shatter_lattice(),
        directions=directions,
        seam_families=tuple(families),
        orientations=_ROLES,
        orient_dirs=tuple(_ORIENT_DIRS[r] for r in _ROLES),
        goal_blocks=_goal_blocks(),
        seam_clear=_seam_clear,
        solved_check=_solved_check,
        overlap=_overlap_hook,
        cell_polygon=_cell_polygon,
        components=_components,
        seam_lines=_seam_lines,
    )
