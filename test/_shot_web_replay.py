# -*- coding: utf-8 -*-
"""把「还原存档」录成动图 —— 给官网当复原思路参考。

用法：
    D:/python/python.exe -u test/_shot_web_replay.py archives/2-6-7-20261001-161826.json
    D:/python/python.exe -u test/_shot_web_replay.py <存档.json> --name solve67 --every 2

原理：存档里每一步自带的 move_info（选了哪条缝、哪一片、往哪推几格）拿去驱动
GUI 自己的补间动画 —— 和 _shot_web_anim.py（官网那批动图）同一套机制，
录出来是**真实的缓动滑动**，不是逐帧跳变。撤销/重做动画天然带「这一步选了
哪一片」的高亮（be_opted），顺手就成了思路提示。

方向自动判定：哪一端是还原态就从另一端往它播（打乱过程存档自动倒放成还原过程）。
"""

import argparse
import json
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
W, H = 900, 620
OUT_W = 640
MOVE_FRAMES = 5       # 一次滑动抓几帧
HOLD = 2              # 每步之后的停顿帧
DUR = 60              # 每帧毫秒
QUALITY = 55          # WebP 质量


# ---------------------------------------------------------------- 画面
def view_rect(gui):
    return pygame.Rect(0, gui.menu_bar_height,
                       gui.screen_width - gui.right_panel_width,
                       gui.screen_height - gui.menu_bar_height - gui.status_bar_height)


def block_box(gui):
    """当前画面的块包围盒（动画中按插值位置算，否则用落点）。"""
    pts = []
    anim = getattr(gui, 'anim_blocks', None)
    animating = getattr(gui, 'animating', False) and anim
    animated = set()
    if animating:
        t = gui.ease_out(gui.anim_progress)
        for i, b in enumerate(anim):
            sr, sc = gui.anim_start_pos[i][0], gui.anim_start_pos[i][1]
            er, ec = gui.anim_end_pos[i][0], gui.anim_end_pos[i][1]
            pts.append((sr + (er - sr) * t, sc + (ec - sc) * t))
            animated.add(id(b))
    for b in gui.game.blocks:
        if id(b) in animated:
            continue
        pts.append((b.location[0], b.location[1]))
    if not pts:
        return None
    return {'min_row': min(p[0] for p in pts), 'max_row': max(p[0] for p in pts),
            'min_col': min(p[1] for p in pts), 'max_col': max(p[1] for p in pts)}


def center_frame(gui):
    """每帧把棋盘居中（缩放恒定） —— 首尾两个还原矩形都居中，循环才无缝。"""
    if getattr(gui, '_bg_fixed_zoom', None) is None:
        return
    b = block_box(gui)
    if not b:
        return
    v = view_rect(gui)
    u = gui.cell_size + gui.gap_width
    gui.zoom = gui._bg_fixed_zoom
    rows = b['max_row'] - b['min_row'] + 1
    cols = b['max_col'] - b['min_col'] + 1
    gui.camera_x = v.left + v.width / 2 - (b['min_col'] + cols / 2.0) * u * gui.zoom
    gui.camera_y = v.top + v.height / 2 - (b['min_row'] + rows / 2.0) * u * gui.zoom


def grab(gui):
    center_frame(gui)
    gui.draw_board()
    surf = gui.screen.subsurface(view_rect(gui)).copy()
    w, h = surf.get_size()
    img = Image.frombytes('RGB', (w, h), pygame.image.tostring(surf, 'RGB'))
    if w != OUT_W:
        img = img.resize((OUT_W, max(1, round(h * OUT_W / float(w)))), Image.LANCZOS)
    return img


def hold(gui, n=HOLD):
    f = grab(gui)
    return [f] * max(1, n)


def fit_all(gui, kind):
    """按「所有快照的包围盒并集」定好缩放（之后每帧只平移、不改缩放，画面才稳）。"""
    v = view_rect(gui)
    if kind in ('tri', 'mi'):
        gui.zoom = gui._fit_triangle_zoom() if kind == 'tri' else gui._fit_mi_zoom()
        gui._bg_fixed_zoom = None          # 异形用自己的居中方法
        if kind == 'tri':
            gui._center_triangle()
        else:
            gui._center_mi()
        return
    u = gui.cell_size + gui.gap_width
    b = gui.game.get_boundaries()
    for snap in gui.game_history.history:
        sb = snap.get('bounds') or {}
        for key, cmp_ in (('min_row', min), ('max_row', max),
                          ('min_col', min), ('max_col', max)):
            if sb.get(key) is not None:
                b[key] = cmp_(b[key], sb[key])
    rows = b['max_row'] - b['min_row'] + 1
    cols = b['max_col'] - b['min_col'] + 1
    gui._bg_fixed_zoom = max(gui.min_zoom, min(gui.max_zoom,
                                               min(v.width * 0.86 / (cols * u),
                                                   v.height * 0.86 / (rows * u))))
    gui.zoom = gui._bg_fixed_zoom
    gui.camera_x = v.left + v.width / 2 - (b['min_col'] + cols / 2.0) * u * gui.zoom
    gui.camera_y = v.top + v.height / 2 - (b['min_row'] + rows / 2.0) * u * gui.zoom


