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


# ======================================================================
# 以下為併入的遠端版本斷言（同一 cell_class 的第二套覆蓋：逐族逐方向/類表/錯位態/step≤1）
# ======================================================================

import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from game import SliderMatrix  # noqa: E402
from game_mi import MiSliderMatrix, mi_key, side_of  # noqa: E402
from game_triangle import TriangleSliderMatrix, tri_key  # noqa: E402
from gui.cell_class import cell_class, class_index  # noqa: E402
from solver.actions import apply_action, enumerate_valid_actions  # noqa: E402

def square_classes(g, step):
    return {id(b): cell_class(tuple(b.location), step, 'square') for b in g.blocks}


def triangle_classes(g, step):
    return {id(b): cell_class(tri_key(b)[:2], step, 'triangle') for b in g.blocks}


def mi_classes(g, step):
    return {id(b): cell_class(mi_key(b)[:2], step, 'mi') for b in g.blocks}


# ================================================================ 方形：h/v 兩族四向
print("=== 方形：每族每方向走一步，逐塊比對類 ===")
g = SliderMatrix(6, 6)
for fam, dirs in (('h', ('a', 'd')), ('v', ('w', 's'))):
    for d in dirs:
        moved = False
        for action in enumerate_valid_actions(g, 2):
            if action[0] != fam or action[3] != d:
                continue
            before = square_classes(g, 2)
            if apply_action(g, action, 2):
                after = square_classes(g, 2)
                check(f"方形 '{fam}' 縫 '{d}' 一步後每塊類不變",
                      before == after,
                      f"變化的塊數 {sum(1 for k in before if before[k] != after[k])}")
                moved = True
                break
        if not moved:
            check(f"方形 '{fam}' 縫 '{d}' 找不到可提交的移動", False)
cnt = {}
for k in square_classes(g, 2).values():
    cnt[k] = cnt.get(k, 0) + 1
check("方形 6×6 step2 類表 4 類各 9 塊（移動前後不變）",
      len(cnt) == 4 and sorted(cnt.values()) == [9, 9, 9, 9],
      str(sorted(cnt.values())))

# ================================================================ 三角：三族六向
print("=== 三角：每族每方向走一步，逐塊比對類 ===")
g = TriangleSliderMatrix(6)
FAMS = (('h', ('a', 'd')), ('p', ('e', 'z')), ('n', ('w', 'x')))
for fam, dirs in FAMS:
    for d in dirs:
        moved = False
        for (t, line) in g.all_gaps():
            if t != fam:
                continue
            for blk in list(g.blocks):
                g.opt(fam, line, blk)
                final = g.try_move_ex(d, 2)[0]
                if final:
                    before = triangle_classes(g, 2)
                    ups = {id(b): tri_key(b)[2] for b in g.blocks}
                    g.commit_move(final)
                    after = triangle_classes(g, 2)
                    check(f"三角 '{fam}' 縫 '{d}' 一步後每塊類不變",
                          before == after,
                          f"line={line}")
                    check(f"三角 '{fam}' 縫 '{d}' 朝向 up 不變",
                          ups == {id(b): tri_key(b)[2] for b in g.blocks})
                    moved = True
                    break
            if moved:
                break
            for b in g.blocks:
                b.be_opted = False
        if not moved:
            check(f"三角 '{fam}' 縫 '{d}' 找不到可提交的移動", False)
tri_cnt = {}
for k in triangle_classes(g, 2).values():
    tri_cnt[k] = tri_cnt.get(k, 0) + 1
check("三角 k=6 step2 還原態 4 類，塊數 12/9/9/6",
      len(tri_cnt) == 4 and sorted(tri_cnt.values()) == [6, 9, 9, 12],
      str(sorted(tri_cnt.values())))

# ================================================================ 米字：四族八向
print("=== 米字：每族每方向走一步，逐塊比對類 ===")
g = MiSliderMatrix(6, 6)
for fam, dirs in (('h', ('a', 'd')), ('v', ('w', 's')),
                  ('d1', ('x', 'q')), ('d2', ('e', 'z'))):
    for d in dirs:
        moved = False
        for (t, line) in g.all_gaps():
            if t != fam:
                continue
            for blk in list(g.blocks):
                g.opt(fam, line, blk)
                final = g.try_move_ex(d, 2)[0]
                if final:
                    before = mi_classes(g, 2)
                    qs = {id(b): mi_key(b)[2] for b in g.blocks}
                    g.commit_move(final)
                    after = mi_classes(g, 2)
                    check(f"米字 '{fam}' 縫 '{d}' 一步後每塊類不變",
                          before == after,
                          f"line={line}")
                    check(f"米字 '{fam}' 縫 '{d}' 朝向 q 不變",
                          qs == {id(b): mi_key(b)[2] for b in g.blocks})
                    moved = True
                    break
            if moved:
                break
            for b in g.blocks:
                b.be_opted = False
        if not moved:
            check(f"米字 '{fam}' 縫 '{d}' 找不到可提交的移動", False)
