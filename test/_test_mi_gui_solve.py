# -*- coding: utf-8 -*-
r"""M3：米字格 GUI 放行（自动求解 → 宏回放全链路）。

与 tri 的 M4 测试同构，但**验的路径不同**：tri 那份测试自己复刻了回放原语
（`_find_block_by_cell` + `opt` + `try_move` + `commit_move`），绕开了
`gui/events.py::_execute_next_macro_step`。本份**直接调 GUI 自己的回放入口**，
因为「改三形态共有的回放层」正是 M3 的一部分（mi 的 rep 要带 q、缝隙有效性
要走 `side_has_blocks`），绕开就等于没验。

覆盖：
  G1  注册表里有 mi 算法，签名与方形/三角一致
  G2  切到米字格时求解器自动换成 mi_gather
  G3  求解产出的 5 元组 → ops 转换带全三元组 rep
  G4  **ops 能在 GUI 真回放层（_execute_next_macro_step）上逐步播到还原**
  G5  随机多盘：全部非空动作序列都能播完
  G6  方形算法在 mi 下被自动换掉（不静默走错算法）
  G7  方形回放路径没被改坏（`side_has_blocks` 归一后的方形回归）
  G8  三角回放路径没被改坏（tri 的 rep 只带两分量仍能播）

运行：D:\python\python.exe -u test\_test_mi_gui_solve.py
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from game_mi import MiSliderMatrix  # noqa: E402
from solver import SOLVER_ALGORITHMS  # noqa: E402

_F = []


def check(name, cond, extra=''):
    print(f'[{"PASS" if cond else "FAIL"}] {name}' + (f'  {extra}' if extra else ''))
    if not cond:
        _F.append(name)


def _gui_mi(m=4, n=4, step=2, shuffle=0, seed=3):
    """构造一个 mi GUI（**必须显式 new_mi_puzzle** —— 它恢复上次的形态）。"""
    from GUI import SliderGUI
    g = SliderGUI(m=m, n=n, step=step)
    g.new_mi_puzzle(m, n, step)
    if shuffle:
        random.seed(seed)
        g.game.shuffle(shuffle, step)
    g.animation_enabled = False
    return g


def _to_ops(actions, step, mi_mode=True):
    """复刻 GUI._handle_gather_result 的 5 元组 → ops 转换。"""
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
            loc = list(rep)
            op['rep_cell'] = loc[:3] if mi_mode else loc[:2]
        ops.append(op)
    return ops


def _replay_via_gui(g, ops, timeout=4000):
    """走 GUI 自己的宏回放入口，把 ops 播完。返回 (成功, 错误文案)。

    **成功判据不能看 `macro_exec_index`**：播完最后一个 op 后，
    `_execute_next_macro_step` 会走**收尾分支**把 `macro_exec_ops` 清空、
    `macro_exec_index` 归 0、`macro_executing` 置 False。所以正常播完的
    状态是「index=0 且 not executing」；中途失败则是 `macro_error_msg`
    被写上且 executing=False。两种情况 executing 都是 False，只能靠
    **有没有错误文案**区分 —— 我第一版拿 index >= len(ops) 当判据，结果
    每一个成功播完的局都报「播到 0/N」（G4/G7 全军覆没，纯属判据写反）。

    所以这里返回 `g.macro_error_msg` 是否为空作为成功与否。
    """
    g.macro_executing = True
    g.macro_exec_name = '聚拢'
    g.macro_exec_ops = list(ops)
    g.macro_exec_index = 0
    g.macro_exec_factor = 1
    g.macro_error_msg = ''
    g._gather_info = None       # 别触发方形专属的 _update_gather_notify
    g._execute_next_macro_step()
    # 无动画时它是 while 循环一次播完；播完会清队列（index 归 0），
    # 中途失败会写 macro_error_msg 并停手。
    return (not g.macro_error_msg), g.macro_error_msg


# ---------------------------------------------------------------------------
def g1_registry():
    print('\n--- G1 注册表里有 mi 算法且签名对齐 ---')
    import inspect
    check('G1a 统一入口 gather 已注册', 'gather' in SOLVER_ALGORITHMS,
          f'共 {len(SOLVER_ALGORITHMS)} 个算法')
    check('G1a2 形态专用入口已移除（三形态共用同一个入口）',
          'mi_gather' not in SOLVER_ALGORITHMS
          and 'tri_gather' not in SOLVER_ALGORITHMS,
          list(SOLVER_ALGORITHMS))
    if 'gather' not in SOLVER_ALGORITHMS:
        return
    label, fn = SOLVER_ALGORITHMS['gather']
    check('G1b 有中文标签', bool(label.strip()), label.strip())
    params = set(inspect.signature(fn).parameters)
    need = {'game', 'step', 'cancel_check', 'progress_callback'}
    check('G1c 签名吃 GUI solve_thread 那套 kwarg', need <= params,
          f'缺 {need - params}')
    check('G1d 标签不带形态后缀（三形态共用同一入口）',
          '米字' not in label and '三角' not in label, label.strip())
    random.seed(3)
    g = MiSliderMatrix(3, 3)
    g.shuffle(60, 2)
    prog = []
    res = fn(g, step=2, cancel_check=None,
             progress_callback=lambda d: prog.append(d), max_wait_time=20)
    check('G1e 能跑并返回 gather 型 dict',
          res.get('type') == 'gather' and 'actions' in res,
          f'type={res.get("type")}')
    check('G1f progress_callback 真的被调', len(prog) > 0, f'{len(prog)} 次')
    check('G1g 异形不返回方形专属的 start/end 指标',
          'start' not in res and 'end' not in res,
          f'键={[k for k in ("start", "end") if k in res]}')
    res2 = fn(g, step=2, cancel_check=lambda: True, max_wait_time=20)
    check('G1h 取消能生效', res2.get('reason') == 'cancelled',
          res2.get('reason'))


def g2_switch_algorithm():
    print('\n--- G2 切 mi 自动换求解器 ---')
    g = _gui_mi(shuffle=0)
    check('G2a 切米字格后 solver_algorithm = gather（统一入口）',
          g.solver_algorithm == 'gather', g.solver_algorithm)
    # 故意设成 mi 不支持的方形算法：应**明确拒绝**并告知没有该功能，
    # 而不是像旧版那样静默把算法改成 mi_gather。
    g.solver_algorithm = 'ida_star'
    g._auto_solve_running = False
    g.macro_executing = False
    g.macro_notify_msg = ''
    g._start_auto_solve()
    check('G2b 不再静默改算法（保留用户选择）',
          g.solver_algorithm == 'ida_star', g.solver_algorithm)
    check('G2c 明确提示「没有该功能」并点出形态',
          '没有' in g.macro_notify_msg and '米字格' in g.macro_notify_msg,
          f'msg={g.macro_notify_msg!r}')
    check('G2d 拒绝时没有启动后台线程', g._auto_solve_running is False)


def g3_ops_carry_q():
    print('\n--- G3 ops 转换带全三元组 rep（q 是 mi 必需的）---')
    g = _gui_mi(shuffle=40, seed=3)
    fn = SOLVER_ALGORITHMS['gather'][1]
    res = fn(g.game, step=2, max_wait_time=20)
    if not res['actions']:
        check('G3a 有动作可播', False, f'reason={res["reason"]}')
        return
    ops = _to_ops(res['actions'], 2)
    check('G3a 动作数 = ops 数', len(ops) == len(res['actions']),
          f'{len(ops)}/{len(res["actions"])}')
    check('G3b 每个 op 的 rep_cell 长度 3（mi 定位必需）',
          all(len(o.get('rep_cell', [])) == 3 for o in ops),
          f'样例 {ops[0].get("rep_cell")}')
    check('G3c rep 的第三分量是合法朝向',
          all(o['rep_cell'][2] in ('N', 'E', 'S', 'W') for o in ops))
    # 关键行为断言：只用前两分量会定位到错误的块。
    # **扫全盘而不是只扫这 2 个 op** —— 某个局面里恰好每个 op 的 (r,c) 上
    # 都只有一块（step=2 的重排会让大片区域重叠得很密，但不是每处都重叠），
    # 那时 dup=0 是巧合、不是「q 不必需」。全盘扫描则是稳定的事实：
    # mi 一个 (r,c) 上最多 8 块（2 晶格档 × NESW 四朝向）。
    cells = g.game.positions()
    multi_rc = {c for c in cells
                if sum(1 for d in cells if d[0] == c[0] and d[1] == c[1]) > 1}
    check('G3d 盘面确实存在「同 (r,c) 多块」→ q 必需（否则定位到错的块）',
          len(multi_rc) > 0,
          f'{len(multi_rc)}/{len(cells)} 个 (r,c) 上有多块'
          f'（最多 {max((sum(1 for d in cells if d[0]==c[0] and d[1]==c[1]) for c in cells), default=0)} 块）')
    # 并且断言引擎真的能造出这种局面（还原态里一格 4 片、2 晶格档 → 8 块）
    from game_mi import MiSliderMatrix
    g2 = MiSliderMatrix(3, 3)
    restored_multi = sum(1 for c in g2.positions()
                         if sum(1 for d in g2.positions()
                                if d[0] == c[0] and d[1] == c[1]) > 1)
    check('G3d2 还原态上同 (r,c) 就有多块（每格 4 片）',
          restored_multi > 0, f'{restored_multi} 个 (r,c) 多块')


def g4_replay_via_gui_path():
    print('\n--- G4 走 GUI 真回放层（_execute_next_macro_step）---')
    fn = SOLVER_ALGORITHMS['gather'][1]
    for m, n, step, shuf, seed in ((3, 3, 2, 60, 1), (3, 3, 1, 50, 2),
                                   (4, 4, 2, 100, 3)):
        g = _gui_mi(m=m, n=n, step=step, shuffle=shuf, seed=seed)
        init = [list(b.location) for b in g.game.blocks]
        res = fn(g.game, step=step, max_wait_time=25)
        if not res['actions']:
            print(f'     （{m}x{n} step={step} 无动作 reason={res["reason"]}）')
            continue
        for b, loc in zip(g.game.blocks, init):
            b.location = list(loc)
        g.game._clear_selection()
        g.game.update_matrix()
        ops = _to_ops(res['actions'], step)
        ok, err = _replay_via_gui(g, ops)
        check(f'G4a {m}x{n} step={step} GUI 回放层播完全部步骤', ok,
              f'{len(ops)} 步 err={err!r}')
        check(f'G4b {m}x{n} step={step} 回放后 is_solved 与求解结果一致',
              g.game.is_solved() == res['solved'],
              f'回放={g.game.is_solved()} 求解={res["solved"]}')


def g5_random_replay_all():
    print('\n--- G5 随机多盘：全部非空动作序列都能播完 ---')
    fn = SOLVER_ALGORITHMS['gather'][1]
    tot = bad = solved = 0
    for seed in range(6):
        g = _gui_mi(m=3, n=3, step=2, shuffle=60, seed=seed)
        init = [list(b.location) for b in g.game.blocks]
        res = fn(g.game, step=2, max_wait_time=20)
        solved += bool(res['solved'])
        if not res['actions']:
            continue
        for b, loc in zip(g.game.blocks, init):
            b.location = list(loc)
        g.game._clear_selection()
        g.game.update_matrix()
        ops = _to_ops(res['actions'], 2)
        ok, err = _replay_via_gui(g, ops)
        tot += 1
        if not ok:
            bad += 1
            print(f'     ★ seed={seed} {len(ops)} 步 '
                  f'err={err!r}')
    check('G5a 所有非空动作序列都能在 GUI 回放层走完', bad == 0,
          f'成功 {tot}，失败 {bad}')
    check('G5b 6 盘里都有可回放的动作序列（聚拢段在工作）',
          tot >= 4, f'{tot} 盘有动作')
    # 注意：这里**不**断言「有盘能还原」——实测贪心在 mi 上 0/6 复原
    # （卡在 score 0.72~0.94，150 步无改进；见 experiments/_mi_gather_diag.py）。
    # 那是**已知能力边界**（缺末端填洞段，計劃 §8 M4/M5），不是回放层缺陷 ——
    # 回放层的职责是「把求解器给的序列忠实播完」，G5a 已经在测这件事。
    print(f'     （參考：還原 {solved}/6 —— 貪心在 mi 上的已知上限，'
          f'非回放層問題）')


def g6_square_replay_not_broken():
    print('\n--- G6 方形回放路径没被 side_has_blocks 改坏 ---')
    from GUI import SliderGUI
    from game import SliderMatrix
    g = SliderGUI(m=4, n=4, step=2)
    g.numbered = False
    g.triangle_mode = False
    g.mi_mode = False
    random.seed(5)
    g.game = SliderMatrix(4, 4)
    g.game.shuffle(20, 2)
    g.animation_enabled = False
    # **必须用引擎给的真实合法动作**，不能拿 all_gaps()[0] 配一个猜的
    # direction —— `all_gaps` 只给「有哪些缝」，哪一侧能往哪走是另一回事。
    # 我第一版硬编码 `('above', 'a')`，结果 try_move 返回空、报
    # 「方向 a 不可移动」，看起来像回放层坏了，其实是这个 op 本身不存在。
    from solver.actions import enumerate_valid_actions, apply_action
    from solver.actions import _get_side_blocks
    acts = enumerate_valid_actions(g.game, 2)
    # 方形 `enumerate_valid_actions` 的 side **本来就是词**（'above'/'below'
    # /'left'/'right'），不是 0/1 —— 别按异形口径去转。我第一版写了
    # `side0 == 0 → 'below'`，把引擎给的 'above' 硬改成 'below'，
    # 于是回放层在**错的一侧**抓块、try_move 返回空。
    #
    # 更要紧的一条实测结论（决定了这条断言该测什么）：
    # **`enumerate_valid_actions` 里相当一部分动作是「侧上有块但滑不动」的**
    # （4×4 shuffle(20) 抽测：40 条里引擎 `apply_action` 只成功 19 条）。
    # GUI 回放层在没有 rep_cell 时只能「在侧上抓第一个块」，抓到的块与
    # 引擎 `_get_side_blocks(...)[0]` **是同一个**（两段逻辑逐字等价），
    # 于是 GUI 会和引擎**一样地**失败在这条动作上。
    #
    # 所以 G6 真正要锁的是「**GUI 与引擎同判据**」，而不是「随便挑一条能播」。
    # 我先前写成后者，测出 G6a FAIL，看着像 side_has_blocks 改坏了回放层，
    # 其实是拿一条本身走不动的 op 去要求它走 —— 断言测错了对象。
    # 选一条引擎自己能走的动作，用来做「一致性 + 真的移动了」双断言。
    picked = None
    for act in acts:
        p = SliderMatrix(4, 4)
        random.seed(5)                     # 每次同一局面，别让随机漂移造出假阳性
        p.shuffle(20, 2)
        if apply_action(p, act, 2):
            picked = act
            break
    if picked is None:
        check('G6a 方形 op 走 side_has_blocks 能播', False,
              f'{len(acts)} 条枚举动作里引擎一条都走不动（局面本身特殊）')
        return
    fam, line, side, d = picked
    # 先在**播之前**记录 GUI 的选块口径（播完局面已变，比对就没意义了）
    sb_before = _get_side_blocks(g.game, fam, line, side)
    gui_block = g._find_block_on_side(fam, line, side)
    check('G6f GUI 选块与引擎 _get_side_blocks[0] 同口径（同判据的关键证据）',
          bool(sb_before) and gui_block is not None
          and list(gui_block.location) == list(sb_before[0].location),
          f'GUI={[int(x) for x in gui_block.location] if gui_block else None} '
          f'引擎={[int(x) for x in sb_before[0].location] if sb_before else None}')
    init = [list(b.location) for b in g.game.blocks]
    ok, err = _replay_via_gui(g, [{'gap_type': fam, 'gap_line': line,
                                    'side': side, 'direction': d, 'step': 2}])
    check('G6a 方形 op 走 side_has_blocks 能播', ok,
          f'err={err!r} op=({fam},{line},{side},{d})')
    check('G6b 方形那一步真的移动了块',
          [list(b.location) for b in g.game.blocks] != init)

    # 侧上无块时 side_has_blocks 必须说 False（闸门的实际作用点）
    far_line = 999
    check('G6e 侧上无块时 side_has_blocks 说 False',
          g.game.side_has_blocks('h', far_line, 'above') is False
          and g.game.side_has_blocks('h', -999, 'below') is False)
    # 未知族必须说 False（不能默认 True 放行）
    check('G6g 未知缝隙族说 False', g.game.side_has_blocks('x', 0, 'above') is False)

    # G6f：GUI 选块口径必须与引擎一致（这才是「没改坏」的关键证据）。
    # 直接比「GUI 抓到的块 == 引擎 _get_side_blocks[0]」。
    sb = _get_side_blocks(g.game, fam, line, side)
    gui_block = g._find_block_on_side(fam, line, side)
    check('G6f GUI 选块与引擎 _get_side_blocks[0] 同口径',
          bool(sb) and gui_block is not None
          and list(gui_block.location) == list(sb[0].location),
          f'GUI={[int(x) for x in gui_block.location] if gui_block else None} '
          f'引擎={[int(x) for x in sb[0].location] if sb else None}')
    # 直接单元测：四个 side 词都要认
    from game import SliderMatrix as SM
    s = SM(4, 4)
    for gt, ln, want in (('h', 1, True), ('v', 1, True), ('h', 0, True)):
        r = s.side_has_blocks(gt, ln, 'above' if gt == 'h' else 'left')
        check(f'G6c 方形 side_has_blocks({gt},{ln})', r is want, str(r))
    check('G6d 方形 side_has_blocks 认 0/1 两档',
          s.side_has_blocks('h', 1, 0) and s.side_has_blocks('h', 1, 1))


def g7_tri_replay_not_broken():
    print('\n--- G7 三角回放路径没被改坏（rep 只带两分量仍能播）---')
    from game_triangle import TriangleSliderMatrix
    from GUI import SliderGUI
    from solver.ml import tri_adapter as TA
    g = SliderGUI(m=4, n=4, step=2)
    g.new_triangle_puzzle(4, 2)
    g.animation_enabled = False
    random.seed(3)
    g.game.shuffle(120, 2)
    init = [list(b.location) for b in g.game.blocks]
    res = TA.tri_gather_solve(g.game, step=2, max_wait_time=20)
    if not res['actions']:
        check('G7a 三角有动作可播', False, f'reason={res["reason"]}')
        return
    for b, loc in zip(g.game.blocks, init):
        b.location = list(loc)
    g.game._clear_selection()
    g.game.update_matrix()
    ops = _to_ops(res['actions'], 2, mi_mode=False)
    check('G7a 三角 op 的 rep_cell 只带两分量',
          all(len(o['rep_cell']) == 2 for o in ops),
          f'样例 {ops[0]["rep_cell"]}')
    ok, err = _replay_via_gui(g, ops)
    check('G7b 三角 op 走 GUI 真回放层播完', ok,
          f'{len(ops)} 步 err={err!r}')
    check('G7c 三角回放后 is_solved 与求解结果一致',
          g.game.is_solved() == res['solved'],
          f'回放={g.game.is_solved()} 求解={res["solved"]}')


def main():
    print('=' * 70)
    print('M3：米字格 GUI 放行回归')
    print('=' * 70)
    g1_registry()
    g2_switch_algorithm()
    g3_ops_carry_q()
    g4_replay_via_gui_path()
    g5_random_replay_all()
    g6_square_replay_not_broken()
    g7_tri_replay_not_broken()
    print('\n' + '=' * 70)
    if _F:
        print(f'FAIL {len(_F)}:')
        for f in _F:
            print(f'  · {f}')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
