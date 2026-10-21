# -*- coding: utf-8 -*-
"""EngineGame 适配器 + 几何引擎开关 的等价性回归。

执行：python test/_test_engine_adapter.py
约定：脚本型回归（check 收集失败，退出码非 0 即失败），零 pygame。

覆盖（验证「启用几何引擎开关」后，适配器与旧 game*.py 逻辑等价；
M/L 节已证明 引擎≡旧 game，本测试再钉死 适配器≡引擎 与开关行为）：
  N0 开关本身：默认关→旧引擎；set_enabled(True)→EngineGame；复位→旧引擎
  N1 位置集合：适配器 positions 归一化 == 旧 game positions 归一化（三形态）
  N2 有效缝：适配器 all_gaps 的分区 == 引擎枚举的分区（三形态）
  N3 移动对拍：每个引擎合法移动经 适配器.opt→try_move→commit 后局面 ==
              引擎 apply（三形态）
  N4 还原判定：适配器 is_solved == 旧 game is_solved（还原态 + 采样态）
  N5 可逆打乱：safe_scramble 路径经适配器重放，前进到终态、反转回起点
  N6 双调用约定：适配器 opt 接受「缝族名」与「方向字母」两种入参（方形）
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game
import game_mi
import game_triangle
from engine import (  # noqa: E402
    EngineGame, create_adapter_puzzle, direction_table, mi_board,
    safe_scramble, square_board, tri_board, tri_spec, verify_path,
)
from engine.compat import move_to_action, _norm_keys  # noqa: E402
from engine.config import is_enabled, set_enabled  # noqa: E402
from game import SliderMatrix  # noqa: E402
from game_mi import MiSliderMatrix  # noqa: E402
from game_triangle import TriangleSliderMatrix  # noqa: E402
from puzzle_types import create_puzzle  # noqa: E402

failures = []


def check(cond, msg):
    if cond:
        print("  ok:", msg)
    else:
        print("  FAIL:", msg)
        failures.append(msg)


def old_positions(game, kind):
    """取旧 game 的全部位置（方形无 positions()，从 blocks 派生）。"""
    if kind == 'square':
        return {(b.location[0], b.location[1]) for b in game.blocks}
    return game.positions()


def norm_positions(game_positions, spec):
    """游戏既有格式位置集合 → 引擎块键集合（中性表示，规避浮点/朝向格式差异）。"""
    return set(_norm_keys(list(game_positions), spec, 'pos'))


def _cell_to_game(engine_key, kind):
    (p, o) = engine_key
    if kind == 'square':
        return (p[0], p[1])
    if kind == 'triangle':
        return (p[0], p[1], (o == 'up'))
    return (p[0] // 2, p[1] // 2, o)  # mi：引擎点 = 实坐标 × 2


def _set_game_positions(g, engine_keys, kind):
    """把旧 game 的 blocks 重建到给定引擎键集合（仅测试摆态用）。"""
    cells = [_cell_to_game(k, kind) for k in engine_keys]
    if kind == 'square':
        g.blocks = [game.Block([r, c]) for (r, c) in sorted(cells)]
    elif kind == 'triangle':
        g.blocks = [game_triangle._make_block(i, j, up)
                    for (i, j, up) in sorted(cells)]
    else:  # mi
        g.blocks = [game_mi._make_block(r, c, q) for (r, c, q) in sorted(cells)]
    g.update_matrix()


def _random_walk(board, step, count, seed):
    rng = random.Random(seed)
    states, seen = [board], {board.canonical_key()}
    for _ in range(count):
        ms = board.legal_moves(step)
        if not ms:
            break
        board = board.apply(rng.choice(ms))
        k = board.canonical_key()
        if k not in seen:
            seen.add(k)
            states.append(board)
    return states


def _adapter_replay(adapter, mv):
    """把引擎 Move 经适配器 opt→try_move→commit 重放（与 GUI 同路）。"""
    action = move_to_action(adapter.spec, mv)
    rep_key = tuple(_norm_keys([action['moved_positions'][0]], adapter.spec, 'rep'))[0]
    rep_block = next((b for b in adapter.blocks if b.engine_key == rep_key), None)
    if rep_block is None:
        return False
    adapter.opt(action['gap_type'], action['gap_line'], rep_block)
    if not any(b.be_opted for b in adapter.blocks):
        return False
    pos = adapter.try_move(action['direction'], mv.step)
    if not pos:
        return False
    adapter.commit_move(pos)
    return True


# 三形态参数：(kind, m, n, triangle_side, 旧 game 构造器, 引擎板型构造器)
_FORMS = [
    ('square', 4, 4, None, lambda: SliderMatrix(4, 4),
     lambda: square_board(4, 4)),
    ('triangle', 4, 4, 4, lambda: TriangleSliderMatrix(4),
     lambda: tri_board(4)),
    ('mi', 3, 3, None, lambda: MiSliderMatrix(3, 3),
     lambda: mi_board(3, 3)),
]

# ======================================================================
print("== N0 开关本身：默认关→旧引擎；开启→EngineGame ==")
set_enabled(False)
assert not is_enabled(), "默认应关闭"
g_off = create_puzzle(4, 4, 2, 'square')
check(not isinstance(g_off, EngineGame),
      f"开关关闭时 create_puzzle 返回旧引擎对象（{type(g_off).__name__}）")
set_enabled(True)
check(is_enabled(), "set_enabled(True) 生效")
g_on = create_puzzle(4, 4, 2, 'square')
check(isinstance(g_on, EngineGame),
      f"开关开启时 create_puzzle 返回 EngineGame（{type(g_on).__name__}）")
check(g_on.board.keys == square_board(4, 4).keys,
      "开启后 EngineGame 包裹方形还原态")
set_enabled(False)  # 复位，后续用例默认关
check(not is_enabled(), "复位：开关关闭")

# ======================================================================
print("== N1~N5 适配器 ≡ 旧 game（三形态逐项）==")
for kind, m, n, k, old_factory, eng_factory in _FORMS:
    print(f"-- {kind} --")
    old = old_factory()
    eng_board = eng_factory()
    adapter = EngineGame(eng_board, m=m, n=n, k=k, kind=kind)
    spec = adapter.spec

    # N1 位置集合：适配器（game 格式）归一化 == 旧 game 位置归一化
    check(norm_positions(old_positions(old, kind), spec) == eng_board.keys,
          f"{kind} 位置集合一致（适配器/旧 game 归一化等价）")

    # N2 有效缝：适配器 all_gaps 的分区 == 引擎枚举的分区（含锁死缝跳过）
    eng_parts = set()
    for fam in spec.seam_families:
        vals = {kk: fam.rank_of(kk[0], kk[1]) for kk in eng_board.keys}
        lo, hi = min(vals.values()), max(vals.values())
        for t in range(lo + 1, hi + 1):
            if spec.seam_clear is not None and \
                    not spec.seam_clear(fam, t, eng_board):
                continue
            side_lo = frozenset(kk for kk in eng_board.keys if vals[kk] < t)
            eng_parts.add((frozenset(side_lo),
                           frozenset(eng_board.keys - side_lo)))
    ad_parts = set()
    for gt, line in adapter.all_gaps():
        fam = next(f for f in spec.seam_families if f.name == gt)
        t = int(round(fam.line_scale * line)) + 1
        side_lo = frozenset(kk for kk in eng_board.keys
                           if fam.rank_of(kk[0], kk[1]) < t)
        ad_parts.add((frozenset(side_lo),
                      frozenset(eng_board.keys - side_lo)))
    check(ad_parts == eng_parts, f"{kind} 有效缝分区一致（{len(eng_parts)} 个）")

    # N3 移动对拍：适配器重放 == 引擎 apply
    states = [eng_board] + _random_walk(eng_board, 1, 40, 1234 + m)
    n3_bad, n3_count = [], 0
    for st in states:
        for step in (1, 2):
            moves = st.legal_moves(step)
            for mv in moves:
                n3_count += 1
                ad = EngineGame(st, m=m, n=n, k=k, kind=kind)
                if not _adapter_replay(ad, mv) or ad.board.keys != st.apply(mv).keys:
                    n3_bad.append((step, mv.family, mv.t))
    check(n3_count >= 100, f"{kind} 采样局面产出足量合法移动（{n3_count}）")
    check(not n3_bad,
          f"{kind} 每个引擎合法移动经适配器重放 == 引擎 apply（偏差 "
          f"{len(n3_bad)}）"
          + (f"；首例 {n3_bad[0]}" if n3_bad else ""))

    # N4 还原判定：适配器 is_solved == 旧 game is_solved（还原态 + 采样态）
    ad_goal = EngineGame(eng_factory(), m=m, n=n, k=k, kind=kind)
    check(ad_goal.is_solved() == old_factory().is_solved(),
          f"{kind} 还原态 is_solved 一致（适配器 {ad_goal.is_solved()} / "
          f"旧 game {old_factory().is_solved()}）")
    n4_bad = 0
    for st in states[:8]:
        ad = EngineGame(st, m=m, n=n, k=k, kind=kind)
        og = old_factory()
        _set_game_positions(og, st.keys, kind)
        if ad.is_solved() != og.is_solved():
            n4_bad += 1
    check(n4_bad == 0, f"{kind} 采样态 is_solved 与旧 game 一致（偏差 {n4_bad}）")

    # N5 可逆打乱：safe_scramble 路径经适配器重放
    rng = random.Random(20261101)
    b0 = eng_factory()
    final, path, undo = safe_scramble(b0, 1, 25, rng)
    ad = EngineGame(b0, m=m, n=n, k=k, kind=kind)
    replay_ok = all(_adapter_replay(ad, mv) for mv in path) and \
        ad.board.keys == final.keys
    check(replay_ok, f"{kind} 打乱路径经适配器重放前进到终态")
    ad2 = EngineGame(final, m=m, n=n, k=k, kind=kind)
    undo_ok = all(_adapter_replay(ad2, mv) for mv in reversed(undo)) and \
        ad2.board.keys == b0.keys
    check(undo_ok, f"{kind} 反转撤销路径经适配器重放精确回到还原态")

# ======================================================================
print("== N6 适配器 opt 双调用约定（缝族名 / 方向字母）==")
# 方形：opt('a', line, block) 与 opt('h', line, block) 应选中同一片
sq = EngineGame(square_board(4, 4), m=4, n=4, kind='square')
mv = sq.board.legal_moves(1)[0]
action = move_to_action(sq.spec, mv)
rep_key = tuple(_norm_keys([action['moved_positions'][0]], sq.spec, 'rep'))[0]
rep_block = next(b for b in sq.blocks if b.engine_key == rep_key)
sq.opt(mv.family, action['gap_line'], rep_block)
sel_family = {b.engine_key for b in sq.blocks if b.be_opted}
sq2 = EngineGame(square_board(4, 4), m=4, n=4, kind='square')
rep_block2 = next(b for b in sq2.blocks if b.engine_key == rep_key)
sq2.opt(action['direction'], action['gap_line'], rep_block2)
sel_letter = {b.engine_key for b in sq2.blocks if b.be_opted}
check(sel_family == sel_letter,
      f"方形 opt 接受缝族名与方向字母选中同一片（差异 "
      f"{len(sel_family ^ sel_letter)}）")

print()
if failures:
    print(f"共 {len(failures)} 項失敗")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("全部通過")
