"""只检查不可解状态（A-B）的几何判据；纯只读。
用法: python check_unsolvable.py <dump> <m> <n> <s>
"""
import sys, os
import numpy as np

def boards(dump):
    n = os.path.getsize(os.path.join(dump, "membership.bin")) // 16
    b = np.fromfile(os.path.join(dump, "boards.bin"), dtype="<u2").reshape(n, 16)
    mem = np.fromfile(os.path.join(dump, "membership.bin"), dtype=np.uint8).reshape(n, 16)
    flags = mem[:, 4]
    outdeg = mem[:, 6:8].copy().view("<u2").ravel()
    dist = mem[:, 10:14].copy().view("<i4").ravel()
    return b, flags, outdeg, dist

def has_run(mask, s):
    run = 0
    while mask:
        if mask & 1:
            run += 1
            if run >= s:
                return True
        else:
            run = 0
        mask >>= 1
    return False

def weak_or(rows, s):
    cols = [0] * 16
    for r in range(16):
        m = int(rows[r])
        if m and not has_run(m, s):
            return True
        for c in range(16):
            if m >> c & 1:
                cols[c] |= 1 << r
    for c in range(16):
        if cols[c] and not has_run(cols[c], s):
            return True
    return False

def has_hole(rows):
    g = [[0] * 18 for _ in range(18)]
    for r in range(16):
        m = int(rows[r])
        for c in range(16):
            if m >> c & 1:
                g[r + 1][c + 1] = 1
    seen = [[False] * 18 for _ in range(18)]
    stack = [(0, 0)]; seen[0][0] = True
    while stack:
        r, c = stack.pop()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < 18 and 0 <= nc < 18 and not seen[nr][nc] and g[nr][nc] == 0:
                seen[nr][nc] = True; stack.append((nr, nc))
    for r in range(1, 17):
        for c in range(1, 17):
            if g[r][c] == 0 and not seen[r][c]:
                return True
    return False

def main():
    dump, m, n, s = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    b, flags, outdeg, dist = boards(dump)
    N = len(flags)
    inB = (flags & 2).astype(bool)
    unsolv = ~inB
    print(f"N={N}  不可解={int(unsolv.sum())}")
    cats = {"困局": (flags & 16).astype(bool), "两不沾": (flags & 64).astype(bool),
            "sink": (flags & 4).astype(bool)}
    for name, sel in cats.items():
        print(f"  {name}: {int((sel & unsolv).sum())}")
    stats = {}
    for i in np.nonzero(unsolv)[0]:
        rows = b[i]
        w = weak_or(rows, s); h = has_hole(rows)
        key = ("困局" if flags[i] & 16 else "两不沾")
        d = stats.setdefault(key, {"n": 0, "w": 0, "h": 0, "wh": 0, "holed": 0})
        d["n"] += 1; d["w"] += int(w); d["h"] += int(h); d["wh"] += int(w and h)
        if h:
            d["holed"] += 1
            if d["holed"] <= 3:
                print(f"  [有洞样例] {key} outdeg={int(outdeg[i])}")
                for r in range(16):
                    mm = int(rows[r])
                    if mm:
                        print("    " + "".join("#" if mm >> c & 1 else "." for c in range(mm.bit_length())))
        if not w:
            print(f"  [弱或反例] {key} outdeg={int(outdeg[i])}")
            for r in range(16):
                mm = int(rows[r])
                if mm:
                    print("    " + "".join("#" if mm >> c & 1 else "." for c in range(mm.bit_length())))
    for k, d in stats.items():
        print(f"{k}: n={d['n']}  弱或={d['w']}  无洞={d['h']}  两者兼具={d['wh']}")

main()
