# -*- coding: utf-8 -*-
"""护栏：大洞填补（定向对齐 + 让路 + 刚体推进）。

背景（2026-11-11 诊断 22 局 >6×6 残局）：
  · 洞簇与凸起簇**形状不全等**时（横 2 格洞 vs 竖 2 格凸起），
    `_rigid_fill` 在形状检查就返回；旧 `_reshape_edges` 只比数量不比形状。
  · 形状相同时也搜不到：9×9 上盲 DFS 500~800 节点跑 20~28s 仍 miss
    —— 分支因子几百（每条缝 × 两侧 × 连通分量 × 四方向）。

对策（「大洞」＝与洞不共线的刚体凸起平移复制品）：
  · `_align_rigid`：只沿单轴、只走「P 跟着整片动且该轴间距严格下降」的
    动作，分支恒为 1 → 9×9 三步 0.04s 到位。
  · `_rigid_fill` 的 prep（腾空走廊）从 `elif` 摘出来成 `prep_follow`，
    P 在分量内也能让路（用户三步里的第 2 步）；carry 组加节点限额。

测试分组：
  A 组 形状 / 共线判据（纯函数）
  B 组 `_align_rigid` 行为（4×4 一步、10×10 三步、形状不同拒绝、
      parity 拒绝、已共线空转）
  C 组 `_moves_of` 模拟 == 引擎回放（逐条核对，防两套枚举漂移）
  D 组 端到端：4×4 验收例子自动解出且步数不退化
  E 组 形状不全等时**不白调** `_rigid_fill`（spy 计数）
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solver.ml import fill_macro as fm  # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + ('  %s' % detail if detail else ''))
    if not ok:
        FAILS.append(name)
    return ok


def board44():
    """用户给的验收盘面：4×4 窗口，洞横 2 格在第 2 行，凸起横 2 格在第 4 行右侧。"""
    return frozenset({(0, 0), (0, 1), (0, 2), (0, 3),
                      (1, 0), (1, 3),
                      (2, 0), (2, 1), (2, 2), (2, 3),
                      (3, 0), (3, 1), (3, 2), (3, 3), (3, 4), (3, 5)})


def board6(box=6, hole=((1, 1), (1, 2)), extra=((5, 6), (6, 6))):
    S = {(r, c) for r in range(box) for c in range(box)}
    for q in hole:
        S.discard(q)
    for q in extra:
        S.add(q)
    return frozenset(S)


def replay_equals(coords, m, n, step, acts, expect):
    """引擎回放 acts 后，盘面是否等于模拟出的 expect。"""
    g = fm.build_game(coords, m, n)
    if not fm._replay_apply(g, acts, m, n, step):
        return False
    return frozenset(fm.gcoords(g)) == expect


# --------------------------------------------------------------------------
# A 组：形状 / 共线判据
# --------------------------------------------------------------------------
def pure_tests():
    H = frozenset({(1, 2), (1, 3)})
    V = frozenset({(3, 4), (4, 4)})
    check('A1 _shape_rel 平移不变',
          fm._shape_rel(H) == fm._shape_rel(frozenset({(7, 9), (7, 10)})))
    check('A2 横 2 格与竖 2 格判为不同形状（刚体不能旋转）',
          fm._shape_rel(H) != fm._shape_rel(V))
    check('A3 _shape_rel L 形与直条形不同',
          fm._shape_rel(frozenset({(0, 0), (1, 0), (1, 1)}))
          != fm._shape_rel(frozenset({(0, 0), (0, 1), (0, 2)})))
    check('A4 _same_line 同行', fm._same_line(H, frozenset({(5, 2), (5, 3)})))
    check('A5 _same_line 同列', fm._same_line(H, frozenset({(5, 2), (6, 3)})))
    check('A6 _same_line 斜置为 False',
          not fm._same_line(H, frozenset({(4, 4), (4, 5)})))


# --------------------------------------------------------------------------
# B 组：_align_rigid
# --------------------------------------------------------------------------
def align_tests():
    c4 = board44()
    H4 = frozenset({(1, 1), (1, 2)})
    P4 = frozenset({(3, 4), (3, 5)})
    acts, cur2, P2 = fm._align_rigid(c4, 4, 4, 2, H4, P4)
    check('B1 4×4 对齐成功（凸起从第 4 行挪到第 2 行）',
          acts is not None and len(acts) == 1 and P2 is not None
          and min(r for r, _ in P2) == 1,
          'acts=%s P2=%s' % (acts, sorted(P2) if P2 else None))
    check('B2 对齐动作引擎回放后与模拟坐标一致（不脱钩）',
          acts is not None
          and replay_equals(c4, 4, 4, 2, acts, cur2))

    # 10×10：行差 9（奇数，parity 不整除）→ 只能走列，3 步
    S = {(r, c) for r in range(10) for c in range(10)}
    S.discard((1, 2))
    S.discard((1, 3))
    S.add((10, 8))
    S.add((10, 9))
    c10 = frozenset(S)
    H10 = frozenset({(1, 2), (1, 3)})
    P10 = frozenset({(10, 8), (10, 9)})
    a10, cur10, p10 = fm._align_rigid(c10, 10, 10, 2, H10, P10,
                                      max_comp=100)
    check('B3 10×10 行被 parity 否掉时退回列对齐，3 步到位',
          a10 is not None and len(a10) == 3 and p10 is not None
          and {c for _, c in p10} == {2, 3},
          'steps=%s P2=%s' % (len(a10) if a10 else None,
                             sorted(p10) if p10 else None))
    check('B4 10×10 对齐动作引擎回放一致',
          a10 is not None and replay_equals(c10, 10, 10, 2, a10, cur10))

    # 形状不全等（横洞 vs 竖凸）→ 拒绝，不产生任何动作
    b_diff = board6(extra=((5, 6), (6, 6)))
    a, c2, p2 = fm._align_rigid(
        b_diff, 6, 6, 2, frozenset({(1, 2), (1, 3)}),
        frozenset({(5, 6), (6, 6)}))
    check('B5 形状不全等（横洞 vs 竖凸）直接拒绝',
          a is None and c2 is None and p2 is None)

    # 两轴 parity 都不对 → 拒绝（行差 7 奇、列差 3 奇）
    b_par = board6(extra=((8, 4), (8, 5)))
    a, c2, p2 = fm._align_rigid(
        b_par, 6, 6, 2, frozenset({(1, 1), (1, 2)}),
        frozenset({(8, 4), (8, 5)}))
    check('B6 两轴 parity 都不整除时拒绝（step 平移永远对不齐）',
          a is None)

    # 已共线 → 空动作，P 原样返回
    Hc = frozenset({(1, 2), (1, 3)})
    Pc = frozenset({(1, 6), (1, 7)})
    a, c2, p2 = fm._align_rigid(c4, 4, 4, 2, Hc, Pc)
    check('B7 已共线时空转（0 步、P 不变、盘面不变）',
          a == [] and p2 == Pc and c2 == c4)

    # 对齐之后必须能推进 —— 这一步靠「让路」（prep_follow）：
    # P 已在同一分量里、carry 走不动，只能先把挡路的整条通道挪开。
    # 旧代码把 prep 锁在 `elif` 里，这里 2 个节点就 dead end。
    racts, used = fm._rigid_fill(cur2, 4, 4, 2, H4, P2, max_nodes=600)
    ok_b8 = False
    if racts:
        g = fm.build_game(cur2, 4, 4)
        for a5 in racts:
            fm._capture_apply(g, a5, 2)
        ok_b8 = g.is_solved()
    check('B8 对齐后靠「让路」推进并全解（上两行右移 → 推入 → 还原）',
          ok_b8, 'used=%d acts=%s' % (used, racts))


# --------------------------------------------------------------------------
# C 组：_moves_of 与引擎一致
# --------------------------------------------------------------------------
def moves_tests():
    c4 = board44()
    moves = fm._moves_of(c4, 4, 4, 2)
    check('C1 _moves_of 在验收盘面上有候选', len(moves) > 0,
          'n=%d' % len(moves))
    bad = []
    for act5, comp, delta, nxt in moves:
        g = fm.build_game(c4, 4, 4)
        ok, _ = fm._capture_apply(g, act5, 2)
        if not ok or frozenset(fm.gcoords(g)) != frozenset(nxt):
            bad.append(act5)
    check('C2 每个候选位移都与引擎回放逐格一致', not bad,
          'mismatch=%s' % bad[:3])


# --------------------------------------------------------------------------
# D 组：端到端
# --------------------------------------------------------------------------
def e2e_tests():
    c4 = board44()
    res = fm.solve_fill_macro(fm.build_game(c4, 4, 4), 2, time_budget=15)
    if not isinstance(res, tuple):
        check('D1 4×4 验收盘面自动解出', False, str(res)[:120])
        check('D2 步数不退化', False)
        return
    acts, reps = res
    full = [tuple(a[:4]) + (tuple(r),) for a, r in zip(acts, reps)]
    check('D1 4×4 验收盘面自动解出（用户给的最简大洞局面）',
          fm.replay_and_verify(c4, 4, 4, 2, full), 'steps=%d' % len(acts))
    # 行为锁定：大洞逻辑不得让小盘路径变绕（改动前就是 3 步）
    check('D2 4×4 步数保持 3（新逻辑不许把路径绕长）',
          len(acts) == 3, 'steps=%d' % len(acts))


# --------------------------------------------------------------------------
# E 组：形状不全等时不许白调 _rigid_fill
# --------------------------------------------------------------------------
def filter_tests():
    b_diff = board6(extra=((5, 6), (6, 6)))   # 横洞 vs 竖凸
    calls = {'n': 0}
    orig = fm._rigid_fill

    def spy(*a, **k):
        calls['n'] += 1
        return orig(*a, **k)

    fm._rigid_fill = spy
    try:
        fm.solve_multi_search(b_diff, 6, 6, 2, node_budget=2,
                              time_budget=6)
    finally:
        fm._rigid_fill = orig
    check('E1 形状不全等的对不会被塞给 _rigid_fill（spy 计数 0）',
          calls['n'] == 0, 'calls=%d' % calls['n'])


def main():
    pure_tests()
    align_tests()
    moves_tests()
    e2e_tests()
    filter_tests()
    print()
    if FAILS:
        print('FAILED %d:' % len(FAILS))
        for f in FAILS:
            print('  -', f)
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
