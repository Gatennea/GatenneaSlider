"""域检查：A 中实心矩形清单 + 「包围盒适配窗口」是否必要（全量，只读）。
用法: python _chk_domain.py <dump> <m> <n>
"""
import sys, os
import numpy as np
from collections import Counter

def bbox(b):
    N = b.shape[0]
    rmin = np.full(N, 16, np.int32); rmax = np.full(N, -1, np.int32)
    lo = np.full(N, 16, np.int32); hi = np.full(N, -1, np.int32)
    for r in range(16):
        row = b[:, r].astype(np.int64); has = row > 0
        rmin = np.where(has, np.minimum(rmin, r), rmin)
        rmax = np.where(has, np.maximum(rmax, r), rmax)
        for bit in range(16):
            on = (row & (1 << bit)) != 0
            lo = np.where(on, np.minimum(lo, bit), lo)
            hi = np.where(on, np.maximum(hi, bit), hi)
    return rmax - rmin + 1, hi - lo + 1

def main():
    dump, m, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    N = os.path.getsize(os.path.join(dump, "membership.bin")) // 16
    b = np.fromfile(os.path.join(dump, "boards.bin"), dtype="<u2").reshape(N, 16)
    mem = np.fromfile(os.path.join(dump, "membership.bin"), dtype=np.uint8).reshape(N, 16)
    fl = mem[:, 4]; inB = (fl & 2) != 0
    H, W = bbox(b)
    rect = (H * W == 16)          # 16 格填满包围盒 = 实心矩形
    print("A 总数:", N, " 实心矩形:", int(rect.sum()))
    for i in np.nonzero(rect)[0]:
        print(f"   {int(H[i])}x{int(W[i])}  inB={bool(inB[i])}  outdeg={int(mem[i,6])}")
    fit = (np.minimum(H, W) <= min(m, n)) & (np.maximum(H, W) <= max(m, n))
    print("适配窗口:", int(fit.sum()), " 不適配却可解:", int(((~fit) & inB).sum()),
          " 适配却不可解:", int((fit & ~inB).sum()))
    print("不適配 bbox 前 5:", Counter(zip(H[~fit].tolist(), W[~fit].tolist())).most_common(5))

main()
