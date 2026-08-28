# -*- coding: utf-8 -*-
"""验证：竞速模式禁止打开存档，练习模式正常"""
import os, sys
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

from GUI import SliderGUI

gui = SliderGUI(m=6, n=6, step=1)

# 竞速模式：load_from_file 应被拦截（不弹对话框）
gui.game_mode = 'timed'
gui.load_from_file()
assert gui._pending_load is False, "竞速模式不应进入对话框"
assert "竞速" in gui.macro_notify_msg, gui.macro_notify_msg
print("[PASS] 竞速模式 load_from_file 被拦截:", gui.macro_notify_msg)

# 竞速模式：_do_load_from_path 双重拦截
import json, tempfile
d = tempfile.mkdtemp()
p = os.path.join(d, 'x.json')
with open(p, 'w', encoding='utf-8') as f:
    json.dump({'version': 1}, f)
gui.game_mode = 'timed'
gui._do_load_from_path(p)
assert gui.current_file_path is None, "竞速模式不应加载"
print("[PASS] 竞速模式 _do_load_from_path 被拦截")

# 练习模式：正常进入对话框
gui.game_mode = 'practice'
gui.load_from_file()
assert gui._pending_load is True, "练习模式应弹对话框"
print("[PASS] 练习模式 load_from_file 正常")

print("ALL PASS")
