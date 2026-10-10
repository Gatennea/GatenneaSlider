# -*- coding: utf-8 -*-
"""方形求解器的不變量工具：行列剖面、剖面缺陷(Φ)、位置無關還原判定。

這些函數直接吃 coords（(r,c) 可迭代），位置無關，不依賴遊戲物件。
命名與性質參見 `求解器優化發現.md` §七。

- 行列剖面：行計數向量（第幾行有幾格）、列計數向量（第幾列有幾格）。
- 剖面缺陷 Φ：把兩個向量的 L1 偏差加總成的單一標量（數值）；Φ=0（＋連通）⟺ 還原。
- is_solved_by_profile：位置無關、直接吃 coords 的嚴格還原判定，與「實心矩形」等價。
"""

from solver.table_core import is_single_connected


def profile_defect(coords, m, n):
    """行列剖面缺陷 Φ：越小越接近還原（0 = 已還原），含轉置取優。

    量的是「每行/每列實際格數」與「還原時均勻格數」的偏差總和（L1）。
    中間量「行列剖面」是行計數向量與列計數向量；Φ 把兩者的 L1 偏差加總成單一標量。
    有上界 O(K)（K = m*n），正常打亂下遠小於極端。
    """
    rows = {}
    cols = {}
    for r, c in coords:
        rows[r] = rows.get(r, 0) + 1
        cols[c] = cols.get(c, 0) + 1

    def defect(row_vals, n_rows, per_row, col_vals, n_cols, per_col):
        R = sorted(row_vals, reverse=True)
        C = sorted(col_vals, reverse=True)
        if len(R) < n_rows:
            R = R + [0] * (n_rows - len(R))
        dr = sum(abs(R[i] - per_row) for i in range(n_rows))
        dr += sum(R[n_rows:])
        if len(C) < n_cols:
            C = C + [0] * (n_cols - len(C))
        dc = sum(abs(C[i] - per_col) for i in range(n_cols))
        dc += sum(C[n_cols:])
        return dr + dc

    if m == n:
        return defect(list(rows.values()), m, n, list(cols.values()), n, m)
    a = defect(list(rows.values()), m, n, list(cols.values()), n, m)
    b = defect(list(rows.values()), n, m, list(cols.values()), m, n)
    return min(a, b)


def _profile_ok(coords, rows_target, cols_target):
    """行恰好 rows_target 行、各行 cols_target 格；列恰好 cols_target 列、各列 rows_target 格
    （其餘行列皆空）。等價於「rows_target×cols_target 實心矩形」的位置無關判定。
    """
    rowcounts = {}
    colcounts = {}
    for r, c in coords:
        rowcounts[r] = rowcounts.get(r, 0) + 1
        colcounts[c] = colcounts.get(c, 0) + 1
    rs = sorted(rowcounts.values(), reverse=True)
    cs = sorted(colcounts.values(), reverse=True)
    if len(rs) < rows_target:
        rs = rs + [0] * (rows_target - len(rs))
    if len(cs) < cols_target:
        cs = cs + [0] * (cols_target - len(cs))
    if rs[:rows_target] != [cols_target] * rows_target:
        return False
    if any(v != 0 for v in rs[rows_target:]):
        return False
    if cs[:cols_target] != [rows_target] * cols_target:
        return False
    if any(v != 0 for v in cs[cols_target:]):
        return False
    return True


def is_solved_by_profile(coords, m, n, check_connected=True):
    """位置無關的還原判定（直接吃 coords，不需遊戲物件）。

    證明：行/列剖面均勻 ⟹ 恰好 m 個不同行各 n 格、n 個不同列各 m 格 ⟹
    bounding box 恰 m×n 且被 mn 格填滿 ⟹ 實心矩形（連通自動成立）。
    含轉置：m×n 與 n×m 兩朝向都放行。
    """
    total = m * n
    if len(coords) != total:
        return False
    if _profile_ok(coords, m, n) or _profile_ok(coords, n, m):
        if check_connected:
            return is_single_connected(coords)
        return True
    return False
