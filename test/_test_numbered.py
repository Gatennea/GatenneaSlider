# -*- coding: utf-8 -*-
"""帶序號滑塊 A2/A3 驗證"""

import os
import sys
sys.path.insert(0, '.')

import pygame
from GUI import SliderGUI
import queue

def main():
    pygame.init()
    q = queue.Queue()
    gui = SliderGUI(6, 6, 2, q)
    gui.new_puzzle(5, 5, 1, numbered=True)

    init_nums = [b.number for b in gui.game.blocks]
    assert all(n is not None for n in init_nums)
    assert init_nums[0] == 1 and init_nums[-1] == 25

    # A2: 移動/打亂不影響序號
    gui._bump_move_session()
    gui.selected_gap = ('h', 0)
    block = next(b for b in gui.game.blocks if b.location == [0, 0])
    gui.game.opt('h', 0, block)
    gui.selected_block = block
    assert gui.move_selected_blocks('d')
    assert [b.number for b in gui.game.blocks] == init_nums

    gui.shuffle_puzzle()
    assert [b.number for b in gui.game.blocks] == init_nums

    # A3: 撤銷/重做（含合併快照）保留編號
    gui.undo()
    assert [b.number for b in gui.game.blocks] == init_nums
    gui.redo()
    assert [b.number for b in gui.game.blocks] == init_nums

    # 存檔往返（臨時文件）
    path = gui._default_save_name()
    before = {tuple(b.location): b.number for b in gui.game.blocks}
    gui._save_to_path(path)
    gui.new_puzzle(3, 3, 1, numbered=True)
    gui._do_load_from_path(path)
    after = {tuple(b.location): b.number for b in gui.game.blocks}
    assert after == before, f"存檔往返編號丟失: {sorted(v for v in after.values() if v)}"
    assert sorted(v for v in after.values() if v) == list(range(1, 26)), "編號集合應為 1..25"
    os.remove(path)

    print("A2/A3 numbered PASS")
    pygame.quit()

if __name__ == '__main__':
    main()
