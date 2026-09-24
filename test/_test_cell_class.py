# -*- coding: utf-8 -*-
"""移動不變量類 cell_class 的純邏輯測試（不開窗、不依賴 pygame）。

執行：python test/_test_cell_class.py
覆蓋：
- 三形態每族每方向各走一步，比對移動前後每個塊的類（類不變性）
- 方形 class_index 與 (r%step)*step+(c%step) 完全一致（含負座標）
- 米字錯位態（斜向一格 → 半整數座標）下類仍不變
- 還原態類數與每類塊數（方形/三角/米字；米字偶數 step 類數減半）
- step <= 1 恆為 (0, 0)
"""
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from game import SliderMatrix  # noqa: E402
from game_mi import MiSliderMatrix, mi_key, side_of  # noqa: E402
from game_triangle import TriangleSliderMatrix, tri_key  # noqa: E402
from gui.cell_class import cell_class, class_index  # noqa: E402
from solver.actions import apply_action, enumerate_valid_actions  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ''))
    if not cond:
        _failures.append(name)
    return bool(cond)


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
