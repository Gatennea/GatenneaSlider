# -*- coding: utf-8 -*-
r"""S4：碎三角 headless GUI 完整回路（打乱 → 选缝选块 → 移动 → Undo → is_solved）。

執行：D:\python\python.exe -u test\_test_shatter_gui.py
約定：腳本型回歸（check 收集失敗，退出碼非 0 即失敗），headless（SDL dummy）。

這是「幾何引擎＝解釋器」路線（docs/spec/GUI解释器化接入计划）S4 的落點。
S0~S2 已逐一驗證「渲染 / 命中 / 選縫 / 移動 / 拖拽」各環節，S4 回答最後
一個問題：**把這些環節串成一局，歷史（撤銷/重做）跟得上嗎？**

斷鏈根因（本測試鎖修的對象）：碎三角走 EngineGame，位置是帶朝向的三元組
``[r, c, orient]``，而 ``history.restore_snapshot`` 的末支按方形 2-tuple 重建、
``adapter.update_matrix`` 的末支寫 1——朝向整段丟失，撤銷/重做出來的局面
角色全變、還原判定必錯。修法：兩側各加一條通用分支，矩陣值 = 
``spec.orientations.index(orient) + 1`` 互為編解碼；合並快照的逐步重播
（expand_snapshot_moves / cells_to_snapshot）按方形寫死，故碎三角不合並
（``_move_merge_key`` 對帶朝向板型返 None，每步一條快照）。

覆蓋：
  S1 建局與矩陣編碼   48 塊 / 還原態 / 值=orientations 下標+1 / 快照往返
  S2 完整回路         engine 安全打亂 → GUI 回放層逆播 → is_solved，
                      中途 Undo/Redo 逐態精確比對（含朝向）
  S3 單步命令回路     select_gap（cmd_queue 真命令路徑）→ opt → move → Undo
  S4 死族縫攔截       綠底縫（G_h/G_d60/G_d120）恆 inert，選縫被拒
  S5 舊形態無回歸     方形 else / 米字 Q_ORDER / 三角 k 三條分支互不搶占
  S6 菜單與存檔閉環   謎題菜單碎三角分組 / 分榜鍵不與矩形 4×4 混榜 /
                      create_puzzle 可分派 / 存檔 type=shatter 往返逐塊一致 /
                      競速·創造·設計畫布·手動構造·隨機生成明拒 /
                      成績回放明拒 / Ctrl+R 重建 / HTTP 狀態帶 orient
"""

import os
import queue
import random
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

failures = []


def check(cond, msg):
    print(f"  {'ok' if cond else 'FAIL'}: {msg}")
    if not cond:
        failures.append(msg)


os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from engine.adapter import EngineGame, create_adapter_puzzle  # noqa: E402
from engine.analysis import safe_scramble  # noqa: E402
from engine.compat import _keys_to_positions, direction_table  # noqa: E402
from history import GameHistory  # noqa: E402


def _gui_shatter(step=1):
    """headless GUI + 碎三角局（不走全局引擎開關，與產品入口同路徑）。"""
    gui = SliderGUI(m=6, n=6, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 5050})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.animation_enabled = False
    gui.new_shatter_puzzle(step)
    return gui


def _positions(game):
    """局面指紋：位置三元組（含朝向）集合——比規範形更嚴的精確判據。"""
    return {tuple(b.location) for b in game.blocks}


def _engine_state(board, spec):
    """引擎局面 → 位置三元組集合（與 _positions 同形比對）。"""
    return {tuple(p) for p in _keys_to_positions(sorted(board.keys), spec)}


