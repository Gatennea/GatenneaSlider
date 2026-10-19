# -*- coding: utf-8 -*-
"""复现 _test_numbered_p2 失败段：撤销后 {location: number} 未完全恢复"""
import os, sys
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pygame
pygame.init()
from GUI import SliderGUI

gui = SliderGUI()
gui.new_puzzle(4, 4, 2, numbered=True)
gui.shuffle_puzzle()
before = {tuple(b.location): b.number for b in gui.game.blocks}
print('before: n=%d, numbers none=%d' % (len(before), sum(1 for v in before.values() if v is None)))

moved = False
bounds = gui.game.matrix_bounds
for gap_type in ('h', 'v'):
    axis = 0 if gap_type == 'h' else 1
    for line in range(bounds['min_row'] if gap_type == 'h' else bounds['min_col'],
                      (bounds['max_row'] if gap_type == 'h' else bounds['max_col']) + 1):
        gui.selected_gap = (gap_type, line)
        for b in gui.game.blocks:
            gui.game.opt(gap_type, line, b)
            if not any(x.be_opted for x in gui.game.blocks):
                continue
            gui.selected_block = b
            for d in ('w', 's', 'a', 'd'):
                if gui.move_selected_blocks(d):
                    moved = True
                    break
            if moved:
                break
        if moved:
            break
    if moved:
        break
print('moved:', moved)
print('history before save: len=%d index=%d' % (len(gui.game_history.history), gui.game_history.history_index))
gui.game_history.save_snapshot(gui.game, session_key=None, move_info=None)
print('history after save : len=%d index=%d' % (len(gui.game_history.history), gui.game_history.history_index))
gui.undo()
print('undo called')
print('history after undo: len=%d index=%d' % (len(gui.game_history.history), gui.game_history.history_index))
restored = {tuple(b.location): b.number for b in gui.game.blocks}
print('restored: n=%d, numbers none=%d' % (len(restored), sum(1 for v in restored.values() if v is None)))
diff = {k: (before.get(k), restored.get(k)) for k in set(before) | set(restored)
        if before.get(k) != restored.get(k)}
print('diff entries:', len(diff))
for k, v in list(diff.items())[:12]:
    print('   ', k, 'before=', v[0], 'restored=', v[1])
print('game.numbered:', getattr(gui.game, 'numbered', 'ABSENT'))
# history[0] 到底是 shuffle 前还是 shuffle 后？
snap0 = gui.game_history.history[0]
m0 = snap0['matrix']
b0 = snap0['bounds']
pos0 = {(b0['min_row'] + i, b0['min_col'] + j): v
        for i, row in enumerate(m0) for j, v in enumerate(row) if v}
print('history[0] occupied cells:', len(pos0), ' sample:', dict(list(pos0.items())[:6]))
print('before sample            :', dict(list(before.items())[:6]))
print('history[0] == before ?   :', pos0 == before)
print('history[0] bounds:', b0, ' before rows/cols span:',
      (min(k[0] for k in before), max(k[0] for k in before)),
      (min(k[1] for k in before), max(k[1] for k in before)))
pygame.quit()
