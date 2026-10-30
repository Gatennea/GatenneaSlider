# -*- coding: utf-8 -*-
"""三角在几何引擎下的两个疑点聚焦调试：①k=3 求解 no_improve；②k=4 回放失败。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import random  # noqa: E402
import tempfile  # noqa: E402

import engine.config as ecfg  # noqa: E402
ecfg._config_path = os.path.join(tempfile.gettempdir(), '_gatennea_engine_cfg_dbg.json')

import pygame  # noqa: E402
pygame.init()

from GUI import SliderGUI  # noqa: E402
from solver import SOLVER_ALGORITHMS  # noqa: E402

fn = SOLVER_ALGORITHMS['gather'][1]


def gui_tri(k, step, shuffle, seed):
    g = SliderGUI(m=k, n=k, step=step)
    g.new_triangle_puzzle(k, step)
    if shuffle:
        random.seed(seed)
        g.game.shuffle(shuffle, step)
    g.animation_enabled = False
    return g


def to_ops(actions, step):
    ops = []
    for a in actions:
        if len(a) >= 5:
            gd, gl, side, md, rep = a[:5]
        else:
            gd, gl, side, md = a[:4]
            rep = None
        op = {'gap_type': gd, 'gap_line': gl, 'side': side,
              'direction': md, 'step': step}
        if rep is not None:
            op['rep_cell'] = list(rep)[:2]
        ops.append(op)
    return ops


for k in (3, 4):
    print(f"\n########## k={k} ##########")
    for enabled in (False, True):
        ecfg.set_enabled(enabled)
        tag = '引擎' if enabled else '經典'
        g = gui_tri(k, 2, 80, 7)
        init = [list(b.location) for b in g.game.blocks]
        res = fn(g.game, step=2, max_wait_time=25)
        acts = res.get('actions') or []
        print(f"{tag}: reason={res.get('reason')} 動作數={len(acts)} "
              f"solved={res.get('solved')} score={res.get('score')}")
        if not acts:
            continue
        ops = to_ops(acts, 2)
        # 逐步回放，打印每步细节
        for b, loc in zip(g.game.blocks, init):
            b.location = list(loc)
        if hasattr(g.game, '_clear_selection'):
            g.game._clear_selection()
        else:
            for b in g.game.blocks:
                b.be_opted = False
        g.game.update_matrix()
        for i, op in enumerate(ops):
            gt, gl, side, md = (op['gap_type'], op['gap_line'],
                                op['side'], op['direction'])
            tb = None
            if op.get('rep_cell') is not None:
                rr, cc = op['rep_cell']
                tb = g._find_block_by_cell(rr, cc)
            if tb is None:
                tb = g._find_block_on_side(gt, gl, side)
            g.game.opt(gt, gl, tb)
            sel = [b for b in g.game.blocks if b.be_opted]
            fin = g.game.try_move(md, 2)
            print(f"  {tag} 步{i+1}: {gt}{gl} side={side} dir={md} "
                  f"rep={op.get('rep_cell')} → 選中 {len(sel)} 塊 "
                  f"try_move={'OK' if fin else '拒'}")
            if not fin:
                # 拒了：看看是选中空还是方向不合法
                print(f"      選中塊位置: {[list(b.location) for b in sel][:6]}")
                print(f"      全部合法移動數: {len(g.game.all_gaps())} 縫")
                break
            g.game.commit_move(fin)
        print(f"  {tag} 播完 is_solved={g.game.is_solved()}")
ecfg.set_enabled(False)
