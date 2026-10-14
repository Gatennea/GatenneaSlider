# -*- coding: utf-8 -*-
"""A5：带序号谜题的竞速计时 key / 判胜 / 成绩面板 key / HTTP status key"""
import os, sys
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pygame
pygame.init()
from GUI import SliderGUI

gui = SliderGUI()
gui.save_readonly_flag = False
gui.new_puzzle(4, 4, 2, numbered=True)

# 1. 计时 key 带 #num
gui._timer_enter_ready()
assert gui.timer_puzzle_key == '2~4*4#num', gui.timer_puzzle_key
print('PASS: timer key =', gui.timer_puzzle_key)

# 2. 判胜：初始状态 → 已复原；打乱后 → 未复原；reset 回初始 → 复原
assert gui.is_solved() is True
gui.shuffle_puzzle()
assert gui.is_solved() is False, '打乱后不应判胜'
gui.reset_puzzle()
assert gui.is_solved() is True, 'reset 回初始后应判胜'
print('PASS: is_solved 对编号归位敏感')

# 2b. 形状复原但编号错位 → 未复原（交换两块编号，位置不动）
gui.new_puzzle(4, 4, 2, numbered=True)
b0, b1 = gui.game.blocks[0], gui.game.blocks[1]
b0.number, b1.number = b1.number, b0.number
assert gui.is_solved() is False, '编号错位时即使形状复原也不应判胜'
print('PASS: 形状复原+编号错位 → 未复原')

# 3. 成绩面板 key
assert gui._rp_current_key() == '2~4*4#num', gui._rp_current_key()
print('PASS: 成绩面板 key =', gui._rp_current_key())

# 4. HTTP /status 的 puzzle key
st = gui._get_game_status()
assert st['puzzle'] == '2~4*4#num', st['puzzle']
assert all('num' in b for b in st['blocks'])
print('PASS: /status puzzle key 带 #num 且 blocks 带 num')

# 5. 普通方形不受影响
gui.new_puzzle(4, 4, 2)
assert gui._rp_current_key() == '2~4*4'
gui._timer_enter_ready()
assert gui.timer_puzzle_key == '2~4*4'
assert gui._get_game_status()['puzzle'] == '2~4*4'
print('PASS: 普通方形 key 不变')

# 6. 序号模式自动求解已放行（求解器只复原形状，数字乱序为预期，玩家后调）
import time as _time
gui.new_puzzle(4, 4, 2, numbered=True)
gui._start_auto_solve()
# 复原盘面秒解：线程可能瞬间退出，不能断言 running；只断言未走旧拒绝分支
assert gui.macro_notify_msg != '带序号模式暂不支援自动求解', gui.macro_notify_msg
_t0 = _time.time()
while (_time.time() - _t0 < 10
       and (getattr(gui, '_auto_solve_running', False)
            or getattr(gui, '_auto_solve_done', False))):
    gui._check_auto_solve_result()
    _time.sleep(0.01)
gui._check_auto_solve_result()
assert '复原' in (gui.macro_notify_msg or ''), gui.macro_notify_msg
print('PASS: 序号模式自动求解已放行（形状复原为准，数字后调）')

print('A5 numbered timer PASS')
pygame.quit()