mi_cnt = {}
for k in mi_classes(g, 2).values():
    mi_cnt[k] = mi_cnt.get(k, 0) + 1
check("米字 6×6 step2 還原態類數減半（2 類各 72 塊）",
      len(mi_cnt) == 2 and sorted(mi_cnt.values()) == [72, 72],
      str(sorted(mi_cnt.values())))

# ================================================================ 米字錯位態（半整數）
print("=== 米字錯位態：斜向一步後類不變（step=3 奇數） ===")
g = MiSliderMatrix(6, 6)
before = mi_classes(g, 3)
ref = g.block_at(sorted(k for k in g.positions() if side_of('d1', 6, k) == 1)[0])
g.opt('d1', 6, ref)
final = g.try_move_ex('x', 3)[0]
check("step=3 斜向一步可提交（造出錯位態）", bool(final))
g.commit_move(final)
check("錯位態真的出現半整數座標",
      any(abs(v - round(v)) > 1e-9
          for b in g.blocks for v in mi_key(b)[:2]))
after = mi_classes(g, 3)
check("跨晶格（半整數）後每塊類不變", before == after,
      f"變化的塊數 {sum(1 for k in before if before[k] != after[k])}")

# 錯位態下每族再各走一步（奇數 step=3），類仍不變
for fam, dirs in (('h', ('a', 'd')), ('v', ('w', 's')),
                  ('d1', ('x', 'q')), ('d2', ('e', 'z'))):
    moved = False
    for (t, line) in g.all_gaps():
        if t != fam or moved:
            continue
        for blk in list(g.blocks):
            g.opt(fam, line, blk)
            final = g.try_move_ex(dirs[0], 3)[0] or g.try_move_ex(dirs[1], 3)[0]
            if final:
                before = mi_classes(g, 3)
                g.commit_move(final)
                check(f"錯位態下 '{fam}' 縫再走一步類不變",
                      before == mi_classes(g, 3))
                moved = True
                break
            for b in g.blocks:
                b.be_opted = False
    if not moved:
        check(f"錯位態下 '{fam}' 縫找得到可提交的移動", False)

mi3 = MiSliderMatrix(6, 6)
cnt3 = {}
for k in mi_classes(mi3, 3).values():
    cnt3[k] = cnt3.get(k, 0) + 1
check("米字 6×6 step3 還原態 9 類各 16 塊",
      len(cnt3) == 9 and sorted(cnt3.values()) == [16] * 9,
      str(sorted(cnt3.values())))

# ================================================================ class_index 一致性
print("=== class_index：方形與 (r%step)*step+(c%step) 完全一致 ===")
bad = []
for step in (2, 3, 4, 7):
    for r in range(-7, 8):
        for c in range(-7, 8):
            k_old = (r % step) * step + (c % step)
            k_new = class_index(cell_class((r, c), step, 'square'), step)
            if k_old != k_new:
                bad.append((step, r, c, k_old, k_new))
check("方形 class_index ≡ (r%step)*step+(c%step)（含負座標）", not bad,
      str(bad[:3]))

# ================================================================ step <= 1
print("=== step <= 1 恆為 (0, 0) ===")
check("step=1 三形態類均為 (0,0)",
      cell_class((3, 7), 1, 'square') == (0, 0)
      and cell_class((3, 7, True), 1, 'triangle') == (0, 0)
      and cell_class((3.5, 7.5, 'N'), 1, 'mi') == (0, 0))
check("step=0 同樣收斂到 (0,0)",
      cell_class((3, 7), 0, 'square') == (0, 0)
      and cell_class((3.5, 7.5, 'N'), 0, 'mi') == (0, 0))

print()
if _failures:
    print(f"共 {len(_failures)} 項失敗:")
    for n in _failures:
        print("  -", n)
    sys.exit(1)
print("全部通過")
