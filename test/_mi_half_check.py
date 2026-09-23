# -*- coding: utf-8 -*-
"""H0 预研：斜向一格（半格平移）的三件事，全部用独立实现验证，不靠手推结论。

1. 跨晶格鄰接：對每塊窮舉半格位置的候選塊，用「兩條直角邊線段重合」
   判定相鄰（獨立於手推表），再與手推表逐條對帳。
2. 幾何不重疊：精確三角形相交（分離軸），枚舉大量隨機局勢 × 全部合法
   縫 × 全部方向，一步斜向一格後逐塊檢查。
3. 連通性：半步後用擴充後的鄰接表跑 is_single_connected，統計
   disconnected 的次數與原因。
"""
import os
import sys
import random

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from game_mi import (MiSliderMatrix, DIRECTIONS, GAP_DIRECTIONS,  # noqa: E402
                     mi_vertices, side_of, gap_rank)
from game import Block  # noqa: E402

EPS = 1e-9


# ---------- 1. 跨晶格鄰接（獨立實現：邊線段重合） ----------
def _edges(key):
    v = _tri(key)
    return [frozenset((tuple(v[i]), tuple(v[(i + 1) % 3]))) for i in range(3)]


def _same_point(a, b):
    return abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9


def _share_edge(poly1, poly2):
    """兩個三角形是否共用一條完整邊，且第三頂點分居該邊兩側。

    只共線段還不夠：跨晶格時兩塊可能共用同一條直角邊卻趴在同側
    （那種是重疊，不是相鄰）。
    """
    n = len(poly1)
    for i in range(n):
        a1 = poly1[i]
        b1 = poly1[(i + 1) % n]
        t1 = poly1[(i + 2) % n]
        for j in range(len(poly2)):
            a2 = poly2[j]
            b2 = poly2[(j + 1) % len(poly2)]
            t2 = poly2[(j + 2) % len(poly2)]
            if not ((_same_point(a1, a2) and _same_point(b1, b2)) or
                    (_same_point(a1, b2) and _same_point(b1, a2))):
                continue
            if _same_point(t1, a1) or _same_point(t1, b1):
                continue
            if _same_point(t2, a1) or _same_point(t2, b1):
                continue
            nx, ny = -(b1[1] - a1[1]), b1[0] - a1[0]
            base = nx * a1[0] + ny * a1[1]
            s1 = nx * t1[0] + ny * t1[1] - base
            s2 = nx * t2[0] + ny * t2[1] - base
            if s1 * s2 < -1e-9:
                return True
    return False


_KEY_CACHE = {}


def _tri(key):
    if key not in _KEY_CACHE:
        _KEY_CACHE[key] = list(mi_vertices(*key))
    return _KEY_CACHE[key]


def neighbors_all(key):
    """3 個同晶格鄰 + 窮舉得出的跨晶格鄰（共用完整邊且分居兩側）。

    窮舉範圍取半步格（dr, dc ∈ {−2..2} / 2）：跨晶格鄰的偏移是
    (±0.5, ±0.5)，整數偏移的窮舉看不到它們。
    """
    out = []
    poly = _tri(key)
    r, c, q = key
    for dr in (-2, -1, 0, 1, 2):
        for dc in (-2, -1, 0, 1, 2):
            for q2 in ('N', 'E', 'S', 'W'):
                cand = (r + dr / 2.0, c + dc / 2.0, q2)
                if cand == key:
                    continue
                if _share_edge(poly, _tri(cand)):
                    out.append(cand)
    return out


def neighbors_table(key):
    """手推表：3 個同晶格鄰（整數坐標）+ 2 個跨晶格鄰。"""
    r, c, q = key
    same = {
        'N': ((r, c, 'W'), (r, c, 'E'), (r - 1, c, 'S')),
        'E': ((r, c, 'N'), (r, c, 'S'), (r, c + 1, 'W')),
        'S': ((r, c, 'E'), (r, c, 'W'), (r + 1, c, 'N')),
        'W': ((r, c, 'N'), (r, c, 'S'), (r, c - 1, 'E')),
    }[q]
    cross = {
        'N': ((r - 0.5, c - 0.5, 'S'), (r - 0.5, c + 0.5, 'S')),
        'E': ((r - 0.5, c + 0.5, 'W'), (r + 0.5, c + 0.5, 'W')),
        'S': ((r + 0.5, c - 0.5, 'N'), (r + 0.5, c + 0.5, 'N')),
        'W': ((r - 0.5, c - 0.5, 'E'), (r + 0.5, c - 0.5, 'E')),
    }[q]
    return same + cross


def check_table():
    bad = 0
    for r in range(-2, 3):
        for c in range(-2, 3):
            for q in ('N', 'E', 'S', 'W'):
                brute = sorted(neighbors_all((r, c, q)))
                table = sorted(neighbors_table((r, c, q)))
                if brute != table:
                    bad += 1
                    if bad <= 3:
                        print(f'  ✗ {(r, c, q)}: 窮舉 {brute} 表 {table}')
    print(f'鄰接表對帳：{25 * 4 - bad}/{25 * 4} 一致')
    return bad == 0


# ---------- 2/3. 半格移動的幾何與連通 ----------
def tri_pts(key):
    return mi_vertices(*key)


