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
        if set(m.moved) >= {(0, 0), (1, 0)}]
check(len(drag) >= 1, "存在把捆绑组整体拖动的合法移动")
if drag:
    mv = drag[0]
    nb = eb.apply(mv)
    delta = tuple(mv.step * x for x in mv.direction)
    check(nb.point_map[(delta[0], delta[1])].group == 7
          and nb.point_map[(1 + delta[0], delta[1])].group == 7,
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
             if any(p[1] > 1 for p in m.moved))
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
moved = set(mv.moved)
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

print()
if failures:
    print(f"共 {len(failures)} 項失敗")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("全部通過")
