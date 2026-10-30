# -*- coding: utf-8 -*-
"""基于完整距离表的确定性下降求解器（exp 动作，保证最短）。

每一步在当前状态枚举全部「按分量」单位动作，选唯一使
canonical 距离恰好 -1 的动作执行；直至距离 0。
距离表为完整反向 BFS 产物时，路径即最短路径。
"""
import pickle

from experiments import harness as H
from experiments.exp_actions import enumerate_exp_actions, apply_exp_action
from solver.state import snapshot, restore
from solver.table_core import canonicalize

DEFAULT_TABLE = r'E:\program_project\other\doubaotest\狀態拓撲圖分析\4_4_2\table.pkl'


def load_table(path=DEFAULT_TABLE):
    with open(path, 'rb') as f:
        return pickle.load(f)


def table_descent(coords, m, n, step, table):
    """返回 (exp动作序列, 最终坐标, 初始距离)。失败抛错。"""
    cur = frozenset(coords)
    d = table.get(canonicalize(cur))
    if d is None:
        raise ValueError('状态不在表中')
    d0 = d
    path = []
    while d > 0:
        g = H.load_game({'m': m, 'n': n, 'step': step,
                         'coords': sorted(cur)})
        chosen = None
        for a in enumerate_exp_actions(g, step):
            s = snapshot(g)
            if apply_exp_action(g, a, step):
                nxt = H.coords_of(g)
                if table.get(canonicalize(nxt)) == d - 1:
                    chosen = (a, nxt)
                    restore(g, s)
                    break
            restore(g, s)
        if chosen is None:
            raise RuntimeError(f'距离 {d} 处找不到 -1 动作（表/动作模型不一致）')
        a, cur = chosen
        path.append(a)
        d -= 1
    return path, cur, d0