def _move_to_op(mv, spec):
    """引擎 Move → GUI 回放層的 op（與 _execute_next_macro_step 同契約）。

    gap_line = (t-1)/line_scale（_line_to_t 的逆）；side：引擎 -1/+1 →
    GUI 0/1（0 = rank 小的一側）；direction：方向向量反查字母；
    rep_cell 帶齊朝向分量（碎三角同格多塊，缺第三分量會定位到錯的塊）。
    """
    dt = direction_table(spec)
    letter = next(k for k, v in dt.items() if v == mv.direction)
    fam = next(f for f in spec.seam_families if f.name == mv.family)
    line = (mv.t - 1) / fam.line_scale
    line = int(line) if line == int(line) else line
    (r, c, orient), = _keys_to_positions([mv.moved[0]], spec)
    return {'gap_type': mv.family, 'gap_line': line,
            'side': 0 if mv.side < 0 else 1,
            'direction': letter, 'step': mv.step,
            'rep_cell': [r, c, orient]}


def _replay_via_gui(gui, ops):
    """走 GUI 自己的宏回放入口把 ops 播完（無動畫一次播完）。

    成功判據看 ``macro_error_msg`` 是否為空——播完會清空隊列、
    index 歸 0，與「中途失敗」的 executing 都是 False，只能靠錯誤
    文案區分（與 test/_test_mi_gui_solve.py 同口径）。
    """
    gui.macro_executing = True
    gui.macro_exec_name = '逆序'
    gui.macro_exec_ops = list(ops)
    gui.macro_exec_index = 0
    gui.macro_exec_factor = 1
    gui.macro_error_msg = ''
    gui._gather_info = None
    gui._execute_next_macro_step()
    return (not gui.macro_error_msg), gui.macro_error_msg


def _cmd(gui, text):
    """經 cmd_queue 跑一條終端指令，回 (ok, message)。"""
    rq = queue.Queue()
    gui.cmd_queue.put((text, rq))
    gui.process_commands()
    r = rq.get_nowait()
    return r['ok'], r['message']


# ======================================================================
print('== S1 建局與矩陣編碼（通用分支的地面真值）==')

gui = _gui_shatter(1)
g = gui.game
spec = g.spec
orients = spec.orientations

check(len(g.blocks) == 48, f'碎三角 48 塊（實測 {len(g.blocks)}）')
check(g.is_solved(), '建局即還原態')
check(gui._generic_spec() is spec, 'GUI 走通用通道（_generic_spec 拿到板型）')
check(getattr(g, 'kind', '') == 'shatter', f"kind = {getattr(g, 'kind', '?')!r}")
check(gui._move_merge_key() is None,
      '帶朝向板型不合並快照（_move_merge_key = None）')

# update_matrix 逐塊核對：值 = orientations 下標 + 1
g.update_matrix()
mb = g.matrix_bounds
enc_bad = []
for b in g.blocks:
    r, c, o = b.location[0], b.location[1], b.location[2]
    v = g.matrix[r - mb['min_row']][c - mb['min_col']]
    if v != orients.index(o) + 1:
        enc_bad.append((tuple(b.location), v))
check(not enc_bad,
      f'矩陣值 = orientations 下標+1（48/48；偏差 {len(enc_bad)}'
      + (f' 首例 {enc_bad[0]}' if enc_bad else ''))
check(sorted({v for row in g.matrix for v in row})[0] == 0
      and max(v for row in g.matrix for v in row) <= len(orients),
      f'矩陣值域 0..{len(orients)}（0=空；實測 '
      f'{sorted({v for row in g.matrix for v in row})}）')

# 快照往返：save → restore → 位置集合（含朝向）逐塊相等
solved_pos = _positions(g)
hist = GameHistory()
hist.save_snapshot(g)
g.blocks = []                      # 破壞現狀，逼 restore 重建
hist.restore_snapshot(g, 0)
check(_positions(g) == solved_pos,
      'restore_snapshot 通用分支：48 塊位置+朝向逐塊還原')
check(g.is_solved(), 'restore 後仍是還原態')

# ======================================================================
print('\n== S2 完整回路：安全打亂 → GUI 回放層逆播 → is_solved ==')

