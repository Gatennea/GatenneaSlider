# -*- coding: utf-8 -*-
"""EngineGame —— 几何引擎的「游戏契约」适配器（启用开关的落点）。

几何引擎把规则收进一份数据（BoardSpec）+ 一个不可变局面（Board），与现有
三套 game*.py（方形 / 三角 / 米字）各自为政的写法正交。本适配器把
``engine.Board`` 包成 **与 game*.py 同契约** 的对象，让上层（GUI、求解器、
存档）在开关打开时只同引擎对话——三形态共用一套逻辑，不再各写一套。

契约对齐范围（与 game*.py 逐项同义，等价性由
test/_test_engine_adapter.py 钉死）：

    blocks / .location / .be_opted / .group   块视图（与 game.Block 同字段）
    positions()                                位置集合（游戏既有格式）
    all_gaps()                                 全部有效缝 (gap_type, line)
    opt(gap, line, block)                      选组（gap 可为缝族名或方向字母）
    try_move_ex / try_move / commit_move       预测-验证-提交（逐步语义一致）
    is_solved()                                还原判定（走 spec.solved_check）
    get_boundaries / update_matrix / matrix     渲染视图（暂行通用占位）

设计要点：
  · 位置/方向/坐标的全部换算复用 compat 桥（``_keys_to_positions`` /
    ``_norm_keys`` / ``direction_table``），与 history 动作、打乱 record 同源，
    不另写一套、不偷偷改词汇；
  · 选组与移动走引擎的 ``legal_moves`` + ``apply``（纯函数、逐步校验碰撞与
    连通），opt 选中片经 ``_group_closure`` 扩展（捆绑刚体，与 game 一致）；
  · 本模块是迁移件，零依赖 game*.py（引擎纪律：核心与桥都不反向依赖旧引擎）。

⚠️ 渲染视图（matrix）是通用占位：三形态各自的 2-bit / 直角三角矩阵语义
未在此精确还原（开关默认关闭、GUI 尚未接入）。逻辑契约已完整，渲染接入是
产品化 P3 的事，不在本试运行开关范围内。
"""

from .board import Board, _connected_components, _group_closure
from .compat import (_keys_to_positions, _norm_keys, action_to_move,
                     direction_table)


class _AdapterBlock:
    """适配器里的块视图：与 game.Block 同字段（location / be_opted / group）。

    额外挂 ``engine_key`` 反向指针，opt/commit 时从游戏格式位置回查引擎键。
    """

    __slots__ = ('location', 'be_opted', 'group', 'engine_key')

    def __init__(self, location, engine_key, group=0):
        self.location = list(location)
        self.be_opted = False
        self.group = group
        self.engine_key = engine_key


