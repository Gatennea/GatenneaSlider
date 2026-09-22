# -*- coding: utf-8 -*-
r"""
历史快照合并（同一次选中连续移动只存一个矩阵快照）测试 — headless

验证点：
    1. GameHistory：同 session_key 的连续移动并入末条快照（steps/step_total/moves）
    2. 换 session_key / session_key=None → 另起快照（不合并）
    3. 撤销/重做粒度 = 每步（合并段首次撤销时惰性拆成「一步一条」），
       step_count 取快照累计步数
    4. 合成动作：delta = 各步位移之和；expand_snapshot_moves 还原中间态矩阵
    5. 存档往返：moves/steps/step_total 落盘并载回，步数由 step_total 恢复
    6. GUI 端到端：同一次选中连按两次方向键 → 只多 1 条快照；撤销按步退回
    7. 宏/求解器播放（macro_executing=True）不合并

运行：
    D:\python\python.exe test\_test_history_merge.py
"""

import os
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

from game import Block, SliderMatrix                      # noqa: E402
from history import (GameHistory, expand_snapshot_moves,  # noqa: E402
                     snapshot_cells, snapshot_numbers)

ok_all = True


def _check(name, cond, detail=''):
    global ok_all
    ok_all = ok_all and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


def _move(direction, step, moved, gap='h', line=1):
    return {'gap_type': gap, 'gap_line': line, 'direction': direction,
            'step': step, 'moved_positions': [list(p) for p in moved]}


def _set_cells(g, cells):
    g.blocks = [Block(list(c)) for c in sorted(cells)]
    g.update_matrix()


def _set_numbered(g, cell_num):
    """按 {坐标: 编号} 布块（带序號谜题）"""
    g.blocks = []
    for cell, num in sorted(cell_num.items()):
        b = Block(list(cell))
        b.number = num
        g.blocks.append(b)
    g.update_matrix()


def _block_numbers(g) -> dict:
    return {tuple(b.location): b.number for b in g.blocks}


