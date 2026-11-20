# -*- coding: utf-8 -*-
"""三維聚攏求解器（P2 MVP）。

只做「單次聚攏」：每一步在全部合法三維滑動裡挑「與 m×n×d 目標盒重疊最多」
的一步，連續 patience 步無改進就停在歷史最優。**不承諾還原**，也不接
查表 / PDB / IDA* / 混合；那些算法仍是二維語義，不能直接套到 (r,c,d)。

與二維 gather 的差別：
  · 動作族 r/c/d，每族四條平行方向（不是二維的 h/v 四向）；
  · 聚攏度用 3D 前綴和枚舉目標盒，允許 48 對稱裡的 6 種軸排列；
  · 快照走 EngineGame.snapshot_state / restore_state。

2026-11-20 第一輪優化（詳細數據見 docs/solver/三维聚拢基准与优化记录_2026-11-20.md）：
  · 候選改為引擎座標層 full 枚舉（逐連通分量、帶 rep_cell），
    評估不再逐候選改盤面；
  · Φ 預篩 + top-k 完整指標；
  · 實心盒目標走快速還原判定，自訂目標回落引擎判據。

2026-11-20 第二輪（逐洞段收口，方案 P1）：
  · 默認 4 段 × 1200 節點：聚攏停滯後每段只要求「洞 -1」，段內允許分數
    持平/下降，最佳優先（洞數, 塊到窗口的曼哈頓距離和）展開；
  · 一段命中就落盤，並用實際盤面重算指標、要求重疊真的 +1，否則回滾；
  · 實測終態 +0.03 ~ +0.06、代價 0.3 ~ 0.7s（三檔尺寸，見優化記錄 §11）。

返回字典鍵與 `gather_solver.gather_solve` 對齊，GUI 現有播放管道可直接吃；
`form='cubic'` 供 GUI 文案分流。
"""
import heapq
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


def _axis_mod_counts(coords, axis, step):
    counts = [0] * step
    for p in coords:
        counts[int(p[axis]) % step] += 1
    return counts


def _axis_window_counts(length, start, step):
    """長度 length、起點殘餘 start 的實心窗口，每個 mod 類別有多少格。"""
    q, rem = divmod(int(length), step)
    counts = [q] * step
    for k in range(rem):
        counts[(start + k) % step] += 1
    return counts


def cubic_mod_constraints(coords, dims, step):
    """三維目標盒的 mod 不變量約束。

    與二維 `detect_target_corner` 同一個來源：滑動每步沿一軸走 step，
    所以每塊的 `(r%step, c%step, d%step)` 不變；實心目標盒也必須有同樣的
    三維 mod 分佈。對「邊長不被 step 整除」的軸，窗口起點的餘數因此被鎖定；
    整除了的軸任意。

    返回 `{orientation: (r_res, c_res, d_res)}`，每項是 `frozenset[int]`
    或 `None`（None = 該軸無約束）。若整盤完全沒有可判定的約束（例如
    step=1、三軸都可整除、或當前不是實心目標分佈），回 None。

    只按**軸邊長**判：三維長方體的軸排列仍是 6 種，不引入 48 對稱裡的
    反射/旋轉重複；對實心盒而言反射不改變軸長，旋轉就是軸置換。
    """
    step = int(step or 1)
    if step <= 1 or not coords:
        return None
    dims = tuple(int(v) for v in dims)
    # 先看是否至少有一軸不被 step 整除；三軸全整除時任何起點都等價。
    if all(v % step == 0 for v in dims):
        return None

    block_axis = tuple(_axis_mod_counts(coords, ax, step) for ax in range(3))
    out = {}
    for (a, b, c) in _unique_orientations(dims):
        lengths = (a, b, c)
        residues = []
        constrained = False
        for ax, length in enumerate(lengths):
            if length % step == 0:
                residues.append(None)
                continue
            # 另一軸的格數：把「一條線上的 mod 計數」放大成整盒的三維
            # 邊際總數，才能和 block_axis 的總數直接比。
            others = 1
            for other_ax in range(3):
                if other_ax != ax:
                    others *= lengths[other_ax]
            matches = frozenset(
                r for r in range(step)
                if [v * others for v in _axis_window_counts(length, r, step)]
                == block_axis[ax])
            if len(matches) == 1:
                residues.append(matches)
                constrained = True
            else:
                # 0 個（當前不是實心目標分佈/自訂目標）或多個（分佈對稱）
                # 都不是客觀可判定的約束；不強加，避免把合法窗口排掉。
                residues.append(None)
        out[(a, b, c)] = tuple(residues)
    return out if constrained else None


