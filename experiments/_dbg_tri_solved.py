# -*- coding: utf-8 -*-
"""复现 _test_triangle_render 失败段：摆回目标大三角后 gui.is_solved() 不为 True"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
from GUI import SliderGUI
from game import Block

gui = SliderGUI()
gui.save_readonly_flag = False
gui.new_triangle_puzzle(6, 2)
print('initial gui.is_solved :', gui.is_solved())
gui.shuffle_puzzle()
print('after shuffle solved  :', gui.is_solved())
print('demo anchor after shuf:', getattr(gui, '_shuffle_demo_game', 'ABSENT'))
print('animating flag        :', getattr(gui, 'animating', 'ABSENT'))

gui.game.blocks = [Block(list(key)) for key in gui.game.goal_cells()]
print('--- blocks replaced by goal_cells ---')
print('positions == goal     :', set(gui.game.positions()) == gui.game.goal_cells())
print('n blocks              :', len(gui.game.blocks))
print('game.is_solved direct :', gui.game.is_solved())
print('gui.is_solved         :', gui.is_solved())

# 逐项排查 is_solved 内部
cells = gui.game.positions()
print('len(cells)            :', len(cells), ' k*k =', gui.game.k ** 2)
from game_triangle import tri_vertices, convex_hull, cells_inside_triangle
verts = set()
for key in cells:
    verts.update(tri_vertices(*key))
hull = convex_hull(verts)
print('hull size             :', len(hull))
target = gui.game.k * gui.game.k
ok_edges = True
for t in range(3):
    da = hull[(t + 1) % 3][0] - hull[t][0]
    db = hull[(t + 1) % 3][1] - hull[t][1]
    if da * da + da * db + db * db != target:
        ok_edges = False
        print('  edge', t, 'len2 =', da * da + da * db + db * db, 'want', target)
print('edges ok              :', ok_edges)
print('inside == cells       :', cells_inside_triangle(hull) == cells)
if cells_inside_triangle(hull) != cells:
    inside = cells_inside_triangle(hull)
    print('  only in inside:', sorted(inside - cells)[:5])
    print('  only in cells :', sorted(cells - inside)[:5])
pygame_quit = getattr(gui, 'quit', None)
import pygame
pygame.quit()
