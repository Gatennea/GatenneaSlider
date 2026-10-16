# -*- coding: utf-8 -*-
"""
压缩存档（replay 格式）模块。

设计目标（与用户讨论定稿）：
- 当前普通存档每个快照都存**完整 matrix**，大小为 O(步数 × 棋盘)。
- 压缩格式改为：只存「初始快照 + 末态快照(权威) + 步骤原语 + 稀疏哈希校验点」。
- 步骤用**引擎重放原语**记录（gt / line / anchor / dir / n），坐标全部相对包围盒。
- 另存「人类可读公式记号」字符串（展示/交流用），但**非重放权威**——重放只认原语。
- 载入时从初始态重放所有步骤、重建完整历史（等价于普通载入），并逐 K 步校验哈希 +
  末态校验；任何不一致→回退到末态快照并告警（保证用户拿到正确棋盘）。

适用范围：仅方形 / 数字谜题。异形（三角/米字）无直线缝、非矩形片，本设计不覆盖。

格式 (version=3, format='replay')：
{
  'version': 3,
  'format': 'replay',
  'puzzle': {'m','n','step','type':'square'|'numbered'},
  'step_count': N,
  'initial_solved': bool,            # True 时 initial 省略（由 m,n,step 重建）
  'initial': {'matrix','bounds'} | None,   # 编号谜题：matrix 为整数矩阵（值即编号）
  'final': {'matrix','bounds'},
  'steps': [ {'gt','line','anchor':[r,c],'dir','n'}, ... ],  # 引擎重放原语（坐标均为绝对，见 _apply_step）
  # 注：坐标存绝对（与 move_info 一致）最稳健——重放包围盒可能漂移，相对值会错位；
  #     「相对位置」要求仅针对 formulas 人类记号，steps 只需可正确重放。
  'formulas': [ '...', ... ],        # 人类可读记号，与 steps 平行（展示用）
  'checkpoints': [ {'at':int,'hash':str}, ... ],             # 隔 CHECKPOINT_EVERY 步的态哈希
  'readonly': bool (可选),
  'checksum': str
}
"""

import json
import hashlib
from game import Block, SliderMatrix
from puzzle_types import create_puzzle

CHECKPOINT_EVERY = 10

_DIR_FORMULA = {'w': 'R', 's': "R'", 'a': 'U', 'd': "U'"}


# ---------------------------------------------------------------- 基础工具
def _snapshot_cells(snap) -> frozenset:
    """快照 → 绝对坐标格集 {(r, c)}。"""
    bounds = snap['bounds']
    mnr = bounds['min_row']
    mnc = bounds['min_col']
    return frozenset(
        (mnr + i, mnc + j)
        for i, row in enumerate(snap['matrix'])
        for j, v in enumerate(row) if v)


def _game_cells(game) -> frozenset:
    return frozenset(tuple(b.location) for b in game.blocks)


def _snapshot_field(snap) -> dict:
    """快照 → 落盘字段（matrix+bounds；编号直接存在整数矩阵里，无需 numbers）。"""
    return {'matrix': snap['matrix'], 'bounds': snap['bounds']}


def _snapshot_field_from_game(game) -> dict:
    """从游戏对象抽取当前态的落盘字段（编号已在整数 matrix 中）。"""
    return {'matrix': [row[:] for row in game.matrix],
            'bounds': dict(game.matrix_bounds)}


def _game_from_snapshot(snap, m, n, numbered: bool = False) -> SliderMatrix:
    """用快照的整数 matrix/bounds 重建一个 SliderMatrix（仅方形/数字）。

    numbered=True 时 matrix 的值即编号（0=空），据此还原块编号。
    """
    bounds = snap['bounds']
    mnr = bounds['min_row']
    mnc = bounds['min_col']
    cells = []
    for i, row in enumerate(snap['matrix']):
        for j, v in enumerate(row):
            if v:
                cells.append((mnr + i, mnc + j))
    g = SliderMatrix(m, n)
    g.blocks = [Block([r, c]) for (r, c) in cells]
    if numbered:
        for b in g.blocks:
            # 编号即矩阵值（matrix[行][列]）
            ri = b.location[0] - mnr
            ci = b.location[1] - mnc
            b.number = snap['matrix'][ri][ci]
    g.matrix_bounds = dict(bounds)
    g.numbered = numbered
    g.update_matrix()  # 依据块位置重建矩阵（包围盒收紧到当前棋形）
    return g


