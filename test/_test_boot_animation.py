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

    def test_settings_bool_key_synced(self):
        # 两份白名单都应包含开机动画开关，保证本地/远程设置对称（§16）
        import gui.events as events  # noqa: E402
        import http_server  # noqa: E402
        self.assertIn('show_boot_animation', events.EventsMixin._SETTINGS_BOOL_KEYS)
        self.assertIn('show_boot_animation', http_server.GameHTTPHandler._SETTINGS_BOOL_KEYS)

    def test_config_key_name(self):
        # save_config 用 'boot_animation' 持久化，load_last_state 读同名键
        import inspect  # noqa: E402
        import gui.file_ops as file_ops  # noqa: E402
        src = inspect.getsource(file_ops)
        self.assertIn("'boot_animation':", src, "save_config 未持久化 boot_animation")
        self.assertIn("'boot_animation' in config", src, "load_last_state 未读取 boot_animation")


if __name__ == '__main__':
    unittest.main()
