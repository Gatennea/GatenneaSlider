# -*- coding: utf-8 -*-
"""六边形密铺负面测试（P2 冻形预检第一个拷问用例）。

执行：python test/_test_hex_negative.py
约定：脚本型回归（check 收集失败，退出码非 0 即失败），零 pygame。

**为什么蜂巢必须是负面案例**（2026-10-23 立论的几何事实）：
正六边形密铺的行是半格错位的砖墙（点立六角，行距 3/2、奇偶行水平
错开 √3/2）。三条边方向（30°/90°/150°）上**不存在贯穿全盘的直线
缝**——竖直边在偶数行成段、奇数行整体平移半格，砖墙式交错；而平行
于格点平移的方向（0°/60°/120°）上的直线全部穿过六边形**中心**、
把块切穿。结论：蜂巢里没有任何一条「干净缝」，物理上完全滑不动
（任何整组的平移都会在半路上与邻行咬合碰撞）。

**本测试要钉死引擎的三件事**：
  N0  剥掉 seam_clear 钩子 → 引擎的线性缝模型认为蜂巢可玩（误放行）。
      这不是假想：rank 分区线穿过块心，端点位置恰好只接触不重叠，
      碰撞全发生在单位步的**半路上**，端点判据看不见。
  N0b 只挂端点几何 overlap 钩子（米字同款 SAT 口径）→ **仍然误放行**。
      （更正 2026-10-23 的计划原稿：原稿以为 overlap 是必不可缺的
      钩子；几何算下来 overlap 对蜂巢完全盲目，真正必不可缺的是
      **seam_clear**——它按「线切进任何块内部即锁死」把全部候选缝
      锁掉，与米字 span 判据同一机制。）
  N1  挂上 seam_clear → 零合法移动（冻形），与物理真相一致。
  N2  地面真值（精确扫描判据）：N0 枚举出的每一个候选移动，其平移
      路径都穿过某对块的重叠区 → 物理有效移动数 = 0 → 蜂巢**确实**
      冻形 → N1 的钩子不是「无脑全锁」了事，答案是对的。
  P1/P2 阳性对照：钩子会放行不切块的缝、扫描器放得开真正的空程 —
      —证明 N1/N2 的零不是判据空转。

阳性对照与地面真值都用分数（Fraction）精确算术：坐标 (A, B) 表示
真实点 (√3·A, B)，全部量落在 Q(√3) 里，无浮点误差。

坐标约定（点立六角、外接圆 R=1、格心 = (√3(q+r/2), 3r/2)）：
  · 邻接 = 轴向六邻 (q±1,r)/(q,r±1)/(q+1,r-1)/(q-1,r+1)；
  · 三缝族（rank = 点部线性泛函，与方形/立方同构）：
      h  f=q·0+r·1  平行 (±1,0)      （真实方向 0°）
      d1 f=q·1+r·0  平行 (0,±1)      （真实方向 60°）
      d2 f=q·1+r·1  平行 (1,-1)/(-1,1)（真实方向 120°）
  · 还原态 = 边长 k 实心正六边形 H_k（3k(k+1)+1 块）。

⚠️ 本 preset **故意不注册**进 engine 注册表：不可玩的板型一旦可被
GUI 选中就是事故。它作为「拷问用例」活在本文件里，供 P2 冻形预检
引用；将来若做「几何不合法 preset」测试套件再迁去 engine/。
"""

import os
import sys
from fractions import Fraction as F

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import (  # noqa: E402
    Block,
    Board,
    BoardSpec,
    Lattice,
    SeamFamily,
    frozen,
    locked_seams,
)

failures = []


def check(cond, msg):
    if cond:
        print(f"  ok: {msg}")
    else:
        failures.append(msg)
        print(f"  FAIL: {msg}")


# ----------------------------------------------------------------------
# 一、蜂巢几何（精确有理数；(A,B) = 真实点 (√3·A, B)）
# ----------------------------------------------------------------------
def hex_lattice() -> Lattice:
    """蜂巢格心 = 三角晶格：轴向坐标 Z²、6 邻接、无奇偶约束。"""
    return Lattice(dim=2, scale=1,
                   neighbor_steps=((1, 0), (-1, 0), (0, 1), (0, -1),
                                   (1, -1), (-1, 1)))


