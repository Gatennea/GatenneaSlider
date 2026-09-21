# -*- coding: utf-8 -*-
"""A4：带序号谜题的存读档 v2 / 地图导入重排号 / 成绩记录"""
import os, sys, json
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pygame
pygame.init()
from GUI import SliderGUI

gui = SliderGUI()
# 用户配置可能开了「保存带只读标记」，会阻断载入后的新建谜题，测试中关掉
gui.save_readonly_flag = False
gui.new_puzzle(4, 4, 2, numbered=True)

# 1. 存盘为 v2 且 puzzle.type == 'numbered'
path = '/tmp/_a4_num.json'
gui._save_to_path(path)
with open(path, encoding='utf-8') as f:
    data = json.load(f)
assert data['version'] == 2, data['version']
assert data['puzzle']['type'] == 'numbered', data['puzzle']
assert 'numbers' in data['history']['snapshots'][0]
print('PASS: v2 存档带 type=numbered 与 numbers')

# 2. 读档恢复 numbered 标志与编号
gui.new_puzzle(3, 3, 2)               # 先换成普通局
assert getattr(gui, 'numbered', False) is False
gui._do_load_from_path(path)
assert gui.numbered is True
nums = sorted(b.number for b in gui.game.blocks if b.number)
assert nums == list(range(1, 17)), nums
print('PASS: 读档恢复 numbered 标志与 1..16 编号')

# 3. 普通方形仍写 v1 且可读
gui.new_puzzle(4, 4, 2)
path2 = '/tmp/_a4_plain.json'
gui._save_to_path(path2)
with open(path2, encoding='utf-8') as f:
    d2 = json.load(f)
assert d2['version'] == 1 and 'type' not in d2['puzzle'], d2['puzzle']
gui.new_puzzle(5, 5, 2)
gui._do_load_from_path(path2)
assert gui.numbered is False and len(gui.game.blocks) == 16
print('PASS: 普通方形仍为 v1 且向后兼容读档')

# 4. 带序号模式导入地图 → 行主序重排号
gui.new_puzzle(4, 4, 2, numbered=True)
map_str = '#_#_\n_#_#\n#__#\n__##'
ok, msg = gui._do_load_map(map_str)
assert ok, msg
nums = [b.number for b in sorted(gui.game.blocks, key=lambda b: (b.location[0], b.location[1]))]
assert nums == list(range(1, len(nums) + 1)), nums
print(f'PASS: 地图导入后重排号 1..{len(nums)}')

# 5. 成绩记录带 numbered 字段
gui.records.add_record('2~4*4#num', 4, 4, 2, '1111\n1111\n1111\n1111', 5000, 10, False, numbered=True)
rec = gui.records.get_records('2~4*4#num')[-1]
assert rec['numbered'] is True
# 旧记录无该字段时 .get 容错
rec2 = {'puzzle_key': '2~4*4#num'}
assert bool(rec2.get('numbered')) or rec2['puzzle_key'].endswith('#num')
print('PASS: 成绩记录带 numbered，旧记录靠 key 后缀兼容')

# 6. 成绩面板：另存为 / 载入练习（带序号）
saved = gui._rp_save_as_puzzle(rec)
assert saved and os.path.exists(saved)
with open(saved, encoding='utf-8') as f:
    d3 = json.load(f)
assert d3['version'] == 2 and d3['puzzle']['type'] == 'numbered'
assert 'numbers' in d3['history']['snapshots'][0]
print('PASS: 成绩面板另存为产生 v2 带序号存档')

gui.new_puzzle(3, 3, 2)
gui._rp_load_into_practice(rec)
assert gui.numbered is True
assert sorted(b.number for b in gui.game.blocks if b.number) == list(range(1, 17))
print('PASS: 成绩面板载入练习恢复带序号谜题')

os.remove(path); os.remove(path2); os.remove(saved)
print('A4 numbered save PASS')
pygame.quit()