SEED, ATT, STEP = 20261024, 40, 1
rng = random.Random(SEED)
gui = _gui_shatter(STEP)
g = gui.game
spec = g.spec
solved_pos = _positions(g)

final_board, _path, undo_path = safe_scramble(g.board, STEP, ATT, rng)
check(len(undo_path) > 0, f'安全打亂產出撤銷路徑（{len(undo_path)} 步可逆）')
check(_engine_state(final_board, spec) != solved_pos,
      '打亂終態 ≠ 還原態（集合層面）')

# ⚠️ 撤銷路徑要**反序**播：undo_path[k] 是前進第 k 步之後那個局面上的逆移
# 動，終態上第一條可走的是 undo_path[-1]（正序播第一條就會「側上無塊」——
# 那條縫在終態上根本不是有效縫，實測踩過）。
solve_path = list(reversed(undo_path))

# 把終態灌進 GUI（換 game 對象，與 file_ops 讀檔同型），歷史以打亂態為第 0 條
gui.game = EngineGame(final_board, kind='shatter')
g = gui.game
gui.selected_gap = None
gui.selected_block = None
gui.step_count = 0
gui.game_history.reset()
gui.game_history.save_snapshot(g)
gui.center_map()
scrambled_pos = _positions(g)
check(scrambled_pos == _engine_state(final_board, spec),
      'GUI 局面 = 打亂終態（含朝向）')

ops = [_move_to_op(mv, spec) for mv in solve_path]
check(all(len(o['rep_cell']) == 3 and isinstance(o['rep_cell'][2], str)
          for o in ops), '每個 op 的 rep_cell 帶齊朝向分量（字符串角色）')

# —— 先播前 3 步，中途做 Undo/Redo 逐態精確比對 ——
K = min(3, len(ops))
ok, err = _replay_via_gui(gui, ops[:K])
check(ok, f'回放層播完前 {K} 步（err={err!r}）')
state_after_K = _positions(g)
cur = final_board
for mv in solve_path[:K]:
    cur = cur.apply(mv)
check(state_after_K == _engine_state(cur, spec),
      f'播 {K} 步後局面 = 引擎 apply 逐鍵一致（含朝向）')
check(len(gui.game_history.history) == K + 1,
      f'每步一條快照（不合并；history={len(gui.game_history.history)} 條）')

ok_u, _ = gui.game_history.undo(g)
check(ok_u, '撤銷一步成功')
cur2 = final_board
for mv in solve_path[:K - 1]:
    cur2 = cur2.apply(mv)
check(_positions(g) == _engine_state(cur2, spec),
      '撤銷後局面 = 引擎 apply(K-1) 逐鍵一致（朝向沒丟）')
ok_r, _ = gui.game_history.redo(g)
check(ok_r and _positions(g) == state_after_K,
      '重做後局面回到播完 K 步的狀態')
ok_u2, _ = gui.game_history.undo(g)
check(ok_u2 and _positions(g) == _engine_state(cur2, spec),
      '再撤銷一步仍精確（不是「第一次對、其後漂移」）')
# ⚠️ 探完歷史必須**重做回尖端**再繼續播：撤銷把局面退回 K-1 步，
# 而 ops[K] 是第 K+1 步的動作，在 K-1 步的局面上不合法（實測踩過：
# 從中途局面續播會莫名其妙地「方向不可移動」）。
ok_back, _ = gui.game_history.redo(g)
check(ok_back and _positions(g) == state_after_K,
      '重做回播放下標 K 的局面（續播的前提）')

# —— 播完剩餘步，驗證 is_solved ——
ok2, err2 = _replay_via_gui(gui, ops[K:])
check(ok2, f'回放層播完剩餘 {len(ops) - K} 步（err={err2!r}）')
check(g.is_solved(), '逆路徑播完 → is_solved()（字面解法閉環）')
check(_positions(g) == solved_pos,
      '還原態與建局逐塊一致（位置+朝向）')
