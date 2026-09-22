# -*- coding: utf-8 -*-
"""無頭測試：米字格滑動核心（Stage M2；H1 改成斜向一格後全面改寫）。

覆蓋：四族縫隙的 rank/side_of、候選 line（端點 + 空帶中點）、
opt 選組（含跨晶格分組）、try_move_ex / commit_move 八向、
錯位態縫隙枚舉（與 H0 的幾何參考逐條對照）、幾何碰撞判據、
compute_score / shuffle、8-bit 矩陣、export_map / import_map 往返、
存檔快照往返。
"""
import os
import sys
import random

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

import game_mi  # noqa: E402
from game_mi import (  # noqa: E402
    DIRECTIONS, GAP_DIRECTIONS, MiSliderMatrix, gap_for_direction,
    gap_candidates, gap_rank, hull_area_units, lattice_of, mi_key,
    neighbors, side_of, span,
)
from history import GameHistory  # noqa: E402

_failed = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ''))
    if not cond:
        _failed.append(name)


def opt_count(g):
    return sum(1 for b in g.blocks if b.be_opted)


# ================================================================ 縫隙表
print("=== 四族縫隙的 rank / side_of ===")
g = MiSliderMatrix(4, 5)
cells = g.positions()
check("初始 4×5 = 80 塊", len(cells) == 80, f"實得 {len(cells)}")

# 完備性：每條**有效**縫都把全部滑塊劃進兩側（無遺漏無重疊）；
# 候選線裡一定混著無效線（端點但兩側有一側空的、空帶中點），那些由
# is_valid_gap 複核掉，side_of 對它們本來就沒有意義
bad_sides, bad_valid = [], []
for fam in ('h', 'v', 'd1', 'd2'):
    cands = gap_candidates(fam, cells)
    valid = [l for l in cands if g.is_valid_gap(fam, l)]
    check(f"{fam} 族候選線非空（有效 {len(valid)} / 候選 {len(cands)}）",
          len(cands) > 0 and len(valid) > 0)
    for line in valid:
        sides = [side_of(fam, line, c) for c in cells]
        if set(sides) != {0, 1}:
            bad_sides.append((fam, line))
        # 有效縫的判據自己也要認這條線（兩邊最多只差一個端點）
        if not g.is_valid_gap(fam, line):
            bad_valid.append((fam, line))
check("有效縫的 side_of 劃分完備（兩側非空、無遺漏無重疊）",
      not bad_sides, str(bad_sides[:3]))
check("候選線複核結果自洽", not bad_valid, str(bad_valid[:3]))

# 候選線必須由跨度端點導出：對齊態的 d1/d2 端點都是偶數整數，
# 而空帶中點會填進奇數——缺了半條對角鏈時奇數就是合法縫（見本檔末節）
full = MiSliderMatrix(6, 6).positions()
check("滿盤 d1 候選線含奇數（空帶中點），但沒有一條合法",
      any(l % 2 for l in gap_candidates('d1', full))
      and not any(l % 2 for t, l in MiSliderMatrix(6, 6).all_gaps()
                  if t == 'd1'))
check("滿盤上候選線經過複核後一條不多（32 條）",
      len(MiSliderMatrix(6, 6).all_gaps()) == 32,
      f"實得 {len(MiSliderMatrix(6, 6).all_gaps())}")

# 同格四塊的取向分界：d1 分 {N,E}｜{S,W}，d2 分 {N,W}｜{E,S}
r, c = 2, 3
d1_sides = {q: side_of('d1', 2 * (r - c), (r, c, q)) for q in 'NESW'}
check("d1 同格分居兩側（N,E | S,W）",
      d1_sides['N'] == d1_sides['E'] != d1_sides['S'] == d1_sides['W'],
      f"{d1_sides}")
d2_sides = {q: side_of('d2', 2 * (r + c), (r, c, q)) for q in 'NESW'}
check("d2 同格分居兩側（N,W | E,S）",
      d2_sides['N'] == d2_sides['W'] != d2_sides['E'] == d2_sides['S'],
      f"{d2_sides}")

# 一條對角線鏈上 k 相同的格取同一基值 → 一條鏈是完整的一條縫
chain = {(r, c, 'N'), (r + 1, c + 1, 'N'), (r - 1, c - 1, 'E')}
ranks = {gap_rank('d1', k) for k in chain}
check("同一條 d1 鏈的 rank 相同（{N,E} 側）", len(ranks) == 1, f"{ranks}")

