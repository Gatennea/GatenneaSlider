# -*- coding: utf-8 -*-
"""
历史记录模块

采用状态快照方式记录游戏历史，支持撤销和重做。
每条记录保存滑块布局的 0-1 矩阵和边界信息。

快照合并（省空间）：同一次选中（同一 session_key）下的连续移动只占一个
矩阵快照，逐步动作日志存进 'moves'，'steps' 记该快照覆盖的步数，
'step_total' 记到该快照为止的累计步数。撤销粒度 = 每步：首次撤销到该段时
用 moves 日志惰性拆成「一步一条」，之后走普通撤销/重做逻辑。
"""

from game import Block

_DIRS = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}


# ---------------------------------------------------------------- 捆绑组编解码
# 内存里捆绑态是 {位置: gid}（tuple 当 key），json.dumps 不接受 tuple key，
# 落盘必须换成 JSON 安全形式：[[r, c, gid], ...]（排序保稳、紧凑）。
#
# 位置长度随形态变：方形 2 元 (r,c)、三角 3 元 (i,j,up)、米字 3 元 (r,c,q)。
# 落盘统一写成「位置各分量 + gid」——最后一格恒为 gid，前面的都是坐标，
# 因此 2 元与 3 元位置共用同一套读写，方形旧档（[r,c,gid]）天然兼容。
def _coord_to_json(x):
    """坐标分量 → JSON 值（整数就写整数；三角/米字的半格坐标保留小数）。"""
    f = float(x)
    return int(f) if f.is_integer() else f


def _coord_from_json(x):
    """JSON 坐标 → 数值（整数值还原成 int，否则 float）。"""
    f = float(x)
    return int(f) if f.is_integer() else f


def _comp_to_json(x):
    """位置分量 → JSON 值。三角的 up 是 bool（写成 1/0），米字的 q 是字母（原样）。"""
    if isinstance(x, str):
        return x
    if isinstance(x, bool):
        return 1 if x else 0
    return _coord_to_json(x)


def _comp_from_json(x):
    """JSON 值 → 位置分量。字母原样保留；其余转数值（"2" 这类手改值也认）。"""
    if isinstance(x, str):
        try:
            return _coord_from_json(x)
        except (TypeError, ValueError):
            return x
    return _coord_from_json(x)


def groups_to_json(mapping):
    """{位置: gid} → 落盘的 [[坐标..., gid], ...]；空/None 返回 None（不写字段省空间）。

    允许传入已经是落盘形式的 list（或字符串 key 的 dict）——内存态与落盘态
    在几条转换路径上会混用，先归一再序列化，避免炸在 `.items()` 上。
    """
    if not mapping:
        return None
    if isinstance(mapping, (list, tuple)) or (
            isinstance(mapping, dict)
            and not all(isinstance(k, tuple) for k in mapping)):
        mapping = groups_from_json(mapping) or {}
    out = []
    for pos, gid in mapping.items():
        out.append([_comp_to_json(comp) for comp in pos] + [int(gid)])
    out.sort()
    return out


def groups_from_json(raw):
    """落盘形式 → {位置: gid}；兼容 [[r,c,gid]...]、[[i,j,up,gid]...] 与 {"r,c": gid}。"""
    if not raw:
        return None
    out = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                pos = tuple(_comp_from_json(p) for p in str(k).split(','))
                if len(pos) < 2:
                    continue
                out[pos] = int(v)
            except (ValueError, TypeError):
                continue
    elif isinstance(raw, (list, tuple)):
        for item in raw:
            # 最后一格是 gid，前面都是坐标分量（2 元/3 元位置都走这条）
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            try:
                pos = tuple(_comp_from_json(p) for p in item[:-1])
                out[pos] = int(item[-1])
            except (ValueError, TypeError):
                continue
    return out or None


def snapshot_groups(snap):
    """快照 → {位置: gid}（内存态可能是 tuple-key dict，也可能是落盘形式）。"""
    if not isinstance(snap, dict):
        return None
    raw = snap.get('groups')
    if not raw:
        return None
    if isinstance(raw, dict):
        # 内存快照直接用 tuple-key dict；JSON 读回来的是字符串 key
        if all(isinstance(k, tuple) for k in raw):
            return {tuple(k): int(v) for k, v in raw.items()}
        return groups_from_json(raw)
    return groups_from_json(raw)