check(gui.step_count == len(ops),
      f'步數計數 = 逆路徑長度（{gui.step_count}/{len(ops)}）')

# 播完後再撤銷全部：應精確回到打亂態
for _ in range(len(ops)):
    gui.game_history.undo(g)
check(_positions(g) == scrambled_pos,
      '撤銷全部步 → 精確回到打亂態（歷史編碼雙向閉環）')

# ======================================================================
print('\n== S3 單步命令回路：select_gap → opt → move → Undo ==')

gui = _gui_shatter(1)
g = gui.game
spec = g.spec
solved_pos = _positions(g)

# 從還原態找一條活縫 + 一側可行的方向（不硬編碼：板型數據驅動）
pick = None
for fam in spec.seam_families:
    for line in range(-40, 41):
        if not (g.is_valid_gap(fam.name, line) and g.is_live_gap(fam.name, line)):
            continue
        for side in (0, 1):
            blk = gui._find_block_on_side(fam.name, line, side)
            if blk is None:
                continue
            g.opt(fam.name, line, blk)
            for letter in gui._gap_dir_letters(fam.name):
                if g.try_move(letter, 1):
                    pick = (fam.name, line, side, letter)
                    break
            g._clear_selection()
            if pick:
                break
        if pick:
            break
    if pick:
        break
check(pick is not None, '還原態存在「活縫 + 側 + 可行字母」組合'
      + (f'（實測 {pick}）' if pick else ''))

if pick:
    fam_name, line, side, letter = pick
    ok, msg = _cmd(gui, f'select_gap {fam_name} {line}')
    check(ok, f'select_gap {fam_name} {line} 成功（{msg}）')
    check(gui.selected_gap == (fam_name, line),
          f'selected_gap 回讀一致（{gui.selected_gap}）')
    blk = gui._find_block_on_side(fam_name, line, side)
    gui.game.opt(fam_name, line, blk)
    gui.selected_block = blk
    moved = gui.move_selected_blocks(letter)
    check(moved, f'move_selected_blocks({letter!r}) 成功')
    check(_positions(g) != solved_pos, '這一步真的移動了塊')
    check(gui.step_count == 1, f'step_count = 1（實測 {gui.step_count}）')
    check(not g.is_solved(), '移動後不是還原態')
    # 矩陣編碼跟著更新（不是寫 1 的方形占位）
    g.update_matrix()
    vals = sorted({v for row in g.matrix for v in row})
    check(any(v > 1 for v in vals),
          f'移動後矩陣值仍帶朝向編碼（實測值域 {vals[:6]}...）')
    ok_u, _ = gui.game_history.undo(g)
    check(ok_u, 'Undo 成功')
    check(_positions(g) == solved_pos,
          'Undo 後逐塊回到還原態（位置+朝向）')
    check(g.is_solved(), 'Undo 後 is_solved')

# 死縫：碎三角沒有「有效卻選不動」的死縫（縫線表只給真縫線，48 個移動
# 覆蓋 12 條縫的兩側）——這裡反過來釘住「有效 ⇒ 活」
dead_pick = []
for fam in spec.seam_families:
    for line in range(-80, 81):
        if g.is_valid_gap(fam.name, line) and not g.is_live_gap(fam.name, line):
            dead_pick.append((fam.name, line))
check(not dead_pick,
      f'還原態沒有「有效卻選不動」的死縫（違例 {dead_pick[:3]}）')

# 劈塊的線不是縫：選它必須被拒（舊模型這裡一律通過 → 選中後畫出鋸齒）
cut_line = None
for fam in spec.seam_families:
    good = [ln for ln in range(-80, 81) if g.is_valid_gap(fam.name, ln)]
    for ln in range(min(good) + 1, max(good)):
        if ln not in good and any(x < ln for x in good) and any(x > ln for x in good):
            cut_line = (fam.name, ln)
            break
    if cut_line:
        break
