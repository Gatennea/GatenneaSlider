# -*- coding: utf-8 -*-
"""holes==2 短探测路由护栏（2026-11-14）。

背景：默认路由从 2026-10-02 起是「1 洞 / ≥3 洞补缺宏先，2 洞混合(GBFS)先」。
2026-11-14 用入库 15 盘手解中间快照按当年口径复测，2 洞档判定已反转
（补缺宏 8/12 全解、混合 0/12），用户实际反例（2-8-8 第 148 步）补缺宏
0.01s 全解、默认却先跑 10s 聚拢；但同一档内部两极分化（另一批补缺宏 8s
以上未解，10 洞档反而混合 2s 全解），故不按洞数 / 尺寸硬改先手，改为
「先试一下」：默认判混合先时给补缺宏一次 0.10s 短探测，命中即采纳，
失败立刻让位、两候选照原顺序与满预算跑。

⚠️ 前一版「大二级矩形 step==2 且最长边>=10 一律补缺宏先」已被审查否决
（10×10 易解盘实测慢 18.3 倍 / 5.0 倍；证据样本全落在规则不触发的 8×8；
spy 用 53 洞盘，旧规则本就补缺宏先、中和后恒绿）。本护栏按审查纪律重建：

  · 证据样本落在**规则实际生效的档位**（holes==2），且全部由文件内公式
    生成，不依赖任何未入库存档（§23）。FAST/SLOW 与 archives/失败0*.json
    的两个真实手解快照逐位一致（见下注释），但运行时不读存档。
  · spy 选「旧路由会走另一条路」的局面（holes==2 默认混合先），判据直接
    盯「被绕开的混合求解器有没有真启动」，不盯流式播放首段标签。
  · 两处真刀反向验证：中和探测器 / 把探测预算置 0，行为必须回落到旧路由
    （混合被启动），否则说明探测没被真正绕开 → 转红。还原用 try/finally。
  · 超支硬上界：慢盘探测实测墙钟必须 ≤ 0.20s（带移让位链预算透传若被删
    会退回 1.5s；探测预算若被放大到 0.30s 也会转红）。

运行：D:/python/python.exe test/_test_route_gap_probe.py（项目根目录）
"""
import io
import os
import sys
import time
from contextlib import redirect_stdout

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

import solver.auto_solver as A                                    # noqa: E402
from solver.ml.fill_macro import build_game, window_of             # noqa: E402

PASS = []


def check(name, cond, note=''):
    PASS.append(bool(cond))
    print('%s %s%s' % ('PASS' if cond else 'FAIL', name,
                       ('（%s）' % note) if note else ''))


def _holes(coords, m=8, n=8, step=2):
    return len(window_of(coords, m, n, step)[2])


# ---- 可生成几何典例（8×8 s2，全部由公式生成，不读存档）------------------
# FAST：满矩形挖掉 (0,2)/(1,0)，窗外右侧补 (6,8)/(7,8)。
#   逐位等于 archives/失败06.json 快照 7；补缺宏 0.01~0.02s 全解。
# SLOW：满矩形整体右移 3 格，顶行加两凸、第 6 行去两端。
#   逐位等于 archives/失败04.json 快照 10；补缺宏短预算放弃（原有探测会
#   因带移让位链超支 1.5s，band_budget 透传后压到 0.10s）。
_FULL = frozenset((r, c) for r in range(8) for c in range(8))


def FAST():
    return (_FULL - {(0, 2), (1, 0)}) | {(6, 8), (7, 8)}


def SLOW():
    return (({(r, 3 + c) for r in range(8) for c in range(8)}
             | {(0, 11), (0, 12)}) - {(6, 3), (6, 10)})


def ONE():
    return (_FULL - {(0, 0)}) | {(7, 8)}


def THREE():
    return (_FULL - {(0, 2), (1, 0), (4, 4)}) | {(6, 8), (7, 8), (8, 8)}


def TEN():
    return ((_FULL - {(r, c) for r in range(2) for c in range(5)})
            | {(7, 8 + c) for c in range(5)}
            | {(8, 8 + c) for c in range(5)})


# 旧默认路由（2026-10-02 探针 + 2026-11-11 单洞收口）：注入它即复现改动前
# 的行为，且注入时 auto_solve 不做探测（D1 接缝完全覆盖）。A/B 同一个文件、
# 同一份代码，只是注入与否，无需回退源码。
OLD_ROUTE = lambda h, c, m, n, s: (h >= 3 or h == 1)            # noqa: E731


