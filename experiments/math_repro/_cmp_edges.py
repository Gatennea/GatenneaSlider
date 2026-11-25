# -*- coding: utf-8 -*-
"""对拍：moves.py 生成的邻接 vs repro_fast dump 的 edges.bin。

用法：python _cmp_edges.py <dump_dir>
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import moves


def read_dump(d):
    braw = open(os.path.join(d, "boards.bin"), "rb").read()
    eraw = open(os.path.join(d, "edges.bin"), "rb").read()
    N = len(braw) // 32
    states = []
    for i in range(N):
        rows = struct.unpack("<16H", braw[32 * i:32 * i + 32])
        cs = set()
        for y, mask in enumerate(rows):
            x = 0
            while mask:
                if mask & 1:
                    cs.add((y, x))
                mask >>= 1
                x += 1
        states.append(frozenset(cs))
    edges = set()
    for u, v in struct.iter_unpack("<II", eraw):
        edges.add((u, v))
        edges.add((v, u))
    return states, edges


def canon(S):
    best = None
    T = moves.normalize(S)
    for _ in range(4):
        for cand in (T, mirror(T)):
            k = tuple(sorted(moves.normalize(cand)))
            if best is None or k < best:
                best = k
        T = moves.normalize(rot90(T))
    return frozenset(best)


def rot90(S):
    R = max(r for r, _ in S) + 1
    return frozenset((c, R - 1 - r) for r, c in S)


def mirror(S):
    C = max(c for _, c in S) + 1
    return frozenset((r, C - 1 - c) for r, c in S)


def main():
    d = sys.argv[1]
    states, dump_edges = read_dump(d)
    print(f"states={len(states)}  dump undirected edges={len(dump_edges)}")

    idmap = {}
    for i, S in enumerate(states):
        idmap.setdefault(canon(S), i)

    my = set()
    unmatched = 0
    for i, S in enumerate(states):
        for seam, side, comp, unit in moves.legal_moves(S, s=1):
            nxt = moves.apply_move(S, comp, unit, s=1)
            if nxt is None:
                continue
            j = idmap.get(canon(nxt))
            if j is None:
                unmatched += 1
                continue
            my.add((i, j))

    print(f"mine undirected edges={len(my)}  (targets not in dump: {unmatched})")
    miss = dump_edges - my
    extra = my - dump_edges
    print(f"dump-only (I miss): {len(miss)}   mine-only (I add): {len(extra)}")

    def show(pairs, tag, limit=4):
        for (u, v) in list(pairs)[:limit]:
            print(f"\n[{tag}] {u} -> {v}")
            print("  from:")
            for r, c in sorted(states[u]):
                pass
            print(ascii_of(states[u]))
            print("  to:")
            print(ascii_of(states[v]))

    if miss:
        show(miss, "dump-only")
    if extra:
        show(extra, "mine-only")


def ascii_of(S):
    rmin = min(r for r, _ in S); rmax = max(r for r, _ in S)
    cmin = min(c for _, c in S); cmax = max(c for _, c in S)
    return "\n".join("".join("#" if (r, c) in S else "." for c in range(cmin, cmax + 1))
                     for r in range(rmin, rmax + 1))


if __name__ == "__main__":
    main()
