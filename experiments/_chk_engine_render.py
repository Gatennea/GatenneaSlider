# -*- coding: utf-8 -*-
"""几何引擎开启下的真实 GUI 渲染冒烟（P3 可游玩观察期）。

draw_status_bar / 棋盘 / 滑块绘制全部真跑一帧——引擎接入后 GUI 手里
的块对象是 _AdapterBlock，渲染层只认 location/group/number，这里确认
三形态在引擎开关两侧都画得出来（dummy 驱动，不弹窗）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402
import tempfile  # noqa: E402

import engine.config as ecfg  # noqa: E402

# 重定向持久化，绝不碰全局开关
ecfg._config_path = os.path.join(tempfile.gettempdir(),
                                 '_gatennea_engine_cfg_render.json')

from GUI import SliderGUI  # noqa: E402

_fails = []


def check(cond, msg):
    print(("  ok: " if cond else "  FAIL: ") + msg)
    if not cond:
        _fails.append(msg)


pygame.init()
print("== 引擎开关两侧 × 三形态渲染一帧 ==")
for enabled in (False, True):
    ecfg.set_enabled(enabled)
    tag = '引擎' if enabled else '经典'
    cases = (
        ('square', lambda g: g.new_puzzle(4, 4, 2)),
        ('triangle', lambda g: g.new_triangle_puzzle(4, 2)),
        ('mi', lambda g: g.new_mi_puzzle(4, 4, 2)),
    )
    for kind, build in cases:
        try:
            gui = SliderGUI(m=4, n=4, step=2)
            ok = build(gui)
            if not ok:
                check(False, f"{tag} {kind} 建局失败")
                continue
            gui.game.shuffle(10, 2, bias=0.0, min_score=0.7)
            gui.animation_enabled = False
            # 照主循环的组帧序列（GUI.py run() 1615-1634）真画一帧
            gui.draw_board()
            gui.draw_right_panel()
            gui.draw_status_bar()
            gui.draw_menu_bar()
            # 画面不能是全黑（绘制层真的画了东西）
            w, h = gui.screen.get_size()
            px = gui.screen.get_at((w // 2, h // 2))
            nonblack = sum(1 for v in px[:3] if v > 8)
            check(nonblack > 0, f"{tag} {kind} 渲染一帧通过"
                               f"（中心像素 {tuple(px)[:3]}，"
                               f"块对象 {type(gui.game.blocks[0]).__name__}）")
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(False, f"{tag} {kind} 渲染异常：{e!r}")
ecfg.set_enabled(False)

print()
if _fails:
    print(f"失败 {len(_fails)} 項：")
    for f in _fails:
        print("  -", f)
    sys.exit(1)
print("全部通過")
