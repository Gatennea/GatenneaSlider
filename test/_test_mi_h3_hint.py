# -*- coding: utf-8 -*-
"""米字格 H3 交互收尾：錯位態的話要說清楚，別讓玩家對著一條選不動的縫發呆。

規劃 plan-mi-zige-diagonal-unit.md 表 19/20 + §5 手動驗收第 3 條：
「點一條被鎖死的橫豎鍵 → 應得到『錯位了，先沿斜向滑回去』類提示，
而不是無反應」。斜向一格（±(½,½)）之後一半的塊落進 B 晶格，橫豎縫
大量失效——半整數層級的格邊整條穿過塊的內部，畫面畫得出來、也點得到，
就是選不動。舊代碼對這種點擊要麼毫無反應，要麼落進兩次觸控的第二下
分支、拿上一記落點瞎猜一個方向把棋盤滑走。

本文件守四件事：
  1. 選中縫隙時把「這一族的一格有多遠」說清楚（橫豎 = 一條格邊，
     斜向 = 半個格身的斜向距離）；
  2. 點到選不動的縫：給出「這族還剩幾條、該怎麼辦」的提示，且不動棋盤；
  3. 錯位態按橫豎方向鍵（含還沒選縫隙時）：按該族實際剩餘條數說，
     對齊態的提示逐字不變；
  4. 引擎擋下的橫豎滑動附一句「可先沿斜向滑回去」；提示靠的那個事實
     （任一半再沿斜向推一格 → 單一晶格、橫豎縫全數復活）逐條核對。

执行：python test/_test_mi_h3_hint.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_mi import mi_vertices, side_of  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def fire(evt):
    pygame.event.post(evt)
    gui.handle_events()


def click(sx, sy):
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(sx), int(sy))}))


def move_through(gap, direction, side):
    """沿一條縫把某一側推動一格（與虛擬鍵盤/第二下觸控同一条路徑）。"""
    fam, line = gap
    ref = gui.game.block_at(sorted(k for k in gui.game.positions()
                                   if side_of(fam, line, k) == side)[0])
    gui.selected_gap = (fam, line)
    gui.selected_block = ref
    gui.game.opt(fam, line, ref)
    n_sel = len([b for b in gui.game.blocks if b.be_opted])
    ok = gui.move_selected_blocks(direction, 1)
    return ok, gui.macro_notify_msg, n_sel


def edge_midpoints():
    """全部單位邊的中點（世界座標）——玩家點得到的就是這些位置。"""
    cells = gui.game.positions()
    out = []
    for k in sorted(cells):
        for i in range(3):
            p = view.to_world(*mi_vertices(*k)[i])
            t = view.to_world(*mi_vertices(*k)[(i + 1) % 3])
            out.append(((p[0] + t[0]) / 2.0, (p[1] + t[1]) / 2.0))
    return out


def locked_seams():
    """點得到卻選不動的縫 {gap: (世界座標)}：錯位態的半整數橫豎縫。"""
    cells = gui.game.positions()
    out = {}
    for (mx, my) in edge_midpoints():
        g = view.gap_at(mx, my, cells)
        if g is None or gui.game.is_valid_gap(*g):
            continue
        if gui._mi_locked_seam(g, cells):
            out.setdefault(g, (mx, my))
    return out


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False        # 無頭只讀陷阱：載入後 new_puzzle 會靜默失敗
gui.new_mi_puzzle(6, 6, 2)
view = gui._mi_view()

# ================================================================ 對齊態基準
print("== 對齊態：各族一條不少、沒有鎖死的縫 ==")
check("對齊態不是錯位態", gui._mi_shifted() is False)
BASE = gui._mi_fam_counts()
check(f"對齊態各族縫數 {BASE}",
      BASE == {'h': 5, 'v': 5, 'd1': 11, 'd2': 11}, str(BASE))
check("對齊態沒有鎖死的縫", not locked_seams(), str(sorted(locked_seams())))

# ================================================================ 選縫提示
print("== 選中縫隙時把「一格有多遠」說清楚 ==")
check("米字格四族的距離說明都在",
      gui.MI_STEP_NOTE == {
          'h': '横向一格 = 一条格边', 'v': '纵向一格 = 一条格边',
          'd1': '斜向一格 = 半个格身的斜向距离',
          'd2': '斜向一格 = 半个格身的斜向距离'},
      str(gui.MI_STEP_NOTE))


def click_seam(fam, line):
    """點一條縫的中點，回傳選中的縫與當時的提示。

    沿線段取幾個採樣點：線段中點可能正好壓在別的族的交點上（等距時
    gap_at 取長邊，棋盤正中心四族相交就是這種情形），那時選中的不是
    目標縫；換個位置再點即可。
    """
    seg = view.gap_segment(fam, line, view.board_hull(gui.game.positions()))
    check(f"{fam} line={line} 有可點的線段", seg is not None)
    if seg is None:
        return None, ''
    (x0, y0), (x1, y1) = seg
    for t in (0.2, 0.35, 0.5, 0.65, 0.8):
        sx, sy = gui.world_to_screen(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
        gui.macro_notify_msg = ''
        gui.selected_gap = None
        click(sx, sy)
        if gui.selected_gap == (fam, line):
            return gui.selected_gap, gui.macro_notify_msg
    return gui.selected_gap, gui.macro_notify_msg


gap, msg = click_seam('h', 2)
check("點橫縫選中它", gap == ('h', 2), str(gap))
check("橫縫提示附上距離（一格 = 一條格邊）",
      msg == "选中横向缝隙（横向一格 = 一条格边）", msg)
gap, msg = click_seam('d1', 6)
check("點「\\」縫選中它", gap == ('d1', 6), str(gap))
check("斜縫提示附上距離（一格 = 半個格身的斜向距離）",
      msg == "选中主对角缝隙（斜向一格 = 半个格身的斜向距离）", msg)
gap, msg = click_seam('d2', 6)
check("點「/」縫選中它", gap == ('d2', 6), str(gap))
check("副對角縫用同一句斜向說明",
      msg == "选中副对角缝隙（斜向一格 = 半个格身的斜向距离）", msg)

# —— 對齊態點棋形外沿的縫：一側沒有塊，與舊版一致地安靜捨棄 ——
gui.macro_notify_msg = ''
gui.selected_gap = None
gui.selected_block = None
for b in gui.game.blocks:
    b.be_opted = False
outer = None
for (mx, my) in edge_midpoints():
    if abs(my) < 1e-9:
        outer = (mx, my)
        break
check("找得到棋形外沿的格邊", outer is not None)
if outer is not None:
    sx, sy = gui.world_to_screen(*outer)
    snap = set(gui.game.positions())
    click(sx, sy)
    check("對齊態點外沿縫不出提示、不選中、不動棋盤",
          gui.macro_notify_msg == '' and gui.selected_gap is None
          and set(gui.game.positions()) == snap,
          f"msg={gui.macro_notify_msg!r} gap={gui.selected_gap}")

# ================================================================ 錯位態
print("== 錯位態：一次斜向一格之後 ==")
ok, msg, n_sel = move_through(('d1', 6), 'x', 1)
check(f"沿 d1 line=6 走 x（選中 {n_sel} 塊）成功", ok, msg)
check("現在是錯位態", gui._mi_shifted() is True)
counts = gui._mi_fam_counts()
check(f"錯位態各族縫數 {counts}（規劃 §1.3：h 剩 3、v 剩 2）",
      counts == {'h': 3, 'v': 2, 'd1': 11, 'd2': 11}, str(counts))
locked = locked_seams()
check(f"點得到卻選不動的縫 {len(locked)} 條（橫豎都有、含半整數線）",
      len(locked) >= 6 and any(isinstance(l, float) for (t, l) in locked),
      str(sorted(locked)))

# —— 點這些縫：提示 + 不動棋盤 + 不改選中態 ——
bad_msg, bad_move, bad_gap = [], [], []
for g in sorted(locked):
    mx, my = locked[g]
    sx, sy = gui.world_to_screen(mx, my)
    gui.macro_notify_msg = ''
    gui.selected_gap = ('d1', 6)
    gui.selected_block = None
    snap = set(gui.game.positions())
    click(sx, sy)
    m = gui.macro_notify_msg or ''
    want = ('这条缝选不动（错位态切在块里）：'
            + gui._mi_hv_left(g[0]))
    if m != want:
        bad_msg.append((g, m))
    if set(gui.game.positions()) != snap:
        bad_move.append(g)
    if gui.selected_gap != ('d1', 6):
        bad_gap.append(g)
check(f"{len(locked)} 條鎖死的縫都給出对症的提示（異常 {len(bad_msg)}）",
      not bad_msg, str(bad_msg[:3]))
check(f"點鎖死的縫一步都不動（異常 {len(bad_move)}）", not bad_move,
      str(bad_move[:3]))
check(f"點鎖死的縫不改選中態（異常 {len(bad_gap)}）", not bad_gap,
      str(bad_gap[:3]))

# —— 虛擬鍵盤：方向與選中縫不平行 ——
gui.selected_gap = ('d1', 6)
gui.selected_block = None
gui.macro_notify_msg = ''
gui._vk_trigger_action('move_up')
check("錯位態選著對角縫按 ↑：按縱向實際剩餘條數說",
      gui.macro_notify_msg ==
      "移动方向与缝隙方向不匹配（错位态：纵向缝隙还剩 2 条，先点选其中一条）",
      repr(gui.macro_notify_msg))
snap = set(gui.game.positions())
gui._vk_trigger_action('move_left')
check("錯位態選著對角縫按 ←：按橫向實際剩餘條數說",
      gui.macro_notify_msg ==
      "移动方向与缝隙方向不匹配（错位态：横向缝隙还剩 3 条，先点选其中一条）",
      repr(gui.macro_notify_msg))
check("這兩次按鍵都沒動棋盤", set(gui.game.positions()) == snap)

# —— 虛擬鍵盤：還沒選縫隙 ——
gui.selected_gap = None
gui.selected_block = None
for b in gui.game.blocks:
    b.be_opted = False
gui.macro_notify_msg = ''
gui._vk_trigger_action('move_left')
check("錯位態未選縫按 ←：連「該點哪條」一起交代",
      gui.macro_notify_msg ==
      "请先点选缝隙（错位态：横向缝隙还剩 3 条，先点选其中一条）",
      repr(gui.macro_notify_msg))

# —— 對齊態同樣的按法：提示逐字不變 ——
gui.new_mi_puzzle(6, 6, 2)
gui.selected_gap = ('h', 2)
gui.selected_block = None
gui.macro_notify_msg = ''
gui._vk_trigger_action('move_up')
check("對齊態不平行提示不變",
      gui.macro_notify_msg == "移动方向与缝隙方向不匹配",
      repr(gui.macro_notify_msg))
gui.selected_gap = None
gui.selected_block = None
gui.macro_notify_msg = ''
gui._vk_trigger_action('move_left')
check("對齊態未選縫提示不變", gui.macro_notify_msg == "请先点选缝隙",
      repr(gui.macro_notify_msg))

# ================================================================ 引擎擋下
print("== 錯位態：選得動的橫縫卻滑不動 ==")
# 兩步走到錯位態，且某一條橫縫選得動、滑下去會斷開（隨機搜索出來的最短
# 路徑，見提交說明；兩步都沿合法縫走，途中不碰任何非法狀態）
for (fam, line, d, side) in (('d2', 14, 'e', 0), ('v', 0.5, 's', 1)):
    ok, msg, n_sel = move_through((fam, line), d, side)
    check(f"鋪墊步 {fam} {line} {d} side{side}（選中 {n_sel} 塊）", ok, msg)
check("鋪墊後仍是錯位態", gui._mi_shifted() is True)
ok, msg, n_sel = move_through(('h', -0.5), 'a', 0)
check(f"h line=-0.5 走 a 選中 {n_sel} 塊卻被引擎擋下", not ok, msg)
check("擋下的提示附上錯位態的出路",
      msg == "滑动失败：移动后滑块会断开（错位态可先沿斜向滑回去）", repr(msg))
check("被擋時棋盤沒動", gui.is_solved() is False)

# ================================================================ 提示靠的事實
print("== 提示的出路是真的：任一半再沿斜向推一格 ==")
gui.new_mi_puzzle(6, 6, 2)
move_through(('d1', 6), 'x', 1)
mid = dict(locked_seams())
ok, msg, n_sel = move_through(('d1', 6), 'x', 0)
check(f"把另一半（{n_sel} 塊）也朝同向推一格", ok, msg)
after = gui._mi_fam_counts()
check(f"兩步之後各族縫數 {after} = 對齊態的 {BASE}", after == BASE, str(after))
check("兩步之後整盤落在單一晶格（錯位但均勻）",
      gui._mi_shifted() is True
      and {('B' if (r % 1 or c % 1) else 'A')
           for (r, c, _q) in gui.game.positions()} == {'B'})
check(f"鎖死的縫從 {len(mid)} 條歸零", not locked_seams(),
      str(sorted(locked_seams())))

print()
if _failures:
    print(f"未通過 {len(_failures)} 項：")
    for f in _failures:
        print("  -", f)
    sys.exit(1)
print("全部通過")
