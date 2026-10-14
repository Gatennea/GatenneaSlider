# -*- coding: utf-8 -*-
"""
数字谜题「可达排列群」实验（Q1，2026-10）

问题（原版可解的形态，标数字后哪些标法仍可解）：
  形态 S 在原版可解（能移到目标矩形）。给 S 的 K 个块标上 1..K
  （开局按行主序赋编号，随块平移不换号）。问：哪些标法存在一条
  移动序列，使编号沿路搬运后（在 D4 八对称之一下）落回行主序？

模型（全部与 GUI 判定一致）：
  - 编号赋值：开局对行主序块列表赋 1..K（GUI.py 编号赋值处）
  - 移动位移恒为等级的整数倍（按键/拖拽/宏回放三条路径），整体平移禁止
    → 每个编号所在格的 (行 mod 等级, 列 mod 等级) 永不变（逐块着色类不变量）
  - 判胜 = 形状为 m×n 或 n×m 矩形（game.is_solved）+ 编号行主序 + D4 八变换
    （GUI.is_solved 的变换表，目标种子直接照抄）

方法：在「形态 × 编号」的提升状态空间上做正反双向 BFS。
  - 规范化只消去「等级整数倍的整体平移」（min 行/列归一到 [0, 等级)），
    不做 D4 规范化——编号破坏旋转对称，非等级倍平移改变着色类也不同状态
  - 正向：从（复原矩形, 行主序编号）出发 = 游戏打乱能到达的全部状态
  - 反向：从判胜目标出发 = 能通关的全部状态
  - 候选集（闭式计数）：每个编号都落在自己家格同着色类的标法
    候选数 = 各着色类格子数的阶乘之积
  - 猜想：可解标法 == 候选集（着色类匹配 ⟺ 可解）
  - 复原矩形上的正向可达编号集 = 可达排列群本体，检查乘法封闭性
    （编号集合作为「格子→编号」的映射，运算 (L_A ⋆ L_B)[i] = L_A[L_B[i]-1]）

移动模型完备性：try_move 逐格验证（game.py），任何等级整数倍位移都可
分解为若干个「等级格」单步移动，故只枚举等级格单步即完备；缝隙/侧/分量
枚举与 table_core 正向枚举同口径。

前驱生成复用 solver/table_core.predecessors（已通过全量边核验），调用期间
把其 D4 规范化临时替换为平移规范化（monkeypatch，仅本进程生效）。

用法：
  python experiments/math_repro/numbered_monodromy.py 2 3 1
  python experiments/math_repro/numbered_monodromy.py 3 3 2 --max-states 3000000
  python experiments/math_repro/numbered_monodromy.py 4 4 2 --skip-backward
"""

import argparse
import sys
import time
from collections import Counter, defaultdict, deque
from math import factorial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import solver.table_core as tc  # noqa: E402


# ---------------------------------------------------------------------------
# 基础：平移规范化
# ---------------------------------------------------------------------------
# 当前实验的等级（solve() 入口设置）。规范化只消去等级整数倍的平移，
# 必须用模块级变量，因为 table_core.predecessors 的 monkeypatch 只传 coords。
STEP = 1


def norm_cells(cells):
    """平移规范化：只消去等级整数倍的平移，min 行/列落在 [0, 等级)。

    等级谜题中所有移动位移都是等级的整数倍，因此整体平移只有等级整数倍
    才是对称（可互相同一状态）；非等级倍的偏移会改变每个块的着色类，
    属于本质不同的状态，必须保留——这就是 min 归一到 [0, 等级) 的原因。
    STEP=1 时退化为 min 归一到 0。
    """
    mr = min(r for r, _ in cells)
    mc = min(c for _, c in cells)
    sr = mr - (mr % STEP)
    sc = mc - (mc % STEP)
    return frozenset((r - sr, c - sc) for r, c in cells)


