"""三维撤销/重做的动画回归（2026-11-18）。

用户口径：「撤销重做时没有动画」；「重新添加选中动画的按钮和功能」。
验收：
- 三维撤销/重做有滑动插值（cubic_anim），不是瞬间换盘；
- 选中动画开：高亮该步滑块组 + 缝（撤销蓝 / 重做橙），且**不改**玩家选中态；
- 选中动画关：只滑、不描边；
- 滑动动画关：连滑动也不做；
- 右侧栏 / 视觉页 / 功能检索都能找到这个开关。
"""
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from gui import feature_index as fi  # noqa: E402

FAILED = []
PASSED = [0]


def check(ok, label, extra=None):
    if ok:
        PASSED[0] += 1
        print(f"  ok: {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL: {label}" + (f"  <- {extra}" if extra is not None else ''))


tmp = tempfile.mkdtemp(prefix='cubic_sel_anim_')
gui = SliderGUI(m=3, n=3, step=1)
gui.config_dir = tmp
gui.config_path = os.path.join(tmp, 'config.json')
gui.temp_history_path = os.path.join(tmp, 'temp.json')
gui.tutorial_active = False
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()
gui.new_cubic_puzzle(3, 3, 3, 1)
gui.animation_enabled = True
gui.cubic_anim_ms = 140
gui.selection_animation_enabled = True

# 造一段「单块从 r0 推到 r1」的历史：局面前后各自 restore，history 记录 move_info。
# 这样测试不依赖方向字母与真实推块判定，只验撤销/重做这条链。
_MOVE = {'gap_type': 'c', 'gap_line': 0, 'direction': 'R', 'step': 1,
         'moved_positions': [[0, 0, 0]]}
_PRE = {'keys': [[0, 0, 0, 0], [2, 0, 0, 0]], 'points_only': True}
_POST = {'keys': [[1, 0, 0, 0], [2, 0, 0, 0]], 'points_only': True}


def arm_history():
    gui.game.restore_state(_PRE)
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    gui.game.restore_state(_POST)
    gui.game_history.save_snapshot(gui.game, _MOVE)


print('A. 撤销：滑动 + 选中高亮都出现')
arm_history()
gui.undo()
check(gui.cubic_anim is not None, '撤销启动了滑动插值', gui.cubic_anim)
check(gui.cubic_anim and gui.cubic_anim.get('ms') == 140,
      '滑动时长取 cubic_anim_ms', gui.cubic_anim)
check(getattr(gui, '_sel_anim_timer', 0) > 0, '撤销打开选中动画计时',
      getattr(gui, '_sel_anim_timer', 0))
check(getattr(gui, '_sel_anim_locs', None) == frozenset({(0, 0, 0)}),
      '高亮的是这一步的滑块（移动前位置）',
      getattr(gui, '_sel_anim_locs', None))
check(getattr(gui, '_sel_anim_gap', None) == ('c', 0),
      '撤销高亮原缝 c0', getattr(gui, '_sel_anim_gap', None))
check(getattr(gui, '_sel_anim_is_undo', None) is True, '撤销用撤销色（蓝）')
check(gui.selected_gap is None and gui.selected_block is None,
      '选中动画不改玩家 selected_gap / selected_block',
      (gui.selected_gap, gui.selected_block))
check(not any(b.be_opted for b in gui.game.blocks),
      '选中动画不写 be_opted（六键不会误推高亮片）')
check(gui._sel_anim_border() is not None, '渲染层能取到轮廓色')

print('B. 重做：高亮移动后位置，缝仍在原处')
gui.redo()
check(gui.cubic_anim is not None, '重做启动了滑动插值')
check(getattr(gui, '_sel_anim_locs', None) == frozenset({(1, 0, 0)}),
      '重做高亮移动后位置', getattr(gui, '_sel_anim_locs', None))
check(getattr(gui, '_sel_anim_gap', None) == ('c', 0),
      '重做高亮原缝 c0（沿缝面内滑动，缝不挪）',
      getattr(gui, '_sel_anim_gap', None))
