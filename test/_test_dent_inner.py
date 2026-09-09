# -*- coding: utf-8 -*-
"""
填缺口（dent）內層共軛子自洽測試（headless，無 GUI）

內層契約（2026-09-06 與用戶定名）：
    填「單個 dent」的內層共軛子 = 只調用一次 solve_single_void(couple 模式，
    帶 hole+anchor)。外層 ABCB′A′ 負責 setup / A / 尾段收尾。
    ★ 不得改調 solve_fill_macro 或 solve_multi_void——它們會自主決定處理
      多處洞（矯枉過正），破壞整段共軛操作。

基準局：save/solve_dent1~4.json（GUI 錄製的人解，附 setup/A/B/C/B′/A′ 相位）。
驗證內容（X = 外層 A 結束，條件：原缺口格已變成窗內洞）：
    1) 在 X 只呼叫一次 couple(h=原缺口格, p=同 mod 窗外凸起)；
    2) 宏產物回放後 == 錄製解的「B′ 結束」狀態（即內層整段取代人類 B·C·B′）；
    3) 續播錄製的 A′ 尾段 → 還原。
例 solve_dent2 是已知「外層不足」反例（A 結束洞已包住，但同 mod 凸起全在
窗外另一側推不進），不設斷言、僅印狀態供外層規則歸納。
"""
import json
import sys
sys.path.insert(0, '.')
from solver.ml.fill_macro import (solve_single_void, build_game,
                                  _replay_apply, gcoords, window_of)

# (档名, X=A段结束k, 契约couple(h,p), B′结束k, A′尾段起止k)
CASES = [
    ('solve_dent.json',  3, ((4, 0), (2, 4)),  8, (9, 10)),
    ('solve_dent3.json', 2, ((0, 1), (2, -1)), 5, (6, 7)),
    ('solve_dent4.json', 2, ((1, 0), (3, 4)),  7, (8, 9)),
]
OUTLIER = ('solve_dent2.json', 4, (0, 5))   # 已知外層不足反例


def state_of(data, k):
    s = data['history']['snapshots'][k]
    b = s['bounds']
    return frozenset((b['min_row'] + r, b['min_col'] + c)
                     for r, row in enumerate(s['matrix'])
                     for c, v in enumerate(row) if v)


def replay_human_tail(g, data, start, end, st):
    """回放人类录制尾段：目标块 = 该步 moved_positions[0]（录像原始语义）"""
    for k in range(start, end + 1):
        mi = data['history']['snapshots'][k].get('move_info')
        if not mi:
            return False
        tgt = tuple(mi['moved_positions'][0])
        blk = next((b for b in g.blocks if tuple(b.location) == tgt), None)
        if blk is None:
            return False
        g.opt(mi['gap_type'], mi['gap_line'], blk)
        fin = g.try_move(mi['direction'], mi.get('step', st))
        if not fin:
            return False
        g.commit_move(fin)
    return True


def run():
    failed = 0
    for fname, xk, (h, p), bk, (a1, a2) in CASES:
        data = json.load(open('save/' + fname, encoding='utf-8'))
        m, n, st = data['puzzle']['m'], data['puzzle']['n'], data['puzzle']['step']
        sx = state_of(data, xk)
        _reg, ov, holes, outside = window_of(sx, m, n, st)
        assert h in holes and p in outside, \
            'X=%d 处 couple 不在窗内空位/窗外凸起' % xk
        # ★ 内层契约：整段只调一次单洞 couple
        acts, stats = solve_single_void(sx, m, n, st, hole=h, anchor=p,
                                        keep_partial=True)
        assert acts is not None, fname + ' 内层 couple 失败: %s' % stats
        g = build_game(sx, m, n)
        assert _replay_apply(g, acts, m, n, st)
        ok_mid = gcoords(g) == state_of(data, bk)
        ok_solved = False
        if ok_mid:
            ok_solved = replay_human_tail(g, data, a1, a2, st) and g.is_solved()
        tag = 'PASS' if (ok_mid and ok_solved) else 'FAIL'
        if tag == 'FAIL':
            failed += 1
        print('[%s] %s X=%d couple=%s×%s 内层%d步 -> 中点为B′结束:%s, A′尾段还原:%s'
              % (tag, fname, xk, h, p, len(acts), ok_mid, ok_solved))
    # 已知反例：只记录，不断言
    fname, xk, h0 = OUTLIER
    data = json.load(open('save/' + fname, encoding='utf-8'))
    m, n, st = data['puzzle']['m'], data['puzzle']['n'], data['puzzle']['step']
    sx = state_of(data, xk)
    _reg, ov, holes, outside = window_of(sx, m, n, st)
    print('[INFO] %s 外層不足反例：X=%d 原缺口 %s ∈ holes=%s, '
          '窗外凸起=%s（需更長外層，暫不斷言）'
          % (fname, xk, h0, sorted(holes), sorted(outside)))
    print('ALL PASS' if not failed else 'SOME FAILED')


if __name__ == '__main__':
    run()
