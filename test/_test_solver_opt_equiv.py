# -*- coding: utf-8 -*-
"""求解器优化护栏：远端 255b8d3 的「等价提速 + 分段流式 + 按时停机」。

审查 2026-11-09 时坐实的三件事，都用护栏钉住：
1. convoy 连通判定三级化（_union_connected）必须与原满 DFS **逐案等价**——
   从生产源码 AST 抽出函数，随机 + 真实存档双算，不许静默改判据。
2. GBFS 堆条目复用 + 父指针去路径拷贝必须与旧版**逐位一致**——
   真实局面几乎都是 ex=1（一步填一洞），证明力太弱，故用抽象图逼出
   8 层父指针回溯 / 数百节点展开。
3. 流式链（segment_cb / stage_budget / progress_cb）不能回流：静态接线 +
   真实局面逐段重放 + 小预算按时收敛。

⚠️ 求解内部 `fill_macro.py:647 rng = rng or random.Random()` 用系统种子，
同一局面多次求解的解链会漂移（光设 PYTHONHASHSEED / random.seed 不够），
所以运行时断言只看「合法性 / 收敛」，不断言具体步数。

执行：D:/python/python.exe -u test/_test_solver_opt_equiv.py
"""
import heapq
import json
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game import SliderMatrix                                    # noqa: E402
from solver import auto_solver as auto_mod                       # noqa: E402
from solver.auto_solver import auto_solve                        # noqa: E402
from solver.ml.fill_macro import (_DIRS, build_game,            # noqa: E402
                                  _replay_apply)
from solver.ml.invariants import is_solved_by_profile            # noqa: E402
import solver.hybrid_solver as hs                                # noqa: E402
import solver.search_core as sc                                  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, extra))
    if not cond:
        _failures.append(name)
    return bool(cond)


DIR4 = tuple(_DIRS.values())

# ---------------------------------------------------------------- 1. convoy
import solver.ml.fill_macro as _fm  # noqa: E402

# 2026-11-12：_union_connected 从 _convoy_fill 内的嵌套闭包提升为「模块级
# 共用」——convoy / rigid 两宏的 _legal_steps 都调同一个带缓存的三级判定。
# 护栏跟着改成直接钉模块级实现，不再从源码 AST 抽嵌套函数（那样既漏掉
# rigid 是否真共用，也会在刚提升完就抽不到三个函数而恒红）。
check('A1 模块级 _union_connected 存在且是 (rest, mv_k, 双缓存) 四参',
      hasattr(_fm, '_connected_ml') and hasattr(_fm, '_union_connected')
      and _fm._union_connected.__code__.co_argcount == 4)
old_connected = _fm._connected_ml          # 满 DFS 基线
new_connected = _fm._union_connected       # 共用三级判定


def random_cases(rng, count, grid=9):
    cells = [(r, c) for r in range(grid) for c in range(grid)]
    for _ in range(count):
        rng.shuffle(cells)
        rest = frozenset(cells[:rng.randint(1, 20)])
        free = cells[len(rest):]
        if rng.random() < 0.5:
            near = [(r + dr, c + dc) for r, c in rest
                    for dr, dc in DIR4 if (r + dr, c + dc) not in rest]
            start = rng.choice(near) if near else rng.choice(free)
        else:
            start = rng.choice(free)
        size = rng.randint(1, 6)
        blob, frontier = {start}, [start]
        while frontier and len(blob) < size:
            r, c = frontier.pop(rng.randrange(len(frontier)))
            for dr, dc in DIR4:
                q = (r + dr, c + dc)
                if (q not in rest and q not in blob
                        and 0 <= q[0] < grid and 0 <= q[1] < grid):
                    blob.add(q)
                    frontier.append(q)
                    if len(blob) >= size:
                        break
        mv = frozenset(blob)
        if mv & rest:
            continue
        yield rest, mv


def real_cases(rng, count):
    docs = []
    for rel in ['archives/失败%02d.json' % i for i in range(1, 5)] + [
            'beginner_archive/5.1.json']:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            doc = json.load(f)
        s0 = doc['history']['snapshots'][0]
        b0 = s0['bounds']
        docs.append(frozenset((b0['min_row'] + i, b0['min_col'] + j)
                              for i, row in enumerate(s0['matrix'])
                              for j, v in enumerate(row) if v))
    if not docs:
        return
    n = 0
    while n < count:
        coords = rng.choice(docs)
        comp, frontier = {rng.choice(sorted(coords))}, None
        frontier = list(comp)
        size = rng.randint(1, 5)
        while frontier and len(comp) < size:
            r, c = frontier.pop(rng.randrange(len(frontier)))
            for dr, dc in DIR4:
                q = (r + dr, c + dc)
                if q in coords and q not in comp:
                    comp.add(q)
                    frontier.append(q)
                    if len(comp) >= size:
                        break
        rest = coords - comp
        if not rest:
            continue
        dr, dc = rng.choice(DIR4)
        k = rng.randint(1, 3)
        mv = frozenset((r + dr * k, c + dc * k) for r, c in comp)
        if mv & rest:
            continue
        n += 1
        yield frozenset(rest), mv