def _residue_allowed(residues, axis, value, step):
    """residues 是 (set|None,...)，value 是窗口起點座標。"""
    if residues is None:
        return True
    allowed = residues[axis]
    return allowed is None or (int(value) % step) in allowed


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
    """目標盒與實際佔用格的交集數；盒可部分超出邊界。

    ⚠️ 這是候選評估的內環：一次 4×4×4 求解實測 440 萬次調用，
    原版每次調用要跑 6 個 `min`/`max` builtin（cProfile 佔 15% 牆鐘）。
    這裡改成純三元比較的夾取，語義（含越界回 0）完全不變。
    """
    x0, y0, z0, a, b, c = box
    lx, ly, lz = lo
    sx, sy, sz = size
    xa = x0 if x0 > lx else lx
    xb = x0 + a - 1
    xb = xb if xb < lx + sx - 1 else lx + sx - 1
    ya = y0 if y0 > ly else ly
    yb = y0 + b - 1
    yb = yb if yb < ly + sy - 1 else ly + sy - 1
    za = z0 if z0 > lz else lz
    zb = z0 + c - 1
    zb = zb if zb < lz + sz - 1 else lz + sz - 1
    if xa > xb or ya > yb or za > zb:
        return 0
    x0i, x1i = xa - lx, xb - lx + 1
    y0i, y1i = ya - ly, yb - ly + 1
    z0i, z1i = za - lz, zb - lz + 1
    return (pref[x1i][y1i][z1i] - pref[x0i][y1i][z1i]
            - pref[x1i][y0i][z1i] - pref[x1i][y1i][z0i]
            + pref[x0i][y0i][z1i] + pref[x0i][y1i][z0i]
            + pref[x1i][y0i][z0i] - pref[x0i][y0i][z0i])


