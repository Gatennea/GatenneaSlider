"""三维自定义尺寸（2026-11-18，第 5 阶段）：对话框 + 建局 + 预设档。

验收：
- 自定义框有「三维」形态，字段 m/n/d/step，按钮不越界；
- 回车按 m→n→d→step 走；
- 合法尺寸真的开出三维局；等级越界/尺寸过小给明确错误；
- 三维不出现「高级选项…」（二维设计画布入口）；
- 预设档都合法（1×1×1 保留为明确拒绝的脚手架）。
"""
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

FAILED = []
PASSED = [0]


def check(ok, label, extra=None):
    if ok:
        PASSED[0] += 1
        print(f"  ok: {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL: {label}" + (f"  <- {extra}" if extra is not None else ''))


tmp = tempfile.mkdtemp(prefix='cubic_custom_')
gui = SliderGUI(m=4, n=4, step=1)
gui.config_dir = tmp
gui.config_path = os.path.join(tmp, 'config.json')
gui.temp_history_path = os.path.join(tmp, 'temp.json')
gui.tutorial_active = False
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()

print('A. 对话框渲染：五个形态、三维四字段、按钮不越界')
gui.show_custom_dialog = True
gui.custom_kind = 'cubic'
gui.custom_fields = {'m': '4', 'n': '3', 'd': '2', 'step': '1'}
gui.custom_active_field = 'm'
gui.draw_custom_puzzle_dialog()
check(set(gui.custom_kind_rects) == {'rect', 'triangle', 'mi', 'numbered', 'cubic'},
      '形态按钮含三维', sorted(gui.custom_kind_rects))
check(set(gui.custom_field_rects) == {'m', 'n', 'd', 'step'},
      '三维字段是 m/n/d/step', sorted(gui.custom_field_rects))
_dlg = gui._custom_dialog_rect
check(all(_dlg.contains(r) for r in gui.custom_kind_rects.values()),
      '五个形态按钮都在对话框内')
check(all(_dlg.contains(r) for r in gui.custom_field_rects.values()),
      '四个输入框都在对话框内')
check(_dlg.contains(gui.custom_ok_btn) and _dlg.contains(gui.custom_cancel_btn),
      '确定/取消都在对话框内')
check(getattr(gui.custom_adv_btn, 'width', 0) == 0,
      '三维不出现「高级选项…」')

print('B. 回车导航 m -> n -> d -> step')
_ev = lambda: pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN,
                                 unicode='\r', mod=0)
gui.handle_custom_dialog_events(_ev())
check(gui.custom_active_field == 'n', 'm 回车到 n', gui.custom_active_field)
gui.handle_custom_dialog_events(_ev())
check(gui.custom_active_field == 'd', 'n 回车到 d', gui.custom_active_field)
gui.handle_custom_dialog_events(_ev())
check(gui.custom_active_field == 'step', 'd 回车到 step', gui.custom_active_field)

print('C. 合法尺寸真的建局')
check(gui._custom_apply_fields(), '4×3×2 等级1 建局成功', gui.custom_error)
check(gui.cubic_mode and (gui.current_m, gui.current_n, gui.current_depth) == (4, 3, 2),
      '尺寸记成 4×3×2', (gui.current_m, gui.current_n, gui.current_depth))
check(gui.current_step == 1, '等级记成 1', gui.current_step)
check(not gui.show_custom_dialog, '建局后对话框关闭')

print('D. 非法值给明确错误，不建局')
gui.show_custom_dialog = True
gui.custom_kind = 'cubic'
gui.custom_fields = {'m': '4', 'n': '3', 'd': '2', 'step': '4'}
gui.custom_active_field = 'step'
check(not gui._custom_apply_fields(), '等级 >= 最大维度被拒')
check('等级必须' in gui.custom_error, '错误文案点名等级', gui.custom_error)
gui.custom_fields = {'m': '1', 'n': '1', 'd': '1', 'step': '1'}
check(not gui._custom_apply_fields(), '1×1×1 被拒（一步动不了）')
check('至少一个维度' in gui.custom_error, '错误文案说明原因', gui.custom_error)

