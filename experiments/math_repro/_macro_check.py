# -*- coding: utf-8 -*-
"""把刚存的宏回放一遍，验证它自带就能复现同一终态。

走宏功能自己的 convert_to_absolute：相对步骤 -> 绝对 op，再喂引擎。
"""

import json
import io
import os
import queue
import sys

sys.path.insert(0, os.path.abspath('.'))

import pygame

from GUI import SliderGUI
from macro.macro import Macro, MacroManager

M, N, STEP = 4, 4, 2
MACRO_PATH = r'E:\program_project\other\wkbddtest\GatenneaSlider\macro\two-swap-442-9steps.json'


def block_at(gui, rc):
    for b in gui.game.blocks:
        if tuple(b.location) == tuple(rc):
            return b
    return None


def grid(gui):
    rows = []
    for r in range(M):
        row = []
        for c in range(N):
            b = block_at(gui, (r, c))
            row.append(b.number if b and b.number is not None else 0)
        rows.append(row)
    return rows


def main():
    data = json.load(io.open(MACRO_PATH, encoding='utf-8'))
    macro = Macro.from_dict(data)
    print('macro:', macro.name, 'kind:', macro.kind, 'steps:', macro.step_count,
          'recorded_step:', macro.recorded_step, 'base:', macro.base_point)
    comp, factor, reason = macro.check_step_compatibility(STEP)
    print('step compatible:', comp, 'factor:', factor, reason)

    pygame.init()
    gui = SliderGUI(6, 6, STEP, queue.Queue())
    gui.new_puzzle(M, N, STEP, numbered=True)
    gui.animation_enabled = False
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    gui.step_count = 0

    print('start:')
    for row in grid(gui):
        print('  ' + ' '.join(f'{v:3d}' for v in row))

    for i, st in enumerate(macro.steps, 1):
        ops = MacroManager.convert_to_absolute(
            st, macro.base_point[0], macro.base_point[1], STEP, factor, 0)
        print(f'step {i}: {st.gap_type}{st.gap_line_rel:+d} side={st.side} '
              f'dir={st.direction} rep={st.rep_cell_rel} -> ops={len(ops)}')
        for op in ops:
            rep = op.get('rep_cell')
            blk = block_at(gui, rep) if rep else None
            if blk is None:
                print(f'   FAIL no block at rep={rep}; op={op}')
                return 1
            gui.selected_gap = (op['gap_type'], op['gap_line'])
            gui.selected_block = blk
            gui.game.opt(op['gap_type'], op['gap_line'], blk)
            n = sum(1 for b in gui.game.blocks if b.be_opted)
            gui._bump_move_session()
            ok = gui.move_selected_blocks(op['direction'], op['step'])
            print(f'   {op["gap_type"]}_{op["gap_line"]} {op["direction"]} opted={n} ok={ok}')
            if not ok:
                print('   reason:', getattr(gui, '_move_fail_reason', None))
                return 1

    print()
    print('macro-replay final:')
    for row in grid(gui):
        print('  ' + ' '.join(f'{v:3d}' for v in row))
    home = {(r, c): r * N + c + 1 for r in range(M) for c in range(N)}
    off = [(tuple(b.location), b.number, home[tuple(b.location)])
           for b in gui.game.blocks if b.number != home[tuple(b.location)]]
    print('off-home:', off)
    pygame.quit()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
