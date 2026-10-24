# -*- coding: utf-8 -*-
"""通用多邊形視圖（SpecPolygonView）的形態無關性回歸。

執行：python test/_test_polygon_view.py
約定：腳本型回歸（check 收集失敗，退出碼非 0 即失敗），零 pygame。

這個檔案是「幾何引擎＝解釋器」路線（docs/spec/GUI解释器化接入计划）
S1b 的產物，鎖的是一件事：**同一個視圖類，一行不改，能不能把不同形態
畫出來**。

過去每種形態各有一份手繪 view（SquareBoardView / TriangleBoardView），
上層靠形態旗標分支挑選；SpecPolygonView 不認識任何形態，只認
``spec.cell_polygon``——判斷標準從「你是誰」變成「你有沒有形狀數據」。

覆蓋：
  1 構造        —— 四種板型（square/tri/mi/shatter）都能建視圖
  2 佈局完整性  —— 每塊都產出合法閉合多邊形，面積非零
  3 佈局歸一    —— 整盤佈局左上角對齊 margin（縮放平移正確）
  4 命中自洽    —— 每塊多邊形的質心都能命中自己（且不誤鄰）
  5 形態無關性  —— 四種形態走**同一份**視圖代碼，無形態分支
  6 形狀保真    —— 面積/邊長與幾何定義一致（方=單位方、tri=正三角）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import make_board  # noqa: E402
from engine.registry import mi_spec, square_spec, tri_spec  # noqa: E402
from engine.shatter_geometry import shatter_spec  # noqa: E402
from gui.board_view import SpecPolygonView, point_in_polygon  # noqa: E402

failures = []


def check(cond, msg):
    print(f"  {'ok' if cond else 'FAIL'}: {msg}")
    if not cond:
        failures.append(msg)


def area(poly):
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def centroid(poly):
    n = len(poly)
    return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)


# 四種形態：(標籤, board, 期望每塊邊數)
# 注意：全都走同一個 SpecPolygonView 類，本測試裡**沒有任何形態分支**。
_FORMS = [
    ('square', make_board('square', m=4, n=4), 4),
    ('tri', make_board('tri', k=4), 3),
    ('mi', make_board('mi', m=3, n=3), 3),
    ('shatter', make_board('shatter'), 3),
]

CELL = 60.0

# ======================================================================
print("== 1 構造：四種板型都能建通用視圖 ==")
views = {}
for tag, board, _edges in _FORMS:
    try:
        views[tag] = SpecPolygonView(board.spec, cell_size=CELL)
        check(True, f"{tag} 構造 SpecPolygonView 成功")
    except Exception as e:
        check(False, f"{tag} 構造失敗 {type(e).__name__}: {e}")
        views[tag] = None
check(len(views) == 4, "四種形態全部構造成功（含碎三角）")

# ======================================================================
print("== 2 佈局完整性 + 面積非零 ==")
for tag, board, edges in _FORMS:
    v = views[tag]
    if v is None:
        continue
    rows = v.layout(board)
    check(len(rows) == board.block_count,
          f"{tag} 佈局塊數 == 局面塊數（{len(rows)}/{board.block_count}）")
    bad_edge = [k for k, poly in rows if len(poly) != edges]
    check(not bad_edge, f"{tag} 每塊多邊形邊數 == {edges}（異常 {len(bad_edge)}）")
    bad_area = [k for k, poly in rows if area(poly) <= 1e-9]
    check(not bad_area, f"{tag} 每塊面積 > 0（退化 {len(bad_area)}）")

# ======================================================================
print("== 3 佈局歸一：左上角對齊 margin（縮放平移正確）==")
for tag, board, _e in _FORMS:
    v = views[tag]
    if v is None:
        continue
    rows = v.layout(board, margin=10.0)
    xs = [p[0] for _k, poly in rows for p in poly]
    ys = [p[1] for _k, poly in rows for p in poly]
    check(abs(min(xs) - 10.0) < 1e-6 and abs(min(ys) - 10.0) < 1e-6,
          f"{tag} 佈局左上角 == margin（實際 {min(xs):.4f}, {min(ys):.4f}）")

# ======================================================================
print("== 4 命中自洽：每塊質心命中自己 ==")
# 佈局與命中必須用同一 origin 才有意義；layout() 內部自帶歸一 origin，
# 故這裡統一用 origin=(0, 0) 重算多邊形再比對命中。
for tag, board, _e in _FORMS:
    v = views[tag]
    if v is None:
        continue
    rows = [((b.point, b.orient),
             v.world_polygon(b.point, b.orient, (0.0, 0.0)))
            for b in board.blocks]
    wrong = 0
    for key, poly in rows:
        if v.hit(*centroid(poly), board, (0.0, 0.0)) != key:
            wrong += 1
    check(wrong == 0, f"{tag} 每塊質心命中自己（錯判 {wrong}/{len(rows)}）")

# ======================================================================
print("== 5 形態無關性：同一份代碼畫四種形態（無任何形態分支）==")
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'gui', 'board_view.py'), encoding='utf-8').read()
method_src = src.split('class SpecPolygonView:')[1]
bad_tokens = [t for t in ("'square'", '"square"', "'triangle'", '"triangle"',
                          "'mi'", '"mi"', "'shatter'", '"shatter"',
                          'triangle_mode', 'mi_mode')
              if t in method_src]
check(not bad_tokens,
      f"SpecPolygonView 方法體內無形態分支（發現 {bad_tokens}）")

# ======================================================================
print("== 6 形狀保真：面積/尺度與幾何定義一致 ==")
sq = SpecPolygonView(square_spec(4, 4), cell_size=CELL)
# 單位方格 × cell_size → 世界面積 = cell²
poly = sq.world_polygon((0, 0), '', (0.0, 0.0))
check(abs(area(poly) - CELL ** 2) < 1e-6,
      f"square 單塊世界面積 == cell²（{area(poly):.2f} vs {CELL**2:.2f}）")
# 三角必須是正三角：三邊相等
import math  # noqa: E402
tp = tri_spec(4)
tv = SpecPolygonView(tp, cell_size=CELL)
tpoly = tv.world_polygon((0, 0), 'up', (0.0, 0.0))
sides = [math.dist(tpoly[i], tpoly[(i + 1) % len(tpoly)])
         for i in range(len(tpoly))]
check(max(sides) - min(sides) < 1e-6,
      f"tri 單塊三邊相等 == 正三角（{[round(s,3) for s in sides]}）")
mv = SpecPolygonView(mi_spec(3, 3), cell_size=CELL)
mpoly = mv.world_polygon((0, 0), 'N', (0.0, 0.0))
check(len(mpoly) == 3, f"mi 單塊為 3 邊形（{len(mpoly)}）")
check(point_in_polygon(centroid(mpoly), mpoly), "point_in_polygon 對自身質心為真")

# ======================================================================
print()
if failures:
    print(f"共 {len(failures)} 項失敗")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("全部通過")
