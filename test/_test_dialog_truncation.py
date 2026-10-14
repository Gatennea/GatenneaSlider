# -*- coding: utf-8 -*-
"""无头验证文件对话框截断 bug 的修复。

旧 bug：draw() 里路径超宽时直接改 self.current_dir（每帧啃掉 4 字符），
导致含中文的长路径（save/反例存档）被啃坏，_confirm 用坏路径拼出
非法文件路径 → open() FileNotFoundError →「未找到文件」。

验证步骤（SDL dummy 无头）：
  1. show() 打开真实目录 save\反例存档（含中文的长路径）；
  2. draw() 若干帧后 current_dir 必须原样不变；
  3. 选中真实存档 → _confirm() → 拼出的 result 必须存在且可 open。

用法：
  D:\\python\\python.exe test\\test_dialog_truncation.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame  # noqa: E402

pygame.init()
screen = pygame.display.set_mode((900, 700))

from gui.dialogs import PygameFileDialog  # noqa: E402

TARGET_DIR = str(ROOT / 'save' / '反例存档')
TARGET_NAME = '反例-3_3_2-2.json'


def main():
    # 用足够大的字号确保路径渲染超宽——旧 bug（draw 啃 current_dir）会触发的场景
    font = pygame.font.Font(None, 32)
    colors = {k: (200, 200, 200) for k in (
        'dialog_bg', 'dialog_border', 'dialog_title', 'input_bg', 'dialog_text',
        'menu_selected', 'button_hover', 'button_bg', 'input_active', 'input_text')}
    d = PygameFileDialog(screen, font, font, font, colors)
    d.show(mode='open', title='打开', initial_dir=TARGET_DIR, extensions=['json'])
    assert d.current_dir == TARGET_DIR

    # 条件 0：该路径在对话框可用宽度下确实超宽（旧 bug 会被触发的场景）
    max_w = d.up_btn.left - d.dialog_rect.x - 20
    raw_w = font.render(d.current_dir, True, (150, 150, 150)).get_width()
    print(f'路径渲染宽度 {raw_w}px / 可用 {max_w}px  超宽={raw_w > max_w}')
    assert raw_w > max_w, '测试字号未触发超宽，无法覆盖旧 bug 场景'

    # 条件 0b：复现旧逻辑（截断写回 current_dir）确实会啃坏路径
    old = d.current_dir
    w = font.render(old, True, (150, 150, 150)).get_width()
    while w > max_w and len(old) > 10:
        old = '...' + old[4:]
        w = font.render(old, True, (150, 150, 150)).get_width()
    assert old != TARGET_DIR, '旧逻辑未复现啃坏？'
    print(f'旧逻辑会把路径改坏为: {old}')

    # 条件 1：draw 多帧后 current_dir 不被改坏
    for _ in range(5):
        d.draw()
    assert d.current_dir == TARGET_DIR, f'current_dir 被改坏: {d.current_dir}'
    print('✓ draw() 不再修改 current_dir')

    # 条件 2：选中真实文件 → 确认 → 路径有效且可读
    idx = next(i for i, (name, is_dir) in enumerate(d.file_list)
               if not is_dir and name == TARGET_NAME)
    d.selected_index = idx
    d._confirm()
    assert d.result, '对话框未给出结果'
    assert d.result == os.path.join(TARGET_DIR, TARGET_NAME), d.result
    with open(d.result, 'r', encoding='utf-8') as f:
        head = f.read(20)
    print(f'✓ 选中→确定→打开成功: {d.result}')
    print(f'  文件头: {head[:16]}...')
    print('\n全部通过：截断 bug 已修复，反例存档可从对话框正常打开')
    return 0


if __name__ == '__main__':
    sys.exit(main())
