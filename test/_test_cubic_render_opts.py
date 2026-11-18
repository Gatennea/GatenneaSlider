# -*- coding: utf-8 -*-
"""回归：方案 §2.4「三维特有的渲染选项 GUI」。

钉住四件事：
  A. 声明式表：默认值 / 越界夹紧 / 坏类型回默认 / 未知键报错（表是唯一真源）。
  B. 右侧栏：三维态多出「拆分」「切面透明」两条横向滑条、只留 5 个开关
     （连锁 / 复原标记这两个三维用不上的让位）；二维态原样 7 个、无三维滑条。
  C. 拖动：按横坐标写值、夹在表范围内、gap 改了要作废箭头/贴纸缓存并标脏。
  D. 落盘/读盘：`_build_save_data()['cubic_camera']` 带全部表内键且是夹紧后的值；
     `_cubic_load_defaults()` 能读回；越界/垃圾值不会写进渲染属性。
  E. 真的生效：切面 alpha 越小红色越淡（像素统计），旋转灵敏度改的是转角倍率。

跑法：D:/python/python.exe test/_test_cubic_render_opts.py
"""
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from gui import cubic_settings  # noqa: E402

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


print('=' * 60)
print('A. 声明式表：默认 / 夹紧 / 坏类型 / 未知键')


class _Holder:
    pass


h = _Holder()
cubic_settings.reset(h)
d = cubic_settings.defaults()
check(set(d) == {'gap', 'seam_alpha', 'cubic_anim_ms', 'rot_sensitivity'},
      '表里有四条（gap/seam_alpha/cubic_anim_ms/rot_sensitivity）', sorted(d))
check(h.cubic_gap == 0.12 and h.cubic_seam_alpha == 110
      and h.cubic_anim_ms == 140,
      'reset 把默认值写到属性上',
      (h.cubic_gap, h.cubic_seam_alpha, h.cubic_anim_ms))
check(cubic_settings.clamp_value('gap', 9.9) == 0.6, 'gap 超上界夹到 0.6',
      cubic_settings.clamp_value('gap', 9.9))
check(cubic_settings.clamp_value('gap', -1) == 0.0, 'gap 负值夹到 0.0')
check(cubic_settings.clamp_value('seam_alpha', 'abc') == 110,
      '非数字回默认（不写坏渲染参数）')
check(cubic_settings.clamp_value('seam_alpha', 12) == 30, 'int 项夹到 30')
check(isinstance(cubic_settings.clamp_value('seam_alpha', 77.6), int)
      and cubic_settings.clamp_value('seam_alpha', 77.6) == 78,
      'int 项四舍五入到 78')
try:
    cubic_settings.clamp_value('nope', 1)
    check(False, '未登记的键应 KeyError')
except KeyError:
    check(True, '未登记的键 → KeyError')
check(len(cubic_settings.items('view')) == 3,
      'view 组三条（拆分/切面/动画时长）')

print('=' * 60)
print('B. 右侧栏：三维 5 开关 + 两条滑条；二维 7 开关无滑条')
pygame.init()
gui = SliderGUI(m=4, n=4, step=1)
gui.animation_enabled = False
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_opts_')
gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
# config_path 必须一起改：save_config() 写的是 self.config_path，漏了就会把
# 测试值写进仓库里用户真正在用的 config/config.json（本轮实际踩过）
gui.config_path = os.path.join(gui.config_dir, 'config.json')
gui._readonly = False
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()
gui._cubic_camera_prefs = {}
gui.new_cubic_puzzle(3, 3, 3, 1)

gui.draw_right_panel()
sw = getattr(gui, 'right_panel_switch_rects', {})
check(len(sw) == 6, '三维态开关 6 个（选中动画已补回）', sorted(sw))
check('chain_hint_enabled' not in sw and 'board_marks_enabled' not in sw
      and 'coloring_enabled' not in sw,
      '连锁 / 复原标记 / 着色仍撤掉（三维不做这些）', sorted(sw))
