# -*- coding: utf-8 -*-
"""著色＋連鎖三形態遷移的 GUI 無頭測試。

執行：python test/_test_color_chain.py
覆蓋：
- 方形顏色基準：_group_color 與 _group_color_for 對方形逐位一致，
  並釘死 step2/step3 的實測 RGB（改動前後一模一樣的回歸錨）
- 三形態連鎖集合語義：occupied ⊆ 真實滑塊、empty ∩ 滑塊 = ∅、
  兩集合同類（連鎖類含朝向）、hover 更亮的判別鍵在集合裡
- 三角/米字在 step>1 時連鎖含同類空位；移走一塊後該位必為空位高亮
- 高亮不外溢：位置必落在棋形（滑塊併集的凸包）內；晶格則看 step 奇偶——
  偶數 step 斜向位移是整數、晶格守恆；奇數 step 斜向走奇數格會換晶格，
  兩個晶格同屬一條軌道，都該亮（舊版按晶格過濾，高亮數被砍掉一半）
- 米字錯位態（真實斜向一步 → 半整數座標）參與連鎖
- step=1 閘門：方形退化成單一組 → 關；三角/米字退化成朝向分組
  （up 兩組 / q 四組）→ 照常開，且高亮全同朝向、落在棋形凸包內
- 開關關閉回 (None, None, None)
- events 懸停路徑：MOUSEMOTION 後 hover_cell 的形態
  （方形 2 元組、三角 3 元組帶 up、米字 3 元組帶 q）
- 三形態開著色＋連鎖各畫一幀不崩
- 著色環「縮環」畫法回歸錨：pygame 多邊形描邊向外擴半個線寬，
  直接描會漫進塊間縫隙蓋住縫線（含選中紅線）；縮環後塊間縫隙
  中點取樣必須仍不是任何組色（三形態都查）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_mi import mi_key, side_of  # noqa: E402
from game_triangle import tri_key  # noqa: E402
from gui.cell_class import cell_class  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def fire(evt):
    """把單個事件推入 pygame 佇列並驅動一次事件循環。"""
    pygame.event.post(evt)
    gui.handle_events()


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False        # 無頭只讀陷阱：載入後 new_puzzle 會靜默失敗
# temp_history 可能是三角/米字存檔：先建方形局面再開始
if gui.mi_mode or gui.triangle_mode:
    gui.new_puzzle(6, 6, 1)

# ================================================================ 方形顏色基準
print("== 方形顏色基準（實測錨點，改動前後必須逐位一致） ==")
gui.new_puzzle(6, 6, 2)
gui.coloring_enabled = True
STEP2 = [(234, 58, 58), (146, 234, 58), (58, 234, 234), (146, 58, 234)]
STEP3 = [(234, 58, 58), (234, 175, 58), (175, 234, 58), (58, 234, 58),
         (58, 234, 175), (58, 175, 234), (58, 58, 234), (175, 58, 234),
         (234, 58, 175)]
for step, base in ((2, STEP2), (3, STEP3)):
    gui.new_puzzle(6, 6, step)
    bad = []
    for k, rgb in enumerate(base):
        r, c = divmod(k, step)
        col = gui._group_color(r, c)
        col2 = gui._group_color_for((r, c))
        if (col.r, col.g, col.b) != rgb or (col2.r, col2.g, col2.b) != rgb:
            bad.append((step, k, rgb, (col.r, col.g, col.b),
                        (col2.r, col2.g, col2.b)))
    check(f"step{step} 顏色基準 k0..k{len(base)-1}（_group_color 與 "
          f"_group_color_for 一致）", not bad, str(bad[:2]))
gui.new_puzzle(6, 6, 2)

# ================================================================ 連鎖集合語義
print("== 連鎖集合語義（三形態） ==")


def chain_ok(kind, step):
    """當前局面下對懸停塊做一輪集合語義斷言，回傳 (occ, empty, hover)。"""
    blocks = gui.game.blocks
    blk = blocks[len(blocks) // 2]
    if kind == 'square':
        key = (blk.location[0], blk.location[1])
        positions = {(b.location[0], b.location[1]) for b in blocks}
    elif kind == 'triangle':
        key = tri_key(blk)
        positions = set(gui.game.positions())
    else:
        key = mi_key(blk)
        positions = set(gui.game.positions())
    gui.hover_cell = key
    occ, empty, hover = gui._chain_hint_cells()
    check(f"{kind}: occ 非空且 ⊆ 真實滑塊", bool(occ) and occ <= positions)
    check(f"{kind}: empty 與滑塊互斥", not (occ & empty) and not (empty & positions))
    check(f"{kind}: hover 回傳 = 懸停鍵", hover == key)
    check(f"{kind}: hover 判別鍵在 occ 裡（更亮）", key in occ)
    allkeys = occ | empty
    bad = [k for k in allkeys
           if cell_class(k[:2], step, kind) != cell_class(key[:2], step, kind)]
    check(f"{kind}: 全部同位置類", not bad, str(bad[:2]))
    return occ, empty, hover


gui.chain_hint_enabled = True
gui.new_puzzle(6, 6, 2)
occ, empty, _ = chain_ok('square', 2)
check("square: 實心 6×6 bbox 內無空位（empty 空）", empty == set())

gui.new_triangle_puzzle(6, 3)
occ, empty, hover = chain_ok('triangle', 3)
check("triangle: occ 全部同朝向（連鎖類含 up）",
      all(k[2] == hover[2] for k in occ))
# 复原态是实心盘：棋形内没有空位，棋形外（斜座標方框右上側）也不该亮
check("triangle: 復原態實心盤無空位高亮（棋形外不畫）", empty == set())
tview = gui._tri_view()
thull = tview.board_hull(gui.game.positions())
tout = [k for k in (occ | empty)
        if not gui._point_in_convex(tview.piece_center(*k), thull)]
check("triangle: 高亮全在棋形凸包內", not tout, str(tout[:3]))
# 移走一塊：原位必為空位高亮
victim = gui.game.blocks.pop()
vkey = tri_key(victim)
gui.hover_cell = vkey
occ, empty, hover = gui._chain_hint_cells()
check("triangle: 移走的塊原位是空位高亮", vkey in empty and hover == vkey)
gui.game.blocks.append(victim)

gui.new_mi_puzzle(6, 6, 3)
occ, empty, hover = chain_ok('mi', 3)
# step=3 是奇數：斜向 3 格的位移 ±(1.5, 1.5) 是半整數，一步就換晶格，
# 兩個晶格同屬一條軌道；所以只斷「落在棋形凸包內 + 同類（含朝向）」，
# 不再斷「同晶格」（那正是把高亮數砍半的舊行為），晶格語義見下一節。
mview0 = gui._mi_view()
hull0 = mview0.board_hull(gui.game.positions())
check("mi: 高亮全落在棋形凸包內",
      all(gui._point_in_convex(mview0.piece_center(*k), hull0)
          for k in (occ | empty)))
check("mi: occ 全部同朝向（連鎖類含 q）", all(k[2] == hover[2] for k in occ))
victim = gui.game.blocks.pop()
vkey = mi_key(victim)
gui.hover_cell = vkey
occ, empty, hover = gui._chain_hint_cells()
check("mi: 移走的塊原位是空位高亮", vkey in empty and hover == vkey)
gui.game.blocks.append(victim)

# ---- 米字「整格皆空的洞」也要高亮（回歸：洞被棋形過濾誤殺）----
# 洞是連鎖提示最該指的地方（哪塊能補進來）；判據是凸包，不是「該 1×1
# 格有沒有塊」。掏空 (2,2) 四個 q 後懸停它，四個 q 都得自亮。
hole = (2, 2)
victims = [b for b in gui.game.blocks
           if int(b.location[0]) == hole[0] and int(b.location[1]) == hole[1]]
check("mi: 掏空用的一整格有四塊", len(victims) == 4)
for b in victims:
    gui.game.blocks.remove(b)
gui.game.update_matrix()
for q in ('N', 'E', 'S', 'W'):
    gui.hover_cell = (hole[0], hole[1], q)
    occ, empty, hover = gui._chain_hint_cells()
    check(f"mi: 懸停空洞 (2,2,{q}) 自身必高亮（洞不被過濾）",
          hover in empty and hover not in occ)
# 洞的高亮不能外溢凸包：逐個鍵都在棋形凸包內
view = gui._mi_view()
hull = view.board_hull(gui.game.positions())
gui.hover_cell = (hole[0], hole[1], 'N')
occ, empty, hover = gui._chain_hint_cells()
out = [k for k in (occ | empty)
       if not gui._point_in_convex(view.piece_center(*k), hull)]
check("mi: 洞參與後高亮仍全在棋形凸包內", not out, str(out[:3]))
for b in victims:
    gui.game.blocks.append(b)
gui.game.update_matrix()

# ================================================================ 米字錯位態
print("== 米字錯位態（半整數座標）參與連鎖 ==")
gui.new_mi_puzzle(6, 6, 3)
ref = gui.game.block_at(
    sorted(k for k in gui.game.positions() if side_of('d1', 6, k) == 1)[0])
gui.game.opt('d1', 6, ref)
final = gui.game.try_move_ex('x', 3)[0]
check("step=3 斜向一步可提交", bool(final))
gui.game.commit_move(final)
check("錯位態出現半整數座標",
      any(abs(v - round(v)) > 1e-9
          for b in gui.game.blocks for v in mi_key(b)[:2]))
def lat_of(key):
    """晶格：0 = 整數(A)，1 = 半整數(B)。"""
    return int(round(2 * key[0])) % 2


# step=3（奇）：斜向 step 格的位移 ±(step/2, step/2) 是半整數，一步就換
# 晶格，所以「同類」橫跨 A/B 兩個晶格。以前只高亮同晶格，高亮數被砍掉
# 一半——這組斷言就是那個 bug 的回歸錨。
half_blk = next(b for b in gui.game.blocks
                if abs(b.location[0] - round(b.location[0])) > 1e-9)
gui.hover_cell = mi_key(half_blk)
occ, empty, hover = gui._chain_hint_cells()
lats = {lat_of(k) for k in (occ | empty)}
check("mi 錯位態(step=3 奇): 高亮橫跨兩個晶格（斜向奇數格換晶格）",
      lats == {0, 1}, str(sorted(lats)))
hcls = cell_class(hover, 3, 'mi') + (hover[2],)
check("mi 錯位態(step=3 奇): 高亮全同類（含朝向）",
      bool(occ) and all(cell_class(k, 3, 'mi') + (k[2],) == hcls
                        for k in (occ | empty)))
mview = gui._mi_view()
mhull = mview.board_hull(gui.game.positions())
check("mi 錯位態(step=3 奇): 高亮全在棋形凸包內",
      all(gui._point_in_convex(mview.piece_center(*k), mhull)
          for k in (occ | empty)))
# 懸停整數晶格的塊同理：同一條軌道，兩個晶格都要出現
int_blk = next(b for b in gui.game.blocks
               if abs(b.location[0] - round(b.location[0])) < 1e-9)
gui.hover_cell = mi_key(int_blk)
occ_i, empty_i, hover_i = gui._chain_hint_cells()
lats_i = {lat_of(k) for k in (occ_i | empty_i)}
check("mi 錯位態(step=3 奇): 懸停整數塊同樣橫跨兩晶格",
      bool(occ_i) and lats_i == {0, 1}, str(sorted(lats_i)))

# 偶數 step 對照組：斜向位移 ±(step/2, step/2) 是整數，晶格是真不變量，
# 高亮必須守恆（這時「同類」本來就自動排除另一晶格）
gui.new_mi_puzzle(6, 6, 2)
ref2 = gui.game.block_at(
    sorted(k for k in gui.game.positions() if side_of('d1', 4, k) == 1)[0])
gui.game.opt('d1', 4, ref2)
final2 = gui.game.try_move_ex('x', 2)[0]
check("step=2 斜向一步可提交", bool(final2))
if final2:
    gui.game.commit_move(final2)
    check("step=2 斜向後仍是整數晶格（偶數格不換晶格）",
          all(abs(v - round(v)) < 1e-9
              for b in gui.game.blocks for v in mi_key(b)[:2]))
gui.hover_cell = mi_key(gui.game.blocks[len(gui.game.blocks) // 2])
occ_e, empty_e, hover_e = gui._chain_hint_cells()
lats_e = {lat_of(k) for k in (occ_e | empty_e)}
check("mi(step=2 偶): 晶格守恆（斜向偶數格不換晶格）",
      bool(occ_e) and lats_e == {lat_of(hover_e)}, str(sorted(lats_e)))

# ================================================================ 閘門
print("== step=1 閘門：方形關、三角/米字按朝向開；開關關閉 → (None, None, None) ==")
# 三角/米字的類在 step=1 退化成朝向分組（三角 up 兩組、米字 q 四組）——
# 這兩個形態「原本就靠朝向分組」，1 級一步一格，一塊能去的恰是同朝向的
# 任意位置，連鎖照樣有用；方形退化成單一組才要關。
gui.new_triangle_puzzle(6, 1)
gui.chain_hint_enabled = True
tblk = gui.game.blocks[len(gui.game.blocks) // 2]
gui.hover_cell = tri_key(tblk)
occ, empty, hover = gui._chain_hint_cells()
tview1 = gui._tri_view()
thull1 = tview1.board_hull(gui.game.positions())
check("三角 step=1 有連鎖（1 級靠朝向分組）",
      occ is not None and hover == tri_key(tblk) and hover in occ)
check("三角 step=1: 高亮全是同朝向（▲/▼ 兩組）",
      all(k[2] == hover[2] for k in (occ | empty)))
check("三角 step=1: 高亮全在棋形凸包內",
      all(gui._point_in_convex(tview1.piece_center(*k), thull1)
          for k in (occ | empty)))

gui.new_mi_puzzle(6, 6, 1)
gui.hover_cell = mi_key(gui.game.blocks[len(gui.game.blocks) // 2])
occ, empty, hover = gui._chain_hint_cells()
check("米字 step=1 有連鎖（1 級靠朝向分組）",
      occ is not None and hover in (occ | empty))
check("米字 step=1: 高亮全是同朝向 q（N/E/S/W 四組）",
      all(k[2] == hover[2] for k in (occ | empty)))
mview1 = gui._mi_view()
mhull1 = mview1.board_hull(gui.game.positions())
check("米字 step=1: 高亮全在棋形凸包內",
      all(gui._point_in_convex(mview1.piece_center(*k), mhull1)
          for k in (occ | empty)))
# 1 級的 step=1 是奇數：斜向一格的位移 ±(½,½) 就換晶格，兩晶格都在軌道上
check("米字 step=1: 高亮橫跨兩晶格（斜向一格換晶格）",
      {lat_of(k) for k in (occ | empty)} == {0, 1})

gui.new_puzzle(6, 6, 1)
gui.hover_cell = (1, 1)
check("方形 step=1 無連鎖（類退化成單一組）",
      gui._chain_hint_cells() == (None, None, None))
gui.new_puzzle(6, 6, 2)
gui.chain_hint_enabled = False
check("開關關閉無連鎖", gui._chain_hint_cells() == (None, None, None))
gui.hover_cell = None
gui.chain_hint_enabled = True
check("無懸停無連鎖", gui._chain_hint_cells() == (None, None, None))

# ================================================================ events 懸停路徑
print("== events 懸停路徑（MOUSEMOTION → hover_cell） ==")
gui.chain_hint_enabled = True


def hover_at(world_xy):
    sx, sy = gui.world_to_screen(*world_xy)
    fire(pygame.event.Event(pygame.MOUSEMOTION, {'pos': (int(sx), int(sy)),
                                                 'buttons': (0, 0, 0)}))
    return gui.hover_cell


# 方形：2 元組（get_cell_at_pos 吃屏幕座標，內部 screen_to_world）
gui.new_puzzle(6, 6, 2)
blk = gui.game.blocks[5]
view = gui.board_view
wx, wy = view.cell_to_world(blk.location[0], blk.location[1])
cell = hover_at((wx + view.cell_size / 2, wy + view.cell_size / 2))
check(f"方形 hover_cell = {cell}（2 元組）",
      cell is not None and len(cell) == 2 and tuple(blk.location) == cell)

# 三角：3 元組帶 up
gui.new_triangle_puzzle(6, 2)
blk = gui.game.blocks[5]
view = gui._tri_view()
cell = hover_at(view.piece_center(*tri_key(blk)))
check(f"三角 hover_cell = {cell}（3 元組帶 up）",
      cell is not None and len(cell) == 3 and cell == tri_key(blk))

# 米字：3 元組帶 q
gui.new_mi_puzzle(6, 6, 2)
blk = gui.game.blocks[5]
view = gui._mi_view()
cell = hover_at(view.piece_center(*mi_key(blk)))
check(f"米字 hover_cell = {cell}（3 元組帶 q）",
      cell is not None and len(cell) == 3 and cell == mi_key(blk))

# ================================================================ 渲染冒煙
print("== 三形態開著色＋連鎖畫一幀 ==")
gui.coloring_enabled = True
gui.chain_hint_enabled = True

CLASS2 = set(STEP2)   # step2 的全部組色（三形態的組色都由 (k, step) 決定）


def seam_sample(name, sx, sy):
    """螢幕取樣一點，斷言不是任何組色（縮環畫法不得外漫進縫隙）。"""
    got = gui.screen.get_at((int(sx), int(sy)))[:3]
    check(f"{name} 縫隙中點取樣 {got} 不是組色", got not in CLASS2)


def poly_edge_mid_screen(view, key):
    """取滑塊未內縮多邊形第 0 條邊中點的螢幕座標——正好落在塊間縫上。"""
    pts = view.piece_polygon(*key, inset=False)
    mx = (pts[0][0] + pts[1][0]) / 2.0
    my = (pts[0][1] + pts[1][1]) / 2.0
    return gui.world_to_screen(mx, my)


gui.new_puzzle(6, 6, 2)
blk = gui.game.blocks[5]
gui.hover_cell = (blk.location[0], blk.location[1])
gui.draw_board()
check(True, "方形棋盤繪製正常")
# 方形用 rect 描邊（純向內），縫隙天然可見；採樣右鄰格左側縫的中點
view = gui.board_view
wx, wy = view.cell_to_world(blk.location[0], blk.location[1] + 1)
sx, sy = gui.world_to_screen(wx, wy)
seam_sample("方形", sx - gui.gap_width * gui.zoom / 2.0,
            sy + view.cell_size * gui.zoom / 2.0)

gui.new_triangle_puzzle(6, 2)
blk = gui.game.blocks[5]
gui.hover_cell = tri_key(blk)
gui.draw_board()
check(True, "三角棋盤繪製正常")
seam_sample("三角", *poly_edge_mid_screen(gui._tri_view(), tri_key(blk)))

gui.new_mi_puzzle(6, 6, 2)
blk = gui.game.blocks[5]
gui.hover_cell = mi_key(blk)
gui.draw_board()
check(True, "米字棋盤繪製正常")
seam_sample("米字", *poly_edge_mid_screen(gui._mi_view(), mi_key(blk)))

print()
if _failures:
    print(f"共 {len(_failures)} 項失敗:")
    for n in _failures:
        print("  -", n)
    sys.exit(1)
print("全部通過")
