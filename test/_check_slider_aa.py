# -*- coding: utf-8 -*-
"""验收：三角/米字滑块在小缩放下启用 SSAA 抗锯齿（_draw_aa_polygon）。

背景：米字/三角滑块是三角形，缩得较小时斜边切割像素出现明显阶梯锯齿；
方形是轴对齐边无此问题。本精简版 pygame 无 gfxdraw，故用局部超采样
（S 倍大面硬边绘制 → smoothscale 缩回，边界与透明混合成半透明边）。

两部分：
  1) 单元：_draw_aa_polygon 画一个倾斜三角后，边缘应出现「过渡色」像素
     （既非填充也非背景也非描边）——这是抗锯齿生效的签名；同形状硬边
     draw.polygon 作对照，应无过渡色。
  2) 集成：小 zoom（cell<阈值）渲染米字/三角各一帧，无异常且屏幕有内容。

执行：python test/_check_slider_aa.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402


def _dist(c1, c2):
    return (abs(c1[0] - c2[0]) + abs(c1[1] - c2[1]) + abs(c1[2] - c2[2]))


def _count_transition(gui, box, fill, bg, black=(0, 0, 0), thr=12):
    """统计 box 区域内「既非 fill 也非 bg 也非 black」的过渡像素数。"""
    x0, y0, x1, y1 = box
    n = 0
    for yy in range(max(0, y0), min(gui.screen.get_height(), y1)):
        for xx in range(max(0, x0), min(gui.screen.get_width(), x1)):
            c = gui.screen.get_at((xx, yy))[:3]
            if _dist(c, fill) > thr and _dist(c, bg) > thr and _dist(c, black) > thr:
                n += 1
    return n


def test_unit():
    gui = SliderGUI()
    gui.animation_enabled = False
    bg = gui.colors['background']
    fill = (200, 60, 60)
    border = (0, 0, 0)
    tri = [(100, 100), (260, 140), (140, 260)]   # 明显斜边
    box = (90, 90, 275, 275)
    fails = []

    # AA 版：应出现过渡像素
    gui.screen.fill(bg)
    gui._draw_aa_polygon(tri, fill, border, 2)
    aa_n = _count_transition(gui, box, fill, bg)
    if aa_n <= 0:
        fails.append(f'AA 版无过渡像素（抗锯齿未生效）: {aa_n}')

    # 硬边对照：同形状同色，应无过渡像素
    gui.screen.fill(bg)
    pygame.draw.polygon(gui.screen, fill, tri)
    pygame.draw.polygon(gui.screen, border, tri, 2)
    hard_n = _count_transition(gui, box, fill, bg)
    if hard_n > aa_n:
        fails.append(f'硬边过渡像素反多于 AA: hard={hard_n} aa={aa_n}')

    # 轮廓中心不变：AA 只平滑边缘，不平移图形
    # （质心近似：AA 前后填充像素的平均位置应接近）
    def _centroid(g):
        sx = sy = cnt = 0
        for yy in range(box[1], box[3]):
            for xx in range(box[0], box[2]):
                if _dist(g.screen.get_at((xx, yy))[:3], fill) < 40:
                    sx += xx
                    sy += yy
                    cnt += 1
        return (sx / max(cnt, 1), sy / max(cnt, 1), cnt)
    gui.screen.fill(bg)
    gui._draw_aa_polygon(tri, fill, None, 0)
    cxa, cya, na = _centroid(gui)
    gui.screen.fill(bg)
    pygame.draw.polygon(gui.screen, fill, tri)
    cxh, cyh, nh = _centroid(gui)
    if abs(cxa - cxh) > 2 or abs(cya - cyh) > 2:
        fails.append(f'AA 平移了图形: aa=({cxa:.1f},{cya:.1f}) hard=({cxh:.1f},{cyh:.1f})')

    if fails:
        print('单元测试 FAIL:')
        for f in fails:
            print('  -', f)
        return False
    print(f'单元测试 OK（AA 过渡像素 {aa_n} 个 / 硬边 {hard_n} 个，'
          f'质心偏移 {abs(cxa - cxh):.2f},{abs(cya - cyh):.2f}px）')
    return True


def test_integration():
    fails = []
    bg_default = None
    for name, newf in (('mi', lambda g: g.new_mi_puzzle(6, 6, 2)),
                       ('tri', lambda g: g.new_triangle_puzzle(6, 6))):
        gui = SliderGUI()
        gui.animation_enabled = False
        newf(gui)
        gui.zoom = 0.22          # cell≈13 < 18 → 触发 AA
        try:
            gui.draw_board()
        except Exception as e:   # noqa: BLE001
            fails.append(f'{name} draw_board 抛异常: {e!r}')
            continue
        cell = gui.cell_size * gui.zoom
        if not gui._slider_aa_on(cell):
            fails.append(f'{name} AA 未按预期开启: cell={cell}')
        # 屏幕应有内容（非纯背景）
        bg_default = gui.colors['background']
        non_bg = 0
        for yy in range(0, gui.screen.get_height(), 7):
            for xx in range(0, gui.screen.get_width(), 7):
                if gui.screen.get_at((xx, yy))[:3] != bg_default[:3]:
                    non_bg += 1
        if non_bg == 0:
            fails.append(f'{name} 渲染后屏幕无内容')
    if fails:
        print('集成测试 FAIL:')
        for f in fails:
            print('  -', f)
        return False
    print('集成渲染 OK（米字/三角小 zoom 走 SSAA 无异常）')
    return True


if __name__ == '__main__':
    ok1 = test_unit()
    ok2 = test_integration()
    print('===== 結論 =====')
    print('OK：滑块 SSAA 抗锯齿生效且三形态渲染无异常' if (ok1 and ok2)
          else 'FAIL：见上方')
    sys.exit(0 if (ok1 and ok2) else 1)
