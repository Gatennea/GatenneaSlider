# -*- coding: utf-8 -*-
"""完整测试 TextInput - 所有功能"""
import sys
sys.path.insert(0, 'e:/program_project/py/貓九的滑塊遊戲')

from gui.text_input import TextInput
from GUI import _gui_safe_font
import pygame
pygame.init()

# 直接用 pygame.font.SysFont 会扫描系统字体注册表；某些机器上该表被写入过
# 非字符串项（如 sdk_init_timestamp），splitext 会抛 TypeError。GUI 内部
# 已改用 _gui_safe_font，测试与产品保持同一条加载路径。
font = _gui_safe_font('SimHei', 20)

print("=== 基础功能测试 ===")

t = TextInput('hello')
print('1. Init:', 'text=', repr(t.text), 'cursor_pos=', t.cursor_pos)

class FakeEvent:
    def __init__(self, key, unicode=''):
        self.type = 768
        self.key = key
        self.unicode = unicode
        self.mod = 0

# 测试 Left
t.handle_event(FakeEvent(pygame.K_LEFT))
assert t.cursor_pos == 4
print('2. Left:', t.cursor_pos, '(expected 4)')

# 测试 Right
t.handle_event(FakeEvent(pygame.K_RIGHT))
assert t.cursor_pos == 5
print('3. Right:', t.cursor_pos, '(expected 5)')

# 测试 Home
t.handle_event(FakeEvent(pygame.K_HOME))
assert t.cursor_pos == 0
print('4. Home:', t.cursor_pos, '(expected 0)')

# 测试 End
t.handle_event(FakeEvent(pygame.K_END))
assert t.cursor_pos == 5
print('5. End:', t.cursor_pos, '(expected 5)')

# 测试插入
t.handle_event(FakeEvent(0, 'x'))
assert t.text == 'hellox'
assert t.cursor_pos == 6
print('6. Insert x:', repr(t.text), '(expected "hellox")')

# 测试 Backspace
t.handle_event(FakeEvent(pygame.K_BACKSPACE))
assert t.text == 'hello'
assert t.cursor_pos == 5
print('7. Backspace:', repr(t.text), '(expected "hello")')

# 测试 Delete
t.handle_event(FakeEvent(pygame.K_LEFT))
t.handle_event(FakeEvent(pygame.K_DELETE))
assert t.text == 'hell'
print('8. Delete:', repr(t.text), '(expected "hell")')

print()
print("=== 鼠标点击定位测试 ===")

t2 = TextInput('hello')

# 点击在字符前
pos = t2.set_cursor_by_pixel(font, 0, 200)
assert pos == 0
print('9. Click at 0:', pos, '(expected 0)')

# 点击在 'h' 范围内
w_h = font.size('h')[0]
pos = t2.set_cursor_by_pixel(font, w_h // 2, 200)
assert pos == 1
print('10. Click in "h":', pos, '(expected 1)')

# 点击在 'e' 范围内
w_he = font.size('he')[0]
pos = t2.set_cursor_by_pixel(font, w_he - 1, 200)
assert pos == 2
print('11. Click in "e":', pos, '(expected 2)')

# 点击在末尾
pos = t2.set_cursor_by_pixel(font, 1000, 200)
assert pos == 5
print('12. Click after end:', pos, '(expected 5)')

print()
print("=== 闪烁测试 ===")

t3 = TextInput('')
t3.update(600)
assert t3.blink_visible == False
print('13. Blink after 600ms:', t3.blink_visible, '(expected False)')

t3.update(600)
assert t3.blink_visible == True
print('14. Blink after 1200ms:', t3.blink_visible, '(expected True)')

# 操作后重置闪烁
t3.handle_event(FakeEvent(pygame.K_LEFT))
assert t3.blink_visible == True
print('15. Reset blink on key:', t3.blink_visible, '(expected True)')

print()
print("=== set_text / clear 测试 ===")

t4 = TextInput('test')
t4.set_text('new')
assert t4.text == 'new'
assert t4.cursor_pos == 3
print('16. set_text:', repr(t4.text), '(expected "new")')

t4.clear()
assert t4.text == ''
assert t4.cursor_pos == 0
print('17. clear:', repr(t4.text), '(expected "")')

print()
print("=== get_display_text / get_cursor_offset 测试 ===")

t5 = TextInput('hello')
display, visible = t5.get_display_text(font, 200, 'placeholder', True)
assert display == 'hello'
print('18. get_display_text:', repr(display), '(expected "hello")')

t5.cursor_pos = 3
offset = t5.get_cursor_offset(font)
assert offset == font.size('hel')[0]
print('19. get_cursor_offset at 3:', offset, '(expected', font.size('hel')[0], ')')

print()
print('ALL TESTS PASSED!')
pygame.quit()