class EngineGame:
    """把 engine.Board 包成 game*.py 同契约的逻辑对象。

    构造入参是已建好的 ``engine.Board``（还原态或任意局面），外加维度
    (m, n, k) 与形态 kind——仅供 GUI 显示与 key 生成用，逻辑不依赖。
    """

    def __init__(self, board: Board, *, m=None, n=None, k=None, kind='square'):
        if not isinstance(board, Board):
            raise TypeError(f"EngineGame 须包 engine.Board，收到 {type(board)}")
        self.board = board
        self.spec = board.spec
        self.kind = kind
        # 维度（显示/key 用；逻辑不依赖）。三角以 k 为准，方形/米字以 m,n。
        if kind == 'triangle':
            self.k = k if k is not None else (m if m is not None else len(board.keys))
            self.m = self.n = self.k
        else:
            self.m = m if m is not None else (n if n is not None else 0)
            self.n = n if n is not None else (m if m is not None else 0)
            self.k = self.m
        self.numbered = False
        self.matrix = None
        self.matrix_bounds = None
        self._opted_keys = frozenset()
        self._opted_t = None
        self._pending_board = None
        self._rebuild_blocks()

    # ------------------------------------------------------------------
    # 块视图
    # ------------------------------------------------------------------
    def _rebuild_blocks(self):
        """从 board.keys 重建 block 列表（位置 = 游戏既有格式）。

        ⚠️ positions 与 engine_key 必须按**同一顺序**配对：compat 的
        ``_keys_to_positions`` 按传入键的顺序产出位置，故这里先排序键、
        再按同序生成位置，zip 才不会错位（否则块的位置与引擎键错配，
        会导致 opt 选中错误的一片——N3/N5 早期失败的根因）。
        """
        ordered_keys = sorted(self.board.keys)
        positions = _keys_to_positions(ordered_keys, self.spec)
        assert len(positions) == len(ordered_keys), \
            "块数不一致（adapter 与 board 错位）"
        block_map = self.board.block_map
        self.blocks = []
        for pos, key in zip(positions, ordered_keys):
            self.blocks.append(_AdapterBlock(pos, key, block_map[key].group))
        self.update_matrix()

    # ------------------------------------------------------------------
    # 位置集合
    # ------------------------------------------------------------------
    def positions(self) -> set:
        """全部块位置（游戏既有格式：方形 (r,c) / 三角 (i,j,bool) /
        米字 (r,c,q)）。"""
        return set(_keys_to_positions(self.board.keys, self.spec))

    # ------------------------------------------------------------------
    # 缝（与 game.all_gaps 同口径：枚举每族秩区间内的有效缝）
    # ------------------------------------------------------------------
    def all_gaps(self) -> list:
        """当前全部有效缝 (gap_type, line)。

        口径与 game.all_gaps 一致：每族 rank 的 [lo, hi] 区间内，t=line+1
        （米字 h/v 是 4× 线分辨率，line=(t-1)/4）两侧都非空即有效；米字
        span 锁死缝走 spec.seam_clear 钩子跳过。
        """
        keys = self.board.keys
        out = []
        for fam in self.spec.seam_families:
            vals = {k: fam.rank_of(k[0], k[1]) for k in keys}
            lo, hi = min(vals.values()), max(vals.values())
            for t in range(lo + 1, hi + 1):
                if self.spec.seam_clear is not None and \
                        not self.spec.seam_clear(fam, t, self.board):
                    continue
                line = (t - 1) / fam.line_scale
                line = int(line) if line == int(line) else line
                out.append((fam.name, line))
        return out

    # ------------------------------------------------------------------
    # 选组（opt）
    # ------------------------------------------------------------------
    def _gap_family_of(self, gap_or_dir: str) -> str:
        """首个入参规范化成缝族名：已是族名直接返回，方向字母则反查。

        兼容方形 game.opt(direction, line, block) 与三角/米字
        game.opt(gap_type, line, block) 两种调用约定。
        """
        table = direction_table(self.spec)
        if gap_or_dir in table:
            d = table[gap_or_dir]
            for fam in self.spec.seam_families:
                if d in fam.parallel:
                    return fam.name
            raise ValueError(f"方向 {gap_or_dir!r} 不属于任何缝族")
        # 否则当作缝族名
        if any(f.name == gap_or_dir for f in self.spec.seam_families):
            return gap_or_dir
        raise ValueError(f"未知缝族/方向: {gap_or_dir!r}")

    def opt(self, gap_or_dir: str, line, selected_block) -> None:
        """按缝切分连通组，标记 selected_block 所在那一侧（与 game.opt 同义）。

        ``gap_or_dir`` 可为缝族名（'h'/'v'/'n'/'d1'/'d2'）或方向字母
        （方形 'a'/'d'/'w'/'s'、三角/米字六/八字母）；``line`` 是缝线号
        （与 game 同语义）。选中片经 ``_group_closure`` 扩展（捆绑刚体）。
        """
        for b in self.blocks:
            b.be_opted = False
        fam_name = self._gap_family_of(gap_or_dir)
        fam = next(f for f in self.spec.seam_families if f.name == fam_name)
        t = int(round(fam.line_scale * line)) + 1
        sel_key = selected_block.engine_key
        if sel_key not in self.board.keys:
            return
        side_lo = frozenset(k for k in self.board.keys
                           if fam.rank_of(k[0], k[1]) < t)
        side_set = side_lo if sel_key in side_lo else (self.board.keys - side_lo)
        comp = next((c for c in _connected_components(side_set, self.spec)
                     if sel_key in c), frozenset())
        moved = _group_closure(comp, self.board.block_map)
        self._opted_keys = moved
        self._opted_t = t
        for b in self.blocks:
            b.be_opted = b.engine_key in moved

    # ------------------------------------------------------------------
    # 移动（try_move_ex / try_move / commit_move）
    # ------------------------------------------------------------------
    def _build_action(self, direction: str, step: int):
        """opt 选中态 + 方向字母 → 引擎动作 dict（复用 compat 校验）。"""
        if not self._opted_keys:
            return None
        table = direction_table(self.spec)
        if direction not in table:
            return None
        moved_positions = [b.location for b in self.blocks if b.be_opted]
        # 反查方向所属缝族（动作 dict 的 gap_type）
        d = table[direction]
        fam_name = next(f.name for f in self.spec.seam_families
                        if d in f.parallel)
        fam = next(f for f in self.spec.seam_families if f.name == fam_name)
        line = (self._opted_t - 1) / fam.line_scale
        line = int(line) if line == int(line) else line
        return {
            'gap_type': fam_name,
            'gap_line': line,
            'direction': direction,
            'step': step,
            'moved_positions': moved_positions,
        }

    def try_move_ex(self, direction: str, step: int):
        """预测-验证：逐步推进，全部通过才返回最终位置（与 game 同契约）。

        返回 (positions, reason)：positions 与选中块顺序一一对应；'' 成功，
        'no_selection' 无选中、'bad_direction' 方向非法、'collision'/
        'disconnected' 见引擎逐步校验。
        """
        action = self._build_action(direction, step)
        if action is None:
            return [], 'no_selection'
        try:
            move = action_to_move(self.spec, action)
        except ValueError:
            return [], 'bad_direction'
        if move not in self.board.legal_moves(step):
            return [], 'collision'
        new_board = self.board.apply(move)
        # 选中块的新位置 = 原位置 + step·方向（按 opted 块顺序）
        delta = tuple(step * x for x in move.direction)
        new_positions = []
        for b in self.blocks:
            if b.be_opted:
                p = b.engine_key[0]
                new_positions.append([p[i] + delta[i] for i in range(len(p))]
                                     + list(b.location[len(p):]))
        self._pending_board = new_board
        return new_positions, ''

    def try_move(self, direction: str, step: int):
        """同 game 契约：只回最终位置，失败为空列表。"""
        positions, _reason = self.try_move_ex(direction, step)
        return positions

    def commit_move(self, final_positions=None):
        """提交移动结果（与 game 同义：采纳 pending 局面）。"""
        if self._pending_board is None:
            return
        self.board = self._pending_board
        self._pending_board = None
        self._opted_keys = frozenset()
        self._opted_t = None
        self._rebuild_blocks()

    # ------------------------------------------------------------------
    # 还原判定
    # ------------------------------------------------------------------
    def is_solved(self) -> bool:
        """是否还原（走 spec.solved_check / 规范形，与引擎同）。"""
        return self.board.is_solved()

    # ------------------------------------------------------------------
    # 渲染视图（暂行通用占位，P3 精确还原三形态矩阵语义）
    # ------------------------------------------------------------------
    def get_boundaries(self) -> dict:
        """块在「主坐标」下的边界（前两维）。"""
        if not self.blocks:
            return {'min_row': 0, 'max_row': 0, 'min_col': 0, 'max_col': 0}
        rows = [b.location[0] for b in self.blocks]
        cols = [b.location[1] for b in self.blocks]
        return {'min_row': min(rows), 'max_row': max(rows),
                'min_col': min(cols), 'max_col': max(cols)}

    def update_matrix(self):
        """重建占用矩阵（通用占位：主坐标网格，占用的格=1）。

        ⚠️ 米字 B 晶格的真实坐标是**半整数**（引擎点奇数 / scale=2），
        这里对主坐标取整落格——占位视图对米字只保证「不崩、能用」，
        精确还原三形态矩阵语义属 P3（docs/spec/几何引擎.md）。方形/三角
        坐标为整数，不受影响。
        """
        if not self.blocks:
            self.matrix = []
            self.matrix_bounds = {'min_row': 0, 'max_row': 0,
                                 'min_col': 0, 'max_col': 0}
            return
        bounds = self.get_boundaries()
        min_r, max_r = int(round(bounds['min_row'])), int(round(bounds['max_row']))
        min_c, max_c = int(round(bounds['min_col'])), int(round(bounds['max_col']))
        rows = max_r - min_r + 1
        cols = max_c - min_c + 1
        self.matrix = [[0] * cols for _ in range(rows)]
        self.matrix_bounds = bounds
        for b in self.blocks:
            r = int(round(b.location[0])) - min_r
            c = int(round(b.location[1])) - min_c
            if 0 <= r < rows and 0 <= c < cols:
                self.matrix[r][c] = 1

    def get_matrix(self):
        if self.matrix is None:
            self.update_matrix()
        return self.matrix

    def block_at(self, key):
        """位置 → _AdapterBlock；不存在回 None。"""
        engine_keys = _norm_keys([key], self.spec, 'block_at')
        target = next(iter(engine_keys)) if engine_keys else None
        for b in self.blocks:
            if b.engine_key == target:
                return b
        return None


# ----------------------------------------------------------------------
# 工厂：形态 → 引擎板型 → EngineGame（开关打开时由 puzzle_types 调用）
# ----------------------------------------------------------------------
def create_adapter_puzzle(kind: str, m: int, n: int, step: int = 2,
                         *, triangle_side: int | None = None) -> 'EngineGame':
    """按形态造 EngineGame（与 puzzle_types.create_puzzle 同入参）。

    kind: square / numbered / triangle / mi。numbered 退化为 square 的
    引擎板型（编号是显示层的事，逻辑上仍是实心矩形还原态）。
    """
    if kind == 'triangle':
        from .registry import tri_board
        k = triangle_side if triangle_side is not None else m
        board = tri_board(k)
        return EngineGame(board, m=k, n=k, k=k, kind='triangle')
    if kind == 'mi':
        from .registry import mi_board
        board = mi_board(m, n)
        return EngineGame(board, m=m, n=n, kind='mi')
    # square / numbered
    from .registry import square_board
    board = square_board(m, n)
    return EngineGame(board, m=m, n=n, kind=kind)
