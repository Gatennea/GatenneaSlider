# -*- coding: utf-8 -*-
"""重启动画改为新进程开机封面（待办 §三十四 第 8 条，2026-11-11 改写）。

重启是独立进程（看门进程机制，gui/restart.py 的 request_restart 在退出后重拉起
游戏）。旧版在「本进程退出前」播一段 spinner，用户指出那不是他要的动画——他要的
是**新进程开机**的动画。于是：

- 移除本进程退出前的 spinner（_run_restart_phase 及其 run() 调用）；
- 重启动画由新进程的 _run_boot_phase 承担，并在其首屏新增「封面」阶段
  （标题 + 副标题 + 弱化棋盘底纹，交叉淡入开机帧再淡出）。

本测试锁三项核心行为（无显示依赖，靠 fake self / fake clock + monkeypatch）：

- 启动入口确实先 request_restart()（看门进程由此 spawn），不再置 _pending_restart；
- run() 退出前不再调用 _run_restart_phase（空窗由新进程 boot 封面填补）；
- 开机封面方法存在且会绘制（封面淡入 / 交叉淡出确有 blit）。
"""
import os
import sys
import unittest
from unittest import mock

# 让 test 目录的脚本能 import 到仓库根目录的模块
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pygame  # noqa: E402
import GUI  # noqa: E402
import gui.events as events  # noqa: E402


def _gui_class():
    for name in ('SliderGUI', 'GameGUI'):
        cls = getattr(GUI, name, None)
        if cls is not None and hasattr(cls, '_run_boot_phase'):
            return cls
    return None


class _FakeScreen:
    def __init__(self, w=800, h=600):
        self.w, self.h = w, h
        self.blits = 0
        self.fills = 0

    def get_size(self):
        return (self.w, self.h)

    def fill(self, color):
        self.fills += 1

    def blit(self, *a, **k):
        self.blits += 1


class _FakeSurf:
    def __init__(self, w=854, h=480):
        self._w, self._h = w, h

    def get_size(self):
        return (self._w, self._h)

    def set_alpha(self, a):
        pass

    def get_rect(self, **kw):
        return pygame.Rect(0, 0, self._w, self._h)


class _FakeClock:
    def tick(self, fps):
        return 16


class RestartAnimationTest(unittest.TestCase):

    def test_boot_cover_methods_exist(self):
        cls = _gui_class()
        self.assertIsNotNone(cls, "找不到带 _run_boot_phase 的 GUI 类")
        for m in ('_run_boot_phase', '_make_boot_cover', '_paint_boot_cover'):
            self.assertTrue(hasattr(cls, m), f"缺少开机封面方法 {m}")
        # 旧的本进程 spinner 应已彻底移除
        self.assertFalse(hasattr(cls, '_run_restart_phase'),
                         "_run_restart_phase 应已删除（重启动画改由新进程 boot 封面承担）")

    def test_events_trigger_request_restart_only(self):
        import inspect
        src = inspect.getsource(events)
        # 两处重启触发点都应先 request_restart()（看门进程由此 spawn）
        self.assertEqual(src.count('request_restart()'), 2,
                         'request_restart() 调用次数不为 2')
        # 不再需要「本进程退出前」的标记，_pending_restart 应已移除
        self.assertNotIn('_pending_restart', src,
                         'events.py 仍残留 _pending_restart（应已删除）')

    def test_shutdown_has_no_restart_spinner(self):
        import inspect
        src = inspect.getsource(GUI.SliderGUI.run)
        self.assertNotIn('_run_restart_phase', src,
                         'run() 退出前仍调用 _run_restart_phase（旧 spinner 未移除）')
        self.assertNotIn('_pending_restart', src,
                         'run() 退出前仍检查 _pending_restart')

    def test_cover_paints(self):
        """封面阶段确有绘制：淡入 / 交叉淡出都会 blit。"""
        cls = _gui_class()
        g = type('G', (), {})()
        g.screen = _FakeScreen()
        g._boot_frames = [_FakeSurf()]
        g.show_boot_animation = True
        g.running = True
        g._boot_paint_time = 0
        # 把 GUI 类上的封面相关方法绑定到假对象（场景里它们挂在 self 上）
        g._make_boot_cover = cls._make_boot_cover.__get__(g)
        g._paint_boot = cls._paint_boot.__get__(g)
        g._paint_boot_cover = cls._paint_boot_cover.__get__(g)
        g._load_boot_frames = cls._load_boot_frames.__get__(g)

        # 推进时间：每帧 +40ms，约 60 帧即可走完整段（封面+帧+淡出≈2.3s）
        ticks = {'t': 0}

        def fake_ticks():
            ticks['t'] += 40
            return ticks['t']

        with mock.patch('pygame.time.get_ticks', side_effect=fake_ticks), \
                mock.patch('pygame.event.get', return_value=[]), \
                mock.patch('pygame.display.flip'), \
                mock.patch('pygame.draw.line', return_value=None), \
                mock.patch('pygame.transform.scale',
                           return_value=_FakeSurf()):
            try:
                cls._run_boot_phase(g, _FakeClock())
            except Exception:
                self.fail('boot 封面阶段抛异常')
        # 至少画过封面与开机帧（blit 计数 > 0）
        self.assertGreater(g.screen.blits, 0, 'boot 封面阶段没有任何绘制')


if __name__ == '__main__':
    unittest.main()
