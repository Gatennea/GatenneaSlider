# -*- coding: utf-8 -*-
"""几何引擎（Geometry Engine）——原型 v0（feat/geometry-engine 分支）。

愿景与路线图见 docs/spec/几何引擎.md；本包是该方向的 P0 可行性原型：
把「密铺形态」压缩成一份可注册的数据（板型 BoardSpec），规则层
（合法移动 / 规范形 / 还原判定 / 捆绑 / 锁死缝 / 冻形 / 可逆打乱）
全部形态无关，GUI 与求解器今后只同这一层对话。

P0 范围（有意收敛）：
  · 内置方形 preset，且与现有方形引擎**差分对齐**（移动结果集合 /
    规范形 / 还原判定逐项全等，见 test/_test_geometry_engine.py）；
  · 内置立方 preset 证明核心对维度无感（用户方向的三维预留）；
  · 锁死缝（seam_clear）与特殊还原判定（solved_check）两个钩子为
    米字 / 三角预留（P2 实例化）；
  · 不动 game*.py / gui/ / solver/——main 行为零变化。

P1 已完成映射件（本分支）：``engine/compat.py`` 提供 Move ↔ 既有动作格式
（history 动作 dict / 打乱演示 record）的映射层与 ``apply_action`` 回放
原语，为「方形引擎切到引擎层」铺桥（见 docs/spec/几何引擎.md §5）；
「切层本体」（让 GUI/求解器改调引擎层）未开始。

P2 进行中（本分支）：``(point, orient)`` 联合键 + orient 进规范形 +
四族缝 rank 钩子已落地，**米字 + 三角 preset 已实例化**：
  · 米字（``engine/mi_geometry.py``）与 game_mi 差分对齐（测试 L 节）；
  · 三角（``engine/tri_geometry.py``，中心反演对称 + 还原态 120°
    轨道 solved_check）与 game_triangle 差分对齐（测试 M 节）。
产品化预检（锁死缝/冻形/可打乱性 GUI 提示）属 P2 剩余件。

纯逻辑零 pygame（AGENTS.md §10 延续）。
"""

from .analysis import (frozen, locked_seams, safe_scramble,
                       shape_reachability, verify_path)
from .adapter import EngineGame, create_adapter_puzzle  # noqa: F401  （启用开关落点）
from .board import Block, Board, BoardSpec, Move, SeamFamily
from .compat import (SQUARE_DIRECTIONS, action_to_move, apply_action,  # noqa: F401
                     direction_table, move_to_action, move_to_record,
                     record_to_action, record_to_move,
                     register_direction_vocab)
from .config import ENABLED, is_enabled, set_enabled  # noqa: F401  （试运行开关）
from .lattice import Lattice, cubic_lattice, square_lattice
from .registry import (board_types, cubic_board, cubic_spec,
                       get_board_type, make_board, mi_board, mi_lattice,
                       mi_spec, register_board_type, square_board,
                       square_spec, tri_board, tri_lattice, tri_spec)
from . import mi_geometry, tri_geometry  # noqa: E402  （几何层，供测试/适配器直接引用）

__all__ = [
    'Block', 'Board', 'BoardSpec', 'Move', 'SeamFamily',
    'Lattice', 'square_lattice', 'cubic_lattice',
    'register_board_type', 'get_board_type', 'board_types', 'make_board',
    'square_spec', 'square_board', 'cubic_spec', 'cubic_board',
    'mi_spec', 'mi_board', 'mi_lattice',
    'tri_spec', 'tri_board', 'tri_lattice', 'tri_geometry', 'mi_geometry',
    'locked_seams', 'frozen', 'shape_reachability',
    'safe_scramble', 'verify_path',
    'SQUARE_DIRECTIONS', 'register_direction_vocab', 'direction_table',
    'move_to_action', 'action_to_move', 'apply_action',
    'move_to_record', 'record_to_action', 'record_to_move',
    'EngineGame', 'create_adapter_puzzle',
    'ENABLED', 'is_enabled', 'set_enabled',
]
