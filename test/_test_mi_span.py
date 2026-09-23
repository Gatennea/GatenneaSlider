# -*- coding: utf-8 -*-
"""無頭測試：米字格橫豎縫的跨度必須按「真實投影區間」算（半格朝向）。

背景（用户 2026-09-23 反饋）：新建 mi-1-2-2 存档的最終局面裡，橫豎縫「按理
都能選中，實際被拒絕」——點下去連高亮都沒有，直接彈「這條縫選不動（錯位態
切在塊裡）」。

根因：span 對 h/v 一律按整格算，(r−1, r)／(c−1, c)。但 N 塊尖朝下只占上半格
[r, r+½]、S 只占下半格 [r+½, r+1]、v 換成 W 只占左半格、E 只占右半格。錯位態
的橫豎縫落在半整數層級上，正好從這兩類塊的頂點擦過去，舊判據把它算成「切在
塊內部」→ is_valid_gap 否掉 → 連選中態都進不去。side_of 用同一個錯誤區間，側
別也跟著錯（本該在線上方/右方的塊被判到另一側）。

修法：h/v 的跨度由三角頂點的投影區間折算（各減 1 換引擎線號），與渲染用的
mi_vertices 同源；gap_rank = 區間高端 − 1，於是「span 高端 = rank + 1」這條
不變式在 h/v 上結構性地成立。整數線不受影響（對齊態的橫豎縫一條不多一條不
少），d1/d2 族本來就是正確的，沒動。

本檔四件事：①span/gap_rank 與頂點投影逐條對賬；②對齊態縫數一字不差；
③用户那條存档的最終局面逐條對拍（含「原先被拒的兩條現在選得動」）；
④有界可達狀態空間上，引擎判定與獨立算的幾何判據零分歧（貫穿/兩側/側別）。
"""
import os
import sys
from collections import deque

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from game_mi import (  # noqa: E402
    GAP_DIRECTIONS, MiSliderMatrix, _make_block, gap_candidates, gap_rank,
    lattice_of, mi_vertices, side_of, span,
)
from gui.mi_view import MiBoardView  # noqa: E402

_failed = []
EPS = 1e-9
VIEW = MiBoardView(60.0)


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ''))
    if not cond:
        _failed.append(name)


def g_coord(fam, vertex):
    """頂點 (x, y) 在某族縫線座標下的值（幾何，未換引擎線號）。"""
    x, y = vertex
    if fam == 'h':
        return y
    if fam == 'v':
        return x
    return (y - x) if fam == 'd1' else (x + y)


def projection(fam, key):
    """一塊投影到該族座標上的真實區間：直接取三個頂點，不走捷徑表。"""
    fs = [g_coord(fam, v) for v in mi_vertices(*key)]
    return (min(fs), max(fs))


def geom_line(fam, line):
    """引擎 line → 幾何座標（h/v 的 L = g−1，d1 的 L = 2g，d2 的 L = 2(g−1)）。"""
    if fam in ('h', 'v'):
        return line + 1
    if fam == 'd1':
        return line / 2.0
    return line / 2.0 + 1.0


def exact_cut(cells, fam, line):
    """獨立算：線是否嚴格穿進某塊內部（從頂點/頂邊擦過不算切）。"""
    Y = geom_line(fam, line)
    return any(lo < Y < hi
               for lo, hi in (projection(fam, k) for k in cells))


def exact_two_sides(cells, fam, line):
    """獨立算：線兩側是否都至少有一塊（判據與 span 高端同源，單獨寫一份）。"""
    Y = geom_line(fam, line)
    above = any(projection(fam, k)[1] > Y for k in cells)
    below = any(projection(fam, k)[1] <= Y for k in cells)
    return above and below


def exact_verdict(cells, fam, line):
    """幾何判據：不切任何塊內部 + 兩側非空（is_valid_gap 該有的結果）。"""
    return not exact_cut(cells, fam, line) and exact_two_sides(cells, fam, line)


def make_game(cells):
    g = MiSliderMatrix(2, 2)
    g.blocks = [_make_block(r, c, q) for (r, c, q) in sorted(cells)]
    return g


def clickable(cells):
    """點得出的縫：由單位邊反推（與 GUI 選縫同一條徑，VIEW._edge_gap）。"""
    out = set()
    for (r, c, q) in cells:
        vs = mi_vertices(r, c, q)
        for i in range(3):
            p = VIEW.to_world(*vs[i])
            t = VIEW.to_world(*vs[(i + 1) % 3])
            gap = VIEW._edge_gap(p, t)
            if gap is not None:
                out.add(gap)
    return sorted(out)


