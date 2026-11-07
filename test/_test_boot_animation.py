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
                  '_stop_infinite_shuffle', '_restore_infinite_duration',
                  '_finalize_infinite_state'):
            self.assertTrue(hasattr(cls, m), f"缺少无限打乱方法 {m}")
        for gone in ('_start_infinite_segment', '_infinite_shuffle_continue'):
            self.assertFalse(hasattr(cls, gone), f"旧的无限打乱方法 {gone} 应已删除")
        # 防意外打乱：确认 / 存档后打乱
        for m in ('_shuffle_has_history', '_request_shuffle_confirm',
                  '_save_then_shuffle'):
            self.assertTrue(hasattr(cls, m), f"缺防意外打乱方法 {m}")
        # 无限打乱的取步必须走穷举随机扫描（_ann_random_shuffle_move），
        # 不能再退回「game.shuffle(1) 抽 40 次」——那样会误判无路而停机
        self.assertTrue(hasattr(cls, '_ann_random_shuffle_move'),
                        "缺少 _ann_random_shuffle_move（穷举随机取步）")
        import inspect as _inspect  # noqa: E402
        step_src = _inspect.getsource(cls._infinite_shuffle_step)
        self.assertIn('_ann_random_shuffle_move', step_src,
                      "_infinite_shuffle_step 未使用穷举随机取步")
        self.assertNotIn('tries < 40', step_src,
                         "_infinite_shuffle_step 仍在用 40 次抽样兜底")

    def test_boot_frame_assets_present(self):
        # 预渲染帧序列应已生成（作者之后可替换为真动画，保持 frame_NNN.png 命名）
        import glob
        frames = sorted(glob.glob(os.path.join(_ROOT, 'assets', 'picture', 'boot', 'frame_*.png')))
        self.assertGreaterEqual(len(frames), 2, "assets/picture/boot/ 下缺少预渲染帧序列")
        self.assertTrue(
            os.path.exists(os.path.join(_ROOT, 'assets', 'picture', 'splash.bmp')),
            "缺少 PyInstaller 启动图 assets/picture/splash.bmp")

    def test_spec_bundles_boot_assets(self):
        # 打包铁律 §4：新资源必须进 spec 的 datas；启动图在 EXE 的 splash= 配置
        spec_path = os.path.join(_ROOT, 'Gatenneaslider.spec')
        self.assertTrue(os.path.exists(spec_path), "找不到打包 spec")
        with open(spec_path, 'r', encoding='utf-8') as f:
            spec = f.read()
        self.assertIn("'assets/picture/boot'", spec, "spec datas 未打包 assets/picture/boot 帧序列")
        self.assertIn('splash=', spec, "spec EXE 未配置 splash 启动图")

    def test_boot_frames_are_pixel_art_not_static_icon(self):
        """2026-11-07 换代护栏：像素风标题 + 棋盘动画，不许退回图标底 / 平滑缩放。

        用像素级差分证明「打乱→还原」真的在动（首末帧空位数量差很多），
        再静态钉住两条容易回流的写法：smoothscale 会糊掉硬边、cover.png 是旧图标底。
        """
        import glob as _glob
        import inspect as _inspect
        import numpy as np
        from PIL import Image

        frames = sorted(_glob.glob(
            os.path.join(_ROOT, 'assets', 'picture', 'boot', 'frame_*.png')))
        self.assertGreaterEqual(len(frames), 2)
        sizes = set()
        for p in frames:
            with Image.open(p) as im:
                sizes.add(im.size)
        self.assertEqual(len(sizes), 1, '开机帧尺寸不一致')
        self.assertEqual(sizes.pop(), (854, 480))

        with Image.open(frames[0]) as a, Image.open(frames[-1]) as b:
            diff = np.abs(np.asarray(a.convert('RGB'), dtype=np.int16)
                          - np.asarray(b.convert('RGB'), dtype=np.int16))
        changed = int((diff.max(axis=2) > 24).sum())
        self.assertGreater(changed, 20000,
                           '首末帧几乎一样：打乱→还原的棋盘动画没做出来')

        gen = os.path.join(_ROOT, 'tools', 'gen_boot_assets.py')
        with open(gen, 'r', encoding='utf-8') as f:
            src = f.read()
        self.assertIn('pygame.transform.scale(', src, '像素字缺最近邻放大')
        self.assertNotIn('pygame.transform.smoothscale(', src,
                         '像素字被平滑插值糊掉')
        # cover.png 只许当「抠出来的独立小 Logo」，不许再变回全屏底图
        self.assertTrue(os.path.exists(os.path.join(_ROOT, 'assets', 'picture', 'cover.png')),
                        '缺 Logo 源素材 assets/picture/cover.png')
        self.assertIn('build_logo(', src, '开机画面缺独立 Logo')
        self.assertIn('COVER_SRC', src, 'Logo 没指向 cover.png')
        self.assertNotIn('blit(cover', src, '又拿 cover.png 当全屏底图')
        self.assertIn('_filled(', src, '棋盘打乱→还原逻辑不见了')

        # 真把 Logo 画进帧里：按 GUI 的底色 (30,30,30) 做 alpha 合成后，
        # 标题上方中央应有大片亮线稿像素，同尺寸的纯棋盘区域则几乎没有。
        with Image.open(frames[len(frames) // 2]) as im:
            rgba = np.asarray(im.convert('RGBA'), dtype=np.float32)
        alpha = rgba[:, :, 3:4] / 255.0
        comp = rgba[:, :, :3] * alpha + np.array([30, 30, 30], dtype=np.float32) * (1 - alpha)
        logo_band = comp[20:185, 340:515]
        board_band = comp[20:185, 40:215]
        bright = int((logo_band.mean(axis=2) > 150).sum())
        board_bright = int((board_band.mean(axis=2) > 150).sum())
        self.assertGreater(bright, 2000, '标题上方看不到 Logo 线稿')
        self.assertLess(board_bright, 500, '整屏都在发亮，不像暗化棋盘')

        paint = _inspect.getsource(_gui_class()._paint_boot)
        self.assertIn('pygame.transform.scale(', paint)
        self.assertNotIn('pygame.transform.smoothscale(', paint,
                         '_paint_boot 改回平滑缩放会把像素块抹成灰边')

    def test_boot_palette_and_font_note(self):
        """字色必须取自 GUI.py 的 self.colors；字体来源的注释不许再含糊。"""
        import ast

        def rgb_tuples(node):
            """从 dict / 赋值里抠出所有 (r,g,b) 字面量。"""
            out = {}
            pairs = []
            if isinstance(node, ast.Dict):
                pairs = [(k.value if isinstance(k, ast.Constant) else None, v)
                         for k, v in zip(node.keys, node.values)]
            elif isinstance(node, ast.Module):
                for stmt in node.body:
                    if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                            and isinstance(stmt.targets[0], ast.Name)):
                        pairs.append((stmt.targets[0].id, stmt.value))
            for name, val in pairs:
                if (isinstance(val, ast.Tuple) and len(val.elts) == 3
                        and all(isinstance(e, ast.Constant) and isinstance(e.value, int)
                                for e in val.elts)):
                    out[name] = tuple(e.value for e in val.elts)
            return out

        with open(os.path.join(_ROOT, 'GUI.py'), 'r', encoding='utf-8') as f:
            gui_tree = ast.parse(f.read())
        game_colors = set()
        for node in ast.walk(gui_tree):
            if (isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Attribute) and t.attr == 'colors'
                            for t in node.targets)):
                game_colors.update(rgb_tuples(node.value).values())
        self.assertGreater(len(game_colors), 15, '没读到 GUI.py 的游戏调色板')

        gen = os.path.join(_ROOT, 'tools', 'gen_boot_assets.py')
        with open(gen, 'r', encoding='utf-8') as f:
            src = f.read()
        boot_colors = rgb_tuples(ast.parse(src))
        for name in ('BG', 'BLOCK', 'SEAM', 'EDGE', 'INK', 'SUB',
                     'DIM', 'SHADOW', 'LOGO_LINE'):
            self.assertIn(name, boot_colors, f'开机脚本缺颜色常量 {name}')
            self.assertIn(boot_colors[name], game_colors,
                          f'{name}={boot_colors[name]} 不是游戏 self.colors 里的颜色')

        # 上一版注释写「不依赖字体文件」会让人误以为字形是手绘点阵。
        # 准确说法：只在重生成时读开发机 Windows 系统字体，运行时只读 PNG。
        self.assertIn('Windows 系统字体', src, '注释没说清字体来自系统字体')
        self.assertIn('只读 PNG', src, '注释没说清运行时不依赖字体')
        self.assertNotIn('不依赖字体文件', src,
                         '「不依赖字体文件」是错的：重生成时要读系统字体')

    def test_bgm_compressed_and_mixer_not_excluded(self):
        """背景乐正式素材是压缩格式；spec 不许把 mixer 排掉、不许带 music/*.wav。"""
        import gui.audio as audio

        music = os.path.join(_ROOT, 'assets', 'audio', 'music')
        found = audio._find_in(music, 'bgm')
        self.assertIsNotNone(found, 'music/ 下找不到 bgm.*')
        self.assertTrue(found.lower().endswith(('.ogg', '.mp3')),
                        f'背景乐退回未压缩格式：{found}')

        spec_path = os.path.join(_ROOT, 'Gatenneaslider.spec')
        with open(spec_path, 'r', encoding='utf-8') as f:
            spec = f.read()
        self.assertIn('_collect_assets()', spec, 'spec 没走 wav 过滤')
        self.assertIn("name.lower().endswith('.wav')", spec)
        excludes = spec.split('excludes = [', 1)[1].split(']', 1)[0]
        self.assertNotIn("'pygame.mixer'", excludes,
                         'pygame.mixer 被排除 → 打包版音效全静音')
        self.assertNotIn("'pygame.mixer_music'", excludes,
                         'pygame.mixer_music 被排除 → 打包版 bgm 静音')

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
        for key in ('show_boot_animation', 'infinite_shuffle', 'confirm_before_shuffle'):
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
        self.assertIn("'confirm_before_shuffle':", src, "save_config 未持久化 confirm_before_shuffle")
        self.assertIn("'confirm_before_shuffle' in config", src, "load_last_state 未读取 confirm_before_shuffle")
        # 「存档」第三按钮在通用确认框上有渲染与事件处理
        import gui.dialogs as dialogs  # noqa: E402
        dsrc = inspect.getsource(dialogs)
        self.assertIn('confirm_extra_btn', dsrc, "确认框未支持可选的第三按钮")
        self.assertIn('confirm_extra_action', dsrc, "确认框未支持第三按钮回调")


if __name__ == '__main__':
    unittest.main()
