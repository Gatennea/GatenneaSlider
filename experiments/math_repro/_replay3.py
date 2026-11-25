# -*- coding: utf-8 -*-
"""把 _s2_3cyc.log 那 4 步的「box + 逻辑方向」还原成游戏口径的 (缝, 侧, 方向, 代表格)。

逻辑与 _replay9.py 完全相同，只换了 STEPS 和最后的校验文案。
序列来自 `tag_bfs 4 4 2 6 <cap> gens 3` 的 TARGET[3] 输出。

注意：本步的口径是 (4,4,2) 的 s=2，每次平移 2 格（S=2）。
"""

from collections import deque

S = 2
M = N = 4

# (rmin, cmin, rmax, cmax) 与逻辑方向，逐字来自 _s2_3cyc.log
STEPS = [
    ((0, 0, 0, 3),    (0, -1)),
    ((0, -2, 0, -1),  (1, 0)),
    ((0, -2, 3, 0),   (-1, 0)),
    ((-2, 0, -1, 0),  (0, -1)),
    ((-2, -2, 0, 1),  (0, 1)),
    ((-2, 0, 1, 0),   (1, 0)),
]


def bbox(cells):
    rs = [c[0] for c in cells]
    cs = [c[1] for c in cells]
    return (min(rs), min(cs), max(rs), max(cs))


def components(cells):
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
    where = {t: (t // N, t % N) for t in range(16)}
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
                print('   cand', m['box'], (m['addr'], m['addc']),
                      'n=', len(m['comp']))
            return 1

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
              f"labels={sorted(t + 1 for t in labels)}")

    print()
    print('final cells:', sorted(cells))
    full = {(r, c) for r in range(M) for c in range(N)}
    print('is 4x4 full rectangle:', cells == full)
    perm = [where[t] for t in range(16)]
    ident = [(t // N, t % N) for t in range(16)]
    diff = [t + 1 for t in range(16) if perm[t] != ident[t]]
    print('labels off their home cell:', diff)
    print('mapping:', {t + 1: perm[t] for t in range(16) if perm[t] != ident[t]})

    # 四类循环：每类的 4 个位置编号
    for L in range(4):
        pts = [r * N + c for r in range(M) for c in range(N) if (r % 2) * 2 + (c % 2) == L]
        cyc = []
        for p in pts:
            r, c = divmod(p, N)
            t = [t for t in range(16) if where[t] == (r, c)]
            if not t:
                continue
            t0 = t[0]
            cyc.append((p + 1, t0 + 1))
        print(f'  类{L}: ' + ' / '.join(f'格{p}有标签{t}' for p, t in cyc))

    print()
    print('--- 游戏口径参数表（可直接喂 engine）---')
    for i, hit, labels in picked:
        gt = 'v' if hit['vert'] else 'h'
        letter = {(-1, 0): 'w', (1, 0): 's', (0, -1): 'a', (0, 1): 'd'}[(hit['addr'], hit['addc'])]
        rep = min(hit['comp'])
        print(f"{i}. gap_type={gt} line={hit['L']} letter={letter} "
              f"rep=({rep[0]},{rep[1]}) n={len(hit['comp'])} "
              f"labels={sorted(t + 1 for t in labels)}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
