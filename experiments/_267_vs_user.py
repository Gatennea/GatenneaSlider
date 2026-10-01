# 2-6-7：求解器9步 vs 用户手解前9步 对比 + 关键局面的洞完美性
import sys
sys.path.insert(0, '.')

from solver.ml.fill_macro import build_game, gcoords, _replay_apply
from solver.ml.gap_solver import solve_gap_macro, window_of
from experiments._conj_relay import load_start
from experiments._paste_setup import gaps_of


def moved_seq(f):
    d = __import__('json').load(open(f, encoding='utf-8'))
    frames = []
    for s in d['history']['snapshots']:
        b = s['bounds']
        coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                           for i, row in enumerate(s['matrix'])
                           for j, v in enumerate(row) if v)
        frames.append(coords)
    out = []
    for i in range(1, len(frames)):
        out.append((frames[i - 1] - frames[i], frames[i] - frames[i - 1]))
    return out


m, n, step, coords = load_start('save/2-6-7-20261001-161826.json', 0)
user = moved_seq('save/2-6-7-20261001-161826.json')
res = solve_gap_macro(build_game(coords, m, n), step)
g = build_game(coords, m, n)
acts = [tuple(a) + ((tuple(res['rep_cells'][i]),) if res['rep_cells'][i]
                    else (None,)) for i, a in enumerate(res['actions'])]
_replay_apply(g, acts, m, n, step)
print('求解器 partial %d 步；用户手解 %d 步' % (len(acts), len(user)))
print('\n求解器9步 与 用户前9步 逐步对比（frm/to 差集是否一致）：')
for i in range(min(9, len(user))):
    uf, ut = user[i]
    sf, st = gcoords(build_game(coords, m, n)), None
    # 求解器逐步差集：重建
    g2 = build_game(coords, m, n)
    sf_before = gcoords(g2)
    _replay_apply(g2, acts[:i], m, n, step)
    sf_before = gcoords(g2)
    _replay_apply(g2, acts[i:i + 1], m, n, step)
    sf_after = gcoords(g2)
    same = (sf_before - sf_after) == uf and (sf_after - sf_before) == ut
    print('  步%d: %s' % (i + 1, '一致' if same else '不同'))
    if not same:
        break

# 关键局面的洞完美性
print('\n关键局面的洞完美性：')
d = __import__('json').load(open('save/2-6-7-20261001-161826.json',
                                 encoding='utf-8'))
frames = []
for s in d['history']['snapshots']:
    b = s['bounds']
    frames.append(frozenset((b['min_row'] + i, b['min_col'] + j)
                            for i, row in enumerate(s['matrix'])
                            for j, v in enumerate(row) if v))
for k in (0, 8, 9, 16, 17, 26):
    if k >= len(frames):
        continue
    c = frames[k]
    _r, ov, holes, outside = window_of(c, m, n, step)
    info = []
    for h in sorted(holes):
        gaps = gaps_of(c, h)
        info.append('%s%s' % (h, '(缺%s)' % gaps if gaps else '(完美)'))
    print('  第%2d步后 ov=%d 洞: %s' % (k, ov, '  '.join(info)))
