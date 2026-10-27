# -*- coding: utf-8 -*-
"""真实用例冒烟：shatter（48 块 / 自定义基 / pos_scale=3）复制 → 粘贴 → 阵列。"""
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


def no_overlap(gui):
    from engine import editor_geom as eg
    med = gui._med
    placed = med['placed']
    for k in placed:
        others = {kk: vv for kk, vv in placed.items() if kk != k}
        if not eg.can_place((placed[k],), 0, k[0], others, med['basis']):
            return False
    return True


def main():
    import _test_model_editor as m
    from engine import editor_geom as eg
    gui = m._make_gui()
    gui._med_open()
    med = gui._med

    w('load shatter:', gui._med_load_model('shatter'))
    w('blocks=', len(med['placed']), 'ps=', med['pos_scale'],
      'lattice=', med['lattice'])

    # 全选 → 复制
    med['sel'] = set(med['placed'])
    w('copy:', gui._med_copy_sel(), 'items=', len(med['clip']['items']),
      'ref=', med['clip']['ref'])

    # 找第一个能贴下的横向偏移（真实间距由 can_place 判定，不猜）
    ref = med['clip']['ref']
    fit = None
    for dx in range(4, 60, 2):
        gui._med_paste_begin()
        gui._med_paste_update(float(ref[0] + dx), float(ref[1]))
        if med['paste']['ok']:
            fit = dx
            break
        gui._med_paste_cancel()
    w('first fitting dx=', fit)
    if fit is None:
        w('SMOKE_FAIL: 找不到能贴下的偏移')
        return
    w('commit:', gui._med_paste_commit(), 'blocks=', len(med['placed']),
      'last_delta=', med['last_delta'])
    w('no_overlap_after_paste:', no_overlap(gui))

    before = len(med['placed'])
    w('array 2x2:', gui._med_paste_array(2, 2), 'blocks=', len(med['placed']),
      '(was', before, ')')
    w('no_overlap_after_array:', no_overlap(gui))
    w('whole copies:', (len(med['placed']) - before) % 48 == 0)

    gui._med_close()


try:
    main()
    _LINES.append('SMOKE_OK')
except Exception:
    import traceback
    _LINES.append('SMOKE_ERR')
    _LINES.append(traceback.format_exc())

with open(os.path.join(_PROJECT, '_dbg_shatter_copy.txt'), 'w',
          encoding='utf-8') as f:
    f.write('\n'.join(_LINES) + '\n')