check(cut_line is not None, f'存在劈塊的線號（實測 {cut_line}）')
if cut_line:
    before_sel = gui.selected_gap
    ok, msg = _cmd(gui, f'select_gap {cut_line[0]} {cut_line[1]}')
    check(not ok, f'劈塊線 select_gap 被拒（ok={ok} msg={msg!r}）')
    check(gui.selected_gap == before_sel,
          '被拒後 selected_gap 保持原樣（沒有偷偷選上劈塊的線）')

# 陌生族名 / 非法線號
ok, msg = _cmd(gui, 'select_gap nope 3')
check(not ok and '类型必须' in msg, f'陌生族名被拒（msg={msg!r}）')
ok, msg = _cmd(gui, 'select_gap h 999')
check(not ok and '不合法' in msg, f'越界線號被拒（msg={msg!r}）')

# ======================================================================
print('\n== S4 六族全可玩 + 縫線嚴格共線 ==')

live_fams = {}
for fam in spec.seam_families:
    for line in range(-80, 81):
        if g.is_valid_gap(fam.name, line) and g.is_live_gap(fam.name, line):
            live_fams.setdefault(fam.name, []).append(line)
check(set(live_fams) == {f.name for f in spec.seam_families},
      f'六族都有活縫（實測 { {k: len(v) for k, v in live_fams.items()} }）')

import math  # noqa: E402

view = gui._polygon_view()
origin = gui._poly_view_origin(view)
worst = 0.0
empty = []
for fam_name, lines in live_fams.items():
    for ln in lines:
        segs = view.seam_segments(g.board, fam_name, ln, origin)
        pts = [p for s in segs for p in s]
        if len(pts) < 2:
            empty.append((fam_name, ln))
            continue
        x0, y0 = pts[0]
        far = max(pts, key=lambda p: (p[0] - x0) ** 2 + (p[1] - y0) ** 2)
        dx, dy = far[0] - x0, far[1] - y0
        L = math.hypot(dx, dy)
        worst = max(worst,
                    max(abs((p[0] - x0) * dy - (p[1] - y0) * dx) / L for p in pts))
check(not empty, f'每條活縫都有足跡（空足跡 {empty}）')
check(worst < 1e-6, f'全部活縫足跡嚴格共線（最大垂距 {worst:.1e} 像素）')

# ======================================================================
print('\n== S5 舊形態無回歸（三條專用分支互不搶占）==')

for kind, kw, label in (
        ('square', dict(m=4, n=4), '方形（else 0/1 分支）'),
        ('mi', dict(m=3, n=3), '米字（Q_ORDER 8-bit 分支）'),
        ('triangle', dict(m=3, n=3, triangle_side=3), '三角（k 2-bit 分支）')):
    gg = create_adapter_puzzle(kind, step=2, **kw)
    before = _positions(gg)
    h = GameHistory()
    h.save_snapshot(gg)
    gg.blocks = []
    h.restore_snapshot(gg, 0)
    check(_positions(gg) == before,
          f'{label}：快照往返逐塊一致（{len(before)} 塊）')
    check(gg.is_solved(), f'{label}：restore 後仍是還原態')

# 碎三角仍走通用分支（不被上面三條搶占）
gg = create_adapter_puzzle('shatter', 4, 4, 1)
before = _positions(gg)
h = GameHistory()
h.save_snapshot(gg)
gg.blocks = []
h.restore_snapshot(gg, 0)
check(_positions(gg) == before,
      f'碎三角（通用分支）：快照往返逐塊一致（{len(before)} 塊，含朝向）')

# ======================================================================
print('\n== S6 菜單入口 / 分榜鍵 / 存檔往返 / 模式攔截（S3 收尾）==')

from puzzle_types import create_puzzle, puzzle_key  # noqa: E402

gui6 = _gui_shatter(2)