# 未知族
try:
    gap_rank('zz', (0, 0, 'N'))
    check("未知縫隙族拋錯", False)
except ValueError:
    check("未知縫隙族拋錯", True)

# ================================================================ 方向表
print("=== 方向 → 縫隙族 ===")
check("8 個方向", len(DIRECTIONS) == 8, f"{sorted(DIRECTIONS)}")
dir_gap = {d: gap_for_direction(d) for d in DIRECTIONS}
check("h 族 → a/d", [d for d, g_ in dir_gap.items() if g_ == 'h'] == ['a', 'd']
      or set(d for d, g_ in dir_gap.items() if g_ == 'h') == {'a', 'd'})
check("v 族 → w/s", set(d for d, g_ in dir_gap.items() if g_ == 'v') == {'w', 's'})
check("d1 族 → q/x", set(d for d, g_ in dir_gap.items() if g_ == 'd1') == {'q', 'x'})
check("d2 族 → e/z", set(d for d, g_ in dir_gap.items() if g_ == 'd2') == {'e', 'z'})
check("GAP_DIRECTIONS 覆蓋全部 8 向",
      sorted(d for ds in GAP_DIRECTIONS.values() for d in ds) == sorted(DIRECTIONS))

# ================================================================ opt
print("=== opt 選組 ===")
g = MiSliderMatrix(4, 5)
check("初始無選中", opt_count(g) == 0)

b00 = g.block_at((1, 1, 'N'))
g.opt('h', 1, b00)
sel = {mi_key(b) for b in g.blocks if b.be_opted}
check("opt 選中非空且非全部", 0 < len(sel) < len(g.blocks), f"{len(sel)} 塊")
check("opt 選中集都在縫的同一側", all(r <= 1 for r, _c, _q in sel))
check("opt 選中集單一連通", MiSliderMatrix.is_single_connected(sel))

b_hi = next(b for b in g.blocks
            if side_of('h', 1, mi_key(b)) == 1)
g.opt('h', 1, b_hi)
sel_hi = {mi_key(b) for b in g.blocks if b.be_opted}
check("同一條縫、另一側選出互補集合",
      sel_hi and not (sel & sel_hi) and (sel | sel_hi) == g.positions())

for fam in ('v', 'd1', 'd2'):
    line = next(l for l in gap_candidates(fam, g.positions())
                if g.is_valid_gap(fam, l))
    g.opt(fam, line, g.block_at((1, 1, 'N')))
    s = {mi_key(b) for b in g.blocks if b.be_opted}
    check(f"{fam} 縫也能選出互補兩側", 0 < len(s) < len(g.blocks),
          f"{len(s)} 塊")
    # 取「另一側」的參考塊（(1,1,'N') 所在側是 side，另一側是 1-side）
    side = side_of(fam, line, (1, 1, 'N'))
    other = {mi_key(b) for b in g.blocks
             if side_of(fam, line, mi_key(b)) != side}
    g.opt(fam, line, g.block_at(sorted(other)[0]) if other else b00)
    s2 = {mi_key(b) for b in g.blocks if b.be_opted}
    check(f"{fam} 縫兩側互補", not (s & s2) and (s | s2) == g.positions())

# 未知縫隙族 → 全部取消
g.opt('zz', 1, b00)
check("未知縫隙族清空選中", opt_count(g) == 0)
# 不在棋盤上的塊 / None → 全部取消（呼叫方傳錯參考塊不應炸）
g.opt('h', 1, None)
check("None 參考塊清空選中", opt_count(g) == 0)

# ================================================================ 移動
print("=== try_move_ex / commit_move ===")
g = MiSliderMatrix(6, 6)
g.opt('h', 2, g.block_at((0, 0, 'N')))
pos, reason = g.try_move_ex('d', 2)
check("h 縫 + d 方向可移動", bool(pos) and reason == '', f"reason={reason}")
check("回傳位置數 = 選中數", len(pos) == opt_count(g))
check("回傳位置是 3 元素且 q 不變",
      all(len(p) == 3 for p in pos)
      and {p[2] for p in pos} <= {'N', 'E', 'S', 'W'})
