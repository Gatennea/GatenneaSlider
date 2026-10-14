# -*- coding: utf-8 -*-
"""打乱终态「死局黑名单」防护（纯逻辑，供 game.SliderMatrix.shuffle 调用）。

背景：4_4_2 的状态空间已严格穷举，从复原态出发可达的集合里恰好有 9 个
死局态 —— 打乱可以落在这些状态上，但它们永远无法还原回复原态（且死局态
向前封闭：从死局态出发的任何合法移动仍落在死局集合里）。打乱终态命中这些
状态 = 本局无解，必须重打。

黑名单数据：solver/deadend_blacklist.json，由
experiments/math_repro/dump_deadend_blacklist.py 从
experiments/math_repro/trap_paths_4_4_2.json 生成，格式：
    {"<m>_<n>_<step>": [规范哈希, ...]}
目前只有做过完备枚举的 4_4_2 一个 key —— 其它谜题/尺寸不在黑名单里，
防护自动不生效（不是静默兜底，而是「没枚举过就没有可判定的死局」）。

哈希口径：solver.table_core.canonicalize —— 平移归一 + 8 个 D4 变体取
字典序最小后位打包；对平移与 D4 封闭，所以游戏内任意绝对坐标的状态
直接 canonicalize 即可与表内哈希比对。
"""

import json
import os

from solver import table_core as tc

_blacklist_cache = None  # {key: frozenset[int]}，模块级只加载一次


def blacklist_path() -> str:
    """黑名单 JSON 路径（随 solver 包一起分发，见 Gatenneaslider.spec datas）。"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'deadend_blacklist.json')


def load_blacklist() -> dict:
    """加载黑名单（模块级缓存，只读一次文件）。返回 {key: frozenset[int]}。"""
    global _blacklist_cache
    if _blacklist_cache is None:
        with open(blacklist_path(), encoding='utf-8') as f:
            raw = json.load(f)
        _blacklist_cache = {k: frozenset(v) for k, v in raw.items()}
    return _blacklist_cache


def has_deadend_guard(m: int, n: int, step: int) -> bool:
    """当前谜题 {m}_{n}_{step} 是否有黑名单（做过完备枚举）→ 防护是否启用。"""
    return f'{m}_{n}_{step}' in load_blacklist()


def is_deadend(m: int, n: int, step: int, coords) -> bool:
    """终态格子集合是否命中死局黑名单。

    命中 = 一次 canonicalize + 一次 frozenset 查（代价可忽略）。
    谜题不在黑名单里时直接 False（不 canonicalize）。
    """
    key = f'{m}_{n}_{step}'
    blacklist = load_blacklist()
    if key not in blacklist:
        return False
    return tc.canonicalize(coords) in blacklist[key]