# ---------------------------------------------------------------------------
# 1~5. GameHistory 纯逻辑
# ---------------------------------------------------------------------------
def test_history_unit():
    g = SliderMatrix(3, 3)
    base = {(1, 0), (1, 1), (2, 0), (2, 1)}
    s1 = base | {(0, 0), (0, 1)}
    s2 = base | {(0, -1), (0, 0)}
    s3 = base | {(0, -2), (0, -1)}
    mv1 = _move('a', 1, [(0, 1), (0, 2)])
    mv2 = _move('a', 1, [(0, 0), (0, 1)])
    mv3 = _move('a', 1, [(0, -1), (0, 0)])

    h = GameHistory()
    _set_cells(g, base)
    h.save_snapshot(g)                                     # 参考态
    _check('参考态 1 条 / 0 步', len(h.history) == 1 and h.current_step_total() == 0)

    # ---- 1. 同一会话 3 步 → 1 条快照 ----
    _set_cells(g, s1)
    h.save_snapshot(g, mv1, session_key=7)
    _set_cells(g, s2)
    h.save_snapshot(g, mv2, session_key=7)
    _set_cells(g, s3)
    h.save_snapshot(g, mv3, session_key=7)
    _check('同会话 3 步合并为 1 条', len(h.history) == 2,
           f'n={len(h.history)}')
    snap = h.history[-1]
    _check('steps=3', snap['steps'] == 3, str(snap['steps']))
    _check('step_total=3', snap['step_total'] == 3, str(snap['step_total']))
    _check('moves 长度 3', len(snap['moves']) == 3, str(len(snap['moves'])))
    _check('矩阵为末态', snapshot_cells(snap) == frozenset(s3), '')
    _check('step_total_at(1)=3', h.step_total_at(1) == 3,
           str(h.step_total_at(1)))

    # ---- 4. 合成动作与逐步展开 ----
    composed = snap['move_info']
    _check('合成 delta = 各步位移之和', composed.get('delta') == [0, -3],
           str(composed.get('delta')))
    _check('合成 merged=3', composed.get('merged') == 3,
           str(composed.get('merged')))
    expanded = expand_snapshot_moves(h.history[0], snap)
    posts = [frozenset(snapshot_cells(p)) for _pre, p, _mv in expanded]
    _check('展开为 3 步', len(expanded) == 3, str(len(expanded)))
    _check('展开中间态与逐步矩阵一致',
           posts == [frozenset(s1), frozenset(s2), frozenset(s3)], str(posts))
    _check('展开首步动作前 = 段起点',
           frozenset(snapshot_cells(expanded[0][0])) == frozenset(base), '')

    # ---- 2. 换会话 / None 不合并 ----
    s4 = s3 | {(1, 2)}
    _set_cells(g, s4)
    h.save_snapshot(g, _move('d', 1, [(0, -2), (0, -1)]), session_key=8)
    _check('换会话另起 1 条', len(h.history) == 3 and h.history[-1]['steps'] == 1,
           f'n={len(h.history)} steps={h.history[-1]["steps"]}')
    _set_cells(g, s4 | {(0, 3)})
    h.save_snapshot(g, _move('d', 1, [(0, -1), (0, 0)]), session_key=None)
    _set_cells(g, s4 | {(0, 3), (0, 4)})
    h.save_snapshot(g, _move('d', 1, [(0, 0), (0, 1)]), session_key=None)
    _check('session_key=None 不合并', len(h.history) == 5,
           f'n={len(h.history)}')
    _check('None 快照 steps 各为 1',
           h.history[3]['steps'] == 1 and h.history[4]['steps'] == 1, '')
    # 3（合并段）+ 1 + 1 + 1 = 6
    _check('step_total 单调累计', h.step_total_at(4) == 6,
           str(h.step_total_at(4)))

    # ---- 3. 撤销/重做粒度 = 整段 ----
    hi_before = h.history_index
    h.undo(g)
    _check('撤销退回整段（索引 -1）', h.history_index == hi_before - 1,
           f'{hi_before}->{h.history_index}')
    _check('撤销后步数 = 段前累计', h.current_step_total() == 5,
           str(h.current_step_total()))
    _check('撤销后矩阵 = 段前矩阵',
           snapshot_cells(h.history[h.history_index]) == frozenset(s4 | {(0, 3)}), '')
    h.redo(g)
    _check('重做后步数 = 6', h.current_step_total() == 6,
           str(h.current_step_total()))

    # ---- 3b. 逐步撤销：合并段惰性拆成「一步一条」 ----
    h.history_index = 1                    # 回到 3 步合并段末
    n_before = len(h.history)
    h.undo(g)
    _check('撤销合并段：该段被拆开', len(h.history) == n_before + 2,
           f'n={len(h.history)}')
    _check('撤销一步后步数=2', h.current_step_total() == 2,
           str(h.current_step_total()))
    _check('撤销一步后矩阵 = 第 2 步末态',
           snapshot_cells(h.history[h.history_index]) == frozenset(s2), '')
    h.undo(g)
    _check('再撤销一步步数=1', h.current_step_total() == 1,
           str(h.current_step_total()))
    _check('再撤销一步矩阵 = 第 1 步末态',
           snapshot_cells(h.history[h.history_index]) == frozenset(s1), '')
    h.undo(g)
    _check('撤到段首步数=0', h.current_step_total() == 0,
           str(h.current_step_total()))
    _check('撤到段首矩阵 = 段起点',
           snapshot_cells(h.history[h.history_index]) == frozenset(base), '')
    h.redo(g)
    _check('重做一步回到第 1 步末态', h.current_step_total() == 1
           and snapshot_cells(h.history[h.history_index]) == frozenset(s1), '')


