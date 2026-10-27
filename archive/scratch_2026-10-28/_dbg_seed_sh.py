# -*- coding: utf-8 -*-
"""验证「改当前盘面」是否也吃到了 route A（自定义 basis + pos_scale）。

旧口径 family_of_basis 只看 basis 夹角 → 碎三角 (0.866,0)/(0,0.5) 是正交
的，会被误判成 square，且 pos_scale 压根不写（恒 1）。本脚本把这两条都钉住。
"""
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
import engine.editor_geom as eg  # noqa: E402

_OUT = os.path.join(_PROJ, 'archive', '_seed_sh.txt')
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
    spec = gui.game.spec
    basis = spec.basis
    ps = getattr(spec, 'pos_scale', 1)
    n_before = len(gui.game.blocks)
    rec('basis=', [list(r) for r in basis], 'ps=', ps, 'blocks=', n_before)

    # 旧口径对照：这就是改之前会得到的族
    rec('OLD family_of_basis ->', eg.family_of_basis(basis))
    rec('NEW infer_lattice  ->', eg.infer_lattice(
        {'basis': basis, 'pos_scale': int(ps),
         'orientations': {}}) or '(空朝向集→兜底)')

    gui.set_game_mode('create')
    gui._ann_home_sub = 'restore'
    gui.macro_notify_msg = ''
    gui._ann_btn_blocks_current()

    rec('_med_active=', gui._med_active)
    if not gui._med_active:
        rec('!! 编辑器没打开 msg=', gui.macro_notify_msg)
        return
    med = gui._med
    rec('lattice   =', med['lattice'], '(期望 tri)')
    rec('pos_scale =', med['pos_scale'], '(期望 %s)' % int(ps))
    rec('basis     =', [list(r) for r in med['basis']])
    rec('deg       =', med['deg'], '(tri→30)')
    rec('placed    =', len(med['placed']), '(期望 %s)' % n_before)

    # 连通性（保存门的头一条）
    try:
        conn = eg.is_connected(med['placed'], med['images'])
    except Exception as exc:  # noqa: BLE001
        conn = 'ERR %r' % (exc,)
    rec('connected =', conn)
    gok, why = gui._med_gate()
    rec('gate      =', gok, 'why=', why)

    # 几何往返：屏幕↔几何（ps=3 时才真验到换算）
    g = next(iter(med['placed']))
    sx, sy = gui._med_geom_to_screen(g[0][0], g[0][1])
    bx, by = gui._med_screen_to_geom(sx, sy)
    rec('roundtrip =', g[0], '->', (round(bx, 4), round(by, 4)))
    gui._med_close()
    rec('closed    =', not gui._med_active)


try:
    main()
except Exception:
    import traceback
    w.append('EXC')
    w.append(traceback.format_exc())

with open(_OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(w))