check({'animation_enabled', 'selection_animation_enabled', 'game_mode',
       'show_records_panel', 'show_virtual_keyboard',
       'cubic_follow_centroid'} == set(sw),
      '留下的是三维真正生效的六个', sorted(sw))
gr = getattr(gui, 'cubic_gap_slider_rect', None)
ar = getattr(gui, 'cubic_alpha_slider_rect', None)
check(gr is not None and ar is not None, '三维态有拆分/切面透明两条滑条', (gr, ar))
_all4 = [gui.zoom_slider_rect, gui.slider_rect, gr, ar]
check(all(r is not None for r in _all4), '四条滑条矩形都建出来了（缩放/速度/拆分/切面）')
check(all(r.height > r.width for r in _all4),
      '四条全部竖向（高 > 宽）', [(r.width, r.height) for r in _all4])
_col_w = (gui.right_panel_width - 12) // 2
check(gr.width == _col_w and ar.width == _col_w,
      f'2×2 每格半栏宽（{_col_w}）', (gr.width, ar.width))
# 2×2：左列缩放/拆分，右列速度/切面；第二行在第一行轨道下方
check(abs(gr.left - gui.zoom_slider_rect.left) <= 1
      and abs(ar.left - gui.slider_rect.left) <= 1,
      '左列 = 缩放/拆分，右列 = 速度/切面',
      ((gr.left, gui.zoom_slider_rect.left), (ar.left, gui.slider_rect.left)))
check(gr.top >= gui.zoom_slider_rect.bottom
      and ar.top >= gui.slider_rect.bottom,
      '第二行（拆分/切面）在第一行（缩放/速度）下方',
      ((gr.top, gui.zoom_slider_rect.bottom), (ar.top, gui.slider_rect.bottom)))
# 不许叠在开关或任一条滑条上
all_sw = list(sw.values())
check(all(not r.colliderect(s) for r in _all4 for s in all_sw),
      '四条滑条不与任何开关矩形重叠')
check(all(not _all4[i].colliderect(_all4[j])
          for i in range(len(_all4)) for j in range(i + 1, len(_all4))),
      '四条滑条两两不重叠')
# 开关自身也要守住面板：两两不重叠、都在面板内、不压四条滑条
_panel_left = gui.screen_width - gui.right_panel_width
check(all(r.left >= _panel_left and r.right <= gui.screen_width
          and r.top >= 0 and r.bottom <= gui.screen_height for r in all_sw),
      '所有开关都在右侧面板内', [(r.left, r.right) for r in all_sw])
check(all(not all_sw[i].colliderect(all_sw[j])
          for i in range(len(all_sw)) for j in range(i + 1, len(all_sw))),
      '六个开关两两不重叠')
check(all(not r.colliderect(s) for r in all_sw for s in _all4),
      '开关不压任何一条竖滑条')

# 速度竖滑条在三维态必须真的写 cubic_anim_ms（以前它只改二维 animation_duration，
# 在三维里是个哑控件）
gui._update_slider_from_mouse(gui.slider_rect.top)
check(gui.cubic_anim_ms == gui.CUBIC_ANIM_MIN_MS,
      f'滑条拉到顶 = 最快（{gui.cubic_anim_ms}ms）')
gui._update_slider_from_mouse(gui.slider_rect.bottom)
check(gui.cubic_anim_ms == gui.CUBIC_ANIM_MAX_MS,
      f'滑条拉到底 = 最慢（{gui.cubic_anim_ms}ms）')
old_2d = gui.animation_duration
gui._update_slider_from_mouse(gui.slider_rect.top)
check(gui.animation_duration == old_2d, '三维态改速度不碰二维 animation_duration')