# ---------------------------------------------------------------------------
# 正向移动（带编号搬运映射）
# ---------------------------------------------------------------------------
def _try_move(shape, comp, du, step):
    """把 comp 沿 du 平移 step 格（逐格验证碰撞+连通）。

    返回 (新形态[平移规范], 映射) ；映射 = 新形态格子 -> 旧格子（当前帧）。
    镜像 table_core._try_forward 的验证口径。
    """
    non_sel = shape - frozenset(comp)
    cur = set(comp)
    for _ in range(step):
        cur = {(r + du[0], c + du[1]) for r, c in cur}
        if cur & non_sel:
            return None
        if not tc.is_single_connected(cur | non_sel):
            return None
    new = frozenset(non_sel | cur)
    new_norm = norm_cells(new)
    # mp：新形态格子 -> 旧格子。旧形态已规范化，故旧绝对坐标即旧规范坐标；
    # 键用新形态的规范坐标
    mr = min(r for r, _ in new)
    mc = min(c for _, c in new)
    sr = mr - (mr % STEP)
    sc = mc - (mc % STEP)
    mp = {}
    for r, c in new:
        key = (r - sr, c - sc)
        if (r, c) in cur:          # 被移动的格子：旧格 = 新格 - step*du
            mp[key] = (r - du[0] * step, c - du[1] * step)
        else:                       # 未动的格子
            mp[key] = (r, c)
    return new_norm, mp


def forward_moves(shape, step):
    """枚举 shape 上全部等级格单步移动（缝隙 × 侧 × 分量 × 方向，去重）。

    缝隙范围/侧分量与 table_core 正向枚举同口径（缝隙作为墙取连通分量）。
    """
    out = {}
    rows = [r for r, _ in shape]
    cols = [c for _, c in shape]
    min_r, max_r = min(rows), max(rows)
    min_c, max_c = min(cols), max(cols)

    def record(res):
        if res is None:
            return
        new_shape, mp = res
        key = (new_shape, frozenset(mp.items()))
        if key not in out:
            out[key] = res

    # 水平缝（行间），只能左右移动
    for line in range(min_r, max_r):
        for side in ('above', 'below'):
            for comp in tc._side_components(shape, 'h', line, side):
                for du in ((0, -1), (0, 1)):
                    record(_try_move(shape, comp, du, step))
    # 垂直缝（列间），只能上下移动
    for line in range(min_c, max_c):
        for side in ('left', 'right'):
            for comp in tc._side_components(shape, 'v', line, side):
                for du in ((-1, 0), (1, 0)):
                    record(_try_move(shape, comp, du, step))
    return list(out.values())


# ---------------------------------------------------------------------------
# 前驱（复用 table_core.predecessors，D4 规范化 → 平移规范化）
# ---------------------------------------------------------------------------
def shape_predecessors(shape, m, n, step, move_cache, pred_cache, fwd_preds,
                       cross_errors):
    """shape 的全部真前驱 + 标签搬运映射：[(前驱形态, 新->旧映射), ...]。

    - table_core.predecessors 产出前驱形态（平移规范化后）
    - 映射回收：从前驱出发枚举正向移动，落在当前形态的那些即为真实边
    - 交叉核验：正向 BFS 已知的「能一步走到本形态」的前驱必须全部被覆盖
    """
    if shape in pred_cache:
        return pred_cache[shape]

    orig = tc.canonicalize
    tc.canonicalize = lambda coords: norm_cells(coords)
    try:
        preds = tc.predecessors(shape, m, n, step)
    finally:
        tc.canonicalize = orig

    # 交叉核验：正向已知前驱 ⊆ 反向生成前驱
    if shape in fwd_preds:
        missing = fwd_preds[shape] - preds
        if missing:
            cross_errors.append((shape, len(missing)))

    out = []
    no_map = 0
    for p in preds:
        got = False
        for new_shape, mp in _cached_moves(p, step, move_cache):
            if new_shape == shape:
                out.append((p, mp))
                got = True
        if not got:
            no_map += 1
    if no_map:
        cross_errors.append((shape, ('前驱无对应正向边', no_map)))
    pred_cache[shape] = out
    return out


def _cached_moves(shape, step, move_cache):
    if shape not in move_cache:
        move_cache[shape] = forward_moves(shape, step)
    return move_cache[shape]


