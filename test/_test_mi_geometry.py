# -*- coding: utf-8 -*-
"""
米字格幾何單元測試（Stage M1 形狀 + M2 命中幾何）。

執行：python test/_test_mi_geometry.py
涵蓋：單位塊頂點公式、內心（inset 縮放中心）、邊相鄰表封閉性與對稱性、
      8 向平移保持密鋪、凸包裁剪出的背景網格、包圍盒為矩形；
      M2 補：rank 分界 line ↔ 幾何直線的一致性（跨縫的公共邊必須壓在線上）、
      世界座標 → 單位塊命中、縫隙命中（就近單位邊、等距取長邊）、縫隙線段裁剪。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_mi import (  # noqa: E402
    DIRECTIONS,
    MiSliderMatrix,
    gap_index_range,
    mi_vertices,
    neighbors,
    side_of,
)
from gui.mi_view import MiBoardView, _INRADIUS  # noqa: E402

INR = _INRADIUS  # 內心到邊的距離（世界單位，一格 = 1）

failures = []


def check(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        failures.append(msg)


print("== 頂點公式（y 軸向下，格心 (c+½, r+½)）==")
check(mi_vertices(0, 0, 'N') == ((0.5, 0.5), (0.0, 0.0), (1.0, 0.0)),
      "N(0,0)：格心 + 上格邊兩端")
check(mi_vertices(0, 0, 'E') == ((0.5, 0.5), (1.0, 0.0), (1.0, 1.0)),
      "E(0,0)：格心 + 右格邊兩端")
check(mi_vertices(0, 0, 'S') == ((0.5, 0.5), (0.0, 1.0), (1.0, 1.0)),
      "S(0,0)：格心 + 下格邊兩端")
check(mi_vertices(0, 0, 'W') == ((0.5, 0.5), (0.0, 0.0), (0.0, 1.0)),
      "W(0,0)：格心 + 左格邊兩端")
check(mi_vertices(2, 3, 'N') == ((3.5, 2.5), (3.0, 2.0), (4.0, 2.0)),
      "N(2,3) 平移到格 (2,3)")

# 每塊三邊：斜邊長 1、兩條直角邊長 √2/2
import math  # noqa: E402
for q in ('N', 'E', 'S', 'W'):
    pts = mi_vertices(1, 1, q)
    lens = sorted(round(math.dist(pts[i], pts[j]), 9)
                  for i in range(3) for j in range(i + 1, 3))
    check(lens[0] == round(math.sqrt(0.5), 9) and lens[1] == lens[0]
          and lens[2] == 1.0, f"{q}(1,1) 邊長：兩腰 √2/2 + 斜邊 1（實得 {lens}）")

# 同格四塊的斜邊就是格子的四條邊
sq = [mi_vertices(0, 0, q) for q in ('N', 'E', 'S', 'W')]
check(sq[0][1:] == ((0.0, 0.0), (1.0, 0.0)), "N 的斜邊 = 上格邊")
check({sq[1][1], sq[1][2]} == {(1.0, 0.0), (1.0, 1.0)}, "E 的斜邊 = 右格邊")
check({sq[2][1], sq[2][2]} == {(0.0, 1.0), (1.0, 1.0)}, "S 的斜邊 = 下格邊")
check({sq[3][1], sq[3][2]} == {(0.0, 0.0), (0.0, 1.0)}, "W 的斜邊 = 左格邊")

print("== 邊相鄰表 ==")
check(neighbors((0, 0, 'N')) == ((0, 0, 'W'), (0, 0, 'E'), (-1, 0, 'S')),
      "N(r,c) ↔ W(r,c)、E(r,c)、S(r-1,c)")
check(neighbors((0, 0, 'E')) == ((0, 0, 'N'), (0, 0, 'S'), (0, 1, 'W')),
      "E(r,c) ↔ N(r,c)、S(r,c)、W(r,c+1)")
check(neighbors((0, 0, 'S')) == ((0, 0, 'E'), (0, 0, 'W'), (1, 0, 'N')),
      "S(r,c) ↔ E(r,c)、W(r,c)、N(r+1,c)")
check(neighbors((0, 0, 'W')) == ((0, 0, 'N'), (0, 0, 'S'), (0, -1, 'E')),
      "W(r,c) ↔ N(r,c)、S(r,c)、E(r,c-1)")

# 對稱性 + 每塊恰 3 鄰 + 相鄰即共享一條邊
sym_ok = True
for r in range(3):
    for c in range(3):
        for q in ('N', 'E', 'S', 'W'):
            nbs = neighbors((r, c, q))
            if len(set(nbs)) != 3:
                sym_ok = False
            for nb in nbs:
                if (r, c, q) not in neighbors(nb):
                    sym_ok = False
check(sym_ok, "鄰接對稱、每塊恰 3 個不同鄰居")

shared_ok = True
for q in ('N', 'E', 'S', 'W'):
    a = set(mi_vertices(1, 1, q))
    for nb in neighbors((1, 1, q)):
        b = set(mi_vertices(*nb))
        common = a & b
        # 相鄰兩塊恰共享一條邊：兩個公共頂點，且其距離是 1（格邊）或 √2/2（半對角線）
        if len(common) != 2:
            shared_ok = False
            continue
        (p, t) = tuple(common)
        d = math.dist(p, t)
        if abs(d - 1.0) > 1e-9 and abs(d - math.sqrt(0.5)) > 1e-9:
            shared_ok = False
check(shared_ok, "邊相鄰 = 恰共享一條邊（公共邊長 1 或 √2/2）")

# 相鄰塊的公共邊：同格 2 鄰走半對角線（短邊）、跨格 1 鄰走格邊（長邊）
len_ok = True
for q in ('N', 'E', 'S', 'W'):
    a = set(mi_vertices(1, 1, q))
    nbs = neighbors((1, 1, q))
    if sum(1 for nb in nbs if nb[0] == 1 and nb[1] == 1) != 2:
        len_ok = False
    if sum(1 for nb in nbs if not (nb[0] == 1 and nb[1] == 1)) != 1:
        len_ok = False
    for nb in nbs:
        common = a & set(mi_vertices(*nb))
        if len(common) != 2:
            len_ok = False
            continue
        p, t = tuple(common)
        d = math.dist(p, t)
        same_cell = (nb[0] == 1 and nb[1] == 1)
        want = math.sqrt(0.5) if same_cell else 1.0
        if abs(d - want) > 1e-9:
            len_ok = False
check(len_ok, "每塊恰 2 個同格鄰（半對角線）+ 1 個跨格鄰（格邊）")

print("== 8 向平移保持密鋪 ==")
check(len(DIRECTIONS) == 8 and set(DIRECTIONS) == set('qweadzxs'),
      "8 個方向字母齊全（QWER 鍵盤方位）")
check(DIRECTIONS['w'] == (-1, 0) and DIRECTIONS['s'] == (1, 0)
      and DIRECTIONS['a'] == (0, -1) and DIRECTIONS['d'] == (0, 1),
      "W/S/A/D = 上下左右")
check(DIRECTIONS['q'] == (-1, -1) and DIRECTIONS['e'] == (-1, 1)
      and DIRECTIONS['z'] == (1, -1) and DIRECTIONS['x'] == (1, 1),
      "Q/E/Z/X = 四個斜向")

# 任意 (Δr, Δc) 都是晶格平移：單位塊映射到單位塊，且 4 塊填滿一格
trans_ok = True
for r in range(-2, 3):
    for c in range(-2, 3):
        for q in ('N', 'E', 'S', 'W'):
            dr, dc = DIRECTIONS['x']
            key = (r + dr, c + dc, q)
            if mi_vertices(*key) is None:
                trans_ok = False
g = MiSliderMatrix(4, 5)
for name, (dr, dc) in DIRECTIONS.items():
    moved = {(r + dr, c + dc, q) for (r, c, q) in g.positions()}
    if len(moved) != 4 * 4 * 5:
        trans_ok = False
    back = {(r - dr, c - dc, q) for (r, c, q) in moved}
    if back != g.positions():
        trans_ok = False
check(trans_ok, "8 向平移都是雙射、塊數守恆、可逆")

print("== 建局 ==")
g = MiSliderMatrix(4, 5)
check(len(g.blocks) == 4 * 4 * 5, "4×5 棋盤 = 80 塊")
check(g.is_solved(), "建局即實心矩形（復原態）")
counts = {}
for (r, c, _q) in g.positions():
    counts[(r, c)] = counts.get((r, c), 0) + 1
check(all(v == 4 for v in counts.values()), "每格恰 4 塊")
b = g.get_boundaries()
check((b['min_row'], b['max_row'], b['min_col'], b['max_col']) == (0, 3, 0, 4),
      "邊界 = 4 行 5 列")
mat = g.get_matrix()
check(len(mat) == 4 and all(len(row) == 5 for row in mat),
      "4-bit 矩陣形狀 4×5")
check(all(val == 15 for row in mat for val in row),
      "實心棋盤每格掩碼 15（NESW 俱全）")
check(g.is_single_connected(g.positions()), "初始局面單一連通")
check(g.block_at((2, 3, 'E')) is not None
      and g.block_at((2, 3, 'Q')) is None, "block_at 命中/未命中")

# 平移後仍是復原態（矩形可平移）
g2 = MiSliderMatrix(4, 5)
for blk in g2.blocks:
    blk.location = [blk.location[0] + 7, blk.location[1] - 3, blk.location[2]]
check(g2.is_solved(), "整體平移後仍是復原態")
# 3×5 也算是復原態嗎？不是——目標尺寸由 m/n 決定，3×5 既不等于 4×5 也不等于 5×4
g2.blocks = [blk for blk in g2.blocks if blk.location[1] != 1]
g2.update_matrix()
check(not g2.is_solved(), "缺一整列後不是復原態")
# 抽掉一塊 → 該格只有 3 塊，仍不是復原態
g3 = MiSliderMatrix(4, 5)
g3.blocks = [blk for blk in g3.blocks if tuple(blk.location) != (0, 0, 'N')]
g3.update_matrix()
check(not g3.is_solved() and g3.is_single_connected(g3.positions()),
      "抽一塊：非復原但仍連通")

print("== 視圖（靜態渲染幾何）==")
# 單位格視圖（cell_size=1）：世界座標 = 格座標，下面所有斷言都按「格」寫，
# 不掺進像素比例；像素版的換算另有一段單獨驗。
view = MiBoardView(1.0, 0.1)
min_x, min_y, max_x, max_y = view.bounding_box(g.positions())
check((min_x, min_y, max_x, max_y) == (0.0, 0.0, 5.0, 4.0),
      f"4×5 棋盤包圍盒 = 整塊矩形（實得 {(min_x, min_y, max_x, max_y)}）")

# 內心到三邊等距（inset 縮放中心）
in_ok = True
for q in ('N', 'E', 'S', 'W'):
    cx, cy = view.incenter(1, 1, q)
    a, b_, c_ = mi_vertices(1, 1, q)

    def dline(px, py, x1, y1, x2, y2):
        num = abs((y2 - y1) * px - (x2 - x1) * py + x2 * y1 - y2 * x1)
        return num / math.dist((x1, y1), (x2, y2))

    ds = [dline(cx, cy, *a, *b_), dline(cx, cy, *b_, *c_), dline(cx, cy, *c_, *a)]
    if max(ds) - min(ds) > 1e-9:
        in_ok = False
check(in_ok, "內心到三邊等距（縮放後三邊間隙一致）")

# inset 後每條邊都內縮 gap_width/2：頂點沿「內心 → 原頂點」連線收縮 f 倍
poly = view.piece_polygon(1, 1, 'N')
raw = mi_vertices(1, 1, 'N')
cx, cy = view.incenter(1, 1, 'N')
f = 1.0 - (view.gap_width / 2.0) / view.inradius
inset_ok = len(poly) == 3
for (px, py), (ox, oy) in zip(poly, raw):
    if abs(math.dist((px, py), (cx, cy))
           - f * math.dist((ox, oy), (cx, cy))) > 1e-9:
        inset_ok = False
check(inset_ok, "inset 多邊形 3 頂點、各頂點沿內心連線收縮 f 倍")
check(abs(f - (1.0 - 0.1 / 2.0 / INR)) < 1e-12,
      f"inset 係數 = 1 − (gap/2)/內切半徑（實得 {f:.5f}）")
# 相鄰塊拼縫的淨間隙 = gap_width：兩塊的內心必在公共邊的異側，各讓 gap/2
gap_ok = True
for q in ('N', 'E', 'S', 'W'):
    for nb in neighbors((1, 1, q)):
        common = set(mi_vertices(1, 1, q)) & set(mi_vertices(*nb))
        if len(common) != 2:
            gap_ok = False
            continue
        p, t = tuple(common)
        icx, icy = view.incenter(1, 1, q)
        pa = (icx + f * (p[0] - icx), icy + f * (p[1] - icy))
        ta = (icx + f * (t[0] - icx), icy + f * (t[1] - icy))
        icbx, icby = view.incenter(*nb)
        num = abs((ta[1] - pa[1]) * icbx - (ta[0] - pa[0]) * icby
                  + ta[0] * pa[1] - ta[1] * pa[0])
        d = num / math.dist(pa, ta)
        # 內心到公共邊原是內切半徑（世界單位）；inset 後該邊退到半程，故距離
        # = r + (gap/2 換算成世界單位)
        gap_world = view.gap_width / view.cell_size / 2.0
        if abs(d - (INR + gap_world)) > 1e-6:
            gap_ok = False
check(gap_ok, "相鄰塊各讓 gap/2，拼縫淨間隙 = gap_width（內心在公共邊異側）")

# 背景網格：4×5 實心棋盤 → 5 橫 + 6 豎 + 8 條 "\" + 8 條 "/"
# （r−c ∈ [−4, 3]、r+c ∈ [0, 7]，貼角的兩條退化成一個點被裁剪掉）
segs = view.grid_segments(view.board_hull(g.positions()))
from collections import Counter  # noqa: E402
fams = Counter()
for (x1, y1), (x2, y2) in segs:
    if abs(y1 - y2) < 1e-9:
        fams['h'] += 1
    elif abs(x1 - x2) < 1e-9:
        fams['v'] += 1
    elif abs((y2 - y1) - (x2 - x1)) < 1e-9:
        fams['d1'] += 1
    else:
        fams['d2'] += 1
check(fams['h'] == 5 and fams['v'] == 6,
      f"格邊：5 橫 + 6 豎（實得 {fams['h']}/{fams['v']}）")
check(fams['d1'] == 8 and fams['d2'] == 8,
      f"對角線：8 條 \"\\\" + 8 條 \"/\"（實得 {fams['d1']}/{fams['d2']}）")
# 每條線段都落在包圍盒內（裁剪正確）
clip_ok = all(-1e-9 <= min(x1, x2) and max(x1, x2) <= 5.0 + 1e-9
              and -1e-9 <= min(y1, y2) and max(y1, y2) <= 4.0 + 1e-9
              for (x1, y1), (x2, y2) in segs)
check(clip_ok, "背景線段全部裁在棋形包圍盒內")

# 缺一塊後凸包不再是矩形，對角線被裁掉一截（洞的形狀會反映出來）
hole = {(r, c, q) for (r, c, q) in g.positions() if (r, c) != (1, 1)}
hull_hole = view.board_hull(hole)
check(len(hull_hole) == 4, "缺一格後凸包仍是矩形（洞在內部）")
segs_hole = view.grid_segments(hull_hole)
check(len(segs_hole) == len(segs), "洞不影響背景網格（裁剪只看凸包，與三角版一致）")

# 像素版：cell_size=60 時世界座標 = 格座標 × 60（與 TriangleBoardView 同基準，
# camera / world_to_screen 才能原樣復用）
px_view = MiBoardView(60.0, 4.0)
pbox = px_view.bounding_box(g.positions())
check(pbox == (0.0, 0.0, 300.0, 240.0),
      f"像素版 4×5 包圍盒 = (0,0,300,240)（實得 {pbox}）")
psegs = px_view.grid_segments(px_view.board_hull(g.positions()))
check(len(psegs) == len(segs),
      f"像素版背景線段條數不變（{len(psegs)} 條）")
check(all(-1e-9 <= min(x1, x2) and max(x1, x2) <= 300.0 + 1e-9
          and -1e-9 <= min(y1, y2) and max(y1, y2) <= 240.0 + 1e-9
          for (x1, y1), (x2, y2) in psegs),
      "像素版線段也裁在包圍盒內")
check(any(abs(y1 - y2) < 1e-9 and abs(y1 - 120.0) < 1e-9
          for (x1, y1), (x2, y2) in psegs),
      "像素版橫線落在整格邊界上（y = level × cell_size）")
check(px_view.inradius == 60.0 * INR,
      "像素版內切半徑 = cell_size × (√2−1)/2")

# ================================================================ M2 命中幾何
print("== rank 分界 ↔ 幾何直線（M2）==")
# game 的 side_of 是純組合判據；這裡斷言「被縫隙分到兩側的公共邊」在幾何上
# 正好壓在這條縫隙線上，「同側的公共邊」都不在線上。兩者一旦漂移，滑動就會
# 沿著看不見的線切開棋盤（三角版當年就是整體偏離一格）。
view = MiBoardView(60.0, 4.0)
g = MiSliderMatrix(4, 5)
cells = g.positions()
hull = view.board_hull(cells)
on_line = off_line = 0
for fam in ('h', 'v', 'd1', 'd2'):
    for line in gap_index_range(fam, cells):
        if not g.is_valid_gap(fam, line):
            continue
        for a in cells:
            for b in neighbors(a):
                if b not in cells:
                    continue
                common = set(view.piece_polygon(*a, inset=False)) \
                    & set(view.piece_polygon(*b, inset=False))
                if len(common) != 2:
                    check(False, f"相鄰塊 {a} {b} 找不到公共邊")
                    continue
                p, t = sorted(common)
                mid = ((p[0] + t[0]) / 2.0, (p[1] + t[1]) / 2.0)
                d = view.gap_line_distance(fam, line, *mid)
                if side_of(fam, line, a) != side_of(fam, line, b):
                    if d < 1e-9:
                        on_line += 1
                elif d >= 1e-9:
                    off_line += 1
                else:
                    check(False, f"{fam} {line}：同側公共邊 {a} {b} 壓在線上")
check(on_line > 40 and off_line > 0,
      f"跨縫公共邊壓在縫線上（{on_line} 條）、同側公共邊都不在線上（{off_line} 條）")

# 縫隙線段：每條有效縫都與凸包有交，線段落在棋形內、中點壓在線上
seg_n = seg_ok = 0
for fam in ('h', 'v', 'd1', 'd2'):
    for line in gap_index_range(fam, cells):
        if not g.is_valid_gap(fam, line):
            continue
        seg = view.gap_segment(fam, line, hull)
        if seg is None:
            continue
        seg_n += 1
        x1, y1 = seg[0]
        x2, y2 = seg[1]
        min_x, min_y, max_x, max_y = view.bounding_box(cells)
        inside = (min_x - 1e-9 <= min(x1, x2) and max(x1, x2) <= max_x + 1e-9
                  and min_y - 1e-9 <= min(y1, y2) and max(y1, y2) <= max_y + 1e-9)
        mid = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        if inside and view.gap_line_distance(fam, line, *mid) < 1e-9:
            seg_ok += 1
check(seg_n >= 12 and seg_ok == seg_n,
      f"{seg_n} 條有效縫都裁在棋形內、中點壓在縫線上（實得 {seg_ok}）")
# 對角族的縫是整條鏈（不是單獨半條斜邊）：4×5 棋盤 d1 line=0 貫穿整塊
seg_d1 = view.gap_segment('d1', 0, hull)
check(seg_d1 is not None and abs(seg_d1[0][0]) < 1e-9
      and abs(seg_d1[1][0] - 240.0) < 1e-9 and abs(seg_d1[1][1] - 240.0) < 1e-9,
      f"d1 縫是完整對角線鏈（實得 {seg_d1}）")

# 世界座標 → 單位塊：每塊內心都命中自己；形狀外回 None
miss = 0
for key in cells:
    cx, cy = view.incenter(*key)
    if view.world_to_cell(cx, cy, cells) != key:
        miss += 1
check(miss == 0, f"80 塊內心全部命中自己（漏 {miss} 塊）")
check(view.world_to_cell(-600.0, -600.0, cells) is None, "形狀外回 None")
check(view.world_to_cell(30.0, 30.0, cells) == (0, 0, 'N'), "格心上方命中 N")

# 縫隙命中：每條共享邊的中點都命中該邊所屬的縫（就近單位邊）
edge_n = edge_ok = 0
for a in cells:
    for b in neighbors(a):
        if b not in cells:
            continue
        common = set(view.piece_polygon(*a, inset=False)) \
            & set(view.piece_polygon(*b, inset=False))
        if len(common) != 2:
            continue
        p, t = sorted(common)
        mid = ((p[0] + t[0]) / 2.0, (p[1] + t[1]) / 2.0)
        want = view._edge_gap(p, t)
        if want is None:
            continue
        edge_n += 1
        if view.gap_at(mid[0], mid[1], cells) == want:
            edge_ok += 1
check(edge_n > 100 and edge_ok == edge_n,
      f"{edge_n} 條共享邊的中點都命中所屬縫（實得 {edge_ok}）")

# 等距裁定：格角（四族交匯）取長邊 → 橫格邊；格心四條半對角線等距時取族序
check(view.gap_at(60.0, 60.0, cells) == ('h', 0),
      f"格角等距取長邊 → ('h', 0)（實得 {view.gap_at(60.0, 60.0, cells)}）")
check(view.gap_at(30.0, 30.0, cells) is not None,
      f"格心四族等距時有穩定裁定 → {view.gap_at(30.0, 30.0, cells)}")
check(view.gap_at(30.0, 45.0, cells) is None,
      f"離所有邊都遠（10px > 9px tolerance）→ 無縫隙（實得 "
      f"{view.gap_at(30.0, 45.0, cells)}）")
check(view.gap_at(30.0, 24.0, cells) == ('d1', 0),
      f"貼著半對角線 4px → ('d1', 0)（實得 {view.gap_at(30.0, 24.0, cells)}）")
check(view.gap_at(30.0, 45.0, cells, 6.0) is None
      and view.gap_at(30.0, 36.0, cells, 6.0) == ('d1', 0),
      "tolerance 可調：6px 時 4.2px 命中、10.6px 不命中")
hole = {k for k in cells if (k[0], k[1]) != (1, 1)}
check(view.gap_at(90.0, 90.0, hole) is None, "洞心（四鄰都沒塊）→ 無縫隙")
# 帶洞的棋盤：洞邊的公共邊照樣裁定，線段仍裁在凸包內
hole = {k for k in cells if (k[0], k[1]) != (1, 1)}
check(view.gap_at(30.0, 60.0, hole) == ('h', 0),
      f"帶洞棋盤格邊照樣命中（實得 {view.gap_at(30.0, 60.0, hole)}）")
check(view.gap_segment('h', 1, view.board_hull(hole)) is not None,
      "帶洞棋盤的有效縫仍有線段")

print()
if failures:
    print(f"共 {len(failures)} 項失敗:")
    for n in failures:
        print("  -", n)
    sys.exit(1)
print("全部通過")
