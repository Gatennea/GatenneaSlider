# -*- coding: utf-8 -*-
"""S1c oracle 对照 + 接线冒烟（通用渲染通道 vs 旧手画路径）。

執行：python test/_test_poly_render.py
約定：腳本型回歸（check 收集失敗，退出碼非 0 即失敗），headless（SDL dummy）。

這是「幾何引擎＝解釋器」路線（docs/spec/GUI解释器化接入计划）S1c 的落點，
回答一個問題：**通用渲染通道算出來的塊位置，和舊手畫路徑的已知答案一致嗎？**

為什麼先拿舊三形態測（而不是先用碎三角）：舊形態的正確答案是已知的（既有
手畫實現就是地面真值）。三者對得上 ⇒ 可信的是「解釋器」，之後新形態表現不
對，結論才能唯一歸給「定義寫得不好」。

對照口徑：比**幾何位置**，不比視覺樣式（漸層/圓角/描邊屬表現層，不參與）。
舊 grid 步進 = cell+gap、新 grid 步進 = cell_size，兩者允許差一個**統一的
縮放**（k = cell/(cell+gap)）；只要對每塊都成立同一個 k，就算通過。

覆蓋：
  1 舊未在默認下不受影響 —— 不開環境開關時舊三形態仍走手畫路徑（零回歸）
  2 square oracle       —— 通用通道位置 ≙ 舊 SquareBoardView 位置（同一 k）
  3 接線冒烟            —— 強制通用後 GUI.draw_board() 在 headless 下能畫（不拋）
  4 碎三角上場          —— create_puzzle('shatter') → 通用通道能畫
  5 建局入口            —— new_shatter_puzzle() 可用
  6 Port 1 功能層       —— 舊三形態全功能態（編號/捆綁/著色/連鎖/填空/宏點/
                           標記/箭頭）走通用通道：不拋 + 機器級斷言路徑已執行
                           （S6 對賬表的 oracle；抓出過兩個真 bug：三角布爾朝向
                            鄰接靜默取空、碎三角連鎖提示 KeyError）
"""

import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

failures = []


def check(cond, msg):
    print(f"  {'ok' if cond else 'FAIL'}: {msg}")
    if not cond:
        failures.append(msg)


from engine import config as ecfg  # noqa: E402
from engine.registry import square_spec  # noqa: E402
from gui.board_view import SpecPolygonView, SquareBoardView  # noqa: E402

CELL = 60.0
GAP = 4.0

# ======================================================================
print("== 1 square oracle：通用通道 vs 舊 SquareBoardView ==")
spec = square_spec(4, 4)
old_view = SquareBoardView(cell_size=CELL, gap_width=GAP)
new_view = SpecPolygonView(spec, cell_size=CELL)
unit = CELL + GAP
k = CELL / unit

bad = []
n = 0
for r in range(4):
    for c in range(4):
        ox, oy = old_view.cell_to_world(r, c)      # 舊：(col*unit, row*unit)
        oxr, oyr, w, h = old_view.block_rect(r, c)
        poly = new_view.world_polygon((r, c), '', (0.0, 0.0))
        nx, ny = min(p[0] for p in poly), min(p[1] for p in poly)
        # 新 = k × 舊（位置對齊），且塊的邊長 = k × cell
        if abs(nx - k * ox) > 1e-6 or abs(ny - k * oy) > 1e-6:
            bad.append(((r, c), (nx, ny), (k * ox, k * oy)))
        n += 1
check(not bad, f"每塊左上角滿足 新 = k×舊（k={k:.6f}），偏差 {len(bad)}/{n}"
      + (f" 首例 {bad[0]}" if bad else ""))

# 塊的實際大小也應為 k×cell（不是被 gap 撐大）
size_bad = []
for r in range(4):
    for c in range(4):
        poly = new_view.world_polygon((r, c), '', (0.0, 0.0))
        w = max(p[0] for p in poly) - min(p[0] for p in poly)
        h = max(p[1] for p in poly) - min(p[1] for p in poly)
        if abs(w - CELL) > 1e-6 or abs(h - CELL) > 1e-6:
            size_bad.append(((r, c), w, h))
check(not size_bad,
      f"每塊外接尺寸 == cell_size（{size_bad[:2]}）")

# ======================================================================
print("== 2 默認不劫持 / 強制生效：真實呼叫 _polygon_view() ==")
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ.pop('GATENNEA_POLY_RENDER', None)
ecfg.set_enabled(True)          # 讓 create_puzzle 走 EngineGame（才有 spec）

