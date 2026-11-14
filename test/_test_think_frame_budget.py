# -*- coding: utf-8 -*-
"""特大尺寸段间「思考演示」选步的一帧预算护栏（待办 §四十三，2026-11-15）。

背景：段间等待期每 walk_frames 帧在主线程同步调 _think_find_move 选一步。
实测（真实引擎 + 公式生成盘面 + 离屏真 GUI 60fps 逐帧采样）：
  · 抽样命中 18 次 opt：6×6 5ms → 14×14 27~43ms（已超一帧 16.7ms）；
  · 抽样落空退回「全量枚举」时**没有上限**：blocks × gaps 次 opt，
    6×6 0.15s → 12×12 6.5s → 14×14 5096 次 / 10.5s；
  · 真 GUI 段间 300 帧：14×14 有 92 帧 >50ms、19 帧 >100ms、最大 156ms；
    关掉思考演示后降到 28 帧 >50ms、最大 103ms ⇒ 选步是主要放大器。
修法：一次选步（抽样 + 兜底 + 打分）共用墙钟预算与 opt 次数上限，
到点用已收集候选收尾；**不按尺寸硬切**（上一版按尺寸猜路由已被审查
否决：8×8 近复原盘实测慢 10~100 倍、证据全落在规则不触发的档位）。

护栏纪律（§23 + 项目「证据与护栏纪律」）：
  · 盘面全部由文件内公式生成（满矩形 / 近复原），**不读任何存档**；
  · 判据驱动真实入口 _think_find_move + 真实引擎 opt/try_move，盯行为
    （opt 调用次数、墙钟、be_opted 选中态），不查源码字符串；
  · 真刀反向验证：把类常量中和成「不设限」，同一典例的 opt 次数与墙钟
    必须大幅回弹（判据转红），且全程 try/finally 还原；
  · 抽样命中路径与小尺寸行为不受伤（20/20 仍能找到步）。

运行：D:/python/python.exe test/_test_think_frame_budget.py（项目根目录）
"""
import contextlib
import io
import os
import random
import sys
import time
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from game import SliderMatrix, Block  # noqa: E402
from gui.auto_solve import AutoSolveMixin  # noqa: E402

PASS = []


def check(name, cond, note=''):
    PASS.append(bool(cond))
    print('%s %s%s' % ('PASS' if cond else 'FAIL', name,
                       ('（%s）' % note) if note else ''))


# ---- 可生成几何典例（全部公式生成，不读存档）------------------------------
def board_full(m, n):
    """满矩形复原态。"""
    return [(r, c) for r in range(m) for c in range(n)]


def board_near(m, n):
    """近复原态：挖两个洞、窗外补两个块（几何典例，可逐位重放）。"""
    s = {(r, c) for r in range(m) for c in range(n)}
    s -= {(0, 2), (1, 0)}
    s |= {(m - 2, n), (m - 1, n)}
    return sorted(s)


def connected(coords):
    """4 邻接连通性自检：避免拿不连通的假盘面做证据（上一轮踩过）。"""
    S = set(coords)
    start = next(iter(S))
    seen = {start}
    stack = [start]
    while stack:
        r, c = stack.pop()
        for nb in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if nb in S and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen) == len(S)


class CountingGame(SliderMatrix):
    """真实引擎 + opt 调用计数（只加计数，不改任何语义）。"""

    def __init__(self, m, n, coords):
        super().__init__(m, n)
        self.blocks = [Block([r, c]) for r, c in coords]
        self.matrix = None
        self.update_matrix()
        self.opt_calls = 0

    def opt(self, *a, **k):
        self.opt_calls += 1
        return super().opt(*a, **k)


class Host(AutoSolveMixin):
    """最小宿主：只接 _think_find_move 需要的三个接口，全委托真实引擎。"""

    def __init__(self, m, n, step, coords):
        self.game = CountingGame(m, n, coords)
        self.current_step = step
        self._think_last_move = None

    def _ann_all_valid_gaps(self):
        g = self.game
        b = g.get_boundaries()
        out = []
        for i in range(b['min_row'], b['max_row']):
            if g.is_valid_h_line(i):
                out.append(('h', i))
        for j in range(b['min_col'], b['max_col']):
            if g.is_valid_v_line(j):
                out.append(('v', j))
        return out

    def _ann_dirs_for_gap(self, gt):
        return {'h': ('a', 'd'), 'v': ('w', 's')}.get(gt, ())


_WARMED = [False]


def _warmup():
    """首次调用的冷启动（import 聚拢度模块 / numpy 初始化）可达 0.3s，
    与选步本身无关。先不计时空跑一次，让所有墙钟判据量的是稳态成本。
    """
    if _WARMED[0]:
        return
    _WARMED[0] = True
    h = Host(6, 6, 2, board_full(6, 6))
    random.seed(1)
    with contextlib.redirect_stdout(io.StringIO()):
        h._think_find_move()


