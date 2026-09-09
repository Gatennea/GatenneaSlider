# -*- coding: utf-8 -*-
"""测试 TextInput 鼠标点击定位光标"""
import sys
sys.path.insert(0, 'e:/program_project/py/貓九的滑塊遊戲')

from gui.text_input import TextInput
import pygame
pygame.init()

font = pygame.font.SysFont('SimHei', 20)

# 测试 set_cursor_by_pixel
t = TextInput('hello')

# 测试1: 点击在第一个字符之前 -> 光标应在位置0
pos = t.set_cursor_by_pixel(font, 0, 200)
assert pos == 0, f"Expected 0, got {pos}"
print(f"1. Click at pixel 0: cursor_pos={t.cursor_pos} (expected 0)")

# 测试2: 点击在字符 'h' 的范围内 -> 光标应在位置1
w_h = font.size('h')[0]
pos = t.set_cursor_by_pixel(font, w_h // 2, 200)
assert pos == 1, f"Expected 1, got {pos}"
print(f"2. Click in 'h': cursor_pos={t.cursor_pos} (expected 1)")

# 测试3: 点击在 'e' 的范围内 -> 光标应在位置2
w_he = font.size('he')[0]
pos = t.set_cursor_by_pixel(font, w_he - 2, 200)
assert pos == 2, f"Expected 2, got {pos}"
print(f"3. Click in 'e': cursor_pos={t.cursor_pos} (expected 2)")

# 测试4: 点击在字符串之后 -> 光标在末尾
pos = t.set_cursor_by_pixel(font, 1000, 200)
assert pos == 5, f"Expected 5, got {pos}"
print(f"4. Click after end: cursor_pos={t.cursor_pos} (expected 5)")

# 测试5: 空文本
t2 = TextInput('')
pos = t2.set_cursor_by_pixel(font, 50, 200)
assert pos == 0, f"Expected 0, got {pos}"
print(f"5. Empty text click: cursor_pos={t2.cursor_pos} (expected 0)")

# 测试6: 中文文本
t3 = TextInput('你好世界')
# 点击在第一个字符之前
pos = t3.set_cursor_by_pixel(font, 0, 200)
assert pos == 0, f"Expected 0, got {pos}"
print(f"6. Chinese text click at 0: cursor_pos={t3.cursor_pos} (expected 0)")

# 点击在 '好' 的后半部分（mid_point是30，所以35在右半边） -> 光标在位置2
w_你 = font.size('你')[0]
pos = t3.set_cursor_by_pixel(font, w_你 + 15, 200)  # 35, 在 '好' 的后半部分
assert pos == 2, f"Expected 2, got {pos}"
print(f"7. Chinese text click in right half of '好': cursor_pos={t3.cursor_pos} (expected 2)")

print()
print('ALL MOUSE CLICK TESTS PASSED!')
pygame.quit()
