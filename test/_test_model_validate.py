# -*- coding: utf-8 -*-
"""模型公理校验器（A0–A3）：好模型必须过，坏模型必须被抓。

为什么测试要写这么多「故意写坏」的模型
--------------------------------------
只测「碎三角通过」等于没测——一个永远返回空列表的校验器也能通过。所以每个
公理都要配一个**只坏这一条**的模型，并断言校验器报出的正是那个 code。

A2 的说明：碎三角还原态的 48 条合法移动在几何上确实一次碰撞都没有（实测把
`overlap` 钩子换成恒 False，legal_moves 仍然是 48 条）。所以 A2 在这块盘上
是「验过、无问题」，它的牙齿留给未来手写步长/朝向写错的野模型——本文件用
`_Truth` 原语级测试把这条判定力单独钉住。

跑法：``PYTHONPATH=. python -u test/_test_model_validate.py``
"""
import copy
import dataclasses
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from engine.board import Board, SeamFamily
from engine.model_loader import LoadedModel, load_file, load_model
from engine.model_validate import _Truth, summarize, validate, _axiom_seam_lines

MODEL_PATH = os.path.join(_PROJ, 'models', 'shatter.json')
_FAILS = []


def check(cond, label, extra=''):
    tag = 'OK  ' if cond else 'FAIL'
    print(f'[{tag}] {label}' + (f'  （{extra}）' if extra else ''))
    if not cond:
        _FAILS.append(label)


def codes(problems, level='error'):
    return {p.code for p in problems if p.level == level}


def has(problems, code, keyword=''):
    for p in problems:
        if p.code == code and p.level == 'error' and keyword in (p.msg + p.where):
            return True
    return False


def rebuild(model, **changes):
    """换掉 BoardSpec 的某些字段（frozen dataclass），保留 doc。"""
    return LoadedModel(dataclasses.replace(model.spec, **changes),
                       model.doc, model.path)


def tiny_doc(base_doc, tiles, orients):
    """用碎三角的几何造一个只含指定块的小模型。"""
    doc = copy.deepcopy(base_doc)
    doc['name'] = 'tiny'
    doc['title'] = '测试小盘'
    doc['orientations'] = {k: v for k, v in doc['orientations'].items()
                           if k in orients}
    doc['tiles'] = tiles
    return doc


# ----------------------------------------------------------------------
def test_good_model(model):
    print('\n== T1 碎三角：四条公理全过 ==')
    ps = validate(model, deep=True)
    e, w = summarize(ps)
    check(e == 0 and w == 0, 'A0–A3 零错误零警告', f'{e} 错 / {w} 警')
    for p in ps:
        print('   ', p)

    # A1 的独立结论必须与引擎缝线表逐族一致（validate 内部已对拍，
    # 这里再从外面确认一次数量，防止对拍代码自己写歪）
    truth = _Truth(model.doc)
    board = Board(model.spec, model.spec.goal_blocks)
    want = {'h': 1, 'd30': 3, 'd60': 1, 'v': 3, 'd120': 1, 'd150': 3}
    got = {}
    for fam in model.spec.seam_families:
        rep, _split, _span = _axiom_seam_lines(truth, board.keys, fam)
        got[fam.name] = len(rep)
    check(got == want, '逐族真缝条数与代码实现一致', f'{got}')


