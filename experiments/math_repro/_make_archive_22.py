# -*- coding: utf-8 -*-
"""在真引擎上重放 7 步「两个对换」，生成数字谜题存档 + 宏文件。

序列来自 _s2_3cyc.log 的 box/delta，经 _replay3.py 还原成引擎口径。
只动 4 个块：(1 9)(2 10)，跨两个 mod 类各一对换，其余 12 块不动。

cwd 必须是主仓根（E:\\program_project\\other\\wkbddtest\\GatenneaSlider）。
"""

import os
import queue
import sys

sys.path.insert(0, os.path.abspath('.'))

import pygame

from GUI import SliderGUI
from macro.macro import Macro, MacroStep, MacroManager

# (gap_type, line, letter, 片代表格, 片块数, 该片上的标签)
PLAN = [
    ('h', 0,  'a', (0, 0),   4, [1, 2, 3, 4]),
    ('v', -1, 's', (0, -2),  2, [1, 2]),
    ('h', 1,  'd', (0, 0),   6, [3, 4, 5, 6, 7, 8]),
    ('v', 1,  'w', (2, -2),  6, [1, 2, 9, 10, 13, 14]),
    ('h', 0,  'd', (0, -2),  6, [1, 2, 3, 4, 9, 10]),
    ('v', 1,  's', (0, 0),   4, [1, 2, 13, 14]),
    ('h', 1,  'a', (0, 2),   8, [3, 4, 5, 6, 7, 8, 9, 10]),
]

M, N, STEP = 4, 4, 2
BASE = (0, 0)
OUT_NAME = 'num-2-4-4-double-swap-7.json'
MACRO_NAME = 'double-swap-442-7steps'


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
    pygame.init()
    q = queue.Queue()
    gui = SliderGUI(6, 6, STEP, q)
    gui.new_puzzle(M, N, STEP, numbered=True)
    gui.animation_enabled = False
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    gui.step_count = 0

    print('start:')
    for row in grid(gui):
        print('  ' + ' '.join(f'{v:3d}' for v in row))

    macro_steps = []
    for i, (gt, line, letter, rep, n_exp, labels_exp) in enumerate(PLAN, 1):
        blk = block_at(gui, rep)
        if blk is None:
            print(f'step {i}: FAIL — no block at {rep}')
            return 1
        gui.selected_gap = (gt, line)
        gui.selected_block = blk
        gui.game.opt(gt, line, blk)
        opted = [b for b in gui.game.blocks if b.be_opted]
        if len(opted) != n_exp:
            print(f'step {i}: FAIL — opted {len(opted)} != expected {n_exp}')
            print('   opted locs:', sorted(tuple(b.location) for b in opted))
            return 1
        nums = sorted(b.number for b in opted)
        if nums != sorted(labels_exp):
            print(f'step {i}: WARN labels {nums} != {sorted(labels_exp)}')

        row_rel = line - BASE[0] if gt == 'h' else line - BASE[1]
        side = 'above' if (rep[0] <= line if gt == 'h' else rep[1] <= line) else 'below'
        macro_steps.append(MacroStep(
            gap_type=gt,
            gap_line_rel=row_rel,
            side=side,
            direction=letter,
            step=STEP,
            rep_cell_rel=[rep[0] - BASE[0], rep[1] - BASE[1]],
            kind='numbered',
        ))

        gui._bump_move_session()
        ok = gui.move_selected_blocks(letter, STEP)
        if not ok:
            print(f'step {i}: FAIL move — reason={getattr(gui, "_move_fail_reason", None)}')
            return 1
        print(f'step {i}: {gt}_{line} {letter} opted={len(opted)} OK')
        for row in grid(gui):
            print('    ' + ' '.join(f'{v:3d}' for v in row))

    print()
    print('final labels:')
    for row in grid(gui):
        print('  ' + ' '.join(f'{v:3d}' for v in row))
    print('step_count:', gui.step_count, 'snapshots:', len(gui.game_history.history))

    nums = sorted(b.number for b in gui.game.blocks)
    print('numbers 1..16 intact:', nums == list(range(1, M * N + 1)))

    home = {(r, c): r * N + c + 1 for r in range(M) for c in range(N)}
    off = []
    for b in gui.game.blocks:
        want = home[tuple(b.location)]
        if b.number != want:
            off.append((tuple(b.location), b.number, want))
    print('blocks not on their home number:', off)
    print('moved blocks:', len(off))

    save_dir = os.path.join(os.path.abspath('.'), 'save')
    path = os.path.join(save_dir, OUT_NAME)
    ok = gui._save_to_path(path)
    print('save ->', path, ok)

    macro_dir = os.path.join(os.path.abspath('.'), 'macro')
    mgr = MacroManager(macro_dir)
    macro = Macro(
        name=MACRO_NAME,
        description=('(4,4,2) 双对换 (2,2)：7 步，D<=9 最短奇置换。'
                     '只动 4 个块：(1 9)(2 10)，跨两类各一对换，其余 12 块不动。'
                     '比 9 步单对换便宜两次，是「一次动四块」的最优形态。'),
        recorded_step=STEP,
        base_point=[BASE[0], BASE[1]],
        steps=macro_steps,
        kind='numbered',
    )
    mgr.save_macro(macro)
    print('macro ->', os.path.join(macro_dir, MACRO_NAME + '.json'))

    gui2 = SliderGUI(6, 6, STEP, queue.Queue())
    gui2._do_load_from_path(path)
    print('reload ok, step_count:', gui2.step_count, 'blocks:', len(gui2.game.blocks))
    print('reload grid:')
    for row in grid(gui2):
        print('  ' + ' '.join(f'{v:3d}' for v in row))

    pygame.quit()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
