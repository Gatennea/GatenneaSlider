"""S6 对拍：原版**方形**板型写成模型文件后，规则必须与代码版逐项等价。

为什么要有这个：`models/*.json` 驱动的板型体系一直被"只验证过碎三角"这件事
卡住——碎三角本来就是为这套 schema 设计的，它通过不代表 schema 有表达力。
方形是原版四板型里最硬的一个（无朝向、4 邻接、两条贯穿缝族），它若能表达，
「丢一个 json 就多一个板型」才算有普适性的证据。

对拍口径：**只比几何**。
  1. 还原态的块多边形集合相等；
  2. `legal_moves(1)` 的条数相等；
  3. 每个合法移动执行后的**局面几何集合**相等（这比条数强得多：条数相同
     但走到不同位置是可能的）。
不比较块键与缝族名——键形态 (`(r,c)` vs `(point,orient)`) 与族名本来就允许
不同，比较它们只会测出实现细节差异。

本测试不改运行时：探针文件在 `experiments/model_probe/`，不在 `models/`。
"""

import json
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

sys.path.insert(0, os.path.join(_PROJ, 'experiments'))

_FAILS = []


def check(cond, msg, detail=''):
    if cond:
        print(f'  ok   {msg}')
    else:
        print(f'  FAIL {msg}' + (f'  [{detail}]' if detail else ''))
        _FAILS.append(msg)


def geo(board):
    """局面的几何指纹：块多边形的集合（顺序无关，坐标取到 1e-4）。"""
    return frozenset(
        tuple(sorted((round(x, 4), round(y, 4)) for (x, y)
                     in board.spec.cell_polygon(b.point, b.orient)))
        for b in board.blocks)


def states(board, depth=1):
    """从该局面出发、走 depth 步能到达的全部几何指纹（含自身）。"""
    frontier = {geo(board): board}
    seen = set(frontier)
    for _ in range(depth):
        nxt = {}
        for fp, bd in frontier.items():
            for mv in bd.legal_moves(1):
                after = bd.apply(mv)
                k = geo(after)
                if k not in seen:
                    nxt[k] = after
        seen |= set(nxt)
        frontier = nxt
        if not frontier:
            break
    return seen


def _load(doc):
    from engine.model_loader import load_model
    return load_model(doc, path=None)


def probe_tri(k=6):
    from engine.board import Board
    from engine.registry import make_board

    print(f'\n== 三角 k={k}：文件版 vs 代码版 ==')
    from _gen_model_tri import build as build_tri
    model = _load(build_tri(k))
    b_file = Board(model.spec, model.spec.goal_blocks)
    board_code = make_board('tri', k=k)
    b_code = Board(board_code.spec, board_code.spec.goal_blocks)

    check(len(b_file.blocks) == len(b_code.blocks),
          f'块数相同（{len(b_file.blocks)} / {len(b_code.blocks)}）')
    check(geo(b_file) == geo(b_code), '还原态几何完全一致',
          f'{len(geo(b_file))} vs {len(geo(b_code))} 个不同多边形')

    mf = b_file.legal_moves(1)
    mc = b_code.legal_moves(1)
    check(len(mf) == len(mc), f'legal_moves(1) 条数相同（{len(mf)} / {len(mc)}）')

    sf = states(b_file, depth=1)
    sc = states(b_code, depth=1)
    check(sf == sc,
          f'1 步可达局面集合相等（{len(sf)} / {len(sc)} 个局面）',
          f'仅文件有 {len(sf - sc)} 个、仅代码有 {len(sc - sf)} 个')

    sf2 = states(b_file, depth=2)
    sc2 = states(b_code, depth=2)
    check(sf2 == sc2,
          f'2 步可达局面集合相等（{len(sf2)} / {len(sc2)} 个局面）',
          f'仅文件有 {len(sf2 - sc2)} 个、仅代码有 {len(sc2 - sf2)} 个')


def probe(m, n):
    from engine.board import Board
    from engine.registry import square_spec
    from _gen_model_probe import build_square

    print(f'\n== 方形 {m}×{n}：文件版 vs 代码版 ==')
    model = _load(build_square(m, n))
    b_file = Board(model.spec, model.spec.goal_blocks)
    spec_code = square_spec(m, n)
    b_code = Board(spec_code, spec_code.goal_blocks)

    check(len(b_file.blocks) == len(b_code.blocks),
          f'块数相同（{len(b_file.blocks)} / {len(b_code.blocks)}）')
    check(geo(b_file) == geo(b_code), '还原态几何完全一致',
          f'{len(geo(b_file))} vs {len(geo(b_code))} 个不同多边形')

    mf = b_file.legal_moves(1)
    mc = b_code.legal_moves(1)
    check(len(mf) == len(mc), f'legal_moves(1) 条数相同（{len(mf)} / {len(mc)}）')

    sf = states(b_file, depth=1)
    sc = states(b_code, depth=1)
    check(sf == sc,
          f'1 步可达局面集合相等（{len(sf)} / {len(sc)} 个局面）',
          f'仅文件有 {len(sf - sc)} 个、仅代码有 {len(sc - sf)} 个')

    # 2 步：条数相同但走向不同是可能的，再深一层才抓得住
    sf2 = states(b_file, depth=2)
    sc2 = states(b_code, depth=2)
    check(sf2 == sc2,
          f'2 步可达局面集合相等（{len(sf2)} / {len(sc2)} 个局面）',
          f'仅文件有 {len(sf2 - sc2)} 个、仅代码有 {len(sc2 - sf2)} 个')


def test_probe_files_are_out_of_runtime():
    """探针文件不能落在 models/ 下（否则会被启动扫描注册成真板型）。"""
    print('\n== 探针文件位置 ==')
    probe_dir = os.path.join(_PROJ, 'experiments', 'model_probe')
    check(os.path.isdir(probe_dir), '探针目录存在')
    names = sorted(os.listdir(probe_dir)) if os.path.isdir(probe_dir) else []
    check(bool(names), f'探针文件已生成（{names}）')
    models_dir = os.path.join(_PROJ, 'models')
    models = sorted(os.listdir(models_dir)) if os.path.isdir(models_dir) else []
    probe_json = {n for n in names if n.endswith('.json')}
    model_json = {n for n in models if n.endswith('.json')}
    check(not (probe_json & model_json),
          '探针文件不在 models/ 下（不会被运行时注册）', str(probe_json & model_json))
    # 文件内容与生成器一致（防止手改后忘记重新生成）
    from _gen_model_probe import build_square
    for fname, (m, n) in (('square_4x4.json', (4, 4)),
                          ('square_6x6.json', (6, 6))):
        path = os.path.join(probe_dir, fname)
        if not os.path.exists(path):
            check(False, f'{fname} 存在')
            continue
        with open(path, encoding='utf-8') as f:
            got = json.load(f)
        check(got == build_square(m, n), f'{fname} 与生成器输出一致（未被手改）')
    # 三角探针
    from _gen_model_tri import build as build_tri
    tpath = os.path.join(probe_dir, 'tri_6.json')
    if os.path.exists(tpath):
        with open(tpath, encoding='utf-8') as f:
            got = json.load(f)
        check(got == build_tri(6), 'tri_6.json 与生成器输出一致（未被手改）')
    else:
        check(False, 'tri_6.json 存在')


def main():
    test_probe_files_are_out_of_runtime()
    probe(4, 4)
    probe(6, 6)
    probe_tri(6)
    print()
    if _FAILS:
        print(f'失败 {len(_FAILS)} 项：')
        for m in _FAILS:
            print('  -', m)
        sys.exit(1)
    print('全部通過')


if __name__ == '__main__':
    main()
