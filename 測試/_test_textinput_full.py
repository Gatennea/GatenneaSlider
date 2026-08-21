# -*- coding: utf-8 -*-
"""完整测试 TextInput 组件"""
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
    e = pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode, mod=mods)
    return e

def make_keyup_event(key):
    return pygame.event.Event(pygame.KEYUP, key=key)

print("=== 测试 1: 基本输入和光标移动 ===")
t = TextInput('hello')
check("初始文本", t.text == 'hello')
check("初始光标在末尾", t.cursor_pos == 5)

# Left 移动
t.handle_event(make_key_event(pygame.K_LEFT))
check("Left 移动光标", t.cursor_pos == 4)

# Right 移动
t.handle_event(make_key_event(pygame.K_RIGHT))
check("Right 移动光标", t.cursor_pos == 5)

# Home
t.handle_event(make_key_event(pygame.K_HOME))
check("Home", t.cursor_pos == 0)

# End
t.handle_event(make_key_event(pygame.K_END))
check("End", t.cursor_pos == 5)

# 输入字符
t.handle_event(make_key_event(0, 'x'))
check("插入字符 x", t.text == 'hellox' and t.cursor_pos == 6)

print("\n=== 测试 2: Backspace 和 Delete ===")
t2 = TextInput('hello')

# 删除光标前
t2.handle_event(make_key_event(pygame.K_BACKSPACE))
check("Backspace 删除末尾字符", t2.text == 'hell' and t2.cursor_pos == 4)

# 移动光标到中间，然后 Backspace
t2.set_text('hello')
t2.cursor_pos = 3
t2._selection_start = 3
t2._selection_end = 3
t2.handle_event(make_key_event(pygame.K_BACKSPACE))
check("Backspace 删除中间字符", t2.text == 'helo' and t2.cursor_pos == 2)

# Delete 删除光标后
t2.set_text('hello')
t2.cursor_pos = 2
t2._selection_start = 2
t2._selection_end = 2
t2.handle_event(make_key_event(pygame.K_DELETE))
check("Delete 删除光标后字符", t2.text == 'helo' and t2.cursor_pos == 2)

print("\n=== 测试 3: 选中和删除选中 ===")
t3 = TextInput('hello world')

# 模拟选中 "hello" (0-5)
t3._selection_start = 0
t3._selection_end = 5
t3.cursor_pos = 5
check("has_selection() 有选中", t3.has_selection() == True)

# Backspace 删除选中
t3.handle_event(make_key_event(pygame.K_BACKSPACE))
check("Backspace 删除选中", t3.text == ' world' and t3.cursor_pos == 0)
check("删除后无选中", t3.has_selection() == False)

# 测试输入字符替换选中
t3.set_text('hello world')
t3._selection_start = 0
t3._selection_end = 5
t3.cursor_pos = 5
t3.handle_event(make_key_event(0, 'X'))
check("输入字符替换选中", t3.text == 'X world' and t3.cursor_pos == 1)

# 测试 Delete 删除选中
t3.set_text('hello world')
t3._selection_start = 0
t3._selection_end = 5
t3.cursor_pos = 5
t3.handle_event(make_key_event(pygame.K_DELETE))
check("Delete 删除选中", t3.text == ' world' and t3.cursor_pos == 0)

print("\n=== 测试 4: Shift + 方向键扩展选择 ===")
t4 = TextInput('hello')
t4.cursor_pos = 5
t4._selection_start = 5
t4._selection_end = 5

# Shift + Left 扩展选择
t4.handle_event(make_key_event(pygame.K_LEFT, '', pygame.KMOD_SHIFT))
check("Shift+Left 扩展选择", t4.cursor_pos == 4 and t4._selection_end == 4)

# 再次 Shift+Left
t4.handle_event(make_key_event(pygame.K_LEFT, '', pygame.KMOD_SHIFT))
check("再次 Shift+Left", t4.cursor_pos == 3 and t4._selection_end == 3)

# 普通 Left 会跳到选中起点
t4.handle_event(make_key_event(pygame.K_LEFT))
check("普通 Left 跳到选中起点", t4.cursor_pos == 3 and t4.has_selection() == False)

print("\n=== 测试 5: Ctrl+A 全选 ===")
t5 = TextInput('hello')
t5.handle_event(make_key_event(pygame.K_a, '', pygame.KMOD_CTRL))
check("Ctrl+A 全选", t5._selection_start == 0 and t5._selection_end == 5 and t5.cursor_pos == 5)

print("\n=== 测试 6: 长按重复（方向键） ===")
t6 = TextInput('hello')
t6.cursor_pos = 5
t6._selection_start = 5
t6._selection_end = 5

# 启动长按
t6._start_repeat(pygame.K_LEFT, 0)

# 模拟时间流逝：1 秒内应该触发多次重复
for _ in range(100):
    t6.update(10)  # 100 次 * 10ms = 1s

