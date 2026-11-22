"""自洽審計：把 docs/math/v2/01 的已核數字寫成期望表，從 dump 重算並逐項比對。

用法：
    D:\\python\\python.exe experiments/math_repro/_audit.py

會自動找 experiments/math_repro/_work/<尺寸>/ 或 ../sweep_dumps/<尺寸>/。
任何一項 FAIL 都不准把該數字寫進文檔，先查是哪一邊錯。
注意：flags 的位要用「!= 0」再 sum，直接對 uint8 求 sum 會得到位權而不是個數。
"""
import os
import numpy as np

# 期望值抄自 docs/math/v2/01（已核欄）。N=兩不沾（A−F−R），iso=孤立死（flag64），
# unsolv=「回不去」（不在 R）——這正是 01 §3.2 那一欄的定義。
EXPECT = {
    "4_4_2": dict(A=559832, F=558286, R=559504, S=558277, T=9, N=319, iso=263,
                  unsolv=328, sinks=52, sinks_T=6, sinks_N=46, edges=4270552),
    "4_4_3": dict(A=24605, F=21761, R=23163, S=21755, T=6, N=1436, iso=1094,
                  unsolv=1442, sinks=327, sinks_T=2, sinks_N=325, edges=94274),
    "5_3_2": dict(A=250620, F=249928, R=250433, S=249928, T=0, N=187, iso=152,
                  unsolv=187, sinks=None, sinks_T=None, sinks_N=None, edges=1772759),
    "4_3_2": dict(A=8127, F=8028, R=8057, S=8028, T=0, N=70, iso=56,
                  unsolv=70, sinks=None, sinks_T=None, sinks_N=None, edges=43777),
    "4_3_3": dict(A=1202, F=4, R=4, S=4, T=0, N=1198, iso=1154,
                  unsolv=1198, sinks=None, sinks_T=None, sinks_N=None, edges=3104),
}


def load(d):
    m = np.fromfile(os.path.join(d, "membership.bin"), dtype=np.uint8).reshape(-1, 16)
    f = m[:, 4].astype(np.int64)
    od = m[:, 6:8].copy().view("<u2").ravel().astype(np.int64)
    e = np.fromfile(os.path.join(d, "edges.bin"), dtype="<u4").reshape(-1, 2)
    return f, od, e


def audit(name, d, exp):
    f, od, e = load(d)
    A = len(f)
    F = int(((f & 1) != 0).sum()); R = int(((f & 2) != 0).sum()); S = int(((f & 128) != 0).sum())
    T = int(((f & 16) != 0).sum()); iso = int(((f & 64) != 0).sum())
    N = A - (F + R - S)
    unsolv = A - R
    sinks = int((od == 0).sum())
    sinks_T = int(((od == 0) & ((f & 16) != 0)).sum())
    sinks_N = int(((od == 0) & (((f & 1) | (f & 2)) == 0)).sum())
    got = dict(A=A, F=F, R=R, S=S, T=T, N=N, iso=iso, unsolv=unsolv,
               sinks=sinks, sinks_T=sinks_T, sinks_N=sinks_N, edges=len(e))
    bad = [f"{k}: 期望 {v} 實得 {got[k]}" for k, v in exp.items() if v is not None and got[k] != v]
    print(f"{name:8s} " + ("PASS" if not bad else "FAIL → " + "；".join(bad)))
    print(f"          A={A} F={F} R={R} S={S} T={T} N={N} iso={iso} 回不去={unsolv} "
          f"凍結={sinks}(T{sinks_T}/N{sinks_N}) 邊={len(e)}")


for name, exp in EXPECT.items():
    for cand in (os.path.join("experiments/math_repro/_work", name),
                 os.path.join("..", "sweep_dumps", name)):
        if os.path.exists(os.path.join(cand, "membership.bin")):
            audit(name, cand, exp)
            break
    else:
        print(f"{name}: 找不到 dump")
