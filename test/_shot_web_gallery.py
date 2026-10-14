# -*- coding: utf-8 -*-
"""给官网截图画廊批量出图（一次跑完，直接写进 GatenneaSliderWeb/images/）。

执行：``D:/python/python.exe -u test/_shot_web_gallery.py``
输出：../GatenneaSliderWeb/images/{5..12}.xxx.png

文件名与官网 index.html 画廊里约定的 data-file 一一对应（改一个就要改另一个）。
每张都是「真实运行画面」，不画示意图 —— 用户明确要求用截图而不是手绘图。

四种形态各出一张三联拼图：小尺寸还原态 / 中等尺寸打乱态（主图）/ 大尺寸还原态，
一个画面里就能看出「尺寸能有多大」和「还原态长什么样」。
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

OUT = os.path.join(os.path.dirname(_ROOT), 'GatenneaSliderWeb', 'images')
if not os.path.isdir(OUT):
    os.makedirs(OUT)

BG = (13, 13, 15)


def view_rect(gui):
    """棋盘所在的可见区域（扣掉顶部菜单、右侧面板、底部状态栏）。"""
    return pygame.Rect(0, gui.menu_bar_height,
                       gui.screen_width - gui.right_panel_width,
                       gui.screen_height - gui.menu_bar_height - gui.status_bar_height)


def snap(gui, name, note=''):
    gui.draw_board()
    path = os.path.join(OUT, name)
    pygame.image.save(gui.screen, path)
    size = os.path.getsize(path) // 1024
    print('  ok %-26s %5d KB  %s' % (name, size, note))


def board_shot(gui, shape, fill=0.86):
    """把当前局面画出来，只裁出棋盘所在的那块画面。"""
    refit(gui, shape, fill)
    gui.draw_board()
    return gui.screen.subsurface(view_rect(gui)).copy()


def center_square(gui, fill=0.86):
    """方形棋盘居中 + 适配缩放（照 _center_mi 的算式，注意一格 = cell_size+gap 世界像素）。"""
    b = gui.game.get_boundaries()
    rows = b['max_row'] - b['min_row'] + 1
    cols = b['max_col'] - b['min_col'] + 1
    u = gui.cell_size + gui.gap_width          # 一格在 zoom=1 时的世界像素
    v = view_rect(gui)
    avail_w = v.width * fill
    avail_h = v.height * fill
    gui.zoom = max(gui.min_zoom, min(gui.max_zoom,
                                     min(avail_w / (cols * u), avail_h / (rows * u))))
    # 方形：screen_x = c*u*zoom + camera_x，screen_y = r*u*zoom + camera_y
    gui.camera_x = v.left + v.width / 2 - (b['min_col'] + cols / 2.0) * u * gui.zoom
    gui.camera_y = v.top + v.height / 2 - (b['min_row'] + rows / 2.0) * u * gui.zoom


def refit(gui, shape, fill=0.86):
    """打乱后边界可能变大，重新居中+适配。"""
    if shape == 'tri':
        gui.zoom = gui._fit_triangle_zoom()
        gui._center_triangle()
    elif shape == 'mi':
        gui.zoom = gui._fit_mi_zoom()
        gui._center_mi()
    else:
        center_square(gui, fill)


def compose(shots, name, note=''):
    """三联拼图：左大图（主视）+ 右上 + 右下。画布 16:9，画廊裁切不会切掉内容。"""
    W, H = 1280, 720
    pad = 8
    boxes = [(0, 0, 820, H), (820, 0, 460, H // 2), (820, H // 2, 460, H // 2)]
    canvas = pygame.Surface((W, H))
    canvas.fill(BG)
    for surf, box in zip(shots, boxes):
        bx, by, bw, bh = box
        iw, ih = surf.get_size()
        s = min((bw - 2 * pad) / float(iw), (bh - 2 * pad) / float(ih))
        tw, th = max(1, int(iw * s)), max(1, int(ih * s))
        canvas.blit(pygame.transform.smoothscale(surf, (tw, th)),
                    (bx + (bw - tw) // 2, by + (bh - th) // 2))
    path = os.path.join(OUT, name)
    pygame.image.save(canvas, path)
    print('  ok %-26s %5d KB  %s' % (name, os.path.getsize(path) // 1024, note))


def setup(gui, shape, spec, shuffle):
    """按形态建局；(rows, cols, step, numbered)。"""
    if shape == 'square':
        gui.new_puzzle(spec[0], spec[1], spec[2], numbered=len(spec) > 3 and spec[3])
    elif shape == 'tri':
        gui.new_triangle_puzzle(spec[0], spec[1])
    else:
        gui.new_mi_puzzle(spec[0], spec[1], spec[2])
    if shuffle:
        try:
            gui.shuffle_puzzle()
        except Exception as e:
            print('    (打乱不可用 %s：%s)' % (shape, e))


gui = SliderGUI(m=6, n=6, step=2)
gui.animation_enabled = False
gui.ui_mode = 'enhanced'
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()
print('画布 %dx%d -> %s' % (gui.screen_width, gui.screen_height, OUT))

# ======================= 四种形态：三联（小还原 / 中打乱 / 大还原）=======================
# 每项 (形态, [小号规格, 主图规格, 大号规格], 说明)
PLANS = [
    ('5.矩形形態.png', 'square',
     [(3, 3, 1), (6, 6, 2), (8, 8, 1)],
     '矩形：3×3 还原 / 6×6 打乱 / 8×8 还原'),
    ('6.三角形態.png', 'tri',
     [(3, 1), (6, 1), (9, 1)],
     '三角：边长 3 还原 / 边长 6 打乱 / 边长 9 还原'),
    ('7.米字形態.png', 'mi',
     [(2, 2, 1), (4, 4, 2), (5, 5, 1)],
     '米字：2×2 还原 / 4×4 打乱 / 5×5 还原'),
    ('8.數字形態.png', 'square',
     [(3, 3, 1, True), (4, 4, 1, True), (6, 6, 1, True)],
     '带序号：3×3 还原 / 4×4 打乱 / 6×6 还原'),
]

for name, shape, specs, note in PLANS:
    shots = []
    for i, spec in enumerate(specs):
        setup(gui, shape, spec, shuffle=(i == 1))   # 只有主图打乱，另两张是还原态
        shots.append(board_shot(gui, shape))
        print('    %s 第%d格 %s 块=%d 状态=%s'
              % (shape, i + 1, spec, len(gui.game.blocks),
                 '打乱' if i == 1 else '还原'))
    # 拼图顺序：主图放左边大格，两张还原态放右边上下
    compose([shots[1], shots[0], shots[2]], name, note)

# ======================= 14 等级 step 对照（着色器开，颜色数 = step²）=======================
# 尺寸相同、只换等级，最能说明「等级决定能互换的范围」。还原态 + 着色器最直观。
_step_shots = []
for _st in (1, 2, 3):
    gui.new_puzzle(6, 6, _st)
    gui.coloring_enabled = True
    gui.chain_hint_enabled = False
    _step_shots.append(board_shot(gui, 'square'))
    print('    step=%d 还原态，着色器开' % _st)
gui.coloring_enabled = False
compose([_step_shots[1], _step_shots[0], _step_shots[2]], '14.等級step.png',
        '同为 6×6，等级 1 / 2 / 3（着色器开：颜色数 = step²）')

# ======================= 9 着色器 =======================
setup(gui, 'square', (6, 6, 2), shuffle=True)
refit(gui, 'square')
gui.coloring_enabled = True
gui.chain_hint_enabled = False
snap(gui, '9.著色器.png', '分组着色开（step=2）')
gui.coloring_enabled = False

# ======================= 10 连锁器（悬停在某个空位上）=======================
setup(gui, 'square', (6, 6, 2), shuffle=True)
refit(gui, 'square')
gui.coloring_enabled = True
gui.chain_hint_enabled = True
# 找一个离棋盘中心最近的空格当悬停点（连锁提示最该指的就是「洞」，且要在画面中间）
hover = None
occ = set((b.location[0], b.location[1]) for b in gui.game.blocks)
bnd = gui.game.get_boundaries()
cr = (bnd['min_row'] + bnd['max_row']) / 2.0
cc = (bnd['min_col'] + bnd['max_col']) / 2.0
best = 1e9
for r in range(bnd['min_row'] - 1, bnd['max_row'] + 2):
    for c in range(bnd['min_col'] - 1, bnd['max_col'] + 2):
        if (r, c) not in occ:
            d = (r - cr) ** 2 + (c - cc) ** 2
            if d < best:
                best, hover = d, (r, c)
gui.hover_cell = hover
snap(gui, '10.連鎖器.png', '连锁+着色开，悬停 %s' % (hover,))
gui.chain_hint_enabled = False
gui.coloring_enabled = False
gui.hover_cell = None

# ======================= 11 选缝隙 + 箭头按键 =======================
# opt() 是「沿缝切出与该块连通的一整片」，整盘连通时会全选 —— 那种画面教学上没意义。
# 这里搜索一个能切出小片（4~9 块）而且真的推得动的（缝 + 锚点块）组合。
setup(gui, 'square', (6, 6, 1), shuffle=True)
refit(gui, 'square')
bnd = gui.game.get_boundaries()
dirs = gui.DIRECTIONS if hasattr(gui, 'DIRECTIONS') else None
picked = None
for direction in ('h', 'v'):
    for line in range(bnd['min_row'] - 1, bnd['max_row'] + 2):
        for blk in gui.game.blocks:
            gui.game.opt(direction, line, blk)
            n = sum(1 for x in gui.game.blocks if x.be_opted)
            if not (4 <= n <= 9):
                continue
            gui.selected_gap = (direction, line)
            gui.selected_block = blk
            gui._gap_anchor_world = gui.screen_to_world(*gui._key_center(tuple(blk.location)))
            # 至少要有一个方向真的能推，箭头按键才会画出来
            try:
                if not any(gui._arrow_move_allowed(d) for d in ('a', 'd', 'w', 's')):
                    continue
            except Exception:
                continue
            picked = (direction, line, blk, n)
            break
        if picked:
            break
    if picked:
        break

if picked is None:  # 兜底：随便留一片全选也不会画不出图，但至少不至于崩
    gui.selected_gap = ('h', 3)
    gui.game.opt('h', 3, gui.game.blocks[0])
    gui.selected_block = gui.game.blocks[0]
    gui._gap_anchor_world = gui.screen_to_world(*gui._key_center(tuple(gui.game.blocks[0].location)))
    print('    警告：没找到小片组合，用了兜底')
else:
    print('    选中 %s 缝 line=%d，共 %d 块（锚点在 %s）'
          % (picked[0], picked[1], picked[3], tuple(picked[2].location)))
snap(gui, '11.縫隙與箭頭按鍵.png', '选中一条缝 + 被切出的一小片 + 两侧箭头按键')
gui.selected_gap = None
gui.selected_block = None
gui._gap_anchor_world = None

# ======================= 12 成绩面板 =======================
setup(gui, 'square', (6, 6, 2), shuffle=True)
refit(gui, 'square')
gui.show_records_panel = True
# 塞几条演示成绩（仅内存，不落盘），空面板没说服力
_key = gui.records_key() if hasattr(gui, 'records_key') else '2~6*6'
_mat = [[1] * 6 for _ in range(6)]
for _ms, _mv in ((187432, 96), (203118, 104), (168940, 88), (241505, 121),
                 (175220, 91), (196377, 99), (159083, 84), (228914, 113)):
    gui.records.add_record(_key, 6, 6, 2, _mat, _ms, _mv, False)

gui.draw_board()
gui.draw_records_panel()
_path = os.path.join(OUT, '12.成績面板.png')
pygame.image.save(gui.screen, _path)
print('  ok %-26s %5d KB  %s' % ('12.成績面板.png', os.path.getsize(_path) // 1024, '成绩面板（F3）'))
gui.show_records_panel = False

print('完成。13.手機觸控.png 需要真机/浏览器，留空位。')
