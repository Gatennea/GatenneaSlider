# -*- coding: utf-8 -*-
"""重启器可视动画（看门进程本体）护栏，2026-11-11。

用户明确：重启动画应归**重启器（看门进程）本身**所有，覆盖「旧进程已退出、新进程未起」
的空窗期——既不是旧进程退出前的 spinner，也不是新进程冷启动的开机封面。

机制：
- request_restart() 拉起 DETACHED 看门进程（--_restart_watch + --_restart_token）；
- 看门进程本体 gui/restart_manager.run() 显示「重启中」动画窗口；
- 旧进程退出后重拉起游戏，命令行补 --_restarted <token>（新进程据此跳过冷启动开机封面）；
- 新游戏首帧绘出后写就绪哨兵，看门进程据此淡出。

本测试锁纯逻辑（无显示依赖）：
- 看门进程命令行确实携带 --_restart_token（且不含 --_restarted，那是 manager 后补的）；
- build_relaunch 在 relaunch 后补 --_restarted <token>；
- 就绪哨兵 write_ready / ready_path / clear_ready 往返一致；
- pid_alive 对当前进程返回 True。
"""
import os
import sys
import unittest
from unittest import mock

# 让 test 目录的脚本能 import 到仓库根目录的模块
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import gui.restart as restart  # noqa: E402
import gui.restart_manager as restart_manager  # noqa: E402


class RestartManagerTest(unittest.TestCase):

    def test_module_importable_without_pygame(self):
        # restart_manager 在 import 时不应触碰 pygame（仅函数内 lazy import）
        self.assertTrue(hasattr(restart_manager, 'run'))
        self.assertTrue(hasattr(restart_manager, 'build_relaunch'))

    def test_request_restart_injects_token(self):
        captured = {}

        def fake_popen(cmd, *a, **k):
            captured['cmd'] = list(cmd)
            # 不真正拉起进程
            class _P:
                pass
            return _P()

        with mock.patch('subprocess.Popen', side_effect=fake_popen):
            ok = restart.request_restart()
        self.assertTrue(ok, "request_restart 应返回 True")
        cmd = captured.get('cmd', [])
        self.assertIn('--_restart_watch', cmd, "看门进程命令行缺少 --_restart_watch")
        self.assertIn('--_restart_token', cmd, "看门进程命令行缺少 --_restart_token")
        # token 紧跟在 --_restart_token 之后且非空
        ti = cmd.index('--_restart_token')
        self.assertGreater(len(cmd), ti + 1)
        self.assertTrue(cmd[ti + 1], "--_restart_token 后的 token 为空")
        # --_restarted 不应出现在看门进程命令行（由 manager 后补到新游戏命令）
        self.assertNotIn('--_restarted', cmd,
                         "--_restarted 不应出现在看门进程命令行")

    def test_build_relaunch_appends_restarted(self):
        relaunch = ['python', 'main.py', '4', '4']
        out = restart_manager.build_relaunch(relaunch, 'TOK123')
        self.assertEqual(out, ['python', 'main.py', '4', '4', '--_restarted', 'TOK123'])
        # 不改原列表
        self.assertEqual(relaunch, ['python', 'main.py', '4', '4'])

    def test_ready_sentinel_roundtrip(self):
        tok = 'test_token_xyz'
        p = restart.ready_path(tok)
        self.assertTrue(p.endswith(restart.READY_PREFIX + tok))
        self.assertFalse(os.path.exists(p))
        restart.write_ready(tok)
        self.assertTrue(os.path.exists(p))
        restart.clear_ready(tok)
        self.assertFalse(os.path.exists(p))

    def test_pid_alive_current(self):
        self.assertTrue(restart.pid_alive(os.getpid()),
                        "pid_alive 对当前进程应返回 True")


if __name__ == '__main__':
    unittest.main()