print('E. 预设档')
_cubic = gui.puzzle_sub_presets['cubic']
_rows = [p for p in _cubic if len(p) >= 6]
check(len(_rows) >= 8, '预设档数量已扩充', len(_rows))
_bad = []
for name, m, n, step, kind, d in _rows:
    if kind != 'cubic' or m < 1 or n < 1 or d < 1:
        _bad.append(name)
    elif max(m, n, d) >= 2 and not (1 <= step < max(m, n, d)):
        _bad.append(name)
check(not _bad, '除 1×1×1 脚手架外预设都合法', _bad)
# 直接按三元组核对新增档位
_dims = {(p[1], p[2], p[5], p[3]) for p in _rows}
check((4, 4, 4, 1) in _dims and (4, 4, 4, 2) in _dims and (4, 4, 4, 3) in _dims,
      '4×4×4 有等级 1/2/3', sorted(_dims))
check((3, 3, 2, 1) in _dims and (4, 3, 2, 1) in _dims and (5, 5, 5, 1) in _dims,
      '长方体与 5×5×5 档位都在', sorted(_dims))

print('F. 命令面板/检索「自定义谜题」在三维预选三维页')
from gui import feature_index as fi  # noqa: E402
gui.new_cubic_puzzle(3, 3, 2, 1)
_entry = next(e for e in fi.FEATURES if e['id'] == 'custom_puzzle')
gui._activate_feature(_entry)
check(gui.show_custom_dialog, '检索动作打开自定义框')
check(gui.custom_kind == 'cubic', '三维局预选「三维」', gui.custom_kind)
check(gui.custom_fields.get('d') == '2', '层数字段带回当前 d', gui.custom_fields)

print('G. 二维页仍放得下五个形态按钮')
gui.custom_kind = 'rect'
gui.custom_fields = {'m': '6', 'n': '6', 'd': '3', 'step': '2'}
gui.draw_custom_puzzle_dialog()
check(gui._custom_dialog_rect.width == 360, '二维框回到 360 宽',
      gui._custom_dialog_rect)
check(all(gui._custom_dialog_rect.contains(r) for r in gui.custom_kind_rects.values()),
      '二维框五个形态按钮不越界')

print('H. 真点一遍：二维框切「三维」→ 确定建局')
gui.show_custom_dialog = True
gui.custom_kind = 'rect'
gui.custom_fields = {'m': '4', 'n': '3', 'd': '2', 'step': '1'}
gui.draw_custom_puzzle_dialog()
_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                            pos=gui.custom_kind_rects['cubic'].center)
gui.handle_custom_dialog_events(_click)
check(gui.custom_kind == 'cubic', '点「三维」按钮切换形态', gui.custom_kind)
gui.draw_custom_puzzle_dialog()
check(gui._custom_dialog_rect.height == 370, '切换后长高到四字段',
      gui._custom_dialog_rect)
check(gui.custom_adv_btn.width == 0, '切换后没有高级选项按钮')
_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                            pos=gui.custom_ok_btn.center)
gui.handle_custom_dialog_events(_click)
check(gui.cubic_mode and (gui.current_m, gui.current_n, gui.current_depth) == (4, 3, 2),
      '点确定真的开出 4×3×2',
      (gui.current_m, gui.current_n, getattr(gui, 'current_depth', None)))

print('I. 自定义尺寸的存档往返')
_data = gui._build_save_data()
check(_data['puzzle'].get('depth') == 2 and _data['puzzle'].get('m') == 4
      and _data['puzzle'].get('n') == 3,
      '存档写入 4×3×2', _data['puzzle'])
gui.new_cubic_puzzle(2, 2, 2, 1)
gui._load_save_data(_data)
check(gui.cubic_mode and (gui.current_m, gui.current_n, gui.current_depth) == (4, 3, 2),
      '读回仍是 4×3×2',
      (gui.current_m, gui.current_n, getattr(gui, 'current_depth', None)))
check(len(gui.game.blocks) == 24, '读回 24 块', len(gui.game.blocks))

print('=' * 60)
total = PASSED[0] + len(FAILED)
print(f'结果：{"全部通过" if not FAILED else "有失败"}（{PASSED[0]} 项通过，{len(FAILED)} 项失败）／共 {total} 项')
if FAILED:
    for f in FAILED:
        print('  -', f)
sys.exit(1 if FAILED else 0)
