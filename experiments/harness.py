# -*- coding: utf-8 -*-
"""实验公共库：可复现打乱语料、局面装载、重放验证、指标。

所有实验脚本都从这里取语料和工具，保证各算法跑在完全相同的输入上。
运行目录需为 GatenneaSlider（game.py 所在目录）。
"""
import os
import sys
import time
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from game import Block, SliderMatrix                      # noqa: E402
from solver.actions import apply_action                  # noqa: E402
from solver.ml.gather_solver import gather_metrics       # noqa: E402


# ---------------------------------------------------------------------------
# 语料
# ---------------------------------------------------------------------------
def gen_state(m, n, step, seed, attempts=140, bias=0.8):
    """生成一个可复现的打乱局面（正向随机游走，故必然可解）。

    返回 dict：m,n,step,seed,coords（排序后的 (r,c) 列表）。
    bias>0 用 Metropolis 偏向更散（更深）的局面。
    """
    random.seed(seed)          # shuffle 内部用全局 random
    g = SliderMatrix(m, n)
    g.shuffle(attempts=attempts, step=step, bias=bias, min_score=None)
    coords = sorted(tuple(b.location) for b in g.blocks)
    return {'m': m, 'n': n, 'step': step, 'seed': seed, 'coords': coords}


def build_corpus(specs, per_config, attempts=140, bias=0.8, seed0=1000):
    """specs: [(m,n,step), ...]；每个配置生成 per_config 个局面。"""
    corpus = []
    for ci, (m, n, step) in enumerate(specs):
        for k in range(per_config):
            seed = seed0 + ci * 100000 + k
            corpus.append(gen_state(m, n, step, seed, attempts, bias))
    return corpus


def load_game(snap):
    """从语料快照装载一个全新 SliderMatrix。"""
    m, n = snap['m'], snap['n']
    g = SliderMatrix(m, n)
    g.blocks = [Block([r, c]) for r, c in snap['coords']]
    g.matrix = None
    g.update_matrix()
    return g


def coords_of(g):
    return frozenset(tuple(b.location) for b in g.blocks)


def start_score(snap):
    return gather_metrics(frozenset(snap['coords']), snap['m'], snap['n'])


# ---------------------------------------------------------------------------
# 重放验证（独立于求解路径，用游戏原生 apply_action 复现）
# ---------------------------------------------------------------------------
def replay(snap, actions):
    """返回 (是否复原, 最终 game)。任一步非法即失败。"""
    g = load_game(snap)
    for a in actions:
        if not apply_action(g, a, snap['step']):
            return False, g
    return g.is_solved(), g


def time_call(fn):
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0
