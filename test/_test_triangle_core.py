# -*- coding: utf-8 -*-
"""無頭測試：三角形密鋪滑動核心（Stage B2a）。

覆蓋 opt / try_move_ex / commit_move / resolve_drag / shuffle，
以及「單次觸控拖動只需一個方向字母」的泛化性質。
"""
import os, sys, random
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from game_triangle import (
    TriangleSliderMatrix, DIRECTIONS, GAP_DIRECTIONS, gap_for_direction,
    finger_line, side_of,
)

_failed = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ''))
    if not cond:
        _failed.append(name)


def opt_count(g):
    return sum(1 for b in g.blocks if b.be_opted)


# ================================================================ opt
print("=== opt 選組 ===")
g = TriangleSliderMatrix(4)
check("初始無選中", opt_count(g) == 0)

# h 族縫隙 j=1：▲(0,0) 落在 j<=1 側
b00 = g.block_at((0, 0, True))
g.opt('h', 1, b00)
sel = {tuple(b.location) for b in g.blocks if b.be_opted}
check("opt 選中一塊所在側的全部連通塊", len(sel) > 0)
check("opt 選中集不含縫另一側", all(j <= 1 for _, j, _ in sel))
check("opt 選中集單一連通", TriangleSliderMatrix.is_single_connected(sel))
check("opt 未選全部（非整體平移）", len(sel) < len(g.blocks))

# 縫隙兩側都取得到：換一塊在另一側
b_hi = None
for b in g.blocks:
    if side_of('h', 1, tuple(b.location)) == 1:
        b_hi = b
        break
g.opt('h', 1, b_hi)
sel_hi = {tuple(b.location) for b in g.blocks if b.be_opted}
check("同一條縫、另一側的塊選出互補集合",
      sel_hi and not (sel & sel_hi) and (sel | sel_hi) == g.positions())

# 未知縫隙族 → 全部取消
g.opt('q', 1, b00)
check("未知縫隙族清空選中", opt_count(g) == 0)

# ================================================================ try_move_ex
print("=== try_move_ex / commit_move ===")
g = TriangleSliderMatrix(4)
g.opt('h', 1, g.block_at((0, 0, True)))
pos, reason = g.try_move_ex('d', 1)
check("h 縫 + d 方向可移動", bool(pos) and reason == '', f"reason={reason}")
check("回傳位置數=選中數", len(pos) == opt_count(g))
check("回傳位置是 3 元素", all(len(p) == 3 for p in pos))

before = {tuple(b.location) for b in g.blocks}
g.commit_move(pos)
after = {tuple(b.location) for b in g.blocks}
check("commit_move 後塊數不變", len(g.blocks) == len(before))
check("commit_move 改變了局面", before != after)
check("commit_move 後仍單一連通",
      TriangleSliderMatrix.is_single_connected(g.positions()))
check("commit_move 後仍是 k² 塊", len(g.blocks) == 16)

# 方向不屬於該縫隙族：合法但會碰撞/斷開（語義上仍由 try_move_ex 把關）
g2 = TriangleSliderMatrix(4)
g2.opt('h', 1, g2.block_at((0, 0, True)))
pos2, reason2 = g2.try_move_ex('e', 1)
check("h 縫配 e 方向被拒絕", not pos2 and reason2 in ('collision', 'disconnected'),
      f"reason={reason2}")

# 無選中
g3 = TriangleSliderMatrix(4)
pos3, reason3 = g3.try_move_ex('d', 1)
check("無選中回 no_selection", not pos3 and reason3 == 'no_selection')

# 未識別方向
g4 = TriangleSliderMatrix(4)
g4.opt('h', 1, g4.block_at((0, 0, True)))
pos4, reason4 = g4.try_move_ex('k', 1)
check("未知方向回 no_selection", not pos4 and reason4 == 'no_selection')

# ================================================================ 六向都不破壞密鋪/連通
print("=== 六向滑動保持密鋪與連通 ===")
random.seed(20260920)
ok_preserve = True
for trial in range(120):
    gg = TriangleSliderMatrix(4)
    gg.shuffle(attempts=14, step=1, bias=0.0, min_score=None)
    gaps = gg.all_gaps()
    if not gaps:
        continue
    gt, ln = random.choice(gaps)
    d = random.choice(GAP_DIRECTIONS[gt])
    blk = random.choice(gg.blocks)
    gg.opt(gt, ln, blk)
    n = random.randint(1, 3)
    p, r = gg.try_move_ex(d, n)
    if not p:
        continue
    gg.commit_move(p)
    if len(gg.blocks) != 16:
        ok_preserve = False
        break
    if not TriangleSliderMatrix.is_single_connected(gg.positions()):
        ok_preserve = False
        break
    # 每個位置仍是一個合法單位三角（location 三元素、up 為布林）
    if not all(len(list(b.location)) == 3 and isinstance(b.location[2], bool)
               for b in gg.blocks):
        ok_preserve = False
        break
check("120 次隨機滑動後塊數/連通/位置格式均保持", ok_preserve)

# ================================================================ resolve_drag
print("=== resolve_drag（單次觸控拖動）===")
g = TriangleSliderMatrix(4)
key = (0, 0, True)
pos, gt, ln, reason, nsteps = g.resolve_drag(key, 'd', 1)
check("拖右：只給一個方向字母即可移動", bool(pos) and reason == '', f"reason={reason}")
check("拖右：縫隙族為 h", gt == 'h')
check("拖右：縫隙線穿過手指", ln == finger_line('h', key), f"line={ln}")
check("拖右：回傳步數=1", nsteps == 1, f"steps={nsteps}")

