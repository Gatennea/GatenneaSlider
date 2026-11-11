# -*- coding: utf-8 -*-
"""护栏：后台密集搜索核心（guided_reduce_one）必须在循环里周期性让出 GIL。

根因：求解期游戏卡顿、进度/计时器几秒不刷新的根因之一是——后台 auto_solve
线程跑纯 Python 的 GBFS 搜索（guided_reduce_one），连续展开成百上千节点、
全程持有 GIL 不主动让出，主线程（渲染+事件）被饿死。修复 = 在该搜索循环里每
展开 256 节点 time.sleep(0)（参考 fill_macro.py / model_preview.py 同款 GIL
让出，开销可忽略、不影响结果与 rng）。

本护栏用 mock 把搜索逼到跑满 budget（强制展开 >=256 节点），断言 time.sleep
被周期性调用且参数为 0（只让出时间片、不主动睡）。反向验证：撤掉 sleep(0)
后 time.sleep 不再被调用，本测试转红。

脚本型测试（conftest 子进程收集，需 __main__ 守卫）。
"""
import os
import sys
import time as _time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver import search_core


def _recording_sleep(s):
    _recording_sleep.calls.append(s)


class TestGilYield(unittest.TestCase):
    def test_search_core_yields_gil_while_busy(self):
        # 强制搜索跑满 budget：mock heuristic_parts 让所有邻居洞数恒 = 2，
        # 起点为 1 洞（h0=1），则「洞数严格变少」永不成立 → GBFS 跑到 budget
        # 上限，必然展开 >=256 节点，从而触发周期性让出。
        calls = []
        _recording_sleep.calls = calls
        _orig_sleep = _time.sleep
        _orig_hp = search_core.heuristic_parts

        def _mock_hp(coords, m, n, step):
            return (0.0, 2)

        _time.sleep = _recording_sleep
        search_core.heuristic_parts = _mock_hp
        try:
            m, n, step = 4, 4, 2
            coords = {(r, c) for r in range(m) for c in range(n)
                      if not (r == 0 and c == 0)}   # 1 洞
            path, expanded = search_core.guided_reduce_one(
                list(coords), m, n, step, budget=600)
        finally:
            _time.sleep = _orig_sleep
            search_core.heuristic_parts = _orig_hp

        self.assertGreaterEqual(
            expanded, 256,
            "mock 未使搜索展开 >=256 节点，测试前提失效")
        self.assertGreaterEqual(
            len(calls), 1,
            "搜索核心未在密集循环周期性让出 GIL (time.sleep)；"
            "求解期后台线程会饿死主线程导致游戏卡顿/计时器停")
        self.assertTrue(
            all(c == 0 for c in calls),
            "让出 GIL 不应主动 sleep 正时长，应为 time.sleep(0)")


if __name__ == '__main__':
    unittest.main()
