# -*- coding: utf-8 -*-
"""EngineGame —— 几何引擎的「游戏契约」适配器（GUI 接入的落点）。

几何引擎把规则收进一份数据（BoardSpec）+ 一个不可变局面（Board），与现有
三套 game*.py（方形 / 三角 / 米字）各自为政的写法正交。本适配器把
``engine.Board`` 包成 **与 game*.py 同契约** 的对象，让上层（GUI、历史、
存档）在开关打开时只同引擎对话——三形态共用一套逻辑，不再各写一套。

契约对齐范围（与 game*.py 逐项同义）：

    blocks / .location / .be_opted / .group / .number   块视图
    positions()                                 位置集合（游戏既有格式）
    all_gaps() / is_valid_gap / is_valid_h_line / is_valid_v_line / side_has_blocks
    opt(gap, line, block)                       选组（gap 可为缝族名或方向字母）
    try_move_ex / try_move / commit_move        预测-验证-提交
    is_solved() / goal_pattern / apply_pattern  还原判定（含设计态自定义样式）
    get_boundaries / update_matrix / matrix     渲染 + 历史快照视图
    compute_score / export_map / import_map / has_legal_move / shuffle / resolve_drag

⚠️ 两套「真值」如何共存（本模块最关键的设计约束）：

    GUI 的多条路径**直接写 block.location**，不经过引擎：
      · 移动动画播完：gui/animation.py 写 ``block.location = anim_end_pos``，
        **不调 commit_move**；
      · 打乱演示：整段重放都在直接写 location（含插值中途态）；
      · 安全打乱回滚：写回移动前的坐标。
    所以「引擎 Board 是唯一真值」这条在这里不成立——反过来：**块位置才是
    GUI 眼中的真值**，引擎局面是它的派生视图。故本适配器：
      · ``positions()`` 直接读 blocks（与旧引擎一致，动画中途也同形）；
      · 每次进入逻辑方法（opt / try_move_ex / is_solved / all_gaps /
        shuffle / update_matrix …）先把 blocks 同步回 Board（``_sync``）；
      · ``commit_move`` 只在有 pending 局面时推进引擎，否则以块为准。
    换句话说：**引擎负责「这一步合不合法」，块位置负责「现在长什么样」**。

设计要点：
  · 位置/方向/坐标的全部换算复用 compat 桥（``_keys_to_positions`` /
    ``_norm_keys`` / ``direction_table``），与 history 动作、打乱 record 同源；
  · 矩阵语义按形态**逐一还原**（方形 0/1+编号、三角 2-bit、米字 8-bit），
    因为 history / 压缩存档 / 成绩键全靠它——通用占位会让撤销重做错位；
  · ``blocks`` 是 property：外部（history.restore_snapshot / file_ops）
    整表替换块列表时回写引擎局面，撤销重做才能成立；
  · 本模块不 import game*.py（引擎纪律：不反向依赖旧引擎）。
"""

import math
import random

from .board import Board, _connected_components, _group_closure
from .compat import (_keys_to_positions, _norm_keys, action_to_move,
                     direction_table)
from . import mi_geometry, tri_geometry

#: 米字象限位（与 game_mi.Q_ORDER / _Q_BITS 同义；engine 侧自持一份，
#: 避免反向依赖旧引擎）。history 用 hasattr(game, 'Q_ORDER') 分流米字矩阵。
MI_Q_ORDER = ('N', 'E', 'S', 'W')
_MI_Q_BITS = {'N': 1, 'E': 2, 'S': 4, 'W': 8}


class _AdapterBlock:
    """适配器里的块视图：与 game.Block 同字段。

    ``engine_key`` 是回查引擎局面的反向指针；``number`` 是编号谜题的显示
    编号（整数矩阵里「值即编号」，重建块时必须保住，否则编号丢失）。
    """

    __slots__ = ('location', 'be_opted', 'group', 'engine_key', 'number')

    def __init__(self, location, engine_key, group=0, number=None):
        self.location = list(location)
        self.be_opted = False
        self.group = group
        self.engine_key = engine_key
        self.number = number


