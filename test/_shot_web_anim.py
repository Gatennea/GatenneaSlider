# -*- coding: utf-8 -*-
"""给官网批量录「动图」（一次跑完，直接写进 GatenneaSliderWeb/images/anim/）。

执行：``D:/python/python.exe -u test/_shot_web_anim.py``

和 _shot_web_gallery.py（静态截图）的区别：这里要的是**过程**，
所以必须让滑块真的滑起来 —— 靠 GUI 自带的补间状态机出中间帧：

    move_selected_blocks()  ->  start_animation()  游戏状态还没提交，
    只把「起点/终点/位移」记在 anim_blocks / anim_start_pos / _anim_dr 上，
    渲染层按 ease_out(anim_progress) 插值画。主循环平时用墙钟推进 anim_progress，
    这里没有主循环，所以**手动把 anim_progress 从 0 拨到 1**，每拨一格抓一帧，
    最后 commit_animation() 提交。得到的是真实的缓动滑动，不是跳变。

输出 WebP 动图（比 GIF 小一个量级，现代浏览器全支持）。
"""

import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from GUI import SliderGUI  # noqa: E402

OUT = os.path.join(os.path.dirname(_ROOT), 'GatenneaSliderWeb', 'images', 'anim')
if not os.path.isdir(OUT):
    os.makedirs(OUT)

W, H = 900, 620          # 录制动图用的窗口（比截图小，动图体积才压得住）
OUT_W = 640              # 输出宽度
MOVE_FRAMES = 9          # 一次滑动抓几帧
HOLD = 7                 # 静止片段重复几帧（让人看清当前状态）
DUR = 55                 # 每帧毫秒
QUALITY = 62             # WebP 质量


def view_rect(gui):
    """棋盘可见区（扣掉顶部菜单、右侧面板、底部状态栏）。"""
    return pygame.Rect(0, gui.menu_bar_height,
                       gui.screen_width - gui.right_panel_width,
                       gui.screen_height - gui.menu_bar_height - gui.status_bar_height)


def center_square(gui, fill=0.80):
    """方形居中 + 适配缩放（照 _center_mi 的算式，一格 = cell_size+gap 世界像素）。"""
    b = gui.game.get_boundaries()
    rows = b['max_row'] - b['min_row'] + 1
    cols = b['max_col'] - b['min_col'] + 1
    u = gui.cell_size + gui.gap_width
    v = view_rect(gui)
    gui.zoom = max(gui.min_zoom, min(gui.max_zoom,
                                     min(v.width * fill / (cols * u),
                                         v.height * fill / (rows * u))))
    gui.camera_x = v.left + v.width / 2 - (b['min_col'] + cols / 2.0) * u * gui.zoom
    gui.camera_y = v.top + v.height / 2 - (b['min_row'] + rows / 2.0) * u * gui.zoom


def refit(gui, shape):
    if shape == 'tri':
        gui.zoom = gui._fit_triangle_zoom()
        gui._center_triangle()
    elif shape == 'mi':
        gui.zoom = gui._fit_mi_zoom()
        gui._center_mi()
    else:
        center_square(gui)


def grab(gui):
    """画一帧并转成 PIL 图（只留棋盘可见区）。"""
    gui.draw_board()
    surf = gui.screen.subsurface(view_rect(gui)).copy()
    w, h = surf.get_size()
    img = Image.frombytes('RGB', (w, h), pygame.image.tostring(surf, 'RGB'))
    if w != OUT_W:
        img = img.resize((OUT_W, max(1, round(h * OUT_W / float(w)))), Image.LANCZOS)
    return img


def hold(gui, n=HOLD):
    """静止片段：同一帧重复 n 次。"""
    f = grab(gui)
    return [f] * n


def slide(gui, direction, step=None):
    """执行一次滑动，返回它的中间帧（含起止的静止帧）。"""
    frames = [grab(gui)]                       # 起始态
    ok = gui.move_selected_blocks(direction, step)
    if not ok or not getattr(gui, 'animating', False):
        return frames, False
    # 手动推进补间：渲染层按 ease_out(anim_progress) 插值
    for i in range(1, MOVE_FRAMES + 1):
        gui.anim_progress = i / float(MOVE_FRAMES)
        frames.append(grab(gui))
    gui.commit_animation()
    gui.selected_gap = None
    gui.selected_block = None
    gui._gap_anchor_world = None
    return frames, True


