# -*- coding: utf-8 -*-
"""把 tag_bfs --gens 吐出的回路置换交给 sympy 做精确 Schreier-Sims。

用来替代 _k1_s16_loop2.py：绝对位置口径的数据由 C++ 产出，这里只算群阶，
不再用任何平移归一化。
"""

import io
import math

from sympy.combinatorics import Permutation, PermutationGroup

LOG = r'E:\program_project\other\doubaotest\slider\math_lab\branch\experiments\math_repro\_work\_s1_abs_d6_gens.log'


def main():
    lines = io.open(LOG, encoding='utf-8').read().splitlines()
    idx = next(i for i, l in enumerate(lines) if l.startswith('-- gens'))
    n = int(lines[idx].split()[2])
    gens = []
    for l in lines[idx + 1: idx + 1 + n]:
        g = [int(x) for x in l.split(',')]
        assert len(g) == 16 and sorted(g) == list(range(16)), ('bad perm', g)
        gens.append(Permutation(g))

    print('gens:', len(gens), 'all are bijections: True')

    G = PermutationGroup(gens)
    order = G.order()
    print('degree:', G.degree)
    print('group order:', order)
    print('16!        :', math.factorial(16))
    print('equals 16! :', order == math.factorial(16))
    print('equals 16!/2:', order == math.factorial(16) // 2)
    print('is_transitive:', G.is_transitive())

    # 顺便：这 130 个里有没有奇置换 / 有没有 2-循环
    odd = [i for i, p in enumerate(gens) if p.signature() == -1]
    two = []
    for i, p in enumerate(gens):
        cyc = p.cyclic_form
        if len(cyc) == 15 and all(len(c) == 2 for c in cyc[:1]) and sum(len(c) for c in cyc) == 16:
            two.append(i)
    print('odd permutations:', len(odd))
    print('pure 2-cycles (15 transpositions? no—single 2-cycle):',
          [i for i, p in enumerate(gens)
           if len(p.cyclic_form) == 1 and len(p.cyclic_form[0]) == 2])


if __name__ == '__main__':
    main()
