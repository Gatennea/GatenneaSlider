# -*- coding: utf-8 -*-
"""回归：防偏移改寫必須是等價（步數不變、回放自洽、終態質心回中）。

方法：用真引擎（fill_macro._Runner._do）在散盤上暴力走出一段合法 act 序列，
再用 solver.anti_drift.transform_sequence_square 改寫，然後在「初始盤面逐幀按
offsets 重平移」的盤上回放——驗三件事：
  A. 改寫後步數不變；
  B. 回放每一步都成功（自洽）；
  C. 終態排列 = 原終態平移 −offsets[k]（故終態質心 == 原初態質心，居中）。
另驗 centroid_offset / drift_offsets 基本性質。
"""
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from solver.ml.fill_macro import build_game, _replay_apply  # noqa: E402
from solver.anti_drift import (centroid_offset, drift_offsets,  # noqa: E402
                               transform_sequence_square)

_ok, _fail = [0], []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print('  ok: ' + msg)
    else:
        _fail.append(msg)
        print('  FAIL: ' + msg + ' ' + extra)
    return cond


def gen_walk(coords, m, n, step, k_moves):
    """用真引擎（g.opt/try_move/commit_move）走出 k_moves 步合法序列，
    回傳 (acts4, reps)。做法与 solver/ml/fill_macro._capture_apply 同构：
    枚举所有合法缝 + 两侧代表块 + 该缝允许的两个方向，直接用 try_move
    当合法闸门（opt 选连通分量，整片平移；碰撞/全员选中会被 try_move 拒）。
    rep = 代表块移动前位置（供 _replay_apply 精确定位）。"""
    import random
    g = build_game(coords, m, n)
    rng = random.Random(20261110)
    acts4, reps = [], []
    for _ in range(k_moves):
        bnd = g.get_boundaries()
        gaps = [('h', i) for i in range(bnd['min_row'] + 1, bnd['max_row'])
                if g.is_valid_h_line(i)]
        gaps += [('v', j) for j in range(bnd['min_col'] + 1, bnd['max_col'])
                 if g.is_valid_v_line(j)]
        rng.shuffle(gaps)
        found = False
        for gap, line in gaps:
            # 该缝两侧的块各取一个当代表；opt 会选代表块所在侧的连通分量
            if gap == 'h':
                sides = ([b for b in g.blocks if b.location[0] <= line],
                         [b for b in g.blocks if b.location[0] > line])
                ddirs = ('a', 'd')
            else:
                sides = ([b for b in g.blocks if b.location[1] <= line],
                         [b for b in g.blocks if b.location[1] > line])
                ddirs = ('w', 's')
            cands = []
            for sb in sides:
                if sb:
                    cands.append(rng.choice(sb))
            rng.shuffle(cands)
            for b in cands:
                for d in ddirs:
                    g.opt(gap, line, b)
                    sel = [bb for bb in g.blocks if bb.be_opted]
                    if len(sel) == len(g.blocks):  # 全员选中 = 废步，跳过
                        for bb in g.blocks:
                            bb.be_opted = False
                        continue
                    final = g.try_move(d, step)
                    if not final:
                        for bb in g.blocks:
                            bb.be_opted = False
                        continue
                    rep = tuple(b.location)  # 移动前位置
                    g.commit_move(final)
                    if gap == 'h':
                        side = 'above' if b.location[0] <= line else 'below'
                    else:
                        side = 'left' if b.location[1] <= line else 'right'
                    acts4.append((gap, line, side, d))
                    reps.append(rep)
                    found = True
                    break
                if found:
                    break
            if found:
                break
        if not found:
            break
    return acts4, reps