#: 点立六角（R=1）顶点偏移（(A,B) 表示）：(±1/2,±1/2) 与 (0,±1)
VERT_OFF = ((F(1, 2), F(1, 2)), (F(0), F(1)), (F(-1, 2), F(1, 2)),
            (F(-1, 2), F(-1, 2)), (F(0), F(-1)), (F(1, 2), F(-1, 2)))


def center_ab(q: int, r: int):
    """格心 (q,r) 的 (A,B) 表示（真实 = (√3·A, B)）。"""
    return (F(q) + F(r, 2), F(3 * r, 2))


def delta_ab(d):
    """引擎方向（点位移）→ 真实位移的 (A,B) 表示。"""
    return (F(d[0]) + F(d[1], 2), F(3 * d[1], 2))


def g_at(coeffs, A, B):
    """缝泛函在真实点 (A,B) 上的值：g = f∘M⁻¹ = a·q(v) + b·r(v)，
    q(v) = A − B/3，r(v) = 2B/3 → g = a·A + (2b−a)·B/3。"""
    return coeffs[0] * A + (2 * coeffs[1] - coeffs[0]) * B / 3


def span_of(coeffs, q: int, r: int):
    """块 (q,r) 在该族缝坐标下的**开**跨度（六顶点 g 值 min/max）。

    线 t 严格落进跨度内部 = 切块 = 缝锁死（与米字 span_t 同机制）。
    """
    A, B = center_ab(q, r)
    vals = [g_at(coeffs, A + da, B + db) for da, db in VERT_OFF]
    return min(vals), max(vals)


def seam_clear(fam, t, board) -> bool:
    """BoardSpec.seam_clear 钩子：缝线切进任何块内部 → 锁死（False）。

    蜂巢的全部候选缝（rank 整数线）都穿过某行的块心，因此全部锁死。
    """
    for b in board.blocks:
        lo, hi = span_of(fam.coeffs, b.point[0], b.point[1])
        if lo < t < hi:
            return False
    return True


def hex_verts_real(q: int, r: int):
    """cell_polygon 钩子：六边形顶点（真实坐标浮点，仅绘制用）。"""
    A, B = center_ab(q, r)
    rt3 = 3 ** 0.5
    return tuple((rt3 * float(A + da), float(B + db)) for da, db in VERT_OFF)


def cell_polygon(point, orient=''):
    return hex_verts_real(point[0], point[1])


def overlap_pair(p, q) -> bool:
    """两块是否有正面积重叠（精确）：差体六边形内部判据。

    差体 D = P−P 是同形六边形（内半径 √3）；d = (√3·ΔA, ΔB) ∈ int(D)
    ⟺ |ΔA| < 1 且 |ΔA+ΔB| < 2 且 |ΔA−ΔB| < 2（严格，共边共点不算）。
    """
    A1, B1 = center_ab(p[0], p[1])
    A2, B2 = center_ab(q[0], q[1])
    dA, dB = A1 - A2, B1 - B2
    return abs(dA) < 1 and abs(dA + dB) < 2 and abs(dA - dB) < 2


def hex_overlap(moved, rest) -> bool:
    """BoardSpec.overlap 钩子：两簇块键之间有无几何重叠（含同键）。

    只查**端点**位置——这正是它对蜂巢盲目的原因：单位步平移的碰撞
    发生在半路上，端点恰好只接触不重叠（见 P2 与 N0b）。
    """
    if not moved or not rest:
        return False
    if moved & rest:
        return True
    mp = {k[0] for k in moved}
    rp = {k[0] for k in rest}
    for p in mp:
        for q in rp:
            if overlap_pair(p, q):
                return True
    return False


# ----------------------------------------------------------------------
# 二、地面真值：精确扫描判据（半路碰撞）
# ----------------------------------------------------------------------
_BIG = F(10 ** 6)


