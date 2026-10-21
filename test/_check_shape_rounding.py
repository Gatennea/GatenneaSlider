# -*- coding: utf-8 -*-
"""验收：三角 / 米字滑塊圓角與方形統一。

兩部分：
  1) 單元：_rounded_polygon_points 的數學正確性（尖角被截進 radius 內、原頂點消失、
     退化保護）。不依賴顯示。
  2) 集成：三形態各渲染一幀（無異常即集成通過），並產出截圖供肉眼核對統一觀感。

執行：python test/_check_shape_rounding.py
"""

import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from gui.renderer import RendererMixin  # noqa: E402

TMP = 'C:/Users/guo/AppData/Local/Temp'


# ----------------------------------------------------------------- 單元測試
def _stub():
    # 繞過 __init__，只需 _rounded_polygon_points / _point_in_convex（皆只用 math）
    return RendererMixin.__new__(RendererMixin)


def _dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _min_dist_to_poly(pt, poly):
    return min(_dist(pt, p) for p in poly)


def test_unit():
    s = _stub()
    fails = []

    # 等邊三角形，頂點 (0,0)
    tri = [(0.0, 0.0), (100.0, 0.0), (50.0, 86.6)]
    R = 10
    out = s._rounded_polygon_points(tri, R)
    # 1. 角被細分 → 輸出點多於輸入
    if not (len(out) > len(tri)):
        fails.append(f'角未細分: in={len(tri)} out={len(out)}')
    # 2. 原尖角頂點不應出現在輸出（已被弧取代）
    if any(_dist((0, 0), p) < 1e-6 for p in out):
        fails.append('原尖角頂點仍出現在輸出')
    # 3. 尖角被截進合理範圍：最近輸出點（弧中段、落在角平分線上）距原頂點
    #    = 圓心距(R/sin30°=2R) − R = R = 10（60° 角）
    md = _min_dist_to_poly((0, 0), out)
    if not (8 < md <= 12):
        fails.append(f'等邊角截進異常: min_dist={md:.2f}')
    # 4. 所有輸出點仍在原三角形內（圓角多邊形是子集）
    for p in out:
        if not s._point_in_convex(p, tri):
            fails.append(f'輸出點跑到三角形外: {p}')
            break

    # 直角三角：90° 角，邊界最近原頂點處 = R·(√2−1) ≈ 4.14（與方形 border_radius 同幾何）
    rtri = [(0.0, 0.0), (100.0, 0.0), (0.0, 100.0)]
    r2 = s._rounded_polygon_points(rtri, R)
    md2 = _min_dist_to_poly((0, 0), r2)
    if not (3 < md2 <= 6):
        fails.append(f'直角角截進異常: min_dist={md2:.2f}')

    # radius=0 → 原樣返回
    same = s._rounded_polygon_points(tri, 0)
    if same != [tuple(p) for p in tri]:
        fails.append('radius=0 未原樣返回')

    # 退化：少於 3 點
    if s._rounded_polygon_points([(0, 0), (1, 1)], 5) != [(0, 0), (1, 1)]:
        fails.append('2 點退化未原樣返回')

    if fails:
        print('單元測試 FAIL:')
        for f in fails:
            print('  -', f)
        return False
    print(f'單元測試 OK（等邊角截進 {md:.1f}px / 直角角截進 {md2:.1f}px，'
          f'輸出 {len(out)} 點，原尖角已消失）')
    return True


# ----------------------------------------------------------------- 集成 + 截圖
def test_render():
    import pygame
    from GUI import SliderGUI

    ok = True
    shots = []

    def snap(gui, name):
        gui.draw_board()
        out = os.path.join(TMP, name)
        pygame.image.save(gui.screen, out)
        shots.append(out)

    try:
        # 方形
        g = SliderGUI(m=6, n=6, step=1)
        g.animation_enabled = False
        g.new_puzzle(6, 6, 1)
        snap(g, '_rounding_sq.png')
        print('方形渲染 OK')

        # 三角
        g = SliderGUI()
        g.animation_enabled = False
        g.new_triangle_puzzle(6, 2)
        if hasattr(g, '_fit_triangle_zoom'):
            g._fit_triangle_zoom()
        if hasattr(g, '_center_triangle'):
            g._center_triangle()
        snap(g, '_rounding_tri.png')
        print('三角渲染 OK')

        # 米字
        g = SliderGUI(m=6, n=6, step=2)
        g.animation_enabled = False
        g.new_mi_puzzle(6, 6, 2)
        if hasattr(g, '_fit_mi_zoom'):
            g._fit_mi_zoom()
        if hasattr(g, '_center_mi'):
            g._center_mi()
        snap(g, '_rounding_mi.png')
        print('米字渲染 OK')
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        ok = False

    return ok, shots


if __name__ == '__main__':
    u = test_unit()
    r, shots = test_render()
    print('\n===== 結論 =====')
    print(f'單元 {"OK" if u else "FAIL"} / 集成渲染 {"OK" if r else "FAIL"}')
    if r:
        print('截圖：')
        for s in shots:
            print('  ', s)
    sys.exit(0 if (u and r) else 1)
