"""三维（立方）第 5 步：历史 / 撤销重做 / 存档读回（§54）。

验收口径（与方案第 5 步一致）：
- 快照是**无损**的：三维局面存 [r,c,d,gid] 键表，不拿二维矩阵凑数；
- 撤销/重做真的换局面（逐格比对），步数跟着历史累计值走；
- 存档写 ``type: cubic`` + ``depth``，读回后局面、步数、形态全对上；
- 边界（无步可撤/可重做）给明确提示，不静默；
- 二维路径不受影响（方形存读回 + 撤销照旧）。
"""
import json
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from gui.file_ops import StaleCubicSave  # noqa: E402
from history import validate_snapshot  # noqa: E402
from _cubic_test_util import internal_seam_point  # noqa: E402

FAILED = []
PASSED = [0]


def check(ok, label, extra=None):
    if ok:
        PASSED[0] += 1
        print(f"  ok: {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL: {label}" + (f"  <- {extra}" if extra is not None else ''))


def make_gui(cfg, tag=''):
    g = SliderGUI(m=4, n=4, step=1)
    g.config_dir = cfg
    g.config_path = os.path.join(cfg, f'config{tag}.json')
    g.temp_history_path = os.path.join(cfg, f'temp{tag}.json')
    g.tutorial_active = False
    pygame.display.set_mode((g.screen_width, g.screen_height))
    g.screen = pygame.display.get_surface()
    return g


def click(g, pos):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    g.handle_events()
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))
    g.handle_events()


def cells(g):
    return sorted(tuple(int(v) for v in b.location) for b in g.game.blocks)


def select_front(g):
    """右键选可见的内部墙 → 左键点块，选出一组（为推做准备）。"""
    g._cubic_view(0)
    g.draw_cubic_board()
    pt, seam, face = internal_seam_point(g, families=('r', 'd'))
    if pt is None or seam is None:
        return False
    g._cubic_seam_click(*pt)       # 右键选缝
    click(g, pt)                   # 左键选块
    return bool(g.selected_gap) and any(b.be_opted for b in g.game.blocks)


