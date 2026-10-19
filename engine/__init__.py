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

纯逻辑零 pygame（AGENTS.md §10 延续）。
"""

from .analysis import (frozen, locked_seams, safe_scramble,
                       shape_reachability, verify_path)
from .board import Block, Board, BoardSpec, Move, SeamFamily
from .lattice import Lattice, cubic_lattice, square_lattice
from .registry import (board_types, cubic_board, cubic_spec,
                       get_board_type, make_board, register_board_type,
                       square_board, square_spec)

__all__ = [
    'Block', 'Board', 'BoardSpec', 'Move', 'SeamFamily',
    'Lattice', 'square_lattice', 'cubic_lattice',
    'register_board_type', 'get_board_type', 'board_types', 'make_board',
    'square_spec', 'square_board', 'cubic_spec', 'cubic_board',
    'locked_seams', 'frozen', 'shape_reachability',
    'safe_scramble', 'verify_path',
]
