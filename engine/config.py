# -*- coding: utf-8 -*-
"""几何引擎开关（试运行性质）。

默认 ``ENABLED = False``：走旧 game*.py 引擎，对主工作区零扰动。把开关拨到
True 即让 ``puzzle_types.create_puzzle`` 改走 ``engine.adapter.EngineGame``
（几何引擎的统一逻辑层，方形/三角/米字一套代码）。

拨动方式（暂不接 GUI；留作产品化钩子）：

    from engine.config import set_enabled
    set_enabled(True)          # 试运行：启用几何引擎
    set_enabled(False)         # 退回旧引擎（默认）

为什么是「试运行」：几何引擎是可行性验证产物，逻辑层已与三形态差分对齐
（test/_test_geometry_engine.py 的 A~M 节），但尚未接进 GUI 渲染/交互——
默认关、由这个开关显式打开，保证不改动既有产品行为。
"""

#: 是否启用几何引擎替代旧 game*.py（默认关闭，零扰动）。
ENABLED = False


def is_enabled() -> bool:
    """开关当前状态。"""
    return ENABLED


def set_enabled(value: bool) -> None:
    """拨动开关（``True``=启用几何引擎，``False``=退回旧引擎）。"""
    global ENABLED
    ENABLED = bool(value)