def cubic_metrics(coords, dims, step=None, mod_constraints=None):
    """當前塊座標 vs m×n×d 實心盒的最大重疊。

    `score = 最大重疊 / 總塊數`，`fill_rate = 最大重疊 / 目標盒體積`。
    目標盒允許 6 種軸排列（立方體的 48 對稱對實心長方體只剩軸置換）。

    `step` / `mod_constraints`：三維 mod 不變量。`step>1` 時只接受
    「窗口起點餘數符合目標盒 mod 分佈」的窗口；`mod_constraints` 可由
    `cubic_mod_constraints()` 預先算好，求解器一輪只算一次。step=None 或
    step=1 = 不套約束（測試/一般查詢）。
    """
    dims = tuple(int(v) for v in dims)
    step = int(step) if step is not None else 1
    if mod_constraints is None and step > 1:
        mod_constraints = cubic_mod_constraints(coords, dims, step)
    total = len(coords)
    if total == 0:
        return {'score': 0.0, 'overlap': 0, 'bbox': (0, 0, 0),
                'fill_rate': 0.0, 'volume': 0, 'window': None,
                'holes': 0, 'outside': 0,
                'mod_constraints': mod_constraints}

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
        residues = (mod_constraints.get((a, b, c))
                    if mod_constraints else None)
        # 只需要枚舉「盒面至少貼到某個佔用格」的起點；兩端各多一格的
        # 越界起點不可能得到更多交集。
        # step=1（residues 為 None）時跳過逐起點的餘數判定——這是 4×4×4
        # 實測最常見的分支，`_residue_allowed` 每次調用本身的開銷在
        # cProfile 裡能佔 1%+。
        if residues is None:
            for x0 in range(lo[0] - a + 1, hi[0] + 1):
                for y0 in range(lo[1] - b + 1, hi[1] + 1):
                    for z0 in range(lo[2] - c + 1, hi[2] + 1):
                        n = _box_count(pref, lo, span, (x0, y0, z0, a, b, c))
                        if best_window is None or n > best_overlap:
                            best_overlap = n
                            best_window = (x0, y0, z0, a, b, c)
                            best_volume = volume
            continue
        for x0 in range(lo[0] - a + 1, hi[0] + 1):
            if not _residue_allowed(residues, 0, x0, step):
                continue
            for y0 in range(lo[1] - b + 1, hi[1] + 1):
                if not _residue_allowed(residues, 1, y0, step):
                    continue
                for z0 in range(lo[2] - c + 1, hi[2] + 1):
                    if not _residue_allowed(residues, 2, z0, step):
                        continue
                    n = _box_count(pref, lo, span, (x0, y0, z0, a, b, c))
                    if best_window is None or n > best_overlap:
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
        # 【新增】洞與盒外塊分開回報（方案 §2.3 的第一步）：`holes` 是
        # 目標盒內的格數缺口，`outside` 是落在最佳窗口之外的塊數。對
        # 實心盒兩者相等；`protrusion` 需要目標形狀本身才能算，這裡
        # 不給假數據（自訂 goal_pattern 待接）。
        'holes': best_volume - best_overlap,
        'outside': total - best_overlap,
        'mod_constraints': mod_constraints,
    }


# ---------------------------------------------------------------------------
# 動作
# ---------------------------------------------------------------------------
def _window_overlap(coords, window):
    """點集落在某個目標盒窗口內的數量（O(塊數)，不做前綴和）。"""
    if not window:
        return 0
    x0, y0, z0, a, b, c = window
    x1, y1, z1 = x0 + a, y0 + b, z0 + c
    n = 0
    for p in coords:
        if x0 <= p[0] < x1 and y0 <= p[1] < y1 and z0 <= p[2] < z1:
            n += 1
    return n


def _candidate_phi(coords, window):
    """候選的廉價聚攏代理值 Φ（方案 §1.4 的預篩口徑）。

    取兩個 O(塊數) 的量的大者：
      ① 候選落在「當前歷史最優窗口」裡的塊數——大多數改善動作只是
         把塊推進同一個窗口；
      ② 以候選自身最小角貼合、沿用最優窗口形狀的窗口裡的塊數——
         覆蓋「最優窗口整體平移」這類動作。
    都不是完整指標（不含 6 軸排列），只用来排序取 top-k 再算完整
    `cubic_metrics`；完整指標仍是選動作的唯一依據。
    """
    if not coords:
        return 0
    best = _window_overlap(coords, window)
    lo = (min(p[0] for p in coords), min(p[1] for p in coords),
          min(p[2] for p in coords))
    if window:
        tight = (lo[0], lo[1], lo[2], window[3], window[4], window[5])
    else:
        return best
    return max(best, _window_overlap(coords, tight))

def _gap_dirs(game, gap_type):
    from engine.compat import direction_table
    fam = next(f for f in game.spec.seam_families if f.name == gap_type)
    table = direction_table(game.spec)
    return tuple(sorted(letter for letter, vec in table.items()
                        if vec in fam.parallel))


def _side_rank(side):
    return 0 if side in ('above', 'low', 0) else 1