def _solve(coords, budget=3.0, **kw):
    """真跑 auto_solve；屏蔽求解器 stdout（探测/候选都有打印）。"""
    with redirect_stdout(io.StringIO()):
        return A.auto_solve(build_game(coords, 8, 8), 2,
                            time_budget=budget, rng_seed=1, **kw)


def _run_hybrid_spy(coords, budget=3.0, **kw):
    """包装（不是替换）hybrid_solve：记录它是否真被启动，行为不变。"""
    calls = []
    real = A.hybrid_solve

    def spy(*a, **k):
        calls.append('hybrid')
        return real(*a, **k)

    A.hybrid_solve = spy
    t0 = time.perf_counter()
    try:
        r = _solve(coords, budget=budget, **kw)
    finally:
        A.hybrid_solve = real
    return r, calls, time.perf_counter() - t0


def _spy_run(coords, budget=1.0, **kw):
    """替换两候选为立即返回的 mock，记录 auto_solve 内部调用顺序。

    探测调用 solve_gap_macro 时带 band_budget、不带 segment_cb；正式 gap
    候选带 segment_cb。据此把「探测」与「正式候选」分开记，避免旧护栏
    「spy 盘面本来就该补缺宏先、中和后恒绿」的假绿。
    """
    events = []
    real_gap = A.solve_gap_macro
    real_hybrid = A.hybrid_solve

    def fake_gap(*_a, **k):
        events.append('probe' if 'band_budget' in k else 'gap')
        return {'type': 'fill_fail'}

    def fake_hybrid(*_a, **_k):
        events.append('hybrid')
        return False

    A.solve_gap_macro = fake_gap
    A.hybrid_solve = fake_hybrid
    try:
        _solve(coords, budget=budget, **kw)
    finally:
        A.solve_gap_macro = real_gap
        A.hybrid_solve = real_hybrid
    return events


# ---------------------------------------------------------------------------
# ① 决策矩阵：默认路由只看洞数，不看尺寸 / 步长 / 形态
# ---------------------------------------------------------------------------
def test_decision_matrix():
    cases = [
        (([1], 8, 8, 2), True),        # 单洞补缺宏先
        (([1, 2], 8, 8, 2), False),    # 两洞混合先（+短探测）
        (([1, 2, 3], 8, 8, 2), True),  # 三洞补缺宏先
        (([1, 2], 10, 10, 2), False),  # 10×10 也不按尺寸切
        (([1, 2], 12, 12, 2), False),  # 更大也不切
        (([1, 2], 10, 12, 3), False),  # 换步长也不切
        (([1, 2], 6, 6, 2), False),    # 小盘同样
        (([1, 2, 3, 4], 4, 4, 2), True),
    ]
    for (holes, m, n, step), exp in cases:
        got = A._decide_gap_first_default(holes, m, n, step)
        check('决策矩阵 holes=%d %dx%d s%d -> %s'
              % (len(holes), m, n, step, 'gap' if exp else 'hybrid'),
              got == exp, 'got=%s' % got)


# ---------------------------------------------------------------------------
# ② 探测命中：真实盘面（规则生效档位），判据盯「混合有没有被启动」
# ---------------------------------------------------------------------------
def test_geometric_examples():
    check('FAST 为 holes==2', _holes(FAST()) == 2, str(_holes(FAST())))
    check('SLOW 为 holes==2', _holes(SLOW()) == 2, str(_holes(SLOW())))
    check('ONE 为 holes==1', _holes(ONE()) == 1, str(_holes(ONE())))
    check('THREE 为 holes==3', _holes(THREE()) == 3, str(_holes(THREE())))
    check('TEN 为 holes==10', _holes(TEN()) == 10, str(_holes(TEN())))


def test_probe_hit_skips_hybrid():
    r, calls, dt = _run_hybrid_spy(FAST(), budget=3.0)
    check('探测命中：全解', isinstance(r, tuple), str(type(r).__name__))
    check('探测命中：混合(GBFS)一次都没启动', calls == [], str(calls))
    check('探测命中：0.5s 内返回', dt < 0.5, '%.3fs' % dt)


def test_probe_hit_reports_stage():
    stages = []
    r = _solve(FAST(), budget=3.0,
               stage_cb=lambda s: stages.append(s['label']))
    check('探测命中：上报「补缺宏·短探测」段',
          isinstance(r, tuple) and '补缺宏·短探测' in stages,
          str(stages))


