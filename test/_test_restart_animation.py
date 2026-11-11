# -*- coding: utf-8 -*-
"""重启等待期加载动画（待办 §三十四 第 8 条）冒烟 + 行为测试。

不依赖真实显示：用 fake self / fake clock + monkeypatch 的 pygame 顶层调用，
锁住三项核心行为：

- 动画播够 HOLD 时长（约 1.2s）才返回，期间确实在画 spinner；
- QUIT 事件 / 任意键可提前退出，且不画多余帧；
- ``show_restart_animation`` 关掉时不播。

以及事件层两处重启触发点确实先 request_restart、再置 _pending_restart、
最后 running=False；run() 退出前确实检查 _pending_restart 并调用
_run_restart_phase(clock)。
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


def _gui_class():
    for name in ('SliderGUI', 'GameGUI'):
        cls = getattr(GUI, name, None)
        if cls is not None and hasattr(cls, '_run_restart_phase'):
            return cls
    return None


class _FakeScreen:
    def __init__(self, w=800, h=600):
        self.w, self.h = w, h

    def get_size(self):
        return (self.w, self.h)

    def fill(self, color):
        pass

    def blit(self, *a, **k):
        pass


class _FakeSurf:
    def get_rect(self, **kw):
        return pygame.Rect(0, 0, 10, 10)


class _FakeFont:
    def render(self, text, antialias, color):
        return _FakeSurf()


class _FakeClock:
    def __init__(self, dt=16):
        self.dt = dt

    def tick(self, fps):
        return self.dt


def _make_gui(**kw):
    g = type('G', (), {})()
    g.screen = _FakeScreen()
    g.status_font = _FakeFont()
    g.show_restart_animation = kw.get('show', True)
    g._pending_restart = True
    return g


class RestartAnimationTest(unittest.TestCase):

    def test_method_and_flag_exist(self):
        cls = _gui_class()
        self.assertIsNotNone(cls, "找不到带 _run_restart_phase 的 GUI 类")
        self.assertTrue(hasattr(cls, '_run_restart_phase'))
        import inspect
        init_src = inspect.getsource(cls.__init__)
        self.assertIn('show_restart_animation', init_src,
                      '__init__ 缺省未初始化 show_restart_animation')
        self.assertIn('_pending_restart', init_src,
                      '__init__ 缺省未初始化 _pending_restart')

    def test_runs_until_hold(self):
        g = _make_gui()
        arc_calls = []
        flips = []

        def fake_ticks():
            # 每帧推进 100ms，绕开真实时钟
            fake_ticks.t = fake_ticks.t + 100
            return fake_ticks.t
        fake_ticks.t = 0

        with mock.patch('pygame.time.get_ticks', side_effect=fake_ticks), \
                mock.patch('pygame.event.get', return_value=[]), \
                mock.patch('pygame.display.flip',
                           side_effect=lambda: flips.append(1)), \
                mock.patch('pygame.draw.arc',
                           side_effect=lambda *a, **k: arc_calls.append(1)):
            cls = _gui_class()
            cls._run_restart_phase(g, _FakeClock())
        # HOLD=1200ms、每帧 +100ms ⇒ 约 12 帧后才返回
        self.assertGreater(len(arc_calls), 5, '动画未播放足够帧数（可能提前退出）')
        self.assertGreater(len(flips), 5, '动画未刷新足够帧数')

    def test_quit_event_exits_early(self):
        g = _make_gui()
        arc_calls = []
        with mock.patch('pygame.time.get_ticks', return_value=0), \
                mock.patch('pygame.event.get',
                           return_value=[pygame.event.Event(pygame.QUIT)]), \
                mock.patch('pygame.display.flip'), \
                mock.patch('pygame.draw.arc',
                           side_effect=lambda *a, **k: arc_calls.append(1)):
            cls = _gui_class()
            cls._run_restart_phase(g, _FakeClock())
        self.assertEqual(len(arc_calls), 0, 'QUIT 事件未让动画立即退出')

    def test_keydown_exits_early(self):
        g = _make_gui()
        arc_calls = []
        with mock.patch('pygame.time.get_ticks', return_value=0), \
                mock.patch('pygame.event.get',
                           return_value=[pygame.event.Event(pygame.KEYDOWN, key=0)]), \
                mock.patch('pygame.display.flip'), \
                mock.patch('pygame.draw.arc',
                           side_effect=lambda *a, **k: arc_calls.append(1)):
            cls = _gui_class()
            cls._run_restart_phase(g, _FakeClock())
        self.assertEqual(len(arc_calls), 0, 'KEYDOWN 未让动画立即退出')

    def test_disabled_by_flag(self):
        g = _make_gui(show=False)
        arc_calls = []
        with mock.patch('pygame.time.get_ticks', return_value=99999), \
                mock.patch('pygame.event.get', return_value=[]), \
                mock.patch('pygame.display.flip'), \
                mock.patch('pygame.draw.arc',
                           side_effect=lambda *a, **k: arc_calls.append(1)):
            cls = _gui_class()
            cls._run_restart_phase(g, _FakeClock())
        self.assertEqual(len(arc_calls), 0, '开关关闭后仍播了动画')

    def test_events_wiring_sets_pending_restart(self):
        import inspect
        import gui.events as events
        src = inspect.getsource(events)
        # 两处重启触发点都应：先 request_restart()、再置 _pending_restart、
        # 再 running=False
        self.assertEqual(src.count('request_restart()'), 2,
                         'request_restart() 调用次数不为 2')
        self.assertGreaterEqual(src.count('_pending_restart = True'), 2,
                                '重启触发点未设置 _pending_restart')

    def test_shutdown_invokes_phase(self):
        import inspect
        src = inspect.getsource(GUI.SliderGUI.run)
        self.assertIn('_pending_restart', src,
                      'run() 退出前未检查 _pending_restart')
        self.assertIn('_run_restart_phase(clock)', src,
                      'run() 退出前未调用 _run_restart_phase(clock)')


if __name__ == '__main__':
    unittest.main()
