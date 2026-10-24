# -*- coding: utf-8 -*-
"""選中縫必須**貫穿整個畫面**（與方形同一套視覺語言）。

背景：方形原版把選中縫畫成貫穿整個視窗的直線（`(0,y)-(W,y)`），而三角/
米字/通用多邊形通道各自把線裁剪到棋形範圍內——同一個交互在三種形態下
長得完全不一樣，用戶 2026-10-24 指出「縫隙沒有貫穿整個地圖」。

本測試的判據是**像素級**的：渲染一幀後，螢幕四條邊上必須能數到縫線顏色的
像素。裁剪到棋形的舊實現一定過不了（線根本到不了邊緣）。

跑法：``PYTHONPATH=. python -u test/_test_seam_fullscreen.py``
"""
import os
import queue
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

_FAILS = []


def check(cond, label, extra=''):
    tag = 'OK  ' if cond else 'FAIL'
    print(f'[{tag}] {label}' + (f'  （{extra}）' if extra else ''))
    if not cond:
        _FAILS.append(label)


def _is_seam_color(c):
    # colors['line'] = (255,0,0)；抗鋸齒會混出偏暗的紅，放寬下限
    return c.r > 170 and c.g < 100 and c.b < 100


def edge_seam_pixels(screen):
    """螢幕四條邊上的縫線色像素數（按邊分別返回）。"""
    w, h = screen.get_size()
    top = sum(1 for x in range(w) if _is_seam_color(screen.get_at((x, 0))))
    bottom = sum(1 for x in range(w) if _is_seam_color(screen.get_at((x, h - 1))))
    left = sum(1 for y in range(h) if _is_seam_color(screen.get_at((0, y))))
    right = sum(1 for y in range(h) if _is_seam_color(screen.get_at((w - 1, y))))
    return {'top': top, 'bottom': bottom, 'left': left, 'right': right}


def _gui():
    g = SliderGUI(m=6, n=6, step=2, cmd_queue=queue.Queue(),
                  ext_state={'enabled': True, 'token': 'T', 'port': 5050})
    g.tut_show_prompt = False
    g.tutorial_active = False
    g.animation_enabled = False
    return g


def check_boards(tag, setup, gaps_pick):
    """對每個 (族, 縫號) **先建局**再渲染，斷言至少一條螢幕邊上有縫線色。

    ⚠️ 必須顯式 setup：SliderGUI 構造時會從 config/temp_history.json 恢復
    上次局面，不建局就會拿到別的形態（曾因此讓碎三角的用例「假通過」）。
    """
    for gap_type, line in gaps_pick:
        g = _gui()
        setup(g)
        g.selected_gap = (gap_type, line)
        g.draw_board()
        e = edge_seam_pixels(g.screen)
        total = e['top'] + e['bottom'] + e['left'] + e['right']
        check(total > 0, f'{tag} 縫 {gap_type}:{line} 貫穿到畫面邊緣',
              f'邊上紅像素 {e}')


def main():
    # ---- 三角形：三族各挑一條 ----
    g = _gui()
    g.new_triangle_puzzle(6, 2)
    all_gaps = list(g.game.all_gaps())
    tri = []
    for fam in ('h', 'p', 'n'):
        cand = [x for x in all_gaps if x[0] == fam]
        if cand:
            tri.append(cand[len(cand) // 2])
    check(len(tri) == 3, f'三角形三族都拿到縫（{tri}）')
    check_boards('三角', lambda g: g.new_triangle_puzzle(6, 2), tri)

    # ---- 米字：四族各挑一條 ----
    g = _gui()
    g.new_mi_puzzle(4, 4, 2)
    all_gaps = list(g.game.all_gaps())
    mi = []
    for fam in ('h', 'v', 'd1', 'd2'):
        cand = [x for x in all_gaps if x[0] == fam]
        if cand:
            mi.append(cand[len(cand) // 2])
    check(len(mi) == 4, f'米字四族都拿到縫（{mi}）')
    check_boards('米字', lambda g: g.new_mi_puzzle(4, 4, 2), mi)

    # ---- 碎三角（通用多邊形通道）：六族裡有縫的都測 ----
    g = _gui()
    g.new_shatter_puzzle(1)
    all_gaps = list(g.game.all_gaps())
    sh = []
    for fam in ('h', 'd30', 'd60', 'v', 'd120', 'd150'):
        cand = [x for x in all_gaps if x[0] == fam]
        if cand:
            sh.append(cand[0])
    check(len(sh) >= 4, f'碎三角拿到多族的縫（{len(sh)} 條：{sh}）')
    check_boards('碎三角', lambda g: g.new_shatter_puzzle(1), sh)

    # ---- 方形（舊手畫路徑）：本來就貫穿，作對照 ----
    # SliderMatrix 沒有 all_gaps；6×6 的內部縫號是 h 0..4 / v 0..4
    for gap_type, line in (('h', 2), ('v', 2)):
        g = _gui()
        g.new_puzzle(6, 6, 2)
        g.selected_gap = (gap_type, line)
        g.draw_board()
        e = edge_seam_pixels(g.screen)
        total = e['top'] + e['bottom'] + e['left'] + e['right']
        check(total > 0, f'方形 縫 {gap_type}:{line} 貫穿到畫面邊緣（對照）',
              f'邊上紅像素 {e}')

    # ---- 未選中任何縫時，邊上不該有紅（防止「一直紅著」的假通過）----
    g = _gui()
    g.new_triangle_puzzle(6, 2)
    g.selected_gap = None
    g.draw_board()
    e = edge_seam_pixels(g.screen)
    check(sum(e.values()) == 0, '未選中縫時畫面邊緣沒有紅線', f'{e}')

    print()
    if _FAILS:
        print(f'失敗 {len(_FAILS)} 項：')
        for x in _FAILS:
            print('  -', x)
        return 1
    print('全部通過')
    return 0


if __name__ == '__main__':
    sys.exit(main())
