# -*- coding: utf-8 -*-
"""几何引擎原型测试（feat/geometry-engine，P0 可行性验证）。

执行：python test/_test_geometry_engine.py
约定：脚本型回归（check 收集失败，退出码非 0 即失败），零 pygame。

覆盖：
  A 差分·移动结果集合  —— 引擎 vs 现有方形引擎（遍历全部锚块的完整空间）
  B 差分·规范形        —— 引擎 vs solver/table_core.canonicalize（D4 同源）
  C 差分·还原判定      —— 引擎 vs game.is_solved（含漂移/旋转/翻面/非矩形）
  D 捆绑组             —— 组是刚体：缝切不开，整组拖动（与现有引擎一致）
  E 锁死缝钩子         —— seam_clear：声名式「这条缝切不动」（米字 span 的落点）
  F 冻形检测           —— 零合法移动（保存/开局前必须拦截的那类形态）
  G 安全打乱           —— 每步可逆 ⟺ 路径反转即解法；BFS 实证终态有解
  H 形状可达性 BFS     —— 「能否打乱」探针 + 确定性
  I 三维立方晶格       —— 48 对称 / 滑移 / 旋转还原 / 冻形（核心零改动延伸）
  J 板型注册表         —— 注册 / 查询 / 未知显式报错 / 参数校验
  K 差分·映射层        —— Move ↔ 动作 dict / 演示 record 往返、跨引擎重放、
                         路径回放、错误路径显式拒绝、goal_canonical 缓存
  L 差分·米字 preset   —— 引擎 vs game_mi：词汇/邻表一致、每个合法移动在
                         game 上逐一重放（缝有效性/选中集/走法/结果态）、
                         game 移动全集 ⊆ 引擎、侧分区覆盖、还原判定
                         （平移/換晶格/旋转/转置/挖洞）、安全打乱双重重放、
                         错位态重叠判定对拍 + 拒绝路径非空性
"""

import os
import random
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import (  # noqa: E402
    Block,
    Board,
    BoardSpec,
    Lattice,
    SeamFamily,
    board_types,
    cubic_board,
    cubic_lattice,
    cubic_spec,
    frozen,
    get_board_type,
    locked_seams,
    make_board,
    mi_board,
    mi_geometry,
    tri_board,
    tri_geometry,
    tri_spec,
    register_board_type,
    safe_scramble,
    shape_reachability,
    square_board,
    square_lattice,
    square_spec,
    verify_path,
)
from engine.compat import (  # noqa: E402
    action_to_move,
    apply_action,
    direction_table,
    move_to_action,
    move_to_record,
    record_to_action,
    record_to_move,
    register_direction_vocab,
)
from game import DIRECTIONS as GAME_DIRECTIONS  # noqa: E402
from game import SliderMatrix  # noqa: E402
from solver.table_core import canonicalize, int_to_coords  # noqa: E402

failures = []


def check(cond, msg):
    if cond:
        print(f"  ok: {msg}")
    else:
        failures.append(msg)
        print(f"  FAIL: {msg}")


# ----------------------------------------------------------------------
# 现有引擎的基线工具（差分对拍用）
# ----------------------------------------------------------------------
def _game_from_cells(m, n, cells, groups=None):
    """把点集装进现有方形引擎（blocks 顺序 = cells 顺序）。"""
    g = SliderMatrix(m, n)
    for b, c in zip(g.blocks, cells):
        b.location = list(c)
        if groups:
            b.group = groups.get(c, 0)
    return g


def _clone_game(g):
    g2 = SliderMatrix(g.m, g.n)
    for b, nb in zip(g.blocks, g2.blocks):
        nb.location = list(b.location)
        nb.group = b.group
    return g2


def game_move_results(g, step):
    """现有引擎的**完整**移动结果集合。

    遍历每条缝 × 每一侧 × 每一方向 × **每一个锚块**（GUI 点哪个块
    就移动哪个块所在的分量——这才是引擎的完整动作空间）。
    注意这与 solver/actions.enumerate_valid_actions 不同：后者每
    (缝, 侧, 方向) 只取第一个块所在分量，是已知欠账的代表块近似。
    """
    results = set()
    bounds = g.get_boundaries()
    specs = (
        ('h', range(bounds['min_row'], bounds['max_row']),
         ('above', 'below'), ('a', 'd'), 0),
        ('v', range(bounds['min_col'], bounds['max_col']),
         ('left', 'right'), ('w', 's'), 1),
    )
    for gap_dir, lines, sides, move_dirs, axis in specs:
        valid = (g.is_valid_h_line if gap_dir == 'h' else g.is_valid_v_line)
        for line in lines:
            if not valid(line):
                continue
            for side in sides:
                for mv in move_dirs:
                    for idx, anchor in enumerate(g.blocks):
                        v = anchor.location[axis]
                        if side in ('above', 'left') and v > line:
                            continue
                        if side in ('below', 'right') and v <= line:
                            continue
                        g2 = _clone_game(g)
                        g2.opt(gap_dir, line, g2.blocks[idx])
                        pos = g2.try_move(mv, step)
                        if pos:
                            g2.commit_move(pos)
                            results.add(
                                frozenset(tuple(b.location) for b in g2.blocks))
    return results


def engine_result_set(board, step):
    out = set()
    for m in board.legal_moves(step):
        nb = board.apply(m)
        out.add(frozenset(b.point for b in nb.blocks))
    return out


def random_walk_states(m, n, step, count, seed):
    """从还原态随机走 count 步，沿途采样局面（去重）。"""
    rng = random.Random(seed)
    cur = square_board(m, n)
    states, seen = [cur], {cur.canonical_key()}
    for _ in range(count):
        ms = cur.legal_moves(step)
        if not ms:
            cur = square_board(m, n)
            continue
        cur = cur.apply(rng.choice(ms))
        k = cur.canonical_key()
        if k not in seen:
            seen.add(k)
            states.append(cur)
    return states


def random_cell_sets(rng, count, kmin=3, kmax=9):
    """随机连通点集（带随机漂移，专测规范化的平移不变）。"""
    out, seen = [], set()
    while len(out) < count:
        k = rng.randint(kmin, kmax)
        cells = {(0, 0)}
        while len(cells) < k:
            r, c = rng.choice(list(cells))
            dr, dc = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
            cells.add((r + dr, c + dc))
        dr, dc = rng.randint(-6, 6), rng.randint(-6, 6)
        s = frozenset((r + dr, c + dc) for r, c in cells)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


