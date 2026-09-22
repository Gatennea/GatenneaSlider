# -*- coding: utf-8 -*-
"""
棋形凸包裁剪工具（多個視圖共用）。

triangle_view 與 mi_view 都要把縫隙線／背景網格裁到「棋形凸包」上
（洞裡不斷線，與原版一致），凸包與穿綫求交的邏輯完全相同，故收到這裡，
避免第三份拷貝。純函式、無狀態，對座標系不作假設：直綫一律由呼叫方換算
成「第二分量 = level」的形式，本模組只問第一個分量的取值區間。
"""

from __future__ import annotations


def convex_hull(points) -> list:
    """二維點集的凸包（單調鏈；共線點保留也無妨，裁剪只問穿邊交點）。"""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def half(seq):
        chain = []
        for p in seq:
            while len(chain) >= 2 and cross(chain[-2], chain[-1], p) <= 0:
                chain.pop()
            chain.append(p)
        return chain

    lower = half(pts)
    upper = half(reversed(pts))
    return lower[:-1] + upper[:-1]


def chord(uv, level: float):
    """(u, v) 點集與直綫 v = level 相交時，u 的參數區間 (u_min, u_max)。

    凸多邊形與直綫相交成一條綫段，故把所有穿邊交點的 u 取最小/最大即得兩端；
    頂點正好落在綫上也要算進來（差值為 0 不算「同側」）。只在一個頂點相切
    時回傳 None。
    """
    ts = []
    n = len(uv)
    for k in range(n):
        u1, v1 = uv[k]
        u2, v2 = uv[(k + 1) % n]
        d1, d2 = v1 - level, v2 - level
        if d1 == 0:
            ts.append(u1)
        if d2 == 0:
            ts.append(u2)
        if d1 == 0 or d2 == 0 or (d1 > 0) == (d2 > 0):
            continue
        ts.append(u1 + (level - v1) * (u2 - u1) / (v2 - v1))
    if not ts:
        return None
    lo, hi = min(ts), max(ts)
    if hi - lo <= 1e-9:
        return None
    return (lo, hi)