def validate_snapshot(snap, kind='square'):
    """载入存档前校验单条快照的 matrix/bounds 是否合法。

    目的：坏数据（matrix 存成字符串/标量、行宽不齐、尺寸与包围盒不符、
    单元类型非整数、三角/米字位打包超出值域）一律判失败，绝不静默当成功载入
    —— 否则会生成死局并把垃圾原样写回磁盘。

    合法则返回 None；非法抛出 ValueError（带中文说明），由上层转成用户提示。
    """
    if not isinstance(snap, dict):
        raise ValueError('快照不是对象')
    matrix = snap.get('matrix')
    bounds = snap.get('bounds')
    if matrix is None or bounds is None:
        raise ValueError('快照缺少 matrix 或 bounds')
    if not isinstance(matrix, list) or len(matrix) == 0:
        raise ValueError('matrix 不是非空二维数组（可能存成了字符串/标量）')
    if not all(isinstance(row, list) for row in matrix):
        raise ValueError('matrix 行不是数组（可能存成了字符串）')
    nrows = len(matrix)
    ncols = None
    for row in matrix:
        if ncols is None:
            ncols = len(row)
            if ncols == 0:
                raise ValueError('matrix 行宽为 0')
        elif len(row) != ncols:
            raise ValueError('matrix 行宽不一致')
        for v in row:
            # bool 是 int 的子类，必须显式排除（True/False 不是合法编号）
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError('matrix 单元不是整数')
    if not isinstance(bounds, dict):
        raise ValueError('bounds 不是对象')
    for key in ('min_row', 'max_row', 'min_col', 'max_col'):
        kv = bounds.get(key)
        if not isinstance(kv, int) or isinstance(kv, bool):
            raise ValueError(f'bounds.{key} 缺失或非整数')
    if bounds['min_row'] > bounds['max_row'] or bounds['min_col'] > bounds['max_col']:
        raise ValueError('bounds 区间非法（min 大于 max）')
    bh = bounds['max_row'] - bounds['min_row'] + 1
    bw = bounds['max_col'] - bounds['min_col'] + 1
    if bh != nrows or bw != ncols:
        raise ValueError('matrix 尺寸与 bounds 不一致')
    # 值域：三角/米字是位打包，超范围会静默丢位 → 拒绝；
    # 方形/编号：0=空、>0=块（含编号），仅要求非负整数
    if kind == 'triangle':
        for row in matrix:
            for v in row:
                if v < 0 or v > 3:
                    raise ValueError('三角形 matrix 单元超出 0~3')
    elif kind == 'mi':
        for row in matrix:
            for v in row:
                if v < 0 or v > 255:
                    raise ValueError('米字格 matrix 单元超出 0~255')
    else:
        for row in matrix:
            for v in row:
                if v < 0:
                    raise ValueError('matrix 单元为负数')

    # 捆绑组（自由捆绑 / 高级选项）：坏数据（负数 gid、条目不是 [坐标...,gid]）
    # 直接判失败——否则载入后 gid 会被塞进块里，产生无法解释的刚性约束。
    # 条目最后一格恒为 gid（前面是 2 元/3 元位置），故统一取 item[-1]；
    # 三角/米字也带捆绑，三种形态一概校验。
    raw_groups = snap.get('groups')
    if raw_groups:
        if isinstance(raw_groups, dict):
            gids = list(raw_groups.values())
        elif isinstance(raw_groups, (list, tuple)):
            gids = []
            for item in raw_groups:
                if not isinstance(item, (list, tuple)) or len(item) < 3:
                    raise ValueError('快照 groups 条目格式错误（应为 [坐标..., gid]）')
                gids.append(item[-1])
        else:
            raise ValueError('快照 groups 不是数组')
        for gid in gids:
            if not isinstance(gid, int) or isinstance(gid, bool) or gid <= 0:
                raise ValueError('快照 groups 的 gid 不是正整数')


def snapshot_cells(snap) -> frozenset:
    """快照 → 绝对坐标格集 {(r, c)}"""
    bounds = snap.get('bounds', {})
    min_row = bounds.get('min_row', 0)
    min_col = bounds.get('min_col', 0)
    return frozenset(
        (min_row + i, min_col + j)
        for i, row in enumerate(snap.get('matrix', []))
        for j, v in enumerate(row) if v)


