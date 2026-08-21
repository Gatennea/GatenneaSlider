# -*- coding: utf-8 -*-
"""调试中文字符光标定位"""
import sys
sys.path.insert(0, 'e:/program_project/py/貓九的滑塊遊戲')

from gui.text_input import TextInput
import pygame
pygame.init()

font = pygame.font.SysFont('SimHei', 20)

# 测试中文
t = TextInput('你好世界')
print(f"Text: '{t.text}'")

w_你 = font.size('你')[0]
w_你好 = font.size('你好')[0]
w_你好好 = font.size('你好好')[0]

print(f"Width of '你': {w_你}")
print(f"Width of '你好': {w_你好}")
print(f"Width of '你好世界': {font.size(t.text)[0]}")

# 点击在 '好' 的前部
click_x = w_你 + 5
print(f"\nClicking at pixel {click_x} (in '好')")

# 手动追踪算法
accumulated_width = 0
for i, char in enumerate(t.text):
    char_width = font.size(char)[0]
    mid_point = accumulated_width + char_width // 2
    print(f"  i={i}, char='{char}': width={char_width}, mid_point={mid_point}, accumulated={accumulated_width}")
    if click_x < mid_point:
        print(f"    -> Cursor at {i}")
        break
    accumulated_width += char_width
    if click_x < accumulated_width:
        print(f"    -> Cursor at {i+1}")
        break
else:
    print(f"  -> Cursor at end (len={len(t.text)})")

# 测试方法
pos = t.set_cursor_by_pixel(font, click_x, 200)
print(f"\nResult: cursor_pos={pos}")
