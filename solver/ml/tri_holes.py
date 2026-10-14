# -*- coding: utf-8 -*-
"""三角形「洞 / 凸起」检测（M0 F2 面板用，计划 §4）。

方形版 `hole_detector.detect_holes` 是**矩形网格**上的洪水填充，套不到三角形上：
  · 方形单元是轴对齐方格，窗口 = 矩形，逐格判「在窗口内」毫无歧义；
  · 三角单元在斜坐标 `(i, j, up)`，窗口 = 大三角（实测**没有 120° 旋转对称**，
    只有恒等与转置，见計劃 §5），**边界是斜线不是直线**，「在窗口内」必须
    真的按斜邊判，不能用 `r0 <= r < r0+rh` 那种範圍比較。

所以本模組走兩條路：
  1. `in_goal(cell, goal)`：單元是否落在目標形狀集合內 —— 直接查集合，
     不做幾何運算（k² ≤ 64，O(1)）。這是最不容易出錯的口徑。
  2. 洪水填充用**引擎自己的鄰接關係**（`game_triangle.neighbors`），保證
     「洞」= 真正連通的一片空白，與遊戲裡的連通語義一致。

記號語義（沿用方形，計劃 §4 說「異形版語義在實現時定」，這裡定為）：
    目標窗口內、被單元包圍的空白（孔洞）  = 圓圈
    目標窗口內、連通窗口邊緣的空白（缺口）= 三角形
    目標窗口外的單元（凸起）              = 斜方形（菱形）
顏色：大孔洞/缺口 = 紅色，小 = 藍色；凸起 = 黃色（與方形一致，便於對照）。

「孔洞 / 缺口」的區分靠**是否觸到窗口邊界**：方形裡窗口是矩形、邊界明確；
三角形的大三角有三條斜邊，任一空白片連到斜邊就是缺口。判定用「該片在窗口
內的 3-鄰接閉包裡能否沿邊界走出去」——實現方式是：把窗口內空白做洪水填充，
再檢查這片白文的成員是否有任何一個的鄰接單元在**窗口外**。
"""
from collections import deque

from game_triangle import neighbors as tri_neighbors

__all__ = ['in_goal', 'detect_tri_holes', 'hole_color', 'HOLE_LARGE',
           'HOLE_SMALL', 'PROTRUSION_COLOR']

# 記號顏色（與方形 _draw_debug_holes 保持一致）
_LARGE = (255, 80, 80)
_SMALL = (80, 160, 255)
_PROTRUSION = (255, 210, 60)

HOLE_LARGE = 'large'
HOLE_SMALL = 'small'
PROTRUSION_COLOR = _PROTRUSION


def hole_color(hole):
    """洞的標記顏色（大 = 紅、小 = 藍）。"""
    return _LARGE if hole['size'] == HOLE_LARGE else _SMALL


def in_goal(cell, goal):
    """單元是否在目標形狀內。`goal` 是 `(i, j, up)` 的集合。

    三角版就是查集合——沒有任何「範圍比較」的機會，所以不會有邊界誤差。
    這一條也讓 GUI 畫框與求解器聚拢度共用同一 `goal`（`tri_placement`
    的 `TriPlacement.cells`），口徑天然一致。
    """
    return cell in goal


def detect_tri_holes(coords, goal, step=1):
    """檢測目標三角內的洞 + 凸起。

    參數
    ----
    coords : iterable
        當前單元集 `(i, j, up)`。
    goal   : iterable
        目標形狀單元集（**已經帶好放置偏移**，即 `TriPlacement.cells`）。
        這一點是計劃 §4「面板與求解器同源」的落點：傳進來的必須是
        `best_placement(...).cells`，不是自己另算一份。
    step   : int
        等級，**只影響洞的大小分檔**（與方形同語義：大洞/小洞的記號大小）。
        不影響「是不是洞」的判定。

    返回 ``(holes, protrusions)``：
        holes        : [{cells, type, size}]，`type` ∈ {'hole','gap'}
        protrusions  : 目標形狀外的單元列表（保持輸入順序）
    """
    cells = frozenset(coords)
    goal = frozenset(goal)

    inside = {c for c in cells if c in goal}
    protrusions = [c for c in cells if c not in goal]

    # 窗口內的空白（= 目標形狀裡沒被占的單元）
    blanks = goal - inside
    holes = []
    seen = set()
    for start in sorted(blanks):
        if start in seen:
            continue
        # 洪水填充：只走「同為空白」的鄰接鏈
        comp = []
        dq = deque([start])
        seen.add(start)
        while dq:
            cur = dq.popleft()
            comp.append(cur)
            for nb in tri_neighbors(cur):
                if nb in blanks and nb not in seen:
                    seen.add(nb)
                    dq.append(nb)
        # 判型：這片空白的成員若有鄰居在窗口**外**，就是「缺口」
        # （連通窗口邊緣）；否則是被單元包圍的「孔洞」。
        touches_edge = False
        for cur in comp:
            for nb in tri_neighbors(cur):
                if nb not in goal:
                    touches_edge = True
                    break
            if touches_edge:
                break
        holes.append({
            'cells': sorted(comp),
            'type': 'gap' if touches_edge else 'hole',
            'size': _size_of(comp, step),
        })
    return holes, protrusions


def _size_of(comp, step):
    """洞的大小分檔：與方形同口徑——大洞能吃下 step×step 目標區塊。"""
    # 三角形沒有正方形那套「行×列」的尺寸，用單元數 + 步長折算：
    # 方形的「大」= 面積 ≥ step²。這裡用「邊長 ≥ step」近似——
    # 對三角形，邊長 step 的大三角含 step(step+1)/2 個單元。
    need = step * (step + 1) // 2 if step > 1 else 1
    return HOLE_LARGE if len(comp) >= need else HOLE_SMALL