# ---------------------------------------------------------------------------
# 判胜目标种子（照抄 GUI.is_solved 的 D4 变换表）
# ---------------------------------------------------------------------------
def gui_targets(m, n):
    """判胜目标 = (形态, 编号) 列表：m×n 与 n×m 两种矩形 × 8 变换 × 平移偏移。

    GUI 判胜允许矩形任意平移（标签按包围盒判定，平移不变）；但等级谜题中
    不同平移偏移 mod 等级是本质不同的状态（着色类整体平移），故每个目标
    还要枚举 [0, 等级)² 内的偏移（等级整数倍偏移规范化时已折叠）。
    """
    K = m * n
    from itertools import product
    seeds = []
    for rows, cols in {(m, n), (n, m)}:
        transforms = (
            (lambda i, j: (i, j), rows, cols),                      # 恒等
            (lambda i, j: (rows - 1 - i, cols - 1 - j), rows, cols),  # 旋转180
            (lambda i, j: (rows - 1 - i, j), rows, cols),           # 上下镜像
            (lambda i, j: (i, cols - 1 - j), rows, cols),           # 左右镜像
            (lambda i, j: (j, i), cols, rows),                      # 主对角线
            (lambda i, j: (cols - 1 - j, rows - 1 - i), cols, rows),  # 副对角线
            (lambda i, j: (j, rows - 1 - i), cols, rows),           # 旋转90
            (lambda i, j: (cols - 1 - j, i), cols, rows),           # 旋转270
        )
        shape = frozenset((i, j) for i in range(rows) for j in range(cols))
        cells = sorted(shape)
        for fn, _rows2, cols2 in transforms:
            labels = []
            for i, j in cells:
                a, b = fn(i, j)
                labels.append(a * cols2 + b + 1)
            labels = tuple(labels)
            assert sorted(labels) == list(range(1, K + 1)), (rows, cols, labels)
            for tr, tc in product(range(STEP), repeat=2):
                # 均匀平移不改变格子排序 → labels 不变；偏移已在 [0,等级) 内，
                # 规范化即自身
                seeds.append((frozenset((r + tr, c + tc) for r, c in shape),
                              labels))
    # 去重（方阵时两组变换可能重合）
    seen = set()
    out = []
    for st in seeds:
        if st not in seen:
            seen.add(st)
            out.append(st)
    return out


# ---------------------------------------------------------------------------
# 提升状态 BFS
# ---------------------------------------------------------------------------
def forward_bfs(rect, start_labels, step, max_states, move_cache, fwd_preds):
    """正向：从（复原矩形, 行主序编号）出发的全部可达状态。

    返回 (fibers, 截断与否, 着色类不变量违例数)。
    fibers[形态] = 可达编号组集合。
    """
    fibers = {rect: {start_labels}}
    dq = deque([(rect, start_labels)])
    n_states = 1
    truncated = False
    sorted_cache = {rect: sorted(rect)}
    t0 = time.time()
    while dq:
        if n_states >= max_states:
            truncated = True
            break
        shape, labels = dq.popleft()
        cells_old = sorted_cache[shape]
        idx_old = {c: i for i, c in enumerate(cells_old)}
        for new_shape, mp in _cached_moves(shape, step, move_cache):
            if new_shape not in sorted_cache:
                sorted_cache[new_shape] = sorted(new_shape)
            cells_new = sorted_cache[new_shape]
            new_labels = tuple(labels[idx_old[mp[c]]] for c in cells_new)
            fwd_preds[new_shape].add(shape)
            bucket = fibers.get(new_shape)
            if bucket is None:
                fibers[new_shape] = {new_labels}
            elif new_labels in bucket:
                continue
            else:
                bucket.add(new_labels)
            dq.append((new_shape, new_labels))
            n_states += 1
            if n_states % 500_000 == 0:
                print(f'    正向已展开 {n_states:,} 状态，'
                      f'形态 {len(fibers)}，{time.time() - t0:.0f}s', flush=True)
    return fibers, truncated, n_states


