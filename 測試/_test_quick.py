# -*- coding: utf-8 -*-
"""测试 TextInput 核心功能（修正边缘情况）"""
import sys
sys.path.insert(0, 'e:/program_project/py/貓九的滑塊遊戲')

from gui.text_input import TextInput
import pygame
pygame.init()

font = pygame.font.SysFont('SimHei', 20)

passed = 0
failed = 0

def check(name, condition):
    global passed, failed
    if condition:
        print(f"  OK: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name}")
        failed += 1

def make_key_event(key, unicode='', mods=0):
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode, mod=mods)

print("=== 测试: 鼠标点击定位（修正位置） ===")
t = TextInput('hello')
input_rect = pygame.Rect(100, 100, 200, 30)

# 点击位置 0（字符之前，2 像素偏移）
e = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(102, 110))
t.handle_event(e, font, input_rect)
check("点击字符前", t.cursor_pos == 0)

# 点击在文本末尾之后
t.set_text('hello')
e = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(250, 110))
t.handle_event(e, font, input_rect)
check("点击文本之后", t.cursor_pos == 5)

# 点击在中间字符
t.set_text('abcdef')
t._selection_start = 0
t._selection_end = 0
e = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(125, 110))
t.handle_event(e, font, input_rect)
print(f"  点击 (125,110) 时光标位置: {t.cursor_pos}")
check("点击中间位置", 0 < t.cursor_pos < 6)

print("\n=== 测试: 中文输入（逐字符） ===")
t2 = TextInput('')
t2.handle_event(make_key_event(0, '测'))
t2.handle_event(make_key_event(0, '试'))
check("输入中文 '测试'", t2.text == '测试' and t2.cursor_pos == 2)

print("\n=== 测试: 输入时替换选中 ===")
t3 = TextInput('hello world')
t3._selection_start = 0
t3._selection_end = 5
t3.cursor_pos = 5
t3.handle_event(make_key_event(0, 'H'))
check("大写替换小写", t3.text == 'H world' and t3.cursor_pos == 1)

print("\n=== 测试: 光标闪烁状态 ===")
t4 = TextInput('test')
t4._blink_visible = True
t4.update(600)  # 600ms > 500ms
check("600ms 后闪烁状态反转", t4.blink_visible == False)

print("\n=== 测试: 操作后重置闪烁 ===")
t5 = TextInput('test')
t5._blink_visible = False
t5.handle_event(make_key_event(pygame.K_LEFT))
check("按键操作后重置闪烁", t5.blink_visible == True)

print("\n=== 测试: 长按后光标移动多次 ===")
t6 = TextInput('1234567890')
t6.cursor_pos = 10
t6._selection_start = 10
t6._selection_end = 10

# 启动长按 Left
t6._start_repeat(pygame.K_LEFT, 0)
# 模拟 800ms
for _ in range(80):
    t6.update(10)  # 80 * 10ms = 800ms

print(f"  长按 Left 800ms 后光标位置: {t6.cursor_pos} (初始=10)")
check("长按 Left 后光标移动", t6.cursor_pos < 10)

# 测试 KEYUP 停止
t6._stop_repeat()
prev_pos = t6.cursor_pos
for _ in range(50):
    t6.update(10)
check("KEYUP 后停止移动", t6.cursor_pos == prev_pos)

print("\n=== 测试: get_selection_range() ===")
t7 = TextInput('test text')
t7._selection_start = 5
t7._selection_end = 9
s, e = t7.get_selection_range()
check("选中范围正确", s == 5 and e == 9)
check("has_selection() 为 True", t7.has_selection() == True)

# 交换 start/end 测试
t7._selection_start = 9
t7._selection_end = 5
s, e = t7.get_selection_range()
check("反向选择范围正确", s == 5 and e == 9)

# 无选中
t7._selection_start = 5
t7._selection_end = 5
check("无选中时 has_selection=False", t7.has_selection() == False)

print("\n" + "=" * 50)
print(f"测试结果: {passed} 通过, {failed} 失败")
print("=" * 50)

if failed == 0:
    print("\n✓ ALL TESTS PASSED!")
else:
    print("\n✗ SOME TESTS FAILED")

pygame.quit()
sys.exit(0 if failed == 0 else 1)
