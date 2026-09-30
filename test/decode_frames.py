# -*- coding: utf-8 -*-
r"""帧间暴力解码：把存档 snapshots 逐帧还原成引擎动作 5 元组。

对每对相邻帧 (A → B)：枚举 缝(h/v)×线×侧 × 该侧连通分量 × 方向×距离，
满足 (A − comp) ∪ (comp+Δ) == B 的即该步动作。
用法：python test/decode_frames.py save/失败03.json
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DIRS = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}


def frame_coords(snap):
    b = snap['bounds']
    return frozenset((i + b['min_row'], j + b['min_col'])
                     for i, row in enumerate(snap['matrix'])
                     for j, v in enumerate(row) if v)


def components(S):
    S = set(S)
    out, seen = [], set()
    for p0 in sorted(S):
        if p0 in seen:
            continue
        comp, stack = set(), [p0]
        while stack:
            q = stack.pop()
            if q in comp:
                continue
            comp.add(q)
            seen.add(q)
            r, c = q
            for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if nb in S and nb not in comp:
                    stack.append(nb)
        out.append(frozenset(comp))
    return out


def decode_pair(A, B):
    """→ [(gap, line, side, dir, rep, comp)] 全部匹配（通常唯一）。"""
    res = []
    rows = [r for r, _ in A]
    cols = [c for _, c in A]
    for gap in ('h', 'v'):
        lines = (range(min(rows) - 6, max(rows) + 7) if gap == 'h'
                 else range(min(cols) - 6, max(cols) + 7))
        for line in lines:
            for side in (('above', 'below') if gap == 'h'
                         else ('left', 'right')):
                st = ((lambda p: p[0] <= line) if side == 'above' else
                      (lambda p: p[0] > line)) if gap == 'h' else \
                     ((lambda p: p[1] <= line) if side == 'left' else
                      (lambda p: p[1] > line))
                sel = frozenset(p for p in A if st(p))
                if not sel:
                    continue
                for comp in components(sel):
                    rest = A - comp
                    for d, (dr, dc) in _DIRS.items():
                        for rep in range(1, 9):
                            moved = frozenset((p[0] + dr * rep,
                                               p[1] + dc * rep)
                                              for p in comp)
                            if ((rest | moved) == B
                                    and not (moved & rest)):
                                res.append((gap, line, side, d, rep, comp))
    return res


def main():
    doc = json.load(open(sys.argv[1], encoding='utf-8'))
    snaps = doc['history']['snapshots']
    pz = doc['puzzle']
    print('puzzle m=%s n=%s step=%s, %d 帧 → %d 步'
          % (pz['m'], pz['n'], pz['step'], len(snaps), len(snaps) - 1))
    coords = [frame_coords(s) for s in snaps]
    for i in range(len(coords) - 1):
        hits = decode_pair(coords[i], coords[i + 1])
        if not hits:
            print('步%02d: ✗ 无法解码' % (i + 1))
            continue
        for gap, line, side, d, rep, comp in hits:
            rc = sorted(comp)[0]
            print('步%02d: (\'%s\',%d,\'%s\',\'%s\',%d)  comp=%d块 rep格=%s'
                  % (i + 1, gap, line, side, d, rep, len(comp), rc))


if __name__ == '__main__':
    main()