# —— 菜單條目：模型子菜單裡的碎三角檔位（由 models/*.json 决定）——
# 碎三角原本在「異形」子菜單硬編碼；改成文件驅動後搬到「模型謎題」子菜單，
# 條目由註冊表生成——丟一個 json 就多一項，GUI 一行不用改。
gui6._refresh_puzzle_presets()
models_menu = gui6.puzzle_sub_presets['models']
shatter_items = [p for p in models_menu if len(p) >= 5 and p[4] == 'shatter']
check(len(shatter_items) >= 2,
      f'模型子菜單有 {len(shatter_items)} 個碎三角檔位（實測 {shatter_items}）')
if shatter_items:
    # 模型條目全部落在「模型文件」那個分組標題之下——分組標題只出現在
    # 子菜單第 0 項（條目按模型名排序，碎三角不一定排第一；用戶自己
    # 搭出來的模型（models/222.json 這類）隨時會插到前面）。
    check(models_menu and models_menu[0][0] == '__group__',
          f'模型子菜單應以分組標題開頭（實得 {models_menu[:1]}）')
    first_group = models_menu.index(models_menu[0])
    check(first_group == 0 and models_menu.index(shatter_items[0]) > 0,
          '碎三角檔位在「模型文件」分組內（不是散在子菜單外）')
leftover = [p for p in gui6.puzzle_sub_presets['exotic']
            if len(p) >= 5 and p[4] == 'shatter']
check(not leftover, '異形子菜單裡不再有硬編碼的碎三角條目（避免兩處入口）')

# —— 分榜鍵：與矩形 4×4 不混榜（矩陣 21×31 vs 4×4，串味即成績全錯）——
check(puzzle_key(1, 4, 4, kind='shatter') == '1~shatter',
      f"碎三角鍵 = {puzzle_key(1, 4, 4, kind='shatter')!r}（無尺寸維度）")
check(puzzle_key(1, 4, 4, kind='shatter') != puzzle_key(1, 4, 4),
      '碎三角鍵與矩形 4×4 鍵不相等')

# —— 當前局信息：kind / key / label / 打勾 ——
check(gui6._current_kind() == 'shatter', f'_current_kind = {gui6._current_kind()!r}')
check(gui6._current_puzzle_key() == '2~shatter',
      f'_current_puzzle_key = {gui6._current_puzzle_key()!r}')
check(gui6._current_puzzle_label() == '碎三角 等级2',
      f'_current_puzzle_label = {gui6._current_puzzle_label()!r}')
cur_key = gui6._current_puzzle_key()
check(gui6._preset_is_current(('等级2', 4, 4, 2, 'shatter'), cur_key)
      and not gui6._preset_is_current(('等级1', 4, 4, 1, 'shatter'), cur_key),
      '等級2 檔位打勾、等級1 不打勾（_preset_puzzle_key 比對）')

# —— create_puzzle 對 shatter 可分派（不靜默落回方形）——
cp = create_puzzle(4, 4, 2, kind='shatter')
check(isinstance(cp, EngineGame) and cp.kind == 'shatter'
      and len(cp.blocks) == 48,
      'create_puzzle(kind=shatter) → EngineGame 48 塊（無靜默方形回退）')

# —— 存檔往返：_build_save_data → _load_save_data（換一台 GUI 載入）——
data = gui6._build_save_data()
check(data['version'] == 2 and data['puzzle'].get('type') == 'shatter',
      f"存檔標明形態（version={data['version']} "
      f"type={data['puzzle'].get('type')!r}）")
gui7 = _gui_shatter(1)          # 先建一局別的，確保載入真的換了盤
gui7._load_save_data(data)
check(getattr(gui7.game, 'kind', '') == 'shatter'
      and len(gui7.game.blocks) == 48,
      '載入後是碎三角 48 塊（不是方形 4×4）')
check(_positions(gui7.game) == _positions(gui6.game),
      '載入後局面逐塊一致（位置+朝向）')
