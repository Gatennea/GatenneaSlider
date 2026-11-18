"""三维宏（C7 第 4 阶段）：录制/持久化/转换/回放四处形态无关。

只测一条最小闭环：在 3×3×3 打乱局里录一步 → 撤销回到起点 →
用同一宏步骤在新基准执行，块必须真的沿同一轴走一步。
"""
import copy
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from macro.macro import Macro, MacroManager, MacroStep  # noqa: E402

FAILED = []
PASSED = [0]


def check(ok, label, extra=None):
    if ok:
        PASSED[0] += 1
        print(f"  ok: {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL: {label}" + (f"  <- {extra}" if extra is not None else ''))


def make_gui():
    cfg = tempfile.mkdtemp(prefix='cubic_macro_')
    g = SliderGUI(m=4, n=4, step=1)
    g.config_dir = cfg
    g.config_path = os.path.join(cfg, 'config.json')
    g.temp_history_path = os.path.join(cfg, 'temp_history.json')
    g.tutorial_active = False
    pygame.display.set_mode((g.screen_width, g.screen_height))
    g.screen = pygame.display.get_surface()
    g._cubic_camera_prefs = {}
    g.animation_enabled = False
    return g


def pick_front_group(g):
    g._cubic_view(0)
    g.draw_cubic_board()
    faces = g._cubic_scene.get('faces') or []
    for f in reversed(faces):
        pt = (int(sum(p[0] for p in f['pts']) / 4.0),
              int(sum(p[1] for p in f['pts']) / 4.0))
        g._cubic_seam_click(*pt)
        if g.selected_gap:
            g._cubic_click(*pt)
            if g.selected_block is not None:
                return
    raise RuntimeError('no front seam/group')


def main():
    print('A. 三维宏步骤模型：相对坐标按轴转换')
    step = MacroStep('r', 0, 'above', 'C', 1, [0, 1, 0], kind='cubic')
    ops = MacroManager.convert_to_absolute(
        step, 2, 1, 1, 1, base_depth=1)
    check(len(ops) == 1, '生成一条绝对操作')
    check(ops and ops[0]['gap_line'] == 2, 'r 轴偏移落在 base_r 上')
    check(ops and ops[0].get('rep_cell') == [2, 2, 1], 'rep 三轴都加基准')
    check(ops and ops[0].get('kind') == 'cubic', '操作保留 cubic 形态')
    m = Macro('m', base_point=[1, 2, 3], steps=[step], kind='cubic')
    m2 = Macro.from_dict(m.to_dict())
    check(m2.kind == 'cubic' and m2.steps[0].kind == 'cubic',
          'to_dict/from_dict 保留三维形态')
    old = Macro.from_dict({'name': 'old', 'base_point': [0, 0],
                           'steps': [{'gap_type': 'h', 'gap_line_rel': 1,
                                      'side': 'above', 'direction': 'w',
                                      'step': 1}]})
    check(old.kind == 'square' and old.steps[0].kind == 'square',
          '老宏缺 kind 时默认 square')

    print('B. GUI 录制一步：自动写 cubic kind / 三轴 rep')
    g = make_gui()
    g.new_cubic_puzzle(3, 3, 3, 1)
    g.cubic_gap = 0.12
    g.shuffle_puzzle(confirm=False)
    pick_front_group(g)
    chosen = None
    for letter in ('c', 'C', 'd', 'D', 'r', 'R'):
        fp, _reason = g.game.try_move_ex(letter, g.current_step)
        if fp:
            chosen = letter
            break
    check(chosen is not None, f'找到可推方向（{chosen}）')
    base = list(g.selected_block.location[:3])
    g.macro_recording = True
    g.macro_recording_steps = []
    g.macro_record_base_point = base
    before = copy.deepcopy(g.game)
    moved = g.move_selected_blocks(chosen)
    check(moved, '三维移动成功')
    recorded_after = sorted(tuple(b.location[:3]) for b in g.game.blocks)
    check(len(g.macro_recording_steps) == 1, '录制了 1 步')
    rec = g.macro_recording_steps[0]
    check(rec.kind == 'cubic', '录制步骤 kind=cubic')
    check(rec.gap_type == g.selected_gap[0], '录制缝隙族与当前一致')
    check(rec.direction == chosen, '录制的方向字母保留大小写')
    check(rec.rep_cell_rel is not None and len(rec.rep_cell_rel) == 3,
          f'rep 是三轴相对坐标（{rec.rep_cell_rel}）')
    check(rec.side in ('above', 'below'), '侧别统一 above/below')
    g.macro_recording = False
    g.macro_recording_steps = []

    print('C. 撤销回起点后回放：同一步真的走同轴')
    g.undo()
    before_set = sorted(tuple(b.location[:3]) for b in before.blocks)
    undo_set = sorted(tuple(b.location[:3]) for b in g.game.blocks)
    check(undo_set == before_set,
          f'撤销恢复初始位置（{undo_set[:3]} vs {before_set[:3]}）')
    op = MacroManager.convert_to_absolute(
        rec, base[0], base[1], g.current_step, 1, base_depth=base[2])[0]
    start = {tuple(b.location[:3]) for b in g.game.blocks}
    g.macro_exec_ops = [op]
    g.macro_exec_index = 0
    g.macro_executing = True
    g.macro_selecting_base = False
    g._execute_next_macro_step()
    check(not g.macro_executing, '一步宏执行完并收尾')
    after = sorted(tuple(b.location[:3]) for b in g.game.blocks)
    check(after != start, '回放确实移动了块')
    check(after == recorded_after,
          f'回放结果与录制结果一致（{after[:2]} vs {recorded_after[:2]}）')

    print()
    print(f'{PASSED[0]} passed, {len(FAILED)} failed')
    if FAILED:
        for f in FAILED:
            print('  -', f)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
