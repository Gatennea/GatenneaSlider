# -*- coding: utf-8 -*-
"""测试 TextInput 组件"""
import sys
sys.path.insert(0, 'e:/program_project/py/貓九的滑塊遊戲')

from gui.text_input import TextInput
import pygame
pygame.init()

# 测试基本功能
t = TextInput('hello')
print('1. Init:', 'text=', repr(t.text), 'cursor_pos=', t.cursor_pos, 'blink_visible=', t.blink_visible)

# 创建假的键盘事件
class FakeEvent:
    def __init__(self, key, unicode='', type_=pygame.KEYDOWN):
        self.type = type_
        self.key = key
        self.unicode = unicode
        # handle_event 会读 event.mod 传给 _start_repeat/_process_key
        self.mod = 0

# 测试 Left 键
t.handle_event(FakeEvent(pygame.K_LEFT))
assert t.cursor_pos == 4, f"Expected cursor_pos=4, got {t.cursor_pos}"
print('2. After Left:', 'cursor_pos=', t.cursor_pos)

# 测试插入字符
t.handle_event(FakeEvent(0, 'x'))
assert t.text == 'hellxo', f"Expected 'hellxo', got '{t.text}'"
assert t.cursor_pos == 5, f"Expected cursor_pos=5, got {t.cursor_pos}"
print('3. After insert x:', 'text=', repr(t.text), 'cursor_pos=', t.cursor_pos)

# 测试 Backspace（删除光标前的字符，即插入的 'x'，回到 'hello'）
t.handle_event(FakeEvent(pygame.K_BACKSPACE))
assert t.text == 'hello', f"Expected 'hello', got '{t.text}'"
assert t.cursor_pos == 4, f"Expected cursor_pos=4, got {t.cursor_pos}"
print('4. After Backspace:', 'text=', repr(t.text), 'cursor_pos=', t.cursor_pos)

# 再次 Backspace，删除 'l'（光标位置4，删除索引3的 'l'）
t.handle_event(FakeEvent(pygame.K_BACKSPACE))
assert t.text == 'helo', f"Expected 'helo', got '{t.text}'"
assert t.cursor_pos == 3
print('4b. After 2nd Backspace:', 'text=', repr(t.text), 'cursor_pos=', t.cursor_pos)

# 测试 Home
t.handle_event(FakeEvent(pygame.K_HOME))
assert t.cursor_pos == 0
print('5. After Home:', 'cursor_pos=', t.cursor_pos)

# 测试 Delete
t.handle_event(FakeEvent(pygame.K_DELETE))
assert t.text == 'elo', f"Expected 'elo', got '{t.text}'"
print('6. After Delete:', 'text=', repr(t.text))

# 测试 End
t.handle_event(FakeEvent(pygame.K_END))
assert t.cursor_pos == len(t.text)
print('7. After End:', 'cursor_pos=', t.cursor_pos)

# 测试 Right (不应该移出边界)
t.handle_event(FakeEvent(pygame.K_RIGHT))
assert t.cursor_pos == len(t.text)
print('8. After Right at end:', 'cursor_pos=', t.cursor_pos)

# 测试闪烁
# 先松开按键：长按重复每触发一次都会重置闪烁计时，按住不放测不到翻转
t.handle_event(FakeEvent(pygame.K_RIGHT, type_=pygame.KEYUP))
t.update(600)
assert t.blink_visible == False, f"Expected False after 600ms, got {t.blink_visible}"
print('9. After 600ms update:', 'blink_visible=', t.blink_visible)

t.update(600)
assert t.blink_visible == True
print('10. After another 600ms:', 'blink_visible=', t.blink_visible)

# 测试 _reset_blink（通过操作触发）
t.handle_event(FakeEvent(pygame.K_RIGHT))
assert t.blink_visible == True
print('11. After key press (reset blink):', 'blink_visible=', t.blink_visible)

# 测试 set_text
t.set_text('new text')
assert t.text == 'new text'
assert t.cursor_pos == len('new text')
print('12. set_text:', 'text=', repr(t.text), 'cursor_pos=', t.cursor_pos)

# 测试 clear
t.clear()
assert t.text == ''
assert t.cursor_pos == 0
print('13. clear:', 'text=', repr(t.text), 'cursor_pos=', t.cursor_pos)

# 测试 get_display_text 和 get_cursor_offset
t2 = TextInput('hello world')
# 与产品同一条字体加载路径：直接 SysFont 会扫描系统字体注册表，
# 某些机器上该表被写入过非字符串项，splitext 会抛 TypeError
from GUI import _gui_safe_font
font = _gui_safe_font('SimHei', 20)
display, visible = t2.get_display_text(font, 200, 'placeholder', True)
print('14. get_display_text (short):', repr(display), 'visible=', visible)
offset = t2.get_cursor_offset(font)
print('15. cursor_offset:', offset, '(should be > 0)')

# 测试空文本 + active
t3 = TextInput('')
display, visible = t3.get_display_text(font, 200, '请输入...', True)
print('16. empty+active:', repr(display), 'visible=', visible)

# 测试空文本 + inactive
t3.active = False
display, visible = t3.get_display_text(font, 200, '请输入...', False)
print('17. empty+inactive:', repr(display), 'visible=', visible)

# 测试退格到空
t4 = TextInput('a')
t4.handle_event(FakeEvent(pygame.K_BACKSPACE))
assert t4.text == ''
assert t4.cursor_pos == 0
print('18. Backspace to empty:', 'text=', repr(t4.text), 'cursor_pos=', t4.cursor_pos)

print()
print('ALL TESTS PASSED!')
pygame.quit()
