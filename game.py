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


class Block:
    """
    单个滑块对象类
    
    属性：
        location: list[int] - 滑块的坐标位置 [行, 列]
        be_opted: bool - 是否被选中（用于高亮显示）
    """
    
    __slots__ = ('location', 'be_opted')
    
    def __init__(self, location: list[int], be_opted: bool = False):
        """
        初始化滑块对象
        
        参数：
            location: 初始坐标位置 [行, 列]
            be_opted: 是否被选中，默认为 False
        """
        self.location = location
        self.be_opted = be_opted
    
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
    
    __slots__ = ('m', 'n', 'blocks', 'matrix', 'matrix_bounds')
    
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
        判断一组位置是否构成单一连通分量（使用DFS）
        
        参数：
            positions: 位置集合，元素为 (row, col) 元组
        
        返回：
            bool - 所有位置连通返回 True，否则返回 False
        """
        if not positions:
            return True
        
        # 从任意一个位置开始DFS
        start = next(iter(positions))
        visited = set()
        stack = [start]
        
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            
            row, col = current
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                neighbor = (row + dr, col + dc)
                if neighbor in positions and neighbor not in visited:
                    stack.append(neighbor)
        
        # 如果访问到的位置数等于总位置数，则连通
        return len(visited) == len(positions)

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
        for block in self.blocks:
            row = block.location[0] - min_row  # 转换为矩阵行索引
            col = block.location[1] - min_col  # 转换为矩阵列索引
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
        分割线选中操作 - 使用DFS算法
        
        根据分割线将滑块组划分为连通部分，标记选中方块所在的部分
        
        参数：
            direction: 分割方向 'h'横向 'v'纵向
            line: 分割线位置（行或列索引）
            selected_block: 玩家选中的方块
        """
        # 清除所有选中状态
        for block in self.blocks:
            block.be_opted = False
        
        # 将滑块位置存入集合以便快速查找
        block_set = set(tuple(b.location) for b in self.blocks)
        
        def is_connected(block1: tuple, block2: tuple, direction: str, line: int) -> bool:
            """
            判断两个方块是否连通（不被分割线隔开）
            
            参数：
                block1: 第一个方块的坐标 (row, col)
                block2: 第二个方块的坐标 (row, col)
                direction: 分割方向
                line: 分割线位置
            
            返回：
                bool - 连通返回 True，否则返回 False
            """
            if direction == 'h':
                # 横向分割：检查两个方块是否在分割线同一侧
                if (block1[0] <= line and block2[0] > line) or \
                   (block1[0] > line and block2[0] <= line):
                    return False
            else:
                # 纵向分割：检查两个方块是否在分割线同一侧
                if (block1[1] <= line and block2[1] > line) or \
                   (block1[1] > line and block2[1] <= line):
                    return False
            return True
        
        def get_neighbors(pos: tuple) -> list:
            """
            获取一个位置的相邻方块位置
            
            参数：
                pos: 当前位置 (row, col)
            
            返回：
                list - 相邻的方块位置列表
            """
            row, col = pos
            neighbors = []
            # 检查上下左右四个方向
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                new_pos = (row + dr, col + dc)
                if new_pos in block_set:
                    neighbors.append(new_pos)
            return neighbors
        
        # 使用DFS遍历连通块
        start_pos = tuple(selected_block.location)
        visited = set()
        stack = [start_pos]
        
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            
            visited.add(current)
            
            # 将连通的邻居加入栈
            for neighbor in get_neighbors(current):
                if neighbor not in visited and is_connected(current, neighbor, direction, line):
                    stack.append(neighbor)
        
        # 标记所有连通的方块为选中状态
        for block in self.blocks:
            if tuple(block.location) in visited:
                block.be_opted = True
    
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
        判断当前是否为复原状态（检查滑块是否形成完整的 m×n 或 n×m 矩形）
        
        返回：
            bool - 复原返回 True，否则返回 False
        """
        if not self.blocks:
            return False
        
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
        pos_set = set((b.location[0], b.location[1]) for b in self.blocks)
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
                      'collision' 移动后与未选中滑块重叠；
                      'disconnected' 移动后整体断开（失去单一连通）
        """
        selected = [b for b in self.blocks if b.be_opted]
        non_selected = [b for b in self.blocks if not b.be_opted]

        if not selected:
            return [], 'no_selection'

        non_selected_positions = set(tuple(b.location) for b in non_selected)
        delta_map = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}
        if direction not in delta_map:
            return [], 'no_selection'
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

    def shuffle(self, attempts: int, step: int):
        """
        随机打乱谜题（纯逻辑，不含动画/GUI状态重置）
        
        模拟玩家随机滑动操作，直接更新滑块位置。
        
        参数：
            attempts: 打乱尝试次数
            step: 每次移动的步数
        """
        import random
        
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
            
            # 提交移动
            self.commit_move(final_positions)
            
            # 清除选中状态
            for b in self.blocks:
                b.be_opted = False
        
        # 确保最终清除所有选中状态
        for b in self.blocks:
            b.be_opted = False

    def export_map(self) -> str:
        """
        导出当前地图为字符串格式
        
        使用 '#' 表示滑块，'_' 表示空白
        
        返回：
            str - 地图字符串（每行一个字符串，用换行符分隔）
        """
        bounds = self.get_boundaries()
        min_row, max_row = bounds['min_row'], bounds['max_row']
        min_col, max_col = bounds['min_col'], bounds['max_col']
        
        rows = []
        for row in range(min_row, max_row + 1):
            line = []
            for col in range(min_col, max_col + 1):
                # 检查该位置是否有滑块
                has_block = any(block.location == [row, col] for block in self.blocks)
                line.append('#' if has_block else '_')
            rows.append(''.join(line))
        
        return '\n'.join(rows)
    
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