orig_sel = sorted(mi_key(b) for b in g.blocks if b.be_opted)
g.commit_move(pos)
check("commit_move 後位置生效",
      sorted(mi_key(b) for b in g.blocks if b.be_opted) == sorted(tuple(p) for p in pos))
moved_keys = [mi_key(b) for b in g.blocks if b.be_opted]
# 'h' 縫 line=2 的 0 側 = 前三行 = 18 格 × 4 塊 = 72 塊；右移 2 格後每格
# 仍恰 4 塊、q 不變，且整組平移（原集合 +2 列就是新集合）
old_cells = {(r, c) for r, c, _q in orig_sel}
new_cells = {(r, c) for r, c, _q in moved_keys}
check("commit_move 後整組右移 2 格",
      new_cells == {(r, c + 2) for r, c in old_cells},
      f"{len(old_cells)} 格 → {len(new_cells)} 格")
check("commit_move 後 q 不變",
      {q for _r, _c, q in moved_keys} == {q for _r, _c, q in orig_sel})
check("commit_move 後每格仍 4 塊", 4 * len(new_cells) == len(moved_keys))
check("commit_move 後不再重疊（位置數=塊數）",
      len(g.positions()) == len(g.blocks))
check("commit_move 後棋盤不再是複原態（上半邊右移）", not g.is_solved())
check("commit_move 後仍連通", g.is_single_connected(g.positions()))

# 不平行方向必須被拒（v/d1/d2 方向對 h 縫）
for d in ('w', 's', 'q', 'e', 'z', 'x'):
    g.opt('h', 2, g.block_at((0, 0, 'N')))
    p, why = g.try_move_ex(d, 1)
    ok = (not p) and why == 'no_selection'
    if not ok:
        # game 層只認「有沒有選中」，方向必須由呼叫方按 GAP_DIRECTIONS 校驗
        check(f"{d} 不平行於 h 縫時不自行開綠燈", False, f"pos={p}")
check("非 DIRECTIONS 方向回 no_selection",
      g.try_move_ex('y', 1) == ([], 'no_selection'))
g._clear_selection()
check("無選中時回 no_selection", g.try_move_ex('d', 1) == ([], 'no_selection'))

# 逐步驗證：步數超過可達距離要失敗而不是跳出
g = MiSliderMatrix(4, 4)
g.opt('h', 1, g.block_at((0, 0, 'N')))
far, why = g.try_move_ex('a', 99)
check("撞邊界回 collision/disconnected", (not far) and why != '', f"reason={why}")

# 8 個方向都能在已打亂的局面裡合法走動（隨機 200 步不死）
random.seed(7)
g = MiSliderMatrix(6, 6)
g.shuffle(60, 2, bias=2.0, min_score=0.6)
moved_dirs = set()
stuck = 0
for _ in range(300):
    fams = g.all_gaps()
    if not fams:
        break
    fam, line = random.choice(fams)
    d = random.choice(GAP_DIRECTIONS[fam])
    side = random.choice([0, 1])
    cand = [k for k in g.positions() if side_of(fam, line, k) == side]
    if not cand:
        continue
    g.opt(fam, line, g.block_at(sorted(cand)[0]))
    p, why = g.try_move_ex(d, 1)
    if p:
        g.commit_move(p)
        moved_dirs.add(d)
    else:
        stuck += 1
check("8 個方向都走得動", len(moved_dirs) == 8, f"實得 {sorted(moved_dirs)}")
check("隨機 300 步後仍是連通局面", g.is_single_connected(g.positions()))
check("隨機移動不丟塊", len(g.blocks) == 144)

# ================================================================ 計分與打亂
print("=== compute_score / shuffle ===")
g = MiSliderMatrix(6, 6)
check("複原態 score = 1", abs(g.compute_score() - 1.0) < 1e-12,
      f"實得 {g.compute_score()}")
check("複原態散度 = 0", abs(g._scatter()) < 1e-12)
check("hull_area_units(實心 6×6) = 144", hull_area_units(g.positions()) == 144,
      f"實得 {hull_area_units(g.positions())}")
g.shuffle(80, 2, bias=3.0, min_score=0.5)
check("打亂後不是複原態", not g.is_solved())
check("打亂後分數低於 0.5（min_score 生效）", g.compute_score() <= 0.5 + 1e-9,
      f"實得 {g.compute_score():.4f}")
