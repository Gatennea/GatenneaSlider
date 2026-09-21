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
    # 關閉動畫：移動/撤銷重做走立即提交路徑，斷言才真正落到 game 狀態
    gui.animation_enabled = False

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

    # A3b: 合併快照逐步撤銷/重做時編號不丟
    #      （惰性拆分必須帶 numbers，否則 restore_snapshot 重建的塊
    #       全部 number=None → 數字消失、is_solved 永不成立、無法還原）
    gui.new_puzzle(5, 5, 1, numbered=True)
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    gui.step_count = 0
    gui._bump_move_session()
    gui.selected_gap = ('h', 1)
    block = next(b for b in gui.game.blocks if b.location == [0, 0])
    gui.game.opt('h', 1, block)
    gui.selected_block = block
    assert gui.move_selected_blocks('a') and gui.move_selected_blocks('a')
    snap = gui.game_history.history[-1]
    assert snap['steps'] == 2, f"合併快照 steps={snap['steps']}"
    assert snap.get('numbers'), '合併快照必須帶 numbers'
    assert sorted(b.number for b in gui.game.blocks) == list(range(1, 26))

    gui.undo()                      # 合併段被拆開，回到第 1 步末態
    assert all(b.number is not None for b in gui.game.blocks), '逐步撤銷後編號丟失'
    gui.undo()                      # 回到起點（還原態）
    assert all(b.number is not None for b in gui.game.blocks), '撤銷後編號丟失'
    assert {tuple(b.location): b.number for b in gui.game.blocks} == \
        {(r, c): r * 5 + c + 1 for r in range(5) for c in range(5)}, '撤到起點編號應歸位'
    assert gui.is_solved(), '撤到起點後應判定為已還原'
    gui.redo()
    assert all(b.number is not None for b in gui.game.blocks), '逐步重做後編號丟失'
    gui.redo()
    assert sorted(b.number for b in gui.game.blocks) == list(range(1, 26))
    assert gui.step_count == 2, f"重做後 step_count={gui.step_count}"

    # 自動存檔名帶 -num 段（自動命名也要能區分形態）
    assert '-num-' in gui._default_save_name(), gui._default_save_name()

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
