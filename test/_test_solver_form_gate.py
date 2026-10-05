# -*- coding: utf-8 -*-
r"""求解器「形态闸门 + 统一入口」回归锁。

起因是 2026-10-06 用户报 ``[自动求解] 出错: list index out of range``：
config.json 里残留了已删除的旧 key ``'mi_gather'``，而 GUI 的 solve_thread
用 ``SOLVER_ALGORITHMS.get(algorithm, SOLVER_ALGORITHMS['ida_star'])``
**静默兜底成 IDA\***（IDA* 是纯方形语义，套到异形就炸），而且 except 只
print 了异常对象、没打 traceback，导致完全无法定位。

本测试锁死这四件事：
  P1 形态识别 `game_form`：三形态各自判对，且不依赖 GUI 旗标；
  P2 注册表里**没有**形态专用入口（tri_gather / mi_gather 已移除）；
  P3 支持表 `solver_supports`：**未知 key 一律 False**（旧写法会落到缺省
     ('square',)，于是失效 key 在方形上被判成「支持」→ 静默跑 IDA*）；
  P4 统一入口 `gather_solve_unified` 真的按形态分发（三形态各能跑出结果）；
  P5 失效 key 的提示文案 + 配置迁移 `_migrate_solver_algorithm`；
  P6 GUI 层：设成失效 key 后启动求解会被**明确拒绝**且不起后台线程。

跑法：``D:/python/python.exe -u test/_test_solver_form_gate.py``
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from solver import (SOLVER_ALGORITHMS, game_form, solver_supports,  # noqa: E402
                    unsupported_solver_msg, gather_solve_unified)
from game import SliderMatrix  # noqa: E402
from game_triangle import TriangleSliderMatrix  # noqa: E402
from game_mi import MiSliderMatrix  # noqa: E402
from gui.file_ops import _migrate_solver_algorithm  # noqa: E402

_FAILURES = []


def check(desc, cond, extra=''):
    tag = 'PASS' if cond else 'FAIL'
    if not cond:
        _FAILURES.append(desc)
    suffix = f'  {extra}' if extra else ''
    print(f'[{tag}] {desc}{suffix}')


# ============================================================ P1 形态识别
print('\n--- P1 形态识别（按类名，不依赖 GUI 旗标）---')
sq = SliderMatrix(4, 4)
tri = TriangleSliderMatrix(4)
mi = MiSliderMatrix(3, 3)
check('P1a 方形 SliderMatrix → square', game_form(sq) == 'square',
      game_form(sq))
check('P1b 三角 TriangleSliderMatrix → triangle',
      game_form(tri) == 'triangle', game_form(tri))
check('P1c 米字 MiSliderMatrix → mi', game_form(mi) == 'mi', game_form(mi))
check('P1d 未知类型兜底为 square（不是抛异常）',
      game_form(object()) == 'square')

# ============================================================ P2 无形态专用入口
print('\n--- P2 注册表不含形态专用入口 ---')
check('P2a tri_gather 已移除', 'tri_gather' not in SOLVER_ALGORITHMS)
check('P2b mi_gather 已移除', 'mi_gather' not in SOLVER_ALGORITHMS)
check('P2c 统一入口 gather 在册', 'gather' in SOLVER_ALGORITHMS)
check('P2d gather 标签不带形态后缀',
      '米字' not in SOLVER_ALGORITHMS['gather'][0]
      and '三角' not in SOLVER_ALGORITHMS['gather'][0],
      SOLVER_ALGORITHMS['gather'][0].strip())

# ============================================================ P3 支持表
print('\n--- P3 支持表：未知 key 一律不支持 ---')
for form in ('square', 'triangle', 'mi'):
    check(f'P3a 失效 key mi_gather 在 {form} 上不支持',
          solver_supports('mi_gather', form) is False)
    check(f'P3b 失效 key tri_gather 在 {form} 上不支持',
          solver_supports('tri_gather', form) is False)
check('P3c gather 三形态都支持',
      all(solver_supports('gather', f) for f in ('square', 'triangle', 'mi')))
check('P3d table 只支持方形',
      solver_supports('table', 'square')
      and not solver_supports('table', 'mi')
      and not solver_supports('table', 'triangle'))
check('P3e hybrid 只支持方形',
      solver_supports('hybrid', 'square')
      and not solver_supports('hybrid', 'mi'))

# ============================================================ P4 统一入口分发
print('\n--- P4 统一入口按形态分发（cancel 立即返回，不看求解质量）---')
for name, g, step in (('方形', sq, 2), ('三角', tri, 2), ('米字', mi, 2)):
    res = gather_solve_unified(g, step=step, cancel_check=lambda: True,
                               progress_callback=None)
    check(f'P4 {name} 走统一入口能产出 gather 型结果',
          isinstance(res, dict) and res.get('type') == 'gather',
          f"reason={res.get('reason') if isinstance(res, dict) else res}")

# ============================================================ P5 文案与迁移
print('\n--- P5 失效 key 文案 + 配置迁移 ---')
msg_unknown = unsupported_solver_msg('mi_gather', 'square')
check('P5a 失效 key 提示「不存在，请重新选择」',
      '不存在' in msg_unknown and '重新选择' in msg_unknown, msg_unknown)
msg_form = unsupported_solver_msg('table', 'mi')
check('P5b 形态不支持的提示点名谜题与该形态可用项',
      '米字格' in msg_form and '没有' in msg_form and '聚拢' in msg_form,
      msg_form)
check('P5c 迁移 mi_gather → gather',
      _migrate_solver_algorithm('mi_gather') == 'gather')
check('P5d 迁移 tri_gather → gather',
      _migrate_solver_algorithm('tri_gather') == 'gather')
check('P5e 正常 key 原样保留',
      _migrate_solver_algorithm('hybrid') == 'hybrid'
      and _migrate_solver_algorithm('gather') == 'gather')

# ============================================================ P6 GUI 层拒绝
print('\n--- P6 GUI：失效 key 启动求解被明确拒绝 ---')
from GUI import SliderGUI  # noqa: E402

gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False
gui.new_puzzle(4, 4, 2)
gui.solver_algorithm = 'mi_gather'      # 模拟老 config 里残留的失效值
gui._auto_solve_running = False
gui.macro_executing = False
gui.macro_notify_msg = ''
gui._start_auto_solve()
check('P6a 明确给出「不存在」提示',
      '不存在' in (gui.macro_notify_msg or ''),
      gui.macro_notify_msg or '')
check('P6b 没有静默换成别的算法（保留原值）',
      gui.solver_algorithm == 'mi_gather', gui.solver_algorithm)
check('P6c 没有启动后台线程', gui._auto_solve_running is False)

# 对照：方形 + 只支持异形的组合不存在；方形 + table 应放行（能启动）
gui.solver_algorithm = 'table'
gui._auto_solve_running = False
gui.macro_executing = False
gui.macro_notify_msg = ''
gui._start_auto_solve()
gui._auto_solve_cancel = True
check('P6d 方形 + table 放行（形态闸门不误伤）',
      gui.solver_algorithm == 'table' and '不存在' not in (
          gui.macro_notify_msg or ''),
      gui.macro_notify_msg or '')

# ============================================================
print('\n' + '=' * 60)
if _FAILURES:
    print(f'FAILED {len(_FAILURES)} 项：')
    for f in _FAILURES:
        print('  -', f)
    sys.exit(1)
print('ALL PASS')