def _overlap(p, q):
    """兩個三角形是否「正面積」相交（只貼角/貼邊不算）。

    分離軸允許弱分離（max == min）：貼邊/貼角的投影在一根軸上恰好相等，
    那是零面積接觸，不是重疊。
    """
    for poly in (p, q):
        n = len(poly)
        for i in range(n):
            ax, ay = poly[i]
            bx, by = poly[(i + 1) % n]
            nx, ny = -(by - ay), bx - ax
            pa = [nx * x + ny * y for (x, y) in p]
            pb = [nx * x + ny * y for (x, y) in q]
            if max(pa) <= min(pb) + EPS or max(pb) <= min(pa) + EPS:
                return False
    return True


def connected(cells, nbr_fn):
    if not cells:
        return True
    start = next(iter(cells))
    seen = {start}
    stack = [start]
    while stack:
        cur = stack.pop()
        for nb in nbr_fn(cur):
            if nb in cells and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen) == len(cells)


def half_delta(direction):
    dr, dc = DIRECTIONS[direction]
    return dr / 2.0, dc / 2.0


def valid_lines(cells, fam):
    """精確判據：不切任何塊內部 + 兩側非空（與 _mi_gap_check 同）。"""
    def g_coord(v):
        """頂點 (x, y) 在某族縫線座標下的值。"""
        if fam == 'h':
            return v[1]
        if fam == 'v':
            return v[0]
        return (v[1] - v[0]) if fam == 'd1' else (v[0] + v[1])

    def span(k):
        # 由三個頂點的投影取區間，不用「四朝向一律整格」的捷徑表：h 的 N
        # 只占半格高、v 的 W 只占半格寬，按整格算會把錯位態從半格塊頂點
        # 上過去的半整數縫誤判成切塊
        fs = [g_coord(v) for v in tri_pts(k)]
        return (min(fs), max(fs))
    spans = [span(k) for k in cells]
    lo = min(t for t, _b in spans)
    hi = max(b for _t, b in spans)
    out = []
    x = lo
    while x <= hi + EPS:
        if not any(t < x - EPS and x + EPS < b for t, b in spans):
            above = any(b <= x + EPS for _t, b in spans)
            below = any(t >= x - EPS for _t, _b in spans)
            if above and below:
                out.append(round(x, 3))
        x += 0.5
    return out


def run_cases(rounds=40, seed=20260922):
    rng = random.Random(seed)
    stats = {'moves': 0, 'overlap': 0, 'disc': 0, 'disc_examples': [],
             'overlap_examples': []}
    for t in range(rounds):
        m = rng.choice((2, 3, 4, 5, 6))
        n = rng.choice((2, 3, 4, 5, 6))
        g = MiSliderMatrix(m, n)
        if t:
            g.shuffle(attempts=40, step=1,
                      min_score=rng.choice((0.5, 0.65, 0.8)))
        cells = set(g.positions())
        for fam in ('h', 'v', 'd1', 'd2'):
            # 用精確判據重算 line（h/v 允許半整數，這裡按 rank 語體轉回）
            for line in _lines_for(cells, fam):
                sides = {}
                for k in cells:
                    sides.setdefault(side_of(fam, line, k), []).append(k)
                if len(sides) != 2:
                    continue
                for direction in GAP_DIRECTIONS[fam]:
                    dr, dc = half_delta(direction)
                    # 選中組 = side 1 的連通分量（從任一塊出發）
                    side1 = sides[1]
                    comp = _component(side1, side1[0], neighbors_all)
                    moved = {(k[0] + dr, k[1] + dc, k[2]) for k in comp}
                    rest = cells - set(comp)
                    stats['moves'] += 1
                    after = moved | rest
                    # 幾何不重疊（同時統計「位置集合不相交但幾何重疊」——
                    # 半格位置下不同 key 的塊是可能正面積重疊的）
                    for a in after:
                        for b in after:
                            if a < b and _overlap(tri_pts(a), tri_pts(b)):
                                stats['overlap'] += 1
                                if len(stats['overlap_examples']) < 3:
                                    stats['overlap_examples'].append((a, b))
                    # 連通
                    if not connected(after, neighbors_all):
                        stats['disc'] += 1
                        if len(stats['disc_examples']) < 3:
                            stats['disc_examples'].append(
                                (m, n, fam, line, direction))
    return stats


def _lines_for(cells, fam):
    """候選 line：rank 的最小~最大（h/v 整數；對角族逐 2）。"""
    ranks = [gap_rank(fam, k) for k in cells]
    lo, hi = min(ranks), max(ranks)
    if fam in ('d1', 'd2'):
        # rank 在半整數座標上是整數值的 float（2*(r−c) 的型別跟著座標走），
        # range 只認 int，先取整（值本來就是整數，round 不改變含義）
        return list(range(int(round(lo)), int(round(hi)) + 1, 2))
    return [lo + 0.5 * i for i in range(int(round((hi - lo) * 2)) + 1)]


def _component(cells, start, nbr_fn):
    seen = {start}
    stack = [start]
    while stack:
        cur = stack.pop()
        for nb in nbr_fn(cur):
            if nb in cells and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return seen


if __name__ == '__main__':
    print('=== 1. 跨晶格鄰接表對帳 ===')
    ok = check_table()
    print('=== 2/3. 半格斜向移動：幾何 + 連通 ===')
    st = run_cases()
    print(f"嘗試移動 {st['moves']} 次；幾何重疊 {st['overlap']} 次；"
          f"連通失敗 {st['disc']} 次")
    if st['overlap_examples']:
        print('  重疊例:', st['overlap_examples'])
    if st['disc_examples']:
        print('  連通失敗例:', st['disc_examples'])
    print('結論：', '鄰接表正確' if ok else '鄰接表有錯',
          '；幾何' + ('無重疊' if st['overlap'] == 0 else '有重疊'),
          '；連通' + ('全部通過' if st['disc'] == 0 else '有失敗'))