def pick(gui, lo=3, hi=8):
    """找一个「缝 + 锚点块」：能被切出小片（lo~hi 块），且至少一个方向推得动。

    opt() 的语义是「沿缝切出与锚点连通的一整片」，整盘连通时会全选 ——
    那样既不好看也不像正常操作，所以这里专挑小片。
    返回 (缝, 锚点块, 能推的方向列表)。
    """
    b = gui.game.get_boundaries()
    for kind in ('h', 'v'):
        for line in range(b['min_row'] - 1, b['max_row'] + 2):
            for blk in gui.game.blocks:
                try:
                    gui.game.opt(kind, line, blk)
                except Exception:
                    continue
                n = sum(1 for x in gui.game.blocks if x.be_opted)
                if not (lo <= n <= hi):
                    continue
                # 判「推得动」要走 GUI 的干跑路径，必须先把缝和锚点块设好
                gui.selected_gap = (kind, line)
                gui.selected_block = blk
                dirs = [d for d in (('a', 'd') if kind == 'h' else ('w', 's'))
                        if gui._arrow_move_allowed(d)]
                if not dirs:
                    continue
                try:
                    gui._gap_anchor_world = gui.screen_to_world(
                        *gui._key_center(tuple(blk.location)))
                except Exception:
                    gui._gap_anchor_world = None
                return (kind, line), blk, dirs
    return None, None, []


def save(frames, name, note=''):
    if not frames:
        print('  -- %-24s 没有帧，跳过' % name)
        return
    path = os.path.join(OUT, name)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=DUR, loop=0, quality=QUALITY, method=4)
    kb = os.path.getsize(path) // 1024
    print('  ok %-24s %5d KB  %2d 帧  %s' % (name, kb, len(frames), note))


def run(label, fn):
    print('== %s ==' % label)
    try:
        fn()
    except Exception:
        print('  !! 失败：')
        traceback.print_exc()


# ---------------------------------------------------------------- 初始化
gui = SliderGUI(m=4, n=4, step=1)
gui.animation_enabled = True        # 这次要动画（静态图脚本里是关掉的）
gui.ui_mode = 'enhanced'
gui.screen_width, gui.screen_height = W, H
pygame.display.set_mode((W, H))
gui.screen = pygame.display.get_surface()
print('画布 %dx%d，输出宽 %d -> %s\n' % (W, H, OUT_W, OUT))


# ======================= A 三步玩法 =======================
def anim_how():
    """选缝 → 点一侧（整片被选中）→ 沿缝推。官网首屏最缺的一段。"""
    gui.new_puzzle(4, 4, 1)
    gui.shuffle_puzzle()
    refit(gui, 'square')
    frames = hold(gui, HOLD + 3)                       # ① 原始局面

    gap, blk, dirs = pick(gui, 3, 6)
    if gap is None:
        print('    没找到合适的小片组合')
        return
    gui.selected_gap = gap                              # ② 只选缝，还没选块
    gui.selected_block = None
    frames += hold(gui, HOLD + 3)
    gui.selected_block = blk
    gui.game.opt(gap[0], gap[1], blk)                   # ③ 点一侧，整片亮起
    frames += hold(gui, HOLD + 3)
    f, ok = slide(gui, dirs[0])                         # ④ 沿缝推
    frames += f
    if ok:
        frames += hold(gui, HOLD + 5)
    save(frames, 'how.webp', '选缝 → 点一侧 → 沿缝推（4×4 等级1）')


# ======================= B 打乱 → 还原 =======================
def anim_restore():
    """不用求解器也能录「还原过程」：从还原态走 N 步造出打乱态，
    再把这 N 步**逆序反着走回去** —— 录出来就是从乱到好的过程。"""
    gui.new_puzzle(3, 3, 1)
    refit(gui, 'square')

    # 先正着走 4 步，记下每一步的（缝, 锚点块, 方向）
    moves = []
    for _ in range(4):
        gap, blk, dirs = pick(gui, 2, 5)
        if gap is None:
            break
        d = dirs[0]
        if not gui.move_selected_blocks(d):
            break
        gui.commit_animation()
        moves.append((gap, blk, d))
        gui.selected_gap = None
        gui.selected_block = None
        gui._gap_anchor_world = None
    if not moves:
        print('    造不出打乱态')
        return
    refit(gui, 'square')

    # 逆序回放：反向字母 + 反着点（缝不变，锚点用「推完之后那一侧」的块）
    opp = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}
    frames = hold(gui, HOLD + 4)                        # 打乱态
    for gap, blk, d in reversed(moves):
        rd = opp[d]
        # 反向移动：锚点要落在移动后该选的那一侧，找一个切出同样大小小片的块
        target = None
        for cand in gui.game.blocks:
            try:
                gui.game.opt(gap[0], gap[1], cand)
            except Exception:
                continue
            n = sum(1 for x in gui.game.blocks if x.be_opted)
            if 2 <= n <= 6 and gui._arrow_move_allowed(rd):
                target = cand
                break
        if target is None:
            continue
        gui.selected_gap = gap
        gui.selected_block = target
        gui.game.opt(gap[0], gap[1], target)
        try:
            gui._gap_anchor_world = gui.screen_to_world(
                *gui._key_center(tuple(target.location)))
        except Exception:
            pass
        frames += hold(gui, 3)
        f, ok = slide(gui, rd)
        frames += f
    frames += hold(gui, HOLD + 8)                       # 还原态（含过关提示）
    save(frames, 'restore.webp', '3×3 从打乱走回实心矩形（逆序回放录制）')


