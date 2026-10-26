# -*- coding: utf-8 -*-
"""回归：模型板型（自造谜题）的画风必须与碎三角一致。

用户 2026-10-26：**自造謎題和原先畫風不一致（理論上應該和碎三角完全一致）**。

根因不是渲染代码分叉——两者都走通用多边形通道（`_draw_polygon_board`），
差别只在**板型渲染参数**：碎三角的 `models/shatter.json` 显式写了
`seam_width: 6 / corner_radius: 3`（6px 缝带 + 圆角），而编辑器存出来的模型
（shield、222…）没写这两个字段 → 渲染器退回方形旧口径（gap_width + 圆角比例）
→ 视觉上是「块贴块 + 一条黑细线」，与碎三角明显不同。

本测试钉住：
  A. 缺省：没写 seam_width / corner_radius 的模型也拿到 6 / 3（与碎三角同款）；
  B. 显式值优先：文件写了别的值（8 / 4）就用文件的值，缺省不覆盖；
  C. 编辑器保存的文档显式带这两个字段（文件自解释，不依赖 loader 缺省）；
  D. 渲染分支真的走到「显式圆角 / 显式缝宽」这条（不是退回旧口径）。

跑法：D:/python/python.exe test/_test_model_style.py
"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402

from engine import model_loader  # noqa: E402
from engine.adapter import create_adapter_puzzle  # noqa: E402
from GUI import SliderGUI  # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg} {extra}')
    return bool(cond)


def _make_gui():
    gui = SliderGUI(m=4, n=4, step=1)
    gui.animation_enabled = False
    gui._readonly = False
    gui.save_readonly_flag = False
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    return gui


def main():
    # ---- A. 缺省：shield 没写这两个字段，也要拿到碎三角同款 ----
    g = create_adapter_puzzle('shield', 4, 4, 1)
    spec = g.spec
    check(spec.seam_width == model_loader.DEFAULT_SEAM_WIDTH,
          f'A1 缺省 seam_width = {model_loader.DEFAULT_SEAM_WIDTH}',
          f'actual={getattr(spec, "seam_width", None)!r}')
    check(spec.corner_radius == model_loader.DEFAULT_CORNER_RADIUS,
          f'A2 缺省 corner_radius = {model_loader.DEFAULT_CORNER_RADIUS}',
          f'actual={getattr(spec, "corner_radius", None)!r}')
    check([spec.seam_width, spec.corner_radius]
          == [model_loader.DEFAULT_SEAM_WIDTH,
              model_loader.DEFAULT_CORNER_RADIUS],
          'A3 缺省值与碎三角文件里的 6 / 3 一致（画风同款）')
    check(spec.corner_radius <= spec.seam_width / 2.0,
          'A4 圆角半径 ≤ 缝半宽（否则圆角弧越过缝、顶点戳尖刺）')

    # ---- 碎三角（显式 6/3）不受影响 ----
    sh = create_adapter_puzzle('shatter', 4, 4, 1)
    check(sh.spec.seam_width == 6 and sh.spec.corner_radius == 3,
          'A5 碎三角的显式 6 / 3 保持不变',
          f'actual={sh.spec.seam_width!r}/{sh.spec.corner_radius!r}')

    # ---- B. 显式值优先（用碎三角的文档改两个数再造一份）----
    from engine import model_registry
    doc = dict(model_registry.loaded('shatter').doc)
    doc['name'] = '__style_probe__'
    doc['seam_width'] = 8
    doc['corner_radius'] = 4
    probe = model_loader.load_model(doc)
    check(probe.spec.seam_width == 8 and probe.spec.corner_radius == 4,
          'B1 文件里显式写的 8 / 4 优先于缺省',
          f'actual={probe.spec.seam_width!r}/{probe.spec.corner_radius!r}')

    # ---- C. 编辑器保存的文档显式带画风字段 ----
    gui = _make_gui()
    ok = gui.new_model_puzzle('shield', 1)
    check(ok, 'C0 shield 建局成功（前置）')
    gui.set_game_mode('create')
    gui._ann_btn_blocks_current()          # 导入当前盘面
    check(gui._med_active, 'C1 编辑器打开（前置）',
          f'msg={gui.macro_notify_msg!r}')
    if gui._med_active:
        out = gui._med_build_doc('__style_probe__')
        check(out.get('seam_width') == model_loader.DEFAULT_SEAM_WIDTH
              and out.get('corner_radius')
              == model_loader.DEFAULT_CORNER_RADIUS,
              'C2 编辑器保存的文档显式写 seam_width / corner_radius',
              f'sw={out.get("seam_width")!r} cr={out.get("corner_radius")!r}')
        gui._med_close()
    else:
        check(False, 'C2 跳过（编辑器没打开）')

    # ---- D. 渲染分支：显式圆角 / 显式缝宽都生效 ----
    gui = _make_gui()
    gui.new_model_puzzle('shield', 1)
    gui.center_map()
    spec = gui.game.board.spec
    check(getattr(spec, 'corner_radius', None) is not None,
          'D1 渲染器会走「显式圆角」分支（_explicit_corner=True）')
    check(getattr(spec, 'seam_width', None) is not None,
          'D2 渲染器会走「板型缝宽」分支（不退回 gap_width）')
    # 画一帧，确认不炸（三趟绘制 + 圆角 + 缝带）
    try:
        gui.draw_board()
        drew = True
        err = ''
    except Exception as exc:               # noqa: BLE001
        drew, err = False, repr(exc)
    check(drew, 'D3 通用通道按新参数绘制无异常', err)

    print(f"\n结果：{'全部通过' if not _fail else str(len(_fail)) + ' 项失败'} "
          f"（{_ok[0]} 项通过）")
    if _fail:
        for m in _fail:
            print('  · 失败：', m)
        sys.exit(1)


if __name__ == '__main__':
    main()