check("打亂後仍連通", g.is_single_connected(g.positions()))
check("打亂後塊數不變", len(g.blocks) == 144)
check("打亂後仍是米字密鋪（q 合法）",
      all(b.location[2] in ('N', 'E', 'S', 'W') for b in g.blocks))
# 只齊 4 塊的格子不存在問題；但不可出現單格 5 塊（密鋪不可能，純防呆）
counts = {}
for k in g.positions():
    counts[(k[0], k[1])] = counts.get((k[0], k[1]), 0) + 1
check("沒有格子超過 4 塊", all(v <= 4 for v in counts.values()))

# 打亂可回歸複原態嗎？給一個保守下界：打亂後一定還能整體合攏（momentum 反向）
g2 = MiSliderMatrix(4, 4)
g2.shuffle(30, 1)
check("等級1 打亂後不是複原態", not g2.is_solved())
check("等級1 打亂後分數在 (0,1]", 0 < g2.compute_score() <= 1.0)

# ================================================================ 地圖編碼
print("=== export_map / import_map ===")
g = MiSliderMatrix(3, 4)
m = g.export_map()
check("導出 3 行", len(m.split('\n')) == 3)
check("每行 4 字元", all(len(line) == 4 for line in m.split('\n')))
check("複原態全是 'f'（四塊俱全）", set(m) == {'f', '\n'})
check("導入 'f' 滿格可直接判勝",
      MiSliderMatrix.import_map(g, m) and g.is_solved())

g = MiSliderMatrix(3, 4)
# 抽掉 N 塊 → 該格 4-bit = 14 → 'e'
g.blocks = [b for b in g.blocks if mi_key(b) != (0, 0, 'N')]
g.update_matrix()
m = g.export_map()
check("缺 N 塊的字元是 'e'（N=1 被清掉）", m.split('\n')[0][0] == 'e',
      f"實得 {m.split(chr(10))[0]}")
check("缺一塊後不是複原態", not g.is_solved())
# 手寫地圖的別名仍接受：'#'=四塊、'n'=僅 N、'_'=空
g = MiSliderMatrix(3, 3)
check("別名 '#'/'n'/'_' 導入成功",
      g.import_map("###\n#n#\n___"))
check("別名導入的塊數 = 21（'###' 12 + '#n#' 9 + '___' 0）",
      len(g.blocks) == 21, f"實得 {len(g.blocks)}")
check("別名 'n' = 該格僅有 N 一塊",
      [mi_key(b) for b in g.blocks if b.location[:2] == [1, 1]] == [(1, 1, 'N')])
check("別名 '_' = 空格（該格一塊都沒有）",
      not any(b.location[:2] == [2, 2] for b in g.blocks))
check("非法字元被拒", not g.import_map("zzz"))
check("不等寬被拒", not g.import_map("fff\nff"))

# 往返：打亂局面 → 導出 → 導入 → 平移歸一後的形狀一致
# （矩陣的行號列號就是 0 起的座標，導入等價於把棋盤搬回原點——
#   與方形/三角形的 import_map 同一個約定，見 game.py import_map）
random.seed(11)
g = MiSliderMatrix(5, 6)
g.shuffle(70, 2, bias=2.0, min_score=0.55)
before = g.positions()
m = g.export_map()
g2 = MiSliderMatrix(5, 6)
check("導入成功", g2.import_map(m))


def _normalize(keys):
    r0 = min(r for r, _c, _q in keys)
    c0 = min(c for _r, c, _q in keys)
    return {(r - r0, c - c0, q) for r, c, q in keys}


check("導入後形狀一致（平移歸一）", _normalize(g2.positions()) == _normalize(before))
check("導入後塊數一致", len(g2.blocks) == len(g.blocks))
check("導入後分數一致", abs(g2.compute_score() - g.compute_score()) < 1e-12)
b1, b2 = g.get_boundaries(), g2.get_boundaries()
check("導入後邊界尺寸一致",
      (b1['max_row'] - b1['min_row'], b1['max_col'] - b1['min_col'])
      == (b2['max_row'] - b2['min_row'], b2['max_col'] - b2['min_col']))
check("導入後邊界從原點起", b2['min_row'] == 0 and b2['min_col'] == 0,
      f"{b2}")

