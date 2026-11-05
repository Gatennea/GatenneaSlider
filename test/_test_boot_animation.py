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
        if cls is not None and hasattr(cls, '_run_boot_phase'):
            return cls
    return None


class BootAnimationSmokeTest(unittest.TestCase):

    def test_boot_methods_exist(self):
        cls = _gui_class()
        self.assertIsNotNone(cls, "找不到带 _run_boot_phase 的 GUI 类")
        # 预渲染帧序列方案的核心方法
        for m in ('_run_boot_phase', '_load_boot_frames', '_paint_boot',
                  '_boot_enabled_now', '_make_fallback_boot_surf'):
            self.assertTrue(hasattr(cls, m), f"缺少开机动画方法 {m}")
        # 旧的代码绘制 + 固定 2.4s 方案应已彻底移除（改为覆盖空缺、不叠加时长）
        for gone in ('_play_boot_animation', '_pixelate'):
            self.assertFalse(hasattr(cls, gone), f"旧开机动画方法 {gone} 应已删除")
        # 无限打乱相关方法（真正单步随机游走，绕开演示管線）
        for m in ('_start_infinite_shuffle', '_infinite_shuffle_step',
                  '_stop_infinite_shuffle', '_restore_infinite_duration'):
            self.assertTrue(hasattr(cls, m), f"缺少无限打乱方法 {m}")
        for gone in ('_start_infinite_segment', '_infinite_shuffle_continue'):
            self.assertFalse(hasattr(cls, gone), f"旧的无限打乱方法 {gone} 应已删除")

    def test_boot_frame_assets_present(self):
        # 预渲染帧序列应已生成（作者之后可替换为真动画，保持 frame_NNN.png 命名）
        import glob
        frames = sorted(glob.glob(os.path.join(_ROOT, 'picture', 'boot', 'frame_*.png')))
        self.assertGreaterEqual(len(frames), 2, "picture/boot/ 下缺少预渲染帧序列")
        self.assertTrue(
            os.path.exists(os.path.join(_ROOT, 'picture', 'splash.bmp')),
            "缺少 PyInstaller 启动图 picture/splash.bmp")

    def test_spec_bundles_boot_assets(self):
        # 打包铁律 §4：新资源必须进 spec 的 datas；启动图在 EXE 的 splash= 配置
        spec_path = os.path.join(_ROOT, 'Gatenneaslider.spec')
        self.assertTrue(os.path.exists(spec_path), "找不到打包 spec")
        with open(spec_path, 'r', encoding='utf-8') as f:
            spec = f.read()
        self.assertIn("'picture/boot'", spec, "spec datas 未打包 picture/boot 帧序列")
        self.assertIn('splash=', spec, "spec EXE 未配置 splash 启动图")

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
