# -*- coding: utf-8 -*-
"""把 _s2_abs_d9.log 里那 9 步的「box + 逻辑方向」还原成游戏口径的 (缝, 侧)。

tag_bfs.cpp 只打印了被搬分量的包围盒和方向，没打印是哪条缝、哪一侧。
这里用 Python 复刻 moves_from_board 的枚举顺序（同一条缝、同一切法、同一
顺序），对每一步找一个 (vert, L, side) 使「该侧的连通分量」正好等于 box，
且方向一致；然后把每步逐步应用到带标签的块上，最后校验真的是 4x4 满盘、
只有两块互换。
"""

from collections import deque

S = 2                      # 二级：每次平移 2 格
M = N = 4

# (rmin, cmin, rmax, cmax) 与记录的逻辑方向，逐字来自 _s2_abs_d9.log
STEPS = [
    ((0, 0, 0, 3),   (0, -1)),
    ((0, -2, 3, 0),  (-1, 0)),
    ((-2, -2, -2, 0), (0, 1)),
    ((1, 2, 3, 3),   (-1, 0)),
    ((-2, 2, 1, 3),  (1, 0)),
    ((-2, 0, -1, 1), (0, 1)),
    ((-2, 3, -2, 3), (1, 0)),
    ((-2, 2, -1, 2), (0, -1)),
    ((-2, 0, 1, 0),  (1, 0)),
]


def bbox(cells):
    rs = [c[0] for c in cells]
    cs = [c[1] for c in cells]
    return (min(rs), min(cs), max(rs), max(cs))


def components(cells):
    """4-邻接连通分量，返回 list[set]。"""
    seen = set()
    out = []
    for start in cells:
        if start in seen:
            continue
        comp = set()
        dq = deque([start])
        seen.add(start)
        while dq:
            r, c = dq.popleft()
            comp.add((r, c))
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (r + dr, c + dc)
                if nb in cells and nb not in seen:
                    seen.add(nb)
                    dq.append(nb)
        out.append(comp)
    return out


def is_connected(cells):
    if not cells:
        return True
    return len(components(cells)) == 1


def can_move(cells, comp, addr, addc):
    """复刻 tag_bfs 的逐格校验：S 次位移，每次查重叠 + 全盘连通。"""
    rest = cells - comp
    cur = set(comp)
    for _ in range(S):
        cur = {(r + addr, c + addc) for r, c in cur}
        if cur & rest:
            return None
        if not is_connected(cur | rest):
            return None
    return cur


def enumerate_moves(cells):
    """按 cpp 的顺序枚举：缝由近到远，侧 0 再侧 1，方向先 -1 再 +1。"""
    rmin = min(r for r, _ in cells)
    rmax = max(r for r, _ in cells)
    cmin = min(c for _, c in cells)
    cmax = max(c for _, c in cells)
    nsh = rmax - rmin
    nsv = cmax - cmin
    for t in range(nsh + nsv):
        vert = t >= nsh
        idx = (t - nsh) if vert else t
        L = (cmin + idx) if vert else (rmin + idx)
        for sd in (0, 1):
            if vert:
                side = {x for x in cells if (x[1] <= L if sd == 0 else x[1] > L)}
            else:
                side = {x for x in cells if (x[0] <= L if sd == 0 else x[0] > L)}
            for comp in components(side):
                # 缝只负责选片；移动方向可以任意 —— 四个方向全试。
                for addr, addc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    after = can_move(cells, comp, addr, addc)
                    if after is None:
                        continue
                    yield {
                        'vert': vert, 'L': L, 'sd': sd, 'comp': comp,
                        'addr': addr, 'addc': addc, 'after': after,
                        'box': bbox(comp),
                    }


def main():
    # 初始：16 个标签各自占一格，标签值 = r*N+c+1（与数字谜题口径一致）
    where = {t: (t // N, t % N) for t in range(16)}      # label -> (r,c)
    cells = set(where.values())

    picked = []
    for i, (box, delta) in enumerate(STEPS, 1):
        hit = None
        for m in enumerate_moves(cells):
            if m['box'] != box:
                continue
            if (m['addr'], m['addc']) != delta:
                continue
            hit = m
            break
        if hit is None:
            print(f'step {i}: NO MATCH for box={box} delta={delta}')
            for m in enumerate_moves(cells):
                print('   cand', m['box'], (m['addr'], m['addc']), 'L=', hit['L'] if hit else None)
            return 1

        # 应用：把 comp 里每个标签按 delta*S 搬走
        comp = hit['comp']
        labels = [t for t, p in where.items() if p in comp]
        for t in labels:
            r, c = where[t]
            where[t] = (r + hit['addr'] * S, c + hit['addc'] * S)
        cells = set(where.values())
        picked.append((i, hit, labels))
        gt = 'v' if hit['vert'] else 'h'
        letter = {(-1, 0): 'w', (1, 0): 's', (0, -1): 'a', (0, 1): 'd'}[(hit['addr'], hit['addc'])]
        print(f"step {i}: seam={'V' if hit['vert'] else 'H'}_{hit['L']} "
              f"side={'left/top' if hit['sd'] == 0 else 'right/bottom'} "
              f"letter={letter} n={len(comp)} "
              f"comp={sorted(comp)} labels={sorted(t + 1 for t in labels)}")

    print()
    print('final cells:', sorted(cells))
    full = {(r, c) for r in range(M) for c in range(N)}
    print('is 4x4 full rectangle:', cells == full)
    perm = [where[t] for t in range(16)]
    ident = [(t // N, t % N) for t in range(16)]
    diff = [t + 1 for t in range(16) if perm[t] != ident[t]]
    print('labels off their home cell:', diff)
    print('mapping:', {t + 1: perm[t] for t in range(16) if perm[t] != ident[t]})

    print()
    print('--- 游戏口径参数表（可直接喂 engine）---')
    for i, hit, labels in picked:
        gt = 'v' if hit['vert'] else 'h'
        letter = {(-1, 0): 'w', (1, 0): 's', (0, -1): 'a', (0, 1): 'd'}[(hit['addr'], hit['addc'])]
        rep = min(hit['comp'])
        print(f'{i}. gap_type={gt} line={hit["L"]} letter={letter} '
              f'rep=({rep[0]},{rep[1]}) n={len(hit["comp"])} '
              f'labels={sorted(t + 1 for t in labels)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