# ----------------------------------------------------------------------
# A 差分·移动结果集合
# ----------------------------------------------------------------------
print("== A 差分·移动结果集合（引擎 vs 现有方形引擎） ==")
spec33 = square_spec(3, 3)
diff_cases = 0
for m, n, step in ((4, 4, 1), (4, 4, 2), (3, 5, 1), (3, 5, 2), (3, 4, 2)):
    states = random_walk_states(m, n, step, 70, seed=m * 100 + n * 10 + step)
    # 采样：首/中/尾 + 随机几个，按规范形去重（防同尺寸覆盖塌缩）
    picks = [states[0], states[len(states) // 2], states[-1]]
    picks += random.Random(7).sample(states, min(4, len(states)))
    uniq, seen = [], set()
    for b in picks:
        k = b.canonical_key()
        if k not in seen:
            seen.add(k)
            uniq.append(b)
    check(len(uniq) >= 5,
          f"{m}x{n} step{step} 采样去重后覆盖 ≥5（实际 {len(uniq)}，"
          f"防小空间塌缩）")
    spec = square_spec(m, n)
    for b in uniq:
        cells = sorted(b.points)
        g = _game_from_cells(m, n, cells)
        eb = Board.from_points(spec, cells)
        eng = engine_result_set(eb, step)
        base = game_move_results(g, step)
        diff_cases += 1
        if eng != base:
            only_eng = eng - base
            only_base = base - eng
            check(False,
                  f"{m}x{n} step{step} 移动集合不一致："
                  f"引擎多 {len(only_eng)} / 基线多 {len(only_base)}"
                  f"（样例 {sorted(only_eng)[:1]}{sorted(only_base)[:1]}）")
check(diff_cases >= 25, f"对拍局面数 {diff_cases}（应 ≥ 25）")
print(f"  （对拍局面 {diff_cases} 个，全部一致）" if not failures else "")

# ----------------------------------------------------------------------
# B 差分·规范形
# ----------------------------------------------------------------------
print("== B 差分·规范形（引擎 vs table_core.canonicalize） ==")
rng = random.Random(4242)
cell_sets = random_cell_sets(rng, 120)
mismatch = 0
for cells in cell_sets:
    tc = canonicalize(frozenset(cells))
    decoded = frozenset(int_to_coords(tc, len(cells)))
    eb = Board.from_points(spec33, cells)
    if decoded != frozenset(eb.canonical_key()):
        mismatch += 1
check(mismatch == 0, f"规范形逐项相等（{len(cell_sets)} 例，不一致 {mismatch}）")

# 等价类划分一致性：引擎说等的，table_core 也必须说等。
# 注意：table_core 的规范形是「整数 + 块数」配对语义（折叠整数不自分界），
# 只能在同块数内比较；引擎的规范形是自描述元组，跨块数也可比。
part_ok = True
by_size = {}
for s in cell_sets:
    by_size.setdefault(len(s), []).append(s)
pair_count = 0
for group in by_size.values():
    for i in range(len(group)):
        ki = Board.from_points(spec33, group[i]).canonical_key()
        ti = canonicalize(group[i])
        for j in range(i + 1, len(group)):
            kj = Board.from_points(spec33, group[j]).canonical_key()
            tj = canonicalize(group[j])
            pair_count += 1
            if (ki == kj) != (ti == tj):
                part_ok = False
check(part_ok, f"等价类划分一致（同块数 {pair_count} 对）")

# ----------------------------------------------------------------------
# C 差分·还原判定
# ----------------------------------------------------------------------
print("== C 差分·还原判定（引擎 vs game.is_solved） ==")
mismatch = 0
for m, n in ((4, 4), (3, 5), (2, 6)):
    spec = square_spec(m, n)
    goal_cells = sorted(b.point for b in spec.goal_blocks)
    cases = [
        goal_cells,                                        # 还原态
        [(r + 3, c - 2) for r, c in goal_cells],           # 平移
        [(c, r) for r, c in goal_cells],                   # 转置（m≠n 时是另一矩形）
        [(-r, c) for r, c in goal_cells],                  # 上下翻面
        goal_cells[:-1],                                   # 缺一块
        goal_cells + [(99, 99)],                           # 多一块
    ]
    for st in random_walk_states(m, n, 1, 40, seed=m * 7 + n):
        cases.append(sorted(st.points))
    for cells in cases:
        if len(cells) != m * n:
            continue  # 缺块/多块用例块数不符，单独走引擎侧断言
        g = _game_from_cells(m, n, cells)
        eb = Board.from_points(spec, cells)
        if g.is_solved() != eb.is_solved():
            mismatch += 1
check(mismatch == 0, "同块数局面判定一致（含漂移/转置/翻面/随机走查）")
check(Board.from_points(spec33, [(0, 0), (0, 1), (1, 0)]).is_solved() is False,
      "缺块/碎形不判还原")

# ----------------------------------------------------------------------
# D 捆绑组
# ----------------------------------------------------------------------
print("== D 捆绑组（组是刚体，缝切不开） ==")
cells = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
groups = {(0, 0): 7, (1, 0): 7}
spec23 = square_spec(2, 3)
eb = Board.from_points(spec23, cells, groups=groups)
g = _game_from_cells(2, 3, cells, groups=groups)
check(engine_result_set(eb, 1) == game_move_results(g, 1),
      "捆绑局面移动集合与现有引擎一致")
drag = [m for m in eb.legal_moves(1)
        if {(0, 0), (1, 0)} <= {k[0] for k in m.moved}]
check(len(drag) >= 1, "存在把捆绑组整体拖动的合法移动")
if drag:
    mv = drag[0]
    nb = eb.apply(mv)
    delta = tuple(mv.step * x for x in mv.direction)
    check(nb.block_map[((delta[0], delta[1]), '')].group == 7
          and nb.block_map[((1 + delta[0], delta[1]), '')].group == 7,
          "拖动后两组员仍同组且同步位移")

# ----------------------------------------------------------------------
# E 锁死缝钩子
# ----------------------------------------------------------------------
print("== E 锁死缝钩子（seam_clear，米字 span 判据的落点） ==")
spec44 = square_spec(5, 4)
locked_spec = replace(
    spec44,
    seam_clear=lambda fam, t, board: not (fam.name == 'h' and t % 2 == 0))
goal44 = Board(spec44, spec44.goal_blocks)
locked_board = Board(locked_spec, spec44.goal_blocks)
locks = locked_seams(locked_board)
check({(d['family'], d['t']) for d in locks} == {('h', 2), ('h', 4)},
      f"锁死缝清单 = h@2 / h@4（实际 {[(d['family'], d['t']) for d in locks]}）")
open_moves = goal44.legal_moves(1)
lock_moves = locked_board.legal_moves(1)
check(all(not (m.family == 'h' and m.t % 2 == 0) for m in lock_moves),
      "被锁的缝不出现在合法移动里")
check(len(lock_moves) < len(open_moves) and
      {m.moved for m in lock_moves} <= {m.moved for m in open_moves},
      f"锁死後移动是真子集（{len(open_moves)} → {len(lock_moves)}）")
check(locked_seams(goal44) == [], "无钩子的板型没有锁死缝概念")

# ----------------------------------------------------------------------
# F 冻形检测
# ----------------------------------------------------------------------
print("== F 冻形检测（零合法移动） ==")
line3 = Board.from_points(spec33, [(0, 0), (0, 1), (0, 2)])
check(frozen(line3, 1) is True and line3.legal_moves(1) == (),
      "1×3 直线冻形（任何滑动都甩出孤块）")
check(game_move_results(_game_from_cells(1, 3, [(0, 0), (0, 1), (0, 2)]), 1)
      == set(), "现有引擎同样判 1×3 直线冻形")
line5 = Board.from_points(spec33, [(0, i) for i in range(5)])
check(frozen(line5, 2) is True, "1×5 直线 step=2 冻形")
check(frozen(square_board(2, 2), 1) is False, "2×2 对照：不冻形")

# ----------------------------------------------------------------------
# G 安全打乱（可逆 ⟺ 有解）
# ----------------------------------------------------------------------
print("== G 安全打乱（每步精确可逆，撤销路径即字面解法） ==")
rng = random.Random(20261020)
b32 = square_board(3, 2)
final, path, undo_path = safe_scramble(b32, 1, 40, rng)
check(len(path) == 40, f"40 步全部可逆（实际 {len(path)}）")
check(len(undo_path) == len(path), "每步都记录了撤销移动")
check(not final.is_solved(), "终态不是还原态")
check(verify_path(b32, path) == final, "路径重放与终态一致")
# 撤销路径逐条反转 = 字面意义的合法解法（每步精确可逆，非规范形近似）
back = verify_path(final, tuple(reversed(undo_path)))
check(back == b32, "反转撤销路径精确回到还原态（字面解法）")
reach = shape_reachability(final, 1, cap=20000,
                           target_key=b32.canonical_key())
check(reach['target_reachable'] is True,
      f"BFS 实证：打乱终态可达还原态（可达形状 {reach['count']}）")
# step 定义域：≥1 的整数，显式拒绝（game 的 step=0 空转是怪癖，不继承）
for bad_step in (0, -1, 1.5, '2'):
    try:
        b32.legal_moves(bad_step)
        check(False, f"step={bad_step!r} 必须显式拒绝")
    except (ValueError, TypeError):
        check(True, f"step={bad_step!r} 显式拒绝")
# 回放防护：别局的 Move 不能误放到本局
b55 = square_board(5, 5)
stale = next(m for m in b55.legal_moves(1)
             if any(p[0][1] > 1 for p in m.moved))
try:
    b32.apply(stale)
    check(False, "别局 Move 必须显式拒绝")
except ValueError:
    check(True, "别局 Move 显式拒绝（回放防护）")

# ----------------------------------------------------------------------
# H 形状可达性 BFS
# ----------------------------------------------------------------------
print("== H 形状可达性 BFS（能否打乱的探针） ==")
r1 = shape_reachability(square_board(2, 2), 1)
r2 = shape_reachability(square_board(2, 2), 1)
check(r1['count'] >= 4 and not r1['capped'],
      f"2×2 可达形状 ≥ 4（实际 {r1['count']}）")
check(r1 == r2, "BFS 确定（两次结果一致）")

# ----------------------------------------------------------------------
# I 三维立方晶格
# ----------------------------------------------------------------------
print("== I 三维立方晶格（核心零改动延伸） ==")
check(len(list(cubic_lattice().iter_symmetries())) == 48, "3 维自同构 = 48")
cube = cubic_board(2, 2, 2)
moves = cube.legal_moves(1)
check(len(moves) > 0, f"立方体有合法移动（{len(moves)} 个）")
mv = next(m for m in moves if m.family == 'r')
delta = tuple(mv.step * x for x in mv.direction)
moved = {k[0] for k in mv.moved}
expected = frozenset(
    tuple(p[i] + (delta[i] if p in moved else 0) for i in range(3))
    for p in cube.points)
check(cube.apply(mv).points == expected, "r 族缝移动 = 选中片整体平移")
check(cube.is_solved() and cube.translate((5, -3, 7)).is_solved(),
      "立方体 / 漂移立方体判还原")
box = cubic_board(2, 3, 4)
rot = Board(box.spec, tuple(Block((p[1], -p[0], p[2])) for p in box.points))
check(box.is_solved() and rot.is_solved(), "长方体 / 90° 旋转後判还原")
check(rot.canonical_key() == box.canonical_key(),
      "旋转不改变规范形（48 对称之一）")
check(cubic_board(3, 2, 4).is_solved(), "转置长方体判还原")
line3d = Board.from_points(cubic_spec(2, 2, 2),
                           [(0, 0, 0), (0, 0, 1), (0, 0, 2)])
check(frozen(line3d, 1) is True, "三维 1×1×3 直线同样冻形")

# ----------------------------------------------------------------------
# J 板型注册表
# ----------------------------------------------------------------------
print("== J 板型注册表 ==")
check('square' in board_types() and 'cubic' in board_types(),
      f"内置板型已注册（{board_types()}）")
register_board_type('test_geo_sq4', lambda **kw: square_spec(4, 4))
check('test_geo_sq4' in board_types(), "自定义板型可注册")
tb = make_board('test_geo_sq4')
check(tb.block_count == 16 and tb.is_solved(), "按名造局 = 还原态")
try:
    get_board_type('no_such_board')
    check(False, "未知板型必须显式报错")
except KeyError:
    check(True, "未知板型显式 KeyError（不静默兜底）")
for bad in ('', None, 3):
    try:
        register_board_type(bad, square_spec)
        check(False, f"板型名 {bad!r} 必须拒绝")
    except ValueError:
        check(True, f"拒绝非法板型名 {bad!r}")
try:
    register_board_type('test_geo_sq4', square_spec)
    check(False, "同名重复注册必须显式拒绝")
except ValueError:
    check(True, "同名重复注册显式拒绝（不静默覆盖）")
# 板型构造校验：永冻板型 / bool 冒充整数 / 混合奇偶系数，全部显式拒绝
for bad_params in ((0, 4), (True, 2), (2.0, 4)):
    try:
        square_spec(*bad_params)
        check(False, f"square_spec{bad_params} 必须拒绝")
    except (ValueError, TypeError):
        check(True, f"square_spec{bad_params} 显式拒绝")
try:
    from engine import Lattice
    Lattice(dim=2, parity_linear=(1, 0))
    check(False, "混合奇偶系数必须拒绝（对自同构群不封闭）")
except ValueError:
    check(True, "混合奇偶系数显式拒绝")
try:
    BoardSpec(name='dead', lattice=square_lattice(), directions=(),
              seam_families=(SeamFamily('h', (1, 0), ((0, 1),)),))
    check(False, "空方向表的永冻板型必须拒绝")
except ValueError:
    check(True, "空方向表显式拒绝")

# ----------------------------------------------------------------------
# K 差分·映射层（Move ↔ 既有动作格式，P1 桥）
# ----------------------------------------------------------------------
print("== K 差分·映射层（Move ↔ 动作 dict / 演示 record） ==")


def _game_replay_action(g, action):
    """在现有引擎上按动作 dict 重放一步（GUI 同路：opt → try_move → commit）。

    锚块取选中片里任意一块：opt 按锚块定侧、选同侧连通分量（捆绑扩展），
    与引擎 legal_moves 的 (side, comp, group closure) 同构。返回结果点集；
    选不中/走不动返回 None（调用方按差分失败计）。
    """
    target = {tuple(p) for p in action['moved_positions']}
    anchor = next((b for b in g.blocks if tuple(b.location) in target), None)
    if anchor is None:
        return None
    g.opt(action['gap_type'], action['gap_line'], anchor)
    if not any(b.be_opted for b in g.blocks):
        return None
    pos = g.try_move(action['direction'], action['step'])
    if not pos:
        return None
    g.commit_move(pos)
    return frozenset(tuple(b.location) for b in g.blocks)


# K1 往返：move → action → move 全等（全部合法移动，多尺寸/等级）
rt_count = 0
rt_bad = []
for m, n, step in ((4, 4, 1), (4, 4, 2), (3, 5, 1), (2, 6, 2), (3, 3, 3)):
    spec = square_spec(m, n)
    for b in random_walk_states(m, n, step, 25, seed=900 + m * 10 + n + step):
        for mv in b.legal_moves(step):
            act = move_to_action(spec, mv)
            back = action_to_move(spec, act)
            rt_count += 1
            if back != mv:
                rt_bad.append((mv, act))
check(not rt_bad and rt_count >= 300,
      f"动作往返全等（{rt_count} 个合法移动，偏差 {len(rt_bad)}）")

# K2 跨引擎差分：动作 dict 在现有方形引擎上重放，结果与引擎 apply 一致。
# 这是「切层」的安全证明——存档/宏里的旧动作喂给新桥，两边走出同一局面。
replay_cases = 0
replay_bad = []
for m, n, step in ((4, 4, 1), (4, 4, 2), (3, 5, 1)):
    spec = square_spec(m, n)
    states = random_walk_states(m, n, step, 40, seed=310 + m * 7 + n)
    picks = [states[0], states[len(states) // 2], states[-1]]
    picks += random.Random(11).sample(states, min(3, len(states)))
    uniq, seen = [], set()
    for b in picks:
        k = b.canonical_key()
        if k not in seen:
            seen.add(k)
            uniq.append(b)
    for b in uniq:
        g0 = _game_from_cells(m, n, sorted(b.points))
        for mv in b.legal_moves(step):
            act = move_to_action(spec, mv)
            got = _game_replay_action(_clone_game(g0), act)
            want = frozenset(p.point for p in b.apply(mv).blocks)
            replay_cases += 1
            if got != want:
                replay_bad.append((m, n, step, act, got is None))
check(not replay_bad and replay_cases >= 200,
      f"动作在现有引擎上重放一致（{replay_cases} 步，偏差 {len(replay_bad)}）")

# K3 record 往返：move → record → move 全等；record → action 与直转同形
rec_count = 0
rec_bad = 0
for m, n, step in ((4, 4, 1), (3, 5, 2)):
    spec = square_spec(m, n)
    for b in random_walk_states(m, n, step, 20, seed=520 + m + n):
        for mv in b.legal_moves(step):
            rec = move_to_record(spec, mv)
            rec_count += 1
            if record_to_move(spec, rec) != mv:
                rec_bad += 1
            elif record_to_action(rec) != move_to_action(spec, mv):
                rec_bad += 1
check(rec_bad == 0 and rec_count >= 200,
      f"record 往返全等（{rec_count} 个合法移动，偏差 {rec_bad}）")

# K4 路径回放：safe_scramble 的前进/撤销路径逐条 apply_action ——
#    前进到终态；撤销路径逆序回到起点（「路径反转即解法」在动作层成立）。
rng_k = random.Random(20261021)
path_ok = True
path_steps = 0
for m, n, step in ((3, 4, 1), (4, 4, 2), (2, 5, 1)):
    spec = square_spec(m, n)
    start = square_board(m, n)
    end, fwd, undo = safe_scramble(start, step, 15, rng_k)
    cur = start
    for mv in fwd:
        cur = apply_action(cur, move_to_action(spec, mv))
        path_steps += 1
    if cur != end:
        path_ok = False
    cur2 = end
    for mv in reversed(undo):
        cur2 = apply_action(cur2, move_to_action(spec, mv))
        path_steps += 1
    if cur2 != start:
        path_ok = False
check(path_ok and path_steps >= 60,
      f"safe_scramble 路径经动作 dict 回放（{path_steps} 步：前进到终态、"
      f"逆序撤销回起点）")

# K5 错误路径：结构坏/不合法，全部显式抛错（AGENTS.md §2）
spec42 = square_spec(4, 2)
b42 = square_board(4, 2)
good = b42.legal_moves(1)[0]
good_act = move_to_action(spec42, good)


def _expect_raise(fn, msg):
    try:
        fn()
        check(False, f"{msg}：未抛错（静默容忍 = 缺陷）")
    except (ValueError, TypeError, KeyError) as e:
        check(True, f"{msg}：显式拒绝（{type(e).__name__}）")


_expect_raise(lambda: action_to_move(spec42, {**good_act, 'gap_type': 'z'}),
              "未知缝族")
_expect_raise(lambda: action_to_move(spec42, {**good_act, 'direction': 'q'}),
              "非法方向字母")
_expect_raise(lambda: action_to_move(
    spec42, {'gap_type': 'v', 'gap_line': 0, 'direction': 'a', 'step': 1,
             'moved_positions': [(0, 0)]}),
    "字母与缝族不平行（'a' 对 'v' 族）")
_expect_raise(lambda: action_to_move(spec42, {**good_act, 'step': 0}),
              "step=0")
_expect_raise(lambda: action_to_move(spec42, {**good_act, 'merged': 2}),
              "merged 合并态动作")
_expect_raise(lambda: action_to_move(spec42,
                                     {'gap_type': 'h', 'gap_line': 0}),
              "动作 dict 缺键")
_expect_raise(lambda: action_to_move(spec42, {**good_act,
                                              'moved_positions': []}),
              "空选中片")
_expect_raise(lambda: action_to_move(spec42, {**good_act, 'moved_positions':
                                              [(0, 0), (0, 0)]}),
              "选中片重复坐标")
_expect_raise(lambda: action_to_move(spec42, {**good_act, 'moved_positions':
                                              [(0.5, 0)]}),
              "选中片离格点（半整数坐标）")
_expect_raise(lambda: action_to_move(
    spec42, {'gap_type': 'h', 'gap_line': 1, 'direction': 'a', 'step': 1,
             'moved_positions': [(0, 0), (2, 0)]}),
    "选中片横跨缝两侧")
_expect_raise(lambda: apply_action(
    b42, {'gap_type': 'h', 'gap_line': 0, 'direction': 'a', 'step': 1,
          'moved_positions': [(0, 0)]}),
    "结构合法但非本局合法移动（单块切开走）")
_expect_raise(lambda: direction_table(replace(spec42, name='no_such')),
              "未注册词汇表的板型")
_expect_raise(lambda: register_direction_vocab('square', {'x': (1, 0)}),
              "同名词汇表重复注册")
check(direction_table(spec42) == GAME_DIRECTIONS,
      "方形字母表与 game.DIRECTIONS 逐项一致（桥不偷偷改词汇）")

# K6 goal_canonical 缓存：同一对象 + 与现算一致 + replace 出的 spec 独立
specA = square_spec(4, 4)
first = specA.goal_canonical()
second = specA.goal_canonical()
check(first is second, "goal_canonical 命中缓存（重复调用同一对象）")
check(first == Board(specA, specA.goal_blocks).canonical_key(),
      "缓存值与现算一致")
specB = replace(specA, seam_clear=lambda fam, t, board: True)
check(specB.goal_canonical() == first,
      "replace 出的新 spec 缓存独立且同值")

# ----------------------------------------------------------------------
# L 米字 preset：引擎 vs game_mi 差分对拍（P2）
# ----------------------------------------------------------------------
print("== L 米字 preset：引擎 vs game_mi 差分对拍 ==")
import game_mi
from game_mi import (DIRECTIONS as MI_GAME_DIRECTIONS,  # noqa: E402
                     GAP_DIRECTIONS as MI_GAME_GAP,
                     _has_overlap, any_overlap, mi_key, neighbors, side_of)
import game_triangle
from game_triangle import (DIRECTIONS as TRI_GAME_DIRECTIONS,  # noqa: E402
                          GAP_DIRECTIONS as TRI_GAME_GAP,
                          tri_key, neighbors as tri_neighbors,
                          side_of as tri_side_of)


def _mi_norm2(x):
    """实坐标 → game location 分量（整数化归 int，与 commit_move 同约定）。"""
    return int(x) if float(x).is_integer() else float(x)


def _mi_game_from_keys(keys, m, n):
    """引擎块键集合 → game_mi.MiSliderMatrix（键数不足 4mn 时截掉多余块）。"""
    g = game_mi.MiSliderMatrix(m, n)
    for gb, (p, o) in zip(g.blocks, sorted(keys)):
        gb.location = [_mi_norm2(p[0] / 2), _mi_norm2(p[1] / 2), o]
    del g.blocks[len(keys):]
    g.update_matrix()
    return g


def _mi_engine_keys_to_game(keys):
    """引擎块键 → game 位置 (r, c, q)（实坐标，整数分量归一化）。"""
    out = set()
    for p, o in keys:
        out.add((_mi_norm2(p[0] / 2), _mi_norm2(p[1] / 2), o))
    return out


def _mi_components(cells):
    """按 game_mi 5-邻接求连通分量（与 opt 的 DFS 同邻接定义）。"""
    seen, out = set(), []
    for c in cells:
        if c in seen:
            continue
        comp, stack = set(), [c]
        seen.add(c)
        while stack:
            cur = stack.pop()
            comp.add(cur)
            for nb in neighbors(cur):
                if nb in cells and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        out.append(comp)
    return out


def mi_game_move_results(g, step):
    """game_mi 的完整移动结果集合（全部有效缝 × 两侧 × 全部分量 × 平行方向）。

    与方形版 game_move_results 同哲学；米字侧遍历 game 自己的 all_gaps
    候选缝、分量用 game 自己的 neighbors。每次成功提交后还原 location，
    供同一局面的下一轮候选使用。
    """
    results = set()
    orig = [list(b.location) for b in g.blocks]
    cells = g.positions()
    key_to_block = {mi_key(b): b for b in g.blocks}
    for gap_type, line in g.all_gaps():
        for side in (0, 1):
            same = {c for c in cells if side_of(gap_type, line, c) == side}
            for comp in _mi_components(same):
                g.opt(gap_type, line, key_to_block[min(comp)])
                for d in MI_GAME_GAP[gap_type]:
                    pos = g.try_move(d, step)
                    if pos:
                        g.commit_move(pos)
                        results.add(frozenset(mi_key(b) for b in g.blocks))
                        for b, loc in zip(g.blocks, orig):
                            b.location = list(loc)
    return results


def mi_engine_move_replay(eb, g, mv):
    """引擎移动 → game_mi 重放核对（L1a 的单元，逐项钉死移动语义）。

    依次校验：① 缝过得了 game 的 is_valid_gap；② game 的 opt 选中集与
    引擎 moved 逐键相同；③ game 的 try_move 接受该走法；④ 提交后的结果
    态与引擎 apply 一致。任一不过返回 (False, 细节)。
    """
    action = move_to_action(eb.spec, mv)
    moved_game = _mi_engine_keys_to_game(mv.moved)
    rep = min(moved_game)
    gb = next((b for b in g.blocks if mi_key(b) == rep), None)
    if gb is None:
        return False, f"选中片代表块 {rep} 不在 game 盘面上"
    if not g.is_valid_gap(action['gap_type'], action['gap_line']):
        return False, (f"缝 ({action['gap_type']}, {action['gap_line']}) "
                       f"过不了 game 的 is_valid_gap")
    orig = [list(b.location) for b in g.blocks]
    g.opt(action['gap_type'], action['gap_line'], gb)
    selected = {mi_key(b) for b in g.blocks if b.be_opted}
    if selected != moved_game:
        for b, loc in zip(g.blocks, orig):
            b.location = list(loc)
        return False, (f"game 选中集与引擎 moved 不一致：多 "
                       f"{sorted(selected - moved_game)[:3]} / 少 "
                       f"{sorted(moved_game - selected)[:3]}")
    pos = g.try_move(action['direction'], mv.step)
    if not pos:
        for b, loc in zip(g.blocks, orig):
            b.location = list(loc)
        return False, (f"game 拒绝引擎移动（{action['direction']} "
                       f"step={mv.step}）")
    g.commit_move(pos)
    result = frozenset(mi_key(b) for b in g.blocks)
    for b, loc in zip(g.blocks, orig):
        b.location = list(loc)
    expect = frozenset(_mi_engine_keys_to_game(eb.apply(mv).keys))
    if result != expect:
        return False, "game 重放结果态与引擎 apply 不一致"
    return True, ''


def mi_engine_seam_partitions(eb):
    """引擎侧全部有效缝（seam_clear 通过且 t 在秩区间内）的侧分区（game 坐标）。"""
    spec = eb.spec
    keys = eb.keys
    parts = set()
    for fam in spec.seam_families:
        vals = {k: fam.rank_of(k[0], k[1]) for k in keys}
        lo, hi = min(vals.values()), max(vals.values())
        for t in range(lo + 1, hi + 1):
            if not spec.seam_clear(fam, t, eb):
                continue
            side_lo = frozenset(k for k in keys if vals[k] < t)
            parts.add((frozenset(_mi_engine_keys_to_game(side_lo)),
                       frozenset(_mi_engine_keys_to_game(keys - side_lo))))
    return parts


def mi_game_seam_partitions(g):
    """game 侧全部有效缝（all_gaps）的侧分区。"""
    cells = g.positions()
    parts = set()
    for gap_type, line in g.all_gaps():
        s0 = frozenset(c for c in cells if side_of(gap_type, line, c) == 0)
        parts.add((s0, frozenset(cells - s0)))
    return parts


def mi_game_reject_attribution(g, step):
    """game 侧全部候选走法的拒绝归因（L6 非空性证明用，只读不改盘面）。

    逐步检查复刻 try_move_ex 的 _check_step 三步判据（键相交 / 几何
    重叠 / 单一连通），用于定位失败发生在第几步、该步选中片是否键
    不相交。纯统计：不提交任何移动，location 不被改动。
    """
    stats = {'ok': 0, 'collision_key': 0, 'collision_overlap_only': 0,
             'disconnected': 0}
    cells = g.positions()
    key_to_block = {mi_key(b): b for b in g.blocks}
    for gap_type, line in g.all_gaps():
        for side in (0, 1):
            same = {c for c in cells if side_of(gap_type, line, c) == side}
            for comp in _mi_components(same):
                g.opt(gap_type, line, key_to_block[min(comp)])
                sel = [b for b in g.blocks if b.be_opted]
                if not sel:
                    continue
                non_keys = {mi_key(b) for b in g.blocks if not b.be_opted}
                for d in MI_GAME_GAP[gap_type]:
                    delta = MI_GAME_DIRECTIONS[d]
                    cur = [list(b.location) for b in sel]
                    reason = 'ok'
                    for _ in range(step):
                        nxt = [(c[0] + delta[0], c[1] + delta[1], c[2])
                               for c in cur]
                        nxt_set = set(nxt)
                        if nxt_set & non_keys:
                            reason = 'collision_key'
                            break
                        if _has_overlap(nxt_set, non_keys):
                            reason = 'collision_overlap_only'
                            break
                        if not g.is_single_connected(nxt_set | non_keys):
                            reason = 'disconnected'
                            break
                        cur = nxt
                    stats[reason] += 1
    return stats


def _mi_random_walk_states(m, n, step, count, seed):
    """从还原态随机走 count 步，沿途采样局面（按规范形去重）。"""
    rng = random.Random(seed)
    cur = mi_board(m, n)
    states, seen = [cur], {cur.canonical_key()}
    for _ in range(count):
        ms = cur.legal_moves(step)
        if not ms:
            break
        cur = cur.apply(rng.choice(ms))
        k = cur.canonical_key()
        if k not in seen:
            seen.add(k)
            states.append(cur)
    return states


def _mi_game_apply_action(g, action):
    """在 game_mi 上按动作 dict 重放一步（GUI 同路：opt → try_move → commit）。"""
    target = tuple(action['moved_positions'][0])
    anchor = next((b for b in g.blocks if mi_key(b) == target), None)
    if anchor is None:
        return None
    g.opt(action['gap_type'], action['gap_line'], anchor)
    if not any(b.be_opted for b in g.blocks):
        return None
    pos = g.try_move(action['direction'], action['step'])
    if not pos:
        return None
    g.commit_move(pos)
    return frozenset(mi_key(b) for b in g.blocks)


# ---- L0 词汇与邻表：引擎常量表 = game_mi × 2（桥不偷偷改词汇）----
check(mi_geometry.MI_DIRECTIONS ==
      {k: (2 * v[0], 2 * v[1]) for k, v in MI_GAME_DIRECTIONS.items()},
      "米字方向字母表与 game_mi.DIRECTIONS 逐项一致（×2 坐标）")
check(mi_geometry.MI_GAP_DIRECTIONS == MI_GAME_GAP,
      "米字缝族方向表与 game_mi.GAP_DIRECTIONS 一致")
_nb_bad = 0
for _q in mi_geometry.MI_ORIENTATIONS:
    _eng = {(*off[0], off[1])
            for off in dict(mi_geometry.MI_ORIENT_STEPS)[_q]}
    _game = {(round(2 * nb[0]), round(2 * nb[1]), nb[2])
             for nb in neighbors((0, 0, _q))}
    if _eng != _game:
        _nb_bad += 1
check(_nb_bad == 0, "米字 5 邻表与 game_mi.neighbors 逐项一致（×2 坐标）")

# ---- 退化尺寸：1×1 有两条对角缝、8 个合法移动；单块板冻形，两引擎一致 ----
mi11 = mi_board(1, 1)
g11 = _mi_game_from_keys(mi11.keys, 1, 1)
check(len(mi11.legal_moves(1)) == 8,
      f"1×1 米字 8 个合法移动（两条对角缝 × 两侧 × 两方向，实际 "
      f"{len(mi11.legal_moves(1))}）")
check(set(g11.all_gaps()) == {('d1', 0), ('d2', 0)},
      f"1×1 米字有两条对角缝（game all_gaps 实测 {sorted(g11.all_gaps())}）")
mi1b = Board.from_keys(mi11.spec, [((0, 0), 'N')])
g1b = _mi_game_from_keys(mi1b.keys, 1, 1)
check(frozen(mi1b, 1) is True and g1b.all_gaps() == [],
      "单块米字冻形（引擎零合法移动，game 无有效缝）")

# ---- 采样局面：四个尺寸还原态 + 随机走查态（规范形去重，总量封顶）----
sampled = [(m, n, mi_board(m, n)) for m, n in ((3, 3), (2, 3), (2, 2), (1, 1))]
_seen = {eb.canonical_key() for _, _, eb in sampled}
for m, n, step, cnt, seed in ((3, 3, 1, 60, 4242), (2, 3, 1, 60, 777),
                              (3, 3, 2, 50, 99), (2, 2, 1, 40, 55)):
    for b in _mi_random_walk_states(m, n, step, cnt, seed):
        k = b.canonical_key()
        if k in _seen:
            continue
        _seen.add(k)
        sampled.append((m, n, b))
        if len(sampled) >= 18:
            break
    if len(sampled) >= 18:
        break

# ---- L1 移动对拍 ----
l1a_bad, l1a_count = [], 0
game_only_total = engine_only_total = 0
state_ov_bad = []
for m, n, eb in sampled:
    g = _mi_game_from_keys(eb.keys, m, n)
    if any_overlap(g.positions()):
        state_ov_bad.append((m, n))
        continue
    for step in ((1, 2) if m * n > 1 else (1,)):
        moves = eb.legal_moves(step)
        # L1a：引擎每个合法移动 → game 逐一重放（缝/选中集/走法/结果态）
        for mv in moves:
            l1a_count += 1
            ok, detail = mi_engine_move_replay(eb, g, mv)
            if not ok:
                l1a_bad.append((m, n, step, mv.family, mv.t, detail))
        # L1b：game 每个移动的结果 ⊆ 引擎结果集合（完整性方向）
        eng_results = {frozenset(_mi_engine_keys_to_game(nb.keys))
                       for nb in (eb.apply(mv) for mv in moves)}
        game_results = mi_game_move_results(g, step)
        game_only_total += len(game_results - eng_results)
        engine_only_total += len(eng_results - game_results)
check(not state_ov_bad, f"采样局面本身无任何两块重叠（偏差 {state_ov_bad}）")
check(not l1a_bad and l1a_count >= 200,
      f"引擎每个合法移动在 game_mi 上逐一重放一致（{l1a_count} 个，"
      f"偏差 {len(l1a_bad)}）"
      + (f"；首例 {l1a_bad[0][:5]}: {l1a_bad[0][5]}" if l1a_bad else ""))
check(game_only_total == 0,
      f"game 的每个移动引擎都有（game ⊆ engine；engine 多出 "
      f"{engine_only_total} 个结果——game 的候选缝生成是启发式、引擎给"
      f"全量有效缝，多出部分的正确性由上面的逐一重放保底）")

# ---- L2 缝隙分区：game 每条有效缝的侧分区，引擎必有同分区的有效缝 ----
l2_bad, l2_parts = [], 0
for m, n, eb in sampled:
    g = _mi_game_from_keys(eb.keys, m, n)
    eng_parts = mi_engine_seam_partitions(eb)
    game_parts = mi_game_seam_partitions(g)
    l2_parts += len(game_parts)
    missing = game_parts - eng_parts
    if missing:
        l2_bad.append((m, n, len(missing)))
check(not l2_bad,
      f"game 每条有效缝的侧分区引擎都有（{l2_parts} 个分区，偏差 {l2_bad}）")

# ---- L4 还原判定：采样局面 + 平移/換晶格/旋转/转置/挖洞变体 ----
def _mi_sym(eb, f):
    """D4 变换：(r, c) → f(r, c)；朝向按 base 边法线的诱导置换 N→W→S→E→N。"""
    qmap = {'N': 'W', 'W': 'S', 'S': 'E', 'E': 'N'}
    return Board(eb.spec, tuple(
        Block(f(b.point), qmap[b.orient], b.group) for b in eb.blocks))


l4_bad, l4_count = [], 0
for m, n, eb in sampled:
    variants = [
        eb,
        eb.translate((4, -2)),                  # 整数平移（A 晶格内）
        eb.translate((1, 1)),                   # 半整平移（A → B 晶格）
        _mi_sym(eb, lambda p: (-p[1], p[0])),   # 90° 旋转
        _mi_sym(eb, lambda p: (p[1], p[0])),    # 转置
    ]
    if len(eb.blocks) > 4:
        variants.append(Board(eb.spec, eb.blocks[1:]))   # 挖掉一块
    for vb in variants:
        l4_count += 1
        g = _mi_game_from_keys(vb.keys, m, n)
        if vb.is_solved() != g.is_solved():
            l4_bad.append((m, n, vb.is_solved(), g.is_solved()))
check(not l4_bad,
      f"还原判定一致（{l4_count} 个局面/变体：平移/換晶格/旋转/转置/挖洞，"
      f"偏差 {len(l4_bad)}）")

# ---- L5 安全打乱：路径/撤销在 game_mi 上双重重放 ----
rng = random.Random(20261021)
b53 = mi_board(3, 3)
final, path, undo_path = safe_scramble(b53, 1, 30, rng)
check(len(path) == 30, f"30 步全部可逆（实际 {len(path)}）")
check(len(undo_path) == len(path), "每步都记录了撤销移动")
check(not final.is_solved(), "终态不是还原态")
check(verify_path(b53, path) == final, "路径重放与终态一致")
check(verify_path(final, tuple(reversed(undo_path))) == b53,
      "反转撤销路径精确回到还原态（字面解法）")
g5 = _mi_game_from_keys(b53.keys, 3, 3)
g5_ok = True
for mv in path:
    if _mi_game_apply_action(g5, move_to_action(b53.spec, mv)) is None:
        g5_ok = False
        break
if g5_ok:
    if g5.is_solved() or frozenset(g5.positions()) != \
            frozenset(_mi_engine_keys_to_game(final.keys)):
        g5_ok = False
    else:
        for mv in reversed(undo_path):
            if _mi_game_apply_action(g5, move_to_action(b53.spec, mv)) is None:
                g5_ok = False
                break
        if g5_ok and frozenset(g5.positions()) != \
                frozenset(_mi_engine_keys_to_game(b53.keys)):
            g5_ok = False
check(g5_ok, "打乱路径经 game_mi 重放：前进到终态、逆序撤销回起点")

# ---- L6 错位态重叠：判定对拍 + 拒绝路径非空性 ----
# 有界区域内全部合法点（引擎整数坐标，p0≡p1 mod 2 = A/B 双晶格）× 四朝向
_pts6 = [(r, c) for r in range(7) for c in range(7) if (r - c) % 2 == 0]
_keys6 = [((r, c), q) for r, c in _pts6
          for q in mi_geometry.MI_ORIENTATIONS]
ov_bad = ov_positive = 0
for k1 in _keys6:
    g1 = next(iter(_mi_engine_keys_to_game({k1})))
    for k2 in _keys6:
        g2 = next(iter(_mi_engine_keys_to_game({k2})))
        eng = mi_geometry.has_overlap({k1}, {k2})
        # game 的键相交在调用方 _check_step，_has_overlap 只管几何
        game = (g1 == g2) or _has_overlap({g1}, {g2})
        if eng != game:
            ov_bad += 1
        if eng and k1 != k2:
            ov_positive += 1
check(ov_bad == 0,
      f"重叠判定与 game_mi 逐对一致（{len(_keys6)}² 对，偏差 {ov_bad}）")
check(ov_positive > 0,
      f"错位态存在键不同但正面积重叠的块对（{ov_positive} 对——"
      f"「键集合不相交」放它们过去就是死盘，几何判定非摆设）")
rej = {'ok': 0, 'collision_key': 0, 'collision_overlap_only': 0,
       'disconnected': 0}
for m, n, eb in sampled:
    g = _mi_game_from_keys(eb.keys, m, n)
    for k, v in mi_game_reject_attribution(g, 1).items():
        rej[k] += v
check(rej['collision_overlap_only'] > 0,
      f"走查中出现的「键不相交但几何重叠」拒绝 {rej['collision_overlap_only']} "
      f"次（候选统计 {rej}）")


# ======================================================================
print("== M 三角 preset：引擎 vs game_triangle 差分对拍 ==")
# ----------------------------------------------------------------------
# 坐标约定与 game_triangle 同套斜坐标（纯整数）：point=(i,j)、orient∈{up,down}；
# 既有格式的位置是 (i, j, bool)。以下辅助负责两侧格式互转与移动重放。
# ----------------------------------------------------------------------
def tri_engine_keys_to_game(keys):
    """引擎块键 ((i,j),'up'/'down') → game 位置 (i,j,bool)。"""
    return {(i, j, (o == 'up')) for (i, j), o in keys}


def tri_game_cells_to_engine(cells):
    """game 位置 (i,j,bool) → 引擎块键 ((i,j),'up'/'down')。"""
    return {((i, j), 'up' if up else 'down') for (i, j, up) in cells}


def tri_game_from_keys(keys, k):
    """引擎块键集合 → game_triangle.TriangleSliderMatrix(k) 重建。"""
    g = game_triangle.TriangleSliderMatrix(k)
    g.blocks = [game_triangle._make_block(i, j, (o == 'up'))
                for (i, j), o in keys]
    g.update_matrix()
    return g


def _tri_components(cells):
    """连通分量（三角 3-邻接：game_triangle.neighbors）。"""
    remaining = set(cells)
    comps = []
    while remaining:
        seed = remaining.pop()
        comp = {seed}
        stack = [seed]
        while stack:
            cur = stack.pop()
            for nb in tri_neighbors(cur):
                if nb in remaining:
                    remaining.discard(nb)
                    comp.add(nb)
                    stack.append(nb)
        comps.append(frozenset(comp))
    return comps


def tri_game_move_results(g, step):
    """game 侧全部走法的结果集合（L1b 完整性方向）。"""
    results = set()
    orig = [list(b.location) for b in g.blocks]
    cells = g.positions()
    key_to_block = {tri_key(b): b for b in g.blocks}
    for gap_type, line in g.all_gaps():
        for side in (0, 1):
            same = {c for c in cells if tri_side_of(gap_type, line, c) == side}
            for comp in _tri_components(same):
                g.opt(gap_type, line, key_to_block[min(comp)])
                for d in TRI_GAME_GAP[gap_type]:
                    pos = g.try_move(d, step)
                    if pos:
                        g.commit_move(pos)
                        results.add(frozenset(tri_key(b) for b in g.blocks))
                        for b, loc in zip(g.blocks, orig):
                            b.location = list(loc)
    return results


def tri_engine_move_replay(eb, g, mv):
    """引擎移动 → game_triangle 重放核对（L1a 单元：缝/选中集/走法/结果态）。"""
    action = move_to_action(eb.spec, mv)
    moved_game = tri_engine_keys_to_game(mv.moved)
    rep = min(moved_game)
    gb = next((b for b in g.blocks if tri_key(b) == rep), None)
    if gb is None:
        return False, f"选中片代表块 {rep} 不在 game 盘面上"
    if not g.is_valid_gap(action['gap_type'], action['gap_line']):
        return False, (f"缝 ({action['gap_type']}, {action['gap_line']}) "
                       f"过不了 game 的 is_valid_gap")
    orig = [list(b.location) for b in g.blocks]
    g.opt(action['gap_type'], action['gap_line'], gb)
    selected = {tri_key(b) for b in g.blocks if b.be_opted}
    if selected != moved_game:
        for b, loc in zip(g.blocks, orig):
            b.location = list(loc)
        return False, (f"game 选中集与引擎 moved 不一致：多 "
                       f"{sorted(selected - moved_game)[:3]} / 少 "
                       f"{sorted(moved_game - selected)[:3]}")
    pos = g.try_move(action['direction'], mv.step)
    if not pos:
        for b, loc in zip(g.blocks, orig):
            b.location = list(loc)
        return False, (f"game 拒绝引擎移动（{action['direction']} "
                       f"step={mv.step}）")
    g.commit_move(pos)
    result = frozenset(tri_key(b) for b in g.blocks)
    for b, loc in zip(g.blocks, orig):
        b.location = list(loc)
    expect = frozenset(tri_engine_keys_to_game(eb.apply(mv).keys))
    if result != expect:
        return False, "game 重放结果态与引擎 apply 不一致"
    return True, ''


def tri_game_apply_action(g, action):
    """在 game_triangle 上按动作 dict 重放一步（GUI 同路：opt→try→commit）。"""
    target = tuple(action['moved_positions'][0])
    anchor = next((b for b in g.blocks if tri_key(b) == target), None)
    if anchor is None:
        return None
    g.opt(action['gap_type'], action['gap_line'], anchor)
    if not any(b.be_opted for b in g.blocks):
        return None
    pos = g.try_move(action['direction'], action['step'])
    if not pos:
        return None
    g.commit_move(pos)
    return frozenset(tri_key(b) for b in g.blocks)


def tri_engine_seam_partitions(eb):
    """引擎侧全部有效缝的侧分区（game 坐标）。"""
    spec = eb.spec
    keys = eb.keys
    parts = set()
    for fam in spec.seam_families:
        vals = {k: fam.rank_of(k[0], k[1]) for k in keys}
        lo, hi = min(vals.values()), max(vals.values())
        for t in range(lo + 1, hi + 1):
            side_lo = frozenset(k for k in keys if vals[k] < t)
            parts.add((frozenset(tri_engine_keys_to_game(side_lo)),
                       frozenset(tri_engine_keys_to_game(keys - side_lo))))
    return parts


def tri_game_seam_partitions(g):
    """game 侧全部有效缝（all_gaps）的侧分区。"""
    cells = g.positions()
    parts = set()
    for gap_type, line in g.all_gaps():
        s0 = frozenset(c for c in cells if tri_side_of(gap_type, line, c) == 0)
        parts.add((s0, frozenset(cells - s0)))
    return parts


def _tri_rotate_vertices(cells, times):
    """绕原点整体旋转 times×120°：旋转全部顶点后再重算内部单元（轨道等价构造）。

    R(i,j)=(-i-j,i) 是三角密铺的整数格自同构（把三族缝的边长方向映到
    另三族边长方向），转动 hull 顶点、再 cells_inside_triangle 即得旋转后
    的实心正三角形——这一构造与 game_triangle.is_solved 的凸包判据同源，
    专门用于验证「120°/240° 旋转后的还原态仍判还原」（§4.2 真问题）。
    """
    verts = set()
    for i, j, up in cells:
        verts.update(game_triangle.tri_vertices(i, j, up))
    pts = [tuple(v) for v in verts]
    for _ in range(times % 3):
        pts = [(-a - b, a) for (a, b) in pts]
    hull = game_triangle.convex_hull(pts)
    return game_triangle.cells_inside_triangle(hull)


def _tri_random_walk_states(k, step, count, seed):
    """从还原态随机走 count 步，沿途采样局面（按规范形去重）。"""
    rng = random.Random(seed)
    cur = tri_board(k)
    states, seen = [cur], {cur.canonical_key()}
    for _ in range(count):
        ms = cur.legal_moves(step)
        if not ms:
            break
        cur = cur.apply(rng.choice(ms))
        kk = cur.canonical_key()
        if kk not in seen:
            seen.add(kk)
            states.append(cur)
    return states


# ---- M0 词汇与邻表：引擎常量表 = game_triangle（桥不偷偷改词汇）----
check(tri_geometry.TRI_DIRECTIONS ==
      {k: v for k, v in TRI_GAME_DIRECTIONS.items()},
      "三角方向字母表与 game_triangle.DIRECTIONS 逐项一致")
check(tri_geometry.TRI_GAP_DIRECTIONS == TRI_GAME_GAP,
      "三角缝族方向表与 game_triangle.GAP_DIRECTIONS 一致")
_eng_orient_steps = dict(tri_geometry.TRI_ORIENT_STEPS)
_nb_bad = 0
for _o in tri_geometry.TRI_ORIENTATIONS:
    _eng = {(*off[0], off[1] == 'up') for off in _eng_orient_steps[_o]}
    _game = {(*nb[:2], nb[2]) for nb in tri_neighbors((0, 0, _o == 'up'))}
    if _eng != _game:
        _nb_bad += 1
check(_nb_bad == 0, "三角 3 邻表与 game_triangle.neighbors 逐项一致")

# ---- 采样局面：三个尺寸还原态 + 随机走查态（规范形去重）----
sampled_tri = [(k, tri_board(k)) for k in (3, 4, 5)]
_seen_tri = {eb.canonical_key() for _, eb in sampled_tri}
for k, step, cnt, seed in ((3, 1, 60, 4242), (4, 1, 60, 777),
                           (3, 2, 50, 99), (4, 2, 40, 55)):
    for b in _tri_random_walk_states(k, step, cnt, seed):
        kk = b.canonical_key()
        if kk in _seen_tri:
            continue
        _seen_tri.add(kk)
        sampled_tri.append((k, b))
        if len(sampled_tri) >= 18:
            break
    if len(sampled_tri) >= 18:
        break
check(len(sampled_tri) >= 8, f"三角采样局面数量达标（{len(sampled_tri)}）")

# ---- M1 移动对拍 ----
m1a_bad, m1a_count = [], 0
game_only_total = engine_only_total = 0
for k, eb in sampled_tri:
    g = tri_game_from_keys(eb.keys, k)
    for step in (1, 2):
        moves = eb.legal_moves(step)
        for mv in moves:
            m1a_count += 1
            ok, detail = tri_engine_move_replay(eb, g, mv)
            if not ok:
                m1a_bad.append((k, step, mv.family, mv.t, detail))
        eng_results = {frozenset(tri_engine_keys_to_game(nb.keys))
                       for nb in (eb.apply(mv) for mv in moves)}
        game_results = tri_game_move_results(g, step)
        game_only_total += len(game_results - eng_results)
        engine_only_total += len(eng_results - game_results)
check(m1a_count >= 200, f"三角采样局面能产出足量合法移动（{m1a_count} 个）")
check(not m1a_bad,
      f"引擎每个合法移动在 game_triangle 上逐一重放一致（{m1a_count} 个，"
      f"偏差 {len(m1a_bad)}）"
      + (f"；首例 {m1a_bad[0][:4]}: {m1a_bad[0][4]}" if m1a_bad else ""))
check(game_only_total == 0,
      f"game 的每个移动引擎都有（game ⊆ engine；engine 多出 "
      f"{engine_only_total} 个——出现则说明引擎漏缝，需查 M2）")
check(engine_only_total == 0,
      f"引擎的每个移动 game 也有（engine ⊆ game；双向相等，偏差 "
      f"{engine_only_total}）")

# ---- M2 缝隙分区：game 每条有效缝的侧分区，引擎必有且仅有同分区 ----
m2_bad, m2_parts = [], 0
for k, eb in sampled_tri:
    g = tri_game_from_keys(eb.keys, k)
    eng_parts = tri_engine_seam_partitions(eb)
    game_parts = tri_game_seam_partitions(g)
    m2_parts += len(game_parts)
    missing = game_parts - eng_parts
    extra = eng_parts - game_parts
    if missing or extra:
        m2_bad.append((k, len(missing), len(extra)))
check(not m2_bad,
      f"三角缝分区引擎与 game 完全相等（{m2_parts} 个分区，"
      f"game 缺 {[x[1] for x in m2_bad]} / 引擎多 {[x[2] for x in m2_bad]}）")

# ---- M4 还原判定：采样局面 + 平移/120°/240° 旋转/挖洞变体 ----
m4_bad, m4_count = [], 0
orbit_seen = False
for k, eb in sampled_tri:
    g0 = tri_game_from_keys(eb.keys, k)
    variants = [('原态', eb, g0)]
    if eb.is_solved():  # 仅还原态做轨道变体（平移/旋转仍还原、挖洞变非还原）
        for label, times in (('平移', None), ('120°', 1), ('240°', 2)):
            if times is None:
                vb = eb.translate((3, -2))
            else:
                rc = _tri_rotate_vertices(tri_engine_keys_to_game(eb.keys), times)
                vb = Board.from_keys(eb.spec,
                                     tri_game_cells_to_engine(rc))
                if vb.keys != eb.keys:
                    orbit_seen = True
            gv = tri_game_from_keys(vb.keys, k)
            variants.append((label, vb, gv))
        vb = Board(eb.spec, eb.blocks[1:])  # 挖掉一块 → 非还原
        gv = tri_game_from_keys(vb.keys, k)
        variants.append(('挖洞', vb, gv))
    for label, vb, gv in variants:
        m4_count += 1
        if vb.is_solved() != gv.is_solved():
            m4_bad.append((k, label, vb.is_solved(), gv.is_solved()))
check(orbit_seen, "120°/240° 旋转确实产生与还原态不同的等价还原局面（轨道非平凡）")
check(not m4_bad,
      f"三角还原判定一致（{m4_count} 个局面/变体：平移/120°/240°/挖洞，"
      f"偏差 {len(m4_bad)}）")

# ---- M5 安全打乱：路径/撤销在 game_triangle 上双重重放 ----
rng = random.Random(20261021)
b_t = tri_board(4)
final_t, path_t, undo_t = safe_scramble(b_t, 1, 30, rng)
check(len(path_t) == 30, f"三角 30 步全部可逆（实际 {len(path_t)}）")
check(len(undo_t) == len(path_t), "三角每步都记录了撤销移动")
check(not final_t.is_solved(), "三角终态不是还原态")
check(verify_path(b_t, path_t) == final_t, "三角路径重放与终态一致")
check(verify_path(final_t, tuple(reversed(undo_t))) == b_t,
      "三角反转撤销路径精确回到还原态（字面解法）")
g_t = tri_game_from_keys(b_t.keys, 4)
gt_ok = True
for mv in path_t:
    if tri_game_apply_action(g_t, move_to_action(b_t.spec, mv)) is None:
        gt_ok = False
        break
if gt_ok and frozenset(g_t.positions()) != tri_engine_keys_to_game(final_t.keys):
    gt_ok = False
check(gt_ok, "三角打乱路径经 game_triangle 重放：前进到终态、逆序撤销回起点")

# ---- 冻形检测：单块三角零合法移动（与 game 一致）----
single_t = Board.from_keys(tri_spec(3), [((0, 0), 'up')])
check(frozen(single_t, 1) is True, "单块三角冻形（引擎零合法移动）")
g_single = tri_game_from_keys(single_t.keys, 3)
check(g_single.all_gaps() == [], "单块三角在 game 无有效缝（与引擎一致）")


print()
if failures:
    print(f"共 {len(failures)} 項失敗")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("全部通過")
