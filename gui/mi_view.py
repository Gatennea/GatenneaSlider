# -*- coding: utf-8 -*-
"""
米字格（方格四切）棋盤幾何視圖（Stage M1：靜態雛形）。

職責：把 (r, c, q) 單位塊轉成螢幕多邊形、算棋形凸包、米字背景網格
（格邊 + 每格兩條對角線，按凸包裁剪）、包圍盒。

**世界座標與三角形版同基準**：都以像素為單位（一格 = cell_size），
這樣 camera / world_to_screen / screen_to_world 三條路徑可以原樣復用，
米字格的矩形包圍盒也就直接走方形相機那套算式。格座標（1 格 = 1 單位）
只在函式內部出現，進出一律經 to_world / from_world。

單位塊是「貼著格子某一條邊的半格」：斜邊 = 格邊（長 cell_size），
兩條直角邊 = 半對角線（長 cell_size/√2）。inset 用的縮放中心是**內心**
而不是重心——重心到三邊的距離不相等（這是米字格與三角版的關鍵差別：
等邊三角的重心就是內心，直角三角形不是），用重心縮放會讓三邊的
視覺間隙一大兩小。

滑動與縫隙命中（M2）：world_to_cell 反查單位塊；gap_at 按「最近的單位邊」
裁定縫隙，gap_line_distance / gap_segment 把 game 的 rank 分界 line 翻成
幾何直線（level = line + 1，與三角版 GAP_LINE_OFFSET 同理：相鄰 rank 的
遠側邊才是真正的切口）。斜向一格之後（規劃 plan-mi-zige-diagonal-unit.md）
位置出現半整數座標，線號隨之可以是半整數：_hit_cells 把半偏移格也查遍、
_edge_gap 按 ½ 對齊反推線號、grid_segments 的橫豎層級由塊的邊導出。
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from game_mi import GAP_DIRECTIONS, gap_candidates, mi_vertices
from gui.hull_util import chord, convex_hull

# 直角等腰三角的內切圓半徑（格為單位）：面積 1/4、半周長 (1+√2)/2
#   → r = (1/4) / ((1+√2)/2) = (√2−1)/2
_INRADIUS = (math.sqrt(2.0) - 1.0) / 2.0

_SQRT2 = math.sqrt(2.0)

# 命中裁定平手時的優先序（h 橫邊、v 豎邊、d1 "\"、d2 "/"）。四族縫在
# 格心/格角交匯，完全等距的點是真平手，必須有個穩定次序才可預期。
_FAM_ORDER = {'h': 0, 'v': 1, 'd1': 2, 'd2': 3}


def _half_round(v: float) -> float:
    """取最近的 ½ 倍數；結果是整數時回 int。

    錯位態的格邊落在半整數格座標上，線號（= 格邊層級 − 1）隨之是半整數，
    取整會把縫線號吞成鄰近整數、點到正確的邊卻給出錯的縫。按 ½ 對齊既吃掉
    反座標換算的浮點誤差，也不吃掉真正的半格。回 int 是為了與
    gap_candidates 的線號型態一致（顯示/JSON 好看，比較上 1 == 1.0 也無妨）。
    """
    h = round(v * 2.0) / 2.0
    return int(h) if float(h).is_integer() else h


class MiBoardView:
    """米字格棋盤的座標轉換與幾何計算。

    座標系（與 TriangleBoardView 一致）：
      格座標   (x, y)，一格 = 1×1，y 軸向下，格心 = (c+½, r+½)
      世界座標 (x, y) * cell_size，即 zoom=1 時的像素位置
    滑塊身份 (r, c, q) 帶 q，命中反查（world_to_cell）留到 M2。
    """

    def __init__(self, cell_size: float = 60.0, gap_width: float = 4.0):
        self.cell_size = float(cell_size)
        self.gap_width = float(gap_width)
        self.inradius = self.cell_size * _INRADIUS   # 像素

    # ---------- 座標換算 ----------
    def to_world(self, x: float, y: float) -> Tuple[float, float]:
        """格座標 → 世界座標（像素）。"""
        return (x * self.cell_size, y * self.cell_size)

    def from_world(self, wx: float, wy: float) -> Tuple[float, float]:
        """世界座標（像素）→ 格座標。"""
        return (wx / self.cell_size, wy / self.cell_size)

    # ---------- 多邊形 ----------
    def incenter(self, r: int, c: int, q: str) -> Tuple[float, float]:
        """單位塊的內心（世界座標，像素）。

        直角等腰三角的內心落在「斜邊中點 → 格心」連線上，距每邊一個
        內切半徑；q 決定斜邊朝向，也就是內心偏在格子的哪一角。
        """
        i = _INRADIUS
        if q == 'N':      # 斜邊在格子上邊 y=r
            p = (c + 0.5, r + i)
        elif q == 'E':    # 斜邊在格子右邊 x=c+1
            p = (c + 1.0 - i, r + 0.5)
        elif q == 'S':    # 斜邊在格子下邊 y=r+1
            p = (c + 0.5, r + 1.0 - i)
        elif q == 'W':    # 斜邊在格子左邊 x=c
            p = (c + i, r + 0.5)
        else:
            raise ValueError(f"unknown quarter: {q}")
        return self.to_world(*p)

    def piece_polygon(self, r: int, c: int, q: str,
                      inset: bool = True) -> list:
        """單位塊多邊形（世界座標頂點列表，3 個頂點）。"""
        pts = [self.to_world(x, y) for (x, y) in mi_vertices(r, c, q)]
        if inset and self.gap_width > 0:
            # 均勻縮放：每條邊各內縮 gap_width/2，相鄰塊間留出視覺間隙。
            # 必須以內心為中心，三邊內縮量才一致（重心不行）。
            f = 1.0 - (self.gap_width / 2.0) / self.inradius
            f = max(0.4, min(1.0, f))
            cx, cy = self.incenter(r, c, q)
            pts = [(cx + (x - cx) * f, cy + (y - cy) * f) for (x, y) in pts]
        return pts

    def piece_center(self, r: int, c: int, q: str) -> Tuple[float, float]:
        """單位塊的內心（繪製提示文字/選中圈的錨點）。"""
        return self.incenter(r, c, q)

    # ---------- 命中 ----------
    def _hit_cells(self, wx: float, wy: float) -> list:
        """點擊位置附近要檢查的格子 (r, c) 清單（整數格在前，次序穩定）。

        對齊態：四塊鋪滿一格，落點所在格就夠；點壓在格線上時還要算上/左
        那一格，落在格線下方/右方不到一個容差時（例如棋形外沿往下 2px）
        也要算下/右那一格，所以取所在格的 3×3 整數格。

        錯位態（斜向一格之後）：B 晶格的塊 key 是半整數，而它橫跨整數格邊
        ——半整數格 (r0±½, c0±½) 的盒子正好蓋住落點，它們的上下沿/左右沿
        就是半整數層級的格邊。不追加這四個半偏移格的話，錯位那一半的塊在
        hit-test 裡全程不存在：點它的內心也返回 None，gap_at 也看不到它的邊。
        """
        gx, gy = self.from_world(wx, wy)
        r0, c0 = math.floor(gy), math.floor(gx)
        return [(r, c)
                for r in (r0 - 1, r0, r0 + 1, r0 - 0.5, r0 + 0.5)
                for c in (c0 - 1, c0, c0 + 1, c0 - 0.5, c0 + 0.5)]

    def world_to_cell(self, wx: float, wy: float, cells=None) \
            -> Optional[Tuple[float, float, str]]:
        """世界座標 → 單位塊 (r, c, q)；空白（或不在 cells 內）回傳 None。

        四塊剛好鋪滿一格，故只須檢查落點附近那幾格的四個三角形；邊界上的點
        同時屬於兩塊，依清單次序 + N/E/S/W 取先命中者（穩定、可預期）。
        r/c 可以是半整數（錯位態的 B 晶格塊）。整數格排在半偏移格之前，
        所以對齊態的裁定與只看整數格時完全一致。
        """
        for r, c in self._hit_cells(wx, wy):
            for q in ('N', 'E', 'S', 'W'):
                if cells is not None and (r, c, q) not in cells:
                    continue
                if _point_in_tri(wx, wy, self.piece_polygon(r, c, q,
                                                           inset=False)):
                    return (r, c, q)
        return None

    def gap_line_distance(self, gap_type: str, line: float,
                          wx: float, wy: float) -> float:
        """點到某條縫隙線的垂直距離（像素）。

        直線方程式（level = line + 1 —— game 的 line 是 rank 分界，
        相鄰 rank 的遠側邊才是幾何上的切口，與三角版 GAP_LINE_OFFSET 同理）：
            'h' ：y = level                      （格邊）
            'v' ：x = level                      （格邊）
            'd1'：y − x = line/2                 （"\" 對角線，鏈 k = r−c）
            'd2'：x + y = line/2 + 1             （"/" 對角線，鏈 k = r+c）
        line 可以是半整數（錯位態的橫豎縫就是半整數線號）；算式本是浮點的，
        半整數原樣成立。
        """
        s = self.cell_size
        level = line + 1
        if gap_type == 'h':
            return abs(wy - level * s)
        if gap_type == 'v':
            return abs(wx - level * s)
        if gap_type == 'd1':
            k = (line / 2.0) * s
            return abs((wy - wx) - k) / _SQRT2
        if gap_type == 'd2':
            k = (line / 2.0 + 1.0) * s
            return abs((wx + wy) - k) / _SQRT2
        raise ValueError(f"unknown gap type: {gap_type}")

    def gap_at(self, wx: float, wy: float, cells, tolerance: float = None):
        """世界座標 → 縫隙 (gap_type, line)；太遠回傳 None。

        裁定規則（規劃 §3）：取點擊位置最近的**單位邊**（任何共享邊），
        該邊所在族與所在線即目標縫隙；等距時取長邊（格邊長 cell_size
        優先於半對角線長 cell_size/√2），仍平手時按 _FAM_ORDER。
        單位邊比「到直線的距離」更貼手感：格角附近最近的是那兩條格邊，
        格心附近最近的是四條半對角線，二者對應玩家肉眼看到的縫。
        """
        if tolerance is None:
            # 一條縫的可點範圍，取 1/12 格（cell_size=60 時 5px）。
            # 不能再放寬：單位塊是直角等腰三角形，內心到三邊都只有
            # 12.4px，而玩家瞄的是三角形的視覺中心（重心），它離最近的
            # 格邊只有 10px。容差一旦接近這個數，「點在方塊中間」就有
            # 接近一半的概率被裁定成點在縫上——實測 9px 時塊內均勻
            # 採樣 93% 判成縫、方塊中心上下抖 4~6px 就有 1/3 誤判。
            # 米字格的第一下選縫、第二下點塊全靠這兩類點擊區分，誤判
            # 的後果是「只是點了幾下方塊、滑塊自己滑走了」：選中縫會
            # 記下定向錨點，下一次點在塊上就直接提交移動。5px 時縫的
            # 可點帶寬 10px（視覺裂縫 4px 的 2.5 倍），方塊中部離最近的
            # 縫也還有 5px 以上的餘量，兩邊都夠用。
            tolerance = max(3.0, self.cell_size / 12.0)
        best = None
        for r, c in self._hit_cells(wx, wy):
            for q in ('N', 'E', 'S', 'W'):
                if (r, c, q) not in cells:
                    continue
                verts = mi_vertices(r, c, q)
                for i in range(3):
                    p = self.to_world(*verts[i])
                    t = self.to_world(*verts[(i + 1) % 3])
                    dist = _point_seg_dist(wx, wy, p, t)
                    if dist > tolerance:
                        continue
                    gap = self._edge_gap(p, t)
                    if gap is None:
                        continue
                    key = (round(dist, 9), -math.dist(p, t),
                           _FAM_ORDER[gap[0]], gap)
                    if best is None or key < best:
                            best = key
        return best[3] if best is not None else None

    def _edge_gap(self, p, t):
        """一條單位邊（世界座標兩端點）→ 所屬縫隙 (gap_type, line)。

        三種單位邊：水平/豎直格邊、兩種斜向半對角線。由端點常數反推 line：
        格邊 y=g → 'h' line = g−1；y−x=k → 'd1' line = 2k；
        x+y=k（k = r+c+1）→ 'd2' line = 2(k−1) = 2(r+c)。

        橫豎的 line 可以是半整數（錯位態的格邊落在半整數層級上，如 y=1.5
        → 'h' line 0.5），所以按 ½ 對齊取最近值，不能 round 取整——取整會
        把點到的邊歸到鄰近的整數線上，而那條線多半切在塊裡、is_valid_gap
        直接否掉，表現就是「點了縫沒反應」。對角族不用改：兩個晶格的
        y−x、x+y 都恆為整數（不變量，見 game_mi 模組 docstring）。
        """
        dx, dy = t[0] - p[0], t[1] - p[1]
        tol = 1e-6
        s = self.cell_size
        if abs(dy) <= tol and abs(dx) > tol:            # 水平格邊
            return ('h', _half_round(p[1] / s - 1.0))
        if abs(dx) <= tol and abs(dy) > tol:            # 豎直格邊
            return ('v', _half_round(p[0] / s - 1.0))
        if abs(dy - dx) <= tol:                          # "\" 半對角線
            k = (p[1] - p[0]) / s
            return ('d1', 2 * int(round(k)))
        if abs(dy + dx) <= tol:                          # "/" 半對角線
            k = (p[0] + p[1]) / s
            return ('d2', 2 * (int(round(k)) - 1))
        return None

    def candidate_gaps(self, wx: float, wy: float, cells, tolerance: float = None):
        """候選縫隙（未經遊戲邏輯驗證），由近到遠（供 HTTP 診斷用）。"""
        if tolerance is None:
            # 與 gap_at 同一個值（理由见 gap_at）：米字格的「點縫」與
            # 「點塊」必須能分開，放寬容差會讓點方塊中部被判成點縫
            tolerance = max(3.0, self.cell_size / 12.0)
        found = []
        for gap_type in GAP_DIRECTIONS:
            for line in gap_candidates(gap_type, cells):
                dist = self.gap_line_distance(gap_type, line, wx, wy)
                if dist <= tolerance:
                    found.append((dist, (gap_type, line)))
        found.sort()
        return [gap for _dist, gap in found]

    def gap_segment(self, gap_type: str, line: float, hull):
        """縫隙 line 與棋形凸包相交的那一段（世界座標兩端點）；不相交回 None。

        凸包是棋形的「棋盤範圍」，縫隙線只畫到它上面（與三角版同理：
        洞裡不斷線，選中的紅線也不會斷在形狀外面）。對角族的縫是整條
        對角線鏈（r−c 或 r+c 相同的全部格子），不是單獨半條斜邊——
        這正是規劃裡「一條鏈是完整的一條縫」的意思。

        line 半整數時（錯位態的橫豎縫）level = line + 1 照樣成立：算式是
        浮點的，chord 也吃浮點層級，沒有整數假設。
        """
        if not hull or len(hull) < 3:
            return None
        # 凸包頂點換回格座標，level 也用格座標（一進一出同一個單位）
        pts = [self.from_world(x, y) for (x, y) in hull]
        level = line + 1
        if gap_type == 'h':
            rng = chord([(x, y) for (x, y) in pts], level)
            ends = [(t, level) for t in rng] if rng else None
        elif gap_type == 'v':
            rng = chord([(y, x) for (x, y) in pts], level)
            ends = [(level, t) for t in rng] if rng else None
        elif gap_type == 'd1':
            k = line / 2.0
            rng = chord([(x, y - x) for (x, y) in pts], k)
            ends = [(t, k + t) for t in rng] if rng else None
        elif gap_type == 'd2':
            k = line / 2.0 + 1.0
            rng = chord([(x, x + y) for (x, y) in pts], k)
            ends = [(t, k - t) for t in rng] if rng else None
        else:
            raise ValueError(f"unknown gap type: {gap_type}")
        if not ends:
            return None
        return tuple(self.to_world(*p) for p in ends)

    # ---------- 棋形 ----------
    def board_hull(self, positions) -> list:
        """棋形（滑塊併集）的凸包（世界座標頂點列表）。"""
        pts = []
        for key in positions:
            pts.extend(self.to_world(x, y) for (x, y) in mi_vertices(*key))
        return convex_hull(pts)

    def grid_segments(self, hull, positions=None) -> list:
        """米字背景網格：凸包內的格邊 + 兩族對角線（世界座標線段）。

        四族直線各自與凸包求交（hull_util.chord），因此洞裡/形狀外都不畫。
        實心矩陣時這張圖就是完整的「方格 + 每格兩條對角線」。

        positions 給定時，橫豎層級由**塊的邊**導出（每塊貢獻上/下沿與左/右沿
        四個層級）：對齊態導出來就是整數，錯位態自動含半整數階層——兩半錯開
        半格後，格邊本來就落在半整數層級上，只畫整數層級會讓背景與塊對不齊。
        對角族仍走整數區間：兩個晶格的 y−x、x+y 都恆為整數（見 game_mi
         docstring 的不變量），且交錯的兩套對角線合起來正好鋪滿整數層級。
        positions 為 None 時退回舊行為（整數區間），供只看凸包的調用方使用。
        """
        if not hull or len(hull) < 3:
            return []
        # 四族各取 (參數 u, 約束量 v) 的點集；v 沿著世界座標計，
        # level 仍以「格」為單位，乘 cell_size 後才是像素級的約束值
        uv = {
            'h': [(x, y) for (x, y) in hull],
            'v': [(y, x) for (x, y) in hull],
            'd1': [(x, y - x) for (x, y) in hull],
            'd2': [(x, x + y) for (x, y) in hull],
        }
        s = self.cell_size
        levels = {}
        for fam in ('h', 'v', 'd1', 'd2'):
            if positions is not None and fam in ('h', 'v'):
                # 橫邊層級 = 每塊的 r 與 r+1；豎邊層級 = c 與 c+1
                k = 0 if fam == 'h' else 1
                vals = {key[k] for key in positions}
                vals |= {key[k] + 1 for key in positions}
                levels[fam] = sorted(vals)
            else:
                vals = [v for (_u, v) in uv[fam]]
                lo = int(math.floor(min(vals) / s))
                hi = int(math.ceil(max(vals) / s))
                levels[fam] = range(lo, hi + 1)
        out = []
        for fam in ('h', 'v', 'd1', 'd2'):
            for level in levels[fam]:
                lv = level * s
                rng = chord(uv[fam], lv)
                if rng is None:
                    continue
                t0, t1 = rng
                if fam == 'h':
                    ends = ((t0, lv), (t1, lv))
                elif fam == 'v':
                    ends = ((lv, t0), (lv, t1))
                elif fam == 'd1':      # y - x = level
                    ends = ((t0, lv + t0), (t1, lv + t1))
                else:                  # x + y = level
                    ends = ((t0, lv - t0), (t1, lv - t1))
                out.append(ends)
        return out

    # ---------- 包圍盒 ----------
    def bounding_box(self, positions) -> Tuple[float, float, float, float]:
        """全部滑塊的世界座標包圍盒 (min_x, min_y, max_x, max_y)。"""
        if not positions:
            return (0.0, 0.0, 0.0, 0.0)
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        for key in positions:
            for (x, y) in mi_vertices(*key):
                wx, wy = self.to_world(x, y)
                min_x, min_y = min(min_x, wx), min(min_y, wy)
                max_x, max_y = max(max_x, wx), max(max_y, wy)
        return (min_x, min_y, max_x, max_y)


def _point_in_tri(px: float, py: float, pts) -> bool:
    """點是否在三角形內（含邊界）。"""
    (ax, ay), (bx, by), (cx, cy) = pts
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)


def _point_seg_dist(px: float, py: float, a, b) -> float:
    """點到線段的距離（線段退化為點時回傳點距）。"""
    vx, vy = b[0] - a[0], b[1] - a[1]
    wx, wy = px - a[0], py - a[1]
    denom = vx * vx + vy * vy
    if denom <= 0.0:
        return math.dist((px, py), a)
    t = (wx * vx + wy * vy) / denom
    t = max(0.0, min(1.0, t))
    return math.dist((px, py), (a[0] + t * vx, a[1] + t * vy))
