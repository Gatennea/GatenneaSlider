# -*- coding: utf-8 -*-
"""回归：三维局的存档口子（2026-11-17 用户实测控制台报错）。

现场：
    旧模型存档缺 engine_state，已载入但块可能缺失
    加载上次状态失败: 存档需要模型 'cubic'，但它没有安装…

两个问题都出在我自己造的坏档上（cubic 局的 json 载入端读不回来）。钉住：
  A. temp_history 里若是 `type: cubic`，启动要**安静回落**，不许提「模型
     cubic.json 未安装」，并且要用新局把这条坏档覆盖掉（自愈，不然每次启动都弹）。
  B. 三维局里 Ctrl+S / 另存为要被挡住并给出原因（第 5 步才支持），不落坏档。

跑法：D:/python/python.exe test/_test_cubic_save_guard.py
"""
import os
import sys
import json
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


def make_gui():
    gui = SliderGUI(m=4, n=4, step=1)
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    d = tempfile.mkdtemp(prefix='gs_cubic_save_guard_')
    gui.config_dir = d
    gui.temp_history_path = os.path.join(d, 'temp_history.json')
    gui.config_path = os.path.join(d, 'config.json')
    gui._readonly = False
    gui.save_readonly_flag = False
    gui.animation_enabled = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui._cubic_camera_prefs = {}
    return gui


STALE = {
    'version': 2,
    'puzzle': {'m': 3, 'n': 3, 'step': 1, 'type': 'cubic'},
    'readonly': False,
    'history': {'history_index': 0, 'snapshots': [{
        'matrix': [[0] * 9 for _ in range(9)],
        'bounds': [[0, 0], [8, 8]],
        'moves': [], 'steps': 0, 'step_total': 0,
    }]},
}

print('=' * 60)
print('A. cubic 自动存档：安静回落 + 自愈')
gui = make_gui()
with open(gui.temp_history_path, 'w', encoding='utf-8') as f:
    json.dump(STALE, f)
json.dump({'last_file_path': gui.temp_history_path},
          open(gui.config_path, 'w', encoding='utf-8'))
gui.load_last_state()
check(gui._current_kind() == 'square', f'回落到二维局（{gui._current_kind()}）')
with open(gui.temp_history_path, encoding='utf-8') as f:
    healed = json.load(f)
check(healed['puzzle'].get('type') in (None, 'square'),
      f'坏档已被覆盖成二维局（{healed["puzzle"].get("type")}）', healed['puzzle'])
check(healed['puzzle'].get('m') == gui.current_m,
      f'覆盖内容就是当前局（{healed["puzzle"].get("m")}×{healed["puzzle"].get("n")}）')

print('B. 三维局现在能存档（第 5 步）：type+depth，且读得回来')
gui2 = make_gui()
gui2.new_cubic_puzzle(3, 3, 3, 1)
target = os.path.join(gui2.config_dir, 'cubic_ok.json')
result = gui2._save_to_path(target)
check(result is True, f'_save_to_path 返回 True（{result}）')
check(os.path.exists(target), '文件确实写出来了')
with open(target, encoding='utf-8') as f:
    saved = json.load(f)
check(saved['puzzle'].get('type') == 'cubic', f'type=cubic（{saved["puzzle"].get("type")}）')
check(saved['puzzle'].get('depth') == 3, f'depth=3（{saved["puzzle"].get("depth")}）')
check(all('matrix' not in s for s in saved['history']['snapshots']),
      '三维快照不写二维矩阵')
check(all(len((s.get('engine_state') or {}).get('keys') or []) == 27
          for s in saved['history']['snapshots']),
      '每条快照都带 27 块的无损键表')

gui3 = make_gui()
gui3._cubic_camera_prefs = {}
with open(target, encoding='utf-8') as f:
    gui3._load_save_data(json.load(f))
check(gui3.cubic_mode is True, '读回后仍是三维局')
check(len(gui3.game.blocks) == 27, f'读回 27 块（{len(gui3.game.blocks)}）')

print('=' * 60)
if _fail:
    print(f'结果：{_ok[0]} 项通过，{len(_fail)} 项失败')
    for m in _fail:
        print('  ·', m)
    sys.exit(1)
print(f'结果：全部通过（{_ok[0]} 项通过，0 项失败）')
