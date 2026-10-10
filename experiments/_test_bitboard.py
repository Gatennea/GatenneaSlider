# -*- coding: utf-8 -*-
"""阶段3 正确性回归：bitboard 版 opt / is_single_connected 必须与原 set-DFS
语义【逐格一致】。参考实现独立重推（不复制旧代码），避免「改完发现换了个错法」。

用法：D:/python/python.exe -u -X utf8 experiments/_test_bitboard.py
"""
import sys, random

sys.path.insert(0, '.')
from game import SliderMatrix, Block
from solver.actions import enumerate_valid_actions, apply_action


# ---------------------------------------------------------------------------
# 独立参考实现（重推语义）
# ---------------------------------------------------------------------------
def ref_is_single_connected(positions):
    if not positions:
        return True
    start = next(iter(positions))
    visited = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in visited:
            continue
        visited.add(cur)
        r, c = cur
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nb = (r + dr, c + dc)
            if nb in positions and nb not in visited:
                stack.append(nb)
    return len(visited) == len(positions)


def ref_opt(game, direction, line, selected_block):
    block_set = set((b.location[0], b.location[1]) for b in game.blocks)

    def is_conn(b1, b2):
        if direction == 'h':
            if (b1[0] <= line and b2[0] > line) or (b1[0] > line and b2[0] <= line):
                return False
        else:
            if (b1[1] <= line and b2[1] > line) or (b1[1] > line and b2[1] <= line):
                return False
        return True

    def neighbors(pos):
        r, c = pos
        res = []
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nb = (r + dr, c + dc)
            if nb in block_set:
                res.append(nb)
        return res

    start = (selected_block.location[0], selected_block.location[1])
    visited = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in visited:
            continue
        visited.add(cur)
        for nb in neighbors(cur):
            if nb not in visited and is_conn(cur, nb):
                stack.append(nb)
    return visited


def opted_set(game):
    return frozenset((b.location[0], b.location[1]) for b in game.blocks if b.be_opted)


# ---------------------------------------------------------------------------
# 测试 1：is_single_connected
# ---------------------------------------------------------------------------
def test_is_single_connected(rng):
    fail = 0
    trials = 0
    for _ in range(4000):
        # 随机生成一个占用点集（可能不连通）
        n = rng.randint(1, 30)
        cells = set()
        for _ in range(n):
            cells.add((rng.randint(-3, 6), rng.randint(-3, 6)))
        ref = ref_is_single_connected(cells)
        got = SliderMatrix.is_single_connected(cells)
        trials += 1
        if ref != got:
            fail += 1
            if fail <= 5:
                print(f"  [is_sc FAIL] cells={sorted(cells)} ref={ref} got={got}")
    print(f"[is_single_connected] {trials} 局，不符 {fail}")
    return fail


# ---------------------------------------------------------------------------
# 测试 2：opt（每个侧块都当 representative 比一遍）
# ---------------------------------------------------------------------------
def test_opt(rng):
    fail = 0
    trials = 0
    sizes = [(4, 4), (6, 6), (8, 8)]
    for m, n in sizes:
        for _ in range(300):
            g = SliderMatrix(m, n)
            g.shuffle(attempts=80, step=2)
            # 随机走若干合法动作制造散乱但合法的局面
            for _ in range(rng.randint(0, 40)):
                acts = enumerate_valid_actions(g, 2)
                if not acts:
                    break
                a = rng.choice(acts)
                # 直接用动作系统的 apply 制造真实局面
                apply_action(g, a, 2)
            # 遍历所有缝隙/侧，每个侧块当代表逐一比对
            bounds = g.get_boundaries()
            for direction in ('h', 'v'):
                if direction == 'h':
                    lines = range(bounds['min_row'], bounds['max_row'])
                else:
                    lines = range(bounds['min_col'], bounds['max_col'])
                for line in lines:
                    # 覆盖两侧（above/below 或 left/right）
                    for side in (('above', 'below') if direction == 'h'
                                 else ('left', 'right')):
                        reps = []
                        for b in g.blocks:
                            if direction == 'h':
                                on = (b.location[0] <= line) if side == 'above' else (b.location[0] > line)
                            else:
                                on = (b.location[1] <= line) if side == 'left' else (b.location[1] > line)
                            if on:
                                reps.append(b)
                        for rep in reps:
                            # 参考（独立 set-DFS）
                            ref = ref_opt(g, direction, line, rep)
                            # 被测（bitboard）
                            for b in g.blocks:
                                b.be_opted = False
                            g.opt(direction, line, rep)
                            got = opted_set(g)
                            trials += 1
                            if ref != got:
                                fail += 1
                                if fail <= 8:
                                    print(f"  [opt FAIL] {m}x{n} dir={direction} "
                                          f"line={line} side={side} rep={tuple(rep.location)} "
                                          f"ref={sorted(ref)} got={sorted(got)}")
    print(f"[opt] {trials} 局(representative×缝隙×侧)，不符 {fail}")
    return fail


def main():
    rng = random.Random(20261010)
    print("=== 阶段3 bitboard 正确性回归 ===\n")
    f1 = test_is_single_connected(rng)
    f2 = test_opt(rng)
    print()
    if f1 == 0 and f2 == 0:
        print("ALL PASS —— bitboard 与原 set-DFS 语义逐格一致")
        sys.exit(0)
    else:
        print("FAIL —— 见上方明细")
        sys.exit(1)


if __name__ == '__main__':
    main()
