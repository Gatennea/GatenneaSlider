# -*- coding: utf-8 -*-
r"""幽灵块追踪实验（失败07，2026-10-02 用户提案）。

提案：追踪空位身份前，在洞位临时放一个"幽灵块"（只在内存中），
让它跟着分量移动，追踪结束撤掉。洞的身份 = 幽灵块的实时位置。

本实验用失败07 用户手解前 6 步（(9,6)→(7,2) 的"带下移让位＋粘上接走"）
做三盘对照：
  1) 真盘：重放 6 步，验解码正确（终局应 == snap4）。
  2) 幽灵盘段A（让位/接应段）：幽灵块在 (7,2) 在场，逐步读幽灵块轨迹。
  3) 撤幽灵块后段B（填入/回位段）：验原洞位 (7,2) 被真实块占据。

设计原则（用户风险提醒后确立）：幽灵块只当追踪器、永不当裁判——
所有合法性/闸门判定在真盘重放上做；幽灵盘只用于生成动作与看轨迹。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from test.decode_frames import frame_coords, decode_pair
from solver.ml.fill_macro import build_game, _capture_apply

DIRS = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}
HOLE = (7, 2)          # 用户第一组的目标洞
N_STEPS = 6
N_SEG_A = 3            # 段A = 步1-3（让位+接应），段B = 步4-6（填入+回位）


def replay_dist(g, gap, line, side, d, dist, rep, step):
    r"""按距离拆步连滑：引擎单次 try_move 只滑 step 格，
    存档动作 dist∈1..8 → 连滑 ceil(dist/step) 次，rep 逐步更新。"""
    dr, dc = DIRS[d]
    n_slide = -(-dist // step)
    for _ in range(n_slide):
        ok, _ = _capture_apply(g, (gap, line, side, d, rep), step)
        if not ok:
            return False
        rep = (rep[0] + dr * step, rep[1] + dc * step)
    return True


def main():
    doc = json.load(open('archives/失败07.json', encoding='utf-8'))
    snaps = doc['history']['snapshots']
    pz = doc['puzzle']
    m, n, step = pz['m'], pz['n'], pz['step']
    coords0 = frame_coords(snaps[0])
    snap4 = frame_coords(snaps[4])

    # ---- 1) 解码前 6 步 → 5 元组动作（rep = 分量内任一格）----
    acts = []
    cur = coords0
    for i in range(N_STEPS):
        hits = decode_pair(cur, frame_coords(snaps[i + 1]))
        if not hits:
            print('步%d: ✗ 解码失败' % (i + 1))
            return
        gap, line, side, d, dist, comp = hits[0]
        rep = sorted(comp)[0]
        acts.append((gap, line, side, d, dist, rep))
        moved = frozenset((p[0] + DIRS[d][0] * dist, p[1] + DIRS[d][1] * dist)
                          for p in comp)
        cur = (cur - comp) | moved
        print('步%d: (\'%s\',%d,\'%s\',\'%s\') dist=%d 分量%d格 rep=%s'
              % (i + 1, gap, line, side, d, dist, len(comp), rep))

    # ---- 2) 真盘重放（无幽灵块）：合法性 + 每步看 (7,2) ----
    g = build_game(coords0, m, n)
    ok_all = True
    for i, (gap, line, side, d, dist, rep) in enumerate(acts):
        ok = replay_dist(g, gap, line, side, d, dist, rep, step)
        ok_all &= ok
        filled = any(tuple(b.location) == HOLE for b in g.blocks)
        print('真盘 步%d: ok=%s  (7,2)有块=%s' % (i + 1, ok, filled))
    final = frozenset(tuple(b.location) for b in g.blocks)
    snap6 = frame_coords(snaps[N_STEPS])
    print('真盘 6 步全合法 = %s；终局 == snap6 = %s' % (ok_all, final == snap6))
    print('snap6 == snap4 =', snap6 == snap4)
    if final != snap6:
        print('  真盘终局 - snap6 =', sorted(final - snap6)[:6],
              ' snap6 - 终局 =', sorted(snap6 - final)[:6])

    # ---- 3) 幽灵盘段A：幽灵块在 (7,2)，重放步1-3 并追踪 ----
    gg = build_game(coords0 | {HOLE}, m, n)
    ghost = [b for b in gg.blocks if tuple(b.location) == HOLE][0]
    traj = [tuple(ghost.location)]
    okA = True
    for i in range(N_SEG_A):
        gap, line, side, d, dist, rep = acts[i]
        ok = replay_dist(gg, gap, line, side, d, dist, rep, step)
        okA &= ok
        traj.append(tuple(ghost.location))
        print('幽灵盘 步%d: ok=%s  幽灵块→%s' % (i + 1, ok, tuple(ghost.location)))
    print('段A 全合法 = %s；幽灵块轨迹: %s' % (okA, ' → '.join(map(str, traj))))

    # ---- 4) 撤幽灵块，段B：验原洞位被填 ----
    mid = frozenset(tuple(b.location) for b in gg.blocks) - {tuple(ghost.location)}
    g2 = build_game(mid, m, n)
    okB = True
    for i in range(N_SEG_A, N_STEPS):
        gap, line, side, d, dist, rep = acts[i]
        ok = replay_dist(g2, gap, line, side, d, dist, rep, step)
        okB &= ok
        filled = any(tuple(b.location) == HOLE for b in g2.blocks)
        print('段B 步%d: ok=%s  (7,2)有块=%s' % (i + 1, ok, filled))
    print('段B 全合法 = %s；终局原洞位 (7,2) 被填 = %s'
          % (okB, any(tuple(b.location) == HOLE for b in g2.blocks)))
    print('段B 终局 == snap6 =',
          frozenset(tuple(b.location) for b in g2.blocks) == snap6)


if __name__ == '__main__':
    main()