def test_a0_overlap(_model):
    print('\n== T2 A0：放置真的重叠必须被抓 ==')
    # 碎三角造不出「重叠但仍连通」的坏盘（平移 1/3 边长就必然断开，而
    # BoardSpec.__post_init__ 会先挡下不连通的盘）。所以手工造一个：
    # 方形里塞一个用它的三条边拼成的三角 —— 共享 3 个顶点（连通 ✓），
    # 三角整块落在方形内部（重叠 ✓）。
    doc = {
        'schema': 'gatenna.board/1',
        'name': 'overlap_probe',
        'title': '重叠探针',
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
    m = load_model(doc, path=None)           # 加载器只管结构，不管几何
    ps = validate(m, deep=False)
    check(has(ps, 'A0', '重叠'), 'A0 报重叠并指出是哪两块',
          next((p.msg for p in ps if p.code == 'A0'), '（没报）'))


def test_a0_count(model):
    print('\n== T3 A0：块数对不上必须被抓 ==')
    # 删一块但保持剩余连通，否则 BoardSpec 自己就会先拒绝（那是另一道闸）
    truth = _Truth(model.doc)
    goal = list(model.spec.goal_blocks)
    dropped = None
    for i in range(len(goal) - 1, -1, -1):
        rest = goal[:i] + goal[i + 1:]
        if len(truth.components([(b.point, b.orient) for b in rest])) == 1:
            dropped = goal[i]
            goal = rest
            break
    check(dropped is not None, '找到一个「删掉后仍连通」的块', f'{dropped!r}')
    m = rebuild(model, goal_blocks=tuple(goal))
    ps = validate(m, deep=False)
    check(has(ps, 'A0', '块数') or has(ps, 'A0', '48'), 'A0 报块数不符',
          next((p.msg for p in ps if p.code == 'A0'), '（没报）'))


def test_a0_disconnect(model):
    print('\n== T4 不连通盘面：在构造期就被拒（早于 A0）==')
    far = tiny_doc(model.doc,
                   [{'p': [2, 4], 'o': '12'}, {'p': [13, 31], 'o': '8'}],
                   {'12', '8'})
    try:
        load_model(far, path=None)
    except ValueError as exc:
        check('连通' in str(exc), 'BoardSpec 直接拒绝不连通还原态', str(exc))
    else:
        check(False, 'BoardSpec 直接拒绝不连通还原态', '（居然构造成功了）')


def test_a1_fake_seam(model):
    print('\n== T5/T6/T7 A1：多报 / 漏报 / 报劈块缝 ==')
    board = Board(model.spec, model.spec.goal_blocks)
    fam = next(f for f in model.spec.seam_families if f.name == 'h')
    real = model.spec.seam_lines

    # 多报：多给一条几何上不存在的线
    def extra_seam(b, f):
        got = real(b, f)
        return got + ((999, 998),) if f.name == 'h' else got
    ps = validate(rebuild(model, seam_lines=extra_seam), deep=False)
    check(has(ps, 'A1', '多报'), 'A1 报多报假缝',
          next((p.msg for p in ps if p.code == 'A1'), '（没报）'))

    # 漏报：少给一条真缝
    def miss_seam(b, f):
        got = real(b, f)
        return got[1:] if f.name == 'h' else got
    ps = validate(rebuild(model, seam_lines=miss_seam), deep=False)
    check(has(ps, 'A1', '漏报'), 'A1 报漏报真缝',
          next((p.msg for p in ps if p.code == 'A1'), '（没报）'))

    # 报劈块缝：把「局部贴边、别处穿块」的 t 也当成真缝
    truth = _Truth(model.doc)
    split, split_fam = {}, None
    for cand in model.spec.seam_families:
        _rep, sp, _span = _axiom_seam_lines(truth, board.keys, cand)
        if sp:
            split, split_fam = sp, cand
            break
    check(bool(split), '碎三角确实存在「有共边但会穿块」的假缝 t',
          f'{sorted(split)}（族 {getattr(split_fam, "name", None)}）')
    bad_t = sorted(split)[0]

    def split_seam(b, f):
        got = real(b, f)
        if f.name != split_fam.name:
            return got
        return got + ((bad_t, bad_t - 1),)
    ps = validate(rebuild(model, seam_lines=split_seam), deep=False)
    check(has(ps, 'A1', '劈开'), 'A1 报该缝会劈开块',
          next((p.msg for p in ps if p.code == 'A1'), '（没报）'))


def test_a1_dead_board(model):
    print('\n== T8 A1/A2：单块盘面（永冻）必须被拒 ==')
    one = tiny_doc(model.doc, [{'p': [2, 4], 'o': '12'}], {'12'})
    m = load_model(one, path=None)
    ps = validate(m, deep=False)
    check(has(ps, 'A1', '可用'), 'A1 报「所有缝族都没有可用的缝」')
    check(has(ps, 'A2', '冻死'), 'A2 报「一条合法移动都没有」')


def test_a3_switch(model):
    print('\n== T9 A3：deep 开关真的在控制 A3 ==')
    shallow = validate(model, deep=False)
    deep = validate(model, deep=True)
    check(not any(p.code == 'A3' for p in shallow), 'deep=False 不做 A3')
    check(not any(p.code == 'A3' for p in deep), 'deep=True 时 A3 全过')


def test_truth_primitives(model):
    print('\n== T10 独立几何原语：能判重叠、能判断开 ==')
    truth = _Truth(model.doc)
    board = Board(model.spec, model.spec.goal_blocks)
    keys = sorted(board.keys)

    check(truth.self_overlap(keys) is None, '还原态自重叠 = 无')
    check(len(truth.components(keys)) == 1, '还原态单一连通')

    # 把一块挪 1/3 个边长 → 必与邻居正面积重叠
    victim = keys[0]
    moved = ((victim[0][0] + 1, victim[0][1]), victim[1])
    rest = [k for k in keys if k != victim]
    found = None
    for k in rest:
        if truth.overlaps([moved], [k]) is not None:
            found = k
            break
    check(found is not None, '平移 1/3 边长后能查出与某块重叠', f'撞到 {found!r}')

    # 挪到很远处 → 断开
    far = (((victim[0][0] + 999, victim[0][1] + 999), victim[1]),)
    check(not truth.connected(list(far) + rest), '远离主体后判为断开')

    # 相切（共边）不算重叠
    neigh = truth.edge_pairs(keys)[0][1][1]
    check(truth.overlaps([victim], [neigh]) is None,
          '共边的邻块不算重叠（相切 ≠ 碰撞）')


def main():
    model = load_file(MODEL_PATH)
    test_good_model(model)
    test_a0_overlap(model)
    test_a0_count(model)
    test_a0_disconnect(model)
    test_a1_fake_seam(model)
    test_a1_dead_board(model)
    test_a3_switch(model)
    test_truth_primitives(model)

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
