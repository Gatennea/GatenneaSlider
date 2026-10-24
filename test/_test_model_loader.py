# -*- coding: utf-8 -*-
"""模型文件加载器：与代码实现逐项对拍 + 坏模型必须被拒。

对拍口径（不用「能不能造出来」这种弱判据）：
  · 还原态块键集合完全相同；
  · 合法移动数相同（碎三角 48）；
  · 逐族缝线条数相同（h/v/d150 各 3，d30/d60/d120 各 1）；
  · 加载器给的 cell_polygon 与代码 `_polygon_at` 的平面多边形逐块一致。

跑法：``PYTHONPATH=. python -u test/_test_model_loader.py``
"""
import copy
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from engine.board import Board
from engine.model_loader import ModelError, load_file, load_model, read_json
from engine.registry import make_board
from engine.shatter_geometry import _polygon_at

MODEL_PATH = os.path.join(_PROJ, 'models', 'shatter.json')
_FAILS = []


def check(cond, label, extra=''):
    tag = 'OK  ' if cond else 'FAIL'
    print(f'[{tag}] {label}' + (f'  （{extra}）' if extra else ''))
    if not cond:
        _FAILS.append(label)


def test_equivalence():
    print('\n== T1 文件版 ≡ 代码版 ==')
    m = load_file(MODEL_PATH)
    board = Board(m.spec, m.spec.goal_blocks)
    ref = make_board('shatter')

    check(len(board.blocks) == 48, '还原态 48 块', f'{len(board.blocks)} 块')
    check(board.keys == ref.keys, '块键集合与代码完全相同')

    got = len(board.legal_moves(1))
    want = len(ref.legal_moves(1))
    check(got == want == 48, '合法移动数一致', f'文件 {got} / 代码 {want}')

    per = []
    for fam in m.spec.seam_families:
        rf = next(g for g in ref.spec.seam_families if g.name == fam.name)
        a = len(m.spec.seam_lines(board, fam))
        b = len(ref.spec.seam_lines(ref, rf))
        per.append((fam.name, a, b))
    check(all(a == b for _n, a, b in per), '逐族缝线条数一致',
          '、'.join(f'{n}={a}' for n, a, b in per))

    diff = 0
    for blk in board.blocks:
        mine = sorted((round(x, 6), round(y, 6))
                      for x, y in m.spec.cell_polygon(blk.point, blk.orient))
        refp = sorted((round(x, 6), round(y, 6))
                      for x, y in _polygon_at(blk.point, blk.orient))
        if mine != refp:
            diff += 1
    check(diff == 0, 'cell_polygon 与代码多边形逐块一致', f'不一致 {diff} 块')


def test_group_field():
    print('\n== T2 放置表能带捆绑组号 ==')
    doc = copy.deepcopy(read_json(MODEL_PATH))
    doc['tiles'][0]['g'] = 7
    m = load_model(doc)
    gid = next(b.group for b in m.spec.goal_blocks
               if (b.point, b.orient) == (tuple(doc['tiles'][0]['p']),
                                          doc['tiles'][0]['o']))
    check(gid == 7, 'tiles[].g 落到 Block.group', f'group={gid}')


def test_rejects():
    print('\n== T3 坏模型必须被拒 ==')
    base = read_json(MODEL_PATH)

    def expect(mutate, label, keyword=''):
        doc = copy.deepcopy(base)
        mutate(doc)
        try:
            load_model(doc)
        except ModelError as e:
            ok = keyword in str(e) if keyword else True
            check(ok, label, str(e)[:60])
            return
        check(False, label, '没有被拒绝')

    expect(lambda d: d.__setitem__('schema', 'nope'), '陌生 schema 被拒', 'schema')
    expect(lambda d: d.pop('basis'), '缺 basis 被拒', 'basis')
    expect(lambda d: d.__setitem__('basis', [[1, 0], [2, 0]]),
           '退化 basis 被拒', '退化')
    expect(lambda d: d['tiles'].append(dict(d['tiles'][0])),
           '重复放置被拒', '重复')
    expect(lambda d: d['tiles'][0].__setitem__('o', '不存在'),
           '未定义朝向被拒', '未定义')
    expect(lambda d: d['seams'][0].__setitem__('step', [0, 0]),
           '零步长被拒', '零向量')
    expect(lambda d: d['seams'][0].__setitem__('step', [1, 1]),
           '步长不沿缝被拒', '正交')
    expect(lambda d: d['orientations']['1'].__setitem__('off', [[0, 0]]),
           '顶点不足被拒', '≥3')
    expect(lambda d: d['tiles'][0].__setitem__('g', -1),
           '负组号被拒', '非负')


if __name__ == '__main__':
    test_equivalence()
    test_group_field()
    test_rejects()
    print()
    if _FAILS:
        print(f'FAILED ({len(_FAILS)}): ' + '; '.join(_FAILS))
        sys.exit(1)
    print('ALL PASS')
