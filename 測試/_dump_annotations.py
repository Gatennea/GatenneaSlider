# -*- coding: utf-8 -*-
r"""临时分析：把 15 条标注样本压缩成紧凑动作表（每步 action + moved 数量 + 轨迹）"""
import json
import os
import sys

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SAMPLE = os.path.join(_PROJECT, 'save', '标注样本', 'annotations.jsonl')


def cells_set(lst):
    return set(tuple(p) for p in (lst or []))


def main():
    with open(_SAMPLE, encoding='utf-8') as f:
        eps = [json.loads(l) for l in f if l.strip()]
    print('共 %d 条 episode\n' % len(eps))
    for ep in eps:
        pz = ep['puzzle']
        st = ep['start']
        en = ep['end']
        print('==== %s  %(m)sx%(n)s step=%(step)s  void_delta=%(vd)s  phases=%(pc)s' % {
            'm': pz['m'], 'n': pz['n'], 'step': pz['step'],
            'vd': ep['void_delta'],
            'pc': json.dumps(ep['phase_counts'], ensure_ascii=False)})
        tv = cells_set(st.get('target_void'))
        ta = cells_set(st.get('target_anchor'))
        print('  start void=%s anchor=%s void_block=%s' %
              (sorted(tv), sorted(ta), st.get('void_block_count')))
        prev_a, prev_v = ta, tv
        for i, s in enumerate(ep['steps']):
            mi = s['move_info']
            rec_v = cells_set(s.get('track_void'))
            rec_a = cells_set(s.get('track_anchor'))
            moved = [tuple(p) for p in (mi.get('moved_positions') or [])]
            print('  [%d] ph=%-3s %s l=%s side=%-5s dir=%s step=%s moved=%d' %
                  (i, s.get('phase'), mi.get('gap_type'), mi.get('gap_line'),
                   mi.get('side'), mi.get('direction'), mi.get('step'),
                   len(moved)))
            if len(moved) <= 8:
                print('        moved_pos=%s' % sorted(moved))
            # 凸起/空位轨迹变化（相对上一帧）
            if rec_v != prev_v or rec_a != prev_a:
                print('        void %s -> %s' %
                      (sorted(prev_v), sorted(rec_v)))
                print('        anch %s -> %s' %
                      (sorted(prev_a), sorted(rec_a)))
            prev_v, prev_a = rec_v, rec_a
        print()


if __name__ == '__main__':
    main()