def backward_bfs(seeds, step, m, n, max_states, move_cache, pred_cache,
                 fwd_preds, cross_errors):
    """反向：能走到任一判胜目标的全部状态。"""
    fibers = {}
    dq = deque()
    for st in seeds:
        shape, labels = st
        fibers.setdefault(shape, set()).add(labels)
        dq.append(st)
    n_states = len(seeds)
    truncated = False
    sorted_cache = {st[0]: sorted(st[0]) for st in seeds}
    t0 = time.time()
    while dq:
        if n_states >= max_states:
            truncated = True
            break
        shape, labels = dq.popleft()
        cells_new = sorted_cache[shape]
        for p, mp in shape_predecessors(shape, m, n, step, move_cache,
                                        pred_cache, fwd_preds, cross_errors):
            if p not in sorted_cache:
                sorted_cache[p] = sorted(p)
            cells_p = sorted_cache[p]
            idx_p = {c: i for i, c in enumerate(cells_p)}
            new_labels = [0] * len(cells_p)
            for i, c in enumerate(cells_new):
                new_labels[idx_p[mp[c]]] = labels[i]
            new_labels = tuple(new_labels)
            bucket = fibers.get(p)
            if bucket is None:
                fibers[p] = {new_labels}
            elif new_labels in bucket:
                continue
            else:
                bucket.add(new_labels)
            dq.append((p, new_labels))
            n_states += 1
            if n_states % 500_000 == 0:
                print(f'    反向已展开 {n_states:,} 状态，'
                      f'形态 {len(fibers)}，{time.time() - t0:.0f}s', flush=True)
    return fibers, truncated, n_states


# ---------------------------------------------------------------------------
# 候选集（逐块着色类不变量）
# ---------------------------------------------------------------------------
def make_candidate(m, n, step):
    K = m * n

    def home_class(num):
        r, c = divmod(num - 1, n)
        return (r % step, c % step)

    num_cnt = Counter(home_class(v) for v in range(1, K + 1))

    def candidate_count(shape):
        """候选标法数 = 各着色类格子数阶乘之积（类计数不匹配则为 0）。"""
        cell_cnt = Counter((r % step, c % step) for r, c in shape)
        if cell_cnt != num_cnt:
            return 0
        total = 1
        for v in cell_cnt.values():
            total *= factorial(v)
        return total

    def is_candidate(shape, labels):
        cells = sorted(shape)
        return all((cells[i][0] % step, cells[i][1] % step) == home_class(labels[i])
                   for i in range(len(labels)))

    def candidate_enum(shape):
        """枚举候选标法（候选数过大时返回 None）。上限 200,000。"""
        cnt = candidate_count(shape)
        if cnt == 0:
            return set()
        if cnt > 200_000:
            return None
        cells = sorted(shape)
        groups = defaultdict(list)   # 着色类 -> 该类格子下标
        for i, (r, c) in enumerate(cells):
            groups[(r % step, c % step)].append(i)
        num_groups = defaultdict(list)  # 着色类 -> 该类编号
        for num in range(1, m * n + 1):
            num_groups[home_class(num)].append(num)
        # 逐类全排列组合
        class_keys = sorted(groups.keys())
        from itertools import permutations, product
        per_class = []
        for k in class_keys:
            per_class.append(list(permutations(num_groups[k])))
        out = set()
        for combo in product(*per_class):
            labels = [0] * (m * n)
            for k_idx, k in enumerate(class_keys):
                for slot, cell_i in enumerate(groups[k]):
                    labels[cell_i] = combo[k_idx][slot]
            out.add(tuple(labels))
        return out

    return candidate_count, is_candidate, candidate_enum


# ---------------------------------------------------------------------------
# 广义候选（GUI 判胜口径：D4 × 平移偏移）
# ---------------------------------------------------------------------------
def g_class_maps(m, n, step):
    """广义类映射集合：每个映射 = (编号k 的目标着色类[k-1])，取自全部判胜目标。

    等级谜题中编号 k 的着色类沿移动不变；(S, 标法) 可解的必要条件是存在
    一个判胜目标（某个 D4 × 某个平移偏移），使每个编号的当前着色类都等于
    它在该目标中的着色类。
    """
    maps = set()
    for shape, labels in gui_targets(m, n):
        cells = sorted(shape)
        pos = [None] * (m * n)
        for i, c in enumerate(cells):
            pos[labels[i] - 1] = c
        maps.add(tuple((r % step, c % step) for r, c in pos))
    return maps


