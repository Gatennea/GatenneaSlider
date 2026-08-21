# -*- coding: utf-8 -*-
"""
建表查询与验证工具（CLI）

子命令：
    status                - 显示表统计（状态数、最大距离、分布）
    dist    "<map_str>"   - 给定 # / _ 地图，输出求解距离
    solve   "<map_str>"   - 输出最短解法（状态序列 + 步数）
    verify  [N]           - 随机抽样 N 个表内状态，验证距离一致性

地图格式：
    '#'  = 有方块
    '_' 或 '.' 或空格 = 空格
    行间用换行或 '|' 分隔

运行：
    D:\\python\\python.exe -m solver.table_query status
    D:\\python\\python.exe -m solver.table_query dist "###|###"
    D:\\python\\python.exe -m solver.table_query solve "##.|##.|.##"
    D:\\python\\python.exe -m solver.table_query verify 20
"""

import os
import sys
import json
import pickle
import random

from solver import table_core as tc


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def _find_table(m, n, step):
    """查找指定等级的数据目录，返回 (data_dir, table_path, meta_path)。"""
    data_dir = os.path.join(DATA_DIR, f'{m}_{n}_{step}')
    table_path = os.path.join(data_dir, 'table.pkl')
    meta_path = os.path.join(data_dir, 'meta.json')
    if not os.path.exists(table_path):
        return None, None, None
    return data_dir, table_path, meta_path


def _find_any_table():
    """查找任意已建表的数据目录。"""
    if not os.path.isdir(DATA_DIR):
        return None, None, None
    for name in sorted(os.listdir(DATA_DIR)):
        data_dir = os.path.join(DATA_DIR, name)
        if not os.path.isdir(data_dir):
            continue
        parts = name.split('_')
        if len(parts) != 3:
            continue
        table_path = os.path.join(data_dir, 'table.pkl')
        meta_path = os.path.join(data_dir, 'meta.json')
        if os.path.exists(table_path):
            return data_dir, table_path, meta_path
    return None, None, None


def _load_table(m=None, n=None, step=None):
    """加载表。若指定 m/n/step 则查对应目录，否则自动查找。"""
    if m is not None:
        data_dir, table_path, meta_path = _find_table(m, n, step)
    else:
        data_dir, table_path, meta_path = _find_any_table()

    if table_path is None:
        print(f"错误: 找不到建表数据。请先用 `python -m solver.build_table {m or 'm'} {n or 'n'} {step or 'step'}` 建表。")
        sys.exit(1)

    with open(table_path, 'rb') as f:
        table = pickle.load(f)
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
    return table, meta


# ---------------------------------------------------------------------------
# 地图解析
# ---------------------------------------------------------------------------
def parse_map(map_str, m=None, n=None, step=None):
    """将地图字符串解析为坐标集合。

    格式：'#' 有方块，'_'/ '.'/空格 无方块，行间用换行或 '|' 分隔。
    返回: frozenset[(row, col)]
    """
    # 统一换行符，按 | 或换行分割
    map_str = map_str.replace('\\n', '\n')
    rows = []
    for line in map_str.split('\n'):
        for part in line.split('|'):
            if part.strip():
                rows.append(part)

    coords = set()
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch == '#':
                coords.add((r, c))
    if not coords:
        print("错误: 地图中没有方块（'#'）")
        sys.exit(1)
    return frozenset(coords)