def _open_interval(c, e, lo, hi):
    """{τ : lo < c·τ + e < hi} 的开区间（None = 空集）。"""
    if c > 0:
        return ((lo - e) / c, (hi - e) / c)
    if c < 0:
        return ((hi - e) / c, (lo - e) / c)
    return (-_BIG, _BIG) if lo < e < hi else None


def sweep_hit(m_pts, r_pts, d, step):
    """精确扫描碰撞检查（地面真值的核心）。

    moved 各块沿 d 平移 step 个单位：逐个单位步、逐对 (moved, rest)，
    用分数算术解「中心路径穿过重叠区」的 τ 区间（重叠区 = 以 rest
    块心为中心的差体六边形内部；路径是线段，区域是凸的，六个严格
    线性约束的开区间交非空 ⟺ 半路相撞）。

    返回见证 (m, r, 单位步序号, τ下界, τ上界) 或 None（全程无碰撞）。
    """
    wA, wB = delta_ab(d)
    for m in m_pts:
        for i in range(step):
            base = (m[0] + i * d[0], m[1] + i * d[1])
            A0, B0 = center_ab(base[0], base[1])
            for r in r_pts:
                Ar, Br = center_ab(r[0], r[1])
                eA, eB = A0 - Ar, B0 - Br
                iv = []
                for c, e, lo, hi in (
                        (wA, eA, -1, 1),          # |A| < 1
                        (wA + wB, eA + eB, -2, 2),  # |A+B| < 2
                        (wA - wB, eA - eB, -2, 2)):  # |A−B| < 2
                    sub = _open_interval(c, e, lo, hi)
                    if sub is None:
                        iv = None
                        break
                    iv.append(sub)
                if iv is None:
                    continue
                low = max(x[0] for x in iv)
                high = min(x[1] for x in iv)
                if low < high and low < 1 and high > 0:
                    return (m, r, i, low, high)
    return None


# ----------------------------------------------------------------------
# 三、preset 构造（钩子可拆，专供反面拷问）
# ----------------------------------------------------------------------
def hex_goal(k: int):
    """边长 k 实心正六边形还原态：|q|,|r|,|q+r| ≤ k（3k(k+1)+1 块）。"""
    return tuple(Block((q, r))
                 for q in range(-k, k + 1)
                 for r in range(-k, k + 1)
                 if abs(q) <= k and abs(r) <= k and abs(q + r) <= k)


def hex_spec(k: int, name: str = 'hex-neg',
             with_seam_clear: bool = True,
             with_overlap: bool = True) -> BoardSpec:
    """蜂巢 preset（负面拷问用）：三线性缝族 + 可拆钩子。"""
    fams = (
        SeamFamily('h', (0, 1), ((1, 0), (-1, 0))),
        SeamFamily('d1', (1, 0), ((0, 1), (0, -1))),
        SeamFamily('d2', (1, 1), ((1, -1), (-1, 1))),
    )
    return BoardSpec(
        name=name,
        lattice=hex_lattice(),
        directions=((1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)),
        seam_families=fams,
        goal_blocks=hex_goal(k),
        seam_clear=seam_clear if with_seam_clear else None,
        overlap=hex_overlap if with_overlap else None,
        cell_polygon=cell_polygon,
    )


# ----------------------------------------------------------------------
# 四、测试本体
# ----------------------------------------------------------------------
print('== S 构造自检：蜂巢 preset 是合法板型 ==')
for k in (1, 2, 3):
    spec = hex_spec(k)
    b = Board(spec, spec.goal_blocks)
    n = 3 * k * (k + 1) + 1
    check(b.block_count == n,
          f"H_{k} 块数 {b.block_count} = 3k(k+1)+1 = {n}")
    check(b.is_solved(), f"H_{k} 还原态 is_solved 自洽")
    check(len(spec.lattice.neighbors_of((0, 0))) == 6,
          f"H_{k} 格心 6 邻接（轴向六邻）")
    v = spec.cell_polygon((0, 0))
    check(len(v) == 6 and len(set(v)) == 6,
          f"H_{k} cell_polygon 给 6 个互异顶点")

