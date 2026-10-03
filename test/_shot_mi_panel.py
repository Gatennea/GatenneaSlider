# -*- coding: utf-8 -*-
"""把米字格的**调试面板 + 目标框 + 洞/凸起记号**截圖存成 png 供人工验收。

執行：``D:/python/python.exe test/_shot_mi_panel.py``

導出（到 ``experiments/out/``）：
    mi_panel_solved.png   還原態：面板显示聚拢度 100%，框正好罩住整盘，无记號
    mi_panel_holes.png    打乱態：面板显示实际聚拢度，绿框是最佳放置，
                          圈=孔洞、三角=缺口、菱形=凸起
    mi_panel_panel.png    同上但只截右侧调试面板（看行内容）

这是 M3 F2 的**人工验收物料** —— 自动化测试只能验「像素有变化」，
「框罩得对不对、记号画在缺的那格上吗」得用眼睛。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'experiments', 'out')
os.makedirs(_OUT, exist_ok=True)


def shoot(gui, name, clip=None):
    path = os.path.join(_OUT, name)
    if clip:
        surf = pygame.Surface((clip[2], clip[3]))
        surf.blit(gui.screen, (0, 0), clip)
        pygame.image.save(surf, path)
    else:
        pygame.image.save(gui.screen, path)
    print(f'saved: {path}')


def render(gui, panel_xy=None):
    """画一帧完整画面：棋盘（含目标框与记号）+ 调试面板。

    踩过的坑（每条都让第一版截出「半截棋盘 + 无框无记号」）：

      · mi 的棋盘入口是 **`draw_mi_board()`**，不是 `draw_board()`；
      · 相机要用 mi 专用的 **`_fit_mi_zoom()` + `_center_mi()`** ——
        通用 `center_map()` 按方形包围盒算，mi 凸包不同，居中会偏；
      · 目标框与洞/记号是在棋盘绘制**内部**被调起的（renderer 里的
        `if show_metrics_panel:` 分支），而**面板本身**要单独调
        `draw_metrics_panel()` —— 只调前者会得到「有框无面板」，
        只调后者会得到「有面板但棋盘上没标记」；
      · 打乱之后要重新 `_fit_mi_zoom()`：建局时的 zoom 是按还原态定的，
        打乱后凸包变大，不重算就会截到出界。
    """
    gui.screen.fill((0, 0, 0))
    gui._fit_mi_zoom()
    gui._center_mi()
    gui.draw_mi_board()
    if panel_xy is not None:
        gui.mp_pos = list(panel_xy)
    gui.draw_metrics_panel()


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False
gui.show_metrics_panel = True

# ---------------------------------------------------------------- 還原態
gui.new_mi_puzzle(4, 4, 2)
best = gui._compute_target_region()
met = gui._mp_current_metrics()
print(f'還原態：score={met["score"]:.3f} overlap={met["overlap"]} '
      f'lattice={best.lattice} shape={best.shape} offset={best.offset}')
# 面板放右上：棋盘居中后左侧是棋盘，右上角空着
render(gui, panel_xy=(gui.screen_width - 200, 8))
shoot(gui, 'mi_panel_solved.png')

# ---------------------------------------------------------------- 打乱態
import random  # noqa: E402

random.seed(7)
gui.game.shuffle(40, 2)
best = gui._compute_target_region()
met = gui._mp_current_metrics()
from solver.ml.mi_adapter import mi_coords        # noqa: E402
from solver.ml.mi_holes import detect_mi_holes     # noqa: E402

holes, protr = detect_mi_holes(mi_coords(gui.game), best.cells, 2)
nh = sum(1 for h in holes if h['type'] == 'hole')
ng = sum(1 for h in holes if h['type'] == 'gap')
print(f'打乱態：score={met["score"]:.3f} overlap={met["overlap"]}/{4 * 4 * 4} '
      f'洞{nh} 缺{ng} 凸{len(protr)}')
for h in holes[:6]:
    print(f'   {h["type"]:4s} {h["size"]:5s} {len(h["cells"])}片 '
          f'格={h["cells_geo"]}')
render(gui, panel_xy=(gui.screen_width - 200, 8))
shoot(gui, 'mi_panel_holes.png')

# ---------------------------------------------------------------- 面板特写
# 用 **mp_panel_rect**（上一帧渲染时算出的真实矩形）而不是 `_mp_panel_size()`：
# 后者不给行数会退回 6 行，mi 的第 7 行（mod 约束）就被裁掉了 —— 我第一版
# 正是这么写的，截出来的图最后一行缺了一截还以为面板没画全。
x, y = gui.mp_pos
rect = gui.mp_panel_rect
shoot(gui, 'mi_panel_panel.png',
      clip=(rect.x - 4, rect.y - 4, rect.width + 8, rect.height + 8))
print(f'面板矩形 {rect.width}×{rect.height}（{gui._mp_row_count()} 行）')

print('done.')
