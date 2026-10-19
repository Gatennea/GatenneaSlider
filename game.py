# -*- coding: utf-8 -*-
"""
滑块游戏核心逻辑模块

本模块包含两个主要类：
1. Block - 单个滑块对象
2. SliderMatrix - 滑块矩阵管理类

滑块游戏规则：
- m*n个正方形滑块构成的矩形为复原状态
- 沿分割线滑动滑块组的一部分
- 从复原状态打乱后还原
"""

# 移动方向字母 → (Δrow, Δcol)（与 TriangleSliderMatrix/MiSliderMatrix 同键名，
# 供上层按形态统一查表；try_move_ex 内部直接消费这张表）
DIRECTIONS = {
    'w': (-1, 0),
    's': (1, 0),
    'a': (0, -1),
    'd': (0, 1),
}

# 位棋盘连通性原语（阶段3：替换 set 版 DFS 热点，见根目录 bitboard.py）
from bitboard import build_occupancy, is_connected, component, grid_side_mask


class Block:
    """
    单个滑块对象类
    
    属性：
        location: list[int] - 滑块的坐标位置 [行, 列]
        be_opted: bool - 是否被选中（用于高亮显示）
        group: int - 捆绑组编号（0=未捆绑；自由捆绑模式，见
            docs/spec/bandaged_mode.md）。捆绑组是刚体：组内任一块
            被选中时整组一起平移，缝隙切不开组。

    注意：location 是可变的（commit_move 原地改写），而 __hash__/__eq__ 基于
    location——禁止把 Block 直接作为 set/dict 的键，一律用 tuple(b.location)。
    """
    
    __slots__ = ('location', 'be_opted', 'number', 'group')
    
    def __init__(self, location: list[int], be_opted: bool = False):
        """
        初始化滑块对象
        
        参数：
            location: 初始坐标位置 [行, 列]
            be_opted: 是否被选中，默认为 False
        """
        self.location = location
        self.be_opted = be_opted
        self.number = None
        self.group = 0
    
    def __eq__(self, other) -> bool:
        """
        判断两个滑块是否相等（位置相同即为相等）
        
        参数：
            other: 另一个滑块对象
        
        返回：
            bool - 位置相同返回 True，否则返回 False
        """
        if not isinstance(other, Block):
            return False
        return self.location == other.location
    
    def __hash__(self) -> int:
        """
        计算滑块的哈希值
        
        返回：
            int - 基于位置的哈希值，用于集合存储
        """
        return hash(tuple(self.location))
    
    def move(self, direction: str, step: int = 2):
        """
        移动滑块
        
        参数：
            direction: 移动方向 'w'上 's'下 'a'左 'd'右
            step: 移动步数，默认为2
        
        异常：
            ValueError - 无效方向
        """
        if direction == 'w':
            self.location[0] -= step
        elif direction == 's':
            self.location[0] += step
        elif direction == 'a':
            self.location[1] -= step
        elif direction == 'd':
            self.location[1] += step
        else:
            raise ValueError("Invalid direction")


def can_undo_shuffle_step(game, gap_type, line, block, step, directions,
                          before_sel):
    """安全打乱的可逆性校验（2026-10-18，对齐网页版 shuffle_safe）。

    在一步移动 commit **之后**调用：用同一个块触发同一条缝的 opt，遍历该
    缝族的所有方向，看能否把当前选中的分量精确推回 before_sel（该步移动前
    那组块的位置集合）。能 → 该步可逆、保留；不能 → 调用方回滚该步。

    为什么遍历方向而非固定「反方向」：
      · 三角有三种缝隙朝向、米字含斜向半格，「反向」没有统一方向表；
      · 可逆的语义本就是「存在一条同缝合法移动能精确回到移动前」——
        玩家能操作回去就算数，不必纠结是否原路，遍历反而不会误拒。
    分量一致性天然被落点集合覆盖：移动后若与别的块粘成更大一坨，opt 会
    选中更大组，落点集合数量就对不上 before_sel → 判定不可逆（保守但
    安全：宁可少走一步，也不放行任何可能回不去的操作）。

    只读不改：opt/try_move 均不动坐标，调用方随后清 be_opted 即可。
    """
    game.opt(gap_type, line, block)
    if not any(b.be_opted for b in game.blocks):
        return False
    for d in directions:
        back = game.try_move(d, step)
        if back and {tuple(p) for p in back} == before_sel:
            return True
    return False


def commit_shuffle_step(game, gap_type, line, block, direction, step,
                        directions, final_positions, record=None):
    """提交一步打乱移动并做可逆性校验（安全打乱，2026-10-18）。

    对齐网页版 shuffle_safe 的结构：**先提交、再校验、不可逆回滚**——用
    同一个块触发同一条缝的 opt，遍历 directions 看能否把当前选中的分量
    精确推回移动前的位置集合。可逆 → 采纳该步；不可逆 → 回滚坐标与
    record，当作这步没走过（4_4_2 实测约 15% 的随机走法不可逆）。

    为什么值得：每一步都可逆 ⟺ 整条打乱路径反转是一条合法解法 ⟺ 终态
    **保证有解**。于是开局自带一条已知解法，指示、自动求解、关卡生成
    永远有答案；也不可能撞死局（死局都在 cone\\B 里，可逆可达的终态必然
    不在），死局黑名单降级为冗余兜底。

    校验必须在 commit 之后：未提交时 opt 选中的组还在原位，任何方向的
    落点都不可能等于「原位」——放在提交前会恒假（2026-10-18 踩过）。

    record 非 None 时按执行顺序记录；该步被回滚则退回这条记录。
    """
    before_locs = [list(b.location) for b in game.blocks]
    before_sel = {tuple(b.location) for b in game.blocks if b.be_opted}
    if record is not None:
        record_shuffle_move(record, game, gap_type, line, direction, step,
                            final_positions)
    game.commit_move(final_positions)
    ok = can_undo_shuffle_step(game, gap_type, line, block, step, directions,
                               before_sel)
    for b in game.blocks:
        b.be_opted = False
    if ok:
        return True
    # 不可逆：轻量回滚——只写回坐标（保留 Block.number 等其余属性）；
    # matrix 是懒更新缓存，commit_move 本就不动它，无需处理
    for i, b in enumerate(game.blocks):
        b.location = before_locs[i]
    if record is not None:
        record.pop()
    return False