print()
print('== P1 钩子选择性：seam_clear 不是无脑全锁 ==')
spec_sel = hex_spec(1, name='hex-neg-sel')
b_sel = Board(spec_sel, (Block((0, 0)), Block((10, 10))))
fam_h = spec_sel.seam_families[0]
check(spec_sel.seam_clear(fam_h, 5, b_sel) is True,
      "seam_clear：t=5 不切任何块 → 放行（会解锁）")
check(spec_sel.seam_clear(fam_h, 0, b_sel) is False,
      "seam_clear：t=0 穿过 (0,0) 块心 → 锁死")
check(spec_sel.seam_clear(spec_sel.seam_families[2], 20, b_sel) is False,
      "seam_clear：d2 族 t=20 穿过 (10,10) 块心（q+r=20）→ 锁死")

print()
print('== P2 扫描器阳性对照：不是无脑全撞 ==')
check(sweep_hit([(0, 0)], [(30, 30)], (1, 0), 1) is None,
      "扫描器：rest 在 30 格外 → 空程无碰撞（判得出可走）")
w = sweep_hit([(0, 0)], [(0, 1)], (1, 0), 1)
check(w is not None,
      f"扫描器：(0,0) 右滑擦过 (0,1) → 半路碰撞 τ∈({float(w[3]):.3f},"
      f"{float(w[4]):.3f})" if w else "扫描器：漏报半路碰撞")
check(not overlap_pair((0, 0), (0, 1)),
      "佐证：终点两位置不重叠——端点判据的盲区正是这一撞")

print()
print('== N0 剥 seam_clear：引擎误放行（线性缝模型的假象） ==')
# ⚠️ H_1 step=3 是规模假象：7 块小盘上任何 3 单位平移都把选中片
#    甩出邻接圈（断开），无钩子模型自己也空——与几何无关，故大步长
#    用例取 H_2/H_3（下面 N0c 把这个假象单独钉住）。
for k, steps in ((1, (1, 2)), (2, (1, 2, 3)), (3, (1, 2, 3))):
    for step in steps:
        spec = hex_spec(k, with_seam_clear=False, with_overlap=False)
        b = Board(spec, spec.goal_blocks)
        mv = b.legal_moves(step)
        check(len(mv) > 0,
              f"H_{k} step={step} 无钩子 → 引擎认为可玩：{len(mv)} 个"
              f"合法移动（物理上全部非法）")

print()
print('== N0c 规模假象备案：H_1 step=3 无钩子也为空 ==')
spec_tiny = hex_spec(1, with_seam_clear=False, with_overlap=False)
b_tiny = Board(spec_tiny, spec_tiny.goal_blocks)
n_tiny = len(b_tiny.legal_moves(3))
check(n_tiny == 0,
      f"H_1 step=3 无钩子模型自身即空（{n_tiny} 个）——3 单位平移在 "
      f"7 块盘上必断连通，是规模假象非几何；大步长用例因此取 H_2/H_3")

print()
print('== N0b 只挂 overlap（米字同款端点 SAT）：仍然误放行 ==')
for k in (1, 2, 3):
    spec = hex_spec(k, with_seam_clear=False, with_overlap=True)
    b = Board(spec, spec.goal_blocks)
    mv = b.legal_moves(1)
    check(len(mv) > 0,
          f"H_{k} step=1 仅 overlap → 仍放行 {len(mv)} 个移动"
          f"（端点干净，SAT 看不见半路碰撞）")

print()
print('== N1 挂 seam_clear：冻形（与物理真相一致） ==')
for k in (1, 2, 3):
    for step in (1, 2, 3):
        spec = hex_spec(k)
        b = Board(spec, spec.goal_blocks)
        mv = b.legal_moves(step)
        check(len(mv) == 0,
              f"H_{k} step={step} 全钩子 → 零合法移动（冻形）")
        check(frozen(b, step) is True, f"H_{k} step={step} frozen() 为真")
        # 锁死缝清单覆盖全部候选缝（不是大部分，是全部）
        cand = 0
        for fam in spec.seam_families:
            vals = [fam.rank_of(bl.point, bl.orient) for bl in b.blocks]
            cand += max(vals) - min(vals)
        locked = locked_seams(b)
        check(len(locked) == cand,
              f"H_{k} 候选缝 {cand} 条全部锁死（locked_seams 实报 "
              f"{len(locked)} 条）")
        check(all(x['reason'] == 'seam_clear' for x in locked),
              f"H_{k} 锁死原因全部落在 seam_clear 钩子上")

