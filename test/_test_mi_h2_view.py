# -*- coding: utf-8 -*-
"""米字格斜向「一格」H2：gui/mi_view.py 在錯位態的命中與背景（規劃 §2 表 13~16）。

表 13~16 說的是同一件事：斜向一格之後位置出現半整數座標，視圖層四處整數
假設隨之失效——

    表 13 `_edge_gap`     原先按 int(round(...)) 反推線號 → 半整數格邊被吞成
                          鄰近整數線，點到正確的邊卻給出錯的縫（而那條線多半切
                          在塊裡，引擎直接否掉 → 玩家「點了縫沒反應」）
    表 14 `world_to_cell` 只查落點所在整數格的 2×2 → B 晶格塊的 key 是半整數、
                          橫跨整數格邊，查不到它，錯位那一半全程點不中
    表 15 `grid_segments` 橫豎層級走整數區間 → 背景畫的是對齊態的格，與錯開
                          半格的塊對不齊
    表 16 `gap_line_distance` / `gap_segment` 原是 `level = line + 1` 的整數暗示
                          → 算式本來就是浮點的，半整數線號原樣成立，這裡把
                          「中點壓線、距離算式自洽」複核一遍

夾具是規劃 §1.3 表裡三行「斜向一格之後」的真實局面（都取 side 1 那一側，
與 test/_test_mi_core.py 同一約定）：6×6 沿 d1 line=6 走 x、6×1 沿 d2
line=6 走 e、4×4 沿 d2 line=4 走 e。三行分別只剩整數縫、整數與半整數混在、
只剩半整數縫，合起來把兩種線號都覆蓋到。

执行：python test/_test_mi_h2_view.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from game_mi import (MiSliderMatrix, lattice_of, mi_key,  # noqa: E402
                     mi_vertices, neighbors, side_of)

from gui.mi_view import MiBoardView, _half_round  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


view = MiBoardView(60.0, 4.0)


def shift(m, n, fam, line, direction):
    """沿一條縫把 side 1 滑 direction 一格；回傳 (game, reason)。"""
    g = MiSliderMatrix(m, n)
    ref = g.block_at(sorted(k for k in g.positions()
                            if side_of(fam, line, k) == 1)[0])
    g.opt(fam, line, ref)
    pos, reason = g.try_move_ex(direction, 1)
    if not pos:
        return g, reason
    g.commit_move(pos)
    return g, ''


# (說明, m, n, 族, 引擎 line, 方向) —— 規劃 §1.3 表的第 1/3/5 行
FIXTURES = [
    ('6×6 d1 line=6 走 x', 6, 6, 'd1', 6, 'x'),
    ('6×1 d2 line=6 走 e', 6, 1, 'd2', 6, 'e'),
    ('4×4 d2 line=4 走 e', 4, 4, 'd2', 4, 'e'),
]

STATES = []
for (label, m, n, fam, line, d) in FIXTURES:
    g, reason = shift(m, n, fam, line, d)
    if not check(f"夾具 {label}：斜向一格成功", not reason, reason):
        continue
    cells = g.positions()
    B = {k for k in cells if lattice_of(k)}
    if not check(f"夾具 {label}：出現 B 晶格塊（{len(B)}/{len(cells)}）", len(B) > 0):
        continue
    check(f"夾具 {label}：不变量 2r 與 2c 同奇偶",
          all(int(round(2 * k[0])) % 2 == int(round(2 * k[1])) % 2 for k in cells))
    STATES.append((label, g, cells, B))

check("三個錯位夾具都建好了", len(STATES) == 3)

# ---- 夾具的縫隙分佈：整數縫、混雜、只有半整數（規劃 §1.3 表逐行斷言）
gaps_by_label = {label: g.all_gaps() for (label, g, _c, _b) in STATES}


def _lines(label, fam):
    return sorted(l for (t, l) in gaps_by_label[label] if t == fam)


check("6×6：錯位後橫縫 = [0,1,2]、豎縫 = [3,4]（規劃表 1 的引擎線號）",
      _lines('6×6 d1 line=6 走 x', 'h') == [0, 1, 2]
      and _lines('6×6 d1 line=6 走 x', 'v') == [3, 4],
      f"h={_lines('6×6 d1 line=6 走 x', 'h')} "
      f"v={_lines('6×6 d1 line=6 走 x', 'v')}")
check("6×1：錯位後橫縫 = [0, 1, 3.5]（整數與半整數混在，規劃表 3）",
      _lines('6×1 d2 line=6 走 e', 'h') == [0, 1, 3.5],
      f"實得 {_lines('6×1 d2 line=6 走 e', 'h')}")
check("4×4：錯位後豎縫只剩半整數 [2.5]（規劃表 5）",
      _lines('4×4 d2 line=4 走 e', 'v') == [2.5],
      f"實得 {_lines('4×4 d2 line=4 走 e', 'v')}")
check("三個夾具合起來覆蓋了整數縫與半整數縫兩種線號",
      any(not float(l).is_integer() for _t, l in gaps_by_label[STATES[0][0]])
      or any(not float(l).is_integer() for _t, l in gaps_by_label[STATES[1][0]]))

# ================================================================ 表 14
print("== 表 14：world_to_cell 追加半偏移格 ==")
for (label, g, cells, B) in STATES:
    miss = [k for k in cells
            if view.world_to_cell(*view.incenter(*k), cells) != k]
    miss_b = [k for k in B
              if view.world_to_cell(*view.incenter(*k), cells) != k]
    check(f"{label}：{len(cells)} 塊內心全部命中自己（B 晶格 {len(B)} 塊在內）",
          not miss, f"漏 {miss[:3]}")
    check(f"{label}：B 晶格 {len(B)} 塊也全部命中自己", not miss_b,
          f"漏 {miss_b[:3]}")
    # 重心（玩家實際瞄的視覺中心）同理
    miss_c = [k for k in cells
              if view.world_to_cell(*view.to_world(
                  *(sum(p[i] for p in mi_vertices(*k)) / 3.0 for i in (0, 1))),
                  cells) != k]
    check(f"{label}：全部重心也命中自己", not miss_c, f"漏 {len(miss_c)} 塊")

p = view.to_world(1.0, 1.0)
check("交界格角返回某個存在的塊（不是 None）",
      view.world_to_cell(*p, STATES[0][2]) in STATES[0][2],
      f"實得 {view.world_to_cell(*p, STATES[0][2])}")
check("半偏移格在檢查清單裡（B 晶格塊的 key）",
      (0.5, 0.5) in view._hit_cells(*view.to_world(0.75, 0.75)))
check("整數 3×3 都在清單裡（棋形外沿差一個容差的點也要算到）",
      all((r, c) in view._hit_cells(*view.to_world(0.2, 0.2))
          for r in (-1, 0, 1) for c in (-1, 0, 1)))
check("清單 25 格各一次（不重複）",
      len(set(view._hit_cells(0.0, 0.0))) == 25)
check("棋形外沿往下 2px 仍看得到上面那格的邊（hittest 的裂縫全寬）",
      view.gap_at(*view.to_world(0.5, -2.0 / view.cell_size),
                  {(0, 0, q) for q in 'NESW'}) is not None)
check("錯位塊橫跨整數格邊：半偏移格的盒子蓋住落點",
      view.to_world(0.75, 0.75)[0] / 60.0 == 0.75
      and min(x for x, _y in mi_vertices(0.5, 0.5, 'N')) <= 0.75
      and max(x for x, _y in mi_vertices(0.5, 0.5, 'N')) >= 0.75)

# ================================================================ 表 13
print("== 表 13：_edge_gap 半整數線號 ==")
total_edges = half_edges = bad_edges = 0
first_bad = None
for (label, g, cells, B) in STATES:
    for a in cells:
        for b in neighbors(a):
            if b not in cells:
                continue
            common = set(view.piece_polygon(*a, inset=False)) \
                & set(view.piece_polygon(*b, inset=False))
            if len(common) != 2:
                continue
            p, t = sorted(common)
            want = view._edge_gap(p, t)
            if want is None:
                continue
            total_edges += 1
            if not float(want[1]).is_integer():
                half_edges += 1
            mid = ((p[0] + t[0]) / 2.0, (p[1] + t[1]) / 2.0)
            got = view.gap_at(*mid, cells)
            if got != want:
                bad_edges += 1
                if first_bad is None:
                    first_bad = (label, a, b, want, got)
check(f"三個夾具 {total_edges} 條共享邊的中點都命中所屬縫",
      bad_edges == 0, f"不符 {bad_edges} 條{first_bad or ''}")
check(f"其中 {half_edges} 條所屬縫在半整數線上", half_edges > 0)

check("半整數橫格邊 → 'h' 半整數線號",
      view._edge_gap(view.to_world(0, 1.5), view.to_world(1, 1.5)) == ('h', 0.5),
      f"實得 {view._edge_gap(view.to_world(0, 1.5), view.to_world(1, 1.5))}")
check("整數橫格邊仍是整數線號",
      view._edge_gap(view.to_world(0, 2.0), view.to_world(1, 2.0)) == ('h', 1))
check("半整數豎格邊 → 'v' 半整數線號",
      view._edge_gap(view.to_world(2.5, 0), view.to_world(2.5, 1)) == ('v', 1.5),
      f"實得 {view._edge_gap(view.to_world(2.5, 0), view.to_world(2.5, 1))}")
check("_half_round 取最近 ½ 倍數（吃浮點誤差、不吃半格、負數也對）",
      _half_round(0.4999999) == 0.5 and _half_round(-1.0) == -1
      and _half_round(2.74) == 2.5 and _half_round(0.0) == 0
      and _half_round(-0.26) == -0.5, f"實得 {_half_round(-0.26)}")

# ================================================================ 表 16
print("== 表 16：半整數 line 的距離算式與線段 ==")


def _sample(seg, t):
    return (seg[0][0] + (seg[1][0] - seg[0][0]) * t,
            seg[0][1] + (seg[1][1] - seg[0][1]) * t)


# 沿著縫線取 19 個採樣點。縫線穿過一串單位邊，單位邊的接縫正是格點，
# 格點上橫豎縫與對角縫等距相交——那裡按既定的「等距取長邊」裁定成橫豎縫
# （對齊態的斷言一樣：格角 → ('h', 0)），所以不能要求每個採樣點都回本縫，
# 只要求：① 至少一個採樣點回本縫（縫點得到）；② 每個採樣點要麼回本縫、
# 要麼回一條同樣壓在該點上、且引擎認帳的縫（沒有 round 造成的假縫）。
seg_total = seg_off = seg_none = seg_fake = seg_unreach = 0
for (label, g, cells, B) in STATES:
    hull = view.board_hull(cells)
    valid = set(g.all_gaps())
    for (fam, line) in sorted(valid):
        seg = view.gap_segment(fam, line, hull)
        if seg is None:
            check(f"{label} {fam} {line}：線段存在", False)
            continue
        seg_total += 1
        # 線上任意點到該縫的距離都是 0（level = line + 1 的換算對半整數成立）
        if any(view.gap_line_distance(fam, line, *_sample(seg, t)) > 1e-9
               for t in (0.1, 0.5, 0.9)):
            seg_off += 1
        hits = [t for t in (i / 20.0 for i in range(1, 20))
                if view.gap_at(*_sample(seg, t), cells) == (fam, line)]
        if not hits:
            seg_unreach += 1
        for t in (i / 20.0 for i in range(1, 20)):
            pt = _sample(seg, t)
            got = view.gap_at(*pt, cells)
            if got is None:
                seg_none += 1        # 線上可能有空檔（洞/階梯），無邊可點
                continue
            # 裁定本來就是「容差內最近的那條單位邊」：縫線延伸到沒有塊的地方
            # 時，最近的是別族的邊（相距 < 容差），這不是錯誤；只有當回覆的縫
            # 離點擊超過容差，才是把點歸到了八竿子打不著的線上
            if (view.gap_line_distance(got[0], got[1], *pt)
                    > max(3.0, view.cell_size / 12.0) + 1e-9):
                seg_fake += 1
                check(f"{label} {fam} {line}：點在縫上（t={t:.2f}）"
                      f"得到的 {got} 離點擊太遠", False, f"該點 {pt}")
check(f"{seg_total} 條縫的線段都壓在縫線上", seg_off == 0, f"偏離 {seg_off} 條")
check(f"{seg_total} 條縫都點得到（每條至少一個採樣點回本縫）",
      seg_unreach == 0, f"點不到 {seg_unreach} 條")
check(f"點在縫上只會得到容差內的縫（空檔/別族邊更近共 {seg_none} 處）",
      seg_fake == 0, f"離太遠 {seg_fake} 處")

# 半整數線的距離算式：沿垂直方向挪半格邊，距離就多半格邊
half_ok = True
for (label, g, cells, B) in STATES:
    hull = view.board_hull(cells)
    for (fam, line) in g.all_gaps():
        if float(line).is_integer():
            continue
        seg = view.gap_segment(fam, line, hull)
        if seg is None:
            continue
        mid = _sample(seg, 0.5)
        if fam == 'h':
            off = (mid[0], mid[1] + view.cell_size / 2.0)
        elif fam == 'v':
            off = (mid[0] + view.cell_size / 2.0, mid[1])
        else:
            continue
        if abs(view.gap_line_distance(fam, line, *off)
               - view.cell_size / 2.0) > 1e-9:
            half_ok = False
check("半整數縫：距離算式隨半格邊等比伸縮", half_ok)

# ================================================================ 表 15
print("== 表 15：背景層級由塊的邊導出 ==")


def _level_of(seg):
    """線段 → (族, 層級[格])。"""
    (x1, y1), (x2, y2) = seg
    if abs(y1 - y2) < 1e-9:
        return ('h', y1 / view.cell_size)
    if abs(x1 - x2) < 1e-9:
        return ('v', x1 / view.cell_size)
    if abs((y2 - y1) - (x2 - x1)) < 1e-9:
        return ('d1', (y1 - x1) / view.cell_size)
    return ('d2', (x1 + y1) / view.cell_size)


for (label, g, cells, B) in STATES:
    hull = view.board_hull(cells)
    segs = view.grid_segments(hull, cells)
    levels = [_level_of(s) for s in segs]
    h_seen = {lvl for fam, lvl in levels if fam == 'h'}
    v_seen = {lvl for fam, lvl in levels if fam == 'v'}
    want_h = {k[0] + d for k in cells for d in (0, 1)}
    want_v = {k[1] + d for k in cells for d in (0, 1)}
    check(f"{label}：橫邊層級 = 全部塊的上下沿（{len(want_h)} 層）",
          h_seen == want_h, f"實得 {sorted(h_seen)}")
    check(f"{label}：豎邊層級 = 全部塊的左右沿（{len(want_v)} 層）",
          v_seen == want_v, f"實得 {sorted(v_seen)}")
    # 對角族：兩晶格的 y−x、x+y 都恆整數；塊的每條半對角線都必須畫出來
    for fam, uv in (('d1', lambda x, y: y - x), ('d2', lambda x, y: x + y)):
        seen = [lvl for f, lvl in levels if f == fam]
        want = set()
        for k in cells:
            vs = mi_vertices(*k)
            for i in range(3):
                (x1, y1), (x2, y2) = vs[i], vs[(i + 1) % 3]
                if abs((y2 - y1) - (x2 - x1)) < 1e-9 and fam == 'd1':
                    want.add(uv(x1, y1))
                if abs((y2 - y1) + (x2 - x1)) < 1e-9 and fam == 'd2':
                    want.add(uv(x1, y1))
        span = [uv(p[0] / view.cell_size, p[1] / view.cell_size) for p in hull]
        full = set(range(int(math.floor(min(span))), int(math.ceil(max(span))) + 1))
        check(f"{label} {fam}：層級全整數、無重複、塊的半對角線一條不漏",
              all(float(v).is_integer() for v in seen)
              and len(set(seen)) == len(seen) and want <= set(seen),
              f"缺 {sorted(want - set(seen))[:4]}")
        # 兩端的極值層級可能只與凸包切在一個角點上（退化成一條「線段」的
        # 起點），chord 會回 None → 不畫；其餘層級必須一條不少
        missing = full - set(seen)
        check(f"{label} {fam}：除了切角的極值層級外鋪滿凸包區間",
              set(seen) <= full
              and missing <= {min(full), max(full)},
              f"實得 {len(set(seen))}/{len(full)} 條，缺 {sorted(missing)[:3]}")
    check(f"{label}：錯位態橫豎層級確實含半整數",
          any(not float(v).is_integer() for v in h_seen | v_seen))

# 對齊態：傳 positions 與舊的「只傳凸包」必須等價（renderer 改了也不能變畫面）
ga = MiSliderMatrix(4, 5)
ha = view.board_hull(ga.positions())
check("對齊態傳 positions 與只傳凸包結果一致",
      view.grid_segments(ha, ga.positions()) == view.grid_segments(ha),
      f"{len(view.grid_segments(ha, ga.positions()))} vs "
      f"{len(view.grid_segments(ha))} 條")
check("對齊態背景仍是整數層級（沒多出半格線）",
      all(float(lvl).is_integer()
          for fam, lvl in map(_level_of,
                              view.grid_segments(ha, ga.positions()))))
check("只傳凸包（舊行為）仍是整數區間",
      all(float(lvl).is_integer()
          for fam, lvl in map(_level_of, view.grid_segments(ha))))

print()
if _failures:
    print(f"共 {len(_failures)} 項失敗:")
    for n in _failures:
        print("  -", n)
    sys.exit(1)
print("全部通過")
