# -*- coding: utf-8 -*-
r"""幽灵滑块追踪 + 帧差对照 的 headless 验证（2026-10-02 重写标注追踪）

场景取自失败07 手解步1（带移让位，洞 (7,2) 随带漂移到 (9,2)）：
    旧版 advance_void_cells 在此误判「被填即完成」→ 接应段跟踪丢失；
    新版幽灵滑块应把标记跟到 (9,2)。

运行：
    C:/Users/guo/.workbuddy/binaries/python/versions/3.13.12/python.exe test/_test_ann_ghost.py
"""

import os
import sys
import json

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)
sys.path.insert(0, os.path.join(_PROJECT, 'test'))

from gui.annotation import (advance_void_cells, decode_move_candidates,
                            infer_side)
from decode_frames import frame_coords, decode_pair

_DIR_NAME = {'w': '上', 's': '下', 'a': '左', 'd': '右'}
PASS = []


def check(name, cond, detail=''):
    PASS.append(bool(cond))
    print('%s %s %s' % ('✓' if cond else '✗', name, detail))


def main():
    doc = json.load(open(os.path.join(_PROJECT, 'archives', '失败07.json'),
                         encoding='utf-8'))
    pz = doc['puzzle']
    m, n, step = pz['m'], pz['n'], pz['step']
    snaps = doc['history']['snapshots']
    coords = [frame_coords(s) for s in snaps]

    # ---- 解码手解步1（带移让位）----
    hits = decode_pair(coords[0], coords[1])
    check('07 步1 可解码', bool(hits), '候选 %d 个' % len(hits))
    gap, line, side, d, dist, comp = hits[0]
    moved = sorted(comp)
    print('  真实动作: (%s,%d,%s) %s 移 %d 格, 移动组 %d 块'
          % (gap, line, side, _DIR_NAME[d], dist, len(moved)))

    # ---- 场景1：幽灵滑块洞漂移（旧版误判 filled 的场景）----
    cells, filled, status = advance_void_cells(
        coords[0], coords[1], moved, gap, line, d, step, {(7, 2)})
    print('  跟踪结果: cells=%s filled=%d status=%s' % (cells, filled, status))
    check('让位段洞身份漂移 (7,2)→(9,2)',
          cells == [(9, 2)] and filled == 0 and status == 'ok',
          '（实验轨迹一致）')

    # ---- 场景2：普通填洞 → 被迎面填上 = 完成 ----
    prev2 = {(r, c) for r in range(5) for c in range(5)} - {(1, 1)}
    prev2 |= {(6, 1)}                       # 下方一颗送填块
    cur2 = (prev2 - {(6, 1)}) | {(1, 1)}    # 下移…用几何构造：块 (0,1)→(1,1)
    prev2 = {(r, c) for r in range(5) for c in range(5)} - {(1, 1)}
    prev2 = frozenset(prev2 | {(0, 1)} | {(6, 1)})
    # 块 (0,1) 下移 1 填 (1,1)
    cur2 = frozenset((prev2 - {(0, 1)}) | {(1, 1)})
    cells2, filled2, status2 = advance_void_cells(
        prev2, cur2, [(0, 1)], 'h', 0, 's', 1, {(1, 1)})
    print('  填洞场景: cells=%s filled=%d status=%s' % (cells2, filled2, status2))
    check('迎面填上判完成', cells2 == [] and filled2 == 1
          and status2 == 'filled')

    # ---- 场景3：帧差独立解码对照 ----
    cands = decode_move_candidates(coords[0], coords[1])
    side_real = infer_side(gap, line, moved)
    real_in = any(g == gap and ln == line and sd == side_real
                  and dd == d and rp == step
                  for g, ln, sd, dd, rp, _c in cands)
    print('  解码候选 %d 个, 真实动作在候选中 = %s'
          % (len(cands), real_in))
    check('解码候选含真实动作', real_in)
    check('07 步1 帧差唯一解释（无歧义）', len(cands) == 1,
          '候选 = %s' % [(g, ln, sd, dd, rp) for g, ln, sd, dd, rp, _c in cands])

    # ---- 场景4：连通但未被补上 → 原位保持（空隙没流动）----
    # (2,2) 单块下移1；标 (2,3)：与移动块相邻连通、但没被补上 → 洞没动
    prev4 = set()
    for r in range(4):
        prev4 |= {(r, 0), (r, 1)}
    prev4 |= {(0, 4), (1, 4), (2, 2)}
    prev4 = frozenset(prev4)
    cur4 = frozenset((prev4 - {(2, 2)}) | {(3, 2)})
    cells4, filled4, status4 = advance_void_cells(
        prev4, cur4, [(2, 2)], 'v', 1, 's', 1, {(2, 3)})
    print('  连通未补上: cells=%s filled=%d status=%s'
          % (cells4, filled4, status4))
    check('未被补上 → 原位保持（不误漂）',
          cells4 == [(2, 3)] and filled4 == 0 and status4 == 'ok')

    # ---- 场景5：v 被补上但落点被占（幽灵块桥接外块）→ filled 兜底 ----
    prev5 = {(r, c) for r in range(4) for c in (0, 1)}
    prev5 |= {(1, 2), (3, 2)}               # (1,2) 移动块、(3,2) 占落点
    prev5 = frozenset(prev5)
    cur5 = frozenset((prev5 - {(1, 2)}) | {(2, 2)})     # (1,2) 下移1 补 (2,2)
    cells5, filled5, status5 = advance_void_cells(
        prev5, cur5, [(1, 2)], 'v', 1, 's', 1, {(2, 2)})
    print('  落点被占回退: cells=%s filled=%d status=%s'
          % (cells5, filled5, status5))
    check('落点被占 → 回退被填即完成',
          cells5 == [] and filled5 == 1 and status5 == 'filled')

    print('\n%d/%d 通过' % (sum(PASS), len(PASS)))
    return 0 if all(PASS) else 1


if __name__ == '__main__':
    sys.exit(main())
