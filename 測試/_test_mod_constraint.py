# -*- coding: utf-8 -*-
"""驗證 detect_target_corner + mod 約束的實際行為。"""
import os, sys
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver.ml.gather_solver import detect_target_corner, _count_by_mod
from game import SliderMatrix


def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    globals()['_ok'] = globals().get('_ok', True) and cond


# ---- 1. 6×6 step=2：m,n 皆被整除 → None（無約束） ----
g = SliderMatrix(6, 6)
coords = frozenset((b.location[0], b.location[1]) for b in g.blocks)
tc = detect_target_corner(coords, 6, 6, 2)
check("6x6 step=2 → None（無約束）", tc is None)
# 每類各 9 個
mc = _count_by_mod(coords, 2)
check("6x6 每類 9 個", all(v == 9 for v in mc.values()))


# ---- 2. 5×5 step=2：唯一解應為 (0,0) ----
g5 = SliderMatrix(5, 5)
coords5 = frozenset((b.location[0], b.location[1]) for b in g5.blocks)
tc5 = detect_target_corner(coords5, 5, 5, 2)
check("5x5 step=2 初始 detect → (0, 0)", tc5 == (0, 0))
mc5 = _count_by_mod(coords5, 2)
check("5x5 類計數 (0,0)=9 (0,1)=6 (1,0)=6 (1,1)=4",
      mc5[(0,0)] == 9 and mc5[(0,1)] == 6 and mc5[(1,0)] == 6 and mc5[(1,1)] == 4)


# ---- 3. 4×6 step=2：m=4可被整除，n=6可被整除 → None ----
g46 = SliderMatrix(4, 6)
coords46 = frozenset((b.location[0], b.location[1]) for b in g46.blocks)
tc46 = detect_target_corner(coords46, 4, 6, 2)
check("4x6 step=2 → None（皆被整除）", tc46 is None)


# ---- 4. 5×4 step=2：m=5不整除，n=4整除，只有一種目標 ----
g54 = SliderMatrix(5, 4)
coords54 = frozenset((b.location[0], b.location[1]) for b in g54.blocks)
tc54 = detect_target_corner(coords54, 5, 4, 2)
check("5x4 step=2 有唯一目標角點", tc54 is not None)


# ---- 5. 6×5 step=2：同上一例，方向反轉，同樣有唯一目標 ----
g65 = SliderMatrix(6, 5)
coords65 = frozenset((b.location[0], b.location[1]) for b in g65.blocks)
tc65 = detect_target_corner(coords65, 6, 5, 2)
check("6x5 step=2 有唯一目標角點", tc65 is not None)


# ---- 6. 打亂 5×5 step=2 後，目標角點不應改變（平移 invariant） ----
g5.shuffle(attempts=30, step=2)
coords5b = frozenset((b.location[0], b.location[1]) for b in g5.blocks)
tc5b = detect_target_corner(coords5b, 5, 5, 2)
check("5x5 打亂後 detect 仍穩定", tc5b is not None)


print(f"\n{'ALL PASS' if globals().get('_ok', True) else 'SOME FAILED'}")
sys.exit(0 if globals().get('_ok', True) else 1)
