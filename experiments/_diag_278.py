# 解剖 2-7-8 两种解法：前31步相同，第32步起分叉（多分量歧义 + setup）
import json
import sys
sys.path.insert(0, '.')

from solver.ml.fill_macro import build_game
from solver.ml.gap_solver import window_of

F_A = 'save/2-7-8-20261001-182028.json'
F_B = 'save/2-7-8-20261001-185331.json'


def load(f):
    d = json.load(open(f, encoding='utf-8'))
    m, n, step = d['puzzle']['m'], d['puzzle']['n'], d['puzzle']['step']
    snaps = d['history']['snapshots']
    frames = []
    for s in snaps:
        b = s['bounds']
        coords = frozenset(
            (b['min_row'] + i, b['min_col'] + j)
            for i, row in enumerate(s['matrix'])
            for j, v in enumerate(row) if v)
        frames.append((coords, s.get('move_info') or {}))
    return m, n, step, frames


def desc(mi):
    if not mi:
        return 'START'
    mp = [(tuple(p)) for p in mi.get('moved_positions', [])]
    rs = [p[0] for p in mp]
    cs = [p[1] for p in mp]
    return '%s%s %s %d格 r[%d,%d] c[%d,%d]' % (
        mi.get('gap_type'), mi.get('gap_line'), mi.get('direction'),
        len(mp), min(rs), max(rs), min(cs), max(cs))


def state(coords, m, n, step):
    (r0, c0, wh), ov, holes, outside = window_of(coords, m, n, step)
    return (r0, c0, wh), ov, sorted(holes), sorted(outside)


for tag, f, lo, hi in (('A', F_A, 29, 44), ('B', F_B, 29, 50)):
    m, n, step, frames = load(f)
    print('=' * 70)
    print('%s  %s  m=%d n=%d step=%d  总步=%d' % (tag, f, m, n, step, len(frames) - 1))
    for i in range(lo, min(hi, len(frames) - 1) + 1):
        coords, mi = frames[i]
        (r0, c0, wh), ov, holes, outside = state(coords, m, n, step)
        print('\n-- 执行第 %d 步: %s' % (i, desc(mi)))
        print('   执行前: 窗(%d,%d,%s) ov=%d 洞=%s 凸=%s' % (r0, c0, wh, ov, holes, outside))
    # 终局
    coords, _ = frames[-1]
    (r0, c0, wh), ov, holes, outside = state(coords, m, n, step)
    print('\n终局: ov=%d 洞=%s 凸=%s' % (ov, holes, outside))

# 前31步末（两者相同局面）：求解器停机的地方
m, n, step, frames = load(F_B)
coords, _ = frames[31]
(r0, c0, wh), ov, holes, outside = state(coords, m, n, step)
print('\n' + '=' * 70)
print('第31步后（两解共同局面，求解器停机处）: 窗(%d,%d,%s) ov=%d' % (r0, c0, wh, ov))
print('  洞=%s' % (holes,))
print('  凸=%s' % (outside,))