def test_old_route_starts_hybrid():
    """旧默认（注入复现）：同一盘面必须先启动混合。"""
    _r, calls, dt = _run_hybrid_spy(FAST(), budget=3.0,
                                    route_fn=OLD_ROUTE)
    check('注入旧默认：混合(GBFS)先启动', len(calls) >= 1,
          'calls=%s dt=%.3fs' % (calls, dt))


# ---------------------------------------------------------------------------
# ③ 真刀反向验证：中和探测器 / 预算置 0，行为必须回落到旧路由
#    （若探测没被真正绕开，混合仍是 0 次 → 判据转红）
# ---------------------------------------------------------------------------
def test_reverse_neutralize_probe():
    real = A._probe_gap_first
    A._probe_gap_first = lambda *a, **k: None
    try:
        _r, calls, _dt = _run_hybrid_spy(FAST(), budget=3.0)
    finally:
        A._probe_gap_first = real
    check('反向验证·中和探测器后混合被启动', len(calls) >= 1, str(calls))


def test_reverse_neutralize_budget():
    old = A._GAP_PROBE_BUDGET
    A._GAP_PROBE_BUDGET = 0.0
    try:
        _r, calls, _dt = _run_hybrid_spy(FAST(), budget=3.0)
    finally:
        A._GAP_PROBE_BUDGET = old
    check('反向验证·探测预算置 0 后混合被启动', len(calls) >= 1, str(calls))


# ---------------------------------------------------------------------------
# ④ 探测失败：让位、不改候选顺序、不播段；硬上界 0.6s
# ---------------------------------------------------------------------------
def test_probe_failure_hands_over():
    events = _spy_run(SLOW(), budget=1.0)
    check('慢盘：探测先试一次', events.count('probe') == 1, str(events))
    check('慢盘：探测失败后两候选照原顺序 hybrid→gap',
          events == ['probe', 'hybrid', 'gap'], str(events))


def test_probe_hard_cap():
    t0 = time.perf_counter()
    with redirect_stdout(io.StringIO()):
        got = A._probe_gap_first(SLOW(), 8, 8, 2, lambda: False, 1)
    dt = time.perf_counter() - t0
    check('慢盘：探测放弃（不采纳部分成果）', got is None, str(got))
    check('慢盘：探测墙钟 ≤ 0.20s（带移链预算透传 + 预算未放大）',
          dt <= 0.20, '%.3fs' % dt)


def test_probe_failure_emits_no_stage():
    stages = []
    _solve(SLOW(), budget=1.0,
           stage_cb=lambda s: stages.append(s['label']))
    check('慢盘：探测失败不播出「短探测」段',
          '补缺宏·短探测' not in stages, str(stages))


# ---------------------------------------------------------------------------
# ⑤ D1 接缝：route_fn 注入完全覆盖默认（含不做探测）；其它洞数档不探测
# ---------------------------------------------------------------------------
def test_route_fn_overrides_probe():
    ev_false = _spy_run(FAST(), budget=1.0, route_fn=lambda *a: False)
    ev_true = _spy_run(FAST(), budget=1.0, route_fn=lambda *a: True)
    check('注入 route_fn=False：不探测、混合先',
          ev_false == ['hybrid', 'gap'], str(ev_false))
    check('注入 route_fn=True：不探测、补缺宏先',
          ev_true == ['gap', 'hybrid'], str(ev_true))


def test_other_hole_counts_no_probe():
    for name, coords, expect_first in [('holes==1', ONE(), 'gap'),
                                       ('holes==3', THREE(), 'gap'),
                                       ('holes==10', TEN(), 'gap')]:
        events = _spy_run(coords, budget=1.0)
        check('%s：不探测且补缺宏先' % name,
              'probe' not in events and events and events[0] == expect_first,
              str(events))


def test_zz_all_guardrails():
    """pytest 兜底：check() 只 print 不 raise，末尾显式断言防假绿。"""
    assert all(PASS), '有护栏未通过：%d/%d' % (sum(PASS), len(PASS))


def main():
    test_decision_matrix()
    test_geometric_examples()
    test_probe_hit_skips_hybrid()
    test_probe_hit_reports_stage()
    test_old_route_starts_hybrid()
    test_reverse_neutralize_probe()
    test_reverse_neutralize_budget()
    test_probe_failure_hands_over()
    test_probe_hard_cap()
    test_probe_failure_emits_no_stage()
    test_route_fn_overrides_probe()
    test_other_hole_counts_no_probe()
    print('==== %s（%d/%d 通過）' %
          ('全部通過' if all(PASS) else '有失敗', sum(PASS), len(PASS)))
    return 0 if all(PASS) else 1


if __name__ == '__main__':
    sys.exit(main())