def _side_block(game, gap_type, line, side, rep_cell=None):
    """取該側的代表塊；`rep_cell` 給定時優先定位到同一塊。

    三維一條縫的同一側可以有多個連通分量。只按「同側第一塊」取代表塊，
    回放時 `opt` 會選到另一個分量——與求解時選中的那一步不是同一個動作
    （方案 §2.1 指出的唯一真缺口）。`rep_cell` 是求解器動作的第五分量。
    """
    want = _side_rank(side)
    if rep_cell is not None:
        target = tuple(rep_cell[:3])
        for b in game.blocks:
            if tuple(b.location[:3]) != target:
                continue
            if game.side_of(gap_type, line, target) == want:
                return b
        # rep 失效（盤面被外部改寫）：退回同側首塊，不讓回放直接崩
    for b in game.blocks:
        if game.side_of(gap_type, line, tuple(b.location)) == want:
            return b
    return None


def _clear_opt(game):
    for b in game.blocks:
        b.be_opted = False


def _apply_cubic_action(game, action, step):
    """執行一條 (gap_type, line, side, direction[, rep_cell])。

    成功回 (rep, final_positions)。第五分量是 rep_cell：GUI 播放側已按它
    定位目標塊，這裡也必須按它選代表塊，否則「同一側多分量」的局面裡
    求解與回放會選到不同分量。
    """
    gap_type, line, side, direction = action[:4]
    rep_cell = action[4] if len(action) >= 5 else None
    if not game.is_valid_gap(gap_type, line) or not game.side_has_blocks(
            gap_type, line, side):
        return None
    _clear_opt(game)
    rep_block = _side_block(game, gap_type, line, side, rep_cell)
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
    """全部「幾何上值得一試」的三維滑動；非法由 apply 逐步校驗。

    ⚠️ 這是舊的近似枚舉（每 (縫, 側, 方向) 只取同側首塊所在分量），
    保留給外部調用與差分對照；求解主迴圈已改用 `cubic_candidates`
    （逐分量、帶 rep_cell、純座標落點）。
    """
    out = []
    for gap_type, line in game.all_gaps():
        dirs = _gap_dirs(game, gap_type)
        for side in ('above', 'below'):
            if not game.side_has_blocks(gap_type, line, side):
                continue
            for direction in dirs:
                out.append((gap_type, line, side, direction))
    return out


def cubic_candidates(game, step):
    """用引擎座標層枚舉全部合法三維滑動，並直接算出落點座標。

    方案 P0 第 3–4 項的落地方式（不重寫幾何，借用引擎的純座標層）：
      · `Board.legal_moves(step)` 本來就是「每條縫每一側、每一連通分量、
        每平行方向、逐步校驗」，是三維的完整動作空間；舊枚舉只取同側
        首塊所在分量，同側多分量時漏動作 / 選錯分量。
      · `Move.moved` 自帶被移動鍵集，落點 = moved + step·方向 ∪ 其餘，
        候選評估**不再 snapshot → opt → try_move → restore**。原版每個
        候選都 restore_state 一次（重建全部 Block），4×4×4 剖析裡這條鏈
        佔約四成牆鐘。
      · 連通判據走板型自帶的 6 鄰接 lattice，不另造 3D bitboard——另造
        一份會與引擎的連通語義分叉，正是方案 §1.3 提醒的「6 鄰接」坑。
      · 動作帶第五分量 rep_cell，GUI 已有按它定位目標塊的分支。

    回傳 list[(action, coords, move)]；coords 為落點點集（未排序）。
    """
    return _candidates_from_board(game, game.board, step)