# 光标应该向左移动了多次（从 5 移动到 0 附近）
check("长按 Left 重复触发", t6.cursor_pos < 5)

print("\n=== 测试 7: 长按重复（Backspace） ===")
t7 = TextInput('hello world')
t7.cursor_pos = 11
t7._selection_start = 11
t7._selection_end = 11

t7._start_repeat(pygame.K_BACKSPACE, 0)
for _ in range(100):
    t7.update(10)

check("长按 Backspace 重复删除", len(t7.text) < 11)

print("\n=== 测试 8: KEYUP 停止长按 ===")
t8 = TextInput('hello')
t8._start_repeat(pygame.K_LEFT, 0)
t8.update(1000)  # 先触发一些
pos_after_some = t8.cursor_pos

t8._stop_repeat()  # 手动停止
for _ in range(50):
    t8.update(10)

check("KEYUP 停止长按", t8.cursor_pos == pos_after_some)

print("\n=== 测试 9: 鼠标点击定位 ===")
t9 = TextInput('hello')
# 模拟点击输入框内的位置
input_rect = pygame.Rect(100, 100, 200, 30)

# 点击起始位置附近
e = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(105, 110))
t9.handle_event(e, font, input_rect)
check("点击起始位置", t9.cursor_pos == 0)

# 点击末尾位置附近
t9.set_text('hello')
e = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(290, 110))
t9.handle_event(e, font, input_rect)
check("点击末尾位置", t9.cursor_pos == 5)

print("\n=== 测试 10: 鼠标拖拽选中 ===")
t10 = TextInput('hello world')
input_rect = pygame.Rect(100, 100, 300, 30)

# 点击起始位置
e1 = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(103, 110))
t10.handle_event(e1, font, input_rect)
check("拖拽开始：点击起点", t10.cursor_pos == 0 and t10.has_selection() == False)

# 拖拽移动
e2 = pygame.event.Event(pygame.MOUSEMOTION, pos=(160, 110))
t10.handle_event(e2, font, input_rect)
check("拖拽中：有选中", t10.has_selection() == True)

# 松开鼠标
e3 = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(160, 110))
t10.handle_event(e3, font, input_rect)

# 现在应该有选中了
s, e = t10.get_selection_range()
print(f"  选中范围: ({s}, {e}), 文本: '{t10.text[s:e]}'")
check("拖拽后有选中", s != e)

print("\n=== 测试 11: set_text / clear / 属性 ===")
t11 = TextInput('initial')
t11.set_text('new text')
check("set_text", t11.text == 'new text' and t11.cursor_pos == 8)

t11.clear()
check("clear", t11.text == '' and t11.cursor_pos == 0)

check("has_selection() 空文本无选中", t11.has_selection() == False)

print("\n=== 测试 12: get_display_text 和 get_cursor_offset ===")
t12 = TextInput('hello')
display, visible = t12.get_display_text(font, 200, 'placeholder', True)
check("get_display_text 非空", display == 'hello')

t12.cursor_pos = 3
t12._display_start = 0
offset = t12.get_cursor_offset(font)
check("get_cursor_offset 正确", offset > 0)

# 空文本测试
t12.set_text('')
display, visible = t12.get_display_text(font, 200, 'placeholder', True)
check("空文本显示", display == '')

display, visible = t12.get_display_text(font, 200, 'placeholder', False)
check("空文本非激活显示提示", display == 'placeholder')
check("非激活时光标不可见", visible == False)

print("\n=== 测试 13: get_selection_offsets ===")
t13 = TextInput('hello world')
t13._selection_start = 0
t13._selection_end = 5
t13.cursor_pos = 5
t13._display_start = 0

offsets = t13.get_selection_offsets(font)
check("有选中时返回偏移", offsets is not None)
if offsets:
    s_off, e_off = offsets
    check("选中偏移非零", s_off == 0 and e_off > 0)

t13._selection_start = 5
t13._selection_end = 5
check("无选中时返回 None", t13.get_selection_offsets(font) is None)

print("\n=== 测试 14: 中文字符支持 ===")
t14 = TextInput('你好世界')
t14.cursor_pos = 2
t14._selection_start = 2
t14._selection_end = 2
t14.handle_event(make_key_event(0, '测试'))
check("中文输入", t14.text == '你好测试世界' and t14.cursor_pos == 4)

t14.set_text('你好世界')
t14._selection_start = 0
t14._selection_end = 2
t14.cursor_pos = 2
t14.handle_event(make_key_event(pygame.K_BACKSPACE))
check("选中后 Backspace 删除中文", t14.text == '世界' and t14.cursor_pos == 0)

print("\n" + "=" * 50)
print(f"测试结果: {passed} 通过, {failed} 失败")
print("=" * 50)

if failed == 0:
    print("\n✓ ALL TESTS PASSED!")
else:
    print("\n✗ SOME TESTS FAILED")

pygame.quit()
sys.exit(0 if failed == 0 else 1)