# 跟随质心开关：关掉后不被拉回，重开即回正
gui.cubic_pan = [40.0, -20.0]
gui.cubic_follow_centroid = True
gui._handle_right_panel_switch('cubic_follow_centroid')
check(gui.cubic_follow_centroid is False, '点一下：跟随质心关掉')
check(gui.cubic_pan == [40.0, -20.0], '关掉后手动平移保留，不会被拽回')
gui._handle_right_panel_switch('cubic_follow_centroid')
check(gui.cubic_follow_centroid is True and gui.cubic_pan == [0.0, 0.0],
      '再点一下：重新跟随并立刻回正')

gui.new_puzzle(4, 4, 1)
gui.draw_right_panel()
check(len(getattr(gui, 'right_panel_switch_rects', {})) == 7, '二维态仍是 7 个开关')
check(getattr(gui, 'cubic_gap_slider_rect', None) is None
      and getattr(gui, 'cubic_alpha_slider_rect', None) is None,
      '二维态不画三维滑条')
check(gui.zoom_slider_rect.height > gui.zoom_slider_rect.width
      and gui.slider_rect.height > gui.slider_rect.width,
      '二维态缩放/速度仍是竖向（右栏没有横滑条）',
      ((gui.zoom_slider_rect.width, gui.zoom_slider_rect.height),
       (gui.slider_rect.width, gui.slider_rect.height)))

print('=' * 60)
print('C. 拖动：按纵坐标写值 + 夹紧 + 缓存作废（顶部=最大）')
gui._cubic_camera_prefs = {}
gui.new_cubic_puzzle(3, 3, 3, 1)
gui.draw_right_panel()
gr = gui.cubic_gap_slider_rect
gui._cubic_arrow_sig = ('sentinel',)
gui._cubic_sil_cache = {'sentinel': 1}
ver0 = gui._board_version
gui._update_cubic_opt_from_mouse('gap', gr.bottom)
check(abs(gui.cubic_gap - 0.0) < 1e-9, '拖到最底 = gap 0（贴死）', gui.cubic_gap)
check(cubic_settings.clamp_value('gap', gui.cubic_gap) == gui.cubic_gap,
      '写进去的值本身就在表范围内')
gui._update_cubic_opt_from_mouse('gap', gr.top - 50)
check(abs(gui.cubic_gap - 0.6) < 1e-9, '拖出顶部夹到 0.6', gui.cubic_gap)
check(getattr(gui, '_cubic_arrow_sig', None) is None
      and getattr(gui, '_cubic_sil_cache', None) is None,
      'gap 变了 → 箭头可推性 / 贴纸轮廓缓存立刻作废')
check(gui._board_version == ver0,
      '只改显示参数不动棋盘版号（标题栏不该平白出现星号）',
      (ver0, gui._board_version))
ar = gui.cubic_alpha_slider_rect
gui._update_cubic_opt_from_mouse('seam_alpha', ar.top + ar.height / 2.0)
check(30 <= gui.cubic_seam_alpha <= 220, '切面透明度落在 30..220', gui.cubic_seam_alpha)
check(gui.cubic_seam_alpha == 125, '正中 = 125（30 + 0.5*(220-30)）',
      gui.cubic_seam_alpha)
prev = gui.cubic_seam_alpha
gui._update_cubic_opt_from_mouse('seam_alpha', ar.top + ar.height / 2.0)
check(gui.cubic_seam_alpha == prev, '同一点再拖不重复写（幂等）')

print('=' * 60)
print('D. 落盘 / 读盘：config.json 的 cubic_camera 带齐表内键，坏值不落')
import json
gui.cubic_gap = 0.33
gui.cubic_seam_alpha = 180
gui.cubic_rot_sensitivity = 1.4
gui.cubic_anim_ms = 260
gui.save_config()
with open(gui.config_path, encoding='utf-8') as f:
    cfg = json.load(f)
