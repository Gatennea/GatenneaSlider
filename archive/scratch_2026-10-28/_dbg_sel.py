# -*- coding: utf-8 -*-
"""诊断：右键拖框选为什么选不中。"""
import os
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

_PROJECT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)
sys.path.insert(0, os.path.join(_PROJECT, 'test'))

import pygame  # noqa: E402

_LINES = []


def w(*a):
    _LINES.append(' '.join(str(x) for x in a))


def main():
    import _test_model_editor as m
    from engine import editor_geom as eg
    gui = m._make_gui()
    gui._med_open()
    med = gui._med
    i_up, _i_dn = m._tri_indices(gui)
    imgs = med['images']['tri']
    med['placed'] = {((x, 0), 'tri', i_up): imgs[i_up] for x in (0, 4, 8)}
    med['groups'] = {}
    gui._med_rebuild()
    gui.center_map()

    w('screen', gui.screen_width, gui.screen_height,
      'menu_bar_h', gui.menu_bar_height)
    w('panel_rect', gui._med_panel_rect())
    w('bar_rect', gui._med_bar_rect())

    pts = []
    for k in med['placed']:
        poly = eg.poly_of(k[0], med['placed'][k], med['basis'])
        pts.append(gui._med_geom_to_screen(sum(p[0] for p in poly) / len(poly),
                                           sum(p[1] for p in poly) / len(poly)))
    w('block_screen_pts', pts)
    x0 = min(p[0] for p in pts) - 45
    y0 = min(p[1] for p in pts) - 45
    x1 = max(p[0] for p in pts) + 45
    y1 = max(p[1] for p in pts) + 45
    w('band', x0, y0, x1, y1)
    w('hits_panel', gui._med_panel_rect().collidepoint(x0, y0),
      'hits_bar', gui._med_bar_rect().collidepoint(x0, y0))

    # 手动走一遍事件，看每步状态
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 3, 'pos': (float(x0), float(y0))})
    ret = gui._med_handle_event(ev)
    w('after_down ret=', ret, 'rmb=', med.get('rmb'))
    for t in (0.3, 0.7, 1.0):
        gui._med_handle_event(pygame.event.Event(
            pygame.MOUSEMOTION,
            {'pos': (float(x0 + (x1 - x0) * t), float(y0 + (y1 - y0) * t)),
             'rel': (0, 0), 'buttons': (0, 0, 1)}))
    w('after_motion rmb=', med.get('rmb'), 'rband=', med.get('rband'))
    gui._med_handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONUP, {'button': 3, 'pos': (float(x1), float(y1))}))
    w('after_up sel=', med.get('sel'), 'rband=', med.get('rband'))

    # 直接调 select_box 看几何口径对不对
    import pygame as _pg
    med['rband'] = None
    gui._med_select_box(_pg.Rect(x0, y0, x1 - x0, y1 - y0))
    w('direct select_box sel=', len(med.get('sel') or []))
    gui._med_close()


try:
    main()
    _LINES.append('DBG_OK')
except Exception:
    import traceback
    _LINES.append('DBG_ERR')
    _LINES.append(traceback.format_exc())

with open(os.path.join(_PROJECT, '_dbg_sel.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(_LINES) + '\n')
