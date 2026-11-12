# -*- coding: utf-8 -*-
"""护栏 #49①：_rigid_fill 复用模块级 _union_connected + 补 time_cap。

复用审计结论：_rigid_fill 自己用满 DFS `_connected_ml(rest | mku)` 逐案判
连通，而 _convoy_fill 早已抽出自带记忆化的三级判定 `_union_connected`。两宏
的连通判据本应同一套——本次把 `_union_connected` 提升为模块级，两宏共用，并
给 _rigid_fill 补 `time_cap`（老签名只有 max_nodes，大盘盲 DFS 无墙钟上限会
白烧时间）。

本测试锁（行为级反向验证风格）：
  T1 复用：_rigid_fill 在已知可解盘面（board44 对齐后）仍解出、引擎回放全解；
  T2 复用无回归：把共享 `_union_connected` 临时换成满 DFS `_connected_ml`，
     同盘仍得有效解（证明提速没改判据）；
  T3 复用被真正执行：spy 统计 _rigid_fill 调用 `_union_connected` 次数 > 0；
  T4 time_cap 接线：伪造墙钟到点，_rigid_fill 立即 (None, 0) 收；
  T5 time_cap=None（老调用）同盘仍能解、不抛错（行为不变）。

跑法：D:/python/python.exe -u test/_test_rigid_fill_shared_conn.py
"""
import os
import sys
import time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import solver.ml.fill_macro as fm  # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + ('  %s' % detail if detail else ''))
    if not ok:
        FAILS.append(name)
    return ok


def board44():
    """用户给的验收盘面：4×4 窗口，洞横 2 格在第 2 行，凸起横 2 格在第 4 行右。"""
    return frozenset({(0, 0), (0, 1), (0, 2), (0, 3),
                      (1, 0), (1, 3),
                      (2, 0), (2, 1), (2, 2), (2, 3),
                      (3, 0), (3, 1), (3, 2), (3, 3), (3, 4), (3, 5)})


def align_board44():
    c4 = board44()
    H4 = frozenset({(1, 1), (1, 2)})
    P4 = frozenset({(3, 4), (3, 5)})
    acts, cur2, P2 = fm._align_rigid(c4, 4, 4, 2, H4, P4)
    return cur2, H4, P2


def rigid_solves(cur2, H4, P2, **kw):
    racts, used = fm._rigid_fill(cur2, 4, 4, 2, H4, P2, max_nodes=600, **kw)
    if not racts:
        return None, used
    g = fm.build_game(cur2, 4, 4)
    for a5 in racts:
        fm._capture_apply(g, a5, 2)
    return (racts if g.is_solved() else None), used


def test_rigid_still_solves():
    cur2, H4, P2 = align_board44()
    racts, used = rigid_solves(cur2, H4, P2)
    check('T1 _rigid_fill 对齐后盘面仍解出且引擎回放全解',
          racts is not None, 'used=%s' % used)


def test_rigid_equiv_to_full_dfs():
    cur2, H4, P2 = align_board44()
    racts, used = rigid_solves(cur2, H4, P2)
    orig = fm._union_connected

    def full_dfs(rest, mv_k, ca, ib):
        return fm._connected_ml(rest | mv_k)
    fm._union_connected = full_dfs
    try:
        racts2, _ = rigid_solves(cur2, H4, P2)
    finally:
        fm._union_connected = orig
    check('T2 共享判据换成满 DFS 仍得有效解（提速未改判据）',
          racts2 is not None,
          'acts1=%s acts2=%s' % (len(racts or []), len(racts2 or [])))


def test_rigid_calls_shared():
    cur2, H4, P2 = align_board44()
    orig = fm._union_connected
    cnt = {'n': 0}

    def spy(rest, mv_k, ca, ib):
        cnt['n'] += 1
        return orig(rest, mv_k, ca, ib)
    fm._union_connected = spy
    try:
        fm._rigid_fill(cur2, 4, 4, 2, H4, P2, max_nodes=600)
    finally:
        fm._union_connected = orig
    check('T3 _rigid_fill 实际调用共享 _union_connected（次数>0）',
          cnt['n'] > 0, 'calls=%d' % cnt['n'])


def test_rigid_time_cap_prunes():
    cur2, H4, P2 = align_board44()
    real = _time.time

    # 伪造墙钟：第一次调用（算 _deadline）返回 0，之后每次跳 1000s，
    # 使 dfs 入口处的 time.time() 必然 >= _deadline，触发到点剪枝。
    _st = {'n': 0}

    def fake():
        v = _st['n']
        _st['n'] += 1000
        return float(v)
    _time.time = fake
    try:
        racts, used = fm._rigid_fill(cur2, 4, 4, 2, H4, P2,
                                     max_nodes=600, time_cap=1.0)
    finally:
        _time.time = real
    # 第一层 dfs 即判墙钟过期返回，节点数 0、无解
    check('T4 time_cap 到点提前收（used==0）',
          racts is None and used == 0, 'used=%s' % used)


def test_rigid_default_no_cap():
    cur2, H4, P2 = align_board44()
    racts, used = rigid_solves(cur2, H4, P2)  # 内部 time_cap=None
    check('T5 time_cap=None 老调用仍能解出（行为不变）',
          racts is not None, 'used=%s' % used)


def main():
    test_rigid_still_solves()
    test_rigid_equiv_to_full_dfs()
    test_rigid_calls_shared()
    test_rigid_time_cap_prunes()
    test_rigid_default_no_cap()
    print()
    if FAILS:
        print('FAILED %d:' % len(FAILS))
        for f in FAILS:
            print('  -', f)
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
