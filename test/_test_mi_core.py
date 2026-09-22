# -*- coding: utf-8 -*-
"""無頭測試：米字格滑動核心（Stage M2）。

覆蓋：四族縫隙的 rank/side_of 完備性、候選 line（含對角族只取偶數）、
opt 選組、try_move_ex / commit_move 8 向、compute_score / shuffle、
export_map / import_map 往返。
"""
import os
import sys
import random

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from game_mi import (  # noqa: E402
    DIRECTIONS, GAP_DIRECTIONS, MiSliderMatrix, gap_for_direction,
    gap_index_range, gap_rank, hull_area_units, mi_key, neighbors,
    side_of,
)

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

# 完備性：每族每條候選線兩側都非空，且兩側互補（無遺漏無重疊）
cover_ok = True
for fam in ('h', 'v', 'd1', 'd2'):
    lines = list(gap_index_range(fam, cells))
    check(f"{fam} 族有候選線", len(lines) > 0, f"共 {len(lines)} 條")
    if fam in ('d1', 'd2') and any(l % 2 for l in lines):
        cover_ok = False
    for line in lines:
        sides = [side_of(fam, line, c) for c in cells]
        if set(sides) != {0, 1}:
            cover_ok = False
        if len(lines) > 1 and not g.is_valid_gap(fam, line):
            # 範圍保證兩側非空，與 is_valid_gap 不一致就說明判據漂移
            cover_ok = False
check("四族候選線都把全部滑塊劃進兩側（完備）", cover_ok)

# 對角族只取偶數 line：奇數 line 對應的線從格心與邊中點之間穿過，會切開塊內部
check("d1 候選線全是偶數", all(l % 2 == 0 for l in gap_index_range('d1', cells)))
check("d2 候選線全是偶數", all(l % 2 == 0 for l in gap_index_range('d2', cells)))

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
    line = next(iter(gap_index_range(fam, g.positions())))
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

print()
if _failed:
    print(f"共 {len(_failed)} 項失敗:")
    for n in _failed:
        print("  -", n)
    sys.exit(1)
print("全部通過")
