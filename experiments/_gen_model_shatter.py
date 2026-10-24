# -*- coding: utf-8 -*-
"""从现有碎三角代码生成模型文件（models/shapes.json + models/shatter.json）。

**为什么用生成**：48 条放置表 × 24 朝向，手写必错；生成后脚本自己回头重建
并逐块比对，比对通过才落盘。

**坐标（第一版：直译，不做基变换）**
  · 代码的顶点整数格 (kx, my) → 平面 = (kx·√3/2, my/2)，即 basis
    [[√3/2, 0], [0, 1/2]]。
  · 块位置 p = 三顶点之和 = 3×质心（三角形质心带 1/3，故存 3× 保证整数）。
  · 每个朝向记 `off` = 3×(顶点 − 质心) = 3·顶点 − p，整数偏移。
  · 于是 顶点 = (p + off) / 3，`pos_scale = 3`。

⚠️ 第一版**不**把朝向压成「形状 + 角度 + 镜像」。压缩要求坐标系等距
（旋转 60° 才是格的线性自同构），而 (kx,my) 格是 30° 旋转过的矩形表示。
压缩留到 S2b 单独做、单独验证——本版只求「文件能 1:1 复现代码」。
`shapes.json` 里的两个原子形状仍给出（编辑器选形状要用），模型里的
`shape` 字段只作身份/配色提示，几何以 `off` 为准。

跑法：``PYTHONPATH=. python -u experiments/_gen_model_shatter.py``
"""
import json
import math
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from engine.registry import make_board
from engine.shatter_geometry import _block_vertices, _polygon_at

SQ3_2 = math.sqrt(3.0) / 2.0
#: 顶点格 (kx, my) → 平面
BASIS = [[SQ3_2, 0.0], [0.0, 0.5]]
#: 位置缩放：p = 3× 质心
POS_SCALE = 3

#: 原子形状（单位三角格下的整数顶点；给编辑器与形状身份用）
SHAPES = {
    'tri':   [[0, 0], [1, 0], [0, 1]],
    'iso30': [[0, 0], [1, 0], [1, 1]],
}


def shape_of(role):
    """朝向标签 → 形状名（'1'..'6' 正三角，其余 30-30-120 等腰）。"""
    base = role[1:] if role.startswith('r') else role
    return 'tri' if base in ('1', '2', '3', '4', '5', '6') else 'iso30'


def build():
    board = make_board('shatter')
    tiles = []
    orients = {}
    for key in sorted(board.keys):
        point, role = key
        vs = _block_vertices(key)
        px = sum(v[0] for v in vs)
        py = sum(v[1] for v in vs)
        assert (px, py) == tuple(point), f'位置应为顶点和：{point} vs {(px, py)}'
        offs = [[v[0] * 3 - px, v[1] * 3 - py] for v in vs]
        # 同一朝向在所有平移下偏移必须一致（本文件的关键前提）
        if role in orients:
            assert orients[role]['off'] == offs, f'朝向 {role} 的偏移随位置变了'
        else:
            orients[role] = {'shape': shape_of(role), 'off': offs}
        tiles.append({'p': [px, py], 'o': role})

    seams = [{'name': fam.name,
              'coeffs': [fam.coeffs[0], fam.coeffs[1]],
              'step': [fam.parallel[0][0], fam.parallel[0][1]]}
             for fam in board.spec.seam_families]

    shapes_doc = {
        'schema': 'gatenna.shapes/1',
        'comment': '原子形状。顶点为单位三角格（边长为 1）下的整数坐标；'
                   'basis 由引用它的模型声明。此处供编辑器选形状与形状身份用。',
        'shapes': SHAPES,
    }
    model = {
        'schema': 'gatenna.board/1',
        'name': 'shatter',
        'title': '碎三角',
        'engine': 'geometric',
        'basis': BASIS,
        'pos_scale': POS_SCALE,
        'shapes_ref': 'shapes.json',
        'orientations': orients,
        'tiles': tiles,
        'seams': seams,
        'view': {'rotate': 0, 'mirror': False},
    }
    return shapes_doc, model


def poly_from_file(model, tile):
    """按文件内容独立重建一块的平面多边形（不复用引擎代码）。"""
    basis = model['basis']
    ps = model['pos_scale']
    offs = model['orientations'][tile['o']]['off']
    out = []
    for ox, oy in offs:
        a = (tile['p'][0] + ox) / ps
        b = (tile['p'][1] + oy) / ps
        out.append((a * basis[0][0] + b * basis[1][0],
                    a * basis[0][1] + b * basis[1][1]))
    return tuple(out)


def _key(poly):
    return tuple(sorted((round(x, 6), round(y, 6)) for x, y in poly))


def verify(model):
    ref = {_key(_polygon_at(*k)) for k in make_board('shatter').keys}
    got = {_key(poly_from_file(model, t)) for t in model['tiles']}
    return ref == got, ref - got, got - ref


if __name__ == '__main__':
    shapes_doc, model = build()
    ok, only_code, only_file = verify(model)
    print(f'朝向标签 {len(model["orientations"])} 个，放置 {len(model["tiles"])} 块')
    print(f'缝族 {len(model["seams"])} 条：' + '、'.join(s['name'] for s in model['seams']))
    print(f'重建比对：代码独有 {len(only_code)} 块，文件独有 {len(only_file)} 块')
    for p in list(only_code)[:2]:
        print('  代码:', p)
    for p in list(only_file)[:2]:
        print('  文件:', p)
    if not ok:
        sys.exit(1)
    out_dir = os.path.join(_PROJ, 'models')
    os.makedirs(out_dir, exist_ok=True)
    for fname, doc in (('shapes.json', shapes_doc), ('shatter.json', model)):
        path = os.path.join(out_dir, fname)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.write('\n')
        print(f'写入 {path}  （{os.path.getsize(path)} 字节）')