# 空格的導入
g3 = MiSliderMatrix(3, 3)
ok = g3.import_map("___\n_n_\n___")
check("全 '_' 之外的合法導入成功", ok)
check("導入的塊數 = 1", len(g3.blocks) == 1 and mi_key(g3.blocks[0]) == (1, 1, 'N'))
check("導入單塊後不是複原態", not g3.is_solved())
check("導入單塊後仍連通", g3.is_single_connected(g3.positions()))
check("導入單塊後分數 = 1（凸包恰 1 塊，封頂 1.0）",
      abs(g3.compute_score()
          - min(1.0, 36.0 / hull_area_units(g3.positions()))) < 1e-12,
      f"實得 {g3.compute_score()}")
check("空導入被拒", not g3.import_map("\n\n"))
check("不等寬導入被拒", not g3.import_map("###\n#"))

# ================================================================ 錯位態
# 斜向一格（H1）的直接後果：位置出現兩種晶格（A 整數 / B 半整數）。
# 下面五節都用「真的走一次斜向一格」造出錯位態，再逐項斷言。
print("=== 錯位態：一次斜向一格之後 ===")
EPS = 1e-9


def _g_of(fam, vertex):
    """頂點 (x, y) 在某族縫線座標下的值（與引擎的 span 無關，獨立幾何）。"""
    x, y = vertex
    if fam == 'h':
        return y
    if fam == 'v':
        return x
    if fam == 'd1':
        return y - x
    return x + y


def _engine_of_g(fam, g):
    """幾何縫線座標 g → 引擎 line（h/v: L=g−1；d1: L=2g；d2: L=2(g−1)）。"""
    if fam in ('h', 'v'):
        return g - 1.0
    if fam == 'd1':
        return 2.0 * g
    return 2.0 * (g - 1.0)


def geom_seams(cells, fam):
    """有效縫線（幾何座標 g，0.5 步進）——不經過引擎的 span/side_of。

    一塊被這條線切開 ⇔ g 嚴格落在它三個頂點的 g 值之間；沒被切的塊整體
    在某一側（三個頂點全 ≤ g 或全 ≥ g）。縫合法 ⇔ 沒有塊被切，且兩側
    都至少有一塊。這是規劃 §1.3 判據的幾何原文，用來複核 all_gaps()。
    """
    vals = {k: [_g_of(fam, v) for v in game_mi.mi_vertices(*k)] for k in cells}
    lo = min(min(v) for v in vals.values())
    hi = max(max(v) for v in vals.values())
    out, x = [], lo + 0.5
    while x < hi - EPS:
        if not any(min(v) < x < max(v) for v in vals.values()):
            below = any(all(t <= x + EPS for t in v) for v in vals.values())
            above = any(all(t >= x - EPS for t in v) for v in vals.values())
            if below and above:
                out.append(round(x, 3))
        x += 0.5
    return out


