# -*- coding: utf-8 -*-
"""大二级矩形路由护栏（2026-11-14）。

背景：混合求解器最终阶段用 GBFS 收尾，对「比较大的二级矩形谜题」GBFS 易失败
（§9.5 大盘基准 8×8 s2 卡在「只差最后一两格」、加预算也解不开；从停机终态
重跑 auto_solve 重新路由 2/3 在 22.5s 解开）。修复 = 默认路由对
step==2 且 max(m,n) >= _LARGE_STEP2_MIN_SIDE(=10) 的大二级矩形一律补缺宏（填洞
补缺）先跑，让它在满预算下先出手，而非先被 GBFS 吃掉预算再当兜底。

注：阈值从 8 抬到 10——无头标定（16 盘 8×8 s2，holes 2–4）证明对 8×8 强制补缺
宏先反而 10–100× 变慢、解却相同（GBFS 在 8×8 仍高效）；用户实测失败集中在 10×10+
，故取 10 精准命中真实故障区、不伤 8×8。

实锤（experiments/_validate_holes2_route.py）：用 §9.5 真实 few-hole 卡死终态复跑，
holes==2 大二级矩形 → 补缺宏 0.0s 直解 vs 混合(GBFS) 22s 卡死式 churn——这正是
「GBFS 失败、填洞补缺更好」的实证，证明本路由修复方向正确。（10×10 无 few-hole 卡死
样本，速度优势按 8×8 §9.5 同构外推；多洞卡死局 holes≥9 属补缺宏多洞固有缺陷，非本路由
能解，见 stalled_bigger.json 复跑俩路皆败。）

护栏纪律（见 MEMORY.md）：判据要直接盯「被绕开的求解器有没有真启动、顺序对
不对」，别只盯流式播放首段标签。本文件两层守卫：

  ① 决策矩阵单测：直接断言 _decide_gap_first_default 的返回值（确定性，不依赖
     具体盘面），把「大二级矩形 → 补缺宏先」这条规则钉死。
  ② 启动顺序 spy：用「立即返回」的 mock 替换 solve_gap_macro / hybrid_solve，
     跑一个真实 10×10 s2 盘面，确认补缺宏**先被调用**、混合作为兜底**随后**才启动
     —— 即路由切换确实接进了 auto_solve，不只是个游离函数。

运行：D:/python/python.exe test/_test_route_large_step2.py（项目根目录）
"""
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'experiments'))

import solver.auto_solver as A                                   # noqa: E402
from solver.ml.fill_macro import build_game, window_of            # noqa: E402
from experiments import harness                                  # noqa: E402

PASS = []


def check(name, cond, note=''):
    PASS.append(bool(cond))
    print('%s %s%s' % ('PASS' if cond else 'FAIL', name,
                       ('（%s）' % note) if note else ''))


# ---------------------------------------------------------------------------
# ① 决策矩阵单测
# ---------------------------------------------------------------------------
def test_decision_matrix():
    cases = [
        (([1, 2], 8, 8, 2), False),   # 阈值=10，8×8 不触发（8×8 标定无回归）
        (([1, 2], 10, 10, 2), True),  # 大二级矩形（10×10）→ 补缺宏先
        (([1, 2], 10, 12, 2), True),  # 大二级矩形（10×12）→ 补缺宏先
        (([1, 2], 6, 6, 2), False),   # 小盘 holes==2 → 混合(GBFS)先（探针 5.1 更快）
        (([1, 2], 7, 7, 2), False),   # 阈值下不触发（§9.5：7×7 s2 全解）
        (([1, 2], 8, 8, 3), False),   # 仅 step==2 生效
        (([1, 2], 6, 10, 2), True),   # 长边 >= 10 即算大
        (([1], 4, 4, 2), True),       # 既有规则：单洞补缺宏先
        (([1, 2, 3], 4, 4, 2), True), # 既有规则：holes>=3 补缺宏先
    ]
    for (holes, m, n, step), exp in cases:
        got = A._decide_gap_first_default(holes, m, n, step)
        check('决策矩阵 holes=%d %dx%d s%d -> %s' % (len(holes), m, n, step,
                                                     'gap' if exp else 'hybrid'),
              got == exp, 'got=%s' % got)


# ---------------------------------------------------------------------------
# ② 启动顺序 spy：真实盘面，确认路由切换确实接进了 auto_solve（护栏纪律：
#    盯「被绕开的求解器有没有真启动、顺序对不对」）。两个候选用「立即返回」的
#    mock 替换，只记录 auto_solve 内部调用顺序，不真算、不依赖具体可解性。
# ---------------------------------------------------------------------------
def _spy_run(coords, m, n, step):
    """用立即返回的 mock 替换两个候选，记录 auto_solve 内部调用顺序。"""
    order = []
    real_gap = A.solve_gap_macro
    real_hybrid = A.hybrid_solve

    def fake_gap(*_a, **_k):
        order.append('gap')
        return {'type': 'fill_fail'}

    def fake_hybrid(*_a, **_k):
        order.append('hybrid')
        return False

    A.solve_gap_macro = fake_gap
    A.hybrid_solve = fake_hybrid
    try:
        # time_budget 仅用于让 auto_solve 尽快收尾；mock 已立即返回，不会真算。
        A.auto_solve(build_game(coords, m, n), step, time_budget=1)
    finally:
        A.solve_gap_macro = real_gap
        A.hybrid_solve = real_hybrid
    return order


def test_spy_large_step2_gap_first():
    # 大二级矩形：step==2 且 max(m,n)>=10 → 默认永远补缺宏先跑，与洞数无关。
    # 任取一个 10×10 s2 真实盘面即可（gen_state 用固定 seed 复现）。
    snap = harness.gen_state(10, 10, 2, 3000)
    coords = frozenset(snap['coords'])
    _r, _o, holes, _u = window_of(coords, 10, 10, 2)
    check('10×10 s2 复现盘面 holes>=1', len(holes) >= 1, 'holes=%d' % len(holes))
    order = _spy_run(coords, 10, 10, 2)
    check('大二级矩形：补缺宏先启动', order and order[0] == 'gap', str(order))
    check('大二级矩形：混合作为兜底也启动', 'hybrid' in order, str(order))


def test_spy_small_step2_hybrid_first():
    # 小盘 holes==2 → 默认混合(GBFS)先跑（探针 5.1：混合 1.4s vs 补缺宏 57.2s）。
    # 深打乱盘 holes 极多（>=3 也会走补缺宏先），故直接构造一个恰好 2 洞的 6×6 s2
    # 盘面（满盘去掉两角），只验证调用顺序，不依赖可解性。
    full = frozenset((r, c) for r in range(6) for c in range(6))
    coords = full - {(0, 0), (5, 5)}
    _r, _o, holes, _u = window_of(coords, 6, 6, 2)
    check('构造盘面确为 holes==2', len(holes) == 2, 'holes=%d' % len(holes))
    order = _spy_run(coords, 6, 6, 2)
    check('小盘 holes==2：混合(GBFS)先启动（不被大二级规则误伤）',
          order and order[0] == 'hybrid', str(order))
    check('小盘 holes==2：补缺宏作为兜底也启动', 'gap' in order, str(order))


def main():
    test_decision_matrix()
    test_spy_large_step2_gap_first()
    test_spy_small_step2_hybrid_first()
    print('==== %s（%d/%d 通過）' %
          ('全部通過' if all(PASS) else '有失敗', sum(PASS), len(PASS)))
    return 0 if all(PASS) else 1


if __name__ == '__main__':
    sys.exit(main())