check(getattr(gui, '_sel_anim_is_undo', None) is False, '重做用重做色（橙）')
# 回归 2026-11-18 的变量遮蔽：描边线宽曾用过 _bw/_bh 这两个名字，把
# smoothscale 的目标宽度覆盖成 6px，整盘被压成一条细线。
gui.cubic_anim['t0'] = pygame.time.get_ticks() - 70
gui.draw_board()
_bg = gui.colors['background']
_xs = []
for _y in range(80, gui.screen_height, 4):
    for _x in range(0, gui.screen_width, 4):
        if gui.screen.get_at((_x, _y))[:3] != _bg:
            _xs.append(_x)
check(bool(_xs) and (max(_xs) - min(_xs)) > 150,
      '动画帧仍是完整盘面（没被压成细线）',
      (min(_xs), max(_xs)) if _xs else None)

print('C. 关「选中动画」：只滑、不描边')
arm_history()
gui.selection_animation_enabled = False
gui._clear_sel_anim()   # 与真实开关关闭同一路径
gui.undo()
check(gui.cubic_anim is not None, '滑动仍发生（滑动动画独立）')
check(getattr(gui, '_sel_anim_timer', 0) == 0, '选中高亮不启动',
      getattr(gui, '_sel_anim_timer', 0))
check(gui._sel_anim_border() is None, '渲染层不描边')

print('D. 关「滑动动画」：撤销/重做即时换盘')
arm_history()
gui.selection_animation_enabled = True
gui.animation_enabled = False
gui.undo()
check(gui.cubic_anim is None, '滑动动画关 → 不插值', gui.cubic_anim)
check(getattr(gui, '_sel_anim_timer', 0) > 0,
      '选中高亮仍按选中动画开关生效', getattr(gui, '_sel_anim_timer', 0))
arm_history()
gui.animation_enabled = True
gui.undo()
check(gui.cubic_anim is not None and getattr(gui, '_sel_anim_locs', None)
      == frozenset({(0, 0, 0)}), '重开滑动动画后恢复插值')

print('E. 开关入口：右侧栏 / 视觉页 / 功能检索')
gui.new_cubic_puzzle(3, 3, 3, 1)
gui.draw_right_panel()
_sw = getattr(gui, 'right_panel_switch_rects', {})
check('selection_animation_enabled' in _sw, '三维右侧栏有「选中动画」', sorted(_sw))
_rect = _sw['selection_animation_enabled']
gui.selection_animation_enabled = True
gui._handle_right_panel_switch('selection_animation_enabled')
check(gui.selection_animation_enabled is False, '点一下变关')
gui._handle_right_panel_switch('selection_animation_enabled')
check(gui.selection_animation_enabled is True, '再点变开')
gui.settings_active_tab = 'animation'
gui.draw_settings_dialog()
check(getattr(gui, '_settings_sel_anim_toggle_rect', None) is not None
      and gui._settings_sel_anim_toggle_rect.width > 0,
      '三维视觉页画出了选中动画开关')
_entry = next(e for e in fi.FEATURES if e['id'] == 'selection_animation_enabled')
check('cubic' in _entry['forms'], '功能检索里三维已登记为可用',
      _entry['forms'])

print('F. 到期清理不拖泥带水')
arm_history()
gui.undo()
gui._sel_anim_timer = 1
gui.update_animation()
check(getattr(gui, '_sel_anim_timer', 0) == 0, '计时归零')
check(not getattr(gui, '_sel_anim_locs', frozenset()), '高亮位置清空')
check(gui.selected_gap is None, '没有误改玩家选中缝', gui.selected_gap)

print('=' * 60)
total = PASSED[0] + len(FAILED)
print(f'结果：{"全部通过" if not FAILED else "有失败"}（{PASSED[0]} 项通过，{len(FAILED)} 项失败）／共 {total} 项')
if FAILED:
    for f in FAILED:
        print('  -', f)
sys.exit(1 if FAILED else 0)
