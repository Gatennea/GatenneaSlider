# -*- coding: utf-8 -*-
"""定位「改当前盘面」在碎三角上为什么失败（复刻 _med_seed_from_model 的前置）。"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.abspath(__file__))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402

_OUT = os.path.join(_PROJ, 'archive', '_seed2.txt')
w = []


def rec(*a):
    w.append(' '.join(str(x) for x in a))


def main():
    gui = SliderGUI(m=4, n=4, step=1)
    gui.animation_enabled = False
    gui._readonly = False
    gui.save_readonly_flag = False
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui.new_model_puzzle('shatter', 1)
    gui.center_map()

    game = gui.game
    spec = game.spec
    orients = spec.orientations
    rec('n_orients =', len(orients))
    rec('labels[:8] =', list(orients)[:8])
    rec('pos_scale =', getattr(spec, 'pos_scale', None))

    basis = spec.basis
    b00, b01 = float(basis[0][0]), float(basis[0][1])
    b10, b11 = float(basis[1][0]), float(basis[1][1])
    det = b00 * b11 - b10 * b01
    scale = float(getattr(spec, 'pos_scale', 1.0) or 1.0)
    rec('det =', det, ' scale =', scale)

    def to_grid(poly):
        out = []
        for px, py in poly:
            a = (px * b11 - py * b10) / det * scale
            c = (b00 * py - b01 * px) / det * scale
            ia, ic = int(round(a)), int(round(c))
            if abs(a - ia) > 1e-6 or abs(c - ic) > 1e-6:
                raise ValueError((a, c, ia, ic))
            out.append((ia, ic))
        return tuple(out)

    bad = []
    for lb in list(orients)[:6]:
        try:
            poly = spec.cell_polygon((0, 0), lb)
            g = to_grid(poly)
            rec('  ', lb, 'poly=', [tuple(round(v, 4) for v in p) for p in poly],
                '-> grid=', g)
        except Exception as exc:  # noqa: BLE001
            bad.append((lb, repr(exc)))
            rec('  ', lb, 'ERR', repr(exc))
    rec('bad_labels =', bad[:5], 'total_bad=', len(bad))

    # 全部标签扫一遍，统计失败
    nbad = 0
    first_err = None
    for lb in orients:
        try:
            to_grid(spec.cell_polygon((0, 0), lb))
        except Exception as exc:  # noqa: BLE001
            nbad += 1
            if first_err is None:
                first_err = (lb, repr(exc))
    rec('scan: nbad =', nbad, '/', len(orients), 'first=', first_err)

    # blocks 的 point/orient
    board = game.board
    bs = list(getattr(board, 'blocks', ()))
    rec('n_blocks =', len(bs))
    if bs:
        b0 = bs[0]
        rec('b0.point =', b0.point, 'orient =', b0.orient, 'group =', getattr(b0, 'group', None))
    badp = [b.point for b in bs
            if any(float(v) != int(v) for v in b.point)]
    rec('non_int_points =', len(badp), badp[:5])
    labels_not_in = [str(b.orient) for b in bs if str(b.orient) not in orients]
    rec('orients_not_in_spec =', len(labels_not_in), labels_not_in[:5])

    # 真跑一次，看通知
    gui.set_game_mode('create')
    gui._ann_home_sub = 'restore'
    gui.macro_notify_msg = ''
    gui._ann_btn_blocks_current()
    rec('notify =', gui.macro_notify_msg)


try:
    main()
except Exception:
    import traceback
    w.append('EXC')
    w.append(traceback.format_exc())

with open(_OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(w))
