# -*- coding: utf-8 -*-
r"""选块填空（原单段求解）收编进求解器列表后的行为核对。

锁定四件事：
  1. 菜单里填洞宏已并掉、选块填空在列，且两者支持的形态符合预期；
  2. 老配置里的 fill_macro 能迁到新 key，不会留下失效选项；
  3. 没指定目标方块时入口不硬算，明确返回失败；
  4. 编辑菜单不再有单段求解，自动求解仍在末项（主循环靠末项改「停止求解」）。
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
sys.path.insert(0, _root)

ok_all = True


def check(name, cond, extra=''):
    global ok_all
    if cond:
        print('[PASS] %s' % name)
    else:
        ok_all = False
        print('[FAIL] %s  %s' % (name, extra))


from solver import (SOLVER_ALGORITHMS, solver_supports,          # noqa: E402
                    unsupported_solver_msg)
from gui.file_ops import _migrate_solver_algorithm                # noqa: E402

# ---- 1. 注册表 ----
check('填洞宏已从菜单并掉', 'fill_macro' not in SOLVER_ALGORITHMS,
      str(list(SOLVER_ALGORITHMS)))
check('选块填空在列', 'pick_fill' in SOLVER_ALGORITHMS)
_gap_name = SOLVER_ALGORITHMS.get('gap_macro', ('?',))[0].strip()
check('补缺宏改叫「填洞补缺」', _gap_name == '填洞补缺', _gap_name)
_pick_name = SOLVER_ALGORITHMS.get('pick_fill', ('?',))[0].strip()
check('新项叫「选块填空」', _pick_name == '选块填空', _pick_name)

check('选块填空支持方形', solver_supports('pick_fill', 'square'))
check('选块填空不支持三角', not solver_supports('pick_fill', 'triangle'))
check('选块填空不支持米字', not solver_supports('pick_fill', 'mi'))
_msg = unsupported_solver_msg('pick_fill', 'triangle')
check('不支持时给出明确文案', '选块填空' in _msg and '没有' in _msg, _msg)

# ---- 2. 旧配置迁移 ----
check('fill_macro → gap_macro',
      _migrate_solver_algorithm('fill_macro') == 'gap_macro',
      _migrate_solver_algorithm('fill_macro'))
check('gather 不受影响',
      _migrate_solver_algorithm('gather') == 'gather')
check('mi_gather 仍迁 gather',
      _migrate_solver_algorithm('mi_gather') == 'gather')

# ---- 3. 缺目标时不硬算 ----
from solver.ml.gap_solver import solve_pick_fill          # noqa: E402
from game import SliderMatrix                             # noqa: E402

g = SliderMatrix(4, 4)
try:
    res = solve_pick_fill(g, step=2)
    check('未指定方块时返回失败而非抛错',
          isinstance(res, dict) and res.get('type') == 'fill_fail', str(res))
except Exception as e:
    check('未指定方块时返回失败而非抛错', False, repr(e))

# ---- 4. 编辑菜单结构 ----
import pygame                                              # noqa: E402
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
try:
    pygame.init()
    pygame.display.set_mode((100, 100))
except Exception:
    pass
from GUI import SliderGUI                                  # noqa: E402

gui = SliderGUI()
gui._update_menu_shortcut_texts()
items = gui.edit_menu_items
check('编辑菜单不含单段求解',
      not any('单段' in str(t) for t in items), str(items))
check('自动求解仍在末项', '自动求解' in str(items[-1]), str(items))
# 索引必须与 events.py 编辑菜单点击分发的硬编码序号一致：
# 5 = 居中（视图操作），6 = 自动求解。加/删菜单项时两处都要改。
check('自动求解索引为 6（5 = 居中）', items.index(items[-1]) == 6,
      str(list(enumerate(items))))
check('第 5 项是居中', '居中' in str(items[5]), str(items[5]))

print('\n=== %s ===' % ('全部通过' if ok_all else '存在失败'))
sys.exit(0 if ok_all else 1)