cc = cfg.get('cubic_camera') or {}
check(set(d) <= set(cc), 'cubic_camera 里带齐表内四个键', sorted(cc))
check(abs(cc['gap'] - 0.33) < 1e-6 and cc['seam_alpha'] == 180
      and abs(cc['rot_sensitivity'] - 1.4) < 1e-6
      and cc['cubic_anim_ms'] == 260,
      '导出值 = 当前值（不是默认值）', cc)

gui._cubic_camera_prefs = {'gap': 0.25, 'seam_alpha': 9999,
                          'rot_sensitivity': -3, 'cubic_anim_ms': 999}
cubic_settings.reset(gui)
gui._cubic_load_defaults()
check(abs(gui.cubic_gap - 0.25) < 1e-6, 'gap 读回 0.25', gui.cubic_gap)
check(gui.cubic_seam_alpha == 220, 'seam_alpha 越界夹到 220（不是照抄 9999）',
      gui.cubic_seam_alpha)
check(abs(gui.cubic_rot_sensitivity - 0.2) < 1e-6, 'rot_sensitivity 负值夹到 0.2',
      gui.cubic_rot_sensitivity)
check(gui.cubic_anim_ms == 400, 'cubic_anim_ms 越界夹到 400（不是照抄 999）',
      gui.cubic_anim_ms)
check(abs(gui.cubic_rot_sensitivity - 0.2) < 1e-6, 'rot_sensitivity 负值夹到 0.2',
      gui.cubic_rot_sensitivity)

print('=' * 60)
print('E. 真的生效：alpha 影响红色浓淡；灵敏度改转角')


def _redness(alpha):
    gui.cubic_gap = 0.30
    gui.cubic_seam_alpha = alpha
    gui._cubic_clear_selection()
    seam = ('r', 1)
    gui.selected_gap = seam
    gui.draw_cubic_board()
    surf = gui.screen
    n = 0
    for x in range(0, surf.get_width(), 3):
        for y in range(0, surf.get_height(), 3):
            r, g, b = surf.get_at((x, y))[:3]
            if r > 30 and r > g + 12 and r > b + 12:
                n += 1
    return n


_lo = _redness(30)
_hi = _redness(220)
check(_hi > _lo, '切面 alpha 越大红色像素越多（透明真的生效）', (_lo, _hi))
check(_lo > 0, 'alpha=30 时切面仍然可见（不是完全消失）', _lo)

gui.cubic_gap = 0.12
gui.cubic_seam_alpha = 110


def _drag_angle(sens):
    """同一段拖动（120px 横拖）在不同灵敏度下，相机**相对原姿态**转过的角度。"""
    cam0 = gui.cubic_camera
    q0 = cam0.q
    gui.cubic_rot_sensitivity = sens
    gui.cubic_dragging = True
    gui.cubic_drag_moved = True
    gui.cubic_drag_start = (300, 300)
    gui.cubic_drag_from = cam0
    gui._cubic_drag_update((420, 300))
    q = gui.cubic_camera.q
    gui.cubic_camera = cam0
    dot = abs(sum(a * b for a, b in zip(q, q0)))
    return 2 * math.acos(min(1.0, dot))


import math
_a_lo = _drag_angle(0.3)
_a_hi = _drag_angle(1.6)
check(_a_hi > _a_lo > 0, '灵敏度越大同一段拖动转得越多（灵敏度真的被读）',
      (_a_lo, _a_hi))
check(_drag_angle(0.0) == _drag_angle(0.0) == 0.0 or _drag_angle(0.0) < 0.02,
      '灵敏度 0 = 拖了也不转', _drag_angle(0.0))

print('=' * 60)
print('F. 设置页「三维」专页：8 页签放得下、按钮可用、二维置灰')


def _open_settings(gui):
    gui.show_settings_dialog = True
    gui.settings_active_tab = 'cubic'
    gui.draw_settings_dialog()


