# -*- coding: utf-8 -*-
"""三维创造模式第 0 步：数据 / 判定层回归。

锁住 `engine/cubic_edit.py` 的契约：
  A. 容积内增删 / 越界 / 已有块 / 空格拒绝；
  B. 草稿挂到 EngineGame（含空盘），块数与局面一致；
  C. 保存门：空盘 / 不连通 / 冻形；正常拆开的局面能过；
  D. 自订还原态必要条件：块数凑不出长方体 / mod 配额不对 / 满长方体通过；
  E. 三维自订 goal_pattern 的还原判定认 48 对称（旋转 90° 仍算还原）；
  F. 面外邻格轴映射（r/c/d）与 cubic_view 一致。

跑法：D:/python/python.exe test/_test_cubic_edit.py
"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

from engine.adapter import create_adapter_puzzle  # noqa: E402
from engine.cubic_edit import (  # noqa: E402
    CubicDraft, full_cells, normalize_cells,
)

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg} {extra}')
    return bool(cond)


print('=' * 60)
print('A. 增删与边界')
d = CubicDraft(3, 3, 3, 1)
check(len(d) == 27, '3×3×3 草稿默认是还原态 27 块', len(d))
check(d.remove((1, 1, 1)).ok, '挖掉中心一块')
check(len(d) == 26, '块数 -1', len(d))
check(d.remove((1, 1, 1)).reason == 'empty', '同一格再挖被拒（empty）')
check(d.add((1, 1, 1)).ok, '放回中心')
check(d.add((1, 1, 1)).reason == 'occupied', '已有块再放被拒（occupied）')
check(not d.add((3, 0, 0)).ok and d.add((3, 0, 0)).reason == 'out_of_bounds',
      '越界放块被拒（out_of_bounds）')
check(not d.remove((-1, 0, 0)).ok, '负坐标挖块被拒')
check(d.neighbor((1, 1, 1), 0, 1) == (1, 2, 1), 'axis 0 对应 c 方向')
check(d.neighbor((1, 1, 1), 1, 1) == (1, 1, 2), 'axis 1 对应 d 方向')
check(d.neighbor((1, 1, 1), 2, -1) == (0, 1, 1), 'axis 2 对应 r 方向')
try:
    normalize_cells([(0, 0, 3)], 3, 3, 3)
    check(False, '越界集合应 ValueError')
except ValueError:
    check(True, '越界集合 ValueError')

print('=' * 60)
print('B. 草稿 → EngineGame')
d = CubicDraft(3, 3, 3, 1)
d.remove((1, 1, 1))
g = create_adapter_puzzle('cubic', 3, 3, 1, depth=3)
d.apply_to(g)
check(len(g.blocks) == 26, '挂 26 块草稿后块数一致', len(g.blocks))
check(not g.is_solved(), '缺一块不是还原态')
d.clear()
d.apply_to(g)
check(len(g.blocks) == 0, '空盘也能挂上（apply_pattern 不接受空列表）', len(g.blocks))
check(not g.is_solved(), '空盘不是还原态')

print('=' * 60)
print('C. 保存门：空 / 不连通 / 冻形')
d = CubicDraft(3, 3, 3, 1)
d.clear()
r = d.check_save()
check(not r.ok and 'empty' in r.reasons, '空盘被保存门拦下', r.reasons)
# 抽掉中间整层：上下两层各自连通，但整体不连通
d.reset_solved()
for c in range(3):
    for dep in range(3):
        d.remove((1, c, dep))
r = d.check_save()
check(not r.ok and 'disconnected' in r.reasons, '抽中间层后整体不连通', r.reasons)
check('frozen' in r.reasons, '上下两层都动不了（冻形）', r.reasons)
# 正常拆开的 26 块：不冻、连通
d = CubicDraft(3, 3, 3, 1)
d.remove((1, 1, 1))
check(d.check_save().ok, '缺中心一块仍是可玩局面（没冻、连通）')

print('=' * 60)
print('D. 自订还原态必要条件')
d = CubicDraft(3, 3, 3, 1)
d.remove((1, 1, 1))
r = d.check_restorable()
check(not r.ok and 'not_cuboid' in r.reasons,
      '26 块凑不出 m×n×d 长方体', r.reasons)

# 4×4×4 中把 3×3×3 的一角换成盒外的同类块：块数仍 27，
# 但 mod 类配额被破坏——这是 step>1 才有的强必要条件。
cells = set(full_cells(3, 3, 3))
cells.remove((0, 0, 0))
cells.add((3, 0, 0))
d = CubicDraft(4, 4, 4, 2, cells)
r = d.check_restorable()
check(not r.ok and 'mod_mismatch' in r.reasons,
      '27 块但 mod 配额不对（step=2）', r.reasons)
check(d.check_save().ok, '这一局本身仍能当谜题（连通、可动）')

check(CubicDraft(3, 3, 3, 2).check_restorable().ok,
      '3×3×3 实心长方体通过必要条件（step=2）')
check(CubicDraft(4, 4, 4, 2).check_restorable().ok,
      '4×4×4 实心长方体通过必要条件（step=2）')

print('=' * 60)
print('E. 三维自订 goal_pattern 认 48 对称')
g = create_adapter_puzzle('cubic', 3, 3, 1, depth=3)
check(g.set_goal_pattern([(0, 0, 0), (0, 0, 1)]),
      '设定 1×1×2 多米诺目标')
g.apply_pattern([(0, 0, 0), (1, 0, 0)])
check(g.is_solved(), '目标与当前差 90° 旋转，仍判还原（48 对称）')
g.apply_pattern([(0, 0, 0), (2, 0, 0)])
check(not g.is_solved(), '拉开距离的多米诺不是同一目标')

print('=' * 60)
print('F. 滑出原盒后的包围盒 / 还原态（2026-11-18 用户报越过容积）')
# 4×4×4 整层在 d 方向推一格：坐标变成 d=1..4，原盒 d=0..3 装不下，
# 但局面仍连通且可动。编辑器应以 4×4×5 包围盒作画布，还原态仍是
# 平移后的 4×4×4，不能拿原 m×n×d 直接 normalize。
shifted = [(r, c, dep + 1) for r in range(4)
           for c in range(4) for dep in range(4)]
d = CubicDraft(4, 4, 5, 1, shifted, solved_cells=shifted)
check(len(d) == 64, '64 块全部装进 4×4×5 包围盒', len(d))
check(d.check_save().ok, '滑出原盒后仍判连通且可动', d.check_save().reasons)
check(d.check_restorable().ok, '仍是可还原的必要条件内',
      d.check_restorable().reasons)
d.remove((0, 0, 1))
d.reset_solved()
check(d.cells == frozenset(shifted),
      '还原态回到平移后的 4×4×4，而不是 4×4×5')

print('=' * 60)
total = _ok[0] + len(_fail)
print(f'结果：{"全部通过" if not _fail else "有失败"}（{_ok[0]} 项通过，'
      f'{len(_fail)} 项失败）／共 {total} 项')
if _fail:
    for name in _fail:
        print('  -', name)
    sys.exit(1)
