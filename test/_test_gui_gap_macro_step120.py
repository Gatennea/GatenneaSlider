"""端到端护栏：step120 经「填洞补缺」(gap_macro) 到 GUI 真实播放器必须播完复原。

用户真实路径：菜单「填洞补缺」→ file_ops 映射 gap_macro → solve_gap_macro
（2 洞走 solve_multi_vacancy）→ 流式段 → GUI `_execute_next_macro_step` 逐步回放。

历史回归（2026-11-12）：求解器产出的动作段里有 2 个 `side=None` 的整线动作。
GUI 播放器每步第一步就 `side_has_blocks(gap, line, None)`，None 时两个分支
都不命中 → 返回 False → 弹「[填洞宏·流水] 执行中断：12/26步」，只播到 ov=56。
而求解器内部 `_capture_apply` 用 rep 定位块、根本不看 side，所以**所有 solver
级测试都绿，唯独用户点按钮必断**——这正是此前反复「误认为已解决」的根源。

修复（gui/events.py `_execute_next_macro_step`）：side=None 且有 rep_cell 时，
按块相对缝隙的位置反推 side（h: rep行<=缝线→above 否则 below；v 同理），
再走正常回放。

本护栏直接构造 SliderGUI、把求解器真实段塞进 macro_exec_ops、驱动真实
`_execute_next_macro_step`（无动画一口气跑完），锁死「必须播到 ov=64、
macro_error_msg 为空」——不再只看函数返回或内部 replay。
"""
import os
import sys
import importlib.util

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

from engine import config as _ecfg  # noqa: E402
_ecfg.set_enabled(False)           # 经典方形引擎

_spec = importlib.util.spec_from_file_location(
    't120', os.path.join(_PROJ, 'test', '_test_gap_macro_step120.py'))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
COORDS = _mod.COORDS

from solver.ml.fill_macro import build_game, gcoords, window_of  # noqa: E402
from solver.ml.gap_solver import solve_gap_macro                  # noqa: E402
from GUI import SliderGUI                                         # noqa: E402

M, N, STEP = 8, 8, 2
_fails = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + ('' if not detail else '  ' + detail))
    if not ok:
        _fails.append(name)


def obtain_ops():
    """跑真实求解器直到拿到完整解（随机贪心偶发 partial，最多试 5 次）。

    返回 (ops_raw, solved)。ops_raw = 5 元组列表 (gap,line,side,d,rep)。
    """
    for _ in range(5):
        g = build_game(COORDS, M, N)
        segs = []
        res = solve_gap_macro(
            g, STEP,
            segment_cb=lambda l, a: segs.append((l, [tuple(x) for x in a])),
            time_budget=30)
        ops = []
        for l, a in segs:
            ops.extend(a)
        solved = (res.get('solved') if isinstance(res, dict) else True)
        if solved and ops:
            return ops, True
    return [], False


def main():
    (r0, c0, wh), ov0, holes, out = window_of(COORDS, M, N, STEP)
    check('P0 盘面锁：64 块 / ov=62 / 两洞两凸',
          len(COORDS) == 64 and ov0 == 62
          and len(holes) == 2 and len(out) == 2,
          'n=%d ov=%d holes=%s' % (len(COORDS), ov0, holes))

    ops_raw, solved = obtain_ops()
    check('P1 求解器产出完整解（含 side=None 动作）',
          solved and len(ops_raw) > 0,
          'ops=%d' % len(ops_raw))
    if not solved:
        print('\nFAILED:', _fails)
        return 1
    n_none = sum(1 for a in ops_raw if a[2] is None)
    print('       （段内 side=None 动作 %d 个 —— 修复前正是它们让 GUI 中断）'
          % n_none)

    gui = SliderGUI(m=M, n=N, step=STEP)
    gui.game = build_game(COORDS, M, N)
    gui.current_step = STEP
    gui.animation_enabled = False
    gui.animation_duration = 0
    gui.macro_error_msg = ''
    gui.macro_exec_ops = []
    for a in ops_raw:
        op = {'gap_type': a[0], 'gap_line': a[1], 'side': a[2],
              'direction': a[3], 'step': STEP}
        if len(a) > 4 and a[4]:
            op['rep_cell'] = a[4]
        gui.macro_exec_ops.append(op)
    gui.macro_exec_index = 0
    gui.macro_executing = True
    gui.macro_exec_name = '填洞宏·流水'
    gui._execute_next_macro_step()

    ov = window_of(frozenset(gcoords(gui.game)), M, N, STEP)[1]
    err = getattr(gui, 'macro_error_msg', '') or ''
    executed = getattr(gui, 'macro_exec_index', -1)

    check('P2 GUI 播放器未中断（macro_error_msg 为空）', err == '',
          'err=%r executed=%s/%d' % (err, executed, len(gui.macro_exec_ops)))
    check('P3 播放到全解 ov=64', ov == M * N and gui.game.is_solved(),
          'end_ov=%d solved=%s' % (ov, gui.game.is_solved()))

    if _fails:
        print('\nFAILED:', _fails)
        return 1
    print('\nALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
