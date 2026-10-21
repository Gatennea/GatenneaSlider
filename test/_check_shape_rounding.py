# -*- coding: utf-8 -*-
"""验收：三角 / 米字滑塊圓角與方形統一（削進深度對齊，而非弧半徑字面相等）。

兩部分：
  1) 單元：_rounded_polygon_points 的數學正確性。關鍵：傳入「削進深度 depth」後，
     任意頂角（60° / 90°）被削進的深度都 == depth；而方形 border_radius=R 的削進
     深度恰為 R·(√2−1)，故三形態視覺削進一致（舊寫法同檔 R 會把 60° 角削進 R·1.73，
     約 4 倍，即「圓得過頭」）。含退化保護。不依賴顯示。
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


def _circum_radius(a, b, c):
    """三點外接圓半徑（用於從採樣弧點反推圓角弧半徑 r_eff）。"""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy)
          + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx)
          + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    return math.hypot(ax - ux, ay - uy)


def test_unit():
    s = _stub()
    fails = []

    zoom = 2.0
    sq_R = int(round(5 * zoom))                 # 方形 border_radius（像素）
    sq_cut = sq_R * (math.sqrt(2) - 1)          # 方形角頂實際削進深度（pygame 幾何）
    depth = max(1, int(round(sq_R * (math.sqrt(2) - 1))))

    # 三形態統一前提：三角/米字削進深度 = 方形削進深度
    if abs(depth - round(sq_cut)) > 1:
        fails.append(f'depth 與方形削進不符: depth={depth} sq_cut={sq_cut:.2f}')

    # 等邊三角形，頂點 (0,0)
    tri = [(0.0, 0.0), (100.0, 0.0), (50.0, 86.6)]
    out = s._rounded_polygon_points(tri, depth)
    # 1. 角被細分 → 輸出點多於輸入
    if not (len(out) > len(tri)):
        fails.append(f'角未細分: in={len(tri)} out={len(out)}')
    # 2. 原尖角頂點不應出現在輸出（已被弧取代）
    if any(_dist((0, 0), p) < 1e-6 for p in out):
        fails.append('原尖角頂點仍出現在輸出')
    # 3. 從採樣弧點反推圓角弧半徑 r_eff，應等於 depth/(1/sin(θ/2)−1)
    def _expected_r(theta_deg, d):
        h = math.radians(theta_deg) / 2.0
        return d / (1.0 / math.sin(h) - 1.0)

    # 等邊 60°：取角頂附近 3 個弧內點擬合外接圓半徑
    exp_r60 = _expected_r(60, depth)
    r_eff60 = _circum_radius(out[1], out[2], out[3])
    if r_eff60 is None or not (0.8 * exp_r60 <= r_eff60 <= 1.2 * exp_r60):
        fails.append(f'等邊角弧半徑不符: r_eff={r_eff60} 期望≈{exp_r60:.2f}')
    # 4. 所有輸出點仍在原三角形內（圓角多邊形是子集）
    for p in out:
        if not s._point_in_convex(p, tri):
            fails.append(f'輸出點跑到三角形外: {p}')
            break

    # 直角 90° 角：弧半徑也應等於對應預期（新語義下任意內角按 depth 反推一致）
    rtri = [(0.0, 0.0), (100.0, 0.0), (0.0, 100.0)]
    r2 = s._rounded_polygon_points(rtri, depth)
    exp_r90 = _expected_r(90, depth)
    r_eff90 = _circum_radius(r2[1], r2[2], r2[3])
    if r_eff90 is None or not (0.8 * exp_r90 <= r_eff90 <= 1.2 * exp_r90):
        fails.append(f'直角角弧半徑不符: r_eff={r_eff90} 期望≈{exp_r90:.2f}')

    # 關鍵回歸：新寫法確實「收小」了三角圓角——
    # 舊寫法若把方形同檔半徑 sq_R 直接給 60° 角，r_eff = sq_R（約 {sq_R}px），
    # 是新寫法 exp_r60≈{exp_r60:.1f}px 的 {sq_R/exp_r60:.1f} 倍。故新 r_eff 必須顯著小於 sq_R。
    if not (r_eff60 < 0.6 * sq_R):
        fails.append(f'圓角未收小（仍過圓）: r_eff60={r_eff60:.2f} sq_R={sq_R}')

    # depth=0 → 原樣返回
    same = s._rounded_polygon_points(tri, 0)
    if same != [tuple(p) for p in tri]:
        fails.append('depth=0 未原樣返回')

    # 退化：少於 3 點
    if s._rounded_polygon_points([(0, 0), (1, 1)], 5) != [(0, 0), (1, 1)]:
        fails.append('2 點退化未原樣返回')

    if fails:
        print('單元測試 FAIL:')
        for f in fails:
            print('  -', f)
        return False
    print(f'單元測試 OK（depth={depth}px：等邊角弧半徑 {r_eff60:.1f}≈期望{exp_r60:.1f}px / '
          f'直角角 {r_eff90:.1f}≈期望{exp_r90:.1f}px，均 == 方形削進 {sq_cut:.1f}px 對應；'
          f'舊寫法 60° 會用 r_eff={sq_R}px≈{sq_R / exp_r60:.1f} 倍，已收小）')
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