def run_step(m, n, coords, seed=7, force_fallback=False):
    """驱动真实入口，返回 (spec, 墙钟, opt 次数, host)。"""
    _warmup()
    host = Host(m, n, 2, coords)
    random.seed(seed)
    t0 = time.perf_counter()
    if force_fallback:
        # 让两次 random.sample 都返回空池 → 抽样必然落空 → 稳定走兜底分支。
        # 这是驱动真实入口的行为注入，不是源码字符串判据。
        with mock.patch('random.sample', return_value=[]):
            with contextlib.redirect_stdout(io.StringIO()):
                spec = host._think_find_move()
    else:
        with contextlib.redirect_stdout(io.StringIO()):
            spec = host._think_find_move()
    return spec, time.perf_counter() - t0, host.game.opt_calls, host


# ---------------------------------------------------------------------------
def test_constants():
    """常量存在且合理；必须是类属性（护栏可真刀中和）。"""
    b = getattr(AutoSolveMixin, 'THINK_STEP_BUDGET_S', None)
    c = getattr(AutoSolveMixin, 'THINK_MAX_OPT_CALLS', None)
    s = getattr(AutoSolveMixin, 'THINK_MAX_SCORED', None)
    check('B1 墙钟预算存在且不超过一帧', isinstance(b, (int, float))
          and 0 < b <= 0.0167, 'BUDGET=%s' % b)
    check('B2 opt 次数上限存在且为正', isinstance(c, int) and c > 0,
          'MAX_OPT=%s' % c)
    check('B3 打分候选上限存在且为正', isinstance(s, int) and s > 0,
          'MAX_SCORED=%s' % s)


def test_geometric_examples():
    """几何典例自检：全部公式生成、连通、可重放。"""
    for m, n in ((6, 6), (12, 12), (14, 14)):
        full = board_full(m, n)
        near = board_near(m, n)
        check(f'G{m} {m}x{n} 满矩形块数正确', len(full) == m * n)
        check(f'G{m} {m}x{n} 满矩形连通', connected(full))
        check(f'G{m} {m}x{n} 近复原连通', connected(near))
        check(f'G{m} {m}x{n} 典例可逐位重放',
              board_full(m, n) == full and board_near(m, n) == near)


def test_sample_path_healthy():
    """抽样命中路径不回归：各尺寸仍能找到步、仍是抽样、选中态干净。"""
    for m, n in ((6, 6), (10, 10), (12, 12), (14, 14)):
        spec, dt, opt, host = run_step(m, n, board_full(m, n))
        check(f'S{m} {m}x{n} 抽样命中能找到步', spec is not None,
              'dt=%.4fs opt=%d' % (dt, opt))
        check(f'S{m} {m}x{n} 仍是抽样（opt ≤ 18）', opt <= 18,
              'opt=%d' % opt)
        check(f'S{m} {m}x{n} 单帧墙钟 ≤ 0.06s', dt <= 0.06,
              '%.4fs' % dt)
        if spec is not None:
            check(f'S{m} {m}x{n} 终态非空且为 list',
                  isinstance(spec[3], list) and len(spec[3]) > 0)
            sel = [b for b in host.game.blocks if b.be_opted]
            check(f'S{m} {m}x{n} 选中态恰好留给提交方',
                  0 < len(sel) < len(host.game.blocks), 'sel=%d' % len(sel))


def test_fallback_capped():
    """核心修复：抽样落空的兜底被硬闸截断，不再随尺寸爆炸。"""
    for m, n, old_s in ((6, 6, 0.15), (10, 10, 2.8),
                        (12, 12, 6.5), (14, 14, 10.5)):
        spec, dt, opt, host = run_step(m, n, board_full(m, n),
                                       force_fallback=True)
        cap = AutoSolveMixin.THINK_MAX_OPT_CALLS
        check(f'C{m} {m}x{n} 兜底 opt ≤ {cap}', opt <= cap,
              'opt=%d（旧全量 %d）' % (opt, m * n * (2 * m - 2)))
        check(f'C{m} {m}x{n} 兜底墙钟 ≤ 0.10s', dt <= 0.10,
              '%.4fs（旧实测约 %.1fs）' % (dt, old_s))
        check(f'C{m} {m}x{n} 不抛异常且返回合法协议',
              spec is None or isinstance(spec, tuple))
        if spec is None:
            check(f'C{m} {m}x{n} 无步时选中态全清',
                  not any(b.be_opted for b in host.game.blocks))
    # 近复原典例同样受控（真实求解段末盘面形态）
    spec, dt, opt, _ = run_step(14, 14, board_near(14, 14),
                                force_fallback=True)
    check('C9 14×14 近复原兜底 opt 受控', opt <= AutoSolveMixin.THINK_MAX_OPT_CALLS,
          'opt=%d' % opt)
    check('C10 14×14 近复原兜底墙钟 ≤ 0.10s', dt <= 0.10, '%.4fs' % dt)


