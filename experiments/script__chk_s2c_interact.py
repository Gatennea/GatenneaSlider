# -*- coding: utf-8 -*-
"""S2c 通用交互幾何驗證：headless GUI + 碎三角，跑渲染器新接線。

檢查項：
  1 _key_center  round-trip：screen_to_world(中心) == 世界多邊形質心
  2 _game_dir_tables / _gap_dir_letters：各族兩個字母（引擎 parallel 反查）
  3 _letter_screen_vec：字母的落屏方向（d 右 / a 左 / w 上 / s 下）
  4 選中活縫 → _get_gap_direction_annotation 兩個箭頭按鍵，d 在 a 右側
  5 _poly_seam_segments：選中縫足跡非空
  6 _piece_screen_radius > 0
  7 選中縫狀態下 draw_board 不拋
  8 拖拽/動畫偏移下 _key_center 跟著挪（視覺鍵）
"""
import os
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
import queue  # noqa: E402
from GUI import SliderGUI  # noqa: E402

try:
    gui = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 5050})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    ok = gui.new_shatter_puzzle(1)
    check(ok, "new_shatter_puzzle(1) 建局成功")

    game = gui.game
    view = gui._polygon_view()
    check(view is not None, "進入通用渲染通道")
    origin = gui._poly_view_origin(view)
    # 手動佈一個合理相機（S2d 會把這段收進 center_map 通用分支）
    minx, miny, maxx, maxy = view.bounds_of(game.board.blocks)
    W, H = (maxx - minx) * view.cell_size, (maxy - miny) * view.cell_size
    gui.zoom = 1.0
    gui.camera_x = (gui.screen_width - gui.right_panel_width) / 2 - W / 2
    gui.camera_y = (gui.menu_bar_height +
                    (gui.screen_height - gui.menu_bar_height
                     - gui.status_bar_height) / 2 - H / 2)

    print("== 1 _key_center round-trip ==")
    bad = 0
    for b in game.blocks:
        key = tuple(b.location)
        point, orient = gui._poly_key_parts(key)
        poly = view.world_polygon(point, orient, origin)
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        sx, sy = gui._key_center(key)
        wx, wy = gui.screen_to_world(sx, sy)
        if abs(wx - cx) > 1e-6 or abs(wy - cy) > 1e-6:
            bad += 1
    check(bad == 0, f"48 塊質心 round-trip 全對（錯 {bad}/48）")

    print("== 2 方向字母表（parallel 反查）==")
    deltas, table = gui._game_dir_tables()
    check(len(deltas) == 12, f"12 個方向字母（實測 {len(deltas)}）")
    want = {'L_v': ('a', 'd'), 'L_d30': ('e', 'z'),
            'L_d150': ('q', 'x'), 'G_h': ('s', 'w')}
    for fam, letters in want.items():
        check(table.get(fam) == letters,
              f"{fam} → {letters}（實測 {table.get(fam)}）")
    check(gui._gap_dir_letters('L_v') == ('a', 'd'),
          f"_gap_dir_letters('L_v') == ('a','d')（實測 "
          f"{gui._gap_dir_letters('L_v')}）")

    print("== 3 字母落屏方向 ==")
    key = tuple(game.blocks[0].location)
    exp = {'d': (1, 0), 'a': (-1, 0), 'w': (0, -1), 's': (0, 1),
           'e': (1, -1), 'q': (-1, -1), 'z': (-1, 1), 'x': (1, 1)}
    name = {'d': '右', 'a': '左', 'w': '上', 's': '下',
            'e': '右上', 'q': '左上', 'z': '左下', 'x': '右下'}
    for letter, (ex, ey) in exp.items():
        vx, vy = gui._letter_screen_vec(letter, key)
        check(vx * ex >= -1e-9 and vy * ey >= -1e-9
              and (abs(vx) > 1e-6 or abs(vy) > 1e-6),
              f"'{letter}' 落屏方向符合 {name[letter]}"
              f"（實測 ({vx:.1f},{vy:.1f})）")

    print("== 4 選中活縫 → 箭頭按鍵 ==")
    # L_v line 5 ↔ t=6（S2a 實測活縫）
    live_line = 5
    gui.selected_gap = ('L_v', live_line)
    game.opt('L_v', live_line, game.blocks[0])
    n_opt = sum(1 for b in game.blocks if b.be_opted)
    check(0 < n_opt < len(game.blocks),
          f"opt 選中 {n_opt}/{len(game.blocks)} 塊（非空非全員）")
    segs = gui._poly_seam_segments(view, 'L_v', live_line, origin)
    check(len(segs) > 0, f"選中縫足跡非空（{len(segs)} 段）")
    annot = gui._get_gap_direction_annotation()
    check(annot is not None and len(annot['buttons']) == 2,
          "箭頭註解返回兩個按鍵"
          f"（實測 {None if annot is None else len(annot['buttons'])}）")
    if annot:
        letters = [d for d, _c, _a, _m in annot['buttons']]
        check(sorted(letters) == ['a', 'd'],
              f"兩個按鍵是 a/d（實測 {letters}）")
        c_a = next(c for d, c, _a, _m in annot['buttons'] if d == 'a')
        c_d = next(c for d, c, _a, _m in annot['buttons'] if d == 'd')
        check(c_d[0] > c_a[0], f"d 按鍵在 a 右側（{c_d[0]:.0f} > {c_a[0]:.0f}）")
        movable = {d: m for d, _c, _a, m in annot['buttons']}
        print(f"    可走方向：{movable}")

    print("== 5 _piece_screen_radius ==")
    r = gui._piece_screen_radius()
    check(r > 0, f"選中切片外接半徑 > 0（實測 {r:.1f}px）")

    print("== 6 選中縫狀態下 draw_board 不拋 ==")
    err = None
    try:
        gui.draw_board()
    except Exception as e:
        import traceback
        traceback.print_exc()
        err = f"{type(e).__name__}: {e}"
    check(err is None, f"draw_board 無異常（{err}）")

    print("== 7 視覺鍵跟隨偏移 ==")
    b0 = game.blocks[0]
    base = gui._key_center(tuple(b0.location))
    gui.drag_following = True
    gui.drag_follow_offset = (2.0, 0.0)      # P 空間右移 2
    moved = gui._key_center(gui._visual_key(b0))
    check(moved[0] > base[0] + 1e-6,
          f"偏移後中心右移（{base[0]:.1f} → {moved[0]:.1f}）")
    gui.drag_following = False
    gui.drag_follow_offset = (0.0, 0.0)
    back = gui._key_center(gui._visual_key(b0))
    check(abs(back[0] - base[0]) < 1e-6, "取消偏移後復位")

finally:
    ecfg.set_enabled(False)

print()
if fails:
    print(f"共 {len(fails)} 項失敗")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("全部通過")