def _candidates_from_board(game, board, step):
    """`cubic_candidates` 的內核：接受現成 Board。

    逐洞 segment 的搜索每層由「純座標集」重建 Board（`Board.from_points`），
    不必 restore_state 重建整盤 Block 對象。
    """
    scale = game.spec.lattice.scale
    if scale != 1:
        raise ValueError(
            f'cubic_candidates 假定立方格 scale=1，收到 {scale!r}')
    keys = board.keys
    if not keys:
        return []
    from engine.compat import direction_table
    table = direction_table(game.spec)
    letter_of = {vec: letter for letter, vec in table.items()}
    fam_by_name = {f.name: f for f in game.spec.seam_families}
    out = []
    for mv in board.legal_moves(int(step)):
        fam = fam_by_name[mv.family]
        line = (mv.t - 1) / fam.line_scale
        line = int(line) if line == int(line) else line
        side = 'above' if mv.side < 0 else 'below'
        letter = letter_of.get(mv.direction)
        if letter is None:
            # 動作方向不在方向字母表裡 = 板型配置壞了，顯式報錯
            raise ValueError(
                f'方向 {mv.direction!r} 不在板型 {game.spec.name!r} 的字母表裡')
        moved_pts = {k[0] for k in mv.moved}
        rest_pts = [k[0] for k in keys if k[0] not in moved_pts]
        delta = tuple(int(step) * x for x in mv.direction)
        coords = [(p[0] + delta[0], p[1] + delta[1], p[2] + delta[2])
                  for p in moved_pts]
        coords.extend(rest_pts)
        rep = tuple(min(moved_pts))
        out.append(((mv.family, line, side, letter, rep), coords, mv))
    return out


# ---------------------------------------------------------------------------
# 主求解
# ---------------------------------------------------------------------------
def _solid_goal_signature(spec, dims):
    """目標盒是否「實心長方體」；是則回 `(塊數, 排序後邊長)`，否則 None。

    給定這個簽名後，還原判定不必每輪跑引擎 `is_solved()`——立方板型的
    `is_solved` 走 48 對稱的 `canonical_key()`，3×3×3 實測一次 ~4.5ms，
    每輪調用會佔兩成牆鐘。實心盒的等價快判：塊數 == 目標體積、最佳窗口
    重疊 == 塊數、且邊界盒排序後等於目標邊長排序（48 對稱對實心盒只剩
    軸置換，反射不改變形狀）。

    自訂 `goal_pattern`（三維創造模式）不是實心盒時回 None，調用方繼續
    走引擎真判據，不能拿快判徑硬套。
    """
    goal = [tuple(b.point[:3]) for b in spec.goal_blocks]
    volume = dims[0] * dims[1] * dims[2]
    if not goal or len(goal) != volume or len(set(goal)) != len(goal):
        return None
    lo = tuple(min(p[i] for p in goal) for i in range(3))
    hi = tuple(max(p[i] for p in goal) for i in range(3))
    span = tuple(hi[i] - lo[i] + 1 for i in range(3))
    if tuple(sorted(span)) != tuple(sorted(dims)):
        return None
    return (len(goal), tuple(sorted(dims)))


def _solved_fast(coords, met, signature):
    """實心盒目標的快速還原判定；`signature` 為 None 時回 None（未知）。"""
    if signature is None:
        return None
    n, dims_sorted = signature
    return (len(coords) == n and met['overlap'] == len(coords)
            and tuple(sorted(met['bbox'])) == dims_sorted)


# ---------------------------------------------------------------------------
# 逐洞 segment 收口（方案 P1）
# ---------------------------------------------------------------------------
def _holes_and_distance(coords, window):
    """洞數與「塊到窗口的曼哈頓距離和」；都是 O(塊數)。

    洞數是段目標（每段只要求 -1），距離和是段內排序的次鍵：
    「同樣少的洞，離得近的更可能真的收得進去」。
    """
    if not window:
        return 10 ** 9, 10 ** 9
    x0, y0, z0, a, b, c = window
    x1, y1, z1 = x0 + a, y0 + b, z0 + c
    holes = a * b * c
    dist = 0
    for p in coords:
        if x0 <= p[0] < x1:
            dx = 0
        else:
            dx = x0 - p[0] if p[0] < x0 else p[0] - x1 + 1
        if y0 <= p[1] < y1:
            dy = 0
        else:
            dy = y0 - p[1] if p[1] < y0 else p[1] - y1 + 1
        if z0 <= p[2] < z1:
            dz = 0
        else:
            dz = z0 - p[2] if p[2] < z0 else p[2] - z1 + 1
        dist += dx + dy + dz
        if dx == 0 and dy == 0 and dz == 0:
            holes -= 1
    return holes, dist


