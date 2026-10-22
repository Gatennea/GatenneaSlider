# -*- coding: utf-8 -*-
"""几何引擎开关（试运行性质）。

默认 ``ENABLED = False``：走旧 game*.py 引擎，对既有产品零扰动。打开后
``puzzle_types.create_puzzle`` 改走 ``engine.adapter.EngineGame``
（几何引擎的统一逻辑层，方形/三角/米字一套代码）。

三档来源，优先级从高到低：

    1. 运行时   ``set_enabled(True)``            —— 进程内立即生效
    2. 环境变量 ``GATENNEA_ENGINE=1``            —— 免改文件，适合临时对比
    3. 配置文件 ``config/engine.json``           —— 持久化，GUI 菜单项写这里

``is_enabled()`` 按上述顺序取值；``source()`` 告知当前值来自哪一档
（'runtime' / 'env' / 'file' / 'default'），GUI 状态栏据此提示。

为什么是「试运行」：几何引擎是可行性验证产物，逻辑层已与三形态差分对齐
（test/_test_geometry_engine.py 的 A~M 节 + test/_test_engine_adapter.py
的 N 节），但 GUI 交互/存档链路的覆盖仍在推进——默认关、由这个开关显式
打开，保证不改动既有产品行为；用户打开后即可直接对比体感是否一致。
"""

import json
import os

#: 环境变量名（值为 1/true/on/yes 视为开，其余视为关）。
ENV_VAR = 'GATENNEA_ENGINE'

#: 持久化文件名（放 config/，与既有 config/*.json 惯例一致）。
FILE_NAME = 'engine.json'

#: 进程内默认（未拨动、无环境变量、无配置文件时的取值）。
_DEFAULT = False

# 运行时覆盖：None = 未拨动（落到环境变量 / 配置文件）
_override = None


def _project_root() -> str:
    """项目根目录（engine/ 的上一级）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path() -> str:
    """持久化文件的绝对路径。"""
    return os.path.join(_project_root(), 'config', FILE_NAME)


def _truthy(raw) -> bool:
    return str(raw).strip().lower() in ('1', 'true', 'on', 'yes', 'y')


def _read_env():
    """环境变量档：未设置返回 None（未设置 ≠ 关闭，要能落到文件档）。"""
    raw = os.environ.get(ENV_VAR)
    if raw is None or raw.strip() == '':
        return None
    return _truthy(raw)


def _read_file():
    """配置文件档：文件缺失/损坏返回 None。"""
    path = config_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or 'enabled' not in data:
        return None
    return bool(data['enabled'])


def is_enabled() -> bool:
    """开关当前状态（运行时 > 环境变量 > 配置文件 > 默认关）。"""
    if _override is not None:
        return _override
    env = _read_env()
    if env is not None:
        return env
    file_val = _read_file()
    if file_val is not None:
        return file_val
    return _DEFAULT


def source() -> str:
    """当前取值来自哪一档：'runtime' / 'env' / 'file' / 'default'。"""
    if _override is not None:
        return 'runtime'
    if _read_env() is not None:
        return 'env'
    if _read_file() is not None:
        return 'file'
    return 'default'


def set_enabled(value: bool) -> None:
    """拨动开关（进程内立即生效，不写盘——写盘用 ``persist``）。"""
    global _override
    _override = bool(value)


def clear_override() -> None:
    """撤销运行时覆盖，重新听环境变量 / 配置文件。"""
    global _override
    _override = None


def persist(value: bool) -> bool:
    """把开关写进 ``config/engine.json``（不含运行时覆盖）。

    返回是否写成功（目录不可写时返回 False，由调用方提示）。
    """
    try:
        os.makedirs(os.path.dirname(config_path()), exist_ok=True)
        with open(config_path(), 'w', encoding='utf-8') as fp:
            json.dump({'enabled': bool(value)}, fp, ensure_ascii=False,
                      indent=2)
    except OSError:
        return False
    return True


def describe() -> str:
    """一行人话，供 GUI 状态栏/日志显示当前引擎与来源。"""
    on = is_enabled()
    src = {'runtime': '运行时', 'env': f'环境变量 {ENV_VAR}',
           'file': '配置文件', 'default': '默认'}[source()]
    return f"{'几何引擎' if on else '经典引擎'}（{src}）"
