# -*- coding: utf-8 -*-
"""米字格動畫無頭測試（M3 的第一筆：先還上規劃裡漏記的欠賬）。

執行：python test/_test_mi_animation.py
覆蓋：_move_delta 的米字格八向表（橫豎一格 = ±1 格邊、斜向一格 = ±½ 格邊）、
      draw_mi_board 的位移插值（原本沒有動畫分支，滑動是「凍結 300ms 再跳」）、
      斜向移動的撤銷/重做動畫與選中高亮（原本 delta=(0,0)，撤回時找不回原位，
      直接無動畫瞬移）。

無頭陷阱：測試開頭必須關 save_readonly_flag，否則載入後 new_puzzle 會靜默失敗。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_mi import (  # noqa: E402
    DIRECTIONS as MI_DIRECTIONS,
    GAP_DIRECTIONS as MI_GAP,
    MiSliderMatrix,
    mi_key,
)
from game_triangle import DIRECTIONS as TRI_DIRECTIONS  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = True
gui.animation_duration = 300
gui.save_readonly_flag = False
gui.new_mi_puzzle(6, 6, 2)
check("建局為米字格 6×6", isinstance(gui.game, MiSliderMatrix)
      and len(gui.game.blocks) == 144)

# ================================================================ 位移表
print("== _move_delta：米字格八向表 ==")
check("mi_mode 旗標在位", gui.mi_mode is True)
for d, (dr, dc) in MI_DIRECTIONS.items():
    for st in (1, 2, 3):
        got = gui._move_delta({'direction': d, 'step': st})
        check(f"_move_delta {d}×{st} = ({dr * st},{dc * st})，實得 {got}",
              abs(got[0] - dr * st) < 1e-9 and abs(got[1] - dc * st) < 1e-9)
# step 缺省時取 current_step
gui.current_step = 2
_dr, _dc = MI_DIRECTIONS['x']
got = gui._move_delta({'direction': 'x'})
check(f"_move_delta 省略 step 取 current_step=2，實得 {got}",
      abs(got[0] - _dr * 2) < 1e-9 and abs(got[1] - _dc * 2) < 1e-9)
# 合併快照的合成位移優先（方向可能不是單向）
got = gui._move_delta({'delta': [3, -2], 'direction': 'x', 'step': 2})
check(f"_move_delta 優先用合併 delta，實得 {got}", got == (3, -2))
gui.current_step = 1

# 別的形態分支不能被這筆改動帶壞
gui.triangle_mode = True
got = gui._move_delta({'direction': 'w', 'step': 2})
check(f"三角分支仍是六向表，實得 {got}",
      abs(got[0] - TRI_DIRECTIONS['w'][0] * 2) < 1e-9
      and abs(got[1] - TRI_DIRECTIONS['w'][1] * 2) < 1e-9)
gui.triangle_mode = False
gui.mi_mode = False
check("方形分支仍是四向表",
      gui._move_delta({'direction': 'a', 'step': 2}) == (0, -2))
gui.mi_mode = True


# ================================================================ 工具
def find_move(gt):
    """找一組 (縫, 塊, 方向)：opt 後這一側能沿該方向滑動一格。

    實心棋盤上多數組合會被擋住或移完斷開，逐個試到走得動的為止。
    """
    for (g, line) in gui.game.all_gaps():
        if g != gt:
            continue
        for blk in gui.game.blocks:
            gui.game.opt(g, line, blk)
            n_sel = len([b for b in gui.game.blocks if b.be_opted])
            if n_sel >= len(gui.game.blocks):
                gui.game._clear_selection()
                continue
            for d in MI_GAP[gt]:
                if gui.game.try_move_ex(d, 1)[0]:
                    gui.game._clear_selection()
                    return (g, line), blk, d
            gui.game._clear_selection()
    return None, None, None


def animate_and_spy(progress):
    """把動畫停在 progress，畫一幀，回傳這幀 piece_center 收到的全部座標。"""
    seen = []

    def spy(r, c, q):
        seen.append((r, c, q))
        return orig(r, c, q)

    view = gui._mi_view()
    orig = view.piece_center
    view.piece_center = spy
    try:
        gui.anim_progress = progress
        gui.draw_board()
    finally:
        view.piece_center = orig
    return seen


def _eq(a, b):
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return abs(a - b) < 1e-9


def has(seen, pos):
    """畫面上是否出現過這個 (r, c, q)（前兩項比大小，q 比字串）。"""
    return any(len(s) == len(pos) and all(_eq(a, b) for a, b in zip(s, pos))
               for s in seen)


# ================================================================ 插值
print("== draw_mi_board 插值（原本：凍結 300ms 後直接跳）==")
for gt in ('h', 'v', 'd1', 'd2'):
    gui.new_mi_puzzle(6, 6, 2)
    gui.game._clear_selection()
    gap, blk, d = find_move(gt)
    check(f"{gt} 族有可滑的組合", blk is not None, f"實得 {gap} {d}")
    if blk is None:
        continue
    dr, dc = MI_DIRECTIONS[d]
    gui.selected_gap = gap
    gui.selected_block = blk
    gui.animation_enabled = True
    gui.animation_duration = 300
    check(f"{gt}：移動進入動畫", gui.move_selected_blocks(d, 1) is True
          and gui.animating)
    n_anim = len(gui.anim_blocks)
    check(f"{gt}：動畫覆蓋 {n_anim} 塊", n_anim > 0)
    check(f"{gt}：動畫位移表記下 ({dr},{dc})",
          abs(gui._anim_dr - dr) < 1e-9 and abs(gui._anim_dc - dc) < 1e-9)

    starts = [tuple(p[:2]) + (p[2],) for p in gui.anim_start_pos]
    ends = [tuple(p) for p in gui.anim_end_pos]
    # ease_out(0.5)=0.75 → 中點位置 = 起點 + 0.75×位移
    t = gui.ease_out(0.5)
    mids = [(s[0] + dr * t, s[1] + dc * t, s[2]) for s in starts]

    seen = animate_and_spy(0.5)
    ok = all(has(seen, m) for m in mids)
    check(f"{gt}：半程畫在插值位置（起點+{t:.2f}×位移）", ok)
    check(f"{gt}：起點位置不再被畫（不是凍結）",
          not any(has(seen, s) for s in starts))
    check(f"{gt}：終點位置還沒被畫（沒有提前跳）",
          not any(has(seen, e) for e in ends))

    # progress=0 → 起點；progress=1 → 終點
    check(f"{gt}：progress=0 畫在起點",
          all(has(animate_and_spy(0.0), s) for s in starts))
    check(f"{gt}：progress=1 畫在終點",
          all(has(animate_and_spy(1.0), e) for e in ends))

    # 像素級複核：半程畫面必須真的變了，且插值位置上畫著選中組
    # （選中組走 be_opted → 選中色；不靠「某個像素等於某個色」這種脆斷言，
    #  動畫中的重疊邊框會蓋住點，所以要麼整幀比較、要麼取多個樣本取任一）
    seen0 = animate_and_spy(0.0)
    frame0 = pygame.surfarray.array3d(gui.screen).copy()
    seen5 = animate_and_spy(0.5)
    frame5 = pygame.surfarray.array3d(gui.screen)
    changed = int((frame0 != frame5).any(axis=2).sum())
    check(f"{gt}：半程畫面與起點不同（{changed} 像素）", changed > 1000)

    view = gui._mi_view()
    sel = tuple(gui.colors['block_selected'])
    arr = frame5

    def px(sx, sy):
        return tuple(int(v) for v in arr[int(sx), int(sy)])

    pick = [sm for m in mids
            for sm in [gui.world_to_screen(*view.piece_center(*m))]
            if 0 <= sm[0] < gui.screen_width and 0 <= sm[1] < gui.screen_height]
    check(f"{gt}：插值位置有可看畫面內的樣本（{len(pick)} 個）", len(pick) > 0)
    if pick:
        hit = [sm for sm in pick[:24] if px(*sm) == sel]
        check(f"{gt}：插值位置上畫著選中組（{len(hit)}/{min(24, len(pick))} 個樣本）",
              len(hit) > 0)

    gui.commit_animation()
    gui.animation_enabled = True

# 提交落點的精确断言（上一节已经在画面上验过插值，这里只看结果）
print("== commit_animation 落點 ==")
gui.new_mi_puzzle(6, 6, 2)
gap, blk, d = find_move('h')
check("h 族有可滑組合", blk is not None)
if blk is not None:
    gui.selected_gap = gap
    gui.selected_block = blk
    gui.animation_enabled = True
    gui.animation_duration = 300
    gui.move_selected_blocks(d, 1)
    want = [list(p) for p in gui.anim_end_pos]
    blocks = list(gui.anim_blocks)
    gui.commit_animation()
    bad = [list(b.location) for b in blocks if list(b.location) not in want]
    check(f"提交後 {len(blocks)} 塊全部落在終點（異常 {len(bad)} 塊）", not bad)
    check(f"終點集合與 anim_end_pos 一致（{len(want)} 個位置）",
          {tuple(p) for p in want} == {tuple(b.location) for b in blocks})

# ================================================================ 撤銷/重做
print("== 斜向移動的撤銷 / 重做動畫（原本：delta=(0,0) → 無動畫瞬移）==")
for gt in ('d1', 'd2', 'h', 'v'):
    gui.new_mi_puzzle(6, 6, 2)
    gap, blk, d = find_move(gt)
    check(f"{gt}：撤銷場景有可滑組合", blk is not None)
    if blk is not None:
        dr, dc = MI_DIRECTIONS[d]
        gui.selected_gap = gap
        gui.selected_block = blk
        gui.animation_enabled = True
        gui.animation_duration = 300
        gui.selection_animation_enabled = True
        pre_pos = {tuple(b.location) for b in gui.game.blocks}
        gui.move_selected_blocks(d, 1)
        n_move = len(gui.anim_blocks)
        gui.commit_animation()
        post_pos = {tuple(b.location) for b in gui.game.blocks}
        check(f"{gt}：移動後步數 = 1", gui.step_count == 1)
        check(f"{gt}：移動後局面確實變了", post_pos != pre_pos)

        # —— 撤銷：動畫是把整組從「移動後」推回「移動前」，位移是 −delta ——
        gui.undo()
        check(f"{gt}：撤銷走的是動畫路徑（不是瞬移）",
              gui.animating and gui._undo_redo_type == 'undo')
        check(f"{gt}：撤銷動畫找回了全部 {n_move} 塊",
              len(gui.anim_blocks) == n_move, f"實得 {len(gui.anim_blocks)}")
        check(f"{gt}：撤銷位移 = ({-dr},{-dc})（反向）",
              abs(gui._anim_dr + dr) < 1e-9 and abs(gui._anim_dc + dc) < 1e-9)
        check(f"{gt}：選中高亮也找回了全部塊（不是空高亮）",
              len(getattr(gui, '_sel_anim_blocks', [])) == n_move,
              f"實得 {len(getattr(gui, '_sel_anim_blocks', []))}")
        # 半程渲染：座標必須落在插值位置上（從移動後往移動前走）
        t = gui.ease_out(0.5)
        starts = [tuple(p[:2]) + (p[2],) for p in gui.anim_start_pos]
        mids = [(s[0] - dr * t, s[1] - dc * t, s[2]) for s in starts]
        seen = animate_and_spy(0.5)
        check(f"{gt}：撤銷動畫畫在插值位置", all(has(seen, m) for m in mids))
        check(f"{gt}：撤銷高亮選中的縫是 {gap[0]} {gap[1]}",
              gui._sel_anim_gap == gap, f"實得 {gui._sel_anim_gap}")
        gui.commit_animation()
        check(f"{gt}：撤銷後整局回到移動前",
              {tuple(b.location) for b in gui.game.blocks} == pre_pos)

        # —— 重做 ——
        gui.redo()
        check(f"{gt}：重做走的是動畫路徑",
              gui.animating and gui._undo_redo_type == 'redo')
        check(f"{gt}：重做動畫找回全部 {n_move} 塊",
              len(gui.anim_blocks) == n_move, f"實得 {len(gui.anim_blocks)}")
        r_starts = [tuple(p[:2]) + (p[2],) for p in gui.anim_start_pos]
        r_mids = [(s[0] + dr * t, s[1] + dc * t, s[2]) for s in r_starts]
        check(f"{gt}：重做動畫畫在插值位置",
              all(has(animate_and_spy(0.5), m) for m in r_mids))
        gui.commit_animation()
        check(f"{gt}：重做後整局回到移動後",
              {tuple(b.location) for b in gui.game.blocks} == post_pos)

print()
if _failures:
    print(f"共 {len(_failures)} 項失敗:")
    for n in _failures:
        print("  -", n)
    sys.exit(1)
print("全部通過")