def _best_first_segment(game, step, dims, mod_constraints, solid_goal,
                        target_overlap, node_budget, deadline=None,
                        cancel_check=None, stats=None):
    """單個「洞數 -1」段：最佳優先搜尋，允許分數持平/下降。

    與主迴圈的差別：主迴圈是「每步都挑當下最聚攏的一步」，撞局部最優就停；
    這裡允許先拆開再裝回，只要求段結束時重疊嚴格 +1（洞 -1）。狀態只在
    純座標層展開（`Board.from_points`），不碰盤面 Block。

    回傳 `(path, nodes)`：path 是從當前局面起、達到段目標的動作序列；
    找不到回 `(None, nodes)`。
    """
    if solid_goal is None or node_budget is None or node_budget <= 0:
        return None, 0
    from engine.board import Board

    start = [tuple(b.location[:3]) for b in game.blocks]
    start_met = cubic_metrics(start, dims, step=step,
                              mod_constraints=mod_constraints)
    seq = itertools.count()
    h0, d0 = _holes_and_distance(start, start_met['window'])
    queue = [(h0, d0, next(seq), tuple(sorted(start)), ())]
    visited = {tuple(sorted(start))}
    nodes = 0
    while queue:
        if cancel_check and cancel_check():
            return None, nodes
        if deadline is not None and time.time() >= deadline:
            return None, nodes
        _h, _d, _seq, key, path = heapq.heappop(queue)
        board = Board.from_points(game.spec, [tuple(p) for p in key])
        for act, child, _mv in _candidates_from_board(game, board, step):
            nodes += 1
            if stats is not None:
                stats['closeout_nodes'] = stats.get('closeout_nodes', 0) + 1
            if cancel_check and cancel_check():
                return None, nodes
            if nodes >= node_budget:
                return None, nodes
            if deadline is not None and time.time() >= deadline:
                return None, nodes
            child_key = tuple(sorted(child))
            if child_key in visited:
                continue
            visited.add(child_key)
            met = cubic_metrics(child, dims, step=step,
                                mod_constraints=mod_constraints)
            if stats is not None:
                stats['metric_calls'] = stats.get('metric_calls', 0) + 1
            if _solved_fast(child, met, solid_goal):
                return list(path) + [act], nodes
            if met['overlap'] > target_overlap:
                return list(path) + [act], nodes
            holes, dist = _holes_and_distance(child, met['window'])
            heapq.heappush(queue, (holes, dist, next(seq), child_key,
                                   path + (act,)))
    return None, nodes


def _closeout_segments(game, step, dims, mod_constraints, solid_goal,
                       segments, node_budget, deadline, cancel_check, stats):
    """連續跑若干個逐洞段，命中一段就落盤一段。

    回傳 `(actions_added, metrics_added)`；每段落盤後都重新算實際指標並
    要求「重疊嚴格 +1」，任何回放失敗 / 沒漲都立刻回滾到段前快照。
    """
    added_actions, added_metrics = [], []
    for _seg in range(int(segments)):
        if game.is_solved():
            break
        start_coords = [tuple(b.location[:3]) for b in game.blocks]
        start_met = cubic_metrics(start_coords, dims, step=step,
                                  mod_constraints=mod_constraints)
        target = start_met['overlap']
        if target >= len(start_coords):
            break
        path, _nodes = _best_first_segment(
            game, step, dims, mod_constraints, solid_goal, target,
            node_budget, deadline=deadline, cancel_check=cancel_check,
            stats=stats)
        if not path:
            stats['closeout_stuck_overlap'] = target
            break
        pre_snap = game.snapshot_state()
        played, mets = [], []
        for act in path:
            if _apply_cubic_action(game, act, step) is None:
                break
            played.append(act)
            after = [tuple(b.location[:3]) for b in game.blocks]
            mets.append(cubic_metrics(after, dims, step=step,
                                      mod_constraints=mod_constraints))
            stats['metric_calls'] = stats.get('metric_calls', 0) + 1
        if not mets or len(played) != len(path) or \
                mets[-1]['overlap'] <= target:
            # 預測與真實落點不一致 / 沒真的漲：回滾，不污染結果
            game.restore_state(pre_snap)
            stats['closeout_replay_fail'] = \
                stats.get('closeout_replay_fail', 0) + 1
            break
        added_actions += played
        added_metrics += mets
        stats['closeout_segments_done'] = \
            stats.get('closeout_segments_done', 0) + 1
        stats['closeout_best_overlap'] = mets[-1]['overlap']
    return added_actions, added_metrics