check(gui7.current_step == 2 and gui7._current_kind() == 'shatter',
      '載入後等級/形態鍵正確')

# —— 模式攔截（2026-10-25 細化）——
# · 競速：碎三角仍明拒（export_map 的方形分支把 24 朝向壓成 '#'，成績無意義）
# · 創造：**放行**——創造模式裡的「搭積木（自由板型）」不依賴當前盤面形態
#   （編輯器自建預覽局）；形態限制下沉到「格子畫布」「打亂狀態設計」兩個
#   子入口各自攔。
ok_t = gui6.set_game_mode('timed')
check(not ok_t and gui6.game_mode == 'practice',
      f'set_game_mode(timed) 被拒且留在練習（ok={ok_t} '
      f'mode={gui6.game_mode!r}）')
ok_c = gui6.set_game_mode('create')
check(ok_c and gui6.game_mode == 'create',
      f'set_game_mode(create) 對模型板型放行（搭積木不挑形態，ok={ok_c} '
      f'mode={gui6.game_mode!r}）')
gui6._ann_btn_home_restore()
gui6._ann_btn_design()
check(gui6._ann_view != 'design',
      f'格子畫布仍對模型板型明拒（view={gui6._ann_view!r}）')

# 帶著 timed 進碎三角：建局自動退回練習並說明（不留丟朝向的競速局）
gui6.game_mode = 'timed'
gui6.new_shatter_puzzle(1)
check(gui6.game_mode == 'practice',
      f'建局把 timed 退回練習（mode={gui6.game_mode!r}）')
check('碎三角' in gui6.macro_notify_msg,
      f'退回練習有說明（msg={gui6.macro_notify_msg!r}）')

# —— Ctrl+R 重建仍是碎三角（不靜默換方形）——
gui6.reset_puzzle()
check(getattr(gui6.game, 'kind', '') == 'shatter' and gui6.is_solved(),
      'reset_puzzle 重建碎三角且為還原態')

# —— 設計畫布 / 手動構造 / 隨機生成：入口明拒（重建走方形 create_puzzle）——
gui6._ann_btn_design()
check(gui6._ann_view != 'design', '高級選項對碎三角明拒（不進設計畫布）')
gui6._ann_btn_manual_build()
check(gui6._ann_view != 'build', '手動構造對碎三角明拒')
gui6._ann_btn_random_gen()
check(gui6._ann_sub_dialog != 'gen', '隨機生成對碎三角明拒')

# —— 指標面板：報「未實裝」而不是用矩形公式在質心晶格上算 0.0% ——
check(gui6._mp_kind() == 'shatter', f'_mp_kind = {gui6._mp_kind()!r}')
check(gui6._mp_kind() not in gui6._MP_SUPPORTED,
      '指標面板對碎三角給未實裝占位（不落方形分支）')

# —— 成績回放：碎三角成績明拒（無 #/_ 字符地圖，載入會靜默變形）——
rec = {'puzzle_key': '2~shatter', 'm': 4, 'n': 4, 'step': 2,
       'initial_matrix': 'x', 'numbered': False}
check(gui6._rp_is_shatter(rec), '_rp_is_shatter 認得碎三角成績')
before_pos = _positions(gui6.game)
gui6._rp_load_into_practice(rec)
check(_positions(gui6.game) == before_pos,
      '載入練習被拒：盤面沒被換成方形')

# —— HTTP 狀態：kind=shatter 且塊帶 orient（mod 在質心晶格上無分組語義）——
st = gui6._get_game_status()
check(st['puzzle'] == '1~shatter', f"狀態 puzzle 鍵 = {st['puzzle']!r}")
check(all('orient' in b and 'mod' not in b for b in st['blocks']),
      '狀態塊帶 orient、無 mod')

print('\n' + '=' * 70)
if failures:
    print(f'FAIL {len(failures)}:')
    for f in failures:
        print(f'  · {f}')
    sys.exit(1)
print('ALL PASS')
