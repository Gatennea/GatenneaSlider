# -*- coding: utf-8 -*-
"""调试单个过渡：矩阵重建 vs move_info 预测，定位坐标偏移。"""
import json
import sys

from experiments.analyze_conjugation import snap_coords
from experiments import harness as H
from game import DIRECTIONS


def main(path, idx):
    arc = json.load(open(path, encoding='utf-8'))
    snaps = arc['history']['snapshots']
    coords = [snap_coords(s) for s in snaps]
    pre, post = frozenset(coords[idx]), frozenset(coords[idx + 1])
    mi = snaps[idx + 1]['move_info']
    dr, dc = DIRECTIONS[mi['direction']]
    step = mi['step']
    moved = [tuple(p) for p in mi['moved_positions']]
    pred_post = (pre - set(moved)) | {(r + dr * step, c + dc * step)
                                      for r, c in moved}

    print(f"gap {mi['gap_type']} line {mi['gap_line']} dir {mi['direction']}")
    print(f"矩阵重建 移除={sorted(pre - post)}")
    print(f"矩阵重建 新增={sorted(post - pre)}")
    print(f"move_info moved(pre)={sorted(moved)}")
    print(f"预测 移除={sorted(set(moved))}")
    print(f"预测 新增={sorted({(r+dr*step,c+dc*step) for r,c in moved})}")
    print(f"预测post==矩阵post ? {pred_post == post}")
    # 若是整体偏移，求 pre 与“矩阵post反推”的常数差
    # 直接比较 moved 与 矩阵重建移除：
    rem = pre - post
    if set(moved) != rem:
        offs = {(m[0]-x[0], m[1]-x[1]) for m, x in
                zip(sorted(moved), sorted(rem))}
        print(f"moved 与 矩阵移除 的逐对偏移集合: {offs}")


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