def coords_to_grid(coords, m=None, n=None):
    """将坐标集合渲染为文本网格。"""
    coords = set(coords)
    if not coords:
        return '(空)'
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    min_r, max_r = min(rs), max(rs)
    min_c, max_c = min(cs), max(cs)
    lines = []
    for r in range(min_r, max_r + 1):
        line = ''
        for c in range(min_c, max_c + 1):
            line += '#' if (r, c) in coords else '.'
        lines.append(line)
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# 子命令: status
# ---------------------------------------------------------------------------
def cmd_status(args):
    m = n = step = None
    if len(args) >= 3:
        m, n, step = int(args[0]), int(args[1]), int(args[2])

    table, meta = _load_table(m, n, step)
    m = meta.get('m', m)
    n = meta.get('n', n)
    step = meta.get('step', step)

    print(f"═══ 建表统计 ═══")
    print(f"  尺寸: {m}×{n}  步长: {step}  总格子: {m * n}")
    print(f"  总状态数: {len(table):,}")
    print(f"  最大距离: {meta.get('max_distance', max(table.values()) if table else 0)}")
    print(f"  创建时间: {meta.get('created_at', '未知')}")

    distrib = meta.get('distance_distribution', {})
    if not distrib and table:
        # 从 table 重新统计
        distrib = {}
        for d in table.values():
            distrib[d] = distrib.get(d, 0) + 1

    print(f"\n  距离分布:")
    for d in sorted(distrib.keys(), key=lambda x: int(x)):
        count = distrib[d] if isinstance(distrib[d], int) else int(distrib[d])
        bar = '█' * min(count // max(1, len(table) // 60), 50)
        print(f"    d={int(d):3d}: {count:8d}  {bar}")

    # 数据文件信息
    data_dir = os.path.join(DATA_DIR, f'{m}_{n}_{step}')
    ckpt = os.path.join(data_dir, 'checkpoint.pkl')
    if os.path.exists(ckpt):
        ckpt_size = os.path.getsize(ckpt) / 1024 / 1024
        print(f"\n  断点文件: {ckpt_size:.1f} MB")
    table_file = os.path.join(data_dir, 'table.pkl')
    if os.path.exists(table_file):
        table_size = os.path.getsize(table_file) / 1024 / 1024
        print(f"  表文件: {table_size:.1f} MB")


# ---------------------------------------------------------------------------
# 子命令: dist
# ---------------------------------------------------------------------------
def cmd_dist(args):
    if not args:
        print("用法: python -m solver.table_query dist \"<map_str>\" [m n step]")
        sys.exit(1)

    map_str = args[0]
    m = n = step = None
    if len(args) >= 4:
        m, n, step = int(args[1]), int(args[2]), int(args[3])

    table, meta = _load_table(m, n, step)
    m = meta.get('m', m)
    n = meta.get('n', n)
    step = meta.get('step', step)
    total = m * n

    coords = parse_map(map_str)
    if len(coords) != total:
        print(f"警告: 地图有 {len(coords)} 个方块，但 {m}×{n} 应有 {total} 个")

    h = tc.canonicalize(coords)
    print(f"输入状态 ({len(coords)} 格):")
    print(coords_to_grid(coords))

    if h in table:
        d = table[h]
        print(f"\n求解距离: {d}")
    else:
        print(f"\n该状态不在表中（可能是不可解的死局，或表未建完）")


# ---------------------------------------------------------------------------
# 子命令: solve
# ---------------------------------------------------------------------------
def cmd_solve(args):
    if not args:
        print("用法: python -m solver.table_query solve \"<map_str>\" [m n step]")
        sys.exit(1)

    map_str = args[0]
    m = n = step = None
    if len(args) >= 4:
        m, n, step = int(args[1]), int(args[2]), int(args[3])

    table, meta = _load_table(m, n, step)
    m = meta.get('m', m)
    n = meta.get('n', n)
    step = meta.get('step', step)
    total = m * n

    coords = parse_map(map_str)
    if len(coords) != total:
        print(f"警告: 地图有 {len(coords)} 个方块，但 {m}×{n} 应有 {total} 个")

    h = tc.canonicalize(coords)
    if h not in table:
        print("该状态不在表中（不可解或表未建完），无法求解。")
        sys.exit(1)

    target_dist = table[h]
    print(f"起始距离: {target_dist}")
    print(f"起始状态:")
    print(coords_to_grid(coords))
    print()

    # 贪心走 dist-1 邻居
    cur_h = h
    cur_coords = set(tc.int_to_coords(cur_h, total))
    path = [cur_h]
    step_num = 0

    while table[cur_h] > 0:
        step_num += 1
        nbrs = tc.forward_neighbors(cur_coords, step, total)
        # 找 dist-1 的邻居
        best = None
        for nb_h in nbrs:
            if nb_h in table and table[nb_h] == table[cur_h] - 1:
                best = nb_h
                break

        if best is None:
            print(f"错误: 在距离 {table[cur_h]} 处找不到 dist-1 的邻居，表可能不完整。")
            break

        cur_h = best
        cur_coords = set(tc.int_to_coords(cur_h, total))
        path.append(cur_h)
        print(f"── 步骤 {step_num} (距离 {table[cur_h]}) ──")
        print(coords_to_grid(cur_coords))
        print()

    if table[cur_h] == 0:
        print(f"✓ 到达目标！总步数: {step_num}")


# ---------------------------------------------------------------------------
# 子命令: verify
# ---------------------------------------------------------------------------
def cmd_verify(args):
    m = n = step = None
    sample_n = 50
    i = 0
    while i < len(args):
        try:
            val = int(args[i])
            if sample_n == 50 and i == 0:
                sample_n = val
                i += 1
                continue
            elif m is None:
                m = val
            elif n is None:
                n = val
            elif step is None:
                step = val
            i += 1
        except ValueError:
            i += 1

    if m is not None and (n is None or step is None):
        sample_n = m
        m = n = step = None

    table, meta = _load_table(m, n, step)
    m = meta.get('m', m)
    n = meta.get('n', n)
    step = meta.get('step', step)
    total = m * n

    print(f"═══ 距离一致性验证 ═══")
    print(f"  尺寸: {m}×{n}  步长: {step}")
    print(f"  表内状态数: {len(table):,}")
    print(f"  抽样数: {sample_n}")
    print()

    # 随机抽样
    keys = list(table.keys())
    if len(keys) > sample_n:
        random.seed(42)
        sample = random.sample(keys, sample_n)
    else:
        sample = keys

    ok = 0
    fail = 0
    skipped = 0

    for h in sample:
        d = table[h]
        if d == 0:
            skipped += 1
            continue

        coords = set(tc.int_to_coords(h, total))
        nbrs = tc.forward_neighbors(coords, step, total)

        # 验证：存在 dist-1 的邻居，且无 dist < d-1 的邻居
        nbr_dists = [table[nb] for nb in nbrs if nb in table]
        if not nbr_dists:
            print(f"  [失败] dist={d} 无表内邻居")
            fail += 1
            continue

        min_nbr = min(nbr_dists)
        if min_nbr != d - 1:
            print(f"  [失败] dist={d} 邻居最小距离={min_nbr} (应为 {d - 1})")
            fail += 1
        else:
            ok += 1

    print(f"  结果: 通过={ok}  失败={fail}  跳过(目标)={skipped}")
    if fail == 0:
        print(f"  ✓ 距离一致性验证通过")
    else:
        print(f"  ✗ 存在不一致，请检查")
        sys.exit(1)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
USAGE = """用法:
    python -m solver.table_query status [m n step]
    python -m solver.table_query dist "<map_str>" [m n step]
    python -m solver.table_query solve "<map_str>" [m n step]
    python -m solver.table_query verify [N] [m n step]

地图格式: '#' 有方块, '.'/'_'/' ' 空格, 行间用 '|' 或换行分隔
示例:     "###|###"  或  "##.\\n##.\\n.##"
"""


def main():
    args = sys.argv[1:]
    if not args:
        print(USAGE)
        sys.exit(0)

    cmd = args[0]
    rest = args[1:]

    if cmd == 'status':
        cmd_status(rest)
    elif cmd == 'dist':
        cmd_dist(rest)
    elif cmd == 'solve':
        cmd_solve(rest)
    elif cmd == 'verify':
        cmd_verify(rest)
    else:
        print(f"未知命令: {cmd}")
        print(USAGE)
        sys.exit(1)


if __name__ == '__main__':
    main()
