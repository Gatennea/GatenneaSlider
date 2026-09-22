# -*- coding: utf-8 -*-
"""米字格 H4：規劃 §5 手動驗收清單裡「機器能判」的那幾條，先過一遍再交人眼。

清單原文（plan-mi-zige-diagonal-unit.md §5）：
  1. 6×6 等級1 新建 → 點一條 "\" 縫 → 點一側的塊 → 確認只移動一格，形狀不散。
  4. 把另一半也朝同方向推一格 → 橫豎縫復活的數目與枚舉一致。
  5. 撤銷/重做整段 → 位置與動畫位移對得上。
  6. 打亂一局 → 撤銷回建局態 → 判勝；再故意把一條斜縫兩半朝同向各推一格 →
     **錯半格的矩形也判勝**。
  7. 存檔 → 讀檔：錯位態下存讀都要成功。

第 2、3 條（縫隙枚舉、被鎖縫的提示）已由 _test_mi_h2_view / _test_mi_h3_hint
逐條釘死，這裡把它們的結論當已知事實引用，不重複量。

本文件走**真實玩家路徑**（兩次觸控的鼠標點擊 + move_selected_blocks + 動畫
開著），不是直接撥引擎狀態：驗收要問的就是「點下去會怎樣」。

执行：python test/_test_mi_h4_acceptance.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_mi import DIRECTIONS, lattice_of, side_of  # noqa: E402

_failures = []
BUILD = {(r, c, q) for r in range(6) for c in range(6) for q in 'NESW'}
BASE = {'h': 5, 'v': 5, 'd1': 11, 'd2': 11}    # 對齊態各族縫數（規劃 §1.3）


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def fire(evt):
    pygame.event.post(evt)
    gui.handle_events()


def click(sx, sy):
    """一次點擊（只發 BUTTONDOWN；位移 0，不會進拖拽分支）。"""
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(sx), int(sy))}))


gui = SliderGUI(m=6, n=6, step=1)
gui.save_readonly_flag = False        # 無頭只讀陷阱：載入後 new_puzzle 會靜默失敗
gui.game_mode = 'practice'
view = gui._mi_view()


def seam_points(gap):
    """縫隙與棋形凸包相交那一段上的幾個採樣點（世界座標，t = 0.2…0.8）。

    只取中點不夠：錯位態之後凸包與塊的位置都變了，中點可能正好壓在別的
    族的交匯處，玩家點下去會選到鄰近的縫。逐個 t 試，第一個真能被 gap_at
    判成這條縫的點才是「玩家點得中」的位置。
    """
    seg = view.gap_segment(gap[0], gap[1], view.board_hull(gui.game.positions()))
    assert seg is not None, gap
    (x1, y1), (x2, y2) = seg
    return [(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t) for t in (0.2, 0.35, 0.5, 0.65, 0.8)]


def drain_animation():
    """播完當前動畫，回傳它的位移（格）——提交後 _anim_dr/_anim_dc 會被清掉。

    進度走 `pygame.time.get_ticks()`，所以每幀之間必須真的睡一會兒，
    緊密自旋只會在 progress=0 的空轉裡耗盡保護次數（無頭環境同樣適用）。
    """
    import time
    delta = (gui._anim_dr, gui._anim_dc)
    guard = 0
    while gui.animating and guard < 500:
        delta = (gui._anim_dr, gui._anim_dc)
        gui.update_animation()
        guard += 1
        if gui.animating:
            time.sleep(0.02)
    return delta


def click_seam(gap):
    """第一下觸控：點縫隙（沿線段找第一個真點得中的位置）。回傳是否選中。

    同一條縫已經處於選中態時（上一次移動之後縫隙不會自動取消），產品行為
    是「再點一次 = 取消選中」，所以要多點一下才重新選上——這裡照玩家的做
    法連點，第二下才真正選中。
    """
    cells = gui.game.positions()
    for (wx, wy) in seam_points(gap):
        if view.gap_at(wx, wy, cells) != gap:
            continue
        for _ in range(2):
            click(*gui.world_to_screen(wx, wy))
            if gui.selected_gap == gap:
                return True
        return gui.selected_gap == gap
    return False


def click_cell(key):
    """第二下觸控：點某一塊的內心（玩家瞄的就是這裡）。"""
    wx, wy = view.incenter(*key)
    click(*gui.world_to_screen(wx, wy))


def two_touch(gap, direction, side=None):
    """完整的兩次觸控：點縫 → 點 direction 那一側的一塊。

    點哪一塊純由「第二下落點 − 第一下落在縫切向上的符號」決定（與
    `_MI_GAP_AXES` 同判據）：這裡先按 side 過濾，再取切向投影最接近 0 的
    一塊（貼著縫、最像玩家會點的位置）。回傳 (塊, 提示)；(None, 提示)
    表示沒點成。
    """
    if not click_seam(gap):
        return None, '縫隙沒選中（點擊被別的物品吃掉）'
    # 定向用的第一下落點必須是真實錨點（_mi_gap_point），不是縫的中點
    # ——中點可能壓在別的族的交匯處，玩家實際點到的是旁邊那個位置
    first = getattr(gui, '_mi_gap_point', None) or seam_points(gap)[2]
    tangent, _normal, pos_dir, _neg = gui.MI_GAP_AXES[gap[0]]
    if direction == pos_dir:
        sign = 1
    elif direction == _neg:
        sign = -1
    else:
        return None, f'{direction} 不平行於 {gap[0]} 縫'
    cands = [k for k in gui.game.positions()
             if (side is None or side_of(gap[0], gap[1], k) == side)]
    best = None
    for key in sorted(cands):
        px, py = view.incenter(*key)
        proj = (px - first[0]) * tangent[0] + (py - first[1]) * tangent[1]
        if proj * sign <= 0:
            continue
        if best is None or abs(proj) < abs(best[1]):
            best = (key, proj)
    if best is None:
        return None, f'side={side} 找不到朝 {direction} 那一側的塊'
    click_cell(best[0])
    return best[0], gui.macro_notify_msg


def one_side(gap, direction, side):
    """點缝 → 點指定側的一塊 → 提交一格（動畫開著，播完才回）。"""
    key, msg = two_touch(gap, direction, side)
    if key is None:
        return None, msg, None
    return key, msg, drain_animation()


def move_through(gap, direction, side):
    """虛擬鍵盤路徑：選縫 + 選該側一塊 + move_selected_blocks（播完動畫）。"""
    fam, line = gap
    for key in sorted(k for k in gui.game.positions()
                      if side_of(fam, line, k) == side):
        ref = gui.game.block_at(key)
        if ref is None:
            continue
        gui.selected_gap = (fam, line)
        gui.selected_block = ref
        gui.game.opt(fam, line, ref)
        if not [b for b in gui.game.blocks if b.be_opted]:
            continue
        if gui.move_selected_blocks(direction, 1):
            return key, gui.macro_notify_msg, drain_animation()
    return None, gui.macro_notify_msg, None


def fam_counts():
    out = {'h': 0, 'v': 0, 'd1': 0, 'd2': 0}
    for fam, _line in gui.game.all_gaps():
        if fam in out:
            out[fam] += 1
    return out


def lat_set():
    return {'B' if lattice_of(k) else 'A' for k in gui.game.positions()}


def moved_group(before, after):
    """兩次位置集合之差：(挪走的塊, 新落點的塊)。"""
    return (before - after, after - before)


# ================================================================ §5-1 斜向一格
print("== §5-1：點 \\ 縫 → 點一側的塊，只移動一格 ==")
gui.new_mi_puzzle(6, 6, 1)
check("建局即對齊態、判還原", gui.is_solved() is True
      and gui._mi_shifted() is False)
before = set(gui.game.positions())
key, msg, delta = one_side(('d1', 6), 'x', side=1)
check("兩次觸控在 d1 line=6 上提交成功（動畫 300ms 播完）",
      key is not None, str(msg))
after = set(gui.game.positions())
gone, new = moved_group(before, after)
moved_side = side_of('d1', 6, next(iter(gone)))
side_all = {k for k in before if side_of('d1', 6, k) == moved_side}
other_side = 1 - moved_side
check(f"只有一整側被搬走（{len(gone)} 塊 = 該側全部 {len(side_all)} 塊）",
      gone == side_all, f"{len(gone)} 塊、該側共 {len(side_all)} 塊")
check("搬走的那一批全在縫的同一側",
      len({side_of('d1', 6, k) for k in gone}) == 1,
      str(sorted({side_of('d1', 6, k) for k in gone})))
check("新落點 = 原位置 + (½,½)（一格，不是兩格）",
      new == {(r + 0.5, c + 0.5, q) for (r, c, q) in gone}, str(sorted(new)[:3]))
check("動畫位移 = (½,½)（與提交一致）", delta == (0.5, 0.5), str(delta))
check("另一側一塊都沒動", (before - gone) == (after - new),
      f"差 {len((before - gone) ^ (after - new))} 塊")
check("走完整盤落進兩個晶格（錯位態）", lat_set() == {'A', 'B'}, str(sorted(lat_set())))
check("一步之後不是還原態（形狀被錯開）", gui.is_solved() is False)
check("橫豎縫大幅減少但沒全空（規劃 §1.3：h 剩 3、v 剩 2）",
      fam_counts() == {'h': 3, 'v': 2, 'd1': 11, 'd2': 11}, str(fam_counts()))

# ================================================================ §5-4/6 錯回來
print("== §5-4/6：另一半朝同向再推一格 → 復活 + 錯半格也判勝 ==")
key2, msg2, delta2 = move_through(('d1', 6), 'x', side=other_side)
check(f"另一半（side{other_side}）也朝同向推一格", key2 is not None, str(msg2))
check("第二段的動畫位移同樣是 (½,½)", delta2 == (0.5, 0.5), str(delta2))
check(f"各族縫數回到對齊態 {BASE}", fam_counts() == BASE, str(fam_counts()))
check("整盤落在單一晶格（B：錯開半格但均勻）",
      lat_set() == {'B'}, str(sorted(lat_set())))
check("§5-6：錯半格的矩形也判勝", gui.is_solved() is True)
check("沒有畫得出來卻選不動的橫豎縫",
      not [g for g in gui.game.all_gaps()
           if g[0] in ('h', 'v') and not gui.game.is_valid_gap(*g)])
snap_shifted = set(gui.game.positions())
steps_after_moves = gui.step_count

# ================================================================ §5-5 撤銷/重做
print("== §5-5：撤銷/重做整段，位置與動畫位移對得上 ==")
gui.animation_duration = 300          # 決議 4：時長不變（一直是 300）
gui.new_mi_puzzle(6, 6, 1)
deltas = []
for side in (1, 0):
    key, msg, delta = one_side(('d1', 6), 'x', side=side)
    check(f"兩次觸控 side{side} x", key is not None and delta is not None,
          f"{msg} / {delta}")
    deltas.append(delta)
check("兩步之後整盤錯到 B 晶格", lat_set() == {'B'}, str(sorted(lat_set())))
check("兩步之後判勝（錯半格矩形）", gui.is_solved() is True)
for i, delta in enumerate(deltas):
    check(f"第 {i + 1} 段動畫位移 = (½,½)", delta == (0.5, 0.5), str(delta))
snap2 = set(gui.game.positions())
steps2 = gui.step_count

gui.undo()
undo_delta = drain_animation()
check("撤銷一步的動畫位移 = −(½,½)", undo_delta == (-0.5, -0.5), str(undo_delta))
check("撤銷一步後回到混合晶格", lat_set() == {'A', 'B'}, str(sorted(lat_set())))
gui.undo()
drain_animation()
check("撤銷兩步回到建局態（對齊、判勝、144 塊）",
      set(gui.game.positions()) == BUILD and gui._mi_shifted() is False
      and gui.is_solved() is True and len(gui.game.blocks) == 144)
gui.redo()
drain_animation()
gui.redo()
drain_animation()
check("重做兩步回到錯半格矩形", set(gui.game.positions()) == snap2,
      f"差 {len(set(gui.game.positions()) ^ snap2)} 塊")
check("重做後仍判勝", gui.is_solved() is True)
check("步數 = 移動次數（每步記 1，不累加 step）",
      gui.step_count == steps2, f"{gui.step_count} vs {steps2}")

# ================================================================ §5-7 存讀檔
print("== §5-7：錯位態存檔 → 讀檔 ==")
data = gui._build_save_data()
check("存檔為 v2 且 type=mi", data['version'] == 2
      and data['puzzle']['type'] == 'mi')
gui.new_puzzle(5, 5, 2)          # 先切到方形，確認載入會正確分派
gui._load_save_data(data)
check("讀檔後 mi_mode 復原、三角形旗標為假",
      gui.mi_mode is True and gui.triangle_mode is False)
check("讀檔後位置一塊不差（錯位態原樣）",
      set(gui.game.positions()) == snap2,
      f"差 {len(set(gui.game.positions()) ^ snap2)} 塊")
check("讀檔後仍是錯位態且判勝", gui._mi_shifted() is True
      and gui.is_solved() is True)
check("讀檔後各族縫數仍是對齊態的數", fam_counts() == BASE, str(fam_counts()))

print()
if _failures:
    print(f"未通過 {len(_failures)} 項：")
    for f in _failures:
        print("  -", f)
    sys.exit(1)
print("全部通過")