def g_ok(shape, labels, maps):
    """标法是否满足某个广义类映射（可解的必要条件）。

    maps 元素 = (编号k的目标着色类[k-1])，着色类按 STEP 取模。
    """
    cells = sorted(shape)
    cell_cls = [(r % STEP, c % STEP) for r, c in cells]
    for mp in maps:
        if all(cell_cls[i] == mp[num - 1] for i, num in enumerate(labels)):
            return True
    return False


def g_count(shape, maps):
    """形态上满足广义类映射的标法总数（不同映射的标法集互不相交：两个不同
    映射必在某编号上给出不同着色类，标法无法同时满足两者）。"""
    cells = sorted(shape)
    cell_hist = Counter((r % STEP, c % STEP) for r, c in cells)
    total = 0
    for mp in maps:
        num_hist = Counter(mp)
        if num_hist != cell_hist:
            continue
        ways = 1
        for v in cell_hist.values():
            ways *= factorial(v)
        total += ways
    return total


def g_enum(shape, maps, cap=200_000):
    """枚举满足广义类映射的全部标法；总数 > cap 时返回 None。"""
    cells = sorted(shape)
    cell_groups = defaultdict(list)
    for i, (r, c) in enumerate(cells):
        cell_groups[(r % STEP, c % STEP)].append(i)
    out = set()
    from itertools import permutations, product
    for mp in maps:
        num_groups = defaultdict(list)
        for num, cls in enumerate(mp, start=1):
            num_groups[cls].append(num)
        keys = set(num_groups) | set(cell_groups)
        if any(len(num_groups.get(k, ())) != len(cell_groups.get(k, ()))
               for k in keys):
            continue
        class_keys = sorted(cell_groups.keys())
        per_class = [list(permutations(num_groups.get(k, ())))
                     for k in class_keys]
        for combo in product(*per_class):
            labels = [0] * (len(cells))
            for k_idx, k in enumerate(class_keys):
                for slot, cell_i in enumerate(cell_groups[k]):
                    labels[cell_i] = combo[k_idx][slot]
            out.add(tuple(labels))
            if len(out) > cap:
                return None
    return out


