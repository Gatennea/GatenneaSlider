# -*- coding: utf-8 -*-
"""米字格 GUI 無頭測試（Stage M1 靜態預覽 + M2 兩次觸控互動）。

執行：python test/_test_mi_gui.py
覆蓋：建局入口（new_mi_puzzle）的形態旗標與判勝、謎題鍵/標籤/預設打勾、
      相機（米字格包圍盒是矩形但世界座標無 gap 間距）、draw_board 米字分支
      真的畫出了東西、M2 的兩次觸控（第一下選縫、第二下按住滑塊拖動才提交；
      只按不拖 = 選組，方向留給虛擬鍵盤）、
      打亂、縫隙/滑塊命中、拖拽起點記錄與無縫不跟隨、自動求解被攔並提示、
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


# —— 未選縫隙時一律不動，並說明要先點選縫隙 ——
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

# —— 兩次觸控：第一下選縫、第二下「按住並拖動」才提交 ——
from game_mi import (  # noqa: E402
    DIRECTIONS as MI_DIRECTIONS,
    GAP_DIRECTIONS as MI_GAP,
    mi_key,
    side_of,
)


def gaps_of(gt):
    """某一族出現過的全部 line（保持 all_gaps 的順序、去重）。"""
    return list(dict.fromkeys(l for (g, l) in gui.game.all_gaps() if g == gt))


def seam_point(gt, line):
    """縫線段 30% 處的世界座標（第一下的落點）；None = 沒有線段。

    線段中點常落在格角/格心（多條單位邊等距 0），那時命中的是平手裁決而
    不是這條縫本身，故取 30% 處。
    """
    seg = view.gap_segment(gt, line, hull)
    if seg is None:
        return None
    return (seg[0][0] + (seg[1][0] - seg[0][0]) * 0.3,
            seg[0][1] + (seg[1][1] - seg[0][1]) * 0.3)


def dir_vec(letter, cells=1.0):
    """沿方向字母拖 cells 格的屏幕位移向量。

    「一格」按該字母在 (行,列) 上的位移算：橫豎 = 1、斜向 = ½。
    """
    dr, dc = MI_DIRECTIONS[letter]
    s = view.cell_size * gui.zoom
    return (dc * s * cells, dr * s * cells)


def normal_vec(gt, sign, cells=1.0):
    """沿該族法向拖 cells 格的屏幕位移向量。"""
    n = gui.MI_GAP_AXES[gt][1]
    s = view.cell_size * gui.zoom
    return (n[0] * sign * s * cells, n[1] * sign * s * cells)


def drag_dir(gt, line, blk, vec):
    """點縫 → 按 blk → 沿 vec（屏幕像素）拖 → 鬆手。回傳鎖定的方向字母。

    只關心定向：拖的量不給足半格，鬆手不提交，棋盤保持原樣，接著做下一組
    手勢時落點還對得上同一塊。沒進跟隨（純法向拖動）回 None。
    """
    at = seam_point(gt, line)
    if at is None:
        return None
    if gui.selected_gap != (gt, line):
        # 已選中同一條縫時不能再點——那一下是「取消選中」
        ax, ay = gui.world_to_screen(*at)
        fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 1, 'pos': (int(ax), int(ay))}))
        if gui.selected_gap != (gt, line):
            # 上一處選中的是別條縫：第一下只是把它取消，再點一次才選上
            fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                    {'button': 1, 'pos': (int(ax), int(ay))}))
        if gui.selected_gap != (gt, line):
            return None
    bsx, bsy = gui.world_to_screen(*view.piece_center(*mi_key(blk)))
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(bsx), int(bsy))}))
    if gui.selected_block is not blk:
        return None
    tx, ty = int(round(bsx + vec[0])), int(round(bsy + vec[1]))
    fire(pygame.event.Event(pygame.MOUSEMOTION,
                            {'pos': (tx, ty), 'rel': (0, 0),
                             'buttons': (1, 0, 0)}))
    got = gui.drag_follow_direction if gui.drag_following else None
    fire(pygame.event.Event(pygame.MOUSEBUTTONUP,
                            {'button': 1, 'pos': (tx, ty)}))
    return got


def choose_pair(gt):
    """給定縫族找一組 (line, block, 方向)：按著它拖一格真能提交一步。

    條件：縫上落點自己命中這條縫、這一塊所在的組沿該方向滑得動。實心棋盤
    上多數組合會被擋住或移完斷開，逐個試到走得動的為止。
    """
    for line in gaps_of(gt):
        at = seam_point(gt, line)
        if at is None:
            continue
        sx, sy = gui.world_to_screen(*at)
        if gui.get_gap_at_pos(int(sx), int(sy)) != (gt, line):
            continue
        for direction in (gui.MI_GAP_AXES[gt][2], gui.MI_GAP_AXES[gt][3]):
            for blk in gui.game.blocks:
                gui.game.opt(gt, line, blk)
                movable = bool(
                    gui.game.try_move_ex(direction, gui.current_step)[0])
                gui.game._clear_selection()
                if movable:
                    return line, blk, direction
    return None, None, None


def run_two_touch(gt, line, blk, direction):
    """完整跑一遍「第一下選縫 → 按住塊拖一格 → 鬆手提交」，回傳是否全合預期。"""
    key = mi_key(blk)
    at = seam_point(gt, line)
    asx, asy = gui.world_to_screen(*at)
    ok = check(f"{gt} {line}：縫上落點自己命中該縫",
               gui.get_gap_at_pos(int(asx), int(asy)) == (gt, line))
    step = gui.current_step
    dr, dc = MI_DIRECTIONS[direction]
    bsx, bsy = gui.world_to_screen(*view.piece_center(*key))
    # 預先算好這一次的選中組（opt 只置標誌、不動位置），再清掉重來，
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
    # 1) 第一下：點在縫上 → 選中縫隙
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(asx), int(asy))}))
    ok &= check(f"{gt} {line}：第一下選中該縫", gui.selected_gap == (gt, line))
    ok &= check(f"{gt} {line}：選縫後未選塊", gui.selected_block is None)
    ok &= check(f"{gt} {line}：選縫時沒有動過棋盤", gui.is_solved() is True)
    # 2) 第二下：按在塊上 → 只選中滑塊組，還不提交
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(bsx), int(bsy))}))
    opted = set(mi_key(b) for b in gui.game.blocks if b.be_opted)
    ok &= check(f"{gt} {line}：第二下選中了滑塊組（{len(opted)} 塊）",
                len(opted) == len(before) > 0)
    ok &= check(f"{gt} {line}：按下還沒提交（步數仍是 0）", gui.step_count == 0)
    ok &= check(f"{gt} {line}：提示「选中滑块组 共N个」",
                gui.macro_notify_msg == f"选中滑块组 共{len(opted)}个",
                gui.macro_notify_msg or '')
    # 3) 沿切向拖一步（拖的量按 current_step 給）→ 鬆手才提交
    vx, vy = dir_vec(direction, step)
    tx, ty = int(round(bsx + vx)), int(round(bsy + vy))
    fire(pygame.event.Event(pygame.MOUSEMOTION,
                            {'pos': (tx, ty), 'rel': (0, 0),
                             'buttons': (1, 0, 0)}))
    ok &= check(f"{gt} {line}：進了跟隨且方向鎖定 {direction}",
                gui.drag_following and gui.drag_follow_direction == direction,
                f"方向={getattr(gui, 'drag_follow_direction', None)}")
    fire(pygame.event.Event(pygame.MOUSEBUTTONUP, {'button': 1, 'pos': (tx, ty)}))
    moved = set(mi_key(b) for b in gui.game.blocks if b.be_opted)
    ok &= check(f"{gt} {line}：鬆手後步數 = 1（實得 {gui.step_count}）",
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
    # 4) 第三下點同一條縫 → 取消選中
    #    螢幕座標必須重新投影：滑出棋盤的組會讓 ensure_blocks_visible 平移
    #    鏡頭，移動前記下的像素已經指到別的世界點上（米字格組經常半幅出界）
    asx, asy = gui.world_to_screen(*at)
    ok &= check(f"{gt} {line}：移後同一世界點仍命中該縫",
                gui.get_gap_at_pos(int(asx), int(asy)) == (gt, line))
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(asx), int(asy))}))
    ok &= check(f"{gt} {line}：再點同一條縫取消選中", gui.selected_gap is None)
    return ok


# 四族縫各跑一遍（方向來自位移向量在切向上的投影，四族的切向軸互不相同）
for gt in ('h', 'v', 'd1', 'd2'):
    gui.new_mi_puzzle(6, 6, 2)
    view = gui._mi_view()
    hull = view.board_hull(gui.game.positions())
    line, blk, expect = choose_pair(gt)
    check(f"{gt} 族有可用的「縫＋塊＋方向」組合", blk is not None,
          f"實得 line={line} 方向={expect}")
    if blk is not None:
        run_two_touch(gt, line, blk, expect)

# —— 回歸：提交一次移動後，單擊滑塊只換選組、不再滑動 ——
# 曾經的症狀（舊的「兩下點擊即提交」時代）：提交一次移動後選中態還留著，
# 之後每次單擊滑塊都拿上一記落點重新定向，出現「只是點了幾下、滑塊自己
# 滑走」的幽靈移動。現在第二下必須「按住並拖動」才有位移，單擊只選組。
gui.new_mi_puzzle(6, 6, 2)
view = gui._mi_view()
hull = view.board_hull(gui.game.positions())
line, blk, expect = choose_pair('h')
check("回歸場景有可用組合", blk is not None)
if blk is not None:
    run_two_touch('h', line, blk, expect)
    check("兩次觸控（按著拖）提交了一步", gui.step_count == 1)
    # run_two_touch 末尾點了同一條縫取消選中；繼續操作要把選中態撿回來
    at = seam_point('h', line)
    ax, ay = gui.world_to_screen(*at)
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(ax), int(ay))}))
    check("同一条縫可重新選中", gui.selected_gap == ('h', line))
    check("重新點縫 = 新的選中會話，上一組的選中標誌被清掉",
          all(b.be_opted is False for b in gui.game.blocks))
    # 選中態還在的時候再單擊一塊（沒有重新點縫、也沒有拖）→ 只換選組，
    # 不動棋盤
    other = next((b for b in gui.game.blocks if not b.be_opted), None)
    check("找得到選中組之外的塊", other is not None)
    if other is not None:
        osx, osy = gui.world_to_screen(*view.piece_center(*mi_key(other)))
        check("那塊的內心不會誤選到縫",
              gui.get_gap_at_pos(int(osx), int(osy)) is None)
        gui.macro_notify_msg = ''
        fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 1, 'pos': (int(osx), int(osy))}))
        n_other = len([b for b in gui.game.blocks if b.be_opted])
        check("提交後單擊滑塊不再滑動", gui.is_solved() is False
              and gui.step_count == 1)
        check("單擊只換選組並提示「选中滑块组 共N个」",
              gui.macro_notify_msg == f"选中滑块组 共{n_other}个",
              gui.macro_notify_msg or '')

# —— 定向校驗：切向正負給方向；純法向拖動沒有方向 ——
# 一律走真實手勢（點縫 → 按塊 → 拖 → 鬆手），不再直接調內部定向函式：
# 方向是「拖」出來的，不是「兩下落點差」算出來的，測試也要照這條路走。
# 每次只拖 0.4 格（不到半格）→ 鬆手不提交，棋盤保持原樣，下一組手勢的
# 落點還對得上同一塊。
for gt in ('h', 'v', 'd1', 'd2'):
    gui.new_mi_puzzle(6, 6, 2)
    view = gui._mi_view()
    hull = view.board_hull(gui.game.positions())
    line, blk, _expect = choose_pair(gt)
    check(f"{gt}：有可用組合做定向校驗", blk is not None)
    if blk is None:
        continue
    pos_d, neg_d = gui.MI_GAP_AXES[gt][2], gui.MI_GAP_AXES[gt][3]
    for want in (pos_d, neg_d):
        d = drag_dir(gt, line, blk, dir_vec(want, 0.4))
        check(f"{gt}：拖向 {want} 那一側 → {want}", d == want, f"實得 {d}")
    check(f"{gt}：兩次定向手勢都沒提交", gui.step_count == 0,
          f"step_count={gui.step_count}")
    # 純法向拖動：切向投影 = 0，落在瞄準容差裡 → 沒有方向，組仍留在選中態
    sn = 1.0 if side_of(gt, line, mi_key(blk)) == 1 else -1.0
    d = drag_dir(gt, line, blk, normal_vec(gt, sn, 2.0))
    check(f"{gt}：純法向拖動拿不到方向", d is None, f"實得 {d}")
    check(f"{gt}：純法向拖動後滑塊組還在選中態",
          len([b for b in gui.game.blocks if b.be_opted]) > 0)

# —— 與選中縫隙不平行的方向被拒 ——
gui.selected_gap = ('h', 2)
gui.selected_block = gui.game.blocks[0]
gui.macro_notify_msg = ''
check("不平行方向被拒", gui.move_selected_blocks('w', 1) is False)
check("不平行方向有提示", '不平行' in (gui.macro_notify_msg or ''), gui.macro_notify_msg or '')

# —— 拖拽起點照記，但沒有預選縫隙就沒有切向可投影（米字格無單次觸控）——
# 米字格的方向來自成一次「按住並拖動」的位移向量，不記起點等於手勢不存在
gui.selected_gap = None
gui.selected_block = None
gui.macro_notify_msg = ''
b0 = gui.game.blocks[0]
b0x, b0y = gui.world_to_screen(*view.piece_center(*mi_key(b0)))
fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                        {'button': 1, 'pos': (int(b0x), int(b0y))}))
check("拖拽記下了起點", gui._mouse_drag_state is not None)
check("未選縫隙時不進跟隨（沒有單次觸控這條捷徑）",
      gui._init_drag_follow(b0, 40, 0) is False)
before_no_gap = set(gui.game.positions())
step_no_gap = gui.step_count
fire(pygame.event.Event(pygame.MOUSEBUTTONUP,
                        {'button': 1, 'pos': (int(b0x) + 40, int(b0y))}))
check("不進跟隨也不滑動（單擊只選組）",
      set(gui.game.positions()) == before_no_gap
      and gui.step_count == step_no_gap)
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