# ======================= C 等级 step 对比 =======================
def anim_step():
    """左右两栏：等级1 一次走 1 格 vs 等级2 一次走 2 格。
    打乱带 step、消耗的随机序列不同，两栏没法摆出严格相同的局面 ——
    但要对比的本来就是「一次滑动滑多远」，局面不同无妨。"""
    cols = {}
    for st in (1, 2):
        gui.new_puzzle(5, 5, st)
        gui.shuffle_puzzle()
        refit(gui, 'square')
        gap, blk, dirs = pick(gui, 4, 9)
        if gap is None:
            cols[st] = None
            continue
        f, ok = slide(gui, dirs[0])          # step 默认取 current_step
        if not ok:
            cols[st] = None
            continue
        cols[st] = hold(gui, 6) + f + hold(gui, 8)
    if cols.get(1) is None or cols.get(2) is None:
        print('    有一栏没录成：%s' % {k: ('ok' if v else '失败')
                                    for k, v in cols.items()})
        return
    n = min(len(cols[1]), len(cols[2]))
    pad = 6
    w1 = cols[1][0].width
    h1 = cols[1][0].height
    canvas_w = w1 * 2 + pad * 3
    frames = []
    for i in range(n):
        c = Image.new('RGB', (canvas_w, h1), (13, 13, 15))
        c.paste(cols[1][i], (pad, 0))
        c.paste(cols[2][i], (w1 + pad * 2, 0))
        frames.append(c.resize((OUT_W, max(1, round(h1 * OUT_W / float(canvas_w)))),
                               Image.LANCZOS))
    save(frames, 'step.webp', '左=等级1 走1格，右=等级2 走2格（同局面同缝）')


# ======================= D 三角形态滑动 =======================
def anim_triangle():
    """打乱局面随机，能推动的组合时有时无 —— 外层多试几个局面。"""
    frames = None
    for attempt in range(10):
        gui.new_triangle_puzzle(5, 1)
        try:
            gui.shuffle_puzzle()
        except Exception:
            pass
        refit(gui, 'tri')
        got = _try_shape_move(gui, kinds=('h', 'v'), lines=range(-2, 9),
                              dirs=('w', 's', 'a', 'd', 'q', 'e'),
                              lo=2, hi=7)
        if got:
            pre, mid, post = got
            frames = hold(gui, HOLD + 3) + pre + mid + post
            break
    if frames is None:
        print('    三角试了 10 个局面都没找到能推动的组合')
        return
    save(frames, 'triangle.webp', '三角形態：整片沿斜向晶格滑动')


def _try_shape_move(gui, kinds, lines, dirs, lo, hi):
    """在当前局面找「缝+锚点+方向」，找到就录一段滑动。
    返回 (前置hold帧, 动画帧, 结尾hold帧) 或 None。"""
    for kind in kinds:
        for line in lines:
            for blk in list(gui.game.blocks):
                try:
                    gui.game.opt(kind, line, blk)
                except Exception:
                    continue
                n = sum(1 for x in gui.game.blocks if x.be_opted)
                if not (lo <= n <= hi):
                    continue
                gui.selected_gap = (kind, line)
                gui.selected_block = blk
                for d in dirs:
                    if not gui._arrow_move_allowed(d):
                        continue
                    f, ok = slide(gui, d)
                    if ok:
                        return hold(gui, 3), f, hold(gui, 6)
    return None


# ======================= E 米字形态滑动 =======================
def anim_mi():
    frames = None
    for attempt in range(10):
        gui.new_mi_puzzle(3, 3, 1)
        try:
            gui.shuffle_puzzle()
        except Exception:
            pass
        refit(gui, 'mi')
        # 米字 4 族缝：h/v/d1/d2，缝线可以落在半格位置，步长 0.5 暴力扫
        got = _try_shape_move(gui, kinds=('h', 'v', 'd1', 'd2'),
                              lines=[x * 0.5 for x in range(-4, 18)],
                              dirs=('w', 's', 'a', 'd', 'q', 'e', 'z', 'x'),
                              lo=2, hi=8)
        if got:
            pre, mid, post = got
            frames = hold(gui, HOLD + 3) + pre + mid + post
            break
    if frames is None:
        print('    米字试了 10 个局面都没找到能推动的组合')
        return
    save(frames, 'mi.webp', '米字形態：一格里的多块小三角整体滑动')


# ======================= F 数字谜题 =======================
def anim_numbered():
    gui.new_puzzle(4, 4, 1, numbered=True)
    gui.shuffle_puzzle()
    refit(gui, 'square')
    frames = hold(gui, HOLD + 3)
    gap, blk, dirs = pick(gui, 3, 6)
    if gap is None:
        print('    数字形态没找到小片')
        return
    f, ok = slide(gui, dirs[0])
    frames += hold(gui, 3) + f + hold(gui, 6)
    save(frames, 'numbered.webp', '數字形態：編號跟着整片一起走')


run('A 三步玩法', anim_how)
run('B 打乱→还原', anim_restore)
run('C 等级对比', anim_step)
run('D 三角', anim_triangle)
run('E 米字', anim_mi)
run('F 数字', anim_numbered)
print('\n完成 ->', OUT)
