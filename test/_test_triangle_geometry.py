# -*- coding: utf-8 -*-
"""
正三角形密鋪幾何單元測試（Stage B1，先於渲染鎖定數學）。

執行：python test/_test_triangle_geometry.py
涵蓋：單位三角頂點、3-鄰接對稱性、縫隙族劃分、6 向滑動保持密鋪、
      大三角形計數（k²）、復原判定（平移/旋轉/翻轉/缺塊/多塊）、
      地圖編碼往返。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_triangle import (  # noqa: E402
    DIRECTIONS,
    GAP_DIRECTIONS,
    TriangleSliderMatrix,
    cells_inside_triangle,
    convex_hull,
    gap_index_range,
    gap_rank,
    neighbors,
    side_of,
    tri_key,
    tri_vertices,
)

failures = []


def check(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        failures.append(msg)


print("== 頂點公式 ==")
check(tri_vertices(0, 0, True) == ((0, 0), (1, 0), (0, 1)), "▲(0,0) 頂點")
check(tri_vertices(0, 0, False) == ((1, 0), (1, 1), (0, 1)), "▼(0,0) 頂點")
check(tri_vertices(2, 3, True) == ((2, 3), (3, 3), (2, 4)), "▲(2,3) 頂點")
# ▲(i,j) 與 ▼(i,j) 共享邊 (i+1,j)-(i,j+1)
shared = set(tri_vertices(1, 1, True)) & set(tri_vertices(1, 1, False))
check(shared == {(2, 1), (1, 2)}, "▲(i,j) 與 ▼(i,j) 共享斜邊")

print("== 鄰接對稱性（每對恰共享一條邊）==")


def edge_set(key):
    vs = tri_vertices(*key)
    return {frozenset((vs[t], vs[(t + 1) % 3])) for t in range(3)}


bad = 0
for i in range(-2, 3):
    for j in range(-2, 3):
        for up in (True, False):
            key = (i, j, up)
            nbs = neighbors(key)
            if len(nbs) != 3 or len(set(nbs)) != 3:
                bad += 1
                continue
            for nb in nbs:
                if not (edge_set(key) & edge_set(nb)):
                    bad += 1
                if key not in neighbors(nb):
                    bad += 1
check(bad == 0, f"3-鄰接雙向且共享邊（異常數 {bad}）")
check(set(neighbors((0, 0, True))) == {(0, 0, False), (-1, 0, False), (0, -1, False)},
      "▲(i,j) 鄰居 = ▼(i,j),▼(i-1,j),▼(i,j-1)")
check(set(neighbors((0, 0, False))) == {(0, 0, True), (1, 0, True), (0, 1, True)},
      "▼(i,j) 鄰居 = ▲(i,j),▲(i+1,j),▲(i,j+1)")

print("== 縫隙族劃分 ==")
g = TriangleSliderMatrix(4)
cells = g.positions()
check(len(cells) == 16, f"k=4 單元三角數 = {len(cells)}")
for kk in (2, 3, 5, 6, 8):
    t = TriangleSliderMatrix(kk)
    check(len(t.positions()) == kk * kk, f"k={kk} 單元三角數 = k² = {kk * kk}")
# 'h' 族：j <= line 與 j > line
check(side_of('h', 2, (0, 2, True)) == 0 and side_of('h', 2, (0, 3, True)) == 1, "'h' 按 j 劃分")
check(side_of('p', 2, (2, 0, True)) == 0 and side_of('p', 2, (3, 0, True)) == 1, "'p' 按 i 劃分")
check(side_of('n', 3, (1, 2, True)) == 0 and side_of('n', 3, (1, 3, True)) == 1, "'n' 按 i+j 劃分")
# 'n' 族必須看朝向：▲(i,j) 與 ▼(i,j) 同屬一個菱形胞，分隔二者的斜邊就是
# 這條縫，兩者落在縫的兩側。若忽略 up，同一條縫兩側會被劃進同一組，
# 選中組邊界呈現鋸齒狀（邊緣多/少幾個滑塊）。
check(side_of('n', 3, (1, 2, True)) != side_of('n', 3, (1, 2, False)),
      "'n' 族同格 ▲/▼ 分居縫兩側")
check(side_of('n', 3, (1, 2, False)) == 1, "'n' 族 ▼ 在座標大的一側")
# 三族縫隙的兩側必須被 line 乾淨切開：任一 rank 不得同時出現在兩側
for K in (2, 3, 4, 6, 8):
    t = TriangleSliderMatrix(K)
    tcells = t.positions()
    jagged = []
    for gt in ('h', 'p', 'n'):
        for line in range(-1, K + 1):
            if not t.is_valid_gap(gt, line):
                continue
            r0 = {gap_rank(gt, c) for c in tcells if side_of(gt, line, c) == 0}
            r1 = {gap_rank(gt, c) for c in tcells if side_of(gt, line, c) == 1}
            if not r0 or not r1:
                continue
            if max(r0) > line or min(r1) <= line:
                jagged.append((gt, line))
    check(not jagged, f"k={K} 三族縫兩側無交錯（異常 {jagged[:3]}）")
# 有效 line 範圍必須兩側非空
for gt in ('h', 'p', 'n'):
    rng = list(gap_index_range(gt, cells))
    ok = all(g.is_valid_gap(gt, line) for line in rng)
    outside_ok = all(not g.is_valid_gap(gt, line)
                     for line in (rng[0] - 1, rng[-1] + 1))
    check(ok and outside_ok, f"'{gt}' 族有效 line = {rng[0]}..{rng[-1]}，界外無效")
check(list(gap_index_range('n', cells)) == [0, 1, 2], "'n' 族範圍跟隨實際 i+j 範圍")
# 每族方向都平行於該族縫隙線
for gt, dirs in GAP_DIRECTIONS.items():
    parallel = True
    for d in dirs:
        di, dj = DIRECTIONS[d]
        if gt == 'h' and dj != 0:
            parallel = False
        if gt == 'p' and di != 0:
            parallel = False
        if gt == 'n' and di + dj != 0:
            parallel = False
    check(parallel, f"'{gt}' 族方向平行縫隙：{dirs}")
check(len(DIRECTIONS) == 6 and len(set(DIRECTIONS.values())) == 6, "6 個方向互不重複")

print("== 平移保持密鋪與連通 ==")
base = TriangleSliderMatrix(4).positions()
for d, (di, dj) in DIRECTIONS.items():
    moved = {(i + di, j + dj, up) for (i, j, up) in base}
    check(moved == cells_inside_triangle(convex_hull(
        {v for key in moved for v in tri_vertices(*key)})),
        f"方向 {d} 平移後仍為實心三角形（密鋪保持）")
    check(TriangleSliderMatrix.is_single_connected(moved), f"方向 {d} 平移後仍連通")

print("== 復原判定 ==")
check(TriangleSliderMatrix(4).is_solved(), "初始態判復原")
# 平移：整組 +3i +5j
g2 = TriangleSliderMatrix(4)
for b in g2.blocks:
    b.location[0] += 3
    b.location[1] += 5
check(g2.is_solved(), "平移後仍判復原")
# 移除一個三角 → 不復原
g3 = TriangleSliderMatrix(4)
g3.blocks.pop()
check(not g3.is_solved(), "缺一塊不判復原")
# 多一塊（在外部補一個）→ 不復原
g4 = TriangleSliderMatrix(4)
g4.blocks.append(type(g4.blocks[0])([10, 10, True]))
check(not g4.is_solved(), "多一塊不判復原")
# 180° 翻轉（上下顛倒）形狀仍是邊長 k 三角形 → 判復原（等價形）
g5 = TriangleSliderMatrix(4)
for b in g5.blocks:
    i, j, up = tri_key(b)
    b.location[0], b.location[1], b.location[2] = 4 - 1 - i, 4 - 1 - j, (not up)
check(g5.is_solved(), "翻轉形狀（等效三角）判復原")
# 非三角形但同塊數：4 個三角排成平行四邊形
g6 = TriangleSliderMatrix(4)
g6.blocks = [type(g6.blocks[0])(loc) for loc in
             ([0, 0, True], [0, 0, False], [0, 1, True], [0, 1, False])]
check(not g6.is_solved(), "平行四邊形（4 塊）不判復原")
# 單元數不等
g7 = TriangleSliderMatrix(4)
g7.blocks = [type(g7.blocks[0])(loc) for loc in ([0, 0, True], [0, 0, False])]
check(not g7.is_solved(), "塊數不足不判復原")

print("== 矩陣視圖（菱形胞 2-bit）==")
g8 = TriangleSliderMatrix(3)
mat = g8.get_matrix()
check(len(mat) == 3 and all(len(r) == 3 for r in mat), "3x3 菱形矩陣尺寸")
# 實心三角的四角是半格：僅含 ▲（值 1），其餘為 3
check(mat == [[3, 3, 1], [3, 1, 0], [1, 0, 0]], f"實心態矩陣 = {mat}")
check(g8.matrix_bounds == {'min_row': 0, 'max_row': 2, 'min_col': 0, 'max_col': 2},
      "matrix_bounds 正確")
# 移除 ▼(0,0) → (0,0) 格應為 1
g8.blocks = [b for b in g8.blocks if tuple(b.location) != (0, 0, False)]
g8.update_matrix()
check(g8.matrix[0][0] == 1, "移除 ▼(0,0) 後該格為 1（僅▲）")

print("== 地圖編碼往返 ==")
g9 = TriangleSliderMatrix(4)
text = g9.export_map()
lines = text.split('\n')
check(len(lines) == 4 and all(len(l) == 4 for l in lines), "導出 4x4 字元矩陣")
check(text == '###^\n##^_\n#^__\n^___', f"實心態編碼（半角為 '^'）：\n{text}")
g10 = TriangleSliderMatrix(4)
check(g10.import_map(text) and g10.positions() == g9.positions(), "導入往返位置一致")
# 半格編碼
half = "^\n_"
g11 = TriangleSliderMatrix(2)
check(g11.import_map(half) and g11.positions() == {(0, 0, True)}, "僅▲ 導入")
bad_map = "^v_x"
g12 = TriangleSliderMatrix(2)
check(not g12.import_map(bad_map), "非法字元導入失敗")

print()
if failures:
    print(f"共 {len(failures)} 項失敗")
    sys.exit(1)
print("全部通過")
