# -*- coding: utf-8 -*-
"""移動不變量類的純邏輯測試（gui/cell_class.py）。

執行：python test/_test_cell_class.py
覆蓋：三形態類不變性（每族每方向真實移動前後類多重集不變 + 全部位置
      純邏輯枚舉）、米字錯位態（奇數 step 出現半整數座標）、class_index
      對方形與現行 (r%step)*step+(c%step) 完全一致且為 [0, step²) 雙射。
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_triangle import (  # noqa: E402
    DIRECTIONS as TRI_DIRS, TriangleSliderMatrix, tri_key,
    side_of as tri_side_of, gap_for_direction as tri_gap_of,
)
from game_mi import (  # noqa: E402
    DIRECTIONS as MI_DIRS, MiSliderMatrix, mi_key,
    side_of as mi_side_of, gap_for_direction as mi_gap_of, lattice_of,
)
from gui.cell_class import cell_class, class_index  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


def _real_move_invariant(kind, step, make_game, key_of, side_of, gap_of, dirs):
    """每族每方向：還原態下找一條能動的縫＋塊，移動前後類多重集不變。

    還原態下沿縫平移一側整組通常合法；遍歷縫與塊直到找到一次成功，
    保證每個方向都真的被移動驗證到（而非只驗證純邏輯平移）。
    """
    for direction in sorted(dirs):
        gap_type = gap_of(direction)
        found = False
        for _trial in range(50):
            g = make_game()
            lines = [l for (t, l) in g.all_gaps() if t == gap_type]
            if not lines:
                break
            for line in lines:
                side0 = [b for b in g.blocks if side_of(gap_type, line, key_of(b)) == 0]
                for block in side0:
                    g.opt(gap_type, line, block)
                    before = Counter(cell_class(key_of(b), step, kind)
                                     for b in g.blocks)
                    pos = g.try_move(direction, step)
                    if not pos:
                        continue
                    g.commit_move(pos)
                    after = Counter(cell_class(key_of(b), step, kind)
                                    for b in g.blocks)
                    check(f"{kind} 真實移動 {direction}: 類多重集不變",
                          before == after)
                    found = True
                    break
                if found:
                    break
            if found:
                break
        check(f"{kind} 真實移動 {direction}: 至少一次成功", found)


def _enumerate_invariant(kind, positions, step, deltas):
    """純邏輯：全部位置 × 每方向，平移 step×delta 後類不變。"""
    bad = []
    for pos in positions:
        for (dr, dc) in deltas:
            if cell_class((pos[0] + step * dr, pos[1] + step * dc), step, kind) \
                    != cell_class(pos, step, kind):
                bad.append((pos, dr, dc))
    return bad


print("== 三角：真實移動類不變（k=6 step2）==")
_real_move_invariant('triangle', 2, lambda: TriangleSliderMatrix(6),
                     tri_key, tri_side_of, tri_gap_of, TRI_DIRS)

print("== 米字：真實移動類不變（6×6 step2）==")
_real_move_invariant('mi', 2, lambda: MiSliderMatrix(6, 6),
                     mi_key, mi_side_of, mi_gap_of, MI_DIRS)

print("== 米字錯位態（6×6 step3，奇數 step 出現半整數）==")
g = MiSliderMatrix(6, 6)
moved = False
for line in [l for (t, l) in g.all_gaps() if t == 'd2']:
    for block in [b for b in g.blocks if mi_side_of('d2', line, mi_key(b)) == 0]:
        g.opt('d2', line, block)
        before = Counter(cell_class(mi_key(b), 3, 'mi') for b in g.blocks)
        pos = g.try_move('e', 3)
        if pos:
            g.commit_move(pos)
            after = Counter(cell_class(mi_key(b), 3, 'mi') for b in g.blocks)
            check("米字 step3 斜向移動：類多重集不變", before == after)
            keys = [mi_key(b) for b in g.blocks]
            check("米字 step3 斜向移動：出現半整數（B 晶格）",
                  any(lattice_of(k) for k in keys))
            # 錯位態下的類不變：半整數塊的類與移動前相同（cell_class 內部整數化；
            # direction 'e' step3 = 每塊平移 (-1.5, +1.5)，故移動前 = (k+1.5, k-1.5)）
            bad = [mi_key(b) for b in g.blocks
                   if cell_class(mi_key(b), 3, 'mi')
                   != cell_class((mi_key(b)[0] + 1.5, mi_key(b)[1] - 1.5), 3, 'mi')]
            check("米字錯位塊類與平移前一致（純邏輯）", not bad, f"bad={bad[:3]}")
            moved = True
            break
    if moved:
        break
check("米字 step3 斜向移動：至少一次成功", moved)

print("== 純邏輯：全部位置 × 每族每方向 ==")
tri_solved = TriangleSliderMatrix(5).positions()
mi_solved = MiSliderMatrix(5, 5).positions()
sq_solved = {(r, c) for r in range(5) for c in range(5)}
for step in (2, 3, 4):
    bad_t = _enumerate_invariant('triangle', tri_solved, step,
                                 [(1, 0), (-1, 0), (0, 1), (0, -1),
                                  (-1, 1), (1, -1)])
    check(f"三角 k=5 step{step}: 全位置全方向類不變", not bad_t, f"bad={bad_t[:3]}")
    bad_m = _enumerate_invariant('mi', mi_solved, step,
                                 [(-0.5, -0.5), (-1, 0), (-0.5, 0.5),
                                  (0, -1), (0, 1), (0.5, -0.5), (1, 0), (0.5, 0.5)])
    check(f"米字 5×5 step{step}: 全位置全方向類不變", not bad_m, f"bad={bad_m[:3]}")
    bad_s = _enumerate_invariant('square', sq_solved, step,
                                 [(-1, 0), (1, 0), (0, -1), (0, 1)])
    check(f"方形 5×5 step{step}: 全位置全方向類不變", not bad_s, f"bad={bad_s[:3]}")

print("== class_index：方形與現行算式一致、[0, step²) 雙射 ==")
for step in (2, 3, 4, 5):
    all_ok = True
    for r in range(30):
        for c in range(30):
            if class_index((r % step, c % step), step) \
                    != (r % step) * step + (c % step):
                all_ok = False
    check(f"class_index step{step} 與 (r%step)*step+(c%step) 一致", all_ok)
    keys = [(a, b) for a in range(step) for b in range(step)]
    idxs = [class_index(k, step) for k in keys]
    check(f"class_index step{step}: step² 個類 → step² 個不同索引",
          len(set(idxs)) == step * step and 0 <= min(idxs) and max(idxs) < step * step)
# 三角/米字的類索引也落在 [0, step²)
for kind, positions in (('triangle', tri_solved), ('mi', mi_solved)):
    in_range = all(0 <= class_index(cell_class(p, 2, kind), 2) < 4
                   for p in positions)
    check(f"{kind} class_index 輸出落在 [0, 4)", in_range)

if _failures:
    print(f'\nFAILURES: {_failures}')
    sys.exit(1)
print('\nALL PASS')