# ---------------------------------------------------------------- 判定方向
def solved_at(gui, idx):
    gh = gui.game_history
    old = gh.history_index
    gh.restore_snapshot(gui.game, idx)
    try:
        return bool(gui.game.is_solved())
    finally:
        gh.restore_snapshot(gui.game, old)


def play(gui, reverse, every, max_steps):
    """逐步播完，返回帧列表。reverse=True 表示用 undo 往回播。"""
    gh = gui.game_history
    frames = []
    jumped = 0
    played = 0
    taken = 0

    def push_anim(mv, is_undo):
        ok = gui._start_undo_redo_animation(mv, is_undo=is_undo)
        if not ok:
            return False
        for k in range(1, MOVE_FRAMES + 1):
            gui.anim_progress = k / float(MOVE_FRAMES)
            frames.append(grab(gui))
        gui.commit_animation()          # 顺带把 history_index 推进/回退一步
        return True

    while True:
        if not reverse and gh.history_index >= len(gh.history) - 1:
            break
        if reverse and gh.history_index <= 0:
            break
        if max_steps and played >= max_steps:
            break
        mv = gh.peek_undo() if reverse else gh.peek_redo()
        taken += 1
        skip = every > 1 and (taken % every) != 1
        if mv is None or skip:
            # 没有动作信息 / 抽帧跳过的步：直接落到目标快照，不单独占帧
            gh.history_index += (-1 if reverse else 1)
            gh.restore_snapshot(gui.game, gh.history_index)
            jumped += 1
            continue
        gui._clear_sel_anim()
        if push_anim(mv, reverse):
            gui._flash_move_selection(mv, reverse)
            played += 1
            frames += hold(gui)
        else:
            gh.history_index += (-1 if reverse else 1)
            gh.restore_snapshot(gui.game, gh.history_index)
            jumped += 1
            frames += hold(gui, 1)
    return frames, played, jumped


# ---------------------------------------------------------------- main
def main():
    global OUT_W, MOVE_FRAMES, HOLD, QUALITY, DUR
    ap = argparse.ArgumentParser()
    ap.add_argument('save')
    ap.add_argument('--name', default='')
    ap.add_argument('--every', type=int, default=1, help='每 N 步录 1 步（其余瞬变跳过）')
    ap.add_argument('--max-steps', type=int, default=0)
    ap.add_argument('--width', type=int, default=OUT_W)
    ap.add_argument('--frames', type=int, default=MOVE_FRAMES, help='一次滑动抓几帧')
    ap.add_argument('--hold', type=int, default=HOLD, help='每步之后的停顿帧')
    ap.add_argument('--quality', type=int, default=QUALITY)
    ap.add_argument('--dur', type=int, default=DUR, help='每帧毫秒')
    ap.add_argument('--no-reverse', action='store_true', help='不做倒放判定，强制按存档顺序播')
    args = ap.parse_args()
    OUT_W = args.width
    MOVE_FRAMES = args.frames
    HOLD = args.hold
    QUALITY = args.quality
    DUR = args.dur

    d = json.load(open(args.save, encoding='utf-8'))
    gui = SliderGUI(m=4, n=4, step=1)
    gui.animation_enabled = True
    gui.ui_mode = 'enhanced'
    gui.selection_animation_enabled = True     # 高亮「这一步选了哪一片」
    gui.screen_width, gui.screen_height = W, H
    pygame.display.set_mode((W, H))
    gui.screen = pygame.display.get_surface()
    gui._load_save_data(d)

    kind = (d.get('puzzle') or {}).get('type', 'square')
    pz = d.get('puzzle') or {}
    gh = gui.game_history
    print('存档 %s  形态=%s %sx%s 等级=%s  快照=%d'
          % (os.path.basename(args.save), kind, pz.get('m'), pz.get('n'),
             pz.get('step'), len(gh.history)))

    reverse = False
    if not args.no_reverse:
        head = solved_at(gui, 0)
        tail = solved_at(gui, len(gh.history) - 1)
        # 打乱过程存档（首帧是还原态）→ 倒放，播出来才是「从乱到好」
        reverse = head and not tail
        print('首帧还原态=%s 末帧还原态=%s  -> %s'
              % (head, tail, '倒放（undo）' if reverse else '正放（redo）'))

    # 起点
    gh.history_index = len(gh.history) - 1 if reverse else 0
    gh.restore_snapshot(gui.game, gh.history_index)
    fit_all(gui, kind)

    frames = hold(gui, HOLD + 4)          # 开局先让人看清局面
    mid, played, jumped = play(gui, reverse, args.every, args.max_steps)
    frames += mid
    frames += hold(gui, HOLD + 6)         # 结尾停在还原态

    name = args.name or ('replay_' + os.path.splitext(os.path.basename(args.save))[0])
    name = name if name.endswith('.webp') else name + '.webp'
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    path = os.path.join(OUT, name)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=DUR, loop=0, quality=QUALITY, method=4)
    print('ok %s  %d KB  %d 帧  （滑动 %d 步 / 瞬变 %d 步）'
          % (name, os.path.getsize(path) // 1024, len(frames), played, jumped))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