# ============================================== ① 跨度/低位索引對賬
print("== ① span / gap_rank 與頂點投影對賬（h/v 兩族）==")
bad_span, bad_rank = [], []
keys = [(r, c, q) for r in range(3) for c in range(3) for q in 'NESW']
keys += [(r + 0.5, c + 0.5, q) for r in range(3) for c in range(3)
         for q in 'NESW']
for k in keys:
    for fam in ('h', 'v'):
        lo, hi = span(fam, k)
        want = projection(fam, k)
        if abs(lo - want[0] + 1) > EPS or abs(hi - want[1] + 1) > EPS:
            bad_span.append((fam, k, (lo, hi), want))
        # 不變式：跨度高端就是低位索引（側別判據 rank <= line 歸 0 側）
        if abs(gap_rank(fam, k) - hi) > EPS:
            bad_rank.append((fam, k, gap_rank(fam, k), hi))
check("h/v 的跨度 = 頂點投影區間 − 1（A/B 兩個晶格 × 四個朝向 × 2 族）",
      not bad_span, str(bad_span[:3]))
check("h/v 的 gap_rank = 跨度高端（span 與 side_of 用同一個區間）",
      not bad_rank, str(bad_rank[:3]))

# 四個朝向的跨度寬度：h 的 N/S 只有半格，v 的 W/E 只有半格，其餘整格
half, full = [], []
for q in 'NESW':
    for fam in ('h', 'v'):
        if span(fam, (0, 0, q))[1] - span(fam, (0, 0, q))[0] == 0.5:
            half.append((fam, q))
        else:
            full.append((fam, q))
check("半格跨度正是那四個朝向（h 的 N/S、v 的 W/E），其餘仍占滿整格",
      set(half) == {('h', 'N'), ('h', 'S'), ('v', 'W'), ('v', 'E')}
      and set(full) == {('h', 'E'), ('h', 'W'), ('v', 'N'), ('v', 'S')},
      f"半格 {sorted(half)}／整格 {sorted(full)}")

# ============================================== ② 對齊態一條都不變
print("== ② 對齊態的縫數不受影響 ==")
g = MiSliderMatrix(6, 6)
counts = {fam: len([1 for (t, _l) in g.all_gaps() if t == fam])
          for fam in ('h', 'v', 'd1', 'd2')}
check("6×6 滿盤縫數仍是規劃的 {'h': 5, 'v': 5, 'd1': 11, 'd2': 11}",
      counts == {'h': 5, 'v': 5, 'd1': 11, 'd2': 11}, str(counts))
for m, n in ((1, 1), (2, 2), (3, 5), (6, 1)):
    g = MiSliderMatrix(m, n)
    cells = g.positions()
    want = sorted((fam, l) for fam in ('h', 'v')
                  for l in gap_candidates(fam, cells)
                  if exact_verdict(cells, fam, l))
    got = sorted((t, l) for (t, l) in g.all_gaps() if t in ('h', 'v'))
    check(f"{m}×{n} 滿盤橫豎縫與頂點投影判據逐條一致（{len(got)} 條）",
          want == got, f"幾何 {want} vs 引擎 {got}")


# ============================================== ③ 用户存档的最終局面
print("== ③ 用户存档 mi-1-2-2 的最終局面逐條對拍 ==")
# config/temp_history.json 裡那條 mi-1-2-2（2×2 等級1，10 步）的最終矩陣，
# 8-bit 格式：每格兩個十六進位字元，前 A 晶格 nibble、後 B 晶格 nibble
MATRIX = [[112, 226, 0], [177, 208, 4], [0, 8, 0]]
MAP = 'mi8\n' + '\n'.join(''.join(f'{v:02x}' for v in row) for row in MATRIX)
g = MiSliderMatrix(2, 2)
check("矩陣能導入", g.import_map(MAP))
check("導出後與原矩陣一字不差（確是這條存档的終局）", g.export_map() == MAP)
cells = set(g.positions())
check("終局 16 塊、且是錯位態（A/B 兩個晶格混著）",
      len(cells) == 16 and any(lattice_of(k) for k in cells)
      and not all(lattice_of(k) for k in cells),
      f"實得 {len(cells)} 塊、B 晶格 {sum(1 for k in cells if lattice_of(k))} 塊")

# 點得出的橫豎縫：引擎判定必須與獨立算的幾何判據逐條一致
gaps = [x for x in clickable(cells) if x[0] in ('h', 'v')]
agree = [x for x in gaps
         if g.is_valid_gap(*x) == exact_verdict(cells, *x)]
check(f"點得出的橫豎縫 {len(gaps)} 條，引擎與幾何判據逐條一致",
      len(agree) == len(gaps),
      str([x for x in gaps if g.is_valid_gap(*x) != exact_verdict(cells, *x)]))

