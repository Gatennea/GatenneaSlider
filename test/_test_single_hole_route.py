# -*- coding: utf-8 -*-
"""单洞路由护栏（2026-11-11）。

回归：auto_solve 默认路由对「单洞（无论内外）」局面必须走补缺宏(填洞)先，而非
混合(聚攏)先。实测 5×5 s2 单内洞默认路由曾白跑一趟混合(聚攏/GBFS)烧 7.5s，才
轮到填洞 0.0s 直解。修复＝auto_solver 路由放宽：单洞一律 gap_first（先前只覆盖
单洞+贴边/角，漏了单内洞）。

判据（确定性，不靠计时）：spy 监控 `solver.auto_solver.hybrid_solve` 是否被调用。
修复态填洞先跑即全解并 return，混合根本不该启动；旧路由混合先跑必调用它。
⚠️不能用「首段标签」当判据：旧路由下混合跑完没采纳任何段，随后补缺宏解出，
首段仍是「补缺宏」——反向验证实测该判据撤修复仍绿，是假护栏。

只挑「补缺宏确实能直解」的单内洞快照（有些单洞因「洞凸不同mod」填洞解不了，
那种局面本来就该回落混合，不属本护栏约束）。

执行：D:/python/python.exe -u test/_test_single_hole_route.py
"""
import os
import sys
import json
import glob
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solver.ml.fill_macro import build_game, window_of  # noqa: E402
from solver.ml.gap_solver import solve_gap_macro, _edge_of  # noqa: E402
from solver.auto_solver import auto_solve  # noqa: E402
import solver.auto_solver as _as  # noqa: E402


def _gap_can_solve(coords, m, n, step):
    """补缺宏能否对该局面确定性直解（避免挑到「洞凸不同mod」不可直解的单洞）。"""
    try:
        res = solve_gap_macro(build_game(coords, m, n), step, time_budget=5.0)
    except Exception:
        return False
    if isinstance(res, tuple):
        return True
    if isinstance(res, dict):
        return bool(res.get('solved'))
    return False


def _find_case():
    """找「恰好 1 洞且在内部 INNER、且补缺宏可直解」的快照（优先最新存档）。"""
    cands = glob.glob(os.path.join(ROOT, 'save', '**', '2-5-5-*.json'),
                      recursive=True)
    cands.sort(key=os.path.getmtime, reverse=True)
    for p in cands:
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        puz = d.get('puzzle') or {}
        m, n, step = puz.get('m'), puz.get('n'), puz.get('step')
        if not (m and n and step):
            continue
        for snap in d['history']['snapshots']:
            mat = snap['matrix']
            b = snap['bounds']
            coords = frozenset((r + b['min_row'], c + b['min_col'])
                              for r, row in enumerate(mat)
                              for c, v in enumerate(row) if v)
            _reg, _ov, holes, _out = window_of(coords, m, n, step)
            if len(holes) != 1:
                continue
            h = next(iter(holes))
            e = _edge_of(h, _reg[0], _reg[1], _reg[2][0], _reg[2][1])
            if e != 'INNER':
                continue
            if _gap_can_solve(coords, m, n, step):
                return coords, m, n, step, p
    return None


def main():
    found = _find_case()
    if not found:
        print('[SKIP] 未找到「单内洞且补缺宏可直解」的 2-5-5 存档快照')
        return 0
    coords, m, n, step, path = found
    print('命中存档 %s  单内洞 %dx%d s%d' % (os.path.basename(path), m, n, step))

    labels = []
    calls = [0]
    _orig_hybrid = _as.hybrid_solve

    def spy(*args, **kwargs):
        calls[0] += 1
        return _orig_hybrid(*args, **kwargs)

    def cb(seg):
        labels.append(seg.get('label', ''))

    _as.hybrid_solve = spy
    try:
        t0 = time.time()
        r = auto_solve(build_game(coords, m, n), step, total_budget=15.0,
                       rng_seed=1, stage_cb=cb)
        dt = time.time() - t0
    finally:
        _as.hybrid_solve = _orig_hybrid

    ok_solved = isinstance(r, tuple)
    no_hybrid = calls[0] == 0
    print('全解=%s  混合求解器启动次数=%d  首段=%r  耗时=%.3fs'
          % (ok_solved, calls[0], labels[0] if labels else None, dt))
    if not ok_solved:
        print('[FAIL] 单内洞未全解: %r' % (r,))
        return 1
    if not no_hybrid:
        print('[FAIL] 单内洞默认路由启动了混合(聚攏)求解器——回归：该填洞却先跑混合')
        return 1
    print('[PASS] 单内洞默认路由直达填洞、未启动混合，且全解')
    return 0


if __name__ == '__main__':
    sys.exit(main())
