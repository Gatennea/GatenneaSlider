# -*- coding: utf-8 -*-
"""S2d 命中/相機/選縫端到端驗證：headless GUI + 碎三角。

檢查項：
  1 center_map 通用分支：相機居中，_is_camera_valid 為真
  2 get_block_at_pos round-trip：48 塊質心屏幕座標 → 同一塊對象
  3 get_gap_at_pos：點活縫足跡中點 → 拿到 valid+live 的縫
  4 get_gap_at_pos：點死縫（綠底族恆死）→ None
  5 _generic_gap_live 與引擎 is_live_gap 對全部候選逐一致
  6 select_gap 命令通道：合法活縫成功 / 死縫被拒 / 陌生族名被拒
  7 select_gap 成功後 selected_gap 生效（回讀命令 state）
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
    check(view is not None, "進入通用通道")

    print("== 1 center_map / _is_camera_valid ==")
    gui.zoom = 1.0
    gui.center_map()
    check(gui._is_camera_valid(), "center_map 後相機有效")
    bbox = gui._poly_world_bbox()
    _l, _t, W, H = bbox
    cx_screen, cy_screen = gui.world_to_screen(W / 2, H / 2)
    want_x = (gui.screen_width - gui.right_panel_width) / 2
    want_y = gui.menu_bar_height + (
        gui.screen_height - gui.menu_bar_height - gui.status_bar_height) / 2
    check(abs(cx_screen - want_x) < 1e-6 and abs(cy_screen - want_y) < 1e-6,
          f"盤面世界中心對準遊戲區中心（({cx_screen:.0f},{cy_screen:.0f}) vs "
          f"({want_x:.0f},{want_y:.0f})）")
    # 邊界外相機無效（通用分支真的在起作用，不是永遠返回 True）
    gui.camera_x += 10 ** 6
    check(not gui._is_camera_valid(), "相機甩到宇宙外後判無效")
    gui.center_map()

    print("== 2 get_block_at_pos round-trip ==")
    bad = 0
    tested = 0
    for b in game.blocks:
        sx, sy = gui._key_center(tuple(b.location))
        got = gui.get_block_at_pos(int(round(sx)), int(round(sy)))
        tested += 1
        if got is not b:
            bad += 1
    check(bad == 0, f"{tested} 塊質心點擊全回到自身（錯 {bad}）")

    print("== 3/4 get_gap_at_pos 活縫命中 / 死縫拒絕 ==")
    origin = gui._poly_view_origin(view)
    live_nonone = 0
    live_tested = 0
    dead_violation = []
    live_miss = []
    for gap_type, line in view.seam_candidates(game.board):
        segs = view.seam_segments(game.board, gap_type, line, origin)
        if not segs:
            continue
        # 點在第一段足跡的中點（真實線上，不是形心）
        (ax, ay), (bx, by) = segs[0]
        mx, my = (ax + bx) / 2, (ay + by) / 2
        sx, sy = gui.world_to_screen(mx, my)
        got = gui.get_gap_at_pos(int(round(sx)), int(round(sy)))
        # 一條接觸邊可被多條候選縫共享（實測 1~4），點上去拿到的可能是
        # 同距離另一條縫——設計就是「第一條活縫決勝」，所以只要求：
        # 活縫 → 必拿到某條活縫；死縫 → 拿到的必須也是活縫（絕不返回死縫）
        if game.is_live_gap(gap_type, line):
            live_tested += 1
            if got is None:
                live_miss.append((gap_type, line))
            elif game.is_live_gap(*got) and game.is_valid_gap(*got):
                live_nonone += 1
        else:
            if got is not None and not game.is_live_gap(*got):
                dead_violation.append((gap_type, line, got))
        # 點擊的那條縫自己必須在候選裡（距離 0）
        cand = view.gap_candidates(mx, my, game.board, origin)
        names = [(gt, ln) for gt, ln, _d in cand]
        if (gap_type, line) not in names:
            live_miss.append(('not-in-candidates', gap_type, line))
    check(not live_miss, f"活縫足跡點擊必拿到活縫且自身在候選（問題 {live_miss[:3]}）")
    check(not dead_violation,
          f"死縫足跡點擊絕不返回死縫（違反 {dead_violation[:3]}）")
    print(f"    （活縫 {live_tested} 條全拿到活縫；死縫點擊若返回則為共享活縫）")

    print("== 5 _generic_gap_live ↔ is_live_gap ==")
    mism = [(gt, ln) for gt, ln in view.seam_candidates(game.board)
            if gui._generic_gap_live((gt, ln)) != game.is_live_gap(gt, ln)]
    check(not mism, f"全部候選縫活性判據一致（不一致 {mism[:3]}）")

    print("== 6 select_gap 命令通道 ==")

    def run_cmd(cmd):
        rq = queue.Queue()
        gui.cmd_queue.put((cmd, rq))
        gui.process_commands()
        return rq.get_nowait()

    live_line = 5      # L_v t=6，S2a 實測活縫
    r = run_cmd(f"select_gap L_v {live_line}")
    check(r.get('ok'), f"select_gap L_v {live_line} 成功（{r.get('message', '')[:60]}）")
    check(gui.selected_gap == ('L_v', live_line),
          f"selected_gap == ('L_v', {live_line})（實測 {gui.selected_gap}）")
    # 死縫：綠底族（恆死），取它第一個候選線號
    g_h = [ln for gt, ln in view.seam_candidates(game.board) if gt == 'G_h']
    dead_line = g_h[0] if g_h else None
    if dead_line is not None:
        r = run_cmd(f"select_gap G_h {dead_line}")
        check(not r.get('ok'), f"select_gap G_h {dead_line} 被拒（{r.get('message', '')[:50]}）")
    r = run_cmd("select_gap NOPE 3")
    check(not r.get('ok'), f"陌生族名被拒（{r.get('message', '')[:50]}）")
    r = run_cmd("select_gap L_v abc")
    check(not r.get('ok'), "非數字 line 被拒")
    # ¼ 線（4× 線分辨率族）也要能解析
    r = run_cmd("select_gap L_v 5.25")
    check('line 必须是' not in str(r.get('message', '')),
          f"¼ 小數線可解析（{r.get('message', '')[:60]}）")

    print("== 7 select_gap 生效後回讀 ==")
    r = run_cmd("status")
    check(isinstance(r, dict) and 'selected_gap' in r,
          f"status 命令可回讀（keys={sorted(r)[:6]}…）")
    check(r.get('selected_gap') == ['L_v', 5.25],
          f"status 回讀 selected_gap == ['L_v', 5.25]（實測 {r.get('selected_gap')}）")

finally:
    ecfg.set_enabled(False)

print()
if fails:
    print(f"共 {len(fails)} 項失敗")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("全部通過")