# ---------------------------------------------------------------------------
# 6~7. GUI 端到端
# ---------------------------------------------------------------------------
def test_gui_end_to_end():
    from GUI import SliderGUI
    gui = SliderGUI(m=3, n=3, step=1)
    # 构造时可能从上一次会话恢复 step，这里强制回 1
    gui.current_step = 1
    gui.animation_enabled = False
    gui._readonly = False
    gui.save_readonly_flag = False
    if getattr(gui, 'mi_mode', False) or getattr(gui, 'triangle_mode', False):
        # 构造时会从 config/temp_history.json 恢复上次会话，那里可能是三角/
        # 米字格存档（棋子是三坐标的）。本测试要方形棋：必须先切回去，
        # 否则 update_matrix 会按三坐标解包方形棋子而抛 IndexError
        gui.new_puzzle(3, 3, 1)

    # 3×3 去掉 (0,0)：选中 h 缝 1 的连通组后可连按两次 'a'（第三次会断开）
    start = {(0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)}
    _set_cells(gui.game, start)
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    gui.step_count = 0
    gui.center_map()

    # 玩家点击缝隙 + 点击方块（= 一次选中）
    gui._bump_move_session()
    gui.selected_gap = ('h', 1)
    block = next(b for b in gui.game.blocks if b.location == [0, 1])
    gui.game.opt('h', 1, block)
    gui.selected_block = block

    moved1 = gui.move_selected_blocks('a')
    moved2 = gui.move_selected_blocks('a')
    _check('同一次选中可连移两步', moved1 and moved2,
           f'{moved1}/{moved2}')
    _check('历史只多 1 条快照', len(gui.game_history.history) == 2,
           f'n={len(gui.game_history.history)}')
    _check('该快照 steps=2', gui.game_history.history[-1]['steps'] == 2,
           str(gui.game_history.history[-1]['steps']))
    _check('step_count=2', gui.step_count == 2, str(gui.step_count))
    merged_cells = frozenset(tuple(b.location) for b in gui.game.blocks)

    # ---- 5. 存档往返 ----
    data = gui._build_save_data()
    snap_json = data['history']['snapshots'][-1]
    _check('落盘含 moves/steps/step_total',
           len(snap_json.get('moves', [])) == 2
           and snap_json.get('steps') == 2
           and snap_json.get('step_total') == 2,
           f"{snap_json.get('steps')}/{snap_json.get('step_total')}")
    gui._load_save_data(data)
    _check('载回后仍 1 条合并快照',
           len(gui.game_history.history) == 2
           and gui.game_history.history[-1]['steps'] == 2, '')
    _check('载回后 step_count=2', gui.step_count == 2, str(gui.step_count))
    _check('载回后矩阵一致',
           frozenset(tuple(b.location) for b in gui.game.blocks) == merged_cells,
           '')
    _check('载回后不承接旧会话（session_key=None）',
           gui.game_history.history[-1]['session_key'] is None, '')

    # ---- 逐步撤销（合并段惰性拆成单步）----
    gui.undo()
    _check('撤销一步 step_count=1', gui.step_count == 1, str(gui.step_count))
    _check('撤销一步后不在起点',
           frozenset(tuple(b.location) for b in gui.game.blocks)
           != frozenset(start), '')
    gui.undo()
    _check('再撤销一步回到起点',
           frozenset(tuple(b.location) for b in gui.game.blocks)
           == frozenset(start), '')
    _check('撤销后 step_count=0', gui.step_count == 0, str(gui.step_count))
    gui.redo()
    _check('重做一步 step_count=1', gui.step_count == 1, str(gui.step_count))
    gui.redo()
    _check('重做整段回来',
           frozenset(tuple(b.location) for b in gui.game.blocks) == merged_cells,
           '')
    _check('重做后 step_count=2', gui.step_count == 2, str(gui.step_count))

    # ---- 7. 宏播放不合并 ----
    gui.macro_executing = True
    _check('宏播放时 merge key = None', gui._move_merge_key() is None, '')
    gui.macro_executing = False
    _check('非宏播放时 merge key 为会话号',
           gui._move_merge_key() == gui._move_session_id, '')
    # 标注录制中也不合并（history 与录制步需一一对应）
    gui._ann_recording = True
    _check('标注录制时 merge key = None', gui._move_merge_key() is None, '')
    gui._ann_recording = False
    # 选中变化 → 会话号前进
    sid = gui._move_session_id
    gui._bump_move_session()
    _check('选中变化后会话号 +1', gui._move_session_id == sid + 1, '')


