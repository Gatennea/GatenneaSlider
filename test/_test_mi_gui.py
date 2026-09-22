# -*- coding: utf-8 -*-
"""米字格 GUI 無頭測試（Stage M1 靜態預覽 + M2 兩次觸控互動）。

執行：python test/_test_mi_gui.py
覆蓋：建局入口（new_mi_puzzle）的形態旗標與判勝、謎題鍵/標籤/預設打勾、
      相機（米字格包圍盒是矩形但世界座標無 gap 間距）、draw_board 米字分支
      真的畫出了東西、M2 的兩次觸控（第一下選縫、第二下點塊即提交）、
      打亂、縫隙/滑塊命中、拖拽與單次觸控與自動求解被攔並提示、
      物理鍵盤只提示、虛擬鍵盤八向、4-bit 快照往返
      （save_snapshot → restore_snapshot）、v2 存檔 type=mi 往返。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_mi import MiSliderMatrix, mi_key  # noqa: E402
from gui.mi_view import MiBoardView  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False        # 無頭只讀陷阱：載入後 new_puzzle 會靜默失敗

# ================================================================ 建局
print("== 建局入口 ==")
check("new_mi_puzzle 返回 True", gui.new_mi_puzzle(4, 4, 1) is True)
check("mi_mode 旗標置位且三角形/數字旗標清空",
      gui.mi_mode is True and gui.triangle_mode is False and gui.numbered is False)
check("game 是 MiSliderMatrix", isinstance(gui.game, MiSliderMatrix))
check(f"4×4 建局 {len(gui.game.blocks)} 塊（4 塊/格）", len(gui.game.blocks) == 64)
check("建局即為還原態", gui.is_solved() is True)
check("非法尺寸/等級被拒",
      gui.new_mi_puzzle(4, 4, 4) is False and gui.new_mi_puzzle(1, 4, 1) is False)

# 長方形（m≠n）也支持：分榜鍵與 is_solved 都按 m×n
check("5×3 米字格可建", gui.new_mi_puzzle(5, 3, 2) is True)
check(f"5×3 有 {len(gui.game.blocks)} 塊", len(gui.game.blocks) == 60)
check("5×3 判還原", gui.is_solved() is True)

gui.new_mi_puzzle(6, 6, 2)
check("6×6 有 144 塊", len(gui.game.blocks) == 144)

# ================================================================ 鍵／標籤／預設
print("== 謎題鍵與菜單預設 ==")
check(f"謎題鍵 = {gui._current_puzzle_key()}", gui._current_puzzle_key() == '2~mi6*6')
check(f"形態鍵 = {gui._current_kind()}", gui._current_kind() == 'mi')
check(f"標籤 = {gui._current_puzzle_label()}",
      gui._current_puzzle_label() == '米字格 6×6 等级2')

mi_preset = [p for p in gui.puzzle_presets if len(p) >= 5 and p[4] == 'mi']
check(f"謎題菜單有 {len(mi_preset)} 個米字格預設", len(mi_preset) >= 3)
check("每個米字格預設都能对上當前鍵（打勾邏輯）",
      all(gui._preset_puzzle_key(p) == gui._current_puzzle_key()
          for p in mi_preset if p[:4] == (6, 6, 2, 2)))
check("米字格預設的等級都小於 max(m,n)",
      all(p[3] < max(p[1], p[2]) for p in mi_preset))
check("米字格預設自成一個分組（前一项是分组标题）",
      any(p[:2] == ('__group__', '米字格谜题') for p in gui.puzzle_presets))

# 切回方形：鍵與旗標都要回位
gui.new_puzzle(5, 5, 2)
check("切回方形後鍵 = 2~5*5", gui._current_puzzle_key() == '2~5*5')
check("切回方形後 mi_mode 清空", gui.mi_mode is False)

# ================================================================ 相機
print("== 相機（米字格包圍盒）==")
gui.new_mi_puzzle(6, 6, 2)
view = gui._mi_view()
check("_mi_view 緩存：同尺寸返回同一對象", gui._mi_view() is view)
old_cell = gui.cell_size
gui.cell_size = old_cell + 1
check("_mi_view 隨 cell_size 重建", gui._mi_view().cell_size == old_cell + 1)
gui.cell_size = old_cell          # 還原，後斷言按 60 寫
gui.new_mi_puzzle(6, 6, 2)
view = gui._mi_view()
min_x, min_y, max_x, max_y = view.bounding_box(gui.game.positions())
check(f"6×6 包圍盒 = ({min_x},{min_y},{max_x},{max_y})",
      (min_x, min_y, max_x, max_y) == (0.0, 0.0, 360.0, 360.0))
check(f"初始縮放 = {gui.zoom:.3f} 在合理範圍", 0.1 < gui.zoom <= 5.0)
# center_map 後棋心應落在遊戲區中心（用包圍盒中心，不是某一塊的內心）
bcx, bcy = (min_x + max_x) / 2.0, (min_y + max_y) / 2.0
sx, sy = gui.world_to_screen(bcx, bcy)
exp_x = (gui.screen_width - gui.right_panel_width) / 2
exp_y = gui.menu_bar_height + (gui.screen_height - gui.menu_bar_height
                               - gui.status_bar_height) / 2
check(f"棋心落在遊戲區中心（偏差 {abs(sx - exp_x):.1f},{abs(sy - exp_y):.1f}px）",
      abs(sx - exp_x) < 2 and abs(sy - exp_y) < 2)
gui.ensure_blocks_visible()
sx2, sy2 = gui.world_to_screen(min_x, min_y)
sx3, sy3 = gui.world_to_screen(max_x, max_y)
check(f"ensure_blocks_visible 後棋盤在視口內"
      f"（x {sx2:.0f}~{sx3:.0f}，視口 0~{gui.screen_width - gui.right_panel_width}）",
      sx2 >= -1 and sx3 <= gui.screen_width - gui.right_panel_width + 1)
check("_mi_hit_board：棋心命中、遠處不命中",
      gui._mi_hit_board(int(exp_x), int(exp_y))
      and not gui._mi_hit_board(5, 5))

# ================================================================ 渲染
print("== draw_board 米字分支 ==")
before = pygame.surfarray.array3d(gui.screen).copy()
gui.draw_board()
after = pygame.surfarray.array3d(gui.screen)
changed = int((before != after).any(axis=2).sum())
check(f"draw_mi_board 改變了 {changed} 個像素", changed > 10000)
# 背景應被棋盤色（60,150,200）覆蓋一大片
bg = tuple(gui.colors['background'])
blue = tuple(gui.colors['block'])
n_bg = int((after == bg).all(axis=2).sum())
n_blue = int((after == blue).all(axis=2).sum())
total = after.shape[0] * after.shape[1]
# 棋盤只佔遊戲區一塊，其餘是背景（菜單欄/右面板/邊距都在背景色裡）
check(f"背景像素仍是多數但不到 90%（{n_bg}/{total}）",
      total * 0.5 < n_bg < total * 0.9)
check(f"畫出了 {n_blue} 個滑塊色像素", n_blue > 50000)
# 米字背景：取棋心附近應有深色縫線像素（colors['gap']）
gap_c = tuple(gui.colors['gap'])
n_gap = int((after == gap_c).all(axis=2).sum())
check(f"米字背景畫出了 {n_gap} 個縫線像素", n_gap > 100)

# ================================================================ M2 交互
print("== M2 交互（兩次觸控 / 打亂 / 護欄）==")
gui.new_mi_puzzle(6, 6, 2)
view = gui._mi_view()
s = view.cell_size


def fire(evt):
    """把单个事件推入 pygame 队列并驱动一次事件循环。"""
    pygame.event.post(evt)
    gui.handle_events()


# —— 未選縫隙時一律不動，並說明要兩次觸觸 ——
gui.macro_notify_msg = ''
check("未選縫隙不能移動", gui.move_selected_blocks('w', 1) is False)
check("提示要點選縫隙", '点选缝隙' in (gui.macro_notify_msg or ''), gui.macro_notify_msg or '')
check("未選縫隙時局面不變", gui.is_solved() is True)

# —— 打亂接上（M2 起 game_mi.shuffle 可用）——
snap = set(gui.game.positions())
gui.shuffle_puzzle()
check(f"打亂後局面改變（{len(gui.game.positions())} 塊）",
      set(gui.game.positions()) != snap and len(gui.game.positions()) == 144)
check("打亂後不是還原態", gui.is_solved() is False)
check("打亂後仍是米字模式", gui.mi_mode is True)

# —— 命中：縫隙線中點 → get_gap_at_pos；塊內心 → get_block_at_pos ——
gui.new_mi_puzzle(6, 6, 2)
view = gui._mi_view()
hull = view.board_hull(gui.game.positions())
for gt, line in [('h', 2), ('v', 3), ('d1', 0), ('d2', 4)]:
    seg = view.gap_segment(gt, line, hull)
    check(f"{gt} {line} 有縫隙線段", seg is not None)
    if seg is None:
        continue
    # 取線上 30% 處而非中點：中點常落在格角/格心（多條邊等距 0），
    # 那樣驗的是平手裁決而不是「這條線本身能不能命中」
    mx = seg[0][0] + (seg[1][0] - seg[0][0]) * 0.3
    my = seg[0][1] + (seg[1][1] - seg[0][1]) * 0.3
    sx, sy = gui.world_to_screen(mx, my)
    got = gui.get_gap_at_pos(int(sx), int(sy))
    check(f"點在 {gt} {line} 線上命中該縫（實得 {got}）", got == (gt, line))
# 塊內心命中該塊
c0 = gui.game.blocks[0]
pcx, pcy = view.piece_center(*mi_key(c0))
sx, sy = gui.world_to_screen(pcx, pcy)
check("塊內心命中該塊", gui.get_block_at_pos(int(sx), int(sy)) is c0)
# 棋盤外（真正的空白）不命中滑塊
check("棋盤外不命中滑塊",
      gui.get_block_at_pos(*gui.world_to_screen(*view.to_world(-0.5, 2.0))) is None)

# —— 兩次觸控：第一下選縫、第二下點塊即提交 ——
from game_mi import (  # noqa: E402
    DIRECTIONS as MI_DIRECTIONS,
    GAP_DIRECTIONS as MI_GAP,
    mi_key,
    side_of,
)

POS_DIR = {'h': 'd', 'v': 's', 'd1': 'x', 'd2': 'e'}


def gaps_of(gt):
    """某一族出現過的全部 line（保持 all_gaps 的順序、去重）。"""
    return list(dict.fromkeys(l for (g, l) in gui.game.all_gaps() if g == gt))


POS_DIR = {'h': 'd', 'v': 's', 'd1': 'x', 'd2': 'e'}


def gaps_of(gt):
    """某一族出現過的全部 line（保持 all_gaps 的順序、去重）。"""
    return list(dict.fromkeys(l for (g, l) in gui.game.all_gaps() if g == gt))


def seg_extent(gt, line):
    """縫隙線段的切向取值範圍（格座標 (lo, hi)）；沒有線段回 None。

    切向座標 = (x, y)·tangent：水平族就是 x、豎直族是 y、兩族對角各是
    x+y / x−y，與 MI_GAP_AXES 同一套軸，故整段測試只用這一個標尺。
    """
    seg = view.gap_segment(gt, line, hull)
    if seg is None:
        return None
    tan = gui.MI_GAP_AXES[gt][0]
    a, b = view.from_world(*seg[0]), view.from_world(*seg[1])
    ts = [a[0] * tan[0] + a[1] * tan[1], b[0] * tan[0] + b[1] * tan[1]]
    return min(ts), max(ts)


def anchor_for(gt, line, key):
    """塊中心投影到縫線上，再沿切向負方向挪 0.4 格（夾在縫線段內）。

    回傳 (世界座標錨點, 預期方向字母)。錨點落在縫上 → 法向校驗必過；
    塊在錨點的切向正側 → 正方向字母，負側 → 負方向字母。線段太短、兩個
    方向都挪不出 0.4 格時回傳 (None, None)。

    直接拿塊的投影當錨點有兩個坑：那時的偏移是純法向的，正好命中
    「判斷不出方向」那條提示；而靠邊的塊投影後再沿切向挪，錨點會掉到棋
    盤外，第一下連縫都選不中——所以必須夾在縫線段內。
    """
    bx, by = view.from_world(*view.piece_center(*key))
    pos_d, neg_d = gui.MI_GAP_AXES[gt][2], gui.MI_GAP_AXES[gt][3]
    if gt == 'h':
        proj, t = (bx, line + 1), bx
    elif gt == 'v':
        proj, t = (line + 1, by), by
    elif gt == 'd1':
        k = line / 2.0                       # 縫線 y − x = k
        proj, t = ((bx + by - k) / 2.0, (bx + by + k) / 2.0), bx + by
    else:                                   # d2：縫線 x + y = k
        k = line / 2.0 + 1.0
        proj, t = ((bx - by + k) / 2.0, (k - bx + by) / 2.0), bx - by
    ext = seg_extent(gt, line)
    if ext is None:
        return None, None
    lo, hi = ext
    if t - 0.4 >= lo:
        at, expect = t - 0.4, pos_d
    elif t + 0.4 <= hi:
        at, expect = t + 0.4, neg_d
    else:
        return None, None
    d = at - t
    if gt == 'h':
        p = (proj[0] + d, proj[1])
    elif gt == 'v':
        p = (proj[0], proj[1] + d)
    elif gt == 'd1':
        p = (proj[0] + d / 2.0, proj[1] + d / 2.0)
    else:
        p = (proj[0] + d / 2.0, proj[1] - d / 2.0)
    return view.to_world(*p), expect


def choose_pair(gt):
    """給定縫族找一組 (line, block, 方向)：兩次觸控能真正提交一步。

    條件：錨點自己命中這條縫、方向由切向符號定出、選中組沿這個方向滑得
    動。實心棋盤上多數組合會被擋住或移完斷開，逐個試到走得動的為止。
    """
    for line in gaps_of(gt):
        for blk in gui.game.blocks:
            anchor, expect = anchor_for(gt, line, mi_key(blk))
            if anchor is None:
                continue
            sx, sy = gui.world_to_screen(*anchor)
            if gui.get_gap_at_pos(int(sx), int(sy)) != (gt, line):
                continue
            gui.game.opt(gt, line, blk)
            movable = bool(gui.game.try_move_ex(expect, gui.current_step)[0])
            gui.game._clear_selection()
            if movable:
                return line, blk, expect
    return None, None, None


def run_two_touch(gt, line, blk):
    """完整跑一遍「第一下選縫 → 第二下點塊即提交」，回傳是否全部符合預期。"""
    key = mi_key(blk)
    anchor, expect = anchor_for(gt, line, key)
    if anchor is None:
        check(f"{gt} {line}：找到縫上的錨點", False)
        return False
    step = gui.current_step
    dr, dc = MI_DIRECTIONS[expect]
    asx, asy = gui.world_to_screen(*anchor)
    bsx, bsy = gui.world_to_screen(*view.piece_center(*key))
    ok = check(f"{gt} {line}：錨點自己命中該縫",
               gui.get_gap_at_pos(int(asx), int(asy)) == (gt, line))
    # 手算一次預期方向（與 GUI 的投影同源但獨立寫在這裡）
    t, n, pos_d, _neg_d = gui.MI_GAP_AXES[gt]
    dx, dy = bsx - asx, bsy - asy
    proj_t = dx * t[0] + dy * t[1]
    proj_n = dx * n[0] + dy * n[1]
    ok &= check(f"{gt} {line}：切向分量對應 {expect}（proj_t={proj_t:.1f}px）",
                (proj_t > 0) == (expect == pos_d))
    side = side_of(gt, line, key)
    ok &= check(f"{gt} {line}：法向分量指向 {side} 側（proj_n={proj_n:.1f}px）",
                (proj_n > 0) == (side == 1))
    # 預先算好這一側的選中組（opt 只置標誌、不動位置），再清掉重來，
    # 讓兩次觸控自己走一遍選組流程
    gui.game.opt(gt, line, blk)
    before = set(mi_key(b) for b in gui.game.blocks if b.be_opted)
    ok &= check(f"{gt} {line}：這一側選中 {len(before)} 塊（不是全部、也不是空）",
                0 < len(before) < len(gui.game.blocks))
    for b in gui.game.blocks:
        b.be_opted = False
    rest_before = set(gui.game.positions()) - before
    gui.selected_gap = None
    gui.selected_block = None
    # 1) 第一下：點在縫上 → 選中縫隙並記下錨點
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(asx), int(asy))}))
    ok &= check(f"{gt} {line}：第一下選中該縫", gui.selected_gap == (gt, line))
    ok &= check(f"{gt} {line}：錨點已記錄",
                getattr(gui, '_mi_gap_point', None) is not None)
    ok &= check(f"{gt} {line}：選縫後未選塊", gui.selected_block is None)
    ok &= check(f"{gt} {line}：選縫時沒有動過棋盤", gui.is_solved() is True)
    # 2) 第二下：點在塊上 → 直接提交
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(bsx), int(bsy))}))
    moved = set(mi_key(b) for b in gui.game.blocks if b.be_opted)
    ok &= check(f"{gt} {line}：第二下選中了滑塊組（{len(moved)} 塊）",
                len(moved) == len(before) > 0)
    ok &= check(f"{gt} {line}：提交後步數 = 1（實得 {gui.step_count}）",
                gui.step_count == 1)
    # 選中組整體沿 expect 移動 step 格，q 不變
    want = {(r + dr * step, c + dc * step, q) for (r, c, q) in before}
    ok &= check(f"{gt} {line}：選中組沿正確方向平移",
                want == moved,
                f"期望 {sorted(want)[:3]} 實得 {sorted(moved)[:3]}")
    ok &= check(f"{gt} {line}：q 朝向不變",
                {q for (_r, _c, q) in moved} ==
                {q for (_r, _c, q) in before})
    # 未被選中的其餘部分原封不動
    ok &= check(f"{gt} {line}：其餘部分沒被動",
                set(gui.game.positions()) - moved == rest_before)
    # 3) 第三下點同一條縫 → 取消選中
    #    螢幕座標必須重新投影：滑出棋盤的組會讓 ensure_blocks_visible 平移
    #    鏡頭，移動前記下的像素已經指到別的世界點上（米字格組經常半幅出界）
    asx, asy = gui.world_to_screen(*anchor)
    ok &= check(f"{gt} {line}：移後同一世界點仍命中該縫",
                gui.get_gap_at_pos(int(asx), int(asy)) == (gt, line))
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(asx), int(asy))}))
    ok &= check(f"{gt} {line}：再點同一條縫取消選中", gui.selected_gap is None)
    return ok


# 四族縫各跑一遍（方向來自切向符號，四族的切向軸互不相同）
for gt in ('h', 'v', 'd1', 'd2'):
    gui.new_mi_puzzle(6, 6, 2)
    view = gui._mi_view()
    hull = view.board_hull(gui.game.positions())
    line, blk, expect = choose_pair(gt)
    check(f"{gt} 族有可用的「縫＋塊＋方向」組合", blk is not None,
          f"實得 line={line} 方向={expect}")
    if blk is not None:
        run_two_touch(gt, line, blk)

# —— 回歸：第二下用掉錨點後，單擊滑塊只選組、不再滑動 ——
# 曾經的症狀：兩次觸控提交一次移動後選中態還留著，之後每次單擊滑塊都拿
# 第一下的舊落點重新定向，出現「只是點了幾下、滑塊自己滑走」的幽靈移動。
gui.new_mi_puzzle(6, 6, 2)
view = gui._mi_view()
hull = view.board_hull(gui.game.positions())
line, blk, expect = choose_pair('h')
check("回歸場景有可用組合", blk is not None)
if blk is not None:
    key = mi_key(blk)
    anchor, expect = anchor_for('h', line, key)
    asx, asy = gui.world_to_screen(*anchor)
    bsx, bsy = gui.world_to_screen(*view.piece_center(*key))
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(asx), int(asy))}))
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(bsx), int(bsy))}))
    check("兩次觸控提交了一步", gui.step_count == 1)
    check("提交後錨點已用掉", gui._mi_gap_point is None)
    check("提交後選中態仍留著（縫與組都還在）",
          gui.selected_gap == ('h', line)
          and len([b for b in gui.game.blocks if b.be_opted]) > 0)
    # 選中態還在的時候再單擊一塊（沒有重新點縫）→ 只換選組，不動棋盤
    other = next((b for b in gui.game.blocks if not b.be_opted), None)
    check("找得到選中組之外的塊", other is not None)
    if other is not None:
        osx, osy = gui.world_to_screen(*view.piece_center(*mi_key(other)))
        check("那塊的內心不會誤選到縫",
              gui.get_gap_at_pos(int(osx), int(osy)) is None)
        gui.macro_notify_msg = ''
        fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 1, 'pos': (int(osx), int(osy))}))
        check("提交後單擊滑塊不再滑動", gui.is_solved() is False
              and gui.step_count == 1)
        check("單擊只換選組並提示用虛擬鍵盤",
              '虚拟键盘' in (gui.macro_notify_msg or ''),
              gui.macro_notify_msg or '')

# —— 定向校驗：純法向偏移 / 塊在偏移背面 都要被拒 ——
# 直接用軸向量構造偏移、不靠投影湊：切向與法向正交，所以「純法向」就是
# 精確的零切向分量，「背面」就是精確反號的法向分量。
for gt in ('h', 'v', 'd1', 'd2'):
    gui.new_mi_puzzle(6, 6, 2)
    view = gui._mi_view()
    hull = view.board_hull(gui.game.positions())
    line, blk, _expect = choose_pair(gt)
    check(f"{gt}：有可用組合做定向校驗", blk is not None)
    if blk is None:
        continue
    t, n, pos_d, neg_d = gui.MI_GAP_AXES[gt]
    # 法向指向自己所在側的符號（與 GUI 內部 side_of 同一套判據）
    sn = 1.0 if side_of(gt, line, mi_key(blk)) == 1 else -1.0
    # 純法向偏移（指向自己那一側）→ 沒有切向分量，判不出方向
    gui.macro_notify_msg = ''
    d = gui._mi_tap_direction(gt, line, blk, (n[0] * sn * 0.4, n[1] * sn * 0.4))
    check(f"{gt}：純法向偏移判不出方向",
          d is None and '垂直' in (gui.macro_notify_msg or ''),
          gui.macro_notify_msg or '')
    # 法向指向自己那一側的反面（相當於點了縫另一側的塊）→ 校驗攔下
    gui.macro_notify_msg = ''
    d = gui._mi_tap_direction(gt, line, blk,
                              (-n[0] * sn * 0.4 + t[0] * 0.4,
                               -n[1] * sn * 0.4 + t[1] * 0.4))
    check(f"{gt}：塊在偏移的背面拿不到方向",
          d is None and '另一侧' in (gui.macro_notify_msg or ''),
          gui.macro_notify_msg or '')
    # 法向指向自己那一側、切向正負 → 分別給正/負方向字母
    gui.macro_notify_msg = ''
    d = gui._mi_tap_direction(gt, line, blk,
                              (n[0] * sn * 0.4 + t[0] * 0.4,
                               n[1] * sn * 0.4 + t[1] * 0.4))
    check(f"{gt}：切向為正向給 {pos_d}", d == pos_d, f"實得 {d}")
    gui.macro_notify_msg = ''
    d = gui._mi_tap_direction(gt, line, blk,
                              (n[0] * sn * 0.4 - t[0] * 0.4,
                               n[1] * sn * 0.4 - t[1] * 0.4))
    check(f"{gt}：切向為負向給 {neg_d}", d == neg_d, f"實得 {d}")

# —— 與選中縫隙不平行的方向被拒 ——
gui.selected_gap = ('h', 2)
gui.selected_block = gui.game.blocks[0]
gui.macro_notify_msg = ''
check("不平行方向被拒", gui.move_selected_blocks('w', 1) is False)
check("不平行方向有提示", '不平行' in (gui.macro_notify_msg or ''), gui.macro_notify_msg or '')

# —— 單次觸控 / 拖拽 / 自動求解：一律攔下 ——
gui.selected_gap = None
gui.selected_block = None
gui.macro_notify_msg = ''
check("拖拽不記錄起點", (fire(pygame.event.Event(
    pygame.MOUSEBUTTONDOWN, {'button': 1, 'pos': (
        int(gui.world_to_screen(*view.piece_center(*mi_key(gui.game.blocks[0])))[0]),
        int(gui.world_to_screen(*view.piece_center(*mi_key(gui.game.blocks[0])))[1]))})),
    gui._mouse_drag_state is None)[1])
check("_init_drag_follow 被攔", gui._init_drag_follow(gui.game.blocks[0], 10, 0) is False)
check("拖拽提示提到兩次觸控", '两次触控' in (gui.macro_notify_msg or ''), gui.macro_notify_msg or '')
gui.macro_notify_msg = ''
gui._start_auto_solve()
check("自動求解被攔", '米字格' in (gui.macro_notify_msg or ''), gui.macro_notify_msg or '')

# —— 物理鍵盤：只提示，不動棋盤 ——
gui.new_mi_puzzle(6, 6, 2)
snap = set(gui.game.positions())
gui.selected_gap = ('h', 2)
gui.selected_block = gui.game.blocks[0]
gui.game.opt('h', 2, gui.game.blocks[0])
gui.macro_notify_msg = ''
fire(pygame.event.Event(pygame.KEYDOWN, {'key': pygame.K_w, 'mod': 0, 'unicode': 'w'}))
check("按方向鍵只提示用虛擬鍵盤", '虚拟键盘' in (gui.macro_notify_msg or ''),
      gui.macro_notify_msg or '')
check("按方向鍵不動棋盤", set(gui.game.positions()) == snap)

# —— 虛擬鍵盤：八向 + 方向必須平行於已選縫隙 ——
gui.new_mi_puzzle(6, 6, 2)
rects = gui._vk_build_layout()
check(f"米字格方向鍵 8 個（實得 {len(rects) - 3} 個）",
      {'move_up', 'move_down', 'move_left', 'move_right',
       'move_ul', 'move_ur', 'move_dl', 'move_dr'} <= set(rects))
check("米字格方向鍵 3 行", gui._vk_direction_rows() == 3)
# 選一條水平縫 → 只有 a/d 允許
gui.selected_gap = ('h', 2)
gui.selected_block = None
gui.game.opt('h', 2, gui.game.blocks[0])
n_sel = len([b for b in gui.game.blocks if b.be_opted])
check(f"虛擬鍵盤路徑：未點塊也能選組（{n_sel} 塊）", n_sel > 0)
gui.macro_notify_msg = ''
gui._vk_trigger_action('move_ur')
check("斜向鍵對水平縫不生效", '不匹配' in (gui.macro_notify_msg or ''),
      gui.macro_notify_msg or '')
snap = set(gui.game.positions())
gui._vk_trigger_action('move_right')
check("按 → 沿水平縫移動", set(gui.game.positions()) != snap)
check("移動後步數 = 1", gui.step_count == 1)
# 未選縫隙 → 提示先點縫
gui.selected_gap = None
gui.selected_block = None
for b in gui.game.blocks:
    b.be_opted = False
gui.macro_notify_msg = ''
gui._vk_trigger_action('move_up')
check("未選縫隙按鍵有提示", '点选缝隙' in (gui.macro_notify_msg or ''),
      gui.macro_notify_msg or '')

# —— 回歸：虛擬鍵盤八向按鍵 ↔ 四族縫隙的方向字母表 ——
# 曾經的症狀：↖（move_ul）用的是三角版的字母 w，米字格該是 q——選著
# 對角縫按 ↖ 報「方向不匹配」，選著豎直縫則默默走上而不是左上。
VK_BTN = {'q': 'move_ul', 'w': 'move_up', 'e': 'move_ur',
          'a': 'move_left', 'd': 'move_right',
          'z': 'move_dl', 's': 'move_down', 'x': 'move_dr'}
for gt in ('h', 'v', 'd1', 'd2'):
    gui.new_mi_puzzle(6, 6, 2)
    view = gui._mi_view()
    hull = view.board_hull(gui.game.positions())
    line, blk, expect = choose_pair(gt)
    check(f"{gt}：VK 回歸有可用組合", blk is not None)
    if blk is None:
        continue
    gui.selected_gap = (gt, line)
    gui.selected_block = blk
    gui.game.opt(gt, line, blk)
    snap = set(gui.game.positions())
    gui.macro_notify_msg = ''
    gui._vk_trigger_action(VK_BTN[expect])
    check(f"{gt} 縫：{VK_BTN[expect]} 對應 {expect} 並真的滑動",
          set(gui.game.positions()) != snap and gui.step_count == 1,
          gui.macro_notify_msg or '')
    # 其餘六個按鍵（別的族的字母）都必須被「方向與縫隙不平行」擋下，
    # 且不動棋盤；同族另一個字母是合法的，這裡不斷言它移不移得動
    for letter, action in VK_BTN.items():
        if letter in MI_GAP[gt]:
            continue
        snap = set(gui.game.positions())
        gui.macro_notify_msg = ''
        gui._vk_trigger_action(action)
        check(f"{gt} 縫：{action}（{letter}）被擋下",
              set(gui.game.positions()) == snap
              and '不匹配' in (gui.macro_notify_msg or ''),
              gui.macro_notify_msg or '')

# —— 單次觸控開關在米字格下被拒 ——
gui.macro_notify_msg = ''
gui.control_single_touch = False
gui.show_settings_dialog = True
gui.settings_active_tab = 'control'
# 其餘 Tab / 開關矩形全部挪到屏幕外（對話框未真正繪製，值為 None 會撞）
for _name in ('_settings_tab_kb_rect', '_settings_tab_solver_rect',
              '_settings_tab_anim_rect', '_settings_tab_gather_rect',
              '_settings_tab_file_rect', '_settings_tab_control_rect',
              '_settings_readonly_toggle_rect', '_settings_prevent_overwrite_rect',
              '_settings_chain_toggle_rect', '_settings_coloring_toggle_rect',
              '_settings_slider_track_rect', '_settings_slider_knob_rect'):
    setattr(gui, _name, pygame.Rect(-100, -100, 10, 10))
gui._settings_ctrl_single_rect = pygame.Rect(10, 10, 40, 20)
fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'button': 1, 'pos': (10, 10)}))
check("米字格不讓開單次觸控",
      gui.control_single_touch is False and '单次触控' in (gui.macro_notify_msg or ''),
      gui.macro_notify_msg or '')
gui.show_settings_dialog = False

# ================================================================ 4-bit 快照往返
print("== 4-bit 快照往返 ==")
gui.new_mi_puzzle(4, 4, 1)
before_pos = set(gui.game.positions())
gui.game_history.save_snapshot(gui.game)
gui.game.blocks = gui.game.blocks[2:]          # 弄壞局面
gui.game_history.restore_snapshot(gui.game, 0)
check(f"restore_snapshot 還原 {len(gui.game.blocks)} 塊",
      len(gui.game.blocks) == len(before_pos))
check("restore_snapshot 還原每塊的 (r,c,q)",
      set(mi_key(b) for b in gui.game.blocks) == before_pos)
flat = [v for row in gui.game.matrix for v in row]
check(f"快照矩陣取值均在 0..15（{min(flat)}..{max(flat)}）",
      all(0 <= v <= 15 for v in flat))
check(f"快照矩陣覆蓋全部 64 塊（{sum(bin(v).count('1') for v in flat)}）",
      sum(bin(v).count('1') for v in flat) == 64)

# ================================================================ 存讀檔往返
print("== v2 存檔 type=mi 往返 ==")
data = gui._build_save_data()
check("存檔 version=2 且 type=mi",
      data['version'] == 2 and data['puzzle']['type'] == 'mi')
check("存檔 m/n/step 正確",
      (data['puzzle']['m'], data['puzzle']['n'], data['puzzle']['step']) == (4, 4, 1))
saved_pos = set(gui.game.positions())
gui.new_puzzle(5, 5, 2)          # 先切到方形，確認載入會正確分派
gui._load_save_data(data)
check("載入後 mi_mode 復原", gui.mi_mode is True)
check("載入後三角形旗標為假", gui.triangle_mode is False)
check("載入後 game 是米字格", isinstance(gui.game, MiSliderMatrix))
check("載入後塊數/位置一致",
      len(gui.game.blocks) == 64 and set(gui.game.positions()) == saved_pos)
check("載入後判還原", gui.is_solved() is True)

# ================================================================ 像素級形狀
print("== 像素級形狀（代替肉眼看圖）==")
gui.new_mi_puzzle(4, 4, 1)
view = gui._mi_view()
gui.draw_board()
arr = pygame.surfarray.array3d(gui.screen)
blue = tuple(gui.colors['block'])
bg = tuple(gui.colors['background'])


def px(sx, sy):
    return tuple(int(v) for v in arr[int(sx), int(sy)])


# 1) 每塊內心都落在滑塊色上（64 塊 = 4 格 × 4 塊）
bad = [(r, c, q) for r in range(4) for c in range(4) for q in ('N', 'E', 'S', 'W')
       if px(*gui.world_to_screen(*view.piece_center(r, c, q))) != blue]
check(f"64 塊的內心都是滑塊色（異常 {len(bad)} 塊：{bad[:4]}）", not bad)

# 2) 每格中心是四塊交匯處（兩條對角線都穿過它）→ 不該被任何一塊蓋住
bad = [(r, c) for r in range(4) for c in range(4)
       if px(*gui.world_to_screen(*view.to_world(c + 0.5, r + 0.5))) == blue]
check(f"格心留白（16/16，異常 {bad[:4]}）", not bad)

# 3) 每條格邊的中點是相鄰兩塊的拼縫 → 不該被任何一塊蓋住
bad = []
for r in range(4):
    for c in range(4):
        if px(*gui.world_to_screen(*view.to_world(c + 0.5, r))) == blue:
            bad.append(('h', r, c))           # 上格邊
        if px(*gui.world_to_screen(*view.to_world(c, r + 0.5))) == blue:
            bad.append(('v', r, c))           # 左格邊
check(f"格邊都是縫（拼縫數 4×4×2，異常 {len(bad)} 條：{bad[:4]}）", not bad)

# 4) 棋盤一格外是背景色；棋盤頂點處留白（inset 後四塊都退離頂點）
check("棋盤左上外側是背景",
      px(*gui.world_to_screen(*view.to_world(-1.0, -1.0))) == bg)
check("棋盤右側外是背景",
      px(*gui.world_to_screen(*view.to_world(4.5, 2.0))) == bg)
check("棋盤左上頂點處留白",
      px(*gui.world_to_screen(*view.to_world(0.02, 0.02))) != blue)

# 5) 覆蓋率量級：64 塊各 1/4 格、inset 收縮 f²、再扣掉邊框寬帶，
#    滑塊色應落在棋盤面積的 45%~75% 之間
n_blue_final = int((arr == blue).all(axis=2).sum())
board_px = (4 * view.cell_size * gui.zoom) ** 2
ratio = n_blue_final / board_px
check(f"滑塊色覆蓋率 {ratio:.1%}（{n_blue_final}/{int(board_px)}），期望 45%~75%",
      0.45 < ratio < 0.75)

print()
if _failures:
    print(f"共 {len(_failures)} 項失敗:")
    for n in _failures:
        print("  -", n)
    sys.exit(1)
print("全部通過")
