# -*- coding: utf-8 -*-
"""三形態構造校驗（gui/shape_validate.py）＋ blocks_from_cells（game_triangle/game_mi）。

執行：python test/_test_shape_validate.py
覆蓋：三形態合法形狀通過；缺塊／斷開／類計數錯／還原態（無空位）被拒；
      偏移掃描（整體平移 step 倍數與非整數倍都通過，三角/米字 anchor 與
      實際平移一致）；方形平移過的構造通過、類計數真錯的仍被拒；
      blocks_from_cells 的塊數／location 正規化／排序／update_matrix 能吃。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import SliderMatrix  # noqa: E402
from game_triangle import (  # noqa: E402
    TriangleSliderMatrix, tri_key, neighbors as tri_neighbors,
    side_of as tri_side_of, blocks_from_cells as tri_blocks_from_cells,
)
from game_mi import (  # noqa: E402
    MiSliderMatrix, mi_key, neighbors as mi_neighbors,
    side_of as mi_side_of, blocks_from_cells as mi_blocks_from_cells, lattice_of,
)
from gui.cell_class import cell_class  # noqa: E402
from gui.shape_validate import validate_shape, solved_cell_count  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


def _conn(kind, cells):
    if kind == 'square':
        return SliderMatrix.is_single_connected(cells)
    if kind == 'triangle':
        return TriangleSliderMatrix.is_single_connected(cells)
    return MiSliderMatrix.is_single_connected(cells)


def _shift(cells, dr, dc):
    return {(p[0] + dr, p[1] + dc) + p[2:] for p in cells}


def _shuffle_cells(kind, params, step, attempts=25):
    """從還原態合法打亂：類不變、單連通、非還原態 → 一個已知合法構造態。"""
    if kind == 'square':
        m, n = params
        g = SliderMatrix(m, n)
        g.shuffle(attempts, step)
        return {(b.location[0], b.location[1]) for b in g.blocks}
    if kind == 'triangle':
        g = TriangleSliderMatrix(params[0])
        g.shuffle(attempts, step)
        return g.positions()
    m, n = params
    g = MiSliderMatrix(m, n)
    g.shuffle(attempts, step)
    return g.positions()


def _solved_cells(kind, params):
    if kind == 'square':
        m, n = params
        return {(r, c) for r in range(m) for c in range(n)}
    if kind == 'triangle':
        return TriangleSliderMatrix(params[0]).positions()
    return MiSliderMatrix(params[0], params[1]).positions()


def _neighbor_spots(kind, x):
    if kind == 'square':
        return [(x[0] + dr, x[1] + dc) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))]
    if kind == 'triangle':
        return tri_neighbors(x)
    return mi_neighbors(x)


def _break_class(kind, cells, step, params):
    """挖一塊（保持連通）放到異類鄰位（保持連通）：塊數/連通對、類計數錯。

    返回變造後的 cells；找不到則回 None（測試會明確標記失敗）。
    """
    for x in sorted(cells):
        rest = cells - {x}
        if not _conn(kind, rest):
            continue
        cx = cell_class(x, step, kind)
        for y in _neighbor_spots(kind, x):
            if y in cells:
                continue
            if cell_class(y, step, kind) == cx:
                continue
            new = rest | {y}
            if _conn(kind, new):
                return new
    return None


def _disconnected_same_count(kind, params, step):
    """還原態分兩半、下半平移 (10,0)：塊數對、類計數對（step 倍數平移）、
    兩堆間距 10 格而不連通。"""
    solved = _solved_cells(kind, params)
    half = sorted(solved)
    cut = len(half) // 2
    return set(half[:cut]) | _shift(set(half[cut:]), 10, 0)


print("== 三形態：打亂態合法（含 anchor）==")
# 米字用 5×5 step3：step3 的表有 9 類且各偏移唯一（step2 的 s/d 同奇偶，
# 表退化到 2 類，(1,0) 與 (0,1) 不可分——anchor 唯一性只對非退化表成立）
CASES = [('triangle', (5,), 2), ('mi', (5, 5), 3), ('square', (4, 4), 2)]
shuffled = {}
for kind, params, step in CASES:
    cells = _shuffle_cells(kind, params, step)
    shuffled[kind] = cells
    ok, msg, anchor = validate_shape(kind, cells, params, step)
    check(f"{kind} 打亂態合法", ok, f"msg={msg}")
    # 打亂態 = 從還原態合法移動 → 類不變 → 偏移 (0,0)（三角/米字表非均勻，唯一）
    if kind in ('triangle', 'mi'):
        check(f"{kind} 打亂態 anchor=(0,0)", anchor == (0, 0), f"anchor={anchor}")

print("== 偏移掃描：整體平移 ==")
for kind, params, step in CASES:
    cells = shuffled[kind]
    # step 倍數平移：類不變，anchor 不變
    ok, _msg, anchor = validate_shape(kind, _shift(cells, step, 0), params, step)
    check(f"{kind} 平移({step},0)=step倍數 通過且 anchor=(0,0)",
          ok and anchor == (0, 0), f"anchor={anchor}")
    if kind in ('triangle', 'mi'):
        # 非整數倍平移：anchor = 平移的 mod 類（表非退化，這一條是關鍵）
        ok, _msg, anchor = validate_shape(kind, _shift(cells, 1, 0), params, step)
        check(f"{kind} 平移(1,0) 通過且 anchor=(1,0)",
              ok and anchor == (1, 0), f"anchor={anchor}")

print("== 方形：偏移掃描是現行判據的超集 ==")
sq = shuffled['square']
ok, _msg, _anchor = validate_shape('square', _shift(sq, 1, 0), (4, 4), 2)
check("方形平移(1,0)（step 不整除 m/n 的合法棋形）也通過", ok)
bad = _break_class('square', sq, 2, (4, 4))
check("方形找到類計數錯的構造", bad is not None)
if bad is not None:
    ok, msg, _a = validate_shape('square', bad, (4, 4), 2)
    check("方形類計數真錯的仍被拒", not ok and '類計數' in msg, f"msg={msg}")

print("== 非法路徑：缺塊 / 斷開 / 類計數錯 / 還原態 / 空狀態 ==")
for kind, params, step in CASES:
    cells = shuffled[kind]
    # 缺一塊 → 塊數不符
    missing = cells - {next(iter(cells))}
    ok, msg, _a = validate_shape(kind, missing, params, step)
    check(f"{kind} 缺一塊被拒", not ok and '滑塊數' in msg, f"msg={msg}")
    # 兩堆分開 → 單連通被拒（塊數/類計數都對）
    disc = _disconnected_same_count(kind, params, step)
    ok, msg, _a = validate_shape(kind, disc, params, step)
    check(f"{kind} 兩塊斷開被拒", not ok and '連通' in msg, f"msg={msg}")
    # 挖一塊放異類鄰位 → 類計數被拒
    bad = _break_class(kind, cells, step, params)
    if bad is None:
        check(f"{kind} 找到類計數錯的構造", False, '輔助枚舉失敗')
    else:
        ok, msg, _a = validate_shape(kind, bad, params, step)
        check(f"{kind} 類計數錯被拒", not ok and '類計數' in msg, f"msg={msg}")
    # 還原態本身 → 無空位被拒
    ok, msg, _a = validate_shape(kind, _solved_cells(kind, params), params, step)
    check(f"{kind} 還原態（無空位）被拒", not ok and '無空位' in msg, f"msg={msg}")
    # 空狀態
    ok, msg, _a = validate_shape(kind, set(), params, step)
    check(f"{kind} 空狀態被拒", not ok and msg == '空狀態', f"msg={msg}")

print("== blocks_from_cells ==")
tri_cells = shuffled['triangle']
blocks = tri_blocks_from_cells(tri_cells)
check("三角 blocks_from_cells 塊數", len(blocks) == len(tri_cells))
check("三角 location 正規化且照位置排序",
      [tuple(b.location) for b in blocks] == sorted(tri_cells))
tmp = TriangleSliderMatrix(5)
tmp.blocks = blocks
tmp.update_matrix()
check("三角 update_matrix 能吃 blocks_from_cells 產出",
      tmp.get_matrix() is not None and len(tmp.matrix) > 0)

# 米字：含半整數塊（錯位態）也能吃
g = MiSliderMatrix(5, 5)
moved = False
for line in [l for (t, l) in g.all_gaps() if t == 'd2']:
    for block in [b for b in g.blocks if mi_side_of('d2', line, mi_key(b)) == 0]:
        g.opt('d2', line, block)
        pos = g.try_move('e', 3)
        if pos:
            g.commit_move(pos)
            moved = True
            break
    if moved:
        break
check("米字含半整數塊（錯位態）", moved and any(lattice_of(mi_key(b)) for b in g.blocks))
mi_cells = g.positions()
blocks = mi_blocks_from_cells(mi_cells)
check("米字 blocks_from_cells 塊數", len(blocks) == len(mi_cells))
check("米字 location 正規化且照位置排序",
      [tuple(b.location) for b in blocks] == sorted(mi_cells))
tmp = MiSliderMatrix(5, 5)
tmp.blocks = blocks
tmp.update_matrix()
check("米字 update_matrix 能吃（含錯位）",
      tmp.get_matrix() is not None and len(tmp.matrix) > 0)
# 塊數總量：4*m*n
check("米字 blocks_from_cells 塊數 == 4mn",
      len(blocks) == solved_cell_count('mi', (5, 5)))

if _failures:
    print(f'\nFAILURES: {_failures}')
    sys.exit(1)
print('\nALL PASS')
