# -*- coding: utf-8 -*-
"""editor_geom（搭积木编辑器几何纯逻辑）护栏。

覆盖四组不变量，全部有引擎 preset 真值背书：
1. D6 朝向生成：单位等边三角形 → 恰 2 个像（▲/▼），与三角谜题实际
   朝向数一致。
2. 贴边吸附：候选 = 新块某条边**整条**贴上已有块某条边（两端点分别
   相等）；共边相切保留、正面积重叠滤掉。**边表必须用物理整数顶点**
   （point + offs）——局部 offs 等于假设所有块锚在原点，贴到非原点
   块时会凭空造出/漏掉候选（v4 探针抓到的真 bug）。
3. 缝族推导：primitive 步长 + centroid rank（model_loader._centroid_rank
   的理由），与 tri preset 的「h/p 朴素 + n 挂钩子」逐项等价——
   k=3 实心三角上**物理移动集 12/12 全等**（只比数量会漏：朴素锚点
   rank 把 ▲(0,0)/▼(0,0) 划进同侧，数量仍是 12 但块片选错）。
4. 冻形识别：2×1 菱形条带 preset 真值 0 移 → 推零族；5 块三连+挂
   preset 真值 4 移（p×2 + n×2）→ 活族与移动集逐项相等。
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
    if v[0] < 0 or (v[0] == 0 and v[1] < 0):
        return (-v[0], -v[1])
    return v


def canon_fam(cf, st):
    """coeffs、step 符号各自独立归一（加载后同一族）。"""
    return (_sign_norm(cf), _sign_norm(st))


def editor_board(blocks, orientations, fams):
    """按 (name, coeffs, step) 族列表建编辑器通道棋盘（centroid rank）。"""
    doc = {
        'schema': SCHEMA_BOARD, 'name': '_t_editor_geom',
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


def snap_build(images, click_seq):
    """从第 0 个朝向 @ (0,0) 起按点击序列贴边摆放。"""
    placed = {((0, 0), 0): images[0]}
    out = [((0, 0), 0)]
    for click in click_seq:
        got = None
        for p, idx, poly, dist in eg.snap_candidates(images, placed, click,
                                                     max_dist=1.5):
            if (p, idx) in placed:
                continue
            got = (p, idx)
            break
        if got is None:
            break
        placed[got] = images[got[1]]
        out.append(got)
    return out


def differential(name, images, labels, seq, expect_n):
    """吸附搭建 → 推导缝族 → 与 preset 引擎同形状全量差分。"""
    print(f'== {name} ==')
    built = snap_build(images, seq)
    blocks = [Block(p, 'a' if idx == 0 else 'b', 0) for p, idx in built]
    check(len(blocks) == expect_n, f'摆了 {expect_n} 块（实际 {len(blocks)}）')
    check(eg.is_connected(blocks, labels), '单一连通')
    spec = make_board('tri', k=3).spec
    pblocks = [Block(p, 'up' if idx == 0 else 'down', 0)
               for p, idx in built]
    pboard = Board(spec, tuple(pblocks))
    pre_live = {canon_fam(f.coeffs, f.parallel[0])
                for f in spec.seam_families
                if any(m.family == f.name for m in pboard.legal_moves(1))}
    fams = eg.derive_families(blocks, labels)
    my_fs = {canon_fam(cf, st) for _nm, cf, st, _n in fams}
    print('   推出族:', sorted(my_fs), ' preset 活族:', sorted(pre_live))
    check(my_fs == pre_live, '活族集合与 preset 一致')
    if fams:
        my_moves = physical_moves(editor_board(
            blocks, labels, [(nm, cf, st) for nm, cf, st, _n in fams]))
    else:
        my_moves = set()   # 零族 = 永冻（加载器拒绝空 seams，正合语义）
    pre_moves = physical_moves(
        pboard, lambda k: (k[0], 'a' if k[1] == 'up' else 'b'))
    check(my_moves == pre_moves,
          f'物理移动集相等（我 {len(my_moves)} / preset {len(pre_moves)}）')
    if my_moves != pre_moves:
        print('     仅 preset 有:', sorted(pre_moves - my_moves)[:3])
        print('     仅我有    :', sorted(my_moves - pre_moves)[:3])


# ----------------------------------------------------------------------
print('== D6 朝向生成 ==')
imgs = eg.d6_images([(0, 0), (1, 0), (0, 1)])
check(len(imgs) == 2, f'单位等边三角形 → 2 个像（实际 {len(imgs)}）')
labels = {'a': imgs[0], 'b': imgs[1]}
print('   ', [list(map(list, im)) for im in imgs])

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
my_fs = {canon_fam(cf, st) for _nm, cf, st, _n in fams}
pre_fs = {canon_fam(f.coeffs, f.parallel[0]) for f in preset.spec.seam_families}
check(my_fs == pre_fs, '缝族（符号各自归一）集合相等')
my_moves = physical_moves(editor_board(
    blocks, labels, [(nm, cf, st) for nm, cf, st, _n in fams]))
pre_moves = physical_moves(preset, lambda k: (k[0],
                                              'a' if k[1] == 'up' else 'b'))
check(my_moves == pre_moves,
      f'物理移动集相等（我 {len(my_moves)} / preset {len(pre_moves)}）')
if my_moves != pre_moves:
    print('     仅 preset 有:', sorted(pre_moves - my_moves)[:3])
    print('     仅我有    :', sorted(my_moves - pre_moves)[:3])

# 吸附搭建的两个形状（preset 真值：条带冻形 0 移；三连+挂 4 移）
differential('2×1 菱形条带（冻形，preset 0 移）', imgs, labels,
             [(1.25, 0.4330127018922193), (1.75, 0.4330127018922193),
              (2.25, 0.4330127018922193)], 4)
differential('5 块簇（preset 4 移）', imgs, labels,
             [(0.75, 0.4330127018922193), (1.0, 0.8660254037844386),
              (0.75, 1.299038105676658), (1.25, 0.4330127018922193)], 5)

print('== 连通判定必须用物理顶点 ==')
# 2026-10-25 真 bug 的护栏：is_connected 曾拿锚点相对的 offs 当顶点，
# 于是「两块锚点不同、offs 相同」被误判成同一块的两个副本 → 不连通的盘
# 恒判连通，编辑器保存门的连通检查整个失效。
_imgs_tri = eg.d6_images([(0, 0), (1, 0), (0, 1)])
_lbl = {f'x:{i}': im for i, im in enumerate(_imgs_tri)}
_one = [Block((0, 0), 'x:0')]
_two_far = [Block((0, 0), 'x:0'), Block((3, 9), 'x:0')]
_two_adj = [Block((0, 0), 'x:0'), Block((0, 0), 'x:1')]
check(eg.is_connected(_one, _lbl), '单块应判连通')
check(eg.is_connected(_two_adj, _lbl), '共边相邻两块应判连通')
check(not eg.is_connected(_two_far, _lbl),
      '相距 (0,0)/(3,9) 的两块必须判不连通（锚点相对顶点曾让它恒真）')
check(not eg.is_connected([], _lbl), '空盘应判不连通')

print('== 30-60-90 十二朝向 ==')
imgs_half = eg.d6_images([(0, 0), (2, 0), (1, 1)])
best = 0
for start in range(len(imgs_half)):
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
check(best == 4, f'每个起始朝向都能贴出 4 块（实际最多 {best}）')

print()
print('FAILED:', len(fails)) if fails else print('全部通过')
sys.exit(1 if fails else 0)
