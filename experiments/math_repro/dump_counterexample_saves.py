# -*- coding: utf-8 -*-
"""
把「着色集合相同但不可解」反例导出为游戏可直接打开的 JSON 存档。

复用成绩面板的 01 矩阵 → 滑块组转换（gui/records_panel.py 的
_rp_save_as_puzzle，即面板里「另存为存档」按钮的同一段代码），
生成的存档与游戏内另存的结构完全一致，可在「文件 - 打开」直接载入，
无需手写 JSON 再验证能否导入。

流程：
  verify_coloring.verify(puzzle)  →  反例格集（A−B）
  cells → 0/1 矩阵串（成绩记录 initial_matrix 口径）
  RecordsPanelMixin._rp_save_as_puzzle  →  save/反例存档/反例-<puzzle>-<序号>.json

用法：
  D:\\python\\python.exe experiments\math_repro\\dump_counterexample_saves.py [puzzle...]
  缺省跑 2_3_1 3_3_1 3_3_2（当前已出反例的三个完整表）。
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from verify_coloring import parse_puzzle, verify  # noqa: E402
from gui.records_panel import RecordsPanelMixin  # noqa: E402

OUT_DIR = ROOT / 'save' / '反例存档'
DEFAULT_PUZZLES = ['2_3_1', '3_3_1', '3_3_2']


class _SaveStub(RecordsPanelMixin):
    """只提供 save_dir 的最小宿主——_rp_save_as_puzzle 只用到它。"""

    def __init__(self, save_dir):
        self.save_dir = str(save_dir)


def cells_to_matrix(cells):
    """反例格集 → 成绩记录口径的 0/1 矩阵串（行间 \\n，矩形包围盒）。

    与 records.add_record 存 initial_matrix 的格式一致（'1111\\n1110...'），
    _rp_record_map_str 会把它换回 #/_ 再交给 game.import_map。
    """
    cells = {(r, c) for r, c in cells}
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    return '\n'.join(
        ''.join('1' if (r, c) in cells else '0' for c in range(min(cs), max(cs) + 1))
        for r in range(min(rs), max(rs) + 1))


def main(puzzles):
    stub = _SaveStub(OUT_DIR)
    made = []
    for pz in puzzles:
        print()
        res = verify(pz)
        cells_all = None if res is None else res.get('example_cells')
        if not cells_all:
            print(f'[{pz}] 无可导出反例（表缺失 / 不完整 / sanity 失败 / A==B）')
            continue
        m, n, step = parse_puzzle(pz)
        for i, cells in enumerate(cells_all, 1):
            rec = {'m': m, 'n': n, 'step': step,
                   'initial_matrix': cells_to_matrix(cells)}
            path = stub._rp_save_as_puzzle(rec)
            if not path:
                print(f'  [{pz} #{i}] 转换失败')
                continue
            target = OUT_DIR / f'反例-{pz}-{i}.json'
            os.replace(path, target)
            made.append((target, pz, m, n, step, sorted(cells)))
            print(f'  已导出 {target.name}')

    # 轻量结构检查（复用官方转换后只需确认落盘完整，不测游戏导入）
    print('\n结构检查：')
    ok = True
    for path, pz, m, n, step, cells in made:
        data = json.loads(path.read_text(encoding='utf-8'))
        snap = data['history']['snapshots'][0]
        ones = sum(sum(row) for row in snap['matrix'])
        good = (data['puzzle'] == {'m': m, 'n': n, 'step': step}
                and ones == len(cells)
                and len(snap['matrix']) > 0)
        ok = ok and good
        print(f'  {"✓" if good else "✗"} {path.name}  '
              f'puzzle={m}x{n} step={step} 滑块={ones} 盒='
              f'{len(snap["matrix"])}x{len(snap["matrix"][0])}')
    print(f'\n共导出 {len(made)} 个存档 → {OUT_DIR}')
    return 0 if ok and made else 1


if __name__ == '__main__':
    args = sys.argv[1:] or DEFAULT_PUZZLES
    sys.exit(main(args))
