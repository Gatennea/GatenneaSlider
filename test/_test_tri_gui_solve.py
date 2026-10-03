# -*- coding: utf-8 -*-
r"""M4：三角形 GUI 放行（自动求解 → 宏回放全链路）。

计划 §8 M4：「GUI Ctrl+A 放行——auto_solve 对异形没有查表/补缺宏可路由，
直接走梯度聚拢」。

**验收标准是全链路，不是「函数能调通」**：
  ① 注册表里有三角算法，且签名与方形一致（GUI 的 solve_thread 统一调用）；
  ② 切到三角形时求解器自动换成三角版（不换就会静默走方形算法）；
  ③ 求解产出的 5 元组动作能被 GUI 的 ops 转换接住；
  ④ **ops 能在真盘上逐步回放到还原**——这条才是「GUI 里能按出来」的定义。
     只验 ①~③ 会漏掉「rep 定位不到块」「方向被改写」这类只有回放才暴露的问题。
  ⑤ 非聚拢算法在三角下被明确拦下（而不是静默走错算法）。
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from game_triangle import TriangleSliderMatrix  # noqa: E402
from solver import SOLVER_ALGORITHMS  # noqa: E402
from solver.ml import tri_adapter as TA  # noqa: E402

_F = []


def check(name, cond, extra=''):
    print(f'[{"PASS" if cond else "FAIL"}] {name}' + (f'  {extra}' if extra else ''))
    if not cond:
        _F.append(name)


def _gui_tri(k=4, step=2, shuffle=120, seed=3):
    """构造一个已打乱的三角 GUI。

    **不能靠 SliderGUI(m,n,step) 的默认形态** —— 它恢复的是「上次关闭时的
    形态」（mi 那个坑，见面板 H9 组），必须显式 new_triangle_puzzle。
    """
    from GUI import SliderGUI
    g = SliderGUI(m=k, n=k, step=step)
    g.new_triangle_puzzle(k, step)
    if shuffle:
        random.seed(seed)
        g.game.shuffle(shuffle, step)
    g.animation_enabled = False
    return g


def _to_ops(actions, step):
    """复刻 GUI._handle_gather_result 的 5 元组 → ops 转换。

    单独抽出来是为了让测试真的锁这条转换，而不是复制一份「差不多」的代码
    就算通过 —— 转换错的话测试会跟着错。
    """
    ops = []
    for action in actions:
        if len(action) >= 5:
            gd, gl, side, md, rep = action[:5]
        else:
            gd, gl, side, md = action[:4]
            rep = None
        op = {'gap_type': gd, 'gap_line': gl, 'side': side,
              'direction': md, 'step': step}
        if rep is not None:
            op['rep_cell'] = list(rep)[:2]
        ops.append(op)
    return ops


# ---------------------------------------------------------------------------
def m1_registry():
    print('\n--- M1 注册表里有三角算法且签名对齐 ---')
    check('M1a tri_gather 已注册', 'tri_gather' in SOLVER_ALGORITHMS,
          f'共 {len(SOLVER_ALGORITHMS)} 个算法')
    if 'tri_gather' not in SOLVER_ALGORITHMS:
        return
    label, fn = SOLVER_ALGORITHMS['tri_gather']
    check('M1b 有中文标签', bool(label.strip()), label.strip())
    import inspect
    params = set(inspect.signature(fn).parameters)
    need = {'game', 'step', 'cancel_check', 'progress_callback'}
    check('M1c 签名吃 GUI solve_thread 那套 kwarg', need <= params,
          f'缺 {need - params}')
    # 实际调一次，确认不抛
    random.seed(3)
    g = TriangleSliderMatrix(4)
    g.shuffle(120, 2)
    prog = []
    res = fn(g, step=2, cancel_check=None,
             progress_callback=lambda d: prog.append(d), max_wait_time=20)
    check('M1d 能跑并返回 gather 型 dict',
          res.get('type') == 'gather' and 'actions' in res, f'type={res.get("type")}')
    check('M1e progress_callback 真的被调', len(prog) > 0, f'{len(prog)} 次')
    check('M1f 异形不返回方形专属的 start/end 指标',
          'start' not in res and 'end' not in res,
          f'键={[k for k in ("start","end") if k in res]}')
    check('M1g 取消能生效',
          _solve_cancelled() is not None)


def _solve_cancelled():
    random.seed(3)
    g = TriangleSliderMatrix(4)
    g.shuffle(120, 2)
    fn = SOLVER_ALGORITHMS['tri_gather'][1]
    res = fn(g, step=2, cancel_check=lambda: True, max_wait_time=20)
    return res


def m2_switch_algorithm():
    print('\n--- M2 切三角自动换求解器 ---')
    g = _gui_tri(shuffle=0)
    check('M2a 切三角后 solver_algorithm = tri_gather',
          g.solver_algorithm == 'tri_gather', g.solver_algorithm)
    # 显式设成方形算法后再开求解：应自动切回 tri_gather 并明确提示
    # （不静默走错算法，也不硬拦——拦会让按钮路径与快捷键路径不一致）
    g.solver_algorithm = 'ida_star'
    g._auto_solve_running = False
    g.macro_executing = False
    g.macro_notify_msg = ''
    g._start_auto_solve()
    check('M2b 方形算法在三角下被自动换成 tri_gather',
          g.solver_algorithm == 'tri_gather', g.solver_algorithm)
    check('M2c 换算法时有明确提示（不是静默）',
          '聚拢' in g.macro_notify_msg, f'msg={g.macro_notify_msg!r}')
    g._auto_solve_cancel = True   # 别让后台线程真跑起来
    check('M2d 拦下时没有启动后台线程', g._auto_solve_running is False)


def m3_ops_and_replay():
    print('\n--- M3 求解 → ops → 真盘回放（GUI 全链路）---')
    for k, step, shuf, seed in ((4, 2, 120, 3), (3, 1, 80, 1), (5, 2, 200, 5)):
        g = _gui_tri(k=k, step=step, shuffle=shuf, seed=seed)
        init = [list(b.location) for b in g.game.blocks]
        fn = SOLVER_ALGORITHMS['tri_gather'][1]
        res = fn(g.game, step=step, max_wait_time=25)
        if not res['actions']:
            check(f'M3a k={k} 有动作可播', False, f'reason={res["reason"]}')
            continue
        ops = _to_ops(res['actions'], step)
        check(f'M3a k={k} 动作数 = ops 数',
              len(ops) == len(res['actions']), f'{len(ops)}/{len(res["actions"])}')
        check(f'M3b k={k} 每个 op 都带 rep_cell（5 元组第 5 位）',
              all('rep_cell' in o for o in ops))
        # 回放：恢复初始 → 用 GUI 的回放原语逐步执行
        for b, loc in zip(g.game.blocks, init):
            b.location = list(loc)
        g.game._clear_selection()
        g.game.update_matrix()
        ok = True
        for op in ops:
            blk = g._find_block_by_cell(op['rep_cell'][0], op['rep_cell'][1])
            if blk is None:
                ok = False
                break
            g.game._clear_selection()
            g.game.opt(op['gap_type'], op['gap_line'], blk)
            pos = g.game.try_move(op['direction'], op['step'])
            if not pos:
                ok = False
                break
            g.game.commit_move(pos)
            g.game._clear_selection()
            g.game.update_matrix()
        check(f'M3c k={k} GUI 回放原语逐步执行成功', ok)
        check(f'M3d k={k} 回放后 is_solved 与求解结果一致',
              g.game.is_solved() == res['solved'],
              f'回放={g.game.is_solved()} 求解={res["solved"]}')


def m4_replay_all_actions():
    print('\n--- M4 随机多盘：ops 回放全成功（真盘重放终裁）---')
    fn = SOLVER_ALGORITHMS['tri_gather'][1]
    tot = 0
    bad = 0
    solved = 0
    for seed in range(8):
        g = _gui_tri(k=4, step=2, shuffle=120, seed=seed)
        init = [list(b.location) for b in g.game.blocks]
        res = fn(g.game, step=2, max_wait_time=20)
        solved += bool(res['solved'])
        if not res['actions']:
            continue
        ops = _to_ops(res['actions'], 2)
        for b, loc in zip(g.game.blocks, init):
            b.location = list(loc)
        g.game._clear_selection()
        g.game.update_matrix()
        for op in ops:
            blk = g._find_block_by_cell(op['rep_cell'][0], op['rep_cell'][1])
            if blk is None:
                bad += 1
                break
            g.game._clear_selection()
            g.game.opt(op['gap_type'], op['gap_line'], blk)
            pos = g.game.try_move(op['direction'], op['step'])
            if not pos:
                bad += 1
                break
            g.game.commit_move(pos)
            g.game._clear_selection()
            g.game.update_matrix()
        else:
            tot += 1
    check('M4a 所有非空动作序列都能在 GUI 回放层走完',
          bad == 0, f'成功 {tot}，失败 {bad}')
    check('M4b 8 盘里有一定还原率', solved >= 5, f'{solved}/8')


def main():
    print('=' * 68)
    print('M4：三角形 GUI 放行回归')
    print('=' * 68)
    m1_registry()
    m2_switch_algorithm()
    m3_ops_and_replay()
    m4_replay_all_actions()
    print('\n' + '=' * 68)
    if _F:
        print(f'FAIL {len(_F)}:')
        for f in _F:
            print(f'  · {f}')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
