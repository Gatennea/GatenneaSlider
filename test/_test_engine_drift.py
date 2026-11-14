# -*- coding: utf-8 -*-
"""engine/drift.py 的独立验证（方形 / 三角 / 米字 三形态同一条代码）。

跑法：D:\\python\\python.exe -u test\\_test_engine_drift.py
"""
import random
import sys
import time

sys.path.insert(0, __import__('os').path.dirname(
    __import__('os').path.dirname(__import__('os').path.abspath(__file__))))

from engine.registry import make_board, tri_spec  # noqa: E402
from engine.board import Board  # noqa: E402
from engine.drift import (_centroid, rewrite_moves,  # noqa: E402
                          shift_move)

FAIL = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok   {name}')
    else:
        print(f'  FAIL {name}  {detail}')
        FAIL.append(name)


def dist_to(board, anchor):
    c = _centroid(board)
    return sum((x - y) ** 2 for x, y in zip(c, anchor)) ** 0.5


def walk(board, step, n, rng):
    """从当前局面随机走 n 步，返回 (初始局面, 步序列, 终局面)。"""
    moves = []
    for _ in range(n):
        legal = list(board.legal_moves(step))
        if not legal:
            break
        # 有意识偏「推大片」：一半概率从「动块数 > 全盘一半」的合法移动里选
        big = [m for m in legal if len(m.moved) * 2 > board.block_count]
        chosen = rng.choice(big or legal)
        moves.append(chosen)
        board = board.apply(chosen)
    return board, moves


def case(tag, board0, step, n, rng):
    print(f'--- {tag} ---')
    b0 = board0
    end0, moves = walk(copy_board(b0), step, n, rng)
    if not moves:
        print('  (没有合法移动，跳过)')
        return
    n0 = len(moves)
    anchor = _centroid(b0)
    d_raw = dist_to(end0, anchor)

    t0 = time.time()
    new_moves, end1, flips = rewrite_moves(b0, moves)
    el = time.time() - t0
    d_new = dist_to(end1, anchor)

    print(f'  步数 {n0}，换侧 {flips} 次，{el*1000:.0f}ms')
    print(f'  质心漂移：原 {d_raw:.2f} 格 → 改写后 {d_new:.2f} 格')
    check(f'{tag}: 步数不变', len(new_moves) == n0, f'{len(new_moves)} vs {n0}')
    check(f'{tag}: 终态形状不变',
          end1.canonical_key() == end0.canonical_key())
    check(f'{tag}: 漂移不升', d_new <= d_raw + 1e-9,
          f'{d_raw:.2f} → {d_new:.2f}')
    check(f'{tag}: 漂移被钉住', d_new <= 1.6,
          f'{d_new:.2f}')

    # 独立回放：用刚产出的新序列在 b0 上重放，终态形状必须与原终态一致
    rb = b0
    for mv in new_moves:
        if not rb.move_ok(mv):
            check(f'{tag}: 改写序列可回放', False, f'非法步 {mv}')
            break
        rb = rb.apply(mv)
    else:
        check(f'{tag}: 改写序列可回放',
              rb.canonical_key() == end0.canonical_key())
    return end1


def copy_board(b):
    return Board(b.spec, b.blocks)


def main():
    rng = random.Random(20261114)

    sq = make_board('square', m=4, n=4)
    case('方形 4x4 s2', sq, 2, 30, rng)

    tri = make_board('tri', k=4)
    case('三角 k=4 s2', tri, 2, 24, rng)

    mi = make_board('mi', m=2, n=2)
    case('米字 2x2 s1', mi, 1, 16, rng)

    print('--- shift_move 往返 ---')
    spec = tri_spec(4)
    b = make_board('tri', k=4)
    mv = b.legal_moves(2)[0]
    back = shift_move(spec, shift_move(spec, mv, (2, 1)), (-2, -1))
    check('往返恒等', back == mv)

    print()
    if FAIL:
        print(f'{len(FAIL)} 项失败: {FAIL}')
        return 1
    print('全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
