#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
死局结构自动分析器（第一梯队③ 工具）

读取 repro_fast 引擎输出的 dead-state 文本（如 out_442_full.txt / out_443_full.txt），
对每一个死局自动核验三条几何/连通命题：

  (a) 弱或条件（必要条件）：死局 ⇒ 存在某行或某列不存在 s 连段。
  (b) 强或条件的前提（充分条件候选）：每行都无 s 连段 ∨ 每列都无 s 连段。
      —— s=2 时在 (4,4,2) 内虽可证但从不触发（真而无用）；s>=3 是真战场。
  (c) 包围盒短边：已知 (4,4,2) 9 死局短边均=3；检验"短边<=3 是否充要"。
  (d) 无洞：死局形状内是否含被 # 包围的内部空位（四连通意义）。

用法：python deadend_structure.py <out_file> <s>
依赖：仅标准库。
"""
import sys
import re
from collections import deque


def parse_dead_states(text):
    """从引擎输出解析每个 dead#N 块的网格（'.' 空 / '#' 格）。"""
    lines = text.splitlines()
    blocks = []
    cur = None
    for line in lines:
        m = re.match(
            r'^dead#(\d+)\s+id=(\d+)\s+outdeg=(\d+)\s+succ_in_B=(\d+)\s+succ_in_dead=(\d+)',
            line,
        )
        if m:
            cur = {
                'idx': int(m.group(1)),
                'id': int(m.group(2)),
                'outdeg': int(m.group(3)),
                'succ_in_B': int(m.group(4)),
                'succ_in_dead': int(m.group(5)),
                'grid': [],
            }
            blocks.append(cur)
            continue
        if cur is not None:
            stripped = line.rstrip('\n')
            # 网格行：非空且全部字符属于 {'.','#'}
            if stripped and set(stripped) <= set('.#'):
                cur['grid'].append(stripped)
            else:
                # 遇到 succ(dead): / weak components / 空行 等非网格行 → 结束当前块
                cur = None
    return blocks


def _run_len(seq, s):
    """seq 中是否存在长度 >= s 的连续 '#'。"""
    run = 0
    for ch in seq:
        if ch == '#':
            run += 1
            if run >= s:
                return True
        else:
            run = 0
    return False


def detect_hole(rows):
    """包围盒内是否存在被 # 包围的内部空位（不与边界空位连通的 '.'）。"""
    H = len(rows)
    if H == 0:
        return False
    W = max((len(r) for r in rows), default=0)
    if W == 0:
        return False
    ext = [[False] * W for _ in range(H)]
    dq = deque()
    for r in range(H):
        for c in range(W):
            if rows[r][c] == '.' and (r == 0 or r == H - 1 or c == 0 or c == W - 1):
                ext[r][c] = True
                dq.append((r, c))
    while dq:
        r, c = dq.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < H and 0 <= nc < W and rows[nr][nc] == '.' and not ext[nr][nc]:
                ext[nr][nc] = True
                dq.append((nr, nc))
    for r in range(H):
        for c in range(W):
            if rows[r][c] == '.' and not ext[r][c]:
                return True
    return False


def analyze(block, s):
    grid = block['grid']
    H = len(grid)
    W = max((len(r) for r in grid), default=0)
    rows = [(r + '.' * W)[:W] for r in grid]
    # 行/列 s-连段
    row_has_s = [ _run_len(r, s) for r in rows ]
    col_has_s = [ _run_len([ rows[r][c] for r in range(H) ], s) for c in range(W) ]
    all_rows_have_s = all(row_has_s)
    all_cols_have_s = all(col_has_s)
    any_row_has_s = any(row_has_s)
    any_col_has_s = any(col_has_s)
    # 弱或条件（必要条件候选）：存在某行无 s 连段 ∨ 存在某列无 s 连段
    weak_or = (not all_rows_have_s) or (not all_cols_have_s)
    # 强或条件的前提（充分条件候选 "每行无s连段 ∨ 每列无s连段 ⟹ 死局"）：
    #   全行都无 s 连段，或全列都无 s 连段
    strong_or_pre = (not any_row_has_s) or (not any_col_has_s)
    hole = detect_hole(rows)
    short_side = min(H, W)
    long_side = max(H, W)
    return {
        'H': H, 'W': W, 'short_side': short_side, 'long_side': long_side,
        'row_has_s': row_has_s, 'col_has_s': col_has_s,
        'weak_or': weak_or, 'strong_or_pre': strong_or_pre,
        'hole': hole, 'outdeg': block['outdeg'],
    }


def main():
    if len(sys.argv) < 3:
        print('usage: python deadend_structure.py <out_file> <s>')
        sys.exit(1)
    out_file = sys.argv[1]
    s = int(sys.argv[2])
    with open(out_file, 'r', encoding='utf-8') as f:
        text = f.read()
    blocks = parse_dead_states(text)
    if not blocks:
        print(f'[!] 未在 {out_file} 中解析到任何 dead# 块（可能该尺寸无死局，或文件未跑完）')
        sys.exit(0)
    print(f'=== 死局结构分析（s={s}，来源 {out_file}）===')
    print(f'{"#":>3} {"id":>7} {"bbox":>7} {"短边":>3} {"无洞":>3} | '
          f'{"弱或(存在)":>9} {"强或(全行/列)":>11} | outdeg')
    print('-' * 66)
    n_weak = n_strong = n_nohole = n_short3 = 0
    for b, a in [ (b, analyze(b, s)) for b in blocks ]:
        tag_weak = 'Y' if a['weak_or'] else 'N'
        tag_strong = 'Y' if a['strong_or_pre'] else 'N'
        tag_hole = 'Y' if not a['hole'] else 'N(hole)'
        bbox = f"{a['H']}x{a['W']}"
        print(f"{b['idx']:>3} {b['id']:>7} {bbox:>7} {a['short_side']:>3} {tag_hole:>7} | "
              f"{tag_weak:>9} {tag_strong:>11} | {b['outdeg']}")
        n_weak += 1 if a['weak_or'] else 0
        n_strong += 1 if a['strong_or_pre'] else 0
        n_nohole += 1 if not a['hole'] else 0
        n_short3 += 1 if a['short_side'] <= 3 else 0
    n = len(blocks)
    print('-' * 66)
    print(f'总计 {n} 个死局：')
    print(f'  弱或(必要条件：存在某行/列无{s}连段) 成立 = {n_weak}/{n}')
    print(f'  强或(充分条件前提：全行无{s}连段 ∨ 全列无{s}连段) 成立 = {n_strong}/{n}')
    print(f'  无洞 = {n_nohole}/{n}')
    print(f'  包围盒短边 <= 3 = {n_short3}/{n}  （"短边=3 是否充要"之必要性：{n_short3==n}）')


if __name__ == '__main__':
    main()
