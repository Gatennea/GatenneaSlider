# -*- coding: utf-8 -*-
"""把 5 个尺寸的「最优解距离分布」导出成 OEIS 提交格式。

table.pkl = 反向 BFS 成品表，table.values() 即每个可解态到复原态的最短步数
（回程口径，与 A089473 / A090031 同体裁）。

输出：
  - 控制台打印每个尺寸的序列 c_0, c_1, ..., c_god（c_d = 距离恰好为 d 的状态数）
  - experiments/math_repro/oeis_bfiles/<puzzle>.txt  b-file 格式（两列：d  c_d）
  - experiments/math_repro/oeis_bfiles/<puzzle>_seq.txt 纯序列（逗号分隔，便于贴 OEIS）

用法：
  D:\\python\\python.exe experiments\\math_repro\\oeis_dist.py
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # 仓库根 GatenneaSlider
MATHREPRO = Path(__file__).resolve().parent            # experiments/math_repro
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(MATHREPRO))

from verify_coloring import load_table  # noqa: E402

PUZZLES = ['2_3_1', '3_3_1', '3_3_2', '4_4_2', '4_4_3']
OUT = Path(__file__).resolve().parent / 'oeis_bfiles'
OUT.mkdir(exist_ok=True)


def main():
    for p in PUZZLES:
        table, path, complete = load_table(p)
        if table is None:
            print(f'[{p}] 无完整 table.pkl，跳过')
            continue
        vals = list(table.values())
        cnt = Counter(vals)
        god = max(vals)
        n = len(vals)
        seq = [cnt.get(d, 0) for d in range(god + 1)]

        # 一致性自检
        assert sum(seq) == n, f'{p}: 分布和 {sum(seq)} != 状态数 {n}'
        assert seq[0] == 1, f'{p}: 距离0应为1（复原态），实为 {seq[0]}'

        (OUT / f'{p}.txt').write_text(
            '\n'.join(f'{d} {c}' for d, c in enumerate(seq)) + '\n',
            encoding='utf-8')
        (OUT / f'{p}_seq.txt').write_text(', '.join(map(str, seq)),
                                           encoding='utf-8')

        print('=' * 60)
        print(f'[{p}] 状态数 n={n:,}  上帝之数 god={god}  完整表={complete}')
        print(f'  序列: {seq}')
        print(f'  b-file -> oeis_bfiles/{p}.txt')
        print(f'  纯序列 -> oeis_bfiles/{p}_seq.txt')


if __name__ == '__main__':
    main()
