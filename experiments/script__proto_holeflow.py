# -*- coding: utf-8 -*-
"""2-6-7 残局原型：洞流 BFS（状态=盘面，边=合法单步带移，目标=可行 couple）。

验证「洞重定位」思路：不追求每步 ov 提升，只要求 ov 不降，
把洞搬到能与同 mod 凸起构成可行 couple 的位置。
"""
import json
import sys
import os
import time
from collections import deque

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import build_game, gcoords, _replay_apply  # noqa: E402
from solver.ml.gap_solver import window_of, _vacancy_couple_hook  # noqa: E402

DIRS = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}

path = os.path.join(_ROOT, 'save', '2-6-7-20261001-161826.json')
with open(path, encoding='utf-8') as f:
    doc = json.load(f)
m, n = doc['puzzle']['m'], doc['puzzle']['n']
step = doc['puzzle']['step']
snap = doc['history']['snapshots'][0]
b = snap['bounds']
coords0 = frozenset((b['min_row'] + i, b['min_col'] + j)
                    for i, row in enumerate(snap['matrix'])
                    for j, v in enumerate(row) if v)


def comps(S):
    S = set(S)
    out, seen = [], set()
    for q0 in S:
        if q0 in seen:
            continue
        comp, stack = set(), [q0]
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


def connected(S):
    S = set(S)
    if not S:
        return False
    p0 = next(iter(S))
    seen, stack = {p0}, [p0]
    while stack:
        r, c = stack.pop()
        for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if nb in S and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen) == len(S)


def legal_steps(cur, step):
    """全部合法 step 单步 → [(act5, nxt)]。不剪分量大小，只剪整盘平移。"""
    out = []
    rows = [r for r, _c in cur]
    cols = [c for _r, c in cur]
    for gap in ('h', 'v'):
        lines = (range(min(rows) - 2, max(rows) + 3) if gap == 'h'
                 else range(min(cols) - 2, max(cols) + 3))
        for line in lines:
            for side in (('above', 'below') if gap == 'h'
                         else ('left', 'right')):
                if gap == 'h':
                    st = (lambda q: q[0] <= line) if side == 'above' \
                        else (lambda q: q[0] > line)
                else:
                    st = (lambda q: q[1] <= line) if side == 'left' \
                        else (lambda q: q[1] > line)
                sel = frozenset(q for q in cur if st(q))
                if not sel or sel == cur:
                    continue
                for comp in comps(sel):
                    rest = cur - comp
                    if not rest:
                        continue          # 整盘平移剪枝
                    rep = min(comp)
                    for d, (dr, dc) in DIRS.items():
                        ok = True
                        for k in range(1, step + 1):
                            mv_k = frozenset((q[0] + dr * k, q[1] + dc * k)
                                             for q in comp)
                            if mv_k & rest or not connected(rest | mv_k):
                                ok = False
                                break
                        if not ok:
                            continue
                        nxt = frozenset((q[0] + dr * step, q[1] + dc * step)
                                        for q in comp) | rest
                        out.append(((gap, line, side, d, rep), nxt))
    return out


hook = _vacancy_couple_hook(False)


def couples_ok(cur):
    """当前局面的可行 couple 动作（hook+回放+闸门）。"""
    _reg, _ov, holes, outside = window_of(cur, m, n, step)
    for h in holes:
        for p in outside:
            if (p[0] - h[0]) % step or (p[1] - h[1]) % step:
                continue
            acts, _s = hook(cur, m, n, step, h, p)
            if acts is None:
                continue
            g2 = build_game(cur, m, n)
            if _replay_apply(g2, acts, m, n, step):
                from solver.ml.fill_macro import _overlap_raised
                if _overlap_raised(cur, m, n, step, acts):
                    return acts
    return None


# ---- 起点：9 步后的 ov40 残局 ----
acts9, _st = hook(coords0, m, n, step, (0, 5), (6, 3))
g = build_game(coords0, m, n)
_replay_apply(g, acts9, m, n, step)
start = frozenset(gcoords(g))
ov0 = window_of(start, m, n, step)[1]
print('残局 ov=%d 洞数=%d' % (ov0, len(window_of(start, m, n, step)[2])))

# ---- BFS ----
t0 = time.time()
MAX_STATES, MAX_DEPTH = 400, 8
seen = {start}
prev = {start: None}          # state -> (act5, parent)
queue = deque([(start, 0)])
found = None
expanded = 0
edge_cnt = 0
while queue:
    cur, dep = queue.popleft()
    if dep >= MAX_DEPTH:
        continue
    expanded += 1
    if expanded > MAX_STATES:
        break
    r_acts = couples_ok(cur)
    if r_acts is not None:
        found = (cur, r_acts)
        break
    for act5, nxt in legal_steps(cur, step):
        edge_cnt += 1
        if nxt in seen:
            continue
        # 剪枝：ov 不降（洞流允许 ov 暂平）
        if window_of(nxt, m, n, step)[1] < ov0:
            continue
        seen.add(nxt)
        prev[nxt] = (act5, cur)
        queue.append((nxt, dep + 1))

print('BFS: 展开%d状态 / %d边 / %.1fs / found=%s'
      % (expanded, edge_cnt, time.time() - t0, found is not None))
if found is None and expanded <= MAX_STATES:
    print('深度内未找到（全部展开完毕）')

if found:
    end_state, r_acts = found
    chain = []
    s = end_state
    while prev[s] is not None:
        act5, par = prev[s]
        chain.append(act5)
        s = par
    chain.reverse()
    print('整形链 %d 步 + couple %d 步' % (len(chain), len(r_acts)))
    g2 = build_game(start, m, n)
    ok = _replay_apply(g2, chain + r_acts, m, n, step)
    print('残局回放:', ok)
    ov2 = window_of(frozenset(gcoords(g2)), m, n, step)[1]
    print('残局 ov %d → %d' % (ov0, ov2))
