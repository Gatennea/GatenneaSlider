# -*- coding: utf-8 -*-
"""在真引擎上重放 4 步「四类同步 4-cycle」，生成数字谜题存档 + 宏文件。

序列来自 _s2_4444.log 的 box/delta，经 _replay4.py 还原成引擎口径的
(缝类型, 缝线, 方向, 代表格)。不手写任何 json：存档走 gui._save_to_path()，
宏走 MacroManager.save_macro()。

与 _make_archive.py 的唯一差别是 PLAN（4 步 vs 9 步）和输出文件名。

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
# 来自 _replay4.py 的参数表，逐项对照
PLAN = [
    ('h', 1,  'a', (0, 0),  8, [1, 2, 3, 4, 5, 6, 7, 8]),
    ('v', -1, 's', (0, -2), 4, [1, 2, 5, 6]),
    ('v', 1,  'w', (2, 2),  4, [11, 12, 15, 16]),
    ('h', 1,  'd', (2, -2), 8, [1, 2, 5, 6, 9, 10, 13, 14]),
]

M, N, STEP = 4, 4, 2
BASE = (0, 0)
OUT_NAME = 'num-2-4-4-four-cycle-4.json'
MACRO_NAME = 'four-cycle-442-4steps'


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

    # 四类循环核对
    print('per-class cycle:')
    for L in range(4):
        pts = [(r, c) for r in range(M) for c in range(N) if (r % 2) * 2 + (c % 2) == L]
        line = []
        for p in pts:
            b = block_at(gui, p)
            line.append(f'格{p}={b.number if b else 0}')
        print(f'  类{L}: ' + ' / '.join(line))

    save_dir = os.path.join(os.path.abspath('.'), 'save')
    path = os.path.join(save_dir, OUT_NAME)
    ok = gui._save_to_path(path)
    print('save ->', path, ok)

    macro_dir = os.path.join(os.path.abspath('.'), 'macro')
    mgr = MacroManager(macro_dir)
    macro = Macro(
        name=MACRO_NAME,
        description=('(4,4,2) 四类同步 4-cycle：4 步（实测最短）。'
                     '每个 mod 类各转一圈，四类同时完成，'
                     '比单对 2-swap 的 9 步短一半多。在数字谜题上执行。'),
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