def replay_with_offsets(initial_coords, shifted_acts, shifted_reps,
                        per_step, m, n, step):
    """在「初始盤面逐幀按 offsets 重平移」的盤上回放 shifted 序列。

    與 transform_sequence_square 同構：每步先播「平移 −per_step[i] 的 act」，
    播完再把整盤平移 per_step[i]−per_step[i+1]，累積恰好把終態拉回初態質心。
    """
    g = build_game(initial_coords, m, n)
    for i, a in enumerate(shifted_acts):
        rep = shifted_reps[i]
        a5 = tuple(a) + ((tuple(rep),) if rep else (None,))
        if not _replay_apply(g, [a5], m, n, step):
            return None
        if i + 1 < len(per_step):
            cur = tuple(int(round(x)) for x in per_step[i])
            nxt = tuple(int(round(x)) for x in per_step[i + 1])
            delta = tuple(c - p for c, p in zip(cur, nxt))
            for b in g.blocks:
                b.location = [b.location[k] + delta[k]
                              for k in range(len(b.location))]
    return frozenset(tuple(b.location) for b in g.blocks)


def run():
    # 散盤：4×4 区域（m=n=4, step=1）放在偏移区，挖掉一格做洞（15-puzzle
    # 形态）——只有内部空格能滑，矩陣才覆蓋得到；洞繞跑會產生質心漂移。
    coords = frozenset((r + 6, c + 6) for r in range(4) for c in range(4)
                       if not (r == 0 and c == 0))
    m, n, step = 4, 4, 1

    acts4, reps = gen_walk(coords, m, n, step, 14)
    check(len(acts4) >= 6, '暴力走出至少 6 步合法序列', '只走出 %d 步' % len(acts4))
    if not acts4:
        print('SKIP（無法生成序列）')
        return

    # 原序列回放終態
    g0 = build_game(coords, m, n)
    orig_final = None
    for i, a in enumerate(acts4):
        rep = reps[i]
        a5 = tuple(a) + ((tuple(rep),) if rep else (None,))
        if not _replay_apply(g0, [a5], m, n, step):
            check(False, '原序列回放成功', '第 %d 步失敗' % i)
            break
    else:
        orig_final = frozenset(tuple(b.location) for b in g0.blocks)

    # 改寫
    init2, sh_acts, sh_reps, per_step = transform_sequence_square(
        coords, acts4, reps, m, n, step)
    check(len(sh_acts) == len(acts4), '改寫後步數不變',
          '%d -> %d' % (len(acts4), len(sh_acts)))

    # B. 回放自洽
    shifted_final = replay_with_offsets(
        init2, sh_acts, sh_reps, per_step, m, n, step)
    check(shifted_final is not None, '改寫序列回放自洽（每步成功）')

    if orig_final is not None and shifted_final is not None:
        k = len(acts4)
        ok_shift = per_step[k]
        expect = frozenset((p[0] - int(round(ok_shift[0])),
                            p[1] - int(round(ok_shift[1]))) for p in orig_final)
        check(shifted_final == expect, '終態排列 = 原終態平移 −offsets[k]',
              '差 %d 格' % len(shifted_final ^ expect))
        c0 = centroid_offset(coords)
        cf = centroid_offset(shifted_final)
        # 整數序列改寫路徑：取整四捨五入後殘差 ≤ 0.5 格（見 anti_drift 模塊
        # 文檔）；「精確回中」由顯示抵消（浮點相機）主路保證，不在此路。
        check(abs(cf[0] - c0[0]) <= 0.5 + 1e-6 and
              abs(cf[1] - c0[1]) <= 0.5 + 1e-6,
              '終態質心回中（整數改寫殘差 ≤ 0.5 格）',
              'c0=%s cf=%s' % (c0, cf))

    # drift_offsets 基本性質
    c0 = centroid_offset(coords)
    states = [coords]
    g = build_game(coords, m, n)
    for i, a in enumerate(acts4):
        rep = reps[i]
        a5 = tuple(a) + ((tuple(rep),) if rep else (None,))
        _replay_apply(g, [a5], m, n, step)
        states.append(frozenset(tuple(b.location) for b in g.blocks))
    offs = drift_offsets(coords, states[1:])
    check(len(offs) == len(states), 'drift_offsets 長度 = 步數+1')
    check(offs[0] == tuple(0.0 for _ in c0), 'drift_offsets[0] = 0')


if __name__ == '__main__':
    run()
    print('\n通过 %d 项，失败 %d 项' % (_ok[0], len(_fail)))
    if _fail:
        for m in _fail:
            print('  ✗', m)
        print('FAILED')
        sys.exit(1)
    print('ALL PASS')
