"""S6：把原版**方形**板型写成模型文件，只用于验证 schema 的表达力。

目的不是让方形改走文件（原版四板型必须永远走手写快路径），而是回答一个
问题：`engine/model_loader` 的 schema 到底能不能表达原版板型？表达不了的
话，所谓「丢一个 json 就多一个板型」就只对碎三角这种专门设计过的板型成立。

做法：由代码版的 `square_spec` **导出**文件，再由 `model_loader` 从文件
重建，两者按**几何**对拍（块多边形集合 + 每个合法移动后的局面集合）。
对拍不比较块键/缝族名，只比几何，因为命名与键形态本来就允许不同。

坐标换算（与方形密铺对齐）：
  整数格 → 平面：`(x, y) / 2`（`basis` 取单位阵，`pos_scale = 2`）
  块 (c, r) 的四个角 = (2c, 2r) + {(0,0), (2,0), (2,2), (0,2)}
  缝族 h（水平线）：rank = y，t = 2r+2 为偶数；沿 x 走 2 = 一个块宽
  缝族 v（竖直线）：rank = x，t = 2c+2 为偶数；沿 y 走 2 = 一个块高

用法：
  PYTHONPATH=. python experiments/_gen_model_probe.py
产物写到 experiments/model_probe/（**不在 models/ 下**，不会被运行时注册）。
"""

import json
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

OUT_DIR = os.path.join(_PROJ, 'experiments', 'model_probe')

# 頂點相對「塊位置」的整數偏移（順時針：左下 → 右下 → 右上 → 左上）
_SQ_OFF = [[0, 0], [2, 0], [2, 2], [0, 2]]


def build_square(m: int, n: int) -> dict:
    """生成方形 m(行) × n(列) 的模型文件內容。"""
    tiles = []
    for r in range(m):
        for c in range(n):
            tiles.append({'p': [2 * c, 2 * r], 'o': 'sq'})
    return {
        'schema': 'gatenna.board/1',
        'name': f'probe_square_{m}x{n}',
        'title': f'方形对拍 {m}×{n}',
        'engine': 'geometric',
        'basis': [[1.0, 0.0], [0.0, 1.0]],
        'pos_scale': 2,
        'shapes_ref': 'shapes.json',
        'solved': 'canonical',
        'orientations': {
            'sq': {'shape': 'sq', 'off': _SQ_OFF},
        },
        'tiles': tiles,
        'seams': [
            # 水平縫：rank = 整數 y；沿縫走 2（= 一個塊寬）
            {'name': 'hs', 'coeffs': [0, 1], 'step': [2, 0]},
            # 豎直縫：rank = 整數 x；沿縫走 2（= 一個塊高）
            {'name': 'vs', 'coeffs': [1, 0], 'step': [0, 2]},
        ],
        'view': {'rotate': 0, 'mirror': False},
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for m, n in ((4, 4), (6, 6)):
        doc = build_square(m, n)
        path = os.path.join(OUT_DIR, f'square_{m}x{n}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False, indent=1, sort_keys=False)
            f.write('\n')
        print(f'写入 {path}（{len(doc["tiles"])} 块，{os.path.getsize(path)} 字节）')


if __name__ == '__main__':
    main()
