# -*- coding: utf-8 -*-
"""S2b is_live_gap 驗證：與 legal_moves 活縫集合逐項對齊 + 死縫開銷。

對每種板型：legal_moves 的 (族, t) 活縫集 vs is_live_gap 逐候選掃描
的活縫集，必須完全相等（多一個少一個都算回歸——GUI 的「選不動」提示
與拖拽探測全靠這個判據）。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import make_board  # noqa: E402
from engine.adapter import create_adapter_puzzle  # noqa: E402
from gui.board_view import SpecPolygonView  # noqa: E402

fails = []


def check(cond, msg):
    print(f"  {'ok' if cond else 'FAIL'}: {msg}")
    if not cond:
        fails.append(msg)


CASES = [
    ('square', 'square', 4, 4, 1),
    ('tri', 'triangle', 4, None, 1),
    ('mi', 'mi', 3, 3, 1),
    ('shatter', 'shatter', 4, 4, 1),
    ('shatter_lattice', 'shatter', 4, 4, 1),
]

for tag, kind, m, n, step in CASES:
    print(f"== {tag} ==")
    if kind == 'triangle':
        board = make_board('tri', k=m)
        game = create_adapter_puzzle('triangle', m, None, step)
    else:
        board = make_board(kind, m=m, n=n) if kind != 'shatter' \
            else make_board('shatter' if tag == 'shatter' else 'shatter_lattice')
        game = create_adapter_puzzle(
            'shatter' if tag.startswith('shatter') else kind, m, n, step)
    view = SpecPolygonView(board.spec, cell_size=60.0)
    cands = view.seam_candidates(board)
    # legal_moves 活縫（引擎真值）
    live_true = {(mv.family, mv.t) for mv in board.legal_moves(step)}
    # is_live_gap 逐候選掃描
    live_gui = set()
    dead_cost = 0.0
    dead_n = 0
    live_cost = 0.0
    live_n = 0
    for (fname, line) in cands:
        t0 = time.perf_counter()
        ok = game.is_live_gap(fname, line, step)
        dt = (time.perf_counter() - t0) * 1000
        if ok:
            live_gui.add((fname, game._line_to_t(fname, line)))
            live_cost += dt
            live_n += 1
        else:
            dead_cost += dt
            dead_n += 1
    print(f"  候選 {len(cands)}：legal_moves 活縫 {len(live_true)}，"
          f"is_live_gap 活縫 {len(live_gui)}")
    check(live_true == live_gui,
          f"{tag} 活縫集合相等（差 {sorted(live_true ^ live_gui)[:4]}）")
    if dead_n:
        print(f"  死縫均耗 {dead_cost / dead_n:.1f}ms（{dead_n} 條），"
              f"活縫均耗 {live_cost / max(live_n, 1):.1f}ms（{live_n} 條）")
    # 非法族名 / 空線號健壯性
    check(game.is_live_gap('nope', 0) is False, f"{tag} 未知族名 → False")

print()
if fails:
    print(f"共 {len(fails)} 項失敗")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("全部通過")
