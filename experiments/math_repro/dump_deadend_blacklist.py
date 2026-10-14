# -*- coding: utf-8 -*-
"""从 trap_paths_4_4_2.json 生成打乱死局黑名单 solver/deadend_blacklist.json。

数据来源：experiments/math_repro/trap_paths_4_4_2.json（shuffle_trap.py 产出，
4_4_2 状态空间严格穷举的结论）。每个 traps[i].edges[-1].child_cells 是第 i 个
死局态在规范坐标系下的格子列表，脚本重新 canonicalize 校验一遍再写入
（不手抄哈希，防止 JSON 与结论脱节）。

输出格式（供 solver.deadend_guard 读取）：
    {"4_4_2": [9 个规范哈希整数]}

位置说明：必须入库（.gitignore 没排除），所以不能放 solver/data/ ——
该目录整体被忽略，放进去打包/克隆后运行时会缺文件。

用法：
  python experiments/math_repro/dump_deadend_blacklist.py [trap_paths 文件]
  缺省读 experiments/math_repro/trap_paths_4_4_2.json。
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver import table_core as tc  # noqa: E402

OUT_PATH = ROOT / 'solver' / 'deadend_blacklist.json'


def main(argv) -> int:
    t0 = time.perf_counter()
    src = (Path(argv[0]) if argv
           else Path(__file__).resolve().parent / 'trap_paths_4_4_2.json')
    data = json.loads(src.read_text(encoding='utf-8'))

    key = f"{data['m']}_{data['n']}_{data['step']}"
    if key != data['puzzle']:
        raise SystemExit(f"puzzle 字段 {data['puzzle']!r} 与 m/n/step 推出的 {key!r} 不一致")

    hashes = []
    for i, trap in enumerate(data['traps']):
        cells = [tuple(c) for c in trap['edges'][-1]['child_cells']]
        h = tc.canonicalize(cells)
        if h != trap['state']:
            raise SystemExit(f"traps[{i}].child_cells 规范化得 {h}，与 state {trap['state']} 不符")
        hashes.append(h)

    if len(set(hashes)) != len(hashes):
        raise SystemExit('死局哈希有重复，检查 trap_paths 数据')
    if hashes and tc.canonicalize(tc.goal_state(data['m'], data['n'])) in hashes:
        raise SystemExit('复原态不得进黑名单')

    OUT_PATH.write_text(
        json.dumps({key: hashes}, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(f"写入 {OUT_PATH}：{key} 共 {len(hashes)} 个死局哈希")
    print(f"耗时 {time.perf_counter() - t0:.3f}s")
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