def cells_to_snapshot(cells: set, num_map: dict = None) -> dict:
    """绝对坐标格集 → {matrix, bounds}（紧凑包围盒）。

    num_map 提供 (r, c) -> 编号 时，矩阵写成整数（编号即矩阵值，0=空）；
    否则占位写 1。带序号谜题逐步拆分的「中间态」靠 num_map 携带编号，
    使撤销拆分出的每帧快照都自带编号（否则还原会丢号）。
    """
    mnr = min(r for r, _ in cells)
    mxr = max(r for r, _ in cells)
    mnc = min(c for _, c in cells)
    mxc = max(c for _, c in cells)
    matrix = []
    for i, r in enumerate(range(mnr, mxr + 1)):
        row = []
        for j, c in enumerate(range(mnc, mxc + 1)):
            if (r, c) in cells:
                if num_map is not None:
                    row.append(num_map.get((r, c), 1))
                else:
                    row.append(1)
            else:
                row.append(0)
        matrix.append(row)
    return {'matrix': matrix,
            'bounds': {'min_row': mnr, 'max_row': mxr,
                       'min_col': mnc, 'max_col': mxc}}


def snapshot_numbers(snap) -> dict:
    """快照的编号表 → {(r, c): 编号}。

    编号谜题的整数矩阵里「值即编号」（0=空），直接读取即可；
    方形/无编号（矩阵全 1）返回 {}。用「是否存在 >1 的值」判定编号矩阵
    （编号 k>=2 必含 >1；1x1 退化局忽略）。
    """
    matrix = snap.get('matrix', [])
    if not matrix:
        return {}
    bounds = snap.get('bounds', {})
    min_row = bounds.get('min_row', 0)
    min_col = bounds.get('min_col', 0)
    if not any(v > 1 for row in matrix for v in row):
        return {}
    return {(min_row + i, min_col + j): val
            for i, row in enumerate(matrix)
            for j, val in enumerate(row) if val}


def compose_move_info(moves: list):
    """把一段连续移动合成一个动作（供撤销/重做整段位移动画）。

    选中组整体刚性平移，各块位移一致 → 合成位移 = 各步位移之和。
    单步时原样返回；多步时附 'delta'（格数）与 'merged'（步数）。
    """
    if not moves:
        return None
    if len(moves) == 1:
        return moves[0]
    first = moves[0]
    dr = dc = 0
    same_dir = True
    for mv in moves:
        d = _DIRS.get(mv.get('direction') or '', (0, 0))
        k = mv.get('step', 1)
        dr += d[0] * k
        dc += d[1] * k
        if mv.get('direction') != first.get('direction'):
            same_dir = False
    return {
        'gap_type': first.get('gap_type'),
        'gap_line': first.get('gap_line'),
        'direction': first.get('direction') if same_dir else None,
        'step': sum(mv.get('step', 1) for mv in moves),
        'delta': [dr, dc],
        'moved_positions': first.get('moved_positions') or [],
        'merged': len(moves),
    }


def expand_snapshot_moves(prev_snap, snap) -> list:
    """快照 → [(动作前快照, 动作后快照, move_info), ...]（逐步展开）。

    合并快照只存会话末态矩阵，中间态按 moves 日志里的逐步位移重建，
    使标注数据集/训练导出仍能拿到每步的动作前矩阵。
    """
    moves = snap.get('moves')
    if not moves:
        mv = snap.get('move_info')
        return [(prev_snap, snap, mv)] if mv else []
    if len(moves) == 1:
        return [(prev_snap, snap, moves[0])]
    if not all(mv and mv.get('moved_positions') for mv in moves):
        return [(prev_snap, snap, moves[-1])]
    cells = set(snapshot_cells(prev_snap))
    # 带序号：编号随块一起动（块移动不换号），逐步重建中间态的编号表
    num_map = snapshot_numbers(prev_snap)
    # 捆绑关系同理：整组一起平移，中间态必须带上 groups，
    # 否则撤销拆到该段中点时 set_groups_from_positions(None) 会把捆绑清掉。
    grp = snapshot_groups(prev_snap) or {}
    out = []
    pre = prev_snap
    for i, mv in enumerate(moves):
        d = _DIRS.get(mv.get('direction') or '', (0, 0))
        k = mv.get('step', 1)
        dr, dc = d[0] * k, d[1] * k
        moved = {tuple(p) for p in mv['moved_positions']}
        cells = (cells - moved) | {(r + dr, c + dc) for r, c in moved}
        if not cells:
            break
        if num_map:
            shifted = {(r + dr, c + dc): v for (r, c), v in num_map.items()
                       if (r, c) in moved}
            num_map = {p: v for p, v in num_map.items() if p not in moved}
            num_map.update(shifted)
        if grp:
            g_shift = {(r + dr, c + dc): g for (r, c), g in grp.items()
                       if (r, c) in moved}
            grp = {p: g for p, g in grp.items() if p not in moved}
            grp.update(g_shift)
        post = snap if i == len(moves) - 1 else cells_to_snapshot(cells, num_map)
        if post is not snap and grp:
            post['groups'] = dict(grp)
        out.append((pre, post, mv))
        pre = post
    return out