def cubic_gather_solve(game, step=None, max_steps=240, patience=80,
                       max_wait_time=20, target_gather_score=1.0,
                       phi_prescreen_k=8, closeout_segments=4,
                       closeout_budget=1200, cancel_check=None,
                       progress_callback=None, **kwargs):
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
    # 實心盒目標的還原快判簽名（自訂 goal_pattern 回 None → 走引擎判據）。
    solid_goal = _solid_goal_signature(game.spec, dims)
    # mod 不變量只取決於初始方塊的 (r%step,c%step,d%step)；整場滑動都不變。
    # 每輪候選評估都重算會把 6×step³ 的枚舉放大到每步一次，這裡只算一次。
    mod_constraints = cubic_mod_constraints(start_coords, dims, step)
    start_metrics = cubic_metrics(start_coords, dims,
                                  step=step, mod_constraints=mod_constraints)
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
    # 【新增】展開與指標調用計數（方案 P0「展開節點數」口徑）。
    stats = {'expanded': 0, 'metric_calls': 1, 'steps': 0, 'deviations': 0,
             'prescreened': 0}
    # 【改動】當前態指標與狀態鍵跨輪攜帶：舊版每輪開頭重算一次
    # `cubic_metrics`，而上一輪結束時剛算過同一局面（每輪白算一次）。
    cur_metrics = start_metrics
    cur_hash = tuple(sorted(start_coords))
    cur_coords = start_coords

    for i in range(int(max_steps)):
        if cancel_check and cancel_check():
            reason = 'cancelled'
            break
        # 【改動】每輪的還原判定：實心盒走快判（O(1) + 一次 O(3) 排序），
        # 自訂目標才回落引擎 `is_solved()`（48 對稱 canonical，昂貴）。
        solved_now = _solved_fast(cur_coords, cur_metrics, solid_goal)
        if solved_now is None:
            solved_now = game.is_solved()
        if solved_now:
            reason = 'solved'
            break
        if max_wait_time is not None and max_wait_time > 0 and \
                time.time() - start_time >= max_wait_time:
            reason = 'timeout'
            break

        cur = cur_metrics
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

        if cur_hash in visited:
            reason = 'stuck'
            break
        visited.add(cur_hash)

        snap = game.snapshot_state()
        scored = []
        cands = cubic_candidates(game, step)
        stats['expanded'] += len(cands)
        # 【新增】Φ 預篩（方案 P1「便宜 Φ 預篩 + 前 k 個算完整指標」）：
        # 4×4×4 打亂後同側多分量使候選漲到 ~110 個，每個都算完整 3D
        # 指標會讓指標層吃掉七成牆鐘。先用 O(塊數) 的 Φ 排序，只對
        # 前 phi_prescreen_k 個算完整 cubic_metrics；k=0/None 關閉預篩。
        if phi_prescreen_k and phi_prescreen_k > 0 and \
                len(cands) > phi_prescreen_k:
            best_window = cur.get('window')
            ranked = sorted(
                ((_candidate_phi(coords, best_window), act, coords)
                 for act, coords, _mv in cands),
                key=lambda t: (-t[0], t[1]))
            stats['prescreened'] += len(cands) - len(ranked[:phi_prescreen_k])
            selected_cands = [(act, coords)
                              for _phi, act, coords in ranked[:phi_prescreen_k]]
        else:
            selected_cands = [(act, coords) for act, coords, _mv in cands]
        # 候選不再逐個改盤面：cubic_candidates 一次給出「動作 + 落點座標」，
        # 評估只做指標計算（方案 P0 第 3–4 項）。
        for act, coords in selected_cands:
            met = cubic_metrics(coords, dims, step=step,
                                mod_constraints=mod_constraints)
            stats['metric_calls'] += 1
            nh = tuple(sorted(coords))
            scored.append((met['score'], met['overlap'],
                           -int(met['bbox'][0] * met['bbox'][1] * met['bbox'][2]),
                           nh in visited, act, act[4], nh, met))

        if not scored:
            reason = 'no_candidates'
            break
        # 選未訪問優先；再按聚攏度 / 重疊 / 較大邊界盒 / 動作字典序。
        # 排序鍵與舊版逐位一致（只多帶了 met，不參與比較）。
        scored.sort(key=lambda t: (t[3], -t[0], -t[1], t[2], t[4]))
        _, _, _, _, best_action, rep, nh, end_met = scored[0]

        res = _apply_cubic_action(game, best_action, step)
        if res is None:
            game.restore_state(snap)
            reason = 'invalid_action'
            break
        actions.append(best_action)
        reps.append(rep)
        stats['steps'] += 1
        # 落點自檢：候選預測的座標集必須等於真實落點。rep 選錯分量 /
        # 外部改過盤面時兩者會分叉——此時以真實落點重算指標，不把
        # 預測值當結果（靜默沿用會讓 best / trace 都失真）。
        after = tuple(sorted(tuple(b.location[:3]) for b in game.blocks))
        if after != nh:
            stats['deviations'] += 1
            end_met = cubic_metrics([tuple(p) for p in after], dims,
                                    step=step,
                                    mod_constraints=mod_constraints)
            stats['metric_calls'] += 1
            nh = after
        trace.append(end_met)
        cur_metrics = end_met
        cur_hash = nh
        cur_coords = [tuple(p) for p in after]
        # 不把「剛到達的狀態」直接標成已展開：visited 的語義是「這個狀態
        # 已經當過當前態去生成候選」。下一輪開頭會把它加入；若這一步真的
        # 原地繞回，下一輪才會判 stuck。若在這裡就 add，會把正常前進的
        # 第二步誤判成「已訪問」而一步停機。

    if not game.is_solved():
        game.restore_state(best_snap)
        actions = actions[:best_idx]
        reps = reps[:best_idx]
        trace = trace[:best_idx]

    # 【新增】逐洞 segment 收口：默認關閉（closeout_segments=0）。開啟時用
    # 剩餘時間預算，一個段只要求「洞 -1」，允許段內分數持平/下降。
    if (not game.is_solved()) and closeout_segments and closeout_segments > 0:
        deadline = (start_time + max_wait_time
                    if max_wait_time and max_wait_time > 0 else None)
        added_actions, added_metrics = _closeout_segments(
            game, step, dims, mod_constraints, solid_goal,
            closeout_segments, closeout_budget, deadline, cancel_check, stats)
        if added_actions:
            actions = list(actions) + added_actions
            reps = [a[4] for a in actions]
            trace = list(trace) + added_metrics
            reason = 'closeout'

    end_metrics = cubic_metrics([tuple(b.location[:3]) for b in game.blocks],
                                dims, step=step,
                                mod_constraints=mod_constraints)
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
        'stats': stats,
        'ignored_kwargs': ignored,
        'stochastic': False,
        'seed': None,
        'kicks': 0,
        'opt_removed': 0,
    }
