#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把复现引擎输出的死局块渲染为带坐标的 ASCII 画廊。

解析 repro_fast 的 out_*_full.txt 中 `dead#N ...` 段（`.`/`#` 网格），
为每个死局渲染：带 (行,列) 坐标的网格 + 几何属性（bbox / 短边 / 是否有洞 /
弱或 / 强或），并汇总成画廊文本。

用法：
    python deadend_shapes.py <out_full.txt> <s> [out_gallery.txt]
不传第三参数则打印到 stdout。
"""
import sys


def parse_deadends(path):
    """返回 [(idx, id, outdeg, grid_rows, succ_line), ...]"""
    deads = []
    cur = None  # (idx, id, outdeg, rows[])
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.rstrip("\n")
            if s.startswith("dead#"):
                # 收尾上一块
                if cur is not None:
                    deads.append(cur)
                # dead#1 id=2620 outdeg=1 ...
                parts = s.split()
                idx = int(parts[0][len("dead#"):])
                idv = int(parts[1].split("=")[1])
                od = int(parts[2].split("=")[1])
                cur = [idx, idv, od, []]
            elif cur is not None:
                if s.startswith("  succ") or s.strip() == "":
                    # 块间分隔行：空行或 succ 行都表示网格结束（仅 succ 行真正结束）
                    if s.startswith("  succ"):
                        deads.append(cur)
                        cur = None
                    # 空行：忽略（网格已收集）
                elif all(ch in ".#" for ch in s) and s:
                    cur[3].append(s)
                else:
                    # 其他非网格行（理论上不会有）：忽略
                    pass
    if cur is not None:
        deads.append(cur)
    return deads


def geometry(grid):
    """grid: list[str]，'#'=占，'.'=空。返回几何量。"""
    nrows = len(grid)
    if nrows == 0:
        return dict(H=0, W=0, short=0, hole=False, weak_or=False, strong_or=False)
    ncols = max(len(r) for r in grid)
    g = [[(grid[r][c] == "#" if c < len(grid[r]) else False) for c in range(ncols)] for r in range(nrows)]
    # 连通性 / 洞：占格集合的 4-连通补集中，被占格包围的空格 = 洞
    occ = [(r, c) for r in range(nrows) for c in range(ncols) if g[r][c]]
    from collections import deque
    seen = set(occ)
    # 外部空域 BFS（从边界空格出发）
    exterior = set()
    dq = deque()
    for r in range(nrows):
        for c in range(ncols):
            if not g[r][c] and (r in (0, nrows - 1) or c in (0, ncols - 1)):
                if (r, c) not in exterior:
                    exterior.add((r, c))
                    dq.append((r, c))
    while dq:
        r, c = dq.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < nrows and 0 <= nc < ncols and not g[nr][nc] and (nr, nc) not in exterior:
                exterior.add((nr, nc))
                dq.append((nr, nc))
    hole = any(not g[r][c] and (r, c) not in exterior for r in range(nrows) for c in range(ncols))
    # 行/列 s 连段存在性：逐行/列是否存在长度 >= s 的连续占格
    def has_s_segment_line(line):
        run = 0
        for v in line:
            run = run + 1 if v else 0
            if run >= S:
                return True
        return False
    rows_occ = [[g[r][c] for c in range(ncols)] for r in range(nrows)]
    cols_occ = [[g[r][c] for r in range(nrows)] for c in range(ncols)]
    row_has = [has_s_segment_line(rows_occ[r]) for r in range(nrows)]
    col_has = [has_s_segment_line(cols_occ[c]) for c in range(ncols)]
    weak_or = (not all(row_has)) or (not all(col_has))   # 存在某行/列无 s 连段（必要条件）
    strong_or = (not any(row_has)) or (not any(col_has))  # 全行无 s 连段 ∨ 全列无 s 连段（恒假）
    H = nrows
    W = ncols
    return dict(H=H, W=W, short=min(H, W), hole=hole, weak_or=weak_or, strong_or=strong_or)


def render(grid, idx, idv, od, geo):
    """渲染单个死局为带坐标的 ASCII。"""
    nrows = len(grid)
    ncols = max(len(r) for r in grid) if grid else 0
    lines = []
    head = f"dead#{idx} id={idv} outdeg={od}  bbox={geo['H']}x{geo['W']} 短边={geo['short']} 洞={'有' if geo['hole'] else '无'} 弱或={geo['weak_or']} 强或={geo['strong_or']}"
    lines.append(head)
    # 列坐标
    colhdr = "    " + "".join(str(c % 10) for c in range(ncols))
    lines.append(colhdr)
    for r in range(nrows):
        row = grid[r] if r < len(grid) else ""
        cells = "".join(row[c] if c < len(row) else "." for c in range(ncols))
        lines.append(f"  {r:>1} {cells}")
    lines.append("")
    return lines


def main():
    global S
    if len(sys.argv) < 3:
        print("usage: deadend_shapes.py <out_full.txt> <s> [gallery.txt]")
        sys.exit(1)
    path = sys.argv[1]
    S = int(sys.argv[2])
    out = sys.argv[3] if len(sys.argv) > 3 else None
    deads = parse_deadends(path)
    blocks = []
    for (idx, idv, od, grid) in deads:
        geo = geometry(grid)
        blocks.extend(render(grid, idx, idv, od, geo))
    text = "\n".join(blocks)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {len(deads)} deadend shapes -> {out}")
    else:
        print(text)
        print(f"({len(deads)} deadends)")


if __name__ == "__main__":
    main()