def main():
    cfg = tempfile.mkdtemp()

    print('=' * 60)
    print('A. 新局快照：无损键表，不碰二维矩阵')
    g = make_gui(cfg)
    g._cubic_camera_prefs = {}
    g.new_cubic_puzzle(3, 3, 3, 1)
    g.cubic_gap = 0.12
    h = g.game_history
    check(len(h.history) == 1 and h.history_index == 0, '开局一条参考快照')
    snap = h.history[0]
    check(snap.get('cubic') is True, '三维快照带 cubic 标记')
    st = snap.get('engine_state')
    check(isinstance(st, dict) and len(st.get('keys') or []) == 27,
          f'无损键表记全 27 块（{len((st or {}).get("keys") or [])}）')
    check(all(len(item) == 4 for item in (st or {}).get('keys') or []),
          '每条键是 [r,c,d,gid] 四元')
    check(snap.get('matrix') == [], '三维快照不写二维矩阵（矩阵没有深度）')
    check(validate_snapshot(snap, 'cubic') is None, 'validate_snapshot(kind=cubic) 通过')

    print('B. 推一步 → 撤销 → 重做：逐格比对')
    ok_sel = select_front(g)
    check(ok_sel, '双击选出一组（为推做准备）')
    before = cells(g)
    moved = g._cubic_push_letter('C')
    check(moved, '推一步成功')
    after = cells(g)
    check(before != after, '推一步真的挪了块')
    check(len(h.history) == 2 and h.history_index == 1, '多出一条快照并停在它上面')
    check(g.step_count == 1, f'步数 1（{g.step_count}）')
    g.undo()
    check(cells(g) == before, '撤销回到推之前（逐格一致）')
    check(g.step_count == 0 and h.history_index == 0, '撤销后步数 0、指针回 0')
    check(g.selected_gap is None, '撤销后清掉选中（不带着旧选中继续推）')
    g.redo()
    check(cells(g) == after, '重做回到推之后（逐格一致）')
    check(g.step_count == 1, '重做后步数 1')

    print('C. 边界：无步可撤 / 无步可重做都给提示')
    g.undo()
    g.undo()
    check(h.history_index == 0 and g.macro_notify_msg == '没有可撤销的步骤',
          f'撤到起点：提示「没有可撤销的步骤」（{g.macro_notify_msg}）')
    g.redo()
    g.redo()
    check(h.history_index == 1 and g.macro_notify_msg == '没有可重做的步骤',
          f'重做到终点：提示「没有可重做的步骤」（{g.macro_notify_msg}）')

    print('D. 多步 + 跳步：跳到第 0 步回到初始局面')
    for _l in ('c', 'C', 'c'):
        select_front(g)
        g._cubic_push_letter(_l)
    check(h.history_index >= 2, f'多步后历史指针前进（{h.history_index}）')
    total = g.step_count
    g.jump_to_history_index(0)
    check(cells(g) == before, '跳回第 0 步 = 开局局面')
    check(g.step_count == 0, '跳回第 0 步后步数归零')
    g.jump_to_history_index(h.history_index)
    g.jump_to_history_index(len(h.history) - 1)
    check(g.step_count == total, f'跳到最后一步步数回到 {total}（{g.step_count}）')

    print('E. 存档写读：type=cubic + depth，读回局面/步数/形态全对上')
    data = g._build_save_data()
    check(data['version'] == 2, f"version 2（{data['version']}）")
    check(data['puzzle'].get('type') == 'cubic', 'puzzle.type = cubic')
    check(data['puzzle'].get('depth') == 3, f"depth 3（{data['puzzle'].get('depth')}）")
    snaps = data['history']['snapshots']
    check(len(snaps) == len(h.history), f'快照条数与内存一致（{len(snaps)}）')
    check(all(('matrix' not in s) and s.get('cubic') for s in snaps),
          '每条落盘快照都不含 matrix、带 cubic')
    check(all(validate_snapshot(s, 'cubic') is None for s in snaps),
          '落盘快照逐条通过校验')
    data['checksum'] = None  # 校验和按落盘口径由 _compute_checksum 重算，测试只看结构
    path = os.path.join(cfg, 'cubic_save.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    saved_cells = cells(g)
    saved_steps = g.step_count

    g2 = make_gui(cfg, tag='2')
    g2._cubic_camera_prefs = {}
    with open(path, encoding='utf-8') as f:
        g2._load_save_data(json.load(f))
    check(g2.cubic_mode is True, '读回后进三维形态')
    check(g2.game.kind == 'cubic' and g2.game.depth == 3, '逻辑对象是三维 3 层')
    check(cells(g2) == saved_cells, '读回局面逐格一致')
    check(g2.step_count == saved_steps, f'读回步数 {saved_steps}（{g2.step_count}）')
    check(g2.current_m == 3 and g2.current_n == 3, '尺寸字段一致')
    check(1e-6 < g2.cubic_gap < 1.0, f'读回后拆分仍是正的（{g2.cubic_gap}）')
    check(g2.show_virtual_keyboard is True, '读回后键盘面板打开（三维唯一鼠标入口）')
    g2.undo()
    check(cells(g2) != saved_cells, '读回后还能继续撤销（换回上一步局面）')
    g2.redo()
    check(cells(g2) == saved_cells, '读回后重做回到存档局面')

    print('E2. 真走一遍文件：_save_to_path → _do_load_from_path（Ctrl+S / 打开）')
    real_path = os.path.join(cfg, 'cubic_roundtrip.json')
    ok_save = g._save_to_path(real_path)
    check(ok_save and os.path.exists(real_path),
          f'存档真的写到盘上（{os.path.basename(real_path)}）')
    raw = json.load(open(real_path, encoding='utf-8'))
    check(raw.get('checksum') is not None, '写盘文件带校验和')
    g3 = make_gui(cfg, tag='3')
    g3._cubic_camera_prefs = {}
    g3._do_load_from_path(real_path)
    check(g3.cubic_mode is True and g3.game.depth == 3, '真实文件读回仍是三维 3 层')
    check(cells(g3) == saved_cells, '真实文件读回局面逐格一致')
    check(g3.step_count == saved_steps, f'真实文件读回步数 {saved_steps}（{g3.step_count}）')
    check('已打开' in (g3.macro_notify_msg or ''),
          f'打开有可见提示（{g3.macro_notify_msg}）')

    print('F. 坏档拒绝：键表缺项/维度不对都判失败')
    bad = {'cubic': True, 'engine_state': {'keys': [[0, 0, 0]]}}
    try:
        validate_snapshot(bad, 'cubic')
        check(False, '三维快照条目只有 3 元应判失败')
    except ValueError:
        check(True, '三维快照条目只有 3 元判失败')
    bad2 = {'cubic': True}
    try:
        validate_snapshot(bad2, 'cubic')
        check(False, '缺 engine_state 应判失败')
    except ValueError:
        check(True, '缺 engine_state 判失败')
    g2b = make_gui(cfg, tag='3')
    bad_save = {'version': 2, 'puzzle': {'m': 3, 'n': 3, 'step': 1, 'type': 'cubic'},
                'step_count': 0,
                'history': {'history_index': 0, 'snapshots': [{'cubic': True}]}}
    try:
        g2b._load_save_data(bad_save)
        check(False, '三维存档缺 depth 应拒绝')
    except ValueError as exc:
        check('depth' in str(exc), f'缺 depth 明确报错（{exc}）')
    except StaleCubicSave as exc:
        check('depth' in str(exc), f'缺 depth 走「旧档安静回落」（{exc}）')

    print('G. 二维不受影响：方形存读回 + 撤销照旧')
    sq_cfg = os.path.join(cfg, 'sq')
    os.makedirs(sq_cfg, exist_ok=True)
    s = make_gui(sq_cfg, tag='sq')
    s.new_cubic_puzzle(3, 3, 3, 1)
    s.new_puzzle(4, 4, 1)
    sq_cells = [tuple(int(v) for v in b.location) for b in s.game.blocks]
    check(not s.cubic_mode, '二维局 cubic_mode 关闭')
    check(s.game_history.history and s.game_history.history[-1].get('matrix') != [],
          '二维快照照旧写矩阵')
    sq_data = s._build_save_data()
    check('type' not in sq_data['puzzle'], '方形存档仍不写 type（v1 口径）')
    sq_path = os.path.join(sq_cfg, 'sq.json')
    with open(sq_path, 'w', encoding='utf-8') as f:
        json.dump(sq_data, f)
    s2 = make_gui(sq_cfg, tag='sq2')
    with open(sq_path, encoding='utf-8') as f:
        s2._load_save_data(json.load(f))
    check(not s2.cubic_mode, '方形读回后不是三维')
    check(sorted(tuple(int(v) for v in b.location) for b in s2.game.blocks)
          == sorted(sq_cells), '方形读回局面一致')

    print('=' * 60)
    if FAILED:
        print(f'结果：{len(FAILED)} 项失败（{PASSED[0]} 项通过）')
        for f_ in FAILED:
            print('  -', f_)
        return 1
    print(f'结果：全部通过（{PASSED[0]} 项通过，0 项失败）')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
