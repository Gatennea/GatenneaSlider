# -*- coding: utf-8 -*-
r"""
洞检测器 — 定位并分类目标矩形内的「洞」

对当前状态做：
    1. find_target_region ：找包含最多方块的 m×n 或 n×m 矩形区域（目标区域）。
    2. detect_holes        ：在目标区域内用洪水填充找出所有连通空格（洞），
                             并分类「缺口 / 孔洞」、判定「大 / 小」。

洞的类型：
    gap  ：连通到目标矩形外缘的空格（缺口/凹陷）
    hole ：被方块完全包围的空格（孔洞）

洞的大小（相对移动步长 step）：
    large ：洞的边界盒 长 > step 或 宽 > step
    small ：边界盒 长、宽都 ≤ step

同时返回：
    protrusions ：目标矩形外的方块（凸起，可作为「填料」）

运行测试：
    D:\python\python.exe -m solver.ml.hole_detector
"""

import sys


# ---------------------------------------------------------------------------
# 目标区域
# ---------------------------------------------------------------------------
def find_target_region(coords, m, n):
    """找包含最多方块的 m×n 或 n×m 矩形区域。

    返回 (r0, c0, (rh, cw), overlap)：
        r0, c0      : 矩形左上角坐标
        (rh, cw)    : 矩形朝向（(m,n) 或 (n,m)）
        overlap     : 矩形内方块数
    """
    total = m * n
    if not coords:
        return 0, 0, (m, n), 0
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    min_r, max_r = min(rs), max(rs)
    min_c, max_c = min(cs), max(cs)

    best = (min_r, min_c, (m, n), 0)
    for rh, cw in ((m, n), (n, m)):
        for r0 in range(min_r - rh + 1, max_r + 1):
            for c0 in range(min_c - cw + 1, max_c + 1):
                cnt = 0
                for r, c in coords:
                    if r0 <= r < r0 + rh and c0 <= c < c0 + cw:
                        cnt += 1
                if cnt > best[3]:
                    best = (r0, c0, (rh, cw), cnt)
                    if cnt == total:
                        return best
    return best


# ---------------------------------------------------------------------------
# 洞检测
# ---------------------------------------------------------------------------
def detect_holes(coords, m, n, step, region=None):
    """检测目标矩形内的洞 + 凸起。

    参数：
        coords : 方块坐标集合（frozenset/set）
        m, n   : 目标尺寸
        step   : 移动步长（用于判定洞的大小）
        region : 固定目标窗口 (r0, c0, (rh, cw))；None = 由 find_target_region
                 自动寻找（不含 mod 约束）。GUI 传 region 可让洞/凸起的
                 语义与「画出的目标框」完全一致。

    返回 (holes, protrusions, region)：
        holes        : 洞列表，每个为 {cells, type, bbox, size}
        protrusions  : 凸起坐标列表（目标矩形外的方块）
        region       : (r0, c0, (rh, cw)) 目标区域
    """
    if region is not None:
        r0, c0, (rh, cw) = region
    else:
        r0, c0, (rh, cw), _ = find_target_region(coords, m, n)

    # 目标矩形网格：1=有方块，0=空
    grid = [[0] * cw for _ in range(rh)]
    protrusions = []
    for r, c in coords:
        if r0 <= r < r0 + rh and c0 <= c < c0 + cw:
            grid[r - r0][c - c0] = 1
        else:
            protrusions.append((r, c))

    # 洪水填充：把所有连通 0 区域标记出来
    visited = [[False] * cw for _ in range(rh)]
    holes = []
    for i in range(rh):
        for j in range(cw):
            if grid[i][j] == 0 and not visited[i][j]:
                cells = []
                touches_edge = False
                stack = [(i, j)]
                visited[i][j] = True
                while stack:
                    x, y = stack.pop()
                    cells.append((x, y))
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < rh and 0 <= ny < cw:
                            if grid[nx][ny] == 0 and not visited[nx][ny]:
                                visited[nx][ny] = True
                                stack.append((nx, ny))
                        else:
                            touches_edge = True  # 越界 = 连通外缘

                hole_type = 'gap' if touches_edge else 'hole'
                rs = [x for x, _ in cells]
                cs = [y for _, y in cells]
                h = max(rs) - min(rs) + 1
                w = max(cs) - min(cs) + 1
                size = 'large' if (h >= step or w >= step) else 'small'
                abs_cells = [(x + r0, y + c0) for x, y in cells]
                holes.append({
                    'cells': abs_cells,
                    'type': hole_type,
                    'bbox': (h, w),
                    'size': size,
                })

    return holes, protrusions, (r0, c0, (rh, cw))


def _game_coords(game):
    return frozenset((b.location[0], b.location[1]) for b in game.blocks)


def summarize(game, step):
    """返回当前游戏的洞检测摘要（供 GUI 面板/调试使用）。"""
    m, n = game.m, game.n
    holes, protrusions, region = detect_holes(_game_coords(game), m, n, step)
    return {
        'holes': holes,
        'protrusions': protrusions,
        'region': region,
        'large_count': sum(1 for h in holes if h['size'] == 'large'),
        'small_count': sum(1 for h in holes if h['size'] == 'small'),
        'gap_count': sum(1 for h in holes if h['type'] == 'gap'),
        'hole_count': sum(1 for h in holes if h['type'] == 'hole'),
    }


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------
def main():
    m, n, step = 4, 4, 2
    if len(sys.argv) > 3:
        m, n, step = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])

    # 直接手工构造：行0,1,2 正常，行3 右移2
    coords = {(r, c) for r in range(m - 1) for c in range(n)} | \
             {(m - 1, c) for c in range(step, step + n)}

    holes, protrusions, region = detect_holes(coords, m, n, step)
    r0, c0, (rh, cw) = region
    print(f"目标区域: ({r0},{c0}) {rh}x{cw}")
    print(f"凸起: {protrusions}")
    print(f"洞数量: {len(holes)}")
    for i, h in enumerate(holes):
        print(f"  洞{i}: 类型={h['type']} 大小={h['size']} 边界盒={h['bbox']} 格数={len(h['cells'])} 位置={h['cells']}")


if __name__ == '__main__':
    main()