def render(shape, labels):
    """把（形态, 编号）画成方格图，超出矩形范围用 · 表示空位。"""
    cells = sorted(shape)
    max_r = max(r for r, _ in cells)
    max_c = max(c for _, c in cells)
    grid = [['·'] * (max_c + 1) for _ in range(max_r + 1)]
    for i, (r, c) in enumerate(cells):
        grid[r][c] = str(labels[i]) if labels[i] < 10 else chr(ord('a') + labels[i] - 10)
    return '\n'.join(' '.join(row) for row in grid)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def solve(m, n, step, max_states, skip_backward):
    global STEP
    STEP = step
    K = m * n
    tag = f'{m}_{n}_{step}'
    print('=' * 70)
    print(f'[{tag}] {m}×{n} 等级{step}，K={K}')
    t0 = time.time()

    rect = frozenset((r, c) for r in range(m) for c in range(n))
    rect_cells = sorted(rect)
    start_labels = tuple(r * n + c + 1 for r, c in rect_cells)
    assert start_labels == tuple(range(1, K + 1))

    candidate_count, is_candidate, candidate_enum = make_candidate(m, n, step)

    move_cache = {}
    pred_cache = {}
    fwd_preds = defaultdict(set)
    cross_errors = []

    # ---- 正向 ----
    print('  正向 BFS（打乱可达集合）...', flush=True)
    fwd, fwd_trunc, n_fwd = forward_bfs(rect, start_labels, step, max_states,
                                        move_cache, fwd_preds)
    cand_rect = candidate_count(rect)
    g_size = len(fwd.get(rect, ()))
    print(f'  正向: 状态 {n_fwd:,}，形态 {len(fwd)}'
          f'{"（已截断！结论仅下界）" if fwd_trunc else ""}'
          f'，{time.time() - t0:.0f}s')

    # 可达排列群（复原矩形上的正向可达编号集）
    g_set = fwd.get(rect, set())
    print(f'  可达排列群（复原矩形上的可达编号集）: 阶 = {g_size:,}，'
          f'候选集 = {cand_rect:,}，相等? {g_size == cand_rect}')
    if not fwd_trunc and g_size <= 3000:
        ident = tuple(range(1, K + 1))
        closed = True
        if ident not in g_set:
            closed = False
        else:
            for la in g_set:
                for lb in g_set:
                    comp = tuple(la[lb[i] - 1] for i in range(K))
                    if comp not in g_set:
                        closed = False
                        break
                if not closed:
                    break
        print(f'  乘法封闭（成群）? {closed}'
              + ('（含恒等）' if ident in g_set else '（缺恒等！）'))
    elif g_size > 3000:
        print('  乘法封闭: 组太大，跳过全查（>3000）')

    # 各形态可达标法数分布 + 候选集一致性（必要性方向）
    dist = Counter(len(v) for v in fwd.values())
    print(f'  各形态可达标法数: 最少 {min(dist)}, 最多 {max(dist)}，'
          f'分布(前5) {dict(sorted(dist.items())[:5])}'
          + (' ...' if len(dist) > 5 else ''))

    if skip_backward:
        print(f'  （--skip-backward，跳过反向）总耗时 {time.time() - t0:.0f}s')
        return

    # ---- 反向：恒等目标（严格复原到行主序） ----
    print('  反向 BFS（恒等判胜目标）...', flush=True)
    b_id, b_id_trunc, n_bid = backward_bfs([(rect, start_labels)], step, m, n,
                                           max_states, move_cache, pred_cache,
                                           fwd_preds, cross_errors)
    print(f'  反向(恒等): 状态 {n_bid:,}，形态 {len(b_id)}'
          f'{"（已截断！）" if b_id_trunc else ""}')

    # ---- 反向：全部 16 个判胜目标 ----
    seeds = gui_targets(m, n)
    print(f'  反向 BFS（全部判胜目标 {len(seeds)} 个）...', flush=True)
    b_all, b_all_trunc, n_ball = backward_bfs(seeds, step, m, n, max_states,
                                              move_cache, pred_cache, fwd_preds,
                                              cross_errors)
    print(f'  反向(全部目标): 状态 {n_ball:,}，形态 {len(b_all)}'
          f'{"（已截断！）" if b_all_trunc else ""}')

    # ---- 正向 vs 反向 ----
    fwd_states = sum(len(v) for v in fwd.values())
    bid_states = sum(len(v) for v in b_id.values())
    only_fwd = 0
    only_fwd_sample = None
    for shape, labs in fwd.items():
        bl = b_id.get(shape, set())
        d = labs - bl
        only_fwd += len(d)
        if d and only_fwd_sample is None:
            only_fwd_sample = (shape, next(iter(d)))
    solvable_not_shuffled = 0
    for shape, labs in b_id.items():
        solvable_not_shuffled += len(labs - fwd.get(shape, set()))
    print(f'  打乱可达但无法复原到行主序 = {only_fwd:,}'
          + (f'（样例：\n{render(*only_fwd_sample)}）' if only_fwd_sample else ''))
    print(f'  可解但打乱到不了 = {solvable_not_shuffled:,}')
    d4_bonus = n_ball - n_bid
    print(f'  D4 目标额外可解状态 = {d4_bonus:,}')
    # D4 额外状态的性质：它们不在恒等反向集合里，检查是否为候选
    # （打乱不可达的态不受着色类不变量约束，应为非候选 → 对实际游玩无意义）
    d4_extra_nec_ok = 0
    d4_extra_nec_bad = 0
    for shape, labs in b_all.items():
        base = b_id.get(shape, set())
        for lb in labs - base:
            if is_candidate(shape, lb):
                d4_extra_nec_ok += 1
            else:
                d4_extra_nec_bad += 1
    print(f'  D4 额外状态中: 候选(违反打乱不变量?) {d4_extra_nec_ok:,}，'
          f'非候选(打乱不可达, 无实际意义) {d4_extra_nec_bad:,}')

    # ---- 定理检验 ----
    # 严格口径（恒等目标，行主序）：可解 == 候选（逐块着色类 == 家格着色类）
    # 必要性：反向(恒等) 全部落在候选集内（应恒成立）
    nec_viol = 0
    nec_sample = None
    for shape, labs in b_id.items():
        for lb in labs:
            if not is_candidate(shape, lb):
                nec_viol += 1
                if nec_sample is None:
                    nec_sample = (shape, lb)
    # 充分性：候选集 ⊆ 反向(恒等)，逐形态比大小 + 必要时枚举差集
    insuf = []
    checked_shapes = set(fwd) | set(b_id)
    for shape in checked_shapes:
        cc = candidate_count(shape)
        sol = len(b_id.get(shape, set()))
        if cc != sol:
            insuf.append((shape, sol, cc))
    print(f'  定理检验「可解 == 候选」: 必要性违例 {nec_viol}'
          + (f'（样例：\n{render(*nec_sample)}）' if nec_sample else ''))
    print(f'  充分性不符的形态数 = {len(insuf)} / {len(checked_shapes)}'
          + ('' if not fwd_trunc and not b_id_trunc else '（有截断，仅供参考）'))
    for shape, sol, cc in insuf[:3]:
        cand = candidate_enum(shape)
        if cand is None:
            print(f'    形态候选 {cc:,} 可解 {sol:,}（候选过大未枚举）:\n'
                  f'{render(shape, sorted(b_id.get(shape, [(0, 0)]))[0] if b_id.get(shape) else tuple(range(1, K + 1)))}')
        else:
            miss = cand - b_id.get(shape, set())
            extra = b_id.get(shape, set()) - cand
            print(f'    形态: 候选 {len(cand)} 可解 {sol}，'
                  f'候选中不可解 {len(miss)}，可解中非候选 {len(extra)}')
            if miss:
                lab = next(iter(miss))
                print(f'    候选但不可解的样例：\n{render(shape, lab)}')

    # ---- 广义口径（GUI 判胜：全部 D4 × 平移偏移）：可解 == 广义候选 ----
    # 前提：形态原版可解 ⟺ 该形态出现在反向(全部目标)里
    #   （若原版可解，把目标标法沿原版路径逆运输即得可解标法；反之显然）
    gmaps = g_class_maps(m, n, step)
    g_nec = 0
    g_nec_sample = None
    for shape, labs in b_all.items():
        for lb in labs:
            if not g_ok(shape, lb, gmaps):
                g_nec += 1
                if g_nec_sample is None:
                    g_nec_sample = (shape, lb)
    print(f'  广义定理「可解 == 广义候选」: 必要性违例 = {g_nec}'
          + (f'（样例：\n{render(*g_nec_sample)}）' if g_nec_sample else ''))
    if b_all_trunc:
        print('  充分性: 反向(全部目标)已截断，跳过（需更大上限或生成元法）')
    else:
        g_insuf = []
        for shape, labs in b_all.items():
            gc = g_count(shape, gmaps)
            if gc != len(labs):
                g_insuf.append((shape, len(labs), gc))
        print(f'  充分性不符的形态数 = {len(g_insuf)} / {len(b_all)}')
        for shape, sol, gc in g_insuf[:3]:
            gset = g_enum(shape, gmaps)
            if gset is None:
                print(f'    形态广义候选 {gc:,} 可解 {sol:,}（过大未枚举）')
                continue
            miss = gset - b_all[shape]
            extra = b_all[shape] - gset
            print(f'    形态: 广义候选 {len(gset)} 可解 {sol}，'
                  f'候选中不可解 {len(miss)}，可解中非候选 {len(extra)}')
            if miss:
                print(f'    广义候选但不可解的样例：\n{render(shape, next(iter(miss)))}')

    # ---- 前驱交叉核验 ----
    if cross_errors:
        print(f'  ⚠ 前驱交叉核验告警 {len(cross_errors)} 条: {cross_errors[:5]}')
    else:
        print('  前驱交叉核验: 正向已知前驱全部被反向生成覆盖 ✓')

    print(f'  总耗时 {time.time() - t0:.0f}s')


def main():
    ap = argparse.ArgumentParser(description='数字谜题可达排列群实验')
    ap.add_argument('m', type=int)
    ap.add_argument('n', type=int)
    ap.add_argument('step', type=int)
    ap.add_argument('--max-states', type=int, default=1_500_000,
                    help='单个方向的状态数上限（默认 150 万）')
    ap.add_argument('--skip-backward', action='store_true', help='只跑正向')
    args = ap.parse_args()
    solve(args.m, args.n, args.step, args.max_states, args.skip_backward)


if __name__ == '__main__':
    main()
