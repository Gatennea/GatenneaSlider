# -*- coding: utf-8 -*-
"""O-12：有洞能不能是可解態？—— 對所有態逐個 flood fill（不用歐拉公式）。
用法: python holed_all.py <dump> ...
輸出：holed 在 A / 可解 / F / R / 困局 / 兩不沾 的分佈，並印樣本。
"""
import os, sys, time
import numpy as np


def holes_of(rows, rmin, rmax, cmin, cmax):
    """rows: 16 個 uint16；在 bbox 外扩一圈的框內 flood fill，回傳洞格數（4 連通）。"""
    H = rmax - rmin + 3
    W = cmax - cmin + 3
    g = [[0] * W for _ in range(H)]
    for r in range(rmin, rmax + 1):
        mm = int(rows[r]) >> cmin
        for c in range(cmax - cmin + 1):
            if mm >> c & 1:
                g[r - rmin + 1][c + 1] = 1
    seen = [[False] * W for _ in range(H)]
    st = [(0, 0)]; seen[0][0] = True
    while st:
        r, c = st.pop()
        if r > 0 and not seen[r - 1][c] and g[r - 1][c] == 0:
            seen[r - 1][c] = True; st.append((r - 1, c))
        if r + 1 < H and not seen[r + 1][c] and g[r + 1][c] == 0:
            seen[r + 1][c] = True; st.append((r + 1, c))
        if c > 0 and not seen[r][c - 1] and g[r][c - 1] == 0:
            seen[r][c - 1] = True; st.append((r, c - 1))
        if c + 1 < W and not seen[r][c + 1] and g[r][c + 1] == 0:
            seen[r][c + 1] = True; st.append((r, c + 1))
    cnt = 0
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            if g[r][c] == 0 and not seen[r][c]:
                cnt += 1
    return cnt


def draw(rows, tag):
    print("  " + tag)
    for r in range(16):
        mm = int(rows[r])
        if mm:
            print("    " + "".join("#" if mm >> c & 1 else "." for c in range(16)).rstrip("."))


for d in sys.argv[1:]:
    t0 = time.time()
    mem = np.fromfile(os.path.join(d, "membership.bin"), dtype=np.uint8).reshape(-1, 16)
    N = mem.shape[0]
    flags = mem[:, 4]
    outdeg = mem[:, 6:8].copy().view(np.uint16).ravel().astype(np.int64)
    b = np.fromfile(os.path.join(d, "boards.bin"), dtype=np.uint16).reshape(N, 16)
    rowhas = b != 0
    rmin = np.argmax(rowhas, axis=1); rmax = 15 - np.argmax(rowhas[:, ::-1], axis=1)
    colmask = np.zeros_like(b)
    for c in range(16):
        colmask[:, c] = ((b >> c) & 1).sum(axis=1)
    cmask = colmask > 0
    cmin = np.argmax(cmask, axis=1); cmax = 15 - np.argmax(cmask[:, ::-1], axis=1)

    cone = (flags & 1).astype(bool); B = (flags & 2).astype(bool)
    T = (flags & 16).astype(bool); neither = (flags & 64).astype(bool)
    solv = (flags & 128).astype(bool)

    holed = np.zeros(N, dtype=bool)
    hsizes = {}
    for i in range(N):
        h = holes_of(b[i], int(rmin[i]), int(rmax[i]), int(cmin[i]), int(cmax[i]))
        if h:
            holed[i] = True
            hsizes[h] = hsizes.get(h, 0) + 1
    print(f"\n=== {os.path.basename(d)} N={N}  有洞的態={int(holed.sum())}  洞面積分布={hsizes}  "
          f"({time.time()-t0:.1f}s)")
    print(f"  有洞 ∩ 可解 = {int((holed & solv).sum())}  ← 這格不是 0 就說明「有洞」不蘊含不可解")
    print(f"  有洞 ∩ F = {int((holed & cone).sum())}  ∩ R = {int((holed & B).sum())}  "
          f"∩ 困局 = {int((holed & T).sum())}  ∩ 兩不沾 = {int((holed & neither).sum())}")
    for i in np.nonzero(holed & solv)[0][:2]:
        draw(b[i], f"[可解且有洞] state {i} flags={flags[i]} outdeg={outdeg[i]}")
    for i in np.nonzero(holed & ~B)[0][:1]:
        draw(b[i], f"[不可解且有洞] state {i} flags={flags[i]} outdeg={outdeg[i]}")
