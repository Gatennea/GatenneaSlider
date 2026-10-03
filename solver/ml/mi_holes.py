# -*- coding: utf-8 -*-
"""米字格「洞 / 凸起」检测（M3 F2 面板用，計劃 §4/§6）。

方形版 `hole_detector.detect_holes` 是**矩形网格**上的洪水填充。mi 的
窗口恰好也是矩形（m×n 棋盘轮廓），所以框架能搬，但**邻接关系必须换成
mi 自己的**：

  · 方形單元是一格，窗口 = 矩形，洪水填充走 4-邻接；
  · mi 單元是四分之一格 `(r, c, q)`，窗口 = m×n 棋盘輪廓，共 4mn 片。
    **鄰接有 5 條**（3 條同晶格 + 2 條跨晶格，`game_mi.neighbors`），
    而窗口內的片全部同屬一個晶格檔 —— 所以窗口內的洪水填充只用得上
    **同晶格 3 條**；跨晶格那 2 條會把片連到窗口外的另一檔，會讓
    「缺口」判定全錯。

因此本模組的洪水填充明確走 `game_mi._SAME_NEIGHBORS` 的那 3 條同晶格
鄰接（經 `neighbors` 過濾掉跨晶格項），邊緣判定用同一套。

記號語義（沿用方形與 tri 版，便于對照）：
    目標窗口內、被單元包圍的空白（孔洞）  = 圓圈
    目標窗口內、連通窗口邊緣的空白（缺口）= 三角形
    目標窗口外的單元（凸起）              = 菱形
顏色：大 = 紅、小 = 藍；凸起 = 黃（與方形/tri 一致）。

**與 tri 版最大的差别**：mi 的「空白片」不再是整格，而是四分之一格。
一格缺 1 片与缺 3 片是不同大小的洞，而且缺的片可能构成**不連通**的
洞（同格内 N/S 相对的两片不共边）。所以洞的大小分档要按**片数**算，
不能用 tri 的「边长」口径。
"""
from collections import deque

from game_mi import neighbors as mi_neighbors, sublattice_of

__all__ = ['in_goal', 'detect_mi_holes', 'hole_color', 'HOLE_LARGE',
           'HOLE_SMALL', 'PROTRUSION_COLOR']

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
    """單元是否在目標形狀內。`goal` 是 `(r, c, q)` 的集合。

    mi 版同樣是查集合：窗口就是輪廓本身（`goal_cells()`），沒有任何
    「範圍比較」的機會。分檔（每格是否四塊俱全）留給 `detect_mi_holes`。
    """
    return cell in goal


def _same_lattice_neighbors(key):
    """窗口內可用的鄰接：3 條同晶格邊相鄰。

    **為什麼濾掉跨晶格那 2 條**：它們是「斜滑一格後兩半唯一的通道」，
    連到的是另一晶格檔的片。目標窗口整片同屬一個晶格檔（A 或 B），
    跨晶格鄰接在窗口內永遠落空 → 用它做洪水填充會漏掉同晶格相鄰的空白，
    用它做邊緣判定會讓每個洞都變成「缺口」（每片都有鄰居在窗口外）。
    """
    return tuple(nb for nb in mi_neighbors(key)
                 if sublattice_of(nb) == sublattice_of(key))


def detect_mi_holes(coords, goal, step=1):
    """檢測目標窗口內的洞 + 凸起。

    參數
    ----
    coords : iterable
        當前單元集 `(r, c, q)`（r/c 可為半整數）。
    goal   : iterable
        目標形狀單元集（**已經帶好放置偏移**，即 `MiPlacement.cells`）。
        這一點是計劃 §4「面板與求解器同源」的落點：傳進來的必須是
        `best_placement(...).cells`，不是自己另算一份。
    step   : int
        等級，**只影響洞的大小分檔**（與方形/tri 同語義）。
        不影響「是不是洞」的判定。

    返回 ``(holes, protrusions)``：
        holes        : [{cells, type, size, cells_geo}]，
                       `type` ∈ {'hole','gap'}，`size` ∈ {'large','small'}。
                       `cells_geo` = 這片空白覆蓋的**幾何格**（去重後的
                       `(floor(r), floor(c))`），供 GUI 畫格級記號用 ——
                       面板不需要知道缺的是哪一片，只知道缺了哪幾格。
        protrusions  : 目標形狀外的單元列表（保持輸入順序）。
    """
    cells = frozenset(coords)
    goal = frozenset(goal)

    inside = {c for c in cells if c in goal}
    protrusions = [c for c in cells if c not in goal]

    blanks = goal - inside
    holes = []
    seen = set()
    for start in sorted(blanks):
        if start in seen:
            continue
        comp = []
        dq = deque([start])
        seen.add(start)
        while dq:
            cur = dq.popleft()
            comp.append(cur)
            for nb in _same_lattice_neighbors(cur):
                if nb in blanks and nb not in seen:
                    seen.add(nb)
                    dq.append(nb)
        # 判型：這片空白的成員若有鄰居在窗口**外**，就是「缺口」
        # （連通窗口邊緣）；否則是被單元包圍的「孔洞」。
        touches_edge = False
        for cur in comp:
            for nb in _same_lattice_neighbors(cur):
                if nb not in goal:
                    touches_edge = True
                    break
            if touches_edge:
                break
        holes.append({
            'cells': sorted(comp),
            'cells_geo': sorted({(int(r // 1), int(c // 1)) for r, c, _q in comp}),
            'type': 'gap' if touches_edge else 'hole',
            'size': _size_of(comp, step),
        })
    return holes, protrusions


def _size_of(comp, step):
    """洞的大小分檔：能吃下 step×step 目標區塊（按**片數**算）。

    mi 的一格是 4 片，所以 step×step 的格區 = 4·step² 片。方形與 tri
    都能用「邊長」折算，mi 沒有正方形的行列口徑，只能用片數 —— 但
    刻度是同一件事：大洞是那種「一步搬一整塊」能填上的。
    """
    need = 4 * step * step if step > 1 else 1
    return HOLE_LARGE if len(comp) >= need else HOLE_SMALL
