# -*- coding: utf-8 -*-
r"""
标题栏存档路径 + 修改星号 + 未存档（2a）headless 冒烟测试（dummy video，不开窗口）

验证点：
    1. 初始无路径 → 标题含「未存檔」
    2. 移动后无路径 → 仍显示「未存檔」（未存档不画星号）
    3. 另存为 → 标题含绝对路径且无星号
    4. 再移动 → 路径末尾加「 *」
    5. 保存 → 星号消失
    6. undo / redo → 星号出现
    7. 重新打开存档 → 星号消失
    8. 动画提交路径（commit_animation 移动分支）→ 星号出现
    9. _update_window_title 仅在标题变化时调用 set_caption（缓存标题）

运行：
    D:\python\python.exe 測試\_test_file_title.py
"""

import os
import sys
import tempfile

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

import pygame
from game import Block

ok_all = True


def _check(name, cond, detail=''):
    global ok_all
    ok_all = ok_all and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


def _setup_moveable(gui):
    """5×5 版面铺满第 0~3 行（4 行 × 5 列）。

    存在有效横缝 line 1（0 <= 1 < 3），可把上半（第 0~1 行）沿缝隙向右平移
    step 格且保持单连通——这是真正改变局面的移动。
    （不能用「整片棋形一起平移」那种无效移动：形状不变，已被 GUI 禁止。）
    """
    coords = {(r, c) for r in range(4) for c in range(5)}
    gui.game.blocks = [Block(list(p)) for p in sorted(coords)]
    gui.game.update_matrix()
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    gui.center_map()
    gui.selected_gap = None
    gui.selected_block = None


def _do_move(gui):
    """选横缝 line 1 的上半（第 0~1 行）向右滑动 step 格。"""
    gui.selected_gap = ('h', 1)
    block = next((b for b in gui.game.blocks if b.location == [0, 0]), None)
    if block is None:
        return False
    gui.game.opt('h', 1, block)
    return bool(gui.move_selected_blocks('d'))


def main():
    from GUI import SliderGUI
    gui = SliderGUI(m=5, n=5, step=2)
    gui.animation_enabled = False
    gui._readonly = False          # 屏蔽 temp_history 可能残留的只读标记
    gui.save_readonly_flag = False
    gui.prevent_overwrite_flag = False   # 屏蔽 config 残留的「防止覆盖」开关
    pygame.display.set_caption('')  # 清空，确保下面从空标题开始
    gui._window_title = ''
    gui.new_puzzle(5, 5, 2)
    _setup_moveable(gui)

    # ---- 1. 初始未存档 ----
    gui._update_window_title()
    _check('初始标题含"未存檔"', '未存檔' in gui._window_title, gui._window_title)

    # ---- 2. 移动后（无路径）仍显示未存檔 ----
    assert _do_move(gui)
    _check('无路径移动后仍"未存檔"', '未存檔' in gui._window_title and '*' not in gui._window_title,
           gui._window_title)

    # ---- 3. 另存为 ----
    tmpdir = tempfile.mkdtemp(prefix='slider_title_')
    save_path = os.path.join(tmpdir, 't.json')
    gui._save_to_path(save_path)
    _check('另存为后标题含绝对路径', save_path in gui._window_title, gui._window_title)
    _check('另存为后无星号', '*' not in gui._window_title, gui._window_title)

    # ---- 4. 再移动（重建可动板面） → 星号 ----
    _setup_moveable(gui)
    assert _do_move(gui)
    _check('移动后星号出现', '*' in gui._window_title, gui._window_title)

    # ---- 5. 保存 → 星号消失 ----
    gui.save_to_file()
    _check('保存后星号消失', '*' not in gui._window_title, gui._window_title)

    # ---- 6. undo / redo → 星号出现 ----
    gui.undo()
    _check('undo 后星号出现', '*' in gui._window_title, gui._window_title)
    gui.redo()
    _check('redo 后星号出现', '*' in gui._window_title, gui._window_title)

    # ---- 7. 重新打开存档 → 星号消失 ----
    gui._do_load_from_path(save_path)
    _check('重开存档后无星号', '*' not in gui._window_title, gui._window_title)
    _check('重开存档标题含路径', save_path in gui._window_title, gui._window_title)

    # ---- 8. 动画提交路径（commit_animation 移动分支）→ 星号 ----
    version_before = gui._board_version
    gui.anim_blocks = [Block([1, 0])]
    gui.anim_end_pos = [[0, 0]]
    gui.anim_start_pos = [[1, 0]]
    gui._undo_redo_type = None
    gui._pending_move_info = {
        'gap_type': 'h', 'gap_line': 0, 'direction': 'w', 'step': 1,
        'moved_positions': [[1, 0]],
    }
    gui.commit_animation()
    _check('动画提交路径版本+1', gui._board_version == version_before + 1,
           f'before={version_before} after={gui._board_version}')
    _check('动画提交路径星号出现', '*' in gui._window_title, gui._window_title)

    # ---- 9. set_caption 仅在标题变化时调用（缓存） ----
    shots = []

    def spy_caption(title):
        shots.append(title)
        orig_caption(title)

    orig_caption = pygame.display.set_caption
    pygame.display.set_caption = spy_caption
    try:
        gui._update_window_title()          # 标题未变 → 不调用
        gui._mark_file_dirty()              # 版本变但仍是星号态 → 标题串不变 → 不调用
        gui._update_window_title()
        _check('标题未变时不重复 set_caption', len(shots) == 0, f'shots={len(shots)}')
        gui._reset_file_dirty()             # 标题变化（星号→干净） → 调用一次
        _check('标题变化时 set_caption 一次', len(shots) == 1, f'shots={len(shots)}')
    finally:
        pygame.display.set_caption = orig_caption

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    print('\n' + ('ALL PASS' if ok_all else 'SOME FAILED'))
    sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()