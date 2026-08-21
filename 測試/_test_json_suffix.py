# -*- coding: utf-8 -*-
"""测试文件对话框自动补 .json 后缀"""
import sys
sys.path.insert(0, 'e:/program_project/py/貓九的滑塊遊戲')

import pygame
pygame.init()

# 模拟 _ensure_json 逻辑

def _ensure_json(name):
    if name and not name.lower().endswith('.json'):
        return name + '.json'
    return name

# 测试用例
print("=== _ensure_json 测试 ===")

# 1. 有 .json 后缀
assert _ensure_json('save.json') == 'save.json'
print('1. save.json ->', _ensure_json('save.json'), '(expected save.json)')

# 2. 大写 .JSON 后缀
assert _ensure_json('save.JSON') == 'save.JSON'
print('2. save.JSON ->', _ensure_json('save.JSON'), '(expected save.JSON)')
# 3. 没有后缀
assert _ensure_json('mygame') == 'mygame.json'
print('3. mygame ->', _ensure_json('mygame'), '(expected mygame.json)')

# 4. 其他后缀
assert _ensure_json('data.txt') == 'data.txt.json'
print('4. data.txt ->', _ensure_json('data.txt'), '(expected data.txt.json)')

# 5. 空字符串
assert _ensure_json('') == ''
print('5. "" ->', repr(_ensure_json('')), '(expected "")')

# 6. 只有后缀
assert _ensure_json('.json') == '.json'
print('6. .json ->', _ensure_json('.json'), '(expected .json)')

# 7. 中文
assert _ensure_json('拼图1') == '拼图1.json'
print('7. 拼图1 ->', _ensure_json('拼图1'), '(expected 拼图1.json)')

# 8. 中间有点
assert _ensure_json('my.game') == 'my.game.json'
print('8. my.game ->', _ensure_json('my.game'), '(expected my.game.json)')

print()
print('ALL TESTS PASSED!')
pygame.quit()
