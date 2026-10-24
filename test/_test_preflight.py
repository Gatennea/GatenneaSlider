# -*- coding: utf-8 -*-
"""P2 产品化预检回归：保存门 0 缝诊断 + 打乱前拦截（2026-10-24）。

锁五件事：
  1. 阳性对照：真实米字盘面有可选缝、可打乱判定过——证明预检不误伤
     正常对局（打乱拦截 fail-open 的那半条也靠它兜底）；
  2. 保存门：一条能选的缝都没有时，错误消息说清病因（每条缝线都切进
     滑块内部 / 只剩一侧有滑块）并给出路（至少留一条干净缝）；
  3. 打乱前拦截：同盘面下 shuffle_puzzle 提示、game.shuffle 未被调用、
     盘面一步没动；
  4. 不打补丁时 shuffle_puzzle 正常走完（通知含「已打乱」）；
  5. 方形候选线 off-by-one 回归：头一条内部线不能漏（2×3 枚举得到
     (h,0)）；「边界盒填满 ≠ 冻形」（2×2 满块可合法外滑 → 放行），
     真冻形是一格宽横条（0 可动 → 拒存且消息说「0 颗能滑动」）。

0 缝盘面在正常晶格上几乎造不出来（未错位时整数缝线都是边并集），
病因路径用 monkeypatch ``_ann_all_valid_gaps → []`` 钉住；阳性对照
走真实盘面。

执行：``D:/python/python.exe -u test/_test_preflight.py``
"""
import os
import queue
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def boot(which, *args):
    gui = SliderGUI(cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.game_mode = 'practice'
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    gui.animation_enabled = False
    getattr(gui, which)(*args)
    gui._update_in_progress = False
    return gui


def positions(gui):
    return sorted(tuple(b.location) for b in gui.game.blocks)


# ---- 1. 阳性对照：真实米字盘面有缝、可打乱 ----
gui = boot('new_mi_puzzle', 4, 4, 1)
gaps = gui._ann_all_valid_gaps()
check('1a 米字 4×4 有可选中的缝', len(gaps) > 0, f'{len(gaps)} 条')
ok, err = gui._ann_validate_shuffleable()
check('1b 米字 4×4 可打乱判定过', ok, err or '')

# ---- 2. 保存门：0 缝 → 可操作诊断 ----
gui._ann_all_valid_gaps = lambda: []          # 实例属性影藏类方法
ok, err = gui._ann_validate_shuffleable()
check('2a 0 缝 → 保存门拒', not ok, repr(err))
check('2b 诊断说清病因（切进了滑块内部 / 只剩一侧）',
      '切进了滑块内部' in err and '只剩一侧' in err, repr(err))
check('2c 诊断给出路（至少留一条干净缝）', '至少留一条' in err, repr(err))
del gui._ann_all_valid_gaps                   # 还原，露出类方法
ok2, _ = gui._ann_validate_shuffleable()
check('2d 还原后照过（补丁没污染盘面）', ok2)

# ---- 3. 打乱前拦截：0 缝 → 提示且一步不动 ----
gui2 = boot('new_mi_puzzle', 4, 4, 1)
before = positions(gui2)
called = []
gui2.game.shuffle = lambda *a, **k: called.append(1)
gui2._ann_all_valid_gaps = lambda: []
gui2.shuffle_puzzle()
check('3a 0 缝 → 打乱被拦（game.shuffle 未被调用）', not called,
      f'called={called}')
check('3b 提示说明原因', '没有能选中的缝' in (gui2.macro_notify_msg or ''),
      repr(gui2.macro_notify_msg))
check('3c 盘面一步没动', positions(gui2) == before)

# ---- 4. 阳性：不打补丁，打乱正常走完 ----
gui3 = boot('new_mi_puzzle', 4, 4, 1)
gui3.shuffle_puzzle()
check('4a 正常盘面打乱不被拦', '已打乱' in (gui3.macro_notify_msg or ''),
      repr(gui3.macro_notify_msg))

# ---- 5. 方形候选线 off-by-one 回归（2026-10-24 修）----
# 旧写法从 min_row+1 起枚举候选线，每条缝族的头一条内部线全漏掉：
# 2 行盘面只剩一条横中缝 → 枚举成空 → 保存门 0 缝诊断误判、打乱
# 拦截误拦。且「边界盒填满 ≠ 冻形」——滑块可滑出棋盘外，2×2 满块
# 中缝两侧都能合法外滑（4 颗可动）；真冻形是一格宽横条（任一侧
# 滑动都会把该侧甩成孤立 → 0 可动）。
gui4 = boot('new_puzzle', 2, 3, 1)
gaps4 = gui4._ann_all_valid_gaps()
check('5a 2×3 盘面枚举得到横中缝 (h,0)', ('h', 0) in gaps4, f'{gaps4}')
gui4._ann_build_coords = {(0, 0), (0, 1), (1, 0), (1, 1)}
gui4._ann_rebuild_game_from_coords()
ok, err = gui4._ann_validate_shuffleable()
check('5b 2×2 满块不是冻形（中缝两侧可合法外滑）→ 放行',
      ok, repr(err))
gui4._ann_build_coords = {(0, 0), (0, 1), (0, 2)}
gui4._ann_rebuild_game_from_coords()
ok, err = gui4._ann_validate_shuffleable()
check('5c 1×3 横条真冻形（0 可动）→ 拒存',
      not ok and '滑动' in err, repr(err))
check('5d 横条的拒因是「0 颗能滑动」而非「没有缝」',
      '没有可选中的缝' not in err, repr(err))

print('\n===', 'ALL PASS' if not _failures else f'{len(_failures)} FAILURES',
      '===')
sys.exit(1 if _failures else 0)
