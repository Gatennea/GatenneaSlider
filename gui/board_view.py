# -*- coding: utf-8 -*-
"""
幾何抽象：單一謎題形態的座標轉換與命中計算。

這裡只有 SquareBoardView；三角形密鋪的幾何在 gui/triangle_view.py
（TriangleBoardView）。兩個類各自獨立、沒有共同介面，上層按 triangle_mode
分支選擇用哪一個——目前只有命中/查格這條路是委派過來的，繪製仍是兩套
獨立實現。要加第三種形態時，先收斂出共同介面再動手（見 docs/agent/readme_to_agent.md）。
"""

from __future__ import annotations

import math
from typing import Tuple, Optional, Generator


class SquareBoardView:
    """正方形網格幾何輔助（接受浮點座標，支援動畫插值）。"""

    def __init__(self, cell_size: float = 60.0, gap_width: float = 4.0):
        self.cell_size = float(cell_size)
        self.gap_width = float(gap_width)
        self._unit = self.cell_size + self.gap_width

    # ---------- 座標轉換 ----------
    def cell_to_world(self, r: float, c: float) -> Tuple[float, float]:
        """格子座標 (row, col) → 世界座標 (x, y)。"""
        return c * self._unit, r * self._unit

    def world_to_cell(self, wx: float, wy: float) -> Optional[Tuple[float, float]]:
        """世界座標 (x, y) → 格子座標 (row, col)；落在縫隙則回傳 None。"""
        c = wx // self._unit
        r = wy // self._unit
        if (wx - c * self._unit) >= self.cell_size or (wy - r * self._unit) >= self.cell_size:
            return None
        return r, c

    def block_rect(self, r: float, c: float) -> Tuple[float, float, float, float]:
        """回傳方塊在世界座標中的 (x, y, w, h)。"""
        x, y = self.cell_to_world(r, c)
        return x, y, self.cell_size, self.cell_size

    # ---------- 縫隙命中 ----------
    def candidate_gaps(
        self,
        wx: float,
        wy: float,
        bounds: dict,
        tolerance: float = 10.0,
    ) -> Generator[Tuple[str, int], None, None]:
        """候選縫隙（未經遊戲邏輯驗證）。"""
        min_row, max_row = bounds['min_row'], bounds['max_row']
        min_col, max_col = bounds['min_col'], bounds['max_col']
        gap = self.gap_width

        for i in range(min_row, max_row + 2):
            gap_y = i * self._unit - gap / 2
            if abs(wy - gap_y) < gap + tolerance:
                board_left = min_col * self._unit
                board_right = (max_col + 1) * self._unit
                if board_left - 50 < wx < board_right + 50:
                    yield 'h', i - 1

        for j in range(min_col, max_col + 2):
            gap_x = j * self._unit - gap / 2
            if abs(wx - gap_x) < gap + tolerance:
                board_top = min_row * self._unit
                board_bottom = (max_row + 1) * self._unit
                if board_top - 50 < wy < board_bottom + 50:
                    yield 'v', j - 1


# ----------------------------------------------------------------------
# 通用多邊形視圖（S1b：解釋器路線的「顯卡」）
# ----------------------------------------------------------------------
def point_in_polygon(pt, poly) -> bool:
    """通用多邊形內點判定（射線法），不限凸性。"""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xin:
                inside = not inside
    return inside


# ----------------------------------------------------------------------
# 縫幾何的公共積木（S2：接觸邊界模型）
# ----------------------------------------------------------------------
# 頂點容差：形狀由浮點座標定義（cell_polygon 的剛體平移是浮點加減），同一
# 頂點在相鄰兩塊裡會相差 ~1e-15——**精確相等會漏計共邊**（實測 34/66 對，
# 連通圖形的共邊被生生少算一半）。必須容差匹配。取 1e-6：頂點格的最小
# 間距約 0.5 幾何單位（實測各板型），容差比它小三個量級，既吃掉浮點噪聲
# 又不會把兩個不同頂點並成一個。
_VTOL = 1e-6


def _seg_dist(px, py, ax, ay, bx, by):
    """點 (px,py) 到線段 (ax,ay)-(bx,by) 的最短距離（退化線段 = 點距）。"""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _poly_area(pts):
    """多邊形面積（shoelace，恆正）。"""
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _poly_perimeter(pts):
    """多邊形周長。"""
    n = len(pts)
    return sum(math.hypot(pts[(i + 1) % n][0] - pts[i][0],
                          pts[(i + 1) % n][1] - pts[i][1])
               for i in range(n))


