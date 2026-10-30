# -*- coding: utf-8 -*-
"""S2f 通用拖拽通道驗證：headless GUI + 碎三角，走真實 pygame 事件流。

檢查項：
  1 按下塊心 → 超過閤值拖拽 → 進入跟隨（方向字母合理）
  2 跟隨偏移 = 螢幕位移投影到該字母一步的屏幕向量（P 空間 t·d）
  3 拖一整步的像素 → 松手提交 → 盤面真的移動了一格
  4 拖不到半步 → 松手不移動（夾緊）
  5 拖拽期間 draw_board 不拋（視覺鍵含小數 P 座標）
  6 _drag_slide 守衛：跟隨便沒起來時不會解包崩潰
  7 死方向拖拽（綠底族字母）→ 提示「這個方向滑不動」且不進入跟隨
"""
import os
import queue
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import pygame  # noqa: E402

from engine import config as ecfg  # noqa: E402

fails = []


def check(cond, msg):
    print(f"  {'ok' if cond else 'FAIL'}: {msg}")
    if not cond:
        fails.append(msg)


def post_click(gui, x, y):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(int(x), int(y))))


def post_motion(gui, x, y):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEMOTION, pos=(int(x), int(y)), rel=(0, 0)))


def post_release(gui, x, y):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, button=1, pos=(int(x), int(y))))


ecfg.set_enabled(True)
from GUI import SliderGUI  # noqa: E402

try:
    gui = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 5050})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    check(gui.new_shatter_puzzle(1), "new_shatter_puzzle(1) 建局成功")
    game = gui.game
    gui.animation_enabled = False   # 看即時效果，不等動畫

    # 選一塊可動的：L_v 活縫任一側的第一塊
    blk = None
    letter = 'd'
    for b in game.blocks:
        vx, vy = gui._letter_screen_vec('d', tuple(b.location))
        if vx is not None and (vx * vx + vy * vy) > 1e-6:
            blk = b
            break
    check(blk is not None, "找到一塊可計算 'd' 向屏幕向量的塊")
    sx0, sy0 = gui._key_center(tuple(blk.location))
    vx, vy = gui._letter_screen_vec(letter, tuple(blk.location))
    step_px = (vx * vx + vy * vy) ** 0.5
    print(f"    一步 '{letter}' 的屏幕長度 = {step_px:.1f}px")

    print("== 1/2/3 拖一整步 → 跟隨 → 提交 ==")
    before_loc = tuple(blk.location)
    before = sorted(tuple(b.location) for b in game.blocks)
    post_click(gui, sx0, sy0)
    gui.handle_events()
    check(gui._mouse_drag_state is not None, "按下記錄拖拽起點")
    post_motion(gui, sx0 + vx * 1.05, sy0 + vy * 1.05)
    gui.handle_events()
    check(gui.drag_following, "超過閤值後進入跟隨")
    check(gui.drag_follow_direction == letter,
          f"鎖定方向 '{letter}'（實測 {gui.drag_follow_direction}）")
    dr, dc = gui.drag_follow_offset
    from engine.compat import direction_table
    d = direction_table(game.spec)[letter]
    # 偏移夾緊到 [0, max_cells]：1.05 步超過探測上限 1 步 → 夾在 1 步
    exp_steps = min(1.05, float(gui.drag_follow_max_cells))
    check(abs(dr - d[0] * exp_steps) < 0.05 and abs(dc - d[1] * exp_steps) < 0.05,
          f"偏移 ≈ {exp_steps:.2f}·{d}（實測 ({dr:.3f},{dc:.3f})，"
          f"max_cells={gui.drag_follow_max_cells}）")
    err = None
    try:
        gui.draw_board()
    except Exception as e:
        import traceback
        traceback.print_exc()
        err = f"{type(e).__name__}: {e}"
    check(err is None, f"跟隨期間 draw_board 不拋（{err}）")
    post_release(gui, sx0 + vx * 1.05, sy0 + vy * 1.05)
    gui.handle_events()
    gui.draw_board()   # 模擬主循環幀：刷新箭頭按鍵矩形（否則下一腳點到陳舊矩形）
    check(not gui.drag_following, "松手後退出跟隨")
    check(tuple(blk.location) != before_loc, "被拖的塊移動了")
    delta = (blk.location[0] - before_loc[0], blk.location[1] - before_loc[1])
    check(delta == d, f"被拖的塊正好走一步 {d}（實測 {delta}）")
    after = sorted(tuple(b.location) for b in game.blocks)
    check(before != after, "盤面移動了")

    print("== 4 拖不到半步 → 不移動 ==")
    before = sorted(tuple(b.location) for b in game.blocks)
    # 換一塊**真能沿 'd' 走**的（resolve_drag 探到才算，避免選到貼邊塊）
    blk2 = None
    vx2 = vy2 = None
    for b in game.blocks:
        pos, _gt, _ln, reason, _n = game.resolve_drag(
            tuple(b.location), 'd', 1)
        game._clear_selection()
        if pos:
            blk2 = b
            vx2, vy2 = gui._letter_screen_vec('d', tuple(b.location))
            break
    check(blk2 is not None, "找到一塊真能沿 'd' 滑的塊")
    if blk2 is not None:
        ax, ay = gui._key_center(tuple(blk2.location))
        post_click(gui, ax, ay)
        gui.handle_events()
        post_motion(gui, ax + vx2 * 0.3, ay + vy2 * 0.3)
        gui.handle_events()
        check(gui.drag_following, "小幅拖拽仍進跟隨（偏移夾緊）")
        dr, dc = gui.drag_follow_offset
        check(abs(dr) <= 0.3 * abs(d[0]) + 0.1, f"偏移夾緊到 0.3 步（{dr:.3f}）")
        post_release(gui, ax + vx2 * 0.3, ay + vy2 * 0.3)
        gui.handle_events()
        after = sorted(tuple(b.location) for b in game.blocks)
        check(before == after, "半步以下不提交移動")

    print("== 6 _drag_slide 守衛 ==")
    err = None
    try:
        gui._drag_slide(blk2, 50, 0)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    check(err is None, f"_drag_slide 對三元組 location 不崩（{err}）")

    print("== 7 死方向拖拽 ==")
    # 綠底族恆死：沿 'r'（G_d60 −）的屏幕方向拖，吸附必中 'r'，
    # resolve_drag 探不到移動 → 不進跟隨 + 提示
    blk3 = game.blocks[0]
    bx, by = gui._key_center(tuple(blk3.location))
    rx, ry = gui._letter_screen_vec('r', tuple(blk3.location))
    gui.macro_notify_msg = None
    gui.draw_board()   # 幀間刷新：箭頭按鍵矩形跟隨當前選中態
    post_click(gui, bx, by)
    gui.handle_events()
    post_motion(gui, bx + rx * 1.05, by + ry * 1.05)
    gui.handle_events()
    check(not gui.drag_following, "死族字母拖拽不進跟隨")
    check(gui.macro_notify_msg is not None
          and '滑不动' in gui.macro_notify_msg,
          f"死族字母拖拽有提示（{gui.macro_notify_msg}）")
    post_release(gui, bx + rx * 1.05, by + ry * 1.05)
    gui.handle_events()
    check(not gui.drag_following, "松手後仍不跟隨")

finally:
    ecfg.set_enabled(False)

print()
if fails:
    print(f"共 {len(fails)} 項失敗")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("全部通過")
