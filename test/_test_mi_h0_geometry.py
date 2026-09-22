# -*- coding: utf-8 -*-
"""米字格斜向「一格」H0：把規劃 §1.1~§1.5 的幾何結論固化成斷言。

術語（用戶 2026-09-23 定）：**一格 = 該方向上能滑動的最小量**，跟幾何長度
無關。斜向一格是座標 ±(½,½)，幾何長度 = 格寬的 √2/2；橫豎一格是座標 ±1，
幾何長度 = 格寬。規劃與代碼裡不再把斜向那一步叫「半格/半步」——那就是
一格；要談實際長度就報長度。舊版的斜向 ±(1,1) 相應地是「斜向兩格」。


規劃：.zcode/plans/plan-mi-zige-diagonal-unit.md。H0 只寫測試、不改玩法，
H1 才動 game_mi.py。五節各守一件事：

§1.1 晶格類不變量：斜向一格（±(½,½)）把位置從 A 晶格（整數座標）搬到
     B 晶格（半整數座標）。真正的不變量是「2r 與 2c 同奇偶」（等價於
     r−c 恆為整數）——不是單個坐標的奇偶不變，整格平移本來就會翻轉
     其中一個。兩條後果：h/v 的 gap_rank 會出現半整數（規劃表 3 那一
     項）；d1/d2 的 gap_rank 恆為整數（rank 公式不用改，規劃 §1.3
     末段）。至於 d1/d2 的候選 line：滿盤上只有偶數 line（穿格心）有效，
     奇數 line（兩條對角之間）要等某條對角缺了半邊塊才可能出現，所以
     規劃表 5 說的「候選 line 由塊的邊導出」不能圖省事沿用逐 2 的 range。
§1.2 兩側不重疊：枚舉 1×1~5×5 全部棋盤 × 每條有效縫 × 兩個平行方向，
     斷言「不撞 key + 移動側每個頂點的帶號距離一個不變 + 兩側無正面積
     重疊」。這是規劃 §1.2 半平面論證的構造性驗證。
§1.3 縫隙枚舉表：把規劃裡那張表逐行斷言（對齊態 → 一次斜向一格之後
     四族的有效縫），含「對角中線把盤面一分為二」的退化局面（橫豎全空）
     與階梯交界處長出的半整數縫。數值一律用**幾何縫線座標** g：
     h 是 y=g、v 是 x=g、d1 是 y−x=g、d2 是 x+y=g；引擎 line 與 g 的
     換算見 seam_g()，表的 line 欄是引擎 line（與規劃一致）。
§1.4 鄰接表：跨晶格鄰恰 2 個、表對稱、相鄰而非重疊；並斷言「不擴表的
     後果」——整數鄰接表下，每一次斜向一格都把棋盤裂成 ≥2 個連通分量
     （H1 起 game_mi.neighbors 本身已含跨晶格鄰，這裡的整數表改為本檔
     自帶的副本，好讓這條斷言不隨引擎演進而失效；引擎層的對應斷言見
     test/_test_mi_core.py）。
§1.5 碰撞判據：同晶格 4032 對零重疊（快速路徑成立）；混合晶格確實有
     正面積重疊（面積恆為 1/8 塊），而且隨機能抵達——一個三步序列讓
     「位置集合不相交」這個判據把一個碰撞步放過去（H1 起引擎改跑幾何
     判定，同一個夾具改在 _test_mi_core.py 斷言它被擋下）。

規劃 §1.5 的絕對計數（「13366 對裡 128 對」）依賴具體的 key 視窗，換個
視窗數字就變（本檔的視窗：A 4×4 全部 64 塊 × B 同起點 4×4 全部 64 塊
= 4096 對中 98 對），所以只斷言結構：存在性、面積恆等、可達性。

执行：python test/_test_mi_h0_geometry.py
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import game_mi  # noqa: E402
from game_mi import GAP_DIRECTIONS, MiSliderMatrix, mi_vertices  # noqa: E402

EPS = 1e-9
_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


# ================================================================ 參考實現
# 規劃 §2 表 1 的新方向表：斜向從兩格 ±(1,1) 改成一格 ±(½,½) / ±(½,−½)
NEW_DIRECTIONS = {
    'q': (-0.5, -0.5), 'e': (-0.5, 0.5), 'z': (0.5, -0.5), 'x': (0.5, 0.5),
    'w': (-1.0, 0.0), 's': (1.0, 0.0), 'a': (0.0, -1.0), 'd': (0.0, 1.0),
}

# 規劃 §1.4 的跨晶格鄰接表（每塊恰 2 個異晶格鄰）
CROSS_NEIGHBORS = {
    'N': (('S', -0.5, -0.5), ('S', -0.5, 0.5)),
    'E': (('W', -0.5, 0.5), ('W', 0.5, 0.5)),
    'S': (('N', 0.5, -0.5), ('N', 0.5, 0.5)),
    'W': (('E', -0.5, -0.5), ('E', 0.5, -0.5)),
}

# 整數鄰接表（3 個同晶格鄰）= game_mi.neighbors 在 H1 之前的樣子。
# H1 起引擎的 neighbors 已含跨晶格鄰，所以這裡保存一份副本：本檔要斷言的
# 是「不擴這張表會怎樣」，那份事實不隨引擎演進而改變。
INT_NEIGHBORS = {
    'N': ((0, 0, 'W'), (0, 0, 'E'), (-1, 0, 'S')),
    'E': ((0, 0, 'N'), (0, 0, 'S'), (0, 1, 'W')),
    'S': ((0, 0, 'E'), (0, 0, 'W'), (1, 0, 'N')),
    'W': ((0, 0, 'N'), (0, 0, 'S'), (0, -1, 'E')),
}


def int_neighbors(key):
    """舊的整數鄰接表：每塊恰 3 個同晶格鄰。"""
    r, c, q = key
    return tuple((r + dr, c + dc, dq) for dr, dc, dq in INT_NEIGHBORS[q])


def ext_neighbors(key):
    """整數鄰接表 3 個同晶格鄰 + §1.4 的 2 個跨晶格鄰（共 5 個）。"""
    r, c, q = key
    cross = tuple((r + dr, c + dc, nq) for (nq, dr, dc) in CROSS_NEIGHBORS[q])
    return int_neighbors(key) + cross


def poly(key):
    return [tuple(p) for p in mi_vertices(*key)]


def signed_area(p):
    s = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def clip_poly(subject, clipper):
    """Sutherland–Hodgman：subject 被 clipper 裁掉的部分。"""
    out = list(subject)
    n = len(clipper)
    for i in range(n):
        a, b = clipper[i], clipper[(i + 1) % n]
        inp, out = out, []
        if not inp:
            return []
        prev = inp[-1]
        for cur in inp:
            def inside(p):
                return ((b[0] - a[0]) * (p[1] - a[1])
                        - (b[1] - a[1]) * (p[0] - a[0])) >= -EPS

            def crossing(p, q):
                rx, ry = q[0] - p[0], q[1] - p[1]
                sx, sy = b[0] - a[0], b[1] - a[1]
                den = rx * sy - ry * sx
                if abs(den) < 1e-15:
                    return q
                t = ((a[0] - p[0]) * sy - (a[1] - p[1]) * sx) / den
                return (p[0] + t * rx, p[1] + t * ry)

            cin, pin = inside(cur), inside(prev)
            if cin:
                if not pin:
                    out.append(crossing(prev, cur))
                out.append(cur)
            elif pin:
                out.append(crossing(prev, cur))
            prev = cur
    return out


def overlap_area(a, b):
    """兩塊的重疊面積（>0 才是「正面積重疊」）；接觸（邊/點）算 0。"""
    p1, p2 = poly(a), poly(b)
    if signed_area(p1) < 0:
        p1.reverse()
    if signed_area(p2) < 0:
        p2.reverse()
    return abs(signed_area(clip_poly(p1, p2)))


def span(fam, key):
    """一塊在某族縫線座標 g 下的跨度（r/c 可半整數）。"""
    r, c, q = key
    if fam == 'h':
        return (r, r + 1.0)
    if fam == 'v':
        return (c, c + 1.0)
    k = (r - c) if fam == 'd1' else (r + c)
    if fam == 'd1':
        return (k - 1.0, k) if q in ('N', 'E') else (k, k + 1.0)
    return (k, k + 1.0) if q in ('N', 'W') else (k + 1.0, k + 2.0)


def seam_g(fam, line):
    """引擎 line → 幾何縫線座標 g（h: y、v: x、d1: y−x、d2: x+y）。"""
    if fam in ('h', 'v'):
        return line + 1.0
    if fam == 'd1':
        return line / 2.0
    return line / 2.0 + 1.0


def engine_line(fam, g):
    """幾何縫線座標 g → 引擎 line（seam_g 的反函數）。"""
    if fam in ('h', 'v'):
        return g - 1.0
    if fam == 'd1':
        return 2.0 * g
    return 2.0 * (g - 1.0)


def g_coord(fam, vertex):
    """頂點 (x, y) 在某族縫線座標下的值。"""
    x, y = vertex
    if fam == 'h':
        return y
    if fam == 'v':
        return x
    if fam == 'd1':
        return y - x
    return x + y


def geom_lines(cells, fam):
    """有效縫線（幾何座標 g，0.5 步進；跨度端點都是 0.5 的倍數故不缺）。"""
    spans = [span(fam, c) for c in cells]
    lo = min(t for t, _b in spans)
    hi = max(b for _t, b in spans)
    out, x = [], lo
    while x <= hi + EPS:
        cut = any(t < x - EPS and x + EPS < b for t, b in spans)
        if not cut:
            above = any(b <= x + EPS for _t, b in spans)
            below = any(t >= x - EPS for t, _b in spans)
            if above and below:
                out.append(round(x, 3))
        x += 0.5
    return out


def side_of_geom(fam, g, key):
    """塊整體在幾何縫線 g 的哪一側：0/1；騎線（縫切進塊內）回 None。"""
    fs = [g_coord(fam, v) - g for v in poly(key)]
    if all(f <= EPS for f in fs):
        return 0
    if all(f >= -EPS for f in fs):
        return 1
    return None


# ================================================================ §1.1
print("== §1.1 晶格類不變量 ==")


def two_r_c_integral(key):
    return abs(2 * key[0] - round(2 * key[0])) < EPS and \
        abs(2 * key[1] - round(2 * key[1])) < EPS


def parity(key):
    return (int(round(2 * key[0])) % 2, int(round(2 * key[1])) % 2)


A_keys = [(r, c, q) for r in range(3) for c in range(3) for q in 'NESW']
B_keys = [(r + 0.5, c + 0.5, q) for r in range(3) for c in range(3)
          for q in 'NESW']

bad_par, bad_int, bad_rank, bad_flip = [], [], [], []
for key in A_keys + B_keys:
    for d in NEW_DIRECTIONS:
        dv = NEW_DIRECTIONS[d]
        moved = (key[0] + dv[0], key[1] + dv[1], key[2])
        # 不變量是「2r 與 2c 同奇偶」（等價於 r−c 恆為整數），不是單個
        # 坐標的奇偶不變——整格平移本來就會把 2r 或 2c 翻個奇偶。
        if parity(moved)[0] != parity(moved)[1]:
            bad_par.append((key, d, moved))
        if not two_r_c_integral(moved):
            bad_int.append((key, d, moved))
        # 斜向一格把 A 晶格搬成 B 晶格（奇偶翻轉）；橫豎一格不換晶格
        diag = d in ('q', 'e', 'z', 'x')
        if diag != (parity(moved)[0] != parity(key)[0]):
            bad_flip.append((key, d))
        # d1/d2 的 rank = 2(r∓c) + 朝向：r 與 c 小數部分永遠相同，
        # 所以 r−c 恆為整數、rank 恆為整數（奇偶由朝向 N/E 與 S/W 決定）
        if diag:
            for fam in ('d1', 'd2'):
                rank = game_mi.gap_rank(fam, moved)
                if abs(rank - round(rank)) > EPS:
                    bad_rank.append((fam, moved, rank))
check(f"8 個方向平移都保持「2r 與 2c 同奇偶」（{len(A_keys) + len(B_keys)} 塊 × 8 向）",
      not bad_par, str(bad_par[:3]))
check("平移後 2r/2c 仍是整數（只會從 A 晶格搬到 B 晶格，不落到別的柵格上）",
      not bad_int, str(bad_int[:3]))
check("斜向一格 A↔B 換晶格、橫豎一格不換晶格", not bad_flip, str(bad_flip[:3]))
check("d1/d2 的 gap_rank 恆為整數（r−c 恆整，rank 公式不用改）",
      not bad_rank, str(bad_rank[:3]))

# h/v 的 rank 則是半整數：這是規劃表 3「允許半整數」的那一項
half_ranks = [game_mi.gap_rank('h', k) for k in B_keys]
check("h/v 的 gap_rank 在錯位態確實出現半整數",
      any(abs(v - round(v)) > EPS for v in half_ranks),
      f'例 {sorted(set(half_ranks))[:5]}')

# mi_vertices 是線性的：半整數座標原樣可用，且半步平移 = 整體平移
bad_aff = []
for key in A_keys[:8]:
    for d in ('q', 'e', 'z', 'x', 'w', 'a'):
        dr, dc = NEW_DIRECTIONS[d]
        want = sorted((x + dc, y + dr) for (x, y) in mi_vertices(*key))
        got = sorted(tuple(p) for p in mi_vertices(key[0] + dr, key[1] + dc, key[2]))
        if any(abs(a[0] - b[0]) > EPS or abs(a[1] - b[1]) > EPS
               for a, b in zip(want, got)) or len(want) != len(got):
            bad_aff.append((key, d))
check("mi_vertices 對半整數座標原樣可用（線性，斜向一格 = 整體平移）",
      not bad_aff, str(bad_aff[:3]))

# ================================================================ §1.2
print("== §1.2 兩側不重疊（半平面論證的構造性驗證） ==")
n_combo = n_clean = 0
viol = []
for m in range(1, 6):
    for n in range(1, 6):
        cells = MiSliderMatrix(m, n).positions()
        for fam in ('h', 'v', 'd1', 'd2'):
            for g in geom_lines(cells, fam):
                side1 = {c for c in cells if side_of_geom(fam, g, c) == 1}
                if not side1 or side1 == cells:
                    continue
                for d in GAP_DIRECTIONS[fam]:
                    dv = NEW_DIRECTIONS[d]
                    n_combo += 1
                    moved = {(c[0] + dv[0], c[1] + dv[1], c[2]) for c in side1}
                    fixed = cells - side1
                    if moved & fixed:
                        viol.append(('撞 key', m, n, fam, g, d))
                        continue
                    bad = 0
                    # 兩側之間無正面積重疊
                    for a, b in itertools.combinations(sorted(moved | fixed), 2):
                        if (a in moved) != (b in moved) and overlap_area(a, b) > EPS:
                            bad += 1
                    # 移動方向與縫平行：每個頂點的帶號距離一個不變
                    for c in side1:
                        old = [g_coord(fam, v) - g for v in poly(c)]
                        new = [g_coord(fam, v) - g
                               for v in poly((c[0] + dv[0], c[1] + dv[1], c[2]))]
                        if any(abs(x - y) > EPS for x, y in zip(old, new)):
                            bad += 1000
                    if bad:
                        viol.append((bad, m, n, fam, g, d))
                    else:
                        n_clean += 1
check(f"1×1~5×5 × 每條有效縫 × 兩個平行方向共 {n_combo} 組全部乾淨",
      n_combo > 400 and not viol, str(viol[:3]))
check("枚舉數量覆蓋到 4 個族（不是只測了橫豎）", n_combo >= 500,
      f'實得 {n_combo}')

# ================================================================ §1.3
print("== §1.3 縫隙枚舉表（對齊態 → 一次斜向一格之後的四族有效縫） ==")

# (說明, m, n, 族, 引擎 line, 方向, {族: 之後的幾何縫線})
TABLE = [
    ('6×6 沿 d1 line=6 走 x', 6, 6, 'd1', 6, 'x',
     {'h': [1, 2, 3], 'v': [4, 5]}),
    ('6×6 沿 v line=2 走 z', 6, 6, 'v', 2, 'z',
     {'h': [], 'v': [1, 2, 3.5, 4.5]}),
    ('6×1 沿 d2 line=6 走 e', 6, 1, 'd2', 6, 'e',
     {'h': [1, 2, 4.5], 'v': []}),
    ('1×6 沿 d1 line=0 走 x', 1, 6, 'd1', 0, 'x',
     {'h': [], 'v': [2, 3, 4, 5]}),
    ('4×4 沿 d2 line=4 走 e', 4, 4, 'd2', 4, 'e',
     {'h': [], 'v': [3.5]}),
    ('4×4 沿 d1 line=2 走 x', 4, 4, 'd1', 2, 'x',
     {'h': [1], 'v': []}),
    ('4×4 沿 d1 line=0 走 x（退化：對角中線一分為二）', 4, 4, 'd1', 0, 'x',
     {'h': [], 'v': []}),
    ('4×4 沿 d1 line=0 走 q（同一個退化局面，反方向）', 4, 4, 'd1', 0, 'q',
     {'h': [], 'v': []}),
    ('2×2 沿 d1 line=0 走 x（最小退化局面）', 2, 2, 'd1', 0, 'x',
     {'h': [], 'v': []}),
]
for (label, m, n, fam, line, d, expect) in TABLE:
    g = seam_g(fam, line)
    cells = MiSliderMatrix(m, n).positions()
    before = {f: geom_lines(cells, f) for f in ('h', 'v', 'd1', 'd2')}
    dv = NEW_DIRECTIONS[d]
    side1 = {c for c in cells if side_of_geom(fam, g, c) == 1}
    after_cells = (cells - side1) | {(c[0] + dv[0], c[1] + dv[1], c[2])
                                     for c in side1}
    after = {f: geom_lines(after_cells, f) for f in ('h', 'v', 'd1', 'd2')}
    ok = all(after[f] == expect[f] for f in expect)
    detail = '；'.join(
        f"{f} {before[f]}→{after[f]}" for f in ('h', 'v', 'd1', 'd2'))
    check(f"{label}：{'、'.join(f'{f}={expect[f]}' for f in expect)}", ok, detail)

# 沿著走的那一族一條都不少（跨度不變）；錯開走的對角色只會在兩端增減
# 注意只取平行於縫的方向（GAP_DIRECTIONS[ fam ]）：不平行於縫的走法
# （規劃表裡 6×6 沿 v 縫走 z 那一行）本來就會改沿走族的縫，不適用這條。
for (label, m, n, fam, line, d) in [
        ('6×6 d1 line=6 x', 6, 6, 'd1', 6, 'x'),
        ('6×6 v line=2 w', 6, 6, 'v', 2, 'w'),
        ('6×6 v line=2 s', 6, 6, 'v', 2, 's'),
        ('6×1 d2 line=6 e', 6, 1, 'd2', 6, 'e'),
        ('4×4 d1 line=0 x', 4, 4, 'd1', 0, 'x'),
        ('4×4 h line=1 a', 4, 4, 'h', 1, 'a')]:
    g = seam_g(fam, line)
    cells = MiSliderMatrix(m, n).positions()
    dv = NEW_DIRECTIONS[d]
    side1 = {c for c in cells if side_of_geom(fam, g, c) == 1}
    after_cells = (cells - side1) | {(c[0] + dv[0], c[1] + dv[1], c[2])
                                     for c in side1}
    before, after = geom_lines(cells, fam), geom_lines(after_cells, fam)
    along = before == after
    other = 'd2' if fam == 'd1' else 'd1'
    ob, oa = geom_lines(cells, other), geom_lines(after_cells, other)
    lost = [v for v in ob if v not in oa]
    gained = [v for v in oa if v not in ob]
    ends_ok = all(v in (ob[0], ob[-1]) for v in lost) and \
        all(v in (ob[0] - 1, ob[-1] + 1) for v in gained) if ob else True
    check(f"{label}：沿走族 {fam} 一條不少、錯開族 {other} 只在兩端增減",
          along and len(lost) <= 2 and len(gained) <= 2 and ends_ok,
          f'{fam} 不變={along}；{other} {ob}→{oa}')

# ================================================================ §1.4
print("== §1.4 鄰接表：跨晶格鄰、對稱性、以及不擴表的後果 ==")
# 每塊恰 5 個鄰（3 同晶格 + 2 跨晶格），且跨晶格鄰與同晶格鄰不重複
bad_cnt, bad_dup = [], []
for r in (0, 0.5, 1.5):
    for c in (0, 0.5, 1.5):
        for q in 'NESW':
            key = (r, c, q)
            ext = ext_neighbors(key)
            if len(ext) != 5:
                bad_cnt.append((key, len(ext)))
            if len(set(ext)) != 5:
                bad_dup.append(key)
check("每塊恰 5 個鄰：3 同晶格 + 2 跨晶格，且互不重複",
      not bad_cnt and not bad_dup,
      f'數量異常 {bad_cnt[:3]}／重複 {bad_dup[:3]}')

# 表對稱：b 是 a 的鄰 ⟹ a 是 b 的鄰
bad_sym = []
window = [(r, c, q) for r in (-1, -0.5, 0, 0.5, 1, 1.5)
          for c in (-1, -0.5, 0, 0.5, 1, 1.5) for q in 'NESW']
for key in window:
    for nb in ext_neighbors(key):
        if key not in ext_neighbors(nb):
            bad_sym.append((key, nb))
check(f"鄰接表對稱（{len(window)} 塊窮舉）", not bad_sym, str(bad_sym[:3]))

# 跨晶格鄰共用整條單位邊、且第三頂點分居該邊兩側（相鄰而不是重疊）
bad_adj = []
for r in (0, 0.5):
    for c in (0, 0.5):
        for q in 'NESW':
            key = (r, c, q)
            mine = poly(key)
            for nb in ext_neighbors(key):
                if nb in int_neighbors(key):
                    continue
                other = poly(nb)
                shared = [v for v in mine if v in other]
                if len(shared) != 2:
                    bad_adj.append((key, nb, 'shared', shared))
                    continue
                if overlap_area(key, nb) > EPS:
                    bad_adj.append((key, nb, 'overlap', overlap_area(key, nb)))
                a, b = shared
                ex, ey = (b[0] - a[0], b[1] - a[1])
                L2 = ex * ex + ey * ey
                signs = []
                for v in (mine, other):
                    third = [p for p in v if p not in shared][0]
                    signs.append((ex * (third[1] - a[1]) - ey * (third[0] - a[0]))
                                 / (L2 ** 0.5))
                if signs[0] * signs[1] >= 0:
                    bad_adj.append((key, nb, 'same side', signs))
check("跨晶格鄰共用整條邊、第三頂點分居兩側（相鄰而非重疊）",
      not bad_adj, str(bad_adj[:3]))


def components(cells, table):
    seen, out = set(), []
    for s in sorted(cells):
        if s in seen:
            continue
        stack, comp = [s], set()
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp.add(cur)
            for nb in table(cur):
                if nb in cells and nb not in comp:
                    stack.append(nb)
        seen |= comp
        out.append(comp)
    return out


def after_one(m, n, fam, line, d):
    """對齊態沿 (fam, line) 走一次方向 d 之後的全部位置。"""
    cells = MiSliderMatrix(m, n).positions()
    g = seam_g(fam, line)
    dv = NEW_DIRECTIONS[d]
    side1 = {c for c in cells if side_of_geom(fam, g, c) == 1}
    return (cells - side1) | {(c[0] + dv[0], c[1] + dv[1], c[2])
                              for c in side1}


SCEN = [('4×4 d1 0 x', 4, 4, 'd1', 0, 'x'),
        ('4×4 d1 0 q', 4, 4, 'd1', 0, 'q'),
        ('4×4 d2 4 e', 4, 4, 'd2', 4, 'e'),
        ('6×6 d1 6 x', 6, 6, 'd1', 6, 'x'),
        ('6×6 v 2 z', 6, 6, 'v', 2, 'z')]
bad_old, bad_new = [], []
for (label, m, n, fam, line, d) in SCEN:
    cells = after_one(m, n, fam, line, d)
    old, new = components(cells, int_neighbors), components(cells, ext_neighbors)
    if len(old) < 2:
        bad_old.append((label, len(old)))
    if len(new) != 1:
        bad_new.append((label, len(new)))
check("現行整數鄰接表下，每次斜向一格之後棋盤都裂成 ≥2 個連通分量",
      not bad_old, str(bad_old[:3]))
check("換成擴展表（+2 個跨晶格鄰）之後合回單一連通分量",
      not bad_new, str(bad_new[:3]))
# 引擎層的同一件事（H1 起 game_mi 的 DIRECTIONS / neighbors 就是這两张表，
# 斜向一格走得通；把 neighbors 換回整數表就又全被 'disconnected' 擋下）
# 移到 test/_test_mi_core.py —— 那是引擎契約，不是幾何事實。

# ================================================================ §1.5
print("== §1.5 碰撞判據：同晶格零重疊、混合晶格有正面積重疊 ==")
A4 = [(r, c, q) for r in range(4) for c in range(4) for q in 'NESW']
B4 = [(r + 0.5, c + 0.5, q) for r in range(4) for c in range(4) for q in 'NESW']
n_same = n_same_bad = 0
for lat in (A4, B4):
    for a, b in itertools.combinations(lat, 2):
        n_same += 1
        if overlap_area(a, b) > EPS:
            n_same_bad += 1
check(f"同晶格 {n_same} 對零重疊（快速路徑成立）", n_same_bad == 0,
      f'重疊 {n_same_bad} 對')

n_mix = 0
areas = set()
for a in A4:
    for b in B4:
        area = overlap_area(a, b)
        if area > EPS:
            n_mix += 1
            areas.add(round(area, 9))
check(f"混合晶格 A(4×4)×B(同起點 4×4) 確實有正面積重疊：{len(A4) * len(B4)} 對中 {n_mix} 對",
      n_mix > 0, f'面積取值 {sorted(areas)}')
check("混合晶格的重疊面積恆為 1/8 塊（不是連續譜，可按面積歸類）",
      areas == {0.125}, f'實得 {sorted(areas)}')
check("規劃引用的實例：A 晶格 N(0,0) 與 B 晶格 E(−½,−½) 重疊 1/8 塊",
      abs(overlap_area((0, 0, 'N'), (-0.5, -0.5, 'E')) - 0.125) < EPS,
      f'實得 {overlap_area((0, 0, "N"), (-0.5, -0.5, "E"))}')

# 「混合晶格的重疊在普通玩法裡真的會遇到」——可達性要用引擎證明（opt 只移動
# 一側的一個連通分量，同側其它分量留下來才會撞上），所以那個三步夾具放在
# test/_test_mi_core.py：那裡斷言引擎把第三步判 'collision'，並且用手算的
# 候選位置證明「位置集合不相交」這個舊判據確實會放它過去。

print()
if _failures:
    print(f"共 {len(_failures)} 項失敗:")
    for n in _failures:
        print("  -", n)
    sys.exit(1)
print("全部通過")
