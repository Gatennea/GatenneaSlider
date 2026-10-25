# -*- coding: utf-8 -*-
"""回归：通用引擎板型（shield）撤销/重做不能丢块（丢同格多朝向块）。

shield 模型同一 2D 格叠两块（不同朝向），旧 history 矩阵编码把它们压成一格，
撤销后盘面碎成多连通分量、所有选中被拒、动画与打乱全废。修复后 EngineGame
带无损键表快照（snapshot_state/restore_state），restore 还原零丢失。

纯逻辑回归（不需要 pygame）：create_adapter_puzzle / GameHistory 都不依赖运行时。
"""
import json
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from engine.adapter import create_adapter_puzzle
from engine.board import _connected_components
from history import GameHistory

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg} {extra}')
    return cond


def state(g):
    keys = g.board.keys
    return (len(g.blocks), len(keys),
            len(_connected_components(keys, g.spec)))


def _do_one_move(g):
    """走一步合法移动（opt -> try_move -> commit_move），与 GUI 同契约。"""
    for gap_type, line in g.all_gaps():
        for d in g._gap_directions(gap_type):
            g.opt(gap_type, line, g.blocks[0])
            if not any(b.be_opted for b in g.blocks):
                continue
            final = g.try_move(d, 1)
            if final:
                g.commit_move(final)
                return True
    return False


def main():
    # 1) 还原态回放快照不丢块
    g = create_adapter_puzzle('shield', 4, 4, 1)
    check(state(g) == (28, 28, 1), 'shield 初始 28 块 / 1 连通分量', state(g))
    h = GameHistory()
    h.reset()
    h.save_snapshot(g)
    h.restore_snapshot(g, 0)
    check(state(g) == (28, 28, 1), 'restore 后依然 28 块 / 1 连通分量', state(g))

    # 2) 走一步 + 撤销 + 重做，全程满盘
    g = create_adapter_puzzle('shield', 4, 4, 1)
    h = GameHistory()
    h.reset()
    h.save_snapshot(g)                  # index 0
    moved = _do_one_move(g)
    check(moved, 'shield 能走出一步合法移动')
    check(state(g) == (28, 28, 1), '移动后满盘', state(g))
    h.save_snapshot(g)                  # index 1
    ok, _ = h.undo(g)
    check(ok and state(g) == (28, 28, 1), '撤销后满盘（不丢块）', state(g))
    ok, _ = h.redo(g)
    check(ok and state(g) == (28, 28, 1), '重做后满盘（不丢块）', state(g))

    # 3) snapshot_state 经 JSON 往返无损（存档落盘等价）
    g = create_adapter_puzzle('shield', 4, 4, 1)
    st = json.loads(json.dumps(g.snapshot_state()))
    g2 = create_adapter_puzzle('shield', 4, 4, 1)
    g2.restore_state(st)
    check(state(g2) == (28, 28, 1), 'JSON 往返 + restore 无损', state(g2))
    check(set(g.board.keys) == set(g2.board.keys), '键集完全一致')

    print(f'\n通过 {_ok[0]} 项，失败 {len(_fail)} 项')
    if _fail:
        for m in _fail:
            print('  x', m)
        print('FAILED')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