def double_run(label, cases, limit):
    total = diff = 0
    for rest, mv in cases:
        if total >= limit:
            break
        if old_connected(rest | mv) != new_connected(rest, mv, {}, {}):
            diff += 1
        total += 1
    check(label, diff == 0 and total >= limit,
          'cases=%d diff=%d' % (total, diff))


if old_connected and new_connected:
    _rng = random.Random(20261109)
    double_run('A2 随机网格双算等价', random_cases(_rng, 12000), 10000)
    double_run('A3 真实存档双算等价', real_cases(_rng, 12000), 10000)


def _shared_calls():
    """行为级：两个宏的 _legal_steps 是否真的都调共享 _union_connected。

    旧判据查源码子串 `'...' in fm_src`——把调用撤掉、只留注释也恒绿，
    是典型的假护栏。改成 spy 计数，直接盯「共享函数有没有被启动」。
    """
    calls = {'n': 0}
    orig = _fm._union_connected

    def spy(rest, mv_k, ca, ib):
        calls['n'] += 1
        return orig(rest, mv_k, ca, ib)

    c4 = frozenset({(0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 3),
                    (2, 0), (2, 1), (2, 2), (2, 3), (3, 0), (3, 1),
                    (3, 2), (3, 3), (3, 4), (3, 5)})
    _fm._union_connected = spy
    try:
        _fm._convoy_fill(c4, 4, 4, 2, (1, 1), (3, 5), max_nodes=8)
        convoy_hit = calls['n'] > 0
        calls['n'] = 0
        _fm._rigid_fill(c4, 4, 4, 2,
                        frozenset({(1, 1), (1, 2)}),
                        frozenset({(3, 4), (3, 5)}), max_nodes=8)
        rigid_hit = calls['n'] > 0
    finally:
        _fm._union_connected = orig
    return convoy_hit, rigid_hit


_hits = _shared_calls()
check('A4 convoy/rigid 的 _legal_steps 都实际调用共享 _union_connected',
      _hits[0] and _hits[1], 'convoy=%s rigid=%s' % _hits)

