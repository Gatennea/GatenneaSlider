# -*- coding: utf-8 -*-
"""设置-视觉页 + 求解器顺序 + 聚拢参数注记 无头测试。

背景（2026-10-13 用户实机反馈三连）：
  1. 设置第三个 tab 改名「视觉」，加「缩放」滑条，与右侧面板缩放滑条联动；
  2. 「悬停连锁提示」没有解释、「标记」不在这一页 —— 真因是
     _calc_settings_content_height 把视觉页写死 340，真实内容 660+，
     滚动上限只有 22px，下面的行整块被裁在可见区外（代码里有解释，
     玩家看不到 = Bug）。本测试锁死「高度计算 ≥ 实际绘制高度」且
     「滚到底后每个控件都必须落在内容裁剪区内」；
  3. 求解器顺序重排（混合置顶 / 旧三项沉底）、「聚拢」更名「单次聚拢」、
     聚拢参数页标明只给聚拢求解器用。

执行：``D:/python/python.exe -u test/_test_visual_tab.py``
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from solver import SOLVER_ALGORITHMS  # noqa: E402
from gui.feature_index import place_text, FEATURES, _ACTIONS  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


# ---------------------------------------------------------------- 基础设施
gui = SliderGUI(m=4, n=4, step=2, cmd_queue=None) if False else None
import queue  # noqa: E402
gui = SliderGUI(m=4, n=4, step=2, cmd_queue=queue.Queue())
gui.tut_show_prompt = False
gui.tutorial_active = False

# 设置框几何（renderer.draw_settings_dialog 内同构）
DIALOG_H = 480
dialog_y = (gui.screen_height - DIALOG_H) // 2
CONTENT_Y = dialog_y + 58 + 30 + 10          # tab_y + tab_height + 10
CONTENT_H = DIALOG_H - (CONTENT_Y - dialog_y) - 64


def open_settings(tab):
    gui.show_settings_dialog = True
    gui.settings_active_tab = tab
    gui.settings_editing_action = None
    gui.settings_editing_value = None
    gui._settings_backup_keybindings = dict(gui.keybindings)
    gui.draw_settings_dialog()


def click_at(pos):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    gui.handle_events()


def scroll_to_bottom():
    gui.settings_scrollbar.set_scroll(10 ** 6)   # set_scroll 内部夹紧
    gui.draw_settings_dialog()


# ================================================================ 视觉页
print("\n--- 视觉页：tab 改名与控件齐全 ---")
_rnd = open(os.path.join('gui', 'renderer.py'), encoding='utf-8').read()
check('V0a 第三个 tab 标签为「视觉」',
      'tab_anim_text = self.status_font.render("视觉"' in _rnd)
# 「视觉」入口 = 顶栏「设置」→ 对话框 → 视觉 Tab（历史上的「设置」下拉菜单
# 是死机制，已删；这里锁现行路径：点「设置」直接开对话框，不开下拉）。
check('V0b 顶栏「设置」点击直达设置对话框', '设置' in gui.menu_items,
      str(gui.menu_items))

open_settings('animation')
_tab_row_attrs = {
    '界面模式': '_settings_ui_mode_rect',
    '滑动动画': '_settings_anim_toggle_rect',
    '选中动画': '_settings_sel_anim_toggle_rect',
    '动画时长': '_settings_slider_track_rect',
    '缩放': '_settings_zoom_track_rect',
    '分组着色': '_settings_coloring_toggle_rect',
    '悬停连锁提示': '_settings_chain_toggle_rect',
    '复原提示标记': '_settings_marks_toggle_rect',
    '调试面板': '_settings_metrics_toggle_rect',
}
check('V1a 缩放滑条 rect 已绘制',
      hasattr(gui, '_settings_zoom_track_rect')
      and hasattr(gui, '_settings_zoom_knob_rect'))
check('V1b 缩放滑条与动画时长滑条同栏对齐（x 相同）',
      gui._settings_zoom_track_rect.x == gui._settings_slider_track_rect.x,
      f"{gui._settings_zoom_track_rect.x} vs {gui._settings_slider_track_rect.x}")

# tab 顺序：快捷键 < 控制 < 视觉 < 求解器 < 聚拢参数 < 文件
_tabs = [gui._settings_tab_kb_rect, gui._settings_tab_control_rect,
         gui._settings_tab_anim_rect, gui._settings_tab_solver_rect,
         gui._settings_tab_gather_rect, gui._settings_tab_file_rect]
check('V0c 视觉页排在第三个 tab',
      _tabs[0].x < _tabs[1].x < _tabs[2].x < _tabs[3].x < _tabs[4].x < _tabs[5].x,
      str([r.x for r in _tabs]))

# 「标记」已更名并入本页（用户：标记也应该加入这里，名为复原提示标记）
check('V1c 标记行更名「复原提示标记」', '复原提示标记：' in _rnd
      and '"棋盘标记："' not in _rnd)
check('V1d 右下角 compact 标签同步为「复原标记」',
      "_sw_btn('board_marks_enabled', '复原标记'" in _rnd)
# 「悬停连锁提示」的解释必须在代码里（用户：若发现解释存在 → 是可见性 Bug）
check('V1e 悬停连锁提示有解释文案',
      '悬停滑块时，边界盒内同组位置（含空格）提亮提示' in _rnd)

print("\n--- 视觉页：内容高度 vs 实际绘制（防裁切回归）---")
drawn_h = getattr(gui, '_settings_anim_height', 0)
calc_h = gui._calc_settings_content_height(CONTENT_H)
check('V2a 高度计算 ≥ 实际绘制高度', calc_h >= drawn_h - 1,
      f"calc={calc_h} drawn={drawn_h}")
check('V2b 内容确实超出可见区（需要滚动）', drawn_h > CONTENT_H,
      f"drawn={drawn_h} visible={CONTENT_H}")

scroll_to_bottom()
# rect 必须**滚动之后**取：draw 每次都会新建 Rect，滚动前捕获到的是
# 上一帧（scroll=0）的对象，拿旧对象断言可见性会永远失败。
_rows = {name: getattr(gui, attr) for name, attr in _tab_row_attrs.items()}
max_scroll = gui.settings_scrollbar.scroll   # set_scroll(10**6) 已夹紧
print(f"  scroll={max_scroll} content=[{CONTENT_Y},{CONTENT_Y + CONTENT_H}]")
check('V2c 滚动上限 = 内容高 - 可见高（底部能被拉到可见区）',
      max_scroll == drawn_h - CONTENT_H, f"{max_scroll} vs {drawn_h - CONTENT_H}")
# 滚到底时最后一行必须完整可见（旧 bug 的症状正是它连影子都看不到）
_last = _rows['调试面板']
check('V2d 滚到底时末行（调试面板）完整可见',
      _last.bottom <= CONTENT_Y + CONTENT_H,
      f"bottom={_last.bottom} limit={CONTENT_Y + CONTENT_H}")
# 每个控件都「可达」：存在某个滚动位置使它至少部分落在内容裁剪区内。
# （不能要求 9 行同时可见——内容本来就比可见区高，同时可见是不可能的。）
bad = []
for name, r in _rows.items():
    y0 = r.y + max_scroll               # 该行在 scroll=0 时的 y
    s_star = max(0, min(max_scroll, y0 - CONTENT_Y))  # 能把该行拉到顶部的滚动量
    top = y0 - s_star
    if not (top + r.height > CONTENT_Y and top < CONTENT_Y + CONTENT_H):
        bad.append(f'{name}:y={top}~{top + r.height}')
check('V2e 9 个控件全部可达（存在可见的滚动位置）', not bad, '; '.join(bad))
# 悬停连锁提示的说明画在开关行下方 38px：行完整可见 ⇒ 说明必然在可见区内
check('V2f 连锁提示行完整可见（说明不再被裁）',
      _rows['悬停连锁提示'].bottom <= CONTENT_Y + CONTENT_H
      and _rows['悬停连锁提示'].top >= CONTENT_Y,
      f"y={_rows['悬停连锁提示'].y}~{_rows['悬停连锁提示'].bottom} "
      f"limit={CONTENT_Y + CONTENT_H}")

print("\n--- 视觉页：缩放滑条拖拽（与速度条同一套逻辑）---")
gui.zoom = 1.0
ztr = gui._settings_zoom_track_rect
click_at(ztr.center)                     # 点轨道中点 → 约一半量程
mid = 0.1 + 0.5 * (gui.max_zoom - gui.min_zoom)
check('V3a 点轨道中点 → 缩放约 50% 量程', abs(gui.zoom - mid) < 0.02,
      f"zoom={gui.zoom:.3f} expect≈{mid:.3f}")
# 夹紧语义在拖动中生效：按住后把鼠标移到轨道两端之外
pygame.event.post(pygame.event.Event(
    pygame.MOUSEMOTION, pos=(ztr.right + 50, ztr.centery)))
gui.handle_events()
check('V3b 按住拖到右端之外 → 夹紧 max_zoom', gui.zoom == gui.max_zoom,
      f"zoom={gui.zoom}")
pygame.event.post(pygame.event.Event(
    pygame.MOUSEMOTION, pos=(ztr.x - 50, ztr.centery)))
gui.handle_events()
check('V3c 按住拖到左端之外 → 夹紧 min_zoom', gui.zoom == gui.min_zoom,
      f"zoom={gui.zoom}")
# 拖动事件（按下后移动）
click_at(ztr.center)
pygame.event.post(pygame.event.Event(
    pygame.MOUSEMOTION, pos=(ztr.right, ztr.centery)))
gui.handle_events()
check('V3d 按住拖动 → 连续更新到 max', gui.zoom == gui.max_zoom, f"zoom={gui.zoom}")
pygame.event.post(pygame.event.Event(
    pygame.MOUSEBUTTONUP, button=1, pos=(ztr.right, ztr.centery)))
gui.handle_events()
check('V3e 松手停止拖拽', getattr(gui, '_settings_zoom_dragging', True) is False)

print("\n--- 视觉页：缩放与右侧面板滑条联动（同一 self.zoom）---")
# 设置页拖到最大后重画 → 旋钮应贴在轨道右端
gui.draw_settings_dialog()
check('V4a 设置页旋钮跟随共享 zoom（贴右端）',
      abs(gui._settings_zoom_knob_rect.centerx - ztr.right) <= 2,
      f"knob={gui._settings_zoom_knob_rect.centerx} track_right={ztr.right}")
# 模拟右侧面板入口改缩放（共享锚点函数）→ 设置页旋钮应跟着回到左端
cam_before = (gui.camera_x, gui.camera_y)
gui._apply_zoom_centered(gui.min_zoom)
gui.draw_settings_dialog()
check('V4b 外部入口改 zoom → 设置页旋钮跟随（贴左端）',
      abs(gui._settings_zoom_knob_rect.centerx - ztr.x) <= 2,
      f"knob={gui._settings_zoom_knob_rect.centerx} track_left={ztr.x}")
# 锚点语义：窗口中心对应的棋盘坐标不变
cx, cy = gui.screen_width // 2, gui.menu_bar_height + (
    gui.screen_height - gui.menu_bar_height - gui.status_bar_height) // 2
wx = (cx - cam_before[0]) / gui.max_zoom
wy = (cy - cam_before[1]) / gui.max_zoom
check('V4c 锚点为窗口中心（改缩放不跳画面）',
      abs((cx - gui.camera_x) / gui.zoom - wx) < 1e-6
      and abs((cy - gui.camera_y) / gui.zoom - wy) < 1e-6)

# 右侧面板滑条入口（重构后委托 _apply_zoom_centered）仍可用
gui.zoom_slider_rect = pygame.Rect(0, 100, 20, 200)
gui._update_zoom_slider_from_mouse(100)   # 顶部 = 放大
check('V4d 右侧面板滑条：顶部=max', gui.zoom == gui.max_zoom, f"zoom={gui.zoom}")
gui._update_zoom_slider_from_mouse(300)   # 底部 = 缩小
check('V4e 右侧面板滑条：底部=min', gui.zoom == gui.min_zoom, f"zoom={gui.zoom}")
gui.zoom = 1.0

print("\n--- 视觉页：复原提示标记开关点击 ---")
open_settings('animation')
scroll_to_bottom()
click_at(gui._settings_marks_toggle_rect.center)
check('V5a 点标记行 → 通知用新名字',
      '复原提示标记' in (gui.macro_notify_msg or ''),
      repr(gui.macro_notify_msg))

# ================================================================ 求解器页
print("\n--- 求解器：顺序重排 + 单次聚拢更名 ---")
expect_order = ['hybrid', 'gather_gradient', 'gap_macro', 'gather',
                'pick_fill', 'table', 'ida_star', 'fast', 'greedy']
check('S1a 注册表顺序 = 混合/梯度/填坑/单次聚拢/选块/查表/旧三项',
      list(SOLVER_ALGORITHMS) == expect_order, str(list(SOLVER_ALGORITHMS)))
check('S1b 「聚拢」更名「单次聚拢」',
      SOLVER_ALGORITHMS['gather'][0].strip() == '单次聚拢',
      SOLVER_ALGORITHMS['gather'][0])
check('S1c 混合求解置顶', list(SOLVER_ALGORITHMS)[0] == 'hybrid')
check('S1d 旧搜索三项沉底（且注明低效备查）',
      list(SOLVER_ALGORITHMS)[-3:] == ['ida_star', 'fast', 'greedy']
      and '备查' in gui._solver_description('ida_star')
      and '备查' in gui._solver_description('fast')
      and '备查' in gui._solver_description('greedy'))

open_settings('solver')
check('S2a 求解器页按同一顺序绘制',
      list(gui._settings_solver_rects) == expect_order,
      str(list(gui._settings_solver_rects)))
check('S2b 单次聚拢说明已更新',
      '单次聚拢（方形' in gui._solver_description('gather'))

# ================================================================ 聚拢参数页
print("\n--- 聚拢参数：标明只给聚拢求解器用 ---")
open_settings('gather')
check('G1a 参数页有适用范围注记',
      '这些参数只给「单次聚拢」用' in _rnd)
_gcalc = gui._calc_settings_content_height(CONTENT_H)
_gdrawn = 26 + 22 + len(gui._gather_param_specs) * 52 + 10
check('G1b 参数页高度跟上新增注记行', _gcalc >= _gdrawn - 1,
      f"calc={_gcalc} drawn={_gdrawn}")

# ================================================================ 功能索引
print("\n--- 功能可发现性索引同步 ---")
check('F1a 索引里视觉页改名', place_text(('settings', 'animation')) == '设置 → 视觉页',
      place_text(('settings', 'animation')))
_by_id = {f['id']: f for f in FEATURES}
check('F1b 单次聚拢条目更名', _by_id['algo_gather']['name'] == '单次聚拢（求解算法）'
      and '选「单次聚拢」' in _by_id['algo_gather']['howto'])
check('F1c 复原提示标记条目更名', _by_id['board_marks_enabled']['name'] == '复原提示标记'
      and '视觉页' in _by_id['board_marks_enabled']['howto'])
check('F1d 新增缩放条目（可被命令面板搜到）',
      'zoom' in _by_id and _ACTIONS.get('zoom', {}).get('tab') == 'animation'
      and '联动' in _by_id['zoom']['howto'])

print("\n=== 结果 ===")
print("PASS" if not _failures else f"FAIL: {_failures}")
sys.exit(1 if _failures else 0)