print()
print('== N1b 无钩子时预检层是全盲的（对照） ==')
spec_blind = hex_spec(2, with_seam_clear=False, with_overlap=False)
b_blind = Board(spec_blind, spec_blind.goal_blocks)
check(locked_seams(b_blind) == [],
      "无 seam_clear → locked_seams 报空（预检看不见锁死缝）")
check(frozen(b_blind, 1) is False,
      "无 seam_clear → frozen() 报可玩（预检误判）")

print()
print('== N2 地面真值：N0 的每个候选移动都半路碰撞 ==')
total_moves = 0
total_valid = 0
example = None
for k in (1, 2, 3):
    for step in (1, 2, 3):
        spec = hex_spec(k, with_seam_clear=False, with_overlap=False)
        b = Board(spec, spec.goal_blocks)
        mv_keys = set(b.keys)
        for m in b.legal_moves(step):
            total_moves += 1
            m_pts = [p for p, o in m.moved]
            moved_set = set(m.moved)
            r_pts = [bl.point for bl in b.blocks
                     if (bl.point, bl.orient) not in moved_set]
            wit = sweep_hit(m_pts, r_pts, m.direction, m.step)
            if wit is None:
                total_valid += 1
                if example is None:
                    example = (k, step, m)
check(total_valid == 0,
      f"地面真值：{total_moves} 个候选移动全部半路碰撞"
      f"（物理有效 {total_valid} 个）→ 蜂巢确实冻形")

# 示范一个见证：把第一个候选移动的碰撞对与 τ 区间打出来
spec_demo = hex_spec(2, with_seam_clear=False, with_overlap=False)
b_demo = Board(spec_demo, spec_demo.goal_blocks)
m0 = b_demo.legal_moves(1)[0]
moved_set = set(m0.moved)
r_pts = [bl.point for bl in b_demo.blocks
         if (bl.point, bl.orient) not in moved_set]
wit = sweep_hit([p for p, o in m0.moved], r_pts, m0.direction, m0.step)
if wit is not None:
    print(f"  见证：H_2 step=1 移动 {m0.family} t={m0.t} side={m0.side} "
          f"dir={m0.direction}（{len(m0.moved)} 块）")
    print(f"        块 {wit[0]} 右滑擦过 rest 块 {wit[1]}：第 {wit[2]+1} "
          f"个单位步、τ∈({float(wit[3]):.3f},{float(wit[4]):.3f}) 相撞")
    print(f"        （端点位置两块距恰好 √3——只接触不重叠，端点判据"
          f"完全看不见）")

print()
print('== N3 信息项：挖洞蜂巢也滑不动吗 ==')
for k, hole in ((2, (0, 0)), (3, (0, 0))):
    spec = hex_spec(k, with_seam_clear=False, with_overlap=False)
    blocks = tuple(bl for bl in spec.goal_blocks if bl.point != hole)
    b = Board(spec, blocks)
    n_valid = 0
    n_all = 0
    for m in b.legal_moves(1):
        n_all += 1
        moved_set = set(m.moved)
        r_pts = [bl.point for bl in b.blocks
                 if (bl.point, bl.orient) not in moved_set]
        if sweep_hit([p for p, o in m.moved], r_pts,
                     m.direction, m.step) is None:
            n_valid += 1
    print(f"  H_{k} 挖心 {len(blocks)} 块：引擎放行 {n_all} 个移动，"
          f"物理有效 {n_valid} 个")
    check(n_all > 0, f"H_{k} 挖心后引擎仍放行（{n_all} 个）——钩子依旧必需")
    check(n_valid == 0,
          f"H_{k} 挖心后物理有效移动仍为 0（砖墙咬合与空洞无关）")

print()
if failures:
    print(f"共 {len(failures)} 項失敗")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("全部通過")
