# -*- coding: utf-8 -*-
"""§六十二 护栏：立体光效（二维面内四边微倒角）开关。

覆盖（对应 docs/agent/待办清单.md §62 验收）：
- 护栏A「开关关时渲染与改动前一致」= 关态下三形态绘制 **零次** 走
  `_draw_face_bevel`（行为判据：运行时调用计数，不用源码字符串）
- 护栏B 三形态视觉回归：开/关两帧像素不同（开关真生效）+ 关态两帧一致（确定性）
- 护栏C 方向数学：上边提亮、下边压暗（与三维 face_shade 同向）
- 三处同步（AGENTS §16）：config.json 存取 / _SETTINGS_BOOL_KEYS / http 白名单
- 设置页开关与 feature_index 登记（§3 新红线）+ 一键切换接线
- AA 路径与直出路径走同一 helper

运行：python test/_test_face_bevel.py
"""
import json
import os
import queue
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from gui import renderer as renderer_mod  # noqa: E402
from gui import events as events_mod  # noqa: E402
from gui import feature_index as fi  # noqa: E402
import http_server  # noqa: E402

PASSED = 0
FAILED = 0
_calls = []
_orig_bevel = renderer_mod._draw_face_bevel


def _counting_bevel(*args, **kwargs):
    _calls.append(args[0] if args else None)
    return _orig_bevel(*args, **kwargs)


def check(cond, label, detail=''):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f'PASS: {label}')
    else:
        FAILED += 1
        d = f' -- {detail}' if detail else ''
        print(f'FAIL: {label}{d}')


