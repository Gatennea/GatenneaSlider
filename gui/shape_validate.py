# -*- coding: utf-8 -*-
"""三形態構造校驗：塊數／單連通／類計數＋偏移掃描／空位。

計劃二 A 的產出：把「這個棋形合不合法、要還原到哪」變成一條可單測的
純邏輯，供計劃二 B（手動構造畫布）接線。方形也一併切到偏移掃描版本
（現行判據的超集，見計劃 §4 決策點）：原本通過的一定還通過，只是
「整體平移過、而 step 不整除 m/n」的合法棋形不再被冤拒。
`solver.ml.ann_gen.validate_state` 保留給 ML 生成器自用，本模組不碰。

核心不變量（見 gui/cell_class.py）：一次合法移動把整組滑塊平移一個
向量，該向量是方向生成元的 step 倍，所以每塊的類永遠不變。還原態有
一張固定的類計數表；構造出來的棋形必須在**某個偏移**下與它逐類相等
（三角/米字的表非均勻，所以掃偏移、≤ step² 次），掃到的那個偏移就是
anchor（目標框位置，計劃二 B 用它畫框；三角/米字沒有求解器算框）。

類計數用「類含朝向」（三角 +up、米字 +q）：朝向是平移不變量，也是
不變量的一部分。若只按位置類計數，「挖 ▲、補 ▼」（位置類相同、朝向
翻轉）的構造會被誤判合法——它改變了 ▲/▼ 各自的塊數，還原態裡兩者
不能互相代替。方形無朝向，維持位置類。

anchor 的含義：匹配的偏移 (dr, dc) ∈ [0, step)²——還原態整體平移
(dr, dc) 後，類計數表與構造態一致。整體平移 step 的整數倍時類不變，
所以 anchor 是平移向量的 mod step 類；三角/米字的表非均勻，anchor 幾乎
唯一；方形表均勻時 anchor 只代表其中一個可行偏移，不具方向性。
"""
from collections import Counter

from game import SliderMatrix
from game_mi import MiSliderMatrix, blocks_from_cells as mi_blocks_from_cells
from game_mi import any_overlap as mi_any_overlap, lattice_of as mi_lattice_of
from game_triangle import TriangleSliderMatrix, blocks_from_cells as tri_blocks_from_cells
from gui.cell_class import cell_class

__all__ = ['validate_shape', 'solved_cell_count']


def solved_cell_count(kind, params) -> int:
    """還原態塊數：方形 m*n、三角 k*k、米字 4*m*n。"""
    if kind == 'square':
        m, n = params
        return m * n
    if kind == 'triangle':
        return params[0] * params[0]
    m, n = params
    return 4 * m * n


def _solved_positions(kind, params) -> set:
    """還原態（錨定原點）的完整位置集合（含朝向分量）。"""
    if kind == 'square':
        m, n = params
        return {(r, c) for r in range(m) for c in range(n)}
    if kind == 'triangle':
        k = params[0]
        cells = {(i, j, True) for i in range(k) for j in range(k - i)}
        cells |= {(i, j, False) for i in range(k - 1) for j in range(k - 1 - i)}
        return cells
    m, n = params
    return {(r, c, q) for r in range(m) for c in range(n)
            for q in ('N', 'E', 'S', 'W')}


def _class_counts(positions, step, kind, dr=0, dc=0) -> Counter:
    """位置集合在偏移 (dr, dc) 下的類計數表（含朝向）。

    三角/米字把朝向併入類鍵（up / q 是平移不變量，見 cell_class.py 的
    「類（含朝向）」）——否則「挖 ▲ 補 ▼」這類朝向翻轉的構造會被誤判
    合法。方形無朝向，維持位置類。"""
    if kind == 'triangle':
        return Counter(cell_class((p[0] + dr, p[1] + dc), step, kind) + (p[2],)
                       for p in positions)
    if kind == 'mi':
        return Counter(cell_class((p[0] + dr, p[1] + dc), step, kind) + (p[2],)
                       for p in positions)
    return Counter(cell_class((p[0] + dr, p[1] + dc), step, kind)
                   for p in positions)


def _match_anchor(kind, cells, params, step):
    """偏移掃描：找偏移使構造態與還原態逐類相等。

    **米字格的偏移域必須含半格**（2026-10-03 修）。米字有A/B兩層晶格
    （整數座標 / 半整數座標），錯位態就是整盤換到B 層。舊版只在
    [0,step)² 的整數格裡掃，而 B 層的類鍵與 A 層**完全不同**
    （step=2 實測：A 層落在(0,0)/(1,1)，B 層落在 (0,1)/(1,0)），
    偏移 (0.5,0.5) 永遠掃不到 → 所有錯位態構造全被冤拒成
    「不變量類計數與還原態不一致」。

    方形與三角沒有雙層晶格，偏移域不變（仍是 step² 次）。
    """
    solved = _solved_positions(kind, params)
    target = _class_counts(cells, step, kind)
    domain = _anchor_domain(kind, step)
    for dr, dc in domain:
        if _class_counts(solved, step, kind, dr, dc) == target:
            return (dr, dc)
    return None


