# -*- coding: utf-8 -*-
"""跨尺寸掃描：對每個 (m,n,s) 跑引擎、算集合量、算幾何判據、算兩個半徑。
用法: python sweep_geom.py [--keep]  （輸出 markdown 表格到 stdout，同時寫 sweep_geom_matrix.md）
純只讀 + 在自己目錄建 dump。
"""
import os, sys, subprocess, shutil
import numpy as np
from collections import deque

EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "branch", "experiments", "math_repro", "repro_fast.exe")
if not os.path.exists(EXE):
    EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "branch", "experiments", "math_repro", "repro_fast.exe")
ROOT = os.path.dirname(os.path.abspath(__file__))
DUMPROOT = os.path.join(ROOT, "sweep_dumps")

CNT = np.array([bin(i).count("1") for i in range(65536)], dtype=np.int16)


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
    """整張 16×16 檢查（骨牌會伸出窗口，不能只看 m×n）"""
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
        mm = int(rows[r])
        for c in range(16):
            if mm >> c & 1:
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


def solid_rects(boards):
    """回傳 (是否實心矩形 的布林陣列, 高, 寬)"""
    counts = CNT[boards].sum(axis=1).astype(np.int32)
    rowhas = boards != 0
    rmin = np.argmax(rowhas, axis=1)
    rmax = 15 - np.argmax(rowhas[:, ::-1], axis=1)
    colmask = np.zeros_like(boards)
    for c in range(16):
        colmask[:, c] = ((boards >> c) & 1).sum(axis=1)
    cmask = colmask > 0
    cmin = np.argmax(cmask, axis=1)
    cmax = 15 - np.argmax(cmask[:, ::-1], axis=1)
    area = (rmax - rmin + 1) * (cmax - cmin + 1)
    return counts == area, (rmax - rmin + 1), (cmax - cmin + 1)


def analyse(d, m, n, s, want_edges):
    mem = np.fromfile(os.path.join(d, "membership.bin"), dtype=np.uint8).reshape(-1, 16)
    N = mem.shape[0]
    flags = mem[:, 4]
    outdeg = mem[:, 6:8].copy().view(np.uint16).ravel().astype(np.int64)
    dist = mem[:, 10:14].copy().view(np.int32).ravel().astype(np.int64)
    b = np.fromfile(os.path.join(d, "boards.bin"), dtype=np.uint16).reshape(N, 16)

    cone = (flags & 1).astype(bool); B = (flags & 2).astype(bool)
    sink = (flags & 4).astype(bool); T = (flags & 16).astype(bool)
    neither = (flags & 64).astype(bool); solv = (flags & 128).astype(bool)
    unsolv = ~B

    rect, rh, rw = solid_rects(b)
    nl = int((rect & cone).sum())
    sizes = sorted({(int(a), int(bb)) for a, bb in zip(rh[rect & cone], rw[rect & cone])})

    n_w = n_h = 0
    for i in np.nonzero(unsolv)[0]:
        if weak_or(b[i], s):
            n_w += 1
        if has_hole(b[i]):
            n_h += 1

    god_fwd = -1
    if want_edges and os.path.exists(os.path.join(d, "edges.bin")):
        ed = np.fromfile(os.path.join(d, "edges.bin"), dtype=np.uint32).reshape(-1, 2)
        src, dst = ed[:, 0].astype(np.int64), ed[:, 1].astype(np.int64)
        order = np.argsort(src, kind="stable")
        ptr = np.zeros(N + 1, dtype=np.int64)
        ptr[1:] = np.cumsum(np.bincount(src, minlength=N))
        adj = dst[order]
        fwd = np.full(N, -1, dtype=np.int32)
        q = deque()
        for g0 in np.nonzero(dist == 0)[0]:
            fwd[g0] = 0; q.append(int(g0))
        while q:
            u = q.popleft()
            nf = fwd[u] + 1
            for v in adj[ptr[u]:ptr[u + 1]]:
                v = int(v)
                if fwd[v] < 0:
                    fwd[v] = nf; q.append(v)
        r = fwd >= 0
        god_fwd = int(fwd[r].max()) if r.any() else -1

    return dict(N=N, F=int(cone.sum()), R=int(B.sum()), S=int(solv.sum()),
                T=int(T.sum()), neither=int((neither & unsolv).sum()),
                sink=int(sink.sum()), unsolv=int(unsolv.sum()),
                edges=int(outdeg.sum()), god_ret=int(dist.max()), god_fwd=god_fwd,
                rect=int(rect.sum()), rect_in_C=nl, rect_sizes=sizes,
                w=n_w, h=n_h, s=s)


SIZES = [(2, 2, 1), (3, 2, 1), (3, 2, 2), (3, 3, 1), (3, 3, 2), (3, 3, 3),
         (4, 3, 2), (4, 3, 3), (5, 3, 2), (4, 4, 2), (4, 4, 3)]
# 不含 (4,4,1)：s=1 於 4×4 跑 5 分鐘未收斂（記憶體 2.1GB 仍在長），不划算

def row_md(x):
    return (f"| {x['tag']} | {x['N']} | {x['F']} | {x['R']} | {x['S']} | {x['T']} | "
            f"{x['neither']} | {x['unsolv']} | {x['rect_in_C']} {x['rect_sizes']} | "
            f"{x['w']}/{x['unsolv']} | {x['h']}/{x['unsolv']} | "
            f"{x['god_ret']}/{x['god_fwd']} |")


def main():
    keep = "--keep" in sys.argv
    os.makedirs(DUMPROOT, exist_ok=True)
    path = os.path.join(ROOT, "sweep_geom_matrix.md")
    fh = open(path, "w", encoding="utf-8")
    fh.write("| (m,n,s) | \\|A\\| | \\|F\\| | \\|R\\| | 可解 | 困局 | 兩不沾 | 不可解 |"
             " C 內實心矩形 | 弱或 | 無洞 | god 回程/正向 |\n")
    fh.write("|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|\n")
    fh.flush()
    try:
        for (m, n, s) in SIZES:
            tag = f"{m}_{n}_{s}"
            d = os.path.join(DUMPROOT, tag)
            os.makedirs(d, exist_ok=True)
            r = subprocess.run([EXE, str(m), str(n), str(s), "-dump", d],
                               capture_output=True, text=True)
            if not os.path.exists(os.path.join(d, "membership.bin")):
                print(f"[skip] {tag}: {r.stdout.strip()} {r.stderr.strip()}", flush=True)
                continue
            st = analyse(d, m, n, s, want_edges=True)
            st["tag"] = tag
            fh.write(row_md(st) + "\n")
            fh.flush()
            print(f"[ok] {tag:8s} N={st['N']:7d} unsolv={st['unsolv']:5d} "
                  f"弱或={st['w']}/{st['unsolv']} 有洞={st['h']}/{st['unsolv']} "
                  f"god {st['god_ret']}/{st['god_fwd']}", flush=True)
            if not keep:
                shutil.rmtree(d, ignore_errors=True)
    finally:
        fh.close()
    print("\n寫入 " + path, flush=True)


main()
