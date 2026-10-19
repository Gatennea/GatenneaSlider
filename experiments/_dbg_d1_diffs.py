# -*- coding: utf-8 -*-
"""复现 D1 段拿逐盘差数：原骨架 gather_solve vs 共享 square_gatherer（10 seeds）"""
import os, sys, random, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from game import SliderMatrix
from solver.ml.gather_solver import gather_solve
from solver.ml.shape_gather import square_gatherer

sg = square_gatherer()
diffs = []
for seed in range(10):
    random.seed(seed)
    g = SliderMatrix(4, 4)
    g.shuffle(30, 2)
    a = gather_solve(g, 2, max_steps=300, patience=150, max_wait_time=10)
    random.seed(seed)
    g2 = SliderMatrix(4, 4)
    g2.shuffle(30, 2)
    b = sg.solve(g2, (4, 4, 2), 2, max_steps=300, patience=150, max_wait_time=10)
    d = abs(a['end']['score'] - b['score'])
    diffs.append(d)
    print('seed %d: orig=%.4f shared=%.4f diff=%.4f' %
          (seed, a['end']['score'], b['score'], d))
print('---')
print('max diff = %.4f, mean = %.4f, >0.02 count = %d' %
      (max(diffs), statistics.mean(diffs), sum(1 for d in diffs if d >= 0.02)))
