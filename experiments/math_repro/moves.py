"""依 核心玩法形式化 §2 實作的移動生成器（單步 = s 格位移，逐步驗證碰撞與四連通）。

只依賴格點集合，不依賴引擎 dump。用於：
1) 反推引擎邊「到底是哪一步」；
2) 之後做帶標籤的走法搜尋（O-4）。
"""

def connected(cs):
    cs = set(cs)
    if not cs:
        return False
    seed = next(iter(cs))
    stack = [seed]
    seen = {seed}
    while stack:
        r, c = stack.pop()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (r + dr, c + dc)
            if n in cs and n not in seen:
                seen.add(n)
                stack.append(n)
    return len(seen) == len(cs)


def components(cs):
    cs = set(cs)
    comps = []
    while cs:
        seed = next(iter(cs))
        stack = [seed]
        seen = {seed}
        while stack:
            r, c = stack.pop()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (r + dr, c + dc)
                if n in cs and n not in seen:
                    seen.add(n)
                    stack.append(n)
        comps.append(frozenset(seen))
        cs -= seen
    return comps


def legal_moves(S, s=2):
    """回傳 [(seam, side, comp, unit)]，unit 為每步位移"""
    S = frozenset(S)
    out = []
    rmin = min(r for r, _ in S); rmax = max(r for r, _ in S)
    cmin = min(c for _, c in S); cmax = max(c for _, c in S)
    for k in range(rmin, rmax):                      # 水平縫 H_k
        up = frozenset(p for p in S if p[0] <= k)
        down = frozenset(p for p in S if p[0] > k)
        for side, sel in (("上", up), ("下", down)):
            for comp in components(sel):
                for unit in ((0, 1), (0, -1)):
                    out.append(("H_%d" % k, side, comp, unit))
    for k in range(cmin, cmax):                      # 垂直縫 V_k
        left = frozenset(p for p in S if p[1] <= k)
        right = frozenset(p for p in S if p[1] > k)
        for side, sel in (("左", left), ("右", right)):
            for comp in components(sel):
                for unit in ((1, 0), (-1, 0)):
                    out.append(("V_%d" % k, side, comp, unit))
    return out


def apply_move(S, comp, unit, s=2):
    """合法則回傳新集合，非法回傳 None（每步都檢查碰撞與四連通）"""
    S = frozenset(S)
    rest = S - comp
    if not rest:
        return None
    for i in range(1, s + 1):
        moved = frozenset((r + i * unit[0], c + i * unit[1]) for r, c in comp)
        nxt = rest | moved
        if len(nxt) != len(S):
            return None
        if not connected(nxt):
            return None
    return frozenset(rest | frozenset((r + s * unit[0], c + s * unit[1]) for r, c in comp))


def normalize(cs):
    rmin = min(r for r, _ in cs); cmin = min(c for _, c in cs)
    return frozenset((r - rmin, c - cmin) for r, c in cs)


def moves_to(S, target, s=2, normalized=True):
    """列出從 S 一步到 target 的所有合法走法（target 可為正規化過的集合）"""
    want = normalize(target) if normalized else frozenset(target)
    hits = []
    for seam, side, comp, unit in legal_moves(S, s):
        nxt = apply_move(S, comp, unit, s)
        if nxt is None:
            continue
        if normalize(nxt) == want:
            hits.append((seam, side, comp, unit))
    return hits
