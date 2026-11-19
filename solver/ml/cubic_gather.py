# -*- coding: utf-8 -*-
"""三維聚攏求解器（P2 MVP）。

只做「單次聚攏」：每一步在全部合法三維滑動裡挑「與 m×n×d 目標盒重疊最多」
的一步，連續 patience 步無改進就停在歷史最優。**不承諾還原**，也不接
查表 / PDB / IDA* / 混合；那些算法仍是二維語義，不能直接套到 (r,c,d)。

與二維 gather 的差別：
  · 動作族 r/c/d，每族四條平行方向（不是二維的 h/v 四向）；
  · 聚攏度用 3D 前綴和枚舉目標盒，允許 48 對稱裡的 6 種軸排列；
  · 快照走 EngineGame.snapshot_state / restore_state。

返回字典鍵與 `gather_solver.gather_solve` 對齊，GUI 現有播放管道可直接吃；
`form='cubic'` 供 GUI 文案分流。
"""
import itertools
import time

_AXIS = {'r': 0, 'c': 1, 'd': 2}


# ---------------------------------------------------------------------------
# 指標
# ---------------------------------------------------------------------------
def _dims_of(game):
    return (int(game.m), int(game.n), int(game.depth))


def _unique_orientations(dims):
    return sorted(set(itertools.permutations(dims)))


def _prefix3(points, lo, size):
    """把整數三維點集建成 3D 前綴和；座標已平移到 lo。"""
    sx, sy, sz = size
    grid = [[[0] * sz for _ in range(sy)] for _ in range(sx)]
    for p in points:
        x, y, z = p[0] - lo[0], p[1] - lo[1], p[2] - lo[2]
        if 0 <= x < sx and 0 <= y < sy and 0 <= z < sz:
            grid[x][y][z] = 1
    pref = [[[0] * (sz + 1) for _ in range(sy + 1)] for _ in range(sx + 1)]
    for x in range(sx):
        for y in range(sy):
            row = grid[x][y]
            for z in range(sz):
                pref[x + 1][y + 1][z + 1] = (
                    row[z]
                    + pref[x][y + 1][z + 1]
                    + pref[x + 1][y][z + 1]
                    + pref[x + 1][y + 1][z]
                    - pref[x][y][z + 1]
                    - pref[x][y + 1][z]
                    - pref[x + 1][y][z]
                    + pref[x][y][z]
                )
    return pref, lo, size


def _box_count(pref, lo, size, box):
    """目標盒與實際佔用格的交集數；盒可部分超出邊界。"""
    x0, y0, z0, a, b, c = box
    lx, ly, lz = lo
    sx, sy, sz = size
    xa = max(x0, lx); xb = min(x0 + a - 1, lx + sx - 1)
    ya = max(y0, ly); yb = min(y0 + b - 1, ly + sy - 1)
    za = max(z0, lz); zb = min(z0 + c - 1, lz + sz - 1)
    if xa > xb or ya > yb or za > zb:
        return 0
    x0i, x1i = xa - lx, xb - lx + 1
    y0i, y1i = ya - ly, yb - ly + 1
    z0i, z1i = za - lz, zb - lz + 1
    return (pref[x1i][y1i][z1i] - pref[x0i][y1i][z1i]
            - pref[x1i][y0i][z1i] - pref[x1i][y1i][z0i]
            + pref[x0i][y0i][z1i] + pref[x0i][y1i][z0i]
            + pref[x1i][y0i][z0i] - pref[x0i][y0i][z0i])


