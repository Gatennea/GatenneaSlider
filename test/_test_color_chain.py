# -*- coding: utf-8 -*-
"""著色＋連鎖三形態遷移的 GUI 無頭測試。

執行：python test/_test_color_chain.py
覆蓋：
- 方形顏色基準：_group_color 與 _group_color_for 對方形逐位一致，
  並釘死 step2/step3 的實測 RGB（改動前後一模一樣的回歸錨）
- 三形態連鎖集合語義：occupied ⊆ 真實滑塊、empty ∩ 滑塊 = ∅、
  兩集合同類（連鎖類含朝向）、hover 更亮的判別鍵在集合裡
- 三角/米字在 step>1 時連鎖含同類空位；移走一塊後該位必為空位高亮
- 高亮不外溢：位置必與懸停塊同晶格、且落在棋形內（三角的斜座標方框
  空白角落、米字的另一晶格都不亮）
- 米字錯位態（真實斜向一步 → 半整數座標）參與連鎖
- step=1 與開關關閉回 (None, None, None)
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
check("triangle: step>1 連鎖含同類空位", bool(empty))
check("triangle: occ 全部同朝向（連鎖類含 up）",
      all(k[2] == hover[2] for k in occ))
# 移走一塊：原位必為空位高亮
victim = gui.game.blocks.pop()
vkey = tri_key(victim)
gui.hover_cell = vkey
occ, empty, hover = gui._chain_hint_cells()
check("triangle: 移走的塊原位是空位高亮", vkey in empty and hover == vkey)
gui.game.blocks.append(victim)

gui.new_mi_puzzle(6, 6, 3)
occ, empty, hover = chain_ok('mi', 3)
check("mi: 高亮空位必與懸停塊同晶格且落在棋形內",
      all(abs(k[0] - hover[0]) % 1 < 1e-9 and abs(k[1] - hover[1]) % 1 < 1e-9
          for k in (occ | empty)))
check("mi: occ 全部同朝向（連鎖類含 q）", all(k[2] == hover[2] for k in occ))
victim = gui.game.blocks.pop()
vkey = mi_key(victim)
gui.hover_cell = vkey
occ, empty, hover = gui._chain_hint_cells()
check("mi: 移走的塊原位是空位高亮", vkey in empty and hover == vkey)
gui.game.blocks.append(victim)

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
# 懸停一個「半整數晶格」的塊：同類高亮必須全在同晶格（都是半整數）
half_blk = next(b for b in gui.game.blocks
                if abs(b.location[0] - round(b.location[0])) > 1e-9)
gui.hover_cell = mi_key(half_blk)
occ, empty, hover = gui._chain_hint_cells()
check("mi 錯位態: 懸停半整數塊時高亮全在半整數晶格",
      bool(occ) and all(abs(k[0] - round(k[0])) > 1e-9
                        and abs(k[1] - round(k[1])) > 1e-9
                        for k in (occ | empty)))
# 懸停整數晶格的塊：高亮全在整數晶格（不混入半整數）
int_blk = next(b for b in gui.game.blocks
               if abs(b.location[0] - round(b.location[0])) < 1e-9)
gui.hover_cell = mi_key(int_blk)
occ_i, empty_i, _ = gui._chain_hint_cells()
check("mi 錯位態: 懸停整數塊時高亮全在整數晶格",
      all(abs(k[0] - round(k[0])) < 1e-9 and abs(k[1] - round(k[1])) < 1e-9
          for k in (occ_i | empty_i)))

# ================================================================ 閘門
print("== step=1 與開關關閉 → (None, None, None) ==")
gui.new_triangle_puzzle(6, 1)
gui.chain_hint_enabled = True
gui.hover_cell = tri_key(gui.game.blocks[0])
check("三角 step=1 無連鎖", gui._chain_hint_cells() == (None, None, None))
gui.new_mi_puzzle(6, 6, 1)
gui.hover_cell = mi_key(gui.game.blocks[0])
check("米字 step=1 無連鎖", gui._chain_hint_cells() == (None, None, None))
gui.new_puzzle(6, 6, 1)
gui.hover_cell = (1, 1)
check("方形 step=1 無連鎖", gui._chain_hint_cells() == (None, None, None))
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
