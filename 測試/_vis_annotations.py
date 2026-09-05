# -*- coding: utf-8 -*-
r"""临时分析：逐步可视化指定 episode 的几何（ASCII 棋盘 + moved 标记）
用法：D:\python\python.exe 測試\_vis_annotations.py [episode_id 关键字]
"""
import json
import os
import sys

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SAMPLE = os.path.join(_PROJECT, 'save', '标注样本', 'annotations.jsonl')


def abs_cells(matrix, bounds):
    mr = bounds['min_row']
    mc = bounds['min_col']
    out = set()
    for i, row in enumerate(matrix):
        for j, v in enumerate(row):
            if v:
                out.add((i + mr, j + mc))
    return out


def draw(coords, region, moved_pre=None, mark=None):
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    if region:
        rr0, cc0 = region[0], region[1]
        if isinstance(region[2], (list, tuple)):
            rh, cw = region[2]
        else:
            rh, cw = region[2], region[3]
        rb = [rr0, rr0 + rh - 1]
        cb = [cc0, cc0 + cw - 1]
    else:
        rb = cb = []
    r0 = min(rs + rb)
    r1 = max(rs + rb)
    c0 = min(cs + cb)
    c1 = max(cs + cb)
    for r in range(r0, r1 + 1):
        line = []
        for c in range(c0, c1 + 1):
            if (r, c) in coords:
                line.append('M' if (moved_pre and (r, c) in moved_pre) else '#')
            elif mark and (r, c) in mark:
                line.append('?')
            else:
                line.append('.')
        print('    ' + ''.join(line))


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else '0022'
    with open(_SAMPLE, encoding='utf-8') as f:
        eps = [json.loads(l) for l in f if l.strip()]
    for ep in eps:
        if key not in ep['episode_id']:
            continue
        pz = ep['puzzle']
        print('======== %s  %dx%d step=%d void_delta=%d phases=%s' % (
            ep['episode_id'], pz['m'], pz['n'], pz['step'],
            ep['void_delta'], json.dumps(ep['phase_counts'], ensure_ascii=False)))
        st = ep['start']
        region = st.get('region')
        prev_cells = abs_cells(st['matrix'], st['bounds'])
        prev_v = set(tuple(p) for p in (st.get('target_void') or []))
        prev_a = set(tuple(p) for p in (st.get('target_anchor') or []))
        for i, s in enumerate(ep['steps']):
            if i + 1 < len(ep['steps']):
                post_m, post_b = ep['steps'][i + 1]['pre_matrix'], ep['steps'][i + 1]['pre_bounds']
            else:
                post_m, post_b = ep['end']['matrix'], ep['end']['bounds']
            cur = abs_cells(post_m, post_b)
            mi = s['move_info']
            moved = set(tuple(p) for p in (mi.get('moved_positions') or []))
            print('\n step%d ph=%-3s gap=%s l=%s side=%-5s dir=%s moved=%d'
                  % (i, s.get('phase'), mi.get('gap_type'), mi.get('gap_line'),
                     mi.get('side'), mi.get('direction'), len(moved)))
            draw(prev_cells, region, moved_pre=moved, mark=prev_v | prev_a)
            print('    --move--')
            draw(cur, region,
                 mark=set(tuple(p) for p in (s.get('track_void') or [])))
            prev_cells = cur
            prev_v = set(tuple(p) for p in (s.get('track_void') or []))
            prev_a = set(tuple(p) for p in (s.get('track_anchor') or []))
        print('\n')


if __name__ == '__main__':
    main()