def record_shuffle_move(record, game, gap_type, line, direction, step,
                        final_positions):
    """记录一步打乱移动，供 GUI 演示动画重放（纯数据，无 GUI 依赖）。

    三种形态（方形 / 三角 / 米字）的打乱都是「选缝 → 选中一片 → 平移」，
    与玩家动作同构，因此记录格式通用：

        'moved'     : 该步选中块（be_opted）的移动前位置，与块同序
        'final'     : try_move 返回的移动后位置，与 moved 按索引一一对应
        'gap'       : (gap_type, line) 该步用的缝隙
        'direction' : 移动方向字母
        'step'      : 步长

    GUI 端重放：_find_blocks_at_positions(moved) 找到块对象 →
    start_animation(blocks, final)。调用方传 None 时整体跳过（零开销），
    故 solver/ml 等批量打乱的调用方不受影响。
    """
    record.append({
        'moved': [tuple(b.location) for b in game.blocks if b.be_opted],
        'final': [tuple(p) for p in final_positions],
        'gap': (gap_type, line),
        'direction': direction,
        'step': step,
    })


class SliderMatrix:
    """
    滑块矩阵管理类
    
    采用混合存储方案：
    - Block列表：存储实际滑块对象，支持属性扩展
    - 0-1矩阵：用于高效的位置查询和连通性判断
    
    属性：
        m: int - 初始行数
        n: int - 初始列数
        blocks: list[Block] - 滑块对象列表
        blocks_template: frozenset - 初始状态的滑块集合（用于判断是否复原）
        matrix: list[list[int]] - 0-1矩阵表示地图（1有滑块，0空白）
        matrix_bounds: dict - 矩阵对应的边界范围
    """
    
    __slots__ = ('m', 'n', 'blocks', 'matrix', 'matrix_bounds', 'numbered',
                 'goal_pattern')
    
    def __init__(self, m: int = 6, n: int = 6):
        """
        初始化滑块矩阵
        
        参数：
            m: 初始行数，默认为6
            n: 初始列数，默认为6
        """
        self.m = m
        self.n = n
        self.blocks = []
        
        # 创建初始滑块网格
        for i in range(m):
            for j in range(n):
                self.blocks.append(Block([i, j]))
        
        # 初始化矩阵相关属性
        self.matrix = None
        self.matrix_bounds = None
        # numbered=True 时 update_matrix 将块的编号写入矩阵（整数矩阵），
        # 否则只写 1；默认 False，由 new_puzzle / 载入路径显式置位
        self.numbered = False
        # 自定义还原形态（自由捆绑/设计模式，docs/spec/bandaged_mode.md）：
        # None = 默认满矩形（is_solved 走矩形快路径）；frozenset((r,c),...)
        # = 设计态保存的样式，is_solved 改走 D4 八变换比较（旋转/翻面都算还原）
        self.goal_pattern = None
        self.update_matrix()
    
    def get_boundaries(self) -> dict:
        """
        获取所有滑块的边界范围
        
        返回：
            dict - 包含 min_row, max_row, min_col, max_col
        """
        if not self.blocks:
            return {'min_row': 0, 'max_row': 0, 'min_col': 0, 'max_col': 0}
        
        # 提取所有行和列坐标
        rows = [block.location[0] for block in self.blocks]
        cols = [block.location[1] for block in self.blocks]
        
        return {
            'min_row': min(rows),
            'max_row': max(rows),
            'min_col': min(cols),
            'max_col': max(cols)
        }
    
    def is_valid_h_line(self, line: int) -> bool:
        """
        判断横向分割线是否有效（不在边缘上）
        
        参数：
            line: 分割线所在的行索引
        
        返回：
            bool - 有效返回 True，否则返回 False
        """
        bounds = self.get_boundaries()
        return bounds['min_row'] <= line < bounds['max_row']
    
    def is_valid_v_line(self, line: int) -> bool:
        """
        判断纵向分割线是否有效（不在边缘上）
        
        参数：
            line: 分割线所在的列索引
        
        返回：
            bool - 有效返回 True，否则返回 False
        """
        bounds = self.get_boundaries()
        return bounds['min_col'] <= line < bounds['max_col']

    def side_has_blocks(self, gap_type: str, line, side) -> bool:
        """
        缝隙的指定侧是否有滑块 —— **三形态共有的回放原语**（与
        `game_triangle` / `game_mi` 的同名方法同契约）。

        为什么方形也要有这个：GUI 的宏回放层原本直接调
        `is_valid_h_line` / `is_valid_v_line`，那两个方法**只有方形引擎
        有**，异形（三角/米字）上会 AttributeError；而且它们的语义是
        「在边界盒内」，与异形「线两侧都有块」不是一回事。回放层改吃
        这个方法之后，三形态共用一条路径（gui/events.py 的
        `_execute_next_macro_step`）。

        方形的 side 用 'above'/'below'/'left'/'right'（历史语义，
        MacroStep 存的就是这四个词），异形用 0/1（`side_of` 的口徑）。
        两种都在这里归一，回放层不必分支。
        """
        if gap_type == 'h':
            if not self.is_valid_h_line(line):
                return False
            lo, hi = self.get_boundaries()['min_row'], \
                self.get_boundaries()['max_row']
        elif gap_type == 'v':
            if not self.is_valid_v_line(line):
                return False
            lo, hi = self.get_boundaries()['min_col'], \
                self.get_boundaries()['max_col']
        else:
            return False
        for b in self.blocks:
            v = b.location[0] if gap_type == 'h' else b.location[1]
            on_lo = v <= line
            if side in ('above', 'left', 0) and on_lo:
                return True
            if side in ('below', 'right', 1) and not on_lo:
                return True
        return False

    @staticmethod
    def check_move_valid(selected_positions: set, non_selected_positions: set) -> tuple:
        """
        检查移动后的所有方块位置是否合法（无碰撞且连通）
        
        参数：
            selected_positions: 移动后选中方块的位置集合，元素为 (row, col) 元组
            non_selected_positions: 未选中方块的位置集合，元素为 (row, col) 元组
        
        返回：
            tuple: (is_valid: bool, reason: str)
                - (True, '') 表示合法
                - (False, 'collision') 表示有碰撞
                - (False, 'disconnected') 表示不连通
        """
        # 碰撞检测：选中与未选中位置是否重叠
        if selected_positions & non_selected_positions:
            return (False, 'collision')
        
        # 连通性检测：所有方块是否构成单一连通分量
        all_positions = selected_positions | non_selected_positions
        if not SliderMatrix.is_single_connected(all_positions):
            return (False, 'disconnected')
        
        return (True, '')

    @staticmethod
    def is_single_connected(positions: set) -> bool:
        """
        判断一组位置是否构成单一连通分量（位棋盘版，等价原 set-DFS 语义）。

        位置集合元素为 (row, col) 元组；网格宽度由【实际坐标范围】推导
        （min/max + offset），不依赖 m,n，对任意漂移后的局面都正确。
        """
        if not positions:
            return True
        mask, W, H, col0, colW, off_r, off_c = build_occupancy(positions)
        return is_connected(mask, W, col0, colW)

    def update_matrix(self):
        """
        根据当前滑块列表更新0-1矩阵
        
        矩阵以边界为范围，1表示有滑块，0表示空白
        矩阵坐标与实际坐标通过 matrix_bounds 进行转换
        """
        if not self.blocks:
            self.matrix = []
            self.matrix_bounds = {'min_row': 0, 'max_row': 0, 'min_col': 0, 'max_col': 0}
            return
        
        bounds = self.get_boundaries()
        min_row, max_row = bounds['min_row'], bounds['max_row']
        min_col, max_col = bounds['min_col'], bounds['max_col']
        
        # 计算矩阵大小
        rows = max_row - min_row + 1
        cols = max_col - min_col + 1
        
        # 创建初始化为0的矩阵
        self.matrix = [[0] * cols for _ in range(rows)]
        self.matrix_bounds = bounds
        
        # 在矩阵中标记滑块位置
        # numbered 谜题：整数矩阵，0=空、k=编号为 k 的块（与三角/米字一致，
        # 编号即矩阵值，省去并行 numbers 字段）；其余形态只写 1（占位）。
        for block in self.blocks:
            row = block.location[0] - min_row  # 转换为矩阵行索引
            col = block.location[1] - min_col  # 转换为矩阵列索引
            if getattr(self, 'numbered', False):
                num = getattr(block, 'number', None)
                self.matrix[row][col] = num if num is not None else 1
            else:
                self.matrix[row][col] = 1
    
    def get_matrix(self) -> list[list[int]]:
        """
        获取当前的0-1矩阵（懒加载）
        
        返回：
            list[list[int]] - 0-1矩阵
        """
        if self.matrix is None:
            self.update_matrix()
        return self.matrix
    
    def opt(self, direction: str, line: int, selected_block: 'Block'):
        """
        分割线选中操作 - 位棋盘版（连通分量洪泛，等价原 set-DFS 语义）

        选中 selected_block 所在侧、且与该块连通的那一片（缝隙作为墙，
        不允许跨线连通）。网格宽度由当前坐标实际范围推导，不依赖 m,n。

        参数：
            direction: 分割方向 'h'横向 'v'纵向
            line: 分割线位置（行或列索引）
            selected_block: 玩家选中的方块
        """
        blocks = self.blocks
        # 清除所有选中状态
        for b in blocks:
            b.be_opted = False
        if not blocks:
            return

        cells = [(b.location[0], b.location[1]) for b in blocks]
        mask, W, H, col0, colW, off_r, off_c = build_occupancy(cells)
        if mask == 0:
            return

        sr = selected_block.location[0]
        sc = selected_block.location[1]
        # 选定块所在侧决定 opted 片归属（与原 is_connected 跨线返回 False 等价）
        if direction == 'h':
            side = 'above' if sr <= line else 'below'
        else:
            side = 'left' if sc <= line else 'right'
        side_m = grid_side_mask(W, H, off_r, off_c, direction, line, side)
        opt_mask = mask & side_m
        start_bit = 1 << ((sr - off_r) * W + (sc - off_c))
        if not (opt_mask & start_bit):
            return  # 选定块不在该侧（理论不发生，防御性早退）

        comp = component(opt_mask, start_bit, W, col0, colW)
        # 捆绑扩展（自由捆绑模式，docs/spec/bandaged_mode.md）：
        # 选中片里出现的捆绑组，整组强制选中——捆绑组是刚体，缝隙切不开。
        # 组员若在盘面远处不在 comp 里，也会被拖入选中片（随之平移），
        # 拉扯导致碰撞时由 try_move_ex 拒绝该步（捆绑魔方「转不动」体感）。
        sel_groups = set()
        for b in blocks:
            br, bc = b.location[0], b.location[1]
            if comp & (1 << ((br - off_r) * W + (bc - off_c))):
                b.be_opted = True
                if b.group:
                    sel_groups.add(b.group)
        if sel_groups:
            for b in blocks:
                if b.group and b.group in sel_groups:
                    b.be_opted = True
    
    # ------------------------------------------------------------------
    # 自由捆绑（docs/spec/bandaged_mode.md）
    #   捆绑组是刚体：组内任一块被 opt 选中时整组一起平移（见 opt 的
    #   捆绑扩展），缝隙切不开组；可逆性/有解性由「合法移动收窄为子集」
    #   自动继承。v1 仅方形（4-邻接在整数坐标的占用格上走）。
    # ------------------------------------------------------------------

    def _pos_to_block(self) -> dict:
        """位置 (r,c) → Block 的当前映射（每次调用重建，O(块数)）。"""
        return {(b.location[0], b.location[1]): b for b in self.blocks}

    def bind_path(self, a_pos: tuple, b_pos: tuple):
        """把 a_pos → b_pos 的一条最短路径（4-邻接、只在占用格上走，
        直线优先）上的所有块绑成一个新捆绑组。

        参数：
            a_pos, b_pos: 起止位置 (row, col)

        返回：
            int - 新组编号（≥1）；两端不可达（中间有空位断开）返回 None。
            任一端不是占用格同样返回 None。路径长度为 1（同块）时返回
            其已有组号或 None（无组可退）。
        """
        pmap = self._pos_to_block()
        if a_pos not in pmap or b_pos not in pmap:
            return None
        if a_pos == b_pos:
            g = pmap[a_pos].group
            return g if g else None
        # BFS：直线步（同方向延续）优先——用 (转向次数, 步数) 字典序，
        # 即先走尽量少转弯的最短路（视觉上是一条「顺」的胶带）。
        from collections import deque
        occ = set(pmap)
        start = (a_pos, None)
        dist = {a_pos: 0}
        turn = {a_pos: 0}
        prev = {a_pos: None}
        dq = deque([(a_pos, None)])
        best_b = None
        # 分层 BFS：同层内先扩展直线步
        while dq:
            pos, d = dq.popleft()
            if pos == b_pos:
                best_b = pos
                break
            for nd in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nxt = (pos[0] + nd[0], pos[1] + nd[1])
                if nxt not in occ:
                    continue
                nt = turn[pos] + (0 if d is not None and nd == d else 1)
                if nxt in dist:
                    # 已访问：仅在「转向更少」时更新（保证直线优先）
                    if nt < turn.get(nxt, 99):
                        turn[nxt] = nt
                        prev[nxt] = pos
                        dq.append((nxt, nd))
                    continue
                dist[nxt] = dist[pos] + 1
                turn[nxt] = nt
                prev[nxt] = pos
                dq.append((nxt, nd))
        if best_b is None:
            return None
        # 回溯路径
        path = []
        cur = best_b
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        # 路径上任一块已有组 → 并入该组（组可增长）；否则新建
        gid = 0
        for p in path:
            g = pmap[p].group
            if g:
                gid = g
                break
        if not gid:
            gid = max((b.group for b in self.blocks), default=0) + 1
        for p in path:
            pmap[p].group = gid
        return gid

    def unbind_at(self, pos: tuple) -> bool:
        """解绑 pos 所在捆绑组（整组拆开）。

        返回：该位置原本在组里（执行了解绑）为 True，否则 False。
        """
        pmap = self._pos_to_block()
        b = pmap.get(pos)
        if b is None or not b.group:
            return False
        gid = b.group
        for other in self.blocks:
            if other.group == gid:
                other.group = 0
        return True

    def clear_groups(self) -> int:
        """清空所有捆绑组，返回被解散的组数。"""
        gids = {b.group for b in self.blocks if b.group}
        for b in self.blocks:
            b.group = 0
        return len(gids)

    def groups_summary(self) -> list:
        """当前捆绑组一览：[(gid, [位置...]), ...] 按 gid 排序，供 HUD/视觉。"""
        acc = {}
        for b in self.blocks:
            if b.group:
                acc.setdefault(b.group, []).append((b.location[0], b.location[1]))
        return sorted(acc.items())

    def set_groups_from_positions(self, mapping: dict) -> None:
        """从 {位置: gid} 恢复捆绑状态（history 快照/压缩存档回放用）。

        位置对不上当前块（撤销后盘面已变）的条目静默忽略；先清空再灌入。
        """
        self.clear_groups()
        if not mapping:
            return
        pmap = self._pos_to_block()
        for pos, gid in mapping.items():
            pos = tuple(pos)
            b = pmap.get(pos)
            if b is not None:
                b.group = int(gid)

    def groups_as_positions(self) -> dict:
        """捆绑状态的 {位置: gid} 序列化形式（供快照存档）。"""
        return {(b.location[0], b.location[1]): b.group
                for b in self.blocks if b.group}

    # ------------------------------------------------------------------
    # 自定义还原形态（设计模式：增/减/捆/解 → 保存样式 → 作为谜题目标态）
    #   goal_pattern 是平移归一到原点的 frozenset((r,c),...)；is_solved
    #   走 D4 八变换比较。打乱强度用 pattern_fit（与 goal 的最大 D4 交集率）。
    # ------------------------------------------------------------------

    def set_goal_pattern(self, cells) -> bool:
        """把当前盘面（或给定 cells）设为自定义还原形态。

        传入 cells（可迭代 (r,c)）时直接采用（自动平移归一到原点）；
        不传则取当前盘面。返回是否设置成功（空盘面拒绝）。
        """
        cells = list(cells) if cells is not None else [
            (b.location[0], b.location[1]) for b in self.blocks]
        if not cells:
            return False
        rs = [r for r, _ in cells]
        cs = [c for _, c in cells]
        mr, mc = min(rs), min(cs)
        self.goal_pattern = frozenset((r - mr, c - mc) for r, c in cells)
        return True

    def clear_goal_pattern(self) -> None:
        """清除自定义还原形态，回到默认满矩形判定。"""
        self.goal_pattern = None

    def pattern_fit(self, cells=None) -> float:
        """当前（或给定）形状与 goal_pattern 的 D4 最大交集率（0~1）。

        对 goal 的 8 个 D4 变体各自平移归一到原点，与 cells（同样归一）
        取最大 |交| / |cells|。无 goal_pattern 时退化为「距满矩形的
        填充率」语义不适用，返回 0.0 由调用方处理。
        """
        if cells is None:
            cells = [(b.location[0], b.location[1]) for b in self.blocks]
        cells = list(cells)
        if not cells or self.goal_pattern is None:
            return 0.0

        def norm(s):
            rs = [r for r, _ in s]
            cs = [c for _, c in s]
            mr, mc = min(rs), min(cs)
            return {(r - mr, c - mc) for r, c in s}

        cur = norm(cells)
        g = norm(self.goal_pattern)
        h = max(r for r, _ in g)
        w = max(c for _, c in g)
        best = 0
        base = list(g)
        for _ in range(4):
            for var in (base, [(r, w - c) for r, c in base]):
                best = max(best, len(cur & set(var)))
            base = [(c, h - r) for r, c in base]
        return best / len(cells)

    def apply_pattern(self, cells, groups=None) -> None:
        """按给定样式重塑盘面（自定义谜题初始化/设计态提交）。

        cells 平移归一到原点后重建 blocks（编号形态按行主序重编号）；
        groups 为 {位置(归一后): gid} 恢复捆绑。m/n 更新为边界盒尺寸，
        is_valid_h_line 等边界逻辑随之适配。
        """
        cells = [(r, c) for r, c in cells]
        rs = [r for r, _ in cells]
        cs = [c for _, c in cells]
        mr, mc = min(rs), min(cs)
        norm_cells = sorted((r - mr, c - mc) for r, c in cells)
        self.blocks = []
        numbered = getattr(self, 'numbered', False)
        for i, (r, c) in enumerate(norm_cells):
            b = Block([r, c])
            if numbered:
                b.number = i + 1
            self.blocks.append(b)
        self.m = max(r for r, _ in norm_cells) + 1
        self.n = max(c for _, c in norm_cells) + 1
        self.update_matrix()
        if groups:
            self.set_groups_from_positions(
                {(r - mr, c - mc): gid for (r, c), gid in
                 ((tuple(k), v) for k, v in groups.items())})

    def has_legal_move(self, step: int = 1) -> bool:
        """当前盘面是否存在至少一步合法移动（step=1 即可动性检测）。

        设计态保存样式前必须校验——「缺格小形状可能在单一连通约束下
        完全冻住」（如 3×3 的 L 形：任何移动都会把某块甩成孤立）。
        冻形不是 bug（捆绑魔方精神的极端：Bicube 也只有特定角能转），
        但作为可玩谜题无意义，保存/启用时由 GUI 拦截提示。
        """
        if len(self.blocks) < 2:
            return False
        bounds = self.get_boundaries()
        h_lines = [i for i in range(bounds['min_row'] + 1, bounds['max_row'])
                   if self.is_valid_h_line(i)]
        v_lines = [j for j in range(bounds['min_col'] + 1, bounds['max_col'])
                   if self.is_valid_v_line(j)]
        for gt, lines in (('h', h_lines), ('v', v_lines)):
            dirs = ('a', 'd') if gt == 'h' else ('w', 's')
            for line in lines:
                for blk in self.blocks:
                    self.opt(gt, line, blk)
                    for d in dirs:
                        if self.try_move(d, step):
                            for b in self.blocks:
                                b.be_opted = False
                            return True
                    for b in self.blocks:
                        b.be_opted = False
        return False

    def toggle_block(self, pos: tuple) -> str:
        """设计态：pos 处有块则删除，无块则添加（都是合法操作——
        「放置破坏底层引擎的逻辑」由安全打乱/可逆校验兜底，不在引擎层拦）。

        返回：'added' / 'removed' / 'invalid'（pos 非整数坐标）。
        """
        r, c = pos
        if not (isinstance(r, int) and isinstance(c, int)):
            return 'invalid'
        for i, b in enumerate(self.blocks):
            if b.location[0] == r and b.location[1] == c:
                del self.blocks[i]
                self.update_matrix()
                return 'removed'
        self.blocks.append(Block([r, c]))
        self.update_matrix()
        return 'added'

    def add_block(self, pos: tuple) -> bool:
        """设计态：在空格 pos 添加块（已占用返回 False）。"""
        if any(b.location[0] == pos[0] and b.location[1] == pos[1]
               for b in self.blocks):
            return False
        self.blocks.append(Block([pos[0], pos[1]]))
        self.update_matrix()
        return True

    def remove_block(self, pos: tuple) -> bool:
        """设计态：删除 pos 处的块（无块返回 False）。"""
        for i, b in enumerate(self.blocks):
            if b.location[0] == pos[0] and b.location[1] == pos[1]:
                del self.blocks[i]
                self.update_matrix()
                return True
        return False

    def pattern_export(self) -> dict:
        """导出当前盘面为样式 dict（JSON 可存）：归一 cells + 捆绑 + 尺寸。"""
        cells = [(b.location[0], b.location[1]) for b in self.blocks]
        if not cells:
            return {'cells': [], 'groups': {}, 'm': self.m, 'n': self.n}
        mr = min(r for r, _ in cells)
        mc = min(c for _, c in cells)
        norm = sorted((r - mr, c - mc) for r, c in cells)
        groups = {}
        for b in self.blocks:
            if b.group:
                groups[f'{b.location[0] - mr},{b.location[1] - mc}'] = b.group
        return {
            'cells': [[r, c] for r, c in norm],
            'groups': groups,
            'm': self.m,
            'n': self.n,
        }

    @staticmethod
    def pattern_import(data: dict):
        """从样式 dict 还原 cells 列表 + groups 映射（供 apply_pattern）。

        返回 (cells: list[(r,c)], groups: dict[(r,c), gid])。
        """
        cells = [tuple(p) for p in data.get('cells', [])]
        groups = {}
        for k, v in (data.get('groups') or {}).items():
            r, c = k.split(',')
            groups[(int(r), int(c))] = int(v)
        return cells, groups

    def opt_simple(self, direction: str, line: int, selected_block: 'Block'):
        """
        分割线选中操作 - 简单版本（保留作为参考）
        
        直接根据坐标判断，不考虑连通性，适合规则矩形布局
        
        参数：
            direction: 分割方向 'h'横向 'v'纵向
            line: 分割线位置
            selected_block: 玩家选中的方块
        """
        # 清除所有选中状态
        for block in self.blocks:
            block.be_opted = False
        
        if direction == 'h':
            # 横向分割
            selected_row = selected_block.location[0]
            
            if selected_row <= line:
                # 选中分割线上方的所有方块
                for block in self.blocks:
                    if block.location[0] <= line:
                        block.be_opted = True
            else:
                # 选中分割线下方的所有方块
                for block in self.blocks:
                    if block.location[0] > line:
                        block.be_opted = True
        
        elif direction == 'v':
            # 纵向分割
            selected_col = selected_block.location[1]
            
            if selected_col <= line:
                # 选中分割线左侧的所有方块
                for block in self.blocks:
                    if block.location[1] <= line:
                        block.be_opted = True
            else:
                # 选中分割线右侧的所有方块
                for block in self.blocks:
                    if block.location[1] > line:
                        block.be_opted = True
    
    def is_solved(self) -> bool:
        """
        判断当前是否为复原状态。

        默认（无自定义形态）：检查滑块是否形成完整的 m×n 或 n×m 矩形
        （矩形旋转/翻面后仍是矩形，D4 等价免费成立）。
        自定义形态（goal_pattern，设计模式保存的样式）：当前形状的 D4
        八变换任一与样式平移归一后相同即算还原（旋转/翻面都算）。
        """
        if not self.blocks:
            return False

        cells = frozenset((b.location[0], b.location[1]) for b in self.blocks)

        if self.goal_pattern is not None:
            # 自定义样式：canonicalize = 8 种 D4 变体各自平移归一取最小，
            # 与 solver 的规范形同源（数学文档的 A 集定义同款）
            from solver.table_core import canonicalize
            return canonicalize(cells) == canonicalize(self.goal_pattern)

        rows = [b.location[0] for b in self.blocks]
        cols = [b.location[1] for b in self.blocks]
        min_r, max_r = min(rows), max(rows)
        min_c, max_c = min(cols), max(cols)
        height = max_r - min_r + 1
        width = max_c - min_c + 1
        
        # 必须是 m×n 或 n×m 的矩形
        if not ((height == self.m and width == self.n) or
                (height == self.n and width == self.m)):
            return False
        
        # 矩形内无空洞
        pos_set = cells
        for r in range(min_r, max_r + 1):
            for c in range(min_c, max_c + 1):
                if (r, c) not in pos_set:
                    return False
        return True

    def try_move(self, direction: str, step: int) -> list:
        """
        尝试移动所有选中的滑块（纯逻辑，不含动画/步数/历史）

        使用预测-验证-提交模式：逐步验证（每次1格，共step次），
        所有步骤都通过后才返回最终位置。

        参数：
            direction: 移动方向 'w'上 's'下 'a'左 'd'右
            step: 移动步数

        返回：
            list - 最终位置列表 [(row, col), ...]，如果任何一步不合法返回空列表
        """
        positions, _reason = self.try_move_ex(direction, step)
        return positions

    def try_move_ex(self, direction: str, step: int) -> tuple:
        """
        同 try_move，但额外返回失败原因（供 GUI 提示）。

        返回：
            (positions, reason)
            - positions: 最终位置列表 [(row, col), ...]；失败为空列表
            - reason: '' 成功；'no_selection' 无选中滑块；
                      'all_selected' 全员选中（纯平移，无意义）；
                      'bad_direction' 方向字母无效；
                      'collision' 移动后与未选中滑块重叠；
                      'disconnected' 移动后整体断开（失去单一连通）
        """
        selected = [b for b in self.blocks if b.be_opted]
        non_selected = [b for b in self.blocks if not b.be_opted]

        if not selected:
            return [], 'no_selection'
        if not non_selected:
            # 全员选中 = 整体纯平移：盘面相对构型毫无变化（复原判定平移无关），
            # 且 GUI 交互做不出这种选法（切缝两侧必有块）。碰撞检查在全员
            # 选中时形同虚设（无静块可撞），必须在引擎层显式拒绝，
            # 防脚本/HTTP/重放造出毫无意义的废步。
            return [], 'all_selected'

        non_selected_positions = set(tuple(b.location) for b in non_selected)
        delta_map = DIRECTIONS
        if direction not in delta_map:
            return [], 'bad_direction'
        delta = delta_map[direction]

        # 从当前位置开始，逐步预测
        current = [list(b.location) for b in selected]

        for _ in range(step):
            # 预测下一步位置
            next_pos = [(current[i][0] + delta[0], current[i][1] + delta[1]) for i in range(len(selected))]
            next_set = set(tuple(p) for p in next_pos)

            # 验证：碰撞和连通性
            is_valid, reason = SliderMatrix.check_move_valid(next_set, non_selected_positions)
            if not is_valid:
                return [], reason

            current = next_pos

        return current, ''

    def commit_move(self, final_positions: list):
        """
        提交移动结果，更新选中滑块的位置
        
        参数：
            final_positions: 最终位置列表 [(row, col), ...]
        """
        selected = [b for b in self.blocks if b.be_opted]
        for i, block in enumerate(selected):
            block.location = list(final_positions[i])

    def compute_score(self) -> float:
        """
        计算当前状态的聚拢度 Score（0~1，复原态 = 1.0）

        与 TriangleSliderMatrix/MiSliderMatrix 的方法名保持一致（共同契约），
        实现沿用 solver.heuristic.compute_score；延迟导入避免循环依赖
        （heuristic 反向 import 本模块）。
        """
        from solver.heuristic import compute_score
        return compute_score(self)

    def shuffle(self, attempts: int, step: int, bias: float = 0.0, min_score: float = 0.75,
                record=None):
        """
        随机打乱谜题（纯逻辑，不含动画/GUI状态重置）—— 对外入口。

        死局黑名单防护：黑名单覆盖的谜题（当前仅方形 4_4_2，见
        solver/deadend_guard）终态命中死局黑名单时，回到复原态重新打乱，
        重试上限 100 次（命中概率约万分之 0.16，几乎不可能循环）；超限打印
        警告并接受最后一次结果。其它谜题只跑一次 _shuffle_once，行为不变。

        参数 record：传入 list 时，把每一次成功移动按执行顺序记录进去
        （格式见模块级 record_shuffle_move）。记录全程累积——打乱是从
        打乱前状态连续演变到终态的，GUI 可从打乱前快照按记录逐步重放出
        完整过程；步数过多时由 GUI 决定只演前几步再淡入终局。死局重试
        会回到复原态重打，此时记录已无意义，由调用方清空重取（GUI 在
        重试路径外先存快照，不受影响）。

        安全打乱（2026-10-18 起，对齐网页版 shuffle_safe）：每一步都过
        可逆性校验——同一条缝上存在某方向能把选中组精确推回移动前，否则
        该步作废（4_4_2 实测约 15% 的随机走法不可逆）。于是整条打乱路径
        反转即是一条合法解法，**终态保证有解**：开局自带已知解法，指示、
        自动求解、关卡生成永远有答案；也不可能撞死局（死局都在 cone\\B 里，
        可逆可达的终态必然不在），死局黑名单因此只是冗余兜底。代价是
        有效步数略少于 attempts（约 -15%），min_score 兜底补打乱强度。
        """
        from solver.deadend_guard import has_deadend_guard, is_deadend

        if not has_deadend_guard(self.m, self.n, step):
            self._shuffle_once(attempts, step, bias, min_score, record)
            return

        for retry in range(100):
            if retry:
                # 死局态向前封闭：从死局态出发的任何合法移动仍落在死局集合
                # 里，不先回复原态就重打，重试永远出不去。
                if self.goal_pattern is not None:
                    # 自定义形态：回复到 goal 样式（而非默认满矩形）
                    cells = sorted(self.goal_pattern)
                    for i, b in enumerate(self.blocks):
                        if i < len(cells):
                            b.location = list(cells[i])
                else:
                    for i, b in enumerate(self.blocks):
                        b.location = [i // self.n, i % self.n]
                if record is not None:
                    record.clear()  # 回到复原态重打：上一轮的记录作废
            self._shuffle_once(attempts, step, bias, min_score, record)
            if not is_deadend(self.m, self.n, step,
                              {tuple(b.location) for b in self.blocks}):
                return
        print('警告: 打乱终态连续 100 次命中死局黑名单，接受最后一次结果')

    def _shuffle_once(self, attempts: int, step: int, bias: float = 0.0, min_score: float = 0.75,
                      record=None):
        """
        单次随机打乱核心（终态死局防护的包装在 shuffle）。

        模拟玩家随机滑动操作，直接更新滑块位置。

        参数：
            attempts: 打乱尝试次数
            step: 每次移动的步数
            bias: 偏置强度（0=纯随机，>0=偏向更散的状态）
                  bias>0 时用 Metropolis 准则：向更紧凑的移动按概率拒绝，
                  使打乱结果偏向深层状态（离复原更远）。
            min_score: 洗牌完成后检验聚拢度阈值。
                       若最终状态的 compute_score > min_score（太容易还原），
                       则丢弃并重洗，直到满足条件或达到重试上限。
                       设为 None 时不检验。
        """
        import random

        def _scatter(coords):
            """散度 = 1 - compute_score（内联避免循环导入）。

            0 = 复原态，越大越散。等价于 solver.heuristic.compute_score 的反值。
            """
            if not coords:
                return 0.0
            rs = [r for r, _ in coords]
            cs = [c for _, c in coords]
            H = max(rs) - min(rs) + 1
            W = max(cs) - min(cs) + 1
            K = self.m * self.n
            fill_rate = K / (H * W) if H * W > 0 else 0.0
            min_dim, max_dim = min(self.m, self.n), max(self.m, self.n)
            target_ratio = max_dim / min_dim if min_dim > 0 else 1.0
            min_hw, max_hw = min(H, W), max(H, W)
            current_ratio = max_hw / min_hw if min_hw > 0 else 1.0
            max_ratio = max(current_ratio, target_ratio)
            aspect_error = abs(current_ratio - target_ratio) / max_ratio if max_ratio > 0 else 0.0
            score = 0.5 * fill_rate + 0.5 * (1.0 - aspect_error)
            return 1.0 - score

        cur_scatter = _scatter({tuple(b.location) for b in self.blocks})

        for _ in range(attempts):
            bounds = self.get_boundaries()
            min_row, max_row = bounds['min_row'], bounds['max_row']
            min_col, max_col = bounds['min_col'], bounds['max_col']

            # 收集所有有效缝隙
            h_lines = [i for i in range(min_row + 1, max_row) if self.is_valid_h_line(i)]
            v_lines = [j for j in range(min_col + 1, max_col) if self.is_valid_v_line(j)]
            all_gaps = [('h', line) for line in h_lines] + [('v', line) for line in v_lines]

            if not all_gaps:
                continue

            # 随机选择一个缝隙
            gap_type, line = random.choice(all_gaps)

            # 根据缝隙类型选择合法方向
            if gap_type == 'h':
                direction = random.choice(['a', 'd'])
            else:
                direction = random.choice(['w', 's'])

            # 随机选择一个滑块来触发 opt
            block = random.choice(self.blocks)
            self.opt(gap_type, line, block)

            # 使用 try_move 验证并获取最终位置
            final_positions = self.try_move(direction, step)
            if not final_positions:
                # 不合法，清除选中状态继续
                for b in self.blocks:
                    b.be_opted = False
                continue

            # bias 模式：Metropolis 接受准则
            if bias > 0:
                import math
                # 从候选位置计算散度（不需要 commit，直接算）
                non_sel = {tuple(b.location) for b in self.blocks if not b.be_opted}
                cand_coords = non_sel | {tuple(p) for p in final_positions}
                cand_scatter = _scatter(cand_coords)
                # 候选更紧凑（散度下降）→ 按概率拒绝
                if cand_scatter < cur_scatter:
                    if random.random() >= math.exp(bias * (cand_scatter - cur_scatter)):
                        # 拒绝：不提交，清除选中
                        for b in self.blocks:
                            b.be_opted = False
                        continue

            # 安全打乱（对齐网页版 shuffle_safe）：提交 + 可逆性校验，
            # 不可逆自动回滚该步——整条打乱路径反转即是合法解法，终态
            # 保证有解；4_4_2 实测约 15% 的随机走法过不了这一关
            if commit_shuffle_step(
                    self, gap_type, line, block, direction, step,
                    ('a', 'd') if gap_type == 'h' else ('w', 's'),
                    final_positions, record):
                if bias > 0:
                    cur_scatter = cand_scatter  # 校验通过才真正接受该候选
        # 确保最终清除所有选中状态
        for b in self.blocks:
            b.be_opted = False

        # min_score 校验：聚拢度过高说明题目太简单，重洗直到满足要求
        if min_score is not None:
            import math as _math
            max_retries = attempts * 3  # 最多重试 3 倍原次数
            def _cur_score():
                rs = [r for r, _ in coords]
                cs = [c for _, c in coords]
                H = max(rs) - min(rs) + 1
                W = max(cs) - min(cs) + 1
                K = self.m * self.n
                fill_rate = K / (H * W) if H * W > 0 else 0.0
                min_dim, max_dim = min(self.m, self.n), max(self.m, self.n)
                target_ratio = max_dim / min_dim if min_dim > 0 else 1.0
                min_hw, max_hw = min(H, W), max(H, W)
                current_ratio = max_hw / min_hw if min_hw > 0 else 1.0
                max_ratio = max(current_ratio, target_ratio)
                aspect_error = abs(current_ratio - target_ratio) / max_ratio if max_ratio > 0 else 0.0
                return 0.5 * fill_rate + 0.5 * (1.0 - aspect_error)
            for _ in range(max_retries):
                coords = {tuple(b.location) for b in self.blocks}
                if self.goal_pattern is not None:
                    # 自定义形态（设计模式样式）：强度判据换成「与 goal 的
                    # D4 最大交集率」——fit 过高 = 终态太像还原态 = 太简单。
                    # 默认满矩形路径不受影响。
                    if self.pattern_fit(coords) <= min_score:
                        break
                elif _cur_score() <= min_score:
                    break
                # 不够散，重新打乱（带 bias 加速）
                found_good = False
                for _attempt in range(attempts):
                    bounds = self.get_boundaries()
                    min_row, max_row = bounds['min_row'], bounds['max_row']
                    min_col, max_col = bounds['min_col'], bounds['max_col']
                    h_lines = [i for i in range(min_row + 1, max_row) if self.is_valid_h_line(i)]
                    v_lines = [j for j in range(min_col + 1, max_col) if self.is_valid_v_line(j)]
                    all_gaps = [('h', line) for line in h_lines] + [('v', line) for line in v_lines]
                    if not all_gaps:
                        continue
                    gap_type, line = random.choice(all_gaps)
                    direction = random.choice(['a', 'd']) if gap_type == 'h' else random.choice(['w', 's'])
                    block = random.choice(self.blocks)
                    self.opt(gap_type, line, block)
                    final_positions = self.try_move(direction, step)
                    if not final_positions:
                        for b in self.blocks:
                            b.be_opted = False
                        continue
                    if bias > 0:
                        non_sel = {tuple(b.location) for b in self.blocks if not b.be_opted}
                        cand_coords = non_sel | {tuple(p) for p in final_positions}
                        rs2 = [r for r, _ in cand_coords]
                        cs2 = [c for _, c in cand_coords]
                        H2 = max(rs2) - min(rs2) + 1
                        W2 = max(cs2) - min(cs2) + 1
                        K2 = self.m * self.n
                        fr2 = K2 / (H2 * W2) if H2 * W2 > 0 else 0.0
                        min_d2, max_d2 = min(self.m, self.n), max(self.m, self.n)
                        tr2 = max_d2 / min_d2 if min_d2 > 0 else 1.0
                        mh2, mx2 = min(H2, W2), max(H2, W2)
                        cr2 = mx2 / mh2 if mh2 > 0 else 1.0
                        mr2 = max(cr2, tr2)
                        ae2 = abs(cr2 - tr2) / mr2 if mr2 > 0 else 0.0
                        cand_score = 0.5 * fr2 + 0.5 * (1.0 - ae2)
                        cur_s = _cur_score()
                        if cand_score > cur_s or random.random() >= _math.exp(bias * (cand_score - cur_s)):
                            pass
                        else:
                            for b in self.blocks:
                                b.be_opted = False
                            continue
                    # 安全打乱（同主循环）：提交 + 可逆性校验，不可逆
                    # 自动回滚该步——终态可解是无条件保证，与 record 无关
                    commit_shuffle_step(
                        self, gap_type, line, block, direction, step,
                        ('a', 'd') if gap_type == 'h' else ('w', 's'),
                        final_positions, record)
                # 檢查這次重洗是否滿足條件
                coords = {tuple(b.location) for b in self.blocks}
                if _cur_score() <= min_score:
                    found_good = True
                    break
                # 否則繼續下一次重試（不 break else 子句）

    def export_map(self) -> str:
        """
        导出当前地图为字符串格式
        
        使用 '#' 表示滑块，'_' 表示空白
        
        返回：
            str - 地图字符串（每行一个字符串，用换行符分隔）
        """
        # 直接用 0-1 矩阵生成（O(格数)），不再对每格遍历全部滑块（O(块×格)）
        self.update_matrix()
        if not self.matrix:
            return ''
        return '\n'.join(''.join('#' if v else '_' for v in row)
                         for row in self.matrix)
    
    def import_map(self, map_str: str) -> bool:
        """
        从字符串导入地图
        
        参数：
            map_str: 地图字符串（'#'表示滑块，其他字符表示空白）
        
        返回：
            bool - 导入成功返回 True，失败返回 False
        """
        # 解析地图字符串
        lines = [line.strip() for line in map_str.strip().split('\n') if line.strip()]
        
        if not lines:
            return False
        
        # 清空现有滑块
        self.blocks = []
        self.m = len(lines)
        self.n = len(lines[0]) if lines else 0
        
        # 根据字符串创建滑块
        for row_idx, line in enumerate(lines):
            for col_idx, char in enumerate(line):
                if char == '#':
                    self.blocks.append(Block([row_idx, col_idx]))
        
        # 更新矩阵
        self.update_matrix()
        return True