def _anchor_domain(kind, step):
    """偏移掃描域。米字含半格（雙層晶格），其餘為整數格 [0,step)²。"""
    if kind != 'mi':
        return [(dr, dc) for dr in range(step) for dc in range(step)]
    half = [v / 2 for v in range(2 * step)]
    return [(dr, dc) for dr in half for dc in half]


def _square_is_solved(cells, m, n) -> bool:
    """方形：佔用格構成實心 m×n 或 n×m 矩形（與 SliderMatrix.is_solved 同判據）。"""
    if not cells:
        return False
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    height = max(rs) - min(rs) + 1
    width = max(cs) - min(cs) + 1
    if not ((height == m and width == n) or (height == n and width == m)):
        return False
    return len(cells) == height * width


def _is_solved_shape(kind, cells, params) -> bool:
    """是否已構成完整還原態（無空位）：是 → 構造出來的題目至少要有洞/凸起。

    直接借各形態引擎自己的 is_solved（三角凸包、米字每格 4 塊實心矩形），
    透過 blocks_from_cells 把位置集合塞進臨時實例——同時驗證了重建函數
    與 update_matrix 能吃下構造態。
    """
    if kind == 'square':
        return _square_is_solved(cells, params[0], params[1])
    if kind == 'triangle':
        tmp = TriangleSliderMatrix(params[0])
        tmp.blocks = tri_blocks_from_cells(cells)
        tmp.update_matrix()
        return tmp.is_solved()
    m, n = params
    tmp = MiSliderMatrix(m, n)
    tmp.blocks = mi_blocks_from_cells(cells)
    tmp.update_matrix()
    return tmp.is_solved()


def validate_shape(kind, cells, params, step):
    """三形態構造校驗。

    kind：'square' / 'triangle' / 'mi'。
    cells：位置集合（方形 (r,c)、三角 (i,j,up)、米字 (r,c,q)）。
    params：方形與米字 (m, n)、三角 (k,)。
    step：等級。

    判據（依序）：塊數 == 還原態塊數；單連通（三角/米字用各自 game 的
    is_single_connected，方形沿用既有判據）；類計數表在**某個偏移**下
    等於還原態的表（anchor 回傳匹配的偏移）；至少一個空位（塊數相同但
    有洞/凸起才算構造出來的題目）。

    返回 (ok, msg, anchor)：anchor 為匹配的偏移 (dr, dc)，失敗時 None。
    """
    if not cells:
        return False, '空狀態', None
    # 跨晶格正面積重疊閘門（2026-10-03 補）。**必須排在塊數判據之前**：
    # 重疊局面本身就是非法構造，用戶要看到的訊息是「重疊」而不是「塊數不對」
    # ——後者會把真正的原因藏起來，且塊數不對的狀況滿地都是、單獨報錯就夠。
    #
    # 米字錯位態下兩塊位置 key 不同卻可以疊在一起（game_mi._tri_overlap /
    # 規劃 §1.5），「位置集合相交」擋不住。引擎只在移動期查跨層重疊
    # （_has_overlap），創造模式能直接擺出這種局面——不補這道閘門就能
    # 構造出遊戲裡根本走不出來的死盤，直接違反「所有合法局面都該由合法
    # 移動到達」的設計哲學。
    if kind == 'mi' and mi_any_overlap(cells):
        return False, '有重疊的滑塊（跨晶格錯位重疊，遊戲中走不出來）', None
    n_expected = solved_cell_count(kind, params)
    if len(cells) != n_expected:
        return False, f'滑塊數 {len(cells)} != {n_expected}', None
    if kind == 'square':
        conn = SliderMatrix.is_single_connected(cells)
    elif kind == 'triangle':
        conn = TriangleSliderMatrix.is_single_connected(cells)
    else:
        conn = MiSliderMatrix.is_single_connected(cells)
    if not conn:
        return False, '不是單一連通分量', None
    anchor = _match_anchor(kind, cells, params, step)
    if anchor is None:
        return False, '不變量類計數與還原態不一致', None
    if _is_solved_shape(kind, cells, params):
        return False, '無空位（就是還原態本身）', None
    return True, 'ok', anchor