# 被拒絕的提示（GUI._mi_locked_seam）也必須與幾何判據同源：真的切在塊裡
# 才提示；另一種「點得到但不合法」是外沿縫（兩側有一側沒塊），那種不動聲色
from game_mi import span as _span  # noqa: E402
locked = [x for x in gaps if not g.is_valid_gap(*x)
          and any(lo < x[1] < hi
                  for (lo, hi) in (_span(x[0], k) for k in cells))]
truly_cut = [x for x in gaps if exact_cut(cells, *x)]
check("提示「選不動」的縫 = 精確判據下眞正切在塊裡的縫（不再有冤拒）",
      sorted(locked) == sorted(truly_cut),
      f"提示 {sorted(locked)} vs 精確 {sorted(truly_cut)}")
check("外沿縫（兩側有一側沒塊）不彈提示，只是選不中",
      all(not exact_two_sides(cells, *x)
          for x in gaps if not g.is_valid_gap(*x) and x not in locked),
      str([x for x in gaps if not g.is_valid_gap(*x) and x not in locked]))

# 用户報的那兩條：h line=1、v line=1（幾何 y=2 / x=2，錯位態的整數縫）
for fam, line in (('h', 1), ('v', 1)):
    Y = geom_line(fam, line)
    sides = {s: sorted(k for k in cells if side_of(fam, line, k) == s)
             for s in (0, 1)}
    geo_sides = {s: sorted(k for k in cells
                           if (0 if projection(fam, k)[1] <= Y + EPS else 1) == s)
                 for s in (0, 1)}
    check(f"{fam} line={line} 現在選得動（原先被拒）+ 兩側都非空",
          g.is_valid_gap(fam, line) and len(sides[0]) and len(sides[1]),
          f"兩側 {len(sides[0])}/{len(sides[1])} 塊")
    check(f"{fam} line={line} 的側別與幾何判據一致",
          sides[0] == geo_sides[0] and sides[1] == geo_sides[1],
          f"引擎 0 側 {len(sides[0])} 塊 vs 幾何 0 側 {len(geo_sides[0])} 塊")

# 對角色沒動：終局的對角縫數與修復前一致
diag = {fam: sorted(l for (t, l) in g.all_gaps() if t == fam)
        for fam in ('d1', 'd2')}
check("對角族縫數不變（d1 3 條、d2 5 條）",
      diag == {'d1': [-2, 0, 2], 'd2': [0, 2, 4, 6, 8]}, str(diag))


# ============================================== ④ 有界可達空間對拍
print("== ④ 可達狀態空間上引擎與幾何判據零分歧 ==")


def reachable(limit):
    start = frozenset((r, c, q) for r in range(2) for c in range(2)
                      for q in 'NESW')
    seen = {start}
    queue = deque([start])
    while queue and len(seen) < limit:
        cur = queue.popleft()
        game = make_game(cur)
        for gap in game.all_gaps():
            gtype, line = gap
            for d in GAP_DIRECTIONS[gtype]:
                for side in (0, 1):
                    ref = next((k for k in sorted(cur)
                                if side_of(gtype, line, k) == side), None)
                    if ref is None:
                        continue
                    g2 = make_game(cur)
                    g2.opt(gtype, line, g2.block_at(ref))
                    moved = {tuple(b.location) for b in g2.blocks if b.be_opted}
                    if not moved:
                        continue
                    pos, _reason = g2.try_move_ex(d, 1)
                    if not pos:
                        continue
                    nxt = frozenset((cur - moved) | {tuple(p) for p in pos})
                    if nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)
    return seen


STATES = reachable(3000)
n_seam = n_over = n_under = n_side = 0
for st in STATES:
    game = make_game(st)
    for gap in clickable(st):
        fam, line = gap
        n_seam += 1
        eng = game.is_valid_gap(fam, line)
        want = exact_verdict(st, fam, line)
        if eng and not want:
            n_under += 1
        if want and not eng:
            n_over += 1
        if eng:
            Y = geom_line(fam, line)
            for k in st:
                if (0 if projection(fam, k)[1] <= Y else 1) != \
                        side_of(fam, line, k):
                    n_side += 1
check(f"{len(STATES)} 個可達狀態 × 點得出的縫 {n_seam} 條：零冤拒/零錯放/零側別錯",
      n_over == 0 and n_under == 0 and n_side == 0,
      f"冤拒 {n_over}、錯放 {n_under}、側別錯 {n_side}")

print()
if _failed:
    print(f"未通過 {len(_failed)} 項：")
    for name in _failed:
        print('  - ' + name)
    sys.exit(1)
print("ALL PASS")