def boot(which, *args):
    gui = SliderGUI(cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.game_mode = 'practice'
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    gui.animation_enabled = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    getattr(gui, which)(*args)
    gui._update_in_progress = False
    return gui


def frame_bytes(gui, draw_fn):
    draw_fn()
    return pygame.image.tobytes(gui.screen, 'RGB')


def run_form(name, which, args, draw_attr):
    """一个形态：关态零调用 + 关/开两帧像素不同 + 关态确定性。"""
    gui = boot(which, *args)
    draw = getattr(gui, draw_attr)

    gui.face_bevel_enabled = False
    _calls.clear()
    b_off1 = frame_bytes(gui, draw)
    check(len(_calls) == 0,
          f'{name} 关态不走倒角（渲染与改动前一致）', f'调用 {len(_calls)} 次')
    b_off2 = frame_bytes(gui, draw)
    check(b_off1 == b_off2, f'{name} 关态两帧一致（渲染确定性）')

    gui.face_bevel_enabled = True
    _calls.clear()
    b_on = frame_bytes(gui, draw)
    check(len(_calls) > 0, f'{name} 开态走倒角 helper', f'调用 {len(_calls)} 次')
    check(b_on != b_off1, f'{name} 开/关两帧像素不同（开关真生效）')
    gui.face_bevel_enabled = False
    return gui


def run():
    global PASSED, FAILED
    renderer_mod._draw_face_bevel = _counting_bevel
    try:
        # ---------- 1 默认值与真源登记 ----------
        print('\n--- 1 默认值 / feature_index 登记（§3 红线） ---')
        gui = SliderGUI(cmd_queue=queue.Queue(),
                        ext_state={'enabled': False, 'token': None})
        check(gui.face_bevel_enabled is True, '默认开（用户点名要这效果）')
        ent = next((f for f in fi.FEATURES if f['id'] == 'face_bevel_enabled'), None)
        check(ent is not None, 'feature_index 已登记 face_bevel_enabled')
        check(ent is not None and ent['action'].get('type') == 'toggle',
              'action 接一键切换 toggle')
        check('face_bevel_enabled' in events_mod.EventsMixin._SETTINGS_BOOL_KEYS,
              '_SETTINGS_BOOL_KEYS 同步')
        check('face_bevel_enabled' in http_server.GameHTTPHandler._SETTINGS_BOOL_KEYS,
              'http 白名单同步')

        # ---------- 2 方向数学（helper 单元）----------
        print('\n--- 2 倒角方向：上提亮 / 下压暗 ---')
        surf = pygame.Surface((120, 120))
        fill = (100, 140, 190)
        surf.fill(fill)  # 真实路径：先填面底色，再压倒角带
        pts = [(10, 10), (110, 10), (110, 110), (10, 110)]
        _orig_bevel(surf, pts, fill)
        top = surf.get_at((60, 14))     # 上边带（应 > fill）
        bot = surf.get_at((60, 106))    # 下边带（应 < fill）
        left = surf.get_at((14, 60))
        right = surf.get_at((106, 60))
        check(top[0] > fill[0] and top[1] > fill[1],
              '上边提亮', f'top={tuple(top[:3])}')
        check(bot[0] < fill[0] and bot[1] < fill[1],
              '下边压暗', f'bot={tuple(bot[:3])}')
        check(left[0] > fill[0], '左边提亮', f'left={tuple(left[:3])}')
        check(right[0] < fill[0], '右边压暗', f'right={tuple(right[:3])}')
        center = surf.get_at((60, 60))
        check(tuple(center[:3]) == fill, '面心保持原色（只有窄带变）',
              f'center={tuple(center[:3])}')

        # ---------- 3 三形态行为（关态零调用 / 开关像素差）----------
        print('\n--- 3 三形态：关态一致 / 开态生效 ---')
        run_form('方形', 'new_puzzle', (6, 6, 2), 'draw_board')
        run_form('三角', 'new_triangle_puzzle', (5, 2), 'draw_triangle_board')
        run_form('米字', 'new_mi_puzzle', (4, 4, 2), 'draw_mi_board')

        # ---------- 4 AA 路径与直出路径同一 helper ----------
        print('\n--- 4 AA 路径 ---')
        gui = boot('new_triangle_puzzle', 5, 2)
        poly = [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0)]
        _calls.clear()
        gui._draw_aa_polygon(poly, (100, 140, 190), (0, 0, 0), 2, bevel=False)
        check(len(_calls) == 0, 'AA bevel=False 不走倒角')
        _calls.clear()
        gui._draw_aa_polygon(poly, (100, 140, 190), (0, 0, 0), 2, bevel=True)
        check(len(_calls) > 0, 'AA bevel=True 走同一 helper')

        # ---------- 5 设置页开关 + 一键切换接线 ----------
        print('\n--- 5 设置页开关 / 一键切换 ---')
        gui = boot('new_puzzle', 6, 6, 2)
        gui.show_settings_dialog = True
        gui.settings_active_tab = 'animation'
        gui.draw_settings_dialog()
        rect = getattr(gui, '_settings_bevel_toggle_rect', None)
        check(rect is not None and rect.w > 0, '设置页画出「立体光效」开关')
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                pos=rect.center)
        before = gui.face_bevel_enabled
        gui._handle_settings_dialog_event(ev)
        check(gui.face_bevel_enabled != before, '设置页点击翻转生效',
              f'{before} -> {gui.face_bevel_enabled}')
        # Ctrl+K 一键切换（toggle action 同一支）
        gui._handle_right_panel_switch('face_bevel_enabled')
        check(gui.face_bevel_enabled == before, '一键切换同支翻转回来',
              f'-> {gui.face_bevel_enabled}')

        # ---------- 6 config.json 存取 roundtrip ----------
        print('\n--- 6 config 存取 roundtrip ---')
        tmp = tempfile.mkdtemp(prefix='s62_')
        gui = boot('new_puzzle', 6, 6, 2)
        gui.config_dir = tmp
        gui.config_path = os.path.join(tmp, 'config.json')
        gui.temp_history_path = os.path.join(tmp, 'temp_history.json')
        gui.face_bevel_enabled = False
        gui.save_config()
        with open(gui.config_path, encoding='utf-8') as f:
            cfg = json.load(f)
        check(cfg.get('face_bevel_enabled') is False, 'save 落盘 False',
              str(cfg.get('face_bevel_enabled')))
        # 载入侧：另起实例读回
        gui2 = boot('new_puzzle', 6, 6, 2)
        gui2.config_dir = tmp
        gui2.config_path = gui.config_path
        gui2.temp_history_path = gui.temp_history_path
        gui2.face_bevel_enabled = True
        gui2.load_last_state()
        check(gui2.face_bevel_enabled is False, 'load 读回 False')
    finally:
        renderer_mod._draw_face_bevel = _orig_bevel
        pygame.quit()


if __name__ == '__main__':
    pygame.init()
    run()
    total = PASSED + FAILED
    print(f'\n{PASSED}/{total} passed' + (f', {FAILED} FAILED' if FAILED else ' — ALL PASS'))
    sys.exit(1 if FAILED else 0)
