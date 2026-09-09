# -*- coding: utf-8 -*-
r"""
人工标注样本有效性检查 — headless

对 save/标注样本/annotations.jsonl 里每条 episode：
    1. 从 start 的 target_anchor / target_void 出发，用当前几何算法
       （advance_anchor_cells / advance_void_cells + from 兜底保险）逐步入
       历史重放，比对每步记录值 track_anchor / track_void；
    2. 校验每步结束后凸起仍在滑块上、空位没有被错误保留在占用格。

运行：
    D:\python\python.exe 測試\_check_annotations.py
"""
import json
import os
import sys

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

from gui.annotation import (  # noqa: E402
    advance_anchor_cells, advance_void_cells, snapshot_abs_coords,
)

_SAMPLE = os.path.join(_PROJECT, 'save', '标注样本', 'annotations.jsonl')


def post_of(ep, i):
    steps = ep['steps']
    if i + 1 < len(steps):
        return steps[i + 1]['pre_matrix'], steps[i + 1]['pre_bounds']
    return ep['end']['matrix'], ep['end']['bounds']


def check_one(ep):
    eid = ep['episode_id']
    problems = []
    anchor = set(tuple(p) for p in (ep['start'].get('target_anchor') or []))
    void = set(tuple(p) for p in (ep['start'].get('target_void') or []))
    filled_total = reselect_a = reselect_v = 0
    for i, st in enumerate(ep['steps']):
        pre_m, pre_b = st['pre_matrix'], st['pre_bounds']
        post_m, post_b = post_of(ep, i)
        mi = st['move_info']
        prev_cells = set(snapshot_abs_coords(pre_m, pre_b))
        cur_cells = set(snapshot_abs_coords(post_m, post_b))
        direction, step = mi['direction'], mi['step']
        moved = [tuple(p) for p in mi['moved_positions']]
        rec_a = set(tuple(p) for p in (st.get('track_anchor') or []))
        rec_v = set(tuple(p) for p in (st.get('track_void') or []))
        a_reset = v_reset = False
        # --- 回放（与 _ann_build_step 相同的推进逻辑 + 兜底保险）---
        new_a = [a for a in advance_anchor_cells(
            prev_cells, moved, direction, step, anchor) if a in cur_cells]
        new_v, filled, _status = advance_void_cells(
            prev_cells, cur_cells, moved, mi['gap_type'], mi['gap_line'],
            direction, step, void)
        filled_total += filled
        if set(new_a) != rec_a:
            # 允许「人工重选凸起」：新记录点必须都在 pre 的滑块上
            if rec_a and rec_a.issubset(prev_cells):
                anchor = rec_a          # 以记录为准接力
                reselect_a += 1
                a_reset = True
            else:
                problems.append('step%d anchor 记录%s 回放%s'
                                % (i, sorted(rec_a), sorted(set(new_a))))
        if (set(new_v) if new_v else set()) != rec_v:
            # 允许「人工重选空位」：新记录点必须都在 pre 的空位上
            if rec_v and not rec_v.intersection(prev_cells):
                void = rec_v            # 以记录为准接力
                reselect_v += 1
                v_reset = True
            else:
                problems.append('step%d void 记录%s 回放%s'
                                % (i, sorted(rec_v),
                                   sorted(set(new_v) if new_v else set())))
        # --- 结束后位置合法性（绝对坐标直接判定，含窗外格）---
        for a in rec_a:
            if a not in cur_cells:
                problems.append('step%d anchor%s 结束后不在滑块上' % (i, a))
        for v in rec_v:
            if v in cur_cells:
                problems.append('step%d void%s 结束后该格被占却仍保留' % (i, v))
        if not a_reset:
            anchor = set(new_a)
        if not v_reset:
            void = set(new_v)
    return problems, filled_total, reselect_a, reselect_v


def main():
    with open(_SAMPLE, encoding='utf-8') as f:
        eps = [json.loads(l) for l in f if l.strip()]
    total = ok = 0
    for ep in eps:
        total += 1
        problems, filled, ra, rv = check_one(ep)
        if not problems:
            ok += 1
        print('%s %-26s steps=%-2d phases=%-16s 空位填掉=%d 重选凸起=%d 重选空位=%d'
              % ('OK ' if not problems else 'BAD',
                 ep['episode_id'], len(ep['steps']),
                 json.dumps(ep['phase_counts'], ensure_ascii=False),
                 filled, ra, rv))
        for p in problems:
            print('    - ' + p)
    print('\n有效 %d/%d' % (ok, total))
    return 0 if ok == total else 1


if __name__ == '__main__':
    sys.exit(main())