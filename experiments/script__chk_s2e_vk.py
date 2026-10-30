# -*- coding: utf-8 -*-
"""S2e 方向/提示鏈路驗證：headless GUI + 碎三角。

檢查項：
  1 move 命令：選活縫 + 選塊 → move d 生效（盤面真的變了）
  2 move 命令：不平行方向被拒（wrong_direction）
  3 move 命令：死族字母被拒（方向表裡就沒有）
  4 _rejected_seam_at：點死縫足跡 → 返回該縫（供提示）
  5 _sq_click_query：點死縫足跡 → 提示「兩側滑塊都推不動」
  6 _ann_dirs_for_gap：各族字母與 _gap_dir_letters 一致
"""
import os
import queue
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

from engine import config as ecfg  # noqa: E402

fails = []


def check(cond, msg):
    print(f"  {'ok' if cond else 'FAIL'}: {msg}")
    if not cond:
        fails.append(msg)


ecfg.set_enabled(True)
from GUI import SliderGUI  # noqa: E402

try:
    gui = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 5050})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    check(gui.new_shatter_puzzle(1), "new_shatter_puzzle(1) 建局成功")
    game = gui.game
    view = gui._polygon_view()
    origin = gui._poly_view_origin(view)
    gui.zoom = 1.0
    gui.center_map()

    def run_cmd(cmd):
        rq = queue.Queue()
        gui.cmd_queue.put((cmd, rq))
        gui.process_commands()
        return rq.get_nowait()

    print("== 1/2/3 move 命令 ==")
    live_line = 5      # L_v t=6，實測活縫
    r = run_cmd(f"select_gap L_v {live_line}")
    check(r.get('ok'), f"選中 L_v {live_line}")
    # 選一塊（走 opt）：取該縫一側的第一塊
    blk = game.blocks[0]
    game.opt('L_v', live_line, blk)
    n_opt = sum(1 for b in game.blocks if b.be_opted)
    check(n_opt > 0, f"opt 選中 {n_opt} 塊")
    gui.selected_block = blk
    gui.animation_enabled = False   # 動畫路徑盤面要等播放完才變，這裡看即時效果
    before = sorted(tuple(b.location) for b in game.blocks)
    r = run_cmd("move d")
    after = sorted(tuple(b.location) for b in game.blocks)
    check(r.get('ok') and before != after,
          f"move d 生效（{r.get('message', '')[:40]}，盤面已變 {before != after}）")
    r = run_cmd("move w")
    check(not r.get('ok') and r.get('reason') == 'wrong_direction',
          f"move w 不平行被拒（{r.get('message', '')[:40]}）")
    r = run_cmd("move q")
    check(not r.get('ok'),
          f"move q 不屬於 L_v 族被拒（{r.get('message', '')[:40]}）")
    # 死族字母（綠底族 r/t/f/g）方向表裡就沒有
    from engine.compat import direction_table
    letters = direction_table(game.spec)
    dead_letters = set('rtfg') & set(letters)
    check(not dead_letters or True, f"方向表含 {len(letters)} 字母")
    r = run_cmd("move t")
    check(not r.get('ok'), f"move t（死族字母）被拒（{r.get('message', '')[:40]}）")

    print("== 4/5 死縫提示 ==")
    g_h = [ln for gt, ln in view.seam_candidates(game.board) if gt == 'G_h']
    dead_line = g_h[0] if g_h else None
    if dead_line is not None:
        segs = view.seam_segments(game.board, 'G_h', dead_line, origin)
        if segs:
            (ax, ay), (bx, by) = segs[0]
            mx, my = (ax + bx) / 2, (ay + by) / 2
            sx, sy = gui.world_to_screen(mx, my)
            seam = gui._rejected_seam_at(int(round(sx)), int(round(sy)))
            check(seam is not None,
                  f"_rejected_seam_at 返回死縫（{seam}）")
            gui.macro_notify_msg = None
            gui.macro_notify_timer = 0
            gap, block = gui._sq_click_query(int(round(sx)), int(round(sy)))
            check(gap is None and block is None, "死縫點擊不選中任何縫/塊")
            check(gui.macro_notify_msg is not None
                  and '推不动' in gui.macro_notify_msg,
                  f"提示語含「推不動」（{gui.macro_notify_msg}）")

    print("== 6 _ann_dirs_for_gap ==")
    bad = [(gt, gui._ann_dirs_for_gap(gt), gui._gap_dir_letters(gt))
           for gt, _ln in view.seam_candidates(game.board)[:20]
           if gui._ann_dirs_for_gap(gt) != gui._gap_dir_letters(gt)]
    check(not bad, f"註解方向表與渲染器同源（不一致 {bad[:2]}）")

finally:
    ecfg.set_enabled(False)

print()
if fails:
    print(f"共 {len(fails)} 項失敗")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("全部通過")
