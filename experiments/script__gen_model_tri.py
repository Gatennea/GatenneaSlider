"""从代码版三角板型导出一份「仅作对拍」的模型文件。

目的：验证 `models/*.json` 这个 schema 能否表达三角密铺（斜坐标三角晶格，
3 个朝向无关缝族 h/p + 1 个带朝向修正的 n 族）。不进运行时——三角在 GUI
里走手写渲染路径（gui/triangle_view.py），文件版只用来证明 schema 的表达力。

三角与碎三角同构：point = 三顶点之和（= 3× 质心，斜坐标整数），offset[orient]
= 3× 顶点 − point，pos_scale = 3。plane_of = basis·顶点。basis 取代码版的
_TRI_PLANE_BASIS（单位三角晶格基）。

缝族 rank 在通用 schema 里作用于「顶点（3× 斜坐标）」；三角的 n 族代码版用
rank_n 钩子作用于「块位置 + 朝向偏移」。两者是否等价：n 缝是 up 与 down 共用
的那条斜边，其两个端点在斜坐标下本就同 rank，故 coeffs=(1,1) 作用于顶点即等价，
无需朝向修正。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.registry import make_board
from engine.tri_geometry import tri_vertices, TRI_DIRECTIONS

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCALE = 3
BASIS = [[1.0, 0.0], [0.5, 0.8660254037844386]]  # _TRI_PLANE_BASIS


def build(k=6):
    board = make_board('tri', k=k)
    tiles = []
    orientations = {}
    for key in sorted(board.keys):
        (i, j), orient = key
        verts = tri_vertices(i, j, orient)
        point = (sum(v[0] for v in verts), sum(v[1] for v in verts))
        offs = [[v[0] * SCALE - point[0], v[1] * SCALE - point[1]] for v in verts]
        # 三角的朝向只有 2 种，首次遇到时记录偏移（同一朝向跨平移一致）
        if orient not in orientations:
            orientations[orient] = {'off': offs}
        else:
            assert orientations[orient]['off'] == offs, \
                f'朝向 {orient} 偏移随位置变化'
        tiles.append({'p': list(point), 'o': orient})

    # step 是「沿缝走一个三角单元的整数格位移」（point = 3× 斜坐标质心和，
    # 故一个单元 = 3 个斜坐标单位）。coeffs·step 必须正交（缝垂直于移动方向）。
    seams = [
        {'name': 'h', 'coeffs': [0, 1], 'step': [3, 0],
         'parallel': [[-3, 0], [3, 0]]},
        {'name': 'p', 'coeffs': [1, 0], 'step': [0, 3],
         'parallel': [[0, -3], [0, 3]]},
        {'name': 'n', 'coeffs': [1, 1], 'step': [3, -3],
         'parallel': [[-3, 3], [3, -3]]},
    ]
    directions = [list(d) for d in TRI_DIRECTIONS.values()]

    model = {
        'schema': 'gatenna.board/1',
        'name': 'tri_probe',
        'title': '三角(对拍)',
        'engine': 'geometric',
        'basis': BASIS,
        'pos_scale': SCALE,
        'shapes_ref': 'shapes.json',
        'orientations': orientations,
        'tiles': tiles,
        'seams': seams,
        'directions': directions,
        'view': {'rotate': 0, 'mirror': False},
    }
    return model


if __name__ == '__main__':
    import math  # noqa: E402

    model = build()

    def _TRI_PLANE_BASIS_POLY(key):
        (i, j), orient = key
        e1, e2 = BASIS
        return tuple((a * e1[0] + b * e2[0], a * e1[1] + b * e2[1])
                     for (a, b) in tri_vertices(i, j, orient))

    def poly_from_file(m, t):
        o = m['orientations'][t['o']]
        out = []
        for v in o['off']:
            a = t['p'][0] / SCALE + v[0] / SCALE
            b = t['p'][1] / SCALE + v[1] / SCALE
            out.append((a * BASIS[0][0] + b * BASIS[1][0],
                        a * BASIS[0][1] + b * BASIS[1][1]))
        return tuple(out)

    def key(poly):
        return tuple(sorted((round(x, 6), round(y, 6)) for x, y in poly))

    ref = {key(_TRI_PLANE_BASIS_POLY(k)) for k in make_board("tri", k=6).keys}
    got = {key(poly_from_file(model, t)) for t in model['tiles']}
    ok = ref == got
    print(f'朝向 {len(model["orientations"])} 个，放置 {len(model["tiles"])} 块')
    print(f'重建比对：代码独有 {len(ref - got)}，文件独有 {len(got - ref)}')
    if not ok:
        sys.exit(1)
    out_dir = os.path.join(PROJ, 'experiments', 'model_probe')
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'tri_6.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(model, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print(f'写入 {path}（{os.path.getsize(path)} 字节）')