class GameHistory:
    """
    游戏历史记录管理类
    
    属性：
        history: list[dict] - 操作历史栈，每条记录包含 matrix 和 bounds
        history_index: int - 当前位置指针
    """
    
    __slots__ = ('history', 'history_index')
    
    def __init__(self):
        """初始化历史记录"""
        self.history = []
        self.history_index = -1
    
    def save_snapshot(self, game, move_info=None, session_key=None):
        """
        保存当前游戏状态快照到历史记录

        参数：
            game: SliderMatrix 游戏对象
            move_info: dict 或 None - 移动元数据（用于撤销/重做动画）
            session_key: 选中会话标识；与末条快照相同且给了 move_info 时，
                本次移动并入该快照（只留末态矩阵 + 逐步日志），否则新开一条。
                None = 不合并（参考态、宏/求解器播放等）。
        """
        # 更新矩阵
        game.update_matrix()

        # 引擎板型（通用带朝向模型）携带无损键表快照：矩阵编码会把同格多块
        # 压成一格，撤销时丢块。restore_snapshot 优先用它还原。其他形态忽略。
        # ⚠️ 只在「會走通用分支」时计算：三角(self.k→2-bit 专属分支)、米字
        # (self.Q_ORDER→8-bit 专属分支) 的块朝向不在 spec.orientations 里，
        # 调用 snapshot_state 会因 index 找不到朝向而崩；且二者位打包已无损，
        # 也不需要 engine_state。模型板型(shield/shatter…)才走通用分支、矩阵
        # 编码丢同格多块，才有必要算。
        _spec = getattr(game, 'spec', None)
        _engine_generic = (
            _spec is not None
            and _spec.orientations
            and not hasattr(game, 'k')
            and not hasattr(game, 'Q_ORDER')
        )
        engine_state = (game.snapshot_state()
                        if (_engine_generic
                            and hasattr(game, 'snapshot_state')) else None)

        # 如果当前不在历史末尾，截断后续记录
        if self.history_index < len(self.history) - 1:
            self.history = self.history[:self.history_index + 1]

        # 合并：同一次选中的连续移动只占一个矩阵快照
        if (session_key is not None and move_info is not None and self.history
                and self.history[-1].get('session_key') == session_key):
            snap = self.history[-1]
            snap['matrix'] = [row[:] for row in game.matrix]
            snap['bounds'] = dict(game.matrix_bounds)
            snap['moves'].append(move_info)
            snap['steps'] += 1
            snap['step_total'] += 1
            snap['move_info'] = compose_move_info(snap['moves'])
            # 捆绑状态随快照更新（自由捆绑；无组时 None 省空间）
            snap['groups'] = (game.groups_as_positions()
                              if hasattr(game, 'groups_as_positions') else None)
            snap['engine_state'] = engine_state
            # 编号直接存在 matrix（整数矩阵，值即编号），无需并行 numbers 字段
            return

        prev_total = self.history[-1].get('step_total', 0) if self.history else 0
        steps = 1 if move_info else 0
        snapshot = {
            'matrix': [row[:] for row in game.matrix],
            'bounds': dict(game.matrix_bounds),
            'move_info': move_info,
            'moves': [move_info] if move_info else [],
            'steps': steps,
            'step_total': prev_total + steps,
            'session_key': session_key,
            # 捆绑状态（自由捆绑模式）：{位置: gid}；无组为 None
            'groups': (game.groups_as_positions()
                       if hasattr(game, 'groups_as_positions') else None),
            # 引擎板型无损键表（矩阵编码丢同格多块；还原优先用它）
            'engine_state': engine_state,
        }
        # 编号直接存在 matrix（整数矩阵，值即编号），无需并行 numbers 字段

        # 追加快照
        self.history.append(snapshot)
        self.history_index = len(self.history) - 1

    def step_total_at(self, index: int) -> int:
        """快照 index 处的累计步数（旧存档无该字段时退回索引值）。"""
        if index < 0 or index >= len(self.history):
            return 0
        return self.history[index].get('step_total', index)

    def current_step_total(self) -> int:
        """当前历史位置的累计步数。"""
        return self.step_total_at(self.history_index)

    
    def restore_snapshot(self, game, index: int):
        """
        根据历史快照恢复游戏状态
        
        参数：
            game: SliderMatrix 游戏对象
            index: 历史记录索引
        """
        if index < 0 or index >= len(self.history):
            return
        
        snapshot = self.history[index]
        matrix = snapshot['matrix']
        bounds = snapshot['bounds']
        
        min_row = bounds['min_row']
        min_col = bounds['min_col']

        if hasattr(game, 'k'):
            # 三角形密鋪：matrix 為菱形胞 2-bit 網格（bit0=▲、bit1=▼）
            game.blocks = []
            for row_idx, row in enumerate(matrix):
                for col_idx, val in enumerate(row):
                    if val & 1:
                        game.blocks.append(Block([min_row + row_idx, min_col + col_idx, True]))
                    if val & 2:
                        game.blocks.append(Block([min_row + row_idx, min_col + col_idx, False]))
        elif hasattr(game, 'Q_ORDER'):
            # 米字格：matrix 為每格 8-bit 網格
            # （bit 0~3 = A 晶格塊 [R,C,q]；bit 4~7 = B 晶格塊 [R+½,C+½,q]，
            #  即同一格裡錯開半格的那套三角——斜向一格會產生這種錯位態）
            game.blocks = []
            for row_idx, row in enumerate(matrix):
                for col_idx, val in enumerate(row):
                    for bit, q in enumerate(game.Q_ORDER):
                        if val & (1 << bit):
                            game.blocks.append(
                                Block([min_row + row_idx, min_col + col_idx, q]))
                        if val & (1 << (bit + 4)):
                            game.blocks.append(
                                Block([min_row + row_idx + 0.5,
                                       min_col + col_idx + 0.5, q]))
        elif getattr(game, 'spec', None) is not None and game.spec.orientations:
            # 通用带朝向板型（shield 等）：matrix 值 = orientations 下标+1。
            # 但同 2D 格可叠多块（不同朝向），matrix 会把它们压成一格 →
            # 丢块。若带无损键表快照（EngineGame.snapshot_state），直接用它
            # 还原并 return，跳过下面的 lossy 重建与末尾矩阵覆写。
            if hasattr(game, 'restore_state') and snapshot.get('engine_state'):
                game.restore_state(snapshot['engine_state'])
                return
            # 回退（非 EngineGame 的带朝向板型）：matrix 值 = orientations 下标+1
            # （与 adapter.update_matrix 的通用分支互为编解码）。三角/米字有位
            # 打包专用分支在上面；方形/立方 orientations 为空元组，落到 else。
            game.blocks = []
            orients = game.spec.orientations
            for row_idx, row in enumerate(matrix):
                for col_idx, val in enumerate(row):
                    if val:
                        game.blocks.append(Block([min_row + row_idx,
                                                  min_col + col_idx,
                                                  orients[val - 1]]))
        else:
            # 根據矩陣重建滑塊列表；编号谜题的整数矩阵「值即编号」，直接取用
            game.blocks = []
            numbered = getattr(game, 'numbered', False)
            for row_idx, row in enumerate(matrix):
                for col_idx, val in enumerate(row):
                    if val:
                        b = Block([min_row + row_idx, min_col + col_idx])
                        if numbered:
                            b.number = val
                        game.blocks.append(b)

        # 恢复捆绑状态（自由捆绑；旧快照无该字段 = 无捆绑）。
        # **必须在三条重建分支之后统一做**：位置匹配与形态无关
        # （方形 (r,c) / 三角 (i,j,up) / 米字 (r,c,q) 都由 groups_as_positions
        # 出来、按 tuple(location) 对上），之前只写在方形分支里，导致三角/
        # 米字存档带着 groups 落盘、载入后却静默变回全散块。
        # 内存态通常是 {tuple: gid}，但压缩存档回放建立的快照可能已是落盘
        # 形式 [[坐标..., gid],...]，统一归一后再灌。
        if hasattr(game, 'set_groups_from_positions'):
            game.set_groups_from_positions(snapshot_groups(snapshot))

        # 更新游戏内部状态
        game.matrix = [r[:] for r in matrix]
        game.matrix_bounds = dict(bounds)
    
    def can_undo(self) -> bool:
        """判断是否可以撤销"""
        return self.history_index > 0

    def can_redo(self) -> bool:
        """判断是否可以重做"""
        return self.history_index < len(self.history) - 1

    def _ensure_step_granularity(self, index: int) -> int:
        """若快照 index 覆盖多步，就地拆成「一步一条」（惰性），返回段末索引。

        合并快照只存段末矩阵，而撤销/重做要按步进行：首次撤销到该段时，
        用 moves 日志重建中间态，把它展开成多条单步快照，之后走普通逻辑。
        """
        if index <= 0 or index >= len(self.history):
            return index
        snap = self.history[index]
        if snap.get('steps', 1) <= 1:
            return index
        expanded = expand_snapshot_moves(self.history[index - 1], snap)
        if len(expanded) <= 1:
            return index
        base_total = self.step_total_at(index - 1)
        new_snaps = []
        for k, (_pre, post, mv) in enumerate(expanded):
            snap_new = {
                'matrix': [row[:] for row in post['matrix']],
                'bounds': dict(post['bounds']),
                'move_info': mv,
                'moves': [mv],
                'steps': 1,
                'step_total': base_total + k + 1,
                'session_key': None,
            }
            # 编号直接写在整数矩阵里（值即编号），随快照一起携带，
            # 撤销/重做恢复到这些中间态时 restore_snapshot 据矩阵还原块编号
            new_snaps.append(snap_new)
        self.history[index:index + 1] = new_snaps
        return index + len(new_snaps) - 1

    def peek_undo(self):
        """「下一次撤销将回退的那一步」的 move_info（顺带把合并段惰性展开）。

        供 GUI 提前拿到单步动作做撤销动画；无步可撤时返回 None。
        """
        self.history_index = self._ensure_step_granularity(self.history_index)
        if self.history_index <= 0:
            return None
        return self.history[self.history_index].get('move_info')

    def peek_redo(self):
        """「下一次重做将前进的那一步」的 move_info（顺带把目标段惰性展开）。"""
        nxt = self.history_index + 1
        if nxt >= len(self.history):
            return None
        if self.history[nxt].get('steps', 1) > 1:
            self._ensure_step_granularity(nxt)
        return self.history[nxt].get('move_info')

    def undo(self, game) -> tuple:
        """
        撤销操作（每次一步；合并快照先惰性展开成单步）

        参数：
            game: SliderMatrix 游戏对象

        返回：
            tuple: (success: bool, move_info: dict or None)
        """
        if not self.can_undo():
            return False, None
        self.history_index = self._ensure_step_granularity(self.history_index)
        if self.history_index <= 0:
            return False, None
        current_move_info = self.history[self.history_index].get('move_info')
        self.history_index -= 1
        self.restore_snapshot(game, self.history_index)
        return True, current_move_info

    def redo(self, game) -> tuple:
        """
        重做操作（每次一步；目标段为合并快照时先惰性展开）

        参数：
            game: SliderMatrix 游戏对象

        返回：
            tuple: (success: bool, move_info: dict or None)
        """
        if not self.can_redo():
            return False, None
        nxt = self.history_index + 1
        if self.history[nxt].get('steps', 1) > 1:
            self._ensure_step_granularity(nxt)
        self.history_index += 1
        target_move_info = self.history[self.history_index].get('move_info')
        self.restore_snapshot(game, self.history_index)
        return True, target_move_info
    
    def reset(self):
        """清空历史记录"""
        self.history = []
        self.history_index = -1