# (說明, m, n, 族, 引擎 line, 方向, 期望的晶格數)
# 走法全部平行於所選的縫（規劃 §1.3 表）；v line=2 走 z 是唯一一條
# **不**平行於縫的，引擎現在會用幾何判據把它擋下（§1.5），單列一行。
SCENARIOS = [
    ('6×6 沿 d1 line=6 走 x', 6, 6, 'd1', 6, 'x', 2),
    ('6×6 沿 v line=2 走 z（不平行於縫）', 6, 6, 'v', 2, 'z', None),
    ('6×1 沿 d2 line=6 走 e', 6, 1, 'd2', 6, 'e', 2),
    ('1×6 沿 d1 line=0 走 x', 1, 6, 'd1', 0, 'x', 2),
    ('4×4 沿 d2 line=4 走 e', 4, 4, 'd2', 4, 'e', 2),
    ('4×4 沿 d1 line=2 走 x', 4, 4, 'd1', 2, 'x', 2),
    ('4×4 沿 d1 line=0 走 x（對角中線一分為二）', 4, 4, 'd1', 0, 'x', 2),
    ('4×4 沿 d1 line=0 走 q（同一個退化局面，反方向）', 4, 4, 'd1', 0, 'q', 2),
    ('2×2 沿 d1 line=0 走 x（最小退化局面）', 2, 2, 'd1', 0, 'x', 2),
    ('4×4 沿 h line=1 走 a', 4, 4, 'h', 1, 'a', 1),
]
for (label, m, n, fam, line, d, want_lat) in SCENARIOS:
    g = MiSliderMatrix(m, n)
    ref = g.block_at(sorted(k for k in g.positions()
                            if side_of(fam, line, k) == 1)[0])
    g.opt(fam, line, ref)
    pos, reason = g.try_move_ex(d, 1)
    if want_lat is None:
        # 不平行於縫的走法：輪到它把同側分量推出重疊，幾何判據要認出來
        check(f"{label}：引擎擋下（{reason}）", not pos and reason == 'collision')
        continue
    if not pos:
        check(f"{label}：移動成功", False, f"reason={reason}")
        continue
    g.commit_move(pos)
    lat = {lattice_of(k) for k in g.positions()}
    check(f"{label}：移動成功", True)
    check(f"{label}：晶格數 = {want_lat}（斜向換晶格、橫豎不換）",
          len(lat) == want_lat, f"實得 {sorted(lat)}")
    mism = []
    for fam2 in ('h', 'v', 'd1', 'd2'):
        want = sorted(_engine_of_g(fam2, x) for x in geom_seams(g.positions(), fam2))
        got = sorted(l for (t, l) in g.all_gaps() if t == fam2)
        if [float(x) for x in want] != [float(x) for x in got]:
            mism.append((fam2, want, got))
    check(f"{label}：錯位態四族縫隙與幾何參考逐條一致", not mism, str(mism[:2]))

# 規劃 §1.3 表的兩個代表數字（引擎 line = 幾何 g − 1）：
# 6×6 沿 d1 line=6 走 x 之後 h 只剩 [0,1,2]、v 只剩 [3,4]
g = MiSliderMatrix(6, 6)
ref = g.block_at(sorted(k for k in g.positions() if side_of('d1', 6, k) == 1)[0])
g.opt('d1', 6, ref)
g.commit_move(g.try_move_ex('x', 1)[0])
check("6×6 d1 line=6 x：錯位後 h = [0,1,2]、v = [3,4]（規劃表 1 逐行斷言）",
      sorted(l for (t, l) in g.all_gaps() if t == 'h') == [0, 1, 2]
      and sorted(l for (t, l) in g.all_gaps() if t == 'v') == [3, 4],
      f"h={[l for (t, l) in g.all_gaps() if t == 'h']} "
      f"v={[l for (t, l) in g.all_gaps() if t == 'v']}")
# 沿著走的那族一條不少（跨度不變）
d1_after = [l for (t, l) in g.all_gaps() if t == 'd1']
check("沿走族 d1 一條不少（11 條，與錯位前相同）", len(d1_after) == 11,
      f"{d1_after}")

# ---- 跨晶格 opt 分組：選中的一側同時含 A/B 兩套塊，且仍是單一連通分量
def _engine_g(fam, line):
    """引擎 line → 幾何縫線座標 g（_engine_of_g 的反函數）。"""
    if fam in ('h', 'v'):
        return line + 1.0
    if fam == 'd1':
        return line / 2.0
    return line / 2.0 + 1.0


def _geom_side(fam, line, key):
    """塊整體在縫的哪一側（幾何，獨立於 side_of）；縫切進塊內回 None。"""
    g = _engine_g(fam, line)
    vs = [_g_of(fam, v) for v in game_mi.mi_vertices(*key)]
    if all(v <= g + EPS for v in vs):
        return 0
    if all(v >= g - EPS for v in vs):
        return 1
    return None


g = MiSliderMatrix(6, 6)
ref = g.block_at(sorted(k for k in g.positions() if side_of('d1', 6, k) == 1)[0])
g.opt('d1', 6, ref)
g.commit_move(g.try_move_ex('x', 1)[0])
crossed = None
for (t, l) in g.all_gaps():
    blk = next((b for b in g.blocks if _geom_side(t, l, mi_key(b)) == 1), None)
    if blk is None:
        continue
    g.opt(t, l, blk)
    sel = {mi_key(b) for b in g.blocks if b.be_opted}
    if len({lattice_of(k) for k in sel}) == 2:
        crossed = (t, l, sel)
        break
