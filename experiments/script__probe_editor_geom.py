# -*- coding: utf-8 -*-
"""editor_geom 探针 v5：吸附 + 缝族推导 + 与引擎三角 preset 深度对拍。

对拍口径（v3→v5 的认知修正，全部有 preset 引擎真值背书）：
1. 族比较按「coeffs、step 符号各自独立归一」后的集合：加载器把 step
   规范成 (step, -step) 对，侧判定双面都枚举，故两者符号都不载语义；
   族名是板型本地词汇（preset h/p/n vs 编辑器 h/d60/d120），不比。
2. **物理移动集**对拍：preset 的 up/down 键译成编辑器的 a/b，比较
   (direction, moved) 集合。v3 只比数量（12=12）是巧合——朴素锚点
   rank 会把 ▲(0,0)/▼(0,0) 划进同侧，选出错误的块片；编辑器一律挂
   centroid rank（model_loader._centroid_rank），与 preset 的
   「h/p 朴素 + n 挂钩子」逐项等价。
3. 冻形/移动形都以 preset 引擎（Board(tri_spec.spec, blocks)）为真值：
   · 2×1 菱形条带 = 冻形（preset 0 移）→ 推零族才对；
   · 5 块「三连+挂」= 4 移（p×2 + n×2）→ 推导结果须逐项相符。
"""
import sys
sys.path.insert(0, '.')

from engine import editor_geom as eg
from engine.board import Block, Board
from engine.model_loader import SCHEMA_BOARD, load_model
from engine.registry import make_board

fails = []


def check(cond, msg):
    print(('  ok  ' if cond else '  FAIL') + ' ' + msg)
    if not cond:
        fails.append(msg)


def _sign_norm(v):
    """向量符号规范：首个非零分量为正。"""
    if v[0] < 0 or (v[0] == 0 and v[1] < 0):
        return (-v[0], -v[1])
    return v


def canon_fam(cf, st):
    """(coeffs, step) → 符号各自独立归一（加载后同一族）。"""
    return (_sign_norm(cf), _sign_norm(st))


def editor_board(blocks, orientations, fams):
    """按 (name, coeffs, step) 族列表建编辑器通道棋盘（centroid rank）。"""
    doc = {
        'schema': SCHEMA_BOARD, 'name': '_probe',
        'basis': [list(r) for r in eg.TRI_BASIS], 'pos_scale': 1,
        'orientations': {lb: {'shape': 'x', 'off': [list(v) for v in offs]}
                         for lb, offs in orientations.items()},
        'tiles': [{'p': list(b.point), 'o': b.orient, 'g': 0} for b in blocks],
        'seams': [{'name': nm, 'coeffs': list(cf), 'step': list(st),
                   'rank': 'centroid'}
                  for nm, cf, st in fams],
    }
    return Board(load_model(doc).spec, tuple(blocks))


def physical_moves(board, keymap=None):
    """移动的物理内容：(direction, 排序后的 moved 键集合)。"""
    out = set()
    for m in board.legal_moves(1):
        moved = tuple(sorted((keymap(k) if keymap else k) for k in m.moved))
        out.add((m.direction, moved))
    return out


tri = [(0, 0), (1, 0), (0, 1)]
imgs = eg.d6_images(tri)
labels = {'a': imgs[0], 'b': imgs[1]}
print('images:', [list(map(list, im)) for im in imgs])

print('== 贴边吸附 ==')
placed = {((0, 0), 'a'): imgs[0]}
mid = ((eg.to_plane((1, 0))[0] + eg.to_plane((0, 1))[0]) / 2,
       (eg.to_plane((1, 0))[1] + eg.to_plane((0, 1))[1]) / 2)
cands = eg.snap_candidates(imgs, placed, mid, max_dist=1.0)
check(bool(cands), '斜边中点附近有候选')
if cands:
    p, idx, poly, dist = cands[0]
    vs = {tuple(round(c, 9) for c in v) for v in poly}
    want = {tuple(round(c, 9) for c in eg.to_plane(v))
            for v in ((1, 0), (0, 1), (1, 1))}
    check(vs == want and p == (0, 0), f'斜边 → ▼ 贴上（p={p}, dist={dist:.3f}）')
    check(dist < 0.05, f'候选紧贴点击点（dist={dist:.4f}）')
cands = eg.snap_candidates(imgs, placed, (0.5, 0.0), max_dist=1.0)
if cands:
    p, idx, poly, dist = cands[0]
    vs = {tuple(round(c, 9) for c in v) for v in poly}
    want = {tuple(round(c, 9) for c in eg.to_plane(v))
            for v in ((0, 0), (1, 0), (1, -1))}
    check(vs == want and p == (0, -1), f'底边 → ▼ 贴下（p={p}）')

print('== 与引擎三角 preset 对拍（k=3 实心三角）==')
preset = make_board('tri', k=3)
pkeys = sorted(preset.keys)
blocks = [Block(p, 'a' if o == 'up' else 'b', 0) for (p, o) in pkeys]
mine = set()
for b in blocks:
    vs = tuple(sorted(tuple(round(c, 9) for c in v)
                      for v in eg.poly_of(b.point, labels[b.orient])))
    mine.add(vs)
theirs = set()
for k in pkeys:
    vs = tuple(sorted(tuple(round(c, 9) for c in v)
                      for v in preset.spec.cell_polygon(k[0], k[1])))
    theirs.add(vs)
check(mine == theirs, f'平面多边形集合相等（我 {len(mine)} / preset {len(theirs)}）')
check(eg.is_connected(blocks, labels), '单一连通')