class EngineGame:
    """把 engine.Board 包成 game*.py 同契约的逻辑对象。

    构造入参是已建好的 ``engine.Board``（还原态或任意局面），外加维度
    (m, n, k) 与形态 kind——仅供 GUI 显示与 key 生成用，逻辑不依赖。
    """

    def __init__(self, board: Board, *, m=None, n=None, k=None, kind='square'):
        if not isinstance(board, Board):
            raise TypeError(f"EngineGame 须包 engine.Board，收到 {type(board)}")
        self._board = board
        self.spec = board.spec
        self.kind = kind
        # 维度（显示/key 用；逻辑不依赖）。三角以 k 为准，方形/米字以 m,n。
        #
        # ⚠️ k 只在三角上挂：history.restore_snapshot 用 hasattr(game, 'k')
        #    分流「三角 2-bit 矩阵」解码——方形也挂会被误判成三角形，撤销
        #    重做出来的块全错。米字靠 Q_ORDER 分流（见下）。
        if kind == 'triangle':
            self.k = k if k is not None else (m if m is not None else 0)
            self.m = self.n = self.k
        else:
            self.m = m if m is not None else (n if n is not None else 0)
            self.n = n if n is not None else (m if m is not None else 0)
        if kind == 'mi':
            self.Q_ORDER = MI_Q_ORDER
        # numbered 由 kind 派生：puzzle_types.create_puzzle 的引擎分支
        # **提前 return**，走不到旧路径的 ``g.numbered = (kind=='numbered')``
        # （曾致编号谜题矩阵值全变 1，存档/面板静默错）。
        self.numbered = (kind == 'numbered')
        self.goal_pattern = None      # 设计态自定义样式（None = 默认满盘）
        self._goal_keys = None
        self.matrix = None
        self.matrix_bounds = None
        self._blocks = []
        self._sig = None
        # 块对象 → 引擎键（**按 id 索引**，不能写回块上：game.Block 有
        # __slots__=('location','be_opted','number','group')，塞 engine_key
        # 会 AttributeError。history.restore_snapshot / 测试用 _set_cells
        # 塞进来的正是 game.Block——挂不上键的话 opt 会选中 0 块。）
        self._key_by_id = {}
        self._opted_keys = frozenset()
        self._opted_t = None
        self._pending_board = None
        self._pending_updates = None
        self._rebuild_blocks()

    # ------------------------------------------------------------------
    # 引擎局面 ↔ 块视图
    # ------------------------------------------------------------------
    @property
    def board(self) -> Board:
        """引擎局面（读取前先把块位置同步回去）。"""
        self._sync()
        return self._board

    @board.setter
    def board(self, value: Board) -> None:
        self._board = value
        self._pending_board = None
        self._rebuild_blocks()

    def _locations_sig(self):
        """块位置的廉价指纹（判断是否被外部改写过）。"""
        return tuple(tuple(b.location) for b in self._blocks)

    def _sync(self, force: bool = False) -> None:
        """块位置 → 引擎局面（仅当位置指纹变化时重建）。

        GUI 直接写 block.location 的路径（动画落位 / 打乱演示 / 回滚）都靠
        这里回到引擎；指纹未变时零开销。
        """
        sig = self._locations_sig()
        if not force and sig == self._sig:
            return
        if not self._blocks:
            self._board = Board(self.spec, ())
            self._sig = sig
            return
        keyed = []
        for b in self._blocks:
            key = _norm_keys([tuple(b.location)], self.spec, 'adapter.sync')[0]
            # 键按 id 记在适配器上（详见 __init__ 的 _key_by_id 说明）
            try:
                b.engine_key = key
            except AttributeError:
                pass
            self._key_by_id[id(b)] = key
            keyed.append((key, b))
        groups = {key: (b.group or 0) for key, b in keyed}
        self._board = Board.from_keys(self.spec, {k for k, _ in keyed},
                                      groups=groups)
        self._sig = sig

    def _rebuild_blocks(self) -> None:
        """引擎局面 → 块列表（**复用既有块对象**，保住 GUI 持有的引用）。

        ⚠️ 绝不能整表重建 Block：GUI 的 selected_block / anim_blocks 持有旧
        对象的引用，换了对象会让选中态、动画目标全部失联。这里按 engine_key
        复用：位置就地更新，新增的才建、消失的才删。

        ⚠️ positions 与 engine_key 必须按**同一顺序**配对：compat 的
        ``_keys_to_positions`` 按传入键的顺序产出位置，故这里先排序键、
        再按同序生成位置（否则块的位置与引擎键错配 → opt 选中错误的一片，
        这是开发期踩过的坑）。
        """
        ordered_keys = sorted(self._board.keys)
        positions = _keys_to_positions(ordered_keys, self.spec)
        assert len(positions) == len(ordered_keys), \
            "块数不一致（adapter 与 board 错位）"
        bmap = self._board.block_map
        old = {}
        for b in self._blocks:
            k = self._key_of(b)
            if k is not None:
                old[k] = b
        new_blocks = []
        for pos, key in zip(positions, ordered_keys):
            blk = old.pop(key, None)
            if blk is None:
                blk = _AdapterBlock(pos, key, bmap[key].group)
            else:
                # 编号必须继承：restore_snapshot 塞进来的是 game.Block（带
                # .number），这里若不接管，重建后编号全丢、数字谜题判不出还原
                num = getattr(blk, 'number', None)
                blk.location = list(pos)
                blk.group = bmap[key].group
                try:
                    blk.engine_key = key
                except AttributeError:
                    pass
                if num is not None:
                    try:
                        blk.number = num
                    except AttributeError:
                        pass
            blk.be_opted = key in self._opted_keys
            self._key_by_id[id(blk)] = key
            new_blocks.append(blk)
        self._blocks = new_blocks
        self._key_by_id = {id(b): self._key_of(b) for b in self._blocks
                           if self._key_of(b) is not None}
        self._sig = self._locations_sig()
        self.update_matrix()

    @property
    def blocks(self):
        """块列表（与 game*.py 同字段）。"""
        return self._blocks

    @blocks.setter
    def blocks(self, value) -> None:
        """外部整表替换块（history.restore_snapshot / file_ops 的路径）。

        赋值后立刻把引擎局面同步到新位置——否则撤销/重做只改了视图，
        下一步逻辑还在旧局面上算。
        """
        self._blocks = list(value)
        self._opted_keys = frozenset()
        self._opted_t = None
        self._sync(force=True)
        self.update_matrix()

    # ------------------------------------------------------------------
    # 位置集合（直接读块：动画中途与旧引擎同形）
    # ------------------------------------------------------------------
    def positions(self) -> set:
        """全部块位置（游戏既有格式：方形 (r,c) / 三角 (i,j,bool) /
        米字 (r,c,q)）。"""
        return {tuple(b.location) for b in self._blocks}

    # ------------------------------------------------------------------
    # 缝（与 game.all_gaps 同口径）
    # ------------------------------------------------------------------
    def _gap_directions(self, gap_type: str) -> tuple:
        """缝族 → 该族的两个方向字母（与 game 的 GAP_DIRECTIONS 同义）。

        ⚠️ ``SeamFamily.parallel`` 存的是**方向向量**不是字母，必须经
        ``direction_table`` 反查回字母——直接拿 parallel 当字母喂给
        try_move 会全判 bad_direction（方形打乱 0 步就是这么来的）。
        """
        fam = next((f for f in self.spec.seam_families
                    if f.name == gap_type), None)
        if fam is None:
            return ()
        table = direction_table(self.spec)
        return tuple(sorted(letter for letter, vec in table.items()
                            if vec in fam.parallel))

    def all_gaps(self) -> list:
        """当前全部有效缝 (gap_type, line)。

        口径与 game.all_gaps 一致：每族 rank 的 [lo, hi] 区间内，t=line+1
        （米字 h/v 是 4× 线分辨率，line=(t-1)/4）两侧都非空即有效；米字
        span 锁死缝走 spec.seam_clear 钩子跳过。
        """
        keys = self.board.keys
        if not keys:
            return []
        out = []
        for fam in self.spec.seam_families:
            vals = {k: fam.rank_of(k[0], k[1]) for k in keys}
            lo, hi = min(vals.values()), max(vals.values())
            for t in range(lo + 1, hi + 1):
                if self.spec.seam_clear is not None and \
                        not self.spec.seam_clear(fam, t, self._board):
                    continue
                line = (t - 1) / fam.line_scale
                line = int(line) if line == int(line) else line
                out.append((fam.name, line))
        return out

    def _line_to_t(self, gap_type: str, line) -> int:
        """缝线号 → 引擎的 t（同族内 ``t = line_scale·line + 1``）。"""
        fam = next(f for f in self.spec.seam_families if f.name == gap_type)
        return int(round(fam.line_scale * line)) + 1

    def is_valid_gap(self, gap_type: str, line) -> bool:
        """缝隙有效性：线两侧都至少有块（与 game_triangle/game_mi 同义）。"""
        if not any(f.name == gap_type for f in self.spec.seam_families):
            return False
        keys = self.board.keys
        if not keys:
            return False
        fam = next(f for f in self.spec.seam_families if f.name == gap_type)
        t = self._line_to_t(gap_type, line)
        # ⚠️ 两道关缺一不可：①线不能切进任何块（spec.seam_clear 钩子，
        #    米字的 span 锁死判据）；②两侧都非空。只判②会让米字整族对
        #    角缝在「切块」的线上也算有效（差分抓到 d2 全族误判）。
        if self.spec.seam_clear is not None and \
                not self.spec.seam_clear(fam, t, self._board):
            return False
        sides = {0 if fam.rank_of(k[0], k[1]) < t else 1 for k in keys}
        return sides == {0, 1}

    def is_valid_h_line(self, line: int) -> bool:
        """横向分割线是否在边界盒内（方形，``min_row <= line < max_row``）。"""
        b = self.get_boundaries()
        return b['min_row'] <= line < b['max_row']

    def is_valid_v_line(self, line: int) -> bool:
        """纵向分割线是否在边界盒内（方形，``min_col <= line < max_col``）。"""
        b = self.get_boundaries()
        return b['min_col'] <= line < b['max_col']

    def side_has_blocks(self, gap_type: str, line, side) -> bool:
        """缝的指定侧是否有块（宏回放原语，与 game 同契约）。

        方形传 'above'/'below'/'left'/'right'（MacroStep 存的就是这四个词），
        异形传 0/1（``side_of`` 口径）；两种都在这里归一。
        """
        if not any(f.name == gap_type for f in self.spec.seam_families):
            return False
        if gap_type in ('h', 'v') and self.kind in ('square', 'numbered'):
            # 方形沿用 is_valid_h/v_line 的门（不在边界盒内即无效）
            if not (self.is_valid_h_line(line) if gap_type == 'h'
                    else self.is_valid_v_line(line)):
                return False
        elif not self.is_valid_gap(gap_type, line):
            return False
        keys = self.board.keys
        if not keys:
            return False
        t = self._line_to_t(gap_type, line)
        fam = next(f for f in self.spec.seam_families if f.name == gap_type)
        want_lo = side in ('above', 'left', 0)
        for k in keys:
            on_lo = fam.rank_of(k[0], k[1]) < t
            if want_lo and on_lo:
                return True
            if not want_lo and not on_lo:
                return True
        return False

    def side_of(self, gap_type: str, line, key) -> int:
        """单位块位于缝隙的哪一侧：0 = 索引小的一侧，1 = 大的一侧。

        与 ``game_mi.side_of`` / ``game_triangle.side_of`` 同契约（回放层
        ``_find_block_on_side`` 按形态分派到这一份）。判据走引擎自家的
        ``SeamFamily.rank_of``，与旧口径逐项等价——**包括非整数线**：

        - 旧口径：``gap_rank(key) <= line`` → 0 侧；
        - 引擎：``rank_e <= line_scale·line``（h/v 的 rank_e = 4×实数 rank、
          line_scale = 4；d1/d2 的 rank_e = 2×整数 rank、line_scale = 1；
          方形 rank_e = r/c、line_scale = 1）——逐形态都是旧口径的精确
          放大，**不经 t**。
        - ⚠️ 两个都别写：①``rank_e < t``——整数线下等价，非整数线（d1 的
          L=-2.5 这类）下 ``rank <= -2.5``（⟺ <= -3）与 ``rank < -1.5``
          （⟺ <= -2）判据不同，差分实测 60+ 处分歧全在这类线上；
          ②经 ``_line_to_t``——它有 ``int(round(...))``，半整数线会被吞掉
          一半（-2.5 → -2），同样偏。引擎自身枚举只产整数线（``all_gaps``
          实测 0/30 非整数）故不致命，但回放层拿到的线号来源不止一条，
          精确等价才算数。

        ``key`` 接受 GUI 位置形状（``[r, c]`` / ``[r, c, q]``），内部经
        ``_norm_keys`` 转引擎键。**先同步**：与 opt 同一条前置条件——块可能
        被外部就地改过 location（动画落位 / solver restore），键缓存会过期。
        """
        if not any(f.name == gap_type for f in self.spec.seam_families):
            raise ValueError(f"未知缝族: {gap_type!r}")
        self._sync()   # 刷新键缓存（_sync 是唯一刷新点，见 _key_of 注释）
        (point, orient), = _norm_keys([tuple(key)], self.spec, 'side_of')
        fam = next(f for f in self.spec.seam_families if f.name == gap_type)
        return 0 if fam.rank_of(point, orient) <= fam.line_scale * line else 1

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
        if any(f.name == gap_or_dir for f in self.spec.seam_families):
            return gap_or_dir
        raise ValueError(f"未知缝族/方向: {gap_or_dir!r}")

    def _key_of(self, selected_block):
        """块对象 → 引擎键（优先读块上的指针，退回 id 映射）。

        ⚠️ **调用前必须先摸过 `self.board`**：`_sync()` 是缓存键的唯一刷新
        点，它按块**当前 location** 重算 `engine_key`。外部就地改写
        `b.location`（`solver/state.restore` 就是 ``b.location[0] = loc[0]``
        这种写法，用来做搜索回溯）之后，块上的旧键会与真实位置脱节；此时
        `_key_of` 若先于 `_sync` 被调用，就会拿过期键去查新局面 → 判定
        「选中块不在盘面上」→ 选中 0 块 → 求解器收到 False → 报
        `invalid_action`（2026-10-21 实测：方形 3×3 动作空间新旧同形 28=28，
        旧引擎 5 步解完，引擎侧却卡在第 6 步）。
        """
        key = getattr(selected_block, 'engine_key', None)
        if key is not None:
            return key
        return self._key_by_id.get(id(selected_block))

    def opt(self, gap_or_dir: str, line, selected_block) -> None:
        """按缝切分连通组，标记 selected_block 所在那一侧（与 game.opt 同义）。

        ``gap_or_dir`` 可为缝族名（'h'/'v'/'n'/'d1'/'d2'）或方向字母
        （方形 'a'/'d'/'w'/'s'、三角六字母、米字八字母）；``line`` 是缝线号。
        选中片经 ``_group_closure`` 扩展（捆绑刚体）。
        """
        for b in self._blocks:
            b.be_opted = False
        fam_name = self._gap_family_of(gap_or_dir)
        fam = next(f for f in self.spec.seam_families if f.name == fam_name)
        t = int(round(fam.line_scale * line)) + 1
        # ⚠️ **先同步再读键**：_sync 会按块当前 location 刷新 engine_key。
        #    写在 _key_of 之后的话，外部就地改写过 location 时拿到的是过期
        #    键（详见 _key_of 的 docstring）——求解器回溯路径必踩。
        keys = self.board.keys
        sel_key = self._key_of(selected_block)
        if sel_key is None or sel_key not in keys:
            self._opted_keys = frozenset()
            self._opted_t = None
            return
        side_lo = frozenset(k for k in keys
                            if fam.rank_of(k[0], k[1]) < t)
        side_set = side_lo if sel_key in side_lo else (keys - side_lo)
        comp = next((c for c in _connected_components(side_set, self.spec)
                     if sel_key in c), frozenset())
        moved = _group_closure(comp, self._board.block_map)
        self._opted_keys = moved
        self._opted_t = t
        for b in self._blocks:
            b.be_opted = self._key_of(b) in moved

    def _clear_selection(self) -> None:
        """清空选中态（与 game 的 _clear_selection 同义）。"""
        self._opted_keys = frozenset()
        self._opted_t = None
        for b in self._blocks:
            b.be_opted = False

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
        moved_positions = [b.location for b in self._blocks if b.be_opted]
        d = table[direction]
        fam = next(f for f in self.spec.seam_families if d in f.parallel)
        line = (self._opted_t - 1) / fam.line_scale
        line = int(line) if line == int(line) else line
        return {
            'gap_type': fam.name,
            'gap_line': line,
            'direction': direction,
            'step': step,
            'moved_positions': moved_positions,
        }

    def try_move_ex(self, direction: str, step: int):
        """预测-验证：逐步推进，全部通过才返回最终位置（与 game 同契约）。

        返回 (positions, reason)：positions 与选中块顺序一一对应；'' 成功，
        'no_selection' 无选中、'all_selected' 全员选中（纯平移无意义）、
        'bad_direction' 方向非法、'collision'/'disconnected' 见引擎逐步校验。
        """
        action = self._build_action(direction, step)
        if action is None:
            return [], 'no_selection'
        if len(self._opted_keys) == len(self._blocks):
            return [], 'all_selected'
        try:
            # ⚠️ 只借 action_to_move 做**结构校验**（方向∥缝、选中片不跨
            #    缝、步长合法）；合法性判定不走 legal_moves 成员检查——
            #    那会把整棵合法移动树枚举一遍，6×6 打乱实测占 98% 耗时。
            move = action_to_move(self.spec, action)
        except ValueError:
            return [], 'bad_direction'
        cur = self.board
        fam = next(f for f in self.spec.seam_families
                   if f.name == move.family)
        new_board = cur.slide(move.moved, move.direction, step,
                              fam, move.t)
        if new_board is None:
            return [], 'collision'
        # 选中块的新位置 = 原位置 + step·方向（按 opted 块顺序）
        #
        # ⚠️ 单位陷阱：move.direction 是**引擎点单位**的方向，位移先按点算
        #    （p + step·direction），最后整体 /scale 才回到真实坐标。把
        #    delta 先除 scale 再加到点上，等于把点当真实坐标——米字
        #    scale=2 时会平移出双倍距离（2026-10-21 差分抓到）。
        delta = tuple(step * x for x in move.direction)
        scale = self.spec.lattice.scale
        new_positions = []
        updates = []
        for b in self._blocks:
            if b.be_opted:
                key = self._key_of(b)
                p = key[0]
                pos = [_num((p[i] + delta[i]) / scale) for i in range(len(p))]
                pos += list(b.location[len(p):])
                new_positions.append(pos)
                updates.append((b, (tuple(p[i] + delta[i]
                                          for i in range(len(p))),
                                    key[1]), pos))
        self._pending_board = new_board
        self._pending_updates = updates
        return new_positions, ''

    def try_move(self, direction: str, step: int):
        """同 game 契约：只回最终位置，失败为空列表。"""
        positions, _reason = self.try_move_ex(direction, step)
        return positions

    def commit_move(self, final_positions=None) -> None:
        """提交移动结果（与 game 同义）。

        有 pending 局面（try_move_ex 刚验证过）→ **就地改写选中块的
        location**，块列表顺序与对象身份全部保持不变；没有（GUI 动画路径
        已直接写过 location）→ 以块位置为准同步引擎。

        ⚠️ 为什么不能在这里 `_rebuild_blocks`：老引擎的 commit_move 只写
        坐标、从不重排 blocks，上层（编号谜题的 `[b.number for b in
        blocks]`、GUI 持有的 selected_block）都依赖这个顺序稳定性。按位置
        重排会把编号顺序洗掉——`test/_test_numbered.py` 就是这样挂的。
        """
        if self._pending_board is not None:
            for blk, key, pos in (self._pending_updates or ()):
                blk.location = list(pos)
                try:
                    blk.engine_key = key
                except AttributeError:
                    pass
                self._key_by_id[id(blk)] = key
            self._board = self._pending_board
            self._pending_board = None
            # ⚠️ 选中态**必须保留**（与老引擎同：commit_move 只写坐标、不清
            #    be_opted）。玩家连续按两次方向键走两步，靠的就是这个——
            #    清掉的话第二步直接变 no_selection。
            #    缝线号 t 也不用重算：移动**平行于缝**，选中块的族内序号
            #    （缝的法向坐标）恒定不变，_opted_t 依旧是那条缝。
            self._opted_keys = frozenset(key for _blk, key, _pos
                                         in (self._pending_updates or ()))
            self._pending_updates = None
            self._sig = self._locations_sig()
            self.update_matrix()
        else:
            self._opted_keys = frozenset()
            self._opted_t = None
            self._sync(force=True)
            self.update_matrix()

    def block_at(self, key: tuple):
        """位置 → 块对象；不存在回 None。"""
        target = tuple(key)
        for b in self._blocks:
            if tuple(b.location) == target:
                return b
        return None

    # ------------------------------------------------------------------
    # 连通性 / 可动性
    # ------------------------------------------------------------------
    def is_single_connected(self, cells: set) -> bool:
        """位置集合是否单一连通（走引擎的连通性，与 game 的同名静态语义同）。"""
        if not cells:
            return True
        keys = frozenset(_norm_keys(list(cells), self.spec, 'connectivity'))
        return len(_connected_components(keys, self.spec)) == 1

    def has_legal_move(self, step: int = 1) -> bool:
        """是否存在至少一步合法移动（设计态保存前的冻形检测）。"""
        return self.board.has_legal_move(step)

    # ------------------------------------------------------------------
    # 还原判定
    # ------------------------------------------------------------------
    def is_solved(self) -> bool:
        """是否还原。

        · 默认满盘：走 spec.solved_check / 规范形（与引擎同）；
        · 设计态（goal_pattern 非空）：平移归一后逐键比（方形另走 D4 八变换，
          与 game.SliderMatrix 的 canonicalize 判定同义）。
        """
        cur = self.board
        if self._goal_keys is None:
            return cur.is_solved()
        if len(cur.keys) != len(self._goal_keys):
            return False
        if self.spec.lattice.symmetry == 'hyperoctahedral':
            # 方形：D4 八变换任一命中即算还原（旋转/翻面都算）
            goal_board = Board.from_keys(self.spec, self._goal_keys)
            return cur.canonical_key() == goal_board.canonical_key()
        return _translate_normalized(cur.keys) == \
            _translate_normalized(self._goal_keys)

    def goal_cells(self) -> set:
        """默认还原态的位置集合（游戏既有格式）。"""
        if self.kind == 'triangle':
            k = self.k
            return ({(i, j, True) for i in range(k) for j in range(k - i)} |
                    {(i, j, False) for i in range(k - 1)
                     for j in range(k - 1 - i)})
        if self.kind == 'mi':
            return {(r, c, q) for r in range(self.m) for c in range(self.n)
                    for q in MI_Q_ORDER}
        return {(r, c) for r in range(self.m) for c in range(self.n)}

    def set_goal_pattern(self, cells) -> bool:
        """设计态：设定自定义还原样式（None 表示回到默认满盘）。"""
        if cells is None:
            self.goal_pattern = None
            self._goal_keys = None
            return True
        norm = frozenset(tuple(c) for c in cells)
        if not norm:
            return False
        self.goal_pattern = norm
        self._goal_keys = frozenset(_norm_keys(list(norm), self.spec,
                                               'goal_pattern'))
        return True

    def clear_goal_pattern(self) -> None:
        """设计态：清除自定义还原样式。"""
        self.set_goal_pattern(None)

    def apply_pattern(self, cells, groups=None) -> None:
        """设计态：按给定格集合（+ 捆绑组）重建局面。"""
        norm = [tuple(c) for c in cells]
        keys = _norm_keys(norm, self.spec, 'apply_pattern')
        gmap = {}
        if groups:
            for pos, gid in groups.items():
                k = _norm_keys([tuple(pos)], self.spec, 'apply_pattern')[0]
                gmap[k] = gid
        self._board = Board.from_keys(self.spec, frozenset(keys),
                                      groups=gmap or None)
        self._opted_keys = frozenset()
        self._opted_t = None
        self._rebuild_blocks()

    # ------------------------------------------------------------------
    # 捆绑（自由捆绑，docs/spec/bandaged_mode.md）
    # ------------------------------------------------------------------
    def groups_as_positions(self):
        """捆绑组 → {位置: gid}（无组时返回 None，与 game 同口径）。"""
        out = {}
        for b in self._blocks:
            if b.group:
                out[tuple(b.location)] = b.group
        return out or None

    def set_groups_from_positions(self, groups) -> None:
        """{位置: gid} → 写回捆绑组（None 表示清空）。"""
        self._sync()          # 先刷新缓存键（_key_of 的前置条件）
        if not groups:
            for b in self._blocks:
                b.group = 0
        else:
            gmap = {}
            for pos, gid in groups.items():
                k = _norm_keys([tuple(pos)], self.spec, 'groups')[0]
                gmap[k] = gid
            for b in self._blocks:
                b.group = gmap.get(self._key_of(b), 0)
        self._sync(force=True)

    # ------------------------------------------------------------------
    # 渲染视图（按形态还原真实矩阵语义：历史/存档/成绩键全靠它）
    # ------------------------------------------------------------------
    def get_boundaries(self) -> dict:
        """块在主坐标下的边界（前两维；米字按 floor 归格，与 game_mi 同）。"""
        if not self._blocks:
            return {'min_row': 0, 'max_row': 0, 'min_col': 0, 'max_col': 0}
        rows = [b.location[0] for b in self._blocks]
        cols = [b.location[1] for b in self._blocks]
        if self.kind == 'mi':
            # 米字：A 晶格 (R,C) 与 B 晶格 (R+½,C+½) 同属一格，格号取 floor
            return {'min_row': math.floor(min(rows)),
                    'max_row': math.floor(max(rows)),
                    'min_col': math.floor(min(cols)),
                    'max_col': math.floor(max(cols))}
        return {'min_row': min(rows), 'max_row': max(rows),
                'min_col': min(cols), 'max_col': max(cols)}

    def _matrix_bounds(self) -> dict:
        """矩阵边界（求解器的 snap/restore 契约）。

        `solver/ml/mi_adapter.restore` 在收尾时显式调它重算（而不是置
        None——`history.py` 直接 `dict(game.matrix_bounds)`，None 会崩；
        留旧值更糟，是「看着有效其实与当前位置不符」的静默错误）。语义与
        `game_mi._matrix_bounds` 一致：米字按格号 floor 取整。
        """
        if not self._blocks:
            return {'min_row': 0, 'max_row': 0, 'min_col': 0, 'max_col': 0}
        return self.get_boundaries()

    def update_matrix(self):
        """重建矩阵，语义逐形态还原（不是通用占位）。

        方形：0=空、1=有块；编号谜题「值即编号」（与 game.SliderMatrix 同）。
        三角：菱形胞 2-bit（bit0=▲、bit1=▼）。
        米字：每格 8-bit（bit0~3 = A 晶格四象限、bit4~7 = B 晶格）。
        """
        if not self._blocks:
            self.matrix = []
            self.matrix_bounds = {'min_row': 0, 'max_row': 0,
                                  'min_col': 0, 'max_col': 0}
            return
        bounds = self.get_boundaries()
        min_r, max_r = bounds['min_row'], bounds['max_row']
        min_c, max_c = bounds['min_col'], bounds['max_col']
        rows = max_r - min_r + 1
        cols = max_c - min_c + 1
        self.matrix = [[0] * cols for _ in range(rows)]
        self.matrix_bounds = bounds
        for b in self._blocks:
            loc = b.location
            r = math.floor(loc[0]) - min_r
            c = math.floor(loc[1]) - min_c
            if not (0 <= r < rows and 0 <= c < cols):
                continue
            if self.kind == 'triangle':
                self.matrix[r][c] |= 1 if loc[2] else 2
            elif self.kind == 'mi':
                q = loc[2]
                # B 晶格 = 半整数坐标（2r 为奇数）
                lat = 0 if (2 * loc[0]) % 2 == 0 else 1
                self.matrix[r][c] |= _MI_Q_BITS[q] << (4 * lat)
            else:
                # 方形：编号谜题整数矩阵「值即编号」
                # ⚠️ getattr：history.restore_snapshot 塞进来的是 game.Block，
                #    未设过 number 时根本没有这个属性（Block 是动态挂的）。
                num = getattr(b, 'number', None)
                self.matrix[r][c] = num if (self.numbered and num) else 1

    def get_matrix(self):
        if self.matrix is None:
            self.update_matrix()
        return self.matrix

    # ------------------------------------------------------------------
    # 散度 / 聚拢度（打乱门槛与指标面板）
    # ------------------------------------------------------------------
    def compute_score(self) -> float:
        """聚拢度 0~1（复原态 = 1.0），逐形态还原旧引擎公式。"""
        cells = self.positions()
        if not cells:
            return 0.0
        if self.kind == 'triangle':
            return _tri_score(cells, self.k)
        if self.kind == 'mi':
            return _mi_score(cells, self.m, self.n)
        return _square_score(cells, self.m, self.n)

    def _scatter(self) -> float:
        return 1.0 - self.compute_score()

    def _scatter_of(self, cells: set) -> float:
        """给定位置集合的散度（Metropolis 预估值，不依赖 self.blocks）。"""
        if not cells:
            return 1.0
        if self.kind == 'triangle':
            return 1.0 - _tri_score(cells, self.k)
        if self.kind == 'mi':
            return 1.0 - _mi_score(cells, self.m, self.n)
        return 1.0 - _square_score(cells, self.m, self.n)

    # ------------------------------------------------------------------
    # 打乱（安全打乱：每步可逆，终态保证有解）
    # ------------------------------------------------------------------
    def _random_move(self, step: int, bias: float, cur_scatter: float,
                     record=None):
        """执行一次随机合法滑动，回传 (是否移动, 新散度)。

        对齐 game.commit_shuffle_step 的三段式：**先提交、再校验可逆、
        不可逆回滚**。校验用「同缝遍历方向能否精确推回移动前的位置集合」
        （与 game.can_undo_shuffle_step 同标准）——整条路径反转即是一条
        合法解法，终态保证有解。

        ⚠️ 校验必须在提交之后：未提交时 opt 选中的组还在原位，任何方向的
        落点都不可能等于原位，放前面会恒假（2026-10-18 踩过）。

        record 非 None 时按执行顺序记录（格式见 game.record_shuffle_move）。
        """
        gaps = self.all_gaps()
        if not gaps:
            return False, cur_scatter
        gap_type, line = random.choice(gaps)
        dirs = self._gap_directions(gap_type)
        if not dirs:
            return False, cur_scatter
        direction = random.choice(dirs)
        block = random.choice(self._blocks)
        self.opt(gap_type, line, block)
        if not any(b.be_opted for b in self._blocks):
            self._clear_selection()
            return False, cur_scatter
        before_locs = [list(b.location) for b in self._blocks]
        moved = [tuple(b.location) for b in self._blocks if b.be_opted]
        before_sel = set(moved)
        final = self.try_move(direction, step)
        if not final:
            self._clear_selection()
            return False, cur_scatter
        cand_scatter = cur_scatter
        if bias > 0:
            non_sel = {tuple(b.location) for b in self._blocks
                       if not b.be_opted}
            cand_scatter = self._scatter_of(non_sel |
                                            {tuple(p) for p in final})
            # Metropolis：候选更紧凑（散度下降）时按概率拒绝
            if cand_scatter < cur_scatter:
                if random.random() >= math.exp(bias *
                                               (cand_scatter - cur_scatter)):
                    self._clear_selection()
                    return False, cur_scatter
        # 提交（把 pending 局面落到引擎 + 块）
        self.commit_move(final)
        # 可逆性校验：同缝遍历方向，能否精确回到移动前的那组位置
        ok = False
        for d in dirs:
            self.opt(gap_type, line, block)
            back = self.try_move(d, step)
            if back and {tuple(p) for p in back} == before_sel:
                ok = True
                break
        self._clear_selection()
        if ok:
            if record is not None:
                record.append({
                    'moved': [tuple(p) for p in moved],
                    'final': [tuple(p) for p in final],
                    'gap': (gap_type, line),
                    'direction': direction,
                    'step': step,
                })
            return True, cand_scatter
        # 不可逆：回滚坐标（引擎局面下次 _sync 时随之回到该状态）
        for i, b in enumerate(self._blocks):
            b.location = list(before_locs[i])
        return False, cur_scatter

    def _shuffle_once(self, attempts: int, step: int, bias: float,
                      min_score, record) -> None:
        """单次随机打乱核心（死局防护的包装在 shuffle）。"""
        cur_scatter = self._scatter()
        for _ in range(attempts):
            _moved, cur_scatter = self._random_move(step, bias, cur_scatter,
                                                    record)
        if min_score is None:
            return
        for _ in range(attempts * 3):
            if self.compute_score() <= min_score:
                break
            for _attempt in range(attempts):
                _moved, cur_scatter = self._random_move(step, bias,
                                                        cur_scatter, record)
        self._clear_selection()

    def shuffle(self, attempts: int, step: int, bias: float = 0.0,
                min_score: float = 0.75, record=None) -> None:
        """随机打乱（纯逻辑）：重复随机合法滑动，每步过可逆性校验。

        参数与旧引擎逐项同义：bias>0 用 Metropolis 准则偏向更散的状态；
        min_score 为聚拢度下限，太高就重洗（最多 attempts*3 轮）。

        ⚠️ 死局黑名单防护不可省（与 game.SliderMatrix.shuffle 同构）：
        4_4_2 的死局态**向前封闭**——从死局出发的任何合法移动仍落在死局
        集合里，一步都走不出去。所以终态命中黑名单时必须**先回复原态再
        重打**，否则「从死局态开局打乱」永远出不来（_test_shuffle_guard
        端到端就是卡在这里）。安全打乱的可逆性已能保证终态不在死局里，
        这层只是冗余兜底（详见 solver/deadend_guard）。
        """
        from solver.deadend_guard import has_deadend_guard, is_deadend

        # ⚠️ 死局黑名单是**方形专属**：`solver/deadend_guard` 的 canonicalize
        #    只吃 (r, c) 二元组，三角 (i,j,bool) / 米字 (r,c,q) 三元组喂进去
        #    直接 `ValueError: too many values to unpack`（_test_tri_gui_solve
        #    实测崩溃）。异形的死局语义不同（三角/米字没做过完备枚举），
        #    这里按形态短路——不是静默降级，是本来就没有可用黑名单。
        if self.kind not in ('square', 'numbered') or \
                not has_deadend_guard(self.m, self.n, step):
            self._shuffle_once(attempts, step, bias, min_score, record)
            return

        for retry in range(100):
            if retry:
                cells = (sorted(self.goal_pattern)
                         if self.goal_pattern is not None else None)
                if cells is None:
                    # 默认满矩形（与 game 同式：第 i 块放 i//n 行 i%n 列）
                    for i, b in enumerate(self._blocks):
                        b.location = [i // self.n, i % self.n]
                else:
                    for i, b in enumerate(self._blocks):
                        if i < len(cells):
                            b.location = list(cells[i])
                self._opted_keys = frozenset()
                self._opted_t = None
                self._sync(force=True)
                if record is not None:
                    record.clear()   # 回到复原态重打：上一轮记录作废
            self._shuffle_once(attempts, step, bias, min_score, record)
            if not is_deadend(self.m, self.n, step, self.positions()):
                return
        # 与 game 同口径：连续 100 次都命中才接受最后一次，并如实打印
        print('警告: 打乱终态连续 100 次命中死局黑名单，接受最后一次结果')

    # ------------------------------------------------------------------
    # 拖动（三角单指拖动：缝隙线穿手指）
    # ------------------------------------------------------------------
    def resolve_drag(self, key: tuple, direction: str, steps: int) -> tuple:
        """单次触摸拖动解析：手指下的块 + 一个晶格方向 → 可行移动。

        与 game_triangle.resolve_drag 同契约：缝线优先取穿过手指那条，
        无效时按距离外推邻近线；步数从 steps 递减尝试（拖到哪算哪）。

        返回 (positions, gap_type, line, reason, steps)；positions 为空即
        失败（此时 steps=0）。成功时留下 opt 选中态，失败时清空。
        """
        table = direction_table(self.spec)
        if direction not in table:
            return [], None, None, 'bad_direction', 0
        if key not in self.positions():
            return [], None, None, 'no_block', 0
        fam = next((f for f in self.spec.seam_families
                    if table[direction] in f.parallel), None)
        if fam is None:
            return [], None, None, 'bad_direction', 0
        k = _norm_keys([tuple(key)], self.spec, 'resolve_drag')[0]
        # 「穿过手指的那条线」：块的族内序号（rank）换算回线号
        # （side_of 判据是 rank <= line·line_scale，故 base = rank/line_scale）
        base = fam.rank_of(k[0], k[1]) / fam.line_scale
        block = self.block_at(key)
        span = max(self.m, self.n) + getattr(self, 'k', 0) + 2
        for dist in range(0, span + 1):
            for line in ({base - dist, base + dist} if dist else {base}):
                if not self.is_valid_gap(fam.name, line):
                    continue
                for nstep in range(steps, 0, -1):
                    self.opt(fam.name, line, block)
                    pos = self.try_move(direction, nstep)
                    if pos:
                        return pos, fam.name, line, '', nstep
                self._clear_selection()
        self._clear_selection()
        return [], None, None, 'no_move', 0

    # ------------------------------------------------------------------
    # 地图编码（导入/导出，逐形态同格式）
    # ------------------------------------------------------------------
    def export_map(self) -> str:
        """导出为字符矩阵：方形 '#/_'，三角 '#/^/v/_'，米字十六进制。"""
        keys = [tuple(b.location) for b in self._blocks]
        if not keys:
            return ''
        if self.kind == 'triangle':
            grid = {}
            for (i, j, up) in keys:
                grid[(i, j)] = grid.get((i, j), 0) | (1 if up else 2)
            lo_i = min(i for i, _ in grid)
            hi_i = max(i for i, _ in grid)
            lo_j = min(j for _, j in grid)
            hi_j = max(j for _, j in grid)
            rows = []
            for i in range(lo_i, hi_i + 1):
                rows.append(''.join(
                    '#' if grid.get((i, j), 0) == 3 else
                    ('^' if grid.get((i, j), 0) == 1 else
                     ('v' if grid.get((i, j), 0) == 2 else '_'))
                    for j in range(lo_j, hi_j + 1)))
            return '\n'.join(rows)
        if self.kind == 'mi':
            grid = {}
            for (r, c, q) in keys:
                R, C = math.floor(r), math.floor(c)
                lat = 0 if (2 * r) % 2 == 0 else 1
                grid[(R, C)] = grid.get((R, C), 0) | \
                    (_MI_Q_BITS[q] << (4 * lat))
            lo_r = min(r for r, _ in grid)
            hi_r = max(r for r, _ in grid)
            lo_c = min(c for _, c in grid)
            hi_c = max(c for _, c in grid)
            shifted = any(v >> 4 for v in grid.values())
            hexch = '0123456789abcdef'
            rows = ['mi8'] if shifted else []
            for r in range(lo_r, hi_r + 1):
                line = []
                for c in range(lo_c, hi_c + 1):
                    v = grid.get((r, c), 0)
                    if shifted:
                        line.append(hexch[v & 15] + hexch[(v >> 4) & 15])
                    else:
                        line.append(hexch[v & 15])
                rows.append(''.join(line))
            return '\n'.join(rows)
        # 方形：0-1 矩阵
        self.update_matrix()
        if not self.matrix:
            return ''
        return '\n'.join(''.join('#' if v else '_' for v in row)
                         for row in self.matrix)

    def import_map(self, map_str: str) -> bool:
        """从字符矩阵导入（格式见 export_map）。失败返回 False。"""
        lines = [ln.strip() for ln in map_str.strip().split('\n') if ln.strip()]
        if not lines:
            return False
        if self.kind == 'triangle':
            blocks = []
            for ri, line in enumerate(lines):
                for cj, ch in enumerate(line):
                    if ch in ('#', '^'):
                        blocks.append([ri, cj, True])
                    if ch in ('#', 'v'):
                        blocks.append([ri, cj, False])
            if not blocks:
                return False
            self._adopt_locations(blocks)
            return True
        if self.kind == 'mi':
            eight = lines[0].lower() == 'mi8'
            if eight:
                lines = lines[1:]
            if not lines:
                return False
            per = 2 if eight else 1
            width = len(lines[0])
            if width == 0 or width % per or any(len(l) != width
                                                for l in lines):
                return False
            hexmap = {c: i for i, c in enumerate('0123456789abcdef')}
            hexmap.update({'#': 15, '_': 0, '.': 0,
                           'n': 1, 'e': 2, 's': 4, 'w': 8})
            locs = []
            cols = width // per
            for R, line in enumerate(lines):
                for i in range(cols):
                    chunk = line[i * per:(i + 1) * per]
                    vals = [hexmap.get(ch.lower()) for ch in chunk]
                    if any(v is None for v in vals):
                        return False
                    for qi, q in enumerate(MI_Q_ORDER):
                        if vals[0] & (1 << qi):
                            locs.append([R, i, q])
                        if eight and vals[1] & (1 << qi):
                            locs.append([R + 0.5, i + 0.5, q])
            if not locs:
                return False
            self._adopt_locations(locs)
            return True
        # 方形
        locs = []
        for ri, line in enumerate(lines):
            for cj, ch in enumerate(line):
                if ch == '#':
                    locs.append([ri, cj])
        if not locs:
            return False
        self._adopt_locations(locs)
        return True

    def _adopt_locations(self, locations) -> None:
        """按位置列表重建块（导入地图 / 存档恢复的落点）。"""
        self._blocks = []
        for p in locations:
            self._blocks.append(_AdapterBlock(p, None))
        self._opted_keys = frozenset()
        self._opted_t = None
        self._sync(force=True)
        self.update_matrix()


# ----------------------------------------------------------------------
# 散度/聚拢度的形态专用公式（与旧引擎逐式同形，纯函数便于对拍）
# ----------------------------------------------------------------------
def _num(x):
    """整数结果归一为 int（与 game 的 location 整数归一同形）。"""
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


def _square_score(cells, m, n) -> float:
    """方形聚拢度：0.5×填充率 + 0.5×(1−长宽比偏差)，与 solver.heuristic 同式。"""
    if not cells:
        return 0.0
    rs = [c[0] for c in cells]
    cs = [c[1] for c in cells]
    H = max(rs) - min(rs) + 1
    W = max(cs) - min(cs) + 1
    K = m * n
    bb = H * W
    fill_rate = K / bb if bb > 0 else 0.0
    min_dim, max_dim = min(m, n), max(m, n)
    target_ratio = max_dim / min_dim if min_dim > 0 else 1.0
    min_hw, max_hw = min(H, W), max(H, W)
    cur_ratio = max_hw / min_hw if min_hw > 0 else 1.0
    max_ratio = max(cur_ratio, target_ratio)
    aspect_error = (abs(cur_ratio - target_ratio) / max_ratio
                    if max_ratio > 0 else 0.0)
    return 0.5 * fill_rate + 0.5 * (1.0 - aspect_error)


def _hull_area(verts) -> float:
    """整数点集凸包的面积（鞋带公式 / 2，与 game 的 hull_area_units 同法）。"""
    hull = _convex_hull_int(verts)
    if len(hull) < 3:
        return 0.0
    total = 0
    for t in range(len(hull)):
        x1, y1 = hull[t]
        x2, y2 = hull[(t + 1) % len(hull)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _convex_hull_int(points):
    """整数点凸包（Andrew monotone chain）。"""
    pts = sorted(set((int(round(x)), int(round(y))) for x, y in points))
    if len(pts) <= 2:
        return pts

    def _cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _tri_score(cells, k) -> float:
    """三角聚拢度 = k² / 凸包面积（单位三角数）。

    与 game_triangle.compute_score 同式：坐标取 (2a+b, b) 的整数线性变换，
    鞋带和 /2 即单位三角数（实心大三角恰为 k²）。
    """
    if not cells:
        return 0.0
    verts = set()
    for (i, j, up) in cells:
        verts.update(tri_geometry.tri_vertices(i, j, up))
    if len(verts) < 3:
        return 0.0
    # 斜坐标 → (2a+b, b) 后鞋带和 /2 即单位三角数（与 game_triangle 同式：
    # 该变换下面积放大 2 倍，单位三角恰为 1，故不必再除）
    flat = {(2 * a + b, b) for (a, b) in verts}
    area = _hull_area(flat)
    if area <= 0:
        return 0.0
    return min(1.0, (k * k) / area)


def _mi_score(cells, m, n) -> float:
    """米字聚拢度 = 4mn / 凸包面积（单位块数）。

    与 game_mi.compute_score 同式：顶点坐标 ×2 取整，鞋带和 /2 即单位块数
    （实心 m×n 恰为 4mn 块）。
    """
    if not cells:
        return 0.0
    verts = set()
    for (r, c, q) in cells:
        verts.update(mi_geometry.block_vertices(r, c, q))
    if len(verts) < 3:
        return 0.0
    # 顶点 ×2 取整后鞋带和 /2 即单位块数（与 game_mi.hull_area_units 同式）
    flat = {(int(round(2 * x)), int(round(2 * y))) for (x, y) in verts}
    area = _hull_area(flat)
    if area <= 0:
        return 0.0
    return min(1.0, (4 * m * n) / area)


def _translate_normalized(keys):
    """键集合平移归一（各维减最小值），用于自定义样式的精确比对。"""
    if not keys:
        return frozenset()
    dim = len(next(iter(keys))[0])
    mins = [min(k[0][i] for k in keys) for i in range(dim)]
    return frozenset((tuple(k[0][i] - mins[i] for i in range(dim)), k[1])
                     for k in keys)


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