check("錯位態存在跨晶格的選組（一側同時含 A/B 兩套塊）",
      crossed is not None,
      f"{crossed[0]} {crossed[1]} 共 {len(crossed[2])} 塊" if crossed else '')
if crossed:
    t, l, sel = crossed
    side = _geom_side(t, l, next(iter(sel)))
    same_side = {k for k in g.positions() if _geom_side(t, l, k) == side}
    check(f"跨晶格選組 = 這條縫的整個一側（{t} {l}，{len(sel)} 塊）",
          sel == same_side,
          f"缺 {sorted(same_side - sel)[:2]} 多 {sorted(sel - same_side)[:2]}")
    check("跨晶格選組單一連通（鄰接表缺了跨晶格鄰就會裂開）",
          MiSliderMatrix.is_single_connected(sel))

# ---- 整盤錯開半格也判勝（規劃 §3.2 決議）
g = MiSliderMatrix(3, 3)
m8 = 'mi8\n' + '\n'.join('0f' * 3 for _ in range(3))
check("mi8 導入：整盤 B 晶格實心矩形", g.import_map(m8))
check("  全是半整數座標", {lattice_of(mi_key(b)) for b in g.blocks} == {1})
check("  錯半格的矩形也判勝", g.is_solved())
check("  仍單一連通", g.is_single_connected(g.positions()))
check("  邊界是 0.5 起的矩形",
      g.get_boundaries() == {'min_row': 0.5, 'max_row': 2.5,
                             'min_col': 0.5, 'max_col': 2.5},
      f"{g.get_boundaries()}")
# 而且普通玩法走得到：一條斜縫的兩半朝同向各走一格 = 整體換一次晶格。
# 這裡直接搬到 B 晶格等價驗證：導出→導入→再導出，字串一致（8-bit 可逆）
out1 = g.export_map()
g2 = MiSliderMatrix(3, 3)
check("  錯位態導出/導入往返", g2.import_map(out1)
      and g2.export_map() == out1)

# ---- 8-bit 矩陣：同格兩套三角、floor 歸格
g = MiSliderMatrix(3, 3)
g.import_map('mi8\n' + '12' + 'ff' * 2 + '\n' + ('ff' * 3 + '\n') * 2)
check("同格 A 的 N + B 的 E → matrix[0][0] = 1|(2<<4) = 33",
      g.get_matrix()[0][0] == 33, f"實得 {g.get_matrix()[0][0]}")
check("  該格恰兩塊：A(0,0,'N') 與 B(0.5,0.5,'E')",
      sorted(mi_key(b) for b in g.blocks
             if b.location[:2] in ([0, 0], [0.5, 0.5]))
      == [(0, 0, 'N'), (0.5, 0.5, 'E')],
      f"{sorted(mi_key(b) for b in g.blocks)[:4]}")
g = MiSliderMatrix(2, 2)
g.import_map('mi8\n' + '\n'.join('0f' * 2 for _ in range(2)))
check("整格只有 B 晶格 → matrix = 0xF0 = 240", g.get_matrix() == [[240, 240]] * 2,
      f"實得 {g.get_matrix()}")
check("  矩陣邊界按 floor 歸格（半整數座標不炸）",
      g.matrix_bounds == {'min_row': 0, 'max_row': 1, 'min_col': 0, 'max_col': 1},
      f"{g.matrix_bounds}")

# ---- 存檔快照往返：save_snapshot 走 update_matrix（表 11 說它會炸）
g = MiSliderMatrix(4, 4)
ref = g.block_at(sorted(k for k in g.positions() if side_of('d1', 0, k) == 1)[0])
g.opt('d1', 0, ref)
g.commit_move(g.try_move_ex('x', 1)[0])
saved = sorted(mi_key(b) for b in g.blocks)
hist = GameHistory()
hist.save_snapshot(g)
hist.save_snapshot(g, move_info={'direction': 'x'})
# 再走一步，然後撤銷回第一次的快照
g.opt('d1', 2, g.blocks[0])
pos, reason = g.try_move_ex('q', 1)
if pos:
    g.commit_move(pos)
check("再走一步確實換了局面", sorted(mi_key(b) for b in g.blocks) != saved)
hist.restore_snapshot(g, 0)
check("快照還原後位置逐一相等（8-bit 解碼）",
      sorted(mi_key(b) for b in g.blocks) == saved,
      f"實得 {sorted(mi_key(b) for b in g.blocks)[:3]}")