def test_scoring_capped():
    """打分阶段也受同一预算：gather_metrics 调用数不超过候选上限。"""
    calls = [0]
    from solver.ml import gather_solver
    real = gather_solver.gather_metrics

    def spy(coords, m, n):
        calls[0] += 1
        return real(coords, m, n)

    with mock.patch.object(gather_solver, 'gather_metrics', side_effect=spy):
        run_step(14, 14, board_full(14, 14), force_fallback=True)
    check('P1 打分候选数受上限约束',
          calls[0] <= AutoSolveMixin.THINK_MAX_SCORED + 1,
          'gather_metrics 调用 %d 次（上限 %d + pre 一次）'
          % (calls[0], AutoSolveMixin.THINK_MAX_SCORED))


def test_reverse_neutralize_budget():
    """真刀反向验证：中和三道闸后，同一典例的枚举量/墙钟必须大幅回弹。

    8×8 旧全量约 896 次 opt / 0.8s；修复后 ≤48 次。中和后必须 >200 次
    且 >0.2s —— 否则说明「兜底被截断」不是这道修复造成的（假绿）。
    """
    cap = AutoSolveMixin.THINK_MAX_OPT_CALLS
    before = run_step(8, 8, board_full(8, 8), force_fallback=True)
    check('R0 中和前 8×8 兜底确实受控', before[2] <= cap,
          'opt=%d' % before[2])

    with mock.patch.object(AutoSolveMixin, 'THINK_STEP_BUDGET_S', 0), \
         mock.patch.object(AutoSolveMixin, 'THINK_MAX_OPT_CALLS', 0), \
         mock.patch.object(AutoSolveMixin, 'THINK_MAX_SCORED', 10 ** 6):
        after = run_step(8, 8, board_full(8, 8), force_fallback=True)
    check('R1 中和后枚举量回弹到全量级（判据会转红）', after[2] > 200,
          'opt %d → %d' % (before[2], after[2]))
    check('R2 中和后墙钟回弹（判据会转红）', after[1] > 0.20,
          '%.4fs → %.4fs' % (before[1], after[1]))
    check('R3 中和后常量已还原',
          AutoSolveMixin.THINK_MAX_OPT_CALLS == cap
          and AutoSolveMixin.THINK_STEP_BUDGET_S > 0)


def test_reverse_each_gate():
    """单独中和每一道闸，另一道仍要兜住（双闸互不依赖）。"""
    cap = AutoSolveMixin.THINK_MAX_OPT_CALLS
    # 只放开墙钟：次数闸仍要压住枚举量
    with mock.patch.object(AutoSolveMixin, 'THINK_STEP_BUDGET_S', 0):
        spec, dt, opt, _ = run_step(10, 10, board_full(10, 10),
                                    force_fallback=True)
    check('R4 只放开墙钟，次数闸仍压住 opt', opt <= cap, 'opt=%d' % opt)
    # 只放开次数：墙钟闸仍要压住耗时
    with mock.patch.object(AutoSolveMixin, 'THINK_MAX_OPT_CALLS', 0):
        spec, dt, opt, _ = run_step(10, 10, board_full(10, 10),
                                    force_fallback=True)
    check('R5 只放开次数，墙钟闸仍压住耗时', dt <= 0.10,
          '%.4fs opt=%d' % (dt, opt))


def test_uniform_budget_not_size_switch():
    """统一预算而非尺寸阈值：小/中/大盘用同一组常量、同样受控。

    （上一版按尺寸硬切被审查否决；这里用行为证明没有 8×8/10×10 分界。）
    """
    small = run_step(6, 6, board_full(6, 6), force_fallback=True)
    large = run_step(14, 14, board_full(14, 14), force_fallback=True)
    check('U1 6×6 与 14×14 用同一个 opt 上限',
          small[2] <= AutoSolveMixin.THINK_MAX_OPT_CALLS
          and large[2] <= AutoSolveMixin.THINK_MAX_OPT_CALLS,
          'opt=%d / %d' % (small[2], large[2]))
    check('U2 6×6 兜底也不再超一帧量级', small[1] <= 0.10,
          '%.4fs（旧 0.15s）' % small[1])


def test_zz_all_guardrails():
    """pytest 兜底：check() 只 print 不 raise，末尾显式断言防假绿。"""
    assert all(PASS), '有护栏未通过：%d/%d' % (sum(PASS), len(PASS))


def main():
    test_constants()
    test_geometric_examples()
    test_sample_path_healthy()
    test_fallback_capped()
    test_scoring_capped()
    test_reverse_neutralize_budget()
    test_reverse_each_gate()
    test_uniform_budget_not_size_switch()
    print('==== %s（%d/%d 通过）' %
          ('全部通过' if all(PASS) else '有失败', sum(PASS), len(PASS)))
    return 0 if all(PASS) else 1


if __name__ == '__main__':
    sys.exit(main())