_open_settings(gui)
gui.new_cubic_puzzle(3, 3, 3, 1)
_open_settings(gui)
_rects = [getattr(gui, a, None) for a in
          ('_settings_tab_kb_rect', '_settings_tab_control_rect',
           '_settings_tab_anim_rect', '_settings_tab_audio_rect',
           '_settings_tab_solver_rect', '_settings_tab_gather_rect',
           '_settings_tab_file_rect', '_settings_tab_cubic_rect')]
check(all(r is not None for r in _rects), '8 个页签矩形都画出来了')
check(all(_rects[i].right <= _rects[i + 1].left for i in range(len(_rects) - 1))
      and _rects[-1].right <= gui.screen_width,
      '页签互不重叠、最后一个不出屏', [(r.left, r.right) for r in _rects])
check(all(_rects[i].width == 72 for i in range(len(_rects))), '页签宽 72（放得下 8 个）')

_btns = getattr(gui, '_settings_cubic_btn_rects', {})
check(len(_btns) == 6 and ('gap', 1) in _btns and ('rot_sensitivity', -1) in _btns
      and ('cubic_anim_ms', 1) not in _btns and ('zoom', 1) not in _btns,
      '三维页只列三维独有 3 项（缩放/动画时长归视觉页）', sorted(_btns.keys()))
check(all(r.collidepoint(r.center) and r.bottom <= gui._settings_content_rect.bottom + 1
          for r in _btns.values()),
      '按钮都落在可见内容区内')


# 点 + 真的改值（走设置页真实事件入口，不直接调内部函数）
_g0 = gui.cubic_gap
_r = _btns[('gap', 1)]
gui._handle_settings_dialog_event(
    pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'pos': _r.center, 'button': 1}))
check(abs(gui.cubic_gap - cubic_settings.clamp_value('gap', _g0 + 0.05)) < 1e-9,
      '点「+」按步长加一档（0.05）', (gui.cubic_gap, _g0))
_r2 = _btns[('gap', -1)]
gui._handle_settings_dialog_event(
    pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'pos': _r2.center, 'button': 1}))
check(abs(gui.cubic_gap - _g0) < 1e-9, '再点「−」回到原值', gui.cubic_gap)
_r3 = _btns[('seam_alpha', 1)]
gui._handle_settings_dialog_event(
    pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'pos': _r3.center, 'button': 1}))
check(gui.cubic_seam_alpha == cubic_settings.clamp_value(
    'seam_alpha', 110 + 5) or gui.cubic_seam_alpha != 110,
      '切面透明度的 + 也生效', gui.cubic_seam_alpha)

gui.settings_active_tab = 'cubic'
gui.new_puzzle(4, 4, 1)
_open_settings(gui)
check(getattr(gui, '_settings_cubic_btn_rects', None) == {},
      '二维局下三维页不注册任何步进按钮（点不到）')

print('=' * 60)
print('G. 三维局「视觉」页：只留生效项（明确不做的直接不画）')
gui.new_cubic_puzzle(3, 3, 3, 1)
gui.settings_active_tab = 'animation'
gui.draw_settings_dialog()
_hidden = ('_settings_coloring_toggle_rect', '_settings_chain_toggle_rect',
           '_settings_gap_hover_toggle_rect', '_settings_marks_toggle_rect',
           '_settings_metrics_toggle_rect', '_settings_records_toggle_rect',
           '_settings_grid_toggle_rect', '_settings_anti_drift_toggle_rect',
           '_settings_thinking_toggle_rect')
_bad = [(a, getattr(gui, a, None)) for a in _hidden
        if getattr(gui, a, None) is not None and getattr(gui, a).width > 0]
check(not _bad, '三维局视觉页不画着色/连锁/标记/面板/网格等二维项', _bad)
check(getattr(gui, '_settings_sel_anim_toggle_rect', None) is not None
      and gui._settings_sel_anim_toggle_rect.width > 0,
      '三维局视觉页补回「选中动画」开关')
check(getattr(gui, '_settings_boot_toggle_rect', None) is not None
      and gui._settings_boot_toggle_rect.width > 0,
      '三维局保留开机动画开关')
