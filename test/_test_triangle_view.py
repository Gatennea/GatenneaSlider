# -*- coding: utf-8 -*-
"""
TriangleBoardView 幾何測試（Stage B1）：鎖定座標/命中/縫隙/包圍盒。

執行：python test/_test_triangle_view.py
不依賴 pygame（純數學），可在無顯示環境跑。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_triangle import (  # noqa: E402
    DIRECTIONS,
    GAP_DIRECTIONS,
    TriangleSliderMatrix,
    tri_vertices,
)
from gui.triangle_view import TriangleBoardView  # noqa: E402

failures = []


def check(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        failures.append(msg)


def _polys_overlap(p, q):
    """兩個凸多邊形是否相交（分離軸定理）。"""
    for poly in (p, q):
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            axis = (-(y2 - y1), x2 - x1)
            pa = [pt[0] * axis[0] + pt[1] * axis[1] for pt in p]
            pb = [pt[0] * axis[0] + pt[1] * axis[1] for pt in q]
            if max(pa) <= min(pb) or max(pb) <= min(pa):
                return False
    return True


def _area(pts):
    return abs(sum(pts[i][0] * pts[(i + 1) % 3][1] - pts[(i + 1) % 3][0] * pts[i][1]
                   for i in range(3)) / 2)


view = TriangleBoardView(cell_size=60.0, gap_width=4.0)

print("== 座標轉換往返 ==")
ok = True
for (a, b) in [(0, 0), (3, 5), (-2, 7), (10, -4)]:
    wx, wy = view.to_world(a, b)
    a2, b2 = view.to_oblique(wx, wy)
    if abs(a - a2) > 1e-9 or abs(b - b2) > 1e-9:
        ok = False
check(ok, "to_world / to_oblique 往返一致")
# e1 向右、e2 向右上（y 軸向下）
check(view.to_world(1, 0) == (60.0, 0.0), "e1 指向右")
check(abs(view.to_world(0, 1)[0] - 30.0) < 1e-9 and view.to_world(0, 1)[1] < 0,
      "e2 指向右上（y 為負）")

print("== 朝向約定 ==")
# ▲(0,0) 尖朝上：第三個頂點 y 最小
pts = [view.to_world(*p) for p in tri_vertices(0, 0, True)]
apex = min(pts, key=lambda p: p[1])
check(apex == view.to_world(0.5, 0.8660254037844386 / 1) or apex[1] < 0,
      f"▲(0,0) 尖朝上（apex y={apex[1]:.1f}）")
check(pts[2][1] < pts[0][1] and pts[2][1] < pts[1][1], "▲ 頂點中 b 最大者最靠上")
# 初始大三角形：尖朝上（最高點只有一個，且是頂端）
box = view.bounding_box(TriangleSliderMatrix(4).positions())
top_y = box[1]
n_top = sum(1 for (i, j, up) in TriangleSliderMatrix(4).positions()
            for (x, y) in [view.to_world(*p) for p in tri_vertices(i, j, up)]
            if abs(y - top_y) < 1e-6)
check(n_top == 1, f"大三角形頂端只有 1 個頂點（實測 {n_top}）")

print("== 方向字母與螢幕方向 ==")
screen_ok = True
for letter, (di, dj) in DIRECTIONS.items():
    vx, vy = view.to_world(di, dj)
    base = view.to_world(0, 0)
    dx, dy = vx - base[0], vy - base[1]
    exp = {
        'd': (1, 0), 'a': (-1, 0),
        'e': (0.5, -0.8660254037844386), 'z': (-0.5, 0.8660254037844386),
        'w': (-0.5, -0.8660254037844386), 'x': (0.5, 0.8660254037844386),
    }[letter]
    if abs(dx / 60.0 - exp[0]) > 1e-6 or abs(dy / 60.0 - exp[1]) > 1e-6:
        screen_ok = False
check(screen_ok, "6 個方向的螢幕向量符合鍵盤佈局 W E / A D / Z X")
for gap_type, dirs in GAP_DIRECTIONS.items():
    parallel = True
    for d in dirs:
        di, dj = DIRECTIONS[d]
        if gap_type == 'h' and dj != 0:
            parallel = False
        if gap_type == 'p' and di != 0:
            parallel = False
        if gap_type == 'n' and di + dj != 0:
            parallel = False
    check(parallel, f"'{gap_type}' 族方向平行縫隙線：{dirs}")

print("== 命中 ==")
g = TriangleSliderMatrix(3)
cells = g.positions()
hit_ok = True
for key in cells:
    cx, cy = view.piece_center(*key)
    got = view.world_to_cell(cx, cy)
    if got != key:
        hit_ok = False
        print(f"      {key} -> {got}")
check(hit_ok, f"全部 {len(cells)} 個滑塊重心命中自身")
# 菱形中心（▲▼ 交界）也應命中其中之一
mx, my = view.to_world(0.5, 0.5)
check(view.world_to_cell(mx, my) in cells, "菱形中心命中某一半")
# 三角密鋪鋪滿整個平面：遠處點也會落到某個晶格三角上，
# 但該三角不在棋盤上（呼叫方再據此判斷「點到空白」）
far = view.world_to_cell(5000.0, -7000.0)
check(far is not None and far not in cells, f"遠處點落到棋盤外的晶格三角：{far}")

print("== 縫隙距離 ==")
# 'h' 族：b = 1 的水平線在 y = -height
check(abs(view.gap_line_distance('h', 1, 123.0, -view.height)) < 1e-9,
      "'h' 線上距離為 0")
check(abs(view.gap_line_distance('h', 1, 0.0, 0.0) - view.height) < 1e-9,
      "原點到 'h'(1) 距離 = 三角高")
# 'p' 族：a = 1 的線通過 to_world(1, 0)
px, py = view.to_world(1, 0)
check(abs(view.gap_line_distance('p', 1, px, py)) < 1e-9, "'p' 線上距離為 0")
# 'n' 族：a+b = 1 的線通過 to_world(1, 0) 與 to_world(0, 1)
nx, ny = view.to_world(0, 1)
check(abs(view.gap_line_distance('n', 1, px, py)) < 1e-9
      and abs(view.gap_line_distance('n', 1, nx, ny)) < 1e-9,
      "'n' 線穿過 (1,0) 與 (0,1)")
# 候選縫隙：貼著 'h'(1) 線取點
gaps = view.candidate_gaps(0.0, -view.height, cells, tolerance=3.0)
check(('h', 1) in gaps, f"貼線命中 'h'(1)：{gaps}")

print("== 多邊形與間隙 ==")
poly_up = view.piece_polygon(0, 0, True, inset=True)
poly_raw = view.piece_polygon(0, 0, True, inset=False)
check(len(poly_up) == 3 and len(poly_raw) == 3, "三角形多邊形 3 頂點")
check(_area(poly_up) < _area(poly_raw), "內縮後面積變小")
# 相鄰兩塊（▲(0,0) 與 ▼(0,0)）內縮後不重疊：間隙 > 0
a = view.piece_polygon(0, 0, True)
b = view.piece_polygon(0, 0, False)
check(not _polys_overlap(a, b), "相鄰 ▲/▼ 內縮後不重疊（有視覺間隙）")

print("== 包圍盒 ==")
box = view.bounding_box(TriangleSliderMatrix(4).positions())
w = box[2] - box[0]
h = box[3] - box[1]
check(abs(w - 4 * 60.0) < 1e-6, f"邊長 4 的三角形寬 = 4*cell（{w:.1f}）")
check(abs(h - 4 * view.height) < 1e-6, f"高 = 4*height（{h:.1f}）")
check(view.bounding_box(set()) == (0.0, 0.0, 0.0, 0.0), "空集合包圍盒為零")

print()
if failures:
    print(f"共 {len(failures)} 項失敗")
    sys.exit(1)
print("全部通過")
