# -*- coding: utf-8 -*-
"""回归：三維調試面板（P0）。

钉住四件事：
  A. 三維局不再落到「本形態尚未實裝」占位行，且面板加寬到 260；
  B. 行內容報的是三維真實狀態（尺寸/塊數/視角/縮放/切面/選中/場景/宏佇列），
     不含二維「聚攏度 / 重疊 / 填充率 / 邊界盒」假數字；
  C. 宏 op 佇列與錯誤文字真的從 `macro_exec_ops` / `macro_error_index` 讀；
  D. 設定 → 三維頁有「調試面板」開關，點一下真的切 `show_metrics_panel`；
     二維面板寬度保持 190，不被三維改動影響。

跑法：D:/python/python.exe test/_test_cubic_metrics_panel.py
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
print('A. 三維面板不再是占位行')
pygame.init()
gui = SliderGUI(m=4, n=4, step=1)
gui.animation_enabled = False
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_mp_')
gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
gui.config_path = os.path.join(gui.config_dir, 'config.json')
gui._readonly = False
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()
gui._cubic_camera_prefs = {}
gui.new_cubic_puzzle(3, 3, 3, 1)

check(gui._mp_kind() == 'cubic', '三維局 _mp_kind 回 cubic', gui._mp_kind())
rows, met = gui._mp_rows()
labels = [r[0] for r in rows]
check('调试面板' not in labels, '不再出现「调试面板：本形态尚未实装」占位行', labels)
check('形态' in labels and rows[0][1] == '三维 3×3×3',
      '首行報三維尺寸', rows[0])
check(not any(k in labels for k in ('聚拢度', '重叠', '填充率', '边界盒')),
      '三維不套二維聚攏指標（禁止假數字）', labels)
check(met is None, '三維 _mp_current_metrics 明確回 None（算不出就不假裝）', met)

print('=' * 60)
print('B. 面板寬度 / 行數 / 真實狀態')

gui.draw_cubic_board()
gui.selected_gap = ('d', 1)
gui.cubic_gap = 0.12
gui.cubic_seam_alpha = 110
gui.cubic_zoom = 1.25
if gui.game.blocks:
    gui.game.blocks[0].be_opted = True
gui.macro_exec_ops = [
    {'kind': 'cubic', 'gap_type': 'd', 'gap_line': 1,
     'side': 'above', 'direction': 'R', 'step': 1},
    {'kind': 'cubic', 'gap_type': 'r', 'gap_line': 0,
     'side': 'below', 'direction': 'L', 'step': 1},
]
gui.macro_exec_index = 1
gui.macro_error_msg = ''
rows, _ = gui._mp_rows()
_d = {k: v for k, v in rows}
check('1.25' not in _d.get('缩放', '') and _d.get('缩放') == '125%',
      '縮放行讀 cubic_zoom（125%）', _d.get('缩放'))
check(_d.get('拆分') == '0.12', '拆分讀 cubic_gap', _d.get('拆分'))
check(_d.get('切面') == 'd1 α110', '切面讀 selected_gap + alpha', _d.get('切面'))
check(_d.get('选中组') == '1块', '選中組按 be_opted 統計', _d.get('选中组'))
check(_d.get('操作队') == '1/2', '宏佇列 = index/len(ops)', _d.get('操作队'))
check(_d.get('当前op') == 'r 0 below L', '當前 op 報 gap/side/direction', _d.get('当前op'))
check(_d.get('错误') == '-', '沒錯誤時報 -', _d.get('错误'))

gui.show_metrics_panel = True
gui.draw_metrics_panel()
check(gui.mp_panel_rect is not None and gui.mp_panel_rect.width == 260,
      '三維面板寬 260（二維仍 190）', gui.mp_panel_rect)
check(gui.mp_panel_rect.height == gui._MP_TITLE_H + gui._MP_PAD * 2 + gui._MP_ROW_H * len(rows),
      '面板高度按 12 行算，不截最後一行', gui.mp_panel_rect.height)

gui.macro_exec_index = 2
gui.macro_error_msg = '目标块被挪走后找不到替代块'
rows, _ = gui._mp_rows()
check(dict(rows)['操作队'] == '2/2', 'index 走到隊尾仍顯示 2/2')
check(dict(rows)['当前op'] == '-', '隊尾沒有當前 op 時報 -')
check(dict(rows)['错误'].startswith('目标块'), '最後錯誤真的顯示', dict(rows)['错误'])

print('=' * 60)
print('C. 設定 → 三維頁的調試面板開關')

gui.settings_active_tab = 'cubic'
gui.show_metrics_panel = False
gui.settings_open = True
gui.draw_settings_dialog()
_rect = getattr(gui, '_settings_metrics_toggle_rect', None)
check(_rect is not None, '三維設定頁畫出「調試面板」開關矩形')
check(_rect is not None and _rect.top > 100 + 48,
      '開關在三個數值行下方，不壓其它控件')
if _rect is not None:
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'pos': _rect.center, 'button': 1})
    gui._handle_settings_dialog_event(ev)
    check(gui.show_metrics_panel is True,
          '點三維頁開關 → show_metrics_panel 真的變 True')

print('=' * 60)
print('D. 二維面板不被三維加寬污染')
gui.show_metrics_panel = False
gui.new_puzzle(4, 4, 1)
check(gui._mp_kind() == 'square', '切回二維 _mp_kind = square', gui._mp_kind())
_rows2, _ = gui._mp_rows()
_labels2 = [r[0] for r in _rows2]
check('聚拢度' in _labels2 or '聚拢' in _labels2,
      '二維仍走原聚攏行', _labels2)
check(gui._mp_panel_size(len(_rows2))[0] == 190,
      '二維面板寬仍是 190', gui._mp_panel_size(len(_rows2)))

print('=' * 60)
print(f'{_ok[0]} ok, {len(_fail)} failed')
if _fail:
    for msg in _fail:
        print('FAIL:', msg)
    raise SystemExit(1)
