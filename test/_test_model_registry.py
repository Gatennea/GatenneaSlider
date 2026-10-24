# -*- coding: utf-8 -*-
"""模型注册表：文件即板型，且失败不静默。

覆盖：
  R1 注册结果       models/*.json 全部登记进 registry
  R2 文件即来源     make_board('shatter') 拿到的 spec 就是文件版
                    （朝向顺序、还原判定、块数、缝族全与文件一致）
  R3 拒绝参数       模型板型不给尺寸参数（`make_board(name, m=4)` 必须报错）
  R4 坏模型不注册   故意写坏一个模型 → 不登记 + errors() 留下原因，
                    且**不回退成方形**（拿不到就 KeyError）
  R5 分榜键         模型名进 puzzle_key 后不与同尺寸矩形混榜
  R6 建局入口       create_puzzle / create_adapter_puzzle 都能按名字建局
  R7 GUI 开局      new_model_puzzle 能开任意模型局，且 _current_kind 认它

跑法：``PYTHONPATH=. python -u test/_test_model_registry.py``
"""
import json
import os
import queue
import shutil
import sys
import tempfile

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

_FAILS = []


def check(cond, label, extra=''):
    tag = 'OK  ' if cond else 'FAIL'
    print(f'[{tag}] {label}' + (f'  （{extra}）' if extra else ''))
    if not cond:
        _FAILS.append(label)


def test_registry():
    print('\n== R1 注册结果 ==')
    from engine import model_registry
    from engine.registry import board_types
    installed = model_registry.loaded()
    check('shatter' in installed and 'shatter_lattice' in installed,
          '两个碎三角模型都已装', f'{sorted(installed)}')
    check(set(installed) <= set(board_types()), '都已进 registry')
    check(model_registry.errors() == (), '安装期无错误',
          f'{model_registry.errors()}')


def test_file_is_source():
    print('\n== R2 板型来源就是文件 ==')
    from engine import model_registry
    from engine.registry import make_board
    from engine.model_loader import load_file
    file_model = load_file(os.path.join(_PROJ, 'models', 'shatter.json'))
    board = make_board('shatter')
    # 不能比 `is`：每次 load_file 都会造一份新 spec（同一份数据、不同对象）。
    # 判据取「还原态逐块相同 + 缝族同名同序 + 朝向同序」——这三样定了，
    # 盘型就是同一个。
    check({(b.point, b.orient) for b in board.spec.goal_blocks}
          == {(b.point, b.orient) for b in file_model.spec.goal_blocks},
          '还原态逐块相同（= 板型来自这个文件）')
    check(tuple(f.name for f in board.spec.seam_families)
          == tuple(f.name for f in file_model.spec.seam_families),
          '缝族同名同序', f'{[f.name for f in board.spec.seam_families]}')
    check(board.spec.orientations == file_model.spec.orientations,
          '朝向顺序 = 文件书写顺序', f'{board.spec.orientations[:4]}…')
    # 顺序是盘型身份的一部分（update_matrix 用它编码快照），必须与代码版一致
    from engine.shatter_geometry import shatter_spec
    check(board.spec.orientations == shatter_spec(full=True).orientations,
          '朝向顺序与代码版一致（旧存档编码不会错位）')
    check(len(board.blocks) == 48 and len(board.legal_moves(1)) == 48,
          '48 块 / 48 条合法移动')
    check(board.is_solved(), '还原态 is_solved() 为真')


def test_reject_params():
    print('\n== R3 模型板型拒绝尺寸参数 ==')
    from engine.registry import make_board
    try:
        make_board('shatter', m=4)
    except TypeError as exc:
        check('不接受参数' in str(exc), '带参数调用明确报错', str(exc)[:40])
    else:
        check(False, '带参数调用明确报错', '（居然接受了）')