try:
    import queue  # noqa: E402
    from GUI import SliderGUI  # noqa: E402
    gui = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 5050})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    check(hasattr(gui.game, 'spec'),
          f"GUI 的 game 走 EngineGame（有 spec，實際 {type(gui.game).__name__}）")

    # 選項 A：引擎遊戲（帶 board + spec）現在**默認就走通用通道**——舊閘門
    # （name in square/tri/mi 且未開 GATENNEA_POLY_RENDER → 回 None）已移除。
    # 舊引擎遊戲（無 board）仍走既有手畫路徑（通用通道需 board 才能渲染）；
    # 兜底 _spec_for_old_game 只在「有 board 但無 spec」時接管。
    check(gui._polygon_view() is not None,
          f"引擎遊戲默認進通用通道（{getattr(gui.game.spec, 'name', '?')} "
          f"取得 SpecPolygonView，選項 A 生效）")

    # 選項 A 兜底專測：舊引擎遊戲 SliderMatrix 無 .spec，_spec_for_old_game
    # 仍能按類型造出帶 cell_polygon 的 spec（邏輯層驗證，不依賴 board）。
    from game import SliderMatrix  # noqa: E402
    _fb = SliderGUI._spec_for_old_game(SliderMatrix(4, 4))
    check(_fb is not None and callable(getattr(_fb, 'cell_polygon', None)),
          "舊引擎遊戲經 _spec_for_old_game 兜底造出帶 cell_polygon 的 spec（選項 A）")

    # ==================================================================
    print("== 3 接線冒烟：強制通用路徑下 draw_board() 能畫（不拋異常）==")
    err = None
    try:
        gui.draw_board()
    except Exception as e:      # 不靜默：繪製拋異常即失敗
        err = f"{type(e).__name__}: {e}"
    check(err is None, f"draw_board() headless 繪製無異常（{err}）")

    # ==================================================================
    print("== 4 碎三角上場：create_puzzle('shatter') → 通用通道能畫（S1d + S3）==")
    from engine.adapter import EngineGame  # noqa: E402
    from puzzle_types import create_puzzle  # noqa: E402
    g = create_puzzle(4, 4, 1, 'shatter')
    check(isinstance(g, EngineGame),
          f"create_puzzle('shatter') 造出 EngineGame（實際 "
          f"{type(g).__name__}）——沒被靜默回退成方形")
    check(getattr(g.spec, 'name', '') == 'shatter',
          f"造出的板型是 shatter（實際 {getattr(g.spec, 'name', '?')}）")
    check(callable(getattr(g.spec, 'cell_polygon', None)),
          "shatter 的 spec 帶 cell_polygon（形狀寫成了數據）")
    check(g.board.block_count == 48,
          f"碎三角局面 48 塊（實際 {g.board.block_count}）")
    # 交給 GUI 的通用通道：換上碎三角局面後應進入通用渲染且能畫
    gui.game = g
    pv2 = gui._polygon_view()
    check(pv2 is not None, "碎三角進入通用通道（取得 SpecPolygonView）")
    err2 = None
    try:
        gui.draw_board()
    except Exception as e:      # 不靜默
        err2 = f"{type(e).__name__}: {e}"
    check(err2 is None, f"碎三角 draw_board() headless 繪製無異常（{err2}）")

    # ==================================================================
    print("== 5 建局入口：new_shatter_puzzle() 可用（S3 入口側）==")
    ok = gui.new_shatter_puzzle(1)
    check(ok, "new_shatter_puzzle() 回傳 True（建局成功）")
    check(getattr(gui.game.spec, 'name', '') == 'shatter',
          f"建局後板型為 shatter（實際 {getattr(gui.game.spec, 'name', '?')}）")
    check(gui.game.board.block_count == 48,
          f"建局後 48 塊（實際 {gui.game.board.block_count}）")
    check(gui.mi_mode is False and gui.triangle_mode is False,
          "兩個手畫形態旗標都關（形狀交給通用通道，不走手畫分支）")
    check(gui._polygon_view() is not None, "建局後進入通用渲染通道")
    err3 = None
    try:
        gui.draw_board()
    except Exception as e:      # 不靜默
        err3 = f"{type(e).__name__}: {e}"
    check(err3 is None, f"建局後 draw_board() 繪製無異常（{err3}）")

    # ==================================================================
    print("== 6 Port 1 功能層 oracle：舊三形態全功能態走通用通道（S6 對賬）==")
    # S6 對賬表逐行落地：編號字 / 捆綁組 / 分組著色 / 連鎖提示 / 選塊填空 /
    # 宏基準點 / 指標標記 / 方向箭頭。口徑 = 每一行都在通用通道裡**真的走
    # 一遍**（不拋異常 + 機器級斷言路徑已執行），而非只畫個背景。

    def _adjacent_pair(gui):
        """相鄰兩塊（鄰交由引擎晶格經 _poly_neighbors_of 回答）——捆綁組
        渲染的最小用例；同時用來斷言鄰接回調本身（oracle 的 oracle）。"""
        pv = gui._polygon_view()
        b0 = gui.game.blocks[0]
        key0 = tuple(b0.location)
        for nb in gui._poly_neighbors_of(pv)(key0):
            for b in gui.game.blocks:
                if tuple(b.location) == tuple(nb):
                    return b0, b
        return None

    def _full_feature_draw(gui, pick_fill):
        """功能層全開 → draw_board() 一次；回傳 (異常串或 None, 捆綁對)。"""
        gui.numbered = True
        for i, b in enumerate(gui.game.blocks):
            b.number = i + 1
        pair = _adjacent_pair(gui)
        if pair is not None:
            pair[0].group = 1
            pair[1].group = 1
        gui.current_step = 2          # 著色/連鎖都要 >1 級
        gui.coloring_enabled = True
        gui.chain_hint_enabled = True
        gui.hover_cell = tuple(gui.game.blocks[0].location)
        if pick_fill:
            # 選塊填空選取態只存在於方形（_pick_fill_form_blocked 入口閘門，
            # 見 _draw_pick_fill_marks docstring）；異形不置。
            gui._pick_fill = {'block': tuple(gui.game.blocks[0].location),
                              'hole': None}
        gui.macro_record_base_point = tuple(gui.game.blocks[0].location)
        gui.show_metrics_panel = True
        gui.board_marks_enabled = True
        err = None
        try:
            gui.draw_board()
        except Exception as e:      # 不靜默
            err = f"{type(e).__name__}: {e}"
        # 復位：箭頭 oracle 還要選縫，旗標留著會污染後續斷言
        gui.numbered = False
        for b in gui.game.blocks:
            b.number = None
            b.group = 0
        gui.current_step = 1
        gui.coloring_enabled = False
        gui.chain_hint_enabled = False
        gui.hover_cell = None
        gui._pick_fill = None
        gui.macro_record_base_point = None
        gui.show_metrics_panel = False
        gui.board_marks_enabled = False
        return err, pair

    def _arrow_oracle(gui):
        """選一條活縫 + opt 一片 → 箭頭兩端按鍵，至少一個方向可走。"""
        block = gui.game.blocks[0]
        tried = 0
        for gap in gui.game.all_gaps():
            tried += 1
            gui.selected_gap = gap
            gui.selected_block = block
            gui.game.opt(gap[0], gap[1], block)
            if not any(b.be_opted for b in gui.game.blocks):
                continue
            ann = gui._get_gap_direction_annotation()
            if not ann:
                continue
            btns = ann.get('buttons') or []
            if len(btns) != 2 or not any(b[3] for b in btns):
                continue
            err = None
            try:
                gui.draw_board()   # 箭頭畫在通用通道裡（最上層）
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
            gui.selected_gap = None
            gui.selected_block = None
            gui.game._clear_selection()
            return err
        gui.selected_gap = None
        gui.selected_block = None
        gui.game._clear_selection()
        return f"no-gap-with-allowed-direction (tried {tried})"

    # 舊三形態逐一過堂（選塊填空只測方形——選取態是方形專屬入口）
    for _kind, _maker, _pick in (
            ('square', lambda: (setattr(gui, 'game', create_puzzle(4, 4, 1)),
                                setattr(gui, 'mi_mode', False),
                                setattr(gui, 'triangle_mode', False),
                                gui.center_map()), True),
            ('tri', lambda: gui.new_triangle_puzzle(5, 1), False),
            ('mi', lambda: gui.new_mi_puzzle(4, 4, 1), False),
    ):
        _maker()
        _pv = gui._polygon_view()
        check(_pv is not None, f"[{_kind}] 強制通用通道生效（SpecPolygonView）")
        if _pv is None:
            continue
        _err, _pair = _full_feature_draw(gui, _pick)
        check(_err is None,
              f"[{_kind}] 功能層全開 draw_board() 無異常（{_err}）")
        check(bool(getattr(gui, '_num_font_cache', None)),
              f"[{_kind}] 編號路徑真的執行（_num_font_cache 已建）")
        _region = gui._compute_target_region()
        check(_region is not None,
              f"[{_kind}] 指標標記的目標窗口算得出（{type(_region).__name__}）")
        if _pair is not None:
            _nb = gui._poly_neighbors_of(_pv)
            _ka = tuple(_pair[0].location)
            _kb = tuple(_pair[1].location)
            check(tuple(_kb) in [tuple(x) for x in _nb(_ka)]
                  and tuple(_ka) in [tuple(x) for x in _nb(_kb)],
                  f"[{_kind}] 捆綁對互相列為鄰居（_poly_neighbors_of 鄰接回調）")
        _aerr = _arrow_oracle(gui)
        check(_aerr is None,
              f"[{_kind}] 箭頭 oracle：活縫兩端按鍵 + 至少一個方向可走 + "
              f"繪製無異常（{_aerr}）")

finally:
    ecfg.set_enabled(False)
    os.environ.pop('GATENNEA_POLY_RENDER', None)

# ======================================================================
print()
if failures:
    print(f"共 {len(failures)} 項失敗")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("全部通過")