def inset_unit_polygon(pts, d):
    """單位多邊形各邊均勻內縮 d（幾何單位）：向質心縮放。

    內半徑用 2A/P 近似（三角形精確、近似正多邊形誤差可忽略）——與
    ``TriangleBoardView.piece_polygon`` 的 inset 同一手法（那裡用精確
    內切圓半徑）。縮放因數鉗在 [0.4, 1.0]：d 相對塊太大時不允許縮沒。
    用途只有一個：捆綁組渲染要「普通塊形狀」（組外留正常縫隙），見
    ``_draw_bandaged_groups_poly`` 的 inset 參數。
    """
    if d <= 0.0 or len(pts) < 3:
        return tuple(pts)
    a = _poly_area(pts)
    p = _poly_perimeter(pts)
    if a <= 0.0 or p <= 0.0:
        return tuple(pts)
    inradius = 2.0 * a / p
    if inradius <= 0.0:
        return tuple(pts)
    f = 1.0 - d / inradius
    f = max(0.4, min(1.0, f))
    cx = sum(x for x, _ in pts) / len(pts)
    cy = sum(y for _, y in pts) / len(pts)
    return tuple((cx + (x - cx) * f, cy + (y - cy) * f) for x, y in pts)


class SpecPolygonView:
    """消費 ``BoardSpec.cell_polygon`` 的**形態無關**視圖。

    與上方兩個手繪 view 的根本差別：本類**不認識任何具體形態**（沒有
    square / triangle / mi 分支），只認「spec 把形狀寫成了數據」這件事。
    判斷標準因而從「你是哪個形態」變成「你有沒有 cell_polygon」。

    任何新板型只要提供了 cell_polygon，就能被本類畫出來並命中——這是
    P3b 通用渲染通道的幾何核心，也是「幾何引擎＝解釋器」的顯示端。

    約定（與既有 view 對齊）：幾何單位座標 → 世界座標是「乘 cell_size、
    加 origin」的純縮放平移；origin 由呼叫方按整盤包圍盒自行決定。
    """

    def __init__(self, spec, cell_size: float = 60.0, gap_width: float = 0.0):
        if spec is None or getattr(spec, 'cell_polygon', None) is None:
            raise ValueError(
                "SpecPolygonView 需要帶 cell_polygon 的 BoardSpec"
                "（形狀沒寫成數據的板型無法通用渲染）")
        self.spec = spec
        self.cell_size = float(cell_size)
        # 視覺縫寬（世界單位）：只影響 inset 變體（捆綁組的「普通塊形狀」），
        # 普通塊繪製不吃它（走 _rounded_polygon_points 的圓角削進）。
        self.gap_width = float(gap_width)

    # ---------- 幾何（單位座標）----------
    def unit_polygon(self, point, orient='') -> Tuple:
        """該塊的單位多邊形（直接來自定義，未縮放）。"""
        return tuple(self.spec.cell_polygon(point, orient))

    def bounds_of(self, blocks) -> Tuple[float, float, float, float]:
        """一串塊在幾何單位下的包圍盒 (minx, miny, maxx, maxy)。"""
        xs, ys = [], []
        for b in blocks:
            for (x, y) in self.unit_polygon(b.point, b.orient):
                xs.append(x)
                ys.append(y)
        if not xs:
            return 0.0, 0.0, 0.0, 0.0
        return min(xs), min(ys), max(xs), max(ys)

    # ---------- 世界座標 ----------
    def world_polygon(self, point, orient='', origin=(0.0, 0.0),
                      inset: bool = False) -> Tuple:
        """該塊在世界座標下的多邊形（供繪製 / 命中）。

        inset=True 給「普通塊形狀」（各邊內縮 half-gap，組外留正常縫隙），
        只服務捆綁組渲染；普通塊與命中一律用 inset=False 的精確形狀。
        """
        ox, oy = origin
        s = self.cell_size
        pts = self.unit_polygon(point, orient)
        if inset and self.gap_width > 0:
            pts = inset_unit_polygon(pts, (self.gap_width / 2.0) / s)
        return tuple((x * s + ox, y * s + oy)
                     for (x, y) in pts)

    def origin_of(self, board, margin: float = 0.0):
        """佈局原點（世界座標）：包圍盒左上角對齊 margin。

        與 layout 同公式，拆出來供渲染 / 命中 / 箭頭錨點共用同一個
        origin——三處各算一遍 origin，曾是「zoom≠1 全鏈路錯位」的病根。
        """
        minx, miny, _mx, _my = self.bounds_of(board.blocks)
        s = self.cell_size
        return (margin - minx * s, margin - miny * s)

    def layout(self, board, margin: float = 0.0):
        """整盤佈局：回傳 [(塊鍵, 世界多邊形), ...]，origin 對齊包圍盒左上角。"""
        origin = self.origin_of(board, margin)
        return [((b.point, b.orient),
                 self.world_polygon(b.point, b.orient, origin))
                for b in board.blocks]

    # ---------- 命中 ----------
    def hit(self, wx, wy, board, origin=(0.0, 0.0)):
        """世界座標命中塊鍵 -> (point, orient) or None。

        逐一測試是 O(n)；大量命中時呼叫方可自建空間索引，此處先求正確
        （先在「能不能通用」上站住，再談快）。
        """
        for b in board.blocks:
            if point_in_polygon(
                    (wx, wy), self.world_polygon(b.point, b.orient, origin)):
                return (b.point, b.orient)
        return None

    # ---------- 縫幾何（S2：接觸邊界模型）----------
    # 縫的視覺身份 = 分區之間的接觸邊足跡，**不是代數直線 {f=t}**：
    # 恆等空間各向異性（平面映射是各軸不同比例的縮放），代數直線落進
    # 平面會切進塊內部（實測穿過某塊質心）——畫直線會誤導玩家。故候選
    # 縫與足跡一律從「跨分區接觸邊」出發，與引擎 rank 分區逐字對齊。

    def _family_candidates(self, board, fam) -> list:
        """一個縫族的候選縫 [(t, line), ...]。

        兩條來源：
        · 板型掛了 ``seam_lines`` 鉤子（顯式鄰接板型：縫必須落在真實塊邊
          上）→ 直接用幾何給出的縫線。**逐整數 t 枚舉在這裡是錯的**：它會
          把「線穿過塊內部」的 t 也算成候選，畫到盤面上就是鋸齒縫。
        · 否則沿用 rank 邊界口徑（= distinct rank 邊界，去最大值）：
          與 ``Board.legal_moves`` 的 t 逐字對齊：分區只在 t 跨過某個 rank
          值時改變，等價類 (v_i, v_{i+1}] 的**首個整數** t = v_i + 1 就是
          legal_moves 實際發出的標號（回放/存檔的 gap_line 也這個口徑）；
          外部線號 line = v_i / line_scale（4× 線分辨率的族會在這裡出現
          ¼ 線，與 all_gaps 同約定）。
        舊 all_gaps 逐整數 t 枚舉會把同分區別名重複計數（碎三角 390 vs
        121）——玩家只認「分區邊界」，故按 distinct 收斂。
        """
        hook = getattr(self.spec, 'seam_lines', None)
        if hook is not None:
            return list(hook(board, fam))
        vals = sorted({fam.rank_of(k[0], k[1]) for k in board.keys})
        out = []
        for v in vals[:-1]:
            line = v / fam.line_scale
            line = int(line) if line == int(line) else line
            out.append((v + 1, line))
        return out

    def seam_candidates(self, board) -> list:
        """全部候選縫 [(gap_type, line), ...]（跨族，按板型族序）。"""
        out = []
        for fam in self.spec.seam_families:
            out.extend((fam.name, line)
                       for _t, line in self._family_candidates(board, fam))
        return out

    def contact_edges(self, board, origin=(0.0, 0.0)) -> list:
        """跨塊接觸邊：[((塊鍵1, 塊鍵2), 世界線段), ...]。

        判據 = 兩塊多邊形恰有 2 個公共頂點（容差匹配）⇒ 共邊；
        1 個公共頂點 = 只擦角（排除），3 個 = 重合（排除）。
        bbox 預濾後 O(n²)；容差必要性見 _VTOL 註釋。
        """
        items = []
        for b in board.blocks:
            poly = self.world_polygon(b.point, b.orient, origin)
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            items.append(((b.point, b.orient), poly,
                          (min(xs), min(ys), max(xs), max(ys))))
        out = []
        for i in range(len(items)):
            k1, p1, bb1 = items[i]
            for j in range(i + 1, len(items)):
                k2, p2, bb2 = items[j]
                if (bb1[2] < bb2[0] - _VTOL or bb2[2] < bb1[0] - _VTOL or
                        bb1[3] < bb2[1] - _VTOL or bb2[3] < bb1[1] - _VTOL):
                    continue
                shared = [a for a in p1
                          if any(abs(a[0] - b[0]) <= _VTOL and
                                 abs(a[1] - b[1]) <= _VTOL for b in p2)]
                if len(shared) != 2:
                    continue
                out.append(((k1, k2), (shared[0], shared[1])))
        return out

    def seam_segments(self, board, gap_type, line, origin=(0.0, 0.0)) -> list:
        """一條縫的幾何足跡：跨分區接觸邊（世界座標線段列表）。

        判據純代數：邊 (A, B) 在足跡上 ⟺ min(r_A, r_B) < t ≤ max(r_A, r_B)
        （rank 相同 = 平行於縫，排除）。足跡是分區邊界（鋸齒狀），
        不是代數直線 {f=t}——理由見本節開頭註釋。
        """
        fam = next((f for f in self.spec.seam_families
                    if f.name == gap_type), None)
        if fam is None:
            return []
        hook = getattr(self.spec, 'seam_lines', None)
        if hook is not None:
            # 显式邻接板型：线号 ↔ 缝号由几何缝线表反查（line = t - 1，
            # 但这里不假定换算关系，直接查表，避免 ±1 口径漂移）。
            t = next((tt for tt, ln in hook(board, fam) if ln == line), None)
            if t is None:
                return []
        else:
            t = int(round(fam.line_scale * line)) + 1
        ranks = {k: fam.rank_of(k[0], k[1]) for k in board.keys}
        out = []
        for (k1, k2), seg in self.contact_edges(board, origin):
            r1, r2 = ranks[k1], ranks[k2]
            lo, hi = (r1, r2) if r1 <= r2 else (r2, r1)
            if lo < t <= hi:
                out.append(seg)
        return out

    def gap_candidates(self, wx, wy, board, origin=(0.0, 0.0),
                       tolerance: float = 10.0) -> list:
        """點擊附近的候選縫，按 (距離, 族序, 線號) 排序。

        回傳 [(gap_type, line, 距離), ...]，只收距離 ≤ tolerance 的。
        一條接觸邊可被多條候選縫共享（兩塊 rank 之間有多個 distinct
        邊界時，實測 1~4 條）——每條共享邊對每個覆蓋它的候選縫各計
        一次點段距，取該縫的最小值。

        ⚠️ 本方法**不判合法性/活性**：候選只是「幾何上離點擊最近」。
        呼叫方按距離序逐條過 is_valid_gap / is_live_gap（活性校驗在
        引擎適配器），第一條活縫即選中——歧義就這麼決勝。
        """
        fams = list(self.spec.seam_families)
        order = {f.name: i for i, f in enumerate(fams)}
        cand_t = {}
        fam_vals = {}
        for f in fams:
            pts = self._family_candidates(board, f)
            fam_vals[f.name] = [t for t, _ln in pts]
            for t, ln in pts:
                cand_t[(f.name, t)] = ln
        items = []
        for b in board.blocks:
            poly = self.world_polygon(b.point, b.orient, origin)
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            items.append(((b.point, b.orient), poly,
                          (min(xs), min(ys), max(xs), max(ys)),
                          {f.name: f.rank_of(b.point, b.orient)
                           for f in fams}))
        best = {}
        n = len(items)
        for i in range(n):
            _k1, p1, bb1, r1 = items[i]
            for j in range(i + 1, n):
                _k2, p2, bb2, r2 = items[j]
                if (bb1[2] < bb2[0] - _VTOL or bb2[2] < bb1[0] - _VTOL or
                        bb1[3] < bb2[1] - _VTOL or bb2[3] < bb1[1] - _VTOL):
                    continue
                shared = [a for a in p1
                          if any(abs(a[0] - b[0]) <= _VTOL and
                                 abs(a[1] - b[1]) <= _VTOL for b in p2)]
                if len(shared) != 2:
                    continue
                d = _seg_dist(wx, wy,
                              shared[0][0], shared[0][1],
                              shared[1][0], shared[1][1])
                for fname in order:
                    ra, rb = r1[fname], r2[fname]
                    if ra == rb:
                        continue
                    lo, hi = (ra, rb) if ra <= rb else (rb, ra)
                    for t in fam_vals[fname]:
                        if lo < t <= hi:
                            key = (fname, cand_t[(fname, t)])
                            if key not in best or d < best[key]:
                                best[key] = d
        out = [(gt, ln, dist) for (gt, ln), dist in best.items()
               if dist <= tolerance]
        out.sort(key=lambda item: (item[2], order[item[0]], item[1]))
        return out
