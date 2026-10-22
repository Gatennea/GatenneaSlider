# -*- coding: utf-8 -*-
"""验收：三角形棋盤「圖像外單擊不應選中縫隙」。

對照方形/米字行為：
  - 方形 candidate_gaps 有矩形邊界守衛（board_view.py），
  - 米字 gap_at 只認棋盤內的單位邊（mi_view.py），
  二者都不會在棋盤圖像外選中縫隙。三角形原本缺這道守衛，
  只用「到無限長縫隙線的距離」判斷，空角裡單擊也會命中。

本測試直接驅動 TriangleBoardView.candidate_gaps：
  1) 取棋形凸包外、明顯在圖像外的世界座標點 → 必須回傳 []
  2) 取棋形內一條有效縫隙線段的中點 → 必須回傳至少一個候選
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_triangle import GAP_DIRECTIONS, gap_index_range
from GUI import SliderGUI


def main():
    g = SliderGUI()
    g.animation_enabled = False
    g.new_triangle_puzzle(6, 2)
    if hasattr(g, '_fit_triangle_zoom'):
        g._fit_triangle_zoom()
    if hasattr(g, '_center_triangle'):
        g._center_triangle()

    cells = g.game.positions()
    view = g._tri_view()
    hull = view.board_hull(cells)

    fails = []

    # ---- 1) 圖像外：棋形凸包包圍盒再往外推 40px ----
    xs = [p[0] for p in hull]
    ys = [p[1] for p in hull]
    ox = min(xs) - 40.0
    oy = min(ys) - 40.0
    out = view.candidate_gaps(ox, oy, cells)
    if out:
        fails.append(f'圖像外單擊仍選中縫隙: {out}')
    else:
        print(f'圖像外單擊 OK（點 ({ox:.0f},{oy:.0f}) 回傳 []）')

    # 再取另一個空角（包圍盒右下外）確認
    ox2, oy2 = max(xs) + 40.0, max(ys) + 40.0
    out2 = view.candidate_gaps(ox2, oy2, cells)
    if out2:
        fails.append(f'圖像外（另一角）仍選中縫隙: {out2}')
    else:
        print(f'圖像外單擊 OK（點 ({ox2:.0f},{oy2:.0f}) 回傳 []）')

    # ---- 2) 圖像內：一條有效縫隙線段中點 ----
    target = None
    for gt in GAP_DIRECTIONS:
        for line in gap_index_range(gt, cells):
            if not g.game.is_valid_gap(gt, line):
                continue
            seg = view.gap_line_segment(gt, line, hull)
            if seg:
                target = (gt, line, seg)
                break
        if target:
            break

    if target is None:
        fails.append('找不到任何有效縫隙線段（測試自身有誤）')
    else:
        (a, b) = target[2]
        mx = (a[0] + b[0]) / 2.0
        my = (a[1] + b[1]) / 2.0
        ins = view.candidate_gaps(mx, my, cells)
        if not ins:
            fails.append(f'圖像內縫隙線上單擊竟無候選: 線段 {target[0]},{target[1]}')
        else:
            print(f'圖像內縫隙單擊 OK（命中 {ins[0]} 等 {len(ins)} 個候選）')

    # ---- 結論 ----
    print('\n===== 結論 =====')
    if fails:
        print('FAIL:')
        for f in fails:
            print('  -', f)
        return 1
    print('OK：三角形棋盤圖像外單擊不再選中縫隙，圖像內縫隙選取不受影響。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
