# -*- coding: utf-8 -*-
r"""护栏：带移链「成功返回」分支不得引用已删除的接运局部变量。

背景（#49 ① 验证时由 _test_solver_opt_equiv 的 stderr 暴露）：
  #47 把源接运的单轴循环抽成 `_relay_1d` / `_relay_bump` 后，
  `_band_shift_chain` 成功分支的 verbose 打印与 `info['relay']` 仍引用
  `gap2/line2/side2/d2/k2`——这些变量已随抽出而不在本作用域。
  ⚠️ `'relay': (...)` 那行在**非 verbose 路径也执行**，所以带移链一旦成功
  就抛 NameError；上层 `auto_solver.run_gap` 的 except 打 traceback 后降级，
  功能静默失效、所有既有护栏却全绿（P1~P4 只测 `_relay_bump` 与
  `_edge_band_shift_attempt`，从没让 `_band_shift_chain` 成功返回）。

修法：接运是逐轴多段，没有「单一缝/方向」可言；诊断只记真实可得的
（模式、目标洞位、接运动作数），不再回指 helper 内部枚举变量。

本测试锁（行为级 + 源级撤修复反向验证）：
  P1 正向：fake 驱动走通成功 return，不抛异常、info 合法且 relay 语义正确
     （verbose=False / True 各一次，覆盖 info 字典与 print 两条路径）；
  P2 反向：把生产源码里修好的 info 行**打回旧版**（重新引用 gap2），
     在独立 namespace 里 exec 出旧函数，同样驱动必抛 NameError
     ——证明 P1 判据真能抓到这个 bug，不是恒绿的假护栏；
  P3 补丁确实命中（防止「patch 没生效、测的还是新代码」的假判据）。

⚠️ 反向验证只读内存里的源码字符串、exec 到独立 namespace，不写盘、
   不 reload 模块，天然无中断还原问题；patch 字符串为单行、不含 \n，
   规避 CRLF 仓库的换行符坑。

跑法：D:/python/python.exe -u test/_test_band_shift_chain_info.py
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import solver.ml.fill_macro as FM  # noqa: E402

FM_PATH = os.path.join(ROOT, 'solver', 'ml', 'fill_macro.py')
M = N = 6
STEP = 2
HOLE = (2, 2)
P_SRC = (5, 5)
COORDS = frozenset((r, c) for r in range(M) for c in range(N)
                   if (r, c) != HOLE)

FAILS = []
_MISS = object()

# 修复后的单行 / 修复前的单行（用于源级反向验证）
NEW_LINE = "'relay': (mode2, h_new, len(sub2)),"
OLD_LINE = "'relay': (mode2, gap2, line2, side2, d2, k2 * step),"


def check(name, ok, detail=''):
    print('[%s] %s %s' % ('PASS' if ok else 'FAIL', name, detail))
    if not ok:
        FAILS.append(name)
    return ok


def _make_patches():
    """构造「必然走通成功分支」的 fake，避免依赖难构造的真实可解盘面。

    只替换判定链的外部依赖，真实函数体（含成功分支的诊断构造）照跑。
    """
    calls = {'n': 0}

    def fake_probe(g, gap, line, side, rep0, d, times, step,
                   cancel_check=None):
        calls['n'] += 1
        if calls['n'] == 1:
            # 幽灵盘让位：把洞位幽灵块挪一步，使 h_new != hole。
            # 第三次（回位）绝不能挪，否则「原洞位被填」判据会失败。
            for b in g.blocks:
                if tuple(b.location) == HOLE:
                    b.location = (HOLE[0] + step, HOLE[1])
                    break
        return True, []

    def fake_relay(g1, p_src, h_new, step, cancel_check=None):
        # g2 含洞位块 → 回位后的 g3 里「原洞位被填」判据成立
        g2 = FM.build_game(frozenset(FM.gcoords(g1)) | {HOLE}, M, N)
        return [], g2

    return {
        '_hole_band_seams': lambda hole: [('h', hole[0], 'above')],
        '_es_probe_run': fake_probe,
        '_relay_bump': fake_relay,
        '_replay_apply': lambda *a, **k: True,
        '_overlap_raised': lambda *a, **k: True,
    }


def _drive(fn, verbose=False):
    """把 fake 注入 fn 的 globals 后调用，finally 逐键还原。"""
    gl = fn.__globals__
    patches = _make_patches()
    saved = {k: gl.get(k, _MISS) for k in patches}
    gl.update(patches)
    try:
        return fn(COORDS, M, N, STEP, HOLE, P_SRC, verbose=verbose)
    finally:
        for k, v in saved.items():
            if v is _MISS:
                gl.pop(k, None)
            else:
                gl[k] = v


def _old_fn_from_source():
    """从生产源码 exec 出「info 行打回旧版」的 _band_shift_chain。"""
    with open(FM_PATH, encoding='utf-8') as f:
        src = f.read()
    return src, src.replace(NEW_LINE, OLD_LINE)


def main():
    # ---- P3 先确认补丁命中，否则 P2 的「必抛」没有意义 ----
    src, old_src = _old_fn_from_source()
    check('P3 生产源码含修复后的 info 行且反向补丁命中',
          NEW_LINE in src and OLD_LINE in old_src and old_src != src)

    # ---- P1 正向：成功分支不再引用已删除变量 ----
    for verbose in (False, True):
        try:
            acts, info = _drive(FM._band_shift_chain, verbose=verbose)
            raised = None
        except Exception as e:                # noqa: BLE001
            acts, info, raised = None, None, e
        ok = (raised is None and isinstance(acts, list)
              and isinstance(info, dict)
              and info.get('relay') == ('relay', (HOLE[0] + STEP, HOLE[1]), 0)
              and 'band' in info and 'h_shifted' in info and 'tries' in info)
        check('P1 成功分支不抛异常且 info 合法（verbose=%s）' % verbose,
              ok, 'raised=%r info=%s' % (raised, info))

    # ---- P2 反向：撤掉修复必抛 NameError ----
    ns = dict(FM.__dict__)
    tree = ast.parse(old_src)
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == '_band_shift_chain')
    mod = ast.Module(body=[node], type_ignores=[])
    exec(compile(mod, FM_PATH, 'exec'), ns)   # noqa: S102
    old_fn = ns['_band_shift_chain']
    try:
        _drive(old_fn, verbose=False)
        raised2 = None
    except NameError as e:
        raised2 = e
    except Exception as e:                    # noqa: BLE001
        raised2 = e
    check('P2 反向：info 行打回旧版必抛 NameError（判据有效）',
          isinstance(raised2, NameError), 'raised=%r' % raised2)

    # 还原后真实函数仍正常（patch 没污染模块）
    try:
        a3, i3 = _drive(FM._band_shift_chain, verbose=False)
        clean = isinstance(a3, list) and isinstance(i3, dict)
    except Exception as e:                    # noqa: BLE001
        clean, i3 = False, e
    check('P2 反向验证后模块未被污染', clean, 'info=%s' % i3)

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
