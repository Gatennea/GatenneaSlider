# -*- coding: utf-8 -*-
"""把 4_4_2 的 9 个死局（逃逸态）导出为「含复原态 → 死局态全部步骤」的游戏存档。

数据来源：experiments/math_repro/trap_paths_4_4_2.json（shuffle_trap.py 产出）。
每个逃逸态带一条从复原态出发的最短路径，每条边存的是规范坐标系下的
(parent_cells, comp, d, child_cells)。

回放方案（不走 D4 对齐）：规则对 D4 等变，所以直接在【当前绝对坐标】上
重新枚举正向边（镜像 forward_edges，另带 gap_type/line/side），挑出
规范化后等于 child 的那条边，再交给游戏引擎官方执行
（side_has_blocks → opt → try_move → commit_move），每步
GameHistory.save_snapshot(session_key=None) 一步一快照留档。

存档结构用 FileOpsMixin._build_save_data 官方拼装（自动带 checksum），
_compact_json_dumps 官方序列化，写入 save/死局存档/。
最后用 test_open_saves 的 _LoadStub 走 _load_save_data 原路 headless 验证。

用法：
  python experiments/math_repro/dump_deadend_saves.py [trap_paths 文件]
  缺省读 experiments/math_repro/trap_paths_4_4_2.json。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver import table_core as tc  # noqa: E402
from game import DIRECTIONS  # noqa: E402
from puzzle_types import create_puzzle  # noqa: E402
from history import GameHistory, snapshot_cells  # noqa: E402
from gui.file_ops import FileOpsMixin, _compact_json_dumps  # noqa: E402
from verify_coloring import parse_puzzle  # noqa: E402
from test_open_saves import _LoadStub  # noqa: E402

OUT_DIR = ROOT / 'save' / '死局存档'


# ---------------------------------------------------------------------------
# 正向边枚举（镜像 forward_closure.forward_edges，另带缝隙信息）
# ---------------------------------------------------------------------------
def _try(B, comp, d_unit, step, total):
    """把 comp 沿 d_unit 逐步推 step 次，合法则返回 (结果哈希, comp, d_unit)。"""
    non_sel = B - set(comp)
    cur = set(comp)
    for _ in range(step):
        cur = {(r + d_unit[0], c + d_unit[1]) for r, c in cur}
        if cur & non_sel:
            return None
        if not tc.is_single_connected(cur | non_sel):
            return None
    result = non_sel | cur
    if len(result) != total:
        return None
    return tc.canonicalize(frozenset(result)), frozenset(comp), d_unit


def edges_with_gap(cells, step, total):
    """[(结果哈希, comp, d_unit, gap_type, L, side), ...]——与
    forward_closure.forward_edges 同口径，只是补回缝隙三元组供引擎回放。"""
    B = set(cells)
    out = []
    rows = [r for r, _ in B]
    cols = [c for _, c in B]
    min_r, max_r = min(rows), max(rows)
    min_c, max_c = min(cols), max(cols)
    for L in range(min_r, max_r):
        for side in ('above', 'below'):
            for comp in tc._side_components(B, 'h', L, side):
                for sign in (-1, 1):
                    r = _try(B, comp, (0, sign), step, total)
                    if r:
                        out.append((*r, 'h', L, side))
    for L in range(min_c, max_c):
        for side in ('left', 'right'):
            for comp in tc._side_components(B, 'v', L, side):
                for sign in (-1, 1):
                    r = _try(B, comp, (sign, 0), step, total)
                    if r:
                        out.append((*r, 'v', L, side))
    return out


# ---------------------------------------------------------------------------
# 官方存档宿主（只承载 _build_save_data 所需状态）
# ---------------------------------------------------------------------------
class _SaveHost(FileOpsMixin):
    def __init__(self, m, n, step):
        self.game = create_puzzle(m, n, step)
        self.game_history = GameHistory()
        self.current_m = m
        self.current_n = n
        self.current_step = step
        self.step_count = 0
        self.numbered = False
        self.triangle_mode = False
        self.mi_mode = False
        self.save_readonly_flag = False


# ---------------------------------------------------------------------------
# 路径回放
# ---------------------------------------------------------------------------
def replay(host, trap, goal_cells, m, n, step, K):
    """把一条 复原态 → 逃逸态 最短路径逐步在引擎里走完并留档。"""
    game = host.game
    cur = {tuple(b.location) for b in game.blocks}
    goal = {tuple(c) for c in goal_cells}
    assert cur == goal, '引擎初始状态与规范复原态不一致'
    host.game_history.save_snapshot(game, None)   # 参考态（复原态）
    host.step_count = 0

    edges = trap['edges']
    assert len(edges) == trap['dist'], '路径长度与 BFS 距离不符'

    for i, e in enumerate(edges, 1):
        if i == 1:
            assert e['parent_cells'] == goal_cells, '首步父态不是复原态'
        child_hash = tc.canonicalize(frozenset(tuple(c) for c in e['child_cells']))
        cands = [c for c in edges_with_gap(cur, step, K) if c[0] == child_hash]
        assert cands, f'第 {i} 步：当前状态找不到指向 child 的正向边'

        done = False
        for _h, comp, d, gap_type, L, side in cands:
            if not game.side_has_blocks(gap_type, L, side):
                continue
            block = next((b for b in game.blocks
                          if tuple(b.location) in comp), None)
            if block is None:
                continue
            game.opt(gap_type, L, block)          # 官方选组
            sel = {tuple(b.location) for b in game.blocks if b.be_opted}
            if sel != set(comp):
                continue
            direction = next(k for k, v in DIRECTIONS.items() if v == d)
            positions = game.try_move(direction, step)   # 官方逐步验证
            if not positions:
                continue
            moved = {(r + d[0] * step, c + d[1] * step) for r, c in comp}
            if set(map(tuple, positions)) != moved:
                continue
            new_cur = (set(cur) - set(comp)) | moved
            if tc.canonicalize(frozenset(new_cur)) != child_hash:
                continue
            move_info = {
                'gap_type': gap_type,
                'gap_line': L,
                'direction': direction,
                'step': step,
                # 与 events.py 宏回放一致：提交前的选中组位置
                'moved_positions': [list(b.location)
                                    for b in game.blocks if b.be_opted],
            }
            game.commit_move(positions)            # 官方提交
            host.step_count += 1
            host.game_history.save_snapshot(game, move_info, None)
            cur = new_cur
            done = True
            break
        assert done, f'第 {i} 步引擎回放失败'

    assert tc.canonicalize(frozenset(cur)) == trap['state'], '终态与逃逸态不符'
    assert {tuple(b.location) for b in game.blocks} == set(cur), '引擎终态不符'
    return cur


def verify(path, expect_snaps, expect_state, expect_step):
    """headless 走游戏原代码 _load_save_data 打开存档并核对内容。"""
    stub = _LoadStub()
    data = json.loads(path.read_text(encoding='utf-8'))
    stub._load_save_data(data)
    hist = stub.game_history.history
    assert len(hist) == expect_snaps, \
        f'快照数 {len(hist)} != 期望 {expect_snaps}'
    assert stub.game_history.history_index == len(hist) - 1, 'history_index 不在末尾'
    assert stub.step_count == expect_step, f'step_count {stub.step_count} != {expect_step}'
    cells = snapshot_cells(hist[-1])
    assert tc.canonicalize(cells) == expect_state, '载入终态与逃逸态不符'
    assert {tuple(b.location) for b in stub.game.blocks} == set(cells), \
        '载入后引擎状态与快照不符'


def main(argv):
    src = Path(argv[0]) if argv else Path(__file__).resolve().parent / 'trap_paths_4_4_2.json'
    if not src.exists():
        print(f'找不到路径数据：{src}（先跑 shuffle_trap.py）')
        return 1
    data = json.loads(src.read_text(encoding='utf-8'))
    puzzle = data['puzzle']
    m, n, step = parse_puzzle(puzzle)
    K = m * n
    goal_cells = data['goal_cells']
    traps = data['traps']
    print(f'[{puzzle}] 逃逸态 {len(traps)} 个，路径数据 {src.name}')

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    made = []
    for idx, trap in enumerate(traps, 1):
        host = _SaveHost(m, n, step)
        replay(host, trap, goal_cells, m, n, step, K)
        out = host._build_save_data()             # 官方结构 + 官方 checksum
        path = OUT_DIR / f'死局-{puzzle}-{idx}.json'
        path.write_text(_compact_json_dumps(out), encoding='utf-8')
        made.append((path, trap))
        print(f'  已导出 {path.name}  步数={trap["dist"]}  '
              f'快照={len(host.game_history.history)}  入口边={trap["entry_edges"]}')

    print('\nheadless 载入验证：')
    ok = True
    for path, trap in made:
        try:
            verify(path, trap['dist'] + 1, trap['state'], trap['dist'])
            print(f'  ✓ {path.name}  打开成功，{trap["dist"]} 步可逐步撤销回复原态')
        except Exception as ex:
            ok = False
            print(f'  ✗ {path.name}  {type(ex).__name__}: {ex}')
    print(f'\n共导出 {len(made)} 个存档 → {OUT_DIR}')
    return 0 if ok and made else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
