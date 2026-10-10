# -*- coding: utf-8 -*-
"""階段2 驗收：剖面缺陷預篩（k=8）vs 舊行為（k=0）。

ABAB 交替 + 逐輪配對（用戶定的測量紀律：本機漂移大，10~20% 量級必須這樣測）。
同時驗證：k=8 與 k=0 的最終聚攏度必須一致（質量不退化）。
"""

import sys
import time
import os
import json
import statistics

sys.path.insert(0, ".")

from solver.ml.fill_macro import build_game  # noqa: E402
from solver.ml.gather_solver import gather_solve  # noqa: E402


def load(path, snap_idx=0):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    snap = doc["history"]["snapshots"][snap_idx]
    b = snap["bounds"]
    coords = frozenset((b["min_row"] + i, b["min_col"] + j)
                       for i, row in enumerate(snap["matrix"])
                       for j, v in enumerate(row) if v)
    pz = doc["puzzle"]
    return coords, pz["m"], pz["n"], pz["step"]


BOARDS = [
    ("archives/失败06.json", 0),
    ("archives/失败07.json", 0),
    ("archives/2-7-8-20261001-185331.json", 0),
]


def bench_one(coords, m, n, step, k, rounds=6):
    times = []
    scores = []
    for _ in range(rounds):
        g = build_game(coords, m, n)
        t0 = time.time()
        r = gather_solve(g, step, max_steps=300, patience=80,
                         max_wait_time=30, phi_prescreen_k=k)
        times.append(time.time() - t0)
        scores.append(r["end"]["score"])
    return statistics.median(times), scores


def main():
    for rel, _ in BOARDS:
        coords, m, n, step = load(rel)
        # ABAB 交替：A=k0, B=k8，逐輪配對
        k0_times, k8_times = [], []
        k0_scores, k8_scores = [], []
        for i in range(6):
            k = 0 if i % 2 == 0 else 8
            g = build_game(coords, m, n)
            t0 = time.time()
            r = gather_solve(g, step, max_steps=300, patience=80,
                             max_wait_time=30, phi_prescreen_k=k)
            dt = time.time() - t0
            if k == 0:
                k0_times.append(dt); k0_scores.append(r["end"]["score"])
            else:
                k8_times.append(dt); k8_scores.append(r["end"]["score"])
        med0, med8 = statistics.median(k0_times), statistics.median(k8_times)
        score0 = statistics.median(k0_scores)
        score8 = statistics.median(k8_scores)
        ratio = med0 / med8 if med8 else float("inf")
        score_ok = abs(score0 - score8) < 1e-9
        print("[%s]" % rel)
        print("  k=0 中位時間 %.3fs | k=8 中位時間 %.3fs | k8/k0 時間比 %.2f (越小越快)" %
              (med0, med8, ratio))
        print("  最終聚攏度 k0=%.5f k8=%.5f | 質量一致=%s" % (score0, score8, score_ok))
        assert score_ok, "質量退化！"


if __name__ == "__main__":
    main()