def test_bad_model_not_installed():
    print('\n== R4 坏模型不注册、不回退方形 ==')
    from engine import model_registry
    from engine.registry import board_types, make_board
    tmp = tempfile.mkdtemp(prefix='gatenna_bad_')
    try:
        # ① 结构坏：放置重复 → 加载器直接拒
        src = os.path.join(_PROJ, 'models', 'shatter.json')
        doc = json.load(open(src, encoding='utf-8'))
        doc['name'] = 'broken_struct'
        doc['tiles'][0] = dict(doc['tiles'][1])
        json.dump(doc, open(os.path.join(tmp, 'broken_struct.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False)

        # ② 结构合法但**几何重叠**：方形里塞一个用它的三条边拼的三角
        #    （共享 3 个顶点 → 连通 ✓，三角整块在方形内部 → 重叠 ✓）。
        #    这种盘只有 A0 抓得住，是「注册期校验不是摆设」的证据。
        overlap_doc = {
            'schema': 'gatenna.board/1',
            'name': 'broken_overlap',
            'title': '重叠坏盘',
            'basis': [[1, 0], [0, 1]],
            'pos_scale': 2,
            'orientations': {
                'sq': {'shape': 'sq', 'off': [[0, 0], [2, 0], [2, 2], [0, 2]]},
                'tri': {'shape': 'tri', 'off': [[0, 0], [2, 0], [0, 2]]},
            },
            'tiles': [{'p': [0, 0], 'o': 'sq'}, {'p': [0, 0], 'o': 'tri'}],
            'seams': [{'name': 'h', 'coeffs': [0, 1], 'step': [2, 0]}],
            'view': {'rotate': 0, 'mirror': False},
        }
        json.dump(overlap_doc, open(os.path.join(tmp, 'broken_overlap.json'),
                                    'w', encoding='utf-8'), ensure_ascii=False)

        before = set(board_types())
        model_registry.clear_errors()
        fresh = model_registry.install(tmp)
        after = set(board_types())
        errs = ' | '.join(model_registry.errors())

        check('broken_struct' not in after, '结构坏的没进 registry')
        check('broken_overlap' not in after, '几何重叠的没进 registry')
        check(not fresh, 'install 没把任何一个算作已装')
        check('加载失败' in errs, '结构失败原因留下了', errs[:70])
        check('物理公理' in errs and '重叠' in errs,
              '几何失败原因定位到 A0 重叠', errs[:160])
        # 关键：不回退成方形——拿不到就必须报错
        for bad in ('broken_struct', 'broken_overlap'):
            try:
                make_board(bad)
            except KeyError:
                check(True, f'取 {bad} 抛 KeyError（绝不静默换成方形）')
            else:
                check(False, f'取 {bad} 抛 KeyError（绝不静默换成方形）')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_puzzle_key():
    print('\n== R5 分榜键不混榜 ==')
    from puzzle_types import puzzle_key
    check(puzzle_key(2, 4, 4, 'shatter') == '2~shatter',
          '碎三角键保持旧格式', puzzle_key(2, 4, 4, 'shatter'))
    check(puzzle_key(2, 4, 4, 'shatter_lattice') == '2~shatter_lattice',
          '晶格变体有自己的键')
    check(puzzle_key(2, 4, 4, 'shatter') != puzzle_key(2, 4, 4, 'square'),
          '不与同尺寸矩形混榜')


def test_create_puzzle():
    print('\n== R6 建局入口 ==')
    from puzzle_types import create_puzzle
    g = create_puzzle(4, 4, 2, 'shatter')
    check(len(g.blocks) == 48, 'create_puzzle 建出 48 块',
          f'{type(g).__name__}')
    g2 = create_puzzle(4, 4, 1, 'shatter_lattice')
    check(len(g2.blocks) == 48, '晶格变体也是 48 块')
    try:
        create_puzzle(4, 4, 1, 'no_such_model')
    except KeyError as exc:
        check('no_such_model' in str(exc), '未注册模型名明确报错')
    else:
        check(False, '未注册模型名明确报错', '（静默成了方形）')


def test_gui():
    print('\n== R7 GUI 按模型开局 ==')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    from GUI import SliderGUI
    gui = SliderGUI(m=6, n=6, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 5050})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.animation_enabled = False
    ok = gui.new_model_puzzle('shatter_lattice', 2)
    check(ok, 'new_model_puzzle 建局成功')
    check(len(gui.game.blocks) == 48, '48 块')
    check(gui._current_kind() == 'shatter_lattice', '形态键 = 模型名',
          gui._current_kind())
    check(gui._current_puzzle_key() == '2~shatter_lattice', '分榜键正确',
          gui._current_puzzle_key())
    check(not gui.new_model_puzzle('no_such_model', 1),
          '未注册模型开局被拒（不静默换形）')
    # 菜单里应有模型分组，且条目由文件决定
    gui._refresh_puzzle_presets()
    items = gui.puzzle_sub_presets.get('models') or []
    names = {it[4] for it in items if len(it) >= 5}
    check({'shatter', 'shatter_lattice'} <= names, '菜单条目来自模型文件',
          f'{sorted(names)}')


def test_save_roundtrip():
    print('\n== R8 模型局存档：往返逐块一致 / 模型缺失明确报错 ==')
    import random
    from engine.adapter import EngineGame
    from engine.analysis import safe_scramble
    from GUI import SliderGUI

    gui = SliderGUI(m=6, n=6, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 5050})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.animation_enabled = False

    def fingerprint(game):
        return {(b.location[0], b.location[1], b.location[2])
                for b in game.blocks}

    for name in ('shatter', 'shatter_lattice'):
        gui.new_model_puzzle(name, 1)
        solved = fingerprint(gui.game)
        data = gui._build_save_data()
        check(data['puzzle'].get('type') == name, f'{name}：存档 type = 模型名',
              str(data['puzzle'].get('type')))
        check((data['puzzle'].get('model') or {}).get('name') == name,
              f'{name}：存档头带模型身份',
              str(data['puzzle'].get('model')))
        gui.new_puzzle(4, 4, 2)                     # 先切走，避免假通过
        gui._load_save_data(data)
        check(fingerprint(gui.game) == solved,
              f'{name}：还原态往返逐块一致（含朝向）')
        check(gui._current_kind() == name, f'{name}：载入后形态键正确',
              gui._current_kind())

        # 打乱几步再往返：位置与朝向都动了，才是真的有信息量
        gui.new_model_puzzle(name, 1)
        rng = random.Random(20261024)
        final, _path, undo = safe_scramble(gui.game.board, 1, 40, rng)
        check(len(undo) > 0, f'{name}：打乱产出可逆路径（{len(undo)} 步）')
        gui.game = EngineGame(final, kind=name)
        gui.center_map()
        gui.game_history.reset()
        gui.game_history.save_snapshot(gui.game)
        scrambled = fingerprint(gui.game)
        check(scrambled != solved, f'{name}：确实是打乱后的局面')
        data = gui._build_save_data()
        gui.new_puzzle(4, 4, 2)
        gui._load_save_data(data)
        check(fingerprint(gui.game) == scrambled,
              f'{name}：打乱后往返逐块一致（含朝向）')

    # 模型缺失：必须明确报错，绝不回退成方形
    ghost = {'version': 2,
             'puzzle': {'m': 4, 'n': 4, 'step': 1, 'type': 'ghost_model',
                        'model': {'name': 'ghost_model', 'hash': 'x'}},
             'step_count': 0,
             'history': {'history_index': 0,
                         'snapshots': [{'matrix': [[1]], 'bounds':
                                        {'min_row': 0, 'max_row': 0,
                                         'min_col': 0, 'max_col': 0}}]}}
    try:
        gui._load_save_data(ghost)
    except ValueError as exc:
        check('ghost_model' in str(exc), '模型缺失时明确报错并指出模型名',
              str(exc)[:80])
    except KeyError as exc:
        check('ghost_model' in str(exc), '模型缺失时明确报错并指出模型名',
              str(exc)[:80])
    else:
        check(False, '模型缺失时明确报错并指出模型名', '（居然载入成功了）')
    check(gui._current_kind() != 'ghost_model', '载入失败没有留下半个坏局面',
          gui._current_kind())


def main():
    test_registry()
    test_file_is_source()
    test_reject_params()
    test_bad_model_not_installed()
    test_puzzle_key()
    test_create_puzzle()
    test_gui()
    test_save_roundtrip()
    print()
    if _FAILS:
        print(f'失败 {len(_FAILS)} 项：')
        for x in _FAILS:
            print('  -', x)
        return 1
    print('全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