# ------------------------------------------------------------------ 2. GBFS
def old_guided_reduce_one(coords, m, n, step, budget=80000,
                          cancel_check=None):
    """改动前 search_core 的逐字实现（b5d19ef），只作为差分基线。"""
    start = frozenset(coords)
    h0 = len(sc.fast_window(start, m, n)[1])
    counter = 0
    openq = [(h0, 0, 0, start, [])]
    bestg = {sc.canonicalize(start): 0}
    closed = set()
    expanded = 0
    while openq:
        _f, g, _, cur, path = heapq.heappop(openq)
        ck = sc.canonicalize(cur)
        if g > bestg.get(ck, -1) or ck in closed:
            continue
        if len(sc.fast_window(cur, m, n)[1]) < h0:
            return path, expanded
        closed.add(ck)
        expanded += 1
        if expanded > budget or (cancel_check and cancel_check()):
            return None, expanded
        for new, act, rep in sc.expand(cur, step):
            nk = sc.canonicalize(new)
            ng = g + 1
            if ng >= bestg.get(nk, 10 ** 9):
                continue
            bestg[nk] = ng
            counter += 1
            _win, holes, protr = sc.fast_window(new, m, n)
            h = len(holes)
            for p in protr:
                if holes:
                    d = min(abs(p[0] - q[0]) + abs(p[1] - q[1])
                            for q in holes)
                    h += max(1, d // step)
            heapq.heappush(openq, (h, ng, counter, new,
                                   path + [(act, rep)]))
    return None, expanded


def abstract_graph(seed, size=500):
    rng = random.Random(seed)
    hval = [rng.choice([3, 3, 3, 4, 4, 5]) for _ in range(size)]
    hval[0] = 3
    edges = {}
    for s in range(size):
        tgt = set(rng.randint(1, size - 1)
                  for _ in range(rng.randint(1, 3)))
        tgt.discard(s)
        edges[frozenset({s})] = [(frozenset({t}), ('mv', s, t), None)
                                 for t in sorted(tgt)]
    for i in range(8):
        edges[frozenset({i})].append(
            (frozenset({i + 1}), ('chain', i, i + 1), None))
        hval[i] = 3
    hval[8] = 1
    if seed == 99:
        hval = [max(v, 3) for v in hval]        # 无解图：跑到堆空
    return hval, edges


_saved = {k: getattr(sc, k) for k in
          ('expand', 'fast_window', 'canonicalize', 'heuristic_parts')}
_diff, _exs, _paths = 0, [], []
try:
    for _seed in (7, 17, 29, 43, 61, 99):
        hval, edges = abstract_graph(_seed)

        def _idx(s):
            return next(iter(s))

        def _fw(coords, m, n, _h=hval):
            return None, [0] * _h[_idx(coords)], []

        def _ex(cur, step, _e=edges):
            return _e.get(cur, [])

        def _hp(coords, m, n, step, _h=hval):
            v = _h[_idx(coords)]
            return v, v

        sc.expand, sc.fast_window, sc.canonicalize = _ex, _fw, lambda s: s
        sc.heuristic_parts = _hp
        st = frozenset({0})
        po, xo = old_guided_reduce_one(st, 4, 4, 2, budget=10000)
        pn, xn = sc.guided_reduce_one(st, 4, 4, 2, budget=10000)
        _diff += (po != pn or xo != xn)
        _exs.append(xo)
        _paths.append(len(pn or []))
finally:
    for _k, _v in _saved.items():
        setattr(sc, _k, _v)

check('B1 抽象图深层差分逐位一致（父指针回溯）', _diff == 0,
      'diff=%d' % _diff)
check('B2 覆盖深层（展开>=100 且路径>=4）',
      max(_exs) >= 100 and max(_paths) >= 4,
      'max_ex=%d max_path=%d' % (max(_exs), max(_paths)))

# ------------------------------------------------- 3. 流式链 / 停机 接线
import inspect                                                    # noqa: E402

check('C1 hybrid_solve 签名仍有 segment_cb',
      'segment_cb' in inspect.signature(hs.hybrid_solve).parameters)
check('C2 auto_solve 签名仍有 stage_budget',
      'stage_budget' in inspect.signature(auto_mod.auto_solve).parameters)
check('C3 guided_reduce_one 签名仍有 progress_cb',
      'progress_cb' in inspect.signature(sc.guided_reduce_one).parameters)


def a5_of(acts, reps):
    reps = list(reps or [])
    return [tuple(a) + ((tuple(reps[i]),) if i < len(reps) and reps[i]
                        else (None,))
            for i, a in enumerate(acts)]


def stream_case(m, n, seed, budget):
    random.seed(seed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=150, step=2)
    coords0 = frozenset(tuple(b.location) for b in g.blocks)
    stages, t0 = [], time.time()

    def cb(s):
        stages.append(dict(s))

    r = auto_solve(g, 2, stage_cb=cb, stage_budget=budget)
    dt = time.time() - t0
    cur, ok = coords0, True
    for s in stages:
        gg = build_game(cur, m, n)
        if not _replay_apply(gg, a5_of(s['actions'], s['reps']), m, n, 2):
            ok = False
            break
        cur = frozenset(tuple(b.location) for b in gg.blocks)
        if cur != frozenset(s['end']):
            ok = False
            break
    solved = isinstance(r, tuple)
    if solved:
        end = build_game(coords0, m, n)
        _replay_apply(end, a5_of(r[0], r[1]), m, n, 2)
        solved_ok = is_solved_by_profile(
            frozenset(tuple(b.location) for b in end.blocks), m, n)
    else:
        solved_ok = True
    return {'ok': ok, 'dt': dt, 'stages': len(stages), 'solved': solved,
            'solved_ok': solved_ok}


_s = stream_case(5, 5, 5, 15)
check('C4 流式链逐段重放 end 与落点一致（5×5）', _s['ok'] and
      _s['stages'] >= 1, str(_s))
check('C5 若返回全解，整链确实复原', _s['solved_ok'], str(_s['solved']))
_d = stream_case(7, 7, 3, 2)
check('C6 小预算难局按时收敛（<25s）', _d['dt'] < 25 and _d['ok'],
      'dt=%.1fs stages=%d' % (_d['dt'], _d['stages']))

print('==== %s（%d 项失败）' % ('全部通过' if not _failures else '有失败',
                            len(_failures)))
sys.exit(1 if _failures else 0)