def _state_hash(game) -> str:
    """游戏当前态的稳定哈希（matrix + 编号），用于校验点与末态比对。"""
    # 编号必须序列化成 [r, c, 编号] 列表（排序保稳）：dict 用 tuple 当 key
    # 会让 json.dumps 抛 TypeError——数字谜题此前因此在压缩分支必炸。
    nums = sorted([b.location[0], b.location[1], b.number]
                  for b in game.blocks
                  if getattr(b, 'number', None) is not None)
    payload = json.dumps({'m': game.matrix, 'n': nums}, sort_keys=True,
                         ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _checksum(data) -> str:
    # 与 file_ops._compute_checksum 使用完全一致的正则化（compact 分隔符），
    # 否则压缩存档的校验和在载入时被 file_ops 重新计算会对不上、误报损坏。
    d = {k: v for k, v in data.items() if k != 'checksum'}
    s = json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def verify_checksum(data) -> bool:
    return data.get('checksum') == _checksum(data)


def is_compressed(save_data) -> bool:
    return isinstance(save_data, dict) and save_data.get('format') == 'replay'


# ---------------------------------------------------------------- 公式记号（展示用）
def _components(blocks):
    """blocks: 坐标集合；返回其中 4-连通分量列表（每项为 frozenset）。"""
    remaining = set(blocks)
    comps = []
    while remaining:
        seed = next(iter(remaining))
        stack = [seed]
        comp = set()
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp.add(cur)
            r, c = cur
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (r + dr, c + dc)
                if nb in remaining and nb not in comp:
                    stack.append(nb)
        remaining -= comp
        comps.append(frozenset(comp))
    return comps


def _encode_formula(game, gt, gap_line, direction, n) -> str:
    """把一步移动编码成人类可读记号（展示用，非重放权威）。

    规则（用户定稿，魔方记号习惯）：
    - 前缀 j-：选中第 j 个连通部分（默认 1，省略）；
    - a：选中区域沿缝垂直方向的跨度（默认 1，省略）；
    - 方向字母：上→R、左→U；反向加 '（下→R'、右→U'）；
    - 后缀 d：移动多少步长倍数（默认 1，省略）。
    """
    moved = frozenset((b.location[0], b.location[1])
                      for b in game.blocks if b.be_opted)
    if not moved:
        return ''
    if gt == 'h':
        if max(r for r, _ in moved) <= gap_line:
            side_blocks = {tuple(b.location) for b in game.blocks
                          if b.location[0] <= gap_line}
        else:
            side_blocks = {tuple(b.location) for b in game.blocks
                          if b.location[0] > gap_line}
        comps = _components(side_blocks)
        comps.sort(key=lambda comp: min(r for r, _ in comp))
        a = max(r for r, _ in moved) - min(r for r, _ in moved) + 1
    else:
        if max(c for _, c in moved) <= gap_line:
            side_blocks = {tuple(b.location) for b in game.blocks
                          if b.location[1] <= gap_line}
        else:
            side_blocks = {tuple(b.location) for b in game.blocks
                          if b.location[1] > gap_line}
        comps = _components(side_blocks)
        comps.sort(key=lambda comp: min(c for _, c in comp))
        a = max(c for _, c in moved) - min(c for _, c in moved) + 1
    j = comps.index(moved) + 1
    letter = _DIR_FORMULA[direction]
    parts = []
    if j > 1:
        parts.append(f"{j}-")
    if a > 1:
        parts.append(f"{a}")
    parts.append(letter)
    if n > 1:
        parts.append(f"{n}")
    return ''.join(parts)


# ---------------------------------------------------------------- 重放原语
def _apply_step(game, step):
    """在 game 上应用一步重放原语（坐标均为绝对，与 move_info 一致）。

    返回 (final_positions, reason, pre_positions)；reason 非空表示失败，
    pre_positions 为提交前（移动前）被选中块的坐标列表，用于重建 move_info。
    """
    gt = step['gt']
    line_abs = step['line']            # 绝对缝位置（opt 直接吃绝对值）
    ar, ac = step['anchor']            # 绝对锚块坐标
    anchor = None
    for b in game.blocks:
        if b.location[0] == ar and b.location[1] == ac:
            anchor = b
            break
    if anchor is None:
        return None, 'anchor_not_found', None
    game.opt(gt, line_abs, anchor)
    # 提交前采集移动前坐标（此时 be_opted 块仍在原位置）
    pre = [list(b.location) for b in game.blocks if b.be_opted]
    final, reason = game.try_move_ex(step['dir'], step['n'])
    if final:
        game.commit_move(final)
        game.update_matrix()  # 重放后刷新矩阵/包围盒（checkpoint 哈希 + 快照矩阵正确）
    return final, reason, pre


# ---------------------------------------------------------------- 压缩（普通→压缩）
def _iter_moves(snapshots):
    for snap in snapshots[1:]:
        ms = snap.get('moves')
        if not ms:
            mi = snap.get('move_info')
            ms = [mi] if mi else []
        for m in ms:
            if m:
                yield m


def compress_snapshots(puzzle, snapshots, step_count, readonly=False) -> dict:
    """从普通存档的快照序列生成压缩存档 dict（纯数据，不含 pygame）。

    snapshots[0] 为初始参考态；其余每个 move_info 对应一步。
    用引擎**重放**生成步骤的相对坐标（正确处理合并快照的中间态），并沿途
    计算稀疏校验点、验证末态一致。
    """
    m = puzzle['m']
    n = puzzle['n']
    step = puzzle['step']
    kind = puzzle.get('type', 'square')
    if kind not in ('square', 'numbered'):
        raise ValueError(f"压缩存档不支持形态：{kind}")

    initial = snapshots[0]
    final = snapshots[-1]
    game = _game_from_snapshot(initial, m, n, numbered=(kind == 'numbered'))  # 重放起点 = 初始态

    steps = []
    formulas = []
    checkpoints = []
    applied = 0
    for mv in _iter_moves(snapshots):
        gt = mv['gap_type']
        gap_line = mv['gap_line']
        direction = mv['direction']
        nstep = mv['step']
        moved = mv['moved_positions']  # 移动前坐标
        if not moved:
            raise ValueError("压缩失败：move_info 缺少 moved_positions")
        ar0, ac0 = moved[0]
        anchor = None
        for b in game.blocks:
            if b.location[0] == ar0 and b.location[1] == ac0:
                anchor = b
                break
        if anchor is None:
            raise ValueError("压缩失败：找不到锚块（存档可能损坏）")
        game.opt(gt, gap_line, anchor)
        # 公式在提交前（移动前位置）编码——移动后块位移，相对旧缝线的
        # 「第几个部分」会错位
        formula = _encode_formula(game, gt, gap_line, direction, nstep)
        final_pos, reason = game.try_move_ex(direction, nstep)
        if not final_pos:
            raise ValueError(f"压缩失败：第 {applied + 1} 步重放不合法（{reason}）")
        game.commit_move(final_pos)
        game.update_matrix()  # 重放后刷新矩阵/包围盒（checkpoint 哈希 + 下一步坐标基准）
        applied += 1

        # 存绝对坐标（gap_line / anchor），重放包围盒漂移也不错位
        steps.append({'gt': gt, 'line': gap_line,
                      'anchor': [ar0, ac0], 'dir': direction, 'n': nstep})
        formulas.append(formula)
        if applied % CHECKPOINT_EVERY == 0:
            checkpoints.append({'at': applied, 'hash': _state_hash(game)})

    # 末态一致性（数据自洽的最强校验）
    if _snapshot_cells(final) != _game_cells(game):
        raise ValueError("压缩失败：重放末态与存档末态不一致（存档可能损坏）")

    # 初始态始终完整存储：相对坐标（line_rel/anchor_rel）都相对「初始态包围盒」
    # 计算，载入时必须用同一包围盒重建初始态才能正确反推绝对坐标。省略初始态
    # 会改用 create_puzzle（原点可能不同）导致坐标错位，省的空间又极小，故不优化。
    init_field = _snapshot_field(initial)

    data = {
        'version': 3,
        'format': 'replay',
        'puzzle': dict(puzzle),
        # step_count 用实际重放步数（applied），保证压缩档自洽；
        # 源存档的 step_count 元数据若与真实步数不符（陈旧/损坏）也不影响。
        'step_count': applied,
        'initial_solved': False,
        'initial': init_field,
        'final': _snapshot_field(final),
        'steps': steps,
        'formulas': formulas,
        'checkpoints': checkpoints,
    }
    if readonly:
        data['readonly'] = True
    data['checksum'] = _checksum(data)
    return data


def compress_from_game(gui) -> dict:
    """从当前 GUI 的 game_history 直接生成压缩存档（保存路径）。"""
    kind = 'numbered' if getattr(gui, 'numbered', False) else 'square'
    puzzle = {'m': gui.current_m, 'n': gui.current_n,
              'step': gui.current_step, 'type': kind}
    snapshots = gui.game_history.history
    readonly = bool(getattr(gui, '_readonly', False))
    return compress_snapshots(puzzle, snapshots, gui.step_count, readonly)


# ---------------------------------------------------------------- 解压（压缩→普通）
def _normal_version_for(kind):
    return 2 if kind in ('numbered', 'triangle', 'mi') else 1


def decompress_to_normal(compressed) -> dict:
    """把压缩存档重放还原成普通存档 dict（导出 / 互转工具用）。"""
    if not is_compressed(compressed):
        raise ValueError("不是压缩存档格式")
    if not verify_checksum(compressed):
        raise ValueError("压缩存档校验和失败（文件可能已损坏）")
    puzzle = compressed['puzzle']
    m, n, step = puzzle['m'], puzzle['n'], puzzle['step']
    kind = puzzle.get('type', 'square')
    readonly = compressed.get('readonly', False)

    if compressed.get('initial_solved'):
        game = create_puzzle(m, n, step, kind=kind)
    else:
        game = _game_from_snapshot(compressed['initial'], m, n,
                                   numbered=(kind == 'numbered'))

    snapshots_out = [_snapshot_field_from_game(game)]
    steps_total = 0
    cp_by_at = {c['at']: c for c in compressed.get('checkpoints', [])}
    warned = False
    for idx, stepd in enumerate(compressed['steps']):
        final_pos, reason, pre = _apply_step(game, stepd)
        if not final_pos:
            raise ValueError(f"解压失败：第 {idx + 1} 步重放不合法（{reason}）")
        line_abs = stepd['line']   # 绝对缝位置（与原始 move_info 一致）
        mv_info = {'gap_type': stepd['gt'], 'gap_line': line_abs,
                   'direction': stepd['dir'], 'step': stepd['n'],
                   'moved_positions': [list(p) for p in pre]}
        steps_total += 1
        snap = {'matrix': [row[:] for row in game.matrix],
                'bounds': dict(game.matrix_bounds),
                'move_info': mv_info, 'moves': [mv_info],
                'steps': 1, 'step_total': steps_total}
        snapshots_out.append(snap)
        if (idx + 1) % CHECKPOINT_EVERY == 0:
            cp = cp_by_at.get(idx + 1)
            if cp and _state_hash(game) != cp['hash']:
                warned = True

    final_cells = _snapshot_cells(compressed['final'])
    if _game_cells(game) != final_cells or warned:
        raise ValueError("解压失败：重放末态与存档末态不一致（存档可能损坏）")

    data = {
        'version': _normal_version_for(kind),
        'puzzle': dict(puzzle),
        'step_count': steps_total,
        'history': {
            'history_index': len(snapshots_out) - 1,
            'snapshots': snapshots_out,
        },
    }
    if kind != 'square':
        data['puzzle']['type'] = kind
    if readonly:
        data['readonly'] = True
    data['checksum'] = _checksum(data)
    return data


# ---------------------------------------------------------------- 载入压缩存档到 GUI
def load_compressed_into_gui(gui, compressed):
    """把压缩存档载入到 GUI（等价于普通载入，但用重放重建历史 + 校验）。

    返回 (ok, warn_msg)：ok=False 表示发生了回退（已回退到末态，棋盘正确）。
    """
    if not is_compressed(compressed):
        raise ValueError("不是压缩存档格式")
    puzzle = compressed['puzzle']
    m, n, step = puzzle['m'], puzzle['n'], puzzle['step']
    kind = puzzle.get('type', 'square')
    if kind not in ('square', 'numbered'):
        raise ValueError(f"压缩存档不支持形态：{kind}")

    gui.numbered = (kind == 'numbered')
    gui.triangle_mode = False
    gui.mi_mode = False
    gui.current_m = m
    gui.current_n = n
    gui.current_step = step
    gui.game_history.reset()

    if compressed.get('initial_solved'):
        game = create_puzzle(m, n, step, kind=kind)
    else:
        game = _game_from_snapshot(compressed['initial'], m, n,
                                   numbered=(kind == 'numbered'))
    gui.game = game
    gui.game_history.history.append(_snapshot_field_from_game(game))
    gui.game_history.history_index = 0

    warned = False
    steps_total = 0
    cp_by_at = {c['at']: c for c in compressed.get('checkpoints', [])}
    try:
        for idx, stepd in enumerate(compressed['steps']):
            final_pos, reason, pre = _apply_step(gui.game, stepd)
            if not final_pos:
                warned = True
                break
            line_abs = stepd['line']   # 绝对缝位置（与原始 move_info 一致）
            mv_info = {'gap_type': stepd['gt'], 'gap_line': line_abs,
                       'direction': stepd['dir'], 'step': stepd['n'],
                       'moved_positions': [list(p) for p in pre]}
            steps_total += 1
            snap = {'matrix': [row[:] for row in gui.game.matrix],
                    'bounds': dict(gui.game.matrix_bounds),
                    'move_info': mv_info, 'moves': [mv_info],
                    'steps': 1, 'step_total': steps_total}
            gui.game_history.history.append(snap)
            if (idx + 1) % CHECKPOINT_EVERY == 0:
                cp = cp_by_at.get(idx + 1)
                if cp and _state_hash(gui.game) != cp['hash']:
                    warned = True
    except Exception as e:  # 任何异常都回退到末态
        warned = True
        print(f"压缩存档重放异常（回退末态）：{e}")

    # 末态校验
    final_cells = _snapshot_cells(compressed['final'])
    if _game_cells(gui.game) != final_cells:
        warned = True

    if warned:
        # 回退：直接用末态快照重建（棋盘正确，历史最小化）
        fg = _game_from_snapshot(compressed['final'], m, n,
                                 numbered=(kind == 'numbered'))
        gui.game = fg
        gui.game_history.history = [
            _snapshot_field_from_game(
                _game_from_snapshot(compressed['initial'], m, n,
                                   numbered=(kind == 'numbered'))
                if not compressed.get('initial_solved') else
                create_puzzle(m, n, step, kind=kind)),
            _snapshot_field_from_game(fg),
        ]
        gui.game_history.history_index = len(gui.game_history.history) - 1
        gui.step_count = compressed['step_count']
        gui._readonly = bool(compressed.get('readonly', False))
        return False, "压缩存档公式校验未通过，已按末态加载（存档可能损坏）"

    gui.game_history.history_index = len(gui.game_history.history) - 1
    gui.step_count = steps_total
    gui._readonly = bool(compressed.get('readonly', False))
    return True, ""


# ---------------------------------------------------------------- 一键转换文件
def convert_save_file(src_path, dst_path):
    """把一个存档文件转换成另一种格式写到 dst_path。

    返回 ('compressed'|'normal'|'unchanged', msg)。
    普通→压缩：compress_snapshots；压缩→普通：decompress_to_normal。
    """
    with open(src_path, 'r', encoding='utf-8') as f:
        src = json.load(f)
    if is_compressed(src):
        out = decompress_to_normal(src)
        out_kind = 'normal'
    else:
        if src.get('puzzle', {}).get('type', 'square') not in ('square', 'numbered'):
            raise ValueError("压缩存档仅支持方形/数字谜题，源存档为异形")
        hist = src.get('history', {})
        snapshots = hist.get('snapshots', [])
        if not snapshots:
            raise ValueError("源存档无快照，无法转换")
        puzzle = src['puzzle']
        kind = puzzle.get('type', 'square')
        readonly = bool(src.get('readonly', False))
        out = compress_snapshots(puzzle, snapshots, src.get('step_count', 0), readonly)
        out_kind = 'compressed'
    with open(dst_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out_kind, f"已转换并写入：{dst_path}"
