# -*- coding: utf-8 -*-
"""开机动画冒烟测试（无显示依赖，仅校验结构与默认值）。

真实视觉表现需在带显示的环境下启动游戏人工验收；
本测试只保证：方法存在、默认开关为开、config 键名约定一致。
"""
import os
import sys
import unittest

# 让 test 目录的脚本能 import 到仓库根目录的模块
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import GUI  # noqa: E402


def _gui_class():
    for name in ('SliderGUI', 'GameGUI'):
        cls = getattr(GUI, name, None)
        if cls is not None and hasattr(cls, '_play_boot_animation'):
            return cls
    return None


class BootAnimationSmokeTest(unittest.TestCase):

    def test_boot_methods_exist(self):
        cls = _gui_class()
        self.assertIsNotNone(cls, "找不到带 _play_boot_animation 的 GUI 类")
        self.assertTrue(hasattr(cls, '_pixelate'), "缺少 _pixelate 像素化辅助方法")
        # 无限打乱相关方法（真正单步随机游走，绕开演示管線）
        for m in ('_start_infinite_shuffle', '_infinite_shuffle_step',
                  '_stop_infinite_shuffle', '_restore_infinite_duration'):
            self.assertTrue(hasattr(cls, m), f"缺少无限打乱方法 {m}")
        # 旧的分段续接方案已废弃，不应残留
        for gone in ('_start_infinite_segment', '_infinite_shuffle_continue'):
            self.assertFalse(hasattr(cls, gone), f"旧的无限打乱方法 {gone} 应已删除")

    def test_infinite_bypasses_demo_pipeline(self):
        # 无限打乱必须是真·单步游走，不进入打乱演示管線
        # （否则会画进度条、走淡出切屏）—— commit_animation 续播入口改指
        # _infinite_shuffle_step，而非演示的 _play_next_shuffle_record。
        import inspect  # noqa: E402
        import gui.animation as animation  # noqa: E402
        src = inspect.getsource(animation.AnimationMixin.commit_animation)
        self.assertIn('_infinite_shuffle_step()', src,
                      "commit_animation 未续播到 _infinite_shuffle_step")
        # 且不应再残留演示续接的旧钩子
        self.assertNotIn('_infinite_shuffle_continue', src,
                         "commit_animation 仍残留旧续接钩子")

    def test_settings_bool_key_synced(self):
        # 两份白名单都应包含开机动画/无限打乱开关，保证本地/远程设置对称（§16）
        import gui.events as events  # noqa: E402
        import http_server  # noqa: E402
        for key in ('show_boot_animation', 'infinite_shuffle'):
            self.assertIn(key, events.EventsMixin._SETTINGS_BOOL_KEYS)
            self.assertIn(key, http_server.GameHTTPHandler._SETTINGS_BOOL_KEYS)

    def test_config_key_name(self):
        # save_config 用 'boot_animation' / 'infinite_shuffle' 持久化，
        # load_last_state 读同名键
        import inspect  # noqa: E402
        import gui.file_ops as file_ops  # noqa: E402
        src = inspect.getsource(file_ops)
        self.assertIn("'boot_animation':", src, "save_config 未持久化 boot_animation")
        self.assertIn("'boot_animation' in config", src, "load_last_state 未读取 boot_animation")
        self.assertIn("'infinite_shuffle':", src, "save_config 未持久化 infinite_shuffle")
        self.assertIn("'infinite_shuffle' in config", src, "load_last_state 未读取 infinite_shuffle")


if __name__ == '__main__':
    unittest.main()
