# -*- coding: utf-8 -*-
"""位棋盘（bitboard）连通性原语 —— 针对 game.py 的 set 版 DFS 热点。

设计铁律（避免重演「写死 4x4 常量、对 8x8 静默 return 0」的坑）：
  - 网格宽度 W 必须由【当前坐标实际范围】推导（min/max + offset 归一），
    绝不依赖 m,n 或任何模块级尺寸常量。滑块坐标在多次移动后会漂移，
    不是固定的 m*n 方块；用实际范围才能保证任意局面都正确。
  - 所有函数显式返回并传入 W / col0 / colW（左右边界列掩码），
    位并行平移时用它们防止「绕回相邻列」。
  - 坐标是整数（方形 / 三角）；米字半整数不在本模块范围（异形有各自 opt）。

位并行 BFS 算法骨架来自 solver/table_core._mask_is_connected（已验证正确），
但**不带 lru_cache** —— 求解热路径里掩码几乎每调都不同，缓存反而增开销。
"""

# ---------------------------------------------------------------------------
# 占用掩码构建
# ---------------------------------------------------------------------------
def build_occupancy(cells):
    """把 (r,c) 坐标集合打包成单个 int 位掩码。

    返回 (mask, W, H, col0, colW, off_r, off_c)：
      off_r/off_c : 真实坐标 -> 网格索引的偏移（idx = (r-off_r)*W + (c-off_c)）
      col0        : 最左列掩码（<<1 时防跨列绕回）
      colW        : 最右列掩码（>>1 时防跨列绕回）
    坐标可为任意整数（含负），自动加 offset 归一到非负网格。
    """
    if not cells:
        return 0, 1, 0, 0, 0, 0, 0
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    min_r, max_r = min(rs), max(rs)
    min_c, max_c = min(cs), max(cs)
    W = max_c - min_c + 1
    H = max_r - min_r + 1
    mask = 0
    for r, c in cells:
        idx = (r - min_r) * W + (c - min_c)
        mask |= 1 << idx
    col0 = 0
    colW = 0
    for r in range(H):
        col0 |= 1 << (r * W)              # 列 0
        colW |= 1 << (r * W + (W - 1))    # 列 W-1
    return mask, W, H, col0, colW, min_r, min_c


# ---------------------------------------------------------------------------
# 位并行连通性
# ---------------------------------------------------------------------------
def is_connected(mask, W, col0, colW):
    """位并行 BFS 连通判定：mask 是否为单一连通分量。

    单 int 表示占用格；右/左/上/下邻居通过位移 + 边界列掩码求得。
    """
    if mask == 0:
        return True
    if mask & (mask - 1) == 0:  # 仅单格
        return True
    visited = mask & -mask       # 最低置位 = 种子
    while True:
        right = (visited & ~colW) << 1
        left = (visited & ~col0) >> 1
        up = visited >> W
        down = visited << W
        nb = (right | left | up | down) & mask
        new = nb & ~visited
        if not new:
            break
        visited |= new
    return visited == mask


def component(mask, start_bit, W, col0, colW):
    """从 start_bit 出发，在 mask 内做连通洪泛，返回连通分量掩码。

    start_bit 必须已在 mask 中（调用方保证）；返回包含 start_bit 的
    整个连通分量（位并行，等价于 set 版「从某格 DFS 到所有相邻格」）。
    """
    if not (mask & start_bit):
        return 0
    visited = start_bit
    while True:
        right = (visited & ~colW) << 1
        left = (visited & ~col0) >> 1
        up = visited >> W
        down = visited << W
        nb = (right | left | up | down) & mask
        new = nb & ~visited
        if not new:
            break
        visited |= new
    return visited


# ---------------------------------------------------------------------------
# 缝隙侧掩码
# ---------------------------------------------------------------------------
def grid_side_mask(W, H, off_r, off_c, direction, line, side):
    """整张网格中落在缝隙指定侧的所有格子掩码（与占用无关）。

    direction 'h'：line 是行索引，above = 行 <= line，below = 行 > line；
    direction 'v'：line 是列索引，left  = 列 <= line，right = 列 > line。
    返回掩码：该侧每个格子对应位置置 1。O(H) 次位移构造，不逐格循环。

    注意：一行有 W 个格子（W 个列位），一列有 H 个格子（H 个行位）；
    侧掩码是把「该侧整行 / 整列」的所有位都置 1，不能误用行/列索引当位宽。
    越界（缝隙在线框之外 → 整张网格都落在一侧）时钳制成全 1 或全 0，
    避免负索引位移崩溃。
    """
    full = (1 << (H * W)) - 1 if H * W > 0 else 0
    if direction == 'h':
        if side == 'above':
            max_gr = line - off_r          # 网格行 0..max_gr 属 above
            if max_gr < 0:
                return 0
            if max_gr >= H - 1:
                return full
            row_full = (1 << W) - 1        # 单行全部 W 个列位
            m = 0
            for gr in range(0, max_gr + 1):
                m |= row_full << (gr * W)
            return m
        else:  # below
            min_gr = line - off_r + 1
            if min_gr >= H:
                return 0
            if min_gr <= 0:
                return full
            row_full = (1 << W) - 1
            m = 0
            for gr in range(min_gr, H):
                m |= row_full << (gr * W)
            return m
    else:  # 'v'
        if side == 'left':
            max_gc = line - off_c          # 网格列 0..max_gc 属 left
            if max_gc < 0:
                return 0
            if max_gc >= W - 1:
                return full
            col_full = 0
            for gr in range(H):            # 单列（列 0）跨全部 H 行的位
                col_full |= 1 << (gr * W)
            m = 0
            for gc in range(0, max_gc + 1):
                m |= col_full << gc
            return m
        else:  # right
            min_gc = line - off_c + 1
            if min_gc >= W:
                return 0
            if min_gc <= 0:
                return full
            col_full = 0
            for gr in range(H):
                col_full |= 1 << (gr * W)
            m = 0
            for gc in range(min_gc, W):
                m |= col_full << gc
            return m
