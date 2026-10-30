# -*- coding: utf-8 -*-
"""legal_moves(1) 在碎三角上的耗时测量（决定 S2 活缝过滤策略）。

若可接受（<100ms 量级），通用通道可按「每局面缓存一次 legal_moves(1)」
生成活缝候选集；若不可接受，改用点击时惰性校验。
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.registry import make_board  # noqa: E402


def timed(board, n=5):
    t0 = time.perf_counter()
    for _ in range(n):
        mv = board.legal_moves(1)
    return (time.perf_counter() - t0) / n * 1000.0, len(mv)


def main():
    board = make_board('shatter')
    ms, n = timed(board)
    print(f"还原态：legal_moves(1) {ms:.1f}ms/次，{n} 个移动")

    # 随机走 10 步后的局面
    rng = random.Random(7)
    for i in range(10):
        mv = board.legal_moves(1)
        if not mv:
            break
        board = board.apply(rng.choice(mv))
    ms, n = timed(board)
    print(f"随机 10 步后：legal_moves(1) {ms:.1f}ms/次，{n} 个移动")

    # 再走 20 步
    for i in range(20):
        mv = board.legal_moves(1)
        if not mv:
            break
        board = board.apply(rng.choice(mv))
    ms, n = timed(board)
    print(f"随机 30 步后：legal_moves(1) {ms:.1f}ms/次，{n} 个移动")


if __name__ == '__main__':
    main()