# 六向都能解析出合法移動（從不同起點嘗試）
all_ok = True
detail = {}
for letter in DIRECTIONS:
    found = False
    for i in range(4):
        for j in range(4 - i):
            for up in (True, False):
                if (i + j) > (3 if up else 2):
                    continue
                p, gt2, ln2, r2, ns2 = TriangleSliderMatrix(4).resolve_drag(
                    (i, j, up), letter, 1)
                if p:
                    found = True
                    break
            if found:
                break
        if found:
            break
    detail[letter] = found
    all_ok = all_ok and found
check("六個方向都至少有一個起點可拖動", all_ok, str(detail))

# 未知方向
p, gt3, ln3, r3, ns3 = g.resolve_drag(key, 'k', 1)
check("未知方向回 bad_direction", not p and r3 == 'bad_direction' and ns3 == 0)

# 不存在的滑塊
p, gt4, ln4, r4, ns4 = g.resolve_drag((99, 99, True), 'd', 1)
check("不存在的位置回 no_block", not p and r4 == 'no_block' and ns4 == 0)

# 步數遞減：拖 3 格但只能走 1 格時應走到 1 格而非失敗
g5 = TriangleSliderMatrix(4)
p5, _, _, r5, ns5 = g5.resolve_drag((0, 0, True), 'd', 3)
check("拖 3 格時夾緊到可行步數", bool(p5) and r5 == '', f"reason={r5}")
check("回傳步數與實際夾緊值一致", 1 <= ns5 <= 3, f"steps={ns5}")
if p5:
    # resolve_drag 只做 opt + try_move_ex，不提交，故選中標記仍有效
    sel5 = [b for b in g5.blocks if b.be_opted]
    disps = {p[0] - b.location[0] for p, b in zip(p5, sel5)}
    check("夾緊後步數在 1..3 且全組一致",
          len(disps) == 1 and 1 <= next(iter(disps)) <= 3, str(disps))

# ================================================================ shuffle
print("=== shuffle / compute_score ===")
g = TriangleSliderMatrix(4)
check("初始態 compute_score = 1.0", abs(g.compute_score() - 1.0) < 1e-9,
      f"score={g.compute_score()}")
check("初始態 is_solved", g.is_solved())
random.seed(7)
g.shuffle(attempts=30, step=1, bias=0.0, min_score=None)
check("打亂後不再是復原態", not g.is_solved())
check("打亂後塊數不變", len(g.blocks) == 16)
check("打亂後仍單一連通", TriangleSliderMatrix.is_single_connected(g.positions()))
check("打亂後聚攏度下降", g.compute_score() < 1.0, f"score={g.compute_score():.3f}")
check("打亂後無殘留選中", opt_count(g) == 0)

random.seed(11)
g2 = TriangleSliderMatrix(4)
g2.shuffle(attempts=40, step=1, bias=0.6, min_score=0.9)
check("min_score=0.9 時打亂結果夠散", g2.compute_score() <= 0.9,
      f"score={g2.compute_score():.3f}")
check("打亂後散度為正（指標有分辨力）", g2.compute_score() < 0.999,
      f"score={g2.compute_score():.4f}")

# 打亂可逆：反覆打亂不應產生重疊/丟塊
random.seed(23)
g3 = TriangleSliderMatrix(5)
stable = True
for _ in range(6):
    g3.shuffle(attempts=25, step=2, bias=0.0, min_score=None)
    if len(g3.blocks) != 25 or not TriangleSliderMatrix.is_single_connected(g3.positions()):
        stable = False
        break
check("反覆打亂（step=2）保持塊數與連通", stable)

# ================================================================ 輔助函式
print("=== 輔助函式 ===")
check("gap_for_direction 覆蓋六向",
      {gap_for_direction(d) for d in DIRECTIONS} == {'h', 'p', 'n'})
check("gap_for_direction 對無關字母回 None", gap_for_direction('k') is None)
check("finger_line h 族取 j", finger_line('h', (3, 5, True)) == 5)
check("finger_line p 族取 i", finger_line('p', (3, 5, True)) == 3)
check("finger_line n 族取 i+j", finger_line('n', (3, 5, True)) == 8)
# 凸包面積：邊長 k 實心大正面積 = k² 個單位三角
from game_triangle import hull_area_units
check("hull_area_units(k=2 實心) = 4",
      hull_area_units({(0, 0), (2, 0), (0, 2)}) == 4,
      str(hull_area_units({(0, 0), (2, 0), (0, 2)})))
check("hull_area_units(k=4 實心) = 16",
      hull_area_units({(0, 0), (4, 0), (0, 4)}) == 16,
      str(hull_area_units({(0, 0), (4, 0), (0, 4)})))
# 三族方向都平行於對應縫隙線（斜座標下沿線移動時索引不變）
par_ok = True
for gt, dirs in GAP_DIRECTIONS.items():
    for d in dirs:
        di, dj = DIRECTIONS[d]
        for (i, j) in ((3, 5), (0, 0), (7, 2)):
            k = (i, j, True)
            k2 = (i + di, j + dj, True)
            if side_of(gt, finger_line(gt, k), k) != side_of(gt, finger_line(gt, k), k2):
                par_ok = False
check("沿縫平行移動不跨到另一側", par_ok)

print()
if _failed:
    print(f"共 {len(_failed)} 項失敗:")
    for n in _failed:
        print("  -", n)
    sys.exit(1)
print("全部通過")