def cubic_metrics(coords, dims):
    """當前塊座標 vs m×n×d 實心盒的最大重疊。

    `score = 最大重疊 / 總塊數`，`fill_rate = 最大重疊 / 目標盒體積`。
    目標盒允許 6 種軸排列（立方體的 48 對稱對實心長方體只剩軸置換）。
    """
    total = len(coords)
    if total == 0:
        return {'score': 0.0, 'overlap': 0, 'bbox': (0, 0, 0),
                'fill_rate': 0.0, 'volume': 0, 'window': None}

    lo = (min(p[0] for p in coords), min(p[1] for p in coords),
          min(p[2] for p in coords))
    hi = (max(p[0] for p in coords), max(p[1] for p in coords),
          max(p[2] for p in coords))
    span = (hi[0] - lo[0] + 1, hi[1] - lo[1] + 1, hi[2] - lo[2] + 1)
    pref, lo, span = _prefix3(coords, lo, span)

    best_overlap = 0
    best_window = None
    best_volume = 0
    for (a, b, c) in _unique_orientations(dims):
        volume = a * b * c
        # 只需要枚舉「盒面至少貼到某個佔用格」的起點；兩端各多一格的
        # 越界起點不可能得到更多交集。
        for x0 in range(lo[0] - a + 1, hi[0] + 1):
            for y0 in range(lo[1] - b + 1, hi[1] + 1):
                for z0 in range(lo[2] - c + 1, hi[2] + 1):
                    n = _box_count(pref, lo, span, (x0, y0, z0, a, b, c))
                    if n > best_overlap:
                        best_overlap = n
                        best_window = (x0, y0, z0, a, b, c)
                        best_volume = volume
    return {
        'score': best_overlap / total,
        'overlap': best_overlap,
        'bbox': span,
        'fill_rate': best_overlap / best_volume if best_volume else 0.0,
        'volume': best_volume,
        'window': best_window,
    }


# ---------------------------------------------------------------------------
# 動作
# ---------------------------------------------------------------------------
def _gap_dirs(game, gap_type):
    from engine.compat import direction_table
    fam = next(f for f in game.spec.seam_families if f.name == gap_type)
    table = direction_table(game.spec)
    return tuple(sorted(letter for letter, vec in table.items()
                        if vec in fam.parallel))


def _side_rank(side):
    return 0 if side in ('above', 'low', 0) else 1


def _side_block(game, gap_type, line, side):
    want = _side_rank(side)
    for b in game.blocks:
        if game.side_of(gap_type, line, tuple(b.location)) == want:
            return b
    return None


def _clear_opt(game):
    for b in game.blocks:
        b.be_opted = False


def _apply_cubic_action(game, action, step):
    """執行一條 (gap_type, line, side, direction)；成功回 (rep, final_positions)。"""
    gap_type, line, side, direction = action
    if not game.is_valid_gap(gap_type, line) or not game.side_has_blocks(
            gap_type, line, side):
        return None
    _clear_opt(game)
    rep_block = _side_block(game, gap_type, line, side)
    if rep_block is None:
        return None
    game.opt(gap_type, line, rep_block)
    selected = [b for b in game.blocks if b.be_opted]
    if not selected:
        _clear_opt(game)
        return None
    rep = tuple(selected[0].location[:3])
    final_positions, _reason = game.try_move_ex(direction, step)
    if not final_positions:
        _clear_opt(game)
        return None
    game.commit_move(final_positions)
    _clear_opt(game)
    return rep, final_positions


def enumerate_cubic_actions(game):
    """全部「幾何上值得一試」的三維滑動；非法由 apply 逐步校驗。"""
    out = []
    for gap_type, line in game.all_gaps():
        dirs = _gap_dirs(game, gap_type)
        for side in ('above', 'below'):
            if not game.side_has_blocks(gap_type, line, side):
                continue
            for direction in dirs:
                out.append((gap_type, line, side, direction))
    return out