fams = eg.derive_families(blocks, labels)
print('   推出:', [(nm, cf, st, n) for nm, cf, st, n in fams])
print('   preset:', [(f.name, f.coeffs, f.parallel[0]) for f in preset.spec.seam_families])
my_fs = {canon_fam(cf, st) for _nm, cf, st, _n in fams}
pre_fs = {canon_fam(f.coeffs, f.parallel[0]) for f in preset.spec.seam_families}
check(my_fs == pre_fs, '缝族（符号各自归一）集合相等')

km = lambda k: (k[0], 'a' if k[1] == 'up' else 'b')
pre_moves = physical_moves(preset, km)
# 我的棋盘本身就是 a/b 键，**不能再套 km**（v5 曾误套，'a' 全被翻成 'b'）
my_moves = physical_moves(editor_board(blocks, labels,
                                       [(nm, cf, st) for nm, cf, st, _n in fams]))
check(my_moves == pre_moves,
      f'物理移动集相等（我 {len(my_moves)} / preset {len(pre_moves)}）')
if my_moves != pre_moves:
    print('     仅 preset 有:', sorted(pre_moves - my_moves)[:3])
    print('     仅我有    :', sorted(my_moves - pre_moves)[:3])


def snap_build(click_seq):
    """从 ▲(0,0) 起按点击序列贴边摆放，返回 [(p, label), ...]。"""
    placed = {((0, 0), 'a'): imgs[0]}
    out = [((0, 0), 'a')]
    for click in click_seq:
        got = None
        for p, idx, poly, dist in eg.snap_candidates(imgs, placed, click,
                                                     max_dist=1.5):
            lb = 'a' if idx == 0 else 'b'
            if (p, lb) in placed:
                continue
            got = (p, lb)
            break
        if got is None:
            break
        p, lb = got
        placed[(p, lb)] = imgs[idx]
        out.append((p, lb))
    return out


def differential(name, seq, expect_n):
    """吸附搭建 → 推导缝族 → 与 preset 引擎同形状全量差分。"""
    print(f'== {name} ==')
    built = snap_build(seq)
    blocks = [Block(p, 'a' if lb == 'a' else 'b', 0) for p, lb in built]
    check(len(blocks) == expect_n,
          f'摆了 {expect_n} 块（实际 {len(blocks)}）')
    print('   块:', [(b.point, b.orient) for b in blocks])
    check(eg.is_connected(blocks, labels), '单一连通')
    # preset 真值（同形状）
    pblocks = [Block(p, 'up' if lb == 'a' else 'down', 0)
               for (p, lb) in built]
    pboard = Board(make_board('tri', k=3).spec, tuple(pblocks))
    pre_live = {canon_fam(f.coeffs, f.parallel[0])
                for f in make_board('tri', k=3).spec.seam_families
                if any(m.family == f.name for m in pboard.legal_moves(1))}
    fams = eg.derive_families(blocks, labels)
    my_fs = {canon_fam(cf, st) for _nm, cf, st, _n in fams}
    print('   推出族:', sorted(my_fs), '  preset 活族:', sorted(pre_live))
    check(my_fs == pre_live, '活族集合与 preset 一致')
    if fams:
        my_moves = physical_moves(editor_board(blocks, labels,
                                               [(nm, cf, st)
                                                for nm, cf, st, _n in fams]))
    else:
        my_moves = set()   # 零族 = 永冻（加载器拒绝空 seams，正合语义）
    pre_moves = physical_moves(pboard, km)
    check(my_moves == pre_moves,
          f'物理移动集相等（我 {len(my_moves)} / preset {len(pre_moves)}）')
    if my_moves != pre_moves:
        print('     仅 preset 有:', sorted(pre_moves - my_moves)[:3])
        print('     仅我有    :', sorted(my_moves - pre_moves)[:3])


# 2×1 菱形条带：preset 真值 = 冻形（0 移）→ 应推零族
differential('2×1 菱形条带（冻形，preset 0 移）',
             [(1.25, 0.4330127018922193), (1.75, 0.4330127018922193),
              (2.25, 0.4330127018922193)], 4)
# 5 块三连+挂：preset 真值 = 4 移（p×2 + n×2）
#   ▲(0,0) → ▼(0,0)（右上斜边）→ ▲(0,1)（▼ 顶边）→ ▼(0,1)（▲ 右上斜边）
#   → ▲(1,0)（▼(0,0) 右边）
differential('5 块三连+挂（preset 4 移）',
             [(0.75, 0.4330127018922193), (1.0, 0.8660254037844386),
              (0.75, 1.299038105676658), (1.25, 0.4330127018922193)], 5)

print('== 30-60-90 十二朝向贴 4 块 ==')
half = [(0, 0), (2, 0), (1, 1)]
imgs_half = eg.d6_images(half)
best = 0
for start in range(12):
    pl = {((0, 0), start): imgs_half[start]}
    for _ in range(3):
        cand = None
        for p, idx, poly, dist in eg.snap_candidates(
                imgs_half, pl, (3.0, 1.0), max_dist=6.0):
            if (p, idx) in pl:
                continue
            cand = (p, idx)
            break
        if cand is None:
            break
        pl[cand] = imgs_half[cand[1]]
    best = max(best, len(pl))
check(best == 4, f'30-60-90 能贴出 4 块（实际最多 {best}）')

print()
print('FAILED:', len(fails)) if fails else print('全部通过')
sys.exit(1 if fails else 0)
