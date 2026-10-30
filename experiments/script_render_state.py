# -*- coding: utf-8 -*-
"""渲染聚拢后卡住的硬形状（标注目标窗口/洞/凸起），供讨论双层共轭。"""
import sys

from experiments import harness as H


def render(m, n, step, seed):
    from solver.ml.gather_solver import gradient_gather
    from solver.ml.fill_macro import window_of
    g = H.load_game(H.gen_state(m, n, step, seed))
    r = gradient_gather(g, step)
    coords = H.coords_of(g)
    win, ov, holes, outside = window_of(coords, m, n, step)
    r0, c0, (rh, cw) = win
    region = {(r, c) for r in range(r0, r0 + rh)
              for c in range(c0, c0 + cw)}
    rs = [x[0] for x in coords] + [r0, r0 + rh - 1]
    cs = [x[1] for x in coords] + [c0, c0 + cw - 1]
    r0b, r1, c0b, c1 = min(rs), max(rs), min(cs), max(cs)
    print(f"seed={seed} 窗口=({r0},{c0},{rh}x{cw}) 重叠={ov}/{m*n} "
          f"洞={sorted(holes)} 凸起={sorted(outside)} solved={g.is_solved()}")
    for r_ in range(r0b, r1 + 1):
        line = ''
        for c_ in range(c0b, c1 + 1):
            p = (r_, c_)
            if p in coords:
                line += '*' if p in outside else '#'
            else:
                line += 'o' if p in holes else ('.' if p in region else ' ')
        print('  ' + line)
    print("  (# 窗口内块, o 窗口内洞, * 窗口外凸起)")


if __name__ == '__main__':
    m, n, step, seed = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    render(m, n, step, seed)