# ---------------------------------------------------------------------------
# 主求解
# ---------------------------------------------------------------------------
def cubic_gather_solve(game, step=None, max_steps=240, patience=80,
                       max_wait_time=20, target_gather_score=1.0,
                       cancel_check=None, progress_callback=None, **kwargs):
    """三維單次聚攏：貪心最大重疊，停在歷史最優。

    `**kwargs` 吃掉 GUI 的 gather_params（stochastic / seed / kick_moves
    等），三維 MVP 暫不支持隨機踢；不靜默改結果，只忽略並在返回的
    `ignored_kwargs` 裡留痕。
    """
    if step is None:
        step = 1
    step = int(step)
    if getattr(game, 'kind', None) != 'cubic':
        raise ValueError(f'cubic_gather_solve 只接受 cubic，收到 {getattr(game, "kind", None)!r}')

    dims = _dims_of(game)
    ignored = sorted(kwargs.keys())
    start_time = time.time()
    start_coords = [tuple(b.location[:3]) for b in game.blocks]
    start_metrics = cubic_metrics(start_coords, dims)
    best_metrics = start_metrics
    best_score = start_metrics['score']
    best_snap = game.snapshot_state()
    best_idx = 0

    actions = []
    reps = []
    trace = []
    visited = set()
    no_improve = 0
    reason = 'max_steps'

    def _hash():
        return tuple(sorted(tuple(b.location[:3]) for b in game.blocks))

    for i in range(int(max_steps)):
        if cancel_check and cancel_check():
            reason = 'cancelled'
            break
        if game.is_solved():
            reason = 'solved'
            break
        if max_wait_time is not None and max_wait_time > 0 and \
                time.time() - start_time >= max_wait_time:
            reason = 'timeout'
            break

        cur = cubic_metrics([tuple(b.location[:3]) for b in game.blocks], dims)
        if target_gather_score is not None and \
                cur['score'] >= target_gather_score - 1e-9:
            reason = 'target'
            break
        if cur['score'] > best_score + 1e-9:
            best_score = cur['score']
            best_metrics = cur
            best_snap = game.snapshot_state()
            best_idx = len(actions)
            no_improve = 0
        else:
            no_improve += 1

        if progress_callback:
            progress_callback({
                'stage': 'cubic_gather', 'step': i, 'total': max_steps,
                'score': cur['score'], 'best_score': best_score,
                'overlap': cur['overlap'], 'bbox': cur['bbox'],
                'fill_rate': cur['fill_rate'],
            })

        if patience is not None and no_improve >= patience:
            reason = 'no_improve'
            break

        h = _hash()
        if h in visited:
            reason = 'stuck'
            break
        visited.add(h)

        snap = game.snapshot_state()
        scored = []
        for act in enumerate_cubic_actions(game):
            res = _apply_cubic_action(game, act, step)
            if res is None:
                game.restore_state(snap)
                continue
            rep, _final = res
            coords = [tuple(b.location[:3]) for b in game.blocks]
            met = cubic_metrics(coords, dims)
            nh = tuple(sorted(coords))
            scored.append((met['score'], met['overlap'],
                           -int(met['bbox'][0] * met['bbox'][1] * met['bbox'][2]),
                           nh in visited, act, rep, nh))
            game.restore_state(snap)

        if not scored:
            reason = 'no_candidates'
            break
        # 選未訪問優先；再按聚攏度 / 重疊 / 較小邊界盒 / 動作字典序。
        scored.sort(key=lambda t: (t[3], -t[0], -t[1], t[2], t[4]))
        _, _, _, _, best_action, rep, nh = scored[0]

        res = _apply_cubic_action(game, best_action, step)
        if res is None:
            reason = 'invalid_action'
            break
        actions.append(best_action)
        reps.append(rep)
        end_met = cubic_metrics([tuple(b.location[:3]) for b in game.blocks], dims)
        trace.append(end_met)
        # 不把「剛到達的狀態」直接標成已展開：visited 的語義是「這個狀態
        # 已經當過當前態去生成候選」。下一輪開頭會把它加入；若這一步真的
        # 原地繞回，下一輪才會判 stuck。若在這裡就 add，會把正常前進的
        # 第二步誤判成「已訪問」而一步停機。

    if not game.is_solved():
        game.restore_state(best_snap)
        actions = actions[:best_idx]
        reps = reps[:best_idx]
        trace = trace[:best_idx]

    end_metrics = cubic_metrics([tuple(b.location[:3]) for b in game.blocks], dims)
    if game.is_solved():
        best_metrics = end_metrics
        reason = 'solved'

    return {
        'type': 'gather',
        'form': 'cubic',
        'actions': actions,
        'rep_cells': reps,
        'start_coords': start_coords,
        'solved': game.is_solved(),
        'reason': reason,
        'start': start_metrics,
        'end': end_metrics,
        'best': best_metrics,
        'score': end_metrics['score'],
        'trace': trace,
        'ignored_kwargs': ignored,
        'stochastic': False,
        'seed': None,
        'kicks': 0,
        'opt_removed': 0,
    }