check("快照還原後晶格混合保留下來",
      {lattice_of(mi_key(b)) for b in g.blocks} == {0, 1})
check("快照還原後仍連通、塊數不變",
      MiSliderMatrix.is_single_connected(g.positions())
      and len(g.blocks) == 64)

# ---- 三步夾具：前兩步乾淨，第三步是正面積重疊，引擎要擋下（§1.5）
# 夾具原本給 H0 參考實現用（那裡斷言「位置集合不相交」會放它過去）；
# 這裡改走真引擎，斷言幾何判據把它認出來。
FIXTURE = [('d2', 4.0, 'e'), ('h', 3.5, 'd'), ('d1', 6.0, 'x')]
g = MiSliderMatrix(6, 6)
notes = []
for i, (fam, line, d) in enumerate(FIXTURE, 1):
    ref = g.block_at(sorted(k for k in g.positions()
                            if side_of(fam, line, k) == 1)[0])
    g.opt(fam, line, ref)
    pos, reason = g.try_move_ex(d, 1)
    if not pos:
        notes.append((i, f'{fam} {line:g} {d}', reason))
        break
    g.commit_move(pos)
    notes.append((i, f'{fam} {line:g} {d}', 'ok'))
check("夾具前兩步合法、第三步被擋", [n[2] for n in notes] == ['ok', 'ok', 'collision'],
      str(notes))
# 第三步的候選位置：與靜止側一個 key 都不撞（舊判據會放行），但有正面積重疊
g = MiSliderMatrix(6, 6)
for fam, line, d in FIXTURE[:2]:
    ref = g.block_at(sorted(k for k in g.positions()
                            if side_of(fam, line, k) == 1)[0])
    g.opt(fam, line, ref)
    g.commit_move(g.try_move_ex(d, 1)[0])
ref = g.block_at(sorted(k for k in g.positions()
                        if side_of('d1', 6.0, k) == 1)[0])
g.opt('d1', 6.0, ref)
sel = {mi_key(b) for b in g.blocks if b.be_opted}
non = {mi_key(b) for b in g.blocks if not b.be_opted}
dr, dc = DIRECTIONS['x']
cand = {(k[0] + dr, k[1] + dc, k[2]) for k in sel}
check("第三步：選中組與靜止側一個 key 都不撞（舊判據的口徑）",
      not (cand & non), f"撞上 {sorted(cand & non)[:3]}")
bad = [(a, b) for a in cand for b in non
       if game_mi._tri_overlap(a, b)]
check("第三步：候選位置與靜止側有正面積重疊（幾何判據的依據）",
      bool(bad), f"實得 {bad[:2]}")
check("第三步：被擋的原因正是 collision",
      g.try_move_ex('x', 1)[1] == 'collision')

# ---- 缺了半條對角鏈：奇數 d1 線號成為合法縫（規劃 §1.3 末段）
g = MiSliderMatrix(4, 4)
# 去掉 r−c=1 的全部 S/W 與 r−c=2 的全部 N/E：兩條對角之間就空出
# 一條帶來，g=1.5（引擎 line 3）整條落在空帶裡
g.blocks = [b for b in g.blocks
            if not ((b.location[0] - b.location[1] == 1
                     and b.location[2] in ('S', 'W'))
                    or (b.location[0] - b.location[1] == 2
                        and b.location[2] in ('N', 'E')))]
g.update_matrix()
odd = [l for (t, l) in g.all_gaps() if t == 'd1' and int(l) % 2]
check("缺半條對角鏈時，奇數 d1 線號出現且合法", odd == [3], f"實得 {odd}")
check("  只由端點生成候選就提不出這條線（空帶中點是必需的）",
      3 in gap_candidates('d1', g.positions())
      and 3 not in {span('d1', k)[0] for k in g.positions()}
      | {span('d1', k)[1] for k in g.positions()})
check("  滿盤上同一條線不合法（滿盤推進這個斷言才有意義）",
      not MiSliderMatrix(4, 4).is_valid_gap('d1', 3))

print()
if _failed:
    print(f"共 {len(_failed)} 項失敗:")
    for n in _failed:
        print("  -", n)
    sys.exit(1)
print("全部通過")