# ---------------------------------------------------------------------------
# 8. 带序号：合并快照同步 numbers，逐步撤销的拆分也必须带 numbers
#    （否则 restore_snapshot 重建出的块全部 number=None → 数字消失、无法还原）
# ---------------------------------------------------------------------------
def test_numbered_history():
    st0 = {(0, 0): 1, (0, 1): 2, (0, 2): 3,
           (1, 0): 4, (1, 1): 5, (1, 2): 6,
           (2, 0): 7, (2, 1): 8, (2, 2): 9}
    # 选中 h 缝 1 上方一行，连按两次 'a'（左移）
    st1 = {(0, -1): 1, (0, 0): 2, (0, 1): 3,
           (1, 0): 4, (1, 1): 5, (1, 2): 6,
           (2, 0): 7, (2, 1): 8, (2, 2): 9}
    st2 = {(0, -2): 1, (0, -1): 2, (0, 0): 3,
           (1, 0): 4, (1, 1): 5, (1, 2): 6,
           (2, 0): 7, (2, 1): 8, (2, 2): 9}
    mv1 = _move('a', 1, [(0, 0), (0, 1), (0, 2)])
    mv2 = _move('a', 1, [(0, -1), (0, 0), (0, 1)])

    g = SliderMatrix(3, 3)
    h = GameHistory()
    _set_numbered(g, st0)
    h.save_snapshot(g)
    _check('参考态快照带 numbers', bool(h.history[0].get('numbers')), '')
    _set_numbered(g, st1)
    h.save_snapshot(g, mv1, session_key=5)
    _set_numbered(g, st2)
    h.save_snapshot(g, mv2, session_key=5)

    snap = h.history[-1]
    _check('合并快照带 numbers', bool(snap.get('numbers')), '')
    _check('合并快照编号 = 末态', snapshot_numbers(snap) == st2,
           str(sorted(snapshot_numbers(snap).items())))
    expanded = expand_snapshot_moves(h.history[0], snap)
    posts = [snapshot_numbers(p) for _pre, p, _mv in expanded]
    _check('展开中间态编号随块移动（不换号）', posts == [st1, st2],
           str([sorted(p.items()) for p in posts]))

    # ---- 逐步撤销：合并段惰性拆成单步，拆分出的快照必须带 numbers ----
    h.history_index = 1
    n_before = len(h.history)
    h.undo(g)
    _check('拆分后条数 = 原条数 + 1', len(h.history) == n_before + 1,
           f'n={len(h.history)}')
    _check('撤销一步后编号不丢（= 第 1 步末态）', _block_numbers(g) == st1,
           str(sorted(_block_numbers(g).items())))
    h.undo(g)
    _check('撤到起点编号归位', _block_numbers(g) == st0,
           str(sorted(_block_numbers(g).items())))
    h.redo(g)
    _check('重做一步编号不丢', _block_numbers(g) == st1, '')
    h.redo(g)
    _check('重做回末态编号不丢', _block_numbers(g) == st2, '')


def main():
    print('A. GameHistory 合并逻辑')
    test_history_unit()
    print('\nB. GUI 端到端')
    test_gui_end_to_end()
    print('\nC. 带序号历史（合并快照的 numbers 传递）')
    test_numbered_history()
    print('\n' + ('ALL PASS' if ok_all else 'SOME FAILED'))
    return 0 if ok_all else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