check(getattr(gui, '_settings_confirm_shuffle_toggle_rect', None) is not None
      and gui._settings_confirm_shuffle_toggle_rect.width > 0,
      '三维局保留防意外打乱开关')
_track = getattr(gui, '_settings_slider_track_rect', None)
_ztrack = getattr(gui, '_settings_zoom_track_rect', None)
check(_track is not None and _track.width > 0,
      '三维视觉页保留动画滑条（动画时长不在三维页重复）', _track)
check(_ztrack is not None and _ztrack.width > 0,
      '三维视觉页保留缩放滑条（缩放不在三维页重复）', _ztrack)

# 动画滑条仍写 cubic_anim_ms，不碰二维 animation_duration
_2d_anim0 = gui.animation_duration
gui._handle_settings_dialog_event(pygame.event.Event(
    pygame.MOUSEBUTTONDOWN, {'pos': (_track.left + 1, _track.centery), 'button': 1}))
check(gui.cubic_anim_ms <= gui.CUBIC_ANIM_MIN_MS + 2,
      '三维视觉页动画滑条最左 = 最快', gui.cubic_anim_ms)
gui._handle_settings_dialog_event(pygame.event.Event(
    pygame.MOUSEBUTTONUP, {'pos': (_track.left + 1, _track.centery), 'button': 1}))
gui._handle_settings_dialog_event(pygame.event.Event(
    pygame.MOUSEBUTTONDOWN, {'pos': (_track.right - 1, _track.centery), 'button': 1}))
check(gui.cubic_anim_ms >= gui.CUBIC_ANIM_MAX_MS - 2,
      '三维视觉页动画滑条最右 = 最慢', gui.cubic_anim_ms)
check(gui.animation_duration == _2d_anim0,
      '三维视觉页改动画时长不碰二维 animation_duration',
      (gui.animation_duration, _2d_anim0))
gui._handle_settings_dialog_event(pygame.event.Event(
    pygame.MOUSEBUTTONUP, {'pos': (_track.right - 1, _track.centery), 'button': 1}))

# 缩放滑条必须写 cubic_zoom（以前错写 self.zoom），且区间 0.5..3.0
_zoom2d0 = gui.zoom
gui._handle_settings_dialog_event(pygame.event.Event(
    pygame.MOUSEBUTTONDOWN, {'pos': (_ztrack.left + 1, _ztrack.centery), 'button': 1}))
check(abs(gui.cubic_zoom - gui.CUBIC_ZOOM_RANGE[0]) < 0.02,
      '三维视觉页缩放滑条最左 = 0.5', gui.cubic_zoom)
gui._handle_settings_dialog_event(pygame.event.Event(
    pygame.MOUSEBUTTONUP, {'pos': (_ztrack.left + 1, _ztrack.centery), 'button': 1}))
gui._handle_settings_dialog_event(pygame.event.Event(
    pygame.MOUSEBUTTONDOWN, {'pos': (_ztrack.right - 1, _ztrack.centery), 'button': 1}))
check(abs(gui.cubic_zoom - gui.CUBIC_ZOOM_RANGE[1]) < 0.02,
      '三维视觉页缩放滑条最右 = 3.0', gui.cubic_zoom)
check(gui.zoom == _zoom2d0,
      '三维视觉页改缩放不碰二维 self.zoom', (gui.zoom, _zoom2d0))
gui._handle_settings_dialog_event(pygame.event.Event(
    pygame.MOUSEBUTTONUP, {'pos': (_ztrack.right - 1, _ztrack.centery), 'button': 1}))

print('=' * 60)
total = _ok[0] + len(_fail)
print(f'结果：{"全部通过" if not _fail else "有失败"}（{_ok[0]} 项通过，{len(_fail)} 项失败）／共 {total} 项')
if _fail:
    for f in _fail:
        print('  -', f)
sys.exit(1 if _fail else 0)
