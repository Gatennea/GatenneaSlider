# -*- coding: utf-8 -*-
"""防偏移（anti-drift）：利用「聚攏目標平移不變」的對稱性，把滑動序列改寫成
視覺居中的等價序列；或計算每步質心偏移供顯示時抵消。

前提（solver/ml/invariants.profile_defect 與 auto_solver._phi_of 已確認）：
* 聚攏成功判據只認「形狀」，與絕對位置無關（Φ=0 ⟺ 還原，平移不變）。
* 整盤（含空格）整體平移 v 是規則的對稱：平移後的每一步滑動在原盤都有對應
  的合法滑動。因此一段序列可整體重標籤而不改其相對解——這正是魔方「整體轉體
  可消去」在本謎題的對應（整體平移 = 整體轉體，是零代價的對稱分量）。

兩種用法（都不增不減步數）：
* 顯示抵消（零風險，主路）：逐幀把質心偏移扣掉，質心鎖在初始位置；只動相機，
  不動解法、不動盤面（見 GUI._anti_drift_recenter）。
* 序列改寫（可複用 / 存檔）：把「初始盤面」與「每步 act」按累積質心偏移的負值
  整體平移，得到自洽、居中、步數相同的序列（transform_sequence_square）。
  方形網格坐標為整數，質心偏移可能是分數——取整四捨五入後殘差 ≤ 0.5 格，
  相對排列不變；顯示抵消用浮點相機，精確無殘差。
"""
from solver.ml.fill_macro import build_game, _replay_apply


def centroid_offset(coords):
    """coords: iterable of (r, c[, ...])。回傳平均位置（質心，浮點）。"""
    s = None
    n = 0
    for p in coords:
        if s is None:
            s = [float(x) for x in p]
        else:
            for i, v in enumerate(p):
                s[i] += float(v)
        n += 1
    if n == 0:
        return None
    return tuple(x / n for x in s)


def drift_offsets(initial_coords, transitions):
    """transitions: list of 盤面（frozenset/set of coords）在每步之後的狀態。
    回傳長度 len(transitions)+1 的列表，offsets[i] = 質心_i − 質心_0。
    offsets[0] = 全 0。顯示時把 offsets[i] 從第 i 步的渲染位置扣掉即可鎖質心。
    """
    c0 = centroid_offset(initial_coords)
    out = [tuple(0.0 for _ in c0)]
    for st in transitions:
        c = centroid_offset(st)
        out.append(tuple(a - b for a, b in zip(c, c0)))
    return out


def translate_act_square(act, vec):
    """方形 act=(gap,line,side,d[,rep...]) 整體平移 vec=(vr,vc)：
    gap=='h' 的縫是「行」，line 沿行號 +vr；'v' 是「列」，+vc；rep 整體平移。
    結構量 gap/side/d 不變。
    """
    vr, vc = vec[0], vec[1]
    gap, line, side, d = act[0], act[1], act[2], act[3]
    line2 = line + (vr if gap == 'h' else vc)
    tail = tuple(act[4:])
    if tail and tail[0] is not None:
        rep = tail[0]
        new_rep = tuple(r + v for r, v in zip(rep, (vr, vc)))
        return (gap, line2, side, d, new_rep) + tuple(tail[1:])
    return (gap, line2, side, d) + tail


def transform_sequence_square(initial_coords, acts4, reps, m, n, step):
    """把 (初始盤面, 4元組act, 平行rep) 改寫成質心居中的自洽序列。

    回傳 (initial_coords, shifted_acts4, shifted_reps, per_step_offsets)。
      · initial_coords 不動（d0=0，初始即居中）。
      · shifted_acts4[i] 是 act i 整體平移 per_step_offsets[i] 後的結果。
      · per_step_offsets[i] 是「第 i 步之前」的累積質心偏移（整數四捨五入）；
        回放時須在播第 i 步前把盤面整體平移 (offsets[i] − offsets[i-1]) 才自洽。

    證明：在「初始盤面逐幀按 offsets 重平移」的盤上回放 shifted 序列，終態 =
    原終態平移 −offsets[k]（k=步數），故終態質心 == 原初態質心（居中）。
    可複用於 headless 批處理 / 存檔；GUI 主路直接用顯示抵消（見
    GUI._anti_drift_recenter），不走本函數的盤面重平移。
    """
    g = build_game(initial_coords, m, n)
    states = [frozenset(initial_coords)]
    for i, a in enumerate(acts4):
        rep = reps[i] if (reps and i < len(reps) and reps[i]) else None
        a5 = tuple(a) + ((tuple(rep),) if rep else (None,))
        if not _replay_apply(g, [a5], m, n, step):
            return initial_coords, acts4, reps, [tuple(0 for _ in (0, 0))] * (len(acts4) + 1)
        states.append(frozenset(tuple(b.location) for b in g.blocks))
    c0 = centroid_offset(initial_coords)
    per_step = [tuple(0 for _ in c0)]
    for st in states[1:]:
        c = centroid_offset(st)
        per_step.append(tuple(ci - b for ci, b in zip(c, c0)))
    shifted_acts, shifted_reps = [], []
    for i, a in enumerate(acts4):
        # 負向平移：把第 i 步整體平移 −per_step[i]（與回放時「每步後再平移
        # per_step[i]−per_step[i+1]」配合，累積恰好把終態質心拉回初態）。
        veci = tuple(-int(round(x)) for x in per_step[i])
        sh = translate_act_square(a, veci)
        shifted_acts.append(tuple(sh[:4]))
        shifted_reps.append(sh[4] if len(sh) > 4 else None)
    return initial_coords, shifted_acts, shifted_reps, per_step
