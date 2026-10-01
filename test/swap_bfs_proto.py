# -*- coding: utf-8 -*-
"""紧凑盘 step 级 BFS 原型（移形换位可行性验证，2026-10-01）。

对 2-4-4-*.json 三个存档：从初始帧广搜全部合法 step 级动作
（含 k=step 和 k=2*step 距离），目标 is_solved。
合法性 = 引擎同款：逐格无碰撞 + 每个中间位置整体连通。
"""
import importlib.util
import json
import sys
import time

sys.path.insert(0, '.')
spec = importlib.util.spec_from_file_location('df', 'test/decode_frames.py')
df = importlib.util.module_from_spec(spec)
spec.loader.exec_module(df)

from solver.ml.fill_macro import build_game


def legal_moves(cur, m, n, step, area):
    """全部合法 step 级动作 [(gap,line,side,d,k,comp,rep)]，集合层模拟。"""
    rows = [r for r, _ in cur]
    cols = [c for _, c in cur]
    out = []
    for gap in ('h', 'v'):
        lo = (min(rows) - step) if gap == 'h' else (min(cols) - step)
        hi = (max(rows) + step) if gap == 'h' else (max(cols) + step)
        for line in range(lo, hi + 1):
            for side in (('above', 'below') if gap == 'h'
                         else ('left', 'right')):
                if gap == 'h':
                    st = ((lambda q: q[0] <= line) if side == 'above'
                          else (lambda q: q[0] > line))
                else:
                    st = ((lambda q: q[1] <= line) if side == 'left'
                          else (lambda q: q[1] > line))
                sel = frozenset(q for q in cur if st(q))
                if not sel or sel == cur:
                    continue
                S = set(sel)
                seen_c = set()
                for q0 in sorted(S):
                    if q0 in seen_c:
                        continue
                    comp, stk = set(), [q0]
                    while stk:
                        q = stk.pop()
                        if q in comp:
                            continue
                        comp.add(q)
                        seen_c.add(q)
                        r, c2 = q
                        for nb in ((r - 1, c2), (r + 1, c2),
                                   (r, c2 - 1), (r, c2 + 1)):
                            if nb in S and nb not in comp:
                                stk.append(nb)
                    comp = frozenset(comp)
                    rest = cur - comp
                    if not rest:
                        continue
                    for d, (dr, dc) in {'w': (-1, 0), 's': (1, 0),
                                        'a': (0, -1), 'd': (0, 1)}.items():
                        for k in (step, 2 * step):
                            # 逐格：每个中间位置无碰撞且整体连通
                            ok = True
                            mv = comp
                            for _cell in range(k):
                                mv = frozenset((q[0] + dr, q[1] + dc)
                                               for q in mv)
                                if mv & rest:
                                    ok = False
                                    break
                                S2 = rest | mv
                                p0 = next(iter(S2))
                                sn = {p0}
                                stk2 = [p0]
                                while stk2:
                                    r2, c3 = stk2.pop()
                                    for nb in ((r2 - 1, c3), (r2 + 1, c3),
                                               (r2, c3 - 1), (r2, c3 + 1)):
                                        if nb in S2 and nb not in sn:
                                            sn.add(nb)
                                            stk2.append(nb)
                                if len(sn) != len(S2):
                                    ok = False
                                    break
                            if not ok:
                                continue
                            final = frozenset((q[0] + dr * k, q[1] + dc * k)
                                              for q in comp)
                            if any(not (area[0] <= r3 <= area[1]
                                        and area[2] <= c3 <= area[3])
                                   for r3, c3 in final):
                                continue
                            out.append((gap, line, side, d, k, comp,
                                        min(comp), final))
    return out


def bfs_solve(coords, m, n, step, max_nodes=200000, max_depth=16):
    area = (-2, m + 2, -2, n + 2)
    t0 = time.time()
    from collections import deque
    start = frozenset(coords)
    if build_game(start, m, n).is_solved():
        return [], {'nodes': 0, 'secs': 0}
    prev = {start: None}   # state -> (prev_state, action4+k)
    q = deque([start])
    nodes = 0
    depth = {start: 0}
    while q:
        cur = q.popleft()
        nodes += 1
        if nodes >= max_nodes or depth[cur] >= max_depth:
            break
        for gap, line, side, d, k, comp, rep, final in legal_moves(
                cur, m, n, step, area):
            nxt = cur - comp | final   # 完整新状态（非仅分量终位！）
            if nxt in prev:
                continue
            prev[nxt] = (cur, (gap, line, side, d, k, rep))
            depth[nxt] = depth[cur] + 1
            if build_game(nxt, m, n).is_solved():
                # 回溯路径
                path = []
                s = nxt
                while prev[s] is not None:
                    s, a = prev[s]
                    path.append(a)
                path.reverse()
                return path, {'nodes': nodes, 'secs': time.time() - t0,
                              'depth': len(path)}
            q.append(nxt)
    return None, {'nodes': nodes, 'secs': time.time() - t0}


for tag in ['save/2-4-4-20261001-103250.json',
            'save/2-4-4-20261001-103347.json',
            'save/2-4-4-20261001-103418.json']:
    doc = json.load(open(tag, encoding='utf-8'))
    pz = doc['puzzle']
    m, n, step = pz['m'], pz['n'], pz['step']
    co0 = df.frame_coords(doc['history']['snapshots'][0])
    path, st = bfs_solve(co0, m, n, step)
    if path is None:
        print('%s BFS失败 nodes=%d %.1fs' % (tag[-16:], st['nodes'],
                                             st['secs']))
    else:
        print('%s BFS解出 %d 步 nodes=%d %.1fs' % (tag[-16:], len(path),
                                                  st['nodes'], st['secs']))
        for a in path:
            print('   ', a)
